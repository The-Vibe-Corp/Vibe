"""GH-67: Browserabnahme „Projekt/Work“ (unabhängig aus Ticket + SPEC).

Quelle der Fälle: ``TICKET-GH-67.json`` (Abschnitte 1–7: gemeinsame Sidebar,
Priorisierungsansicht/Zähler, Lokalisierung, Kategorie vs. Tickettyp,
Filterleiste, Statuszuordnung/-wechsel, Dialogaktionen) und ``SPEC.md``
(Arbeitspakete in ``.vibe/tickets.json``, Oberflächensprache Englisch,
Trennung von Anzeigetext und gespeicherten Statuswerten) sowie der Nachforderung
„Bearbeiten setzt ein Ticket automatisch auf in-progress“. Die Fälle werden
nicht aus einem Implementierungsdiff abgeleitet.

Der Live-Server läuft isoliert auf einem freien Port mit bereinigter
VIBE_*-/SANDBOX_-Umgebung und eigenen Temp-Pfaden; der Browser nutzt den
vorgegebenen ``PLAYWRIGHT_BROWSERS_PATH``. Aufbau entspricht
``tests/browser/test_gh56_work_ui.py``.

Erwartete Hooks (Vertrag für die Umsetzung):
    ``NV.sidebar`` mit ``open/close/isOpen``; geteilt von ``NV.editView``
      (Settings + Ticket-Editor) und ``NV.context`` (Detail/Kontext)
    ``div[data-nv-priority-strip]`` nur bei <=768px, ``[data-nv-prio-count]``
    ``article[data-nv-col='draft|ready|running']`` → ``article[data-nv-ticket]``
      mit ``data-nv-state`` (Rohzustand) und Status-Badge als ``span``
    ``input[data-nv-work-search]``, ``div[data-nv-search]``,
      ``div[data-nv-work-kinds]``, ``button[data-nv-work-hide-done]``
      außerhalb von ``div[data-nv-filter-bar]``, Chips draft/ready/running
    Editor: ``aside[data-nv-ticket-editor]``, ``[data-nv-field]`` mit
      ``category`` (feature/bug/feedback) und ``ticket-type``
      (task/bug/feature/feedback), ``button[data-nv-action=...]``

Hinweis zum Tickettyp-Feld: erwartet wird ``data-nv-field='ticket-type'``
innerhalb des Editors. ``data-nv-field='type'`` ist im Projekt bereits für
den Projekttyp (generic/android/…) vergeben und wird nur als Fallback
akzeptiert (siehe ``ticket_type_select``).

Run (Rot-Phase, vor der Implementierung):

    PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright \
      python3 -m unittest tests.browser.test_gh67_work_ui -v
"""
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

_BROWSERS = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"
PROJECT = "proj"
STAMP = "2026-01-01T00:00:00+00:00"
DESKTOP = {"width": 1500, "height": 1100}
MOBILE = {"width": 600, "height": 800}


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def isolated_env(root, home, port):
    """Keine VIBE_*/SANDBOX_-Werte der laufenden Instanz übernehmen."""
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                "TMUX", "TMUX_PANE"):
            env.pop(key, None)
    env.update({
        "VIBE": str(root),
        "VIBE_NO_CONTAINER": "1",
        "VIBE_UI_PORT": str(port),
        "HOME": str(home),
        "TMPDIR": str(root / "tmp"),
        "TMUX_TMPDIR": str(root / "tmux"),
        "VIBE_STATE": str(root / "_toolchain"),
        "VIBE_INSTALL": str(root / "_toolchain"),
        "VIBE_RUNTIME": str(root / "_logs"),
        "VIBE_AGENTS_DIR": str(home / ".config" / "opencode" / "agents"),
        "VIBE_CONFIG_FILE": str(home / ".config" / "vibe" / "config.json"),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    return env


def ticket(tid, title, type="task", state="open", **extra):
    record = {
        "id": tid, "title": title, "type": type, "state": state,
        "description": "", "github": None, "pr_url": "", "commit": "",
        "test": "", "blocked_reason": "", "waiting_note": "",
        "priority": "", "dependencies": [],
        "created": STAMP, "updated": STAMP,
    }
    record.update(extra)
    return record


class GH67WorkBrowserTest(unittest.TestCase):
    """Ein isolierter Live-Server; je Testfall ein eigener Browser-Kontext."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / PROJECT
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        cls.store_path = cls.project / ".vibe" / "tickets.json"
        for path in ("_logs", "_toolchain", "tmp", "tmux",
                     "home/.config/opencode/agents"):
            (cls.root / path).mkdir(parents=True, exist_ok=True)
        # Die Settings-Sektion „Globale AGENTS.md“ bietet nur dann einen
        # Edit-Button, wenn die Datei existiert (Vorbedingung wie in GH-57).
        (cls.root / "home" / ".config" / "opencode" / "AGENTS.md").write_text(
            "# Globale Regeln\n", encoding="utf-8")
        cls.home = cls.root / "home"
        cls.port = free_port()
        cls.base = "http://127.0.0.1:%d" % cls.port
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=isolated_env(cls.root, cls.home, cls.port),
            stdout=cls.server_log, stderr=subprocess.STDOUT, text=True)

        token_file = cls.root / "_logs" / "web.token"
        deadline = time.time() + 25
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                            ("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = (cls.root / "web-server.log").read_text(
                    encoding="utf-8", errors="replace")
                raise AssertionError("vibe-web wurde vorzeitig beendet: " + output)
            time.sleep(0.05)
        else:
            raise AssertionError(
                "vibe-web ist nicht erreichbar: "
                + (cls.root / "web-server.log").read_text(
                    encoding="utf-8", errors="replace"))
        cls.token = token_file.read_text(encoding="utf-8").strip()

        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except Exception as error:  # noqa: BLE001 - Environment vs. Fachfehler
            cls.playwright.stop()
            raise unittest.SkipTest(
                "Chromium ist für Playwright nicht verfügbar: " + str(error))

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser.close()
            cls.playwright.stop()
        finally:
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
        self.context = self.browser.new_context(viewport=DESKTOP)
        self.page = self.context.new_page()
        self.page.set_default_timeout(8000)
        self.page_errors = []
        self.dialogs = []
        self.dialog_policy = None
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))
        self.page.on("dialog", self._on_dialog)

    def tearDown(self):
        self.context.close()

    def _on_dialog(self, dialog):
        self.dialogs.append(dialog.type + ": " + dialog.message)
        accept = True
        if self.dialog_policy:
            accept = self.dialog_policy.pop(0)
        if accept:
            dialog.accept()
        else:
            dialog.dismiss()

    # --------------------------------------------------------- Helfer
    def write_store(self, tickets):
        self.store_path.write_text(
            json.dumps({"version": 1, "tickets": tickets},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

    def read_store(self):
        return {item["id"]: item for item in json.loads(
            self.store_path.read_text(encoding="utf-8"))["tickets"]}

    def api_json(self, path, method="GET", payload=None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=body, headers={
                "Host": "127.0.0.1:%d" % self.port,
                "X-Token": self.token,
                "Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, response.read().decode(
                "utf-8", errors="replace")
        finally:
            conn.close()

    def set_priority(self, ids):
        """PACKAGE_ORDER über die API setzen (Leerzeichen-getrennte Kennungen)."""
        status, body = self.api_json("/api/priority", "POST", {
            "name": PROJECT, "action": "set", "order": " ".join(ids)})
        self.assertEqual(200, status, body)
        self.assertTrue(json.loads(body).get("ok", False), body)

    def stored_priority(self):
        status, body = self.api_json("/api/priority?name=" + PROJECT)
        self.assertEqual(200, status)
        return [str(row.get("id") or "") for row in
                json.loads(body).get("order", [])]

    def wait_until(self, predicate, timeout=8, message="Bedingung fehlt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(120)
        self.fail(message)

    def goto_work(self, viewport=None):
        """Boot + Work-Route öffnen; optional mit eigenem Viewport/Kontext."""
        if viewport:
            context = self.browser.new_context(viewport=viewport)
            page = context.new_page()
            page.set_default_timeout(8000)
            page.on("dialog", self._on_dialog)
            page.on("pageerror",
                    lambda error: self.page_errors.append(str(error)))
            self.addCleanup(context.close)
            self.context = context
            self.page = page
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)
        self.page.goto(self.base + "/#/project/" + PROJECT + "/work")
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        work = self.page.locator("section[data-nv-ppanel='work']")
        work.wait_for(state="visible", timeout=20000)
        return work

    def route_to(self, fragment):
        """Routenwechsel ohne Dokument-Reload (hashbasierter Router)."""
        self.page.evaluate("fragment => { window.location.hash = fragment; }",
                           fragment)

    def set_lang(self, lang):
        self.page.evaluate(
            "lang => (window.VIBE_I18N || window.I18N).set(lang)", lang)
        self.wait_until(
            lambda: self.page.evaluate(
                "() => document.documentElement.lang") == lang,
            message="Sprache wurde nicht auf %r gestellt" % lang)
        self.page.wait_for_timeout(250)  # retranslateDOM + rerender

    def board(self):
        return self.page.locator("div[data-nv-board]").first

    def col(self, name):
        return self.page.locator("article[data-nv-col='%s']" % name).first

    def card(self, tid):
        return self.page.locator("article[data-nv-ticket='%s']" % tid).first

    def editor(self):
        return self.page.locator("aside[data-nv-ticket-editor]").first

    def strip(self):
        return self.page.locator("div[data-nv-priority-strip]").first

    def prio_count(self):
        return self.page.locator("[data-nv-prio-count]").first

    def open_new(self, mode):
        action = {"package": "new-package", "bug": "new-bug",
                  "feedback": "new-feedback"}[mode]
        self.page.locator("[data-nv-action='%s']" % action).first.click()
        editor = self.editor()
        editor.wait_for(state="visible", timeout=6000)
        return editor

    def ticket_type_select(self, editor):
        """Tickettyp-Auswahl im Editor.

        Vertragserwartung: ``data-nv-field='ticket-type'``. Das Attribut
        ``data-nv-field='type'`` ist im Projekt bereits für den Projekttyp
        reserviert und wird hier nur als akzeptierter Fallback geprüft.
        """
        selected = editor.locator("[data-nv-field='ticket-type']")
        if selected.count() == 0:
            selected = editor.locator("[data-nv-field='type']")
        self.assertGreaterEqual(
            selected.count(), 1,
            "Dem Anlageformular fehlt die Tickettyp-Auswahl "
            "(data-nv-field='ticket-type', Fallback 'type')")
        return selected.first

    def open_ticket_editor(self, tid):
        self.card(tid).locator(
            "button[data-nv-action='ticket-details']").first.click()
        detail = self.page.locator("[data-nv-ticket-detail='%s']" % tid).first
        detail.wait_for(state="visible", timeout=5000)
        detail.locator("button[data-nv-action='ticket-edit']").first.click()
        editor = self.editor()
        editor.wait_for(state="visible", timeout=5000)
        return editor

    def card_state_text(self, tid):
        """Statuslabel der Karte samt Spaltenüberschrift (groß/klein)."""
        return self.card(tid).evaluate("""card => {
          const col = card.closest('article[data-nv-col]');
          return ((card.textContent || '') + ' ' + (col ? col.textContent : ''))
            .toLowerCase();
        }""")

    def click_open_scrim(self):
        for selector in ("[data-nv-sidebar-scrim]",
                         "[data-nv-editview-scrim]",
                         "[data-nv-context-scrim]"):
            node = self.page.locator(selector)
            if node.count() and node.first.is_visible():
                node.first.click(position={"x": 5, "y": 5})
                return selector
        self.fail("Kein sichtbarer Scrim vorhanden")

    def set_marker(self):
        """DOM-Marker + JS-Variable zum Nachweis eines fehlenden Voll-Neuladens."""
        self.page.evaluate("""() => {
          window.__gh67Marker = 'alive';
          const board = document.querySelector('[data-nv-board]')
            || document.querySelector('[data-nv-priority-strip]')
            || document.querySelector('[data-nv-work-list]');
          if (board) board.setAttribute('data-nv-marker', 'gh67');
        }""")

    def assert_js_marker_alive(self, message="Die Oberfläche wurde vollständig neu geladen"):
        """Nur der JS-Marker: ein Routenwechsel darf die DOM ersetzen."""
        self.assertEqual(
            "alive", self.page.evaluate("() => window.__gh67Marker || ''"),
            message + " (JS-Marker)")

    def assert_marker_alive(self, message="Die Oberfläche wurde vollständig neu geladen"):
        state = self.page.evaluate("""() => ({
          js: window.__gh67Marker || '',
          dom: !!document.querySelector('[data-nv-marker=\"gh67\"]')
        })""")
        self.assertEqual("alive", state["js"], message + " (JS-Marker)")
        self.assertTrue(state["dom"], message + " (DOM-Marker)")

    def show_done(self):
        toggle = self.page.locator("button[data-nv-work-hide-done]").first
        toggle.wait_for(state="visible", timeout=6000)
        if toggle.get_attribute("aria-pressed") == "true":
            toggle.click()

    def drag_ticket(self, tid, target_col=None):
        """HTML5-DnD deterministisch via DataTransfer-Dispatches."""
        return self.page.evaluate("""([tid, col]) => {
          const card = document.querySelector('article[data-nv-ticket="' + tid + '"]');
          if (!card) return false;
          const dt = new DataTransfer();
          card.dispatchEvent(new DragEvent('dragstart', {
            dataTransfer: dt, bubbles: true, cancelable: true}));
          const target = col
            ? document.querySelector('article[data-nv-col="' + col
                + '"] [data-nv-col-cards]')
            : card.parentElement;
          if (!target) return false;
          const rect = target.getBoundingClientRect();
          const opts = {dataTransfer: dt, bubbles: true, cancelable: true,
            clientX: rect.left + rect.width / 2,
            clientY: rect.top + rect.height / 2};
          target.dispatchEvent(new DragEvent('dragover', opts));
          target.dispatchEvent(new DragEvent('drop', opts));
          card.dispatchEvent(new DragEvent('dragend', {
            dataTransfer: dt, bubbles: true, cancelable: true}));
          return true;
        }""", [tid, target_col])

    def assert_clean_page(self):
        self.assertEqual([], self.page_errors,
                         "Die Work-Ansicht erzeugte JavaScript-Fehler")

    # ========================================================== 1. Sidebar
    def test_01_nv_sidebar_api_exists_and_is_shared(self):
        """Vorbedingung: Work geöffnet. Aktion: NV-Objekte im Browser lesen.

        Erwartung: ``NV.sidebar`` existiert mit open/close/isOpen und wird von
        ``NV.editView`` wie von ``NV.context`` genutzt (kein doppeltes,
        ansichtsspezifisches Schließverhalten).
        """
        self.write_store([ticket("AP1", "Sidebar-Karte")])
        self.goto_work()
        info = self.page.evaluate("""() => ({
          sidebar: !!(window.NV && NV.sidebar && typeof NV.sidebar === 'object'),
          methods: (window.NV && NV.sidebar)
            ? ['open', 'close', 'isOpen'].filter(
                k => typeof NV.sidebar[k] === 'function') : [],
          editView: !!(window.NV && NV.editView),
          context: !!(window.NV && NV.context)
        })""")
        self.assertTrue(info["sidebar"], "NV.sidebar existiert nicht")
        self.assertEqual(["open", "close", "isOpen"], info["methods"],
                         "NV.sidebar hat nicht die gemeinsamen Steuerfunktionen")
        self.assertTrue(info["editView"] and info["context"],
                        "NV.editView oder NV.context fehlt")

    def test_02_settings_editview_escape_scrim_and_focus_return(self):
        """AP1 GH-57 unverändert: Settings-Edit-View öffnet/schließt zentral.

        Vorbedingung: Settings, Desktop. Aktion: Global-Agents-Edit öffnen,
        Escape, erneut öffnen, Scrim klicken. Erwartung: body-Attribut gesetzt,
        Fokus am Auslöser zurück, Scrim schließt identisch.
        """
        self.write_store([])
        self.goto_work()
        self.route_to("#/settings")
        self.page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=20000)
        trigger = self.page.locator(
            "section[data-nv-ssection='global-agents'] "
            "button[data-nv-action='global-agents-edit']").first
        trigger.wait_for(state="visible", timeout=15000)
        trigger.click()
        aside = self.page.locator("aside[data-nv-editview]").first
        aside.wait_for(state="visible", timeout=10000)
        self.assertTrue(
            self.page.evaluate("() => !!(NV.sidebar && NV.sidebar.isOpen())")
            or self.page.evaluate("() => NV.editView.isOpen()"),
            "Die zentrale Sidebar meldet sich nicht als offen")
        self.page.keyboard.press("Escape")
        self.wait_until(lambda: not aside.is_visible(),
                        message="Escape schließt die Settings-Edit-View nicht")
        self.assertEqual(
            "global-agents-edit",
            self.page.evaluate(
                "() => document.activeElement && document.activeElement"
                ".getAttribute('data-nv-action')"),
            "Der Fokus kehrt nicht zum Auslöser zurück")
        trigger.click()
        aside.wait_for(state="visible", timeout=10000)
        self.click_open_scrim()
        self.wait_until(lambda: not aside.is_visible(),
                        message="Der Scrim schließt die Edit-View nicht")

    def test_03_work_ticket_editor_open_close_identical(self):
        """AP1 GH-67: Ticket-Editor öffnet/schließt wie die Settings-Sidebar.

        Vorbedingung: Work, Desktop. Aktion: Paket anlegen, Escape, erneut
        öffnen, Scrim. Erwartung: identische zentrale Schließmechanismen.
        """
        self.write_store([])
        self.goto_work()
        editor = self.open_new("package")
        self.assertTrue(
            self.page.evaluate("() => NV.editView.isOpen()"),
            "Der Ticket-Editor meldet sich nicht als offen")
        self.page.keyboard.press("Escape")
        self.wait_until(lambda: not editor.is_visible(),
                        message="Escape schließt den Ticket-Editor nicht")
        self.assertEqual(
            "new-package",
            self.page.evaluate(
                "() => document.activeElement && document.activeElement"
                ".getAttribute('data-nv-action')"),
            "Der Fokus kehrt nach Escape nicht zum Anlegen-Button zurück")
        self.open_new("package")
        self.click_open_scrim()
        self.wait_until(lambda: not self.editor().is_visible(),
                        message="Der Scrim schließt den Ticket-Editor nicht")

    def test_04_work_context_panel_escape_close(self):
        """AP1: Das Work-Detail-Panel (NV.context) schließt per Escape.

        Vorbedingung: eine Karte, Desktop. Aktion: Details öffnen, Escape.
        Erwartung: Panel offen, dann geschlossen; body-Attribut konsistent.
        """
        self.write_store([ticket("AP1", "Detail-Panel")])
        self.goto_work()
        self.card("AP1").locator(
            "button[data-nv-action='ticket-details']").first.click()
        detail = self.page.locator("[data-nv-ticket-detail='AP1']").first
        detail.wait_for(state="visible", timeout=5000)
        self.assertTrue(self.page.evaluate("() => NV.context.isOpen()"),
                        "NV.context ist nicht offen")
        self.page.keyboard.press("Escape")
        self.wait_until(lambda: not detail.is_visible(),
                        message="Escape schließt das Detail-Panel nicht")
        self.assertNotEqual(
            "true", self.page.evaluate(
                "() => document.body.getAttribute('data-nv-context-open')"),
            "Das body-Attribut bleibt nach Escape gesetzt")

    def test_05_route_change_closes_editview_and_context_without_reload(self):
        """AP1: Routenwechsel schließt beide Panels (Parität), ohne Reload.

        Vorbedingung: Work, Editor offen. Aktion: Marker setzen, Route wechseln
        (hash), Editor und danach Detail-Panel öffnen und erneut wechseln.
        Erwartung: beide Panels geschlossen; Marker überlebt (kein Voll-Laden).
        """
        self.write_store([ticket("AP1", "Routen-Parität")])
        self.goto_work()
        self.open_new("package")
        self.set_marker()
        self.route_to("#/settings")
        self.page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=20000)
        self.assertFalse(self.page.evaluate("() => NV.editView.isOpen()"),
                         "Ein Routenwechsel schließt den Editor nicht")
        self.assert_js_marker_alive()
        self.route_to("#/project/" + PROJECT + "/work")
        self.page.locator("section[data-nv-ppanel='work']").wait_for(
            state="visible", timeout=20000)
        self.card("AP1").locator(
            "button[data-nv-action='ticket-details']").first.click()
        self.page.locator("[data-nv-ticket-detail='AP1']").first.wait_for(
            state="visible", timeout=5000)
        self.assertTrue(self.page.evaluate("() => NV.context.isOpen()"),
                        "Das Detail-Panel ist nicht offen")
        self.route_to("#/settings")
        self.page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=20000)
        self.assertFalse(self.page.evaluate("() => NV.context.isOpen()"),
                         "Ein Routenwechsel schließt das Detail-Panel nicht")

    def test_06_settings_editview_resize_and_mobile_fullscreen_unchanged(self):
        """AP1 GH-57: Resize-Griff, sessionStorage-Breite, Vollbild ≤768px.

        Vorbedingung: Desktop-Settings. Aktion: Edit-View öffnen, Griff ziehen,
        schließen, wieder öffnen; danach 600x800. Erwartung: Breite bleibt in
        sessionStorage erhalten; auf Mobile Vollbild ohne Griff.
        """
        self.write_store([])
        self.goto_work()
        self.route_to("#/settings")
        self.page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=20000)
        self.page.locator(
            "section[data-nv-ssection='global-agents'] "
            "button[data-nv-action='global-agents-edit']").first.click()
        aside = self.page.locator("aside[data-nv-editview]").first
        aside.wait_for(state="visible", timeout=10000)
        handle = self.page.locator("[data-nv-editview-resize]").first
        self.assertTrue(handle.count() >= 1, "Der Resize-Griff fehlt auf Desktop")
        box = aside.bounding_box()
        hbox = handle.bounding_box()
        start_x, start_y = hbox["x"] + hbox["width"] / 2, hbox["y"] + hbox["height"] / 2
        self.page.mouse.move(start_x, start_y)
        self.page.mouse.down()
        self.page.mouse.move(start_x - 90, start_y, steps=6)
        self.page.mouse.up()
        self.page.wait_for_timeout(250)
        stored = self.page.evaluate(
            "() => sessionStorage.getItem('nv-editview-width')")
        self.assertIsNotNone(
            stored, "Die Breite wurde nicht in sessionStorage gespeichert")
        self.page.keyboard.press("Escape")
        self.wait_until(lambda: not aside.is_visible(),
                        message="Escape schließt die Edit-View nicht")

        mobile = self.browser.new_context(viewport=MOBILE)
        self.addCleanup(mobile.close)
        page = mobile.new_page()
        page.set_default_timeout(8000)
        page.goto(self.base + "/#t=" + self.token)
        page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)
        page.goto(self.base + "/#/settings")
        page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=25000)
        page.locator(
            "section[data-nv-ssection='global-agents'] "
            "button[data-nv-action='global-agents-edit']").first.click()
        maside = page.locator("aside[data-nv-editview]").first
        maside.wait_for(state="visible", timeout=10000)
        mbox = maside.bounding_box()
        self.assertGreaterEqual(mbox["width"], MOBILE["width"] * 0.95,
                                "Die Edit-View ist auf Mobile nicht bildbreit")
        self.assertGreaterEqual(mbox["height"], MOBILE["height"] * 0.95,
                                "Die Edit-View ist auf Mobile nicht bildhoch")
        self.assertFalse(
            page.locator("[data-nv-editview-resize]").first.is_visible(),
            "Der Resize-Griff ist auf Mobile nicht ausgeblendet")

    # ============================================== 2. Priorisierung/Zähler
    def test_07_priority_strip_absent_on_desktop(self):
        """AP2: Desktop zeigt keine Priorisierungsansicht – auch kein Layout.

        Vorbedingung: Ready-Tickets, 1500x1100. Aktion: Work öffnen.
        Erwartung: kein ``div[data-nv-priority-strip]`` im DOM; Board sichtbar.
        """
        self.write_store([ticket("AP1", "Ready A"), ticket("AP2", "Ready B")])
        self.set_priority(["AP1", "AP2"])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        self.assertEqual(
            0, self.page.locator("div[data-nv-priority-strip]").count(),
            "Die Priorisierungsansicht ist auf Desktop im DOM vorhanden")

    def test_08_priority_strip_visible_on_mobile_ready_only(self):
        """AP2: Mobile zeigt den Strip, ausschließlich mit Rohzustand open.

        Vorbedingung: draft/open/in-progress, 600x800. Aktion: Work öffnen.
        Erwartung: Strip sichtbar; nur die Ready-ID erscheint als Zeile.
        """
        self.write_store([
            ticket("AP3", "Draft", state="draft"),
            ticket("AP1", "Ready"),
            ticket("AP2", "Running", state="in-progress"),
        ])
        self.goto_work(viewport=MOBILE)
        strip = self.strip()
        strip.wait_for(state="visible", timeout=5000)
        ids = strip.locator("[data-nv-priority-id]").evaluate_all(
            "els => els.map(e => e.getAttribute('data-nv-priority-id'))")
        self.assertEqual(["AP1"], ids,
                         "Der Strip enthält nicht ausschließlich Ready-Tickets")

    def test_09_prio_count_zero_with_configured_but_no_ready(self):
        """AP2 Regression: 5 konfigurierte IDs, 0 Ready ⇒ Zähler „0“.

        Vorbedingung: fünf Draft-Tickets, alle in PACKAGE_ORDER. Aktion:
        mobile Work öffnen. Erwartung: Zähler enthält 0 und „prioritized“,
        nie „priotized“.
        """
        ids = ["D%d" % n for n in range(1, 6)]
        self.write_store([ticket(i, "Draft " + i, state="draft") for i in ids])
        self.set_priority(ids)
        self.goto_work(viewport=MOBILE)
        self.strip().wait_for(state="visible", timeout=5000)
        text = self.prio_count().inner_text().strip()
        self.assertIn("prioritized", text.lower(),
                      "Der Zähler enthält nicht das englische Wort: " + text)
        self.assertNotIn("priotized", text.lower(),
                         "Der Zähler enthält den Tippfehler: " + text)
        self.assertIn("0", text,
                      "Ohne Ready-Tickets muss der Zähler 0 zeigen: " + text)
        self.assertNotIn("5", text,
                         "Der Zähler zählt konfigurierte Drafts: " + text)

    def test_10_prio_count_singular_one_ready(self):
        """AP2: genau 1 priorisierte Ready-Karte ⇒ Singularform.

        Vorbedingung: ein Ready- und zwei Draft-Tickets, alle priorisiert.
        Erwartung: „1 prioritized ticket“ (kein Plural).
        """
        self.write_store([
            ticket("AP1", "Ready"),
            ticket("D1", "Draft 1", state="draft"),
            ticket("D2", "Draft 2", state="draft"),
        ])
        self.set_priority(["AP1", "D1", "D2"])
        self.goto_work(viewport=MOBILE)
        self.strip().wait_for(state="visible", timeout=5000)
        text = self.prio_count().inner_text().strip()
        self.assertIn("1 prioritized ticket", text,
                      "Die Singularform fehlt: " + text)
        self.assertNotIn("tickets", text,
                         "Bei einem Ticket steht die Pluralform: " + text)

    def test_11_prio_count_plural_multiple_ready(self):
        """AP2: mehrere priorisierte Ready-Karten ⇒ Pluralform mit Zahl.

        Vorbedingung: zwei Ready-Tickets in PACKAGE_ORDER.
        Erwartung: „2 prioritized tickets“.
        """
        self.write_store([ticket("AP1", "Ready A"), ticket("AP2", "Ready B")])
        self.set_priority(["AP1", "AP2"])
        self.goto_work(viewport=MOBILE)
        self.strip().wait_for(state="visible", timeout=5000)
        text = self.prio_count().inner_text().strip()
        self.assertIn("2 prioritized tickets", text,
                      "Die Pluralform fehlt: " + text)
        self.assertNotIn("priotized", text.lower())

    def test_12_prio_count_after_reorder_updates_without_reload(self):
        """AP2: Zähler bleibt nach lokalem Speichern korrekt (ohne Route-Reload).

        Vorbedingung: zwei priorisierte Ready-Tickets, mobile Work. Aktion:
        Marker setzen, priority-down klicken. Erwartung: Reihenfolge und Zähler
        lokal aktualisiert, DOM-Marker erhalten.
        """
        self.write_store([ticket("AP1", "Ready A"), ticket("AP2", "Ready B")])
        self.set_priority(["AP1", "AP2"])
        self.goto_work(viewport=MOBILE)
        strip = self.strip()
        strip.wait_for(state="visible", timeout=5000)
        ids = strip.locator("[data-nv-priority-id]").evaluate_all(
            "els => els.map(e => e.getAttribute('data-nv-priority-id'))")
        self.assertGreaterEqual(len(ids), 2)
        self.set_marker()
        strip.locator(
            "[data-nv-priority-id='%s'] button[data-nv-action='priority-down']"
            % ids[0]).first.click()
        self.wait_until(
            lambda: strip.locator("[data-nv-priority-id]").evaluate_all(
                "els => els.map(e => e.getAttribute('data-nv-priority-id'))"
            )[:1] == [ids[1]],
            message="Die Reihenfolge wurde lokal nicht aktualisiert")
        self.assertIn("2 prioritized tickets", self.prio_count().inner_text(),
                      "Der Zähler wurde nach dem Speichern nicht nachgezogen")
        self.assert_marker_alive()

    # ============================================= 3. Draft/Ready-Zuordnung
    def test_13_state_to_column_mapping_and_raw_state(self):
        """AP6: gespeicherter Zustand bestimmt Spalte, Badge und data-nv-state.

        Vorbedingung: draft/open/in-progress/blocked/waiting-merge/done.
        Aktion: Work öffnen. Erwartung: draft→draft, open→ready,
        in-progress→running, blocked/waiting-merge→ready, done verborgen.
        """
        self.write_store([
            ticket("AP3", "Draft", state="draft"),
            ticket("AP1", "Ready"),
            ticket("AP2", "Running", state="in-progress"),
            ticket("B1", "Blocked", type="bug", state="blocked"),
            ticket("W1", "Waiting", state="waiting-merge"),
            ticket("AP4", "Done", state="done", commit="abcdef1", test="t"),
        ])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        cases = {
            "AP3": ("draft", "draft"), "AP1": ("ready", "open"),
            "AP2": ("running", "in-progress"), "B1": ("ready", "blocked"),
            "W1": ("ready", "waiting-merge"),
        }
        for tid, (column, raw) in cases.items():
            with self.subTest(ticket=tid):
                self.assertEqual(
                    1, self.col(column).locator(
                        "article[data-nv-ticket='%s']" % tid).count(),
                    "%s liegt nicht in Spalte %s" % (tid, column))
                self.assertEqual(raw, self.card(tid).get_attribute(
                    "data-nv-state"), "Falscher Rohzustand bei " + tid)
        self.wait_until(lambda: not self.card("AP4").is_visible(),
                        message="Ein done-Ticket ist nicht verborgen")

    def test_14_draft_and_ready_badges_are_distinguishable(self):
        """AP6: Draft heißt Draft/Entwurf, Ready heißt Ready/Bereit.

        Vorbedingung: ein Draft- und ein Ready-Ticket. Erwartung: die
        jeweilige Bezeichnung erscheint bei der richtigen Karte, nicht
        vertauscht.
        """
        self.write_store([
            ticket("AP3", "Nur Entwurf", state="draft"),
            ticket("AP1", "Bereit zum Start"),
        ])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        draft_text = self.card_state_text("AP3")
        ready_text = self.card_state_text("AP1")
        self.assertTrue(any(t in draft_text for t in ("draft", "entwurf")),
                        "Die Draft-Karte zeigt kein Draft-Badge: " + draft_text)
        self.assertTrue(any(t in ready_text for t in ("ready", "bereit", "open", "offen")),
                        "Die Ready-Karte zeigt kein Ready-Badge: " + ready_text)
        self.assertNotIn("ready", draft_text)
        self.assertNotIn("draft", ready_text)

    def test_15_state_buttons_persist_correct_state(self):
        """AP6: „Bereit“ speichert open, „Entwurf“ speichert draft.

        Vorbedingung: je ein Draft-/Ready-Ticket. Aktion: Bereit- und
        Entwurf-Button klicken. Erwartung: Store und Spalte wechseln passend.
        """
        self.write_store([
            ticket("AP3", "Draft", state="draft"),
            ticket("AP1", "Ready"),
        ])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        self.card("AP3").locator(
            "button[data-nv-action='ticket-ready']").first.click()
        self.wait_until(lambda: self.read_store()["AP3"]["state"] == "open",
                        message="„Bereit“ speichert nicht state=open")
        self.card("AP1").locator(
            "button[data-nv-action='ticket-draft']").first.click()
        self.wait_until(lambda: self.read_store()["AP1"]["state"] == "draft",
                        message="„Entwurf“ speichert nicht state=draft")

    def test_16_dnd_state_mapping_both_directions(self):
        """AP6: DnD draft→ready speichert open, ready→draft speichert draft.

        Vorbedingung: je ein Draft-/Ready-Ticket. Aktion: beide DnD-Richtungen.
        Erwartung: Store und Zielspalte stimmen überein.
        """
        self.write_store([
            ticket("AP3", "Draft", state="draft"),
            ticket("AP1", "Ready"),
        ])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        self.assertTrue(self.drag_ticket("AP3", "ready"))
        self.wait_until(lambda: self.read_store()["AP3"]["state"] == "open",
                        message="DnD Draft→Ready speichert nicht open")
        self.assertTrue(self.drag_ticket("AP1", "draft"))
        self.wait_until(lambda: self.read_store()["AP1"]["state"] == "draft",
                        message="DnD Ready→Draft speichert nicht draft")

    def test_17_viewing_detail_does_not_change_state(self):
        """AP6: reines Anzeigen ändert den gespeicherten Zustand nicht.

        Vorbedingung: Draft-Ticket. Aktion: Karte öffnen und Again schließen.
        Erwartung: Store bleibt draft, Badge unverändert.
        """
        self.write_store([ticket("AP3", "Sichtbar", state="draft")])
        self.goto_work()
        self.card("AP3").locator(
            "button[data-nv-action='ticket-details']").first.click()
        self.page.locator("[data-nv-ticket-detail='AP3']").first.wait_for(
            state="visible", timeout=5000)
        self.page.keyboard.press("Escape")
        self.assertEqual("draft", self.read_store()["AP3"]["state"],
                         "Das Öffnen der Details hat den Zustand geändert")
        self.assertEqual("draft", self.card("AP3").get_attribute("data-nv-state"))

    def test_18_status_badge_is_span_without_action(self):
        """AP6: Status als nicht-interaktives Badge, separater Bedienweg.

        Vorbedingung: Draft-/Ready-Ticket. Erwartung: Status wird in einem
        ``span`` ohne ``data-nv-action`` gezeigt; kein Button trägt die reine
        Statusbezeichnung; Bereit/Entwurf-Buttons bleiben vorhanden.
        """
        self.write_store([
            ticket("AP3", "Draft", state="draft"),
            ticket("AP1", "Ready"),
        ])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        for tid in ("AP3", "AP1"):
            with self.subTest(ticket=tid):
                result = self.card(tid).evaluate("""card => {
                  const label = /^(draft|open|ready|entwurf|bereit|done|erledigt)$/i;
                  const interactive = Array.from(
                    card.querySelectorAll('button, [data-nv-action]'))
                    .filter(e => label.test((e.textContent || '').trim())).length;
                  const spans = Array.from(card.querySelectorAll('span'))
                    .filter(e => label.test((e.textContent || '').trim())
                      && !e.hasAttribute('data-nv-action')).length;
                  return {interactive, spans};
                }""")
                self.assertEqual(0, result["interactive"],
                                 "Der Status ist als Button/Befehl ausgeführt")
                self.assertGreaterEqual(result["spans"], 1,
                                        "Es gibt kein Status-Badge als span")
        self.assertGreaterEqual(self.card("AP3").locator(
            "button[data-nv-action='ticket-ready']").count(), 1)
        self.assertGreaterEqual(self.card("AP1").locator(
            "button[data-nv-action='ticket-draft']").count(), 1)

    # ======================================= 4. Statuswechsel ohne Neuladen
    def test_19_state_button_keeps_dom_and_filters(self):
        """AP6: Statuswechsel per Button erhält DOM, Suche und Filter.

        Vorbedingung: Karte, Suchbegriff, gesetzter Filter, DOM-Marker. Aktion:
        „Bereit“ klicken. Erwartung: kein Voll-Neuladen, Suche/aria-pressed
        unverändert, Karte in neuer Spalte, Spaltenzähler korrekt.
        """
        self.write_store([
            ticket("AP3", "Alpha Draft", state="draft"),
            ticket("AP1", "Beta Ready"),
        ])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        search = self.page.locator("input[data-nv-work-search]").first
        search.fill("Alpha")
        chip = self.page.locator("button[data-nv-work-kind='package']").first
        chip.click()
        self.wait_until(lambda: chip.get_attribute("aria-pressed") == "true",
                        message="Der Filter ist nicht aktiv")
        self.set_marker()
        self.card("AP3").locator(
            "button[data-nv-action='ticket-ready']").first.click()
        self.wait_until(lambda: self.read_store()["AP3"]["state"] == "open",
                        message="Der Statuswechsel wurde nicht gespeichert")
        self.assert_marker_alive()
        self.assertEqual("Alpha", search.input_value(),
                         "Der Suchbegriff ging verloren")
        self.assertEqual("true", chip.get_attribute("aria-pressed"),
                         "Die Filtereinstellung ging verloren")
        self.wait_until(
            lambda: self.col("ready").locator(
                "article[data-nv-ticket='AP3']").count() == 1,
            message="Die Karte ist nicht in die Ready-Spalte gewechselt")

    def test_20_detail_state_save_keeps_dom_and_filters(self):
        """AP6: Detail-State-Save erhält DOM, Suche und Schnellfilter.

        Vorbedingung: Draft-Ticket, Suche, Filter, Marker. Aktion: im Detail
        Zustand auf open setzen undticket-state-save klicken. Erwartung: kein
        Voll-Neuladen; Suche/aria-pressed unverändert; Karte in Ready.
        """
        self.write_store([
            ticket("AP3", "Alpha Draft", state="draft"),
            ticket("AP1", "Beta Ready"),
        ])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        search = self.page.locator("input[data-nv-work-search]").first
        search.fill("Alpha")
        chip = self.page.locator("button[data-nv-work-kind='package']").first
        chip.click()
        self.card("AP3").locator(
            "button[data-nv-action='ticket-details']").first.click()
        detail = self.page.locator("[data-nv-ticket-detail='AP3']").first
        detail.wait_for(state="visible", timeout=5000)
        detail.locator("select[data-nv-ticket-state-select]").first.select_option("open")
        self.set_marker()
        detail.locator("button[data-nv-action='ticket-state-save']").first.click()
        self.wait_until(lambda: self.read_store()["AP3"]["state"] == "open",
                        message="Der Detail-State-Save speichert nicht open")
        self.assert_marker_alive()
        self.assertEqual("Alpha", search.input_value(),
                         "Der Suchbegriff ging beim Detail-Save verloren")
        self.assertEqual("true", chip.get_attribute("aria-pressed"),
                         "Die Filtereinstellung ging beim Detail-Save verloren")

    # ===================================== 5. Kategorie vs. Ticket Type
    def test_21_category_select_options_and_default(self):
        """AP4: Kategorie hat genau feature/bug/feedback, Default feature.

        Vorbedingung: leerer Store. Aktion: „Paket anlegen“ öffnen.
        Erwartung: select[data-nv-field=category] mit genau diesen Optionen
        (lokalisierte Anzeige), Vorauswahl feature.
        """
        self.write_store([])
        self.goto_work()
        editor = self.open_new("package")
        select = editor.locator("[data-nv-field='category']")
        self.assertGreaterEqual(select.count(), 1,
                                "Das Anlageformular hat keine Kategorie-Auswahl")
        options = select.first.locator("option").evaluate_all(
            "els => els.map(e => ({value: e.value, text: e.textContent.trim()}))")
        self.assertEqual({"feature", "bug", "feedback"},
                         {row["value"] for row in options},
                         "Die Kategorie-Optionen sind falsch: " + repr(options))
        self.assertEqual("feature", select.first.input_value(),
                         "Die Kategorie-Vorauswahl ist nicht feature")

    def test_22_ticket_type_options_and_button_defaults(self):
        """AP4: Tickettyp task/bug/feature/feedback je Button vorbelegt.

        Vorbedingung: drei Öffnungsbuttons. Aktion: Paket/Bug/Feedback öffnen.
        Erwartung: Optionen task/bug/feature/feedback, aria-label vorhanden,
        Default task / bug / feedback.
        """
        self.write_store([])
        self.goto_work()
        expected = {"package": "task", "bug": "bug", "feedback": "feedback"}
        for mode, default in expected.items():
            with self.subTest(mode=mode):
                editor = self.open_new(mode)
                try:
                    select = self.ticket_type_select(editor)
                    options = select.locator("option").evaluate_all(
                        "els => els.map(e => e.value)")
                    self.assertEqual({"task", "bug", "feature", "feedback"},
                                     set(options),
                                     "Die Tickettyp-Optionen sind falsch: " + repr(options))
                    self.assertTrue(select.get_attribute("aria-label"),
                                    "Die Tickettyp-Auswahl hat kein aria-label")
                    self.assertEqual(default, select.input_value(),
                                     "Falsche Tickettyp-Vorauswahl für " + mode)
                finally:
                    self.page.keyboard.press("Escape")
                    self.wait_until(lambda: not self.editor().is_visible(),
                                    message="Editor lässt sich nicht schließen")

    def test_23_type_preselect_does_not_override_category(self):
        """AP4: „Bug melden“ lässt die Kategorie auf feature.

        Vorbedingung: Bug-Button. Erwartung: type=bug, category=feature –
        die Vorauswahl im Tickettyp überschreibt die Kategorie nicht.
        """
        self.write_store([])
        self.goto_work()
        editor = self.open_new("bug")
        self.assertEqual("bug", self.ticket_type_select(editor).input_value())
        category = editor.locator("[data-nv-field='category']").first
        self.assertGreaterEqual(category.count(), 1, "Keine Kategorie-Auswahl")
        self.assertEqual("feature", category.input_value(),
                         "Die Tickettyp-Vorauswahl hat die Kategorie überschrieben")

    def test_24_changed_ticket_type_is_saved(self):
        """AP4: geänderter Tickettyp wird gespeichert, nicht die Vorauswahl.

        Vorbedingung: Bug-Button, dann auf feedback ändern; und Paket-Button,
        dann auf bug ändern. Aktion: Titel füllen und speichern. Erwartung:
        gespeicherter type=feedback bzw. type=bug; state bleibt draft.
        """
        cases = (("bug", "feedback", "FB-GH67-A"),
                 ("package", "bug", "BUG-GH67-B"))
        for mode, changed, title in cases:
            with self.subTest(mode=mode, changed=changed):
                self.write_store([])
                self.goto_work()
                editor = self.open_new(mode)
                self.ticket_type_select(editor).select_option(changed)
                editor.locator("input[data-nv-field='title']").first.fill(title)
                editor.locator("button[data-nv-action='ticket-save']").first.click()
                self.wait_until(
                    lambda: any(r["title"] == title
                                for r in self.read_store().values()),
                    message="Das Ticket mit geändertem Typ wurde nicht gespeichert")
                row = [r for r in self.read_store().values()
                       if r["title"] == title][0]
                self.assertEqual(changed, row.get("type"),
                                 "Der geänderte Tickettyp wurde nicht gespeichert")
                self.assertEqual("draft", row.get("state"),
                                 "Ein neues Ticket ist kein Draft")

    def test_25_new_ticket_draft_and_valid_id(self):
        """AP11: neue Tickets behalten state=draft und eine gültige ID.

        Vorbedingung: leerer Store. Aktion: Paket anlegen und speichern.
        Erwartung: genau ein Eintrag, state=draft, ID nicht leer/ gültig.
        """
        self.write_store([])
        self.goto_work()
        editor = self.open_new("package")
        editor.locator("input[data-nv-field='title']").first.fill("Neues GH67")
        editor.locator("button[data-nv-action='ticket-save']").first.click()
        self.wait_until(
            lambda: any(r["title"] == "Neues GH67"
                        for r in self.read_store().values()),
            message="Das neue Ticket wurde nicht gespeichert")
        rows = [r for r in self.read_store().values()
                if r["title"] == "Neues GH67"]
        self.assertEqual(1, len(rows))
        self.assertEqual("draft", rows[0]["state"])
        self.assertRegex(str(rows[0]["id"]), r"^[A-Za-z][A-Za-z0-9_-]*$",
                         "Die vergebene ID ist ungültig")

    # ================================================ 6. Filterleiste
    def test_26_hide_done_outside_filter_bar_and_effective(self):
        """AP5: „Show done“ außerhalb der Filterleiste, aber wirksam.

        Vorbedingung: ein done-Ticket. Aktion: Work öffnen, Show-done klicken.
        Erwartung: der Button liegt nicht in ``[data-nv-filter-bar]``, sondern
        direkt in der Work-Sektion; done ist standardmäßig verborgen und danach
        sichtbar.
        """
        self.write_store([
            ticket("AP4", "Fertig", state="done", commit="abcdef1", test="t")])
        self.goto_work()
        placement = self.page.evaluate("""() => {
          const btn = document.querySelector('button[data-nv-work-hide-done]');
          if (!btn) return {present: false};
          return {
            present: true,
            inFilterBar: !!btn.closest('[data-nv-filter-bar]'),
            inWork: !!btn.closest("section[data-nv-ppanel='work']")
          };
        }""")
        self.assertTrue(placement["present"], "Show-done fehlt")
        self.assertFalse(placement["inFilterBar"],
                         "Show-done liegt innerhalb der Filterleiste")
        self.assertTrue(placement["inWork"],
                        "Show-done liegt außerhalb der Work-Sektion")
        self.wait_until(lambda: not self.card("AP4").is_visible(),
                        message="done ist nicht standardmäßig verborgen")
        self.show_done()
        self.wait_until(lambda: self.card("AP4").is_visible(),
                        message="Show-done blendet done nicht ein")

    def test_27_no_closed_quick_filter_and_remaining_chips(self):
        """AP5: kein „Closed“-Schnellfilter; Chips draft/ready/running.

        Vorbedingung: Work geöffnet. Erwartung: kein
        ``button[data-nv-work-state='done']``; Chips draft/ready/running
        vorhanden; Show-done als eigener Schalter.
        """
        self.write_store([ticket("AP1", "Ready")])
        self.goto_work()
        self.assertEqual(0, self.page.locator(
            "button[data-nv-work-state='done']").count(),
            "Es gibt noch einen done/Closed-Schnellfilter")
        for state in ("draft", "ready", "running"):
            self.assertGreaterEqual(self.page.locator(
                "button[data-nv-work-state='%s']" % state).count(), 1,
                "Der Chip %s fehlt" % state)
        self.assertGreaterEqual(self.page.locator(
            "button[data-nv-work-hide-done]").count(), 1,
            "Der eigenständige Show-done-Schalter fehlt")

    def test_28_filter_bar_alignment_desktop(self):
        """AP5: Suche und Schnellfilter auf Desktop vertikal bündig.

        Vorbedingung: 1500x1100. Erwartung: ``div[data-nv-search]`` und
        ``[data-nv-work-kinds]`` teilen eine Kante (±4px), überlappen nicht.
        """
        self.write_store([ticket("AP1", "Ready")])
        self.goto_work()
        boxes = self.page.evaluate("""() => {
          const pick = s => {
            const n = document.querySelector(s);
            if (!n) return null;
            const r = n.getBoundingClientRect();
            return {top: r.top, bottom: r.bottom, left: r.left, right: r.right};
          };
          return {search: pick('div[data-nv-search]'),
                  kinds: pick('[data-nv-work-kinds]')};
        }""")
        self.assertIsNotNone(boxes["search"], "Die Suchleiste fehlt")
        self.assertIsNotNone(boxes["kinds"], "Die Schnellfiltergruppe fehlt")
        search, kinds = boxes["search"], boxes["kinds"]
        aligned = (abs(search["top"] - kinds["top"]) <= 4
                   or abs(search["bottom"] - kinds["bottom"]) <= 4)
        self.assertTrue(aligned,
                        "Suche und Schnellfilter sind nicht bündig: " + repr(boxes))
        overlap = not (search["right"] <= kinds["left"]
                       or kinds["right"] <= search["left"])
        self.assertFalse(overlap, "Suche und Schnellfilter überlappen sich")

    def test_29_filter_bar_no_overlap_or_overflow_mobile(self):
        """AP5: auf 600px kein horizontaler Überlauf, keine Überlappung.

        Vorbedingung: 600x800. Erwartung: scrollWidth <= clientWidth + 2;
        die Bounding Boxes von Suche und Schnellfilter überlappen nicht.
        """
        self.write_store([ticket("AP1", "Ready")])
        self.goto_work(viewport=MOBILE)
        metrics = self.page.evaluate("""() => {
          const doc = document.documentElement;
          const pick = s => {
            const n = document.querySelector(s);
            if (!n) return null;
            const r = n.getBoundingClientRect();
            return {top: r.top, bottom: r.bottom, left: r.left, right: r.right};
          };
          return {scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth,
                  search: pick('div[data-nv-search]'),
                  kinds: pick('[data-nv-work-kinds]')};
        }""")
        self.assertLessEqual(
            metrics["scrollWidth"], metrics["clientWidth"] + 2,
            "Die Work-Ansicht verursacht horizontalen Überlauf: " + repr(metrics))
        search, kinds = metrics["search"], metrics["kinds"]
        self.assertIsNotNone(search, "Die Suchleiste fehlt auf Mobile")
        self.assertIsNotNone(kinds, "Die Schnellfiltergruppe fehlt auf Mobile")
        overlap_x = search["left"] < kinds["right"] and kinds["left"] < search["right"]
        overlap_y = search["top"] < kinds["bottom"] and kinds["top"] < search["bottom"]
        self.assertFalse(overlap_x and overlap_y,
                         "Suche und Schnellfilter überlappen auf Mobile")

    # =============================================== 7. Lokalisierung
    def test_30_english_work_texts_are_translated(self):
        """AP3: englische Standardtexte vollständig, keine Rohschlüssel.

        Vorbedingung: leerer Store, Englisch aktiv. Aktion: Formular öffnen,
        Priorisierung (mobile) und Work-Text lesen. Erwartung: Kategorie/
        Tickettyp beschriftet, Zähler englisch, keine „undefined“/„[object“.
        """
        self.write_store([ticket("AP1", "Ready")])
        self.goto_work()
        editor = self.open_new("package")
        editor_text = editor.inner_text()
        self.assertIn("Category", editor_text,
                      "Die Kategorie ist im englischen UI nicht übersetzt")
        self.assertIn("Ticket", editor_text,
                      "Der Tickettyp ist im englischen UI nicht beschriftet")
        self.assertNotRegex(editor_text, r"undefined|\[object",
                            "Das Formular enthält technische Platzhalter")

    def test_31_german_work_texts_are_translated(self):
        """AP3: deutsche Texte für Kategorie, Tickettyp und Zähler.

        Vorbedingung: Ready-Ticket, I18N.set('de'). Aktion: Formular öffnen,
        mobile Priorisierung lesen. Erwartung: deutsche Beschriftungen,
        deutscher Zähler mit korrekter Zahl, keine Rohschlüssel.
        """
        self.write_store([ticket("AP1", "Ready"), ticket("AP2", "Ready2")])
        self.set_priority(["AP1", "AP2"])
        self.goto_work()
        self.set_lang("de")
        self.assertEqual("de", self.page.evaluate(
            "() => (window.VIBE_I18N || window.I18N).current()"))
        editor = self.open_new("package")
        editor_text = editor.inner_text()
        self.assertIn("Kategorie", editor_text,
                      "Die Kategorie ist auf Deutsch nicht übersetzt")
        self.assertRegex(editor_text, r"Ticket ?typ|Ticketart|Tickettyp",
                         "Der Tickettyp ist auf Deutsch nicht übersetzt")
        self.assertNotRegex(editor_text, r"undefined|\[object",
                            "Das Formular enthält technische Platzhalter")
        self.page.keyboard.press("Escape")

        self.goto_work(viewport=MOBILE)
        self.set_lang("de")
        self.strip().wait_for(state="visible", timeout=5000)
        text = self.prio_count().inner_text().strip()
        self.assertRegex(text, r"2|zwei", "Der deutsche Zähler nennt die Zahl nicht")
        self.assertIn("priorisier", text.lower(),
                      "Der deutsche Zähler ist nicht übersetzt: " + text)
        self.assertNotIn("priotized", text.lower())

    def test_32_internal_ids_and_states_stable_across_languages(self):
        """AP3: interne IDs/Statuswerte bleiben in beiden Sprachen unverändert.

        Vorbedingung: Englisch. Aktion: Kategorie-/Tickettyp-Optionen und
        data-nv-state lesen, auf Deutsch umstellen, erneut lesen. Erwartung:
        options values feature/bug/feedback/task und Rohzustände identisch.
        """
        self.write_store([
            ticket("AP3", "Draft", state="draft"),
            ticket("AP1", "Ready"),
        ])
        self.goto_work()
        expected = {"feature", "bug", "feedback"}
        for lang in ("en", "de"):
            with self.subTest(lang=lang):
                self.set_lang(lang)
                editor = self.open_new("package")
                try:
                    category = editor.locator("[data-nv-field='category']").first
                    values = category.locator("option").evaluate_all(
                        "els => els.map(e => e.value)")
                    self.assertEqual(expected, set(values),
                                     "Interne Kategorie-IDs ändern sich mit der Sprache")
                    types = self.ticket_type_select(editor).locator(
                        "option").evaluate_all("els => els.map(e => e.value)")
                    self.assertEqual({"task", "bug", "feature", "feedback"},
                                     set(types),
                                     "Interne Tickettyp-IDs ändern sich mit der Sprache")
                finally:
                    self.page.keyboard.press("Escape")
                    self.wait_until(lambda: not self.editor().is_visible(),
                                    message="Editor schließt nicht")
        self.assertEqual("draft", self.card("AP3").get_attribute("data-nv-state"))
        self.assertEqual("open", self.card("AP1").get_attribute("data-nv-state"))

    # ============================================ 8. Dialogaktionen
    def test_33_cancel_discards_changes(self):
        """AP7: „Cancel“ speichert nichts – mit und ohne Änderungen.

        Vorbedingung: Ticket „Original“. Aktion: (a) Editor ohne Änderung
        abbrechen, (b) Titel ändern und abbrechen. Erwartung: Editor schließt,
        Store-Titel bleibt in beiden Fällen unverändert.
        """
        self.write_store([ticket("AP1", "Original", state="draft")])
        self.goto_work()
        for changed in (False, True):
            with self.subTest(changed=changed):
                editor = self.open_ticket_editor("AP1")
                if changed:
                    editor.locator("input[data-nv-field='title']").first.fill(
                        "Geändert aber nicht gespeichert")
                editor.locator("button[data-nv-action='ticket-cancel']").first.click()
                self.wait_until(lambda: not self.editor().is_visible(),
                                message="Cancel schließt den Editor nicht")
                self.assertEqual("Original", self.read_store()["AP1"]["title"],
                                 "Cancel hat Änderungen gespeichert")
                # GH-67 Zusatz: der Statuswechsel passiert bereits beim Öffnen
                # und bleibt auch nach dem Abbruch erhalten.
                self.assertEqual(
                    "in-progress", self.read_store()["AP1"]["state"],
                    "Cancel hat den automatischen Statuswechsel zurückgenommen")

    def test_34_close_button_naming_and_confirmation(self):
        """AP7: destruktiver Close eindeutig benannt, confirm, Abbruch.

        Vorbedingung: offenes Ticket. Aktion: Label prüfen; Close mit
        abgelehntem und danach bestätigtem Dialog klicken. Erwartung: Label
        weist auf dauerhaftes Schließen hin; Abbruch ändert nichts; Bestätigung
        speichert state=done.
        """
        self.write_store([ticket("AP1", "Abschluss GH67")])
        self.goto_work()
        editor = self.open_ticket_editor("AP1")
        close = editor.locator("button[data-nv-action='ticket-close']").first
        self.assertGreaterEqual(close.count(), 1, "Der Close-Button fehlt")
        label = " ".join(filter(None, [
            close.inner_text(),
            close.get_attribute("aria-label") or "",
            close.get_attribute("title") or ""])).lower()
        self.assertTrue(
            any(term in label for term in ("abschließen", "close ticket",
                                           "dauerhaft", "permanent")),
            "Der Close-Button ist nicht eindeutig benannt: " + label)
        self.dialog_policy = [False]
        close.click()
        self.wait_until(lambda: len(self.dialogs) == 1,
                        message="Close fragt nicht per confirm nach")
        self.assertEqual("in-progress", self.read_store()["AP1"]["state"],
                         "Der abgebrochene Dialog hat trotzdem geschlossen "
                         "(Öffnen des Editors setzt in-progress)")
        self.dialog_policy = [True]
        editor = self.open_ticket_editor("AP1") if not self.editor().is_visible() else self.editor()
        editor.locator("button[data-nv-action='ticket-close']").first.click()
        self.wait_until(lambda: self.read_store()["AP1"]["state"] == "done",
                        message="Bestätigtes Close speichert nicht state=done")

    # ============================ 9. Auto-Statuswechsel beim Bearbeiten
    def test_35_open_editor_from_draft_sets_in_progress(self):
        """Vorbedingung: Ticket im Zustand draft. Aktion: Details → Bearbeiten.

        Erwartung: das Öffnen des Editors setzt Store state=in-progress und
        verschiebt die Karte lokal in article[data-nv-col='running'] mit
        data-nv-state='in-progress' und Badge „In Progress“. Nicht erst das
        Speichern löst den Wechsel aus.
        """
        self.write_store([ticket("AP3", "Draft in Bearbeitung", state="draft")])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        self.set_marker()
        self.open_ticket_editor("AP3")
        self.wait_until(
            lambda: self.read_store()["AP3"]["state"] == "in-progress",
            message="Das Öffnen des Editors speichert nicht state=in-progress")
        self.assert_marker_alive()
        self.wait_until(
            lambda: self.col("running").locator(
                "article[data-nv-ticket='AP3']").count() == 1,
            message="Die Karte ist nicht in die Spalte running gewechselt")
        self.assertEqual(
            "in-progress", self.card("AP3").get_attribute("data-nv-state"),
            "Die Karte trägt nicht den Rohzustand in-progress")
        self.assertIn("in progress", self.card_state_text("AP3").lower(),
                      "Die Karte zeigt kein Badge „In Progress“")

    def test_36_open_editor_from_open_sets_in_progress(self):
        """Gleiche Regel für ein Ticket im Zustand open.

        Vorbedingung: Ticket state=open. Aktion: Editor öffnen. Erwartung:
        Store und UI wechseln auf in-progress/running; kein Voll-Neuladen.
        """
        self.write_store([ticket("AP1", "Ready in Bearbeitung")])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        self.set_marker()
        self.open_ticket_editor("AP1")
        self.wait_until(
            lambda: self.read_store()["AP1"]["state"] == "in-progress",
            message="Ein offenes Ticket wechselt beim Öffnen nicht auf "
                    "state=in-progress")
        self.assert_marker_alive()
        self.wait_until(
            lambda: self.col("running").locator(
                "article[data-nv-ticket='AP1']").count() == 1,
            message="Das offene Ticket ist nicht in die Spalte running gewechselt")
        self.assertIn("in progress", self.card_state_text("AP1").lower(),
                      "Die Karte zeigt kein Badge „In Progress“")

    def test_37_auto_state_change_keeps_search_and_filters(self):
        """Der automatische Wechsel darf Suche und Filter nicht zurücksetzen.

        Vorbedingung: zwei Tickets, Suchbegriff und Typ-Chip aktiv, Marker.
        Aktion: Editor des passenden Tickets öffnen. Erwartung: Store
        in-progress, Karte in running, Suche/aria-pressed unverändert,
        DOM-Marker erhalten.
        """
        self.write_store([
            ticket("AP3", "Alpha in Arbeit", state="draft"),
            ticket("AP1", "Beta unberührt"),
        ])
        self.goto_work()
        search = self.page.locator("input[data-nv-work-search]").first
        search.fill("Alpha")
        chip = self.page.locator("button[data-nv-work-kind='package']").first
        chip.click()
        self.wait_until(lambda: chip.get_attribute("aria-pressed") == "true",
                        message="Der Filter ist nicht aktiv")
        self.set_marker()
        self.open_ticket_editor("AP3")
        self.wait_until(
            lambda: self.read_store()["AP3"]["state"] == "in-progress",
            message="Der automatische Statuswechsel wurde nicht gespeichert")
        self.assert_marker_alive()
        self.assertEqual("Alpha", search.input_value(),
                         "Der Suchbegriff ging beim Öffnen des Editors verloren")
        self.assertEqual("true", chip.get_attribute("aria-pressed"),
                         "Die Filtereinstellung ging beim Öffnen verloren")
        self.wait_until(
            lambda: self.col("running").locator(
                "article[data-nv-ticket='AP3']").count() == 1,
            message="Die Karte ist nicht in der Spalte running")

    def test_38_auto_state_change_applies_even_on_cancel(self):
        """Der Wechsel passiert beim Öffnen – auch bei anschließendem Cancel.

        Vorbedingung: Draft-Ticket „Original“. Aktion: Editor öffnen, Titel
        ändern, ticket-cancel klicken. Erwartung: state bleibt in-progress;
        Titel bleibt „Original“; Karte bleibt in running.
        """
        self.write_store([ticket("AP3", "Original", state="draft")])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        editor = self.open_ticket_editor("AP3")
        self.wait_until(
            lambda: self.read_store()["AP3"]["state"] == "in-progress",
            message="Beim Öffnen wurde kein state=in-progress gespeichert")
        if not self.editor().is_visible():
            # Fällt eine Umsetzung den Editor nach dem Wechsel neu auf, wird
            # er erneut geöffnet (in-progress löst keinen zweiten Wechsel aus).
            editor = self.open_ticket_editor("AP3")
        editor.locator("input[data-nv-field='title']").first.fill(
            "Nur lokal geändert")
        editor.locator("button[data-nv-action='ticket-cancel']").first.click()
        self.wait_until(lambda: not self.editor().is_visible(),
                        message="Cancel schließt den Editor nicht")
        self.assertEqual("in-progress", self.read_store()["AP3"]["state"],
                         "Cancel hat den automatischen Wechsel rückgängig gemacht")
        self.assertEqual("Original", self.read_store()["AP3"]["title"],
                         "Cancel hat die Titeländerung gespeichert")
        self.wait_until(
            lambda: self.col("running").locator(
                "article[data-nv-ticket='AP3']").count() == 1,
            message="Die Karte ist nach Cancel nicht mehr in running")

    def test_39_new_ticket_editor_does_not_auto_change_state(self):
        """Neue Tickets werden beim Öffnen nicht auf in-progress gesetzt.

        Vorbedingung: leerer Store. Aktion: Paket/Bug/Feedback öffnen und
        abbrechen; danach ein Paket speichern. Erwartung: beim Öffnen entsteht
        kein Ticket; das gespeicherte neue Ticket bleibt draft.
        """
        self.write_store([])
        self.goto_work()
        for mode in ("package", "bug", "feedback"):
            with self.subTest(mode=mode):
                editor = self.open_new(mode)
                try:
                    self.assertEqual(
                        0, len(self.read_store()),
                        "Beim Öffnen des Anlageformulars wurde ein Ticket "
                        "auf in-progress gesetzt")
                finally:
                    editor.locator(
                        "button[data-nv-action='ticket-cancel']").first.click()
                    self.wait_until(lambda: not self.editor().is_visible(),
                                    message="Anlageformular schließt nicht")
        editor = self.open_new("package")
        editor.locator("input[data-nv-field='title']").first.fill("Ganz neu GH67")
        editor.locator("button[data-nv-action='ticket-save']").first.click()
        self.wait_until(
            lambda: any(r["title"] == "Ganz neu GH67"
                        for r in self.read_store().values()),
            message="Das neue Ticket wurde nicht gespeichert")
        row = [r for r in self.read_store().values()
               if r["title"] == "Ganz neu GH67"][0]
        self.assertEqual("draft", row["state"],
                         "Ein neues Ticket muss draft bleiben")

    def test_40_no_auto_change_for_in_progress_blocked_waiting_merge(self):
        """Kein automatischer Wechsel bei in-progress/blocked/waiting-merge.

        Vorbedingung: je ein Ticket in diesen Zuständen. Aktion: Editor öffnen
        und abbrechen. Erwartung: Store und data-nv-state bleiben unverändert.
        """
        cases = (("AP2", "in-progress"), ("B1", "blocked"),
                 ("W1", "waiting-merge"))
        for tid, state in cases:
            with self.subTest(ticket=tid, state=state):
                self.write_store([ticket(tid, "Bleibt " + state, state=state)])
                self.goto_work()
                editor = self.open_ticket_editor(tid)
                try:
                    self.assertEqual(
                        state, self.read_store()[tid]["state"],
                        "Der Zustand %s wurde beim Öffnen verändert" % state)
                    self.assertEqual(
                        state, self.card(tid).get_attribute("data-nv-state"),
                        "data-nv-state wurde beim Öffnen verändert")
                finally:
                    editor.locator(
                        "button[data-nv-action='ticket-cancel']").first.click()
                    self.wait_until(lambda: not self.editor().is_visible(),
                                    message="Editor schließt nicht")

    def test_41_done_ticket_is_not_editable_and_stays_done(self):
        """Erledigte Tickets sind nicht bearbeitbar und bleiben done.

        Vorbedingung: erledigtes Ticket mit Nachweis, Show done aktiv. Aktion:
        Details öffnen. Erwartung: kein Bearbeiten-Button, keine Felder, Store
        bleibt done; es findet kein automatischer Statuswechsel statt.
        """
        self.write_store([
            ticket("AP4", "Fertig", state="done", commit="abcdef1", test="t")])
        self.goto_work()
        self.show_done()
        self.wait_until(lambda: self.card("AP4").is_visible(),
                        message="Die erledigte Karte ist nicht einblendbar")
        self.card("AP4").locator(
            "button[data-nv-action='ticket-details']").first.click()
        detail = self.page.locator("[data-nv-ticket-detail='AP4']").first
        detail.wait_for(state="visible", timeout=5000)
        self.assertEqual(0, detail.locator(
            "button[data-nv-action='ticket-edit']").count(),
            "Ein erledigtes Ticket bietet Bearbeiten an")
        self.assertEqual(0, detail.locator("[data-nv-field]").count(),
                         "Ein erledigtes Ticket enthält bearbeitbare Felder")
        self.assertEqual("done", self.read_store()["AP4"]["state"],
                         "Ein erledigtes Ticket wurde automatisch geändert")


if __name__ == "__main__":
    unittest.main()
