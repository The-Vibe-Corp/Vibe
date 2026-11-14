#!/usr/bin/env python3
"""Snapshot und Prüfung der aktiven vibe-Installation.

Aufruf:
  active-install.py snapshot [--root <install>] [--snapshot <datei>]
  active-install.py verify   [--root <install>] [--snapshot <datei>]

Der Snapshot enthält SHA-256 und relative Pfade der Programmdateien unter
bin/, templates/, models.json, profiles.json, vibe.svg und verify/.
Laufzeitdaten (_logs, Tokens, Sicherungen) und __pycache__ sind ausgenommen.
Nicht im Umfang sind außerdem die nicht programmatischen Bereiche gradle/,
android-sdk/, config-backups/ und agent-backups/.
Die Prüfung belegt, dass die aktive Installation während V-001 unverändert
blieb. Sie liest nur und schreibt nur den Snapshot im Modus 'snapshot'.
"""
import argparse
import hashlib
import os
import sys
from pathlib import Path

SCOPES = ("bin", "templates", "models.json", "profiles.json", "vibe.svg", "verify")
SKIP_DIRS = {"__pycache__", ".git"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def default_root():
    vibe = os.environ.get("VIBE")
    if vibe:
        return Path(vibe) / "_toolchain"
    return Path.home() / "VibeCode" / "_toolchain"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect(root):
    files = {}
    for scope in SCOPES:
        base = root / scope
        if base.is_file():
            files[scope] = base
        elif base.is_dir():
            for path in sorted(base.rglob("*")):
                if not path.is_file():
                    continue
                if SKIP_DIRS.intersection(path.parts):
                    continue
                if path.suffix in SKIP_SUFFIXES:
                    continue
                files[path.relative_to(root).as_posix()] = path
    return files


def read_snapshot(path):
    entries = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        entries[rel] = digest
    return entries


def write_snapshot(root, target):
    files = collect(root)
    lines = [f"{sha256_file(path)}  {rel}" for rel, path in sorted(files.items())]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"OK: {len(lines)} Dateien der aktiven Installation in {target} erfasst.")
    return 0


def verify(root, snapshot):
    if not snapshot.exists():
        print(f"FEHLT: Snapshot {snapshot} fehlt")
        return 1
    expected = read_snapshot(snapshot)
    actual = collect(root)
    problems = []
    for rel, digest in expected.items():
        if rel not in actual:
            problems.append(f"FEHLT: {rel}: fehlt in der aktiven Installation")
        elif sha256_file(actual[rel]) != digest:
            problems.append(f"FEHLT: {rel}: geändert gegenüber Snapshot")
    for rel in sorted(set(actual) - set(expected)):
        problems.append(f"FEHLT: {rel}: neu in der aktiven Installation")
    if problems:
        print("\n".join(problems))
        print(f"FEHLT: aktive Installation weicht in {len(problems)} Punkt(en) vom Snapshot ab")
        return 1
    print(f"OK: aktive Installation unverändert ({len(expected)} Dateien geprüft).")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Aktive Installation prüfen")
    parser.add_argument("command", choices=("snapshot", "verify"))
    parser.add_argument("--root", default=str(default_root()))
    parser.add_argument(
        "--snapshot",
        default=str(Path(__file__).resolve().parent.parent / "docs" / "baseline-installation.sha256"),
    )
    args = parser.parse_args(argv)
    root = Path(args.root)
    snapshot = Path(args.snapshot)
    if not root.is_dir():
        print(f"FEHLT: Installationsordner {root} fehlt")
        return 1
    if args.command == "snapshot":
        return write_snapshot(root, snapshot)
    return verify(root, snapshot)


if __name__ == "__main__":
    sys.exit(main())
