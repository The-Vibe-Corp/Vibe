"""AP4-Korbat (Regeln/SPEC): T-I1.

Die Fälle leiten sich aus dem Arbeitspaket AP4-Korbat (TICKETS.md), AP3.md
§6 und §7 sowie den Design-Entscheidungen 14–16 ab — nicht aus einem
Implementierungsdiff:

* T-I1: Es gibt genau EINE kanonische Quelle für den runner-eigenen
  Abschluss. ``SPEC.md`` beschreibt das Produktverhalten (GitHub-Modus:
  Integration vor dem Push, PR als Standard, Auto-Merge nur per Opt-in,
  Konflikte im Paket-Worktree) und führt keinen eigenen Git-Abschnitt mehr.
  Die Agentenregeln stehen in der englischen Plattformanweisung
  (``bin/vibe_harness.py``; Textprüfung in
  ``tests.unit.test_gh76_platform_instructions``). Beide alten „Strictly
  Enforced“-Blöcke sind ersetzt; ``gh pr merge --squash --delete-branch``
  und ``git branch -D`` stehen nicht mehr im Agentenauftrag. Der Abschnitt
  „Out of scope“ nennt die Freigabe und den konfigurierten Auto-Merge-Opt-in.
  Der Modul-Docstring von ``bin/vibe_github.py`` beschreibt das
  Merge-Verhalten mit ``GITHUB_AUTO_MERGE``.

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
HARNESS = REPO / "bin" / "vibe_harness.py"
SPEC = REPO / "SPEC.md"

OLD_SPEC_HEADINGS = (
    "## Git Workflow & Branch Rules (Strictly Enforced)",
    "## Git&GitHub Workflow & Branch Rules (Strictly Enforced)",
)

# Die drei Runner-Merge-Aussagen der englischen SPEC (Abschnitt
# "Work packages and feedback").
RUNNER_MERGE_STATEMENTS = (
    "In GitHub mode, the runner fetches the current integration state and "
    "merges it into the feature branch before pushing. Conflicts are "
    "resolved in the package worktree.",
    "Without auto-merge, the runner opens a PR and waits for manual merge "
    "and closure confirmation. The worktree remains registered in the "
    "meantime.",
    "With auto-merge enabled, the runner may squash-merge the approved PR "
    "after all gates pass. Final synchronization and cleanup follow "
    "confirmed merge.",
)


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

    def test_spec_has_no_separate_git_section(self):
        """Vorbedingung: ``SPEC.md``.
        Aktion: Überschriften und die Runner-Merge-Aussagen lesen.
        Erwartung: keine ``## ``-Überschrift nennt Git; der GitHub-Modus,
        der PR-Standard und der bestätigte Auto-Merge sind als
        Produktverhalten formuliert.
        Fehlerfall: eigener Git-Abschnitt oder fehlende Merge-Aussagen.
        """
        headings = [line for line in self.text.splitlines()
                    if line.startswith("## ") and "Git" in line]
        self.assertEqual([], headings, headings)
        for statement in RUNNER_MERGE_STATEMENTS:
            self.assertIn(statement, self.text)

    def test_platform_instructions_own_runner_actions_and_conflict_repair(self):
        """Vorbedingung: ``bin/vibe_harness.py``.
        Aktion: die englische Plattformanweisung lesen.
        Erwartung: der Runner besitzt Worktrees, Branches, Integration, Push,
        PR und Merge; Konflikte werden im Paket-Worktree fortgesetzt, ohne
        zweiten Merge, Abort, Rebase oder pauschale Seitenwahl.
        Fehlerfall: Agentenseitige Git-Aktionen bleiben erlaubt oder der
        Konfliktweg fehlt.
        """
        text = HARNESS.read_text(encoding="utf-8")
        self.assertIn(
            "The runner owns worktrees, branches, integration, push, "
            "PR creation, merge, and cleanup. Do not perform those actions "
            "yourself.",
            text,
        )
        for fragment in ("continue that merge",
                         "Do not start another merge, abort",
                         "rebase",
                         "choose one side wholesale"):
            self.assertIn(fragment, text, "Konfliktweg fehlt: %r" % fragment)

    def test_spec_documents_pr_only_default_and_opt_in_auto_merge(self):
        """Vorbedingung: ``SPEC.md``.
        Aktion: Aussagen zum Merge-Verhalten lesen.
        Erwartung: ohne Auto-Merge bleibt der PR manuell und der Worktree
        registriert; mit Auto-Merge ist der Squash-Merge nach allen Gates
        erlaubt; „Out of scope“ verlangt den konfigurierten Opt-in.
        Fehlerfall: Standard oder Opt-in-Bedingung fehlen.
        """
        self.assertIn(
            "Without auto-merge, the runner opens a PR and waits for manual "
            "merge and closure confirmation.",
            self.text,
        )
        self.assertIn("The worktree remains registered in the meantime.",
                      self.text)
        self.assertIn(
            "With auto-merge enabled, the runner may squash-merge the "
            "approved PR after all gates pass.",
            self.text,
        )
        self.assertIn("Automatic GitHub merge requires the configured opt-in.",
                      self.text)

    def test_no_agent_side_squash_merge_or_force_delete_remains(self):
        """Vorbedingung: ``SPEC.md``.
        Aktion: verbotene Agentenkommandos suchen.
        Erwartung: ``gh pr merge --squash --delete-branch`` und
        ``git branch -D`` kommen nicht mehr vor.
        Fehlerfall: Agentenauftrag enthält weiterhin Merge/Force-Delete.
        """
        self.assertNotIn("gh pr merge --squash --delete-branch", self.text)
        self.assertNotIn("git branch -D", self.text)

    def test_out_of_scope_line_names_authorization_and_auto_merge(self):
        """Vorbedingung: Abschnitt „Out of scope“.
        Aktion: die alte deutsche Zeile und die englische Formulierung suchen.
        Erwartung: Die alte Zeile ohne Freigabebezug ist weg; die englische
        Zeile nennt die Freigabe und den konfigurierten Auto-Merge-Opt-in.
        Fehlerfall: unveränderte alte Aussage oder fehlender Opt-in-Bezug.
        """
        old = ("- Automatische Veröffentlichung, Push, Merge oder Release "
               "ohne Freigabe.")
        self.assertNotIn(old, self.text)
        self.assertIn(
            "- Automatic publication, push, merge, or release without "
            "authorization.",
            self.text,
        )
        self.assertIn("Automatic GitHub merge requires the configured opt-in.",
                      self.text)

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
