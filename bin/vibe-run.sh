#!/usr/bin/env bash
# Allgemeiner Paket-Läufer. Aufruf: vibe-run.sh <projektordner> [agent] [modell]
# Kostenbremse: MAX_PACKAGES in .vibe/project.env (oder Umgebungsvariable
# VIBE_MAX_PACKAGES) begrenzt die Zahl der Durchgänge; MAX_RETRIES begrenzt die
# Wiederholungen je Arbeitspaket.
#
# V-015: Jeder Lauf hat eine eigene ID, ein eigenes Lauf- und Prüfprotokoll und
# einen eigenen Eintrag im Laufregister. Die Abschlussprüfung richtet sich nach
# dem Projekttyp; ein Nicht-Android-Projekt braucht keine Android-Abnahmedateien
# und wird nie still mit dem Android-Prüfskript geprüft.
P="$(cd "${1:?Projektordner}" && pwd)"
# Installations-, Laufzeit- und Serverpfade vor dem Einlesen der Projektdatei
# festhalten: .vibe/project.env beschreibt das Projekt, nicht die vibe-Pfade.
VIBE_ROOT="${VIBE:?VIBE nicht gesetzt}"
INSTALL="${VIBE_INSTALL:-$VIBE_ROOT/_toolchain}"
RUNTIME="${VIBE_RUNTIME:-$VIBE_ROOT/_logs}"
OPENCODE_PORT="${VIBE_OPENCODE_PORT:-4096}"
if ! [[ "$OPENCODE_PORT" =~ ^[0-9]+$ ]] || [ "$OPENCODE_PORT" -lt 1 ] || [ "$OPENCODE_PORT" -gt 65535 ]; then
  echo "ABBRUCH: VIBE_OPENCODE_PORT muss eine Zahl zwischen 1 und 65535 sein." >&2
  exit 2
fi
V="$INSTALL/verify"
BIN="$INSTALL/bin"
RUNS_PY="$BIN/vibe_runs.py"
mkdir -p "$RUNTIME"
# F19: Der gemeinsame opencode-Server ist mit Basic-Auth geschützt. Das
# Kennwort steht in der Laufzeitdatei und wird nur als Umgebungsvariable an
# opencode und als curl-Anmeldedaten verwendet, nie als sichtbares Argument.
PASSWORD_FILE="$RUNTIME/opencode.password"
CURL_AUTH=()
if [ -r "$PASSWORD_FILE" ] && [ -s "$PASSWORD_FILE" ]; then
  OPENCODE_SERVER_PASSWORD="$(cat "$PASSWORD_FILE")"
  export OPENCODE_SERVER_PASSWORD
  CURL_AUTH=(-u "opencode:$OPENCODE_SERVER_PASSWORD")
fi
# opencode v2 meldet sich unter /api/info; /global/health bleibt nur als
# Rückfall für ältere Installationen ohne Kennwort. Mit Kennwort wird der alte
# Endpunkt nicht geprüft, weil er auch ohne Anmeldung eine HTML-Seite liefert.
server_is_up() {
  if curl -sf --max-time 2 "${CURL_AUTH[@]}" \
      "http://127.0.0.1:$OPENCODE_PORT/api/info" > /dev/null 2>&1; then
    return 0
  fi
  [ "${#CURL_AUTH[@]}" -eq 0 ] || return 1
  curl -sf --max-time 2 "http://127.0.0.1:$OPENCODE_PORT/global/health" > /dev/null 2>&1
}
# Laufschlüssel: bin/vibe übergibt ihn als VIBE_LOGNAME. Ein direkt gestarteter
# Lauf fragt das Register nach einem kollisionsfreien Schlüssel und fällt ohne
# Register auf den Verzeichnisnamen zurück.
NAME="${VIBE_LOGNAME:-}"
if [ -z "$NAME" ] && [ -f "$RUNS_PY" ]; then
  NAME="$(python3 "$RUNS_PY" key "$P" "$RUNTIME" 2>/dev/null || true)"
fi
if [ -z "$NAME" ]; then
  NAME="$(basename "$P" | tr -c 'A-Za-z0-9_\n-' '_')"
fi
LOG="$RUNTIME/$NAME.log"
VLOG="$RUNTIME/$NAME.verify.log"
PAUSE_FLAG="$RUNTIME/$NAME.pause-after"
RUN_ID="${VIBE_RUN_ID:-}"
RUN_SESSION="${VIBE_SESSION:-vibe-$NAME}"
cd "$P" || exit 1
[ -f .vibe/project.env ] && set -a && . ./.vibe/project.env && set +a
AGENT="${2:-${AGENT:-}}"
if [ -z "$AGENT" ]; then
  echo "ABBRUCH: Kein Agent angegeben (2. Argument oder AGENT in .vibe/project.env)." | tee -a "$LOG"
  exit 2
fi
if ! [[ "$AGENT" =~ ^[A-Za-z0-9][A-Za-z0-9_-]*$ ]]; then
  echo "ABBRUCH: Agentenname ungültig (erlaubt: Buchstaben, Ziffern, _ und -)." | tee -a "$LOG"
  exit 2
fi
# F17: Eine Modellüberschreibung aus der Projektansicht wird unverändert an
# opencode run übergeben. Sie wird nie über eine Shell ausgewertet.
MODEL="${3:-${VIBE_MODEL:-}}"
MODEL_ARGS=()
if [ -n "$MODEL" ]; then
  if ! [[ "$MODEL" =~ ^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$ ]]; then
    echo "ABBRUCH: Modellangabe ungültig (erlaubt: Buchstaben, Ziffern, . _ : / @ + -)." | tee -a "$LOG"
    exit 2
  fi
  MODEL_ARGS=(--model "$MODEL")
fi
MAXP="${VIBE_MAX_PACKAGES:-${MAX_PACKAGES:-80}}"
if ! [[ "$MAXP" =~ ^[0-9]+$ ]]; then
  echo "ABBRUCH: MAX_PACKAGES muss eine Zahl sein." | tee -a "$LOG"
  exit 2
fi
MAXR="${MAX_RETRIES:-2}"
if ! [[ "$MAXR" =~ ^[0-9]+$ ]]; then
  echo "ABBRUCH: MAX_RETRIES muss eine Zahl sein." | tee -a "$LOG"
  exit 2
fi
TRIES_PER_ITEM=$((MAXR + 1))
# Hinweis an den Agenten (F16): Rückfragen erscheinen im Dashboard; ohne
# Antwort im Zeitlimit bleibt die Frage offen und wird später fortgesetzt.
# Ist der autonome Modus aktiv, entscheidet der Agent selbst (auch wenn der
# Nutzer ihn während des Wartens einschaltet) und dokumentiert die Entscheidung.
QUESTION_HINT='Wenn eine fachliche Entscheidung offen ist, stelle eine Rückfrage mit vibe ask "Frage" --option "A" --option "B"; sie erscheint im Dashboard. Ohne Antwort im Zeitlimit endet der Befehl mit Exit-Code 3, die Frage bleibt offen; setze danach mit vibe ask --wait <id> fort. Im autonomen Modus (vibe autonomous on <projekt>) oder wenn der Nutzer ihn während des Wartens einschaltet, entscheidest du selbst und dokumentierst die Entscheidung mit vibe answer <id> --text "..." --by agent.'
# Ein zu großes Protokoll wird vor dem Start rotiert (max. 5 MiB, 3 Archive).
if [ -f "$RUNS_PY" ]; then
  python3 "$RUNS_PY" rotate "$LOG" >/dev/null 2>&1 || true
  python3 "$RUNS_PY" rotate "$VLOG" >/dev/null 2>&1 || true
fi
register_start() {
  [ -f "$RUNS_PY" ] || return 0
  if [ -n "$RUN_ID" ]; then
    python3 "$RUNS_PY" start --runtime "$RUNTIME" --project "$P" --name "$NAME" \
      --key "$NAME" --agent "$AGENT" --session "$RUN_SESSION" --log "$LOG" \
      --verify-log "$VLOG" --id "$RUN_ID" --state running >>"$LOG" 2>&1 || true
  else
    RUN_ID="$(python3 "$RUNS_PY" start --runtime "$RUNTIME" --project "$P" --name "$NAME" \
      --key "$NAME" --agent "$AGENT" --session "$RUN_SESSION" --log "$LOG" \
      --verify-log "$VLOG" --state running 2>>"$LOG")" || RUN_ID=""
  fi
  return 0
}
register_finish() {
  [ -f "$RUNS_PY" ] && [ -n "$RUN_ID" ] || return 0
  python3 "$RUNS_PY" finish --runtime "$RUNTIME" --id "$RUN_ID" \
    --exit-code "$1" --state "$2" >>"$LOG" 2>&1 || true
  return 0
}
HASHFILE="$HOME/.config/schreibfuchs-verify.sha"
# Die Android-Abnahmedateien gelten nur für Android-Projekte. Ein generisches
# Projekt wird ohne sie ausgeführt und geprüft.
check_hash() {
  [ "${TYPE:-}" = "android" ] || return 0
  [ -f "$HASHFILE" ] && (cd "$V" && sha256sum -c "$HASHFILE" --quiet) || { echo "ABBRUCH: Abnahme-Dateien fehlen oder wurden verändert."; exit 3; }
}
# Typabhängiger Prüfadapter: eigener Befehl des Projekts, sonst die
# Android-Abnahme — und die ausschließlich für Android-Projekte.
final_verify() {
  local CMD="${VERIFY_FULL:-}"
  if [ -n "$CMD" ] && [[ "$CMD" == *TODO* ]]; then
    echo "ABBRUCH: VERIFY_FULL ist nur ein Platzhalter (TODO); es wird keine Prüfung ausgeführt."
    return 3
  fi
  if [ -n "$CMD" ]; then bash -lc "$CMD"; return $?; fi
  if [ "${TYPE:-}" = "android" ] && [ -f "$V/verify.sh" ]; then bash "$V/verify.sh" "$P" full; return $?; fi
  echo "FEHLT: keine VERIFY_FULL-Prüfung in .vibe/project.env definiert (und keine Android-Abnahme für TYPE=${TYPE:-generic})."
  return 3
}
next_item() {
  local T; T="$(mktemp -d)"
  flock /tmp/vibe-next.lock bash -c 'python3 "$1" "$2" "$3" > /dev/null && cp /tmp/next_id "$4/id" && cp /tmp/next_block "$4/block"' _ "$V/next_item.py" "$P" "$SKIP" "$T"
  local rc=$?
  if [ $rc = 0 ]; then ID=$(cat "$T/id"); BLOCK=$(cat "$T/block"); fi
  rm -rf "$T"; return $rc
}
SERVER_ARGS="--standalone"
SANDBOX_WRAP=(); SANDBOX_STATE=off
# Eine einzige Quelle für die Auswertung von SANDBOX: das Sandbox-Modul.
# Dadurch startet kein Lauf ungeschützt, nur weil der Wert anders geschrieben
# ist (z. B. TRUE, yes, 1).
if [ -f "$BIN/vibe_sandbox.py" ]; then
  SANDBOX_VERDICT=$(python3 "$BIN/vibe_sandbox.py" "$P" --enabled 2>>"$LOG")
  SANDBOX_RC=$?
  case "$SANDBOX_RC:$SANDBOX_VERDICT" in
    0:on) SANDBOX_STATE=on ;;
    1:off) SANDBOX_STATE=off ;;
    *)
      echo "ABBRUCH: Sandbox-Zustand nicht lesbar (Exit $SANDBOX_RC, Antwort '$SANDBOX_VERDICT')." | tee -a "$LOG"
      exit 2
      ;;
  esac
elif [ -n "${SANDBOX:-}" ] && [ "${SANDBOX:-off}" != "off" ]; then
  echo "ABBRUCH: SANDBOX ist in .vibe/project.env gesetzt, aber $BIN/vibe_sandbox.py fehlt. Der Lauf startet nicht ungeschützt." | tee -a "$LOG"
  exit 2
fi
if [ "$SANDBOX_STATE" = "on" ]; then
  # Eine Sandbox muss den gesamten Agenten inklusive Werkzeugausführung
  # enthalten. Deshalb immer ein privater Server im selben bubblewrap-Prozess;
  # ein vorhandener gemeinsamer Server würde die Werkzeuge außerhalb der
  # Sandbox ausführen.
  SERVER_ARGS="--standalone"
  python3 "$BIN/vibe_sandbox.py" "$P" --check 2>&1 | tee -a "$LOG"
  if [ "${PIPESTATUS[0]}" != 0 ]; then
    echo "ABBRUCH: Sandbox ist eingeschaltet, aber nicht startbar. Der Agent läuft nicht ohne Sandbox." | tee -a "$LOG"
    exit 2
  fi
  SANDBOX_WRAP=(python3 "$BIN/vibe_sandbox.py" "$P" --)
elif server_is_up; then SERVER_ARGS="--server http://127.0.0.1:$OPENCODE_PORT"; fi
register_start
echo "Lauf: ${RUN_ID:-ohne Register}, Modus: $SERVER_ARGS, Agent: $AGENT, Sandbox: $SANDBOX_STATE, höchstens $MAXP Durchgänge, höchstens $MAXR Wiederholungen je Paket" | tee -a "$LOG"
# F19: opencode liefert mit --format json Ereignisse. Der Filter macht daraus
# menschenlesbare Zeilen (Grundlage für Syntax-Highlighting) und erfasst
# Subagenten samt Ausgabe in <log>.state.json. Fehlt das Modul, bleibt die
# Ausgabe unverändert (kein stiller Abbruch des Laufs).
STREAM_FILTER=(cat)
if [ -f "$RUNS_PY" ]; then
  STREAM_FILTER=(python3 "$RUNS_PY" stream --state "$LOG.state.json")
fi
PAUSED=0; LAST_ID=""
declare -A TRY; SKIP=""
for n in $(seq 1 "$MAXP"); do
  check_hash
  if [ -f "$PAUSE_FLAG" ]; then
    rm -f "$PAUSE_FLAG"; PAUSED=1
    if [ -n "$LAST_ID" ]; then echo "PAUSE: Arbeitspaket $LAST_ID beendet. Kein neues Paket gestartet." | tee -a "$LOG"
    else echo "PAUSE: Pause war vor dem Start angefordert. Kein Arbeitspaket gestartet." | tee -a "$LOG"; fi
    break
  fi
  if ! next_item; then echo "Keine offenen Arbeitspakete mehr."; break; fi
  TRY[$ID]=$(( ${TRY[$ID]:-0} + 1 ))
  if [ "${TRY[$ID]}" -gt "$TRIES_PER_ITEM" ]; then
    echo "Überspringe $ID nach $TRIES_PER_ITEM Versuchen ($MAXR Wiederholungen, Wiederholungslimit erreicht, von Hand prüfen)." | tee -a "$LOG"
    SKIP="$SKIP,$ID"; continue
  fi
  echo "=== [$NAME] Arbeitspaket $ID, Versuch ${TRY[$ID]}/$TRIES_PER_ITEM, Durchgang $n/$MAXP  $(date +%T) ===" | tee -a "$LOG"
  PROMPT="Arbeitspaket $ID. Der Punkt steht in FEEDBACK.md bzw. TICKETS.md des Projektordners. Wortlaut:
$BLOCK
Bearbeite NUR dieses Arbeitspaket gemäß deinem Workflow. Commit-Präfix: '$ID:'.
$QUESTION_HINT"
  "${SANDBOX_WRAP[@]}" opencode run $SERVER_ARGS --format json --auto --thinking --agent "$AGENT" "${MODEL_ARGS[@]}" --title "$NAME $ID" "$PROMPT" 2>&1 | "${STREAM_FILTER[@]}" | tee -a "$LOG"
  RC=${PIPESTATUS[0]}
  echo "=== Agent beendet, Exit-Code $RC ===" | tee -a "$LOG"
  LAST_ID="$ID"
  if [ "$RC" != 0 ]; then
    printf '\a\a\a'; echo "Agent mit Fehler beendet (z. B. Request-Limit)." | tee -a "$LOG"
    # Die Automatik ist standardmäßig aus; 'fritz auto' fordert nur bei
    # ausdrücklich gespeicherter Automatik eine neue IP an. Ein Lauf wartet
    # nicht auf eine Eingabe, wenn niemand an einem Terminal sitzt.
    # F18: Der Projektname geht an die zentrale Steuerung; läuft bereits ein
    # Reconnect eines anderen Projekts, wird dessen Ergebnis übernommen und
    # dieser Lauf danach fortgesetzt.
    FRITZ_OUT="$(VIBE_PROJECT="$P" python3 "$BIN/vibe" fritz auto 2>&1)"; FRITZ_RC=$?
    if [ -n "$FRITZ_OUT" ]; then printf '%s\n' "$FRITZ_OUT" | tee -a "$LOG"; fi
    if [ "$FRITZ_RC" = 0 ]; then
      echo "Zentraler Reconnect abgeschlossen; der Lauf wird nach kurzer Wartezeit fortgesetzt." | tee -a "$LOG"
      sleep 20
    elif [ -t 0 ]; then read -r -p "Neue IP manuell anfordern, dann Enter (Strg+C = Abbruch): " _
    else echo "Keine neue IP angefordert; der Lauf wird fortgesetzt." | tee -a "$LOG"; fi
  fi
done
if [ "$PAUSED" != 1 ] && [ -f "$PAUSE_FLAG" ]; then
  rm -f "$PAUSE_FLAG"; PAUSED=1
  echo "PAUSE: Pause angefordert. Kein weiteres Arbeitspaket gestartet." | tee -a "$LOG"
fi
if [ "$PAUSED" = 1 ]; then
  register_finish 0 paused
  printf '\a'; echo "Angehalten auf Wunsch. Die Abschlussprüfung wurde nicht ausgeführt. Nächster Start: vibe run $NAME" | tee -a "$LOG"; exit 0
fi
echo "=== Abschlussprüfung ===" | tee -a "$LOG" "$VLOG"
VOUT=$(final_verify 2>&1); VRC=$?
printf '%s\n' "$VOUT" | tee -a "$LOG" "$VLOG"
if [ "$VRC" = 0 ]; then
  register_finish 0 finished
  printf '\a'; echo "FERTIG: Abnahme bestanden. Jetzt selbst auf dem Zielgerät prüfen." | tee -a "$LOG"; exit 0
fi
register_finish "$VRC" failed
echo "Noch Lücken (oder Durchgangsgrenze erreicht), Prüfung Exit-Code $VRC. Blockierte/übersprungene Punkte in FEEDBACK.md prüfen." | tee -a "$LOG"; exit "$VRC"
