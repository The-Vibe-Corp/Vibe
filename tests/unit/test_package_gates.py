"""Tests für Paketauswahl, Preflight, Abschlussschranke und Fehlerklassen.

Die Tests arbeiten mit echten, kleinen Git-Repositories und prüfen die
versionierte Läuferlogik in ``bin/vibe_packages.py``. Es werden keine
Modellaufrufe oder externen Dienste verwendet.
"""
import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "bin" / "vibe_packages.py"


def load_module():
    loader = importlib.machinery.SourceFileLoader(
        "vibe_packages_under_test", str(MODULE)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class PackageTestCase(unittest.TestCase):
    """Gemeinsames echtes Repository mit Agenten und Prüfbefehl."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        support.init_repo(self.project)
        self.agents = self.root / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        support.write_project(
            self.project,
            "TYPE=generic\n"
            "AGENT=tester\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL="true"\n',
        )
        support.commit_all(self.project)
        self.module = load_module()

    def tearDown(self):
        self.tmp.cleanup()

    def write_feedback(self, text):
        (self.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n" + text, encoding="utf-8"
        )

    def write_tickets(self, text):
        (self.project / "TICKETS.md").write_text(
            "# TICKETS\n\n" + text, encoding="utf-8"
        )

    def commit(self, message):
        support.commit_all(self.project, message)
        return support.git(self.project, "rev-parse", "--short", "HEAD").stdout.strip()


class PackageSelectionTest(PackageTestCase):
    def select(self, skip=None):
        return self.module.select_package(
            str(self.project), skip=skip, state_path=self.root / "state.json"
        )

    def test_tickets_are_selected_before_feedback(self):
        self.write_tickets("- [ ] T1 Ticket zuerst\n  Beschreibung: Test\n")
        self.write_feedback("- [ ] F1 Feedback danach\n  Beschreibung: Test\n")

        selected = self.select()

        self.assertIsNotNone(selected)
        self.assertEqual(selected["id"], "T1")
        self.assertEqual(selected["source"], "TICKETS.md")

    def test_dependencies_block_a_ticket_until_the_dependency_is_done(self):
        self.write_tickets(
            "- [ ] T1 Abhängig\n  Abhängigkeiten: T2\n"
            "- [ ] T2 Grundlage\n"
        )

        first = self.select()
        self.assertEqual(first["id"], "T2")

        self.write_tickets(
            "- [ ] T1 Abhängig\n  Abhängigkeiten: T2\n"
            "- [x] T2 Grundlage\n  Commit: %s; Test: test_t2\n"
            % self.commit("T2: Grundlage")
        )
        support.commit_all(self.project, "T2: Nachweis")

        second = self.select()
        self.assertEqual(second["id"], "T1")

    def test_a_checked_ticket_without_proof_is_still_open(self):
        self.write_tickets("- [x] T1 Ohne Nachweis\n  Beschreibung: Test\n")

        selected = self.select()

        self.assertIsNotNone(selected)
        self.assertEqual(selected["id"], "T1")

    def test_a_checked_ticket_with_proof_counts_as_done(self):
        (self.project / "umsetzung.txt").write_text("x\n", encoding="utf-8")
        hash_value = self.commit("T1: Umsetzung")
        self.write_tickets(
            "- [x] T1 Mit Nachweis\n  Commit: %s; Test: test_t1\n" % hash_value
        )
        support.commit_all(self.project, "T1: Nachweis")

        self.assertIsNone(self.select())

    def test_blocked_entries_are_skipped(self):
        self.write_tickets(
            "- [ ] T1 Blockiert\n  BLOCKIERT: externer Dienst fehlt\n"
            "- [ ] T2 Offen\n"
        )

        selected = self.select()

        self.assertEqual(selected["id"], "T2")

    def test_priority_orders_tickets(self):
        self.write_tickets(
            "- [ ] T1 Später\n  Priorität: P2\n"
            "- [ ] T2 Sofort\n  Priorität: P0\n"
        )

        selected = self.select()

        self.assertEqual(selected["id"], "T2")

    def test_skip_list_is_honoured(self):
        self.write_tickets("- [ ] T1\n- [ ] T2\n")

        selected = self.select(skip={"T1"})

        self.assertEqual(selected["id"], "T2")

    def test_selection_state_is_written_inside_the_project(self):
        self.write_feedback("- [ ] F1\n")
        state = self.project / ".vibe" / "tmp" / "next-package.json"

        selected = self.module.select_package(str(self.project))

        self.assertEqual(selected["id"], "F1")
        self.assertTrue(state.is_file())
        self.assertEqual(state, self.project / ".vibe" / "tmp" / "next-package.json")


class ClassificationTest(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_success_is_ok(self):
        self.assertEqual(self.module.classify_output(0, ""), "ok")

    def test_quota_is_detected(self):
        self.assertEqual(
            self.module.classify_output(1, "429 rate limit exceeded"), "quota"
        )

    def test_auth_is_detected(self):
        self.assertEqual(
            self.module.classify_output(1, "401 Unauthorized"), "auth"
        )

    def test_network_is_detected(self):
        self.assertEqual(
            self.module.classify_output(1, "ECONNRESET connection reset"), "network"
        )

    def test_unknown_failure_is_other(self):
        self.assertEqual(self.module.classify_output(1, "kaputt"), "other")

    def test_quota_wins_over_network_words(self):
        self.assertEqual(
            self.module.classify_output(
                1, "network error: 429 too many requests"
            ),
            "quota",
        )


class PreflightTest(PackageTestCase):
    def errors(self):
        return self.module.preflight_errors(
            str(self.project),
            agents_dir=str(self.agents),
            tester="test-agent",
            reviewer="code-reviewer",
        )

    def test_clean_repository_passes(self):
        self.assertEqual(self.errors(), [])

    def test_dirty_working_tree_is_rejected(self):
        (self.project / "unfertig.txt").write_text("x\n", encoding="utf-8")

        errors = self.errors()

        self.assertTrue(any("Arbeitsbaum" in error for error in errors), errors)

    def test_missing_repository_is_rejected(self):
        other = self.root / "ohne-git"
        other.mkdir()

        errors = self.module.preflight_errors(
            str(other),
            agents_dir=str(self.agents),
            tester="test-agent",
            reviewer="code-reviewer",
        )

        self.assertTrue(any("Git-Repository" in error for error in errors), errors)

    def test_missing_test_agent_is_rejected(self):
        (self.agents / "test-agent.md").unlink()

        errors = self.errors()

        self.assertTrue(any("TESTER" in error for error in errors), errors)

    def test_missing_review_agent_is_rejected(self):
        (self.agents / "code-reviewer.md").unlink()

        errors = self.errors()

        self.assertTrue(any("REVIEWER" in error for error in errors), errors)

    def test_missing_package_check_is_rejected(self):
        (self.project / ".vibe" / "project.env").write_text(
            'TYPE=generic\nTESTER=test-agent\nREVIEWER=code-reviewer\n'
            'VERIFY_FULL="echo TODO"\n',
            encoding="utf-8",
        )
        support.commit_all(self.project, "Prüfbefehl entfernt")

        errors = self.errors()

        self.assertTrue(any("Paketprüfung" in error for error in errors), errors)

    def test_project_local_temp_files_do_not_dirty_the_tree(self):
        temp = self.project / ".vibe" / "tmp"
        temp.mkdir(parents=True)
        (temp / "next-package.json").write_text("{}\n", encoding="utf-8")

        self.assertEqual(self.errors(), [])
        status = support.git(self.project, "status", "--porcelain").stdout
        self.assertEqual(status, "")


class GateTest(PackageTestCase):
    def setUp(self):
        super().setUp()
        self.base = support.git(self.project, "rev-parse", "HEAD").stdout.strip()

    def create_package(
        self,
        pid="F1",
        commit_prefix=True,
        ticket_done=True,
        ticket_proof=True,
        docs=True,
        review="Verdict: PASS",
        proof_commit=None,
    ):
        (self.project / "impl.txt").write_text(pid + "\n", encoding="utf-8")
        support.commit_all(
            self.project, (pid + ": Umsetzung") if commit_prefix else "Umsetzung"
        )
        hash_value = support.git(
            self.project, "rev-parse", "--short", "HEAD"
        ).stdout.strip()
        if ticket_done:
            marker = "- [x]"
        else:
            marker = "- [ ]"
        proof = ""
        if ticket_proof:
            proof = "  Commit: %s; Test: test_%s\n" % (
                proof_commit or hash_value,
                pid.lower().replace("-", "_"),
            )
        self.write_feedback(
            "%s %s Testpaket\n  Beschreibung: Test\n%s" % (marker, pid, proof)
        )
        if docs:
            (self.project / "docs" / "features").mkdir(parents=True, exist_ok=True)
            (self.project / "docs" / "features" / (pid + ".md")).write_text(
                "# " + pid + "\n", encoding="utf-8"
            )
        if review is not None:
            (self.project / "docs" / "reviews").mkdir(parents=True, exist_ok=True)
            (self.project / "docs" / "reviews" / (pid + "-review-1.md")).write_text(
                "# Review\n\n" + review + "\n", encoding="utf-8"
            )
        support.commit_all(
            self.project, (pid + ": Nachweis") if commit_prefix else "Nachweis"
        )

    def errors(self, pid="F1"):
        return self.module.gate_errors(str(self.project), pid, self.base)

    def test_complete_package_passes(self):
        self.create_package()

        self.assertEqual(self.errors(), [])

    def test_missing_commit_prefix_is_rejected(self):
        self.create_package(commit_prefix=False)

        errors = self.errors()

        self.assertTrue(any("Präfix" in error for error in errors), errors)

    def test_missing_feature_documentation_is_rejected(self):
        self.create_package(docs=False)

        errors = self.errors()

        self.assertTrue(any("docs/features" in error for error in errors), errors)

    def test_missing_review_is_rejected(self):
        self.create_package(review=None)

        errors = self.errors()

        self.assertTrue(any("Review" in error for error in errors), errors)

    def test_review_without_pass_is_rejected(self):
        self.create_package(review="Verdict: CHANGES REQUIRED")

        errors = self.errors()

        self.assertTrue(any("PASS" in error for error in errors), errors)

    def test_ticket_without_proof_is_rejected(self):
        self.create_package(ticket_proof=False)

        errors = self.errors()

        self.assertTrue(any("Nachweis" in error for error in errors), errors)

    def test_ticket_must_be_checked(self):
        self.create_package(ticket_done=False)

        errors = self.errors()

        self.assertTrue(any("nicht abgehakt" in error for error in errors), errors)

    def test_proof_from_outside_the_package_branch_is_rejected(self):
        self.create_package(proof_commit=self.base)

        errors = self.errors()

        self.assertTrue(any("Nachweis" in error for error in errors), errors)

    def test_uncommitted_worktree_is_rejected(self):
        self.create_package()
        (self.project / "offen.txt").write_text("x\n", encoding="utf-8")

        errors = self.errors()

        self.assertTrue(any("sauber" in error for error in errors), errors)


class StatusReportTest(PackageTestCase):
    def test_report_distinguishes_open_blocked_and_done(self):
        (self.project / "fertig.txt").write_text("x\n", encoding="utf-8")
        hash_value = self.commit("F1: Umsetzung")
        self.write_feedback(
            "- [x] F1 Fertig\n  Commit: %s; Test: test_f1\n"
            "- [ ] F2 Blockiert\n  BLOCKIERT: extern\n"
            "- [ ] F3 Offen\n" % hash_value
        )

        support.commit_all(self.project, "Nachweise")

        report = self.module.status_report(str(self.project))

        self.assertEqual(report["done"], ["F1"])
        self.assertEqual(report["blocked"], ["F2"])
        self.assertEqual(report["open"], ["F3"])


if __name__ == "__main__":
    unittest.main()
