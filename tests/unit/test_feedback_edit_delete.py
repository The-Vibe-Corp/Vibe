"""Tests für das Bearbeiten und Löschen vorhandener Feedback-Punkte (F2).

Geprüft werden das Markdown-Modell (Parsen, Ändern, Löschen), die HTTP-API des
Dashboards und die tatsächlich ausgelieferte Projektdetail-Seite. Die
Markdown-Funktionen arbeiten auf echten Dateien in einem temporären
Arbeitsbereich; die API-Tests starten bin/vibe-web.py auf einem eigenen Port.
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

from tests.unit import env_support
from tests.unit.web_page import served_page

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
WEB = REPO / "bin" / "vibe-web.py"

STAMP = "2026-01-01T00:00:00+00:00"


def ticket_record(tid, title, type="feedback", state="open", **extra):
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
    ticket_record("F1", "Erster Punkt", description="Erste Beschreibung"),
    ticket_record("F2", "Zweiter Punkt", description="Zweite Beschreibung"),
]


def load_cli(vibe_root):
    """Lädt bin/vibe als Modul, ohne main() auszuführen, isoliert.

    ``HOME`` und die Pfadquellen werden mitgesetzt, damit keine geerbte
    persönliche Konfiguration produktive Laufzeit-/Zustandsorte vorgibt.
    """
    with env_support.isolated_process_environment(
        VIBE=vibe_root,
        VIBE_NO_CONTAINER="1",
        HOME=Path(vibe_root) / "home",
        VIBE_RUNTIME=Path(vibe_root) / "_logs",
        VIBE_STATE=Path(vibe_root) / "_toolchain",
        VIBE_CONFIG_FILE=(
            Path(vibe_root) / "home" / ".config" / "vibe" / "config.json"
        ),
    ):
        loader = importlib.machinery.SourceFileLoader(
            "vibe_feedback_edit_under_test", str(CLI)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    return module


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def init_git_repo(path):
    """Legt ein Repository mit einem Commit an und liefert dessen Kurzhash."""
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
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
        cwd=path,
        check=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class FeedbackEditModelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        self.commit = init_git_repo(self.root)
        self.cli = load_cli(self.root)
        self.store = self.project / ".vibe" / "tickets.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write_feedback(self, records):
        self.store.write_text(
            json.dumps({"version": 1, "tickets": list(records)},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        return self.store

    def text(self):
        return self.store.read_text(encoding="utf-8")

    def records(self):
        return {item["id"]: item for item in json.loads(
            self.text())["tickets"]}

    def test_lists_all_feedback_entries_with_description_and_state(self):
        """Vor: offen/done/blockiert im Speicher. Aktion: feedback_items.
        Erwartet: Reihenfolge und Anzeigezustände offen/erledigt/BLOCKIERT."""
        self.write_feedback([
            ticket_record("F1", "Offener Punkt",
                          description="Erste Beschreibung"),
            ticket_record("F2", "Erledigter Punkt", state="done",
                          description="Zweite Beschreibung",
                          commit=self.commit, test="test_x"),
            ticket_record("F3", "Blockierter Punkt", state="blocked",
                          description="Dritte Beschreibung",
                          blocked_reason="fehlende Freigabe"),
        ])

        entries = self.cli.feedback_items("proj")

        self.assertEqual([entry["id"] for entry in entries],
                         ["F1", "F2", "F3"])
        self.assertEqual("Offener Punkt", entries[0]["title"])
        self.assertEqual("Erste Beschreibung", entries[0]["description"])
        self.assertEqual("offen", entries[0]["state"])
        self.assertEqual("erledigt", entries[1]["state"])
        self.assertEqual("BLOCKIERT", entries[2]["state"])

    def test_collects_a_multiline_description(self):
        """Vor: Ticket mit zweizeiliger Beschreibung. Aktion: feedback_items.
        Erwartet: beide Zeilen bleiben erhalten."""
        self.write_feedback([ticket_record(
            "F1", "Alter Punkt",
            description="Erste Zeile\nZweite Zeile der Beschreibung")])

        entries = self.cli.feedback_items("proj")

        self.assertEqual("Erste Zeile\nZweite Zeile der Beschreibung",
                         entries[0]["description"])

    def test_update_changes_title_and_description_only(self):
        """Vor: F1 mit Zusatzfeld, F2 daneben. Aktion: update F1.
        Erwartet: F1 neu, Zusatzfeld und F2 unverändert."""
        self.write_feedback([
            ticket_record("F1", "Alter Titel", description="Alte Beschreibung",
                          custom="bleibt"),
            ticket_record("F2", "Bleibt unverändert",
                          description="Unverändert"),
        ])

        self.cli.feedback_update("proj", "F1", "Neuer Titel",
                                 "Neue Beschreibung")

        records = self.records()
        self.assertEqual("Neuer Titel", records["F1"]["title"])
        self.assertEqual("Neue Beschreibung", records["F1"]["description"])
        self.assertEqual("bleibt", records["F1"]["custom"])
        self.assertEqual("Bleibt unverändert", records["F2"]["title"])

    def test_update_keeps_other_fields(self):
        """Vor: F1 mit Priorität und Typ. Aktion: update des Titels.
        Erwartet: Typ, Priorität und Zustand bleiben."""
        self.write_feedback([ticket_record(
            "F1", "Titel", priority="P2", state="in-progress")])

        self.cli.feedback_update("proj", "F1", "Neu", "Text")

        record = self.records()["F1"]
        self.assertEqual("feedback", record["type"])
        self.assertEqual("P2", record["priority"])
        self.assertEqual("in-progress", record["state"])

    def test_update_accepts_a_multiline_description(self):
        """Vor: F1. Aktion: update mit zwei Zeilen.
        Erwartet: beide Zeilen im Feld."""
        self.write_feedback([ticket_record("F1", "Titel", description="Alt")])

        self.cli.feedback_update("proj", "F1", "Titel",
                                 "Zeile eins\nZeile zwei")

        self.assertEqual("Zeile eins\nZeile zwei",
                         self.records()["F1"]["description"])

    def test_update_rejects_empty_title_without_changing_the_store(self):
        """Vor: F1. Aktion: update mit Leertitel.
        Erwartet: ValueError „Titel fehlt", Speicher unverändert."""
        self.write_feedback([ticket_record("F1", "Titel", description="Alt")])
        before = self.text()

        with self.assertRaisesRegex(ValueError, "Titel"):
            self.cli.feedback_update("proj", "F1", "   ", "Neu")

        self.assertEqual(self.text(), before)

    def test_update_rejects_title_with_line_break(self):
        """Vor: F1. Aktion: update mit mehrzeiligem Titel.
        Erwartet: ValueError „Zeilenumbruch", Speicher unverändert."""
        self.write_feedback([ticket_record("F1", "Titel", description="Alt")])
        before = self.text()

        with self.assertRaisesRegex(ValueError, "Zeilenumbruch"):
            self.cli.feedback_update("proj", "F1", "Neu\nF2", "Neu")

        self.assertEqual(self.text(), before)

    def test_update_accepts_an_empty_description(self):
        """Vor: F1 mit Beschreibung. Aktion: update mit leerer Beschreibung.
        Erwartet: das Feld ist leer, kein Resttext."""
        self.write_feedback([ticket_record("F1", "Titel", description="Alt")])

        self.cli.feedback_update("proj", "F1", "Titel", "")

        self.assertEqual("", self.records()["F1"]["description"])

    def test_update_rejects_unknown_id_without_changing_the_store(self):
        """Vor: F1. Aktion: update F99. Erwartet: ValueError „nicht gefunden"."""
        self.write_feedback([ticket_record("F1", "Titel", description="Alt")])
        before = self.text()

        with self.assertRaisesRegex(ValueError, "nicht gefunden"):
            self.cli.feedback_update("proj", "F99", "Neu", "Neu")

        self.assertEqual(self.text(), before)

    def test_delete_removes_only_selected_entry(self):
        """Vor: F1, F2. Aktion: delete F1. Erwartet: nur F2 bleibt."""
        self.write_feedback(BASELINE)

        self.cli.feedback_delete("proj", "F1")

        records = self.records()
        self.assertEqual(["F2"], list(records))
        self.assertEqual("Zweite Beschreibung", records["F2"]["description"])

    def test_delete_rejects_unknown_id_without_changing_the_store(self):
        """Vor: BASELINE. Aktion: delete F99. Erwartet: ValueError, unverändert."""
        self.write_feedback(BASELINE)
        before = self.text()

        with self.assertRaisesRegex(ValueError, "nicht gefunden"):
            self.cli.feedback_delete("proj", "F99")

        self.assertEqual(self.text(), before)

    def test_update_preserves_the_file_mode(self):
        """Vor: Speicher mit Modus 0640. Aktion: update.
        Erwartet: der Modus bleibt erhalten."""
        path = self.write_feedback([ticket_record("F1", "Titel",
                                                  description="Alt")])
        os.chmod(path, 0o640)

        self.cli.feedback_update("proj", "F1", "Neu", "Text")

        self.assertEqual(os.stat(path).st_mode & 0o777, 0o640)


class FeedbackApiFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        log_dir = cls.root / "_logs"
        log_dir.mkdir()
        (log_dir / "proj.log").write_text("Startzeile\n", encoding="utf-8")
        cls.port = free_port()
        env = env_support.isolated_environ(
            VIBE=cls.root,
            VIBE_NO_CONTAINER="1",
            VIBE_UI_PORT=cls.port,
            VIBE_RUNTIME=cls.root / "_logs",
            VIBE_STATE=cls.root / "_toolchain",
            HOME=cls.root / "home",
            VIBE_CONFIG_FILE=(
                cls.root / "home" / ".config" / "vibe" / "config.json"
            ),
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.root / "_logs" / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError("vibe-web wurde vorzeitig beendet: " + output)
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
            data=data,
            method="POST" if data else "GET",
        )
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

    def feedback_text(self):
        return (self.project / ".vibe" / "tickets.json").read_text(
            encoding="utf-8")

    def records(self):
        return {item["id"]: item for item in json.loads(
            self.feedback_text())["tickets"]}


class FeedbackApiTest(FeedbackApiFixture):
    def test_project_detail_exposes_editable_feedback_entries(self):
        status, body = self.request("/api/project?name=proj")

        self.assertEqual(status, 200, body)
        detail = json.loads(body)
        self.assertEqual([entry["id"] for entry in detail["feedback"]], ["F1", "F2"])
        self.assertEqual(detail["feedback"][0]["title"], "Erster Punkt")
        self.assertEqual(
            detail["feedback"][0]["description"], "Erste Beschreibung"
        )
        self.assertEqual(detail["feedback"][0]["state"], "offen")

    def test_api_updates_existing_entry(self):
        status, body = self.request(
            "/api/feedback",
            {
                "name": "proj",
                "action": "update",
                "id": "F1",
                "title": "Geänderter Titel",
                "description": "Geänderte Beschreibung",
            },
        )

        self.assertEqual(status, 200, body)
        self.assertTrue(json.loads(body)["ok"])
        records = self.records()
        self.assertEqual("Geänderter Titel", records["F1"]["title"])
        self.assertEqual("Geänderte Beschreibung",
                         records["F1"]["description"])
        self.assertEqual("Zweiter Punkt", records["F2"]["title"])

    def test_api_deletes_existing_entry(self):
        status, body = self.request(
            "/api/feedback", {"name": "proj", "action": "delete", "id": "F2"}
        )

        self.assertEqual(status, 200, body)
        records = self.records()
        self.assertNotIn("F2", records)
        self.assertEqual("Erster Punkt", records["F1"]["title"])

    def test_api_rejects_unknown_entry_and_keeps_file(self):
        before = self.feedback_text()

        status, body = self.request(
            "/api/feedback",
            {
                "name": "proj",
                "action": "update",
                "id": "F99",
                "title": "Neu",
                "description": "Neu",
            },
        )
        self.assertEqual(status, 400, body)
        self.assertIn("nicht gefunden", body)

        status, body = self.request(
            "/api/feedback", {"name": "proj", "action": "delete", "id": "F99"}
        )
        self.assertEqual(status, 400, body)
        self.assertEqual(self.feedback_text(), before)

    def test_api_rejects_missing_id_without_changing_file(self):
        before = self.feedback_text()

        status, body = self.request(
            "/api/feedback", {"name": "proj", "action": "delete", "title": "ohne ID"}
        )

        self.assertEqual(status, 400, body)
        self.assertIn("Feedback-ID fehlt", body)
        self.assertEqual(self.feedback_text(), before)

    def test_api_rejects_empty_title_without_changing_file(self):
        before = self.feedback_text()

        status, body = self.request(
            "/api/feedback",
            {
                "name": "proj",
                "action": "update",
                "id": "F1",
                "title": " ",
                "description": "Neu",
            },
        )

        self.assertEqual(status, 400, body)
        self.assertIn("Titel fehlt", body)
        self.assertEqual(self.feedback_text(), before)

    def test_api_rejects_unknown_action_without_changing_file(self):
        before = self.feedback_text()

        status, body = self.request(
            "/api/feedback", {"name": "proj", "action": "foo", "id": "F1"}
        )

        self.assertEqual(status, 400, body)
        self.assertIn("Unbekannte Aktion", body)
        self.assertEqual(self.feedback_text(), before)

    def test_detail_page_contains_feedback_and_log_controls(self):
        html = served_page(self.request)

        self.assertIn("Feedback (", html)
        self.assertIn("action:'update'", html)
        self.assertIn("action:'delete'", html)
        self.assertIn("'Bearbeiten'", html)
        self.assertIn("'Löschen'", html)
        self.assertIn("Pause", html)
        self.assertIn("Vergrößern", html)
        self.assertIn("logcard", html)
        self.assertIn("logPaused", html)
        self.assertNotIn("height:420px", html)


if __name__ == "__main__":
    unittest.main()
