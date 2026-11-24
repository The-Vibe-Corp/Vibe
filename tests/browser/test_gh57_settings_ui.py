"""Browserabnahme GH-57: Überarbeitete Settings-Ansicht (Shell, Edit-View, Sektionen).

Ableitung AUSSCHLIESSLICH aus ``docs/features/GH-57.md`` (verbindlicher Vertrag:
„Globale Anforderungen", „Gemeinsame Komponenten", „Sektionsspezifikation (Hooks)"),
dem Ticket ``TICKETS.md`` GH-57 (Akzeptanzkriterien) und ``SPEC.md`` (Sprache der
Web-Oberfläche ist Englisch; Modellprofile; MCP). Bewusst NICHT abgeleitet aus einem
Implementierungs-Diff (Rotphase: es existiert keines).

Das echte Dashboard läuft als eigener Prozess auf einem freien Loopback-Port mit
isoliertem VIBE/HOME/VIBE_STATE/VIBE_RUNTIME (VIBE_NO_CONTAINER=1, VIBE_* und TMUX
aus der Umgebung geräumt), einer opencode-HTTP-Attrappe auf VIBE_OPENCODE_PORT und
einer opencode-STUB-Binary auf dem PATH (Muster ``tests/browser/test_f34_settings_ui.py``
und ``tests/browser/test_agents_ui.py``). Der STUB liefert für ``opencode models`` die
Zeilen aus ``$GH57_FAKE_MODELS_FILE``; damit liefert
``POST /api/agents {action:'refresh_models'}`` echte Modelldaten und Cache/Stand
(``<Zustand>/models-cache.json``) sind testbar. Kein Netzzugriff außerhalb Loopback.

Hinweis zur Entstehung: Die Fälle wurden vom unabhängigen Test-Agenten abgeleitet
und geschrieben; dessen Sitzung hatte keine Schreib-/Ausführungsrechte, daher wurde
der Inhalt vom Koordinator unverändert abgelegt und die Rotphase vom Koordinator
ausgeführt (Ergebnis unten im Abschnitt „ROT-PHASE“).

Testfälle (Name, Vorbedingung, Aktion, Erwartung)
------------------------------------------------
ShellAndEditViewTest
``test_mobile_nav_visible_below_header_and_horizontally_scrollable``
    Vorbedingung: mobil 390×844, Einstellungen offen (alle Features an).
    Aktion: Kopfzeile, Menü und Sektionsanker messen, dann 300 px scrollen.
    Erwartung: ``nav[data-nv-settings-nav]`` sichtbar und horizontal scrollbar
    (scrollWidth > clientWidth, overflow-x auto/scroll); vor und nach dem
    Scrollen keine Überlappung mit der sticky Kopfzeile
    (``nav.top >= header.bottom - 2``); Sektionsanker tragen
    ``scroll-margin-top > 0`` (unterhalb der Leiste).
``test_mobile_page_has_no_horizontal_scrolling``
    Vorbedingung: mobil 390×844, Einstellungen offen, alle Feature-Sektionen an.
    Aktion: Dokumentbreite messen.
    Erwartung: ``documentElement.scrollWidth <= innerWidth + 2`` (keine
    seitlichen Scrollbalken der Seite; Tabellen liegen in ``.nv-table-wrap``).
``test_wide_nav_is_sticky_left_and_marks_active_section_on_click``
    Vorbedingung: Breitbild 1440×900, Einstellungen offen.
    Aktion: Navigation messen; Link „access" klicken.
    Erwartung: Navigation sticky (computed ``position: sticky``), links vom
    Inhalt, Spaltenbreite 14–16 rem (±Toleranz); genau der geklickte Link
    trägt ``aria-current="true"``; die Sektion ist im Sichtbereich.
``test_wide_nav_marks_active_section_on_scroll_sync``
    Vorbedingung: Breitbild, Einstellungen offen.
    Aktion: ``models``-Sektion per scrollIntoView an den oberen Rand bringen
    (kein Klick).
    Erwartung: Scroll-Sync markiert nach dem Scrollen den Link „models" mit
    ``aria-current="true"``.
``test_editview_desktop_width_resize_and_session_storage``
    Vorbedingung: Breitbild 1400×900, globale AGENTS.md vorhanden.
    Aktion: ``global-agents-edit`` klicken; Ziehgriff
    ``[data-nv-editview-resize]`` um 100 px nach links ziehen; schließen und
    erneut öffnen.
    Erwartung: ``aside[data-nv-editview]`` sichtbar mit Scrim,
    ``body[data-nv-editview-open="true"]``, Oberkante auf
    ``var(--nv-top-h)`` (≈68 px), Breite ≥ 29 % des Viewports (Vertrag
    „mindestens 30 %", Toleranz 1 %); Ziehen vergrößert die Breite und
    schreibt ``sessionStorage['nv-editview-width']``; nach Wiederöffnen ist
    die gespeicherte Breite wiederhergestellt.
``test_editview_is_fullscreen_on_mobile_and_escape_closes``
    Vorbedingung: mobil 390×844, globale AGENTS.md vorhanden.
    Aktion: ``global-agents-edit`` klicken, Escape drücken.
    Erwartung: Vollbild (link/top ≈ 0, Breite/Höhe ≈ Viewport), Ziehgriff
    ausgeblendet; Escape schließt (``body[data-nv-editview-open]`` nicht
    „true", Ansicht unsichtbar).

GlobalAgentsSectionTest
``test_section_is_flat_with_hint_and_editview_editor``
    Vorbedingung: globale AGENTS.md existiert.
    Aktion: Sektion lesen, Bearbeiten-Knopf klicken.
    Erwartung: Sektion flach (kein ``details``-Nachfahre); Erklärung
    ``[data-nv-global-agents-hint]`` nichtleer; ``global-agents-edit`` öffnet
    die Edit-View mit ``textarea[data-nv-agents-text]`` (rows ≥ 16),
    vorbelegt mit dem Dateiinhalt.
``test_missing_global_agents_file_offers_create_only``
    Vorbedingung: globale AGENTS.md fehlt.
    Aktion: ``global-agents-create`` klicken.
    Erwartung: Knopf nur bei fehlender Datei; danach Datei angelegt und
    Edit-View-Editor vorbelegt; Anlegen-Knopf verschwindet.
``test_save_writes_file_with_digest_and_toast``
    Vorbedinung: Datei vorhanden, Edit-View offen.
    Aktion: Text ändern, ``agents-save`` klicken.
    Erwartung: genau der neue POST ``{action:'save', text, digest}`` mit der
    zuvor geladenen Prüfsumme; Datei enthält den Text; Toast bestätigt.
``test_backup_restore_and_project_rows``
    Vorbedingung: Datei vorhanden, Projekt „proj" existiert.
    Aktion: Backup klicken; Restore-Auswahl prüfen und Restore bestätigen;
    Projektzeile ``[data-nv-agents-file-row='proj']`` bearbeiten.
    Erwartung: POST ``{action:'backup'}``; danach bietet
    ``[data-nv-agents-backup-select]`` eine Sicherung an; Restore sendet
    ``{action:'restore', confirm:true}`` nach Bestätigung (NV.context, keine
    nativen Dialoge); die Projektzeile öffnet die Edit-View mit zwei
    Textfeldern (before/after) und Hinweis auf den verwalteten Block.

AccessSectionTest
``test_restart_note_uses_plain_wording_without_ui_json``
    Vorbedingung: Einstellungen offen.
    Aktion: Hinweistext lesen.
    Erwartung: ``[data-nv-restart-note]`` sichtbar, nennt Neustart-Befristung
    („Neustart"/„restart"), ohne Techniker-Satz mit „ui.json".
``test_restart_button_asks_confirmation_and_post_is_intercepted``
    Vorbedingung: Einstellungen offen; der POST ``/api/security`` wird per
    ``page.route`` abgefangen und mit ``ok:false`` beantwortet, damit der
    Server im Test NIEMALS wirklich neu startet (dokumentierte Wahl).
    Aktion: ``dashboard-restart`` klicken, Bestätigung bestätigen.
    Erwartung: Bestätigung über ``NV.confirmView`` (``aside[data-nv-context]``,
    kein ``window.confirm``-Dialog); danach genau ein abgefangener POST
    ``{action:'restart'}``; der Server bleibt erreichbar (``/api/health`` 200).

FeaturesSectionTest
``test_feature_toggle_keeps_scroll_position_and_render_count``
    Vorbedingung: Einstellungen offen, zum Seitenende gescrollt.
    Aktion: Feature „gates" per JS-Klick aus- und wieder einschalten.
    Erwartung: ``scrollY`` und der echte Render-Zähler (umhülltes
    ``NV.render``) bleiben unverändert; Sektion und Navigations-Eintrag
    verschwinden sofort (``[hidden]``) und erscheinen wieder.

LimitsSectionTest
``test_single_toggle_posts_mode_without_rerender``
    Vorbedingung: Feature „limits" an, ``limits.json`` entfernt (Modus stop).
    Aktion: Schalter ``input[type=checkbox][data-nv-limits-mode]`` umlegen.
    Erwartung: genau ein Schalter in ``label.nv-switch-row``, Erklärung
    ``[data-nv-limits-help]`` nichtleer, keine Knöpfe ``limits-continue``/
    ``limits-stop``; Umschalten sendet ``POST /api/limits
    {action:'continue'}`` (bzw. zurück „stop"), ``GET /api/limits`` bestätigt,
    Toast, Render-Zähler unverändert.

GatesSectionTest
``test_global_context_is_default_with_editable_values_and_translated_origin``
    Vorbedingung: Feature „gates" an, frischer Zustand.
    Aktion: Auswahl/Tabelle lesen; Sprache nach „de" wechseln und neu laden.
    Erwartung: ``select[data-nv-gates-project]`` steht auf ``global``; je Zeile
    editierbares ``[data-nv-gate-value]`` und nichtleere Herkunft
    ``[data-nv-gate-origin]``; Tabelle nutzt die volle Sektionsbreite; die
    Herkunft wird übersetzt (mindestens ein Zeilentext ändert sich de/en).
``test_project_context_readonly_global_effective_preview_and_save_under_table``
    Vorbedingung: Feature „gates" an.
    Aktion: Projekt „proj" wählen; Override für „retries" tippen; speichern.
    Erwartung: je Zeile nur-lesender globaler Wert ``[data-nv-gate-global]``,
    editierbarer Projektwert ``[data-nv-gate-override]``, Wirksam-Vorschau
    ``[data-nv-gate-effective]`` + Herkunft; das Tippen aktualisiert die
    Vorschau sofort OHNE ``POST /api/gates``; Speichern sendet genau einen
    POST ``{project:'proj', values:{alle Schlüssel}}``; die Aktionszeile
    (gates-save/gates-reset) liegt unterhalb der Tabelle.

ModelsSectionTest
``test_details_collapsed_refresh_always_visible_and_stand_date_after_refresh``
    Vorbedingung: Feature „models" an, kein Modell-Cache, STUB liefert Modelle.
    Aktion: Sektion lesen; ``models-refresh`` klicken.
    Erwartung: ``details[data-nv-models]`` eingeklappt (kein ``open``); der
    Aktualisieren-Knopf ist auch eingeklappt sichtbar; keine
    Katalog-Beschreibung („Referenz") mehr und kein ``[data-nv-models-hint]``;
    ``[data-nv-models-stand]`` zeigt ohne Cache „—"/leer, nach dem Refresh
    ``POST /api/agents {action:'refresh_models'}`` ein Datum und der Cache
    ``models-cache.json`` existiert mit „stand".
``test_model_row_opens_editview_detail``
    Vorbedingung: wie oben, Refresh ausgeführt.
    Aktion: erste Zeile ``tr[data-nv-model]`` klicken.
    Erwartung: Edit-View öffnet mit ``[data-nv-model-detail]``; keine
    eingebettete Detailzeile ``tr[data-nv-model-detail]`` in der Tabelle.
``test_empty_state_without_model_data``
    Vorbedingung: kein Cache, STUB-Modelldatei geleert, Seite neu geladen.
    Aktion: Modellsbereich lesen; Datei danach wiederherstellen.
    Erwartung: ``[data-nv-models-empty]`` sichtbar (mit Hinweis auf
    Aktualisieren), Aktualisieren-Knopf bleibt sichtbar.

ProfilesSectionTest
``test_select_lists_standard_and_custom_profiles_with_badges``
    Vorbedingung: ``profiles.json`` mit Nutzerprofil „meins"; Feature „profiles".
    Aktion: Auswahl und Marker lesen.
    Erwartung: ``select[data-nv-profiles-select]`` führt die vier
    Standardprofile und „meins"; ``[data-nv-profile-selected]``,
    Standard-Badge ``[data-nv-profile-standard]`` und Aktiv-Badge
    ``[data-nv-profile-active]`` vorhanden.
``test_role_comboboxes_with_default_option_and_default_hint``
    Vorbedingung: Profil „free" gewählt (ohne Werte).
    Aktion: Coder-Combobox öffnen; „Default" wählen.
    Erwartung: erste Option heißt „Default"; nach der Wahl erscheint
    ``[data-nv-profile-default-hint]`` mit dem dahinterstehenden Modell
    (aus den Agent-Einstellungen: ``opencode/test-modell``).
``test_default_profile_is_readonly``
    Vorbedingung: Profil „default" gewählt.
    Aktion: Zuordnungsbereich und Löschen-Knopf prüfen.
    Erwartung: keine Rollen-Comboboxen; lesende Spiegelung der
    Agent-Einstellungen (nennt ``opencode/test-modell``); Löschen
    deaktiviert oder abwesend (Standardprofile geschützt).
``test_create_and_delete_custom_profile``
    Vorbedingung: Einstellungen offen.
    Aktion: „Sonderprofil" über ``[data-nv-profile-name]`` +
    ``profile-new`` anlegen; wählen; ``profile-delete`` mit Bestätigung.
    Erwartung: POST ``{action:'create'}``; Auswahl bietet das Profil an;
    Löschen sendet ``{action:'delete'}`` nach Bestätigung; die Option
    verschwindet.
``test_save_sends_only_selected_profile_and_cancel_discards``
    Vorbedingung: Profil „meins" gewählt.
    Aktion: Coder-Modell ändern, speichern; erneut ändern, Abbrechen.
    Erwartung: der Save-POST trägt ``data.profile`` mit GENAU dem gewählten
    Profil plus ``rollen``; Abbrechen sendet keinen weiteren Save-POST und
    stellt den gespeicherten Wert wieder her (``data-nv-value``).
``test_backup_restore_and_apply_with_preview``
    Vorbedingung: Profil „meins" gewählt.
    Aktion: Backup; gewählte Sicherung restoren (Bestätigung); „Anwenden"
    mit Vorschau bestätigen.
    Erwartung: POSTs ``backup``/``restore{confirm:true}``/``use``; die
    Vorschau (NV.context) nennt ein aufgelöstes Modell; nach Bestätigung
    steht ``aktiv='meins'`` in ``profiles.json`` und der Tester-Agent
    erhält das Profilmodell.

McpSectionTest
``test_add_opens_editview_form_and_saves_via_create``
    Vorbedingung: Feature „mcp" an.
    Aktion: ``mcp-add`` klicken; Formular ausfüllen; ``mcp-save`` klicken.
    Erwartung: Edit-View mit den Vertragsfeldern (name, scope, type
    local/remote, command, env, cwd, url, headers, noauth, enabled,
    timeout) und Fuß (save/test/abort); Speichern sendet
    ``POST /api/mcp {action:'save', create:true}`` — NIEMALS
    ``action:'set'``; die neue Server-Karte erscheint.
``test_state_badge_visible_on_mobile_without_overlap``
    Vorbedingung: mobil 390×844, MCP-Server vorhanden.
    Aktion: Badge-Kästchen gegen die Karten-Knöpfe messen.
    Erwartung: ``[data-nv-mcp-state]`` sichtbar, vollständig im Viewport und
    ohne Überlappung mit den Karten-Knöpfen.

HarnessSectionTest
``test_status_grid_stacks_on_mobile_with_install_button``
    Vorbedingung: Feature „harness" an; kein Pi installiert.
    Aktion: Statusbereich lesen; auf 390 px verengen.
    Erwartung: ``[data-nv-harness-status]`` mit je Harness einer Karte
    (``.nv-card``); auf mobil stapeln die Karten ohne vertikale Überlappung;
    Installationsknopf ``[data-nv-action='harness-install']`` für die
    fehlende Installation sichtbar;
    ``[data-nv-harness-install-feedback]`` vorhanden.

I18nTest
``test_new_labels_are_translated_to_english``
    Vorbedingung: aktive Sprache „en".
    Aktion: neue Beschriftungen lesen; Sprachwechsel de/en vergleichen.
    Erwartung: Neustart-Knopf textlich mit „restart" (en); MCP-
    Hinzufügen-Knopf mit „add" (en); die Aktualisierungs-Zeile
    ``[data-nv-models-stand]`` ist übersetzt (de≠en, en „updated/last").

Vertragsunklarheiten (dokumentiert, nicht geraten)
--------------------------------------------------
1. Für ``mcp-test`` nennt der Vertrag nur den Fuß der Edit-View; ein
   Ergebnis-/Fehlerbereich dort hat keinen Hook. Die Bestandsprüfung
   (``test_ap22_advanced_ui.McpTest``) klickt kartenebene — siehe Bericht.
   (Koordinator-Klärung: Der Karte bleibt ihr Test-Knopf mit
   ``[data-nv-mcp-result]`` erhalten; die Edit-View führt ebenfalls
   ``mcp-test`` aus und zeigt das Ergebnis ebenfalls in einem
   ``[data-nv-mcp-result]``-Bereich.)
2. Die Edit-View-Fokus-Rückkehr (Vertrag Barrierefreiheit) wird bewusst
   nicht geprüft (kein robuster, implementationsunabhängiger Beobachtungspunkt).

ROT-PHASE (2026-11-23/24, vor der Implementierung, Koordinator-Lauf)
--------------------------------------------------------------------
Die ausführende Agentensitzung des Test-Agenten hatte keine Schreib-/
Ausführungsrechte; die Rotphase wurde vom Koordinator vor der
Implementierung ausgeführt::

    PLAYWRIGHT_BROWSERS_PATH=/home/vibe/vibe-logs/playwright-browsers \
        python3 -m unittest tests.browser.test_gh57_settings_ui -v
    Ran 29 tests in 451.493s — FAILED (failures=13, errors=18)

Rot wie erwartet an allen neuen Verträgen: Edit-View/Sidebar fehlt
(`aside[data-nv-editview]`), Navigation nicht sticky und ohne
Scroll-Sync, Sektionen ohne die neuen Hooks (agents-text, restart-note/
restart-pending, dashboard-restart, limits-mode, gates-global/effective,
models-stand/empty, profiles-select/roles/default-hint, mcp-add-Formular),
globals-agents flach statt details. Die Fehler sind Fach-Fehler
(fehlende Hooks/Verhalten, Timeouts auf nicht existierende Selektoren),
keine Umgebungsfehler: das isolierte Dashboard bootete und ältere Hooks
(Kopfzeile, Sektionshüllen) waren erreichbar. Einzelfälle, die heute
bereits gedecktes Bestandsverhalten prüfen, würden grün bleiben — das
ist dokumentierter Regressionsschutz; die Gesamtbilanz des Moduls ist
rot. Die gleichen Vorbedingungen gelten für die angepassten Bestands-
module (test_f34_settings_ui, test_f33_settings_ui,
test_ap22_settings_ui, test_ap22_advanced_ui): ihre ersetzten Fälle
widersprechen dem GH-57-Vertrag und sind gegen den Altstand rot.
"""
import http.client
import json
import os
import re
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
OTHER = "zweit"
GLOBAL_AGENTS_TEXT = "GH57-GLOBAL-RULE: gilt für alle Projekte.\n"
FAKE_MODELS = "opencode/test-modell\nopencode/vibe-modell\nopencode/neu\n"

VIBE_AGENT = """---
description: Vibe-Standardagent für Nutzerunterstützung
mode: primary
model: opencode/vibe-modell
---

Vibe-Agent-Prompt.
"""

TESTER_AGENT = """---
description: Tester mit Coder-Rolle
mode: subagent
model: opencode/test-modell
---

Tester-Prompt.
"""

# Standardprofile werden von profiles_load ergänzt (Vertrag §Backend 2);
# „meins" bleibt als nutzerdefiniertes Profil erhalten. Der Coder der
# Agent-Einstellungen (tester → opencode/test-modell) ist das Modell hinter
# „Default" für die Rolle coder.
PROFILES_SEED = {
    "aktiv": "default",
    "rollen": {"tester": "coder", "vibe-agent": "vibe"},
    "profile": {"meins": {"coder": "opencode/vibe-modell"}},
}

MCP_SEED = {"mcp": {"servers": {"gh57-basis-server": {
    "type": "local", "command": ["echo", "basis"], "enabled": True}}}}

FAKE_OPENCODE = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf 'opencode 2.1.4\\n'
    exit 0
    ;;
  models)
    if [ -n "$GH57_FAKE_MODELS_FILE" ] && [ -f "$GH57_FAKE_MODELS_FILE" ]; then
      cat "$GH57_FAKE_MODELS_FILE"
    fi
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
    """opencode-Server-Attrappe: antwortet leer, startet keine Modelle."""

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


class GH57SettingsBrowserTest(unittest.TestCase):
    """Dashboard, Browser, opencode-Attrappen, isolierter Zustand (GH-57)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        for name in (PROJECT, OTHER):
            project = cls.root / name
            (project / ".vibe").mkdir(parents=True)
            (project / ".vibe" / "project.env").write_text(
                "TYPE=generic\n", encoding="utf-8")
            (project / "FEEDBACK.md").write_text(
                "# FEEDBACK\n", encoding="utf-8")
            (project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True)
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir(parents=True)
        password = cls.log_dir / "opencode.password"
        password.write_text("gh57-ui-kennwort-42", encoding="utf-8")
        password.chmod(0o600)

        # opencode-STUB-Binary auf dem PATH (Modelle aus Datei, kein Netz).
        cls.fake_bin = cls.root / "fakebin"
        cls.fake_bin.mkdir()
        stub = cls.fake_bin / "opencode"
        stub.write_text(FAKE_OPENCODE, encoding="utf-8")
        stub.chmod(0o755)
        cls.models_source = cls.fake_bin / "models.txt"
        cls.models_source.write_text(FAKE_MODELS, encoding="utf-8")

        cls.port = free_port()
        cls.oc_port = free_port()
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), _FakeOpenCodeHandler)
        cls._fake_http.daemon_threads = True
        cls._fake_thread = threading.Thread(
            target=cls._fake_http.serve_forever)
        cls._fake_thread.daemon = True
        cls._fake_thread.start()

        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                    "TMUX", "TMUX_PANE", "GH57_FAKE_MODELS_FILE"):
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
            "GH57_FAKE_MODELS_FILE": str(cls.models_source),
            "PATH": str(cls.fake_bin) + os.pathsep + env.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        cls.env = env
        cls.server_log = open(cls.root / "web-server.log", "w",
                              encoding="utf-8")
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
        # Unabhängiger Zustand je Fall: Fachdateien zurücksetzen.
        for name in ("gates.json", "limits.json", "models-cache.json"):
            (self.state_dir / name).unlink(missing_ok=True)
        (self.state_dir / "profiles.json").write_text(
            json.dumps(PROFILES_SEED, ensure_ascii=False) + "\n",
            encoding="utf-8")
        self.models_source.write_text(FAKE_MODELS, encoding="utf-8")
        self.global_agents = (
            self.root / "home" / ".config" / "opencode" / "AGENTS.md")
        self.global_agents.parent.mkdir(parents=True, exist_ok=True)
        self.global_agents.write_text(GLOBAL_AGENTS_TEXT, encoding="utf-8")
        self.tester_agent = (
            self.root / "home" / ".config" / "opencode" / "agents"
            / "tester.md")
        self.tester_agent.write_text(TESTER_AGENT, encoding="utf-8")
        self.mcp_config = (
            self.root / "home" / ".config" / "opencode" / "opencode.json")
        self.mcp_config.write_text(
            json.dumps(MCP_SEED, ensure_ascii=False) + "\n", encoding="utf-8")
        self.api_post("/api/language", {"language": "en"})
        self.api_post("/api/security", {"action": "password", "clear": True})
        self.page_errors = []
        self._post_requests = []
        self.context = self.browser.new_context(
            viewport={"width": 1400, "height": 900})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))
        self.page.on(
            "request",
            lambda request: self._post_requests.append(request)
            if request.method == "POST" else None)
        self.context.add_init_script(
            "try { localStorage.setItem('nv-features', JSON.stringify("
            "{agentsfile: true, gates: true, limits: true, models: true, "
            "profiles: true, mcp: true, harness: true})); } catch (e) {}")

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

    def api_post(self, path, payload, token=None):
        body = json.dumps(payload).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("POST", path, body=body, headers={
                "Host": f"127.0.0.1:{self.port}",
                "X-Token": token or self.token,
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
                "Host": f"127.0.0.1:{self.port}",
                "X-Token": self.token})
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
        self.page.locator(
            "main#nv-main[data-nv-view='home']").wait_for(
                state="visible", timeout=25000)
        self.install_render_counter()

    def open_settings(self):
        self.page.goto(self.base + "/#/settings")
        self.page.locator(
            "main#nv-main[data-nv-view='settings']").wait_for(
                state="visible", timeout=20000)
        self.install_render_counter()

    def set_viewport(self, width, height):
        self.page.set_viewport_size({"width": width, "height": height})

    def boxes(self, selectors):
        return self.page.evaluate(
            """(selectors) => {
                 const out = {};
                 for (const s of selectors) {
                   const node = document.querySelector(s);
                   const r = node ? node.getBoundingClientRect() : null;
                   out[s] = r ? {x: r.left, y: r.top, w: r.width,
                                 h: r.height, right: r.right,
                                 bottom: r.bottom} : null;
                 }
                 return out;
               }""",
            list(selectors))

    def posts_to(self, path):
        payloads = []
        for request in self._post_requests:
            if request.url.split("?")[0].endswith(path):
                try:
                    payloads.append(json.loads(request.post_data or "{}"))
                except ValueError:
                    payloads.append({})
        return payloads

    def wait_for_post(self, path, predicate, timeout=20,
                      message="Post nicht empfangen"):
        self.wait_until(
            lambda: any(predicate(p) for p in self.posts_to(path)),
            timeout=timeout, message=message)

    def toast_text(self):
        toasts = self.page.locator("#nv-toasts")
        return (toasts.inner_text() if toasts.count() else "") or ""

    def install_render_counter(self):
        """Umhüllt ``NV.render`` mit einem Zähler des Testgerüsts (Muster F34)."""
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
              return {ok: true, already: false,
                      wrapped: NV.render !== window.__nvRenderCountOriginal,
                      countsInBody: String(NV.render)
                        .indexOf('__nvRenderCount') !== -1};
            }""")
        self.assertTrue(state.get("ok"),
                        "Render-Zähler nicht installierbar: %r"
                        % (state.get("reason"),))
        if not state.get("already"):
            self.assertTrue(
                state.get("wrapped") and state.get("countsInBody"),
                "Die Umhüllung von NV.render zählt nicht wirklich: %r"
                % (state,))

    def nv_render_count(self):
        state = self.page.evaluate(
            """() => ({
              installed: window.__nvRenderCounterInstalled === true,
              count: typeof window.__nvRenderCount === 'number'
                ? window.__nvRenderCount : null
            })""")
        self.assertTrue(state.get("installed"),
                        "Render-Zähler nicht installiert")
        self.assertIsNotNone(state.get("count"))
        return state["count"]

    def confirm_in_context(self, timeout=15):
        """Klickt eine sichtbare Bestätigen-Schaltfläche im NV.context."""
        panel = self.page.locator("aside[data-nv-context]")
        deadline = time.time() + timeout
        while time.time() < deadline:
            if panel.count() and panel.first.is_visible():
                buttons = panel.first.locator("button")
                for index in range(buttons.count()):
                    button = buttons.nth(index)
                    if not button.is_visible():
                        continue
                    text = (button.inner_text() or "").strip().lower()
                    if re.search(r"bestätig|bestaetig|confirm|ja\b|yes|ok",
                                 text, re.I):
                        button.click()
                        return True
            self.page.wait_for_timeout(100)
        return False

    def assert_no_page_errors(self):
        self.assertEqual(
            [], self.page_errors, "Die Oberfläche erzeugte JavaScript-Fehler")

    def open_global_agents_edit(self):
        section = self.page.locator(
            "section[data-nv-ssection='global-agents']")
        section.wait_for(state="visible", timeout=20000)
        edit = section.locator("button[data-nv-action='global-agents-edit']")
        edit.wait_for(state="visible", timeout=20000)
        edit.click()
        aside = self.page.locator("aside[data-nv-editview]")
        aside.wait_for(state="visible", timeout=20000)
        return aside

    def section(self, name):
        node = self.page.locator(f"section[data-nv-ssection='{name}']")
        node.wait_for(state="visible", timeout=20000)
        return node


class ShellAndEditViewTest(GH57SettingsBrowserTest):
    MOBILE = {"width": 390, "height": 844}

    def test_mobile_nav_visible_below_header_and_horizontally_scrollable(self):
        """Mobil: Menü sichtbar, scrollbar, unterhalb der Kopfzeile, Anker-Marge."""
        self.set_viewport(self.MOBILE["width"], self.MOBILE["height"])
        self.boot()
        self.open_settings()
        nav = self.page.locator("nav[data-nv-settings-nav]")
        nav.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(
            nav.locator("[data-nv-ssection-link]").count(), 8,
            "Die mobile Navigation bietet nicht alle Sektionen")
        scrollable = nav.evaluate(
            """node => ({sw: node.scrollWidth, cw: node.clientWidth,
                         ox: getComputedStyle(node).overflowX})""")
        self.assertGreater(
            scrollable["sw"], scrollable["cw"],
            "Die mobile Navigation ist nicht horizontal scrollbar: "
            + repr(scrollable))
        self.assertIn(scrollable["ox"], ("auto", "scroll"),
                      "Die mobile Navigation hat kein horizontales Scrollen: "
                      + repr(scrollable))

        def geometry():
            return self.boxes(["header.nv-top", "nav[data-nv-settings-nav]",
                               "section[data-nv-ssection='appearance']"])

        boxes = geometry()
        self.assertIsNotNone(boxes["header.nv-top"], "Kopfzeile fehlt")
        self.assertGreaterEqual(
            boxes["nav[data-nv-settings-nav]"]["y"],
            boxes["header.nv-top"]["bottom"] - 2,
            "Die mobile Navigation überlappt die globale Kopfzeile")
        margin = self.page.locator(
            "section[data-nv-ssection='appearance']").evaluate(
                "node => parseFloat(getComputedStyle(node).scrollMarginTop)"
                " || 0")
        self.assertGreater(
            margin, 0,
            "Sektionsanker haben keinen scroll-margin-top unterhalb der Leiste")

        self.page.evaluate("window.scrollTo(0, 300)")
        self.page.wait_for_timeout(300)
        boxes = geometry()
        self.assertGreaterEqual(
            boxes["nav[data-nv-settings-nav]"]["y"],
            boxes["header.nv-top"]["bottom"] - 2,
            "Beim Scrollen rutscht die mobile Navigation unter/über die "
            "sticky Kopfzeile")
        self.assert_no_page_errors()

    def test_mobile_page_has_no_horizontal_scrolling(self):
        """Mobil: die Seite scrollt nicht horizontal (Vertrag „Einheitliches Layout")."""
        self.set_viewport(self.MOBILE["width"], self.MOBILE["height"])
        self.boot()
        self.open_settings()
        metrics = self.page.evaluate(
            "() => ({sw: document.documentElement.scrollWidth,"
            "       iw: window.innerWidth})")
        self.assertLessEqual(
            metrics["sw"], metrics["iw"] + 2,
            "Die Einstellungen-Seite scrollt auf mobil horizontal: "
            + repr(metrics))
        self.assert_no_page_errors()

    def test_wide_nav_is_sticky_left_and_marks_active_section_on_click(self):
        """Breitbild: sticky linke Navigation, Klick setzt aria-current."""
        self.set_viewport(1440, 900)
        self.boot()
        self.open_settings()
        nav = self.page.locator("nav[data-nv-settings-nav]")
        nav.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            "sticky", nav.evaluate("node => getComputedStyle(node).position"),
            "Die Navigation ist auf Breitbild nicht sticky")
        boxes = self.boxes(["nav[data-nv-settings-nav]",
                            "div.nv-settings-content"])
        self.assertLess(
            boxes["nav[data-nv-settings-nav]"]["right"],
            boxes["div.nv-settings-content"]["x"] + 0.5,
            "Die Navigation liegt nicht links vom Inhalt")
        nav_width = boxes["nav[data-nv-settings-nav]"]["w"]
        self.assertGreaterEqual(
            nav_width, 200,
            "Die Navigationsspalte ist schmaler als 14 rem: %r" % nav_width)
        self.assertLessEqual(
            nav_width, 300,
            "Die Navigationsspalte ist breiter als ~16 rem: %r" % nav_width)

        link = nav.locator("[data-nv-ssection-link='access']")
        link.click()
        self.wait_until(
            lambda: link.get_attribute("aria-current") == "true",
            timeout=15, message="Der geklickte Link trägt kein aria-current")
        current = self.page.evaluate(
            """() => Array.from(document.querySelectorAll(
                   'nav[data-nv-settings-nav] [data-nv-ssection-link]'))
                 .filter(n => n.getAttribute('aria-current') === 'true')
                 .map(n => n.getAttribute('data-nv-ssection-link'))""")
        self.assertEqual(
            ["access"], current,
            "Nach dem Klick ist nicht genau die Ziel-Sektion aktiv: "
            + repr(current))
        self.assert_no_page_errors()

    def test_wide_nav_marks_active_section_on_scroll_sync(self):
        """Breitbild: das Scrollen des Inhalts aktualisiert die Markierung."""
        self.set_viewport(1440, 900)
        self.boot()
        self.open_settings()
        self.page.evaluate(
            "document.querySelector(\"section[data-nv-ssection='models']\")"
            ".scrollIntoView({block: 'start'})")
        link = self.page.locator(
            "nav[data-nv-settings-nav] [data-nv-ssection-link='models']")
        self.wait_until(
            lambda: link.get_attribute("aria-current") == "true",
            timeout=15,
            message="Der Scroll-Sync markiert die sichtbare Sektion models "
                    "nicht mit aria-current")
        self.assert_no_page_errors()

    def test_editview_desktop_width_resize_and_session_storage(self):
        """Desktop: ≥ 30 % Breite, Ziehgriff, sessionStorage, Wiederöffnen."""
        self.boot()
        self.open_settings()
        self.open_global_agents_edit()
        aside = self.page.locator("aside[data-nv-editview]")
        self.assertEqual(
            "true", self.page.get_attribute("body", "data-nv-editview-open"),
            "body[data-nv-editview-open] ist beim Öffnen nicht 'true'")
        self.assertEqual(
            1, self.page.locator("[data-nv-editview-scrim]").count(),
            "Der Scrim der Edit-View fehlt")
        box = aside.bounding_box()
        self.assertIsNotNone(box, "Die Edit-View hat keine Kästchen")
        self.assertGreaterEqual(
            box["y"], 55, "Die Edit-View beginnt nicht unter der Kopfzeile")
        self.assertLessEqual(
            box["y"], 90, "Die Edit-View beginnt unerwartet tief")
        ratio = box["width"] / 1400.0
        self.assertGreaterEqual(
            ratio, 0.29,
            "Die Edit-View ist schmaler als ~30 %% des Viewports: %r" % box)

        handle = self.page.locator("[data-nv-editview-resize]")
        handle_box = handle.bounding_box()
        self.assertIsNotNone(handle_box, "Der Ziehgriff fehlt")
        start_y = handle_box["y"] + handle_box["height"] / 2
        start_x = handle_box["x"] + handle_box["width"] / 2
        self.page.mouse.move(start_x, start_y)
        self.page.mouse.down()
        self.page.mouse.move(start_x - 100, start_y, steps=10)
        self.page.mouse.up()
        self.wait_until(
            lambda: (aside.bounding_box() or {}).get("width", 0)
            >= box["width"] + 60,
            timeout=10, message="Der Ziehgriff ändert die Breite nicht")
        new_box = aside.bounding_box()
        stored = self.page.evaluate(
            "() => sessionStorage.getItem('nv-editview-width')")
        self.assertIsNotNone(
            stored, "Die Breite wurde nicht in sessionStorage gespeichert")
        self.assertAlmostEqual(
            float(stored), new_box["width"], delta=30,
            msg="sessionStorage['nv-editview-width'] passt nicht zur Breite")

        self.page.locator("[data-nv-editview-close]").click()
        self.wait_until(
            lambda: not aside.is_visible(), timeout=10,
            message="Der Schließen-Knopf schließt die Edit-View nicht")
        self.open_global_agents_edit()
        reopened = aside.bounding_box()
        self.assertAlmostEqual(
            reopened["width"], new_box["width"], delta=25,
            msg="Die gewählte Breite überlebt das Wiederöffnen nicht")
        self.page.keyboard.press("Escape")

    def test_editview_is_fullscreen_on_mobile_and_escape_closes(self):
        """Mobil: Vollbild-Ansicht ohne Ziehgriff; Escape schließt."""
        self.set_viewport(self.MOBILE["width"], self.MOBILE["height"])
        self.boot()
        self.open_settings()
        self.open_global_agents_edit()
        aside = self.page.locator("aside[data-nv-editview]")
        box = aside.bounding_box()
        self.assertIsNotNone(box)
        self.assertLessEqual(box["x"], 1, "Die mobile Ansicht startet nicht links")
        self.assertLessEqual(box["y"], 1, "Die mobile Ansicht startet nicht oben")
        self.assertGreaterEqual(
            box["width"], self.MOBILE["width"] * 0.98,
            "Die mobile Ansicht ist nicht bildbreit: %r" % box)
        self.assertGreaterEqual(
            box["height"], self.MOBILE["height"] * 0.95,
            "Die mobile Ansicht ist nicht bildhoch: %r" % box)
        self.assertFalse(
            self.page.locator("[data-nv-editview-resize]").is_visible(),
            "Auf Mobil ist der Ziehgriff ausgeblendet")
        self.page.keyboard.press("Escape")
        self.wait_until(
            lambda: self.page.get_attribute("body", "data-nv-editview-open")
            != "true", timeout=10, message="Escape schließt die Edit-View nicht")
        self.assertFalse(
            aside.is_visible(), "Die Edit-View ist nach Escape sichtbar")
        self.assert_no_page_errors()


class GlobalAgentsSectionTest(GH57SettingsBrowserTest):
    def test_section_is_flat_with_hint_and_editview_editor(self):
        """Flache Sektion, Erklärung, Bearbeiten öffnet Edit-View (rows ≥ 16)."""
        self.boot()
        self.open_settings()
        section = self.section("global-agents")
        self.assertEqual(
            0, section.locator("details").count(),
            "Die Sektion global-agents bleibt details-verschachtelt")
        hint = section.locator("[data-nv-global-agents-hint]")
        hint.wait_for(state="visible", timeout=20000)
        self.assertTrue(
            (hint.inner_text() or "").strip(),
            "Die Erklärung zur globalen AGENTS.md ist leer")
        aside = self.open_global_agents_edit()
        textarea = aside.locator("textarea[data-nv-agents-text]")
        textarea.wait_for(state="visible", timeout=20000)
        rows = textarea.evaluate(
            "node => parseInt(node.getAttribute('rows') || '0', 10)"
            " || node.rows")
        self.assertGreaterEqual(
            rows, 16, "textarea[data-nv-agents-text] hat weniger als 16 rows")
        self.assertIn(
            "GH57-GLOBAL-RULE", textarea.input_value(),
            "Der Editor ist nicht mit dem Dateiinhalt vorbelegt")
        self.page.keyboard.press("Escape")

    def test_missing_global_agents_file_offers_create_only(self):
        """Fehlt die Datei: Anlegen-Knopf, danach Editor und kein Anlegen-Knopf."""
        self.global_agents.unlink(missing_ok=True)
        self.boot()
        self.open_settings()
        section = self.section("global-agents")
        create = section.locator(
            "button[data-nv-action='global-agents-create']")
        create.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            0, section.locator(
                "button[data-nv-action='global-agents-edit']").count(),
            "Bei fehlender Datei gibt es einen Bearbeiten-Knopf")
        create.click()
        self.wait_until(
            lambda: self.global_agents.is_file(), timeout=20,
            message="Die globale AGENTS.md wurde nicht angelegt")
        aside = self.page.locator("aside[data-nv-editview]")
        textarea = aside.locator("textarea[data-nv-agents-text]")
        textarea.wait_for(state="visible", timeout=20000)
        self.assertTrue(
            (textarea.input_value() or "").strip(),
            "Der Editor ist nach dem Anlegen nicht vorbelegt")
        self.wait_until(
            lambda: self.page.locator(
                "button[data-nv-action='global-agents-create']").count() == 0,
            timeout=15, message="Der Anlegen-Knopf bleibt stehen")

    def test_save_writes_file_with_digest_and_toast(self):
        """Speichern: POST mit Text + geladener Prüfsumme, Datei, Toast."""
        self.boot()
        self.open_settings()
        initial = self.api_json("/api/global_agents_file")
        self.assertTrue(initial.get("digest"), "Die API liefert keinen Digest")
        self.open_global_agents_edit()
        textarea = self.page.locator(
            "aside[data-nv-editview] textarea[data-nv-agents-text]")
        new_text = GLOBAL_AGENTS_TEXT + "Neue globale Regel 4711.\n"
        textarea.fill(new_text)
        self.page.locator(
            "aside[data-nv-editview] button[data-nv-action='agents-save']"
            ).click()
        self.wait_for_post(
            "/api/global_agents_file",
            lambda p: p.get("action") == "save",
            message="Es wurde kein POST action=save gesendet")
        payload = [p for p in self.posts_to("/api/global_agents_file")
                   if p.get("action") == "save"][-1]
        self.assertEqual(new_text, payload.get("text"),
                         "Der POST trägt nicht den neuen Text")
        self.assertEqual(
            initial["digest"], payload.get("digest"),
            "Der POST sendet nicht die geladene Prüfsumme")
        self.wait_until(
            lambda: "Neue globale Regel 4711"
            in self.global_agents.read_text(encoding="utf-8"),
            timeout=20, message="Die Datei wurde nicht geschrieben")
        self.wait_until(
            lambda: re.search(r"gespeichert|saved", self.toast_text(), re.I)
            is not None, timeout=20,
            message="Das Speichern bestätigt nicht per Toast: "
                    + repr(self.toast_text()))

    def test_backup_restore_and_project_rows(self):
        """Backup/Restore im Fuß; Projektzeilen öffnen den Projekt-Editor."""
        self.boot()
        self.open_settings()
        self.open_global_agents_edit()
        aside = self.page.locator("aside[data-nv-editview]")
        aside.locator("button[data-nv-action='agents-backup']").click()
        self.wait_for_post(
            "/api/global_agents_file", lambda p: p.get("action") == "backup",
            message="Es wurde kein Backup-POST gesendet")
        select = aside.locator("[data-nv-agents-backup-select]")
        self.wait_until(
            lambda: select.count() == 1
            and select.evaluate(
                "node => node.options.length") >= 1,
            timeout=20, message="Die Restore-Auswahl bietet keine Sicherung an")
        select.select_option(index=0)
        aside.locator("button[data-nv-action='agents-restore']").click()
        self.assertTrue(
            self.confirm_in_context(),
            "Der Restore fragt nicht über NV.confirmView ab")
        self.wait_for_post(
            "/api/global_agents_file",
            lambda p: p.get("action") == "restore" and p.get("confirm") is True,
            message="Der Restore sendet keinen bestätigten POST")
        self.page.keyboard.press("Escape")

        row = self.page.locator("[data-nv-agents-file-row='proj']")
        row.wait_for(state="visible", timeout=20000)
        row.locator("button[data-nv-action='agents-file-edit']").click()
        aside = self.page.locator("aside[data-nv-editview]")
        aside.wait_for(state="visible", timeout=20000)
        textareas = aside.locator("textarea")
        self.assertGreaterEqual(
            textareas.count(), 2,
            "Der Projekt-Editor bietet nicht zwei Felder (before/after)")
        self.assertTrue(
            re.search(r"verwalteten block|managed block",
                      (aside.inner_text() or ""), re.I),
            "Der Projekt-Editor weist nicht auf den verwalteten Block hin")
        self.assert_no_page_errors()


class AccessSectionTest(GH57SettingsBrowserTest):
    def test_restart_note_uses_plain_wording_without_ui_json(self):
        """Neuer Hinweistext ohne Techniker-Jargon (Ticket: Satz ersetzen)."""
        self.boot()
        self.open_settings()
        note = self.section("access").locator("[data-nv-restart-note]")
        note.wait_for(state="visible", timeout=20000)
        text = (note.inner_text() or "").strip()
        self.assertTrue(text, "Der Neustart-Hinweis ist leer")
        self.assertRegex(
            text, re.compile(r"neustart|restart", re.I),
            "Der Hinweis nennt den Neustart nicht: " + repr(text))
        self.assertNotIn(
            "ui.json", text,
            "Der Hinweis verwendet weiterhin den technischen ui.json-Satz")

    def test_restart_button_asks_confirmation_and_post_is_intercepted(self):
        """Bestätigung via NV.confirmView; POST abgefangen, kein echter Neustart.

        Dokumentierte Wahl: ``page.route`` fängt POST /api/security ab und
        antwortet ``ok:false`` — der Server wird im Test nie wirklich neu
        gestartet; geprüft wird der gesendete Auftrag.
        """
        self.restart_posts = []
        native_dialogs = []

        def on_dialog(dialog):
            native_dialogs.append(dialog.type)
            dialog.dismiss()

        def intercept(route, request):
            if request.method == "POST":
                try:
                    payload = json.loads(request.post_data or "{}")
                except ValueError:
                    payload = {}
                self.restart_posts.append(payload)
                route.fulfill(status=200, content_type="application/json",
                              body=json.dumps(
                                  {"ok": False,
                                   "message": "vom Test blockiert"}))
                return
            route.continue_()

        self.page.on("dialog", on_dialog)
        self.page.route("**/api/security", intercept)
        self.boot()
        self.open_settings()
        button = self.section("access").locator(
            "button[data-nv-action='dashboard-restart']")
        button.wait_for(state="visible", timeout=20000)
        button.click()
        context_panel = self.page.locator("aside[data-nv-context]")
        self.wait_until(
            lambda: context_panel.count() == 1 and context_panel.is_visible(),
            timeout=15,
            message="Der Neustart-Knopf fragt nicht per NV.confirmView ab")
        self.assertTrue(
            self.confirm_in_context(),
            "Die Bestätigung bietet keinen Bestätigen-Knopf")
        self.wait_until(
            lambda: any(p.get("action") == "restart"
                        for p in self.restart_posts),
            timeout=15, message="Es wurde kein Neustart-POST gesendet")
        self.assertEqual(
            [], native_dialogs,
            "Die Bestätigung nutzt einen nativen window.confirm-Dialog")
        status, _body = self.api_get("/api/health")
        self.assertEqual(
            200, status,
            "Der Server wurde trotz Abfangens des POSTs beendet")
        self.assert_no_page_errors()


class FeaturesSectionTest(GH57SettingsBrowserTest):
    def test_feature_toggle_keeps_scroll_position_and_render_count(self):
        """Feature-Umschalten: kein Scroll-Sprung, kein Voll-Neurender."""
        self.boot()
        self.open_settings()
        self.page.evaluate(
            "window.scrollTo(0, document.documentElement.scrollHeight)")
        self.page.wait_for_timeout(300)
        scroll_before = self.page.evaluate("() => window.scrollY")
        self.assertGreater(scroll_before, 0,
                           "Vorbedingung: die Seite wurde nicht gescrollt")
        render_before = self.nv_render_count()
        toggle = self.page.locator("input[data-nv-feature='gates']")
        toggle.evaluate("node => node.click()")
        section = self.page.locator("section[data-nv-ssection='gates']")
        nav_link = self.page.locator(
            "nav[data-nv-settings-nav] [data-nv-ssection-link='gates']")
        self.wait_until(
            lambda: section.count() == 0 or not section.is_visible(),
            timeout=15, message="Die gates-Sektion verschwindet nicht")
        self.wait_until(
            lambda: nav_link.count() == 0 or not nav_link.is_visible(),
            timeout=15, message="Der Navigations-Eintrag verschwindet nicht")
        self.assertEqual(
            scroll_before, self.page.evaluate("() => window.scrollY"),
            "Das Umschalten setzte die Scroll-Position zurück")
        self.assertEqual(
            render_before, self.nv_render_count(),
            "Das Feature-Umschalten in den Einstellungen vollneu-renderd")
        toggle.evaluate("node => node.click()")
        self.wait_until(
            lambda: section.count() > 0 and section.is_visible(),
            timeout=15, message="Die gates-Sektion erscheint nicht wieder")
        self.assertEqual(
            scroll_before, self.page.evaluate("() => window.scrollY"),
            "Das Wiedereinschalten verschob die Scroll-Position")
        self.assert_no_page_errors()


class LimitsSectionTest(GH57SettingsBrowserTest):
    def test_single_toggle_posts_mode_without_rerender(self):
        """Kompakte Limits-Sektion: ein Schalter, POST, Toast, kein Re-Render."""
        self.boot()
        self.open_settings()
        section = self.section("limits")
        self.assertEqual(
            0, self.page.locator(
                "button[data-nv-action='limits-continue'],"
                " button[data-nv-action='limits-stop']").count(),
            "Die Limits-Sektion hat noch die alten Modus-Knöpfe")
        help_box = section.locator("[data-nv-limits-help]")
        help_box.wait_for(state="visible", timeout=20000)
        self.assertTrue(
            (help_box.inner_text() or "").strip(),
            "Die Erklärung zu Fortsetzen/Stopp fehlt")
        toggle = section.locator("input[type=checkbox][data-nv-limits-mode]")
        toggle.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            1, toggle.count(),
            "Es gibt nicht genau einen Limits-Schalter")
        self.assertEqual(
            "label.nv-switch-row",
            toggle.evaluate(
                "node => { const l = node.closest('label');"
                " return l ? l.className : ''; }"),
            "Der Schalter liegt nicht in label.nv-switch-row")
        mode = self.api_json("/api/limits").get("mode")
        self.assertEqual(
            mode == "continue", toggle.is_checked(),
            "Der Schalter spiegelt den Modus %r nicht" % (mode,))

        render_before = self.nv_render_count()
        toggle.click()
        expected = "continue" if mode != "continue" else "stop"
        self.wait_for_post(
            "/api/limits", lambda p: p.get("action") == expected,
            message="Der Schalter sendet kein POST /api/limits "
                    "{action:%r}" % expected)
        self.wait_until(
            lambda: self.api_json("/api/limits").get("mode") == expected,
            timeout=20, message="GET /api/limits bestätigt den Modus nicht")
        self.wait_until(
            lambda: re.search(r"fortsetz|stopp|continue|stop",
                              self.toast_text(), re.I) is not None,
            timeout=15, message="Der Moduswechsel bestätigt nicht per Toast")
        self.assertEqual(
            render_before, self.nv_render_count(),
            "Der Limits-Schalter vollneu-renderd")
        self.assertEqual(
            expected == "continue", toggle.is_checked(),
            "Der Schalter zeigt den neuen Modus nicht")


class GatesSectionTest(GH57SettingsBrowserTest):
    def test_global_context_is_default_with_editable_values_and_translated_origin(self):
        """Standardkontext global; Werte editierbar; Herkunft übersetzt."""
        self.boot()
        self.open_settings()
        section = self.section("gates")
        select = section.locator("select[data-nv-gates-project]")
        select.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            "global", select.input_value(),
            "Die Projektauswahl startet nicht im Global-Kontext")
        table = section.locator("table[data-nv-gates-table]")
        table.wait_for(state="visible", timeout=20000)
        rows = table.locator("tr[data-nv-gate]")
        self.wait_until(
            lambda: rows.count() >= 1, timeout=20,
            message="Die Gates-Tabelle hat keine Zeilen")
        for index in range(rows.count()):
            row = rows.nth(index)
            with self.subTest(gate=row.get_attribute("data-nv-gate")):
                value = row.locator("[data-nv-gate-value]")
                self.assertEqual(
                    1, value.count(), "Eine Zeile hat kein Wert-Feld")
                self.assertTrue(
                    value.first.evaluate(
                        "node => (node.tagName === 'INPUT'"
                        " || node.tagName === 'SELECT')"
                        " && !node.readOnly && !node.disabled"),
                    "Der Wert im Global-Kontext ist nicht editierbar")
                origin = row.locator("[data-nv-gate-origin]")
                self.assertEqual(
                    1, origin.count(), "Eine Zeile hat keine Herkunft")
                self.assertTrue(
                    (origin.first.inner_text() or "").strip(),
                    "Die Origin-Spalte ist leer (alter Fehler)")

        widths = self.page.evaluate(
            """() => {
                 const s = document.querySelector(
                   "section[data-nv-ssection='gates']");
                 const t = s.querySelector("table[data-nv-gates-table]");
                 const cs = getComputedStyle(s);
                 const inner = s.clientWidth
                   - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
                 return {inner: inner, table: t.getBoundingClientRect().width};
               }""")
        self.assertGreaterEqual(
            widths["table"], 0.9 * widths["inner"],
            "Die Gates-Tabelle nutzt nicht die volle Breite: " + repr(widths))

        origins_en = [
            (rows.nth(i).locator("[data-nv-gate-origin]").first.inner_text()
             or "").strip() for i in range(rows.count())]
        self.api_post("/api/language", {"language": "de"})
        try:
            self.page.reload()
            self.open_settings()
            rows = self.section("gates").locator(
                "table[data-nv-gates-table] tr[data-nv-gate]")
            self.wait_until(
                lambda: rows.count() >= 1, timeout=20,
                message="Die Gates-Tabelle fehlt nach dem Sprachwechsel")
            origins_de = [
                (rows.nth(i).locator("[data-nv-gate-origin]").first.inner_text()
                 or "").strip() for i in range(rows.count())]
        finally:
            self.api_post("/api/language", {"language": "en"})
        self.assertTrue(
            any(text for text in origins_de),
            "Die Herkunft ist im Deutschen leer")
        self.assertTrue(
            any(a != b for a, b in zip(origins_en, origins_de)),
            "Die Herkunft wird nicht übersetzt: en=%r de=%r"
            % (origins_en, origins_de))

    def test_project_context_readonly_global_effective_preview_and_save_under_table(self):
        """Projektkontext: global nur-lesend, Wirksam-Vorschau, Aktionen unten."""
        self.boot()
        self.open_settings()
        section = self.section("gates")
        select = section.locator("select[data-nv-gates-project]")
        select.select_option(PROJECT)
        table = section.locator("table[data-nv-gates-table]")
        rows = table.locator("tr[data-nv-gate]")
        self.wait_until(
            lambda: rows.locator("[data-nv-gate-override]").count() >= 1,
            timeout=20,
            message="Im Projektkontext erscheinen keine Override-Felder")
        for index in range(rows.count()):
            row = rows.nth(index)
            with self.subTest(gate=row.get_attribute("data-nv-gate")):
                readonly = row.locator("[data-nv-gate-global]")
                self.assertEqual(
                    1, readonly.count(),
                    "Eine Zeile zeigt den globalen Wert nicht nur-lesend")
                if readonly.first.evaluate(
                        "node => node.tagName === 'INPUT'"
                        " || node.tagName === 'SELECT'"):
                    self.assertTrue(
                        readonly.first.evaluate(
                            "node => node.readOnly || node.disabled"),
                        "Der globale Wert ist im Projektkontext editierbar")
                self.assertEqual(
                    1, row.locator("[data-nv-gate-effective]").count(),
                    "Eine Zeile hat keine Wirksam-Vorschau")
                self.assertEqual(
                    1, row.locator("[data-nv-gate-origin]").count(),
                    "Eine Zeile hat keine Herkunft")

        retries = table.locator("tr[data-nv-gate='retries']")
        override = retries.locator("[data-nv-gate-override]")
        effective_before = (
            retries.locator("[data-nv-gate-effective]").inner_text() or "")
        posts_before = len(self.posts_to("/api/gates"))
        override.fill("5")
        self.wait_until(
            lambda: "5" in (retries.locator(
                "[data-nv-gate-effective]").inner_text() or ""),
            timeout=10,
            message="Die Wirksam-Vorschau zeigt den getipsten Wert nicht sofort")
        self.assertEqual(
            posts_before, len(self.posts_to("/api/gates")),
            "Das Tippen des Projektwerts sendet bereits einen POST")
        self.assertNotEqual(
            effective_before,
            retries.locator("[data-nv-gate-effective]").inner_text(),
            "Die Wirksam-Vorschau ändert sich beim Tippen nicht")

        expected_values = {}
        for index in range(rows.count()):
            row = rows.nth(index)
            expected_values[row.get_attribute("data-nv-gate")] = (
                row.locator("[data-nv-gate-override]").input_value() or "")
        save = section.locator("button[data-nv-action='gates-save']")
        order = table.evaluate(
            """(table, saveSel) => {
                 const save = document.querySelector(saveSel);
                 return save ? Boolean(
                   table.compareDocumentPosition(save)
                   & Node.DOCUMENT_POSITION_FOLLOWING) : false;
               }""",
            "section[data-nv-ssection='gates'] "
            "button[data-nv-action='gates-save']")
        self.assertTrue(
            order, "Die Aktionszeile liegt nicht unterhalb der Tabelle")
        save.click()
        self.wait_for_post(
            "/api/gates", lambda p: p.get("project") == PROJECT,
            message="Es wurde kein POST /api/gates mit dem Projekt gesendet")
        payload = [p for p in self.posts_to("/api/gates")
                   if p.get("project") == PROJECT][-1]
        self.assertEqual(
            expected_values, payload.get("values"),
            "Der POST enthält nicht alle Zeilenschlüssel mit den Werten")
        self.assertEqual(
            1, section.locator("button[data-nv-action='gates-reset']").count(),
            "Der Reset-Knopf fehlt im Projektkontext")
        self.assert_no_page_errors()


class ModelsSectionTest(GH57SettingsBrowserTest):
    def test_details_collapsed_refresh_always_visible_and_stand_date_after_refresh(self):
        """Eingeklappt, Aktualisieren immer sichtbar, Stand-Datum nach Refresh."""
        self.boot()
        self.open_settings()
        section = self.section("models")
        details = section.locator("details[data-nv-models]")
        details.wait_for(state="attached", timeout=20000)
        self.assertFalse(
            details.evaluate("node => node.open"),
            "details[data-nv-models] ist standardmäßig aufgeklappt")
        refresh = section.locator(
            "button[data-nv-action='models-refresh']")
        self.assertTrue(
            refresh.is_visible(),
            "Der Aktualisieren-Knopf ist im eingeklappten Zustand nicht "
            "sichtbar (Sektionskopf)")
        self.assertEqual(
            0, section.locator("[data-nv-models-hint]").count(),
            "Der Beschreibungstext zum Katalog ist nicht entfallen")
        section_text = section.inner_text() or ""
        self.assertNotRegex(
            section_text, re.compile(r"referenz", re.I),
            "Die Katalog-Beschreibung („Der Katalog ist nur eine Referenz…“) "
            "existiert weiterhin")
        stand = section.locator("[data-nv-models-stand]")
        stand.wait_for(state="attached", timeout=20000)

        cache = self.state_dir / "models-cache.json"
        self.assertFalse(
            cache.exists(), "Vorbedingung: der Modell-Cache existiert bereits")
        refresh.click()
        self.wait_for_post(
            "/api/agents", lambda p: p.get("action") == "refresh_models",
            message="Der Aktualisieren-Knopf sendet kein POST "
                    "{action:'refresh_models'}")
        self.wait_until(
            lambda: cache.exists(), timeout=30,
            message="Der Modell-Cache models-cache.json wurde nicht geschrieben")
        cache_data = json.loads(cache.read_text(encoding="utf-8"))
        self.assertTrue(
            cache_data.get("stand"), "Der Cache trägt kein „stand“-Datum")
        self.wait_until(
            lambda: any(ch.isdigit()
                        for ch in (stand.inner_text() or "")),
            timeout=20,
            message="[data-nv-models-stand] zeigt nach der Aktualisierung "
                    "kein Datum: " + repr(stand.inner_text()))
        self.assert_no_page_errors()

    def test_model_row_opens_editview_detail(self):
        """Modellzeile öffnet die Edit-View-Detailansicht, keine Detailzeile."""
        self.boot()
        self.open_settings()
        section = self.section("models")
        refresh = section.locator("button[data-nv-action='models-refresh']")
        refresh.click()
        rows = section.locator("table[data-nv-models-table] tr[data-nv-model]")
        self.wait_until(
            lambda: rows.count() >= 1, timeout=30,
            message="Nach dem Refresh erscheinen keine Modellzeilen")
        rows.first.click()
        aside = self.page.locator("aside[data-nv-editview]")
        aside.wait_for(state="visible", timeout=20000)
        detail = aside.locator("[data-nv-model-detail]")
        detail.wait_for(state="visible", timeout=20000)
        self.assertTrue(
            (detail.inner_text() or "").strip(),
            "Die Modelldetail-Ansicht ist leer")
        self.assertEqual(
            0, section.locator("tr[data-nv-model-detail]").count(),
            "Die Modelldetails liegen weiterhin als eingebettete Zeile")
        self.page.keyboard.press("Escape")

    def test_empty_state_without_model_data(self):
        """Ohne Modelldaten: leerer Zustand mit Hinweis auf Aktualisieren."""
        try:
            self.models_source.write_text("", encoding="utf-8")
            (self.state_dir / "models-cache.json").unlink(missing_ok=True)
            self.boot()
            self.open_settings()
            section = self.section("models")
            empty = section.locator("[data-nv-models-empty]")
            empty.wait_for(state="visible", timeout=30000)
            self.assertTrue(
                (empty.inner_text() or "").strip(),
                "Der leere Zustand erklärt nichts")
            self.assertTrue(
                section.locator(
                    "button[data-nv-action='models-refresh']").is_visible(),
                "Der Aktualisieren-Knopf fehlt im leeren Zustand")
        finally:
            self.models_source.write_text(FAKE_MODELS, encoding="utf-8")


class ProfilesSectionTest(GH57SettingsBrowserTest):
    def profiles_select(self):
        select = self.page.locator("select[data-nv-profiles-select]")
        select.wait_for(state="visible", timeout=20000)
        return select

    def choose_profile(self, name):
        select = self.profiles_select()
        select.select_option(name)
        display = self.page.locator("[data-nv-profile-selected]")
        self.wait_until(
            lambda: display.count() >= 1
            and name in (display.first.inner_text() or ""),
            timeout=15,
            message="Die Auswahl zeigt das gewählte Profil nicht an")

    def role_combobox(self, role):
        return self.page.locator(f"[data-nv-profile-role='{role}']")

    def open_role_list(self, role):
        combo = self.role_combobox(role)
        combo.wait_for(state="visible", timeout=20000)
        combo.locator("input[data-nv-combobox-input]").click()
        options = self.page.locator("li[data-nv-combobox-option]")
        options.first.wait_for(state="visible", timeout=10000)
        return combo, options

    def choose_role_model(self, role, value):
        combo, options = self.open_role_list(role)
        option = self.page.locator(
            "li[data-nv-combobox-option]", has_text=value).first
        option.click()
        self.wait_until(
            lambda: combo.get_attribute("data-nv-value") == value,
            timeout=10, message="Die Combobox übernahm %r nicht" % value)

    def test_select_lists_standard_and_custom_profiles_with_badges(self):
        """Auswahl führt Standard- und Nutzerprofile; Marker und Badges."""
        self.boot()
        self.open_settings()
        select = self.profiles_select()
        values = select.evaluate(
            "node => Array.from(node.options).map(o => o.value)")
        for name in ("default", "free", "mid", "high", "meins"):
            self.assertIn(
                name, values,
                f"Die Profilauswahl bietet {name!r} nicht an: " + repr(values))
        self.choose_profile("default")
        section = self.section("profiles")
        self.assertGreaterEqual(
            section.locator("[data-nv-profile-standard]").count(), 1,
            "Das Standardprofil trägt keinen Standard-Badge")
        self.assertGreaterEqual(
            section.locator("[data-nv-profile-active]").count(), 1,
            "Das aktive Profil trägt keinen Aktiv-Badge")
        self.assertEqual(
            0, section.locator("article[data-nv-profile]").count(),
            "Die Profile erscheinen weiterhin als Karten")
        self.assert_no_page_errors()

    def test_role_comboboxes_with_default_option_and_default_hint(self):
        """Rollen-Comboboxen mit erster Option „Default“ und Modell-Hinweis."""
        self.boot()
        self.open_settings()
        self.choose_profile("free")
        roles = self.page.locator("[data-nv-profile-roles]")
        roles.wait_for(state="visible", timeout=20000)
        combo, options = self.open_role_list("coder")
        first_text = (options.first.inner_text() or "").strip()
        self.assertRegex(
            first_text, re.compile(r"default", re.I),
            "Die erste Combobox-Option heißt nicht „Default“: "
            + repr(first_text))
        options.first.click()
        hint = self.role_combobox("coder").locator(
            "[data-nv-profile-default-hint]")
        hint.wait_for(state="visible", timeout=15000)
        self.assertIn(
            "opencode/test-modell", hint.inner_text(),
            "Der Default-Hinweis nennt nicht das Modell der "
            "Agent-Einstellungen (Default-Kette): "
            + repr(hint.inner_text()))

    def test_default_profile_is_readonly(self):
        """Default-Profil: keine Comboboxen, lesende Spiegelung, Lösch-Schutz."""
        self.boot()
        self.open_settings()
        self.choose_profile("default")
        section = self.section("profiles")
        self.wait_until(
            lambda: section.locator("[data-nv-profile-role]").count() == 0,
            timeout=15,
            message="Das Default-Profil bietet editierbare Comboboxen an")
        self.assertIn(
            "opencode/test-modell", section.inner_text(),
            "Das Default-Profil spiegelt die Agent-Einstellungen nicht lesend")
        delete = section.locator("button[data-nv-action='profile-delete']")
        self.assertTrue(
            delete.count() == 0 or delete.first.is_disabled(),
            "Das Standardprofil darf nicht löschbar sein")

    def test_create_and_delete_custom_profile(self):
        """Nutzerprofil anlegen und entfernen; Standardprofile bleiben."""
        self.boot()
        self.open_settings()
        section = self.section("profiles")
        name_field = section.locator("[data-nv-profile-name]")
        name_field.wait_for(state="visible", timeout=20000)
        name_field.fill("Sonderprofil")
        section.locator("button[data-nv-action='profile-new']").click()
        self.wait_for_post(
            "/api/profiles", lambda p: p.get("action") == "create",
            message="Das Anlegen sendet kein POST {action:'create'}")
        select = self.profiles_select()
        self.wait_until(
            lambda: "Sonderprofil" in select.evaluate(
                "node => Array.from(node.options).map(o => o.value)"),
            timeout=15, message="Das neue Profil erscheint nicht in der Auswahl")
        select.select_option("Sonderprofil")
        delete = section.locator("button[data-nv-action='profile-delete']")
        self.wait_until(
            lambda: delete.count() == 1 and delete.first.is_enabled(),
            timeout=15, message="Das eigene Profil bietet kein aktives Löschen")
        delete.first.click()
        self.assertTrue(
            self.confirm_in_context(),
            "Das Löschen fragt nicht über NV.confirmView ab")
        self.wait_for_post(
            "/api/profiles",
            lambda p: p.get("action") == "delete"
            and p.get("name") == "Sonderprofil",
            message="Das Löschen sendet keinen POST {action:'delete'}")
        self.wait_until(
            lambda: "Sonderprofil" not in select.evaluate(
                "node => Array.from(node.options).map(o => o.value)"),
            timeout=15, message="Das gelöschte Profil bleibt in der Auswahl")

    def test_save_sends_only_selected_profile_and_cancel_discards(self):
        """Save-POST trägt nur das gewählte Profil; Abbrechen verwirft."""
        self.boot()
        self.open_settings()
        self.choose_profile("meins")
        self.choose_role_model("coder", "opencode/neu")
        save = self.section("profiles").locator(
            "button[data-nv-action='profile-save']")
        save.click()
        self.wait_for_post(
            "/api/profiles", lambda p: p.get("action") == "save",
            message="Das Speichern sendet keinen POST {action:'save'}")
        payload = [p for p in self.posts_to("/api/profiles")
                   if p.get("action") == "save"][-1]
        data = payload.get("data") or {}
        self.assertEqual(
            {"meins"}, set((data.get("profile") or {}).keys()),
            "Der Save-POST enthält nicht genau das gewählte Profil: "
            + repr(payload))
        self.assertIn("rollen", data,
                      "Der Save-POST trägt die Rollen nicht: " + repr(payload))

        self.choose_role_model("coder", "opencode/test-modell")
        cancel = self.section("profiles").locator(
            "button[data-nv-action='profile-cancel']")
        cancel.click()
        self.wait_until(
            lambda: self.role_combobox("coder").get_attribute(
                "data-nv-value") == "opencode/neu",
            timeout=15, message="Abbrechen stellt den gespeicherten Wert "
                                "nicht wieder her")
        saves = [p for p in self.posts_to("/api/profiles")
                 if p.get("action") == "save"]
        self.assertEqual(
            1, len(saves), "Abbrechen hat einen weiteren Save-POST gesendet")

    def test_backup_restore_and_apply_with_preview(self):
        """Backup/Restore mit Bestätigung; Anwenden mit Vorschau und Wirkung."""
        self.boot()
        self.open_settings()
        self.choose_profile("meins")
        section = self.section("profiles")
        section.locator("button[data-nv-action='profile-backup']").click()
        self.wait_for_post(
            "/api/profiles", lambda p: p.get("action") == "backup",
            message="Backup sendet keinen POST {action:'backup'}")
        select = section.locator("[data-nv-profile-restore-select]")
        self.wait_until(
            lambda: select.count() == 1 and select.evaluate(
                "node => node.options.length") >= 1,
            timeout=20, message="Die Restore-Auswahl bleibt leer")
        select.select_option(index=0)
        section.locator("button[data-nv-action='profile-restore']").click()
        self.assertTrue(
            self.confirm_in_context(),
            "Der Restore fragt nicht über NV.confirmView ab")
        self.wait_for_post(
            "/api/profiles",
            lambda p: p.get("action") == "restore"
            and p.get("confirm") is True,
            message="Der Restore sendet keinen bestätigten POST")

        section.locator("button[data-nv-action='profile-apply']").click()
        context_panel = self.page.locator("aside[data-nv-context]")
        self.wait_until(
            lambda: context_panel.count() == 1 and context_panel.is_visible(),
            timeout=15, message="Das Anwenden zeigt keine Vorschau")
        preview_text = context_panel.inner_text() or ""
        self.assertIn(
            "opencode/", preview_text,
            "Die Vorschau nennt kein aufgelöstes Modell: " + repr(preview_text))
        self.assertTrue(
            self.confirm_in_context(),
            "Die Vorschau bietet kein Bestätigen an")

        def applied():
            try:
                path = self.state_dir / "profiles.json"
                return json.loads(path.read_text(encoding="utf-8")).get(
                    "aktiv") == "meins"
            except (OSError, ValueError):
                return False

        self.wait_until(
            applied, timeout=30,
            message="Nach Bestätigen ist „meins“ nicht aktiv")
        self.wait_for_post(
            "/api/profiles", lambda p: p.get("action") == "use",
            message="Das Anwenden sendet keinen POST {action:'use'}")
        self.wait_until(
            lambda: "opencode/vibe-modell"
            in self.tester_agent.read_text(encoding="utf-8"),
            timeout=30, message="Der Tester-Agent hat das Profilmodell "
                                "nicht erhalten")
        self.assert_no_page_errors()


class McpSectionTest(GH57SettingsBrowserTest):
    MCP_FIELDS = (
        "[data-nv-mcp-name]", "[data-nv-mcp-scope]", "[data-nv-mcp-type]",
        "[data-nv-mcp-command]", "[data-nv-mcp-env]", "[data-nv-mcp-cwd]",
        "[data-nv-mcp-url]", "[data-nv-mcp-headers]",
        "[data-nv-mcp-noauth]", "[data-nv-mcp-enabled]",
        "[data-nv-mcp-timeout]")

    def test_add_opens_editview_form_and_saves_via_create(self):
        """Hinzufügen öffnet das Edit-View-Formular; Speichern nutzt create."""
        self.boot()
        self.open_settings()
        section = self.section("mcp")
        add = section.locator("button[data-nv-action='mcp-add']")
        add.wait_for(state="visible", timeout=20000)
        add.click()
        aside = self.page.locator("aside[data-nv-editview]")
        aside.wait_for(state="visible", timeout=20000)
        for selector in self.MCP_FIELDS:
            with self.subTest(field=selector):
                self.assertEqual(
                    1, aside.locator(selector).count(),
                    f"Das MCP-Formular fehlt das Feld {selector}")
        type_select = aside.locator("[data-nv-mcp-type]")
        self.assertIn(
            "local", type_select.evaluate(
                "node => Array.from(node.options).map(o => o.value)"),
            "Der Typ local fehlt")
        self.assertIn(
            "remote", type_select.evaluate(
                "node => Array.from(node.options).map(o => o.value)"),
            "Der Typ remote fehlt")
        for selector in ("mcp-save", "mcp-test"):
            self.assertEqual(
                1, aside.locator(f"button[data-nv-action='{selector}']").count(),
                f"Der Fuß bietet {selector} nicht an")

        aside.locator("[data-nv-mcp-name]").fill("gh57-server")
        aside.locator("[data-nv-mcp-type]").select_option("local")
        aside.locator("[data-nv-mcp-command]").fill("echo\ngh57")
        aside.locator("button[data-nv-action='mcp-save']").click()
        self.wait_for_post(
            "/api/mcp",
            lambda p: p.get("action") == "save" and p.get("create") is True,
            message="Das Anlegen sendet kein POST {action:'save', create:true}")
        self.assertEqual(
            [], [p for p in self.posts_to("/api/mcp")
                 if p.get("action") == "set"],
            "Das Anlegen verwendet weiterhin die ungültige action 'set'")
        payloads = [json.dumps(p) for p in self.posts_to("/api/mcp")]
        self.assertTrue(
            any("gh57-server" in text for text in payloads),
            "Der POST nennt den neuen Server nicht: " + repr(payloads))
        self.wait_until(
            lambda: self.section("mcp").locator(
                "article[data-nv-mcp-server='gh57-server']").count() == 1,
            timeout=20, message="Die neue Server-Karte erscheint nicht")
        self.assert_no_page_errors()

    def test_state_badge_visible_on_mobile_without_overlap(self):
        """Mobil: Status-Badge immer sichtbar und ohne Überlappung."""
        self.set_viewport(390, 844)
        self.boot()
        self.open_settings()
        cards = self.page.locator("article[data-nv-mcp-server]")
        cards.first.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(
            cards.count(), 1, "Vorbedingung: keine MCP-Karten")
        badge = cards.first.locator("[data-nv-mcp-state]")
        self.assertTrue(
            badge.is_visible(), "Der Status-Badge ist auf Mobil unsichtbar")
        self.assertTrue(
            (badge.inner_text() or "").strip(),
            "Der Status-Badge hat keinen Text")
        geometry = self.page.evaluate(
            """() => {
                 const card = document.querySelector(
                   "article[data-nv-mcp-server]");
                 const badge = card.querySelector("[data-nv-mcp-state]");
                 const btn = card.querySelector(
                   "button[data-nv-action='mcp-toggle']");
                 const rect = n => { const b = n.getBoundingClientRect();
                   return {l: b.left, r: b.right, t: b.top, b: b.bottom}; };
                 return {badge: rect(badge),
                         btn: btn ? rect(btn) : null,
                         vw: window.innerWidth};
               }""")
        box = geometry["badge"]
        self.assertGreaterEqual(box["l"], 0, "Der Badge ragt links heraus")
        self.assertLessEqual(
            box["r"], geometry["vw"] + 0.5,
            "Der Badge ragt rechts aus dem Viewport")
        button = geometry["btn"]
        if button:
            overlap_x = min(box["r"], button["r"]) - max(box["l"], button["l"])
            overlap_y = min(box["b"], button["b"]) - max(box["t"], button["t"])
            self.assertLessEqual(
                min(overlap_x, overlap_y), 0.5,
                "Der Status-Badge überlappt die Karten-Knöpfe: "
                + repr(geometry))


class HarnessSectionTest(GH57SettingsBrowserTest):
    def test_status_grid_stacks_on_mobile_with_install_button(self):
        """Responsives Harness-Raster; Installationsknopf für Fehlende."""
        self.boot()
        self.open_settings()
        section = self.section("harness")
        status = section.locator("[data-nv-harness-status]")
        status.wait_for(state="visible", timeout=20000)
        cards = status.locator(".nv-card")
        self.wait_until(
            lambda: cards.count() >= 2, timeout=20,
            message="Der Harness-Status zeigt nicht je Harness eine Karte")
        text = section.inner_text() or ""
        self.assertIn("opencode", text)
        self.assertIn("pi", text.lower(),
                      "Der Harness-Status nennt Pi nicht")
        install = section.locator(
            "button[data-nv-action='harness-install']")
        self.assertTrue(
            install.first.is_visible(),
            "Der Installationsknopf für die fehlende Installation fehlt")
        self.assertEqual(
            1, section.locator(
                "[data-nv-harness-install-feedback]").count(),
            "Der Feedback-Bereich für Installationen fehlt")

        self.set_viewport(390, 844)
        self.page.wait_for_timeout(300)
        rects = self.page.evaluate(
            """() => Array.from(document.querySelectorAll(
                   "[data-nv-harness-status] > .nv-card"))
                 .map(n => { const b = n.getBoundingClientRect();
                   return {top: b.top, bottom: b.bottom}; })""")
        for index in range(1, len(rects)):
            self.assertGreaterEqual(
                rects[index]["top"], rects[index - 1]["bottom"] - 1,
                "Auf Mobil überlappen die Harness-Karten: " + repr(rects))
        self.assert_no_page_errors()


class I18nTest(GH57SettingsBrowserTest):
    def test_new_labels_are_translated_to_english(self):
        """Neue Labels sind mit aktiver Sprache en englisch (SPEC.md)."""
        self.boot()
        self.open_settings()
        restart = self.section("access").locator(
            "button[data-nv-action='dashboard-restart']")
        self.assertRegex(
            (restart.inner_text() or "").strip(), re.compile(r"restart", re.I),
            "Der Neustart-Knopf ist nicht englisch beschriftet: "
            + repr(restart.inner_text()))
        add = self.section("mcp").locator(
            "button[data-nv-action='mcp-add']")
        self.assertRegex(
            (add.inner_text() or "").strip(), re.compile(r"add", re.I),
            "Der MCP-Hinzufügen-Knopf ist nicht englisch beschriftet: "
            + repr(add.inner_text()))

        section = self.section("models")
        stand = section.locator("[data-nv-models-stand]")
        stand.wait_for(state="attached", timeout=20000)
        section.locator(
            "button[data-nv-action='models-refresh']").click()
        self.wait_until(
            lambda: any(ch.isdigit() for ch in (stand.inner_text() or "")),
            timeout=30, message="Vorbedingung: kein Stand-Datum nach Refresh")
        text_en = (stand.inner_text() or "").strip()
        self.assertRegex(
            text_en, re.compile(r"updated|last", re.I),
            "Die Aktualisierungs-Zeile ist nicht englisch: " + repr(text_en))
        try:
            self.api_post("/api/language", {"language": "de"})
            self.page.reload()
            self.open_settings()
            text_de = (
                self.section("models").locator(
                    "[data-nv-models-stand]").inner_text() or "").strip()
        finally:
            self.api_post("/api/language", {"language": "en"})
        self.assertRegex(
            text_de, re.compile(r"aktualisier|stand", re.I),
            "Die Aktualisierungs-Zeile ist nicht deutsch: " + repr(text_de))
        self.assertNotEqual(
            text_en, text_de,
            "Die Aktualisierungs-Zeile ist nicht übersetzt")
        self.assert_no_page_errors()


if __name__ == "__main__":
    unittest.main()
