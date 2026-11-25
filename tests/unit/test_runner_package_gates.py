"""Paket-Gates des Läufers: Hash-Schutz und transportierte Dateien.

Aufruf: python3 -m unittest tests.unit.test_runner_package_gates -v
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


# ===========================================================================
# T-: Hash-/Diff-Wächter nach dem Agentenlauf
# ===========================================================================

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support  # noqa: E402
from tests.unit.test_github_runner import AP9WiringFixture, git  # noqa: E402

PROJECT_ENV = """TYPE=generic
AGENT=test-agent
TESTER=test-agent
REVIEWER=code-reviewer
VERIFY_PACKAGE="true"
VERIFY_FULL="true"
MAX_RETRIES=3
"""

BASELINE_TEXT = (
    "{\n"
    '  "version": 1,\n'
    '  "min_tests": 1,\n'
    '  "envs": {}\n'
    "}\n"
)


class HashGuardFixture(AP9WiringFixture):
    """Projekt mit transportierter project.env und optionaler (nicht
    transportierter) lokaler Baseline.

    ``.vibe/`` ist wie im echten Projekt git-ignoriert; ``project.env`` liegt
    damit unversioniert im Projekt und wird vom Transport in die Arbeitskopie
    kopiert. ``verify-baseline`` entsteht ebenfalls im Projektordner, wird
    seit GH-46 aber nicht mehr transportiert. Die Dateien entstehen erst nach
    dem Ausgangscommit, damit keine versionierte Kopie den Transport überdeckt.
    """

    def make_guard_project(self, baseline=False, name="proj"):
        project = self.root / name
        support.init_repo(project)
        (project / ".gitignore").write_text("/.vibe/\n", encoding="utf-8")
        support.commit_all(project, "Ausgangsstand")
        (project / ".vibe").mkdir()
        (project / ".vibe" / "project.env").write_text(
            PROJECT_ENV, encoding="utf-8"
        )
        # GH-48: Das Paket liegt unversioniert im Projekt-Ticketspeicher.
        support.write_ticket_store(project, [
            support.ticket_record("F1", "Erstes Paket", type="feedback",
                                  description="Test"),
        ])
        if baseline:
            (project / ".vibe" / "verify-baseline").write_text(
                BASELINE_TEXT, encoding="utf-8"
            )
        return project

    def ticket(self, project, pid="F1"):
        """Liest das Ticket aus dem Projekt-Ticketspeicher."""
        import json

        data = json.loads(
            (project / ".vibe" / "tickets.json").read_text(encoding="utf-8"))
        for record in data["tickets"]:
            if record["id"] == pid:
                return record
        self.fail("Ticket %s fehlt im Speicher" % pid)

    # ---------------------------------------------------------- Beobachtung
    def blocked_lines(self, log):
        return [line for line in log.splitlines()
                if line.startswith("BLOCKIERT")]

    def report(self, project):
        path = self.runtime / (project.name + ".report.txt")
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def agent_calls(self):
        """Nicht-Preflight-Aufrufe des nachgebildeten Agenten."""
        path = self.root / "calls.jsonl"
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [line for line in lines
                if line and not line.startswith("preflight")]

    def assert_blocked_for(self, log, changed_file):
        blocked = self.blocked_lines(log)
        self.assertTrue(blocked, "Der Lauf blockiert nicht:\n" + log)
        self.assertTrue(
            any(changed_file in line for line in blocked),
            "Keine BLOCKIERT-Zeile nennt die veränderte Datei %r:\n%s"
            % (changed_file, log),
        )
        self.assertNotIn("FERTIG", log,
                         "Ein blockiertes Paket darf nicht FERTIG melden:\n"
                         + log)
        self.assertNotIn("REPARATUR", log,
                         "Tampering darf keine Reparaturrunde auslösen:\n"
                         + log)
        self.assertEqual(
            1, len(self.agent_calls()),
            "Der Agent wurde erneut aufgerufen (Reparaturrunde): %r"
            % (self.agent_calls(),),
        )

    def assert_not_blocked(self, result, project):
        """Das Paket läuft trotz der Manipulation vollständig durch."""
        log = self.log(project)
        self.assertEqual(0, result.returncode,
                         result.stdout + result.stderr + "\n" + log)
        self.assertIn("FERTIG", log)
        self.assertEqual([], self.blocked_lines(log), log)
        self.assertIn("Geschlossen: F1", self.report(project))


class TamperedProjectEnvTest(HashGuardFixture):
    """T-V21: veränderte ``.vibe/project.env`` blockiert das Paket."""

    def test_tampered_project_env_blocks_and_names_the_file(self):
        """Vorbedingung: Projekt mit transportierter ``.vibe/project.env``;
        der Agent schließt das Paket ab, verändert dabei aber die
        transportierte Projektdatei (``FAKE_TAMPER=append:project.env``).
        Aktion: Läufer einmal ausführen.
        Erwartung: Exit ungleich 0; eine BLOCKIERT-Zeile nennt
        ``.vibe/project.env``; keine Reparaturrunde (genau ein
        Agentenaufruf), kein FERTIG, kein lokaler Merge, Ticket bleibt offen.
        Fehlerfall: Die veränderte Konfiguration wird stillschweigend
        weiterbenutzt (Manipulation der autoritativen Projektwerte).
        """
        project = self.make_guard_project()

        result = self.run_runner(
            project, FAKE_TAMPER="append:project.env"
        )

        self.assertNotEqual(0, result.returncode,
                            result.stdout + result.stderr)
        log = self.log(project)
        self.assert_blocked_for(log, ".vibe/project.env")
        self.assertNotEqual(
            0, git(project, "cat-file", "-e", "HEAD:impl-F1.txt").returncode,
            "Ein blockiertes Paket darf nicht lokal gemergt sein:\n" + log,
        )
        self.assertNotEqual("done", self.ticket(project)["state"],
                            "Ein blockiertes Paket muss offen bleiben")

    def test_identical_rewrite_is_not_a_block(self):
        """Vorbedingung: Der Agent schreibt ``.vibe/project.env`` mit
        identischem Inhalt neu (``FAKE_TAMPER=rewrite:project.env``).
        Aktion: Läufer einmal ausführen.
        Erwartung: Exit 0 und FERTIG — der Wächter vergleicht den Inhalt
        (sha256), nicht die Änderungszeit.
        Fehlerfall: Ein reines Neuschreiben blockiert ein gesundes Paket
        (Fehlalarm, der jede Agentenrunde blockieren würde).
        """
        project = self.make_guard_project()

        result = self.run_runner(
            project, FAKE_TAMPER="rewrite:project.env"
        )

        log = self.log(project)
        self.assertEqual(0, result.returncode,
                         result.stdout + result.stderr + "\n" + log)
        self.assertIn("FERTIG", log)
        self.assertEqual([], self.blocked_lines(log), log)


class UntouchedFilesTest(HashGuardFixture):
    """T-V21: unveränderte Dateien blockieren nicht."""

    def test_untouched_project_and_baseline_do_not_block(self):
        """Vorbedingung: Projekt mit ``.vibe/project.env`` und einer lokalen
        ``.vibe/verify-baseline``; der Agent verändert keine der Dateien.
        Aktion: Läufer einmal ausführen.
        Erwartung: Exit 0, ``Geschlossen: F1`` im Bericht, kein
        BLOCKIERT-Vermerk — der Wächter greift nur bei Abweichung einer
        transportierten Datei.
        Fehlerfall: Der Wächter blockiert jedes Paket.
        """
        project = self.make_guard_project(baseline=True)

        result = self.run_runner(project)

        log = self.log(project)
        self.assertEqual(0, result.returncode,
                         result.stdout + result.stderr + "\n" + log)
        self.assertEqual([], self.blocked_lines(log), log)
        report = self.report(project)
        self.assertIn("Geschlossen: F1", report)


class DeletedTransportedFileTest(HashGuardFixture):
    """T-V21: Löschen einer beim Start vorhandenen transportierten Datei.

    Der Wächter erfasst den Inhalt beim Paketstart. Fehlt die Datei nach dem
    Agentenlauf, ist das nicht „unverändert", sondern eine Manipulation: Der
    Agent könnte damit unliebsame Projektwerte beseitigen. Die Prüfung darf
    sich deshalb nicht auf ``[ -f datei ]`` verlassen, sondern muss bereits
    das Fehlen als Abweichung vom erfassten Startzustand werten. Das gilt
    ausschließlich für die transportierte ``.vibe/project.env``.
    """

    def test_deleted_project_env_blocks_and_names_the_file(self):
        """Vorbedingung: Projekt mit transportierter ``.vibe/project.env``;
        der Agent löscht die Datei im Lauf
        (``FAKE_TAMPER=delete:project.env``).
        Aktion: Läufer einmal ausführen.
        Erwartung: Exit ungleich 0; eine BLOCKIERT-Zeile nennt
        ``.vibe/project.env``; keine Reparaturrunde, kein Merge, Ticket
        offen.
        Fehlerfall: Die autoritative Projektkonfiguration kann unbemerkt aus
        der Arbeitskopie verschwinden; die Paketprüfung liefe dann ohne die
        vom Projekt vorgegebenen Befehle.
        """
        project = self.make_guard_project()

        result = self.run_runner(
            project, FAKE_TAMPER="delete:project.env"
        )

        self.assertNotEqual(0, result.returncode,
                            result.stdout + result.stderr)
        log = self.log(project)
        self.assert_blocked_for(log, ".vibe/project.env")
        self.assertNotEqual(
            0, git(project, "cat-file", "-e", "HEAD:impl-F1.txt").returncode,
            "Ein blockiertes Paket darf nicht lokal gemergt sein:\n" + log,
        )


class UnwatchedVerifyBaselineTest(HashGuardFixture):
    """GH-46: ``.vibe/verify-baseline`` wird nicht transportiert/bewacht.

    Eine lokale Bootstrap-Baseline ist kein Paketinhalt mehr. Ob der Agent
    eine solche Datei anlegt, verändert oder löscht, darf das Paket nicht
    blockieren; maßgeblich ist allein die committete
    ``tests/verify-baseline.json`` im Branch.
    """

    def test_changed_verify_baseline_present_at_start_does_not_block(self):
        """Vorbedingung: Projekt mit ``.vibe/verify-baseline`` (beim
        Paketstart vorhanden); der Agent verändert sie im Lauf
        (``FAKE_TAMPER=append:verify-baseline``).
        Aktion: Läufer einmal ausführen.
        Erwartung: Exit 0, FERTIG, kein BLOCKIERT — für die nicht
        transportierte Baseline gibt es keinen Wächter.
        Fehlerfall: Der Läufer blockiert wegen einer Datei, die gar nicht Teil
        des Pakets ist, und verhindert so jedes Paket in einem Projekt mit
        lokaler Baseline.
        """
        project = self.make_guard_project(baseline=True)

        result = self.run_runner(
            project, FAKE_TAMPER="append:verify-baseline"
        )

        self.assert_not_blocked(result, project)

    def test_deleted_verify_baseline_present_at_start_does_not_block(self):
        """Vorbedingung: Projekt mit ``.vibe/verify-baseline`` (beim
        Paketstart vorhanden); der Agent löscht sie im Lauf
        (``FAKE_TAMPER=delete:verify-baseline``).
        Aktion: Läufer einmal ausführen.
        Erwartung: Exit 0, FERTIG, kein BLOCKIERT — das Löschen einer nicht
        transportierten Datei ist keine Manipulation am Paket.
        Fehlerfall: Ein veralteter Baseline-Wächter blockiert das Paket,
        obwohl die Baseline nur lokal im Projektordner lag.
        """
        project = self.make_guard_project(baseline=True)

        result = self.run_runner(
            project, FAKE_TAMPER="delete:verify-baseline"
        )

        self.assert_not_blocked(result, project)

    def test_baseline_created_by_the_agent_does_not_block(self):
        """Vorbedingung: Projekt ohne ``.vibe/verify-baseline``; der Agent
        legt die Datei im Lauf selbst an (``FAKE_TAMPER=create:…``).
        Aktion: Läufer einmal ausführen.
        Erwartung: Exit 0, FERTIG — eine im Lauf erzeugte Baseline ist kein
        Abweichungsgrund.
        Fehlerfall: Der Wächter verlangt oder verbietet Dateien, die nicht
        transportiert wurden, und blockiert gesunde Pakete.
        """
        project = self.make_guard_project(baseline=False)

        result = self.run_runner(
            project, FAKE_TAMPER="create:verify-baseline"
        )

        self.assert_not_blocked(result, project)

    def test_deleting_an_absent_baseline_does_not_block(self):
        """Vorbedingung: Projekt ohne ``.vibe/verify-baseline``; der Agent
        „löscht" die nie transportierte Datei
        (``FAKE_TAMPER=delete:verify-baseline``, folgenlos wie ``rm -f``).
        Aktion: Läufer einmal ausführen.
        Erwartung: Exit 0, FERTIG, kein BLOCKIERT — es gibt keinen
        Baseline-Wächter mehr.
        Fehlerfall: Ein Lauf ohne transportierte Baseline blockiert, weil der
        Wächter eine Startdatei unterstellt, die es nie gab.
        """
        project = self.make_guard_project(baseline=False)

        result = self.run_runner(
            project, FAKE_TAMPER="delete:verify-baseline"
        )

        self.assert_not_blocked(result, project)


if __name__ == "__main__":
    unittest.main()
