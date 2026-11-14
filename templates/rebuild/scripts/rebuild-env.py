#!/usr/bin/env python3
"""Prüft und richtet die Werkzeugumgebung eines Rebuild-Projekts ein (F14).

Aufruf:
    python3 scripts/rebuild-env.py --check [--json]
    python3 scripts/rebuild-env.py --plan [--all]
    python3 scripts/rebuild-env.py --setup --yes [--all]

Das Profil unterscheidet Werkzeuggruppen:

* ``core``       Git, Python, Shell, Datei- und Binärwerkzeuge
* ``analyse``    Debugger, Tracing, Wine, Java
* ``reverse``    Ghidra headless (nur bei fehlenden Quellen nötig)
* ``paketierung`` linuxdeploy, appimagetool, patchelf
* ``ci``         Container-Laufzeit für die Testmatrix
* ``tests``      Screenshot-/Browserwerkzeuge

Pflicht sind die Gruppen aus ``REBUILD_REQUIRED_GROUPS`` in
``.vibe/project.env`` (Standard: ``core analyse``). Fehlt ein Werkzeug einer
Pflichtgruppe, endet ``--check`` mit Exit 1. Optionale Gruppen werden nur
gemeldet.

``--setup`` installiert ausschließlich über den erkannten Paketmanager und nur
mit ausdrücklicher Bestätigung ``--yes``. Werkzeuge ohne Paket (Ghidra,
linuxdeploy, appimagetool, opencode) werden nie automatisch heruntergeladen;
der Befehl nennt stattdessen den manuellen nächsten Schritt und behauptet
keinen Erfolg. Es werden keine Netzwerkaufrufe aus dem Prüfmodus ausgeführt.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Tool:
    name: str
    group: str
    commands: tuple
    packages: dict = field(default_factory=dict)
    hint: str = ""


TOOLS = (
    Tool("git", "core", ("git",), {"apt": ["git"], "dnf": ["git"], "pacman": ["git"], "zypper": ["git"]}),
    Tool("python3", "core", ("python3",), {"apt": ["python3"], "dnf": ["python3"], "pacman": ["python"], "zypper": ["python3"]}),
    Tool("bash", "core", ("bash",), {"apt": ["bash"], "dnf": ["bash"], "pacman": ["bash"], "zypper": ["bash"]}),
    Tool("opencode", "core", ("opencode",), {}, "opencode installieren: https://opencode.ai (nicht automatisch herunterladen)"),
    Tool("tmux", "core", ("tmux",), {"apt": ["tmux"], "dnf": ["tmux"], "pacman": ["tmux"], "zypper": ["tmux"]}),
    Tool("bwrap", "core", ("bwrap",), {"apt": ["bubblewrap"], "dnf": ["bubblewrap"], "pacman": ["bubblewrap"], "zypper": ["bubblewrap"]}),
    Tool("file", "core", ("file",), {"apt": ["file"], "dnf": ["file"], "pacman": ["file"], "zypper": ["file"]}),
    Tool("strings", "core", ("strings",), {"apt": ["binutils"], "dnf": ["binutils"], "pacman": ["binutils"], "zypper": ["binutils"]}),
    Tool("objdump", "core", ("objdump",), {"apt": ["binutils"], "dnf": ["binutils"], "pacman": ["binutils"], "zypper": ["binutils"]}),
    Tool("readelf", "core", ("readelf",), {"apt": ["binutils"], "dnf": ["binutils"], "pacman": ["binutils"], "zypper": ["binutils"]}),
    Tool("gdb", "analyse", ("gdb",), {"apt": ["gdb"], "dnf": ["gdb"], "pacman": ["gdb"], "zypper": ["gdb"]}),
    Tool("strace", "analyse", ("strace",), {"apt": ["strace"], "dnf": ["strace"], "pacman": ["strace"], "zypper": ["strace"]}),
    Tool("ltrace", "analyse", ("ltrace",), {"apt": ["ltrace"], "dnf": ["ltrace"], "pacman": ["ltrace"], "zypper": ["ltrace"]}),
    Tool("wine", "analyse", ("wine",), {"apt": ["wine"], "dnf": ["wine"], "pacman": ["wine"], "zypper": ["wine"]}),
    Tool("java", "analyse", ("java",), {"apt": ["default-jre-headless"], "dnf": ["java-17-openjdk-headless"], "pacman": ["jre-openjdk-headless"], "zypper": ["java-17-openjdk-headless"]}),
    Tool("ghidra", "reverse", ("ghidra", "analyzeHeadless"), {}, "Ghidra entpacken und analyzeHeadless in den PATH legen: https://ghidra-sre.org"),
    Tool("linuxdeploy", "paketierung", ("linuxdeploy",), {}, "linuxdeploy als AppImage bereitstellen: https://github.com/linuxdeploy/linuxdeploy"),
    Tool("appimagetool", "paketierung", ("appimagetool",), {}, "appimagetool als AppImage bereitstellen: https://github.com/AppImage/appimagetool"),
    Tool("patchelf", "paketierung", ("patchelf",), {"apt": ["patchelf"], "dnf": ["patchelf"], "pacman": ["patchelf"], "zypper": ["patchelf"]}),
    Tool("podman", "ci", ("podman",), {"apt": ["podman"], "dnf": ["podman"], "pacman": ["podman"], "zypper": ["podman"]}),
    Tool("docker", "ci", ("docker",), {"apt": ["docker.io"], "dnf": ["docker"], "pacman": ["docker"], "zypper": ["docker"]}),
    Tool("playwright", "tests", ("playwright",), {}, "pip install playwright && playwright install chromium"),
)

MANAGERS = ("dnf", "apt-get", "pacman", "zypper")
DEFAULT_REQUIRED_GROUPS = ("core", "analyse")
KNOWN_GROUPS = tuple(sorted({tool.group for tool in TOOLS}))


def tool_by_name(name):
    for tool in TOOLS:
        if tool.name == name:
            return tool
    raise KeyError("Unbekanntes Werkzeug: " + str(name))


def detect_manager(which=shutil.which):
    for manager in MANAGERS:
        if which(manager):
            return manager
    return None


def check(which=shutil.which, required_groups=DEFAULT_REQUIRED_GROUPS):
    """Ermittelt vorhandene und fehlende Werkzeuge, ohne etwas zu starten."""
    required = set(required_groups)
    unknown = sorted(required - set(KNOWN_GROUPS))
    if unknown:
        raise ValueError(
            "Unbekannte Werkzeuggruppe(n): " + ", ".join(unknown)
            + " (erlaubt: " + ", ".join(KNOWN_GROUPS) + ")"
        )
    rows = []
    missing_required = []
    missing_optional = []
    for tool in TOOLS:
        path = next((candidate for candidate in (which(command) for command in tool.commands) if candidate), None)
        needs = tool.group in required
        row = {
            "name": tool.name,
            "group": tool.group,
            "commands": list(tool.commands),
            "path": path,
            "required": needs,
            "hint": tool.hint,
            "packages": tool.packages,
        }
        rows.append(row)
        if path:
            continue
        (missing_required if needs else missing_optional).append(tool.name)
    return {
        "ok": not missing_required,
        "required_groups": sorted(required),
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "tools": rows,
    }


def install_plan(missing_names, manager=None, which=shutil.which, euid=None):
    """Baut einen Installationsplan; führt ihn nicht aus."""
    euid = os.geteuid() if euid is None else euid
    manager = manager or detect_manager(which)
    package_key = {"apt-get": "apt"}.get(manager or "", manager or "")
    packages = []
    manual = []
    for name in missing_names:
        tool = tool_by_name(name)
        choices = tool.packages.get(package_key, [])
        if choices:
            for package in choices:
                if package not in packages:
                    packages.append(package)
        else:
            manual.append({"tool": tool.name, "hint": tool.hint or "manuell installieren"})
    commands = []
    if packages:
        if not manager:
            return {
                "manager": None,
                "commands": [],
                "manual": manual,
                "error": "Kein unterstützter Paketmanager gefunden (" + ", ".join(MANAGERS) + ").",
            }
        prefix = [] if euid == 0 else (["sudo"] if which("sudo") else [])
        commands.append(prefix + [manager, "install", "-y"] + packages)
    return {"manager": manager, "commands": commands, "manual": manual}


def setup(plan, runner=None):
    """Führt ausschließlich die Paketbefehle des Plans aus."""
    if runner is None:
        runner = lambda command: subprocess.run(command, check=False)  # noqa: E731
    results = []
    for command in plan.get("commands", []):
        result = runner(command)
        returncode = getattr(result, "returncode", 1)
        results.append({"command": list(command), "returncode": returncode, "ok": returncode == 0})
        if returncode != 0:
            break
    return results


def parse_required_groups(text):
    values = {}
    for line in text.splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    raw = values.get("REBUILD_REQUIRED_GROUPS", " ".join(DEFAULT_REQUIRED_GROUPS))
    return tuple(part for part in raw.replace(",", " ").split() if part)


def read_required_groups(project):
    env_file = Path(project) / ".vibe" / "project.env"
    try:
        return parse_required_groups(env_file.read_text(encoding="utf-8"))
    except OSError:
        return DEFAULT_REQUIRED_GROUPS


def render(result):
    print("Rebuild-Werkzeugprüfung")
    print("Pflichtgruppen: " + ", ".join(result["required_groups"]))
    for row in result["tools"]:
        state = "OK   " if row["path"] else "FEHLT"
        if row["path"]:
            suffix = row["path"]
        elif row["hint"]:
            suffix = row["hint"]
        elif row["packages"]:
            suffix = "über Paketmanager installierbar (--plan)"
        else:
            suffix = "manuell installieren"
        print(f"  {state} {row['name']:14} {suffix}")
    if result["missing_required"]:
        print("Fehlende Pflichtwerkzeuge: " + ", ".join(result["missing_required"]))
    if result["missing_optional"]:
        print("Optionale Werkzeuge fehlen: " + ", ".join(result["missing_optional"]))
    print("Ergebnis: " + ("vollständig" if result["ok"] else "unvollständig"))
    return 0 if result["ok"] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Werkzeugumgebung eines Rebuild-Projekts prüfen")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="Werkzeuge prüfen (Standard)")
    action.add_argument("--plan", action="store_true", help="Installationsplan anzeigen")
    action.add_argument("--setup", action="store_true", help="Fehlende Pakete installieren")
    parser.add_argument("--yes", action="store_true", help="Installation ausdrücklich bestätigen")
    parser.add_argument("--all", action="store_true", help="auch optionale Gruppen einplanen")
    parser.add_argument("--json", action="store_true", help="maschinenlesbare Ausgabe")
    parser.add_argument("--project", default=None, help="Projektordner (Standard: zwei Ebenen über dem Skript)")
    parser.add_argument("--env-file", default=None, help="abweichende .vibe/project.env")
    parser.add_argument("--required-groups", default=None, help="kommagetrennte Pflichtgruppen")
    args = parser.parse_args(argv)

    project = Path(args.project).resolve() if args.project else Path(__file__).resolve().parents[1]
    if args.env_file:
        try:
            groups = parse_required_groups(Path(args.env_file).read_text(encoding="utf-8"))
        except OSError:
            groups = DEFAULT_REQUIRED_GROUPS
    else:
        groups = read_required_groups(project)
    if args.required_groups:
        groups = tuple(part for part in args.required_groups.replace(",", " ").split() if part)

    try:
        result = check(required_groups=groups)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    missing = list(result["missing_required"])
    if args.all:
        missing += result["missing_optional"]

    if args.setup:
        plan = install_plan(missing)
        if not args.yes:
            if args.json:
                print(json.dumps({"plan": plan, "applied": False}, ensure_ascii=False, indent=2))
            else:
                print("Bestätigung fehlt: Installation nur mit --setup --yes.")
                if plan.get("error"):
                    print("  " + plan["error"])
                for command in plan["commands"]:
                    print("  " + " ".join(command))
                for item in plan["manual"]:
                    print(f"  MANUELL {item['tool']}: {item['hint']}")
            return 2
        results = setup(plan)
        after = check(required_groups=groups)
        if args.json:
            print(json.dumps({"plan": plan, "results": results, "check": after}, ensure_ascii=False, indent=2))
        else:
            if plan.get("error"):
                print("FEHLER: " + plan["error"])
            for item in results:
                print(("OK   " if item["ok"] else "FEHLER") + " " + " ".join(item["command"]))
            for item in plan["manual"]:
                print(f"  MANUELL {item['tool']}: {item['hint']}")
            render(after)
        return 0 if after["ok"] and not plan["manual"] else 1

    if args.plan:
        plan = install_plan(missing)
        if args.json:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
        else:
            print("Paketmanager: " + str(plan["manager"] or "nicht gefunden"))
            if plan.get("error"):
                print("  " + plan["error"])
            for command in plan["commands"]:
                print("  " + " ".join(command))
            for item in plan["manual"]:
                print(f"  MANUELL {item['tool']}: {item['hint']}")
        return 0

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    return render(result)


if __name__ == "__main__":
    sys.exit(main())
