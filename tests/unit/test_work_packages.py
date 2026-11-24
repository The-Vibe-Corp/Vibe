"""Tests für Arbeitspakete und Bugmeldungen aus der Oberfläche (F15, GH-48).

Geprüft werden der Ticketspeicher (Lesen, Anlegen, Ändern, Löschen), die
Bugmeldung als Tickettyp ``bug``, die HTTP-API des Dashboards und die
tatsächlich ausgelieferte Projektdetail-Seite. Alle Schreibvorgänge arbeiten
auf temporären Dateien; Markdown-Ledger existieren nicht mehr.

Run:

    python3 -m unittest tests.unit.test_work_packages -v
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from tests.unit.web_page import served_page

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
WEB = REPO / "bin" / "vibe-web.py"
STAMP = "2026-01-01T00:00:00+00:00"


def ticket_record(tid, title, type="task", state="open", **extra):
    record = {
        "id": tid, "title": title, "type": type, "state": state,
        "description": "", "github": None, "pr_url": "", "commit": "",
        "test": "", "blocked_reason": "", "waiting_note": "",
        "priority": "", "dependencies": [],
        "created": STAMP, "updated": STAMP,
    }
    record.update(extra)
    return record


BASELINE = [
    ticket_record("F15", "Arbeitspakete", description="Bestehendes Paket",
                  priority="P1"),
    ticket_record("V-001", "Erledigtes Paket", state="done",
                  description="Fertig", priority="P0", commit="abcdef1",
                  test="test_x"),
    ticket_record("V-099", "Blockiertes Paket", state="blocked",
                  description="Wartet", blocked_reason="fehlende Freigabe"),
    ticket_record("F1", "Bestehender Punkt", type="feedback",
                  description="Bestehende Beschreibung"),
]

ISOLATED_ENV = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_PROFILE", "VIBE_INSTALL",
    "VIBE_RUNTIME", "VIBE_STATE", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR", "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER",
)


def isolated_env(root, home, port):
    env = os.environ.copy()
    for key in ISOLATED_ENV:
        env.pop(key, None)
    env.update({
        "VIBE": str(root),
        "VIBE_NO_CONTAINER": "1",
        "VIBE_UI_PORT": str(port),
        "HOME": str(home),
        "VIBE_STATE": str(Path(root) / "_toolchain"),
        "VIBE_AGENTS_DIR": str(Path(home) / ".config" / "opencode" / "agents"),
        "VIBE_CONFIG_FILE": str(Path(home) / ".config" / "vibe" / "config.json"),
    })
    return env


def load_cli(vibe_root):
    root = Path(vibe_root)
    old = {key: os.environ.get(key) for key in ISOLATED_ENV}
    for key in ISOLATED_ENV:
        os.environ.pop(key, None)
    os.environ.update(isolated_env(root, root / "home", 8787))
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_work_packages_under_test", str(CLI))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return module


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def numbered_id_parts(ident):
    match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.:-]*?)(\d+)", ident)
    if not match:
        raise AssertionError("Erwartete fortlaufende Auto-ID: " + repr(ident))
    return match.group(1), int(match.group(2))


class WorkPackageFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        self.cli = load_cli(self.root)
        self.store = self.project / ".vibe" / "tickets.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, records):
        self.store.write_text(
            json.dumps({"version": 1, "tickets": list(records)},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        return self.store

    def records(self):
        if not self.store.is_file():
            return {}
        return {item["id"]: item for item in json.loads(
            self.store.read_text(encoding="utf-8"))["tickets"]}


class WorkPackageModelTest(WorkPackageFixture):
    def test_lists_work_packages_with_title_description_and_state(self):
        self.write(BASELINE)

        entries = self.cli.ticket_items("proj")

        self.assertEqual([entry["id"] for entry in entries],
                         ["F15", "V-001", "V-099"])
        self.assertEqual("Arbeitspakete", entries[0]["title"])
        self.assertEqual("Bestehendes Paket", entries[0]["description"])
        self.assertEqual("offen", entries[0]["state"])
        self.assertEqual("erledigt", entries[1]["state"])
        self.assertEqual("BLOCKIERT", entries[2]["state"])

    def test_missing_store_yields_no_entries(self):
        self.assertEqual([], self.cli.ticket_items("proj"))
        self.assertEqual([], self.cli.feedback_items("proj"))

    def test_update_changes_title_and_description_but_keeps_other_fields(self):
        self.write(BASELINE)

        self.cli.ticket_update("proj", "F15", "Neuer Titel", "Neue Beschreibung")

        record = self.records()["F15"]
        self.assertEqual("Neuer Titel", record["title"])
        self.assertEqual("Neue Beschreibung", record["description"])
        self.assertEqual("P1", record["priority"])
        self.assertEqual("task", record["type"])

    def test_update_rejects_completed_work_package(self):
        self.write(BASELINE)
        before = self.store.read_bytes()

        with self.assertRaisesRegex(ValueError, "nicht bearbeitbar"):
            self.cli.ticket_update("proj", "V-001", "Neu")

        self.assertEqual(before, self.store.read_bytes())

    def test_update_rejects_empty_title_and_line_break(self):
        self.write(BASELINE)
        before = self.store.read_bytes()

        with self.assertRaises(ValueError):
            self.cli.ticket_update("proj", "F15", "   ")
        with self.assertRaisesRegex(ValueError, "Zeilenumbruch"):
            self.cli.ticket_update("proj", "F15", "Neu\nZweite")

        self.assertEqual(before, self.store.read_bytes())

    def test_update_rejects_unknown_id_without_changing_the_store(self):
        self.write(BASELINE)
        before = self.store.read_bytes()

        with self.assertRaisesRegex(ValueError, "nicht gefunden"):
            self.cli.ticket_update("proj", "F99", "Neu")

        self.assertEqual(before, self.store.read_bytes())

    def test_add_work_package_appends_and_keeps_existing_entries(self):
        self.write(BASELINE)

        tid = self.cli.add_ticket("proj", "F18", "Neues Paket",
                                  "Beschreibung")

        self.assertEqual("F18", tid)
        self.assertEqual("Neues Paket", self.records()["F18"]["title"])
        self.assertIn("F15", self.records())

    def test_add_work_package_rejects_duplicate_id(self):
        self.write(BASELINE)

        with self.assertRaises(ValueError):
            self.cli.add_ticket("proj", "F15", "Doppelt")

        self.assertEqual(1, list(self.records()).count("F15"))

    def test_add_work_package_rejects_invalid_id(self):
        with self.assertRaises(ValueError):
            self.cli.add_ticket("proj", "keine id", "Titel")

        self.assertEqual({}, self.records())

    def test_add_work_package_with_blank_id_gets_an_auto_assigned_id(self):
        tid = self.cli.add_ticket("proj", "", "Auto Paket", "Text")

        prefix, number = numbered_id_parts(tid)
        self.assertEqual("AP", prefix)
        self.assertEqual(1, number)
        self.assertEqual("Auto Paket", self.records()[tid]["title"])

    def test_repeated_blank_ids_produce_distinct_sequential_ids(self):
        first = self.cli.add_ticket("proj", "", "Erstes")
        second = self.cli.add_ticket("proj", "", "Zweites")

        self.assertNotEqual(first, second)
        self.assertEqual(["AP1", "AP2"], [first, second])

    def test_auto_assigned_id_skips_numbers_already_taken(self):
        self.write([ticket_record("AP4", "Vorhanden")])

        tid = self.cli.add_ticket("proj", "", "Neu")

        self.assertEqual("AP5", tid)

    def test_auto_assignment_creates_a_missing_store(self):
        """GH-48: Die freie Anlage legt einen fehlenden Speicher an."""
        tid = self.cli.add_ticket("proj", "", "Ohne Speicher")

        self.assertTrue(self.store.is_file())
        self.assertIn(tid, self.records())

    def test_delete_removes_only_the_selected_work_package(self):
        self.write(BASELINE)

        self.cli.ticket_delete("proj", "F15")

        records = self.records()
        self.assertNotIn("F15", records)
        self.assertIn("V-099", records)

    def test_delete_rejects_unknown_id_without_changing_the_store(self):
        self.write(BASELINE)
        before = self.store.read_bytes()

        with self.assertRaisesRegex(ValueError, "nicht gefunden"):
            self.cli.ticket_delete("proj", "F99")

        self.assertEqual(before, self.store.read_bytes())

    def test_add_bug_uses_the_bug_type_and_separate_numbering(self):
        number = self.cli.add_bug("proj", "Kaputt", "Text")

        self.assertEqual("B1", number)
        record = self.records()["B1"]
        self.assertEqual("bug", record["type"])
        self.assertEqual("Kaputt", record["title"])

    def test_second_bug_gets_the_next_number_and_feedback_keeps_f_numbers(self):
        self.assertEqual("B1", self.cli.add_bug("proj", "Eins"))
        self.assertEqual("B2", self.cli.add_bug("proj", "Zwei"))
        self.assertEqual("F1", self.cli.add_feedback("proj", "Idee"))

        records = self.records()
        self.assertEqual("bug", records["B2"]["type"])
        self.assertEqual("feedback", records["F1"]["type"])

    def test_update_bug_keeps_the_bug_type(self):
        self.write([ticket_record("B1", "Bug", type="bug")])

        self.cli.feedback_update("proj", "B1", "Neuer Bug", "Text")

        self.assertEqual("bug", self.records()["B1"]["type"])

    def test_regular_feedback_has_kind_feedback(self):
        self.cli.add_feedback("proj", "Idee", "Text")

        rows = self.cli.feedback_items("proj")

        self.assertEqual("feedback", rows[0]["kind"])
        self.assertEqual("feedback", rows[0]["state"] and "feedback")

    def test_bug_rejects_missing_title_without_writing(self):
        with self.assertRaises(ValueError):
            self.cli.add_bug("proj", "   ")

        self.assertEqual({}, self.records())


class WorkPackageApiFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        log_dir = cls.root / "_logs"
        log_dir.mkdir()
        (log_dir / "proj.log").write_text("Startzeile\n", encoding="utf-8")
        cls.home = cls.root / "home"
        cls.home.mkdir()
        cls.port = free_port()
        env = isolated_env(cls.root, cls.home, cls.port)
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        token_file = cls.root / "_logs" / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port),
                                                  timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: " + output)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        if cls.proc.stdout:
            cls.proc.stdout.close()
        cls.tmp.cleanup()

    def setUp(self):
        (self.project / ".vibe" / "tickets.json").write_text(
            json.dumps({"version": 1, "tickets": BASELINE},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

    def request(self, path, payload=None, token=True):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data, method="POST" if data else "GET")
        req.add_header("Host", f"127.0.0.1:{self.port}")
        if token:
            req.add_header("X-Token", self.token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            code = error.code
            error.close()
            return code, body

    def records(self):
        return {item["id"]: item for item in json.loads(
            (self.project / ".vibe" / "tickets.json").read_text(
                encoding="utf-8"))["tickets"]}


class WorkPackageApiTest(WorkPackageApiFixture):
    def test_project_detail_exposes_editable_work_packages(self):
        status, body = self.request("/api/project?name=proj")

        self.assertEqual(status, 200, body)
        detail = json.loads(body)
        self.assertEqual([entry["id"] for entry in detail["tickets"]],
                         ["F15", "V-001", "V-099"])
        self.assertEqual("Arbeitspakete", detail["tickets"][0]["title"])
        self.assertEqual("Bestehendes Paket",
                         detail["tickets"][0]["description"])

    def test_api_adds_updates_and_deletes_a_work_package(self):
        status, body = self.request("/api/ticket", {
            "name": "proj", "action": "add", "id": "F18",
            "title": "Neues Paket", "description": "Beschreibung"})
        self.assertEqual(status, 200, body)
        self.assertIn("F18 angelegt", body)
        self.assertIn("F18", self.records())

        status, body = self.request("/api/ticket", {
            "name": "proj", "action": "update", "id": "F18",
            "title": "Geändertes Paket", "description": "Geändert"})
        self.assertEqual(status, 200, body)
        self.assertEqual("Geändertes Paket", self.records()["F18"]["title"])

        status, body = self.request("/api/ticket", {
            "name": "proj", "action": "delete", "id": "F18"})
        self.assertEqual(status, 200, body)
        self.assertNotIn("F18", self.records())
        self.assertIn("F15", self.records())

    def test_api_adds_work_package_without_an_id_and_names_the_assigned_id(self):
        status, body = self.request("/api/ticket", {
            "name": "proj", "action": "add", "title": "Auto Paket"})

        self.assertEqual(status, 200, body)
        self.assertNotIn("F15", body)
        fresh = [ident for ident in self.records()
                 if ident not in ("F15", "V-001", "V-099", "F1")]
        self.assertEqual(1, len(fresh), self.records())
        self.assertEqual(fresh[0] + " angelegt",
                         json.loads(body).get("message"), body)

    def test_api_rejects_duplicate_invalid_and_unknown_work_packages(self):
        before = (self.project / ".vibe" / "tickets.json").read_bytes()

        status, body = self.request("/api/ticket", {
            "name": "proj", "action": "update", "id": "F99",
            "title": "Neu"})
        self.assertEqual(status, 400, body)

        status, body = self.request("/api/ticket", {
            "name": "proj", "action": "add", "id": "F15",
            "title": "Doppelt"})
        self.assertEqual(status, 400, body)

        status, body = self.request("/api/ticket", {
            "name": "proj", "action": "add", "title": "   "})
        self.assertEqual(status, 400, body)
        self.assertEqual(before, (self.project / ".vibe"
                                  / "tickets.json").read_bytes())

    def test_api_rejects_unknown_action_and_missing_id_without_changing_file(self):
        before = (self.project / ".vibe" / "tickets.json").read_bytes()

        status, body = self.request("/api/ticket", {
            "name": "proj", "action": "foo", "id": "F15"})
        self.assertEqual(status, 400, body)
        self.assertIn("Unbekannte Aktion", body)

        status, body = self.request("/api/ticket", {
            "name": "proj", "action": "delete", "title": "ohne ID"})
        self.assertEqual(status, 400, body)
        self.assertIn("ID fehlt", body)
        self.assertEqual(before, (self.project / ".vibe"
                                  / "tickets.json").read_bytes())

    def test_api_reports_a_bug_as_feedback_of_kind_bug(self):
        status, body = self.request("/api/feedback", {
            "name": "proj", "kind": "bug", "title": "Kaputt"})

        self.assertEqual(status, 200, body)
        # Exakte Meldung: ein Doppelprefix (BB1) muss auffallen.
        self.assertEqual("B1 eingetragen", json.loads(body).get("message"),
                         body)
        self.assertEqual("bug", self.records()["B1"]["type"])

        status, body = self.request("/api/project?name=proj")
        detail = json.loads(body)
        kinds = {entry["id"]: entry["kind"] for entry in detail["feedback"]}
        self.assertEqual("bug", kinds["B1"])

    def test_detail_page_contains_work_package_and_bug_controls(self):
        html = served_page(self.request)

        self.assertIn("ticket-new", html)
        self.assertIn("bug-new", html)
        self.assertIn("Zustand", html)


if __name__ == "__main__":
    unittest.main()
