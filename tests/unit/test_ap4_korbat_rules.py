"""AP4-Korbat (Regeln/SPEC): T-I1.

Die Fälle leiten sich aus dem Arbeitspaket AP4-Korbat (TICKETS.md), AP3.md
§6 und §7 sowie den Design-Entscheidungen 14–16 ab — nicht aus einem
Implementierungsdiff:

* T-I1: ``SPEC.md`` enthält genau EINEN kanonischen Git-Abschnitt
  („Git & work-package closing (runner-owned)“, AP3 §6.1). Beide alten
  „Strictly Enforced“-Blöcke sind ersetzt; ``gh pr merge --squash
  --delete-branch`` und ``git branch -D`` stehen nicht mehr im
  Agentenauftrag. Zeile ~330 („Nicht im Umfang“) nennt die Freigabe bzw.
  ``GITHUB_AUTO_MERGE``. Der Modul-Docstring von ``bin/vibe_github.py``
  beschreibt das Merge-Verhalten mit ``GITHUB_AUTO_MERGE``.

GH-76: Die frühere T-I2-Prüfung des deutschen ``GENERAL_RULES``-Blocks und
seiner Kopie in den Vorlagen ist entfallen. Der verbindliche Regeltext der
Agentenläufe ist jetzt die englische Plattformanweisung; er wird in
``tests.unit.test_gh76_platform_instructions`` geprüft. Die SPEC- und
GitHub-Docstring-Anforderungen bleiben unverändert.

Es werden nur Dateien gelesen; keine Modellaufrufe, kein Netz.

Run:

    python3 -m unittest tests.unit.test_ap4_korbat_rules -v
"""
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GITHUB_MODULE = REPO / "bin" / "vibe_github.py"
SPEC = REPO / "SPEC.md"

OLD_SPEC_HEADINGS = (
    "## Git Workflow & Branch Rules (Strictly Enforced)",
    "## Git&GitHub Workflow & Branch Rules (Strictly Enforced)",
)
CANONICAL_SPEC_HEADING = "## Git & work-package closing (runner-owned)"


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
        (deutsche Fassung der SPEC) vorhanden.
        Fehlerfall: Duplikat oder fehlender Abschnitt.
        """
        headings = [line for line in self.text.splitlines()
                    if line.startswith("## ") and "Git" in line]
        self.assertEqual([CANONICAL_SPEC_HEADING], headings, headings)
        self.assertIn("Der Runner besitzt Worktrees, Branches, Mergebarkeit, "
                      "Push, PR, Merge und Cleanup.", self.text)

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


if __name__ == "__main__":
    unittest.main()
