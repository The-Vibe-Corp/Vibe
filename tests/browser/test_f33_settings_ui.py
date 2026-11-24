"""Browserabnahme F34 WP4: Einstellungen (Sektionen, Akzent-Raster, Absences).

Ableitung aus ``docs/features/F34.md`` (WP4 + Leitentscheidungen 2/3/8) und
dem Arbeitspaket F34. Das alte F33-Vertrag (Auswertungen in den Einstellungen,
Advanced-Bereiche, ``select[data-nv-accent]``, Sessions/Limit-Hinweise in der
Aktivität) wird durch die ``F34-Anpassung:``-Abschnitte im Modul-Docstring
abgedeckt: Jeder neu geprüfte oder ersetzte Fall nennt, warum sein neuer
Vertrag gelten wird. Das echte Dashboard läuft als eigener Prozess mit
isoliertem VIBE-Root; offene Rückfragen, das Laufregister und eine temporäre
opencode-Datenbank liegen **vor** dem Serverstart bereit (Muster
``tests/browser/test_ap22_activity_ui.py`` und ``tests/browser/test_costs_ui.py``).

Testfälle (Kurzfassung; Details in den Methoden)
------------------------------------------------
``ActivityOrderTest.test_activity_sections_follow_the_contract_order``
    Erwartung: ``[data-nv-activity-tiles]`` → ``[data-nv-questions]`` →
    ``[data-nv-runs]`` in genau dieser DOM-Reihenfolge; absence:
    ``[data-nv-sessions]``, ``[data-nv-sessions-limit]``, ``[data-nv-limit-hint]``.
``ActivityOrderTest.test_question_project_filter_limits_the_cards``
    Erwartung: Die Auswahl bietet „Alle Projekte“ und beide Projekte; nach
    Auswahl zeigt die Aktivität nur die Karte des Projekts
    (``article[data-nv-question]`` mit ``data-nv-question-id`` in
    ``[data-nv-questions]``), „Alle“ zeigt wieder beide.
``ActivityOrderTest.test_question_and_limit_hints_are_present``
    Erwartung: ``p[data-nv-questions-hint]`` sichtbar und nicht leer;
    ``p[data-nv-activity-sessions-hint]`` sichtbar und verweist auf die
    Projekte (Link ``#/``); ``[data-nv-limit-hint]`` ist entfallen.
``SettingsStructureTest.test_settings_sections_in_contract_order`` (NEW)
    Erwartung: ``section[data-nv-ssection]`` in Vertragsreihenfolge:
    global-agents, appearance, access, features, limits, gates, models,
    profiles, mcp, harness; ``nav[data-nv-settings-nav]`` in der gleichen
    Reihenfolge; absence ``section[data-nv-ssection='language']`` und die
    F33-Sektionen ``[data-nv-advanced='costs'|'runs'|'env']``.
``SettingsStructureTest.test_network_advanced_is_collapsed_and_opens``
    Erwartung: ``details[data-nv-network-advanced]`` liegt in
    ``section[data-nv-ssection='access']``, ist standardmäßig geschlossen
    (``input[data-nv-field='port']`` unsichtbar) und öffnet per Klick auf die
    Zusammenfassung; danach ist das Portfeld sichtbar.
``SettingsStructureTest.test_feature_groups_live_in_a_responsive_grid``
    Erwartung: ``div[data-nv-feature-groups]`` umschließt die Feature-Schalter
    (mindestens ein ``input[data-nv-feature]``).
``SettingsStructureTest.test_every_visible_gate_has_a_help_text``
    Erwartung: Die Sektion ``section[data-nv-ssection='gates']`` ist
    immer sichtbar (vor dem Einschalten keine Tabelle); nach Einschalten
    des Feature-Schalters ``input[data-nv-feature='gates']`` zeigt die
    Tabelle ``table[data-nv-gates-table]`` je Schranke eine Zeile
    ``tr[data-nv-gate]`` mit nichtleerem ``small[data-nv-gate-help]``.
``EvaluationsGroupTest.test_evaluations_absent_from_settings`` (NEW)
    Erwartung: In den Einstellungen sind Kosten/Läufe/Umgebung entfallen:
    absence der Feature-Schalter ``input[data-nv-feature='costs'|'runs'|'env']``
    und der F33-Hooks ``[data-nv-advanced='costs']``, ``p[data-nv-costs-hint]``,
    ``tr[data-nv-cost-project]``, ``div[data-nv-cost-detail]``,
    ``button[data-nv-action='cost-global-edit']``,
    ``input[data-nv-cost-global-model]``, ``[data-nv-advanced='runs']``,
    ``p[data-nv-runs-hint]``, ``span[data-nv-run-pruneable]``,
    ``[data-nv-advanced='env']``.
``EvaluationsGroupTest.test_evaluations_reachable_via_main_nav`` (NEW)
    Erwartung: Der Hauptpunkt ``nav[data-nv-navs] [data-nv-nav='evaluations']``
    führt nach ``main#nv-main[data-nv-view='evaluations']``; die drei Tabs
    ``button[data-nv-etab='costs'|'runs'|'environment']`` zeigen.
``RunRegisterTest.test_run_register_absent_from_settings`` (NEW)
    Erwartung: Das Run-Register ist in den Einstellungen entfallen:
    ``p[data-nv-runs-hint]``, ``span[data-nv-run-pruneable]``,
    ``[data-nv-advanced='runs']``, ``input[data-nv-feature='runs']`` absence.
``AccentTest.test_accent_grid_has_twelve_buttons_without_select``
    Erwartung: ``div[data-nv-accents]`` im Sektion ``appearance`` bietet
    exakt die 12 Vertrags-Akzente; je Knopf ein sichtbarer ``span.nv-swatch``,
    ``aria-pressed`` und übersetzter Name; absence ``select[data-nv-accent]``;
    die Wahl setzt ``html[data-accent]``/``localStorage['nv-accent']`` und
    überlebt das Neuladen.
``GlobalAgentsFileTest.test_missing_file_shows_hint_and_create_button``
``GlobalAgentsFileTest.test_existing_file_editor_prefills_and_saves_with_digest``
``GlobalAgentsFileTest.test_hint_explains_the_scope_of_the_global_file``

F34-Anpassung:

Alte F33-Klassifikation: Die Fälle prüfen den alten Vertrag, in dem
Auswertungen (Kosten/Läufe/Umgebung) in den Einstellungen lagen, es einen
``select[data-nv-accent]`` gab, die Aktivität Sessions und einen
Limit-Hinweis hatte. Die neuen Fälle sind den F34-Hooks
(``docs/features/F34.md``, WP4/WP7) gewidmet; ersetzte Verhaltenserwartungen
werden durch Abwesenheitsprüfungen ergänzt.

1. ``ActivityOrderTest.test_activity_sections_follow_the_contract_order`` —
   F34 WP3: Der Bereichsvergleich prüft jetzt nur ``[data-nv-activity-tiles]``
   → ``[data-nv-questions]`` → ``[data-nv-runs]``; das ehemalige
   Sessions-Bereich ``[data-nv-sessions]``/``[data-nv-sessions-limit]`` und
   der Limit-Hinweis ``[data-nv-limit-hint]`` sind entfallen —
   Abwesenheitsprüfungen.
2. ``ActivityOrderTest.test_question_project_filter_limits_the_cards`` —
   F34 WP3: Die Rückfrage-Karten nutzen die gemeinsame F34-Karte
   ``article[data-nv-question]`` mit ``data-nv-question-id`` im Bereich
   ``[data-nv-questions]`` (nova-widgets.js ``NV.questionCard``); der
   F33-Vertrag hatte die Karten über ``[data-nv-question]`` und den ID-Wert
   angeführt — die Hooks sind vertagt: Aktion und Erwartung nur auf die
   neuen Hooks umgestellt.
3. ``ActivityOrderTest.test_question_and_limit_hints_are_present`` —
   F34: ``p[data-nv-questions-hint]`` bleibt. Der Hinweis
   ``p[data-nv-activity-sessions-hint]`` ist neu/gelockert: er verweist auf
   die Projekte (Link ``#/``); der F33-Hinweis ``[data-nv-limit-hint]`` ist
   entfallen — Abwesenheitsprüfung.
4. ``SettingsStructureTest.test_settings_sections_in_contract_order`` — NEW
   (F34): Vertragsreihenfolge der ``section[data-nv-ssection]``-Sektionen,
   übereinstimmende lokale Navigation (``nav[data-nv-settings-nav]``),
   absence ``section[data-nv-ssection='language']`` und der F33-Sektionen
   ``[data-nv-advanced='costs'|'runs'|'env']``.
5. ``SettingsStructureTest.test_network_advanced_is_collapsed_and_opens`` —
   F34 WP4: ``details[data-nv-network-advanced]`` liegt jetzt in
   ``section[data-nv-ssection='access']``; prüft weiterhin standardmäßig zu
   (Portfeld unsichtbar), öffnet per Klick, danach ist
   ``input[data-nv-field='port']`` sichtbar.
6. ``SettingsStructureTest.test_every_visible_gate_has_a_help_text`` —
   F34: Die Sektion ``section[data-nv-ssection='gates']`` ist immer
   sichtbar (geprüft, auch vor dem Einschalten: Tabelle noch nicht
   vorhanden). Der Inhalt — ``table[data-nv-gates-table]`` mit
   ``tr[data-nv-gate]`` und nichtleerem ``small[data-nv-gate-help]`` —
   kommt bei Einschalten des Feature-Schalters
   ``input[data-nv-feature='gates']``; F34 lässt den Inhalt
   feature-gated (``NV_SETTINGS_FEATURE_GROUPS``, nova-settings.js:137);
   das Einschalten löst via ``nv:featureschange`` → ``render()`` auf die
   Tabelle aus (nova-core.js:564). Die Zeilen-/Hilfetext-Prüfungen bleiben
   unverändert vollständig.
7. ``EvaluationsGroupTest.test_evaluations_absent_from_settings`` — NEW
   (F34 WP3/WP7): Abwesenheitsprüfungen der Feature-Schalter
   ``input[data-nv-feature='costs'|'runs'|'env']`` sowie der F33-Hooks
   ``[data-nv-advanced='costs']``, ``p[data-nv-costs-hint]``,
   ``tr[data-nv-cost-project]``, ``div[data-nv-cost-detail]``,
   ``button[data-nv-action='cost-global-edit']``,
   ``input[data-nv-cost-global-model]``, ``[data-nv-advanced='runs']``,
   ``p[data-nv-runs-hint]``, ``span[data-nv-run-pruneable']``,
   ``[data-nv-advanced='env']`` in den Einstellungen. Die inhaltliche Tiefe
   (Summen, Preislink, Währung) liegt in ``tests/browser/test_f34_activity_evals_ui.py``
   — dort nicht dupliziert.
8. ``EvaluationsGroupTest.test_evaluations_reachable_via_main_nav`` — NEW
   (F34): Verweis-Test: Der Hauptpunkt
   ``nav[data-nv-navs] [data-nv-nav='evaluations']`` führt nach
   ``main#nv-main[data-nv-view='evaluations']``; die drei Tabs
   ``button[data-nv-etab='costs'|'runs'|'environment']`` zeigen.
9. ``RunRegisterTest.test_run_register_absent_from_settings`` — NEW (F34):
   Abwesenheitsprüfungen ``p[data-nv-runs-hint]``,
   ``span[data-nv-run-pruneable']``, ``[data-nv-advanced='runs']``,
   ``input[data-nv-feature='runs']`` in den Einstellungen.
10. ``AccentTest.test_accent_grid_has_twelve_buttons_without_select`` —
    F34: Der Akzent ist ein Raster ``div[data-nv-accents]`` mit je 12
    ``button[data-nv-accent]`` (sichtbarer ``span.nv-swatch``,
    ``aria-pressed``, übersetzter Name); Abwesenheitsprüfung
    ``select[data-nv-accent]``. Die Wahl via ``NV.setAccent`` persistiert
    nach ``localStorage['nv-accent']`` und ``html[data-accent]``; die
    Reload-Prüfung bleibt.
11. ``SettingsStructureTest.test_feature_groups_live_in_a_responsive_grid`` —
    F34: ``div[data-nv-feature-groups]`` bleibt im Einstellungs-Raster.
12. ``GlobalAgentsFileTest.*`` — F34: Die Sektions-Hook ``section()`` an den
    Vertrag (``section[data-nv-ssection='global-agents']`` mit
    ``details[data-nv-global-agents][open]``); Beschriftung, Editor,
    Anlegen-Knopf, Vorlage und Hinweis bleiben unverändert.
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

# Minimale opencode-Datenbank (Struktur wie tests/browser/test_costs_ui.py).
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

    def visible_question_ids(self):
        # F34: Die Rückfrage-Karten sind article[data-nv-question] mit
        # data-nv-question-id innerhalb [data-nv-questions]
        # (nova-widgets.js NV.questionCard).
        cards = self.page.locator(
            "[data-nv-questions] article[data-nv-question]")
        result = []
        for index in range(cards.count()):
            card = cards.nth(index)
            if card.is_visible():
                result.append(card.get_attribute("data-nv-question-id"))
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
        Rückfragen → Läufe: ``[data-nv-activity-tiles]`` liegt vor
        ``[data-nv-questions]`` und dieses vor ``[data-nv-runs]``.
        """
        self.open_activity()
        self.page.locator(
            "[data-nv-questions] article[data-nv-question]").first.wait_for(
            state="visible", timeout=20000)
        ordered = self.page.evaluate(
            """() => {
              const selectors = ['[data-nv-activity-tiles]',
                                 '[data-nv-questions]',
                                 '[data-nv-runs]'];
              const nodes = selectors.map(s => document.querySelector(s));
              if (nodes.some(node => !node)) return null;
              return nodes.every((node, index) => index === 0 ||
                (nodes[index - 1].compareDocumentPosition(node)
                 & Node.DOCUMENT_POSITION_FOLLOWING) !== 0);
            }""")
        self.assertIsNotNone(
            ordered, "Mindestens einer der Bereiche Kacheln/Rückfragen/Läufe fehlt")
        self.assertTrue(
            ordered, "Die Aktivitätsbereiche stehen nicht in der Reihenfolge "
                     "Kacheln → Rückfragen → Läufe")
        self.assertEqual(
            0, self.page.locator("[data-nv-sessions]").count(),
            "Der Sessions-Bereich ist in der Aktivität nicht entfernt")
        self.assertEqual(
            0, self.page.locator("[data-nv-sessions-limit]").count(),
            "Der Sessions-Limit-Bereich ist in der Aktivität nicht entfernt")
        self.assertEqual(
            0, self.page.locator("[data-nv-limit-hint]").count(),
            "Der Limit-Hinweis ist in der Aktivität nicht entfernt")
        self.assert_no_page_errors()

    def test_question_project_filter_limits_the_cards(self):
        """Vorbedingung: je eine offene Frage für ``proj`` und ``zweit``.

        Aktion: Im Filter ``select[data-nv-questions-project]`` das Projekt
        ``zweit`` wählen, dann wieder „Alle Projekte“.
        Erwartung: Die Auswahl bietet „Alle Projekte“ und beide Projekte;
        nach der Wahl ist nur die Karte des Projekts sichtbar, „Alle“
        zeigt beide.
        """
        self.open_activity()
        self.page.locator(
            "[data-nv-questions] article[data-nv-question]").first.wait_for(
            state="visible", timeout=20000)
        self.wait_until(
            lambda: len(self.visible_question_ids()) == 2, timeout=20,
            message="Beide offenen Rückfragen sind in der Aktivität "
                    "sichtbar: " + repr(self.visible_question_ids()))
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

        select.select_option(index=0)
        self.wait_until(
            lambda: set(self.visible_question_ids())
            == {QUESTION_PROJ, QUESTION_OTHER},
            timeout=20,
            message="„Alle Projekte“ zeigt nicht wieder beide Rückfragen: "
                    + repr(self.visible_question_ids()))
        self.assert_no_page_errors()

    def test_question_and_limit_hints_are_present(self):
        """Vorbedingung: Aktivität offen.

        Erwartung: ``p[data-nv-questions-hint]`` ist sichtbar und nicht
        leer; ``p[data-nv-activity-sessions-hint]`` ist sichtbar und
        verweist auf die Projekte (Linkziel ``#/``). F34:
        ``[data-nv-limit-hint]`` ist entfallen.
        """
        self.open_activity()
        hint = self.page.locator("p[data-nv-questions-hint]")
        hint.wait_for(state="visible", timeout=20000)
        self.assertTrue((hint.inner_text() or "").strip(),
                        "Der Hinweis zur Rückfragenliste ist leer")
        sessions_hint = self.page.locator("p[data-nv-activity-sessions-hint]")
        sessions_hint.wait_for(state="visible", timeout=20000)
        text = (sessions_hint.inner_text() or "").strip()
        self.assertTrue(
            re.search(r"projekt|project", text, re.I),
            "Der Sitzungs-Hinweis nennt die Projekte nicht: " + repr(text))
        link = sessions_hint.locator("a").first
        self.assertEqual(
            1, link.count(), "Der Sitzungs-Hinweis verweist auf kein Ziel")
        self.assertTrue(
            (link.get_attribute("href") or "").startswith("#/"),
            "Der Link des Sitzungs-Hinweises zielt nicht auf die Projekte: "
            + repr(link.get_attribute("href")))
        self.assertEqual(
            0, self.page.locator("[data-nv-limit-hint]").count(),
            "Der Session-Limit-Hinweis ist in der Aktivität nicht entfernt")
        self.assert_no_page_errors()


class SettingsStructureTest(F33SettingsBrowserTest):
    SETTINGS_SECTIONS = [
        "global-agents", "appearance", "access", "features", "limits",
        "gates", "models", "profiles", "mcp", "harness"]

    def test_settings_sections_in_contract_order(self):
        """Vorbedingung: Einstellungen offen.

        Erwartung: Die Sektionen ``section[data-nv-ssection]`` stehen in
        Vertragsreihenfolge (global-agents, appearance, access, features,
        limits, gates, models, profiles, mcp, harness); die lokale Navigation
        ``nav[data-nv-settings-nav]`` in der gleichen Reihenfolge. Absence:
        ``section[data-nv-ssection='language']`` und die F33-Sektionen
        ``[data-nv-advanced='costs'|'runs'|'env']``.
        """
        self.open_settings()
        ids = self.page.evaluate(
            "() => Array.from(document.querySelectorAll("
            "'section[data-nv-ssection]')).map(n => "
            "n.getAttribute('data-nv-ssection'))")
        self.assertEqual(
            self.SETTINGS_SECTIONS, ids,
            "Die Sektionen stehen nicht in Vertragsreihenfolge: " + repr(ids))
        links = self.page.evaluate(
            "() => Array.from(document.querySelectorAll("
            "'nav[data-nv-settings-nav] button[data-nv-ssection-link]')).map("
            "n => n.getAttribute('data-nv-ssection-link'))")
        self.assertEqual(
            self.SETTINGS_SECTIONS, links,
            "Die lokale Navigation steht nicht in Vertragsreihenfolge: "
            + repr(links))
        for hook in ("section[data-nv-ssection='language']",
                     "[data-nv-advanced='costs']", "[data-nv-advanced='runs']",
                     "[data-nv-advanced='env']"):
            self.assertEqual(
                0, self.page.locator(hook).count(),
                f"{hook} existiert in den Einstellungen, ist in F34 aber "
                "entfernt")
        self.assert_no_page_errors()

    def test_network_advanced_is_collapsed_and_opens(self):
        """Vorbedingung: Einstellungen offen.

        Erwartung: ``details[data-nv-network-advanced]`` liegt in
        ``section[data-nv-ssection='access']``, ist standardmäßig
        geschlossen (Portfeld ``input[data-nv-field='port']`` unsichtbar)
        und öffnet per Klick auf die Zusammenfassung; danach ist das
        Portfeld sichtbar.
        """
        self.open_settings()
        access = self.page.locator("section[data-nv-ssection='access']")
        access.wait_for(state="visible", timeout=20000)
        details = access.locator("details[data-nv-network-advanced]")
        self.assertEqual(
            1, details.count(),
            "Der Netzwerk-Bereich liegt nicht in der Sektion access")
        details.wait_for(state="visible", timeout=20000)
        self.assertFalse(
            details.evaluate("node => node.open"),
            "Der Netzwerk-Bereich ist standardmäßig aufgeklappt")
        port = details.locator("input[data-nv-field='port']")
        self.assertEqual(
            1, port.count(), "Das Portfeld fehlt im Netzwerk-Bereich")
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
        """Vorbedingung: Schranken sind geliefert (GET /api/gates).

        Erwartung: Die Sektion ``section[data-nv-ssection='gates']`` ist
        immer sichtbar (vor dem Einschalten noch ohne Tabelle); nach
        Einschalten des Feature-Schalters ``input[data-nv-feature='gates']``
        zeigt die Tabelle ``table[data-nv-gates-table]`` je Schranke eine
        Zeile ``tr[data-nv-gate]`` mit nichtleerem
        ``small[data-nv-gate-help]``.
        """
        self.open_settings()
        section = self.page.locator("section[data-nv-ssection='gates']")
        section.wait_for(state="visible", timeout=20000)
        # Vertrag: die Sektion ist immer vorhanden; die Tabelle kommt
        # erst mit dem Funktionsschalter gates (nova-settings.js:137).
        self.assertEqual(
            0, section.locator("table[data-nv-gates-table]").count(),
            "Vor dem Einschalten muss die Gates-Tabelle noch nicht liegen")
        toggle = self.page.locator("input[data-nv-feature='gates']")
        toggle.wait_for(state="visible", timeout=20000)
        if not toggle.is_checked():
            toggle.check()
        table = section.locator("table[data-nv-gates-table]")
        table.wait_for(state="visible", timeout=20000)
        gates_view = self.api_json("/api/gates")
        self.assertTrue(gates_view.get("ok"), gates_view)
        keys = list(gates_view["gates"])
        rows = table.locator("tr[data-nv-gate]")
        self.wait_until(
            lambda: rows.count() == len(keys), timeout=20,
            message="Der Schrankenbereich zeigt nicht je Schranke eine "
                    "Zeile: " + repr(rows.count()) + " von " + repr(len(keys)))
        for index in range(rows.count()):
            row = rows.nth(index)
            help_text = row.locator("small[data-nv-gate-help]")
            with self.subTest(gate=row.get_attribute("data-nv-gate")):
                self.assertEqual(
                    1, help_text.count(),
                    "Die Schranke trägt kein small[data-nv-gate-help]")
                self.assertTrue(
                    (help_text.first.inner_text() or "").strip(),
                    "Ein Schranken-Hinweis ist leer")
        self.assert_no_page_errors()


class EvaluationsGroupTest(F33SettingsBrowserTest):
    def test_evaluations_absent_from_settings(self):
        """Vorbedingung: Einstellungen offen, Datenbank mit einer Sitzung.

        Erwartung: In den Einstellungen sind die Auswertungen (Kosten,
        Läufe, Umgebung) entfallen: absence der Feature-Schalter
        ``input[data-nv-feature='costs'|'runs'|'env']`` sowie der F33-Hooks
        ``[data-nv-advanced='costs']``, ``p[data-nv-costs-hint]``,
        ``tr[data-nv-cost-project]``, ``div[data-nv-cost-detail]``,
        ``button[data-nv-action='cost-global-edit']``,
        ``input[data-nv-cost-global-model]``, ``[data-nv-advanced='runs']``,
        ``p[data-nv-runs-hint]``, ``span[data-nv-run-pruneable']``,
        ``[data-nv-advanced='env']`` in den Einstellungen.
        """
        self.open_settings()
        settings = self.page.locator("main#nv-main[data-nv-view='settings']")
        settings.wait_for(state="visible", timeout=20000)
        for feature in ("costs", "runs", "env"):
            self.assertEqual(
                0, settings.locator(
                    f"input[data-nv-feature='{feature}']").count(),
                f"Es gibt den Feature-Schalter {feature!r} noch in den "
                "Einstellungen")
        for hook in (
                "[data-nv-advanced='costs']", "p[data-nv-costs-hint]",
                "tr[data-nv-cost-project]", "div[data-nv-cost-detail]",
                "button[data-nv-action='cost-global-edit']",
                "input[data-nv-cost-global-model]", "[data-nv-advanced='runs']",
                "p[data-nv-runs-hint]", "span[data-nv-run-pruneable]",
                "[data-nv-advanced='env']"):
            with self.subTest(hook=hook):
                self.assertEqual(
                    0, settings.locator(hook).count(),
                    f"{hook} existiert in den Einstellungen, ist in F34 "
                    "aber entfernt")
        self.assert_no_page_errors()

    def test_evaluations_reachable_via_main_nav(self):
        """Vorbedingung: Einstellungen sind zugänglich.

        Aktion: Über den Hauptpunkt
        ``nav[data-nv-navs] [data-nv-nav='evaluations']`` in die
        Auswertungen gehen.

        Erwartung: ``main#nv-main[data-nv-view='evaluations']`` ist
        sichtbar; die drei Tabs ``button[data-nv-etab='costs']``,
        ``button[data-nv-etab='runs']`` und
        ``button[data-nv-etab='environment']`` zeigen.
        """
        self.boot()
        nav = self.page.locator("nav[data-nv-navs] [data-nv-nav='evaluations']")
        nav.wait_for(state="visible", timeout=20000)
        nav.click()
        self.page.locator("main#nv-main[data-nv-view='evaluations']").wait_for(
            state="visible", timeout=25000)
        for name in ("costs", "runs", "environment"):
            tab = self.page.locator(f"button[data-nv-etab='{name}']")
            self.assertEqual(
                1, tab.count(),
                f"Der Tab {name!r} ist in den Auswertungen nicht da")
            tab.wait_for(state="visible", timeout=20000)
        self.assert_no_page_errors()


class RunRegisterTest(F33SettingsBrowserTest):
    def test_run_register_absent_from_settings(self):
        """Vorbedingung: ein abgeschlossener Lauf (``failed``) im Register.

        Erwartung: Das Run-Register ist in den Einstellungen entfallen:
        ``p[data-nv-runs-hint]``, ``span[data-nv-run-pruneable]``,
        ``[data-nv-advanced='runs']`` und ``input[data-nv-feature='runs']``
        sind in den Einstellungen abwesent.
        """
        (self.log_dir / "runs.json").write_text(
            self.failed_runs_text, encoding="utf-8")
        self.open_settings()
        for hook in ("p[data-nv-runs-hint]", "span[data-nv-run-pruneable]",
                     "[data-nv-advanced='runs']",
                     "input[data-nv-feature='runs']"):
            self.assertEqual(
                0, self.page.locator(hook).count(),
                f"{hook} existiert in den Einstellungen, ist in F34 aber "
                "entfernt")
        self.assert_no_page_errors()


class AccentTest(F33SettingsBrowserTest):
    def test_accent_grid_has_twelve_buttons_without_select(self):
        """Vorbedingung: Einstellungen offen, Sprache ``en``.

        Erwartung: ``div[data-nv-accents]`` im Sektion ``appearance``
        bietet exakt die 12 Vertrags-Akzente; je Knopf ein sichtbarer
        ``span.nv-swatch``, ein ``aria-pressed`` und ein übersetzter Name;
        absence ``select[data-nv-accent]``. Die Wahl setzt
        ``html[data-accent]`` und ``localStorage['nv-accent']`` und überlebt
        das Neuladen.
        """
        self.open_settings()
        grid = self.page.locator(
            "[data-nv-ssection='appearance'] div[data-nv-accents]")
        grid.wait_for(state="visible", timeout=20000)
        buttons = grid.locator("button[data-nv-accent]")
        self.assertEqual(12, buttons.count())
        values = self.page.evaluate(
            "() => Array.from(document.querySelectorAll("
            "'div[data-nv-accents] button[data-nv-accent]'))"
            ".map(n => n.getAttribute('data-nv-accent'))")
        self.assertEqual(
            ACCENT_IDS, values,
            "Das Akzent-Raster bietet nicht die 12 Vertragsfarben: "
            + repr(values))
        for index in range(buttons.count()):
            button = buttons.nth(index)
            with self.subTest(accent=values[index]):
                self.assertTrue(button.is_visible())
                self.assertIsNotNone(
                    button.get_attribute("aria-pressed"),
                    "Der Akzent-Knopf trägt kein aria-pressed")
                self.assertTrue(
                    button.locator("span.nv-swatch").is_visible(),
                    "Der Akzent-Knopf trägt keinen sichtbaren span.nv-swatch")
                self.assertTrue(
                    (button.inner_text() or "").strip(),
                    "Der Akzent-Knopf trägt keinen übersetzten Namen")
        self.assertEqual(
            0, self.page.locator("select[data-nv-accent]").count(),
            "Es gibt ein select[data-nv-accent], ist aber in F34 entfernt")

        teal = buttons.nth(ACCENT_IDS.index("teal"))
        teal.click()
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
        self.assertEqual(
            "true", teal.get_attribute("aria-pressed"),
            "Der gewählte Akzent-Knopf ist nicht aria-pressed gesetzt")

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

    Vorbedingung: Die globale Datei liegt unter ``HOME/.config/opencode/AGENTS.md``;
    jeder Fall legt sie selbst an oder löscht sie, damit die Fälle
    unabhängig bleiben. Der Editor erfolgt unter
    ``section[data-nv-ssection='global-agents']`` (GH-57-Vertrag: flache
    Sektion, Editor in ``NV.editView`` mit ``textarea[data-nv-agents-text]``).
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
        # Vor dem ersten Laden der Editor-State setzen, sodass die Sektion
        # sicher eingeschaltet ist.
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
        # GH-57-Vertrag: flache Sektion global-agents ohne details.
        return self.page.locator(
            "section[data-nv-ssection='global-agents']")

    def open_global_agents_editor(self):
        """Öffnet den gemeinsamen Editor über den Bearbeiten-Knopf (GH-57)."""
        section = self.section()
        section.wait_for(state="visible", timeout=20000)
        edit = section.locator(
            "button[data-nv-action='global-agents-edit']")
        edit.wait_for(state="visible", timeout=20000)
        edit.click()
        editor = self.page.locator(
            "aside[data-nv-editview] textarea[data-nv-agents-text]")
        editor.wait_for(state="visible", timeout=20000)
        return editor

    def test_missing_file_shows_hint_and_create_button(self):
        """Vorbedingung: globale AGENTS.md existiert nicht.

        Aktion: Einstellungen öffnen, ``button[data-nv-action=
        "global-agents-create"]`` klicken.
        Erwartung: Ein Hinweis nennt die fehlende Datei; der Klick sendet
        ``POST /api/global_agents_file {action:"create"}``; danach erscheint
        ``textarea[data-nv-agents-text]`` in der Edit-View mit der
        angelegten Vorlage.
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
        editor = self.page.locator(
            "aside[data-nv-editview] textarea[data-nv-agents-text]")
        editor.wait_for(state="visible", timeout=20000)
        self.assertTrue(
            (editor.input_value() or "").strip(),
            "Der Editor ist nach dem Anlegen nicht mit der Vorlage vorbelegt")
        self.assert_no_page_errors()

    def test_existing_file_editor_prefills_and_saves_with_digest(self):
        """Vorbedingung: globale AGENTS.md mit Text vorhanden.

        Aktion: Text im Editor ändern und speichern.
        Erwartung: ``textarea[data-nv-agents-text]`` ist mit dem aktuellen
        Text vorbelegt; der POST ``{action:"save", text, digest}`` trägt den
        neuen Text und eine Prüfsumme; ein Toast bestätigt; die Datei enthält
        den neuen Text. Ein zweites Speichern nutzt den aktualisierten Digest
        (lokales Digest-Update), nicht die alte Prüfsumme.
        """
        self.global_agents.write_text(GLOBAL_AGENTS_TEXT, encoding="utf-8")
        self.open_settings()
        editor = self.open_global_agents_editor()
        self.assertIn(
            "GLOBALE-REGEL-4711", editor.input_value(),
            "Der Editor ist nicht mit dem aktuellen Text der globalen "
            "AGENTS.md vorbelegt")
        initial = self.global_view()
        self.assertTrue(initial.get("exists"),
                        "Vorbedingung: Die globale Datei wird nicht erkannt")
        new_text = GLOBAL_AGENTS_TEXT + "Neue globale Regel 4711.\n"
        editor.fill(new_text)
        save = self.page.locator(
            "aside[data-nv-editview] button[data-nv-action='agents-save']")
        self.assertEqual(1, save.count(),
                         "Der Speichern-Knopf agents-save fehlt")
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

        Erwartung: ``[data-nv-global-agents-hint]`` ist sichtbar und
        erklärt, dass die Regeln für alle Projekte gelten und die
        projektbezogene AGENTS.md sie ergänzt. (GH-57: Hook ohne Element-
        Typ-Vorgabe, Text-Assertionen unverändert.)
        """
        self.global_agents.write_text(GLOBAL_AGENTS_TEXT, encoding="utf-8")
        self.open_settings()
        hint = self.page.locator("[data-nv-global-agents-hint]")
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
