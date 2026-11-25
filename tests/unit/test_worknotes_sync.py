"""Worknotes-Synchronisierung: Paketauswahl, Gates, Ticket-Sync und Arbeitskopie.

Aufruf: python3 -m unittest tests.unit.test_worknotes_sync -v
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


# ===========================================================================
# Vertragstests für den Läufer auf dem Ticketspeicher
# ===========================================================================

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support


_CACHE = {}


def load_runner_tickets_module():
    if "packages" not in _CACHE:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_packages_gh48_under_test", str(MODULE))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        _CACHE["packages"] = module
    return _CACHE["packages"]


def requires(module, name):
    """Liefert die Vertragsfunktion oder scheitert mit klarem GH-48-Befund."""
    function = getattr(module, name, None)
    if function is None:
        raise AssertionError(
            "vibe_packages." + name + " fehlt (Vertrag GH-48).")
    return function


class _IssueHandler(BaseHTTPRequestHandler):
    """Loopback-Fake für ``set_issue_state`` (GET Issue, PATCH Labels)."""

    def log_message(self, *args):
        return

    def _record(self, body=b""):
        self.server.requests.append({
            "method": self.command,
            "path": self.path,
            "body": json.loads(body.decode("utf-8")) if body else None,
        })

    def _respond(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _number(self):
        return int(urllib.parse.urlparse(self.path).path.rsplit("/", 1)[1])

    def do_GET(self):
        self._record()
        number = self._number()
        issue = self.server.issues.get(number)
        if issue is None:
            self._respond(404, {"message": "Not Found"})
            return
        self._respond(200, issue)

    def do_PATCH(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        self._record(raw)
        if self.server.fail_patch:
            self._respond(500, {"message": "simulierter GitHub-Fehler"})
            return
        number = self._number()
        issue = self.server.issues.get(number)
        if issue is None:
            self._respond(404, {"message": "Not Found"})
            return
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if "labels" in payload:
            issue["labels"] = [{"name": name}
                               for name in payload.get("labels") or []]
        self._respond(200, issue)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        self._record(raw)
        self._respond(201, {"number": 999, "title": "unerwartet"})


class RunnerCase(unittest.TestCase):
    """Echtes Git-Projekt; Ticketspeicher je Fall nach Bedarf."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        support.init_repo(self.project)
        self.agents = self.root / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        (self.project / ".vibe").mkdir(parents=True, exist_ok=True)
        self.env_path = self.project / ".vibe" / "project.env"
        self.env_path.write_text("TYPE=generic\n", encoding="utf-8")
        (self.project / "AGENTS.md").write_text("# Regeln\n", encoding="utf-8")
        support.commit_all(self.project)
        self.module = load_runner_tickets_module()
        self.base = self.head(self.project)
        self.worktrees = []

    def tearDown(self):
        for worktree in self.worktrees:
            support.git(self.project, "worktree", "remove", "--force",
                        str(worktree))

    # ------------------------------------------------------------- fixtures
    def head(self, cwd):
        return support.git(cwd, "rev-parse", "HEAD").stdout.strip()

    def git_ok(self, cwd, *args):
        result = support.git(cwd, *args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def add_worktree(self, name="wt"):
        worktree = self.root / name
        self.git_ok(self.project, "worktree", "add", "-q", "-b",
                    "feature/test/" + name, str(worktree), "HEAD")
        self.worktrees.append(worktree)
        return worktree

    def store(self, *records):
        return support.write_ticket_store(self.project, list(records))

    def read_store(self):
        path = self.project / ".vibe" / "tickets.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def records(self):
        return {item["id"]: item for item in self.read_store()["tickets"]}

    def write_ticket_file(self, worktree, record):
        path = worktree / ("TICKET-" + record["id"] + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
        return path

    def set_order(self, value):
        self.env_path.write_text("TYPE=generic\nPACKAGE_ORDER=\"%s\"\n" % value,
                                 encoding="utf-8")

    def select(self, **kwargs):
        kwargs.setdefault("state_path", str(self.root / "next-package.json"))
        return requires(self.module, "select_package")(self.project, **kwargs)

    def prepare_package(self, worktree, pid="AP7", state="done", commit=None,
                        test="test_ap7", docs=True, review="PASS"):
        """Vollständiger Paketstand in der Arbeitskopie."""
        (worktree / ("impl-" + pid + ".txt")).write_text(pid + "\n",
                                                         encoding="utf-8")
        if docs:
            (worktree / "docs" / "features").mkdir(parents=True, exist_ok=True)
            (worktree / "docs" / "features" / (pid + ".md")).write_text(
                "# " + pid + "\n", encoding="utf-8")
        if review is not None:
            (worktree / "docs" / "reviews").mkdir(parents=True, exist_ok=True)
            (worktree / "docs" / "reviews" / (pid + "-review-1.md")).write_text(
                "# Review\n\nVerdict: " + review + "\n", encoding="utf-8")
        self.git_ok(worktree, "add", "-A")
        self.git_ok(worktree, "commit", "-q", "-m", pid + ": Umsetzung")
        revision = self.head(worktree)
        record = ticket(pid, "Titel", state=state,
                        commit=revision if commit is None else commit,
                        test=test)
        self.write_ticket_file(worktree, record)
        return revision


class SelectPackageTest(RunnerCase):
    """Kandidaten, Ordnung, Abhängigkeiten und Reattach."""

    def test_open_and_in_progress_are_candidates_in_store_order(self):
        """Vor: AP1 offen, AP2 in-progress. Aktion: select_package.
        Erwartet: AP1 (Speicherposition), danach mit skip AP1 -> AP2;
        Zeilenform enthält id, type, title, description, priority, ordered,
        github."""
        self.store(ticket("AP1", "Offen"), ticket("AP2", "Läuft",
                                                 state="in-progress"))

        first = self.select()
        self.assertEqual("AP1", first["id"])
        for key in ("id", "type", "title", "description", "priority",
                    "ordered", "github"):
            self.assertIn(key, first)
        self.assertEqual("task", first["type"])
        self.assertEqual("Offen", first["title"])
        self.assertIs(False, first["ordered"])

        self.assertEqual("AP2", self.select(skip={"AP1"})["id"])

    def test_draft_blocked_waiting_and_done_are_never_selected(self):
        """Vor: nur draft/blocked/waiting-merge/done. Aktion: select_package.
        Erwartet: None — Entwürfe und Nachweise starten nicht."""
        self.store(
            ticket("AP1", "Entwurf", state="draft"),
            ticket("AP2", "Blockiert", state="blocked",
                   blocked_reason="Grund"),
            ticket("AP3", "Wartet", state="waiting-merge",
                   waiting_note="PR"),
            ticket("AP4", "Fertig", state="done", commit="abcdef1",
                   test="test_ap4"),
        )

        self.assertIsNone(self.select())

    def test_package_order_wins_over_priority_and_position(self):
        """Vor: PACKAGE_ORDER="AP2 AP1"; AP1 hat P0, AP2 P1.
        Aktion: select_package. Erwartet: AP2 zuerst mit ordered=True."""
        self.set_order("AP2 AP1")
        self.store(ticket("AP1", "Wichtig", priority="P0"),
                   ticket("AP2", "Zweit", priority="P1"))

        selected = self.select()

        self.assertEqual("AP2", selected["id"])
        self.assertIs(True, selected["ordered"])
        self.assertEqual("P1", selected["priority"])

    def test_standard_order_is_priority_then_store_position(self):
        """Vor: B1 (Bug) zuerst im Speicher, danach AP1 P1, AP2 P0, AP3 ohne
        Priorität. Aktion: select_package (mit skip).
        Erwartet: AP2 -> AP1 -> B1 -> AP3. Die alte Trennung TICKETS vor
        FEEDBACK entfällt; bei gleicher Priorität zählt nur die
        Speicherposition (kein Typ-Tiebreaker)."""
        self.store(ticket("B1", "Bug zuerst", type="bug"),
                   ticket("AP1", "Eins", priority="P1"),
                   ticket("AP2", "Zwei", priority="P0"),
                   ticket("AP3", "Drei"))

        order = []
        skip = set()
        while True:
            selected = self.select(skip=skip)
            if selected is None:
                break
            order.append(selected["id"])
            skip.add(selected["id"])

        self.assertEqual(["AP2", "AP1", "B1", "AP3"], order)

    def test_a_known_dependency_must_be_done(self):
        """Vor: AP2 hängt von AP1 ab; AP1 offen, danach erledigt.
        Aktion: select_package. Erwartet: zuerst nur AP1 wählbar; nach
        Abschluss von AP1 wird AP2 gewählt. Unbekannte Abhängigkeiten
        blockieren nicht."""
        self.store(ticket("AP1", "Basis"),
                   ticket("AP2", "Abhängig", dependencies=["AP1"]))
        self.assertEqual("AP1", self.select()["id"])

        stored = self.read_store()
        for item in stored["tickets"]:
            if item["id"] == "AP1":
                item.update(state="done", commit="abcdef1", test="test_ap1")
        support.write_ticket_store(self.project, stored["tickets"])
        self.assertEqual("AP2", self.select()["id"])

        support.write_ticket_store(self.project, [
            ticket("AP3", "Fremd", dependencies=["X9"])])
        self.assertEqual("AP3", self.select()["id"])

    def test_prefer_reattaches_even_a_blocked_package(self):
        """Vor: AP1 offen, AP2 blockiert. Aktion: select_package(prefer=AP2).
        Erwartet: AP2 wird vorrangig gewählt (Nutzer-Intention Reattach);
        ein unbekanntes prefer wird ignoriert."""
        self.store(ticket("AP1", "Offen"),
                   ticket("AP2", "Blockiert", state="blocked",
                          blocked_reason="Grund"))

        self.assertEqual("AP2", self.select(prefer="AP2")["id"])
        self.assertEqual("AP1", self.select(prefer="X9")["id"])


class GateTest(RunnerCase):
    """Abschlussschranke auf ``TICKET-<ID>.json``."""

    def gate(self, worktree, pid="AP7"):
        return requires(self.module, "gate_errors")(worktree, pid, self.base)

    def test_complete_package_passes_without_findings(self):
        """Vor: Commit mit Paketpräfix, docs/features, Review PASS, saubere
        Arbeitskopie und TICKET-Datei mit state done/commit/test.
        Aktion: gate_errors. Erwartet: []."""
        worktree = self.add_worktree()
        self.prepare_package(worktree)

        self.assertEqual([], self.gate(worktree))

    def test_missing_ticket_file_is_a_finding(self):
        """Vor: vollständiger Paketstand, aber keine TICKET-AP7.json.
        Aktion: gate_errors. Erwartet: Befund nennt die Datei."""
        worktree = self.add_worktree()
        self.prepare_package(worktree)
        (worktree / "TICKET-AP7.json").unlink()

        errors = self.gate(worktree)

        self.assertTrue(any("TICKET-AP7.json" in error for error in errors),
                        errors)

    def test_unreadable_ticket_file_is_a_finding(self):
        """Vor: TICKET-Datei mit defektem JSON. Aktion: gate_errors.
        Erwartet: Befund nennt die Datei und die Lesbarkeit."""
        worktree = self.add_worktree()
        self.prepare_package(worktree)
        (worktree / "TICKET-AP7.json").write_text("{", encoding="utf-8")

        errors = self.gate(worktree)

        text = "\n".join(errors)
        self.assertIn("TICKET-AP7.json", text)
        self.assertIn("lesbar", text.lower())

    def test_state_must_be_done(self):
        """Vor: TICKET-Datei mit state=in-progress. Aktion: gate_errors.
        Erwartet: Befund nennt state und done."""
        worktree = self.add_worktree()
        self.prepare_package(worktree)
        revision = self.head(worktree)
        self.write_ticket_file(worktree, ticket(
            "AP7", "Titel", state="in-progress", commit=revision,
            test="test_ap7"))

        errors = self.gate(worktree)

        text = "\n".join(errors)
        self.assertIn("state", text)
        self.assertIn("done", text)

    def test_commit_must_exist_in_the_repository(self):
        """Vor: TICKET-Datei nennt einen unbekannten Commit. Aktion:
        gate_errors. Erwartet: Befund nennt commit und Repository."""
        worktree = self.add_worktree()
        self.prepare_package(worktree, commit="deadbee")

        errors = self.gate(worktree)

        text = "\n".join(errors)
        self.assertIn("commit", text.lower())
        self.assertIn("deadbee", text)

    def test_test_field_must_not_be_empty(self):
        """Vor: TICKET-Datei mit leerem test-Feld. Aktion: gate_errors.
        Erwartet: Befund nennt test."""
        worktree = self.add_worktree()
        self.prepare_package(worktree, test="")

        errors = self.gate(worktree)

        self.assertTrue(any("test" in error.lower() for error in errors),
                        errors)

    def test_already_integrated_package_passes_without_new_commits(self):
        """Vor: Paketcommit liegt bereits als Vorfahre der Basis vor, die
        TICKET-Datei nennt ihn; kein neuer Commit seit der Basis.
        Aktion: gate_errors. Erwartet: kein Befund (Already-Integrated-Regel)."""
        (self.project / "docs" / "features").mkdir(parents=True, exist_ok=True)
        (self.project / "docs" / "features" / "AP7.md").write_text(
            "# AP7\n", encoding="utf-8")
        (self.project / "docs" / "reviews").mkdir(parents=True, exist_ok=True)
        (self.project / "docs" / "reviews" / "AP7-review-1.md").write_text(
            "# Review\n\nVerdict: PASS\n", encoding="utf-8")
        (self.project / "impl-AP7.txt").write_text("x\n", encoding="utf-8")
        self.git_ok(self.project, "add", "-A")
        self.git_ok(self.project, "commit", "-q", "-m", "AP7: Umsetzung")
        revision = self.head(self.project)
        self.base = revision
        self.write_ticket_file(self.project, ticket(
            "AP7", "Titel", state="done", commit=revision,
            test="test_ap7"))

        self.assertEqual([], self.gate(self.project))

    def test_docs_review_and_clean_checks_are_unchanged(self):
        """Vor: fehlende Feature-Doku, Review ohne PASS, uncommittete Datei.
        Aktion: gate_errors. Erwartet: je ein Befund zu docs/features,
        Review-PASS und Sauberkeit."""
        worktree = self.add_worktree()
        self.prepare_package(worktree, docs=False, review="FAIL")
        (worktree / "offen.txt").write_text("x\n", encoding="utf-8")

        errors = self.gate(worktree)

        text = "\n".join(errors)
        self.assertIn("docs/features/AP7.md", text)
        self.assertIn("Verdict: PASS", text)
        self.assertIn("sauber", text)
        self.assertIn("offen.txt", text)


class SyncTicketTest(RunnerCase):
    """Übernahme des Paketabschlusses in den Projektspeicher."""

    def sync(self, worktree, pid="AP1", **kwargs):
        return requires(self.module, "sync_ticket")(
            self.project, worktree, pid, **kwargs)

    def test_a_complete_ticket_is_taken_over_and_clears_block_fields(self):
        """Vor: Projekt AP1 blockiert; Arbeitskopie TICKET-AP1.json done mit
        commit/test/pr_url. Aktion: sync_ticket(require_commit=False).
        Erwartet: changed=True; state/commit/test/pr_url übernommen,
        blocked_reason/waiting_note geräumt."""
        self.store(ticket("AP1", "Titel", state="blocked",
                          blocked_reason="alt", waiting_note="alt"))
        worktree = self.add_worktree()
        self.write_ticket_file(worktree, ticket(
            "AP1", "Titel", state="done", commit="deadbee",
            test="test_ap1", pr_url="http://example.invalid/pr/1"))

        changed, message = self.sync(worktree, require_commit=False)

        self.assertTrue(changed, message)
        record = self.records()["AP1"]
        self.assertEqual("done", record["state"])
        self.assertEqual("deadbee", record["commit"])
        self.assertEqual("test_ap1", record["test"])
        self.assertEqual("http://example.invalid/pr/1", record["pr_url"])
        self.assertEqual("", record["blocked_reason"])
        self.assertEqual("", record["waiting_note"])

    def test_require_commit_rejects_a_commit_unknown_to_the_project(self):
        """Vor: Arbeitskopie nennt einen Commit, den das Projekt nicht kennt.
        Aktion: sync_ticket ohne require_commit=False.
        Erwartet: changed=False, Speicher unverändert."""
        self.store(ticket("AP1", "Titel"))
        before = self.read_store()
        worktree = self.add_worktree()
        self.write_ticket_file(worktree, ticket(
            "AP1", "Titel", state="done", commit="deadbee",
            test="test_ap1"))

        changed, message = self.sync(worktree)

        self.assertFalse(changed, message)
        self.assertEqual(before, self.read_store())

    def test_missing_or_incomplete_source_is_refused_without_change(self):
        """Vor: fehlende Datei, defekte Datei und nicht-done-Datei.
        Aktion: sync_ticket. Erwartet: jeweils changed=False und ein Grund;
        der Speicher bleibt unverändert."""
        self.store(ticket("AP1", "Titel"))
        before = self.read_store()
        worktree = self.add_worktree()

        changed, message = self.sync(worktree)
        self.assertFalse(changed)
        self.assertTrue(message)
        self.assertEqual(before, self.read_store())

        (worktree / "TICKET-AP1.json").write_text("{", encoding="utf-8")
        changed, message = self.sync(worktree)
        self.assertFalse(changed)
        self.assertTrue(message)

        self.write_ticket_file(worktree, ticket("AP1", "Titel",
                                                state="open"))
        changed, message = self.sync(worktree)
        self.assertFalse(changed)
        self.assertTrue(message)
        self.assertEqual(before, self.read_store())

    def test_a_ticket_missing_in_the_project_is_refused(self):
        """Vor: Arbeitskopie X9 done, Projekt kennt X9 nicht. Aktion:
        sync_ticket. Erwartet: changed=False, kein Ticket wird erfunden."""
        self.store(ticket("AP1", "Titel"))
        worktree = self.add_worktree()
        self.write_ticket_file(worktree, ticket(
            "X9", "Fremd", state="done", commit="abcdef1", test="test_x9"))

        changed, message = self.sync(worktree, "X9", require_commit=False)

        self.assertFalse(changed, message)
        self.assertNotIn("X9", self.records())


class MarkAndReportTest(RunnerCase):
    """Blockier-/Wartevermerke und der Statusbericht."""

    def test_mark_blocked_sets_state_and_reason_idempotently(self):
        """Vor: AP1 offen. Aktion: mark_blocked zweimal. Erwartet: erster
        Aufruf changed=True mit state=blocked und Grund, zweiter changed=False
        ohne weiteren Zustandswechsel."""
        self.store(ticket("AP1", "Titel"))

        changed, message = requires(self.module, "mark_blocked")(
            self.project, "AP1", "Merge kaputt")
        self.assertTrue(changed, message)
        record = self.records()["AP1"]
        self.assertEqual("blocked", record["state"])
        self.assertEqual("Merge kaputt", record["blocked_reason"])

        changed, message = self.module.mark_blocked(
            self.project, "AP1", "anderer Grund")
        self.assertFalse(changed, message)
        self.assertEqual("Merge kaputt", self.records()["AP1"]["blocked_reason"])

    def test_mark_waiting_merge_sets_note_and_pr_url(self):
        """Vor: AP1 offen. Aktion: mark_waiting_merge mit Notiz und PR-URL.
        Erwartet: state=waiting-merge, waiting_note und pr_url gesetzt;
        ein zweiter Aufruf ändert nichts."""
        self.store(ticket("AP1", "Titel"))

        changed, message = requires(self.module, "mark_waiting_merge")(
            self.project, "AP1", "PR offen", "http://example.invalid/pr/9")

        self.assertTrue(changed, message)
        record = self.records()["AP1"]
        self.assertEqual("waiting-merge", record["state"])
        self.assertEqual("PR offen", record["waiting_note"])
        self.assertEqual("http://example.invalid/pr/9", record["pr_url"])

        changed, message = self.module.mark_waiting_merge(
            self.project, "AP1", "neu", "http://example.invalid/pr/10")
        self.assertFalse(changed, message)
        self.assertEqual("PR offen", self.records()["AP1"]["waiting_note"])

    def test_status_report_groups_by_store_state(self):
        """Vor: offen/in-progress/blockiert/wartend/erledigt im Speicher.
        Aktion: status_report. Erwartet: open enthält offen und in-progress,
        waiting/blocked/done jeweils die passenden IDs."""
        self.store(
            ticket("AP1", "Offen"),
            ticket("AP2", "Läuft", state="in-progress"),
            ticket("AP3", "Blockiert", state="blocked",
                   blocked_reason="x"),
            ticket("AP4", "Wartet", state="waiting-merge",
                   waiting_note="x"),
            ticket("AP5", "Fertig", state="done", commit="abcdef1",
                   test="test_ap5"),
        )

        report = requires(self.module, "status_report")(self.project)

        self.assertEqual(["AP1", "AP2"], report["open"])
        self.assertEqual(["AP4"], report["waiting"])
        self.assertEqual(["AP3"], report["blocked"])
        self.assertEqual(["AP5"], report["done"])


class MarkStartedTest(RunnerCase):
    """B1/Anforderung 4: der Läufer markiert den Bearbeitungsbeginn.

    ``mark_start(project, pid)`` ist der einzige automatische Übergang
    open → in-progress. Er gehört zum Läufer-Lebenszyklus, nicht zum Editor:
    die UI ändert weiterhin nie einen Zustand. Der Loopback-Fake ersetzt
    GitHub; es gibt keine echten Netzzugriffe.
    """

    def setUp(self):
        super().setUp()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _IssueHandler)
        self.httpd.requests = []
        self.httpd.issues = {
            501: {"number": 501, "title": "Remote", "state": "open",
                  "labels": [{"name": "ready"}]},
        }
        self.httpd.fail_patch = False
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_github)
        self.github_base = ("http://127.0.0.1:%d"
                            % self.httpd.server_address[1])

    def _stop_github(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    # ------------------------------------------------------------- Helfer
    def write_issues_env(self):
        self.env_path.write_text(
            "TYPE=generic\n"
            'GITHUB_ENABLED="1"\n'
            'GITHUB_REPO="owner/name"\n'
            'GITHUB_API="%s"\n'
            'GITHUB_ISSUES_ENABLED="1"\n' % self.github_base,
            encoding="utf-8")

    def run_cli(self, *args):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("VIBE")
               and key not in ("GITHUB_TOKEN", "GH_TOKEN")}
        (self.root / "home").mkdir(exist_ok=True)
        env.update({
            "HOME": str(self.root / "home"),
            "VIBE": str(self.root),
            "VIBE_STORAGE_LOCK_DIR": str(self.root / "locks"),
            "VIBE_NO_CONTAINER": "1",
        })
        return subprocess.run(
            [sys.executable, str(MODULE), *args],
            cwd=str(self.root), env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=60)

    def store_bytes(self):
        return (self.project / ".vibe" / "tickets.json").read_bytes()

    def patches(self):
        return [call for call in self.httpd.requests
                if call["method"] == "PATCH"]

    # -------------------------------------------------------------- Fälle
    def test_open_becomes_in_progress_and_cli_reports_ok(self):
        """Vor: AP1 und AP2 offen, nicht verbunden. Aktion: mark_start (AP1)
        und CLI ``mark-start`` (AP2). Erwartet: beide in-progress,
        changed=True bzw. Exit 0 mit OK-Zeile."""
        self.store(ticket("AP1", "Eins"), ticket("AP2", "Zwei"))

        changed, message = requires(self.module, "mark_start")(
            self.project, "AP1")
        self.assertTrue(changed, message)
        self.assertEqual("in-progress", self.records()["AP1"]["state"])

        result = self.run_cli("mark-start", "--project", str(self.project),
                              "--id", "AP2")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("OK:", result.stdout)
        self.assertEqual("in-progress", self.records()["AP2"]["state"])

    def test_already_in_progress_is_idempotent_and_cli_reports_hint(self):
        """Vor: AP1/AP2 bereits in-progress. Aktion: mark_start und CLI.
        Erwartet: Speicher bytegleich, changed=False, CLI-Exit 1 mit
        HINWEIS-Zeile."""
        self.store(ticket("AP1", "Eins", state="in-progress"),
                   ticket("AP2", "Zwei", state="in-progress"))
        before = self.store_bytes()

        changed, message = requires(self.module, "mark_start")(
            self.project, "AP1")
        self.assertFalse(changed, message)
        self.assertIn("bereits", message.lower())
        self.assertEqual(before, self.store_bytes())

        result = self.run_cli("mark-start", "--project", str(self.project),
                              "--id", "AP2")
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("HINWEIS:", result.stdout)
        self.assertEqual(before, self.store_bytes())

    def test_draft_is_not_started(self):
        """Vor: AP1 draft. Aktion: mark_start. Erwartet: unverändert,
        changed=False (nur open darf starten)."""
        self.store(ticket("AP1", "Entwurf", state="draft"))
        before = self.store_bytes()

        changed, message = requires(self.module, "mark_start")(
            self.project, "AP1")

        self.assertFalse(changed, message)
        self.assertEqual("draft", self.records()["AP1"]["state"])
        self.assertEqual(before, self.store_bytes())

    def test_done_blocked_and_waiting_merge_are_not_started(self):
        """Vor: AP2 done, AP3 blocked, AP4 waiting-merge. Aktion: mark_start.
        Erwartet: alle unverändert, changed=False."""
        self.store(
            ticket("AP2", "Fertig", state="done", commit="abcdef1",
                   test="test_ap2"),
            ticket("AP3", "Blockiert", state="blocked",
                   blocked_reason="Grund"),
            ticket("AP4", "Wartet", state="waiting-merge",
                   waiting_note="PR"),
        )
        before = self.store_bytes()

        for tid in ("AP2", "AP3", "AP4"):
            with self.subTest(ticket=tid):
                changed, message = requires(self.module, "mark_start")(
                    self.project, tid)
                self.assertFalse(changed, message)
                self.assertEqual(before, self.store_bytes())

    def test_missing_ticket_reports_the_store_gap(self):
        """Vor: kein Ticket X9. Aktion: mark_start. Erwartet: changed=False,
        Meldung „fehlt im Ticketspeicher“, Speicher unverändert."""
        self.store(ticket("AP1", "Eins"))
        before = self.store_bytes()

        changed, message = requires(self.module, "mark_start")(
            self.project, "X9")

        self.assertFalse(changed, message)
        self.assertIn("fehlt im Ticketspeicher", message)
        self.assertEqual(before, self.store_bytes())

    def test_connected_open_updates_the_in_progress_label(self):
        """Vor: Issues-Sync aktiv, GH-Ticket mit github=501 und Ready-Label.
        Aktion: mark_start. Erwartet: genau ein Label-PATCH mit
        in-progress (Ready-Label bleibt), lokaler Zustand in-progress."""
        self.write_issues_env()
        self.store(ticket("GH-501", "Verbunden", github=501))

        changed, message = requires(self.module, "mark_start")(
            self.project, "GH-501")

        self.assertTrue(changed, message)
        self.assertEqual("in-progress", self.records()["GH-501"]["state"])
        patches = self.patches()
        self.assertEqual(1, len(patches), patches)
        self.assertTrue(patches[0]["path"].rstrip("/").endswith("/issues/501"),
                        patches)
        labels = set(patches[0]["body"].get("labels") or [])
        self.assertIn("in-progress", labels)
        self.assertIn("ready", labels)

    def test_connected_patch_failure_still_sets_the_local_state(self):
        """Vor: Issues-Sync aktiv, github=501, PATCH antwortet 500. Aktion:
        mark_start. Erwartet: lokaler Zustand in-progress, changed=True und
        eine Meldung mit Best-effort-Hinweis (Sync gleicht später ab)."""
        self.write_issues_env()
        self.httpd.fail_patch = True
        self.store(ticket("GH-501", "Verbunden", github=501))

        changed, message = requires(self.module, "mark_start")(
            self.project, "GH-501")

        self.assertTrue(changed, message)
        self.assertEqual("in-progress", self.records()["GH-501"]["state"])
        text = message.lower()
        self.assertTrue(any(term in text for term in
                            ("best effort", "best-effort", "lokal", "github")),
                        message)

    def test_connected_ticket_without_github_reference_has_no_rest_call(self):
        """Vor: Issues-Sync aktiv, AP1 ohne github-Bezug. Aktion: mark_start.
        Erwartet: rein lokale Änderung in-progress, kein REST-Aufruf."""
        self.write_issues_env()
        self.store(ticket("AP1", "Lokal"))

        changed, message = requires(self.module, "mark_start")(
            self.project, "AP1")

        self.assertTrue(changed, message)
        self.assertEqual("in-progress", self.records()["AP1"]["state"])
        self.assertEqual([], self.httpd.requests)

    def test_transport_after_mark_start_carries_in_progress(self):
        """Vor: AP1 offen, Arbeitskopie vorhanden. Aktion: mark_start, dann
        transport_ticket. Erwartet: TICKET-AP1.json zeigt state in-progress –
        die Reihenfolge mark-start vor copy-notes ist damit belegt."""
        self.store(ticket("AP1", "Transport"))
        worktree = self.add_worktree()

        changed, message = requires(self.module, "mark_start")(
            self.project, "AP1")
        self.assertTrue(changed, message)
        ok, _ = requires(self.module, "transport_ticket")(
            self.project, worktree, "AP1")
        self.assertTrue(ok)
        carried = json.loads(
            (worktree / "TICKET-AP1.json").read_text(encoding="utf-8"))
        self.assertEqual("in-progress", carried["state"])

    def test_two_calls_are_idempotent(self):
        """Vor: AP1 offen. Aktion: mark_start zweimal. Erwartet: erster
        changed=True, zweiter changed=False; Speicher nach dem zweiten
        bytegleich zum Stand nach dem ersten."""
        self.store(ticket("AP1", "Eins"))

        first, first_message = requires(self.module, "mark_start")(
            self.project, "AP1")
        self.assertTrue(first, first_message)
        after_first = self.store_bytes()

        second, second_message = requires(self.module, "mark_start")(
            self.project, "AP1")
        self.assertFalse(second, second_message)
        self.assertIn("bereits", second_message.lower())
        self.assertEqual(after_first, self.store_bytes())

    def test_runner_invokes_mark_start_between_register_and_copy_notes(self):
        """Vor: Quelltext ``bin/vibe-run.sh``. Aktion: Positionen prüfen.
        Erwartet: ``mark-start`` steht nach ``worktree-register`` und vor
        ``copy-notes``; der Aufruf ist nicht blockierend (``|| true``).
        Fehlerfall: kein Aufruf, falsche Reihenfolge oder blockierender
        Fehlschlag."""
        text = (REPO / "bin" / "vibe-run.sh").read_text(encoding="utf-8")
        start = text.find("mark-start --project")
        self.assertGreaterEqual(
            start, 0, "vibe-run.sh ruft kein mark-start --project auf")
        copy_notes = text.find("copy-notes")
        self.assertGreater(copy_notes, start,
                           "mark-start steht nicht vor copy-notes")
        register = text.find("worktree-register")
        self.assertGreaterEqual(register, 0)
        self.assertLess(register, start,
                        "mark-start steht vor worktree-register")
        region = text[start:start + 220]
        self.assertIn("|| true", region,
                      "mark-start ist blockierend (kein '|| true'): " + region)


class PriorityViewTest(RunnerCase):
    """Priorisierungsansicht und -validierung auf dem Speicher."""

    def setUp(self):
        super().setUp()
        self.store(
            ticket("AP1", "Eins", priority="P1"),
            ticket("AP2", "Zwei", priority="P0"),
            ticket("AP3", "Fertig", state="done", commit="abcdef1",
                   test="test_ap3"),
            ticket("B1", "Bug", type="bug"),
        )
        self.set_order("AP3 AP2 AP1 X9")

    def test_priority_view_reports_status_and_effective_queue(self):
        """Vor: PACKAGE_ORDER mit erledigtem und unbekanntem Eintrag.
        Aktion: priority_view. Erwartet: Status erledigt/offen/fehlt je
        Eintrag; queue in Standardordnung AP2, AP1, B1 (erledigt entfällt)."""
        view = requires(self.module, "priority_view")(self.project)

        statuses = {entry["id"]: entry["status"] for entry in view["order"]}
        self.assertEqual("erledigt", statuses["AP3"])
        self.assertEqual("offen", statuses["AP2"])
        self.assertEqual("fehlt", statuses["X9"])
        self.assertEqual(["AP2", "AP1", "B1"],
                         [entry["id"] for entry in view["queue"]])

    def test_normalize_order_deduplicates_and_rejects_unknown_ids(self):
        """Vor: gültige und unbekannte IDs. Aktion: normalize_order.
        Erwartet: Dubletten entfallen, Reihenfolge bleibt; unbekannte ID
        ist ValueError mit der ID in der Meldung."""
        normalize_order = requires(self.module, "normalize_order")

        self.assertEqual(["AP2", "AP1"],
                         normalize_order(self.project, "AP2, AP1, AP2"))
        with self.assertRaises(ValueError) as caught:
            normalize_order(self.project, "AP2 X9")
        self.assertIn("X9", str(caught.exception))


class WorkCopyTest(RunnerCase):
    """Arbeitsnotizen, Tickettransport und Git-Exclude."""

    def test_copy_work_notes_transfers_only_agents_md(self):
        """Vor: Projekt mit AGENTS.md, TICKETS.md und FEEDBACK.md.
        Aktion: copy_work_notes. Erwartet: nur AGENTS.md in der Arbeitskopie;
        die alten Ledger-Dateien werden nicht mehr transportiert."""
        (self.project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
        (self.project / "FEEDBACK.md").write_text("# FEEDBACK\n",
                                                  encoding="utf-8")
        worktree = self.add_worktree()

        copied, skipped = requires(self.module, "copy_work_notes")(
            self.project, worktree)

        self.assertEqual(["AGENTS.md"], copied)
        self.assertEqual([], skipped)
        self.assertTrue((worktree / "AGENTS.md").is_file())
        self.assertFalse((worktree / "TICKETS.md").exists())
        self.assertFalse((worktree / "FEEDBACK.md").exists())

    def exclude_path(self, worktree):
        result = support.git(worktree, "rev-parse", "--git-path", "info/exclude")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        path = Path(result.stdout.strip())
        return path if path.is_absolute() else worktree / path

    def test_transport_ticket_writes_a_visible_file_and_excludes_it(self):
        """Vor: AP1 im Projekt-Speicher, echte Arbeitskopie. Aktion:
        transport_ticket zweimal. Erwartet: TICKET-AP1.json in der Wurzel mit
        dem Ticketinhalt; genau ein Exclude-Eintrag, auch nach dem zweiten
        Lauf."""
        self.store(ticket("AP1", "Titel", state="in-progress"))
        worktree = self.add_worktree()
        transport = requires(self.module, "transport_ticket")

        ok, exclude_ok = transport(self.project, worktree, "AP1")

        self.assertTrue(ok)
        self.assertTrue(exclude_ok)
        target = worktree / "TICKET-AP1.json"
        self.assertTrue(target.is_file())
        self.assertEqual("AP1",
                         json.loads(target.read_text(encoding="utf-8"))["id"])
        exclude = self.exclude_path(worktree)
        first = exclude.read_text(encoding="utf-8")
        self.assertIn("TICKET-AP1.json", first)

        transport(self.project, worktree, "AP1")
        self.assertEqual(1, exclude.read_text(encoding="utf-8")
                         .count("TICKET-AP1.json"))

    def test_transport_ticket_missing_in_the_store_fails(self):
        """Vor: Projekt ohne Ticket AP9. Aktion: transport_ticket.
        Erwartet: ok=False, keine Datei, kein Exclude-Eintrag."""
        worktree = self.add_worktree()

        ok, _ = requires(self.module, "transport_ticket")(
            self.project, worktree, "AP9")

        self.assertFalse(ok)
        self.assertFalse((worktree / "TICKET-AP9.json").exists())
        exclude = self.exclude_path(worktree)
        text = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
        self.assertNotIn("TICKET-AP9.json", text)

    def test_copy_notes_id_transports_the_ticket_and_reports_missing_ones(self):
        """Vor: AP1 im Speicher, AP9 nicht. Aktion: copy-notes --id AP1 bzw.
        --id AP9 über die CLI. Erwartet: AP1 Exit 0 mit OK-Zeile und Datei;
        AP9 Exit 1 mit FEHLT-Zeile und ohne Datei."""
        self.store(ticket("AP1", "Titel"))
        worktree = self.add_worktree()
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("VIBE")}
        env.update({
            "HOME": str(self.root / "home"),
            "VIBE": str(self.root),
            "VIBE_STORAGE_LOCK_DIR": str(self.root / "locks"),
            "VIBE_NO_CONTAINER": "1",
        })
        (self.root / "home").mkdir(exist_ok=True)

        def run(pid):
            return subprocess.run(
                [sys.executable, str(MODULE), "copy-notes",
                 "--project", str(self.project),
                 "--worktree", str(worktree), "--id", pid],
                cwd=str(self.root), env=env, stdin=subprocess.DEVNULL,
                capture_output=True, text=True, timeout=60)

        ok = run("AP1")
        self.assertEqual(0, ok.returncode, ok.stdout + ok.stderr)
        self.assertIn("OK:", ok.stdout)
        self.assertTrue((worktree / "TICKET-AP1.json").is_file())

        missing = run("AP9")
        self.assertEqual(1, missing.returncode,
                         missing.stdout + missing.stderr)
        self.assertIn("FEHLT:", missing.stdout)
        self.assertFalse((worktree / "TICKET-AP9.json").exists())

    def test_is_work_note_path_covers_ticket_files_at_the_root_only(self):
        """Vor: Stammdateien TICKET-<ID>.json und Pfade in Unterordnern.
        Aktion: is_work_note_path. Erwartet: Stammdateien sind Arbeitsnotizen
        (kein Dirty-Befund), Unterordner und andere Endungen nicht."""
        check = requires(self.module, "is_work_note_path")

        for value in ("TICKET-AP7.json", "TICKET-GH-48.json",
                      "AGENTS.md"):
            with self.subTest(path=value):
                self.assertTrue(check(value))
        for value in ("sub/TICKET-AP7.json", "TICKET-AP7.txt",
                      "TICKET-.json", "notiz.md"):
            with self.subTest(path=value):
                self.assertFalse(check(value))

    def test_project_exclude_mentions_only_current_work_notes(self):
        """Vor: Git-Projekt. Aktion: ensure_project_exclude. Erwartet:
        .vibe/tmp/ und AGENTS.md sind eingetragen; TICKETS.md/FEEDBACK.md
        nicht mehr."""
        requires(self.module, "ensure_project_exclude")(self.project)

        exclude = self.project / ".git" / "info" / "exclude"
        text = exclude.read_text(encoding="utf-8")
        self.assertIn(".vibe/tmp/", text)
        self.assertIn("AGENTS.md", text)
        self.assertNotIn("TICKETS.md", text)
        self.assertNotIn("FEEDBACK.md", text)


if __name__ == "__main__":
    unittest.main()
