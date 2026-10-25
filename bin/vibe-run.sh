#!/usr/bin/env bash
# Allgemeiner Paket-Läufer. Aufruf: vibe-run.sh <projektordner> [agent]
# Kostenbremse: MAX_PACKAGES in .vibe/project.env (oder Umgebungsvariable VIBE_MAX_PACKAGES) begrenzt die Zahl der Durchgänge.
P="$(cd "${1:?Projektordner}" && pwd)"; NAME="${VIBE_LOGNAME:-$(basename "$P" | tr -c 'A-Za-z0-9_\n-' '_')}"
V="${VIBE:?VIBE nicht gesetzt}/_toolchain/verify"
BIN="$VIBE/_toolchain/bin"
LOG="$VIBE/_logs/$NAME.log"; mkdir -p "$VIBE/_logs"
cd "$P" || exit 1
[ -f .vibe/project.env ] && set -a && . ./.vibe/project.env && set +a
AGENT="${2:-${AGENT:-coding-agent_deepseek}}"
MAXP="${VIBE_MAX_PACKAGES:-${MAX_PACKAGES:-80}}"
FRITZ_PY="$VIBE/_toolchain/fritz-venv/bin/python"; [ -x "$FRITZ_PY" ] || FRITZ_PY="$HOME/.venvs/fritz/bin/python"
FRITZ_SCRIPT="$BIN/fritz-reconnect.py"
HASHFILE="$HOME/.config/schreibfuchs-verify.sha"
check_hash() { [ -f "$HASHFILE" ] && (cd "$V" && sha256sum -c "$HASHFILE" --quiet) || { echo "ABBRUCH: Abnahme-Dateien fehlen oder wurden verändert."; exit 3; }; }
final_verify() {
  if [ "$TYPE" = "android" ]; then bash "$V/verify.sh" "$P" full
  elif [ -n "$VERIFY_FULL" ] && [[ "$VERIFY_FULL" != *TODO* ]]; then bash -lc "$VERIFY_FULL"
  else echo "FEHLT: keine VERIFY_FULL-Prüfung in .vibe/project.env definiert"; return 1; fi
}
next_item() {
  local T; T="$(mktemp -d)"
  flock /tmp/vibe-next.lock bash -c 'python3 "$1" "$2" "$3" > /dev/null && cp /tmp/next_id "$4/id" && cp /tmp/next_block "$4/block"' _ "$V/next_item.py" "$P" "$SKIP" "$T"
  local rc=$?
  if [ $rc = 0 ]; then ID=$(cat "$T/id"); BLOCK=$(cat "$T/block"); fi
  rm -rf "$T"; return $rc
}
SERVER_ARGS="--standalone"
if curl -sf --max-time 2 http://127.0.0.1:4096/global/health > /dev/null 2>&1; then SERVER_ARGS="--server http://127.0.0.1:4096"; fi
echo "Modus: $SERVER_ARGS, Agent: $AGENT, höchstens $MAXP Durchgänge" | tee -a "$LOG"
declare -A TRY; SKIP=""
for n in $(seq 1 "$MAXP"); do
  check_hash
  if ! next_item; then echo "Keine offenen Arbeitspakete mehr."; break; fi
  TRY[$ID]=$(( ${TRY[$ID]:-0} + 1 ))
  if [ "${TRY[$ID]}" -gt 3 ]; then echo "Überspringe $ID nach 3 Versuchen (von Hand prüfen)."; SKIP="$SKIP,$ID"; continue; fi
  echo "=== [$NAME] Arbeitspaket $ID, Versuch ${TRY[$ID]}, Durchgang $n/$MAXP  $(date +%T) ===" | tee -a "$LOG"
  PROMPT="Arbeitspaket $ID. Der Punkt steht in FEEDBACK.md bzw. TICKETS.md des Projektordners. Wortlaut:
$BLOCK
Bearbeite NUR dieses Arbeitspaket gemäß deinem Workflow. Commit-Präfix: '$ID:'."
  opencode run $SERVER_ARGS --auto --thinking --agent "$AGENT" --title "$NAME $ID" "$PROMPT" 2>&1 | tee -a "$LOG"
  RC=${PIPESTATUS[0]}
  echo "=== Agent beendet, Exit-Code $RC ===" | tee -a "$LOG"
  if [ "$RC" != 0 ]; then
    printf '\a\a\a'; echo "Agent mit Fehler beendet (z. B. Request-Limit)." | tee -a "$LOG"
    if [ -x "$FRITZ_PY" ] && [ -f "$HOME/.config/fritz.env" ] && [ -f "$FRITZ_SCRIPT" ] && "$FRITZ_PY" "$FRITZ_SCRIPT"; then sleep 20
    else read -r -p "Neue IP manuell anfordern, dann Enter (Strg+C = Abbruch): " _; fi
  fi
done
echo "=== Abschlussprüfung ===" | tee -a "$LOG"
VOUT=$(final_verify 2>&1); VRC=$?
echo "$VOUT" | tee -a "$LOG"
if [ $VRC = 0 ]; then printf '\a'; echo "FERTIG: Abnahme bestanden. Jetzt selbst auf dem Zielgerät prüfen."; exit 0; fi
echo "Noch Lücken (oder Durchgangsgrenze erreicht). Blockierte/übersprungene Punkte in FEEDBACK.md prüfen."; exit 1
