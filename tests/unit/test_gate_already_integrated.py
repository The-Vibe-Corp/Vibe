"""Abschlussschranke: bereits in den Integrationsstand gemergte Pakete.

Fachlicher Hintergrund (Bug F25): Ein Paket kann vollständig implementiert,
reviewt und in den Integrationsbranch gemergt sein, während der Haken in der
nicht versionierten Arbeitsnotiz erst in der Arbeitskopie gesetzt wurde. Die
neue Arbeitskopie basiert auf dem Integrationsstand und enthält keine neuen
Commits. Die Schranke muss den Nachweis im Basisstand erkennen, statt einen
neuen Paketcommit zu verlangen.

Die Tests arbeiten mit echten temporären Git-Repositories. FEEDBACK.md und
TICKETS.md sind darin wie im Produktprojekt per .gitignore ausgenommen. Es
werden keine Modellaufrufe, Netzverbindungen oder externen Dienste benutzt.

Zuordnung der Testklassen zu den Akzeptanzkriterien:

* ``AlreadyIntegratedPassTest``          -> A1, A6
* ``AlreadyIntegratedPrefixTest``        -> A2
* ``AlreadyIntegratedUnknownProofTest``  -> A3
* ``NewCommitsRegressionTest``           -> A4
* ``AlreadyIntegratedDefectTest``        -> A5
"""
import importlib.machinery
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "bin" / "vibe_packages.py"

ENV_TEXT = (
    "TYPE=generic\n"
    "AGENT=tester\n"
    "TESTER=test-agent\n"
    "REVIEWER=code-reviewer\n"
    'VERIFY_PACKAGE="true"\n'
    'VERIFY_FULL="true"\n'
)


def load_module():
    loader = importlib.machinery.SourceFileLoader(
        "vibe_packages_already_integrated_under_test", str(MODULE)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class AlreadyIntegratedGateTestCase(unittest.TestCase):
    """Gemeinsames echtes Repository mit nicht versionierten Arbeitsnotizen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        support.init_repo(self.project)
        # Wie im Produktprojekt: Arbeitsnotizen sind Laufzeitstand und werden
        # nicht versioniert. Das ist für A6 entscheidend.
        (self.project / ".gitignore").write_text(
            "FEEDBACK.md\nTICKETS.md\n", encoding="utf-8"
        )
        support.write_project(self.project, ENV_TEXT)
        support.commit_all(self.project)
        self.initial = self.revision()
        self.module = load_module()

    def tearDown(self):
        self.tmp.cleanup()

    # -- Git- und Dateihilfen ------------------------------------------------

    def git_ok(self, *args):
        result = support.git(self.project, *args)
        self.assertEqual(
            result.returncode, 0, result.stdout + result.stderr
        )
        return result

    def revision(self):
        return support.git(
            self.project, "rev-parse", "HEAD"
        ).stdout.strip()

    def short_revision(self):
        return support.git(
            self.project, "rev-parse", "--short", "HEAD"
        ).stdout.strip()

    def commit(self, message):
        support.commit_all(self.project, message)
        return self.short_revision()

    def write_feedback(self, text):
        (self.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n" + text, encoding="utf-8"
        )

    def write_tickets(self, text):
        (self.project / "TICKETS.md").write_text(
            "# TICKETS\n\n" + text, encoding="utf-8"
        )

    def write_docs(self, pid="F1", docs=True, review="Verdict: PASS"):
        """Legt Feature-Dokumentation und Review an (beide optional)."""
        if docs:
            features = self.project / "docs" / "features"
            features.mkdir(parents=True, exist_ok=True)
            (features / (pid + ".md")).write_text(
                "# " + pid + "\n\nTestdokumentation.\n", encoding="utf-8"
            )
        if review is not None:
            reviews = self.project / "docs" / "reviews"
            reviews.mkdir(parents=True, exist_ok=True)
            (reviews / (pid + "-review-1.md")).write_text(
                "# Review\n\n" + review + "\n", encoding="utf-8"
            )

    def write_note(
        self,
        pid="F1",
        source="FEEDBACK.md",
        checked=True,
        commit=None,
        test_proof=True,
    ):
        """Schreibt den Ticketblock in die nicht versionierte Arbeitsnotiz."""
        marker = "- [x]" if checked else "- [ ]"
        lines = [marker + " " + pid + " Testpaket", "  Beschreibung: Test"]
        if commit is not None:
            lines.append("  Commit: " + commit)
            if test_proof:
                lines.append(
                    "  Test: test_" + pid.lower().replace("-", "_")
                )
        text = "\n".join(lines) + "\n"
        if source == "TICKETS.md":
            self.write_tickets(text)
        else:
            self.write_feedback(text)

    # -- Zustände ------------------------------------------------------------

    def integrated_base(self, pid="F1", prefix=True, docs=True, review="Verdict: PASS"):
        """Baut einen Integrationsstand, der das Paket bereits enthält.

        Der Paketcommit (mit Präfix) und die Dokumentation liegen vollständig
        im Basisstand. Danach entsteht kein weiterer Commit. Rückgabe:
        (Nachweis-Commit, Basis-Commit).
        """
        (self.project / ("impl-" + pid + ".txt")).write_text(
            pid + "\n", encoding="utf-8"
        )
        proof = self.commit((pid + ": Umsetzung") if prefix else "Umsetzung")
        if docs or review is not None:
            self.write_docs(pid, docs=docs, review=review)
            self.commit((pid + ": Nachweis") if prefix else "Nachweis")
        return proof, self.revision()

    def errors(self, pid="F1", base=None):
        return self.module.gate_errors(str(self.project), pid, base or self.initial)


class AlreadyIntegratedPassTest(AlreadyIntegratedGateTestCase):
    """A1/A6: Gemergtes Paket ohne neue Commits gilt als integriert."""

    def test_integrated_package_without_new_commits_passes(self):
        # Vorbedingung: Paketcommit, Feature-Doku und PASS-Review sind bereits
        # im Basisstand; die getickte Notiz ist ignoriert und uncommitted.
        proof, base = self.integrated_base()
        self.write_note(commit=proof)
        self.assertEqual(support.git(self.project, "status", "--porcelain").stdout, "")

        # Aktion: Schranke gegen denselben Integrationsstand prüfen.
        errors = self.errors(base=base)

        # Erwartet: keine Befunde.
        self.assertEqual(errors, [])

    def test_integrated_package_proof_equal_to_base_passes(self):
        # Vorbedingung: Der Nachweis-Commit ist selbst der Basisstand
        # (Fast-Forward-Merge ohne spätere Commits).
        (self.project / "impl-F1.txt").write_text("F1\n", encoding="utf-8")
        self.write_docs("F1")
        base = self.commit("F1: Umsetzung und Nachweis")
        self.write_note(commit=base)

        errors = self.errors(base=base)

        self.assertEqual(errors, [])

    def test_integrated_package_listed_in_tickets_passes(self):
        # A1 gilt unabhängig davon, ob der Nachweis in TICKETS.md oder
        # FEEDBACK.md steht.
        proof, base = self.integrated_base()
        self.write_note(source="TICKETS.md", commit=proof)

        errors = self.errors(base=base)

        self.assertEqual(errors, [])

    def test_uncommitted_work_notes_do_not_block_the_integrated_package(self):
        # A6: Die Notiz ist uncommitted und per .gitignore ausgenommen; das
        # darf weder als unsauberer Arbeitsbaum noch als fehlender Commit
        # gewertet werden.
        proof, base = self.integrated_base()
        self.write_note(commit=proof)
        self.assertEqual(
            support.git(self.project, "check-ignore", "FEEDBACK.md").returncode,
            0,
        )
        self.assertEqual(
            support.git(self.project, "status", "--porcelain").stdout, ""
        )

        errors = self.errors(base=base)

        self.assertEqual(errors, [])


class AlreadyIntegratedPrefixTest(AlreadyIntegratedGateTestCase):
    """A2: Fehlender Paketpräfix im Nachweiscommit bleibt blockierend."""

    def test_integrated_proof_commit_without_package_prefix_still_blocks(self):
        # Vorbedingung: Der Nachweiscommit ist Vorfahre von base, seine
        # Commit-Message hat aber nicht das Präfix "F1:".
        proof, base = self.integrated_base(prefix=False)
        self.write_note(commit=proof)

        errors = self.errors(base=base)

        # Erwartet: Die bisherigen Commit-Befunde bleiben erhalten.
        self.assertTrue(
            any("Kein Commit seit dem Integrationsstand" in error for error in errors),
            errors,
        )
        self.assertTrue(any("Präfix" in error for error in errors), errors)


class AlreadyIntegratedUnknownProofTest(AlreadyIntegratedGateTestCase):
    """A3: Nachweis außerhalb des Basisstands bleibt blockierend."""

    def test_proof_commit_on_another_branch_still_blocks(self):
        # Vorbedingung: Alles außer dem Nachweis ist erfüllt; der genannte
        # Commit entsteht auf einem anderen Zweig und ist nicht Vorfahre
        # von base.
        _, base = self.integrated_base()
        self.git_ok("checkout", "-q", "-b", "anderer-zweig")
        (self.project / "seitlich.txt").write_text("x\n", encoding="utf-8")
        side = self.commit("F1: Umsetzung")
        self.assertEqual(self.short_revision(), side)
        self.git_ok("checkout", "-q", "main")
        self.assertEqual(self.revision(), base)
        self.write_note(commit=side)

        errors = self.errors(base=base)

        self.assertTrue(errors, "Die Schranke darf nicht durchlassen.")
        self.assertTrue(any("Nachweis" in error for error in errors), errors)

    def test_unknown_proof_commit_still_blocks(self):
        # Vorbedingung: Der Nachweis nennt einen syntaktisch gültigen, aber
        # nicht vorhandenen Commit.
        _, base = self.integrated_base()
        self.write_note(commit="abcdef1")

        errors = self.errors(base=base)

        self.assertTrue(errors, "Die Schranke darf nicht durchlassen.")
        self.assertTrue(any("Nachweis" in error for error in errors), errors)


class NewCommitsRegressionTest(AlreadyIntegratedGateTestCase):
    """A4: Pakete mit neuen Commits seit base verhalten sich unverändert."""

    def new_package(
        self,
        pid="F1",
        prefix=True,
        checked=True,
        commit_proof=True,
        test_proof=True,
        docs=True,
        review="Verdict: PASS",
        proof_commit=None,
    ):
        (self.project / ("impl-" + pid + ".txt")).write_text(
            pid + "\n", encoding="utf-8"
        )
        proof = self.commit((pid + ": Umsetzung") if prefix else "Umsetzung")
        self.write_note(
            pid=pid,
            checked=checked,
            commit=(proof_commit or proof) if commit_proof else None,
            test_proof=test_proof,
        )
        self.write_docs(pid, docs=docs, review=review)
        self.commit((pid + ": Nachweis") if prefix else "Nachweis")
        return proof

    def test_new_package_with_new_commits_passes(self):
        self.new_package()

        self.assertEqual(self.errors(), [])

    def test_new_package_without_prefix_still_blocks(self):
        self.new_package(prefix=False)

        errors = self.errors()

        self.assertTrue(any("Präfix" in error for error in errors), errors)

    def test_proof_commit_outside_the_package_range_still_blocks(self):
        self.new_package(proof_commit=self.initial)

        errors = self.errors()

        self.assertTrue(any("Nachweis" in error for error in errors), errors)

    def test_new_package_without_feature_documentation_still_blocks(self):
        self.new_package(docs=False)

        errors = self.errors()

        self.assertTrue(any("docs/features" in error for error in errors), errors)

    def test_new_package_without_review_still_blocks(self):
        self.new_package(review=None)

        errors = self.errors()

        self.assertTrue(any("Review" in error for error in errors), errors)

    def test_new_package_with_review_without_pass_still_blocks(self):
        self.new_package(review="Verdict: CHANGES REQUIRED")

        errors = self.errors()

        self.assertTrue(any("PASS" in error for error in errors), errors)

    def test_new_package_with_newer_review_without_pass_still_blocks(self):
        self.new_package(review="Verdict: PASS")
        (self.project / "docs" / "reviews" / "F1-review-2.md").write_text(
            "# Review\n\nVerdict: CHANGES REQUIRED\n", encoding="utf-8"
        )
        self.commit("F1: neues Review")

        errors = self.errors()

        self.assertTrue(any("PASS" in error for error in errors), errors)

    def test_new_package_with_unchecked_ticket_still_blocks(self):
        self.new_package(checked=False)

        errors = self.errors()

        self.assertTrue(any("nicht abgehakt" in error for error in errors), errors)

    def test_new_package_with_incomplete_proof_still_blocks(self):
        self.new_package(test_proof=False)

        errors = self.errors()

        self.assertTrue(any("Nachweis" in error for error in errors), errors)

    def test_unrelated_new_commit_does_not_activate_the_shortcut(self):
        # A1 verlangt ausdrücklich, dass seit base kein Commit entstanden ist.
        # Ein fremder Commit nach dem Integrationsstand darf den gespeicherten
        # alten Nachweis nicht nachträglich durchlassen.
        proof, base = self.integrated_base()
        (self.project / "andere-arbeit.txt").write_text("x\n", encoding="utf-8")
        self.commit("Andere Arbeit")
        self.assertNotEqual(self.revision(), base)
        self.write_note(commit=proof)

        errors = self.errors(base=base)

        self.assertTrue(any("Präfix" in error for error in errors), errors)

    def test_new_package_commit_does_not_accept_the_old_proof_commit(self):
        # Auch ein neuer Paketcommit lässt den Nachweis nicht durch, wenn er
        # auf einen Commit außerhalb des Paketbereichs verweist.
        proof, base = self.integrated_base()
        (self.project / "nachbesserung.txt").write_text("x\n", encoding="utf-8")
        self.commit("F1: Nachbesserung")
        self.write_note(commit=proof)

        errors = self.errors(base=base)

        self.assertTrue(any("Nachweis" in error for error in errors), errors)


class AlreadyIntegratedDefectTest(AlreadyIntegratedGateTestCase):
    """A5: Ein gemergtes Paket entbindet nicht von den übrigen Nachweisen."""

    def test_integrated_package_with_unchecked_ticket_still_blocks(self):
        proof, base = self.integrated_base()
        self.write_note(checked=False, commit=proof)

        errors = self.errors(base=base)

        self.assertTrue(any("nicht abgehakt" in error for error in errors), errors)

    def test_integrated_package_without_proof_still_blocks(self):
        _, base = self.integrated_base()
        self.write_note(commit=None)

        errors = self.errors(base=base)

        self.assertTrue(any("Nachweis" in error for error in errors), errors)

    def test_integrated_package_with_incomplete_proof_still_blocks(self):
        proof, base = self.integrated_base()
        self.write_note(commit=proof, test_proof=False)

        errors = self.errors(base=base)

        self.assertTrue(any("Nachweis" in error for error in errors), errors)

    def test_integrated_package_without_feature_documentation_still_blocks(self):
        proof, base = self.integrated_base(docs=False)
        self.write_note(commit=proof)

        errors = self.errors(base=base)

        self.assertTrue(any("docs/features" in error for error in errors), errors)

    def test_integrated_package_without_review_still_blocks(self):
        proof, base = self.integrated_base(review=None)
        self.write_note(commit=proof)

        errors = self.errors(base=base)

        self.assertTrue(any("Review" in error for error in errors), errors)

    def test_integrated_package_with_review_without_pass_still_blocks(self):
        proof, base = self.integrated_base(review="Verdict: CHANGES REQUIRED")
        self.write_note(commit=proof)

        errors = self.errors(base=base)

        self.assertTrue(any("PASS" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
