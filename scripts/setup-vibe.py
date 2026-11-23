#!/usr/bin/env python3
"""Universeller, interaktiver Setup für vibe.

Aufruf:
    python3 scripts/setup-vibe.py
    py -3 scripts\\setup-vibe.py            (Windows)

Der Setup erkennt Linux (Ubuntu/Debian, Fedora, Bazzite, Arch), Container
(Docker/Podman/Toolbx/Distrobox) und Windows. Er prüft die benötigten
Werkzeuge, bietet deren Installation über den vorhandenen Paketmanager an,
installiert die vibe-Programmdateien und kann eine bestehende Installation
wiederverwenden, ohne Laufzeitdaten oder persönliche Einstellungen zu
überschreiben.

Nur Python-Standardbibliothek. Es werden keine Projektbefehle, Modellaufrufe
oder Router-Aktionen ausgeführt.

Seit V-018 kennt der Setup zusätzlich Vorschau, Versionskennung, Sicherung,
Rollback und Uninstall. Eine Aktualisierung wird nur ausgeführt, wenn kein
Agentenlauf aktiv ist; mit ``--force`` lässt sich diese Sperre ausdrücklich
aufheben. Laufzeitdaten, persönliche Konfiguration, Sicherungen und Projekte
werden weder beim Update noch beim Uninstall entfernt.
"""
import argparse
import json
import os
import platform as _platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
MIN_PYTHON = (3, 8)
if str(KIT / "bin") not in sys.path:
    sys.path.insert(0, str(KIT / "bin"))
import vibe_harness
import vibe_paths

PROGRAM_FILES = (
    "vibe",
    "vibe-run.sh",
    "vibe_harness.py",
    "vibe_limits.py",
    "vibe_keys.py",
    "vibe_gates.py",
    "vibe_runs.py",
    "vibe_packages.py",
    "vibe-web.py",
    "vibe_mcp.py",
    "vibe_opencode.py",
    "vibe_models.py",
    "vibe_sandbox.py",
    "vibe_paths.py",
    "vibe_ui_config.py",
    "vibe_storage.py",
    "vibe_guide.py",
    "vibe_questions.py",
    "vibe_autonomous.py",
    "vibe_services.py",
    "vibe_github.py",
    "vibe_issues.py",
    "fritz-reconnect.py",
)
WEB_FILES = (
    "index.html", "styles.css", "app.js", "i18n.js",
    # AP22: neue Standard-UI plus die dauerhaft erreichbare klassische Shell.
    "classic.html", "nova.css", "nova-core.js", "nova-home.js",
    "nova-project.js", "nova-output.js", "nova-agents.js",
    "nova-activity.js", "nova-settings.js",
    # F34: Auswertungen (WP3 ersetzt den Platzhalter inhaltlich).
    "nova-evals.js",
    # F33: Combobox-Widget und Logo/Favicon (auch als /static/vibe.svg ausgeliefert).
    "nova-widgets.js", "vibe.svg",
)
RUNTIME_FILES = ("vibe.json", "models.json", "profiles.json", "fritz.json", "costs.json")
VERSION_FILE = "VERSION"
VERSION_META = "version.json"
BACKUP_META = "backup.json"
UNINSTALL_BACKUP_PREFIX = "backup-uninstall-"
UNKNOWN_VERSION = "unbekannt"
LIVE_RUN_STATES = ("starting", "running")
OFFICIAL_OPENCODE = "https://opencode.ai/docs/"
OPENCODE_NPM_PACKAGE = "opencode-ai"
OFFICIAL_PI = "https://pi.dev/docs/latest"
PI_NPM_PACKAGE = "@earendil-works/pi-coding-agent"
PI_NODE_MINIMUM = "22.19"
BAD_TARGETS = {
    "/", "/usr", "/etc", "/bin", "/sbin", "/lib", "/lib64", "/proc", "/sys",
    "/dev", "/boot", "/root", "/run", "/var", "/tmp", "/home", "/opt", "/mnt",
    "/media",
}
DEBIAN_IDS = {"ubuntu", "debian", "linuxmint", "pop", "elementary", "zorin", "kali", "neon"}
FEDORA_IDS = {"fedora", "rhel", "centos", "rocky", "almalinux", "bazzite"}
ARCH_IDS = {"arch", "manjaro", "endeavouros", "cachyos", "garuda"}
IMMUTABLE_IDS = {"bazzite", "silverblue", "kinoite", "coreos"}

DEPENDENCIES = (
    {
        "name": "git",
        "why": "Projektverwaltung, Status und Nachweise",
        "required": True,
        "packages": {"apt-get": "git", "dnf": "git", "pacman": "git", "winget": ("Git.Git",)},
    },
    {
        "name": "tmux",
        "why": "Agentenläufe, Dashboard und opencode-Server",
        "required": True,
        "packages": {"apt-get": "tmux", "dnf": "tmux", "pacman": "tmux"},
    },
    {
        "name": "flock",
        "why": "Durchgangssperre für parallele Läufe",
        "required": True,
        "packages": {"apt-get": "util-linux", "dnf": "util-linux", "pacman": "util-linux"},
    },
    {
        "name": "curl",
        "why": "Health-Checks und Netzzugriffe",
        "required": True,
        "packages": {"apt-get": "curl", "dnf": "curl", "pacman": "curl"},
    },
    {
        "name": "opencode",
        "why": "Agentenläufe und Modellzugriff (Harness opencode)",
        "required": True,
        "harnesses": ("opencode",),
        "packages": {},
    },
    {
        "name": "node",
        "why": "Laufzeit für Pi (mindestens " + PI_NODE_MINIMUM + ")",
        "required": True,
        "harnesses": ("pi",),
        "packages": {"apt-get": "nodejs", "dnf": "nodejs", "pacman": "nodejs"},
    },
    {
        "name": "pi",
        "why": "Agentenläufe mit dem Harness Pi",
        "required": True,
        "harnesses": ("pi",),
        "packages": {},
    },
)


class SetupError(Exception):
    """Verständlicher Fehler im Setup; die Installation wird nicht fortgesetzt."""


def read_os_release(path=None):
    """Liest /etc/os-release ohne externe Abhängigkeit."""
    target = Path(path) if path else Path("/etc/os-release")
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return {}
    data = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _read_proc_version():
    try:
        return Path("/proc/version").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def detect_platform(system=None, os_release=None, exists=None, env=None,
                    proc_version=None, which=None):
    """Erkennt Betriebssystem, Distribution, Container und Paketmanager."""
    system = system if system is not None else _platform.system()
    exists = exists or os.path.exists
    env = env if env is not None else os.environ
    which = which or shutil.which
    release = os_release if os_release is not None else read_os_release()
    version_text = proc_version if proc_version is not None else _read_proc_version()

    lowered = (system or "").lower()
    if lowered.startswith("win"):
        os_name = "windows"
    elif lowered == "linux":
        os_name = "linux"
    else:
        os_name = lowered or "unknown"

    identifiers = []
    if release.get("ID"):
        identifiers.append(release["ID"].lower())
    identifiers.extend(part.lower() for part in release.get("ID_LIKE", "").split() if part)
    distro = identifiers[0] if identifiers else ("windows" if os_name == "windows" else "unknown")

    family = None
    if os_name == "windows":
        family = "windows"
    else:
        for candidate, members in (("debian", DEBIAN_IDS), ("fedora", FEDORA_IDS), ("arch", ARCH_IDS)):
            if any(identifier in members for identifier in identifiers):
                family = candidate
                break

    container = bool(
        env.get("container")
        or exists("/.dockerenv")
        or exists("/run/.containerenv")
        or exists("/run/.toolboxenv")
    )
    wsl = bool(
        env.get("WSL_DISTRO_NAME")
        or env.get("WSL_INTEROP")
        or "microsoft" in (version_text or "").lower()
    )
    immutable = bool(
        exists("/run/ostree-booted")
        or distro in IMMUTABLE_IDS
        or release.get("VARIANT_ID", "").lower() in IMMUTABLE_IDS
    )

    manager = None
    if os_name == "windows":
        manager = "winget"
    elif immutable and not container:
        manager = None
    elif family == "debian":
        manager = "apt-get"
    elif family == "fedora":
        manager = "dnf"
    elif family == "arch":
        manager = "pacman"

    name = release.get("NAME") or ("Windows" if os_name == "windows" else distro.title())
    version = release.get("VERSION_ID") or ""
    label = (name + " " + version).strip() or os_name
    if container:
        label += " (Container)"
    if wsl:
        label += " (WSL)"

    return {
        "os": os_name,
        "distro": distro,
        "family": family,
        "manager": manager,
        "container": container,
        "immutable": immutable,
        "wsl": wsl,
        "wsl_available": bool(which("wsl.exe") or which("wsl")),
        "npm_available": bool(which("npm")),
        "label": label,
        "release": release,
    }


def python_ok(version=None):
    """Prüft die Python-Mindestversion (3.8)."""
    version = version or sys.version_info
    return tuple(version[:2]) >= MIN_PYTHON


def _dependency_applies(dependency, harness):
    """Ein Harness-spezifisches Werkzeug gilt nur für den gewählten Harness."""
    scoped = dependency.get("harnesses")
    if not scoped:
        return True
    return (harness or "opencode") in scoped


def dependency_report(info, which=None, harness=None):
    """Liefert je Werkzeug Präsenz, Installierbarkeit und konkreten Hinweis.

    Werkzeuge mit ``harnesses`` gelten nur für den gewählten Harness; ohne
    Angabe bleibt opencode der Standard, damit bestehende Aufrufer unverändert
    das bisherige Ergebnis erhalten.
    """
    which = which or shutil.which
    result = []
    for dependency in DEPENDENCIES:
        if not _dependency_applies(dependency, harness):
            continue
        name = dependency["name"]
        present = bool(which(name))
        installable = False
        hint = ""
        if not present:
            if info["os"] == "windows":
                if "winget" in dependency["packages"]:
                    installable = True
                elif name in ("tmux", "flock"):
                    hint = (
                        "Unter Windows nur über WSL2 oder Docker verfügbar. "
                        "Native Windows-Installationen können vibe-Dateien nutzen, "
                        "aber keine tmux-Agentenläufe starten."
                    )
                elif name == "opencode" and info.get("npm_available"):
                    installable = True
                elif name == "pi" and info.get("npm_available"):
                    installable = True
                elif name == "pi":
                    hint = (f"Pi benötigt Node.js {PI_NODE_MINIMUM}+. Offiziell: "
                            f"{OFFICIAL_PI} (kein automatisches Netzskript).")
                else:
                    hint = f"Bitte offiziell installieren: {OFFICIAL_OPENCODE} (kein automatisches Netzskript)."
            elif info["immutable"] and not info["container"]:
                hint = (
                    "Bazzite/ostree: nicht auf dem Host schichten, sondern im "
                    "Container ausführen (im Quellordner: distrobox enter <name> -- "
                    "python3 scripts/setup-vibe.py)."
                )
            elif info["manager"] and dependency["packages"].get(info["manager"]):
                installable = True
            elif name == "opencode" and info.get("npm_available"):
                installable = True
            elif name == "pi" and info.get("npm_available"):
                installable = True
            elif name == "opencode":
                hint = f"Bitte offiziell installieren: {OFFICIAL_OPENCODE} (kein automatisches Netzskript)."
            elif name == "pi":
                hint = (f"Pi benötigt Node.js {PI_NODE_MINIMUM}+. Offiziell: "
                        f"{OFFICIAL_PI} (kein automatisches Netzskript).")
            else:
                hint = "Kein Paket für diese Plattform bekannt; bitte manuell installieren."
        result.append(
            {
                "name": name,
                "why": dependency["why"],
                "required": dependency["required"],
                "present": present,
                "installable": installable,
                "hint": hint,
            }
        )
    return result


def privilege_prefix(info, is_root, has_sudo):
    """Ermittelt den Befehlspräfix oder None, wenn keine Installation möglich ist."""
    if info["os"] == "windows":
        return []
    if info["immutable"] and not info["container"]:
        return None
    if is_root:
        return []
    return ["sudo"] if has_sudo else None


def install_commands(info, names, prefix):
    """Baut Argumentlisten für die fehlenden Werkzeuge; niemals eine Shellzeile."""
    if prefix is None or not names:
        return []
    if info["immutable"] and not info["container"]:
        return []
    commands = []
    if info["os"] == "windows":
        for dependency in DEPENDENCIES:
            if dependency["name"] in names and "winget" in dependency["packages"]:
                package = dependency["packages"]["winget"][0]
                commands.append(["winget", "install", "--id", package, "-e"])
    else:
        manager = info.get("manager")
        if manager:
            packages = []
            for dependency in DEPENDENCIES:
                if dependency["name"] not in names:
                    continue
                package = dependency["packages"].get(manager)
                if package and package not in packages:
                    packages.append(package)
            if packages:
                if manager == "pacman":
                    commands.append(prefix + ["pacman", "-S", "--needed", "--noconfirm"] + packages)
                else:
                    commands.append(prefix + [manager, "install", "-y"] + packages)
    if "opencode" in names and info.get("npm_available"):
        commands.append(prefix + ["npm", "install", "-g", OPENCODE_NPM_PACKAGE])
    if "pi" in names and info.get("npm_available"):
        commands.append(prefix + ["npm", "install", "-g", "--ignore-scripts", PI_NPM_PACKAGE])
    return commands


def default_target(info, home, environ=None):
    """Standard-Zielordner: vorhandenes VIBE oder ~/VibeCode."""
    environ = os.environ if environ is None else environ
    configured = environ.get("VIBE")
    if configured:
        return Path(os.path.expanduser(configured))
    return Path(home) / "VibeCode"


def _prod_config(environ=None):
    """Liest die persönliche Konfiguration (Profil prod); fehlerhafte Datei -> SetupError."""
    try:
        config = vibe_paths.load_config(environ=environ)
        return vibe_paths._profile_config(config, "prod", vibe_paths.default_config_path(environ))
    except vibe_paths.ConfigError as error:
        raise SetupError(str(error)) from error


def _configured_path(key, environ_key, environ):
    environ = os.environ if environ is None else environ
    if environ.get(environ_key):
        return Path(os.path.abspath(os.path.expanduser(environ[environ_key])))
    configured = _prod_config(environ).get(key)
    if isinstance(configured, str) and configured.strip():
        return Path(os.path.abspath(os.path.expanduser(configured.strip())))
    return None


def default_workspace(info, home, environ=None):
    """Standard-Workspace: VIBE, dann Konfiguration, sonst ~/VibeCode."""
    return _configured_path("workspace", "VIBE", environ) or (Path(home) / "VibeCode")


def default_install(workspace, environ=None):
    """Standard-Installationsort: VIBE_INSTALL, Konfiguration, sonst <workspace>/_toolchain."""
    return _configured_path("install", "VIBE_INSTALL", environ) or (Path(workspace) / "_toolchain")


def default_logs(workspace, environ=None):
    """Standard-Logverzeichnis: VIBE_RUNTIME, Konfiguration, sonst <workspace>/_logs."""
    return _configured_path("runtime", "VIBE_RUNTIME", environ) or (Path(workspace) / "_logs")


def validate_install(value, workspace, kit, home):
    """Wie validate_target; getrennt vom Workspace (Workspace nicht im Installationsort)."""
    install = Path(validate_target(value, kit, home))
    workspace = Path(workspace).resolve(strict=False)
    if install == workspace:
        raise SetupError(
            "Installationsort und Workspace dürfen nicht identisch sein "
            "(Vorschlag: <Workspace>/_toolchain oder ein eigener Ordner)."
        )
    if install in workspace.parents:
        raise SetupError("Der Workspace darf nicht innerhalb des Installationsorts liegen.")
    return str(install)


def validate_logs(value, workspace, install, kit, home):
    """Wie validate_target; das Logverzeichnis ist weder Workspace noch Installationsort."""
    logs = Path(validate_target(value, kit, home))
    for label, other in (("Workspace", workspace), ("Installationsort", install)):
        other = Path(other).resolve(strict=False)
        if logs == other:
            raise SetupError(f"Das Logverzeichnis darf nicht mit dem {label} identisch sein.")
        if logs in other.parents:
            raise SetupError(f"Der {label} darf nicht innerhalb des Logverzeichnisses liegen.")
    return str(logs)


def save_paths_config(workspace, install, logs, timestamp=None, environ=None):
    """Trägt Pfade unter profiles.prod der persönlichen Konfiguration ein.

    ``runtime`` wird nur gespeichert, wenn es vom Standard <workspace>/_logs
    abweicht. Andere Einstellungen bleiben erhalten; eine vorhandene Datei wird
    vorher gesichert; eine ungültige Datei wird nicht überschrieben.
    """
    environ = os.environ if environ is None else environ
    timestamp = timestamp or time.strftime("%Y%m%d-%H%M%S")
    path = Path(vibe_paths.default_config_path(environ))
    try:
        data = vibe_paths.load_config(str(path), environ)
    except vibe_paths.ConfigError as error:
        raise SetupError(f"Konfiguration nicht geändert: {error}") from error
    profiles = data.get("profiles")
    if profiles is None:
        profiles = {}
    if not isinstance(profiles, dict):
        raise SetupError(f"Konfiguration {path}: 'profiles' muss ein Objekt sein; nicht geändert.")
    prod = profiles.get("prod")
    if prod is None:
        prod = {}
    if not isinstance(prod, dict):
        raise SetupError(f"Konfiguration {path}: 'profiles.prod' muss ein Objekt sein; nicht geändert.")
    wanted = {"workspace": str(workspace), "install": str(install)}
    if Path(logs) != Path(workspace) / "_logs":
        wanted["runtime"] = str(logs)
    updated = dict(prod)
    updated.update(wanted)
    if "runtime" not in wanted:
        updated.pop("runtime", None)
    if updated == prod:
        return {"path": str(path), "changed": False, "backup": None}
    profiles["prod"] = updated
    data["profiles"] = profiles
    backup = None
    if path.is_file():
        backup_path = path.with_name(path.name + f".bak-{timestamp}")
        counter = 1
        while backup_path.exists():
            backup_path = path.with_name(path.name + f".bak-{timestamp}-{counter}")
            counter += 1
        shutil.copy2(str(path), str(backup_path))
        backup = str(backup_path)
    _write_text_atomic(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return {"path": str(path), "changed": True, "backup": backup}


def validate_target(value, kit, home):
    """Lehnt allgemeine, gefährliche und mit dem Quellcode identische Ziele ab."""
    if value is None or not str(value).strip():
        raise SetupError("Kein Zielordner angegeben.")
    path = Path(os.path.abspath(os.path.expanduser(str(value).strip())))
    resolved = path.resolve(strict=False)
    kit_path = Path(os.path.abspath(str(kit))).resolve(strict=False)
    home_path = Path(os.path.abspath(str(home))).resolve(strict=False)
    if str(path) in BAD_TARGETS or str(resolved) in BAD_TARGETS:
        raise SetupError(f"Zielordner zu allgemein: {path}")
    if resolved == home_path:
        raise SetupError("Der Home-Ordner selbst ist kein geeigneter vibe-Arbeitsbereich.")
    if resolved == kit_path:
        raise SetupError("Der Quellcode-Ordner kann nicht gleichzeitig Zielordner sein.")
    if kit_path in resolved.parents:
        raise SetupError("Der Zielordner darf nicht innerhalb des Quellcode-Ordners liegen.")
    if resolved.exists() and not resolved.is_dir():
        raise SetupError(f"Ziel ist keine Ordner: {resolved}")
    return str(resolved)


def detect_existing(vibe_root):
    """Erfasst eine vorhandene Installation, ohne etwas zu verändern."""
    toolchain = Path(vibe_root)
    programs = [name for name in PROGRAM_FILES if (toolchain / "bin" / name).is_file()]
    web = [name for name in WEB_FILES if (toolchain / "bin" / "web" / name).is_file()]
    runtime = [name for name in RUNTIME_FILES if (toolchain / name).is_file()]
    return {
        "toolchain": toolchain.is_dir(),
        "programs": programs,
        "web": web,
        "runtime": runtime,
        "complete": len(programs) == len(PROGRAM_FILES) and len(web) == len(WEB_FILES),
    }


def read_kit_version(kit=None, runner=None):
    """Liest Version und Commit des Quellstands; rät nichts, wenn Angaben fehlen."""
    kit = Path(kit) if kit else KIT
    version = UNKNOWN_VERSION
    version_file = kit / VERSION_FILE
    if version_file.is_file():
        try:
            text = version_file.read_text(encoding="utf-8").strip()
        except OSError:
            text = ""
        if text:
            version = text
    commit = None
    if (kit / ".git").exists():
        runner = runner or subprocess.run
        try:
            completed = runner(
                ["git", "-C", str(kit), "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            completed = None
        if completed is not None and getattr(completed, "returncode", 1) == 0:
            text = (getattr(completed, "stdout", "") or "").strip()
            if re.fullmatch(r"[0-9a-f]{7,40}", text):
                commit = text
    return {"version": version, "commit": commit}


def read_installed_version(vibe_root):
    """Liest die Versionskennung einer Installation; None heißt nicht installiert."""
    path = Path(vibe_root) / VERSION_META
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": UNKNOWN_VERSION, "error": f"{path} ist nicht lesbar"}
    if not isinstance(data, dict):
        return {"version": UNKNOWN_VERSION, "error": f"{path} enthält kein Objekt"}
    data.setdefault("version", UNKNOWN_VERSION)
    return data


def _version_payload(kit, mode, timestamp, runner=None):
    kit_info = read_kit_version(kit, runner=runner)
    return {
        "version": kit_info["version"],
        "commit": kit_info["commit"],
        "installed_at": timestamp,
        "mode": mode,
        "source": str(Path(kit).resolve()),
    }


def _install_sources(kit):
    """Liefert (relativer Pfad, Quelldatei, ausführbar) für alle Programmdateien."""
    for name in PROGRAM_FILES:
        yield f"bin/{name}", Path(kit) / "bin" / name, True
    for name in WEB_FILES:
        yield f"bin/web/{name}", Path(kit) / "bin" / "web" / name, False
    templates = Path(kit) / "templates"
    if templates.is_dir():
        for source in sorted(templates.rglob("*")):
            if source.is_file():
                yield source.relative_to(kit).as_posix(), source, False
    yield "models.json", Path(kit) / "data" / "models.json", False


def build_install_plan(kit, vibe_root, mode="update", timestamp=None, runner=None):
    """Berechnet die Installation, ohne eine Datei zu schreiben.

    Die Vorschau und die tatsächliche Installation verwenden dieselbe Planung;
    dadurch kann die Vorschau nicht von der Ausführung abweichen.
    """
    if mode not in ("reuse", "update"):
        raise SetupError(f"Unbekannter Modus: {mode}")
    kit = Path(kit)
    vibe_root = Path(vibe_root)
    source_program = kit / "bin" / "vibe"
    if not source_program.is_file():
        raise SetupError(f"Unvollständiges Quellverzeichnis: {source_program} fehlt")
    toolchain = vibe_root
    plan = {
        "target": str(toolchain),
        "mode": mode,
        "files": [],
        "warnings": [],
        "version": {
            "from": read_installed_version(vibe_root),
            "to": _version_payload(kit, mode, timestamp or time.strftime("%Y%m%d-%H%M%S"), runner),
        },
    }
    for relative, source, executable in _install_sources(kit):
        if not source.is_file():
            if relative == "models.json":
                plan["warnings"].append(
                    "data/models.json fehlt im Quellverzeichnis; der Modellkatalog wird nicht installiert."
                )
                continue
            raise SetupError(f"Unvollständiges Quellverzeichnis: {source} fehlt")
        destination = toolchain / relative
        if relative == "models.json" and destination.exists():
            action = "skip"
            reason = "Laufzeitdatei bleibt erhalten"
        elif destination.exists():
            if mode == "reuse":
                action = "skip"
                reason = "vorhanden (wird wiederverwendet)"
            elif destination.is_file() and destination.read_bytes() == source.read_bytes():
                action = "skip"
                reason = "unverändert"
            else:
                action = "backup"
                reason = "wird gesichert und ersetzt"
        else:
            action = "copy"
            reason = "neu"
        plan["files"].append(
            {
                "path": relative,
                "action": action,
                "reason": reason,
                "source": str(source),
                "executable": executable,
            }
        )
    return plan


def describe_plan(plan):
    """Formatiert eine Vorschau als Zeilen; schreibt nichts."""
    before = plan["version"]["from"]
    before_text = (before or {}).get("version", UNKNOWN_VERSION) if before else "nicht installiert"
    after = plan["version"]["to"]["version"]
    lines = [
        f"Vorschau: Ziel {plan['target']} (Modus {plan['mode']})",
        f"Version: {before_text} -> {after}",
    ]
    symbols = {"copy": "+", "backup": "~", "skip": "="}
    for entry in plan["files"]:
        lines.append(f"  {symbols[entry['action']]} {entry['path']} ({entry['reason']})")
    for warning in plan["warnings"]:
        lines.append("Hinweis: " + warning)
    return lines


def _copy_file(source, destination):
    """Atomarer Dateikopiervorgang innerhalb des Zielordners."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".vibe-setup-", dir=str(destination.parent))
    os.close(handle)
    try:
        shutil.copyfile(str(source), temporary)
        try:
            shutil.copymode(str(source), temporary)
        except OSError:
            pass
        os.replace(temporary, str(destination))
    finally:
        if os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _write_text_atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".vibe-setup-", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        os.replace(temporary, str(path))
    finally:
        if os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _make_executable(path):
    try:
        os.chmod(str(path), 0o755)
    except OSError:
        pass


def _backup_file(source, backup_root, relative):
    """Sichert eine vorhandene Datei kollisionsfrei unter dem relativen Pfad."""
    target = Path(backup_root) / relative
    counter = 1
    while target.exists():
        target = Path(backup_root) / (relative + f".{counter}")
        counter += 1
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source), str(target))
    return target.relative_to(Path(backup_root)).as_posix()


def _next_backup_root(toolchain, timestamp):
    base = Path(toolchain) / f"backup-{timestamp}"
    if not base.exists():
        return base
    counter = 2
    while (Path(toolchain) / f"backup-{timestamp}-{counter}").exists():
        counter += 1
    return Path(toolchain) / f"backup-{timestamp}-{counter}"


def _remove_empty_parents(path, stop):
    """Entfernt leere Elternordner bis ``stop``; andere Dateien bleiben."""
    path = Path(path).parent
    stop = Path(stop)
    while path != stop and stop in path.parents:
        try:
            path.rmdir()
        except OSError:
            return
        path = path.parent


def _restore_file(source, destination):
    """Setzt eine gesicherte Datei atomar zurück, unabhängig vom Kopierpfad des Updates."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".vibe-restore-", dir=str(destination.parent))
    os.close(handle)
    try:
        shutil.copy2(str(source), temporary)
        os.replace(temporary, str(destination))
    finally:
        if os.path.exists(temporary):
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _safe_relative(relative):
    """Nur einfache relative Pfade innerhalb der Installation zulassen."""
    if not isinstance(relative, str) or not relative:
        return None
    path = Path(relative)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        return None
    return path.as_posix()


def _checked_paths(values):
    """Validiert Pfadlisten aus einer Sicherung, bevor etwas geschrieben wird."""
    checked = []
    for relative in values:
        safe = _safe_relative(relative)
        if safe is None:
            raise SetupError(f"Sicherung enthält einen ungültigen Pfad: {relative!r}")
        checked.append(safe)
    return checked


def _restore_backup(toolchain, backup_root):
    """Stellt eine Sicherung wieder her und entfernt nur deren neu angelegte Dateien."""
    toolchain = Path(toolchain)
    backup_root = Path(backup_root)
    meta_path = backup_root / BACKUP_META
    meta = {}
    if meta_path.is_file():
        try:
            loaded = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                meta = loaded
        except (OSError, ValueError):
            meta = {}
    backed_up = meta.get("backed_up")
    if not isinstance(backed_up, list):
        backed_up = [
            path.relative_to(backup_root).as_posix()
            for path in sorted(backup_root.rglob("*"))
            if path.is_file() and path.name != BACKUP_META
        ]
    backed_up = _checked_paths(backed_up)
    created = meta.get("created") if isinstance(meta.get("created"), list) else []
    created = _checked_paths(created)
    restored = []
    removed = []
    for relative in backed_up:
        source = backup_root / relative
        if not source.is_file():
            continue
        destination = toolchain / relative
        _restore_file(source, destination)
        if relative.startswith("bin/"):
            _make_executable(destination)
        restored.append(relative)
    for relative in created:
        destination = toolchain / relative
        if destination.is_file() or destination.is_symlink():
            destination.unlink()
            removed.append(relative)
            _remove_empty_parents(destination, toolchain)
    version_path = toolchain / VERSION_META
    if "version_before_existed" in meta:
        before = meta.get("version_before")
        if meta.get("version_before_existed") and isinstance(before, dict):
            _write_text_atomic(
                version_path,
                json.dumps(before, indent=1, ensure_ascii=False) + "\n",
            )
        elif not meta.get("version_before_existed") and version_path.exists():
            version_path.unlink()
    return {"restored": restored, "removed": removed}


def _undo_install(vibe_root, result, launcher=None):
    """Nimmt eine geschriebene, aber nicht fertiggestellte Installation zurück.

    Gibt ``restored`` zurück, wenn eine Sicherung eingespielt wurde, sonst
    ``removed``, wenn die neu angelegten Dateien entfernt wurden.
    """
    toolchain = Path(vibe_root)
    if launcher:
        path = Path(launcher["path"])
        if launcher.get("backed_up"):
            _restore_file(Path(launcher["backed_up"]), path)
        elif launcher.get("created"):
            try:
                if path.is_symlink() or path.is_file():
                    path.unlink()
            except OSError:
                pass
    backup = result.get("backup")
    if backup:
        _restore_backup(toolchain, Path(backup))
        return "restored"
    for relative in result.get("copied", []):
        destination = toolchain / relative
        if destination.is_file() or destination.is_symlink():
            destination.unlink()
            _remove_empty_parents(destination, toolchain)
    version = toolchain / VERSION_META
    if result.get("wrote_version") and version.is_file():
        version.unlink()
    if not result.get("existing_before"):
        try:
            toolchain.rmdir()
        except OSError:
            pass
    return "removed"


def install_program_files(kit, vibe_root, mode="update", timestamp=None, runner=None):
    """Kopiert Programmdateien und Vorlagen; Laufzeitdaten bleiben unangetastet.

    Bei einem Update werden ersetzte Dateien vorher gesichert. Schlägt der
    Vorgang ab, wird der vorherige Stand aus dieser Sicherung wiederhergestellt.
    Die Sicherung selbst bleibt für einen späteren Rollback erhalten.
    """
    timestamp = timestamp or time.strftime("%Y%m%d-%H%M%S")
    plan = build_install_plan(kit, vibe_root, mode=mode, timestamp=timestamp, runner=runner)
    kit = Path(kit)
    vibe_root = Path(vibe_root)
    toolchain = vibe_root
    changed = [entry for entry in plan["files"] if entry["action"] in ("copy", "backup")]
    existing_before = toolchain.is_dir()
    result = {
        "copied": [],
        "skipped": [],
        "backed_up": [],
        "created": [],
        "warnings": list(plan["warnings"]),
        "backup": None,
        "version": plan["version"],
        "plan": plan,
        "existing_before": existing_before,
        "wrote_version": False,
    }
    backup_root = None
    if mode == "update" and existing_before:
        backup_root = _next_backup_root(toolchain, timestamp)
        try:
            backup_root.mkdir(parents=True, exist_ok=True)
            meta = {
                "timestamp": timestamp,
                "mode": mode,
                "version_before": plan["version"]["from"],
                "version_before_existed": (toolchain / VERSION_META).is_file(),
                "version_after": plan["version"]["to"],
                "backed_up": [],
                "created": [],
            }
            for entry in changed:
                destination = toolchain / entry["path"]
                if entry["action"] == "backup":
                    relative = _backup_file(destination, backup_root, entry["path"])
                    meta["backed_up"].append(relative)
                    result["backed_up"].append(relative)
                elif entry["action"] == "copy":
                    meta["created"].append(entry["path"])
                    result["created"].append(entry["path"])
            _write_text_atomic(
                backup_root / BACKUP_META,
                json.dumps(meta, indent=1, ensure_ascii=False) + "\n",
            )
        except OSError as error:
            if backup_root.is_dir():
                shutil.rmtree(str(backup_root), ignore_errors=True)
            raise SetupError(
                f"Sicherung konnte nicht angelegt werden; nichts geändert: {error}"
            ) from error
        result["backup"] = str(backup_root)

    wrote_version = False
    try:
        for entry in changed:
            destination = toolchain / entry["path"]
            _copy_file(Path(entry["source"]), destination)
            if entry["executable"]:
                _make_executable(destination)
            result["copied"].append(entry["path"])
        result["skipped"] = [
            entry["path"] for entry in plan["files"] if entry["action"] == "skip"
        ]
        if mode == "update" or not existing_before:
            _write_text_atomic(
                toolchain / VERSION_META,
                json.dumps(plan["version"]["to"], indent=1, ensure_ascii=False) + "\n",
            )
            wrote_version = True
            result["wrote_version"] = True
    except Exception as error:
        if backup_root is not None:
            try:
                _restore_backup(toolchain, backup_root)
            except OSError as restore_error:
                raise SetupError(
                    f"Update abgebrochen; Wiederherstellung fehlgeschlagen: {restore_error}"
                ) from error
            raise SetupError(
                f"Update abgebrochen, vorheriger Stand wiederhergestellt: {error}"
            ) from error
        for relative in result["copied"]:
            destination = toolchain / relative
            if destination.is_file():
                try:
                    destination.unlink()
                except OSError:
                    pass
                _remove_empty_parents(destination, toolchain)
        if wrote_version and (toolchain / VERSION_META).exists():
            try:
                (toolchain / VERSION_META).unlink()
            except OSError:
                pass
        raise SetupError(f"Installation abgebrochen: {error}") from error
    return result


def _backup_sort_key(path):
    """Sortiert Sicherungen nach Zeitstempel und numerischem Zähler."""
    match = re.match(r"^(\d{8}-\d{6})(?:-(\d+))?$", path.name[len("backup-"):])
    if match:
        return (1, match.group(1), int(match.group(2) or 1))
    return (0, path.name, 0)


def select_backup(vibe_root, backup=None):
    """Wählt die jüngste oder eine ausdrücklich benannte Sicherung."""
    toolchain = Path(vibe_root)
    if not toolchain.is_dir():
        raise SetupError(f"Keine Installation unter {toolchain} gefunden.")
    candidates = sorted(
        (
            path
            for path in toolchain.iterdir()
            if path.is_dir()
            and path.name.startswith("backup-")
            and not path.name.startswith(UNINSTALL_BACKUP_PREFIX)
        ),
        key=_backup_sort_key,
    )
    if not candidates:
        raise SetupError(f"Keine Sicherung unter {toolchain} gefunden; nichts zurückgerollt.")
    if backup:
        chosen = Path(backup)
        if not chosen.is_absolute():
            chosen = toolchain / chosen
        try:
            chosen.resolve().relative_to(toolchain.resolve())
        except ValueError:
            raise SetupError(f"Sicherung liegt außerhalb der Installation: {backup}")
        if (
            not chosen.is_dir()
            or not chosen.name.startswith("backup-")
            or chosen.name.startswith(UNINSTALL_BACKUP_PREFIX)
        ):
            raise SetupError(f"Unbekannte Sicherung: {backup}")
        return chosen
    return candidates[-1]


def rollback(vibe_root, backup=None):
    """Stellt die jüngste oder eine benannte Sicherung wieder her."""
    toolchain = Path(vibe_root)
    chosen = select_backup(vibe_root, backup)
    report = _restore_backup(toolchain, chosen)
    report["backup"] = chosen.name
    return report


def uninstall(vibe_root, home=None, remove_launcher=False, timestamp=None):
    """Entfernt Programmdateien und Vorlagen; Laufzeitdaten und Projekte bleiben.

    Vorlagen werden vor dem Entfernen unter
    ``<Installationsort>/backup-uninstall-<Zeitstempel>/`` gesichert, damit auch
    persönlich angepasste Vorlagen erhalten bleiben.
    """
    vibe_root = Path(vibe_root)
    toolchain = vibe_root
    report = {"removed": [], "kept": [], "missing": False, "launchers": [], "backup": None}
    if not toolchain.is_dir():
        report["missing"] = True
        return report
    templates = toolchain / "templates"
    if templates.is_dir():
        stamp = timestamp or time.strftime("%Y%m%d-%H%M%S")
        backup_root = _next_backup_root(toolchain, f"uninstall-{stamp}")
        try:
            shutil.copytree(str(templates), str(backup_root / "templates"))
        except OSError as error:
            raise SetupError(
                f"Vorlagen konnten nicht gesichert werden; nichts entfernt: {error}"
            ) from error
        report["backup"] = str(backup_root)
    for name in PROGRAM_FILES:
        path = toolchain / "bin" / name
        if path.is_file() or path.is_symlink():
            path.unlink()
            report["removed"].append(f"bin/{name}")
    for name in WEB_FILES:
        path = toolchain / "bin" / "web" / name
        if path.is_file() or path.is_symlink():
            path.unlink()
            report["removed"].append(f"bin/web/{name}")
    web_dir = toolchain / "bin" / "web"
    if web_dir.is_dir():
        try:
            web_dir.rmdir()
            report["removed"].append("bin/web")
        except OSError:
            pass
    if templates.is_dir():
        shutil.rmtree(str(templates))
        report["removed"].append("templates")
    version = toolchain / VERSION_META
    if version.is_file():
        version.unlink()
        report["removed"].append(VERSION_META)
    if remove_launcher and home:
        launcher = Path(home) / ".local" / "bin" / "vibe"
        if launcher.is_symlink():
            try:
                target = launcher.resolve()
            except OSError:
                target = None
            if target == (toolchain / "bin" / "vibe").resolve():
                launcher.unlink()
                report["launchers"].append(str(launcher))
        command = vibe_root / "vibe.cmd"
        if command.is_file():
            command.unlink()
            report["launchers"].append(str(command))
    bin_dir = toolchain / "bin"
    if bin_dir.is_dir():
        try:
            bin_dir.rmdir()
            report["removed"].append("bin")
        except OSError:
            pass
    for child in sorted(toolchain.iterdir(), key=lambda item: item.name.lower()):
        report["kept"].append(child.name)
    return report


def running_installation(logs_dir, runner=None, which=None):
    """Nennt laufende Agentenläufe und Dashboard-/Server-Sitzungen dieser Installation.

    Ein Registereintrag in ``starting``/``running`` gilt nur dann als laufend,
    wenn seine tmux-Sitzung tatsächlich existiert. Sonst ist der Lauf verwaist
    und darf eine Aktualisierung nicht blockieren. Ohne prüfbare Sitzung
    (tmux fehlt oder Eintrag ohne Sitzungsangabe) bleibt die Sperre konservativ.

    Eine vorhandene, aber leere (oder nur aus Leerraum bestehende) ``runs.json``
    enthält nachweislich keine Läufe und sperrt wie eine fehlende Datei nicht.
    Nur nicht-leerer Inhalt, der nicht lesbar/auswertbar ist, bleibt ein
    Sperrgrund (``Laufzustand … ist nicht lesbar``).
    """
    reasons = []
    which = which or shutil.which
    tmux = which("tmux")
    runner = runner or subprocess.run

    def session_state(session, own_socket=False):
        """True/False, wenn tmux die Sitzung prüfen kann; sonst None.

        Agentenläufe liegen seit V-026 auf einem eigenen tmux-Server; der
        Socket-Name ist dort der Sitzungsname. Dashboard und opencode-Server
        bleiben auf dem Standard-Server.
        """
        if not tmux or not session:
            return None
        command = [tmux]
        if own_socket:
            command += ["-L", session]
        command += ["has-session", "-t", session]
        try:
            completed = runner(
                command,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        code = getattr(completed, "returncode", None)
        if code == 0:
            return True
        if code == 1:
            return False
        return None

    runs_path = Path(logs_dir) / "runs.json"
    data = None
    if runs_path.exists():
        # B4: Eine leere (oder nur-Leerraum-) runs.json enthält nachweislich
        # keine Läufe und sperrt wie eine fehlende Datei nicht. Nur Inhalt,
        # der nicht lesbar/auswertbar ist, bleibt ein Sperrgrund.
        try:
            text = runs_path.read_text(encoding="utf-8")
        except OSError:
            reasons.append(f"Laufzustand {runs_path} ist nicht lesbar")
        else:
            if text.strip():
                try:
                    data = json.loads(text)
                except ValueError:
                    reasons.append(f"Laufzustand {runs_path} ist nicht lesbar")
    if isinstance(data, dict):
        for record in data.get("runs", []):
            if not isinstance(record, dict):
                continue
            if record.get("state") not in LIVE_RUN_STATES:
                continue
            run_id = record.get("id", "?")
            session = str(record.get("session") or "")
            state = session_state(session, own_socket=True)
            if state is False:
                continue
            if state is None:
                reasons.append(
                    f"Agentenlauf {run_id} ist {record.get('state')}; "
                    f"tmux-Sitzung {session or '(ohne Angabe)'} nicht prüfbar"
                )
            else:
                reasons.append(f"Agentenlauf {run_id} ist {record.get('state')}")
    for session in ("vibe-ui", "vibe-ui-dev", "vibe-server", "vibe-server-dev"):
        if session_state(session):
            reasons.append(f"tmux-Sitzung {session} läuft")
    return reasons


def install_launcher(vibe_root, home, info, timestamp=None):
    """Legt den Startbefehl an; vorhandene Dateien werden gesichert, nie gelöscht."""
    vibe_root = Path(vibe_root)
    home = Path(home)
    timestamp = timestamp or time.strftime("%Y%m%d-%H%M%S")
    if info.get("os") == "windows":
        launcher = vibe_root / "vibe.cmd"
        content = (
            "@echo off\r\n"
            "setlocal\r\n"
            "py -3 \"%~dp0bin\\vibe\" %*\r\n"
        )
        backed_up = None
        existed = launcher.exists()
        if launcher.exists():
            existing = launcher.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
            if existing != content.replace("\r\n", "\n"):
                backup = launcher.with_name(f"vibe.cmd.bak-{timestamp}")
                counter = 1
                while backup.exists():
                    backup = launcher.with_name(f"vibe.cmd.bak-{timestamp}-{counter}")
                    counter += 1
                os.replace(str(launcher), str(backup))
                backed_up = str(backup)
        _write_text_atomic(launcher, content)
        return {"path": str(launcher), "backed_up": backed_up, "created": not existed}

    target = vibe_root / "bin" / "vibe"
    launcher = home / ".local" / "bin" / "vibe"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    backed_up = None
    if launcher.exists() or launcher.is_symlink():
        try:
            already_linked = launcher.is_symlink() and launcher.resolve() == target.resolve()
        except OSError:
            already_linked = False
        if already_linked:
            return {"path": str(launcher), "backed_up": None, "created": False}
        backup = launcher.with_name(f"vibe.bak-{timestamp}")
        counter = 1
        while backup.exists():
            backup = launcher.with_name(f"vibe.bak-{timestamp}-{counter}")
            counter += 1
        os.replace(str(launcher), str(backup))
        backed_up = str(backup)
    os.symlink(str(target), str(launcher))
    return {"path": str(launcher), "backed_up": backed_up, "created": True}


def register_projects(workspace, install):
    """Ergänzt fehlende .vibe/project.env im Workspace; Vorlagen kommen aus dem Installationsort."""
    vibe_root = Path(workspace)
    toolchain = Path(install)
    result = {"projects": [], "created": [], "warnings": []}
    if not vibe_root.is_dir():
        return result
    for child in sorted(vibe_root.iterdir(), key=lambda item: item.name.lower()):
        if child.name.startswith(("_", ".")) or not child.is_dir():
            continue
        if not (child / ".git").exists():
            continue
        entry = {"project": child.name, "type": None, "created": False}
        project_env = child / ".vibe" / "project.env"
        if project_env.exists():
            result["projects"].append(entry)
            continue
        project_type = "android" if (child / "gradlew").exists() else "generic"
        source = toolchain / "templates" / project_type / ".vibe" / "project.env"
        if not source.is_file():
            source = toolchain / "templates" / "generic" / ".vibe" / "project.env"
        if not source.is_file():
            result["warnings"].append(
                f"Vorlage für {child.name} fehlt; .vibe/project.env wurde nicht angelegt."
            )
            result["projects"].append(entry)
            continue
        project_env.parent.mkdir(parents=True, exist_ok=True)
        _copy_file(source, project_env)
        entry["type"] = project_type
        entry["created"] = True
        result["created"].append(child.name)
        result["projects"].append(entry)
    return result


def verify_installation(vibe_root):
    """Prüft die installierten Dateien und die Python-Version."""
    toolchain = Path(vibe_root)
    checks = []
    for name in PROGRAM_FILES:
        path = toolchain / "bin" / name
        checks.append({"label": f"Programm bin/{name}", "ok": path.is_file(), "hint": "Setup erneut ausführen"})
    for name in WEB_FILES:
        path = toolchain / "bin" / "web" / name
        checks.append({"label": f"Webdatei bin/web/{name}", "ok": path.is_file(), "hint": "Setup erneut ausführen"})
    for name in ("vibe", "vibe-run.sh"):
        path = toolchain / "bin" / name
        checks.append({"label": f"Ausführbar bin/{name}", "ok": path.is_file() and os.access(str(path), os.X_OK), "hint": "chmod +x setzen"})
    template = toolchain / "templates" / "generic" / ".vibe" / "project.env"
    checks.append({"label": "Vorlagen installiert", "ok": template.is_file(), "hint": "Setup erneut ausführen"})
    checks.append(
        {
            "label": "Versionskennung version.json",
            "ok": read_installed_version(vibe_root) is not None,
            "hint": "Setup --update ausführen",
        }
    )
    checks.append({"label": f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+", "ok": python_ok(), "hint": "Python aktualisieren"})
    return checks


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="setup-vibe.py",
        description="Interaktiver Setup für vibe (Linux, Container und Windows); Workspace, Installationsort und Logverzeichnis sind getrennt.",
    )
    try:
        version_text = (KIT / VERSION_FILE).read_text(encoding="utf-8").strip() or UNKNOWN_VERSION
    except OSError:
        version_text = UNKNOWN_VERSION
    parser.add_argument(
        "--version",
        action="version",
        version=f"vibe-Setup {version_text}",
        help="Version des Quellstands anzeigen",
    )
    parser.add_argument("--vibe", "--workspace", dest="vibe", metavar="PFAD",
                        help="Workspace (Projektordner, entspricht VIBE)")
    parser.add_argument("--install", metavar="PFAD",
                        help="Installationsort (Programme, Vorlagen, Einstellungen; Standard: <Workspace>/_toolchain)")
    parser.add_argument("--logs", metavar="PFAD",
                        help="Log- und Laufzeitverzeichnis (entspricht VIBE_RUNTIME; Standard: <Workspace>/_logs)")
    parser.add_argument("--source", metavar="VERZEICHNIS",
                        help="autorisiertes Quellverzeichnis für --update (Kit aus diesem Checkout)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--reuse", action="store_true", help="bestehende Installation wiederverwenden")
    mode.add_argument("--update", action="store_true", help="Programmdateien aktualisieren (mit Sicherung)")
    mode.add_argument("--rollback", action="store_true", help="letzte Sicherung wiederherstellen")
    mode.add_argument("--uninstall", action="store_true", help="Programmdateien entfernen; Nutzerdaten bleiben")
    parser.add_argument("--backup", metavar="NAME", help="Sicherung für --rollback (Standard: jüngste)")
    parser.add_argument("--force", action="store_true", help="Aktualisierung trotz laufendem Agentenlauf")
    parser.add_argument("--yes", "-y", action="store_true", help="ohne Rückfragen (Standardwerte verwenden)")
    parser.add_argument("--install-deps", action="store_true", help="fehlende Werkzeuge ohne Rückfrage installieren")
    parser.add_argument("--skip-deps", action="store_true", help="keine Werkzeuge installieren oder abfragen")
    parser.add_argument(
        "--dry-run",
        "--preview",
        dest="dry_run",
        action="store_true",
        help="Vorschau anzeigen, nichts schreiben oder ausführen",
    )
    parser.add_argument("--no-register", action="store_true", help="Projektordner nicht registrieren")
    parser.add_argument("--no-launcher", action="store_true", help="keinen Startbefehl anlegen")
    parser.add_argument(
        "--harness",
        choices=vibe_harness.harness_ids(),
        help="Harness für Agentenläufe (Standard: gespeicherte Auswahl, sonst opencode)",
    )
    return parser.parse_args(argv)


def main(argv=None, input_fn=None, output=print, which=None, runner=None,
         platform_info=None, home=None, kit=None, interactive=None,
         is_root=None, has_sudo=None, environ=None):
    """Führt den Setup aus und liefert 0 (fertig), 1 (Fehler) oder 2 (unvollständig).

    ``environ`` ist die einzige Quelle für Pfadauflösungen; ``None`` behält
    das Verhalten der Prozessumgebung. So kann ein Test den Setup mit einer
    bereinigten Umgebung und eigenen Temp-Pfaden aufrufen, ohne die laufende
    Installation zu berühren (B17).
    """
    options = parse_args(argv)
    environ = os.environ if environ is None else environ
    input_fn = input_fn or input
    which = which or shutil.which
    runner = runner or subprocess.run
    # Eine ausdrücklich benannte Quelle hat Vorrang vor dem übergebenen Kit.
    kit = Path(options.source) if options.source else (Path(kit) if kit else KIT)
    home = Path(home) if home else Path(
        environ.get("HOME") or os.path.expanduser("~")
    )
    info = platform_info or detect_platform(which=which)
    interactive = sys.stdin.isatty() if interactive is None else interactive
    is_root = os.geteuid() == 0 if is_root is None and hasattr(os, "geteuid") else bool(is_root)
    has_sudo = shutil.which("sudo") is not None if has_sudo is None else has_sudo
    timestamp = time.strftime("%Y%m%d-%H%M%S")

    if not interactive and not options.yes and not options.dry_run:
        output("FEHLER: Ohne Terminal ist kein interaktiver Setup möglich. Nutze --yes (optional mit --install-deps).")
        return 1

    output("vibe-Setup")
    output("Erkannt: " + info["label"])
    if info.get("container"):
        output("Umgebung: Container; Installation erfolgt im Container.")
    if info.get("wsl"):
        output("Umgebung: Windows-Subsystem für Linux (WSL).")
    if info.get("immutable") and not info.get("container"):
        output("Hinweis: Unveränderliches System; Systempakete werden nicht auf dem Host installiert.")

    try:
        if options.vibe:
            raw_workspace = options.vibe
        else:
            default_ws = default_workspace(info, home, environ=environ)
            if interactive:
                answer = input_fn(f"Workspace (Projektordner) [{default_ws}]: ").strip()
                raw_workspace = answer or str(default_ws)
            else:
                raw_workspace = str(default_ws)
        workspace = Path(validate_target(raw_workspace, kit, home))

        if options.install:
            raw_install = options.install
        else:
            default_inst = default_install(workspace, environ=environ)
            if interactive:
                answer = input_fn(
                    f"Installationsort (Programme, Vorlagen, Einstellungen) [{default_inst}]: "
                ).strip()
                raw_install = answer or str(default_inst)
            else:
                raw_install = str(default_inst)
        target = Path(validate_install(raw_install, workspace, kit, home))

        if options.logs:
            raw_logs = options.logs
        else:
            default_log = default_logs(workspace, environ=environ)
            if interactive:
                answer = input_fn(f"Logverzeichnis (Logs, Laufzeitzustand) [{default_log}]: ").strip()
                raw_logs = answer or str(default_log)
            else:
                raw_logs = str(default_log)
        logs_dir = Path(validate_logs(raw_logs, workspace, target, kit, home))
    except SetupError as error:
        output("FEHLER: " + str(error))
        return 1
    output(f"Workspace:        {workspace}")
    output(f"Installationsort: {target}")
    output(f"Logverzeichnis:   {logs_dir}")

    # B17: Ein --update darf die laufende Instanz nicht verändern. Das gilt
    # auch für ein ausdrückliches --install, wenn es auf dieselbe Installation
    # zeigt (VIBE_INSTALL aus environ/Konfiguration). Nur Ziele außerhalb der
    # laufenden Installation sind ohne --source erlaubt. Die Vorschau bleibt
    # gefahrlos möglich und erklärt die Autorisierung.
    # Nur der produktive Pfad aus der übergebenen Umgebung markiert die
    # laufende Installation; ein zuvor in der Testkonfiguration gespeicherter
    # Pfad ist gerade kein Produktivpfad.
    running_install = environ.get("VIBE_INSTALL")
    implicit_running = not options.install and detect_existing(target)["toolchain"]
    explicit_running = bool(running_install) and (
        Path(target).resolve(strict=False)
        == Path(os.path.abspath(os.path.expanduser(str(running_install)))).resolve(strict=False)
    )
    if options.update and not options.source and (implicit_running or explicit_running):
        guard = (
            "Schutz der laufenden Instanz: Für --update auf dieses "
            "Installationsziel ist eine autorisierte Quelle nötig. "
            "--source <verzeichnis> angeben oder mit --install ein eigenes "
            "Ziel verwenden."
        )
        if not options.dry_run:
            output("FEHLER: " + guard)
            return 1
        output("(dry-run) " + guard)

    if options.backup and not options.rollback:
        output("FEHLER: --backup ist nur zusammen mit --rollback zulässig.")
        return 1
    if options.rollback:
        try:
            chosen = select_backup(target, options.backup)
        except SetupError as error:
            output("FEHLER: " + str(error))
            return 1
        if options.dry_run:
            output(f"(dry-run) Rollback aus {chosen.name}; es wird nichts geändert.")
            return 0
        if not options.force:
            reasons = running_installation(logs_dir, runner=runner, which=which)
            if reasons:
                output("FEHLER: Die Installation wird gerade verwendet; nichts zurückgerollt.")
                for reason in reasons:
                    output("  - " + reason)
                output("Beende die Läufe/Sitzungen oder nutze --force für einen bewussten Rollback.")
                return 1
        try:
            report = rollback(target, options.backup)
        except (SetupError, OSError) as error:
            output("FEHLER: Rollback fehlgeschlagen: " + str(error))
            return 1
        output(f"Rollback: {report['backup']}")
        output(f"Wiederhergestellt: {len(report['restored'])} Datei(en)")
        if report["removed"]:
            output(f"Entfernt (neu seit dem Update): {len(report['removed'])} Datei(en)")
        return 0
    if options.uninstall:
        if options.dry_run:
            toolchain = target
            removable = [f"bin/{name}" for name in PROGRAM_FILES if (toolchain / "bin" / name).exists()]
            if (toolchain / "templates").is_dir():
                removable.append("templates")
            if (toolchain / VERSION_META).is_file():
                removable.append(VERSION_META)
            output(f"(dry-run) Uninstall würde {len(removable)} Datei(en)/Bereich(e) entfernen:")
            for relative in removable:
                output("  - " + relative)
            if (toolchain / "templates").is_dir():
                output("(dry-run) Angepasste Vorlagen würden vorher gesichert.")
            output("(dry-run) Laufzeitdaten, Sicherungen und Projekte bleiben erhalten.")
            return 0
        if not options.yes and not interactive:
            output("FEHLER: Uninstall löscht Programmdateien; ohne Terminal ist --yes erforderlich.")
            return 1
        if interactive and not options.yes:
            answer = input_fn(
                "Programmdateien entfernen? Laufzeitdaten und Projekte bleiben erhalten. [j/N]: "
            ).strip().lower()
            if not answer.startswith("j"):
                output("Uninstall abgebrochen; nichts geändert.")
                return 1
        if not options.force:
            reasons = running_installation(logs_dir, runner=runner, which=which)
            if reasons:
                output("FEHLER: Die Installation wird gerade verwendet; nichts entfernt.")
                for reason in reasons:
                    output("  - " + reason)
                output("Beende die Läufe/Sitzungen oder nutze --force für ein bewusstes Entfernen.")
                return 1
        try:
            report = uninstall(target, home=home, remove_launcher=not options.no_launcher)
        except (SetupError, OSError) as error:
            output("FEHLER: Uninstall fehlgeschlagen: " + str(error))
            return 1
        if report["missing"]:
            output("Keine Installation gefunden; nichts entfernt.")
            return 0
        output(f"Uninstall: {len(report['removed'])} Datei(en)/Bereich(e) entfernt.")
        if report["backup"]:
            output("Vorlagen gesichert: " + report["backup"])
        for launcher in report["launchers"]:
            output("Startbefehl entfernt: " + launcher)
        if report["kept"]:
            output("Erhalten: " + ", ".join(report["kept"]))
        output("Projekte und Laufzeitdaten wurden nicht verändert.")
        return 0

    # Harness-Auswahl (AP04): Eine gespeicherte Auswahl bleibt bei Updates
    # erhalten; --harness setzt sie bewusst neu. Ohne Datei und ohne Angabe
    # bleibt opencode der Standard, damit bestehende Installationen ihr
    # Verhalten nicht ändern.
    state_dir = target
    selection_file = Path(vibe_harness.selection_path(state_dir))
    stored_harness = None
    if selection_file.exists():
        try:
            stored_harness = vibe_harness.read_selection(state_dir)
        except vibe_harness.HarnessError as error:
            output("FEHLER: " + str(error))
            return 1
    if options.harness:
        chosen_harness = options.harness
    elif stored_harness:
        chosen_harness = stored_harness
    elif interactive and not options.yes:
        answer = input_fn(
            f"Harness für Agentenläufe [opencode/pi] [{vibe_harness.DEFAULT_HARNESS}]: "
        ).strip()
        try:
            chosen_harness = vibe_harness.definition(answer or vibe_harness.DEFAULT_HARNESS)["id"]
        except vibe_harness.HarnessError as error:
            output("FEHLER: " + str(error))
            return 1
    else:
        chosen_harness = vibe_harness.DEFAULT_HARNESS
    output("Harness: " + chosen_harness)

    existing = detect_existing(target)
    if options.reuse:
        mode = "reuse"
    elif options.update:
        mode = "update"
    elif existing["toolchain"]:
        if interactive:
            runtime = ", ".join(existing["runtime"]) or "-"
            output(
                "Bestehende Installation gefunden: "
                f"{len(existing['programs'])}/{len(PROGRAM_FILES)} Programme, Laufzeitdaten: {runtime}"
            )
            answer = input_fn(
                "Bestehende Installation [w]iederverwenden, [a]ktualisieren oder [q] abbrechen? [w]: "
            ).strip().lower()
            if answer in ("q", "abbrechen", "quit"):
                output("Setup abgebrochen; nichts geändert.")
                return 1
            if answer in ("a", "aktualisieren", "update"):
                mode = "update"
            elif answer in ("", "w", "wiederverwenden", "reuse"):
                mode = "reuse"
            else:
                output("Unbekannte Auswahl; Setup abgebrochen.")
                return 1
        else:
            mode = "reuse"
    else:
        mode = "update"

    report = dependency_report(info, which, harness=chosen_harness)
    missing = [item for item in report if item["required"] and not item["present"]]
    output("Werkzeuge:")
    for item in report:
        status = "OK   " if item["present"] else "FEHLT"
        output(f"  {status} {item['name']:<8} {item['why']}")
        if not item["present"] and item["hint"]:
            output("        -> " + item["hint"])
    installable = [item["name"] for item in missing if item["installable"]]

    if options.dry_run:
        try:
            plan = build_install_plan(
                kit, target, mode=mode, timestamp=timestamp, runner=runner
            )
        except SetupError as error:
            output("FEHLER: " + str(error))
            return 1
        harness_plan = vibe_harness.setup_plan(chosen_harness)
        output("Harness-Hinweis: " + harness_plan["hint"])
        output("Harness offiziell: " + harness_plan["official"])
        if harness_plan["install_command"]:
            output("(dry-run) Harness einrichten: " + " ".join(harness_plan["install_command"]))
        for line in describe_plan(plan):
            output(line)
        prefix = privilege_prefix(info, is_root, has_sudo)
        for command in install_commands(info, installable, prefix):
            output("(dry-run) " + " ".join(command))
        output(f"(dry-run) Konfiguration {vibe_paths.default_config_path(environ)}: profiles.prod.workspace={workspace}, install={target}, runtime={logs_dir}")
        output(f"(dry-run) Ziel: {target}; Workspace: {workspace}; Logs: {logs_dir}; Modus: {mode}; es wird nichts geändert.")
        return 0

    if mode == "update" and existing["toolchain"] and not options.force:
        reasons = running_installation(logs_dir, runner=runner, which=which)
        if reasons:
            output("FEHLER: Die Installation wird gerade verwendet; nichts geändert.")
            for reason in reasons:
                output("  - " + reason)
            output("Beende die Läufe/Sitzungen oder nutze --force für eine bewusste Aktualisierung.")
            return 1

    dependency_failed = False
    if missing and installable and not options.skip_deps:
        do_install = bool(options.install_deps)
        if interactive and not options.install_deps:
            answer = input_fn("Fehlende Abhängigkeiten jetzt installieren? [j/N]: ").strip().lower()
            do_install = answer.startswith("j")
        if do_install:
            prefix = privilege_prefix(info, is_root, has_sudo)
            commands = install_commands(info, installable, prefix)
            if not commands:
                output("Keine Installationsrechte (root/sudo) für den Paketmanager; bitte die Hinweise oben befolgen.")
            for command in commands:
                output("Führe aus: " + " ".join(command))
                try:
                    completed = runner(command, capture_output=True, text=True, timeout=1800)
                except subprocess.TimeoutExpired:
                    output(f"FEHLER: {command[0]} hat nach 30 Minuten nicht geendet.")
                    dependency_failed = True
                    continue
                except OSError as error:
                    output(f"FEHLER beim Start von {command[0]}: {error}")
                    dependency_failed = True
                    continue
                if completed.returncode != 0:
                    detail = (completed.stderr or completed.stdout or "").strip().splitlines()
                    output(
                        f"FEHLER: {command[0]} endete mit Code {completed.returncode}"
                        + (f": {detail[0]}" if detail else "")
                    )
                    dependency_failed = True

    files = None
    launcher = None
    try:
        files = install_program_files(kit, target, mode=mode, timestamp=timestamp, runner=runner)
        if not options.no_launcher:
            launcher = install_launcher(target, home, info, timestamp=timestamp)
        registration = None
        if not options.no_register:
            if interactive and not options.yes:
                answer = input_fn("Vorhandene Projektordner registrieren? [J/n]: ").strip().lower()
                if not answer.startswith("n"):
                    registration = register_projects(workspace, target)
            else:
                registration = register_projects(workspace, target)
    except (SetupError, OSError) as error:
        if files is not None:
            try:
                state = _undo_install(target, files, launcher=launcher)
            except (SetupError, OSError) as undo_error:
                output("FEHLER: Installation fehlgeschlagen: " + str(error))
                output("FEHLER: Wiederherstellung fehlgeschlagen: " + str(undo_error))
                return 1
            if state == "restored":
                output(
                    "FEHLER: Installation abgebrochen, vorheriger Stand wiederhergestellt: "
                    + str(error)
                )
            else:
                output("FEHLER: Installation abgebrochen; nichts geändert: " + str(error))
            return 1
        output("FEHLER: Installation fehlgeschlagen: " + str(error))
        return 1

    # Eine bestehende Auswahl wird beim Update nicht neu geschrieben; ohne
    # Datei oder mit --harness wird die getroffene Wahl gespeichert.
    if options.harness or not selection_file.exists():
        try:
            vibe_harness.write_selection(state_dir, chosen_harness)
        except (vibe_harness.HarnessError, OSError) as error:
            output("FEHLER: Harness-Auswahl konnte nicht gespeichert werden: " + str(error))
            return 1

    try:
        for directory in (workspace, logs_dir):
            directory.mkdir(parents=True, exist_ok=True)
        saved = save_paths_config(workspace, target, logs_dir, timestamp=timestamp, environ=environ)
    except (SetupError, OSError) as error:
        output("FEHLER: " + str(error))
        output(
            f"Setze stattdessen VIBE={workspace}, VIBE_INSTALL={target} und "
            f"VIBE_RUNTIME={logs_dir} in deiner Shell-Umgebung."
        )
        return 2
    if saved["changed"]:
        output(f"Konfiguration: {saved['path']} (profiles.prod: workspace/install/runtime)")
        if saved["backup"]:
            output("Vorherige Konfiguration gesichert: " + saved["backup"])
    for variable, chosen in (("VIBE", workspace), ("VIBE_INSTALL", target), ("VIBE_RUNTIME", logs_dir)):
        value = environ.get(variable)
        if value and os.path.abspath(os.path.expanduser(value)) != str(chosen):
            output(f"Hinweis: {variable}={value} überschreibt die Konfiguration; Variable anpassen oder entfernen.")
    for warning in files["warnings"]:
        output("Hinweis: " + warning)
    output(f"Installation: {len(files['copied'])} Datei(en) kopiert, {len(files['skipped'])} unverändert.")
    version = files["version"]["to"]
    version_line = f"Version: {version['version']}"
    if version.get("commit"):
        version_line += f" (Commit {version['commit']})"
    output(version_line)
    if files["backed_up"]:
        output(f"Sicherung: {files['backup']} ({len(files['backed_up'])} Datei(en))")
    if launcher:
        output("Startbefehl: " + launcher["path"])
        if launcher.get("backed_up"):
            output("Vorheriger Startbefehl gesichert: " + launcher["backed_up"])
    if registration is not None:
        output(f"Projekte registriert: {len(registration['projects'])}" + (
            f" (neu: {', '.join(registration['created'])})" if registration["created"] else ""
        ))
        for warning in registration["warnings"]:
            output("Hinweis: " + warning)

    checks = verify_installation(target)
    for check in checks:
        if not check["ok"]:
            output(f"Prüfung fehlgeschlagen: {check['label']} -> {check['hint']}")

    report = dependency_report(info, which, harness=chosen_harness)
    remaining = [item for item in report if item["required"] and not item["present"]]
    # --skip-deps nimmt die Werkzeugprüfung aus dem Lauf heraus; fehlende
    # Werkzeuge werden weiterhin gemeldet, sollen den Setup aber nicht als
    # unvollständig markieren (B17: isolierte Läufe schalten die Prüfung ab).
    if (remaining or dependency_failed) and not options.skip_deps:
        output("Unvollständig: folgende Werkzeuge fehlen noch: " + ", ".join(item["name"] for item in remaining))
        output("Bitte die Hinweise oben befolgen und den Setup erneut ausführen.")
        return 2
    if remaining and options.skip_deps:
        output("Hinweis: Werkzeuge übersprungen (--skip-deps): " + ", ".join(item["name"] for item in remaining))
    output("Fertig. Nächste Schritte: vibe list | vibe doctor | vibe ui")
    if info.get("os") == "windows":
        output(
            "Windows-Hinweis: Agentenläufe benötigen tmux und flock. "
            "Nutze dafür WSL2 oder Docker und führe den Setup dort erneut aus."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
