#!/usr/bin/env python3
"""Prüft die importierten Programmdateien gegen docs/import-manifest.json.

Aufruf: check-import-manifest.py [--root <repo>] [--manifest <datei>]
Exit 0 = alle Dateien stimmen mit dem Manifest überein, Exit 1 = Abweichung.

Der Prüfer arbeitet ausschließlich lokal: keine Netzverbindung, keine
Modellaufrufe, keine Änderung an Dateien.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

SKIP_DIRS = {"__pycache__", ".git", "node_modules"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scope_files(root, scopes):
    """Alle Dateien innerhalb der Manifest-Bereiche, relativ und POSIX-notiert."""
    found = {}
    for scope in scopes:
        base = root / scope
        if base.is_file():
            found[scope] = base
        elif base.is_dir():
            for path in sorted(base.rglob("*")):
                if not path.is_file():
                    continue
                if SKIP_DIRS.intersection(path.parts):
                    continue
                if path.suffix in SKIP_SUFFIXES:
                    continue
                found[path.relative_to(root).as_posix()] = path
        else:
            found[scope] = None
    return found


def in_scope(rel, scopes):
    for scope in scopes:
        scope_path = Path(scope)
        if rel == scope_path or scope_path in rel.parents:
            return True
    return False


def main(argv=None):
    default_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Importmanifest prüfen")
    parser.add_argument("--root", default=str(default_root), help="Repository-Wurzel")
    parser.add_argument("--manifest", default=None, help="Pfad zum Manifest")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    manifest_path = Path(args.manifest) if args.manifest else root / "docs" / "import-manifest.json"
    display = os.path.relpath(manifest_path, root)

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as error:
        print(f"FEHLT: {display} nicht lesbar: {error}", file=sys.stdout)
        return 1
    except json.JSONDecodeError as error:
        print(f"FEHLT: {display} ist kein gültiges JSON: {error}", file=sys.stdout)
        return 1

    errors = []
    for key in ("version", "stand", "quelle", "hinweis", "scopes", "files"):
        if key not in manifest:
            errors.append(f"FEHLT: {display}: Pflichtfeld '{key}' fehlt")
    if errors:
        print("\n".join(errors))
        return 1

    scopes = manifest["scopes"]
    files = manifest["files"]
    if not isinstance(scopes, list) or not scopes or not all(isinstance(s, str) and s for s in scopes):
        print(f"FEHLT: {display}: 'scopes' muss eine nichtleere Liste von Pfaden sein")
        return 1
    if not isinstance(files, list) or not files:
        print(f"FEHLT: {display}: 'files' muss eine nichtleere Liste sein")
        return 1

    declared = set()
    for entry in files:
        if not isinstance(entry, dict):
            errors.append(f"FEHLT: {display}: Eintrag ist kein Objekt: {entry!r}")
            continue
        rel_text = entry.get("path")
        if not isinstance(rel_text, str) or not rel_text:
            errors.append(f"FEHLT: {display}: Eintrag ohne gültigen 'path'")
            continue
        rel = Path(rel_text)
        if rel.is_absolute() or ".." in rel.parts:
            errors.append(f"FEHLT: {rel_text}: Pfad ist absolut oder verlässt das Repository")
            continue
        if not in_scope(rel, scopes):
            errors.append(f"FEHLT: {rel_text}: Pfad liegt außerhalb der Manifest-Bereiche")
            continue
        if rel_text in declared:
            errors.append(f"FEHLT: {rel_text}: doppelt im Manifest")
            continue
        declared.add(rel_text)

        target = root / rel
        if not target.is_file():
            errors.append(f"FEHLT: {rel_text}: im Manifest genannt, aber nicht vorhanden")
            continue
        size = target.stat().st_size
        if entry.get("bytes") != size:
            errors.append(
                f"FEHLT: {rel_text}: Größe weicht ab (Manifest {entry.get('bytes')}, Datei {size})"
            )
        actual = sha256_file(target)
        if entry.get("sha256") != actual:
            errors.append(
                f"FEHLT: {rel_text}: Prüfsumme weicht ab "
                f"(Manifest {str(entry.get('sha256'))[:12]}, Datei {actual[:12]})"
            )

    actual_files = scope_files(root, scopes)
    for rel, path in actual_files.items():
        if path is None:
            errors.append(f"FEHLT: Bereich '{rel}' existiert nicht")
        elif rel not in declared:
            errors.append(f"FEHLT: {rel}: Datei ist nicht im Manifest aufgeführt")

    if errors:
        print("\n".join(errors))
        print(f"FEHLT: {len(errors)} Abweichung(en) zwischen Bestand und {display}")
        return 1

    print(f"OK: {len(declared)} Dateien stimmen mit {display} überein.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
