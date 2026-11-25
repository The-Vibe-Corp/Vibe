"""Shell-Oberfläche: Start, Anmeldung, Navigation, Theme, Animationen, Sprache, Responsive, Glocke, Router, Toast, Seitenleiste und Kontextpanel.

Aufruf: python3 -m unittest tests.browser.test_shell_ui -v
"""


# ===========================================================================
# Browserabnahme: neue Shell, Anmeldung, Navigation, Theme, Sprache
# ===========================================================================

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

NAV_LABELS_EN = {
    "home": "Home",
    "agents": "Agents",
    "activity": "Activity",
    "evaluations": "Evaluations",
    "settings": "Settings",
}
NAV_LABELS_DE = {
    "home": "Start",
    "agents": "Agenten",
    "activity": "Aktivität",
    "evaluations": "Auswertungen",
    "settings": "Einstellungen",
}


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


class AP22BrowserTest(unittest.TestCase):
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
            "# FEEDBACK\n", encoding="utf-8")
        (cls.project / "TICKETS.md").write_text(
            "# TICKETS — Test\n\n- [ ] AP22 Testpaket\n"
            "  Beschreibung: Offenes Paket\n", encoding="utf-8")
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
        password.write_text("geheim-AP22-4711", encoding="utf-8")
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

    # ---------- Umgebung je Test ----------

    def setUp(self):
        # Sprache ist serverseitig (AP21): vor jedem Fall auf Englisch
        # zurücksetzen, damit die Fälle unabhängig von der Reihenfolge sind.
        self.post_language("en")
        self.page_errors = []
        self.console_errors = []
        self.context = self.browser.new_context(
            viewport={"width": 1400, "height": 900})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))
        self.page.on("console", self._on_console)

    def _on_console(self, message):
        if message.type == "error":
            self.console_errors.append(message.text)

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

    def post_language(self, lang, token=None):
        """Setzt die globale Sprache über die API (Test-Vorbedingung)."""
        body = json.dumps({"language": lang}).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", "/api/language", body=body, headers={
                "Host": f"127.0.0.1:{self.port}", "X-Token": token or self.token,
                "Content-Type": "application/json"})
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def boot(self, page=None, hash_route=""):
        """Öffnet die neue UI mit Token-Tausch (``#t=``) und wartet auf home."""
        page = page or self.page
        page.goto(self.base + "/" + hash_route + "#t=" + self.token)
        page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def html_attr(self, name):
        return self.page.evaluate(
            "name => document.documentElement.getAttribute(name)", name)

    def local_storage(self, key):
        return self.page.evaluate(
            "key => window.localStorage.getItem(key)", key)

    def nav_labels(self):
        return self.page.evaluate(
            """() => {
              const out = {};
              document.querySelectorAll('[data-nv-nav]').forEach(node => {
                out[node.getAttribute('data-nv-nav')] =
                  (node.innerText || '').trim();
              });
              return out;
            }""")

    def i18n_current(self):
        return self.page.evaluate(
            """() => {
              const api = window.VIBE_I18N || window.I18N;
              return api && typeof api.current === 'function'
                ? api.current() : null;
            }""")

    def assert_login_card(self, page=None, visible=True):
        page = page or self.page
        card = page.locator("[data-nv-login]")
        if visible:
            card.wait_for(state="visible", timeout=15000)
        else:
            self.assertFalse(
                card.is_visible() if card.count() else False,
                "Die Login-Karte ist trotz Anmeldung sichtbar")

    def assert_clean_page(self):
        self.assertEqual(
            [], self.page_errors, "Die Oberfläche erzeugte JavaScript-Fehler")
        # Netzwerkfehler für favicon.ico sind kein JS-Fehler und werden
        # deshalb ausgeblendet; alles andere zählt als Konsolenfehler.
        relevant = [text for text in self.console_errors
                    if "favicon" not in text.lower()]
        self.assertEqual(
            [], relevant, "Die Oberfläche meldete Konsolenfehler")


class ShellBootTest(AP22BrowserTest):
    def test_boot_shows_new_shell_without_js_errors(self):
        """Vorbedingung: frischer Kontext, ``#t=<Token>``. Aktion: booten.

        Erwartung: ``body[data-nv-app]`` vorhanden, ``main#nv-main`` mit
        ``data-nv-view="home"`` sichtbar, Login-Karte unsichtbar, Token aus
        der URL entfernt, keine JS-/Konsolenfehler.
        """
        self.boot()
        self.assertEqual(
            1, self.page.locator("body[data-nv-app]").count(),
            "body[data-nv-app] fehlt in der neuen Shell")
        self.assert_login_card(visible=False)
        self.assertNotIn(
            self.token, self.page.url,
            "Der Token steht nach dem Boot noch in der URL")
        self.assert_clean_page()


class AuthTest(AP22BrowserTest):
    def test_login_card_without_token_and_token_login(self):
        """Vorbedingung: frischer Kontext ohne Hash und ohne Cookie.

        Aktion: ``/`` öffnen; Token in die Karte eingeben und anmelden.
        Erwartung: Karte mit ``input[data-nv-login-input]`` und
        ``button[data-nv-login-submit]`` sichtbar, Projektliste unsichtbar;
        nach der Anmeldung erscheint die Projektliste.
        """
        self.page.goto(self.base + "/")
        self.assert_login_card()
        self.assertEqual(
            1, self.page.locator("[data-nv-login] input[data-nv-login-input]").count(),
            "Eingabefeld der Login-Karte fehlt")
        self.assertEqual(
            1,
            self.page.locator(
                "[data-nv-login] button[data-nv-login-submit]").count(),
            "Anmeldeknopf der Login-Karte fehlt")
        projects = self.page.locator("[data-nv-projects]")
        self.assertFalse(
            projects.is_visible() if projects.count() else False,
            "Die Projektliste ist ohne Anmeldung sichtbar")

        self.page.locator(
            "[data-nv-login] input[data-nv-login-input]").fill(self.token)
        self.page.locator(
            "[data-nv-login] button[data-nv-login-submit]").click()
        self.page.locator("[data-nv-projects]").wait_for(
            state="visible", timeout=20000)
        self.assert_login_card(visible=False)

    def test_token_boot_hides_the_login_card(self):
        """Vorbedingung: ``#t=<Token>``. Aktion: booten.

        Erwartung: Die Login-Karte ist nicht sichtbar (Token wurde gegen die
        Session getauscht).
        """
        self.boot()
        self.assert_login_card(visible=False)


class NavigationTest(AP22BrowserTest):
    def test_nav_buttons_switch_views_and_set_aria_current(self):
        """Vorbedingung: angemeldet. Aktion: Agents, dann Home klicken.

        Erwartung: Die fünf Vertragsknöpfe existieren; ``aria-current``
        markiert den aktiven Knopf; ``main[data-nv-view]`` folgt
        (agents → agents, home → home).
        """
        self.boot()
        # Die fünf Navigationsknöpfe liegen dauerhaft in der Kopfzeile
        # (nav[data-nv-navs]) — F34 entfernt die statische Sidebar. Die
        # Semantik (Klick erreicht die Ansicht, aria-current wandert)
        # bleibt unverändert.
        nav_scope = "nav[data-nv-navs]"
        for key in NAV_LABELS_EN:
            self.assertEqual(
                1,
                self.page.locator(
                    f"{nav_scope} [data-nv-nav='{key}']").count(),
                f"Navigationsknopf data-nv-nav={key!r} fehlt")

        self.page.locator(f"{nav_scope} [data-nv-nav='agents']").click()
        self.page.locator("main#nv-main[data-nv-view='agents']").wait_for(
            state="visible", timeout=20000)
        self.assertEqual(
            "page",
            self.page.locator(
                f"{nav_scope} [data-nv-nav='agents']").get_attribute(
                "aria-current"),
            "Der aktive Agents-Knopf trägt kein aria-current=page")

        self.page.locator(f"{nav_scope} [data-nv-nav='home']").click()
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=20000)
        self.assertEqual(
            "page",
            self.page.locator(
                f"{nav_scope} [data-nv-nav='home']").get_attribute(
                "aria-current"),
            "Der aktive Home-Knopf trägt kein aria-current=page")
        self.assert_clean_page()


class ThemeTest(AP22BrowserTest):
    def test_theme_toggle_cycles_and_persists(self):
        """Vorbedingung: frisches Profil. Aktion: Theme-Knopf, Reload, Knopf.

        Erwartung: ``data-theme`` hell → dunkel; nach Reload dunkel; erneut
        klicken → hell; ``nv-theme`` liegt im localStorage.
        """
        self.boot()
        self.assertEqual("light", self.html_attr("data-theme"),
                         "Der Theme-Standard ist nicht hell")

        self.page.locator("button[data-nv-theme-toggle]").click()
        self.wait_until(
            lambda: self.html_attr("data-theme") == "dark",
            timeout=10,
            message="Der Theme-Knopf schaltete nicht auf dunkel")
        self.assertEqual("dark", self.local_storage("nv-theme"),
                         "nv-theme wurde nicht gespeichert")

        self.page.reload()
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)
        self.assertEqual(
            "dark", self.html_attr("data-theme"),
            "Nach dem Reload ging die dunkle Darstellung verloren")

        self.page.locator("button[data-nv-theme-toggle]").click()
        self.wait_until(
            lambda: self.html_attr("data-theme") == "light",
            timeout=10,
            message="Der Theme-Knopf schaltete nicht zurück auf hell")


class AnimationTest(AP22BrowserTest):
    def test_animation_toggle_persists(self):
        """Vorbedingung: frisches Profil. Aktion: Animations-Schalter, Reload.

        Erwartung: ``data-animations`` on → off; Reload hält off;
        ``nv-animations=off``.
        """
        self.boot()
        self.assertEqual("on", self.html_attr("data-animations"),
                         "Der Animations-Standard ist nicht on")

        self.page.locator("input[data-nv-anim-toggle]").click()
        self.wait_until(
            lambda: self.html_attr("data-animations") == "off",
            timeout=10,
            message="Der Animations-Schalter setzte data-animations nicht")
        self.assertEqual("off", self.local_storage("nv-animations"),
                         "nv-animations wurde nicht gespeichert")

        self.page.reload()
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)
        self.assertEqual(
            "off", self.html_attr("data-animations"),
            "Nach dem Reload waren die Animationen wieder an")

    def test_reduced_motion_disables_animations_without_storage(self):
        """Vorbedingung: frischer Kontext mit ``prefers-reduced-motion``.

        Aktion: booten. Erwartung: ``data-animations="off"`` ohne
        localStorage-Eintrag ``nv-animations`` (Systemwunsch, keine
        gespeicherte Wahl).
        """
        context = self.browser.new_context(
            viewport={"width": 1400, "height": 900}, reduced_motion="reduce")
        try:
            page = context.new_page()
            self.boot(page=page)
            animations = page.evaluate(
                "() => document.documentElement.getAttribute('data-animations')")
            self.assertEqual(
                "off", animations,
                "prefers-reduced-motion schaltet die Animationen nicht ab")
            self.assertIsNone(
                page.evaluate(
                    "() => window.localStorage.getItem('nv-animations')"),
                "Trotz Systemwunsch wurde eine Animationseinstellung gespeichert")
        finally:
            context.close()


class LanguageTest(AP22BrowserTest):
    def test_default_english_and_switch_to_german_persists(self):
        """Vorbedingung: frisches Profil. Aktion: Labels lesen, ``de`` wählen.

        Erwartung: ``lang="en"`` und die fünf englischen Vertragslabels; nach
        der Wahl ``lang="de"`` und
        ``Start``/``Agenten``/``Aktivität``/``Auswertungen``/
        ``Einstellungen``; ein Reload hält Deutsch (serverseitig, AP21).
        """
        self.boot()
        self.assertEqual("en", self.page.evaluate(
            "() => document.documentElement.lang"))
        self.assertEqual("en", self.i18n_current())
        self.wait_until(
            lambda: self.nav_labels() == NAV_LABELS_EN,
            timeout=15,
            message="Die englischen Navigationslabels fehlen: "
                    + repr(self.nav_labels()))

        # Der Sprachumschalter liegt im Einstellungsbereich (AP22-Vertrag).
        # Die Navigationsknöpfe liegen dauerhaft in der Kopfzeile
        # (nav[data-nv-navs]) — F34 entfernt die statische Sidebar.
        self.page.locator(
            "nav[data-nv-navs] [data-nv-nav='settings']").click()
        self.page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=20000)
        self.page.locator("select[aria-label='Language']").select_option("de")
        self.wait_until(
            lambda: self.page.evaluate(
                "() => document.documentElement.lang") == "de",
            timeout=20,
            message="<html lang> wurde nach der Sprachwahl nicht de")
        self.wait_until(
            lambda: self.nav_labels() == NAV_LABELS_DE,
            timeout=20,
            message="Die deutschen Navigationslabels fehlen: "
                    + repr(self.nav_labels()))

        self.page.reload()
        self.page.locator(
            "nav[data-nv-navs] [data-nv-nav='home']").wait_for(
            state="visible", timeout=25000)
        self.assertEqual(
            "de", self.page.evaluate("() => document.documentElement.lang"),
            "Nach dem Reload ist die Sprache nicht mehr Deutsch")
        self.wait_until(
            lambda: self.nav_labels() == NAV_LABELS_DE,
            timeout=15,
            message="Nach dem Reload sind die Labels nicht Deutsch: "
                    + repr(self.nav_labels()))


class ResponsiveTest(AP22BrowserTest):
    def test_mobile_nav_toggle_and_desktop_layout(self):
        """Vorbedingung: angemeldet. Aktion: schmaler Viewport, Toggle, breit.

        Erwartung: mobil ist ``button[data-nv-nav-toggle]`` sichtbar; der
        Klick setzt ``aria-expanded="true"`` und zeigt die Nav-Knöpfe; bei
        1280×800 ist der Toggle verborgen und die Navigation direkt in der
        Kopfzeile sichtbar (``nav[data-nv-navs]`` — F34: keine Sidebar).
        """
        self.boot()
        self.page.set_viewport_size({"width": 390, "height": 844})
        toggle = self.page.locator("button[data-nv-nav-toggle]")
        toggle.wait_for(state="visible", timeout=15000)
        self.assertNotEqual(
            "true", toggle.get_attribute("aria-expanded"),
            "Der Nav-Toggle ist mobil bereits expandiert")

        toggle.click()
        self.wait_until(
            lambda: toggle.get_attribute("aria-expanded") == "true",
            timeout=10,
            message="Der Nav-Toggle setzte aria-expanded nicht")
        self.assertTrue(
            self.page.locator(".nv-top [data-nv-nav='home']").is_visible(),
            "Die Navigationsknöpfe sind nach dem Aufklappen nicht sichtbar")

        self.page.set_viewport_size({"width": 1280, "height": 800})
        self.wait_until(
            lambda: not toggle.is_visible(),
            timeout=10,
            message="Der Nav-Toggle bleibt auf dem Desktop sichtbar")
        self.wait_until(
            lambda: self.page.locator(
                "nav[data-nv-navs] [data-nv-nav='home']").is_visible(),
            timeout=10,
            message="Die Navigation ist auf dem Desktop nicht direkt "
                    "sichtbar (nav[data-nv-navs] in der Kopfzeile)")


class BellTest(AP22BrowserTest):
    def test_bell_exists_and_badge_is_hidden_when_empty(self):
        """Vorbedingung: angemeldet, keine offenen Fragen/Läufe.

        Erwartung: ``button[data-nv-bell]`` vorhanden; der Zähler
        ``span[data-nv-bell-count]`` ist unsichtbar.
        """
        self.boot()
        self.page.locator("button[data-nv-bell]").wait_for(
            state="visible", timeout=15000)
        badge = self.page.locator("span[data-nv-bell-count]")
        self.assertEqual(
            1, badge.count(), "Der Glocken-Zähler fehlt im DOM")
        self.assertFalse(
            badge.is_visible(),
            "Der Glocken-Zähler ist ohne Meldungen sichtbar")


class ClassicRouteTest(AP22BrowserTest):
    def test_classic_serves_the_old_ui(self):
        """Vorbedingung: frischer Kontext. Aktion: ``/classic#t=<Token>``.

        Erwartung: ``nav#nav``, ``main#main`` und der alte Tab
        ``data-t="projects"`` sind sichtbar; ``body`` trägt kein
        ``data-nv-app``.
        """
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.page.locator("#nav button[data-t='projects']").wait_for(
            state="visible", timeout=25000)
        self.assertEqual(
            1, self.page.locator("#nav").count(),
            "Die klassische Navigation nav#nav fehlt unter /classic")
        self.assertEqual(
            1, self.page.locator("main#main").count(),
            "Der klassische Hauptbereich main#main fehlt unter /classic")
        self.assertEqual(
            0, self.page.locator("body[data-nv-app]").count(),
            "Unter /classic erscheint die neue Shell")


class RouterTest(AP22BrowserTest):
    def test_direct_hash_routes_render_the_matching_views(self):
        """Vorbedingung: angemeldet (Cookie aus dem Boot). Aktion: Hash-Routen
        direkt öffnen.

        Erwartung: ``#/agents``, ``#/activity``, ``#/settings`` rendern die
        passende ``data-nv-view``; ``#/nonsense`` fällt auf home zurück.
        """
        self.boot()
        for route, view in (
            ("#/agents", "agents"),
            ("#/activity", "activity"),
            ("#/settings", "settings"),
        ):
            with self.subTest(route=route):
                self.page.goto(self.base + "/" + route)
                self.page.locator(
                    f"main#nv-main[data-nv-view='{view}']").wait_for(
                        state="visible", timeout=25000)

        self.page.goto(self.base + "/#/nonsense")
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)


# ===========================================================================
# Browserabnahme: Shell, Design, Benachrichtigungen, zentrale Bausteine
# ===========================================================================

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

if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import (  # noqa: E402
    Error as PlaywrightError,
    sync_playwright,
)


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


# ===========================================================================
# Browserabnahme: Shell, Design und Startseite
# ===========================================================================

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

if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402


# Fünf Projekte, damit Suche und Trefferzahl echte Filterarbeit leisten.


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
