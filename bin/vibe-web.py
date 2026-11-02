#!/usr/bin/env python3
"""vibe-web — lokales Dashboard (nur Standardbibliothek). Start über: vibe ui"""
import os, sys, json, re, time, secrets, threading, subprocess, io, contextlib, signal
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
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
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


def call(fn, *a, **k):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            fn(*a, **k)
        return True, ANSI.sub("", buf.getvalue()).strip()
    except SystemExit as e:
        return False, (str(e.code) if e.code not in (None, 0) else ANSI.sub("", buf.getvalue()).strip())
    except Exception as e:
        return False, str(e)

def known(n):
    if n not in vibe.projects(): raise AssertionError("Unbekanntes Projekt: " + n)
    return n

def known_scope(s):
    if s != "global": known(s)
    return s

def tail(path, n=120):
    if not os.path.exists(path): return []
    with open(path, "rb") as f:
        data = f.read()[-60000:]
    return ANSI.sub("", data.decode("utf-8", "replace")).splitlines()[-n:]

def project_row(n):
    br, dirty, last = vibe.git_info(n); items = vibe.open_items(n)
    state = vibe.run_state(n)
    return {"name": n, "type": vibe.ptype(n), "branch": br, "dirty": dirty, "last": last, "open": len(items), "path": vibe.ppath(n),
            "running": state["running"], "run": state, "init": vibe.is_init(n), "log": os.path.exists(vibe.logpath(n)),
            "pause_after": vibe.pause_after_active(n)}

def project_detail(n):
    d = project_row(n)
    d["items"] = [{"id": i, "title": t, "state": s} for i, t, s in vibe.open_items(n)]
    d["feedback"] = vibe.feedback_items(n)
    d["tickets"] = vibe.ticket_items(n)
    d["tail"] = tail(vibe.logpath(n), 80)
    try: d["verify_cmd"] = bool(vibe.verify_command(n, "quick"))
    except ValueError: d["verify_cmd"] = False
    d["env"] = vibe.penv(n)
    try:
        d["write_dirs"] = vibe.write_dirs(n)
        d["write_dirs_error"] = None
    except ValueError as e:
        d["write_dirs"] = []
        d["write_dirs_error"] = str(e)
    d["write_dirs_default"] = vibe.write_dirs_default(n)
    d["write_dirs_custom"] = vibe.write_dirs_custom(n)
    try:
        d["sandbox"] = vibe.sandbox_status(n)
    except Exception as e:
        d["sandbox"] = {"enabled": False, "tools": [], "write_dirs": [], "tool_caches": [],
                        "missing_tools": [], "bwrap": "", "state_dir": "", "error": str(e)}
    try:
        d["autonomous"] = vibe_autonomous.is_enabled(PATHS.runtime, n)
    except ValueError:
        d["autonomous"] = False
    return d

def guide_info(n):
    """Zustand des Projektassistenten inklusive laufendem Agentenauftrag."""
    path = vibe.ppath(n)
    data = vibe_guide.state(path, name=n)
    status = vibe_guide.agent_status(path, name=n, log_dir=vibe.LOGS)
    data["agent"] = {"session": status["session"], "running": status["running"],
                     "agent": status["agent"], "log": status["log"],
                     "log_tail": status["log_tail"]}
    return data

def roots_info():
    pm = vibe.project_map(); out = []
    for r in vibe.roots():
        out.append({"path": r, "fixed": r == vibe.VIBE, "projects": [k for k, v in pm.items() if os.path.dirname(v) == r]})
    return out

def project_agents_info(n):
    """Agentenauswahl eines Projekts samt Modellen für die Oberfläche."""
    info = vibe.models_info()
    data = {"project": n, "agents": [], "error": None,
            "models": [], "info": {m["id"]: m for m in info.get("models", [])},
            "stand": info.get("stand", ""), "hinweis": info.get("hinweis", "")}
    try:
        data["agents"] = vibe.project_agent_rows(n)
    except ValueError as error:
        data["error"] = str(error)
    try:
        data["models"] = vibe.models_list()
    except Exception:
        data["models"] = []
    return data

def agents_info():
    info = vibe.models_info()
    ps = vibe.projects()
    write_dirs, write_dirs_errors = {}, {}
    for p in ps:
        try:
            write_dirs[p] = vibe.write_dirs(p)
        except ValueError as e:
            write_dirs[p] = []
            write_dirs_errors[p] = str(e)
    return {"agents": vibe.agents_all(), "projects": ps, "models": vibe.models_list(),
            "info": {m["id"]: m for m in info.get("models", [])}, "stand": info.get("stand", ""), "hinweis": info.get("hinweis", ""),
            "katalog": {"schema": info.get("schema"), "version": info.get("version", ""),
                        "legacy": info.get("legacy", False), "findings": info.get("findings", []),
                        "quellen": info.get("quellen", []), "nicht_uebernommen": info.get("nicht_uebernommen", [])},
            "perms": vibe.PERM_LABELS, "perms_project": vibe.PERM_LABELS_PROJECT,
            "write_dirs": write_dirs, "write_dirs_errors": write_dirs_errors, "profiles": vibe.profiles_load()}

def verify_bg(n, mode):
    try:
        argv = vibe.verify_argv(n, mode)
    except ValueError as error:
        return False, str(error)
    if not argv: return False, "Keine Prüfbefehle in .vibe/project.env"
    lg = open(vibe.logpath(n, "verify"), "w")
    lg.write(f"$ {vibe.verify_command(n, mode)}\n"); lg.flush()
    subprocess.Popen(argv, cwd=vibe.ppath(n), stdout=lg, stderr=subprocess.STDOUT)
    return True, "Prüfung gestartet"

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
        self._send(200, {
            "ok": True,
            "app": "vibe",
            "api": 1,
            "instance": INSTANCE,
            "bind": BIND,
            "port": PORT,
            "pid": os.getpid(),
            "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(STARTED)),
        })

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if not self._guard(False): return
        if u.path == "/": return self._send(200, page(), "text/html")
        if u.path == "/api/health": return self._health()
        if not self._authorized(allow_query=(u.path == "/api/stream")):
            return self._error(403, "unauthorized", "Token fehlt oder falsch")
        try:
            if u.path == "/api/projects": return self._send(200, [project_row(n) for n in vibe.projects()])
            if u.path == "/api/run-state":
                n = known(q["name"][0])
                return self._send(200, {"running": vibe.tmux_has(n), "pause_after": vibe.pause_after_active(n)})
            if u.path == "/api/project": return self._send(200, project_detail(known(q["name"][0])))
            if u.path == "/api/roots": return self._send(200, roots_info())
            if u.path == "/api/agents": return self._send(200, agents_info())
            if u.path == "/api/project-agents": return self._send(200, project_agents_info(known(q["name"][0])))
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
            if u.path == "/api/guide": return self._send(200, guide_info(known(q["name"][0])))
            if u.path == "/api/doctor": return self._send(200, [{"label": a, "ok": b, "hint": c} for a, b, c in vibe.doctor_checks()])
            if u.path == "/api/fritz": return self._send(200, vibe.fritz_status())
            if u.path == "/api/questions": return self._send(200, {"questions": vibe_questions.open_questions(PATHS.runtime)})
            if u.path == "/api/autonomous":
                n = q.get("name", [""])[0]
                if n: known(n)
                return self._send(200, vibe_autonomous.status(PATHS.runtime, n))
            if u.path == "/api/server": h = vibe.server_health(); return self._send(200, {"up": bool(h), "url": vibe.OC_URL, "info": h})
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
            if u.path == "/api/run": ok, msg = call(vibe.cmd_run, name, body.get("agent") or None)
            elif u.path == "/api/stop": ok, msg = call(vibe.cmd_stop, name, body.get("run_id") or None)
            elif u.path == "/api/verify": ok, msg = verify_bg(name, "full" if body.get("mode") == "full" else "quick")
            elif u.path == "/api/init": ok, msg = call(vibe.cmd_init, name, body.get("type") or None)
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
            elif u.path == "/api/new": ok, msg = call(vibe.cmd_new, name, body.get("type", "generic"), body.get("tpl") or None)
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
                extra["project_agents"] = project_agents_info(project)
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
            elif u.path == "/api/model": ok, msg = call(vibe.cmd_model, body.get("agent", ""), body.get("model", ""), body.get("scope", "global"))
            elif u.path == "/api/server": ok, msg = call(vibe.cmd_server, "start" if body.get("action") == "start" else "stop")
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
            send(tail(path, 80) or ["(noch keine Ausgabe)"])
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

PAGE = r"""<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>vibe</title><style>
:root{--bg:#14161a;--card:#1d2026;--line:#2c313a;--tx:#e6e8eb;--mut:#8b93a1;--ac:#5aa9ff;--ok:#4cc38a;--warn:#f2b84b;--bad:#f06a6a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.4 system-ui,sans-serif}
header{display:flex;gap:16px;align-items:center;padding:10px 18px;border-bottom:1px solid var(--line);flex-wrap:wrap}
header h1{font-size:16px;margin:0}nav button{background:none;border:0;color:var(--mut);padding:8px 12px;cursor:pointer;font-size:14px}
nav button.on{color:var(--tx);border-bottom:2px solid var(--ac)}main{padding:18px;max-width:1300px;margin:auto}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:8px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--mut);font-weight:500}
td.num{text-align:right;font-variant-numeric:tabular-nums}
tr.row{cursor:pointer}tr.row:hover{background:#1a1d23}.pill{padding:2px 8px;border-radius:10px;font-size:12px;background:#2a2f38;white-space:nowrap}
.run{background:#17382a;color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.ok{color:var(--ok)}.mut{color:var(--mut)}
.pill.ok{background:#17382a}.pill.warn{background:#3a3016}.pill.bad{background:#3d1d1d}.pill.mut{background:#2a2f38}
button.b{background:#2a2f38;color:var(--tx);border:1px solid var(--line);padding:6px 12px;border-radius:6px;cursor:pointer}button.b:hover{border-color:var(--ac)}
button.p{background:var(--ac);color:#06121f;border-color:var(--ac)}button.d{border-color:var(--bad);color:var(--bad)}button.quit{background:#5a1d1d;border-color:var(--bad);color:#fff;font-weight:600}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px;margin-bottom:14px}
pre#log{background:#0d0f12;border:1px solid var(--line);border-radius:6px;padding:10px;height:320px;overflow:auto;white-space:pre-wrap;font:12px/1.4 ui-monospace,monospace;margin:0}
input,textarea,select{background:#0d0f12;color:var(--tx);border:1px solid var(--line);border-radius:6px;padding:6px;width:100%}label{display:block;margin:8px 0 2px;color:var(--mut);font-size:12px}
input[type=checkbox]{width:auto}textarea.raw{font:12px/1.4 ui-monospace,monospace;min-height:360px}details summary{cursor:pointer;font-weight:600}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.bar{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0;align-items:center}a{color:var(--ac)}
.err{border-color:var(--bad)}.detail td{background:#181b20}ul.l{margin:4px 0 8px 18px;padding:0}.sep{width:1px;height:22px;background:var(--line)}@media(max-width:900px){.grid,.grid3{grid-template-columns:1fr}}
.logcard{display:flex;flex-direction:column;min-height:0}.logcard.full{position:fixed;inset:8px;z-index:100;margin:0;box-shadow:0 0 0 1px var(--line),0 12px 40px #000a}
.logcard.full pre#log{flex:1 1 auto;height:auto;min-height:0}body.logfull{overflow:hidden}
.fbentry{border-top:1px solid var(--line);padding:8px 0}.fbentry:first-child{border-top:0}.fbdesc{white-space:pre-wrap;margin:2px 0 6px}.fbentry .bar{margin:4px 0 0}
.toasts{position:fixed;right:16px;bottom:16px;z-index:200;display:flex;flex-direction:column;gap:8px;width:min(460px,calc(100vw - 32px))}
.toast{display:flex;gap:10px;align-items:flex-start;background:#232830;border:1px solid var(--line);border-left:3px solid var(--ac);border-radius:8px;padding:10px 12px;box-shadow:0 8px 24px #0008}
.toast .toasttext{white-space:pre-wrap;overflow-wrap:anywhere}.toast .x{padding:2px 8px;margin-left:auto;cursor:pointer;flex:0 0 auto}
/* Rückfragen des Agenten (F16) */
.qwrap{max-width:1300px;margin:0 auto;padding:14px 18px 0}
.qwrap[hidden]{display:none}
.qcard{background:var(--card);border:1px solid var(--warn);border-left:4px solid var(--warn);border-radius:8px;padding:12px 14px;margin-bottom:10px}
.qhead{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:4px}
.qtext{font-size:15px;font-weight:600;margin:0 0 4px;white-space:pre-wrap;overflow-wrap:anywhere}
.qopts{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 0}
.qfree{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap;align-items:center}
.qfree input{flex:1 1 240px;width:auto;min-width:0}
.confirm{display:inline-flex;gap:8px;align-items:center;flex-wrap:wrap;background:#2a2416;border:1px solid var(--warn);border-radius:6px;padding:4px 8px}
/* Projektdetail: feste Kopfleiste, Register und Kennzahlen (F13) */
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);margin:0 0 16px;overflow-x:auto;scrollbar-width:thin}
.tabs [role=tab]{background:none;border:0;border-bottom:2px solid transparent;color:var(--mut);padding:10px 14px;cursor:pointer;font-size:14px;white-space:nowrap}
.tabs [role=tab]:hover{color:var(--tx)}
.tabs [role=tab][aria-selected=true]{color:var(--tx);border-bottom-color:var(--ac)}
.detailbar{position:sticky;top:0;z-index:60;background:var(--bg);border-bottom:1px solid var(--line);margin:0 0 14px;padding:10px 0;align-items:center}
.dhead{display:flex;gap:10px;align-items:center;flex-wrap:wrap;min-width:0}
.dhead h2{font-size:18px}
.dmeta{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:48ch}
.dactions{margin:0 0 0 auto;flex-wrap:nowrap}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px;min-width:0}
.tile .k{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.05em}
.tile .v{font-size:20px;font-weight:600;margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tile .v.small{font-size:13px;font-weight:500}
.item{padding:4px 0}.item+.item{border-top:1px solid var(--line)}
.warnbox{border-color:var(--warn)}
.factrow{display:flex;gap:12px;justify-content:space-between;padding:5px 0;border-top:1px solid var(--line);font-size:13px}
.factrow:first-of-type{border-top:0}.factrow span:last-child{text-align:right;overflow-wrap:anywhere}
button:focus-visible,a:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible,[role=tab]:focus-visible{outline:2px solid var(--ac);outline-offset:2px}
[role=tabpanel][hidden]{display:none}
@media(max-width:640px){.detailbar{position:static}.dactions{margin-left:0;flex-wrap:wrap}.dmeta{display:none}}
</style></head><body>
<header><h1>vibe</h1><nav id="nav"></nav><span id="srv" style="margin-left:auto;display:flex;gap:8px;align-items:center"></span></header><div id="questions" class="qwrap" role="region" aria-label="Rückfragen" aria-live="polite" hidden></div><main id="main"></main>
<script>
const T=(()=>{const m=location.hash.match(/t=([^&]+)/);if(m){sessionStorage.t=m[1];history.replaceState(null,'',location.pathname)}return sessionStorage.t||''})();
function errText(j,status){const e=j&&j.error;return (e&&(e.message||e))||(j&&j.message)||('HTTP '+status)}
async function api(p,body){const o=body?{method:'POST',headers:{'X-Token':T,'Content-Type':'application/json'},body:JSON.stringify(body)}:{headers:{'X-Token':T}};
 const r=await fetch(p,o);const j=await r.json().catch(()=>({}));if(!r.ok&&!body)throw new Error(errText(j,r.status));return j}
function el(t,a={},...c){const e=document.createElement(t);for(const[k,v]of Object.entries(a)){if(k==='on')for(const[ev,f]of Object.entries(v))e.addEventListener(ev,f);else if(k==='class')e.className=v;else if(k==='value')e.value=v;else e.setAttribute(k,v)}
 for(const x of c.flat())if(x!==null&&x!==undefined&&x!==false)e.append(x.nodeType?x:document.createTextNode(String(x)));return e}
const main=document.getElementById('main'),nav=document.getElementById('nav'),srvbox=document.getElementById('srv');let tab='projects',es=null,timer=null,LOG=null;
function showErr(e){main.replaceChildren(el('div',{class:'card err'},el('b',{class:'bad'},'Fehler: '),String(e&&e.message||e)),el('button',{class:'b',on:{click:()=>setTab('projects')}},'← zur Projektliste'))}
function setTab(t){exitLogFull();LOG=null;DTAB='arbeit';tab=t;if(es){es.close();es=null}clearInterval(timer);[...nav.children].forEach(b=>b.classList.toggle('on',b.dataset.t===t));Promise.resolve(({projects,agents,mcp,env,costs}[t])()).catch(showErr);header()}
[['projects','Projekte'],['agents','Agenten & Modelle'],['mcp','MCP-Tools'],['env','Umgebung'],['costs','Kosten']].forEach(([k,l])=>nav.append(el('button',{'data-t':k,on:{click:()=>setTab(k)}},l)));
const toastBox=el('div',{id:'toasts',class:'toasts',role:'status','aria-live':'polite','aria-atomic':'false'});
document.body.append(toastBox);
function toast(m){const t=el('div',{class:'toast'},el('span',{class:'toasttext'},String(m)),el('button',{class:'b x',type:'button','aria-label':'Meldung schließen',title:'Meldung schließen',on:{click:()=>t.remove()}},'×'));
 toastBox.prepend(t);while(toastBox.children.length>4)toastBox.lastElementChild.remove();setTimeout(()=>t.remove(),8000)}
/* Rückfragen (F16): Der Agent stellt eine Frage, das Dashboard zeigt sie mit
   den angebotenen Möglichkeiten und schreibt die Antwort zurück. */
const qbox=document.getElementById('questions'),qBaseTitle=document.title;
let qSeen=new Set(),qSig=null;
function questionCard(q){
 const send=body=>answerQuestion(q.id,body);
 const opts=(q.options||[]).map((text,i)=>el('button',{class:'b'+(i===0?' p':''),type:'button','data-option':String(i),on:{click:()=>send({option:i})}},text));
 let free=null;
 if(q.free_text!==false){
  const inp=el('input',{type:'text','aria-label':'Eigene Antwort zu '+q.id,placeholder:'Eigene Antwort …',maxlength:'4000'});
  const go=()=>{const text=inp.value.trim();if(!text){inp.focus();return}send({text})};
  inp.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();go()}});
  free=el('div',{class:'qfree'},inp,el('button',{class:'b p',type:'button',on:{click:go}},'Antwort senden'));
 }
 const auto=q.project?el('button',{class:'b',type:'button',title:'Der Agent entscheidet ohne Antwort selbst und dokumentiert die Entscheidung',on:{click:()=>setAutonomous(q.project)}},'Autonom entscheiden'):null;
 return el('section',{class:'qcard','data-question':q.id,'data-id':q.id},el('div',{class:'qhead'},el('span',{class:'pill warn'},'Rückfrage'),q.project?el('span',{class:'mut'},q.project):null,q.agent?el('span',{class:'mut'},'Agent: '+q.agent):null),el('p',{class:'qtext'},q.text),opts.length?el('div',{class:'qopts'},...opts):null,free,auto?el('div',{class:'qopts'},auto):null);
}
function showQuestions(list){
 const fresh=list.filter(q=>!qSeen.has(q.id));qSeen=new Set(list.map(q=>q.id));
 const sig=JSON.stringify(list.map(q=>[q.id,q.project,q.agent,q.text,q.options,q.free_text]));
 if(sig!==qSig){qSig=sig;qbox.replaceChildren(...list.map(questionCard));qbox.hidden=!list.length}
 document.title=list.length?'('+list.length+') '+qBaseTitle:qBaseTitle;
 if(fresh.length)toast('Neue Rückfrage'+(fresh[0].project?' ('+fresh[0].project+')':'')+': '+fresh[0].text);
}
async function answerQuestion(id,body){
 try{const r=await api('/api/questions',Object.assign({action:'answer',id},body));
  if(r.ok){toast(r.message);showQuestions(r.questions||[])}else toast(r.message||'Antwort abgelehnt')}catch(e){toast('Antwort nicht gesendet: '+String(e&&e.message||e))}
}
async function setAutonomous(name){
 try{const r=await api('/api/autonomous',{name,action:'on'});toast(r.message);
  if(r.ok)showQuestions((await api('/api/questions')).questions||[])}catch(e){toast('Autonomer Modus nicht geändert: '+String(e&&e.message||e))}
}
async function pollQuestions(){try{showQuestions((await api('/api/questions')).questions||[])}catch(e){}}
pollQuestions();setInterval(pollQuestions,3000);
function askInline(btn,q,okLabel,run){if(!btn.isConnected)return;
 const bar=btn.parentNode;if(bar&&bar.querySelector('.confirm'))return;
 const back=()=>{group.remove();btn.hidden=false;if(btn.isConnected)btn.focus()};
 const yes=el('button',{class:'b '+(btn.classList.contains('d')?'d':'p'),type:'button',on:{click:async()=>{yes.disabled=true;no.disabled=true;try{await run()}catch(e){showErr(e)}finally{back()}}}},okLabel);
 const no=el('button',{class:'b',type:'button',on:{click:back}},'Abbrechen');
 const group=el('span',{class:'confirm',role:'group','aria-label':q},el('span',{class:'mut'},q),yes,no);
 group.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();back()}});
 btn.hidden=true;btn.after(group);yes.focus()}
function setLogFull(on){if(!LOG)return;LOG.card.classList.toggle('full',on);document.body.classList.toggle('logfull',on);LOG.button.textContent=on?'Verkleinern':'Vergrößern';if(on)LOG.pre.style.height='auto';else LOG.fit()}
function exitLogFull(){if(LOG&&LOG.card.classList.contains('full'))setLogFull(false)}
window.addEventListener('keydown',e=>{if(e.key==='Escape')exitLogFull()});
window.addEventListener('resize',()=>{if(LOG)LOG.fit()});
const GOOD=['sehr schnell','schnell','gering','geeignet','gut','ja'],MID=['mittel','bedingt','unklar'],BAD=['langsam','hoch','eingeschränkt','nicht empfohlen','nein'];
function badge(v){v=v||'?';return el('span',{class:'pill '+(GOOD.includes(v)?'ok':MID.includes(v)?'warn':BAD.includes(v)?'bad':'mut')},v)}
async function header(){try{const s=await api('/api/server');
 const quit=el('button',{class:'b quit',title:'Beendet diese App (das Dashboard), nicht opencode',on:{click:()=>askInline(quit,'Dashboard (diese App) beenden? Laufende Agentenläufe in tmux laufen weiter.','Ja, beenden',async()=>{await api('/api/shutdown',{});
   main.replaceChildren(el('div',{class:'card'},'Dashboard beendet. Neu starten im Terminal: vibe ui'));srvbox.replaceChildren()})}},'Dashboard beenden');
 srvbox.replaceChildren(el('span',{class:s.up?'ok':'mut'},'opencode-Server: '+(s.up?'an':'aus')),
  el('button',{class:'b',title:'Startet/stoppt nur den gemeinsamen opencode-Server (Weboberfläche), nicht dieses Dashboard',on:{click:async()=>{toast((await api('/api/server',{action:s.up?'stop':'start'})).message);header()}}},s.up?'opencode stoppen':'opencode starten'),el('span',{class:'sep'}),quit)}catch(e){}}
async function rootsCard(){const rs=await api('/api/roots');const inp=el('input',{placeholder:'/var/mnt/data/.../mein-entwicklungsordner'});
 const rows=rs.map(r=>el('div',{class:'bar'},el('b',{},r.path),el('span',{class:'mut'},r.projects.length+' Projekt(e)'+(r.projects.length?': '+r.projects.join(', '):'')),
  r.fixed?el('span',{class:'pill'},'Standard'):el('button',{class:'b d',on:{click:async()=>{await api('/api/roots',{action:'remove',path:r.path});setTab('projects')}}},'entfernen')));
 return el('div',{class:'card'},el('b',{},'Entwicklungsordner'),...rows,el('label',{},'Ordner hinzufügen und Projekte darin einlesen (jeder Unterordner mit .git)'),
  el('div',{class:'bar'},inp,el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/roots',{action:'add',path:inp.value});toast(r.message);setTab('projects')}}},'Einlesen'),
   el('button',{class:'b',on:{click:async()=>{await api('/api/roots',{action:'scan'});setTab('projects')}}},'Neu einlesen')))}
async function projects(){
 if(!T){main.replaceChildren(el('div',{class:'card'},'Token fehlt. Dashboard mit "vibe ui" öffnen (der Link enthält das Token).'));return}
 const render=async()=>{const ps=await api('/api/projects');
  const tb=el('table',{},el('tr',{},...['Projekt','Typ','Branch','Offen','Änd.','Lauf','Letzter Commit'].map(h=>el('th',{},h))));
  ps.forEach(p=>tb.append(el('tr',{class:'row',on:{click:()=>detail(p.name).catch(showErr)}},el('td',{},p.name,p.init?null:el('span',{class:'warn'},' ●')),el('td',{},p.type),el('td',{},p.branch),
   el('td',{class:p.open?'warn':'ok'},p.open),el('td',{},p.dirty),el('td',{},el('span',{class:'pill '+(p.running?'run':'')},p.running?'läuft':'-'),p.pause_after?el('span',{class:'pill warn',title:'Nach dem aktuellen Arbeitspaket wird kein neues gestartet'},' Pause'):null),el('td',{class:'mut'},p.last))));
  const rc=await rootsCard();
  main.replaceChildren(el('div',{class:'card'},ps.length?tb:el('span',{class:'mut'},'Keine Projekte gefunden. Entwicklungsordner unten hinzufügen.'),ps.some(p=>!p.init)?el('div',{class:'warn',style:'margin-top:8px'},'● = noch nicht für vibe vorbereitet (Projekt öffnen → „Für vibe vorbereiten“)'):null),rc,newForm())};
 await render();timer=setInterval(()=>{if(tab==='projects'&&!document.activeElement.matches('input,textarea,select'))render().catch(()=>{})},5000)}
function newForm(){const types=el('select',{});api('/api/types').then(t=>t.forEach(x=>types.append(el('option',{},x))));
 const nm=el('input',{placeholder:'projektname (a-z, 0-9, -)'}),tp=el('input',{placeholder:'nur Android: Vorlage aus "android create --list"'});
 return el('div',{class:'card',id:'nf'},el('b',{},'Neues Projekt (im Standardordner)'),el('div',{class:'grid'},el('div',{},el('label',{},'Name'),nm),el('div',{},el('label',{},'Typ'),types)),el('label',{},'Android-Vorlage'),tp,
  el('div',{class:'mut'},'Nach dem Anlegen öffnet der Projektassistent die fachlichen Schritte und legt SPEC.md sowie fehlende Grundlagen an.'),
  el('div',{class:'bar'},el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/new',{name:nm.value,type:types.value,tpl:tp.value});toast(r.message);if(r.ok){DTAB='assistent';detail(nm.value).catch(showErr)}else setTab('projects')}}},'Anlegen und Assistent öffnen')))}
let DTAB='arbeit';
const DTABS=[['arbeit','Arbeit'],['ausgabe','Ausgabe'],['assistent','Assistent'],['einstellungen','Einstellungen']];
function tile(k,v,tone){return el('div',{class:'tile'},el('div',{class:'k'},k),el('div',{class:'v'+(tone?' '+tone:'')},String(v)))}
function tabPanel(key,...c){return el('section',{class:'tabpanel',role:'tabpanel',id:'panel-'+key,'data-panel':key,'aria-labelledby':'tab-'+key,hidden:''},...c)}
function showDetailTab(key,panels,btns,focus){DTAB=key;
 DTABS.forEach(([k])=>{const on=k===key;btns[k].setAttribute('aria-selected',on?'true':'false');btns[k].tabIndex=on?0:-1;panels[k].hidden=!on});
 if(key!=='ausgabe')exitLogFull();if(key==='ausgabe'&&LOG)LOG.fit();if(focus&&btns[key])btns[key].focus()}
function detailTabs(panels){const btns={},list=el('div',{class:'tabs',role:'tablist','aria-label':'Projektbereiche'});
 DTABS.forEach(([k,label])=>{const b=el('button',{type:'button',role:'tab',id:'tab-'+k,'aria-controls':'panel-'+k},label);
  b.addEventListener('click',()=>showDetailTab(k,panels,btns));btns[k]=b;list.append(b)});
 list.addEventListener('keydown',e=>{const keys=DTABS.map(d=>d[0]);const i=Math.max(0,keys.indexOf(DTAB));let n=null;
  if(e.key==='ArrowRight')n=(i+1)%keys.length;else if(e.key==='ArrowLeft')n=(i-1+keys.length)%keys.length;
  else if(e.key==='Home')n=0;else if(e.key==='End')n=keys.length-1;else return;
  e.preventDefault();showDetailTab(keys[n],panels,btns,true)});
 showDetailTab(DTAB in panels?DTAB:'arbeit',panels,btns);
 return {list,btns}}
async function detail(name){
 clearInterval(timer);if(es){es.close();es=null}exitLogFull();LOG=null;window.scrollTo(0,0);
 const d=await api('/api/project?name='+encodeURIComponent(name));
 const runPill=el('span',{id:'runstate',class:'pill '+(d.running?'run':''),title:d.running?'Der Paket-Läufer ist aktiv.':'Der Agentenlauf ist beendet.'},d.running?'läuft':'gestoppt');
 const refreshRun=async()=>{const s=await api('/api/run-state?name='+encodeURIComponent(name));
  runPill.textContent=s.running?'läuft':'gestoppt';runPill.className='pill '+(s.running?'run':'');
  runPill.title=s.running?'Der Paket-Läufer ist aktiv.':'Der Agentenlauf ist beendet.'};
 const act=(p,b)=>async()=>{const r=await api(p,b);toast(r.message);detail(name).catch(showErr)};
 let openTab=()=>{};
 const items=el('div',{class:'itemlist'},d.items.length?d.items.map(i=>el('div',{class:'item'},el('span',{class:'pill '+(i.state==='BLOCKIERT'?'bad':'warn')},i.state),el('span',{},el('b',{},i.id+' '),i.title))):el('span',{class:'ok'},'Alles abgehakt'));
 const itemsCard=el('div',{class:'card'},el('div',{class:'bar'},el('b',{},'Offene Arbeitspakete ('+d.items.length+')')),items);
 const fact=(k,v)=>el('div',{class:'factrow'},el('span',{class:'mut'},k),el('span',{},String(v)));
 const factsCard=el('div',{class:'card'},el('b',{},'Projekt'),fact('Pfad',d.path),fact('Typ',d.type),fact('Branch',d.branch),fact('Letzter Commit',d.last||'—'),fact('Vorbereitet',d.init?'ja':'nein'));
 const startVerify=mode=>async()=>{openTab('ausgabe');const r=await api('/api/verify',{name,mode});toast(r.message);if(r.ok)stream('verify')};
 const checksCard=el('div',{class:'card'},el('b',{},'Prüfungen'),
  el('div',{class:'mut'},'quick prüft Struktur und Sicherheit, full zusätzlich Unit- und Browsertests. Die Ausgabe erscheint im Bereich „Ausgabe“.'),
  el('div',{class:'bar'},el('button',{class:'b',type:'button',on:{click:startVerify('quick')}},'Prüfung quick'),
   el('button',{class:'b',type:'button',on:{click:startVerify('full')}},'Prüfung full'),
   el('a',{href:'__OPENCODE_URL__',target:'_blank'},'opencode-Weboberfläche')));
 const tsel=el('select',{});api('/api/types').then(t=>t.forEach(x=>{const o=el('option',{},x);if(x===d.type)o.selected=true;tsel.append(o)}));
 const initCard=d.init?null:el('div',{class:'card warnbox'},el('b',{class:'warn'},'Noch nicht für vibe vorbereitet'),el('div',{class:'mut'},'Ergänzt fehlende Dateien (FEEDBACK.md, TICKETS.md, AGENTS.md, .vibe/project.env). Vorhandenes wird nie überschrieben, es wird nichts committet.'),
  el('div',{class:'bar'},tsel,el('button',{class:'b p',type:'button',on:{click:act('/api/init',{name,type:tsel.value})}},'Für vibe vorbereiten')));
 const head=el('div',{class:'bar detailbar'},
  el('button',{class:'b',type:'button',on:{click:()=>setTab('projects')}},'← zurück'),
  el('div',{class:'dhead'},el('h2',{},name),runPill,el('span',{class:'mut dmeta',title:d.path},d.type+' · '+d.branch+' · '+d.dirty+' Änderungen · '+d.path)),
  el('div',{class:'bar dactions'},el('button',{class:'b p',type:'button',on:{click:act('/api/run',{name})}},'Agentenlauf starten'),el('button',{class:'b',type:'button',on:{click:act('/api/stop',{name})}},'Stoppen')));
 const tiles=el('div',{class:'tiles'},tile('Offene Arbeitspakete',d.items.length,d.items.length?'warn':'ok'),tile('Änderungen',d.dirty,d.dirty?'warn':'ok'),tile('Branch',d.branch,'small'),tile('Letzter Commit',d.last||'—','small'));
 const L=logView(d,()=>stream('run'));
 const panels={arbeit:tabPanel('arbeit',tiles,el('div',{class:'grid'},
   el('div',{},itemsCard,ticketCard(d,name),ticketFormCard(d,name),feedbackCard(d,name),bugFormCard(d,name),feedbackFormCard(d,name)),
   el('div',{},pauseCard(d,name),autonomousCard(d,name),checksCard,factsCard))),
  ausgabe:tabPanel('ausgabe',L.card),
  assistent:tabPanel('assistent',guideCard(name)),
  einstellungen:tabPanel('einstellungen',el('div',{class:'grid'},projectAgentsCard(name),rightsCard(d,name),sandboxCard(d,name)))};
 const tabs=detailTabs(panels);
 openTab=k=>showDetailTab(k,panels,tabs.btns);
 main.replaceChildren(...[head,initCard,tabs.list,panels.arbeit,panels.ausgabe,panels.assistent,panels.einstellungen].filter(Boolean));
 L.fit();
 function stream(kind){if(es)es.close();L.clear();es=new EventSource('/api/stream?name='+encodeURIComponent(name)+'&kind='+kind+'&t='+encodeURIComponent(T));
  es.onmessage=ev=>L.feed(JSON.parse(ev.data).join('\n')+'\n')}
 stream('run');
 timer=setInterval(()=>{refreshRun().catch(()=>{})},3000)}
function pauseCard(d,name){
 const active=!!d.pause_after;
 const btn=el('button',{class:'b'+(active?' p':''),on:{click:async()=>{const r=await api('/api/pause',{name,action:active?'off':'on'});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},active?'Pause aufheben':'Nach aktuellem Paket anhalten');
 return el('div',{class:'card'},el('div',{class:'bar'},el('b',{},'Arbeitspaket-Pause'),el('span',{class:'pill '+(active?'warn':'mut')},active?'Pause angefordert':'keine Pause'),btn),
  el('div',{class:'mut'},'Der laufende Agent wird nicht unterbrochen. Nach dem aktuellen Arbeitspaket startet der Läufer kein neues Paket; die Anforderung gilt einmalig und wird beim Anhalten verbraucht.'))}
function autonomousCard(d,name){
 const active=!!d.autonomous;
 const btn=el('button',{class:'b'+(active?'':' p'),type:'button',on:{click:async()=>{const r=await api('/api/autonomous',{name,action:active?'off':'on'});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},active?'Autonomen Modus ausschalten':'Autonomen Modus einschalten');
 return el('div',{class:'card',id:'autonomous'},el('div',{class:'bar'},el('b',{},'Autonomer Modus'),el('span',{class:'pill '+(active?'warn':'mut')},active?'aktiv':'aus'),btn),
  el('div',{class:'mut'},'Ist der Modus aktiv, entscheidet der Agent ohne Antwort des Nutzers selbst und dokumentiert die Entscheidung als Antwort auf seine Rückfrage. Die Einstellung lässt sich auch während eines Laufs ändern und gilt nur für dieses Projekt.'))}
function projectAgentsCard(name){
 const body=el('div',{},el('span',{class:'mut'},'Lade Agenten …'));
 const rowsCard=(data)=>{
  const rows=data.agents.map(a=>{
   const cb=el('input',{type:'checkbox','aria-label':'Agent '+a.name+' auswählen'});cb.checked=!!a.selected;
   const mo=modelSelect(data.models,data.info,a.override,'— Standard aus Agentendatei —');mo.setAttribute('aria-label','Modell für '+a.name);
   const change=async()=>{const r=await api('/api/project-agents',{name,agent:a.name,selected:cb.checked,model:mo.value});toast(r.message);if(r.ok)load().catch(showErr)};
   cb.addEventListener('change',change);mo.addEventListener('change',change);
   return el('tr',{'data-project-agent':a.name,'data-selected':a.selected?'ja':'nein'},
    el('td',{},cb),el('td',{},a.name),el('td',{class:'mut'},a.scope==='global'?'global':'Projekt'),
    el('td',{class:'mut'},a.effective_model||'—'),el('td',{},mo))});
  const parts=[el('div',{class:'mut'},'Der Agent läuft mit dem Modell aus seiner Datei. Eine Auswahl hier gilt nur für dieses Projekt; abgewählte Agenten startet vibe nicht.'),
   el('table',{},el('tr',{},...['Aktiv','Agent','Geltung','Wirksames Modell','Modell für dieses Projekt'].map(h=>el('th',{},h))),...rows)];
  if(data.error)parts.push(el('div',{class:'bad'},data.error));
  body.replaceChildren(...parts)};
 const load=async()=>{const data=await api('/api/project-agents?name='+encodeURIComponent(name));rowsCard(data)};
 load().catch(e=>body.replaceChildren(el('div',{class:'bad'},'Agentenauswahl nicht verfügbar: '+String(e&&e.message||e))));
 return el('div',{class:'card',id:'project-agents'},el('b',{},'Agenten in diesem Projekt'),body)}
function guideCard(name){
 const body=el('div',{},el('span',{class:'mut'},'Lade Projektassistent …'));
 const load=async()=>{const g=await api('/api/guide?name='+encodeURIComponent(name));body.replaceChildren(...drawGuide(g,name))};
 load().catch(e=>body.replaceChildren(el('div',{class:'bad'},'Projektassistent nicht verfügbar: '+String(e&&e.message||e))));
 return el('div',{class:'card',id:'guide'},body)}
function drawGuide(g,name){
 const out=[],ask={};
 const tone=s=>s==='gefüllt'?'ok':(s==='offen'?'warn':'mut');
 const status=g.complete?el('span',{class:'pill ok'},'vollständig'):el('span',{class:'pill warn'},g.filled+'/'+g.total+' Pflichtschritte');
 out.push(el('div',{class:'bar'},el('b',{},'Projektassistent'),el('span',{class:'mut'},'Fachliche Grundlagen'),status));
 out.push(el('div',{class:'mut'},'Der Assistent schreibt SPEC.md und legt fehlende Grundlagen an. Vorhandene Dateien und gefüllte Abschnitte bleiben unverändert, außer du änderst sie hier ausdrücklich.'));
 out.push(el('div',{class:'mut'},'Dateien: '+g.files.map(f=>(f.exists?'✓ ':'✗ ')+f.path).join(' · ')));
 if(g.missing_files.length)out.push(el('div',{class:'warn'},'Fehlende Pflichtdateien: '+g.missing_files.join(', ')));
 g.steps.forEach(s=>{const ta=el('textarea',{rows:4,value:s.value||''});ask[s.id]=ta;
  const note=el('input',{placeholder:'Hinweis für den Agenten (optional)','aria-label':'Hinweis für '+s.title});
  const block=el('div',{class:'gstep','data-step':s.id},
   el('div',{class:'bar'},el('b',{},s.title),el('span',{class:'pill '+tone(s.status)},s.status),el('span',{class:'mut'},s.required?'Pflicht':'optional')),
   el('label',{},s.question),ta,el('div',{class:'mut'},s.help),
   el('div',{class:'bar'},el('button',{class:'b',on:{click:async()=>{const r=await api('/api/guide',{name,action:'agent',step:s.id,note:note.value});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Mit Agent entwerfen'),note));
  if(s.draft)block.append(el('div',{class:'mut'},el('b',{},'Entwurf des Agenten'),el('pre',{},g.drafts[s.id]||''),
   el('div',{class:'bar'},el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/guide',{name,action:'draft_apply',step:s.id});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Entwurf übernehmen'),
    el('button',{class:'b',on:{click:async()=>{const r=await api('/api/guide',{name,action:'draft_discard',step:s.id});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Entwurf verwerfen'))));
  out.push(block)});
 if(g.agent&&(g.agent.running||g.agent.log))out.push(el('div',{class:'card'},el('div',{class:'bar'},el('b',{},'Agentenauftrag'),el('span',{class:'pill '+(g.agent.running?'run':'mut')},g.agent.running?'läuft':'beendet')),
  el('div',{class:'mut'},'Sitzung '+g.agent.session+' · Agent '+(g.agent.agent||'?')+(g.agent.log?' · Log '+g.agent.log:'')),
  el('pre',{},(g.agent.log_tail||[]).join('\n')||'(noch keine Ausgabe)')));
 out.push(el('div',{class:'bar'},el('button',{class:'b p',on:{click:async()=>{
   const answers={},replace=[];
   g.steps.forEach(s=>{const v=(ask[s.id].value||'').trim();if(!v)return;answers[s.id]=v;if(s.value&&v!==s.value.trim())replace.push(s.id)});
   if(!Object.keys(answers).length){toast('Noch keine Antworten eingetragen.');return}
   const r=await api('/api/guide',{name,action:'save',answers,replace});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Antworten speichern und Dateien anlegen')));
 return out}
function feedbackCard(d,name){const list=el('div',{});const cls=s=>s==='erledigt'?'ok':s==='BLOCKIERT'?'bad':'warn';
 const done=d.feedback.filter(i=>i.completed),pending=d.feedback.filter(i=>!i.completed);let showDone=false;
 const toggle=el('button',{class:'b'});
 const delBtn=i=>{const b=el('button',{class:'b d',on:{click:()=>askInline(b,'Feedback '+i.id+' wirklich löschen?','Ja, löschen',async()=>{const r=await api('/api/feedback',{name,action:'delete',id:i.id});toast(r.message);if(r.ok)detail(name).catch(showErr)})}},'Löschen');return b};
 const rowFor=i=>{const row=el('div',{class:'fbentry','data-id':i.id});
  row.append(el('div',{},el('span',{class:'pill '+cls(i.state)},i.state),i.kind==='bug'?el('span',{class:'pill bad'},' Bug'):null,el('b',{},' '+i.id+' '+i.title)),
   ...(i.description?[el('div',{class:'mut fbdesc'},i.description)]:[]),
   el('div',{class:'bar'},
    ...(i.completed?[el('span',{class:'mut'},'abgeschlossen – nicht bearbeitbar')]:[el('button',{class:'b',on:{click:()=>edit(i,row)}},'Bearbeiten')]),
    delBtn(i)));
  return row};
 const draw=()=>{const shown=showDone?d.feedback:pending;
  list.replaceChildren(...(shown.length?shown.map(rowFor):[el('span',{class:'mut'},showDone?'Noch kein Feedback vorhanden.':'Keine offenen Feedback-Punkte.')]));
  toggle.textContent=showDone?'Abgeschlossene ausblenden':'Abgeschlossene anzeigen ('+done.length+')';
  toggle.classList.toggle('p',showDone);toggle.setAttribute('aria-expanded',showDone?'true':'false');
  toggle.style.display=done.length?'':'none'};
 const edit=(i,row)=>{const t=el('input',{value:i.title}),b=el('textarea',{rows:4,value:i.description||''});
  const ed=el('div',{class:'fbentry','data-id':i.id},el('label',{},'Titel'),t,el('label',{},'Beschreibung'),b,
   el('div',{class:'bar'},el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/feedback',{name,action:'update',id:i.id,title:t.value,description:b.value});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Speichern'),
    el('button',{class:'b',on:{click:()=>ed.replaceWith(row)}},'Abbrechen')));
  row.replaceWith(ed)};
 toggle.addEventListener('click',()=>{showDone=!showDone;draw()});
 draw();
 return el('div',{class:'card',id:'feedback'},el('div',{class:'bar'},el('b',{},'Feedback ('+d.feedback.length+')'),toggle),list)}
function ticketCard(d,name){const list=el('div',{});const cls=s=>s==='erledigt'?'ok':s==='BLOCKIERT'?'bad':'warn';
 const done=d.tickets.filter(i=>i.completed),pending=d.tickets.filter(i=>!i.completed);let showDone=false;
 const toggle=el('button',{class:'b'});
 const delBtn=i=>{const b=el('button',{class:'b d',on:{click:()=>askInline(b,'Arbeitspaket '+i.id+' wirklich löschen?','Ja, löschen',async()=>{const r=await api('/api/ticket',{name,action:'delete',id:i.id});toast(r.message);if(r.ok)detail(name).catch(showErr)})}},'Löschen');return b};
 const rowFor=i=>{const row=el('div',{class:'fbentry','data-id':i.id});
  row.append(el('div',{},el('span',{class:'pill '+cls(i.state)},i.state),el('b',{},' '+i.id+' '+i.title)),
   ...(i.description?[el('div',{class:'mut fbdesc'},i.description)]:[]),
   el('div',{class:'bar'},
    ...(i.completed?[el('span',{class:'mut'},'abgeschlossen – nicht bearbeitbar')]:[el('button',{class:'b',on:{click:()=>edit(i,row)}},'Bearbeiten')]),
    delBtn(i)));
  return row};
 const draw=()=>{const shown=showDone?d.tickets:pending;
  list.replaceChildren(...(shown.length?shown.map(rowFor):[el('span',{class:'mut'},showDone?'Noch keine Arbeitspakete vorhanden.':'Keine offenen Arbeitspakete.')]));
  toggle.textContent=showDone?'Abgeschlossene ausblenden':'Abgeschlossene anzeigen ('+done.length+')';
  toggle.classList.toggle('p',showDone);toggle.setAttribute('aria-expanded',showDone?'true':'false');
  toggle.style.display=done.length?'':'none'};
 const edit=(i,row)=>{const t=el('input',{value:i.title}),b=el('textarea',{rows:4,value:i.description||''});
  const ed=el('div',{class:'fbentry','data-id':i.id},el('label',{},'Titel'),t,el('label',{},'Beschreibung'),b,
   el('div',{class:'bar'},el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/ticket',{name,action:'update',id:i.id,title:t.value,description:b.value});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Speichern'),
    el('button',{class:'b',on:{click:()=>ed.replaceWith(row)}},'Abbrechen')));
  row.replaceWith(ed)};
 toggle.addEventListener('click',()=>{showDone=!showDone;draw()});
 draw();
 return el('div',{class:'card',id:'tickets'},el('div',{class:'bar'},el('b',{},'Arbeitspakete ('+d.tickets.length+')'),toggle),list)}
function ticketFormCard(d,name){
 const f={id:el('input',{placeholder:'z. B. F18','aria-label':'ID des Arbeitspakets'}),t:el('input',{}),b:el('textarea',{rows:3,placeholder:'Was soll umgesetzt werden?'})};
 return el('div',{class:'card',id:'ticket-new'},el('b',{},'Neues Arbeitspaket'),el('label',{},'ID'),f.id,el('label',{},'Titel'),f.t,el('label',{},'Beschreibung'),f.b,
  el('div',{class:'bar'},el('button',{class:'b p',type:'button',on:{click:async()=>{const r=await api('/api/ticket',{name,action:'add',id:f.id.value,title:f.t.value,description:f.b.value});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Arbeitspaket anlegen')))}
function bugFormCard(d,name){
 const f={t:el('input',{}),b:el('textarea',{rows:3,placeholder:'Was funktioniert nicht?'})};
 return el('div',{class:'card',id:'bug-new'},el('b',{},'Bug melden'),el('label',{},'Titel'),f.t,el('label',{},'Beschreibung'),f.b,
  el('div',{class:'bar'},el('button',{class:'b p',type:'button',on:{click:async()=>{const r=await api('/api/feedback',{name,kind:'bug',title:f.t.value,description:f.b.value});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Bug melden')))}
function feedbackFormCard(d,name){
 const f={t:el('input',{}),b:el('textarea',{rows:3,placeholder:'Was soll geändert oder ergänzt werden?'})};
 return el('div',{class:'card',id:'feedback-new'},el('b',{},'Feedback eintragen'),el('label',{},'Titel'),f.t,el('label',{},'Beschreibung'),f.b,
  el('div',{class:'bar'},el('button',{class:'b p',type:'button',on:{click:async()=>{const r=await api('/api/feedback',{name,title:f.t.value,description:f.b.value});toast(r.message);detail(name).catch(showErr)}}},'Eintragen')))}
function logView(d,onRun){
 const pre=el('pre',{id:'log'},(d.tail||[]).join('\n')||'(noch keine Ausgabe)');
 let logPaused=false,logBuf='';
 function append(text){const near=pre.scrollHeight-pre.scrollTop-pre.clientHeight<60;pre.textContent+=text;if(pre.textContent.length>80000)pre.textContent=pre.textContent.slice(-60000);if(near)pre.scrollTop=pre.scrollHeight}
 const pauseBtn=el('button',{class:'b',type:'button'},'Pause'),fullBtn=el('button',{class:'b',type:'button'},'Vergrößern');
 const runBtn=el('button',{class:'b',type:'button',title:'Verbindet die Ausgabe wieder mit dem Agentenlauf',on:{click:onRun}},'Lauf-Log');
 const card=el('div',{class:'card logcard'});
 const fit=()=>{if(card.classList.contains('full'))return;const h=Math.max(240,window.innerHeight-pre.getBoundingClientRect().top-18);pre.style.height=h+'px'};
 pauseBtn.addEventListener('click',()=>{logPaused=!logPaused;pauseBtn.textContent=logPaused?'Fortsetzen':'Pause';pauseBtn.classList.toggle('p',logPaused);
  if(!logPaused&&logBuf){append(logBuf);logBuf='';pre.scrollTop=pre.scrollHeight}});
 fullBtn.addEventListener('click',()=>setLogFull(!card.classList.contains('full')));
 card.append(el('div',{class:'bar'},el('b',{},'Live-Ausgabe'),el('span',{class:'mut'},'Lauf-Ausgabe des aktuellen Projekts'),runBtn,pauseBtn,fullBtn),pre);
 LOG={card,pre,button:fullBtn,fit};
 return {card,fit,clear:()=>{pre.textContent=''},feed:text=>{if(logPaused){logBuf=(logBuf+text).slice(-80000);return}append(text)}}}
function rightsCard(d,name){const inp=el('input',{placeholder:'/absoluter/pfad','aria-label':'Schreibverzeichnis'});
 const reset=el('button',{class:'b',on:{click:()=>askInline(reset,'Standardverzeichnisse wiederherstellen?','Ja, zurücksetzen',async()=>{const r=await api('/api/rights',{name,action:'reset'});toast(r.message);if(r.ok)detail(name).catch(showErr)})}},'Standard wiederherstellen');
 const rows=el('div',{},...(d.write_dirs.length?d.write_dirs.map(p=>el('div',{class:'bar'},el('span',{class:'mut'},p),
   el('button',{class:'b d',on:{click:async()=>{const r=await api('/api/rights',{name,action:'remove',path:p});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Entfernen'))):[el('span',{class:'mut'},'Keine Verzeichnisse – Schreiben ist gesperrt.')]));
 const sandboxOn=!!(d.sandbox&&d.sandbox.enabled);
 return el('div',{class:'card'},el('b',{},'Schreibrechte (Agenten)'),
  el('div',{class:'mut'},sandboxOn
   ? 'Sandbox aktiv: Schreibwerkzeug (edit) und Shell-Befehle (bash) können nur in diesen Verzeichnissen, den Caches der Build-Werkzeuge und /tmp/opencode schreiben. MCP und Netzwerk bleiben erlaubt; Lesezugriffe werden nicht eingeschränkt.'
   : 'Verzeichnisse für das Schreibwerkzeug (edit) der Projektagenten. Voreingestellt sind /tmp/opencode und das Projektverzeichnis. Agenten ohne Schreibrecht bleiben unverändert. Shell-Befehle (bash) bleiben erlaubt und können Dateien außerhalb dieser Liste ändern – die Liste ist keine Sandbox.'),
  d.write_dirs_error?el('div',{class:'bad'},'Liste nicht lesbar: '+d.write_dirs_error):null,
  rows,
  el('div',{class:'bar'},inp,el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/rights',{name,action:'add',path:inp.value});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Hinzufügen')),
  el('div',{class:'bar'},reset,
   el('button',{class:'b',on:{click:async()=>{const r=await api('/api/rights',{name,action:'apply'});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Auf Projektagenten anwenden')),
  el('div',{class:'mut'},d.write_dirs_custom?'Eigene Liste aktiv.':'Standardliste aktiv.'))}
function sandboxCard(d,name){const s=d.sandbox||{enabled:false,tools:[],write_dirs:[],missing_tools:[],error:null,bwrap:''};
 const active=!!s.enabled,missing=s.missing_tools||[],dirs=s.write_dirs||[],tools=s.tools||[];
 const state=!active?'aus':(s.error?'Fehler':(!s.bwrap?'bubblewrap fehlt':(missing.length?'Werkzeuge fehlen':'bereit')));
 const tone=!active?'mut':(s.error||!s.bwrap||missing.length?'bad':'ok');
 const inp=el('input',{value:tools.join(' '),placeholder:'git node npm','aria-label':'Build-Werkzeuge'});
 return el('div',{class:'card',id:'sandbox'},el('div',{class:'bar'},el('b',{},'Sandbox (Shell und Build-Werkzeuge)'),el('span',{class:'pill '+tone},state),
   el('button',{class:'b'+(active?'':' p'),on:{click:async()=>{const r=await api('/api/sandbox',{name,action:active?'off':'on'});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},active?'Sandbox ausschalten':'Sandbox einschalten'),
   el('button',{class:'b',on:{click:async()=>{const r=await api('/api/sandbox',{name,action:'check'});toast(r.message)}}},'Prüfen')),
  el('div',{class:'mut'},'Aktiv läuft der Agent mit eigenem opencode-Server in bubblewrap. Schreiben ist nur in den Verzeichnissen unten, in den Caches der Build-Werkzeuge und in einem privaten Temporärordner möglich; /tmp ist sonst schreibgeschützt. MCP und Netzwerk bleiben verfügbar; Lesezugriffe werden nicht eingeschränkt.'),
  el('div',{class:'mut'},'Die Sandbox-Konfiguration (.vibe/project.env, .vibe/permissions.json) ist im Lauf schreibgeschützt.'),
  s.error?el('div',{class:'bad'},'Fehler: '+s.error):null,
  missing.length?el('div',{class:'bad'},'Fehlende Werkzeuge: '+missing.join(', ')):null,
  !active?el('div',{class:'mut'},'Ohne Sandbox bleiben Shell-Befehle (bash) außerhalb der Liste möglich.'):null,
  el('label',{},'Build-Werkzeuge (Leerzeichen oder Komma)'),inp,
  el('div',{class:'bar'},el('button',{class:'b',on:{click:async()=>{const r=await api('/api/sandbox',{name,action:'tools',tools:inp.value});toast(r.message);if(r.ok)detail(name).catch(showErr)}}},'Werkzeuge speichern')),
  el('details',{},el('summary',{},'Erlaubte Schreibverzeichnisse ('+dirs.length+')'),el('div',{},...dirs.map(p=>el('div',{class:'mut'},p)))))}

/* ---------- Kosten ---------- */
const PRICE_SOURCE={user:'eigener Preis',system:'Systempreis',kostenlos:'kostenlos',unbekannt:'Preis unbekannt'};
function fmtN(n){return Number(n||0).toLocaleString('de-DE')}
function fmtEUR(v){return Number(v||0).toLocaleString('de-DE',{minimumFractionDigits:4,maximumFractionDigits:4})+' €'}
function pricePill(src){return el('span',{class:'pill '+(src==='user'?'ok':src==='unbekannt'?'warn':'mut'),title:'Preisquelle: '+(PRICE_SOURCE[src]||src)},PRICE_SOURCE[src]||src)}
function tokenCells(t){return [el('td',{class:'num'},fmtN(t.input)),el('td',{class:'num'},fmtN(t.cached)),el('td',{class:'num'},fmtN(t.output))]}
function costsNote(d){return el('div',{class:'mut'},'Preise in '+d.currency+' je 1 Mio. Tokens. „Eingabe“ enthält die gecachten Tokens, „Ausgabe“ die Reasoning-Tokens. Unbekannte Modelle werden mit 0 € angesetzt, bis ein Preis eingetragen ist. Eigene Preise gelten nur für dieses Projekt und schlagen Systempreise.')}
async function costs(){
 const d=await api('/api/costs');
 const head=['Projekt','Pakete','Sitzungen','Eingabe','davon cached','Ausgabe','Kosten'];
 const tb=el('table',{},el('tr',{},...head.map(h=>el('th',{},h))));
 d.projects.forEach(p=>tb.append(el('tr',{class:'row','data-project':p.name,on:{click:()=>costDetail(p.name).catch(showErr)}},
  el('td',{},p.name),el('td',{class:'num'},fmtN(p.packages)),el('td',{class:'num'},fmtN(p.sessions)),...tokenCells(p.tokens),el('td',{class:'num'},fmtEUR(p.cost)))));
 tb.append(el('tr',{},el('td',{},el('b',{},'Gesamt')),el('td',{}),el('td',{class:'num'},fmtN(d.total.sessions)),...tokenCells(d.total.tokens),el('td',{class:'num'},el('b',{},fmtEUR(d.total.cost)))));
 main.replaceChildren(el('div',{class:'card',id:'costs'},el('div',{class:'bar'},el('b',{},'Kosten je Projekt'),el('span',{class:'mut'},'EUR je 1 Mio. Tokens')),
  d.available?null:el('div',{class:'warn'},'Sitzungsdaten nicht verfügbar: '+(d.message||'unbekannt')),
  d.projects.length?tb:el('span',{class:'mut'},'Keine Projekte gefunden.'),
  el('div',{class:'mut',style:'margin-top:8px'},'Quelle: '+(d.db||'—')+' (nur lesend). Projekt anklicken für Arbeitspakete, Agenten und Modelle.'),
  el('div',{class:'bar'},el('button',{class:'b',on:{click:()=>costs().catch(showErr)}},'Aktualisieren'))));
}
async function costDetail(name){
 const d=await api('/api/costs?name='+encodeURIComponent(name));
 const tb=el('table',{},el('tr',{},...['Paket / Modell','Sitzungen','Eingabe','davon cached','Ausgabe','Kosten'].map(h=>el('th',{},h))));
 d.packages.forEach(p=>{
  tb.append(el('tr',{class:'row','data-package':p.id||'ohne'},el('td',{},el('b',{},p.id||'Ohne Arbeitspaket'),p.title&&p.id?el('div',{class:'mut'},p.title):null),
   el('td',{class:'num'},fmtN(p.sessions)),...tokenCells(p.tokens),el('td',{class:'num'},fmtEUR(p.cost))));
  p.models.forEach(m=>tb.append(el('tr',{class:'mut','data-model-row':m.model},
   el('td',{style:'padding-left:22px'},m.agent+' · '+m.model+' ',pricePill(m.price_source)),
   el('td',{}),...tokenCells(m.tokens),el('td',{class:'num'},fmtEUR(m.cost)))));
 });
 tb.append(el('tr',{},el('td',{},el('b',{},'Summe Projekt')),el('td',{class:'num'},fmtN(d.total.sessions)),...tokenCells(d.total.tokens),el('td',{class:'num'},el('b',{},fmtEUR(d.total.cost)))));
 const priceInputs=[];
 const priceRows=d.models.map(m=>{
  const cur=m.price||{input:0,cached_input:0,output:0};
  const fields=[['input','Eingabe'],['cached_input','cached'],['output','Ausgabe']].map(([f,l])=>{
   const inp=el('input',{type:'number',min:'0',step:'0.0001','data-model':m.model,'data-field':f,'aria-label':l+' '+m.model,value:String(cur[f]??0),style:'width:110px'});
   priceInputs.push(inp);return el('label',{style:'display:inline-flex;gap:4px;align-items:center;margin-right:12px'},l,inp)});
  const reset=el('button',{class:'b',on:{click:async()=>{const r=await api('/api/costs',{name,action:'prices',prices:{[m.model]:null}});toast(r.message);if(r.ok)costDetail(name).catch(showErr)}}},'Systempreis');
  return el('div',{class:'bar','data-price-model':m.model},el('b',{},m.model),pricePill(m.price_source),...fields,reset)});
 const save=el('button',{class:'b p',on:{click:async()=>{
   const prices={};
   for(const inp of priceInputs){const raw=String(inp.value).trim().replace(',','.');
    if(raw===''){toast('Bitte für '+inp.dataset.model+' alle drei Preise eintragen.');inp.focus();return}
    const num=Number(raw);
    if(!Number.isFinite(num)||num<0){toast('Preis für '+inp.dataset.model+' ist ungültig.');inp.focus();return}
    (prices[inp.dataset.model]=prices[inp.dataset.model]||{})[inp.dataset.field]=num}
   const r=await api('/api/costs',{name,action:'prices',prices});toast(r.message);
   if(r.ok)costDetail(name).catch(showErr)}}},'Preise speichern');
 main.replaceChildren(
  el('div',{class:'bar'},el('button',{class:'b',on:{click:()=>costs().catch(showErr)}},'← alle Projekte'),el('h2',{style:'margin:0'},name),el('span',{class:'mut'},'Kosten in '+d.currency)),
  el('div',{class:'card',id:'cost-detail','data-project':name},
   el('div',{class:'bar'},el('b',{},'Kosten je Arbeitspaket'),el('span',{class:'pill '+(d.available?'ok':'bad')},d.available?'Daten gelesen':'keine Daten')),
   d.available?null:el('div',{class:'warn'},'Sitzungsdaten nicht verfügbar: '+(d.message||'unbekannt')),
   costsNote(d),
   d.packages.length?tb:el('span',{class:'mut'},'Keine Sitzungen für dieses Projekt gefunden.')),
  el('div',{class:'card',id:'cost-prices'},el('b',{},'Preise je 1 Mio. Tokens (nur dieses Projekt)'),
   el('div',{class:'mut'},'Eigene Preise schlagen systemische Preise. „Systempreis“ entfernt den eigenen Preis.'),
   ...(priceRows.length?priceRows:[el('span',{class:'mut'},'Noch keine Modelle in diesem Projekt verwendet.')]),
   priceRows.length?el('div',{class:'bar'},save):null));
}

/* ---------- Agenten, Modelle, Profile ---------- */
let AG=null,AGFILTER='alle';
function mval(node){return node&&typeof node==='object'?String(node.wert??node.text??'unbekannt'):'unbekannt'}
function msrc(node){if(!node||!node.quelle)return 'Quelle unbekannt';return node.quelle+(node.datum?' ('+node.datum+')':'')}
function mart(node){return node&&node.art?' ['+node.art+']':''}
function mAssert(label,node){return el('div',{class:'mut','data-assertion':label},el('b',{},label+': '),mval(node),mart(node),el('span',{class:'mut'},' — '+msrc(node)))}
function mList(label,rows){return el('div',{},el('b',{},label),rows&&rows.length?el('ul',{class:'l'},rows.map(node=>el('li',{},mval(node)+mart(node)+' — '+msrc(node)))):el('div',{class:'mut'},'keine Angaben'))}
function mPrice(m){const p=(m&&m.preis)||{};const rows=[el('div',{},el('b',{},'Preis: '),p.text||'unbekannt')];
 if(p.status&&p.status!=='unbekannt'){rows.push(el('div',{class:'mut'},'Währung: '+(p.waehrung||'?')+' · Einheit: '+(p.einheit||'?')+' · Stand: '+(p.stand||'?')+' · Quelle: '+(p.quelle||'?')));
  const t=p.tarife||{};rows.push(el('div',{class:'mut'},'Tarife je Einheit: Eingabe '+(t.eingabe??'?')+', Ausgabe '+(t.ausgabe??'?')+(t.cache_lesen!=null?', Cache lesen '+t.cache_lesen:'')+(t.cache_schreiben!=null?', Cache schreiben '+t.cache_schreiben:'')));
  (t.staffeln||[]).forEach(s=>rows.push(el('div',{class:'mut'},'Staffel ab '+(s.ab_kontext??'?')+' Kontext: '+(s.eingabe??'?')+' / '+(s.ausgabe??'?'))))}
 else if(p.grund){rows.push(el('div',{class:'mut'},'Grund: '+p.grund))}
 return el('div',{class:'mprice'},...rows)}
function modelLabel(id,info){const m=info[id];if(!m)return id;return `${id} — ${(m.preis||{}).text||'unbekannt'} · ${mval((m.einschaetzungen||{}).tempo)}, ${mval((m.einschaetzungen||{}).aufwand)} Aufwand, Daten ${mval((m.fakten||{}).daten)}`}
function modelSelect(models,info,current,blank){const s=el('select',{});if(blank)s.append(el('option',{value:''},blank));const groups={};
 models.forEach(m=>{(groups[m.split('/')[0]]=groups[m.split('/')[0]]||[]).push(m)});if(current&&!models.includes(current))(groups[current.split('/')[0]]=groups[current.split('/')[0]]||[]).push(current);
 Object.entries(groups).forEach(([g,ms])=>{const og=el('optgroup',{label:g});ms.forEach(m=>og.append(el('option',{value:m},modelLabel(m,info))));s.append(og)});if(current)s.value=current;return s}
async function agents(){AG=await api('/api/agents');const d=AG;
 const sel=el('select',{'aria-label':'Bereich filtern'},el('option',{value:'alle'},'Alle'),el('option',{value:'global'},'Nur global (alle Projekte)'),...d.projects.map(p=>el('option',{value:p},'Projekt: '+p)));sel.value=AGFILTER;
 sel.addEventListener('change',()=>{AGFILTER=sel.value;agents().catch(showErr)});
 const rows=d.agents.filter(a=>AGFILTER==='alle'||a.scope===AGFILTER);
 const tb=el('table',{},el('tr',{},...['Agent','Geltung','Wirksam','Modus','Modell','Beschreibung',''].map(h=>el('th',{},h))));
 rows.forEach(a=>tb.append(el('tr',{'data-agent':a.name,'data-scope':a.scope},
  el('td',{},a.name,a.role?el('span',{class:'pill',title:'Rolle laut profiles.json'},' Rolle '+a.role):null,
   a.conflict?el('span',{class:'pill warn',title:'Gleicher Name in global und Projekt – der Projektagent gilt nur in seinem Projekt'},' Konflikt'):null,
   a.valid?null:el('span',{class:'pill bad',title:'Datei ist kein gültiger Agent – im Rohtexteditor bearbeitbar'},' defekt')),
  el('td',{},a.scope==='global'?el('span',{class:'pill ok'},'global'):el('span',{class:'pill'},'Projekt: '+a.scope)),
  el('td',{class:'prio'},a.priority),
  el('td',{},a.mode),el('td',{class:'mut'},a.model),el('td',{class:'mut'},a.description),
  el('td',{},el('button',{class:'b',type:'button',on:{click:()=>agentForm(a.scope,a.name).catch(showErr)}},'Bearbeiten')))));
 main.replaceChildren(el('div',{class:'card',id:'agents'},
   el('div',{class:'bar'},el('b',{},'Agenten'),sel,el('button',{class:'b p',type:'button',on:{click:()=>agentForm(null,null).catch(showErr)}},'Neuer Agent')),
   rows.length?tb:el('span',{class:'mut'},'Keine Agenten in diesem Bereich.'),
   el('div',{class:'mut',style:'margin-top:8px'},'Global = ~/.config/opencode/agents (für alle Projekte). Projekt = <Projekt>/.opencode/agents (nur dort, Teil des Repos). Ein Projektagent mit demselben Namen überschreibt den globalen Agenten ausschließlich in seinem Projekt; „Wirksam“ nennt die tatsächliche Geltung.')),
  profilesCard(d),modelsCard(d))}
function profilesCard(d){const P=JSON.parse(JSON.stringify(d.profiles));const names=Object.keys(P.profile);const cur=el('select',{},...names.map(n=>el('option',{value:n},n+(n===P.aktiv?' (aktiv)':''))));cur.value=P.aktiv;
 const roles=['coder','reviewer'];const body=el('div',{});
 const draw=()=>{const prof=P.profile[cur.value];body.replaceChildren(
   el('table',{},el('tr',{},el('th',{},'Rolle'),el('th',{},'Agenten in dieser Rolle'),el('th',{},'Modell im Profil „'+cur.value+'“')),
    ...roles.map(r=>{const ms=modelSelect(d.models,d.info,prof[r]||'','— nicht ändern —');ms.addEventListener('change',()=>{prof[r]=ms.value});
      return el('tr',{},el('td',{},r),el('td',{class:'mut'},Object.entries(P.rollen).filter(([a,x])=>x===r).map(([a])=>a).join(', ')||'—'),el('td',{},ms))})))};
 cur.addEventListener('change',draw);draw();
 const rol=el('div',{class:'mut'},'Rollenzuordnung (globale Agenten): ',...d.agents.filter(a=>a.scope==='global').map(a=>{const s=el('select',{style:'width:auto;margin:0 8px 0 4px'},el('option',{value:''},'—'),...roles.map(r=>el('option',{value:r},r)));s.value=P.rollen[a.name]||'';
   s.addEventListener('change',()=>{if(s.value)P.rollen[a.name]=s.value;else delete P.rollen[a.name]});return el('span',{},a.name,s)}));
 return el('div',{class:'card'},el('details',{open:'open'},el('summary',{},'Profile – Modelle pro Rolle umschalten (z. B. kostenlos ↔ bezahlt)'),
  el('div',{class:'mut',style:'margin:6px 0'},'Ein Profil legt fest, welches Modell die Rollen Coder und Reviewer nutzen. „Anwenden“ schreibt die model:-Zeile der zugeordneten globalen Agenten (mit Sicherung). Bezahlte Modelle erscheinen erst, wenn der Anbieter verbunden ist (/connect bzw. opencode auth login).'),
  el('div',{class:'bar'},cur,el('button',{class:'b',on:{click:async()=>{const r=await api('/api/profiles',{action:'save',data:P});toast(r.message)}}},'Profile speichern'),
   el('button',{class:'b p',on:{click:async()=>{const sv=await api('/api/profiles',{action:'save',data:P});const r=await api('/api/profiles',{action:'use',profile:cur.value});toast(r.message);if(r.ok)agents().catch(showErr)}}},'Speichern und anwenden')),body,rol))}
function modelsCard(d){const used={};d.agents.forEach(a=>{(used[a.model]=used[a.model]||[]).push(a.name+(a.scope==='global'?'':'@'+a.scope))});
 const K=d.katalog||{};const known=d.models.length>0;
 const ids=d.models.filter(m=>m.startsWith('opencode/')||d.info[m]);Object.keys(d.info).forEach(i=>{if(!ids.includes(i))ids.push(i)});
 const other={};d.models.filter(m=>!m.startsWith('opencode/')&&!d.info[m]).forEach(m=>{other[m.split('/')[0]]=(other[m.split('/')[0]]||0)+1});
 const tb=el('table',{},el('tr',{},...['Modell','Anbieter','Preis','Tempo','Aufwand','Daten','Bilder','Coder','Reviewer','in Verwendung'].map(h=>el('th',{},h))));
 ids.forEach(id=>{const m=d.info[id]||null;const gone=!!m&&known&&!d.models.includes(id);
  let det;
  if(!m){det=el('tr',{class:'detail','data-model-detail':id},el('td',{colspan:'10'},el('div',{'data-model-unknown':'1'},
    el('b',{},'Kein Katalogeintrag'),el('div',{class:'mut'},'Für dieses verbundene Modell liegen keine belegten Fakten, Einschätzungen oder Preise vor.'))));det.style.display='none'}
  else{const facts=Object.entries(m.fakten||{}).map(([k,n])=>mAssert(k,n));
   const assessments=Object.entries(m.einschaetzungen||{}).map(([k,n])=>mAssert(k,n));
   const beleg=m.id_beleg||{};
   det=el('tr',{class:'detail','data-model-detail':id},el('td',{colspan:'10'},el('div',{class:'grid3'},
    el('div',{class:'mfacts'},el('b',{},'Fakten (Quelle/Datum)'),...(facts.length?facts:[el('div',{class:'mut'},'keine Angaben')])),
    el('div',{class:'mopinion'},el('b',{},'Einschätzungen (Quelle/Datum)'),...(assessments.length?assessments:[el('div',{class:'mut'},'keine Angaben')]),mList('Stärken',m.staerken),mList('Schwächen',m.schwaechen)),
    el('div',{class:'mproof'},el('b',{},'Preis und Beleg'),mPrice(m),
     el('div',{class:'mut'},'ID-Beleg: '+(beleg.quelle||'—')+(beleg.datum?' ('+beleg.datum+')':'')),
     el('div',{class:'mut'},'ID-Status: '+(m.id_status||'unbekannt')),
     gone?el('div',{class:'bad'},'Nicht in „opencode models“ (Anbieter nicht verbunden oder Modell entfernt).'):null,
     m.id_status==='entfernt'?el('div',{class:'bad'},'Als entfernt geführt'+(m.entfernt_am?' seit '+m.entfernt_am:'')+(m.entfernt_quelle?' ('+m.entfernt_quelle+')':'')):null))));
   det.style.display='none'}
  const price=(m&&m.preis)||{};
  const removed=!!m&&(gone||m.id_status==='entfernt');
  tb.append(el('tr',{class:'row','data-model-row':id,on:{click:()=>{det.style.display=det.style.display==='none'?'table-row':'none'}}},
   el('td',{},'▸ '+((m&&m.name)||id),removed?el('span',{class:'pill bad'},' nicht mehr gelistet'):null,el('div',{class:'mut'},id)),
   el('td',{class:'mut'},(m&&m.anbieter)||'?'),
   el('td',{class:'mprice-cell','data-price-status':price.status||'unbekannt'},price.text||'unbekannt'),
   el('td',{},badge(mval(m&&(m.einschaetzungen||{}).tempo))),el('td',{},badge(mval(m&&(m.einschaetzungen||{}).aufwand))),
   el('td',{},badge(mval(m&&(m.fakten||{}).daten))),el('td',{},badge(mval(m&&(m.fakten||{}).bild))),
   el('td',{},badge(mval(m&&(m.einschaetzungen||{}).coder))),el('td',{},badge(mval(m&&(m.einschaetzungen||{}).reviewer))),
   el('td',{class:'mut'},(used[id]||[]).join(', ')||'—')));tb.append(det)});
 const findings=K.findings||[];
 const findingBox=findings.length?el('div',{class:'card err','data-catalog-findings':findings.length},el('b',{},'Katalogbefunde ('+findings.length+')'),el('ul',{class:'l'},findings.map(f=>el('li',{},f.text)))):null;
 const legacy=K.legacy?el('div',{class:'bad'},'Altkatalog (Schema 1): Die Angaben sind nicht erneut geprüft und nur als Altbestand lesbar.'):null;
 const nei=K.nicht_uebernommen||[];
 const altbestand=nei.length?el('details',{'data-not-adopted':'1'},el('summary',{},'Nicht übernommene Altbestände ('+nei.length+')'),
   el('div',{class:'mut'},'Diese Modelle standen im Altkatalog, sind aber am Prüftag nicht bestätigt und werden deshalb nicht als Fakten geführt.'),
   el('ul',{class:'l'},nei.map(x=>el('li',{},el('b',{},x.id),' – '+(x.grund||'kein Grund'))))):null;
 const sources=(K.quellen||[]).map(q=>q.name+(q.datum?' ('+q.datum+')':''));
 return el('div',{class:'card',id:'models'},el('details',{},el('summary',{},'Modelle – Fakten, Einschätzungen und Preise (aufklappen, Zeile anklicken für Details)'),
   el('div',{class:'mut',style:'margin:8px 0'},'Stand '+(d.stand||'?')+' · Katalog '+(K.version||'?')+'. '+d.hinweis),
   legacy,findingBox,
   el('div',{class:'mut','data-catalog-sources':'1'},'Quellen: '+(sources.length?sources.join('; '):'keine Quellen im Katalog')),
   tb,
   altbestand,
   Object.keys(other).length?el('div',{class:'mut',style:'margin-top:8px'},'Weitere verbundene Anbieter (ohne Katalogeintrag): '+Object.entries(other).map(([k,v])=>k+' ('+v+' Modelle)').join(', ')):null))}
async function agentForm(scope,name){const d=AG||await api('/api/agents');const isNew=!name;
 let text='',digest=null,fields={},backups=[];
 if(!isNew){const loaded=await api('/api/agent?scope='+encodeURIComponent(scope)+'&name='+encodeURIComponent(name));text=loaded.text;digest=loaded.digest;fields=loaded.fields||{};backups=loaded.backups||[]}
 const structured=!fields.invalid;
 const nm=el('input',{'aria-label':'Name',placeholder:'name (a-z, 0-9, -, _)'});if(!isNew){nm.value=name;nm.setAttribute('disabled','disabled')}
 const sc=el('select',{'aria-label':'Geltung'},el('option',{value:'global'},'global (alle Projekte)'),...d.projects.map(p=>el('option',{value:p},'Projekt: '+p)));sc.value=scope||'global';if(!isNew)sc.setAttribute('disabled','disabled');
 const ds=el('input',{'aria-label':'Beschreibung',placeholder:'Wofür ist der Agent da? (Pflicht)',value:fields.description||''});
 const md=el('select',{'aria-label':'Modus'},el('option',{value:''},'— nicht gesetzt —'),el('option',{value:'subagent'},'subagent (wird von anderen aufgerufen)'),el('option',{value:'primary'},'primary (direkt startbar)'),el('option',{value:'all'},'all'));
 md.value=fields.mode||(isNew?'subagent':'');
 const mo=modelSelect(d.models,d.info,fields.model||'','— Standardmodell —');mo.setAttribute('aria-label','Modell');
 const permsFor=()=>sc.value==='global'?d.perms:d.perms_project;
 const pm=el('select',{'aria-label':'Rechte'});
 const setPerms=()=>{const keep=pm.value;const list=Object.entries(permsFor()).map(([k,v])=>el('option',{value:k},v));
  if(!isNew)list.unshift(el('option',{value:''},fields.permission_custom?'individuell – unverändert lassen':'— nicht gesetzt —'));
  pm.replaceChildren(...list);
  pm.value=keep&&permsFor()[keep]?keep:(isNew?'lesen':(fields.permission&&permsFor()[fields.permission]?fields.permission:''))};
 setPerms();
 const tp=el('input',{'aria-label':'Temperatur',placeholder:'z. B. 0.1',value:isNew?'0.1':(fields.temperature||'')});
 const st=el('input',{'aria-label':'Max. Schritte',placeholder:'z. B. 60',value:isNew?'':(fields.steps||'')});
 const pr=el('textarea',{'aria-label':'Prompt',rows:5,placeholder:'System-Prompt: Rolle, Regeln, Ausgabeformat',value:isNew?'':(fields.prompt||'')});
 const raw=el('textarea',{class:'raw','aria-label':'Datei (Frontmatter + Prompt)'});raw.value=text;
 // F17: Ausgangsstand der strukturierten Felder. Beim Speichern werden nur
 // geänderte Felder übernommen; freie Rohtextänderungen an anderer Stelle
 // bleiben erhalten und eine geänderte Modellauswahl geht nicht verloren.
 const formValues=()=>({description:ds.value,mode:md.value,model:mo.value,temperature:tp.value,steps:st.value,permission:pm.value,prompt:pr.value});
 let baseline=formValues();
 const hint=el('div',{class:'mut'});
 const updHint=()=>{const dirs=sc.value==='global'?null:(d.write_dirs[sc.value]||[]);const err=sc.value==='global'?null:(d.write_dirs_errors||{})[sc.value];
  hint.textContent=err?'Schreibrechte nicht lesbar: '+err:(sc.value==='global'?'Global: volle Schreibrechte ohne Verzeichnisgrenze.':'Schreibrechte (edit, voll) nur in: '+(dirs&&dirs.length?dirs.join(', '):'keine Verzeichnisse – Schreiben gesperrt')+'. Shell (bash) bleibt erlaubt.')};
 updHint();
 const unknown=el('div',{class:'mut',id:'agent-unknown'},
  fields.invalid?'Strukturierte Bearbeitung nicht möglich: '+fields.invalid:
  (fields.unknown&&fields.unknown.length?'Unbekannte Felder bleiben beim Speichern erhalten: '+fields.unknown.join(', '):'Keine unbekannten Frontmatter-Felder.'));
 const gen=async()=>{const r=await api('/api/agent_template',{description:ds.value,mode:md.value,model:mo.value,temperature:tp.value,steps:st.value,perm:pm.value||'lesen',prompt:pr.value,scope:sc.value});if(r.ok)raw.value=r.message;else toast(r.message)};
 const apply=async()=>{if(!structured){toast('Strukturierte Bearbeitung nicht möglich: '+fields.invalid);return}
  const r=await api('/api/agent',{action:'render',scope:sc.value,name:name,text:raw.value,values:{description:ds.value,mode:md.value,model:mo.value,temperature:tp.value,steps:st.value,permission:pm.value,prompt:pr.value}});
  toast(r.message);if(r.ok)raw.value=r.text};
 sc.addEventListener('change',()=>{setPerms();updHint();if(isNew)gen().catch(showErr)});
 if(isNew)setTimeout(()=>gen().catch(showErr),0);
 const kopf=isNew?el('div',{},el('div',{class:'grid'},el('div',{},el('label',{},'Name'),nm),el('div',{},el('label',{},'Geltung'),sc))):
  el('div',{},el('div',{class:'bar'},el('b',{},name),el('span',{class:'pill'},scope==='global'?'global':'Projekt: '+scope),
   el('span',{class:'mut'},(d.agents.find(a=>a.name===name&&a.scope===scope)||{}).priority||'')));
 const felder=el('div',{id:'agent-fields'},
  el('label',{},'Beschreibung'),ds,
  el('div',{class:'grid3'},el('div',{},el('label',{},'Modus'),md),el('div',{},el('label',{},'Modell'),mo),el('div',{},el('label',{},'Rechte'),pm)),
  hint,
  el('div',{class:'grid'},el('div',{},el('label',{},'Temperatur'),tp),el('div',{},el('label',{},'Max. Schritte'),st)),
  el('label',{},'Prompt'),pr,unknown,
  el('div',{class:'bar'},isNew?el('button',{class:'b',type:'button',on:{click:()=>gen()}},'Datei aus Eingaben erzeugen'):
   el('button',{class:'b',type:'button',on:{click:()=>apply()}},'In Rohtext übernehmen'),
   el('span',{class:'mut'},'Das Ergebnis unten kann vor dem Speichern frei bearbeitet werden.')));
 const save=async()=>{const n=isNew?nm.value:name,s=isNew?sc.value:scope;
  const payload={action:'save',scope:s,name:n,text:raw.value,create:isNew,expected:digest};
  if(structured){const current=formValues(),changed={};for(const k in current)if(current[k]!==baseline[k])changed[k]=current[k];
   if(Object.keys(changed).length)payload.values=changed}
  const r=await api('/api/agent',payload);toast(r.message);if(r.ok){baseline=formValues();if(isNew)agents().catch(showErr);else{digest=r.digest;raw.value=r.text}}};
 const cp=el('select',{'aria-label':'Kopieren nach …'},el('option',{value:''},'Kopieren nach …'),...['global',...d.projects].filter(x=>x!==scope).map(x=>el('option',{value:x},x==='global'?'global':'Projekt: '+x)));
 const delAgent=isNew?null:el('button',{class:'b d',type:'button',on:{click:()=>askInline(delAgent,'Agent „'+name+'“ löschen? Eine Sicherung bleibt in agent-backups.','Ja, löschen',async()=>{const r=await api('/api/agent',{action:'delete',scope,name});toast(r.message);if(r.ok)agents().catch(showErr)})}},'Löschen');
 const backupBox=el('div',{id:'agent-backups'},el('span',{class:'mut'},'Noch keine Sicherung.'));
 const drawBackups=()=>{backupBox.replaceChildren(...(backups.length?backups.map(b=>{const btn=el('button',{class:'b',type:'button',on:{click:()=>askInline(btn,'Sicherung „'+b+'“ wiederherstellen? Der aktuelle Stand wird vorher gesichert.','Ja, wiederherstellen',async()=>{const r=await api('/api/agent',{action:'restore',scope,name,backup:b});toast(r.message);if(r.ok)agentForm(scope,name).catch(showErr)})}},'Wiederherstellen');
  return el('div',{class:'bar'},el('span',{class:'mut'},b),btn)}):[el('span',{class:'mut'},'Noch keine Sicherung vorhanden.')]))};
 const backupBtn=isNew?null:el('button',{class:'b',type:'button',on:{click:async()=>{const loaded=await api('/api/agent?scope='+encodeURIComponent(scope)+'&name='+encodeURIComponent(name));backups=loaded.backups||[];drawBackups();backupBox.hidden=false;toast(backups.length?backups.length+' Sicherung(en).':'Noch keine Sicherung vorhanden.')}}},'Sicherungen anzeigen');
 main.replaceChildren(el('div',{class:'bar'},el('button',{class:'b',type:'button',on:{click:()=>agents().catch(showErr)}},'← zurück'),el('h2',{style:'margin:0'},isNew?'Neuer Agent':'Agent bearbeiten')),
  el('div',{class:'card'},kopf,felder,el('label',{},'Datei (Frontmatter + Prompt)'),raw,
   el('div',{class:'bar'},el('button',{class:'b p',type:'button',on:{click:save}},'Speichern'),
    isNew?null:cp,isNew?null:el('button',{class:'b',type:'button',on:{click:async()=>{if(!cp.value)return toast('Ziel wählen');const r=await api('/api/agent',{action:'copy',scope,name,to:cp.value});toast(r.message);if(r.ok)setTab('agents')}}},'Kopieren'),
    isNew?null:backupBtn,delAgent)),
  isNew?null:el('div',{class:'card'},el('b',{},'Sicherungen'),el('div',{class:'mut'},'Vor jedem Speichern wird der bisherige Stand gesichert. Die Wiederherstellung sichert zuerst den aktuellen Stand.'),backupBox))}
/* ---------- MCP-Tools ---------- */
async function mcp(){const d=await api('/api/mcp');
 const tb=el('table',{},el('tr',{},...['Name','Geltung','Typ','Ziel','aktiv',''].map(h=>el('th',{},h))));
 d.servers.forEach(s=>{ if(s.error){tb.append(el('tr',{},el('td',{colspan:'6',class:'bad'},s.scope+': Konfiguration nicht lesbar: '+s.error)));return}
  tb.append(el('tr',{},el('td',{},s.name),el('td',{},s.scope==='global'?el('span',{class:'pill ok'},'global'):el('span',{class:'pill'},'Projekt: '+s.scope)),el('td',{},s.type),el('td',{class:'mut'},s.target),el('td',{},badge(s.enabled?'ja':'nein')),
   el('td',{},el('div',{class:'bar',style:'margin:0'},el('button',{class:'b',on:{click:async()=>{const r=await api('/api/mcp',{action:'test',scope:s.scope,name:s.name});mcpResult(r)}}},'Testen'),
    el('button',{class:'b',on:{click:()=>mcpForm(s.scope,s.name).catch(showErr)}},'Bearbeiten'),
    el('button',{class:'b',on:{click:async()=>{const r=await api('/api/mcp',{action:'toggle',scope:s.scope,name:s.name});toast(s.name+' '+r.message);mcp().catch(showErr)}}},s.enabled?'Ausschalten':'Einschalten')))))});
 const layouts=[...new Set(d.servers.filter(s=>s.layout).map(s=>s.scope+': '+s.layout+' → '+s.path))];
 main.replaceChildren(el('div',{class:'card'},el('div',{class:'bar'},el('b',{},'MCP-Server (Model Context Protocol)'),el('button',{class:'b p',on:{click:()=>mcpForm(null,null).catch(showErr)}},'Neuer MCP-Server')),
  d.servers.length?tb:el('span',{class:'mut'},'Keine MCP-Server konfiguriert.'),
  el('div',{class:'mut',style:'margin-top:8px'},'MCP-Server geben dem Agenten zusätzliche Werkzeuge (z. B. Notizen, Datenbanken, Dokumentation). Die Werkzeuge belegen Kontext und kosten dadurch Tokens: nur aktivieren, was gebraucht wird. Geheimnisse (Token, Schlüssel) werden hier maskiert; beim Speichern bleiben sie unverändert.'),
  el('div',{class:'mut'},'Verbindungstest: startet bei local ein Programm und stellt bei remote eine Netzverbindung her. Unterstützt werden local (stdio) und remote (Streamable HTTP); andere Transporte werden nicht getestet. Geprüft werden nur initialize und tools/list, keine fachlichen Werkzeuge. OAuth: vibe führt keine Anmeldung durch und liest keine Tokens; bei OAuth-Servern zuerst „opencode mcp auth“ ausführen.'),
  layouts.length?el('div',{class:'mut'},'Konfigurationsdateien: '+layouts.join(' | ')):null),el('div',{id:'mcpres'}))}
function mcpResult(r,into){const t=r.result;const box=into||document.getElementById('mcpres');if(!box)return toast(r.message);
 box.replaceChildren(el('div',{class:'card '+(t&&t.ok?'':'err')},el('b',{class:t&&t.ok?'ok':'bad'},t?(t.ok?'Test bestanden':'Test fehlgeschlagen'):'Fehler'),r.ok?null:el('div',{class:'bad'},r.message),
  t&&t.warning?el('div',{class:'warn'},'Hinweis: '+t.warning):null,
  t&&t.transport?el('div',{class:'mut'},'Transport: '+t.transport):null,
  t&&t.category?el('div',{class:'mut'},'Fehlerart: '+t.category):null,
  t&&t.server&&t.server.name?el('div',{class:'mut'},'Server: '+t.server.name+' '+(t.server.version||'')):null,...(t?t.steps.map(s=>el('div',{class:'mut'},'✓ '+s)):[]),...(t&&t.notes?t.notes.map(n=>el('div',{class:'mut'},'ℹ '+n)):[]),
  t&&t.error?el('div',{class:'bad'},t.error):null,t&&t.hint?el('div',{class:'warn'},'Hinweis: '+t.hint):null,
  t&&t.tools&&t.tools.length?el('div',{},el('b',{},t.tools.length+' Werkzeuge'),el('ul',{class:'l'},t.tools.map(x=>el('li',{},el('b',{},x.name),x.description?' – '+x.description:'')))):null))}
const lines=s=>s.split('\n').map(x=>x.trim()).filter(Boolean);
const kv=(s,sep)=>{const o={};lines(s).forEach(l=>{const i=l.indexOf(sep);if(i>0)o[l.slice(0,i).trim()]=l.slice(i+1).trim()});return o};
const unkv=(o,sep)=>Object.entries(o||{}).map(([a,b])=>a+sep+b).join('\n');
async function mcpForm(scope,name){const d=await api('/api/mcp');let e={type:'local',command:[],enabled:true},digest=null;
 if(name){const loaded=await api('/api/mcp_entry?scope='+encodeURIComponent(scope)+'&name='+encodeURIComponent(name));e=loaded.entry;digest=loaded.digest}
 const isNew=!name;const nm=el('input',{value:name||'',placeholder:'name (Buchstaben, Ziffern, _ -)'});
 const sc=el('select',{},el('option',{value:'global'},'global (alle Projekte)'),...d.projects.map(p=>el('option',{value:p},'Projekt: '+p)));sc.value=scope||'global';if(!isNew)sc.setAttribute('disabled','disabled');
 const ty=el('select',{},el('option',{value:'local'},'local (Programm starten, stdio)'),el('option',{value:'remote'},'remote (URL, Streamable HTTP)'));ty.value=e.type||'local';
 const cmd=el('textarea',{rows:4,placeholder:'ein Argument pro Zeile, z. B.\nnpx\n-y\n@modelcontextprotocol/server-everything'});cmd.value=(e.command||[]).join('\n');
 const envv=el('textarea',{rows:3,placeholder:'NAME=Wert (eine pro Zeile; {env:VARIABLE} erlaubt)'});envv.value=unkv(e.environment,'=');
 const cwd=el('input',{value:e.cwd||'',placeholder:'optional'});
 const url=el('input',{value:e.url||'',placeholder:'https://…/mcp'});
 const hdr=el('textarea',{rows:3,placeholder:'Name: Wert (eine pro Zeile, z. B. Authorization: Bearer {env:TOKEN})'});hdr.value=unkv(e.headers,': ');
 const noauth=el('input',{type:'checkbox'});noauth.checked=e.oauth===false;
 const en=el('input',{type:'checkbox'});en.checked=e.enabled!==false;
 const to=el('input',{value:String(e.timeout||''),placeholder:'ms, Standard 30000'});
 const loc=el('div',{},el('label',{},'Befehl (Programm und Argumente)'),cmd,el('label',{},'Umgebungsvariablen'),envv,el('label',{},'Arbeitsordner'),cwd);
 const rem=el('div',{},el('label',{},'URL'),url,el('label',{},'Header'),hdr,el('label',{},el('span',{},'OAuth abschalten (für Server mit Schlüssel im Header) '),noauth));
 const show=()=>{loc.style.display=ty.value==='local'?'block':'none';rem.style.display=ty.value==='remote'?'block':'none'};ty.addEventListener('change',show);show();
 const build=()=>{const o={type:ty.value};if(ty.value==='local'){o.command=lines(cmd.value);const ev=kv(envv.value,'=');if(Object.keys(ev).length)o.environment=ev;if(cwd.value.trim())o.cwd=cwd.value.trim()}
  else{o.url=url.value.trim();const hv=kv(hdr.value,':');if(Object.keys(hv).length)o.headers=hv;if(noauth.checked)o.oauth=false;else if(e.oauth&&typeof e.oauth==='object')o.oauth=e.oauth}
  o.enabled=en.checked;if(to.value.trim())o.timeout=parseInt(to.value,10);return o};
 const res=el('div',{});
 const delMcp=isNew?null:el('button',{class:'b d',on:{click:()=>askInline(delMcp,'MCP-Server „'+name+'“ löschen?','Ja, löschen',async()=>{const r=await api('/api/mcp',{action:'delete',scope,name});toast(r.message);if(r.ok)mcp().catch(showErr)})}},'Löschen');
 main.replaceChildren(el('div',{class:'bar'},el('button',{class:'b',on:{click:()=>mcp().catch(showErr)}},'← zurück'),el('h2',{style:'margin:0'},isNew?'Neuer MCP-Server':'MCP-Server bearbeiten')),
  el('div',{class:'card'},el('div',{class:'grid'},el('div',{},el('label',{},'Name (Werkzeuge erscheinen mit diesem Präfix)'),nm),el('div',{},el('label',{},'Geltung'),sc)),
   el('div',{class:'grid'},el('div',{},el('label',{},'Typ'),ty),el('div',{},el('label',{},'Timeout (ms)'),to)),loc,rem,el('label',{},el('span',{},'aktiv '),en),
   el('div',{class:'mut',style:'margin-top:6px'},'Maskierte Werte (***) bleiben beim Speichern unverändert. Zum Ändern den ganzen Wert neu eintragen.'),
   el('div',{class:'mut'},'Beim Testen wird ein Programm gestartet (local) oder eine Netzverbindung hergestellt (remote). Der Test ruft nur initialize und tools/list auf, keine fachlichen Werkzeuge. OAuth-Anmeldungen führt vibe nicht durch.'),
   el('div',{class:'bar'},el('button',{class:'b p',on:{click:async()=>{const r=await api('/api/mcp',{action:'save',scope:isNew?sc.value:scope,name:nm.value,old_name:isNew?'':name,create:isNew,entry:build(),expected:digest});toast(r.message);if(r.ok)mcp().catch(showErr)}}},'Speichern'),
    el('button',{class:'b',on:{click:async()=>{res.replaceChildren(el('div',{class:'mut'},'Teste … (kann bis zu einer Minute dauern, z. B. wenn npx Pakete lädt)'));const r=await api('/api/mcp',{action:'test',scope:isNew?sc.value:scope,name:isNew?'':name,entry:build()});mcpResult(r,res)}}},'Testen (mit den Werten oben)'),
    delMcp)),res)}
async function env(){const d=await api('/api/doctor');const f=await api('/api/fritz');
 main.replaceChildren(el('div',{class:'card'},el('b',{},'Umgebungsprüfung'),...d.map(c=>el('div',{},el('span',{class:c.ok?'ok':'bad'},c.ok?'OK   ':'FEHL '),c.label,c.ok||!c.hint?null:el('span',{class:'mut'},'  → '+c.hint)))),fritzCard(f))}
function fritzCard(f){
 const cb=el('input',{type:'checkbox'});cb.checked=!!f.automation;
 const state=el('span',{class:'pill '+(f.automation?'warn':'mut')},'Automatik: '+(f.automation?'an':'aus'));
 const ready=el('span',{class:'pill '+(f.ready?'ok':'bad')},f.ready?'bereit':'nicht bereit');
 const resultBox=el('div',{});
 const recon=el('button',{class:'b p'},'Jetzt neu verbinden');
 recon.disabled=!f.ready;
 recon.addEventListener('click',()=>askInline(recon,'FRITZ!Box neu verbinden? Die Internetverbindung wird kurz getrennt; alle Geräte im Netz sind betroffen.','Ja, verbinden',async()=>{
  recon.disabled=true;resultBox.replaceChildren(el('div',{class:'mut'},'Reconnect läuft … (die FRITZ!Box prüft bis zu drei Minuten auf eine neue IP)'));
  try{const r=await api('/api/fritz',{action:'reconnect'});
   resultBox.replaceChildren(el('div',{class:'card '+(r.ok?'':'err')},el('b',{class:r.ok?'ok':'bad'},r.ok?'Reconnect erfolgreich':'Reconnect fehlgeschlagen'),
    el('pre',{style:'white-space:pre-wrap;margin:8px 0 0'},(r.result&&r.result.output)||r.message||'')))}catch(e){resultBox.replaceChildren(el('div',{class:'card err'},String(e&&e.message||e)))}finally{recon.disabled=!f.ready}}));
 return el('div',{class:'card'},el('div',{class:'bar'},el('b',{},'Fritzbox-Reconnect'),state,ready,recon),
  el('div',{class:'mut'},'Optionale Altintegration: Nach einem fehlgeschlagenen Agentenlauf kann eine neue Internet-IP angefordert werden (z. B. nach einem Anbieter-Limit). Ein Reconnect trennt die Internetverbindung der FRITZ!Box kurz; das betrifft alle Geräte im Netz. Die Automatik ist standardmäßig aus und greift nur nach einem Fehler, nie während eines laufenden Pakets.'),
  el('div',{class:'mut'},'Konfiguration: '+f.env+' (nicht im Repository)'+(f.configured?' – vorhanden':' – fehlt oder unvollständig')),
  el('div',{class:'mut'},'Helfer: '+f.script+(f.script_ok?'':' (fehlt)')+' · Python: '+(f.python||'nicht gefunden')+(f.python_ok?'':' (nicht ausführbar)')+' · Voraussetzung: fritzconnection im Python installiert'),
  el('div',{class:'bar'},el('label',{style:'margin:0'},el('span',{},' Automatik nach fehlgeschlagenem Agentenlauf '),cb),
   el('button',{class:'b',on:{click:async()=>{const r=await api('/api/fritz',{action:'automation',enabled:cb.checked});toast(r.message);if(r.ok)env().catch(showErr)}}},'Automatik übernehmen')),
  resultBox)}
window.addEventListener('unhandledrejection',e=>showErr(e.reason));
setTab('projects');
</script></body></html>"""

def page():
    """Liefert die Oberfläche mit dem aufgelösten opencode-Port.

    Der Port ist konfigurierbar; ein fest eingetragener Link würde bei
    abweichender Konfiguration ins Leere zeigen.
    """
    return PAGE.replace("__OPENCODE_URL__", vibe.OC_URL)

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
