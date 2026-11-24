"""Abnahme der acht Maßnahmen im Paket-Läufer.

Geprüft werden Preflight, Isolation je Paket, Abschlussschranke,
Fehlerklassen, Auswahlordnung, Agenten-Verfügbarkeit, Abschlussbericht und
Aufräumen mit echten Git-Repositories und einer nachgebildeten
opencode-Ablage. Es werden keine Modellaufrufe ausgeführt.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support


FEEDBACK_ONE = [support.ticket_record(
    "F1", "Erstes Paket", type="feedback", description="Test")]
FEEDBACK_TWO = [
    support.ticket_record("F1", "Erstes Paket", type="feedback",
                          description="Test"),
    support.ticket_record("F2", "Zweites Paket", type="feedback",
                          description="Test"),
]
FEEDBACK_THREE = FEEDBACK_TWO + [
    support.ticket_record("F3", "Drittes Paket", type="feedback",
                          description="Test"),
]


class RunnerGateTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        (self.tool_bin / "vibe").write_text(support.FAKE_VIBE, encoding="utf-8")
        (self.tool_bin / "vibe").chmod(0o755)
        self.runtime = self.root / "_logs"
        self.project = self.root / "proj"
        support.init_repo(self.project)
        self.write_project(feedback=FEEDBACK_THREE)
        self.calls = self.root / "calls.log"
        self.counter = self.root / "counter"
        self.fakebin = support.install_fake_tools(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def write_project(self, env_text=None, feedback=None):
        env_text = env_text or (
            "TYPE=generic\n"
            "AGENT=tester\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL="true"\n'
            "MAX_RETRIES=1\n"
        )
        support.write_project(
            self.project,
            env_text,
            feedback=feedback if feedback is not None else FEEDBACK_THREE,
        )
        support.git(self.project, "add", "-A")
        if support.git(self.project, "diff", "--cached", "--quiet").returncode:
            support.commit_all(self.project, "Ausgangsstand")

    def env(self, **extra):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_"):
                env.pop(key, None)
        for key in ("AGENT", "MAX_PACKAGES", "MAX_RETRIES", "SANDBOX",
                    "SANDBOX_TOOLS", "VERIFY_FULL", "VERIFY_PACKAGE"):
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(self.root),
                "VIBE_INSTALL": str(self.install),
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_AGENTS_DIR": str(self.agents),
                "VIBE_LOGNAME": "proj",
                "VIBE_MAX_PACKAGES": "2",
                "VIBE_RETRY_DELAY": "0",
                "HOME": str(self.home),
                "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
                "FAKE_CALLS": str(self.calls),
                "FAKE_COUNTER": str(self.counter),
            }
        )
        env.update(extra)
        return env

    def run_runner(self, **extra):
        return subprocess.run(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(self.project)],
            cwd=str(self.project),
            env=self.env(**extra),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def log(self):
        path = self.runtime / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def call_lines(self):
        if not self.calls.exists():
            return []
        return self.calls.read_text(encoding="utf-8").splitlines()

    def worktrees(self):
        return [path for path in (self.runtime / "worktrees").glob("*") if path.is_dir()]


class PreflightRunnerTest(RunnerGateTestCase):
    def test_dirty_worktree_blocks_before_any_agent_call(self):
        (self.project / "unfertig.txt").write_text("x\n", encoding="utf-8")

        result = self.run_runner()

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("BLOCKIERT", result.stdout)
        self.assertIn("Arbeitsbaum", result.stdout)
        self.assertEqual(self.call_lines(), [])

    def test_missing_review_agent_blocks_before_any_agent_call(self):
        (self.agents / "code-reviewer.md").unlink()

        result = self.run_runner()

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("REVIEWER", result.stdout)
        self.assertEqual(self.call_lines(), [])


class WorktreeIsolationTest(RunnerGateTestCase):
    def test_failed_worktree_creation_leaves_no_directory(self):
        real_git = shutil.which("git")
        wrapper = self.fakebin / "git"
        wrapper.write_text(
            "#!/bin/sh\n"
            'case " $* " in\n'
            '  *" worktree add "*) exit 1 ;;\n'
            "esac\n"
            'exec "' + real_git + '" "$@"\n',
            encoding="utf-8",
        )
        wrapper.chmod(0o755)

        result = self.run_runner()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Arbeitskopie", result.stdout)
        self.assertEqual(self.worktrees(), [], "Arbeitskopie blieb liegen")
        self.assertEqual(self.call_lines(), [])

    def test_dirty_integration_tree_between_packages_blocks(self):
        self.write_project(feedback=FEEDBACK_TWO)

        result = self.run_runner(
            FAKE_DIRTY_INTEGRATION=str(self.project), VIBE_MAX_PACKAGES="2"
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Integrationsstand ist nicht sauber", result.stdout)
        self.assertEqual(len(self.call_lines()), 1, self.call_lines())
        self.assertEqual(self.worktrees(), [], "Arbeitskopie blieb liegen")

    def test_agent_works_in_a_worktree_under_runtime_and_it_is_removed(self):
        self.write_project(feedback=FEEDBACK_ONE)

        result = self.run_runner()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.call_lines()
        self.assertEqual(len(calls), 1, calls)
        _, worktree = calls[0].split("\t")
        self.assertTrue(
            worktree.startswith(str(self.runtime / "worktrees")), worktree
        )
        state = self.project / ".vibe" / "tmp" / "next-package.json"
        self.assertTrue(state.is_file(), "projektlokaler Auswahlstand fehlt")
        self.assertEqual(self.worktrees(), [], "Arbeitskopie wurde nicht entfernt")
        # B16: Paketbranches folgen dem Muster feature/{owner}/{id}
        # (Fixture: feature/test/<id>). Die frühere Prüfung auf "vibe/*"
        # war seit dem neuen Branch-Schema immer erfüllt und damit blind.
        branches = support.git(
            self.project, "branch", "--list", "feature/*"
        ).stdout
        self.assertEqual(branches.strip(), "", "Paketbranch wurde nicht entfernt")
        self.assertEqual(
            support.git(self.project, "status", "--porcelain").stdout, ""
        )


class ClosingGateTest(RunnerGateTestCase):
    def test_missing_artifacts_block_and_stop_the_run(self):
        self.write_project(feedback=FEEDBACK_ONE)

        result = self.run_runner(FAKE_MODE="no-artifacts")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Abschlussschranke für F1", result.stdout)
        # B9: Der Schrankenbefund löst zwei Reparaturrunden im selben
        # Arbeitsbaum aus (Erstlauf plus zwei Reparaturen).
        calls = self.call_lines()
        self.assertEqual(len(calls), 3, calls)
        self.assertEqual(
            len({line.split("\t", 1)[1] for line in calls}),
            1,
            "Reparaturrunden liefen nicht im selben Arbeitsbaum: %s" % calls,
        )
        self.assertTrue(self.worktrees(), "Blockierte Arbeitskopie fehlt zur Diagnose")
        self.assertIn("BLOCKIERT", result.stdout)

    def test_ticket_proof_is_required_for_tickets_too(self):
        self.write_project(
            env_text=(
                "TYPE=generic\nAGENT=tester\nTESTER=test-agent\n"
                "REVIEWER=code-reviewer\n"
                'VERIFY_PACKAGE="true"\nVERIFY_FULL="true"\nMAX_RETRIES=1\n'
            ),
            feedback=FEEDBACK_ONE,
        )
        support.write_project(
            self.project,
            (self.project / ".vibe" / "project.env").read_text(encoding="utf-8"),
            feedback=FEEDBACK_ONE,
            tickets=[support.ticket_record("T1", "Ticket",
                                           description="Test")],
        )

        result = self.run_runner(VIBE_MAX_PACKAGES="1")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Arbeitspaket T1", self.log())
        self.assertIn("Geschlossen: T1", result.stdout)


class ErrorClassTest(RunnerGateTestCase):
    def test_quota_stops_immediately_without_retry(self):
        self.write_project(
            env_text=(
                "TYPE=generic\nAGENT=tester\nTESTER=test-agent\n"
                "REVIEWER=code-reviewer\n"
                'VERIFY_PACKAGE="true"\nVERIFY_FULL="true"\nMAX_RETRIES=3\n'
            ),
            feedback=FEEDBACK_ONE,
        )

        result = self.run_runner(FAKE_MODE="quota")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(len(self.call_lines()), 1, self.call_lines())
        self.assertIn("Quota/Kontingent bei F1", result.stdout)
        self.assertIn("BLOCKIERT", result.stdout)

    def test_network_retry_does_not_consume_the_package_budget(self):
        self.write_project(feedback=FEEDBACK_TWO)

        result = self.run_runner(
            FAKE_MODE_SEQUENCE="network-first,complete,complete",
            VIBE_MAX_PACKAGES="2",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(self.call_lines()), 3, self.call_lines())
        self.assertIn("Geschlossen: F1", result.stdout)
        self.assertIn("Geschlossen: F2", result.stdout)

    def test_retry_limit_skips_a_package_and_continues(self):
        self.write_project(feedback=FEEDBACK_TWO)

        result = self.run_runner(FAKE_MODE="fail", VIBE_MAX_PACKAGES="2")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(self.call_lines()), 4, self.call_lines())
        self.assertIn("Überspringe F1 nach 2 Versuchen", self.log())
        self.assertIn("Blockiert: F1", result.stdout)
        self.assertIn("Blockiert: F2", result.stdout)


class ReportTest(RunnerGateTestCase):
    def test_report_lists_closed_blocked_and_open_packages(self):
        # F1 schließt ab. F2 scheitert im Erstlauf und in beiden
        # Reparaturrunden; die Sequenz muss deshalb dauerhaft bei
        # ``no-artifacts`` bleiben (der letzte Eintrag wiederholt sich).
        result = self.run_runner(
            FAKE_MODE_SEQUENCE="complete,no-artifacts,no-artifacts,no-artifacts",
            VIBE_MAX_PACKAGES="3",
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Geschlossen: F1", result.stdout)
        self.assertIn("Blockiert: F2", result.stdout)
        self.assertIn("Offen: F3", result.stdout)
        self.assertTrue((self.runtime / "proj.report.txt").is_file())


class IntegrationVerificationTest(RunnerGateTestCase):
    def test_final_verification_runs_on_a_clean_integration_tree(self):
        self.write_project(
            env_text=(
                "TYPE=generic\nAGENT=tester\nTESTER=test-agent\n"
                "REVIEWER=code-reviewer\n"
                'VERIFY_PACKAGE="true"\n'
                'VERIFY_FULL="git status --porcelain > \\"$VIBE_RUNTIME/verify.status\\""\n'
                "MAX_RETRIES=1\n"
            ),
            feedback=FEEDBACK_ONE,
        )

        result = self.run_runner(VIBE_MAX_PACKAGES="1")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        status = (self.runtime / "verify.status").read_text(encoding="utf-8")
        self.assertEqual(status, "", "Gesamtprüfung lief nicht auf sauberem Stand")


if __name__ == "__main__":
    unittest.main()
