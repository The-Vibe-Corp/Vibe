#!/usr/bin/env python3
"""Sucht nach versehentlich abgelegten Geheimnissen im Repository.

Aufruf: check-no-secrets.py [--root <verzeichnis>]
Exit 0 = keine erkannten Geheimnisse, Exit 1 = mindestens ein Fund.

Die Prüfung ist eine Heuristik für typische Schlüsselformate und
Zugangsdaten-Zuweisungen. Sie ersetzt keine vollständige Secret-Scanning-
Lösung, sondern belegt für V-001 reproduzierbar, dass der importierte
Bestand keine offensichtlichen Geheimnisse enthält. Dateien über 2 MiB
werden übersprungen. Es werden keine Netzverbindungen aufgebaut und keine
Dateien verändert.
"""
import argparse
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}
MAX_BYTES = 2 * 1024 * 1024

PATTERNS = (
    ("Privater Schlüssel", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |PGP )?PRIVATE KEY-----")),
    ("AWS-Zugangsschlüssel", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub-Token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("OpenAI-/Anthropic-Schlüssel", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("Slack-Token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Google-API-Schlüssel", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Passwort in URL", re.compile(r"://[^/\s:@]+:[^/\s@]{8,}@")),
    (
        "Zugangsdaten-Zuweisung",
        re.compile(
            r"(?i)\b(?:api[_-]?key|apikey|access[_-]?token|secret|password|passwd|token)\b"
            r"\s*[:=]\s*[\"'][^\"'\s]{16,}[\"']"
        ),
    ),
    (
        "Dotenv-Zugangsdaten",
        re.compile(
            r"(?im)^\s*[A-Z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API_KEY|APIKEY|ACCESS_KEY)"
            r"[A-Z0-9_]*\s*=\s*[^\s\"'$#()[\]]{16,}\s*$"
        ),
    ),
)


def iter_files(root):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if SKIP_DIRS.intersection(path.parts):
            continue
        try:
            if path.stat().st_size > MAX_BYTES:
                continue
        except OSError:
            continue
        yield path


def scan_file(path):
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        for label, pattern in PATTERNS:
            if pattern.search(line):
                findings.append((number, label))
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description="Geheimnisprüfung")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Anzahl der geprüften Dateien ausgeben",
    )
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    findings = []
    count = 0
    for path in iter_files(root):
        count += 1
        rel = path.relative_to(root).as_posix()
        for number, label in scan_file(path):
            findings.append(f"FEHLT: {rel}:{number}: {label}")

    if findings:
        print("\n".join(findings))
        print(f"FEHLT: {len(findings)} mögliche(s) Geheimnis(se) gefunden")
        return 1

    print("OK: keine Geheimnisse erkannt.")
    if args.verbose:
        print(f"Geprüft: {count} Dateien.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
