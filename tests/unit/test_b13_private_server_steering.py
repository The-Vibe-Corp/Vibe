"""Unit-Abnahme B13 (Teil 2): Zusatzanweisungen an den privaten Server.

Arbeitspaket B13 „Anweisung senden gibt Fehler“ (Bug): Das Dashboard sendete
POST /api/steer immer an den gemeinsamen opencode-Server; bei Läufen mit
privatem Server (kein gemeinsamer Server erreichbar) kam es zu
„Der opencode-Server ist nicht erreichbar: [Errno 111] Connection refused“.
Vereinbartes Verhalten (umsetzungsneutral):

* POST /api/steer löst zuerst den Endpunkt des aktiven Laufs aus
  ``<Laufprotokoll>.server.json`` auf und sendet POST
  ``/api/session/<id>/prompt`` mit Basic-Auth ``opencode:<Kennwort aus
  password_file>`` dorthin. Akzeptiert werden nur Loopback-URLs
  (http://127.0.0.1 | localhost | ::1) mit gültigem Port. [AK3]
* Defekte oder fremde Serverdateien (defektes JSON, fehlender Port,
  nicht-Loopback-Host) werden nicht angenommen; das Verhalten fällt auf den
  bisherigen Pfad zurück bzw. lehnt verständlich ab. [AK8]
* Ohne Serverdatei gilt der bisherige Pfad (gemeinsamer Server + globale
  Kennwortdatei) unverändert. [AK4, Rückfall]
* Ohne/leerer Kennwortdatei bleibt die verständliche Ablehnung. [AK4]
* Pi bleibt unangetastet: keine privaten Server, bekannte Ablehnung. [AK7]
* Das Kennwort erscheint in keiner Antwort und keinem Protokoll.

Das echte Dashboard (bin/vibe-web.py) läuft isoliert; der gemeinsame
opencode-Port ist ein gebundener, lauschloser Socket (zuverlässig
abgewiesen), der private Server des Laufs ein lokaler Testserver. Keine
Modellaufrufe, keine externen Dienste.
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
CHILD_SESSION = "ses_child"
FOREIGN_SESSION = "ses_fremd"
STEER_TEXT = "B13: Bitte das Paket F19 nachziehen"
PASSWORD = "b13-privat-4711"
SERVER_CREDENTIAL = PASSWORD


class _PrivateServerHandler(BaseHTTPRequestHandler):
    """Lokaler „privater opencode-Server“ des aktiven Laufs.

    Alle Anfragen werden protokolliert; nur mit korrekter Basic-Auth-
    Anmeldung ``opencode:<Kennwort aus credential_path>`` antwortet er mit
    200, sonst mit 401.
    """

    context = None

    def log_message(self, *args):
        return

    def _record(self, body=""):
        with open(self.context["record_path"], "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "method": self.command,
                "path": self.path,
                "auth_ok": self._auth_ok(),
                "body": body,
            }, ensure_ascii=False) + "\n")

    def _auth_ok(self):
        try:
            password = Path(self.context["credential_path"]).read_text(
                encoding="utf-8").strip()
        except OSError:
            return False
        encoded = base64.b64encode(("opencode:" + password).encode()).decode()
        return self.headers.get("Authorization", "") == "Basic " + encoded

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._record()
        self._send_json(200, {"ok": self._auth_ok()})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        self._record(body)
        self._send_json(200 if self._auth_ok() else 401, {"ok": self._auth_ok()})


def make_private_handler(context):
    def build():
        handler = type("BoundHandler", (BaseHTTPRequestHandler,), {})
        for attribute, value in _PrivateServerHandler.__dict__.items():
            if not attribute.startswith("__"):
                setattr(handler, attribute, value)
        handler.context = context
        return handler
    return build()


FAKE_TMUX = r'''#!/usr/bin/env python3
"""Zeichnet tmux-Aufrufe auf; verhält sich wie ein frischer Server."""
import json
import os
import sys

args = sys.argv[1:]
if args[:1] == ["-L"] and len(args) > 1:
    args = args[2:]
path = os.environ.get("FAKE_TMUX_LOG")
if path:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"args": args}, ensure_ascii=False) + "\n")
if args[:1] == ["has-session"]:
    sys.exit(1)
if args[:1] == ["show-environment"]:
    sys.stdout.write("unknown variable: VIBE_MANAGED\n")
    sys.exit(1)
sys.exit(0)
'''


class B13SteerFixture(unittest.TestCase):
    """Dashboard mit totem gemeinsamen Server und privatem Testserver."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        cls.project.mkdir()
        (cls.project / ".vibe").mkdir()
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=test-agent\nTESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL="true"\n',
            encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] B13 Steuerung\n  Beschreibung: Test\n",
            encoding="utf-8")
        agent_path = cls.project / ".opencode" / "agents" / "test-agent.md"
        agent_path.parent.mkdir(parents=True)
        agent_path.write_text(
            "---\ndescription: Testagent\nmode: primary\n---\n"
            "Du bist der Coding-Agent der Arbeitspakete.\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", "-b", "main", str(cls.project)],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", cls.project, "config", "user.name",
                        "Test"], check=True, capture_output=True)
        subprocess.run(["git", "-C", cls.project, "config", "user.email",
                        "test@example.invalid"], check=True, capture_output=True)
        subprocess.run(["git", "-C", cls.project, "add", "-A"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", cls.project, "commit", "-q", "-m",
                        "Ausgangsstand"], check=True, capture_output=True)
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
        tmux = cls.fakebin / "tmux"
        tmux.write_text(FAKE_TMUX, encoding="utf-8")
        tmux.chmod(0o755)
        cls.tmux_log = cls.root / "tmux.log"
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        # Toter gemeinsamer Server: gebundener Socket ohne listen(); alle
        # Verbindungen dorthin werden zuverlässig abgewiesen (Bug-Nachbild).
        cls.dead_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cls.dead_socket.bind(("127.0.0.1", 0))
        cls.dead_port = cls.dead_socket.getsockname()[1]
        # Privater Server des Laufs (Testprozess-Thread).
        cls.priv_port = None
        cls.context = {
            "credential_path": str(cls.log_dir / "opencode.password"),
            "record_path": str(cls.root / "private-server.requests.jsonl"),
        }
        cls.port = cls.free_port()
        cls.web_log_path = cls.root / "web-server.log"
        cls.env = cls.build_env()
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=cls.env,
            stdout=open(cls.web_log_path, "w", encoding="utf-8"),
            stderr=subprocess.STDOUT, text=True)
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
    def free_port(cls):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    @classmethod
    def build_env(cls):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_") or key in (
                    "TMUX", "TMUX_PANE"):
                env.pop(key, None)
        (cls.root / "tmp").mkdir(exist_ok=True)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_OPENCODE_PORT": str(cls.dead_port),
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
            "FAKE_TMUX_LOG": str(cls.tmux_log),
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
        cls.dead_socket.close()
        cls.tmp.cleanup()

    # ---------- Helfer ----------

    def setUp(self):
        for path in (self.log_dir / "proj.log.state.json",
                     self.log_dir / "proj.log.server.json",
                     self.log_dir / "runs.json",
                     self.state_dir / "harness.json",
                     self.tmux_log,
                     Path(self.context["record_path"]),
                     Path(self.context["credential_path"])):
            if path.exists():
                path.unlink()
        if self.priv_port is not None:
            self.stop_private_server()

    def start_private_server(self):
        """Startet den lokalen privaten Server auf einem freien Port."""
        port = self.free_port()
        self.priv_http = ThreadingHTTPServer(
            ("127.0.0.1", port), make_private_handler(self.context))
        self.priv_http.daemon_threads = True
        self.priv_thread = threading.Thread(target=self.priv_http.serve_forever)
        self.priv_thread.daemon = True
        self.priv_thread.start()
        self.priv_port = port
        return port

    def stop_private_server(self):
        self.priv_http.shutdown()
        self.priv_http.server_close()
        self.priv_thread.join(timeout=5)
        self.priv_port = None

    def password_file(self):
        return self.log_dir / "opencode.password"

    def write_password(self, value=PASSWORD):
        path = self.password_file()
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
        return path

    def server_file(self):
        return self.log_dir / "proj.log.server.json"

    def write_server_file(self, url=None, port=None, password_file=None,
                          raw=None):
        """Schreibt die Serverdatei des aktiven Laufs (Läufer-Nachbildung)."""
        if raw is None:
            data = {
                "url": url or "http://127.0.0.1:%d" % self.priv_port,
                "port": port if port is not None else self.priv_port,
                "password_file": password_file
                or str(self.password_file()),
            }
            raw = json.dumps(data, ensure_ascii=False)
        self.server_file().write_text(raw, encoding="utf-8")
        return self.server_file()

    def register_run(self, state="running"):
        result = subprocess.run([
            sys.executable, str(RUNS_PY), "start",
            "--runtime", str(self.log_dir),
            "--project", str(self.project.resolve()),
            "--name", "proj", "--key", "proj", "--agent", "test-agent",
            "--state", state,
        ], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0,
                         "Vorbedingung Laufregister fehlgeschlagen: "
                         + result.stdout + result.stderr)

    def write_state(self, data):
        path = self.log_dir / "proj.log.state.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def running_entry(self, session, agent, started):
        return {
            "session": session,
            "agent": agent,
            "description": agent + " arbeitet",
            "prompt": "Kurzer Auftrag",
            "status": "running",
            "started": int(started),
            "ended": 0,
            "output": "",
        }

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

    def post_steer(self, session=None):
        body = {"name": "proj", "text": STEER_TEXT}
        if session is not None:
            body["session"] = session
        return self.request("POST", "/api/steer", body)

    def private_requests(self):
        path = Path(self.context["record_path"])
        if not path.exists():
            return []
        return [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines()
                if line.strip()]

    def deliveries(self):
        return [entry for entry in self.private_requests()
                if entry["method"] == "POST" and "/prompt" in entry["path"]]

    @staticmethod
    def ok_flag(payload):
        return bool(payload) and payload.get("ok") is True

    @staticmethod
    def message_of(payload):
        if not isinstance(payload, dict):
            return ""
        return str(payload.get("message")
                   or (payload.get("error") or {}).get("message") or "")

    def assert_no_password_leak(self, raw):
        self.assertNotIn(
            PASSWORD, raw, "Das Kennwort erscheint in der API-Antwort")
        log = self.log_dir / "proj.log"
        if log.exists():
            self.assertNotIn(
                PASSWORD, log.read_text(encoding="utf-8"),
                "Das Kennwort steht im Laufprotokoll")
        if self.web_log_path.exists():
            self.assertNotIn(
                PASSWORD, self.web_log_path.read_text(
                    encoding="utf-8", errors="replace"),
                "Das Kennwort steht im Dashboard-Protokoll")


class PrivateDeliveryTest(B13SteerFixture):
    """AK3: Zustellung an den privaten Server des aktiven Laufs."""

    def test_steer_delivers_to_the_private_server_of_the_active_run(self):
        """AK3: Anweisung erreicht den privaten Server statt Connection refused.

        Vorbedingung: aktiver Lauf, Hauptsession ses_main erfasst, gültige
        Kennwortdatei, gültige Serverdatei auf den lokalen privaten
        Testserver; gemeinsamer Port ist abgewiesen.
        Aktion: POST /api/steer.
        Erwartung: ok:true mit Übermittelt-Meldung; genau eine Zustellung an
        ``/api/session/ses_main/prompt`` mit korrekter Basic-Auth („opencode:
        Kennwort aus der Datei“) und dem Anweisungstext; Kennwort in keiner
        Antwort und keinem Protokoll.
        Fehlerfall: „Connection refused“, Zustellung am gemeinsamen Server
        oder falsche Anmeldung.
        """
        self.start_private_server()
        self.write_password()
        self.register_run("running")
        now = int(time.time())
        self.write_state({
            "session": MAIN_SESSION,
            "subagents": [self.running_entry(CHILD_SESSION, "tester",
                                             now + 10)],
        })
        self.write_server_file()

        status, data, raw = self.post_steer()

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data),
                        f"Zustellung am privaten Server schlug fehl: {raw}")
        self.assertTrue(self.message_of(data).strip(), raw)
        posts = self.deliveries()
        self.assertEqual(1, len(posts), f"Genau eine Zustellung: {posts}")
        self.assertEqual(f"/api/session/{MAIN_SESSION}/prompt",
                         posts[0]["path"], posts)
        self.assertTrue(posts[0]["auth_ok"], posts)
        self.assertIn(STEER_TEXT, posts[0]["body"], posts)
        self.assert_no_password_leak(raw)

    def test_steer_targets_a_running_subagent_via_the_private_server(self):
        """AK3: Zielgenaue Zustellung an einen laufenden Subagenten.

        Vorbedingung: wie Haupttest; laufender Subagent ses_child.
        Aktion: POST /api/steer mit session=ses_child.
        Erwartung: ok:true; Zustellung an ``/api/session/ses_child/prompt``.
        Fehlerfall: Falsches Ziel oder Zustellung an die Hauptsession.
        """
        self.start_private_server()
        self.write_password()
        self.register_run("running")
        now = int(time.time())
        self.write_state({
            "session": MAIN_SESSION,
            "subagents": [self.running_entry(CHILD_SESSION, "tester",
                                             now + 10)],
        })
        self.write_server_file()

        status, data, raw = self.post_steer(session=CHILD_SESSION)

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        posts = self.deliveries()
        self.assertEqual(1, len(posts), posts)
        self.assertEqual(f"/api/session/{CHILD_SESSION}/prompt",
                         posts[0]["path"], posts)
        self.assertTrue(posts[0]["auth_ok"], posts)

    def test_steer_accepts_a_localhost_server_url(self):
        """AK3: Auch localhost ist als Loopback-URL zulässig.

        Vorbedingung: Serverdatei mit URL ``http://localhost:<Port>``.
        Aktion: POST /api/steer.
        Erwartung: ok:true mit Zustellung am Port der URL.
        Fehlerfall: Die localhost-URL wird abgelehnt.
        """
        self.start_private_server()
        self.write_password()
        self.register_run("running")
        self.write_state({"session": MAIN_SESSION, "subagents": []})
        self.write_server_file(url="http://localhost:%d" % self.priv_port)

        status, data, raw = self.post_steer()

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data),
                        f"localhost-URL wurde nicht akzeptiert: {raw}")
        self.assertEqual(1, len(self.deliveries()), self.private_requests())


class PreviousPathTest(B13SteerFixture):
    """AK4/AK8: Rückfall auf den bisherigen Pfad bzw. verständliche Ablehnung."""

    def test_steer_without_a_server_file_keeps_the_previous_path(self):
        """AK4: Ohne Serverdatei bleibt der bisherige Weg unverändert.

        Vorbedingung: aktiver Lauf, Kennwortdatei gesetzt, keine
        Serverdatei; gemeinsamer Port abgewiesen.
        Aktion: POST /api/steer.
        Erwartung: ok:false mit nichtleerer Meldung; keine Zustellung am
        privaten Testserver.
        Fehlerfall: Zustellung trotz fehlender Serverdatei.
        """
        self.write_password()
        self.register_run("running")
        self.write_state({"session": MAIN_SESSION, "subagents": []})

        status, data, raw = self.post_steer()

        self.assertIn(status, (200, 400), raw)
        self.assertFalse(self.ok_flag(data), raw)
        self.assertTrue(self.message_of(data).strip(), raw)
        self.assertEqual([], self.deliveries(), self.private_requests())

    def test_steer_without_password_file_rejects_understandably(self):
        """AK4: Fehlende/leere Kennwortdatei → verständliche Meldung.

        Vorbedingung: aktive Lauf mit erfasster Session, aber ohne
        Kennwortdatei (und zweiteilige Variante: leere Datei); keine
        Serverdatei.
        Aktion: POST /api/steer.
        Erwartung: ok:false; die Meldung nennt das fehlende Kennwort und ist
        nicht die rohe Verbindungsfehlermeldung; keine Zustellung.
        Fehlerfall: „Connection refused“ statt verständlicher Ablehnung.
        """
        for variant in ("fehlt", "leer"):
            with self.subTest(variant=variant):
                self.setUp()
                if variant == "leer":
                    self.password_file().write_text(
                        "   \n", encoding="utf-8")
                self.register_run("running")
                self.write_state({"session": MAIN_SESSION, "subagents": []})

                status, data, raw = self.post_steer()

                self.assertIn(status, (200, 400), raw)
                self.assertFalse(self.ok_flag(data), raw)
                message = self.message_of(data)
                self.assertIn(
                    "Kennwort", message,
                    f"Verständliche Ablehnung nennt das Kennwort: {message}")
                self.assertNotIn(
                    "Connection refused", message,
                    f"Rohe Fehlermeldung erreicht den Nutzer: {message}")
                self.assertEqual([], self.deliveries(),
                                 self.private_requests())

    def test_steer_ignores_a_broken_server_file(self):
        """AK8: Defektes JSON wird nicht angenommen.

        Vorbedingung: ``proj.log.server.json`` enthält kein gültiges JSON;
        privater Testserver läuft.
        Aktion: POST /api/steer.
        Erwartung: ok:false mit nichtleerer Meldung; keine Zustellung am
        privaten Server.
        Fehlerfall: Die defekte Datei wird trotzdem verwendet.
        """
        self.start_private_server()
        self.write_password()
        self.register_run("running")
        self.write_state({"session": MAIN_SESSION, "subagents": []})
        self.write_server_file(raw="{kein json")

        status, data, raw = self.post_steer()

        self.assertIn(status, (200, 400), raw)
        self.assertFalse(self.ok_flag(data), raw)
        self.assertTrue(self.message_of(data).strip(), raw)
        self.assertEqual([], self.deliveries(), self.private_requests())

    def test_steer_ignores_a_server_file_without_usable_url(self):
        """AK8: Datei ohne gültigen Port wird nicht angenommen.

        Vorbedingung: Serverdatei nur mit ``password_file``, ohne URL/Port;
        privater Testserver läuft.
        Aktion: POST /api/steer.
        Erwartung: ok:false mit nichtleerer Meldung; keine Zustellung.
        Fehlerfall: Der fehlende Port wird still ergänzt oder es wird
        trotzdem gesendet.
        """
        self.start_private_server()
        self.write_password()
        self.register_run("running")
        self.write_state({"session": MAIN_SESSION, "subagents": []})
        self.write_server_file(raw=json.dumps(
            {"password_file": str(self.password_file())}))

        status, data, raw = self.post_steer()

        self.assertIn(status, (200, 400), raw)
        self.assertFalse(self.ok_flag(data), raw)
        self.assertTrue(self.message_of(data).strip(), raw)
        self.assertEqual([], self.deliveries(), self.private_requests())

    def test_steer_ignores_a_non_loopback_server_url(self):
        """AK8: Fremde Hosts werden nicht angenommen.

        Vorbedingung: Serverdatei mit URL ``http://example.invalid:<Port>``;
        zusätzlich lauscht lokal ein Server am selben Port auf 127.0.0.1, um zu
        belegen, dass nichts „in der Nähe“ zugestellt wird; privater
        Testserver läuft.
        Aktion: POST /api/steer.
        Erwartung: ok:false mit nichtleerer Meldung; keine Zustellung am
        lokalen Auffang-Servers am selben Port und keine am privaten
        Testserver.
        Fehlerfall: Die fremde URL wird akzeptiert oder der Host still
        durch Loopback ersetzt.
        """
        self.start_private_server()
        self.write_password()
        self.register_run("running")
        self.write_state({"session": MAIN_SESSION, "subagents": []})

        class CatchHandler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                self.send_response(200)
                self.end_headers()

        catch_port = self.free_port()
        catcher = ThreadingHTTPServer(("127.0.0.1", catch_port), CatchHandler)
        catcher.daemon_threads = True
        catcher.requests = []
        thread = threading.Thread(target=catcher.serve_forever)
        thread.daemon = True
        thread.start()
        try:
            self.write_server_file(url="http://example.invalid:%d" % catch_port,
                                   port=catch_port)

            status, data, raw = self.post_steer()
        finally:
            catcher.shutdown()
            catcher.server_close()
            thread.join(timeout=5)

        self.assertIn(status, (200, 400), raw)
        self.assertFalse(self.ok_flag(data), raw)
        self.assertTrue(self.message_of(data).strip(), raw)
        self.assertEqual([], self.deliveries(), self.private_requests())


class PiSteerKeptTest(B13SteerFixture):
    """AK7: Pi-Ablehnung bleibt auch mit Serverdatei bestehen."""

    def test_pi_steer_stays_forbidden_even_with_a_server_file(self):
        """AK7: Pi wird auch mit privatem Server nicht gesteuert.

        Vorbedingung: harness.json wählt pi; aktiver Lauf; gültige
        Serverdatei und Kennwortdatei; privater Testserver läuft.
        Aktion: POST /api/steer.
        Erwartung: ok:false mit der bekannten Meldung „Zusatzanweisungen
        sind bei Pi nicht möglich“; keine Zustellung.
        Fehlerfall: Die Serverdatei umgeht die Pi-Ablehnung.
        """
        self.start_private_server()
        self.write_password()
        (self.state_dir / "harness.json").write_text(
            json.dumps({"harness": "pi"}, ensure_ascii=False) + "\n",
            encoding="utf-8")
        self.register_run("running")
        self.write_state({"session": MAIN_SESSION, "subagents": []})
        self.write_server_file()

        status, data, raw = self.post_steer()

        self.assertIn(status, (200, 400), raw)
        self.assertFalse(self.ok_flag(data), raw)
        message = self.message_of(data)
        self.assertIn("Zusatzanweisungen sind bei Pi nicht möglich",
                      message, f"Bekannter Hinweistext fehlt: {message}")
        self.assertEqual([], self.deliveries(), self.private_requests())


if __name__ == "__main__":
    unittest.main()
