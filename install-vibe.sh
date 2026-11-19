#!/usr/bin/env bash
# Kompatibler Einstieg für Linux: installiert/aktualisiert vibe ohne Rückfragen.
# Der eigentliche, plattformübergreifende Setup liegt in scripts/setup-vibe.py.
set -e
: "${VIBE:?VIBE nicht gesetzt (im Container: source ~/.bashrc)}"
KIT="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$KIT/scripts/setup-vibe.py" --yes --update --vibe "$VIBE" --source "$KIT" "$@"
