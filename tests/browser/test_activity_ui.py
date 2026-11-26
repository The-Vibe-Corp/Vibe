"""Aktivität: Abschnitte, Läufe, Sitzungen, Fragen, Glocke und Auswertungen.

Aufruf: python3 -m unittest tests.browser.test_activity_ui -v
"""


# ===========================================================================
# Browserabnahme, Meilenstein B: Aktivität (Läufe, Fragen, Glocke)
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
RUNS_PY = REPO / "bin" / "vibe_runs.py"
PROJECT = "proj"
TMUX_SESSION = "vibe-" + PROJECT
QUESTION_ID = "qaaaaaaaaaaaa"
QUESTION_TEXT = "AP22-FRAGE-4711: Soll die Schaltfläche blau werden?"
QUESTION_OPTIONS = ["Ja, blau", "Nein, grau"]
FREE_QUESTION_ID = "qbbbbbbbbbbbb"
FREE_QUESTION_TEXT = "AP22-FREITEXT-4711: Wie soll die Begrüßung lauten?"
BLOCKED_ID = "AP22-BLOCK"
BLOCKED_TITLE = "Blockiertes Paket"


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
            "  Beschreibung: Test\n\n- [ ] AP22-BLOCK Blockiertes Paket\n"
            "  Beschreibung: Wartet auf Freigabe.\n"
            "  BLOCKIERT: externe Freigabe fehlt\n", encoding="utf-8")
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

        # Review-Fix AP22: Der fehlgeschlagene Lauf entsteht mit dem echten
        # Registerformat **vor** dem Serverstart. Die Vorlage wird je Test
        # erneut in runs.json gelegt, damit die Fälle isoliert bleiben.
        failed = subprocess.run([
            sys.executable, str(RUNS_PY), "start",
            "--runtime", str(cls.log_dir),
            "--project", str(cls.project.resolve()),
            "--name", PROJECT, "--key", PROJECT, "--agent", "vibe-agent",
            "--session", "vibe-failed-review", "--state", "failed",
        ], env=env, capture_output=True, text=True, timeout=30)
        if failed.returncode != 0:
            raise AssertionError(
                "Vorbedingung fehlgeschlagener Lauf fehlgeschlagen: "
                + failed.stdout + failed.stderr)
        runs_path = cls.log_dir / "runs.json"
        cls.failed_runs_text = runs_path.read_text(encoding="utf-8")
        cls.failed_run_id = json.loads(
            cls.failed_runs_text)["runs"][-1]["id"]
        runs_path.unlink()

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
    def _follows(self, first, second,
                 root="main#nv-main[data-nv-view='activity']"):
        """Prüft, ob ``first`` vor ``second`` in DOM-Reihenfolge steht."""
        return self.page.evaluate("""([first, second, rootSel]) => {
            const root = document.querySelector(rootSel);
            const a = root && root.querySelector(first);
            const b = root && root.querySelector(second);
            return !!a && !!b && !!(a.compareDocumentPosition(b) & 4);
        }""", [first, second, root])

    def test_activity_sections_render(self):
        """Vorbedingung: eine offene Frage in der gemeinsamen Quelle.

        Erwartung: ``[data-nv-activity-tiles]`` → ``[data-nv-questions]`` →
        ``[data-nv-runs]`` sind sichtbar, in dieser Reihenfolge;
        ``p[data-nv-activity-sessions-hint]`` mit Link zu den Projekten,
        ``select[data-nv-questions-project]`` und ``[data-nv-questions-hint]``.
        """
        self.open_activity()
        activity = self.page.locator("main#nv-main[data-nv-view='activity']")
        activity.wait_for(state="visible", timeout=25000)
        self.page.locator(
            "[data-nv-activity-tiles] [data-nv-tile]").first.wait_for(
            state="visible", timeout=20000)
        for selector in ("[data-nv-questions]", "[data-nv-runs]"):
            locator = self.page.locator(selector)
            self.assertEqual(1, locator.count(), f"Bereich {selector} fehlt")
            locator.first.wait_for(state="visible", timeout=20000)
        # F34: Reihenfolge Kacheln → Rückfragen → Läufe.
        self.assertTrue(
            self._follows("[data-nv-activity-tiles]", "[data-nv-questions]"),
            "Die Kacheln stehen nicht vor den Rückfragen")
        self.assertTrue(
            self._follows("[data-nv-questions]", "[data-nv-runs]"),
            "Die Rückfragen stehen nicht vor den Läufen")
        # F34: Sessions-Sektion und Session-Limit wurden entfernt.
        for selector in ("[data-nv-sessions]", "[data-nv-sessions-limit]",
                         "[data-nv-limit-hint]",
                         "select[data-nv-sessions-project]"):
            self.assertEqual(
                0, activity.locator(selector).count(),
                f"F34-Absence: {selector} existiert in der Aktivität")
        # Der Projekthinweis bleibt, mit Link zu den Projekten.
        hint = activity.locator("p[data-nv-activity-sessions-hint]").first
        hint.wait_for(state="visible", timeout=20000)
        self.assertEqual(1, hint.locator("a").count(),
                         "Der Sitzungshinweis nennt die Projekte nicht")
        # F34: Rückfragen zeigen den Projektfilter und den Hint.
        questions = activity.locator("[data-nv-questions]")
        self.assertEqual(
            1, questions.locator("select[data-nv-questions-project]").count(),
            "Die Projektauswahl der Rückfragen fehlt")
        self.assertEqual(
            1, activity.locator("[data-nv-questions-hint]").count(),
            "Der Rückfragen-Hint [data-nv-questions-hint] fehlt")
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
    def test_session_limit_moved_to_project_settings(self):
        """(a) F34-Absence: kein Sessions-Bereich in der Aktivität;
        (b) F34-Vertragsprüfung: Limit speichern + Reload in den
        Projekteinstellungen.

        Aktion: ``nav[data-nv-navs]`` → Home, Projektkarte
        ``a[data-nv-action='open-project']`` → Tab ``settings``,
        ``input[data-nv-session-limit]`` mit ``7`` speichern.
        Erwartung: ``/api/sessions?name=proj`` liefert ``limit=7``; nach
        Reload steht ``7`` im Eingabefeld.
        """
        # (a) Aktivität: Sessions/Limit/Projektfilter sind entfallen.
        self.open_activity()
        activity = self.page.locator("main#nv-main[data-nv-view='activity']")
        activity.wait_for(state="visible", timeout=25000)
        for selector in ("[data-nv-sessions]", "[data-nv-sessions-limit]",
                         "[data-nv-limit-hint]",
                         "select[data-nv-sessions-project]"):
            self.assertEqual(
                0, activity.locator(selector).count(),
                f"F34-Absence: {selector} existiert in der Aktivität")
        self.assert_clean_page()

        # (b) Echte Prüfung: Limit in den Projekteinstellungen.
        self.page.locator(
            "nav[data-nv-navs] button[data-nv-nav='home']").first.click()
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)
        self.page.locator(
            f"article[data-nv-project='{PROJECT}']"
            " a[data-nv-action='open-project']").first.wait_for(
            state="visible", timeout=20000)
        self.page.locator(
            f"article[data-nv-project='{PROJECT}']"
            " a[data-nv-action='open-project']").first.click()
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        settings_tab = self.page.locator("button[data-nv-ptab='settings']")
        settings_tab.wait_for(state="visible", timeout=20000)
        settings_tab.first.click()
        section = self.page.locator("[data-nv-psection='session-limit']").first
        section.wait_for(state="visible", timeout=20000)
        limit_input = section.locator("input[data-nv-session-limit]").first
        limit_input.wait_for(state="visible", timeout=20000)
        limit_input.fill("7")
        section.locator("[data-nv-action='session-limit-save']").first.click()
        self.wait_until(
            lambda: self.api_json(
                f"/api/sessions?name={PROJECT}").get("limit") == 7,
            timeout=20,
            message="Das Session-Limit wurde nicht gespeichert")
        self.assert_clean_page()

        # Reload: Wert wieder angezeigt.
        self.page.reload()
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        section = self.page.locator("[data-nv-psection='session-limit']").first
        section.wait_for(state="visible", timeout=20000)
        limit_input = section.locator("input[data-nv-session-limit]").first
        limit_input.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: (limit_input.input_value() or "").strip() == "7",
            timeout=20,
            message="Das Session-Limit ging beim Reload verloren: "
                    + repr(limit_input.input_value()))
        self.assertEqual(
            7, self.api_json(f"/api/sessions?name={PROJECT}").get("limit"),
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

        Aktion: ``input[data-nv-answer-field]`` füllen,
        ``button[data-nv-answer-send]`` klicken.
        Erwartung: Antwortdatei mit ``text``; die Frage verschwindet
        (``article[data-nv-question-id]`` == 0).
        """
        for path in self.questions.iterdir():
            path.unlink()
        self.write_question_file(
            FREE_QUESTION_ID, FREE_QUESTION_TEXT, [], free_text=True)
        self.open_activity()
        card = self.page.locator(
            f"[data-nv-questions] article[data-nv-question-id='{FREE_QUESTION_ID}']").first
        card.wait_for(state="visible", timeout=20000)
        field = card.locator("input[data-nv-answer-field]").first
        field.wait_for(state="visible", timeout=20000)
        field.fill("Herzlich willkommen")
        card.locator("button[data-nv-answer-send]").first.click()
        path = self.answer_file(FREE_QUESTION_ID)
        self.wait_until(
            lambda: path.is_file(),
            timeout=20,
            message="Die Freitext-Antwort wurde nicht gespeichert")
        answer = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsNone(answer.get("option"), answer)
        self.assertEqual("Herzlich willkommen", answer.get("text"), answer)
        self.wait_until(
            lambda: self.page.locator(
                f"[data-nv-questions]"
                f" article[data-nv-question-id='{FREE_QUESTION_ID}']").count() == 0,
            timeout=20,
            message="Die beantwortete Frage ist in der Aktivität noch sichtbar")
        self.assert_clean_page()

    def test_second_answer_is_rejected_with_message(self):
        """Vorbedingung: Die Frage ist bereits durch einen anderen Client
        beantwortet, wird aber noch angezeigt.

        Aktion: Eine Auswahl anklicken.
        Erwartung: Der Fehler liegt INLINE in ``[data-nv-question-error]``
        (F34: kein Toast); die Antwortdatei und die Karte bleiben unverändert.
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
        # F34: Klick, während die beantwortete Karte noch angezeigt wird.
        self.page.locator("[data-nv-answer='2']").click()
        error = self.page.locator("[data-nv-question-error]").first
        self.wait_until(
            lambda: error.count() == 1 and error.first.is_visible()
            and (error.first.inner_text() or "").strip(),
            timeout=20,
            message="Der Inline-Fehler [data-nv-question-error] fehlt oder "
                    "ist leer")
        error_text = (error.first.inner_text() or "").strip()
        self.assertNotIn(
            error_text,
            self.page.locator("#nv-toasts").inner_text() or "",
            "Der Inline-Fehler [data-nv-question-error] soll kein Toast sein")
        self.assertEqual(
            original,
            json.loads(self.answer_file().read_text(encoding="utf-8")),
            "Die zweite Antwort hat die erste überschrieben")
        self.assertEqual(
            1, self.page.locator(
                f"article[data-nv-question-id='{QUESTION_ID}']").count(),
            "Die beantwortete Karte sollte bei Fehler angezeigt bleiben")
        self.assert_clean_page()


class BellTest(AP22ActivityBrowserTest):
    def run_row_info(self):
        """Gibt ``(text, href)`` einer bellen Live-Zeile zurück, die einen
        ``a[href*=output]``-Link und das Projekt im Zeilentext hat."""
        return self.page.evaluate("""([project]) => {
            const row = Array.from(document.querySelectorAll(
                'div.nv-bell-row.nv-bell-live')).find(node => {
                const link = node.querySelector('a[href*="output"]');
                return link && (node.textContent || '').includes(project);
            });
            if (!row) return null;
            const link = row.querySelector('a[href*="output"]');
            return {text: row.textContent || '',
                    href: link ? (link.getAttribute('href') || '') : ''};
        }""", [PROJECT])

    def test_bell_counts_links_and_updates_after_answer(self):
        """Vorbedingung: eine offene Frage und ein laufender Lauf.

        Erwartung: Zähler sichtbar (≥ 1); eine Live-Zeile nennt die
        Fragetext und das Projekt (F34: Frage ist kein Link mehr, sondern
        ``button[data-nv-live-question-open]``); die Lauf-Zeile bietet
        ``a.nv-bell-link`` mit nichtleerem Ziel auf ``output``; nach der
        Antwort verlässt die Frage die Live-Zeilen (der Zähler darf durch das
        gespeicherte Antwort-Toast nicht sinken: er bleibt vorhanden, sichtbar
        und zeigt weiterhin ≥ 1).
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

        # Die offene Frage: Zeile nennt Fragetext und Projekt, hat keinen Link
        # (F34: Antwort via [data-nv-live-question-open] in der Live-Zeile).
        question_row = panel.locator(
            "div.nv-bell-row.nv-bell-live").filter(has_text=QUESTION_TEXT).first
        self.assertEqual(1, question_row.count(),
                         "Die offene Frage ist im Ausklapp nicht vorhanden")
        self.assertIn(QUESTION_TEXT, question_row.inner_text(),
                      "Die Frage-Zeile nennt die offene Frage nicht")
        self.assertIn(PROJECT, question_row.inner_text(),
                      "Die Frage-Zeile nennt das Projekt nicht")
        self.assertEqual(
            1, question_row.locator("[data-nv-live-question-open]").count(),
            "Der Live-Eintrag der Frage bietet den Antworten-Knopf")
        self.assertEqual(
            0, question_row.locator("a.nv-bell-link").count(),
            "Die Frage ist im Ausklapp (F34) nicht verlinkt, sondern ein "
            "Antworten-Knopf")

        # Der laufende Lauf: Zeile nennt das Projekt, Link hat nichtleeres
        # Ziel auf die Ausgabe.
        info = self.run_row_info()
        self.assertIsNotNone(
            info, "Der laufende Lauf ist im Ausklapp nicht verlinkt")
        self.assertIn(PROJECT, info["text"],
                      "Die Lauf-Zeile nennt das Projekt nicht")
        self.assertIn("output", info["href"],
                      "Der Link des Laufes zeigt nicht auf den Ausgab-Tab")
        self.assertTrue(info["href"].strip(),
                        "Der Lauf-Link hat kein Ziel")

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

        def question_row_gone():
            return panel.locator(
                "div.nv-bell-row.nv-bell-live").filter(
                    has_text=QUESTION_TEXT).count() == 0

        self.wait_until(
            question_row_gone, timeout=25,
            message="Der Live-Eintrag der beantworteten Frage ist nicht "
                    "verschwunden")
        # F34: Das Antwort-Toast wird als gespeicherter Glocke-Eintrag
        # erhalten — der Zähler sinkt nicht mehr über die Frage, die Live-
        # Zeile ist die Verschwindens-Prüfung. Der Zähler muss aber vorhanden,
        # sichtbar und mindestens 1 sein, solange der gespeicherte Antwort-
        # Eintrag noch ungelesen ist (ein fehlender Zähler gälte sonst als
        # „nicht gesunken“).
        badge = self.page.locator("span[data-nv-bell-count]")
        self.assertEqual(
            1, badge.count(), "Der Glocken-Zähler fehlt nach der Antwort")
        badge = badge.first
        self.wait_until(
            lambda: badge.is_visible(), timeout=20,
            message="Der Glocken-Zähler bleibt nach der Antwort verborgen, "
                    "obwohl der gespeicherte Antwort-Eintrag ungelesen ist")
        match = re.search(r"\d+", badge.inner_text() or "")
        self.assertIsNotNone(
            match, "Der Glocken-Zähler zeigt keine Zahl: "
                   + repr(badge.inner_text()))
        self.assertGreaterEqual(
            int(match.group(0)), 1,
            "Der Glocken-Zähler zeigt nach der Antwort kleiner als 1, "
            "obwohl der gespeicherte Antwort-Eintrag ungelesen ist")
        self.assert_clean_page()


class ReviewActivityParityTest(AP22ActivityBrowserTest):
    """Review-Fix AP22: Glocke, Kacheln und Stop decken den Vertrag ab.

    Verbindliche DOM-Hooks dieser Runde (der Vertrag nennt die Inhalte, aber
    keine Zeilen-/Kachelnamen; die Fix-Runde setzt genau diese Namen um)::

        [data-nv-bell-count]                        Zähler (Bestand)
        [data-nv-bell-panel]                        Ausklapp (Bestand)
        a[href*="/work"] im Panel                   blockiertes Paket
        a[href*="/output"] im Panel                 fehlgeschlagener Lauf
        [data-nv-tile="running|questions|blocked"]  Zusammenfassungs-Kacheln
        [data-nv-run="<projekt>"]                   Laufzeile
        [data-nv-action="stop-run"]                 Stop in der Laufzeile
        [data-nv-confirm] oder window.confirm()     optionale Stop-Bestätigung

    Die Glocke zählt drei Quellen: offene Fragen, blockierte Pakete
    (``BLOCKIERT:`` in TICKETS.md) und fehlgeschlagene Läufe
    (``runs.json``, Zustand ``failed``). Blockierte Pakete verlinken auf den
    Arbeits-Tab, fehlgeschlagene Läufe auf die Ausgabe. Der Test nimmt eine
    vorhandene Stop-Bestätigung an, erzwingt aber keine bestimmte Bauform;
    verbindlich ist der Stop-Hook in der Zeile.
    """

    def setUp(self):
        super().setUp()
        (self.log_dir / "runs.json").write_text(
            self.failed_runs_text, encoding="utf-8")
        self.page.on("dialog", lambda dialog: dialog.accept())

    def latest_run_state(self):
        data = json.loads(
            (self.log_dir / "runs.json").read_text(encoding="utf-8"))
        for record in reversed(data.get("runs") or []):
            if record.get("name") == PROJECT:
                return str(record.get("state") or "")
        return None

    def bell_count(self):
        badge = self.page.locator("span[data-nv-bell-count]")
        if badge.count() == 0 or not badge.first.is_visible():
            return 0
        match = re.search(r"\d+", badge.first.inner_text() or "")
        return int(match.group(0)) if match else 0

    def wait_bell_count(self, expected, timeout=25):
        """Wartet auf den Glocken-Zähler und nennt den echten Istwert."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.bell_count() == expected:
                return
            self.page.wait_for_timeout(100)
        self.fail("Die Glocke zählt nicht die erwarteten Quellen (erwartet "
                  + str(expected) + ", gesehen " + str(self.bell_count())
                  + ")")

    def confirm_stop_if_shown(self):
        """Nimmt eine optionale Stop-Bestätigung an (Dialog oder Inline)."""
        for root in (self.page.locator("[data-nv-confirm]"),
                     self.page.locator("[role='dialog']")):
            if not root.count():
                continue
            confirm = root.locator("button").filter(
                has_text=re.compile(r"stopp|stop|ja|yes|bestätig|bestaetig",
                                    re.I)).first
            if confirm.count() and confirm.is_visible():
                confirm.click()
                return

    def activity_tile_value(self, name):
        tile = self.page.locator(f"[data-nv-tile='{name}']").first
        self.wait_until(
            lambda: tile.count() == 1 and tile.is_visible(),
            timeout=20,
            message=f"Die Zusammenfassungs-Kachel {name!r} fehlt")
        text = tile.inner_text() or ""
        match = re.search(r"\d+", text)
        self.assertIsNotNone(
            match, f"Kachel {name!r} zeigt keine Zahl: {text!r}")
        return int(match.group(0))

    def test_bell_counts_questions_blocked_and_failed_with_links(self):
        """Vorbedingung: eine offene Frage, ein ``BLOCKIERT:``-Paket und ein
        fehlgeschlagener Lauf im Register.

        Erwartung: Der Glocken-Zähler ist 3; der Ausklapp nennt alle drei
        Quellen (F34: Live-Zeilen ``div.nv-bell-row.nv-bell-live``). Das
        blockierte Paket: Zeile nennt ``Blocked: <id>`` und bietet
        ``a.nv-bell-link`` → ``/work``; der fehlgeschlagene Lauf: Zeile
        nennt das Projekt und ``a.nv-bell-link`` → ``/output``; die Frage:
        Zeile nennt die Frage und bietet ``button[data-nv-live-question-open]``
        (kein ``a.nv-bell-link``). Nach der Antwort verlässt die Frage die
        Live-Zeilen (Zähler kann durch das gespeicherte Antwort-Toast nicht
        sinken).
        """
        self.boot()
        self.wait_bell_count(3)
        self.page.locator("button[data-nv-bell]").click()
        panel = self.page.locator("[data-nv-bell-panel]")
        panel.wait_for(state="visible", timeout=20000)
        text = panel.inner_text()
        for needle in (QUESTION_TEXT, BLOCKED_ID, self.failed_run_id):
            with self.subTest(needle=needle):
                self.assertIn(needle, text,
                              f"Der Glocken-Ausklapp nennt {needle!r} nicht")

        blocked_row = panel.locator("div.nv-bell-row.nv-bell-live").filter(
            has_text=BLOCKED_ID).first
        self.assertEqual(
            1, blocked_row.count(),
            "Das blockierte Paket ist im Ausklapp nicht vorhanden")
        blocked_link = blocked_row.locator("a.nv-bell-link").first
        self.assertEqual(
            1, blocked_link.count(),
            "Das blockierte Paket hat im Ausklapp keinen Live-Link")
        self.assertIn(
            "/work", blocked_link.get_attribute("href") or "",
            "Der Link des blockierten Pakets zeigt nicht auf den Arbeits-Tab")

        failed_row = panel.locator("div.nv-bell-row.nv-bell-live").filter(
            has_text=self.failed_run_id).first
        self.assertEqual(
            1, failed_row.count(),
            "Der fehlgeschlagene Lauf ist im Ausklapp nicht vorhanden")
        self.assertIn(
            PROJECT, failed_row.inner_text(),
            "Die Lauf-Zeile nennt das Projekt nicht")
        failed_link = failed_row.locator("a.nv-bell-link").first
        self.assertEqual(
            1, failed_link.count(),
            "Der fehlgeschlagene Lauf hat im Ausklapp keinen Live-Link")
        self.assertIn(
            "output", failed_link.get_attribute("href") or "",
            "Der Link des fehlgeschlagenen Laufes zeigt nicht auf die Ausgabe")

        question_row = panel.locator("div.nv-bell-row.nv-bell-live").filter(
            has_text=QUESTION_TEXT).first
        self.assertEqual(
            1, question_row.count(),
            "Die offene Frage ist im Ausklapp nicht vorhanden")
        self.assertEqual(
            1, question_row.locator("[data-nv-live-question-open]").count(),
            "Der Live-Eintrag der Frage bietet den Antworten-Knopf")
        self.assertEqual(
            0, question_row.locator("a.nv-bell-link").count(),
            "Die Frage ist im Ausklapp (F34) nicht verlinkt, sondern ein "
            "Antworten-Knopf")

        self.page.goto(self.base + "/#/activity")
        self.page.locator("main#nv-main[data-nv-view='activity']").wait_for(
            state="visible", timeout=25000)
        self.page.locator("[data-nv-answer='1']").wait_for(
            state="visible", timeout=20000)
        self.page.locator("[data-nv-answer='1']").click()
        self.wait_until(lambda: self.answer_file().is_file(), timeout=20,
                        message="Die Frage wurde nicht beantwortet")
        self.page.goto(self.base + "/#/")
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)
        # F34: Die beantwortete Frage verlässt die Live-Einträge (Das Toast
        # ersetzt sie als gespeicherter Glocke-Eintrag).
        def question_row_gone():
            return self.page.locator(
                "div.nv-bell-row.nv-bell-live").filter(
                    has_text=QUESTION_TEXT).count() == 0

        self.wait_until(
            question_row_gone, timeout=25,
            message="Der Live-Eintrag der beantworteten Frage ist nicht "
                    "verschwunden")
        self.assert_clean_page()

    def test_activity_summary_tiles_show_running_questions_and_blocked(self):
        """Vorbedingung: dieselbe Fixture wie der Glocken-Fall (kein laufender
        Lauf, eine Frage, ein blockiertes Paket).

        Erwartung: Die Kacheln ``running=0``, ``questions=1``, ``blocked=1``
        sind sichtbar und zeigen die Zahlen.
        """
        self.open_activity()
        expected = {"running": 0, "questions": 1, "blocked": 1}
        for name, value in expected.items():
            with self.subTest(tile=name):
                self.assertEqual(
                    value, self.activity_tile_value(name),
                    f"Kachel {name!r} zeigt nicht die erwartete Anzahl")
        self.assert_clean_page()

    def test_run_row_offers_stop_and_stops_the_run(self):
        """Vorbedingung: ein laufender Attrappen-Lauf mit markierter
        tmux-Sitzung im Register.

        Aktion: ``[data-nv-action="stop-run"]`` in der Zeile
        ``[data-nv-run="proj"]`` klicken.
        Erwartung: Der Registereintrag endet im Zustand ``stopped`` und
        ``/api/run-state`` meldet nicht mehr ``running``.
        """
        self.start_run()
        self.open_activity()
        row = self.page.locator(f"[data-nv-run='{PROJECT}']")
        self.wait_until(
            lambda: row.count() == 1 and row.first.is_visible(),
            timeout=20,
            message="Die Laufzeile [data-nv-run] fehlt")
        stop = row.locator("[data-nv-action='stop-run']")
        self.assertEqual(1, stop.count(),
                         "Die Laufzeile bietet keinen Stop-Knopf")
        stop.first.click()
        self.page.wait_for_timeout(300)
        self.confirm_stop_if_shown()
        self.wait_until(
            lambda: self.latest_run_state() == "stopped", timeout=25,
            message="Der Lauf wurde nicht auf 'stopped' gesetzt: "
                    + repr(self.latest_run_state()))
        self.assertFalse(
            self.api_json(f"/api/run-state?name={PROJECT}").get("running"),
            "Die Lauf-Pille meldet nach dem Stop weiterhin einen Lauf")
        self.assert_clean_page()


# ===========================================================================
# Browserabnahme: Aktivität (Kacheln, Rückfragen, Läufe) und Auswertungen
# ===========================================================================

import http.client
import json
import os
import socket
import sqlite3
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

BIN = REPO / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))
import vibe_questions  # noqa: E402  (Import nach sys.path-Anpassung)

QUESTION_TEXT_f34 = "F34-Rückfrage 4711: Soll die Schaltfläche blau werden?"
FREE_TEXT_QUESTION = "F34-FREITEXT 4711: Wie soll die Begrüßung lauten?"

DDL_V2 = """
CREATE TABLE `session_v2` (
  `id` text PRIMARY KEY,
  `project_id` text NOT NULL,
  `workspace_id` text,
  `parent_id` text,
  `fork_session_id` text,
  `fork_boundary` text,
  `slug` text NOT NULL,
  `directory` text NOT NULL,
  `path` text,
  `title` text,
  `version` text NOT NULL,
  `share_url` text,
  `summary_additions` integer,
  `summary_deletions` integer,
  `summary_files` integer,
  `summary_diffs` text,
  `metadata` text,
  `cost` real DEFAULT 0 NOT NULL,
  `tokens_input` integer DEFAULT 0 NOT NULL,
  `tokens_output` integer DEFAULT 0 NOT NULL,
  `tokens_reasoning` integer DEFAULT 0 NOT NULL,
  `tokens_cache_read` integer DEFAULT 0 NOT NULL,
  `tokens_cache_write` integer DEFAULT 0 NOT NULL,
  `revert` text,
  `permission` text,
  `agent` text,
  `model` text,
  `time_created` integer NOT NULL,
  `time_updated` integer NOT NULL,
  `time_compacting` integer,
  `time_archived` integer,
  `time_suspended` integer,
  `resume_attempts` integer DEFAULT 0 NOT NULL,
  `time_idle` integer,
  `time_viewed` integer,
  `idle_outcome` text
);
CREATE TABLE "session_message" (
  `id` text PRIMARY KEY,
  `session_id` text NOT NULL,
  `type` text NOT NULL,
  `seq` integer NOT NULL,
  `time_created` integer NOT NULL,
  `time_updated` integer NOT NULL,
  `data` text NOT NULL
);
"""


class F34ActivityEvalsBrowserTest(unittest.TestCase):
    """Dashboard, Browser, opencode-DB, Laufregister-, Rückfragen-Fixture."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / PROJECT
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "TICKETS.md").write_text(
            "# TICKETS — F34 Test\n\n- [ ] F34-TEST WP zum Test\n"
            "  Beschreibung: WP, das durch die Browser-Tests verwendet wird.\n",
            encoding="utf-8")
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

        # opencode-Datenbank mit bekanntem Verbrauch: 1 Mio. In
        # (400k + 600k Cache), 0,5 Mio. Out (300k + 200k Reasoning).
        cls.db = cls.root / "opencode.db"
        con = sqlite3.connect(str(cls.db))
        con.executescript(DDL_V2)
        now = int(time.time())
        con.execute(
            "insert into session_v2 (id, project_id, slug, directory, title,"
            " version, agent, model, time_created, time_updated)"
            " values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ses_f34_a", "proj", "slug-a", str(cls.project),
             "F34-TEST WP zum Test", "2.1.4", "coding-agent",
             json.dumps({"id": "model-a", "providerID": "opencode"}),
             now, now))
        con.execute(
            "insert into session_message (id, session_id, type, seq,"
            " time_created, time_updated, data) values (?, ?, ?, ?, ?, ?, ?)",
            ("msg_f34_a", "ses_f34_a", "assistant", 1, now, now,
             json.dumps({
                 "agent": "coding-agent",
                 "model": {"id": "model-a", "providerID": "opencode"},
                 "tokens": {
                     "input": 400000,
                     "output": 300000,
                     "reasoning": 200000,
                     "cache": {"read": 600000, "write": 0},
                 },
             })))
        con.commit()
        con.close()

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
            "VIBE_OPENCODE_DB": str(cls.db),
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

        status, body = cls.post_json("/api/language", {"language": "de"})
        if status != 200:
            raise AssertionError(
                "Sprache konnte nicht auf de gesetzt werden: " + body)

        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

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
        self.question_id = vibe_questions.create(
            self.log_dir, project=PROJECT, agent="tester",
            text=QUESTION_TEXT_f34, options=list(QUESTION_OPTIONS), free_text=True)
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

    # ---------- Helpers ----------

    def answer_file(self, qid=None):
        return self.questions / ((qid or self.question_id) + ".answer.json")

    def wait_until(self, predicate, timeout=25,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def api_json(self, path):
        # Absolute URL: Der Page-Load steht zum Zeitpunkt des ersten
        # Aufrufs noch nicht zur Verfügung (about:blank); die Cookies des
        # Browsers authentifizieren die Anfragen danach.
        return self.page.evaluate(
            """async (url) => {
              const response = await fetch(url, {headers: {'Accept': 'application/json'}});
              return await response.json();
            }""", self.base + path)

    def assert_clean_page(self):
        self.assertEqual(
            [], self.page_errors,
            "Die Auswertungsseite erzeugte JavaScript-Fehler")

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_activity(self):
        self.boot()
        self.page.goto(self.base + "/#/activity")
        self.page.locator("main#nv-main[data-nv-view='activity']").wait_for(
            state="visible", timeout=25000)

    def open_evaluations(self, tab=None):
        self.boot()
        hash_ = "/#/evaluations" if tab is None else "/#/evaluations/" + tab
        self.page.goto(self.base + hash_)
        self.page.locator("main#nv-main[data-nv-view='evaluations']").wait_for(
            state="visible", timeout=25000)

    @classmethod
    def post_json(cls, path, body):
        conn = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=10)
        try:
            conn.request("POST", path,
                         body=json.dumps(body).encode("utf-8"), headers={
                             "Host": f"127.0.0.1:{cls.port}",
                             "X-Token": cls.token,
                             "Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, response.read().decode("utf-8", "replace")
        finally:
            conn.close()

    # ---------- Fixtures ----------

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

    def start_finished_run(self):
        result = subprocess.run([
            sys.executable, str(RUNS_PY), "start",
            "--runtime", str(self.log_dir),
            "--project", str(self.project.resolve()),
            "--name", PROJECT, "--key", PROJECT, "--agent", "vibe-agent",
            "--session", "vibe-f34-finished", "--state", "finished",
        ], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(
            result.returncode, 0,
            "Vorbedingung abgeschlossener Lauf (state=finished) fehlgeschlagen: "
            + result.stdout + result.stderr)
        data = json.loads(
            (self.log_dir / "runs.json").read_text(encoding="utf-8"))
        return data["runs"][-1]["id"]

    @staticmethod
    def digits(text):
        return (text or "").replace(".", "").replace(",", "")


class ActivityTest(F34ActivityEvalsBrowserTest):
    def test_activity_render_order_without_sessions_hooks(self):
        """Name: Aktivität — Bereichsreihenfolge ohne Sitzungs-Hooks.
        Vorbedingung: eine offene Rückfrage, kein Lauf im Register.
        Aktion: Aktivitätsansicht laden.
        Erwartung: ``[data-nv-activity-tiles]``, ``[data-nv-questions]`` und
        ``[data-nv-runs]`` sind vorhanden; DOM-Reihenfolge ist
        Kacheln → Rückfragen → Läufe; die Hooks ``[data-nv-sessions]``,
        ``[data-nv-sessions-limit]`` und ``[data-nv-limit-hint]`` existieren
        nicht."""
        self.open_activity()
        for selector in ("[data-nv-activity-tiles]", "[data-nv-questions]",
                         "[data-nv-runs]"):
            locator = self.page.locator(selector)
            self.assertEqual(1, locator.count(), f"Bereich {selector} fehlt")
            locator.first.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: self.page.locator("[data-nv-tile='questions']").count() == 1,
            timeout=25, message="Die Summary-Kachel 'questions' erscheint nicht")
        order = self.page.evaluate(
            """() => {
              const a = document.querySelector('[data-nv-activity-tiles]');
              const b = document.querySelector('[data-nv-questions]');
              const c = document.querySelector('[data-nv-runs]');
              return !!a && !!b && !!c
                && (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0
                && (b.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
            }""")
        self.assertTrue(order, "DOM-Reihenfolge ist nicht Kacheln → Rückfragen → Läufe")
        for selector in ("[data-nv-sessions]", "[data-nv-sessions-limit]",
                         "[data-nv-limit-hint]"):
            self.assertEqual(
                0, self.page.locator(selector).count(),
                f"{selector} existiert, ist aber entfernt")
        self.assert_clean_page()

    def test_activity_sessions_hint_links_to_projects(self):
        """Name: Aktivität — Hinweis für Sitzungen.
        Vorbedingung: eine offene Rückfrage.
        Aktion: Aktivitätsansicht laden.
        Erwartung: ``p[data-nv-activity-sessions-hint]`` ist sichtbar und
        verweist auf die Projekte (Linkziel ``#/``)."""
        self.open_activity()
        hint = self.page.locator("[data-nv-activity-sessions-hint]").first
        hint.wait_for(state="visible", timeout=20000)
        self.assertIn("Projekt", hint.inner_text())
        link = hint.locator("a").first
        self.assertEqual(1, link.count(), "Hinweis verweist auf kein Ziel")
        self.assertTrue((link.get_attribute("href") or "").startswith("#/"))
        self.assert_clean_page()

    def test_activity_running_run_row_offers_open_and_stop(self):
        """Name: Aktivität — Laufzeile mit Aktion „Öffnen" und Stop.
        Vorbedingung: laufender Lauf im Register (v2 + tmux, Pattern AP22).
        Aktion: Aktivitätsansicht öffnen.
        Erwartung: Die Laufzeile ``div[data-nv-run='proj']`` nennt das Projekt,
        zeigt einen Zustands-Pille (läuft), bietet
        ``[data-nv-action='open-output']`` und ``[data-nv-action='stop-run']``
        (Stopp bleibt verfügbar)."""
        self.start_run()
        self.open_activity()
        row = self.page.locator(f"[data-nv-run='{PROJECT}']")
        self.wait_until(lambda: row.count() == 1 and row.first.is_visible(),
                        timeout=25,
                        message="Die laufende Laufzeile erscheint nicht")
        self.assertIn(PROJECT, row.first.inner_text())
        self.assertGreaterEqual(row.first.locator(".nv-pill").count(), 1,
                                "Die Laufzeile zeigt keinen Zustands-Pille")
        self.assertIn("läuft", row.first.locator(".nv-pill").first.inner_text())
        open_link = row.first.locator("[data-nv-action='open-output']")
        self.assertEqual(1, open_link.count(), "Die Zeile bietet keinen Open-Knopf")
        self.assertTrue(open_link.is_visible())
        self.assertIn("Öffnen", open_link.inner_text())
        self.assertIn("output", open_link.get_attribute("href") or "")
        self.assertEqual(1, row.first.locator("[data-nv-action='stop-run']").count(),
                         "Stopp bleibt in der Laufzeile verfügbar")
        self.assert_clean_page()

    def test_activity_question_option_answer_creates_answer(self):
        """Name: Aktivität — Rückfrage mit Auswahl beantworten.
        Vorbedingung: eine offene Rückfrage mit zwei Auswahlmöglichkeiten
        (gemeinsame Rückfrage-Karte ``NV.questionCard``).
        Aktion: ``[data-nv-answer='1']`` klicken.
        Erwartung: ``article[data-nv-question][data-nv-question-id]`` zeigt die
        Karte (Projekt, Fragetext); ``<id>.answer.json`` entsteht mit
        ``option=0`` und ``option_text``; die Karte verschwindet lokal."""
        self.open_activity()
        self.wait_until(
            lambda: self.page.locator("article[data-nv-question][data-nv-question-id]").count() == 1,
            timeout=25, message="Die Rückfrage-Karte erscheint nicht")
        card = self.page.locator("article[data-nv-question][data-nv-question-id]").first
        self.assertIn(QUESTION_TEXT_f34, card.inner_text())
        self.assertEqual(1, self.page.locator("[data-nv-answer='2']").count(),
                         "Die zweite Auswahlmöglichkeit fehlt")
        self.page.locator("[data-nv-answer='1']").first.click()
        self.wait_until(lambda: self.answer_file().is_file(), timeout=20,
                        message="Die gewählte Antwort wurde nicht gespeichert")
        answer = json.loads(self.answer_file().read_text(encoding="utf-8"))
        self.assertEqual(0, answer.get("option"), answer)
        self.assertEqual("Ja, blau", answer.get("option_text"), answer)
        self.wait_until(
            lambda: self.page.locator("article[data-nv-question]").count() == 0,
            timeout=20, message="Die beantwortete Karte bleibt sichtbar")
        self.assert_clean_page()

    def test_activity_question_free_text_answer_creates_answer(self):
        """Name: Aktivität — Rückfrage mit Freitext beantworten.
        Vorbedingung: offene Rückfrage ohne Auswahlmöglichkeiten (freitext).
        Aktion: ``[data-nv-answer-field]`` füllen, ``[data-nv-answer-send]``
        klicken.
        Erwartung: ``<id>.answer.json`` entsteht mit ``text``; die Karte
        verschwindet lokal."""
        for path in self.questions.iterdir():
            path.unlink()
        self.question_id = vibe_questions.create(
            self.log_dir, project=PROJECT, agent="tester",
            text=FREE_TEXT_QUESTION, options=[], free_text=True)
        self.open_activity()
        field = self.page.locator("[data-nv-answer-field]").first
        field.wait_for(state="visible", timeout=20000)
        field.fill("Herzlich willkommen")
        self.page.locator("[data-nv-answer-send]").first.click()
        self.wait_until(lambda: self.answer_file().is_file(), timeout=20,
                        message="Die Freitext-Antwort wurde nicht gespeichert")
        answer = json.loads(self.answer_file().read_text(encoding="utf-8"))
        self.assertIsNone(answer.get("option"), answer)
        self.assertEqual("Herzlich willkommen", answer.get("text"), answer)
        self.wait_until(
            lambda: self.page.locator("article[data-nv-question]").count() == 0,
            timeout=20, message="Die beantwortete Karte bleibt sichtbar")
        self.assert_clean_page()


class CostsTest(F34ActivityEvalsBrowserTest):
    def test_costs_summary_statistics_and_currency_eur(self):
        """Name: Kostenübersicht — Zusammenfassung und Währung EUR.
        Vorbedingung: Datenbank mit 1 Sitzung (``opencode/model-a``: Eingabe
        1 Mio., davon 600k Cache, Ausgabe 500k); Sprache ``de``; Währung
        ``EUR`` (erzwungen, als Belt-and-Braces gegen Leckage).
        Aktion: ``POST /api/ui_settings {currency: EUR}``; Auswertungen
        → ``costs`` öffnen.
        Erwartung: ``div[data-nv-cost-summary]`` mit den Stats ``total-cost``,
        ``total-input``, ``total-cached``, ``total-output``,
        ``total-sessions``, ``current-month`` und ``projects`` sichtbar; die
        Stats haben sichtbare Werte; ``[data-nv-cost-currency-hint]``
        verborgen; ``[data-nv-costs-empty]`` während der DB vorliegt
        verborgen."""
        self.post_json("/api/ui_settings", {"currency": "EUR", "usd_rate": 1.0})
        self.open_evaluations("costs")
        summary = self.page.locator("[data-nv-cost-summary]").first
        summary.wait_for(state="visible", timeout=20000)
        for key in ("total-cost", "total-input", "total-cached", "total-output",
                    "total-sessions", "current-month", "projects"):
            with self.subTest(stat=key):
                stat = self.page.locator(f"[data-nv-cost-stat='{key}']").first
                self.assertEqual(1, stat.count(), f"Stat {key} fehlt")
                stat.wait_for(state="visible", timeout=20000)
                self.assertTrue(stat.inner_text().strip(),
                                f"Stat {key} ist leer")
        self.assertIn("€", self.page.locator(
            "[data-nv-cost-stat='total-cost'] strong").first.inner_text())
        self.assertEqual("1000000", self.digits(self.page.locator(
            "[data-nv-cost-stat='total-input'] strong").first.inner_text()))
        self.assertEqual("600000", self.digits(self.page.locator(
            "[data-nv-cost-stat='total-cached'] strong").first.inner_text()))
        self.assertEqual("500000", self.digits(self.page.locator(
            "[data-nv-cost-stat='total-output'] strong").first.inner_text()))
        self.assertEqual("1", self.digits(self.page.locator(
            "[data-nv-cost-stat='total-sessions'] strong").first.inner_text()))
        self.assertEqual("1", self.digits(self.page.locator(
            "[data-nv-cost-stat='projects'] strong").first.inner_text()))
        current_month = self.page.locator(
            "[data-nv-cost-stat='current-month']").first
        self.assertIn("Eingabe", current_month.inner_text())
        self.assertIn("Ausgabe", current_month.inner_text())
        self.assertTrue(self.page.locator(
            "[data-nv-cost-currency-hint]").first.is_hidden())
        self.assertTrue(self.page.locator(
            "[data-nv-costs-empty]").first.is_hidden())
        self.assert_clean_page()

    def test_costs_project_table_expand_shows_detail(self):
        """Name: Kostenübersicht — Projekttabelle und Aufklapp-Detail.
        Vorbedingung: Projekttabelle ``table[data-nv-cost-projects]`` mit Zeile
        ``tr[data-nv-cost-project='proj']``; DB liegt vor.
        Aktion: ``button[data-nv-cost-expand]`` klicken.
        Erwartung: ``tr[data-nv-cost-detail]`` wird sichtbar; enthält
        ``div[data-nv-cost-months]`` und ``table[data-nv-cost-packages]``."""
        self.open_evaluations("costs")
        table = self.page.locator("[data-nv-cost-projects]").first
        table.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            1, self.page.locator("[data-nv-cost-projects] tr[data-nv-cost-project='proj']").count(),
            "Die Projektzeile [data-nv-cost-project='proj'] fehlt")
        expand = self.page.locator("[data-nv-cost-projects] [data-nv-cost-expand]").first
        expand.wait_for(state="visible", timeout=20000)
        self.assertEqual("false", expand.get_attribute("aria-expanded"))
        expand.click()
        detail = self.page.locator("[data-nv-cost-detail]").first
        detail.wait_for(state="visible", timeout=20000)
        self.assertEqual("true", self.page.locator(
            "[data-nv-cost-projects] [data-nv-cost-expand]").first.get_attribute("aria-expanded"))
        self.wait_until(lambda: self.page.locator("div[data-nv-cost-months]").count() == 1,
                        timeout=25, message="Das Detail lädt nicht: div[data-nv-cost-months] fehlt")
        self.assertEqual(1, self.page.locator("table[data-nv-cost-packages]").count())
        self.assert_clean_page()

    def test_costs_missing_price_editor_save_updates(self):
        """Name: Kostenübersicht — Fehlender Preis, Preis-Editor, Speichern.
        Vorbedingung: ein Paket mit unbekanntem Preis (``opencode/model-a``),
        detail auf ``proj`` aufgeklappt.
        Aktion: ``button[data-nv-cost-price-link]`` klicken; im
        ``section[data-nv-price-editor]`` Felder ausfüllen;
        ``button[data-nv-action='cost-prices-save']`` klicken.
        Erwartung: ``span[data-nv-cost-missing]`` „Preis fehlt" und
        ``button[data-nv-cost-price-link]`` werden angezeigt; nach dem
        Speichern ist ``[data-nv-cost-missing]`` weg, ein Toast meldet
        „Preise gespeichert", und ``costs.json`` enthält den neuen Preis."""
        self.open_evaluations("costs")
        table = self.page.locator("[data-nv-cost-projects]").first
        table.wait_for(state="visible", timeout=20000)
        self.page.locator("[data-nv-cost-projects] [data-nv-cost-expand]").first.click()
        self.wait_until(lambda: self.page.locator("[data-nv-cost-missing]").count() == 1,
                        timeout=25,
                        message="Der fehlende Preis meldet sich nicht in der Detail-Tabelle")
        self.page.locator("[data-nv-cost-missing]").first.is_visible()
        self.assertEqual(1, self.page.locator("[data-nv-cost-price-link]").count())
        self.page.locator("[data-nv-cost-price-link]").first.click()
        editor = self.page.locator("[data-nv-price-editor]").first
        editor.wait_for(state="visible", timeout=20000)
        project_select = editor.locator("[data-nv-price-project]").first
        self.assertEqual(1, project_select.count())
        self.assertEqual(PROJECT, project_select.input_value())
        # Das Modell erscheint im Editor, sobald der Detailaufruf ankam.
        self.wait_until(
            lambda: editor.locator("input[data-nv-price-field='input']").count() == 1,
            timeout=25, message="Keine Eingabezeilen im Preis-Editor")
        editor.locator("input[data-nv-price-field='input']").first.fill("1.5")
        editor.locator("input[data-nv-price-field='cached_input']").first.fill("0.25")
        editor.locator("input[data-nv-price-field='output']").first.fill("2.0")
        self.page.locator("[data-nv-action='cost-prices-save']").first.click()
        toast = self.page.locator("[data-nv-toast-auto]").first
        toast.wait_for(state="visible", timeout=20000)
        self.assertIn("Preise", toast.inner_text())
        self.wait_until(lambda: self.page.locator("[data-nv-cost-missing]").count() == 0,
                        timeout=25,
                        message="Der Preisfehler verschwindet nicht nach dem Speichern")
        costs_file = self.root / "_toolchain" / "costs.json"
        self.assertTrue(costs_file.exists(),
                        "costs.json liegt nach dem Speichern nicht vor")
        stored = json.loads(costs_file.read_text(encoding="utf-8"))
        price = stored["projects"][PROJECT]["models"]["opencode/model-a"]
        self.assertEqual(
            {"input": 1.5, "cached_input": 0.25, "output": 2.0}, price,
            "costs.json enthält die falschen Preise: " + repr(price))
        self.assert_clean_page()

    def test_costs_currency_usd_shows_dollar_and_hint(self):
        """Name: Kostenübersicht — Währung USD.
        Vorbedingung: DB liegt vor; Sprache ``de``; ``POST /api/ui_settings``
        mit ``currency=USD, usd_rate=2.0`` ist möglich.
        Aktion: ``POST /api/ui_settings {currency: USD, usd_rate: 2.0}``;
        Auswertungen → ``costs`` öffnen.
        Erwartung: ``[data-nv-cost-stat='total-cost']`` beginnt mit ``$``;
        ``small[data-nv-cost-currency-hint]`` ist sichtbar und nennt die
        Umrechnung (USD); Danach wird auf EUR zurückgesetzt."""
        status, body = self.post_json(
            "/api/ui_settings", {"currency": "USD", "usd_rate": 2.0})
        self.assertEqual(200, status, "Umschaltung auf USD fehlgeschlagen: " + body)
        self.open_evaluations("costs")
        self.wait_until(
            lambda: self.api_json("/api/ui_settings").get("currency") == "USD",
            timeout=20, message="Währung umgestellt, GET zeigt kein USD")
        total = self.page.locator("[data-nv-cost-stat='total-cost'] strong").first
        total.wait_for(state="visible", timeout=20000)
        self.assertTrue(
            total.inner_text().strip().startswith("$"),
            "Gesamtkosten beginnen nicht mit $: " + (total.inner_text() or ""))
        hint = self.page.locator("[data-nv-cost-currency-hint]").first
        hint.wait_for(state="visible", timeout=20000)
        self.assertIn("USD", hint.inner_text())
        status, body = self.post_json(
            "/api/ui_settings", {"currency": "EUR", "usd_rate": 1.0})
        self.assertEqual(200, status, "Zurücksetzen auf EUR fehlgeschlagen: " + body)
        self.assert_clean_page()

    def test_costs_empty_state_without_database(self):
        """Name: Kostenübersicht — Leerzustand ohne Datenbank.
        Vorbedingung: Fixture-Datenbank liegt vor; Auswertungen → ``costs``.
        Aktion: Datenbank für den Laufzeitordner verschieben; Seite öffnen.
        Erwartung: ``p[data-nv-costs-empty]`` sichtbar, Text enthält „Kosten
        nicht verfügbar" und die Ursache aus ``message``; Link zu den
        Einstellungen (Modellpreise); ``[data-nv-cost-summary]`` weiter
        sichtbar mit 0en."""
        hidden = self.db.with_name(self.db.name + ".hidden")
        self.db.rename(hidden)
        try:
            self.open_evaluations("costs")
            empty = self.page.locator("[data-nv-costs-empty]").first
            empty.wait_for(state="visible", timeout=20000)
            text = empty.inner_text() or ""
            self.assertIn("Kosten nicht verfügbar", text)
            self.assertIn("noch kein Agentenlauf", text)
            link = empty.locator("a").first
            self.assertEqual(1, link.count())
            self.assertTrue((link.get_attribute("href") or "").startswith("#/settings"))
            self.page.locator("[data-nv-cost-summary]").first.wait_for(
                state="visible", timeout=20000)
            self.assert_clean_page()
        finally:
            hidden.rename(self.db)


    def test_costs_show_persisted_package_aggregation_without_live_sessions(self):
        """GH-99: Kostenübersicht aus persistierten Paketkosten.

        Vorbedingung: ``/api/costs`` liefert persistierte Paketkosten, bei
        denen zwei Sitzungen desselben Pakets bereits zu einem Paketwert
        zusammengeführt wurden; ``total.sessions`` ist 0 (keine live
        Sitzungen mehr). Simuliert per API-Route, ohne Modellaufrufe.

        Erwartung: Die Zusammenfassung zeigt den gespeicherten Kostenwert,
        obwohl keine Sitzungen mehr existieren; die aufklappbare Paketzeile
        nennt das Paket und den aggregierten Wert aus beiden Sitzungen.
        """
        tokens = {"input": 800000, "cached": 400000, "output": 200000}
        package = {
            "id": "F34-TEST", "title": "WP zum Test", "month": "2026-11",
            "sessions": 2, "tokens": tokens, "cost": 0.042,
            "models": [{"price_source": "system"}],
        }
        detail = {
            "available": True, "project": PROJECT,
            "packages": [package],
            "total": {"tokens": tokens, "cost": 0.042, "sessions": 2},
            "monthly": [{"month": "2026-11", "sessions": 2,
                         "tokens": tokens, "cost": 0.042}],
            "user_prices": {}, "global_prices": {},
        }
        overview = {
            "available": True, "currency": "EUR",
            "projects": [{"name": PROJECT, "packages": 1, "sessions": 0,
                          "tokens": tokens, "cost": 0.042, "monthly": []}],
            "total": {"tokens": tokens, "cost": 0.042, "sessions": 0},
            "monthly": [], "global_prices": {},
        }

        def handle_costs(route):
            body = detail if "name=" in route.request.url else overview
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(body, ensure_ascii=False))

        self.page.route("**/api/costs*", handle_costs)
        self.post_json("/api/ui_settings", {"currency": "EUR", "usd_rate": 1.0})
        self.open_evaluations("costs")

        # Keine live Sitzungen, aber der persistierte Kostenwert ist sichtbar.
        sessions_stat = self.page.locator(
            "[data-nv-cost-stat='total-sessions'] strong").first
        sessions_stat.wait_for(state="visible", timeout=20000)
        self.assertEqual("0", self.digits(sessions_stat.inner_text()))
        cost_stat = self.page.locator(
            "[data-nv-cost-stat='total-cost'] strong").first
        self.assertIn("0,0420", cost_stat.inner_text())

        # Detail: das Paket trägt die aus zwei Sitzungen zusammengefassten
        # Werte, obwohl keine einzelne Sitzung mehr vorliegt.
        self.page.locator(
            "[data-nv-cost-projects] [data-nv-cost-expand]").first.click()
        self.wait_until(
            lambda: self.page.locator(
                "table[data-nv-cost-packages] tr").count() >= 2,
            timeout=25, message="Die Pakettabelle lädt nicht")
        row = self.page.locator(
            "table[data-nv-cost-packages] tr", has_text="F34-TEST").first
        self.assertEqual(1, row.count(),
                         "Die aggregierte Paketzeile F34-TEST fehlt")
        cells = [cell.inner_text().strip() for cell in row.locator("td").all()]
        self.assertIn("F34-TEST", cells, cells)
        self.assertIn("2", cells, "Die aggregierte Sitzungszahl fehlt: " + repr(cells))
        self.assertTrue(
            any("0,0420" in cell for cell in cells),
            "Der persistierte Paketkostenwert fehlt: " + repr(cells))
        self.assert_clean_page()


class RunsTableTest(F34ActivityEvalsBrowserTest):
    def test_runs_table_cleanup_removes_finished_run(self):
        """Name: Läufe — Register, Filter, Cleanup.
        Vorbedingung: abgeschlossener Lauf im Register (``state=finished``).
        Aktion: Auswertungen → ``runs`` öffnen; ``[data-nv-action="runs-cleanup"]``
        klicken.
        Erwartung: Lauftabelle ``table[data-nv-run-table]`` mit Lauf, Projekt,
        Zustand (``tr[data-nv-run-state='finished']``), Sitzung, Start, Dauer,
        Bereinigbarkeit (``[data-nv-run-pruneable]``); Filter
        ``[data-nv-run-search]``, ``select[data-nv-run-state]``;
        ``[data-nv-action='runs-prune']`` und ``[data-nv-action='runs-cleanup']``
        existieren; keine rohen JSON-Objekte. Nach dem Klick zeigt
        ``[data-nv-runs-result]`` „1 entfernt" und die Zeile ist weg;
        „Keine Läufe im Register." ist sichtbar."""
        run_id = self.start_finished_run()
        self.open_evaluations("runs")
        table = self.page.locator("[data-nv-run-table]").first
        table.wait_for(state="visible", timeout=20000)
        row = self.page.locator(f"[data-nv-run='{run_id}']")
        self.wait_until(
            lambda: row.count() == 1 and row.first.is_visible(),
            timeout=25, message="Der beendete Lauf erscheint nicht im Register")
        self.assertEqual(1, row.locator("[data-nv-run-state='finished']").count(),
                         "Die Laufzeile zeigt kein finished-Badge")
        self.assertEqual(1, row.locator("[data-nv-run-pruneable]").count(),
                         "Die Laufzeile ist nicht als bereinigbar markiert")
        self.assertEqual(1, self.page.locator("[data-nv-run-search]").count())
        self.assertEqual(1, self.page.locator("select[data-nv-run-state]").count())
        self.assertEqual(1, self.page.locator("[data-nv-action='runs-prune']").count())
        self.assertEqual(1, self.page.locator("[data-nv-action='runs-cleanup']").count())
        text = table.inner_text() or ""
        self.assertNotIn("{", text)
        self.assertNotIn("}", text)
        self.assertNotIn('"', text)
        self.page.locator("[data-nv-action='runs-cleanup']").first.click()
        result = self.page.locator("[data-nv-runs-result]").first
        result.wait_for(state="visible", timeout=20000)
        self.assertIn("entfernt", result.inner_text())
        self.wait_until(lambda: row.count() == 0, timeout=25,
                        message="Der beendete Lauf bleibt nach Cleanup sichtbar")
        self.assertIn("Keine Läufe im Register", table.inner_text())
        self.assert_clean_page()


class EnvironmentTest(F34ActivityEvalsBrowserTest):
    def env_text(self):
        parts = []
        for selector in ("[data-nv-env-doctor]", "[data-nv-paths]",
                         "[data-nv-harness-status]"):
            locator = self.page.locator(selector).first
            if locator.count():
                parts.append(locator.inner_text() or "")
        return "\n".join(parts)

    def test_environment_doctor_rows_and_paths(self):
        """Name: Umgebung — Prüfungen und Pfade.
        Vorbedingung: Auswertungen → ``environment``.
        Erwartung: ``div[data-nv-env-doctor]`` mit mindestens einer
        ``[data-nv-doctor-row]``, die ``data-nv-ok`` (``true``/``false``)
        trägt; ``div[data-nv-paths]`` sichtbar mit Inhalt (Schlüssel
        ``runtime``); ``[data-nv-emulator]`` existiert nicht; kein Text
        „opencode-Server" oder „Emulator" im Environment-Bereich."""
        self.open_evaluations("environment")
        doctor = self.page.locator("[data-nv-env-doctor]").first
        doctor.wait_for(state="visible", timeout=20000)
        rows = self.page.locator("[data-nv-env-doctor] [data-nv-doctor-row]")
        self.assertGreaterEqual(rows.count(), 1, "Keine Prüfungs-Zeilen gefunden")
        for index in range(rows.count()):
            ok = rows.nth(index).get_attribute("data-nv-ok")
            self.assertIsNotNone(ok, "Prüfungs-Zeile fehlt data-nv-ok")
            self.assertIn(ok, ("true", "false"), f"Prüfungs-Zeile {index}: ungültiges data-nv-ok")
        paths = self.page.locator("[data-nv-paths]").first
        paths.wait_for(state="visible", timeout=20000)
        self.assertIn("runtime", paths.inner_text())
        text = self.env_text()
        self.assertNotIn("{", text)
        self.assertNotIn("}", text)
        self.assertNotIn("Emulator", text)
        self.assertNotIn("opencode-Server", text)
        self.assertEqual(0, self.page.locator("[data-nv-emulator]").count())
        self.assert_clean_page()

    def test_environment_harness_status_display_only(self):
        """Name: Umgebung — Harness-Status nur Anzeige.
        Vorbedingung: Auswertungen → ``environment``.
        Erwartung: ``div[data-nv-harness-status]`` ist sichtbar mit Text
        („Auswahl" bis Anzeige des Harness); keine ``[data-nv-action]``-Hooks
        innerhalb."""
        self.open_evaluations("environment")
        harness = self.page.locator("[data-nv-harness-status]").first
        harness.wait_for(state="visible", timeout=20000)
        text = harness.inner_text() or ""
        self.assertIn("Auswahl", text)
        self.assertEqual(0, harness.locator("[data-nv-action]").count())
        self.assert_clean_page()


class EvalTabsTest(F34ActivityEvalsBrowserTest):
    def test_eval_tabs_switch_without_full_reload(self):
        """Name: Auswertungen — Tabwechsel ohne Voll-Neurender.
        Vorbedingung: Auswertungen → ``costs`` mit aufgeklapptem Projekt
        (``[data-nv-cost-expand] aria-expanded == 'true'``).
        Aktion: ``button[data-nv-etab='runs']`` klicken, zurück auf ``costs``.
        Erwartung: ``[data-nv-eval-tabs]``/``button[data-nv-etab]``; URL zeigt
        ``#/evaluations/runs``; ``[data-nv-eval-panel='runs']`` sichtbar,
        ``[data-nv-eval-panel='costs']`` verborgen; beim Wechsel zurück ist das
        gleiche Dokument (Marker ``window.__h2``) und die Expansions-Stufe
        bleibt (``aria-expanded == 'true'``)."""
        self.open_evaluations("costs")
        self.page.evaluate(
            "() => { window.__h2 = document.querySelector('h2.nv-page-title'); }")
        expand = self.page.locator(
            "[data-nv-cost-projects] [data-nv-cost-expand]").first
        expand.wait_for(state="visible", timeout=20000)
        expand.click()
        self.page.locator("[data-nv-cost-detail]").first.wait_for(
            state="visible", timeout=20000)
        self.assertEqual(
            "true", self.page.locator(
                "[data-nv-cost-projects] [data-nv-cost-expand]").first.get_attribute("aria-expanded"))
        # Wechsel auf runs
        self.assertEqual(1, self.page.locator("[data-nv-etab='runs']").count())
        self.assertEqual(1, self.page.locator("[data-nv-etab='costs']").count())
        self.assertEqual(1, self.page.locator("[data-nv-etab='environment']").count())
        self.page.locator("[data-nv-etab='runs']").first.click()
        self.page.locator("[data-nv-eval-panel='runs']").first.wait_for(
            state="visible", timeout=20000)
        self.assertIn("evaluations/runs", self.page.url)
        self.assertTrue(self.page.locator("[data-nv-eval-panel='costs']").first.is_hidden())
        # Wechsel zurück auf costs — kein Reload
        self.page.locator("[data-nv-etab='costs']").first.click()
        self.page.locator("[data-nv-eval-panel='costs']").first.wait_for(
            state="visible", timeout=20000)
        self.assertTrue(self.page.evaluate(
            "() => window.__h2 === document.querySelector('h2.nv-page-title')"),
            "Tabwechsel hat einen Full-Neuladen ausgelöst")
        self.assertEqual(
            "true", self.page.locator("[data-nv-cost-expand]").first.get_attribute("aria-expanded"))


if __name__ == "__main__":
    unittest.main()
