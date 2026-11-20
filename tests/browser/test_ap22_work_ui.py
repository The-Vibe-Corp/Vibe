"""Browserabnahme AP22, Meilenstein B: Arbeit (Board), Feedback, Priorisierung.

Die Fälle leiten sich aus ``docs/features/AP22.md`` („Projektansicht → Arbeit
(Board)“) ab. Das echte Dashboard läuft isoliert auf freiem Port; Chromium
kommt aus dem Nur-Lese-Cache. Getestet wird ausschließlich über die
``data-nv-*``-Hooks des Vertrags.

Testfälle (Kurzfassung; Details in den Methoden)
-----------------------------------------------
``BoardTest.test_columns_and_tickets_follow_the_fixture_states``
    Vorbedingung: zwei offene, ein blockiertes, ein erledigtes Paket sowie
    zwei Feedback-Einträge ohne Nachweis. Erwartung: vier beschriftete
    Spalten ``open|blocked|proof|done``; die Karten liegen mit Titel und
    Rohstatus in der richtigen Spalte.
``FeedbackListTest.test_feedback_list_shows_kind_badges``
    Erwartung: ``[data-nv-feedback]`` listet beide Einträge, der Bug trägt
    ein Bug-Badge, das gewöhnliche Feedback ein Feedback-Badge.
``CreateTest.test_create_package_and_cancel_the_form``
    Aktion: ``new-package``, Titel/Beschreibung speichern; danach erneut
    öffnen und abbrechen. Erwartung: neue Karte in ``open``, Datei
    geschrieben; Abbrechen blendet das Formular ohne Eintrag aus.
``EditTest.test_edit_prefills_and_saves_only_the_chosen_ticket``
    Aktion: ``ticket-edit`` an ``AP-OPEN``. Erwartung: Formular ist
    vorbefüllt; die Änderung erscheint, ``AP-OPEN2`` bleibt unverändert.
``DeleteTest.test_delete_removes_the_card``
    Aktion: ``ticket-delete`` (Bestätigung wird akzeptiert). Erwartung:
    Karte und Eintrag sind verschwunden, die übrigen bleiben.
``FeedbackCreateTest.test_create_bug_and_feedback_entries``
    Aktion: ``new-bug`` und ``new-feedback`` ausfüllen und speichern.
    Erwartung: beide erscheinen mit dem richtigen Art-Badge.
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
1. **Nachweis-Spalte.** ``ohne Nachweis`` entsteht laut Backend nur bei
   ``FEEDBACK.md``-Einträgen (bei ``TICKETS.md`` genügt die Checkbox). Die
   Fixtures legen deshalb Feedback-Einträge mit ungültigem Commit an und
   erwarten sie als Board-Karten in ``proof``.
2. **Art-Badge.** Der Vertrag nennt nur „Art-Badge (bug|feedback)“, keinen
   eigenen Hook. Geprüft wird der sichtbare Text ``Bug`` bzw. ``Feedback``
   im jeweiligen ``article[data-nv-feedback-item]``.
3. **Spaltenbeschriftung.** Der Vertrag legt keinen Wortlaut fest. Geprüft
   werden die vier Hooks, ``<html lang="en">`` und eine nichtleere
   Beschriftung je Spalte.
4. **Priorisierungszeilen.** Für die Zeilen nennt der Vertrag keinen Hook.
   Die Zeile wird über den Pakettext und den enthaltenen
   ``priority-up``-Knopf gefunden.
5. **Löschbestätigung.** Der Vertrag nennt kein Bestätigungsformat. Ein
   nativer Dialog wird akzeptiert; erscheint eine eingebettete Bestätigung,
   wird der sichtbare Bestätigungsknopf geklickt.
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

TICKETS = """# TICKETS — AP22 Test

- [ ] AP-OPEN Offenes Paket
  Beschreibung: Noch offen.

- [ ] AP-OPEN2 Zweites offenes Paket
  Beschreibung: Ebenfalls offen.

- [ ] AP-BLOCK Blockiertes Paket
  Beschreibung: Wartet auf Freigabe.
  BLOCKIERT: externe Freigabe fehlt

- [x] AP-DONE Erledigtes Paket
  Beschreibung: Fertig.
"""

FEEDBACK = """# FEEDBACK — AP22 Test

- [x] BUG-7 Absturz beim Start
  Beschreibung: Fenster bleibt leer.
  Art: Bug
  Commit: 1234567; Test: test_start

- [x] FB-1 Wunsch für die Oberfläche
  Beschreibung: Bitte größere Schaltflächen.
  Commit: 7654321; Test: test_ui
"""


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
        (self.project / "TICKETS.md").write_text(TICKETS, encoding="utf-8")
        (self.project / "FEEDBACK.md").write_text(FEEDBACK, encoding="utf-8")
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

    def ticket_text(self):
        return (self.project / "TICKETS.md").read_text(encoding="utf-8")

    def feedback_text(self):
        return (self.project / "FEEDBACK.md").read_text(encoding="utf-8")

    def card(self, ticket_id):
        return self.page.locator(
            f"article[data-nv-ticket='{ticket_id}']").first

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
        """Vorbedingung: Fixtures in allen vier Zuständen.

        Erwartung: Vier beschriftete Spalten; ``AP-OPEN``/``AP-OPEN2`` in
        ``open``, ``AP-BLOCK`` in ``blocked``, ``BUG-7``/``FB-1`` in
        ``proof``, ``AP-DONE`` in ``done``. Die Karten tragen Titel und
        ``data-nv-state`` mit dem Rohstatus des Backends.
        """
        self.open_work()
        self.assertEqual(
            "en", self.page.evaluate("() => document.documentElement.lang"),
            "Die Standardsprache der Oberfläche ist nicht Englisch")
        for column in ("open", "blocked", "proof", "done"):
            locator = self.page.locator(f"[data-nv-col='{column}']")
            self.assertEqual(1, locator.count(), f"Board-Spalte {column!r} fehlt")
            self.assertTrue(locator.first.is_visible(),
                            f"Board-Spalte {column!r} ist nicht sichtbar")
            self.assertTrue((locator.first.inner_text() or "").strip(),
                            f"Board-Spalte {column!r} ist unbeschriftet")

        expected = {
            "AP-OPEN": ("open", "offen"),
            "AP-OPEN2": ("open", "offen"),
            "AP-BLOCK": ("blocked", "BLOCKIERT"),
            "BUG-7": ("proof", "ohne Nachweis"),
            "FB-1": ("proof", "ohne Nachweis"),
            "AP-DONE": ("done", "erledigt"),
        }
        for ticket_id, (column, state) in expected.items():
            with self.subTest(ticket=ticket_id):
                column_locator = self.page.locator(
                    f"[data-nv-col='{column}'] article[data-nv-ticket='{ticket_id}']")
                self.assertEqual(
                    1, column_locator.count(),
                    f"{ticket_id} liegt nicht in Spalte {column!r}")
                article = column_locator.first
                self.assertEqual(
                    state, article.get_attribute("data-nv-state"),
                    f"{ticket_id} trägt nicht den Rohstatus {state!r}")
                self.assertIn(
                    ticket_id, article.inner_text(),
                    f"Die Karte {ticket_id} zeigt ihre Kennung nicht")
        self.assert_clean_page()


class FeedbackListTest(AP22WorkBrowserTest):
    def test_feedback_list_shows_kind_badges(self):
        """Vorbedingung: ein Bug und ein gewöhnlicher Feedback-Eintrag.

        Erwartung: ``[data-nv-feedback]`` enthält beide
        ``article[data-nv-feedback-item]``; der Bug trägt ein Bug-Badge, der
        andere Eintrag ein Feedback-Badge.
        """
        self.open_work()
        list_box = self.page.locator("[data-nv-feedback]")
        list_box.wait_for(state="visible", timeout=20000)
        bug = self.page.locator("[data-nv-feedback-item='BUG-7']")
        feedback = self.page.locator("[data-nv-feedback-item='FB-1']")
        self.assertEqual(1, bug.count(), "Der Bug fehlt in der Feedback-Liste")
        self.assertEqual(1, feedback.count(),
                         "Das Feedback fehlt in der Feedback-Liste")
        self.assertRegex(bug.inner_text(), r"bug", "Dem Bug fehlt das Art-Badge")
        self.assertRegex(feedback.inner_text(), r"feedback",
                         "Dem Eintrag fehlt das Feedback-Badge")
        self.assertNotRegex(
            feedback.inner_text(), r"\bbug\b",
            "Der gewöhnliche Feedback-Eintrag trägt fälschlich ein Bug-Badge")
        self.assert_clean_page()


class CreateTest(AP22WorkBrowserTest):
    def test_create_package_and_cancel_the_form(self):
        """Vorbedingung: Board geöffnet. Aktion: Paket anlegen, danach ein
        zweites Formular abbrechen.
        Erwartung: Das neue Paket erscheint in ``open`` und in der Datei;
        Abbrechen schließt das Formular, ohne etwas anzulegen.
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
            "[data-nv-col='open'] article[data-nv-ticket]").filter(
                has_text="NEU-AP22 Anlegen").first
        card.wait_for(state="visible", timeout=20000)
        self.assertTrue((card.get_attribute("data-nv-ticket") or "").strip(),
                        "Die neue Karte trägt keine Paketkennung")
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
                "article[data-nv-ticket]").filter(
                    has_text="VERWORFEN-AP22").count(),
            "Abbrechen hat trotzdem eine Karte angelegt")
        self.assert_clean_page()


class EditTest(AP22WorkBrowserTest):
    def test_edit_prefills_and_saves_only_the_chosen_ticket(self):
        """Vorbedingung: ``AP-OPEN`` und ``AP-OPEN2`` vorhanden.

        Aktion: ``ticket-edit`` an ``AP-OPEN``, Titel ändern, speichern.
        Erwartung: Formular ist vorbefüllt; nur ``AP-OPEN`` ändert sich,
        ``AP-OPEN2`` bleibt unverändert.
        """
        self.open_work()
        self.card("AP-OPEN").locator(
            "[data-nv-action='ticket-edit']").first.click()
        form = self.page.locator("[data-nv-ticket-form]")
        form.wait_for(state="visible", timeout=20000)
        title = form.locator("input[data-nv-field='title']")
        self.assertEqual(
            "Offenes Paket", title.input_value(),
            "Das Bearbeitungsformular ist nicht mit dem Titel vorbefüllt")

        title.fill("AP-OPEN Geändertes Paket")
        form.locator("textarea[data-nv-field='description']").fill(
            "Neue Beschreibung")
        self.save_form(form)
        self.wait_until(
            lambda: "AP-OPEN Geändertes Paket" in self.ticket_text(),
            timeout=20,
            message="Die Bearbeitung wurde nicht gespeichert")
        text = self.ticket_text()
        self.assertIn("- [ ] AP-OPEN Geändertes Paket", text)
        self.assertIn("  Beschreibung: Neue Beschreibung", text)
        self.assertIn("- [ ] AP-OPEN2 Zweites offenes Paket", text)
        self.assertIn("- [ ] AP-BLOCK Blockiertes Paket", text)
        self.assert_clean_page()


class DeleteTest(AP22WorkBrowserTest):
    def test_delete_removes_the_card(self):
        """Vorbedingung: ``AP-OPEN`` vorhanden.

        Aktion: ``ticket-delete`` (Bestätigung wird akzeptiert).
        Erwartung: Karte und Dateieintrag verschwinden, die übrigen bleiben.
        """
        self.open_work()
        self.card("AP-OPEN").locator(
            "[data-nv-action='ticket-delete']").first.click()
        self.confirm_if_visible()
        self.wait_until(
            lambda: self.page.locator(
                "article[data-nv-ticket='AP-OPEN']").count() == 0,
            timeout=20,
            message="Die Karte wurde nicht gelöscht")
        self.wait_until(
            lambda: "AP-OPEN " not in self.ticket_text()
            and "AP-OPEN\n" not in self.ticket_text(),
            timeout=20,
            message="Der Eintrag wurde nicht aus TICKETS.md entfernt")
        text = self.ticket_text()
        self.assertIn("AP-OPEN2 Zweites offenes Paket", text)
        self.assertIn("AP-BLOCK Blockiertes Paket", text)
        self.assertIn("AP-DONE Erledigtes Paket", text)
        self.assert_clean_page()


class FeedbackCreateTest(AP22WorkBrowserTest):
    def test_create_bug_and_feedback_entries(self):
        """Vorbedingung: Board geöffnet.

        Aktion: ``new-bug`` und ``new-feedback`` ausfüllen und speichern.
        Erwartung: Beide erscheinen in ``[data-nv-feedback]`` mit dem
        richtigen Art-Badge.
        """
        self.open_work()
        form = self.open_form("new-bug")
        self.fill_form(form, "NEUER-BUG-AP22", "Absturz beim Speichern")
        self.save_form(form)
        self.wait_until(
            lambda: "NEUER-BUG-AP22" in self.feedback_text(),
            timeout=20,
            message="Der neue Bug wurde nicht gespeichert")
        bug = self.page.locator("[data-nv-feedback-item]").filter(
            has_text="NEUER-BUG-AP22").first
        bug.wait_for(state="visible", timeout=20000)
        self.assertRegex(bug.inner_text(), r"bug",
                         "Der neue Bug trägt kein Bug-Badge")

        form = self.open_form("new-feedback")
        self.fill_form(form, "NEUES-FEEDBACK-AP22", "Bitte schneller laden")
        self.save_form(form)
        self.wait_until(
            lambda: "NEUES-FEEDBACK-AP22" in self.feedback_text(),
            timeout=20,
            message="Das neue Feedback wurde nicht gespeichert")
        feedback = self.page.locator("[data-nv-feedback-item]").filter(
            has_text="NEUES-FEEDBACK-AP22").first
        feedback.wait_for(state="visible", timeout=20000)
        self.assertRegex(feedback.inner_text(), r"feedback",
                         "Das neue Feedback trägt kein Feedback-Badge")
        self.assertNotRegex(feedback.inner_text(), r"\bbug\b",
                            "Das neue Feedback trägt fälschlich ein Bug-Badge")
        self.assert_clean_page()


class PriorityTest(AP22WorkBrowserTest):
    def test_priority_card_appears_with_feature_and_persists(self):
        """Vorbedingung: Feature ``priority`` aus.

        Aktion: Schalter in ``#/settings`` aktivieren, Arbeit öffnen,
        ``AP-OPEN2`` hochschieben, speichern, neu laden.
        Erwartung: ``[data-nv-priority]`` erscheint mit Zeilen und
        ``priority-up|down``/``priority-save``; die neue Reihenfolge bleibt
        über den Reload erhalten.
        """
        self.open_work()
        self.assertEqual(
            0, self.page.locator("[data-nv-priority]").count(),
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
        card = self.page.locator("[data-nv-priority]")
        card.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(
            self.page.locator(
                "[data-nv-priority] [data-nv-action='priority-up']").count(), 1,
            "Die Priorisierung zeigt keine Hoch-Knöpfe")
        self.assertEqual(
            1, self.page.locator(
                "[data-nv-priority] [data-nv-action='priority-save']").count(),
            "Der Speichern-Knopf der Priorisierung fehlt")

        clicked = self.page.evaluate(
            """() => {
              const card = document.querySelector('[data-nv-priority]');
              if (!card) return false;
              const buttons = Array.from(
                card.querySelectorAll("[data-nv-action='priority-up']"));
              const target = buttons.find(button => {
                let node = button;
                while (node && node !== card) {
                  if ((node.textContent || '').includes('AP-OPEN2')) return true;
                  node = node.parentElement;
                }
                return false;
              });
              if (!target) return false;
              target.click();
              return true;
            }""")
        self.assertTrue(clicked,
                        "Keine Priorisierungszeile für AP-OPEN2 gefunden")
        self.page.locator(
            "[data-nv-priority] [data-nv-action='priority-save']").click()

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
            lambda view: ordered_before(view, "AP-OPEN2", "AP-OPEN"),
            message="Die Priorisierung wurde nicht in der erwarteten "
                    "Reihenfolge gespeichert")
        order = order_ids(data)

        self.page.reload()
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        card.wait_for(state="visible", timeout=20000)
        positions = self.page.evaluate(
            """() => {
              const card = document.querySelector('[data-nv-priority]');
              const text = card ? card.innerText : '';
              return [text.search(/\\bAP-OPEN2\\b/), text.search(/\\bAP-OPEN\\b/)];
            }""")
        self.assertGreaterEqual(positions[0], 0,
                                "AP-OPEN2 fehlt nach dem Reload")
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
