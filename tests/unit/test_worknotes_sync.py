"""GH-48: Arbeitsnotizen, Tickettransport und Abschluss-Sync des Läufers.

Neu abgeleitet aus Arbeitspaket GH-48, ``SPEC.md`` (Git & work-package
closing) und dem verbindlichen Implementierungsvertrag GH-48 (§4). Die alten
Markdown-Ledger TICKETS.md/FEEDBACK.md sind keine Arbeitsnotizen mehr:

* ``AGENTS.md`` und die sichtbare Stammdatei ``TICKET-<ID>.json`` dürfen
  Preflight und Abschlussschranke nicht blockieren; andere Änderungen schon.
* ``copy-notes`` transportiert AGENTS.md und ``.vibe/project.env``; mit
  ``--id`` zusätzlich genau das aktuelle Ticket.
* ``sync-ticket`` übernimmt state/commit/test aus der Arbeitskopie in den
  Projekt-Ticketspeicher und verweigert Unfertiges mit ``FEHLT:``/Exit 1.

Echte temporäre Git-Repositories und Arbeitskopien
(``tests/unit/runner_support.py``); keine Modellaufrufe, keine Netzverbindungen,
keine produktiven Pfade.

Run:

    python3 -m unittest tests.unit.test_worknotes_sync -v
"""
import importlib.machinery
import importlib.util
import json
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
STAMP = "2026-01-01T00:00:00+00:00"

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
        "vibe_packages_worknotes_under_test", str(MODULE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def ticket(tid, title, type="task", state="open", **extra):
    record = {
        "id": tid, "title": title, "type": type, "state": state,
        "description": "", "github": None, "pr_url": "", "commit": "",
        "test": "", "blocked_reason": "", "waiting_note": "",
        "priority": "", "dependencies": [],
        "created": STAMP, "updated": STAMP,
    }
    record.update(extra)
    return record


class WorkNotesTestCase(unittest.TestCase):
    """Gemeinsames echtes Repository mit versionierter AGENTS.md."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        support.init_repo(self.project)
        self.agents = self.root / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        (self.project / ".vibe").mkdir(parents=True, exist_ok=True)
        (self.project / ".vibe" / "project.env").write_text(
            ENV_TEXT, encoding="utf-8")
        (self.project / "AGENTS.md").write_text("# Regeln\n", encoding="utf-8")
        support.commit_all(self.project)
        self.module = load_module()
        self.worktrees = []
        self.base = self.head(self.project)

    def tearDown(self):
        for worktree in self.worktrees:
            support.git(self.project, "worktree", "remove", "--force",
                        str(worktree))

    def head(self, cwd):
        return support.git(cwd, "rev-parse", "HEAD").stdout.strip()

    def git_ok(self, cwd, *args):
        result = support.git(cwd, *args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def add_worktree(self, name="wt"):
        self.base = self.head(self.project)
        worktree = self.root / name
        self.git_ok(self.project, "worktree", "add", "-q", "-b",
                    "branch-" + name, str(worktree), "HEAD")
        self.worktrees.append(worktree)
        return worktree

    def make_agents_untracked(self):
        self.git_ok(self.project, "rm", "--cached", "-q", "AGENTS.md")
        self.git_ok(self.project, "commit", "-q", "-m",
                    "AGENTS.md aus der Versionierung nehmen")

    def store(self, *records):
        return support.write_ticket_store(self.project, list(records))

    def read_store(self):
        path = self.project / ".vibe" / "tickets.json"
        return {item["id"]: item for item in json.loads(
            path.read_text(encoding="utf-8"))["tickets"]}

    def write_ticket_file(self, worktree, record):
        path = worktree / ("TICKET-" + record["id"] + ".json")
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
        return path

    def run_cli(self, *args):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("VIBE")}
        env.update({
            "HOME": str(self.root / "home"),
            "VIBE": str(self.root),
            "VIBE_STORAGE_LOCK_DIR": str(self.root / "locks"),
            "VIBE_NO_CONTAINER": "1",
        })
        (self.root / "home").mkdir(exist_ok=True)
        return subprocess.run(
            [sys.executable, str(MODULE), *args],
            cwd=str(self.root), env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=120)

    def copy_notes(self, worktree, *extra):
        return self.run_cli("copy-notes", "--project", str(self.project),
                            "--worktree", str(worktree), *extra)

    def sync_ticket(self, worktree, pid):
        return self.run_cli("sync-ticket", "--project", str(self.project),
                            "--worktree", str(worktree), "--id", pid)


class PreflightWorkNotesTest(WorkNotesTestCase):
    """Geänderte oder unversionierte Arbeitsnotizen blockieren nicht."""

    def errors(self):
        return self.module.preflight_errors(
            str(self.project), agents_dir=str(self.agents),
            tester="test-agent", reviewer="code-reviewer")

    def test_modified_agents_md_does_not_block_the_preflight(self):
        """Vor: versionierte AGENTS.md wird geändert. Aktion: Preflight.
        Erwartet: keine Befunde."""
        (self.project / "AGENTS.md").write_text("# Regeln\nNeu\n",
                                                encoding="utf-8")

        self.assertEqual([], self.errors())

    def test_untracked_agents_md_does_not_block_the_preflight(self):
        """Vor: AGENTS.md ist unversioniert vorhanden. Aktion: Preflight.
        Erwartet: keine Befunde."""
        self.make_agents_untracked()
        (self.project / "AGENTS.md").write_text("# Regeln\nNeu\n",
                                                encoding="utf-8")

        self.assertEqual([], self.errors())

    def test_untracked_ticket_file_does_not_block_the_preflight(self):
        """Vor: TICKET-AP1.json liegt unversioniert im Projektstamm. Aktion:
        Preflight. Erwartet: keine Befunde (Laufzeitstand)."""
        (self.project / "TICKET-AP1.json").write_text(
            json.dumps(ticket("AP1", "Titel")), encoding="utf-8")

        self.assertEqual([], self.errors())

    def test_other_modified_file_still_blocks_the_preflight(self):
        """Vor: versionierte Datei notiz.txt wird geändert. Aktion: Preflight.
        Erwartet: Befund nennt notiz.txt, nicht AGENTS.md."""
        other = self.project / "notiz.txt"
        other.write_text("alt\n", encoding="utf-8")
        support.commit_all(self.project, "weitere versionierte Datei")
        other.write_text("neu\n", encoding="utf-8")

        errors = self.errors()

        text = "\n".join(errors)
        self.assertTrue(any("Arbeitsbaum" in error for error in errors), errors)
        self.assertIn("notiz.txt", text)
        self.assertNotIn("AGENTS.md", text)

    def test_other_untracked_file_still_blocks_the_preflight(self):
        """Vor: unversionierte Datei unfertig.txt. Aktion: Preflight.
        Erwartet: Befund nennt unfertig.txt."""
        (self.project / "unfertig.txt").write_text("x\n", encoding="utf-8")

        errors = self.errors()

        self.assertTrue(any("Arbeitsbaum" in error for error in errors), errors)
        self.assertIn("unfertig.txt", "\n".join(errors))

    def test_ticket_file_in_a_subfolder_still_blocks_the_preflight(self):
        """Vor: TICKET-AP1.json in einem Unterordner. Aktion: Preflight.
        Erwartet: nur der Projektstamm ist Arbeitsnotiz; der Unterordner
        blockiert und wird genannt."""
        (self.project / "sub").mkdir()
        (self.project / "sub" / "TICKET-AP1.json").write_text("{}",
                                                               encoding="utf-8")

        errors = self.errors()

        self.assertTrue(any("Arbeitsbaum" in error for error in errors), errors)
        self.assertIn("sub/", "\n".join(errors))


class GateWorkNotesTest(WorkNotesTestCase):
    """Arbeitsnotizen verletzen die Sauberkeit der Arbeitskopie nicht."""

    def gate_errors(self, worktree, pid="AP7"):
        return self.module.gate_errors(str(worktree), pid, self.base)

    def prepare_package(self, worktree, pid="AP7"):
        (worktree / ("impl-" + pid + ".txt")).write_text(pid + "\n",
                                                         encoding="utf-8")
        (worktree / "docs" / "features").mkdir(parents=True, exist_ok=True)
        (worktree / "docs" / "features" / (pid + ".md")).write_text(
            "# " + pid + "\n", encoding="utf-8")
        (worktree / "docs" / "reviews").mkdir(parents=True, exist_ok=True)
        (worktree / "docs" / "reviews" / (pid + "-review-1.md")).write_text(
            "# Review\n\nVerdict: PASS\n", encoding="utf-8")
        self.git_ok(worktree, "add", "-A")
        self.git_ok(worktree, "commit", "-q", "-m", pid + ": Umsetzung")
        revision = self.head(worktree)
        self.write_ticket_file(worktree, ticket(
            pid, "Titel", state="done", commit=revision, test="test_ap7"))
        return revision

    def test_modified_agents_md_does_not_dirty_the_workcopy(self):
        """Vor: vollständiges Paket, danach AGENTS.md geändert. Aktion:
        gate_errors. Erwartet: keine Befunde."""
        worktree = self.add_worktree()
        self.prepare_package(worktree)
        (worktree / "AGENTS.md").write_text("# Regeln\nManuell\n",
                                            encoding="utf-8")

        self.assertEqual([], self.gate_errors(worktree))

    def test_ticket_files_do_not_dirty_the_workcopy(self):
        """Vor: vollständiges Paket mit TICKET-AP7.json und einer weiteren
        TICKET-Datei im Stamm. Aktion: gate_errors. Erwartet: keine Befunde
        (Laufzeitstand wird ignoriert)."""
        worktree = self.add_worktree()
        self.prepare_package(worktree)
        (worktree / "TICKET-X9.json").write_text("{}", encoding="utf-8")

        self.assertEqual([], self.gate_errors(worktree))

    def test_modified_other_file_still_dirties_the_workcopy(self):
        """Vor: vollständiges Paket, danach impl-Datei geändert. Aktion:
        gate_errors. Erwartet: Sauberkeitsbefund nennt impl-AP7.txt."""
        worktree = self.add_worktree()
        self.prepare_package(worktree)
        (worktree / "impl-AP7.txt").write_text("geändert\n", encoding="utf-8")

        errors = self.gate_errors(worktree)

        text = "\n".join(errors)
        self.assertTrue(any("sauber" in error for error in errors), errors)
        self.assertIn("impl-AP7.txt", text)
        self.assertNotIn("TICKET-AP7.json", text)


class CopyNotesCommandTest(WorkNotesTestCase):
    """copy-notes transportiert nur noch die aktuellen Arbeitsnotizen."""

    def test_agents_and_project_env_are_transported_without_ledgers(self):
        """Vor: Projekt mit AGENTS.md, altem TICKETS.md und project.env.
        Aktion: copy-notes ohne --id. Erwartet: AGENTS.md und project.env
        sind in der Arbeitskopie; TICKETS.md nicht."""
        (self.project / "TICKETS.md").write_text("# TICKETS\n",
                                                 encoding="utf-8")
        worktree = self.add_worktree()

        result = self.copy_notes(worktree)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(
            (self.project / "AGENTS.md").read_text(encoding="utf-8"),
            (worktree / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertTrue((worktree / ".vibe" / "project.env").is_file())
        self.assertFalse((worktree / "TICKETS.md").exists())

    def test_without_id_no_ticket_is_transported(self):
        """Vor: AP1 im Speicher, Arbeitskopie ohne TICKET-Datei. Aktion:
        copy-notes ohne --id. Erwartet: keine TICKET-Datei (Abwärts-
        kompatibilität des Aufrufs ohne Paket)."""
        self.store(ticket("AP1", "Titel"))
        worktree = self.add_worktree()

        result = self.copy_notes(worktree)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertFalse((worktree / "TICKET-AP1.json").exists())


class SyncTicketCommandTest(WorkNotesTestCase):
    """sync-ticket schreibt den Abschluss gezielt in den Speicher."""

    def test_a_complete_ticket_reaches_the_project_store(self):
        """Vor: AP1 offen im Speicher; Arbeitskopie TICKET-AP1.json done mit
        commit/test/pr_url. Aktion: sync-ticket. Erwartet: Exit 0 mit OK;
        Speicher übernimmt state/commit/test/pr_url."""
        self.store(ticket("AP1", "Titel"))
        worktree = self.add_worktree()
        (worktree / "impl-AP1.txt").write_text("x\n", encoding="utf-8")
        self.git_ok(worktree, "add", "-A")
        self.git_ok(worktree, "commit", "-q", "-m", "AP1: Umsetzung")
        revision = self.head(worktree)
        self.write_ticket_file(worktree, ticket(
            "AP1", "Titel", state="done", commit=revision, test="test_ap1",
            pr_url="http://example.invalid/pr/1"))

        result = self.sync_ticket(worktree, "AP1")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("OK:", result.stdout)
        record = self.read_store()["AP1"]
        self.assertEqual("done", record["state"])
        self.assertEqual(revision, record["commit"])
        self.assertEqual("test_ap1", record["test"])
        self.assertEqual("http://example.invalid/pr/1", record["pr_url"])

    def test_a_ticket_that_is_not_done_is_refused(self):
        """Vor: Arbeitskopie TICKET-AP1.json state=in-progress. Aktion:
        sync-ticket. Erwartet: Exit 1 mit FEHLT; Speicher unverändert."""
        self.store(ticket("AP1", "Titel"))
        before = self.read_store()
        worktree = self.add_worktree()
        self.write_ticket_file(worktree, ticket(
            "AP1", "Titel", state="in-progress"))

        result = self.sync_ticket(worktree, "AP1")

        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("FEHLT:", result.stdout)
        self.assertEqual(before, self.read_store())

    def test_a_missing_ticket_file_is_refused(self):
        """Vor: keine TICKET-Datei in der Arbeitskopie. Aktion: sync-ticket.
        Erwartet: Exit 1 mit FEHLT; Speicher unverändert."""
        self.store(ticket("AP1", "Titel"))
        before = self.read_store()
        worktree = self.add_worktree()

        result = self.sync_ticket(worktree, "AP1")

        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("FEHLT:", result.stdout)
        self.assertEqual(before, self.read_store())

    def test_an_unknown_proof_commit_is_refused(self):
        """Vor: Arbeitskopie nennt commit=deadbee, den das Projekt nicht
        kennt. Aktion: sync-ticket ohne Ausnahme-Flag. Erwartet: Exit 1 mit
        FEHLT; Speicher unverändert."""
        self.store(ticket("AP1", "Titel"))
        before = self.read_store()
        worktree = self.add_worktree()
        self.write_ticket_file(worktree, ticket(
            "AP1", "Titel", state="done", commit="deadbee",
            test="test_ap1"))

        result = self.sync_ticket(worktree, "AP1")

        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("FEHLT:", result.stdout)
        self.assertEqual(before, self.read_store())

    def test_a_ticket_missing_in_the_project_is_refused(self):
        """Vor: Arbeitskopie X9 done, Projekt-Speicher ohne X9. Aktion:
        sync-ticket. Erwartet: Exit 1 mit FEHLT; kein Ticket erfunden."""
        self.store(ticket("AP1", "Titel"))
        worktree = self.add_worktree()
        self.write_ticket_file(worktree, ticket(
            "X9", "Fremd", state="done", commit="abcdef1", test="test_x9"))

        result = self.sync_ticket(worktree, "X9")

        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("FEHLT:", result.stdout)
        self.assertNotIn("X9", self.read_store())


if __name__ == "__main__":
    unittest.main()
