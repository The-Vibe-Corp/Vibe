"""Unit-Abnahme F20: Pi als gewählter Harness im Dashboard (Backend).

Aus Arbeitspaket F20 abgeleitete Anforderungen (und docs/compatibility.md
„Pi 1.5.0“: Pi läuft im Print-Modus mit --no-session, liest keine
opencode-Agentenverwaltung, hat keinen opencode-Server, Sessions werden
nicht fortgesetzt, bei Pi meldet /api/server server_supported:false):

* GET /api/server meldet bei Pi ``harness:"pi"`` und ``server_supported:false``;
  bei opencode (Default ohne Auswahl oder ausdrücklicher Wahl)
  ``harness:"opencode"`` und ``server_supported:true``.
* POST /api/steer lehnt bei Pi die Zusatzanweisung mit ``ok:false`` ab. Die
  Meldung nennt den Grund (Pi Print-Modus, keine fortsetzbare Session, keine
  Übermittlung an den Agenten) und ist nicht die sessionbezogene Meldung
  „Die Session des laufenden Agenten ist nicht erfasst …“. Es darf dabei
  kein Zustellversuch an den opencode-Server stattfinden (in der Attrappe:
  kein Eintrag im Request-Protokoll).
* Regression opencode: ohne Auswahl, mit ausdrücklicher Wahl „opencode“ und
  bei unbekannter Auswahl in ``harness.json`` verhält sich /api/steer genau
  wie bisher (Zustellversuch per HTTP Basic-Auth, Erfolg bei passender
  Attrappe).

Voraussetzung der Auswahl ist ``<VIBE_STATE>/harness.json =
{"harness":"pi"}`` bzw. ``{"harness":"opencode"}`` für den Webserver-Prozess;
VIBE_HARNESS wird in dieser Datei nicht gesetzt (isolierte Prozesse, eigenes
VIBE/HOME/PORT, keine echten Modellaufrufe).
Provenienz: Von der unabhängigen Test-Agenten-Sitzung geprüft, formal
übernommen und als verbindliche Testfälle des Test-Agenten erklärt.
"""
import base64
import http.client
import importlib.machinery
import importlib.util
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
CLI = REPO / "bin" / "vibe"
WEB = REPO / "bin" / "vibe-web.py"
RUNS_PY = REPO / "bin" / "vibe_runs.py"

MAIN_SESSION = "ses_main"
STEER_TEXT = "Prüfe zuerst die Borderstellung"
SERVER_CREDENTIAL = "geheim-PASSWORT-4711"

STATE_FILE = {"session": MAIN_SESSION, "subagents": []}

SESSION_MISSING_MESSAGE = (
    "Die Session des laufenden Agenten ist nicht erfasst"
)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def load_cli_module(name="vibe_f20_api_under_test"):
    """Lädt bin/vibe mit der aktuellen Umgebungsvariablen des Aufrufers."""
    loader = importlib.machinery.SourceFileLoader(name, str(CLI))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """Nachbildung des opencode-Servers: GET meldet Lauffähigkeit, POST nimmt
    eine Zusatzanweisung nur mit gültiger Basic-Auth an. Alle POST-Anfragen
    landen in <runtime>/fake-opencode.requests.jsonl, damit Tests beweisen
    können, ob eine Zustellung (nicht) versucht wurde."""

    context = None  # dict(credential_path, record_path)

    def log_message(self, *args):
        return

    def _signature(self):
        try:
            password = Path(self.context["credential_path"]).read_text(
                encoding="utf-8"
            ).strip()
        except OSError:
            return None
        encoded = base64.b64encode(("opencode:" + password).encode()).decode()
        return "Basic " + encoded

    def do_GET(self):
        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        signature = self._signature()
        header = self.headers.get("Authorization", "")
        auth_ok = signature is not None and header == signature
        user = ""
        if header.startswith("Basic "):
            try:
                decoded = base64.b64decode(header[6:]).decode("utf-8")
                user = decoded.split(":", 1)[0]
            except Exception:
                user = ""
        with open(self.context["record_path"], "a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"path": self.path, "auth_ok": auth_ok, "user": user,
                     "body": body},
                    ensure_ascii=False,
                ) + "\n"
            )
        status = 200 if auth_ok else 401
        payload = json.dumps({"ok": auth_ok}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def make_fake_handler(context):
    def build():
        handler = type("BoundHandler", (BaseHTTPRequestHandler,), {})
        for attribute, value in _FakeOpenCodeHandler.__dict__.items():
            if not attribute.startswith("__"):
                setattr(handler, attribute, value)
        handler.context = context
        return handler
    return build()


class ApiFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True
        )
        cls.state_dir = cls.root / "_toolchain"
        cls.state_dir.mkdir()
        cls.port = free_port()
        cls.oc_port = free_port()
        cls.context = {
            "credential_path": str(cls.root / "_logs" / "opencode.password"),
            "record_path": str(cls.root / "_logs" / "fake-opencode.requests.jsonl"),
        }
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), make_fake_handler(cls.context)
        )
        cls._fake_http.daemon_threads = True
        cls._fake_thread = threading.Thread(target=cls._fake_http.serve_forever)
        cls._fake_thread.daemon = True
        cls._fake_thread.start()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.env = cls.build_env()
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=cls.env,
            stdout=cls.server_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                        ("127.0.0.1", cls.port), timeout=0.5
                    ):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: "
                    + cls.root.joinpath("web-server.log").read_text(
                        encoding="utf-8", errors="replace"
                    )
                )
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.session = cls.sess_name("proj")

    @classmethod
    def build_env(cls):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                "TMUX", "TMUX_PANE",
            ):
                env.pop(key, None)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir()
        cls.tmux_dir.chmod(0o700)
        tmp = cls.root / "tmp"
        tmp.mkdir()
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "VIBE_OPENCODE_PORT": str(cls.oc_port),
                "VIBE_INSTALL": str(cls.state_dir),
                "VIBE_RUNTIME": str(cls.root / "_logs"),
                "VIBE_STATE": str(cls.state_dir),
                "HOME": str(cls.root / "home"),
                "VIBE_CONFIG_FILE": str(
                    cls.root / "home" / ".config" / "vibe" / "config.json"
                ),
                "TMPDIR": str(tmp),
                "TMUX_TMPDIR": str(cls.tmux_dir),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        return env

    @classmethod
    def sess_name(cls, name):
        saved = os.environ.copy()
        try:
            os.environ.update(cls.env)
            module = load_cli_module()
            return module.sess(name)
        finally:
            for key in list(os.environ):
                if key not in saved:
                    os.environ.pop(key, None)
            os.environ.update(saved)

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
        try:
            cls._fake_http.shutdown()
            cls._fake_http.server_close()
            cls._fake_thread.join(timeout=5)
        except Exception:
            pass
        subprocess.run(
            ["tmux", "kill-server"],
            env={**os.environ, "TMUX_TMPDIR": str(cls.tmux_dir)},
            capture_output=True,
            timeout=20,
        )
        cls.tmp.cleanup()

    # ---------- Helfer ----------
    def setUp(self):
        self.reset_state()
        self.password_clear()
        self.clear_requests()
        self.set_selection(None)

    def reset_state(self):
        state = self.root / "_logs" / "proj.log.state.json"
        if state.exists():
            state.unlink()

    def write_state(self, data=STATE_FILE):
        path = self.root / "_logs" / "proj.log.state.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def set_selection(self, harness):
        """Schreibt/entfernt <VIBE_STATE>/harness.json für den Webserver-Prozess."""
        path = self.state_dir / "harness.json"
        if harness is None:
            if path.exists():
                path.unlink()
        else:
            path.write_text(
                json.dumps({"harness": harness}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        return path

    def password_private(self, value=SERVER_CREDENTIAL):
        path = self.root / "_logs" / "opencode.password"
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
        return path

    def password_clear(self):
        path = self.root / "_logs" / "opencode.password"
        if path.exists():
            path.unlink()

    def request(self, method, path, body=None):
        if body is not None and not isinstance(body, (bytes, bytearray)):
            encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        else:
            encoded = body
        headers = {
            "Host": f"127.0.0.1:{self.port}",
            "X-Token": self.token,
            "Origin": f"http://127.0.0.1:{self.port}",
            "Sec-Fetch-Site": "same-origin",
        }
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
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

    def clear_requests(self):
        path = Path(self.context["record_path"])
        if path.exists():
            path.unlink()

    def posts(self):
        """Alle protokollierten POST-Zustellungen an die opencode-Attrappe."""
        path = Path(self.context["record_path"])
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def log_text(self):
        path = self.root / "_logs" / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def touch_run_log(self):
        path = self.root / "_logs" / "proj.log"
        path.write_text(
            "Lauf: proj, Modus: --standalone, Agent: tester\n"
            "=== [proj] Arbeitspaket F20, Versuch 1/3, Durchgang 1/80 ===\n",
            encoding="utf-8",
        )
        return path

    def start_active_run(self):
        """Vorbedingung „aktiver Lauf“: Registereintrag state running plus
        offene tmux-Sitzung, wie im F19-Muster nachgebildet."""
        subprocess.run(
            [
                sys.executable, str(RUNS_PY), "start",
                "--runtime", str(self.root / "_logs"),
                "--project", str(self.project.resolve()),
                "--name", "proj", "--key", "proj", "--agent", "tester",
                "--session", self.session,
                "--state", "running",
            ],
            env=self.env_clean(),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def stop_active_run(self):
        subprocess.run(
            ["tmux", "kill-session", "-t", self.session],
            env=self.env_clean(),
            capture_output=True,
            timeout=20,
        )
        register = self.root / "_logs" / "runs.json"
        if register.exists():
            data = json.loads(register.read_text(encoding="utf-8"))
            for record in reversed(data.get("runs", [])):
                if record.get("session") == self.session and record.get(
                    "state"
                ) in ("running", "starting"):
                    record["state"] = "finished"
            register.write_text(
                json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8",
            )

    def env_clean(self):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                "TMUX", "TMUX_PANE",
            ):
                env.pop(key, None)
        env.update(self.env)
        return env

    def post_steer(self, name="proj", text=STEER_TEXT):
        return self.request("POST", "/api/steer", {"name": name, "text": text})

    def make_delivery_ready(self):
        """Vollständige Zustellbarkeit nachbilden: aktiver Lauf, erfasste
        Session und gespeicherten opencode-Kennworts (nur Testkennwort)."""
        self.start_active_run()
        self.touch_run_log()
        self.write_state()
        status, data, raw = self.request("GET", "/api/run-state?name=proj")
        self.assertEqual(status, 200, raw)
        self.assertTrue(data.get("running"), "Vorbedingung aktiver Lauf fehlgeschlagen: " + raw)
        self.password_private()
        return status

    def tearDown(self):
        self.stop_active_run()
        try:
            self.set_selection(None)
        finally:
            self.password_clear()
            self.reset_state()
            self.clear_requests()


class ServerEndpointTest(ApiFixture):
    """AK A Einzelpins: /api/server meldet Auswahl und Serverfähigkeit."""

    def test_server_reports_pi_without_server_support(self):
        # Vorbedingung: harness.json wählt Pi; Aktion: GET /api/server;
        # Erwartung: harness "pi" und server_supported false.
        self.set_selection("pi")
        status, data, raw = self.request("GET", "/api/server")
        self.assertEqual(status, 200, raw)
        self.assertEqual(data.get("harness"), "pi", raw)
        self.assertFalse(data.get("server_supported", True), raw)

    def test_server_reports_opencode_support_by_default(self):
        # Vorbedingung: keine Auswahl (Default); Aktion: GET /api/server;
        # Erwartung: harness "opencode" und server_supported true.
        status, data, raw = self.request("GET", "/api/server")
        self.assertEqual(status, 200, raw)
        self.assertEqual(data.get("harness"), "opencode", raw)
        self.assertTrue(data.get("server_supported", False), raw)

    def test_server_reports_explicit_opencode_selection_as_supported(self):
        # Vorbedingung: harness.json wählt ausdrücklich opencode;
        # Aktion: GET /api/server; Erwartung: server_supported true.
        self.set_selection("opencode")
        status, data, raw = self.request("GET", "/api/server")
        self.assertEqual(status, 200, raw)
        self.assertEqual(data.get("harness"), "opencode", raw)
        self.assertTrue(data.get("server_supported", False), raw)


class SteerSelectionTest(ApiFixture):
    """AK A: /api/steer bei Pi verständliche Ablehnung ohne Zustellversuch;
    Regression opencode/ohne Auswahl/unbekannte Auswahl wie bisher."""

    def test_steer_with_selected_pi_is_rejected_without_delivery_attempt(self):
        # Vorbedingung: Pi gewählt, aktiver Lauf, erfasste Session, Kennwort
        # gesetzt und erreichbare opencode-Attrappe (volle Zustellbarkeit);
        # Aktion: POST /api/steer;
        # Erwartung: ok:false (HTTP 400, code "rejected"), Pi-Meldung mit
        # Grund, nicht die sessionbezogene Meldung, kein POST an opencode.
        self.set_selection("pi")
        self.make_delivery_ready()
        before = len(self.posts())

        status, data, raw = self.post_steer()
        self.assertEqual(status, 400, raw)
        self.assertEqual(data["error"]["code"], "rejected", raw)
        message = str(data["error"]["message"] or "")
        self.assertTrue(message.strip(), "Ablehnung braucht eine verständliche Meldung")
        self.assertIn("Pi", message, "Meldung muss die Ursache Pi nennen: " + message)
        reason_tokens = (
            "Print", "print", "--no-session", "no-session",
            "Session", "Sitzung", "fortgesetzt", "fortsetzbar",
        )
        self.assertTrue(
            any(token in message for token in reason_tokens),
            "Meldung muss den Print-Modus/die fehlende fortsetzbare Session nennen: "
            + message,
        )
        self.assertNotIn(
            SESSION_MISSING_MESSAGE, message,
            "Bei Pi darf die sessionbezogene Fehlermeldung nicht erscheinen",
        )
        self.assertEqual(
            len(self.posts()), before,
            "Bei Pi darf kein Zustellversuch an den opencode-Server stattfinden",
        )
        self.assertNotIn(
            "Zusatzanweisung an den Agenten übermittelt", self.log_text(),
            "Bei Pi darf keine Kennzeile im Protokoll stehen",
        )
        # Das Kennwort darf in keinem Ergebnis erscheinen.
        self.assertNotIn(SERVER_CREDENTIAL, raw)

    def test_steer_regression_default_selection_is_delivered_as_before(self):
        # Vorbedingung: keine Auswahl (Default opencode), volle Zustellbarkeit;
        # Aktion: POST /api/steer; Erwartung: Erfolg wie bisher inkl. Basic-Auth
        # und Kennzeile im Protokoll.
        self.make_delivery_ready()

        status, data, raw = self.post_steer()
        self.assertEqual(status, 200, raw)
        self.assertTrue(data.get("ok"), raw)
        posts = self.posts()
        self.assertTrue(posts, "opencode-Server hat keine Zustellung erhalten")
        text_found = [post for post in posts if STEER_TEXT in post.get("body", "")]
        self.assertTrue(text_found, f"Zusatztext fehlt in der Zustellung: {posts}")
        self.assertTrue(all(post.get("user") == "opencode" for post in text_found), posts)
        self.assertTrue(all(post.get("auth_ok") for post in text_found), posts)
        self.assertIn(STEER_TEXT, self.log_text())

    def test_steer_regression_explicit_opencode_selection_is_delivered(self):
        # Vorbedingung: harness.json wählt ausdrücklich opencode, volle
        # Zustellbarkeit; Aktion: POST /api/steer; Erwartung: Erfolg wie bisher.
        self.set_selection("opencode")
        self.make_delivery_ready()

        status, data, raw = self.post_steer()
        self.assertEqual(status, 200, raw)
        self.assertTrue(data.get("ok"), raw)
        self.assertTrue(self.posts(), "opencode-Server hat keine Zustellung erhalten")
        self.assertIn(STEER_TEXT, self.log_text())

    def test_unknown_harness_value_keeps_the_previous_behavior(self):
        # Vorbedingung: harness.json enthält einen unbekannten Wert; volle
        # Zustellbarkeit; Aktion: POST /api/steer;
        # Erwartung: bisheriges Verhalten (Zustellversuch/Erfolg), nicht die
        # Pi-Ablehnung und kein Absturz.
        self.set_selection("völlig-unbekannt")
        self.make_delivery_ready()

        status, data, raw = self.post_steer()
        self.assertEqual(status, 200, raw)
        self.assertTrue(data.get("ok"), "Bei unbekannter Auswahl gilt bisheriges Verhalten: " + raw)
        self.assertNotIn("Pi", str(data.get("message") or ""))
        self.assertTrue(self.posts(), "opencode-Server hat keine Zustellung erhalten")
        self.assertIn(STEER_TEXT, self.log_text())

    def test_password_secret_never_leaves_api_results(self):
        # Sicherheitsregression: Das Serverkennwort erscheint in keinem API-
        # Ergebnis, unabhängig von der gewählten Auswahl.
        self.make_delivery_ready()  # legt Kennwortdatei und Fall an
        self.set_selection("pi")
        for method, path in (
            ("GET", "/api/server"),
            ("GET", "/api/run-state?name=proj"),
            ("GET", "/api/projects"),
        ):
            status, data, raw = self.request(method, path)
            self.assertNotIn(SERVER_CREDENTIAL, raw, f"Kennwort in {path}: {raw}")
        self.post_steer()
        for post in self.posts():
            self.assertNotIn(SERVER_CREDENTIAL, json.dumps(post, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
