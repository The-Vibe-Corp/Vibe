#!/usr/bin/env python3
"""Syntaxprüfung der Programmdateien: Python, Bash und JSON.

Aufruf: check-syntax.py [--root <repo>]
Exit 0 = alles syntaktisch gültig, Exit 1 = mindestens ein Fehler.

Die Prüfung ist rein lokal, startet keine Programme aus dem Projekt und
verändert keine Dateien. Python wird mit compile() geprüft, damit keine
__pycache__-Dateien entstehen.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}


def walk_files(root, suffixes, name_filter=None):
    result = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if SKIP_DIRS.intersection(path.parts):
            continue
        if suffixes and path.suffix not in suffixes:
            continue
        if name_filter and not name_filter(path):
            continue
        result.append(path)
    return result


def python_files(root):
    files = []
    bin_dir = root / "bin"
    if bin_dir.is_dir():
        for path in sorted(bin_dir.iterdir()):
            if not path.is_file() or path.suffix in {".pyc", ".pyo", ".sh"}:
                continue
            files.append(path)
    for folder in ("scripts", "tests"):
        base = root / folder
        if base.is_dir():
            files.extend(p for p in walk_files(base, {".py"}))
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(description="Syntaxprüfung")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    errors = []
    py = python_files(root)
    sh = walk_files(root, {".sh"})
    js = walk_files(root, {".json"})

    for path in py:
        rel = path.relative_to(root).as_posix()
        try:
            compile(path.read_text(encoding="utf-8"), rel, "exec")
        except (SyntaxError, UnicodeDecodeError) as error:
            detail = f"Zeile {error.lineno}: {error.msg}" if isinstance(error, SyntaxError) else str(error)
            errors.append(f"FEHLT: {rel}: Syntaxfehler ({detail})")

    for path in sh:
        rel = path.relative_to(root).as_posix()
        result = subprocess.run(
            ["bash", "-n", str(path)], capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout).strip().splitlines()
            errors.append(f"FEHLT: {rel}: Bash-Syntaxfehler ({message[0] if message else 'unbekannt'})")

    for path in js:
        rel = path.relative_to(root).as_posix()
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            errors.append(f"FEHLT: {rel}: JSON-Fehler ({error})")

    if errors:
        print("\n".join(errors))
        print(f"FEHLT: {len(errors)} Syntaxfehler")
        return 1

    print(
        f"OK: {len(py)} Python-, {len(sh)} Bash- und {len(js)} JSON-Datei(en) "
        "syntaktisch geprüft."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
