"""Browserabnahme F33, WP3: Projektdetail (Overview, Arbeit, Beschreibung,
Einstellungen).

Ableitung ausschließlich aus ``docs/features/F33.md`` — Abschnitt
„Dom-Hook-Vertrag → WP3 — Projektdetail (2n, 2o, 2q, 2r)“ sowie den
Nutzerentscheidungen. Geprüft werden die dort verbindlich vereinbarten
``data-nv-*``-Hooks, ihre Reihenfolge und ihr beobachtbares Verhalten
(Filterung, Persistenz, POST-Nutzlasten). Sichtbare Texte werden nur dort
fest verdrahtet, wo der Vertrag sie ausdrücklich nennt; sonst genügt ein
deutscher oder englischer Treffer, weil die Fälle wie im Bestand mit
``en`` laufen.

Das echte Dashboard läuft als eigener Prozess auf einem freien
Loopback-Port mit isoliertem ``VIBE``/``HOME`` und einer opencode-Attrappe
(Muster ``tests/browser/test_ap22_project_ui.py`` und
``tests/browser/test_f33_agents_ui.py``). Die Features ``priority``,
``github`` und ``agentsfile`` sind über ``localStorage['nv-features']``
eingeschaltet. Es gibt keine Modellaufrufe und keinen Netzzugriff außerhalb
von Loopback.

Fachlicher Rahmen
-----------------
* **Overview (2n):** Der Leitfaden-Link unter den Sitzungen entfällt; der
  autonome Modus wandert als ``div[data-nv-autonomous-row]`` in den
  Überblick; die Pause erscheint als Pille ``span[data-nv-pause-badge]``
  (``nv-warn``) nur bei aktiver Pause, geschaltet über
  ``[data-nv-action="pause"]``.
* **Arbeit (2o):** Reihenfolge Aktionsleiste → Suche/Filter →
  Priorisierungsleiste → Board → Feedback; Live-Suche
  ``input[data-nv-work-search]``; ``button[data-nv-work-hide-done]`` mit
  ``aria-pressed``; begrenzte Beschreibung mit ``button[data-nv-ticket-more]``;
  sichtbare ``nv-secondary``/``nv-danger``-Knöpfe; Feedback bearbeiten über
  ``POST /api/feedback {action:"update"}``; zusammengeklappte
  ``details[data-nv-feedback-box]``; Formular direkt unter der Aktionsleiste;
  Kennungsvorschlag ``F<n>+1``/``B<n>+1`` samt Hinweis.
* **Priorisierung (2o):** ``div[data-nv-priority-strip]`` oberhalb des
  Boards, Drag-Griff ``button[data-nv-drag-handle]`` (Drop speichert
  ``POST /api/priority {action:"set"}`), ↑/↓-Knöpfe,
  ``button[data-nv-priority-reset]`` (``order:""``), Badges
  ``span[data-nv-prio-badge]`` „P1“… und Zähler „{{n}} priorisiert“.
* **Beschreibung (2q):** Tab-Label „Beschreibung“, kein ``data-nv-note``,
  Status ``span[data-nv-step-status]`` (``nv-ok``/``nv-warn`` mit ``title``),
  „Mit Agent entwerfen“ als ``nv-secondary``, „Antwort speichern“ ohne
  Voll-Neurender.
* **Einstellungen (2r):** AGENTS.md als erste Sektion
  (``textarea[data-nv-agents-before]``, readonly ``pre[data-nv-agents-managed]``,
  ``textarea[data-nv-agents-after]``, Speichern mit ``before``/``after``/
  ``digest``), globale AGENTS.md als readonly ``details``, Sicherung und
  Wiederherstellung mit Inline-Bestätigung, GitHub-Erklärungen, MR-Block über
  dem Issue-Block, Auto-Merge als ``label.nv-switch-row``, Modellwahl als
  Combobox, keine eigene Pause-Sektion.

Testfälle (Kurzfassung; Details in den Methoden)
-----------------------------------------------
``OverviewTest.test_sessions_card_has_no_guide_link``
``OverviewTest.test_autonomous_row_lives_in_the_overview``
``OverviewTest.test_pause_badge_only_shows_for_an_active_pause``
``WorkOrderTest.test_work_tab_follows_the_contract_order``
``WorkOrderTest.test_work_search_filters_ticket_and_feedback_cards_live``
``WorkOrderTest.test_hide_done_toggle_hides_and_shows_done_cards``
``WorkOrderTest.test_long_ticket_description_is_clamped_and_expandable``
``WorkOrderTest.test_ticket_actions_are_visible_secondary_and_danger_buttons``
``WorkOrderTest.test_feedback_box_starts_collapsed_with_edit_and_delete``
``WorkOrderTest.test_feedback_edit_posts_update``
``WorkOrderTest.test_feedback_delete_posts_delete``
``WorkOrderTest.test_form_opens_directly_under_the_action_bar``
``WorkOrderTest.test_id_field_has_placeholder_hint_and_suggestion``
``PriorityTest.test_strip_sits_above_the_board_with_badges_and_count``
``PriorityTest.test_drag_and_drop_saves_the_order``
``PriorityTest.test_arrow_buttons_reorder_and_save``
``PriorityTest.test_reset_clears_the_order``
``DescriptionTest.test_tab_is_labelled_description_without_note_field``
``DescriptionTest.test_step_status_reports_filled_and_open_steps``
``DescriptionTest.test_draft_button_is_secondary``
``DescriptionTest.test_answer_save_updates_status_without_rerender``
``SettingsTabTest.test_agents_file_is_the_first_section_with_split_editor``
``SettingsTabTest.test_agents_file_save_posts_before_after_and_digest``
``SettingsTabTest.test_global_agents_hint_is_readonly``
``SettingsTabTest.test_agents_file_backup_and_restore_controls``
``SettingsTabTest.test_github_explains_branches_and_puts_mr_above_issues``
``SettingsTabTest.test_auto_merge_is_a_switch_row``
``SettingsTabTest.test_team_model_is_a_combobox``
``SettingsTabTest.test_there_is_no_own_pause_section``

Vertragsunklarheiten (bewusst so geprüft und dokumentiert)
---------------------------------------------------------
1. **Tab-Hook der Beschreibung.** Der Vertrag ändert nur das *Label*; der
   bestehende Hook ``data-nv-ptab="assistant"`` bleibt (AP22 prüft ihn).
   Geprüft wird daher das Label dieses Tabs, nicht ein neuer Hook.
2. **Kennungsvorschlag.** „F<n>+1“/„B<n>+1“ wird als höchste vorhandene
   Nummer + 1 gelesen. Die Fixture enthält F1–F4 und B7; erwartet werden
   exakt ``F5`` bzw. ``B8``. „löschbar“ heißt: das Feld bleibt editierbar
   und leerbar.
3. **Drag&Drop-Reihenfolge.** Der Vertrag nennt das Ziel der Einfügung
   nicht. Geprüft wird: Der Drop löst ``POST /api/priority {action:"set"}``
   mit einer Permutation der beiden Kennungen aus, die von der Ausgangsfolge
   abweicht, und die neue Folge ist über ``GET /api/priority`` persistiert.
4. **↑/↓-Knöpfe.** Sie sind „Alternativbedienung“ zum automatisch
   speichernden Drop; der Test erwartet daher ebenfalls einen
   ``action:"set"``-POST und die verschobene Reihenfolge.
5. **Formularposition.** „Direkt unter der Aktionsleiste“ wird als
   „im oberen Bereich, vor dem Board und ohne Scrollen sichtbar“ gelesen —
   nicht als unmittelbarer Geschwisterknoten, weil Suche/Filter laut
   Reihenfolge dazwischen liegen.
6. **Feedback-Zähler.** „Feedback ({{n}} offen)“ zählt die offenen
   Feedback-Einträge; die Fixture hat zwei offene (B7, FB-1), erwartet
   wird die Ziffer 2 in der Summary.
7. **AGENTS.md-Speichern.** Der Vertrag nennt keinen Knopf-Hook; geprüft
   wird der bestehende ``button[data-nv-action="agents-file-save"]``.
8. **Globale AGENTS.md.** Der readonly-``pre`` liegt in
   ``details[data-nv-global-agents-hint]``; geprüft wird der Inhalt aus
   ``GET /api/global_agents_file`` (Fixture ``GLOBALE-REGEL-4711``).

ROT-PHASE (2026-11-21, vor der Implementierung von WP3)
------------------------------------------------------
Ausgeführt mit::

    PLAYWRIGHT_BROWSERS_PATH=/home/vibe/vibe-logs/playwright-browsers \
        python3 -m unittest discover -s tests/browser \
        -p 'test_f33_project_ui.py' -v

Gelaufen gegen einen sauberen ``git archive HEAD``-Baum (temporär entpackt),
weil im Arbeitsbaum bereits Teile von WP3/WP4/WP5 parallel implementiert
wurden. Der Baseline-Baum enthält den committeten WP6-Backendstand, aber
keine WP3-Oberflächenänderungen — das ist der Stand „vor der
Implementierung“. Die Testdatei ist unverändert die finale Fassung.

Ergebnis: **29 Fälle, 29 rot, 0 grün.** Kein Fall scheiterte aus
Umgebungsgründen (Server, Port, Browser, Syntax); alle Fehler sind
fehlende Hooks (``TimeoutError``) oder fehlendes Verhalten
(``AssertionError``).

``OverviewTest`` (3/3 rot)
* ``test_sessions_card_has_no_guide_link`` — AssertionError: Der Überblick
  zeigt weiterhin ``Guide →`` unter den Sitzungen.
* ``test_autonomous_row_lives_in_the_overview`` — TimeoutError:
  ``div[data-nv-autonomous-row]`` fehlt (die Autonom-Zeile liegt im
  Assistenten).
* ``test_pause_badge_only_shows_for_an_active_pause`` — AssertionError:
  Nach „Pause anfordern“ erscheint keine ``span[data-nv-pause-badge]``.

``WorkOrderTest`` (10/10 rot)
* ``test_work_tab_follows_the_contract_order`` — AssertionError: Suche,
  Priorisierungsleiste und Feedback-Box fehlen als eigene Bereiche.
* ``test_work_search_filters_ticket_and_feedback_cards_live`` —
  TimeoutError: ``input[data-nv-work-search]`` fehlt.
* ``test_hide_done_toggle_hides_and_shows_done_cards`` — TimeoutError:
  ``button[data-nv-work-hide-done]`` fehlt.
* ``test_long_ticket_description_is_clamped_and_expandable`` —
  AssertionError: ``button[data-nv-ticket-more]`` fehlt.
* ``test_ticket_actions_are_visible_secondary_and_danger_buttons`` —
  AssertionError: Bearbeiten ist ``nv-ghost`` statt ``nv-secondary``.
* ``test_feedback_box_starts_collapsed_with_edit_and_delete`` —
  TimeoutError: ``details[data-nv-feedback-box]`` fehlt.
* ``test_feedback_edit_posts_update`` — TimeoutError: kein
  Feedback-Bearbeiten-Formular.
* ``test_feedback_delete_posts_delete`` — TimeoutError: kein
  Feedback-Löschen-Knopf.
* ``test_form_opens_directly_under_the_action_bar`` — AssertionError: Das
  Formular steht hinter dem Board statt darüber.
* ``test_id_field_has_placeholder_hint_and_suggestion`` — AssertionError:
  Platzhalter und ``small[data-nv-id-hint]`` fehlen; keine Vorbelegung.

``PriorityTest`` (4/4 rot)
* ``test_strip_sits_above_the_board_with_badges_and_count`` —
  TimeoutError: ``div[data-nv-priority-strip]`` fehlt.
* ``test_drag_and_drop_saves_the_order`` — TimeoutError: kein
  ``button[data-nv-drag-handle]``.
* ``test_arrow_buttons_reorder_and_save`` — TimeoutError: keine
  ``priority-down``-Knöpfe.
* ``test_reset_clears_the_order`` — TimeoutError: kein
  ``button[data-nv-priority-reset]``.

``DescriptionTest`` (4/4 rot)
* ``test_tab_is_labelled_description_without_note_field`` —
  AssertionError: Der Tab heißt weiterhin ``Assistant``.
* ``test_step_status_reports_filled_and_open_steps`` — TimeoutError:
  ``span[data-nv-step-status]`` fehlt.
* ``test_draft_button_is_secondary`` — AssertionError: „Mit Agent
  entwerfen“ ist ``nv-ghost`` statt ``nv-secondary``.
* ``test_answer_save_updates_status_without_rerender`` — TimeoutError:
  ``button[data-nv-answer-save]``/Status-Pille fehlen.

``SettingsTabTest`` (8/8 rot)
* ``test_agents_file_is_the_first_section_with_split_editor`` —
  AssertionError: Erste Sektion ist ``team`` statt ``agentsfile``.
* ``test_agents_file_save_posts_before_after_and_digest`` — TimeoutError:
  ``textarea[data-nv-agents-before]`` fehlt.
* ``test_global_agents_hint_is_readonly`` — TimeoutError:
  ``details[data-nv-global-agents-hint]`` fehlt.
* ``test_agents_file_backup_and_restore_controls`` — AssertionError: Kein
  Sicherungs-Knopf, keine Inline-Bestätigung.
* ``test_github_explains_branches_and_puts_mr_above_issues`` —
  AssertionError: ``small[data-nv-github-help-source]`` fehlt.
* ``test_auto_merge_is_a_switch_row`` — TimeoutError:
  ``label.nv-switch-row[data-nv-automerge-switch]`` fehlt.
* ``test_team_model_is_a_combobox`` — AssertionError: Die Modellwahl ist
  weiterhin eine ``select``-Liste.
* ``test_there_is_no_own_pause_section`` — AssertionError: Die eigene
  Pause-Sektion existiert weiterhin.
"""
import http.client
import json
import os
import re
import shutil
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

from playwright.sync_api import sync_playwright  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"

PROJECT = "proj"

LONG_DESCRIPTION = (
    "Diese Beschreibung ist absichtlich sehr lang und besteht aus vielen "
    "Wörtern, damit sie in der schmalen Board-Spalte über die vereinbarten "
    "fünf Zeilen hinausläuft und ohne Aufklappen abgeschnitten werden muss. "
    "Sie wiederholt sich bewusst, damit die Höhe zuverlässig größer ist als "
    "der begrenzte Kasten und der Aufklapp-Knopf einen sichtbaren Unterschied "
    "macht. Noch ein Satz, noch ein Satz, noch ein Satz, noch ein Satz, "
    "noch ein Satz, noch ein Satz, noch ein Satz, noch ein Satz, noch ein "
    "Satz, noch ein Satz, noch ein Satz, noch ein Satz, noch ein Satz, "
    "noch ein Satz, noch ein Satz, noch ein Satz, noch ein Satz."
)

TICKETS = """# TICKETS — F33 Test

- [ ] F1 Erstes Paket
  Beschreibung: {long}

- [ ] F2 Zweites Paket
  Beschreibung: Kurz und knapp.

- [ ] F3 Blockiertes Paket
  Beschreibung: Wartet auf Freigabe.
  BLOCKIERT: externe Freigabe fehlt

- [x] F4 Erledigtes Paket
  Beschreibung: Fertig.
  Commit: 1234567; Test: test_erledigt
""".format(long=LONG_DESCRIPTION)

FEEDBACK = """# FEEDBACK — F33 Test

- [ ] B7 Absturz beim Start
  Beschreibung: Fenster bleibt leer.
  Art: Bug

- [ ] FB-1 Wunsch für die Oberfläche
  Beschreibung: Bitte größere Schaltflächen.
"""

SPEC = """# SPEC — F33 Test

## Produktziel

Ein gefüllter Absatz, der den Zweck beschreibt.

## Zielgruppe und Nutzung

Noch offen – im Projektassistenten ergänzen.

## Funktionsumfang

Noch offen – im Projektassistenten ergänzen.

## Nicht im Umfang

Noch offen – im Projektassistenten ergänzen.

## Zielumgebung

Noch offen – im Projektassistenten ergänzen.

## Qualität und Abnahme

Noch offen – im Projektassistenten ergänzen.
"""

PROJECT_AGENTS = """Projektregel davor.

<!-- vibe:general-rules -->
Verwaltete Regel 4711.
<!-- /vibe:general-rules -->

Projektregel danach.
"""

GLOBAL_AGENTS_TEXT = "GLOBALE-REGEL-4711: gilt für alle Projekte.\n"

TESTER_AGENT = """---
description: Testet die Anwendung
mode: subagent
model: opencode/tester-modell
permission:
  read: allow
  edit: deny
---

Teste die Anwendung.
"""

HELPER_AGENT = """---
description: Hilft beim Testen
mode: subagent
model: opencode/helper-modell
permission:
  read: allow
  edit: deny
---

Hilf beim Testen.
"""

FAKE_OPENCODE = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf 'opencode 2.1.4\\n'
    exit 0
    ;;
  models)
    printf 'opencode/tester-modell\\nopencode/helper-modell\\n'
    exit 0
    ;;
esac
exit 2
"""


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """opencode-Attrappe: leere Antworten, kein Modellaufruf."""

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


class F33ProjectBrowserTest(unittest.TestCase):
    """Dashboard, Browser, Fixtures für Projektdetail (WP3)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / PROJECT
        (cls.project / ".vibe").mkdir(parents=True)
        cls.home = cls.root / "home"
        cls.agents_dir = cls.home / ".config" / "opencode" / "agents"
        cls.agents_dir.mkdir(parents=True)
        (cls.agents_dir / "tester.md").write_text(TESTER_AGENT, encoding="utf-8")
        (cls.agents_dir / "helper.md").write_text(HELPER_AGENT, encoding="utf-8")
        cls.global_agents = cls.home / ".config" / "opencode" / "AGENTS.md"
        cls.global_agents.write_text(GLOBAL_AGENTS_TEXT, encoding="utf-8")
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir(parents=True)
        fake_bin = cls.root / "fakebin"
        fake_bin.mkdir()
        fake = fake_bin / "opencode"
        fake.write_text(FAKE_OPENCODE, encoding="utf-8")
        fake.chmod(0o755)

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
            "VIBE_STATE": str(cls.state_dir),
            "VIBE_RUNTIME": str(cls.log_dir),
            "HOME": str(cls.home),
            "TMPDIR": str(cls.root / "tmp"),
            "TMUX_TMPDIR": str(cls.tmux_dir),
            "VIBE_CONFIG_FILE": str(
                cls.home / ".config" / "vibe" / "config.json"),
            "PATH": str(fake_bin) + os.pathsep + env.get("PATH", ""),
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

    # ---------- Umgebung je Test ----------

    def setUp(self):
        self.write_fixtures()
        for path in (
            self.log_dir / f"{PROJECT}.pause-after",
            self.log_dir / "autonomous.json",
            self.project / ".vibe" / "agents.json",
        ):
            path.unlink(missing_ok=True)
        self.post_language("en")
        self.page_errors = []
        self.post_requests = []
        self.context = self.browser.new_context(
            viewport={"width": 1500, "height": 1000})
        self.context.add_init_script(
            "try { localStorage.setItem('nv-features', JSON.stringify("
            "{priority: true, github: true, agentsfile: true})); } "
            "catch (error) {}")
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))
        self.page.on(
            "request",
            lambda request: self.post_requests.append(request)
            if request.method == "POST" else None)

    def tearDown(self):
        self.page.close()
        self.context.close()

    def write_fixtures(self):
        (self.project / "TICKETS.md").write_text(TICKETS, encoding="utf-8")
        (self.project / "FEEDBACK.md").write_text(FEEDBACK, encoding="utf-8")
        (self.project / "SPEC.md").write_text(SPEC, encoding="utf-8")
        (self.project / "AGENTS.md").write_text(PROJECT_AGENTS, encoding="utf-8")
        (self.global_agents).write_text(GLOBAL_AGENTS_TEXT, encoding="utf-8")
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n"
            'GITHUB_ENABLED=""\nGITHUB_REPO="owner/name"\n',
            encoding="utf-8")

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
            conn.getresponse().read()
        finally:
            conn.close()

    def api_json(self, path):
        return self.page.evaluate(
            """async (url) => {
              const response = await fetch(url, {headers: {'Accept': 'application/json'}});
              return await response.json();
            }""", self.base + path)

    def post_json(self, path, payload):
        body = json.dumps(payload).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("POST", path, body=body, headers={
                "Host": f"127.0.0.1:{self.port}", "X-Token": self.token,
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{self.port}",
                "Sec-Fetch-Site": "same-origin"})
            response = conn.getresponse()
            return response.status, json.loads(
                response.read().decode("utf-8", "replace") or "{}")
        finally:
            conn.close()

    def wait_api(self, path, predicate, timeout=20, message=None):
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

    def posts_to(self, path):
        payloads = []
        for request in self.post_requests:
            if request.url.split("?")[0].endswith(path):
                try:
                    payloads.append(json.loads(request.post_data or "{}"))
                except ValueError:
                    payloads.append({})
        return payloads

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_project(self):
        self.boot()
        self.page.locator("[data-nv-action='open-project']").first.click()
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        return self.page.locator("main#nv-main[data-nv-view='project']")

    def open_tab(self, tab):
        self.page.locator(f"[data-nv-ptab='{tab}']").click()
        panel = self.page.locator(f"section[data-nv-ppanel='{tab}']")
        panel.wait_for(state="visible", timeout=20000)
        return panel

    def toast_text(self):
        toasts = self.page.locator("#nv-toasts")
        return (toasts.inner_text() if toasts.count() else "") or ""

    def classes(self, locator):
        return (locator.get_attribute("class") or "").split()

    def assert_follows(self, selectors, message):
        """Prüft die DOM-Reihenfolge der Selektoren (jeder folgt dem vorigen)."""
        missing = [selector for selector in selectors
                   if self.page.locator(selector).count() == 0]
        self.assertEqual([], missing,
                         message + " — fehlende Hooks: " + repr(missing))
        ordered = self.page.evaluate(
            """(selectors) => {
              const nodes = selectors.map(s => document.querySelector(s));
              return nodes.every((node, index) => index === 0 ||
                (nodes[index - 1].compareDocumentPosition(node)
                 & Node.DOCUMENT_POSITION_FOLLOWING) !== 0);
            }""", selectors)
        self.assertTrue(ordered, message)

    def assert_before(self, first, second, message):
        missing = [selector for selector in (first, second)
                   if self.page.locator(selector).count() == 0]
        self.assertEqual([], missing,
                         message + " — fehlende Hooks: " + repr(missing))
        result = self.page.evaluate(
            """([a, b]) => {
              const A = document.querySelector(a);
              const B = document.querySelector(b);
              if (!A || !B) return null;
              return (A.compareDocumentPosition(B)
                      & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
            }""", [first, second])
        self.assertTrue(result, message)

    def open_work(self):
        self.open_project()
        return self.open_tab("work")

    def open_feedback_box(self):
        details = self.page.locator("details[data-nv-feedback-box]")
        if details.count() and not details.evaluate("node => node.open"):
            details.locator("summary").first.click()
        return details

    def assert_clean_page(self):
        self.assertEqual(
            [], self.page_errors, "Die Projektansicht erzeugte JavaScript-Fehler")


class OverviewTest(F33ProjectBrowserTest):
    def test_sessions_card_has_no_guide_link(self):
        """Vorbedingung: Projekt geöffnet, Überblick aktiv.

        Erwartung: Die Sitzungskarte ``[data-nv-sessions]`` enthält keinen
        Link mit der Beschriftung „Leitfaden“ (deutsch/englisch); der
        Leitfaden bleibt über den Tab erreichbar.
        """
        self.open_project()
        sessions = self.page.locator("[data-nv-sessions]")
        sessions.wait_for(state="visible", timeout=20000)
        # Der Vertrag meint den Link *unter* den Sitzungen; er ist ein
        # Geschwister der Sitzungskarte. Deshalb wird der gesamte Überblick
        # geprüft, nicht nur der Inhalt von [data-nv-sessions].
        overview = self.page.locator("section[data-nv-ppanel='overview']")
        links = overview.locator("a")
        texts = [text.strip() for text in links.all_inner_texts()]
        self.assertFalse(
            any(re.search(r"leitfaden|guide", text, re.I) for text in texts),
            "Der Überblick enthält weiterhin einen Leitfaden-Link unter den "
            "Sitzungen: " + repr(texts))
        self.assertEqual(
            1, self.page.locator("[data-nv-ptab='assistant']").count(),
            "Der Leitfaden-Tab fehlt")
        self.assert_clean_page()

    def test_autonomous_row_lives_in_the_overview(self):
        """Vorbedingung: Überblick aktiv, autonomer Modus aus.

        Erwartung: ``div[data-nv-autonomous-row]`` ist im Überblick sichtbar,
        enthält ``input[data-nv-autonomous]`` und eine Erklärung, die das
        automatische Beantworten offener Rückfragen beschreibt.
        """
        self.open_project()
        overview = self.page.locator("section[data-nv-ppanel='overview']")
        row = overview.locator("div[data-nv-autonomous-row]")
        row.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            1, row.locator("input[data-nv-autonomous]").count(),
            "Die Autonom-Zeile enthält keinen Schalter [data-nv-autonomous]")
        text = row.inner_text() or ""
        self.assertTrue(
            re.search(r"automatisch|automatically|rückfragen|questions", text,
                      re.I),
            "Die Autonom-Zeile erklärt das automatische Beantworten nicht: "
            + repr(text))
        self.assert_clean_page()

    def test_pause_badge_only_shows_for_an_active_pause(self):
        """Vorbedingung: keine Pause angefordert.

        Aktion: ``[data-nv-action="pause"]`` im Held klicken.
        Erwartung: Vorher existiert keine ``span[data-nv-pause-badge]``;
        danach erscheint die Pille mit Klasse ``nv-warn`` und dem Hinweis auf
        die aktive Pause nach dem Paket.
        """
        self.open_project()
        badge = self.page.locator("span[data-nv-pause-badge]")
        self.assertEqual(
            0, badge.count(),
            "Die Pause-Pille ist ohne aktive Pause bereits vorhanden")
        self.page.locator("[data-nv-action='pause']").first.click()
        pause_file = self.log_dir / f"{PROJECT}.pause-after"
        self.wait_until(lambda: pause_file.is_file(), timeout=20,
                        message="Die Pause-Anforderung wurde nicht gespeichert")
        self.wait_until(lambda: badge.count() == 1, timeout=20,
                        message="Die Pause-Pille erscheint nicht")
        self.assertTrue(badge.first.is_visible(),
                        "Die Pause-Pille ist nicht sichtbar")
        self.assertIn(
            "nv-warn", self.classes(badge.first),
            "Die Pause-Pille trägt nicht die Klasse nv-warn")
        self.assertTrue(
            re.search(r"pause", badge.first.inner_text() or "", re.I),
            "Die Pause-Pille nennt die Pause nicht: "
            + repr(badge.first.inner_text()))
        self.assert_clean_page()


class WorkOrderTest(F33ProjectBrowserTest):
    def test_work_tab_follows_the_contract_order(self):
        """Vorbedingung: Feature ``priority`` an, Arbeit geöffnet.

        Erwartung: Aktionsleiste → Suche/Filter → Priorisierungsleiste →
        Board → Feedback in genau dieser DOM-Reihenfolge.
        """
        panel = self.open_work()
        self.assert_follows(
            [
                "section[data-nv-ppanel='work'] [data-nv-action='new-package']",
                "section[data-nv-ppanel='work'] input[data-nv-work-search]",
                "section[data-nv-ppanel='work'] div[data-nv-priority-strip]",
                "section[data-nv-ppanel='work'] .nv-board",
                "section[data-nv-ppanel='work'] details[data-nv-feedback-box]",
            ],
            "Die Arbeitsbereiche stehen nicht in der Reihenfolge "
            "Aktionsleiste → Suche → Priorisierung → Board → Feedback")
        self.assertTrue(panel.is_visible(), "Das Arbeits-Panel ist nicht sichtbar")
        self.assert_clean_page()

    def test_work_search_filters_ticket_and_feedback_cards_live(self):
        """Vorbedingung: Pakete F1/F2/F3/F4, Feedback B7/FB-1.

        Aktion: ``input[data-nv-work-search]`` mit „F2“ füllen, dann leeren.
        Erwartung: Nur die Karte F2 bleibt sichtbar, F1 wird ausgeblendet;
        nach dem Leeren sind beide wieder sichtbar.
        """
        self.open_work()
        search = self.page.locator("input[data-nv-work-search]")
        search.wait_for(state="visible", timeout=20000)
        card_f1 = self.page.locator("[data-nv-ticket='F1']")
        card_f2 = self.page.locator("[data-nv-ticket='F2']")
        search.fill("F2")
        self.wait_until(
            lambda: card_f2.is_visible() and not card_f1.is_visible(),
            timeout=15,
            message="Die Live-Suche blendet die nicht passende Karte F1 nicht "
                    "aus oder versteckt F2")
        search.fill("")
        self.wait_until(
            lambda: card_f1.is_visible(), timeout=15,
            message="Nach dem Leeren der Suche erscheint F1 nicht wieder")
        self.assert_clean_page()

    def test_hide_done_toggle_hides_and_shows_done_cards(self):
        """Vorbedingung: F4 ist erledigt.

        Aktion: ``button[data-nv-work-hide-done]`` prüfen, dann klicken.
        Erwartung: Standard ``aria-pressed="true"``, F4 unsichtbar; der Knopf
        nennt „Erledigte anzeigen (1)“. Nach dem Klick ist F4 sichtbar,
        ``aria-pressed="false"`` und der Knopf bietet das Ausblenden an.
        """
        self.open_work()
        toggle = self.page.locator("button[data-nv-work-hide-done]")
        toggle.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            "true", toggle.get_attribute("aria-pressed"),
            "„Erledigte ausblenden“ ist nicht standardmäßig aktiv")
        done = self.page.locator("[data-nv-ticket='F4']")
        self.assertFalse(done.is_visible(),
                         "Die erledigte Karte F4 ist trotz Standardfilter sichtbar")
        label = toggle.inner_text() or ""
        self.assertTrue(
            re.search(r"anzeigen|show", label, re.I) and "1" in label,
            "Der Knopf bietet nicht „Erledigte anzeigen (1)“ an: " + repr(label))
        toggle.click()
        self.wait_until(
            lambda: toggle.get_attribute("aria-pressed") == "false",
            timeout=15,
            message="Der Klick setzt aria-pressed nicht auf false")
        self.wait_until(lambda: done.is_visible(), timeout=15,
                        message="Die erledigte Karte F4 erscheint nicht")
        self.assertTrue(
            re.search(r"ausblend|hide", toggle.inner_text() or "", re.I),
            "Der Knopf bietet nach dem Einblenden kein Ausblenden an: "
            + repr(toggle.inner_text()))
        self.assert_clean_page()

    def test_long_ticket_description_is_clamped_and_expandable(self):
        """Vorbedingung: F1 hat eine sehr lange Beschreibung.

        Aktion: ``button[data-nv-ticket-more]`` klicken.
        Erwartung: ``div.nv-ticket-desc`` ist zunächst auf ~5 Zeilen begrenzt
        (scrollHeight > clientHeight), ``aria-expanded="false"``; nach dem
        Klick ist der Text vollständig sichtbar und ``aria-expanded="true"``.
        """
        self.open_work()
        card = self.page.locator("[data-nv-ticket='F1']")
        desc = card.locator("div.nv-ticket-desc")
        desc.wait_for(state="visible", timeout=20000)
        more = card.locator("button[data-nv-ticket-more]")
        self.assertEqual(1, more.count(),
                         "Der Aufklapp-Knopf [data-nv-ticket-more] fehlt")
        self.assertEqual("false", more.get_attribute("aria-expanded"),
                         "Der Aufklapp-Knopf meldet nicht aria-expanded=false")
        clamped = desc.evaluate(
            "node => ({client: node.clientHeight, scroll: node.scrollHeight})")
        self.assertGreater(
            clamped["scroll"], clamped["client"] + 4,
            "Die lange Beschreibung ist nicht sichtbar begrenzt: " + repr(clamped))
        more.click()
        self.wait_until(
            lambda: more.get_attribute("aria-expanded") == "true",
            timeout=15, message="Der Aufklapp-Knopf setzt aria-expanded nicht")
        opened = desc.evaluate(
            "node => ({client: node.clientHeight, scroll: node.scrollHeight})")
        self.assertGreaterEqual(
            opened["client"] + 4, opened["scroll"],
            "Die Beschreibung ist nach dem Aufklappen nicht vollständig "
            "sichtbar: " + repr(opened))
        self.assertTrue(
            re.search(r"weniger|less", more.inner_text() or "", re.I),
            "Der Knopf bietet nach dem Aufklappen kein „weniger“ an: "
            + repr(more.inner_text()))
        self.assert_clean_page()

    def test_ticket_actions_are_visible_secondary_and_danger_buttons(self):
        """Vorbedingung: Karte F1 im Board.

        Erwartung: ``data-nv-action="ticket-edit"`` ist ein sichtbarer Knopf
        mit ``nv-secondary``, ``data-nv-action="ticket-delete"`` mit
        ``nv-danger``.
        """
        self.open_work()
        card = self.page.locator("[data-nv-ticket='F1']")
        card.wait_for(state="visible", timeout=20000)
        edit = card.locator("button[data-nv-action='ticket-edit']")
        delete = card.locator("button[data-nv-action='ticket-delete']")
        self.assertEqual(1, edit.count(), "Der Bearbeiten-Knopf fehlt")
        self.assertEqual(1, delete.count(), "Der Löschen-Knopf fehlt")
        self.assertTrue(edit.is_visible(), "Der Bearbeiten-Knopf ist unsichtbar")
        self.assertTrue(delete.is_visible(), "Der Löschen-Knopf ist unsichtbar")
        self.assertIn("nv-secondary", self.classes(edit),
                      "Der Bearbeiten-Knopf trägt nicht nv-secondary")
        self.assertIn("nv-danger", self.classes(delete),
                      "Der Löschen-Knopf trägt nicht nv-danger")
        self.assert_clean_page()

    def test_feedback_box_starts_collapsed_with_edit_and_delete(self):
        """Vorbedingung: zwei offene Feedback-Einträge.

        Erwartung: ``details[data-nv-feedback-box]`` ist anfangs zu, die
        Summary nennt „Feedback (2 offen)“; nach dem Aufklappen hat jeder
        Eintrag sichtbare ``feedback-edit``- und ``feedback-delete``-Knöpfe.
        """
        self.open_work()
        details = self.page.locator("details[data-nv-feedback-box]")
        details.wait_for(state="visible", timeout=20000)
        self.assertFalse(details.evaluate("node => node.open"),
                         "Die Feedback-Box ist standardmäßig aufgeklappt")
        summary = details.locator("summary").first.inner_text() or ""
        self.assertTrue(re.search(r"feedback", summary, re.I),
                        "Die Summary nennt Feedback nicht: " + repr(summary))
        self.assertIn("2", summary,
                      "Die Summary nennt nicht zwei offene Einträge: "
                      + repr(summary))
        self.open_feedback_box()
        edits = details.locator("button[data-nv-action='feedback-edit']")
        deletes = details.locator("button[data-nv-action='feedback-delete']")
        self.assertGreaterEqual(edits.count(), 2,
                                "Nicht jeder Feedback-Eintrag hat einen "
                                "Bearbeiten-Knopf")
        self.assertGreaterEqual(deletes.count(), 2,
                                "Nicht jeder Feedback-Eintrag hat einen "
                                "Löschen-Knopf")
        self.assertTrue(edits.first.is_visible(),
                        "Der Bearbeiten-Knopf der Feedback-Karte ist unsichtbar")
        self.assert_clean_page()

    def test_feedback_edit_posts_update(self):
        """Vorbedingung: Feedback B7 offen.

        Aktion: Bearbeiten öffnen, Titel ändern, speichern.
        Erwartung: Die Kennung ist schreibgeschützt; der POST geht an
        ``/api/feedback`` mit ``action:"update"`` und ``id:"B7"``; die
        geänderte Beschreibung erscheint anschließend in ``/api/project``.
        """
        self.open_work()
        details = self.open_feedback_box()
        item = details.locator("[data-nv-feedback-item='B7']")
        item.wait_for(state="visible", timeout=20000)
        item.locator("button[data-nv-action='feedback-edit']").click()
        form = self.page.locator("[data-nv-ticket-form]")
        form.wait_for(state="visible", timeout=15000)
        ident = form.locator("input[data-nv-field='id']")
        self.assertFalse(ident.is_editable(),
                         "Die Kennung ist beim Bearbeiten nicht schreibgeschützt")
        self.assertEqual("B7", ident.input_value(),
                         "Das Bearbeiten-Formular trägt nicht die Kennung B7")
        form.locator("input[data-nv-field='title']").fill(
            "Absturz beim Start (neu)")
        form.locator("button[data-nv-action='ticket-save']").click()
        self.wait_until(
            lambda: any(payload.get("action") == "update"
                        and payload.get("id") == "B7"
                        for payload in self.posts_to("/api/feedback")),
            timeout=20,
            message="Es wurde kein /api/feedback-POST mit action=update "
                    "gesendet: " + repr(self.posts_to("/api/feedback")))
        self.wait_api(
            f"/api/project?name={PROJECT}",
            lambda data: any(
                entry.get("id") == "B7"
                and "Absturz beim Start (neu)" in str(entry.get("title") or "")
                for entry in data.get("feedback", [])),
            message="Der geänderte Feedback-Titel ist nicht gespeichert")
        self.assert_clean_page()

    def test_feedback_delete_posts_delete(self):
        """Vorbedingung: Feedback B7 offen.

        Aktion: Löschen bestätigen.
        Erwartung: POST ``/api/feedback`` mit ``action:"delete"`` und
        ``id:"B7"``; der Eintrag verschwindet aus ``/api/project``.
        """
        self.open_work()
        details = self.open_feedback_box()
        item = details.locator("[data-nv-feedback-item='B7']")
        item.wait_for(state="visible", timeout=20000)
        self.page.on("dialog", lambda dialog: dialog.accept())
        item.locator("button[data-nv-action='feedback-delete']").click()
        self.wait_until(
            lambda: any(payload.get("action") == "delete"
                        and payload.get("id") == "B7"
                        for payload in self.posts_to("/api/feedback")),
            timeout=20,
            message="Es wurde kein /api/feedback-POST mit action=delete "
                    "gesendet: " + repr(self.posts_to("/api/feedback")))
        self.wait_api(
            f"/api/project?name={PROJECT}",
            lambda data: all(entry.get("id") != "B7"
                             for entry in data.get("feedback", [])),
            message="Der gelöschte Feedback-Eintrag B7 ist weiterhin vorhanden")
        self.assert_clean_page()

    def test_form_opens_directly_under_the_action_bar(self):
        """Vorbedingung: Arbeit geöffnet, kein Formular im Ruhezustand.

        Aktion: ``[data-nv-action="new-package"]`` klicken.
        Erwartung: ``[data-nv-ticket-form]`` erscheint nach der Aktionsleiste
        und vor dem Board, im sichtbaren oberen Bereich (kein Riesenscroll).
        """
        self.open_work()
        self.assertEqual(
            0, self.page.locator("[data-nv-ticket-form]").count(),
            "Im Ruhezustand steht bereits ein Formular im DOM")
        self.page.locator("[data-nv-action='new-package']").first.click()
        form = self.page.locator("[data-nv-ticket-form]")
        form.wait_for(state="visible", timeout=15000)
        self.assert_before(
            "section[data-nv-ppanel='work'] [data-nv-action='new-package']",
            "[data-nv-ticket-form]",
            "Das Formular steht nicht unter der Aktionsleiste")
        self.assert_before(
            "[data-nv-ticket-form]",
            "section[data-nv-ppanel='work'] .nv-board",
            "Das Formular steht nicht vor dem Board")
        box = form.bounding_box()
        self.assertIsNotNone(box)
        self.assertGreaterEqual(box["y"], 0,
                                "Das Formular liegt oberhalb des Viewports")
        self.assertLess(
            box["y"], 0.75 * 1000,
            "Das Formular öffnet erst weit unten (Riesenscroll): y="
            + repr(box["y"]))
        self.assert_clean_page()

    def test_id_field_has_placeholder_hint_and_suggestion(self):
        """Vorbedingung: Pakete F1–F4 und Bug B7 vorhanden.

        Aktion: „Paket anlegen“ und danach „Bug melden“ öffnen.
        Erwartung: ``input[data-nv-field="id"]`` trägt den Platzhalter
        „leer lassen = automatisch vergeben“, einen Hinweis
        ``small[data-nv-id-hint]`` und ist mit dem nächsten Vorschlag
        vorbelegt: ``F5`` für Pakete, ``B8`` für Bugs; das Feld ist löschbar.
        """
        self.open_work()
        self.page.locator("[data-nv-action='new-package']").first.click()
        form = self.page.locator("[data-nv-ticket-form]")
        form.wait_for(state="visible", timeout=15000)
        ident = form.locator("input[data-nv-field='id']")
        placeholder = ident.get_attribute("placeholder") or ""
        self.assertTrue(
            re.search(r"leer|empty|automatisch|automatic", placeholder, re.I),
            "Der Platzhalter der Kennung erklärt das Leerlassen nicht: "
            + repr(placeholder))
        hint = form.locator("small[data-nv-id-hint]")
        self.assertEqual(1, hint.count(),
                         "Der Kennungs-Hinweis small[data-nv-id-hint] fehlt")
        self.assertTrue(
            re.search(r"automatisch|automatic|vergeben|assign",
                      hint.inner_text() or "", re.I),
            "Der Kennungs-Hinweis erklärt die automatische Vergabe nicht: "
            + repr(hint.inner_text()))
        self.assertEqual("F5", ident.input_value(),
                         "Das Paket-Formular ist nicht mit dem nächsten "
                         "Vorschlag F5 vorbelegt")
        ident.fill("")
        self.assertEqual("", ident.input_value(),
                         "Das Kennungsfeld lässt sich nicht leeren")

        self.page.locator("[data-nv-action='new-bug']").first.click()
        form = self.page.locator("[data-nv-ticket-form]")
        form.wait_for(state="visible", timeout=15000)
        ident = form.locator("input[data-nv-field='id']")
        self.assertEqual("B8", ident.input_value(),
                         "Das Bug-Formular ist nicht mit dem nächsten "
                         "Vorschlag B8 vorbelegt")
        self.assert_clean_page()


class PriorityTest(F33ProjectBrowserTest):
    def prepare_order(self, order):
        status, data = self.post_json(
            "/api/priority", {"name": PROJECT, "action": "set", "order": order})
        self.assertEqual(200, status, repr(data))

    def test_strip_sits_above_the_board_with_badges_and_count(self):
        """Vorbedingung: gespeicherte Reihenfolge F2 vor F1.

        Erwartung: ``div[data-nv-priority-strip]`` steht oberhalb des Boards;
        die Karte F2 trägt ``span[data-nv-prio-badge]`` „P1“, F1 „P2“; die
        Leiste meldet „2 priorisiert“.
        """
        self.prepare_order("F2 F1")
        self.open_work()
        strip = self.page.locator("div[data-nv-priority-strip]")
        strip.wait_for(state="visible", timeout=20000)
        self.assert_before(
            "section[data-nv-ppanel='work'] div[data-nv-priority-strip]",
            "section[data-nv-ppanel='work'] .nv-board",
            "Die Priorisierungsleiste steht nicht oberhalb des Boards")
        first = self.page.locator(
            "[data-nv-ticket='F2'] span[data-nv-prio-badge]")
        second = self.page.locator(
            "[data-nv-ticket='F1'] span[data-nv-prio-badge]")
        self.assertEqual(1, first.count(),
                         "Die priorisierte Karte F2 trägt kein P1-Badge")
        self.assertEqual(1, second.count(),
                         "Die priorisierte Karte F1 trägt kein P2-Badge")
        self.assertRegex(first.inner_text() or "", r"P1",
                         "Das erste Badge ist nicht P1")
        self.assertRegex(second.inner_text() or "", r"P2",
                         "Das zweite Badge ist nicht P2")
        text = strip.inner_text() or ""
        self.assertTrue(
            re.search(r"2", text) and re.search(
                r"priorisiert|prioriti[sz]ed|priorit", text, re.I),
            "Die Leiste meldet nicht „2 priorisiert“: " + repr(text))
        self.assert_clean_page()

    def test_drag_and_drop_saves_the_order(self):
        """Vorbedingung: keine gespeicherte Reihenfolge, offene Pakete.

        Aktion: Drag-Griff von F2 auf die Zeile von F1 ziehen.
        Erwartung: ``POST /api/priority`` mit ``action:"set"`` und einer von
        der Ausgangsfolge abweichenden Permutation; die neue Folge ist über
        ``GET /api/priority`` persistiert.
        """
        self.open_work()
        strip = self.page.locator("div[data-nv-priority-strip]")
        strip.wait_for(state="visible", timeout=20000)
        handles = strip.locator("button[data-nv-drag-handle]")
        self.assertGreaterEqual(handles.count(), 2,
                                "Die Priorisierungszeilen haben keine "
                                "Drag-Griffe")
        rows = handles.evaluate_all(
            "nodes => nodes.map(n => (n.parentElement.textContent || '').trim())")
        index_f2 = next((i for i, text in enumerate(rows) if "F2" in text), None)
        index_f1 = next((i for i, text in enumerate(rows) if "F1" in text), None)
        self.assertIsNotNone(index_f2, "Keine Zeile für F2: " + repr(rows))
        self.assertIsNotNone(index_f1, "Keine Zeile für F1: " + repr(rows))
        before = [row.split()[0] for row in rows]
        handles.nth(index_f2).drag_to(handles.nth(index_f1))
        self.wait_until(
            lambda: any(payload.get("action") == "set"
                        for payload in self.posts_to("/api/priority")),
            timeout=20,
            message="Der Drop speichert nicht über POST /api/priority "
                    "{action:'set'}: " + repr(self.posts_to("/api/priority")))
        payload = [p for p in self.posts_to("/api/priority")
                   if p.get("action") == "set"][-1]
        order = [part for part in str(payload.get("order") or "").split()
                 if part]
        self.assertIn("F1", order, "Die gespeicherte Folge enthält F1 nicht: "
                                   + repr(order))
        self.assertIn("F2", order, "Die gespeicherte Folge enthält F2 nicht: "
                                   + repr(order))
        self.assertNotEqual(
            before[:len(order)], order,
            "Der Drop hat die Reihenfolge nicht verändert: " + repr(order))
        self.wait_api(
            f"/api/priority?name={PROJECT}",
            lambda data: [str(entry.get("id"))
                          for entry in (data.get("order") or [])] == order,
            message="Die per Drop gespeicherte Reihenfolge ist nicht "
                    "persistiert: " + repr(order))
        self.assert_clean_page()

    def test_arrow_buttons_reorder_and_save(self):
        """Vorbedingung: keine gespeicherte Reihenfolge, F1 vor F2.

        Aktion: ↓ am Paket F1 klicken.
        Erwartung: F1 rückt hinter F2; die Änderung wird als
        ``POST /api/priority {action:"set"}`` gespeichert.
        """
        self.open_work()
        strip = self.page.locator("div[data-nv-priority-strip]")
        strip.wait_for(state="visible", timeout=20000)
        down = strip.locator("button[data-nv-action='priority-down']")
        self.assertGreaterEqual(down.count(), 1,
                                "Die Priorisierungszeilen haben keine "
                                "↓-Knöpfe")
        target = None
        for index in range(down.count()):
            row_text = down.nth(index).evaluate(
                "node => (node.parentElement.textContent || '')")
            if "F1" in row_text:
                target = down.nth(index)
                break
        self.assertIsNotNone(target, "Keine ↓-Knopf-Zeile für F1 gefunden")
        target.click()
        self.wait_until(
            lambda: any(payload.get("action") == "set"
                        and [part for part in str(payload.get("order") or "")
                             .split()][:2] == ["F2", "F1"]
                        for payload in self.posts_to("/api/priority")),
            timeout=20,
            message="Der ↓-Knopf speichert die neue Reihenfolge F2 vor F1 "
                    "nicht: " + repr(self.posts_to("/api/priority")))
        self.assert_clean_page()

    def test_reset_clears_the_order(self):
        """Vorbedingung: gespeicherte Reihenfolge F2 vor F1.

        Aktion: ``button[data-nv-priority-reset]`` klicken.
        Erwartung: ``POST /api/priority`` mit ``action:"set"`` und
        ``order:""``; danach tragen die Karten keine Prioritäts-Badges mehr.
        """
        self.prepare_order("F2 F1")
        self.open_work()
        strip = self.page.locator("div[data-nv-priority-strip]")
        strip.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(
            self.page.locator("span[data-nv-prio-badge]").count(), 1,
            "Vorbedingung: Die priorisierte Reihenfolge zeigt keine Badges")
        reset = strip.locator("button[data-nv-priority-reset]")
        self.assertEqual(1, reset.count(),
                         "Der Zurücksetzen-Knopf fehlt")
        reset.click()
        self.wait_until(
            lambda: any(payload.get("action") == "set"
                        and str(payload.get("order") or "") == ""
                        for payload in self.posts_to("/api/priority")),
            timeout=20,
            message="Das Zurücksetzen sendet nicht order:\"\": "
                    + repr(self.posts_to("/api/priority")))
        self.wait_until(
            lambda: self.page.locator("span[data-nv-prio-badge]").count() == 0,
            timeout=15,
            message="Die Prioritäts-Badges bleiben nach dem Zurücksetzen stehen")
        self.assert_clean_page()


class DescriptionTest(F33ProjectBrowserTest):
    def open_description(self):
        self.open_project()
        return self.open_tab("assistant")

    def test_tab_is_labelled_description_without_note_field(self):
        """Vorbedingung: Projekt geöffnet.

        Erwartung: Der Tab ``data-nv-ptab="assistant"`` heißt „Beschreibung“
        (englisch „Description“); im Panel gibt es kein ``[data-nv-note]``
        mehr, die Leitfragen bleiben sichtbar.
        """
        panel = self.open_description()
        tab = self.page.locator("[data-nv-ptab='assistant']")
        # F33 WP3: Vertrag/Nutzerentscheidung 3 verlangt sichtbar
        # „Beschreibung“ (en „Description“) — die Prüfung ist case-insensitiv.
        self.assertRegex(
            tab.inner_text() or "",
            re.compile(r"beschreibung|description", re.I),
            "Der Tab heißt nicht „Beschreibung“: " + repr(tab.inner_text()))
        self.assertEqual(
            0, panel.locator("[data-nv-note]").count(),
            "Das Notizfeld [data-nv-note] existiert weiterhin")
        self.assertGreaterEqual(
            panel.locator("textarea[data-nv-answer-field]").count(), 1,
            "Die Leitfragen-Antworten fehlen")
        self.assert_clean_page()

    def test_step_status_reports_filled_and_open_steps(self):
        """Vorbedingung: ``ziel`` ist gefüllt, ``nutzer`` ist offen.

        Erwartung: ``span[data-nv-step-status]`` ist gefüllt und trägt je
        Schritt ``nv-ok`` (ausgefüllt) bzw. ``nv-warn`` (offen) sowie den
        ``title`` „Zeigt an, ob dieser Abschnitt schon beantwortet ist“.
        """
        panel = self.open_description()
        statuses = panel.locator("span[data-nv-step-status]")
        statuses.first.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(statuses.count(), 2,
                                "Es fehlen Schritt-Status-Pillen")
        self.assertIn("nv-ok", self.classes(statuses.nth(0)),
                      "Der gefüllte Schritt trägt nicht nv-ok")
        self.assertIn("nv-warn", self.classes(statuses.nth(1)),
                      "Der offene Schritt trägt nicht nv-warn")
        for index in range(2):
            pill = statuses.nth(index)
            self.assertTrue((pill.inner_text() or "").strip(),
                            "Eine Status-Pille ist leer")
            self.assertRegex(
                pill.get_attribute("title") or "",
                r"beantwortet|answered|ausgefüllt|filled",
                "Der Status-Pille fehlt der erklärende title")
        self.assert_clean_page()

    def test_draft_button_is_secondary(self):
        """Vorbedingung: Beschreibung geöffnet.

        Erwartung: „Mit Agent entwerfen“ ist ein Knopf der Klasse
        ``nv-secondary`` (klar sichtbar, nicht Ghost).
        """
        panel = self.open_description()
        buttons = panel.locator("button").filter(
            has_text=re.compile(r"entwerfen|draft", re.I))
        self.assertGreaterEqual(buttons.count(), 1,
                                "Der Knopf „Mit Agent entwerfen“ fehlt")
        self.assertIn(
            "nv-secondary", self.classes(buttons.first),
            "„Mit Agent entwerfen“ trägt nicht die Klasse nv-secondary: "
            + repr(buttons.first.get_attribute("class")))
        self.assert_clean_page()

    def test_answer_save_updates_status_without_rerender(self):
        """Vorbedingung: Schritt ``nutzer`` ist offen.

        Aktion: Antwort eintragen, ``button[data-nv-answer-save]`` klicken.
        Erwartung: Kein Voll-Neurender (dieselbe Schritt-DOM bleibt bestehen,
        kein Skelett), die Status-Pille wechselt lokal auf ``nv-ok`` und ein
        Toast bestätigt; ``/api/guide`` meldet den Schritt als gefüllt.
        """
        panel = self.open_description()
        field = panel.locator("textarea[data-nv-answer-field='nutzer']")
        field.wait_for(state="visible", timeout=20000)
        step = field.locator(
            "xpath=ancestor::*[.//span[@data-nv-step-status]][1]")
        step.evaluate("node => node.setAttribute('data-test-sentinel', '1')")
        pill = step.locator("span[data-nv-step-status]")
        self.assertIn("nv-warn", self.classes(pill),
                      "Vorbedingung: Der Schritt nutzer ist nicht offen")
        field.fill("Antwort-4711: Die Zielgruppe sind Tester.")
        step.locator("button[data-nv-answer-save]").click()
        self.wait_until(
            lambda: re.search(r"gespeichert|saved", self.toast_text(), re.I)
            is not None,
            timeout=20,
            message="Das Speichern der Antwort bestätigt nicht: "
                    + repr(self.toast_text()))
        self.wait_until(
            lambda: "nv-ok" in self.classes(
                panel.locator(
                    "textarea[data-nv-answer-field='nutzer']"
                ).locator(
                    "xpath=ancestor::*[.//span[@data-nv-step-status]][1]"
                ).locator("span[data-nv-step-status]")),
            timeout=20,
            message="Die Status-Pille wechselt nach dem Speichern nicht auf "
                    "ausgefüllt")
        self.assertEqual(
            "1", step.get_attribute("data-test-sentinel"),
            "Die Ansicht wurde vollständig neu gerendert (Schritt-DOM ersetzt)")
        self.assertEqual(
            "Antwort-4711: Die Zielgruppe sind Tester.", field.input_value(),
            "Die Antwort ging beim Speichern verloren")
        self.assertFalse(
            panel.locator(".nv-skeleton:visible").count() > 0,
            "Beim Speichern erscheint ein Skelett-Platzhalter")
        self.wait_api(
            f"/api/guide?name={PROJECT}",
            lambda data: any(
                entry.get("id") == "nutzer"
                and entry.get("status") == "gefüllt"
                for entry in data.get("steps", [])),
            message="Der Leitfaden-Schritt nutzer ist nicht als gefüllt "
                    "gespeichert")
        self.assert_clean_page()


class SettingsTabTest(F33ProjectBrowserTest):
    def open_settings(self):
        self.open_project()
        return self.open_tab("settings")

    def section(self, name):
        locator = self.page.locator(f"[data-nv-psection='{name}']")
        locator.wait_for(state="visible", timeout=20000)
        return locator

    def test_agents_file_is_the_first_section_with_split_editor(self):
        """Vorbedingung: Feature ``agentsfile`` an, AGENTS.md mit verwaltetem
        Block vorhanden.

        Erwartung: ``[data-nv-psection="agentsfile"]`` ist die erste Sektion
        (vor Team); ``textarea[data-nv-agents-before]`` enthält den freien
        Teil davor, ``pre[data-nv-agents-managed]`` ist readonly und zeigt den
        verwalteten Block, ``textarea[data-nv-agents-after]`` den Teil danach;
        ``data-nv-action="agents-file-create"`` existiert.
        """
        panel = self.open_settings()
        order = panel.evaluate(
            """node => Array.from(node.querySelectorAll(
                 'section[data-nv-psection]'))
                 .map(section => section.getAttribute('data-nv-psection'))""")
        self.assertTrue(order, "Es wurden keine Projekt-Sektionen gefunden")
        self.assertEqual(
            "agentsfile", order[0],
            "AGENTS.md ist nicht die erste Sektion der Einstellungen: "
            + repr(order))
        section = self.section("agentsfile")
        before = section.locator("textarea[data-nv-agents-before]")
        after = section.locator("textarea[data-nv-agents-after]")
        managed = section.locator("pre[data-nv-agents-managed]")
        self.assertEqual(1, before.count(), "textarea[data-nv-agents-before] fehlt")
        self.assertEqual(1, after.count(), "textarea[data-nv-agents-after] fehlt")
        self.assertEqual(1, managed.count(), "pre[data-nv-agents-managed] fehlt")
        self.assertIn("Projektregel davor",
                      before.input_value(),
                      "Der freie Teil davor ist nicht vorbelegt")
        self.assertIn("Verwaltete Regel 4711", managed.inner_text(),
                      "Der verwaltete Block wird nicht angezeigt")
        self.assertIsNotNone(managed.get_attribute("readonly"),
                             "Der verwaltete Block ist nicht readonly")
        self.assertIn("Projektregel danach",
                      after.input_value(),
                      "Der freie Teil danach ist nicht vorbelegt")
        self.assertEqual(
            1, section.locator("[data-nv-action='agents-file-create']").count(),
            "Der Anlegen-Knopf agents-file-create fehlt")
        self.assert_clean_page()

    def test_agents_file_save_posts_before_after_and_digest(self):
        """Vorbedingung: AGENTS.md vorhanden.

        Aktion: Freien Teil davor ändern und speichern.
        Erwartung: POST ``/api/agents_file`` mit ``action:"save"``,
        ``before``, ``after`` und nichtleerem ``digest``; Toast; die Datei
        enthält den neuen Text, der verwaltete Block wird auf die kanonischen
        Regeln normalisiert (Bestandsverhalten, siehe F31).
        """
        self.open_settings()
        section = self.section("agentsfile")
        before = section.locator("textarea[data-nv-agents-before]")
        before.fill("Neue Regel davor 4711.\n")
        save = section.locator("button[data-nv-action='agents-file-save']")
        self.assertEqual(1, save.count(),
                         "Der Speichern-Knopf agents-file-save fehlt")
        save.click()
        self.wait_until(
            lambda: any(payload.get("action") == "save"
                        for payload in self.posts_to("/api/agents_file")),
            timeout=20,
            message="Es wurde kein /api/agents_file-POST mit action=save "
                    "gesendet: " + repr(self.posts_to("/api/agents_file")))
        payload = [p for p in self.posts_to("/api/agents_file")
                   if p.get("action") == "save"][-1]
        self.assertIn("Neue Regel davor 4711", str(payload.get("before") or ""),
                      "Der POST enthält den geänderten Teil davor nicht")
        self.assertTrue(str(payload.get("after") or "").strip(),
                        "Der POST enthält den Teil danach nicht")
        self.assertTrue(str(payload.get("digest") or ""),
                        "Der POST enthält keine Prüfsumme")
        self.wait_until(
            lambda: re.search(r"gespeichert|saved", self.toast_text(), re.I)
            is not None,
            timeout=20,
            message="Das Speichern der AGENTS.md bestätigt nicht")
        # F33 WP6: der bestehende GET-Vertrag antwortet flach
        # ({exists, digest, before, managed, after}); nur POST-Antworten
        # tragen den agents_file-Wrapper — kein Breaking Change.
        self.wait_api(
            f"/api/agents_file?name={PROJECT}",
            lambda data: "Neue Regel davor 4711"
            in str(data.get("before") or ""),
            message="Der geänderte freie Teil ist nicht gespeichert")
        text = (self.project / "AGENTS.md").read_text(encoding="utf-8")
        # F33: der verwaltete Block wird beim Speichern auf die kanonischen
        # GENERAL_RULES normalisiert (Bestandsverhalten seit F31, bin/vibe
        # agents_file_save) — der Fixture-Platzhalter bleibt nicht erhalten.
        self.assertIn("<!-- vibe:general-rules -->", text,
                      "Der kanonische verwaltete Block fehlt nach dem Speichern")
        self.assertIn("## Projektordner sauber halten", text,
                      "Der kanonische Regeln-Inhalt fehlt nach dem Speichern")
        self.assertNotIn(
            "Verwaltete Regel 4711", text,
            "Der Fixture-Platzhalter wurde nicht auf GENERAL_RULES normalisiert")
        self.assert_clean_page()

    def test_global_agents_hint_is_readonly(self):
        """Vorbedingung: globale AGENTS.md vorhanden.

        Erwartung: ``details[data-nv-global-agents-hint]`` nennt die globale
        Datei („immer gültig“) und zeigt ihren Inhalt in einem readonly
        ``pre`` aus ``GET /api/global_agents_file``.
        """
        self.open_settings()
        details = self.page.locator("details[data-nv-global-agents-hint]")
        details.wait_for(state="visible", timeout=20000)
        summary = details.locator("summary").first.inner_text() or ""
        # F33 WP3: der Hinweis heißt „Globale AGENTS.md (immer gültig)“;
        # die Prüfung bleibt case-insensitiv gegenüber der genauen Formulierung.
        self.assertRegex(summary, re.compile(r"global", re.I),
                         "Die Hinweis-Summary nennt die globale Datei nicht: "
                         + repr(summary))
        self.assertRegex(summary, re.compile(r"agents", re.I),
                         "Die Hinweis-Summary nennt AGENTS.md nicht: "
                         + repr(summary))
        pre = details.locator("pre")
        self.assertGreaterEqual(pre.count(), 1,
                                "Der readonly-Inhalt der globalen AGENTS.md fehlt")
        self.assertIsNotNone(pre.first.get_attribute("readonly"),
                             "Der Inhalt der globalen AGENTS.md ist nicht readonly")
        self.assertIn("GLOBALE-REGEL-4711", pre.first.inner_text(),
                      "Der Inhalt der globalen AGENTS.md wird nicht angezeigt")
        self.assert_clean_page()

    def test_agents_file_backup_and_restore_controls(self):
        """Vorbedingung: AGENTS.md-Sektion sichtbar.

        Erwartung: ``agents-file-backup`` und ``agents-file-restore``
        existieren; ein Klick auf Wiederherstellen zeigt zuerst die
        Inline-Bestätigung ``div[data-nv-agents-restore-confirm]``, ohne
        sofort zu schreiben.
        """
        self.open_settings()
        section = self.section("agentsfile")
        backup = section.locator("button[data-nv-action='agents-file-backup']")
        restore = section.locator("button[data-nv-action='agents-file-restore']")
        self.assertEqual(1, backup.count(), "Der Sicherungs-Knopf fehlt")
        self.assertEqual(1, restore.count(), "Der Wiederherstellen-Knopf fehlt")
        confirm = section.locator("div[data-nv-agents-restore-confirm]")
        self.assertEqual(1, confirm.count(),
                         "Die Inline-Bestätigung der Wiederherstellung fehlt")
        self.assertFalse(confirm.is_visible(),
                         "Die Bestätigung ist ohne Klick bereits sichtbar")
        restore.click()
        confirm.wait_for(state="visible", timeout=15000)
        self.assertEqual(
            0, len([payload for payload in self.posts_to("/api/agents_file")
                    if payload.get("action") == "restore"]),
            "Die Wiederherstellung wurde ohne Bestätigung ausgeführt")
        self.assert_clean_page()

    def test_github_explains_branches_and_puts_mr_above_issues(self):
        """Vorbedingung: Feature ``github`` an.

        Erwartung: ``small[data-nv-github-help-source]`` und
        ``small[data-nv-github-help-target]`` erklären Quell-/Ziel-Branch;
        der Merge-Request-Block steht über dem Issue-Block.
        """
        self.open_settings()
        section = self.section("github")
        source = section.locator("small[data-nv-github-help-source]")
        target = section.locator("small[data-nv-github-help-target]")
        self.assertEqual(1, source.count(),
                         "Die Erklärung des Quell-Branches fehlt")
        self.assertEqual(1, target.count(),
                         "Die Erklärung des Ziel-Branches fehlt")
        self.assertTrue((source.inner_text() or "").strip(),
                        "Die Erklärung des Quell-Branches ist leer")
        self.assertTrue((target.inner_text() or "").strip(),
                        "Die Erklärung des Ziel-Branches ist leer")
        self.assert_before(
            "[data-nv-psection='github'] [data-nv-action='github-pr']",
            "[data-nv-psection='github'] [data-nv-action='github-issues']",
            "Der Merge-Request-Block steht nicht über dem Issue-Block")
        self.assert_clean_page()

    def test_auto_merge_is_a_switch_row(self):
        """Vorbedingung: Feature ``github`` an.

        Erwartung: ``label.nv-switch-row[data-nv-automerge-switch]`` enthält
        ``input[data-nv-field="github-auto-merge"]`` und einen beschreibenden
        Text zum automatischen Mergen.
        """
        self.open_settings()
        section = self.section("github")
        label = section.locator("label.nv-switch-row[data-nv-automerge-switch]")
        label.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            1, label.locator("input[data-nv-field='github-auto-merge']").count(),
            "Der Auto-Merge-Schalter liegt nicht in der Schalterzeile")
        self.assertRegex(
            label.inner_text() or "", r"merge",
            "Die Schalterzeile erklärt das automatische Mergen nicht: "
            + repr(label.inner_text()))
        self.assert_clean_page()

    def test_team_model_is_a_combobox(self):
        """Vorbedingung: Team-Sektion mit Agent ``tester``.

        Erwartung: Die Modellwahl ist keine ``select``-Liste mehr, sondern
        eine Combobox; der Wert-Hook ``data-nv-agent-model`` liegt am
        Combobox-Container.
        """
        self.open_settings()
        self.section("team")
        row = self.page.locator("[data-nv-team-agent='tester']")
        row.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            0, row.locator("select[data-nv-agent-model]").count(),
            "Die Modellwahl ist weiterhin eine select-Liste")
        container = row.locator("[data-nv-agent-model]")
        self.assertEqual(1, container.count(),
                         "Der Wert-Hook data-nv-agent-model fehlt am "
                         "Combobox-Container")
        is_combobox = container.evaluate(
            """node => node.hasAttribute('data-nv-combobox')
                 || !!node.querySelector("input[data-nv-combobox-input]")""")
        self.assertTrue(is_combobox,
                        "data-nv-agent-model liegt nicht an einer Combobox")
        self.assert_clean_page()

    def test_there_is_no_own_pause_section(self):
        """Vorbedingung: Einstellungen geöffnet.

        Erwartung: Die eigene Einstellungssektion „Pause nach Paket“ entfällt
        vollständig (``[data-nv-psection="pause"]`` existiert nicht); der
        Status steht im Überblick.
        """
        panel = self.open_settings()
        self.assertEqual(
            0, panel.locator("[data-nv-psection='pause']").count(),
            "Die eigene Pause-Sektion existiert weiterhin")
        self.assertNotRegex(
            panel.inner_text() or "", r"Pause nach Paket",
            "Die Einstellungen nennen weiterhin die Pause-Sektion")
        self.assert_clean_page()


if __name__ == "__main__":
    unittest.main()
