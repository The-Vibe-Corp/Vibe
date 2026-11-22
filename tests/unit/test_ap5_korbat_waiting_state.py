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
* GUI: Nova-Spalte ``waiting`` (zwischen offen und blockiert), Kachel,
  „Paket abschließen“ auch für wartende Pakete (nur Pakete), gelbe Pille;
  klassische Oberfläche: WARTET → ``warn``, BLOCKIERT bleibt ``bad``;
  i18n EN „Waiting for merge“.

Keine Netzverbindungen, keine Modellaufrufe, keine produktiven Pfade.

Run:

    python3 -m unittest tests.unit.test_ap5_korbat_waiting_state -v
"""
import contextlib
import importlib.machinery
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


def make_project(root, tickets="", feedback="", env_text="TYPE=generic\n"):
    project = Path(root) / "proj"
    (project / ".vibe").mkdir(parents=True)
    (project / ".vibe" / "project.env").write_text(env_text, encoding="utf-8")
    (project / "TICKETS.md").write_text(
        "# TICKETS\n\n" + tickets, encoding="utf-8")
    (project / "FEEDBACK.md").write_text(
        "# FEEDBACK\n\n" + feedback, encoding="utf-8")
    return project


def js_region(text, marker, fallback=6000):
    start = text.find(marker)
    if start < 0:
        return ""
    end = text.find("\nfunction ", start + len(marker))
    if end < 0:
        end = start + fallback
    return text[start:end]


class WaitingMarkerUnitTest(unittest.TestCase):
    """Semantik des neuen Markers und des Nachweis-Aufräumens."""

    @classmethod
    def setUpClass(cls):
        cls.module = load_packages()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_is_waiting_merge_is_true_for_the_new_marker_only(self):
        """Vorbedingung: Blöcke mit WARTET- bzw. BLOCKIERT-Marker.
        Aktion: ``is_waiting_merge`` und ``is_blocked`` auswerten.
        Erwartung: WARTET → ``is_waiting_merge`` True, ``is_blocked`` False;
        BLOCKIERT → ``is_blocked`` True, ``is_waiting_merge`` False.
        Fehlerfall: Marker werden verwechselt oder ``is_blocked`` verändert.
        """
        waiting = "- [ ] T1 Wartet\n  WARTET AUF MERGE: MR offen\n"
        blocked = "- [ ] T2 Blockiert\n  BLOCKIERT: extern\n"

        self.assertTrue(self.module.is_waiting_merge(waiting))
        self.assertFalse(self.module.is_blocked(waiting))
        self.assertTrue(self.module.is_blocked(blocked))
        self.assertFalse(self.module.is_waiting_merge(blocked))

    def test_sync_proof_removes_waiting_and_blocked_markers(self):
        """Vorbedingung: Projektblock enthält WARTET- und BLOCKIERT-Zeilen;
        die Arbeitskopie liefert denselben Block abgehakt mit Nachweis.
        Aktion: ``sync_proof(..., require_commit=False)``.
        Erwartung: Beide Markerzeilen sind im Projekt entfernt, Checkbox und
        Nachweis sind übernommen.
        Fehlerfall: WARTET bleibt stehen und das Paket gilt weiter als wartend.
        """
        project = make_project(
            self.root,
            tickets=(
                "- [ ] T1 Paket\n"
                "  Beschreibung: offen\n"
                "  WARTET AUF MERGE: alter PR\n"
                "  BLOCKIERT: alter Vermerk\n"
            ),
        )
        worktree = self.root / "wt"
        worktree.mkdir()
        (worktree / "TICKETS.md").write_text(
            "# TICKETS\n\n"
            "- [x] T1 Paket\n"
            "  Beschreibung: offen\n"
            "  Commit: abc1234; Test: test_t1\n",
            encoding="utf-8",
        )

        changed, message = self.module.sync_proof(
            project, worktree, "T1", require_commit=False
        )

        self.assertTrue(changed, message)
        text = (project / "TICKETS.md").read_text(encoding="utf-8")
        self.assertIn("- [x] T1", text)
        self.assertNotIn(WAITING, text)
        self.assertNotIn("BLOCKIERT", text)
        self.assertIn("Test: test_t1", text)


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
            tickets=(
                "- [ ] T1 Wartet\n  Beschreibung: PR offen\n\n"
                "- [ ] T2 Offen\n  Beschreibung: frei\n"
            ),
        )

    def mark_waiting(self, note="PR #6 wartet"):
        return subprocess.run(
            [sys.executable, str(PACKAGES), "mark-waiting",
             "--project", str(self.project), "--id", "T1", "--note", note],
            cwd=str(self.root), stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=60,
        )

    def tickets_text(self):
        return (self.project / "TICKETS.md").read_text(encoding="utf-8")

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
        self.assertIn("wartend", (result.stdout + result.stderr).lower())
        lines = self.tickets_text().splitlines()
        self.assertTrue(
            any(line.strip() == WAITING + ": PR #6 wartet"
                and line.startswith("  ") for line in lines),
            self.tickets_text(),
        )

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
        self.assertIn("wartend", output.lower())
        text = self.tickets_text()
        self.assertEqual(text.count(WAITING), 1, text)

    def test_mark_waiting_leaves_other_blocks_unchanged(self):
        """Vorbedingung: T1 und T2 offen.
        Aktion: ``mark-waiting`` für T1 ausführen.
        Erwartung: Nur der Block T1 erhält die Marke; T2 bleibt unverändert.
        Fehlerfall: Marke im falschen Block oder Datei-Umschreibung.
        """
        before = self.tickets_text()

        result = self.mark_waiting()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        after = self.tickets_text()
        t2_before = before[before.index("- [ ] T2"):]
        t2_after = after[after.index("- [ ] T2"):]
        self.assertEqual(t2_before, t2_after)


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
            tickets=(
                "- [ ] T1 Wartet\n  WARTET AUF MERGE: PR #6\n"
                "- [ ] T2 Offen\n"
            ),
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
            tickets=(
                "- [ ] T1 Wartet\n  WARTET AUF MERGE: PR #6\n"
                "- [ ] T2 Offen\n"
            ),
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
            tickets=(
                "- [ ] T1 Wartet\n  WARTET AUF MERGE: PR #6\n"
                "- [ ] T2 Offen\n"
                "- [ ] T3 Blockiert\n  BLOCKIERT: extern\n"
                "- [ ] T4 Beides\n  WARTET AUF MERGE: PR #7\n"
                "  BLOCKIERT: extern\n"
            ),
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
            tickets=(
                "- [ ] T1 Wartet\n  WARTET AUF MERGE: PR #6\n"
                "- [ ] T2 Offen\n"
            ),
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

    def project(self, tickets="", feedback=""):
        project = make_project(self.workspace, tickets=tickets, feedback=feedback)
        self.cli._pm.clear()
        return project

    def test_open_items_marks_waiting_tickets(self):
        """Vorbedingung: TICKETS.md enthält T1 mit WARTET-Marker (offen).
        Aktion: ``open_items("proj")``.
        Erwartung: T1 erscheint mit Status „WARTET AUF MERGE“.
        Fehlerfall: Status bleibt „offen“ oder Eintrag fehlt.
        """
        self.project(
            tickets="- [ ] T1 Wartet\n  WARTET AUF MERGE: PR #6\n"
        )

        items = self.cli.open_items("proj")

        self.assertIn(("T1", "Wartet", WAITING), items, items)

    def test_open_items_shows_waiting_feedback(self):
        """Vorbedingung: FEEDBACK.md enthält F1 mit WARTET-Marker (offen).
        Aktion: ``open_items("proj")``.
        Erwartung: F1 erscheint mit Status „WARTET AUF MERGE“.
        Fehlerfall: Feedback wartet still weiter als offen oder als erledigt.
        """
        self.project(feedback="- [ ] F1 Wartet\n  WARTET AUF MERGE: PR #8\n")

        items = self.cli.open_items("proj")

        self.assertIn(("F1", "Wartet", WAITING), items, items)

    def test_blocked_wins_when_a_block_carries_both_markers(self):
        """Vorbedingung: T1 trägt WARTET und BLOCKIERT.
        Aktion: ``open_items("proj")`` und ``_parse_entry`` auswerten.
        Erwartung: Status ist „BLOCKIERT“ (schwerer wiegt).
        Fehlerfall: WARTET überdeckt den bestehenden Blockierzustand.
        """
        project = self.project(
            tickets=(
                "- [ ] T1 Beides\n"
                "  WARTET AUF MERGE: PR #6\n"
                "  BLOCKIERT: extern\n"
            )
        )

        items = self.cli.open_items("proj")
        entries = self.cli._feedback_scan(
            self.cli._read_text(project / "TICKETS.md"))
        parsed = self.cli._parse_entry(entries[0], str(project), need_proof=False)

        self.assertIn(("T1", "Beides", "BLOCKIERT"), items, items)
        self.assertEqual("BLOCKIERT", parsed["state"], parsed)

    def test_waiting_marker_ends_the_description_section(self):
        """Vorbedingung: T1 hat einen ``Beschreibung:``-Abschnitt, direkt
        gefolgt von einer ``WARTET AUF MERGE:``-Zeile.
        Aktion: ``_feedback_scan`` und ``_parse_entry(..., need_proof=False)``.
        Erwartung: ``description`` enthält nur „Bitte warten.“; die Marke
        beendet den Abschnitt. ``state`` bleibt „WARTET AUF MERGE“.
        Fehlerfall: Die Marke wird in die Beschreibung eingesogen und erscheint
        im Ticket-Editor als Beschreibungstext.
        """
        project = self.project(
            tickets=(
                "- [ ] T1 Titel\n"
                "  Beschreibung: Bitte warten.\n"
                "  WARTET AUF MERGE: PR #6\n"
            )
        )

        entries = self.cli._feedback_scan(
            self.cli._read_text(project / "TICKETS.md"))
        parsed = self.cli._parse_entry(entries[0], str(project), need_proof=False)

        self.assertEqual("Bitte warten.", parsed["description"], parsed)
        self.assertEqual(WAITING, parsed["state"], parsed)


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
            tickets=(
                "- [ ] T1 Wartet\n  WARTET AUF MERGE: PR #6\n"
                "- [ ] T2 Offen\n"
            ),
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

    def test_nova_maps_waiting_to_its_own_column_and_label(self):
        """Vorbedingung: ``nova-project.js``.
        Aktion: ``nvpStateColumn``/``nvpStateLabel`` prüfen.
        Erwartung: „WARTET AUF MERGE“ → Spalte ``waiting`` und Label
        „Wartet auf Merge“.
        Fehlerfall: Wartende landen in ``blocked`` oder ``open``.
        """
        column = js_region(self.text, "function nvpStateColumn(")
        label = js_region(self.text, "function nvpStateLabel(")

        self.assertTrue(column, "nvpStateColumn nicht gefunden")
        self.assertIn(WAITING, column)
        self.assertIn("waiting", column)
        self.assertIn("Wartet auf Merge", label)

    def test_nova_board_orders_the_waiting_column_between_open_and_blocked(self):
        """Vorbedingung: Board-Aufbau in ``nova-project.js``.
        Aktion: Spaltenliste prüfen.
        Erwartung: vollständige Reihenfolge ``open``, ``progress``, ``draft``,
        ``waiting``, ``blocked``, ``proof``, ``done``; die Wartet-Spalte
        bleibt nach den Arbeitszuständen und vor ``blocked``.
        Fehlerfall: Spalte fehlt, steht an falscher Stelle oder die
        AP3-Spalten ``progress``/``draft`` fehlen.
        """
        # AP3-Board-Vertragsänderung: 'progress' (In Progress) und 'draft'
        # (Entwurf) sind vor 'waiting' neu; die Wartet-Spalte bleibt zwischen
        # den Arbeitszuständen und 'blocked'.
        self.assertRegex(
            self.text,
            r"\[\s*'open'\s*,\s*'progress'\s*,\s*'draft'\s*,\s*'waiting'"
            r"\s*,\s*'blocked'\s*,\s*'proof'\s*,\s*'done'\s*\]",
            "Keine Spaltenfolge open → progress → draft → waiting → blocked "
            "→ proof → done",
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

    def test_nova_offers_package_close_in_blocked_and_waiting_columns(self):
        """Vorbedingung: ``nvpBoardColumn`` in ``nova-project.js``.
        Aktion: Bedingung für den Abschluss-Button prüfen.
        Erwartung: Der Button erscheint in ``blocked`` UND ``waiting``, aber
        nur für Pakete (nicht für Feedback).
        Fehlerfall: Wartende Pakete lassen sich nicht über die GUI schließen.
        """
        region = js_region(self.text, "function nvpBoardColumn(")
        self.assertTrue(region)
        condition = (
            r"column\s*===\s*'blocked'[\s\S]{0,200}column\s*===\s*'waiting'"
            r"|\[\s*'blocked'\s*,\s*'waiting'\s*\]\.includes\(column\)"
            r"|column\s*===\s*'waiting'[\s\S]{0,200}column\s*===\s*'blocked'"
        )
        self.assertRegex(region, condition)
        self.assertIn("!isFeedback", region)
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
