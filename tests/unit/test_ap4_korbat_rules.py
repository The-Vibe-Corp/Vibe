"""AP4-Korbat (Regeln/SPEC): T-I1, T-I2.

Die Fälle leiten sich aus dem Arbeitspaket AP4-Korbat (TICKETS.md), AP3.md
§6 und §7 sowie den Design-Entscheidungen 14–16 ab — nicht aus einem
Implementierungsdiff:

* T-I1: ``SPEC.md`` enthält genau EINEN kanonischen Git-Abschnitt
  („Git & work-package closing (runner-owned)“, AP3 §6.1). Beide alten
  „Strictly Enforced“-Blöcke sind ersetzt; ``gh pr merge --squash
  --delete-branch`` und ``git branch -D`` stehen nicht mehr im
  Agentenauftrag. Zeile ~330 („Nicht im Umfang“) nennt die Freigabe bzw.
  ``GITHUB_AUTO_MERGE``. Der Modul-Docstring von ``bin/vibe_github.py``
  beschreibt das Merge-Verhalten mit ``GITHUB_AUTO_MERGE``. Die
  Abschlusszeile in ``GENERAL_RULES`` verlangt weiter Push und
  Merge-Request bei aktivierter Verknüpfung, verweist aber für den Merge auf
  ``GITHUB_AUTO_MERGE`` (Auto-Merge aus = PR-only).
* T-I2: Der Block „Laufende Instanz nicht verändern (verbindlich)“ steht in
  ``GENERAL_RULES`` und in jeder ``templates/*/AGENTS.md`` genau einmal.
  Die verwalteten Blöcke der Vorlagen bleiben mit ``GENERAL_RULES``
  bytengleich. Genau ein Markerpaar ``<!-- vibe:general-rules -->`` /
  ``<!-- /vibe:general-rules -->``.

Es werden nur Dateien gelesen; keine Modellaufrufe, kein Netz.

Run:

    python3 -m unittest tests.unit.test_ap4_korbat_rules -v
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
GITHUB_MODULE = REPO / "bin" / "vibe_github.py"
SPEC = REPO / "SPEC.md"
TEMPLATES = sorted((REPO / "templates").glob("*/AGENTS.md"))

OLD_SPEC_HEADINGS = (
    "## Git Workflow & Branch Rules (Strictly Enforced)",
    "## Git&GitHub Workflow & Branch Rules (Strictly Enforced)",
)
CANONICAL_SPEC_HEADING = "## Git & work-package closing (runner-owned)"
INSTANCE_BLOCK = "## Laufende Instanz nicht verändern (verbindlich)"
MARK_START = "<!-- vibe:general-rules -->"
MARK_END = "<!-- /vibe:general-rules -->"


def load_cli(vibe_root, home):
    """Lädt ``bin/vibe`` als Modul mit isoliertem VIBE und HOME."""
    old = {key: os.environ.get(key)
           for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_ap4_rules_under_test", str(CLI))
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


class GeneralRulesTest(unittest.TestCase):
    """AK T-I1/T-I2: eine Regelquelle, ein Instanz-Block, Merge-Hinweis."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / "vibe").mkdir()
        (root / "home").mkdir()
        cls.cli = load_cli(root / "vibe", root / "home")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_rules_contain_exactly_one_running_instance_block(self):
        """Vorbedingung: ``GENERAL_RULES`` aus ``bin/vibe``.
        Aktion: Vorkommen der Überschrift zählen.
        Erwartung: genau 1 (T-I2: keine dreifache Wiederholung).
        Fehlerfall: 0 oder >1 Vorkommen.
        """
        self.assertEqual(
            1, self.cli.GENERAL_RULES.count(INSTANCE_BLOCK),
            "Der Block „Laufende Instanz“ muss genau einmal vorkommen")

    def test_rules_contain_exactly_one_marker_pair(self):
        """Vorbedingung: ``GENERAL_RULES``.
        Aktion: Marker zählen.
        Erwartung: je genau 1 Start- und Endmarker (T-I1).
        Fehlerfall: doppelte oder fehlende Marker.
        """
        self.assertEqual(1, self.cli.GENERAL_RULES.count(MARK_START))
        self.assertEqual(1, self.cli.GENERAL_RULES.count(MARK_END))

    def test_completion_line_keeps_the_push_gate_and_names_auto_merge(self):
        """Vorbedingung: ``GENERAL_RULES``.
        Aktion: Abschlusszeile unter „Ordnung im Git halten“ prüfen.
        Erwartung: „Push“, „Merge-Request“ und „aktivier“ bleiben (B16);
        zusätzlich wird ``GITHUB_AUTO_MERGE`` als Merge-Steuerung genannt.
        Fehlerfall: alte Aussage „ohne Push und Merge-Request kein Häkchen“
        ohne Auto-Merge-Bezug oder Verlust der GitHub-Schranke.
        """
        section = self.cli.GENERAL_RULES.split("## Ordnung im Git halten", 1)[1]
        section = section.split("\n## ", 1)[0]
        for marker in ("Push", "Merge-Request", "aktivier"):
            self.assertIn(marker, section,
                          "B16-Anforderung %r fehlt" % marker)
        self.assertIn("GITHUB_AUTO_MERGE", section,
                      "Merge-Steuerung über GITHUB_AUTO_MERGE fehlt")

    def test_every_template_contains_the_rules_exactly_once(self):
        """Vorbedingung: alle ``templates/*/AGENTS.md``.
        Aktion: verwalteten Block vergleichen und Vorkommen zählen.
        Erwartung: ``GENERAL_RULES`` ist bytengleich enthalten; der
        Instanz-Block und das Markerpaar kommen je genau einmal vor.
        Fehlerfall: abweichende Vorlage oder Duplikat.
        """
        self.assertTrue(TEMPLATES, "Keine Vorlagen gefunden")
        for path in TEMPLATES:
            with self.subTest(path=str(path)):
                text = path.read_text(encoding="utf-8")
                self.assertIn(self.cli.GENERAL_RULES, text,
                              "Vorlage weicht von GENERAL_RULES ab")
                self.assertEqual(1, text.count(INSTANCE_BLOCK),
                                 "Instanz-Block nicht genau einmal")
                self.assertEqual(1, text.count(MARK_START))
                self.assertEqual(1, text.count(MARK_END))

    def test_github_module_docstring_describes_auto_merge(self):
        """Vorbedingung: ``bin/vibe_github.py``.
        Aktion: Modul-Docstring/Quelltext lesen.
        Erwartung: „Das Zusammenführen selbst bleibt manuell.“ ist ersetzt;
        ``GITHUB_AUTO_MERGE`` wird als Ausnahme genannt.
        Fehlerfall: veraltete Aussage bleibt stehen.
        """
        text = GITHUB_MODULE.read_text(encoding="utf-8")
        self.assertNotIn("Das Zusammenführen selbst bleibt manuell.", text)
        self.assertIn("GITHUB_AUTO_MERGE", text)


class SpecCanonicalTest(unittest.TestCase):
    """AK T-I1: eine kanonische SPEC-Quelle ohne widersprüchliche Blöcke."""

    def setUp(self):
        self.text = SPEC.read_text(encoding="utf-8")

    def test_both_old_strictly_enforced_sections_are_gone(self):
        """Vorbedingung: ``SPEC.md``.
        Aktion: die beiden alten Git-Überschriften suchen.
        Erwartung: keine ist mehr vorhanden; „Strictly Enforced“ kommt nicht
        mehr vor.
        Fehlerfall: einer der widersprüchlichen Blöcke bleibt stehen.
        """
        for heading in OLD_SPEC_HEADINGS:
            self.assertNotIn(heading, self.text, heading)
        self.assertNotIn("Strictly Enforced", self.text)

    def test_exactly_one_canonical_git_section_exists(self):
        """Vorbedingung: ``SPEC.md``.
        Aktion: den kanonischen Abschnitt aus AP3 §6.1 suchen.
        Erwartung: genau eine Git-Abschnittsüberschrift, der kanonische Text
        vorhanden.
        Fehlerfall: Duplikat oder fehlender Abschnitt.
        """
        headings = [line for line in self.text.splitlines()
                    if line.startswith("## ") and "Git" in line]
        self.assertEqual([CANONICAL_SPEC_HEADING], headings, headings)
        self.assertIn("The runner owns worktrees, branches, mergeability, "
                      "push, PR, merge and cleanup.", self.text)

    def test_canonical_section_describes_pr_only_and_auto_merge(self):
        """Vorbedingung: kanonischer Abschnitt.
        Aktion: Aussagen zu ``GITHUB_AUTO_MERGE`` lesen.
        Erwartung: PR-only ist der Standard (leer/aus), ``"1"`` aktiviert
        Auto-Merge (squash), der Worktree bleibt bis zum Close registriert.
        Fehlerfall: Schalter oder Standard fehlen.
        """
        self.assertIn("GITHUB_AUTO_MERGE", self.text)
        lower = self.text.lower()
        self.assertIn("pr-only", lower)
        self.assertIn("auto-merge", lower)
        self.assertIn("vibe package close", self.text)

    def test_no_agent_side_squash_merge_or_force_delete_remains(self):
        """Vorbedingung: ``SPEC.md``.
        Aktion: verbotene Agentenkommandos suchen.
        Erwartung: ``gh pr merge --squash --delete-branch`` und
        ``git branch -D`` kommen nicht mehr vor.
        Fehlerfall: Agentenauftrag enthält weiterhin Merge/Force-Delete.
        """
        self.assertNotIn("gh pr merge --squash --delete-branch", self.text)
        self.assertNotIn("git branch -D", self.text)

    def test_conflict_repair_wording_is_documented(self):
        """Vorbedingung: kanonischer Abschnitt.
        Aktion: Anweisung für Merge-Konflikte lesen.
        Erwartung: ``git merge --continue``, ``--ours``/``--theirs``,
        „rebase“/„force-push“ werden ausdrücklich behandelt.
        Fehlerfall: Konfliktweg fehlt.
        """
        lower = self.text.lower()
        self.assertIn("git merge --continue", lower)
        self.assertIn("--ours", lower)
        self.assertIn("--theirs", lower)
        self.assertIn("rebase", lower)
        self.assertIn("force-push", lower)

    def test_out_of_scope_line_names_approval_and_auto_merge(self):
        """Vorbedingung: Abschnitt „Nicht im Umfang“.
        Aktion: die alte Zeile und die neue Formulierung suchen.
        Erwartung: Die alte Zeile ohne Bezug ist weg; die neue nennt
        Freigabe bzw. ``GITHUB_AUTO_MERGE``.
        Fehlerfall: unveränderte alte Aussage.
        """
        old = "- Automatische Veröffentlichung, Push, Merge oder Release ohne Freigabe."
        self.assertNotIn(old, self.text)
        self.assertRegex(
            self.text,
            r"Automatische Veröffentlichung, Push, Merge oder Release"
            r"[\s\S]{0,120}GITHUB_AUTO_MERGE")


if __name__ == "__main__":
    unittest.main()
