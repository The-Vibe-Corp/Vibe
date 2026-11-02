#!/usr/bin/env bash
# Installiert den vibe-Startmenüeintrag für den aktuellen Benutzer (V-017).
# Der eigentliche Installer liegt in scripts/vibe-desktop.py; dieses Skript
# ist der stabile Einstieg für Dokumentation und Host-Aufrufe.
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 "$SCRIPT_DIR/vibe-desktop.py" install "$@"
