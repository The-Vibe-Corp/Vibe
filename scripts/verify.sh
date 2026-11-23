#!/usr/bin/env bash
# Isolierte Projektprüfung (V-002).
# Aufruf: bash scripts/verify.sh quick|package|full [--project DIR] [--tests DIR ...]
#         [--jobs N] [--timeout SEK] [--baseline PATH] [--env LABEL]
#         [--min-tests N] [--write-baseline] [--keep]
# Die eigentliche Logik liegt in scripts/verify_engine.py (Python-Standardbibliothek).
set -u
SCRIPT_SOURCE="${BASH_SOURCE[0]}"
SCRIPT_DIR="${SCRIPT_SOURCE%/*}"
if [ "$SCRIPT_DIR" = "$SCRIPT_SOURCE" ]; then
    SCRIPT_DIR="."
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "FEHLT: python3 wird für scripts/verify.sh benötigt (Werkzeug, Exit 4)." >&2
    exit 4
fi
exec python3 "$SCRIPT_DIR/verify_engine.py" "$@"
