"""Browserabnahme F34, WP5: Projektdetail (Überblick, Arbeit, Beschreibung,
Einstellungen).

Ableitung ausschließlich aus ``docs/features/F34.md`` Abschnitt
„WP5 — Projektdetail“ (Überblick, Arbeit, Beschreibung, Einstellungsreihenfolge,
Einstellungen). Das Dashboard läuft als eigener Prozess auf einem freien
Loopback-Port mit isoliertem ``VIBE``/``HOME`` und einer opencode-Attrappe;
es gibt keine Modellaufrufe und keinen Netzzugriff außerhalb von Loopback.

Fixtures (echte Dateien/APIs, package_catalog = Paketkennungen aus
TICKETS.md/FEEDBACK.md, typisch ``F1``):

- ``TICKETS.md``: F1–F8 in den Zuständen offen (F1, F7, F8), erledigt (F2),
  BLOCKIERT (F3), WARTET AUF MERGE (F4), Draft (F5), In Progress (F6).
- ``FEEDBACK.md``: B7 (Art: Bug, offen), FB-1 (erledigt mit echtem Nachweis
  über Commit + ``Test:``-Zeile auf einem echten Git-Commit).
- ``sessions.json``: drei Sessions mit ``package_id`` (F1, F1, F7), Agenten
  (tester, helper), Zuständen (läuft, gestoppt), relativen Zeiten.
- ``project.env`` (GitHub-Fixture: Verknüpfung ``owner/name`` aktiv),
  ``AGENTS.md``, ``SPEC.md``, Home-Agents-Dateien (tester, helper).

Testfälle (Name, Vorbedingung, Aktion, Erwartung)
------------------------------------------------
``OverviewTest``
``test_autonomous_card_is_first_in_overview``
    Vorbedingung: Überblick geöffnet.
    Erwartung: ``section[data-nv-autonomous-card]`` ist das erste Element
    (y-Position vor den Kacheln), enthält ``input[data-nv-autonomous]``, eine
    Überschrift, die Erklärung („Beantwortet offene Rückfragen automatisch…“)
    und eine Zustands-Pille ``span[data-nv-autonomous-state]`` („aktiv“/„inaktiv“).
``test_tiles_match_the_contract_set``
    Vorbedingung: Pakete in den Zuständen offen, erledigt, BLOCKIERT, WARTET
    AUF MERGE, Draft, In Progress.
    Erwartung: genau die sechs Kacheln ``div[data-nv-tile]`` mit
    ``data-nv-tile`` ∈ {open, progress, blocked, waiting, done, draft}; die
    Entwurf-Kachel trägt eine ``title``-Erklärung; keine Kachel nennt
    „Feedback“ oder „ohne Nachweis“ (keine eigene Kacheln).
``test_state_card_names_the_last_package``
    Vorbedingung: Pakete vorhanden (B7 letztes Paket der effektiven Reihenfolge).
    Erwartung: ``section[data-nv-state-card]`` nennt Kennung + Titel + Zustand
    des letzten Arbeitspakets aus der effektiven Reihenfolge; danach
    „Letzter Commit“ und „Prüfung“.
``test_sessions_rows_and_resume_column``
    Vorbedingung: drei Session-Zeilen in ``div[data-nv-sessions]``.
    Erwartung: Zeilen nennen Paketkennung/Titel (aus ``package_id``,
    package_catalog), Agent, Zustand, relative Zeit; die technische ID steht
    nur in ``code.nv-session-id`` (gekürzt, ``title`` voll); die
    ``button[data-nv-action="session-resume"]`` rechts in einer Spalte mit
    gleicher x-Position.
``test_session_limit_is_only_in_settings``
    Vorbedingung: Überblick geöffnet.
    Erwartung: kein ``[data-nv-session-limit]`` im Überblick; in den
    Einstellungen ``input[data-nv-session-limit]`` +
    ``button[data-nv-action="session-limit-save"]`` (wird geprüft in
    SettingsTest).

``WorkTest``
``test_work_order_and_no_board``
    Vorbedingung: Arbeit geöffnet.
    Erwartung: Aktionsleiste → Filterleiste → Priorisierung → Liste in
    DOM-Reihenfolge; kein Board (``.nv-board``).
``test_filterbar_hooks_exist``
    Vorbedingung: Arbeit geöffnet.
    Erwartung: ``input[data-nv-work-search]``, Chips
    ``button[data-nv-work-kind`` in {all, package, bug, feedback}``,
    ``button[data-nv-work-hide-done]`` mit ``aria-pressed="true"``.
``test_integrated_list_and_kinds``
    Vorbedingung: Arbeit geöffnet, „Erledigte anzeigen“ aus.
    Erwartung: ``div.nv-ticket-list[data-nv-ticket-list]`` mit sichtbaren
    Karten ``article[data-nv-ticket]``/``article[data-nv-feedback-item]``,
    ``data-nv-kind`` ∈ {package, bug, feedback}; erledigtes Paket F2 als
    Karte gelistet, unsichtbar; keine separate Feedback-Sektion
    (``details[data-nv-feedback-box]``).
``test_work_search_finds_done_and_filters``
    Vorbedingung: F2 erledigt und ausgeblendet.
    Aktion: Suche „F2“ eingeben, leeren.
    Erwartung: F2 erscheint obwohl „Erledigte anzeigen“ aus ist; nach dem
    Leeren verschwindet es wieder, F1 erscheint erneut.
``test_hide_done_toggle``
    Vorbedingung: F2 erledigt.
    Erwartung: Standard ``aria-pressed="true"``, F2 unsichtbar, Label „Erledigte
    anzeigen (1)“; nach Klick ``aria-pressed="false"``, F2 sichtbar, Label
    „Erledigte ausblenden“.
``test_work_chips_filter_by_kind``
    Vorbedingung: Arbeit geöffnet.
    Aktion: Chip ``data-nv-work-kind="bug"`` drücken.
    Erwartung: nur ``article[data-nv-kind="bug"]`` (B7) sichtbar, Paket-Karten
    ausgeblendet; Chip „all“ stellt alle offenen wieder her.
``test_done_cards_have_no_delete_and_api_rejects_delete``
    Vorbedingung: Arbeit geöffnet.
    Aktion: API-Löschversuch auf das erledigte Paket F2 und das erledigte
    Feedback FB-1.
    Erwartung: F2-Karte hat keinen Löschen-Knopf; ``POST /api/ticket`` und
    ``POST /api/feedback`` liefern ``ok:false``; beide Einträge bleiben vorhanden.
``test_priority_strip_is_first_two_prioritized``
    Vorbedingung: ``POST /api/priority`` order „F5 F8“.
    Erwartung: Strip-Reihenfolge == effektive Ordnung, erste beiden F5, F8;
    manuell priorisierte erscheinen vor allen anderen offenen Einträgen.
``test_drag_and_drop_shows_marker_and_persists``
    Vorbedingung: order „F5 F8“.
    Aktion: Drag-Griff von F5 auf die Zeile von B7 ziehen.
    Erwartung: während des Ziehens sichtbare Einfügemarke
    (``div[data-nv-drop-marker]``); nach Drop POST ``/api/priority {action:"set"}``
    mit abweichender Permutation; Strip zeichnet neue Reihenfolge sofort;
    ``GET /api/priority`` liefert die neue Reihenfolge persistiert.
``test_drag_and_drop_moves_card_to_exact_target_position``
    Vorbedingung: explizite Priorität „F5 B7 F8 F1 F3 F4 F6 F7“.
    Aktion: Drag-Griff von F1 auf die Zeile von F8 ziehen.
    Erwartung: F1 steht an definierter Position (direkt vor F8); die
    Kennung davor (B7) und danach (F8) stimmen; exakte neue Reihenfolge
    sichtbar, Toast und persistiert; KEIN Voll-Neurender (DOM-Sentinel am
    Strip bleibt, echter Render-Zähler des Testgerüsts unverändert).
``test_arrows_reorder_and_save``
    Vorbedingung: order „F5 F8“.
    Aktion: ↓-Knopf der ersten Zeile klicken.
    Erwartung: ``POST /api/priority`` mit neuer Reihenfolge (F8 vor F5),
    sichtbar im Strip, Toast, ``GET /api/priority`` bestätigt sie; KEIN
    Voll-Neurender (DOM-Sentinel am Strip bleibt, echter Render-Zähler des
    Testgerüsts unverändert).
``test_card_rank_badges_follow_priority_action_without_rerender``
    Vorbedingung: order „F5 F8 B7“ (nur diese Karten tragen ``P1``–``P3``;
    F1 hat kein Badge).
    Aktion: ↓-Knopf der Zeile F5 klicken (Speicherweg wie nach Drag & Drop).
    Erwartung: Karten-Badges ``[data-nv-prio-badge]`` in
    ``div[data-nv-ticket-list]`` tragen die NEUE Reihenfolge
    (``P<index+1>`` gemäß Strip-Reihenfolge und persistierter
    ``/api/priority``-Order); Karten ohne Rang tragen kein Badge; der Strip
    zeigt dieselben Ränge; Toast bestätigt; KEIN Voll-Neurender (echter
    Render-Zähler unverändert).
``test_priority_reset``
    Vorbedingung: order „F5 F8“ (Badges vorhanden).
    Aktion: ``button[data-nv-priority-reset]`` klicken.
    Erwartung: POST mit ``order:""``; Badges verschwinden.
``test_back_to_top``
    Vorbedingung: Arbeit geöffnet.
    Aktion: bis zu 600 px Scrolltiefe scrollen.
    Erwartung: ``button[data-nv-back-to-top]`` erscheint; Klick scrollt zum
    Listenanfang (scrollY sinkt deutlich).

``AssistantTest``
``test_assistant_tab_and_headings``
    Vorbedingung: Projekt geöffnet.
    Erwartung: Tab „Beschreibung“, ``nav[data-nv-guide-nav]`` mit
    ``[data-nv-guide-step]``, Überschrift „1. Project goal“ im englischen
    Modus (Projektziel nicht deutsch).
``test_answer_fields_have_rows_ge_6``
    Vorbedingung: Beschreibung geöffnet.
    Erwartung: alle ``textarea[data-nv-answer-field]`` haben ``rows >= 6``.
``test_no_status_pills_ausgefuellt_or_open``
    Vorbedingung: Beschreibung geöffnet.
    Erwartung: keine ``span.nv-pill`` mit Text „ausgefüllt“/„open“; keine
    ``[data-nv-step-status]``.
``test_guide_nav_jumps_to_step``
    Vorbedingung: Beschreibung geöffnet.
    Aktion: ``button[data-nv-guide-step="ziel"]`` klicken.
    Erwartung: der Schritt wird sichtbar/in den Viewport gescrollt
    (``section[data-nv-guide-step-id="ziel"]`` im Viewport).

``SettingsTest``
``test_settings_section_order``
    Vorbedingung: Einstellungen geöffnet (generisches Projekt).
    Erwartung: Sektionen in der Reihenfolge agentsfile, basics, sandbox, team,
    github, writeaccess, session-limit (Fehlerbehebung nur für Android).
``test_agents_section_details_and_textareas``
    Vorbedingung: AGENTS.md vorhanden („Projektregel davor“/„Verwaltete Regel 4711“).
    Erwartung: ``details[data-nv-agents-section]`` offen; ``textarea[data-nv-agents-before]``
    und ``[data-nv-agents-after]`` haben ``rows >= 14``; ``pre[data-nv-agents-managed]``
    zeigt den verwalteten Block; ``select[data-nv-agents-backup]`` vorhanden.
``test_agents_backup_select_lists_backups``
    Vorbedingung: AGENTS.md-Sektion offen.
    Aktion: „Sicherung anlegen“ klicken (POST ``/api/agents_file`` action=backup).
    Erwartung: ``select[data-nv-agents-backup]`` listet die Sicherung mit
    Zeitstempel.
``test_agents_restore_confirmation_and_post``
    Vorbedingung: AGENTS.md-Sektion offen.
    Aktion: „Wiederherstellen“ klicken.
    Erwartung: ``div[data-nv-agents-restore-confirm]`` sichtbar (sichtbarer
    Sicherungsname); „Ja, wiederherstellen“ schickt POST ``/api/agents_file``
    action=restore.
``test_basics_type_help_and_confirm``
    Vorbedingung: Basics geöffnet, Projekt initialisiert.
    Erwartung: ``small[data-nv-type-help]`` nicht leer, „Projekt vorbereiten“
    fehlt; Typwechsel zeigt ``div[data-nv-type-confirm]``; „Ja, Typ ändern“
    POSTet ``/api/init``.
``test_sandbox_section_early_with_explanation``
    Vorbedingung: Einstellungen geöffnet.
    Erwartung: ``section[data-nv-psection='sandbox']`` nach basics, vor team;
    Erklärung („Sandbox“, Erlaubtes/Verbotenes) und
    ``[data-nv-field='sandbox-toggle']``/``[data-nv-field='sandbox-check']``.
``test_team_section_rows``
    Vorbedingung: Einstellungen geöffnet.
    Erwartung: ``section[data-nv-psection='team']`` mit
    ``[data-nv-team-agent]``-Zeilen für tester und helper.
``test_github_structure``
    Vorbedingung: Einstellungen geöffnet, GitHub-Verbindung konfiguriert.
    Erwartung: ``span[data-nv-github-token-state]`` (Token-Status-Pille,
    „Kein Token“ ohne Token); ``select[data-nv-github-push-branch]`` und
    ``select[data-nv-github-push-target]`` (keine Freitextfelder); „Fetch“
    im Synchronisieren-Block; Issues-Sync erklärt (``[data-nv-field=
    'github-issues-enabled']``).
``test_write_access_section``
    Vorbedingung: Einstellungen geöffnet.
    Erwartung: ``section[data-nv-psection='writeaccess']`` mit
    ``[data-nv-field='path']`` und ``[data-nv-action='rights-add']``.
``test_session_limit_section_and_save``
    Vorbedingung: Einstellungen geöffnet.
    Erwartung: ``input[data-nv-session-limit]`` + ``button[data-nv-action=
    'session-limit-save']``; Erklärung „gilt nur für dieses Projekt“; Save
    POSTet ``/api/sessions {action:"limit"}`` und ``GET /api/sessions?name=``
    liefert ``limit``.
``test_no_checks_or_opencode_server_hooks``
    Vorbedingung: Einstellungen geöffnet.
    Erwartung: keine ``[data-nv-doctor-row]`` (Prüfungen), keine
    ``[data-nv-sessions-limit]``/``[data-nv-limit-hint]`` (Alt-Hooks WP3).
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

# --- F34-Fixture: TICKETS.md ------------------------------------------------
# Zustände gemäß Backend/Vertrag: offen, erledigt, BLOCKIERT, WARTET AUF
# MERGE, Draft, In Progress. FB-1 ist erledigt (echter Nachweis auf einem
# echten Git-Commit); B7 ist offen (Art: Bug).
TICKETS = """# TICKETS — F34 Test

- [ ] F1 Erstes Paket
  Beschreibung: Erstes Paket eingegeben, wartet auf Umsetzung.

- [x] F2 Zweites Paket
  Beschreibung: Projekt als erledigt markiert.

- [ ] F3 Blockiertes Paket
  BLOCKIERT: externe Freigabe fehlt

- [ ] F4 Wartet auf Merge
  WARTET AUF MERGE: Wartet auf Merge-Freigabe.

- [ ] F5 Entwurf erstellt
  Status: draft

- [ ] F6 In Arbeit
  Status: In Progress

- [ ] F7 Dritte Überprüfung
  Beschreibung: Noch ein offenes Paket, um die Listenhöhe zu erhöhen.

- [ ] F8 Vierte Überprüfung
  Beschreibung: Ein weiteres offenes Paket, um die Listenhöhe zu erhöhen.
"""

# --- F34-Fixture: FEEDBACK.md (B7 offen, FB-1 erledigt mit Nachweis) ---------
FEEDBACK_PREFIX = """# FEEDBACK — F34 Test

- [ ] B7 Wunsch für die Oberfläche
  Beschreibung: Bitte größere Schaltflächen.
  Art: Bug
"""


def feedback_fixture(proof_hash):
    return FEEDBACK_PREFIX + """
- [x] FB-1 Absturz beim Start
  Beschreibung: Fenster bleibt leer.
  Commit: %s; Test: test_f34
""" % proof_hash


SPEC = """# SPEC — F34 Test

## Produktziel

Das Projekttest-Projekt der F34-Vertragsprüfung.

## Zielgruppe und Nutzung

Entwicklerinnen und Entwickler im Dashboard.

## Funktionsumfang

Überblick, Arbeit, Beschreibung, Einstellungen.

## Nicht im Umfang

Keine Auswertungen im Projektdetail.

## Zielumgebung

Dashboard auf Loopback.

## Qualität und Abnahme

Browser-Tests gegen das echte Dashboard.
"""

PROJECT_AGENTS = """Projektregel davor.

<!-- vibe:general-rules -->
Verwaltete Regel 4711.
<!-- /vibe:general-rules -->

Projektregel danach.
"""

GLOBAL_AGENTS_TEXT = "GLOBALE-REGEL-4711: gilt für alle Projekte.\n"

PROJECT_ENV = (
    "TYPE=generic\n"
    "GITHUB_ENABLED=1\n"
    'GITHUB_REPO="owner/name"\n'
    "GITHUB_BRANCH=main\n"
)

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

# --- F34-Fixture: sessions.json (drei Session-Zeilen) -----------------------
# package_catalog (Paketkennung -> Kurztitel aus FEEDBACK.md / TICKETS.md):
# F1 -> "Erstes Paket", F7 -> "Dritte Überprüfung" — die Werte werden per
# Fixture aus TICKETS.md/FEEDBACK.md abgeleitet.
# Reihenfolge: session_overview liefert jüngste zuerst — erste Zeile also
# den jüngsten Eintrag.
EXPECTED_TITLES = {"F1": "Erstes Paket", "F7": "Dritte Überprüfung"}
SESSION_ROWS = [
    # (session, agent, package_id, relativ-Zeit-Sekunden, state)
    ("ses_f34cc1b2c3d4e5f6c3", "tester", "F7", 5, "stopped"),
    ("ses_f34bb1b2c3d4e5f6b2", "helper", "F1", 60, "running"),
    ("ses_f34aa1b2c3d4e5f6a1", "tester", "F1", 120, "running"),
]


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def git(project, *argv):
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
    })
    return subprocess.run(
        ["git", "-C", str(project), *argv],
        capture_output=True, text=True, check=True, timeout=60, env=env)


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


class F34ProjectBrowserTest(unittest.TestCase):
    """Dashboard, Browser, Fixtures für Projektdetail (F34 WP5)."""

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

        # Echtes Git-Repository mit einem Commit: Beweis für das erledigte
        # Feedback FB-1 (Commit-Hash + ``Test:``-Zeile im Block).
        git(cls.project, "init", "-q", "-b", "main")
        git(cls.project, "commit", "--allow-empty", "-q", "-m", "F34 Test Commit")
        cls.proof_hash = git(cls.project, "rev-parse", "HEAD").stdout.strip()

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
        (self.log_dir / "autonomous.json").unlink(missing_ok=True)
        self.post_language("en")
        self.page_errors = []
        self.post_requests = []
        self.context = self.browser.new_context(
            viewport={"width": 1500, "height": 1000})
        self.context.add_init_script(
            "try { localStorage.setItem('nv-features', JSON.stringify("
            "{priority: true, sandbox: true, writeaccess: true, "
            "agentsfile: true, github: true})); } catch (error) {}")
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
        (self.project / "FEEDBACK.md").write_text(
            feedback_fixture(self.proof_hash), encoding="utf-8")
        (self.project / "SPEC.md").write_text(SPEC, encoding="utf-8")
        (self.project / "AGENTS.md").write_text(PROJECT_AGENTS, encoding="utf-8")
        (self.global_agents).write_text(GLOBAL_AGENTS_TEXT, encoding="utf-8")
        (self.project / ".vibe" / "project.env").write_text(
            PROJECT_ENV, encoding="utf-8")
        now = int(time.time())
        sessions = {
            "limit": 5,
            "sessions": [{
                "session": session,
                "project": os.path.realpath(str(self.project)),
                "name": PROJECT,
                "run_id": "",
                "agent": agent,
                "harness": "",
                "worktree_path": "",
                "package_id": package_id,
                "branch": "main",
                "first_seen": now - age - 10,
                "last_seen": now - age,
                "state": state,
            } for session, agent, package_id, age, state in SESSION_ROWS],
            "project_limits": {},
        }
        (self.log_dir / "sessions.json").write_text(
            json.dumps(sessions, ensure_ascii=False, indent=1) + "\n",
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
            except Exception:  # noqa: BLE001 - Poll darf kurze Fehler sehen
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

    def open_overview(self):
        return self.open_project()

    def open_work(self):
        self.open_project()
        panel = self.open_tab("work")
        self.page.locator("div.nv-ticket-list[data-nv-ticket-list]").first \
            .wait_for(state="visible", timeout=20000)
        self.page.locator("input[data-nv-work-search]").wait_for(
            state="visible", timeout=20000)
        self.page.locator("div[data-nv-priority-strip]").wait_for(
            state="visible", timeout=20000)
        self.install_render_counter()
        return panel

    def install_render_counter(self):
        """Umhüllt ``NV.render`` mit einem Zähler des TESTGERÜSTS.

        Das Produkt hat keinen eigenen Render-Zähler; dieser Helfer legt sich
        nach dem Laden vor ``NV.render`` (``bin/web/nova-core.js``) und erhöht
        ``window.__nvRenderCount`` bei jedem Aufruf. Ein unveränderter Zähler
        belegt damit, dass eine Prioritätsaktion keinen Voll-Neurender
        ausgelöst hat. Der Helfer ist idempotent; nach einem ``page.goto``
        muss er erneut laufen.
        """
        state = self.page.evaluate(
            """() => {
              if (window.__nvRenderCounterInstalled === true) {
                return {ok: true, already: true};
              }
              if (typeof NV === 'undefined'
                  || typeof NV.render !== 'function') {
                return {ok: false, reason: 'NV.render fehlt'};
              }
              var original = NV.render;
              window.__nvRenderCount = 0;
              window.__nvRenderCountOriginal = original;
              NV.render = function () {
                window.__nvRenderCount += 1;
                return original.apply(this, arguments);
              };
              window.__nvRenderCounterInstalled = true;
              return {
                ok: true,
                already: false,
                wrapped: NV.render !== window.__nvRenderCountOriginal,
                countsInBody: String(NV.render)
                  .indexOf('__nvRenderCount') !== -1
              };
            }""")
        self.assertTrue(
            state.get("ok"),
            "Der Render-Zähler konnte nicht installiert werden: %r"
            % (state.get("reason"),))
        if not state.get("already"):
            self.assertTrue(
                state.get("wrapped") and state.get("countsInBody"),
                "Die Umhüllung von NV.render zählt nicht wirklich: %r"
                % (state,))

    def nv_render_count(self):
        """Zählerstand des testseitig umhüllten ``NV.render``.

        Scheitert, wenn der Zähler fehlt — ein stiller Rückfall auf 0 würde
        eine Zusicherung vortäuschen, die nichts prüft.
        """
        state = self.page.evaluate(
            """() => ({
              installed: window.__nvRenderCounterInstalled === true,
              count: typeof window.__nvRenderCount === 'number'
                ? window.__nvRenderCount : null
            })""")
        self.assertTrue(
            state.get("installed"),
            "Der Render-Zähler ist nicht installiert; nv_render_count() "
            "kann keinen Voll-Neurender ausschließen")
        self.assertIsNotNone(
            state.get("count"),
            "Der Render-Zähler hat keinen numerischen Stand")
        return state["count"]

    def open_assistant(self):
        self.open_project()
        return self.open_tab("assistant")

    def open_settings(self):
        self.open_project()
        return self.open_tab("settings")

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

    def assert_clean_page(self):
        self.assertEqual(
            [], self.page_errors, "Die Projektansicht erzeugte JavaScript-Fehler")

    # ---------- F34-Vertrags-Hilfen ----------

    def card_selector(self, ident):
        return (f"div.nv-ticket-list [data-nv-ticket='{ident}'], "
                f"div.nv-ticket-list [data-nv-feedback-item='{ident}']")

    def visible_card_ids(self):
        ids = []
        for card in self.page.locator(
                "div.nv-ticket-list [data-nv-ticket], "
                "div.nv-ticket-list [data-nv-feedback-item]").all():
            if card.is_visible():
                ident = (card.get_attribute("data-nv-ticket")
                         or card.get_attribute("data-nv-feedback-item") or "")
                ids.append(ident)
        return ids

    def strip_ids(self):
        return self.page.locator(
            "div[data-nv-priority-strip] [data-nv-priority-id]").evaluate_all(
                "nodes => nodes.map("
                "node => node.getAttribute('data-nv-priority-id'))")

    def expected_effective_ids(self):
        """Effektive Prioritätsreihenfolge aus ``GET /api/priority``.

        Die UI (``nvpPriorityStrip``) nutzt ``open`` aus ``/api/project``:
        Einträge mit ``state == "erledigt"`` (F2) erscheinen nie. Die
        ``standard``-Liste des Backends kann ein erledigtes Paket ohne Nachweis
        (F2) als ``status:"offen"`` auflisten — es ist trotzdem ausgeschlossen.
        """
        data = self.api_json(f"/api/priority?name={PROJECT}")
        tickets, feedback = self.project_entries()
        done_ids = {str(entry.get("id") or "") for entry in tickets + feedback
                    if str(entry.get("state") or "") == "erledigt"}
        ids, seen = [], set()
        for entry in list(data.get("order") or []) + \
                list(data.get("standard") or []):
            entry_id = str(entry.get("id") or "")
            if not entry_id or entry_id in seen or entry_id in done_ids:
                continue
            if str(entry.get("status") or "") == "erledigt":
                continue
            ids.append(entry_id)
            seen.add(entry_id)
        return ids

    def set_priority(self, order):
        status, data = self.post_json(
            "/api/priority", {"name": PROJECT, "action": "set", "order": order})
        self.assertEqual(200, status, repr(data))
        self.assertTrue(bool(data.get("ok")), repr(data))

    def project_entries(self):
        data = self.api_json(f"/api/project?name={PROJECT}")
        return data.get("tickets") or [], data.get("feedback") or []

    def sessions_rows(self):
        data = self.api_json(f"/api/sessions?name={PROJECT}")
        return data.get("sessions") or []

    def state_label(self, state):
        """Zustands-Pille der Oberfläche (englischer Modus, siehe i18n.js)."""
        return {
            "offen": "Open",
            "WARTET AUF MERGE": "Waiting for merge",
            "BLOCKIERT": "Blocked",
            "In Progress": "In Progress",
            "Draft": "Draft",
            "ohne Nachweis": "Ohne Nachweis",
            "erledigt": "Done",
        }.get(state, "Open")


class OverviewTest(F34ProjectBrowserTest):
    def test_autonomous_card_is_first_in_overview(self):
        """Vorbedingung: Überblick geöffnet, kein Status gesetzt.

        Erwartung: ``section[data-nv-autonomous-card]`` ist das erste Element
        der Übersicht (y-Position vor den Kacheln), enthält
        ``input[data-nv-autonomous]``, eine Überschrift, die Erklärung
        („Beantwortet offene Rückfragen automatisch …“) und eine
        Zustands-Pille ``span[data-nv-autonomous-state]`` mit einem Wert.
        """
        self.open_overview()
        panel = self.page.locator("section[data-nv-ppanel='overview']")
        card = panel.locator("section[data-nv-autonomous-card]")
        card.wait_for(state="visible", timeout=20000)
        self.assertEqual(1, card.count(), "Die autonome Karte fehlt")
        tiles = panel.locator("div[data-nv-tile]")
        tiles.first.wait_for(state="visible", timeout=20000)
        card_box = card.bounding_box()
        tile_box = tiles.first.bounding_box()
        self.assertIsNotNone(card_box)
        self.assertIsNotNone(tile_box)
        self.assertLess(card_box["y"], tile_box["y"],
                        "Die autonome Karte steht nicht oben (vor den Kacheln)")
        self.assertEqual(1, card.locator("input[data-nv-autonomous]").count(),
                         "Der Schalter [data-nv-autonomous] fehlt")
        self.assertGreaterEqual(card.locator("h3").count(), 1,
                                "Der Kachel trägt keine Überschrift")
        text = card.inner_text() or ""
        self.assertRegex(
            text, re.compile(r"beantwortet|automatisch|rückfragen|questions",
                             re.I),
            "Die Karte trägt keine Erklärung (Beantwortung offener Rückfragen): "
            + repr(text))
        state = card.locator("span[data-nv-autonomous-state]")
        self.assertEqual(1, state.count(), "Die Zustands-Pille fehlt")
        self.assertTrue((state.inner_text() or "").strip(),
                        "Die Zustands-Pille ist leer")
        self.assert_clean_page()

    def test_tiles_match_the_contract_set(self):
        """Vorbedingung: Pakete in den Zuständen offen, erledigt, BLOCKIERT,
        WARTET AUF MERGE, Draft, In Progress.

        Erwartung: genau die sechs Kacheln ``div[data-nv-tile]`` mit
        ``data-nv-tile`` ∈ {open, progress, blocked, waiting, done, draft};
        die Entwurf-Kachel trägt eine ``title``-Erklärung; keine Kachel
        nennt „Feedback“ oder „ohne Nachweis“.
        """
        panel = self.open_overview()
        tiles = panel.locator("div[data-nv-tile]")
        tiles.first.wait_for(state="visible", timeout=20000)
        values = sorted(tiles.evaluate_all(
            "nodes => nodes.map(node => node.getAttribute('data-nv-tile'))"))
        self.assertEqual(
            ["blocked", "done", "draft", "open", "progress", "waiting"],
            values, "Die Kacheln (data-nv-tile) sind nicht genau die sechs "
            "offenen/erledigten/Draft-Kacheln: " + repr(values))
        draft = panel.locator("div[data-nv-tile][data-nv-tile='draft']")
        self.assertTrue(
            (draft.first.get_attribute("title") or "").strip(),
            "Die Entwurf-Kachel trägt keine title-Erklärung")
        for index in range(tiles.count()):
            text = (tiles.nth(index).inner_text() or "").lower()
            self.assertNotRegex(
                text, r"feedback|ohne nachweis",
                "Eine Kachel nennt Feedback oder „ohne Nachweis“: " + repr(text))
        self.assert_clean_page()

    def test_state_card_names_the_last_package(self):
        """Vorbedingung: Pakete vorhanden; B7 ist das letzte Paket der
        effektiven Reihenfolge (ohne manuelle Priorisierung).

        Erwartung: ``section[data-nv-state-card]`` nennt Kennung + Titel +
        Zustand des letzten Arbeitspakets („B7“, „Wunsch für die Oberfläche“,
        „Offen“); danach „Letzter Commit“ und „Prüfung“.
        """
        panel = self.open_overview()
        tickets, feedback = self.project_entries()
        expected_last = self.expected_effective_ids()[-1]
        self.assertEqual("B7", expected_last,
                         "Vorbedingung: das letzte Paket der effektiven "
                         "Reihenfolge ist B7, erhalten: " + repr(expected_last))
        match = next(
            (entry for entry in tickets + feedback
             if str(entry.get("id") or "") == expected_last), None)
        self.assertIsNotNone(match, "Vorbedingung: B7 existiert")
        state_card = panel.locator("section[data-nv-state-card]")
        state_card.wait_for(state="visible", timeout=20000)
        card_text = state_card.inner_text() or ""
        self.assertIn(expected_last, card_text,
                      "Der Kennung des letzten Pakets fehlt in der „Zustand“-Karte: "
                      + repr(card_text))
        self.assertIn(str(match.get("title") or ""), card_text,
                      "Der Titel des letzten Pakets fehlt in der „Zustand“-Karte")
        self.assertIn(self.state_label(str(match.get("state") or "")), card_text,
                      "Der Zustand des letzten Pakets fehlt in der „Zustand“-Karte")
        # Vertragsbegriffe (englischer Modus): Überschrift, letzter Commit,
        # Prüfstatus — alle in der „Zustand“-Karte.
        for fragment in ("State", "Last work package", "Last commit",
                         "Verification"):
            self.assertIn(fragment, card_text,
                          f"Der Fragment {fragment!r} fehlt in der „Zustand“-Karte")
        self.assert_clean_page()

    def test_sessions_rows_and_resume_column(self):
        """Vorbedingung: ``sessions.json`` mit drei Session-Zeilen
        (package_id F1/F1/F7, Agent tester/helper/tester).

        Erwartung: Zeilen in ``div[data-nv-sessions]`` nennen Paketkennung +
        Titel (aus package_id), Agent, Zustand, relative Zeit; die technische
        ID steht nur in ``code.nv-session-id`` (gekürzt, ``title`` voll);
        ``button[data-nv-action="session-resume"]`` rechts in einer Spalte
        mit gleicher x-Position.
        """
        self.open_overview()
        rows = self.page.locator("div[data-nv-sessions] div.nv-session-row")
        rows.first.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(rows.count(), 3,
                                "Vorbedingung: drei Session-Zeilen, "
                                "erhalten: " + repr(rows.count()))
        api_rows = {
            str(row.get("session") or ""): row
            for row in self.sessions_rows()}
        for index, (session, agent, package_id, age, state) in enumerate(
                SESSION_ROWS):
            row = rows.nth(index)
            text = row.inner_text() or ""
            self.assertIn(package_id, text,
                          f"Zeile {index}: Paketkennung {package_id} fehlt: "
                          + repr(text))
            title = EXPECTED_TITLES[package_id]
            self.assertIn(title, text,
                          f"Zeile {index}: Pakettitel {title} fehlt: " + repr(text))
            self.assertIn(agent, text,
                          f"Zeile {index}: Agent {agent} fehlt: " + repr(text))
            self.assertRegex(
                text, re.compile(r"(?i)(\d+\s*(min|stunde)|gerade eben|just now)",
                                 re.I),
                f"Zeile {index}: keine relative Zeit angezeigt: " + repr(text))
            state_label = api_rows.get(session, {}).get("state_label") or ""
            if state_label:
                self.assertIn(state_label, text,
                              f"Zeile {index}: Zustand {state_label} fehlt: "
                              + repr(text))
            self.assertNotIn(session, text,
                             f"Zeile {index}: die technische Session-ID steht "
                             "im Zeilentext: " + repr(text))
            code = row.locator("code.nv-session-id")
            self.assertEqual(1, code.count(),
                             f"Zeile {index}: code.nv-session-id fehlt")
            self.assertEqual(session, code.first.get_attribute("title"),
                             f"Zeile {index}: der title der Session-ID ist nicht voll")
            self.assertLess(
                len(code.first.inner_text() or ""), len(session),
                f"Zeile {index}: die technische ID ist nicht gekürzt")
            resume = row.locator("button[data-nv-action='session-resume']")
            self.assertEqual(1, resume.count(),
                             f"Zeile {index}: button[data-nv-action=session-resume] "
                             "fehlt")
            self.assertRegex(
                resume.first.inner_text() or "",
                re.compile(r"forsetz|resume|continue", re.I),
                f"Zeile {index}: Der Fortsetzen-Knopf hat kein Label")
        resumes = self.page.locator("button[data-nv-action='session-resume']")
        xs = [resume.bounding_box()["x"] for resume in resumes.all()]
        self.assertTrue(
            xs and max(xs) - min(xs) < 1,
            "Die Fortsetzen-Knöpfe sind nicht in einer Spalte mit gleicher "
            "x-Position: " + repr(xs))
        self.assert_clean_page()

    def test_session_limit_is_only_in_settings(self):
        """Vorbedingung: Überblick geöffnet.

        Erwartung: kein ``[data-nv-session-limit]`` im Überblick; in den
        Einstellungen ``input[data-nv-session-limit]`` +
        ``button[data-nv-action="session-limit-save"]`` (SettingsTest).
        """
        self.open_overview()
        self.assertEqual(
            0, self.page.locator("section[data-nv-ppanel='overview'] "
                                 "[data-nv-session-limit]").count(),
            "Das Session-Limit ist im Überblick sichtbar (wurde WP3 eingeführt)")
        self.assert_clean_page()


class WorkTest(F34ProjectBrowserTest):
    def test_work_order_and_no_board(self):
        """Vorbedingung: Arbeit geöffnet.

        Erwartung: Aktionsleiste → Filterleiste → Priorisierung → Liste in
        DOM-Reihenfolge; kein Board (``.nv-board``).
        """
        panel = self.open_work()
        self.assert_follows(
            [
                "section[data-nv-ppanel='work'] [data-nv-action='new-package']",
                "section[data-nv-ppanel='work'] [data-nv-action='new-bug']",
                "section[data-nv-ppanel='work'] [data-nv-action='new-feedback']",
                "section[data-nv-ppanel='work'] div.nv-filter-bar[data-nv-filter-bar]",
                "section[data-nv-ppanel='work'] div[data-nv-priority-strip]",
                "section[data-nv-ppanel='work'] div.nv-ticket-list[data-nv-ticket-list]",
            ],
            "Die Arbeitsbereiche stehen nicht in der Reihenfolge "
            "Aktionsleiste → Filterleiste → Priorisierung → Liste")
        self.assertEqual(
            0, panel.locator(".nv-board").count(),
            "Ein Board (.nv-board) ist in der Arbeit vorhanden")
        self.assert_clean_page()

    def test_filterbar_hooks_exist(self):
        """Vorbedingung: Arbeit geöffnet.

        Erwartung: ``input[data-nv-work-search]``, Chips
        ``button[data-nv-work-kind]`` in {all, package, bug, feedback},
        ``button[data-nv-work-hide-done]`` mit ``aria-pressed="true"``.
        """
        panel = self.open_work()
        search = panel.locator("input[data-nv-work-search]")
        search.wait_for(state="visible", timeout=20000)
        self.assertEqual(1, search.count(),
                         "input[data-nv-work-search] fehlt")
        chips = panel.locator(
            "div[data-nv-work-kinds] button[data-nv-work-kind]")
        self.assertEqual(
            ["all", "package", "bug", "feedback"],
            chips.evaluate_all(
                "nodes => nodes.map(node => node.getAttribute('data-nv-work-kind'))"),
            "Die Typ-Chips haben nicht die Werte all|package|bug|feedback")
        toggle = panel.locator("button[data-nv-work-hide-done]")
        self.assertEqual(1, toggle.count(),
                         "button[data-nv-work-hide-done] fehlt")
        self.assertEqual(
            "true", toggle.get_attribute("aria-pressed"),
            "„Erledigte anzeigen“ ist nicht standardmäßig aktiv")
        self.assert_clean_page()

    def test_integrated_list_and_kinds(self):
        """Vorbedingung: Arbeit geöffnet, „Erledigte anzeigen“ aus
        (F2 erledigtes Paket, FB-1 erledigtes Feedback).

        Erwartung: ``div.nv-ticket-list[data-nv-ticket-list]`` mit sichtbaren
        Karten ``article[data-nv-ticket]``/``article[data-nv-feedback-item]``
        mit ``data-nv-kind`` ∈ {package, bug, feedback}; erledigtes F2 als
        Karte gelistet, unsichtbar; keine separate Feedback-Sektion
        (``details[data-nv-feedback-box]``).
        """
        panel = self.open_work()
        expected = self.visible_card_ids()
        self.assertEqual(
            ["F1", "F3", "F4", "F5", "F6", "F7", "F8", "B7"], expected,
            "Alle offenen Einträge (Pakete, Bugs) erscheinen in der "
            "integrierten Liste (erledigte sind ausgeblendet)")
        f2 = self.page.locator("div.nv-ticket-list [data-nv-ticket='F2']")
        self.assertEqual(1, f2.count(),
                         "Das erledigte Paket F2 ist nicht als Karte gelistet")
        self.assertFalse(f2.is_visible(),
                         "F2 ist ohne „Erledigte anzeigen“ sichtbar")
        fb1 = self.page.locator("div.nv-ticket-list [data-nv-feedback-item='FB-1']")
        self.assertEqual(1, fb1.count(),
                         "Das erledigte Feedback FB-1 ist nicht als Karte gelistet")
        kinds = {ident: self.page.locator(self.card_selector(ident))
                 .first.get_attribute("data-nv-kind") or ""
                 for ident in ["F1", "F3", "F4", "F5", "F6", "F7", "F8",
                               "B7", "FB-1"]}
        self.assertEqual(
            {"F1": "package", "F3": "package", "F4": "package", "F5": "package",
             "F6": "package", "F7": "package", "F8": "package", "B7": "bug",
             "FB-1": "feedback"},
            kinds, "Die Karten nennen data-nv-kind package|bug|feedback")
        self.assertEqual(
            0, self.page.locator("details[data-nv-feedback-box]").count(),
            "Es gibt eine separate Feedback-Sektion (details[data-nv-feedback-box])")
        self.assert_clean_page()

    def test_work_search_finds_done_and_filters(self):
        """Vorbedingung: F2 ist erledigt und ausgeblendet.

        Aktion: ``input[data-nv-work-search]`` mit „F2“ füllen, danach leeren.

        Erwartung: Ein erledigtes Paket mit passendem Suchbegriff ist sichtbar,
        obwohl „Erledigte anzeigen“ aus ist; nach dem Leeren erscheint es
        wieder nicht, F1 bleibt sichtbar.
        """
        panel = self.open_work()
        search = panel.locator("input[data-nv-work-search]")
        f2 = self.page.locator("div.nv-ticket-list [data-nv-ticket='F2']")
        f1 = self.page.locator("div.nv-ticket-list [data-nv-ticket='F1']")
        self.assertFalse(f2.is_visible(), "Vorbedingung: F2 ist ausgeblendet")
        search.fill("F2")
        self.wait_until(
            lambda: f2.is_visible(), timeout=15,
            message="Das erledigte Paket F2 erscheint nicht bei Suche „F2“, "
                    "obwohl „Erledigte anzeigen“ aus ist")
        self.wait_until(
            lambda: not f1.is_visible(), timeout=15,
            message="Die Suche „F2“ lässt das nicht passende Paket F1 sichtbar")
        self.assertEqual(["F2"], self.visible_card_ids())
        search.fill("")
        self.wait_until(
            lambda: f1.is_visible(), timeout=15,
            message="Nach dem Leeren der Suche erscheint F1 nicht wieder")
        self.wait_until(
            lambda: not f2.is_visible(), timeout=15,
            message="F2 ist nach dem Leeren der Suche sichtbar (Erledigt "
                    "sollte ausgeblendet sein)")
        self.assert_clean_page()

    def test_hide_done_toggle(self):
        """Vorbedingung: F2 erledigt (ausgeblendet).

        Erwartung: Standard ``aria-pressed="true"``, F2 unsichtbar, Label
        „Erledigte anzeigen (1)“; nach Klick ``aria-pressed="false"``, F2
        sichtbar, Label „Erledigte ausblenden“.
        """
        panel = self.open_work()
        toggle = panel.locator("button[data-nv-work-hide-done]")
        toggle.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            "true", toggle.get_attribute("aria-pressed"),
            "„Erledigte anzeigen“ ist nicht standardmäßig aktiv")
        f2 = self.page.locator("div.nv-ticket-list [data-nv-ticket='F2']")
        self.assertFalse(f2.is_visible(),
                         "Die erledigte Karte F2 ist trotz Standardfilter sichtbar")
        label = toggle.inner_text() or ""
        self.assertRegex(
            label, re.compile(r"(?i)show done|erledigte anzeigen"),
            "Der Knopf bietet nicht „Erledigte anzeigen“ an: " + repr(label))
        self.assertIn("1", label,
                      "Der Knopf meldet nicht die Anzahl 1: " + repr(label))
        toggle.click()
        self.wait_until(
            lambda: toggle.get_attribute("aria-pressed") == "false",
            timeout=15,
            message="Der Klick setzt aria-pressed nicht auf false")
        self.wait_until(lambda: f2.is_visible(), timeout=15,
                        message="Die erledigte Karte F2 erscheint nicht")
        label = toggle.inner_text() or ""
        self.assertRegex(
            label, re.compile(r"(?i)hide done|erledigte ausblenden"),
            "Der Knopf bietet nach dem Einblenden kein „Erledigte ausblenden“ "
            "an: " + repr(label))
        self.assert_clean_page()

    def test_work_chips_filter_by_kind(self):
        """Vorbedingung: Arbeit geöffnet.

        Aktion: Chip ``button[data-nv-work-kind="bug"]`` drücken.

        Erwartung: nur ``article[data-nv-kind="bug"]`` (B7) sichtbar,
        Paket-/Feedback-Karten ausgeblendet; Chip „all“ stellt alle offenen
        wieder her.
        """
        panel = self.open_work()
        bug_chip = panel.locator(
            "div[data-nv-work-kinds] button[data-nv-work-kind='bug']")
        bug_chip.click()
        b7 = self.page.locator("div.nv-ticket-list [data-nv-feedback-item='B7']")
        f1 = self.page.locator("div.nv-ticket-list [data-nv-ticket='F1']")
        self.wait_until(
            lambda: b7.is_visible() and not f1.is_visible(), timeout=15,
            message="Chip „bug“: B7 ist nicht sichtbar oder F1 bleibt sichtbar "
                    "(Karten tragen data-nv-kind nicht auf article-Ebene?)")
        self.assertEqual([card.get_attribute("data-nv-ticket")
                          or card.get_attribute("data-nv-feedback-item")
                          for card in self.page.locator(
                              "div.nv-ticket-list [data-nv-ticket], "
                              "div.nv-ticket-list [data-nv-feedback-item]").all()
                          if card.is_visible()], ["B7"],
                         "Nach Chip „bug“ sind nicht nur die Bugs sichtbar")
        all_chip = panel.locator(
            "div[data-nv-work-kinds] button[data-nv-work-kind='all']")
        all_chip.click()
        self.wait_until(
            lambda: f1.is_visible() and b7.is_visible(), timeout=15,
            message="Chip „all“ stellt die offenen Einträge nicht wieder her")
        self.assert_clean_page()

    def test_done_cards_have_no_delete_and_api_rejects_delete(self):
        """Vorbedingung: Arbeit geöffnet (F2 erledigt, FB-1 erledigt).

        Aktion: API-Löschversuch auf das erledigte Paket F2 und das erledigte
        Feedback FB-1.

        Erwartung: Die F2-Karte hat keinen Löschen-Knopf (Edit gesperrt);
        ``POST /api/ticket`` {action:delete,id:F2} und ``POST /api/feedback``
        {action:delete,id:FB-1} liefern ``ok:false``; beide Einträge bleiben
        in ``/api/project`` vorhanden.
        """
        panel = self.open_work()
        f2 = self.page.locator("div.nv-ticket-list [data-nv-ticket='F2']")
        self.assertEqual(1, f2.count(), "Das erledigte Paket F2 ist nicht als Karte gelistet")
        self.assertEqual(
            0, f2.locator("button[data-nv-action='ticket-delete']").count(),
            "Die erledigte Karte hat einen Löschen-Knopf (Backend-Schutz fehlt)")
        self.assertEqual(
            0, f2.locator("button[data-nv-action='ticket-edit']").count(),
            "Die erledigte Karte hat einen Bearbeiten-Knopf")
        status, data = self.post_json(
            "/api/ticket", {"name": PROJECT, "action": "delete", "id": "F2"})
        # Vertrag (WP7): ``ok:false`` + Meldung (HTTP-Status kann 400 sein,
        # die Anwendungs-Antwort ist ``ok:false``).
        self.assertFalse(data.get("ok"),
                         "Der API-Löschversuch auf das erledigte Paket F2 "
                         "liefert ok:true: " + repr(data))
        self.assertRegex(
            str(data.get("message") or ""), r"Abgeschlossen",
            "Der API-Löschversuch auf F2 liefert keine Nachweis-Meldung: "
            + repr(data))
        status, data = self.post_json(
            "/api/feedback",
            {"name": PROJECT, "action": "delete", "id": "FB-1"})
        self.assertFalse(data.get("ok"),
                         "Der API-Löschversuch auf das erledigte Feedback FB-1 "
                         "liefert ok:true: " + repr(data))
        self.wait_api(
            f"/api/project?name={PROJECT}",
            lambda data: any(entry.get("id") == "F2" for entry in data.get("tickets") or [])
            and any(entry.get("id") == "FB-1" for entry in data.get("feedback") or []),
            message="F2/FB-1 wurden durch den Löschversuch gelöscht")
        self.assert_clean_page()

    def test_priority_strip_is_first_two_prioritized(self):
        """Vorbedingung: ``POST /api/priority`` order „F5 F8“.

        Erwartung: Strip-Reihenfolge == effektive Ordnung
        (``expected_effective_ids``), erste beide F5, F8; manuell priorisierte
        erscheinen vor den Standardreihenfolge-Einträgen.
        """
        self.set_priority("F5 F8")
        self.open_work()
        self.page.locator("div[data-nv-priority-strip]").wait_for(
            state="visible", timeout=20000)
        expected = self.expected_effective_ids()
        self.assertEqual(
            ["F5", "F8"], expected[:2],
            "Vorbedingung: F5/F8 leiten sich als erste, priorisierte Einträge "
            "ab: " + repr(expected))
        self.wait_until(
            lambda: self.strip_ids() == expected, timeout=20,
            message="Die Strip-Reihenfolge passt nicht zur effektiven Ordnung: "
                    + repr(self.strip_ids()) + " erwartet: " + repr(expected))
        self.assertIn("F1", expected, "Vorbedingung: F1 in der Ordnung")
        f5_card = self.page.locator("div.nv-ticket-list [data-nv-ticket='F5']")
        f5_card.wait_for(state="visible", timeout=15000)
        self.assertEqual(
            "P1", f5_card.locator("span[data-nv-prio-badge]").first
            .inner_text(),
            "Die priorisierte Karte F5 trägt kein P1-Badge")
        self.assert_clean_page()

    def test_drag_and_drop_shows_marker_and_persists(self):
        """Vorbedingung: order „F5 F8“.

        Aktion: Drag-Griff von F5 auf die Zeile von B7 ziehen.

        Erwartung: während des Ziehens sichtbare Einfügemarke
        (``div[data-nv-drop-marker]``); nach Drop POST ``/api/priority``
        {action:"set"} mit abweichender Permutation; Strip zeichnet die neue
        Reihenfolge sofort; ``GET /api/priority`` liefert sie persistiert.
        """
        self.set_priority("F5 F8")
        self.open_work()
        self.page.locator("div[data-nv-priority-strip]").wait_for(
            state="visible", timeout=20000)
        before = self.strip_ids()
        handle = self.page.locator(
            "div[data-nv-priority-strip] [data-nv-priority-id='F5'] "
            "button[data-nv-drag-handle]")
        target = self.page.locator(
            "div[data-nv-priority-strip] [data-nv-priority-id='B7'] "
            "button[data-nv-drag-handle]")
        handle.wait_for(state="visible", timeout=20000)
        handle_box = handle.bounding_box()
        target_box = target.bounding_box()
        self.assertIsNotNone(handle_box)
        self.assertIsNotNone(target_box)
        # 1) Echter Drag-Start auf dem Drag-Griff (dragstart → Geister-Zeile).
        #    Chromium startet den Drag erst beim ersten Move nach mouse.down.
        self.page.mouse.move(handle_box["x"] + handle_box["width"] / 2,
                             handle_box["y"] + handle_box["height"] / 2)
        self.page.mouse.down()
        self.page.mouse.move(target_box["x"] + target_box["width"] / 2,
                             target_box["y"] + target_box["height"] / 2)
        ghost = self.page.locator("[data-nv-drag-ghost]")
        self.wait_until(
            lambda: ghost.count() == 1 and ghost.is_visible(), timeout=15,
            message="Der Drag-Griff bricht ab: keine sichtbare Geisterzeile "
                    "(div[data-nv-drag-ghost]) beim Ziehen")
        # 2) Einfügemarke während des Ziehens. Headless-Chromium feuert
        #    während manuellen Ziehen kein dragover; wir fahren es auf dem
        #    Strip nach, um den Produkt-Pfad (Live-Einfügemarke) zu üben —
        #    browserseitig wird dragover während eines Drags gefeuert.
        self.page.evaluate(
            """(y) => {
              const strip = document.querySelector(
                'div[data-nv-priority-strip]');
              const dataTransfer = new DataTransfer();
              strip.dispatchEvent(new DragEvent('dragover', {
                bubbles: true, cancelable: true, clientY: y,
                dataTransfer: dataTransfer}));
            }""", target_box["y"] + target_box["height"] / 2)
        marker = self.page.locator(
            "div[data-nv-priority-strip] div[data-nv-drop-marker]")
        self.wait_until(
            lambda: marker.count() == 1 and marker.is_visible(), timeout=15,
            message="Während des Ziehens ist keine sichtbare Einfügemarke "
                    "(div[data-nv-drop-marker]) vorhanden")
        # 3) Drop durch einen echten Playwright-Drag (Chromium feuert
        #    dragover + drop während des Drag-Vorgangs).
        self.page.mouse.up()
        handle.drag_to(target, force=True)
        self.wait_until(
            lambda: any(payload.get("action") == "set"
                        for payload in self.posts_to("/api/priority")),
            timeout=20,
            message="Der Drop speichert nicht über POST /api/priority "
                    "{action:'set'}: " + repr(self.posts_to("/api/priority")))
        posted = [payload for payload in self.posts_to("/api/priority")
                  if payload.get("action") == "set"][-1]
        posted_order = [part for part in str(posted.get("order") or "").split()
                        if part]
        self.assertNotEqual(
            before, posted_order,
            "Der Drop hat die Strip-Reihenfolge nicht verändert: " + repr(posted_order))
        self.assertIn("F5", posted_order, "Die neue Reihenfolge enthält F5 nicht: "
                                         + repr(posted_order))
        self.wait_api(
            f"/api/priority?name={PROJECT}",
            lambda data: [str(entry.get("id"))
                          for entry in (data.get("order") or [])] == posted_order,
            message="Die per Drop gespeicherte Reihenfolge ist nicht "
                    "persistiert: " + repr(posted_order))
        self.wait_until(
            lambda: self.strip_ids() == posted_order, timeout=15,
            message="Der Strip zeichnet die neue Reihenfolge nicht sofort: "
                    + repr(self.strip_ids()))
        self.assert_clean_page()

    def test_drag_and_drop_moves_card_to_exact_target_position(self):
        """Vorbedingung: explizite Priorität „F5 B7 F8 F1 F3 F4 F6 F7“ über alle
        offenen Einträge.
        Aktion: Drag-Griff von F1 auf die Zeile von F8 ziehen.
        Erwartung: F1 steht an definierter Position (direkt vor F8); die
        Kennung davor (B7) und danach (F8) stimmen; die exakte neue
        Reihenfolge wird per POST und ``GET /api/priority`` persistiert.
        """
        self.set_priority("F5 B7 F8 F1 F3 F4 F6 F7")
        self.open_work()
        self.page.locator("div[data-nv-priority-strip]").wait_for(
            state="visible", timeout=20000)
        expected_before = ["F5", "B7", "F8", "F1", "F3", "F4", "F6", "F7"]
        self.wait_until(
            lambda: self.strip_ids() == expected_before, timeout=20,
            message="Die definierte Startreihenfolge der Strip-Liste fehlt: "
                    + repr(self.strip_ids()))
        # Kein-Voll-Neurender-Messung: DOM-Sentinel am Strip (überlebt nur,
        # wenn das Element nicht ersetzt wird) plus echter Render-Zähler
        # (testseitig umhülltes NV.render, siehe install_render_counter).
        strip = self.page.locator("div[data-nv-priority-strip]")
        strip.evaluate(
            "node => node.setAttribute('data-nv-f34-no-rerender', '1')")
        render_before = self.nv_render_count()
        source = self.page.locator(
            "div[data-nv-priority-strip] [data-nv-priority-id='F1'] "
            "button[data-nv-drag-handle]")
        target = self.page.locator(
            "div[data-nv-priority-strip] [data-nv-priority-id='F8'] "
            "button[data-nv-drag-handle]")
        source.wait_for(state="visible", timeout=20000)
        target.wait_for(state="visible", timeout=20000)
        source_box = source.bounding_box()
        target_box = target.bounding_box()
        self.assertIsNotNone(source_box)
        self.assertIsNotNone(target_box)
        self.page.mouse.move(source_box["x"] + source_box["width"] / 2,
                             source_box["y"] + source_box["height"] / 2)
        self.page.mouse.down()
        self.page.mouse.move(target_box["x"] + target_box["width"] / 2,
                             target_box["y"] + target_box["height"] / 2)
        ghost = self.page.locator("[data-nv-drag-ghost]")
        self.wait_until(
            lambda: ghost.count() == 1 and ghost.is_visible(), timeout=15,
            message="Der Drag-Start bricht ab: keine sichtbare Geisterzeile "
                    "(div[data-nv-drag-ghost]) beim Ziehen")
        # 2) Einfügemarke während des Ziehens. Headless-Chromium feuert
        #    während manuellen Ziehen kein dragover; wir fahren es auf dem
        #    Strip nach, um den Produkt-Pfad (Live-Einfügemarke) zu üben —
        #    browserseitig wird dragover während eines Drags gefeuert.
        self.page.evaluate(
            """(y) => {
              const strip = document.querySelector(
                'div[data-nv-priority-strip]');
              const dataTransfer = new DataTransfer();
              strip.dispatchEvent(new DragEvent('dragover', {
                bubbles: true, cancelable: true, clientY: y,
                dataTransfer: dataTransfer}));
            }""", target_box["y"] + target_box["height"] / 2)
        marker = self.page.locator(
            "div[data-nv-priority-strip] div[data-nv-drop-marker]")
        self.wait_until(
            lambda: marker.count() == 1 and marker.is_visible(), timeout=15,
            message="Während des Ziehens ist keine sichtbare Einfügemarke "
                    "(div[data-nv-drop-marker]) vorhanden")
        self.page.mouse.up()
        source.drag_to(target, force=True)
        self.wait_until(
            lambda: any(payload.get("action") == "set"
                        for payload in self.posts_to("/api/priority")),
            timeout=20,
            message="Der Drop speichert nicht über POST /api/priority "
                    "{action:'set'}: " + repr(self.posts_to("/api/priority")))
        posted = [payload for payload in self.posts_to("/api/priority")
                  if payload.get("action") == "set"][-1]
        posted_order = [part for part in str(posted.get("order") or "").split()
                        if part]
        expected_after = ["F5", "B7", "F1", "F8", "F3", "F4", "F6", "F7"]
        self.assertEqual(
            expected_after, posted_order,
            "Der Drop hat die exakte Zielposition nicht respektiert: "
            "erwartet " + repr(expected_after) + ", erhalten: " + repr(posted_order))
        self.wait_api(
            f"/api/priority?name={PROJECT}",
            lambda data: [str(entry.get("id"))
                          for entry in (data.get("order") or [])] == posted_order,
            message="Die per Drop gespeicherte Reihenfolge ist nicht persistiert: "
                    + repr(posted_order))
        self.wait_until(
            lambda: self.strip_ids() == posted_order, timeout=15,
            message="Der Strip zeichnet die exakte neue Reihenfolge nicht: "
                    + repr(self.strip_ids()))
        self.wait_until(
            lambda: re.search(
                r"priority saved|priorisierung gespeichert",
                self.toast_text(), re.I) is not None, timeout=20,
            message="Der Drop bestätigt das Speichern nicht: "
                    + repr(self.toast_text()))
        self.assertEqual(
            "1", strip.get_attribute("data-nv-f34-no-rerender"),
            "Der Drop hat den Priorisierungs-Strip ersetzt "
            "(Voll-Neurender statt lokalem Neuzeichnen)")
        self.assertEqual(
            render_before, self.nv_render_count(),
            "Der Drop vollneu-rendered (NV.render wurde während des "
            "Speicherns aufgerufen)")
        self.assert_clean_page()

    def test_arrows_reorder_and_save(self):
        """Vorbedingung: order „F5 F8“.

        Aktion: ↓-Knopf der ersten Zeile (F5) klicken.

        Erwartung: ``POST /api/priority`` mit neuer Reihenfolge (F8 vor F5);
        ``GET /api/priority`` bestätigt die neue Reihenfolge.
        """
        self.set_priority("F5 F8")
        self.open_work()
        self.page.locator("div[data-nv-priority-strip]").wait_for(
            state="visible", timeout=20000)
        strip = self.page.locator("div[data-nv-priority-strip]")
        strip.evaluate(
            "node => node.setAttribute('data-nv-f34-no-rerender', '1')")
        render_before = self.nv_render_count()
        down = self.page.locator(
            "div[data-nv-priority-strip] [data-nv-priority-id='F5'] "
            "button[data-nv-action='priority-down']")
        self.assertEqual(1, down.count(), "↓-Knopf für F5 fehlt")
        down.click()
        self.wait_until(
            lambda: any(payload.get("action") == "set"
                        for payload in self.posts_to("/api/priority")),
            timeout=20,
            message="Der ↓-Knopf speichert nicht über POST /api/priority "
                    "{action:'set'}: " + repr(self.posts_to("/api/priority")))
        posted = [payload for payload in self.posts_to("/api/priority")
                  if payload.get("action") == "set"][-1]
        posted_order = [part for part in str(posted.get("order") or "").split()
                        if part]
        self.assertEqual(
            ["F8", "F5"], posted_order[:2],
            "Der ↓-Knopf speichert F8 vor F5 nicht: " + repr(posted_order))
        self.wait_api(
            f"/api/priority?name={PROJECT}",
            lambda data: [str(entry.get("id"))
                          for entry in (data.get("order") or [])] == posted_order,
            message="Die per ↓ gespeicherte Reihenfolge ist nicht persistiert: "
                    + repr(posted_order))
        self.wait_until(
            lambda: self.strip_ids()[:2] == ["F8", "F5"], timeout=15,
            message="Der Strip zeigt nach ↓ nicht sichtbar F8 vor F5: "
                    + repr(self.strip_ids()))
        self.wait_until(
            lambda: re.search(
                r"priority saved|priorisierung gespeichert",
                self.toast_text(), re.I) is not None, timeout=20,
            message="Der ↓-Knopf bestätigt das Speichern nicht: "
                    + repr(self.toast_text()))
        self.assertEqual(
            "1", strip.get_attribute("data-nv-f34-no-rerender"),
            "Der ↓-Knopf hat den Priorisierungs-Strip ersetzt "
            "(Voll-Neurender statt lokalem Neuzeichnen)")
        self.assertEqual(
            render_before, self.nv_render_count(),
            "Der ↓-Knopf vollneu-rendered (NV.render wurde während des "
            "Speicherns aufgerufen)")
        self.assert_clean_page()

    def test_card_rank_badges_follow_priority_action_without_rerender(self):
        """Vorbedingung: order „F5 F8 B7“: nur diese Karten tragen ``P1``–``P3``,
        F1 trägt kein Badge.

        Aktion: ↓-Knopf der Zeile F5 klicken (Speicherweg wie nach Drag & Drop).

        Erwartung: die Karten-Badges ``span[data-nv-prio-badge]`` der
        Arbeitskarten in ``div[data-nv-ticket-list]`` tragen die NEUE
        Reihenfolge (``P<index+1>`` gemäß Strip-Reihenfolge und persistierter
        ``/api/priority``-Order); Karten ohne Rang tragen kein Badge; der Strip
        zeigt dieselben Ränge; Toast bestätigt das Speichern; KEIN
        Voll-Neurender (echter Render-Zähler unverändert).
        """
        self.set_priority("F5 F8 B7")
        self.open_work()
        strip = self.page.locator("div[data-nv-priority-strip]")
        strip.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: self.strip_ids()[:3] == ["F5", "F8", "B7"], timeout=20,
            message="Vorbedingung: der Strip beginnt nicht mit F5, F8, B7: "
                    + repr(self.strip_ids()))

        def card_badges():
            """Rang-Badge je Arbeitskarte (Kennung -> ``P<n>`` oder ``None``)."""
            return self.page.evaluate(
                """() => {
                  const out = {};
                  document.querySelectorAll(
                    'div[data-nv-ticket-list] [data-nv-ticket], '
                    + 'div[data-nv-ticket-list] [data-nv-feedback-item]'
                  ).forEach(card => {
                    const id = card.getAttribute('data-nv-ticket')
                      || card.getAttribute('data-nv-feedback-item');
                    const badge = card.querySelector(
                      'span[data-nv-prio-badge]');
                    out[id] = badge ? badge.textContent.trim() : null;
                  });
                  return out;
                }""")

        def strip_ranks():
            """Rang-Präfix je Strip-Zeile (Kennung -> Text der Zeile)."""
            return self.page.evaluate(
                """() => {
                  const out = {};
                  document.querySelectorAll(
                    'div[data-nv-priority-strip] [data-nv-priority-id]'
                  ).forEach(row => {
                    const id = row.getAttribute('data-nv-priority-id');
                    const label = row.querySelector('.nv-priority-label');
                    out[id] = label ? label.textContent.trim() : '';
                  });
                  return out;
                }""")

        before = card_badges()
        self.assertEqual(
            {"F5": "P1", "F8": "P2", "B7": "P3"},
            {ident: before.get(ident) for ident in ("F5", "F8", "B7")},
            "Vorbedingung: die priorisierten Karten tragen nicht P1–P3: "
            + repr(before))
        self.assertIsNone(
            before.get("F1"),
            "Vorbedingung: F1 hat ohne Rang ein Badge: " + repr(before))

        render_before = self.nv_render_count()
        down = self.page.locator(
            "div[data-nv-priority-strip] [data-nv-priority-id='F5'] "
            "button[data-nv-action='priority-down']")
        self.assertEqual(1, down.count(), "↓-Knopf für F5 fehlt")
        down.click()
        self.wait_until(
            lambda: any(payload.get("action") == "set"
                        for payload in self.posts_to("/api/priority")),
            timeout=20,
            message="Der ↓-Knopf speichert nicht über POST /api/priority "
                    "{action:'set'}: " + repr(self.posts_to("/api/priority")))
        posted = [payload for payload in self.posts_to("/api/priority")
                  if payload.get("action") == "set"][-1]
        posted_order = [part for part in str(posted.get("order") or "").split()
                        if part]
        self.assertEqual(
            ["F8", "F5", "B7"], posted_order[:3],
            "Der ↓-Knopf speichert die neue Reihenfolge nicht: "
            + repr(posted_order))
        self.wait_api(
            f"/api/priority?name={PROJECT}",
            lambda data: [str(entry.get("id"))
                          for entry in (data.get("order") or [])] == posted_order,
            message="Die per ↓ gespeicherte Reihenfolge ist nicht persistiert: "
                    + repr(posted_order))
        self.wait_until(
            lambda: self.strip_ids() == posted_order, timeout=15,
            message="Der Strip zeichnet die neue Reihenfolge nicht sofort: "
                    + repr(self.strip_ids()))

        expected_badges = {ident: "P" + str(index + 1)
                           for index, ident in enumerate(posted_order)}
        observed = card_badges()
        deadline = time.time() + 15
        while time.time() < deadline:
            observed = card_badges()
            if all(observed.get(ident) == badge
                   for ident, badge in expected_badges.items()):
                break
            self.page.wait_for_timeout(100)
        self.assertEqual(
            expected_badges,
            {ident: observed.get(ident) for ident in expected_badges},
            "Die Karten-Badges folgen der neuen Reihenfolge nicht "
            "(erwartet ``P<index+1>`` gemäß Strip und persistierter Order): "
            + repr(observed))
        unbewertet = {ident: badge for ident, badge in observed.items()
                      if ident not in expected_badges and badge}
        self.assertEqual(
            {}, unbewertet,
            "Karten ohne Rang tragen ein Badge: " + repr(unbewertet))
        ranks = strip_ranks()
        for index, ident in enumerate(posted_order):
            self.assertTrue(
                str(ranks.get(ident) or "").startswith("P" + str(index + 1) + " "),
                "Der Strip zeigt für " + ident + " nicht P" + str(index + 1)
                + ": " + repr(ranks.get(ident)))
        self.wait_until(
            lambda: re.search(
                r"priority saved|priorisierung gespeichert",
                self.toast_text(), re.I) is not None, timeout=20,
            message="Der ↓-Knopf bestätigt das Speichern nicht: "
                    + repr(self.toast_text()))
        self.assertEqual(
            render_before, self.nv_render_count(),
            "Die Rang-Aktualisierung vollneu-rendered (NV.render wurde "
            "während des Speicherns aufgerufen)")
        self.assert_clean_page()

    def test_priority_reset(self):
        """Vorbedingung: order „F5 F8“ (Badges vorhanden).

        Aktion: ``button[data-nv-priority-reset]`` klicken.

        Erwartung: POST ``/api/priority`` mit ``order:""``; Badges
        (``span[data-nv-prio-badge]``) verschwinden.
        """
        self.set_priority("F5 F8")
        self.open_work()
        strip = self.page.locator("div[data-nv-priority-strip]")
        strip.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(
            self.page.locator("span[data-nv-prio-badge]").count(), 2,
            "Vorbedingung: die priorisierten Einträge zeigen keine Badges")
        reset = strip.locator("button[data-nv-priority-reset]")
        self.assertEqual(1, reset.count(), "Der Zurücksetzen-Knopf fehlt")
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

    def test_back_to_top(self):
        """Vorbedingung: Arbeit geöffnet.

        Aktion: bis zu 600 px Scrolltiefe scrollen.

        Erwartung: ``button[data-nv-back-to-top]`` erscheint; Klick scrollt
        zum Listenanfang (scrollY sinkt deutlich).
        """
        panel = self.open_work()
        button = panel.locator("button[data-nv-back-to-top]")
        self.assertEqual(1, button.count(),
                         "Der Nach-oben-Knopf [data-nv-back-to-top] fehlt")
        self.assertFalse(button.is_visible(),
                         "Der Nach-oben-Knopf ist ohne Scrolltiefe sichtbar")
        self.page.evaluate(
            "() => window.scrollTo(0, Math.max(document.body.scrollHeight, "
            "1200))")
        self.wait_until(
            lambda: self.page.evaluate(
                "() => Math.max(window.scrollY || 0, "
                "document.documentElement.scrollTop || 0) >= 600"),
            timeout=20,
            message="Die Seite ist nicht in die benötigte Tiefe scrollbar")
        self.wait_until(
            lambda: button.is_visible(), timeout=15,
            message="Der Nach-oben-Knopf erscheint nicht ab 600px Scrolltiefe")
        before = self.page.evaluate(
            "() => Math.max(window.scrollY || 0, "
            "document.documentElement.scrollTop || 0)")
        button.click()
        self.wait_until(
            lambda: self.page.evaluate(
                "() => Math.max(window.scrollY || 0, "
                "document.documentElement.scrollTop || 0) < %s" % (before - 100,)),
            timeout=20,
            message="Das Scrollen zum Listenanfang ging nicht zurück (scrollY "
                    "hat nicht um mindestens 100px abgesunken)")
        self.assert_clean_page()


class AssistantTest(F34ProjectBrowserTest):
    def test_assistant_tab_and_headings(self):
        """Vorbedingung: Projekt geöffnet.

        Erwartung: Tab „Beschreibung“ (label ~/beschreibung|description/i),
        ``nav[data-nv-guide-nav]`` mit mindestens einem
        ``[data-nv-guide-step]``; Überschrift „1. Project goal“ im englischen
        Modus (keine deutsche „Projektziel“-Überschrift).
        """
        panel = self.open_assistant()
        tab = self.page.locator("[data-nv-ptab='assistant']")
        self.assertRegex(tab.inner_text() or "",
                         re.compile(r"beschreibung|description", re.I),
                         "Der Tab heißt nicht „Beschreibung“: "
                         + repr(tab.inner_text()))
        nav = panel.locator("nav[data-nv-guide-nav]")
        nav.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(
            panel.locator("nav[data-nv-guide-nav] [data-nv-guide-step]").count(),
            1, "Es fehlen Schritt-Knöpfe in nav[data-nv-guide-nav]")
        headings = panel.locator("h4").all_inner_texts()
        self.assertTrue(
            any(re.search(r"^1\.\s*Project goal$", text.strip())
                for text in headings),
            "Der erste Schritt heißt im englischen Modus „1. Project goal“: "
            + repr(headings))
        self.assertNotIn("Projektziel", panel.inner_text() or "",
                         "Eine deutsche „Projektziel“-Überschrift bleibt im "
                         "englischen Modus")
        self.assert_clean_page()

    def test_answer_fields_have_rows_ge_6(self):
        """Vorbedingung: Beschreibung geöffnet.

        Erwartung: alle ``textarea[data-nv-answer-field]`` haben ``rows >= 6``.
        """
        panel = self.open_assistant()
        fields = panel.locator("textarea[data-nv-answer-field]")
        fields.first.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(fields.count(), 1, "Es fehlen Antwortfelder")
        for index in range(fields.count()):
            rows = fields.nth(index).evaluate(
                "node => parseInt(node.getAttribute('rows') || '0', 10) || "
                "node.rows")
            self.assertGreaterEqual(
                rows, 6, f"Antwortfeld {index} hat weniger als 6 rows")
        self.assert_clean_page()

    def test_no_status_pills_ausgefuellt_or_open(self):
        """Vorbedingung: Beschreibung geöffnet.

        Erwartung: keine ``span.nv-pill`` mit Text „ausgefüllt“/„open“;
        keine ``[data-nv-step-status]``.
        """
        panel = self.open_assistant()
        pills = panel.locator("span.nv-pill").all()
        for pill in pills:
            text = (pill.inner_text() or "").strip()
            self.assertFalse(
                re.search(r"(?i)ausgefüllt|open", text),
                "Unerlaubte Status-Pille: " + repr(text))
        self.assertEqual(
            0, panel.locator("[data-nv-step-status]").count(),
            "Es gibt noch die F33-Status-Pillen [data-nv-step-status]")
        self.assert_clean_page()

    def test_guide_nav_jumps_to_step(self):
        """Vorbedingung: Beschreibung geöffnet.

        Aktion: ``button[data-nv-guide-step="ziel"]`` klicken.

        Erwartung: der Schritt ``section[data-nv-guide-step-id="ziel"]`` wird
        sichtbar (in den Viewport gescrollt).
        """
        panel = self.open_assistant()
        nav = panel.locator("nav[data-nv-guide-nav]")
        first = nav.locator("[data-nv-guide-step]").first
        first.wait_for(state="visible", timeout=20000)
        first.click()
        self.wait_until(
            lambda: self.page.evaluate(
                """id => {
                  const el = document.querySelector(
                    'section[data-nv-guide-step-id="' + id + '"]');
                  if (!el) return false;
                  const rect = el.getBoundingClientRect();
                  return rect.bottom > 0 && rect.top < window.innerHeight;
                }""", "ziel"),
            timeout=20,
            message="Der Klick auf den Schritt-Knopf springt nicht zum Schritt")
        self.assert_clean_page()


class SettingsTest(F34ProjectBrowserTest):
    def test_settings_section_order(self):
        """Vorbedingung: Einstellungen geöffnet (generisches Projekt).

        Erwartung: Sektionen in der Reihenfolge agentsfile, basics, sandbox,
        team, github, writeaccess, session-limit (Fehlerbehebung nur Android).
        """
        panel = self.open_settings()
        order = panel.evaluate(
            """node => Array.from(node.querySelectorAll(
                'section[data-nv-psection]'))
                 .map(section => section.getAttribute('data-nv-psection'))""")
        self.assertEqual(
            ["agentsfile", "basics", "sandbox", "team", "github",
             "writeaccess", "session-limit"], order,
            "Die Einstellungen sind nicht in der vertraglichen Reihenfolge: "
            + repr(order))
        self.assert_clean_page()

    def test_agents_section_details_and_textareas(self):
        """Vorbedingung: AGENTS.md vorhanden („Projektregel davor“/„Verwaltete
        Regel 4711“).

        Erwartung: ``details[data-nv-agents-section]`` offen (Standard);
        ``textarea[data-nv-agents-before]``/``[data-nv-agents-after]`` haben
        ``rows >= 14``; ``pre[data-nv-agents-managed]`` zeigt den verwalteten
        Block; ``select[data-nv-agents-backup]`` vorhanden.
        """
        panel = self.open_settings()
        details = panel.locator("details[data-nv-agents-section]")
        details.wait_for(state="visible", timeout=20000)
        self.assertTrue(details.evaluate("node => node.open"),
                        "Die AGENTS.md-Sektion ist nicht offen (Standard offen)")
        before = details.locator("textarea[data-nv-agents-before]")
        after = details.locator("textarea[data-nv-agents-after]")
        self.assertEqual(1, before.count(), "textarea[data-nv-agents-before] fehlt")
        self.assertEqual(1, after.count(), "textarea[data-nv-agents-after] fehlt")
        for textarea in (before, after):
            rows = textarea.evaluate(
                "node => parseInt(node.getAttribute('rows') || '0', 10) || node.rows")
            self.assertGreaterEqual(rows, 14,
                                    "textarea[data-nv-agents-*] hat weniger als 14 rows")
        self.assertIn("Projektregel davor", before.input_value(),
                      "Der freie Teil davor ist nicht vorbelegt: "
                      + repr(before.input_value()))
        managed = details.locator("pre[data-nv-agents-managed]")
        self.assertIn("Verwaltete Regel 4711", managed.inner_text(),
                      "Der verwaltete Block wird nicht angezeigt")
        backup = details.locator("select[data-nv-agents-backup]")
        self.assertEqual(1, backup.count(), "select[data-nv-agents-backup] fehlt")
        self.assert_clean_page()

    def test_agents_backup_select_lists_backups(self):
        """Vorbedingung: AGENTS.md-Sektion offen.

        Aktion: „Sicherung anlegen“ klicken (POST ``/api/agents_file``
        action=backup).

        Erwartung: ``select[data-nv-agents-backup]`` listet die angelegte
        Sicherung (Zeitstempel).
        """
        panel = self.open_settings()
        details = panel.locator("details[data-nv-agents-section]")
        backup = details.locator("select[data-nv-agents-backup]")
        backup.wait_for(state="visible", timeout=20000)
        backup_button = details.locator(
            "button[data-nv-action='agents-file-backup']")
        self.assertEqual(1, backup_button.count(), "Der Sicherungs-Knopf fehlt")
        backup_button.click()
        self.wait_until(
            lambda: any(payload.get("action") == "backup"
                        for payload in self.posts_to("/api/agents_file")),
            timeout=20,
            message="Der Klick speichert nicht über POST /api/agents_file "
                    "{action: backup}: " + repr(self.posts_to("/api/agents_file")))
        options = backup.locator("option").all_inner_texts()
        timestamps = [text for text in options
                      if re.search(r"\d{8}-\d{6}-\d{6}", text)]
        self.assertTrue(
            timestamps,
            "Der select[data-nv-agents-backup] listet keine Sicherungen mit "
            "Zeitstempel: " + repr(options))
        self.assert_clean_page()

    def test_agents_restore_confirmation_and_post(self):
        """Vorbedingung: AGENTS.md-Sektion offen.

        Aktion: „Wiederherstellen“ klicken; bestätigen.

        Erwartung: ``div[data-nv-agents-restore-confirm]`` sichtbar mit
        sichtbarem Sicherungsnamen; „Ja, wiederherstellen“ schickt POST
        ``/api/agents_file`` {action:restore}.
        """
        panel = self.open_settings()
        details = panel.locator("details[data-nv-agents-section]")
        restore = details.locator(
            "button[data-nv-action='agents-file-restore']")
        self.assertEqual(1, restore.count(), "Der Wiederherstellen-Knopf fehlt")
        confirm = details.locator("div[data-nv-agents-restore-confirm]")
        self.assertEqual(1, confirm.count(),
                         "Die Inline-Bestätigung der Wiederherstellung fehlt")
        self.assertFalse(confirm.is_visible(),
                         "Die Bestätigung ist ohne Klick sichtbar")
        restore.click()
        confirm.wait_for(state="visible", timeout=15000)
        self.assertIn("wiederherstellen", (confirm.inner_text() or "").lower(),
                      "Der Bestätigungstext nennt das Wiederherstellen nicht: "
                      + repr(confirm.inner_text()))
        self.assertEqual(
            0, len([payload for payload in self.posts_to("/api/agents_file")
                    if payload.get("action") == "restore"]),
            "Die Wiederherstellung wurde ohne Bestätigung ausgeführt")
        self.page.locator("details[data-nv-agents-section] "
                          "button[data-nv-action='agents-file-restore-confirm']") \
            .click()
        self.wait_until(
            lambda: any(payload.get("action") == "restore"
                        for payload in self.posts_to("/api/agents_file")),
            timeout=20,
            message="Die Bestätigung sendet keinen /api/agents_file-POST "
                    "action=restore: " + repr(self.posts_to("/api/agents_file")))
        self.assert_clean_page()

    def test_basics_type_help_and_confirm(self):
        """Vorbedingung: Basics geöffnet, Projekt initialisiert (``.vibe/project.env``).

        Erwartung: ``small[data-nv-type-help]`` nicht leer; „Projekt
        vorbereiten“ fehlt; Typwechsel zeigt ``div[data-nv-type-confirm]``;
        „Ja, Typ ändern“ POSTet ``/api/init``.
        """
        panel = self.open_settings()
        section = panel.locator("section[data-nv-psection='basics']")
        section.wait_for(state="visible", timeout=20000)
        type_help = section.locator("small[data-nv-type-help]")
        self.assertEqual(1, type_help.count(), "small[data-nv-type-help] fehlt")
        self.assertTrue((type_help.inner_text() or "").strip(),
                        "Die Typ-Erklärung ist leer")
        self.assertEqual(
            0, section.locator("[data-nv-action='init']").count(),
            "Der Knopf „Projekt vorbereiten“ ist für ein vorhandenes Projekt "
            "unexpected sichtbar")
        type_select = section.locator("select[data-nv-field='type']")
        type_select.wait_for(state="visible", timeout=20000)
        type_select.select_option("python")
        confirm = section.locator("div[data-nv-type-confirm]")
        self.wait_until(
            lambda: confirm.is_visible(), timeout=15000,
            message="Das Typwechsel-Bestätigungs-Div ist ohne Änderung nicht sichtbar")
        self.assertRegex(type_help.inner_text() or "", re.compile(r"python", re.I),
                         "Die Typ-Erklärung ändert sich nicht mit dem Typ")
        section.locator("button[data-nv-action='type-confirm-yes']").click()
        self.wait_until(
            lambda: any(payload.get("type") == "python"
                        for payload in self.posts_to("/api/init")),
            timeout=20,
            message="Der Bestätigung sendet keinen /api/init-POST mit type=python: "
                    + repr(self.posts_to("/api/init")))
        self.assert_clean_page()

    def test_sandbox_section_early_with_explanation(self):
        """Vorbedingung: Einstellungen geöffnet.

        Erwartung: ``section[data-nv-psection='sandbox']`` nach Basics und
        vor Team; Erklärung („Sandbox“ + erlaubte/verbotene Punkte);
        ``[data-nv-field='sandbox-toggle']`` und ``[data-nv-field='sandbox-check']``.
        """
        panel = self.open_settings()
        section = panel.locator("section[data-nv-psection='sandbox']")
        section.wait_for(state="visible", timeout=20000)
        self.assertRegex(section.inner_text() or "", re.compile(r"sandbox"),
                         "Die Sandbox-Erklärung fehlt")
        self.assertEqual(
            1, section.locator("[data-nv-action='sandbox-toggle']").count(),
            "Der Sandbox-Schalter [data-nv-action=sandbox-toggle] fehlt")
        self.assertEqual(
            1, section.locator("[data-nv-action='sandbox-check']").count(),
            "Der Prüfen-Knopf [data-nv-action=sandbox-check] fehlt")
        self.assert_clean_page()

    def test_team_section_rows(self):
        """Vorbedingung: Einstellungen geöffnet (Agents tester/helper in HOME).

        Erwartung: ``section[data-nv-psection='team']`` mit
        ``[data-nv-team-agent]``-Zeilen für tester und helper.
        """
        panel = self.open_settings()
        section = panel.locator("section[data-nv-psection='team']")
        section.wait_for(state="visible", timeout=20000)
        agents = section.evaluate(
            """node => Array.from(node.querySelectorAll('[data-nv-team-agent]'))
                 .map(row => row.getAttribute('data-nv-team-agent'))""")
        self.assertIn("tester", agents, "Vorbedingung: Agent tester fehlt")
        self.assertIn("helper", agents, "Vorbedingung: Agent helper fehlt")
        self.assert_clean_page()

    def test_github_structure(self):
        """Vorbedingung: Einstellungen geöffnet, GitHub-Verbindung
        (``owner/name``) konfiguriert.

        Erwartung: ``span[data-nv-github-token-state]`` (Token-Status-Pille,
        „Kein Token“ ohne Token); ``select[data-nv-github-push-branch]`` und
        ``select[data-nv-github-push-target]`` als selects; „Fetch“ im
        Synchronisieren-Block (``[data-nv-action='github-fetch']``);
        Issues-Sync erklärt (``[data-nv-field='github-issues-enabled']``).
        """
        panel = self.open_settings()
        section = panel.locator("section[data-nv-psection='github']")
        section.wait_for(state="visible", timeout=20000)
        token_state = section.locator("span[data-nv-github-token-state]")
        self.assertEqual(1, token_state.count(),
                         "Die Token-Status-Pille [data-nv-github-token-state] fehlt")
        self.assertTrue((token_state.inner_text() or "").strip(),
                        "Der Token-Status ist leer")
        for hook in ("select[data-nv-github-push-branch]",
                     "select[data-nv-github-push-target]"):
            select = section.locator(hook)
            self.assertEqual(1, select.count(),
                             f"{hook} fehlt")
            self.assertEqual("SELECT", select.first.evaluate(
                "node => node.tagName"), f"{hook} ist kein select")
        for hook in ("[data-nv-action='github-pull']",
                     "[data-nv-action='github-fetch']",
                     "[data-nv-action='github-push']"):
            self.assertEqual(1, section.locator(hook).count(),
                             f"Der Synchronisieren-Block hat keinen {hook}")
        issues = section.locator("[data-nv-field='github-issues-enabled']")
        self.assertEqual(1, issues.count(),
                         "Der Issues-Sync-Schalter fehlt")
        self.assertRegex(section.inner_text() or "", re.compile(r"issues"),
                         "Die GitHub-Issues werden nicht erklärt")
        self.assert_clean_page()

    def test_write_access_section(self):
        """Vorbedingung: Einstellungen geöffnet.

        Erwartung: ``section[data-nv-psection='writeaccess']`` mit
        ``[data-nv-field='path']`` und ``[data-nv-action='rights-add']``.
        """
        panel = self.open_settings()
        section = panel.locator("section[data-nv-psection='writeaccess']")
        section.wait_for(state="visible", timeout=20000)
        self.assertEqual(1, section.locator("[data-nv-field='path']").count(),
                         "[data-nv-field=path] fehlt")
        self.assertEqual(
            1, section.locator("[data-nv-action='rights-add']").count(),
            "[data-nv-action=rights-add] fehlt")
        self.assert_clean_page()

    def test_session_limit_section_and_save(self):
        """Vorbedingung: Einstellungen geöffnet.

        Erwartung: ``input[data-nv-session-limit]`` +
        ``button[data-nv-action="session-limit-save"]``; Erklärung „gilt nur
        für dieses Projekt“; Save POSTet ``/api/sessions {action:"limit"}``;
        ``GET /api/sessions?name=`` liefert ``limit``.
        """
        panel = self.open_settings()
        section = panel.locator("section[data-nv-psection='session-limit']")
        section.wait_for(state="visible", timeout=20000)
        limit_input = section.locator("input[data-nv-session-limit]")
        save = section.locator("button[data-nv-action='session-limit-save']")
        self.assertEqual(1, limit_input.count(),
                         "input[data-nv-session-limit] fehlt")
        self.assertEqual(1, save.count(),
                         "button[data-nv-action=session-limit-save] fehlt")
        self.assertRegex(
            section.inner_text() or "",
            re.compile(r"(?i)applies to this project only|gilt nur für dieses Projekt"),
            "Die Erklärung „gilt nur für dieses Projekt“ fehlt")
        limit_input.fill("5")
        save.click()
        self.wait_until(
            lambda: any(payload.get("action") == "limit" and payload.get("limit") == 5
                        for payload in self.posts_to("/api/sessions")),
            timeout=20,
            message="Der Speichern-Knopf POSTet nicht über /api/sessions "
                    "action=limit limit=5: " + repr(self.posts_to("/api/sessions")))
        self.wait_api(
            f"/api/sessions?name={PROJECT}",
            lambda data: int(data.get("limit") or 0) == 5,
            message="Das Projektlimit ist nicht gespeichert")
        self.assert_clean_page()

    def test_no_checks_or_opencode_server_hooks(self):
        """Vorbedingung: Einstellungen geöffnet.

        Erwartung: keine ``[data-nv-doctor-row]`` (Prüfungen), keine
        ``[data-nv-sessions-limit]``/``[data-nv-limit-hint]`` (WP3-Hooks).
        """
        panel = self.open_settings()
        self.assertEqual(0, panel.locator("[data-nv-doctor-row]").count(),
                         "Die Prüfungen (data-nv-doctor-row) sind vorhanden")
        self.assertEqual(0, panel.locator("[data-nv-sessions-limit]").count(),
                         "Die WP3-Hook [data-nv-sessions-limit] ist vorhanden")
        self.assertEqual(0, panel.locator("[data-nv-limit-hint]").count(),
                         "Der WP3-Hook [data-nv-limit-hint] ist vorhanden")
        self.assert_clean_page()


if __name__ == "__main__":
    unittest.main()
