"""Browserabnahme AP22: neue Shell, Anmeldung, Navigation, Theme, Sprache.

Die Fälle leiten sich aus ``docs/features/AP22.md`` („Feste Entscheidungen“,
„Frontend-Vertrag“) ab. Das echte Dashboard läuft als eigener Prozess auf
freiem Port mit isoliertem VIBE-Root und einer lokalen opencode-Attrappe
(Muster ``tests/browser/test_ap21_i18n_ui.py``); Chromium kommt aus dem
Nur-Lese-Nutzer-Cache, niemals heruntergeladen. Keine echten Modellaufrufe.

Die neue Oberfläche liegt unter ``/``, die alte unverändert unter
``/classic``. Getestet wird ausschließlich über die ``data-nv-*``-Hooks und
``I18N``-Texte des Vertrags.

F34-Anpassung: Die fünf Navigationspunkte liegen dauerhaft in der
Kopfzeile (``nav[data-nv-navs]`` mit ``button[data-nv-nav]``); die
statische ``aside[data-nv-side]`` ist bewusst leer. Alle Selektoren auf
Navigation und ``open_settings``-Absprünge sind auf ``nav[data-nv-navs]``
umgestellt (Semantik Klick → Ansicht und ``aria-current`` unverändert).

Sprachlabels: Der Vertrag legt die vier Navigationsbeschriftungen fest —
englisch exakt ``Home``/``Agents``/``Activity``/``Settings``, deutsch exakt
``Start``/``Agenten``/``Aktivität``/``Einstellungen``. Die Quellschlüssel sind
deutsch (``Start`` …); ``bin/web/i18n.js`` wird in der Implementierung um
diese Schlüssel ergänzt. Die Tests prüfen die vier Werte exakt, weil die
Navigationsbegriffe Teil des abgestimmten UI-Vertrags sind.

Testfälle (Kurzfassung; Details in den Methoden)
------------------------------------------------
``ShellBootTest.test_boot_shows_new_shell_without_js_errors``
    Vorbedingung: frischer Kontext, ``#t=<Token>``. Aktion: booten.
    Erwartung: ``body[data-nv-app]``, ``main#nv-main[data-nv-view="home"]``
    sichtbar, Token aus der URL entfernt, keine JS-Fehler.
``AuthTest.test_login_card_without_token_and_token_login``
    Vorbedingung: frischer Kontext ohne Hash. Aktion: ``/`` öffnen, dann
    Instanz-Token in der Karte anmelden. Erwartung: Login-Karte mit Eingabe
    und Knopf, Projektliste unsichtbar; nach Anmeldung Projektliste sichtbar.
``AuthTest.test_token_boot_hides_the_login_card``
    Vorbedingung: ``#t=<Token>``. Aktion: booten. Erwartung: Login-Karte
    unsichtbar.
``NavigationTest.test_nav_buttons_switch_views_and_set_aria_current``
    Aktion: ``data-nv-nav="agents"`` klicken, dann ``home``.
    Erwartung: ``aria-current="page"`` wandert mit, ``main[data-nv-view]``
    folgt (agents, home).
``ThemeTest.test_theme_toggle_cycles_and_persists``
    Aktion: Theme-Knopf klicken, neu laden, erneut klicken.
    Erwartung: hell → dunkel → (Reload hält dunkel) → hell; ``nv-theme``
    liegt im localStorage.
``AnimationTest.test_animation_toggle_persists``
    Aktion: ``input[data-nv-anim-toggle]`` umschalten, neu laden.
    Erwartung: ``data-animations`` on → off, Reload hält off,
    ``nv-animations=off``.
``AnimationTest.test_reduced_motion_disables_animations_without_storage``
    Vorbedingung: frischer Kontext mit ``prefers-reduced-motion: reduce``.
    Erwartung: ``data-animations="off"`` ohne localStorage-Eintrag.
``LanguageTest.test_default_english_and_switch_to_german_persists``
    Aktion: Labels lesen, ``de`` wählen, neu laden.
    Erwartung: englisch ``Home``/``Agents``/``Activity``/``Settings``;
    ``lang="de"`` und ``Start``/``Agenten``/``Aktivität``/``Einstellungen``;
    Reload hält Deutsch (serverseitig über ``/api/language``).
``ResponsiveTest.test_mobile_nav_toggle_and_desktop_layout``
    Aktion: Viewport 390×844, Toggle klicken, dann 1280×800.
    Erwartung: Toggle nur mobil sichtbar, ``aria-expanded`` und Nav-Knöpfe
    folgen; Desktop zeigt die Navigation ohne Toggle.
``BellTest.test_bell_exists_and_badge_is_hidden_when_empty``
    Erwartung: ``button[data-nv-bell]`` vorhanden, Zähler unsichtbar.
``ClassicRouteTest.test_classic_serves_the_old_ui``
    Aktion: ``/classic#t=<Token>`` öffnen. Erwartung: ``nav#nav``,
    ``main#main``, alter Tab ``data-t="projects"`` sichtbar; kein
    ``data-nv-app``.
``RouterTest.test_direct_hash_routes_render_the_matching_views``
    Aktion: ``#/agents``, ``#/activity``, ``#/settings``, ``#/nonsense``.
    Erwartung: passende ``data-nv-view``; unbekannter Hash fällt auf home.
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

NAV_LABELS_EN = {
    "home": "Home",
    "agents": "Agents",
    "activity": "Activity",
    "settings": "Settings",
}
NAV_LABELS_DE = {
    "home": "Start",
    "agents": "Agenten",
    "activity": "Aktivität",
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

        Erwartung: Die vier Vertragsknöpfe existieren; ``aria-current``
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

        Erwartung: ``lang="en"`` und die vier englischen Vertragslabels; nach
        der Wahl ``lang="de"`` und ``Start``/``Agenten``/``Aktivität``/
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


if __name__ == "__main__":
    unittest.main()
