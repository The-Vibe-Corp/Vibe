"""AP5-Korbat 4a/4b: neuer Zustand „WARTET AUF MERGE“ statt BLOCKIERT.

Die Fälle leiten sich aus dem Arbeitspaket AP5-Korbat (4a/4b) und SPEC.md ab:
PR-only-Pakete warten auf den Merge des Eigentümers. Dafür gilt:

* Neuer Marker ``WARTET AUF MERGE:`` (eingerückt) mit eigenem
  ``is_waiting_merge``; ``is_blocked`` bleibt unverändert.
* CLI ``mark-waiting`` schreibt den Marker idempotent in den Paketblock des
  Projektordners; die Ausgabe nennt „wartend“.
* ``select_package`` überspringt wartende Pakete wie blockierte; ``prefer``
  (Reattach) bleibt erlaubt.
* ``status_report`` liefert zusätzlich ``waiting``; ``priority_view`` zeigt
  „wartet auf Merge“ in ``order`` und ``standard``.
* ``bin/vibe``: ``_parse_entry``/``open_items`` liefern den Ticket-Status
  „WARTET AUF MERGE“; bei beiden Markern gewinnt BLOCKIERT.
* ``_apply_proof`` räumt WARTET-Zeilen beim Zurückschreiben des Nachweises ab.
* Der Läufer ruft in ``pr_only_fallback`` ``mark-waiting`` statt
  ``mark-blocked`` auf; die Logzeile „WARTET AUF MERGE“ bleibt.
* GUI: Nova zeigt „Wartet auf Merge“ in der integrierten Liste (Label und
  gelbe Pille), die Uebersichtskachel ``waiting`` zaehlt wartende Pakete,
  „Paket abschließen“ bleibt fuer wartende Pakete im Kontext-Panel
  verfuegbar; klassische Oberflaeche: WARTET → ``warn``, BLOCKIERT bleibt
  ``bad``; i18n EN „Waiting for merge“.

F34-Anpassung: Das Board ist entfernt (Leitentscheidung 7). Die Nova-Faelle
pruefen deshalb Karten-Zustandspille und Kontext-Panel statt
``nvpStateColumn``/``nvpBoardColumn``/Spaltenreihenfolge; Board-Hooks duerfen
nicht mehr existieren.

Keine Netzverbindungen, keine Modellaufrufe, keine produktiven Pfade.

Run:

    python3 -m unittest tests.unit.test_ap5_korbat_waiting_state -v
"""
import contextlib
import importlib.machinery
import json
import importlib.util
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PACKAGES = REPO / "bin" / "vibe_packages.py"
CLI = REPO / "bin" / "vibe"
RUNNER = REPO / "bin" / "vibe-run.sh"
NOVA = REPO / "bin" / "web" / "nova-project.js"
APP_JS = REPO / "bin" / "web" / "app.js"
I18N = REPO / "bin" / "web" / "i18n.js"

WAITING = "WARTET AUF MERGE"


def load_packages():
    """Lädt ``bin/vibe_packages.py`` als eigenes Modul."""
    loader = importlib.machinery.SourceFileLoader(
        "vibe_packages_ap5_waiting_under_test", str(PACKAGES)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


def load_cli(vibe_root, home):
    """Lädt ``bin/vibe`` als Modul mit isoliertem VIBE und HOME."""
    old = {key: os.environ.get(key) for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_ap5_waiting_cli_under_test", str(CLI)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def ticket_record(tid, title, type="task", state="open", **extra):
    record = {
        "id": tid, "title": title, "type": type, "state": state,
        "description": "", "github": None, "pr_url": "", "commit": "",
        "test": "", "blocked_reason": "", "waiting_note": "",
        "priority": "", "dependencies": [],
        "created": "2026-01-01T00:00:00+00:00",
        "updated": "2026-01-01T00:00:00+00:00",
    }
    record.update(extra)
    return record


def make_project(root, tickets=None, feedback=None, env_text="TYPE=generic\n"):
    """Projekt mit GH-48-Ticketspeicher statt Markdown-Ledgern."""
    project = Path(root) / "proj"
    (project / ".vibe").mkdir(parents=True, exist_ok=True)
    (project / ".vibe" / "project.env").write_text(env_text, encoding="utf-8")
    records = []
    for source in (tickets, feedback):
        if source:
            records.extend(source)
    if records:
        (project / ".vibe" / "tickets.json").write_text(
            json.dumps({"version": 1, "tickets": records},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
    return project


def js_region(text, marker, fallback=6000):
    start = text.find(marker)
    if start < 0:
        return ""
    end = text.find("\nfunction ", start + len(marker))
    if end < 0:
        end = start + fallback
    return text[start:end]


# GH-48: `is_waiting_merge`/`sync_proof` (Markdown-Marker) sind entfernt.
# Die Zustandssemantik tragen tests/unit/test_gh48_runner_tickets.py und
# tests/unit/test_gh48_ticket_store.py.


class MarkWaitingCommandTest(unittest.TestCase):
    """CLI ``mark-waiting``: Marker, Idempotenz, Ausgabe."""

    @classmethod
    def setUpClass(cls):
        cls.module = load_packages()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = make_project(
            self.root,
            tickets=[
                ticket_record("T1", "Wartet", description="PR offen"),
                ticket_record("T2", "Offen", description="frei"),
            ],
        )

    def mark_waiting(self, note="PR #6 wartet"):
        return subprocess.run(
            [sys.executable, str(PACKAGES), "mark-waiting",
             "--project", str(self.project), "--id", "T1", "--note", note],
            cwd=str(self.root), stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=60,
        )

    def records(self):
        document = json.loads(
            (self.project / ".vibe" / "tickets.json").read_text(
                encoding="utf-8"))
        return {item["id"]: item for item in document["tickets"]}

    def test_mark_waiting_writes_an_indented_marker_and_reports_waiting(self):
        """Vorbedingung: offenes Paket T1 in TICKETS.md.
        Aktion: ``mark-waiting --id T1 --note …`` ausführen.
        Erwartung: Exit 0; eine eingerückte Zeile
        ``  WARTET AUF MERGE: <note>`` steht im Block T1; die Ausgabe enthält
        „wartend“.
        Fehlerfall: fehlender/falsch platzierter Marker oder stumme Ausgabe.
        """
        result = self.mark_waiting("PR #6 wartet")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("wartet", (result.stdout + result.stderr).lower())
        record = self.records()["T1"]
        self.assertEqual("waiting-merge", record["state"])
        self.assertEqual("PR #6 wartet", record["waiting_note"])

    def test_mark_waiting_is_idempotent(self):
        """Vorbedingung: ``mark-waiting`` lief bereits einmal für T1.
        Aktion: denselben Befehl erneut ausführen.
        Erwartung: Der Marker bleibt genau einmal vorhanden; die Ausgabe nennt
        weiterhin „wartend“.
        Fehlerfall: doppelte Markerzeile oder Fehlerabbruch.
        """
        first = self.mark_waiting()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)

        second = self.mark_waiting()

        output = second.stdout + second.stderr
        self.assertIn("wartet", output.lower())
        self.assertEqual("PR #6 wartet", self.records()["T1"]["waiting_note"])

    def test_mark_waiting_leaves_other_blocks_unchanged(self):
        """Vorbedingung: T1 und T2 offen.
        Aktion: ``mark-waiting`` für T1 ausführen.
        Erwartung: Nur der Block T1 erhält die Marke; T2 bleibt unverändert.
        Fehlerfall: Marke im falschen Block oder Datei-Umschreibung.
        """
        result = self.mark_waiting()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual("T2", list(self.records())[1])
        self.assertEqual("open", self.records()["T2"]["state"])
        self.assertEqual("", self.records()["T2"]["waiting_note"])


class WaitingSelectionAndReportTest(unittest.TestCase):
    """Auswahl, Status und Prioritätsansicht behandeln Wartende wie Gesperrte."""

    @classmethod
    def setUpClass(cls):
        cls.module = load_packages()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_select_package_skips_a_waiting_package(self):
        """Vorbedingung: T1 wartet auf Merge, T2 ist offen.
        Aktion: ``select_package(project)``.
        Erwartung: T2 wird gewählt; T1 wird nicht erneut gestartet.
        Fehlerfall: Wartendes Paket wird ausgewählt.
        """
        project = make_project(
            self.root,
            tickets=[
                ticket_record("T1", "Wartet", state="waiting-merge",
                              waiting_note="PR #6"),
                ticket_record("T2", "Offen"),
            ],
        )

        selected = self.module.select_package(
            project, state_path=str(self.root / "next.json"))

        self.assertIsNotNone(selected)
        self.assertEqual("T2", selected["id"])

    def test_select_package_with_prefer_reattaches_a_waiting_package(self):
        """Vorbedingung: T1 wartet auf Merge, T2 offen.
        Aktion: ``select_package(project, prefer="T1")``.
        Erwartung: T1 wird ausdrücklich erneut gewählt (Reattach bleibt
        erlaubt).
        Fehlerfall: ``prefer`` wird durch den neuen Zustand wirkungslos.
        """
        project = make_project(
            self.root,
            tickets=[
                ticket_record("T1", "Wartet", state="waiting-merge",
                              waiting_note="PR #6"),
                ticket_record("T2", "Offen"),
            ],
        )

        selected = self.module.select_package(
            project, prefer="T1", state_path=str(self.root / "next.json"))

        self.assertIsNotNone(selected)
        self.assertEqual("T1", selected["id"])

    def test_status_report_lists_waiting_before_open(self):
        """Vorbedingung: T1 wartet, T2 offen, T3 blockiert, T4 trägt beide
        Marker.
        Aktion: ``status_report(project)``.
        Erwartung: ``waiting`` enthält T1 (nicht ``open``); ``open`` enthält
        nur T2; ``blocked`` enthält T3 und T4 (BLOCKIERT wiegt schwerer).
        Fehlerfall: Wartende erscheinen als offen oder verdrängen BLOCKIERT.
        """
        project = make_project(
            self.root,
            tickets=[
                ticket_record("T1", "Wartet", state="waiting-merge",
                              waiting_note="PR #6"),
                ticket_record("T2", "Offen"),
                ticket_record("T3", "Blockiert", state="blocked",
                              blocked_reason="extern"),
                ticket_record("T4", "Beides", state="blocked",
                              waiting_note="PR #7",
                              blocked_reason="extern"),
            ],
        )

        report = self.module.status_report(project)

        self.assertIn("waiting", report, report)
        self.assertEqual(["T1"], report["waiting"])
        self.assertEqual(["T2"], report["open"])
        self.assertIn("T3", report["blocked"])
        self.assertIn("T4", report["blocked"])
        self.assertNotIn("T1", report["open"])

    def test_priority_view_marks_waiting_in_order_and_standard(self):
        """Vorbedingung: ``PACKAGE_ORDER="T1,T2"``; T1 wartet, T2 offen.
        Aktion: ``priority_view(project)``.
        Erwartung: ``order`` zeigt für T1 „wartet auf Merge“, ``standard``
        ebenfalls; ``queue`` beginnt mit T2 (T1 ist nicht bereit).
        Fehlerfall: Wartende gelten als offen oder fehlen in der Ansicht.
        """
        project = make_project(
            self.root,
            tickets=[
                ticket_record("T1", "Wartet", state="waiting-merge",
                              waiting_note="PR #6"),
                ticket_record("T2", "Offen"),
            ],
            env_text='TYPE=generic\nPACKAGE_ORDER="T1,T2"\n',
        )

        view = self.module.priority_view(project)

        by_id = {entry["id"]: entry for entry in view["order"]}
        self.assertEqual("wartet auf Merge", by_id["T1"]["status"])
        standard = {entry["id"]: entry for entry in view["standard"]}
        self.assertEqual("wartet auf Merge", standard["T1"]["status"])
        self.assertEqual("T2", view["queue"][0]["id"])
        self.assertNotIn("T1", [item["id"] for item in view["queue"]])


class TicketStatusWaitingTest(unittest.TestCase):
    """``bin/vibe``: Ticket-Status WARTET AUF MERGE, BLOCKIERT hat Vorrang."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.workspace = self.base / "ws"
        self.workspace.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.cli = load_cli(self.workspace, self.home)

    def project(self, tickets=None, feedback=None):
        project = make_project(self.workspace, tickets=tickets, feedback=feedback)
        self.cli._pm.clear()
        return project

    def test_open_items_marks_waiting_tickets(self):
        """Vorbedingung: TICKETS.md enthält T1 mit WARTET-Marker (offen).
        Aktion: ``open_items("proj")``.
        Erwartung: T1 erscheint mit Status „WARTET AUF MERGE“.
        Fehlerfall: Status bleibt „offen“ oder Eintrag fehlt.
        """
        self.project(tickets=[
            ticket_record("T1", "Wartet", state="waiting-merge",
                          waiting_note="PR #6")])

        items = self.cli.open_items("proj")

        self.assertIn(("T1", "Wartet", WAITING), items, items)

    def test_open_items_shows_waiting_feedback(self):
        """Vorbedingung: FEEDBACK.md enthält F1 mit WARTET-Marker (offen).
        Aktion: ``open_items("proj")``.
        Erwartung: F1 erscheint mit Status „WARTET AUF MERGE“.
        Fehlerfall: Feedback wartet still weiter als offen oder als erledigt.
        """
        self.project(feedback=[
            ticket_record("F1", "Wartet", type="feedback",
                          state="waiting-merge", waiting_note="PR #8")])

        items = self.cli.open_items("proj")

        self.assertIn(("F1", "Wartet", WAITING), items, items)

    def test_done_wins_over_a_stale_waiting_note(self):
        """Vorbedingung: erledigtes Ticket mit altem waiting_note.
        Aktion: ``open_items``/``ticket_items``.
        Erwartung: Es gilt der Zustand done (erledigt), nicht der Wartevermerk.
        Fehlerfall: Ein Wartefeld überdeckt den Abschluss."""
        self.project(tickets=[
            ticket_record("T1", "Beides", state="done", commit="abcdef1",
                          test="test_t1", waiting_note="PR #6")])

        items = self.cli.open_items("proj")
        rows = self.cli.ticket_items("proj")

        self.assertEqual([], items)
        self.assertEqual("erledigt", rows[0]["state"])

    def test_waiting_ticket_keeps_its_description(self):
        """Vorbedingung: wartendes Ticket mit Beschreibung.
        Aktion: ``ticket_items``.
        Erwartung: state „WARTET AUF MERGE", Beschreibung unverändert.
        Fehlerfall: Zustandsfelder landen in der Beschreibung."""
        self.project(tickets=[
            ticket_record("T1", "Titel", state="waiting-merge",
                          waiting_note="PR #6",
                          description="Bitte warten.")])

        rows = self.cli.ticket_items("proj")

        self.assertEqual("WARTET AUF MERGE", rows[0]["state"])
        self.assertEqual("Bitte warten.", rows[0]["description"])


class PriorityCommandWaitingTest(unittest.TestCase):
    """``vibe priority <projekt> list`` nennt wartende Pakete in der Liste."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.workspace = self.base / "ws"
        self.workspace.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.cli = load_cli(self.workspace, self.home)

    def test_priority_list_names_a_waiting_package(self):
        """Vorbedingung: ``PACKAGE_ORDER="T1,T2"``; T1 wartet auf Merge, T2
        ist offen.
        Aktion: ``cmd_priority("proj", "list")`` mit eingefangenem stdout.
        Erwartung: Die Ausgabezeile zu T1 nennt „wartet auf Merge“.
        Fehlerfall: Wartende Pakete erscheinen in der Priorisierungsliste ohne
        Zusatz und sind von offenen nicht zu unterscheiden.
        """
        make_project(
            self.workspace,
            tickets=[
                ticket_record("T1", "Wartet", state="waiting-merge",
                              waiting_note="PR #6"),
                ticket_record("T2", "Offen"),
            ],
            env_text='TYPE=generic\nPACKAGE_ORDER="T1,T2"\n',
        )
        self.cli._pm.clear()

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.cli.cmd_priority("proj", "list")

        text = output.getvalue()
        lines = [line for line in text.splitlines() if line.startswith("  T1")]
        self.assertTrue(lines, text)
        self.assertRegex(lines[0], r"(?i)wartet auf merge", text)


class RunnerWiringTest(unittest.TestCase):
    """Der PR-only-Rückfall ruft ``mark-waiting`` statt ``mark-blocked`` auf."""

    def shell_function(self, text, marker):
        start = text.find(marker)
        if start < 0:
            return ""
        end = text.find("\n}", start)
        return text[start:end + 2] if end >= 0 else text[start:start + 2000]

    def test_pr_only_fallback_uses_mark_waiting_and_keeps_the_log_line(self):
        """Vorbedingung: Quelltext ``bin/vibe-run.sh``.
        Aktion: Funktion ``pr_only_fallback`` ausschneiden.
        Erwartung: Sie ruft ``mark-waiting`` auf, nicht ``mark-blocked``; die
        Logzeile „WARTET AUF MERGE“ bleibt.
        Fehlerfall: Läufer schreibt weiterhin BLOCKIERT statt Wartend.
        """
        text = RUNNER.read_text(encoding="utf-8")
        region = self.shell_function(text, "pr_only_fallback() {")
        self.assertTrue(region, "pr_only_fallback nicht gefunden")
        self.assertIn(WAITING, region, region)
        self.assertIn("mark-waiting", region, region)
        self.assertNotIn("mark-blocked", region, region)


class NovaWaitingSurfaceTest(unittest.TestCase):
    """Nova-Oberfläche: eigene wartende Spalte, Kachel, Aktion, gelbe Pille."""

    def setUp(self):
        self.text = NOVA.read_text(encoding="utf-8")

    def test_nova_maps_waiting_to_its_label_and_warning_pill(self):
        """Vorbedingung: ``nova-project.js``.
        Aktion: ``nvpStateLabel`` und die Zustands-Pille der Karte pruefen.
        Erwartung (F34): „WARTET AUF MERGE“ wird mit „Wartet auf Merge“
        beschriftet und an der Karte als gelbe Pille ``nv-warn`` dargestellt;
        eine eigene Board-Spalte existiert nicht mehr.
        Fehlerfall: Wartende erscheinen wie offen oder ohne Warnfarbe.
        """
        label = js_region(self.text, "function nvpStateLabel(")
        card = js_region(self.text, "function nvpTicketCard(")

        self.assertTrue(label, "nvpStateLabel nicht gefunden")
        self.assertTrue(card, "nvpTicketCard nicht gefunden")
        self.assertIn(WAITING, label)
        self.assertIn("Wartet auf Merge", label)
        self.assertIn(WAITING, card)
        self.assertIn("nv-warn", card)
        self.assertNotIn("nvpStateColumn", self.text,
                         "Die entfernte Board-Spaltenabbildung existiert noch")

    def test_nova_integrated_list_replaces_the_board_columns(self):
        """Vorbedingung: Arbeit-Aufbau in ``nova-project.js``.
        Aktion: Liste, Karten und Board-Abwesenheit pruefen.
        Erwartung (F34): Die Arbeit ist die integrierte Liste
        ``div.nv-ticket-list[data-nv-ticket-list]``; alle Eintraege laufen
        durch ``nvpTicketCard``, damit wartende Pakete in der Liste
        erscheinen. Die fruehere Spaltenreihenfolge (``open``, ``progress``,
        ``draft``, ``waiting``, ``blocked``, ``proof``, ``done``) und
        ``.nv-board`` existieren nicht mehr.
        Fehlerfall: Spalte fehlt, steht an falscher Stelle oder das Board
        besteht weiter.
        """
        work = js_region(self.text, "var ticketList = el('div'")
        self.assertTrue(work, "Integrierte Arbeitsliste nicht gefunden")
        self.assertIn("data-nv-ticket-list", work)
        self.assertIn("nvpTicketCard", work)
        self.assertIn("allItems.forEach", work)
        self.assertNotIn(".nv-board", self.text)
        self.assertNotIn("nvpBoardColumn", self.text)
        self.assertNotRegex(
            self.text,
            r"\[\s*'open'\s*,\s*'progress'\s*,\s*'draft'\s*,\s*'waiting'"
            r"\s*,\s*'blocked'\s*,\s*'proof'\s*,\s*'done'\s*\]",
            "Die entfernte Board-Spaltenfolge existiert noch",
        )

    def test_nova_overview_counts_waiting_packages(self):
        """Vorbedingung: Übersichts-Kacheln in ``nova-project.js``.
        Aktion: Kacheldefinitionen prüfen.
        Erwartung: Eine Kachel ``waiting`` zählt Pakete mit „WARTET AUF
        MERGE“ und ist mit „Wartet auf Merge“ beschriftet.
        Fehlerfall: Wartende werden in der Übersicht nicht gezählt.
        """
        self.assertIn("'waiting'", self.text)
        self.assertRegex(
            self.text,
            r"\['waiting'[^\]]*nvpCount\([^)]*" + WAITING,
            "Keine Wartend-Kachel",
        )
        self.assertIn("Wartet auf Merge", self.text)

    def test_nova_offers_package_close_for_blocked_and_waiting_packages(self):
        """Vorbedingung: ``nvpOpenTicketDetail`` in ``nova-project.js``.
        Aktion: Bedingung fuer den Abschluss-Button im Kontext-Panel pruefen.
        Erwartung (F34): Der Button erscheint bei ``BLOCKIERT`` und bei
        ``WARTET AUF MERGE``, aber nur fuer Pakete (nicht fuer Feedback).
        Fehlerfall: Wartende Pakete lassen sich nicht ueber die GUI schliessen.
        """
        region = js_region(self.text, "function nvpOpenTicketDetail(")
        self.assertTrue(region, "nvpOpenTicketDetail nicht gefunden")
        condition = (
            r"row\.state\s*===\s*'BLOCKIERT'[\s\S]{0,200}"
            r"row\.state\s*===\s*'WARTET AUF MERGE'"
            r"|row\.state\s*===\s*'WARTET AUF MERGE'[\s\S]{0,200}"
            r"row\.state\s*===\s*'BLOCKIERT'"
            r"|\[\s*'BLOCKIERT'\s*,\s*'WARTET AUF MERGE'\s*\]\.includes\("
        )
        self.assertRegex(region, condition)
        self.assertIn("kind === 'package'", region)
        self.assertIn("package-close", region)

    def test_nova_waiting_pill_uses_the_warning_colors(self):
        """Vorbedingung: Status-Pille für Wartende in ``nova-project.js``.
        Aktion: Zuordnung von „WARTET AUF MERGE“ zu einer CSS-Klasse prüfen.
        Erwartung: Wartende erhalten ``nv-warn`` (gelb).
        Fehlerfall: Wartende erscheinen wie blockiert oder ohne Farbe.
        """
        self.assertRegex(
            self.text,
            WAITING + r"[\s\S]{0,400}nv-warn|nv-warn[\s\S]{0,400}" + WAITING,
            "Keine gelbe Pille für WARTET AUF MERGE",
        )

    def test_english_translation_names_waiting_for_merge(self):
        """Vorbedingung: ``bin/web/i18n.js``.
        Aktion: Wörterbuch prüfen.
        Erwartung: ``"Wartet auf Merge": "Waiting for merge"``.
        Fehlerfall: Englische Oberfläche zeigt den deutschen Text.
        """
        text = I18N.read_text(encoding="utf-8")

        self.assertIn('"Wartet auf Merge"', text)
        self.assertRegex(
            text, r'"Wartet auf Merge"\s*:\s*"Waiting for merge"',
            "Englische Übersetzung fehlt",
        )

    def test_german_dictionary_keeps_the_status_label(self):
        """Vorbedingung: ``bin/web/i18n.js`` mit den Blöcken ``DICTS.en`` und
        ``DICTS.de``.
        Aktion: Nur den ``de``-Bereich ab ``de: {`` prüfen.
        Erwartung: ``DICTS.de`` enthält das Identitätspaar
        ``"Wartet auf Merge": "Wartet auf Merge"``; der ``en``-Eintrag
        („Waiting for merge“) bleibt davon unberührt.
        Fehlerfall: ``tr('Wartet auf Merge')`` fällt bei deutscher Oberfläche
        auf den englischen Default zurück.
        """
        text = I18N.read_text(encoding="utf-8")
        marker = "    de: {"
        self.assertIn(marker, text, "DICTS.de nicht gefunden")
        de_region = text[text.index(marker):]

        self.assertRegex(
            de_region,
            r'"Wartet auf Merge"\s*:\s*"Wartet auf Merge"',
            "Deutsches Identitätspaar fehlt in DICTS.de",
        )
        self.assertRegex(
            text[:text.index(marker)],
            r'"Wartet auf Merge"\s*:\s*"Waiting for merge"',
            "Englischer Eintrag muss unverändert bleiben",
        )


class ClassicWaitingSurfaceTest(unittest.TestCase):
    """Klassische Oberfläche: Wartend gelb, BLOCKIERT bleibt rot."""

    def test_classic_ticket_pill_marks_waiting_as_warning(self):
        """Vorbedingung: Statusklassen-Zuordnung in ``bin/web/app.js``.
        Aktion: Zuordnung prüfen.
        Erwartung: „WARTET AUF MERGE“ wird der Klasse ``warn`` zugeordnet;
        BLOCKIERT bleibt ``bad``.
        Fehlerfall: Wartende erscheinen rot wie blockiert.
        """
        text = APP_JS.read_text(encoding="utf-8")

        self.assertRegex(text, WAITING + r"[\s\S]{0,400}warn",
                         "Keine warn-Klasse für WARTET AUF MERGE")
        self.assertRegex(text, r"BLOCKIERT[\s\S]{0,120}bad",
                         "BLOCKIERT muss weiterhin bad bleiben")


if __name__ == "__main__":
    unittest.main()
