"""Browserabnahme AP22, Meilenstein B: Arbeit (Liste, Feedback, Priorisierung).

Die Fälle leiten sich aus ``docs/features/AP22.md`` („Projektansicht → Arbeit“)
ab. Das echte Dashboard läuft isoliert auf freiem Port; Chromium kommt aus
dem Nur-Lese-Cache. Getestet wird ausschließlich über die ``data-nv-*``-Hooks
des Vertrags.

Testfälle (Kurzfassung; Details in den Methoden)
-----------------------------------------------
``BoardTest.test_columns_and_tickets_follow_the_fixture_states``
    Vorbedingung: zwei offene, ein blockiertes, ein erledigtes Paket sowie
    zwei Feedback-Einträge ohne Nachweis. Erwartung: F34 — kein Board;
    Reihenfolge Aktionsleiste → Filterleiste → Priorisierung → Liste;
    ``AP-101``/``AP-102`` (offen), ``AP-103`` (BLOCKIERT),
    ``BUG-7``/``FB-1`` (ohne Nachweis), ``AP-104`` (erledigt) in der
    ``div[data-nv-ticket-list]`` mit ``data-nv-kind``, ``data-nv-state``-Pille
    und Kennung im Text.
``FeedbackListTest.test_feedback_list_shows_kind_badges``
    Erwartung: F34 — Feedback ist in der gemeinsamen Liste (keine
    ``details[data-nv-feedback-box]``); die ``article[data-nv-feedback-item]``
    tragen ``data-nv-kind`` und ``span.nv-kind-badge`` (Bug/Feedback).
``CreateTest.test_create_package_and_cancel_the_form``
    Aktion: ``new-package``, Titel/Beschreibung speichern; danach erneut
    öffnen und abbrechen. Erwartung: neue Karte in ``div[data-nv-ticket-list]``,
    Datei geschrieben; Abbrechen blendet das Formular ohne Eintrag aus.
``EditTest.test_edit_prefills_and_saves_only_the_chosen_ticket``
    Aktion: Klick auf ``article[data-nv-ticket='AP-101']`` →
    ``button[data-nv-action='ticket-edit']`` im Kontext-Panel
    (``[data-nv-ticket-detail='AP-101']``); Titel ändern, speichern.
    Erwartung: Formular ist vorbefüllt; die Änderung erscheint,
    ``AP-102`` bleibt unverändert.
``DeleteTest.test_delete_removes_the_card``
    Aktion: Klick auf ``article[data-nv-ticket='AP-101']`` →
    ``button[data-nv-action='ticket-delete']`` im Kontext-Panel
    (Bestätigung wird akzeptiert). Erwartung: Karte und Eintrag sind
    verschwunden, die übrigen bleiben.
``FeedbackCreateTest.test_create_bug_and_feedback_entries``
    Aktion: ``new-bug`` und ``new-feedback`` ausfüllen und speichern.
    Erwartung: beide erscheinen in der ``div[data-nv-ticket-list]`` mit
    ``data-nv-kind`` (Bug/Feedback-Badge).
``PriorityTest.test_priority_card_appears_with_feature_and_persists``
    Vorbedingung: Feature ``priority`` aus. Aktion: Schalter in den
    Einstellungen aktivieren, Arbeit öffnen, ein Paket hochschieben und
    speichern, neu laden. Erwartung: ``[data-nv-priority]`` erscheint mit
    Zeilen und Knöpfen; die Reihenfolge bleibt über den Reload erhalten.
``FormErrorTest.test_empty_title_shows_error_and_creates_nothing``
    Aktion: Paket ohne Titel speichern. Erwartung: ``[data-nv-form-error]``
    im Formular sichtbar, Datei unverändert, keine neue Karte.

Vertragsunklarheiten (bewusst so geprüft und dokumentiert)
----------------------------------------------------------
1. **Nachweis-Badge.** ``ohne Nachweis`` ist kein Zustand mehr, sondern ein
   Badge (``span[data-nv-proof]``) am Eintrag (Backend liefert
   ``ohne Nachweis`` für unbeglichene Feedback ohne Nachweis).
2. **Art-Badge.** Der Vertrag nennt „Badge ``span.nv-kind-badge``
   (bug|feedback) + linke Farbkante“; ``data-nv-kind`` wird auf der Karte
   getragen.
3. **Löschbestätigung.** Der Vertrag nennt kein Bestätigungsformat. Ein
   nativer Dialog wird akzeptiert; erscheint eine eingebettete Bestätigung,
   wird der sichtbare Bestätigungsknopf geklickt.

F34-Anpassungen
---------------
* ``BoardTest.test_columns_and_tickets_follow_the_fixture_states``: Der F34-
  Vertrag entfernt das Board komplett (Absence: ``.nv-board``,
  ``[data-nv-col]``). Drum herum gehört die Reihenfolge Aktionsleiste →
  Filterleiste → Priorisierung → Liste (per ``compareDocumentPosition``), die
  Karten liegen in ``div[data-nv-ticket-list]``; ``data-nv-kind``
  (package|bug|feedback) und ``data-nv-state`` (offen, BLOCKIERT,
  ohne Nachweis, erledigt) trägt der Eintrag.
* ``FeedbackListTest.test_feedback_list_shows_kind_badges``: F34: Feedback ist
  in der gemeinsamen Liste — Absence ``details[data-nv-feedback-box]``; die Art
  wird per ``data-nv-kind`` geprüft.
* ``CreateTest.test_create_package_and_cancel_the_form``: F34: Die neue Karte
  erscheint in ``div[data-nv-ticket-list]`` (keine Spalte mehr).
* ``EditTest.test_edit_prefills_and_saves_only_the_chosen_ticket``: F34: Klick
  auf die Karte öffnet das Kontext-Panel (``[data-nv-ticket-detail='<id>']``);
  ``ticket-edit`` (nv-secondary) steht im Panel — die Card selbst bietet keinen
  Edit-Knopf (Absence auf ``article[data-nv-ticket]``).
* ``DeleteTest.test_delete_removes_the_card``: F34: ``ticket-delete`` (nv-danger)
  steht im Kontext-Panel — die Card selbst bietet keinen Lösch-Knopf (Absence).
  Löschen mit Bestätigung: Karte und Datei verschwinden, übrige bleiben.
* ``FeedbackCreateTest.test_create_bug_and_feedback_entries``: F34: Bug/Feedback
  sind dieselben Listeneinträge (``article[data-nv-feedback-item]``), die Art
  über ``data-nv-kind`` auszeichnet; keine eigene Feedback-Sektion mehr.
"""
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
        # Ordnung: Aktionsleiste → Filterleiste → Board. GH-67: die
        # Priorisierungsansicht liegt auf Desktop nicht im DOM; die
        # Reihenfolge-Prüfung für den Strip erfolgt in den PriorityTest-
        # Fällen bzw. in test_gh67_work_ui.py (mobil).
        self.assertTrue(
            self._follows("[data-nv-action='new-package']", "[data-nv-filter-bar]"),
            "Die Aktionsleiste steht nicht vor der Filterleiste")
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
        # GH-67: „Show done“ ist ein eigenständiger Schalter außerhalb der
        # Filterleiste, und der Done-Schnellfilter entfällt.
        self.assertEqual(
            0, filter_bar.locator("[data-nv-work-hide-done]").count(),
            "Show-done liegt wider Erwarten in der Filterleiste")
        self.assertEqual(
            1, self.page.locator("button[data-nv-work-hide-done]").count(),
            "Der Knopf [data-nv-work-hide-done] fehlt")
        for state in ("draft", "ready", "running"):
            self.assertEqual(
                1, filter_bar.locator(
                    f"button[data-nv-work-state='{state}']").count(),
                f"Der Status-Chip {state} fehlt in der Filterleiste")
        self.assertEqual(
            0, filter_bar.locator("button[data-nv-work-state='done']").count(),
            "Der Done-Schnellfilter gibt es nicht mehr")

        # Erledigte einblenden (hideDone startet true), damit AP-104 sitzt.
        self.page.locator("[data-nv-work-hide-done]").first.click()

        expected = {
            "AP-101": ("package", "open", "ready"),
            "AP-102": ("package", "open", "ready"),
            "AP-103": ("package", "blocked", "ready"),
            "BUG-7": ("bug", "open", "ready"),
            "FB-1": ("feedback", "open", "ready"),
            "AP-104": ("package", "done", "ready"),
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


if __name__ == "__main__":
    unittest.main()
