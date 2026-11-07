#!/usr/bin/env python3
"""vibe-web — lokales Dashboard (nur Standardbibliothek). Start über: vibe ui"""
import os, sys, json, time, secrets, threading, contextlib, signal
import importlib.util, importlib.machinery
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import vibe_storage, vibe_paths
_loader = importlib.machinery.SourceFileLoader("vibe", os.path.join(HERE, "vibe"))
_spec = importlib.util.spec_from_loader("vibe", _loader)
vibe = importlib.util.module_from_spec(_spec); sys.modules["vibe"] = vibe; _loader.exec_module(vibe)
import vibe_mcp
import vibe_guide
import vibe_questions
import vibe_autonomous
import vibe_harness
import vibe_services

try:
    PATHS = vibe_paths.resolve()
except vibe_paths.ConfigError as error:
    raise SystemExit("Pfadkonfiguration: " + str(error))

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
SRV = None
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
    Verzeichnisse, keine Tokendateien, kein Serverprozess.
    """
    global TOKEN, INSTANCE
    try:
        vibe_paths.ensure(PATHS, "runtime")
    except vibe_paths.ConfigError as error:
        raise SystemExit("Pfadkonfiguration: " + str(error))
    TOKEN = secrets.token_urlsafe(24)
    INSTANCE = secrets.token_hex(8)
    write_private(INSTFILE, INSTANCE)
    write_private(TOKFILE, TOKEN)

def redact(text):
    """Entfernt das Token aus jeder nach außen gegebenen Meldung."""
    text = str(text)
    return text.replace(TOKEN, "[entfernt]") if TOKEN else text

def split_host(value):
    text = (value or "").strip().lower()
    if text.startswith("["):
        end = text.find("]")
        return text[1:end] if end >= 0 else ""
    if text.count(":") == 1:
        return text.split(":", 1)[0]
    return text

def host_allowed(value):
    return split_host(value) in LOOPBACK_HOSTS

def origin_allowed(value):
    """Origin muss auf diese Loopback-Instanz zeigen (Port inklusive)."""
    if not value:
        return True
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme != "http":
        return False
    if (parsed.hostname or "").lower() not in LOOPBACK_HOSTS:
        return False
    effective_port = port if port is not None else 80
    return effective_port == PORT

class RequestError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def known(n):
    if n not in vibe.projects(): raise AssertionError("Unbekanntes Projekt: " + n)
    return n

def known_scope(s):
    if s != "global": known(s)
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

def request_stop(signum=None, frame=None):
    """Signalhandler: keine Prozessabbrüche mitten in einer Antwort."""
    STOP.set()
    threading.Thread(
        target=shutdown_server, kwargs={"delay": 0}, daemon=True
    ).start()

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def log_request(self, code="-", size="-"):
        """Zugriffslog ohne Query-String: Tokens gelangen nicht in Logs."""
        try:
            path = urlparse(getattr(self, "path", "")).path
            sys.stderr.write(f"[vibe] {self.command} {path} -> {code}\n")
            sys.stderr.flush()
        except Exception:
            pass

    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else (json.dumps(body, ensure_ascii=False).encode() if ctype == "application/json" else body.encode())
        self.send_response(code); self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers(); self.wfile.write(b)

    def _error(self, code, slug, message):
        """Strukturierte Fehlerantwort; Meldungen werden vom Token bereinigt."""
        message = redact(message)
        self._send(code, {"ok": False, "error": {"code": slug, "message": message}, "message": message})

    def _authorized(self, allow_query=False):
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
        except ValueError:
            self.close_connection = True
            raise RequestError(400, "invalid_length", "Content-Length ist keine Zahl")
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
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RequestError(400, "invalid_json", "Ungültiges JSON")
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

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if not self._guard(False): return
        if u.path == "/": return self._send(200, page(), "text/html")
        if u.path.startswith("/static/"):
            data, ctype = static_asset(u.path)
            if data is None: return self._error(404, "not_found", "nicht gefunden")
            return self._send(200, data, ctype)
        if u.path == "/api/health": return self._health()
        if not self._authorized(allow_query=(u.path == "/api/stream")):
            return self._error(403, "unauthorized", "Token fehlt oder falsch")
        try:
            if u.path == "/api/projects": return self._send(200, [vibe_services.project_row(vibe, n) for n in vibe.projects()])
            if u.path == "/api/run-state":
                n = known(q["name"][0])
                return self._send(200, {"running": vibe.tmux_has(n), "pause_after": vibe.pause_after_active(n)})
            if u.path == "/api/project": return self._send(200, vibe_services.project_detail(vibe, PATHS, known(q["name"][0])))
            if u.path == "/api/roots": return self._send(200, vibe_services.roots_info(vibe))
            if u.path == "/api/agents": return self._send(200, vibe_services.agents_info(vibe))
            if u.path == "/api/project-agents": return self._send(200, vibe_services.project_agents_info(vibe, known(q["name"][0])))
            if u.path == "/api/costs":
                n = q.get("name", [""])[0]
                return self._send(200, vibe.costs_project(known(n)) if n else vibe.costs_overview())
            if u.path == "/api/agent":
                scope = known_scope(q["scope"][0]); snapshot = vibe.agent_snapshot(scope, q["name"][0])
                try: fields = vibe.agent_fields(scope, snapshot.text)
                except ValueError as error:
                    # Eine defekte Datei bleibt im Rohtexteditor bearbeitbar.
                    fields = {"invalid": str(error)}
                return self._send(200, {"text": snapshot.text, "digest": snapshot.digest,
                                        "fields": fields,
                                        "backups": list(reversed(vibe.agent_backups(scope, q["name"][0])))})
            if u.path == "/api/mcp": return self._send(200, {"servers": vibe_mcp.list_all(), "projects": vibe.projects()})
            if u.path == "/api/mcp_entry":
                scope = known_scope(q["scope"][0]); return self._send(200, vibe_mcp.get_entry(scope, q["name"][0]))
            if u.path == "/api/types": return self._send(200, vibe.types())
            if u.path == "/api/guide": return self._send(200, vibe_services.guide_info(vibe, known(q["name"][0])))
            if u.path == "/api/doctor": return self._send(200, [{"label": a, "ok": b, "hint": c} for a, b, c in vibe.doctor_checks()])
            if u.path == "/api/fritz": return self._send(200, vibe.fritz_status())
            if u.path == "/api/questions": return self._send(200, {"questions": vibe_questions.open_questions(PATHS.runtime)})
            if u.path == "/api/autonomous":
                n = q.get("name", [""])[0]
                if n: known(n)
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
            if u.path == "/api/stream": return self.stream(known(q["name"][0]), q.get("kind", ["run"])[0])
        except (AssertionError, ValueError) as e:
            return self._error(404, "not_found", str(e))
        except KeyError as e:
            return self._error(400, "invalid_request", "Parameter fehlt: " + str(e))
        except Exception as e:
            return self._error(500, "internal_error", f"{type(e).__name__}: {e}")
        self._error(404, "not_found", "nicht gefunden")
    def do_POST(self):
        u = urlparse(self.path)
        if not self._guard(True): return
        if not self._authorized(): return self._error(403, "unauthorized", "Token fehlt oder falsch")
        try:
            body = self._read_json()
        except RequestError as e:
            return self._error(e.status, e.code, e.message)
        try:
            name = body.get("name", "")
            if u.path in ("/api/run", "/api/stop", "/api/verify", "/api/feedback", "/api/ticket", "/api/init", "/api/rights", "/api/pause", "/api/sandbox", "/api/guide", "/api/costs", "/api/autonomous"): known(name)
            extra = {}
            if u.path == "/api/run": ok, msg = vibe_services.capture(vibe.cmd_run, name, body.get("agent") or None)
            elif u.path == "/api/stop": ok, msg = vibe_services.capture(vibe.cmd_stop, name, body.get("run_id") or None)
            elif u.path == "/api/verify": ok, msg = vibe_services.verify_bg(vibe, name, "full" if body.get("mode") == "full" else "quick")
            elif u.path == "/api/init": ok, msg = vibe_services.capture(vibe.cmd_init, name, body.get("type") or None)
            elif u.path == "/api/feedback":
                act = body.get("action") or "add"
                try:
                    if act == "add":
                        t = (body.get("title") or "").strip(); assert t, "Titel fehlt"
                        kind = body.get("kind") or "feedback"
                        if kind == "bug":
                            num = vibe.add_bug(name, t, body.get("description", "")); ok, msg = True, f"B{num} eingetragen"
                        else:
                            num = vibe.add_feedback(name, t, body.get("description", "")); ok, msg = True, f"F{num} eingetragen"
                    elif act == "update":
                        fid = (body.get("id") or "").strip(); assert fid, "Feedback-ID fehlt"
                        vibe.feedback_update(name, fid, body.get("title"), body.get("description", "")); ok, msg = True, f"{fid} gespeichert"
                    elif act == "delete":
                        fid = (body.get("id") or "").strip(); assert fid, "Feedback-ID fehlt"
                        vibe.feedback_delete(name, fid); ok, msg = True, f"{fid} gelöscht"
                    else: ok, msg = False, "Unbekannte Aktion"
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/ticket":
                act = body.get("action") or "add"
                try:
                    if act == "add":
                        tid = (body.get("id") or "").strip(); assert tid, "ID fehlt"
                        vibe.add_ticket(name, tid, body.get("title"), body.get("description", "")); ok, msg = True, f"{tid} angelegt"
                    elif act == "update":
                        tid = (body.get("id") or "").strip(); assert tid, "ID fehlt"
                        vibe.ticket_update(name, tid, body.get("title"), body.get("description", "")); ok, msg = True, f"{tid} gespeichert"
                    elif act == "delete":
                        tid = (body.get("id") or "").strip(); assert tid, "ID fehlt"
                        vibe.ticket_delete(name, tid); ok, msg = True, f"{tid} gelöscht"
                    else: ok, msg = False, "Unbekannte Aktion"
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/new": ok, msg = vibe_services.capture(vibe.cmd_new, name, body.get("type", "generic"), body.get("tpl") or None)
            elif u.path == "/api/roots":
                act = body.get("action"); path = body.get("path", "")
                try:
                    if act == "add": p = vibe.root_add(path)
                    elif act == "remove": vibe.root_remove(path); p = path
                    else: vibe._pm.clear(); p = ""
                    pm = vibe.project_map(); found = [k for k, v in pm.items() if p and os.path.dirname(v) == os.path.abspath(os.path.expanduser(p))]
                    ok, msg = True, (f"{len(found)} Projekt(e) in {p}: {', '.join(found) or '-'}" if act == "add" else "OK")
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/rights":
                act = body.get("action"); ok, msg, changed = True, "", None
                try:
                    if act == "add":
                        dirs = vibe.write_dirs_add(name, body.get("path", "")); msg = "Verzeichnis hinzugefügt"
                    elif act in ("remove", "rm"):
                        dirs = vibe.write_dirs_remove(name, body.get("path", "")); msg = "Verzeichnis entfernt"
                    elif act == "reset":
                        dirs = vibe.write_dirs_reset(name); msg = "Standardverzeichnisse wiederhergestellt"
                    elif act == "apply":
                        dirs = vibe.write_dirs(name); changed = vibe.apply_write_dirs_to_project(name)
                        msg = ("Schreibrechte auf " + str(len(changed)) + " Projektagent(en) angewendet: " + ", ".join(changed)) if changed else "Nichts geändert – keine Projektagenten mit Schreibrecht vorhanden"
                    else:
                        ok, msg, dirs = False, "Unbekannte Aktion", None
                    if dirs is not None:
                        extra["write_dirs"] = dirs; extra["custom"] = vibe.write_dirs_custom(name)
                    if changed is not None: extra["changed"] = changed
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/sandbox":
                act = body.get("action"); ok, msg, status = True, "", None
                try:
                    if act == "on":
                        status = vibe.sandbox_set(name, True); msg = "Sandbox eingeschaltet"
                    elif act == "off":
                        status = vibe.sandbox_set(name, False); msg = "Sandbox ausgeschaltet"
                    elif act == "tools":
                        status = vibe.sandbox_tools(name, body.get("tools", "")); msg = "Build-Werkzeuge gespeichert"
                    elif act == "check":
                        checked = vibe.sandbox_check(name); ok, msg = checked["ok"], checked["message"]
                        status = vibe.sandbox_status(name); extra["check"] = checked
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                    if status is not None: extra["sandbox"] = status
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/pause":
                act = body.get("action") or "on"; ok, msg = True, ""
                try:
                    if act in ("on", "an", "request"):
                        vibe.pause_after_request(name); msg = "Pause nach dem aktuellen Arbeitspaket angefordert"
                    elif act in ("off", "aus", "cancel"):
                        released = vibe.pause_after_cancel(name)
                        msg = "Pause-Anforderung aufgehoben" if released else "Keine Pause angefordert"
                    else:
                        ok, msg = False, "Unbekannte Aktion"
                    extra["pause_after"] = vibe.pause_after_active(name)
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/costs":
                act = body.get("action") or "prices"; ok, msg = True, ""
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
                act = body.get("action"); ok, msg = True, ""
                try:
                    if act in ("automation", "on", "off", "set"):
                        enabled = (act == "on") if act in ("on", "off") else body.get("enabled")
                        if not isinstance(enabled, bool):
                            raise ValueError("enabled muss true oder false sein")
                        vibe.fritz_automation_set(enabled)
                        msg = "Fritzbox-Automatik " + ("an" if enabled else "aus")
                    elif act == "reconnect":
                        result = vibe.fritz_reconnect(); extra["result"] = result
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
                        ok, msg = True, result["message"]; extra["guide"] = result
                    elif act == "agent":
                        started = vibe_guide.start_agent(path, body.get("step", ""), name=name, note=body.get("note", ""), log_dir=vibe.LOGS)
                        ok, msg = True, "Agentenauftrag gestartet. Der Entwurf erscheint nach dem Lauf unter .vibe/guide/."; extra["agent"] = started
                    elif act == "draft_apply":
                        result = vibe_guide.draft_apply(path, body.get("step", ""), name=name, templates_dir=vibe.TPL)
                        ok, msg = True, "Entwurf übernommen. " + result["message"]; extra["guide"] = result
                    elif act == "draft_discard":
                        vibe_guide.draft_discard(path, body.get("step", ""))
                        ok, msg = True, "Entwurf verworfen."
                    else: ok, msg = False, "Unbekannte Aktion"
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
                act = body.get("action"); scope = known_scope(body.get("scope", "global")); an = body.get("name", "")
                try:
                    if act == "save":
                        # Die strukturierten Eingaben sind auch ohne Klick auf
                        # „In Rohtext übernehmen“ wirksam. Die Oberfläche sendet
                        # nur geänderte Felder, damit freie Rohtextänderungen an
                        # anderen Stellen erhalten bleiben.
                        text = body.get("text", "")
                        if body.get("values") is not None:
                            text = vibe.agent_render_fields(scope, text, body.get("values"))
                        warn = vibe.agent_write(scope, an, text, create=bool(body.get("create")), expected=body.get("expected"))
                        snapshot = vibe.agent_snapshot(scope, an)
                        extra["text"] = snapshot.text; extra["digest"] = snapshot.digest
                        ok, msg = True, "Gespeichert" + (" – Hinweis: " + " ".join(warn) if warn else "")
                    elif act == "delete": vibe.agent_delete(scope, an); ok, msg = True, "Gelöscht (Sicherung in agent-backups)"
                    elif act == "copy": vibe.agent_copy(scope, an, known_scope(body.get("to", "global"))); ok, msg = True, "Kopiert"
                    elif act == "render":
                        # Vorschau: strukturierte Eingaben in den Rohtext übernehmen,
                        # ohne die Datei zu verändern.
                        extra["text"] = vibe.agent_render_fields(scope, body.get("text", ""), body.get("values"))
                        ok, msg = True, "Eingaben in den Rohtext übernommen – noch nicht gespeichert"
                    elif act == "restore":
                        vibe.agent_restore(scope, an, body.get("backup") or None)
                        snapshot = vibe.agent_snapshot(scope, an)
                        extra["text"] = snapshot.text; extra["digest"] = snapshot.digest
                        ok, msg = True, "Sicherung wiederhergestellt"
                    else: ok, msg = False, "Unbekannte Aktion"
                except vibe_storage.ConcurrentChangeError as e:
                    return self._error(409, "conflict", str(e))
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/mcp":
                act = body.get("action"); scope = known_scope(body.get("scope", "global")); entry = body.get("entry")
                try:
                    if act == "save": p = vibe_mcp.save(scope, name, entry, body.get("old_name") or None, bool(body.get("create")), expected=body.get("expected")); ok, msg = True, "Gespeichert in " + p + " (Sicherung in config-backups). opencode liest die Konfiguration beim nächsten Start."
                    elif act == "delete": vibe_mcp.delete(scope, name); ok, msg = True, "Gelöscht (Sicherung in config-backups)"
                    elif act == "toggle": en = vibe_mcp.toggle(scope, name); ok, msg = True, "aktiviert" if en else "deaktiviert"
                    elif act == "test": extra["result"] = vibe_mcp.test(scope, name or None, entry); ok, msg = True, "Test beendet"
                    else: ok, msg = False, "Unbekannte Aktion"
                except vibe_storage.ConcurrentChangeError as e:
                    return self._error(409, "conflict", str(e))
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/profiles":
                act = body.get("action")
                try:
                    if act == "save":
                        d = vibe.profiles_load(); data = body.get("data") or {}
                        for k in ("rollen", "profile"):
                            if isinstance(data.get(k), dict): d[k] = data[k]
                        vibe.profiles_save(d); ok, msg = True, "Profile gespeichert"
                    elif act == "use":
                        done, skipped = vibe.profile_apply(body.get("profile", "")); ok, msg = True, "Angewendet: " + "; ".join(done) + (" | übersprungen: " + "; ".join(skipped) if skipped else "")
                    else: ok, msg = False, "Unbekannte Aktion"
                except ValueError as e:
                    ok, msg = False, str(e)
            elif u.path == "/api/model": ok, msg = vibe_services.capture(vibe.cmd_model, body.get("agent", ""), body.get("model", ""), body.get("scope", "global"))
            elif u.path == "/api/server": ok, msg = vibe_services.capture(vibe.cmd_server, "start" if body.get("action") == "start" else "stop")
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
                threading.Thread(target=shutdown_server, daemon=True).start(); return
            else: return self._error(404, "not_found", "nicht gefunden")
            message = redact(msg)
            out = {"ok": ok, "message": message}
            if not ok: out["error"] = {"code": "rejected", "message": message}
            out.update(extra)
            self._send(200 if ok else 400, out)
        except AssertionError as e:
            self._error(400, "invalid_request", str(e))
        except ValueError as e:
            self._error(400, "invalid_request", str(e))
        except Exception as e:
            self._error(500, "internal_error", f"{type(e).__name__}: {e}")
    def stream(self, name, kind):
        path = vibe.logpath(name, "verify" if kind == "verify" else "run")
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-store"); self.end_headers()
        def send(lines):
            self.wfile.write(("data: " + json.dumps(lines, ensure_ascii=False) + "\n\n").encode()); self.wfile.flush()
        try:
            pos = os.path.getsize(path) if os.path.exists(path) else 0
            send(vibe_services.tail(path, 80) or ["(noch keine Ausgabe)"])
            while not STOP.is_set():
                if STOP.wait(1):
                    break
                if os.path.exists(path):
                    size = os.path.getsize(path)
                    if size < pos: pos = 0
                    if size > pos:
                        with open(path, "rb") as f:
                            f.seek(pos); chunk = f.read(); pos = size
                        send(ANSI.sub("", chunk.decode("utf-8", "replace")).splitlines()); continue
                self.wfile.write(b": ping\n\n"); self.wfile.flush()
            if STOP.is_set():
                send(["Dashboard wird beendet."])
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.close_connection = True

STATIC_FILES = {
    "/static/styles.css": ("web/styles.css", "text/css"),
    "/static/app.js": ("web/app.js", "application/javascript"),
}
_PAGE = None

def page():
    """Liefert die Oberfläche aus der eigenen HTML-Datei.

    Der opencode-Link kommt aus einem Meta-Feld; damit bleibt das getrennte
    JavaScript unverändert und ohne serverseitige Textersetzung.
    """
    global _PAGE
    if _PAGE is None:
        with open(os.path.join(HERE, "web", "index.html"), encoding="utf-8") as handle:
            _PAGE = handle.read()
    return _PAGE.replace("__OPENCODE_URL__", vibe.OC_URL)

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

if __name__ == "__main__":
    # Kein erneuter Container-Eintritt: vibe ui startet dieses Skript bereits
    # mit den aufgelösten Pfaden im richtigen Kontext.
    os.environ["VIBE_NO_CONTAINER"] = "1"
    prepare_runtime()
    SRV = ThreadingHTTPServer((BIND, PORT), H)
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
