#!/usr/bin/env python3
"""Erzeugt eine reproduzierbare Quellrelease ohne persönliche Daten (V-020).

Aufruf:
    python3 scripts/build-release.py [--source DIR] [--output DIR] [--ref REF]
    python3 scripts/build-release.py verify ARCHIV.tar.gz

Die Release wird ausschließlich aus versionierten Dateien eines Git-Stands
gebaut. Unversionierte Laufzeitdaten (Token, Logs, Sicherungen, Installation)
gelangen dadurch nicht in das Archiv. Zusätzlich prüft der Bau jeden Text auf
absolute Home-Pfade und die Muster der Geheimnisprüfung. Zwei Baue desselben
Commits sind byte-identisch: Einträge sind sortiert, Zeitstempel, Benutzer und
Gruppen sind fest, und die gzip-Kopfzeile enthält keinen Zeitpunkt.

Das Archiv enthält ``RELEASE.json`` mit Version, Commit und SHA-256 jeder
Datei. ``verify`` prüft ein vorhandenes Archiv gegen dieses Manifest.
"""
import argparse
import fnmatch
import gzip
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

FORMAT = 1
DEFAULT_NAME = "vibe"
RELEASE_MANIFEST = "RELEASE.json"
VERSION_PATH = "VERSION"

EXCLUDE_PATTERNS = (
    ".git",
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.log",
    "*.tmp",
    "*.swp",
    "web.token",
    "web.instance",
    "_secrets.env",
    ".env",
    "config-backups",
    "agent-backups",
    "_toolchain",
    "_logs",
    "dist",
    "build",
    ".venv",
    "venv",
    "node_modules",
    "*.tar.gz",
)

REQUIRED_PATHS = (
    "VERSION",
    "README.md",
    "SPEC.md",
    "AGENTS.md",
    "bin/vibe",
    "bin/vibe-web.py",
    "scripts/setup-vibe.py",
    "scripts/verify.sh",
    "tests",
)

HOME_PATH_RE = re.compile(r"(?<![\w/.-])/(?:home|Users)/([A-Za-z0-9._-]+)/")
PLACEHOLDER_USERS = {
    "user",
    "users",
    "nutzer",
    "alice",
    "bob",
    "example",
    "test",
    "name",
}
VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._+~-]*$")
MAX_SCAN_BYTES = 1024 * 1024


class ReleaseError(Exception):
    """Der Releasebau kann nicht verantwortbar fortgesetzt werden."""


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(source, arguments):
    """Ruft git ohne Shell im Quellordner auf und liefert die Rohausgabe."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(source), *arguments],
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ReleaseError("git konnte nicht ausgeführt werden: " + str(error))
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", "replace").strip()
        raise ReleaseError(
            "git " + " ".join(arguments) + " ist fehlgeschlagen: " + message
        )
    return completed.stdout


def require_git(source):
    try:
        git(source, ["rev-parse", "--git-dir"])
    except ReleaseError:
        raise ReleaseError(
            "Der Quellordner ist kein Git-Repository; eine reproduzierbare "
            "Release wird nur aus versionierten Dateien gebaut."
        )


def tracked_entries(source, ref):
    """Liefert (mode, blob-sha, pfad) je versionierter Datei des Stands."""
    output = git(source, ["ls-tree", "-r", "-z", "--full-tree", ref])
    entries = []
    for record in output.split(b"\0"):
        if not record:
            continue
        meta, separator, name = record.partition(b"\t")
        if not separator:
            raise ReleaseError("Unerwartete git-ls-tree-Ausgabe: " + repr(record[:80]))
        mode, kind, digest = meta.decode("ascii").split()
        if kind != "blob":
            raise ReleaseError(
                "Untermodule und Sonderobjekte werden nicht unterstützt: "
                + name.decode("utf-8", "replace")
            )
        if mode == "120000":
            # Git speichert einen Symlink als Blob mit dem Zielpfad als Inhalt.
            # Ohne diese Prüfung läge im Archiv eine reguläre Datei mit dem
            # Zieltext und der Inhalt wäre still verfälscht.
            raise ReleaseError(
                "Symbolische Links werden nicht unterstützt: "
                + name.decode("utf-8", "replace")
            )
        entries.append((mode, digest, name.decode("utf-8")))
    return sorted(entries, key=lambda entry: entry[2])


def blob(source, digest):
    return git(source, ["cat-file", "blob", digest])


def excluded(path):
    parts = path.split("/")
    for pattern in EXCLUDE_PATTERNS:
        if fnmatch.fnmatch(path, pattern):
            return True
        if any(fnmatch.fnmatch(part, pattern) for part in parts):
            return True
    return False


def secret_patterns(script_dir):
    """Lädt die Muster der vorhandenen Geheimnisprüfung, falls vorhanden."""
    checker = Path(script_dir) / "check-no-secrets.py"
    if not checker.is_file():
        return ()
    try:
        spec = importlib.util.spec_from_file_location(
            "build_release_secret_checker", checker
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (ImportError, OSError, ValueError):
        return ()
    return tuple(getattr(module, "PATTERNS", ()))


def decode_text(data):
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def scan_text(path, text, patterns):
    problems = []
    for number, line in enumerate(text.splitlines(), 1):
        match = HOME_PATH_RE.search(line)
        if match and match.group(1).lower() not in PLACEHOLDER_USERS:
            problems.append(
                "%s:%d: absoluter Home-Pfad eines Benutzers (%s)"
                % (path, number, match.group(1))
            )
        for label, pattern in patterns:
            if pattern.search(line):
                problems.append("%s:%d: %s" % (path, number, label))
    return problems


def read_version(source, entries, ref):
    for mode, digest, path in entries:
        if path == VERSION_PATH:
            text = blob(source, digest).decode("utf-8", "replace").strip()
            if not VERSION_RE.match(text):
                raise ReleaseError(
                    "VERSION enthält keine gültige Versionskennung: " + repr(text)
                )
            return text
    raise ReleaseError("VERSION fehlt im Stand " + str(ref))


def build_release(source, output, ref="HEAD", name=DEFAULT_NAME):
    """Baut die Release und liefert den Pfad des Archivs."""
    source = Path(source).resolve()
    output = Path(output).resolve()
    require_git(source)
    full_commit = git(source, ["rev-parse", ref]).decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{7,64}", full_commit):
        raise ReleaseError("git lieferte keinen gültigen Commit: " + repr(full_commit))
    short_commit = full_commit[:7]
    entries = tracked_entries(source, ref)
    version = read_version(source, entries, ref)
    patterns = secret_patterns(Path(__file__).resolve().parent)

    files = []
    problems = []
    for mode, digest, path in entries:
        if excluded(path):
            raise ReleaseError(
                "Versionierte Datei entspricht einem Ausschlussmuster und darf "
                "nicht stillschweigend fehlen: " + path
            )
        data = blob(source, digest)
        text = decode_text(data) if len(data) <= MAX_SCAN_BYTES else None
        if text is not None:
            problems.extend(scan_text(path, text, patterns))
        files.append(
            {
                "path": path,
                "sha256": sha256_bytes(data),
                "bytes": len(data),
                "mode": 0o755 if mode == "100755" else 0o644,
                "data": data,
            }
        )
    if problems:
        raise ReleaseError(
            "Persönliche Daten oder Geheimnisse im Releaseinhalt:\n"
            + "\n".join(problems)
        )

    manifest = {
        "format": FORMAT,
        "name": name,
        "version": version,
        "commit": full_commit,
        "short_commit": short_commit,
        "ref": str(ref),
        "files": [
            {
                "path": entry["path"],
                "sha256": entry["sha256"],
                "bytes": entry["bytes"],
                "mode": entry["mode"],
            }
            for entry in files
        ],
    }
    manifest_data = (
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    files.append(
        {
            "path": RELEASE_MANIFEST,
            "sha256": sha256_bytes(manifest_data),
            "bytes": len(manifest_data),
            "mode": 0o644,
            "data": manifest_data,
        }
    )

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for entry in sorted(files, key=lambda item: item["path"]):
            info = tarfile.TarInfo(entry["path"])
            info.size = entry["bytes"]
            info.mode = entry["mode"]
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(entry["data"]))
    archive_name = "%s-%s-%s.tar.gz" % (name, version, short_commit)
    output.mkdir(parents=True, exist_ok=True)
    target = output / archive_name
    with open(target, "wb") as handle:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=handle, mtime=0
        ) as compressed:
            compressed.write(buffer.getvalue())
    digest = sha256_file(target)
    (output / (archive_name + ".sha256")).write_text(
        "%s  %s\n" % (digest, archive_name), encoding="utf-8"
    )
    return target


def verify_archive(path, patterns=None):
    """Prüft ein Archiv gegen sein Manifest; leer heißt fehlerfrei."""
    path = Path(path)
    if patterns is None:
        patterns = secret_patterns(Path(__file__).resolve().parent)
    problems = []
    try:
        archive = tarfile.open(path, "r:gz")
    except (OSError, tarfile.TarError) as error:
        return ["Archiv nicht lesbar: " + str(error)]
    with archive:
        members = {}
        for member in archive.getmembers():
            name = member.name
            if name.startswith("/") or ".." in Path(name).parts:
                problems.append("Unsicherer Pfad im Archiv: " + name)
                continue
            if not member.isfile():
                problems.append("Nur reguläre Dateien erlaubt: " + name)
                continue
            if excluded(name):
                problems.append("Ausgeschlossene Datei im Archiv: " + name)
                continue
            handle = archive.extractfile(member)
            members[name] = handle.read() if handle else b""

    if RELEASE_MANIFEST not in members:
        problems.append("RELEASE.json fehlt im Archiv")
        return problems
    try:
        manifest = json.loads(members[RELEASE_MANIFEST].decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        problems.append("RELEASE.json ist ungültig: " + str(error))
        return problems
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        problems.append("RELEASE.json hat ein unbekanntes Format")
        return problems
    entries = manifest.get("files")
    if not isinstance(entries, list):
        problems.append("RELEASE.json enthält keine Dateiliste")
        return problems

    declared = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            problems.append("Ungültiger Eintrag in RELEASE.json")
            continue
        name = entry["path"]
        if name in declared:
            problems.append("Doppelter Eintrag in RELEASE.json: " + name)
            continue
        declared[name] = entry
    actual = set(members) - {RELEASE_MANIFEST}
    for name in sorted(actual - set(declared)):
        problems.append("Datei fehlt in RELEASE.json: " + name)
    for name in sorted(set(declared) - actual):
        problems.append("Datei aus RELEASE.json fehlt im Archiv: " + name)
    for name in sorted(actual & set(declared)):
        data = members[name]
        entry = declared[name]
        if entry.get("bytes") != len(data):
            problems.append("Größe weicht ab: " + name)
        if entry.get("sha256") != sha256_bytes(data):
            problems.append("Prüfsumme weicht ab: " + name)
        text = decode_text(data) if len(data) <= MAX_SCAN_BYTES else None
        if text is not None:
            problems.extend(scan_text(name, text, patterns))
    for required in REQUIRED_PATHS:
        if required in members:
            continue
        if any(name.startswith(required.rstrip("/") + "/") for name in members):
            continue
        problems.append("Pflichtdatei fehlt: " + required)
    return sorted(set(problems))


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "verify":
        parser = argparse.ArgumentParser(
            prog="build-release.py verify",
            description="Releasearchiv gegen RELEASE.json prüfen",
        )
        parser.add_argument("archive")
        args = parser.parse_args(arguments[1:])
        problems = verify_archive(Path(args.archive))
        if problems:
            print("\n".join("FEHLT: " + problem for problem in problems))
            return 1
        print("OK: Release geprüft:", args.archive)
        return 0

    default_source = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Reproduzierbare Quellrelease ohne persönliche Daten bauen"
    )
    parser.add_argument("--source", default=str(default_source))
    parser.add_argument("--output", default=str(default_source / "dist"))
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--name", default=DEFAULT_NAME)
    args = parser.parse_args(arguments)
    try:
        target = build_release(
            source=Path(args.source),
            output=Path(args.output),
            ref=args.ref,
            name=args.name,
        )
    except ReleaseError as error:
        print("FEHLT: " + str(error), file=sys.stderr)
        return 1
    print("Release:", target)
    print("SHA-256:", sha256_file(target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
