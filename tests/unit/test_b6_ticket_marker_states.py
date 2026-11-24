"""GH-48: Blockier- und Wartezustände des Läufers im Ticketspeicher.

Dieses Modul ersetzt die früheren B6-Markdown-Marker-Fälle. Marker wie
``BLOCKIERT:``/``WARTET AUF MERGE:`` existieren nicht mehr; die Zustände sind
Felder des Ticketspeichers (``blocked``/``waiting-merge``). Geprüft wird:

* Freitext in der Beschreibung kann keinen Zustand vortäuschen,
* ``mark_blocked``/``mark_waiting_merge`` setzen Zustand, Grund/Notiz und
  PR-URL idempotent (auch über die CLI),
* ``status_report``/``select_package``/``priority_view``/``open_items``
  folgen den Speicherzuständen,
* ein erledigtes Ticket bleibt erledigt, auch wenn alte Wartefelder
  zurückbleiben.

Die Aussagen zu Auswahlordnung, Gate und Transport tragen zusätzlich
``tests/unit/test_gh48_runner_tickets.py``; hier bleibt die historische
B6-Fläche kompakt abgesichert. Keine Modellaufrufe, keine Netzverbindungen,
keine produktiven Pfade.

Run:

    python3 -m unittest tests.unit.test_b6_ticket_marker_states -v
"""
import importlib.machinery
import importlib.util
import io
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PACKAGES = REPO / "bin" / "vibe_packages.py"
CLI = REPO / "bin" / "vibe"

WAITING = "WARTET AUF MERGE"


def load_packages():
    loader = importlib.machinery.SourceFileLoader(
        "vibe_packages_b6_states_under_test", str(PACKAGES))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


def load_cli(vibe_root, home):
    old = {key: os.environ.get(key)
           for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ.update({"VIBE": str(vibe_root), "VIBE_NO_CONTAINER": "1",
                       "HOME": str(home)})
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_b6_states_cli_under_test", str(CLI))
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


def ticket_record(tid, title, type="task", state="open", **extra):
    record = {
        "id": tid, "title": title, "type": type, "state": state,
        "description": "", "github": None, "pr_url": "", "commit": "",
        "test": "", "blocked_reason": "", "waiting_note": "",
        "priority": "", "dependencies": [],
        "created": "2026-01-01T00:00:00+00:00",
        "updated": "2026-01-01T00:00:00+00:00",
    }
    record.update(extra)
    return record


def make_project(root, records, env_text="TYPE=generic\n"):
    project = Path(root) / "proj"
    (project / ".vibe").mkdir(parents=True, exist_ok=True)
    (project / ".vibe" / "project.env").write_text(env_text, encoding="utf-8")
    (project / ".vibe" / "tickets.json").write_text(
        json.dumps({"version": 1, "tickets": list(records)},
                   ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    return project


def read_records(project):
    document = json.loads(
        (Path(project) / ".vibe" / "tickets.json").read_text(encoding="utf-8"))
    return {item["id"]: item for item in document["tickets"]}


class StateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.module = load_packages()


class FreetextCannotPretendStateTest(StateCase):
    """Zustände sind Felder; Beschreibungstext ist nie eine Steuerzeile."""

    def test_marker_words_in_the_description_keep_the_ticket_open(self):
        """Vor: offenes Ticket, dessen Beschreibung 'BLOCKIERT:' und
        'WARTET AUF MERGE:' enthält. Aktion: status_report/select.
        Erwartet: open/ausgewählt, nicht blocked/waiting."""
        project = make_project(self.root, [ticket_record(
            "B5", "Titel", description="BLOCKIERT: Bericht\nWARTET AUF MERGE: PR")])

        report = self.module.status_report(project)
        selected = self.module.select_package(
            project, state_path=str(self.root / "next.json"))

        self.assertEqual(["B5"], report["open"])
        self.assertEqual([], report["blocked"])
        self.assertEqual([], report["waiting"])
        self.assertEqual("B5", selected["id"])

    def test_priority_view_reports_freetext_as_open(self):
        """Vor: PACKAGE_ORDER=B5, Beschreibung mit Markerwörtern.
        Aktion: priority_view. Erwartet: Status offen."""
        project = make_project(
            self.root,
            [ticket_record("B5", "Titel",
                           description="BLOCKIERT: nur Text")],
            env_text='TYPE=generic\nPACKAGE_ORDER="B5"\n')

        view = self.module.priority_view(project)
        by_id = {entry["id"]: entry for entry in view["order"]}

        self.assertEqual("offen", by_id["B5"]["status"])


class MarkCommandsTest(StateCase):
    """``mark_blocked``/``mark_waiting_merge`` schreiben Speicherzustände."""

    def test_mark_blocked_sets_state_and_reason(self):
        """Vor: T1 offen. Aktion: mark_blocked. Erwartet: blocked + Grund."""
        project = make_project(self.root, [ticket_record("T1", "Titel")])

        changed, message = self.module.mark_blocked(project, "T1", "extern")

        self.assertTrue(changed, message)
        record = read_records(project)["T1"]
        self.assertEqual("blocked", record["state"])
        self.assertEqual("extern", record["blocked_reason"])

    def test_mark_blocked_is_idempotent(self):
        """Vor: T1 bereits blocked. Aktion: zweiter Aufruf.
        Erwartet: changed False, Grund bleibt."""
        project = make_project(self.root, [ticket_record(
            "T1", "Titel", state="blocked", blocked_reason="extern")])

        changed, message = self.module.mark_blocked(project, "T1", "neu")

        self.assertFalse(changed, message)
        self.assertEqual("extern", read_records(project)["T1"]["blocked_reason"])

    def test_mark_waiting_sets_note_and_pr_url(self):
        """Vor: T1 offen. Aktion: mark_waiting_merge mit PR-URL.
        Erwartet: waiting-merge, waiting_note und pr_url gesetzt."""
        project = make_project(self.root, [ticket_record("T1", "Titel")])

        changed, message = self.module.mark_waiting_merge(
            project, "T1", "PR offen", "http://example.invalid/pr/6")

        self.assertTrue(changed, message)
        record = read_records(project)["T1"]
        self.assertEqual("waiting-merge", record["state"])
        self.assertEqual("PR offen", record["waiting_note"])
        self.assertEqual("http://example.invalid/pr/6", record["pr_url"])

    def test_mark_commands_report_unknown_tickets(self):
        """Vor: leerer Speicher. Aktion: mark_blocked/mark_waiting_merge.
        Erwartet: changed False und eine Meldung."""
        project = make_project(self.root, [])

        for call in (lambda: self.module.mark_blocked(project, "X1", "x"),
                     lambda: self.module.mark_waiting_merge(project, "X1", "x")):
            changed, message = call()
            self.assertFalse(changed)
            self.assertIn("X1", message)


class MarkCommandsSubprocessTest(StateCase):
    """CLI-Unterbefehle schreiben dieselben Zustände."""

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(PACKAGES), *args],
            cwd=str(self.root), stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=60)

    def test_mark_blocked_subcommand(self):
        """Vor: T1 offen. Aktion: mark-blocked --id T1 --note Grund.
        Erwartet: Exit 0, Ausgabe nennt blockiert, Speicher blocked."""
        project = make_project(self.root, [ticket_record("T1", "Titel")])

        result = self.run_cli("mark-blocked", "--project", str(project),
                              "--id", "T1", "--note", "extern")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("blockiert", (result.stdout + result.stderr).lower())
        self.assertEqual("blocked", read_records(project)["T1"]["state"])

    def test_mark_waiting_subcommand_keeps_pr_url(self):
        """Vor: T1 offen. Aktion: mark-waiting mit --pr-url.
        Erwartet: Exit 0, waiting-merge und pr_url im Speicher."""
        project = make_project(self.root, [ticket_record("T1", "Titel")])

        result = self.run_cli(
            "mark-waiting", "--project", str(project), "--id", "T1",
            "--note", "PR offen", "--pr-url",
            "http://example.invalid/pr/7")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        record = read_records(project)["T1"]
        self.assertEqual("waiting-merge", record["state"])
        self.assertEqual("http://example.invalid/pr/7", record["pr_url"])


class ReportAndSelectionTest(StateCase):
    """Bericht, Auswahl und Prioritätsansicht folgen den Speicherzuständen."""

    def test_status_report_groups_blocked_and_waiting(self):
        """Vor: T1 blocked, T2 waiting, T3 offen, T4 done.
        Erwartet: blocked=[T1], waiting=[T2], open=[T3], done=[T4]."""
        project = make_project(self.root, [
            ticket_record("T1", "Blockiert", state="blocked",
                          blocked_reason="extern"),
            ticket_record("T2", "Wartet", state="waiting-merge",
                          waiting_note="PR"),
            ticket_record("T3", "Offen"),
            ticket_record("T4", "Fertig", state="done", commit="abcdef1",
                          test="test_t4"),
        ])

        report = self.module.status_report(project)

        self.assertEqual(["T1"], report["blocked"])
        self.assertEqual(["T2"], report["waiting"])
        self.assertEqual(["T3"], report["open"])
        self.assertEqual(["T4"], report["done"])

    def test_selection_skips_blocked_and_waiting(self):
        """Vor: T1 blockiert, T2 wartend, T3 offen.
        Aktion: select_package. Erwartet: T3."""
        project = make_project(self.root, [
            ticket_record("T1", "Blockiert", state="blocked",
                          blocked_reason="extern"),
            ticket_record("T2", "Wartet", state="waiting-merge",
                          waiting_note="PR"),
            ticket_record("T3", "Offen"),
        ])

        selected = self.module.select_package(
            project, state_path=str(self.root / "next.json"))

        self.assertEqual("T3", selected["id"])

    def test_priority_view_marks_blocked_and_waiting(self):
        """Vor: PACKAGE_ORDER=T1,T2,T3; T1 blocked, T2 waiting, T3 offen.
        Erwartet: gesperrt / wartet auf Merge / offen; queue beginnt T3."""
        project = make_project(
            self.root,
            [ticket_record("T1", "Blockiert", state="blocked",
                           blocked_reason="extern"),
             ticket_record("T2", "Wartet", state="waiting-merge",
                           waiting_note="PR"),
             ticket_record("T3", "Offen")],
            env_text='TYPE=generic\nPACKAGE_ORDER="T1,T2,T3"\n')

        view = self.module.priority_view(project)
        by_id = {entry["id"]: entry for entry in view["order"]}

        self.assertEqual("gesperrt", by_id["T1"]["status"])
        self.assertEqual("wartet auf Merge", by_id["T2"]["status"])
        self.assertEqual("offen", by_id["T3"]["status"])
        self.assertEqual("T3", view["queue"][0]["id"])

    def test_done_ticket_stays_done_even_with_stale_waiting_note(self):
        """Vor: done-Ticket mit altem waiting_note. Aktion: open_items/
        ticket_items. Erwartet: nicht offen, Anzeige erledigt."""
        workspace = self.root / "ws"
        workspace.mkdir()
        home = self.root / "home"
        home.mkdir()
        cli = load_cli(workspace, home)
        make_project(workspace, [ticket_record(
            "T1", "Fertig", state="done", commit="abcdef1", test="test_t1",
            waiting_note="PR alt")])
        cli._pm.clear()

        self.assertEqual([], cli.open_items("proj"))
        self.assertEqual("erledigt", cli.ticket_items("proj")[0]["state"])


class TicketStatusDisplayTest(StateCase):
    """``bin/vibe`` zeigt die Zustände aus dem Speicher."""

    def test_open_items_and_ticket_items_show_blocked_and_waiting(self):
        """Vor: T1 blocked, T2 waiting. Aktion: open_items/ticket_items.
        Erwartet: (T1, Titel, BLOCKIERT) und (T2, Titel, WARTET AUF MERGE)."""
        workspace = self.root / "ws"
        workspace.mkdir()
        home = self.root / "home"
        home.mkdir()
        cli = load_cli(workspace, home)
        make_project(workspace, [
            ticket_record("T1", "Blockiert", state="blocked",
                          blocked_reason="extern"),
            ticket_record("T2", "Wartet", state="waiting-merge",
                          waiting_note="PR"),
        ])
        cli._pm.clear()

        items = cli.open_items("proj")
        rows = {row["id"]: row for row in cli.ticket_items("proj")}

        self.assertIn(("T1", "Blockiert", "BLOCKIERT"), items)
        self.assertIn(("T2", "Wartet", WAITING), items)
        self.assertEqual("BLOCKIERT", rows["T1"]["state"])
        self.assertEqual(WAITING, rows["T2"]["state"])

    def test_priority_command_names_waiting_package(self):
        """Vor: PACKAGE_ORDER=T1,T2; T1 waiting. Aktion: cmd_priority list.
        Erwartet: Zeile T1 nennt 'wartet auf Merge'."""
        workspace = self.root / "ws"
        workspace.mkdir()
        home = self.root / "home"
        home.mkdir()
        cli = load_cli(workspace, home)
        make_project(
            workspace,
            [ticket_record("T1", "Wartet", state="waiting-merge",
                           waiting_note="PR"),
             ticket_record("T2", "Offen")],
            env_text='TYPE=generic\nPACKAGE_ORDER="T1,T2"\n')
        cli._pm.clear()

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            cli.cmd_priority("proj", "list")

        text = output.getvalue()
        lines = [line for line in text.splitlines() if line.startswith("  T1")]
        self.assertTrue(lines, text)
        self.assertRegex(lines[0], r"(?i)wartet auf merge", text)


if __name__ == "__main__":
    unittest.main()
