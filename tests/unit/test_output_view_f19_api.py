"""Unit-Abnahme F19 (Teil 2): HTTP-API des Dashboards für Subagenten,
Subagenten-Ausgabe und Zusatzanweisungen (Steuerung eines laufenden Laufs).

Aus Arbeitspaket F19 abgeleitete Anforderungen (und SPEC.md „Agentenläufe" plus
Sicherheitsregeln):

* GET /api/subagents ist token-geschützt wie die übrigen /api-Endpunkte und
  liest Laufsession und erfasste Subagenten aus der Zustandsdatei
  ``<log>.state.json`` (im Test als Eingabedaten nachgebildet; die Erfassung
  durch den Läufer prüft tests/unit/test_output_view_f19_runner.py). Ohne
  Zustandsdatei sind keine Subagenten erfasst — es gibt keine Attrappen.
* GET /api/subagent-output liefert die Ausgabe eines erfassten Subagenten;
  für unbekannte Sessions antwortet ok:false mit einer verständlichen Meldung
  und ohne HTTP-Fehler.
* POST /api/steer übermittelt eine Zusatzanweisung tatsächlich an den
  opencode-Server. Erfolg gibt es nur bei echter Zustellung mittels HTTP
  Basic-Auth (Benutzer „opencode" mit dem Kennwort aus
  ``<runtime>/opencode.password``). Ohne Token, bei leerem Text, ohne aktiven
  Lauf, ohne Session oder bei nicht erreichbarem Server ist die Antwort
  HTTP 400 mit ``error.code`` = „rejected"; niemals vorgetäuschter Erfolg.
  Nach Erfolg steht eine Kennzeile im Laufprotokoll.
* Das Serverkennwort erscheint in keinem API-Ergebnis.

Es werden keine echten Modellaufrufe getätigt; der opencode-Server ist ein
lokaler Testserver (temporäres VIBE/HOME, eigene Ports, eigene tmux-Umgebung).
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

from tests.support.tmux_cleanup import cleanup_env

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
WEB = REPO / "bin" / "vibe-web.py"
RUNS_PY = REPO / "bin" / "vibe_runs.py"

MAIN_SESSION = "ses_main"
CHILD_SESSION = "ses_child"
CHILD_RUNNING = "ses_child2"
STEER_TEXT = "Prüfe zuerst die Borderstellung"
SERVER_CREDENTIAL = "geheim-PASSWORT-4711"

STATE_FILE = {
    "session": MAIN_SESSION,
    "subagents": [
        {
            "session": CHILD_SESSION,
            "agent": "general",
            "description": "Testzusammenfassung",
            "prompt": "Sammle Infos",
            "status": "completed",
            "started": 1,
            "ended": 2,
            "output": "PONG",
        },
        {
            "session": "ses_child2",
            "agent": "general",
            "description": "Sammlung läuft",
            "prompt": "Lies Protokoll",
            "status": "running",
            "started": 3,
            "ended": 0,
            "output": "",
        },
    ],
}


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def load_cli_module(name="vibe_f19_api_under_test"):
    """Lädt bin/vibe mit der aktuellen Umgebungsvariablen des Aufrufers."""
    loader = importlib.machinery.SourceFileLoader(name, str(CLI))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """Nachbildung des opencode-Servers: GET teilt Lauffähigkeit mit, POST nimmt
    eine Zusatzanweisung nur mit gültiger Basic-Auth (Benutzer „opencode" und
    Kennwort aus <runtime>/opencode.password) an. Jede POST-Anfrage wird in
    <runtime>/fake-opencode.requests.jsonl protokolliert, damit ein Test die
    tatsächliche Zustellung beweisen kann."""

    context = None  # dict(credential_path, record_path), vom Test gesetzt

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
                    {
                        "path": self.path,
                        "auth_ok": auth_ok,
                        "user": user,
                        "body": body,
                    },
                    ensure_ascii=False,
                )
                + "\n"
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
        # Den exakten Jestelling-Sitzungsnamen (Projektschlüssel, Profil) mit
        # derselben Projektlogik bestimmen, die auch die Web-API verwendet.
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
                "VIBE_INSTALL": str(cls.root / "_toolchain"),
                "VIBE_RUNTIME": str(cls.root / "_logs"),
                "VIBE_STATE": str(cls.root / "_toolchain"),
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
        cls.stop_fake_server()
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        cls.server_log.close()
        subprocess.run(
            ["tmux", "kill-server"],
            env=cleanup_env(os.environ, cls.tmux_dir),
            capture_output=True,
            timeout=20,
        )
        cls.tmp.cleanup()

    @classmethod
    def stop_fake_server(cls):
        if getattr(cls, "_fake_stopped", False):
            return
        cls._fake_stopped = True
        try:
            cls._fake_http.shutdown()
            cls._fake_http.server_close()
            cls._fake_thread.join(timeout=5)
        except Exception:
            pass

    @classmethod
    def start_fake_server(cls):
        if getattr(cls, "_fake_stopped", False):
            cls._fake_http = ThreadingHTTPServer(
                ("127.0.0.1", cls.oc_port), make_fake_handler(cls.context)
            )
            cls._fake_http.daemon_threads = True
            cls._fake_thread = threading.Thread(target=cls._fake_http.serve_forever)
            cls._fake_thread.daemon = True
            cls._fake_thread.start()
            cls._fake_stopped = False

    # ---------- Helfer ----------
    def setUp(self):
        self.reset_state()

    def reset_state(self):
        state = self.root / "_logs" / "proj.log.state.json"
        if state.exists():
            state.unlink()

    def write_state(self, data=STATE_FILE):
        path = self.root / "_logs" / "proj.log.state.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
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

    def request(
        self,
        method,
        path,
        body=None,
        token=True,
        host=None,
        origin=None,
        extra_headers=None,
    ):
        if body is not None and not isinstance(body, (bytes, bytearray)):
            encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        else:
            encoded = body
        headers = {"Host": host if host is not None else f"127.0.0.1:{self.port}"}
        if token is True:
            headers["X-Token"] = self.token
        elif isinstance(token, str):
            headers["X-Token"] = token
        if origin is not None:
            headers["Origin"] = origin
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        headers.update(extra_headers or {})
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

    def delivered_posts(self):
        path = self.context["record_path"]
        if not Path(path).exists():
            return []
        return [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def log_text(self):
        path = self.root / "_logs" / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def start_active_run(self):
        """Vorbedingung „aktiver Lauf": Laufregister-Eintrag (state running)
        plus offene tmux-Sitzung — dieselben Bausteine eines echten Läufers.
        Hier werden keine Läufer- oder Protokollfunktionen ersetzt."""
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


class SubagentsEndpointTest(ApiFixture):
    """AK: Subagenten sichtbar; ohne Erfassung keine Attrappen; Token-Pflicht."""

    def test_subagents_is_token_protected(self):
        for token in (None, "falsches-token"):
            status, _, raw = self.request(
                "GET", "/api/subagents?name=proj", token=token
            )
            self.assertEqual(
                status, 403, f"bei Token {token!r} muss 403 folgen: {raw}"
            )
            data = json.loads(raw)
            self.assertEqual(data["error"]["code"], "unauthorized", raw)
            self.assertNotIn(self.token, raw)
        # Mit Token muss ein fachliches Ergebnis kommen (Routenpräsenz).
        status, data, raw = self.request("GET", "/api/subagents?name=proj")
        self.assertEqual(status, 200, raw)
        self.assertTrue(data and data.get("ok"), raw)
        self.assertIn("subagents", data, raw)

    def test_subagents_reports_state_file_entries(self):
        """B11-Anpassung: /api/subagents liefert nur Einträge des aktuellen
        Laufs. Der Test registriert deshalb einen laufenden Lauf und setzt
        die Startzeiten der erfassten Einträge hinter den Laufbeginn; die
        Feldsemantik (Session, Agent, Beschreibung, Status, Ausgabe) bleibt
        die der F19-Regression."""
        self.start_active_run()
        base_started = int(time.time()) + 5
        state = {
            "session": MAIN_SESSION,
            "subagents": [
                {**STATE_FILE["subagents"][0], "started": base_started + 5},
                {**STATE_FILE["subagents"][1], "started": base_started},
            ],
        }
        self.write_state(state)
        status, data, raw = self.request("GET", "/api/subagents?name=proj")
        self.assertEqual(status, 200, raw)
        self.assertTrue(data.get("ok"), raw)
        self.assertIsInstance(data.get("running"), bool, raw)
        self.assertEqual(data.get("session"), MAIN_SESSION, raw)
        entries = data.get("subagents")
        self.assertIsInstance(entries, list, raw)
        self.assertEqual(len(entries), 2, f"beide erfassten Subagenten fehlen: {raw}")
        by_session = {entry.get("session"): entry for entry in entries}
        completed = by_session.get(CHILD_SESSION)
        running = by_session.get(CHILD_RUNNING)
        self.assertIsNotNone(completed, f"erfasster abgeschlossener Eintrag fehlt: {raw}")
        self.assertIsNotNone(running, f"erfasster laufender Eintrag fehlt: {raw}")
        self.assertEqual(completed.get("agent"), "general", raw)
        self.assertEqual(completed.get("description"), "Testzusammenfassung", raw)
        self.assertEqual(completed.get("status"), "completed", raw)
        self.assertIn("PONG", str(completed.get("output") or ""), raw)
        self.assertEqual(running.get("status"), "running", raw)
        self.assertEqual(running.get("agent"), "general", raw)
        self.assertEqual(running.get("description"), "Sammlung läuft", raw)

    def test_subagents_reports_empty_without_state_file(self):
        status, data, raw = self.request("GET", "/api/subagents?name=proj")
        self.assertEqual(status, 200, raw)
        self.assertTrue(data.get("ok"), raw)
        self.assertIsInstance(data.get("running"), bool, raw)
        self.assertEqual([], data.get("subagents") or [], raw)
        self.assertNotIn(MAIN_SESSION, raw, "Session darf nicht erfunden werden")
        self.assertNotIn("ses_", raw, "Es dürfen keine erfundenen Sessions erscheinen")


class SubagentOutputTest(ApiFixture):
    """AK: Ausgaben von Subagenten anzeigen; für Zustände ohne Ausgabe eine
    verständliche Meldung statt eines HTTP-Fehlers."""

    def test_output_of_a_captured_subagent(self):
        """B11-Anpassung: Auch die Ausgabeabfrage gilt für Einträge des
        aktuellen Laufs; der Test registriert deshalb einen laufenden Lauf
        und setzt die Startzeit des erfassten Eintrags hinter den
        Laufbeginn."""
        self.start_active_run()
        state = json.loads(json.dumps(STATE_FILE))
        state["subagents"][0]["started"] = int(time.time()) + 5
        self.write_state(state)
        status, data, raw = self.request(
            "GET", f"/api/subagent-output?name=proj&session={CHILD_SESSION}"
        )
        self.assertEqual(status, 200, raw)
        self.assertTrue(data.get("ok"), raw)
        self.assertIn("PONG", str(data.get("text") or ""), raw)

    def test_output_of_unknown_session_is_ok_false_without_http_error(self):
        status, data, raw = self.request(
            "GET", "/api/subagent-output?name=proj&session=ses_unbekannt"
        )
        self.assertEqual(status, 200, raw)
        self.assertFalse(data.get("ok"), raw)
        self.assertTrue(str(data.get("message") or "").strip(), raw)

    def test_output_of_running_subagent_without_live_data_is_ok_false(self):
        self.stop_fake_server()
        try:
            status, data, raw = self.request(
                "GET", "/api/subagent-output?name=proj&session=ses_child2"
            )
        finally:
            self.start_fake_server()
        self.assertEqual(status, 200, raw)
        # Ohne erreichbaren opencode-Server gibt es keine Live-Ausgabe; das darf
        # weder ein HTTP-Fehler sein noch ein erfundener Text.
        self.assertFalse(data.get("ok"), raw)
        self.assertTrue(str(data.get("message") or "").strip(), raw)


class SteerTest(ApiFixture):
    """AK: Zusatzanweisung während des Laufs übermitteln; Erfolg nur bei echter
    Zustellung; Kennzeile im Protokoll; Verweigerungen mit code 'rejected'."""

    def setUp(self):
        self.reset_state()
        self.password_clear()

    def post_steer(self, name="proj", text=STEER_TEXT, token=True):
        return self.request(
            "POST", "/api/steer", body={"name": name, "text": text}, token=token,
            origin=f"http://127.0.0.1:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"},
        )

    def tearDown(self):
        self.stop_active_run()

    def touch_run_log(self):
        path = self.root / "_logs" / "proj.log"
        path.write_text(
            "Lauf: proj, Modus: --standalone, Agent: tester\n"
            "=== [proj] Arbeitspaket F19, Versuch 1/3, Durchgang 1/80 ===\n",
            encoding="utf-8",
        )
        return path

    def test_rejections_before_any_delivery(self):
        status, data, raw = self.post_steer(token=False)
        self.assertEqual(status, 403, raw)
        self.assertEqual(data["error"]["code"], "unauthorized", raw)
        self.assertEqual([], self.delivered_posts(), raw)

        for body in ({"name": "proj", "text": ""},
                     {"name": "proj", "text": "   "}):
            status, data, raw = self.post_steer(**body)
            self.assertEqual(status, 400, raw)
            self.assertFalse(data.get("ok"), raw)
            self.assertEqual(data["error"]["code"], "rejected", raw)
            self.assertTrue(str(data["error"]["message"] or "").strip(), raw)
        self.assertEqual([], self.delivered_posts(), raw)

        status, data, raw = self.post_steer(name="fehlt")
        self.assertEqual(status, 400, raw)
        self.assertFalse(data.get("ok"), raw)
        self.assertTrue(str(data["error"]["message"] or "").strip(), raw)
        self.assertEqual([], self.delivered_posts(), raw)

    def test_rejection_without_active_run(self):
        status, data, raw = self.post_steer()
        self.assertEqual(status, 400, raw)
        self.assertFalse(data.get("ok"), raw)
        self.assertEqual(data["error"]["code"], "rejected", raw)
        self.assertEqual([], self.delivered_posts(), raw)

    def test_active_run_and_wrong_or_missing_password_is_rejected(self):
        self.start_active_run()
        self.write_state({"session": MAIN_SESSION, "subagents": []})
        status, data, raw = self.request("GET", "/api/run-state?name=proj")
        self.assertEqual(status, 200, raw)
        self.assertTrue(data.get("running"), "Vorbedingung aktiver Lauf fehlgeschlagen: " + raw)

        status, data, raw = self.post_steer()
        self.assertEqual(status, 400, raw)
        self.assertFalse(data.get("ok"), raw)
        self.assertEqual(data["error"]["code"], "rejected", raw)

    def test_active_run_with_unreachable_server_is_rejected(self):
        self.start_active_run()
        self.password_private()
        self.write_state({"session": MAIN_SESSION, "subagents": []})
        self.stop_fake_server()
        try:
            status, data, raw = self.post_steer()
            self.assertEqual(status, 400, raw)
            self.assertFalse(data.get("ok"), raw)
            self.assertEqual(data["error"]["code"], "rejected", raw)
        finally:
            self.start_fake_server()
        self.assertEqual([], self.delivered_posts(), raw)

    def test_steering_is_delivered_and_marked_in_log(self):
        self.start_active_run()
        self.touch_run_log()
        self.write_state({"session": MAIN_SESSION, "subagents": []})

        # Ohne Kennwort darf es keine Zustellung geben.
        status, data, raw = self.post_steer()
        self.assertEqual(status, 400, raw)
        self.assertFalse(data.get("ok"), raw)

        self.password_private()

        status, data, raw = self.post_steer()
        self.assertEqual(status, 200, "Zusatzanweisung wurde nicht übermittelt: " + raw)
        self.assertTrue(data.get("ok"), raw)
        self.assertTrue(str(data.get("message") or "").strip(), raw)

        posts = self.delivered_posts()
        self.assertTrue(posts, "opencode-Server hat keine Zustellung erhalten")
        text_found = [post for post in posts if STEER_TEXT in post.get("body", "")]
        self.assertTrue(text_found, f"Zusatztext fehlt in der Zustellung: {posts}")
        self.assertTrue(all(post.get("user") == "opencode" for post in text_found), posts)
        self.assertTrue(all(post.get("auth_ok") for post in text_found), posts)

        log = self.log_text()
        self.assertIn(
            STEER_TEXT, log, "Nach der Zustellung fehlt die Kennzeile im Protokoll"
        )

    def test_steering_without_session_state_is_rejected(self):
        self.start_active_run()
        self.password_private()
        # Session unbestimmbar (Zustandsdatei fehlt) -> verweigert.
        status, data, raw = self.post_steer()
        self.assertEqual(status, 400, raw)
        self.assertFalse(data.get("ok"), raw)
        self.assertEqual(data["error"]["code"], "rejected", raw)

    def test_opencode_password_never_leaves_api_results(self):
        self.password_private()
        collected = []
        for method, path, body in (
            ("GET", "/api/subagents?name=proj", None),
            ("GET", "/api/subagent-output?name=proj&session=ses_unbekannt", None),
            ("GET", "/api/projects", None),
            ("GET", "/api/run-state?name=proj", None),
        ):
            status, data, raw = self.request(method, path, body=body)
            collected.append(raw)
            self.assertNotIn(
                SERVER_CREDENTIAL,
                raw,
                f"Kennwort in {path} lesbar: {raw}",
            )
        self.post_steer()  # ohne aktiven Lauf: rechtfertigte Verweigerung
        status, data, raw = self.request("GET", "/api/subagents?name=proj")
        self.assertNotIn(SERVER_CREDENTIAL, raw)
        self.assertNotIn(SERVER_CREDENTIAL, json.dumps(data or {}, default=str))

    def test_password_file_never_appears_in_runtime_files_or_static_data(self):
        # Auch bei Fehlkonfiguration und Logs darf das Kennwort nirgends
        # ausgeliefert werden; gescannt wird die Laufzeitumgebung.
        scan_root = self.root / "_logs"
        for path in scan_root.rglob("*"):
            if path.is_file() and path.name != "opencode.password":
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                self.assertNotIn(SERVER_CREDENTIAL, content, f"Kennwort in {path}")


if __name__ == "__main__":
    unittest.main()
