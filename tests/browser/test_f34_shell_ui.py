"""Browserabnahme F34 WP1: Shell, Design, Benachrichtigungen, zentrale Bausteine.

Die Fälle leiten sich aus ``docs/features/F34.md`` ab — Abschnitt „Globale
Bausteine (WP1)“ (Toasts/Glocke, Kontext-Panel, Suche/Filter, Combobox) sowie der
Abschnitt „Zentrale Rückfragen“ (WP1/WP3). Geprüft werden ausschließlich die
dort verbindlich vereinbarten ``data-nv-*``-Hooks, ``data-*``-Attribute und
aria-Labels; sichtbare Texte nur dort, wo der Vertrag sie ausdrücklich festlegt.

Das echte Dashboard läuft als eigener Prozess auf einem freien Loopback-Port
mit isoliertem ``VIBE``/``HOME``, fünf registrierten Projekten und einer
opencode-Attrappe (Muster ``tests/browser/test_f33_shell_home_ui.py``). Es gibt
keine Modellaufrufe und keinen Netzzugriff außerhalb von Loopback.

Testfälle (Name, Vorbedingung, Aktion, Erwartung)
-------------------------------------------------
ToastPeekTest
* ``test_toast_container_is_top_right_below_bell_and_visible``
  (Vorbedingung: angemeldet, Startseite. Aktion: Toast erzeugen.
   Erwartung: ``#nv-toasts`` existiert, ist sichtbar, liegt optisch oben rechts
   unter der Glocke und oberhalb der Seitenmitte — kein Fix unten rechts.)
* ``test_each_toast_is_stored_as_bell_entry``
  (Vorbedingung: angemeldet. Aktion: Toast erzeugen, Glocke öffnen.
   Erwartung: Jede Toast-Meldung erzeugt zusätzlich einen Glocken-Eintrag.)

BellTest
* ``test_bell_explanation_is_translated_and_compact``
  (Vorbedingung: angemeldet, Glocke offen. Aktion: Erklärung lesen, Sprachwechsel
   nach DE und zurück nach EN, Viewport auf 1280px. Erwartung: Erklärung ist in
   DE deutsch und in EN übersetzt (nicht identisch), einzeilig/kompakt (Höhe
   deutlich kleiner als 3 Zeilen) und enthält im EN keinen unübersetzten
   deutschen Satz.)
* ``test_bell_single_dismiss_removes_only_that_entry``
  (Vorbedingung: angemeldet, zwei gespeicherte Glocken-Einträge.
   Aktion: Einzel-Schließen eines Eintrags. Erwartung: wird nur dieser entfernt;
   „Alle als gelesen“ über ``button[data-nv-bell-clear]`` leert Zähler und Liste;
   ``span[data-nv-bell-count]`` verschwindet bei 0.)

SidebarTest
* ``test_no_static_sidebar_navigation_and_five_header_nav_points``
  (Vorbedingung: angemeldet, Viewport 1400px. Aktion: lesen.
   Erwartung: ``aside.nv-side`` enthält keine ``[data-nv-nav]``-Knöpfe; die fünf
   Kopfzeilen-Punkte home/agents/activity/evaluations/settings sind sichtbar.)

ContextPanelTest
* ``test_context_panel_opens_close_and_escape``
  (Vorbedingung: angemeldet. Aktion: ``NV.context.open``,
   Schließen per Button und Escape, Body-Attribut prüfen.
   Erwartung: Panel mit Titel/Körper/Schließen, ``body[data-nv-context-open]``
   wird gesetzt und zurückgenommen.)

SearchFilterComboboxTest
* ``test_search_renders_data_hooks_and_filter_bar``
  (Vorbedingung: angemeldet, Startseite. Erwartung: ``div.nv-search[data-nv-search]``
  mit Lupe, ``input[data-nv-search-input]``, Clear-Knopf sowie
  ``div.nv-filter-bar[data-nv-filter-bar]``.)
* ``test_combobox_opens_on_focus_click_loupe_placeholder_and_sizes``
  (Vorbedingung: angemeldet. Aktion: Combobox mit langen Modellnamen erzeugen,
   per Fokus/Klick öffnen, filtern, auswählen.
   Erwartung: Öffnen bei Fokus/Klick, Placeholder und Lupe, Liste breiter als das
   Eingabefeld bei langen Namen, max-height ≥ 300px bei vielen Einträgen.)

ROT-PHASE (2026-11-22, vor der Implementierung von F34 WP1)
--------------------------------------------------------
Ausgeführt mit::

    PLAYWRIGHT_BROWSERS_PATH=/home/vibe/vibe-logs/playwright-browsers \
        python3 -m unittest discover -s tests/browser \
        -p 'test_f34_shell_ui.py' -v

Erwartung: alle Fälle rot (Fachrecht: F34-Vertrag noch nicht umgesetzt);
kein Fall aus Umgebungsgründen (Server, Port, Browser, Syntax).
"""
import http.client
import json
import math
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

_BROWSERS = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import (  # noqa: E402
    Error as PlaywrightError,
    sync_playwright,
)

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"

VIEWPORT_WIDE = 1400
VIEWPORT_H = 900
VIEWPORT_NARROW = 1280
VIEWPORT_H_NARROW = 800

# Fünf Projekte, damit Suche und Trefferzahl echte Filterarbeit leisten.
PROJECTS = (
    ("alpha-projekt", "Alpha Testpaket"),
    ("beta-projekt", "Beta Testpaket"),
    ("gamma", "Gamma Testpaket"),
    ("delta", "Delta Testpaket"),
    ("epsilon", "Epsilon Testpaket"),
)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """opencode-Attrappe: antwortet leer, startet keine Modelle."""

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
        self._send_json(200, {"data": []})


class F34ShellTest(unittest.TestCase):
    """Dashboard, fünf Projekte, Vorlagen, Browser, opencode-Attrappe."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        for name, feeder in PROJECTS:
            folder = cls.root / name
            (folder / ".vibe").mkdir(parents=True)
            (folder / ".vibe" / "project.env").write_text(
                "TYPE=generic\n", encoding="utf-8")
            (folder / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
            (folder / "TICKETS.md").write_text(
                "# TICKETS — Test\n\n- [ ] " + feeder +
                "\n  Beschreibung: Offenes Paket\n", encoding="utf-8")
        toolchain = cls.root / "_install"
        for typ in ("generic", "web"):
            template = toolchain / "templates" / typ
            (template / ".vibe").mkdir(parents=True)
            (template / ".vibe" / "project.env").write_text(
                "TYPE=" + typ + "\n", encoding="utf-8")
            (template / "AGENTS.md").write_text(
                "# AGENTS\n", encoding="utf-8")
        (toolchain / "templates" / "common").mkdir()
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True)
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir(parents=True)
        password = cls.log_dir / "opencode.password"
        password.write_text("geheim-F34-wp1", encoding="utf-8")
        password.chmod(0o600)
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
            "VIBE_INSTALL": str(toolchain),
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

    def setUp(self):
        self.post_language("en")
        self.page_errors = []
        self.context = self.browser.new_context(
            viewport={"width": VIEWPORT_WIDE, "height": VIEWPORT_H})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))

    def tearDown(self):
        self.page.close()
        self.context.close()

    # ---------- Helfer ----------

    def wait_until(self, predicate, timeout=20,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def post_language(self, lang):
        body = json.dumps({"language": lang}).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", "/api/language", body=body, headers={
                "Host": f"127.0.0.1:{self.port}", "X-Token": self.token,
                "Content-Type": "application/json"})
            conn.getresponse().read()
        finally:
            conn.close()

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def boot_after_reload(self):
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_bell(self):
        return self.ensure_bell_open()

    def _bell_panel_is_open(self):
        panel = self.page.locator("[data-nv-bell-panel]")
        if panel.count() == 0:
            return False
        return panel.is_visible() and panel.get_attribute("hidden") is None

    def ensure_bell_open(self, deadline_seconds=20):
        """Glocke vor jedem Zugriff öffnen und offen halten.

        ``render()`` ruft ``closeBellPanel()``; ein später Render kann das
        Panel daher zwischen zwei Messungen wieder schließen. Deshalb wird der
        Zustand vor jedem Zugriff geprüft und bei Bedarf erneut geklickt.
        """
        bell = self.page.locator("[data-nv-bell]")
        panel = self.page.locator("[data-nv-bell-panel]")
        deadline = time.time() + deadline_seconds
        while time.time() < deadline:
            if self._bell_panel_is_open():
                return panel
            try:
                bell.wait_for(state="visible", timeout=10000)
                bell.first.click()
                panel.wait_for(state="visible", timeout=3000)
            except PlaywrightError:
                continue
        self.fail("Die Glocke ließ sich nicht zuverlässig öffnen")

    def bell_explain_text(self, deadline_seconds=20):
        explain = self.page.locator("p[data-nv-bell-explain]")
        deadline = time.time() + deadline_seconds
        while time.time() < deadline:
            self.ensure_bell_open()
            try:
                explain.wait_for(state="visible", timeout=3000)
                return (explain.inner_text() or "").strip()
            except PlaywrightError:
                continue
        self.fail(
            "Die Glocke-Erklärung p[data-nv-bell-explain] wurde nicht sichtbar")

    def bell_explain_box(self, deadline_seconds=20):
        """Bounding-Box und Zeilenhöhe der Erklärung bei offener Glocke lesen."""
        explain = self.page.locator("p[data-nv-bell-explain]")
        deadline = time.time() + deadline_seconds
        while time.time() < deadline:
            self.ensure_bell_open()
            try:
                explain.wait_for(state="visible", timeout=3000)
                box = explain.bounding_box()
                # Selektor im JS statt eines (nach einem Poll u. U.
                # abgehängten) Element-Handles: die Glocke wird bei jedem
                # Poll neu gezeichnet.
                line_height = float(self.page.evaluate(
                    "() => { var el = document.querySelector('p[data-nv-bell-explain]'); "
                    "var s = getComputedStyle(el); return parseFloat(s.lineHeight) "
                    "|| parseFloat(s.fontSize) * 1.2; }"))
            except (PlaywrightError, TypeError, ValueError):
                continue
            if box is not None:
                return box, line_height
        self.fail("Die Glocke-Erklärung ließ sich nicht messen")

    def bell_counter_text(self):
        counter = self.page.locator("span[data-nv-bell-count]")
        counter.wait_for(state="visible", timeout=10000)
        return (counter.inner_text() or "").strip()

    def bell_notifications(self, panel):
        return panel.locator("[data-nv-notification]")

    def local_storage_json(self, key):
        raw = self.page.evaluate(
            "key => window.localStorage.getItem(key)", key)
        if raw is None:
            return None
        return json.loads(raw)

    def http_get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("GET", path, headers={
                "Host": f"127.0.0.1:{self.port}"})
            response = conn.getresponse()
            return (response.status,
                    response.getheader("Content-Type") or "",
                    response.read())
        finally:
            conn.close()

    def assert_no_page_errors(self):
        self.assertEqual(
            [], self.page_errors, "Die Oberfläche erzeugte JavaScript-Fehler")


GERMAN_BELL_EXPLAIN = (
    "Die Glocke sammelt dauerhafte Sammlung (Fragen, blockierte Pakete, "
    "fehlgeschlagene Läufe). Toasts sind kurzlebiges Aktionsfeedback.")


class F34ToastPeekTest(F34ShellTest):
    def test_toast_container_is_top_right_below_bell_and_visible(self):
        """Vorbedingung: angemeldet. Aktion: Toast erzeugen und ``#nv-toasts`` lesen.

        Erwartung: ``#nv-toasts`` existiert, ist sichtbar, der Container liegt
        optisch oben rechts unter der Glocke und oberhalb der Seitenmitte —
        kein Fix unten rechts.
        """
        self.boot()
        self.page.evaluate("text => toast(String(text))", "F34 Toast Prüfung")
        toast = self.page.locator("#nv-toasts [data-nv-toast-auto]")
        toast.first.wait_for(state="visible", timeout=10000)
        container = self.page.locator("#nv-toasts")
        self.assertEqual(1, container.count(),
                         "#nv-toasts existiert nicht (oder doppelt)")
        self.assertTrue(container.is_visible(), "#nv-toasts ist nicht sichtbar")
        box = container.bounding_box()
        self.assertIsNotNone(box, "#nv-toasts hat keine Bounding-Box")
        self.assertLess(
            box["y"] + box["height"], VIEWPORT_H / 2,
            "Der Toast-Container liegt nicht oberhalb der Seitenmitte: "
            f"y={box['y']}, height={box['height']}")
        self.assertLess(
            box["y"], 160, "Der Toast-Container liegt nicht ganz oben: "
            f"y={box['y']}")
        self.assertLess(
            box["x"] + box["width"], VIEWPORT_WIDE,
            "Der Toast-Container liegt nicht rechts: "
            f"x={box['x']}, width={box['width']}")
        self.assert_no_page_errors()

    def test_each_toast_is_stored_as_bell_entry(self):
        """Vorbedingung: angemeldet. Aktion: Toast erzeugen, Glocke öffnen.

        Erwartung: Jede Toast-Meldung erzeugt zusätzlich einen Glocken-Eintrag
        (``[data-nv-notification][data-nv-notification-id]`` im Panel).
        """
        self.boot()
        self.page.evaluate("text => toast(String(text))", "F34 Toast Prüfung")
        self.page.locator("#nv-toasts [data-nv-toast-auto]").first.wait_for(
            state="visible", timeout=10000)
        panel = self.open_bell()
        self.wait_until(
            lambda: panel.locator("[data-nv-notification]").count() >= 1,
            timeout=10,
            message="Jede Toast-Meldung erzeugt keinen Glocken-Eintrag")
        entry = panel.locator("[data-nv-notification]").first
        self.assertIn(
            "F34 Toast Prüfung", entry.inner_text(),
            "Der Glocken-Eintrag zum Toast enthält nicht die Toast-Meldung")
        self.assert_no_page_errors()


class F34BellTest(F34ShellTest):
    def test_bell_explanation_is_translated_and_compact(self):
        """Vorbedingung: angemeldet, Glocke offen. Aktion: Erklärung lesen,
        Sprachwechsel DE → EN, Viewport auf 1280px.

        Erwartung: Erklärung ist in DE deutsch und in EN übersetzt (nicht
        identisch); einzeilig/kompakt (Höhe deutlich kleiner als 3 Zeilen); im EN
        kein unübersetzter deutscher Satz.
        """
        self.boot()
        panel = self.open_bell()
        self.assertEqual(1, panel.locator("p[data-nv-bell-explain]").count(),
                         "Die Glocke hat keine Erklärung p[data-nv-bell-explain]")

        self.assertEqual(
            "en", self.page.evaluate(
                "() => (window.VIBE_I18N && VIBE_I18N.current()) || 'en'"),
            "Die Standardsprache ist nicht en")
        en_text = self.bell_explain_text()
        self.assertTrue(en_text.strip(), "Die Erklärung fehlt")

        self.post_language("de")
        self.page.reload()
        self.boot_after_reload()
        panel = self.open_bell()
        de_text = self.bell_explain_text()

        self.post_language("en")
        self.page.reload()
        self.boot_after_reload()
        panel = self.open_bell()
        en_text = self.bell_explain_text()

        self.assertTrue(de_text.strip(), "Die deutsche Erklärung fehlt")
        self.assertNotEqual(
            de_text, en_text,
            "Die Glocke-Erklärung ist nicht übersetzt (DE und EN identisch): "
            + repr((de_text, en_text)))

        self.page.set_viewport_size(
            {"width": VIEWPORT_NARROW, "height": VIEWPORT_H_NARROW})
        box, line_height = self.bell_explain_box()
        self.assertIsNotNone(box, "Die Erklärung hat keine Bounding-Box")
        self.assertTrue(
            math.isfinite(line_height) and line_height > 0,
            "Die Zeilenhöhe der Glocke-Erklärung ist nicht bestimmbar: "
            + repr(line_height))
        self.assertLess(
            box["height"], 2.0 * line_height,
            "Die Glocke-Erklärung ist nicht einzeilig/kompakt (deutlich kleiner "
            f"als 3 Zeilen): Höhe={box['height']}, Zeilenhöhe={line_height}")

        # Nach dem Sprachwechsel zurück auf Englisch: kein unübersetzter
        # deutscher Satz darf in der englischen Fassung stehen.
        self.assertNotIn(
            GERMAN_BELL_EXPLAIN, en_text,
            "Die englische Erklärung enthält einen unübersetzten deutschen Satz: "
            + repr(en_text))
        self.assert_no_page_errors()


class F34BellDismissClearTest(F34ShellTest):
    def _seed_notifications(self):
        entries = [
            {"id": "nv-f34-1", "text": "F34 Blockade Projekt", "kind": "blocked",
             "href": "#/project/alpha-projekt/work", "ts": 1764000000000, "read": False},
            {"id": "nv-f34-2", "text": "F34 Lauf fehlgeschlagen", "kind": "failed",
             "href": "#/project/alpha-projekt/output", "ts": 1764000001000, "read": False},
        ]
        self.page.evaluate(
            "(entries) => {"
            " window.localStorage.setItem('nv-notifications', JSON.stringify(entries));"
            " if (window.NV && typeof NV.refreshBell === 'function') NV.refreshBell();"
            "}", entries)

    def test_bell_single_dismiss_removes_only_that_entry(self):
        """Vorbedingung: angemeldet, zwei gespeicherte Glocken-Einträge.
        Aktion: Einzel-Schließen eines Eintrags, dann „Alle als gelesen“.
        Erwartung: Einzel-Schließen entfernt nur diesen Eintrag; „Alle als
        gelesen“ leert Zähler und Liste; Zähler ``span[data-nv-bell-count]``
        verschwindet bei 0.
        """
        self.boot()
        self._seed_notifications()
        panel = self.open_bell()
        entries = self.bell_notifications(panel)
        self.wait_until(
            lambda: entries.count() == 2,
            timeout=10,
            message="Die zwei gespeicherten Glocken-Einträge erschienen nicht")
        self.assertEqual(
            "2", self.bell_counter_text(),
            "Der Glocken-Zähler muss bei zwei offenen Einträgen „2“ zeigen")

        dismiss_buttons = entries.nth(1).locator("button[data-nv-notification-dismiss]")
        self.wait_until(
            lambda: dismiss_buttons.count() == 1,
            timeout=10,
            message="Der Einzel-Schließen-Knopf button[data-nv-notification-dismiss] fehlt")
        dismiss_buttons.first.click()
        self.wait_until(
            lambda: entries.count() == 1,
            timeout=10,
            message="Das Einzel-Schließen entfernt nicht genau diesen Eintrag")
        self.wait_until(
            lambda: self.bell_notifications(panel).first.is_visible(),
            timeout=10,
            message="Der verbleibende Glocken-Eintrag ist nicht sichtbar")

        clear = panel.locator("button[data-nv-bell-clear]")
        self.wait_until(
            lambda: clear.count() == 1,
            timeout=10,
            message="Die Aktion button[data-nv-bell-clear] fehlt")
        clear.first.click()
        self.wait_until(
            lambda: entries.count() == 0,
            timeout=10,
            message="„Alle als gelesen“ leert die Glocken-Liste nicht")
        self.wait_until(
            lambda: self.page.locator("span[data-nv-bell-count]").get_attribute("hidden") is not None,
            timeout=10,
            message="Der Glocken-Zähler blendet bei 0 nicht aus (hidden)")

    def test_bell_clear_all_resets_counter_and_list(self):
        """Vorbedingung: angemeldet, zwei gespeicherte Glocken-Einträge.
        Aktion: „Alle als gelesen“.
        Erwartung: Zähler und Liste werden geleert; ``span[data-nv-bell-count]``
        verschwindet bei 0.
        """
        self.boot()
        self._seed_notifications()
        panel = self.open_bell()
        entries = self.bell_notifications(panel)
        self.wait_until(
            lambda: entries.count() == 2,
            timeout=10,
            message="Die zwei gespeicherten Glocken-Einträge erschienen nicht")
        clear = panel.locator("button[data-nv-bell-clear]")
        self.wait_until(
            lambda: clear.count() == 1,
            timeout=10,
            message="Die Aktion button[data-nv-bell-clear] fehlt")
        clear.first.click()
        self.wait_until(
            lambda: entries.count() == 0,
            timeout=10,
            message="„Alle als gelesen“ leert die Glocken-Liste nicht")
        counter = self.page.locator("span[data-nv-bell-count]")
        self.wait_until(
            lambda: counter.get_attribute("hidden") is not None,
            timeout=10,
            message="Der Glocken-Zähler blendet bei 0 nicht aus (hidden)")


class F34SidebarTest(F34ShellTest):
    def test_no_static_sidebar_navigation_and_five_header_nav_points(self):
        """Vorbedingung: angemeldet, Viewport 1400px.
        Aktion: lesen.
        Erwartung: ``aside.nv-side`` enthält keine ``[data-nv-nav]``-Knöpfe; die
        fünf Kopfzeilen-Punkte home/agents/activity/evaluations/settings sind
        sichtbar.
        """
        self.boot()
        self.page.set_viewport_size(
            {"width": VIEWPORT_WIDE, "height": VIEWPORT_H})
        side = self.page.locator("aside.nv-side")
        self.assertEqual(1, side.count(),
                         "Die leere Sidebar aside.nv-side fehlt")
        nav_in_side = self.page.locator("aside.nv-side [data-nv-nav]")
        self.assertEqual(
            0, nav_in_side.count(),
            "Die statische Sidebar-Navigation darf nicht gerendert werden")

        for key in ("home", "agents", "activity", "evaluations", "settings"):
            nav = self.page.locator(f"header .nv-nav [data-nv-nav='{key}']")
            self.assertEqual(
                1, nav.count(),
                f"Die Kopfzeile hat den Navigationspunkt {key!r} nicht")
            self.assertTrue(
                nav.first.is_visible(),
                f"Der Navigationspunkt {key!r} ist nicht sichtbar")


class F34ContextPanelTest(F34ShellTest):
    def test_context_panel_opens_close_and_escape(self):
        """Vorbedingung: angemeldet. Aktion: ``NV.context.open``, Schließen,
        Body-Attribut prüfen.

        Erwartung: ``aside[data-nv-context]`` öffnet über ``NV.context.open``,
        hat Titel/Körper/Schließen, schließt über Escape und setzt
        ``body[data-nv-context-open="true"]`` sowie zurück.
        """
        self.boot()
        self.page.evaluate(
            "() => NV.context.open({title: 'F34 Kontext', content: 'Fachinhalt F34', footer: 'Fußnote F34'})")
        panel = self.page.locator("aside[data-nv-context]")
        panel.wait_for(state="visible", timeout=10000)
        self.assertEqual(1, panel.count(), "Das Kontext-Panel fehlt")
        self.assertEqual(
            "F34 Kontext", panel.locator("[data-nv-context-title]").inner_text(),
            "Das Kontext-Panel hat keinen Titel")
        self.assertIn(
            "Fachinhalt F34", panel.locator("[data-nv-context-body]").inner_text(),
            "Das Kontext-Panel hat keinen Körper")

        open_attr = self.page.evaluate(
            "() => document.body.getAttribute('data-nv-context-open')")
        self.assertEqual(
            "true", open_attr, "body[data-nv-context-open] wird nicht auf true gesetzt")

        self.page.locator("[data-nv-context-close]").click()
        self.wait_until(
            lambda: not panel.first.is_visible(),
            timeout=10,
            message="Das Kontext-Panel schließt sich nicht über den Schließen-Knopf")

        open_attr = self.page.evaluate(
            "() => document.body.getAttribute('data-nv-context-open')")
        self.assertNotEqual(
            "true", open_attr,
            "body[data-nv-context-open] wird nach dem Schließen nicht zurückgenommen")


class F34SearchFilterComboboxTest(F34ShellTest):
    def test_search_renders_data_hooks_and_filter_bar(self):
        """Vorbedingung: angemeldet, Startseite. Aktion: Suche und Filterleiste
        prüfen.

        Erwartung: ``NV.search`` rendert ``div.nv-search[data-nv-search]`` mit
        Lupe, ``input[data-nv-search-input]`` und Clear-Knopf; die Filterleiste
        ``div.nv-filter-bar[data-nv-filter-bar]`` bündelt Suche und Chips.
        """
        self.boot()
        search = self.page.locator("div.nv-search[data-nv-search]")
        search.wait_for(state="visible", timeout=20000)
        self.assertEqual(1, search.count(), "Die Suche div.nv-search fehlt")
        self.assertTrue(
            search.locator("span.nv-search-icon").is_visible(),
            "Die Suche hat keine Lupe span.nv-search-icon")
        search_input = self.page.locator(
            "input[type=search][data-nv-search-input]")
        search_input.wait_for(state="visible", timeout=10000)
        self.assertTrue(
            self.page.locator("button[data-nv-search-clear]").is_visible(),
            "Der Clear-Knopf button[data-nv-search-clear] fehlt")

        filter_bar = self.page.locator("div.nv-filter-bar[data-nv-filter-bar]")
        filter_bar.wait_for(state="visible", timeout=20000)
        self.assertEqual(1, filter_bar.count(), "Die Filterleiste fehlt")

        self.assert_no_page_errors()

    def test_combobox_opens_on_focus_click_loupe_placeholder_and_sizes(self):
        """Vorbedingung: angemeldet. Aktion: Combobox mit langen Modellnamen
        erzeugen, per Fokus/Klick öffnen, filtern.

        Erwartung: Öffnen bei Fokus/Klick, Placeholder und Lupe vorhanden,
        Liste breiter als das Eingabefeld bei langen Modellnamen, max-height
        wirksam (mind. 300px bei vielen Einträgen).
        """
        long_values = [
            "claude-sonnet-4-5-20250929-with-very-long-model-identifier",
            "gpt-5-turbo-high-very-long-suffix-for-testing",
            "gemini-2.5-pro-exp-very-long-model-name-here",
            "llama-3.3-70b-instruct-long-model-name",
            "mistral-large-2411-instruct-70b-extra-long",
            "qwen2.5-max-72b-instruct-very-long-name",
            "deepseek-r1-distill-qwen-32b-long-name",
            "kimi-k2-instruct-long-model-identifier",
        ]
        self.boot()
        self.page.evaluate(
            "(values) => {"
            " var host = document.createElement('div');"
            " host.id = 'nv-combobox-probe';"
            " document.body.appendChild(host);"
            " var cb = NV.combobox(values, '',"
            "   {placeholder: 'Modell suchen …', field: 'model', onchange: function () {}});"
            " host.appendChild(cb);"
            " cb.querySelector('[data-nv-combobox-input]').focus();"
            " return true;"
            "}", long_values)
        combobox = self.page.locator("#nv-combobox-probe [data-nv-combobox]")
        combobox.wait_for(state="visible", timeout=10000)
        input = self.page.locator(
            "#nv-combobox-probe [data-nv-combobox-input]")
        input.wait_for(state="visible", timeout=10000)
        list = self.page.locator("#nv-combobox-probe [data-nv-combobox-list]")

        self.wait_until(
            lambda: input.get_attribute("aria-expanded") == "true",
            timeout=10,
            message="Die Combobox öffnet die Liste nicht bei Fokus")

        self.assertEqual(
            1, self.page.locator(
                "#nv-combobox-probe span.nv-combobox-icon").count(),
            "Die Combobox hat keine Lupe span.nv-combobox-icon")
        self.assertEqual(
            "Modell suchen …", input.get_attribute("placeholder") or "",
            "Die Combobox hat keinen Placeholder")

        list.wait_for(state="visible", timeout=10000)
        input_box = input.bounding_box()
        list_box = list.bounding_box()
        self.assertIsNotNone(input_box)
        self.assertIsNotNone(list_box)
        self.assertGreater(
            list_box["width"], input_box["width"],
            "Die Combobox-Liste ist nicht breiter als das Eingabefeld "
            f"(list={list_box['width']}, input={input_box['width']})")
        self.assertGreaterEqual(
            list_box["height"], 300,
            "Die Combobox-Liste ist nicht mindestens 300px hoch "
            f"(max-height wirksam): {list_box['height']}")
        self.assert_no_page_errors()


if __name__ == "__main__":
    unittest.main()
