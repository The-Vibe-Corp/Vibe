"""Browserabnahme AP22: Startseite (Projektkarten, Anlage, Klonen, Ordner).

Die Fälle leiten sich aus ``docs/features/AP22.md`` („Startseite“) ab. Das
echte Dashboard läuft als eigener Prozess mit isoliertem VIBE-Root, zwei
registrierten Projekten und einer opencode-Attrappe
(``tests/browser/test_ap21_i18n_ui.py`` als Muster).

Der Vertrag definiert für einige Bedienelemente keinen eigenen Hook; die
Tests halten sich an folgende, dokumentierte Lesart:

* Typ-Badge: Der Kartentext nennt den Projekttyp (``TYPE`` aus
  ``.vibe/project.env``), hier ``generic`` (auch ``generisch`` akzeptiert).
* Lauf-Status-Pille ``[data-nv-run-state]``: Der Wert steht als Text oder als
  ``data-state``/``data-run-state``-Attribut und ist ``running`` oder
  ``stopped``.
* Öffnen: Es gibt keinen eigenen Hook für den Öffnen-Knopf; der Test klickt
  den ersten Projekt-Link/Knopf der Karte und fällt auf den Projektnamen
  zurück.
* Fehleranzeige für Klonen/Ordner: Der Vertrag erlaubt Toast
  (``#nv-toasts``) oder ``[data-nv-form-error]``; der Test akzeptiert beides.

Testfälle (Kurzfassung; Details in den Methoden)
------------------------------------------------
``ProjectGridTest.test_project_cards_show_name_type_state_and_open_count``
    Vorbedingung: Projekt ``proj`` registriert. Aktion: Startseite booten.
    Erwartung: ``div[data-nv-projects]`` mit ``article[data-nv-project]``,
    Name, Typ-Badge, Lauf-Status-Pille und offene-Pakete-Zahl.
``ProjectGridTest.test_clicking_a_project_opens_the_project_view``
    Aktion: Projektnamen in der Karte klicken. Erwartung: Route
    ``#/project/proj``, ``main[data-nv-view="project"]`` und
    ``h2[data-nv-project-title]`` mit dem Namen.
``GuideTest.test_guide_is_visible_then_dismissed_persistently``
    Vorbedingung: frisches Profil. Aktion: Schließen klicken, neu laden.
    Erwartung: ``[data-nv-guide]`` sichtbar → unsichtbar → nach Reload
    unsichtbar, ``nv-guide-dismissed`` gespeichert.
``NewProjectTest.test_types_and_create_project_navigates_to_assistant``
    Aktion: Typ-Select prüfen, Projekt mit eindeutigem Namen anlegen.
    Erwartung: ``generic`` ist eine Option (mindestens zwei Typen), die
    Karte erscheint in der Übersicht und die Ansicht wechselt in den
    Assistenten (``data-nv-ppanel="assistant"``).
``CloneFeatureTest.test_clone_card_needs_github_feature_and_shows_error``
    Aktion: Startseite ohne Feature, dann Feature ``github`` einschalten,
    ungültige URL absenden. Erwartung: Karte zunächst nicht sichtbar, dann
    mit ``input[data-nv-field="url"]`` und ``[data-nv-action="clone"]``;
    Fehler sichtbar (Toast oder Formularfehler), kein Absturz.
``RootsTest.test_roots_card_and_garbage_path_error``
    Aktion: Ordner hinzufügen mit ungültigem Pfad. Erwartung:
    ``[data-nv-roots]`` mit Zeilen, Eingabe und Knöpfen ``root-add``/
    ``root-scan``; die Backend-Meldung erscheint als sichtbarer Fehler, ohne
    JS-Fehler.
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


class AP22HomeTest(unittest.TestCase):
    """Dashboard, zwei Projekte, Vorlagen, Browser, opencode-Attrappe."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.projects = {}
        for name, feeder in (("proj", "AP22 Testpaket"), ("zweit", "Zweites Paket")):
            folder = cls.root / name
            (folder / ".vibe").mkdir(parents=True)
            (folder / ".vibe" / "project.env").write_text(
                "TYPE=generic\n", encoding="utf-8")
            (folder / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
            (folder / "TICKETS.md").write_text(
                "# TICKETS — Test\n\n- [ ] " + feeder +
                "\n  Beschreibung: Offenes Paket\n", encoding="utf-8")
            cls.projects[name] = folder
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
        password.write_text("geheim-AP22-home", encoding="utf-8")
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
        body = json.dumps({"language": "en"}).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", "/api/language", body=body, headers={
                "Host": f"127.0.0.1:{self.port}", "X-Token": self.token,
                "Content-Type": "application/json"})
            conn.getresponse().read()
        finally:
            conn.close()
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

    def card(self, name):
        return self.page.locator(f"article[data-nv-project='{name}']")

    def open_project_card(self, name):
        """Öffnet eine Projektkarte über ihren Öffnen-Knopf.

        Der Vertrag nennt keinen Hook für den Öffnen-Knopf; der Test nimmt
        den ersten Projekt-Link/Knopf der Karte und fällt auf den
        Projektnamen zurück.
        """
        card = self.card(name)
        card.wait_for(state="visible", timeout=20000)
        for selector in ("a[href*='#/project/']",
                         "[data-nv-action='open']",
                         "[data-nv-action='project-open']",
                         "button"):
            candidates = card.locator(selector)
            if candidates.count():
                candidates.first.click()
                return
        card.get_by_text(name, exact=True).first.click()

    def run_state_text(self, card):
        pill = card.locator("[data-nv-run-state]")
        self.assertEqual(1, pill.count(), "Lauf-Status-Pille fehlt in der Karte")
        text = (pill.inner_text() or "").strip().lower()
        if text in ("running", "stopped"):
            return text
        for attribute in ("data-state", "data-run-state", "aria-label"):
            value = (pill.get_attribute(attribute) or "").strip().lower()
            if value in ("running", "stopped"):
                return value
        return text

    def visible_error_text(self):
        """Sichtbarer Fehlertext aus Toast oder Formularfehler (Vertrag erlaubt beides)."""
        parts = []
        for selector in ("#nv-toasts", "[data-nv-form-error]",
                         "[data-nv-clone] [data-nv-form-error]",
                         "[data-nv-roots] [data-nv-form-error]"):
            nodes = self.page.locator(selector)
            for index in range(nodes.count()):
                node = nodes.nth(index)
                if node.is_visible():
                    parts.append((node.inner_text() or "").strip())
        return "\n".join(parts)

    def assert_no_page_errors(self):
        self.assertEqual(
            [], self.page_errors, "Die Oberfläche erzeugte JavaScript-Fehler")

    # ---------- Fälle ----------

    def test_project_cards_show_name_type_state_and_open_count(self):
        """Vorbedingung: Projekte ``proj`` und ``zweit`` registriert.

        Aktion: Startseite booten.
        Erwartung: ``div[data-nv-projects]`` sichtbar; je Projekt eine Karte
        ``article[data-nv-project]`` mit Namen, Typ-Badge (``generic``),
        Lauf-Status-Pille (``running``/``stopped``) und Zahl der offenen
        Pakete.
        """
        self.boot()
        self.page.locator("div[data-nv-projects]").wait_for(
            state="visible", timeout=20000)
        for name in ("proj", "zweit"):
            with self.subTest(project=name):
                card = self.card(name)
                card.wait_for(state="visible", timeout=20000)
                text = card.inner_text()
                self.assertIn(name, text,
                              "Die Karte nennt den Projektnamen nicht")
                self.assertTrue(
                    "generic" in text.lower() or "generisch" in text.lower(),
                    "Die Karte zeigt kein Typ-Badge für 'generic': " + repr(text))
                self.assertIn(
                    self.run_state_text(card), ("running", "stopped"),
                    "Die Lauf-Status-Pille hat keinen gültigen Wert")
                open_count = card.locator("[data-nv-open-count]")
                self.assertEqual(
                    1, open_count.count(),
                    "Die Zahl der offenen Pakete fehlt in der Karte")
                self.assertTrue(
                    any(char.isdigit()
                        for char in (open_count.inner_text() or "")),
                    "Die offene-Pakete-Zahl enthält keine Zahl")

    def test_clicking_a_project_opens_the_project_view(self):
        """Vorbedingung: Startseite. Aktion: Projektnamen in der Karte klicken.

        Erwartung: Route ``#/project/proj``; ``main[data-nv-view="project"]``
        sichtbar; ``h2[data-nv-project-title]`` nennt ``proj``.
        """
        self.boot()
        self.open_project_card("proj")
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        self.assertIn(
            "#/project/proj", self.page.url,
            "Die Route der Projektansicht ist nicht #/project/proj")
        title = self.page.locator("h2[data-nv-project-title]")
        title.wait_for(state="visible", timeout=15000)
        self.assertEqual("proj", title.inner_text().strip(),
                         "Der Projekttitel nennt nicht den Projektnamen")
        self.assert_no_page_errors()

    def test_guide_is_visible_then_dismissed_persistently(self):
        """Vorbedingung: frisches Profil. Aktion: Hinweis schließen, neu laden.

        Erwartung: ``[data-nv-guide]`` sichtbar; nach Klick auf
        ``[data-nv-guide-dismiss]`` unsichtbar; nach Reload weiterhin
        unsichtbar, ``nv-guide-dismissed`` liegt im localStorage.
        """
        self.boot()
        guide = self.page.locator("[data-nv-guide]")
        guide.wait_for(state="visible", timeout=20000)
        self.page.locator("[data-nv-guide-dismiss]").click()
        self.wait_until(
            lambda: not guide.is_visible(),
            timeout=10000,
            message="Der Einstiegshinweis ließ sich nicht schließen")
        self.assertIsNotNone(
            self.page.evaluate("() => localStorage.getItem('nv-guide-dismissed')"),
            "nv-guide-dismissed wurde nicht gespeichert")

        self.page.reload()
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)
        self.assertFalse(
            self.page.locator("[data-nv-guide]").is_visible(),
            "Der Einstiegshinweis erscheint nach dem Reload wieder")

    def test_types_and_create_project_navigates_to_assistant(self):
        """Vorbedingung: Vorlagen ``generic`` und ``web`` installiert.

        Aktion: Typ-Select lesen; Projekt ``neu-ap22`` anlegen; zurück zur
        Übersicht.
        Erwartung: ``generic`` ist eine Option, mindestens zwei Typen; nach
        dem Anlegen steht die Ansicht im Assistenten
        (``data-nv-ppanel="assistant"``) und die Karte erscheint in der
        Projektübersicht.
        """
        self.boot()
        select = self.page.locator(
            "[data-nv-new-project] select[data-nv-field='type']")
        select.wait_for(state="visible", timeout=20000)
        options = select.evaluate(
            "node => Array.from(node.options).map(o => [o.value, "
            "o.textContent.trim()])")
        values = [value for value, _text in options]
        self.assertIn("generic", values,
                      "Der Typ-Select bietet nicht den Typ generic an: "
                      + repr(options))
        self.assertGreaterEqual(
            len(values), 2,
            "Der Typ-Select bietet weniger als zwei Typen an: " + repr(options))

        self.page.locator(
            "[data-nv-new-project] input[data-nv-field='name']").fill("neu-ap22")
        self.page.locator(
            "[data-nv-new-project] [data-nv-action='create-project']").click()

        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=30000)
        self.page.locator(
            "section[data-nv-ppanel='assistant']").wait_for(
                state="visible", timeout=20000)

        self.page.locator("[data-nv-nav='home']").click()
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)
        self.card("neu-ap22").wait_for(state="visible", timeout=20000)
        self.assert_no_page_errors()

    def test_clone_card_needs_github_feature_and_shows_error(self):
        """Vorbedingung: frisches Profil, Feature ``github`` aus.

        Aktion: Startseite lesen; Feature ``github`` in den Einstellungen
        einschalten; zurück zur Startseite; ungültige URL absenden.
        Erwartung: Ohne Feature fehlt ``[data-nv-clone]``; mit Feature ist
        die Karte samt ``input[data-nv-field="url"]`` und
        ``[data-nv-action="clone"]`` da; die ungültige URL erzeugt einen
        sichtbaren Fehler ohne JS-Absturz.
        """
        self.boot()
        clone = self.page.locator("[data-nv-clone]")
        self.assertFalse(
            clone.is_visible() if clone.count() else False,
            "Die Clone-Karte ist ohne Feature github sichtbar")

        self.page.locator("[data-nv-nav='settings']").click()
        self.page.locator(
            "main#nv-main[data-nv-view='settings']").wait_for(
                state="visible", timeout=20000)
        toggle = self.page.locator("input[data-nv-feature='github']")
        toggle.wait_for(state="visible", timeout=15000)
        toggle.check()
        self.page.locator("[data-nv-nav='home']").click()
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

        clone = self.page.locator("[data-nv-clone]")
        clone.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            1, clone.locator("input[data-nv-field='url']").count(),
            "Der Clone-Karte fehlt das URL-Feld")
        self.assertEqual(
            1, clone.locator("[data-nv-action='clone']").count(),
            "Der Clone-Karte fehlt der Clone-Knopf")

        clone.locator("input[data-nv-field='url']").fill(
            "kein-gueltiges-remote-ap22")
        clone.locator("[data-nv-action='clone']").click()
        self.wait_until(
            lambda: self.visible_error_text() != "",
            timeout=25000,
            message="Die ungültige Clone-URL erzeugte keinen sichtbaren Fehler")
        self.assert_no_page_errors()

    def test_roots_card_and_garbage_path_error(self):
        """Vorbedingung: frisches Profil. Aktion: ungültigen Ordner hinzufügen.

        Erwartung: ``[data-nv-roots]`` mit Zeilen ``[data-nv-root]``, Eingabe
        ``input[data-nv-field="root"]`` und den Knöpfen ``root-add`` /
        ``root-scan``; die Backend-Meldung („existiert nicht“ bzw. der Pfad)
        erscheint als sichtbarer Fehler, ohne JS-Fehler.
        """
        self.boot()
        roots = self.page.locator("[data-nv-roots]")
        roots.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(
            self.page.locator("[data-nv-root]").count(), 1,
            "Die Ordnerliste zeigt keine Zeile [data-nv-root]")
        field = roots.locator("input[data-nv-field='root']")
        self.assertEqual(1, field.count(),
                         "Der Ordnerkarte fehlt das Eingabefeld")
        self.assertEqual(
            1, roots.locator("[data-nv-action='root-add']").count(),
            "Der Ordnerkarte fehlt der Hinzufügen-Knopf")
        self.assertEqual(
            1, roots.locator("[data-nv-action='root-scan']").count(),
            "Der Ordnerkarte fehlt der Neu-einlesen-Knopf")

        garbage = "/kein/ordner-ap22"
        field.fill(garbage)
        roots.locator("[data-nv-action='root-add']").click()
        self.wait_until(
            lambda: self.visible_error_text() != "",
            timeout=25000,
            message="Der ungültige Ordnerpfad erzeugte keinen sichtbaren Fehler")
        self.assertTrue(
            garbage in self.visible_error_text()
            or "existiert" in self.visible_error_text(),
            "Der sichtbare Fehler nennt nicht die Backend-Meldung: "
            + repr(self.visible_error_text()))
        self.assert_no_page_errors()


if __name__ == "__main__":
    unittest.main()
