"""Unit-Abnahme B14: Live-Ausgabe der Subagenten über den privaten Laufserver.

FEEDBACK.md B14 „Subagenten output statisch“ (Bug): Die Ausgabefenster der
Subagenten bleiben beim ersten erfassten Text stehen. Belegte Ursache (nach
eigenem Nachprüfen der Stellen): ``live_subagent_output()`` (Kartenausgabe)
und ``live_subagents()`` (Subagentenerkennung) fragen über
``opencode_request()`` stets den gemeinsamen Server (``vibe.OC_URL``) mit dem
globalen Kennwort. Läuft kein gemeinsamer Server (Normalfall), scheitert die
Live-Abfrage (Verbindung abgewiesen → ``None``) und der Endpunkt
``/api/subagent-output`` fällt auf die in ``<Laufprotokoll>.state.json``
erfasste Ausgabe zurück — genau den statischen Ersttext. B13 liefert mit
``steer_endpoint(name)`` bereits die Auflösung des privaten Laufendpunkts
(``<Laufprotokoll>.server.json`` mit Loopback-URL und Kennwort aus der dort
genannten ``password_file``); genau diese Semantik wird hier für die
Live-Lesezugriffe gefordert.

Vereinbarter Vertrag (umsetzungsneutral, geprüft über die HTTP-Endpunkte des
echten Dashboards ``bin/vibe-web.py``):

1. Live-Lesezugriffe fragen für einen aktiven Lauf zuerst den Endpunkt
   dieses Laufs an (Loopback-URL und Kennwort aus ``password_file`` der
   Serverdatei), sonst Rückfall auf den gemeinsamen Server mit dem
   globalen Kennwort. [AK1, AK2, AK5]
2. Ohne Serverdatei und ohne verwertbaren gemeinsamen Server bleibt das
   bisherige Verhalten: erfasster Fallback-Text, ok:false bei leerer
   Ausgabe, keine erfundenen Daten. [AK3]
3. Defekte oder fremde (nicht-Loopback) Serverdatei-Inhalte werden nicht
   angefragt; Rückfall wie ``steer_endpoint``. [AK4]
4. Das Kennwort erscheint in keiner API-Antwort und keinem Protokoll. [AK8]
5. Zwei gleichzeitig „aktive“ Projekte erhalten jeweils ihren eigenen
   Endpunkt (Projektkontext korrekt). [AK6]

Testfälle mit Zuordnung:

1. test_live_output_comes_from_the_run_server_endpoint            [AK1]
   Vorbedingung: aktiver Lauf mit laufendem Subagenten samt statischer
   erfasster Ausgabe; gültige Serverdatei auf den privaten Laufserver;
   gemeinsamer Attrappenserver ohne verwertbare Daten.
   Aktion: GET /api/subagent-output.
   Erwartung: Der LIVE-Text vom Laufserver wird geliefert; der statische
   erfasste Text erscheint nicht.
   Fehlerfall (Ausgangsstand): statischer Fallback-Text.
2. test_second_poll_returns_refreshed_live_output           [AK1, AK7]
   Vorbedingung: wie 1; zwischen zwei Abrufen wächst der LIVE-Text.
   Aktion: Zwei aufeinanderfolgende Abrufe.
   Erwartung: Der zweite Abruf liefert den neuen Text; der alte Text und
   der statische Ersttext frieren nicht ein.
   Fehlerfall (Ausgangsstand): beide Abrufe liefern den statischen Text.
3. test_requests_target_the_loopback_url_with_the_file_password     [AK2]
   Aktion: GET /api/subagent-output mit gültiger Serverdatei, deren
   ``password_file`` ein anderes Kennwort nennt als die globale
   Kennwortdatei.
   Erwartung: Jede Anfrage erreicht den Laufserver mit korrekter
   Basic-Auth „opencode:<Kennwort aus password_file>“.
   Fehlerfall (Ausgangsstand): keine Anfrage am Laufserver.
4. test_no_request_reaches_the_common_server_with_a_valid_file      [AK2]
   Aktion: wie 3.
   Erwartung: Der gemeinsame Server erhält keine /message- und keine
   /api/session-Anfrage.
   Fehlerfall (Ausgangsstand): alle Anfragen gehen an OC_URL.
5. test_without_server_file_the_captured_output_is_served           [AK3]
   Vorbedingung: aktiver Lauf, keine Serverdatei, gemeinsamer
   Attrappenserver erreichbar (ohne verwertbare Daten).
   Aktion: GET /api/subagent-output.
   Erwartung: ok:true mit der erfassten Ausgabe; die Abfrage ging an den
   gemeinsamen Server (bisheriger Pfad bleibt).
   Fehlerfall: Ausgabeverlust oder erfundene Daten.
6. test_without_server_file_and_without_output_keeps_the_message    [AK3]
   Vorbedingung: wie 5, aber erfasste Ausgabe leer.
   Erwartung: ok:false mit der bestehenden Meldung „liegt noch keine
   Ausgabe vor“ und dem Status.
7. test_without_password_nothing_is_queried_and_captured_text_remains [AK3]
   Vorbedingung: wie 5, aber ohne globale Kennwortdatei; privater
   Laufserver läuft.
   Erwartung: ok:true mit der erfassten Ausgabe; keine Anfrage am
   Laufserver (keine erfundenen Live-Daten).
8. test_broken_json_server_file_is_not_used                         [AK4]
   Vorbedingung: Serverdatei mit defektem JSON; privater Laufserver läuft.
   Erwartung: ok:true mit der erfassten Ausgabe; keine Anfrage am
   Laufserver.
9. test_non_loopback_server_url_is_not_used                         [AK4]
   Vorbedingung: Serverdatei mit URL http://example.invalid:<Port>; lokal
   lauscht ein aufzeichnender Auffangserver am selben Port.
   Erwartung: ok:true mit der erfassten Ausgabe; weder der Auffangserver
   noch der Laufserver wurde angefragt (kein Ersatzloopback).
10. test_server_file_without_usable_url_is_not_used                  [AK4]
    Vorbedingung: Serverdatei nur mit ``password_file`` (fehlender Port).
    Erwartung: ok:true mit der erfassten Ausgabe; keine Laufserver-Anfrage.
11. test_live_subagents_are_discovered_via_the_run_endpoint          [AK5]
    Vorbedingung: aktiver Lauf; der Laufserver meldet eine Kind-Session
    (parentID der Hauptsession) als aktiv; Zustandsdatei ohne Subagenten.
    Aktion: GET /api/subagents.
    Erwartung: Der live erkannte Subagent erscheint mit Status running; die
    Session-Abfragen gingen an den Laufserver.
    Fehlerfall (Ausgangsstand): Subagent fehlt (Abfrage am gemeinsamen
    Server ohne Daten).
12. test_two_active_projects_use_their_own_endpoints                 [AK6]
    Vorbedingung: zwei aktive Projekte mit jeweils eigener Serverdatei auf
    zwei verschiedenen Laufservern mit unterscheidbaren LIVE-Texten.
    Aktion: GET /api/subagent-output für beide Projekte.
    Erwartung: Jedes Projekt erhält seinen eigenen LIVE-Text; jeder
    Laufserver sah nur die Session seines eigenen Projekts.
    Fehlerfall (Ausgangsstand): beide erhalten den statischen Text.
13. test_the_password_stays_secret                                  [AK8]
    Aktion: GET /api/subagent-output mit vollständigem Setup.
    Erwartung: Weder das private noch das globale Kennwort erscheint in
    einer API-Antwort oder in einem Protokoll.

Der gemeinsame opencode-Port ist in dieser Suite ein lauschender,
aufzeichnender Attrappenserver ohne verwertbare Daten: So lässt sich
belegen, dass Anfragen am Ausgangsstand dorthin gehen (Rotphase) und nach
der Umsetzung bei gültiger Serverdatei nicht mehr. Keine echten
Modellaufrufe, keine produktive Installation, keine externen Dienste.
"""
import base64
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"
RUNS_PY = REPO / "bin" / "vibe_runs.py"

MAIN_SESSION = "ses_main"
CHILD_SESSION = "ses_kind"
STATIC_OUTPUT = ("The subagent is working in the background "
                 "(sessionID: ses_kind). STATISCH-4711")
LIVE_TEXT_A = "LIVE-A-4711: Der Subagent schreibt seine erste Fassung."
LIVE_TEXT_B = "LIVE-B-4711: Der Subagent schreibt eine zweite Fassung."
LIVE_TEXT_PROJECT_A = "PROJEKT-A-4711: Live-Ausgabe des ersten Projekts."
LIVE_TEXT_PROJECT_B = "PROJEKT-B-4711: Live-Ausgabe des zweiten Projekts."
PASSWORD_GLOBAL = "global-4711"
PASSWORD_PRIVATE = "privat-4711"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _CommonServerHandler(BaseHTTPRequestHandler):
    """Gemeinsamer Attrappenserver: erreichbar, aber ohne verwertbare Daten.

    Jede Anfrage wird protokolliert; geantwortet wird immer ``{"ok": true}``
    (ein Dict ohne ``data``-Liste) — genau die Lage, bei der die
    Live-Abfragen leer bleiben und der erfasste Fallback-Text greift.
    """

    record_path = ""

    def log_message(self, *args):
        return

    def _record(self):
        with open(self.record_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "method": self.command,
                "path": self.path,
            }, ensure_ascii=False) + "\n")

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._record()
        self._send_json(200, {"ok": True})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self._record()
        self._send_json(200, {"ok": True})


class _RunServerHandler(BaseHTTPRequestHandler):
    """Privater Laufserver-Attrappe mit Kennwortprüfung und Nachrichten.

    Der Kontext trägt ``credential_path`` (Kennwortdatei laut
    ``password_file`` der Serverdatei), ``record_path`` sowie die
    testseitig gesetzten payloads ``messages``, ``sessions`` und ``active``.
    Anfragen werden nur mit korrekter Basic-Auth
    („opencode:<Kennwort aus credential_path>“) als authentifiziert
    vermerkt.
    """

    context = None

    def log_message(self, *args):
        return

    def _auth_ok(self):
        try:
            password = Path(self.context["credential_path"]).read_text(
                encoding="utf-8").strip()
        except OSError:
            return False
        encoded = base64.b64encode(
            ("opencode:" + password).encode()).decode()
        return self.headers.get("Authorization", "") == "Basic " + encoded

    def _record(self):
        with open(self.context["record_path"], "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "method": self.command,
                "path": self.path,
                "auth_ok": self._auth_ok(),
            }, ensure_ascii=False) + "\n")

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._record()
        if self.path == "/api/session/active":
            self._send_json(200, self.context.get("active") or {"data": {}})
            return
        if "/message" in self.path:
            payload = self.context.get("messages") or {"data": []}
            if "order=asc" not in self.path:
                messages = payload.get("data") if isinstance(payload, dict) else []
                payload = {"data": list(reversed(messages or []))}
            self._send_json(200, payload)
            return
        if self.path.startswith("/api/session"):
            self._send_json(200, self.context.get("sessions") or {"data": []})
            return
        self._send_json(200, {"ok": True})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self._record()
        self._send_json(200 if self._auth_ok() else 401,
                        {"ok": self._auth_ok()})


def make_handler(base, **attributes):
    def build():
        handler = type("BoundHandler", (BaseHTTPRequestHandler,), {})
        for name, value in base.__dict__.items():
            if not name.startswith("__"):
                setattr(handler, name, value)
        for name, value in attributes.items():
            setattr(handler, name, value)
        return handler
    return build()


class B14ApiFixture(unittest.TestCase):
    """Echtes Dashboard, isoliertes VIBE-Root, Attrappen-Server."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.projects = {}
        for name in ("proj", "proj2"):
            project = cls.root / name
            (project / ".vibe").mkdir(parents=True)
            (project / ".vibe" / "project.env").write_text(
                "TYPE=generic\nAGENT=test-agent\nTESTER=test-agent\n"
                "REVIEWER=code-reviewer\n", encoding="utf-8")
            (project / "FEEDBACK.md").write_text(
                "# FEEDBACK\n\n- [ ] B14 Subagenten output statisch\n"
                "  Beschreibung: Test\n", encoding="utf-8")
            agent_path = project / ".opencode" / "agents" / "test-agent.md"
            agent_path.parent.mkdir(parents=True)
            agent_path.write_text(
                "---\ndescription: Testagent\nmode: primary\n---\n"
                "Du bist der Coding-Agent der Arbeitspakete.\n",
                encoding="utf-8")
            subprocess.run(["git", "init", "-q", "-b", "main", str(project)],
                           check=True, capture_output=True)
            subprocess.run(["git", "-C", str(project), "config", "user.name",
                            "Test"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(project), "config", "user.email",
                            "test@example.invalid"], check=True,
                           capture_output=True)
            subprocess.run(["git", "-C", str(project), "add", "-A"],
                           check=True, capture_output=True)
            subprocess.run(["git", "-C", str(project), "commit", "-q", "-m",
                            "Ausgangsstand"], check=True, capture_output=True)
            cls.projects[name] = project
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        for name in ("test-agent", "code-reviewer"):
            (cls.agents / (name + ".md")).write_text(
                "---\ndescription: Testagent\nmode: primary\n---\n"
                "Du bist der Coding-Agent der Arbeitspakete.\n",
                encoding="utf-8")
        cls.fakebin = cls.root / "fakebin"
        cls.fakebin.mkdir()
        cls.tmux_log = cls.root / "tmux.log"
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        (cls.root / "tmp").mkdir()
        # Gemeinsamer Attrappenserver (OC_URL): lauschend und aufzeichnend,
        # aber ohne verwertbare Daten — der Fall „kein gemeinsamer Server
        # mit Inhalt“, unter dem der Bug den statischen Text einfriert.
        cls.oc_port = free_port()
        cls.common_record = cls.root / "common-server.requests.jsonl"
        cls._common_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port),
            make_handler(_CommonServerHandler, record_path=str(cls.common_record)))
        cls._common_http.daemon_threads = True
        cls._common_thread = threading.Thread(target=cls._common_http.serve_forever)
        cls._common_thread.daemon = True
        cls._common_thread.start()
        cls.port = free_port()
        cls.web_log_path = cls.root / "web-server.log"
        cls.env = cls.build_env()
        cls.server_log = open(cls.web_log_path, "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=cls.env,
            stdout=cls.server_log, stderr=subprocess.STDOUT, text=True)
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 30
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                            ("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: "
                    + cls.web_log_path.read_text(
                        encoding="utf-8", errors="replace"))
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()

    @classmethod
    def build_env(cls):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_") or key in (
                    "TMUX", "TMUX_PANE"):
                env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_OPENCODE_PORT": str(cls.oc_port),
            "VIBE_INSTALL": str(cls.root / "_toolchain"),
            "VIBE_RUNTIME": str(cls.log_dir),
            "VIBE_STATE": str(cls.state_dir),
            "VIBE_AGENTS_DIR": str(cls.agents),
            "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
            "VIBE_STORAGE_LOCK_DIR": str(cls.home / "locks"),
            "HOME": str(cls.home),
            "XDG_CONFIG_HOME": str(cls.home / ".config"),
            "TMPDIR": str(cls.root / "tmp"),
            "PATH": str(cls.fakebin) + os.pathsep + env.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        return env

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        cls.server_log.close()
        cls._common_http.shutdown()
        cls._common_http.server_close()
        cls._common_thread.join(timeout=5)
        cls.tmp.cleanup()

    # ---------- Helfer ----------

    def setUp(self):
        for path in (self.log_dir / "proj.log.state.json",
                     self.log_dir / "proj.log.server.json",
                     self.log_dir / "proj2.log.state.json",
                     self.log_dir / "proj2.log.server.json",
                     self.log_dir / "runs.json",
                     self.log_dir / "opencode.password",
                     self.state_dir / "harness.json",
                     self.tmux_log,
                     Path(self.common_record)):
            if path.exists():
                path.unlink()
        self.stop_run_servers()
        self.global_password(PASSWORD_GLOBAL)

    def stop_run_servers(self):
        for entry in getattr(self, "privates", {}).values():
            entry["http"].shutdown()
            entry["http"].server_close()
            entry["thread"].join(timeout=5)
            entry["credential"].unlink(missing_ok=True)
        self.privates = {}

    def global_password(self, value):
        path = self.log_dir / "opencode.password"
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
        return path

    def start_run_server(self, key="run"):
        """Startet einen privaten Laufserver mit eigener Kennwortdatei."""
        port = free_port()
        credential = self.root / (key + ".password")
        credential.write_text(PASSWORD_PRIVATE, encoding="utf-8")
        credential.chmod(0o600)
        context = {
            "credential_path": str(credential),
            "record_path": str(self.root / (key + ".requests.jsonl")),
            "messages": {"data": []},
            "sessions": {"data": []},
            "active": {"data": {}},
        }
        httpd = ThreadingHTTPServer(
            ("127.0.0.1", port),
            make_handler(_RunServerHandler, context=context))
        httpd.daemon_threads = True
        thread = threading.Thread(target=httpd.serve_forever)
        thread.daemon = True
        thread.start()
        self.privates[key] = {
            "http": httpd, "thread": thread, "port": port,
            "context": context, "credential": credential,
        }
        return port

    def run_server(self, key="run"):
        return self.privates[key]

    def set_messages(self, payload, key="run"):
        self.run_server(key)["context"]["messages"] = payload

    def set_sessions(self, payload, key="run"):
        self.run_server(key)["context"]["sessions"] = payload

    def set_active(self, payload, key="run"):
        self.run_server(key)["context"]["active"] = payload

    def write_server_file(self, name="proj", url=None, port=None,
                          password_file=None, raw=None):
        """Schreibt die Serverdatei des Laufs (Nachbildung des Läufers)."""
        if raw is None:
            data = {
                "url": url or "http://127.0.0.1:%d" % self.run_server()["port"],
                "port": port if port is not None else self.run_server()["port"],
                "password_file": password_file or str(
                    self.run_server()["credential"]),
            }
            raw = json.dumps(data, ensure_ascii=False)
        path = self.log_dir / (name + ".log.server.json")
        path.write_text(raw, encoding="utf-8")
        return path

    def register_run(self, name="proj", state="running"):
        result = subprocess.run([
            sys.executable, str(RUNS_PY), "start",
            "--runtime", str(self.log_dir),
            "--project", str(self.projects[name].resolve()),
            "--name", name, "--key", name, "--agent", "test-agent",
            "--state", state,
        ], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0,
                         "Vorbedingung Laufregister fehlgeschlagen: "
                         + result.stdout + result.stderr)

    def write_state(self, name="proj", entry_output=STATIC_OUTPUT,
                    session=None):
        session = session or CHILD_SESSION
        entry = {
            "session": session,
            "agent": "tester",
            "description": "tester arbeitet",
            "prompt": "Kurzer Auftrag",
            "status": "running",
            "started": int(time.time()) + 5,
            "ended": 0,
            "output": entry_output,
        }
        (self.log_dir / (name + ".log.state.json")).write_text(
            json.dumps({"session": MAIN_SESSION, "subagents": [entry]},
                       ensure_ascii=False),
            encoding="utf-8")
        return entry

    def request(self, method, path, body=None):
        encoded = (json.dumps(body, ensure_ascii=False).encode("utf-8")
                   if body is not None else None)
        headers = {
            "Host": f"127.0.0.1:{self.port}",
            "X-Token": self.token,
            "Origin": f"http://127.0.0.1:{self.port}",
            "Sec-Fetch-Site": "same-origin",
        }
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.port, timeout=20)
        try:
            connection.request(method, path, body=encoded, headers=headers)
            response = connection.getresponse()
            text = response.read().decode("utf-8", "replace")
            try:
                payload = json.loads(text)
            except ValueError:
                payload = None
            return response.status, payload, text
        finally:
            connection.close()

    def get_output(self, name="proj", session=None):
        session = session or CHILD_SESSION
        return self.request(
            "GET", "/api/subagent-output?name=%s&session=%s" % (name, session))

    def get_subagents(self, name="proj"):
        return self.request("GET", "/api/subagents?name=" + name)

    def common_requests(self):
        path = Path(self.common_record)
        if not path.exists():
            return []
        return [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines()
                if line.strip()]

    def run_server_requests(self, key="run"):
        path = Path(self.run_server(key)["context"]["record_path"])
        if not path.exists():
            return []
        return [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines()
                if line.strip()]

    def message_requests(self, key="run"):
        return [entry for entry in self.run_server_requests(key)
                if entry["method"] == "GET" and "/message" in entry["path"]]

    @staticmethod
    def ok_flag(payload):
        return bool(payload) and payload.get("ok") is True

    @staticmethod
    def message_of(payload):
        if not isinstance(payload, dict):
            return ""
        return str(payload.get("message")
                   or (payload.get("error") or {}).get("message") or "")

    def assert_no_password_leak(self, raw, name="proj"):
        for password in (PASSWORD_PRIVATE, PASSWORD_GLOBAL):
            self.assertNotIn(password, raw,
                             "Ein Kennwort erscheint in der API-Antwort")
        log = self.log_dir / (name + ".log")
        if log.exists():
            self.assertNotIn(
                PASSWORD_PRIVATE, log.read_text(encoding="utf-8"),
                "Das private Kennwort steht im Laufprotokoll")
        if self.web_log_path.exists():
            self.assertNotIn(
                PASSWORD_PRIVATE, self.web_log_path.read_text(
                    encoding="utf-8", errors="replace"),
                "Das private Kennwort steht im Dashboard-Protokoll")


class LiveOutputViaRunEndpointTest(B14ApiFixture):
    """AK1/AK2: LIVE-Ausgabe kommt vom Endpunkt des Laufs."""

    def test_live_output_comes_from_the_run_server_endpoint(self):
        """AK1: Der LIVE-Text vom Laufserver schlägt den statischen Text.

        Vorbedingung: aktiver Lauf mit laufendem Subagenten und nicht
        leerer erfasster Ausgabe; gültige Serverdatei auf den privaten
        Laufserver mit Assistant-Nachricht; gemeinsamer Attrappenserver
        ohne verwertbare Daten.
        Aktion: GET /api/subagent-output.
        Erwartung: ok:true; der Text enthält LIVE-A-4711; STATISCH-4711
        erscheint nicht.
        Fehlerfall (Ausgangsstand): statischer Fallback-Text, weil die
        Live-Abfrage am gemeinsamen Server scheitert.
        """
        self.register_run()
        self.write_state()
        self.start_run_server()
        self.set_messages({"data": [
            {"info": {"role": "assistant"},
             "parts": [{"type": "text", "text": LIVE_TEXT_A}]},
        ]})
        self.write_server_file()

        status, data, raw = self.get_output()

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        text = str((data or {}).get("text") or "")
        self.assertIn("LIVE-A-4711", text,
                      f"LIVE-Text vom Laufserver fehlt: {text!r}")
        self.assertNotIn(
            "STATISCH-4711", text,
            "Der statische erfasste Text wurde statt der LIVE-Ausgabe "
            f"geliefert: {text!r}")
        self.assert_no_password_leak(raw)

    def test_second_poll_returns_refreshed_live_output(self):
        """AK1/AK7: Ein zweiter Abruf liefert den gewachsenen LIVE-Text.

        Vorbedingung: wie AK1; die Attrappe liefert zunächst LIVE-A-4711,
        danach nur noch LIVE-B-4711.
        Aktion: Zwei aufeinanderfolgende Abrufe.
        Erwartung: Der erste Abruf enthält LIVE-A-4711, der zweite
        LIVE-B-4711; der zweite enthält weder LIVE-A-4711 noch
        STATISCH-4711.
        Fehlerfall (Ausgangsstand): Beide Abrufe liefern denselben
        statischen erfassten Text — die Karte friert ein.
        """
        self.register_run()
        self.write_state()
        self.start_run_server()
        self.set_messages({"data": [
            {"info": {"role": "assistant"},
             "parts": [{"type": "text", "text": LIVE_TEXT_A}]},
        ]})
        self.write_server_file()

        status, data, raw = self.get_output()
        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        first = str((data or {}).get("text") or "")
        self.assertIn("LIVE-A-4711", first,
                      f"Erster Abruf ohne LIVE-Text: {first!r}")

        self.set_messages({"data": [
            {"info": {"role": "assistant"},
             "parts": [{"type": "text", "text": LIVE_TEXT_B}]},
        ]})
        status, data, raw = self.get_output()
        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        second = str((data or {}).get("text") or "")
        self.assertIn("LIVE-B-4711", second,
                      f"Zweiter Abruf ist nicht aktualisiert: {second!r}")
        self.assertNotIn(
            "LIVE-A-4711", second,
            f"Der zweite Abruf friert den ersten Text ein: {second!r}")
        self.assertNotIn(
            "STATISCH-4711", second,
            f"Der zweite Abruf fiel auf den statischen Text zurück: "
            f"{second!r}")

    def test_requests_target_the_loopback_url_with_the_file_password(self):
        """AK2: Anfrage geht an die Loopback-URL mit dem password_file-Kennwort.

        Vorbedingung: gültige Serverdatei; ``password_file`` nennt ein
        anderes Kennwort als die globale Kennwortdatei (diese existiert
        ebenfalls); privater Laufserver läuft.
        Aktion: GET /api/subagent-output.
        Erwartung: Mindestens eine /message-Anfrage am Laufserver, jede
        davon mit korrekter Basic-Auth „opencode:<password_file-Kennwort>“
        — nicht mit dem globalen Kennwort.
        Fehlerfall (Ausgangsstand): keine Anfrage am Laufserver; die
        Abfrage läuft mit dem globalen Kennwort gegen OC_URL.
        """
        self.register_run()
        self.write_state()
        self.start_run_server()
        self.set_messages({"data": [
            {"info": {"role": "assistant"},
             "parts": [{"type": "text", "text": LIVE_TEXT_A}]},
        ]})
        self.write_server_file()

        status, data, raw = self.get_output()

        self.assertEqual(200, status, raw)
        requests = self.message_requests()
        self.assertTrue(
            requests,
            "Die LIVE-Ausgabe wurde nicht am Laufserver-Endpunkt angefragt")
        for entry in requests:
            self.assertTrue(
                entry["auth_ok"],
                "Die Anfrage am Laufserver trug nicht das Kennwort aus "
                f"der password_file: {entry}")
        self.assertTrue(
            any("/message" in entry["path"] for entry in requests),
            requests)

    def test_no_request_reaches_the_common_server_with_a_valid_file(self):
        """AK2: Mit gültiger Serverdatei wird OC_URL nicht angefragt.

        Vorbedingung: wie AK2; der gemeinsame Attrappenserver zeichnet auf.
        Aktion: GET /api/subagent-output.
        Erwartung: Der gemeinsame Server erhält keine /message- und keine
        /api/session-Anfrage.
        Fehlerfall (Ausgangsstand): alle Live-Abfragen laufen gegen OC_URL.
        """
        self.register_run()
        self.write_state()
        self.start_run_server()
        self.set_messages({"data": [
            {"info": {"role": "assistant"},
             "parts": [{"type": "text", "text": LIVE_TEXT_A}]},
        ]})
        self.write_server_file()

        status, data, raw = self.get_output()

        self.assertEqual(200, status, raw)
        leaked = [entry for entry in self.common_requests()
                  if "/message" in entry["path"]
                  or entry["path"].startswith("/api/session")]
        self.assertEqual(
            [], leaked,
            "Trotz gültiger Serverdatei wurde der gemeinsame Server "
            f"angefragt: {leaked}")


class WithoutServerFileTest(B14ApiFixture):
    """AK3: Ohne Serverdatei bleibt das bisherige Verhalten unverändert."""

    def test_without_server_file_the_captured_output_is_served(self):
        """AK3: Ohne Serverdatei wird die erfasste Ausgabe geliefert.

        Vorbedingung: aktiver Lauf, keine Serverdatei, gemeinsamer
        Attrappenserver erreichbar (ohne verwertbare Daten), erfasste
        Ausgabe nicht leer.
        Aktion: GET /api/subagent-output.
        Erwartung: ok:true mit der erfassten Ausgabe (STATISCH-4711); der
        gemeinsame Server wurde abgefragt (bisheriger Pfad bleibt).
        Fehlerfall: Ausgabeverlust oder erfundene LIVE-Daten.
        """
        self.register_run()
        self.write_state()

        status, data, raw = self.get_output()

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        text = str((data or {}).get("text") or "")
        self.assertIn("STATISCH-4711", text,
                      f"Erfasste Ausgabe ging verloren: {text!r}")
        self.assertNotIn("LIVE-A-4711", text,
                         f"Erfundene LIVE-Daten: {text!r}")
        self.assertTrue(
            any("/message" in entry["path"] for entry in
                self.common_requests()),
            "Der bisherige Pfad (Abfrage am gemeinsamen Server) wurde "
            "verändert: " + str(self.common_requests()))

    def test_without_server_file_and_without_output_keeps_the_message(self):
        """AK3: Ohne jede Ausgabe bleibt die bestehende klare Meldung.

        Vorbedingung: wie AK3, aber erfasste Ausgabe leer; der gemeinsame
        Server liefert keinen verwertbaren LIVE-Text.
        Aktion: GET /api/subagent-output.
        Erwartung: ok:false; Meldung enthält „liegt noch keine Ausgabe
        vor“; das Statusfeld nennt den Eintragsstatus.
        Fehlerfall: fälschliches ok:true, andere oder leere Meldung.
        """
        self.register_run()
        self.write_state(entry_output="")

        status, data, raw = self.get_output()

        self.assertEqual(200, status, raw)
        self.assertFalse(self.ok_flag(data),
                         f"Leerer Fall wurde als Erfolg gemeldet: {raw}")
        message = self.message_of(data)
        self.assertIn("liegt noch keine Ausgabe vor", message,
                      f"Bestehende Meldung wurde verändert: {message!r}")
        self.assertEqual("running", str((data or {}).get("status") or ""),
                         raw)

    def test_without_password_nothing_is_queried_and_captured_text_remains(self):
        """AK3: Ohne Kennwort keine Abfrage, aber die erfasste Ausgabe bleibt.

        Vorbedingung: aktiver Lauf, keine Serverdatei, keine globale
        Kennwortdatei, privater Laufserver läuft (muss unangetastet
        bleiben), erfasste Ausgabe nicht leer.
        Aktion: GET /api/subagent-output.
        Erwartung: ok:true mit der erfassten Ausgabe; keine Anfrage am
        Laufserver (keine erfundenen LIVE-Daten ohne Anmeldung).
        Fehlerfall: Anfrage ohne/ mit falschem Kennwort oder erfundene
        Daten.
        """
        self.register_run()
        self.write_state()
        self.start_run_server()
        (self.log_dir / "opencode.password").unlink()

        status, data, raw = self.get_output()

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        text = str((data or {}).get("text") or "")
        self.assertIn("STATISCH-4711", text,
                      f"Erfasste Ausgabe ging verloren: {text!r}")
        self.assertEqual([], self.run_server_requests(),
                         "Ohne Kennwort wurde der Laufserver angefragt")


class BrokenServerFileTest(B14ApiFixture):
    """AK4: Defekte oder fremde Serverdatei-Inhalte werden nicht angefragt."""

    def test_broken_json_server_file_is_not_used(self):
        """AK4: Defektes JSON führt zum Rückfall, nicht zur Anfrage.

        Vorbedingung: aktiver Lauf; ``proj.log.server.json`` enthält kein
        gültiges JSON; privater Laufserver läuft.
        Aktion: GET /api/subagent-output.
        Erwartung: ok:true mit der erfassten Ausgabe; keine Anfrage am
        Laufserver.
        Fehlerfall: Die defekte Datei wird trotzdem verwendet.
        """
        self.register_run()
        self.write_state()
        self.start_run_server()
        self.set_messages({"data": [
            {"info": {"role": "assistant"},
             "parts": [{"type": "text", "text": LIVE_TEXT_A}]},
        ]})
        self.write_server_file(raw="{kein json")

        status, data, raw = self.get_output()

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        text = str((data or {}).get("text") or "")
        self.assertIn("STATISCH-4711", text,
                      f"Erfasste Ausgabe ging verloren: {text!r}")
        self.assertEqual([], self.run_server_requests(),
                         "Die defekte Serverdatei wurde trotzdem verwendet")

    def test_non_loopback_server_url_is_not_used(self):
        """AK4: Fremde Hosts werden nicht angefragt, auch nicht am Port.

        Vorbedingung: aktiver Lauf; Serverdatei mit URL
        ``http://example.invalid:<Port>``; lokal lauscht ein
        aufzeichnender Auffangserver am selben Port; privater Laufserver
        läuft.
        Aktion: GET /api/subagent-output.
        Erwartung: ok:true mit der erfassten Ausgabe; weder Auffangserver
        noch Laufserver wurden angefragt (der fremde Host wird nicht still
        durch Loopback ersetzt).
        Fehlerfall: Die fremde URL wird akzeptiert oder es wird „in der
        Nähe“ angefragt.
        """
        self.register_run()
        self.write_state()
        self.start_run_server()

        catch_record = self.root / "catch.requests.jsonl"
        catch_port = free_port()
        catcher = ThreadingHTTPServer(
            ("127.0.0.1", catch_port),
            make_handler(_CommonServerHandler, record_path=str(catch_record)))
        catcher.daemon_threads = True
        thread = threading.Thread(target=catcher.serve_forever)
        thread.daemon = True
        thread.start()
        try:
            self.write_server_file(
                url="http://example.invalid:%d" % catch_port,
                port=catch_port)

            status, data, raw = self.get_output()
        finally:
            catcher.shutdown()
            catcher.server_close()
            thread.join(timeout=5)

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        text = str((data or {}).get("text") or "")
        self.assertIn("STATISCH-4711", text,
                      f"Erfasste Ausgabe ging verloren: {text!r}")
        self.assertFalse(
            catch_record.exists(),
            "Am Port der fremden URL wurde lokal angefragt: "
            + (catch_record.read_text(encoding="utf-8")
               if catch_record.exists() else "(keine Aufzeichnung)"))
        self.assertEqual([], self.run_server_requests(),
                         self.run_server_requests())

    def test_server_file_without_usable_url_is_not_used(self):
        """AK4: Serverdatei ohne URL/Port wird nicht angenommen.

        Vorbedingung: aktiver Lauf; Serverdatei nur mit ``password_file``
        (keine URL, kein Port); privater Laufserver läuft.
        Aktion: GET /api/subagent-output.
        Erwartung: ok:true mit der erfassten Ausgabe; keine Anfrage am
        Laufserver.
        Fehlerfall: Der fehlende Port wird still ergänzt oder es wird
        trotzdem angefragt.
        """
        self.register_run()
        self.write_state()
        self.start_run_server()
        self.set_messages({"data": [
            {"info": {"role": "assistant"},
             "parts": [{"type": "text", "text": LIVE_TEXT_A}]},
        ]})
        self.write_server_file(raw=json.dumps(
            {"password_file": str(self.run_server()["credential"])}))

        status, data, raw = self.get_output()

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        text = str((data or {}).get("text") or "")
        self.assertIn("STATISCH-4711", text,
                      f"Erfasste Ausgabe ging verloren: {text!r}")
        self.assertEqual([], self.run_server_requests(),
                         self.run_server_requests())


class SubagentDiscoveryTest(B14ApiFixture):
    """AK5: Die Subagentenerkennung nutzt denselben Lauf-Endpunkt."""

    def test_live_subagents_are_discovered_via_the_run_endpoint(self):
        """AK5: Live erkannte Kind-Sessions kommen vom Laufserver.

        Vorbedingung: aktiver Lauf; Zustandsdatei ohne Subagenten; der
        Laufserver meldet eine Kind-Session (parentID der Hauptsession) in
        der Session-Liste und führt sie als aktiv; gemeinsamer
        Attrappenserver ohne Daten.
        Aktion: GET /api/subagents.
        Erwartung: Der live erkannte Subagent erscheint mit Status
        running; die Session-Abfragen gingen an den Laufserver (mit
        Kennwort aus password_file).
        Fehlerfall (Ausgangsstand): Der Subagent fehlt, weil die
        Erkennung am gemeinsamen Server ohne Daten scheitert.
        """
        self.register_run()
        self.write_state()
        self.start_run_server()
        now_ms = int(time.time() * 1000)
        self.set_sessions({"data": [
            {"id": "ses_live", "parentID": MAIN_SESSION,
             "title": "live entdeckt", "agent": {"name": "tester"},
             "time": {"created": now_ms, "updated": now_ms}},
        ]})
        self.set_active({"data": {"ses_live": {"type": "running"}}})
        self.write_server_file()

        status, data, raw = self.get_subagents()

        self.assertEqual(200, status, raw)
        entries = (data or {}).get("subagents")
        self.assertIsInstance(entries, list, raw)
        found = [entry for entry in entries
                 if entry.get("session") == "ses_live"]
        self.assertTrue(
            found, f"Der live erkannte Subagent fehlt: {raw}")
        self.assertEqual("running", found[0].get("status"), raw)
        session_requests = [
            entry for entry in self.run_server_requests()
            if entry["path"].startswith("/api/session")]
        self.assertTrue(
            session_requests,
            "Die Subagentenerkennung wurde nicht am Laufserver-Endpunkt "
            "angefragt: " + str(self.run_server_requests()))
        for entry in session_requests:
            self.assertTrue(
                entry["auth_ok"],
                f"Erkennungs-Anfrage ohne password_file-Kennwort: {entry}")


class TwoProjectsTest(B14ApiFixture):
    """AK6: Zwei aktive Projekte erhalten jeweils ihren eigenen Endpunkt."""

    def test_two_active_projects_use_their_own_endpoints(self):
        """AK6: Der Projektkontext (name) steuert die Endpunktwahl.

        Vorbedingung: zwei aktive Projekte (proj, proj2) mit jeweils
        eigener Zustandsdatei, eigener Serverdatei und eigenem Laufserver;
        die Laufserver liefern unterscheidbare LIVE-Texte.
        Aktion: GET /api/subagent-output für beide Projekte.
        Erwartung: proj erhält PROJEKT-A-4711, proj2 erhält
        PROJEKT-B-4711; jeder Laufserver sah nur die /message-Anfrage des
        eigenen Projekts.
        Fehlerfall (Ausgangsstand): beide Projekte erhalten den statischen
        Text bzw. den falschen Endpunkt.
        """
        self.register_run("proj")
        self.register_run("proj2")
        self.write_state("proj", session="ses_a")
        self.write_state("proj2", session="ses_b")
        self.start_run_server("a")
        self.start_run_server("b")
        self.set_messages({"data": [
            {"info": {"role": "assistant"},
             "parts": [{"type": "text", "text": LIVE_TEXT_PROJECT_A}]},
        ]}, key="a")
        self.set_messages({"data": [
            {"info": {"role": "assistant"},
             "parts": [{"type": "text", "text": LIVE_TEXT_PROJECT_B}]},
        ]}, key="b")
        self.write_server_file(name="proj", url="http://127.0.0.1:%d"
                               % self.run_server("a")["port"],
                               port=self.run_server("a")["port"],
                               password_file=str(
                                   self.run_server("a")["credential"]))
        self.write_server_file(name="proj2", url="http://127.0.0.1:%d"
                               % self.run_server("b")["port"],
                               port=self.run_server("b")["port"],
                               password_file=str(
                                   self.run_server("b")["credential"]))

        status_a, data_a, raw_a = self.get_output("proj", session="ses_a")
        status_b, data_b, raw_b = self.get_output("proj2", session="ses_b")

        self.assertEqual(200, status_a, raw_a)
        self.assertEqual(200, status_b, raw_b)
        text_a = str((data_a or {}).get("text") or "")
        text_b = str((data_b or {}).get("text") or "")
        self.assertIn("PROJEKT-A-4711", text_a,
                      f"Projekt A erhielt den falschen Text: {text_a!r}")
        self.assertIn("PROJEKT-B-4711", text_b,
                      f"Projekt B erhielt den falschen Text: {text_b!r}")
        self.assertNotIn("PROJEKT-B-4711", text_a, text_a)
        self.assertNotIn("PROJEKT-A-4711", text_b, text_b)
        self.assertTrue(self.message_requests("a"),
                        "Projekt A wurde nicht an seinem Endpunkt angefragt")
        self.assertTrue(self.message_requests("b"),
                        "Projekt B wurde nicht an seinem Endpunkt angefragt")
        for entry in self.message_requests("a"):
            self.assertIn("ses_a", entry["path"], entry)
        for entry in self.message_requests("b"):
            self.assertIn("ses_b", entry["path"], entry)
        self.assert_no_password_leak(raw_a, "proj")
        self.assert_no_password_leak(raw_b, "proj2")


class PasswordSecrecyTest(B14ApiFixture):
    """AK8: Kennwortgeheimhaltung wie bisher."""

    def test_the_password_stays_secret(self):
        """AK8: Kein Kennwort in Antworten oder Protokollen.

        Vorbedingung: vollständiges Setup mit gültiger Serverdatei und
        privatem Laufserver; globale Kennwortdatei ebenfalls gesetzt.
        Aktion: GET /api/subagent-output.
        Erwartung: ok:true mit LIVE-Text; weder das private noch das
        globale Kennwort erscheint in der Antwort, im Lauf- oder im
        Dashboard-Protokoll oder in den aufgezeichneten Serveranfragen.
        Fehlerfall: Kennwortleak in einem der Kanäle.
        """
        self.register_run()
        self.write_state()
        self.start_run_server()
        self.set_messages({"data": [
            {"info": {"role": "assistant"},
             "parts": [{"type": "text", "text": LIVE_TEXT_A}]},
        ]})
        self.write_server_file()

        status, data, raw = self.get_output()

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        self.assertIn("LIVE-A-4711", str((data or {}).get("text") or ""), raw)
        self.assert_no_password_leak(raw)
        records = self.run_server_requests()
        self.assertTrue(records, "Der Laufserver wurde nicht angefragt")
        for entry in records:
            blob = json.dumps(entry, ensure_ascii=False)
            self.assertNotIn(PASSWORD_PRIVATE, blob,
                             f"Kennwort in Serveraufzeichnung: {blob}")
            self.assertNotIn(PASSWORD_GLOBAL, blob,
                             f"Kennwort in Serveraufzeichnung: {blob}")


if __name__ == "__main__":
    unittest.main()
