"""B3 (neu vergeben): Abgeschlossene Pakete mit zitierten Markern.

Der Projektordner meldete ein gemergtes, abgehaktes Paket weiterhin als
„WARTET AUF MERGE“, weil sein Block als Nutzer-Evidenz wörtlich eine
``WARTET AUF MERGE:``-Zeile enthält. Die Zustandserkennung prüfte die
Marker-Substrings über den ganzen Block **vor** der Abhaken-Prüfung.

Die Fälle leiten sich aus FEEDBACK.md (B3), SPEC.md („Erledigt bedeutet:
Akzeptanzkriterien erfüllt und Nachweise vorhanden.“, „Blockierte Einträge
werden nicht automatisch als erledigt interpretiert.“) und den GUI-Anforderungen
ab:

* Erledigt-Vorrang: Ein abgehaktes Paket mit gültigem Nachweis gilt überall
  als erledigt, auch wenn sein Blocktext zitierte ``BLOCKIERT:``- oder
  ``WARTET AUF MERGE:``-Zeilen enthält.
* Nicht abgehakte Einträge mit echten Markern behalten ihre Zustände;
  BLOCKIERT wiegt weiterhin schwerer als WARTET AUF MERGE.
* Ein abgehaktes Feedback ohne gültigen Nachweis bleibt im Markenzustand
  (nicht erledigt, nicht „ohne Nachweis“).
* Die klassische Oberfläche (``app.js``) bietet „Paket abschließen“ für
  blockierte und wartende Paketzeilen, aber nicht für Feedback und nicht für
  erledigte Zeilen; i18n erhält das englische und das deutsche Paar.

Browser stehen in dieser Umgebung nicht zur Verfügung; die GUI-Verträge
werden deshalb wie in ``test_ap5_korbat_waiting_state.py`` über
Quelltext-/Strukturprüfungen abgesichert. Alle Zustandsfälle laufen gegen
temporäre Projektordner mit einem echten lokalen Git-Repository (für
``proof_ok``); keine produktive ``HOME``/``VIBE``-Konfiguration, keine
Netzaufrufe, keine Modellaufrufe.

Run:

    python3 -m unittest tests.unit.test_b3_merged_waiting -v
"""
import importlib.machinery
import importlib.util
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
APP_JS = REPO / "bin" / "web" / "app.js"
I18N = REPO / "bin" / "web" / "i18n.js"

WAITING = "WARTET AUF MERGE"
BLOCKED = "BLOCKIERT"
DONE = "erledigt"
CLOSE_LABEL = "Paket abschließen"


# --------------------------------------------------------------------------
# Ladepfade und Fixtures
# --------------------------------------------------------------------------
def load_packages():
    """Lädt ``bin/vibe_packages.py`` als eigenes Modul."""
    loader = importlib.machinery.SourceFileLoader(
        "vibe_packages_b3_merged_waiting_under_test", str(PACKAGES)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


def load_cli(vibe_root, home):
    """Lädt ``bin/vibe`` als Modul mit isoliertem VIBE und HOME."""
    old = {key: os.environ.get(key)
           for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_b3_merged_waiting_cli_under_test", str(CLI)
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


def init_git_repo(path):
    """Legt ein Repository mit einem echten Commit an; liefert den Kurzhash.

    ``proof_ok`` prüft den Commit mit ``git cat-file`` im Projektordner; ohne
    ein echtes Repository wäre jeder Nachweis ungültig und die
    Erledigt-Erkennung ließe sich nicht von der Marker-Erkennung trennen.
    """
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "init",
        ],
        cwd=str(path),
        check=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(path),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def make_project(root, tickets="", feedback="", env_text="TYPE=generic\n"):
    """Temporäres Projekt mit TICKETS.md und FEEDBACK.md.

    Das Projekt liegt unter einem vom Test angelegten Git-Repository; der
    Commit-Hash muss deshalb vor dem Schreiben der Blöcke bekannt sein und
    wird von den Tests über ``self.commit`` eingesetzt.
    """
    project = Path(root) / "proj"
    (project / ".vibe").mkdir(parents=True)
    (project / ".vibe" / "project.env").write_text(env_text, encoding="utf-8")
    (project / "TICKETS.md").write_text(
        "# TICKETS\n\n" + tickets, encoding="utf-8")
    (project / "FEEDBACK.md").write_text(
        "# FEEDBACK\n\n" + feedback, encoding="utf-8")
    return project


def js_region(text, marker, fallback=6000):
    """Schneidet den Quelltextabschnitt ab ``marker`` bis zur nächsten
    Top-Level-Funktion; ohne Treffer einen leeren String."""
    start = text.find(marker)
    if start < 0:
        return ""
    end = text.find("\nfunction ", start + len(marker))
    if end < 0:
        end = start + fallback
    return text[start:end]


def proof_line(commit, name="test_b3_merged_waiting.py"):
    """Nachweiszeile im Projektformat: Commit plus Test."""
    return "  Commit: %s; Test: tests/unit/%s\n" % (commit, name)


# --------------------------------------------------------------------------
# AK1/AK2/AK3: ``bin/vibe`` — _parse_entry
# --------------------------------------------------------------------------
class TicketEntryDonePrecedenceTest(unittest.TestCase):
    """``_parse_entry``: erledigt vor zitierten Markern, Marker bleiben sonst."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.workspace = self.base / "ws"
        self.workspace.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.commit = init_git_repo(self.workspace)
        self.cli = load_cli(self.workspace, self.home)

    def project(self, tickets="", feedback=""):
        project = make_project(
            self.workspace, tickets=tickets, feedback=feedback)
        self.cli._pm.clear()
        return project

    def parsed(self, project, filename, need_proof):
        path = project / filename
        entries = self.cli._feedback_scan(
            self.cli._read_text(path))
        self.assertTrue(entries, "Kein Eintrag erkannt")
        return self.cli._parse_entry(
            entries[0], str(project), need_proof=need_proof)

    def test_checked_ticket_with_quoted_waiting_marker_is_done(self):
        """AK1. Vorbedingung: TICKETS.md-Paket ist abgehakt, trägt einen
        gültigen Nachweis und zitiert als Beschreibungstext wörtlich
        ``WARTET AUF MERGE:``.
        Aktion: ``_feedback_scan`` + ``_parse_entry(..., need_proof=False)``.
        Erwartung: state ``erledigt`` (nicht ``WARTET AUF MERGE``).
        Fehlerfall: Das gemergte Paket bleibt als wartend klassifiziert.
        """
        project = self.project(tickets=(
            "- [x] T1 Gemergt\n"
            "  Beschreibung: Ausgabe des Läufers:\n"
            "  WARTET AUF MERGE: AP5 — Merge-Request #6; danach: close\n"
            + proof_line(self.commit)
        ))

        parsed = self.parsed(project, "TICKETS.md", need_proof=False)

        self.assertEqual(DONE, parsed["state"], parsed)

    def test_checked_ticket_with_quoted_blocked_marker_is_done(self):
        """AK1. Vorbedingung: abgehaktes TICKETS.md-Paket mit gültigem
        Nachweis und zitiertem ``BLOCKIERT:``-Text.
        Aktion: ``_parse_entry(..., need_proof=False)``.
        Erwartung: state ``erledigt`` (nicht ``BLOCKIERT``).
        Fehlerfall: Ein erledigtes Paket bleibt blockiert.
        """
        project = self.project(tickets=(
            "- [x] T2 Gemergt\n"
            "  Beschreibung: Zitat:\n"
            "  BLOCKIERT: alter Vermerk aus einem früheren Lauf\n"
            + proof_line(self.commit)
        ))

        parsed = self.parsed(project, "TICKETS.md", need_proof=False)

        self.assertEqual(DONE, parsed["state"], parsed)

    def test_checked_feedback_with_quoted_waiting_marker_and_proof_is_done(self):
        """AK2. Vorbedingung: FEEDBACK.md-Eintrag ist abgehakt, hat einen
        gültigen Nachweis und zitiert ``WARTET AUF MERGE:``.
        Aktion: ``_parse_entry(..., need_proof=True)``.
        Erwartung: state ``erledigt``.
        Fehlerfall: Feedback bleibt trotz Nachweis im Wartezustand.
        """
        project = self.project(feedback=(
            "- [x] F1 Erledigt\n"
            "  Beschreibung: Zitat:\n"
            "  WARTET AUF MERGE: PR #9 wartet\n"
            + proof_line(self.commit)
        ))

        parsed = self.parsed(project, "FEEDBACK.md", need_proof=True)

        self.assertEqual(DONE, parsed["state"], parsed)

    def test_checked_feedback_with_quoted_blocked_marker_and_proof_is_done(self):
        """AK2. Vorbedingung: abgehaktes Feedback mit gültigem Nachweis und
        zitiertem ``BLOCKIERT:``.
        Aktion: ``_parse_entry(..., need_proof=True)``.
        Erwartung: state ``erledigt``.
        Fehlerfall: Feedback bleibt blockiert, obwohl es belegt erledigt ist.
        """
        project = self.project(feedback=(
            "- [x] F2 Erledigt\n"
            "  Beschreibung: Zitat:\n"
            "  BLOCKIERT: extern\n"
            + proof_line(self.commit)
        ))

        parsed = self.parsed(project, "FEEDBACK.md", need_proof=True)

        self.assertEqual(DONE, parsed["state"], parsed)

    def test_unchecked_ticket_with_genuine_waiting_marker_stays_waiting(self):
        """AK3. Vorbedingung: offenes TICKETS.md-Paket mit echtem
        ``WARTET AUF MERGE:``.
        Aktion: ``_parse_entry(..., need_proof=False)``.
        Erwartung: state ``WARTET AUF MERGE``.
        Fehlerfall: Der neue Erledigt-Vorrang verdeckt echte Wartezustände.
        """
        project = self.project(tickets=(
            "- [ ] T3 Wartet\n  WARTET AUF MERGE: PR #6\n"))

        parsed = self.parsed(project, "TICKETS.md", need_proof=False)

        self.assertEqual(WAITING, parsed["state"], parsed)

    def test_unchecked_ticket_with_genuine_blocked_marker_stays_blocked(self):
        """AK3. Vorbedingung: offenes TICKETS.md-Paket mit echtem
        ``BLOCKIERT:``.
        Aktion: ``_parse_entry(..., need_proof=False)``.
        Erwartung: state ``BLOCKIERT``.
        Fehlerfall: Blockierte Einträge werden als erledigt interpretiert.
        """
        project = self.project(tickets=(
            "- [ ] T4 Blockiert\n  BLOCKIERT: extern\n"))

        parsed = self.parsed(project, "TICKETS.md", need_proof=False)

        self.assertEqual(BLOCKED, parsed["state"], parsed)

    def test_unchecked_ticket_with_both_markers_stays_blocked(self):
        """AK3. Vorbedingung: offenes TICKETS.md-Paket trägt beide echten
        Marker.
        Aktion: ``_parse_entry(..., need_proof=False)``.
        Erwartung: state ``BLOCKIERT`` (schwerer wiegt).
        Fehlerfall: WARTET verdrängt den Blockierzustand.
        """
        project = self.project(tickets=(
            "- [ ] T5 Beides\n"
            "  WARTET AUF MERGE: PR #7\n"
            "  BLOCKIERT: extern\n"
        ))

        parsed = self.parsed(project, "TICKETS.md", need_proof=False)

        self.assertEqual(BLOCKED, parsed["state"], parsed)

    def test_checked_feedback_with_genuine_waiting_marker_but_no_proof_keeps_marker(self):
        """AK3. Vorbedingung: FEEDBACK.md ist abgehakt und trägt einen echten
        ``WARTET AUF MERGE:``-Marker, aber keinen gültigen Nachweis.
        Aktion: ``_parse_entry(..., need_proof=True)``.
        Erwartung: state ``WARTET AUF MERGE`` — nicht ``erledigt`` und nicht
        ``ohne Nachweis``.
        Fehlerfall: Ein bloßes Häkchen ohne Nachweis gilt als erledigt oder
        verliert den Markenzustand.
        """
        project = self.project(feedback=(
            "- [x] F3 Ohne Nachweis\n"
            "  WARTET AUF MERGE: PR #8\n"
            "  Beschreibung: kein Commit\n"
        ))

        parsed = self.parsed(project, "FEEDBACK.md", need_proof=True)

        self.assertEqual(WAITING, parsed["state"], parsed)

    def test_checked_feedback_with_genuine_blocked_marker_but_no_proof_keeps_marker(self):
        """AK3. Vorbedingung: abgehaktes Feedback mit echtem ``BLOCKIERT:``
        und ohne gültigen Nachweis.
        Aktion: ``_parse_entry(..., need_proof=True)``.
        Erwartung: state ``BLOCKIERT`` (nicht ``erledigt``, nicht
        ``ohne Nachweis``).
        Fehlerfall: Blockierte Einträge werden automatisch als erledigt
        interpretiert.
        """
        project = self.project(feedback=(
            "- [x] F4 Ohne Nachweis\n"
            "  BLOCKIERT: extern\n"
            "  Beschreibung: kein Commit\n"
        ))

        parsed = self.parsed(project, "FEEDBACK.md", need_proof=True)

        self.assertEqual(BLOCKED, parsed["state"], parsed)


# --------------------------------------------------------------------------
# AK1/AK3: ``bin/vibe`` — open_items
# --------------------------------------------------------------------------
class OpenItemsDonePrecedenceTest(unittest.TestCase):
    """``open_items`` führt abgehakte belegte Einträge nicht als offen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.workspace = self.base / "ws"
        self.workspace.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.commit = init_git_repo(self.workspace)
        self.cli = load_cli(self.workspace, self.home)

    def project(self, tickets="", feedback=""):
        project = make_project(
            self.workspace, tickets=tickets, feedback=feedback)
        self.cli._pm.clear()
        return project

    def ids(self, items):
        return [row[0] for row in items]

    def test_open_items_omits_done_tickets_with_quoted_markers(self):
        """AK1. Vorbedingung: TICKETS.md enthält zwei abgehakte, belegte
        Pakete, die ``WARTET AUF MERGE:`` bzw. ``BLOCKIERT:`` zitieren.
        Aktion: ``open_items("proj")``.
        Erwartung: Keines der Pakete erscheint als offen, wartend oder
        blockiert.
        Fehlerfall: Das gemergte Paket steht weiterhin in der offenen Liste.
        """
        project = self.project(tickets=(
            "- [x] T1 Gemergt\n"
            "  WARTET AUF MERGE: AP5 — Merge-Request #6\n"
            + proof_line(self.commit) +
            "\n- [x] T2 Gemergt\n"
            "  BLOCKIERT: alter Vermerk\n"
            + proof_line(self.commit)
        ))

        items = self.cli.open_items("proj")

        self.assertNotIn("T1", self.ids(items), items)
        self.assertNotIn("T2", self.ids(items), items)

    def test_open_items_omits_done_feedback_with_quoted_waiting_marker_and_proof(self):
        """AK2. Vorbedingung: FEEDBACK.md enthält einen abgehakten Eintrag mit
        gültigem Nachweis und zitiertem ``WARTET AUF MERGE:``.
        Aktion: ``open_items("proj")``.
        Erwartung: Der Eintrag ist nicht mehr offen/wartend/blockiert.
        Fehlerfall: Erledigtes Feedback bleibt als wartend sichtbar.
        """
        project = self.project(feedback=(
            "- [x] F1 Gemergt\n"
            "  WARTET AUF MERGE: PR #9\n"
            + proof_line(self.commit)
        ))

        items = self.cli.open_items("proj")

        self.assertNotIn("F1", self.ids(items), items)

    def test_open_items_keeps_unchecked_genuine_waiting_and_blocked(self):
        """AK3. Vorbedingung: TICKETS.md enthält ein offenes wartendes und ein
        offenes blockiertes Paket mit echten Markern.
        Aktion: ``open_items("proj")``.
        Erwartung: T1 → ``WARTET AUF MERGE``, T2 → ``BLOCKIERT``.
        Fehlerfall: Der Erledigt-Vorrang verdeckt echte Marken.
        """
        self.project(tickets=(
            "- [ ] T1 Wartet\n  WARTET AUF MERGE: PR #6\n"
            "- [ ] T2 Blockiert\n  BLOCKIERT: extern\n"
        ))

        items = self.cli.open_items("proj")

        self.assertIn(("T1", "Wartet", WAITING), items, items)
        self.assertIn(("T2", "Blockiert", BLOCKED), items, items)


# --------------------------------------------------------------------------
# AK1/AK2/AK3/AK7: ``vibe_packages`` — status_report / priority_view
# --------------------------------------------------------------------------
class StatusReportDonePrecedenceTest(unittest.TestCase):
    """``status_report`` und ``priority_view`` mit zitierten Markern."""

    @classmethod
    def setUpClass(cls):
        cls.module = load_packages()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.commit = init_git_repo(self.root)

    def test_status_report_lists_checked_ticket_with_quoted_waiting_as_done(self):
        """AK1. Vorbedingung: abgehaktes TICKETS.md-Paket mit gültigem
        Nachweis und zitiertem ``WARTET AUF MERGE:``.
        Aktion: ``status_report(project)``.
        Erwartung: Das Paket steht unter ``done``, nicht unter ``waiting``.
        Fehlerfall: Das gemergte Paket gilt weiter als wartend.
        """
        project = make_project(self.root, tickets=(
            "- [x] T1 Gemergt\n"
            "  WARTET AUF MERGE: AP5 — Merge-Request #6\n"
            + proof_line(self.commit)
        ))

        report = self.module.status_report(project)

        self.assertIn("T1", report["done"], report)
        self.assertNotIn("T1", report["waiting"], report)
        self.assertNotIn("T1", report["blocked"], report)
        self.assertNotIn("T1", report["open"], report)

    def test_status_report_lists_checked_ticket_with_quoted_blocked_as_done(self):
        """AK1. Vorbedingung: abgehaktes TICKETS.md-Paket mit gültigem
        Nachweis und zitiertem ``BLOCKIERT:``.
        Aktion: ``status_report(project)``.
        Erwartung: Das Paket steht unter ``done``, nicht unter ``blocked``.
        Fehlerfall: Ein belegtes Paket bleibt blockiert.
        """
        project = make_project(self.root, tickets=(
            "- [x] T2 Gemergt\n"
            "  BLOCKIERT: alter Vermerk\n"
            + proof_line(self.commit)
        ))

        report = self.module.status_report(project)

        self.assertIn("T2", report["done"], report)
        self.assertNotIn("T2", report["blocked"], report)

    def test_status_report_lists_checked_feedback_with_quoted_waiting_as_done(self):
        """AK2. Vorbedingung: abgehaktes FEEDBACK.md mit gültigem Nachweis
        und zitiertem ``WARTET AUF MERGE:``.
        Aktion: ``status_report(project)``.
        Erwartung: Der Eintrag steht unter ``done``, nicht unter ``waiting``.
        Fehlerfall: Erledigtes Feedback bleibt wartend.
        """
        project = make_project(self.root, feedback=(
            "- [x] F1 Gemergt\n"
            "  WARTET AUF MERGE: PR #9\n"
            + proof_line(self.commit)
        ))

        report = self.module.status_report(project)

        self.assertIn("F1", report["done"], report)
        self.assertNotIn("F1", report["waiting"], report)

    def test_status_report_keeps_unchecked_waiting_and_blocked(self):
        """AK3. Vorbedingung: ein offenes wartendes und ein offenes
        blockiertes Paket mit echten Markern.
        Aktion: ``status_report(project)``.
        Erwartung: ``waiting`` enthält T1, ``blocked`` enthält T2.
        Fehlerfall: Erledigt-Vorrang verdeckt echte Marken.
        """
        project = make_project(self.root, tickets=(
            "- [ ] T1 Wartet\n  WARTET AUF MERGE: PR #6\n"
            "- [ ] T2 Blockiert\n  BLOCKIERT: extern\n"
        ))

        report = self.module.status_report(project)

        self.assertEqual(["T1"], report["waiting"], report)
        self.assertIn("T2", report["blocked"], report)
        self.assertNotIn("T1", report["done"], report)
        self.assertNotIn("T2", report["done"], report)

    def test_status_report_keeps_checked_feedback_without_proof_in_marker_state(self):
        """AK3. Vorbedingung: abgehaktes Feedback mit echtem
        ``WARTET AUF MERGE:``, aber ohne gültigen Nachweis.
        Aktion: ``status_report(project)``.
        Erwartung: Der Eintrag bleibt unter ``waiting`` (nicht ``done``,
        nicht ``open``).
        Fehlerfall: Häkchen ohne Nachweis wird als erledigt gewertet.
        """
        project = make_project(self.root, feedback=(
            "- [x] F2 Ohne Nachweis\n"
            "  WARTET AUF MERGE: PR #8\n"
        ))

        report = self.module.status_report(project)

        self.assertIn("F2", report["waiting"], report)
        self.assertNotIn("F2", report["done"], report)

    def test_priority_view_treats_checked_proven_package_with_quoted_waiting_as_done(self):
        """AK7. Vorbedingung: ``PACKAGE_ORDER="T1,T2"``; T1 ist abgehakt,
        belegt und zitiert ``WARTET AUF MERGE:``; T2 ist offen.
        Aktion: ``priority_view(project)``.
        Erwartung: ``order`` status T1 = ``erledigt``; ``standard`` enthält
        T1 nicht und zeigt T2 als ``offen``.
        Fehlerfall: Die Ansichten weichen von ``status_report`` ab.
        """
        project = make_project(
            self.root,
            tickets=(
                "- [x] T1 Gemergt\n"
                "  WARTET AUF MERGE: PR #6\n"
                + proof_line(self.commit) +
                "\n- [ ] T2 Offen\n"
            ),
            env_text='TYPE=generic\nPACKAGE_ORDER="T1,T2"\n',
        )

        view = self.module.priority_view(project)

        by_id = {entry["id"]: entry for entry in view["order"]}
        self.assertEqual(DONE, by_id["T1"]["status"], view)
        self.assertNotIn("T1", [entry["id"] for entry in view["standard"]],
                         view)
        standard = {entry["id"]: entry for entry in view["standard"]}
        self.assertEqual("offen", standard["T2"]["status"], view)

    def test_priority_view_keeps_genuine_waiting_unchanged(self):
        """AK7. Vorbedingung: ``PACKAGE_ORDER="T1,T2"``; T1 wartet echt,
        T2 ist offen.
        Aktion: ``priority_view(project)``.
        Erwartung: ``order`` und ``standard`` zeigen für T1 weiterhin
        ``wartet auf Merge``.
        Fehlerfall: Die Erledigt-Erkennung verändert echte Wartezustände.
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
        standard = {entry["id"]: entry for entry in view["standard"]}
        self.assertEqual("wartet auf Merge", by_id["T1"]["status"], view)
        self.assertEqual("wartet auf Merge", standard["T1"]["status"], view)


# --------------------------------------------------------------------------
# AK5: klassische Oberfläche — „Paket abschließen“
# --------------------------------------------------------------------------
class ClassicGuiPackageCloseTest(unittest.TestCase):
    """AK5: ``app.js`` bietet den Abschluss-Button nur passenden Paketen."""

    def setUp(self):
        self.text = APP_JS.read_text(encoding="utf-8")
        self.tickets = js_region(self.text, "function ticketCard(")
        self.feedback = js_region(self.text, "function feedbackCard(")

    def test_classic_ticket_card_offers_package_close_button(self):
        """AK5. Vorbedingung: ``bin/web/app.js``, Funktion ``ticketCard``.
        Aktion: Quelltext der Ticketkarte prüfen.
        Erwartung: Sie enthält den Button „Paket abschließen“.
        Fehlerfall: In der klassischen Oberfläche fehlt der Abschluss-Button.
        """
        self.assertTrue(self.tickets, "ticketCard nicht gefunden")
        self.assertIn(CLOSE_LABEL, self.tickets)

    def test_classic_package_close_posts_to_the_package_endpoint(self):
        """AK5. Vorbedingung: Abschluss-Button in ``ticketCard``.
        Aktion: Aufruf von ``/api/package`` prüfen.
        Erwartung: Der Aufruf sendet ``name``, ``id`` und
        ``action: 'close'``.
        Fehlerfall: Der Button ruft einen falschen Endpunkt oder ohne ID auf.
        """
        call = re.search(
            r"api\(\s*['\"]/api/package['\"]\s*,\s*\{([^}]*)\}",
            self.tickets,
        )
        self.assertIsNotNone(
            call, "Kein api('/api/package', …)-Aufruf in ticketCard")
        arguments = call.group(1)
        self.assertIn("name", arguments, call.group(0))
        self.assertRegex(arguments, r"id\s*:\s*i\.id|id\b",
                         call.group(0))
        self.assertRegex(arguments, r"action\s*:\s*['\"]close['\"]",
                         call.group(0))

    def test_classic_package_close_is_limited_to_blocked_and_waiting_tickets(self):
        """AK5. Vorbedingung: ``ticketCard`` in ``app.js``.
        Aktion: Bedingung für den Abschluss-Button prüfen.
        Erwartung: Der Button ist an die Zustände ``BLOCKIERT`` und
        ``WARTET AUF MERGE`` gebunden (echte ``i.state``-Prüfung); damit
        erscheint er nicht für ``offen``, ``ohne Nachweis`` oder ``erledigt``.
        Fehlerfall: Der Button erscheint bei jedem Paket oder fehlt bei
        wartenden Paketen.
        """
        conditions = (
            r"i\.state\s*===?\s*['\"]BLOCKIERT['\"][\s\S]{0,200}"
            r"i\.state\s*===?\s*['\"]WARTET AUF MERGE['\"]",
            r"i\.state\s*===?\s*['\"]WARTET AUF MERGE['\"][\s\S]{0,200}"
            r"i\.state\s*===?\s*['\"]BLOCKIERT['\"]",
            r"\[\s*['\"]BLOCKIERT['\"]\s*,\s*['\"]WARTET AUF MERGE['\"]\s*\]"
            r"\.includes\(\s*i\.state\s*\)",
            r"\[\s*['\"]WARTET AUF MERGE['\"]\s*,\s*['\"]BLOCKIERT['\"]\s*\]"
            r"\.includes\(\s*i\.state\s*\)",
        )
        self.assertTrue(
            any(re.search(pattern, self.tickets) for pattern in conditions),
            "Keine Zustandsbindung an BLOCKIERT und WARTET AUF MERGE:\n"
            + self.tickets,
        )

    def test_classic_package_close_reports_backend_message_and_refreshes(self):
        """AK5. Vorbedingung: Abschluss-Button in ``ticketCard``.
        Aktion: Erfolgs-/Fehlerbehandlung um den Button prüfen.
        Erwartung: Die Backend-Meldung wird per ``toast`` gezeigt und die
        Projektansicht bei Erfolg über ``detail(name)`` neu geladen.
        Fehlerfall: Fehler bleiben unsichtbar oder die Ansicht bleibt veraltet.
        """
        position = self.tickets.find(CLOSE_LABEL)
        self.assertGreaterEqual(position, 0, "Abschluss-Button fehlt")
        window = self.tickets[max(0, position - 800):position + 300]
        self.assertIn("/api/package", window)
        self.assertIn("toast", window)
        self.assertIn("message", window)
        self.assertIn("detail(name)", window)

    def test_classic_feedback_card_offers_no_package_close(self):
        """AK5. Vorbedingung: ``feedbackCard`` in ``app.js``.
        Aktion: Quelltext der Feedback-Karte prüfen.
        Erwartung: Kein „Paket abschließen“-Button und kein
        ``/api/package``-Aufruf.
        Fehlerfall: Feedback ließe sich fälschlich als Paket abschließen.
        """
        self.assertTrue(self.feedback, "feedbackCard nicht gefunden")
        self.assertNotIn(CLOSE_LABEL, self.feedback)
        self.assertNotIn("/api/package", self.feedback)


# --------------------------------------------------------------------------
# AK6: i18n
# --------------------------------------------------------------------------
class I18nPackageCloseTest(unittest.TestCase):
    """AK6: englische Übersetzung und deutsches Identitätspaar."""

    def setUp(self):
        self.text = I18N.read_text(encoding="utf-8")
        self.marker = "    de: {"
        self.assertIn(self.marker, self.text, "DICTS.de nicht gefunden")
        split = self.text.index(self.marker)
        self.en_region = self.text[:split]
        self.de_region = self.text[split:]

    def test_english_dictionary_translates_package_close(self):
        """AK6. Vorbedingung: ``bin/web/i18n.js`` mit ``DICTS.en``.
        Aktion: Eintrag für „Paket abschließen“ im englischen Bereich suchen.
        Erwartung: Ein nichtleerer englischer Wert, der „package“ nennt und
        nicht der deutsche Schlüssel ist.
        Fehlerfall: ``tr('Paket abschließen')`` fällt in der englischen
        Oberfläche auf den deutschen Text zurück.
        """
        match = re.search(
            r'"Paket abschließen"\s*:\s*"([^"]*)"', self.en_region)
        self.assertIsNotNone(match, "Kein englischer Eintrag")
        value = match.group(1).strip()
        self.assertTrue(value, "Englischer Eintrag ist leer")
        self.assertNotEqual(value, CLOSE_LABEL,
                            "Englischer Eintrag ist nur der Schlüssel")
        self.assertRegex(value, r"(?i)package",
                         "Englischer Eintrag nennt kein Paket: " + value)

    def test_german_dictionary_keeps_package_close_identity(self):
        """AK6. Vorbedingung: ``bin/web/i18n.js`` mit ``DICTS.de``.
        Aktion: Nur den ``de``-Bereich ab ``de: {`` prüfen.
        Erwartung: Identitätspaar
        ``"Paket abschließen": "Paket abschließen"``.
        Fehlerfall: Die deutsche Oberfläche zeigt einen englischen Default.
        """
        self.assertRegex(
            self.de_region,
            r'"Paket abschließen"\s*:\s*"Paket abschließen"',
            "Deutsches Identitätspaar fehlt in DICTS.de",
        )


if __name__ == "__main__":
    unittest.main()
