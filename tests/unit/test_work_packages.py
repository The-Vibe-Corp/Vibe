"""Arbeitspakete: Ticketspeicher, Oberflächen, Web-API, Markerzustände und Wartestatus.

Aufruf: python3 -m unittest tests.unit.test_work_packages -v
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


# ===========================================================================
# Vertragstests für den Ticketspeicher (``bin/vibe_tickets.py``)
# ===========================================================================

import datetime
import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

BIN = REPO / "bin"
STORE_MODULE = BIN / "vibe_tickets.py"

if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

_CACHE = {}


def tickets_module():
    """Lädt ``bin/vibe_tickets.py``; fehlt es, scheitert der Fall sichtbar."""
    if "tickets" not in _CACHE:
        if not STORE_MODULE.is_file():
            raise AssertionError(
                "bin/vibe_tickets.py fehlt (Ticketspeicher-Modul nach GH-48).")
        loader = importlib.machinery.SourceFileLoader(
            "vibe_tickets_gh48_store_under_test", str(STORE_MODULE))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[loader.name] = module
        loader.exec_module(module)
        _CACHE["tickets"] = module
    return _CACHE["tickets"]


class StoreCase(unittest.TestCase):
    """Frisches Projektverzeichnis je Fall; kein Speicher vorhanden."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        self.project.mkdir()
        self.store = self.project / ".vibe" / "tickets.json"

    @property
    def module(self):
        return tickets_module()

    def write_store(self, payload, name="tickets.json"):
        path = self.project / ".vibe" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"
        path.write_text(payload, encoding="utf-8")
        return path

    def read_json(self, path=None):
        path = Path(path or self.store)
        return json.loads(path.read_text(encoding="utf-8"))

    def add(self, **fields):
        fields.setdefault("title", "Titel")
        return self.module.add(self.project, **fields)


class LoadSaveTest(StoreCase):
    """Dateiformat: fehlend -> leer; defekt -> ValueError; Schreiben atomar."""

    def test_a_missing_store_reads_as_an_empty_list(self):
        """Vor: kein .vibe/tickets.json. Aktion: load. Erwartet: []."""
        self.assertEqual([], self.module.load(self.project))

    def test_save_creates_folder_and_document_with_version_and_newline(self):
        """Vor: kein Speicher. Aktion: save mit einem Ticket.
        Erwartet: .vibe/tickets.json wird angelegt, UTF-8, indent=1,
        abschließender Zeilenumbruch, Dokument {"version": 1, "tickets": [...]},
        Umlaute bleiben unescaped (ensure_ascii=False)."""
        record = {"id": "AP1", "title": "Größe prüfen"}

        self.module.save(self.project, [record])

        self.assertTrue(self.store.is_file())
        raw = self.store.read_text(encoding="utf-8")
        self.assertTrue(raw.endswith("\n"), repr(raw[-5:]))
        self.assertIn("Größe", raw, raw)
        self.assertNotIn("\\u00e4", raw, raw)
        document = json.loads(raw)
        self.assertEqual(1, document["version"])
        self.assertEqual(1, len(document["tickets"]))
        self.assertEqual("AP1", document["tickets"][0]["id"])

    def test_load_returns_the_saved_tickets(self):
        """Vor: gespeichertes Ticket. Aktion: load. Erwartet: Ticket mit
        normalisierten Feldern, Reihenfolge bleibt erhalten."""
        self.module.save(self.project, [
            {"id": "B2", "title": "Zweiter", "type": "bug"},
            {"id": "AP1", "title": "Erster"},
        ])

        tickets = self.module.load(self.project)

        self.assertEqual(["B2", "AP1"], [item["id"] for item in tickets])
        self.assertEqual("bug", tickets[0]["type"])

    def test_invalid_json_is_reported_and_never_repaired(self):
        """Vor: Speicher mit defektem JSON. Aktion: load.
        Erwartet: ValueError mit "Ticketspeicher unlesbar" und Pfad; die Datei
        bleibt byte-identisch (kein stilles Reparieren)."""
        broken = '{"version": 1, "tickets": ['
        path = self.write_store(broken)
        before = path.read_bytes()

        with self.assertRaises(ValueError) as caught:
            self.module.load(self.project)

        self.assertIn("Ticketspeicher unlesbar", str(caught.exception))
        self.assertIn(str(path), str(caught.exception))
        self.assertEqual(before, path.read_bytes())

    def test_a_conflicting_write_is_reported_and_preserves_foreign_state(self):
        """Vor: Speicher gelesen (Prüfsumme), danach von außen verändert.
        Aktion: save mit der veralteten Prüfsumme.
        Erwartet: ValueError (Konflikt), fremder Stand bleibt unverändert."""
        path = self.write_store({"version": 1, "tickets": [
            {"id": "AP1", "title": "Alt"}]})
        import vibe_storage

        stale = vibe_storage.read_snapshot(str(path)).digest
        foreign = {"version": 1, "tickets": [{"id": "AP9", "title": "Fremd"}]}
        path.write_text(json.dumps(foreign, ensure_ascii=False), encoding="utf-8")
        before = path.read_bytes()

        with self.assertRaises(ValueError) as caught:
            self.module.save(self.project, [{"id": "AP1", "title": "Neu"}],
                             expected=stale)

        self.assertIn("konflikt", str(caught.exception).lower())
        self.assertEqual(before, path.read_bytes())

    def test_unknown_keys_on_document_and_ticket_level_survive_a_rewrite(self):
        """Vor: Speicher mit Zusatzschlüsseln auf Dokument- und Ticketebene.
        Aktion: load, save. Erwartet: alle unbekannten Schlüssel bleiben
        erhalten (Vorwärtskompatibilität, keine Datenvernichtung)."""
        self.write_store({
            "version": 1,
            "custom_doc": {"team": "a"},
            "tickets": [{"id": "AP1", "title": "Titel", "custom": "bleibt"}],
        })

        tickets = self.module.load(self.project)
        self.module.save(self.project, tickets)

        document = self.read_json()
        self.assertEqual({"team": "a"}, document["custom_doc"])
        self.assertEqual("bleibt", document["tickets"][0]["custom"])

    def test_unknown_fields_of_an_updated_ticket_are_kept(self):
        """Vor: Ticket mit Zusatzfeld. Aktion: update des Titels.
        Erwartet: Zusatzfeld bleibt, Titel ist neu."""
        self.add(tid="AP1", title="Alt", extra={"custom": "bleibt"})

        self.module.update(self.project, "AP1", title="Neu")

        record = self.module.find(self.module.load(self.project), "AP1")
        self.assertEqual("Neu", record["title"])
        self.assertEqual("bleibt", record["custom"])


class NormalizeTest(StoreCase):
    """Feldschema, Defaults und Validierung."""

    def test_defaults_fill_all_contract_fields(self):
        """Vor: minimales Ticket. Aktion: normalize. Erwartet: type=task,
        state=open, description/pr_url/commit/test/blocked_reason/
        waiting_note/priority leer, github=None, dependencies=[]."""
        record = self.module.normalize({"id": "AP7", "title": "Titel"})

        self.assertEqual("task", record["type"])
        self.assertEqual("open", record["state"])
        for field in ("description", "pr_url", "commit", "test",
                      "blocked_reason", "waiting_note", "priority"):
            self.assertEqual("", record[field], field)
        self.assertIsNone(record["github"])
        self.assertEqual([], record["dependencies"])

    def test_id_must_end_with_digits_and_start_with_a_letter(self):
        """Vor: gültige IDs (GH-48, AP7, T-01, B12, F3) und ungültige
        (48, AP, -AP1, "AP 1"). Aktion: normalize.
        Erwartet: gültige werden normalisiert, ungültige lösen ValueError aus."""
        for value in ("GH-48", "AP7", "T-01", "B12", "F3"):
            with self.subTest(valid=value):
                self.assertEqual(value, self.module.normalize(
                    {"id": value, "title": "Titel"})["id"])
        for value in ("48", "AP", "-AP1", "AP 1", ""):
            with self.subTest(invalid=value):
                with self.assertRaises(ValueError):
                    self.module.normalize({"id": value, "title": "Titel"})

    def test_title_is_required_and_single_line(self):
        """Vor: fehlender, leerer und mehrzeiliger Titel. Aktion: normalize.
        Erwartet: ValueError in allen drei Fällen; ein einzeiliger Titel wird
        getrimmt übernommen."""
        for value in ("", "   ", "Zeile 1\nZeile 2", "Zeile 1\rZeile 2"):
            with self.subTest(title=value):
                with self.assertRaises(ValueError):
                    self.module.normalize({"id": "AP1", "title": value})
        with self.assertRaises(ValueError):
            self.module.normalize({"id": "AP1"})
        self.assertEqual("Titel", self.module.normalize(
            {"id": "AP1", "title": "  Titel  "})["title"])

    def test_type_and_state_are_closed_enumerations(self):
        """Vor: alle Vertragswerte und ein Fremdwert je Feld. Aktion: normalize.
        Erwartet: task/bug/feature/feedback und draft/open/in-progress/blocked/
        waiting-merge/done sind gültig; "chore" bzw. "erledigt" nicht."""
        module = self.module
        for value in module.TYPES:
            self.assertEqual(value, module.normalize(
                {"id": "AP1", "title": "T", "type": value})["type"])
        for value in module.STATES:
            self.assertEqual(value, module.normalize(
                {"id": "AP1", "title": "T", "state": value,
                 "commit": "abcdef1", "test": "test_x"}
                if value == "done" else
                {"id": "AP1", "title": "T", "state": value})["state"])
        for field, value in (("type", "chore"), ("state", "erledigt")):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    module.normalize(
                        {"id": "AP1", "title": "T", field: value})

    def test_commit_must_be_a_hex_hash_of_7_to_40_characters(self):
        """Vor: gültige Hex-Hashes (7 und 40 Zeichen) und ungültige
        (6 Zeichen, Nicht-Hex). Aktion: normalize.
        Erwartet: gültige übernommen, ungültige ValueError."""
        module = self.module
        for value in ("abcdef1", "a" * 40):
            self.assertEqual(value, module.normalize(
                {"id": "AP1", "title": "T", "commit": value})["commit"])
        for value in ("abcdef", "ZZZZZZZ", "abcdefg"):
            with self.subTest(commit=value):
                with self.assertRaises(ValueError):
                    module.normalize({"id": "AP1", "title": "T",
                                      "commit": value})

    def test_done_requires_commit_and_test(self):
        """Vor: state=done ohne Nachweis, nur Commit, nur Test, mit beidem.
        Aktion: normalize. Erwartet: die ersten drei Fälle sind ValueError;
        mit Commit und Test ist done gültig (der alte Zustand "ohne Nachweis"
        entfällt)."""
        base = {"id": "AP1", "title": "T", "state": "done"}
        for extra in ({}, {"commit": "abcdef1"}, {"test": "test_x"}):
            with self.subTest(extra=extra):
                with self.assertRaises(ValueError):
                    self.module.normalize(dict(base, **extra))
        record = self.module.normalize(dict(base, commit="abcdef1",
                                            test="test_x"))
        self.assertEqual("done", record["state"])

    def test_priority_is_empty_or_p0_to_p8(self):
        """Vor: "", P0, P8, P9. Aktion: normalize.
        Erwartet: ""/P0/P8 gültig, P9 ValueError."""
        module = self.module
        for value in ("", "P0", "P8"):
            self.assertEqual(value, module.normalize(
                {"id": "AP1", "title": "T", "priority": value})["priority"])
        with self.assertRaises(ValueError):
            module.normalize({"id": "AP1", "title": "T", "priority": "P9"})

    def test_github_is_an_integer_and_dependencies_a_list_of_ids(self):
        """Vor: github=12, dependencies=["AP1","B2"]. Aktion: normalize.
        Erwartet: Werte bleiben; ein ungültiges Abhängigkeitsformat ist
        ValueError."""
        record = self.module.normalize({
            "id": "AP2", "title": "T", "github": 12,
            "dependencies": ["AP1", "B2"]})
        self.assertEqual(12, record["github"])
        self.assertEqual(["AP1", "B2"], record["dependencies"])
        with self.assertRaises(ValueError):
            self.module.normalize({"id": "AP2", "title": "T",
                                   "dependencies": "AP1"})
        with self.assertRaises(ValueError):
            self.module.normalize({"id": "AP2", "title": "T",
                                   "dependencies": ["keine id"]})


class AddUpdateDeleteTest(StoreCase):
    """ID-Vergabe, Zeitstempel, Teilaktualisierung und Nachweisschutz."""

    def test_auto_ids_follow_the_type_prefix(self):
        """Vor: leerer Speicher. Aktion: add task/bug/feedback/feature.
        Erwartet: AP1, B1, F1; ein feature-Ticket ohne eigene ID erhält AP2
        (B1: feature nutzt den AP-Zähler gemeinsam mit task); ein
        feature-Ticket mit eigener ID bleibt erhalten. Die IDs sind
        eindeutig."""
        self.assertEqual("AP1", self.add(type="task")["id"])
        self.assertEqual("B1", self.add(type="bug", title="Bug")["id"])
        self.assertEqual("F1", self.add(type="feedback", title="Idee")["id"])
        self.assertEqual("AP2", self.add(type="feature", title="Feature")["id"])
        self.assertEqual("FEAT-1", self.add(type="feature", tid="FEAT-1",
                                            title="Feature benannt")["id"])
        self.assertEqual(["AP1", "B1", "F1", "AP2", "FEAT-1"],
                         [item["id"] for item in self.module.load(self.project)])

    def test_auto_ids_continue_after_the_highest_number(self):
        """Vor: AP9 existiert. Aktion: add ohne ID (task), danach feature.
        Erwartet: AP10, danach AP11 (nächste freie Nummer über den
        gemeinsamen AP-Zähler; bestehende Lücke füllt nicht)."""
        self.add(tid="AP9", title="Neun")
        self.assertEqual("AP10", self.add(title="Zehn")["id"])
        self.assertEqual("AP11", self.add(type="feature", title="Elf")["id"])

    def test_an_explicit_id_is_validated_and_must_be_unique(self):
        """Vor: Ticket AP1. Aktion: add mit AP1 erneut, add mit ungültiger ID.
        Erwartet: ValueError (existiert bereits / ungültig)."""
        self.add(tid="AP1")
        with self.assertRaises(ValueError):
            self.add(tid="AP1")
        with self.assertRaises(ValueError):
            self.add(tid="keine id")

    def test_gh_prefix_ids_are_reserved_for_issue_imports(self):
        """Vor: leerer Speicher. Aktion: add mit GH-7.
        Erwartet: ValueError — GH-IDs entstehen nur über Sync/verbundene
        Anlage, nicht über die freie Anlage."""
        with self.assertRaises(ValueError):
            self.add(tid="GH-7")

    def test_created_and_updated_are_iso_utc_and_updated_changes(self):
        """Vor: Ticket mit altem updated-Stand. Aktion: update des Titels.
        Erwartet: created bleibt, updated ist ein neuer ISO-8601-UTC-Wert
        (zeitzonenbewusst)."""
        self.write_store({"version": 1, "tickets": [{
            "id": "AP1", "title": "Alt",
            "created": "2000-01-01T00:00:00+00:00",
            "updated": "2000-01-01T00:00:00+00:00"}]})

        self.module.update(self.project, "AP1", title="Neu")

        record = self.module.find(self.module.load(self.project), "AP1")
        self.assertEqual("2000-01-01T00:00:00+00:00", record["created"])
        changed = datetime.datetime.fromisoformat(record["updated"])
        self.assertIsNotNone(changed.tzinfo)
        self.assertGreater(changed.year, 2000)

    def test_update_is_a_partial_update_and_validates(self):
        """Vor: Ticket AP1 offen mit Beschreibung. Aktion: update nur state
        und priority. Erwartet: übrige Felder bleiben, unbekannte ID ist
        ValueError, ungültiger Zustand ist ValueError."""
        self.add(tid="AP1", title="Titel", description="Beschreibung")

        self.module.update(self.project, "AP1", state="in-progress",
                           priority="P2")

        record = self.module.find(self.module.load(self.project), "AP1")
        self.assertEqual("in-progress", record["state"])
        self.assertEqual("P2", record["priority"])
        self.assertEqual("Titel", record["title"])
        self.assertEqual("Beschreibung", record["description"])
        with self.assertRaises(ValueError):
            self.module.update(self.project, "X9", title="Unbekannt")
        with self.assertRaises(ValueError):
            self.module.update(self.project, "AP1", state="erledigt")

    def test_update_refuses_done_without_proof(self):
        """Vor: offenes Ticket. Aktion: update(state="done") ohne Commit/Test.
        Erwartet: ValueError; das Ticket bleibt offen."""
        self.add(tid="AP1")

        with self.assertRaises(ValueError):
            self.module.update(self.project, "AP1", state="done")

        self.assertEqual("open", self.module.find(
            self.module.load(self.project), "AP1")["state"])

    def test_delete_removes_exactly_one_ticket(self):
        """Vor: AP1 und AP2. Aktion: delete AP1. Erwartet: nur AP2 bleibt."""
        self.add(tid="AP1")
        self.add(tid="AP2", title="Zwei")

        self.module.delete(self.project, "AP1")

        self.assertEqual(["AP2"],
                         [item["id"] for item in self.module.load(self.project)])
        with self.assertRaises(ValueError):
            self.module.delete(self.project, "X9")

    def test_done_tickets_are_protected_from_delete_and_editing(self):
        """Vor: erledigtes Ticket mit Commit/Test. Aktion: delete und
        update(Titel/Beschreibung). Erwartet: jeweils ValueError (Nachweis-
        schutz); das Ticket bleibt unverändert erhalten."""
        self.add(tid="AP1", title="Titel", description="Text")
        self.module.update(self.project, "AP1", state="done",
                           commit="abcdef1", test="test_ap1")
        before = self.read_json()

        for action in (
            lambda: self.module.delete(self.project, "AP1"),
            lambda: self.module.update(self.project, "AP1", title="Neu"),
            lambda: self.module.update(self.project, "AP1",
                                       description="Neu"),
        ):
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(before, self.read_json())


class LookupTest(StoreCase):
    """Nachschlagefunktionen und Anzeigezustand."""

    def test_find_and_find_by_github(self):
        """Vor: AP1 (github 5) und AP2. Aktion: find/find_by_github.
        Erwartet: Treffer bzw. None; find_by_github findet die Issuenummer."""
        tickets = [self.module.normalize({"id": "AP1", "title": "T",
                                          "github": 5}),
                   self.module.normalize({"id": "AP2", "title": "U"})]

        self.assertEqual("AP1", self.module.find(tickets, "AP1")["id"])
        self.assertIsNone(self.module.find(tickets, "X9"))
        self.assertEqual("AP1", self.module.find_by_github(tickets, 5)["id"])
        self.assertIsNone(self.module.find_by_github(tickets, 99))

    def test_next_number_uses_the_exact_prefix(self):
        """Vor: AP3, AP7, GH-48, B9. Aktion: next_number.
        Erwartet: AP -> 8, B -> 10, F -> 1 (fremde Präfixe zählen nicht)."""
        tickets = [{"id": value} for value in ("AP3", "AP7", "GH-48", "B9")]
        self.assertEqual(8, self.module.next_number(tickets, "AP"))
        self.assertEqual(10, self.module.next_number(tickets, "B"))
        self.assertEqual(1, self.module.next_number(tickets, "F"))

    def test_display_state_uses_the_known_labels(self):
        """Vor: je Zustand ein Ticket. Aktion: display_state.
        Erwartet: done=erledigt, blocked=BLOCKIERT,
        waiting-merge=WARTET AUF MERGE, in-progress=In Progress, draft=Draft,
        open=offen."""
        expected = {"done": "erledigt", "blocked": "BLOCKIERT",
                    "waiting-merge": "WARTET AUF MERGE",
                    "in-progress": "In Progress", "draft": "Draft",
                    "open": "offen"}
        for state, label in expected.items():
            with self.subTest(state=state):
                self.assertEqual(label, self.module.display_state({"state": state}))


class TicketFileTest(StoreCase):
    """Sichtbare Einzeldatei ``TICKET-<ID>.json`` in der Arbeitskopie."""

    def test_file_name_follows_the_template(self):
        """Vor: Kennung AP7. Aktion: ticket_file_name.
        Erwartet: TICKET-AP7.json."""
        self.assertEqual("TICKET-AP7.json", self.module.ticket_file_name("AP7"))
        self.assertEqual("TICKET-GH-48.json",
                         self.module.ticket_file_name("GH-48"))

    def test_write_and_read_roundtrip(self):
        """Vor: gültiges Ticket. Aktion: write_ticket_file, read_ticket_file.
        Erwartet: gelesenes Ticket entspricht dem normalisierten Ticket."""
        record = self.module.normalize({"id": "AP7", "title": "Titel",
                                        "state": "in-progress"})
        path = self.root / self.module.ticket_file_name("AP7")

        self.module.write_ticket_file(path, record)

        self.assertEqual(record, self.module.read_ticket_file(path))
        self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))

    def test_broken_or_invalid_files_raise_value_error(self):
        """Vor: defektes JSON und JSON ohne Pflichtfelder. Aktion:
        read_ticket_file. Erwartet: ValueError in beiden Fällen."""
        broken = self.root / "TICKET-AP1.json"
        broken.write_text("{", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.module.read_ticket_file(broken)

        missing_title = self.root / "TICKET-AP2.json"
        missing_title.write_text(
            json.dumps({"id": "AP2", "state": "open"}), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.module.read_ticket_file(missing_title)

        bad_state = self.root / "TICKET-AP3.json"
        bad_state.write_text(
            json.dumps({"id": "AP3", "title": "T", "state": "erledigt"}),
            encoding="utf-8")
        with self.assertRaises(ValueError):
            self.module.read_ticket_file(bad_state)


# ===========================================================================
# Vertragstests für die Ticket-/Feedback-Oberflächen in ``bin/vibe``
# ===========================================================================

import importlib.machinery
import importlib.util
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from tests.unit import env_support

FAKE_TOKEN = "gh48-fake-token-4711"

# Variablen, die der GitHub-REST-Fake braucht bzw. die keine echten
# Zugangsdaten oder Proxys in den Test lassen dürfen.
GITHUB_ENV_KEYS = (
    "GITHUB_TOKEN", "GH_TOKEN", "http_proxy", "https_proxy", "all_proxy",
    "VIBE_GITHUB_CREDENTIAL", "GIT_TERMINAL_PROMPT", "NO_PROXY",
)


def load_cli_gh48(vibe_root):
    """Lädt ``bin/vibe`` als Modul mit vollständig temporären Pfaden."""
    with env_support.isolated_process_environment(
        VIBE=str(vibe_root),
        VIBE_NO_CONTAINER="1",
        HOME=str(Path(vibe_root) / "home"),
        VIBE_RUNTIME=str(Path(vibe_root) / "_logs"),
        VIBE_STATE=str(Path(vibe_root) / "_toolchain"),
        VIBE_STORAGE_LOCK_DIR=str(Path(vibe_root) / "locks"),
        VIBE_CONFIG_FILE=str(Path(vibe_root) / "home" / ".config" / "vibe"
                             / "config.json"),
        GITHUB_TOKEN=FAKE_TOKEN,
    ):
        loader = importlib.machinery.SourceFileLoader(
            "vibe_gh48_surface_under_test", str(CLI))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    return module


def ticket(tid, title, type="task", state="open", **extra):
    """Ticketdatensatz mit allen Vertragsfeldern."""
    record = {
        "id": tid, "title": title, "type": type, "state": state,
        "description": "", "github": None, "pr_url": "", "commit": "",
        "test": "", "blocked_reason": "", "waiting_note": "",
        "priority": "", "dependencies": [],
        "created": STAMP, "updated": STAMP,
    }
    record.update(extra)
    return record


def issue(number, title, labels=(), state="open", body="", assignees=(),
          pull_request=None):
    item = {
        "number": number, "title": title, "body": body, "state": state,
        "labels": [{"name": name} for name in labels],
        "assignees": [{"login": name} for name in assignees],
    }
    if pull_request is not None:
        item["pull_request"] = pull_request
    return item


class _IssuesHandler(BaseHTTPRequestHandler):
    """Loopback-REST-Fake für Issues und Pull-Requests."""

    def log_message(self, *args):
        return

    def _record(self, body=b""):
        self.server.requests.append({
            "method": self.command,
            "path": self.path,
            "body": json.loads(body.decode("utf-8")) if body else None,
            "authorization": self.headers.get("Authorization") or "",
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
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = urllib.parse.parse_qs(parsed.query)
        if path.endswith("/issues"):
            items = list(self.server.issues)
            if query.get("state", [""])[0] == "open":
                items = [item for item in items
                         if item.get("state") != "closed"]
            self._respond(200, items)
            return
        if "/issues/" in path:
            number = self._number()
            for item in self.server.issues:
                if item.get("number") == number:
                    self._respond(200, item)
                    return
            self._respond(404, {"message": "Not Found"})
            return
        if path.endswith("/pulls"):
            self._respond(200, [])
            return
        self._respond(404, {"message": "Not Found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        self._record(raw)
        path = urllib.parse.urlparse(self.path).path.rstrip("/")
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if path.endswith("/issues"):
            self.server.next_number += 1
            number = self.server.next_number
            item = {
                "number": number,
                "title": payload.get("title", ""),
                "body": payload.get("body", ""),
                "state": "open",
                "labels": [{"name": name}
                           for name in payload.get("labels") or []],
                "assignees": [{"login": name}
                              for name in payload.get("assignees") or []],
            }
            self.server.issues.append(item)
            self._respond(201, item)
            return
        self._respond(404, {"message": "Not Found"})

    def do_PATCH(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        self._record(raw)
        path = urllib.parse.urlparse(self.path).path.rstrip("/")
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if "/issues/" in path:
            number = self._number()
            for item in self.server.issues:
                if item.get("number") != number:
                    continue
                if "state" in payload:
                    item["state"] = payload["state"]
                if "labels" in payload:
                    item["labels"] = [{"name": name}
                                      for name in payload.get("labels") or []]
                self._respond(200, item)
                return
        self._respond(404, {"message": "Not Found"})


class FakeIssuesServer:
    def __init__(self, issues, next_number=200):
        self.requests = []
        self.issues = [dict(item) for item in issues]
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.port = port
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), _IssuesHandler)
        self.httpd.requests = self.requests
        self.httpd.issues = self.issues
        self.httpd.next_number = next_number
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       daemon=True)

    @property
    def base(self):
        return "http://127.0.0.1:%d" % self.port

    def start(self):
        self.thread.start()
        return self

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    def by_path(self, method, suffix):
        return [item for item in self.requests if item["method"] == method
                and urllib.parse.urlparse(item["path"]).path.rstrip("/")
                .endswith(suffix)]


class SurfaceCase(unittest.TestCase):
    """Temporäres Projekt mit Ticketspeicher; ``bin/vibe`` isoliert geladen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.saved_env = {key: os.environ.get(key) for key in GITHUB_ENV_KEYS}
        self.addCleanup(self.restore_env)
        for key in GITHUB_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ.update({
            "GITHUB_TOKEN": FAKE_TOKEN,
            "GIT_TERMINAL_PROMPT": "0",
            "NO_PROXY": "127.0.0.1,localhost",
        })
        self.root = Path(self.tmp.name)
        (self.root / "home").mkdir()
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        self.env = self.project / ".vibe" / "project.env"
        self.env.write_text("TYPE=generic\n", encoding="utf-8")
        self.store = self.project / ".vibe" / "tickets.json"
        self.cli = load_cli_gh48(self.root)

    def restore_env(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def write_env(self, text):
        self.env.write_text(text, encoding="utf-8")

    def issues_env(self, server):
        self.write_env(
            "TYPE=generic\n"
            'GITHUB_ENABLED="1"\n'
            'GITHUB_REPO="owner/name"\n'
            'GITHUB_API="%s"\n'
            'GITHUB_ISSUES_ENABLED="1"\n' % server.base)

    def write_store(self, tickets):
        self.store.write_text(
            json.dumps({"version": 1, "tickets": tickets},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

    def read_store(self):
        return json.loads(self.store.read_text(encoding="utf-8"))

    def tickets(self):
        return {item["id"]: item for item in self.read_store()["tickets"]}

    def rows(self, function, name="proj"):
        return {row["id"]: row for row in function(name)}


class RowShapeTest(SurfaceCase):
    """Zeilenformen der drei Leseflächen auf dem Speicher."""

    def setUp(self):
        super().setUp()
        self.write_store([
            ticket("AP1", "Offen", priority="P1"),
            ticket("FEAT-2", "Feature", type="feature", state="in-progress"),
            ticket("AP3", "Entwurf", state="draft"),
            ticket("AP4", "Fertig", state="done", commit="abcdef1",
                   test="test_ap4"),
            ticket("B1", "Bug", type="bug", github=12),
            ticket("F1", "Rückmeldung", type="feedback", state="blocked",
                   blocked_reason="wartet"),
        ])

    def test_ticket_items_read_task_and_feature_rows_from_the_store(self):
        """Vor: task/feature/done/bug/feedback im Speicher. Aktion:
        ticket_items. Erwartet: nur task/feature; Zeilenform mit id, title,
        description, state (Anzeigezustand), completed, status, github."""
        rows = self.rows(self.cli.ticket_items)

        self.assertEqual({"AP1", "FEAT-2", "AP3", "AP4"}, set(rows))
        row = rows["FEAT-2"]
        for key in ("id", "title", "description", "state", "completed",
                    "status", "github"):
            self.assertIn(key, row)
        self.assertEqual("In Progress", row["state"])
        self.assertEqual("in-progress", row["status"])
        self.assertFalse(row["completed"])
        self.assertEqual("offen", rows["AP1"]["state"])
        self.assertEqual("Draft", rows["AP3"]["state"])
        self.assertEqual("erledigt", rows["AP4"]["state"])
        self.assertTrue(rows["AP4"]["completed"])

    def test_feedback_items_read_bug_and_feedback_rows_with_kind(self):
        """Vor: Bug B1 und Feedback F1 im Speicher. Aktion: feedback_items.
        Erwartet: beide Zeilen mit kind=bug bzw. feedback; der blockierte
        Zustand erscheint als BLOCKIERT, github bleibt sichtbar."""
        rows = self.rows(self.cli.feedback_items)

        self.assertEqual({"B1", "F1"}, set(rows))
        self.assertEqual("bug", rows["B1"]["kind"])
        self.assertEqual("feedback", rows["F1"]["kind"])
        self.assertEqual(12, rows["B1"]["github"])
        self.assertEqual("BLOCKIERT", rows["F1"]["state"])
        self.assertFalse(rows["F1"]["completed"])

    def test_open_items_list_all_unfinished_tickets_in_store_order(self):
        """Vor: offen/in-progress/draft/blockiert/erledigt. Aktion: open_items.
        Erwartet: alle außer done, in Speicherreihenfolge, je (id, Titel[:60],
        Anzeigezustand)."""
        items = self.cli.open_items("proj")

        self.assertEqual(["AP1", "FEAT-2", "AP3", "B1", "F1"],
                         [item[0] for item in items])
        self.assertEqual(("AP1", "Offen", "offen"), items[0])
        self.assertEqual(("FEAT-2", "Feature", "In Progress"), items[1])
        self.assertEqual(("B1", "Bug", "offen"), items[3])
        self.assertEqual(("F1", "Rückmeldung", "BLOCKIERT"), items[4])


class MissingStoreTest(SurfaceCase):
    """Ohne Ticketspeicher liefern die Leseflächen leere Listen."""

    def test_missing_store_yields_empty_rows(self):
        """Vor: kein Ticketspeicher (kein setUp-Store). Aktion: alle
        Leseflächen. Erwartet: leere Listen statt Fehler (keine
        TICKETS.md-Pflicht)."""
        self.assertFalse(self.store.exists())

        self.assertEqual([], self.cli.ticket_items("proj"))
        self.assertEqual([], self.cli.feedback_items("proj"))
        self.assertEqual([], self.cli.open_items("proj"))


class AddTest(SurfaceCase):
    """Anlegen mit Auto-IDs, Typen und fehlendem Speicher."""

    def test_add_ticket_creates_a_missing_store_with_ap_id(self):
        """Vor: kein Speicher, kein TICKETS.md. Aktion: add_ticket ohne ID.
        Erwartet: AP1, .vibe/tickets.json wird angelegt, Ticket ist task/open."""
        tid = self.cli.add_ticket("proj", "", "Erstes Paket", "Beschreibung")

        self.assertEqual("AP1", tid)
        self.assertTrue(self.store.is_file())
        record = self.tickets()["AP1"]
        self.assertEqual("task", record["type"])
        self.assertEqual("open", record["state"])
        self.assertEqual("Erstes Paket", record["title"])
        self.assertEqual("Beschreibung", record["description"])

    def test_add_ticket_accepts_an_explicit_id_and_continues_auto_ids(self):
        """Vor: AP7 angelegt. Aktion: add_ticket ohne ID.
        Erwartet: eigene ID bleibt, die Auto-ID zählt danach weiter (AP8)."""
        self.assertEqual("AP7", self.cli.add_ticket("proj", "AP7", "Eigen"))
        self.assertEqual("AP8", self.cli.add_ticket("proj", "", "Auto"))

    def test_add_ticket_rejects_duplicate_and_invalid_ids(self):
        """Vor: AP1 existiert. Aktion: AP1 erneut bzw. ungültige ID.
        Erwartet: ValueError jeweils; der Speicher bleibt bei einem Ticket."""
        self.cli.add_ticket("proj", "AP1", "Erstes")
        with self.assertRaises(ValueError):
            self.cli.add_ticket("proj", "AP1", "Doppelt")
        with self.assertRaises(ValueError):
            self.cli.add_ticket("proj", "keine id", "Ungültig")
        self.assertEqual(["AP1"], list(self.tickets()))

    def test_add_feedback_and_add_bug_store_the_distinct_types(self):
        """Vor: leerer Speicher. Aktion: add_feedback, add_bug, add_feedback.
        Erwartet: F1 (feedback), B1 (bug), F2 (feedback)."""
        self.assertEqual("F1", self.cli.add_feedback("proj", "Idee", "Text"))
        self.assertEqual("B1", self.cli.add_bug("proj", "Fehler", "Text"))
        self.assertEqual("F2", self.cli.add_feedback("proj", "Noch eine"))

        records = self.tickets()
        self.assertEqual("feedback", records["F1"]["type"])
        self.assertEqual("bug", records["B1"]["type"])
        self.assertEqual("feedback", records["F2"]["type"])


class EditDeleteTest(SurfaceCase):
    """Bearbeiten/Löschen mit Nachweisschutz und Speicher-Fehlermeldungen."""

    def setUp(self):
        super().setUp()
        self.write_store([
            ticket("AP1", "Offen", description="alt"),
            ticket("AP2", "Fertig", state="done", commit="abcdef1",
                   test="test_ap2"),
            ticket("F1", "Feedback", type="feedback", description="alt"),
            ticket("B1", "Bug", type="bug"),
        ])

    def test_ticket_update_changes_only_title_and_description(self):
        """Vor: offenes AP1. Aktion: ticket_update. Erwartet: Titel und
        Beschreibung neu, Typ/Zustand unverändert."""
        self.cli.ticket_update("proj", "AP1", "Neu", "neu")

        record = self.tickets()["AP1"]
        self.assertEqual("Neu", record["title"])
        self.assertEqual("neu", record["description"])
        self.assertEqual("open", record["state"])
        self.assertEqual("task", record["type"])

    def test_done_tickets_stay_protected_against_edit_and_delete(self):
        """Vor: erledigtes AP2. Aktion: ticket_update und ticket_delete.
        Erwartet: ValueError jeweils, der Speicher bleibt unverändert."""
        before = self.store.read_bytes()

        with self.assertRaises(ValueError):
            self.cli.ticket_update("proj", "AP2", "Neu")
        with self.assertRaises(ValueError):
            self.cli.ticket_delete("proj", "AP2")

        self.assertEqual(before, self.store.read_bytes())

    def test_feedback_update_and_delete_follow_the_same_rules(self):
        """Vor: offenes F1 und offener Bug B1. Aktion: update F1, delete B1.
        Erwartet: F1 neu, B1 entfernt, AP1/AP2 unberührt."""
        self.cli.feedback_update("proj", "F1", "Neu", "neu")
        self.cli.feedback_delete("proj", "B1")

        records = self.tickets()
        self.assertEqual("Neu", records["F1"]["title"])
        self.assertNotIn("B1", records)
        self.assertIn("AP1", records)

    def test_unknown_ticket_reports_the_ticket_store_not_the_legacy_files(self):
        """Vor: kein Ticket X9. Aktion: ticket_update/delete/feedback_update.
        Erwartet: ValueError, dessen Meldung den Ticketspeicher nennt und
        TICKETS.md/FEEDBACK.md nicht mehr adressiert."""
        for action in (
            lambda: self.cli.ticket_update("proj", "X9", "Titel"),
            lambda: self.cli.ticket_delete("proj", "X9"),
            lambda: self.cli.feedback_update("proj", "X9", "Titel"),
        ):
            with self.assertRaises(ValueError) as caught:
                action()
            message = str(caught.exception)
            self.assertIn("Ticketspeicher", message)
            self.assertNotIn("TICKETS.md", message)
            self.assertNotIn("FEEDBACK.md", message)


class GithubSurfaceTest(SurfaceCase):
    """GitHub-Import, -Sync und -Zustand schreiben in den Ticketspeicher."""

    def setUp(self):
        super().setUp()
        self.server = FakeIssuesServer([
            issue(101, "Remote Bug", labels=["bug"], body="Body 101"),
            issue(102, "Remote Aufgabe", labels=["ready"], body="Body 102"),
            issue(104, "Nur PR", pull_request={"url": "x"}),
        ]).start()
        self.addCleanup(self.server.close)
        self.issues_env(self.server)

    def test_legacy_import_entry_points_are_gone(self):
        """GH-47: ``github_issues`` und ``github_issues_import`` entfallen;
        ihre Aufgabe übernimmt der eine Sync (``github_issues_sync``).
        Vor: Projektkontext. Aktion: Attribute von ``bin/vibe`` prüfen.
        Erwartet: beide Legacy-Funktionen fehlen; der Sync bleibt vorhanden.
        Fehlerfall: Altabktionen bleiben erreichbar."""
        self.assertFalse(hasattr(self.cli, "github_issues_import"),
                         "github_issues_import existiert noch")
        self.assertFalse(hasattr(self.cli, "github_issues"),
                         "github_issues existiert noch")
        self.assertTrue(hasattr(self.cli, "github_issues_sync"),
                        "github_issues_sync fehlt")

    def test_sync_pulls_states_and_pushes_open_local_tickets(self):
        """GH-47 (q9a10d0cf6e7f, Option A): fehlende ``gh_text``-Basislinie
        mit unterschiedlichen Texten ist ein Konflikt; die lokale Fassung
        gewinnt und wird gepusht.
        Vor: lokale Tickets AP1 (offen, ohne GitHub), GH-101 (Titel „Alt“,
        offen, kein gh_text) und GH-103 (offen, Issue geschlossen); Remote
        101 trägt „Remote neu“ und in-progress.
        Aktion: github_issues_sync.
        Erwartet: GH-101 behält den lokalen Titel, der Konflikt wird in der
        Meldung gezählt, ein PATCH überträgt den lokalen Titel, der Zustand
        kommt weiterhin aus den Labels (in-progress), GH-103 wird done, AP1
        erhält eine Issuenummer; nichts wird als Markdown geschrieben."""
        self.server.issues[:] = [
            issue(101, "Remote neu", labels=["in-progress"]),
            issue(103, "Remote zu", state="closed"),
        ]
        self.write_store([
            ticket("AP1", "Lokal offen"),
            ticket("GH-101", "Alt", github=101),
            ticket("GH-103", "Alt zu", github=103),
        ])

        ok, message = self.cli.github_issues_sync("proj")

        self.assertTrue(ok, message)
        self.assertRegex(message, r"(?i)konflikt",
                         "Der Konflikt wurde nicht gezählt/gemeldet: " + message)
        records = self.tickets()
        self.assertEqual("Alt", records["GH-101"]["title"])
        self.assertNotEqual("Remote neu", records["GH-101"]["title"])
        self.assertEqual("in-progress", records["GH-101"]["state"])
        self.assertEqual("done", records["GH-103"]["state"])
        self.assertIsNotNone(records["AP1"]["github"])
        patches = self.server.by_path("PATCH", "/issues/101")
        self.assertTrue(any(patch["body"].get("title") == "Alt"
                            for patch in patches),
                        "Der lokale Titel wurde nicht gepusht: " + repr(patches))
        posts = self.server.by_path("POST", "/issues")
        self.assertEqual(["Lokal offen"], [post["body"].get("title")
                                           for post in posts])

    def test_state_action_maps_ready_to_open_and_keeps_draft(self):
        """Vor: GH-101 offen. Aktion: github_issues_state draft, ready,
        in-progress. Erwartet: draft -> draft, ready -> open, in-progress ->
        in-progress; das Issue wird per PATCH aktualisiert."""
        self.write_store([ticket("GH-101", "Titel", github=101)])

        self.cli.github_issues_state("proj", "GH-101", "draft")
        self.assertEqual("draft", self.tickets()["GH-101"]["state"])
        self.cli.github_issues_state("proj", "GH-101", "ready")
        self.assertEqual("open", self.tickets()["GH-101"]["state"])
        self.cli.github_issues_state("proj", "GH-101", "in-progress")
        self.assertEqual("in-progress", self.tickets()["GH-101"]["state"])
        self.assertGreaterEqual(len(self.server.by_path("PATCH", "/issues/101")), 3)
        with self.assertRaises(ValueError):
            self.cli.github_issues_state("proj", "GH-101", "erledigt")


class PackageCloseTest(SurfaceCase):
    """``package_close`` übernimmt den Abschluss ohne Commit-Prüfung."""

    def test_package_close_uses_sync_ticket_without_require_commit(self):
        """Vor: registrierter Worktree, aktive GitHub-Verknüpfung, gemergter
        PR. Aktion: package_close. Erwartet: sync_ticket(..., 
        require_commit=False) wird aufgerufen; der alte sync_proof-Pfad nicht."""
        self.write_env(
            'TYPE=generic\nGITHUB_ENABLED="1"\nGITHUB_REPO="owner/name"\n')
        worktree = self.root / "wt"
        worktree.mkdir()
        if not hasattr(self.cli.vibe_packages, "sync_ticket"):
            raise AssertionError(
                "vibe_packages.sync_ticket fehlt (GH-48: sync-ticket).")

        class Registry:
            def __init__(self, *args, **kwargs):
                pass

            def get(self, project, pid):
                return {"branch": "feature/test/x1",
                        "path": str(worktree)}

            def unregister(self, project, pid):
                return None

        class Sessions:
            def __init__(self, *args, **kwargs):
                pass

            def forget_worktree(self, path):
                return None

        sync_calls = []

        def fake_sync(project, path, pid, require_commit=True):
            sync_calls.append({"project": project, "path": path, "pid": pid,
                               "require_commit": require_commit})
            return True, pid + " übernommen."

        with mock.patch.object(self.cli.vibe_runs, "WorktreeRegistry", Registry), \
                mock.patch.object(self.cli.vibe_runs, "SessionRegistry", Sessions), \
                mock.patch.object(self.cli.vibe_github, "remotes",
                                  return_value=[{"name": "origin"}]), \
                mock.patch.object(
                    self.cli.vibe_github, "merged_pull_request",
                    return_value={"found": True, "merged": True,
                                  "url": "http://example.invalid/pr/1"}), \
                mock.patch.object(self.cli.vibe_github, "pull_integration",
                                  return_value=(True, True, "ok")), \
                mock.patch.object(self.cli.vibe_github, "git",
                                  return_value=(0, "")), \
                mock.patch.object(self.cli.vibe_packages, "sync_ticket",
                                  side_effect=fake_sync) as sync_spy:
            ok, message = self.cli.package_close("proj", "X1")

        self.assertTrue(ok, message)
        self.assertEqual(1, sync_spy.call_count, sync_calls)
        self.assertEqual(1, len(sync_calls), sync_calls)
        self.assertIs(False, sync_calls[0]["require_commit"])
        self.assertEqual("X1", sync_calls[0]["pid"])
        # Der alte Markdown-Nachweispfad ist vertragsgemäß entfernt; es gibt
        # keinen zweiten Abschlussweg neben sync_ticket.
        self.assertFalse(hasattr(self.cli.vibe_packages, "sync_proof"))


# ===========================================================================
# Vertragstests für die Web-API ``/api/ticket`` und ``/api/feedback``
# ===========================================================================

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tests.unit import env_support

FAKE_TOKEN_gh48 = "gh48-web-fake-token"
GITHUB_TOKEN = "gh48-web-github-token"


def api_ticket(tid, title, type="task", state="open", **extra):
    record = {
        "id": tid, "title": title, "type": type, "state": state,
        "description": "", "github": None, "pr_url": "", "commit": "",
        "test": "", "blocked_reason": "", "waiting_note": "",
        "priority": "", "dependencies": [],
        "created": STAMP, "updated": STAMP,
    }
    record.update(extra)
    return record


class ApiIssuesHandler(BaseHTTPRequestHandler):
    """Minimaler Loopback-Fake für die verbundene Ticket-Anlage."""

    def log_message(self, *args):
        return

    def _respond(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._respond(200, [])

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        self.server.requests.append(payload)
        self.server.number += 1
        self._respond(201, {
            "number": self.server.number,
            "title": payload.get("title", ""),
            "body": payload.get("body", ""),
            "state": "open",
            "labels": [{"name": name}
                       for name in payload.get("labels") or []],
            "assignees": [],
        })


class TicketApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        cls.project.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(cls.project)],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(cls.project), "-c", "user.name=Test",
                        "-c", "user.email=test@example.invalid", "commit",
                        "--allow-empty", "-q", "-m", "init"],
                       check=True, capture_output=True)
        (cls.project / ".vibe").mkdir()
        cls.env_path = cls.project / ".vibe" / "project.env"
        cls.store_path = cls.project / ".vibe" / "tickets.json"

        cls.github = ThreadingHTTPServer(("127.0.0.1", 0), ApiIssuesHandler)
        cls.github.requests = []
        cls.github.number = 200
        cls.github_thread = threading.Thread(target=cls.github.serve_forever,
                                             daemon=True)
        cls.github_thread.start()
        cls.github_base = "http://127.0.0.1:%d" % cls.github.server_address[1]

        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.state = cls.root / "_toolchain"
        cls.state.mkdir()
        cls.port = free_port()
        env = env_support.isolated_environ()
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "HOME": str(cls.home),
            "VIBE_STATE": str(cls.state),
            "VIBE_INSTALL": str(cls.state),
            "VIBE_RUNTIME": str(cls.log_dir),
            "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode"
                                   / "agents"),
            "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe"
                                    / "config.json"),
            "GITHUB_TOKEN": GITHUB_TOKEN,
            "NO_PROXY": "127.0.0.1,localhost",
        })
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        token_file = cls.log_dir / "web.token"
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
        cls.base = "http://127.0.0.1:%d" % cls.port

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
        cls.github.shutdown()
        cls.github.server_close()
        cls.github_thread.join(timeout=5)
        cls.tmp.cleanup()

    def setUp(self):
        self.write_env("TYPE=generic\n")
        self.write_store([])
        self.github.requests.clear()
        self.github.number = 200

    # -------------------------------------------------------------- Helfer
    def write_env(self, text):
        self.env_path.write_text(text, encoding="utf-8")

    def issues_env(self):
        self.write_env(
            "TYPE=generic\n"
            'GITHUB_ENABLED="1"\n'
            'GITHUB_REPO="owner/name"\n'
            'GITHUB_API="%s"\n'
            'GITHUB_ISSUES_ENABLED="1"\n' % self.github_base)

    def write_store(self, tickets):
        self.store_path.write_text(
            json.dumps({"version": 1, "tickets": tickets},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

    def read_store(self):
        return {item["id"]: item
                for item in json.loads(self.store_path.read_text(
                    encoding="utf-8"))["tickets"]}

    def request(self, path, body=None, token=True):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.base + path, data=data,
            method="POST" if body is not None else "GET")
        if token:
            request.add_header("X-Token", self.token)
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(
                    response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", "replace")
            try:
                return error.code, json.loads(raw)
            except ValueError:
                return error.code, {"raw": raw}

    def post(self, path, body):
        return self.request(path, body)

    # ------------------------------------------------------------- add
    def test_add_offline_defaults_to_open(self):
        """Vor: kein Speicher, keine GitHub-Verknüpfung. Aktion: POST
        /api/ticket add ohne type/state. Erwartet: ok, AP1 im Speicher,
        state open, type feature (B1: fehlender Typ heißt feature)."""
        status, payload = self.post("/api/ticket", {
            "name": "proj", "action": "add", "title": "Erstes Paket",
            "description": "Text"})

        self.assertEqual(200, status, payload)
        self.assertTrue(payload.get("ok"), payload)
        records = self.read_store()
        self.assertIn("AP1", records)
        self.assertEqual("open", records["AP1"]["state"])
        self.assertEqual("feature", records["AP1"]["type"])
        self.assertEqual("Erstes Paket", records["AP1"]["title"])

    def test_add_accepts_an_optional_state(self):
        """Vor: kein Speicher. Aktion: POST /api/ticket add mit
        state=draft. Erwartet: AP1 ist draft (offline nutzbar)."""
        status, payload = self.post("/api/ticket", {
            "name": "proj", "action": "add", "title": "Entwurf",
            "state": "draft"})

        self.assertEqual(200, status, payload)
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual("draft", self.read_store()["AP1"]["state"])
        self.assertEqual("feature", self.read_store()["AP1"]["type"])

    def test_offline_feature_without_id_gets_an_ap_id_and_ignores_category(self):
        """Vor: kein Speicher, keine GitHub-Verknüpfung. Aktion: add mit
        type=feature, category=bug, ohne ID. Erwartet: AP1 mit type feature –
        die Kategorie hat keinen Einfluss mehr auf die Anlage (B1/E)."""
        status, payload = self.post("/api/ticket", {
            "name": "proj", "action": "add", "title": "Neues Feature",
            "type": "feature", "category": "bug", "state": "draft"})

        self.assertEqual(200, status, payload)
        self.assertTrue(payload.get("ok"), payload)
        records = self.read_store()
        self.assertEqual(["AP1"], list(records))
        self.assertEqual("feature", records["AP1"]["type"])
        self.assertEqual("draft", records["AP1"]["state"])

    def test_offline_unknown_type_is_rejected_without_a_ticket(self):
        """Vor: leerer Speicher. Aktion: POST add mit type=epic.
        Erwartet: ok falsch mit Klartext, kein Ticket entsteht."""
        status, payload = self.post("/api/ticket", {
            "name": "proj", "action": "add", "title": "Unbekannt",
            "type": "epic"})

        self.assertIn(status, (200, 400), payload)
        self.assertFalse(payload.get("ok"), payload)
        message = str(payload.get("message") or "").lower()
        self.assertIn("epic", message, payload)
        self.assertEqual({}, self.read_store())

    def test_feedback_add_creates_bug_and_feedback_types(self):
        """Vor: kein Speicher. Aktion: POST /api/feedback add zweimal
        (kind=bug, ohne kind). Erwartet: B1 type bug, F1 type feedback."""
        first = self.post("/api/feedback", {
            "name": "proj", "action": "add", "title": "Kaputt",
            "kind": "bug"})
        second = self.post("/api/feedback", {
            "name": "proj", "action": "add", "title": "Idee"})

        self.assertTrue(first[1].get("ok"), first)
        self.assertTrue(second[1].get("ok"), second)
        records = self.read_store()
        self.assertEqual("bug", records["B1"]["type"])
        self.assertEqual("feedback", records["F1"]["type"])

    # ------------------------------------------------------------ state
    def test_state_action_allows_draft_open_and_in_progress(self):
        """Vor: AP1 offen. Aktion: state draft -> open -> in-progress.
        Erwartet: jeweils ok und der Speicherzustand folgt."""
        self.write_store([api_ticket("AP1", "Titel")])

        for value in ("draft", "open", "in-progress"):
            status, payload = self.post("/api/ticket", {
                "name": "proj", "action": "state", "id": "AP1",
                "state": value})
            self.assertEqual(200, status, payload)
            self.assertTrue(payload.get("ok"), payload)
            self.assertEqual(value, self.read_store()["AP1"]["state"])

    def test_state_action_rejects_runner_and_github_states(self):
        """Vor: AP1 offen. Aktion: state done/blocked/waiting-merge.
        Erwartet: ok falsch mit Klartext; der Speicher bleibt offen."""
        self.write_store([api_ticket("AP1", "Titel")])

        for value in ("done", "blocked", "waiting-merge"):
            status, payload = self.post("/api/ticket", {
                "name": "proj", "action": "state", "id": "AP1",
                "state": value})
            self.assertIn(status, (200, 400), payload)
            self.assertFalse(payload.get("ok"), payload)
            message = str(payload.get("message") or "")
            self.assertTrue(message.strip())
            self.assertTrue(value in message.lower()
                            or "state" in message.lower()
                            or "zustand" in message.lower(), payload)
            self.assertEqual("open", self.read_store()["AP1"]["state"])

    def test_state_action_rejects_unknown_ticket(self):
        """Vor: leerer Speicher. Aktion: state für X9.
        Erwartet: ok falsch, kein Ticket entsteht."""
        status, payload = self.post("/api/ticket", {
            "name": "proj", "action": "state", "id": "X9",
            "state": "open"})

        self.assertIn(status, (200, 400), payload)
        self.assertFalse(payload.get("ok"), payload)
        message = str(payload.get("message") or "").lower()
        self.assertTrue("x9" in message or "nicht gefunden" in message
                        or "unbekannt" in message, payload)
        self.assertEqual({}, self.read_store())

    # --------------------------------------------------- update/delete
    def test_update_and_delete_open_ticket(self):
        """Vor: AP1 offen. Aktion: update, danach delete.
        Erwartet: Titel geändert, danach ist AP1 entfernt."""
        self.write_store([api_ticket("AP1", "Alt")])

        status, payload = self.post("/api/ticket", {
            "name": "proj", "action": "update", "id": "AP1",
            "title": "Neu", "description": "Text"})
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual("Neu", self.read_store()["AP1"]["title"])

        status, payload = self.post("/api/ticket", {
            "name": "proj", "action": "delete", "id": "AP1"})
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual({}, self.read_store())

    def test_done_ticket_cannot_be_deleted_or_edited_via_the_api(self):
        """Vor: AP2 done mit Nachweis. Aktion: update und delete.
        Erwartet: ok falsch jeweils; das Ticket bleibt unverändert."""
        self.write_store([api_ticket("AP2", "Fertig", state="done",
                                 commit="abcdef1", test="test_ap2")])
        before = self.store_path.read_bytes()

        for body in (
            {"name": "proj", "action": "update", "id": "AP2",
             "title": "Neu"},
            {"name": "proj", "action": "delete", "id": "AP2"},
        ):
            status, payload = self.post("/api/ticket", body)
            self.assertIn(status, (200, 400), payload)
            self.assertFalse(payload.get("ok"), payload)
        self.assertEqual(before, self.store_path.read_bytes())

    # -------------------------------------------------------- verbunden
    def test_connected_add_creates_the_issue_first_and_the_gh_ticket(self):
        """Vor: Issues-Sync aktiv, Loopback-GitHub. Aktion: POST /api/ticket
        add mit type=bug und state=draft. Erwartet: genau ein Issue-POST mit
        Label bug (kein Ready-Label), lokales Ticket GH-201 mit type bug,
        state draft und github 201 (B1/B)."""
        self.issues_env()

        status, payload = self.post("/api/ticket", {
            "name": "proj", "action": "add", "title": "Verbunden",
            "description": "Text", "type": "bug", "state": "draft"})

        self.assertEqual(200, status, payload)
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual(1, len(self.github.requests), self.github.requests)
        issue = self.github.requests[0]
        self.assertEqual(["bug"], issue.get("labels"), issue)
        records = self.read_store()
        self.assertIn("GH-201", records)
        self.assertEqual("bug", records["GH-201"]["type"])
        self.assertEqual("draft", records["GH-201"]["state"])
        self.assertEqual(201, records["GH-201"]["github"])

    def test_connected_add_maps_feature_and_feedback_to_label_and_type(self):
        """Vor: Issues-Sync aktiv, Loopback-GitHub. Aktion: verbundene Anlage
        mit type=feature bzw. type=feedback (jeweils draft). Erwartet: genau
        ein Issue-POST mit dem passenden Label und ohne Ready-Label; das
        lokale GH-Ticket trägt denselben Typ und state draft (B1/B)."""
        self.issues_env()

        cases = (("feature", "Feat"), ("feedback", "Idee"))
        expected_number = 200
        for ttype, title in cases:
            with self.subTest(type=ttype):
                self.write_store([])
                self.github.requests.clear()
                self.github.number = expected_number
                status, payload = self.post("/api/ticket", {
                    "name": "proj", "action": "add", "title": title,
                    "type": ttype, "state": "draft"})
                self.assertEqual(200, status, payload)
                self.assertTrue(payload.get("ok"), payload)
                self.assertEqual(1, len(self.github.requests),
                                 self.github.requests)
                issue = self.github.requests[0]
                self.assertEqual([ttype], issue.get("labels"), issue)
                ticket_id = "GH-" + str(expected_number + 1)
                records = self.read_store()
                self.assertEqual(ttype, records[ticket_id]["type"])
                self.assertEqual("draft", records[ticket_id]["state"])
                expected_number += 1

    def test_connected_add_defaults_to_feature_and_ready_for_open(self):
        """Vor: Issues-Sync aktiv. Aktion: verbundene Anlage ohne type und
        ohne state. Erwartet: Label feature plus Ready-Label (Default state
        open), lokales GH-201 type feature state open (B1/B+E)."""
        self.issues_env()

        status, payload = self.post("/api/ticket", {
            "name": "proj", "action": "add", "title": "Ohne Typ"})

        self.assertEqual(200, status, payload)
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual(1, len(self.github.requests), self.github.requests)
        issue = self.github.requests[0]
        labels = issue.get("labels") or []
        self.assertIn("feature", labels, issue)
        self.assertIn("ready", labels, issue)
        record = self.read_store()["GH-201"]
        self.assertEqual("feature", record["type"])
        self.assertEqual("open", record["state"])

    def test_connected_add_rejects_an_unknown_type(self):
        """Vor: Issues-Sync aktiv. Aktion: verbundene Anlage mit type=epic.
        Erwartet: ok falsch mit Klartext; kein Issue-POST, Speicher
        unverändert (B1/E)."""
        self.issues_env()

        status, payload = self.post("/api/ticket", {
            "name": "proj", "action": "add", "title": "Unbekannt",
            "type": "epic", "state": "draft"})

        self.assertIn(status, (200, 400), payload)
        self.assertFalse(payload.get("ok"), payload)
        self.assertIn("epic", str(payload.get("message") or "").lower(), payload)
        self.assertEqual([], self.github.requests)
        self.assertEqual({}, self.read_store())

    def test_connected_add_accepts_task_without_a_type_label(self):
        """Vor: Issues-Sync aktiv. Aktion: verbundene Anlage mit type=task
        (Bestandskompatibilität, GH-70). Erwartet: kein Typ-Label, aber das
        lokale Ticket behält type task (B1/E)."""
        self.issues_env()

        status, payload = self.post("/api/ticket", {
            "name": "proj", "action": "add", "title": "Altes Paket",
            "type": "task", "state": "draft"})

        self.assertEqual(200, status, payload)
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual(1, len(self.github.requests), self.github.requests)
        issue = self.github.requests[0]
        self.assertEqual([], issue.get("labels") or [], issue)
        record = self.read_store()["GH-201"]
        self.assertEqual("task", record["type"])
        self.assertEqual("draft", record["state"])

    # --------------------------------------------------- project_detail
    def test_project_detail_assigns_tickets_and_feedback(self):
        """Vor: task/feature/bug/feedback im Speicher. Aktion: GET
        /api/project?name=proj. Erwartet: data["tickets"] = task/feature,
        data["feedback"] = bug/feedback mit kind."""
        self.write_store([
            api_ticket("AP1", "Aufgabe"),
            api_ticket("FEAT-2", "Feature", type="feature"),
            api_ticket("B1", "Bug", type="bug"),
            api_ticket("F1", "Feedback", type="feedback"),
        ])

        status, payload = self.request("/api/project?name=proj")

        self.assertEqual(200, status, payload)
        ticket_ids = {row["id"] for row in payload["tickets"]}
        feedback_ids = {row["id"] for row in payload["feedback"]}
        self.assertEqual({"AP1", "FEAT-2"}, ticket_ids)
        self.assertEqual({"B1", "F1"}, feedback_ids)
        kinds = {row["id"]: row.get("kind") for row in payload["feedback"]}
        self.assertEqual("bug", kinds["B1"])
        self.assertEqual("feedback", kinds["F1"])

    # -------------------------------------------------------------- Auth
    def test_new_actions_still_require_the_token(self):
        """Vor: gültiger Speicher. Aktion: POST /api/ticket ohne Token.
        Erwartet: 403; der Speicher bleibt unverändert."""
        self.write_store([api_ticket("AP1", "Titel")])
        before = self.store_path.read_bytes()

        status, _ = self.request("/api/ticket", {
            "name": "proj", "action": "delete", "id": "AP1"}, token=False)

        self.assertEqual(403, status)
        self.assertEqual(before, self.store_path.read_bytes())


# ===========================================================================
# Blockier- und Wartezustände des Läufers im Ticketspeicher
# ===========================================================================

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

PACKAGES = REPO / "bin" / "vibe_packages.py"

WAITING = "WARTET AUF MERGE"


def load_packages():
    loader = importlib.machinery.SourceFileLoader(
        "vibe_packages_b6_states_under_test", str(PACKAGES))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


def load_cli_b6(vibe_root, home):
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


def ticket_record_b6(tid, title, type="task", state="open", **extra):
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
        project = make_project(self.root, [ticket_record_b6(
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
            [ticket_record_b6("B5", "Titel",
                           description="BLOCKIERT: nur Text")],
            env_text='TYPE=generic\nPACKAGE_ORDER="B5"\n')

        view = self.module.priority_view(project)
        by_id = {entry["id"]: entry for entry in view["order"]}

        self.assertEqual("offen", by_id["B5"]["status"])


class MarkCommandsTest(StateCase):
    """``mark_blocked``/``mark_waiting_merge`` schreiben Speicherzustände."""

    def test_mark_blocked_sets_state_and_reason(self):
        """Vor: T1 offen. Aktion: mark_blocked. Erwartet: blocked + Grund."""
        project = make_project(self.root, [ticket_record_b6("T1", "Titel")])

        changed, message = self.module.mark_blocked(project, "T1", "extern")

        self.assertTrue(changed, message)
        record = read_records(project)["T1"]
        self.assertEqual("blocked", record["state"])
        self.assertEqual("extern", record["blocked_reason"])

    def test_mark_blocked_is_idempotent(self):
        """Vor: T1 bereits blocked. Aktion: zweiter Aufruf.
        Erwartet: changed False, Grund bleibt."""
        project = make_project(self.root, [ticket_record_b6(
            "T1", "Titel", state="blocked", blocked_reason="extern")])

        changed, message = self.module.mark_blocked(project, "T1", "neu")

        self.assertFalse(changed, message)
        self.assertEqual("extern", read_records(project)["T1"]["blocked_reason"])

    def test_mark_waiting_sets_note_and_pr_url(self):
        """Vor: T1 offen. Aktion: mark_waiting_merge mit PR-URL.
        Erwartet: waiting-merge, waiting_note und pr_url gesetzt."""
        project = make_project(self.root, [ticket_record_b6("T1", "Titel")])

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
        project = make_project(self.root, [ticket_record_b6("T1", "Titel")])

        result = self.run_cli("mark-blocked", "--project", str(project),
                              "--id", "T1", "--note", "extern")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("blockiert", (result.stdout + result.stderr).lower())
        self.assertEqual("blocked", read_records(project)["T1"]["state"])

    def test_mark_waiting_subcommand_keeps_pr_url(self):
        """Vor: T1 offen. Aktion: mark-waiting mit --pr-url.
        Erwartet: Exit 0, waiting-merge und pr_url im Speicher."""
        project = make_project(self.root, [ticket_record_b6("T1", "Titel")])

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
            ticket_record_b6("T1", "Blockiert", state="blocked",
                          blocked_reason="extern"),
            ticket_record_b6("T2", "Wartet", state="waiting-merge",
                          waiting_note="PR"),
            ticket_record_b6("T3", "Offen"),
            ticket_record_b6("T4", "Fertig", state="done", commit="abcdef1",
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
            ticket_record_b6("T1", "Blockiert", state="blocked",
                          blocked_reason="extern"),
            ticket_record_b6("T2", "Wartet", state="waiting-merge",
                          waiting_note="PR"),
            ticket_record_b6("T3", "Offen"),
        ])

        selected = self.module.select_package(
            project, state_path=str(self.root / "next.json"))

        self.assertEqual("T3", selected["id"])

    def test_priority_view_marks_blocked_and_waiting(self):
        """Vor: PACKAGE_ORDER=T1,T2,T3; T1 blocked, T2 waiting, T3 offen.
        Erwartet: gesperrt / wartet auf Merge / offen; queue beginnt T3."""
        project = make_project(
            self.root,
            [ticket_record_b6("T1", "Blockiert", state="blocked",
                           blocked_reason="extern"),
             ticket_record_b6("T2", "Wartet", state="waiting-merge",
                           waiting_note="PR"),
             ticket_record_b6("T3", "Offen")],
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
        cli = load_cli_b6(workspace, home)
        make_project(workspace, [ticket_record_b6(
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
        cli = load_cli_b6(workspace, home)
        make_project(workspace, [
            ticket_record_b6("T1", "Blockiert", state="blocked",
                          blocked_reason="extern"),
            ticket_record_b6("T2", "Wartet", state="waiting-merge",
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
        cli = load_cli_b6(workspace, home)
        make_project(
            workspace,
            [ticket_record_b6("T1", "Wartet", state="waiting-merge",
                           waiting_note="PR"),
             ticket_record_b6("T2", "Offen")],
            env_text='TYPE=generic\nPACKAGE_ORDER="T1,T2"\n')
        cli._pm.clear()

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            cli.cmd_priority("proj", "list")

        text = output.getvalue()
        lines = [line for line in text.splitlines() if line.startswith("  T1")]
        self.assertTrue(lines, text)
        self.assertRegex(lines[0], r"(?i)wartet auf merge", text)


# ===========================================================================
# 4a/4b: neuer Zustand „WARTET AUF MERGE“ statt BLOCKIERT
# ===========================================================================

import contextlib
import importlib.machinery
import json
import importlib.util
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RUNNER = REPO / "bin" / "vibe-run.sh"
NOVA = REPO / "bin" / "web" / "nova-project.js"
APP_JS = REPO / "bin" / "web" / "app.js"
I18N = REPO / "bin" / "web" / "i18n.js"


def load_packages_ap5():
    """Lädt ``bin/vibe_packages.py`` als eigenes Modul."""
    loader = importlib.machinery.SourceFileLoader(
        "vibe_packages_ap5_waiting_under_test", str(PACKAGES)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


def load_cli_ap5(vibe_root, home):
    """Lädt ``bin/vibe`` als Modul mit isoliertem VIBE und HOME."""
    old = {key: os.environ.get(key) for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_ap5_waiting_cli_under_test", str(CLI)
        )
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


def ticket_record_ap5(tid, title, type="task", state="open", **extra):
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


def make_project_ap5(root, tickets=None, feedback=None, env_text="TYPE=generic\n"):
    """Projekt mit GH-48-Ticketspeicher statt Markdown-Ledgern."""
    project = Path(root) / "proj"
    (project / ".vibe").mkdir(parents=True, exist_ok=True)
    (project / ".vibe" / "project.env").write_text(env_text, encoding="utf-8")
    records = []
    for source in (tickets, feedback):
        if source:
            records.extend(source)
    if records:
        (project / ".vibe" / "tickets.json").write_text(
            json.dumps({"version": 1, "tickets": records},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
    return project


def js_region_waiting(text, marker, fallback=6000):
    start = text.find(marker)
    if start < 0:
        return ""
    end = text.find("\nfunction ", start + len(marker))
    if end < 0:
        end = start + fallback
    return text[start:end]


# GH-48: `is_waiting_merge`/`sync_proof` (Markdown-Marker) sind entfernt.
# Die Zustandssemantik tragen tests/unit/test_gh48_runner_tickets.py und
# tests/unit/test_gh48_ticket_store.py.


class MarkWaitingCommandTest(unittest.TestCase):
    """CLI ``mark-waiting``: Marker, Idempotenz, Ausgabe."""

    @classmethod
    def setUpClass(cls):
        cls.module = load_packages_ap5()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = make_project_ap5(
            self.root,
            tickets=[
                ticket_record_ap5("T1", "Wartet", description="PR offen"),
                ticket_record_ap5("T2", "Offen", description="frei"),
            ],
        )

    def mark_waiting(self, note="PR #6 wartet"):
        return subprocess.run(
            [sys.executable, str(PACKAGES), "mark-waiting",
             "--project", str(self.project), "--id", "T1", "--note", note],
            cwd=str(self.root), stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=60,
        )

    def records(self):
        document = json.loads(
            (self.project / ".vibe" / "tickets.json").read_text(
                encoding="utf-8"))
        return {item["id"]: item for item in document["tickets"]}

    def test_mark_waiting_writes_an_indented_marker_and_reports_waiting(self):
        """Vorbedingung: offenes Paket T1 in TICKETS.md.
        Aktion: ``mark-waiting --id T1 --note …`` ausführen.
        Erwartung: Exit 0; eine eingerückte Zeile
        ``  WARTET AUF MERGE: <note>`` steht im Block T1; die Ausgabe enthält
        „wartend“.
        Fehlerfall: fehlender/falsch platzierter Marker oder stumme Ausgabe.
        """
        result = self.mark_waiting("PR #6 wartet")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("wartet", (result.stdout + result.stderr).lower())
        record = self.records()["T1"]
        self.assertEqual("waiting-merge", record["state"])
        self.assertEqual("PR #6 wartet", record["waiting_note"])

    def test_mark_waiting_is_idempotent(self):
        """Vorbedingung: ``mark-waiting`` lief bereits einmal für T1.
        Aktion: denselben Befehl erneut ausführen.
        Erwartung: Der Marker bleibt genau einmal vorhanden; die Ausgabe nennt
        weiterhin „wartend“.
        Fehlerfall: doppelte Markerzeile oder Fehlerabbruch.
        """
        first = self.mark_waiting()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)

        second = self.mark_waiting()

        output = second.stdout + second.stderr
        self.assertIn("wartet", output.lower())
        self.assertEqual("PR #6 wartet", self.records()["T1"]["waiting_note"])

    def test_mark_waiting_leaves_other_blocks_unchanged(self):
        """Vorbedingung: T1 und T2 offen.
        Aktion: ``mark-waiting`` für T1 ausführen.
        Erwartung: Nur der Block T1 erhält die Marke; T2 bleibt unverändert.
        Fehlerfall: Marke im falschen Block oder Datei-Umschreibung.
        """
        result = self.mark_waiting()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual("T2", list(self.records())[1])
        self.assertEqual("open", self.records()["T2"]["state"])
        self.assertEqual("", self.records()["T2"]["waiting_note"])


class WaitingSelectionAndReportTest(unittest.TestCase):
    """Auswahl, Status und Prioritätsansicht behandeln Wartende wie Gesperrte."""

    @classmethod
    def setUpClass(cls):
        cls.module = load_packages_ap5()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_select_package_skips_a_waiting_package(self):
        """Vorbedingung: T1 wartet auf Merge, T2 ist offen.
        Aktion: ``select_package(project)``.
        Erwartung: T2 wird gewählt; T1 wird nicht erneut gestartet.
        Fehlerfall: Wartendes Paket wird ausgewählt.
        """
        project = make_project_ap5(
            self.root,
            tickets=[
                ticket_record_ap5("T1", "Wartet", state="waiting-merge",
                              waiting_note="PR #6"),
                ticket_record_ap5("T2", "Offen"),
            ],
        )

        selected = self.module.select_package(
            project, state_path=str(self.root / "next.json"))

        self.assertIsNotNone(selected)
        self.assertEqual("T2", selected["id"])

    def test_select_package_with_prefer_reattaches_a_waiting_package(self):
        """Vorbedingung: T1 wartet auf Merge, T2 offen.
        Aktion: ``select_package(project, prefer="T1")``.
        Erwartung: T1 wird ausdrücklich erneut gewählt (Reattach bleibt
        erlaubt).
        Fehlerfall: ``prefer`` wird durch den neuen Zustand wirkungslos.
        """
        project = make_project_ap5(
            self.root,
            tickets=[
                ticket_record_ap5("T1", "Wartet", state="waiting-merge",
                              waiting_note="PR #6"),
                ticket_record_ap5("T2", "Offen"),
            ],
        )

        selected = self.module.select_package(
            project, prefer="T1", state_path=str(self.root / "next.json"))

        self.assertIsNotNone(selected)
        self.assertEqual("T1", selected["id"])

    def test_status_report_lists_waiting_before_open(self):
        """Vorbedingung: T1 wartet, T2 offen, T3 blockiert, T4 trägt beide
        Marker, T5 ist ein Entwurf.
        Aktion: ``status_report(project)``.
        Erwartung: ``waiting`` enthält T1 (nicht ``open``); ``open`` enthält
        nur T2; ``blocked`` enthält T3 und T4 (BLOCKIERT wiegt schwerer);
        ``draft`` enthält T5 (GH-47: Entwürfe sind nicht offen).
        Fehlerfall: Wartende/Entwürfe erscheinen als offen oder verdrängen
        BLOCKIERT.
        """
        project = make_project_ap5(
            self.root,
            tickets=[
                ticket_record_ap5("T1", "Wartet", state="waiting-merge",
                              waiting_note="PR #6"),
                ticket_record_ap5("T2", "Offen"),
                ticket_record_ap5("T3", "Blockiert", state="blocked",
                              blocked_reason="extern"),
                ticket_record_ap5("T4", "Beides", state="blocked",
                              waiting_note="PR #7",
                              blocked_reason="extern"),
                ticket_record_ap5("T5", "Entwurf", state="draft"),
            ],
        )

        report = self.module.status_report(project)

        self.assertIn("waiting", report, report)
        self.assertIn("draft", report, report)
        self.assertEqual(["T1"], report["waiting"])
        self.assertEqual(["T2"], report["open"])
        self.assertEqual(["T5"], report["draft"])
        self.assertIn("T3", report["blocked"])
        self.assertIn("T4", report["blocked"])
        self.assertNotIn("T1", report["open"])
        self.assertNotIn("T5", report["open"])

    def test_priority_view_marks_waiting_in_order_and_standard(self):
        """Vorbedingung: ``PACKAGE_ORDER="T1,T2"``; T1 wartet, T2 offen.
        Aktion: ``priority_view(project)``.
        Erwartung: ``order`` zeigt für T1 „wartet auf Merge“, ``standard``
        ebenfalls; ``queue`` beginnt mit T2 (T1 ist nicht bereit).
        Fehlerfall: Wartende gelten als offen oder fehlen in der Ansicht.
        """
        project = make_project_ap5(
            self.root,
            tickets=[
                ticket_record_ap5("T1", "Wartet", state="waiting-merge",
                              waiting_note="PR #6"),
                ticket_record_ap5("T2", "Offen"),
            ],
            env_text='TYPE=generic\nPACKAGE_ORDER="T1,T2"\n',
        )

        view = self.module.priority_view(project)

        by_id = {entry["id"]: entry for entry in view["order"]}
        self.assertEqual("wartet auf Merge", by_id["T1"]["status"])
        standard = {entry["id"]: entry for entry in view["standard"]}
        self.assertEqual("wartet auf Merge", standard["T1"]["status"])
        self.assertEqual("T2", view["queue"][0]["id"])
        self.assertNotIn("T1", [item["id"] for item in view["queue"]])


class TicketStatusWaitingTest(unittest.TestCase):
    """``bin/vibe``: Ticket-Status WARTET AUF MERGE, BLOCKIERT hat Vorrang."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.workspace = self.base / "ws"
        self.workspace.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.cli = load_cli_ap5(self.workspace, self.home)

    def project(self, tickets=None, feedback=None):
        project = make_project_ap5(self.workspace, tickets=tickets, feedback=feedback)
        self.cli._pm.clear()
        return project

    def test_open_items_marks_waiting_tickets(self):
        """Vorbedingung: TICKETS.md enthält T1 mit WARTET-Marker (offen).
        Aktion: ``open_items("proj")``.
        Erwartung: T1 erscheint mit Status „WARTET AUF MERGE“.
        Fehlerfall: Status bleibt „offen“ oder Eintrag fehlt.
        """
        self.project(tickets=[
            ticket_record_ap5("T1", "Wartet", state="waiting-merge",
                          waiting_note="PR #6")])

        items = self.cli.open_items("proj")

        self.assertIn(("T1", "Wartet", WAITING), items, items)

    def test_open_items_shows_waiting_feedback(self):
        """Vorbedingung: FEEDBACK.md enthält F1 mit WARTET-Marker (offen).
        Aktion: ``open_items("proj")``.
        Erwartung: F1 erscheint mit Status „WARTET AUF MERGE“.
        Fehlerfall: Feedback wartet still weiter als offen oder als erledigt.
        """
        self.project(feedback=[
            ticket_record_ap5("F1", "Wartet", type="feedback",
                          state="waiting-merge", waiting_note="PR #8")])

        items = self.cli.open_items("proj")

        self.assertIn(("F1", "Wartet", WAITING), items, items)

    def test_done_wins_over_a_stale_waiting_note(self):
        """Vorbedingung: erledigtes Ticket mit altem waiting_note.
        Aktion: ``open_items``/``ticket_items``.
        Erwartung: Es gilt der Zustand done (erledigt), nicht der Wartevermerk.
        Fehlerfall: Ein Wartefeld überdeckt den Abschluss."""
        self.project(tickets=[
            ticket_record_ap5("T1", "Beides", state="done", commit="abcdef1",
                          test="test_t1", waiting_note="PR #6")])

        items = self.cli.open_items("proj")
        rows = self.cli.ticket_items("proj")

        self.assertEqual([], items)
        self.assertEqual("erledigt", rows[0]["state"])

    def test_waiting_ticket_keeps_its_description(self):
        """Vorbedingung: wartendes Ticket mit Beschreibung.
        Aktion: ``ticket_items``.
        Erwartung: state „WARTET AUF MERGE", Beschreibung unverändert.
        Fehlerfall: Zustandsfelder landen in der Beschreibung."""
        self.project(tickets=[
            ticket_record_ap5("T1", "Titel", state="waiting-merge",
                          waiting_note="PR #6",
                          description="Bitte warten.")])

        rows = self.cli.ticket_items("proj")

        self.assertEqual("WARTET AUF MERGE", rows[0]["state"])
        self.assertEqual("Bitte warten.", rows[0]["description"])


class PriorityCommandWaitingTest(unittest.TestCase):
    """``vibe priority <projekt> list`` nennt wartende Pakete in der Liste."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.workspace = self.base / "ws"
        self.workspace.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.cli = load_cli_ap5(self.workspace, self.home)

    def test_priority_list_names_a_waiting_package(self):
        """Vorbedingung: ``PACKAGE_ORDER="T1,T2"``; T1 wartet auf Merge, T2
        ist offen.
        Aktion: ``cmd_priority("proj", "list")`` mit eingefangenem stdout.
        Erwartung: Die Ausgabezeile zu T1 nennt „wartet auf Merge“.
        Fehlerfall: Wartende Pakete erscheinen in der Priorisierungsliste ohne
        Zusatz und sind von offenen nicht zu unterscheiden.
        """
        make_project_ap5(
            self.workspace,
            tickets=[
                ticket_record_ap5("T1", "Wartet", state="waiting-merge",
                              waiting_note="PR #6"),
                ticket_record_ap5("T2", "Offen"),
            ],
            env_text='TYPE=generic\nPACKAGE_ORDER="T1,T2"\n',
        )
        self.cli._pm.clear()

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.cli.cmd_priority("proj", "list")

        text = output.getvalue()
        lines = [line for line in text.splitlines() if line.startswith("  T1")]
        self.assertTrue(lines, text)
        self.assertRegex(lines[0], r"(?i)wartet auf merge", text)


class RunnerWiringTest(unittest.TestCase):
    """Der PR-only-Rückfall ruft ``mark-waiting`` statt ``mark-blocked`` auf."""

    def shell_function(self, text, marker):
        start = text.find(marker)
        if start < 0:
            return ""
        end = text.find("\n}", start)
        return text[start:end + 2] if end >= 0 else text[start:start + 2000]

    def test_pr_only_fallback_uses_mark_waiting_and_keeps_the_log_line(self):
        """Vorbedingung: Quelltext ``bin/vibe-run.sh``.
        Aktion: Funktion ``pr_only_fallback`` ausschneiden.
        Erwartung: Sie ruft ``mark-waiting`` auf, nicht ``mark-blocked``; die
        Logzeile „WARTET AUF MERGE“ bleibt.
        Fehlerfall: Läufer schreibt weiterhin BLOCKIERT statt Wartend.
        """
        text = RUNNER.read_text(encoding="utf-8")
        region = self.shell_function(text, "pr_only_fallback() {")
        self.assertTrue(region, "pr_only_fallback nicht gefunden")
        self.assertIn(WAITING, region, region)
        self.assertIn("mark-waiting", region, region)
        self.assertNotIn("mark-blocked", region, region)


class NovaWaitingSurfaceTest(unittest.TestCase):
    """Nova-Oberfläche: eigene wartende Spalte, Kachel, Aktion, gelbe Pille."""

    def setUp(self):
        self.text = NOVA.read_text(encoding="utf-8")

    def test_nova_maps_waiting_to_its_label_and_warning_pill(self):
        """Vorbedingung: ``nova-project.js``.
        Aktion: ``nvpStateLabel`` und die Zustands-Pille der Karte pruefen.
        Erwartung (F34): „WARTET AUF MERGE“ wird mit „Wartet auf Merge“
        beschriftet und an der Karte als gelbe Pille ``nv-warn`` dargestellt;
        eine eigene Board-Spalte existiert nicht mehr.
        Fehlerfall: Wartende erscheinen wie offen oder ohne Warnfarbe.
        """
        label = js_region_waiting(self.text, "function nvpStateLabel(")
        card = js_region_waiting(self.text, "function nvpTicketCard(")

        self.assertTrue(label, "nvpStateLabel nicht gefunden")
        self.assertTrue(card, "nvpTicketCard nicht gefunden")
        self.assertIn(WAITING, label)
        self.assertIn("Wartet auf Merge", label)
        self.assertIn(WAITING, card)
        self.assertIn("nv-warn", card)
        self.assertNotIn("nvpStateColumn", self.text,
                         "Die entfernte Board-Spaltenabbildung existiert noch")

    def test_nova_integrated_list_replaces_the_board_columns(self):
        """Vorbedingung: Arbeit-Aufbau in ``nova-project.js``.
        Aktion: Liste, Karten und Board-Abwesenheit pruefen.
        Erwartung (F34): Die Arbeit ist die integrierte Liste
        ``div.nv-ticket-list[data-nv-ticket-list]``; alle Eintraege laufen
        durch ``nvpTicketCard``, damit wartende Pakete in der Liste
        erscheinen. Die fruehere Spaltenreihenfolge (``open``, ``progress``,
        ``draft``, ``waiting``, ``blocked``, ``proof``, ``done``) und
        ``.nv-board`` existieren nicht mehr.
        Fehlerfall: Spalte fehlt, steht an falscher Stelle oder das Board
        besteht weiter.
        """
        work = js_region_waiting(self.text, "var ticketList = el('div'")
        self.assertTrue(work, "Integrierte Arbeitsliste nicht gefunden")
        self.assertIn("data-nv-ticket-list", work)
        self.assertIn("nvpTicketCard", work)
        self.assertIn("allItems.forEach", work)
        self.assertNotIn(".nv-board", self.text)
        self.assertNotIn("nvpBoardColumn", self.text)
        self.assertNotRegex(
            self.text,
            r"\[\s*'open'\s*,\s*'progress'\s*,\s*'draft'\s*,\s*'waiting'"
            r"\s*,\s*'blocked'\s*,\s*'proof'\s*,\s*'done'\s*\]",
            "Die entfernte Board-Spaltenfolge existiert noch",
        )

    def test_nova_overview_counts_waiting_packages(self):
        """Vorbedingung: Übersichts-Kacheln in ``nova-project.js``.
        Aktion: Kacheldefinitionen prüfen.
        Erwartung: Eine Kachel ``waiting`` zählt Pakete mit „WARTET AUF
        MERGE“ und ist mit „Wartet auf Merge“ beschriftet.
        Fehlerfall: Wartende werden in der Übersicht nicht gezählt.
        """
        self.assertIn("'waiting'", self.text)
        self.assertRegex(
            self.text,
            r"\['waiting'[^\]]*nvpCount\([^)]*" + WAITING,
            "Keine Wartend-Kachel",
        )
        self.assertIn("Wartet auf Merge", self.text)

    def test_nova_offers_package_close_for_blocked_and_waiting_packages(self):
        """Vorbedingung: ``nvpOpenTicketDetail`` in ``nova-project.js``.
        Aktion: Bedingung fuer den Abschluss-Button im Kontext-Panel pruefen.
        Erwartung (F34): Der Button erscheint bei ``BLOCKIERT`` und bei
        ``WARTET AUF MERGE``, aber nur fuer Pakete (nicht fuer Feedback).
        Fehlerfall: Wartende Pakete lassen sich nicht ueber die GUI schliessen.
        """
        region = js_region_waiting(self.text, "function nvpOpenTicketDetail(")
        self.assertTrue(region, "nvpOpenTicketDetail nicht gefunden")
        condition = (
            r"row\.state\s*===\s*'BLOCKIERT'[\s\S]{0,200}"
            r"row\.state\s*===\s*'WARTET AUF MERGE'"
            r"|row\.state\s*===\s*'WARTET AUF MERGE'[\s\S]{0,200}"
            r"row\.state\s*===\s*'BLOCKIERT'"
            r"|\[\s*'BLOCKIERT'\s*,\s*'WARTET AUF MERGE'\s*\]\.includes\("
        )
        self.assertRegex(region, condition)
        self.assertIn("kind === 'package'", region)
        self.assertIn("package-close", region)

    def test_nova_waiting_pill_uses_the_warning_colors(self):
        """Vorbedingung: Status-Pille für Wartende in ``nova-project.js``.
        Aktion: Zuordnung von „WARTET AUF MERGE“ zu einer CSS-Klasse prüfen.
        Erwartung: Wartende erhalten ``nv-warn`` (gelb).
        Fehlerfall: Wartende erscheinen wie blockiert oder ohne Farbe.
        """
        self.assertRegex(
            self.text,
            WAITING + r"[\s\S]{0,400}nv-warn|nv-warn[\s\S]{0,400}" + WAITING,
            "Keine gelbe Pille für WARTET AUF MERGE",
        )

    def test_english_translation_names_waiting_for_merge(self):
        """Vorbedingung: ``bin/web/i18n.js``.
        Aktion: Wörterbuch prüfen.
        Erwartung: ``"Wartet auf Merge": "Waiting for merge"``.
        Fehlerfall: Englische Oberfläche zeigt den deutschen Text.
        """
        text = I18N.read_text(encoding="utf-8")

        self.assertIn('"Wartet auf Merge"', text)
        self.assertRegex(
            text, r'"Wartet auf Merge"\s*:\s*"Waiting for merge"',
            "Englische Übersetzung fehlt",
        )

    def test_german_dictionary_keeps_the_status_label(self):
        """Vorbedingung: ``bin/web/i18n.js`` mit den Blöcken ``DICTS.en`` und
        ``DICTS.de``.
        Aktion: Nur den ``de``-Bereich ab ``de: {`` prüfen.
        Erwartung: ``DICTS.de`` enthält das Identitätspaar
        ``"Wartet auf Merge": "Wartet auf Merge"``; der ``en``-Eintrag
        („Waiting for merge“) bleibt davon unberührt.
        Fehlerfall: ``tr('Wartet auf Merge')`` fällt bei deutscher Oberfläche
        auf den englischen Default zurück.
        """
        text = I18N.read_text(encoding="utf-8")
        marker = "    de: {"
        self.assertIn(marker, text, "DICTS.de nicht gefunden")
        de_region = text[text.index(marker):]

        self.assertRegex(
            de_region,
            r'"Wartet auf Merge"\s*:\s*"Wartet auf Merge"',
            "Deutsches Identitätspaar fehlt in DICTS.de",
        )
        self.assertRegex(
            text[:text.index(marker)],
            r'"Wartet auf Merge"\s*:\s*"Waiting for merge"',
            "Englischer Eintrag muss unverändert bleiben",
        )


class ClassicWaitingSurfaceTest(unittest.TestCase):
    """Klassische Oberfläche: Wartend gelb, BLOCKIERT bleibt rot."""

    def test_classic_ticket_pill_marks_waiting_as_warning(self):
        """Vorbedingung: Statusklassen-Zuordnung in ``bin/web/app.js``.
        Aktion: Zuordnung prüfen.
        Erwartung: „WARTET AUF MERGE“ wird der Klasse ``warn`` zugeordnet;
        BLOCKIERT bleibt ``bad``.
        Fehlerfall: Wartende erscheinen rot wie blockiert.
        """
        text = APP_JS.read_text(encoding="utf-8")

        self.assertRegex(text, WAITING + r"[\s\S]{0,400}warn",
                         "Keine warn-Klasse für WARTET AUF MERGE")
        self.assertRegex(text, r"BLOCKIERT[\s\S]{0,120}bad",
                         "BLOCKIERT muss weiterhin bad bleiben")


# ===========================================================================
# (neu vergeben): Abgeschlossene Pakete mit zitierten Markern
# ===========================================================================

import importlib.machinery
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


BLOCKED = "BLOCKIERT"
DONE = "erledigt"
CLOSE_LABEL = "Paket abschließen"


# --------------------------------------------------------------------------
# Ladepfade und Fixtures
# --------------------------------------------------------------------------
def load_packages_b3():
    """Lädt ``bin/vibe_packages.py`` als eigenes Modul."""
    loader = importlib.machinery.SourceFileLoader(
        "vibe_packages_b3_merged_waiting_under_test", str(PACKAGES)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


def load_cli_b3(vibe_root, home):
    """Lädt ``bin/vibe`` als Modul mit isoliertem VIBE und HOME."""
    old = {key: os.environ.get(key)
           for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_b3_merged_waiting_cli_under_test", str(CLI)
        )
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


def init_git_repo(path):
    """Legt ein Repository mit einem echten Commit an; liefert den Kurzhash.

    ``proof_ok`` prüft den Commit mit ``git cat-file`` im Projektordner; ohne
    ein echtes Repository wäre jeder Nachweis ungültig und die
    Erledigt-Erkennung ließe sich nicht von der Marker-Erkennung trennen.
    """
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "init",
        ],
        cwd=str(path),
        check=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(path),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def make_project_b3(root, tickets="", feedback="", env_text="TYPE=generic\n"):
    """Temporäres Projekt mit TICKETS.md und FEEDBACK.md.

    Das Projekt liegt unter einem vom Test angelegten Git-Repository; der
    Commit-Hash muss deshalb vor dem Schreiben der Blöcke bekannt sein und
    wird von den Tests über ``self.commit`` eingesetzt.
    """
    project = Path(root) / "proj"
    (project / ".vibe").mkdir(parents=True)
    (project / ".vibe" / "project.env").write_text(env_text, encoding="utf-8")
    (project / "TICKETS.md").write_text(
        "# TICKETS\n\n" + tickets, encoding="utf-8")
    (project / "FEEDBACK.md").write_text(
        "# FEEDBACK\n\n" + feedback, encoding="utf-8")
    return project


def js_region_package_close(text, marker, fallback=6000):
    """Schneidet den Quelltextabschnitt ab ``marker`` bis zur nächsten
    Top-Level-Funktion; ohne Treffer einen leeren String."""
    start = text.find(marker)
    if start < 0:
        return ""
    end = text.find("\nfunction ", start + len(marker))
    if end < 0:
        end = start + fallback
    return text[start:end]


def proof_line(commit, name="test_b3_merged_waiting.py"):
    """Nachweiszeile im Projektformat: Commit plus Test."""
    return "  Commit: %s; Test: tests/unit/%s\n" % (commit, name)


# --------------------------------------------------------------------------
# AK1/AK2/AK3: ``bin/vibe`` — _parse_entry
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# GH-48: Die Markdown-Marker- und „erledigt hat Vorrang“-Fälle des alten
# Textparsers entfallen. Zustände (auch blocked/waiting-merge) sind
# Speicherfelder; die Aussagen (Anzeige, Statusbericht, Prioritätsansicht,
# Auswahl) tragen tests/unit/test_gh48_runner_tickets.py und
# tests/unit/test_gh48_ticket_store.py. Die weiterhin gültige
# Oberflächenprüfung für „Paket abschließen“ bleibt hier erhalten.
# --------------------------------------------------------------------------


# AK5: klassische Oberfläche — „Paket abschließen“
# --------------------------------------------------------------------------
class ClassicGuiPackageCloseTest(unittest.TestCase):
    """AK5: ``app.js`` bietet den Abschluss-Button nur passenden Paketen."""

    def setUp(self):
        self.text = APP_JS.read_text(encoding="utf-8")
        self.tickets = js_region_package_close(self.text, "function ticketCard(")
        self.feedback = js_region_package_close(self.text, "function feedbackCard(")

    def test_classic_ticket_card_offers_package_close_button(self):
        """AK5. Vorbedingung: ``bin/web/app.js``, Funktion ``ticketCard``.
        Aktion: Quelltext der Ticketkarte prüfen.
        Erwartung: Sie enthält den Button „Paket abschließen“.
        Fehlerfall: In der klassischen Oberfläche fehlt der Abschluss-Button.
        """
        self.assertTrue(self.tickets, "ticketCard nicht gefunden")
        self.assertIn(CLOSE_LABEL, self.tickets)

    def test_classic_package_close_posts_to_the_package_endpoint(self):
        """AK5. Vorbedingung: Abschluss-Button in ``ticketCard``.
        Aktion: Aufruf von ``/api/package`` prüfen.
        Erwartung: Der Aufruf sendet ``name``, ``id`` und
        ``action: 'close'``.
        Fehlerfall: Der Button ruft einen falschen Endpunkt oder ohne ID auf.
        """
        call = re.search(
            r"api\(\s*['\"]/api/package['\"]\s*,\s*\{([^}]*)\}",
            self.tickets,
        )
        self.assertIsNotNone(
            call, "Kein api('/api/package', …)-Aufruf in ticketCard")
        arguments = call.group(1)
        self.assertIn("name", arguments, call.group(0))
        self.assertRegex(arguments, r"id\s*:\s*i\.id|id\b",
                         call.group(0))
        self.assertRegex(arguments, r"action\s*:\s*['\"]close['\"]",
                         call.group(0))

    def test_classic_package_close_is_limited_to_blocked_and_waiting_tickets(self):
        """AK5. Vorbedingung: ``ticketCard`` in ``app.js``.
        Aktion: Bedingung für den Abschluss-Button prüfen.
        Erwartung: Der Button ist an die Zustände ``BLOCKIERT`` und
        ``WARTET AUF MERGE`` gebunden (echte ``i.state``-Prüfung); damit
        erscheint er nicht für ``offen``, ``ohne Nachweis`` oder ``erledigt``.
        Fehlerfall: Der Button erscheint bei jedem Paket oder fehlt bei
        wartenden Paketen.
        """
        conditions = (
            r"i\.state\s*===?\s*['\"]BLOCKIERT['\"][\s\S]{0,200}"
            r"i\.state\s*===?\s*['\"]WARTET AUF MERGE['\"]",
            r"i\.state\s*===?\s*['\"]WARTET AUF MERGE['\"][\s\S]{0,200}"
            r"i\.state\s*===?\s*['\"]BLOCKIERT['\"]",
            r"\[\s*['\"]BLOCKIERT['\"]\s*,\s*['\"]WARTET AUF MERGE['\"]\s*\]"
            r"\.includes\(\s*i\.state\s*\)",
            r"\[\s*['\"]WARTET AUF MERGE['\"]\s*,\s*['\"]BLOCKIERT['\"]\s*\]"
            r"\.includes\(\s*i\.state\s*\)",
        )
        self.assertTrue(
            any(re.search(pattern, self.tickets) for pattern in conditions),
            "Keine Zustandsbindung an BLOCKIERT und WARTET AUF MERGE:\n"
            + self.tickets,
        )

    def test_classic_package_close_reports_backend_message_and_refreshes(self):
        """AK5. Vorbedingung: Abschluss-Button in ``ticketCard``.
        Aktion: Erfolgs-/Fehlerbehandlung um den Button prüfen.
        Erwartung: Die Backend-Meldung wird per ``toast`` gezeigt und die
        Projektansicht bei Erfolg über ``detail(name)`` neu geladen.
        Fehlerfall: Fehler bleiben unsichtbar oder die Ansicht bleibt veraltet.
        """
        position = self.tickets.find(CLOSE_LABEL)
        self.assertGreaterEqual(position, 0, "Abschluss-Button fehlt")
        window = self.tickets[max(0, position - 800):position + 300]
        self.assertIn("/api/package", window)
        self.assertIn("toast", window)
        self.assertIn("message", window)
        self.assertIn("detail(name)", window)

    def test_classic_feedback_card_offers_no_package_close(self):
        """AK5. Vorbedingung: ``feedbackCard`` in ``app.js``.
        Aktion: Quelltext der Feedback-Karte prüfen.
        Erwartung: Kein „Paket abschließen“-Button und kein
        ``/api/package``-Aufruf.
        Fehlerfall: Feedback ließe sich fälschlich als Paket abschließen.
        """
        self.assertTrue(self.feedback, "feedbackCard nicht gefunden")
        self.assertNotIn(CLOSE_LABEL, self.feedback)
        self.assertNotIn("/api/package", self.feedback)


# --------------------------------------------------------------------------
# AK6: i18n
# --------------------------------------------------------------------------
class I18nPackageCloseTest(unittest.TestCase):
    """AK6: englische Übersetzung und deutsches Identitätspaar."""

    def setUp(self):
        self.text = I18N.read_text(encoding="utf-8")
        self.marker = "    de: {"
        self.assertIn(self.marker, self.text, "DICTS.de nicht gefunden")
        split = self.text.index(self.marker)
        self.en_region = self.text[:split]
        self.de_region = self.text[split:]

    def test_english_dictionary_translates_package_close(self):
        """AK6. Vorbedingung: ``bin/web/i18n.js`` mit ``DICTS.en``.
        Aktion: Eintrag für „Paket abschließen“ im englischen Bereich suchen.
        Erwartung: Ein nichtleerer englischer Wert, der „package“ nennt und
        nicht der deutsche Schlüssel ist.
        Fehlerfall: ``tr('Paket abschließen')`` fällt in der englischen
        Oberfläche auf den deutschen Text zurück.
        """
        match = re.search(
            r'"Paket abschließen"\s*:\s*"([^"]*)"', self.en_region)
        self.assertIsNotNone(match, "Kein englischer Eintrag")
        value = match.group(1).strip()
        self.assertTrue(value, "Englischer Eintrag ist leer")
        self.assertNotEqual(value, CLOSE_LABEL,
                            "Englischer Eintrag ist nur der Schlüssel")
        self.assertRegex(value, r"(?i)package",
                         "Englischer Eintrag nennt kein Paket: " + value)

    def test_german_dictionary_keeps_package_close_identity(self):
        """AK6. Vorbedingung: ``bin/web/i18n.js`` mit ``DICTS.de``.
        Aktion: Nur den ``de``-Bereich ab ``de: {`` prüfen.
        Erwartung: Identitätspaar
        ``"Paket abschließen": "Paket abschließen"``.
        Fehlerfall: Die deutsche Oberfläche zeigt einen englischen Default.
        """
        self.assertRegex(
            self.de_region,
            r'"Paket abschließen"\s*:\s*"Paket abschließen"',
            "Deutsches Identitätspaar fehlt in DICTS.de",
        )


if __name__ == "__main__":
    unittest.main()
