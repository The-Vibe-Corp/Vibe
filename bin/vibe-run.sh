#!/usr/bin/env bash
# Allgemeiner Paket-Läufer. Aufruf: vibe-run.sh <projektordner> [agent] [modell]
# Kostenbremse: MAX_PACKAGES in .vibe/project.env (oder Umgebungsvariable
# VIBE_MAX_PACKAGES) begrenzt die Zahl der bearbeiteten Pakete; MAX_RETRIES
# begrenzt die Wiederholungen je Arbeitspaket. Wiederholungen zählen nicht als
# eigenes Paket.
#
# V-015: Jeder Lauf hat eine eigene ID, ein eigenes Lauf- und Prüfprotokoll und
# einen eigenen Eintrag im Laufregister. Die Abschlussprüfung richtet sich nach
# dem Projekttyp; ein Nicht-Android-Projekt braucht keine Android-Abnahmedateien
# und wird nie still mit dem Android-Prüfskript geprüft.
#
# Abschluss-Gates: Der Lauf startet nur auf einem sauberen Git-Integrationsstand
# (Preflight). Jedes Paket läuft in einer eigenen Arbeitskopie unter
# $VIBE_RUNTIME/worktrees/<ID>. Erst wenn Commit, Ticket-Nachweis,
# Feature-Dokumentation, Review mit "Verdict: PASS", saubere Arbeitskopie und
# Paketprüfung vorliegen, wird der Paketbranch per Fast-Forward gemergt und die
# Arbeitskopie entfernt. Quota- und Anmeldefehler halten sofort an; Netz- und
# sonstige Fehler werden begrenzt wiederholt. Fehlt der Test- oder Review-Agent,
# ist das Paket blockiert.
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
PACKAGES_PY="$BIN/vibe_packages.py"
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
REPORT="$RUNTIME/$NAME.report.txt"
RUN_ID="${VIBE_RUN_ID:-}"
RUN_SESSION="${VIBE_SESSION:-vibe-$NAME}"
cd "$P" || exit 1
[ -f .vibe/project.env ] && set -a && . ./.vibe/project.env && set +a
if [ ! -f "$PACKAGES_PY" ]; then
  echo "ABBRUCH: $PACKAGES_PY fehlt. Installation aktualisieren (Setup --update)." | tee -a "$LOG"
  exit 2
fi
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
# Harness-Auswahl (AP04): Ohne vibe_harness.py bleibt der bisherige direkte
# opencode-Pfad erhalten (ältere Installationen und Prüf-Attrappen). Der
# Zustandsordner enthält harness.json; VIBE_HARNESS überschreibt ihn für
# genau diesen Lauf.
STATE="${VIBE_STATE:-$INSTALL}"
HARNESS=opencode
HARNESS_CLI="$BIN/vibe_harness.py"
if [ -f "$HARNESS_CLI" ]; then
  if ! HARNESS="$(python3 "$HARNESS_CLI" selected --state "$STATE" 2>>"$LOG")"; then
    echo "ABBRUCH: Harness-Auswahl in $STATE/harness.json konnte nicht gelesen werden." | tee -a "$LOG"
    exit 2
  fi
  case "$HARNESS" in
    opencode|pi) ;;
    *)
      echo "ABBRUCH: Unbekannter Harness '$HARNESS' (erlaubt: opencode, pi)." | tee -a "$LOG"
      exit 2
      ;;
  esac
fi
if [ "$HARNESS" = "pi" ] && [ ! -f "$HARNESS_CLI" ]; then
  echo "ABBRUCH: Harness pi gewählt, aber $HARNESS_CLI fehlt. Installation aktualisieren (Setup --update)." | tee -a "$LOG"
  exit 2
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
RETRY_DELAY="${VIBE_RETRY_DELAY:-0}"
if ! [[ "$RETRY_DELAY" =~ ^[0-9]+$ ]]; then
  echo "ABBRUCH: VIBE_RETRY_DELAY muss eine Zahl (Sekunden) sein." | tee -a "$LOG"
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
# Projektlokaler Auswahlstand: kein globales /tmp, keine Kollision zwischen
# Projekten. Die Datei liegt unter .vibe/tmp und wird über .git/info/exclude
# aus dem Git-Status herausgehalten.
select_item() {
  local state="$P/.vibe/tmp/next-package.json"
  if ! python3 "$PACKAGES_PY" select --project "$P" --state "$state" --skip "$SKIP" >>"$LOG" 2>&1; then
    return 1
  fi
  eval "$(python3 - "$state" <<'PY'
import json
import shlex
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
print("ID=" + shlex.quote(data["id"]))
print("BLOCK=" + shlex.quote(data["block"]))
print("SOURCE=" + shlex.quote(data["source"]))
PY
)"
  return 0
}
# Jedes Paket läuft in einer eigenen Arbeitskopie unter dem Laufzeitordner,
# nie unter /tmp. Der Branch wird vom aktuellen Integrationsstand abgezweigt.
create_worktree() {
  local safe_name safe_id
  safe_name="$(printf '%s' "$NAME" | tr -c 'A-Za-z0-9_.-' '-')"
  safe_id="$(printf '%s' "$ID" | tr -c 'A-Za-z0-9_.-' '-')"
  WT_ROOT="$RUNTIME/worktrees"
  mkdir -p "$WT_ROOT" || return 1
  WT="$(mktemp -d "$WT_ROOT/${safe_name}-${safe_id}-XXXXXX")" || return 1
  BRANCH="vibe/${safe_name}-${safe_id}-$(date +%s)-$$"
  git -C "$P" worktree add --quiet -b "$BRANCH" "$WT" "$PACKAGE_BASE" >>"$LOG" 2>&1 || return 1
  return 0
}
run_agent() {
  local wrap=()
  if [ "$SANDBOX_STATE" = "on" ]; then
    wrap=(python3 "$BIN/vibe_sandbox.py" "$WT" --)
  fi
  (
    cd "$WT" || exit 1
    if [ "$HARNESS" = "pi" ]; then
      local args=(python3 "$HARNESS_CLI" run --harness pi --project "$WT" --agent "$AGENT" --title "$NAME $ID" --prompt "$PROMPT")
      [ -n "$MODEL" ] && args+=(--model "$MODEL")
      [ -n "${VIBE_AGENTS_DIR:-}" ] && args+=(--agents-dir "$VIBE_AGENTS_DIR")
      "${wrap[@]}" "${args[@]}" 2>&1 | tee -a "$LOG"
      exit "${PIPESTATUS[0]}"
    fi
    "${wrap[@]}" opencode run $SERVER_ARGS --format json --auto --thinking --agent "$AGENT" "${MODEL_ARGS[@]}" --title "$NAME $ID" "$PROMPT" 2>&1 | "${STREAM_FILTER[@]}" | tee -a "$LOG"
    exit "${PIPESTATUS[0]}"
  )
}
run_package_tests() {
  local cmd="${VERIFY_PACKAGE:-${VERIFY_FULL:-}}"
  echo "=== Paketprüfung für $ID ===" | tee -a "$LOG"
  ( cd "$WT" && bash -lc "$cmd" ) >>"$LOG" 2>&1
}
gate_ok() {
  local out rc
  out="$(python3 "$PACKAGES_PY" gate --project "$WT" --id "$ID" --base "$PACKAGE_BASE" 2>&1)"
  rc=$?
  printf '%s\n' "$out" | tee -a "$LOG"
  return $rc
}
merge_and_cleanup() {
  if ! git -C "$P" merge --ff-only "$BRANCH" >>"$LOG" 2>&1; then
    echo "FEHLT: Merge von $BRANCH nach $BASE_BRANCH fehlgeschlagen." | tee -a "$LOG"
    return 1
  fi
  # Nur gemergte Arbeitskopien und Branches werden entfernt. Blockierte
  # Arbeitskopien bleiben zur Diagnose liegen.
  if ! git -C "$P" worktree remove --force "$WT" >>"$LOG" 2>&1; then
    echo "WARNUNG: Arbeitskopie $WT konnte nicht entfernt werden." | tee -a "$LOG"
  fi
  if ! git -C "$P" branch -d "$BRANCH" >>"$LOG" 2>&1; then
    echo "WARNUNG: Branch $BRANCH konnte nicht entfernt werden." | tee -a "$LOG"
  fi
  return 0
}
SERVER_ARGS="--standalone"
SANDBOX_STATE=off
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
elif server_is_up; then SERVER_ARGS="--server http://127.0.0.1:$OPENCODE_PORT"; fi
# Preflight: sauberer Git-Integrationsstand, verfügbare Test-/Review-Agenten
# und ein echter Paketprüfbefehl. Ohne diese Bedingungen startet kein Paket.
PREFLIGHT_OUT="$(python3 "$PACKAGES_PY" preflight --project "$P" \
  --agents-dir "${VIBE_AGENTS_DIR:-$HOME/.config/opencode/agents}" \
  --tester "${TESTER:-}" --reviewer "${REVIEWER:-}" 2>&1)"
PREFLIGHT_RC=$?
if [ "$PREFLIGHT_RC" != 0 ]; then
  printf '%s\n' "$PREFLIGHT_OUT" | tee -a "$LOG"
  echo "ABBRUCH: Preflight nicht bestanden. Es wurde kein Arbeitspaket gestartet." | tee -a "$LOG"
  register_finish 2 blocked
  exit 2
fi
BASE_BRANCH="$(git -C "$P" symbolic-ref --quiet --short HEAD)"
git -C "$P" worktree prune >>"$LOG" 2>&1 || true
register_start
if [ "$HARNESS" = "pi" ]; then RUN_MODE="Pi --print"; else RUN_MODE="$SERVER_ARGS"; fi
echo "Lauf: ${RUN_ID:-ohne Register}, Harness: $HARNESS, Modus: $RUN_MODE, Agent: $AGENT, Sandbox: $SANDBOX_STATE, höchstens $MAXP Pakete, höchstens $MAXR Wiederholungen je Paket" | tee -a "$LOG"
# F19: opencode liefert mit --format json Ereignisse. Der Filter macht daraus
# menschenlesbare Zeilen (Grundlage für Syntax-Highlighting) und erfasst
# Subagenten samt Ausgabe in <log>.state.json. Fehlt das Modul, bleibt die
# Ausgabe unverändert (kein stiller Abbruch des Laufs).
STREAM_FILTER=(cat)
if [ -f "$RUNS_PY" ]; then
  STREAM_FILTER=(python3 "$RUNS_PY" stream --state "$LOG.state.json")
fi
PAUSED=0; LAST_ID=""; STOP=0; PACKAGES=0; SKIP=""
CLOSED=(); BLOCKED_IDS=(); BLOCKED_REPORT=(); BLOCK_REASON=""
record_block() {
  BLOCKED_IDS+=("$1")
  BLOCKED_REPORT+=("$1 ($2)")
}
report() {
  local status_json
  OPEN_LIST="keine"; BLOCKED_LIST="keine"; DONE_LIST="keine"
  status_json="$(python3 "$PACKAGES_PY" status --project "$P" 2>>"$LOG")"
  eval "$(printf '%s' "$status_json" | python3 -c '
import json
import shlex
import sys

data = json.load(sys.stdin)
for key in ("open", "blocked", "done"):
    value = ", ".join(data.get(key, [])) or "keine"
    print(key.upper() + "_LIST=" + shlex.quote(value))
' 2>>"$LOG")"
  local open_filtered="" id skip_flag blocked
  if [ "${OPEN_LIST:-keine}" != "keine" ]; then
    IFS=',' read -ra OPEN_ARR <<< "${OPEN_LIST}"
    for id in "${OPEN_ARR[@]}"; do
      id="$(printf '%s' "$id" | tr -d ' ')"
      [ -z "$id" ] && continue
      skip_flag=0
      for blocked in "${BLOCKED_IDS[@]}"; do
        [ "$id" = "$blocked" ] && skip_flag=1
      done
      [ "$skip_flag" = 1 ] && continue
      open_filtered="${open_filtered:+$open_filtered, }$id"
    done
  fi
  open_filtered="${open_filtered:-keine}"
  {
    echo "=== Abschlussbericht ==="
    if [ "${#CLOSED[@]}" -eq 0 ]; then
      echo "Geschlossen: keine"
    else
      for id in "${CLOSED[@]}"; do echo "Geschlossen: $id"; done
    fi
    if [ "${#BLOCKED_REPORT[@]}" -eq 0 ]; then
      echo "Blockiert: keine"
    else
      for blocked in "${BLOCKED_REPORT[@]}"; do echo "Blockiert: $blocked"; done
    fi
    echo "Offen: $open_filtered"
    [ -n "$BLOCK_REASON" ] && echo "Grund: $BLOCK_REASON"
    echo "Integrationsbranch: ${BASE_BRANCH:-unbekannt} @ $(git -C "$P" rev-parse --short HEAD 2>/dev/null || echo unbekannt)"
  } | tee -a "$LOG" "$REPORT"
}
while [ "$PACKAGES" -lt "$MAXP" ] && [ "$STOP" = 0 ]; do
  check_hash
  if [ -f "$PAUSE_FLAG" ]; then
    rm -f "$PAUSE_FLAG"; PAUSED=1
    if [ -n "$LAST_ID" ]; then echo "PAUSE: Arbeitspaket $LAST_ID beendet. Kein neues Paket gestartet." | tee -a "$LOG"
    else echo "PAUSE: Pause war vor dem Start angefordert. Kein Arbeitspaket gestartet." | tee -a "$LOG"; fi
    break
  fi
  if ! select_item; then echo "Keine offenen Arbeitspakete mehr." | tee -a "$LOG"; break; fi
  PACKAGES=$((PACKAGES + 1))
  PACKAGE_BASE="$(git -C "$P" rev-parse HEAD)"
  echo "=== [$NAME] Arbeitspaket $ID, Durchgang $PACKAGES/$MAXP  $(date +%T) ===" | tee -a "$LOG"
  if ! create_worktree; then
    BLOCK_REASON="Arbeitskopie für $ID konnte nicht angelegt werden."
    record_block "$ID" "$BLOCK_REASON"
    echo "BLOCKIERT: $BLOCK_REASON" | tee -a "$LOG"
    STOP=1; break
  fi
  PROMPT="Arbeitspaket $ID. Der Punkt steht in $SOURCE des Projektordners. Wortlaut:
$BLOCK
Bearbeite NUR dieses Arbeitspaket gemäß deinem Workflow. Du arbeitest in der isolierten Arbeitskopie $WT auf dem Branch $BRANCH; der Integrationsstand $P bleibt unberührt. Committe dort mit dem Präfix '$ID:'.
Vor dem Abschluss müssen im Paketbranch vorliegen: ein Commit mit Präfix '$ID:', das Ticket in TICKETS.md bzw. FEEDBACK.md auf [x] mit Commit:/Test:, docs/features/$ID.md und ein Review unter docs/reviews/$ID-review-*.md mit 'Verdict: PASS'. Die Arbeitskopie muss sauber sein. Sonst gilt das Paket als BLOCKIERT und der Lauf hält an.
$QUESTION_HINT"
  ATTEMPT=0
  PACKAGE_DONE=0
  while [ "$ATTEMPT" -lt "$TRIES_PER_ITEM" ]; do
    ATTEMPT=$((ATTEMPT + 1))
    echo "--- Versuch $ATTEMPT/$TRIES_PER_ITEM für $ID in $WT ---" | tee -a "$LOG"
    LOG_START_LINE="$(wc -l < "$LOG" 2>/dev/null || echo 0)"
    run_agent
    RC=$?
    echo "=== Agent beendet, Exit-Code $RC ===" | tee -a "$LOG"
    if [ "$RC" = 0 ]; then
      if ! run_package_tests; then
        BLOCK_REASON="Pakettests für $ID sind nicht grün."
        record_block "$ID" "$BLOCK_REASON"
        echo "BLOCKIERT: $BLOCK_REASON" | tee -a "$LOG"
        STOP=1; break
      fi
      if ! gate_ok; then
        BLOCK_REASON="Abschlussschranke für $ID nicht erfüllt."
        record_block "$ID" "$BLOCK_REASON"
        STOP=1; break
      fi
      if ! merge_and_cleanup; then
        BLOCK_REASON="Merge für $ID fehlgeschlagen."
        record_block "$ID" "$BLOCK_REASON"
        echo "BLOCKIERT: $BLOCK_REASON" | tee -a "$LOG"
        STOP=1; break
      fi
      CLOSED+=("$ID")
      PACKAGE_DONE=1
      break
    fi
    CLASS="$(python3 "$PACKAGES_PY" classify --exit-code "$RC" --log "$LOG" --since "$LOG_START_LINE" 2>>"$LOG")"
    case "$CLASS" in
      quota)
        BLOCK_REASON="Quota/Kontingent bei $ID; der Lauf hält sofort an."
        record_block "$ID" "$BLOCK_REASON"
        echo "BLOCKIERT: $BLOCK_REASON" | tee -a "$LOG"
        STOP=1; break
        ;;
      auth)
        BLOCK_REASON="Anmeldung/Autorisierung bei $ID fehlgeschlagen; der Lauf hält sofort an."
        record_block "$ID" "$BLOCK_REASON"
        echo "BLOCKIERT: $BLOCK_REASON" | tee -a "$LOG"
        STOP=1; break
        ;;
      *)
        printf '\a\a\a'; echo "Agent mit Fehler beendet (Fehlerklasse '$CLASS')." | tee -a "$LOG"
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
        if [ "$ATTEMPT" -ge "$TRIES_PER_ITEM" ]; then
          echo "Überspringe $ID nach $TRIES_PER_ITEM Versuchen ($MAXR Wiederholungen, Wiederholungslimit erreicht, von Hand prüfen)." | tee -a "$LOG"
          record_block "$ID" "Agentenfehler ($CLASS)"
          SKIP="$SKIP,$ID"
          break
        fi
        echo "Wiederhole $ID nach Fehlerklasse '$CLASS' (Versuch $ATTEMPT/$TRIES_PER_ITEM)." | tee -a "$LOG"
        if [ "$RETRY_DELAY" -gt 0 ]; then sleep "$RETRY_DELAY"; fi
        ;;
    esac
  done
  LAST_ID="$ID"
done
if [ "$STOP" = 0 ] && [ "$PAUSED" != 1 ] && [ -f "$PAUSE_FLAG" ]; then
  rm -f "$PAUSE_FLAG"; PAUSED=1
  echo "PAUSE: Pause angefordert. Kein weiteres Arbeitspaket gestartet." | tee -a "$LOG"
fi
if [ "$STOP" = 1 ]; then
  report
  register_finish 1 blocked
  echo "ABBRUCH: Der Lauf ist blockiert. Siehe Abschlussbericht und Protokoll $LOG." | tee -a "$LOG"
  exit 1
fi
if [ "$PAUSED" = 1 ]; then
  report
  register_finish 0 paused
  printf '\a'; echo "Angehalten auf Wunsch. Die Abschlussprüfung wurde nicht ausgeführt. Nächster Start: vibe run $NAME" | tee -a "$LOG"; exit 0
fi
# Die Gesamtprüfung läuft ausschließlich auf einem sauberen Integrationsstand.
INTEGRATION_DIRTY="$(git -C "$P" status --porcelain)"
if [ -n "$INTEGRATION_DIRTY" ]; then
  BLOCK_REASON="Integrationsstand ist nicht sauber: $INTEGRATION_DIRTY"
  record_block "INTEGRATION" "$BLOCK_REASON"
  report
  register_finish 1 blocked
  echo "ABBRUCH: $BLOCK_REASON" | tee -a "$LOG"
  exit 1
fi
echo "=== Abschlussprüfung ===" | tee -a "$LOG" "$VLOG"
VOUT=$(final_verify 2>&1); VRC=$?
printf '%s\n' "$VOUT" | tee -a "$LOG" "$VLOG"
if [ "$VRC" = 0 ]; then
  report
  register_finish 0 finished
  printf '\a'; echo "FERTIG: Abnahme bestanden. Jetzt selbst auf dem Zielgerät prüfen." | tee -a "$LOG"; exit 0
fi
report
register_finish "$VRC" failed
echo "Noch Lücken (oder Durchgangsgrenze erreicht), Prüfung Exit-Code $VRC. Blockierte/übersprungene Punkte in FEEDBACK.md prüfen." | tee -a "$LOG"; exit "$VRC"
