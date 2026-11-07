#!/usr/bin/env bash
# Entfernt den vibe-Startmenüeintrag und die dazu installierten Dateien.
# Projekte, Laufzeitdaten und persönliche Einstellungen bleiben erhalten.
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 "$SCRIPT_DIR/vibe-desktop.py" uninstall "$@"
