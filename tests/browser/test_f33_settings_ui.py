"""Browserabnahme F33, WP5: Aktivität und Einstellungen (Nova-Überarbeitung).

Ableitung ausschließlich aus ``docs/features/F33.md`` („Nutzerentscheidungen“
Punkt 4, „Dom-Hook-Vertrag → WP5“) sowie dem Arbeitspaket. Das echte Dashboard
läuft als eigener Prozess mit isoliertem VIBE-Root; offene Rückfragen, das
Laufregister und eine temporäre opencode-Datenbank liegen **vor** dem
Serverstart bereit (Muster ``tests/browser/test_ap22_activity_ui.py`` und
``tests/browser/test_costs_ui.py``).

Testfälle (Kurzfassung; Details in den Methoden)
-----------------------------------------------
``ActivityOrderTest.test_activity_sections_follow_the_contract_order``
    Erwartung: Kacheln → Rückfragen → Läufe → Sessions in genau dieser
    DOM-Reihenfolge.
``ActivityOrderTest.test_question_project_filter_limits_the_cards``
    Aktion: Projekt im Fragenfilter wählen, dann „Alle Projekte“.
    Erwartung: nur die Karten des gewählten Projekts sind sichtbar; „Alle“
    zeigt wieder beide.
``ActivityOrderTest.test_question_and_limit_hints_are_present``
    Erwartung: ``p[data-nv-questions-hint]`` und
    ``small[data-nv-limit-hint]`` sind sichtbar; der Limit-Hinweis nennt das
    gewählte Projekt.
``SettingsStructureTest.test_network_advanced_is_collapsed_and_opens``
    Erwartung: ``details[data-nv-network-advanced]`` ist standardmäßig zu und
    öffnet per Klick; die Portfelder liegen darin.
``SettingsStructureTest.test_feature_groups_live_in_a_responsive_grid``
    Erwartung: ``div[data-nv-feature-groups]`` umschließt die
    Feature-Schalter.
``SettingsStructureTest.test_every_visible_gate_has_a_help_text``
    Vorbedingung: Feature ``gates`` an. Erwartung: je Schranke ein nichtleeres
    ``small[data-nv-gate-help]``.
``EvaluationsGroupTest.test_evaluations_group_has_heading_and_badges``
    Erwartung: eigene Gruppenüberschrift „Auswertungen“; Kosten- und
    Run-Karte tragen ``span[data-nv-eval-badge]``.
``EvaluationsGroupTest.test_cost_rows_are_clickable_and_detail_lists_token_columns``
    Aktion: Projektzeile anklicken. Erwartung: ``nv-clickable``-Zeile öffnet
    ``div[data-nv-cost-detail]`` mit Kennung, Sitzungen, Eingabe (davon
    gecached), Ausgabe und Kosten.
``EvaluationsGroupTest.test_global_prices_editor_posts_and_confirms``
    Aktion: Globalpreis-Editor öffnen, Wert setzen, speichern. Erwartung:
    POST ``action=prices_global`` und Toast „gespeichert“.
``RunRegisterTest.test_pruneable_runs_carry_badge_and_hint``
    Vorbedingung: abgeschlossener Eintrag im Register. Erwartung: Hinweis
    ``p[data-nv-runs-hint]`` und ``span[data-nv-run-pruneable]``.
``AccentTest.test_accent_select_has_twelve_options_and_persists``
    Aktion: Akzent wählen, neu laden. Erwartung: 12 Optionen,
    ``html[data-accent]`` und ``localStorage['nv-accent']`` bleiben gesetzt.
``GlobalAgentsFileTest.test_missing_file_shows_hint_and_create_button``
    Vorbedingung: globale AGENTS.md fehlt. Erwartung: Hinweis auf das Fehlen;
    ``global-agents-create`` sendet ``{action:"create"}`` und der Editor
    erscheint mit der Vorlage.
``GlobalAgentsFileTest.test_existing_file_editor_prefills_and_saves_with_digest``
    Vorbedingung: globale AGENTS.md vorhanden. Erwartung: Editor vorbelegt;
    ``{action:"save", text, digest}`` mit der geladenen Prüfsumme, Toast und
    lokalem Digest-Update (zweites Speichern nutzt den neuen Digest).
``GlobalAgentsFileTest.test_hint_explains_the_scope_of_the_global_file``
    Erwartung: ``small[data-nv-global-agents-hint]`` erklärt „gilt für alle
    Projekte; projektbezogene AGENTS.md ergänzt sie“.

Vertragsunklarheiten (bewusst so geprüft und dokumentiert)
----------------------------------------------------------
1. **Sprache.** Die Fälle laufen wie im Bestand mit ``en``; sichtbare Texte
   stammen daher aus dem en-Wörterbuch. Geprüft werden die im Vertrag
   genannten Hooks und ihre Bedeutung (z. B. „Hinweis nennt das Projekt“),
   nicht ein bestimmter englischer Wortlaut.
2. **Speichern-Knopf des Globalpreis-Editors.** Der Vertrag nennt nur
   ``button[data-nv-action="cost-global-edit"]``, ``input[data-nv-cost-global-model]``
   und den POST. Der Test sucht den Speichern-Knopf im Editor-Umfeld des
   Eingabefelds über seinen Text („speichern“/„save“).
3. **Gruppenüberschrift.** Der Vertrag nennt „Auswertungen“; der Test
   akzeptiert die deutsche oder englische Beschriftung.

ROT-PHASE (2026-11-21, vor der Implementierung von WP5)
------------------------------------------------------
Ausgeführt mit::

    python3 -m unittest discover -s tests/browser \
        -p 'test_f33_settings_ui.py' -v

Ergebnis: 11 Fälle, 11 rot (3 ``AssertionError`` = Verhalten fehlt,
8 ``playwright TimeoutError`` = DOM-Hook fehlt). Kein Fall war grün.

* ``test_activity_sections_follow_the_contract_order`` — AssertionError:
  Ist-Reihenfolge ist Kacheln → Läufe → Sessions → Rückfragen.
* ``test_question_project_filter_limits_the_cards`` — TimeoutError:
  ``select[data-nv-questions-project]`` fehlt.
* ``test_question_and_limit_hints_are_present`` — TimeoutError:
  ``p[data-nv-questions-hint]`` und ``small[data-nv-limit-hint]`` fehlen.
* ``test_network_advanced_is_collapsed_and_opens`` — TimeoutError:
  ``details[data-nv-network-advanced]`` fehlt (Netzwerk ist ein ``div``).
* ``test_feature_groups_live_in_a_responsive_grid`` — TimeoutError:
  ``div[data-nv-feature-groups]`` fehlt.
* ``test_every_visible_gate_has_a_help_text`` — AssertionError: 0 von 5
  ``small[data-nv-gate-help]`` vorhanden.
* ``test_evaluations_group_has_heading_and_badges`` — AssertionError:
  keine Gruppenüberschrift „Auswertungen“, keine ``data-nv-eval-badge``.
* ``test_cost_rows_are_clickable_and_detail_lists_token_columns`` —
  TimeoutError: ``p[data-nv-costs-hint]``/``nv-clickable`` fehlen; die
  Detailtabelle hat keine Eingabe-/gecached-/Ausgabe-Spalten.
* ``test_global_prices_editor_posts_and_confirms`` — TimeoutError:
  ``button[data-nv-action="cost-global-edit"]`` fehlt.
* ``test_pruneable_runs_carry_badge_and_hint`` — TimeoutError:
  ``p[data-nv-runs-hint]``/``span[data-nv-run-pruneable]`` fehlen.
* ``test_accent_select_has_twelve_options_and_persists`` — TimeoutError:
  ``select[data-nv-accent-select]`` fehlt.

ROT-PHASE ``GlobalAgentsFileTest`` (2026-11-21, vor der Implementierung
der globalen AGENTS.md-Sektion)
--------------------------------------------------------------------
Ausgeführt mit::

    PLAYWRIGHT_BROWSERS_PATH=/home/vibe/vibe-logs/playwright-browsers \
        python3 -m unittest -v test_f33_settings_ui.GlobalAgentsFileTest

Gelaufen gegen einen sauberen ``git archive HEAD``-Baum (temporär entpackt),
weil die globale Sektion im Arbeitsbaum von einem parallelen Agenten bereits
implementiert wurde. Der Baseline-Baum enthält den committeten
WP6-Backendstand (``GET /api/global_agents_file``, POST ``create``/``save``),
aber keine Sektion im Frontend — das ist der Stand „vor der
Implementierung“. Die Testdatei ist unverändert die finale Fassung.

Ergebnis: **3 Fälle, 3 rot, 0 grün.** Alle drei scheitern mit
``TimeoutError``, weil die Sektion samt Editor, Anlegen-Knopf und Hinweis
fehlt; kein Umgebungsfehler.

* ``test_missing_file_shows_hint_and_create_button`` — TimeoutError:
  ``div[data-nv-global-agents]`` fehlt (kein Hinweis, kein
  ``global-agents-create``).
* ``test_existing_file_editor_prefills_and_saves_with_digest`` —
  TimeoutError: ``textarea[data-nv-global-agents]`` fehlt.
* ``test_hint_explains_the_scope_of_the_global_file`` — TimeoutError:
  ``small[data-nv-global-agents-hint]`` fehlt.

Hinweis zur Rotphase im laufenden Arbeitsbaum: Während der Testarbeit hat
ein paralleler Agent die Sektion implementiert. Ein Lauf gegen den
Arbeitsbaum zeigte deshalb zwei Fälle grün und zunächst einen echten
Vertragsfehler (der „Datei fehlt“-Hinweis war bei fehlender Datei
ausgeblendet). Dieser Fehler wurde vom parallelen Agenten behoben; die
Rotphase oben wurde deshalb bewusst gegen den unveränderten
``HEAD``-Baseline-Baum ausgeführt und dokumentiert.
"""
import http.client
import json
import os
import re
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

PROJECT = "proj"
OTHER = "zweit"
QUESTION_PROJ = "qaaaaaaaaaaaa"
QUESTION_OTHER = "qbbbbbbbbbbbb"
QUESTION_TEXT_PROJ = "F33-FRAGE-PROJ: Soll die Kostenkarte blau werden?"
QUESTION_TEXT_OTHER = "F33-FRAGE-ZWEIT: Soll die Akzentfarbe grün werden?"
ACCENT_IDS = [
    "blue", "teal", "cyan", "green", "lime", "yellow",
    "amber", "orange", "red", "pink", "violet", "indigo",
]

GLOBAL_AGENTS_TEXT = "GLOBALE-REGEL-4711: gilt für alle Projekte.\n"

# Minimale opencode-Datenbank, damit die Kosten-Detailansicht echte Zeilen hat
# (Struktur wie tests/browser/test_costs_ui.py).
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


class F33SettingsBrowserTest(unittest.TestCase):
    """Dashboard, zwei Projekte, Fragen, Laufregister, Kosten-Datenbank."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.proj = cls.root / PROJECT
        cls.other = cls.root / OTHER
        for project in (cls.proj, cls.other):
            (project / ".vibe").mkdir(parents=True)
            (project / ".vibe" / "project.env").write_text(
                "TYPE=generic\n", encoding="utf-8")
            (project / "FEEDBACK.md").write_text(
                "# FEEDBACK\n\n- [ ] F1 Erster Punkt\n"
                "  Beschreibung: Testpunkt\n", encoding="utf-8")
            (project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True)
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir(parents=True, exist_ok=True)
        cls.questions = cls.log_dir / "questions"
        cls.questions.mkdir(parents=True, exist_ok=True)

        # Kosten: eine Sitzung mit echten Tokens für die Detailtabelle.
        cls.db = cls.root / "opencode.db"
        con = sqlite3.connect(str(cls.db))
        con.executescript(DDL_V2)
        con.execute(
            "insert into session_v2 (id, project_id, slug, directory, title,"
            " version, agent, model, time_created, time_updated)"
            " values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ses_f33", PROJECT, "slug-f33", str(cls.proj), "proj F1",
             "2.1.4", "coding-agent",
             json.dumps({"id": "model-a", "providerID": "opencode"}), 1, 1))
        con.execute(
            "insert into session_message (id, session_id, type, seq,"
            " time_created, time_updated, data) values (?, ?, ?, ?, ?, ?, ?)",
            ("msg_f33", "ses_f33", "assistant", 1, 1, 1, json.dumps({
                "agent": "coding-agent",
                "model": {"id": "model-a", "providerID": "opencode"},
                "tokens": {"input": 400000, "output": 300000,
                           "reasoning": 200000,
                           "cache": {"read": 600000, "write": 0}},
            })))
        con.commit()
        con.close()

        cls.port = free_port()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                    "TMUX", "TMUX_PANE"):
                env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
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

        # Laufregister-Vorlage: ein abgeschlossener Lauf entsteht mit dem
        # echten Registerformat vor dem Serverstart; je Test wird sie erneut
        # nach runs.json geschrieben.
        failed = subprocess.run([
            sys.executable, str(RUNS_PY), "start",
            "--runtime", str(cls.log_dir),
            "--project", str(cls.proj.resolve()),
            "--name", PROJECT, "--key", PROJECT, "--agent", "vibe-agent",
            "--session", "vibe-f33-failed", "--state", "failed",
        ], env=env, capture_output=True, text=True, timeout=30)
        if failed.returncode != 0:
            raise AssertionError(
                "Vorbedingung fehlgeschlagener Lauf fehlgeschlagen: "
                + failed.stdout + failed.stderr)
        runs_path = cls.log_dir / "runs.json"
        cls.failed_runs_text = runs_path.read_text(encoding="utf-8")
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

    @classmethod
    def write_question_file(cls, qid, project, text):
        (cls.questions / f"{qid}.json").write_text(json.dumps({
            "id": qid,
            "project": project,
            "agent": "tester",
            "text": text,
            "options": ["Ja", "Nein"],
            "free_text": True,
            "created": "2026-11-21T10:00:00Z",
        }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    def setUp(self):
        for path in self.questions.iterdir():
            path.unlink()
        self.write_question_file(QUESTION_PROJ, PROJECT, QUESTION_TEXT_PROJ)
        self.write_question_file(QUESTION_OTHER, OTHER, QUESTION_TEXT_OTHER)
        (self.log_dir / "runs.json").unlink(missing_ok=True)
        self.api_post("/api/language", {"language": "en"})
        self.page_errors = []
        self.context = self.browser.new_context(
            viewport={"width": 1400, "height": 1000})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))

    def tearDown(self):
        self.page.close()
        self.context.close()

    # ---------- Helfer ----------

    def wait_until(self, predicate, timeout=25,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def api_post(self, path, payload):
        body = json.dumps(payload).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("POST", path, body=body, headers={
                "Host": f"127.0.0.1:{self.port}",
                "X-Token": self.token,
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{self.port}",
                "Sec-Fetch-Site": "same-origin"})
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def api_get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("GET", path, headers={
                "Host": f"127.0.0.1:{self.port}", "X-Token": self.token})
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def api_json(self, path):
        status, body = self.api_get(path)
        self.assertEqual(200, status, body)
        return json.loads(body)

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_activity(self):
        self.boot()
        self.page.goto(self.base + "/#/activity")
        self.page.locator("main#nv-main[data-nv-view='activity']").wait_for(
            state="visible", timeout=25000)

    def open_settings(self):
        self.boot()
        # Direkt über die Route: unabhängig von doppelten Navigations-
        # Varianten (Desktop/Mobil) und deren Sichtbarkeit.
        self.page.goto(self.base + "/#/settings")
        self.page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=20000)

    def enable_features(self, *ids):
        for feature in ids:
            toggle = self.page.locator(f"input[data-nv-feature='{feature}']")
            toggle.wait_for(state="visible", timeout=20000)
            if not toggle.is_checked():
                toggle.check()
        self.page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=20000)

    def visible_question_ids(self):
        cards = self.page.locator("[data-nv-question]")
        result = []
        for index in range(cards.count()):
            card = cards.nth(index)
            if card.is_visible():
                result.append(card.get_attribute("data-nv-question"))
        return result

    def toast_text(self):
        toasts = self.page.locator("#nv-toasts")
        return (toasts.inner_text() if toasts.count() else "") or ""

    def assert_no_page_errors(self):
        self.assertEqual(
            [], self.page_errors, "Die Oberfläche erzeugte JavaScript-Fehler")


class ActivityOrderTest(F33SettingsBrowserTest):
    def test_activity_sections_follow_the_contract_order(self):
        """Vorbedingung: eine offene Frage je Projekt.

        Erwartung: Die Bereiche stehen in der Reihenfolge Kacheln →
        Rückfragen → Läufe → Sessions; ``[data-nv-questions]`` liegt vor
        ``[data-nv-runs]`` und dieses vor ``[data-nv-sessions]``.
        """
        self.open_activity()
        self.page.locator("[data-nv-question]").first.wait_for(
            state="visible", timeout=20000)
        ordered = self.page.evaluate(
            """() => {
              const selectors = ['[data-nv-activity-tiles]',
                                 '[data-nv-questions]',
                                 '[data-nv-runs]',
                                 '[data-nv-sessions]'];
              const nodes = selectors.map(s => document.querySelector(s));
              if (nodes.some(node => !node)) return null;
              return nodes.every((node, index) => index === 0 ||
                (nodes[index - 1].compareDocumentPosition(node)
                 & Node.DOCUMENT_POSITION_FOLLOWING) !== 0);
            }""")
        self.assertIsNotNone(
            ordered, "Mindestens einer der Bereiche Kacheln/Rückfragen/Läufe/"
                     "Sessions fehlt")
        self.assertTrue(
            ordered, "Die Aktivitätsbereiche stehen nicht in der Reihenfolge "
                     "Kacheln → Rückfragen → Läufe → Sessions")
        self.assert_no_page_errors()

    def test_question_project_filter_limits_the_cards(self):
        """Vorbedingung: je eine offene Frage für ``proj`` und ``zweit``.

        Aktion: Im Filter ``select[data-nv-questions-project]`` das Projekt
        ``zweit`` wählen, dann wieder „Alle Projekte“.
        Erwartung: Die Auswahl bietet „Alle Projekte“ und beide Projekte; nach
        der Wahl ist nur die Karte des Projekts sichtbar, „Alle“ zeigt beide.
        """
        self.open_activity()
        self.page.locator("[data-nv-question]").first.wait_for(
            state="visible", timeout=20000)
        select = self.page.locator("select[data-nv-questions-project]")
        select.wait_for(state="visible", timeout=20000)
        options = select.evaluate(
            "node => Array.from(node.options).map(o => "
            "[o.value, o.textContent.trim()])")
        self.assertTrue(
            re.search(r"alle projekte|all projects", options[0][1], re.I),
            "Die erste Option des Fragenfilters heißt nicht „Alle Projekte“: "
            + repr(options))
        values = [value for value, _text in options]
        for project in (PROJECT, OTHER):
            self.assertIn(project, values,
                          f"Der Fragenfilter bietet das Projekt {project!r} "
                          "nicht an: " + repr(options))

        select.select_option(OTHER)
        self.wait_until(
            lambda: self.visible_question_ids() == [QUESTION_OTHER],
            timeout=20,
            message="Der Fragenfilter zeigt nach der Projektwahl nicht nur "
                    "die Karte des Projekts: "
                    + repr(self.visible_question_ids()))

        select.select_option(options[0][0])
        self.wait_until(
            lambda: set(self.visible_question_ids())
            == {QUESTION_PROJ, QUESTION_OTHER},
            timeout=20,
            message="„Alle Projekte“ zeigt nicht wieder beide Rückfragen: "
                    + repr(self.visible_question_ids()))
        self.assert_no_page_errors()

    def test_question_and_limit_hints_are_present(self):
        """Vorbedingung: Aktivität offen.

        Erwartung: ``p[data-nv-questions-hint]`` ist sichtbar und nicht leer;
        ``small[data-nv-limit-hint]`` ist sichtbar und nennt, dass das Limit
        für das oben gewählte Projekt gilt.
        """
        self.open_activity()
        hint = self.page.locator("p[data-nv-questions-hint]")
        hint.wait_for(state="visible", timeout=20000)
        self.assertTrue((hint.inner_text() or "").strip(),
                        "Der Hinweis zur Rückfragenliste ist leer")
        limit_hint = self.page.locator(
            "[data-nv-sessions] small[data-nv-limit-hint]")
        limit_hint.wait_for(state="visible", timeout=20000)
        text = (limit_hint.inner_text() or "").strip()
        self.assertTrue(text, "Der Session-Limit-Hinweis ist leer")
        self.assertTrue(
            re.search(r"projekt|project", text, re.I),
            "Der Session-Limit-Hinweis nennt das gewählte Projekt nicht: "
            + repr(text))
        self.assert_no_page_errors()


class SettingsStructureTest(F33SettingsBrowserTest):
    def test_network_advanced_is_collapsed_and_opens(self):
        """Vorbedingung: Einstellungen offen.

        Erwartung: ``details[data-nv-network-advanced]`` ist standardmäßig
        geschlossen (``open`` fehlt, Portfeld unsichtbar) und öffnet per
        Klick auf die Zusammenfassung; danach ist das Portfeld sichtbar.
        """
        self.open_settings()
        details = self.page.locator("details[data-nv-network-advanced]")
        details.wait_for(state="visible", timeout=20000)
        self.assertFalse(
            details.evaluate("node => node.open"),
            "Der Netzwerk-Bereich ist standardmäßig aufgeklappt")
        port = details.locator("input[data-nv-field='port']")
        self.assertFalse(
            port.is_visible() if port.count() else False,
            "Das Portfeld ist trotz geschlossenem Netzwerk-Bereich sichtbar")

        details.locator("summary").first.click()
        self.wait_until(
            lambda: details.evaluate("node => node.open"),
            timeout=15, message="Der Netzwerk-Bereich öffnet sich nicht")
        port.wait_for(state="visible", timeout=15000)
        self.assert_no_page_errors()

    def test_feature_groups_live_in_a_responsive_grid(self):
        """Vorbedingung: Einstellungen offen.

        Erwartung: ``div[data-nv-feature-groups]`` umschließt die
        Feature-Schalter (mindestens ein ``input[data-nv-feature]``).
        """
        self.open_settings()
        groups = self.page.locator("div[data-nv-feature-groups]")
        groups.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(
            groups.locator("input[data-nv-feature]").count(), 1,
            "Im Funktionsraster liegt kein Feature-Schalter")
        self.assert_no_page_errors()

    def test_every_visible_gate_has_a_help_text(self):
        """Vorbedingung: Feature ``gates`` wird eingeschaltet.

        Erwartung: Der Schrankenbereich nennt je Schranke aus ``GET
        /api/gates`` eine nichtleere Erklärung ``small[data-nv-gate-help]``.
        """
        self.open_settings()
        gates_view = self.api_json("/api/gates")
        self.assertTrue(gates_view.get("ok"), gates_view)
        keys = list(gates_view["gates"])
        self.enable_features("gates")
        box = self.page.locator("[data-nv-advanced='gates']")
        box.wait_for(state="visible", timeout=20000)
        helps = box.locator("small[data-nv-gate-help]")
        self.wait_until(
            lambda: helps.count() >= len(keys), timeout=20,
            message="Der Schrankenbereich zeigt nicht je Schranke eine "
                    "Erklärung: " + repr(helps.count()) + " von "
                    + repr(len(keys)))
        for index in range(helps.count()):
            text = (helps.nth(index).inner_text() or "").strip()
            with self.subTest(index=index):
                self.assertTrue(text, "Eine Schranken-Erklärung ist leer")
        self.assert_no_page_errors()


class EvaluationsGroupTest(F33SettingsBrowserTest):
    def test_evaluations_group_has_heading_and_badges(self):
        """Vorbedingung: Features ``costs`` und ``runs`` an.

        Erwartung: Eine eigene Gruppenüberschrift „Auswertungen“ steht vor den
        Karten; die Kosten- und die Run-Karte tragen je ein nichtleeres
        ``span[data-nv-eval-badge]``.
        """
        self.open_settings()
        self.enable_features("costs", "runs")
        costs = self.page.locator("[data-nv-advanced='costs']")
        runs = self.page.locator("[data-nv-advanced='runs']")
        costs.wait_for(state="visible", timeout=20000)
        runs.wait_for(state="visible", timeout=20000)

        heading_ok = self.page.evaluate(
            """() => {
              const costs = document.querySelector("[data-nv-advanced='costs']");
              const nodes = Array.from(document.querySelectorAll(
                "main h2, main h3"));
              return nodes.some(node =>
                /auswertungen|evaluations/i.test(node.textContent || '')
                && (node.compareDocumentPosition(costs)
                    & Node.DOCUMENT_POSITION_FOLLOWING) !== 0);
            }""")
        self.assertTrue(
            heading_ok,
            "Es fehlt die eigene Gruppenüberschrift „Auswertungen“ vor den "
            "Auswertungskarten")
        for name, card in (("Kosten", costs), ("Run-Register", runs)):
            badge = card.locator("span[data-nv-eval-badge]")
            with self.subTest(card=name):
                self.assertEqual(
                    1, badge.count(),
                    f"Die {name}-Karte trägt kein span[data-nv-eval-badge]")
                self.assertTrue(
                    (badge.first.inner_text() or "").strip(),
                    f"Das Auswertungs-Badge der {name}-Karte ist leer")
        self.assert_no_page_errors()

    def test_cost_rows_are_clickable_and_detail_lists_token_columns(self):
        """Vorbedingung: Feature ``costs`` an, eine Sitzung in der Datenbank.

        Aktion: Projektzeile ``tr[data-nv-cost-project]`` anklicken.
        Erwartung: ``p[data-nv-costs-hint]`` nennt das Anklicken; die Zeile
        trägt ``nv-clickable``; der Klick öffnet ``div[data-nv-cost-detail]``
        mit Spalten Kennung, Sitzungen, Eingabe (davon gecached), Ausgabe,
        Kosten.
        """
        self.open_settings()
        self.enable_features("costs")
        card = self.page.locator("[data-nv-advanced='costs']")
        card.wait_for(state="visible", timeout=20000)
        hint = card.locator("p[data-nv-costs-hint]")
        hint.wait_for(state="visible", timeout=20000)
        self.assertTrue(
            re.search(r"anklick|click", hint.inner_text() or "", re.I),
            "Der Kosten-Hinweis nennt das Anklicken der Zeile nicht: "
            + repr(hint.inner_text()))

        row = card.locator(f"tr[data-nv-cost-project='{PROJECT}']")
        row.wait_for(state="visible", timeout=20000)
        self.assertIn(
            "nv-clickable", (row.get_attribute("class") or "").split(),
            "Die Projektzeile der Kosten trägt nicht die Klasse nv-clickable")
        row.click()

        detail = card.locator("div[data-nv-cost-detail]")
        detail.wait_for(state="visible", timeout=20000)
        headers = " ".join(detail.locator("th").all_inner_texts())
        for pattern in (r"kennung|arbeitspaket|paket|^id$|package",
                        r"sitzung|session",
                        r"eingabe|input",
                        r"gecach|cach",
                        r"ausgabe|output",
                        r"kosten|cost"):
            with self.subTest(column=pattern):
                self.assertRegex(
                    headers, pattern,
                    "Die Detailtabelle der Kosten nennt die Spalte "
                    f"{pattern!r} nicht: " + repr(headers))
        self.assert_no_page_errors()

    def test_global_prices_editor_posts_and_confirms(self):
        """Vorbedingung: Feature ``costs`` an.

        Aktion: ``button[data-nv-action="cost-global-edit"]`` klicken, einen
        Modellpreis eintragen und speichern.
        Erwartung: Der Editor zeigt ``input[data-nv-cost-global-model]``; der
        Speichern-Klick sendet ``POST /api/costs`` mit ``action=prices_global``
        und die Oberfläche bestätigt mit „gespeichert“.
        """
        self.open_settings()
        self.enable_features("costs")
        card = self.page.locator("[data-nv-advanced='costs']")
        card.wait_for(state="visible", timeout=20000)
        requests = []
        self.page.on(
            "request",
            lambda request: requests.append(request)
            if request.method == "POST" and request.url.endswith("/api/costs")
            else None)

        card.locator("button[data-nv-action='cost-global-edit']").click()
        field = self.page.locator("input[data-nv-cost-global-model]").first
        field.wait_for(state="visible", timeout=20000)
        field.fill("opencode/model-a")
        fields = self.page.locator("[data-nv-cost-field]")
        self.assertGreaterEqual(
            fields.count(), 1,
            "Der Globalpreis-Editor bietet keine Preisfelder "
            "([data-nv-cost-field])")

        editor = self.page.locator(
            "xpath=//input[@data-nv-cost-global-model]/ancestor::*[.//button][1]")
        save = editor.locator("button").filter(
            has_text=re.compile(r"speicher|save", re.I)).first
        self.assertEqual(
            1, save.count(),
            "Im Globalpreis-Editor fehlt ein Speichern-Knopf")
        save.click()
        self.wait_until(
            lambda: re.search(r"gespeichert|saved", self.toast_text(), re.I)
            is not None,
            timeout=20,
            message="Das Speichern der globalen Preise bestätigt nicht: "
                    + repr(self.toast_text()))

        payloads = []
        for request in requests:
            try:
                payloads.append(json.loads(request.post_data or "{}"))
            except ValueError:
                payloads.append({})
        self.assertTrue(
            any(payload.get("action") == "prices_global" for payload in payloads),
            "Der Editor sendet nicht action=prices_global: " + repr(payloads))
        self.assertTrue(
            any("opencode/model-a" in (payload.get("prices") or {})
                for payload in payloads),
            "Der Editor sendet den eingegebenen Modellpreis nicht: "
            + repr(payloads))
        self.assert_no_page_errors()


class RunRegisterTest(F33SettingsBrowserTest):
    def test_pruneable_runs_carry_badge_and_hint(self):
        """Vorbedingung: ein abgeschlossener Lauf (``failed``) im Register.

        Erwartung: Feature ``runs`` an; ``p[data-nv-runs-hint]`` ist sichtbar;
        der Eintrag mit Endzustand trägt ``span[data-nv-run-pruneable]`` mit
        dem Hinweis „bereinigbar“.
        """
        (self.log_dir / "runs.json").write_text(
            self.failed_runs_text, encoding="utf-8")
        self.open_settings()
        self.enable_features("runs")
        card = self.page.locator("[data-nv-advanced='runs']")
        card.wait_for(state="visible", timeout=20000)
        hint = card.locator("p[data-nv-runs-hint]")
        hint.wait_for(state="visible", timeout=20000)
        self.assertTrue((hint.inner_text() or "").strip(),
                        "Der Hinweis zum Run-Register ist leer")
        badge = card.locator("span[data-nv-run-pruneable]")
        self.wait_until(
            lambda: badge.count() >= 1, timeout=20,
            message="Der abgeschlossene Registereintrag trägt kein "
                    "span[data-nv-run-pruneable]")
        self.assertTrue(
            re.search(r"bereinig|prune", badge.first.inner_text() or "", re.I),
            "Das Register-Badge sagt nicht, dass der Eintrag bereinigbar ist: "
            + repr(badge.first.inner_text()))
        self.assert_no_page_errors()


class AccentTest(F33SettingsBrowserTest):
    def test_accent_select_has_twelve_options_and_persists(self):
        """Vorbedingung: Einstellungen offen, Akzent ``blue``.

        Aktion: ``select[data-nv-accent-select]`` auf ``teal`` stellen, Seite
        neu laden.
        Erwartung: genau die 12 Vertrags-Akzente; die Wahl setzt
        ``html[data-accent]`` und ``localStorage['nv-accent']`` und bleibt
        nach dem Reload erhalten.
        """
        self.open_settings()
        select = self.page.locator(
            "[data-nv-ssection='appearance'] select[data-nv-accent-select]")
        select.wait_for(state="visible", timeout=20000)
        values = select.evaluate(
            "node => Array.from(node.options).map(o => o.value)")
        self.assertEqual(
            ACCENT_IDS, values,
            "Die Akzentauswahl bietet nicht die 12 Vertragsfarben: "
            + repr(values))

        select.select_option("teal")
        self.wait_until(
            lambda: self.page.evaluate(
                "() => document.documentElement.getAttribute('data-accent')")
            == "teal",
            timeout=15,
            message="Die Akzentwahl setzt html[data-accent] nicht auf teal")
        self.assertEqual(
            "teal",
            self.page.evaluate("() => localStorage.getItem('nv-accent')"),
            "Die Akzentwahl speichert nicht localStorage['nv-accent']")

        self.page.reload()
        self.page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=25000)
        self.wait_until(
            lambda: self.page.evaluate(
                "() => document.documentElement.getAttribute('data-accent')")
            == "teal",
            timeout=15,
            message="Der Akzent ging beim Reload verloren")
        self.assert_no_page_errors()


class GlobalAgentsFileTest(F33SettingsBrowserTest):
    """Globale AGENTS.md im Einstellungs-Tab (F33 WP5, Koordinator-Entscheidung 6).

    Vorbedingung: Feature ``agentsfile`` an (über ``localStorage['nv-features']``
    vor dem Laden gesetzt, damit die Sektion ohne UI-Klick sichtbar ist). Die
    globale Datei liegt unter ``HOME/.config/opencode/AGENTS.md``; jeder Fall
    legt sie selbst an oder löscht sie, damit die Fälle unabhängig bleiben.
    """

    def setUp(self):
        super().setUp()
        self.global_agents = (
            self.root / "home" / ".config" / "opencode" / "AGENTS.md")
        self.global_agents.parent.mkdir(parents=True, exist_ok=True)
        self.post_requests = []
        self.page.on(
            "request",
            lambda request: self.post_requests.append(request)
            if request.method == "POST" else None)
        # Feature vor dem ersten Laden setzen; open_settings() lädt die Seite
        # danach neu, sodass die Sektion sicher eingeschaltet ist.
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.evaluate(
            "() => localStorage.setItem('nv-features', "
            "JSON.stringify({agentsfile: true}))")

    def posts_to(self, path):
        payloads = []
        for request in self.post_requests:
            if request.url.split("?")[0].endswith(path):
                try:
                    payloads.append(json.loads(request.post_data or "{}"))
                except ValueError:
                    payloads.append({})
        return payloads

    def global_view(self):
        return self.api_json("/api/global_agents_file")

    def section(self):
        # Der Vertrag nennt keine Sektions-ID; die Karte trägt
        # data-nv-global-agents (wie der Editor). Die Sektion wird
        # asynchron nach der Ansicht eingehängt, deshalb wartet der Aufrufer.
        return self.page.locator("div[data-nv-global-agents]")

    def test_missing_file_shows_hint_and_create_button(self):
        """Vorbedingung: globale AGENTS.md existiert nicht.

        Aktion: Einstellungen öffnen, ``button[data-nv-action=
        "global-agents-create"]`` klicken.
        Erwartung: Ein Hinweis nennt die fehlende Datei; der Klick sendet
        ``POST /api/global_agents_file {action:"create"}``; danach erscheint
        ``textarea[data-nv-global-agents]`` mit der angelegten Vorlage.
        """
        self.global_agents.unlink(missing_ok=True)
        self.open_settings()
        section = self.section()
        section.wait_for(state="visible", timeout=20000)
        text = section.inner_text() or ""
        self.assertTrue(
            re.search(r"fehlt|fehlend|nicht vorhanden|missing|not found",
                      text, re.I),
            "Der Hinweis nennt die fehlende globale AGENTS.md nicht: "
            + repr(text))
        create = section.locator(
            "button[data-nv-action='global-agents-create']")
        self.assertEqual(
            1, create.count(),
            "Der Anlegen-Knopf global-agents-create fehlt bei fehlender Datei")
        create.click()
        self.wait_until(
            lambda: any(payload.get("action") == "create"
                        for payload in self.posts_to("/api/global_agents_file")),
            timeout=20,
            message="Es wurde kein /api/global_agents_file-POST mit "
                    "action=create gesendet: "
                    + repr(self.posts_to("/api/global_agents_file")))
        self.wait_until(
            lambda: self.global_agents.is_file(), timeout=20,
            message="Die globale AGENTS.md wurde nicht angelegt")
        editor = self.page.locator("textarea[data-nv-global-agents]")
        editor.wait_for(state="visible", timeout=20000)
        self.assertTrue(
            (editor.input_value() or "").strip(),
            "Der Editor ist nach dem Anlegen nicht mit der Vorlage vorbelegt")
        self.assert_no_page_errors()

    def test_existing_file_editor_prefills_and_saves_with_digest(self):
        """Vorbedingung: globale AGENTS.md mit Text vorhanden.

        Aktion: Text im Editor ändern und speichern.
        Erwartung: ``textarea[data-nv-global-agents]`` ist mit dem aktuellen
        Text vorbelegt; der POST ``{action:"save", text, digest}`` trägt den
        neuen Text und eine Prüfsumme; ein Toast bestätigt; die Datei enthält
        den neuen Text. Ein zweites Speichern nutzt den aktualisierten Digest
        (lokales Digest-Update), nicht die alte Prüfsumme.
        """
        self.global_agents.write_text(GLOBAL_AGENTS_TEXT, encoding="utf-8")
        self.open_settings()
        editor = self.page.locator("textarea[data-nv-global-agents]")
        editor.wait_for(state="visible", timeout=20000)
        self.assertIn(
            "GLOBALE-REGEL-4711", editor.input_value(),
            "Der Editor ist nicht mit dem aktuellen Text der globalen "
            "AGENTS.md vorbelegt")
        initial = self.global_view()
        self.assertTrue(initial.get("exists"),
                        "Vorbedingung: Die globale Datei wird nicht erkannt")
        new_text = GLOBAL_AGENTS_TEXT + "Neue globale Regel 4711.\n"
        editor.fill(new_text)
        save = self.page.locator("button[data-nv-action='global-agents-save']")
        self.assertEqual(1, save.count(),
                         "Der Speichern-Knopf global-agents-save fehlt")
        save.click()
        self.wait_until(
            lambda: any(payload.get("action") == "save"
                        for payload in self.posts_to("/api/global_agents_file")),
            timeout=20,
            message="Es wurde kein /api/global_agents_file-POST mit "
                    "action=save gesendet: "
                    + repr(self.posts_to("/api/global_agents_file")))
        payload = [p for p in self.posts_to("/api/global_agents_file")
                   if p.get("action") == "save"][-1]
        self.assertEqual(new_text, payload.get("text"),
                         "Der POST enthält nicht den eingegebenen Text")
        self.assertEqual(
            initial["digest"], payload.get("digest"),
            "Der POST sendet nicht die geladene Prüfsumme der globalen "
            "AGENTS.md")
        self.wait_until(
            lambda: re.search(r"gespeichert|saved", self.toast_text(), re.I)
            is not None, timeout=20,
            message="Das Speichern der globalen AGENTS.md bestätigt nicht: "
                    + repr(self.toast_text()))
        self.wait_until(
            lambda: "Neue globale Regel 4711"
            in self.global_agents.read_text(encoding="utf-8"),
            timeout=20,
            message="Der neue Text steht nicht in der globalen AGENTS.md")

        # Lokales Digest-Update: der nächste Save darf nicht an einer
        # veralteten Prüfsumme scheitern.
        current = self.global_view()
        self.assertTrue(current.get("digest"),
                        "Nach dem Speichern liefert die API keine Prüfsumme")
        second_text = new_text + "Noch eine Regel 4712.\n"
        editor.fill(second_text)
        save.click()
        self.wait_until(
            lambda: len([p for p in self.posts_to("/api/global_agents_file")
                         if p.get("action") == "save"]) >= 2,
            timeout=20,
            message="Ein zweites Speichern wurde nicht gesendet: "
                    + repr(self.posts_to("/api/global_agents_file")))
        second = [p for p in self.posts_to("/api/global_agents_file")
                  if p.get("action") == "save"][-1]
        self.assertEqual(
            current["digest"], second.get("digest"),
            "Das zweite Speichern nutzt nicht den aktualisierten Digest "
            "(lokales Digest-Update fehlt)")
        self.wait_until(
            lambda: "Noch eine Regel 4712"
            in self.global_agents.read_text(encoding="utf-8"),
            timeout=20,
            message="Das zweite Speichern schreibt den Text nicht")
        self.assert_no_page_errors()

    def test_hint_explains_the_scope_of_the_global_file(self):
        """Vorbedingung: globale AGENTS.md vorhanden.

        Erwartung: ``small[data-nv-global-agents-hint]`` ist sichtbar und
        erklärt, dass die Regeln für alle Projekte gelten und die
        projektbezogene AGENTS.md sie ergänzt.
        """
        self.global_agents.write_text(GLOBAL_AGENTS_TEXT, encoding="utf-8")
        self.open_settings()
        hint = self.page.locator("small[data-nv-global-agents-hint]")
        hint.wait_for(state="visible", timeout=20000)
        text = hint.inner_text() or ""
        self.assertTrue(text.strip(),
                        "Der Hinweis zur globalen AGENTS.md ist leer")
        self.assertTrue(
            re.search(r"alle|all", text, re.I),
            "Der Hinweis sagt nicht, dass die Regeln für alle Projekte "
            "gelten: " + repr(text))
        self.assertTrue(
            re.search(r"projekte|projects?", text, re.I),
            "Der Hinweis nennt die Projekte nicht: " + repr(text))
        self.assertTrue(
            re.search(r"ergänz|supplement|extend|project-specific", text, re.I),
            "Der Hinweis sagt nicht, dass die projektbezogene AGENTS.md die "
            "globalen Regeln ergänzt: " + repr(text))
        self.assert_no_page_errors()


if __name__ == "__main__":
    unittest.main()
