"""Startseite: Projekte anheften und suchen sowie Agentenübersicht.

Aufruf: python3 -m unittest tests.browser.test_home_ui -v
"""


# ===========================================================================
# Browserabnahme: Startseite (Projektkarten, Anlage, Klonen, Ordner)
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
        # F33 WP1/2b: die Projektliste ist jetzt section[data-nv-projects]
        # (oberhalb liegen Anpinnen-Sektion, Suche und Trefferzahl).
        self.page.locator("section[data-nv-projects]").wait_for(
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

        self.page.locator("nav[data-nv-navs] [data-nv-nav='home']").click()
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

        self.page.locator("nav[data-nv-navs] [data-nv-nav='settings']").click()
        self.page.locator(
            "main#nv-main[data-nv-view='settings']").wait_for(
                state="visible", timeout=20000)
        toggle = self.page.locator("input[data-nv-feature='github']")
        toggle.wait_for(state="visible", timeout=15000)
        toggle.check()
        self.page.locator("nav[data-nv-navs] [data-nv-nav='home']").click()
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


# ===========================================================================
# Browserabnahme: Startseite (Projekte) und Agenten
# ===========================================================================

import http.client
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

if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402


PROJECTS = (
    ("alpha-projekt", "Alpha Testpaket"),
    ("beta-projekt", "Beta Testpaket"),
    ("gamma", "Gamma Testpaket"),
    ("delta", "Delta Testpaket"),
    ("epsilon", "Epsilon Testpaket"),
)

FAKE_OPENCODE = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf 'opencode v2.1.4\\n'
    exit 0
    ;;
  models)
    printf 'opencode/vibe-modell\\nopencode/test-modell\\nopencode/schnell-modell\\n'
    exit 0
    ;;
esac
exit 2
"""

GLOBAL_AGENT = """---
description: Globaler Agent
mode: subagent
model: opencode/vibe-modell
permission:
  read: allow
  edit: deny
---

Globaler Prompt.
"""

SECOND_AGENT = """---
description: Zweiter Agent
mode: subagent
model: opencode/test-modell
permission:
  read: allow
  edit: deny
---

Zweiter Prompt.
"""

BROKEN_AGENT = """---
description: Defekter Agent
mode: quatsch
---

Defekter Prompt.
"""


class F34HomeAgentsTest(unittest.TestCase):
    """Dashboard, Browser, opencode-Attrappe, isolierter VIBE-Root (WP2)."""

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
            (template / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
        (toolchain / "templates" / "common").mkdir()
        agents_dir = cls.root / "home" / ".config" / "opencode" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "tester.md").write_text(GLOBAL_AGENT, encoding="utf-8")
        (agents_dir / "zweiter.md").write_text(SECOND_AGENT, encoding="utf-8")
        (agents_dir / "defekt.md").write_text(BROKEN_AGENT, encoding="utf-8")
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir(parents=True)
        password = cls.log_dir / "opencode.password"
        password.write_text("geheim-F34-wp2", encoding="utf-8")
        password.chmod(0o600)
        cls.port = free_port()
        cls.oc_port = free_port()
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), _FakeOpenCodeHandler)
        cls._fake_http.daemon_threads = True
        cls._fake_thread = threading.Thread(
            target=cls._fake_http.serve_forever)
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
                    "vibe-web wurde vorzeitig beendet: " +
                    (cls.root / "web-server.log").read_text(
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
        # GH-117: angeheftete Projekte/Agenten und weitere Einstellungen
        # werden jetzt im State-Verzeichnis gespeichert. Ohne Zurücksetzen
        # übernimmt der nächste Fall den Pin eines vorherigen Falls. Das
        # frische Browserprofil hat bereits leeren localStorage.
        (self.state_dir / "settings.json").unlink(missing_ok=True)
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

    def wait_until(self, predicate, timeout=20, message="Bedingung nicht erfüllt"):
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

    def post_json(self, path, payload):
        body = json.dumps(payload).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", path, body=body, headers={
                "Host": f"127.0.0.1:{self.port}", "X-Token": self.token,
                "Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, json.loads(
                response.read().decode("utf-8", "replace") or "{}")
        finally:
            conn.close()

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_agents(self):
        self.boot()
        self.page.goto(self.base + "/#/agents")
        self.page.locator("main#nv-main[data-nv-view='agents']").wait_for(
            state="visible", timeout=25000)
        self.page.locator("[data-nv-agent-list]").wait_for(
            state="visible", timeout=20000)

    def card(self, name):
        return self.page.locator(f"article[data-nv-project='{name}']")

    def agent_card(self, name, scope="global"):
        return self.page.locator(
            f"article[data-nv-agent='{name}'][data-nv-agent-scope='{scope}']")

    def local_storage_json(self, key):
        raw = self.page.evaluate(
            "key => window.localStorage.getItem(key)", key)
        if raw is None:
            return None
        return json.loads(raw)

    def assert_no_page_errors(self):
        self.assertEqual(
            [], self.page_errors, "Die Oberfläche erzeugte JavaScript-Fehler")


class HomePinnedProjectsTest(F34HomeAgentsTest):
    def test_pinned_projects_render_in_grid_and_not_in_normal_list(self):
        """Vorbedingung: fünf Projekte, nichts angeheftet.

        Aktion: Anpinn-Knopf von ``alpha-projekt`` und ``beta-projekt``.

        Erwartung: ``section[data-nv-pinned-projects]`` enthält ein
        ``div[data-nv-pinned-grid]`` mit beiden Karten; die Karten fehlen in
        der normalen Liste ``section[data-nv-projects]``.
        """
        self.boot()
        self.page.locator("section[data-nv-projects]").wait_for(
            state="visible", timeout=20000)
        self.pin_project("alpha-projekt")
        self.wait_until(
            lambda: self.page.locator(
                "section[data-nv-pinned-projects] "
                "article[data-nv-project='alpha-projekt']").count() == 1)
        self.pin_project("beta-projekt")
        self.wait_until(
            lambda: self.page.locator(
                "section[data-nv-pinned-projects] "
                "article[data-nv-project='beta-projekt']").count() == 1)
        pinned = self.page.locator("section[data-nv-pinned-projects]")
        pinned.wait_for(state="visible", timeout=10000)
        grid = pinned.locator("div[data-nv-pinned-grid]")
        self.assertEqual(
            1, grid.count(),
            "section[data-nv-pinned-projects] enthält kein div[data-nv-pinned-grid]")
        self.assertEqual(
            2, pinned.locator("article[data-nv-project]").count(),
            "Das Pin-Raster enthält nicht beide angehefteten Karten")
        self.assertEqual(
            0, self.page.locator(
                "section[data-nv-projects] "
                "article[data-nv-project='alpha-projekt']").count(),
            "Die angeheftete Karte fehlt nicht aus der normalen Liste")
        self.assert_no_page_errors()

    def test_two_pinned_cards_side_by_side_at_1400px(self):
        """Vorbedingung: fünf Projekte, nichts angeheftet.

        Aktion: Anpinn-Knopf von ``alpha-projekt`` und ``beta-projekt``.

        Erwartung: die beiden Karten im Pin-Raster stehen nebeneinander (bei
        1400 px Viewport: gleiche y-Position, unterschiedliche x) und nicht
        untereinander.
        """
        self.boot()
        self.page.locator("section[data-nv-projects]").wait_for(
            state="visible", timeout=20000)
        self.pin_project("alpha-projekt")
        self.wait_until(
            lambda: self.page.locator(
                "section[data-nv-pinned-projects] "
                "article[data-nv-project='alpha-projekt']").count() == 1)
        self.pin_project("beta-projekt")
        self.wait_until(
            lambda: self.page.locator(
                "section[data-nv-pinned-projects] "
                "article[data-nv-project='beta-projekt']").count() == 1)
        pinned = self.page.locator("section[data-nv-pinned-projects]")
        grid = pinned.locator("div[data-nv-pinned-grid]")
        grid.wait_for(state="visible", timeout=10000)
        cards = grid.locator("article[data-nv-project]")
        self.assertEqual(
            2, cards.count(),
            "Das Pin-Raster enthält nicht zwei Karten")
        box_low = cards.nth(0).bounding_box()
        box_high = cards.nth(1).bounding_box()
        self.assertIsNotNone(box_low, "Die erste Karte hat keine Position")
        self.assertIsNotNone(box_high, "Die zweite Karte hat keine Position")
        self.assertEqual(
            box_low["y"], box_high["y"],
            "Die angehefteten Karten stehen nicht nebeneinander "
            f"(y={box_low['y']} vs. {box_high['y']})")
        self.assertNotEqual(
            box_low["x"], box_high["x"],
            "Die angehefteten Karten liegen untereinander statt nebeneinander")
        self.assert_no_page_errors()

    def test_pinned_grid_gap_and_action_row_gaps(self):
        """Vorbedingung: ein Projekt ist angeheftet.

        Aktion: Anpinnen eines Projekts.

        Erwartung: Das Kartenraster des Pins hat ein einheitliches Gap von
        ≥ 12 px (gemessen); innerhalb der Karte bleiben Aktionszeilen mit
        Abstand ≥ 8 px.
        """
        self.boot()
        self.page.locator("section[data-nv-projects]").wait_for(
            state="visible", timeout=20000)
        self.pin_project("alpha-projekt")
        self.wait_until(
            lambda: self.page.locator(
                "section[data-nv-pinned-projects] "
                "article[data-nv-project='alpha-projekt']").count() == 1)
        pinned = self.page.locator("section[data-nv-pinned-projects]")
        grid = pinned.locator("div[data-nv-pinned-grid]")
        grid.wait_for(state="visible", timeout=10000)
        gap = grid.first.evaluate(
            "node => parseFloat(getComputedStyle(node).gap) || 0")
        self.assertGreaterEqual(
            gap, 12, "Das Kartenraster hat kein Gap von mindestens 12 px: " + str(gap))
        card = self.card("alpha-projekt")
        rows = card.locator("div.nv-row")
        if rows.count() > 1:
            box_low = rows.nth(0).bounding_box()
            box_high = rows.nth(1).bounding_box()
            row_gap = box_high["y"] - (box_low["y"] + box_low["height"])
            self.assertGreaterEqual(
                row_gap, 8, "Die Aktionszeilen innerhalb der Karte sind zu eng: "
                + str(row_gap))
        self.assert_no_page_errors()

    def pin_project(self, name):
        card = self.page.locator(f"article[data-nv-project='{name}']")
        card.wait_for(state="visible", timeout=20000)
        pin = card.locator("[data-nv-action='project-pin']")
        pin.wait_for(state="visible", timeout=20000)
        pin.first.click()


class HomeProjectSearchTest(F34HomeAgentsTest):
    def test_nv_search_contract_live_count_and_clear(self):
        """Vorbedingung: Startseite mit fünf Projekten.

        Aktion: ``NV.search``-Leerzustand prüfen, Eingabe „alpha“
        eingeben, Zähler ablesen, Clear-Button betätigen.

        Erwartung: ``div[data-nv-search][data-nv-search]`` mit
        ``input[type=search][data-nv-search-input]`` und
        ``button[data-nv-search-clear]``; ``p[data-nv-search-count]`` nennt die
        Trefferzahl live („1 von 5“); Clear leert Eingabe und Zähler.
        """
        self.boot()
        search = self.page.locator("div[data-nv-search][data-nv-search]")
        search.wait_for(state="visible", timeout=20000)
        search_input = self.page.locator("input[data-nv-search-input]")
        search_input.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            "search", search_input.get_attribute("type"),
            "Die Suchleiste ist nicht als type=search ausgebildet")
        clear = self.page.locator("button[data-nv-search-clear]")
        count = self.page.locator("p[data-nv-search-count]")
        count.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            1, count.count(), "Die Trefferzahl p[data-nv-search-count] fehlt")

        search_input.fill("alpha")
        self.wait_until(
            lambda: clear.is_visible(),
            timeout=10,
            message="Der Clear-Knopf wird ohne Eingabe nicht angezeigt")
        self.wait_until(
            lambda: (count.inner_text() or "").strip().endswith("1"),
            timeout=10,
            message="Die Trefferzahl aktualisiert sich nicht live")
        self.wait_until(
            lambda: search_input.input_value() == "alpha",
            timeout=5,
            message="Die Suche hält den Wert nicht")

        clear.first.click()
        self.wait_until(
            lambda: search_input.input_value() == "",
            timeout=10,
            message="Der Clear-Knopf leert die Suche nicht")
        self.wait_until(
            lambda: (count.inner_text() or "").strip().endswith("5"),
            timeout=10,
            message="Die Trefferzahl nach Clear nicht wiederhergestellt")
        self.assert_no_page_errors()


class HomeProjectPinTest(F34HomeAgentsTest):
    def test_project_pin_sets_aria_pressed_and_persists(self):
        """Vorbedingung: Startseite, ``alpha-projekt`` vorhanden.

        Aktion: Anpinn-Knopf klicken, dann erneut.

        Erwartung: ``button[data-nv-action="project-pin"]`` setzt
        ``aria-pressed`` (false → true) und zeigt das Symbol ★/☆; der Name
        persistiert in ``localStorage['nv-pinned-projects']``; erneuter Klick
        hebt das Anheften wieder auf.
        """
        self.boot()
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
        symbol = (pin.first.inner_text() or "").strip()
        self.assertIn(
            symbol, ("★", "☆"),
            "Der Anpinn-Knopf zeigt kein ★/☆-Symbol: " + repr(symbol))
        stored = self.local_storage_json("nv-pinned-projects")
        self.assertIsInstance(stored, list, "nv-pinned-projects ist kein Array")
        self.assertIn("alpha-projekt", stored,
                      "nv-pinned-projects enthält den Namen nicht: " + repr(stored))
        pin.first.click()
        self.wait_until(
            lambda: pin.first.get_attribute("aria-pressed") == "false",
            timeout=10,
            message="Der erneute Klick hebt das Anheften nicht auf")
        self.assertEqual(
            [], self.local_storage_json("nv-pinned-projects") or [],
            "nv-pinned-projects ist nach dem Aufheben nicht leer")
        self.assert_no_page_errors()


class AgentenHeaderTest(F34HomeAgentsTest):
    def test_agent_head_has_search_and_new_agent_button(self):
        """Vorbedingung: angemeldet, Agenten-Ansicht.

        Aktion: Kopf der Agenten-Ansicht prüfen.

        Erwartung: Suchleiste ``div[data-nv-agent-search]`` mit
        ``input[data-nv-search-input]`` und „Neuer Agent“-Knopf in
        ``div.nv-toolbar``.
        """
        self.open_agents()
        toolbar = self.page.locator("div.nv-toolbar")
        toolbar.wait_for(state="visible", timeout=20000)
        new_button = toolbar.locator("[data-nv-action='agent-new']")
        self.assertEqual(
            1, new_button.count(),
            "Die Agenten-Ansicht bietet keinen „Neuer Agent“-Knopf in "
            "div.nv-toolbar")
        self.assertTrue(
            new_button.first.is_visible(),
            "Der „Neuer Agent“-Knopf in div.nv-toolbar ist nicht sichtbar")
        search = self.page.locator(
            "div[data-nv-agent-search] input[data-nv-search-input]")
        search.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            1, self.page.locator("div[data-nv-agent-search]").count(),
            "Der Agenten-Kopf trägt nicht div[data-nv-agent-search]")


class AgentenTagFilterTest(F34HomeAgentsTest):
    def test_tag_filters_above_list_and_combine_with_search(self):
        """Vorbedingung: Agenten mit globalen und projektgebundenen Karten.

        Aktion: Tag-Filter messen und mit Suchlauf kombinieren.

        Erwartung: ``div[data-nv-agent-tag-filters]`` steht über der
        Agentenliste (y kleiner als die erste Karte) und direkt unter der
        Suche; Suche und Tag-Filter kombinieren sich (UND) — ein Agent, der nur
        einen der beiden Treffer erfüllt, bleibt ausgeblendet.
        """
        self.open_agents()
        filters = self.page.locator("div[data-nv-agent-tag-filters]")
        filters.wait_for(state="visible", timeout=20000)
        chips = filters.locator("button[data-nv-tag-filter]")
        self.assertGreaterEqual(
            chips.count(), 1,
            "Die Tag-Filter-Leiste enthält keine Umschalt-Chips")
        card = self.agent_card("tester", "global")
        card.wait_for(state="visible", timeout=20000)
        list_box = self.page.locator("[data-nv-agent-list]").bounding_box()
        filter_box = filters.bounding_box()
        self.assertIsNotNone(list_box, "Die Agentenliste hat keine Position")
        self.assertIsNotNone(filter_box, "Die Tag-Filter haben keine Position")
        self.assertLess(
            filter_box["y"], list_box["y"],
            "Der Tag-Filter steht nicht über der Agentenliste (y="
            + str(filter_box["y"]) + " > " + str(list_box["y"]) + ")")
        search_box = self.page.locator(
            "div[data-nv-agent-search] input[data-nv-search-input]"
        ).bounding_box()
        self.assertIsNotNone(
            search_box, "Die Agentensuche hat keine Position")
        self.assertGreaterEqual(
            filter_box["y"], search_box["y"] + search_box["height"] - 1,
            "Der Tag-Filter steht nicht direkt unter der Suche")

        global_filter = filters.locator(
            "button[data-nv-tag-filter]", has_text=re.compile("global", re.I))
        global_filter.first.click()
        self.wait_until(
            lambda: global_filter.first.get_attribute("aria-pressed") == "true",
            timeout=10,
            message="Der Tag-Filter setzt aria-pressed nicht auf true")
        search = self.page.locator(
            "div[data-nv-agent-search] input[data-nv-search-input]")
        search.fill("Zweiter")
        self.wait_until(
            lambda: not self.agent_card("tester", "global").is_visible(),
            timeout=10,
            message="Suche und Tag-Filter wurden nicht UND-verknüpft")
        self.assertTrue(
            self.agent_card("zweiter", "global").is_visible(),
            "Der Agent, der den Such- und Tag-Treffer erfüllt, blendet nicht ein")
        self.assert_no_page_errors()


class AgentenCardTest(F34HomeAgentsTest):
    def test_agent_card_two_line_and_pin_symbol_only(self):
        """Vorbedingung: globaler Agent ``tester``.

        Aktion: Karte messen, Pin-Knopf-Text prüfen.

        Erwartung: ``h3.nv-agent-name`` überlappt nicht mit Pin-Button und
        Badges (Bounding-Boxen schneiden sich nicht); der Pin-Button zeigt nur
        das Symbol ★/☆ (kein sichtbares Wort) und trägt das aria-label
        „Anpinnen“/„Lösen“.
        """
        self.open_agents()
        card = self.agent_card("tester", "global")
        card.wait_for(state="visible", timeout=20000)
        name = card.locator("h3.nv-agent-name")
        name.wait_for(state="visible", timeout=10000)
        pin = card.locator("[data-nv-action='agent-pin']")
        pin.wait_for(state="visible", timeout=10000)
        badge = card.locator("[data-nv-agent-scope-badge]")
        badge.wait_for(state="visible", timeout=10000)
        tags = card.locator("div[data-nv-agent-tags]")
        tags.wait_for(state="visible", timeout=10000)

        name_box = name.bounding_box()
        pin_box = pin.bounding_box()
        badge_box = badge.bounding_box()
        self.assertIsNotNone(name_box, "Der Agentenname hat keine Position")
        self.assertIsNotNone(pin_box, "Der Pin-Button hat keine Position")
        self.assertIsNotNone(badge_box, "Das Badge hat keine Position")
        self.assertFalse(
            self._boxes_overlap(name_box, pin_box),
            "h3.nv-agent-name überlappt mit dem Pin-Button")
        self.assertFalse(
            self._boxes_overlap(name_box, badge_box),
            "h3.nv-agent-name überlappt mit dem Badge")

        visible = (pin.inner_text() or "").strip()
        self.assertFalse(
            re.search(r"[A-Za-z]", visible),
            "Der Pin-Button enthält ein sichtbares Wort: " + repr(visible))
        self.assertIn(
            visible, ("★", "☆"),
            "Der Pin-Button zeigt kein Symbol ★/☆: " + repr(visible))
        label = (pin.get_attribute("aria-label") or "").strip()
        self.assertTrue(
            label, "Der Pin-Button trägt kein aria-label (Anpinnen/Lösen)")

        tags_box = tags.bounding_box()
        self.assertIsNotNone(tags_box, "Die Tag-Zeile hat keine Position")
        self.assertGreaterEqual(
            tags_box["y"], name_box["y"] + name_box["height"] - 1,
            "Die Tags überlappen die Namenszeile")

    def _boxes_overlap(self, first, second):
        if first["x"] >= second["x"] + second["width"]:
            return False
        if second["x"] >= first["x"] + first["width"]:
            return False
        if first["y"] >= second["y"] + second["height"]:
            return False
        if second["y"] >= first["y"] + first["height"]:
            return False
        return True

    def test_pinned_agent_moves_out_of_list(self):
        """Vorbedingung: globaler Agent ``tester``, nichts angeheftet.

        Aktion: Anpinn-Knopf der Karte ``tester`` klicken.

        Erwartung: ``section[data-nv-pinned-agents]`` enthält die Karte;
        die Karte verschwindet aus der normalen Liste
        (``[data-nv-agent-list]``).
        """
        self.open_agents()
        card = self.agent_card("tester", "global")
        card.wait_for(state="visible", timeout=20000)
        pin = card.locator("[data-nv-action='agent-pin']")
        pin.wait_for(state="visible", timeout=10000)
        self.assertNotEqual(
            "true", pin.first.get_attribute("aria-pressed"),
            "Die Karte ist ohne Zutun bereits angeheftet")
        pin.first.click()
        self.wait_until(
            lambda: pin.first.get_attribute("aria-pressed") == "true",
            timeout=10,
            message="Der Anpinn-Knopf setzt aria-pressed nicht auf true")
        pinned = self.page.locator("section[data-nv-pinned-agents]")
        pinned.wait_for(state="visible", timeout=10000)
        self.assertEqual(
            1, pinned.locator(
                "article[data-nv-agent='tester'][data-nv-agent-scope='global']").count(),
            "Die angeheftete Karte fehlt in section[data-nv-pinned-agents]")
        self.assertEqual(
            0, self.page.locator(
                "[data-nv-agent-list] "
                "article[data-nv-agent='tester'][data-nv-agent-scope='global']").count(),
            "Die angeheftete Karte bleibt in der normalen Liste")
        self.assert_no_page_errors()


if __name__ == "__main__":
    unittest.main()
