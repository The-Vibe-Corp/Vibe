#!/usr/bin/env python3
"""Installiert oder entfernt den vibe-Startmenüeintrag (V-017).

Aufruf:
    python3 scripts/vibe-desktop.py install [--dry-run]
    python3 scripts/vibe-desktop.py uninstall [--dry-run]
    python3 scripts/vibe-desktop.py status

Der Installer arbeitet ausschließlich benutzerbezogen unter
``$XDG_DATA_HOME`` (standardmäßig ``~/.local/share``). Er benötigt keine
Root-Rechte, startet vibe nicht und verändert weder Projekte noch
Laufzeitdaten oder persönliche Einstellungen.

Installiert werden:

* ``vibe/vibe_starter.py`` und ``vibe/vibe_paths.py`` — der Host-Starter,
* ``icons/hicolor/scalable/apps/vibe.svg`` — das Symbol,
* ``applications/vibe.desktop`` — der Menüeintrag mit einer Aktion zum
  Beenden des Dashboards,
* ``vibe/install-manifest.json`` — Prüfsummen der verwalteten Dateien.

Der Starter liest Pfade, Ports und Container zur Laufzeit aus
``~/.config/vibe/config.json`` beziehungsweise den ``VIBE_*``-Variablen. Der
Menüeintrag bleibt dadurch auch bei benutzerdefinierten Pfaden konsistent.
Ein vorhandener fremder Menüeintrag wird vor dem Ersetzen gesichert. Der
Uninstall entfernt nur Dateien, deren Prüfsumme noch dem Manifest entspricht;
geänderte Dateien und alle Nutzerdaten bleiben erhalten.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

MARKER = "X-Vibe-Managed=true"
APP_NAME = "vibe"
DESKTOP_NAME = "vibe.desktop"
ICON_NAME = "vibe.svg"
STARTER_NAME = "vibe_starter.py"
PATHS_NAME = "vibe_paths.py"
MANIFEST_NAME = "install-manifest.json"
MANAGED_BY = "vibe V-017"


class DesktopError(RuntimeError):
    """Verständlicher Fehler bei Installation oder Entfernung."""


def data_home(home=None, environ=None):
    """XDG-Datenverzeichnis des Nutzers; legt nichts an."""
    environ = dict(os.environ if environ is None else environ)
    value = environ.get("XDG_DATA_HOME")
    if value:
        return os.path.abspath(os.path.expanduser(value))
    home = home or environ.get("HOME") or os.path.expanduser("~")
    return os.path.join(os.path.abspath(os.path.expanduser(str(home))), ".local", "share")


def _targets_for_base(base):
    """Zielpfade je Datenverzeichnis; einzige Definition für alle Aufrufer."""
    base = Path(base)
    return {
        "base": base / APP_NAME,
        "starter": base / APP_NAME / STARTER_NAME,
        "paths": base / APP_NAME / PATHS_NAME,
        "manifest": base / APP_NAME / MANIFEST_NAME,
        "icon": base / "icons" / "hicolor" / "scalable" / "apps" / ICON_NAME,
        "desktop": base / "applications" / DESKTOP_NAME,
    }


def _targets(home=None, environ=None):
    return _targets_for_base(data_home(home, environ))


def desktop_quote(value):
    """Quotet ein Argument für das ``Exec``-Feld einer Desktopdatei.

    Die Desktop-Entry-Spezifikation verlangt doppelte Anführungszeichen für
    Argumente mit Leerraum sowie Escapes für Anführungszeichen, Backslash,
    Dollarzeichen und Backtick. Feldcodes (Prozentzeichen) werden verdoppelt.
    """
    text = str(value)
    if not text or any(ord(character) < 32 for character in text):
        raise DesktopError(f"Ungültiger Wert für die Desktopdatei: {value!r}")
    text = text.replace("%", "%%")
    reserved = set(' \t"\'\\<>~|&;$*?#()`')
    if not any(character in text for character in reserved):
        return text
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
    )
    return '"' + escaped + '"'


def _exec_line(starter, action):
    parts = ["/usr/bin/env", "python3", str(starter), action]
    return " ".join(desktop_quote(part) for part in parts)


def desktop_entry(starter, icon):
    """Erzeugt den vollständigen Inhalt der Desktopdatei."""
    icon_text = str(icon)
    if any(ord(character) < 32 for character in icon_text):
        raise DesktopError(f"Ungültiger Symbolpfad: {icon!r}")
    return "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            "Version=1.5",
            "Name=vibe",
            "GenericName=Vibe-Coding-Zentrale",
            "Comment=Projekte, Agenten und Prüfungen im lokalen Dashboard",
            "Exec=" + _exec_line(starter, "start"),
            "Icon=" + icon_text,
            "Terminal=false",
            "Categories=Development;",
            "Keywords=vibe;opencode;agent;",
            "StartupNotify=false",
            "Actions=stop;",
            MARKER,
            "",
            "[Desktop Action stop]",
            "Name=Dashboard beenden",
            "Exec=" + _exec_line(starter, "stop"),
            "",
        ]
    )


def _write(path, content, mode=0o644):
    """Schreibt eine Datei atomar, damit kein halber Menüeintrag entsteht."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=str(target.parent), prefix=".vibe-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        try:
            os.chmod(temporary, mode)
        except OSError:
            pass
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return target


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_manifest(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        return None
    return data


def _managed(path, manifest):
    """True, wenn die Datei unverändert aus diesem Manifest stammt."""
    if not manifest:
        return False
    entry = manifest.get("files", {}).get(str(path))
    if not isinstance(entry, dict):
        return False
    try:
        return entry.get("sha256") == _sha256(path)
    except OSError:
        return False


def _backup(path, timestamp):
    """Sichert eine fremde Datei kollisionsfrei; gibt den Sicherungspfad zurück."""
    target = Path(path)
    base = target.with_name(target.name + ".bak-" + timestamp)
    candidate = base
    counter = 1
    while candidate.exists():
        candidate = base.with_name(base.name + "-" + str(counter))
        counter += 1
    shutil.copy2(str(target), str(candidate))
    return candidate


def _sources(starter_source=None, paths_source=None, icon_source=None):
    here = Path(__file__).resolve().parent
    starter = Path(starter_source) if starter_source else here / STARTER_NAME
    if paths_source:
        paths = Path(paths_source)
    elif (here / PATHS_NAME).is_file():
        paths = here / PATHS_NAME
    else:
        paths = here.parent / "bin" / PATHS_NAME
    icon = Path(icon_source) if icon_source else here / ICON_NAME
    for label, source in (
        ("Starter", starter),
        ("Pfadmodul", paths),
        ("Symbol", icon),
    ):
        if not source.is_file():
            raise DesktopError(f"{label} {source} wurde nicht gefunden.")
    return starter, paths, icon


def install(home=None, data_home_path=None, starter_source=None, paths_source=None,
            icon_source=None, dry_run=False, environ=None):
    """Installiert Starter, Symbol und Menüeintrag; liefert den Bericht."""
    environ = dict(os.environ if environ is None else environ)
    targets = _targets(home, environ)
    if data_home_path:
        targets = _targets_for_base(data_home_path)
    starter, paths, icon = _sources(starter_source, paths_source, icon_source)
    previous = _read_manifest(targets["manifest"])
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    payload = [
        (targets["starter"], starter.read_text(encoding="utf-8"), 0o755),
        (targets["paths"], paths.read_text(encoding="utf-8"), 0o644),
        (targets["icon"], icon.read_text(encoding="utf-8"), 0o644),
        (targets["desktop"], desktop_entry(targets["starter"], targets["icon"]), 0o644),
    ]
    backups = []
    for target, _, _ in payload:
        if Path(target).exists() and not _managed(target, previous):
            backups.append((str(target), str(_backup(target, timestamp))))
    report = {
        "dry_run": bool(dry_run),
        "files": [str(target) for target, _, _ in payload],
        "backups": backups,
        "manifest": str(targets["manifest"]),
    }
    if dry_run:
        return report
    for target, content, mode in payload:
        _write(target, content, mode=mode)
    manifest = {
        "version": 1,
        "managed_by": MANAGED_BY,
        "installed_at": timestamp,
        "files": {
            str(target): {"sha256": _sha256(target), "mode": f"{mode:04o}"}
            for target, _, mode in payload
        },
    }
    _write(targets["manifest"], json.dumps(manifest, indent=1) + "\n", mode=0o644)
    report["installed"] = True
    return report


def uninstall(home=None, data_home_path=None, dry_run=False, environ=None):
    """Entfernt ausschließlich unveränderte, von vibe verwaltete Dateien."""
    environ = dict(os.environ if environ is None else environ)
    targets = _targets(home, environ)
    if data_home_path:
        targets = _targets_for_base(data_home_path)
    manifest = _read_manifest(targets["manifest"])
    report = {"installed": bool(manifest), "dry_run": bool(dry_run),
              "removed": [], "kept": [], "missing": []}
    if not manifest:
        return report
    for path_text, entry in list(manifest.get("files", {}).items()):
        path = Path(path_text)
        if not path.exists():
            report["missing"].append(str(path))
            continue
        try:
            matches = _sha256(path) == entry.get("sha256")
        except OSError:
            matches = False
        if not matches:
            report["kept"].append(str(path))
            continue
        if dry_run:
            report["removed"].append(str(path))
            continue
        try:
            path.unlink()
            report["removed"].append(str(path))
        except OSError:
            report["kept"].append(str(path))
    if dry_run:
        return report
    if report["kept"]:
        remaining = {
            path: entry for path, entry in manifest.get("files", {}).items()
            if path in report["kept"]
        }
        manifest["files"] = remaining
        _write(targets["manifest"], json.dumps(manifest, indent=1) + "\n", mode=0o644)
    else:
        try:
            targets["manifest"].unlink()
        except OSError:
            pass
        for directory in (
            targets["base"],
            targets["icon"].parent,
            targets["icon"].parent.parent,
            targets["icon"].parent.parent.parent,
            targets["desktop"].parent,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass
    return report


def status(home=None, data_home_path=None, environ=None):
    """Meldet den Zustand der verwalteten Dateien, ohne etwas zu ändern."""
    environ = dict(os.environ if environ is None else environ)
    targets = _targets(home, environ)
    if data_home_path:
        targets = _targets_for_base(data_home_path)
    manifest = _read_manifest(targets["manifest"])
    report = {"installed": False, "desktop": str(targets["desktop"]),
              "icon": str(targets["icon"]), "files": [], "problems": []}
    if not manifest:
        report["problems"].append("nicht installiert")
        return report
    report["installed"] = True
    for path_text, entry in sorted(manifest.get("files", {}).items()):
        path = Path(path_text)
        if not path.exists():
            report["files"].append({"path": str(path), "state": "fehlt"})
            report["problems"].append(str(path) + ": fehlt")
        elif _sha256(path) != entry.get("sha256"):
            report["files"].append({"path": str(path), "state": "geändert"})
            report["problems"].append(str(path) + ": geändert")
        else:
            report["files"].append({"path": str(path), "state": "ok"})
    return report


def _add_common(parser):
    parser.add_argument("--home", default=None, help="Benutzer-Home für XDG_DATA_HOME")
    parser.add_argument("--data-home", default=None, help="XDG-Datenverzeichnis")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="vibe im Startmenü installieren, prüfen oder entfernen"
    )
    sub = parser.add_subparsers(dest="action", required=True)
    install_parser = sub.add_parser("install", help="Starter, Symbol und Menüeintrag installieren")
    _add_common(install_parser)
    install_parser.add_argument("--starter-source", default=None)
    install_parser.add_argument("--paths-source", default=None)
    install_parser.add_argument("--icon-source", default=None)
    install_parser.add_argument("--dry-run", action="store_true")
    uninstall_parser = sub.add_parser("uninstall", help="verwaltete Dateien entfernen")
    _add_common(uninstall_parser)
    uninstall_parser.add_argument("--dry-run", action="store_true")
    status_parser = sub.add_parser("status", help="Installationszustand anzeigen")
    _add_common(status_parser)
    args = parser.parse_args(argv)

    try:
        if args.action == "install":
            report = install(
                home=args.home,
                data_home_path=args.data_home,
                starter_source=args.starter_source,
                paths_source=args.paths_source,
                icon_source=args.icon_source,
                dry_run=args.dry_run,
            )
            if report["dry_run"]:
                print("Vorschau: es wird nichts geschrieben.")
            for path in report["files"]:
                print(("würde schreiben: " if report["dry_run"] else "geschrieben: ") + path)
            for original, backup in report["backups"]:
                print("gesichert: " + original + " -> " + backup)
            print("Der Starter liest Pfade, Port und Container aus "
                  "~/.config/vibe/config.json oder den VIBE_*-Variablen.")
            return 0
        if args.action == "uninstall":
            report = uninstall(
                home=args.home, data_home_path=args.data_home, dry_run=args.dry_run
            )
            if not report["installed"]:
                print("Keine von vibe verwaltete Desktopintegration vorhanden.")
                return 0
            for path in report["removed"]:
                print(("würde entfernen: " if report["dry_run"] else "entfernt: ") + path)
            for path in report["kept"]:
                print("behalten (geändert): " + path)
            for path in report["missing"]:
                print("bereits entfernt: " + path)
            return 1 if report["kept"] else 0
        report = status(home=args.home, data_home_path=args.data_home)
        if not report["installed"]:
            print("nicht installiert: " + report["desktop"])
            return 1
        for entry in report["files"]:
            print(entry["state"] + ": " + entry["path"])
        if report["problems"]:
            for problem in report["problems"]:
                print("FEHLER: " + problem, file=sys.stderr)
            return 1
        print("installiert: " + report["desktop"])
        return 0
    except (DesktopError, OSError) as error:
        print("vibe-desktop: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
