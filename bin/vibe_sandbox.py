#!/usr/bin/env python3
"""Startet einen Agentenlauf optional in einer bubblewrap-Sandbox (F7).

Aufruf:
    vibe_sandbox.py <projekt> -- <befehl> [argumente ...]
    vibe_sandbox.py <projekt> --check [--json]
    vibe_sandbox.py <projekt> --enabled        # Exit 0 = Sandbox an, 1 = aus
    vibe_sandbox.py <projekt> --print-command -- <befehl> ...
    vibe_sandbox.py <projekt>                      # Status anzeigen

Die Sandbox begrenzt Schreibzugriffe auf:
- die in ``.vibe/permissions.json`` erlaubten Verzeichnisse (F3),
- die im Projekt konfigurierten Build-Tool-Caches (``SANDBOX_TOOLS``),
- den Rückfrageordner ``questions`` des Laufzeitordners (F16, nur dieser
  Unterordner; Token, Protokolle und Laufregister bleiben unerreichbar) und
- die technisch notwendigen Caches für MCP-Laufzeiten und
- ``/tmp/opencode`` für den opencode-Zustand.

Zusätzlich gilt:
- ``/tmp`` ist ein privater tmpfs und wird nach dem Binden der erlaubten
  Verzeichnisse schreibgeschützt. Temporärdateien gehören nach ``TMPDIR`` im
  Zustandsordner; ein explizit erlaubtes ``/tmp`` bleibt schreibbar.
- ``/dev/shm`` ist ohne ausdrückliche Freigabe ein frisches, isoliertes
  tmpfs (kein Zugriff auf das Host-Verzeichnis; Bug B5).
- Der Zustandsort ist begrenzt und weicht bei zu langen Pfaden auf die kurze
  tmpfs-Wurzel ``/tmp/opencode/vsb`` aus, damit Werkzeug-Sockets die
  AF_UNIX-Pfadgrenze (108 Zeichen) nicht erreichen (Bug B5).
- ``.vibe`` des Projekts bleibt auch im beschreibbaren Projektverzeichnis nur
  lesend, damit ein Agent seine Sandbox-Konfiguration nicht für spätere Läufe
  verändern kann.

Das Wurzeldateisystem wird nur lesend eingebunden. Netzwerk bleibt verfügbar,
damit Modell- und MCP-Verbindungen funktionieren. Lesezugriffe auf das
Dateisystem werden nicht eingeschränkt; deshalb ist die Sandbox eine
Schreibgrenze, keine vollständige Abschottung.

Ist ``SANDBOX`` im Projekt auf keinen aktiven Wert (``on``, ``1``, ``true``,
``yes``; Groß-/Kleinschreibung egal) gesetzt, wird der Befehl ohne bubblewrap
ausgeführt. Ist die Sandbox aktiv und bubblewrap fehlt, bricht der Start ab; es
gibt keinen stillen Fallback ohne Sandbox.
"""
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

WRITE_DIRS_DEFAULT = "/tmp/opencode"
SANDBOX_ROOT = "/tmp/opencode/vibe-sandbox"
SHORT_STATE_ROOT = "/tmp/opencode/vsb"
# Sicherheitsabstand zur AF_UNIX-Grenze von 108 Zeichen (Bug B5, siehe
# docs/features/B5.md): Zustandspfade bleiben <= 84 Zeichen, damit
# nachgeschaltete Werkzeugpfade die Grenze nicht erreichen — z. B.
# ``TMPDIR = state + "/tmp"`` (<= 88 Zeichen) und darunter der tmux-Socket
# ``TMPDIR/tmux-<uid>/default`` (<= 106 Zeichen).
STATE_PATH_LIMIT = 84
TOOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")

# Caches, die für die jeweiligen Build-Werkzeuge beschreibbar sein müssen.
TOOL_CACHES = {
    "git": [],
    "make": [],
    "gcc": [],
    "python": ["~/.cache/pip", "~/.cache/uv"],
    "python3": ["~/.cache/pip", "~/.cache/uv"],
    "pip": ["~/.cache/pip"],
    "uv": ["~/.cache/uv"],
    "pipx": ["~/.cache/pipx", "~/.local/share/pipx"],
    "node": ["~/.npm", "~/.cache/node-gyp"],
    "npm": ["~/.npm", "~/.cache/node-gyp"],
    "npx": ["~/.npm", "~/.cache/node-gyp"],
    "yarn": ["~/.cache/yarn", "~/.config/yarn"],
    "pnpm": ["~/.local/share/pnpm", "~/.cache/pnpm"],
    "bun": ["~/.bun/install/cache"],
    "bunx": ["~/.bun/install/cache"],
    "deno": ["~/.cache/deno"],
    "gradle": ["~/.gradle"],
    "maven": ["~/.m2"],
    "mvn": ["~/.m2"],
    "android": ["~/.android", "~/.config/android"],
    "adb": ["~/.android", "~/.config/android"],
    "cargo": ["~/.cargo"],
    "rustc": ["~/.cargo"],
    "go": ["~/go/pkg/mod", "~/.cache/go-build"],
    "cmake": ["~/.cache/cmake"],
    "wine": ["~/.wine"],
    "wine64": ["~/.wine"],
    "java": ["~/.java"],
    "ghidra": ["~/.config/ghidra", "~/.ghidra"],
    "analyzeHeadless": ["~/.config/ghidra", "~/.ghidra", "~/.java"],
    "docker": ["~/.docker"],
    "podman": ["~/.local/share/containers"],
    "playwright": ["~/.cache/ms-playwright"],
    "pytest": ["~/.cache/pytest"],
}

# Lokale MCP-Server werden häufig über npx, uvx oder bunx gestartet. Ihre
# Caches bleiben deshalb unabhängig von SANDBOX_TOOLS beschreibbar.
MCP_CACHES = [
    "~/.npm",
    "~/.cache/uv",
    "~/.local/share/pnpm",
    "~/.bun/install/cache",
]

# Geräte, die bestimmte Werkzeuge benötigen. ``--dev-bind-try`` ist auch dann
# unschädlich, wenn das Gerät auf dem Host fehlt.
TOOL_DEVICES = {
    "android": ("/dev/kvm", "/dev/dri"),
    "adb": ("/dev/kvm", "/dev/dri"),
}

# Manche Werkzeuge legen ihren Cache über eine Umgebungsvariable ab. Der
# Android-Aufbau dieser Installation setzt z. B. GRADLE_USER_HOME außerhalb
# von ``~/.gradle``.
TOOL_ENV_CACHES = {
    "gradle": ("GRADLE_USER_HOME",),
    "android": ("GRADLE_USER_HOME",),
}

TOOL_DEFAULTS = {
    "generic": ["git", "python3"],
    "web": ["git", "node", "npm"],
    "android": ["git", "java", "android", "adb"],
    "docker": ["git", "docker"],
    "openwrt": ["git", "make", "gcc"],
    "rebuild": [
        "git", "python3", "wine", "java", "ghidra", "analyzeHeadless",
        "gdb", "strace", "ltrace", "strings", "objdump", "readelf",
        "appimagetool", "linuxdeploy", "patchelf", "podman",
    ],
}


def read_env_file(path):
    values = {}
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                match = re.match(r"\s*([A-Z_]+)=(.*)", line)
                if match:
                    values[match.group(1)] = (
                        match.group(2).strip().strip('"').strip("'")
                    )
    except OSError:
        return values
    return values


def normalize_tools(value):
    """Wandelt eine kommagetrennte oder durch Leerzeichen getrennte Liste um."""
    if isinstance(value, (list, tuple)):
        items = [str(item) for item in value]
    else:
        text = str(value or "")
        if any(char in text for char in ("\x00", "\n", "\r")):
            raise ValueError("Werkzeugliste enthält unerlaubte Steuerzeichen")
        items = re.split(r"[,\s]+", text.strip())
    tools = []
    for item in items:
        tool = item.strip()
        if not tool:
            continue
        if any(char in tool for char in ("\x00", "\n", "\r")):
            raise ValueError("Werkzeugname enthält unerlaubte Steuerzeichen")
        if not TOOL_RE.match(tool):
            raise ValueError(
                "Werkzeugname darf nur Buchstaben, Ziffern, '.', '_', '-' und '+' enthalten: "
                + tool
            )
        if tool not in tools:
            tools.append(tool)
    return tools


def normalize_dir(value):
    if not isinstance(value, str):
        raise ValueError("Pfad muss Text sein")
    text = value.strip()
    if not text:
        raise ValueError("Pfad fehlt")
    if any(char in text for char in ("\x00", "\n", "\r")):
        raise ValueError("Pfad enthält unerlaubte Steuerzeichen")
    expanded = os.path.expanduser(text)
    if not os.path.isabs(expanded):
        raise ValueError("Pfad muss absolut sein: " + text)
    path = os.path.realpath(os.path.abspath(expanded))
    if path == os.sep:
        raise ValueError("Das Wurzelverzeichnis / ist nicht als Schreibverzeichnis erlaubt")
    return path


def project_write_dirs(project):
    """Liest dieselbe Liste wie ``vibe rights`` (F3)."""
    path = os.path.join(project, ".vibe", "permissions.json")
    if not os.path.exists(path):
        return [normalize_dir(WRITE_DIRS_DEFAULT), os.path.realpath(project)]
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Schreibrechte nicht lesbar: " + str(error))
    if not isinstance(data, dict) or not isinstance(data.get("write_dirs"), list):
        raise ValueError(
            "Schreibrechte nicht lesbar: 'write_dirs' fehlt oder ist keine Liste"
        )
    result = []
    for value in data["write_dirs"]:
        path_value = normalize_dir(value)
        if path_value not in result:
            result.append(path_value)
    return result


def state_dir(project):
    """Zustandsort des Projekts unterhalb der Sandbox-Wurzel.

    Werkzeuge im Lauf legen Sockets (tmux, IPC) unterhalb dieser Pfade an; die
    AF_UNIX-Grenze liegt bei 108 Zeichen. Ist der berechnete Pfad länger als
    die sichere Begrenzung (Bug B5: NTFS-Arbeitsbäume mit langen Pfaden, ein
    nach oben gesetztes ``VIBE_SANDBOX_ROOT``), weicht die Funktion auf eine
    kurze tmpfs-Wurzel unter /tmp aus; der SHA-256-Präfix des Projektwegs
    bleibt als eindeutige Zuordnung erhalten. Die Begrenzung auf 84
    Zeichen (``STATE_PATH_LIMIT``) hält Sicherheitsabstand zur AF_UNIX-Grenze
    von 108: auch Nachfolger wie ``TMPDIR`` und der darunter liegende
    tmux-Socket-Pfad überschreiten die Grenze nicht.
    """
    digest = hashlib.sha256(os.path.realpath(project).encode("utf-8")).hexdigest()[:10]
    name = re.sub(r"[^A-Za-z0-9_-]", "_", os.path.basename(os.path.realpath(project)))
    base = os.environ.get("VIBE_SANDBOX_ROOT") or SANDBOX_ROOT
    path = os.path.join(os.path.abspath(os.path.expanduser(base)), f"{name}-{digest}")
    if len(path) <= STATE_PATH_LIMIT:
        return path
    return os.path.join(SHORT_STATE_ROOT, digest)


def git_common_dir(project):
    """Gemeinsamer Git-Ordner des Projekts (bei Arbeitskopien außerhalb).

    Der Paket-Läufer startet jeden Agenten in einer eigenen ``git worktree``-
    Arbeitskopie. Deren ``.git`` ist nur eine Verweisdatei; Commits schreiben
    in den gemeinsamen Git-Ordner des Integrationsprojekts. Ohne dessen
    Schreibfreigabe könnte der Agent in der Sandbox nicht committen.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                os.path.realpath(project),
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    path = result.stdout.strip()
    return os.path.realpath(path) if path else ""


def _cache_dirs(tools):
    result = []
    for tool in tools:
        for value in TOOL_CACHES.get(tool, []):
            path = normalize_dir(value)
            if path not in result:
                result.append(path)
        for variable in TOOL_ENV_CACHES.get(tool, []):
            value = os.environ.get(variable)
            if value:
                path = normalize_dir(value)
                if path not in result:
                    result.append(path)
    for value in MCP_CACHES:
        path = normalize_dir(value)
        if path not in result:
            result.append(path)
    return result


def status(project):
    """Beschreibt die Sandbox-Konfiguration, ohne Programme zu starten."""
    project = os.path.realpath(project)
    values = read_env_file(os.path.join(project, ".vibe", "project.env"))
    enabled = values.get("SANDBOX", "off").strip().lower() in (
        "on",
        "1",
        "true",
        "yes",
    )
    error = None
    try:
        tools = normalize_tools(values.get("SANDBOX_TOOLS", ""))
    except ValueError as exception:
        tools = []
        error = str(exception)
    try:
        permitted = project_write_dirs(project)
    except ValueError as exception:
        permitted = []
        error = str(exception) if not error else error + "; " + str(exception)
    state = state_dir(project)
    if enabled:
        try:
            caches = _cache_dirs(tools)
        except ValueError as exception:
            caches = []
            error = str(exception) if not error else error + "; " + str(exception)
        write_dirs = list(permitted)
        for value in [project, normalize_dir(WRITE_DIRS_DEFAULT)] + caches + [state]:
            if value not in write_dirs:
                write_dirs.append(value)
    else:
        caches = []
        write_dirs = list(permitted)
    bwrap = os.environ.get("VIBE_BWRAP") or shutil.which("bwrap")
    return {
        "project": project,
        "enabled": enabled,
        "tools": tools,
        "tool_caches": caches,
        "write_dirs": write_dirs,
        "state_dir": state,
        "bwrap": bwrap,
        "missing_tools": [tool for tool in tools if shutil.which(tool) is None],
        "error": error,
    }


def _bwrap_ok(path):
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def _ensure_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
        return None
    except OSError as error:
        return f"Verzeichnis nicht anlegbar ({path}): {error}"


def check(project):
    """Prüft Konfiguration, bubblewrap und die konfigurierten Werkzeuge."""
    state = status(project)
    problems = []
    if state["error"]:
        problems.append(state["error"])
    if not state["enabled"]:
        return {
            "ok": True,
            "enabled": False,
            "message": "Sandbox ist aus (SANDBOX=off). Der Befehl läuft ohne bubblewrap.",
            "missing_tools": [],
            "bwrap": state["bwrap"],
            "write_dirs": state["write_dirs"],
            "tools": state["tools"],
            "error": None,
        }
    if not _bwrap_ok(state["bwrap"]):
        problems.append(
            "bubblewrap (bwrap) fehlt oder ist nicht ausführbar; "
            "installiere bubblewrap im Container oder deaktiviere die Sandbox."
        )
    elif state["missing_tools"]:
        problems.append(
            "Fehlende Build-Werkzeuge: " + ", ".join(state["missing_tools"])
        )
    if not problems:
        for directory in state["write_dirs"]:
            problem = _ensure_dir(directory)
            if problem:
                problems.append(problem)
    if not problems:
        try:
            probe = subprocess.run(
                [
                    state["bwrap"],
                    "--ro-bind",
                    "/",
                    "/",
                    "--dev",
                    "/dev",
                    "--proc",
                    "/proc",
                    "--tmpfs",
                    "/tmp",
                    "--remount-ro",
                    "/tmp",
                    "--unshare-pid",
                    "--die-with-parent",
                    "--new-session",
                    "/bin/true",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as error:
            problems.append("bubblewrap startet nicht: " + str(error))
        else:
            if probe.returncode != 0:
                output = (probe.stdout + probe.stderr).strip()
                problems.append(
                    "bubblewrap startet nicht (unprivilegierte Benutzernamensräume "
                    "erlaubt?): " + (output or "Exit-Code " + str(probe.returncode))
                )
    if problems:
        message = "Sandbox nicht startbar: " + "; ".join(problems)
        ok = False
    else:
        message = (
            "Sandbox bereit: "
            + ", ".join(state["tools"] or ["keine Build-Werkzeuge"])
            + "."
        )
        ok = True
    return {
        "ok": ok,
        "enabled": True,
        "message": message,
        "missing_tools": state["missing_tools"],
        "bwrap": state["bwrap"],
        "write_dirs": state["write_dirs"],
        "tools": state["tools"],
        "error": state["error"],
    }


def runtime_dir():
    """Laufzeitordner wie ``vibe-run.sh``: ``VIBE_RUNTIME`` oder ``$VIBE/_logs``."""
    value = os.environ.get("VIBE_RUNTIME")
    if value:
        return os.path.abspath(os.path.expanduser(value))
    base = os.environ.get("VIBE")
    if base:
        return os.path.join(os.path.abspath(os.path.expanduser(base)), "_logs")
    return ""


def bwrap_argv(project, command, bwrap=None, runtime=None):
    """Baut die bubblewrap-Argumentliste; verändert keine Projektdateien.

    ``runtime`` bindet ausschließlich den Rückfrageordner ``questions``
    beschreibbar ein (F16). Der restliche Laufzeitordner mit Protokollen,
    Token und Laufregister bleibt unerreichbar; ohne ``runtime`` entsteht
    keine Bindung.
    """
    if not command:
        raise ValueError("Kein Befehl angegeben")
    state = status(project)
    if not state["enabled"]:
        raise ValueError("Sandbox ist aus")
    if state["error"]:
        raise ValueError(state["error"])
    executable = bwrap or state["bwrap"]
    if not _bwrap_ok(executable):
        raise ValueError(
            "bubblewrap (bwrap) fehlt oder ist nicht ausführbar; "
            "die Sandbox bricht ab, statt ohne Schutz zu starten."
        )
    questions = ""
    if runtime:
        questions = os.path.join(
            os.path.abspath(os.path.expanduser(str(runtime))), "questions"
        )
        problem = _ensure_dir(questions)
        if problem:
            raise ValueError(problem)
    directories = []
    for value in state["write_dirs"]:
        directory = os.path.realpath(os.path.abspath(os.path.expanduser(value)))
        if directory not in directories:
            directories.append(directory)
    state_path = state["state_dir"]
    if state_path not in directories:
        directories.append(state_path)
    # In einer Arbeitskopie liegt der beschreibbare Git-Zustand im
    # Integrationsprojekt; ohne diese Freigabe scheitert jeder Commit.
    common = git_common_dir(project)
    if common and common not in directories:
        directories.append(common)
    for directory in directories:
        problem = _ensure_dir(directory)
        if problem:
            raise ValueError(problem)
    data_home = os.path.join(state_path, "data")
    cache_home = os.path.join(state_path, "cache")
    state_home = os.path.join(state_path, "state")
    tmp_home = os.path.join(state_path, "tmp")
    for directory in (data_home, cache_home, state_home, tmp_home):
        problem = _ensure_dir(directory)
        if problem:
            raise ValueError(problem)

    argv = [
        executable,
        "--ro-bind",
        "/",
        "/",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
    ]
    # /dev/shm (Bug B5) vor allen Bindungen: bubblewrap stapelt Mounts in
    # Argumentreihenfolge. Bindungen auf Pfade unter /dev/shm (z. B. ein
    # Rückfrageordner oder ein Projekt im Prüf-tmpfs) müssen in der
    # isolierten Ansicht ansetzen, sonst überschattet der frische Mount die
    # Bindung. Ohne Freigabe bleibt das Host-Verzeichnis aus (der Agent
    # konnte dort außerhalb der erlaubten Verzeichnisse schreiben); mit
    # Freigabe übernimmt die Bindungsschleife unten die Rolle.
    if "/dev/shm" not in directories:
        argv += ["--tmpfs", "/dev/shm"]
    argv += [
        "--unshare-pid",
        "--die-with-parent",
        "--new-session",
        "--chdir",
        state["project"],
    ]
    for directory in directories:
        argv += ["--bind", directory, directory]
    # Rückfragen des Agenten (F16): nur der eigene Unterordner ist
    # beschreibbar, nicht der Laufzeitordner mit Token, Protokollen und
    # Laufregister. Die Bindung steht vor dem Schreibschutz von /tmp, weil
    # bubblewrap den Einhängepunkt im privaten tmpfs anlegen muss; ein
    # Laufzeitordner unter /tmp bleibt dadurch erreichbar, während der übrige
    # Inhalt von /tmp schreibgeschützt wird.
    if questions and questions not in directories:
        argv += ["--bind", questions, questions]
    # /tmp ist ein privater tmpfs, aber kein erlaubtes Schreibziel. Nach dem
    # Binden der erlaubten Verzeichnisse wird er wieder schreibgeschützt;
    # Werkzeuge legen Temporärdateien über TMPDIR im Zustandsordner ab.
    if "/tmp" not in directories:
        argv += ["--remount-ro", "/tmp"]
    # .vibe/project.env und .vibe/permissions.json steuern die Sandbox des
    # nächsten Laufs. Ein schreibender Agent dürfte sie nicht ändern, sonst
    # könnte er seine eigene Grenze für spätere Läufe aufheben.
    vibe_dir = os.path.join(state["project"], ".vibe")
    if state["project"] in directories and os.path.isdir(vibe_dir):
        argv += ["--ro-bind", vibe_dir, vibe_dir]
    devices = []
    for tool in state["tools"]:
        for device in TOOL_DEVICES.get(tool, []):
            if device not in devices:
                devices.append(device)
    for device in devices:
        argv += ["--dev-bind-try", device, device]
    auth = os.path.expanduser("~/.local/share/opencode/auth.json")
    if os.path.isfile(auth):
        target = os.path.join(data_home, "opencode", "auth.json")
        problem = _ensure_dir(os.path.dirname(target))
        if problem:
            raise ValueError(problem)
        argv += ["--ro-bind", auth, target]
    argv += [
        "--setenv",
        "XDG_DATA_HOME",
        data_home,
        "--setenv",
        "XDG_CACHE_HOME",
        cache_home,
        "--setenv",
        "XDG_STATE_HOME",
        state_home,
        "--setenv",
        "TMPDIR",
        tmp_home,
        "--",
    ]
    argv += list(command)
    return argv


def run(project, command):
    """Führt den Befehl aus; bei aktiver Sandbox ausschließlich über bwrap."""
    if not command:
        print("Kein Befehl angegeben.", file=sys.stderr)
        return 2
    state = status(project)
    if not state["enabled"]:
        try:
            os.execvpe(command[0], list(command), os.environ)
        except OSError as error:
            print("Befehl nicht ausführbar: " + str(error), file=sys.stderr)
            return 2
    checked = check(project)
    if not checked["ok"]:
        print(checked["message"], file=sys.stderr)
        return 2
    runtime = runtime_dir()
    if runtime:
        problem = _ensure_dir(os.path.join(runtime, "questions"))
        if problem:
            # Ohne Rückfrageordner bleibt der Lauf möglich, aber der Agent
            # kann keine Rückfrage stellen; das wird ausdrücklich gemeldet.
            print("Rückfragen nicht verfügbar: " + problem, file=sys.stderr)
            runtime = ""
    try:
        argv = bwrap_argv(project, command, runtime=runtime)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    try:
        os.execvpe(argv[0], argv, os.environ)
    except OSError as error:
        print("bubblewrap nicht ausführbar: " + str(error), file=sys.stderr)
        return 2


def _print_status(state):
    print(
        "Sandbox für "
        + os.path.basename(state["project"])
        + ": "
        + ("an" if state["enabled"] else "aus")
    )
    print("bubblewrap:", state["bwrap"] or "fehlt")
    print("Build-Werkzeuge:", " ".join(state["tools"]) or "(keine)")
    if state["missing_tools"]:
        print("Fehlende Werkzeuge:", ", ".join(state["missing_tools"]))
    print("Schreibverzeichnisse:")
    for directory in state["write_dirs"]:
        print("  " + directory)
    print("opencode-Zustand:", state["state_dir"])
    if state["error"]:
        print("Fehler:", state["error"])
    print(
        "Grenze: Schreiben nur in diesen Verzeichnissen und Tool-Caches; "
        "/tmp ist privat und schreibgeschützt, Temporärdateien liegen im "
        "Zustandsordner. Netzwerk, MCP und Lesezugriffe bleiben verfügbar."
    )


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    project = os.path.abspath(os.path.expanduser(arguments.pop(0)))
    if not os.path.isdir(project):
        print("Projektordner fehlt: " + project, file=sys.stderr)
        return 2
    as_json = False
    do_check = False
    print_command = False
    enabled_only = False
    command = []
    while arguments:
        argument = arguments.pop(0)
        if argument == "--":
            command = arguments
            break
        if argument == "--json":
            as_json = True
        elif argument == "--check":
            do_check = True
        elif argument == "--enabled":
            enabled_only = True
        elif argument == "--print-command":
            print_command = True
        elif argument in ("-h", "--help"):
            print(__doc__.strip())
            return 0
        else:
            print("Unbekannte Option: " + argument, file=sys.stderr)
            return 2
    if enabled_only:
        enabled = status(project)["enabled"]
        print("on" if enabled else "off")
        return 0 if enabled else 1
    if do_check:
        result = check(project)
        if as_json:
            print(json.dumps(result, ensure_ascii=False, indent=1))
        else:
            print(result["message"])
        return 0 if result["ok"] else 1
    if print_command:
        if not command:
            print("Kein Befehl angegeben.", file=sys.stderr)
            return 2
        state = status(project)
        runtime = runtime_dir()
        if runtime:
            problem = _ensure_dir(os.path.join(runtime, "questions"))
            if problem:
                print("Rückfragen nicht verfügbar: " + problem, file=sys.stderr)
                runtime = ""
        try:
            if state["enabled"]:
                print(shlex.join(bwrap_argv(project, command, runtime=runtime)))
            else:
                print(shlex.join(command))
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 2
        return 0
    if not command:
        state = status(project)
        if as_json:
            print(json.dumps(state, ensure_ascii=False, indent=1))
        else:
            _print_status(state)
        return 0
    return run(project, command)


if __name__ == "__main__":
    sys.exit(main())
