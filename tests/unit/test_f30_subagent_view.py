"""Unit-Abnahme F30: Live-Subagentenausgabe statt eingefrorenem Text.

FEEDBACK.md F30 „Sub Agent view" meldet (belegt durch den Screenshot und die
Ursachenanalyse des Koordinators): Die Subagent-Karte zeigt für immer genau
den statischen Werkzeug-Ergebnistext („The subagent is working in the
background …"), obwohl der opencode-Server die echten Agentennachrichten der
Kind-Session liefern könnte. Ursache: Der Handler
``GET /api/subagent-output`` nutzt ``live_subagent_output(session)`` nur,
wenn die erfasste Ausgabe aus der Zustandsdatei leer ist — sie ist aber
praktisch nie leer. Fixrichtung: Live-Ausgabe zuerst; erfasste Ausgabe nur
als Fallback (Server nicht erreichbar oder Live-Ausgabe leer).

Akzeptanzkriterien und Testfälle (Zuordnung in den Docstrings):

1. test_live_output_wins_over_captured_state_output          [AK1]
   Vorbedingung: laufender Subagent mit nicht-leerer erfasster Ausgabe in
   der Zustandsdatei; opencode-Attrappe liefert Agentennachrichten.
   Aktion: GET /api/subagent-output.
   Erwartung: Die Live-Ausgabe wird geliefert, chronologisch, die erfasste
   statische Ausgabe erscheint nicht.
   Fehlerfall (aktueller Zustand): Die erfasste Ausgabe gewinnt.
2. test_second_poll_returns_refreshed_live_output            [AK1, AK7]
   Vorbedingung: wie 1; zwischen zwei Abrufen ändert sich die Live-Ausgabe.
   Aktion: Zwei aufeinanderfolgende GET-Abrufe.
   Erwartung: Der zweite Abruf liefert den neuen Text.
   Fehlerfall (aktueller Zustand): Beide Abrufe liefern den statischen Text.
3. test_captured_output_is_used_when_live_output_is_empty    [AK2]
   Vorbedingung: erfasste Ausgabe nicht leer; Server liefert nur eine
   Nutzernachricht (kein Live-Text).
   Aktion: GET /api/subagent-output.
   Erwartung: Die erfasste Ausgabe wird geliefert (ok:true).
   Fehlerfall: Ausgabeverlust bei leerer Live-Ausgabe.
4. test_captured_output_is_used_without_server_credentials   [AK2]
   Vorbedingung: erfasste Ausgabe nicht leer; keine Kennwortdatei, d. h.
   der opencode-Server ist nicht authentifizierbar.
   Aktion: GET /api/subagent-output.
   Erwartung: Erfasste Ausgabe (ok:true); keine Anfrage an den Server.
   Fehlerfall: Verlust der erfassten Ausgabe.
5. test_captured_output_is_used_when_the_server_fails        [AK2]
   Vorbedingung: erfasste Ausgabe nicht leer; Server antwortet auf
   /message mit HTTP 500.
   Aktion: GET /api/subagent-output.
   Erwartung: Erfasste Ausgabe (ok:true).
   Fehlerfall: Verlust der erfassten Ausgabe bei Serverstörung.
6. test_no_output_anywhere_keeps_the_clear_message           [AK3]
   Vorbedingung: erfasste Ausgabe leer; Server liefert keinen Live-Text.
   Aktion: GET /api/subagent-output.
   Erwartung: ok:false mit der bestehenden Meldung „liegt noch keine
   Ausgabe vor" und dem Status.
   Fehlerfall: Andere Meldung, ok:true oder leere Meldung.
7. test_unknown_session_is_rejected_without_a_server_query   [AK4]
   Vorbedingung: Zustandsdatei ohne die angefragte Session.
   Aktion: GET /api/subagent-output?session=ses_unbekannt.
   Erwartung: ok:false mit Meldung; keine /message-Anfrage.
   Fehlerfall: Erfolg oder unnötige Serverabfrage.
8. test_live_fetch_is_attempted_even_when_output_is_captured [AK4, AK1]
   Vorbedingung: erfasste Ausgabe nicht leer; Server erreichbar.
   Aktion: GET /api/subagent-output.
   Erwartung: Der Abruf der Live-Ausgabe passiert mit ``order=asc``.
   Fehlerfall (aktueller Zustand): Es wird gar nicht beim Server angefragt.

Das echte Dashboard (bin/vibe-web.py) läuft in einem isolierten VIBE-Root auf
einem freien Port; der opencode-Server ist eine lokale Attrappe, deren
Verhalten pro Test umgeschaltet werden kann (live/leer/Fehler). Keine echten
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
SERVER_CREDENTIAL = "geheim-F30-4711"

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


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
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
            "record_path": str(cls.root / "fake-opencode.requests.jsonl"),
            "messages_path": str(cls.root / "messages.json"),
            "mode": "live",
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

    def write_state(self, entry_output=STATIC_OUTPUT, session=CHILD_SESSION):
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

    def get_output(self, session=CHILD_SESSION):
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


if __name__ == "__main__":
    unittest.main()
