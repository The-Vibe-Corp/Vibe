"""B6: Statusmarken zählen nur an Statuspositionen.

Eine BLOCKIERT:/WARTET AUF MERGE:-Marke zählt genau dann, wenn sie als letzte
nichtleere Blockzeile steht oder im Kopffeld vor der ersten
Beschreibung:/Erwartet:-Zeile; späteste Position gewinnt, BLOCKIERT schlägt
WARTET im Kopffeld. Freitext-Einfügungen zählen nicht. Präzedenz erledigt >
BLOCKIERT > WARTET AUF MERGE > In-Progress > Draft > offen unverändert.
Rotphasenbelege: docs/reviews/B6-test-agent-report.md.

Die Fälle leiten sich aus Arbeitspaket B6 und SPEC.md/FEEDBACK.md ab.

Run:
    python3 -m unittest tests.unit.test_b6_ticket_marker_states -v
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PACKAGES = REPO / "bin" / "vibe_packages.py"
CLI = REPO / "bin" / "vibe"

BLOCKED = "BLOCKIERT"
WAITING = "WARTET AUF MERGE"
BLOCK_MARKER = "BLOCKIERT:"
WAITING_MARKER = "WARTET AUF MERGE:"


def load_packages():
    loader = importlib.machinery.SourceFileLoader(
        "vibe_packages_b6_marker_under_test", str(PACKAGES)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


def load_cli(vibe_root, home):
    old = {key: os.environ.get(key) for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_b6_marker_cli_under_test", str(CLI)
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


# Freitext-Einfügungen wie im Realfall B5: Markenwörter stehen nicht als letzte
# nichtleere Zeile, sondern mitten im Abschlussbericht.
FREE_TEXT_BLOCK = (
    "- [ ] T1 Titel\n"
    "  Beschreibung: offen\n"
    "  BLOCKIERT: eingefügter Bericht\n"
    "  WARTET AUF MERGE: keine\n"
    "  Offen: keine\n"
)

# Realfall-naher B5-Block (offen, Art: Bug, Abschlussberichts-/Laufzeilen).
B5_LIKE_BLOCK = (
    "- [ ] B5 Work packet closing workflow of runner failed on merge conflict\n"
    "  Art: Bug\n"
    "  Beschreibung: On closing AP6-Korbat, origin/dev could not be pulled.\n"
    "  === Abschlussbericht ===\n"
    "  Geschlossen: keine\n"
    "  Blockiert: AP6-Korbat (GitHub-Abschluss fehlgeschlagen)\n"
    "  Wartet auf Merge: keine\n"
    "  Offen: keine\n"
    "  Grund: GitHub-Abschluss fehlgeschlagen\n"
    "  Fast-forward\n"
)

REAL_BLOCKED_BLOCK = (
    "- [ ] T1 Titel\n"
    "  Beschreibung: offen\n"
    "  BLOCKIERT: extern\n"
)

REAL_WAITING_BLOCK = (
    "- [ ] T1 Titel\n"
    "  Beschreibung: offen\n"
    "  WARTET AUF MERGE: PR #6\n"
)


class MarkerLastLineSemanticsTest(unittest.TestCase):
    """``is_blocked``/``is_waiting_merge`` zählen nur Statuspositionen.

    Eine Marke zählt, wenn sie die letzte nichtleere Blockzeile bildet oder im
    Kopffeld vor der ersten ``Beschreibung:``-/``Erwartet:``-Zeile steht.
    Freitext an anderen Positionen zählt nicht.
    """

    @classmethod
    def setUpClass(cls):
        cls.module = load_packages()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_freetext_marker_is_not_a_blocked_state(self):
        """Vorbedingung: Block mit 'BLOCKIERT:' in der Beschreibung, letzte
        nichtleere Zeile ist 'Offen: keine'.
        Aktion: ``is_blocked`` auswerten.
        Erwartung: False (Freitext zählt nicht).
        Fehlerfall: Teilstring-Check erkennt den Freitext als Sperre.
        """
        self.assertFalse(self.module.is_blocked(FREE_TEXT_BLOCK))

    def test_freetext_marker_is_not_a_waiting_state(self):
        """Vorbedingung: Block mit 'WARTET AUF MERGE:' in der Beschreibung,
        letzte nichtleere Zeile ist 'Offen: keine'.
        Aktion: ``is_waiting_merge`` auswerten.
        Erwartung: False (Freitext zählt nicht).
        Fehlerfall: Teilstring-Check erkennt den Freitext als Warten.
        """
        self.assertFalse(self.module.is_waiting_merge(FREE_TEXT_BLOCK))

    def test_real_blocked_marker_at_block_end_counts(self):
        """Vorbedingung: Block endet mit 'BLOCKIERT: extern'.
        Aktion: ``is_blocked``/``is_waiting_merge`` auswerten.
        Erwartung: blocked True, waiting False.
        Fehlerfall: Endmarke wird ignoriert.
        """
        self.assertTrue(self.module.is_blocked(REAL_BLOCKED_BLOCK))
        self.assertFalse(self.module.is_waiting_merge(REAL_BLOCKED_BLOCK))

    def test_real_waiting_marker_at_block_end_counts(self):
        """Vorbedingung: Block endet mit 'WARTET AUF MERGE: PR #6'.
        Aktion: ``is_blocked``/``is_waiting_merge`` auswerten.
        Erwartung: waiting True, blocked False.
        Fehlerfall: Endmarke wird ignoriert.
        """
        self.assertTrue(self.module.is_waiting_merge(REAL_WAITING_BLOCK))
        self.assertFalse(self.module.is_blocked(REAL_WAITING_BLOCK))

    def test_marker_matching_is_case_insensitive_at_block_end(self):
        """Vorbedingung: Block endet mit kleingeschriebener Marke.
        Aktion: ``is_blocked``/``is_waiting_merge`` auswerten.
        Erwartung: Beide erkennen die Marke unabhängig von Groß-/Kleinschreibung.
        Fehlerfall: Groß-/Kleinschreibung wird streng geprüft.
        """
        blocked = "- [ ] T1 Titel\n  beschreibung: offen\n  blockiert: extern\n"
        waiting = "- [ ] T1 Titel\n  beschreibung: offen\n  wartet auf merge: PR #6\n"
        self.assertTrue(self.module.is_blocked(blocked))
        self.assertTrue(self.module.is_waiting_merge(waiting))

    def test_last_marker_wins_over_earlier_opposite_marker(self):
        """Vorbedingung: Block enthält beide Marken, letzte Zeile ist BLOCKIERT.
        Aktion: ``is_blocked``/``is_waiting_merge`` auswerten.
        Erwartung: blocked True, waiting False (nur Endmarke zählt).
        Fehlerfall: Frühere Marke wird mitgezählt.
        """
        block = (
            "- [ ] T1 Titel\n"
            "  WARTET AUF MERGE: PR #6\n"
            "  BLOCKIERT: extern\n"
        )
        self.assertTrue(self.module.is_blocked(block))
        self.assertFalse(self.module.is_waiting_merge(block))

    def test_b5_like_block_is_not_blocked_or_waiting(self):
        """Vorbedingung: B5-ähnlicher Block mit Abschlussberichtszeilen.
        Aktion: ``is_blocked``/``is_waiting_merge`` auswerten.
        Erwartung: Beide False (Block gilt als offen).
        Fehlerfall: Freitext-Marken setzen den Block dauerhaft auf blockiert/wartend.
        """
        self.assertFalse(self.module.is_blocked(B5_LIKE_BLOCK))
        self.assertFalse(self.module.is_waiting_merge(B5_LIKE_BLOCK))

    def test_head_marker_before_description_counts(self):
        """Vorbedingung: Marke steht im Kopffeld direkt vor 'Beschreibung:'.
        Aktion: ``is_blocked``/``is_waiting_merge``.
        Erwartung: Marke zählt (B3-AK3-Platzierung).
        Fehlerfall: Kopffeld-Marker wird ignoriert.
        """
        blocked = "- [ ] T1 Titel\n  BLOCKIERT: extern\n  Beschreibung: offen\n"
        waiting = "- [ ] T1 Titel\n  WARTET AUF MERGE: PR #6\n  Beschreibung: offen\n"
        self.assertTrue(self.module.is_blocked(blocked))
        self.assertFalse(self.module.is_waiting_merge(blocked))
        self.assertTrue(self.module.is_waiting_merge(waiting))
        self.assertFalse(self.module.is_blocked(waiting))

    def test_no_description_line_mid_marker_does_not_count(self):
        """Vorbedingung: Block ohne Beschreibung:/Erwartet:-Zeile; 'BLOCKIERT:'
        steht mitten im Text und nicht als letzte Zeile.
        Aktion: ``is_blocked``.
        Erwartung: False (Regel (b) greift ohne Beschreibung nicht).
        Fehlerfall: Mittenstehender Marker wird trotz fehlender Statusposition gezählt.
        """
        block = (
            "- [ ] T1 Titel\n"
            "  BLOCKIERT: Bericht\n"
            "  Offen: keine\n"
        )
        self.assertFalse(self.module.is_blocked(block))

    def test_tab_indented_marker_with_trailing_whitespace_counts(self):
        """Vorbedingung: Marke ist letzte nichtleere Zeile, mit Tab-Einrückung und
        Trailing-Whitespace am Zeilenende.
        Aktion: ``is_blocked``.
        Erwartung: True.
        Fehlerfall: Einrückung oder nachfolgende Leerzeichen verhindern die Erkennung.
        """
        block = "- [ ] T1 Titel\n  Beschreibung: offen\n\tBLOCKIERT: extern   \n"
        self.assertTrue(self.module.is_blocked(block))

    def test_marker_in_title_does_not_count(self):
        """Vorbedingung: Marke steht im Titel selbst; der Block enthält sonst
        keine Markerzeile.
        Aktion: ``is_blocked``.
        Erwartung: False.
        Fehlerfall: Teilstring im Titel wird als Statusmarke fehlgelesen.
        """
        block = "- [ ] T1 BLOCKIERT: x"
        self.assertFalse(self.module.is_blocked(block))

    def test_head_marker_before_expected_counts(self):
        """Vorbedingung: Marke steht im Kopffeld direkt vor 'Erwartet:'.
        Aktion: ``is_blocked``/``is_waiting_merge``.
        Erwartung: Marke zählt (Erwartet: als Beschreibungsstart).
        Fehlerfall: Nur 'Beschreibung:' wird als Kopfgrenze akzeptiert.
        """
        blocked = "- [ ] T1 Titel\n  BLOCKIERT: extern\n  Erwartet: x\n"
        self.assertTrue(self.module.is_blocked(blocked))

    def test_head_marker_open_and_unproven_checked_variants(self):
        """Vorbedingung: Kopffeld-Marker bei offenem und abgehaktem Block ohne
        Nachweis.
        Aktion: ``is_blocked``.
        Erwartung: In beiden Fällen zählt die Marke.
        Fehlerfall: Checkbox-Zustand beeinflusst die Marker-Erkennung.
        """
        open_block = "- [ ] T1 Titel\n  BLOCKIERT: extern\n  Beschreibung: offen\n"
        checked = "- [x] T1 Titel\n  BLOCKIERT: extern\n  Beschreibung: offen\n"
        self.assertTrue(self.module.is_blocked(open_block))
        self.assertTrue(self.module.is_blocked(checked))

    def test_marker_after_description_not_last_does_not_count(self):
        """Vorbedingung: Marke steht nach 'Beschreibung:', aber nicht als letzte
        nichtleere Zeile.
        Aktion: ``is_blocked``.
        Erwartung: False (Freitext).
        Fehlerfall: Jede zeilenanfangende Marke zählt.
        """
        block = (
            "- [ ] T1 Titel\n"
            "  Beschreibung: offen\n"
            "  BLOCKIERT: Bericht\n"
            "  Offen: keine\n"
        )
        self.assertFalse(self.module.is_blocked(block))

    def test_latest_position_wins_head_blocked_end_waiting(self):
        """Vorbedingung: Kopffeld-BLOCKIERT und Endzeile-WARTET.
        Aktion: ``is_blocked``/``is_waiting_merge``.
        Erwartung: WARTET gewinnt (späteste Position).
        Fehlerfall: Kopffeld-Marke überdeckt die Endzeile.
        """
        block = (
            "- [ ] T1 Titel\n"
            "  BLOCKIERT: head\n"
            "  Beschreibung: offen\n"
            "  WARTET AUF MERGE: end\n"
        )
        self.assertFalse(self.module.is_blocked(block))
        self.assertTrue(self.module.is_waiting_merge(block))

    def test_latest_position_wins_head_waiting_end_blocked(self):
        """Vorbedingung: Kopffeld-WARTET und Endzeile-BLOCKIERT.
        Aktion: ``is_blocked``/``is_waiting_merge``.
        Erwartung: BLOCKIERT gewinnt (späteste Position).
        Fehlerfall: Kopffeld-Marke überdeckt die Endzeile.
        """
        block = (
            "- [ ] T1 Titel\n"
            "  WARTET AUF MERGE: head\n"
            "  Beschreibung: offen\n"
            "  BLOCKIERT: end\n"
        )
        self.assertTrue(self.module.is_blocked(block))
        self.assertFalse(self.module.is_waiting_merge(block))

    def test_blocked_wins_over_waiting_in_head_field(self):
        """Vorbedingung: Beide Marken im Kopffeld vor der Beschreibung.
        Aktion: ``is_blocked``/``is_waiting_merge``.
        Erwartung: BLOCKIERT gewinnt.
        Fehlerfall: WARTET überdeckt BLOCKIERT im Kopffeld.
        """
        block = (
            "- [ ] T1 Titel\n"
            "  WARTET AUF MERGE: head\n"
            "  BLOCKIERT: head2\n"
            "  Beschreibung: offen\n"
        )
        self.assertTrue(self.module.is_blocked(block))
        self.assertFalse(self.module.is_waiting_merge(block))


class MarkerOpenStateTest(unittest.TestCase):
    """status_report/select_package/priority_view behandeln Freitext als offen."""

    @classmethod
    def setUpClass(cls):
        cls.module = load_packages()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_status_report_treats_freetext_block_as_open(self):
        """Vorbedingung: Projekt mit einem B5-ähnlichen Block.
        Aktion: ``status_report(project)``.
        Erwartung: Block in ``open``, nicht in ``blocked``/``waiting``.
        Fehlerfall: Freitext-Marken verschieben den Block in blocked/waiting.
        """
        project = make_project(self.root, feedback=B5_LIKE_BLOCK)
        report = self.module.status_report(project)
        self.assertIn("B5", report["open"])
        self.assertNotIn("B5", report.get("blocked", []))
        self.assertNotIn("B5", report.get("waiting", []))

    def test_select_package_selects_freetext_block_when_only_candidate(self):
        """Vorbedingung: Projekt mit einem B5-ähnlichen Block als einzigem Paket.
        Aktion: ``select_package(project)``.
        Erwartung: Block wird gewählt.
        Fehlerfall: Freitext-Marken machen den Block nicht wählbar.
        """
        project = make_project(self.root, feedback=B5_LIKE_BLOCK)
        selected = self.module.select_package(
            project, state_path=str(self.root / "next.json"))
        self.assertIsNotNone(selected)
        self.assertEqual("B5", selected["id"])

    def test_status_report_treats_head_marker_block_as_blocked(self):
        """Vorbedingung: Projekt mit Kopffeld-BLOCKIERT vor Beschreibung.
        Aktion: ``status_report(project)``.
        Erwartung: Block in ``blocked``.
        Fehlerfall: Kopffeld-Marker wird ignoriert.
        """
        project = make_project(
            self.root, feedback="- [ ] H1 Titel\n  BLOCKIERT: extern\n  Beschreibung: offen\n")
        report = self.module.status_report(project)
        self.assertIn("H1", report["blocked"])
        self.assertNotIn("H1", report["open"])

    def test_select_package_skips_head_marker_block(self):
        """Vorbedingung: H1 mit Kopffeld-BLOCKIERT, H2 offen.
        Aktion: ``select_package(project)``.
        Erwartung: H2 wird gewählt.
        Fehlerfall: Kopffeld-Marker macht den Block wählbar.
        """
        project = make_project(
            self.root,
            feedback=(
                "- [ ] H1 Titel\n  BLOCKIERT: extern\n  Beschreibung: offen\n"
                "- [ ] H2 Offen\n"
            ),
        )
        selected = self.module.select_package(
            project, state_path=str(self.root / "next.json"))
        self.assertIsNotNone(selected)
        self.assertEqual("H2", selected["id"])

    def test_status_report_head_marker_unproven_checked_is_blocked(self):
        """Vorbedingung: abgehakter Block ohne Nachweis mit Kopffeld-Marker.
        Aktion: ``status_report(project)``.
        Erwartung: Block in ``blocked`` (Konsistenz zu ``_parse_entry``/``open_items``).
        Fehlerfall: Block fällt auf „ohne Nachweis“/„open“ zurück.
        """
        project = make_project(
            self.root, feedback="- [x] U1 Titel\n  BLOCKIERT: extern\n  Beschreibung: offen\n")
        report = self.module.status_report(project)
        self.assertIn("U1", report["blocked"])
        self.assertNotIn("U1", report["open"])

    def test_priority_view_marks_freetext_block_as_open(self):
        """Vorbedingung: Projekt mit B5-ähnlichem Block in PACKAGE_ORDER.
        Aktion: ``priority_view(project)``.
        Erwartung: Status „offen“, nicht „gesperrt“/„wartet auf Merge“.
        Fehlerfall: Freitext-Marken sperren den Block in der Prioritätsansicht.
        """
        project = make_project(
            self.root, feedback=B5_LIKE_BLOCK,
            env_text='TYPE=generic\nPACKAGE_ORDER="B5"\n')
        view = self.module.priority_view(project)
        by_id = {entry["id"]: entry for entry in view["order"]}
        self.assertEqual("offen", by_id["B5"]["status"])


class MarkCommandsTest(unittest.TestCase):
    """``mark_blocked``/``mark_waiting_merge`` hängen echte Endmarken an."""

    @classmethod
    def setUpClass(cls):
        cls.module = load_packages()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_mark_blocked_appends_real_marker_to_freetext_block(self):
        """Vorbedingung: Block enthält Freitext-'BLOCKIERT:' nicht als Endzeile.
        Aktion: ``mark_blocked(project, 'T1', note)``.
        Erwartung: changed True; eine echte Marke steht als letzte nichtleere
        Zeile; ``is_blocked`` wird True.
        Fehlerfall: Idempotenz-Check springt auf Freitext an und verweigert.
        """
        project = make_project(
            self.root,
            tickets=(
                "- [ ] T1 Titel\n"
                "  Beschreibung: offen\n"
                "  BLOCKIERT: Bericht\n"
                "  Offen: keine\n"
            ),
        )
        changed, message = self.module.mark_blocked(project, "T1", "echter Grund")
        self.assertTrue(changed, message)
        text = (project / "TICKETS.md").read_text(encoding="utf-8")
        block = None
        for b in self.module.read_blocks(project / "TICKETS.md"):
            if self.module.block_id(b) == "T1":
                block = b
        self.assertIsNotNone(block)
        last = [line for line in block.splitlines() if line.strip()][-1]
        self.assertTrue(last.strip().upper().startswith("BLOCKIERT:"))
        self.assertTrue(self.module.is_blocked(block))

    def test_mark_blocked_is_idempotent_with_real_marker(self):
        """Vorbedingung: ``mark_blocked`` lief bereits einmal für T1.
        Aktion: denselben Aufruf erneut ausführen.
        Erwartung: changed False; keine zweite Marke.
        Fehlerfall: doppelte Marke oder Fehlerabbruch.
        """
        project = make_project(
            self.root,
            tickets=(
                "- [ ] T1 Titel\n"
                "  Beschreibung: offen\n"
                "  BLOCKIERT: Bericht\n"
                "  Offen: keine\n"
            ),
        )
        first = self.module.mark_blocked(project, "T1", "echter Grund")
        self.assertTrue(first[0], first[1])
        second = self.module.mark_blocked(project, "T1", "echter Grund")
        self.assertFalse(second[0], second[1])
        text = (project / "TICKETS.md").read_text(encoding="utf-8")
        self.assertEqual(2, text.count("BLOCKIERT:"), text)

    def test_mark_waiting_merge_appends_real_marker_to_freetext_block(self):
        """Vorbedingung: Block enthält Freitext-'Wartet auf Merge:' nicht als Endzeile.
        Aktion: ``mark_waiting_merge(project, 'T1', note)``.
        Erwartung: changed True; echte Marke als letzte nichtleere Zeile.
        Fehlerfall: Idempotenz-Check springt auf Freitext an und verweigert.
        """
        project = make_project(
            self.root,
            tickets=(
                "- [ ] T1 Titel\n"
                "  Beschreibung: offen\n"
                "  WARTET AUF MERGE: keine\n"
                "  Offen: keine\n"
            ),
        )
        changed, message = self.module.mark_waiting_merge(project, "T1", "PR #6")
        self.assertTrue(changed, message)
        block = None
        for b in self.module.read_blocks(project / "TICKETS.md"):
            if self.module.block_id(b) == "T1":
                block = b
        last = [line for line in block.splitlines() if line.strip()][-1]
        self.assertTrue(last.strip().upper().startswith("WARTET AUF MERGE:"))
        self.assertTrue(self.module.is_waiting_merge(block))

    def test_mark_waiting_merge_is_idempotent_with_real_marker(self):
        """Vorbedingung: ``mark_waiting_merge`` lief bereits einmal für T1.
        Aktion: denselben Aufruf erneut ausführen.
        Erwartung: changed False; keine zweite Marke.
        Fehlerfall: doppelte Marke oder Fehlerabbruch.
        """
        project = make_project(
            self.root,
            tickets=(
                "- [ ] T1 Titel\n"
                "  Beschreibung: offen\n"
                "  WARTET AUF MERGE: keine\n"
                "  Offen: keine\n"
            ),
        )
        first = self.module.mark_waiting_merge(project, "T1", "PR #6")
        self.assertTrue(first[0], first[1])
        second = self.module.mark_waiting_merge(project, "T1", "PR #6")
        self.assertFalse(second[0], second[1])


class MarkCommandsSubprocessTest(unittest.TestCase):
    """CLI ``mark-blocked``/``mark-waiting`` auf Freitext-Blöcken."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "ws"
        self.root.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.project = make_project(
            self.root,
            tickets=(
                "- [ ] T1 Titel\n"
                "  Beschreibung: offen\n"
                "  BLOCKIERT: Bericht\n"
                "  WARTET AUF MERGE: keine\n"
                "  Offen: keine\n"
            ),
        )

    def run_mark_blocked(self, note="echter Grund"):
        return subprocess.run(
            [sys.executable, str(PACKAGES), "mark-blocked",
             "--project", str(self.project), "--id", "T1", "--note", note],
            cwd=str(self.base), stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=60,
        )

    def run_mark_waiting(self, note="PR #6"):
        return subprocess.run(
            [sys.executable, str(PACKAGES), "mark-waiting",
             "--project", str(self.project), "--id", "T1", "--note", note],
            cwd=str(self.base), stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=60,
        )

    def test_mark_blocked_cli_can_append_to_freetext_block(self):
        """Vorbedingung: T1 mit Freitext-Markern.
        Aktion: ``mark-blocked --id T1``.
        Erwartung: Exit 0; Ausgabe enthält „blockiert“.
        Fehlerfall: Idempotenz springt auf Freitext an.
        """
        result = self.run_mark_blocked()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("blockiert", (result.stdout + result.stderr).lower())

    def test_mark_waiting_cli_can_append_to_freetext_block(self):
        """Vorbedingung: T1 mit Freitext-Markern.
        Aktion: ``mark-waiting --id T1``.
        Erwartung: Exit 0; Ausgabe enthält „wartend“.
        Fehlerfall: Idempotenz springt auf Freitext an.
        """
        result = self.run_mark_waiting()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("wartend", (result.stdout + result.stderr).lower())


class TicketStatusMarkerTest(unittest.TestCase):
    """``bin/vibe``: ``_parse_entry``/``open_items`` konsistent mit Endmarken."""

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

    def test_parse_entry_freetext_uppercase_marker_is_open(self):
        """Vorbedingung: Block mit 'BLOCKIERT:' in der Beschreibung, nicht als
        Endzeile.
        Aktion: ``_parse_entry``.
        Erwartung: state „offen“.
        Fehlerfall: Teilstring-Check klassifiziert als BLOCKIERT.
        """
        project = self.project(
            tickets=(
                "- [ ] T1 Titel\n"
                "  Beschreibung: offen\n"
                "  BLOCKIERT: Bericht\n"
                "  Offen: keine\n"
            )
        )
        entries = self.cli._feedback_scan(
            self.cli._read_text(project / "TICKETS.md"))
        parsed = self.cli._parse_entry(entries[0], str(project), need_proof=False)
        self.assertEqual("offen", parsed["state"], parsed)

    def test_parse_entry_freetext_waiting_marker_is_open(self):
        """Vorbedingung: Block mit 'WARTET AUF MERGE:' in der Beschreibung,
        nicht als Endzeile.
        Aktion: ``_parse_entry``.
        Erwartung: state „offen“.
        Fehlerfall: Teilstring-Check klassifiziert als WARTET AUF MERGE.
        """
        project = self.project(
            tickets=(
                "- [ ] T1 Titel\n"
                "  Beschreibung: offen\n"
                "  WARTET AUF MERGE: keine\n"
                "  Offen: keine\n"
            )
        )
        entries = self.cli._feedback_scan(
            self.cli._read_text(project / "TICKETS.md"))
        parsed = self.cli._parse_entry(entries[0], str(project), need_proof=False)
        self.assertEqual("offen", parsed["state"], parsed)

    def test_parse_entry_real_blocked_marker_at_end(self):
        """Vorbedingung: Block endet mit 'BLOCKIERT: extern'.
        Aktion: ``_parse_entry``.
        Erwartung: state „BLOCKIERT“.
        Fehlerfall: Endmarke wird ignoriert.
        """
        project = self.project(
            tickets="- [ ] T1 Titel\n  Beschreibung: offen\n  BLOCKIERT: extern\n"
        )
        entries = self.cli._feedback_scan(
            self.cli._read_text(project / "TICKETS.md"))
        parsed = self.cli._parse_entry(entries[0], str(project), need_proof=False)
        self.assertEqual("BLOCKIERT", parsed["state"], parsed)

    def test_parse_entry_real_waiting_marker_at_end(self):
        """Vorbedingung: Block endet mit 'WARTET AUF MERGE: PR #6'.
        Aktion: ``_parse_entry``.
        Erwartung: state „WARTET AUF MERGE“.
        Fehlerfall: Endmarke wird ignoriert.
        """
        project = self.project(
            tickets="- [ ] T1 Titel\n  Beschreibung: offen\n  WARTET AUF MERGE: PR #6\n"
        )
        entries = self.cli._feedback_scan(
            self.cli._read_text(project / "TICKETS.md"))
        parsed = self.cli._parse_entry(entries[0], str(project), need_proof=False)
        self.assertEqual("WARTET AUF MERGE", parsed["state"], parsed)

    def test_parse_entry_case_insensitive_marker_at_end(self):
        """Vorbedingung: Block endet mit kleingeschriebener Marke.
        Aktion: ``_parse_entry``.
        Erwartung: state wird entsprechend gesetzt.
        Fehlerfall: Groß-/Kleinschreibung wird streng geprüft.
        """
        project = self.project(
            tickets="- [ ] T1 Titel\n  Beschreibung: offen\n  blockiert: extern\n"
        )
        entries = self.cli._feedback_scan(
            self.cli._read_text(project / "TICKETS.md"))
        parsed = self.cli._parse_entry(entries[0], str(project), need_proof=False)
        self.assertEqual("BLOCKIERT", parsed["state"], parsed)

    def test_parse_entry_blocked_wins_over_waiting(self):
        """Vorbedingung: Block trägt beide Marken, Endzeile ist BLOCKIERT.
        Aktion: ``_parse_entry``.
        Erwartung: state „BLOCKIERT“.
        Fehlerfall: WARTET überdeckt BLOCKIERT.
        """
        project = self.project(
            tickets=(
                "- [ ] T1 Titel\n"
                "  WARTET AUF MERGE: PR #6\n"
                "  BLOCKIERT: extern\n"
            )
        )
        entries = self.cli._feedback_scan(
            self.cli._read_text(project / "TICKETS.md"))
        parsed = self.cli._parse_entry(entries[0], str(project), need_proof=False)
        self.assertEqual("BLOCKIERT", parsed["state"], parsed)

    def test_parse_entry_head_marker_before_description(self):
        """Vorbedingung: Marke im Kopffeld vor 'Beschreibung:'.
        Aktion: ``_parse_entry``.
        Erwartung: state „BLOCKIERT“.
        Fehlerfall: Kopffeld-Marker wird ignoriert.
        """
        project = self.project(
            tickets="- [ ] T1 Titel\n  BLOCKIERT: extern\n  Beschreibung: offen\n"
        )
        entries = self.cli._feedback_scan(
            self.cli._read_text(project / "TICKETS.md"))
        parsed = self.cli._parse_entry(entries[0], str(project), need_proof=False)
        self.assertEqual("BLOCKIERT", parsed["state"], parsed)

    def test_parse_entry_head_marker_before_expected(self):
        """Vorbedingung: Marke im Kopffeld vor 'Erwartet:'.
        Aktion: ``_parse_entry``.
        Erwartung: state „WARTET AUF MERGE“.
        Fehlerfall: 'Erwartet:' wird nicht als Beschreibungsstart akzeptiert.
        """
        project = self.project(
            tickets="- [ ] T1 Titel\n  WARTET AUF MERGE: PR #6\n  Erwartet: x\n"
        )
        entries = self.cli._feedback_scan(
            self.cli._read_text(project / "TICKETS.md"))
        parsed = self.cli._parse_entry(entries[0], str(project), need_proof=False)
        self.assertEqual("WARTET AUF MERGE", parsed["state"], parsed)

    def test_parse_entry_head_marker_unproven_checked(self):
        """Vorbedingung: abgehakter Block ohne Nachweis mit Kopffeld-Marker.
        Aktion: ``_parse_entry``.
        Erwartung: state „BLOCKIERT“ (Marke schlägt 'ohne Nachweis').
        Fehlerfall: Checkbox-/Nachweislogik maskiert die Marke.
        """
        project = self.project(
            tickets="- [x] T1 Titel\n  BLOCKIERT: extern\n  Beschreibung: offen\n"
        )
        entries = self.cli._feedback_scan(
            self.cli._read_text(project / "TICKETS.md"))
        parsed = self.cli._parse_entry(entries[0], str(project), need_proof=True)
        self.assertEqual("BLOCKIERT", parsed["state"], parsed)

    def test_parse_entry_latest_position_head_blocked_end_waiting(self):
        """Vorbedingung: Kopffeld-BLOCKIERT und Endzeile-WARTET.
        Aktion: ``_parse_entry``.
        Erwartung: state „WARTET AUF MERGE“.
        Fehlerfall: Kopffeld-Marke überdeckt Endzeile.
        """
        project = self.project(
            tickets=(
                "- [ ] T1 Titel\n"
                "  BLOCKIERT: head\n"
                "  Beschreibung: offen\n"
                "  WARTET AUF MERGE: end\n"
            )
        )
        entries = self.cli._feedback_scan(
            self.cli._read_text(project / "TICKETS.md"))
        parsed = self.cli._parse_entry(entries[0], str(project), need_proof=False)
        self.assertEqual("WARTET AUF MERGE", parsed["state"], parsed)

    def test_parse_entry_latest_position_head_waiting_end_blocked(self):
        """Vorbedingung: Kopffeld-WARTET und Endzeile-BLOCKIERT.
        Aktion: ``_parse_entry``.
        Erwartung: state „BLOCKIERT“.
        Fehlerfall: Kopffeld-Marke überdeckt Endzeile.
        """
        project = self.project(
            tickets=(
                "- [ ] T1 Titel\n"
                "  WARTET AUF MERGE: head\n"
                "  Beschreibung: offen\n"
                "  BLOCKIERT: end\n"
            )
        )
        entries = self.cli._feedback_scan(
            self.cli._read_text(project / "TICKETS.md"))
        parsed = self.cli._parse_entry(entries[0], str(project), need_proof=False)
        self.assertEqual("BLOCKIERT", parsed["state"], parsed)

    def test_parse_entry_blocked_wins_in_head_field(self):
        """Vorbedingung: Beide Marken im Kopffeld.
        Aktion: ``_parse_entry``.
        Erwartung: state „BLOCKIERT“.
        Fehlerfall: WARTET überdeckt BLOCKIERT im Kopffeld.
        """
        project = self.project(
            tickets=(
                "- [ ] T1 Titel\n"
                "  WARTET AUF MERGE: head\n"
                "  BLOCKIERT: head2\n"
                "  Beschreibung: offen\n"
            )
        )
        entries = self.cli._feedback_scan(
            self.cli._read_text(project / "TICKETS.md"))
        parsed = self.cli._parse_entry(entries[0], str(project), need_proof=False)
        self.assertEqual("BLOCKIERT", parsed["state"], parsed)

    def test_open_items_head_marker(self):
        """Vorbedingung: Kopffeld-Marker vor Beschreibung.
        Aktion: ``open_items('proj')``.
        Erwartung: Status „BLOCKIERT“.
        Fehlerfall: Kopffeld-Marker wird ignoriert.
        """
        self.project(tickets="- [ ] T1 Titel\n  BLOCKIERT: extern\n  Beschreibung: offen\n")
        items = self.cli.open_items("proj")
        self.assertIn(("T1", "Titel", "BLOCKIERT"), items, items)

    def test_open_items_freetext_block_is_open(self):
        """Vorbedingung: TICKETS.md mit Freitext-Markern, nicht als Endzeile.
        Aktion: ``open_items('proj')``.
        Erwartung: Status „offen“.
        Fehlerfall: Teilstring-Check klassifiziert als BLOCKIERT/WARTET.
        """
        self.project(
            tickets=(
                "- [ ] T1 Titel\n"
                "  Beschreibung: offen\n"
                "  BLOCKIERT: Bericht\n"
                "  WARTET AUF MERGE: keine\n"
                "  Offen: keine\n"
            )
        )
        items = self.cli.open_items("proj")
        self.assertIn(("T1", "Titel", "offen"), items, items)

    def test_open_items_real_blocked_marker_at_end(self):
        """Vorbedingung: TICKETS.md endet mit 'BLOCKIERT: extern'.
        Aktion: ``open_items('proj')``.
        Erwartung: Status „BLOCKIERT“.
        Fehlerfall: Endmarke wird ignoriert.
        """
        self.project(tickets="- [ ] T1 Titel\n  BLOCKIERT: extern\n")
        items = self.cli.open_items("proj")
        self.assertIn(("T1", "Titel", "BLOCKIERT"), items, items)

    def test_open_items_real_waiting_marker_at_end(self):
        """Vorbedingung: TICKETS.md endet mit 'WARTET AUF MERGE: PR #6'.
        Aktion: ``open_items('proj')``.
        Erwartung: Status „WARTET AUF MERGE“.
        Fehlerfall: Endmarke wird ignoriert.
        """
        self.project(tickets="- [ ] T1 Titel\n  WARTET AUF MERGE: PR #6\n")
        items = self.cli.open_items("proj")
        self.assertIn(("T1", "Titel", "WARTET AUF MERGE"), items, items)


class RealCaseB5Test(unittest.TestCase):
    """R5: B5-ähnlicher Block ist offen und auswählbar."""

    @classmethod
    def setUpClass(cls):
        cls.packages = load_packages()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.workspace = self.base / "ws"
        self.workspace.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.cli = load_cli(self.workspace, self.home)

    def test_b5_like_feedback_block_is_open_everywhere(self):
        """Vorbedingung: FEEDBACK.md mit B5-ähnlichem Block.
        Aktion: is_blocked/is_waiting_merge, status_report, select_package,
        _parse_entry, open_items.
        Erwartung: Überall als „offen“ klassifiziert und auswählbar.
        Fehlerfall: Freitext-Marken sperren den Block dauerhaft.
        """
        project = make_project(self.workspace, feedback=B5_LIKE_BLOCK)
        self.cli._pm.clear()

        self.assertFalse(self.packages.is_blocked(B5_LIKE_BLOCK))
        self.assertFalse(self.packages.is_waiting_merge(B5_LIKE_BLOCK))

        report = self.packages.status_report(project)
        self.assertIn("B5", report["open"])

        selected = self.packages.select_package(
            project, state_path=str(self.base / "next.json"))
        self.assertIsNotNone(selected)
        self.assertEqual("B5", selected["id"])

        entries = self.cli._feedback_scan(
            self.cli._read_text(project / "FEEDBACK.md"))
        parsed = self.cli._parse_entry(entries[0], str(project), need_proof=False)
        self.assertEqual("offen", parsed["state"], parsed)

        items = self.cli.open_items("proj")
        self.assertTrue(any(item[0] == "B5" and item[2] == "offen" for item in items), items)


class RegressionPrecedenceTest(unittest.TestCase):
    """R6: Präzedenz und echte Marken bleiben wirksam."""

    @classmethod
    def setUpClass(cls):
        cls.packages = load_packages()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_real_markers_not_selectable(self):
        """Vorbedingung: T1 blockiert, T2 wartend, T3 offen.
        Aktion: ``select_package``.
        Erwartung: T3 wird gewählt.
        Fehlerfall: Gesperrte/wartende Pakete werden ausgewählt.
        """
        project = make_project(
            self.root,
            tickets=(
                "- [ ] T1 Blockiert\n  BLOCKIERT: extern\n"
                "- [ ] T2 Wartet\n  WARTET AUF MERGE: PR #6\n"
                "- [ ] T3 Offen\n"
            ),
        )
        selected = self.packages.select_package(
            project, state_path=str(self.root / "next.json"))
        self.assertIsNotNone(selected)
        self.assertEqual("T3", selected["id"])

    def test_status_report_classifies_real_markers(self):
        """Vorbedingung: T1 blockiert, T2 wartend, T3 offen.
        Aktion: ``status_report``.
        Erwartung: blocked=[T1], waiting=[T2], open=[T3].
        Fehlerfall: Klassifikation der echten Marken bricht.
        """
        project = make_project(
            self.root,
            tickets=(
                "- [ ] T1 Blockiert\n  BLOCKIERT: extern\n"
                "- [ ] T2 Wartet\n  WARTET AUF MERGE: PR #6\n"
                "- [ ] T3 Offen\n"
            ),
        )
        report = self.packages.status_report(project)
        self.assertEqual(["T1"], report["blocked"])
        self.assertEqual(["T2"], report["waiting"])
        self.assertEqual(["T3"], report["open"])

    def test_priority_view_real_markers(self):
        """Vorbedingung: T1 blockiert, T2 wartend, PACKAGE_ORDER gesetzt.
        Aktion: ``priority_view``.
        Erwartung: T1 „gesperrt“, T2 „wartet auf Merge“.
        Fehlerfall: Echte Marken verlieren ihre Ansichtsbezeichnung.
        """
        project = make_project(
            self.root,
            tickets=(
                "- [ ] T1 Blockiert\n  BLOCKIERT: extern\n"
                "- [ ] T2 Wartet\n  WARTET AUF MERGE: PR #6\n"
            ),
            env_text='TYPE=generic\nPACKAGE_ORDER="T1,T2"\n',
        )
        view = self.packages.priority_view(project)
        by_id = {entry["id"]: entry for entry in view["order"]}
        self.assertEqual("gesperrt", by_id["T1"]["status"])
        self.assertEqual("wartet auf Merge", by_id["T2"]["status"])

    def test_draft_block_is_skipped_by_select_package(self):
        """Vorbedingung: T1 Entwurf, T2 offen.
        Aktion: ``select_package``.
        Erwartung: T2 wird gewählt.
        Fehlerfall: Entwurf wird als wählbar behandelt.
        """
        project = make_project(
            self.root,
            tickets=(
                "- [ ] T1 Entwurf\n  Status: draft\n"
                "- [ ] T2 Offen\n"
            ),
        )
        selected = self.packages.select_package(
            project, state_path=str(self.root / "next.json"))
        self.assertIsNotNone(selected)
        self.assertEqual("T2", selected["id"])

    def test_apply_proof_still_removes_real_markers(self):
        """Vorbedingung: Block enthält WARTET- und BLOCKIERT-Zeilen; Arbeitskopie
        liefert denselben Block abgehakt mit Nachweis.
        Aktion: ``sync_proof(..., require_commit=False)``.
        Erwartung: Beide Markerzeilen entfernt.
        Fehlerfall: _apply_proof räumt Marken nicht mehr ab.
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
        changed, message = self.packages.sync_proof(
            project, worktree, "T1", require_commit=False)
        self.assertTrue(changed, message)
        text = (project / "TICKETS.md").read_text(encoding="utf-8")
        self.assertNotIn("WARTET AUF MERGE", text)
        self.assertNotIn("BLOCKIERT", text)


class RegressionBinVibeTest(unittest.TestCase):
    """R6 für bin/vibe: Präzedenz erledigt > Marker > In-Progress > Draft."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.workspace = self.base / "ws"
        self.workspace.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.cli = load_cli(self.workspace, self.home)

    def project(self, tickets=""):
        project = make_project(self.workspace, tickets=tickets)
        self.cli._pm.clear()
        return project

    def test_done_precedes_marker(self):
        """Vorbedingung: abgehakter Block mit Freitext-Marker.
        Aktion: ``_parse_entry(..., need_proof=False)``.
        Erwartung: state „erledigt“.
        Fehlerfall: Marker überdeckt erledigt.
        """
        project = self.project(
            tickets="- [x] T1 Titel\n  Beschreibung: offen\n  BLOCKIERT: Bericht\n"
        )
        entries = self.cli._feedback_scan(
            self.cli._read_text(project / "TICKETS.md"))
        parsed = self.cli._parse_entry(entries[0], str(project), need_proof=False)
        self.assertEqual("erledigt", parsed["state"], parsed)

    def test_real_marker_at_state_position_beats_in_progress(self):
        """Vorbedingung: Block mit Status in-progress und BLOCKIERT-Marke an
        einer Statusposition (Kopffeld vor der Beschreibung).
        Aktion: ``_parse_entry``.
        Erwartung: state „BLOCKIERT“ (Runner-Schranke wird nicht maskiert).
        Fehlerfall: In-Progress überdeckt eine echte Runner-Schranke.
        """
        project = self.project(
            tickets=(
                "- [ ] T1 Titel\n"
                "  BLOCKIERT: extern\n"
                "  Status: in-progress\n"
                "  Beschreibung: offen\n"
            )
        )
        entries = self.cli._feedback_scan(
            self.cli._read_text(project / "TICKETS.md"))
        parsed = self.cli._parse_entry(entries[0], str(project), need_proof=False)
        self.assertEqual("BLOCKIERT", parsed["state"], parsed)

    def test_real_marker_at_state_position_beats_draft(self):
        """Vorbedingung: Block mit Status draft und WARTET-Marke an einer
        Statusposition (Endzeile).
        Aktion: ``_parse_entry``.
        Erwartung: state „WARTET AUF MERGE“ (Runner-Schranke gewinnt).
        Fehlerfall: Draft überdeckt eine echte Runner-Schranke.
        """
        project = self.project(
            tickets=(
                "- [ ] T1 Titel\n"
                "  Status: draft\n"
                "  Beschreibung: offen\n"
                "  WARTET AUF MERGE: PR #6\n"
            )
        )
        entries = self.cli._feedback_scan(
            self.cli._read_text(project / "TICKETS.md"))
        parsed = self.cli._parse_entry(entries[0], str(project), need_proof=False)
        self.assertEqual("WARTET AUF MERGE", parsed["state"], parsed)

    def test_freetext_marker_does_not_beat_in_progress(self):
        """Vorbedingung: Block mit Status in-progress und BLOCKIERT-Wort mitten
        im Block (nicht Statusposition).
        Aktion: ``_parse_entry``.
        Erwartung: state „In Progress“.
        Fehlerfall: Freitext wird als Runner-Schranke fehlgelesen.
        """
        project = self.project(
            tickets=(
                "- [ ] T1 Titel\n"
                "  Status: in-progress\n"
                "  Beschreibung: offen\n"
                "  BLOCKIERT: Bericht\n"
                "  Offen: keine\n"
            )
        )
        entries = self.cli._feedback_scan(
            self.cli._read_text(project / "TICKETS.md"))
        parsed = self.cli._parse_entry(entries[0], str(project), need_proof=False)
        self.assertEqual("In Progress", parsed["state"], parsed)

    def test_freetext_marker_does_not_beat_draft(self):
        """Vorbedingung: Block mit Status draft und BLOCKIERT-Wort mitten im
        Block (nicht Statusposition).
        Aktion: ``_parse_entry``.
        Erwartung: state „Draft“.
        Fehlerfall: Freitext wird als Runner-Schranke fehlgelesen.
        """
        project = self.project(
            tickets=(
                "- [ ] T1 Titel\n"
                "  Status: draft\n"
                "  Beschreibung: offen\n"
                "  BLOCKIERT: Bericht\n"
                "  Offen: keine\n"
            )
        )
        entries = self.cli._feedback_scan(
            self.cli._read_text(project / "TICKETS.md"))
        parsed = self.cli._parse_entry(entries[0], str(project), need_proof=False)
        self.assertEqual("Draft", parsed["state"], parsed)


if __name__ == "__main__":
    unittest.main()
