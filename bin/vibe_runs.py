#!/usr/bin/env python3
"""Laufregister für Agentenläufe (V-015).

Ein Lauf ist genau eine Ausführung des Paket-Läufers für ein Projekt. Jeder
Lauf hat eine eindeutige ID, eine eigene tmux-Sitzung, ein eigenes Lauf- und
Prüfprotokoll und einen eigenen Zustand. Das Register liegt als
``<laufzeit>/runs.json`` neben den Logs.

Eigenschaften:

* **Eindeutige IDs** — Zeitstempel plus Zufallsanteil; auch zwei Läufe
  desselben Projekts kollidieren nicht.
* **Parallele Projekte** — jede Änderung liest und schreibt unter einer
  Sperrdatei und ersetzt die Datei atomar. Ein Lauf kann den Eintrag eines
  anderen Projekts nicht überschreiben. Wo das Dateisystem keine wirksame
  Sperre bietet (z. B. FUSE/NTFS), kann der letzte Schreiber gewinnen; das
  wird hier nicht als garantiert zugesichert.
* **Begrenzte Datei** — nur die letzten Einträge bleiben erhalten.

Dieses Modul startet keine Prozesse, spricht nicht mit dem Netzwerk und ruft
keine Modelle auf. Es schreibt ausschließlich im Laufzeitordner und nutzt nur
die Standardbibliothek plus die im selben Ordner gelieferte
Gemeinschaftsschicht
``vibe_storage`` (liegt im selben ``bin``-Ordner): ``bin/vibe-run.sh`` ruft
es als Skript auf, auch wenn die übrige Installation unvollständig ist.

Aufruf aus ``bin/vibe`` und ``bin/vibe-run.sh``:

  vibe_runs.py key <projekt> <laufzeit> [bevorzugt]
  vibe_runs.py start --runtime R --project P --name N --key K --agent A
                     [--session S] [--log L] [--verify-log V] [--id ID]
                     [--state S]
  vibe_runs.py finish --runtime R --id ID [--exit-code N] [--state finished]
  vibe_runs.py rotate <logdatei> [--max-bytes N] [--keep N]
"""
import argparse
import contextlib
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time

# Die Gemeinschaftsschicht liegt als Datei im selben bin-Ordner (Skriptpfad
# ist sys.path[0]); aus ihr kommt die gemeinsame Verzeichnis-Fsync-Hilfe.
import vibe_storage

try:  # Neues Modul: ohne Installation bleibt vibe_runs importierbar.
    import vibe_tickets
except ImportError:  # pragma: no cover - Installation ohne vibe_tickets
    vibe_tickets = None

try:  # Nur unter POSIX verfügbar; ohne Sperre bleibt der letzte Schreibvorgang gewinnen.
    import fcntl
except ImportError:  # pragma: no cover - Windows ohne vibe-Betrieb
    fcntl = None

try:  # Neues Modul: ohne Installation bleibt vibe_runs importierbar.
    import vibe_usage
except ImportError:  # pragma: no cover - Installation ohne vibe_usage
    vibe_usage = None

KEEP_RECORDS = 100
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_KEEP = 3
LIVE_STATES = ("starting", "running")
STATES = ("starting", "running", "finished", "stopped", "paused", "failed", "ended", "blocked")
# AP19: Session-Register. Die Kennung ist zugleich Datei- und Sitzungsname;
# deshalb gilt dieselbe strenge Zeichenklasse wie für Laufschlüssel.
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
SESSION_LIMIT_DEFAULT = 5
SESSION_LIMIT_MAX = 100
# AP4 (T-W2): Branch-Namen des Worktree-Registers folgen dem Git-Refname-Muster
# (Teilmenge wie in vibe_github); keine "..", kein ".lock"-Ende, keine Leer-
# oder Steuerzeichen.
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
# Altersgrenze für das Aufräumen von Sessions ohne (noch existierenden)
# Worktree-Anhang (30 Tage), ausgelöst ausschließlich durch sessions-finish.
SESSION_PRUNE_DAYS = 30
# Laufzustand -> (Anzeigezustand, deutsches Label). "ended" ist der unerwartete
# Abbruch und wird bewusst als "aborted" vorgetragen; ein fehlender Lauf bleibt
# "unknown". Die Tabelle ist die einzige Quelle für state/state_label.
SESSION_STATES = {
    "starting": ("running", "läuft"),
    "running": ("running", "läuft"),
    "finished": ("finished", "abgeschlossen"),
    "failed": ("failed", "fehlgeschlagen"),
    "stopped": ("stopped", "gestoppt"),
    "paused": ("paused", "pausiert"),
    "blocked": ("blocked", "blockiert"),
    "ended": ("aborted", "abgebrochen"),
}


def clean_key(text):
    """Bildet aus einem beliebigen Namen einen Datei- und Sitzungsschlüssel."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(text or ""))


def digest(path):
    """Kurzer, stabiler Fingerabdruck eines Projektpfads."""
    real = os.path.realpath(os.path.abspath(str(path or "")))
    return hashlib.sha1(real.encode("utf-8", "surrogateescape")).hexdigest()[:8]


def new_run_id(key, now=None):
    """Eindeutige Lauf-ID: lesbarer Schlüssel, Zeitstempel, Zufallsanteil."""
    base = clean_key(key) or "lauf"
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    return f"{base}-{stamp}-{secrets.token_hex(3)}"


def rotate_log(path, max_bytes=DEFAULT_MAX_BYTES, keep=DEFAULT_KEEP):
    """Verschiebt eine zu große Logdatei nach ``.1`` und nummeriert ältere um.

    Es bleiben höchstens ``keep`` Archive. Rückgabe: True, wenn rotiert wurde.
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return False
    if max_bytes is None or int(keep) < 1 or size < int(max_bytes):
        return False
    for index in range(int(keep) - 1, 0, -1):
        source = f"{path}.{index}"
        if os.path.exists(source):
            os.replace(source, f"{path}.{index + 1}")
    os.replace(path, f"{path}.1")
    return True


SUBAGENT_FINISHED = ("completed", "error", "failed", "cancelled", "canceled")
# B12: opencode ≥ 2.3 führt Subagenten standardmäßig im Hintergrund; das
# task-Werkzeug der Hauptsession ist sofort "completed", während die
# Metadaten den tatsächlichen Zustand (u. a. "running") nennen. Nur bekannte
# Werte werden übernommen, fremde Formen bleiben unverändert.
SUBAGENT_STATUSES = ("running",) + SUBAGENT_FINISHED
# opencode nennt das Werkzeug intern "task"; ältere Stände und die Anzeige
# verwenden "subagent". Beide Formen werden erkannt.
SUBAGENT_TOOLS = ("task", "subagent")
# B11: Die Zustandsdatei darf durch viele abgeschlossene Subagenten nicht
# unbegrenzt wachsen. Laufende Einträge werden bevorzugt erhalten; bei mehr
# als MAX_SUBAGENTS gleichzeitig laufenden Einträgen können die ältesten
# laufenden verdrängt werden.
MAX_SUBAGENTS = 50
# GH-104: Beendete Einträge verlassen die aktive Liste und wandern in einen
# begrenzten Verlauf. Der Verlauf hält die Ausgabe für /api/subagent-output
# und /api/steer bereit; die ältesten Einträge fallen zuerst heraus.
MAX_SUBAGENT_HISTORY = 50
# B11: Auch die Ausgabe je Eintrag braucht ein Budget. Gespeichert wird nur
# der jüngste Tail; das begrenzt Zustandsdatei, Schreib-/fsync-Kosten und die
# Listenantwort. Die volle Live-Ausgabe liefert /api/subagent-output.
MAX_SUBAGENT_OUTPUT_BYTES = 64 * 1024


def output_tail(text, budget):
    """Liefert die letzten ``budget`` UTF-8-Bytes von ``text``.

    Ein Mehrbyte-Zeichen, das durch den Schnitt zerteilt würde, wird am
    Anfang des Tails verworfen.
    """
    value = str(text or "")
    raw = value.encode("utf-8")
    if len(raw) <= budget:
        return value
    return raw[-budget:].decode("utf-8", "ignore")

# Pi 1.5.0 liefert im JSON-Modus (--mode json) genau diese Ereignistypen
# (Pi-Dokumentation docs/json.md). Der Erfassungsfilter erkennt die Form
# automatisch anhand des Ereignistyps; opencode nutzt eine andere Menge
# (text/reasoning/error/tool_use), so dass sich beide Formen nicht stören.
PI_EVENT_TYPES = (
    "session",
    "agent_start", "agent_end", "agent_settled",
    "turn_start", "turn_end",
    "message_start", "message_update", "message_end",
    "tool_execution_start", "tool_execution_update", "tool_execution_end",
    "queue_update", "entry_appended", "session_info_changed",
    "thinking_level_changed",
    "compaction_start", "compaction_end",
    "auto_retry_start", "auto_retry_end",
    "summarization_retry_scheduled", "summarization_retry_attempt_start",
    "summarization_retry_finished",
    "bash_execution_update", "extension_error",
)


def subagent_state_path(log_path):
    """Zustandsdatei mit Hauptsession und erfassten Subagenten je Laufprotokoll."""
    return str(log_path) + ".state.json"


def load_subagent_state(path):
    """Liest die Zustandsdatei; fehlende oder defekte Daten sind ein leerer Zustand.

    GH-104: ``subagents`` ist die aktive Liste; ``history`` hält beendete
    Einträge samt Ausgabe. Beide Listen werden unverändert übernommen und erst
    beim Speichern begrenzt.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {"session": "", "subagents": [], "history": []}
    if not isinstance(data, dict):
        return {"session": "", "subagents": [], "history": []}
    session = data.get("session") if isinstance(data.get("session"), str) else ""
    entries = [
        dict(item) for item in data.get("subagents") or []
        if isinstance(item, dict)
    ]
    history = [
        dict(item) for item in data.get("history") or []
        if isinstance(item, dict)
    ]
    return {"session": session, "subagents": entries, "history": history}


def save_subagent_state(path, state):
    """Schreibt den Subagenten-Zustand atomar; nur der Läufer schreibt hier.

    GH-104: Aktive Liste und Verlauf werden getrennt begrenzt. Der Verlauf
    behält die jüngsten Einträge; ältere fallen zuerst heraus.
    """
    entries = state.get("subagents")
    if isinstance(entries, list):
        _trim_subagent_entries(entries)
    history = state.get("history")
    if isinstance(history, list):
        _trim_subagent_history(history)
    text = json.dumps(state, ensure_ascii=False, indent=1) + "\n"
    _atomic_write(path, text)


def _trim_subagent_entries(entries):
    """Begrenzt die aktive Liste auf MAX_SUBAGENTS; laufende bleiben bevorzugt."""
    if len(entries) <= MAX_SUBAGENTS:
        return
    running = [item for item in entries
               if item.get("status") not in SUBAGENT_FINISHED]
    finished = [item for item in entries
                if item.get("status") in SUBAGENT_FINISHED]
    room = max(0, MAX_SUBAGENTS - len(running))
    kept = running + (finished[-room:] if room else [])
    entries[:] = kept[-MAX_SUBAGENTS:]


def _trim_subagent_history(history):
    """Begrenzt den Verlauf auf MAX_SUBAGENT_HISTORY; die ältesten fallen heraus."""
    if len(history) > MAX_SUBAGENT_HISTORY:
        del history[:len(history) - MAX_SUBAGENT_HISTORY]


def _history_entries(state):
    """Liefert die Verlaufsliste; fehlende oder defekte Werte werden ersetzt."""
    history = state.get("history")
    if not isinstance(history, list):
        history = []
        state["history"] = history
    return history


def _history_entry(state, session):
    """Findet den Verlaufseintrag einer beendeten Kind-Session."""
    if not session:
        return None
    for item in _history_entries(state):
        if isinstance(item, dict) and item.get("session") == session:
            return item
    return None


def _retire_subagent(state, entry, status="", now=None):
    """Verschiebt einen aktiven Eintrag in den begrenzten Verlauf (GH-104).

    Der Eintrag verlässt die aktive Liste sofort. Ein Abschlussstatus bekommt
    ein ``ended``; ein bereits vorhandener Verlaufseintrag derselben Session
    wird ersetzt, damit keine Dubletten entstehen. Die Ausgabe bleibt erhalten.
    """
    if not isinstance(entry, dict):
        return None
    session = str(entry.get("session") or "")
    entries = state.get("subagents")
    if isinstance(entries, list):
        for index, item in enumerate(entries):
            if item is entry or (session and isinstance(item, dict)
                                 and item.get("session") == session):
                del entries[index]
                break
    if status and entry.get("status") not in SUBAGENT_FINISHED:
        entry["status"] = status
    if entry.get("status") in SUBAGENT_FINISHED and not entry.get("ended"):
        entry["ended"] = int(time.time()) if now is None else int(now)
    history = _history_entries(state)
    if session:
        history[:] = [
            item for item in history
            if not (isinstance(item, dict) and item.get("session") == session)
        ]
    record = dict(entry)
    history.append(record)
    _trim_subagent_history(history)
    return record


def _revive_subagent(state, entry):
    """Holt einen Verlaufseintrag zurück in die aktive Liste (B12/GH-104).

    Nur Ereignisse der konkreten Kind-Session lösen das aus. Status und
    ``ended`` werden auf einen laufenden Eintrag gesetzt; die gesammelte
    Ausgabe bleibt unangetastet.
    """
    if not isinstance(entry, dict):
        return None
    session = str(entry.get("session") or "")
    history = _history_entries(state)
    history[:] = [
        item for item in history
        if item is not entry and not (session and isinstance(item, dict)
                                      and item.get("session") == session)
    ]
    entry["status"] = "running"
    entry["ended"] = 0
    state.setdefault("subagents", []).append(entry)
    return entry


def _retire_active_for_attempt(state):
    """Räumt vor einem neuen Versuch alle übrigen aktiven Einträge ab.

    GH-104: Mehrere Tickets laufen nacheinander im selben Lauf. Ein noch als
    laufend gespeichertes Kind des vorherigen Tickets darf nicht in den neuen
    Versuch hineinragen. Innerhalb des Versuchs neu angelegte Einträge bleiben
    unberührt, weil der Aufruf vor dem Ereignisstrom erfolgt.
    """
    entries = state.get("subagents")
    if not isinstance(entries, list) or not entries:
        return False
    now = int(time.time())
    for entry in list(entries):
        _retire_subagent(state, entry, status="cancelled", now=now)
    return True


def _subagent_session(part, tool_state=None):
    """Liest die Sub-Session aus den Metadaten einer Werkzeugausführung.

    opencode legt das Ergebnis einer Werkzeugausführung unter
    ``part.state.metadata`` ab; dort steht bei ``task`` ein verschachteltes
    ``metadata`` mit ``sessionID``. Ältere Stände und Testnachbildungen führen
    ``metadata`` direkt am Teil. Beide Formen sind gültig.
    """
    candidates = []
    if isinstance(tool_state, dict):
        candidates.append(tool_state.get("metadata"))
    candidates.append(part.get("metadata"))
    for metadata in candidates:
        if not isinstance(metadata, dict):
            continue
        inner = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else metadata
        value = inner.get("sessionID") or inner.get("session_id") or ""
        if isinstance(value, str) and value:
            return value
    return ""


def _subagent_metadata_status(part, tool_state=None):
    """Liest den Subagenten-Status aus den Werkzeug-Metadaten.

    B12: Die Metadaten haben dieselben beiden Formen wie bei
    :func:`_subagent_session` (``tool_state.metadata`` bzw. ``part.metadata``,
    teils verschachtelt). Nur bekannte Statuswerte zählen; ohne Statusfeld
    oder mit unbekanntem Wert bleibt der Werkzeugzustand maßgeblich.
    """
    candidates = []
    if isinstance(tool_state, dict):
        candidates.append(tool_state.get("metadata"))
    candidates.append(part.get("metadata"))
    for metadata in candidates:
        if not isinstance(metadata, dict):
            continue
        inner = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else metadata
        value = inner.get("status")
        if isinstance(value, str) and value in SUBAGENT_STATUSES:
            return value
    return ""


def _subagent_entry(state, session, agent, description):
    """Findet den bestehenden Eintrag; ohne Session über Agent und Beschreibung."""
    if session:
        for entry in state["subagents"]:
            if entry.get("session") == session:
                return entry
        return None
    for entry in state["subagents"]:
        if (not entry.get("session") and entry.get("agent") == agent
                and entry.get("description") == description
                and entry.get("status") == "running"):
            return entry
    return None


def _child_event_lines(event):
    """Klartextzeilen eines Ereignisses aus einer Kind-Session (B11).

    Nur Text, Denken und Werkzeuge tragen zur Live-Ausgabe eines Subagenten
    bei; andere Ereignisse erfinden keinen Eintrag. Die Schreibweise folgt der
    bestehenden opencode-Übersetzung („[Denken] “, „[Werkzeug] “).
    """
    kind = event.get("type")
    part = event.get("part") if isinstance(event.get("part"), dict) else {}
    if kind == "text":
        text = part.get("text")
        return text.splitlines() if isinstance(text, str) and text else []
    if kind == "reasoning":
        text = part.get("text")
        if not isinstance(text, str) or not text.strip():
            return []
        return ["[Denken] " + line for line in text.splitlines()]
    if kind != "tool_use":
        return []
    tool = part.get("tool") or part.get("name") or "?"
    tool_state = part.get("state") if isinstance(part.get("state"), dict) else {}
    status = str(tool_state.get("status") or "unbekannt")
    inputs = tool_state.get("input") if isinstance(tool_state.get("input"), dict) else {}
    detail = inputs.get("description") or inputs.get("command") or inputs.get("filePath") or ""
    detail = " ".join(str(detail).split())
    return [f"[Werkzeug] {tool} — {status}" + (": " + detail if detail else "")]


def _known_subagent_session(state, session):
    """Ist ``session`` eine bereits erfasste Kind-Session (aktiv oder Verlauf)?"""
    if not session:
        return False
    for entry in list(state.get("subagents") or []) + list(_history_entries(state)):
        if isinstance(entry, dict) and entry.get("session") == session:
            return True
    return False


def _locate_subagent(state, session, agent="", description=""):
    """Findet einen Eintrag aktiv oder im Verlauf.

    Rückgabe: ``(entry, retired)``. ``retired`` ist True, wenn der Eintrag aus
    dem Verlauf stammt; der Aufrufer entscheidet, ob er wiederbelebt oder nur
    aktualisiert wird.
    """
    entry = _subagent_entry(state, session, agent, description)
    if entry is not None:
        return entry, False
    return _history_entry(state, session), True


def _capture_child_event(event, state, session):
    """Erfasst ein Ereignis einer fremden Session als laufenden Subagenten.

    B11: Sandbox-Läufe teilen keinen Dashboard-Server mit dem Läufer. Damit
    die Subagenten-Ausgabe trotzdem live sichtbar wird, legt der Filter für
    jede unbekannte Kind-Session einen laufenden Eintrag an und sammelt deren
    Ausgabe. Der Abschluss kommt weiterhin über das ``task``-Ereignis der
    Hauptsession.

    GH-104: Ereignisse einer bereits beendeten Kind-Session holen deren
    Verlaufseintrag zurück in die aktive Liste, statt einen leeren Eintrag
    anzulegen. Nur diese eine Session wird wiederbelebt; Geschwister bleiben
    im Verlauf.
    """
    lines = _child_event_lines(event)
    if not lines:
        return [], False
    entry, retired = _locate_subagent(state, session, "", "")
    if entry is None:
        entry = {
            "session": session,
            "agent": "",
            "description": "",
            "prompt": "",
            "status": "running",
            "started": int(time.time()),
            "ended": 0,
            "output": "",
        }
        state["subagents"].append(entry)
    elif retired:
        _revive_subagent(state, entry)
    if entry.get("status") in SUBAGENT_FINISHED:
        # B12: Lebende Kind-Ereignisse beweisen, dass der Eintrag weiterläuft;
        # ein früher gemeldeter Abschluss war voreilig. Das ist die
        # Rückfalllinie für Harnesses, die Kind-Ereignisse doch liefern.
        entry["status"] = "running"
        entry["ended"] = 0
    text = "\n".join(lines)
    previous = str(entry.get("output") or "")
    entry["output"] = output_tail(
        previous + "\n" + text if previous else text,
        MAX_SUBAGENT_OUTPUT_BYTES,
    )
    return lines, True


def translate_event(event, state, run=None):
    """Übersetzt ein opencode-JSON-Ereignis in Protokollzeilen und Zustand.

    Rückgabe: (Zeilen, Zustand geändert). Roh-JSON wird nie zurückgegeben.

    B11: Ereignisse einer fremden Session (Subagent) legen einen laufenden
    Eintrag an bzw. verlängern dessen Ausgabe; die Hauptsession bleibt
    unverändert.

    ``run`` ist der Kontext eines Agentenlaufs aus :func:`stream_events`:

    * ``run["attempt"]`` (Aufruf durch den Paket-Läufer): Genau ein
      Agentenlauf je Aufruf. Die erste gesehene Session ist die Hauptsession
      dieses Laufs und ersetzt am Ende die gespeicherte; abweichende Sessions
      sind Kind-Sessions. Das trägt F25 (Wiederholung als neue Hauptsession).
    * Ohne ``attempt`` bleibt die gespeicherte Session die Hauptsession;
      abweichende Sessions werden als Kinder erfasst (B11).
    * Ohne ``run`` (direkter Aufruf) gilt F25 „zuletzt gewinnt“: Eine
      abweichende Session wird als neue Hauptsession übernommen.
    """
    if not isinstance(event, dict):
        return [], False
    changed = False
    session_lines = []
    session = event.get("sessionID")
    known_session = state.get("session") or ""
    run_main = ""
    if isinstance(run, dict):
        if run.get("attempt"):
            run_main = run.get("main") or ""
            if not run_main and isinstance(session, str) and session:
                run["main"] = run_main = session
            if isinstance(session, str) and session and run_main \
                    and session != run_main:
                return _capture_child_event(event, state, session)
        elif isinstance(session, str) and session and known_session \
                and session != known_session:
            return _capture_child_event(event, state, session)
    if (not isinstance(run, dict) and isinstance(session, str) and session
            and known_session and session != known_session
            and _known_subagent_session(state, session)):
        # B12/GH-104: Eine bereits erfasste Kind-Session bleibt ein Subagent;
        # ihre späteren Ereignisse beleben den Eintrag wieder (auch aus dem
        # Verlauf), statt die Hauptsession zu ersetzen. F25 „zuletzt gewinnt“
        # gilt nur für unbekannte Sessions.
        return _capture_child_event(event, state, session)
    if isinstance(session, str) and session and session != known_session:
        state["session"] = session
        changed = True
        session_lines.append("[Session] " + session)

    kind = event.get("type")
    part = event.get("part") if isinstance(event.get("part"), dict) else {}
    if kind == "text":
        text = part.get("text")
        if isinstance(text, str) and text:
            return session_lines + text.splitlines(), changed
        return session_lines, changed
    if kind == "reasoning":
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            thinking = ["[Denken] " + line for line in text.splitlines()]
            return session_lines + thinking, changed
        return session_lines, changed
    if kind == "error":
        error = event.get("error")
        if isinstance(error, dict):
            data = error.get("data") if isinstance(error.get("data"), dict) else {}
            message = data.get("message") or error.get("message") or error.get("name") or ""
        else:
            message = error
        message = " ".join(str(message or "").split())
        if message:
            return session_lines + ["[Fehler] " + message], changed
        return session_lines, changed
    if kind != "tool_use":
        return session_lines, changed

    tool = part.get("tool") or part.get("name") or "?"
    tool_state = part.get("state") if isinstance(part.get("state"), dict) else {}
    status = str(tool_state.get("status") or "unbekannt")
    inputs = tool_state.get("input") if isinstance(tool_state.get("input"), dict) else {}
    if tool not in SUBAGENT_TOOLS:
        detail = inputs.get("description") or inputs.get("command") or inputs.get("filePath") or ""
        detail = " ".join(str(detail).split())
        line = f"[Werkzeug] {tool} — {status}"
        return ([line + (": " + detail if detail else "")]), changed

    agent = str(inputs.get("agent") or inputs.get("subagent_type") or "")
    description = str(inputs.get("description") or "")
    prompt = inputs.get("prompt") if isinstance(inputs.get("prompt"), str) else ""
    output = tool_state.get("output") if isinstance(tool_state.get("output"), str) else ""
    child_session = _subagent_session(part, tool_state)
    # B12: Die Metadaten sind Authorität. opencode ≥ 2.3 kehrt beim
    # task-Werkzeug sofort mit state.status="completed" zurück, meldet in den
    # Metadaten aber "running", solange die Kind-Session weiterläuft. Ohne
    # bekannten Metadatenstatus gilt wie bisher der Werkzeugzustand.
    status = _subagent_metadata_status(part, tool_state) or status
    now = int(time.time())
    entry, retired = _locate_subagent(state, child_session, agent, description)
    if entry is None:
        entry = {
            "session": child_session,
            "agent": agent,
            "description": description,
            "prompt": prompt,
            "status": status,
            "started": now,
            "ended": 0,
            "output": "",
        }
        state["subagents"].append(entry)
        retired = False
        changed = True
    for key, value in (
        ("session", child_session), ("agent", agent),
        ("description", description), ("prompt", prompt),
    ):
        if value and entry.get(key) != value:
            entry[key] = value
            changed = True
    if entry.get("status") != status:
        entry["status"] = status
        changed = True
    if output and entry.get("output") != output:
        entry["output"] = output_tail(output, MAX_SUBAGENT_OUTPUT_BYTES)
        changed = True
    ended = now if status in SUBAGENT_FINISHED else 0
    if entry.get("ended") != ended:
        entry["ended"] = ended
        changed = True
    if not isinstance(entry.get("started"), int):
        entry["started"] = now
        changed = True
    if status in SUBAGENT_FINISHED:
        # GH-104: Ein abgeschlossener Subagent verlässt die aktive Liste sofort.
        # Stammt der Eintrag bereits aus dem Verlauf, bleibt er dort und wird
        # nur aktualisiert (keine Dublette).
        if not retired:
            _retire_subagent(state, entry, now=now)
        changed = True
    elif retired:
        # B12/GH-104: Ein laufender task-Status holt den Verlaufseintrag zurück.
        _revive_subagent(state, entry)
        changed = True

    lines = [f"[Subagent] {agent or '?'}: {description or '(ohne Beschreibung)'} — {status}"]
    if output:
        lines.extend(output.splitlines())
    return session_lines + lines, changed


def _pi_result_text(result):
    """Vereinigt die Textblöcke eines Pi-Werkzeupergebnisses zur Ausgabe.

    Pi liefert Werkzeupergebnisse als ``{"content":[{"type":"text",...}]}``
    (Pi-Dokumentation docs/json.md). Andere Blockarten (Bilder, Details)
    tragen nichts zur erfassten Ausgabe bei.
    """
    if isinstance(result, str):
        return result
    if not isinstance(result, dict):
        return ""
    content = result.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    texts = [
        block["text"]
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    ]
    return "\n".join(texts)


def _pi_tool_detail(inputs):
    """Kurzinfo einer Pi-Werkzeugausführung (analog opencode-Übersetzung)."""
    detail = (
        inputs.get("description") or inputs.get("command")
        or inputs.get("filePath") or ""
    )
    return " ".join(str(detail).split())


def _pi_new_entry(tool_call, inputs, now):
    """Lege den Subagenteneintrag für ein Pi-Subagenten-Werkzeug an."""
    return {
        "session": tool_call,
        "agent": str(inputs.get("agent") or ""),
        "description": str(inputs.get("description") or ""),
        "prompt": inputs.get("prompt") if isinstance(inputs.get("prompt"), str) else "",
        "status": "running",
        "started": int(now),
        "ended": 0,
        "output": "",
    }


def _pi_tool_lines(event, state, mode):
    """Übersetzt eine Pi-Werkzeugausführung in Zeilen und Subagentenzustand.

    ``mode`` ist der Ereignistyp ohne Präfix (``start``/``update``/``end``).
    Subagenten-Werkzeuge (SUBAGENT_TOOLS) erzeugen einen Eintrag mit dem
    ``toolCallId`` als Tab-Schlüssel (``session``).
    """
    tool = str(event.get("toolName") or "?")
    inputs = event.get("args") if isinstance(event.get("args"), dict) else {}
    tool_call = str(event.get("toolCallId") or "")
    detail = _pi_tool_detail(inputs)
    now = int(time.time())
    changed = False
    if mode == "start":
        line = f"[Werkzeug] {tool} — läuft" + (": " + detail if detail else "")
        if tool in SUBAGENT_TOOLS:
            entry, retired = _locate_subagent(state, tool_call, "", "")
            if entry is None:
                entry = _pi_new_entry(tool_call, inputs, now)
                state["subagents"].append(entry)
            elif retired:
                _revive_subagent(state, entry)
            for key, value in (
                ("session", tool_call), ("agent", str(inputs.get("agent") or "")),
                ("description", str(inputs.get("description") or "")),
            ):
                if value and entry.get(key) != value:
                    entry[key] = value
            prompt = inputs.get("prompt")
            if isinstance(prompt, str) and prompt and entry.get("prompt") != prompt:
                entry["prompt"] = prompt
            if entry.get("status") != "running":
                entry["status"] = "running"
            if not isinstance(entry.get("started"), int):
                entry["started"] = now
            entry["ended"] = 0
            changed = True
        return [line], changed
    if mode == "update":
        if tool not in SUBAGENT_TOOLS:
            return [], False
        entry, retired = _locate_subagent(state, tool_call, "", "")
        if entry is None:
            entry = _pi_new_entry(tool_call, inputs, now)
            state["subagents"].append(entry)
        elif retired:
            # GH-104: Ein Fortschrittsereignis beweist, dass der Lauf weitergeht.
            _revive_subagent(state, entry)
        text = _pi_result_text(event.get("partialResult"))
        if text and entry.get("output") != text:
            entry["output"] = output_tail(text, MAX_SUBAGENT_OUTPUT_BYTES)
        return [], True
    # mode == "end"
    failed = bool(event.get("isError"))
    line = f"[Werkzeug] {tool} — " + ("Fehler" if failed else "abgeschlossen")
    if tool not in SUBAGENT_TOOLS:
        return [line], False
    entry, retired = _locate_subagent(state, tool_call, "", "")
    if entry is None:
        entry = _pi_new_entry(tool_call, inputs, now)
        state["subagents"].append(entry)
        retired = False
    ending = ("error" if failed else "completed")
    if entry.get("status") != ending:
        entry["status"] = ending
    text = _pi_result_text(event.get("result"))
    if text and entry.get("output") != text:
        entry["output"] = output_tail(text, MAX_SUBAGENT_OUTPUT_BYTES)
    entry["ended"] = now
    if not isinstance(entry.get("started"), int):
        entry["started"] = now
    # GH-104: Pi-Abschluss (completed/error) verlässt die aktive Liste sofort.
    # Ein bereits beendeter Eintrag bleibt im Verlauf und wird nur aktualisiert.
    if not retired:
        _retire_subagent(state, entry, now=now)
    return [line], True


def translate_pi_event(event, state):
    """Übersetzt ein Pi-JSON-Ereignis in Protokollzeilen und Zustand.

    Pi 1.5.0 liefert im JSON-Modus (``--mode json``) einen JSONL-Strom mit
    Session-Header, Nachrichten- und Werkzeigereignissen (Pi-Dokumentation
    docs/json.md). Rückgabe ist gleich der von :func:`translate_event`:
    ``(Zeilen, Zustand geändert)``.

    Der Session-Header erzeugt nur eine ``[Session]``-Zeile. Die Kennung
    wird bewusst nicht als Hauptsession übernommen: Pi läuft mit
    ``--no-session``, die Kennung ist ephemeral, und die opencode-Live-
    Abfrage dürfte niemals mit ihr befragt werden. Verheiratete Zustände
    der opencode-Übersetzung bleiben dadurch unverändert.
    """
    if not isinstance(event, dict):
        return [], False
    kind = str(event.get("type") or "")
    if kind == "session":
        session_id = event.get("id")
        if isinstance(session_id, str) and session_id:
            return ["[Session] " + session_id], False
        return [], False
    if kind == "message_end":
        message = (
            event.get("message") if isinstance(event.get("message"), dict) else {}
        )
        if message.get("role") != "assistant":
            return [], False
        content = message.get("content")
        if isinstance(content, str):
            blocks = [{"type": "text", "text": content}] if content else []
        elif isinstance(content, list):
            blocks = content
        else:
            blocks = []
        lines = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            text = block.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            if block.get("type") == "thinking":
                lines.extend("[Denken] " + line for line in text.splitlines())
            elif block.get("type") == "text":
                lines.extend(text.splitlines())
        return lines, False
    if not kind.startswith("tool_execution_"):
        # Streaming-Deltas und Rauschen (message_update, turn_*, agent_*,
        # queue, compaction, retry) erzeugen keine Zeilen und keine
        # Zustandsänderung.
        return [], False
    mode = kind[len("tool_execution_"):]
    if mode not in ("start", "update", "end"):
        return [], False
    return _pi_tool_lines(event, state, mode)


def stream_events(stdin, emit, state_path, attempt=False, sessions=None,
                  session_project="", session_name="", session_run="",
                  session_agent="", session_harness="",
                  session_worktree="", session_package="", session_branch=""):
    """Liest JSON-Zeilen von stdin, schreibt Klartext und pflegt den Zustand.

    Nicht-JSON-Zeilen (z. B. stderr des Agenten) werden unverändert
    durchgereicht. Jede Zustandsänderung wird atomar gespeichert, damit das
    Dashboard nie eine halbe Datei liest.

    B6: Die Ereignisform wird automatisch erkannt — opencode-Ereignisse
    behalten ihr Verhalten, Ereignisse vom Pi-JSON-Modus gehen durch die
    Pi-Übersetzung. Beide Formen teilen sich dieselbe Zustandsdatei.

    ``attempt`` kennzeichnet den Aufruf als genau einen Agentenlauf des
    Paket-Läufers (F25/B11): Die erste Session dieses Stroms ist die
    Hauptsession, abweichende Sessions sind Kind-Sessions. Ohne diese Angabe
    bleibt die gespeicherte Session die Hauptsession; ein Strom, der nur
    Text-Ereignisse einer einzelnen fremden Session enthält, wird am Ende
    dennoch als neuer Hauptversuch übernommen (Rückwärtskompatibilität der
    direkten Einbettung).

    AP19: Mit ``sessions`` (Registerpfad) wird beim ersten Erscheinen bzw.
    Wechsel der Hauptsession ein Registereintrag geschrieben — noch während
    des Stroms, damit ein harter Abbruch die Kennung nicht verliert. Ohne die
    Option bleibt das Verhalten byte-identisch. Kind-Sessions und Pi-Header
    ändern ``state["session"]`` nicht und erzeugen darum nie einen Eintrag.
    """
    state = load_subagent_state(state_path)
    # GH-104: Jeder Versuch startet mit einer leeren aktiven Liste. Ein noch
    # als laufend gespeichertes Kind eines vorherigen Tickets wandert in den
    # Verlauf und kann nicht in den neuen Versuch hineinragen. Einträge, die
    # erst in diesem Strom entstehen, bleiben unberührt.
    if attempt and _retire_active_for_attempt(state):
        save_subagent_state(state_path, state)
    run = {"attempt": bool(attempt), "main": "", "saw_main": False,
           "unknown": {}}
    # --sessions ist der Dateipfad <laufzeit>/sessions.json; die Registry
    # arbeitet auf dem Laufzeitordner und ergänzt den Dateinamen selbst.
    registry = SessionRegistry(os.path.dirname(os.path.abspath(str(sessions)))) if sessions else None
    recorded = ""

    def capture(event, previous):
        """Einziger Prüfpunkt: Hauptsession des Stroms dauerhaft erfassen."""
        nonlocal recorded
        if registry is None:
            return
        current = str(state.get("session") or "")
        if not current or current == recorded:
            return
        # Ein im Zustand bereits bekannter Sessionname wird nur erfasst, wenn
        # er in diesem Strom auch wirklich erscheint. Am Stromende übernommene
        # Sessions weichen vom vorherigen Wert ab und zählen ebenfalls.
        seen = isinstance(event, dict) and event.get("sessionID") == current
        if current == str(previous or "") and not seen:
            return
        registry.observe(
            session=current, project=session_project, name=session_name,
            run_id=session_run, agent=session_agent, harness=session_harness,
            worktree_path=session_worktree, package_id=session_package,
            branch=session_branch,
        )
        # GH-99: Das Arbeitspaket ist der Eigentümer der Session. Die
        # Zuordnung wird sofort persistiert, damit ein harter Abbruch sie
        # nicht verliert. Ungültige/fehlende Paketkennungen dürfen den Lauf
        # nicht stören.
        if session_package and session_project and vibe_tickets is not None:
            try:
                vibe_tickets.attach_session(
                    session_project, session_package, current)
            except (ImportError, OSError, ValueError):
                pass
        recorded = current

    for raw in stdin:
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        if not line.lstrip().startswith("{"):
            emit(line)
            continue
        try:
            event = json.loads(line)
        except ValueError:
            emit("opencode: " + line)
            continue
        previous = state.get("session")
        if isinstance(event, dict) and event.get("type") in PI_EVENT_TYPES:
            lines, changed = translate_pi_event(event, state)
        else:
            if not run["attempt"]:
                _track_unknown_session(event, state, run)
            lines, changed = translate_event(event, state, run)
        for output_line in lines:
            emit(output_line)
        if changed:
            save_subagent_state(state_path, state)
        capture(event, previous)
    previous = state.get("session")
    if _promote_text_only_attempt(state, run):
        emit("[Session] " + state["session"])
        save_subagent_state(state_path, state)
        capture(None, previous)


def _track_unknown_session(event, state, run):
    """Merkt sich fremde Sessions für die Versuchserkennung ohne ``attempt``.

    ``saw_main`` wird gesetzt, sobald ein Ereignis der gespeicherten
    Hauptsession (oder die erste Session eines leeren Zustands) erscheint.
    ``unknown`` hält je fremder Session fest, ob sie ausschließlich
    Text-Ereignisse geliefert hat.
    """
    if not isinstance(event, dict):
        return
    session = event.get("sessionID")
    known = state.get("session") or ""
    if not isinstance(session, str) or not session:
        return
    if not known or session == known:
        run["saw_main"] = True
        return
    text_only = event.get("type") == "text"
    run["unknown"][session] = run["unknown"].get(session, True) and text_only


def _promote_text_only_attempt(state, run):
    """Übernimmt eine text-only Einzelsession als neuen Hauptversuch.

    B11 erfasst fremde Sessions live als Subagenten. Ein Aufruf, der keine
    Hauptsession-Ereignisse enthält und ausschließlich Text einer einzigen
    fremden Session liefert, ist jedoch der Zweitversuch aus F25: Seine
    Session ersetzt die gespeicherte („zuletzt gewinnt“). Die erfasste
    Ausgabe bleibt erhalten, damit kein Subagenten-Text verloren geht.
    """
    if run.get("attempt") or run.get("saw_main") or len(run.get("unknown") or {}) != 1:
        return False
    promoted, text_only = next(iter(run["unknown"].items()))
    if not text_only or state.get("session") == promoted:
        return False
    state["session"] = promoted
    return True


def _atomic_write(path, text):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".runs-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        vibe_storage.fsync_dir(directory)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


@contextlib.contextmanager
def _registry_lock(runtime, lock_path):
    """Sperrt eine Registerdatei für einen Lese-/Schreibzugriff.

    Gemeinsame Implementierung für Lauf-, Session- und Worktree-Register:
    dieselbe Sperrdatei, dieselbe flock-Semantik, dieselbe Freigabe.
    """
    os.makedirs(runtime, exist_ok=True)
    handle = open(lock_path, "a+", encoding="utf-8")
    try:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if fcntl is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


class RunRegistry:
    """Zustand aller bekannten Läufe eines Laufzeitordners."""

    def __init__(self, runtime, keep=KEEP_RECORDS):
        self.runtime = os.path.abspath(str(runtime))
        self.path = os.path.join(self.runtime, "runs.json")
        self.lock_path = os.path.join(self.runtime, "runs.lock")
        self.keep = int(keep)

    def _locked(self):
        return _registry_lock(self.runtime, self.lock_path)

    def _read(self):
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return []
        runs = data.get("runs") if isinstance(data, dict) else None
        if not isinstance(runs, list):
            return []
        return [
            record for record in runs
            if isinstance(record, dict) and isinstance(record.get("id"), str)
        ]

    def _write(self, runs):
        text = json.dumps({"runs": runs[-self.keep:]}, indent=1, ensure_ascii=False) + "\n"
        _atomic_write(self.path, text)

    def all(self):
        """Alle erfassten Läufe; die Reihenfolge folgt dem Register."""
        return self._read()

    def cleanup_completed(self):
        """Entfernt abgeschlossene Läufe; live bleibende Einträge bleiben (F34).

        Rückgabe ist ``{"removed": n, "remaining": m}``. Im Gegensatz zu
        ``prune`` werden keine Sitzungen beendet und keine Läufe verändert.
        """
        with self._locked():
            runs = self._read()
            kept = [item for item in runs if item.get("state") in LIVE_STATES]
            removed = len(runs) - len(kept)
            if removed:
                self._write(kept)
            return {"removed": removed, "remaining": len(kept)}

    def get(self, run_id):
        """Laufdatensatz als Kopie oder None, wenn die ID unbekannt ist."""
        for record in reversed(self._read()):
            if record.get("id") == run_id:
                return dict(record)
        return None

    def latest(self, project=None, key=None):
        """Jüngster Eintrag, wahlweise für einen Projektpfad oder einen Schlüssel."""
        real = os.path.realpath(os.path.abspath(project)) if project else None
        for record in reversed(self._read()):
            if real is not None and os.path.realpath(
                os.path.abspath(str(record.get("project", "")))
            ) != real:
                continue
            if key is not None and record.get("key") != key:
                continue
            return dict(record)
        return None

    def start(self, project, name, key, agent, session="", log="", verify_log="",
              run_id=None, state="running"):
        """Legt einen Lauf an oder aktualisiert ihn (gleiche ID = gleicher Lauf)."""
        record = {
            "id": run_id or new_run_id(key),
            "project": str(project),
            "name": str(name),
            "key": str(key),
            "agent": str(agent or ""),
            "session": str(session or ""),
            "log": str(log or ""),
            "verify_log": str(verify_log or ""),
            "state": state if state in STATES else "running",
            "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "pid": os.getpid(),
            "exit_code": None,
        }
        with self._locked():
            runs = [item for item in self._read() if item.get("id") != record["id"]]
            runs.append(record)
            self._write(runs)
        return dict(record)

    def finish(self, run_id, exit_code=None, state="finished", note="",
               only_live=False):
        """Beendet einen Lauf; ein unbekannter Lauf bleibt unbekannt (None).

        ``note`` wird nur gespeichert, wenn er nicht leer ist. ``only_live``
        lässt bereits beendete Einträge unverändert (V-026): Ein Signal darf
        einen abgeschlossenen Lauf nicht nachträglich umdeuten.
        """
        if state not in STATES:
            raise ValueError(f"Unbekannter Laufzustand: {state!r}")
        with self._locked():
            runs = self._read()
            found = None
            changed = False
            for record in runs:
                if record.get("id") != run_id:
                    continue
                if only_live and record.get("state") not in LIVE_STATES:
                    return dict(record)
                record["state"] = state
                record["exit_code"] = exit_code
                record["ended"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                if note:
                    record["note"] = str(note)
                else:
                    record.pop("note", None)
                found = dict(record)
                changed = True
            if changed:
                self._write(runs)
            return found


def _epoch_number(value):
    """Epochenwert defensiv als int; unlesbare Angaben ergeben None.

    Bool ist hier unlesbar: ``int(True)`` wäre 1 und würde einen beschädigten
    Zeitwert als gültige Sekunde ausgeben. ``observe`` und ``_read`` verwerfen
    bool aus demselben Grund.
    """
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


class SessionRegistry:
    """Erfasste Hauptsessions eines Laufzeitordners (AP19).

    Das Register liegt als ``<laufzeit>/sessions.json`` neben ``runs.json`` und
    wird unter einer eigenen Sperrdatei atomar geschrieben. Es bleiben höchstens
    ``SESSION_LIMIT_MAX`` Einträge. Ein fehlender oder defekter Bestand wird wie
    beim Laufregister als leerer Bestand mit dem Standardlimit gelesen; die
    Datei wird dabei nie gelöscht.
    """

    def __init__(self, runtime):
        self.runtime = os.path.abspath(str(runtime))
        self.path = os.path.join(self.runtime, "sessions.json")
        self.lock_path = os.path.join(self.runtime, "sessions.lock")

    def _locked(self):
        return _registry_lock(self.runtime, self.lock_path)

    def _read(self):
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            data = None
        if not isinstance(data, dict):
            data = {}
        limit = data.get("limit")
        if (isinstance(limit, bool) or not isinstance(limit, int)
                or not 1 <= limit <= SESSION_LIMIT_MAX):
            limit = SESSION_LIMIT_DEFAULT
        entries = data.get("sessions")
        if not isinstance(entries, list):
            entries = []
        return {
            "limit": int(limit),
            "sessions": [
                dict(item) for item in entries
                if isinstance(item, dict) and isinstance(item.get("session"), str)
            ],
            "project_limits": self._read_project_limits(data.get("project_limits")),
        }

    @staticmethod
    def _read_project_limits(raw):
        """Projekt-Overrides lesen; ungültige Werte werden verworfen (F34)."""
        if not isinstance(raw, dict):
            return {}
        limits = {}
        for key, value in raw.items():
            if (isinstance(value, bool) or not isinstance(value, int)
                    or not 1 <= value <= SESSION_LIMIT_MAX):
                continue
            real = os.path.realpath(os.path.abspath(str(key)))
            limits[real] = int(value)
        return limits

    def _write(self, data):
        sessions = list(data.get("sessions") or [])
        if len(sessions) > SESSION_LIMIT_MAX:
            # Review M2: Es bleiben die Einträge mit den höchsten last_seen,
            # nicht die letzten der Einfügereihenfolge. Ein erneut beobachteter
            # alter Eintrag trägt das neueste last_seen und überlebt damit.
            # Unlesbare Zeitwerte zählen als 0; die Reihenfolge der übrig
            # gebliebenen Einträge bleibt unverändert.
            def seen_at(index):
                item = sessions[index]
                value = _epoch_number(item.get("last_seen")) if isinstance(item, dict) else None
                return value if value is not None else 0

            ranked = sorted(
                range(len(sessions)), key=lambda index: (seen_at(index), index)
            )[-SESSION_LIMIT_MAX:]
            keep = set(ranked)
            sessions = [item for index, item in enumerate(sessions) if index in keep]
        text = json.dumps(
            {"limit": int(data.get("limit", SESSION_LIMIT_DEFAULT)),
             "sessions": sessions,
             "project_limits": self._read_project_limits(
                 data.get("project_limits"))},
            indent=1, ensure_ascii=False,
        ) + "\n"
        _atomic_write(self.path, text)

    def all(self):
        """Alle erfassten Sessions in Registerreihenfolge (Kopien)."""
        return self._read()["sessions"]

    def get(self, session):
        """Sessioneintrag als Kopie oder None, wenn die Kennung unbekannt ist."""
        for entry in self._read()["sessions"]:
            if entry.get("session") == session:
                return dict(entry)
        return None

    def observe(self, session, project, name, run_id, agent, harness, now=None,
                worktree_path="", package_id="", branch=""):
        """Erfasst die Session (Upsert) und liefert den gespeicherten Eintrag.

        Ungültige Kennungen werden ohne jede Dateiänderung ignoriert. Beim
        Upsert bleibt ``first_seen`` erhalten; ``last_seen`` geht nicht zurück.
        AP4 (T-W1): ``worktree_path``, ``package_id`` und ``branch`` werden
        optional mitgeführt; fehlende Angaben (Alteinträge) bleiben leer.
        """
        if not isinstance(session, str) or not SESSION_ID_RE.fullmatch(session):
            return None
        moment = int(time.time()) if now is None else int(now)
        with self._locked():
            data = self._read()
            entries = data["sessions"]
            entry = next(
                (item for item in entries if item.get("session") == session), None)
            if entry is None:
                entry = {"session": session, "first_seen": moment}
                entries.append(entry)
            elif (isinstance(entry.get("first_seen"), bool)
                  or not isinstance(entry.get("first_seen"), int)):
                entry["first_seen"] = moment
            previous = entry.get("last_seen")
            if isinstance(previous, bool) or not isinstance(previous, int):
                previous = moment
            entry.update({
                "project": os.path.realpath(os.path.abspath(str(project or ""))),
                "name": str(name or ""),
                "run_id": str(run_id or ""),
                "agent": str(agent or ""),
                "harness": str(harness or ""),
                "last_seen": max(moment, previous),
                "worktree_path": str(worktree_path or ""),
                "package_id": str(package_id or ""),
                "branch": str(branch or ""),
            })
            self._write(data)
            return dict(entry)

    def limit(self):
        """Gespeicherter Standard für die Auflistung (immer ein int)."""
        return int(self._read()["limit"])

    def set_limit(self, value):
        """Setzt den Standard (1..100), ohne die Einträge zu verändern."""
        if (isinstance(value, bool) or not isinstance(value, int)
                or not 1 <= value <= SESSION_LIMIT_MAX):
            raise ValueError(
                f"Session-Limit muss 1 bis {SESSION_LIMIT_MAX} sein: {value!r}")
        with self._locked():
            data = self._read()
            data["limit"] = int(value)
            self._write(data)
        return int(value)

    @staticmethod
    def _project_key(project):
        """Schlüssel eines Projekt-Overrides: immer der echte Pfad (F34)."""
        return os.path.realpath(os.path.abspath(str(project or "")))

    def project_limit(self, project):
        """Projekt-Override (1..100) oder ``None``, wenn keiner gesetzt ist."""
        return self._read()["project_limits"].get(self._project_key(project))

    def set_project_limit(self, project, value):
        """Setzt das Limit für ein Projekt (1..100), ohne die Einträge zu ändern."""
        if (isinstance(value, bool) or not isinstance(value, int)
                or not 1 <= value <= SESSION_LIMIT_MAX):
            raise ValueError(
                f"Session-Limit muss 1 bis {SESSION_LIMIT_MAX} sein: {value!r}")
        if not str(project or "").strip():
            raise ValueError("Projektpfad fehlt")
        key = self._project_key(project)
        with self._locked():
            data = self._read()
            data["project_limits"][key] = int(value)
            self._write(data)
        return int(value)

    def finish_for_run(self, run_id, state):
        """Persistiert den Endzustand auf allen Einträgen eines Laufs (T-S1).

        Zusätzlich räumt dieser Aufruf altersbedingt auf: Einträge, deren
        ``last_seen`` älter als ``SESSION_PRUNE_DAYS`` Tage ist und die keinen
        (noch existierenden) Worktree-Anhang haben, werden entfernt. Der
        aktuell beendete Lauf (passende ``run_id``) wird nie mit aufgeräumt.
        """
        now = int(time.time())
        cutoff = now - SESSION_PRUNE_DAYS * 86400
        with self._locked():
            data = self._read()
            changed = False
            for entry in data["sessions"]:
                if entry.get("run_id") == run_id and entry.get("state") != state:
                    entry["state"] = str(state)
                    changed = True
            kept = []
            for entry in data["sessions"]:
                if entry.get("run_id") == run_id:
                    kept.append(entry)
                    continue
                last = _epoch_number(entry.get("last_seen"))
                if last is not None and last < cutoff:
                    worktree = str(entry.get("worktree_path") or "").strip()
                    if not (worktree and os.path.isdir(worktree)):
                        changed = True
                        continue
                kept.append(entry)
            if changed:
                data["sessions"] = kept
                self._write(data)

    def forget_worktree(self, path):
        """Entfernt alle Einträge mit diesem Worktree-Anhang (realpath-Vergleich).

        AP4 (T-W1): Nach dem Entfernen einer Arbeitskopie werden die zugehörigen
        Session-Einträge vergessen. Ein leerer Pfad verändert nichts.
        """
        if not str(path or "").strip():
            return
        real = os.path.realpath(os.path.abspath(str(path)))
        with self._locked():
            data = self._read()
            before = len(data["sessions"])
            data["sessions"] = [
                entry for entry in data["sessions"]
                if os.path.realpath(
                    os.path.abspath(str(entry.get("worktree_path") or ""))
                ) != real
            ]
            if len(data["sessions"]) != before:
                self._write(data)

    def forget_sessions(self, sessions):
        """Vergisst genau die genannten Session-Einträge (GH-99).

        Wird nur nach erfolgreichem Paketabschluss aufgerufen, nachdem die
        Kosten gespült und die Zuordnungen am Paket bereinigt wurden.
        """
        wanted = {
            value for value in (sessions or [])
            if isinstance(value, str) and SESSION_ID_RE.fullmatch(value)
        }
        if not wanted:
            return
        with self._locked():
            data = self._read()
            before = len(data["sessions"])
            data["sessions"] = [
                entry for entry in data["sessions"]
                if entry.get("session") not in wanted
            ]
            if len(data["sessions"]) != before:
                self._write(data)


def finish_package(project, package_id, runtime, forget=True):
    """Schließt ein Arbeitspaket erfolgreich ab (GH-99).

    Reihenfolge ist bindend: erst den Verbrauch der gespeicherten Sessions
    persistieren, dann die Zuordnungen am Paket löschen. Scheitert das Spülen,
    bleiben Kosten und Zuordnungen erhalten.

    ``forget=False`` behält die Registereinträge: der Läufer beendet die
    Hauptsession regulär über ``sessions-finish`` und muss ihren Endzustand
    für ``session_overview`` erhalten. Nur der ausdrückliche Paketabschluss
    über die CLI vergisst die Einträge zusätzlich.
    """
    if vibe_tickets is None:
        return []
    record = vibe_tickets.find(vibe_tickets.load(project), package_id)
    if record is None:
        # Kein Datensatz: nichts zu spülen oder zu bereinigen. Der PR-only-
        # Abschluss kann ein Paket betreffen, das (noch) nicht im Speicher
        # steht; das ist kein Fehler.
        return []
    sessions = vibe_tickets.sessions_of(record)
    if vibe_usage is not None:
        vibe_usage.flush_package_usage(project, package_id)
    vibe_tickets.clear_sessions(project, package_id)
    if forget:
        SessionRegistry(runtime).forget_sessions(sessions)
    return sessions


def resume_session_for_package(project, package_id):
    """Gespeicherte fortsetzbare Session eines Pakets oder ``""`` (GH-99)."""
    if vibe_tickets is None:
        return ""
    return vibe_tickets.resume_session(project, package_id)


def _clean_registry_id(value):
    """Paket-Kennung des Worktree-Registers; ungültig → Leerwert."""
    text = str(value or "").strip()
    return text if SESSION_ID_RE.fullmatch(text) else ""


def _clean_registry_branch(value):
    """Branch-Name des Worktree-Registers; ungültig → Leerwert."""
    text = str(value or "").strip()
    if (not text or not BRANCH_RE.match(text) or ".." in text
            or text.endswith(".lock") or text.endswith("/")
            or text.endswith(".")):
        return ""
    return text


class WorktreeRegistry:
    """Registrierte Arbeitskopien eines Laufzeitordners (AP4, T-W2).

    Datei ``<laufzeit>/worktrees.json`` plus Sperrdatei ``worktrees.lock``,
    atomar geschrieben wie das Session-Register. Felder je Eintrag: ``project``
    (realpath), ``id``, ``branch``, ``path``, ``base_commit``, ``created``,
    ``updated``, ``pr_url``, ``session``, ``state``. Ein fehlender oder
    defekter Bestand gilt als leer (die Datei wird nie gelöscht). Ungültige
    ``id``/``branch`` werden abgelehnt (``register`` liefert dann ``None``).
    """

    def __init__(self, runtime):
        self.runtime = os.path.abspath(str(runtime))
        self.path = os.path.join(self.runtime, "worktrees.json")
        self.lock_path = os.path.join(self.runtime, "worktrees.lock")

    def _locked(self):
        return _registry_lock(self.runtime, self.lock_path)

    def _read(self):
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            data = None
        if not isinstance(data, dict):
            data = {}
        entries = data.get("worktrees")
        if not isinstance(entries, list):
            entries = []
        return {"worktrees": [
            dict(item) for item in entries
            if isinstance(item, dict)
            and isinstance(item.get("project"), str)
            and isinstance(item.get("id"), str)
        ]}

    def _write(self, data):
        text = json.dumps({"worktrees": data["worktrees"]},
                          indent=1, ensure_ascii=False) + "\n"
        _atomic_write(self.path, text)

    def register(self, project, id, branch, path, base_commit,
                 pr_url="", session="", state=""):
        """Legt einen Eintrag an oder aktualisiert ihn (Upsert über project+id).

        ``created`` bleibt beim Aktualisieren erhalten; ``updated`` wird neu
        gesetzt. Ungültige ``id``/``branch`` oder fehlende Pflichtangaben
        liefern ``None`` und ändern nichts.
        """
        project = os.path.realpath(os.path.abspath(str(project or "")))
        pid = _clean_registry_id(id)
        branch = _clean_registry_branch(branch)
        path = str(path or "").strip()
        if not project or not pid or not branch or not path:
            return None
        now = int(time.time())
        with self._locked():
            data = self._read()
            entry = next(
                (item for item in data["worktrees"]
                 if item.get("project") == project and item.get("id") == pid),
                None)
            if entry is None:
                entry = {"project": project, "id": pid, "created": now}
                data["worktrees"].append(entry)
            entry.update({
                "branch": branch,
                "path": path,
                "base_commit": str(base_commit or ""),
                "pr_url": str(pr_url or ""),
                "session": str(session or ""),
                "state": str(state or ""),
                "updated": now,
            })
            self._write(data)
            return dict(entry)

    def get(self, project, id):
        """Eintrag als Kopie oder ``None``; Schlüssel sind (project, id)."""
        project = os.path.realpath(os.path.abspath(str(project or "")))
        for entry in self._read()["worktrees"]:
            if entry.get("project") == project and entry.get("id") == id:
                return dict(entry)
        return None

    def unregister(self, project, id):
        """Entfernt genau den benannten Eintrag; ein fehlender ist kein Fehler."""
        project = os.path.realpath(os.path.abspath(str(project or "")))
        with self._locked():
            data = self._read()
            before = len(data["worktrees"])
            data["worktrees"] = [
                item for item in data["worktrees"]
                if not (item.get("project") == project and item.get("id") == id)
            ]
            if len(data["worktrees"]) != before:
                self._write(data)

    def all(self, project=None):
        """Alle Einträge; mit ``project`` nur die dieses Projekts (realpath)."""
        entries = self._read()["worktrees"]
        if project is None:
            return [dict(item) for item in entries]
        project = os.path.realpath(os.path.abspath(str(project)))
        return [dict(item) for item in entries
                if item.get("project") == project]


def session_overview(runtime, project=None, limit=None, text=None):
    """Sessions jüngste zuerst, mit Zustand aus dem Laufregister (AP19).

    Die Rangfolge des Limits ist Parameter > Projekt-Override > gespeicherter
    Standard > 5. Der Projektfilter vergleicht über ``realpath``, der Textfilter sucht ohne
    Rücksicht auf Groß-/Kleinschreibung in der Session-Kennung. Jeder Eintrag
    trägt die Registerfelder sowie ``state`` und ``state_label``. Ein Eintrag
    mit unlesbarem ``last_seen`` wird übersprungen statt die Auflistung
    abbrechen zu lassen.
    """
    registry = SessionRegistry(runtime)
    if limit is None:
        # F34: Ohne ausdrückliches Limit gilt das Projekt-Override, sonst das
        # globale Limit. Ein explizites Limit gewinnt immer.
        override = registry.project_limit(project) if project else None
        effective = override if override is not None else registry.limit()
    elif (isinstance(limit, bool) or not isinstance(limit, int)
          or not 1 <= limit <= SESSION_LIMIT_MAX):
        raise ValueError(
            f"Session-Limit muss 1 bis {SESSION_LIMIT_MAX} sein: {limit!r}")
    else:
        effective = int(limit)

    entries = registry.all()
    if project:
        real = os.path.realpath(os.path.abspath(str(project)))
        entries = [
            item for item in entries
            if os.path.realpath(os.path.abspath(str(item.get("project") or ""))) == real
        ]
    if text:
        needle = str(text).lower()
        entries = [
            item for item in entries
            if needle in str(item.get("session") or "").lower()
        ]
    # Review Minor: Zeitfelder defensiv überführen. Ein beschädigter
    # last_seen-Wert darf weder Liste noch API noch UI abbrechen; der Eintrag
    # wird übersprungen. Die Sortierung läuft danach über die Zahlenwerte.
    usable = []
    for item in entries:
        last = _epoch_number(item.get("last_seen"))
        if last is None:
            continue
        first = _epoch_number(item.get("first_seen"))
        view = dict(item)
        view["last_seen"] = last
        view["first_seen"] = first if first is not None else 0
        usable.append((last, view))
    usable.sort(key=lambda pair: pair[0], reverse=True)
    entries = [view for _, view in usable]

    runs = RunRegistry(runtime)
    overview = []
    for entry in entries[:effective]:
        run_id = str(entry.get("run_id") or "")
        record = runs.get(run_id) if run_id else None
        # AP4 (T-S1): Ein persistiertes ``state`` gilt, wenn der Lauf-Eintrag
        # fehlt; sonst bleibt das Laufregister maßgeblich (LIVE_STATES über die
        # SESSION_STATES-Tabelle). Unbekannt bleibt unknown.
        if record is not None:
            source_state = str((record or {}).get("state") or "")
        else:
            source_state = str(entry.get("state") or "")
        state, label = SESSION_STATES.get(source_state, ("unknown", "unbekannt"))
        item = dict(entry)
        item["state"] = state
        item["state_label"] = label
        overview.append(item)
    return overview


def tmux_session_state(session):
    """True, False oder None für eine Laufsitzung auf ihrem eigenen Server.

    Agentenläufe liegen seit V-026 auf einem eigenen tmux-Server; der
    Socket-Name ist der Sitzungsname. ``False`` gilt nur bei Exitcode 1
    ("keine solche Sitzung"); alles andere ist nicht prüfbar.
    """
    if not session:
        return None
    try:
        completed = subprocess.run(
            ["tmux", "-L", session, "has-session", "-t", session],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    return None


def prune_orphans(runtime, project=None, note="extern beendet (Sitzung fehlt)"):
    """Markiert verwaiste Live-Einträge als ``ended``.

    Ohne ``project`` gilt das Register als Ganzes, mit ``project`` nur dessen
    Einträge. Laufende Sitzungen, nicht prüfbare Sitzungen und bereits
    beendete Einträge bleiben unverändert. Es wird nie eine Sitzung beendet.
    Rückgabe: ``(ended, running, unknown)``.
    """
    registry = RunRegistry(runtime)
    real = os.path.realpath(os.path.abspath(str(project))) if project else None
    ended = running = unknown = 0
    for record in registry.all():
        if record.get("state") not in LIVE_STATES:
            continue
        if real is not None and os.path.realpath(
            os.path.abspath(str(record.get("project") or ""))
        ) != real:
            continue
        session = str(record.get("session") or "")
        state = tmux_session_state(session)
        if state is None:
            unknown += 1
            continue
        if state:
            running += 1
            continue
        registry.finish(record["id"], exit_code=None, state="ended",
                        note=note, only_live=True)
        ended += 1
    return ended, running, unknown


def choose_key(project, runtime, preferred=""):
    """Kollisionsfreier Laufschlüssel für einen direkt gestarteten Lauf.

    ``preferred`` (von ``bin/vibe``) gilt unverändert. Ohne Vorgabe wird der
    Verzeichnisname verwendet — außer ein anderes Projekt ist bereits unter
    demselben Schlüssel eingetragen; dann kommt ein Pfad-Fingerabdruck hinzu.
    Auch beendete Läufe zählen mit: Ihr Protokoll liegt weiterhin unter dem
    Schlüssel und darf nicht von einem anderen Projekt überschrieben werden.
    """
    real = os.path.realpath(os.path.abspath(str(project)))
    base = clean_key(preferred or os.path.basename(real.rstrip(os.sep))) or "projekt"
    if preferred:
        return base
    for record in reversed(RunRegistry(runtime).all()):
        if record.get("key") != base:
            continue
        other = record.get("project") or ""
        if os.path.realpath(os.path.abspath(other)) != real:
            return f"{base}-{digest(real)}"
    return base


def _state(value):
    if value not in STATES:
        raise argparse.ArgumentTypeError(
            "Zustand muss einer von " + ", ".join(STATES) + " sein"
        )
    return value


def build_parser():
    """Argumentkatalog für Kommandozeilenaufrufe des Registrier-Skripts."""
    parser = argparse.ArgumentParser(
        prog="vibe_runs.py", description="Laufregister für Agentenläufe (V-015)"
    )
    sub = parser.add_subparsers(dest="command")

    key = sub.add_parser("key", help="kollisionsfreien Laufschlüssel ausgeben")
    key.add_argument("project")
    key.add_argument("runtime")
    key.add_argument("preferred", nargs="?", default="")

    start = sub.add_parser("start", help="Lauf anlegen oder aktualisieren")
    start.add_argument("--runtime", required=True)
    start.add_argument("--project", required=True)
    start.add_argument("--name", required=True)
    start.add_argument("--key", required=True)
    start.add_argument("--agent", default="")
    start.add_argument("--session", default="")
    start.add_argument("--log", default="")
    start.add_argument("--verify-log", default="")
    start.add_argument("--id", default="")
    start.add_argument("--state", type=_state, default="running")

    finish = sub.add_parser("finish", help="Lauf beenden")
    finish.add_argument("--runtime", required=True)
    finish.add_argument("--id", required=True)
    finish.add_argument("--exit-code", type=int, default=None)
    finish.add_argument("--state", type=_state, default="finished")
    finish.add_argument("--note", default="")
    finish.add_argument(
        "--only-live", action="store_true",
        help="bereits beendete Einträge unverändert lassen",
    )

    prune = sub.add_parser(
        "prune", help="verwaiste Live-Einträge als ended markieren"
    )
    prune.add_argument("--runtime", required=True)
    prune.add_argument("--project", default="")
    prune.add_argument("--note", default="extern beendet (Sitzung fehlt)")

    rotate = sub.add_parser("rotate", help="Logdatei bei Bedarf rotieren")
    rotate.add_argument("path")
    rotate.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    rotate.add_argument("--keep", type=int, default=DEFAULT_KEEP)

    stream = sub.add_parser(
        "stream",
        help="opencode-JSON-Ereignisse in Klartext und Subagenten-Zustand übersetzen",
    )
    stream.add_argument("--state", required=True, help="Zustandsdatei <log>.state.json")
    stream.add_argument(
        "--attempt", action="store_true",
        help="Strom ist genau ein Agentenlauf; erste Session ist die Hauptsession",
    )
    # AP19: Ohne --sessions bleibt der Filter unverändert; die Zusatzangaben
    # landen im Registereintrag der erfassten Hauptsession.
    stream.add_argument("--sessions", default="", help="Pfad zu sessions.json")
    stream.add_argument("--session-project", default="", help="Projektpfad des Eintrags")
    stream.add_argument("--session-name", default="", help="Projektname des Eintrags")
    stream.add_argument("--session-run", default="", help="Lauf-ID des Eintrags")
    stream.add_argument("--session-agent", default="", help="Agent des Eintrags")
    stream.add_argument("--session-harness", default="", help="Harness des Eintrags")
    # AP4 (T-W1): Worktree-Anhang der Session (leer = Integrationsstand).
    stream.add_argument("--session-worktree", default="", help="Worktree-Pfad des Eintrags")
    stream.add_argument("--session-package", default="", help="Paket-Kennung des Eintrags")
    stream.add_argument("--session-branch", default="", help="Branch des Eintrags")

    sessions_finish = sub.add_parser(
        "sessions-finish",
        help="Endzustand auf allen Sessions eines Laufs persistieren (AP4)",
    )
    sessions_finish.add_argument("--runtime", required=True)
    sessions_finish.add_argument("--run-id", required=True)
    sessions_finish.add_argument("--state", type=_state, required=True)

    sessions_forget = sub.add_parser(
        "sessions-forget-worktree",
        help="Sessions eines Worktrees vergessen (AP4)",
    )
    sessions_forget.add_argument("--runtime", required=True)
    sessions_forget.add_argument("--worktree", required=True)

    sessions_finish_package = sub.add_parser(
        "sessions-finish-package",
        help="Verbrauch spülen, Paket-Sessions bereinigen (GH-99)",
    )
    sessions_finish_package.add_argument("--runtime", required=True)
    sessions_finish_package.add_argument("--project", required=True)
    sessions_finish_package.add_argument("--id", required=True)
    sessions_finish_package.add_argument(
        "--keep-registry", action="store_true",
        help="Registereinträge der Hauptsession behalten (Läufer-Erfolgspfad)")

    sessions_resume = sub.add_parser(
        "sessions-resume",
        help="Gespeicherte Session eines Pakets ausgeben (GH-99)",
    )
    sessions_resume.add_argument("--project", required=True)
    sessions_resume.add_argument("--id", required=True)

    worktree_get = sub.add_parser(
        "worktree-get", help="Worktree-Eintrag als JSON oder 'none' (AP4)",
    )
    worktree_get.add_argument("--runtime", required=True)
    worktree_get.add_argument("--project", required=True)
    worktree_get.add_argument("--id", required=True)

    worktree_register = sub.add_parser(
        "worktree-register", help="Worktree-Eintrag anlegen/aktualisieren (AP4)",
    )
    worktree_register.add_argument("--runtime", required=True)
    worktree_register.add_argument("--project", required=True)
    worktree_register.add_argument("--id", required=True)
    worktree_register.add_argument("--branch", required=True)
    worktree_register.add_argument("--path", required=True)
    worktree_register.add_argument("--base-commit", required=True)
    worktree_register.add_argument("--pr-url", default="")
    worktree_register.add_argument("--session", default="")
    worktree_register.add_argument("--state", default="")

    worktree_unregister = sub.add_parser(
        "worktree-unregister", help="Worktree-Eintrag entfernen (AP4)",
    )
    worktree_unregister.add_argument("--runtime", required=True)
    worktree_unregister.add_argument("--project", required=True)
    worktree_unregister.add_argument("--id", required=True)

    return parser


def main(argv=None):
    """Kommandozeileneinstieg; Rückgabe ist der Prozessende-Code."""
    parser = build_parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    if not args.command:
        parser.print_help(sys.stderr)
        return 2
    if args.command == "key":
        print(choose_key(args.project, args.runtime, args.preferred))
        return 0
    if args.command == "start":
        record = RunRegistry(args.runtime).start(
            project=args.project, name=args.name, key=args.key, agent=args.agent,
            session=args.session, log=args.log, verify_log=args.verify_log,
            run_id=args.id or None, state=args.state,
        )
        print(record["id"])
        return 0
    if args.command == "finish":
        record = RunRegistry(args.runtime).finish(
            args.id, exit_code=args.exit_code, state=args.state,
            note=args.note, only_live=args.only_live,
        )
        if record is None:
            print(f"Unbekannter Lauf: {args.id}", file=sys.stderr)
            return 1
        print(record["id"])
        return 0
    if args.command == "prune":
        ended, running, unknown = prune_orphans(
            args.runtime, args.project or None, args.note
        )
        print(f"{ended} verwaiste Einträge beendet, {running} laufen weiter, "
              f"{unknown} nicht prüfbar.")
        return 0
    if args.command == "rotate":
        rotate_log(args.path, max_bytes=args.max_bytes, keep=args.keep)
        return 0
    if args.command == "stream":
        def emit(line):
            sys.stdout.write(str(line) + "\n")
            sys.stdout.flush()
        stream_events(
            sys.stdin, emit, args.state, attempt=args.attempt,
            sessions=args.sessions, session_project=args.session_project,
            session_name=args.session_name, session_run=args.session_run,
            session_agent=args.session_agent, session_harness=args.session_harness,
            session_worktree=args.session_worktree,
            session_package=args.session_package,
            session_branch=args.session_branch,
        )
        return 0
    if args.command == "sessions-finish":
        SessionRegistry(args.runtime).finish_for_run(args.run_id, args.state)
        return 0
    if args.command == "sessions-forget-worktree":
        SessionRegistry(args.runtime).forget_worktree(args.worktree)
        return 0
    if args.command == "sessions-finish-package":
        try:
            finish_package(args.project, args.id, args.runtime,
                           forget=not args.keep_registry)
        except (OSError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 1
        return 0
    if args.command == "sessions-resume":
        try:
            print(resume_session_for_package(args.project, args.id))
        except (OSError, ValueError) as error:
            print(str(error), file=sys.stderr)
            return 1
        return 0
    if args.command == "worktree-get":
        entry = WorktreeRegistry(args.runtime).get(args.project, args.id)
        print(json.dumps(entry, ensure_ascii=False) if entry else "none")
        return 0
    if args.command == "worktree-register":
        entry = WorktreeRegistry(args.runtime).register(
            project=args.project, id=args.id, branch=args.branch, path=args.path,
            base_commit=args.base_commit, pr_url=args.pr_url,
            session=args.session, state=args.state,
        )
        if entry is None:
            print("FEHLT: ungültiger Worktree-Eintrag", file=sys.stderr)
            return 1
        # Bewusst ohne stdout-Ausgabe: Der Läufer hängt den Aufruf an das
        # Laufprotokoll; eine JSON-Zeile würde das Protokoll verfälschen.
        return 0
    if args.command == "worktree-unregister":
        WorktreeRegistry(args.runtime).unregister(args.project, args.id)
        return 0
    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
