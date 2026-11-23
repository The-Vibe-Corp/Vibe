"""Browserabnahme AP22: Einstellungen (Erscheinung, Zugriff, Features).

Die Fälle leiten sich aus ``docs/features/AP22.md`` („Einstellungen“,
„Feste Entscheidungen“ Punkt 4/5) und dem AP21-Vertrag für die globale
Sprache ab. Das echte Dashboard läuft als eigener Prozess mit isoliertem
VIBE-Root und opencode-Attrappe (Muster
``tests/browser/test_ap21_i18n_ui.py``).

F34-Anpassung: Die statische Sidebar entfällt; ``open_settings`` nutzt die
permanente Kopf-Navigation (``nav[data-nv-navs]``).

Dokumentierte Lesarten, wo der Vertrag keinen eigenen Hook nennt:

* Bestätigung nach „Kennwort setzen“ und sichtbare Fehler: Der Vertrag nennt
  nur Toasts ``#nv-toasts`` und (allgemein) ``data-nv-*``; der Test akzeptiert
  einen sichtbaren Toast, einen ``[data-nv-form-error]`` oder einen sichtbaren
  Bestätigungstext im Zugriffsbereich.
* Projekt-Override-Formular der Schranken: Der Vertrag nennt keinen Hook für
  die Felder; der Test verlangt, dass der erweiterte Bereich ``gates`` die
  Schrankenschlüssel der API nennt und mindestens ein Eingabe-/Auswahlfeld
  für den Projektwert enthält.
* Theme ``auto``: ``data-theme`` bleibt laut Shell-Vertrag ``light`` oder
  ``dark`` (aufgelöster Wert); der Test prüft genau das.

Testfälle (Kurzfassung; Details in den Methoden)
------------------------------------------------
``SectionsTest.test_sections_shell_and_classic_link_exist``
``SectionsTest.test_theme_select_offers_light_dark_auto``
``SectionsTest.test_animations_switch_syncs_with_html_attribute``
``SectionsTest.test_language_select_options_match_contract``
    Aktion: Einstellungen öffnen und die Sektionen/Bedienelemente lesen.
    Erwartung: fünf Sektionen, Theme-Select hell/dunkel/system,
    Animations-Schalter synchron zu ``data-animations``,
    ``select[aria-label="Language"]`` mit genau English/Deutsch und Wert
    ``I18N.current()``, Klassisch-Link auf ``/classic``.
``AccessTest.test_password_set_login_and_clear``
    Vorbedingung: angemeldet. Aktion: Kennwort setzen (mit Wiederholung),
    frischer Kontext: falsches und richtiges Kennwort, danach löschen.
    Erwartung: Bestätigung; falsches Kennwort bleibt auf der Karte, richtiges
    öffnet die Projekte; nach dem Löschen verlangt ein frischer Kontext
    wieder Token (Kennwort wird abgelehnt).
``AccessTest.test_port_validation_and_restart_note``
    Aktion: ungültigen Port speichern, dann einen freien Port.
    Erwartung: sichtbarer Fehler und unveränderte ``ui.json``; gültiger Port
    erzeugt den Neustart-Hinweis ``[data-nv-restart-note]`` und steht in
    ``ui.json``.
``FeaturesTest.test_all_feature_toggles_exist_and_default_unchecked``
    Erwartung: je dokumentierter Feature-ID ein ``input[data-nv-feature]``,
    alle standardmäßig aus.
``FeaturesTest.test_advanced_limits_appears_and_switches_mode``
    Aktion: Feature ``limits`` einschalten, Modus auf continue stellen.
    Erwartung: Bereich ``[data-nv-advanced="limits"]`` erscheint ohne
    Neuladen und zeigt den Modus; ``GET /api/limits`` bestätigt ``continue``.
``FeaturesTest.test_advanced_gates_shows_keys_and_project_form``
    Aktion: Feature ``gates`` einschalten. Erwartung: Bereich erscheint,
    nennt die Schrankenschlüssel aus ``GET /api/gates`` und bietet ein
    Projekt-Override-Feld.
``LogoutTest.test_logout_shows_login_card_and_blocks_api``
    Aktion: Abmelden. Erwartung: Login-Karte sichtbar; ``GET /api/projects``
    im Browser antwortet 403.
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

FEATURE_IDS = (
    "github", "models", "profiles", "mcp", "costs", "harness", "limits",
    "gates", "env", "sandbox", "writeaccess", "agentsfile", "priority",
    "runs",
)
SECTIONS = ("appearance", "language", "access", "features", "advanced")
AP22_PASSWORD = "ap22-ui-kennwort-42"


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


class AP22SettingsBrowserTest(unittest.TestCase):
    """Dashboard, Projekt, Browser, opencode-Attrappe, isolierter Zustand."""

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
        password.write_text("geheim-AP22-settings", encoding="utf-8")
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

    def setUp(self):
        # Unabhängige Vorbedingung: Sprache englisch, kein Kennwort gesetzt.
        self.api_post("/api/language", {"language": "en"})
        self.api_post("/api/security", {"action": "password", "clear": True})
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

    def api_post(self, path, payload, token=None):
        """POST direkt über HTTP mit Instanz-Token (Test-Vorbedingung)."""
        body = json.dumps(payload).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("POST", path, body=body, headers={
                "Host": f"127.0.0.1:{self.port}",
                "X-Token": token or self.token,
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{self.port}",
                "Sec-Fetch-Site": "same-origin"})
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def api_get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("GET", path, headers={
                "Host": f"127.0.0.1:{self.port}",
                "X-Token": self.token})
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def api_json(self, path):
        status, body = self.api_get(path)
        self.assertEqual(200, status, body)
        return json.loads(body)

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_settings(self):
        self.page.locator("nav[data-nv-navs] [data-nv-nav='settings']").click()
        self.page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=20000)

    def ui_json_path(self):
        return self.state_dir / "ui.json"

    def ui_json(self):
        path = self.ui_json_path()
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def visible_error_text(self):
        parts = []
        for selector in ("#nv-toasts", "[data-nv-form-error]"):
            nodes = self.page.locator(selector)
            for index in range(nodes.count()):
                node = nodes.nth(index)
                if node.is_visible():
                    parts.append((node.inner_text() or "").strip())
        access = self.page.locator("[data-nv-ssection='access']")
        if access.count() and access.is_visible():
            text = access.inner_text() or ""
            for word in ("ungültig", "invalid", "Fehler", "error"):
                if word in text:
                    parts.append(text)
                    break
        return "\n".join(parts)

    def confirmation_visible(self):
        toasts = self.page.locator("#nv-toasts")
        if toasts.count() and toasts.is_visible() and (
                toasts.inner_text() or "").strip():
            return True
        access = self.page.locator("[data-nv-ssection='access']")
        if access.count() and access.is_visible():
            text = (access.inner_text() or "").lower()
            return any(word in text for word in
                       ("gespeichert", "saved", "gesetzt", "set", "success"))
        return False

    def login(self, page, secret):
        page.locator("[data-nv-login] input[data-nv-login-input]").fill(secret)
        page.locator("[data-nv-login] button[data-nv-login-submit]").click()

    def assert_no_page_errors(self):
        self.assertEqual(
            [], self.page_errors, "Die Oberfläche erzeugte JavaScript-Fehler")


class SettingsTest(AP22SettingsBrowserTest):
    # ---------- Sektionen und Erscheinung ----------

    def test_sections_shell_and_classic_link_exist(self):
        """Vorbedingung: angemeldet. Aktion: Einstellungen öffnen.

        Erwartung: die fünf Sektionen ``appearance``/``language``/``access``/
        ``features``/``advanced`` existieren; der Klassisch-Link
        ``a[data-nv-classic-link]`` zeigt auf ``/classic``.
        """
        self.boot()
        self.open_settings()
        # F33 WP5: erweiterte Bereiche (inkl. „Auswertungen") und der
        # Klassisch-Link werden erst nach den parallelen Datenabrufen
        # asynchron ans DOM gehängt — nicht schon mit dem Basis-Render.
        self.page.locator("[data-nv-ssection='advanced']").wait_for(
            state="visible", timeout=15000)
        self.page.locator("a[data-nv-classic-link]").wait_for(
            state="visible", timeout=15000)
        for section in SECTIONS:
            with self.subTest(section=section):
                self.assertEqual(
                    1,
                    self.page.locator(
                        f"[data-nv-ssection='{section}']").count(),
                    f"Sektion data-nv-ssection={section!r} fehlt")
        link = self.page.locator("a[data-nv-classic-link]")
        self.assertEqual(1, link.count(),
                         "Der Klassisch-Link a[data-nv-classic-link] fehlt")
        self.assertTrue(
            (link.get_attribute("href") or "").endswith("/classic"),
            "Der Klassisch-Link zeigt nicht auf /classic: "
            + repr(link.get_attribute("href")))

    def test_theme_select_offers_light_dark_auto(self):
        """Vorbedingung: Einstellungen offen. Aktion: dunkel, dann auto wählen.

        Erwartung: Optionen ``light``/``dark``/``auto``; dunkel setzt
        ``data-theme="dark"``; auto löst auf ``light`` oder ``dark`` auf
        (der Shell-Vertrag kennt nur diese beiden Attributwerte).
        """
        self.boot()
        self.open_settings()
        select = self.page.locator("[data-nv-theme-select]")
        select.wait_for(state="visible", timeout=15000)
        values = select.evaluate(
            "node => Array.from(node.options).map(o => o.value)")
        self.assertEqual(
            ["light", "dark", "auto"], values,
            "Der Theme-Select bietet nicht light/dark/auto: " + repr(values))

        select.select_option("dark")
        self.wait_until(
            lambda: self.page.evaluate(
                "() => document.documentElement.getAttribute('data-theme')")
            == "dark",
            timeout=10,
            message="Die Wahl 'dark' setzte data-theme nicht")

        select.select_option("auto")
        self.wait_until(
            lambda: self.page.evaluate(
                "() => document.documentElement.getAttribute('data-theme')")
            in ("light", "dark"),
            timeout=10,
            message="Die Wahl 'auto' löste kein light/dark auf")

    def test_animations_switch_syncs_with_html_attribute(self):
        """Vorbedingung: Einstellungen offen. Aktion: Schalter aus und ein.

        Erwartung: ``input[data-nv-anim-toggle]`` schaltet
        ``data-animations`` auf ``off`` und zurück auf ``on``.
        """
        self.boot()
        self.open_settings()
        toggle = self.page.locator("input[data-nv-anim-toggle]")
        toggle.wait_for(state="visible", timeout=15000)
        self.assertEqual(
            "on",
            self.page.evaluate(
                "() => document.documentElement.getAttribute('data-animations')"),
            "Der Animations-Standard ist nicht on")

        toggle.uncheck()
        self.wait_until(
            lambda: self.page.evaluate(
                "() => document.documentElement.getAttribute('data-animations')")
            == "off",
            timeout=10,
            message="Der Schalter setzte data-animations nicht auf off")
        toggle.check()
        self.wait_until(
            lambda: self.page.evaluate(
                "() => document.documentElement.getAttribute('data-animations')")
            == "on",
            timeout=10,
            message="Der Schalter setzte data-animations nicht zurück auf on")

    def test_language_select_options_match_contract(self):
        """Vorbedingung: Einstellungen offen. Aktion: Sprachumschalter lesen.

        Erwartung: genau ``English`` (``en``) und ``Deutsch`` (``de``); der
        Wert entspricht ``I18N.current()``.
        """
        self.boot()
        self.open_settings()
        select = self.page.locator("select[aria-label='Language']")
        self.assertEqual(
            1, select.count(),
            "Es gibt nicht genau einen Sprachumschalter")
        options = select.evaluate(
            "node => Array.from(node.options).map(o => [o.value, "
            "o.textContent.trim()])")
        self.assertEqual(
            [["en", "English"], ["de", "Deutsch"]], options,
            "Der Sprachumschalter bietet nicht genau English/Deutsch: "
            + repr(options))
        current = self.page.evaluate(
            """() => {
              const api = window.VIBE_I18N || window.I18N;
              return api && typeof api.current === 'function'
                ? api.current() : null;
            }""")
        self.assertEqual(current, select.input_value(),
                         "Der Umschalter steht nicht auf I18N.current()")

    # ---------- Zugriff ----------

    def test_password_set_login_and_clear(self):
        """Vorbedingung: angemeldet, kein Kennwort. Aktion: Kennwort setzen,
        frischer Kontext (falsch/richtig), Kennwort löschen.

        Erwartung: Bestätigung sichtbar; das falsche Kennwort bleibt auf der
        Login-Karte, das richtige öffnet die Projektliste; nach dem Löschen
        verlangt ein frischer Kontext wieder Token (Kennwort wird abgelehnt).
        """
        self.boot()
        self.open_settings()
        self.page.locator("input[data-nv-field='password']").fill(AP22_PASSWORD)
        self.page.locator("input[data-nv-field='password-repeat']").fill(AP22_PASSWORD)
        self.page.locator("[data-nv-action='password-set']").click()
        self.wait_until(
            self.confirmation_visible, timeout=20000,
            message="Nach dem Setzen des Kennworts erscheint keine Bestätigung")
        self.assertTrue(
            self.api_json("/api/security").get("password_set"),
            "Der Server meldet kein gesetztes Kennwort")

        context = self.browser.new_context(
            viewport={"width": 1200, "height": 900})
        try:
            fresh = context.new_page()
            fresh.goto(self.base + "/")
            fresh.locator("[data-nv-login]").wait_for(
                state="visible", timeout=20000)
            self.login(fresh, "falsches-kennwort-ap22")
            fresh.wait_for_timeout(1500)
            self.assertTrue(
                fresh.locator("[data-nv-login]").is_visible(),
                "Ein falsches Kennwort öffnete die Oberfläche")
            self.assertFalse(
                fresh.locator("[data-nv-projects]").is_visible(),
                "Die Projektliste ist nach falschem Kennwort sichtbar")

            self.login(fresh, AP22_PASSWORD)
            fresh.locator("[data-nv-projects]").wait_for(
                state="visible", timeout=20000)
        finally:
            context.close()

        self.page.locator("[data-nv-action='password-clear']").click()
        self.wait_until(
            lambda: not self.api_json("/api/security").get("password_set"),
            timeout=20000,
            message="Das Kennwort wurde nicht entfernt")

        context = self.browser.new_context(
            viewport={"width": 1200, "height": 900})
        try:
            fresh = context.new_page()
            fresh.goto(self.base + "/")
            fresh.locator("[data-nv-login]").wait_for(
                state="visible", timeout=20000)
            self.login(fresh, AP22_PASSWORD)
            fresh.wait_for_timeout(1500)
            self.assertTrue(
                fresh.locator("[data-nv-login]").is_visible(),
                "Das gelöschte Kennwort meldet noch an")
        finally:
            context.close()
        self.assert_no_page_errors()

    def test_port_validation_and_restart_note(self):
        """Vorbedingung: Einstellungen offen. Aktion: ungültigen, dann freien
        Port speichern.

        Erwartung: ``70000`` erzeugt einen sichtbaren Fehler und lässt
        ``ui.json`` byte-gleich; ein freier Port erzeugt den sichtbaren
        Neustart-Hinweis ``[data-nv-restart-note]`` und steht als ``ui_port``
        in ``ui.json``. Die Netzwerk-Felder liegen vertragsgemäß im
        standardmäßig zusammengeklappten ``details[data-nv-network-advanced]``
        und werden vor der Prüfung aufgeklappt.
        """
        self.boot()
        self.open_settings()
        # F33 WP5: Netzwerk ist standardmäßig zusammengeklappt (Vertrag).
        network = self.page.locator("details[data-nv-network-advanced]")
        network.wait_for(state="attached", timeout=15000)
        network.locator("summary").click()
        field = self.page.locator("input[data-nv-field='port']")
        field.wait_for(state="visible", timeout=15000)
        save = self.page.locator("[data-nv-action='security-save']")

        before = (self.ui_json_path().read_bytes()
                  if self.ui_json_path().exists() else None)
        field.fill("70000")
        save.click()
        self.wait_until(
            lambda: self.visible_error_text() != "",
            timeout=20000,
            message="Der ungültige Port erzeugte keinen sichtbaren Fehler")
        after = (self.ui_json_path().read_bytes()
                 if self.ui_json_path().exists() else None)
        self.assertEqual(before, after,
                         "Der ungültige Port veränderte ui.json")

        free = free_port()
        field.fill(str(free))
        save.click()
        self.page.locator("[data-nv-restart-note]").wait_for(
            state="visible", timeout=20000)
        self.assertEqual(
            free, self.ui_json().get("ui_port"),
            "ui.json enthält den gespeicherten Port nicht")

        # Aufräumen: laufenden Port wieder eintragen (Neustart-Hinweis weg).
        self.api_post("/api/security", {"action": "save", "port": self.port})
        self.assert_no_page_errors()

    # ---------- Feature-Schalter und erweiterte Bereiche ----------

    def test_all_feature_toggles_exist_and_default_unchecked(self):
        """Vorbedingung: frisches Profil. Aktion: Einstellungen öffnen.

        Erwartung: je dokumentierter Feature-ID ein
        ``input[data-nv-feature]``; alle sind standardmäßig aus.
        """
        self.boot()
        self.open_settings()
        for feature in FEATURE_IDS:
            with self.subTest(feature=feature):
                toggle = self.page.locator(
                    f"input[data-nv-feature='{feature}']")
                self.assertEqual(
                    1, toggle.count(),
                    f"Feature-Schalter data-nv-feature={feature!r} fehlt")
                self.assertFalse(
                    toggle.is_checked(),
                    f"Feature {feature!r} ist standardmäßig eingeschaltet")

    def test_advanced_limits_appears_and_switches_mode(self):
        """Vorbedingung: Feature ``limits`` aus, Modus ``stop``. Aktion:
        Schalter an, dann ``limits-continue``.

        Erwartung: ``[data-nv-advanced="limits"]`` ist zunächst unsichtbar,
        erscheint nach dem Einschalten ohne Neuladen und nennt den Modus;
        der Knopf stellt auf ``continue`` um, was ``GET /api/limits``
        bestätigt.
        """
        self.api_post("/api/limits", {"action": "stop"})
        self.boot()
        self.open_settings()
        advanced = self.page.locator("[data-nv-advanced='limits']")
        self.assertFalse(
            advanced.is_visible() if advanced.count() else False,
            "Der Bereich limits ist ohne Feature-Schalter sichtbar")

        self.page.locator("input[data-nv-feature='limits']").check()
        advanced.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: "stop" in (advanced.inner_text() or "").lower(),
            timeout=20000,
            message="Der Bereich limits nennt den aktuellen Modus nicht: "
                    + repr(advanced.inner_text() if advanced.count() else ""))

        self.page.locator("[data-nv-action='limits-continue']").click()
        self.wait_until(
            lambda: "continue" in (advanced.inner_text() or "").lower(),
            timeout=20000,
            message="Der Moduswechsel auf continue wird nicht angezeigt")
        data = self.api_json("/api/limits")
        self.assertEqual("continue", data.get("mode"),
                         "GET /api/limits bestätigt den Moduswechsel nicht: "
                         + repr(data))
        self.assert_no_page_errors()

    def test_advanced_gates_shows_keys_and_project_form(self):
        """Vorbedingung: Feature ``gates`` aus. Aktion: Schalter an.

        Erwartung: ``[data-nv-advanced="gates"]`` erscheint, nennt die
        Schrankenschlüssel aus ``GET /api/gates`` und enthält mindestens ein
        Feld für den Projekt-Override.
        """
        self.boot()
        self.open_settings()
        gates_view = self.api_json("/api/gates")
        self.assertTrue(gates_view.get("ok"), gates_view)

        advanced = self.page.locator("[data-nv-advanced='gates']")
        self.assertFalse(
            advanced.is_visible() if advanced.count() else False,
            "Der Bereich gates ist ohne Feature-Schalter sichtbar")

        self.page.locator("input[data-nv-feature='gates']").check()
        advanced.wait_for(state="visible", timeout=20000)
        text = advanced.inner_text()
        for key in gates_view["gates"]:
            with self.subTest(gate=key):
                self.assertIn(key, text,
                              "Der Bereich gates nennt die Schranke "
                              f"{key!r} nicht")
        self.assertGreaterEqual(
            advanced.locator("input, select, textarea").count(), 1,
            "Der Bereich gates bietet kein Feld für den Projekt-Override")
        self.assert_no_page_errors()


class LogoutTest(AP22SettingsBrowserTest):
    def test_logout_shows_login_card_and_blocks_api(self):
        """Vorbedingung: angemeldet. Aktion: ``[data-nv-action="logout"]``.

        Erwartung: Die Login-Karte erscheint wieder; ``GET /api/projects``
        im Browser antwortet 403 (Session beendet).
        """
        self.boot()
        self.open_settings()
        self.page.locator("[data-nv-action='logout']").click()
        self.page.locator("[data-nv-login]").wait_for(
            state="visible", timeout=20000)
        status = self.page.evaluate(
            """async () => {
              const response = await fetch('/api/projects',
                {credentials: 'same-origin'});
              return response.status;
            }""")
        self.assertEqual(403, status,
                         "Nach dem Abmelden ist die API weiterhin erreichbar")


if __name__ == "__main__":
    unittest.main()
