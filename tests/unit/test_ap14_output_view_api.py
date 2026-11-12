"""Unit-Abnahme AP14 (Teil 2): Web-API des Dashboards für zielgenaue
Zusatzanweisungen, Fortsetzen und vollständigere Live-Ausgabe.

Arbeitspaket AP14 „Komplette Überarbeitung Ausgabe“ verlangt, dass die Arbeit
aller laufenden Agenten (Hauptagent + Subagenten) live verfolgbar ist, dass
dem Hauptagenten und jedem Subagenten während des Laufs Anweisungen gesendet
werden können und dass ein Lauf in derselben Session fortgesetzt werden kann
(Continue). Pi läuft im Print-Modus (--no-session) und kann weder
Zusatzanweisungen empfangen noch eine Session fortsetzen; die Web-API meldet
das mit einer klaren Hinweismeldung (Fähigkeitsschicht, siehe
tests/unit/test_ap14_harness_capabilities.py).

Geprüfte Schnittstellen (fester Vertrag):

* ``POST /api/steer`` mit und ohne Feld ``session`` (steer_project):
  - ohne ``session``: Zustellung an die Hauptsession des aktiven Laufs
    (bisheriges Verhalten, Regression);
  - mit ``session``: Zustellung genau an diese Session, wenn sie die
    Hauptsession des Laufs oder die Session eines erfassten Subagenten des
    aktiven Laufs ist; opencode-Server erhält
    ``POST /api/session/<session>/prompt``;
  - fremde/unbekannte Sessions werden mit ``ok:false`` und verständlicher
    Meldung abgelehnt, ohne dass etwas zugestellt wird;
  - Pi: ``ok:false`` mit dem bekannten Hinweis (Wortlaut
    „Zusatzanweisungen sind bei Pi nicht möglich: …“ bleibt bestehen).
* ``POST /api/continue`` (neu, Body ``{"name": …}``):
  - token-geschützt wie alle steuernden Endpunkte;
  - Erfolg (``ok:true``), wenn kein Lauf aktiv ist und die Zustandsdatei des
    letzten Laufs (``<log>.state.json``) eine Hauptsession enthält; der
    Startbefehl exportiert ``VIBE_CONTINUE_SESSION=<Session-ID>`` an den
    Läufer (über die tmux-Aufzeichnung der capture-Ebene geprüft);
  - aktiver Lauf: ``ok:false`` mit Meldung, dass Fortsetzen nur bei
    gestopptem Lauf möglich ist;
  - keine erfasste Session: ``ok:false`` mit Meldung;
  - Pi: ``ok:false``, Meldung nennt Pi und die --no-session-Begründung.
* ``live_subagent_output(session)`` über ``GET /api/subagent-output``:
  - liest die Nachrichtenprojektion in der opencode-v2-Form
    (``{"data":[{"info":{"role":…},"parts":[…]}]}``) und der älteren Form
    (``{"data":[{…, "content":[…]}]}``);
  - Textteile unverändert, reasoning-Teile als „[Denken] “-Zeilen,
    tool-Teile je Teil als „[Werkzeug] <tool> — <status>: <detail>“ mit
    Detail aus ``state.input`` (description/command/filePath), ohne Detail
    falls leer;
  - Nutzer-Nachrichten werden übersprungen;
  - bis zu 500 Nachrichten (``GET …/message?limit=500``).

Keine echten Modellaufrufe: Der opencode-Server ist ein lokaler
Testserver, tmux ist eine aufzeichnende Attrappe (Muster aus
tests/unit/test_f27_keep_changes.py), das Projekt ist ein echtes,
isoliertes Git-Repository mit eigenem HOME und eigenen Ports.
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
CHILD_DONE = "ses_child"
CHILD_RUNNING = "ses_child2"
FOREIGN_SESSION = "ses_fremd"
CONTINUE_SESSION = "ses_continue"
STEER_TEXT = "Prüfe zuerst die Borderstellung"
SERVER_CREDENTIAL = "geheim-PASSWORT-4711"

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


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """Nachbildung des opencode-Servers.

    GET-Antworten für Nachrichtenprojektionen (Pfad enthält ``/message``)
    kommen aus der von Tests geschriebenen Datei ``messages_path``; alle
    übrigen GET-Pfade antworten mit ``{"ok":true}``. Jede Anfrage (GET und
    POST) wird in ``record_path`` protokolliert, damit ein Test sowohl die
    angefragte Nachrichtenbegrenzung (limit=500) als auch die tatsächliche
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


def make_fake_handler(context):
    def build():
        handler = type("BoundHandler", (BaseHTTPRequestHandler,), {})
        for attribute, value in _FakeOpenCodeHandler.__dict__.items():
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
            ("127.0.0.1", cls.oc_port), make_fake_handler(cls.context)
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

    def test_live_output_requests_up_to_500_messages(self):
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
                "limit=500", entry["path"],
                f"Nachrichtenabruf ohne limit=500: {entry['path']}",
            )


if __name__ == "__main__":
    unittest.main()
