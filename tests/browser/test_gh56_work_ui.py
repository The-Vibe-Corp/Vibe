"""GH-56: Browserabnahme der Projektansicht „Work“ (unabhängig aus Ticket + SPEC).

Quelle der Fälle: ``TICKET-GH-56.json`` (Akzeptanzkriterien, Abschnitte
„Sidebar“, „Kanban-Board“, „Drag-and-Drop“, „Filter und Suche“, „Mobile“,
„Geschlossene Tickets“, „Neue Tickets“, „Design-Konsistenz“) und ``SPEC.md``
(Arbeitspakete im maschinenlesbaren ``.vibe/tickets.json``, Sprache der
Oberfläche Englisch). Die Fälle werden nicht aus einem Implementierungsdiff
abgeleitet. Ergänzende DOM-Verträge siehe ``docs/features/GH-56-design-notes.md``
und ``docs/reviews/GH-56-test-agent-report.md``.

Der Live-Server läuft isoliert auf einem freien Port mit bereinigter VIBE_*- /
SANDBOX_-Umgebung und eigenen Temp-Pfaden. Der Browser wird mit dem
vorgegebenen PLAYWRIGHT_BROWSERS_PATH gestartet.

Erwartete Hooks (Vertrag für die Umsetzung):
    ``div[data-nv-board]`` → ``article[data-nv-col='draft|ready|running']``
      → ``div[data-nv-col-cards]`` → ``article[data-nv-ticket='<id>']``
    Karten: ``.nv-ticket-title``, ``button[data-nv-action='ticket-details|ticket-resume']``,
      ``data-nv-state`` (Rohzustand), ``draggable='true'``
    DnD-Feedback: ``div[data-nv-board-ghost]``, ``div[data-nv-drop-marker]``
    Filter: ``button[data-nv-work-state='draft|ready|running']`` mit
      ``aria-pressed`` (GH-67: kein done-Chip), ``input[data-nv-work-search]``,
      ``button[data-nv-work-hide-done]`` (eigenständiger Schalter außerhalb
      der Filterleiste)
    Editor: ``aside[data-nv-ticket-editor]``, ``[data-nv-field]``,
      ``button[data-nv-action='ticket-save|ticket-cancel|ticket-close|ticket-copy']``
    Mobile: ``div[data-nv-work-list]``, kein ``div[data-nv-board]``

Run:

    PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright \
      python3 -m unittest tests.browser.test_gh56_work_ui -v
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


class GH56WorkBrowserTest(unittest.TestCase):
    """Gemeinsamer, isolierter Live-Server; ein Browser-Kontext je Fall."""

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
        self.context = self.browser.new_context(
            viewport={"width": 1500, "height": 1100})
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

    # ------------------------------------------------------- Helfer
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

    def board(self):
        return self.page.locator("div[data-nv-board]").first

    def col(self, name):
        return self.page.locator("article[data-nv-col='%s']" % name).first

    def card(self, tid):
        return self.page.locator("article[data-nv-ticket='%s']" % tid).first

    def editor(self):
        return self.page.locator("aside[data-nv-ticket-editor]").first

    def open_editor(self):
        self.page.locator("[data-nv-action='new-package']").first.click()
        editor = self.editor()
        editor.wait_for(state="visible", timeout=6000)
        return editor

    def strip(self):
        return self.page.locator("div[data-nv-priority-strip]").first

    def stored_priority(self):
        status, body = self.api_json("/api/priority?name=" + PROJECT)
        self.assertEqual(200, status)
        return [str(row.get("id") or "") for row in
                json.loads(body).get("order", [])]

    def dom_card_order(self, column=None):
        root = self.col(column) if column else self.board()
        return root.locator("article[data-nv-ticket]").evaluate_all(
            "els => els.map(e => e.getAttribute('data-nv-ticket'))")

    def drag_ticket(self, tid, target_col=None, target_index=None, drop=True):
        """HTML5-DnD deterministisch via DataTransfer-Dispatches."""
        return self.page.evaluate("""([tid, col, idx, doDrop]) => {
          const card = document.querySelector('article[data-nv-ticket="' + tid + '"]');
          if (!card) return false;
          const dt = new DataTransfer();
          card.dispatchEvent(new DragEvent('dragstart', {
            dataTransfer: dt, bubbles: true, cancelable: true}));
          let target = col
            ? document.querySelector('article[data-nv-col="' + col
                + '"] [data-nv-col-cards]')
            : card.parentElement;
          if (!target) return false;
          let point = target;
          if (idx !== null) {
            const kids = Array.from(target.querySelectorAll('article[data-nv-ticket]'));
            if (kids[idx]) point = kids[idx];
          }
          const rect = point.getBoundingClientRect();
          const opts = {dataTransfer: dt, bubbles: true, cancelable: true,
            clientX: rect.left + rect.width / 2,
            clientY: rect.top + rect.height / 2};
          target.dispatchEvent(new DragEvent('dragover', opts));
          if (!doDrop) return true;
          point.dispatchEvent(new DragEvent('drop', opts));
          card.dispatchEvent(new DragEvent('dragend', {
            dataTransfer: dt, bubbles: true, cancelable: true}));
          return true;
        }""", [tid, target_col, target_index, drop])

    def end_drag(self, tid):
        self.page.evaluate("""(tid) => {
          const card = document.querySelector('article[data-nv-ticket="' + tid + '"]');
          if (card) card.dispatchEvent(new DragEvent('dragend', {
            dataTransfer: new DataTransfer(), bubbles: true, cancelable: true}));
        }""", tid)

    def show_done(self):
        toggle = self.page.locator("button[data-nv-work-hide-done]").first
        toggle.wait_for(state="visible", timeout=6000)
        if toggle.get_attribute("aria-pressed") == "true":
            toggle.click()

    def assert_clean_page(self):
        self.assertEqual([], self.page_errors,
                         "Die Work-Ansicht erzeugte JavaScript-Fehler")

    # ------------------------------------------------------- Board & Karten
    def test_01_board_columns_and_tickets_by_state(self):
        """AP2: Drei Spalten; Tickets nach Zustand; keine Duplikate.

        Vorbedingung: Tickets in draft/open/in-progress/blocked/waiting-merge/done.
        Aktion: Work öffnen. Erwartung: Board mit den Spalten draft/ready/
        running; die Karten liegen genau dort; done ist ausgeblendet; die
        Spaltenüberschriften sind vorhanden und unterscheidbar.
        """
        self.write_store([
            ticket("AP3", "Nur Entwurf", state="draft"),
            ticket("AP1", "Bereit zum Start"),
            ticket("AP2", "Läuft gerade", state="in-progress"),
            ticket("B1", "Blockierter Bug", type="bug", state="blocked"),
            ticket("W1", "Wartet auf Merge", state="waiting-merge"),
            ticket("AP4", "Fertig", state="done", commit="abcdef1",
                   test="test_ap4"),
        ])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)

        headings = []
        for name in ("draft", "ready", "running"):
            column = self.col(name)
            column.wait_for(state="visible", timeout=5000)
            self.assertEqual(name, column.get_attribute("data-nv-col"))
            heading = column.locator("h3.nv-col-title").first.inner_text().strip()
            self.assertTrue(heading, "Spalte %s hat keine Überschrift" % name)
            headings.append(heading)
        self.assertEqual(3, len(set(headings)),
                         "Die drei Board-Spalten sind nicht unterscheidbar")

        for tid, column in (("AP3", "draft"), ("AP1", "ready"),
                            ("B1", "ready"), ("W1", "ready"),
                            ("AP2", "running")):
            with self.subTest(ticket=tid, column=column):
                self.assertTrue(
                    self.col(column).locator(
                        "article[data-nv-ticket='%s']" % tid).first.is_visible(),
                    "%s liegt nicht in Spalte %s" % (tid, column))
                self.assertEqual(1, self.page.locator(
                    "article[data-nv-ticket='%s']" % tid).count(),
                    "%s erscheint mehrfach" % tid)
        self.wait_until(lambda: not self.card("AP4").is_visible(),
                        message="Erledigtes Ticket ist standardmäßig sichtbar")
        self.assert_clean_page()

    def test_02_card_badges_actions_and_full_title(self):
        """Kachelvertrag: Badges nur bei zutreffendem Status, Details/Resume.

        Vorbedingung: eine lange Titelzeile je Zustand. Aktion: Work öffnen,
        Details der langen Karte klicken. Erwartung: Running/Blocked/
        Ready-for-Merge-Badges nur an den passenden Karten; Details überall,
        Resume bei in-progress/blocked/waiting-merge; Titel mit Ellipsis
        gekürzt, vollständiger Titel in der Detailansicht.
        """
        long_title = "Sehr langer Titel für die Ellipsis-Prüfung im Board GH56"
        self.write_store([
            ticket("AP3", "Draft ohne Status"),
            ticket("AP1", "Ready ohne Status"),
            ticket("AP2", "Läuft gerade", state="in-progress"),
            ticket("B1", "Blockierter Bug", type="bug", state="blocked"),
            ticket("W1", "Wartet auf Merge", state="waiting-merge"),
            ticket("AP5", long_title),
        ])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)

        badge_terms = {
            "AP2": ("running", "in progress"),
            "B1": ("blocked", "blockiert"),
            "W1": ("ready for merge", "wartet auf merge"),
        }
        for tid, terms in badge_terms.items():
            with self.subTest(badge=tid):
                text = self.card(tid).inner_text().lower()
                self.assertTrue(any(term in text for term in terms),
                                "%s zeigt kein passendes Status-Badge" % tid)
        for tid in ("AP3", "AP1", "AP5"):
            text = self.card(tid).inner_text().lower()
            for terms in badge_terms.values():
                self.assertFalse(any(term in text for term in terms),
                                 "%s zeigt ein nicht zutreffendes Badge" % tid)

        for tid in ("AP3", "AP1", "AP2", "B1", "W1", "AP5"):
            self.assertEqual(1, self.card(tid).locator(
                "button[data-nv-action='ticket-details']").count(),
                "%s hat keinen Details-Button" % tid)
        for tid in ("AP3", "AP1", "AP5"):
            self.assertEqual(0, self.card(tid).locator(
                "button[data-nv-action='ticket-resume']").count(),
                "%s bietet unzulässig Resume an" % tid)
        for tid in ("AP2", "B1", "W1"):
            self.assertGreaterEqual(self.card(tid).locator(
                "button[data-nv-action='ticket-resume']").count(), 1,
                "%s bietet kein Resume an" % tid)

        title_node = self.card("AP5").locator(".nv-ticket-title").first
        style = title_node.evaluate(
            "e => { const s = getComputedStyle(e);"
            " return {overflow: s.overflow, ellipsis: s.textOverflow}; }")
        self.assertIn(style["overflow"], ("hidden", "clip"),
                      "Der Kredititel ist nicht auf Platzmangel gekürzt")
        self.assertEqual("ellipsis", style["ellipsis"],
                         "Der Kartentitel hat keine Ellipsis")

        self.card("AP5").locator(
            "button[data-nv-action='ticket-details']").first.click()
        detail = self.page.locator("[data-nv-ticket-detail='AP5']").first
        detail.wait_for(state="visible", timeout=5000)
        self.assertIn(long_title, detail.inner_text(),
                      "Die Detailansicht zeigt nicht den vollständigen Titel")
        self.assert_clean_page()

    def test_03_drag_draft_to_ready_updates_state(self):
        """AP3 Hinrichtung: Draft → Ready setzt state=open und verschiebt die Karte.

        Vorbedingung: AP3 in draft. Aktion: HTML5-Drag auf die Ready-Spalte.
        Erwartung: Store state=open; Karte in der Ready-Spalte.
        """
        self.write_store([
            ticket("AP3", "Nur Entwurf", state="draft"),
            ticket("AP1", "Bereit zum Start"),
        ])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        self.assertTrue(self.drag_ticket("AP3", "ready"),
                        "Die Draft-Karte ist nicht dragbar")

        self.wait_until(lambda: self.read_store()["AP3"]["state"] == "open",
                        message="DnD Draft→Ready hat nicht state=open gespeichert")
        self.wait_until(
            lambda: self.col("ready").locator(
                "article[data-nv-ticket='AP3']").count() == 1,
            message="AP3 ist in der UI nicht in die Ready-Spalte gewechselt")
        self.assert_clean_page()

    def test_04_drag_ready_to_draft_updates_state(self):
        """AP3 Rückrichtung: Ready → Draft setzt state=draft.

        Vorbedingung: AP1 in Ready. Aktion: HTML5-Drag auf die Draft-Spalte.
        Erwartung: Store state=draft; Karte in der Draft-Spalte.
        """
        self.write_store([
            ticket("AP3", "Nur Entwurf", state="draft"),
            ticket("AP1", "Bereit zum Start"),
        ])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        self.assertTrue(self.drag_ticket("AP1", "draft"),
                        "Die Ready-Karte ist nicht dragbar")

        self.wait_until(lambda: self.read_store()["AP1"]["state"] == "draft",
                        message="DnD Ready→Draft hat nicht state=draft gespeichert")
        self.wait_until(
            lambda: self.col("draft").locator(
                "article[data-nv-ticket='AP1']").count() == 1,
            message="AP1 ist in der UI nicht in die Draft-Spalte gewechselt")
        self.assert_clean_page()

    def test_05_drag_shows_ghost_and_drop_marker(self):
        """DnD-Feedback: Geist + Einfügemarke während des Ziehens.

        Vorbedingung: mind. eine Draft- und eine Ready-Karte. Aktion: dragstart
        und dragover ohne drop, danach dragend. Erwartung: Ghost und Drop-
        marker sichtbar und nach dragend wieder entfernt; Status unverändert.
        """
        self.write_store([
            ticket("AP3", "Nur Entwurf", state="draft"),
            ticket("AP1", "Bereit zum Start"),
        ])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        self.assertTrue(self.drag_ticket("AP3", "ready", drop=False))

        ghost = self.page.locator("div[data-nv-board-ghost]").first
        marker = self.page.locator("div[data-nv-drop-marker]").first
        self.assertEqual(1, ghost.count(), "Kein Drag-Ghost angezeigt")
        self.assertTrue(ghost.is_visible(), "Der Drag-Ghost ist nicht sichtbar")
        self.assertEqual(1, marker.count(), "Keine Drop-Zielmarke angezeigt")
        self.assertTrue(marker.is_visible(), "Die Drop-Zielmarke ist nicht sichtbar")
        self.assertEqual("draft", self.read_store()["AP3"]["state"],
                         "Ein dragover ohne drop darf nichts speichern")

        self.end_drag("AP3")
        self.wait_until(
            lambda: self.page.locator("div[data-nv-board-ghost]").count() == 0
            and self.page.locator("div[data-nv-drop-marker]").count() == 0,
            message="Drag-Feedback bleibt nach dragend zurück")

    def test_06_failed_state_change_rolls_back(self):
        """DnD-Rollback: fehlgeschlagener Request stellt den Ursprung wieder her.

        Vorbedingung: AP3 in draft; /api/ticket antwortet mit einem Fehler.
        Aktion: Drag Draft→Ready. Erwartung: Karte bleibt in Draft, Store bleibt
        unverändert (optimistische Anzeige wird zurückgerollt).
        """
        self.write_store([
            ticket("AP3", "Nur Entwurf", state="draft"),
            ticket("AP1", "Bereit zum Start"),
        ])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        calls = []
        failed = "**/api/ticket"

        def fail_route(route):
            calls.append(route.request.post_data)
            route.fulfill(status=500, content_type="application/json",
                          body='{"ok": false, "message": "simulierter Fehler"}')

        self.page.route(failed, fail_route)
        try:
            self.drag_ticket("AP3", "ready")
            self.wait_until(lambda: len(calls) >= 1,
                            message="Der Statuswechsel wurde nicht gesendet")
            self.wait_until(
                lambda: self.col("draft").locator(
                    "article[data-nv-ticket='AP3']").count() == 1,
                message="Die Karte wurde nach dem Fehler nicht zurückgerollt")
        finally:
            self.page.unroute(failed, fail_route)
        self.assertEqual("draft", self.read_store()["AP3"]["state"],
                         "Ein fehlgeschlagener Wechsel darf nicht speichern")

    def test_07_vertical_board_reorder_persists(self):
        """AP4 Board: vertikale Reihenfolge = Priorität, gespeichert.

        Vorbedingung: drei Ready-Karten. Aktion: oberste Karte per DnD hinter
        die beiden anderen. Erwartung: DOM-Reihenfolge kippt und /api/priority
        enthält die neue Reihenfolge (auch nach Reload).
        """
        self.write_store([
            ticket("AP1", "Erste", priority=""),
            ticket("AP2", "Zweite", priority=""),
            ticket("AP3", "Dritte", priority=""),
        ])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        ids_before = self.dom_card_order("ready")
        self.assertGreaterEqual(len(ids_before), 3,
                                "Die Ready-Spalte zeigt nicht drei Karten")
        first, second = ids_before[0], ids_before[1]

        self.assertTrue(self.drag_ticket(first, "ready", target_index=2),
                        "Vertikales DnD innerhalb der Spalte funktioniert nicht")

        self.wait_until(
            lambda: self.dom_card_order("ready")[:1] == [second],
            message="Die DOM-Reihenfolge im Board hat sich nicht geändert")
        self.wait_until(
            lambda: [x for x in self.stored_priority() if x in ids_before][:1]
            == [second],
            message="Die neue Reihenfolge wurde nicht in /api/priority gespeichert")
        expected = [x for x in self.stored_priority() if x in ids_before]
        self.assertEqual(expected, self.dom_card_order("ready"),
                         "Anzeige und gespeicherte Priorität weichen ab")

        self.page.reload()
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        self.board().wait_for(state="visible", timeout=5000)
        self.assertEqual(expected, self.dom_card_order("ready"),
                         "Die Reihenfolge ging nach dem Reload verloren")
        self.assert_clean_page()

    def test_08_priority_strip_keyboard_reorder_persists(self):
        """AP4 Tastatur: ↑/↓ der Priorisierung ändert und speichert Reihenfolge.

        GH-67: Die separate Priorisierungsansicht existiert nur auf kleinen
        Bildschirmen. Deshalb läuft dieser Fall jetzt mit 600x800 statt auf dem
        Desktop-Board (dort gibt es keinen Strip mehr). Die Tastaturpriorisierung
        selbst bleibt unverändert Gegenstand der Abnahme.

        Vorbedingung: zwei Ready-Tickets, Viewport 600x800. Aktion:
        priority-down der ersten Strip-Zeile. Erwartung: Strip und
        /api/priority kippen übereinstimmend.
        """
        self.write_store([
            ticket("AP1", "Ein AP", priority=""),
            ticket("AP2", "Zwei AP", priority=""),
        ])
        self.goto_work(viewport={"width": 600, "height": 800})
        strip = self.strip()
        strip.wait_for(state="visible", timeout=5000)

        def strip_order():
            return strip.locator("[data-nv-priority-id]").evaluate_all(
                "els => els.map(e => e.getAttribute('data-nv-priority-id'))")

        ids_before = strip_order()
        self.assertGreaterEqual(len(ids_before), 2)
        order_before = self.stored_priority()
        first, second = ids_before[0], ids_before[1]

        strip.locator(
            "[data-nv-priority-id='%s'] button[data-nv-action='priority-down']"
            % first).first.click()
        self.wait_until(lambda: strip_order()[:1] == [second],
                        message="Die Tastaturpriorisierung ändert die Anzeige nicht")
        self.wait_until(lambda: [x for x in self.stored_priority()
                                 if x in ids_before] != order_before,
                        message="Die Tastaturpriorisierung wurde nicht gespeichert")
        self.assertEqual(second, [x for x in self.stored_priority()
                                  if x in ids_before][0],
                         "Gespeicherte und angezeigte Reihenfolge weichen ab")

    # ------------------------------------------------------- Filter & Suche
    def test_09_state_chips_cover_all_states_and_reset(self):
        """AP5: State-Filter für draft/ready/running, aktiv erkennbar, resetbar.

        GH-67: Der Schnellfilter „Closed“/„done“ entfällt; die Sichtbarkeit
        erledigter Tickets wird ausschließlich über „Show done“ gesteuert.
        Deshalb prüft dieser Fall die drei verbleibenden Chips und anschließend
        den Show-done-Schalter statt eines done-Chips.

        Vorbedingung: je ein Ticket in draft/open/in-progress/done. Aktion:
        State-Chips einzeln klicken und erneut klicken, danach Show done.
        Erwartung: genau der gefilterte Status bleibt sichtbar, aria-pressed
        markiert den aktiven Chip, zweiter Klick setzt zurück; done erscheint
        nur nach Show done.
        """
        self.write_store([
            ticket("AP3", "Nur Entwurf", state="draft"),
            ticket("AP1", "Bereit zum Start"),
            ticket("AP2", "Läuft gerade", state="in-progress"),
            ticket("AP4", "Fertig", state="done", commit="abcdef1",
                   test="test_ap4"),
        ])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        cases = (
            ("draft", "AP3", ("AP1", "AP2", "AP4")),
            ("ready", "AP1", ("AP3", "AP2", "AP4")),
            ("running", "AP2", ("AP3", "AP1", "AP4")),
        )
        for state, shown, hidden in cases:
            with self.subTest(state=state):
                chip = self.page.locator(
                    "button[data-nv-work-state='%s']" % state).first
                chip.wait_for(state="visible", timeout=5000)
                chip.click()
                self.wait_until(
                    lambda: chip.get_attribute("aria-pressed") == "true",
                    message="Chip %s ist nicht als aktiv markiert" % state)
                self.assertTrue(self.card(shown).is_visible(),
                                "%s soll bei Chip %s sichtbar sein" % (shown, state))
                for tid in hidden:
                    self.assertFalse(self.card(tid).is_visible(),
                                     "%s soll bei Chip %s verborgen sein"
                                     % (tid, state))
                chip.click()
                self.wait_until(
                    lambda: chip.get_attribute("aria-pressed") != "true",
                    message="Chip %s lässt sich nicht zurücksetzen" % state)
                self.assertTrue(self.card("AP3").is_visible()
                                or state == "draft",
                                "Zurücksetzen stellt die Draft-Karte nicht wieder her")
        self.assertEqual(0, self.page.locator(
            "button[data-nv-work-state='done']").count(),
            "Es gibt noch einen done-Schnellfilter")
        self.wait_until(lambda: not self.card("AP4").is_visible(),
                        message="Erledigte sind nicht standardmäßig verborgen")
        self.show_done()
        self.wait_until(lambda: self.card("AP4").is_visible(),
                        message="Show done blendet erledigte Tickets nicht ein")

    def test_10_search_filters_board_and_can_be_cleared(self):
        """AP5 Suche: Treffer bleiben, Nicht-Treffer verschwinden, Reset.

        Vorbedingung: zwei unterscheidbare Titel. Aktion: Suchfeld füllen und
        leeren. Erwartung: nur die passende Karte sichtbar; nach Leeren wieder
        beide.
        """
        self.write_store([
            ticket("AP1", "Alpha Suchziel GH56"),
            ticket("AP2", "Beta ganz anderes Ziel"),
        ])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        search = self.page.locator("input[data-nv-work-search]").first
        search.wait_for(state="visible", timeout=5000)
        search.fill("Alpha")
        self.wait_until(
            lambda: self.card("AP1").is_visible()
            and not self.card("AP2").is_visible(),
            message="Die Suche filtert die Board-Karten nicht")
        self.assertEqual("Alpha", search.input_value(),
                         "Der aktive Suchfilter ist nicht erkennbar")
        search.fill("")
        self.wait_until(
            lambda: self.card("AP1").is_visible()
            and self.card("AP2").is_visible(),
            message="Das Leeren der Suche stellt beide Karten nicht wieder her")

    # ------------------------------------------------------- Geschlossene
    def test_11_done_hidden_toggle_and_not_editable(self):
        """AP9: done standardmäßig verborgen, einblendbar, nicht bearbeitbar.

        Vorbedingung: ein erledigtes Ticket mit Nachweis. Aktion: Work öffnen,
        „Erledigte anzeigen“ klicken, Karte anklicken. Erwartung: zunächst
        verborgen, danach sichtbar; Detailansicht bietet keine Editieraktion
        und keine Felder; Backend weigert den Zustandswechsel.
        """
        self.write_store([
            ticket("AP4", "Fertiges Paket", state="done",
                   commit="abcdef1", test="test_ap4"),
        ])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        self.wait_until(lambda: not self.card("AP4").is_visible(),
                        message="Erledigtes Ticket ist standardmäßig sichtbar")

        self.show_done()
        self.wait_until(lambda: self.card("AP4").is_visible(),
                        message="Erledigtes Ticket lässt sich nicht einblenden")
        self.card("AP4").locator(
            "button[data-nv-action='ticket-details']").first.click()
        detail = self.page.locator("[data-nv-ticket-detail='AP4']").first
        detail.wait_for(state="visible", timeout=5000)
        self.assertEqual(0, detail.locator(
            "[data-nv-action='ticket-edit']").count(),
            "Ein erledigtes Ticket bietet Bearbeiten an")
        self.assertEqual(0, detail.locator("[data-nv-field]").count(),
                         "Ein erledigtes Ticket enthält bearbeitbare Felder")
        status, body = self.api_json("/api/ticket", "POST", {
            "name": PROJECT, "action": "state", "id": "AP4", "state": "draft"})
        self.assertEqual(200, status)
        self.assertFalse(json.loads(body).get("ok", True),
                         "Das Backend erlaubt unzulässig die Wiedereröffnung")
        self.assertEqual("done", self.read_store()["AP4"]["state"])

    def test_12_close_requires_confirmation(self):
        """AP9 doppelte Absicherung: Rückfrage; Abbruch ändert nichts.

        Vorbedingung: offenes Ticket AP1. Aktion: close anklicken, Dialog
        abbrechen, erneut anklicken und bestätigen. Erwartung: Dialog mit
        klarer Rückfrage; nach Abbruch bleibt der Zustand unverändert (open,
        B1: der Editor ändert den Zustand nicht mehr); nach Bestätigung
        state=done und die Karte ist standardmäßig verborgen.
        """
        self.write_store([ticket("AP1", "Abschlusskandidat GH56")])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        self.card("AP1").locator(
            "button[data-nv-action='ticket-details']").first.click()
        self.page.locator("[data-nv-ticket-detail='AP1']").first.wait_for(
            state="visible", timeout=5000)
        self.dialog_policy = [False, True]

        def close_button():
            return self.page.locator(
                "button[data-nv-action='ticket-close'], "
                "button[data-nv-action='package-close']").first

        if close_button().count() == 0:
            self.page.locator(
                "[data-nv-ticket-detail='AP1'] "
                "button[data-nv-action='ticket-edit']").first.click()
        close = close_button()
        close.wait_for(state="visible", timeout=5000)
        close.click()
        self.assertEqual(1, len(self.dialogs),
                         "Schließen fragt nicht per Bestätigungsdialog nach")
        self.assertTrue(self.dialogs[0].strip(),
                        "Der Bestätigungsdialog enthält keine Rückfrage")
        self.assertEqual("open", self.read_store()["AP1"]["state"],
                         "Abbrechen der Rückfrage hat trotzdem geschlossen "
                         "oder der Editor hat den Zustand verändert")

        close_button().click()
        self.assertEqual(2, len(self.dialogs),
                         "Der zweite Schließen-Versuch fragt nicht erneut nach")
        self.wait_until(lambda: self.read_store()["AP1"]["state"] == "done",
                        message="Bestätigtes Schließen speichert state=done nicht")
        self.wait_until(lambda: not self.card("AP1").is_visible(),
                        message="Geschlossene Karte bleibt ohne Toggle sichtbar")

    def test_13_copy_done_ticket_creates_draft(self):
        """AP10: Kopie eines erledigten Tickets wird neues Draft-Ticket.

        Vorbedingung: ein erledigtes Ticket. Aktion: Karte einblenden, copy
        anklicken, Editor speichern. Erwartung: neuer Eintrag mitstate=draft
        und übernommenem Titel; das Original bleibt unverändert erledigt.
        """
        self.write_store([
            ticket("AP4", "Fertiges Kapitel", state="done",
                   description="Beschreibung der Kopie", commit="abcdef1",
                   test="test_ap4"),
        ])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        self.show_done()
        self.wait_until(lambda: self.card("AP4").is_visible(),
                        message="Die erledigte Karte ist nicht einblendbar")
        copy = self.page.locator("button[data-nv-action='ticket-copy']").first
        if copy.count() == 0:
            self.card("AP4").locator(
                "button[data-nv-action='ticket-details']").first.click()
            self.page.locator("[data-nv-ticket-detail='AP4']").first.wait_for(
                state="visible", timeout=5000)
        copy = self.page.locator("button[data-nv-action='ticket-copy']").first
        copy.wait_for(state="visible", timeout=5000)
        copy.click()
        editor = self.editor()
        editor.wait_for(state="visible", timeout=5000)
        self.assertIn("Fertiges Kapitel", editor.locator(
            "input[data-nv-field='title']").first.input_value(),
            "Der Editor ist nicht mit dem Titel des Originals vorbefüllt")
        editor.locator("button[data-nv-action='ticket-save']").first.click()

        self.wait_until(
            lambda: len([r for r in self.read_store().values()
                         if r["id"] != "AP4"]) == 1,
            message="Die Kopie wurde nicht als neues Ticket gespeichert")
        new = [r for r in self.read_store().values() if r["id"] != "AP4"][0]
        self.assertEqual("draft", new["state"],
                         "Die Kopie eines erledigten Tickets ist kein Draft")
        self.assertIn("Fertiges Kapitel", new["title"],
                      "Die Kopie hat den Titel nicht übernommen")
        self.assertEqual("done", self.read_store()["AP4"]["state"],
                         "Das Original wurde durch das Kopieren verändert")

    # ------------------------------------------------------- Neue Tickets
    def test_14_new_ticket_starts_draft_and_is_visible(self):
        """AP11: Neues Ticket ist Draft und erscheint sofort in der Draft-Spalte.

        Vorbedingung: leerer Ticketspeicher, Work geöffnet. Aktion: Paket
        anlegen, Titel/Beschreibung füllen, speichern. Erwartung: genau ein
        neuer Eintrag mit state=draft und eine Karte in der Draft-Spalte.
        """
        self.write_store([])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        editor = self.open_editor()
        editor.locator("input[data-nv-field='title']").first.fill(
            "Neues Paket GH56")
        editor.locator("textarea[data-nv-field='description']").first.fill(
            "Erstes Board-Ticket")
        state_field = editor.locator("[data-nv-field='state']").first
        if state_field.count():
            self.assertEqual("draft", state_field.input_value(),
                             "Der Editor bietet für neue Tickets nicht Draft an")
        editor.locator("button[data-nv-action='ticket-save']").first.click()

        self.wait_until(
            lambda: any(r["title"] == "Neues Paket GH56"
                        for r in self.read_store().values()),
            message="Das neue Ticket wurde nicht gespeichert")
        rows = [r for r in self.read_store().values()
                if r["title"] == "Neues Paket GH56"]
        self.assertEqual(1, len(rows), "Das neue Ticket ist nicht eindeutig")
        self.assertEqual("draft", rows[0]["state"],
                         "Ein neues Ticket muss state=draft haben")
        self.wait_until(
            lambda: self.col("draft").locator(
                "article[data-nv-ticket='%s']" % rows[0]["id"]).count() == 1,
            message="Das neue Ticket erscheint nicht in der Draft-Spalte")
        self.assertEqual("draft", self.card(rows[0]["id"]).get_attribute(
            "data-nv-state"))

    # ------------------------------------------------------- Sidebar / Editor
    def test_15_editor_default_width_and_full_height(self):
        """AP1: Standardmäßig breite Sidebar über die volle Bildschirmhöhe.

        Vorbedingung: Desktop-Viewport 1500x1100. Aktion: Paket anlegen.
        Erwartung: Editor-Aside mindestens 400 px breit (Testschwelle für
        „deutlich breiter“) und mindestens 95 % der Viewporthöhe, oben bündig;
        dieselben Kernfelder/Aktionen wie in der Desktop-Sidebar.
        """
        self.write_store([])
        self.goto_work()
        editor = self.open_editor()
        box = editor.bounding_box()
        self.assertIsNotNone(box, "Der Editor ist nicht positioniert")
        self.assertGreaterEqual(box["width"], 400,
                                "Die Editor-Sidebar ist nicht deutlich breiter")
        self.assertGreaterEqual(box["height"], 1100 * 0.95,
                                "Die Editor-Sidebar nimmt nicht die volle Höhe ein")
        self.assertLessEqual(box["y"], 4,
                             "Die Editor-Sidebar beginnt nicht oben")
        for hook in ("input[data-nv-field='title']",
                     "textarea[data-nv-field='description']",
                     "button[data-nv-action='ticket-save']",
                     "button[data-nv-action='ticket-cancel']"):
            self.assertGreaterEqual(editor.locator(hook).count(), 1,
                                    "Dem Editor fehlt %s" % hook)

    def test_16_resized_editor_width_persists_during_session(self):
        """AP1: per Drag verstellbare Breite bleibt in der Session erhalten.

        Vorbedingung: Desktop-Viewport, Editor offen. Aktion: linken Rand
        nach links ziehen, zu den Einstellungen und zurück navigieren, Editor
        erneut öffnen. Erwartung: vergrößerte Breite bleibt (ohne Reload).
        """
        self.write_store([])
        self.goto_work()
        editor = self.open_editor()
        before = editor.bounding_box()["width"]
        box = editor.bounding_box()
        start_x, start_y = box["x"] + 1, box["y"] + box["height"] / 2
        self.page.mouse.move(start_x, start_y)
        self.page.mouse.down()
        self.page.mouse.move(start_x - 60, start_y, steps=4)
        self.page.mouse.move(start_x - 140, start_y, steps=4)
        self.page.mouse.up()
        self.page.wait_for_timeout(250)
        resized = self.editor().bounding_box()["width"]
        self.assertGreaterEqual(resized, before + 80,
                                "Die Editor-Breite lässt sich nicht per Drag ändern")

        self.page.goto(self.base + "/#/settings")
        self.page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=25000)
        self.page.goto(self.base + "/#/project/" + PROJECT + "/work")
        self.page.locator("section[data-nv-ppanel='work']").wait_for(
            state="visible", timeout=20000)
        again = self.open_editor().bounding_box()["width"]
        self.assertLessEqual(abs(again - resized), 6,
                             "Die eingestellte Breite ging beim Navigieren verloren")

    def test_17_consistent_spacing_grid(self):
        """AP12: gemeinsames Spacing-Raster für Board, Filter und Editor.

        Vorbedingung: Desktop-Work mit Karte und geöffnetem Editor. Aktion:
        berechnete Abstände der Komponenten auslesen. Erwartung: zentrale
        --nv-space-* Token sind vorhanden; alle gemessenen Padding-/Gap-Werte
        liegen auf einem 4px-Raster (gemeinsames Grundraster).
        """
        self.write_store([ticket("AP1", "Spacing-Karte")])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        self.open_editor()
        values = self.page.evaluate("""() => {
          const root = getComputedStyle(document.documentElement);
          const tokens = ['--nv-space-1', '--nv-space-2', '--nv-space-3']
            .map(k => root.getPropertyValue(k).trim());
          const pick = (sel, prop) => {
            const node = document.querySelector(sel);
            return node ? getComputedStyle(node)[prop] : '';
          };
          return {
            tokens: tokens,
            values: [
              pick('article[data-nv-ticket]', 'padding'),
              pick('article[data-nv-col] [data-nv-col-cards]', 'gap'),
              pick('[data-nv-filter-bar]', 'gap'),
              pick('aside[data-nv-ticket-editor]', 'padding')
            ]
          };
        }""")
        self.assertGreaterEqual(len([t for t in values["tokens"] if t]), 2,
                                "Es fehlen zentrale --nv-space-* Design-Tokens")
        measured = []
        for value in values["values"]:
            if not value or value == "normal":
                continue
            # getComputedStyle liefert z. B. "12px" bzw. "8px 12px"; die
            # Einheit muss vor der Numerik entfernt werden.
            numbers = [float(x[:-2]) for x in value.split()
                       if x.endswith("px")]
            self.assertTrue(numbers, "Kein px-basiertes Spacing: " + value)
            for number in numbers:
                self.assertEqual(0, number % 4,
                                 "Abstand liegt nicht im 4px-Raster: " + value)
                measured.append(number)
        self.assertTrue(measured, "Es wurden keine Abstände gemessen")
        self.assertLessEqual(len(set(measured)), 4,
                             "Die Komponenten verwenden kein gemeinsames Raster")

    # ------------------------------------------------------- Mobile
    def test_18_mobile_shows_list_instead_of_board(self):
        """AP6: Smartphone zeigt Liste statt Kanban-Board.

        Vorbedingung: Tickets in mehreren Zuständen, Viewport 600x800.
        Aktion: Work öffnen. Erwartung: kein Board, eine Liste mit allen
        nicht erledigten Karten und den bestehenden Schnellfiltern.
        """
        self.write_store([
            ticket("AP3", "Nur Entwurf", state="draft"),
            ticket("AP1", "Bereit zum Start"),
            ticket("AP2", "Läuft gerade", state="in-progress"),
        ])
        self.goto_work(viewport={"width": 600, "height": 800})
        self.page.wait_for_timeout(500)
        self.assertEqual(0, self.page.locator("div[data-nv-board]").count(),
                         "Auf Mobile wird trotzdem ein Board angezeigt")
        view = self.page.locator("div[data-nv-work-list]").first
        view.wait_for(state="visible", timeout=5000)
        for tid in ("AP3", "AP1", "AP2"):
            self.assertTrue(self.card(tid).is_visible(),
                            "%s fehlt in der mobilen Liste" % tid)
        self.assertEqual(1, self.page.locator(
            "input[data-nv-work-search]").count(),
            "Die mobile Liste hat keine Suche/Schnellfilter")

    def test_19_mobile_priority_view_ready_only(self):
        """AP7: mobile Priorisierung zeigt ausschließlich Ready-Tickets.

        Vorbedingung: Draft, Ready, Running. Aktion: mobile Work-Ansicht.
        Erwartung: die Priorisierungszeilen enthalten nur die Ready-ID.
        """
        self.write_store([
            ticket("AP3", "Nur Entwurf", state="draft"),
            ticket("AP1", "Bereit zum Start"),
            ticket("AP2", "Läuft gerade", state="in-progress"),
        ])
        self.goto_work(viewport={"width": 600, "height": 800})
        strip = self.strip()
        strip.wait_for(state="visible", timeout=5000)
        ids = strip.locator("[data-nv-priority-id]").evaluate_all(
            "els => els.map(e => e.getAttribute('data-nv-priority-id'))")
        self.assertEqual(["AP1"], ids,
                         "Die mobile Priorisierung zeigt fremde Zustände")

    def test_20_mobile_fullscreen_editor_matches_desktop(self):
        """AP8: mobile Bearbeitung ist Vollbild und enthält die Kernaktionen.

        Vorbedingung: Viewport 600x800. Aktion: Paket anlegen. Erwartung:
        Editor-Overlay bedeckt mindestens 95 % von Breite und Höhe, ist keine
        schmale Sidebar und bietet titles/description sowie save/cancel wie
        die Desktop-Sidebar.
        """
        self.write_store([])
        self.goto_work(viewport={"width": 600, "height": 800})
        editor = self.open_editor()
        box = editor.bounding_box()
        self.assertIsNotNone(box)
        self.assertGreaterEqual(box["width"], 600 * 0.95,
                                "Der mobile Editor ist kein Vollbild (Breite)")
        self.assertGreaterEqual(box["height"], 800 * 0.95,
                                "Der mobile Editor ist kein Vollbild (Höhe)")
        for hook in ("input[data-nv-field='title']",
                     "textarea[data-nv-field='description']",
                     "button[data-nv-action='ticket-save']",
                     "button[data-nv-action='ticket-cancel']"):
            self.assertGreaterEqual(editor.locator(hook).count(), 1,
                                    "Dem mobilen Editor fehlt %s" % hook)

    def test_21_mobile_filters_work_on_list(self):
        """AP5: Schnellfilter und Suche wirken auch auf der mobilen Liste.

        Vorbedingung: Paket und Bug, Viewport 600x800. Aktion: Suche füllen,
        Bug-Chip klicken, Alle-Chip klicken. Erwartung: jeweils nur passende
        Karten sichtbar; Reset stellt beide wieder her.
        """
        self.write_store([
            ticket("AP1", "Alpha Paket"),
            ticket("B1", "Beta Bug", type="bug"),
        ])
        self.goto_work(viewport={"width": 600, "height": 800})
        view = self.page.locator("div[data-nv-work-list]").first
        view.wait_for(state="visible", timeout=5000)

        search = self.page.locator("input[data-nv-work-search]").first
        search.fill("Alpha")
        self.wait_until(
            lambda: self.card("AP1").is_visible()
            and not self.card("B1").is_visible(),
            message="Die Suche filtert die mobile Liste nicht")
        search.fill("")

        self.page.locator("button[data-nv-work-kind='bug']").first.click()
        self.wait_until(
            lambda: self.card("B1").is_visible()
            and not self.card("AP1").is_visible(),
            message="Der Bug-Schnellfilter wirkt auf der mobilen Liste nicht")
        self.page.locator("button[data-nv-work-kind='all']").first.click()
        self.wait_until(
            lambda: self.card("B1").is_visible()
            and self.card("AP1").is_visible(),
            message="Der Filter lässt sich auf Mobile nicht zurücksetzen")


if __name__ == "__main__":
    unittest.main()
