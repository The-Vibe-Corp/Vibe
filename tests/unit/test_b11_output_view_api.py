"""Unit-Abnahme B11 (Teil 2): Datenqualität der Ausgabe-API.

Arbeitspaket B11 verlangt eine von Grund auf neue Ausgabeansicht. Damit die
Ansicht überhaupt live und vollständig speisen kann, wurden am Backend kleine
Anpassungen vereinbart (Arbeitspaket B11, Punkt 6):

* ``GET /api/subagents?name=<projekt>`` liefert nur Einträge des **aktuellen**
  Laufs (keine Überbleibsel früherer Läufe), neueste zuerst und ohne riesige
  ``prompt``-Felder. Der Ausgabebestandteil (``output``) darf weiterhin klein
  mitgeliefert werden; die eigentliche Live-Ausgabe kommt über
  ``/api/subagent-output``.
* ``GET /api/subagent-output?name=<projekt>&session=<id>`` liefert die Ausgabe
  in **chronologischer** Reihenfolge. opencode v2.2.7 gibt Nachrichten
  standardmäßig neueste zuerst zurück; der Abruf muss deshalb ``order=asc``
  anfordern. Eine unbekannte Session wird mit klarer Meldung abgelehnt, ohne
  den opencode-Server zu befragen.
* Die Zielauswahl von ``POST /api/steer`` (Hauptsession oder laufender
  Subagent, fremde Session abgelehnt) und die Ablehnung von
  ``POST /api/continue`` ohne Voraussetzung bleiben als bestehende Semantik
  erhalten (Regression zu F19/AP14).

Testfälle (Zuordnung in den Docstrings):

1. test_subagents_only_lists_entries_of_the_current_run            [AK6]
   Vorbedingung: laufender Registereintrag; Zustandsdatei enthält einen
   abgeschlossenen Eintrag eines früheren Laufs (``started`` eine Stunde vor
   Laufbeginn) und einen Eintrag des aktuellen Laufs (``started`` nach
   Laufbeginn).
   Aktion: GET /api/subagents.
   Erwartung: Der alte Eintrag fehlt, der aktuelle ist enthalten.
   Fehlerfall: Der alte Eintrag erscheint weiterhin.
2. test_subagents_are_sorted_newest_first                         [AK6]
   Vorbedingung: drei Einträge des aktuellen Laufs mit aufsteigender
   Startzeit.
   Aktion: GET /api/subagents.
   Erwartung: Reihenfolge absteigend nach ``started`` (neueste zuerst).
   Fehlerfall: Dateireihenfolge oder aufsteigende Sortierung.
3. test_subagents_payload_carries_no_oversized_prompt             [AK6]
   Vorbedingung: laufender Eintrag mit 200 000 Zeichen langem ``prompt``.
   Aktion: GET /api/subagents.
   Erwartung: Antwort ist kompakt (< 8 KiB), enthält keine langen
   Prompt-Zeichenketten, nennt aber Session, Agent und Status.
   Fehlerfall: Der riesige Prompt reist durch die API.
4. test_subagent_output_is_chronological_and_requests_ascending   [AK6]
   Vorbedingung: laufender Subagent, opencode-Attrappe liefert Nachrichten
   standardmäßig neueste zuerst und nur mit ``order=asc`` chronologisch.
   Aktion: GET /api/subagent-output.
   Erwartung: Abruf enthält ``order=asc``; Ausgabetext ist chronologisch
   (CHRONO-1 vor CHRONO-2 vor CHRONO-3).
   Fehlerfall: Abruf ohne ``order=asc`` oder rückwärts ausgegebener Text.
5. test_subagent_output_rejects_an_unknown_session                 [AK6]
   Vorbedingung: Zustandsdatei ohne die angefragte Session.
   Aktion: GET /api/subagent-output?session=ses_unbekannt.
   Erwartung: ``ok:false`` mit verständlicher Meldung; keine Abfrage an den
   opencode-Server.
   Fehlerfall: Erfolg, leere Meldung oder unnötige Serverabfrage.
6. test_steer_targets_main_and_running_subagent                    [Regression]
   Vorbedingung: aktiver Lauf, Hauptsession und laufender Subagent, gültiges
   Serverkennwort.
   Aktion: POST /api/steer einmal ohne/mit Hauptsession und einmal mit der
   Subagentensession.
   Erwartung: Genau die jeweilige Session erhält den Prompt.
   Fehlerfall: Falsches Ziel oder keine Zustellung.
7. test_steer_rejects_a_foreign_session_without_delivery           [Regression]
   Vorbedingung: wie 6.
   Aktion: POST /api/steer mit fremder Session.
   Erwartung: ``ok:false`` mit Meldung, keine Zustellung.
   Fehlerfall: Fremde Session wird beliefert.
8. test_continue_refuses_without_a_captured_session               [Regression]
   Vorbedingung: kein aktiver Lauf, keine Zustandsdatei/Session.
   Aktion: POST /api/continue.
   Erwartung: ``ok:false`` mit Meldung; kein Laufstart über tmux.
   Fehlerfall: Continue startet trotzdem.

9. test_subagents_output_is_capped_to_a_small_tail   [AK6, Review Medium 3]
   Vorbedingung: laufender Eintrag mit rund 200 KiB ``output``.
   Aktion: GET /api/subagents.
   Erwartung: Antwort unter 8 KiB; ``output`` ist ein Tail von höchstens
   4 KiB (ENDE-4711 erhalten, ANFANG-4711 verworfen).
   Fehlerfall: Die Ausgabe reist ungekürzt durch die API.
10. test_unreadable_run_start_delivers_all_state_entries [AK6, Review Minor 4]
   Vorbedingung: Registereintrag mit defekter ``started``-Zeit; zwei
   Einträge in der Zustandsdatei.
   Aktion: GET /api/subagents.
   Erwartung: Beide Einträge erscheinen (vereinbarte fail-open-Semantik).
   Fehlerfall: Stille leere Liste.
11. test_entry_with_unknown_start_stays_visible_during_a_run
   [AK6, Review Minor 4]
   Vorbedingung: laufender Registereintrag; Einträge mit ``started`` 0 und
   ``None`` neben einem normalen Eintrag.
   Aktion: GET /api/subagents.
   Erwartung: Alle drei Einträge bleiben sichtbar.
   Fehlerfall: Einträge ohne Startzeit fallen unbemerkt aus der Liste.

Das echte Dashboard (bin/vibe-web.py) läuft in einem isolierten VIBE-Root auf
einem freien Port; der opencode-Server ist ein lokaler Testserver. Keine
echten Modellaufrufe, keine produktive Installation, keine externen Dienste.
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
STEER_TEXT = "Bitte die Ausgabe vollständig anzeigen"
SERVER_CREDENTIAL = "geheim-B11-4711"

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


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
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
            ("127.0.0.1", cls.oc_port), make_fake_handler(cls.context))
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

    def password_private(self, value=SERVER_CREDENTIAL):
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


class SubagentOutputTest(B11ApiFixture):
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


class SteerTargetTest(B11ApiFixture):
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
        body = {"name": "proj", "text": STEER_TEXT}
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
            self.assertIn(STEER_TEXT, post["body"], post)

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
        """Ohne lesbare Startzeit erscheinen alle Einträge (fail-open).

        Vorbedingung: laufender Registereintrag mit defekter
        ``started``-Zeit; Zustandsdatei mit einem Eintrag eines früheren
        Standes und einem Eintrag des Laufs.
        Aktion: GET /api/subagents.
        Erwartung: Beide Einträge werden geliefert.
        Fehlerfall: Stille leere Liste oder Ausfall der Anfrage.
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
            {"ses_alt", "ses_aktuell"}, set(sessions),
            "Fail-open verletzt: gelieferte Sessions %r (%s)"
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


if __name__ == "__main__":
    unittest.main()
