"""B1: Browserabnahme für den einheitlichen Tickettyp und den ruhigen Editor.

Quelle der Fälle: ``TICKET-B1.json`` (drei gemeldete Probleme: doppeltes
Typ-/Kategoriefeld, automatischer Zustandswechsel beim Bearbeiten/Abbrechen,
Bug ohne GitHub-Anlage), der verbindliche Zielvertrag A–E (Option A, vom
Nutzer bestätigt) und ``SPEC.md`` (einheitliche Tickets in
``.vibe/tickets.json``, Oberflächensprache Englisch, automatisch vergebene
IDs, Zustände auch ohne GitHub-Verbindung). Die Fälle sind unabhängig aus
Ticket und Spezifikation abgeleitet, nicht aus einem Implementierungsdiff.

Abgedeckte Nutzerverträge:

* **A** Genau ein Typfeld ``select[data-nv-field='ticket-type']`` mit den
  Optionen feature/bug/feedback; keine Kategorie-Auswahl, keine
  „Paket“-/``task``-Option; Vorauswahl je Anlage-Button.
* **B** „Speichern“ schickt die Anlage an ``/api/ticket`` mit ``action=add``,
  ``type``, ``state=draft`` – einheitlich für Paket/Bug/Feedback.
* **C** Offline entsteht ein lokales Ticket mit dem gewählten Typ; die ID
  folgt dem Typ (feature → ``AP<n>``, bug → ``B<n>``, feedback → ``F<n>``).
* **D** Der Editor ändert den Zustand nie: Öffnen, Abbrechen und Speichern
  lassen ``draft``/``open`` unverändert und lösen keinen ``action=state``-POST
  aus. Manuelle Zustandswechsel (Detail-Auswahl, Board, DnD) bleiben möglich.

Der Live-Server läuft isoliert auf einem freien Port mit bereinigter
``VIBE_*``-/``HOME``-Umgebung (``tests/unit/env_support.isolated_environ``)
und eigenen Temp-Pfaden; der Browser nutzt den vorgegebenen
``PLAYWRIGHT_BROWSERS_PATH``. Aufbau entspricht
``tests/browser/test_gh67_work_ui.py``.

Hooks (Vertrag für die Umsetzung):
    ``aside[data-nv-ticket-editor]``, ``button[data-nv-action=new-package]``,
    ``new-bug``, ``new-feedback``, ``select[data-nv-field='ticket-type']``,
    ``input[data-nv-field='id']``, ``input[data-nv-field='title']``,
    ``button[data-nv-action='ticket-save']``, ``ticket-cancel``,
    ``[data-nv-ticket-detail]``, ``select[data-nv-ticket-state-select]``,
    ``button[data-nv-action='ticket-state-save']``,
    ``article[data-nv-ticket]`` mit ``data-nv-state``.

Run (Rot-Phase, vor der Implementierung):

    PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright \
      python3 -m unittest tests.browser.test_b1_work_ui -v
"""
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
VIEWPORT = {"width": 1500, "height": 1100}
NEW_ACTIONS = {"package": "new-package", "bug": "new-bug",
               "feedback": "new-feedback"}
EXPECTED_TYPES = {"feature", "bug", "feedback"}


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


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

        Erwartung: die Auswahl bietet draft/open/in-progress; der Speicher
        steht danach auf ``open`` und die Karte trägt ``data-nv-state=open``.
        Significance: Option A entfernt nur den automatischen Wechsel; die
        ausdrückliche Nutzerkontrolle (Bereit/Freigeben) bleibt erhalten.
        """
        self.write_store([ticket("AP3", "Manuell bereit", state="draft")])
        self.goto_work()
        self.card("AP3").locator(
            "button[data-nv-action='ticket-details']").first.click()
        detail = self.page.locator("[data-nv-ticket-detail='AP3']").first
        detail.wait_for(state="visible", timeout=5000)
        select = detail.locator("select[data-nv-ticket-state-select]").first
        self.assertEqual(
            {"draft", "open", "in-progress"},
            set(select.locator("option").evaluate_all(
                "els => els.map(e => e.value)")),
            "Die Zustandsauswahl bietet nicht alle manuellen Zustände")
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


if __name__ == "__main__":
    unittest.main()
