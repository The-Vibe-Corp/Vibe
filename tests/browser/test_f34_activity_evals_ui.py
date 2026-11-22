"""Browserabnahme F34 WP3: Aktivität (Kacheln, Rückfragen, Läufe) und Auswertungen
(Kosten, Läufe, Umgebung).

Die Fälle leiten sich aus ``docs/features/F34.md`` (Abschnitte „WP3 —
Aktivität und Auswertungen" und „Zentrale Rückfragen") ab. Das echte Dashboard
läuft isoliert auf freiem Port. Vormoderne Fixtures (vgl.
``tests/browser/test_costs_ui.py`` und ``tests/browser/test_ap22_activity_ui.py``):

* opencode-Datenbank (v2-Schema wie ``tests/browser/test_costs_ui.py``) mit
  einem bekannten Agenten-Sitzungsverbrauch;
* Rückfragen über ``vibe_questions.create`` (echte Dateien im Laufzeitordner);
* Laufregister über ``vibe_runs.py start``;
* Fritzbox-Automatik über ``POST /api/fritz {action: automation}``.

Es werden keine Modellaufrufe ausgelöst; ``tmux`` ist nur für den laufenden
Lauf-Fixture nötig (Pattern aus ``test_ap22_activity_ui.py``). Chromium kommt
aus dem Nur-Lese-Cache (``PLAYWRIGHT_BROWSERS_PATH``).

Jeder Testfall hat einen Docstring mit Vorbedingung, Aktion und Erwartung;
Name und Verhalten sind den F34-Hooks zugeordnet.
"""
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

_BROWSERS = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"
RUNS_PY = REPO / "bin" / "vibe_runs.py"
BIN = REPO / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))
import vibe_questions  # noqa: E402  (Import nach sys.path-Anpassung)

PROJECT = "proj"
TMUX_SESSION = "vibe-" + PROJECT
QUESTION_TEXT = "F34-Rückfrage 4711: Soll die Schaltfläche blau werden?"
QUESTION_OPTIONS = ["Ja, blau", "Nein, grau"]
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


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


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
            text=QUESTION_TEXT, options=list(QUESTION_OPTIONS), free_text=True)
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
        """Name: Aktivitätssuche sowie API-Aufrufe; erwarte dies.
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
        self.assertIn(QUESTION_TEXT, card.inner_text())
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


class RunsTest(F34ActivityEvalsBrowserTest):
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
                         "[data-nv-harness-status]", "[data-nv-fritz-status]"):
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

    def test_environment_fritz_automation_toggle(self):
        """Name: Umgebung — Fritzbox-Automatik Ein/Aus.
        Vorbedingung: Auswertungen → ``environment``; Fritz-Automatik aus.
        Aktion 1: Seite laden (Automatik aus). Aktion 2:
        ``POST /api/fritz {action: automation, enabled: true}``, Seite
        neu laden.
        Erwartung 1: ``[data-nv-fritz-hint]`` sichtbar;
        ``[data-nv-action='fritz-reconnect']`` nicht verfügbar.
        Erwartung 2: ``[data-nv-action='fritz-reconnect']`` sichtbar;
        ``[data-nv-fritz-status]`` textet „Automatik: an"."""
        self.open_evaluations("environment")
        hint = self.page.locator("[data-nv-fritz-hint]").first
        hint.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            0, self.page.locator("[data-nv-action='fritz-reconnect']").count())
        status, body = self.post_json(
            "/api/fritz", {"action": "automation", "enabled": True})
        self.assertEqual(200, status, "Automatik aktivieren fehlgeschlagen: " + body)
        self.wait_until(
            lambda: self.api_json("/api/fritz").get("automation") is True,
            timeout=20, message="Fritz-Automatik entspricht GET nicht")
        self.open_evaluations("environment")
        reconnect = self.page.locator("[data-nv-action='fritz-reconnect']").first
        reconnect.wait_for(state="visible", timeout=20000)
        self.assertIn(
            "Automatik: an",
            self.page.locator("[data-nv-fritz-status]").first.inner_text() or "")
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
