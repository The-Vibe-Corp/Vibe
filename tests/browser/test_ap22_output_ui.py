"""Browserabnahme AP22, Meilenstein B: Live-Ausgabe mit Attrappe.

Die Fälle leiten sich aus ``docs/features/AP22.md`` („Projektansicht →
Ausgabe“) ab. Lauf und Subagenten werden wie in
``tests/browser/test_ap20_output_overview_ui.py`` und
``tests/browser/test_b11_output_ui.py`` über das echte Laufregister und die
Zustandsdatei ``proj.log.state.json`` nachgebildet. Eine lokale
opencode-HTTP-Attrappe liefert keine Agentennachrichten; die Ausgabe kommt
deshalb aus der Zustandsdatei. Für den laufenden Zustand existiert eine echte
tmux-Sitzung auf eigenem Socket, damit ``/api/stop`` denselben Weg wie die
CLI nimmt. Es gibt keine Modellaufrufe und keinen Netzzugriff außerhalb von
Loopback.

Testfälle (Kurzfassung; Details in den Methoden)
-----------------------------------------------
``OutputPanelTest.test_overview_main_and_subagent_cards``
    Vorbedingung: laufender Lauf, Hauptlog mit Markern (inklusive
    ``<b>not markup</b>``), zwei laufende Subagenten. Erwartung:
    ``[data-nv-out-overview]`` nennt zwei Subagenten, der Hauptbereich
    ``[data-nv-out-main][role="log"]`` zeigt die Zeilen als Text (kein
    Markup) und beide ``[data-nv-out-sub]``-Karten existieren.
``FocusTest.test_focus_control_marks_exactly_one_subagent``
    Aktion: Fokus-Knopf in Karte A klicken. Erwartung: genau eine Karte
    trägt ein Fokus-Merkmal, und zwar A.
``SteerTest.test_steer_sends_the_instruction_and_reports_the_result``
    Aktion: Anweisung eingeben, ``steer`` klicken. Erwartung: POST
    ``/api/steer`` mit Projekt und Text; die Antwortmeldung erscheint.
``ContinueTest.test_continue_exists_with_active_run_and_shows_api_message``
    Erwartung: ``[data-nv-action="continue"]`` ist auch bei laufendem Lauf
    vorhanden; ein Klick zeigt die API-Meldung ohne Absturz.
``StopTest.test_stop_is_visible_and_run_state_becomes_stopped``
    Aktion: ``stop`` klicken. Erwartung: der Lauf endet als ``stopped`` und
    die Lauf-Pille der Projektansicht meldet ``stopped``.
``LegacyLogTest.test_output_without_live_run_shows_log_tail``
    Vorbedingung: kein Lauf im Register. Erwartung: die Ausgabe zeigt die
    letzten Protokollzeilen, ohne JavaScript-Fehler.

Vertragsunklarheiten (bewusst so geprüft und dokumentiert)
----------------------------------------------------------
1. **Fokus-Merkmal.** Der Vertrag verlangt Fokus-Knöpfe, nennt aber keinen
   Zustands-Hook. Geprüft wird: Die Karte gilt als fokussiert, wenn sie eine
   CSS-Klasse oder ein ``data-*``-Merkmal mit ``focus`` im Namen trägt oder
   ein Fokus-Knopf in der Karte ``aria-expanded="true"`` setzt. Genau eine
   Karte darf dieses Merkmal tragen.
2. **„N Subagenten“.** Als Zahl werden die beiden laufenden Subagenten
   erwartet (nicht der Hauptagent).
3. **Steuern-Ziel.** Der Vertrag nennt kein Ziel-Select für die neue
   Ausgabe. Der Test prüft nur, dass Projekt und Text im POST stehen; eine
   optionale ``session`` wird nicht erzwungen.
4. **Legacy-Ansicht.** Für die Ausgabe ohne Lauf nennt der Vertrag keinen
   eigenen Hook. Geprüft wird der sichtbare Ausgabebereich
   ``section[data-nv-ppanel="output"]`` samt Protokollzeilen.
5. **Stop-Bestätigung.** Ein nativer Dialog wird akzeptiert; eine
   eingebettete Bestätigung wird geklickt, falls sie erscheint.
"""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_BROWSERS = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"
RUNS_PY = REPO / "bin" / "vibe_runs.py"
PROJECT = "proj"
AGENT = "vibe-agent"
MAIN_SESSION = "ses_ap22_main"
CHILD_A = "ses_ap22_a"
CHILD_B = "ses_ap22_b"
MAIN_MARKER = "HAUPT-AP22-4711: Hauptagent schreibt sein Protokoll."
RAW_MARKUP = "<b>not markup</b>"
OUTPUT_A = "AUSGABE-A-AP22-4711: Subagent A arbeitet."
OUTPUT_B = "AUSGABE-B-AP22-4711: Subagent B arbeitet."
STEER_TEXT = "Bitte die vollständige Ausgabe zeigen"
TMUX_SESSION = "vibe-" + PROJECT


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """opencode-Attrappe: liefert keine Agentennachrichten."""

    def log_message(self, *args):
        return

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if "/message" in self.path:
            self._send_json(200, {"data": []})
            return
        self._send_json(200, {"ok": True})


class AP22OutputBrowserTest(unittest.TestCase):
    """Dashboard, Browser, Laufregister, Zustandsdatei und tmux-Nachbildung."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / PROJECT
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "TICKETS.md").write_text(
            "# TICKETS — AP22 Test\n\n- [ ] AP22 Ausgabe\n"
            "  Beschreibung: Test\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True)
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir(parents=True)

        cls.port = free_port()
        cls.oc_port = free_port()
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), _FakeOpenCodeHandler)
        cls._fake_http.daemon_threads = True
        cls._fake_thread = threading.Thread(target=cls._fake_http.serve_forever)
        cls._fake_thread.daemon = True
        cls._fake_thread.start()

        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                    "TMUX", "TMUX_PANE"):
                env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_OPENCODE_PORT": str(cls.oc_port),
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
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
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
                cls._fake_http.shutdown()
                cls._fake_http.server_close()
                cls._fake_thread.join(timeout=5)
            except Exception:
                pass
            cls.kill_tmux()
            if cls.proc.poll() is None:
                cls.proc.terminate()
                try:
                    cls.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls.proc.kill()
                    cls.proc.wait()
            cls.server_log.close()
            cls.tmp.cleanup()

    @classmethod
    def kill_tmux(cls):
        subprocess.run(
            ["tmux", "-L", TMUX_SESSION, "kill-server"],
            env=cls.env, capture_output=True, text=True, timeout=10,
            check=False)

    # ---------- Umgebung je Test ----------

    def setUp(self):
        self.kill_tmux()
        (self.log_dir / "runs.json").unlink(missing_ok=True)
        (self.log_dir / f"{PROJECT}.log").unlink(missing_ok=True)
        (self.log_dir / f"{PROJECT}.log.state.json").unlink(missing_ok=True)
        (self.state_dir / "harness.json").unlink(missing_ok=True)
        self.post_language("en")
        self.page_errors = []
        self.dialogs = []
        self.context = self.browser.new_context(
            viewport={"width": 1400, "height": 1000})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))
        self.page.on("dialog", self._on_dialog)

    def _on_dialog(self, dialog):
        self.dialogs.append(dialog.type + ": " + dialog.message)
        dialog.accept()

    def tearDown(self):
        self.page.close()
        self.context.close()
        self.kill_tmux()

    # ---------- Seeds und Helfer ----------

    def post_language(self, lang):
        body = json.dumps({"language": lang}).encode("utf-8")
        conn = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        try:
            request = (
                "POST /api/language HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{self.port}\r\n"
                f"X-Token: {self.token}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n\r\n"
            ).encode("utf-8") + body
            conn.sendall(request)
            conn.recv(4096)
        finally:
            conn.close()

    def api_json(self, path):
        return self.page.evaluate(
            """async (path) => {
              const response = await fetch(path, {headers: {'Accept': 'application/json'}});
              return await response.json();
            }""", path)

    def start_run(self, state="running"):
        result = subprocess.run([
            sys.executable, str(RUNS_PY), "start",
            "--runtime", str(self.log_dir),
            "--project", str(self.project.resolve()),
            "--name", PROJECT, "--key", PROJECT, "--agent", AGENT,
            "--session", TMUX_SESSION, "--state", state,
        ], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0,
                         "Vorbedingung Laufregister fehlgeschlagen: "
                         + result.stdout + result.stderr)
        if state == "running":
            self.start_tmux()

    def start_tmux(self):
        result = subprocess.run(
            ["tmux", "-L", TMUX_SESSION, "new-session", "-d",
             "-s", TMUX_SESSION, "sleep", "300"],
            env=self.env, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0,
                         "tmux-Sitzung konnte nicht angelegt werden: "
                         + result.stdout + result.stderr)
        result = subprocess.run(
            ["tmux", "-L", TMUX_SESSION, "set-environment",
             "-t", TMUX_SESSION, "VIBE_MANAGED", "run"],
            env=self.env, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0,
                         "tmux-Markierung konnte nicht gesetzt werden: "
                         + result.stdout + result.stderr)

    def write_log(self, *markers):
        (self.log_dir / f"{PROJECT}.log").write_text(
            "=== Agentenlauf proj ===\n" + "\n".join(markers) + "\n",
            encoding="utf-8")

    def sub(self, session, agent, description, output, status="running"):
        return {
            "session": session,
            "agent": agent,
            "description": description,
            "prompt": "Auftrag für " + agent,
            "status": status,
            "started": int(time.time()) + 5,
            "ended": int(time.time()) + 180 if status != "running" else 0,
            "output": output,
        }

    def write_state(self, subs):
        (self.log_dir / f"{PROJECT}.log.state.json").write_text(
            json.dumps({"session": MAIN_SESSION, "subagents": subs},
                       ensure_ascii=False),
            encoding="utf-8")

    def seed_live(self):
        self.start_run("running")
        self.write_log(MAIN_MARKER, RAW_MARKUP)
        self.write_state([
            self.sub(CHILD_A, "testerA", "Auftrag A", OUTPUT_A),
            self.sub(CHILD_B, "testerB", "Auftrag B", OUTPUT_B),
        ])

    def wait_until(self, predicate, timeout=25,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_output(self):
        self.boot()
        self.page.goto(self.base + "/#/project/" + PROJECT + "/output")
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        panel = self.page.locator("section[data-nv-ppanel='output']")
        panel.wait_for(state="visible", timeout=20000)
        return panel

    def run_state(self):
        pill = self.page.locator("[data-nv-run-state]").first
        pill.wait_for(state="visible", timeout=20000)
        state = (pill.get_attribute("data-state") or "").strip().lower()
        text = (pill.inner_text() or "").strip().lower()
        mapping = {"läuft": "running", "gestoppt": "stopped",
                   "running": "running", "stopped": "stopped"}
        return state or mapping.get(text, text)

    def confirm_if_visible(self):
        confirm = self.page.locator(
            "[role='dialog'] button, [data-nv-confirm] button").filter(
                has_text=re.compile(r"stopp|stop|ja|yes", re.I)).first
        if confirm.count() and confirm.is_visible():
            confirm.click()

    def sub_card(self, session):
        return self.page.locator(f"[data-nv-out-sub='{session}']").first

    def focus_marker(self, session):
        return self.page.evaluate(
            """(session) => {
              const card = document.querySelector(
                "[data-nv-out-sub='" + session + "']");
              if (!card) return null;
              const classes = (typeof card.className === 'string'
                ? card.className : '').split(/\\s+/)
                .filter(name => /focus/i.test(name));
              const attrs = Array.from(card.attributes).filter(attribute =>
                /focus/i.test(attribute.name)
                && !['false', '0', ''].includes(attribute.value));
              const expanded = Array.from(card.querySelectorAll('button'))
                .some(button => button.getAttribute('aria-expanded') === 'true'
                  && /fokus|focus/i.test(
                    (button.getAttribute('aria-label') || '')
                    + ' ' + (button.textContent || '')));
              return {classes, attrs: attrs.map(a => a.name), expanded,
                      focused: classes.length > 0 || attrs.length > 0 || expanded};
            }""", session)

    def click_focus(self, session):
        return self.page.evaluate(
            """(session) => {
              const card = document.querySelector(
                "[data-nv-out-sub='" + session + "']");
              if (!card) return false;
              const buttons = Array.from(card.querySelectorAll('button'));
              const target = buttons.find(button => /fokus|focus|zoom|vergröß|enlarge/i
                .test((button.getAttribute('aria-label') || '')
                  + ' ' + (button.textContent || '')));
              if (!target) return false;
              target.click();
              return true;
            }""", session)

    def assert_clean_page(self):
        self.assertEqual(
            [], self.page_errors, "Die Ausgabeansicht erzeugte JavaScript-Fehler")


class OutputPanelTest(AP22OutputBrowserTest):
    def test_overview_main_and_subagent_cards(self):
        """Vorbedingung: laufender Lauf, zwei laufende Subagenten und ein
        Hauptlog mit Markern inklusive ``<b>not markup</b>``.

        Erwartung: Die Übersicht nennt zwei Subagenten, der Hauptbereich ist
        eine Log-Region und zeigt die Zeilen als Text (kein ``<b>``-Element),
        beide Subagenten-Karten existieren mit ihrer Ausgabe.
        """
        self.seed_live()
        self.open_output()

        overview = self.page.locator("[data-nv-out-overview]")
        overview.wait_for(state="visible", timeout=20000)
        text = overview.inner_text() or ""
        self.assertRegex(
            text, r"(?<!\d)2(?!\d)",
            "Die Übersicht nennt nicht zwei Subagenten: " + repr(text))

        main = self.page.locator("[data-nv-out-main][role='log']")
        main.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: MAIN_MARKER in main.evaluate("node => node.textContent"),
            timeout=25,
            message="Der Hauptbereich zeigt das Protokoll nicht")
        content = main.evaluate("node => node.textContent")
        self.assertIn(
            RAW_MARKUP, content,
            "Markup-artiger Protokolltext erscheint nicht als Text")
        self.assertEqual(
            0, main.locator("b").count(),
            "Protokollinhalt wurde als HTML-Markup gerendert")

        for session, marker in ((CHILD_A, OUTPUT_A), (CHILD_B, OUTPUT_B)):
            with self.subTest(session=session):
                card = self.sub_card(session)
                card.wait_for(state="visible", timeout=20000)
                self.wait_until(
                    lambda card=card, marker=marker: marker in card.inner_text(),
                    timeout=20,
                    message=f"Subagentenkarte {session} zeigt ihre Ausgabe nicht")
        self.assert_clean_page()


class FocusTest(AP22OutputBrowserTest):
    def test_focus_control_marks_exactly_one_subagent(self):
        """Vorbedingung: zwei laufende Subagenten.

        Aktion: Fokus-Knopf in Karte A klicken.
        Erwartung: Genau eine Karte trägt ein Fokus-Merkmal, und zwar A.
        """
        self.seed_live()
        self.open_output()
        self.sub_card(CHILD_A).wait_for(state="visible", timeout=20000)
        self.sub_card(CHILD_B).wait_for(state="visible", timeout=20000)

        self.assertTrue(
            self.click_focus(CHILD_A),
            "In der Subagentenkarte fehlt ein Fokus-Knopf")
        self.wait_until(
            lambda: (self.focus_marker(CHILD_A) or {}).get("focused") is True,
            timeout=20,
            message="Der Fokus-Knopf setzte kein Fokus-Merkmal an Karte A")
        self.assertFalse(
            (self.focus_marker(CHILD_B) or {}).get("focused"),
            "Karte B trägt gleichzeitig ein Fokus-Merkmal")
        self.assert_clean_page()


class SteerTest(AP22OutputBrowserTest):
    def test_steer_sends_the_instruction_and_reports_the_result(self):
        """Vorbedingung: laufender Lauf.

        Aktion: Anweisung eingeben, ``[data-nv-action="steer"]`` klicken.
        Erwartung: POST ``/api/steer`` mit Projekt und Text; die
        Antwortmeldung erscheint sichtbar.
        """
        self.seed_live()
        self.open_output()
        records = []

        def handler(route):
            records.append(route.request.post_data or "")
            route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"ok": True, "message": "ANWEISUNG-OK-4711"}))

        self.page.route("**/api/steer", handler)
        steer = self.page.locator("[data-nv-steer]")
        steer.wait_for(state="visible", timeout=20000)
        steer.fill(STEER_TEXT)
        with self.page.expect_request("**/api/steer", timeout=20000):
            self.page.locator("[data-nv-action='steer']").first.click()
        self.assertEqual(1, len(records), "Es wurde kein /api/steer-POST gesendet")
        payload = json.loads(records[0] or "{}")
        self.assertEqual(PROJECT, payload.get("name"), payload)
        self.assertEqual(STEER_TEXT, payload.get("text"), payload)
        self.wait_until(
            lambda: "ANWEISUNG-OK-4711" in self.page.locator("#nv-toasts").inner_text(),
            timeout=20,
            message="Die Antwort auf die Anweisung erscheint nicht als Meldung")
        self.assert_clean_page()


class ContinueTest(AP22OutputBrowserTest):
    def test_continue_exists_with_active_run_and_shows_api_message(self):
        """Vorbedingung: laufender Lauf.

        Erwartung: ``[data-nv-action="continue"]`` ist sichtbar; ein Klick
        zeigt die API-Meldung, ohne die Seite zu brechen.
        """
        self.seed_live()
        self.open_output()
        button = self.page.locator("[data-nv-action='continue']")
        button.wait_for(state="visible", timeout=20000)

        self.page.route(
            "**/api/continue",
            lambda route: route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"ok": False,
                                 "message": "WEITER-AP22-GRENZE"})))
        button.first.click()
        self.wait_until(
            lambda: "WEITER-AP22-GRENZE" in self.page.locator("#nv-toasts").inner_text(),
            timeout=20,
            message="Die API-Meldung zum Fortsetzen erscheint nicht")
        self.assert_clean_page()


class StopTest(AP22OutputBrowserTest):
    def test_stop_is_visible_and_run_state_becomes_stopped(self):
        """Vorbedingung: laufender Lauf mit echter tmux-Sitzung.

        Aktion: ``[data-nv-action="stop"]`` klicken, neu laden.
        Erwartung: ``/api/run-state`` meldet keinen laufenden Lauf mehr und
        die Lauf-Pille zeigt ``stopped``.
        """
        self.seed_live()
        self.open_output()
        stop = self.page.locator("[data-nv-action='stop']")
        stop.wait_for(state="visible", timeout=20000)
        stop.first.click()
        self.confirm_if_visible()
        self.wait_until(
            lambda: self.api_json(
                f"/api/run-state?name={PROJECT}").get("running") is False,
            timeout=30,
            message="Der Lauf wurde durch Stop nicht beendet")

        self.page.reload()
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        self.assertEqual(
            "stopped", self.run_state(),
            "Die Lauf-Pille meldet nach dem Stop nicht stopped")
        self.assertFalse(
            self.page.locator("[data-nv-action='stop']").is_visible(),
            "Der Stop-Knopf bleibt bei gestopptem Lauf sichtbar")
        self.assert_clean_page()


class LegacyLogTest(AP22OutputBrowserTest):
    def test_output_without_live_run_shows_log_tail(self):
        """Vorbedingung: kein Lauf im Register, aber ein Protokoll.

        Erwartung: Die Ausgabe zeigt die letzten Protokollzeilen und erzeugt
        keine JavaScript-Fehler.
        """
        marker = "NACHLESE-AP22-4711: letzte Zeile ohne Lauf."
        self.write_log(MAIN_MARKER, marker)
        self.open_output()
        panel = self.page.locator("section[data-nv-ppanel='output']")
        self.wait_until(
            lambda: marker in panel.inner_text(),
            timeout=25,
            message="Die Ausgabe ohne laufenden Lauf zeigt die Protokollzeilen nicht")
        self.assert_clean_page()


if __name__ == "__main__":
    unittest.main()
