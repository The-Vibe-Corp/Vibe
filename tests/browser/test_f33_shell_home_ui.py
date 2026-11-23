"""Browserabnahme F33 WP1: Shell, Design und Startseite.

Die Fälle leiten sich aus ``docs/features/F33.md`` ab — Abschnitte
„Dom-Hook-Vertrag → WP1“ und „Nutzerentscheidungen“. Geprüft werden
ausschließlich die dort verbindlich vereinbarten ``data-nv-*``-Hooks und
aria-Attribute; sichtbare Texte nur dort, wo der Vertrag sie ausdrücklich
festlegt (Toast-Auto-Dismiss, Trefferzahl, Animations-Label).

Das echte Dashboard läuft als eigener Prozess auf einem freien Loopback-Port
mit isoliertem ``VIBE``/``HOME``, fünf registrierten Projekten und einer
opencode-Attrappe (Muster ``tests/browser/test_ap22_home_ui.py``). Es gibt
keine Modellaufrufe und keinen Netzzugriff außerhalb von Loopback.

Fachlicher Rahmen
-----------------
* **Logo/Favicon (3f):** ``index.html`` trägt in der Kopfzeile
  ``img.nv-logo[data-nv-logo]`` mit ``alt="vibe"`` und verweist als Favicon auf
  ``/static/vibe.svg``. Ausgeliefert wird die Datei durch WP6
  (``STATIC_FILES``); bis dahin ist der Auslieferungstest erwartungsgemäß rot
  und wird grün, sobald die Route registriert ist.
* **Sidebar:** Entfällt (F34). Die fünf Navigationspunkte liegen dauerhaft
  in der Kopfzeile (``nav[data-nv-navs]`` mit ``button[data-nv-nav]``);
  ``aside.nv-side[data-nv-side]`` ist bewusst leer.
* **Breitbildnutzung:** ``main.nv-main`` ist maximal durch ``max-width:
  1600px`` begrenzt und zentriert (Viewport 1600px ⇒ Breite > 1200px).
* **Akzent:** Standard ist ``blue`` als ``data-accent`` am ``<html>``.
* **Toasts (3c):** ``toast()`` hängt Karten mit ``data-nv-toast-auto`` an, die
  sich ohne Klick nach ~6 s selbst entfernen.
* **Animationsschalter (3d):** ``[data-nv-anim-toggle]`` trägt ein
  ``aria-label``/``title`` mit „Animation(en)“ und dem Zustand.
* **Home (2b):** Anpinnen über ``button[data-nv-action="project-pin"]``
  (``aria-pressed``) in ``section[data-nv-pinned-projects]`` mit
  ``localStorage['nv-pinned-projects']``; Live-Suche
  ``input[data-nv-project-search]`` mit ``p[data-nv-search-count]``.

Testfälle (Kurzfassung; Details in den Methoden)
------------------------------------------------
``ShellChromeTest.test_logo_and_favicon_are_delivered``
``ShellChromeTest.test_header_nav_visible_at_1400_1280_1000_and_sidebar_without_navs``
``ShellChromeTest.test_wide_layout_uses_the_full_width``
``ShellChromeTest.test_default_accent_is_blue``
``ShellChromeTest.test_toast_auto_dismisses_without_click``
``ShellChromeTest.test_animation_toggle_label_names_animations_and_state``
``HomePinTest.test_pinning_moves_project_to_pinned_section_and_persists``
``HomeSearchTest.test_search_filters_cards_live_and_shows_count``

ROT-PHASE (2026-11-21, vor der Implementierung von WP1)
------------------------------------------------------
Ausgeführt mit::

    PLAYWRIGHT_BROWSERS_PATH=/home/vibe/vibe-logs/playwright-browsers \
        python3 -m unittest discover -s tests/browser \
        -p 'test_f33_shell_home_ui.py' -v

Ergebnis: 8 Fälle, 8 rot (5 ``AssertionError`` = Verhalten fehlt,
3 ``playwright TimeoutError`` = DOM-Hook fehlt). Kein Fall war grün; kein
Fall scheiterte aus Umgebungsgründen (Server, Port, Browser, Syntax).

* ``test_logo_and_favicon_are_delivered`` — AssertionError: 0 statt 1
  ``img[data-nv-logo]`` in der Kopfzeile (Textmarke statt Logo).
* ``test_sidebar_at_wide_viewport_and_header_nav_below_1280`` —
  AssertionError: ``aside[data-nv-side]`` fehlt bei 1400px.
* ``test_wide_layout_uses_the_full_width`` — AssertionError: ``main`` ist
  1200px breit (weiterhin ``max-width``-begrenzt) statt > 1200px.
* ``test_default_accent_is_blue`` — AssertionError: ``data-accent`` ist
  ``None`` statt ``blue``.
* ``test_toast_auto_dismisses_without_click`` — TimeoutError: keine
  Toast-Karte ``#nv-toasts [data-nv-toast-auto]`` (Auto-Dismiss fehlt).
* ``test_animation_toggle_label_names_animations_and_state`` —
  AssertionError: das Label nennt weder „Animation(en)“ noch den Zustand
  (kein ``aria-label``/``title``); es ändert sich beim Umschalten nicht.
* ``test_pinning_moves_project_to_pinned_section_and_persists`` —
  TimeoutError: ``section[data-nv-projects]`` fehlt (die Projektliste ist
  ein ``div``); der Anpinn-Hook wird dadurch gar nicht erst erreicht.
* ``test_search_filters_cards_live_and_shows_count`` — TimeoutError:
  ``input[data-nv-project-search]`` fehlt.
"""
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

_BROWSERS = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"

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


class F33ShellHomeTest(unittest.TestCase):
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
        # Vorlagen für GET /api/types und POST /api/new (isolierte Installation).
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
        cls.log_dir.mkdir(parents=True, exist_ok=True)
        password = cls.log_dir / "opencode.password"
        password.write_text("geheim-F33-wp1", encoding="utf-8")
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
            viewport={"width": 1400, "height": 900})
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

    def card(self, name):
        return self.page.locator(f"article[data-nv-project='{name}']")

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


class ShellChromeTest(F33ShellHomeTest):
    def test_logo_and_favicon_are_delivered(self):
        """Vorbedingung: angemeldet. Aktion: Kopfzeile und Favicon prüfen,
        ``/static/vibe.svg`` abrufen.

        Erwartung: In der Kopfzeile steht ``img[data-nv-logo]`` mit
        ``alt="vibe"`` und ``src="/static/vibe.svg"``; ``link[rel=icon]``
        verweist mit ``type="image/svg+xml"`` auf dieselbe Datei; der Abruf
        liefert 200, ``image/svg+xml`` und SVG-Inhalt (Auslieferung durch WP6).
        """
        self.boot()
        logo = self.page.locator("header img[data-nv-logo]")
        self.assertEqual(
            1, logo.count(),
            "Die Kopfzeile enthält kein img[data-nv-logo]")
        self.assertTrue(logo.first.is_visible(), "Das Logo ist nicht sichtbar")
        self.assertEqual("vibe", logo.first.get_attribute("alt"),
                         "Das Logo trägt nicht alt=\"vibe\"")
        src = logo.first.get_attribute("src") or ""
        self.assertTrue(
            src.endswith("/static/vibe.svg"),
            "Das Logo verweist nicht auf /static/vibe.svg: " + repr(src))

        icon = self.page.locator("link[rel='icon']")
        self.assertEqual(1, icon.count(), "Der Favicon-Verweis fehlt")
        href = icon.first.get_attribute("href") or ""
        self.assertTrue(
            href.endswith("/static/vibe.svg"),
            "Das Favicon verweist nicht auf /static/vibe.svg: " + repr(href))
        self.assertEqual(
            "image/svg+xml", icon.first.get_attribute("type"),
            "Der Favicon-Verweis hat nicht den Typ image/svg+xml")

        status, ctype, body = self.http_get("/static/vibe.svg")
        self.assertEqual(200, status,
                         "/static/vibe.svg wird nicht ausgeliefert (WP6)")
        self.assertIn("image/svg+xml", ctype.lower(),
                      "Falscher Content-Type für /static/vibe.svg: "
                      + repr(ctype))
        self.assertIn(b"<svg", body, "Die Datei enthält kein SVG")
        self.assert_no_page_errors()

    def test_header_nav_visible_at_1400_1280_1000_and_sidebar_without_navs(self):
        """Vorbedingung: angemeldet. Aktion: Viewport 1400, 1280, 1000.

        Erwartung (F34: statische Sidebar entfällt): bei allen drei
        Breiten ist ``nav[data-nv-navs]`` sichtbar und enthält die fünf
        Navigationspunkte ``[data-nv-nav]`` (``home``, ``agents``,
        ``activity``, ``evaluations``, ``settings``);
        ``aside[data-nv-side]`` enthält keine ``[data-nv-nav]``-Knöpfe.
        """
        self.boot()
        nav = self.page.locator("nav[data-nv-navs]")
        for width in (1400, 1280, 1000):
            with self.subTest(width=width):
                self.page.set_viewport_size({"width": width, "height": 900})
                self.wait_until(
                    lambda: nav.count() == 1 and nav.first.is_visible(),
                    timeout=10,
                    message=f"Bei {width}px fehlt die sichtbare "
                            "Kopf-Navigation nav[data-nv-navs]")
                for key in ("home", "agents", "activity",
                            "evaluations", "settings"):
                    point = nav.locator(f"[data-nv-nav='{key}']")
                    self.assertEqual(
                        1, point.count(),
                        f"Bei {width}px fehlt der Navigationspunkt "
                        f"{key!r} in nav[data-nv-navs]")
                    self.assertTrue(
                        point.first.is_visible(),
                        f"Der Navigationspunkt {key!r} ist bei {width}px "
                        "nicht sichtbar")
                self.assertEqual(
                    0, self.page.locator(
                        "aside[data-nv-side] [data-nv-nav]").count(),
                    f"Bei {width}px enthält aside[data-nv-side] noch "
                    "[data-nv-nav]-Knöpfe (statische Sidebar)")
        self.assert_no_page_errors()

    def test_wide_layout_uses_the_full_width(self):
        """Vorbedingung: angemeldet. Aktion: Viewport 1600×1000.

        Erwartung (F34: statische Sidebar entfällt): ``main.nv-main``
        nutzt die Breite — sichtbar breiter als 1200px und maximal
        1600px — und ist zentriert; das Dokument überläuft horizontal
        nicht; ``aside[data-nv-side]`` enthält keine ``[data-nv-nav]``-
        Knöpfe.
        """
        self.page.set_viewport_size({"width": 1600, "height": 1000})
        self.boot()
        main = self.page.locator("main#nv-main")
        main.wait_for(state="visible", timeout=20000)
        box = main.bounding_box()
        self.assertIsNotNone(box, "Der Hauptbereich hat keine Position")
        self.assertLessEqual(
            box["width"], 1600,
            "Der Hauptbereich überschreitet die Breite von 1600px: "
            f"{box['width']}px bei 1600px Viewport")
        self.assertGreater(
            box["width"], 1200,
            "Der Hauptbereich nutzt die Breitbildfläche nicht: "
            f"{box['width']}px bei 1600px Viewport")
        center = box["x"] + box["width"] / 2
        self.assertLess(
            abs(center - 800), 10,
            "Der Hauptbereich ist nicht zentriert: "
            f"x={box['x']}, breit={box['width']} bei 1600px Viewport")
        scroll_width = self.page.evaluate(
            "() => Math.max(document.documentElement.scrollWidth,"
            " document.body.scrollWidth, 0)")
        self.assertLessEqual(
            scroll_width, 1600 + 1,
            "Das Dokument überläuft horizontal: "
            f"{scroll_width}px bei 1600px Viewport")
        self.assertEqual(
            0, self.page.locator("aside[data-nv-side] [data-nv-nav]").count(),
            "aside[data-nv-side] enthält noch [data-nv-nav]-Knöpfe "
            "(statische Sidebar)")
        self.assert_no_page_errors()

    def test_default_accent_is_blue(self):
        """Vorbedingung: frischer Kontext ohne gespeicherten Akzent.

        Aktion: booten. Erwartung: ``<html data-accent="blue">`` (Standard
        Blau); ``NV.accent()`` meldet denselben Wert, sofern vorhanden.
        """
        self.boot()
        accent = self.page.evaluate(
            "() => document.documentElement.getAttribute('data-accent')")
        self.assertEqual(
            "blue", accent,
            "Der Standard-Akzent ist nicht blue, sondern " + repr(accent))
        read = self.page.evaluate(
            "() => (window.NV && typeof NV.accent === 'function') "
            "? NV.accent() : null")
        if read is not None:
            self.assertEqual(
                "blue", read,
                "NV.accent() liefert nicht den Standard-Akzent blue")

    def test_toast_auto_dismisses_without_click(self):
        """Vorbedingung: Startseite, Projektanlage ohne Namen (löst einen
        Toast aus, WP1-eigene Datei ``nova-home.js``).

        Aktion: „Anlegen“ mit leerem Namen klicken, Toast beobachten.
        Erwartung: Eine Toast-Karte mit ``data-nv-toast-auto`` erscheint und
        verschwindet ohne Klick innerhalb von ~10 s; der Schließen-Knopf wird
        nicht betätigt.
        """
        self.boot()
        self.page.locator(
            "[data-nv-new-project] [data-nv-action='create-project']").click()
        toast = self.page.locator("#nv-toasts [data-nv-toast-auto]")
        toast.first.wait_for(state="visible", timeout=10000)
        self.assertTrue(toast.first.is_visible(),
                        "Der Toast ist nicht sichtbar")
        self.wait_until(
            lambda: toast.count() == 0 or not toast.first.is_visible(),
            timeout=12,
            message="Der Toast verschwindet nicht von selbst "
                    "(data-nv-toast-auto)")
        self.assert_no_page_errors()

    def test_animation_toggle_label_names_animations_and_state(self):
        """Vorbedingung: angemeldet. Aktion: Label lesen, Schalter umlegen,
        danach auf Deutsch neu laden.

        Erwartung: ``[data-nv-anim-toggle]`` (bzw. sein Label) trägt
        ``aria-label``/``title`` mit „Animation(en)“ und dem Zustand; der Text
        ändert sich beim Umschalten; auf Deutsch enthält das Label
        „Animationen“.
        """
        self.boot()
        toggle = self.page.locator("[data-nv-anim-toggle]")
        self.assertEqual(1, toggle.count(),
                         "Der Animationsschalter fehlt")

        def label_text():
            return self.page.evaluate(
                """() => {
                  const node = document.querySelector(
                    '[data-nv-anim-toggle]');
                  if (!node) return '';
                  const label = node.closest('label');
                  return [
                    node.getAttribute('aria-label') || '',
                    node.getAttribute('title') || '',
                    label ? (label.getAttribute('aria-label') || '') : '',
                    label ? (label.getAttribute('title') || '') : ''
                  ].join(' | ');
                }""")

        before = label_text()
        self.assertRegex(
            before, r"(?i)animation",
            "Das Animations-Label nennt nicht „Animation(en)“: "
            + repr(before))
        toggle.first.click()
        self.wait_until(
            lambda: label_text() != before,
            timeout=10,
            message="Das Animations-Label nennt den Zustand nicht "
                    "(ändert sich beim Umschalten nicht)")

        self.post_language("de")
        self.page.reload()
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)
        self.assertIn(
            "Animationen", label_text(),
            "Das deutsche Animations-Label enthält nicht „Animationen“: "
            + repr(label_text()))


class HomePinTest(F33ShellHomeTest):
    def test_pinning_moves_project_to_pinned_section_and_persists(self):
        """Vorbedingung: fünf Projekte, nichts angeheftet.

        Aktion: Anpinn-Knopf der Karte ``alpha-projekt`` klicken, dann erneut.
        Erwartung: ``button[data-nv-action="project-pin"]`` wechselt
        ``aria-pressed`` false → true; die Karte steht in
        ``section[data-nv-pinned-projects]`` oberhalb von
        ``section[data-nv-projects]``; ``localStorage['nv-pinned-projects']``
        enthält den Namen. Erneuter Klick hebt das Anheften auf (Storage leer,
        Karte nicht mehr in der angehefteten Sektion).
        """
        self.boot()
        self.page.locator("section[data-nv-projects]").wait_for(
            state="visible", timeout=20000)
        card = self.card("alpha-projekt")
        card.wait_for(state="visible", timeout=20000)
        pin = card.locator("[data-nv-action='project-pin']")
        self.assertEqual(
            1, pin.count(),
            "Die Projektkarte hat keinen Anpinn-Knopf "
            "[data-nv-action='project-pin']")
        self.assertNotEqual(
            "true", pin.first.get_attribute("aria-pressed"),
            "Die Karte ist ohne Zutun bereits angeheftet")

        pin.first.click()
        self.wait_until(
            lambda: pin.first.get_attribute("aria-pressed") == "true",
            timeout=10,
            message="Der Anpinn-Knopf setzt aria-pressed nicht auf true")
        pinned = self.page.locator("section[data-nv-pinned-projects]")
        pinned.wait_for(state="visible", timeout=10000)
        self.assertEqual(
            1, pinned.locator("article[data-nv-project='alpha-projekt']").count(),
            "Die angeheftete Karte fehlt in section[data-nv-pinned-projects]")
        stored = self.local_storage_json("nv-pinned-projects")
        self.assertIsInstance(
            stored, list,
            "nv-pinned-projects ist kein JSON-Array: " + repr(stored))
        self.assertIn("alpha-projekt", stored,
                      "nv-pinned-projects enthält den Namen nicht: "
                      + repr(stored))
        pinned_box = pinned.bounding_box()
        projects_box = self.page.locator(
            "section[data-nv-projects]").bounding_box()
        self.assertIsNotNone(pinned_box)
        self.assertIsNotNone(projects_box)
        self.assertLess(
            pinned_box["y"], projects_box["y"],
            "Die angeheftete Sektion steht nicht oberhalb der Projektliste")

        pin.first.click()
        self.wait_until(
            lambda: pin.first.get_attribute("aria-pressed") == "false",
            timeout=10,
            message="Der erneute Klick hebt das Anheften nicht auf")
        self.wait_until(
            lambda: pinned.locator(
                "article[data-nv-project='alpha-projekt']").count() == 0,
            timeout=10,
            message="Die Karte bleibt nach dem Aufheben in der angehefteten "
                    "Sektion")
        stored = self.local_storage_json("nv-pinned-projects")
        self.assertEqual(
            [], stored,
            "nv-pinned-projects ist nach dem Aufheben nicht leer: "
            + repr(stored))
        self.assert_no_page_errors()


class HomeSearchTest(F33ShellHomeTest):
    def test_search_filters_cards_live_and_shows_count(self):
        """Vorbedingung: fünf Projekte, nichts angeheftet.

        Aktion: ``input[data-nv-project-search]`` mit „alpha“ füllen, dann mit
        „projekt“, dann leeren.
        Erwartung: Nicht-Treffer werden ``[hidden]`` (nicht sichtbar); die
        Treffer bleiben sichtbar; ``p[data-nv-search-count]`` nennt die
        Trefferzahl („1 von 5“ / „1 of 5“ bzw. „2 von 5“); nach dem Leeren
        sind wieder alle fünf Karten sichtbar.
        """
        self.boot()
        search = self.page.locator("input[data-nv-project-search]")
        search.wait_for(state="visible", timeout=20000)
        count = self.page.locator("p[data-nv-search-count]")
        self.assertEqual(1, count.count(),
                         "Die Trefferzahl p[data-nv-search-count] fehlt")

        search.fill("alpha")
        self.wait_until(
            lambda: not self.card("beta-projekt").is_visible(),
            timeout=10,
            message="Die Suche blendet Nichttreffer nicht aus")
        self.assertTrue(self.card("alpha-projekt").is_visible(),
                        "Der Treffer alpha-projekt ist nicht sichtbar")
        self.assertRegex(
            (count.inner_text() or "").strip(), r"1\s*(von|of)\s*5",
            "Die Trefferzahl nennt nicht 1 von 5: "
            + repr(count.inner_text()))

        search.fill("projekt")
        self.wait_until(
            lambda: self.card("alpha-projekt").is_visible()
            and self.card("beta-projekt").is_visible(),
            timeout=10,
            message="Die Suche zeigt beide Treffer nicht an")
        self.assertFalse(self.card("gamma").is_visible(),
                         "Die Suche blendet gamma trotz Nichttreffer ein")
        self.assertRegex(
            (count.inner_text() or "").strip(), r"2\s*(von|of)\s*5",
            "Die Trefferzahl nennt nicht 2 von 5: "
            + repr(count.inner_text()))

        search.fill("")
        self.wait_until(
            lambda: all(self.card(name).is_visible() for name, _ in PROJECTS),
            timeout=10,
            message="Nach dem Leeren sind nicht wieder alle Karten sichtbar")
        self.assertRegex(
            (count.inner_text() or "").strip(), r"5\s*(von|of)\s*5",
            "Die Trefferzahl nennt nach dem Leeren nicht 5 von 5: "
            + repr(count.inner_text()))
        self.assert_no_page_errors()


if __name__ == "__main__":
    unittest.main()
