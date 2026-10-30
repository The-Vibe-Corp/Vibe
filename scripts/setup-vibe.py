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
"""
import argparse
import os
import platform as _platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
MIN_PYTHON = (3, 8)
PROGRAM_FILES = ("vibe", "vibe-run.sh", "vibe-web.py", "vibe_mcp.py", "vibe_opencode.py", "vibe_models.py", "vibe_sandbox.py", "fritz-reconnect.py")
RUNTIME_FILES = ("vibe.json", "models.json", "profiles.json", "fritz.json")
OFFICIAL_OPENCODE = "https://opencode.ai/docs/"
OPENCODE_NPM_PACKAGE = "opencode-ai"
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
        "why": "Agentenläufe und Modellzugriff",
        "required": True,
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


def dependency_report(info, which=None):
    """Liefert je Werkzeug Präsenz, Installierbarkeit und konkreten Hinweis."""
    which = which or shutil.which
    result = []
    for dependency in DEPENDENCIES:
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
            elif name == "opencode":
                hint = f"Bitte offiziell installieren: {OFFICIAL_OPENCODE} (kein automatisches Netzskript)."
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
    return commands


def default_target(info, home):
    """Standard-Zielordner: vorhandenes VIBE oder ~/VibeCode."""
    configured = os.environ.get("VIBE")
    if configured:
        return Path(os.path.expanduser(configured))
    return Path(home) / "VibeCode"


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
    toolchain = Path(vibe_root) / "_toolchain"
    programs = [name for name in PROGRAM_FILES if (toolchain / "bin" / name).is_file()]
    runtime = [name for name in RUNTIME_FILES if (toolchain / name).is_file()]
    return {
        "toolchain": toolchain.is_dir(),
        "programs": programs,
        "runtime": runtime,
        "complete": len(programs) == len(PROGRAM_FILES),
    }


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


def install_program_files(kit, vibe_root, mode="update", timestamp=None):
    """Kopiert Programmdateien und Vorlagen; Laufzeitdaten bleiben unangetastet."""
    if mode not in ("reuse", "update"):
        raise SetupError(f"Unbekannter Modus: {mode}")
    kit = Path(kit)
    vibe_root = Path(vibe_root)
    source_program = kit / "bin" / "vibe"
    if not source_program.is_file():
        raise SetupError(f"Unvollständiges Quellverzeichnis: {source_program} fehlt")
    timestamp = timestamp or time.strftime("%Y%m%d-%H%M%S")
    toolchain = vibe_root / "_toolchain"
    result = {"copied": [], "skipped": [], "backed_up": [], "warnings": [], "backup": None}
    backup_root = None

    def backup(relative, destination):
        nonlocal backup_root
        if backup_root is None:
            backup_root = _next_backup_root(toolchain, timestamp)
        result["backed_up"].append(_backup_file(destination, backup_root, relative))
        result["backup"] = str(backup_root)

    for name in PROGRAM_FILES:
        source = kit / "bin" / name
        if not source.is_file():
            raise SetupError(f"Unvollständiges Quellverzeichnis: {source} fehlt")
        relative = f"bin/{name}"
        destination = toolchain / "bin" / name
        if destination.exists():
            if mode == "reuse":
                result["skipped"].append(relative)
                continue
            if destination.is_file() and destination.read_bytes() == source.read_bytes():
                result["skipped"].append(relative)
                continue
            backup(relative, destination)
        _copy_file(source, destination)
        _make_executable(destination)
        result["copied"].append(relative)

    templates = kit / "templates"
    if templates.is_dir():
        for source in sorted(templates.rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(kit).as_posix()
            destination = toolchain / relative
            if destination.exists():
                if mode == "reuse":
                    result["skipped"].append(relative)
                    continue
                if destination.is_file() and destination.read_bytes() == source.read_bytes():
                    result["skipped"].append(relative)
                    continue
                backup(relative, destination)
            _copy_file(source, destination)
            result["copied"].append(relative)

    catalog = kit / "data" / "models.json"
    destination_catalog = toolchain / "models.json"
    if not catalog.is_file():
        result["warnings"].append(
            "data/models.json fehlt im Quellverzeichnis; der Modellkatalog wird nicht installiert."
        )
    elif destination_catalog.exists():
        result["skipped"].append("models.json")
    else:
        _copy_file(catalog, destination_catalog)
        result["copied"].append("models.json")
    return result


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
            "py -3 \"%~dp0_toolchain\\bin\\vibe\" %*\r\n"
        )
        backed_up = None
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
        return {"path": str(launcher), "backed_up": backed_up}

    target = vibe_root / "_toolchain" / "bin" / "vibe"
    launcher = home / ".local" / "bin" / "vibe"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    backed_up = None
    if launcher.exists() or launcher.is_symlink():
        try:
            already_linked = launcher.is_symlink() and launcher.resolve() == target.resolve()
        except OSError:
            already_linked = False
        if already_linked:
            return {"path": str(launcher), "backed_up": None}
        backup = launcher.with_name(f"vibe.bak-{timestamp}")
        counter = 1
        while backup.exists():
            backup = launcher.with_name(f"vibe.bak-{timestamp}-{counter}")
            counter += 1
        os.replace(str(launcher), str(backup))
        backed_up = str(backup)
    os.symlink(str(target), str(launcher))
    return {"path": str(launcher), "backed_up": backed_up}


def register_projects(vibe_root):
    """Ergänzt fehlende .vibe/project.env; vorhandene Konfigurationen bleiben."""
    vibe_root = Path(vibe_root)
    toolchain = vibe_root / "_toolchain"
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
    toolchain = Path(vibe_root) / "_toolchain"
    checks = []
    for name in PROGRAM_FILES:
        path = toolchain / "bin" / name
        checks.append({"label": f"Programm bin/{name}", "ok": path.is_file(), "hint": "Setup erneut ausführen"})
    for name in ("vibe", "vibe-run.sh"):
        path = toolchain / "bin" / name
        checks.append({"label": f"Ausführbar bin/{name}", "ok": path.is_file() and os.access(str(path), os.X_OK), "hint": "chmod +x setzen"})
    template = toolchain / "templates" / "generic" / ".vibe" / "project.env"
    checks.append({"label": "Vorlagen installiert", "ok": template.is_file(), "hint": "Setup erneut ausführen"})
    checks.append({"label": f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+", "ok": python_ok(), "hint": "Python aktualisieren"})
    return checks


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="setup-vibe.py",
        description="Interaktiver Setup für vibe (Linux, Container und Windows).",
    )
    parser.add_argument("--vibe", metavar="PFAD", help="Zielordner für die Installation")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--reuse", action="store_true", help="bestehende Installation wiederverwenden")
    mode.add_argument("--update", action="store_true", help="Programmdateien aktualisieren (mit Sicherung)")
    parser.add_argument("--yes", "-y", action="store_true", help="ohne Rückfragen (Standardwerte verwenden)")
    parser.add_argument("--install-deps", action="store_true", help="fehlende Werkzeuge ohne Rückfrage installieren")
    parser.add_argument("--skip-deps", action="store_true", help="keine Werkzeuge installieren oder abfragen")
    parser.add_argument("--dry-run", action="store_true", help="nur anzeigen, nichts schreiben oder ausführen")
    parser.add_argument("--no-register", action="store_true", help="Projektordner nicht registrieren")
    parser.add_argument("--no-launcher", action="store_true", help="keinen Startbefehl anlegen")
    return parser.parse_args(argv)


def main(argv=None, input_fn=None, output=print, which=None, runner=None,
         platform_info=None, home=None, kit=None, interactive=None,
         is_root=None, has_sudo=None):
    """Führt den Setup aus und liefert 0 (fertig), 1 (Fehler) oder 2 (unvollständig)."""
    options = parse_args(argv)
    input_fn = input_fn or input
    which = which or shutil.which
    runner = runner or subprocess.run
    kit = Path(kit) if kit else KIT
    home = Path(home) if home else Path(os.path.expanduser("~"))
    info = platform_info or detect_platform(which=which)
    interactive = sys.stdin.isatty() if interactive is None else interactive
    is_root = os.geteuid() == 0 if is_root is None and hasattr(os, "geteuid") else bool(is_root)
    has_sudo = shutil.which("sudo") is not None if has_sudo is None else has_sudo
    timestamp = time.strftime("%Y%m%d-%H%M%S")

    if not interactive and not options.yes:
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

    if options.vibe:
        raw_target = options.vibe
    else:
        default = default_target(info, home)
        if interactive:
            answer = input_fn(f"Zielordner für vibe [{default}]: ").strip()
            raw_target = answer or str(default)
        else:
            raw_target = str(default)
    try:
        target = Path(validate_target(raw_target, kit, home))
    except SetupError as error:
        output("FEHLER: " + str(error))
        return 1

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

    report = dependency_report(info, which)
    missing = [item for item in report if item["required"] and not item["present"]]
    output("Werkzeuge:")
    for item in report:
        status = "OK   " if item["present"] else "FEHLT"
        output(f"  {status} {item['name']:<8} {item['why']}")
        if not item["present"] and item["hint"]:
            output("        -> " + item["hint"])
    installable = [item["name"] for item in missing if item["installable"]]

    if options.dry_run:
        prefix = privilege_prefix(info, is_root, has_sudo)
        for command in install_commands(info, installable, prefix):
            output("(dry-run) " + " ".join(command))
        output(f"(dry-run) Ziel: {target}; Modus: {mode}; es wird nichts geändert.")
        return 0

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

    try:
        files = install_program_files(kit, target, mode=mode, timestamp=timestamp)
        launcher = None
        if not options.no_launcher:
            launcher = install_launcher(target, home, info, timestamp=timestamp)
        registration = None
        if not options.no_register:
            if interactive and not options.yes:
                answer = input_fn("Vorhandene Projektordner registrieren? [J/n]: ").strip().lower()
                if not answer.startswith("n"):
                    registration = register_projects(target)
            else:
                registration = register_projects(target)
    except (SetupError, OSError) as error:
        output("FEHLER: Installation fehlgeschlagen: " + str(error))
        return 1

    for warning in files["warnings"]:
        output("Hinweis: " + warning)
    output(f"Installation: {len(files['copied'])} Datei(en) kopiert, {len(files['skipped'])} unverändert.")
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

    report = dependency_report(info, which)
    remaining = [item for item in report if item["required"] and not item["present"]]
    if remaining or dependency_failed:
        output("Unvollständig: folgende Werkzeuge fehlen noch: " + ", ".join(item["name"] for item in remaining))
        output("Bitte die Hinweise oben befolgen und den Setup erneut ausführen.")
        return 2
    output("Fertig. Nächste Schritte: vibe list | vibe doctor | vibe ui")
    if info.get("os") == "windows":
        output(
            "Windows-Hinweis: Agentenläufe benötigen tmux und flock. "
            "Nutze dafür WSL2 oder Docker und führe den Setup dort erneut aus."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
