#!/usr/bin/env python3
"""opencode-Verbrauch lesen und am Arbeitspaket persistieren (GH-99).

Dieses Modul ist die einzige Stelle, an der die opencode-Datenbank gelesen
wird. Es wird ausschließlich beim Spülen (``vibe sessions finish-package`` und
der Erfolgspfad des Läufers) benutzt; die Kostenübersicht liest nur noch die
persistierten Paketkosten aus ``vibe_tickets``.

Eigenschaften:

* **Nur lesend** — die Datenbank wird über ``mode=ro`` geöffnet; es entstehen
  weder ``-wal``- noch ``-shm``-Dateien und keine Schreibänderung.
* **Mehrere Datenbanken** — die primäre opencode-Datenbank und die
  Sandbox-Datenbank eines Projekts werden nacheinander gelesen. Eine Session
  wird nur einmal gezählt; die primäre Datenbank gewinnt.
* **Kein Pfadraten** — die Zuordnung kommt aus der am Paket gespeicherten
  Session-Kennung, nicht aus Anzeigenamen oder Verzeichnis-Aliasen.
"""
import json
import os
import re
import sqlite3
import time
import urllib.parse

import vibe_tickets

_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def opencode_db_path():
    """Pfad der primären opencode-Sitzungsdatenbank."""
    explicit = (os.environ.get("VIBE_OPENCODE_DB") or "").strip()
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "opencode", "opencode.db")


def _sandbox_db_path(project):
    """opencode-Datenbank im Sandbox-Zustand des Projekts, falls vorhanden."""
    try:
        import vibe_sandbox
        state = vibe_sandbox.state_dir(project)
    except (ImportError, OSError, ValueError):
        return ""
    return os.path.join(state, "data", "opencode", "opencode.db")


def candidate_databases(project):
    """Primäre und projektspezifische Sandbox-Datenbank (dedupliziert)."""
    paths, seen = [], set()
    for path in (opencode_db_path(), _sandbox_db_path(project)):
        if not path:
            continue
        try:
            key = os.path.realpath(path)
        except OSError:
            key = path
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return paths


def _int_tokens(value):
    """Nichtnegative Ganzzahl; kaputte Werte zählen als 0."""
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return number if number > 0 else 0


def _model_id(provider, ident):
    provider = str(provider or "").strip()
    ident = str(ident or "").strip()
    if not ident:
        return "unbekannt"
    return ident if ("/" in ident or not provider) else provider + "/" + ident


def _model_from_session(value):
    """Modell einer Sitzungszeile; opencode speichert es als JSON-Text."""
    if isinstance(value, dict):
        return _model_id(value.get("providerID"), value.get("id"))
    if not isinstance(value, str) or not value.strip():
        return "unbekannt"
    text = value.strip()
    if text.startswith("{"):
        try:
            return _model_from_session(json.loads(text))
        except ValueError:
            return "unbekannt"
    return text


def _usage_add(usage, agent, model, input_tokens, output_tokens, reasoning, cached):
    key = (agent or "unbekannt", model or "unbekannt")
    entry = usage.setdefault(key, {"input": 0, "cached": 0, "output": 0})
    # Die gespeicherte Eingabe ist die Gesamtsumme; gecachte Tokens sind ein
    # Teil davon. ``cached`` bleibt separat für die Cachepreis-Regel.
    entry["input"] += input_tokens + cached
    entry["cached"] += cached
    entry["output"] += output_tokens + reasoning


def _open_sessions_db(path):
    """Öffnet die Datenbank ausschließlich lesend (kein Anlegen, kein Schreiben)."""
    uri = "file:" + urllib.parse.quote(os.path.abspath(path), safe="/") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _db_schema(conn):
    names = {row[0] for row in conn.execute(
        "select name from sqlite_master where type='table'")}
    if {"session_v2", "session_message"} <= names:
        return "v2"
    if {"session", "message"} <= names:
        return "v1"
    return None


def _read_sessions(conn, schema):
    table = "session_v2" if schema == "v2" else "session"
    sql = ("select id, project_id, parent_id, directory, title, agent, model,"
           " tokens_input, tokens_output, tokens_reasoning, tokens_cache_read,"
           f" time_created from {table}")
    return [dict(row) for row in conn.execute(sql)]


def _json1_available(conn):
    try:
        conn.execute("select json_extract('{\"a\": 1}', '$.a')").fetchone()
        return True
    except sqlite3.Error:
        return False


def _message_usage(conn, schema, session_id, json1=True):
    """Tokenverbrauch je Agent und Modell aus den Assistenten-Nachrichten."""
    if schema == "v2":
        sql = ("select json_extract(data,'$.agent'), json_extract(data,'$.mode'),"
               " json_extract(data,'$.model.providerID'), json_extract(data,'$.model.id'),"
               " coalesce(json_extract(data,'$.tokens.input'),0),"
               " coalesce(json_extract(data,'$.tokens.output'),0),"
               " coalesce(json_extract(data,'$.tokens.reasoning'),0),"
               " coalesce(json_extract(data,'$.tokens.cache.read'),0)"
               " from session_message where session_id=? and type='assistant'"
               " and json_valid(data)")
    else:
        sql = ("select json_extract(data,'$.agent'), json_extract(data,'$.mode'),"
               " json_extract(data,'$.providerID'), json_extract(data,'$.modelID'),"
               " coalesce(json_extract(data,'$.tokens.input'),0),"
               " coalesce(json_extract(data,'$.tokens.output'),0),"
               " coalesce(json_extract(data,'$.tokens.reasoning'),0),"
               " coalesce(json_extract(data,'$.tokens.cache.read'),0)"
               " from message where session_id=? and json_valid(data)"
               " and json_extract(data,'$.role')='assistant'")
    usage = {}
    for row in conn.execute(sql, (session_id,)):
        agent = row[0] or row[1]
        model = _model_id(row[2], row[3])
        _usage_add(usage, agent, model, _int_tokens(row[4]), _int_tokens(row[5]),
                   _int_tokens(row[6]), _int_tokens(row[7]))
    if not usage:
        return None
    if not any(value["input"] or value["output"] for value in usage.values()):
        return None
    return usage


def _message_usage_python(conn, schema, session_id):
    """Ersatzweg ohne JSON1: Nachrichten in Python auswerten."""
    if schema == "v2":
        rows = conn.execute(
            "select data from session_message where session_id=? and type='assistant'",
            (session_id,))
        assistant_only = True
    else:
        rows = conn.execute("select data from message where session_id=?", (session_id,))
        assistant_only = False
    usage = {}
    for row in rows:
        try:
            data = json.loads(row[0])
        except (TypeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        if not assistant_only and data.get("role") != "assistant":
            continue
        tokens = data.get("tokens")
        if not isinstance(tokens, dict):
            continue
        model = data.get("model")
        if isinstance(model, dict):
            name = _model_id(model.get("providerID"), model.get("id"))
        else:
            name = _model_id(data.get("providerID"), data.get("modelID"))
        cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
        _usage_add(usage, data.get("agent") or data.get("mode"), name,
                   _int_tokens(tokens.get("input")), _int_tokens(tokens.get("output")),
                   _int_tokens(tokens.get("reasoning")), _int_tokens(cache.get("read")))
    if not usage:
        return None
    if not any(value["input"] or value["output"] for value in usage.values()):
        return None
    return usage


def _session_usage(row):
    """Rückfall auf die in der Sitzung gespeicherten Summen."""
    cached = _int_tokens(row.get("tokens_cache_read"))
    usage = {}
    _usage_add(usage, row.get("agent"), _model_from_session(row.get("model")),
               _int_tokens(row.get("tokens_input")), _int_tokens(row.get("tokens_output")),
               _int_tokens(row.get("tokens_reasoning")), cached)
    return usage


def _current_month():
    return time.strftime("%Y-%m", time.gmtime())


def _as_package_usage(usage):
    """DB-Verbrauch in die persistierte Form ``{models: {model: {...}}}``."""
    models = {}
    for (agent, model), tokens in usage.items():
        models[model] = {
            "agent": agent,
            "input": int(tokens.get("input", 0)),
            "cached_input": int(tokens.get("cached", 0)),
            "output": int(tokens.get("output", 0)),
        }
    return {"models": models}


def usage_for_sessions(project, session_ids):
    """Verbrauch der gewünschten Sessions aus allen Kandidaten-Datenbanken.

    Liefert ``{session_id: usage}`` mit ``month`` (Spülzeitpunkt). Fehlt eine
    Session, bleibt sie aus dem Ergebnis; vorhandene persistierte Kosten
    werden dann nicht überschrieben. Eine Session wird nur einmal gelesen;
    die primäre Datenbank gewinnt.
    """
    wanted = [sid for sid in session_ids
              if isinstance(sid, str) and _SESSION_RE.fullmatch(sid)]
    found = {}
    month = _current_month()
    for db_path in candidate_databases(project):
        if not os.path.exists(db_path):
            continue
        conn = None
        try:
            conn = _open_sessions_db(db_path)
            schema = _db_schema(conn)
            if schema is None:
                continue
            json1 = _json1_available(conn)
            rows = {row["id"]: row for row in _read_sessions(conn, schema)}
            for sid in wanted:
                if sid in found or sid not in rows:
                    continue
                if json1:
                    usage = _message_usage(conn, schema, sid)
                else:
                    usage = _message_usage_python(conn, schema, sid)
                usage = usage or _session_usage(rows[sid])
                if not usage:
                    continue
                value = _as_package_usage(usage)
                value["month"] = month
                found[sid] = value
        except (sqlite3.Error, OSError):
            continue
        finally:
            if conn is not None:
                conn.close()
    return found


def flush_package_usage(project, package_id):
    """Spült den DB-Verbrauch der am Paket gespeicherten Sessions.

    Vorhandene persistierte Kosten einer Session, die in keiner Datenbank
    vorkommt, bleiben unverändert. Liefert die gespülten Session-Kennungen.
    """
    record = vibe_tickets.find(vibe_tickets.load(project), package_id)
    if record is None:
        raise ValueError("Arbeitspaket nicht gefunden: " + str(package_id))
    sessions = vibe_tickets.sessions_of(record)
    usage = usage_for_sessions(project, sessions)
    for sid in sessions:
        if sid in usage:
            vibe_tickets.record_usage(project, package_id, sid, usage[sid])
    return list(usage)
