"""Browserabnahme B14: laufende Subagent-Karte folgt dem privaten Laufserver.

FEEDBACK.md B14 „Subagenten output statisch“ (Bug): Die Ausgabefenster der
Subagenten bleiben beim ersten erfassten Text stehen. Ursache (nach
eigenem Nachprüfen der Stellen): Das Backend fragt die Live-Ausgabe stets
am gemeinsamen opencode-Server (``vibe.OC_URL``) ab; läuft kein gemeinsamer
Server, fällt ``/api/subagent-output`` auf den in der Zustandsdatei
erfassten Ersttext zurück — die Karte friert ein. Die Kartenaktualisierung
selbst (2-Sekunden-Polling, ``setText``) ist nicht defekt; es fehlt der
neue LIVE-Text.

Dies ist der geforderte Beweis im echten Browser: Das Dashboard läuft mit
einem privaten Laufserver, der NUR über die
``<Laufprotokoll>.server.json`` des aktiven Laufs erreicht wird (kein
gemeinsamer Server — der gemeinsame Port ist ein gebundener, lauschloser
Socket, jede Verbindung dorthin wird abgewiesen). Die laufende Subagent-
Karte muss beim 2-Sekunden-Polling von Text A auf Text B umspringen und
darf den statischen erfassten Ersttext nie zeigen.

Testfälle:

1. test_running_card_refreshes_through_the_private_run_server   [AK7]
   Vorbedingung: aktiver Lauf mit laufendem Subagenten samt statischer
   erfasster Ausgabe; gültige Serverdatei auf den privaten Laufserver,
   der LIVE-A-4711 liefert; kein gemeinsamer Server.
   Aktion: Ausgabebereich öffnen, auf LIVE-A-4711 warten; dann die
   Attrappe auf LIVE-B-4711 umstellen und ohne Neuladen weiter beobachten.
   Erwartung: Die Karte zeigt LIVE-A-4711 und danach LIVE-B-4711; der
   statische erfasste Text (STATISCH-4711) erscheint nie; der Laufserver
   wurde per /message angefragt.
   Fehlerfall (Ausgangsstand): Die Karte friert beim statischen Ersttext.
2. test_the_card_never_shows_the_frozen_captured_first_text      [AK7]
   Vorbedingung: wie 1.
   Aktion: Ansicht öffnen und während mehrerer Polling-Zyklen beobachten.
   Erwartung: Der statische erfasste Ersttext erscheint zu keinem
   Zeitpunkt; der erste LIVE-Text bleibt sichtbar, bis er sich ändert.
   Fehlerfall (Ausgangsstand): Der statische Ersttext bleibt stehen.

Der Fake-Laufserver lehnt ``/message`` mit ``limit>200`` wie echtes
opencode mit HTTP 400 ``InvalidRequestError`` ab; die Karte muss auch mit
dieser strengen Grenze den LIVE-Text zeigen.

Keine echten Modellaufrufe, keine produktive Installation.
"""
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

_BROWSERS = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"
RUNS_PY = REPO / "bin" / "vibe_runs.py"

AGENT = "vibe-agent"
MAIN_SESSION = "ses_main_b14"
CHILD_SESSION = "ses_kind_b14"
STATIC_OUTPUT = ("The subagent is working in the background "
                 "(sessionID: ses_kind_b14). STATISCH-4711")
LIVE_TEXT_A = "LIVE-A-4711: Der Subagent schreibt seine erste Fassung."
LIVE_TEXT_B = "LIVE-B-4711: Der Subagent schreibt eine zweite Fassung."
PASSWORD_PRIVATE = "privat-B14-4711"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _RunServerHandler(BaseHTTPRequestHandler):
    """Privater opencode-Laufserver-Attrappe (nur über die Serverdatei).

    ``/message`` liefert die Nachrichten aus ``messages_path`` (opencode v2
    liefert neueste zuerst; nur mit ``order=asc`` chronologisch — dieses
    Verhalten bildet die Attrappe nach). ``/api/session``-Routen liefern
    eine leere Lage, damit die Zustandsdatei maßgeblich bleibt. Anfragen
    werden mit Auth-Status protokolliert.
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
        encoded = "opencode:" + password
        import base64
        expected = "Basic " + base64.b64encode(encoded.encode()).decode()
        return self.headers.get("Authorization", "") == expected

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
            self._send_json(200, {"data": {}})
            return
        if "/message" in self.path:
            # Echtes opencode akzeptiert nur limit≤200; größere Werte
            # enden mit HTTP 400 InvalidRequestError.
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
            try:
                payload = json.loads(
                    Path(self.context["messages_path"]).read_text(
                        encoding="utf-8"))
            except (OSError, ValueError):
                payload = {"data": []}
            if "order=asc" not in self.path:
                messages = payload.get("data") if isinstance(payload, dict) else []
                payload = {"data": list(reversed(messages or []))}
            self._send_json(200, payload)
            return
        if self.path.startswith("/api/session"):
            self._send_json(200, {"data": []})
            return
        self._send_json(200, {"ok": True})


def make_run_handler(context):
    def build():
        handler = type("BoundHandler", (BaseHTTPRequestHandler,), {})
        for attribute, value in _RunServerHandler.__dict__.items():
            if not attribute.startswith("__"):
                setattr(handler, attribute, value)
        handler.context = context
        return handler
    return build()


class B14BrowserTest(unittest.TestCase):
    """Dashboard, Browser, privater Laufserver, toter gemeinsamer Server."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] B14 Subagenten output statisch\n"
            "  Beschreibung: Test\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True)
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        # Kein gemeinsamer Server: gebundener Socket ohne listen(); alle
        # Verbindungen dorthin werden zuverlässig abgewiesen (Bug-Nachbild).
        cls.dead_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cls.dead_socket.bind(("127.0.0.1", 0))
        cls.dead_port = cls.dead_socket.getsockname()[1]
        # Privater Laufserver des aktiven Laufs (Testprozess-Thread).
        cls.credential = cls.root / "private.password"
        cls.credential.write_text(PASSWORD_PRIVATE, encoding="utf-8")
        cls.credential.chmod(0o600)
        cls.messages_path = cls.root / "messages.json"
        cls.record_path = cls.root / "run-server.requests.jsonl"
        cls.context = {
            "credential_path": str(cls.credential),
            "messages_path": str(cls.messages_path),
            "record_path": str(cls.record_path),
        }
        cls.priv_port = free_port()
        cls._priv_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.priv_port), make_run_handler(cls.context))
        cls._priv_http.daemon_threads = True
        cls._priv_thread = threading.Thread(target=cls._priv_http.serve_forever)
        cls._priv_thread.daemon = True
        cls._priv_thread.start()
        cls.port = free_port()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                    "TMUX", "TMUX_PANE"):
                env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_OPENCODE_PORT": str(cls.dead_port),
            "VIBE_STATE": str(cls.state_dir),
            "VIBE_RUNTIME": str(cls.log_dir),
            "HOME": str(cls.root / "home"),
            "TMPDIR": str(cls.root / "tmp"),
            "TMUX_TMPDIR": str(cls.tmux_dir),
            "VIBE_CONFIG_FILE": str(
                cls.root / "home" / ".config" / "vibe" / "config.json"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        cls.env = env
        cls.server_log = open(cls.root / "web-server.log", "w",
                              encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
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
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser.close()
            cls.playwright.stop()
        finally:
            try:
                cls._priv_http.shutdown()
                cls._priv_http.server_close()
                cls._priv_thread.join(timeout=5)
            except Exception:
                pass
            if cls.proc.poll() is None:
                cls.proc.terminate()
                try:
                    cls.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls.proc.kill()
                    cls.proc.wait()
            cls.dead_socket.close()
            cls.server_log.close()
            cls.tmp.cleanup()

    # ---------- Seeds und Helfer ----------

    def setUp(self):
        register = self.log_dir / "runs.json"
        if register.exists():
            register.unlink()
        (self.log_dir / "proj.log.state.json").unlink(missing_ok=True)
        (self.log_dir / "proj.log").unlink(missing_ok=True)
        (self.state_dir / "harness.json").unlink(missing_ok=True)
        self.write_messages({"data": [
            {"info": {"role": "assistant"},
             "parts": [{"type": "text", "text": LIVE_TEXT_A}]},
        ]})
        self.write_server_file()
        self.page_errors = []
        self.dialogs = []
        self.page = self.browser.new_page(
            viewport={"width": 1400, "height": 900})
        self.page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        self.page.on("dialog", self._on_dialog)

    def _on_dialog(self, dialog):
        self.dialogs.append(dialog.type + ": " + dialog.message)
        dialog.dismiss()

    def tearDown(self):
        self.page.close()

    def write_messages(self, payload):
        Path(self.messages_path).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def write_server_file(self):
        data = {
            "url": "http://127.0.0.1:%d" % self.priv_port,
            "port": self.priv_port,
            "password_file": str(self.credential),
        }
        (self.log_dir / "proj.log.server.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def register_run(self, state="running"):
        result = subprocess.run([
            sys.executable, str(RUNS_PY), "start",
            "--runtime", str(self.log_dir),
            "--project", str(self.project.resolve()),
            "--name", "proj", "--key", "proj", "--agent", AGENT,
            "--state", state,
        ], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0,
                         "Vorbedingung Laufregister fehlgeschlagen: "
                         + result.stdout + result.stderr)

    def write_log(self, *markers):
        (self.log_dir / "proj.log").write_text(
            "=== Agentenlauf proj ===\n" + "\n".join(markers) + "\n",
            encoding="utf-8")

    def write_state(self):
        entry = {
            "session": CHILD_SESSION,
            "agent": "tester",
            "description": "tester arbeitet",
            "prompt": "Auftrag für tester",
            "status": "running",
            "started": int(time.time()) + 5,
            "ended": 0,
            "output": STATIC_OUTPUT,
        }
        (self.log_dir / "proj.log.state.json").write_text(
            json.dumps({"session": MAIN_SESSION, "subagents": [entry]},
                       ensure_ascii=False),
            encoding="utf-8")

    def wait_until(self, predicate, timeout=20, message="Bedingung nicht erfüllt",
                   describe=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(200)
        if describe is not None:
            try:
                message += "\nBefund: " + str(describe())
            except Exception as error:  # pylint: disable=broad-exception-caught
                message += "\nBefund nicht lesbar: " + str(error)
        self.fail(message)

    def panel(self):
        return self.page.locator("[data-panel='ausgabe']")

    def sub_view(self):
        return self.panel().locator(
            "[data-agent-view][data-role='subagent']"
            f"[data-session='{CHILD_SESSION}']")

    def open_detail(self):
        self.page.goto(self.base + "/#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for(state="visible", timeout=20000)
        row.click()
        tabs = self.page.locator(
            "[aria-label='Projektbereiche'] button[role=tab]")
        tabs.first.wait_for(state="visible", timeout=20000)

    def open_output(self):
        tabs = self.page.locator(
            "[aria-label='Projektbereiche'] button[role=tab]")
        out_tab = tabs.filter(has_text="Ausgabe").first
        out_tab.click()
        self.panel().wait_for(state="visible", timeout=15000)

    def open_output_with_running_subagent(self):
        """Standardvorbedingung: laufender Subagent in geöffneter Ansicht."""
        self.register_run("running")
        self.write_log("HAUPT-B14-4711: Hauptagent schreibt sein Protokoll.")
        self.write_state()
        self.open_detail()
        self.open_output()
        view = self.sub_view()
        self.wait_until(
            lambda: view.count() == 1 and view.first.is_visible()
            and view.first.inner_text().strip() != "",
            message="Laufende Subagent-Karte mit Ausgabe fehlt")
        return view.first

    def run_server_message_requests(self):
        path = Path(self.record_path)
        if not path.exists():
            return []
        return [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines()
                if line.strip() and json.loads(line)["method"] == "GET"
                and "/message" in json.loads(line)["path"]]

    def assert_clean_page(self):
        self.assertEqual([], self.page_errors,
                         "Die Ausgabeansicht erzeugte JavaScript-Fehler")
        self.assertEqual([], self.dialogs,
                         "Die Ausgabeansicht öffnete einen Browserdialog")


class CardRefreshThroughRunServerTest(B14BrowserTest):
    def test_running_card_refreshes_through_the_private_run_server(self):
        """AK7: Die laufende Karte folgt dem Laufserver beim 2-Sekunden-Polling.

        Vorbedingung: aktiver Lauf mit laufendem Subagenten samt statischer
        erfasster Ausgabe; gültige Serverdatei auf den privaten Laufserver
        (LIVE-A-4711); kein gemeinsamer Server (Port abgewiesen).
        Aktion: Ausgabebereich öffnen, auf LIVE-A-4711 warten; dann die
        Attrappe auf LIVE-B-4711 umstellen und ohne Neuladen weiter
        beobachten.
        Erwartung: Die Karte zeigt LIVE-A-4711 und danach LIVE-B-4711; der
        statische erfasste Text erscheint nie; der Laufserver wurde per
        /message angefragt (Beleg für den Serverdatei-Pfad).
        Fehlerfall (Ausgangsstand): Die Karte friert beim statischen
        Ersttext ein.
        """
        card = self.open_output_with_running_subagent()
        self.wait_until(
            lambda: "LIVE-A-4711" in card.inner_text(),
            message="Die Karte zeigt nicht die LIVE-Ausgabe vom Laufserver "
                    "(LIVE-A-4711)",
            describe=lambda: "Karteninhalt: " + card.inner_text())
        self.assertNotIn(
            "STATISCH-4711", card.inner_text(),
            "Die Karte zeigt den statischen erfassten Text")
        self.write_messages({"data": [
            {"info": {"role": "assistant"},
             "parts": [{"type": "text", "text": LIVE_TEXT_B}]},
        ]})
        self.wait_until(
            lambda: "LIVE-B-4711" in card.inner_text(),
            timeout=15,
            message="Die Kartenausgabe aktualisiert sich beim Polling nicht")
        self.assertNotIn(
            "LIVE-A-4711", card.inner_text(),
            "Der alte LIVE-Text blieb eingefroren")
        requests = self.run_server_message_requests()
        self.assertTrue(
            requests,
            "Der Laufserver wurde nicht per /message angefragt")
        for entry in requests:
            self.assertTrue(
                entry["auth_ok"],
                f"Die Anfrage trug nicht das password_file-Kennwort: {entry}")
        self.assert_clean_page()

    def test_the_card_never_shows_the_frozen_captured_first_text(self):
        """AK7: Der statische erfasste Ersttext erscheint zu keinem Zeitpunkt.

        Vorbedingung: wie AK7; die Attrappe liefert zunächst LIVE-A-4711.
        Aktion: Ausgabebereich öffnen und über mehrere 2-Sekunden-Zyklen
        beobachten, ohne die Attrappe zu ändern.
        Erwartung: STATISCH-4711 erscheint zu keinem Zeitpunkt; der erste
        LIVE-Text bleibt sichtbar.
        Fehlerfall (Ausgangsstand): Die Karte zeigt den statischen
        Ersttext und friert ein.
        """
        card = self.open_output_with_running_subagent()
        self.wait_until(
            lambda: "LIVE-A-4711" in card.inner_text(),
            message="Die Karte zeigt nicht die LIVE-Ausgabe (LIVE-A-4711)",
            describe=lambda: "Karteninhalt: " + card.inner_text())
        self.page.wait_for_timeout(2500)
        self.page.wait_for_timeout(2500)
        body = card.inner_text()
        self.assertNotIn(
            "STATISCH-4711", body,
            "Der statische erfasste Ersttext erschien im Kartenkörper: "
            f"{body!r}")
        self.assertIn("LIVE-A-4711", body,
                      f"Der LIVE-Text verschwand unerwartet: {body!r}")
        self.assert_clean_page()


if __name__ == "__main__":
    unittest.main()
