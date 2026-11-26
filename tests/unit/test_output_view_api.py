"""Ausgabeansicht (API): Steuerung, Live-Ausgabe, Subagenten, Budget und Syntaxhervorhebung.

Aufruf: python3 -m unittest tests.unit.test_output_view_api -v
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
        """Nur aktive Einträge in der Liste; der Verlauf bleibt erhalten.

        Der Test registriert einen laufenden Lauf und setzt die Startzeiten
        der Einträge hinter den Laufbeginn. Erwartung: Der abgeschlossene
        Eintrag steht nicht in der aktiven Liste; Agent, Beschreibung, Status
        und Ausgabe bleiben in ``history[]`` der Zustandsdatei erhalten.
        Fehlerfall: Der abgeschlossene Eintrag erscheint als aktiv oder sein
        Verlauf geht verloren.
        """
        self.start_active_run()
        base_started = int(time.time()) + 5
        finished = {**STATE_FILE["subagents"][0], "started": base_started + 5}
        state = {
            "session": MAIN_SESSION,
            "subagents": [
                finished,
                {**STATE_FILE["subagents"][1], "started": base_started},
            ],
            "history": [finished],
        }
        self.write_state(state)
        status, data, raw = self.request("GET", "/api/subagents?name=proj")
        self.assertEqual(status, 200, raw)
        self.assertTrue(data.get("ok"), raw)
        self.assertIsInstance(data.get("running"), bool, raw)
        self.assertEqual(data.get("session"), MAIN_SESSION, raw)
        entries = data.get("subagents")
        self.assertIsInstance(entries, list, raw)
        self.assertEqual(
            1, len(entries),
            "Nur der laufende Subagent darf in der aktiven Liste stehen: " + raw)
        by_session = {entry.get("session"): entry for entry in entries}
        self.assertNotIn(CHILD_SESSION, by_session, raw)
        running = by_session.get(CHILD_RUNNING)
        self.assertIsNotNone(running, f"erfasster laufender Eintrag fehlt: {raw}")
        self.assertEqual(running.get("status"), "running", raw)
        self.assertEqual(running.get("agent"), "general", raw)
        self.assertEqual(running.get("description"), "Sammlung läuft", raw)

        preserved = json.loads(
            (self.root / "_logs" / "proj.log.state.json").read_text(
                encoding="utf-8"))
        history = [item for item in (preserved.get("history") or [])
                   if item.get("session") == CHILD_SESSION]
        self.assertEqual(1, len(history), "Verlaufseintrag fehlt: " + raw)
        self.assertEqual("general", history[0].get("agent"), raw)
        self.assertEqual("Testzusammenfassung", history[0].get("description"), raw)
        self.assertEqual("completed", history[0].get("status"), raw)
        self.assertIn("PONG", str(history[0].get("output") or ""), raw)

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


# ===========================================================================
# Unit-Abnahme (Teil 2): Web-API des Dashboards für zielgenaue
# ===========================================================================

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


CHILD_DONE = "ses_child"
FOREIGN_SESSION = "ses_fremd"
CONTINUE_SESSION = "ses_continue"

STATE_WITH_SUBAGENTS = {
    "session": MAIN_SESSION,
    "subagents": [
        {
            "session": CHILD_DONE,
            "agent": "general",
            "description": "Testzusammenfassung",
            "prompt": "Sammle Infos",
            "status": "completed",
            "started": 1,
            "ended": 2,
            "output": "PONG",
        },
        {
            "session": CHILD_RUNNING,
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

# opencode-v2-Nachrichtenprojektion: info.role + parts mit text/reasoning/tool.
V2_MESSAGES = {
    "data": [
        {
            "info": {"role": "user"},
            "parts": [
                {"type": "text", "text": "GEHEIM-NUTZER-EINGABE"},
            ],
        },
        {
            "info": {"role": "assistant"},
            "parts": [
                {"type": "text", "text": "Erste Antwort"},
                {"type": "reasoning", "text": "nachdenkliche Zeile"},
                {"type": "text", "text": "Zweite Zeile"},
                {"type": "tool", "tool": "task",
                 "state": {"status": "completed",
                           "input": {"description": "Testzusammenfassung"}}},
                {"type": "tool", "tool": "bash",
                 "state": {"status": "running",
                           "input": {"command": "git status --short"}}},
                {"type": "tool", "tool": "read",
                 "state": {"status": "running",
                           "input": {"filePath": "src/app.js"}}},
                {"type": "tool", "tool": "grep",
                 "state": {"status": "running", "input": {}}},
            ],
        },
    ],
}

LEGACY_MESSAGES = {
    "data": [
        {
            "type": "user",
            "content": [{"type": "text", "text": "GEHEIM-ALT-EINGABE"}],
        },
        {
            "type": "assistant",
            "content": [
                {"type": "text", "text": "ALT-4711 erste Zeile"},
                {"type": "text", "text": "ALT-4711 zweite Zeile"},
            ],
        },
    ],
}


class Ap14FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """Nachbildung des opencode-Servers.

    GET-Antworten für Nachrichtenprojektionen (Pfad enthält ``/message``)
    kommen aus der von Tests geschriebenen Datei ``messages_path``; alle
    übrigen GET-Pfade antworten mit ``{"ok":true}``. Jede Anfrage (GET und
    POST) wird in ``record_path`` protokolliert, damit ein Test sowohl die
    angefragte Nachrichtenbegrenzung (limit=200) als auch die tatsächliche
    Zustellung einer Zusatzanweisung beweisen kann. POST nimmt eine
    Anweisung nur mit gültiger Basic-Auth (Benutzer „opencode“, Kennwort aus
    ``credential_path``) an — niemals vorgetäuschter Erfolg.
    """

    context = None  # dict(messages_path, record_path, credential_path)

    def log_message(self, *args):
        return

    def _record(self, body=""):
        with open(self.context["record_path"], "a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "method": self.command,
                        "path": self.path,
                        "auth_ok": self._auth_ok(),
                        "body": body,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    def _auth_ok(self):
        try:
            password = Path(self.context["credential_path"]).read_text(
                encoding="utf-8"
            ).strip()
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
        if "/message" in self.path:
            try:
                payload = json.loads(
                    Path(self.context["messages_path"]).read_text(
                        encoding="utf-8"
                    )
                )
            except (OSError, ValueError):
                payload = {"data": []}
            self._send_json(200, payload)
            return
        self._send_json(200, {"ok": True})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        self._record(body)
        if self._auth_ok():
            self._send_json(200, {"ok": True})
        else:
            self._send_json(401, {"ok": False})


def make_ap14_fake_handler(context):
    def build():
        handler = type("BoundHandler", (BaseHTTPRequestHandler,), {})
        for attribute, value in Ap14FakeOpenCodeHandler.__dict__.items():
            if not attribute.startswith("__"):
                setattr(handler, attribute, value)
        handler.context = context
        return handler
    return build()


FAKE_TMUX = r'''#!/usr/bin/env python3
"""Zeichnet tmux-Aufrufe auf und verhält sich wie ein frischer Server."""
import json
import os
import sys

args = sys.argv[1:]
# V-026: Laufsitzungen liegen auf einem eigenen tmux-Server; der optionale
# Zusatz ``-L <socket>`` steht dann vor dem eigentlichen Befehl.
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


class Ap14ApiFixture(unittest.TestCase):
    """Dashboard, isoliertes Projekt, tmux- und opencode-Attrappe."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        cls.project.mkdir()
        (cls.project / ".vibe").mkdir()
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n"
            "AGENT=test-agent\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL="true"\n',
            encoding="utf-8",
        )
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] AP14 Ausgabeüberarbeitung\n"
            "  Beschreibung: Test\n",
            encoding="utf-8",
        )
        project_agent = cls.project / ".opencode" / "agents" / "test-agent.md"
        project_agent.parent.mkdir(parents=True)
        project_agent.write_text(
            "---\ndescription: Testagent\nmode: primary\n---\n"
            "Du bist der Coding-Agent der Arbeitspakete.\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "init", "-q", "-b", "main", str(cls.project)],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(cls.project), "config", "user.name", "Test"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(cls.project), "config", "user.email",
             "test@example.invalid"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(cls.project), "add", "-A"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(cls.project), "commit", "-q", "-m",
             "Ausgangsstand"],
            check=True, capture_output=True,
        )
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        for name in ("test-agent", "code-reviewer"):
            (cls.agents / (name + ".md")).write_text(
                "---\ndescription: Testagent\nmode: primary\n---\n"
                "Du bist der Coding-Agent der Arbeitspakete.\n",
                encoding="utf-8",
            )
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
        cls.port = free_port()
        cls.oc_port = free_port()
        cls.context = {
            "credential_path": str(cls.log_dir / "opencode.password"),
            "record_path": str(cls.root / "fake-opencode.requests.jsonl"),
            "messages_path": str(cls.root / "messages.json"),
        }
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), make_ap14_fake_handler(cls.context)
        )
        cls._fake_http.daemon_threads = True
        cls._fake_thread = threading.Thread(target=cls._fake_http.serve_forever)
        cls._fake_thread.daemon = True
        cls._fake_thread.start()
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

    @classmethod
    def build_env(cls):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_") or key in (
                "TMUX", "TMUX_PANE",
            ):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "VIBE_OPENCODE_PORT": str(cls.oc_port),
                "VIBE_INSTALL": str(cls.root / "_toolchain"),
                "VIBE_RUNTIME": str(cls.log_dir),
                "VIBE_STATE": str(cls.state_dir),
                "VIBE_AGENTS_DIR": str(cls.agents),
                "VIBE_CONFIG_FILE": str(
                    cls.home / ".config" / "vibe" / "config.json"
                ),
                "VIBE_STORAGE_LOCK_DIR": str(cls.home / "locks"),
                "HOME": str(cls.home),
                "XDG_CONFIG_HOME": str(cls.home / ".config"),
                "TMPDIR": str(cls.root / "tmp"),
                "PATH": str(cls.fakebin) + os.pathsep + env.get("PATH", ""),
                "FAKE_TMUX_LOG": str(cls.tmux_log),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        (cls.root / "tmp").mkdir(exist_ok=True)
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
        try:
            cls._fake_http.shutdown()
            cls._fake_http.server_close()
            cls._fake_thread.join(timeout=5)
        except Exception:
            pass
        cls.tmp.cleanup()

    # ---------- Helfer ----------

    def setUp(self):
        # Jeder Test startet ohne Laufregister, ohne Zustandsdatei, ohne
        # Pi-Auswahl und ohne aufgezeichnete Anfragen.
        for path in (
            self.log_dir / "proj.log.state.json",
            self.log_dir / "runs.json",
            self.state_dir / "harness.json",
            self.tmux_log,
            self.root / "fake-opencode.requests.jsonl",
            self.root / "messages.json",
        ):
            if path.exists():
                path.unlink()

    def clear_requests(self):
        path = Path(self.context["record_path"])
        if path.exists():
            path.unlink()

    def requests(self):
        path = Path(self.context["record_path"])
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def write_state(self, data):
        path = self.log_dir / "proj.log.state.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def write_messages(self, payload):
        path = Path(self.context["messages_path"])
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def select_pi(self):
        (self.state_dir / "harness.json").write_text(
            json.dumps({"harness": "pi"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def password_private(self, value=SERVER_CREDENTIAL):
        path = self.log_dir / "opencode.password"
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
        return path

    def start_active_run(self):
        subprocess.run(
            [
                sys.executable, str(RUNS_PY), "start",
                "--runtime", str(self.log_dir),
                "--project", str(self.project.resolve()),
                "--name", "proj", "--key", "proj", "--agent", "test-agent",
                "--session", "vibe-proj",
                "--state", "running",
            ],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def request(
        self,
        method,
        path,
        body=None,
        token=True,
        extra_headers=None,
    ):
        if body is not None:
            encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        else:
            encoded = None
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if token is True:
            headers["X-Token"] = self.token
        elif isinstance(token, str):
            headers["X-Token"] = token
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        headers["Origin"] = f"http://127.0.0.1:{self.port}"
        headers["Sec-Fetch-Site"] = "same-origin"
        headers.update(extra_headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
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

    def new_session_commands(self):
        """Die per Attrappe aufgezeichneten tmux-„new-session“-Befehle."""
        if not self.tmux_log.exists():
            return []
        records = [
            json.loads(line)
            for line in self.tmux_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return [
            " ".join(record["args"])
            for record in records
            if record.get("args", [])[:1] == ["new-session"]
        ]

    @staticmethod
    def ok_flag(payload):
        return bool(payload) and payload.get("ok") is True

    @staticmethod
    def message_of(payload):
        if not isinstance(payload, dict):
            return ""
        return str(
            payload.get("message")
            or (payload.get("error") or {}).get("message")
            or ""
        )


class SteerTargetTest(Ap14ApiFixture):
    """AK: Anweisungen an den Hauptagenten und an jeden erfassten Subagenten
    des aktiven Laufs; fremde Sessions werden abgelehnt; Pi bleibt gesperrt."""

    def setUp(self):
        super().setUp()
        self.password_private()
        self.start_active_run()
        self.write_state(STATE_WITH_SUBAGENTS)

    def post_steer(self, text=STEER_TEXT, session=None):
        body = {"name": "proj", "text": text}
        if session is not None:
            body["session"] = session
        self.clear_requests()
        return self.request("POST", "/api/steer", body=body)

    def deliveries(self):
        return [
            entry for entry in self.requests()
            if entry["method"] == "POST" and "/prompt" in entry["path"]
        ]

    def run_log_path(self):
        """Der Laufprotokoll-Pfad des aktiven Testlaufs ``proj``."""
        return self.log_dir / "proj.log"

    def run_log_lines(self):
        path = self.run_log_path()
        if not path.exists():
            return []
        return path.read_text(encoding="utf-8", errors="replace").splitlines()

    @staticmethod
    def target_label(session):
        """Zielbezeichnung aus der erfassten Zustandsdatei: '<Agent> (<Session>)'
        bei erfasstem Agentennamen, sonst nur die Session."""
        entries = [
            sub for sub in STATE_WITH_SUBAGENTS.get("subagents", [])
            if sub.get("session") == session
        ]
        agent = entries[0].get("agent", "") if entries else ""
        return f"{agent} ({session})" if agent else session

    def assert_log_marker(self, label):
        """Nach der Zustellung steht der Zielmarker genau einmal im Laufprotokoll."""
        expected = (
            f"[Dashboard] Zusatzanweisung an {label} übermittelt: {STEER_TEXT}"
        )
        marker_lines = [
            line for line in self.run_log_lines() if "[Dashboard]" in line
        ]
        self.assertEqual(
            [expected], marker_lines,
            f"Laufprotokoll enthält den Zielmarker nicht genau einmal als "
            f"{expected!r}: {self.run_log_lines()!r}",
        )

    def test_steer_without_session_writes_the_target_marker_to_the_run_log(self):
        """Regression F19 mit Protokollmarker: Nach der Zustellung an die
        Hauptsession (ohne ``session``-Feld) steht der Zielmarker im
        Laufprotokoll und die Rückmeldung nennt das Ziel. Das Fixture erfasst
        für die Hauptsession keinen Agentennamen, daher nennt der Marker
        konsistent zur Implementierung nur die Session."""
        self.run_log_path().unlink(missing_ok=True)
        label = self.target_label(MAIN_SESSION)

        status, data, raw = self.post_steer()

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        self.assertEqual(
            f"Zusatzanweisung an {label} übermittelt.",
            self.message_of(data),
            f"Rückmeldung nennt nicht das Ziel: {raw}",
        )
        self.assert_log_marker(label)

    def test_steer_to_captured_subagent_writes_the_target_marker_to_the_run_log(self):
        """Nach der Zustellung an einen erfassten Subagenten nennen
        Protokollmarker und Rückmeldung Agentenname und Session (dynamisch
        aus dem erfassten Eintrag der Zustandsdatei abgeleitet)."""
        self.run_log_path().unlink(missing_ok=True)
        label = self.target_label(CHILD_RUNNING)

        status, data, raw = self.post_steer(session=CHILD_RUNNING)

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        self.assertEqual(
            f"Zusatzanweisung an {label} übermittelt.",
            self.message_of(data),
            f"Rückmeldung nennt nicht das Ziel: {raw}",
        )
        self.assert_log_marker(label)

    def test_steering_without_session_targets_the_main_session(self):
        """Regression F19: Ohne Session-Feld geht die Anweisung an die
        Hauptsession des aktiven Laufs."""
        status, data, raw = self.post_steer()
        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        posts = self.deliveries()
        self.assertTrue(posts, "opencode-Server hat nichts erhalten")
        self.assertEqual(
            1, len(posts), f"Genau eine Zustellung erwartet: {posts}"
        )
        self.assertIn(f"/api/session/{MAIN_SESSION}/prompt", posts[0]["path"])
        self.assertIn(STEER_TEXT, posts[0]["body"], posts)

    def test_steering_with_session_targets_the_running_subagent(self):
        status, data, raw = self.post_steer(session=CHILD_RUNNING)
        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        posts = self.deliveries()
        self.assertTrue(posts, "Zusatzanweisung kam nicht beim Subagenten an")
        self.assertEqual(
            1, len(posts), f"Genau eine Zustellung erwartet: {posts}"
        )
        self.assertIn(
            f"/api/session/{CHILD_RUNNING}/prompt", posts[0]["path"],
            f"Zustellung ging nicht an den Subagenten: {posts}",
        )
        self.assertIn(STEER_TEXT, posts[0]["body"], posts)
        self.assertNotIn(
            MAIN_SESSION, posts[0]["path"],
            "Die Hauptsession darf parallel nicht beliefert werden",
        )

    def test_steering_with_session_targets_a_captured_subagent(self):
        status, data, raw = self.post_steer(session=CHILD_DONE)
        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        posts = self.deliveries()
        self.assertTrue(posts, "Zustellung fehlt")
        self.assertIn(f"/api/session/{CHILD_DONE}/prompt", posts[0]["path"])
        self.assertIn(STEER_TEXT, posts[0]["body"], posts)

    def test_steering_with_explicit_main_session_targets_the_main_session(self):
        status, data, raw = self.post_steer(session=MAIN_SESSION)
        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        posts = self.deliveries()
        self.assertTrue(posts, "Zustellung fehlt")
        self.assertIn(f"/api/session/{MAIN_SESSION}/prompt", posts[0]["path"])

    def test_steering_rejects_foreign_sessions_without_delivery(self):
        status, data, raw = self.post_steer(session=FOREIGN_SESSION)
        self.assertFalse(
            self.ok_flag(data),
            f"Fremde Session wurde akzeptiert: {raw}",
        )
        self.assertTrue(
            self.message_of(data).strip(),
            f"Ablehnung ohne verständliche Meldung: {raw}",
        )
        self.assertEqual([], self.deliveries(), raw)

    def test_pi_steer_stays_forbidden_with_known_wording(self):
        self.select_pi()
        status, data, raw = self.post_steer()
        self.assertFalse(
            self.ok_flag(data), f"Pi darf keine Zusatzanweisungen zulassen: {raw}"
        )
        message = self.message_of(data)
        self.assertIn(
            "Zusatzanweisungen sind bei Pi nicht möglich",
            message,
            f"Bekannter Hinweistext fehlt: {message}",
        )
        self.assertEqual([], self.deliveries(), raw)


class ContinueEndpointTest(Ap14ApiFixture):
    """AK: Continue setzt einen gestoppten Lauf in derselben Session fort;
    Verweigerungen sind verständlich und starten nichts."""

    def test_continue_is_token_protected(self):
        status, data, raw = self.request(
            "POST", "/api/continue", body={"name": "proj"}, token=False
        )
        self.assertEqual(403, status, raw)
        self.assertEqual(
            "unauthorized", (data or {}).get("error", {}).get("code"), raw
        )
        self.assertEqual([], self.new_session_commands(), raw)

    def test_continue_continues_the_captured_session(self):
        self.write_state({"session": CONTINUE_SESSION, "subagents": []})

        status, data, raw = self.request("POST", "/api/continue", {"name": "proj"})

        self.assertEqual(200, status, raw)
        self.assertTrue(
            self.ok_flag(data),
            "Continue mit erfasster Session wurde nicht angenommen: " + raw,
        )
        self.assertTrue(self.message_of(data).strip(), raw)
        commands = self.new_session_commands()
        self.assertTrue(
            commands, "Continue hat keinen Lauf gestartet (tmux-Attrappe leer)"
        )
        joined = "\n".join(commands)
        self.assertIn(
            f"VIBE_CONTINUE_SESSION={CONTINUE_SESSION}",
            joined,
            "Der Startbefehl exportiert die Session nicht an den Läufer: "
            + joined,
        )

    def test_continue_refuses_while_a_run_is_active(self):
        self.start_active_run()
        self.write_state({"session": CONTINUE_SESSION, "subagents": []})

        status, data, raw = self.request("POST", "/api/continue", {"name": "proj"})

        self.assertFalse(
            self.ok_flag(data), f"Continue bei aktivem Lauf erlaubt: {raw}"
        )
        message = self.message_of(data)
        self.assertTrue(
            ("gestoppt" in message)
            or ("Fortsetz" in message and "Lauf" in message),
            f"Meldung nennt nicht, dass Fortsetzen nur bei gestopptem Lauf "
            f"möglich ist: {message}",
        )
        self.assertEqual(
            [], self.new_session_commands(),
            "Bei aktivem Lauf darf Continue keinen Lauf starten",
        )

    def test_continue_refuses_without_a_captured_session(self):
        status, data, raw = self.request("POST", "/api/continue", {"name": "proj"})

        self.assertFalse(
            self.ok_flag(data), f"Continue ohne erfasste Session erlaubt: {raw}"
        )
        self.assertTrue(
            self.message_of(data).strip(),
            f"Ablehnung ohne verständliche Meldung: {raw}",
        )
        self.assertEqual([], self.new_session_commands(), raw)

    def test_continue_refuses_for_pi_with_no_session_reason(self):
        self.select_pi()
        self.write_state({"session": CONTINUE_SESSION, "subagents": []})

        status, data, raw = self.request("POST", "/api/continue", {"name": "proj"})

        self.assertFalse(
            self.ok_flag(data), f"Continue bei Pi erlaubt: {raw}"
        )
        message = self.message_of(data)
        self.assertIn("Pi", message, f"Meldung nennt Pi nicht: {message}")
        self.assertIn(
            "--no-session", message,
            f"Meldung nennt die --no-session-Begründung nicht: {message}",
        )
        self.assertEqual([], self.new_session_commands(), raw)


class LiveOutputTest(Ap14ApiFixture):
    """AK: Vollständigere Live-Ausgabe eines laufenden Subagenten in beiden
    Nachrichtenprojektionen; Nutzer-Nachrichten bleiben außen vor."""

    def setUp(self):
        super().setUp()
        self.password_private()
        self.write_state(STATE_WITH_SUBAGENTS)

    def live(self, session=CHILD_RUNNING):
        return self.request(
            "GET",
            f"/api/subagent-output?name=proj&session={session}",
        )

    def test_live_output_renders_the_v2_projection(self):
        self.write_messages(V2_MESSAGES)

        status, data, raw = self.live()

        self.assertEqual(200, status, raw)
        self.assertTrue(
            self.ok_flag(data), f"Live-Ausgabe der v2-Projektion fehlt: {raw}"
        )
        text = str(data.get("text") or "")
        for expected in (
            "Erste Antwort",
            "Zweite Zeile",
            "[Denken] nachdenkliche Zeile",
            "[Werkzeug] task — completed: Testzusammenfassung",
            "[Werkzeug] bash — running: git status --short",
            "[Werkzeug] read — running: src/app.js",
            "[Werkzeug] grep — running",
        ):
            self.assertIn(
                expected, text,
                f"Erwartete Zeile fehlt in der Live-Ausgabe: {expected!r} "
                f"in {text!r}",
            )
        self.assertNotIn(
            "GEHEIM-NUTZER-EINGABE", text,
            "Nutzer-Nachrichten dürfen nicht erscheinen",
        )

    def test_live_output_renders_the_legacy_projection(self):
        self.write_messages(LEGACY_MESSAGES)

        status, data, raw = self.live()

        self.assertEqual(200, status, raw)
        self.assertTrue(
            self.ok_flag(data), f"Live-Ausgabe der Alt-Form fehlt: {raw}"
        )
        text = str(data.get("text") or "")
        self.assertIn("ALT-4711 erste Zeile", text, text)
        self.assertIn("ALT-4711 zweite Zeile", text, text)
        self.assertNotIn("GEHEIM-ALT-EINGABE", text, text)

    def test_live_output_requests_at_most_200_messages(self):
        self.write_messages(V2_MESSAGES)

        status, data, raw = self.live()
        self.assertEqual(200, status, raw)

        message_requests = [
            entry for entry in self.requests()
            if entry["method"] == "GET" and "/message" in entry["path"]
        ]
        self.assertTrue(
            message_requests,
            "Die Live-Ausgabe hat keine Nachrichtenprojektion angefragt",
        )
        for entry in message_requests:
            self.assertIn(
                "limit=200", entry["path"],
                f"Nachrichtenabruf ohne limit=200: {entry['path']}",
            )
            self.assertNotIn(
                "limit=500", entry["path"],
                f"Nachrichtenabruf mit unzulässigem Limit: {entry['path']}",
            )


# ===========================================================================
# Unit-Abnahme (Teil 2): Datenqualität der Ausgabe-API
# ===========================================================================

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


STEER_TEXT_b11 = "Bitte die Ausgabe vollständig anzeigen"
SERVER_CREDENTIAL_b11 = "geheim-B11-4711"

CHRONO_MESSAGES = {
    "data": [
        {"info": {"role": "user"},
         "parts": [{"type": "text", "text": "NUTZER-EINGABE"}]},
        {"info": {"role": "assistant"},
         "parts": [{"type": "text", "text": "CHRONO-1"}]},
        {"info": {"role": "assistant"},
         "parts": [{"type": "text", "text": "CHRONO-2"}]},
        {"info": {"role": "assistant"},
         "parts": [{"type": "text", "text": "CHRONO-3"}]},
    ]
}


class B11FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """Lokaler opencode-Testserver ohne Modellaufrufe.

    ``GET .../message`` gibt die in ``messages_path`` hinterlegten Nachrichten
    aus. opencode v2.2.7 liefert sie standardmäßig neueste zuerst; nur mit
    ``order=asc`` kommt die chronologische Reihenfolge. Genau dieses Verhalten
    bildet die Attrappe ab. Jede Anfrage wird protokolliert.
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
        if "/message" in self.path:
            try:
                payload = json.loads(Path(self.context["messages_path"]).read_text(
                    encoding="utf-8"))
            except (OSError, ValueError):
                payload = {"data": []}
            if "order=asc" not in self.path:
                messages = payload.get("data") if isinstance(payload, dict) else []
                payload = {"data": list(reversed(messages or []))}
            self._send_json(200, payload)
            return
        self._send_json(200, {"ok": True})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        self._record(body)
        if self._auth_ok():
            self._send_json(200, {"ok": True})
        else:
            self._send_json(401, {"ok": False})


def make_b11_fake_handler(context):
    def build():
        handler = type("BoundHandler", (BaseHTTPRequestHandler,), {})
        for attribute, value in B11FakeOpenCodeHandler.__dict__.items():
            if not attribute.startswith("__"):
                setattr(handler, attribute, value)
        handler.context = context
        return handler
    return build()


FAKE_TMUX_b11 = r'''#!/usr/bin/env python3
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


class B11ApiFixture(unittest.TestCase):
    """Dashboard, isoliertes Projekt, tmux- und opencode-Attrappe."""

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
            "# FEEDBACK\n\n- [ ] B11 Ausgabeansicht\n  Beschreibung: Test\n",
            encoding="utf-8")
        agent_path = cls.project / ".opencode" / "agents" / "test-agent.md"
        agent_path.parent.mkdir(parents=True)
        agent_path.write_text(
            "---\ndescription: Testagent\nmode: primary\n---\n"
            "Du bist der Coding-Agent der Arbeitspakete.\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", "-b", "main", str(cls.project)],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(cls.project), "config", "user.name",
                        "Test"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(cls.project), "config", "user.email",
                        "test@example.invalid"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(cls.project), "add", "-A"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(cls.project), "commit", "-q", "-m",
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
        tmux.write_text(FAKE_TMUX_b11, encoding="utf-8")
        tmux.chmod(0o755)
        cls.tmux_log = cls.root / "tmux.log"
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.port = free_port()
        cls.oc_port = free_port()
        cls.context = {
            "credential_path": str(cls.log_dir / "opencode.password"),
            "record_path": str(cls.root / "fake-opencode.requests.jsonl"),
            "messages_path": str(cls.root / "messages.json"),
        }
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), make_b11_fake_handler(cls.context))
        cls._fake_http.daemon_threads = True
        cls._fake_thread = threading.Thread(target=cls._fake_http.serve_forever)
        cls._fake_thread.daemon = True
        cls._fake_thread.start()
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.env = cls.build_env()
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
                    + (cls.root / "web-server.log").read_text(
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
        (cls.root / "tmp").mkdir(exist_ok=True)
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
        cls.server_log.close()
        try:
            cls._fake_http.shutdown()
            cls._fake_http.server_close()
            cls._fake_thread.join(timeout=5)
        except Exception:
            pass
        cls.tmp.cleanup()

    # ---------- Helfer ----------

    def setUp(self):
        for path in (self.log_dir / "proj.log.state.json",
                     self.log_dir / "runs.json",
                     self.state_dir / "harness.json",
                     self.tmux_log,
                     Path(self.context["record_path"]),
                     Path(self.context["messages_path"])):
            if path.exists():
                path.unlink()

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

    def write_messages(self, payload):
        path = Path(self.context["messages_path"])
        path.write_text(json.dumps(payload, ensure_ascii=False),
                        encoding="utf-8")
        return path

    def password_private(self, value=SERVER_CREDENTIAL_b11):
        path = self.log_dir / "opencode.password"
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
        return path

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

    def get_subagents(self):
        return self.request("GET", "/api/subagents?name=proj")

    def requests(self):
        path = Path(self.context["record_path"])
        if not path.exists():
            return []
        return [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def deliveries(self):
        return [entry for entry in self.requests()
                if entry["method"] == "POST" and "/prompt" in entry["path"]]

    def new_session_commands(self):
        if not self.tmux_log.exists():
            return []
        records = [json.loads(line) for line in
                   self.tmux_log.read_text(encoding="utf-8").splitlines()
                   if line.strip()]
        return [" ".join(record["args"]) for record in records
                if record.get("args", [])[:1] == ["new-session"]]

    @staticmethod
    def ok_flag(payload):
        return bool(payload) and payload.get("ok") is True

    @staticmethod
    def message_of(payload):
        if not isinstance(payload, dict):
            return ""
        return str(payload.get("message")
                   or (payload.get("error") or {}).get("message") or "")

    def running_entry(self, session, agent, started, output="", description=""):
        return {
            "session": session,
            "agent": agent,
            "description": description or (agent + " arbeitet"),
            "prompt": "Kurzer Auftrag",
            "status": "running",
            "started": int(started),
            "ended": 0,
            "output": output,
        }


class SubagentListTest(B11ApiFixture):
    """AK6: /api/subagents — aktueller Lauf, neueste zuerst, kompakt."""

    def test_subagents_only_lists_entries_of_the_current_run(self):
        """AK6: Eintrag eines früheren Laufs erscheint nicht.

        Vorbedingung: Laufregister läuft (Startzeit jetzt); Zustandsdatei
        enthält einen abgeschlossenen Eintrag mit ``started`` eine Stunde vor
        Laufbeginn und einen laufenden Eintrag mit ``started`` nach Laufbeginn.
        Aktion: GET /api/subagents.
        Erwartung: Nur der Eintrag des aktuellen Laufs (ses_aktuell) wird
        geliefert; ses_alt fehlt.
        Fehlerfall: Der alte Eintrag wird weiterhin ausgeliefert.
        """
        self.register_run("running")
        now = int(time.time())
        self.write_state({
            "session": MAIN_SESSION,
            "subagents": [
                {"session": "ses_alt", "agent": "alt-agent",
                 "description": "früherer Lauf", "prompt": "alt",
                 "status": "completed", "started": now - 3600,
                 "ended": now - 3500, "output": "ALTE-AUSGABE"},
                self.running_entry("ses_aktuell", "neu-agent", now + 2),
            ],
        })

        status, data, raw = self.get_subagents()

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        sessions = [entry.get("session")
                    for entry in (data or {}).get("subagents") or []]
        self.assertIn("ses_aktuell", sessions,
                      "Eintrag des aktuellen Laufs fehlt: " + raw)
        self.assertNotIn(
            "ses_alt", sessions,
            "Eintrag eines früheren Laufs wurde ausgeliefert: " + raw)

    def test_subagents_are_sorted_newest_first(self):
        """AK6: Reihenfolge neueste zuerst.

        Vorbedingung: drei Einträge des aktuellen Laufs mit aufsteigender
        Startzeit (ses_alt, ses_mittel, ses_neu).
        Aktion: GET /api/subagents.
        Erwartung: [ses_neu, ses_mittel, ses_alt].
        Fehlerfall: Dateireihenfolge oder aufsteigende Sortierung.
        """
        self.register_run("running")
        now = int(time.time())
        self.write_state({
            "session": MAIN_SESSION,
            "subagents": [
                self.running_entry("ses_alt", "a", now + 10),
                self.running_entry("ses_mittel", "b", now + 20),
                self.running_entry("ses_neu", "c", now + 30),
            ],
        })

        status, data, raw = self.get_subagents()

        self.assertEqual(200, status, raw)
        sessions = [entry.get("session")
                    for entry in (data or {}).get("subagents") or []]
        self.assertEqual(
            ["ses_neu", "ses_mittel", "ses_alt"], sessions,
            "Subagenten sind nicht neueste zuerst sortiert: " + raw)

    def test_subagents_payload_carries_no_oversized_prompt(self):
        """AK6: Keine riesigen Prompt-Felder in der Subagentenliste.

        Vorbedingung: laufender Eintrag mit einem 200 000 Zeichen langen
        ``prompt``.
        Aktion: GET /api/subagents.
        Erwartung: Antwort bleibt unter 8 KiB, enthält keine 1 000 Zeichen
        lange Zeichenkette; Session, Agent und Status sind vorhanden.
        Fehlerfall: Der Prompt reist vollständig durch die API.
        """
        self.register_run("running")
        huge_prompt = "RIESIG-" + ("x" * 200000)
        now = int(time.time())
        entry = self.running_entry("ses_gross", "tester", now + 30)
        entry["prompt"] = huge_prompt
        self.write_state({"session": MAIN_SESSION, "subagents": [entry]})

        status, data, raw = self.get_subagents()

        self.assertEqual(200, status, raw)
        self.assertLess(
            len(raw.encode("utf-8")), 8192,
            f"Die Subagentenliste ist mit {len(raw)} Zeichen zu groß")
        self.assertNotIn(
            "x" * 1000, raw,
            "Ein riesiges prompt-Feld wurde ungekürzt ausgeliefert")
        entries = (data or {}).get("subagents") or []
        self.assertEqual(1, len(entries), raw)
        self.assertEqual("ses_gross", entries[0].get("session"), raw)
        self.assertEqual("tester", entries[0].get("agent"), raw)
        self.assertEqual("running", entries[0].get("status"), raw)


class SubagentOutputOrderTest(B11ApiFixture):
    """AK6: /api/subagent-output — chronologisch, unbekannte Session klar."""

    def test_subagent_output_is_chronological_and_requests_ascending(self):
        """AK6: Chronologische Ausgabe dank order=asc.

        Vorbedingung: laufender Subagent ohne gespeicherte Ausgabe; die
        opencode-Attrappe liefert Nachrichten standardmäßig neueste zuerst und
        nur mit ``order=asc`` in chronologischer Reihenfolge.
        Aktion: GET /api/subagent-output.
        Erwartung: Der Abruf enthält ``order=asc``; im Text steht CHRONO-1 vor
        CHRONO-2 vor CHRONO-3.
        Fehlerfall: Abruf ohne order=asc oder rückwärts ausgegebene Zeilen.
        """
        self.password_private()
        self.register_run("running")
        now = int(time.time())
        entry = self.running_entry("ses_live", "tester", now + 30)
        entry["output"] = ""
        self.write_state({"session": MAIN_SESSION, "subagents": [entry]})
        self.write_messages(CHRONO_MESSAGES)

        status, data, raw = self.request(
            "GET", "/api/subagent-output?name=proj&session=ses_live")

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        text = str((data or {}).get("text") or "")
        positions = [text.find(marker)
                     for marker in ("CHRONO-1", "CHRONO-2", "CHRONO-3")]
        self.assertTrue(all(pos >= 0 for pos in positions),
                        f"Chronologische Zeilen fehlen: {text!r}")
        self.assertEqual(sorted(positions), positions,
                         f"Ausgabe ist nicht chronologisch: {text!r}")
        message_requests = [item for item in self.requests()
                            if item["method"] == "GET"
                            and "/message" in item["path"]]
        self.assertTrue(message_requests,
                        "Die Ausgabe wurde nicht beim opencode-Server abgerufen")
        for item in message_requests:
            self.assertIn("order=asc", item["path"],
                          "Chronologie wurde nicht angefordert: " + item["path"])

    def test_subagent_output_rejects_an_unknown_session(self):
        """AK6: Unbekannte Session wird klar abgelehnt, ohne Serverabfrage.

        Vorbedingung: Zustandsdatei enthält die Session ses_unbekannt nicht.
        Aktion: GET /api/subagent-output?session=ses_unbekannt.
        Erwartung: ``ok:false``, nicht leere Meldung; keine GET-Anfrage an
        ``/message`` im opencode-Testserver.
        Fehlerfall: Erfolg, leere Meldung oder unnötige Serverabfrage.
        """
        self.register_run("running")
        self.write_state({"session": MAIN_SESSION, "subagents": []})

        status, data, raw = self.request(
            "GET", "/api/subagent-output?name=proj&session=ses_unbekannt")

        self.assertEqual(200, status, raw)
        self.assertFalse(self.ok_flag(data),
                         f"Unbekannte Session wurde akzeptiert: {raw}")
        self.assertTrue(self.message_of(data).strip(),
                        f"Ablehnung ohne Meldung: {raw}")
        message_requests = [item for item in self.requests()
                            if item["method"] == "GET"
                            and "/message" in item["path"]]
        self.assertEqual([], message_requests,
                         "Unbekannte Session löste eine Serverabfrage aus")


class SteerTargetValidationTest(B11ApiFixture):
    """Regression: zielgenaue Anweisungen bleiben erhalten."""

    def setUp(self):
        super().setUp()
        self.password_private()
        self.register_run("running")
        now = int(time.time())
        self.write_state({
            "session": MAIN_SESSION,
            "subagents": [self.running_entry("ses_laeuft", "tester", now + 10)],
        })

    def post_steer(self, session=None):
        body = {"name": "proj", "text": STEER_TEXT_b11}
        if session is not None:
            body["session"] = session
        return self.request("POST", "/api/steer", body)

    def test_steer_targets_main_and_running_subagent(self):
        """Regression: Anweisung erreicht Hauptsession und laufenden Subagenten.

        Vorbedingung: aktiver Lauf, Hauptsession und laufender Subagent.
        Aktion: POST /api/steer ohne ``session`` und mit ``ses_laeuft``.
        Erwartung: Zwei Zustellungen an ``/api/session/ses_main/prompt`` und
        ``/api/session/ses_laeuft/prompt`` mit dem Text.
        Fehlerfall: Falsches Ziel oder keine Zustellung.
        """
        status, data, raw = self.post_steer()
        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        status, data, raw = self.post_steer(session="ses_laeuft")
        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)

        posts = self.deliveries()
        self.assertEqual(2, len(posts), f"Genau zwei Zustellungen: {posts}")
        self.assertIn(f"/api/session/{MAIN_SESSION}/prompt", posts[0]["path"])
        self.assertIn(f"/api/session/ses_laeuft/prompt", posts[1]["path"])
        for post in posts:
            self.assertIn(STEER_TEXT_b11, post["body"], post)

    def test_steer_rejects_a_foreign_session_without_delivery(self):
        """Regression: fremde Session wird abgelehnt und nicht beliefert.

        Vorbedingung: aktiver Lauf.
        Aktion: POST /api/steer mit ``ses_fremd``.
        Erwartung: ``ok:false`` mit Meldung, keine Zustellung.
        Fehlerfall: Fremde Session erhält die Anweisung.
        """
        status, data, raw = self.post_steer(session=FOREIGN_SESSION)

        self.assertFalse(self.ok_flag(data),
                         f"Fremde Session wurde akzeptiert: {raw}")
        self.assertTrue(self.message_of(data).strip(), raw)
        self.assertEqual([], self.deliveries(), raw)


class ContinueRefusalTest(B11ApiFixture):
    """Regression: Continue ohne Voraussetzung startet nichts."""

    def test_continue_refuses_without_a_captured_session(self):
        """Regression: ohne Session keine Fortsetzung.

        Vorbedingung: kein aktiver Lauf und keine Zustandsdatei mit Session.
        Aktion: POST /api/continue.
        Erwartung: ``ok:false`` mit verständlicher Meldung; die tmux-Attrappe
        zeichnet kein ``new-session`` auf.
        Fehlerfall: Continue startet trotzdem einen Lauf.
        """
        status, data, raw = self.request(
            "POST", "/api/continue", {"name": "proj"})

        self.assertFalse(self.ok_flag(data),
                         f"Continue ohne Session wurde angenommen: {raw}")
        self.assertTrue(self.message_of(data).strip(),
                        f"Ablehnung ohne verständliche Meldung: {raw}")
        self.assertEqual([], self.new_session_commands(),
                         "Continue hat trotz fehlender Session einen Lauf gestartet")


class OutputBudgetTest(B11ApiFixture):
    """Review Medium 3: /api/subagents liefert ``output`` nur als kleinen Tail.

    Die Liste bleibt kompakt: Das ``output``-Feld eines Eintrags wird auf
    einen Tail von höchstens 4 KiB begrenzt (Anfang verworfen, Ende
    erhalten). Die vollständige Live-Ausgabe bleibt über
    ``/api/subagent-output`` abrufbar (eigene Fälle in
    ``SubagentOutputTest``).
    """

    def test_subagents_output_is_capped_to_a_small_tail(self):
        """``output`` in der Liste bleibt auf einen 4-KiB-Tail begrenzt.

        Vorbedingung: laufender Registereintrag; Eintrag mit rund 200 KiB
        gespeicherter Ausgabe (ANFANG-4711 am Anfang, ENDE-4711 am Ende).
        Aktion: GET /api/subagents.
        Erwartung: Antwort bleibt unter 8 KiB; ``output`` ist höchstens
        4 KiB, enthält ENDE-4711 und nicht ANFANG-4711.
        Fehlerfall: Die gespeicherte Ausgabe reist ungekürzt durch die API.
        """
        self.register_run("running")
        now = int(time.time())
        entry = self.running_entry("ses_gross", "tester", now + 30)
        entry["output"] = (
            "ANFANG-4711\n" + "m" * 200_000 + "\nENDE-4711"
        )
        self.write_state({"session": MAIN_SESSION, "subagents": [entry]})

        status, data, raw = self.get_subagents()

        self.assertEqual(200, status, raw)
        entries = (data or {}).get("subagents") or []
        self.assertEqual(1, len(entries), raw)
        output = str(entries[0].get("output") or "")
        self.assertLessEqual(
            len(output.encode("utf-8")), 4096,
            "Das output-Feld ist mit %d Bytes zu groß" % len(output))
        self.assertNotIn(
            "ANFANG-4711", output,
            "Der Anfang wurde nicht verworfen (Tail-Semantik)")
        self.assertIn(
            "ENDE-4711", output,
            "Das Ende der Ausgabe ging verloren")
        self.assertLess(
            len(raw.encode("utf-8")), 8192,
            "Die Subagentenliste ist mit %d Zeichen zu groß" % len(raw))


class RunTimeFilterTest(B11ApiFixture):
    """Review Minor 4: Zeitfilter-Grenzfälle (vereinbarte Semantik).

    ``run_start_epoch`` kann für einen Registereintrag ohne lesbare
    Startzeit ``None`` liefern. Vereinbart ist Fail-open mit Dokumentation:

    * Ohne lesbare Startzeit liefert ``/api/subagents`` alle Einträge der
      Zustandsdatei (statt still nichts).
    * Ein Eintrag mit unbekannter Startzeit (``started`` 0 oder ``None``)
      bleibt unter einem aktiven Lauf sichtbar, statt am Zeitvergleich
      unbemerkt wegzufallen.
    """

    def corrupt_run_start(self, value="kein-datum"):
        """Verdirbt die ``started``-Zeit des neuesten Registereintrags."""
        path = self.log_dir / "runs.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        runs = data.get("runs") or []
        self.assertTrue(runs, "Kein Registereintrag vorhanden")
        runs[-1]["started"] = value
        path.write_text(json.dumps(data, ensure_ascii=False),
                        encoding="utf-8")

    def test_unreadable_run_start_delivers_all_state_entries(self):
        """Ohne lesbare Startzeit erscheinen alle aktiven Einträge (fail-open).

        Vorbedingung: laufender Registereintrag mit defekter
        ``started``-Zeit; Zustandsdatei mit einem Eintrag eines früheren
        Standes und einem Eintrag des Laufs. Der frühere Eintrag ist
        abgeschlossen und gehört nicht in die aktive Liste.
        Aktion: GET /api/subagents.
        Erwartung: Der aktive Eintrag wird trotz defekter Startzeit geliefert,
        der abgeschlossene nicht.
        Fehlerfall: Stille leere Liste oder ein abgeschlossener Eintrag als
        aktiv.
        """
        self.register_run("running")
        self.corrupt_run_start()
        now = int(time.time())
        self.write_state({
            "session": MAIN_SESSION,
            "subagents": [
                {"session": "ses_alt", "agent": "alt-agent",
                 "description": "früherer Stand", "prompt": "alt",
                 "status": "completed", "started": now - 3600,
                 "ended": now - 3500, "output": "ALTE-AUSGABE"},
                self.running_entry("ses_aktuell", "tester", now + 2),
            ],
        })

        status, data, raw = self.get_subagents()

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        sessions = [entry.get("session")
                    for entry in (data or {}).get("subagents") or []]
        self.assertEqual(
            {"ses_aktuell"}, set(sessions),
            "Fail-open verletzt oder abgeschlossener Eintrag aktiv: %r (%s)"
            % (sessions, raw))

    def test_entry_with_unknown_start_stays_visible_during_a_run(self):
        """Eintrag ohne ``started`` verschwindet nicht unter aktivem Lauf.

        Vorbedingung: laufender Registereintrag; Zustandsdatei mit einem
        normalen Eintrag, einem Eintrag mit ``started`` 0 und einem Eintrag
        mit ``started`` ``None``.
        Aktion: GET /api/subagents.
        Erwartung: Alle drei Einträge bleiben sichtbar.
        Fehlerfall: Die Einträge ohne Startzeit fallen unbemerkt aus der
        Liste (aktueller Fehler).
        """
        self.register_run("running")
        now = int(time.time())
        entry_zero = self.running_entry("ses_ohne_zeit", "tester", 0)
        entry_none = self.running_entry("ses_keine_zeit", "tester", now + 5)
        entry_none["started"] = None
        self.write_state({
            "session": MAIN_SESSION,
            "subagents": [
                self.running_entry("ses_mit_zeit", "tester", now + 10),
                entry_zero,
                entry_none,
            ],
        })

        status, data, raw = self.get_subagents()

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        sessions = [entry.get("session")
                    for entry in (data or {}).get("subagents") or []]
        self.assertEqual(
            {"ses_mit_zeit", "ses_ohne_zeit", "ses_keine_zeit"}, set(sessions),
            "Einträge mit unbekannter Startzeit fielen aus der Liste: %r (%s)"
            % (sessions, raw))


# ===========================================================================
# Unit-Abnahme: Die Subagenten-API nennt den aktuell arbeitenden Agenten
# ===========================================================================

import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


AGENT = "vibe-agent"


class ActiveAgentApiFixture(unittest.TestCase):
    """Startet das echte Dashboard im isolierten VIBE-Root (eigener Port,
    eigene HOME-/Laufzeitpfade, keine tmux-Sitzung) und beschreibt den
    Laufregister-Eintrag mit bin/vibe_runs.py — demselben Werkzeug der
    echten Läufer."""

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
        cls.log_dir = cls.root / "_logs"
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.port = free_port()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                "TMUX", "TMUX_PANE",
            ):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "VIBE_INSTALL": str(cls.root / "_toolchain"),
                "VIBE_RUNTIME": str(cls.log_dir),
                "VIBE_STATE": str(cls.root / "_toolchain"),
                "HOME": str(cls.root / "home"),
                "VIBE_CONFIG_FILE": str(
                    cls.root / "home" / ".config" / "vibe" / "config.json"
                ),
                "TMPDIR": str(cls.root / "tmp"),
                "TMUX_TMPDIR": str(cls.tmux_dir),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        (cls.root / "tmp").mkdir(parents=True)
        cls.env = env
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=cls.server_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 30
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
        cls.tmp.cleanup()

    # ---------- Helfer ----------

    def setUp(self):
        # Sauberer Start je Testfall: kein Register, keine Zustandsdatei.
        register = self.log_dir / "runs.json"
        if register.exists():
            register.unlink()
        state = self.log_dir / "proj.log.state.json"
        if state.exists():
            state.unlink()

    def write_register(self, agent=AGENT, state="running", key="proj"):
        """Vorbedingung Register: Eintrag mit bin/vibe_runs.py (keine Hand-
        nachbildung des Formats) — dieselbe Quelle wie ein echter Läufer."""
        # runs.json wurde in setUp geleert; jede Vorbedingung entsteht neu.
        result = subprocess.run(
            [
                sys.executable, str(RUNS_PY), "start",
                "--runtime", str(self.log_dir),
                "--project", str(self.project.resolve()),
                "--name", "proj", "--key", key, "--agent", agent,
                "--state", state,
            ],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(
            result.returncode, 0,
            "Vorbedingung Registereintrag fehlgeschlagen: "
            + result.stdout + result.stderr,
        )

    def get_subagents(self):
        """Fachliche Abfrage: GET /api/subagents mit Token (Header und
        t=-Parameter, wie die Oberfläche die Route aufrufen darf)."""
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        headers = {"X-Token": self.token}
        try:
            connection.request(
                "GET",
                "/api/subagents?name=proj&t=" + self.token,
                headers=headers,
            )
            response = connection.getresponse()
            body = response.read().decode("utf-8", "replace")
            try:
                payload = json.loads(body)
            except ValueError:
                payload = None
            return response.status, payload, body
        finally:
            connection.close()


class ActiveRunAgentTest(ActiveAgentApiFixture):
    """AK1: Solange ein Lauf aktiv ist, zeigt die Ausgabemaske den Agenten.
    Die API ist die fachliche Quelle des Namens für den Anzeigeteil."""

    def test_active_run_reports_the_registered_agent(self):
        self.write_register(agent=AGENT, state="running")
        status, data, raw = self.get_subagents()
        self.assertEqual(status, 200, raw)
        self.assertTrue(isinstance(data, dict) and data.get("ok"), raw)
        self.assertTrue(
            data.get("running"),
            "Vorbedingung aktiver Lauf muss gemeldet werden: " + raw,
        )
        self.assertEqual(
            data.get("agent"), AGENT,
            "Die API muss den Agentennamen des Laufregisters melden: " + raw,
        )

    def test_starting_run_reports_the_registered_agent(self):
        # starting ist ebenfalls ein LIVE-Zustand (bin/vibe_runs.py).
        self.write_register(agent=AGENT, state="starting")
        status, data, raw = self.get_subagents()
        self.assertEqual(status, 200, raw)
        self.assertTrue(isinstance(data, dict) and data.get("ok"), raw)
        self.assertTrue(data.get("running"), raw)
        self.assertEqual(data.get("agent"), AGENT, raw)

    def test_the_newest_register_entry_decides(self):
        self.write_register(agent="halt-agent", state="running")
        self.write_register(agent=AGENT, state="running")
        status, data, raw = self.get_subagents()
        self.assertEqual(status, 200, raw)
        self.assertEqual(
            data.get("agent"), AGENT,
            "Der jüngste Registereintrag ist maßgeblich: " + raw,
        )


class InactiveRunAgentTest(ActiveAgentApiFixture):
    """AK1: Ohne aktiven Lauf wird kein Agentenname angezeigt."""

    def test_finished_run_reports_no_agent(self):
        self.write_register(agent=AGENT, state="finished")
        status, data, raw = self.get_subagents()
        self.assertEqual(status, 200, raw)
        self.assertTrue(isinstance(data, dict) and data.get("ok"), raw)
        self.assertFalse(data.get("running"), raw)
        self.assertIn(
            data.get("agent", ""), (None, ""),
            "Ein beendeter Lauf darf keinen Agentennamen zeigen: " + raw,
        )

    def test_without_register_entry_no_agent_is_reported(self):
        status, data, raw = self.get_subagents()
        self.assertEqual(status, 200, raw)
        self.assertTrue(isinstance(data, dict) and data.get("ok"), raw)
        self.assertFalse(data.get("running"), raw)
        self.assertIn(
            data.get("agent", ""), (None, ""),
            "Ohne Register darf kein Agentenname erscheinen: " + raw,
        )


# ===========================================================================
# Unit-Abnahme: Live-Subagentenausgabe statt eingefrorenem Text
# ===========================================================================

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


CHILD_SESSION_f30 = "ses_kind"
STATIC_OUTPUT = ("The subagent is working in the background "
                 "(sessionID: ses_kind). STATISCH-4711")
LIVE_TEXT_A = "LIVE-A-4711: Der Subagent schreibt seine erste Fassung."
LIVE_TEXT_B = "LIVE-B-4711: Der Subagent schreibt eine zweite Fassung."
SERVER_CREDENTIAL_f30 = "geheim-F30-4711"

USER_ONLY_MESSAGES = {
    "data": [
        {"info": {"role": "user"},
         "parts": [{"type": "text", "text": "NUTZER-EINGABE"}]},
    ]
}

LIVE_MESSAGES = {
    "data": [
        {"info": {"role": "assistant"},
         "parts": [{"type": "text", "text": LIVE_TEXT_A}]},
        {"info": {"role": "assistant"},
         "parts": [{"type": "text", "text": LIVE_TEXT_B}]},
    ]
}


class F30FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """Lokaler opencode-Testserver mit pro Test umschaltbarem Verhalten.

    Der Modus steht in ``context["mode"]`` und darf zwischen Tests geändert
    werden (das Attribut des Handlers wird bei jeder Anfrage gelesen):

    * ``live``  — /message liefert ``messages_path``; opencode v2 liefert
      Nachrichten standardmäßig neueste zuerst, nur mit ``order=asc``
      chronologisch (dieses Verhalten bildet die Attrappe nach).
    * ``empty`` — /message liefert nur eine Nutzernachricht, d. h. keinen
      verwertbaren Live-Text.
    * ``error`` — /message antwortet mit HTTP 500 (Serverstörung).
    Jede Anfrage wird protokolliert.
    """

    context = None

    def log_message(self, *args):
        return

    def _record(self, body=""):
        with open(self.context["record_path"], "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "method": self.command,
                "path": self.path,
                "body": body,
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
        if "/message" in self.path:
            mode = self.context.get("mode") or "live"
            if mode == "error":
                self._send_json(500, {"ok": False})
                return
            if mode == "empty":
                self._send_json(200, USER_ONLY_MESSAGES)
                return
            try:
                payload = json.loads(Path(self.context["messages_path"]).read_text(
                    encoding="utf-8"))
            except (OSError, ValueError):
                payload = {"data": []}
            if "order=asc" not in self.path:
                messages = payload.get("data") if isinstance(payload, dict) else []
                payload = {"data": list(reversed(messages or []))}
            self._send_json(200, payload)
            return
        # Alle anderen Routen (u. a. /api/session, /api/session/active)
        # liefern eine leere Lage, damit die Zustandsdatei maßgeblich bleibt.
        self._send_json(200, {"ok": True})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        self._record(body)
        self._send_json(200, {"ok": True})


def make_f30_fake_handler(context):
    def build():
        handler = type("BoundHandler", (BaseHTTPRequestHandler,), {})
        for attribute, value in F30FakeOpenCodeHandler.__dict__.items():
            if not attribute.startswith("__"):
                setattr(handler, attribute, value)
        handler.context = context
        return handler
    return build()


FAKE_TMUX_f30 = r'''#!/usr/bin/env python3
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


class F30ApiFixture(unittest.TestCase):
    """Dashboard, isoliertes Projekt, tmux- und opencode-Attrappe."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        cls.project.mkdir()
        (cls.project / ".vibe").mkdir()
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=test-agent\nTESTER=test-agent\n"
            "REVIEWER=code-reviewer\n",
            encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] F30 Sub Agent view\n  Beschreibung: Test\n",
            encoding="utf-8")
        agent_path = cls.project / ".opencode" / "agents" / "test-agent.md"
        agent_path.parent.mkdir(parents=True)
        agent_path.write_text(
            "---\ndescription: Testagent\nmode: primary\n---\n"
            "Du bist der Coding-Agent der Arbeitspakete.\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", "-b", "main", str(cls.project)],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(cls.project), "config", "user.name",
                        "Test"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(cls.project), "config", "user.email",
                        "test@example.invalid"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(cls.project), "add", "-A"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(cls.project), "commit", "-q", "-m",
                        "Ausgangsstand"], check=True, capture_output=True)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        (cls.agents / "test-agent.md").write_text(
            "---\ndescription: Testagent\nmode: primary\n---\n"
            "Du bist der Coding-Agent der Arbeitspakete.\n", encoding="utf-8")
        cls.fakebin = cls.root / "fakebin"
        cls.fakebin.mkdir()
        tmux = cls.fakebin / "tmux"
        tmux.write_text(FAKE_TMUX_f30, encoding="utf-8")
        tmux.chmod(0o755)
        cls.tmux_log = cls.root / "tmux.log"
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.port = free_port()
        cls.oc_port = free_port()
        cls.context = {
            "record_path": str(cls.root / "fake-opencode.requests.jsonl"),
            "messages_path": str(cls.root / "messages.json"),
            "mode": "live",
        }
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), make_f30_fake_handler(cls.context))
        cls._fake_http.daemon_threads = True
        cls._fake_thread = threading.Thread(target=cls._fake_http.serve_forever)
        cls._fake_thread.daemon = True
        cls._fake_thread.start()
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.env = cls.build_env()
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
                    + (cls.root / "web-server.log").read_text(
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
        (cls.root / "tmp").mkdir(exist_ok=True)
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
        cls.server_log.close()
        try:
            cls._fake_http.shutdown()
            cls._fake_http.server_close()
            cls._fake_thread.join(timeout=5)
        except Exception:
            pass
        cls.tmp.cleanup()

    # ---------- Helfer ----------

    def setUp(self):
        for path in (self.log_dir / "proj.log.state.json",
                     self.log_dir / "runs.json",
                     self.state_dir / "harness.json",
                     self.tmux_log,
                     Path(self.context["record_path"]),
                     Path(self.context["messages_path"])):
            if path.exists():
                path.unlink()
        self.context["mode"] = "live"
        self.password_private()

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

    def write_state(self, entry_output=STATIC_OUTPUT, session=CHILD_SESSION_f30):
        """Laufenden Subagenten mit wählbarer erfasster Ausgabe anlegen."""
        now = int(time.time())
        entry = {
            "session": session,
            "agent": "tester",
            "description": "tester arbeitet",
            "prompt": "Kurzer Auftrag",
            "status": "running",
            "started": now + 5,
            "ended": 0,
            "output": entry_output,
        }
        (self.log_dir / "proj.log.state.json").write_text(
            json.dumps({"session": MAIN_SESSION, "subagents": [entry]},
                       ensure_ascii=False),
            encoding="utf-8")
        return entry

    def write_messages(self, payload):
        Path(self.context["messages_path"]).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def password_private(self, value=SERVER_CREDENTIAL_f30):
        path = self.log_dir / "opencode.password"
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
        return path

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

    def get_output(self, session=CHILD_SESSION_f30):
        return self.request(
            "GET", "/api/subagent-output?name=proj&session=" + session)

    def message_requests(self):
        path = Path(self.context["record_path"])
        if not path.exists():
            return []
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry["method"] == "GET" and "/message" in entry["path"]:
                records.append(entry)
        return records

    @staticmethod
    def ok_flag(payload):
        return bool(payload) and payload.get("ok") is True

    @staticmethod
    def message_of(payload):
        if not isinstance(payload, dict):
            return ""
        return str(payload.get("message")
                   or (payload.get("error") or {}).get("message") or "")


class LiveOutputPreferredTest(F30ApiFixture):
    """AK1/AK7 (Backend): die Live-Ausgabe gewinnt über den statischen Text."""

    def test_live_output_wins_over_captured_state_output(self):
        """AK1: Live-Ausgabe wird geliefert, obwohl die Zustandsdatei voll ist.

        Vorbedingung: laufender Subagent; erfasste Ausgabe in der
        Zustandsdatei nicht leer (statischer Werkzeugtext); opencode-Attrappe
        liefert zwei Assistant-Nachrichten.
        Aktion: GET /api/subagent-output.
        Erwartung: ok:true; der Text enthält LIVE-A-4711 und LIVE-B-4711 in
        chronologischer Reihenfolge; STATISCH-4711 erscheint nicht.
        Fehlerfall (aktueller Fehler): der statische erfasste Text gewinnt.
        """
        self.register_run("running")
        self.write_state()
        self.write_messages(LIVE_MESSAGES)

        status, data, raw = self.get_output()

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        text = str((data or {}).get("text") or "")
        self.assertIn("LIVE-A-4711", text,
                      f"Live-Ausgabe fehlt: {text!r}")
        self.assertIn("LIVE-B-4711", text,
                      f"Live-Ausgabe unvollständig: {text!r}")
        self.assertNotIn(
            "STATISCH-4711", text,
            "Der statische erfasste Text wurde statt der Live-Ausgabe "
            f"geliefert: {text!r}")
        pos_a = text.find("LIVE-A-4711")
        pos_b = text.find("LIVE-B-4711")
        self.assertLess(pos_a, pos_b,
                        f"Ausgabe ist nicht chronologisch: {text!r}")

    def test_second_poll_returns_refreshed_live_output(self):
        """AK1/AK7: Ein zweiter Abruf liefert den aktualisierten Text.

        Vorbedingung: wie AK1; die Attrappe liefert zunächst LIVE-A-4711,
        danach (entsprechend weiterer Agentenausgabe) LIVE-B-4711 allein.
        Aktion: Zwei aufeinanderfolgende GET-Abrufe.
        Erwartung: Der erste Abruf enthält LIVE-A-4711, der zweite
        LIVE-B-4711; der zweite enthält den ersten Text nicht mehr.
        Fehlerfall (aktueller Fehler): Beide Abrufe liefern denselben
        statischen erfassten Text — die Ausgabe ist eingefroren.
        """
        self.register_run("running")
        self.write_state()
        self.write_messages({"data": [
            {"info": {"role": "assistant"},
             "parts": [{"type": "text", "text": LIVE_TEXT_A}]},
        ]})

        status, data, raw = self.get_output()
        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        first_text = str((data or {}).get("text") or "")
        self.assertIn("LIVE-A-4711", first_text,
                      f"Erster Abruf liefert keine Live-Ausgabe: {first_text!r}")

        self.write_messages({"data": [
            {"info": {"role": "assistant"},
             "parts": [{"type": "text", "text": LIVE_TEXT_B}]},
        ]})
        status, data, raw = self.get_output()
        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        second_text = str((data or {}).get("text") or "")
        self.assertIn("LIVE-B-4711", second_text,
                      f"Zweiter Abruf ist nicht aktualisiert: {second_text!r}")
        self.assertNotIn(
            "LIVE-A-4711", second_text,
            f"Der zweite Abruf friert den ersten Text ein: {second_text!r}")


class CapturedOutputFallbackTest(F30ApiFixture):
    """AK2: erfasste Ausgabe bleibt Fallback (Sandbox, Serverstörung)."""

    def test_captured_output_is_used_when_live_output_is_empty(self):
        """AK2: Kein Live-Text → erfasste Ausgabe wird geliefert.

        Vorbedingung: erfasste Ausgabe nicht leer; der Server liefert für
        /message nur eine Nutzernachricht (kein verwertbarer Live-Text).
        Aktion: GET /api/subagent-output.
        Erwartung: ok:true; der Text ist die erfasste Ausgabe (STATISCH-4711).
        Fehlerfall: Ausgabeverlust, obwohl die erfasste Ausgabe vorliegt.
        """
        self.register_run("running")
        self.write_state()
        self.context["mode"] = "empty"

        status, data, raw = self.get_output()

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        text = str((data or {}).get("text") or "")
        self.assertIn("STATISCH-4711", text,
                      f"Erfasste Ausgabe ging verloren: {text!r}")

    def test_captured_output_is_used_without_server_credentials(self):
        """AK2: Ohne Kennwort wird die erfasste Ausgabe geliefert.

        Vorbedingung: erfasste Ausgabe nicht leer; keine Kennwortdatei, d. h.
        der opencode-Server ist nicht authentifizierbar.
        Aktion: GET /api/subagent-output.
        Erwartung: ok:true mit der erfassten Ausgabe; keine /message-Anfrage.
        Fehlerfall: Verlust der erfassten Ausgabe oder unnötige Abfrage.
        """
        self.register_run("running")
        self.write_state()
        (self.log_dir / "opencode.password").unlink()

        status, data, raw = self.get_output()

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        text = str((data or {}).get("text") or "")
        self.assertIn("STATISCH-4711", text,
                      f"Erfasste Ausgabe ging verloren: {text!r}")
        self.assertEqual([], self.message_requests(),
                         "Ohne Kennwort wurde trotzdem der Server befragt")

    def test_captured_output_is_used_when_the_server_fails(self):
        """AK2: Bei einer Serverstörung bleibt die erfasste Ausgabe erhalten.

        Vorbedingung: erfasste Ausgabe nicht leer; die Attrappe antwortet auf
        /message mit HTTP 500.
        Aktion: GET /api/subagent-output.
        Erwartung: ok:true mit der erfassten Ausgabe (Fallback).
        Fehlerfall: Der Fehler führt zu ok:false oder leerer Ausgabe.
        """
        self.register_run("running")
        self.write_state()
        self.context["mode"] = "error"

        status, data, raw = self.get_output()

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        text = str((data or {}).get("text") or "")
        self.assertIn("STATISCH-4711", text,
                      f"Erfasste Ausgabe ging verloren: {text!r}")


class ClearMessageAndRegressionTest(F30ApiFixture):
    """AK3/AK4: klare Leer-Meldung und bestehende Ablehnung bleiben."""

    def test_no_output_anywhere_keeps_the_clear_message(self):
        """AK3: Beide Quellen leer → bestehende klare Meldung bleibt.

        Vorbedingung: erfasste Ausgabe leer; die Attrappe liefert keinen
        verwertbaren Live-Text.
        Aktion: GET /api/subagent-output.
        Erwartung: ok:false; die Meldung enthält „liegt noch keine Ausgabe
        vor"; das Statusfeld nennt den Eintragsstatus.
        Fehlerfall: Andere oder leere Meldung oder fälschlich ok:true.
        """
        self.register_run("running")
        self.write_state(entry_output="")
        self.context["mode"] = "empty"

        status, data, raw = self.get_output()

        self.assertEqual(200, status, raw)
        self.assertFalse(self.ok_flag(data),
                         f"Leerer Fall wurde als Erfolg gemeldet: {raw}")
        message = self.message_of(data)
        self.assertIn("liegt noch keine Ausgabe vor", message,
                      f"Bestehende Meldung wurde verändert: {message!r}")
        self.assertEqual("running", str((data or {}).get("status") or ""),
                         raw)

    def test_unknown_session_is_rejected_without_a_server_query(self):
        """AK4: Unbekannte Session wird abgelehnt, ohne den Server zu fragen.

        Vorbedingung: Zustandsdatei ohne die angefragte Session.
        Aktion: GET /api/subagent-output?session=ses_unbekannt.
        Erwartung: ok:false mit verständlicher Meldung; keine /message-Anfrage.
        Fehlerfall: Erfolg, leere Meldung oder unnötige Serverabfrage.
        """
        self.register_run("running")
        self.write_state()

        status, data, raw = self.get_output(session="ses_unbekannt")

        self.assertEqual(200, status, raw)
        self.assertFalse(self.ok_flag(data),
                         f"Unbekannte Session wurde akzeptiert: {raw}")
        self.assertTrue(self.message_of(data).strip(),
                        f"Ablehnung ohne Meldung: {raw}")
        self.assertEqual([], self.message_requests(),
                         "Unbekannte Session löste eine Serverabfrage aus")

    def test_live_fetch_is_attempted_even_when_output_is_captured(self):
        """AK4/AK1: Auch mit erfasster Ausgabe wird chronologisch live gelesen.

        Vorbedingung: erfasste Ausgabe nicht leer; Server erreichbar und
        authentifizierbar.
        Aktion: GET /api/subagent-output.
        Erwartung: Es gab mindestens eine /message-Anfrage, und jede solche
        Anfrage enthält ``order=asc``.
        Fehlerfall (aktueller Fehler): Es wird gar nicht beim Server
        angefragt, weil die erfasste Ausgabe bevorzugt wird.
        """
        self.register_run("running")
        self.write_state()
        self.write_messages(LIVE_MESSAGES)

        status, data, raw = self.get_output()

        self.assertEqual(200, status, raw)
        requests = self.message_requests()
        self.assertTrue(
            requests,
            "Die Live-Ausgabe wurde nicht beim opencode-Server abgerufen "
            "(erfasste Ausgabe wurde bevorzugt): " + raw)
        for item in requests:
            self.assertIn("order=asc", item["path"],
                          "Chronologie wurde nicht angefordert: "
                          + item["path"])


# ===========================================================================
# Unit-Abnahme: Live-Ausgabe der Subagenten über den privaten Laufserver
# ===========================================================================

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
from urllib.parse import parse_qs, urlparse


CHILD_SESSION_b14 = "ses_kind"
LIVE_TEXT_PROJECT_A = "PROJEKT-A-4711: Live-Ausgabe des ersten Projekts."
LIVE_TEXT_PROJECT_B = "PROJEKT-B-4711: Live-Ausgabe des zweiten Projekts."
PASSWORD_GLOBAL = "global-4711"
PASSWORD_PRIVATE = "privat-4711"


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
            # Echtes opencode begrenzt ``limit`` auf 200: limit>200 endet mit
            # HTTP 400 InvalidRequestError. Die Attrappe bildet das nach,
            # damit Tests nicht versehentlich ein unzulässiges Limit
            # akzeptieren.
            limit_text = parse_qs(urlparse(self.path).query).get(
                "limit", [""])[0]
            try:
                limit = int(limit_text)
            except ValueError:
                limit = None
            if limit is not None and limit > 200:
                self._send_json(400, {
                    "_tag": "InvalidRequestError",
                    "message": ("Expected a value less than or equal to 200\n"
                                '  at ["limit"]'),
                    "kind": "Query",
                })
                return
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
        session = session or CHILD_SESSION_b14
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
        session = session or CHILD_SESSION_b14
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


class RealOpencodeLimitTest(B14ApiFixture):
    """B14 erneut: echtes opencode akzeptiert nur ``limit`` ≤ 200.

    Der Fake-Laufserver validiert das Limit wie der echte Server (HTTP 400
    InvalidRequestError bei limit>200). Damit belegt diese Klasse, dass die
    Live-Ausgabe nicht mehr blind am Limit scheitert und der ausgehende
    Nachrichtenabruf das akzeptierte Limit verwendet.
    """

    def _live_setup(self):
        self.register_run()
        self.write_state()
        self.start_run_server()
        self.set_messages({"data": [
            {"info": {"role": "assistant"},
             "parts": [{"type": "text", "text": LIVE_TEXT_A}]},
        ]})
        self.write_server_file()

    def test_real_opencode_limit_cap_still_serves_live_output(self):
        """Limit>200 liefert HTTP 400; das Dashboard muss trotzdem LIVE liefern.

        Vorbedingung: aktiver Lauf mit gültiger Serverdatei; der
        Laufserver verhält sich wie echtes opencode und lehnt
        ``/message?limit=500`` mit HTTP 400 InvalidRequestError ab
        (limit≤200 wird beantwortet); die Attrappe kennt LIVE-A-4711.
        Aktion: GET /api/subagent-output.
        Erwartung: ok:true mit LIVE-A-4711, nicht der statische erfasste
        Text.
        Fehlerfall (Ausgangsstand): HTTP 400 → leere Live-Ausgabe → die
        Karte zeigt STATISCH-4711.
        """
        self._live_setup()

        status, data, raw = self.get_output()

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        text = str((data or {}).get("text") or "")
        self.assertIn("LIVE-A-4711", text,
                      f"Live-Ausgabe fehlt trotz Limit-Grenze: {text!r}")
        self.assertNotIn(
            "STATISCH-4711", text,
            "Der statische erfasste Text wurde statt der LIVE-Ausgabe "
            f"geliefert: {text!r}")

    def test_message_request_uses_the_accepted_limit(self):
        """Der Nachrichtenabruf verwendet exakt ``limit=200&order=asc``.

        Vorbedingung: wie oben; der Laufserver zeichnet die Anfrage auf.
        Aktion: GET /api/subagent-output.
        Erwartung: Genau eine Anfrage an
        ``/api/session/<session>/message?limit=200&order=asc``; kein
        ``limit=500``.
        Fehlerfall (Ausgangsstand): ``limit=500`` → HTTP 400.
        """
        self._live_setup()

        status, data, raw = self.get_output()
        self.assertEqual(200, status, raw)

        expected = ("/api/session/%s/message?limit=200&order=asc"
                    % CHILD_SESSION_b14)
        paths = [entry["path"] for entry in self.message_requests()]
        self.assertIn(expected, paths,
                      f"Akzeptiertes Nachrichtenlimit fehlt: {paths}")
        self.assertNotIn(
            "/api/session/%s/message?limit=500&order=asc" % CHILD_SESSION_b14,
            paths, f"Unzulässiges Limit angefragt: {paths}")


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


# ===========================================================================
# Quellverträge: Hervorhebung der Agentenausgabe
# ===========================================================================

import re
import unittest
from pathlib import Path

WEB_FILES = tuple(
    REPO / "bin" / "web" / name
    for name in ("index.html", "styles.css", "app.js", "i18n.js")
)
# Echte Injektionsaufrufe; der erläuternde F19-Kommentar („kein innerHTML“)
# soll nicht als Treffer zählen.
INJECTION_PATTERN = re.compile(
    r"\.innerHTML\b|\binnerHTML\s*=[^=]|insertAdjacentHTML|"
    r"\bouterHTML\b|document\.write\s*\(")

REQUIRED_HL_CLASSES = ("hl-head", "hl-err", "hl-tool", "hl-sub")


def page_source():
    return "\n".join(path.read_text(encoding="utf-8") for path in WEB_FILES)


class AP16WebUiHighlightingTest(unittest.TestCase):
    def test_web_ui_never_interprets_log_content_as_html(self):
        page = page_source()
        found = INJECTION_PATTERN.findall(page)
        self.assertEqual(
            found, [],
            "Die Oberfläche nutzt HTML-Injektionsaufrufe; Protokollinhalt "
            "darf nie als HTML interpretiert werden: " + repr(found))

    def test_f19_highlight_classes_remain_scoped_to_the_run_log(self):
        styles = (REPO / "bin" / "web" / "styles.css").read_text(
            encoding="utf-8")
        for name in REQUIRED_HL_CLASSES:
            self.assertIn(
                f"pre#log .{name}", styles,
                f"Der dokumentierte F19-Vertrag fehlt: Regel für {name} "
                "ist nicht an pre#log gebunden")


if __name__ == "__main__":
    unittest.main()
