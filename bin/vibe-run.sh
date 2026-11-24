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
# B17: Produktivpfade gehören ausschließlich in den UI-/Service-Prozess.
# Agenten und Prüfungen erhalten eine bereinigte Umgebung; Laufsteuerung wie
# VIBE_LOGNAME bleibt erhalten. Der Laufzeitordner wird dereferenziert, damit
# Sandbox-Bindungen und der Rückfrage-Hinweis denselben Pfad nennen.
# AP6 (T-BR1): VIBE_UI_BIND/VIBE_UI_PORT leitet vibe_paths aus ui.json ab; das
# Dashboard vererbt sie an den Läufer. Ungefiltert zwingen sie Testserver an
# die produktive LAN-Bindung. GITHUB_AUTO_MERGE
# kommt über `set -a` aus der Projektdatei; Prüfungen und Harnesses erwarten
# den Standard PR-only. HOME bleibt bewusst gesetzt: git-Identität und
# opencode-Daten brauchen es; die Home-Isolation gehört in die Test-Harnesses.
VIBE_CLEAN_ENV=(env -u VIBE -u VIBE_PROFILE -u VIBE_INSTALL -u VIBE_STATE -u VIBE_RUNTIME -u VIBE_CONFIG_FILE -u VIBE_AGENTS_DIR -u VIBE_UI_BIND -u VIBE_UI_PORT -u GITHUB_AUTO_MERGE)
RUNTIME="$(cd "$RUNTIME" && pwd -P)"
# F19: Der gemeinsame opencode-Server ist mit Basic-Auth geschützt. Das
# Kennwort steht in der Laufzeitdatei und wird nur als Umgebungsvariable an
# opencode und als curl-Anmeldedaten verwendet, nie als sichtbares Argument.
PASSWORD_FILE="$RUNTIME/opencode.password"
# F31: opencode v2.3 steuert den Basic-Auth des Servers auch über
# OPENCODE_PASSWORD, und ein geerbter Wert schlägt OPENCODE_SERVER_PASSWORD.
# Eine Alt-Belegung aus der Startumgebung (Dashboard/tmux) ließ den privaten
# Server deshalb dauerhaft 401 antworten. Das Kennwort kommt hier ausschließlich
# aus der Laufzeitdatei.
unset OPENCODE_PASSWORD
CURL_AUTH=()
HAS_SERVER_PASSWORD=0
if [ -r "$PASSWORD_FILE" ] && [ -s "$PASSWORD_FILE" ]; then
  OPENCODE_SERVER_PASSWORD="$(cat "$PASSWORD_FILE")"
  export OPENCODE_SERVER_PASSWORD
  CURL_AUTH=(-u "opencode:$OPENCODE_SERVER_PASSWORD")
  # B13: Eine Datei aus Leerzeichen/Nennzeichen gilt wie eine fehlende; nur
  # ein tatsächlich nichtleeres Kennwort erlaubt den privaten Server.
  if [ -n "${OPENCODE_SERVER_PASSWORD//[[:space:]]/}" ]; then
    HAS_SERVER_PASSWORD=1
  fi
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
# B13/AP1: Der private opencode-Server eines Laufs. Die Serverdatei ist die
# Übergabe an das Dashboard (Ziel, Kennwortdatei und Zielverzeichnis), das
# Protokoll hält die Serverausgabe getrennt vom Laufprotokoll, die PID-Datei
# dient dem Aufräumen.
SERVER_JSON="$LOG.server.json"
SERVER_LOG="$LOG.server.log"
SERVER_PID_FILE="$LOG.server.pid"
SERVER_FAILED_FILE="$LOG.server.failed"
rm -f -- "$SERVER_FAILED_FILE"
# B13: Endpunkt des zuletzt gestarteten privaten Servers aus der Serverdatei.
# Nur der vom Läufer selbst geschriebene Loopback-Endpunkt wird akzeptiert.
private_server_url() {
  python3 - "$SERVER_JSON" <<'PY' 2>/dev/null
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        data = json.load(handle)
except (OSError, ValueError):
    raise SystemExit(1)
url = data.get("url") if isinstance(data, dict) else None
if not isinstance(url, str) or not url.startswith("http://127.0.0.1:"):
    raise SystemExit(1)
print(url.rstrip("/"))
PY
}
# B13/AP1: Ein bereits laufender privater Server wird nur wiederverwendet,
# wenn er gesund ist UND für genau dieses Zielverzeichnis gestartet wurde.
# Die Serverdatei hält das mit realpath aufgelöste write_dir; fehlt sie (alte
# Serverdatei), gilt der Server als nicht passend und wird neu gestartet.
private_server_healthy() {
  local dir="$1" url
  [ -n "$dir" ] || return 1
  url="$(private_server_url)" || return 1
  [ -n "$url" ] || return 1
  curl -sf --max-time 2 -u "opencode:$OPENCODE_SERVER_PASSWORD" \
    "$url/api/info" > /dev/null 2>&1 || return 1
  python3 - "$SERVER_JSON" "$dir" <<'PY' > /dev/null 2>&1
import json
import os
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        data = json.load(handle)
except (OSError, ValueError):
    raise SystemExit(1)
if not isinstance(data, dict):
    raise SystemExit(1)
recorded = data.get("write_dir")
if not isinstance(recorded, str) or not recorded:
    raise SystemExit(1)
if os.path.realpath(recorded) != os.path.realpath(sys.argv[2]):
    raise SystemExit(1)
PY
}
private_free_port() {
  python3 - <<'PY'
import socket

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
}
private_server_file_write() {
  local url="$1" port="$2" dir="$3"
  python3 - "$SERVER_JSON" "$url" "$port" "$PASSWORD_FILE" "$dir" <<'PY'
import json
import os
import sys

path, url, port, password_file, directory = sys.argv[1:6]
if not directory:
    raise SystemExit(1)
data = {
    "url": url,
    "port": int(port),
    "password_file": password_file,
    "write_dir": os.path.realpath(directory),
}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(data, handle, ensure_ascii=False)
    handle.write("\n")
PY
}
# B13: Beendet den privaten Server samt Prozessgruppe und entfernt die
# Übergabedateien. Mehrfache Aufrufe sind unschädlich.
stop_private_server() {
  local pid=""
  if [ -r "$SERVER_PID_FILE" ]; then
    pid="$(cat "$SERVER_PID_FILE" 2>/dev/null || true)"
  fi
  case "$pid" in
    ''|*[!0-9]*) ;;
    *)
      kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
      sleep 1
      kill -KILL -- "-$pid" 2>/dev/null || true
      ;;
  esac
  rm -f -- "$SERVER_JSON" "$SERVER_PID_FILE"
}
# B13: Startet einen privaten opencode-Server auf einem freien Loopback-Port.
# Das Kennwort kommt ausschließlich über die bereits exportierte
# Umgebungsvariable; es erscheint weder in der Argumentliste noch im Protokoll.
start_private_server() {
  local dir="$1" port url wrap=()
  port="$(private_free_port)" || return 1
  url="http://127.0.0.1:$port"
  if [ "$SANDBOX_STATE" = "on" ]; then
    wrap=(python3 "$BIN/vibe_sandbox.py" "$P" --runtime "$RUNTIME" --chdir "$dir" --write-dir "$dir" --)
  fi
  rm -f -- "$SERVER_JSON" "$SERVER_PID_FILE"
  : > "$SERVER_LOG"
  # Der Server läuft in einer eigenen Sitzung und überlebt damit das Ende des
  # Agenten-Subshells. Seine Ausgabe geht in die eigene Serverdatei.
  if command -v setsid > /dev/null 2>&1; then
    setsid --fork bash -c 'echo "$$" > "$1"; shift; exec "$@"' \
      _ "$SERVER_PID_FILE" "${VIBE_CLEAN_ENV[@]}" "${wrap[@]}" \
      opencode serve --hostname 127.0.0.1 --port "$port" \
      >> "$SERVER_LOG" 2>&1 < /dev/null
  else
    # Ohne setsid bleibt der Server Kind dieses Subshells; das ist nur für
    # nicht sandboxierte Läufe dauerhaft. Die PID-Datei ermöglicht dennoch
    # ein sauberes Beenden.
    bash -c 'echo "$$" > "$1"; shift; exec "$@"' \
      _ "$SERVER_PID_FILE" "${VIBE_CLEAN_ENV[@]}" "${wrap[@]}" \
      opencode serve --hostname 127.0.0.1 --port "$port" \
      >> "$SERVER_LOG" 2>&1 < /dev/null &
  fi
  local deadline=$((SECONDS + 15))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if curl -sf --max-time 2 -u "opencode:$OPENCODE_SERVER_PASSWORD" \
        "$url/api/info" > /dev/null 2>&1; then
      if private_server_file_write "$url" "$port" "$dir"; then
        return 0
      fi
      echo "ABBRUCH: Serverdatei $SERVER_JSON konnte nicht geschrieben werden." | tee -a "$LOG"
      stop_private_server
      return 1
    fi
    sleep 0.2
  done
  echo "ABBRUCH: Der private opencode-Server wurde unter $url nicht gesund; ohne erreichbaren Server startet kein Agent." | tee -a "$LOG"
  stop_private_server
  return 1
}
# B13/AP1: Stellt den privaten Server vor jedem opencode-Agentenaufruf sicher.
# Der erste Aufruf startet ihn; spätere Aufrufe verwenden ihn nur, wenn er
# gesund ist und für dasselbe Verzeichnis läuft. Bei Wechsel von $P (Preflight)
# zu $WT (Paket) bzw. zwischen Arbeitskopien wird er neu gestartet. Ein
# Fehlschlag wird als Laufabbruch markiert, nie still durch --standalone
# ersetzt.
ensure_private_server() {
  local dir="$1" url
  [ "$PRIVATE_SERVER" = 1 ] || return 0
  if private_server_healthy "$dir"; then
    SERVER_ARGS="--server $(private_server_url)"
    return 0
  fi
  stop_private_server
  if ! start_private_server "$dir"; then
    printf '%s\n' "Der private opencode-Server konnte nicht gestartet werden." \
      > "$SERVER_FAILED_FILE"
    return 1
  fi
  url="$(private_server_url)" || {
    printf '%s\n' "Der private opencode-Server hat keine gültige Serverdatei geschrieben." \
      > "$SERVER_FAILED_FILE"
    stop_private_server
    return 1
  }
  SERVER_ARGS="--server $url"
  return 0
}
RUN_ID="${VIBE_RUN_ID:-}"
RUN_SESSION="${VIBE_SESSION:-vibe-$NAME}"
cd "$P" || exit 1
[ -f .vibe/project.env ] && set -a && . ./.vibe/project.env && set +a
# F31: Das Einlesen der Projektdatei exportiert mit set -a alle dort
# definierten Variablen erneut. Belegt die Projektdatei OPENCODE_PASSWORD
# (etwa als übernommener Alt-Export), würde ein späterer privater
# Server-(Neu)start diesen Wert erben — dasselbe Fehlerbild wie bei einem
# geerbten Wert aus der Startumgebung. Das Kennwort für den opencode-Server
# kommt ausschließlich aus der Laufzeitdatei.
unset OPENCODE_PASSWORD
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
# AP14: Fortsetzung in derselben Session. Die Kennung kommt ausschließlich
# über die Umgebung vom Startbefehl (vibe.cmd_run) und wird hier mit derselben
# Zeichenklasse geprüft wie im Lauf sonst üblich; ein ungültiger Wert wird
# verworfen, statt den Lauf abzubrechen. Der Pi-Zweig ignoriert die Kennung.
CONTINUE_SESSION="${VIBE_CONTINUE_SESSION:-}"
case "$CONTINUE_SESSION" in
  *[!A-Za-z0-9_-]*) CONTINUE_SESSION="" ;;
esac
# AP4 (T-W1): Resume-Paket aus der Session (Reattach). Dieselbe harte
# Zeichenklassenprüfung wie bei VIBE_CONTINUE_SESSION; ein leerer Wert heißt
# normale Auswahl. Ein bereits geschlossenes Paket wird über den --prefer-
# Hinweis ignoriert und der Lauf wählt normal (protokollierter Rückfall).
RESUME_PACKAGE="${VIBE_RESUME_PACKAGE:-}"
case "$RESUME_PACKAGE" in
  *[!A-Za-z0-9_-]*) RESUME_PACKAGE="" ;;
esac
# Ist das bevorzugte Resume-Paket bereits geschlossen, wird es über den
# --prefer-Hinweis ignoriert; der Lauf wählt dann normal weiter und
# protokolliert den Rückfall (siehe select_item/Arbeitspaket-Schleife).
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
# V-027: Globales Limitverhalten. Ohne Datei und bei defekter Einstellung gilt
# "stop"; "continue" behandelt Quota- und Anmeldefehler wie wiederholbare
# Fehler im Rahmen der vorhandenen Wiederholungslimits. Die Meldung einer
# defekten Datei landet im Laufprotokoll, nie still als "continue".
LIMIT_MODE="stop"
LIMITS_CLI="$BIN/vibe_limits.py"
if [ -f "$LIMITS_CLI" ]; then
  LIMIT_MODE="$(python3 "$LIMITS_CLI" mode --state "$STATE" 2>>"$LOG" || true)"
fi
case "$LIMIT_MODE" in
  stop|continue) ;;
  *) LIMIT_MODE="stop" ;;
esac
# AP10: Wirksame Schrankeneinstellungen. Ohne Modul bleiben alle Werte leer
# und der Läufer nutzt die bisherigen Voreinstellungen. Meldungen zu defekten
# Werten gehen ins Laufprotokoll; defekte Schranken gelten konservativ als
# Voreinstellung. Die Projektwerte aus .vibe/project.env sind bereits in der
# Umgebung (set -a) und schlagen die globalen Einstellungen; die Umgebungs-
# variable VIBE_MAX_PACKAGES behält für die Durchgangsschranke den Vorrang.
GATES_CLI="$BIN/vibe_gates.py"
GATE_PACKAGES=""
GATE_RETRIES=""
GATE_REPAIR_ROUNDS=""
GATE_ASSIST_ROUNDS=""
GATE_OVERRIDE_EFF=""
if [ -f "$GATES_CLI" ]; then
  eval "$(python3 "$GATES_CLI" json --state "$STATE" --project "$P" 2>>"$LOG" | python3 -c '
import json
import shlex
import sys

data = json.load(sys.stdin)
gates = data.get("gates") if isinstance(data, dict) else None
if not isinstance(gates, dict):
    raise SystemExit(1)
for key, name in (
    ("packages", "GATE_PACKAGES"),
    ("retries", "GATE_RETRIES"),
    ("repair_rounds", "GATE_REPAIR_ROUNDS"),
    ("assist_rounds", "GATE_ASSIST_ROUNDS"),
    ("override", "GATE_OVERRIDE_EFF"),
):
    entry = gates.get(key)
    value = entry.get("value") if isinstance(entry, dict) else entry
    print(name + "=" + shlex.quote("" if value is None else str(value)))
' 2>>"$LOG")" || true
fi
# Ohne Gates-Modul gilt der Projektwert (bereits in der Umgebung) oder "ask";
# ein defekter Wert blockiert konservativ (kein "ask", keine Rückfrage).
if [ -z "$GATE_OVERRIDE_EFF" ]; then
  GATE_OVERRIDE_EFF="${GATE_OVERRIDE:-ask}"
fi
if [ "$HARNESS" = "pi" ] && [ ! -f "$HARNESS_CLI" ]; then
  echo "ABBRUCH: Harness pi gewählt, aber $HARNESS_CLI fehlt. Installation aktualisieren (Setup --update)." | tee -a "$LOG"
  exit 2
fi
MAXP="${VIBE_MAX_PACKAGES:-${MAX_PACKAGES:-${GATE_PACKAGES:-80}}}"
if ! [[ "$MAXP" =~ ^[0-9]+$ ]]; then
  echo "ABBRUCH: MAX_PACKAGES muss eine Zahl sein." | tee -a "$LOG"
  exit 2
fi
MAXR="${MAX_RETRIES:-${GATE_RETRIES:-2}}"
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
# Ist der autonome Modus aktiv, sind Rückfragen nicht möglich: vibe ask lehnt
# sie sofort ab; der Agent entscheidet selbst und prüft den Zustand mit status.
QUESTION_HINT='Wenn eine fachliche Entscheidung offen ist, stelle eine Rückfrage mit vibe ask "Frage" --option "A" --option "B"; sie erscheint im Dashboard. Ohne Antwort im Zeitlimit endet der Befehl mit Exit-Code 3, die Frage bleibt offen; setze danach mit vibe ask --wait <id> fort. Im autonomen Modus sind Rückfragen nicht möglich: vibe ask meldet das direkt und du entscheidest selbst; der Nutzer ist nicht erreichbar. Wird der Modus während des Wartens eingeschaltet, endet das Warten sofort; dokumentiere die Entscheidung mit vibe answer <id> --text "..." --by agent.'
# B17: Die Produktivpfade fehlen in der Agentenumgebung; der Laufzeitordner
# wird deshalb ausdrücklich übergeben. Die Kurzform oben bleibt als Hinweis,
# die folgende Form mit --runtime ist für diesen Lauf maßgeblich.
QUESTION_HINT+=" Wichtig: In diesem Lauf immer vibe ask --runtime $RUNTIME \"Frage\" --option \"A\" verwenden und mit vibe ask --wait <id> --runtime $RUNTIME fortsetzen; Antworten mit vibe answer --runtime $RUNTIME <id> --text \"...\" --by agent dokumentieren. Den aktuellen Zustand prüfst du mit vibe autonomous status --runtime $RUNTIME."
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
  # $3 = optionale Notiz, $4 = "only-live" (bereits beendete Läufe bleiben).
  [ -f "$RUNS_PY" ] && [ -n "$RUN_ID" ] || return 0
  local extra=()
  [ -n "${3:-}" ] && extra+=(--note "$3")
  [ "${4:-}" = "only-live" ] && extra+=(--only-live)
  python3 "$RUNS_PY" finish --runtime "$RUNTIME" --id "$RUN_ID" \
    --exit-code "$1" --state "$2" "${extra[@]}" >>"$LOG" 2>&1 || true
  # AP4 (T-S1): Endzustand auf den Session-Einträgen dieses Laufs persistieren
  # (blocked/finished/failed/paused/ended); räumt zugleich altersbedingt auf.
  python3 "$RUNS_PY" sessions-finish --runtime "$RUNTIME" --run-id "$RUN_ID" \
    --state "$2" >>"$LOG" 2>&1 || true
  return 0
}
HASHFILE="$HOME/.config/schreibfuchs-verify.sha"
# Die Android-Abnahmedateien gelten nur für Android-Projekte. Ein generisches
# Projekt wird ohne sie ausgeführt und geprüft.
check_hash() {
  [ "${TYPE:-}" = "android" ] || return 0
  [ -f "$HASHFILE" ] && (cd "$V" && sha256sum -c "$HASHFILE" --quiet) || { echo "ABBRUCH: Abnahme-Dateien fehlen oder wurden verändert."; exit 3; }
}
# B17: Prüfungen laufen mit bereinigter Umgebung und bei SANDBOX=on in
# derselben Sandbox wie der Agent. VIBE_VERIFY_RUNTIME ist die einzige
# Prüfvariable für den laufsspezifischen Lauf-/Prüfordner: kein Produktivpfad,
# gesetzt ausschließlich für die Dauer dieses Prüfaufrufs.
verify_run() {
  local dir="$1" cmd="$2"
  local -a inner=("${VIBE_CLEAN_ENV[@]}" "VIBE_VERIFY_RUNTIME=$RUNTIME" bash -lc "$cmd")
  if [ "$SANDBOX_STATE" = "on" ]; then
    python3 "$BIN/vibe_sandbox.py" "$P" --runtime "$RUNTIME" \
      --chdir "$dir" --write-dir "$dir" --write-dir "$P" -- "${inner[@]}"
  else
    ( cd "$dir" && "${inner[@]}" )
  fi
}
# Typabhängiger Prüfadapter: eigener Befehl des Projekts, sonst die
# Android-Abnahme — und die ausschließlich für Android-Projekte.
final_verify() {
  local CMD="${VERIFY_FULL:-}"
  if [ -n "$CMD" ] && [[ "$CMD" == *TODO* ]]; then
    echo "ABBRUCH: VERIFY_FULL ist nur ein Platzhalter (TODO); es wird keine Prüfung ausgeführt."
    return 3
  fi
  if [ -n "$CMD" ]; then verify_run "$P" "$CMD"; return $?; fi
  if [ "${TYPE:-}" = "android" ] && [ -f "$V/verify.sh" ]; then
    verify_run "$P" "bash \"$V/verify.sh\" \"$P\" full"
    return $?
  fi
  echo "FEHLT: keine VERIFY_FULL-Prüfung in .vibe/project.env definiert (und keine Android-Abnahme für TYPE=${TYPE:-generic})."
  return 3
}
# Projektlokaler Auswahlstand: kein globales /tmp, keine Kollision zwischen
# Projekten. Die Datei liegt unter .vibe/tmp und wird über .git/info/exclude
# aus dem Git-Status herausgehalten.
select_item() {
  local state="$P/.vibe/tmp/next-package.json"
  local prefer=()
  [ -n "$RESUME_PACKAGE" ] && prefer=(--prefer "$RESUME_PACKAGE")
  if ! python3 "$PACKAGES_PY" select --project "$P" --state "$state" --skip "$SKIP" "${prefer[@]}" >>"$LOG" 2>&1; then
    return 1
  fi
  eval "$(python3 - "$state" <<'PY'
import json
import shlex
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
print("ID=" + shlex.quote(str(data["id"])))
print("TICKET_TYPE=" + shlex.quote(str(data.get("type") or "")))
print("TITLE=" + shlex.quote(str(data.get("title") or "")))
print("DESCRIPTION=" + shlex.quote(str(data.get("description") or "")))
print("PRIORITY=" + shlex.quote(str(data.get("priority") or "")))
# AP11: Die projektweise Priorisierung ist verbindlich; der Lauf meldet,
# ob die Wahl aus PACKAGE_ORDER kam oder die Standardordnung galt.
print("ORDERED=" + ("1" if data.get("ordered") else "0"))
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
  RECONNECT=0
  # B16: Der Branch-Name kommt aus dem Repository-Muster (Subkommando
  # branch-name), nicht mehr aus vibe/<...>. Er steht vor mktemp fest, damit
  # ein Fehlschlag keine halbe Arbeitskopie zurücklässt. Die FEHLT-Meldung
  # des Subkommandos landet im Protokoll.
  if ! BRANCH="$(python3 "$PACKAGES_PY" branch-name --project "$P" --id "$ID" 2>>"$LOG")"; then
    printf '%s\n' "$BRANCH" >>"$LOG"
    return 1
  fi
  if [ -z "$BRANCH" ]; then
    echo "FEHLT: branch-name lieferte keinen Branch-Namen für $ID." >>"$LOG"
    return 1
  fi
  # AP4 (T-W2): RECONNECT aus der Worktree-Registry. Ein gültiger Eintrag
  # (Pfad existiert, erscheint in ``worktree list``, Branch existiert) wird
  # wiederverwendet; sonst wird der veraltete Eintrag entfernt.
  if [ -f "$RUNS_PY" ]; then
    local existing wt_candidate branch_candidate base_candidate
    existing="$(python3 "$RUNS_PY" worktree-get --runtime "$RUNTIME" --project "$P" --id "$ID" 2>>"$LOG")"
    if [ -n "$existing" ] && [ "$existing" != "none" ]; then
      eval "$(printf '%s' "$existing" | python3 -c '
import json
import shlex
import sys

data = json.load(sys.stdin)
if isinstance(data, dict):
    print("wt_candidate=" + shlex.quote(str(data.get("path") or "")))
    print("branch_candidate=" + shlex.quote(str(data.get("branch") or "")))
    print("base_candidate=" + shlex.quote(str(data.get("base_commit") or "")))
' 2>>"$LOG")" || true
      if [ -n "$wt_candidate" ] && [ -n "$branch_candidate" ] && [ -d "$wt_candidate" ] \
          && git -C "$P" worktree list --porcelain 2>>"$LOG" | grep -Fxq "worktree $wt_candidate" \
          && git -C "$P" rev-parse --verify --quiet "refs/heads/$branch_candidate" >/dev/null 2>&1; then
        WT="$wt_candidate"
        BRANCH="$branch_candidate"
        PACKAGE_BASE="${base_candidate:-$PACKAGE_BASE}"
        RECONNECT=1
        echo "RECONNECT: Arbeitskopie $WT (Branch $BRANCH) wird wiederverwendet." | tee -a "$LOG"
        return 0
      fi
      python3 "$RUNS_PY" worktree-unregister --runtime "$RUNTIME" --project "$P" --id "$ID" >>"$LOG" 2>&1 || true
    fi
  fi
  WT="$(mktemp -d "$WT_ROOT/${safe_name}-${safe_id}-XXXXXX")" || return 1
  if ! git -C "$P" worktree add --quiet -b "$BRANCH" "$WT" "$PACKAGE_BASE" >>"$LOG" 2>&1; then
    # Keine halbe Arbeitskopie zurücklassen, wenn das Anlegen scheitert.
    rm -rf -- "$WT"
    git -C "$P" worktree prune >>"$LOG" 2>&1 || true
    return 1
  fi
  return 0
}
# B11: Der Agentenauftrag läuft in einer eigenen Prozessgruppe. Nur so beendet
# ein Stopp die ganze Kette (Harness, Wrapper, Enkel), statt einen
# signalignorierenden Harness als Waise weiterarbeiten zu lassen. AGENT_PID ist
# die Prozessgruppe; ein leerer Wert heißt, dass kein Auftrag läuft.
AGENT_PID=""
stop_agent_group() {
  local pgid="$AGENT_PID"
  if [ -z "$pgid" ]; then
    # B11: Feuert ein Signal-Trap im Spawnfenster zwischen dem Start des
    # Auftrags und der Zuweisung von AGENT_PID, ist die Kennung noch leer.
    # Unter set -m ist der Auftrag seine eigene Prozessgruppe; jobs -p nennt
    # deren PID (= PGID). Der Agentenauftrag ist der einzige
    # Hintergrundauftrag dieses Skripts.
    pgid="$(jobs -p)"
  fi
  if [ -n "$pgid" ]; then
    AGENT_PID=""
    if kill -0 -- "-$pgid" 2>/dev/null; then
      kill -TERM -- "-$pgid" 2>/dev/null || true
      sleep 1
      kill -KILL -- "-$pgid" 2>/dev/null || true
    fi
  fi
  # B13: Der private Server gehört zum Lauf, nicht zur Agentengruppe; er wird
  # beim Laufende beendet und seine Übergabedateien werden entfernt.
  stop_private_server
  return 0
}
# Beendet sich der Läufer auf einem Weg ohne Signal-Trap (etwa nach einem
# Fehler oder einem regulären Ende), beendet auch das den Auftrag; sonst
# bliebe eine laufende Agentengruppe als Waise zurück.
trap 'stop_agent_group' EXIT
run_agent_in() {
  local dir="$1" prompt="$2" title="${3:-$NAME $ID}"
  local wrap=() rc
  if [ "$SANDBOX_STATE" = "on" ]; then
    wrap=(python3 "$BIN/vibe_sandbox.py" "$P" --runtime "$RUNTIME" --chdir "$dir" --write-dir "$dir" --)
  fi
  # B11: Die Jobkontrolle stellt den Auftrag in eine eigene Prozessgruppe und
  # lässt den Signal-Trap schon während wait feuern. stdin bleibt wie bisher
  # /dev/null, weil die Jobkontrolle es nicht mehr selbst ersetzt.
  set -m
  (
    cd "$dir" || exit 1
    # B13: Der private Server wird beim ersten Agentenaufruf in diesem
    # Subshell gestartet (set +m hält ihn in dessen Prozessgruppe für den
    # Start; die eigentliche Abkopplung übernimmt setsid). Ein Fehlschlag
    # bricht den Auftrag ab, statt ohne erreichbaren Server zu starten.
    if [ "$PRIVATE_SERVER" = 1 ]; then
      set +m
      ensure_private_server "$dir" || exit 2
    fi
    # AP23: Das ausgewählte Secret gilt nur für diesen einen Agentenlauf.
    # Ohne Vault-Key oder bei einem anderen Fehler startet der Agent nicht.
    # Das Modul ist Teil des Pakets; in älteren Installationen ist es noch
    # nicht vorhanden — dann gilt kein Sync (keine Keys in diesem Install).
    if [ -f "$BIN/vibe_keys.py" ]; then
      if ! python3 "$BIN/vibe_keys.py" sync --state "$STATE" --harness "$HARNESS" >>"$LOG" 2>&1; then
        echo "AP23: Key-Sync fehlgeschlagen; Agent nicht gestartet" >>"$LOG"
        exit 2
      fi
    fi
    if [ "$HARNESS" = "pi" ]; then
      # B6: Pi gibt mit --mode json strukturierte Ereignisse aus. Derselbe
      # Erfassungsfilter wie beim opencode-Zweig macht daraus menschenlesbare
      # Protokollzeilen und die Zustandsdatei für die Ausgabeansicht (F24);
      # maßgeblich bleibt der Exit-Code des Agentenprozesses.
      local args=(python3 "$HARNESS_CLI" run --harness pi --json --project "$dir" --agent "$AGENT" --title "$title" --prompt "$prompt")
      [ -n "$MODEL" ] && args+=(--model "$MODEL")
      [ -n "${VIBE_AGENTS_DIR:-}" ] && args+=(--agents-dir "$VIBE_AGENTS_DIR")
      "${VIBE_CLEAN_ENV[@]}" "${wrap[@]}" "${args[@]}" 2>&1 | "${STREAM_FILTER[@]}" | tee -a "$LOG"
      exit "${PIPESTATUS[0]}"
    fi
    # F25: Ist eine Session aus einem unterbrochenen Versuch erfasst, wird
    # derselbe Auftrag in derselben Session mit --session fortgesetzt statt
    # neu zu beginnen. Ohne erfasste Session verhält sich der Aufruf wie
    # bisher (eine leere Kennung wird nie übergeben).
    local args=(opencode run $SERVER_ARGS --format json --auto --thinking)
    [ -n "${RESUME_SESSION:-}" ] && args+=(--session "$RESUME_SESSION")
    args+=(--agent "$AGENT" "${MODEL_ARGS[@]}" --title "$title" "$prompt")
    "${VIBE_CLEAN_ENV[@]}" "${wrap[@]}" "${args[@]}" 2>&1 | "${STREAM_FILTER[@]}" | tee -a "$LOG"
    exit "${PIPESTATUS[0]}"
  ) </dev/null &
  AGENT_PID=$!
  set +m
  wait "$AGENT_PID"
  rc=$?
  AGENT_PID=""
  # AP23: Least Privilege – nach der Sitzung keine Secrets in der Harness-Config.
  if [ -f "$BIN/vibe_keys.py" ]; then
    python3 "$BIN/vibe_keys.py" sync --reset --state "$STATE" --harness "$HARNESS" >>"$LOG" 2>&1 || true
  fi
  return "$rc"
}
run_agent() {
  run_agent_in "$WT" "$PROMPT" "$NAME $ID"
}
# AP7 (T-V21): Hash-Wächter für die transportierte .vibe/project.env. Nach dem
# Transport (Paketstart) wird der Inhalt erfasst und vor jeder Paketprüfung
# erneut geprüft. Eine Abweichung ist Manipulation der autoritativen
# Projektwerte und kein gewöhnlicher Defekt: blockieren ohne Reparaturrunde.
# Best effort wie der Transport selbst (fehlende Startdatei = kein Wächter).
# GH-46: .vibe/verify-baseline wird nicht mehr transportiert und nicht bewacht;
# Arbeitskopien arbeiten mit der committeten Baseline aus dem Branch.
package_file_hash() {
  local path="$1"
  [ -f "$path" ] || return 1
  sha256sum "$path" | awk '{print $1}'
}
# AP7 (T-V21): Prüft, ob die beim Paketstart vorhandene transportierte
# .vibe/project.env seither verändert oder entfernt wurde. Rückgabe
# 0 = unverändert (bzw. kein Wächter), 1 = Manipulation; TAMPERED_FILE nennt
# die Datei. Eine beim Start fehlende Datei hat keinen Wächter (best effort).
# GH-46: .vibe/verify-baseline wird nicht mehr bewacht (nicht transportiert).
guard_transported_files() {
  TAMPERED_FILE=""
  if [ -n "$PKG_HASH_PROJECT_ENV" ]; then
    if [ ! -f "$WT/.vibe/project.env" ]; then
      TAMPERED_FILE=".vibe/project.env"
    elif [ "$PKG_HASH_PROJECT_ENV" != "$(package_file_hash "$WT/.vibe/project.env")" ]; then
      TAMPERED_FILE=".vibe/project.env"
    fi
  fi
  [ -z "$TAMPERED_FILE" ]
}
run_package_tests() {
  local cmd="${VERIFY_PACKAGE:-${VERIFY_FULL:-}}"
  echo "=== Paketprüfung für $ID ===" | tee -a "$LOG"
  local output
  output="$( verify_run "$WT" "$cmd" 2>&1 )"
  local rc=$?
  printf '%s\n' "$output" >>"$LOG"
  PACKAGE_TEST_OUT="$output"
  return "$rc"
}
gate_ok() {
  local out rc
  out="$(python3 "$PACKAGES_PY" gate --project "$WT" --id "$ID" --base "$PACKAGE_BASE" 2>&1)"
  rc=$?
  printf '%s\n' "$out" | tee -a "$LOG"
  GATE_OUT="$out"
  return $rc
}
# B9: Ein Pakettest- oder Schrankenbefund geht mit den konkreten Befunden an
# den Agenten zurück in denselben Arbeitsbaum. Die Zahl der Runden ist
# begrenzt; danach entscheidet die Schranken-Rückfrage (AP10) oder das Paket
# blockiert mit den letzten Befunden.
repair_round() {
  # $1 = Befund, $2 = Details, $3 = Rundenanzeige, $4 = optionale Anweisung
  local finding="$1" details="$2" round="$3" instruction="${4:-}"
  echo "REPARATUR: $finding (Runde $round/$REPAIR_MAX_ROUNDS) im Arbeitsbaum $WT." | tee -a "$LOG"
  REPAIR_LOG_START="$(wc -l < "$LOG" 2>/dev/null || echo 0)"
  local prompt="Die Abschlussprüfung für Arbeitspaket $ID ist nicht bestanden.
Befund: $finding
Details:
$details
"
  if [ -n "$instruction" ]; then
    prompt+="Anweisung:
$instruction
"
  fi
  prompt+="
Behebe ausschließlich diesen Befund in der Arbeitskopie $WT. Verwirf keine fremden Änderungen. Bearbeite keine anderen Arbeitspakete, starte keinen neuen Lauf, merge oder pushe nicht und schwäche die Abnahme nicht ab. Committe mit dem Präfix '$ID:'. Beende danach deine Arbeit; Paketprüfung und Abschlussschranke werden erneut ausgeführt."
  run_agent_in "$WT" "$prompt" "$NAME $ID Reparatur"
  local rc=$?
  if [ "$rc" != 0 ]; then
    local repair_class
    repair_class="$(python3 "$PACKAGES_PY" classify --exit-code "$rc" --log "$LOG" --since "$REPAIR_LOG_START" 2>>"$LOG")"
    case "$repair_class" in
      quota)
        REPAIR_ERROR="Quota/Kontingent beim Reparaturauftrag für $ID; der Lauf hält sofort an." ;;
      auth)
        REPAIR_ERROR="Anmeldung/Autorisierung beim Reparaturauftrag für $ID fehlgeschlagen; der Lauf hält sofort an." ;;
      *)
        REPAIR_ERROR="Reparatur für $ID fehlgeschlagen (Exit-Code $rc)." ;;
    esac
    return 1
  fi
  return 0
}
# AP10: Schranken-Rückfrage (F16) am erreichtem Reparaturlimit. Rückgabe:
# 0 = eine zusätzliche Reparaturrunde lief; die Prüfung wird erneut
# ausgeführt und jede weitere Runde erfordert eine neue Entscheidung;
# 2 = Paket überspringen (Nutzer- oder autonome Entscheidung); 1 = blockieren
# (override=off, ohne Module, ohne Antwort, ungültige Antwort oder
# fehlgeschlagene zusätzliche Runde). Die Abschlussschranke selbst bleibt
# unangetastet; ein übersprungenes Paket wird nie gemergt.
barrier_repair_round() {
  local finding="$1" details="$2"
  if [ "$GATE_OVERRIDE_EFF" != "ask" ]; then
    REPAIR_ERROR="Reparaturlimit für $ID nach $REPAIR_MAX_ROUNDS Runden erreicht."
    return 1
  fi
  local out
  # AP10: Wartezeit der Schranken-Rückfrage. Ein Lauf kann unbeaufsichtigt
  # starten; dann soll er nicht zehn Minuten auf eine Antwort warten. Das
  # Preflight-Zeitlimit gilt weiterhin, wenn es gesetzt ist; sonst 60 s.
  # VIBE_BARRIER_QUESTION_TIMEOUT setzt beides für die Schranke außer Kraft.
  if ! out="$(python3 "$PACKAGES_PY" barrier --project "$P" --id "$ID" \
      --reason "Reparaturlimit für $ID nach $REPAIR_MAX_ROUNDS Runden erreicht. $finding" \
      --runtime "$RUNTIME" --project-name "$NAME" \
      --timeout "${VIBE_BARRIER_QUESTION_TIMEOUT:-${VIBE_PREFLIGHT_QUESTION_TIMEOUT:-60}}" 2>>"$LOG")" \
      || [ -z "$out" ]; then
    REPAIR_ERROR="Reparaturlimit für $ID nach $REPAIR_MAX_ROUNDS Runden erreicht. (Rückfrage nicht möglich.)"
    return 1
  fi
  BARRIER_ACTION=""
  BARRIER_INSTRUCTION=""
  eval "$(printf '%s' "$out" | python3 -c '
import json
import shlex
import sys

data = json.load(sys.stdin)
action = data.get("action")
instruction = data.get("instruction")
print("BARRIER_ACTION=" + shlex.quote(action if isinstance(action, str) else ""))
print("BARRIER_INSTRUCTION=" + shlex.quote(instruction if isinstance(instruction, str) else ""))
' 2>>"$LOG")" || true
  case "$BARRIER_ACTION" in
    skip)
      BARRIER_NOTE="auf Nutzerentscheidung übersprungen (Reparaturlimit für $ID nach $REPAIR_MAX_ROUNDS Runden erreicht)"
      return 2 ;;
    autonomous)
      BARRIER_NOTE="autonome Entscheidung: übersprungen (Reparaturlimit für $ID nach $REPAIR_MAX_ROUNDS Runden erreicht)"
      return 2 ;;
    agent)
      echo "SCHRANKE: Nutzerentscheidung — zusätzliche Reparaturrunde läuft." | tee -a "$LOG"
      REPAIR_ROUNDS=$((REPAIR_ROUNDS + 1))
      repair_round "$finding" "$details" "$REPAIR_ROUNDS" "$BARRIER_INSTRUCTION"
      return $?
      ;;
    *)
      REPAIR_ERROR="Reparaturlimit für $ID nach $REPAIR_MAX_ROUNDS Runden erreicht."
      return 1 ;;
  esac
}
repair_package_finding() {
  local finding="$1" details="$2"
  if [ "$REPAIR_ROUNDS" -ge "$REPAIR_MAX_ROUNDS" ]; then
    barrier_repair_round "$finding" "$details"
    return $?
  fi
  REPAIR_ROUNDS=$((REPAIR_ROUNDS + 1))
  repair_round "$finding" "$details" "$REPAIR_ROUNDS"
}
# AP4 (T-G7): Basis in den Paketbranch mergen; bei Konflikt genau eine
# begrenzte Reparaturrunde, danach erneut prüfen. Besteht der Konflikt im
# zweiten Versuch, wird der Merge abgebrochen und das Paket blockiert.
# Rückgabe: 0 = mergebar/Skip, 1 = blockiert (REPAIR_ERROR ist gesetzt).
ensure_mergeable_package() {
  local rc instruction repair_rc
  python3 "$PACKAGES_PY" ensure-mergeable --project "$P" --worktree "$WT" >>"$LOG" 2>&1
  rc=$?
  [ "$rc" = 0 ] && return 0
  if [ "$rc" = 2 ]; then
    instruction="Der Läufer hat 'git merge origin/<base>' in die Arbeitskopie gestartet und es gibt Merge-Konflikte. Starte KEINEN neuen Merge und brich den Merge des Läufers NICHT ab. Löse die Konflikte in der Arbeitskopie $WT, 'git add' die gelösten Dateien und schließe mit 'git merge --continue' (oder 'git commit') ab. Nutze niemals global --ours/--theirs, niemals rebase, force-push oder push. Committe mit dem Präfix '$ID:' falls eigene Commits nötig."
    REPAIR_ROUNDS=$((REPAIR_ROUNDS + 1))
    repair_round "Merge-Konflikt mit der Basis in $WT" "$instruction" "$REPAIR_ROUNDS" "$instruction"
    repair_rc=$?
    if [ "$repair_rc" = 0 ]; then
      python3 "$PACKAGES_PY" ensure-mergeable --project "$P" --worktree "$WT" >>"$LOG" 2>&1
      rc=$?
      [ "$rc" = 0 ] && return 0
    fi
    python3 "$PACKAGES_PY" ensure-mergeable --project "$P" --worktree "$WT" --abort >>"$LOG" 2>&1 || true
    REPAIR_ERROR="Merge-Konflikt mit der Basis für $ID nicht behoben."
    return 1
  fi
  # Exit 1 = Fehler ohne Konflikt (z. B. Fetch nicht möglich, Basis unbekannt).
  # Kein Block hier: Der eigentliche Push/Merge-Request läuft über
  # github-complete und meldet einen Fehlschlag dort mit der passenden Ursache.
  return 0
}
merge_package() {
  # AP6 (F27, Variante A): Arbeitsnotizen sind Laufzeitstand (wie dirty_report):
  # lokale, uncommittete Änderungen an ihnen — zurückgeschriebener Nachweis,
  # Blockievermerk (AP10) — dürfen den ff-Merge nicht blockieren. Der
  # Paketbranch enthält dieselben Notizen bereits (sie werden beim Paketstart
  # in die Arbeitskopie kopiert und dort committet), deshalb liefert der Merge
  # denselben Stand zurück. Genau deshalb werden nur die Dateien verworfen,
  # die der Merge ohnehin überschreiben würde: die Differenz HEAD..$BRANCH.
  # Eine dirty Notiz, die der Branch nicht ändert, bleibt unangetastet. Der
  # Verwurf wird mit WARNUNG protokolliert; nicht versionierte Dateien werden
  # nie gelöscht (sie können den Merge weiterhin blockieren).
  local merge_files dirty_files discarded all_notes file
  merge_files="$(git -C "$P" diff --name-only HEAD "$BRANCH" 2>>"$LOG" || true)"
  dirty_files="$(
    git -C "$P" diff --name-only 2>>"$LOG" || true
    git -C "$P" diff --name-only --cached 2>>"$LOG" || true
  )"
  discarded=""
  all_notes=1
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    printf '%s\n' "$dirty_files" | grep -Fxq -- "$file" || continue
    discarded="$discarded $file"
    case "$file" in
      AGENTS.md) ;;
      *) all_notes=0 ;;
    esac
    git -C "$P" checkout -q HEAD -- "$file" 2>>"$LOG" || true
  done <<< "$merge_files"
  if [ -n "$discarded" ]; then
    if [ "$all_notes" = 1 ]; then
      echo "WARNUNG: Uncommittete Änderungen an Arbeitsnotizen werden für den Merge verworfen:$discarded" | tee -a "$LOG"
    else
      echo "WARNUNG: Uncommittete Änderungen an Dateien werden für den Merge verworfen:$discarded" | tee -a "$LOG"
    fi
  fi
  if ! git -C "$P" merge --ff-only "$BRANCH" >>"$LOG" 2>&1; then
    echo "FEHLT: Merge von $BRANCH nach $BASE_BRANCH fehlgeschlagen." | tee -a "$LOG"
    return 1
  fi
  return 0
}
sync_work_notes() {
  python3 "$PACKAGES_PY" sync-ticket \
    --project "$P" --worktree "$WT" --id "$ID" >>"$LOG" 2>&1
}
cleanup_worktree() {
  # T-G4: Erst die Arbeitskopie entfernen (bei Misserfolg prune + ein
  # Wiederholungsversuch), danach den Branch nur löschen, wenn er nicht mehr
  # in einer anderen Arbeitskopie ausgecheckt ist.
  if ! git -C "$P" worktree remove --force "$WT" >>"$LOG" 2>&1; then
    git -C "$P" worktree prune >>"$LOG" 2>&1 || true
    if ! git -C "$P" worktree remove --force "$WT" >>"$LOG" 2>&1; then
      echo "WARNUNG: Arbeitskopie $WT konnte nicht entfernt werden." | tee -a "$LOG"
    fi
  fi
  if git -C "$P" worktree list --porcelain 2>>"$LOG" | grep -Fxq "branch refs/heads/$BRANCH"; then
    echo "WARNUNG: Branch $BRANCH ist in einer Arbeitskopie ausgecheckt; Löschen übersprungen." | tee -a "$LOG"
    return 0
  fi
  if git -C "$P" branch -d "$BRANCH" >>"$LOG" 2>&1; then
    return 0
  fi
  # Nach verifiziertem PR-Squash-Merge erzeugt GitHub einen neuen Commit ohne
  # Abstammung; -d scheitert dann zu Recht und -D ist mit Begründung erlaubt.
  if [ "$VERIFIED_SQUASH" = 1 ]; then
    echo "WARNUNG: Branch $BRANCH nach verifiziertem Squash-Merge mit -D entfernt." | tee -a "$LOG"
    git -C "$P" branch -D "$BRANCH" >>"$LOG" 2>&1 || \
      echo "WARNUNG: Branch $BRANCH konnte nicht entfernt werden." | tee -a "$LOG"
    return 0
  fi
  echo "WARNUNG: Branch $BRANCH konnte nicht entfernt werden." | tee -a "$LOG"
  return 0
}
# B1: Projektmodelle aus $P/.vibe/agents.json erreichen opencode. Sie werden
# als Inline-Konfiguration OPENCODE_CONFIG_CONTENT an opencode run und den
# privaten Server übergeben, damit auch vom Orchestrator gestartete Subagenten
# die Projektmodelle statt ihrer globalen Frontmatter-Modelle verwenden. Pi
# kennt keine OPENCODE_CONFIG_CONTENT und bleibt unverändert.
HAS_PROJECT_MODELS=0
if [ "$HARNESS" = "opencode" ]; then
  MERGED_CONFIG="$(python3 - "$P/.vibe/agents.json" <<'PY' 2>>"$LOG"
import json
import os
import re
import sys

config_path = sys.argv[1]

def fail(message):
    # Verständliche Meldung ohne Konfigurationsinhalte oder Geheimnisse.
    sys.stderr.write(message + "\n")
    sys.exit(2)

def _strip_comments(text):
    """Entfernt //- und /* */-Kommentare außerhalb von Zeichenketten.

    Zeilenkommentare enden am (erhaltenen) Zeilenumbruch; Blockkommentare
    werden durch ein Leerzeichen ersetzt, damit benachbarte Token nicht
    zusammenkleben. Ein nicht abgeschlossener Blockkommentar löst ValueError
    aus (fail-closed), statt bis zum Dateiende entfernt zu werden."""
    result = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            result.append(ch)
            if ch == "\\" and i + 1 < n:
                result.append(text[i + 1])
                i += 1
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] not in "\r\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            if i + 1 >= n:
                raise ValueError("Nicht abgeschlossener Blockkommentar in der Inline-Konfiguration.")
            i += 2
            result.append(" ")
            continue
        result.append(ch)
        i += 1
    return "".join(result)


def _strip_trailing_commas(text):
    """Entfernt Kommas, die unmittelbar vor } oder ] stehen (Trailing Commas).

    Kommentare sind hier bereits entfernt; der Lookahead muss daher nur noch
    Whitespace überspringen."""
    result = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            result.append(ch)
            if ch == "\\" and i + 1 < n:
                result.append(text[i + 1])
                i += 1
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
            continue
        if ch == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                i += 1
                continue
        result.append(ch)
        i += 1
    return "".join(result)


def jsonc_to_json(text):
    """Entfernt Kommentare und Trailing Commas; der Inhalt von Zeichenketten
    (auch '//') bleibt unangetastet."""
    return _strip_trailing_commas(_strip_comments(text))

MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$")

# 1) Projektdatei lesen; fehlt sie, gibt es keine Projektmodelle.
try:
    with open(config_path, encoding="utf-8") as handle:
        raw = handle.read()
except FileNotFoundError:
    # Nur eine tatsächlich fehlende Datei bedeutet "keine Projektmodelle".
    sys.exit(0)
except OSError:
    fail("Die Agentenauswahl " + config_path + " ist nicht lesbar.")

try:
    project = json.loads(raw)
except ValueError:
    fail("Die Agentenauswahl in " + config_path + " ist kein gültiges JSON.")
if not isinstance(project, dict):
    fail("Die Agentenauswahl muss ein JSON-Objekt sein.")
models = project.get("modelle", {})
if not isinstance(models, dict):
    fail("'modelle' in der Agentenauswahl muss ein Objekt mit Agentenname und Modell sein.")
clean = {}
for agent, model in models.items():
    if not isinstance(agent, str) or not agent:
        fail("Ungültiger Agentenname in 'modelle' der Agentenauswahl.")
    if not isinstance(model, str):
        fail("Das Modell in der Agentenauswahl muss eine Zeichenkette sein.")
    value = model.strip()
    if not value:
        continue
    if not MODEL_RE.match(value):
        fail("Das Modell in der Agentenauswahl darf keine Leerzeichen enthalten.")
    clean[agent] = value

# AP2-Korbat: opencode-eigene Subagenten general/explore je Projekt steuern.
# aktiv=true + Modell -> Modell wie bei 'modelle' in beide Maps; aktiv=false ->
# disabled ausschließlich in der aktuellen 'agents'-Map (die Legacy-'agent'-Map
# ignoriert disabled; siehe opencode 2.3.0).
opencode = project.get("opencode", {})
if opencode is None:
    opencode = {}
if not isinstance(opencode, dict):
    fail("'opencode' in der Agentenauswahl muss ein Objekt mit general/explore sein.")
opencode_models = {}
opencode_disabled = []
for name in ("general", "explore"):
    entry = opencode.get(name)
    if entry is None:
        continue
    if not isinstance(entry, dict):
        fail("Der opencode-Eintrag '" + name + "' in der Agentenauswahl muss ein Objekt sein.")
    aktiv = entry.get("aktiv", True)
    if not isinstance(aktiv, bool):
        fail("'aktiv' des opencode-Agenten '" + name + "' muss ein JSON-Bool sein.")
    modell = entry.get("modell", "")
    if modell is None:
        modell = ""
    if not isinstance(modell, str):
        fail("Das Modell des opencode-Agenten '" + name + "' muss eine Zeichenkette sein.")
    modell = modell.strip()
    if modell and not MODEL_RE.match(modell):
        fail("Das Modell des opencode-Agenten '" + name + "' in der Agentenauswahl darf keine Leerzeichen enthalten.")
    if aktiv:
        if modell:
            opencode_models[name] = modell
    else:
        opencode_disabled.append(name)

if not clean and not opencode_models and not opencode_disabled:
    # Keine wirksamen Projektmodelle und keine Deaktivierungen: bestehende
    # Konfiguration und Serverwahl bleiben exakt unverändert.
    sys.exit(0)

# 2) Vorhandene Inline-Konfiguration (JSON/JSONC) semantisch erhalten.
merged = {}
existing = os.environ.get("OPENCODE_CONFIG_CONTENT", "")
if existing.strip():
    try:
        merged = json.loads(jsonc_to_json(existing))
    except ValueError:
        fail("OPENCODE_CONFIG_CONTENT ist keine mergefähige Inline-Konfiguration.")
    if not isinstance(merged, dict):
        fail("OPENCODE_CONFIG_CONTENT muss ein JSON-Objekt sein.")

# 3) Projektmodelle konsistent in vorhandene Maps einsetzen. v2.3.0 akzeptiert
#    'agent' (legacy) und 'agents' (aktuell); sind beide vorhanden, gewinnt
#    'agents' für model. Ohne vorhandene Map wird 'agent' für die Kompatibilität
#    mit dem Projektprofil 2.1.4 angelegt (nur wenn tatsächlich Projektmodelle
#    vorliegen).
def ensure_map(config, key):
    entry = config.get(key)
    if entry is None:
        entry = {}
        config[key] = entry
    elif not isinstance(entry, dict):
        fail("OPENCODE_CONFIG_CONTENT: '" + key + "' muss ein Objekt sein.")
    return entry


def set_entry(mapping, name, key, value):
    entry = mapping.get(name)
    if entry is None:
        entry = {}
        mapping[name] = entry
    elif not isinstance(entry, dict):
        fail("OPENCODE_CONFIG_CONTENT: Eintrag für '" + name + "' muss ein Objekt sein.")
    entry[key] = value


if "agent" in merged or "agents" in merged:
    agent_map = ensure_map(merged, "agent") if "agent" in merged else None
    agents_map = ensure_map(merged, "agents") if "agents" in merged else None
else:
    agent_map = ensure_map(merged, "agent") if clean else None
    agents_map = None

for agent, model in clean.items():
    for mapping in (agent_map, agents_map):
        if mapping is None:
            continue
        set_entry(mapping, agent, "model", model)

for name, model in opencode_models.items():
    set_entry(ensure_map(merged, "agent"), name, "model", model)
    set_entry(ensure_map(merged, "agents"), name, "model", model)

for name in opencode_disabled:
    set_entry(ensure_map(merged, "agents"), name, "disabled", True)

print(json.dumps(merged, ensure_ascii=False))
PY
)"
  rc=$?
  if [ "$rc" != 0 ]; then
    echo "ABBRUCH: Projektmodelle konnten nicht angewendet werden; Details im Protokoll $LOG." | tee -a "$LOG"
    exit 2
  fi
  if [ -n "$MERGED_CONFIG" ]; then
    HAS_PROJECT_MODELS=1
    OPENCODE_CONFIG_CONTENT="$MERGED_CONFIG"
    export OPENCODE_CONFIG_CONTENT
  fi
fi
SERVER_ARGS="--standalone"
SANDBOX_STATE=off
# B13: Ohne erreichbaren gemeinsamen Server startet der Lauf einen eigenen
# privaten opencode-Server, damit Zusatzanweisungen aus dem Dashboard ein
# Ziel haben. Kennwortdatei und Harness müssen das zulassen.
PRIVATE_SERVER=0
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
elif [ "$HAS_PROJECT_MODELS" != 1 ] && server_is_up; then SERVER_ARGS="--server http://127.0.0.1:$OPENCODE_PORT"; fi
# B13: In der Sandbox führt ein gemeinsamer Server die Werkzeuge außerhalb der
# Sandbox aus; dort gilt deshalb immer der private Server. Außerhalb der
# Sandbox nur, wenn kein gemeinsamer Server erreichbar ist. Pi kennt keinen
# privaten opencode-Server und bleibt unverändert.
if [ "$HARNESS" = "opencode" ] && [ "$HAS_SERVER_PASSWORD" = 1 ]; then
  if [ "$SANDBOX_STATE" = "on" ] || [ "$SERVER_ARGS" = "--standalone" ]; then
    PRIVATE_SERVER=1
  fi
fi
# F19: opencode liefert mit --format json Ereignisse. Der Filter macht daraus
# menschenlesbare Zeilen (Grundlage für Syntax-Highlighting) und erfasst
# Subagenten samt Ausgabe in <log>.state.json. Fehlt das Modul, bleibt die
# Ausgabe unverändert (kein stiller Abbruch des Laufs). Der Filter wird auch
# für den Preflight-Agenten (F22) gebraucht und deshalb vorher eingerichtet.
STREAM_FILTER=(cat)
if [ -f "$RUNS_PY" ]; then
  # AP19: Der Preflight erfasst seine Hauptsession ohne Lauf-ID (RUN_ID ist
  # hier noch nicht vergeben). Ohne RUNS_PY bleibt der cat-Rückfall aktiv.
  STREAM_FILTER=(python3 "$RUNS_PY" stream --state "$LOG.state.json" --attempt --sessions "$RUNTIME/sessions.json" --session-project "$P" --session-name "$NAME" --session-agent "$AGENT" --session-harness "$HARNESS")
fi
# Preflight: sauberer Git-Integrationsstand, verfügbare Test-/Review-Agenten
# und ein echter Paketprüfbefehl. Ohne diese Bedingungen startet kein Paket.
# F22: Der Produktpfad ``vibe run`` setzt VIBE_PREFLIGHT_ASSIST=1. Dann fragt
# der Preflight bei einem Befund über F16 nach, statt sofort abzubrechen.
# B9: Die Rückfrage bietet zusätzlich "Agent behebt die Befunde"; eine freie
# Antwort ist eine Anweisung an den Agenten. Nach jedem Agentenlauf wird der
# Preflight erneut geprüft. Derselbe Weg behebt am Laufende einen unsauberen
# Integrationsstand.
# F27: Ein ausdrücklich angeforderter Neustart darf einen unsauberen
# Integrationsstand zulassen. Die Änderungen bleiben dabei unangetastet; der
# Preflight überspringt ausschließlich diesen einen Befund. Die Abschluss-
# prüfung verlangt weiterhin einen sauberen Stand.
PREFLIGHT_ACTION_FILE="$RUNTIME/$NAME.preflight-action.json"
# AP10: Reparatur- und Assistenzrunden sind Schrankeneinstellungen; ohne
# Gates-Modul gelten die bisherigen Voreinstellungen. Die Projektsumgebung
# kann REPAIR_ROUNDS als Zähler nicht dienen, weil der Projekt-Schlüssel
# denselben Namen trägt; gelesen wird ausschließlich GATE_REPAIR_ROUNDS.
REPAIR_MAX_ROUNDS="${GATE_REPAIR_ROUNDS:-2}"
ASSIST_MAX_ROUNDS="${GATE_ASSIST_ROUNDS:-10}"
# F25: Kennung der Session, die bei der nächsten Wiederholung fortgesetzt
# wird. Sie bleibt leer, solange kein Versuch eine Session hinterlassen hat.
RESUME_SESSION=""
# F25: Liest die zuletzt erfasste Hauptsession aus der Zustandsdatei, die der
# Protokollierungsfilter pflegt. Fehlt die Datei (ohne Filter) oder ist sie
# defekt, ist das Ergebnis leer; der Läufer startet dann wie bisher neu.
read_state_session() {
  python3 - "$LOG.state.json" <<'PY'
import json
import sys
try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        data = json.load(handle)
except (OSError, ValueError):
    raise SystemExit(0)
session = data.get("session")
if isinstance(session, str) and session:
    print(session)
PY
}
# B9/F22: Führt den Preflight bis zum Bestehen oder Abbruch aus. ``phase``
# unterscheidet den Laufstart (F27: --allow-dirty) vom Laufende (nie
# --allow-dirty). ``intro`` benennt die Prüfung in der Rückfrage.
preflight_with_assist() {
  local phase="$1" intro="$2"
  local heading="$intro"
  [ -n "$heading" ] || heading="Der Preflight für '$NAME' ist nicht bestanden."
  local args=(preflight --project "$P"
    --agents-dir "${VIBE_AGENTS_DIR:-$HOME/.config/opencode/agents}"
    --tester "${TESTER:-}" --reviewer "${REVIEWER:-}"
    --state "$STATE")
  if [ "$phase" = "start" ] && [ "${VIBE_KEEP_CHANGES:-0}" = "1" ]; then
    args+=(--allow-dirty)
  fi
  if [ "${VIBE_PREFLIGHT_ASSIST:-0}" = "1" ] \
      && [ -f "$BIN/vibe_questions.py" ] \
      && [ -f "$BIN/vibe_autonomous.py" ] \
      && [ -f "$BIN/vibe_storage.py" ]; then
    args+=(--assist --runtime "$RUNTIME" --project-name "$NAME"
      --timeout "${VIBE_PREFLIGHT_QUESTION_TIMEOUT:-600}"
      --action-file "$PREFLIGHT_ACTION_FILE" --assist-reason "$heading"
      --assist-max "$ASSIST_MAX_ROUNDS")
  fi
  ASSIST_ROUNDS=0
  while :; do
    rm -f -- "$PREFLIGHT_ACTION_FILE"
    PREFLIGHT_OUT="$(python3 "$PACKAGES_PY" "${args[@]}" \
      --assist-rounds "$ASSIST_ROUNDS" 2>&1)"
    PREFLIGHT_RC=$?
    if [ "$PREFLIGHT_RC" = 0 ]; then
      rm -f -- "$PREFLIGHT_ACTION_FILE"
      return 0
    fi
    PREFLIGHT_ACTION="$(python3 - "$PREFLIGHT_ACTION_FILE" <<'PY'
import json
import sys
try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        data = json.load(handle)
except (OSError, ValueError):
    data = {}
print(data.get("action") or "abort")
PY
)"
    PREFLIGHT_INSTRUCTION="$(python3 - "$PREFLIGHT_ACTION_FILE" <<'PY'
import json
import sys
try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        data = json.load(handle)
except (OSError, ValueError):
    data = {}
value = data.get("instruction")
print(value if isinstance(value, str) else "")
PY
)"
    PREFLIGHT_SOURCE="$(python3 - "$PREFLIGHT_ACTION_FILE" <<'PY'
import json
import sys
try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        data = json.load(handle)
except (OSError, ValueError):
    data = {}
value = data.get("source")
print(value if isinstance(value, str) else "")
PY
)"
    rm -f -- "$PREFLIGHT_ACTION_FILE"
    if [ "$PREFLIGHT_ACTION" = "agent" ]; then
      ASSIST_ROUNDS=$((ASSIST_ROUNDS + 1))
      if [ "$PREFLIGHT_SOURCE" = "findings" ]; then
        ASSIST_ORIGIN="einer aus den Befunden abgeleiteten Anweisung"
      elif [ "$PREFLIGHT_SOURCE" = "autonomous" ]; then
        ASSIST_ORIGIN="einer autonomen Entscheidung"
      else
        ASSIST_ORIGIN="der Anweisung des Nutzers"
      fi
      echo "PREFLIGHT: Agent wird mit $ASSIST_ORIGIN beauftragt (Runde $ASSIST_ROUNDS/$ASSIST_MAX_ROUNDS)." | tee -a "$LOG"
      ASSIST_PROMPT="$heading
Befunde:
$PREFLIGHT_OUT

Anweisung:
$PREFLIGHT_INSTRUCTION

Behebe ausschließlich diese Befunde im Projektordner. Verwirf keine fremden Änderungen. Committe nur, wenn die Anweisung es verlangt. Ändere keine Arbeitspakete und starte keinen neuen Lauf. Beende danach deine Arbeit; der Preflight wird erneut geprüft."
      run_agent_in "$P" "$ASSIST_PROMPT" "$NAME Preflight"
      ASSIST_RC=$?
      if [ "$ASSIST_RC" != 0 ]; then
        echo "ABBRUCH: Preflight-Agent fehlgeschlagen (Exit-Code $ASSIST_RC); die Befunde sind nicht behoben." | tee -a "$LOG"
        return 2
      fi
      continue
    fi
    printf '%s\n' "$PREFLIGHT_OUT" | tee -a "$LOG"
    return 1
  done
}
# V-026/B11: Ein äußeres Signal darf den Lauf nicht spurlos beenden — auch
# nicht während der Start-Preflight-Assistenz, die selbst eine Agentengruppe
# startet. Die Signal-Traps stehen deshalb vor dem ersten Preflight-Aufruf.
# Ein bereits beendeter Registereintrag bleibt unverändert (only-live).
EXTERN_ENDED=0
external_end() {
  local sig="$1" code="$2"
  [ "$EXTERN_ENDED" = 1 ] && return 0
  EXTERN_ENDED=1
  trap - HUP TERM INT
  echo "ABBRUCH: Lauf extern beendet (Signal $sig)." | tee -a "$LOG"
  register_finish "$code" ended "extern beendet (Signal $sig)" only-live
  # B11: Erst nach der Protokollierung die Agentengruppe beenden; der Läufer
  # selbst endet mit dem bisherigen Signal-Exit-Code.
  stop_agent_group
  exit "$code"
}
trap 'external_end HUP 129' HUP
trap 'external_end TERM 143' TERM
trap 'external_end INT 130' INT
preflight_with_assist start ""
PREFLIGHT_RC=$?
if [ "$PREFLIGHT_RC" != 0 ]; then
  echo "ABBRUCH: Preflight nicht bestanden. Es wurde kein Arbeitspaket gestartet." | tee -a "$LOG"
  register_finish 2 blocked
  exit 2
fi
BASE_BRANCH="$(git -C "$P" symbolic-ref --quiet --short HEAD)"
git -C "$P" worktree prune >>"$LOG" 2>&1 || true
# V-026: Verwaiste Einträge des eigenen Projekts vor dem Start als extern
# beendet kennzeichnen. Fremde Projekte und nicht prüfbare Sitzungen bleiben
# unverändert; es wird niemals eine Sitzung beendet.
if [ -f "$RUNS_PY" ]; then
  python3 "$RUNS_PY" prune --runtime "$RUNTIME" --project "$P" \
    --note "extern beendet (Sitzung fehlt)" >>"$LOG" 2>&1 || true
fi
register_start
# AP19: Ab jetzt ist RUN_ID bekannt. Der Filter wird erneut eingerichtet,
# damit Paket-, Reparatur- und Assistenzsessions die Lauf-ID tragen und ihr
# Zustand aus dem Laufregister abgeleitet werden kann (ohne Register bleibt
# es beim cat-Rückfall). Die Zuweisung steht bewusst ohne Einrückung, damit
# sie als zweite Filterzuweisung am Zeilenanfang erkennbar bleibt.
if [ -f "$RUNS_PY" ]; then
STREAM_FILTER=(python3 "$RUNS_PY" stream --state "$LOG.state.json" --attempt --sessions "$RUNTIME/sessions.json" --session-project "$P" --session-name "$NAME" --session-run "$RUN_ID" --session-agent "$AGENT" --session-harness "$HARNESS")
fi
if [ "$HARNESS" = "pi" ]; then RUN_MODE="Pi --print"
elif [ "$PRIVATE_SERVER" = 1 ]; then RUN_MODE="privater opencode-Server"
else RUN_MODE="$SERVER_ARGS"; fi
echo "Lauf: ${RUN_ID:-ohne Register}, Harness: $HARNESS, Modus: $RUN_MODE, Agent: $AGENT, Sandbox: $SANDBOX_STATE, höchstens $MAXP Pakete, höchstens $MAXR Wiederholungen je Paket" | tee -a "$LOG"
PAUSED=0; LAST_ID=""; STOP=0; PACKAGES=0; SKIP=""
CLOSED=(); CLOSED_BRANCH=(); CLOSED_COMMIT=(); CLOSED_PR=()
BLOCKED_IDS=(); BLOCKED_REPORT=(); BLOCK_REASON=""
WAITING_MERGE=()
VERIFIED_SQUASH=0
record_block() {
  BLOCKED_IDS+=("$1")
  BLOCKED_REPORT+=("$1 ($2)")
}
# AP4 (T-G1): PR-only-Abschluss. Der Lauf hält an, die Arbeitskopie bleibt
# registriert und das Ticket bleibt offen mit Blockievermerk; gemergt wird
# erst vom Eigentümer (oder per ``vibe package close``).
pr_only_fallback() {
  local note="PR-only: wartet auf Merge des Eigentümers; Merge-Request $PR_URL; danach 'vibe package close $NAME $ID'"
  [ -n "${1:-}" ] && note="PR-only-Rückfall ($1): $note"
  python3 "$PACKAGES_PY" mark-waiting --project "$P" --id "$ID" \
    --note "$note" --pr-url "$PR_URL" >>"$LOG" 2>&1 || true
  record_block "$ID" "PR-only: wartet auf Merge (Merge-Request $PR_URL)"
  WAITING_MERGE+=("$ID — Merge-Request $PR_URL; danach: vibe package close $NAME $ID")
  echo "WARTET AUF MERGE: $ID — Merge-Request $PR_URL; danach: vibe package close $NAME $ID" | tee -a "$LOG"
  STOP=1
}
# AP4 (T-G1): Nach erfolgreichem Abschluss den Nachweis zurückschreiben, die
# Arbeitskopie entfernen, Registry/Sessions vergessen und das Paket als
# geschlossen vermerken. Rückgabe 0 = geschlossen, 1 = blockiert.
finish_closed_package() {
  if ! sync_work_notes; then
    BLOCK_REASON="Ticket-Nachweis für $ID konnte nicht in den Projektordner geschrieben werden."
    record_block "$ID" "$BLOCK_REASON"
    echo "BLOCKIERT: $BLOCK_REASON" | tee -a "$LOG"
    return 1
  fi
  cleanup_worktree
  if [ -f "$RUNS_PY" ]; then
    python3 "$RUNS_PY" worktree-unregister --runtime "$RUNTIME" --project "$P" --id "$ID" >>"$LOG" 2>&1 || true
  fi
  CLOSED+=("$ID")
  CLOSED_BRANCH+=("$BRANCH")
  CLOSED_COMMIT+=("$(git -C "$P" rev-parse --short HEAD)")
  CLOSED_PR+=("$PR_URL")
  PACKAGE_DONE=1
  return 0
}
# Arbeitsnotiz (AGENTS.md am Projektstamm) und die sichtbare Ticketdatei
# TICKET-<ID>.json sind Laufzeitstand wie in dirty_report
# (bin/vibe_packages.py). Ihre uncommitteten Änderungen blockieren die
# Integrationsprüfungen des Läufers nicht; andere Änderungen bleiben sichtbar.
work_note_noise() {
  grep -vE '^.. (AGENTS\.md|TICKET-[A-Za-z0-9_.-]+\.json)$' || true
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
      for i in "${!CLOSED[@]}"; do
        id="${CLOSED[$i]}"
        if [ -n "${CLOSED_PR[$i]:-}" ]; then
          echo "Geschlossen: $id — Branch ${CLOSED_BRANCH[$i]}, Commit ${CLOSED_COMMIT[$i]}, Merge-Request ${CLOSED_PR[$i]}"
        else
          echo "Geschlossen: $id — Branch ${CLOSED_BRANCH[$i]}, Commit ${CLOSED_COMMIT[$i]}, Merge-Request: keine (GitHub nicht aktiv oder kein origin)"
        fi
      done
    fi
    if [ "${#BLOCKED_REPORT[@]}" -eq 0 ]; then
      echo "Blockiert: keine"
    else
      for blocked in "${BLOCKED_REPORT[@]}"; do echo "Blockiert: $blocked"; done
    fi
    if [ "${#WAITING_MERGE[@]}" -eq 0 ]; then
      echo "Wartet auf Merge: keine"
    else
      for waiting in "${WAITING_MERGE[@]}"; do echo "Wartet auf Merge: $waiting"; done
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
  # Zwischen zwei Paketen muss der Integrationsstand sauber bleiben. Sonst
  # würde das nächste Paket auf einem fremden, ungeprüften Stand aufsetzen.
  # F27: Ein ausdrücklich angeforderter Neustart lässt vorhandene Änderungen
  # bis zur Gesamtprüfung zu; sie bleiben unverändert und werden nicht Teil
  # der Paketbranches. Die abschließende Prüfung bleibt streng.
  DIRTY_NOW="$(git -C "$P" status --porcelain | work_note_noise)"
  if [ -n "$DIRTY_NOW" ] && [ "${VIBE_KEEP_CHANGES:-0}" = "1" ]; then
    echo "HINWEIS: Nicht committete Änderungen bleiben unverändert; die Gesamtprüfung verlangt weiterhin einen sauberen Integrationsstand." | tee -a "$LOG"
    DIRTY_NOW=""
  fi
  if [ -n "$DIRTY_NOW" ]; then
    BLOCK_REASON="Integrationsstand ist nicht sauber: $DIRTY_NOW"
    record_block "INTEGRATION" "$BLOCK_REASON"
    echo "BLOCKIERT: $BLOCK_REASON" | tee -a "$LOG"
    STOP=1; break
  fi
  if ! select_item; then echo "Keine offenen Arbeitspakete mehr." | tee -a "$LOG"; break; fi
  if [ "$ORDERED" = 1 ]; then
    echo "Auswahl aus projektweiser Priorisierung (PACKAGE_ORDER, verbindlich)." | tee -a "$LOG"
  fi
  # AP4 (T-W1): Ein ausdrücklich bevorzugtes Resume-Paket, das nicht gewählt
  # wurde, ist geschlossen — normaler Rückfall mit Protokolleintrag.
  if [ -n "$RESUME_PACKAGE" ] && [ "$ID" != "$RESUME_PACKAGE" ]; then
    echo "HINWEIS: Resume-Paket $RESUME_PACKAGE ist nicht mehr offen (geschlossen); normale Auswahl." | tee -a "$LOG"
  fi
  # AP9: Vor jedem neuen Arbeitspaket den Haupt-Branch aktualisieren (nur
  # bei GitHub-Konfiguration; sonst bewusster Skip). Ein Fehlschlag erzeugt
  # nur einen Hinweis, blockiert das Paket aber nicht.
  if ! python3 "$PACKAGES_PY" github-pull --project "$P" >>"$LOG" 2>&1; then
    echo "HINWEIS: GitHub-Pull des Haupt-Branchs vor $ID fehlgeschlagen; es wird mit dem aktuellen Stand weitergearbeitet." | tee -a "$LOG"
  fi
  PACKAGES=$((PACKAGES + 1))
  PACKAGE_BASE="$(git -C "$P" rev-parse HEAD)"
  echo "=== [$NAME] Arbeitspaket $ID, Durchgang $PACKAGES/$MAXP  $(date +%T) ===" | tee -a "$LOG"
  if ! create_worktree; then
    BLOCK_REASON="Arbeitskopie/Branch für $ID konnte nicht angelegt werden."
    record_block "$ID" "$BLOCK_REASON"
    echo "BLOCKIERT: $BLOCK_REASON" | tee -a "$LOG"
    STOP=1; break
  fi
  # AP4 (T-W2): Registry nach Anlage/Reconnect aktualisieren (Upsert).
  if [ -f "$RUNS_PY" ]; then
    python3 "$RUNS_PY" worktree-register --runtime "$RUNTIME" --project "$P" \
      --id "$ID" --branch "$BRANCH" --path "$WT" --base-commit "$PACKAGE_BASE" \
      >>"$LOG" 2>&1 || true
  fi
  # AP4 (T-W1): Ab jetzt trägt der Erfassungsfilter den Worktree-Anhang des
  # Pakets; vor dem ersten Paket (Preflight) bleibt er ohne diese Angaben.
  if [ -f "$RUNS_PY" ]; then
STREAM_FILTER=(python3 "$RUNS_PY" stream --state "$LOG.state.json" --attempt --sessions "$RUNTIME/sessions.json" --session-project "$P" --session-name "$NAME" --session-run "$RUN_ID" --session-agent "$AGENT" --session-harness "$HARNESS" --session-worktree "$WT" --session-package "$ID" --session-branch "$BRANCH")
  fi
  # Die Arbeitsnotizen sind Laufzeitstand und nicht versioniert; die
  # Arbeitskopie enthält sie daher nicht. Sie werden hineinkopiert, damit
  # Agent und Abschlussschranke den aktuellen Ticketstand sehen. Bei RECONNECT
  # ist die Arbeitskopie während des Laufs kanonisch; copy-notes wird dann
  # übersprungen.
  if [ "$RECONNECT" = 1 ]; then
    echo "RECONNECT: copy-notes übersprungen (Arbeitskopie ist kanonisch)." >>"$LOG"
  elif ! python3 "$PACKAGES_PY" copy-notes \
      --project "$P" --worktree "$WT" --id "$ID" >>"$LOG" 2>&1; then
    BLOCK_REASON="Arbeitsnotizen konnten nicht in die Arbeitskopie übernommen werden."
    record_block "$ID" "$BLOCK_REASON"
    echo "BLOCKIERT: $BLOCK_REASON" | tee -a "$LOG"
    STOP=1; break
  fi
  # AP7 (T-V21): Hash der transportierten Datei am Paketstart erfassen.
  # Eine beim Start fehlende Datei hat keinen Wächter (best effort).
  PKG_HASH_PROJECT_ENV=""
  if [ -f "$WT/.vibe/project.env" ]; then
    PKG_HASH_PROJECT_ENV="$(package_file_hash "$WT/.vibe/project.env")"
  fi
  PROMPT="Arbeitspaket $ID. Das Ticket liegt als maschinenlesbare Datei $WT/TICKET-$ID.json vor.
Titel: $TITLE
Beschreibung: $DESCRIPTION
Bearbeite NUR dieses Arbeitspaket gemäß deinem Workflow. Du arbeitest in der isolierten Arbeitskopie $WT auf dem Branch $BRANCH; der Integrationsstand $P bleibt unberührt. Committe dort mit dem Präfix '$ID:'.
Vor dem Abschluss müssen im Paketbranch vorliegen: ein Commit mit Präfix '$ID:', das Ticket in $WT/TICKET-$ID.json mit state \"done\" und ausgefüllten Feldern commit (Hash im Paketbranch) und test (Methode oder Datei), docs/features/$ID.md und ein Review unter docs/reviews/$ID-review-*.md mit 'Verdict: PASS'. TICKET-$ID.json ist Laufzeitstand und wird nie committet; die Arbeitskopie muss sauber sein. Sonst gilt das Paket als BLOCKIERT und der Lauf hält an.
$QUESTION_HINT"
  ATTEMPT=0
  PACKAGE_DONE=0
  # F25: Je Paket neu; die Sessions des Vorgängerpakets werden nicht
  # weitergeführt.
  # AP14: Mit angeforderter Fortsetzung (VIBE_CONTINUE_SESSION vom Start-
  # befehl) beginnt auch jedes folgende Paket desselben Laufs in derselben
  # Session (Fortsetzungskette); der erste Versuch erhält --session. Ohne
  # diese Anforderung bleibt es beim F25-Verhalten.
  RESUME_SESSION="$CONTINUE_SESSION"
  if [ -n "$RESUME_SESSION" ] && [ "$HARNESS" != "pi" ]; then
    echo "Fortsetzung in Session $RESUME_SESSION" | tee -a "$LOG"
  fi
  while [ "$ATTEMPT" -lt "$TRIES_PER_ITEM" ]; do
    ATTEMPT=$((ATTEMPT + 1))
    echo "--- Versuch $ATTEMPT/$TRIES_PER_ITEM für $ID in $WT ---" | tee -a "$LOG"
    LOG_START_LINE="$(wc -l < "$LOG" 2>/dev/null || echo 0)"
    # F25: Stand der erfassten Hauptsession vor dem Versuch. Die Kennung des
    # Versuchs selbst wird gegen diesen Stand abgeglichen, damit Kennungen aus
    # früheren Versuchen oder Vorläufen (z. B. Preflight-Agent) nicht als
    # Fortsetzung gelten, obwohl der Versuch selbst keine Session erfasst hat.
    BASE_SESSION="$(read_state_session)"
    case "$BASE_SESSION" in
      *[!A-Za-z0-9_-]*) BASE_SESSION="" ;;
    esac
    run_agent
    RC=$?
    echo "=== Agent beendet, Exit-Code $RC ===" | tee -a "$LOG"
    # B13: Ein nicht startbarer privater Server ist ein Laufabbruch, kein
    # wiederholbarer Agentenfehler; ohne Server gäbe es kein Dashboard-Ziel.
    if [ -f "$SERVER_FAILED_FILE" ]; then
      BLOCK_REASON="$(cat "$SERVER_FAILED_FILE")"
      record_block "$ID" "$BLOCK_REASON"
      echo "ABBRUCH: $BLOCK_REASON" | tee -a "$LOG"
      STOP=1
      break
    fi
    if [ "$RC" = 0 ]; then
      REPAIR_ROUNDS=0
      REPAIR_ERROR=""
      REPAIR_FINDING=""
      PACKAGE_OK=0
      REPAIR_RC=0
      while :; do
        # AP7 (T-V21): Vor jeder Paketprüfung die transportierte
        # .vibe/project.env erneut hashen — auch nach einer Reparaturrunde.
        # Eine Abweichung (Veränderung oder Löschung) ist Manipulation der
        # autoritativen Projektwerte: blockieren ohne Reparaturrunde.
        # GH-46: .vibe/verify-baseline wird nicht mehr bewacht.
        if ! guard_transported_files; then
          BLOCK_REASON="Transportierte Konfiguration wurde verändert oder entfernt: $TAMPERED_FILE"
          record_block "$ID" "$BLOCK_REASON"
          echo "BLOCKIERT: $BLOCK_REASON" | tee -a "$LOG"
          STOP=1
          break
        fi
        if ! run_package_tests; then
          REPAIR_FINDING="Pakettests für $ID sind nicht grün."
          REPAIR_DETAILS="$PACKAGE_TEST_OUT"
        elif ! gate_ok; then
          REPAIR_FINDING="Abschlussschranke für $ID nicht erfüllt."
          REPAIR_DETAILS="$GATE_OUT"
        else
          PACKAGE_OK=1
          break
        fi
        repair_package_finding "$REPAIR_FINDING" "$REPAIR_DETAILS"
        REPAIR_RC=$?
        [ "$REPAIR_RC" != 0 ] && break
      done
      if [ "$STOP" = 1 ]; then
        break
      fi
      if [ "$REPAIR_RC" = 2 ]; then
        # AP10: Bewusstes Fortsetzen — das Paket wird auf Nutzer- oder
        # autonome Entscheidung übersprungen. Der Blockievermerk verhindert
        # die erneute Auswahl; Merge, Abschlussschranke und STOP bleiben
        # unangetastet, der Lauf fährt mit dem nächsten Paket fort.
        if ! python3 "$PACKAGES_PY" mark-blocked --project "$P" --id "$ID" \
            --note "$BARRIER_NOTE" >>"$LOG" 2>&1; then
          echo "WARNUNG: Blockievermerk für $ID konnte nicht geschrieben werden; das Paket wird nur in diesem Lauf übersprungen." | tee -a "$LOG"
        fi
        SKIP="$SKIP,$ID"
        record_block "$ID" "$BARRIER_NOTE"
        echo "BLOCKIERT: $ID $BARRIER_NOTE." | tee -a "$LOG"
        break
      fi
      if [ "$PACKAGE_OK" != 1 ]; then
        if [ -n "$REPAIR_ERROR" ]; then
          BLOCK_REASON="$REPAIR_ERROR $REPAIR_FINDING"
        else
          BLOCK_REASON="$REPAIR_FINDING"
        fi
        record_block "$ID" "$BLOCK_REASON"
        echo "BLOCKIERT: $BLOCK_REASON" | tee -a "$LOG"
        STOP=1; break
      fi
      # AP4 (T-G7): Mergeability vor dem Abschluss sichern (nur GitHub-Modus;
      # ohne Verknüpfung/origin bewusster Skip). Konflikt → eine begrenzte
      # Reparaturrunde; besteht er im zweiten Versuch, wird abgebrochen und
      # das Paket blockiert.
      if ! ensure_mergeable_package; then
        BLOCK_REASON="$REPAIR_ERROR"
        record_block "$ID" "$BLOCK_REASON"
        echo "BLOCKIERT: $BLOCK_REASON" | tee -a "$LOG"
        STOP=1; break
      fi
      # B16: Nach grüner Schranke ist der GitHub-Abschluss (Push und
      # Merge-Request) eine echte Schranke. Bei Fehlschlag wird nicht lokal
      # gemergt, das Ticket bleibt offen und die Arbeitskopie bleibt liegen.
      GH_COMPLETE_OUT="$(python3 "$PACKAGES_PY" github-complete --project "$P" \
          --branch "$BRANCH" --id "$ID" 2>>"$LOG")"
      GH_COMPLETE_RC=$?
      printf '%s\n' "$GH_COMPLETE_OUT" >>"$LOG"
      if [ "$GH_COMPLETE_RC" -ne 0 ]; then
        # Ohne stdout (z. B. SystemExit bei fehlendem vibe_github.py) stünde
        # die Ursache nur im Protokoll; dann eine feste Ersatzursache nennen.
        reason="${GH_COMPLETE_OUT%%$'\n'*}"
        [ -n "$reason" ] || reason="keine Ausgabe des Unterbefehls (Details im Protokoll; fehlt vibe_github.py in der Installation?)"
        BLOCK_REASON="GitHub-Abschluss für $ID fehlgeschlagen (Push/Merge-Request): $reason"
        record_block "$ID" "$BLOCK_REASON"
        echo "BLOCKIERT: $BLOCK_REASON" | tee -a "$LOG"
        STOP=1; break
      fi
      # Die ABGABE-Zeile nennt den Merge-Request; "keine" bedeutet bewusster
      # Skip (GitHub nicht aktiv oder kein origin).
      PR_URL="$(printf '%s\n' "$GH_COMPLETE_OUT" | sed -n 's/^ABGABE: .*, Merge-Request //p')"
      [ "$PR_URL" = "keine" ] && PR_URL=""
      # AP4 (T-W2): Registry um Merge-Request-URL und Session ergänzen (Upsert).
      if [ -f "$RUNS_PY" ]; then
        WT_SESSION="$(read_state_session)"
        python3 "$RUNS_PY" worktree-register --runtime "$RUNTIME" --project "$P" \
          --id "$ID" --branch "$BRANCH" --path "$WT" --base-commit "$PACKAGE_BASE" \
          --pr-url "$PR_URL" --session "$WT_SESSION" >>"$LOG" 2>&1 || true
      fi
      if [ -n "$PR_URL" ]; then
        # GitHub-Modus: Ein Merge-Request steht offen. Ohne GITHUB_AUTO_MERGE
        # bleibt es beim PR-only-Abschluss; mit "1" wird per REST squash-gemergt.
        if [ "${GITHUB_AUTO_MERGE:-}" = "1" ]; then
          GH_MERGE_OUT="$(python3 "$PACKAGES_PY" github-merge --project "$P" \
              --branch "$BRANCH" --id "$ID" 2>>"$LOG")"
          GH_MERGE_RC=$?
          printf '%s\n' "$GH_MERGE_OUT" >>"$LOG"
          if [ "$GH_MERGE_RC" = 2 ]; then
            # Konflikt: genau EIN begrenzter Reparaturdurchlauf — Basis mergen,
            # erneut pushen und mergen. Kein weiterer Versuch, keine Schleife.
            if ensure_mergeable_package; then
              python3 "$PACKAGES_PY" github-push --project "$P" --branch "$BRANCH" >>"$LOG" 2>&1
              GH_MERGE_OUT="$(python3 "$PACKAGES_PY" github-merge --project "$P" \
                  --branch "$BRANCH" --id "$ID" 2>>"$LOG")"
              GH_MERGE_RC=$?
              printf '%s\n' "$GH_MERGE_OUT" >>"$LOG"
            fi
          fi
          if [ "$GH_MERGE_RC" = 0 ]; then
            VERIFIED_SQUASH=1
            # Integrationsbranch auf die Fernspitze bringen (fetch + ff-only).
            python3 "$PACKAGES_PY" github-pull --project "$P" >>"$LOG" 2>&1 || true
            if ! finish_closed_package; then
              STOP=1; break
            fi
            # Der Worktree ist nach dem Squash-Merge endgültig geschlossen;
            # seine Session-Einträge werden vergessen (T-W1).
            if [ -f "$RUNS_PY" ]; then
              python3 "$RUNS_PY" sessions-forget-worktree --runtime "$RUNTIME" --worktree "$WT" >>"$LOG" 2>&1 || true
            fi
            break
          fi
          # Auto-Merge scheiterte (Konflikt blieb oder Token/API/Netz): der PR
          # steht offen; Rückfall auf PR-only, der Eigentümer kann manuell mergen.
          pr_only_fallback "Auto-Merge nicht möglich (Merge-Request steht offen)"
          break
        fi
        pr_only_fallback
        break
      fi
      # Lokal-ohne-GitHub (github-complete-Skip): Bestandsweg ff-only Merge.
      if ! merge_package; then
        BLOCK_REASON="Merge für $ID fehlgeschlagen."
        record_block "$ID" "$BLOCK_REASON"
        echo "BLOCKIERT: $BLOCK_REASON" | tee -a "$LOG"
        STOP=1; break
      fi
      VERIFIED_SQUASH=0
      if ! finish_closed_package; then
        STOP=1; break
      fi
      break
    fi
    CLASS="$(python3 "$PACKAGES_PY" classify --exit-code "$RC" --log "$LOG" --since "$LOG_START_LINE" 2>>"$LOG")"
    case "$CLASS" in
      quota|auth)
        # V-027: Das globale Limitverhalten entscheidet. "stop" ist die
        # Voreinstellung und hält sofort an; "continue" behandelt den Fehler
        # wie einen wiederholbaren Fehler im Rahmen der Wiederholungslimits.
        if [ "$LIMIT_MODE" != "continue" ]; then
          if [ "$CLASS" = "quota" ]; then
            BLOCK_REASON="Quota/Kontingent bei $ID; der Lauf hält sofort an."
          else
            BLOCK_REASON="Anmeldung/Autorisierung bei $ID fehlgeschlagen; der Lauf hält sofort an."
          fi
          record_block "$ID" "$BLOCK_REASON"
          echo "BLOCKIERT: $BLOCK_REASON" | tee -a "$LOG"
          STOP=1; break
        fi
        echo "HINWEIS: Limitverhalten 'continue' — $CLASS bei $ID wird wie ein wiederholbarer Fehler behandelt." | tee -a "$LOG"
        ;&
      *)
        printf '\a\a\a'; echo "Agent mit Fehler beendet (Fehlerklasse '$CLASS')." | tee -a "$LOG"
        # V-027: Quota- und Anmeldefehler werden im Modus "continue"
        # ausschließlich im Rahmen der Wiederholungslimits erneut versucht.
        # Sie lösen weder eine automatische Router-Neuverbindung noch eine
        # manuelle IP-Abfrage aus.
        if [ "$CLASS" != "quota" ] && [ "$CLASS" != "auth" ]; then
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
        if [ "$ATTEMPT" -ge "$TRIES_PER_ITEM" ]; then
          echo "Überspringe $ID nach $TRIES_PER_ITEM Versuchen ($MAXR Wiederholungen, Wiederholungslimit erreicht, von Hand prüfen)." | tee -a "$LOG"
          record_block "$ID" "Agentenfehler ($CLASS)"
          SKIP="$SKIP,$ID"
          break
        fi
        # F25: Die im gescheiterten Versuch erfasste Session wird bei der
        # Wiederholung fortgesetzt (einfaches Continue), statt das Paket von
        # neuem zu beginnen. Quelle ist die Zustandsdatei des
        # Protokollierungsfilters (Maschinenquelle; Agenten-Klartext kann sie
        # nicht verfälschen). Ein Versuch, der selbst keine Session erfasst
        # hat (Stand unverändert), löst keine Fortsetzung aus; in einer
        # laufenden Fortsetzungskette zählt der zuletzt erfasste Stand. Die
        # [Session]-Zeile dient der Anzeige im Laufprotokoll.
        ATTEMPT_SESSION="$(read_state_session)"
        case "$ATTEMPT_SESSION" in
          *[!A-Za-z0-9_-]*) ATTEMPT_SESSION="" ;;
        esac
        if [ -n "$ATTEMPT_SESSION" ] && [ "$ATTEMPT_SESSION" != "$BASE_SESSION" ]; then
          RESUME_SESSION="$ATTEMPT_SESSION"
        fi
        if [ -n "$RESUME_SESSION" ]; then
          echo "Wiederhole $ID nach Fehlerklasse '$CLASS' (Versuch $ATTEMPT/$TRIES_PER_ITEM); die Session $RESUME_SESSION wird fortgesetzt." | tee -a "$LOG"
        else
          echo "Wiederhole $ID nach Fehlerklasse '$CLASS' (Versuch $ATTEMPT/$TRIES_PER_ITEM)." | tee -a "$LOG"
        fi
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
# B9: Mit aktiver Assistenz darf der Agent den Stand zuvor bereinigen; ohne
# Assistenz oder nach Abbruch bleibt es beim bisherigen Blockieren.
INTEGRATION_DIRTY="$(git -C "$P" status --porcelain | work_note_noise)"
if [ -n "$INTEGRATION_DIRTY" ]; then
  preflight_with_assist end "Der Abschluss für '$NAME' ist nicht möglich: Der Integrationsstand ist nicht sauber."
  INTEGRATION_RC=$?
  INTEGRATION_DIRTY="$(git -C "$P" status --porcelain | work_note_noise)"
  if [ "$INTEGRATION_RC" != 0 ] || [ -n "$INTEGRATION_DIRTY" ]; then
    BLOCK_REASON="Integrationsstand ist nicht sauber: $INTEGRATION_DIRTY"
    record_block "INTEGRATION" "$BLOCK_REASON"
    report
    register_finish 1 blocked
    echo "ABBRUCH: $BLOCK_REASON" | tee -a "$LOG"
    exit 1
  fi
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
echo "Noch Lücken (oder Durchgangsgrenze erreicht), Prüfung Exit-Code $VRC. Blockierte/übersprungene Punkte in der Ticketübersicht (Dashboard) prüfen." | tee -a "$LOG"; exit "$VRC"
