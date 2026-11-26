"""Arbeitsoberfläche: Board, Feedback, Anlegen/Bearbeiten/Löschen, Priorität und Formularfehler.

Aufruf: python3 -m unittest tests.browser.test_work_ui -v
"""


# ===========================================================================
# Browserabnahme, Meilenstein B: Arbeit (Liste, Feedback, Priorisierung)
# ===========================================================================

import http.client
import json
import os
import re
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


# GH-48/GH-56: Tickets liegen maschinenlesbar in .vibe/tickets.json.
TICKETS = [
    ticket("AP-101", "Offenes Paket", description="Noch offen."),
    ticket("AP-102", "Zweites offenes Paket", description="Ebenfalls offen."),
    ticket("AP-103", "Blockiertes Paket", state="blocked",
           description="Wartet auf Freigabe.",
           blocked_reason="externe Freigabe fehlt"),
    ticket("AP-104", "Erledigtes Paket", state="done",
           description="Fertig.", commit="abcdef1", test="test_ap_done"),
]

FEEDBACK = [
    ticket("BUG-7", "Absturz beim Start", type="bug",
           description="Fenster bleibt leer.", commit="1234567",
           test="test_start"),
    ticket("FB-1", "Wunsch für die Oberfläche", type="feedback",
           description="Bitte größere Schaltflächen.", commit="7654321",
           test="test_ui"),
]


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class AP22WorkBrowserTest(unittest.TestCase):
    """Dashboard, Browser und Ticket-/Feedback-Fixtures für das Board."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / PROJECT
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True)
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir(parents=True)

        cls.port = free_port()
        cls.oc_port = free_port()
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
        self.write_store(TICKETS + FEEDBACK)
        (self.project / ".vibe" / "agents.json").unlink(missing_ok=True)
        self.post_language("en")
        self.page_errors = []
        self.dialogs = []
        self.context = self.browser.new_context(
            viewport={"width": 1500, "height": 1100})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))
        self.page.on("dialog", self._on_dialog)

    def _on_dialog(self, dialog):
        self.dialogs.append(dialog.type + ": " + dialog.message)
        dialog.accept()

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
            response = conn.getresponse()
            return response.status, response.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def api_json(self, path):
        return self.page.evaluate(
            """async (path) => {
              const response = await fetch(path, {headers: {'Accept': 'application/json'}});
              return await response.json();
            }""", path)

    def wait_api(self, path, predicate, timeout=20, message=None):
        """Pocht eine API-Antwort, bis ``predicate`` sie akzeptiert."""
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                last = self.api_json(path)
            except Exception:  # noqa: BLE001 - Polling darf kurze Fehler sehen
                last = None
            if last is not None and predicate(last):
                return last
            self.page.wait_for_timeout(150)
        self.fail((message or "API-Bedingung nicht erfüllt") + " — zuletzt: "
                  + repr(last))

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_work(self):
        self.boot()
        self.page.goto(self.base + "/#/project/" + PROJECT + "/work")
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        self.page.locator("section[data-nv-ppanel='work']").wait_for(
            state="visible", timeout=20000)
        return self.page.locator("section[data-nv-ppanel='work']")

    def write_store(self, rows):
        (self.project / ".vibe" / "tickets.json").write_text(
            json.dumps({"version": 1, "tickets": rows},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

    def records(self):
        doc = json.loads((self.project / ".vibe" / "tickets.json").read_text(
            encoding="utf-8"))
        return {row["id"]: row for row in doc["tickets"]}

    def ticket_text(self):
        return (self.project / ".vibe" / "tickets.json").read_text(
            encoding="utf-8")

    def feedback_text(self):
        return self.ticket_text()

    def card(self, ticket_id):
        return self.page.locator(
            f"article[data-nv-ticket='{ticket_id}']").first

    def feedback_card(self, ticket_id):
        return self.page.locator(
            f"article[data-nv-feedback-item='{ticket_id}']").first

    def _follows(self, first, second,
                 root="main#nv-main[data-nv-view='project']"):
        """Prüft, ob ``first`` vor ``second`` in DOM-Reihenfolge steht."""
        return self.page.evaluate("""([first, second, rootSel]) => {
            const root = document.querySelector(rootSel);
            const a = root && root.querySelector(first);
            const b = root && root.querySelector(second);
            return !!a && !!b && !!(a.compareDocumentPosition(b) & 4);
        }""", [first, second, root])

    def open_form(self, action):
        self.page.locator(f"[data-nv-action='{action}']").first.click()
        form = self.page.locator("[data-nv-ticket-form]")
        form.wait_for(state="visible", timeout=20000)
        return form

    def fill_form(self, form, title, description=""):
        form.locator("input[data-nv-field='title']").fill(title)
        if description:
            form.locator("textarea[data-nv-field='description']").fill(
                description)

    def save_form(self, form):
        form.locator("[data-nv-action='ticket-save']").click()

    def assert_form_closed(self):
        form = self.page.locator("[data-nv-ticket-form]")
        self.assertTrue(
            form.count() == 0 or not form.first.is_visible(),
            "Das Ticket-Formular bleibt nach dem Abbrechen sichtbar")

    def confirm_if_visible(self):
        """Klickt eine eingebettete Bestätigung, falls die UI eine zeigt."""
        confirm = self.page.locator(
            "button[data-nv-action='ticket-delete-confirm'], "
            "[data-nv-confirm] button").first
        if confirm.count() and confirm.is_visible():
            confirm.click()

    def assert_clean_page(self):
        self.assertEqual(
            [], self.page_errors, "Die Arbeitsansicht erzeugte JavaScript-Fehler")


class BoardTest(AP22WorkBrowserTest):
    def test_columns_and_tickets_follow_the_fixture_states(self):
        """Vorbedingung: Fixtures in allen Zuständen (GH-48-Ticketspeicher).

        GH-56: Die fachliche Absicht — Art, Rohzustand und Kennung jeder
        Karte sowie Filterleiste und Priorisierung — bleibt erhalten; die
        alte F34-Absence des Boards und die alte Liste sind überholt. Neu
        zu prüfen: Board mit drei Spalten und Rohzustand am Kartenattribut.

        GH-82: Erledigte Tickets gehören nicht in die Ready-Spalte; sie
        werden in einem eigenen Raster unterhalb des Boards gezeigt.
        """
        self.open_work()
        self.assertEqual(
            "en", self.page.evaluate("() => document.documentElement.lang"),
            "Die Standardsprache der Oberfläche ist nicht Englisch")
        board = self.page.locator("div[data-nv-board]").first
        board.wait_for(state="visible", timeout=20000)
        for column in ("draft", "ready", "running"):
            self.assertEqual(
                1, board.locator(f"article[data-nv-col='{column}']").count(),
                f"Die Board-Spalte {column} fehlt")
        # GH-108: Die Aktionen stehen im Header, nicht mehr in einer
        # Aktionsleiste der Work-Ansicht. Der Header liegt vor der
        # Filterleiste; danach folgt das Board. GH-67: die Priorisierungs-
        # ansicht liegt auf Desktop nicht im DOM; die Reihenfolge-Prüfung
        # für den Strip erfolgt in den PriorityTest-Fällen bzw. in
        # test_gh67_work_ui.py (mobil).
        self.assertTrue(
            self._follows(
                "[data-nv-hero] [data-nv-action='new-package']",
                "[data-nv-filter-bar]"),
            "Die Header-Aktion steht nicht vor der Filterleiste")
        self.assertEqual(
            0, self.page.locator(
                "section[data-nv-ppanel='work'] div.nv-work-actions").count(),
            "Die entfernte Work-Aktionsleiste existiert noch")
        filter_bar = self.page.locator("[data-nv-filter-bar]").first
        filter_bar.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            1, filter_bar.locator("input[data-nv-work-search]").count(),
            "Die Suchleiste [data-nv-work-search] fehlt in der Filterleiste")
        for kind in ("all", "package", "bug", "feedback"):
            self.assertEqual(
                1, filter_bar.locator(
                    f"button[data-nv-work-kind='{kind}']").count(),
                f"Der Chip data-nv-work-kind='{kind}' fehlt in der Filterleiste")
        # GH-108: „Show done“ steht direkt rechts neben der Suche in der
        # Filterleiste; der Done-Schnellfilter entfällt weiterhin (GH-67).
        self.assertEqual(
            1, filter_bar.locator("[data-nv-work-hide-done]").count(),
            "Show-done fehlt in der Filterleiste")
        self.assertTrue(
            self.page.evaluate("""() => {
              const btn = document.querySelector(
                'button[data-nv-work-hide-done]');
              const prev = btn && btn.previousElementSibling;
              return !!prev && prev.hasAttribute('data-nv-search');
            }"""),
            "Show-done steht nicht direkt rechts neben der Suche")
        for state in ("draft", "ready", "running"):
            self.assertEqual(
                1, filter_bar.locator(
                    f"button[data-nv-work-state='{state}']").count(),
                f"Der Status-Chip {state} fehlt in der Filterleiste")
        self.assertEqual(
            0, filter_bar.locator("button[data-nv-work-state='done']").count(),
            "Der Done-Schnellfilter gibt es nicht mehr")

        self.page.locator("[data-nv-work-hide-done]").first.click()

        expected = {
            "AP-101": ("package", "open", "ready"),
            "AP-102": ("package", "open", "ready"),
            "AP-103": ("package", "blocked", "ready"),
            "BUG-7": ("bug", "open", "ready"),
            "FB-1": ("feedback", "open", "ready"),
        }
        for ticket_id, (kind, state, column) in expected.items():
            with self.subTest(ticket=ticket_id):
                article = board.locator(
                    f"article[data-nv-ticket='{ticket_id}']").first
                self.assertEqual(1, article.count(),
                                 f"{ticket_id} fehlt im Board")
                self.wait_until(
                    lambda: article.is_visible(),
                    message=f"{ticket_id} ist nach dem Einblenden nicht sichtbar")
                self.assertEqual(
                    kind, article.get_attribute("data-nv-kind"),
                    f"{ticket_id} trägt nicht das Art-Badge-Feld {kind!r}")
                self.assertEqual(
                    state, article.get_attribute("data-nv-state"),
                    f"{ticket_id} trägt nicht den Rohstatus {state!r}")
                self.assertEqual(
                    1, board.locator(
                        f"article[data-nv-col='{column}'] "
                        f"article[data-nv-ticket='{ticket_id}']").count(),
                    f"{ticket_id} liegt nicht in Spalte {column}")
                self.assertIn(
                    ticket_id, article.inner_text(),
                    f"Die Karte {ticket_id} zeigt ihre Kennung nicht")
        self.assertEqual(
            0, board.locator("article[data-nv-ticket='AP-104']").count(),
            "Ein erledigtes Ticket liegt wider Erwarten im Board")
        self.assert_clean_page()


class WorkStateOwnershipTest(AP22WorkBrowserTest):
    """Zustandshoheit: erledigte Karten außerhalb des Boards, keine
    Nutzersteuerung für Läufer-Zustände, einheitlicher Dropdown-Stil."""

    def test_completed_tickets_live_in_a_grid_below_the_board(self):
        """Erledigte Tickets stehen nicht in der Ready-Spalte, sondern in
        einem sichtbaren Raster unterhalb des Boards.

        Vorbedingung: ein abgeschlossenes Ticket (AP-104) neben offenen.
        Aktion: Arbeitsansicht öffnen, erledigte Tickets ggf. über den
        Show-done-Schalter einblenden und die Platzierung der Karte im DOM
        prüfen. Erwartung: die Karte liegt außerhalb des Boards, folgt ihm
        im Dokument, ist sichtbar und ihr Container ist ein Raster, das das
        Board selbst nicht enthält.
        """
        self.open_work()
        board = self.page.locator("div[data-nv-board]").first
        board.wait_for(state="visible", timeout=20000)
        toggle = self.page.locator("[data-nv-work-hide-done]")
        if toggle.count() and self.page.locator(
                "article[data-nv-ticket='AP-104']").count():
            toggle.first.click()

        placement = self.page.evaluate("""() => {
            const board = document.querySelector("div[data-nv-board]");
            const card = document.querySelector(
                "article[data-nv-ticket='AP-104']");
            if (!board || !card) return {board: !!board, card: !!card};
            let grid = null;
            for (let node = card.parentElement; node && node !== document.body;
                 node = node.parentElement) {
                if (getComputedStyle(node).display === 'grid'
                    && !node.contains(board)) {
                    grid = node;
                    break;
                }
            }
            return {
                board: true,
                card: true,
                inBoard: board.contains(card),
                afterBoard: !!(board.compareDocumentPosition(card) & 4),
                gridFound: !!grid,
                gridContainsCard: grid ? grid.contains(card) : false,
                gridContainsBoard: grid ? grid.contains(board) : false,
                visible: !card.hasAttribute('hidden')
                    && !!card.getClientRects().length,
            };
        }""")
        self.assertTrue(placement["board"] and placement["card"],
                        "Board oder erledigte Karte fehlt: " + repr(placement))
        self.assertFalse(placement["inBoard"],
                         "Die erledigte Karte steht wider Erwarten im Board "
                         "(Ready-Spalte): " + repr(placement))
        self.assertTrue(placement["afterBoard"],
                        "Die erledigte Karte steht nicht unterhalb des Boards: "
                        + repr(placement))
        self.assertTrue(placement["gridFound"],
                        "Die erledigte Karte liegt in keinem Raster: "
                        + repr(placement))
        self.assertTrue(placement["gridContainsCard"],
                        "Das Raster enthält die erledigte Karte nicht: "
                        + repr(placement))
        self.assertFalse(placement["gridContainsBoard"],
                         "Das Erledigt-Raster enthält auch das Board: "
                         + repr(placement))
        self.assertTrue(placement["visible"],
                        "Die erledigte Karte ist im Raster nicht sichtbar: "
                        + repr(placement))
        self.assert_clean_page()

    def test_detail_offers_no_control_for_in_progress_or_done(self):
        """Nur Entwurf/Bereit sind vom Nutzer setzbar.

        Vorbedingung: ein offenes Paket. Aktion: Detail öffnen und alle
        Zustandssteuerelemente prüfen. Erwartung: die Auswahl bietet weder
        ``in-progress`` noch ``done``, und es gibt keinen Schließen- oder
        Paket-abschließen-Knopf (auch nicht unter einem anderen Label).
        """
        self.open_work()
        self.card("AP-101").click()
        detail = self.page.locator("[data-nv-ticket-detail='AP-101']").first
        detail.wait_for(state="visible", timeout=20000)

        select = detail.locator("select[data-nv-ticket-state-select]")
        self.assertEqual(1, select.count(), "Zustandsauswahl fehlt im Detail")
        values = select.locator("option").evaluate_all(
            "els => els.map(e => e.value)")
        self.assertNotIn("in-progress", values,
                         "Die Auswahl bietet den Läufer-Zustand in-progress")
        self.assertNotIn("done", values,
                         "Die Auswahl bietet den Abschluss-Zustand done")
        self.assertTrue(set(values).issubset({"draft", "open"}),
                        "Die Auswahl bietet unzulässige Zustände: "
                        + repr(values))
        option_labels = " ".join(select.locator("option").all_inner_texts())
        self.assertNotRegex(
            option_labels, r"(?i)in progress|in bearbeitung|geschlossen|done",
            "Ein Optionslabel nennt einen Läufer-Zustand: " + option_labels)

        for action in ("ticket-close", "package-close"):
            self.assertEqual(
                0, detail.locator(
                    f"button[data-nv-action='{action}']").count(),
                f"Der Schließen-Knopf {action} ist noch im Detail vorhanden")
        button_labels = " ".join(detail.locator("button").all_inner_texts())
        self.assertNotRegex(
            button_labels,
            r"(?i)schließen|schliessen|abschließen|abschliessen|close|"
            r"in progress|in bearbeitung",
            "Ein Detail-Knopf bietet einen Läufer-Zustand an: " + button_labels)
        self.assert_clean_page()

    def test_detail_status_select_matches_the_shared_dropdown_style(self):
        """Die Zustandsauswahl im Detail nutzt denselben Stil wie alle
        anderen Vibe-Dropdowns.

        Vorbedingung: offenes Detail und das reguläre Anlageformular.
        Aktion: die berechneten Stile beider Selects vergleichen. Erwartung:
        Rahmen, Innenabstände, Hintergrund, Text und Schrift stimmen überein.
        """
        self.open_work()
        self.card("AP-101").click()
        detail = self.page.locator("[data-nv-ticket-detail='AP-101']").first
        detail.wait_for(state="visible", timeout=20000)
        select = detail.locator("select[data-nv-ticket-state-select]").first
        select.wait_for(state="visible", timeout=20000)
        detail_style = select.evaluate("""el => {
            const style = getComputedStyle(el);
            const keys = ['borderTopWidth', 'borderRightWidth',
                'borderBottomWidth', 'borderLeftWidth', 'borderStyle',
                'borderColor', 'borderRadius', 'paddingTop', 'paddingRight',
                'paddingBottom', 'paddingLeft', 'backgroundColor', 'color',
                'fontFamily', 'fontSize', 'fontWeight'];
            const result = {};
            keys.forEach(key => { result[key] = style[key]; });
            return result;
        }""")

        self.page.keyboard.press("Escape")
        detail.wait_for(state="hidden", timeout=10000)
        self.page.locator("[data-nv-action='new-package']").first.click()
        form = self.page.locator("[data-nv-ticket-form]").first
        form.wait_for(state="visible", timeout=20000)
        reference = form.locator("select[data-nv-field='state']").first
        self.assertEqual(1, reference.count(),
                         "Der Referenz-Dropdown im Formular fehlt")
        reference_style = reference.evaluate("""el => {
            const style = getComputedStyle(el);
            const keys = ['borderTopWidth', 'borderRightWidth',
                'borderBottomWidth', 'borderLeftWidth', 'borderStyle',
                'borderColor', 'borderRadius', 'paddingTop', 'paddingRight',
                'paddingBottom', 'paddingLeft', 'backgroundColor', 'color',
                'fontFamily', 'fontSize', 'fontWeight'];
            const result = {};
            keys.forEach(key => { result[key] = style[key]; });
            return result;
        }""")
        for key in detail_style:
            with self.subTest(property=key):
                self.assertEqual(
                    reference_style[key], detail_style[key],
                    "Der Detail-Dropdown weicht bei " + key + " ab: "
                    + repr(detail_style[key]) + " statt "
                    + repr(reference_style[key]))
        self.assert_clean_page()

    def test_runner_owned_blocked_and_waiting_states_have_no_control(self):
        """Blockierte und wartende Tickets bleiben ohne Zustandsauswahl.

        GH-108 erlaubt ausdrücklich nur, ``in-progress`` über das Detail
        zurückzusetzen. Für ``blocked`` und ``waiting-merge`` gilt weiterhin:
        keine Zustandsauswahl und kein Speichern-Knopf, sondern der
        Läufer-Hinweis; der Speicher bleibt beim Öffnen unverändert.
        Fehlerfall: eine blinde Auswahl sendet einen leeren Wert, den das
        Backend zu ``open`` normalisiert.
        """
        for state in ("blocked", "waiting-merge"):
            with self.subTest(state=state):
                self.write_store([
                    ticket("AP2", "Läuferzustand " + state, state=state),
                ])
                self.open_work()
                self.card("AP2").click()
                detail = self.page.locator(
                    "[data-nv-ticket-detail='AP2']").first
                detail.wait_for(state="visible", timeout=20000)

                self.assertEqual(
                    0, detail.locator(
                        "select[data-nv-ticket-state-select]").count(),
                    "Ein " + state + "-Ticket bietet eine Zustandsauswahl an")
                self.assertEqual(
                    0, detail.locator(
                        "button[data-nv-action='ticket-state-save']").count(),
                    "Ein " + state + "-Ticket bietet einen "
                    "Zustands-Speichern-Knopf an")
                notice = detail.locator("[data-nv-runner-state-notice]")
                self.assertEqual(
                    1, notice.count(),
                    "Ein " + state + "-Ticket zeigt keinen Läufer-Hinweis")
                self.assertTrue(notice.first.is_visible(),
                                "Der Läufer-Hinweis ist nicht sichtbar")
                self.assertEqual(
                    state, self.records()["AP2"]["state"],
                    "Das Öffnen des Details hat den Zustand verändert")
                self.page.keyboard.press("Escape")
                detail.wait_for(state="hidden", timeout=10000)
        self.assert_clean_page()

    def test_detail_can_move_an_in_progress_ticket_back_to_draft(self):
        """GH-108 hebt die GH-82-Sperre für In Progress im Detail auf.

        Vorbedingung: Ticket AP2 in ``in-progress``. Aktion: Detail öffnen,
        ``draft`` wählen und speichern. Erwartung: Die Auswahl bietet draft
        und open, der Speicher wechselt nach draft und die Karte erscheint
        in der Entwurf-Spalte. Blockiert/wartend bleiben dagegen geschützt.
        """
        self.write_store([ticket("AP2", "In Arbeit", state="in-progress")])
        self.open_work()
        self.card("AP2").click()
        detail = self.page.locator("[data-nv-ticket-detail='AP2']").first
        detail.wait_for(state="visible", timeout=20000)

        select = detail.locator("select[data-nv-ticket-state-select]")
        self.assertEqual(
            1, select.count(), "In Progress bietet keine Zustandsauswahl an")
        self.assertEqual(
            0, detail.locator("[data-nv-runner-state-notice]").count(),
            "In Progress zeigt trotz Zustandsauswahl den Läufer-Hinweis")
        values = select.locator("option").evaluate_all(
            "els => els.map(e => e.value)")
        self.assertIn("draft", values)
        self.assertIn("open", values)
        select.select_option("draft")
        detail.locator(
            "button[data-nv-action='ticket-state-save']").click()

        self.wait_until(
            lambda: self.records()["AP2"]["state"] == "draft",
            message="Der Zustandswechsel aus In Progress wurde nicht gespeichert")
        self.wait_until(
            lambda: self.card("AP2").get_attribute("data-nv-state") == "draft",
            message="Die Karte zeigt nach dem Wechsel nicht den Entwurfszustand")
        self.assert_clean_page()

    def test_copying_done_ticket_does_not_suggest_a_used_id(self):
        """Die Kopie einer erledigten Karte schlägt keine vergebene Kennung
        vor.

        Vorbedingung: erledigtes AP1 und offenes AP2 im selben Speicher.
        Aktion: erledigte Karte einblenden, ``ticket-copy`` klicken und den
        ID-Vorschlag des Editors lesen. Erwartung: der Vorschlag ist keine
        bereits vergebene Kennung. Fehlerfall: der Vorschlag wäre AP2, weil
        nur erledigte Einträge als Grundlage dienten.
        """
        self.write_store([
            ticket("AP1", "Erledigt", state="done", commit="abcdef1",
                   test="test_ap1"),
            ticket("AP2", "Offen", state="open"),
        ])
        self.open_work()
        toggle = self.page.locator("[data-nv-work-hide-done]")
        if toggle.count():
            toggle.first.click()
        done_card = self.card("AP1")
        done_card.wait_for(state="visible", timeout=20000)
        copy = done_card.locator("button[data-nv-action='ticket-copy']")
        self.assertEqual(1, copy.count(),
                         "Die erledigte Karte bietet keine Kopie an")
        copy.first.click()

        editor = self.page.locator("aside[data-nv-ticket-editor]").first
        editor.wait_for(state="visible", timeout=20000)
        suggested = editor.locator(
            "input[data-nv-field='id']").first.input_value()
        self.assertNotIn(
            suggested, ("AP1", "AP2"),
            "Der ID-Vorschlag " + repr(suggested)
            + " ist eine bereits vergebene Kennung")
        self.assertEqual("done", self.records()["AP1"]["state"])
        self.assertEqual("open", self.records()["AP2"]["state"])
        self.assert_clean_page()

    def test_done_grid_container_exists_without_done_tickets(self):
        """Das Erledigt-Raster ist als leerer, verborgener Container im DOM,
        damit ein späterer Sync nach ``done`` ihn direkt befüllen kann.

        Vorbedingung: nur offene Tickets. Aktion: Arbeitsansicht öffnen.
        Erwartung: ``section[data-nv-work-done-grid]`` existiert genau
        einmal und ist nicht sichtbar. Fehlerfall: der Container wird erst
        bei vorhandenen erledigten Tickets erzeugt.
        """
        self.write_store([ticket("AP1", "Offen", state="open")])
        self.open_work()
        grid = self.page.locator("section[data-nv-work-done-grid]")
        self.assertEqual(1, grid.count(),
                         "Der Erledigt-Raster-Container fehlt ohne erledigte "
                         "Tickets")
        self.assertFalse(grid.first.is_visible(),
                         "Der leere Erledigt-Raster ist sichtbar")
        self.assert_clean_page()


class FeedbackListTest(AP22WorkBrowserTest):
    def test_feedback_list_shows_kind_badges(self):
        """Vorbedingung: ein Bug und ein gewöhnlicher Feedback-Eintrag.

        Erwartung: F34 — Feedback ist in der gemeinsamen Liste (keine
        ``details[data-nv-feedback-box]`` mehr); die
        ``article[data-nv-feedback-item]`` tragen ``data-nv-kind`` und das
        ``span.nv-kind-badge``-Badge (Bug/Feedback).
        """
        self.open_work()
        # F34: Feedback ist integral in der Liste, keine details-Box mehr.
        self.assertEqual(
            0, self.page.locator("details[data-nv-feedback-box]").count(),
            "F34-Absence: details[data-nv-feedback-box] existiert noch")
        bug = self.feedback_card("BUG-7")
        feedback = self.feedback_card("FB-1")
        self.assertEqual(1, bug.count(), "Der Bug fehlt in der Feedback-Liste")
        self.assertEqual(1, feedback.count(),
                         "Das Feedback fehlt in der Feedback-Liste")
        self.assertEqual("bug", bug.get_attribute("data-nv-kind"),
                         "Dem Bug fehlt das Art-Badge-Feld (F34)")
        self.assertEqual("feedback", feedback.get_attribute("data-nv-kind"),
                         "Dem Feedback fehlt das Art-Badge-Feld (F34)")
        self.assertRegex(bug.locator("span.nv-kind-badge").first.inner_text(),
                         r"bug", "Dem Bug fehlt das Art-Badge")
        self.assertRegex(feedback.locator("span.nv-kind-badge").first.inner_text(),
                         r"feedback", "Dem Eintrag fehlt das Feedback-Badge")
        self.assertNotRegex(
            feedback.inner_text(), r"\bbug\b",
            "Der gewöhnliche Feedback-Eintrag trägt fälschlich ein Bug-Badge")
        self.assert_clean_page()


class CreateTest(AP22WorkBrowserTest):
    def test_create_package_and_cancel_the_form(self):
        """Vorbedingung: Arbeit geöffnet. Aktion: Paket anlegen, danach ein
        zweites Formular abbrechen.
        Erwartung (GH-56): Die neue Karte erscheint in der Draft-Spalte des
        Boards und im Ticketspeicher; Abbrechen schließt das Formular, ohne
        etwas anzulegen.
        """
        self.open_work()
        form = self.open_form("new-package")
        self.fill_form(form, "NEU-AP22 Anlegen", "Zeile eins\nZeile zwei")
        self.save_form(form)
        self.wait_until(
            lambda: "NEU-AP22 Anlegen" in self.ticket_text(),
            timeout=20,
            message="Das neue Arbeitspaket wurde nicht gespeichert")
        card = self.page.locator(
            "article[data-nv-col='draft'] article[data-nv-ticket]").filter(
                has_text="NEU-AP22 Anlegen").first
        card.wait_for(state="visible", timeout=20000)
        tid = (card.get_attribute("data-nv-ticket") or "").strip()
        self.assertTrue(tid, "Die neue Karte trägt keine Paketkennung")
        self.assertEqual("draft", self.records()[tid]["state"],
                         "Ein neues Ticket startet nicht im Status Draft")
        self.assertIn("Zeile eins", self.ticket_text())

        before = self.ticket_text()
        form = self.open_form("new-package")
        self.fill_form(form, "VERWORFEN-AP22", "darf nicht entstehen")
        form.locator("[data-nv-action='ticket-cancel']").click()
        self.assert_form_closed()
        self.assertEqual(
            before, self.ticket_text(),
            "Abbrechen hat die Ticketdatei verändert")
        self.assertEqual(
            0, self.page.locator(
                "div[data-nv-board] article[data-nv-ticket]").filter(
                    has_text="VERWORFEN-AP22").count(),
            "Abbrechen hat trotzdem eine Karte angelegt")
        self.assert_clean_page()


class EditTest(AP22WorkBrowserTest):
    def test_edit_prefills_and_saves_only_the_chosen_ticket(self):
        """Vorbedingung: ``AP-101`` und ``AP-102`` vorhanden.

        Aktion: Klick auf ``article[data-nv-ticket='AP-101']``, dann
        ``button[data-nv-action='ticket-edit']`` im Kontext-Panel
        (``[data-nv-ticket-detail='AP-101']``); Titel ändern, speichern.
        Erwartung: Formular ist vorbefüllt; nur ``AP-101`` ändert sich,
        ``AP-102`` bleibt unverändert.
        """
        self.open_work()
        self.card("AP-101").click()
        detail = self.page.locator("[data-nv-ticket-detail='AP-101']").first
        detail.wait_for(state="visible", timeout=20000)
        # F34: Die Card selbst bietet keinen Bearbeiten-Knopf mehr.
        self.assertEqual(
            0, self.card("AP-101").locator(
                "[data-nv-action='ticket-edit']").count(),
            "F34: Die Karte selbst bietet keinen Bearbeiten-Knopf mehr")
        detail.locator("[data-nv-action='ticket-edit']").first.click()
        form = self.page.locator("[data-nv-ticket-form]")
        form.wait_for(state="visible", timeout=20000)
        title = form.locator("input[data-nv-field='title']")
        self.assertEqual(
            "Offenes Paket", title.input_value(),
            "Das Bearbeitungsformular ist nicht mit dem Titel vorbefüllt")

        title.fill("AP-101 Geändertes Paket")
        form.locator("textarea[data-nv-field='description']").fill(
            "Neue Beschreibung")
        self.save_form(form)
        self.wait_until(
            lambda: "Geändertes Paket" in self.ticket_text(),
            timeout=20,
            message="Die Bearbeitung wurde nicht gespeichert: "
                    + repr(self.records()))
        rows = self.records()
        # Der Editor entfernt einen redundanten ID-Prefix vor dem Speichern;
        # fachlich entscheidend ist der geänderte Titel und dass nur diese
        # Kennung betroffen ist.
        self.assertEqual("Geändertes Paket", rows["AP-101"]["title"])
        self.assertEqual("Neue Beschreibung", rows["AP-101"]["description"])
        self.assertEqual("Zweites offenes Paket", rows["AP-102"]["title"])
        self.assertEqual("Blockiertes Paket", rows["AP-103"]["title"])
        self.assert_clean_page()


class DeleteTest(AP22WorkBrowserTest):
    def test_delete_removes_the_card(self):
        """Vorbedingung: ``AP-101`` vorhanden.

        Aktion: Klick auf ``article[data-nv-ticket='AP-101']``, dann
        ``button[data-nv-action='ticket-delete']`` im Kontext-Panel
        (Bestätigung wird akzeptiert). Erwartung: Karte und Dateieintrag
        verschwinden, die übrigen bleiben.
        """
        self.open_work()
        self.card("AP-101").click()
        detail = self.page.locator("[data-nv-ticket-detail='AP-101']").first
        detail.wait_for(state="visible", timeout=20000)
        # F34: Die Card selbst bietet keinen Löschen-Knopf mehr.
        self.assertEqual(
            0, self.card("AP-101").locator(
                "[data-nv-action='ticket-delete']").count(),
            "F34: Die Karte selbst bietet keinen Löschen-Knopf mehr")
        detail.locator("[data-nv-action='ticket-delete']").first.click()
        self.confirm_if_visible()
        self.wait_until(
            lambda: self.page.locator(
                "article[data-nv-ticket='AP-101']").count() == 0,
            timeout=20,
            message="Die Karte wurde nicht gelöscht")
        self.wait_until(
            lambda: "AP-101" not in self.records(),
            timeout=20,
            message="Der Eintrag wurde nicht aus dem Ticketspeicher entfernt")
        rows = self.records()
        self.assertEqual("Zweites offenes Paket", rows["AP-102"]["title"])
        self.assertEqual("Blockiertes Paket", rows["AP-103"]["title"])
        self.assertEqual("Erledigtes Paket", rows["AP-104"]["title"])
        self.assert_clean_page()


class FeedbackCreateTest(AP22WorkBrowserTest):
    def test_create_bug_and_feedback_entries(self):
        """Vorbedingung: Arbeit geöffnet.

        Aktion: ``new-bug`` und ``new-feedback`` ausfüllen und speichern.
        Erwartung: Beide erscheinen in der ``div[data-nv-ticket-list]``
        (F34: keine ``details[data-nv-feedback-box]`` mehr) mit dem richtigen
        ``data-nv-kind``-Art-Badge.
        """
        self.open_work()
        form = self.open_form("new-bug")
        self.fill_form(form, "NEUER-BUG-AP22", "Absturz beim Speichern")
        self.save_form(form)
        self.wait_until(
            lambda: "NEUER-BUG-AP22" in self.feedback_text(),
            timeout=20,
            message="Der neue Bug wurde nicht gespeichert")
        bug_rows = [r for r in self.records().values()
                    if r["title"] == "NEUER-BUG-AP22"]
        self.assertEqual(1, len(bug_rows), "Der neue Bug ist nicht eindeutig")
        self.assertEqual("bug", bug_rows[0]["type"],
                         "Der neue Bug hat im Speicher nicht den Typ bug")
        bug = self.page.locator("div[data-nv-board] article[data-nv-feedback-item]").filter(
            has_text="NEUER-BUG-AP22").first
        bug.wait_for(state="visible", timeout=20000)
        self.assertEqual("bug", bug.get_attribute("data-nv-kind"),
                         "Der neue Bug trägt kein Art-Badge-Feld (F34)")
        self.assertRegex(bug.inner_text(), r"bug",
                         "Der neue Bug trägt kein Bug-Badge")

        form = self.open_form("new-feedback")
        self.fill_form(form, "NEUES-FEEDBACK-AP22", "Bitte schneller laden")
        self.save_form(form)
        self.wait_until(
            lambda: "NEUES-FEEDBACK-AP22" in self.feedback_text(),
            timeout=20,
            message="Das neue Feedback wurde nicht gespeichert")
        feedback_rows = [r for r in self.records().values()
                         if r["title"] == "NEUES-FEEDBACK-AP22"]
        self.assertEqual(1, len(feedback_rows),
                         "Das neue Feedback ist nicht eindeutig")
        self.assertEqual("feedback", feedback_rows[0]["type"],
                         "Das neue Feedback hat im Speicher nicht den Typ feedback")
        feedback = self.page.locator("div[data-nv-board] article[data-nv-feedback-item]").filter(
            has_text="NEUES-FEEDBACK-AP22").first
        feedback.wait_for(state="visible", timeout=20000)
        self.assertEqual("feedback", feedback.get_attribute("data-nv-kind"),
                         "Das neue Feedback trägt kein Art-Badge-Feld (F34)")
        self.assertRegex(feedback.inner_text(), r"feedback",
                         "Das neue Feedback trägt kein Feedback-Badge")
        self.assertNotRegex(feedback.inner_text(), r"\bbug\b",
                            "Das neue Feedback trägt fälschlich ein Bug-Badge")
        self.assert_clean_page()


class PriorityTest(AP22WorkBrowserTest):
    def test_priority_card_appears_with_feature_and_persists(self):
        """Vorbedingung: Feature ``priority`` aus, Viewport 600x800.

        GH-67: die Priorisierungsansicht gibt es nur auf kleinen Bildschirmen;
        der Fall läuft deshalb mobil statt auf dem Desktop-Board.
        Aktion: Schalter in ``#/settings`` aktivieren, Arbeit öffnen,
        ``AP-102`` hochschieben, neu laden.
        Erwartung: ``div[data-nv-priority-strip]`` steht mit Drag-Griff,
        ``priority-up|down`` und Zurücksetzen; die neue Reihenfolge wird
        sofort gespeichert und bleibt über den Reload erhalten.
        """
        self.page.set_viewport_size({"width": 600, "height": 800})
        self.open_work()
        # F33 WP3/2o: die alte Priorisierungskarte entfällt. Die Leiste ist
        # als Arbeitswerkzeug immer im DOM; ohne Feature fehlen die P-Badges.
        self.assertEqual(
            0, self.page.locator("span[data-nv-prio-badge]").count(),
            "Die Priorisierung ist ohne Feature-Schalter sichtbar")

        self.page.goto(self.base + "/#/settings")
        self.page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=25000)
        feature = self.page.locator("input[data-nv-feature='priority']")
        feature.wait_for(state="visible", timeout=20000)
        self.assertFalse(feature.is_checked(),
                         "Das Priority-Feature ist ohne Zutun bereits an")
        feature.check()
        self.assertTrue(feature.is_checked(),
                        "Der Priority-Schalter ließ sich nicht einschalten")

        self.open_work()
        strip = self.page.locator("div[data-nv-priority-strip]")
        strip.wait_for(state="visible", timeout=20000)
        # F33 WP3/2o: Leiste statt Karte; ↑/↓ speichern sofort, ein eigener
        # Speichern-Knopf ist vertraglich entfallen.
        self.assertGreaterEqual(
            strip.locator("button[data-nv-drag-handle]").count(), 1,
            "Die Priorisierungsleiste zeigt keine Drag-Griffe")
        self.assertGreaterEqual(
            strip.locator("[data-nv-action='priority-up']").count(), 1,
            "Die Priorisierung zeigt keine Hoch-Knöpfe")
        self.assertEqual(
            1, strip.locator("button[data-nv-priority-reset]").count(),
            "Der Zurücksetzen-Knopf der Priorisierung fehlt")

        clicked = self.page.evaluate(
            """() => {
              const strip = document.querySelector('[data-nv-priority-strip]');
              if (!strip) return false;
              const buttons = Array.from(
                strip.querySelectorAll("[data-nv-action='priority-up']"));
              const target = buttons.find(button => {
                const row = button.closest('[data-nv-priority-id]');
                return row && (row.textContent || '').includes('AP-102');
              });
              if (!target || target.disabled) return false;
              target.click();
              return true;
            }""")
        self.assertTrue(clicked,
                        "Keine Priorisierungszeile für AP-102 gefunden")

        def order_ids(view):
            # Der Backend-Vertrag von /api/priority liefert ``order`` als
            # Liste von Objekten je konfiguriertem Eintrag
            # ({"id", "source", "title", "status"}), nicht als ID-Strings.
            return [str(row.get("id") or "")
                    for row in ((view or {}).get("order") or [])]

        def ordered_before(view, first, second):
            ids = order_ids(view)
            return (first in ids and second in ids
                    and ids.index(first) < ids.index(second))

        data = self.wait_api(
            f"/api/priority?name={PROJECT}",
            lambda view: ordered_before(view, "AP-102", "AP-101"),
            message="Die Priorisierung wurde nicht in der erwarteten "
                    "Reihenfolge gespeichert")
        order = order_ids(data)

        self.page.reload()
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        strip.wait_for(state="visible", timeout=20000)
        positions = self.page.evaluate(
            """() => {
              const strip = document.querySelector('[data-nv-priority-strip]');
              const text = strip ? strip.innerText : '';
              return [text.search(/\\bAP-102\\b/), text.search(/\\bAP-101\\b/)];
            }""")
        self.assertGreaterEqual(positions[0], 0,
                                "AP-102 fehlt nach dem Reload")
        self.assertLess(
            positions[0], positions[1],
            "Die Reihenfolge ging beim Reload verloren: " + repr(positions))
        again = self.api_json(f"/api/priority?name={PROJECT}")
        self.assertEqual(
            order, order_ids(again),
            "Die gespeicherte Reihenfolge änderte sich beim Reload")
        self.assert_clean_page()


class FormErrorTest(AP22WorkBrowserTest):
    def test_empty_title_shows_error_and_creates_nothing(self):
        """Vorbedingung: Board geöffnet. Aktion: Paket ohne Titel speichern.
        Erwartung: ``[data-nv-form-error]`` ist im Formular sichtbar, die
        Datei bleibt unverändert, es entsteht keine Karte.
        """
        self.open_work()
        before = self.ticket_text()
        count_before = self.page.locator("article[data-nv-ticket]").count()
        form = self.open_form("new-package")
        form.locator("textarea[data-nv-field='description']").fill(
            "Beschreibung ohne Titel")
        self.save_form(form)
        error = form.locator("[data-nv-form-error]")
        self.wait_until(
            lambda: error.count() == 1 and error.first.is_visible()
            and (error.first.inner_text() or "").strip(),
            timeout=20,
            message="Der Formularfehler [data-nv-form-error] fehlt oder ist leer")
        self.assertEqual(
            before, self.ticket_text(),
            "Trotz fehlendem Titel wurde die Ticketdatei verändert")
        self.assertEqual(
            count_before, self.page.locator("article[data-nv-ticket]").count(),
            "Trotz fehlendem Titel entstand eine Karte")
        self.assert_clean_page()


# ===========================================================================
# Browserabnahme / „Priorisierung der Abarbeitungsreihenfolge“
# ===========================================================================

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

# Installierte Entwicklerabhängigkeit: Chromium nur lesend aus dem
# Nutzer-Cache (Muster tests/browser/test_ap7_settings_ui.py).
_BROWSERS_ap11 = Path.home() / ".cache" / "ms-playwright"
if _BROWSERS_ap11.is_dir():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_BROWSERS_ap11))

from playwright.sync_api import sync_playwright


# Ambient VIBE_*-Werte (Sandbox/Container) würden vibe-web auf die
# produktive Installation zeigen lassen; der Test besitzt alle Laufzeitpfade.
ISOLATED_ENV = (
    "VIBE",
    "VIBE_NO_CONTAINER",
    "HOME",
    "VIBE_PROFILE",
    "VIBE_INSTALL",
    "VIBE_RUNTIME",
    "VIBE_STATE",
    "VIBE_AGENTS_DIR",
    "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR",
    "VIBE_UI_PORT",
    "VIBE_OPENCODE_PORT",
    "VIBE_UI_BIND",
    "VIBE_CONTAINER",
    "VIBE_HARNESS",
)


def git(project, *argv):
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
    })
    return subprocess.run(
        ["git", "-C", str(project), *argv],
        capture_output=True, text=True, check=False, timeout=60,
        env=env,
    )


class Ap11PriorityBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        cls.project.mkdir(parents=True)
        git(cls.project, "init", "-q", "-b", "main")
        (cls.project / ".vibe").mkdir(exist_ok=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nTESTER=test-agent\n", encoding="utf-8")
        # Eine nachweislich erledigte Aufgabe und zwei offene Aufgaben:
        # die Statusanzeige der API (erledigt/offen) wird dadurch prüfbar.
        git(cls.project, "commit", "--allow-empty", "-q", "-m", "init")
        commit = subprocess.run(
            ["git", "-C", str(cls.project), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()
        (cls.project / "TICKETS.md").write_text(
            "# TICKETS\n\n"
            "- [x] T0 Erledigte Aufgabe\n"
            "  Beschreibung: fertig\n"
            "  Commit: %s; Test: test_ap11\n\n" % commit +
            "- [ ] T1 Erste Aufgabe\n  Beschreibung: offen\n"
            "- [ ] T2 Zweite Aufgabe\n  Beschreibung: offen\n",
            encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n", encoding="utf-8")
        git(cls.project, "add", "-A")
        git(cls.project, "commit", "-q", "-m", "Nachweis T0")
        cls.env_path = cls.project / ".vibe" / "project.env"
        cls.base_env = "TYPE=generic\nTESTER=test-agent\n"

        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.toolchain = cls.root / "_toolchain"
        cls.toolchain.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.port = free_port()
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.home),
                "VIBE_STATE": str(cls.toolchain),
                "VIBE_INSTALL": str(cls.toolchain),
                "VIBE_RUNTIME": str(cls.log_dir),
                "VIBE_AGENTS_DIR": str(
                    cls.home / ".config" / "opencode" / "agents"),
                "VIBE_CONFIG_FILE": str(
                    cls.home / ".config" / "vibe" / "config.json"),
            }
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                            ("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: " + output)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        if cls.proc.stdout:
            cls.proc.stdout.close()
        cls.tmp.cleanup()

    def setUp(self):
        """Jeder Test startet mit der Grundkonfiguration ohne Priorisierung."""
        self.env_path.write_text(self.base_env, encoding="utf-8")
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1000})

    def tearDown(self):
        self.page.close()

    # ------------------------------------------------------------ Helfer
    def wait_until(self, predicate, timeout=10, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def open_project(self, tab="arbeit"):
        """Vorbedingung einstellen: Projekt „proj“ öffnen, Register wählen."""
        self.page.goto("about:blank")
        self.page.goto(self.base + "/classic#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        if tab != "arbeit":
            self.page.locator(
                f"[role='tab'][aria-controls='panel-{tab}']").click()
        panel = self.page.locator("#panel-" + tab)
        panel.wait_for()
        self.assertTrue(panel.is_visible(),
                        "Panel „%s“ ist nicht sichtbar" % tab)
        return panel

    def open_settings(self):
        return self.open_project(tab="einstellungen")

    def open_work(self):
        return self.open_project(tab="arbeit")

    def items_card(self):
        """Die Karte „Offene Arbeitspakete“ in der Maske „Arbeit“."""
        card = self.page.locator("#panel-arbeit .card",
                                 has_text="Open work packages").first
        card.wait_for(timeout=10000)
        return card

    def item_ids(self):
        """Die Kennungen der Karte in sichtbarer Reihenfolge.

        Der Itemtext beginnt mit der Zustands-Pille (z. B. „offen“); die
        Kennung (T1, F3, …) wird deshalb per Muster herausgelesen.
        """
        items = self.items_card().locator(".item")
        ids = []
        for item in items.all():
            match = re.search(r"[TFB]\d+", item.inner_text())
            self.assertIsNotNone(
                match,
                "Item nennt keine Kennung: %r" % item.inner_text())
            ids.append(match.group(0))
        return ids

    def handles(self):
        """Die Drag-Handles der Karte (Elemente mit data-drag-handle)."""
        return self.items_card().locator("[data-drag-handle]")

    def save_button(self):
        return self.items_card().get_by_role("button", name="Save",
                                             exact=True).first

    def clear_button(self):
        return self.items_card().get_by_role(
            "button", name=re.compile("Clear", re.I)).first

    def handle_of(self, identifier):
        """Der Handle des Pakets mit der Kennung ``identifier``."""
        handle = self.items_card().locator(
            f".item:has-text('{identifier}') [data-drag-handle]").first
        self.wait_until(
            lambda: handle.count() > 0, timeout=5,
            message="Paket %s hat keinen Drag-Handle (data-drag-handle)"
                    % identifier)
        return handle

    # ------------------------------------------------------------ AK 4
    def test_settings_tab_has_no_priorisierung_section_or_chip(self):
        """AK 4 — Der Einstellungs-Tab enthält keine Priorisierung mehr.

        Vorbedingung: Projekt „proj“ geöffnet, Register „Einstellungen“.
        Aktion: das Einstellungs-Panel nach einem Abschnitt „Priorisierung“
        und einem data-goto-Sprungchip „Priorisierung“ durchsuchen.
        Erwartet: beides existiert nicht mehr (je 0 Treffer) — die
        Bedienstelle ist in die Maske „Arbeit“ verlagert.
        """
        self.open_settings()

        panel = self.page.locator("#panel-einstellungen")
        self.assertEqual(
            0, panel.locator(
                "details",
                has_text=re.compile("Priorisierung|Prioritization")).count(),
            "Einstellungs-Tab enthält noch einen Priorisierungs-Abschnitt")
        self.assertEqual(
            0, panel.locator('[data-goto*="prioris" i]').count(),
            "Einstellungs-Tab enthält noch den Sprungchip „Priorisierung“")

    # ------------------------------------------------------------ AK 3/5
    def test_open_packages_card_offers_drag_handles_save_and_clear(self):
        """AK 3/5 — Karte „Offene Arbeitspakete“ mit Handle je Paket.

        Vorbedingung: Projekt mit erledigter T0 und offenen T1/T2; kein
        PACKAGE_ORDER-Eintrag; Maske „Arbeit“ geöffnet.
        Aktion: die Karte inspizieren.
        Erwartet: die Karte listet die offenen Pakete T1 und T2 (nicht die
        erledigte T0) in der Standardordnung T1 vor T2; je Paket genau ein
        Drag-Handle (Element mit data-drag-handle und aria-label, der
        „verschieben“ enthält); „Speichern“ und „Leeren (Standardordnung)“
        sind in der Karte vorhanden.
        """
        self.open_work()

        card = self.items_card()
        self.assertEqual(["T1", "T2"], self.item_ids(),
                         "Karte zeigt nicht die Standardordnung der offenen "
                         "Pakete: " + ", ".join(self.item_ids()))

        handles = self.handles()
        self.assertEqual(2, handles.count(),
                         "nicht je Paket ein Drag-Handle (%d gefunden)"
                         % handles.count())
        for index in range(handles.count()):
            label = handles.nth(index).get_attribute("aria-label") or ""
            self.assertTrue(
                re.search(r"verschieben|move", label, re.I),
                "Handle %d ist nicht als solches erkennbar (aria-label=%r)"
                % (index, label))

        self.save_button()
        self.clear_button()

    # ------------------------------------------------------------ AK 3
    def test_drag_and_drop_reorders_and_save_writes_package_order(self):
        """AK 3 — Drag&Drop ändert die Reihenfolge, Speichern legt sie ab.

        Vorbedingung: kein PACKAGE_ORDER-Eintrag; Maske „Arbeit“ geöffnet.
        Aktion: den Handle des Pakets T2 per Drag&Drop an die obere Kante
        des Pakets T1 ziehen (Vertrag: Ablegen an der Oberkante fügt vor
        dem Zielpaket ein), danach „Speichern“ klicken.
        Erwartet: project.env enthält PACKAGE_ORDER mit T2 vor T1 und
        behält TYPE/TESTER; nach erneutem Öffnen des Projekts zeigt die
        Karte die übernommene Reihenfolge T2 vor T1.
        """
        self.open_work()
        self.assertEqual(["T1", "T2"], self.item_ids())

        self.handle_of("T2").drag_to(
            self.items_card().locator(".item", has_text="T1").first,
            target_position={"x": 20, "y": 4})
        self.save_button().click()

        self.wait_until(
            lambda: "PACKAGE_ORDER" in self.env_path.read_text(
                encoding="utf-8"),
            message="Speichern schrieb kein PACKAGE_ORDER nach project.env")
        text = self.env_path.read_text(encoding="utf-8")
        self.assertLess(
            text.index("T2"), text.index("T1"),
            "PACKAGE_ORDER wurde nicht in der gezogenen Reihenfolge "
            "abgelegt: " + text)
        self.assertIn("TYPE=generic", text,
                      "Speichern beschädigte project.env")
        self.assertIn("TESTER=test-agent", text,
                      "Speichern beschädigte project.env")

        self.open_project()
        self.assertEqual(
            ["T2", "T1"], self.item_ids(),
            "die Karte zeigt nach dem Speichern nicht die übernommene "
            "Reihenfolge: " + ", ".join(self.item_ids()))

    def test_clear_resets_to_the_standard_order(self):
        """AK 3 — „Leeren (Standardordnung)“ setzt die gespeicherte Ordnung zurück.

        Vorbedingung: PACKAGE_ORDER="T2,T1" abgelegt; Maske „Arbeit“
        geöffnet. Die Karte zeigt die übernommene Reihenfolge T2 vor T1.
        Aktion: „Leeren (Standardordnung)“ klicken.
        Erwartet: PACKAGE_ORDER enthält keine Kennung mehr; TYPE/TESTER
        bleiben; nach erneutem Öffnen zeigt die Karte wieder die
        Standardordnung T1 vor T2.
        """
        self.env_path.write_text(
            self.base_env + 'PACKAGE_ORDER="T2,T1"\n', encoding="utf-8")
        self.open_work()
        self.assertEqual(
            ["T2", "T1"], self.item_ids(),
            "die Karte zeigt die abgelegte Reihenfolge nicht: "
            + ", ".join(self.item_ids()))

        self.clear_button().click()

        self.wait_until(
            lambda: not re.search(
                r'(?m)^\s*PACKAGE_ORDER\s*=\s*["\']?\s*[^"\'\s]+',
                self.env_path.read_text(encoding="utf-8")),
            message="Leeren leerte PACKAGE_ORDER nicht")
        text = self.env_path.read_text(encoding="utf-8")
        self.assertIn("TYPE=generic", text, "Leeren beschädigte project.env")
        self.assertIn("TESTER=test-agent", text,
                      "Leeren beschädigte project.env")

        self.open_project()
        self.assertEqual(
            ["T1", "T2"], self.item_ids(),
            "die Karte zeigt nach dem Leeren nicht die Standardordnung: "
            + ", ".join(self.item_ids()))

    # ------------------------------------------------------------ AK 5
    def test_handle_is_keyboard_operable_with_arrow_keys(self):
        """AK 5 — Die Sortierung ist ohne Maus am Handle bedienbar.

        Vorbedingung: kein PACKAGE_ORDER-Eintrag; Maske „Arbeit“ geöffnet.
        Aktion: den Handle des Pakets T2 fokussieren und „ArrowUp“ drücken
        (Vertrag: Pfeiltaste verschiebt das fokussierte Paket eine
        Position, ohne Moduswechsel); danach „Speichern“ klicken.
        Erwartet: die Karte zeigt T2 vor T1 (Verschieben ohne Maus);
        project.env enthält PACKAGE_ORDER mit T2 vor T1.
        """
        self.open_work()
        self.assertEqual(["T1", "T2"], self.item_ids())

        handle = self.handle_of("T2")
        handle.focus()
        self.page.keyboard.press("ArrowUp")

        self.wait_until(
            lambda: self.item_ids() == ["T2", "T1"],
            message="ArrowUp am fokussierten Handle verschob T2 nicht vor T1: "
                    + ", ".join(self.item_ids()))
        self.save_button().click()

        self.wait_until(
            lambda: "PACKAGE_ORDER" in self.env_path.read_text(
                encoding="utf-8"),
            message="Speichern schrieb kein PACKAGE_ORDER nach project.env")
        text = self.env_path.read_text(encoding="utf-8")
        self.assertLess(
            text.index("T2"), text.index("T1"),
            "PACKAGE_ORDER wurde nicht in der tastaturgezogenen Reihenfolge "
            "abgelegt: " + text)

    # --------------------------------------------- Review M1 (Anzeigeordnung)
    def test_blocked_package_keeps_its_saved_position_after_save(self):
        """Review M1 — BLOCKIERT-Paket behält die gezogene Position.

        Vorbedingung: TICKETS.md mit offenem T1 (zuerst) und gesperrtem T0
        (BLOCKIERT); kein PACKAGE_ORDER-Eintrag; Maske „Arbeit“ geöffnet.
        Aktion: den Handle des BLOCKIERT-Pakets T0 fokussieren, „ArrowUp“
        drücken (T0 rückt an die erste Position) und „Speichern“ klicken.
        Erwartet: project.env enthält PACKAGE_ORDER mit T0 vor T1; nach
        komplettem Neuöffnen der Projektseite zeigt die Karte weiterhin T0
        vor T1; die T0-Zeile trägt die BLOCKIERT-Pille und die
        „priorisiert“-Pille, die T1-Zeile die „Standardordnung“-Pille.
        """
        tickets = self.project / "TICKETS.md"
        original = tickets.read_text(encoding="utf-8")
        self.addCleanup(
            lambda: tickets.write_text(original, encoding="utf-8"))
        tickets.write_text(
            "# TICKETS\n\n"
            "- [ ] T1 Erste Aufgabe\n  Beschreibung: offen\n"
            "- [ ] T0 Gesperrt\n  BLOCKIERT: fehlende Freigabe\n",
            encoding="utf-8")

        self.open_work()
        self.assertEqual(
            ["T1", "T0"], self.item_ids(),
            "Standardordnung ohne BLOCKIERT-Paket: "
            + ", ".join(self.item_ids()))

        self.handle_of("T0").focus()
        self.page.keyboard.press("ArrowUp")
        self.wait_until(
            lambda: self.item_ids() == ["T0", "T1"],
            message="ArrowUp am Handle verschob das BLOCKIERT-Paket T0 "
                    "nicht an die erste Position: "
                    + ", ".join(self.item_ids()))
        self.save_button().click()

        self.wait_until(
            lambda: "PACKAGE_ORDER" in self.env_path.read_text(
                encoding="utf-8"),
            message="Speichern schrieb kein PACKAGE_ORDER nach project.env")
        text = self.env_path.read_text(encoding="utf-8")
        self.assertLess(
            text.index("T0"), text.index("T1"),
            "PACKAGE_ORDER enthält die gezogene Position nicht: " + text)
        self.assertIn("TYPE=generic", text,
                      "Speichern beschädigte project.env")
        self.assertIn("TESTER=test-agent", text,
                      "Speichern beschädigte project.env")

        self.open_project()
        self.assertEqual(
            ["T0", "T1"], self.item_ids(),
            "die Karte verwarf die gezogene Position des BLOCKIERT-Pakets: "
            + ", ".join(self.item_ids()))
        blocked_text = self.items_card().locator(
            ".item", has_text="T0").first.inner_text()
        self.assertIn("BLOCKIERT", blocked_text,
                      "T0-Zeile ohne BLOCKIERT-Pille: " + blocked_text)
        self.assertIn("prioritized", blocked_text,
                      "T0-Zeile ohne „priorisiert“-Pille: " + blocked_text)
        open_text = self.items_card().locator(
            ".item", has_text="T1").first.inner_text()
        # „Speichern“ legt die gesamte sichtbare Zeilenreihenfolge ab,
        # daher ist T1 Teil von PACKAGE_ORDER und priorisiert.
        self.assertIn("prioritized", open_text,
                      "T1-Zeile ist nicht als priorisiert gekennzeichnet: "
                      + open_text)

    # ---------------------------------------- Review M2-Minor (Hinweis fehlt)
    def test_unknown_saved_id_is_reported_and_removed_on_save(self):
        """Review M2-Minor — Unbekannte Kennung wird sichtbar gemeldet.

        Vorbedingung: PACKAGE_ORDER="XX9,T1" abgelegt; XX9 existiert in
        keiner Arbeitsnotiz; Maske „Arbeit“ geöffnet.
        Aktion: die Karte inspizieren, danach „Speichern“ klicken.
        Erwartet: die Karte nennt XX9 im Hinweis („Unbekannte Kennungen …“,
        Entfernung beim nächsten Speichern angekündigt) und listet XX9
        nicht als Zeile; nach dem Speichern ist XX9 aus PACKAGE_ORDER
        entfernt (env-Datei), die bekannten Zeilen bleiben und der Hinweis
        verschwindet.
        """
        self.env_path.write_text(
            self.base_env + 'PACKAGE_ORDER="XX9,T1"\n', encoding="utf-8")

        self.open_work()
        card = self.items_card()
        card_text = card.inner_text()
        self.assertIn("XX9", card_text,
                      "die Karte nennt die unbekannte Kennung nicht: "
                      + card_text)
        self.assertIn("Unknown IDs", card_text,
                      "kein Hinweistext zur unbekannten Kennung: "
                      + card_text)
        self.assertIn("removed", card_text,
                      "der Hinweis kündigt die Entfernung nicht an: "
                      + card_text)
        self.assertNotIn(
            "XX9", self.item_ids(),
            "die unbekannte Kennung erscheint als Zeile: "
            + ", ".join(self.item_ids()))
        self.assertIn("T1", self.item_ids(),
                      "die bekannte Zeile T1 fehlt: "
                      + ", ".join(self.item_ids()))

        self.save_button().click()

        self.wait_until(
            lambda: "PACKAGE_ORDER" in self.env_path.read_text(
                encoding="utf-8")
            and "XX9" not in self.env_path.read_text(encoding="utf-8"),
            message="Speichern entfernte XX9 nicht aus PACKAGE_ORDER: "
                    + self.env_path.read_text(encoding="utf-8"))
        env_text = self.env_path.read_text(encoding="utf-8")
        self.assertIn("T1", env_text,
                      "die bekannte Kennung ging beim Speichern verloren: "
                      + env_text)
        self.assertIn("TYPE=generic", env_text,
                      "Speichern beschädigte project.env")
        self.assertIn("TESTER=test-agent", env_text,
                      "Speichern beschädigte project.env")

        self.wait_until(
            lambda: "XX9" not in self.items_card().inner_text(),
            message="der Hinweis zur unbekannten Kennung verschwand nach "
                    "dem Speichern nicht")
        self.assertIn("T1", self.item_ids(),
                      "die bekannte Zeile T1 verschwand nach dem Speichern: "
                      + ", ".join(self.item_ids()))

    # ------------------------------------------------------------ AK 3 (API)
    def test_priority_api_reports_configured_effective_and_status(self):
        """AK 3 (API-Grundlage) — GET /api/priority (unverändert aus AP11).

        Vorbedingung: PACKAGE_ORDER="T2,T0,X9,T1" abgelegt; T0 erledigt
        (mit Nachweis), T1/T2 offen, X9 unbekannt.
        Aktion: GET /api/priority?name=proj mit Token stellen und die JSON-
        Antwort auswerten.
        Erwartet: HTTP 200; die Antwort nennt die konfigurierten Einträge
        samt Status (erledigt für T0, fehlt für X9), enthält eine
        effektive Reihenfolge, die T2 vor T1 ohne erledigtes T0 zeigt, und
        eine Meldung.
        """
        write_env = self.env_path.read_text(encoding="utf-8")
        write_env = write_env + 'PACKAGE_ORDER="T2,T0,X9,T1"\n'
        self.env_path.write_text(write_env, encoding="utf-8")
        # Die Fixture-Datei ist geteilt: Nach diesem Test gilt wieder die
        # Standardkonfiguration, damit nachfolgende Tests unverändert laufen.
        self.addCleanup(
            lambda: self.env_path.write_text(
                self.base_env, encoding="utf-8"))

        request = urllib.request.Request(
            f"{self.base}/api/priority?name=proj", method="GET")
        request.add_header("X-Token", self.token)
        with urllib.request.urlopen(request, timeout=20) as response:
            self.assertEqual(200, response.status)
            payload = json.loads(response.read().decode("utf-8"))

        dumped = json.dumps(payload, ensure_ascii=False)
        for identifier in ("T0", "T1", "T2", "X9"):
            self.assertIn(identifier, dumped,
                          "Antwort nennt %s nicht: %s" % (identifier, dumped))
        self.assertIn("erledigt", dumped,
                      "Status erledigt fehlt: " + dumped)
        self.assertIn("fehlt", dumped, "Status fehlt für X9: " + dumped)

        # „order" und „queue" sind Listen von Objekten (id, title, status).
        order = {entry["id"]: entry.get("status", "")
                 for entry in payload.get("order", [])
                 if isinstance(entry, dict) and "id" in entry}
        queue = [entry["id"] for entry in payload.get("queue", [])
                 if isinstance(entry, dict) and "id" in entry]
        self.assertEqual({"T2": "offen", "T0": "erledigt", "X9": "fehlt",
                          "T1": "offen"},
                         order,
                         "Status je konfiguriertem Eintrag falsch: " + dumped)
        self.assertEqual(["T2", "T1"], queue,
                         "effektive Reihenfolge falsch: " + dumped)
        self.assertNotIn("T0", queue,
                         "die erledigte T0 rückt in die effektive "
                         "Reihenfolge: " + dumped)
        self.assertTrue(
            any("meldung" in key.lower() or "message" in key.lower()
                for key in self._keys(payload)),
            "keine Meldung in der Antwort: " + dumped,
        )

    def _keys(self, value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from self._keys(item)
        elif isinstance(value, list):
            for item in value:
                yield from self._keys(item)


    # ------------------- Review Runde 2, Finding M1 (AK-C/D/E)
    def write_mixed_open_fixture(self):
        """Gemischte offene Quellen: TICKETS mit Prioritäten, FEEDBACK.

        Ersetzt die Fixture durch zwei offene TICKETS-Einträge, deren
        Prioritäten gegen die Dateireihenfolge laufen (T1 zuerst in der
        Datei, aber P1; T2 danach mit P0) und einen offenen
        FEEDBACK-Eintrag F1. Stellt beide Dateien nach dem Test wieder
        her.
        """
        tickets = self.project / "TICKETS.md"
        feedback = self.project / "FEEDBACK.md"
        original_tickets = tickets.read_text(encoding="utf-8")
        original_feedback = feedback.read_text(encoding="utf-8")
        self.addCleanup(
            lambda: (tickets.write_text(original_tickets, encoding="utf-8"),
                     feedback.write_text(original_feedback, encoding="utf-8")))
        tickets.write_text(
            "# TICKETS\n\n"
            "- [ ] T1 Erste Aufgabe\n  Beschreibung: offen\n"
            "  Priorität: P1\n\n"
            "- [ ] T2 Zweite Aufgabe\n  Beschreibung: offen\n"
            "  Priorität: P0\n",
            encoding="utf-8")
        feedback.write_text(
            "# FEEDBACK\n\n"
            "- [ ] F1 Feedback-Paket\n  Beschreibung: offen\n",
            encoding="utf-8")

    def write_blocked_first_fixture(self):
        """Gesperrtes P0-Paket vor bereitem P1-Paket in TICKETS.md.

        Die Standardordnung des Läufers wählt T0 (BLOCKIERT, P0) vor T1
        (offen, P1); die Dateireihenfolge (d.items) listet T1 zuerst.
        Stellt die Datei nach dem Test wieder her.
        """
        tickets = self.project / "TICKETS.md"
        original = tickets.read_text(encoding="utf-8")
        self.addCleanup(
            lambda: tickets.write_text(original, encoding="utf-8"))
        tickets.write_text(
            "# TICKETS\n\n"
            "- [ ] T1 Bereite Aufgabe\n  Beschreibung: offen\n"
            "  Priorität: P1\n\n"
            "- [ ] T0 Gesperrt\n  Beschreibung: wartet\n"
            "  BLOCKIERT: fehlende Freigabe\n  Priorität: P0\n",
            encoding="utf-8")

    def row_text(self, identifier):
        """Der Zeilentext eines Kartenpakets inklusive seiner Pillen."""
        row = self.items_card().locator(
            ".item", has_text=identifier).first
        row.wait_for(timeout=10000)
        return row.inner_text()

    def get_priority_payload(self):
        """GET /api/priority?name=proj mit Token als JSON-Antwort."""
        request = urllib.request.Request(
            self.base + "/api/priority?name=proj", method="GET")
        request.add_header("X-Token", self.token)
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def package_order_value(self):
        """Der Kennungswert von PACKAGE_ORDER aus project.env als Liste."""
        text = self.env_path.read_text(encoding="utf-8")
        match = re.search(
            r'(?m)^\s*PACKAGE_ORDER\s*=\s*["\']?([^"\'\n]*)', text)
        if not match:
            return None
        return [token for token in re.split(r"[,;\s]+", match.group(1))
                if token]

    def test_standard_order_display_and_pill_without_configuration(self):
        """AK-C — Karte zeigt die Läufer-Standardordnung samt Pille.

        Vorbedingung: gemischte offene Quellen (TICKETS: T2 mit P0, T1
        mit P1 — T1 steht zuerst in der Datei; FEEDBACK: F1 offen); kein
        PACKAGE_ORDER-Eintrag; Maske „Arbeit“ geöffnet.
        Aktion: die Karte inspizieren.
        Erwartet: die Karte listet die offenen Pakete in der Läufer-
        Standardordnung T2 (P0) vor T1 (P1) vor F1 (FEEDBACK dahinter)
        — nicht in der d.items-Dateireihenfolge F1/T1/T2 — und jede
        Zeile trägt die Pille „Standardordnung“.
        """
        self.write_mixed_open_fixture()
        self.open_work()

        self.wait_until(
            lambda: self.item_ids() == ["T2", "T1", "F1"],
            message="die Karte zeigt ohne PACKAGE_ORDER nicht die "
                    "Läufer-Standardordnung (TICKETS nach Priorität vor "
                    "FEEDBACK): " + ", ".join(self.item_ids()))
        for identifier in ("T2", "T1", "F1"):
            self.assertIn(
                "Default order", self.row_text(identifier),
                "Zeile %s trägt nicht die „Standardordnung“-Pille: %r"
                % (identifier, self.row_text(identifier)))

    def test_blank_save_writes_the_displayed_standard_order(self):
        """AK-D — Blankes „Speichern“ legt die Standardordnung ab.

        Vorbedingung: gemischte offene Quellen wie in AK-C; kein
        PACKAGE_ORDER-Eintrag; Maske „Arbeit“ geöffnet und die Karte
        zeigt die Läufer-Standardordnung.
        Aktion: „Speichern“ ohne jede Verschiebung klicken; danach das
        Projekt neu öffnen, GET /api/priority auswerten und den Läufer
        (``bin/vibe_packages.py select``) abfragen.
        Erwartet: PACKAGE_ORDER enthält genau die angezeigte Reihenfolge
        T2 vor T1 vor F1; nach dem Neuöffnen zeigt die Karte diese
        Reihenfolge mit „priorisiert“-Pille je Zeile; GET nennt sie als
        priorisierte (effektive) Reihenfolge; der Läufer wählt T2 zuerst.
        """
        self.write_mixed_open_fixture()
        self.open_work()
        self.wait_until(
            lambda: self.item_ids() == ["T2", "T1", "F1"],
            message="Vorbedingung verletzt: die Karte zeigt nicht die "
                    "Läufer-Standardordnung: "
                    + ", ".join(self.item_ids()))

        self.save_button().click()

        self.wait_until(
            lambda: "PACKAGE_ORDER" in self.env_path.read_text(
                encoding="utf-8"),
            message="Speichern schrieb kein PACKAGE_ORDER nach project.env")
        self.assertEqual(
            ["T2", "T1", "F1"], self.package_order_value(),
            "blankes Speichern legte nicht die angezeigte Standardordnung "
            "ab: " + self.env_path.read_text(encoding="utf-8"))
        text = self.env_path.read_text(encoding="utf-8")
        self.assertIn("TYPE=generic", text,
                      "Speichern beschädigte project.env")
        self.assertIn("TESTER=test-agent", text,
                      "Speichern beschädigte project.env")

        payload = self.get_priority_payload()
        queue = [entry["id"] for entry in payload.get("queue", [])
                 if isinstance(entry, dict) and "id" in entry]
        self.assertEqual(
            ["T2", "T1", "F1"], queue,
            "GET zeigt die gespeicherte Standardordnung nicht als "
            "effektive Reihenfolge: "
            + json.dumps(payload, ensure_ascii=False))

        runner = subprocess.run(
            [sys.executable,
             str(Path(__file__).resolve().parents[2] / "bin"
                 / "vibe_packages.py"),
             "select", "--project", str(self.project)],
            capture_output=True, text=True, check=False, timeout=60,
            env={key: value for key, value in os.environ.items()
                 if not key.startswith("VIBE_")})
        self.assertEqual(
            0, runner.returncode,
            "Läufer-Auswahl schlug fehl: " + runner.stdout + runner.stderr)
        self.assertEqual(
            "T2", runner.stdout.strip(),
            "der Läufer wählt nicht das erste Paket der gespeicherten "
            "Standardordnung: " + runner.stdout)

        self.open_project()
        self.assertEqual(
            ["T2", "T1", "F1"], self.item_ids(),
            "die Karte zeigt nach dem Speichern nicht die übernommene "
            "Standardordnung: " + ", ".join(self.item_ids()))
        for identifier in ("T2", "T1", "F1"):
            self.assertIn(
                "prioritized", self.row_text(identifier),
                "Zeile %s ist nach dem Speichern nicht als priorisiert "
                "gekennzeichnet: %r"
                % (identifier, self.row_text(identifier)))

    def test_blocked_package_appears_in_standard_order_and_keeps_position(
            self):
        """AK-E — BLOCKIERT-Paket steht in der Standardordnung und bleibt.

        Vorbedingung: TICKETS.md mit bereitem offenen T1 (Priorität P1)
        und gesperrtem T0 (BLOCKIERT, Priorität P0); kein
        PACKAGE_ORDER-Eintrag; Maske „Arbeit“ geöffnet.
        Aktion: die Karte inspizieren, danach blankes „Speichern“ (ohne
        Verschiebung) klicken und das Projekt neu öffnen.
        Erwartet: die Karte zeigt T0 vor T1 (Läufer-Standardordnung nach
        Priorität), die T0-Zeile trägt BLOCKIERT- und
        „Standardordnung“-Pille; PACKAGE_ORDER enthält T0 vor T1; nach
        dem Neuöffnen behält das gesperrte T0 seine Position (T0 vor T1)
        und ist dort als „priorisiert“ gekennzeichnet — konsistent zum
        bestehenden Verhalten nach gezogener Position.
        """
        self.write_blocked_first_fixture()
        self.open_work()

        self.wait_until(
            lambda: self.item_ids() == ["T0", "T1"],
            message="die Karte zeigt das gesperrte P0-Paket nicht vor dem "
                    "bereiten P1-Paket in der Standardordnung: "
                    + ", ".join(self.item_ids()))
        blocked_text = self.row_text("T0")
        self.assertIn(
            "BLOCKIERT", blocked_text,
            "T0-Zeile ohne BLOCKIERT-Pille: " + blocked_text)
        self.assertIn(
            "Default order", blocked_text,
            "T0-Zeile ohne „Standardordnung“-Pille: " + blocked_text)

        self.save_button().click()

        self.wait_until(
            lambda: "PACKAGE_ORDER" in self.env_path.read_text(
                encoding="utf-8"),
            message="Speichern schrieb kein PACKAGE_ORDER nach project.env")
        self.assertEqual(
            ["T0", "T1"], self.package_order_value(),
            "blankes Speichern legte nicht die angezeigte Standardordnung "
            "ab: " + self.env_path.read_text(encoding="utf-8"))

        self.open_project()
        self.assertEqual(
            ["T0", "T1"], self.item_ids(),
            "das gesperrte Paket verlor nach dem Speichern seine "
            "Position: " + ", ".join(self.item_ids()))
        blocked_text = self.row_text("T0")
        self.assertIn(
            "BLOCKIERT", blocked_text,
            "T0-Zeile ohne BLOCKIERT-Pille nach dem Speichern: "
            + blocked_text)
        self.assertIn(
            "prioritized", blocked_text,
            "T0-Zeile ist nach dem Speichern nicht als priorisiert "
            "gekennzeichnet: " + blocked_text)


# ===========================================================================
# Browserabnahme für den einheitlichen Tickettyp und den ruhigen Editor
# ===========================================================================

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.parse
from pathlib import Path

from tests.unit import env_support

if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402

VIEWPORT = {"width": 1500, "height": 1100}
NEW_ACTIONS = {"package": "new-package", "bug": "new-bug",
               "feedback": "new-feedback"}
EXPECTED_TYPES = {"feature", "bug", "feedback"}


def isolated_env(root, home, port):
    """Bereinigte VIBE_*-Umgebung; ausschließlich temporäre Pfade.

    ``env_support.isolated_environ`` entfernt die Instanzvariablen der
    laufenden Installation. Sandbox-/Tmux-Reste der aufrufenden Umgebung
    werden zusätzlich entfernt, damit der Testserver keinen fremden
    Arbeitsbereich erbt.
    """
    env = env_support.isolated_environ()
    for key in list(env):
        if key.startswith("SANDBOX") or key in ("TMUX", "TMUX_PANE"):
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


class B1WorkBrowserTest(unittest.TestCase):
    """Ein isolierter Live-Server; je Testfall ein eigener Browser-Kontext."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / PROJECT
        (cls.project / ".vibe").mkdir(parents=True)
        # Nicht verbundenes Projekt: keine Issues-Konfiguration, damit die
        # lokale Anlage (Vertrag C) ohne GitHub geprüft wird.
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
        self.context = self.browser.new_context(viewport=VIEWPORT)
        self.page = self.context.new_page()
        self.page.set_default_timeout(8000)
        self.page_errors = []
        self.dialogs = []
        self.requests = []
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))
        self.page.on("dialog", self._on_dialog)
        self.page.on("request", self._record_request)

    def tearDown(self):
        self.context.close()

    def _on_dialog(self, dialog):
        self.dialogs.append(dialog.type + ": " + dialog.message)
        dialog.accept()

    # --------------------------------------------------------- Helfer
    def _record_request(self, request):
        """Alle Browser-Requests mitschreiben (auch von Routen beantwortete)."""
        payload = None
        if request.post_data:
            try:
                payload = json.loads(request.post_data)
            except ValueError:
                payload = request.post_data
        self.requests.append({
            "method": request.method,
            "path": urllib.parse.urlparse(request.url).path,
            "payload": payload,
        })

    def api_writes(self, path, action=None):
        rows = [row for row in self.requests
                if row["method"] == "POST" and row["path"] == path]
        if action is not None:
            rows = [row for row in rows
                    if isinstance(row["payload"], dict)
                    and row["payload"].get("action") == action]
        return rows

    def fake_ticket_writes(self):
        """Beantwortet Ticket-/Feedback-POSTs lokal, ohne Serverwirkung.

        So bleibt der Test auf dem Request-Vertrag (Vertrag B) fokussiert und
        legt weder Issues noch lokale Einträge an. Bewusst auch
        ``/api/feedback`` abfangen: der alte Anlageweg wäre sonst nicht
        beobachtbar.
        """
        def handler(route, request):
            if request.method == "POST":
                route.fulfill(
                    status=200, content_type="application/json",
                    body=json.dumps({"ok": True, "message": "Testantwort"}))
            else:
                route.continue_()

        self.page.route("**/api/ticket*", handler)
        self.page.route("**/api/feedback*", handler)

    def write_store(self, tickets):
        self.store_path.write_text(
            json.dumps({"version": 1, "tickets": tickets},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

    def read_store(self):
        return {item["id"]: item for item in json.loads(
            self.store_path.read_text(encoding="utf-8"))["tickets"]}

    def wait_until(self, predicate, timeout=8, message="Bedingung fehlt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(120)
        self.fail(message)

    def goto_work(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)
        self.page.goto(self.base + "/#/project/" + PROJECT + "/work")
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        self.page.locator("section[data-nv-ppanel='work']").wait_for(
            state="visible", timeout=20000)

    def editor(self):
        return self.page.locator("aside[data-nv-ticket-editor]").first

    def card(self, tid):
        return self.page.locator("article[data-nv-ticket='%s']" % tid).first

    def type_select(self, editor=None):
        return (editor or self.editor()).locator(
            "select[data-nv-field='ticket-type']")

    def open_new(self, mode):
        # Ein vorheriger Fehlschlag in einem subTest darf den nächsten
        # Öffnungsversuch nicht am Scrim scheitern lassen.
        if self.editor().count() and self.editor().is_visible():
            self.close_editor()
        self.page.locator("[data-nv-action='%s']" % NEW_ACTIONS[mode]).first.click()
        editor = self.editor()
        editor.wait_for(state="visible", timeout=6000)
        return editor

    def open_ticket_editor(self, tid):
        self.card(tid).locator(
            "button[data-nv-action='ticket-details']").first.click()
        detail = self.page.locator("[data-nv-ticket-detail='%s']" % tid).first
        detail.wait_for(state="visible", timeout=5000)
        detail.locator("button[data-nv-action='ticket-edit']").first.click()
        editor = self.editor()
        editor.wait_for(state="visible", timeout=5000)
        return editor

    def close_editor(self):
        self.editor().locator(
            "button[data-nv-action='ticket-cancel']").first.click()
        self.wait_until(lambda: not self.editor().is_visible(),
                        message="Der Editor lässt sich nicht schließen")

    # ================================== 1. Genau ein Typfeld (Vertrag A)
    def test_01_single_ticket_type_field_replaces_category(self):
        """Vor: leerer Store. Aktion: „Paket anlegen“ öffnen.

        Erwartung: genau ein ``select[data-nv-field='ticket-type']`` mit
        exakt feature/bug/feedback, kein ``[data-nv-field='category']``,
        keine Option ``task``/„Paket“ und ein aria-label als zugänglicher
        Name. Significance: der Nutzer wählt den Tickettyp nur einmal; der
        interne Typ ``task`` bleibt API-/Speicher-kompatibel, wird aber nicht
        mehr angeboten.
        """
        self.write_store([])
        self.goto_work()
        editor = self.open_new("package")

        types = self.type_select(editor)
        self.assertEqual(1, types.count(),
                         "Das Formular muss genau eine Typ-Auswahl haben")
        options = types.first.locator("option").evaluate_all(
            "els => els.map(e => ({value: e.value, text: e.textContent.trim()}))")
        self.assertEqual(EXPECTED_TYPES, {row["value"] for row in options},
                         "Die Typ-Optionen sind falsch: " + repr(options))
        self.assertEqual(3, len(options),
                         "Es gibt zusätzliche Typ-Optionen: " + repr(options))
        labels = " ".join(row["text"].lower() for row in options)
        self.assertNotIn("paket", labels,
                         "Die Option „Paket“ ist weiterhin im Typfeld")
        self.assertNotIn("package", labels,
                         "Die Option „Package“ ist weiterhin im Typfeld")
        self.assertEqual(
            0, editor.locator("[data-nv-field='category']").count(),
            "Das überlappende Kategorie-Feld existiert weiterhin")
        accessible = (types.first.get_attribute("aria-label") or "").strip()
        self.assertTrue(accessible,
                        "Die Typ-Auswahl hat keinen zugänglichen Namen")

    def test_02_buttons_preselect_the_type(self):
        """Vor: leerer Store, drei Anlage-Buttons.

        Aktion: Paket/Bug/Feedback öffnen und den Typ lesen. Erwartung:
        Vorauswahl feature/bug/feedback; der Typ bleibt vor dem Speichern
        änderbar. Significance: die Button-Beschriftung und das gespeicherte
        Ticket stimmen überein, ohne zweite Kategorie.
        """
        self.write_store([])
        self.goto_work()
        for mode, expected in (("package", "feature"), ("bug", "bug"),
                               ("feedback", "feedback")):
            with self.subTest(mode=mode):
                editor = self.open_new(mode)
                try:
                    select = self.type_select(editor).first
                    self.assertEqual(expected, select.input_value(),
                                     "Falsche Typ-Vorauswahl für %s" % mode)
                    other = "bug" if expected != "bug" else "feedback"
                    select.select_option(other)
                    self.assertEqual(other, select.input_value(),
                                     "Der Typ ist vor dem Speichern nicht änderbar")
                finally:
                    if self.editor().count() and self.editor().is_visible():
                        self.close_editor()

    # ====================== 2. Editor ändert den Zustand nie (Vertrag D)
    def test_03_editor_open_cancel_and_save_keep_the_state(self):
        """Vor: je ein draft- und ein open-Ticket. Aktion: Bearbeiten öffnen,
        kurz warten, abbrechen; erneut öffnen, Titel ändern, speichern.

        Erwartung: Zustand bleibt in beiden Fällen unverändert, weder Öffnen
        noch Abbrechen noch Speichern sendet ``action=state`` an
        ``/api/ticket``. Significance: der gemeldete Sprung draft →
        in-progress beim Abbrechen ist beseitigt; Zustandswechsel sind
        ausdrücklich (Board, Detail-Auswahl, DnD).
        """
        for tid, state in (("AP3", "draft"), ("AP1", "open")):
            with self.subTest(ticket=tid, state=state):
                self.write_store([ticket(tid, "Ruhiger Editor", state=state)])
                self.goto_work()
                editor = self.open_ticket_editor(tid)
                self.page.wait_for_timeout(500)  # kein asynchroner Nachtrag
                self.assertEqual(
                    [], self.api_writes("/api/ticket", "state"),
                    "Das Öffnen des Editors sendet einen Zustandswechsel")
                self.assertEqual(state, self.read_store()[tid]["state"],
                                 "Das Öffnen des Editors ändert den Zustand")
                self.close_editor()
                self.page.wait_for_timeout(200)
                self.assertEqual(
                    state, self.read_store()[tid]["state"],
                    "Abbrechen nimmt einen Zustandswechsel nicht zurück oder "
                    "ändert den Zustand")
                self.assertEqual(state, self.card(tid).get_attribute(
                    "data-nv-state"),
                    "Die Karte zeigt nach Abbrechen einen anderen Zustand")

                editor = self.open_ticket_editor(tid)
                editor.locator("input[data-nv-field='title']").first.fill(
                    "Geänderter Titel")
                editor.locator(
                    "button[data-nv-action='ticket-save']").first.click()
                self.wait_until(
                    lambda: self.read_store()[tid]["title"] == "Geänderter Titel",
                    message="Speichern übernimmt die Titeländerung nicht")
                self.assertEqual(
                    state, self.read_store()[tid]["state"],
                    "Speichern im Editor ändert den Zustand")
                self.assertEqual(
                    [], self.api_writes("/api/ticket", "state"),
                    "Der Editor sendet weiterhin einen automatischen "
                    "Zustandswechsel")

    # ======================== 3. Anlagewege (Verträge B und C)
    def test_04_creation_is_sent_to_the_ticket_api_with_type_and_draft(self):
        """Vor: leerer Store. Aktion: je Typ einen Titel speichern
        (Paket→feature, Bug→bug, Feedback→feedback); POSTs werden lokal
        beantwortet.

        Erwartung: ausschließlich ``POST /api/ticket`` mit ``action=add``,
        passendem ``type`` und ``state=draft``; kein ``/api/feedback``-POST.
        Significance: Bugs/Feedback landen im verbundenen Projekt über den
        GitHub-fähigen Anlageweg (Fehler 3) und neue Tickets bleiben Entwurf.
        """
        self.write_store([])
        self.goto_work()
        self.fake_ticket_writes()
        cases = (("package", "feature"), ("bug", "bug"),
                 ("feedback", "feedback"))
        for index, (mode, expected) in enumerate(cases):
            title = "B1-Anlage-%d" % index
            with self.subTest(mode=mode):
                editor = self.open_new(mode)
                editor.locator("input[data-nv-field='title']").first.fill(title)
                editor.locator(
                    "button[data-nv-action='ticket-save']").first.click()
                self.wait_until(
                    lambda: any(
                        isinstance(row["payload"], dict)
                        and row["payload"].get("title") == title
                        for row in self.api_writes("/api/ticket", "add")),
                    timeout=6,
                    message="Keine Anlage über /api/ticket für " + mode)
                payload = [row["payload"] for row in
                           self.api_writes("/api/ticket", "add")
                           if row["payload"].get("title") == title][0]
                self.assertEqual("add", payload.get("action"), payload)
                self.assertEqual(expected, payload.get("type"), payload)
                self.assertEqual("draft", payload.get("state"), payload)
                self.assertEqual(PROJECT, payload.get("name"), payload)
                feedback_adds = [
                    row["payload"] for row in
                    self.api_writes("/api/feedback", "add")
                    if isinstance(row["payload"], dict)
                    and row["payload"].get("title") == title]
                self.assertEqual([], feedback_adds,
                                 "Die Anlage läuft weiterhin über /api/feedback")
                self.wait_until(lambda: not self.editor().is_visible(),
                                timeout=6,
                                message="Der Editor schließt nach dem "
                                        "Speichern nicht")

    def test_05_offline_creation_uses_the_selected_type_and_type_prefix(self):
        """Vor: leerer Store, nicht verbundenes Projekt; ID-Feld geleert.

        Aktion: je Typ ein Ticket speichern. Erwartung: lokaler Eintrag mit
        dem gewählten Typ und typgerechter Auto-ID feature→AP<n>,
        bug→B<n>, feedback→F<n>; state bleibt draft. Significance: der
        gewählte Typ bestimmt Speichertyp und ID, auch ohne GitHub.
        """
        cases = (("package", "feature", r"^AP\d+$"),
                 ("bug", "bug", r"^B\d+$"),
                 ("feedback", "feedback", r"^F\d+$"))
        for mode, expected_type, id_pattern in cases:
            title = "Offline-" + mode
            with self.subTest(mode=mode):
                self.write_store([])
                self.goto_work()
                editor = self.open_new(mode)
                editor.locator("input[data-nv-field='id']").first.fill("")
                editor.locator("input[data-nv-field='title']").first.fill(title)
                editor.locator(
                    "button[data-nv-action='ticket-save']").first.click()
                self.wait_until(
                    lambda: any(row["title"] == title
                                for row in self.read_store().values()),
                    timeout=6,
                    message="Das lokale Ticket für %s wurde nicht angelegt" % mode)
                record = [row for row in self.read_store().values()
                          if row["title"] == title][0]
                self.assertEqual(expected_type, record.get("type"),
                                 "Der gewählte Typ wurde nicht gespeichert")
                self.assertRegex(str(record.get("id")), id_pattern,
                                 "Die Auto-ID folgt nicht dem Typ")
                self.assertEqual("draft", record.get("state"),
                                 "Ein neues Ticket muss Entwurf bleiben")

    # ================= 4. Manuelle Zustandswechsel bleiben möglich
    def test_06_manual_state_change_draft_to_open_still_works(self):
        """Vor: AP3 im Zustand draft. Aktion: Detail öffnen, Zustandsauswahl
        auf ``open`` setzen, „Zustand setzen“ klicken.

        Erwartung: die Auswahl bietet nur draft/open (in-progress und done
        gehören dem Läufer); der Speicher steht danach auf ``open`` und die
        Karte trägt ``data-nv-state=open``. Significance: Option A entfernt
        nur den automatischen Wechsel; die ausdrückliche Nutzerkontrolle
        (Bereit/Freigeben) bleibt erhalten.
        """
        self.write_store([ticket("AP3", "Manuell bereit", state="draft")])
        self.goto_work()
        self.card("AP3").locator(
            "button[data-nv-action='ticket-details']").first.click()
        detail = self.page.locator("[data-nv-ticket-detail='AP3']").first
        detail.wait_for(state="visible", timeout=5000)
        select = detail.locator("select[data-nv-ticket-state-select]").first
        self.assertEqual(
            {"draft", "open"},
            set(select.locator("option").evaluate_all(
                "els => els.map(e => e.value)")),
            "Die Zustandsauswahl bietet nicht genau die Nutzer-Zustände")
        select.select_option("open")
        detail.locator(
            "button[data-nv-action='ticket-state-save']").first.click()
        self.wait_until(lambda: self.read_store()["AP3"]["state"] == "open",
                        message="Der manuelle Wechsel draft→open wurde nicht "
                                "gespeichert")
        self.wait_until(
            lambda: self.card("AP3").get_attribute("data-nv-state") == "open",
            message="Die Karte zeigt nach dem manuellen Wechsel nicht open")

    def test_07_no_javascript_errors(self):
        """Vor: Work geöffnet. Aktion: Formular öffnen/schließen.

        Erwartung: keine ``pageerror``-Einträge. Significance: die
        Formularänderung darf keine JS-Fehler erzeugen, die Folgeaktionen
        still blockieren.
        """
        self.write_store([])
        self.goto_work()
        editor = self.open_new("feedback")
        self.assertTrue(editor.is_visible())
        self.close_editor()
        self.assertEqual([], self.page_errors,
                         "Die Work-Ansicht erzeugte JavaScript-Fehler")


# ===========================================================================
# Browserabnahme der Projektansicht „Work“ (unabhängig aus Ticket + SPEC)
# ===========================================================================

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

if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402


def isolated_env_gh56(root, home, port):
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
            env=isolated_env_gh56(cls.root, cls.home, cls.port),
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

    def test_12_no_manual_close_control_in_detail_or_editor(self):
        """GH-82: Abschließen ist dem Läufer vorbehalten, nicht dem Nutzer.

        Vorbedingung: offenes Ticket AP1. Aktion: Detail und Bearbeiten-
        Editor öffnen und beide auf Schließen-Steuerelemente prüfen.
        Erwartung: weder Kontext-Panel noch Editor bieten einen
        Schließen-/Paket-abschließen-Knopf; der Zustand bleibt ``open``.
        """
        self.write_store([ticket("AP1", "Abschlusskandidat GH56")])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        self.card("AP1").locator(
            "button[data-nv-action='ticket-details']").first.click()
        detail = self.page.locator("[data-nv-ticket-detail='AP1']").first
        detail.wait_for(state="visible", timeout=5000)

        def assert_no_close(scope):
            for action in ("ticket-close", "package-close"):
                self.assertEqual(
                    0, scope.locator(
                        f"button[data-nv-action='{action}']").count(),
                    f"Der Schließen-Knopf {action} ist noch vorhanden")
            self.assertNotRegex(
                " ".join(scope.locator("button").all_inner_texts()),
                r"(?i)schließen|schliessen|abschließen|abschliessen|close",
                "Ein Knopf bietet manuelles Schließen an")

        assert_no_close(detail)
        detail.locator("[data-nv-action='ticket-edit']").first.click()
        editor = self.editor()
        editor.wait_for(state="visible", timeout=5000)
        assert_no_close(editor)
        self.assertEqual("open", self.read_store()["AP1"]["state"],
                         "Das Öffnen von Detail/Editor hat den Zustand "
                         "verändert")
        self.assertEqual([], self.page_errors)

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

    def test_19_mobile_priority_view_shows_all_non_closed_except_draft(self):
        """Mobile Priorisierung zeigt alle nicht erledigten Status außer Draft.

        Vorbedingung: Tickets in draft/open/in-progress/blocked/
        waiting-merge/done, keine gespeicherte Priorisierung. Aktion: mobile
        Work-Ansicht. Erwartung: die Priorisierungszeilen enthalten In
        Progress, Ready, BLOCKIERT und WARTET AUF MERGE in dieser
        Statusreihenfolge; Draft und erledigt fehlen.
        """
        status, body = self.api_json("/api/priority", "POST", {
            "name": PROJECT, "action": "clear"})
        self.assertEqual(200, status, body)
        self.write_store([
            ticket("AP3", "Nur Entwurf", state="draft"),
            ticket("AP1", "Bereit zum Start"),
            ticket("AP2", "Läuft gerade", state="in-progress"),
            ticket("AP4", "Blockiert", state="blocked",
                   blocked_reason="externe Freigabe fehlt"),
            ticket("AP5", "Wartet auf Merge", state="waiting-merge"),
            ticket("AP6", "Erledigt", state="done", commit="abcdef1",
                   test="test_ap_done"),
        ])
        self.goto_work(viewport={"width": 600, "height": 800})
        strip = self.strip()
        strip.wait_for(state="visible", timeout=5000)
        ids = strip.locator("[data-nv-priority-id]").evaluate_all(
            "els => els.map(e => e.getAttribute('data-nv-priority-id'))")
        self.assertEqual(["AP2", "AP1", "AP4", "AP5"], ids,
                         "Die mobile Priorisierung zeigt nicht alle "
                         "nicht-erledigten Status in Statusreihenfolge")

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


# ===========================================================================
# Browserabnahme „Projekt/Work“ (unabhängig aus Ticket + SPEC)
# ===========================================================================

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

if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402

DESKTOP = {"width": 1500, "height": 1100}
MOBILE = {"width": 600, "height": 800}


def isolated_env_gh67(root, home, port):
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
            env=isolated_env_gh67(cls.root, cls.home, cls.port),
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
        """Tickettyp-Auswahl im Editor (nach B1 das einzige Typfeld).

        Vertrag A: genau ein ``data-nv-field='ticket-type'`` mit den Optionen
        feature/bug/feedback. ``data-nv-field='type'`` ist im Projekt für den
        Projekttyp reserviert und wird nicht mehr als Fallback akzeptiert.
        """
        selected = editor.locator("[data-nv-field='ticket-type']")
        self.assertEqual(
            1, selected.count(),
            "Dem Anlageformular fehlt die eindeutige Tickettyp-Auswahl "
            "(data-nv-field='ticket-type')")
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

    def test_08_priority_strip_shows_non_closed_states_on_mobile(self):
        """AP2: Mobile zeigt den Strip mit In Progress und Ready, nicht Draft.

        Vorbedingung: draft/open/in-progress, 600x800, keine gespeicherte
        Priorisierung. Aktion: Work öffnen. Erwartung: Strip sichtbar;
        In Progress und Ready erscheinen als Zeilen, Draft nicht, und
        In Progress steht vor Ready.
        """
        self.set_priority([])
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
        self.assertEqual(["AP2", "AP1"], ids,
                         "Der Strip zeigt nicht alle unterstützten "
                         "nicht-erledigten Status in Statusreihenfolge")

    def test_08a_mobile_priority_status_precedes_priority(self):
        """In Progress steht vor Ready, auch bei schlechterer Priorität.

        Vorbedingung: Ready mit P0 steht im Speicher vor In Progress mit P8,
        keine gespeicherte Priorisierung, mobiler Viewport. Aktion: Work
        öffnen. Erwartung: der Strip nennt zuerst In Progress, dann Ready.
        """
        self.set_priority([])
        self.write_store([
            ticket("AP1", "Ready P0", priority="P0"),
            ticket("AP2", "Running P8", state="in-progress", priority="P8"),
        ])
        self.goto_work(viewport=MOBILE)
        strip = self.strip()
        strip.wait_for(state="visible", timeout=5000)
        ids = strip.locator("[data-nv-priority-id]").evaluate_all(
            "els => els.map(e => e.getAttribute('data-nv-priority-id'))")
        self.assertEqual(["AP2", "AP1"], ids,
                         "Ready P0 schlägt In Progress P8")

    def test_08b_mobile_priority_orders_only_within_status_group(self):
        """Priorität sortiert nur innerhalb der Statusgruppen.

        Vorbedingung: Ready P1, Ready P0, In Progress P1, In Progress P0 und
        In Progress ohne Priorität (Speicherreihenfolge wie genannt), mobile
        Work. Erwartung: erst alle In-Progress-Tickets nach Priorität, dann
        die Ready-Tickets nach Priorität; „ohne“ steht hinter P1.
        """
        self.set_priority([])
        self.write_store([
            ticket("AP1", "Ready P1", priority="P1"),
            ticket("AP2", "Ready P0", priority="P0"),
            ticket("AP3", "Running P1", state="in-progress", priority="P1"),
            ticket("AP4", "Running P0", state="in-progress", priority="P0"),
            ticket("AP5", "Running ohne", state="in-progress"),
        ])
        self.goto_work(viewport=MOBILE)
        strip = self.strip()
        strip.wait_for(state="visible", timeout=5000)
        ids = strip.locator("[data-nv-priority-id]").evaluate_all(
            "els => els.map(e => e.getAttribute('data-nv-priority-id'))")
        self.assertEqual(["AP4", "AP3", "AP5", "AP2", "AP1"], ids,
                         "Priorität wurde nicht nur innerhalb der "
                         "Statusgruppen angewendet")

    def test_08c_mobile_priority_orders_other_states_before_priority(self):
        """Sonstige Status folgen der Statusreihenfolge, dann der Priorität.

        Vorbedingung: WARTET AUF MERGE P0, BLOCKIERT P0, BLOCKIERT P8,
        WARTET AUF MERGE P8, Ready und In Progress (Speicherreihenfolge wie
        genannt), mobile Work. Erwartung: In Progress, Ready, dann BLOCKIERT
        (P0 vor P8) vor WARTET AUF MERGE (P0 vor P8).
        """
        self.set_priority([])
        self.write_store([
            ticket("AP1", "Waiting P0", state="waiting-merge", priority="P0"),
            ticket("AP2", "Blocked P0", state="blocked", priority="P0"),
            ticket("AP3", "Blocked P8", state="blocked", priority="P8"),
            ticket("AP4", "Waiting P8", state="waiting-merge", priority="P8"),
            ticket("AP5", "Ready"),
            ticket("AP6", "Running", state="in-progress"),
        ])
        self.goto_work(viewport=MOBILE)
        strip = self.strip()
        strip.wait_for(state="visible", timeout=5000)
        ids = strip.locator("[data-nv-priority-id]").evaluate_all(
            "els => els.map(e => e.getAttribute('data-nv-priority-id'))")
        self.assertEqual(["AP6", "AP5", "AP2", "AP3", "AP1", "AP4"], ids,
                         "Sonstige Status folgen nicht der definierten "
                         "Statusreihenfolge vor der Priorität")

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

    # ========================================== 5. Einheitlicher Tickettyp
    def test_21_single_ticket_type_field_replaces_category(self):
        """B1/A: genau ein Typfeld feature/bug/feedback, keine Kategorie.

        Vorbedingung: leerer Store. Aktion: „Paket anlegen“ öffnen.
        Erwartung: genau ein ``select[data-nv-field='ticket-type']`` mit genau
        diesen Optionen (lokalisierte Anzeige), keine Option task/„Paket“,
        kein ``[data-nv-field='category']``, Vorauswahl feature.
        """
        self.write_store([])
        self.goto_work()
        editor = self.open_new("package")
        select = self.ticket_type_select(editor)
        options = select.locator("option").evaluate_all(
            "els => els.map(e => ({value: e.value, text: e.textContent.trim()}))")
        self.assertEqual({"feature", "bug", "feedback"},
                         {row["value"] for row in options},
                         "Die Typ-Optionen sind falsch: " + repr(options))
        self.assertNotIn("task", {row["value"] for row in options},
                         "Die interne Option task wird weiterhin angeboten")
        labels = " ".join(row["text"].lower() for row in options)
        self.assertNotIn("paket", labels,
                         "Die Option „Paket“ ist weiterhin im Typfeld")
        self.assertEqual(0, editor.locator("[data-nv-field='category']").count(),
                         "Das überlappende Kategorie-Feld existiert weiterhin")
        self.assertEqual("feature", select.input_value(),
                         "Die Typ-Vorauswahl von „Paket anlegen“ ist nicht feature")

    def test_22_ticket_type_options_and_button_defaults(self):
        """B1/A: Typoptionen feature/bug/feedback, Vorauswahl je Button.

        Vorbedingung: drei Öffnungsbuttons. Aktion: Paket/Bug/Feedback öffnen.
        Erwartung: Optionen feature/bug/feedback, aria-label vorhanden,
        Default feature / bug / feedback.
        """
        self.write_store([])
        self.goto_work()
        expected = {"package": "feature", "bug": "bug", "feedback": "feedback"}
        for mode, default in expected.items():
            with self.subTest(mode=mode):
                editor = self.open_new(mode)
                try:
                    select = self.ticket_type_select(editor)
                    options = select.locator("option").evaluate_all(
                        "els => els.map(e => e.value)")
                    self.assertEqual({"feature", "bug", "feedback"},
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

    def test_23_ticket_type_stays_changeable_before_save(self):
        """B1/A: der Typ bleibt bis zum Speichern änderbar.

        Vorbedingung: „Paket anlegen“ (Vorauswahl feature). Aktion: Typ auf
        bug und danach auf feedback stellen. Erwartung: die Auswahl folgt
        jeweils; das Feld bleibt das einzige Typfeld (keine Kategorie).
        """
        self.write_store([])
        self.goto_work()
        editor = self.open_new("package")
        select = self.ticket_type_select(editor)
        self.assertEqual("feature", select.input_value())
        for value in ("bug", "feedback"):
            with self.subTest(value=value):
                select.select_option(value)
                self.assertEqual(value, select.input_value(),
                                 "Der Typ lässt sich nicht auf %s ändern" % value)
        self.assertEqual(0, editor.locator("[data-nv-field='category']").count(),
                         "Das Kategorie-Feld besteht weiterhin")

    def test_24_changed_ticket_type_is_saved(self):
        """B1/B+C: geänderter Tickettyp wird gespeichert, nicht die Vorauswahl.

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
    def test_26_hide_done_next_to_search_and_effective(self):
        """GH-108: „Show done“ direkt rechts neben der Suche und wirksam.

        Vorbedingung: ein done-Ticket. Aktion: Work öffnen, Show-done klicken.
        Erwartung: der Button liegt in ``[data-nv-filter-bar]`` unmittelbar
        nach dem Suchfeld; done ist standardmäßig verborgen und danach
        sichtbar.
        """
        self.write_store([
            ticket("AP4", "Fertig", state="done", commit="abcdef1", test="t")])
        self.goto_work()
        placement = self.page.evaluate("""() => {
          const btn = document.querySelector('button[data-nv-work-hide-done]');
          if (!btn) return {present: false};
          const prev = btn.previousElementSibling;
          return {
            present: true,
            inFilterBar: !!btn.closest('[data-nv-filter-bar]'),
            inWork: !!btn.closest("section[data-nv-ppanel='work']"),
            afterSearch: !!prev && prev.hasAttribute('data-nv-search')
          };
        }""")
        self.assertTrue(placement["present"], "Show-done fehlt")
        self.assertTrue(placement["inFilterBar"],
                        "Show-done fehlt in der Filterleiste")
        self.assertTrue(placement["inWork"],
                        "Show-done liegt außerhalb der Work-Sektion")
        self.assertTrue(placement["afterSearch"],
                        "Show-done steht nicht direkt neben der Suche")
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

    def test_28_quick_filters_above_search_desktop(self):
        """GH-108: Schnellfilter stehen über der Suche, nicht nebeneinander.

        Vorbedingung: 1500x1100. Erwartung: ``[data-nv-work-kinds]`` liegt
        vollständig über ``div[data-nv-search]``; die beiden Gruppen
        überlappen sich nicht.
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
        self.assertLessEqual(
            kinds["bottom"], search["top"] + 4,
            "Die Schnellfilter stehen nicht über der Suche: " + repr(boxes))
        overlap_y = not (kinds["bottom"] <= search["top"]
                         or search["bottom"] <= kinds["top"])
        self.assertFalse(overlap_y,
                         "Suche und Schnellfilter überlappen sich")

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
        """AP3/B1: englische Standardtexte vollständig, keine Rohschlüssel.

        Vorbedingung: leerer Store, Englisch aktiv. Aktion: Formular öffnen,
        Priorisierung (mobile) und Work-Text lesen. Erwartung: Tickettyp
        beschriftet, keine Kategorie mehr, keine „undefined“/„[object“.
        """
        self.write_store([ticket("AP1", "Ready")])
        self.goto_work()
        editor = self.open_new("package")
        editor_text = editor.inner_text()
        self.assertIn("Ticket", editor_text,
                      "Der Tickettyp ist im englischen UI nicht beschriftet")
        self.assertNotIn("Category", editor_text,
                         "Die entfernte Kategorie wird weiterhin angezeigt")
        self.assertNotRegex(editor_text, r"undefined|\[object",
                            "Das Formular enthält technische Platzhalter")

    def test_31_german_work_texts_are_translated(self):
        """AP3/B1: deutsche Texte für Tickettyp und Zähler.

        Vorbedingung: Ready-Ticket, I18N.set('de'). Aktion: Formular öffnen,
        mobile Priorisierung lesen. Erwartung: deutsche Beschriftung des
        Tickettyps, keine Kategorie, deutscher Zähler mit korrekter Zahl,
        keine Rohschlüssel.
        """
        self.write_store([ticket("AP1", "Ready"), ticket("AP2", "Ready2")])
        self.set_priority(["AP1", "AP2"])
        self.goto_work()
        self.set_lang("de")
        self.assertEqual("de", self.page.evaluate(
            "() => (window.VIBE_I18N || window.I18N).current()"))
        editor = self.open_new("package")
        editor_text = editor.inner_text()
        self.assertRegex(editor_text, r"Ticket ?typ|Ticketart|Tickettyp",
                         "Der Tickettyp ist auf Deutsch nicht übersetzt")
        self.assertNotIn("Kategorie", editor_text,
                         "Die entfernte Kategorie wird weiterhin angezeigt")
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
        """AP3/B1: interne IDs/Statuswerte bleiben in beiden Sprachen unverändert.

        Vorbedingung: Englisch. Aktion: Tickettyp-Optionen und data-nv-state
        lesen, auf Deutsch umstellen, erneut lesen. Erwartung: options values
        feature/bug/feedback und Rohzustände identisch.
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
                    values = self.ticket_type_select(editor).locator(
                        "option").evaluate_all("els => els.map(e => e.value)")
                    self.assertEqual(expected, set(values),
                                     "Interne Typ-IDs ändern sich mit der Sprache")
                finally:
                    self.page.keyboard.press("Escape")
                    self.wait_until(lambda: not self.editor().is_visible(),
                                    message="Editor schließt nicht")
        self.assertEqual("draft", self.card("AP3").get_attribute("data-nv-state"))
        self.assertEqual("open", self.card("AP1").get_attribute("data-nv-state"))

    # ============================================ 8. Dialogaktionen
    def test_33_cancel_discards_changes(self):
        """AP7/B1: „Cancel“ speichert nichts und lässt den Zustand in Ruhe.

        Vorbedingung: Ticket „Original“ im Zustand draft. Aktion: (a) Editor
        ohne Änderung abbrechen, (b) Titel ändern und abbrechen. Erwartung:
        Editor schließt, Store-Titel bleibt in beiden Fällen unverändert und
        der Zustand bleibt draft (kein automatischer in-progress-Wechsel).
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
                self.assertEqual(
                    "draft", self.read_store()["AP1"]["state"],
                    "Cancel hat den Zustand verändert (B1: der Editor darf "
                    "keinen automatischen Wechsel auslösen)")

    def test_34_editor_offers_no_manual_close_action(self):
        """GH-82: auch der Bearbeiten-Editor darf nicht schließen.

        Vorbedingung: offenes Ticket. Aktion: Editor öffnen und nach
        Schließen-Knöpfen suchen. Erwartung: weder ``ticket-close`` noch
        ``package-close`` sind vorhanden; der Zustand bleibt ``open``.
        """
        self.write_store([ticket("AP1", "Abschluss GH67")])
        self.goto_work()
        editor = self.open_ticket_editor("AP1")
        for action in ("ticket-close", "package-close"):
            self.assertEqual(
                0, editor.locator(
                    f"button[data-nv-action='{action}']").count(),
                f"Der Schließen-Knopf {action} fehlt nicht im Editor")
        self.assertNotRegex(
            " ".join(editor.locator("button").all_inner_texts()),
            r"(?i)schließen|schliessen|abschließen|abschliessen|close",
            "Der Editor bietet manuelles Schließen an")
        self.assertEqual("open", self.read_store()["AP1"]["state"],
                         "Das Öffnen des Editors hat den Zustand verändert")

    # ============================ 9. Editor ändert den Zustand nie (B1/D)
    def test_35_open_editor_from_draft_keeps_draft(self):
        """B1/D: das Öffnen des Editors setzt kein in-progress mehr.

        Vorbedingung: Ticket im Zustand draft. Aktion: Details → Bearbeiten,
        kurz warten. Erwartung: Store bleibt draft, die Karte bleibt in
        ``article[data-nv-col='draft']`` mit data-nv-state='draft'; kein
        Voll-Neuladen. Zustandswechsel gibt es nur noch ausdrücklich über
        Board, Detail-Auswahl und Drag&Drop.
        """
        self.write_store([ticket("AP3", "Draft in Bearbeitung", state="draft")])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        self.set_marker()
        self.open_ticket_editor("AP3")
        self.page.wait_for_timeout(500)
        self.assertEqual(
            "draft", self.read_store()["AP3"]["state"],
            "Das Öffnen des Editors hat den Zustand automatisch geändert")
        self.assert_marker_alive()
        self.assertEqual(
            1, self.col("draft").locator(
                "article[data-nv-ticket='AP3']").count(),
            "Die Draft-Karte wurde automatisch in eine andere Spalte bewegt")
        self.assertEqual(
            "draft", self.card("AP3").get_attribute("data-nv-state"),
            "Die Karte trägt einen anderen Rohzustand")
        self.assertNotIn("in progress", self.card_state_text("AP3").lower(),
                         "Die Karte zeigt ein automatisches In-Progress-Badge")
        self.page.keyboard.press("Escape")
        self.wait_until(lambda: not self.editor().is_visible(),
                        message="Der Editor lässt sich nicht schließen")
        self.assertEqual("draft", self.read_store()["AP3"]["state"],
                         "Escape/Abbrechen hat den Zustand verändert")

    def test_36_open_editor_from_open_keeps_open(self):
        """B1/D: gleiche Regel für ein Ticket im Zustand open.

        Vorbedingung: Ticket state=open. Aktion: Editor öffnen und abbrechen.
        Erwartung: Store und Karte bleiben open/ready; kein Voll-Neuladen.
        """
        self.write_store([ticket("AP1", "Ready in Bearbeitung")])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        self.set_marker()
        editor = self.open_ticket_editor("AP1")
        self.page.wait_for_timeout(500)
        self.assertEqual(
            "open", self.read_store()["AP1"]["state"],
            "Ein offenes Ticket wechselt beim Öffnen des Editors den Zustand")
        self.assertNotIn("in progress", self.card_state_text("AP1").lower(),
                         "Die Karte zeigt ein automatisches In-Progress-Badge")
        editor.locator("button[data-nv-action='ticket-cancel']").first.click()
        self.wait_until(lambda: not self.editor().is_visible(),
                        message="Cancel schließt den Editor nicht")
        self.assert_marker_alive()
        self.assertEqual("open", self.read_store()["AP1"]["state"],
                         "Cancel hat den Zustand verändert")

    def test_37_editor_does_not_reset_search_or_filters(self):
        """B1/D: Öffnen/Abbrechen erhält DOM, Suche und Schnellfilter.

        Vorbedingung: zwei Tickets, Suchbegriff und Typ-Chip aktiv, Marker.
        Aktion: Editor des passenden Tickets öffnen und abbrechen. Erwartung:
        Store bleibt draft, Suche/aria-pressed unverändert, DOM-Marker
        erhalten.
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
        editor = self.open_ticket_editor("AP3")
        self.page.wait_for_timeout(400)
        self.assertEqual("draft", self.read_store()["AP3"]["state"],
                         "Der Editor hat den Zustand automatisch geändert")
        self.assert_marker_alive()
        self.assertEqual("Alpha", search.input_value(),
                         "Der Suchbegriff ging beim Öffnen des Editors verloren")
        self.assertEqual("true", chip.get_attribute("aria-pressed"),
                         "Die Filtereinstellung ging beim Öffnen verloren")
        editor.locator("button[data-nv-action='ticket-cancel']").first.click()
        self.wait_until(lambda: not self.editor().is_visible(),
                        message="Cancel schließt den Editor nicht")

    def test_38_editor_does_not_change_state_applies_even_on_cancel(self):
        """B1/D: Abbrechen lässt Zustand und Titel unverändert.

        Vorbedingung: Draft-Ticket „Original“. Aktion: Editor öffnen, Titel
        ändern, ticket-cancel klicken. Erwartung: state bleibt draft; Titel
        bleibt „Original“; Karte bleibt in der Draft-Spalte.
        """
        self.write_store([ticket("AP3", "Original", state="draft")])
        self.goto_work()
        self.board().wait_for(state="visible", timeout=5000)
        editor = self.open_ticket_editor("AP3")
        editor.locator("input[data-nv-field='title']").first.fill(
            "Nur lokal geändert")
        editor.locator("button[data-nv-action='ticket-cancel']").first.click()
        self.wait_until(lambda: not self.editor().is_visible(),
                        message="Cancel schließt den Editor nicht")
        self.assertEqual("draft", self.read_store()["AP3"]["state"],
                         "Cancel hat den Zustand verändert")
        self.assertEqual("Original", self.read_store()["AP3"]["title"],
                         "Cancel hat die Titeländerung gespeichert")
        self.assertEqual(
            1, self.col("draft").locator(
                "article[data-nv-ticket='AP3']").count(),
            "Die Karte ist nach Cancel nicht mehr in der Draft-Spalte")


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
