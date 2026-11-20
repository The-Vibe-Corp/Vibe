"""Browserabnahme AP22, Meilenstein B: Aktivität (Läufe, Sessions, Fragen, Glocke).

Die Fälle leiten sich aus ``docs/features/AP22.md`` („Aktivität“,
„Shell → Glocke“) ab. Das echte Dashboard läuft isoliert auf freiem Port.
Die offene Rückfrage liegt **vor dem Serverstart** als JSON im
Laufzeitordner (Format aus ``tests/unit/test_questions.py`` /
``tests/browser/test_questions_ui.py``); Sessions und Läufe werden über die
echten Registerdateien nachgebildet. Chromium kommt aus dem Nur-Lese-Cache.

Testfälle (Kurzfassung; Details in den Methoden)
-----------------------------------------------
``ActivitySectionsTest.test_activity_sections_render``
    Erwartung: ``[data-nv-runs]``, ``[data-nv-sessions]`` mit
    ``select[data-nv-sessions-project]`` und ``[data-nv-questions]`` sind
    sichtbar.
``RunsTest.test_runs_lists_a_live_run_with_link``
    Vorbedingung: laufender Lauf im Register. Erwartung: Projektname und
    ein Link/Knopf zur Ausgabe.
``RunsTest.test_runs_empty_state_without_registry``
    Vorbedingung: kein Lauf. Erwartung: sichtbarer Leerzustand, kein
    Projektlink.
``SessionsTest.test_sessions_load_and_limit_persists``
    Vorbedingung: zwei Sessions im Register. Aktion: Projekt wählen, Limit
    ``7`` speichern, neu laden. Erwartung: Sessions werden geladen;
    ``/api/sessions`` und das Eingabefeld halten ``7``.
``QuestionsTest.test_question_option_answer``
    Aktion: Option 1 beantworten. Erwartung: Antwortdatei mit ``option=0``;
    die Frage verschwindet oder ist als beantwortet markiert.
``QuestionsTest.test_question_free_text_answer``
    Aktion: Freitext senden. Erwartung: Antwortdatei mit ``text``.
``QuestionsTest.test_second_answer_is_rejected_with_message``
    Vorbedingung: Frage ist bereits durch einen anderen Client beantwortet.
    Aktion: Option klicken. Erwartung: sichtbare Ablehnung „bereits
    beantwortet“, die erste Antwort bleibt unverändert.
``BellTest.test_bell_counts_links_and_updates_after_answer``
    Vorbedingung: eine offene Frage und ein laufender Lauf. Erwartung:
    Zähler sichtbar (≥ 1), Ausklapp nennt Frage und Lauf mit Links; nach
    der Antwort sinkt der Zähler oder verschwindet.

Vertragsunklarheiten (bewusst so geprüft und dokumentiert)
----------------------------------------------------------
1. **Glocken-Inhalt.** ``docs/features/AP22.md`` nennt offene Fragen,
   blockierte Pakete und fehlgeschlagene Läufe; die Beauftragung und der
   aktuelle Stand nennen eine offene Frage **und einen laufenden Lauf**.
   Geprüft wird die Beauftragung: Frage + laufender Lauf, beide verlinkt.
2. **Läufe-Zeilen.** Der Vertrag nennt keinen Zeilen-Hook. Geprüft wird der
   Projektname im Bereich und ein Link/Knopf, dessen Ziel die
   Projekt-/Ausgabeansicht ist.
3. **Sessions-Limit.** Der Vertrag nennt nur Eingabe und Speichern-Knopf,
   nicht die POST-Form. Der Test prüft die beobachtbare Persistenz über
   ``GET /api/sessions`` und nach dem Reload.
4. **Optionsnummer.** Der Hook ``[data-nv-answer="<nr>"]`` ist 1-basiert;
   das Backend erwartet den 0-basierten Index. Geprüft wird, dass Klick auf
   ``1`` die Antwort ``option=0`` erzeugt.
5. **Leerzustand Läufe.** Der Wortlaut ist nicht festgelegt; geprüft wird
   ein nichtleerer, sichtbarer Bereich ohne Projektlink.
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
RUNS_PY = REPO / "bin" / "vibe_runs.py"
PROJECT = "proj"
TMUX_SESSION = "vibe-" + PROJECT
QUESTION_ID = "qaaaaaaaaaaaa"
QUESTION_TEXT = "AP22-FRAGE-4711: Soll die Schaltfläche blau werden?"
QUESTION_OPTIONS = ["Ja, blau", "Nein, grau"]
FREE_QUESTION_ID = "qbbbbbbbbbbbb"
FREE_QUESTION_TEXT = "AP22-FREITEXT-4711: Wie soll die Begrüßung lauten?"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class AP22ActivityBrowserTest(unittest.TestCase):
    """Dashboard, Browser, Fragen-, Sessions- und Laufregister-Fixtures."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / PROJECT
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "TICKETS.md").write_text(
            "# TICKETS — AP22 Test\n\n- [ ] AP22 Aktivität\n"
            "  Beschreibung: Test\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True)
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir(parents=True)
        cls.questions = cls.log_dir / "questions"
        cls.questions.mkdir(parents=True)

        # Pflicht aus der Beauftragung: Die offene Frage existiert bereits
        # vor dem Start des Servers.
        cls.write_question_file(
            QUESTION_ID, QUESTION_TEXT, QUESTION_OPTIONS, free_text=True)

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
    def write_question_file(cls, qid, text, options, free_text=True):
        path = cls.questions / f"{qid}.json"
        path.write_text(json.dumps({
            "id": qid,
            "project": PROJECT,
            "agent": "tester",
            "text": text,
            "options": options,
            "free_text": free_text,
            "created": "2026-11-20T10:00:00Z",
        }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return path

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser.close()
            cls.playwright.stop()
        finally:
            cls.kill_tmux()
            if cls.proc.poll() is None:
                cls.proc.terminate()
                try:
                    cls.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls.proc.kill()
                    cls.proc.wait()
            cls.server_log.close()
            cls.tmp.cleanup()

    @classmethod
    def kill_tmux(cls):
        subprocess.run(
            ["tmux", "-L", TMUX_SESSION, "kill-server"],
            env=cls.env, capture_output=True, text=True, timeout=10,
            check=False)

    # ---------- Umgebung je Test ----------

    def setUp(self):
        self.kill_tmux()
        for path in self.questions.iterdir():
            path.unlink()
        self.write_question_file(
            QUESTION_ID, QUESTION_TEXT, QUESTION_OPTIONS)
        (self.log_dir / "runs.json").unlink(missing_ok=True)
        (self.log_dir / "sessions.json").unlink(missing_ok=True)
        self.write_sessions(limit=5)
        (self.log_dir / "autonomous.json").unlink(missing_ok=True)
        self.post_language("en")
        self.page_errors = []
        self.context = self.browser.new_context(
            viewport={"width": 1400, "height": 1000})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))

    def tearDown(self):
        self.page.close()
        self.context.close()
        self.kill_tmux()

    # ---------- Seeds und Helfer ----------

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

    def write_sessions(self, limit=5):
        now = int(time.time())
        entries = [
            {
                "session": "ses_ap22_a",
                "first_seen": now - 60,
                "last_seen": now,
                "project": str(self.project.resolve()),
                "name": PROJECT,
                "run_id": "",
                "agent": "vibe-agent",
                "harness": "opencode",
            },
            {
                "session": "ses_ap22_b",
                "first_seen": now - 120,
                "last_seen": now - 30,
                "project": str(self.project.resolve()),
                "name": PROJECT,
                "run_id": "",
                "agent": "vibe-agent",
                "harness": "opencode",
            },
        ]
        (self.log_dir / "sessions.json").write_text(
            json.dumps({"limit": limit, "sessions": entries},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

    def start_run(self):
        result = subprocess.run([
            sys.executable, str(RUNS_PY), "start",
            "--runtime", str(self.log_dir),
            "--project", str(self.project.resolve()),
            "--name", PROJECT, "--key", PROJECT, "--agent", "vibe-agent",
            "--session", TMUX_SESSION, "--state", "running",
        ], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0,
                         "Vorbedingung Laufregister fehlgeschlagen: "
                         + result.stdout + result.stderr)
        result = subprocess.run(
            ["tmux", "-L", TMUX_SESSION, "new-session", "-d",
             "-s", TMUX_SESSION, "sleep", "300"],
            env=self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0,
                         "tmux-Sitzung konnte nicht angelegt werden: "
                         + result.stdout + result.stderr)
        subprocess.run(
            ["tmux", "-L", TMUX_SESSION, "set-environment",
             "-t", TMUX_SESSION, "VIBE_MANAGED", "run"],
            env=self.env, capture_output=True, text=True, timeout=15,
            check=False)

    def wait_until(self, predicate, timeout=25,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def api_json(self, path):
        return self.page.evaluate(
            """async (path) => {
              const response = await fetch(path, {headers: {'Accept': 'application/json'}});
              return await response.json();
            }""", path)

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_activity(self):
        self.boot()
        self.page.goto(self.base + "/#/activity")
        self.page.locator("main#nv-main[data-nv-view='activity']").wait_for(
            state="visible", timeout=25000)

    def answer_file(self, qid=QUESTION_ID):
        return self.questions / f"{qid}.answer.json"

    def runs_snapshot(self):
        return self.page.evaluate(
            """() => {
              const box = document.querySelector('[data-nv-runs]');
              if (!box) return null;
              return {
                text: box.innerText || '',
                links: Array.from(box.querySelectorAll('a'))
                  .map(link => link.getAttribute('href') || ''),
                controls: Array.from(box.querySelectorAll(
                  'button, [data-nv-action]')).map(node =>
                  (node.getAttribute('data-nv-action') || '')
                  + ' ' + (node.getAttribute('aria-label') || '')
                  + ' ' + (node.textContent || '')),
              };
            }""")

    def assert_clean_page(self):
        self.assertEqual(
            [], self.page_errors, "Die Aktivitätsansicht erzeugte JavaScript-Fehler")


class ActivitySectionsTest(AP22ActivityBrowserTest):
    def test_activity_sections_render(self):
        """Vorbedingung: eine offene Frage, zwei Sessions im Register.

        Erwartung: ``[data-nv-runs]``, ``[data-nv-sessions]`` mit
        ``select[data-nv-sessions-project]`` und ``[data-nv-questions]]``
        sind sichtbar.
        """
        self.open_activity()
        for selector in ("[data-nv-runs]", "[data-nv-sessions]",
                         "[data-nv-questions]"):
            locator = self.page.locator(selector)
            self.assertEqual(1, locator.count(), f"Bereich {selector} fehlt")
            locator.first.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            1, self.page.locator(
                "[data-nv-sessions] select[data-nv-sessions-project]").count(),
            "Die Projektauswahl der Sessions fehlt")
        self.assert_clean_page()


class RunsTest(AP22ActivityBrowserTest):
    def test_runs_lists_a_live_run_with_link(self):
        """Vorbedingung: laufender Lauf im Register.

        Erwartung: ``[data-nv-runs]`` nennt ``proj`` und bietet einen
        Link/Knopf zur Ausgabe des Projekts.
        """
        self.start_run()
        self.open_activity()
        runs = self.page.locator("[data-nv-runs]")
        runs.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: PROJECT in runs.inner_text(),
            timeout=20,
            message="Der laufende Lauf erscheint nicht in der Läufe-Liste")
        snapshot = self.runs_snapshot()
        targets = [
            href for href in snapshot["links"]
            if PROJECT in href or "output" in href
        ]
        controls = [
            text for text in snapshot["controls"]
            if re.search(r"output|ausgabe|open|öffnen|lauf", text, re.I)
        ]
        self.assertTrue(
            targets or controls,
            "Die Läufe-Zeile bietet keinen Link/Knopf zur Ausgabe: "
            + repr(snapshot))
        self.assert_clean_page()

    def test_runs_empty_state_without_registry(self):
        """Vorbedingung: kein Lauf im Register.

        Erwartung: ein sichtbarer, nichtleerer Leerzustand ohne Projektlink.
        """
        self.open_activity()
        runs = self.page.locator("[data-nv-runs]")
        runs.wait_for(state="visible", timeout=20000)
        self.assertTrue((runs.inner_text() or "").strip(),
                        "Die Läufe-Liste zeigt ohne Register keinen Leerzustand")
        snapshot = self.runs_snapshot()
        self.assertEqual(
            [], [href for href in snapshot["links"] if PROJECT in href],
            "Ohne Lauf erscheint dennoch ein Projektlink: " + repr(snapshot))
        self.assert_clean_page()


class SessionsTest(AP22ActivityBrowserTest):
    def test_sessions_load_and_limit_persists(self):
        """Vorbedingung: zwei Sessions für ``proj`` im Register.

        Aktion: Projekt wählen, Limit ``7`` speichern, Seite neu laden.
        Erwartung: Die Sessions erscheinen; ``GET /api/sessions`` und das
        Eingabefeld melden nach dem Reload ``7``.
        """
        self.open_activity()
        select = self.page.locator(
            "[data-nv-sessions] select[data-nv-sessions-project]")
        select.wait_for(state="visible", timeout=20000)
        select.select_option(PROJECT)
        sessions = self.page.locator("[data-nv-sessions]")
        self.wait_until(
            lambda: "ses_ap22_a" in sessions.inner_text(),
            timeout=20,
            message="Die Sessions des Projekts werden nicht geladen: "
                    + repr(sessions.inner_text()))

        limit = self.page.locator("input[data-nv-sessions-limit]")
        limit.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            "5", limit.input_value(),
            "Das gespeicherte Session-Limit wird nicht angezeigt")
        limit.fill("7")
        self.page.locator(
            "[data-nv-action='sessions-limit-save']").first.click()
        self.wait_until(
            lambda: self.api_json(
                f"/api/sessions?name={PROJECT}").get("limit") == 7,
            timeout=20,
            message="Das Session-Limit wurde nicht gespeichert")

        self.page.reload()
        self.page.locator("main#nv-main[data-nv-view='activity']").wait_for(
            state="visible", timeout=25000)
        select = self.page.locator(
            "[data-nv-sessions] select[data-nv-sessions-project]")
        select.wait_for(state="visible", timeout=20000)
        select.select_option(PROJECT)
        limit = self.page.locator("input[data-nv-sessions-limit]")
        self.wait_until(
            lambda: limit.input_value() == "7",
            timeout=20,
            message="Das Session-Limit ging beim Reload verloren: "
                    + repr(limit.input_value()))
        self.assertEqual(
            7, self.api_json(
                f"/api/sessions?name={PROJECT}").get("limit"),
            "Das Session-Limit ist serverseitig nicht mehr 7")
        self.assert_clean_page()


class QuestionsTest(AP22ActivityBrowserTest):
    def test_question_option_answer(self):
        """Vorbedingung: offene Frage mit zwei Optionen.

        Aktion: ``[data-nv-answer="1"]`` klicken.
        Erwartung: Antwortdatei mit ``option=0`` und ``option_text``; die
        Frage verschwindet oder ist als beantwortet markiert.
        """
        self.open_activity()
        first = self.page.locator("[data-nv-answer='1']")
        first.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            1, self.page.locator("[data-nv-answer='2']").count(),
            "Die zweite Auswahlmöglichkeit fehlt")
        first.click()
        self.wait_until(
            lambda: self.answer_file().is_file(),
            timeout=20,
            message="Die gewählte Antwort wurde nicht gespeichert")
        answer = json.loads(self.answer_file().read_text(encoding="utf-8"))
        self.assertEqual(0, answer.get("option"), answer)
        self.assertEqual("Ja, blau", answer.get("option_text"), answer)

        def answered():
            if self.page.locator("[data-nv-answer]").count() == 0:
                return True
            return re.search(
                r"beantwortet|answered",
                self.page.locator("[data-nv-questions]").inner_text(),
                re.I) is not None

        self.wait_until(
            answered, timeout=20,
            message="Die beantwortete Frage bleibt unmarkiert stehen")
        self.assert_clean_page()

    def test_question_free_text_answer(self):
        """Vorbedingung: offene Frage ohne Optionen.

        Aktion: ``[data-nv-field="answer"]`` füllen und ``answer`` klicken.
        Erwartung: Antwortdatei mit dem Freitext.
        """
        for path in self.questions.iterdir():
            path.unlink()
        self.write_question_file(
            FREE_QUESTION_ID, FREE_QUESTION_TEXT, [], free_text=True)
        self.open_activity()
        field = self.page.locator(
            "[data-nv-questions] [data-nv-field='answer']").first
        field.wait_for(state="visible", timeout=20000)
        field.fill("Herzlich willkommen")
        self.page.locator(
            "[data-nv-questions] [data-nv-action='answer']").first.click()
        path = self.answer_file(FREE_QUESTION_ID)
        self.wait_until(
            lambda: path.is_file(),
            timeout=20,
            message="Die Freitext-Antwort wurde nicht gespeichert")
        answer = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsNone(answer.get("option"), answer)
        self.assertEqual("Herzlich willkommen", answer.get("text"), answer)
        self.assert_clean_page()

    def test_second_answer_is_rejected_with_message(self):
        """Vorbedingung: Die Frage ist bereits durch einen anderen Client
        beantwortet, wird aber noch angezeigt.

        Aktion: Eine Auswahl anklicken.
        Erwartung: Eine sichtbare Ablehnung erscheint; die erste Antwort
        bleibt unverändert.
        """
        self.open_activity()
        self.page.locator("[data-nv-answer='1']").wait_for(
            state="visible", timeout=20000)
        original = {
            "option": 0,
            "option_text": "Ja, blau",
            "text": "",
            "at": "2026-11-20T10:01:00Z",
            "by": "web",
        }
        self.answer_file().write_text(
            json.dumps(original, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

        self.page.locator("[data-nv-answer='2']").click()
        self.wait_until(
            lambda: re.search(
                r"bereits beantwortet|already answered",
                self.page.locator("#nv-toasts").inner_text(), re.I) is not None,
            timeout=20,
            message="Die Ablehnung der zweiten Antwort erscheint nicht")
        self.assertEqual(
            original,
            json.loads(self.answer_file().read_text(encoding="utf-8")),
            "Die zweite Antwort hat die erste überschrieben")
        self.assert_clean_page()


class BellTest(AP22ActivityBrowserTest):
    def test_bell_counts_links_and_updates_after_answer(self):
        """Vorbedingung: eine offene Frage und ein laufender Lauf.

        Erwartung: Der Glocken-Zähler ist sichtbar (≥ 1), der Ausklapp nennt
        Frage und Lauf mit Links; nach der Antwort sinkt der Zähler oder
        verschwindet.
        """
        self.start_run()
        self.open_activity()
        self.page.locator("[data-nv-answer='1']").wait_for(
            state="visible", timeout=20000)
        self.page.goto(self.base + "/#/")
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

        badge = self.page.locator("span[data-nv-bell-count]").first
        self.wait_until(
            lambda: badge.is_visible()
            and re.search(r"\d+", badge.inner_text() or "") is not None,
            timeout=20,
            message="Der Glocken-Zähler bleibt trotz offener Frage verborgen")
        initial = int(re.search(r"\d+", badge.inner_text()).group(0))
        self.assertGreaterEqual(initial, 1,
                                "Der Glocken-Zähler ist kleiner als 1")

        self.page.locator("button[data-nv-bell]").click()
        panel = self.page.locator("[data-nv-bell-panel]")
        panel.wait_for(state="visible", timeout=20000)
        text = panel.inner_text()
        self.assertIn(QUESTION_TEXT, text,
                      "Der Ausklapp nennt die offene Frage nicht")
        self.assertIn(PROJECT, text,
                      "Der Ausklapp nennt den laufenden Lauf nicht")
        question_link = panel.locator("a").filter(
            has_text=QUESTION_TEXT).first
        self.assertEqual(1, question_link.count(),
                         "Die Frage ist im Ausklapp nicht verlinkt")
        self.assertTrue((question_link.get_attribute("href") or "").strip(),
                        "Der Frage-Link hat kein Ziel")
        run_link = panel.locator("a[href*='output']").first
        self.assertEqual(1, run_link.count(),
                         "Der laufende Lauf ist im Ausklapp nicht verlinkt")
        self.assertIn(PROJECT, run_link.inner_text(),
                      "Der Lauf-Link nennt das Projekt nicht")

        self.page.goto(self.base + "/#/activity")
        self.page.locator("main#nv-main[data-nv-view='activity']").wait_for(
            state="visible", timeout=25000)
        self.page.locator("[data-nv-answer='1']").wait_for(
            state="visible", timeout=20000)
        self.page.locator("[data-nv-answer='1']").click()
        self.wait_until(
            lambda: self.answer_file().is_file(),
            timeout=20,
            message="Die Frage wurde nicht beantwortet")
        self.page.goto(self.base + "/#/")
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

        def updated():
            badge = self.page.locator("span[data-nv-bell-count]")
            if badge.count() == 0 or not badge.first.is_visible():
                return True
            match = re.search(r"\d+", badge.first.inner_text() or "")
            return match is not None and int(match.group(0)) < initial

        self.wait_until(
            updated, timeout=25,
            message="Der Glocken-Zähler sank nach der Antwort nicht")
        self.assert_clean_page()


if __name__ == "__main__":
    unittest.main()
