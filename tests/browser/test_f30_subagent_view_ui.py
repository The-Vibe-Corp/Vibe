"""Browserabnahme F30: größere, vergrößerbare und live aktualisierte Karten.

FEEDBACK.md F30 „Sub Agent view" meldet drei Beobachtungen:

* Subagenten erscheinen (korrekt) doppelt — zwei reale Kind-Sessions; dafür
  ist kein Fix vorgesehen, nur Dokumentation. Kein Testfall.
* Die Konsolenansicht ist deutlich zu klein (``.bv-subs{max-height:160px}``,
  ``.bv-sub{height:150px}``) — Kartenhöhe soll ≥ 300 px sein.
* Die Ausgabe hat sich nach dem ersten Eintrag nicht mehr aktualisiert
  (statisch). Die Backend-Ursache (erfasste Ausgabe gewinnt gegen die
  Live-Ausgabe) wird in ``tests/unit/test_f30_subagent_view.py`` geprüft;
  hier wird dassel Verhalten Ende-zu-Ende im Browser nachgestellt.

UI-Vertrag dieser Abnahme (bewusst schlank, damit die Umsetzung frei bleibt):

* Jede laufende Subagent-Karte ist weiterhin eine Ansicht mit
  ``data-agent-view``, ``data-role='subagent'`` und ``data-session``.
* Die Karte ist in der Standarddarstellung mindestens 300 px hoch und der
  Kasten ``.bv-subs`` passt seine Höhe entsprechend an (keine 160-px-Deckel).
* Jede laufende Karte bietet einen Vergrößern-Knopf (ein ``<button>`` in der
  Karte mit nicht-leerem ``aria-label``, das „vergrö“ enthält). Der Knopf
  ist per Tastatur bedienbar: Fokus + Enter vergrößert die Karte nahezu
  ansichtsfüllend (≥ 70 % der Viewporthöhe und ≥ 60 % der Viewportbreite),
  ein zweites Enter stellt die Standardgröße wieder her.
* Der Kartenkörper zeigt den Text, den ``/api/subagent-output`` liefert, und
  aktualisiert sich beim 2-Sekunden-Polling, wenn der Endpunkt neuen Text
  liefert (kein eingefrorener Ersttext).

Testfälle:

1. test_subagent_cards_are_substantially_larger            [AK5]
   Vorbedingung: aktiver Lauf mit einem laufenden Subagenten samt Ausgabe;
   Viewport 1400×900.
   Aktion: Ausgabebereich öffnen.
   Erwartung: Kartenhöhe ≥ 300 px und ≥ 30 % der Höhe der Hauptansicht; der
   Kasten .bv-subs ist mindestens so hoch wie die Karte.
   Fehlerfall (aktueller Zustand): Karte bleibt bei ~150 px.
2. test_running_card_can_be_enlarged_and_restored_by_keyboard [AK6]
   Vorbedingung: wie 1.
   Aktion: Vergrößern-Knopf per Tastatur (Fokus + Enter) betätigen; danach
   erneut Enter.
   Erwartung: Nach dem ersten Enter ist die Karte nahezu ansichtsfüllend;
   nach dem zweiten Enter wieder Standardgröße.
   Fehlerfall: Kein Knopf (aktueller Zustand), keine Reaktion oder keine
   Wiederherstellung.
3. test_subagent_output_refreshes_on_polling               [AK7]
   Vorbedingung: wie 1; die opencode-Attrappe liefert zunächst LIVE-A.
   Aktion: Ausgabebereich öffnen, auf LIVE-A warten; dann die Attrappe auf
   LIVE-B umstellen und ohne Neuladen weiter beobachten.
   Erwartung: Die Karte zeigt LIVE-A und später LIVE-B; der statische
   erfasste Text erscheint nicht.
   Fehlerfall (aktueller Zustand): Karte friert beim statischen Ersttext.
4. test_enlarged_card_keeps_showing_refreshed_output       [AK6, AK7]
   Vorbedingung: wie 1.
   Aktion: Karte vergrößern, dann Live-Text ändern.
   Erwartung: Auch die vergrößerte Karte zeigt den neuen Text.
   Fehlerfall: Vergrößerung friert die Aktualisierung ein.

Startpunkt ist das echte Dashboard (``bin/vibe-web.py``) mit eigenem Port und
isolierter VIBE-Umgebung; der opencode-Server ist eine lokale Attrappe.
Keine echten Modellaufrufe, keine produktive Installation.
"""
import base64
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

AGENT = "vibe-agent"
MAIN_SESSION = "ses_main_f30"
CHILD_SESSION = "ses_kind_f30"
STATIC_OUTPUT = ("The subagent is working in the background "
                 "(sessionID: ses_kind_f30). STATISCH-4711")
LIVE_TEXT_A = "LIVE-A-4711: Der Subagent schreibt seine erste Fassung."
LIVE_TEXT_B = "LIVE-B-4711: Der Subagent schreibt eine zweite Fassung."
MAIN_MARKER = "HAUPT-F30-4711: Hauptagent schreibt sein Protokoll."

MIN_CARD_HEIGHT = 300
ENLARGE_RATIO_HEIGHT = 0.70
ENLARGE_RATIO_WIDTH = 0.60

LIVE_MESSAGES = {
    "data": [
        {"info": {"role": "assistant"},
         "parts": [{"type": "text", "text": LIVE_TEXT_A}]},
    ]
}


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """opencode-Attrappe: /message liefert die hinterlegten Nachrichten."""

    context = None

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
        # Leere Lage für /api/session und /api/session/active: Die
        # Zustandsdatei bleibt maßgeblich für die Subagentenliste.
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


class F30BrowserTest(unittest.TestCase):
    """Dashboard, Browser, opencode-Attrappe, isoliertes VIBE-Root."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] F30 Sub Agent view\n  Beschreibung: Test\n",
            encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True)
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.port = free_port()
        cls.oc_port = free_port()
        cls.context = {
            "messages_path": str(cls.root / "messages.json"),
        }
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), make_fake_handler(cls.context))
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
            if cls.proc.poll() is None:
                cls.proc.terminate()
                try:
                    cls.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls.proc.kill()
                    cls.proc.wait()
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
        self.write_messages(LIVE_MESSAGES)
        password = self.log_dir / "opencode.password"
        password.write_text("geheim-F30-4711", encoding="utf-8")
        password.chmod(0o600)
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
        Path(self.context["messages_path"]).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")

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
        started = int(time.time()) + 5
        entry = {
            "session": CHILD_SESSION,
            "agent": "tester",
            "description": "tester arbeitet",
            "prompt": "Auftrag für tester",
            "status": "running",
            "started": started,
            "ended": 0,
            "output": STATIC_OUTPUT,
        }
        (self.log_dir / "proj.log.state.json").write_text(
            json.dumps({"session": MAIN_SESSION, "subagents": [entry]},
                       ensure_ascii=False),
            encoding="utf-8")

    def wait_until(self, predicate, timeout=20, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(200)
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
            "[aria-label='Project sections'] button[role=tab]")
        tabs.first.wait_for(state="visible", timeout=20000)

    def open_output(self):
        tabs = self.page.locator(
            "[aria-label='Project sections'] button[role=tab]")
        out_tab = tabs.filter(has_text="Output").first
        out_tab.click()
        self.panel().wait_for(state="visible", timeout=15000)

    def open_output_with_running_subagent(self):
        """Standardvorbedingung: laufender Subagent in geöffneter Ansicht."""
        self.register_run("running")
        self.write_log(MAIN_MARKER)
        self.write_state()
        self.open_detail()
        self.open_output()
        view = self.sub_view()
        self.wait_until(
            lambda: view.count() == 1 and view.first.is_visible()
            and view.first.inner_text().strip() != "",
            message="Laufende Subagent-Karte mit Ausgabe fehlt")
        return view.first

    def sizes(self, element):
        return element.bounding_box() or {"width": 0, "height": 0, "x": 0, "y": 0}

    def assert_clean_page(self):
        self.assertEqual([], self.page_errors,
                         "Die Ausgabeansicht erzeugte JavaScript-Fehler")
        self.assertEqual([], self.dialogs,
                         "Die Ausgabeansicht öffnete einen Browserdialog")


class CardSizeTest(F30BrowserTest):
    def test_subagent_cards_are_substantially_larger(self):
        """AK5: Subagent-Karten sind in der Standarddarstellung groß.

        Vorbedingung: aktiver Lauf mit einem laufenden Subagenten samt
        Ausgabe; Viewport 1400×900.
        Aktion: Ausgabebereich öffnen und die Karte ausmessen.
        Erwartung: Die Karte ([data-agent-view][data-role='subagent']) ist
        mindestens 300 px hoch und mindestens 30 % so hoch wie die
        Hauptansicht; der Kasten .bv-subs ist mindestens so hoch wie die
        Karte (kein 160-px-Deckel mehr).
        Fehlerfall (aktueller Zustand): Karte bleibt bei 150 px und der
        Kasten bei 160 px.
        """
        card = self.open_output_with_running_subagent()
        box = self.sizes(card)
        self.assertGreaterEqual(
            box["height"], MIN_CARD_HEIGHT,
            f"Die Subagent-Karte ist mit {box['height']} px zu klein "
            f"(Ziel ≥ {MIN_CARD_HEIGHT} px)")
        main_box = self.sizes(self.panel().locator(
            "[data-agent-view][data-role='main']").first)
        self.assertGreaterEqual(
            box["height"], 0.30 * main_box["height"],
            f"Die Karte ist mit {box['height']} px kleiner als 30 % der "
            f"Ausgabeanzeige ({main_box['height']} px)")
        subs_height = self.page.eval_on_selector(
            "[data-panel='ausgabe'] .bv-subs",
            "node => node.clientHeight")
        self.assertGreaterEqual(
            subs_height, MIN_CARD_HEIGHT,
            f"Der Kasten .bv-subs ist mit {subs_height} px zu klein")
        self.assert_clean_page()


class EnlargeTest(F30BrowserTest):
    def test_running_card_can_be_enlarged_and_restored_by_keyboard(self):
        """AK6: Vergrößern per Tastatur, Rückkehr mit zweitem Enter.

        Vorbedingung: aktiver Lauf mit einer laufenden Subagent-Karte.
        Aktion: Den in der Karte befindlichen Vergrößern-Knopf (ein
        <button> mit aria-label, das „vergrö“ enthält) per Fokus + Enter
        betätigen; danach erneut Enter.
        Erwartung: Nach dem ersten Enter ist die Karte nahezu ansichtsfüllend
        (≥ 70 % der Viewporthöhe und ≥ 60 % der Viewportbreite); nach dem
        zweiten Enter wieder Standardgröße (< 450 px hoch).
        Fehlerfall: Kein Knopf (aktueller Zustand), keine Reaktion oder die
        Standardgröße wird nicht wiederhergestellt.
        """
        card = self.open_output_with_running_subagent()
        original = self.sizes(card)
        buttons = self.sub_view().locator("button")
        count = buttons.count()
        enlarge = None
        for index in range(count):
            candidate = buttons.nth(index)
            label = candidate.get_attribute("aria-label") or ""
            if re.search(r"vergr|expand|enlarge", label.lower()):
                enlarge = candidate
                break
        self.assertIsNotNone(
            enlarge,
            f"Kein Vergrößern-Knopf (button mit aria-label „vergrö…“) in der "
            f"Subagent-Karte gefunden; {count} Knöpfe vorhanden")
        enlarge.focus()
        self.page.keyboard.press("Enter")
        self.wait_until(
            lambda: (lambda box: (
                box["height"] >= ENLARGE_RATIO_HEIGHT * 900
                and box["width"] >= ENLARGE_RATIO_WIDTH * 1400))(
                self.sizes(self.sub_view().first)),
            message="Die Karte wurde per Tastatur nicht nahezu ansichtsfüllend")
        enlarged = self.sizes(self.sub_view().first)
        self.assertGreaterEqual(enlarged["height"], 0.70 * 900)
        self.assertGreaterEqual(enlarged["width"], 0.60 * 1400)
        self.page.keyboard.press("Enter")
        self.wait_until(
            lambda: self.sizes(self.sub_view().first)["height"]
            < max(450, original["height"] + 100),
            message="Die Standardgröße wurde nicht wiederhergestellt")
        self.assert_clean_page()


class PollingRefreshTest(F30BrowserTest):
    def test_subagent_output_refreshes_on_polling(self):
        """AK7: Der Kartenkörper folgt dem Endpunkt beim 2-Sekunden-Polling.

        Vorbedingung: laufender Subagent mit statischem erfasstem Text; die
        opencode-Attrappe liefert LIVE-A-4711 als Live-Ausgabe.
        Aktion: Ausgabebereich öffnen, auf LIVE-A-4711 warten; dann die
        Attrappe auf LIVE-B-4711 umstellen und ohne Neuladen weiter
        beobachten (Polling alle 2 s).
        Erwartung: Die Karte zeigt LIVE-A-4711 und danach LIVE-B-4711; der
        statische erfasste Text (STATISCH-4711) erscheint nie.
        Fehlerfall (aktueller Zustand): Die Karte friert beim statischen
        Ersttext ein.
        """
        card = self.open_output_with_running_subagent()
        self.wait_until(
            lambda: "LIVE-A-4711" in card.inner_text(),
            message="Die Karte zeigt nicht die Live-Ausgabe (LIVE-A-4711)")
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
            "Der alte Live-Text blieb eingefroren")
        self.assert_clean_page()

    def test_enlarged_card_keeps_showing_refreshed_output(self):
        """AK6/AK7: Auch die vergrößerte Karte aktualisiert sich weiter.

        Vorbedingung: laufende Subagent-Karte; opencode-Attrappe liefert
        LIVE-A-4711.
        Aktion: Karte über den Vergrößern-Knopf vergrößern; danach die
        Attrappe auf LIVE-B-4711 umstellen.
        Erwartung: Die vergrößerte Karte zeigt LIVE-B-4711.
        Fehlerfall: Die Vergrößerung friert die Aktualisierung ein.
        """
        card = self.open_output_with_running_subagent()
        self.wait_until(
            lambda: "LIVE-A-4711" in card.inner_text(),
            message="Die Karte zeigt nicht die Live-Ausgabe (LIVE-A-4711)")
        buttons = self.sub_view().locator("button")
        enlarge = None
        for index in range(buttons.count()):
            candidate = buttons.nth(index)
            label = candidate.get_attribute("aria-label") or ""
            if re.search(r"vergr|expand|enlarge", label.lower()):
                enlarge = candidate
                break
        self.assertIsNotNone(enlarge, "Kein Vergrößern-Knopf gefunden")
        enlarge.focus()
        self.page.keyboard.press("Enter")
        self.wait_until(
            lambda: (lambda box: box["height"] >= 0.70 * 900)(
                self.sizes(self.sub_view().first)),
            message="Die Karte wurde nicht vergrößert")
        self.write_messages({"data": [
            {"info": {"role": "assistant"},
             "parts": [{"type": "text", "text": LIVE_TEXT_B}]},
        ]})
        self.wait_until(
            lambda: "LIVE-B-4711" in self.sub_view().first.inner_text(),
            timeout=15,
            message="Die vergrößerte Karte aktualisiert sich nicht")
        self.assert_clean_page()


if __name__ == "__main__":
    unittest.main()
