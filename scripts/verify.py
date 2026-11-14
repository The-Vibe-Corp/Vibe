#!/usr/bin/env python3
"""Isolierte Projektprüfung für vibe (V-002).

Aufruf über den Wrapper: bash scripts/verify.sh quick|full [--project DIR] [--keep]

Die Prüfung liest die Befehle aus <projekt>/.vibe/project.env und führt sie in
einer temporären Umgebung aus:

* HOME, VIBE, TMPDIR und die XDG-Verzeichnisse liegen unter einem eigenen
  temporären Prüfverzeichnis. Die Konfiguration des Aufrufers wird nur gelesen.
* Ein geerbtes TMUX wird entfernt; TMUX_TMPDIR zeigt auf ein eigenes
  Verzeichnis. So kann kein Test den tmux-Server der aufrufenden Sitzung
  beenden (Dashboard, opencode, laufender Lauf).
* Für Dashboard, opencode, Tests und Prüfung werden eigene freie Ports
  bereitgestellt (VIBE_UI_PORT, VIBE_OPENCODE_PORT, VIBE_TEST_PORT,
  VIBE_VERIFY_PORT).
* Der Vollmodus muss eine Teststruktur und tatsächlich ausgeführte Tests
  nachweisen. Ein Lauf ohne Tests oder mit "Ran 0 tests" ist kein Erfolg.

Exitcodes:
  0  Prüfung erfolgreich
  1  unerwarteter interner Fehler
  2  Aufruf- oder Modusfehler
  3  fehlende oder ungültige Prüfkonfiguration
  4  benötigtes Werkzeug fehlt
  5  Prüfbefehl ist fehlgeschlagen
  6  Testnachweis fehlt oder ist unvollständig (nur full)
"""
import glob
import json
import os
import re
import shlex
import shutil
import site
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_USAGE = 2
EXIT_CONFIG = 3
EXIT_TOOL = 4
EXIT_CHECK = 5
EXIT_TESTS = 6

MODES = ("quick", "full")
DEFAULT_TEST_PATTERN = r"Ran (\d+) tests?"
TEMP_PREFIX = "vibe-verify-"

USAGE = (
    "Aufruf: bash scripts/verify.sh quick|full [--project DIR] [--keep]\n"
    "\n"
    "  quick    schnelle statische Prüfung (VERIFY_QUICK)\n"
    "  full     vollständige Prüfung inklusive Testnachweis (VERIFY_FULL)\n"
    "  --project DIR  Projekt mit .vibe/project.env (Standard: dieses Repository)\n"
    "  --keep   temporäres Prüfverzeichnis auch bei Erfolg behalten\n"
    "\n"
    "Exitcodes: 0 Erfolg, 1 interner Fehler, 2 Aufruf, 3 Konfiguration,\n"
    "           4 Werkzeug, 5 Prüfbefehl, 6 Testnachweis."
)


class VerifyError(Exception):
    """Abbruch mit definiertem Exitcode und verständlicher Meldung."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def fail(code, message):
    raise VerifyError(code, message)


def print_usage():
    print(USAGE)


def parse_args(argv):
    mode = None
    project = None
    keep = False
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in ("-h", "--help"):
            print_usage()
            raise SystemExit(EXIT_OK)
        if arg == "--keep":
            keep = True
        elif arg == "--project":
            index += 1
            if index >= len(argv):
                fail(EXIT_USAGE, "--project benötigt ein Verzeichnis.")
            project = Path(argv[index]).expanduser()
        elif arg.startswith("--project="):
            project = Path(arg.split("=", 1)[1]).expanduser()
        elif arg.startswith("-"):
            fail(EXIT_USAGE, f"Unbekannte Option: {arg}")
        elif mode is None:
            if arg not in MODES:
                fail(
                    EXIT_USAGE,
                    f"Unbekannter Modus '{arg}'. Erlaubt: quick, full.",
                )
            mode = arg
        else:
            fail(EXIT_USAGE, f"Überzähliges Argument: {arg}")
        index += 1
    if mode is None:
        fail(EXIT_USAGE, "Modus fehlt.")
    return mode, project, keep


def read_project_env(path):
    values = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        fail(EXIT_CONFIG, f"Prüfkonfiguration {path} ist nicht lesbar: {error}")
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export "):].lstrip()
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", stripped)
        if not match:
            fail(
                EXIT_CONFIG,
                f"{path}:{number}: erwartet KEY=WERT, gefunden: {stripped}",
            )
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[match.group(1)] = value
    return values


def project_root(argument):
    root = argument if argument is not None else Path(__file__).resolve().parent.parent
    root = Path(root).resolve()
    if not (root / ".vibe" / "project.env").is_file():
        fail(
            EXIT_CONFIG,
            f"{root}/.vibe/project.env fehlt. Prüfbefehle müssen dort stehen.",
        )
    return root


def select_command(values, mode, env_file):
    key = "VERIFY_QUICK" if mode == "quick" else "VERIFY_FULL"
    command = values.get(key, "").strip()
    if not command:
        fail(EXIT_CONFIG, f"{key} fehlt in {env_file}.")
    if "TODO" in command:
        fail(
            EXIT_CONFIG,
            f"{key} ist in {env_file} noch ein Platzhalter (TODO) und kein Prüfbefehl.",
        )
    return command


def check_tools(values):
    declared = shlex.split(values.get("VERIFY_TOOLS", ""))
    missing = [tool for tool in declared if shutil.which(tool) is None]
    if missing:
        fail(
            EXIT_TOOL,
            "Benötigte Werkzeuge fehlen: "
            + ", ".join(missing)
            + " (VERIFY_TOOLS in .vibe/project.env).",
        )
    return declared


def allocate_ports(count):
    ports = []
    while len(ports) < count:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        if port in (8787, 4096) or port in ports:
            continue
        ports.append(port)
    return ports


def prepare_environment(base):
    home = base / "home"
    vibe = base / "vibe"
    tmp = base / "tmp"
    screenshots = base / "screenshots"
    opencode_config = base / "opencode-config"
    opencode_state = base / "state"
    tmux = base / "tmux"
    for folder in (
        home / ".config",
        home / ".cache" / "opencode",
        home / ".local" / "share",
        home / ".local" / "state",
        vibe / "_toolchain",
        vibe / "_logs",
        tmp,
        screenshots,
        opencode_config,
        opencode_state,
        tmux,
    ):
        folder.mkdir(parents=True, exist_ok=True)
    # tmux akzeptiert TMUX_TMPDIR nur ohne fremde Schreibrechte.
    tmux.chmod(0o700)
    # opencode startet ohne vorhandenen Modellcache einen Hintergrunddienst und
    # wartet auf dessen Port. Eine leere Cache-Markierung lässt 'opencode models'
    # den mitgelieferten Katalog verwenden; es werden keine echten Anbieter-
    # oder Modellaufrufe ausgeführt.
    (home / ".cache" / "opencode" / "models.json").write_text(
        "{}\n", encoding="utf-8"
    )
    gitconfig = base / "gitconfig"
    gitconfig.write_text("", encoding="utf-8")
    # Entwicklungsabhängigkeiten (z. B. Playwright) liegen häufig im
    # Benutzer-Site-Paket. Der Pfad wird gelesen, geschrieben wird nur im
    # temporären HOME.
    python_userbase = site.getuserbase()
    playwright_browsers = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or str(
        Path.home() / ".cache" / "ms-playwright"
    )

    ui_port, opencode_port, test_port, verify_port = allocate_ports(4)
    (opencode_config / "service.json").write_text(
        json.dumps({"port": opencode_port}) + "\n", encoding="utf-8"
    )
    environment = os.environ.copy()
    for key in list(environment):
        if key.startswith("VIBE_") or key == "PYTHONPATH" or key.startswith("XDG_"):
            environment.pop(key, None)
    # Ein geerbtes TMUX gewinnt in tmux gegen TMUX_TMPDIR. Ohne Entfernen
    # erreicht ein Test, der seinen tmux-Server aufräumt, den Server der
    # aufrufenden Sitzung und beendet Dashboard, opencode und laufende Läufe.
    for key in ("TMUX", "TMUX_PANE"):
        environment.pop(key, None)
    environment.update(
        {
            "HOME": str(home),
            "VIBE": str(vibe),
            "PYTHONUSERBASE": python_userbase,
            "TMPDIR": str(tmp),
            "TMUX_TMPDIR": str(tmux),
            "XDG_STATE_HOME": str(opencode_state),
            "VIBE_VERIFY_ROOT": str(base),
            "VIBE_VERIFY_SCREENSHOT_DIR": str(screenshots),
            "VIBE_UI_PORT": str(ui_port),
            "VIBE_OPENCODE_PORT": str(opencode_port),
            "VIBE_TEST_PORT": str(test_port),
            "VIBE_VERIFY_PORT": str(verify_port),
            "VIBE_NO_CONTAINER": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "GIT_CONFIG_GLOBAL": str(gitconfig),
            "GIT_CONFIG_NOSYSTEM": "1",
            "OPENCODE_CONFIG_DIR": str(opencode_config),
            "OPENCODE_DISABLE_MODELS_FETCH": "1",
            "OPENCODE_DISABLE_AUTOUPDATE": "1",
        }
    )
    # Chromium ist eine installierte Entwicklungsabhängigkeit und wird nur
    # gelesen. Ohne diesen Pfad würde Playwright ihn im temporären HOME suchen.
    if Path(playwright_browsers).is_dir():
        environment["PLAYWRIGHT_BROWSERS_PATH"] = playwright_browsers
    return environment


def start_opencode_service(environment):
    """Startet den isolierten opencode-Dienst für schnelle Modellabfragen.

    Der Dienst läuft mit temporärem HOME, Konfigurations- und Statusverzeichnis.
    Er listet nur Modelle; es werden keine Modell- oder MCP-Werkzeuge aufgerufen.
    Fehlt opencode oder startet der Dienst nicht, läuft die Prüfung ohne ihn
    weiter (die Modellwarnungen entfallen dann).
    """
    if shutil.which("opencode") is None:
        return False
    try:
        subprocess.run(
            ["opencode", "service", "start"],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    port = int(environment["VIBE_OPENCODE_PORT"])
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def stop_opencode_service(environment):
    if shutil.which("opencode") is None:
        return
    try:
        subprocess.run(
            ["opencode", "service", "stop"],
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def required_test_files(root, specs):
    missing = []
    for spec in specs:
        candidate = root / spec
        if any(char in spec for char in "*?["):
            paths = [Path(item) for item in glob.glob(str(candidate), recursive=True)]
        elif candidate.is_dir():
            paths = [path for path in candidate.rglob("*") if path.is_file()]
        elif candidate.is_file():
            paths = [candidate]
        else:
            paths = []
        matches = [path for path in paths if "test" in path.name.lower()]
        if not matches:
            missing.append(spec)
    return missing


def test_count(output, pattern):
    try:
        regex = re.compile(pattern)
    except re.error as error:
        fail(EXIT_CONFIG, f"VERIFY_TEST_PATTERN ist ungültig: {error}")
    if regex.groups < 1:
        fail(
            EXIT_CONFIG,
            "VERIFY_TEST_PATTERN benötigt mindestens eine Gruppe für die Testanzahl.",
        )
    return sum(int(match.group(1)) for match in regex.finditer(output))


def run_command(command, root, environment, log):
    log.write(f"$ {command}\n")
    process = subprocess.Popen(
        ["bash", "-c", command],
        cwd=str(root),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    chunks = []
    if process.stdout is None:
        return process.wait(), ""
    for line in process.stdout:
        chunks.append(line)
        log.write(line)
        sys.stdout.write(line)
        if not line.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()
    return process.wait(), "".join(chunks)


def main(argv=None):
    base = None
    mode = None
    try:
        mode, project_argument, keep = parse_args(
            list(sys.argv[1:] if argv is None else argv)
        )
        root = project_root(project_argument)
        env_file = root / ".vibe" / "project.env"
        values = read_project_env(env_file)
        command = select_command(values, mode, env_file)
        tools = check_tools(values)

        specs = shlex.split(values.get("VERIFY_TESTS", ""))
        minimum = 1
        if mode == "full":
            if not specs:
                fail(
                    EXIT_TESTS,
                    f"VERIFY_TESTS fehlt in {env_file}. Ohne Teststruktur ist "
                    "'full' kein vollständiger Nachweis.",
                )
            missing = required_test_files(root, specs)
            if missing:
                fail(
                    EXIT_TESTS,
                    "Keine Testdateien gefunden für: "
                    + ", ".join(missing)
                    + " (VERIFY_TESTS).",
                )
            raw_minimum = values.get("VERIFY_MIN_TESTS", "1").strip() or "1"
            try:
                minimum = int(raw_minimum)
            except ValueError:
                fail(EXIT_CONFIG, f"VERIFY_MIN_TESTS ist keine Zahl: {raw_minimum}")
            if minimum < 1:
                fail(EXIT_CONFIG, "VERIFY_MIN_TESTS muss mindestens 1 sein.")
            pattern = values.get("VERIFY_TEST_PATTERN", "").strip() or DEFAULT_TEST_PATTERN
        else:
            pattern = ""

        base = Path(tempfile.mkdtemp(prefix=TEMP_PREFIX))
        log_path = base / "verify.log"
        environment = prepare_environment(base)
        service_started = (
            start_opencode_service(environment) if mode == "full" else False
        )
        try:
            print(f"=== vibe-Prüfung: {mode} ===")
            print(f"Projekt: {root}")
            print(f"Prüfverzeichnis: {base}")
            if tools:
                print("Werkzeuge: " + " ".join(tools))
            sys.stdout.flush()

            with log_path.open("w", encoding="utf-8") as log:
                log.write(f"Modus: {mode}\nProjekt: {root}\n")
                status, output = run_command(command, root, environment, log)

            if status != 0:
                fail(
                    EXIT_CHECK,
                    f"Prüfbefehl ist fehlgeschlagen (Befehl-Exit {status}, "
                    f"Prüf-Exit {EXIT_CHECK}).",
                )

            if mode == "full":
                count = test_count(output, pattern)
                if count < minimum:
                    fail(
                        EXIT_TESTS,
                        f"Nur {count} ausgeführte Tests erkannt, Minimum {minimum}. "
                        "Fehlende Tests sind kein bestandener Vollnachweis.",
                    )
                print(f"OK: Tests erkannt: {count} (Minimum {minimum}).")
        finally:
            if service_started:
                stop_opencode_service(environment)
    except VerifyError as error:
        print(f"FEHLT: {error.message}", file=sys.stderr)
        if error.code == EXIT_USAGE:
            print(USAGE, file=sys.stderr)
        if base is not None:
            print(f"Prüfverzeichnis behalten: {base}", file=sys.stderr)
        return error.code
    except KeyboardInterrupt:
        message = "FEHLT: Prüfung abgebrochen."
        if base is not None:
            message += f" Prüfverzeichnis behalten: {base}"
        print(message, file=sys.stderr)
        return EXIT_INTERNAL

    if keep:
        print(f"Prüfverzeichnis behalten: {base}")
    else:
        shutil.rmtree(base, ignore_errors=True)
        print(f"Prüfverzeichnis entfernt: {base}")
    print(f"OK: Prüfung '{mode}' erfolgreich. (Exit {EXIT_OK})")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
