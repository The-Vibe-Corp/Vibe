#!/usr/bin/env bash
# Im Container:  bash install-vibe.sh
set -e
: "${VIBE:?VIBE nicht gesetzt (im Container: source ~/.bashrc)}"
KIT="$(cd "$(dirname "$0")" && pwd)"
case "$KIT" in "$VIBE"/[!_]*) echo "FEHLER: Kit liegt in einem Projektordner. Entpacke es nach ~/kits."; exit 1;; esac
command -v tmux > /dev/null || { echo "FEHLER: tmux fehlt: sudo dnf install -y tmux"; exit 1; }
command -v flock > /dev/null || { echo "FEHLER: flock fehlt: sudo dnf install -y util-linux"; exit 1; }
mkdir -p "$VIBE/_toolchain/bin" "$VIBE/_toolchain/templates" "$VIBE/_logs" "$HOME/.local/bin"
cp "$KIT/bin/vibe" "$KIT/bin/vibe-run.sh" "$KIT/bin/vibe-web.py" "$KIT/bin/vibe_mcp.py" "$VIBE/_toolchain/bin/"
chmod +x "$VIBE/_toolchain/bin/vibe" "$VIBE/_toolchain/bin/vibe-run.sh" "$VIBE/_toolchain/bin/vibe-web.py"
cp -r "$KIT/templates/." "$VIBE/_toolchain/templates/"
cp "$KIT/data/models.json" "$VIBE/_toolchain/models.json"
for f in "$VIBE"/*/scripts/fritz-reconnect.py; do [ -f "$f" ] && cp "$f" "$VIBE/_toolchain/bin/" && break; done || true
ln -sf "$VIBE/_toolchain/bin/vibe" "$HOME/.local/bin/vibe"
tmux kill-session -t vibe-ui 2>/dev/null || true
for d in "$VIBE"/*/; do
  n="$(basename "$d")"; case "$n" in _*) continue;; esac
  [ -e "$d/.git" ] || continue
  if [ ! -f "$d/.vibe/project.env" ]; then
    mkdir -p "$d/.vibe"
    t=generic; [ -f "$d/gradlew" ] && t=android
    cp "$VIBE/_toolchain/templates/$t/.vibe/project.env" "$d/.vibe/project.env"
    echo "Projekt registriert: $n ($t) -> .vibe/project.env prüfen"
  fi
done
echo "Fertig. Aufruf: vibe | Browser: vibe ui | Agenten: vibe agents | Modelle: vibe models | MCP: vibe mcp list | Profile: vibe profile"
