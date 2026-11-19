#!/usr/bin/env python3
"""vibe-web — lokales Dashboard (nur Standardbibliothek). Start über: vibe ui"""
import os
import sys
import json
import time
import secrets
import threading
import contextlib
import signal
import base64
import datetime
import http.client
import importlib.util
import importlib.machinery
import ipaddress
from http.cookies import SimpleCookie, CookieError
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
# sys.path wurde erst um HERE erweitert; Kopfimporte der Geschwistermodule
# würden sonst auf das produktive bin/ zeigen statt auf diese Arbeitskopie.
import vibe_storage  # pylint: disable=wrong-import-position
import vibe_paths  # pylint: disable=wrong-import-position
import vibe_runs  # pylint: disable=wrong-import-position
import vibe_ui_config  # pylint: disable=wrong-import-position
_loader = importlib.machinery.SourceFileLoader("vibe", os.path.join(HERE, "vibe"))
_spec = importlib.util.spec_from_loader("vibe", _loader)
vibe = importlib.util.module_from_spec(_spec)
sys.modules["vibe"] = vibe
_loader.exec_module(vibe)
import vibe_mcp  # pylint: disable=wrong-import-position
import vibe_guide  # pylint: disable=wrong-import-position
import vibe_questions  # pylint: disable=wrong-import-position
import vibe_autonomous  # pylint: disable=wrong-import-position
import vibe_harness  # pylint: disable=wrong-import-position
import vibe_github  # pylint: disable=wrong-import-position
import vibe_packages  # pylint: disable=wrong-import-position
import vibe_services  # pylint: disable=wrong-import-position

try:
    PATHS = vibe_paths.resolve()
except vibe_paths.ConfigError as error:
    raise SystemExit("Pfadkonfiguration: " + str(error)) from error

PORT = PATHS.ui_port
BIND = PATHS.ui_bind
MAX_BODY = 1024 * 1024
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

TOKFILE = os.path.join(PATHS.runtime, "web.token")
INSTFILE = os.path.join(PATHS.runtime, "web.instance")
# Erst prepare_runtime() beim echten Start setzt Token und Instanzkennung.
# Der Import dieses Moduls bleibt damit frei von Dateisystem-Nebenwirkungen.
TOKEN = None
INSTANCE = None
STARTED = time.time()
ANSI = vibe_services.ANSI
# Absichtlich ohne snake_case-Umbenennung: tests/unit/test_vibe_paths.py prüft
# SRV als Attribut des importierten Moduls; ein Umbenennen würde die
# beobachtbare Oberfläche und die Annahmetests brechen.
SRV = None  # pylint: disable=invalid-name
# AP13: ui.json wird erst im __main__ geladen (Import bleibt nebenwirkungsfrei);
# das leere Objekt ist der Zustand "nichts konfiguriert".
UI_DATA = {}
# AP13: In-Memory-Sessions. Sie sterben mit dem Dashboard-Prozess, werden
# nirgends geschrieben (kein zweites Geheimnis auf der Platte) und sind
# gegen gleichzeitige Anfragen mit einer Sperre geschützt.
SESSIONS = {}
SESSIONS_LOCK = threading.Lock()
SESSION_COOKIE = "vibe_session"
# Wird beim Beenden gesetzt. Aktive SSE-Streams prüfen das Ereignis und senden
# eine letzte Zeile, statt bis zum Verbindungsabbruch weiterzulaufen.
STOP = threading.Event()

def write_private(path, text):
    """Schreibt Laufzeitkennungen atomar und setzt, soweit möglich, Rechte 0600.

    Auf FUSE/NTFS wirken Unix-Rechte nicht zwingend; die Oberfläche und die
    Dokumentation behaupten das auch nicht.
    """
    vibe_storage.write_text(path, text, mode=0o600)

def prepare_runtime():
    """Legt Laufzeitordner und Kennungen erst beim Start an.

    Der Import dieses Moduls bleibt damit ohne Nebenwirkungen: keine
    Verzeichnisse, keine Tokendateien, kein Serverprozess. Die Kennungen
    werden als Paar zurückgegeben.
    """
    try:
        vibe_paths.ensure(PATHS, "runtime")
    except vibe_paths.ConfigError as error:
        raise SystemExit("Pfadkonfiguration: " + str(error)) from error
    token = secrets.token_urlsafe(24)
    instance = secrets.token_hex(8)
    write_private(INSTFILE, instance)
    write_private(TOKFILE, token)
    return token, instance

def redact(text):
    """Entfernt das Token aus jeder nach außen gegebenen Meldung."""
    text = str(text)
    return text.replace(TOKEN, "[entfernt]") if TOKEN else text

def split_host(value):
    """Liefert den Hostnamen ohne Port und ohne IPv6-Klammern."""
    text = (value or "").strip().lower()
    if text.startswith("["):
        end = text.find("]")
        return text[1:end] if end >= 0 else ""
    if text.count(":") == 1:
        return text.split(":", 1)[0]
    return text

def _is_ip_literal(text):
    """Nur echte IP-Adressliterale (IPv4/IPv6), keine DNS-Namen."""
    try:
        ipaddress.ip_address(text)
    except ValueError:
        return False
    return True

def host_allowed(value):
    """Prüft, ob der Host-Header zu dieser Instanz passt (AP13).

    Loopback-Namen und reine IP-Literale sind erlaubt — beim Netzwerkbetrieb
    sendet der Browser die Zieladresse als Host. DNS-Hostnamen bleiben
    abgelehnt (DNS-Rebinding-Schutz): Ein Angreifer darf seine Domain nicht
    auf dieses Dashboard zeigen lassen können.
    """
    host = split_host(value)
    if host in LOOPBACK_HOSTS:
        return True
    return _is_ip_literal(host)

def origin_allowed(value):
    """Origin muss auf diese Instanz zeigen (Port inklusive).

    Loopback-Namen und IP-Literale sind zulässig (AP13); der Port muss zum
    laufenden Dashboard passen, damit eine Instanz nicht für eine andere
    missbraucht werden kann.
    """
    if not value:
        return True
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme != "http":
        return False
    hostname = (parsed.hostname or "").lower()
    if hostname not in LOOPBACK_HOSTS and not _is_ip_literal(hostname):
        return False
    effective_port = port if port is not None else 80
    return effective_port == PORT

PUBLIC_SUBAGENT_FIELDS = (
    "session", "agent", "description", "prompt", "status",
    "started", "ended", "output",
)
# B11: Die Listenantwort trägt bewusst keinen Prompt; er kann sehr groß sein
# und wird für die Ausgabeansicht nicht gebraucht.
LIST_SUBAGENT_FIELDS = (
    "session", "agent", "description", "status", "started", "ended", "output",
)
# B11: Die Liste wird alle zwei Sekunden abgerufen. ``output`` reist deshalb
# nur als kleiner Tail mit; die volle Ausgabe liefert /api/subagent-output.
MAX_LIST_OUTPUT_BYTES = 4 * 1024
STEER_MAX_CHARS = 4000


def public_subagent(entry):
    """Nur die vereinbarten Felder verlassen die API, nie beliebte Zusatzdaten."""
    return {key: entry.get(key) for key in PUBLIC_SUBAGENT_FIELDS if key in entry}


def listed_subagent(entry):
    """Kompakte Listenform für /api/subagents (ohne prompt, Output als Tail)."""
    listed = {key: entry.get(key) for key in LIST_SUBAGENT_FIELDS if key in entry}
    if "output" in listed:
        listed["output"] = vibe_runs.output_tail(
            listed["output"], MAX_LIST_OUTPUT_BYTES)
    return listed


def run_start_epoch(record):
    """Beginn eines Registereintrags als Unix-Zeit; unlesbar ergibt ``None``."""
    try:
        return datetime.datetime.strptime(
            str(record.get("started") or ""), "%Y-%m-%dT%H:%M:%S%z").timestamp()
    except (AttributeError, TypeError, ValueError):
        return None


def entry_started(entry):
    """Startzeit eines Subagenteneintrags als Zahl; Defektes zählt als 0."""
    try:
        return int(entry.get("started") or 0)
    except (TypeError, ValueError):
        return 0


def opencode_request(path, timeout=3, url=None, password=None):
    """Liest eine GET-Antwort des opencode-Servers mit Basic-Auth.

    B14: Ziel-URL und Kennwort sind Parameter; ohne Angabe bleibt der
    bisherige gemeinsame Server mit dem globalen Kennwort maßgeblich. Ohne
    Kennwort wird nicht angefragt. Fehler und nicht-JSON-Antworten liefern
    ``None``; die Oberfläche erfindet daraus keine Subagenten.
    """
    if password is None:
        password = opencode_password()
    if not password:
        return None
    target = urlparse(url or vibe.OC_URL)
    host = target.hostname or "127.0.0.1"
    port = target.port or 80
    credential = base64.b64encode(("opencode:" + password).encode("utf-8")).decode("ascii")
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request(
            "GET", path, headers={"Authorization": "Basic " + credential}
        )
        response = connection.getresponse()
        body = response.read()
        if not 200 <= response.status < 300:
            return None
        data = json.loads(body.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, http.client.HTTPException, ValueError):
        return None
    finally:
        connection.close()


def _seconds(value):
    """Wandelt opencode-Zeitstempel (Millisekunden) in Sekunden."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number // 1000 if number > 10 ** 12 else number


def _agent_name(info):
    agent = info.get("agent") if isinstance(info, dict) else None
    if isinstance(agent, dict):
        return str(agent.get("name") or agent.get("id") or "")
    return str(agent or "")


def live_endpoint(name=None):
    """Ziel-URL und Kennwort für Live-Lesezugriffe des Dashboards (B14).

    Mit Projektkontext liefert ``steer_endpoint`` den privaten Laufserver
    aus ``<Laufprotokoll>.server.json`` (Loopback, Kennwort aus der dort
    genannten Datei) oder den gemeinsamen Server als Rückfall. Ohne
    Projektkontext bleibt der bisherige Pfad unverändert. Beide Werte werden
    pro Anfrage gelesen, damit geänderte Server- oder Kennwortdateien sofort
    wirken.
    """
    if name:
        return steer_endpoint(name)
    return vibe.OC_URL, opencode_password()


def live_subagents(main_session, name=None):
    """Fragt laufende und beendete Kind-Sessions beim opencode-Server ab.

    ``opencode run --format json`` meldet ein ``task``-Werkzeug erst bei
    Abschluss. Für die Anforderung „zu jedem Zeitpunkt sichtbar“ liest das
    Dashboard deshalb ergänzend die Session-Liste und den Aktivstatus. B14:
    Mit Projektkontext werden diese Abfragen am privaten Lauf-Endpunkt
    gestellt; sonst bleibt der gemeinsame Server maßgeblich. Ohne Server
    oder ohne Kennwort bleibt die Liste aus der Zustandsdatei gültig.
    """
    if not main_session:
        return []
    target_url, password = live_endpoint(name)
    data = opencode_request(
        "/api/session?limit=100", url=target_url, password=password)
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    active_data = opencode_request(
        "/api/session/active", url=target_url, password=password)
    active_map = active_data.get("data") if isinstance(active_data, dict) else None
    active = {
        session_id for session_id, value in (active_map or {}).items()
        if isinstance(value, dict) and value.get("type") == "running"
    } if isinstance(active_map, dict) else set()
    entries = []
    for info in items:
        if not isinstance(info, dict) or info.get("parentID") != main_session:
            continue
        session_id = info.get("id")
        if not isinstance(session_id, str) or not session_id:
            continue
        running = session_id in active
        times = info.get("time") if isinstance(info.get("time"), dict) else {}
        entries.append({
            "session": session_id,
            "agent": _agent_name(info),
            "description": str(info.get("title") or ""),
            "prompt": "",
            "status": "running" if running else "completed",
            "started": _seconds(times.get("created")),
            "ended": 0 if running else _seconds(times.get("updated")),
            "output": "",
        })
    return entries


def _message_parts(message):
    """Teile und Sprecherinformation einer Nachricht in beiden Projektionen.

    opencode v2 liefert ``{"info":{"role":…},"parts":[…]}``; die ältere Form
    trägt ``type``/``content`` direkt am Nachrichtenobjekt. Unbekannte Formen
    liefern keine Teile, statt Inhalte zu erfinden.
    """
    info = message.get("info")
    if not isinstance(info, dict):
        info = {}
    parts = message.get("parts")
    if isinstance(parts, list):
        return info, parts
    content = message.get("content")
    if isinstance(content, list):
        return info, content
    return info, []


def _message_role(message, info):
    """Rolle der Nachricht (v2 unter info, Alt-Form direkt am Objekt)."""
    for source in (info, message):
        if isinstance(source, dict):
            for key in ("role", "type"):
                value = source.get(key)
                if isinstance(value, str) and value:
                    return value
    return ""


def live_subagent_output(session, name=None):
    """Liest die vollständige Agentenausgabe einer Kind-Session (AP14).

    Bis zu 200 Nachrichten werden angefragt. Echtes opencode begrenzt
    ``limit`` auf höchstens 200; ein größerer Wert endet mit HTTP 400
    ``InvalidRequestError`` („Expected a value less than or equal to 200“)
    und die Live-Ausgabe fiele auf den statischen Ersttext zurück (Befund
    am laufenden System, 2026-11-15: limit=500 → HTTP 400).
    B14: Mit Projektkontext kommt
    die Antwort vom privaten Lauf-Endpunkt aus der Serverdatei, sonst vom
    gemeinsamen Server. opencode v2 liefert Nachrichten standardmäßig
    neueste zuerst; ``order=asc`` erzwingt die chronologische Reihenfolge.
    Textteile erscheinen unverändert, Reasoning-Teile mit dem Präfix
    „[Denken] “ und Werkzeugteile je Teil als „[Werkzeug] <tool> — <status>:
    <detail>“ mit Detail aus ``state.input`` (description/command/filePath).
    Nutzer-Nachrichten werden übersprungen.
    """
    target_url, password = live_endpoint(name)
    data = opencode_request(
        "/api/session/" + quote(session, safe="") + "/message?limit=200&order=asc",
        url=target_url, password=password)
    messages = data.get("data") if isinstance(data, dict) else None
    if not isinstance(messages, list):
        return ""
    lines = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        info, parts = _message_parts(message)
        if _message_role(message, info) == "user":
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            kind = part.get("type")
            if kind == "text":
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    lines.append(text)
            elif kind == "reasoning":
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    lines.extend(
                        "[Denken] " + line
                        for line in text.splitlines()
                        if line.strip()
                    )
            elif kind == "tool":
                tool = part.get("tool") or part.get("name") or ""
                state = part.get("state") if isinstance(part.get("state"), dict) else {}
                detail = ""
                input_data = state.get("input") if isinstance(state.get("input"), dict) else {}
                for key in ("description", "command", "filePath"):
                    value = input_data.get(key)
                    if isinstance(value, str) and value.strip():
                        detail = " ".join(value.split())
                        break
                line = "[Werkzeug] " + str(tool) + " — " + str(state.get("status") or "")
                if detail:
                    line += ": " + detail
                lines.append(line)
    return "\n".join(lines)


def subagents_of(name):
    """Hauptsession und erfasste Subagenten aus Zustandsdatei und Server."""
    path = vibe_runs.subagent_state_path(vibe.logpath(name))
    state = vibe_runs.load_subagent_state(path)
    session = state.get("session") or ""
    entries = [public_subagent(entry) for entry in state.get("subagents") or []]
    if session:
        # Die Set-Abbildung wurde nie gelesen; der Unterstrich markiert das
        # angedeutete, nicht ausgebaute Feld.
        _known = {entry.get("session") for entry in entries if entry.get("session")}
        for live in live_subagents(session, name):
            existing = next(
                (entry for entry in entries if entry.get("session") == live["session"]),
                None,
            )
            if existing is None:
                entries.append(live)
                continue
            if not existing.get("agent") and live.get("agent"):
                existing["agent"] = live["agent"]
            if not existing.get("description") and live.get("description"):
                existing["description"] = live["description"]
            if live.get("status") == "running":
                existing["status"] = "running"
                existing["ended"] = 0
            elif existing.get("status") == "running":
                # B12: Der Server kennt die Kind-Session, führt sie aber nicht
                # als aktiv — ein festgehaltenes "running" ist damit beendet.
                # In der Sandbox liefert der Läufer keine Kind-Ereignisse; dort
                # beendet erst die B11-Regel „kein aktiver Lauf → leere Liste“
                # den Eintrag, nicht eine erfundene Serverlage.
                existing["status"] = "completed"
                if live.get("ended"):
                    existing["ended"] = live["ended"]
    return {"session": session, "subagents": entries}


def run_is_active(name):
    """Ein Lauf ist aktiv, solange Register oder tmux-Sitzung ihn führen.

    Das Register ist die Autorität für den Lebenszyklus: ``cmd_run`` legt den
    Eintrag vor der tmux-Sitzung an. Deshalb gilt ein Registereintrag im
    Zustand ``starting``/``running`` auch dann als aktiv, wenn die Sitzung noch
    nicht sichtbar ist. Ein beendeter Läufer setzt den Eintrag auf ``finished``;
    ohne Registereintrag entscheidet wie bisher die tmux-Sitzung (F10).
    """
    if vibe.run_state(name).get("running"):
        return True
    record = vibe.run_registry().latest(
        # Interne Pfadauflösung des Schwestermoduls; eine öffentliche
        # Entsprechung gibt es dort nicht, nur ihre Verwendung.
        project=vibe._real(vibe.ppath(name)))  # pylint: disable=protected-access
    return bool(record and record.get("state") in vibe_runs.LIVE_STATES)


def opencode_password():
    """Liest das opencode-Serverkennwort; es wird nie zurückgegeben oder geloggt."""
    try:
        with open(os.path.join(PATHS.runtime, "opencode.password"), encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def steer_server_url(value):
    """Prüft eine Server-URL aus der Serverdatei eines Laufs (B13).

    Akzeptiert werden ausschließlich Loopback-Ziele über HTTP mit gültigem
    Port. Alles andere liefert ``None``; der Aufrufer fällt dann auf den
    bisherigen gemeinsamen Server zurück.
    """
    try:
        target = urlparse(str(value or ""))
        port = target.port
    except ValueError:
        return None
    if target.scheme != "http":
        return None
    if (target.hostname or "").lower() not in LOOPBACK_HOSTS:
        return None
    if not port or not 1 <= port <= 65535:
        return None
    return target


def steer_endpoint(name):
    """Ziel-URL und Kennwort für eine Zusatzanweisung an den aktiven Lauf.

    B13: Ein Lauf ohne erreichbaren gemeinsamen Server schreibt seinen privaten
    Server nach ``<Laufprotokoll>.server.json``. Nur deren Loopback-URL wird
    angenommen; das Kennwort stammt aus der dort genannten Datei. Fehlt eine
    gültige Serverdatei, bleibt der bisherige Pfad unverändert.
    """
    path = str(vibe.logpath(name)) + ".server.json"
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        data = None
    if isinstance(data, dict) and steer_server_url(data.get("url")) is not None:
        password = ""
        password_file = data.get("password_file")
        if isinstance(password_file, str) and password_file:
            try:
                with open(password_file, encoding="utf-8") as handle:
                    password = handle.read().strip()
            except OSError:
                password = ""
        return data.get("url"), password or opencode_password()
    return vibe.OC_URL, opencode_password()


def deliver_steer(target_url, session, text, password):
    """Übergibt eine Zusatzanweisung per HTTP an den opencode-Server.

    Erfolg nur bei einer 2xx-Antwort mit gültiger Basic-Auth. Der Rückgabewert
    enthält nie das Kennwort.
    """
    target = urlparse(target_url)
    host = target.hostname or "127.0.0.1"
    port = target.port or 80
    if not session or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for char in session):
        return False, "Die Session-ID des Agenten ist ungültig."
    credential = base64.b64encode(("opencode:" + password).encode("utf-8")).decode("ascii")
    # opencode v2 nimmt neue Eingaben über /api/session/<id>/prompt mit dem
    # Feld ``text`` an. /message ist die reine Leseroute.
    payload = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
    connection = http.client.HTTPConnection(host, port, timeout=8)
    try:
        connection.request(
            "POST",
            "/api/session/" + quote(session, safe="") + "/prompt",
            body=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Basic " + credential,
            },
        )
        response = connection.getresponse()
        response.read()
        if 200 <= response.status < 300:
            return True, ""
        return False, f"Der opencode-Server hat die Zusatzanweisung abgelehnt (HTTP {response.status})."
    except (OSError, http.client.HTTPException) as error:
        return False, "Der opencode-Server ist nicht erreichbar: " + str(error)
    finally:
        connection.close()


def steer_project(name, text, session=None):
    """Prüft und übermittelt eine Zusatzanweisung an den laufenden Agenten.

    AP14: Ohne ``session`` geht die Anweisung an die Hauptsession des aktiven
    Laufs (F19-Verhalten). Mit ``session`` wird genau diese Session beliefert,
    wenn sie die Hauptsession des Laufs oder die Session eines erfassten oder
    live bekannten Subagenten des aktiven Laufs ist; fremde Sessions werden
    ohne Zustellung mit verständlicher Meldung abgelehnt.
    """
    text = str(text or "").strip()
    if not text:
        return False, "Bitte eine Zusatzanweisung eingeben."
    if len(text) > STEER_MAX_CHARS:
        return False, f"Die Zusatzanweisung ist länger als {STEER_MAX_CHARS} Zeichen."
    # F20: Bei Pi gibt es keine fortsetzbare Session, an die die Anweisung
    # gehen könnte. Die Auswahl wird vor dem Session-Bezug geprüft; eine
    # unlesbare/unbekannte Auswahl verhält sich wie bisher (opencode).
    try:
        selected = vibe_harness.read_selection(PATHS.state)
    except vibe_harness.HarnessError:
        selected = "opencode"
    if not vibe_harness.supports(selected, "steer"):
        return False, (
            "Zusatzanweisungen sind bei Pi nicht möglich: Pi läuft im "
            "Print-Modus (--no-session) ohne fortsetzbare Session; die "
            "Anweisung kann nicht an den Agenten übermittelt werden."
        )
    if not run_is_active(name):
        return False, "Kein aktiver Lauf: Eine Zusatzanweisung ist nur während der Ausführung möglich."
    state = subagents_of(name)
    target = state.get("session") or ""
    if session:
        # AP14: Zielgenaue Zustellung an Haupt- oder Subagentensession des
        # aktiven Laufs. Fremde Sessions werden nie beliefert.
        session = str(session).strip()
        tracked_sessions = {
            entry.get("session") for entry in state.get("subagents") or []
            if entry.get("session")
        }
        if session == target or session in tracked_sessions:
            target = session
        else:
            return False, (
                "Die angegebene Session gehört weder zur Hauptsession des "
                "Laufs noch zu einem erfassten Subagenten; die Anweisung "
                "wurde nicht gesendet."
            )
    if not target:
        return False, "Die Session des laufenden Agenten ist nicht erfasst; die Anweisung wurde nicht gesendet."
    # B13: Ziel und Kennwort kommen zuerst aus der Serverdatei des aktiven
    # Laufs; ohne gültige Datei bleibt der bisherige gemeinsame Server.
    target_url, password = steer_endpoint(name)
    if not password:
        return False, "Der opencode-Server ist nicht für Zusatzanweisungen angemeldet (Kennwortdatei fehlt)."
    delivered, detail = deliver_steer(target_url, target, text, password)
    if not delivered:
        return False, detail
    marker = " ".join(text.split())
    # Protokollmarker und Rückmeldung nennen das Ziel (Reviewrunde 1).
    agent = next(
        (entry.get("agent") for entry in state.get("subagents") or []
         if entry.get("session") == target),
        "",
    )
    label = f"{agent} ({target})" if agent else target
    try:
        with open(vibe.logpath(name), "a", encoding="utf-8") as handle:
            handle.write("\n[Dashboard] Zusatzanweisung an " + label + " übermittelt: " + marker + "\n")
    except OSError:
        # Die Zustellung ist erfolgt; ein nicht schreibbares Protokoll ändert
        # daran nichts und wird nicht als Fehlschlag vorgetäuscht.
        pass
    return True, f"Zusatzanweisung an {label} übermittelt."


def start_continue(name):
    """AP14: Startet den Lauf erneut und setzt die erfasste Session fort.

    Fortsetzen ist nur bei gestopptem Lauf und nur mit einer in der
    Zustandsdatei erfassten Hauptsession möglich; der Harness muss die
    Fähigkeit unterstützen (Pi im Print-Modus kann das nicht).
    """
    if run_is_active(name):
        return False, (
            "Fortsetzen ist nur bei gestopptem Lauf möglich; für dieses "
            "Projekt läuft bereits ein Lauf."
        )
    state = vibe_runs.load_subagent_state(
        vibe_runs.subagent_state_path(vibe.logpath(name)))
    session = str(state.get("session") or "").strip()
    if not session:
        return False, (
            "Keine erfasste Session zum Fortsetzen: Der letzte Lauf hat "
            "keine Session hinterlassen."
        )
    try:
        selected = vibe_harness.read_selection(PATHS.state)
    except vibe_harness.HarnessError:
        selected = "opencode"
    if not vibe_harness.supports(selected, "continue"):
        return False, (
            "Fortsetzen ist bei Pi nicht möglich: Pi läuft im Print-Modus "
            "(--no-session) ohne fortsetzbare Session; es wurde nichts "
            "gestartet."
        )
    return vibe_services.capture(vibe.cmd_run, name, continue_session=session)


def session_resume_supported():
    """AP19: Fortsetzen ist eine Harness-Fähigkeit; Fehler gelten als "nein".

    Dieselbe Fähigkeitsprüfung wie in ``start_continue``. Eine unlesbare oder
    unbekannte Auswahl darf hier nicht still als opencode durchgehen: ohne
    verlässliche Angabe wird konservativ ``False`` gemeldet.
    """
    try:
        selected = vibe_harness.read_selection(PATHS.state)
    except vibe_harness.HarnessError:
        return False
    return bool(vibe_harness.supports(selected, "continue"))


def reload_ui_data():
    """Lädt ui.json nach einer security-Aktion neu; Erfolg als boolescher Wert.

    Eine dann defekte Datei ist praktisch ausgeschlossen (save schreibt
    atomar und validiert vorher); sie wird gemeldet statt still als leer
    behandelt zu werden — Allowlist/Kennwort würden sonst unbemerkt weichen.
    """
    try:
        data = vibe_ui_config.load(PATHS.state)
    except vibe_ui_config.ConfigError:
        return False
    UI_DATA.clear()
    UI_DATA.update(data)
    return True


def restart_required():
    """Markiert geplante Port-/Bind-Änderungen, die erst nach Neustart wirken.

    ui.json kann jederzeit Port und Bind verschieben; der laufende Server
    hält die Werte seines Starts. weicht der geplante Zustand vom laufenden
    ab, zeigt die Oberfläche den Neustart-Hinweis.
    """
    planned_port = UI_DATA.get("ui_port") if UI_DATA.get("ui_port") is not None else PORT
    planned_bind = UI_DATA.get("ui_bind") if UI_DATA.get("ui_bind") is not None else BIND
    return planned_port != PORT or planned_bind != BIND


def security_data():
    """Zugriffssicherheit als Ansichtsobjekt, ohne Kennwort- oder Hash-Auskunft."""
    return {
        "port": PORT,
        "bind": BIND,
        "allowlist": list(UI_DATA.get("allowlist") or []),
        "password_set": bool(UI_DATA.get("password_hash")),
        "restart_required": restart_required(),
    }


def reload_ui_data():
    """Lädt ui.json nach einer security-Aktion neu; Erfolg als boolescher Wert.

    Eine dann defekte Datei ist praktisch ausgeschlossen (save schreibt
    atomar und validiert vorher); sie wird gemeldet statt still als leer
    behandelt zu werden — Allowlist/Kennwort würden sonst unbemerkt weichen.
    """
    try:
        data = vibe_ui_config.load(PATHS.state)
    except vibe_ui_config.ConfigError:
        return False
    UI_DATA.clear()
    UI_DATA.update(data)
    return True


def restart_required():
    """Markiert geplante Port-/Bind-Änderungen, die erst nach Neustart wirken.

    ui.json kann jederzeit Port und Bind verschieben; der laufende Server
    hält die Werte seines Starts. weicht der geplante Zustand vom laufenden
    ab, zeigt die Oberfläche den Neustart-Hinweis.
    """
    planned_port = UI_DATA.get("ui_port") if UI_DATA.get("ui_port") is not None else PORT
    planned_bind = UI_DATA.get("ui_bind") if UI_DATA.get("ui_bind") is not None else BIND
    return planned_port != PORT or planned_bind != BIND


def security_data():
    """Zugriffssicherheit als Ansichtsobjekt, ohne Kennwort- oder Hash-Auskunft."""
    return {
        "port": PORT,
        "bind": BIND,
        "allowlist": list(UI_DATA.get("allowlist") or []),
        "password_set": bool(UI_DATA.get("password_hash")),
        "restart_required": restart_required(),
    }


def language_data():
    """Globale Sprache aus UI_DATA als Ansichtsobjekt (AP21 v2).

    \u00dcber ui.json gesetzt und beim Start bzw. nach jedem Speichern in UI_DATA
    geladen. Fehlt der Wert, gilt der englische Standard — genau wie beim
    Rendern von index.html.
    """
    current = UI_DATA.get("language")
    if current not in vibe_ui_config.LANGUAGES:
        current = vibe_ui_config.DEFAULT_LANGUAGE
    return {
        "language": current,
        "languages": list(vibe_ui_config.LANGUAGES),
        "default": vibe_ui_config.DEFAULT_LANGUAGE,
    }


class RequestError(Exception):
    """Fehlerbearbeitung bei ungültiger Anfrage: HTTP-Status und Fehlercode."""

    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def known(n):
    """Prüft, ob es das Projekt gibt, und gibt den Namen unverändert zurück."""
    if n not in vibe.projects():
        raise AssertionError("Unbekanntes Projekt: " + n)
    return n

def known_scope(s):
    """Erlaubt nur 'global' oder ein bekanntes Projekt."""
    if s != "global":
        known(s)
    return s

def shutdown_server(delay=0.2):
    """Beendet den Annahme-Loop aus einem eigenen Thread.

    ``shutdown()`` darf nicht aus dem Thread aufgerufen werden, der
    ``serve_forever()`` ausführt. Der Hauptthread schließt danach den Server
    und wartet auf die Handler; aktive Streams sehen ``STOP``.
    """
    if delay:
        time.sleep(delay)
    if SRV is not None:
        with contextlib.suppress(Exception):
            SRV.shutdown()

def request_stop(_signum=None, _frame=None):
    """Signalhandler: keine Prozessabbrüche mitten in einer Antwort."""
    STOP.set()
    threading.Thread(
        target=shutdown_server, kwargs={"delay": 0}, daemon=True
    ).start()

class H(BaseHTTPRequestHandler):
    """Verarbeitet die Dashboard-Anfragen: Lesen mit Token, Schreiben mit Origin-Schutz."""

    # Der Superhandler legt close_connection erst in handle()/parse_request()
    # pro Anfrage neu fest; der Klassenwert ist nur die Ablage vor dem ersten
    # Aufruf und gibt das Attribut für die Prüfung als definiert an.
    close_connection = False

    def log_message(self, *a):
        pass

    def log_request(self, code="-", size="-"):
        """Zugriffslog ohne Query-String: Tokens gelangen nicht in Logs."""
        try:
            path = urlparse(getattr(self, "path", "")).path
            sys.stderr.write(f"[vibe] {self.command} {path} -> {code}\n")
            sys.stderr.flush()
        # Nur die realistischen Ursachen des Protokollierens: Fehler beim
        # Schreiben auf die Standardfehlerausgabe oder beim Verarbeiten
        # der Adressangabe; höheres Unerwartetes ist hier nicht nötig.
        except (OSError, ValueError):
            pass

    def _send(self, code, body, ctype="application/json", headers=None):
        b = body if isinstance(body, bytes) else (json.dumps(body, ensure_ascii=False).encode() if ctype == "application/json" else body.encode())
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in (headers or []):
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(b)

    def _error(self, code, slug, message):
        """Strukturierte Fehlerantwort; Meldungen werden vom Token bereinigt."""
        message = redact(message)
        self._send(code, {"ok": False, "error": {"code": slug, "message": message}, "message": message})

    def _security_view(self):
        """GET /api/security: Ansicht der Zugriffssicherheit (AP13)."""
        return self._send(200, {"ok": True, **security_data()})

    def _client_allowed(self):
        """Allowlist-Prüfung anhand der Verbindungs-Client-IP (AP13).

        Die Logik liegt in vibe_ui_config.client_allowed; Loopback bleibt
        immer erlaubt (Aussperrschutz). Die Ablehnung erfolgt vor allen
        anderen Prüfungen, damit ein nicht zugelassener Client überhaupt
        keine Antwortinhalte sieht.
        """
        address = self.client_address[0] if self.client_address else ""
        return vibe_ui_config.client_allowed(UI_DATA, address)

    def _session(self):
        """Session-Kennung aus dem Cookie oder ""; defekte Cookies sind leer."""
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie") or "")
        except CookieError:
            return ""
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else ""

    def _authorized(self, allow_query=False):
        # AP13: Erst die Session prüfen, dann X-Token; ?t= bleibt dem Stream
        # vorbehalten.
        session = self._session()
        if session:
            with SESSIONS_LOCK:
                if session in SESSIONS:
                    return True
        value = self.headers.get("X-Token") or ""
        if not value and allow_query:
            value = parse_qs(urlparse(self.path).query).get("t", [""])[0]
        if not value:
            return False
        # Als Bytes vergleichen: compare_digest wirft bei Nicht-ASCII-str einen
        # TypeError. Ein falsch kodiertes Token soll aber strukturiert als 403
        # abgelehnt werden statt die Verbindung unbehandelt abzubrechen.
        return secrets.compare_digest(value.encode("utf-8"), TOKEN.encode("utf-8"))

    def _guard(self, write):
        if not host_allowed(self.headers.get("Host")):
            self._error(403, "forbidden_host", "Host ist nicht Loopback")
            return False
        if write:
            origin = self.headers.get("Origin")
            if origin and not origin_allowed(origin):
                self._error(403, "forbidden_origin", "Origin gehört nicht zu dieser Instanz")
                return False
            site = self.headers.get("Sec-Fetch-Site")
            if site and site not in ("same-origin", "none"):
                self._error(403, "forbidden_origin", "Anfrage kommt von einer fremden Seite")
                return False
        return True

    def _read_json(self):
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            self.close_connection = True
            raise RequestError(415, "unsupported_media_type", "Content-Type muss application/json sein")
        raw = self.headers.get("Content-Length")
        if raw is None:
            self.close_connection = True
            raise RequestError(411, "length_required", "Content-Length fehlt")
        try:
            length = int(raw)
        except ValueError as error:
            self.close_connection = True
            raise RequestError(400, "invalid_length", "Content-Length ist keine Zahl") from error
        if length < 0:
            self.close_connection = True
            raise RequestError(400, "invalid_length", "Content-Length ist negativ")
        if length > MAX_BODY:
            # Nicht lesen: die Verbindung wird geschlossen, der Body verworfen.
            self.close_connection = True
            raise RequestError(413, "request_too_large", f"Anfrage ist größer als {MAX_BODY} Bytes")
        data = self.rfile.read(length) if length else b""
        if len(data) != length:
            self.close_connection = True
            raise RequestError(400, "incomplete_body", "Anfrage unvollständig")
        if not data.strip():
            return {}
        try:
            value = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RequestError(400, "invalid_json", "Ungültiges JSON") from error
        if not isinstance(value, dict):
            raise RequestError(400, "invalid_request", "JSON-Objekt erwartet")
        return value

    def _health(self):
        release = vibe_paths.release_info(PATHS)
        self._send(200, {
            "ok": True,
            "app": "vibe",
            "api": 1,
            "instance": INSTANCE,
            "bind": BIND,
            "port": PORT,
            "pid": os.getpid(),
            "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(STARTED)),
            # Releasebasis ohne Geheimnisse: Version, Commit und Herkunft der
            # Kennung. Fehlende Angaben bleiben ausdrücklich "unbekannt".
            "version": release["version"],
            "commit": release["commit"],
            "release_origin": release["origin"],
        })

    # http.server findet GET- und POST-Zustellung über diese konventionellen
    # Namen der Basisklasse; ein snake_case-Stil bricht die Weiterleitung.
    def do_GET(self):  # pylint: disable=invalid-name
        """Verarbeitet GET-Anfragen des Dashboards (Status, Streams, Daten)."""
        u = urlparse(self.path)
        q = parse_qs(u.query)
        # AP13: Allowlist vor allen anderen Prüfungen.
        if not self._client_allowed():
            return self._error(403, "forbidden_ip", "Client-IP ist nicht zugelassen")
        if not self._guard(False):
            return None
        if u.path == "/":
            return self._send(200, page(), "text/html")
        if u.path.startswith("/static/"):
            data, ctype = static_asset(u.path)
            if data is None:
                return self._error(404, "not_found", "nicht gefunden")
            return self._send(200, data, ctype)
        if u.path == "/api/health":
            return self._health()
        if not self._authorized(allow_query=u.path == "/api/stream"):
            return self._error(403, "unauthorized", "Token fehlt oder falsch")
        try:
            # AP13: Ansicht der Zugriffssicherheit (Port, Bind, Allowlist,
            # Kennwortstatus, Neustart-Markierung) — bewusst ohne Geheimnisse.
            if u.path == "/api/security":
                return self._security_view()
            if u.path == "/api/language":
                # AP21 v2: globale Sprache (auth wie die uebrigen APIs).
                return self._send(200, {"ok": True, **language_data()})
            if u.path == "/api/projects":
                return self._send(200, [vibe_services.project_row(vibe, n) for n in vibe.projects()])
            if u.path == "/api/run-state":
                n = known(q["name"][0])
                return self._send(200, {"running": run_is_active(n), "pause_after": vibe.pause_after_active(n)})
            if u.path == "/api/sessions":
                # AP19: Dieselben Limit- und Filterregeln wie in der CLI. Ein
                # zu großer Parameter wird gedeckt, ein ungültiger ignoriert.
                n = known(q.get("name", [""])[0])
                raw_limit = q.get("limit", [""])[0]
                limit = None
                if raw_limit:
                    try:
                        parsed = int(raw_limit)
                    except ValueError:
                        parsed = None
                    if parsed is not None and parsed >= 1:
                        limit = min(parsed, vibe_runs.SESSION_LIMIT_MAX)
                effective = (limit if limit is not None
                             else vibe_runs.SessionRegistry(PATHS.runtime).limit())
                entries = vibe_runs.session_overview(
                    PATHS.runtime, project=vibe.ppath(n), limit=limit,
                    text=q.get("text", [""])[0] or None)
                return self._send(200, {
                    "ok": True,
                    "running": run_is_active(n),
                    "resume_supported": session_resume_supported(),
                    "limit": int(effective),
                    "sessions": entries,
                })
            if u.path == "/api/subagents":
                n = known(q["name"][0])
                state = subagents_of(n)
                record = vibe.run_registry().latest(
                    # Wie in run_is_active: interne Pfadauflösung des
                    # Schwestermoduls, ohne öffentliche Entsprechung.
                    project=vibe._real(vibe.ppath(n))  # pylint: disable=protected-access
                )
                live = bool(record and record.get("state") in vibe_runs.LIVE_STATES)
                # B11: Nur Einträge des aktuellen Laufs. Ohne laufenden
                # Registereintrag liefert die Liste bewusst nichts — sonst
                # würden Überbleibsel früherer Läufe wieder auftauchen.
                entries = []
                if live:
                    started = run_start_epoch(record)
                    # Fail-open: Ohne lesbare Laufzeit erscheinen alle
                    # Einträge; ein Eintrag ohne bekannte Startzeit (0/None)
                    # bleibt sichtbar, statt still am Vergleich zu scheitern.
                    entries = [
                        listed_subagent(item) for item in state["subagents"]
                        if started is None
                        or entry_started(item) == 0
                        or entry_started(item) >= started
                    ]
                    entries.sort(key=entry_started, reverse=True)
                answer = {"ok": True, "running": run_is_active(n),
                          "subagents": entries}
                # F24: Der Name des aktuell arbeitenden Agenten kommt aus dem
                # Laufregister; ohne aktiven Lauf erscheint kein Name
                # (fehlendes Feld statt erfundener Angabe).
                if live:
                    answer["agent"] = str(record.get("agent") or "")
                if state["session"]:
                    answer["session"] = state["session"]
                return self._send(200, answer)
            if u.path == "/api/subagent-output":
                n = known(q["name"][0])
                session = q.get("session", [""])[0]
                state = subagents_of(n)
                entry = next(
                    (item for item in state["subagents"]
                     if session and item.get("session") == session),
                    None,
                )
                if entry is None:
                    return self._send(200, {
                        "ok": False,
                        "message": "Kein erfasster Subagent mit dieser Session. "
                                   "Die Ausgabe ist erst nach dem Start des Subagenten verfügbar.",
                    })
                # F30: Die Live-Ausgabe ist die Wahrheit, solange der Server
                # sie liefert; die erfasste Ausgabe der Zustandsdatei bleibt
                # Fallback (Sandbox ohne Server, fehlendes Kennwort, Störung,
                # noch keine Agentennachricht). Der Tail hält den Kartenkörper
                # im selben Budget wie gespeicherte Ausgaben.
                output = live_subagent_output(entry.get("session") or "", n)
                if not output.strip():
                    output = str(entry.get("output") or "")
                output = vibe_runs.output_tail(
                    output, vibe_runs.MAX_SUBAGENT_OUTPUT_BYTES)
                if not output.strip():
                    status = entry.get("status") or "unbekannt"
                    return self._send(200, {
                        "ok": False,
                        "status": status,
                        "message": f"Für diesen Subagenten liegt noch keine Ausgabe vor (Status: {status}).",
                    })
                return self._send(200, {
                    "ok": True,
                    "text": output,
                    "status": entry.get("status") or "",
                    "agent": entry.get("agent") or "",
                    "description": entry.get("description") or "",
                })
            if u.path == "/api/project":
                return self._send(200, vibe_services.project_detail(vibe, PATHS, known(q["name"][0])))
            if u.path == "/api/roots":
                return self._send(200, vibe_services.roots_info(vibe))
            if u.path == "/api/agents":
                return self._send(200, vibe_services.agents_info(vibe))
            if u.path == "/api/project-agents":
                return self._send(200, vibe_services.project_agents_info(vibe, known(q["name"][0])))
            if u.path == "/api/costs":
                n = q.get("name", [""])[0]
                return self._send(200, vibe.costs_project(known(n)) if n else vibe.costs_overview())
            if u.path == "/api/agent":
                scope = known_scope(q["scope"][0])
                snapshot = vibe.agent_snapshot(scope, q["name"][0])
                try:
                    fields = vibe.agent_fields(scope, snapshot.text)
                except ValueError as error:
                    # Eine defekte Datei bleibt im Rohtexteditor bearbeitbar.
                    fields = {"invalid": str(error)}
                return self._send(200, {"text": snapshot.text, "digest": snapshot.digest,
                                        "fields": fields,
                                        "backups": list(reversed(vibe.agent_backups(scope, q["name"][0])))})
            if u.path == "/api/mcp":
                return self._send(200, {"servers": vibe_mcp.list_all(), "projects": vibe.projects()})
            if u.path == "/api/mcp_entry":
                scope = known_scope(q["scope"][0])
                return self._send(200, vibe_mcp.get_entry(scope, q["name"][0]))
            if u.path == "/api/types":
                return self._send(200, vibe.types())
            if u.path == "/api/guide":
                return self._send(200, vibe_services.guide_info(vibe, known(q["name"][0])))
            if u.path == "/api/agents_file":
                return self._send(200, vibe.agents_file_view(known(q["name"][0])))
            # AP11: Priorisierung je Projekt einsehen (konfigurierte Reihenfolge
            # mit Status und effektive Abarbeitungsreihenfolge).
            if u.path == "/api/priority":
                return self._send(200, vibe_services.priority_info(vibe, known(q["name"][0])))
            if u.path == "/api/doctor":
                return self._send(200, [{"label": a, "ok": b, "hint": c} for a, b, c in vibe.doctor_checks()])
            if u.path == "/api/fritz":
                return self._send(200, vibe.fritz_status())
            if u.path == "/api/questions":
                return self._send(200, {"questions": vibe_questions.open_questions(PATHS.runtime)})
            if u.path == "/api/autonomous":
                n = q.get("name", [""])[0]
                if n:
                    known(n)
                return self._send(200, vibe_autonomous.status(PATHS.runtime, n))
            if u.path == "/api/harness":
                data = vibe_harness.status(PATHS.state)
                data["supported"] = vibe_harness.harness_ids()
                return self._send(200, data)
            if u.path == "/api/server":
                h = vibe.server_health()
                try:
                    selected = vibe_harness.read_selection(PATHS.state)
                except vibe_harness.HarnessError:
                    selected = "unbekannt"
                return self._send(200, {"up": bool(h), "url": vibe.OC_URL, "info": h,
                                        "harness": selected,
                                        "server_supported": selected == "opencode"})
            if u.path == "/api/stream":
                return self.stream(known(q["name"][0]), q.get("kind", ["run"])[0])
        except (AssertionError, ValueError) as e:
            return self._error(404, "not_found", str(e))
        except KeyError as e:
            return self._error(400, "invalid_request", "Parameter fehlt: " + str(e))
        # Letzte Abdeckung: Jede unerwartete Ausnahme wird als 500
        # strukturiert beantwortet, statt die Verbindung unkontrolliert abzubrechen.
        except Exception as e:  # pylint: disable=broad-exception-caught
            return self._error(500, "internal_error", f"{type(e).__name__}: {e}")
        self._error(404, "not_found", "nicht gefunden")
        return None
    # http.server findet POST-Zustellung über den klassenkonventionellen
    # Namen; ein snake_case-Stil bricht die Weiterleitung.
    def do_POST(self):  # pylint: disable=invalid-name
        """Verarbeitet die POST-Anfragen des Dashboards (steuernde Befehle)."""
        u = urlparse(self.path)
        # AP13: Allowlist vor allen anderen Prüfungen.
        if not self._client_allowed():
            return self._error(403, "forbidden_ip", "Client-IP ist nicht zugelassen")
        if not self._guard(True):
            return None
        # AP13: Die Anmeldung ist bewusst ohne Berechtigung erreichbar — sie
        # ist der einzige Weg, eine zu erhalten. Misserfolg bleibt
        # strukturiert, ohne Token oder Kennwort zu verraten.
        if u.path == "/api/login":
            # AP18: Kennwort-/Allowlist-Änderungen von außen (CLI `vibe ui
            # password`) wirken ohne Neustart; die Anmeldung liest ui.json
            # neu. Bleibt die Datei dabei defekt, bleibt der zuletzt
            # geladene Stand wirksam (reload_ui_data meldet, ersetzt aber
            # nichts still durch Defaults).
            reload_ui_data()
            try:
                body = self._read_json()
            except RequestError as e:
                return self._error(e.status, e.code, e.message)
            token_value = str(body.get("token") or "")
            password_value = str(body.get("password") or "")
            token_ok = bool(token_value) and secrets.compare_digest(
                token_value.encode("utf-8"), (TOKEN or "").encode("utf-8")
            )
            password_ok = bool(password_value) and vibe_ui_config.verify_password(
                UI_DATA, password_value
            )
            if not (token_ok or password_ok):
                return self._error(403, "unauthorized", "Anmeldung fehlgeschlagen")
            session = secrets.token_urlsafe(24)
            with SESSIONS_LOCK:
                SESSIONS[session] = time.time()
            # In-Memory-Session ohne Ablaufdatum: Sie endet mit dem
            # Dashboard-Prozess oder durch Logout; eine Session-Datei wäre
            # ein zweites Geheimnis auf der Platte.
            cookie = f"{SESSION_COOKIE}={session}; Path=/; HttpOnly; SameSite=Strict"
            return self._send(
                200, {"ok": True, "message": "Angemeldet"},
                headers=[("Set-Cookie", cookie)])
        if not self._authorized():
            return self._error(403, "unauthorized", "Token fehlt oder falsch")
        # AP13: Logout vor _read_json — der Aufruf kommt ohne Body.
        if u.path == "/api/logout":
            session = self._session()
            if session:
                with SESSIONS_LOCK:
                    SESSIONS.pop(session, None)
            return self._send(
                200, {"ok": True, "message": "Abgemeldet"},
                headers=[("Set-Cookie",
                          f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")])
        try:
            body = self._read_json()
        except RequestError as e:
            return self._error(e.status, e.code, e.message)
        if u.path == "/api/language":
            # AP21 v2: globale Sprache in ui.json persistieren. Die Validierung
            # verhindert, dass eine ungueltige Wahl die Datei veraendert; danach
            # neu laden, damit auch der naechste Seitenaufruf das Meta-Feld mit
            # der neuen Sprache rendert.
            value = body.get("language")
            try:
                vibe_ui_config.validate_language(value)
            except vibe_ui_config.ConfigError:
                return self._error(400, "invalid_language", "Ungueltige Sprache")
            try:
                vibe_ui_config.save(PATHS.state, {**UI_DATA, "language": value})
            except vibe_ui_config.ConfigError as error:
                return self._error(400, "invalid_language", str(error))
            if not reload_ui_data():
                return self._error(
                    500, "internal_error", "ui.json ist nach dem Speichern nicht lesbar")
            return self._send(200, {"ok": True, "language": value,
                                    "message": "Sprache gespeichert"})
        try:
            name = body.get("name", "")
            if u.path in ("/api/run", "/api/stop", "/api/verify", "/api/feedback", "/api/ticket", "/api/init", "/api/rights", "/api/pause", "/api/sandbox", "/api/guide", "/api/agents_file", "/api/costs", "/api/autonomous", "/api/steer", "/api/continue", "/api/sessions", "/api/github", "/api/priority"):
                known(name)
            extra = {}
            if u.path == "/api/security":
                # AP13: Zugriffssicherheit je Aktion ändern. Validierung
                # geschieht im Modul vor dem Schreiben; ungültige Eingaben
                # verändern ui.json nicht (→ 400 "rejected").
                act = body.get("action")
                ok, msg = True, ""
                try:
                    if act == "save":
                        update = {}
                        if body.get("port") is not None:
                            update["ui_port"] = body.get("port")
                        if body.get("bind") is not None:
                            update["ui_bind"] = body.get("bind")
                        if body.get("allowlist") is not None:
                            update["allowlist"] = body.get("allowlist")
                        vibe_ui_config.save(PATHS.state, {**UI_DATA, **update})
                        msg = "Zugriffssicherheit gespeichert"
                    elif act == "password":
                        if body.get("clear"):
                            vibe_ui_config.clear_password(PATHS.state)
                            msg = "Kennwort entfernt"
                        else:
                            vibe_ui_config.set_password(PATHS.state, body.get("password"))
                            msg = "Kennwort gesetzt"
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                except ValueError as e:
                    ok, msg = False, str(e)
                if ok:
                    # Nach jeder Aktion neu laden: Allowlist und Kennwort-
                    # status müssen die laufende Prüfung sofort berücksichtigen.
                    if not reload_ui_data():
                        return self._error(
                            500, "internal_error",
                            "ui.json ist nach dem Speichern nicht lesbar")
                    extra["security"] = security_data()
            elif u.path == "/api/steer":
                # AP14: Mit session-Adresse den Subagenten ansteuern.
                ok, msg = steer_project(
                    name, body.get("text", ""), body.get("session") or None)
            elif u.path == "/api/continue":
                # AP14: Letzten Lauf desselben Projekts fortsetzen.
                ok, msg = start_continue(name)
            elif u.path == "/api/sessions":
                # AP19: Genau die gewählte Session fortsetzen — nie eine
                # fremde oder während eines aktiven Laufs.
                session = str(body.get("session") or "")
                if body.get("action") != "continue":
                    ok, msg = False, (
                        "Unbekannte Aktion für /api/sessions: nur 'continue' "
                        "wird unterstützt.")
                else:
                    entry = vibe_runs.SessionRegistry(PATHS.runtime).get(session)
                    project = vibe._real(vibe.ppath(name))  # pylint: disable=protected-access
                    if (not entry or os.path.realpath(
                            str(entry.get("project") or "")) != project):
                        ok, msg = False, (
                            f"Session '{session}' ist für Projekt '{name}' "
                            "nicht im Register.")
                    elif run_is_active(name):
                        ok, msg = False, (
                            "Fortsetzen ist nur bei gestopptem Lauf möglich; "
                            "für dieses Projekt läuft bereits ein Lauf.")
                    elif not session_resume_supported():
                        ok, msg = False, (
                            "Fortsetzen ist bei Pi nicht möglich: Pi läuft im "
                            "Print-Modus (--no-session) ohne fortsetzbare "
                            "Session; es wurde nichts gestartet.")
                    else:
                        ok, msg = vibe_services.capture(
                            vibe.cmd_run, name, continue_session=session)
            elif u.path == "/api/run":
                ok, msg = vibe_services.capture(vibe.cmd_run, name, body.get("agent") or None, keep_changes=bool(body.get("keep_changes")))
            elif u.path == "/api/stop":
                ok, msg = vibe_services.capture(vibe.cmd_stop, name, body.get("run_id") or None)
            elif u.path == "/api/verify":
                mode = body.get("mode")
                if mode not in vibe.VERIFY_MODES:
                    ok, msg = False, (
                        "Unbekannter Prüfmodus: " + str(mode)
                        + " (erlaubt: " + ", ".join(vibe.VERIFY_MODES) + ")")
                else:
                    ok, msg = vibe_services.verify_bg(vibe, name, mode)
            elif u.path == "/api/init":
                ok, msg = vibe_services.capture(vibe.cmd_init, name, body.get("type") or None)
            elif u.path == "/api/feedback":
                act = body.get("action") or "add"
                try:
                    if act == "add":
                        t = (body.get("title") or "").strip()
                        assert t, "Titel fehlt"
                        kind = body.get("kind") or "feedback"
                        if kind == "bug":
                            num = vibe.add_bug(name, t, body.get("description", ""))
                            ok, msg = True, f"B{num} eingetragen"
                        else:
                            num = vibe.add_feedback(name, t, body.get("description", ""))
                            ok, msg = True, f"F{num} eingetragen"
                    elif act == "update":
                        fid = (body.get("id") or "").strip()
                        assert fid, "Feedback-ID fehlt"
                        vibe.feedback_update(name, fid, body.get("title"), body.get("description", ""))
                        ok, msg = True, f"{fid} gespeichert"
                    elif act == "delete":
                        fid = (body.get("id") or "").strip()
                        assert fid, "Feedback-ID fehlt"
                        vibe.feedback_delete(name, fid)
                        ok, msg = True, f"{fid} gelöscht"
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/ticket":
                act = body.get("action") or "add"
                try:
                    if act == "add":
                        # F23: Ohne ID vergibt add_ticket die ID automatisch.
                        tid = vibe.add_ticket(
                            name, (body.get("id") or "").strip(),
                            body.get("title"), body.get("description", ""))
                        ok, msg = True, f"{tid} angelegt"
                    elif act == "update":
                        tid = (body.get("id") or "").strip()
                        assert tid, "ID fehlt"
                        vibe.ticket_update(name, tid, body.get("title"), body.get("description", ""))
                        ok, msg = True, f"{tid} gespeichert"
                    elif act == "delete":
                        tid = (body.get("id") or "").strip()
                        assert tid, "ID fehlt"
                        vibe.ticket_delete(name, tid)
                        ok, msg = True, f"{tid} gelöscht"
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/new":
                ok, msg = vibe_services.capture(vibe.cmd_new, name, body.get("type", "generic"), body.get("tpl") or None)
            elif u.path == "/api/clone":
                # AP8: Projekt aus Git/GitHub auschecken und mit den lokalen
                # vibe-Einstellungen einrichten; Fehler strukturiert melden.
                try:
                    url = str(body.get("url") or "").strip()
                    if not url:
                        raise ValueError("Remote-Adresse fehlt")
                    found, msg = vibe.checkout_from_github(
                        url, str(body.get("name") or "").strip() or None)
                    ok, extra["project"] = True, found
                except (ValueError, OSError, vibe_storage.StorageError) as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/roots":
                act = body.get("action")
                path = body.get("path", "")
                try:
                    if act == "add":
                        p = vibe.root_add(path)
                    elif act == "remove":
                        vibe.root_remove(path)
                        p = path
                    else:
                        # Cache-Auflösung des Schwestermoduls; die Leere der
                        # Projektliste gehört zum gewählten Verhalten, eine
                        # öffentliche Entsprechung fehlt dort.
                        vibe._pm.clear()  # pylint: disable=protected-access
                        p = ""
                    pm = vibe.project_map()
                    found = [k for k, v in pm.items() if p and os.path.dirname(v) == os.path.abspath(os.path.expanduser(p))]
                    ok, msg = True, (f"{len(found)} Projekt(e) in {p}: {', '.join(found) or '-'}" if act == "add" else "OK")
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/rights":
                act = body.get("action")
                ok, msg, changed = True, "", None
                try:
                    if act == "add":
                        dirs = vibe.write_dirs_add(name, body.get("path", ""))
                        msg = "Verzeichnis hinzugefügt"
                    elif act in ("remove", "rm"):
                        dirs = vibe.write_dirs_remove(name, body.get("path", ""))
                        msg = "Verzeichnis entfernt"
                    elif act == "reset":
                        dirs = vibe.write_dirs_reset(name)
                        msg = "Standardverzeichnisse wiederhergestellt"
                    elif act == "apply":
                        dirs = vibe.write_dirs(name)
                        changed = vibe.apply_write_dirs_to_project(name)
                        msg = ("Schreibrechte auf " + str(len(changed)) + " Projektagent(en) angewendet: " + ", ".join(changed)) if changed else "Nichts geändert – keine Projektagenten mit Schreibrecht vorhanden"
                    else:
                        ok, msg, dirs = False, "Unbekannte Aktion", None
                    if dirs is not None:
                        extra["write_dirs"] = dirs
                        extra["custom"] = vibe.write_dirs_custom(name)
                    if changed is not None:
                        extra["changed"] = changed
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/sandbox":
                act = body.get("action")
                ok, msg, status = True, "", None
                try:
                    if act == "on":
                        status = vibe.sandbox_set(name, True)
                        msg = "Sandbox eingeschaltet"
                    elif act == "off":
                        status = vibe.sandbox_set(name, False)
                        msg = "Sandbox ausgeschaltet"
                    elif act == "tools":
                        status = vibe.sandbox_tools(name, body.get("tools", ""))
                        msg = "Build-Werkzeuge gespeichert"
                    elif act == "check":
                        checked = vibe.sandbox_check(name)
                        ok, msg = checked["ok"], checked["message"]
                        status = vibe.sandbox_status(name)
                        extra["check"] = checked
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                    if status is not None:
                        extra["sandbox"] = status
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/github":
                act = body.get("action") or "status"
                ok, msg = True, ""
                try:
                    if act == "settings":
                        values = {}
                        if "enabled" in body:
                            values["GITHUB_ENABLED"] = "1" if body.get("enabled") else ""
                        if "repo" in body:
                            repo = str(body.get("repo") or "").strip()
                            if repo and not vibe_github.RE_REPO.match(repo):
                                raise ValueError("Repository in der Form owner/name angeben")
                            values["GITHUB_REPO"] = repo
                        if "label" in body:
                            label = str(body.get("label") or "").strip()
                            if any(c in label for c in ("\n", "\r", "\x00")):
                                raise ValueError("Label darf keine Zeilenumbrüche enthalten")
                            values["GITHUB_LABEL"] = label
                        if "api" in body:
                            api = str(body.get("api") or "").strip()
                            if api:
                                vibe_github.check_api(api)
                            values["GITHUB_API"] = api
                        if "base" in body:
                            base = str(body.get("base") or "").strip()
                            if base:
                                # AP9: Basis-Branch für Merge-Requests; die
                                # Validierung teilt sich mit checkout/push.
                                base = vibe_github.branch_name(base)
                            values["GITHUB_BASE"] = base
                        if values:
                            vibe.set_env_values(name, values)
                        msg = "GitHub-Einstellungen gespeichert"
                        extra["github"] = vibe_github.status(name)
                    elif act == "link":
                        url = str(body.get("url") or "").strip()
                        if not url:
                            raise ValueError("Remote-Adresse fehlt")
                        extra["github"] = vibe.github_link(name, url)
                        msg = "Verknüpfung gespeichert: " + vibe_github.mask_url(url)
                    elif act == "unlink":
                        extra["github"] = vibe.github_unlink(name)
                        msg = "Verknüpfung gelöst"
                    elif act == "token.save":
                        # B7/AP9: Token in der Oberfläche hinterlegen — seit
                        # AP9 je Projekt, verschlüsselt im Zustandsordner.
                        vibe_github.save_project_token(vibe.ppath(name),
                                                       body.get("token") or "")
                        extra["github"] = vibe.github_status(name)
                        extra["auth"] = (extra["github"] or {}).get("auth")
                        msg = "GitHub-Token für dieses Projekt gespeichert (verschlüsselt)"
                    elif act == "token.clear":
                        vibe_github.delete_project_token(vibe.ppath(name))
                        extra["github"] = vibe.github_status(name)
                        extra["auth"] = (extra["github"] or {}).get("auth")
                        msg = "GitHub-Token für dieses Projekt entfernt"
                    elif act == "fetch":
                        ok, msg = vibe_github.fetch(vibe.ppath(name))
                        extra["github"] = vibe_github.status(name)
                    elif act == "pull":
                        ok, msg = vibe_github.pull(vibe.ppath(name))
                        extra["github"] = vibe_github.status(name)
                    elif act == "push":
                        ok, msg = vibe_github.push(
                            vibe.ppath(name), branch=str(body.get("branch") or ""),
                            target=str(body.get("target") or ""))
                        extra["github"] = vibe_github.status(name)
                    elif act == "checkout":
                        ok, msg = vibe_github.checkout_branch(
                            vibe.ppath(name), body.get("branch") or "")
                        extra["github"] = vibe_github.status(name)
                    elif act == "connection":
                        # AP9: Verbindungsprüfung für die Oberfläche; wirft
                        # niemals, das Ergebnis wird direkt angezeigt.
                        view = vibe_github.connection(vibe.ppath(name))
                        ok = bool(view.get("ok"))
                        msg = view.get("message") or ("Verbindung: "
                                                      + ("OK" if ok else "FEHLER"))
                        extra["connection"] = view
                    elif act == "issues":
                        label = body.get("label")
                        extra["issues"] = vibe.github_issues(name, None if label is None else str(label))
                        extra["label"] = str(label) if label is not None else ""
                        msg = f"{len(extra['issues'])} offene Issue(s) geladen"
                    elif act == "import":
                        added, seen = vibe.github_issues_import(name, str(body.get("label") or "") if body.get("label") is not None else None)
                        ok = bool(added) or seen == 0
                        if not added and seen:
                            msg = f"Keine neuen Issues ({seen} gesehen); TICKETS.md unverändert."
                        else:
                            msg = ("Arbeitspakete übernommen: " + ", ".join(added)) if added else "Keine offenen Issues."
                    elif act == "pr":
                        result = vibe.github_pr(name, title=body.get("title") or None,
                                                base=body.get("base") or None,
                                                confirm=bool(body.get("confirm")))
                        if not result.get("ok"):
                            ok = False
                        msg = result.get("message") or ""
                        extra["pull_request"] = result
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                        extra["github"] = vibe_github.status(name)
                except ValueError as e:
                    ok, msg = False, str(e)
                    extra["github"] = vibe_github.status(name)
                try:
                    extra["github"] = extra.get("github") or vibe_github.status(name)
                # Die Statusansicht ist best effort: Alle praktischen Ursachen
                # dort sind Dateisystem- oder Text- und Adress-Lesefehler;
                # Git-Aufrufe fängt vibe_github selbst ab.
                except (OSError, ValueError):
                    pass
            elif u.path == "/api/pause":
                act = body.get("action") or "on"
                ok, msg = True, ""
                try:
                    if act in ("on", "an", "request"):
                        vibe.pause_after_request(name)
                        msg = "Pause nach dem aktuellen Arbeitspaket angefordert"
                    elif act in ("off", "aus", "cancel"):
                        released = vibe.pause_after_cancel(name)
                        msg = "Pause-Anforderung aufgehoben" if released else "Keine Pause angefordert"
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                    extra["pause_after"] = vibe.pause_after_active(name)
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/costs":
                act = body.get("action") or "prices"
                ok, msg = True, ""
                try:
                    if act == "prices":
                        vibe.costs_set_prices(name, body.get("prices") or {}, expected=body.get("expected"))
                        msg = "Preise gespeichert"
                        extra["costs"] = vibe.costs_project(name)
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                except vibe_storage.ConcurrentChangeError as e:
                    return self._error(409, "conflict", str(e))
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/fritz":
                act = body.get("action")
                ok, msg = True, ""
                try:
                    if act in ("automation", "on", "off", "set"):
                        enabled = (act == "on") if act in ("on", "off") else body.get("enabled")
                        if not isinstance(enabled, bool):
                            raise ValueError("enabled muss true oder false sein")
                        vibe.fritz_automation_set(enabled)
                        msg = "Fritzbox-Automatik " + ("an" if enabled else "aus")
                    elif act == "reconnect":
                        result = vibe.fritz_reconnect()
                        extra["result"] = result
                        ok, msg = result["ok"], result["message"]
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                except ValueError as e:
                    ok, msg = False, str(e)
                extra["fritz"] = vibe.fritz_status()
            elif u.path == "/api/questions":
                act = body.get("action") or "answer"
                try:
                    if act == "answer":
                        qid = body.get("id")
                        option = body.get("option")
                        if option is not None and (isinstance(option, bool) or not isinstance(option, int)):
                            raise ValueError("Auswahl muss eine Zahl sein")
                        answer = vibe_questions.answer(
                            PATHS.runtime, qid, option=option,
                            text=body.get("text") or "", by="web",
                        )
                        ok, msg = True, "Antwort gespeichert: " + (answer["option_text"] or answer["text"])
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                except ValueError as e:
                    ok, msg = False, str(e)
                extra["questions"] = vibe_questions.open_questions(PATHS.runtime)
            elif u.path == "/api/autonomous":
                act = body.get("action") or "status"
                state = None
                try:
                    if act == "on":
                        state = vibe_autonomous.set_enabled(PATHS.runtime, name, True)
                        ok, msg = True, "Autonomer Modus für " + name + " aktiviert"
                    elif act == "off":
                        state = vibe_autonomous.set_enabled(PATHS.runtime, name, False)
                        ok, msg = True, "Autonomer Modus für " + name + " ausgeschaltet"
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                except ValueError as e:
                    ok, msg = False, str(e)
                state = state or vibe_autonomous.status(PATHS.runtime, name)
                extra["autonomous"] = state
                extra.update(state)
            elif u.path == "/api/guide":
                act = body.get("action") or "save"
                path = vibe.ppath(name)
                try:
                    if act == "save":
                        result = vibe_guide.apply(path, body.get("answers") or {}, replace=body.get("replace") or (), name=name, templates_dir=vibe.TPL)
                        ok, msg = True, result["message"]
                        extra["guide"] = result
                    elif act == "agent":
                        started = vibe_guide.start_agent(path, body.get("step", ""), name=name, note=body.get("note", ""), log_dir=vibe.LOGS)
                        ok, msg = True, "Agentenauftrag gestartet. Der Entwurf erscheint nach dem Lauf unter .vibe/guide/."
                        extra["agent"] = started
                    elif act == "draft_apply":
                        result = vibe_guide.draft_apply(path, body.get("step", ""), name=name, templates_dir=vibe.TPL)
                        ok, msg = True, "Entwurf übernommen. " + result["message"]
                        extra["guide"] = result
                    elif act == "draft_discard":
                        vibe_guide.draft_discard(path, body.get("step", ""))
                        ok, msg = True, "Entwurf verworfen."
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/agents_file":
                act = body.get("action") or "save"
                if act == "save":
                    try:
                        vibe.agents_file_save(
                            name, body.get("before", ""), body.get("after", ""),
                            body.get("digest"))
                        ok, msg = True, "AGENTS.md gespeichert"
                    except ValueError as e:
                        ok, msg = False, str(e)
                    extra["agents_file"] = vibe.agents_file_view(name)
                elif act == "create":
                    try:
                        created = vibe.agents_file_create(name)
                        ok, msg = True, (
                            "AGENTS.md aus der Vorlage angelegt"
                            if created != "kept"
                            else "AGENTS.md war bereits vorhanden")
                    except ValueError as e:
                        ok, msg = False, str(e)
                    extra["agents_file"] = vibe.agents_file_view(name)
                else:
                    # Der Test-Agent erwartet für unbekannte Aktionen einen
                    # Clientfehler; bekannte Fehler bleiben als ok:false.
                    return self._error(400, "rejected", "Unbekannte Aktion")
            elif u.path == "/api/priority":
                # AP11: Priorisierung setzen oder leeren; die Antwort enthält
                # die aktualisierte Ansicht, damit die Karte sofort stimmt.
                act = body.get("action") or "set"
                try:
                    if act == "set":
                        order = vibe_packages.normalize_order(
                            vibe.ppath(name), str(body.get("order") or ""))
                        vibe.set_env_values(
                            name, {vibe_packages.ORDER_KEY: " ".join(order)})
                        # F29: ok gehört zur Antwort, sonst UnboundLocalError.
                        ok, msg = True, ("Priorisierung gespeichert" if order
                                         else "Leere Priorisierung gespeichert (Standardordnung)")
                    elif act == "clear":
                        vibe.set_env_values(name, {vibe_packages.ORDER_KEY: ""})
                        ok, msg = True, "Priorisierung geleert (Standardordnung)"
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                    extra["priority"] = vibe_services.priority_info(vibe, name)
                except vibe_storage.ConcurrentChangeError as e:
                    return self._error(409, "conflict", str(e))
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/project-agents":
                project = known(body.get("name", ""))
                try:
                    vibe.project_agent_set(project, body.get("agent", ""),
                                           selected=body.get("selected"),
                                           model=body.get("model"))
                    ok, msg = True, "Agentenauswahl gespeichert"
                except vibe_storage.ConcurrentChangeError as e:
                    return self._error(409, "conflict", str(e))
                except ValueError as e:
                    ok, msg = False, str(e)
                extra["project_agents"] = vibe_services.project_agents_info(vibe, project)
            elif u.path == "/api/agent_template":
                scope = known_scope(body.get("scope", "global"))
                dirs = vibe.write_dirs(scope) if scope != "global" else None
                ok, msg = True, vibe.agent_template(body.get("description", ""), body.get("mode", "subagent"), body.get("model", ""), body.get("temperature", ""), body.get("steps", ""), body.get("perm", "lesen"), body.get("prompt", ""), write_dirs=dirs)
            elif u.path == "/api/agent":
                act = body.get("action")
                scope = known_scope(body.get("scope", "global"))
                an = body.get("name", "")
                try:
                    if act == "save":
                        # Die strukturierten Eingaben sind auch ohne Klick auf
                        # „In Rohtext übernehmen“ wirksam. Die Oberfläche sendet
                        # nur geänderte Felder, damit freie Rohtextänderungen an
                        # anderen Stellen erhalten bleiben.
                        text = body.get("text", "")
                        if body.get("values") is not None:
                            text = vibe.agent_render_fields(scope, text, body.get("values"))
                        # AP03: Ergebnis, Hierarchie und Rolle werden vor dem
                        # Schreiben geprüft. Ungültige Werte dürfen die
                        # Agentendatei nicht verändern.
                        result = body.get("result")
                        task_allowed = body.get("task_allowed")
                        task_all = body.get("task_all")
                        role = body.get("role")
                        if result is not None and not isinstance(result, str):
                            raise ValueError("Das Ergebnis muss eine Zeichenkette sein.")
                        if role is not None:
                            if not isinstance(role, str):
                                raise ValueError("Die Rolle muss eine Zeichenkette sein.")
                            if scope != "global":
                                raise ValueError("Rollen gelten nur für systemweite Agenten.")
                            role = role.strip()
                            if role and role not in vibe.ROLE_NAMES:
                                raise ValueError("Unbekannte Rolle: " + role)
                            roles = vibe.profiles_load().get("rollen", {})
                            if roles.get(an) == "vibe" and role != "vibe" and not any(
                                value == "vibe" and agent != an
                                for agent, value in roles.items()
                            ):
                                raise ValueError(
                                    "Der letzte Vibe-Agent kann nicht entfernt werden. Zuerst einem anderen Agenten die Rolle 'vibe' zuweisen."
                                )
                        if task_all is not None:
                            if not isinstance(task_all, bool):
                                raise ValueError("'task_all' muss wahr oder falsch sein.")
                            if scope != "global":
                                raise ValueError("Subagenten-Rechte gelten nur für systemweite Agenten.")
                            text = vibe.agent_render_task(scope, text, [], allow_all=task_all)
                        elif task_allowed is not None:
                            if scope != "global":
                                raise ValueError("Subagenten-Rechte gelten nur für systemweite Agenten.")
                            # F32: Der Vibe-Agent wird über die Rolle erkannt — auch wenn die Rolle
                            # im selben Request gesetzt oder entfernt wird.
                            effective_vibe = vibe.vibe_agent_name()
                            if role is not None and str(role).strip() == "vibe":
                                effective_vibe = an
                            elif role is not None and not str(role).strip() and effective_vibe == an:
                                # Die Rollenvalidierung oben („Der letzte
                                # Vibe-Agent kann nicht entfernt werden…“)
                                # stellt sicher, dass hier ein anderer
                                # Vibe-Agent übrig bleibt; der gilt danach.
                                others = [agent for agent, value in
                                          vibe.profiles_load().get("rollen", {}).items()
                                          if value == "vibe" and agent != an]
                                effective_vibe = others[0]
                            vibe.agent_validate_hierarchy(an, task_allowed, own_text=text,
                                                          vibe_agent=effective_vibe)
                            text = vibe.agent_render_task(scope, text, task_allowed)
                        # F32-Invariante: Der Vibe-Agent darf nach dem
                        # Speichern keine Selbstfreigabe besitzen — egal, auf
                        # welchem Weg sie in den Text kam (task_allowed,
                        # Rohtext oder unveränderter bestehender Block).
                        if scope == "global":
                            effective_role = (
                                role if role is not None
                                else str(vibe.profiles_load().get("rollen", {}).get(an) or "")
                            )
                            if effective_role == "vibe":
                                policy = vibe.agent_task_policy(text)
                                if policy["mode"] == "custom" and an in policy["allowed"]:
                                    raise ValueError(
                                        "Der Vibe-Agent darf keine Subagenten "
                                        "seines eigenen Typs aufrufen."
                                    )
                        warn = vibe.agent_write(scope, an, text, create=bool(body.get("create")), expected=body.get("expected"))
                        if result is not None:
                            vibe.agent_result_set(an, result)
                        if role is not None:
                            vibe.agent_role_set(an, role)
                        snapshot = vibe.agent_snapshot(scope, an)
                        extra["text"] = snapshot.text
                        extra["digest"] = snapshot.digest
                        ok, msg = True, "Gespeichert" + (" – Hinweis: " + " ".join(warn) if warn else "")
                    elif act == "delete":
                        vibe.agent_delete(scope, an)
                        ok, msg = True, "Gelöscht (Sicherung in agent-backups)"
                    elif act == "role":
                        if scope != "global":
                            raise ValueError("Rollen gelten nur für systemweite Agenten.")
                        vibe.agent_role_set(an, body.get("role", ""))
                        ok, msg = True, "Rolle gespeichert"
                    elif act == "copy":
                        vibe.agent_copy(scope, an, known_scope(body.get("to", "global")))
                        ok, msg = True, "Kopiert"
                    elif act == "render":
                        # Vorschau: strukturierte Eingaben in den Rohtext übernehmen,
                        # ohne die Datei zu verändern.
                        extra["text"] = vibe.agent_render_fields(scope, body.get("text", ""), body.get("values"))
                        ok, msg = True, "Eingaben in den Rohtext übernommen – noch nicht gespeichert"
                    elif act == "scaffold":
                        # AP03: Prompt-Gerüst für Aufgabe, Ergebnis und Grenzen.
                        # Es wird nur zurückgegeben, nie geschrieben.
                        ok, msg = True, vibe.agent_prompt_scaffold(body.get("aufgabe", ""), body.get("ergebnis", ""), body.get("grenzen", ""))
                    elif act == "restore":
                        vibe.agent_restore(scope, an, body.get("backup") or None)
                        snapshot = vibe.agent_snapshot(scope, an)
                        extra["text"] = snapshot.text
                        extra["digest"] = snapshot.digest
                        ok, msg = True, "Sicherung wiederhergestellt"
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                except vibe_storage.ConcurrentChangeError as e:
                    return self._error(409, "conflict", str(e))
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/mcp":
                act = body.get("action")
                scope = known_scope(body.get("scope", "global"))
                entry = body.get("entry")
                try:
                    if act == "save":
                        p = vibe_mcp.save(scope, name, entry, body.get("old_name") or None, bool(body.get("create")), expected=body.get("expected"))
                        notice = vibe_mcp.version_notice()
                        ok, msg = True, ("Gespeichert in " + p + " (Sicherung in config-backups). opencode liest die Konfiguration beim nächsten Start."
                                         + (" Hinweis: " + notice if notice else ""))
                    elif act == "delete":
                        vibe_mcp.delete(scope, name)
                        ok, msg = True, "Gelöscht (Sicherung in config-backups)"
                    elif act == "toggle":
                        en = vibe_mcp.toggle(scope, name)
                        ok, msg = True, "aktiviert" if en else "deaktiviert"
                    elif act == "test":
                        extra["result"] = vibe_mcp.test(scope, name or None, entry)
                        ok, msg = True, "Test beendet"
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                except vibe_storage.ConcurrentChangeError as e:
                    return self._error(409, "conflict", str(e))
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/profiles":
                act = body.get("action")
                try:
                    if act == "save":
                        d = vibe.profiles_load()
                        data = body.get("data") or {}
                        for k in ("rollen", "profile"):
                            if isinstance(data.get(k), dict):
                                d[k] = data[k]
                        vibe.profiles_save(d)
                        ok, msg = True, "Profile gespeichert"
                    elif act == "use":
                        done, skipped = vibe.profile_apply(body.get("profile", ""))
                        ok, msg = True, "Angewendet: " + "; ".join(done) + (" | übersprungen: " + "; ".join(skipped) if skipped else "")
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/model":
                ok, msg = vibe_services.capture(vibe.cmd_model, body.get("agent", ""), body.get("model", ""), body.get("scope", "global"))
            elif u.path == "/api/server":
                ok, msg = vibe_services.capture(vibe.cmd_server, "start" if body.get("action") == "start" else "stop")
            elif u.path == "/api/harness":
                try:
                    if body.get("action") == "use":
                        chosen = body.get("harness", "")
                        path = vibe_harness.write_selection(PATHS.state, chosen)
                        ok, msg = True, "Gespeichert: " + chosen + " (" + path + ")"
                    elif body.get("action") in (None, "", "setup"):
                        chosen = body.get("harness") or vibe_harness.read_selection(PATHS.state)
                        plan = vibe_harness.setup_plan(chosen)
                        ok, msg = True, plan["hint"]
                        extra["plan"] = plan
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                except vibe_harness.HarnessError as error:
                    ok, msg = False, str(error)
            elif u.path == "/api/shutdown":
                # Zuerst Streams und Handler informieren, dann die Antwort
                # senden und den Annahme-Loop aus einem eigenen Thread stoppen.
                STOP.set()
                self._send(200, {"ok": True, "message": "Dashboard wird beendet"})
                threading.Thread(target=shutdown_server, daemon=True).start()
                return None
            else:
                return self._error(404, "not_found", "nicht gefunden")
            message = redact(msg)
            out = {"ok": ok, "message": message}
            if not ok:
                out["error"] = {"code": "rejected", "message": message}
            out.update(extra)
            self._send(200 if ok else 400, out)
        except AssertionError as e:
            self._error(400, "invalid_request", str(e))
        except ValueError as e:
            self._error(400, "invalid_request", str(e))
        # Letzte Abdeckung: Jede unerwartete Ausnahme wird als 500
        # strukturiert beantwortet, statt die Verbindung unkontrolliert abzubrechen.
        except Exception as e:  # pylint: disable=broad-exception-caught
            self._error(500, "internal_error", f"{type(e).__name__}: {e}")
        return None
    def stream(self, name, kind):
        """Sendet den Protokollstand als SSE-Antwort, bis STOP gesetzt wird."""
        path = vibe.logpath(name, "verify" if kind == "verify" else "run")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        def send(lines):
            self.wfile.write(("data: " + json.dumps(lines, ensure_ascii=False) + "\n\n").encode())
            self.wfile.flush()
        try:
            pos = os.path.getsize(path) if os.path.exists(path) else 0
            send(vibe_services.tail(path, 80) or ["(noch keine Ausgabe)"])
            while not STOP.is_set():
                if STOP.wait(1):
                    break
                if os.path.exists(path):
                    size = os.path.getsize(path)
                    if size < pos:
                        pos = 0
                    if size > pos:
                        with open(path, "rb") as f:
                            f.seek(pos)
                            chunk = f.read()
                            pos = size
                        send(ANSI.sub("", chunk.decode("utf-8", "replace")).splitlines())
                        continue
                self.wfile.write(b": ping\n\n")
                self.wfile.flush()
            if STOP.is_set():
                send(["Dashboard wird beendet."])
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.close_connection = True

STATIC_FILES = {
    "/static/styles.css": ("web/styles.css", "text/css"),
    "/static/i18n.js": ("web/i18n.js", "application/javascript"),
    "/static/app.js": ("web/app.js", "application/javascript"),
}

def page():
    """Liefert die Oberfläche aus der eigenen HTML-Datei.

    Der opencode-Link kommt aus einem Meta-Feld; damit bleibt das getrennte
    JavaScript unverändert und ohne serverseitige Textersetzung. Der einmal
    gelesene Inhalt wird am Funktionsobjekt abgelegt, damit der Modulnamensbereich
    keine globale Änderung fürs Zwischenspeichern braucht.
    """
    if page.cache is None:
        with open(os.path.join(HERE, "web", "index.html"), encoding="utf-8") as handle:
            page.cache = handle.read()
    # AP21 v2: <html lang> und <meta name="vibe-language"> erhalten die global
    # gespeicherte Sprache. Der Wert stammt aus der Whitelist LANGUAGES und ist
    # damit fuer HTML-Attribute ungefaehrlich (kein Benutzer-Freitext).
    language = language_data()["language"]
    return (page.cache.replace("__OPENCODE_URL__", vibe.OC_URL)
            .replace("__VIBE_LANG__", language))

page.cache = None

def static_asset(path):
    """Liest ausschließlich die freigegebenen statischen Dateien."""
    entry = STATIC_FILES.get(path)
    if entry is None:
        return None, None
    name, ctype = entry
    try:
        with open(os.path.join(HERE, name), "rb") as handle:
            return handle.read(), ctype
    except OSError:
        return None, None

def _startup_config():
    """Lädt ui.json und löst die Startpfade für den Serverprozess auf.

    ui.json (Port/Bind) wird hier geladen, nicht beim Import — der Import
    bleibt damit frei von Dateisystem-Nebenwirkungen. Priorität: Defaults
    < ui.json < Umgebung < CLI-Übergabe (vibe_paths.resolve). Eine defekte
    ui.json beendet den Start mit einer klaren Meldung.
    """
    try:
        data = vibe_ui_config.load(PATHS.state)
        resolved = vibe_paths.resolve(
            extra_config=vibe_ui_config.config_extra(PATHS.state) or None)
    except (vibe_ui_config.ConfigError, vibe_paths.ConfigError) as error:
        raise SystemExit("Pfadkonfiguration: " + str(error)) from error
    return data, resolved


if __name__ == "__main__":
    # Kein erneuter Container-Eintritt: vibe ui startet dieses Skript bereits
    # mit den aufgelösten Pfaden im richtigen Kontext.
    os.environ["VIBE_NO_CONTAINER"] = "1"
    # AP13: ui.json (Port/Bind) wird hier geladen, nicht beim Import — der
    # Import bleibt damit frei von Dateisystem-Nebenwirkungen. Priorität:
    # Defaults < ui.json < Umgebung < CLI-Übergabe (vibe_paths.resolve).
    UI_DATA, RESOLVED = _startup_config()
    PORT = RESOLVED.ui_port
    BIND = RESOLVED.ui_bind
    TOKFILE = os.path.join(RESOLVED.runtime, "web.token")
    INSTFILE = os.path.join(RESOLVED.runtime, "web.instance")
    TOKEN, INSTANCE = prepare_runtime()
    # Selber Testpin wie oben: SRV bleibt Modulattribut (tests/unit).
    SRV = ThreadingHTTPServer((BIND, PORT), H)  # pylint: disable=invalid-name
    # Keine daemon-Handler: server_close() wartet auf die Streams, die STOP
    # innerhalb einer Sekunde sehen. So endet der Prozess sauber statt mitten
    # in einer offenen Antwort abgeschnitten zu werden.
    SRV.daemon_threads = False
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(sig, request_stop)
    print(f"vibe-web läuft auf http://{BIND}:{PORT}/  (Token in {TOKFILE})", flush=True)
    try:
        SRV.serve_forever()
    finally:
        STOP.set()
        with contextlib.suppress(Exception):
            SRV.server_close()
    print("vibe-web beendet.", flush=True)
