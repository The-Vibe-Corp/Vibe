"""Browserabnahme F34 WP1/WP3: Zentrale Rückfragen (Banner, Postfach, Karte, Glocke, Poll).

Die Fälle leiten sich aus ``docs/features/F34.md`` ab — Abschnitt „Zentrale
Rückfragen (neu, verbindlich)“ sowie die WP1-/WP3-Abschnitte des Vertrags. Es
werden ausschließlich die dort verbindlich vereinbarten ``data-nv-*``-Hooks und
``data-*``-Attribute geprüft; sichtbare Texte nur dort, wo der Vertrag sie
ausdrücklich festlegt (Banner, Karte, Glocke).

Vor dem Serverstart legen zwei offene Fragen im Laufzeitordner an
(``questions/q<12hex>.json`` mit ``id``, ``project``, ``agent``, ``text``,
``options``, ``free_text``; Muster aus ``vibe_questions.create``). Eine Frage
bietet Optionen + Freitext, die andere nur Freitext.

Das echte Dashboard läuft als eigener Prozess auf einem freien Loopback-Port
mit isoliertem ``VIBE``/``HOME``, einer opencode-Attrappe und den beiden
offenen Fragen. Es gibt keine Modellaufrufe und keinen Netzzugriff außerhalb von
Loopback.

Testfälle (Name, Vorbedingung, Aktion, Erwartung)
------------------------------------------------
F34QuestionsBannerTest
* ``test_question_banner_and_header_counter_show_two_open_questions``
  (Vorbedingung: zwei offene Fragen. Aktion: Startseite lesen.
   Erwartung: Banner ``div[data-nv-question-banner]`` mit Anzahl und Text der
   neuesten Frage, Knopf ``button[data-nv-question-banner-open]``; Kopfzeilen-
   Knopf ``button[data-nv-questions-button]`` mit Zähler
   ``span[data-nv-questions-count]`` = 2 und Hervorhebung.)
* ``test_new_question_created_during_runtime_is_picked_up_by_poll``
  (Vorbedingung: zwei offene Fragen. Aktion: nach dem Boot eine neue Frage anlegen.
   Erwartung: Banner/Zähler aktualisieren sich per Poll, Glocke erhält einen Eintrag.)

F34QuestionInboxTest
* ``test_question_inbox_opens_from_banner_and_shows_both_cards``
  (Vorbedingung: zwei offene Fragen. Aktion: Banner-Knopf klicken.
   Erwartung: Postfach ``section[data-nv-question-inbox]`` mit beiden Karten
   ``article[data-nv-question][data-nv-question-id]``.)
* ``test_option_answer_writes_answer_file_removes_card_and_recounts``
  (Vorbedingung: Postfach offen, Frage mit Optionen.
   Aktion: Option ``button[data-nv-answer="1"]`` anklicken.
   Erwartung: ``questions/<id>.answer.json`` mit passender Antwort; Karte wird
   lokal entfernt ohne Voll-Neurender; Zähler sinkt auf 1.)
* ``test_free_text_answer_writes_answer_and_clears_banner``
  (Vorbedingung: Postfach offen, Frage nur Freitext.
   Aktion: ``input[data-nv-answer-field]`` + ``button[data-nv-answer-send]``.
   Erwartung: Antwort wird geschrieben, Karte lokal entfernt, nach der letzten
   Antwort Banner und Zähler verschwinden (Knopf bleibt, Zähler hidden/0).)

F34QuestionBellTest
* ``test_bell_live_item_links_to_postbox_and_dismissible``
  (Vorbedingung: zwei offene Fragen, Glocke offen.
   Aktion: Live-Eintrag öffnen und einzeln ausblenden.
   Erwartung: ``div[data-nv-live-item][data-nv-live-key="question:<id>"]`` mit
   ``button[data-nv-live-question-open]``; Einzel-Schließen über
   ``button[data-nv-live-dismiss]`` entfernt nur die Glocken-Zeile; Banner und
   Kopfzähler bleiben.)

F34ActivityQuestionsTest
* ``test_activity_shows_question_card_and_answer_works``
  (Vorbedingung: zwei offene Fragen. Aktion: ``#/activity`` öffnen, Karte prüfen,
   Antwort senden.
   Erwartung: Aktivität nutzt dieselbe Karte; Antwort funktioniert dort ebenfalls.)

Laufzeit-Härtung (Sammellauf)
-----------------------------
``render()`` ruft ``closeBellPanel()``; ein später Render kann das
Glocken-Panel zwischen zwei Messungen wieder schließen. Die Helfer
``ensure_bell_open`` / ``ensure_bell_entry_visible`` prüfen den Zustand daher
vor jedem Zugriff und öffnen die Glocke bei Bedarf erneut (Zeitbudget), wie in
``test_f34_shell_ui``. Geprüft wird unverändert: genau ein Eintrag, genau ein
``button.nv-bell-link[data-nv-notification-open]``, kein ``a[href='#/questions']``,
Klick öffnet ``section[data-nv-question-inbox]`` mit der Karte.

ROT-PHASE (2026-11-22, vor der Implementierung von F34 WP1/WP3)
-----------------------------------------------------------
Ausgeführt mit::

    PLAYWRIGHT_BROWSERS_PATH=/home/vibe/vibe-logs/playwright-browsers \
        python3 -m unittest discover -s tests/browser \
        -p 'test_f34_questions_ui.py' -v

Erwartung: alle Fälle rot (Fachrecht: F34-Zentral-Rückfragen noch nicht
umgesetzt); kein Fall aus Umgebungsgründen (Server, Port, Browser, Syntax).
"""
import http.client
import json
import os
import re
import secrets
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

from playwright.sync_api import Error as PlaywrightError  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"

VIEWPORT_WIDE = 1400
VIEWPORT_H = 900
VIEWPORT_NARROW = 1280
VIEWPORT_H_NARROW = 800

PROJECTS = (
    ("alpha-projekt", "Alpha Testpaket"),
    ("beta-projekt", "Beta Testpaket"),
    ("gamma", "Gamma Testpaket"),
    ("delta", "Delta Testpaket"),
    ("epsilon", "Epsilon Testpaket"),
)

QUESTION_IDS = ("qab12cd34ef56", "q0f1e2d3c4b5a")
QUESTION_1 = {
    "id": "qab12cd34ef56",
    "project": "alpha-projekt",
    "agent": "general",
    "text": "Soll die neue Schaltfläche blau werden?",
    "options": ["Ja, blau", "Nein, grau"],
    "free_text": True,
    "created": "2026-11-22T09:00:00Z",
}
QUESTION_2 = {
    "id": "q0f1e2d3c4b5a",
    "project": "alpha-projekt",
    "agent": "general",
    "text": "Wie soll die Begrüßung lauten?",
    "options": [],
    "free_text": True,
    "created": "2026-11-22T10:00:00Z",
}
QUESTION_NEW_TEXT = "Soll der Hintergrund beim Wechsel grau bleiben?"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
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


class F34QuestionsTest(unittest.TestCase):
    """Dashboard mit zwei vorbereiteten offenen Fragen, Browser, Attrappe."""

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
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True)
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir(parents=True)
        (cls.log_dir / "questions").mkdir(parents=True, exist_ok=True)
        for question in (QUESTION_1, QUESTION_2):
            (cls.log_dir / "questions" / (question["id"] + ".json")).write_text(
                json.dumps(question, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8")
        password = cls.log_dir / "opencode.password"
        password.write_text("geheim-F34-wp1", encoding="utf-8")
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
        self.questions_dir = self.log_dir / "questions"
        self.questions_dir.mkdir(parents=True, exist_ok=True)
        for path in self.questions_dir.glob("*"):
            path.unlink()
        for question in (QUESTION_1, QUESTION_2):
            (self.questions_dir / (question["id"] + ".json")).write_text(
                json.dumps(question, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8")
        self.post_language("en")
        self.page_errors = []
        self.context = self.browser.new_context(
            viewport={"width": VIEWPORT_WIDE, "height": VIEWPORT_H})
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

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def boot_after_reload(self):
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def _bell_panel_is_open(self):
        panel = self.page.locator("[data-nv-bell-panel]")
        if panel.count() == 0:
            return False
        return panel.is_visible() and panel.get_attribute("hidden") is None

    def ensure_bell_open(self, deadline_seconds=20):
        """Glocke vor jedem Zugriff öffnen und offen halten.

        ``render()`` ruft ``closeBellPanel()``; ein später Render kann das
        Panel daher zwischen zwei Messungen wieder schließen (im Sammellauf
        beobachtet). Deshalb wird der Zustand vor jedem Zugriff geprüft und bei
        Bedarf erneut geklickt.
        """
        bell = self.page.locator("[data-nv-bell]")
        panel = self.page.locator("[data-nv-bell-panel]")
        deadline = time.time() + deadline_seconds
        while time.time() < deadline:
            if self._bell_panel_is_open():
                return panel
            try:
                bell.wait_for(state="visible", timeout=10000)
                bell.first.click()
                panel.wait_for(state="visible", timeout=3000)
            except PlaywrightError:
                continue
        self.fail("Die Glocke ließ sich nicht zuverlässig öffnen")

    def ensure_bell_entry_visible(self, entry, deadline_seconds=20):
        """Glocken-Eintrag sichtbar machen, auch wenn ein Render das Panel schließt."""
        deadline = time.time() + deadline_seconds
        while time.time() < deadline:
            self.ensure_bell_open()
            try:
                if entry.count() >= 1 and entry.first.is_visible():
                    return
            except PlaywrightError:
                pass
            self.page.wait_for_timeout(100)
        self.fail("Der Glocken-Eintrag wurde nicht sichtbar")

    def open_bell(self):
        return self.ensure_bell_open()

    def banner(self):
        return self.page.locator("div.nv-question-banner[data-nv-question-banner]")

    def header_questions_button(self):
        return self.page.locator("button[data-nv-questions-button]")

    def questions_count(self):
        return self.page.locator("span[data-nv-questions-count]")

    def question_cards(self):
        return self.page.locator(
            "article[data-nv-question][data-nv-question-id]")

    def inbox(self):
        return self.page.locator("section[data-nv-question-inbox]")

    def open_inbox_from_banner(self):
        banner = self.banner()
        banner.wait_for(state="visible", timeout=20000)
        self.page.locator("button[data-nv-question-banner-open]").first.click()
        inbox = self.inbox()
        inbox.wait_for(state="visible", timeout=20000)
        return banner, inbox

    def answer_files(self):
        folder = self.questions_dir
        return sorted(folder.glob("*.answer.json"))

    def assert_no_page_errors(self):
        self.assertEqual(
            [], self.page_errors, "Die Oberfläche erzeugte JavaScript-Fehler")

    # ---------- Fälle ----------

    def test_question_banner_and_header_counter_show_two_open_questions(self):
        """Vorbedingung: zwei offene Fragen im Laufzeitordner.
        Aktion: Startseite lesen.
        Erwartung: Banner sichtbar mit Anzahl und Text der neuesten Frage, Knopf
        ``[data-nv-question-banner-open]``; Kopfzeilen-Knopf mit Zähler = 2 und
        Hervorhebung.
        """
        self.boot()
        banner = self.banner()
        banner.wait_for(state="visible", timeout=20000)
        self.assertEqual(1, banner.count(), "Das Banner fehlt")
        banner_text = (banner.inner_text() or "")
        self.assertIn(
            QUESTION_2["text"], banner_text,
            "Das Banner zeigt nicht den Text der neuesten Frage: "
            + repr(banner_text))
        self.assertTrue(
            self.page.locator("button[data-nv-question-banner-open]").first.is_visible(),
            "Der Banner-Knopf [data-nv-question-banner-open] fehlt")

        questions_button = self.header_questions_button()
        questions_button.wait_for(state="visible", timeout=10000)
        self.assertTrue(questions_button.first.is_visible(), "Der Kopfzahlen-Knopf fehlt")
        count = self.questions_count()
        count.wait_for(state="visible", timeout=10000)
        self.assertEqual(
            "2", (count.inner_text() or "").strip(),
            "Der Kopfzähler muss bei zwei offenen Fragen „2“ zeigen")
        self.assertIn(
            "is-active", questions_button.first.get_attribute("class") or "",
            "Der Kopfzahlen-Knopf ist nicht hervorgehoben (is-active)")
        self.assertIn(
            "2", questions_button.first.get_attribute("aria-label") or "",
            "Der Kopfzahlen-Knopf trägt nicht die Anzahl im aria-label")
        self.assert_no_page_errors()

    def test_new_question_created_during_runtime_is_picked_up_by_poll(self):
        """Vorbedingung: zwei offene Fragen. Aktion: Datei nach dem Boot anlegen.
        Erwartung: Banner/Zähler aktualisieren sich per Poll, Glocke erhält einen
        Eintrag (max. 8 s Warten).
        """
        self.boot()
        new_qid = "q" + secrets.token_hex(6)
        record = {
            "id": new_qid,
            "project": "alpha-projekt",
            "agent": "general",
            "text": QUESTION_NEW_TEXT,
            "options": ["Ja", "Nein"],
            "free_text": True,
            "created": "2026-11-22T11:00:00Z",
        }
        (self.questions_dir / (new_qid + ".json")).write_text(
            json.dumps(record, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

        live_key = self.page.locator(
            f'div[data-nv-live-item][data-nv-live-key="question:{new_qid}"]')
        self.wait_until(
            lambda: live_key.count() >= 1,
            timeout=8,
            message="Eine neue Frage während der Laufzeit löste keinen "
                    "Glocke-Eintrag aus")

        count_text = ""
        deadline = time.time() + 8
        while time.time() < deadline:
            count_text = self.questions_count().inner_text() or ""
            if "3" in count_text:
                break
            self.page.wait_for_timeout(250)
        self.assertIn(
            "3", count_text,
            "Der Kopfzähler hat sich nach der neuen Frage nicht auf 3 aktualisiert: "
            + repr(count_text))
        self.assert_no_page_errors()

    def test_question_inbox_opens_from_banner_and_shows_both_cards(self):
        """Vorbedingung: zwei offene Fragen.
        Aktion: Banner-Knopf klicken.
        Erwartung: Postfach ``section[data-nv-question-inbox]`` mit beiden Karten
        ``article[data-nv-question][data-nv-question-id]``.
        """
        self.boot()
        banner, inbox = self.open_inbox_from_banner()
        cards = self.question_cards()
        self.wait_until(
            lambda: cards.count() == 2,
            timeout=20,
            message="Das Postfach zeigt nicht beide offenen Fragen")
        for qid in QUESTION_IDS:
            card = self.page.locator(
                f"article[data-nv-question][data-nv-question-id='{qid}']")
            self.assertEqual(
                1, card.count(),
                f"Im Postfach fehlt die Karte {qid}")
            self.assertTrue(
                card.first.is_visible(),
                f"Die Karte {qid} ist im Postfach nicht sichtbar")
        self.assertTrue(banner.first.is_visible(), "Das Banner ist nicht sichtbar")
        self.assert_no_page_errors()


class F34QuestionInboxAnswerTest(F34QuestionsTest):
    def test_option_answer_writes_answer_file_removes_card_and_recounts(self):
        """Vorbedingung: Postfach offen, Frage 1 hat Optionen.
        Aktion: Option ``button[data-nv-answer="1"]`` anklicken.
        Erwartung: ``questions/<id>.answer.json`` mit passender Antwort; Karte
        lokal entfernt ohne Voll-Neurender; Zähler sinkt auf 1.
        """
        self.boot()
        banner, inbox = self.open_inbox_from_banner()
        card = self.page.locator(
            "article[data-nv-question][data-nv-question-id='qab12cd34ef56']")
        card.wait_for(state="visible", timeout=20000)
        option = card.locator("button[data-nv-answer='1']")
        option.wait_for(state="visible", timeout=10000)

        scroll_before = self.page.evaluate("() => window.scrollY")
        answer_path = self.questions_dir / "qab12cd34ef56.answer.json"
        option.first.click()

        self.wait_until(
            lambda: answer_path.exists(),
            timeout=15,
            message="Beantwortete Rückfrage schreibt keine questions/<id>.answer.json")
        answer = json.loads(answer_path.read_text(encoding="utf-8"))
        self.assertEqual(0, answer.get("option"), "Die Antwort nutzt nicht die erste Option")
        self.assertEqual("Ja, blau", answer.get("option_text"), "Die Antwort nutzt nicht den Text der ersten Option")
        self.assertEqual("web", answer.get("by"), "Die Antwortquelle ist nicht web")

        self.wait_until(
            lambda: self.page.locator(
                "article[data-nv-question][data-nv-question-id='qab12cd34ef56']").count() == 0,
            timeout=15,
            message="Die beantwortete Karte wird nicht lokal entfernt")
        self.assertEqual(
            "", self.page.evaluate("() => location.hash"),
            "Eine Antwort löst eine Navigation (Voll-Neurender) aus")
        self.assertEqual(
            scroll_before, self.page.evaluate("() => window.scrollY"),
            "Eine Antwort löst eine Scroll-Position-Änderung (Voll-Neurender) aus")

        count = self.questions_count()
        self.wait_until(
            lambda: (count.inner_text() or "").strip() == "1",
            timeout=15,
            message="Der Kopfzähler sinkt nach der Antwort nicht auf 1")
        self.assertTrue(banner.first.is_visible(), "Das Banner darf nach einer Antwort nicht verschwinden")
        self.assert_no_page_errors()

    def test_free_text_answer_writes_answer_and_clears_banner(self):
        """Vorbedingung: Postfach offen, zwei offene Fragen (Frage 2 nur Freitext).
        Aktion: Frage 2 per ``input[data-nv-answer-field]`` +
        ``button[data-nv-answer-send]`` beantworten, dann die verbleibende
        Frage 1 per Option.
        Erwartung: Antwort wird geschrieben, Karte lokal entfernt, Zähler geht
        auf 1; nach der letzten Antwort verschwinden Banner und Zähler (Knopf
        bleibt, Zähler hidden/0).
        """
        self.boot()
        banner, inbox = self.open_inbox_from_banner()
        card = self.page.locator(
            "article[data-nv-question][data-nv-question-id='q0f1e2d3c4b5a']")
        card.wait_for(state="visible", timeout=20000)
        field = card.locator("input[data-nv-answer-field]")
        field.wait_for(state="visible", timeout=10000)
        send = card.locator("button[data-nv-answer-send]")
        send.wait_for(state="visible", timeout=10000)

        field.fill("Herzlich willkommen")
        send.first.click()
        answer_path = self.questions_dir / "q0f1e2d3c4b5a.answer.json"
        self.wait_until(
            lambda: answer_path.exists(),
            timeout=15,
            message="Freitext-Antwort schreibt keine questions/<id>.answer.json")
        answer = json.loads(answer_path.read_text(encoding="utf-8"))
        self.assertIsNone(answer.get("option"), "Freitext-Antwort darf keine Option haben")
        self.assertEqual("Herzlich willkommen", answer.get("text"),
                         "Freitext-Antwort weicht vom eingegebenen Text ab")

        self.wait_until(
            lambda: self.page.locator(
                "article[data-nv-question][data-nv-question-id='q0f1e2d3c4b5a']").count() == 0,
            timeout=15,
            message="Freitext-Antwort entfernt die Karte nicht")
        # Es ist noch die erste Frage offen: erst nach ihrer Antwort dürfen
        # Banner und Zähler verschwinden.
        count = self.questions_count()
        self.wait_until(
            lambda: (count.inner_text() or "").strip() == "1",
            timeout=15,
            message="Der Kopfzähler sinkt nach der Freitext-Antwort nicht auf 1")
        remaining = self.page.locator(
            "article[data-nv-question][data-nv-question-id='qab12cd34ef56']")
        remaining.wait_for(state="visible", timeout=20000)
        remaining.locator("button[data-nv-answer='1']").first.click()
        second_answer = self.questions_dir / "qab12cd34ef56.answer.json"
        self.wait_until(
            lambda: second_answer.exists(),
            timeout=15,
            message="Die Antwort auf die letzte offene Frage wurde nicht geschrieben")
        self.wait_until(
            lambda: remaining.count() == 0,
            timeout=15,
            message="Die letzte beantwortete Karte bleibt im Postfach")
        self.wait_until(
            lambda: not self.banner().first.is_visible(),
            timeout=15,
            message="Das Banner bleibt nach der letzten Antwort sichtbar")
        self.wait_until(
            lambda: self.questions_count().get_attribute("hidden") is not None,
            timeout=15,
            message="Der Kopfzähler blendet nach der letzten Antwort nicht aus")
        self.assertTrue(
            self.page.locator("button[data-nv-questions-button]").first.is_visible(),
            "Der Kopfzahlen-Knopf muss nach Antworten bestehen bleiben")
        self.assert_no_page_errors()


class F34QuestionBellTest(F34QuestionsTest):
    def test_bell_live_item_links_to_postbox_and_dismissible(self):
        """Vorbedingung: zwei offene Fragen.
        Aktion: Glocken-Live-Eintrag öffnen und einzeln ausblenden.
        Erwartung: ``div[data-nv-live-item][data-nv-live-key="question:<id>"]``
        mit ``button[data-nv-live-question-open]``; Einzel-Schließen über
        ``button[data-nv-live-dismiss]`` entfernt nur die Glocken-Zeile; Banner
        und Kopfzähler bleiben.
        """
        self.boot()
        self.open_bell()
        live = self.page.locator(
            'div[data-nv-live-item][data-nv-live-key="question:qab12cd34ef56"]')
        live.wait_for(state="visible", timeout=20000)
        open_button = live.locator("button[data-nv-live-question-open]")
        open_button.wait_for(state="visible", timeout=10000)
        open_button.first.click()
        inbox = self.inbox()
        inbox.wait_for(state="visible", timeout=20000)

        # Das Öffnen des Postfachs schließt die Glocke und legt den Scrim über
        # die Kopfzeile. Erst das Kontext-Panel schließen, dann die Glocke
        # erneut öffnen, damit die einzelne Zeile wieder bedienbar ist.
        self.page.locator("[data-nv-context-close]").first.click()
        self.wait_until(
            lambda: self.page.locator("[data-nv-context-scrim]").evaluate(
                "node => node.hidden") is True,
            timeout=10,
            message="Das Kontext-Panel des Postfachs bleibt nach dem Schließen offen")
        self.open_bell()
        live.wait_for(state="visible", timeout=20000)
        dismiss = live.locator("button[data-nv-live-dismiss]")
        dismiss.wait_for(state="visible", timeout=10000)
        dismiss.first.click()
        self.wait_until(
            lambda: live.count() == 0,
            timeout=10,
            message="Einzelnes Ausblenden entfernt nicht nur die Glocken-Zeile")

        self.wait_until(
            lambda: self.banner().first.is_visible(),
            timeout=10,
            message="Das Banner darf durch das Glocken-Ausblenden nicht verschwinden")
        self.wait_until(
            lambda: (self.questions_count().inner_text() or "").strip() == "2",
            timeout=10,
            message="Der Kopfzähler darf durch das Glocken-Ausblenden nicht "
                    "zurückgehen")
        self.assert_no_page_errors()

    def test_stored_bell_entry_for_new_question_opens_postbox(self):
        """Vorbedingung: erster Fragen-Sync abgeschlossen (Kopfzähler/Banner
        zeigen die beiden Fixture-Fragen), danach erscheint eine neue
        Rückfrage (Runtime-Poll).
        Aktion: Glocken öffnen, gespeicherten Eintrag prüfen, „Öffnen“ klicken.
        Erwartung: gespeicherter Eintrag (kind question, „Neue Rückfrage: …“)
        ohne toten Link ``a[href='#/questions']``, sondern mit Knopf
        ``button.nv-bell-link[data-nv-notification-open]`` (sichtbarer Text
        „Öffnen“); Klick öffnet das Fragen-Postfach
        (``aside[data-nv-context] section[data-nv-question-inbox]``) und zeigt
        die Karte der offenen Frage.
        """
        self.boot()
        self.open_bell()
        # Vorbedingung: der erste Fragen-Sync (loadQuestions beim Boot) ist
        # abgeschlossen, bevor die neue Laufzeit-Frage angelegt wird — sonst
        # würde der erste Sync die Datei als „bereits gesehen“ behandeln und
        # bewusst keine Benachrichtigung erzeugen (kein Spam beim Start-Sync).
        questions_count = self.questions_count()
        questions_count.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: (questions_count.inner_text() or "").strip() == "2",
            timeout=20,
            message="Der erste Fragen-Sync hat die beiden Fixture-Fragen nicht "
                    "gedeutet (Kopfzähler != 2)")
        self.wait_until(
            lambda: self.banner().first.is_visible(),
            timeout=20,
            message="Das Banner zu den beiden offenen Fragen ist nach dem ersten "
                    "Sync nicht sichtbar")
        new_qid = "q" + secrets.token_hex(6)
        record = {
            "id": new_qid,
            "project": "alpha-projekt",
            "agent": "general",
            "text": QUESTION_NEW_TEXT,
            "options": ["Ja", "Nein"],
            "free_text": True,
            "created": "2026-11-22T11:00:00Z",
        }
        (self.questions_dir / (new_qid + ".json")).write_text(
            json.dumps(record, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        new_entry = self.page.locator(
            "div[data-nv-notification][data-nv-notification-id]"
        ).filter(has_text=QUESTION_NEW_TEXT)
        self.wait_until(
            lambda: new_entry.count() >= 1,
            timeout=15,
            message="Nach Erscheinen der neuen Rückfrage liegt kein gespeicherter "
                    "Glocken-Eintrag mit der Frage vor")
        entry = new_entry.first
        # Ein später Render kann das Glocken-Panel schließen; vor Text- und
        # Sichtbarkeitsprüfungen daher erneut öffnen (Sammellauf-Rennen).
        self.ensure_bell_entry_visible(new_entry)
        text = entry.inner_text() or ""
        self.assertRegex(
            text, re.compile(r"(?i)neue rückfrage|new question"),
            "Der gespeicherte Glocken-Eintrag trägt nicht den „Neue Rückfrage“-Text: "
            + repr(text))
        self.assertIn(QUESTION_NEW_TEXT, text, "Der gespeicherte Glocken-Eintrag "
                         "zeigt nicht den Frage-Text: " + repr(text))
        kinds = self.page.evaluate(
            "() => (JSON.parse(localStorage.getItem('nv-notifications') || '[]')"
            ".map(entry => entry.kind))")
        self.assertIn("question", kinds, "Der gespeicherte Glocken-Eintrag hat "
                     "nicht kind=question: " + repr(kinds))
        self.assertEqual(
            0, entry.locator("a").count(),
            "Der gespeicherte Glocken-Eintrag nutzt noch den toten Link "
            "a[href='#/questions']: " + repr(kinds))
        open_button = entry.locator(
            "button.nv-bell-link[data-nv-notification-open]")
        self.assertEqual(1, open_button.count(),
                         "Der gespeicherte Glocken-Eintrag hat keinen Knopf "
                         "button.nv-bell-link[data-nv-notification-open]")
        self.ensure_bell_entry_visible(new_entry)
        self.assertTrue(open_button.first.is_visible(),
                        "Der ‚Öffnen‘-Knopf des gespeicherten Glocken-Eintrags "
                        "ist nicht sichtbar")
        self.assertRegex(
            open_button.first.inner_text() or "",
            re.compile(r"(?i)öffnen|open"),
            "Der ‚Öffnen‘-Knopf …: " + repr(open_button.first.inner_text()))
        self.ensure_bell_entry_visible(new_entry)
        open_button.first.click()
        inbox = self.page.locator(
            "aside[data-nv-context] section[data-nv-question-inbox]")
        inbox.wait_for(state="visible", timeout=20000)
        card = self.page.locator(
            f"article[data-nv-question][data-nv-question-id='{new_qid}']")
        card.wait_for(state="visible", timeout=20000)
        self.assertTrue(card.first.is_visible(),
                        "Die Karte der offenen Frage ist nach dem Glocken-Klick "
                        "nicht sichtbar")
        self.assert_no_page_errors()


class F34ActivityQuestionsTest(F34QuestionsTest):
    def test_activity_shows_question_card_and_answer_works(self):
        """Vorbedingung: zwei offene Fragen.
        Aktion: Ansicht ``#/activity`` öffnen, Karte prüfen, Antwort senden.
        Erwartung: Aktivität nutzt dieselbe Karte; Antwort funktioniert dort
        ebenfalls.
        """
        self.boot()
        self.page.goto(self.base + "/#/activity")
        self.page.locator(
            "main#nv-main[data-nv-view='activity']").wait_for(
            state="visible", timeout=25000)
        cards = self.question_cards()
        self.wait_until(
            lambda: cards.count() == 2,
            timeout=20,
            message="Die Aktivität zeigt nicht beide offenen Fragen")
        card = self.page.locator(
            "article[data-nv-question][data-nv-question-id='qab12cd34ef56']")
        card.wait_for(state="visible", timeout=20000)
        option = card.locator("button[data-nv-answer='1']")
        option.wait_for(state="visible", timeout=10000)
        option.first.click()
        answer_path = self.questions_dir / "qab12cd34ef56.answer.json"
        self.wait_until(
            lambda: answer_path.exists(),
            timeout=15,
            message="Antwort aus der Aktivität schreibt keine Antwortdatei")
        self.assert_no_page_errors()


if __name__ == "__main__":
    unittest.main()
