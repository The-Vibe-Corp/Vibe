"""Tests für den Umgang mit den Arbeitsnotizen FEEDBACK.md und TICKETS.md.

Die Notizen sind Laufzeit- und Werknotizen: Eine manuelle Änderung an ihnen
darf Preflight und Abschlussschranke nicht blockieren. Ein per ``git worktree``
angelegte Arbeitskopie enthält sie nicht; zwei neue CLI-Befehle kopieren sie
hinein und schreiben den Ticket-Nachweis in den Projektordner zurück.

Die Tests arbeiten mit echten temporären Git-Repositories und echten
Arbeitskopien (``tests/unit/runner_support.py``). Es werden keine
Modellaufrufe, keine Netzverbindungen und keine Router-/MCP-Aufrufe verwendet.
"""
import importlib.machinery
import importlib.util
import os
import subprocess
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
        "vibe_packages_worknotes_under_test", str(MODULE)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class WorkNotesTestCase(unittest.TestCase):
    """Gemeinsames echtes Repository mit versionierten Arbeitsnotizen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        support.init_repo(self.project)
        self.agents = self.root / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        support.write_project(self.project, ENV_TEXT)
        support.commit_all(self.project)
        self.module = load_module()
        self.worktrees = []
        self.base = support.git(
            self.project, "rev-parse", "HEAD"
        ).stdout.strip()

    def tearDown(self):
        for worktree in self.worktrees:
            support.git(
                self.project, "worktree", "remove", "--force", str(worktree)
            )
        self.tmp.cleanup()

    def git_ok(self, cwd, *args):
        result = support.git(cwd, *args)
        self.assertEqual(
            result.returncode, 0, result.stdout + result.stderr
        )
        return result

    def add_worktree(self, name="wt"):
        """Legt eine echte Arbeitskopie vom aktuellen Projekt-HEAD an."""
        self.base = support.git(
            self.project, "rev-parse", "HEAD"
        ).stdout.strip()
        worktree = self.root / name
        self.git_ok(
            self.project,
            "worktree",
            "add",
            "-q",
            "-b",
            "branch-" + name,
            str(worktree),
            "HEAD",
        )
        self.worktrees.append(worktree)
        return worktree

    def make_notes_untracked(self):
        """Nimmt die versionierten Notizen aus Git, lässt sie aber liegen."""
        self.git_ok(
            self.project, "rm", "--cached", "-q", "FEEDBACK.md", "TICKETS.md"
        )
        self.git_ok(
            self.project,
            "commit",
            "-q",
            "-m",
            "Notizen aus der Versionierung nehmen",
        )

    def write_project_feedback(self, text):
        (self.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n" + text, encoding="utf-8"
        )

    def write_worktree_feedback(self, worktree, text):
        (worktree / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n" + text, encoding="utf-8"
        )

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(MODULE), *args],
            cwd=str(self.root),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def sync_proof(self, worktree, pid):
        return self.run_cli(
            "sync-proof",
            "--project",
            str(self.project),
            "--worktree",
            str(worktree),
            "--id",
            pid,
        )

    def copy_notes(self, worktree):
        return self.run_cli(
            "copy-notes",
            "--project",
            str(self.project),
            "--worktree",
            str(worktree),
        )


class PreflightWorkNotesTest(WorkNotesTestCase):
    """A1: geänderte oder unversionierte Notizen blockieren den Preflight nicht."""

    def errors(self):
        return self.module.preflight_errors(
            str(self.project),
            agents_dir=str(self.agents),
            tester="test-agent",
            reviewer="code-reviewer",
        )

    def test_modified_versioned_work_notes_do_not_block_the_preflight(self):
        self.write_project_feedback("- [ ] F9 Manuell ergänzt\n")
        (self.project / "TICKETS.md").write_text(
            "# TICKETS\n\n- [ ] T9 Manuell ergänzt\n", encoding="utf-8"
        )

        self.assertEqual(self.errors(), [])

    def test_modified_other_versioned_file_still_blocks_the_preflight(self):
        other = self.project / "notiz.txt"
        other.write_text("alt\n", encoding="utf-8")
        support.commit_all(self.project, "weitere versionierte Datei")
        other.write_text("neu\n", encoding="utf-8")
        self.write_project_feedback("- [ ] F9 Manuell ergänzt\n")
        (self.project / "TICKETS.md").write_text(
            "# TICKETS\n\n- [ ] T9 Manuell ergänzt\n", encoding="utf-8"
        )

        errors = self.errors()

        text = "\n".join(errors)
        self.assertTrue(any("Arbeitsbaum" in error for error in errors), errors)
        self.assertIn("notiz.txt", text)
        self.assertNotIn("FEEDBACK.md", text)
        self.assertNotIn("TICKETS.md", text)

    def test_untracked_work_notes_do_not_block_the_preflight(self):
        self.make_notes_untracked()
        self.write_project_feedback("- [ ] F9 Manuell ergänzt\n")
        (self.project / "TICKETS.md").write_text(
            "# TICKETS\n\n- [ ] T9 Manuell ergänzt\n", encoding="utf-8"
        )

        self.assertEqual(self.errors(), [])

    def test_untracked_other_file_still_blocks_the_preflight(self):
        self.make_notes_untracked()
        self.write_project_feedback("- [ ] F9 Manuell ergänzt\n")
        (self.project / "TICKETS.md").write_text(
            "# TICKETS\n\n- [ ] T9 Manuell ergänzt\n", encoding="utf-8"
        )
        (self.project / "unfertig.txt").write_text("x\n", encoding="utf-8")

        errors = self.errors()

        text = "\n".join(errors)
        self.assertTrue(any("Arbeitsbaum" in error for error in errors), errors)
        self.assertIn("unfertig.txt", text)
        self.assertNotIn("FEEDBACK.md", text)
        self.assertNotIn("TICKETS.md", text)


class GateWorkNotesTest(WorkNotesTestCase):
    """A2: Notizänderungen in der Arbeitskopie verletzen die Sauberkeit nicht."""

    def gate_errors(self, worktree, pid="F1"):
        return self.module.gate_errors(str(worktree), pid, self.base)

    def commit_paths(self, worktree, paths, message):
        self.git_ok(worktree, "add", "--", *paths)
        self.git_ok(worktree, "commit", "-q", "-m", message)

    def prepare_package(self, worktree, pid="F1", notes_tracked=True):
        """Legt einen vollständigen Paketnachweis in der Arbeitskopie an.

        ``notes_tracked=False`` lässt FEEDBACK.md/TICKETS.md unversioniert und
        committet nur Umsetzung und Dokumentation.
        """
        (worktree / ("impl-" + pid + ".txt")).write_text(
            pid + "\n", encoding="utf-8"
        )
        if notes_tracked:
            self.git_ok(worktree, "add", "-A")
        else:
            self.git_ok(worktree, "add", "--", "impl-" + pid + ".txt")
        self.git_ok(worktree, "commit", "-q", "-m", pid + ": Umsetzung")
        revision = support.git(
            worktree, "rev-parse", "--short", "HEAD"
        ).stdout.strip()

        self.write_worktree_feedback(
            worktree,
            "- [x] " + pid + " Testpaket\n"
            "  Beschreibung: Agentenstand.\n"
            "  Commit: " + revision + "\n"
            "  Test: test_" + pid.lower().replace("-", "_") + "\n",
        )
        features = worktree / "docs" / "features"
        features.mkdir(parents=True, exist_ok=True)
        (features / (pid + ".md")).write_text(
            "# " + pid + "\n\nTestdokumentation.\n", encoding="utf-8"
        )
        reviews = worktree / "docs" / "reviews"
        reviews.mkdir(parents=True, exist_ok=True)
        (reviews / (pid + "-review-1.md")).write_text(
            "# Review\n\nVerdict: PASS\n", encoding="utf-8"
        )
        if notes_tracked:
            self.git_ok(worktree, "add", "-A")
        else:
            self.git_ok(worktree, "add", "--", "docs")
        self.git_ok(worktree, "commit", "-q", "-m", pid + ": Nachweis")
        return revision

    def test_modified_tracked_notes_do_not_dirty_the_workcopy(self):
        worktree = self.add_worktree()
        self.prepare_package(worktree, notes_tracked=True)

        (worktree / "FEEDBACK.md").write_text(
            (worktree / "FEEDBACK.md").read_text(encoding="utf-8")
            + "  Manuelle Notiz zum Paket\n",
            encoding="utf-8",
        )
        (worktree / "TICKETS.md").write_text(
            "# TICKETS\n\n- [ ] T9 Manuell ergänzt\n", encoding="utf-8"
        )

        self.assertEqual(self.gate_errors(worktree), [])

    def test_modified_other_file_still_dirties_the_workcopy(self):
        worktree = self.add_worktree()
        self.prepare_package(worktree, notes_tracked=True)
        (worktree / "FEEDBACK.md").write_text(
            (worktree / "FEEDBACK.md").read_text(encoding="utf-8")
            + "  Manuelle Notiz zum Paket\n",
            encoding="utf-8",
        )
        (worktree / "TICKETS.md").write_text(
            "# TICKETS\n\n- [ ] T9 Manuell ergänzt\n", encoding="utf-8"
        )
        (worktree / "impl-F1.txt").write_text("geändert\n", encoding="utf-8")

        errors = self.gate_errors(worktree)

        text = "\n".join(errors)
        self.assertTrue(any("sauber" in error for error in errors), errors)
        self.assertIn("impl-F1.txt", text)
        self.assertNotIn("FEEDBACK.md", text)
        self.assertNotIn("TICKETS.md", text)

    def test_untracked_notes_do_not_dirty_the_workcopy(self):
        self.make_notes_untracked()
        worktree = self.add_worktree()
        self.assertFalse((worktree / "FEEDBACK.md").exists())
        self.prepare_package(worktree, notes_tracked=False)

        self.write_worktree_feedback(
            worktree,
            "- [x] F1 Testpaket\n"
            "  Beschreibung: Agentenstand.\n"
            "  Commit: "
            + support.git(
                worktree, "rev-parse", "--short", "HEAD"
            ).stdout.strip()
            + "\n"
            "  Test: test_f1\n",
        )
        (worktree / "TICKETS.md").write_text(
            "# TICKETS\n\n- [ ] T9 Manuell ergänzt\n", encoding="utf-8"
        )

        self.assertEqual(self.gate_errors(worktree), [])

    def test_untracked_other_file_still_dirties_the_workcopy(self):
        self.make_notes_untracked()
        worktree = self.add_worktree()
        self.prepare_package(worktree, notes_tracked=False)
        revision = support.git(
            worktree, "rev-parse", "--short", "HEAD"
        ).stdout.strip()
        self.write_worktree_feedback(
            worktree,
            "- [x] F1 Testpaket\n"
            "  Beschreibung: Agentenstand.\n"
            "  Commit: " + revision + "\n"
            "  Test: test_f1\n",
        )
        (worktree / "TICKETS.md").write_text(
            "# TICKETS\n\n- [ ] T9 Manuell ergänzt\n", encoding="utf-8"
        )
        (worktree / "offen.txt").write_text("x\n", encoding="utf-8")

        errors = self.gate_errors(worktree)

        text = "\n".join(errors)
        self.assertTrue(any("sauber" in error for error in errors), errors)
        self.assertIn("offen.txt", text)
        self.assertNotIn("FEEDBACK.md", text)
        self.assertNotIn("TICKETS.md", text)


class CopyNotesCommandTest(WorkNotesTestCase):
    """A3: copy-notes überträgt vorhandene Notizen in die Arbeitskopie."""

    def setUp(self):
        super().setUp()
        self.make_notes_untracked()
        self.write_project_feedback("- [ ] F7 Aus dem Projekt\n")
        (self.project / "TICKETS.md").write_text(
            "# TICKETS\n\n- [ ] T7 Aus dem Projekt\n", encoding="utf-8"
        )
        self.worktree = self.add_worktree()
        self.assertFalse((self.worktree / "FEEDBACK.md").exists())
        self.assertFalse((self.worktree / "TICKETS.md").exists())

    def test_both_existing_notes_are_copied_unchanged(self):
        result = self.copy_notes(self.worktree)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            (self.worktree / "FEEDBACK.md").read_text(encoding="utf-8"),
            (self.project / "FEEDBACK.md").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            (self.worktree / "TICKETS.md").read_text(encoding="utf-8"),
            (self.project / "TICKETS.md").read_text(encoding="utf-8"),
        )

    def test_a_note_missing_in_the_project_is_not_created(self):
        (self.project / "TICKETS.md").unlink()

        result = self.copy_notes(self.worktree)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.worktree / "TICKETS.md").exists())
        self.assertEqual(
            (self.worktree / "FEEDBACK.md").read_text(encoding="utf-8"),
            (self.project / "FEEDBACK.md").read_text(encoding="utf-8"),
        )


class SyncProofCommandTest(WorkNotesTestCase):
    """A4/A5: sync-proof schreibt den Nachweis gezielt und verweigert Unfertiges."""

    def setUp(self):
        super().setUp()
        self.make_notes_untracked()
        self.write_project_feedback(
            "- [ ] F1 Erstes Paket\n"
            "  Beschreibung: Manuell im Projekt gepflegt.\n"
            "  Notiz: Diese Zeile gehört dem Nutzer.\n"
            "  Commit: 0000000\n"
            "  Test: test_alt\n"
            "\n"
            "- [ ] F2 Zweites Paket\n"
            "  Beschreibung: Nicht anfassen.\n"
            "\n"
            "Nachbemerkung: bleibt stehen.\n"
        )
        (self.project / "TICKETS.md").write_text(
            "# TICKETS\n\n- [ ] T7 Unverändert\n", encoding="utf-8"
        )
        self.worktree = self.add_worktree()
        (self.worktree / "impl-F1.txt").write_text("F1\n", encoding="utf-8")
        self.git_ok(self.worktree, "add", "--", "impl-F1.txt")
        self.git_ok(self.worktree, "commit", "-q", "-m", "F1: Umsetzung")
        self.revision = support.git(
            self.worktree, "rev-parse", "--short", "HEAD"
        ).stdout.strip()
        self.proof_lines = (
            "  Commit: " + self.revision + "\n"
            "  Test: test_f1_sync\n"
            "  Review: docs/reviews/F1-review-1.md (PASS)\n"
            "  Doku: docs/features/F1.md\n"
        )
        self.write_worktree_feedback(
            self.worktree,
            "- [x] F1 Erstes Paket\n"
            "  Beschreibung: Stand des Agenten.\n"
            + self.proof_lines
            + "\n"
            "- [x] F2 Zweites Paket\n"
            "  Beschreibung: Anderer Stand.\n"
            "  Commit: " + self.revision + "\n"
            "  Test: test_f2\n",
        )
        (self.worktree / "TICKETS.md").write_text(
            "# TICKETS\n\n- [ ] T7 Unverändert\n", encoding="utf-8"
        )

    def project_feedback(self):
        return (self.project / "FEEDBACK.md").read_text(encoding="utf-8")

    def project_tickets(self):
        return (self.project / "TICKETS.md").read_text(encoding="utf-8")

    def assert_command_is_available(self):
        """Stellt sicher, dass der Befehl existiert und nicht an argparse scheitert."""
        result = self.run_cli("sync-proof", "--help")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_checkbox_and_proof_lines_reach_the_project_block(self):
        result = self.sync_proof(self.worktree, "F1")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        text = self.project_feedback()
        self.assertIn("- [x] F1 Erstes Paket", text)
        for line in self.proof_lines.splitlines():
            self.assertIn(line, text)

    def test_other_blocks_and_manual_changes_stay_untouched(self):
        before_tickets = self.project_tickets()
        result = self.sync_proof(self.worktree, "F1")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        text = self.project_feedback()
        self.assertIn(
            "- [ ] F2 Zweites Paket\n  Beschreibung: Nicht anfassen.", text
        )
        self.assertIn("  Notiz: Diese Zeile gehört dem Nutzer.", text)
        self.assertIn("Nachbemerkung: bleibt stehen.", text)
        self.assertNotIn("Stand des Agenten.", text)
        self.assertNotIn("0000000", text)
        self.assertNotIn("test_alt", text)
        self.assertEqual(self.project_tickets(), before_tickets)

    def test_the_command_is_idempotent(self):
        first = self.sync_proof(self.worktree, "F1")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        after_first = self.project_feedback()
        tickets_after_first = self.project_tickets()

        second = self.sync_proof(self.worktree, "F1")

        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(self.project_feedback(), after_first)
        self.assertEqual(self.project_tickets(), tickets_after_first)

    def test_an_unchecked_block_in_the_workcopy_is_refused(self):
        self.assert_command_is_available()
        self.write_worktree_feedback(
            self.worktree,
            "- [ ] F1 Erstes Paket\n"
            "  Beschreibung: Noch nicht abgehakt.\n" + self.proof_lines,
        )
        before = self.project_feedback()

        result = self.sync_proof(self.worktree, "F1")

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.project_feedback(), before)

    def test_an_incomplete_proof_is_refused(self):
        self.assert_command_is_available()
        self.write_worktree_feedback(
            self.worktree,
            "- [x] F1 Erstes Paket\n"
            "  Beschreibung: Nachweis fehlt vollständig.\n",
        )
        before = self.project_feedback()

        result = self.sync_proof(self.worktree, "F1")

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.project_feedback(), before)

    def test_a_missing_block_aborts_without_changing_the_project(self):
        self.assert_command_is_available()
        self.write_worktree_feedback(
            self.worktree,
            "- [x] F2 Zweites Paket\n"
            "  Beschreibung: Anderer Block.\n"
            "  Commit: " + self.revision + "\n"
            "  Test: test_f2\n",
        )
        before = self.project_feedback()

        result = self.sync_proof(self.worktree, "F1")

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.project_feedback(), before)

    def test_a_block_missing_in_the_project_is_refused(self):
        self.assert_command_is_available()
        self.write_project_feedback(
            "- [ ] F2 Zweites Paket\n"
            "  Beschreibung: Nur dieser Block ist im Projekt.\n"
        )
        before = self.project_feedback()

        result = self.sync_proof(self.worktree, "F1")

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.project_feedback(), before)

    def test_a_proof_commit_unknown_to_the_project_is_refused(self):
        self.assert_command_is_available()
        self.write_worktree_feedback(
            self.worktree,
            "- [x] F1 Erstes Paket\n"
            "  Beschreibung: Stand des Agenten.\n"
            "  Commit: deadbee\n"
            "  Test: test_f1_sync\n"
            "  Review: docs/reviews/F1-review-1.md (PASS)\n"
            "  Doku: docs/features/F1.md\n",
        )
        before = self.project_feedback()

        result = self.sync_proof(self.worktree, "F1")

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.project_feedback(), before)


class RunnerWorkNotesTest(WorkNotesTestCase):
    """A7: Der Läufer verdrahtet copy-notes und sync-proof im echten Ablauf.

    Das Projekt führt FEEDBACK.md/TICKETS.md bewusst unversioniert. Der
    nachgebildete Agent arbeitet in einer echten ``git worktree``-Arbeitskopie.
    Nach dem Lauf müssen Arbeitskopie und Paketbranch weg, der Code gemergt und
    der Paketnachweis in den Projektnotizen angekommen sein.
    """

    def setUp(self):
        super().setUp()
        env_path = self.project / ".vibe" / "project.env"
        env_path.write_text(ENV_TEXT + "MAX_RETRIES=1\n", encoding="utf-8")
        support.commit_all(self.project, "Wiederholungslimit festlegen")
        self.write_project_feedback(
            "- [ ] F1 Erstes Paket\n  Beschreibung: Test\n"
        )
        (self.project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
        self.make_notes_untracked()
        self.base = support.git(
            self.project, "rev-parse", "HEAD"
        ).stdout.strip()

        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        (self.tool_bin / "vibe").write_text(support.FAKE_VIBE, encoding="utf-8")
        (self.tool_bin / "vibe").chmod(0o755)
        self.runtime = self.root / "_logs"
        self.fakebin = support.install_fake_tools(self.root)
        self.calls = self.root / "calls.log"
        self.counter = self.root / "counter"
        self.home = self.root / "home"
        self.home.mkdir(parents=True, exist_ok=True)

    def env(self):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_"):
                env.pop(key, None)
        for key in (
            "AGENT",
            "MAX_PACKAGES",
            "MAX_RETRIES",
            "SANDBOX",
            "SANDBOX_TOOLS",
            "VERIFY_FULL",
            "VERIFY_PACKAGE",
        ):
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(self.root),
                "VIBE_INSTALL": str(self.install),
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_AGENTS_DIR": str(self.agents),
                "VIBE_LOGNAME": "proj",
                "VIBE_MAX_PACKAGES": "1",
                "VIBE_RETRY_DELAY": "0",
                "HOME": str(self.home),
                "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
                "FAKE_CALLS": str(self.calls),
                "FAKE_COUNTER": str(self.counter),
            }
        )
        return env

    def run_runner(self):
        return subprocess.run(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(self.project)],
            cwd=str(self.project),
            env=self.env(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def worktree_dirs(self):
        path = self.runtime / "worktrees"
        if not path.is_dir():
            return []
        return [entry for entry in path.glob("*") if entry.is_dir()]

    def test_runner_copies_notes_and_writes_the_proof_back(self):
        result = self.run_runner()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Geschlossen: F1", result.stdout)

        text = (self.project / "FEEDBACK.md").read_text(encoding="utf-8")
        self.assertIn("- [x] F1 Erstes Paket", text)
        self.assertIn("Commit:", text)
        self.assertIn("Test: test_f1", text)

        self.assertTrue(
            (self.project / "impl-F1.txt").is_file(), "Umsetzung nicht gemergt"
        )
        self.assertTrue(
            (self.project / "docs" / "features" / "F1.md").is_file(),
            "Feature-Dokumentation nicht gemergt",
        )
        merged = support.git(
            self.project, "log", "--format=%s", self.base + "..HEAD"
        ).stdout
        self.assertIn("F1: Nachweis", merged)

        self.assertEqual(self.worktree_dirs(), [], "Arbeitskopie blieb liegen")
        self.assertEqual(
            support.git(self.project, "branch", "--list", "vibe/*").stdout.strip(),
            "",
            "Paketbranch wurde nicht entfernt",
        )
        self.assertEqual(
            support.git(
                self.project, "ls-files", "FEEDBACK.md", "TICKETS.md"
            ).stdout.strip(),
            "",
            "Arbeitsnotizen dürfen nicht versioniert werden",
        )


if __name__ == "__main__":
    unittest.main()
