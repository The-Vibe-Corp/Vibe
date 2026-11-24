"""Tests für abgeschlossene Feedback-Punkte (F8).

Abgeschlossen heißt nach SPEC.md: Checkbox gesetzt *und* Nachweis vorhanden
(``Commit:`` plus ``Test:``/``Datei:``). Solche Punkte kennzeichnet das Modell
mit ``completed``, die HTTP-API lehnt Änderungen daran ab. Geprüft wird auf
echten Dateien in einem temporären Arbeitsbereich; die API-Tests starten
bin/vibe-web.py auf einem eigenen Port.

F34-Anpassung: (WP7.1) Abgeschlossene Feedback-Punkte sind Nachweise und
dürfen nicht gelöscht werden; offene Punkte bleiben löschbar
(Bestandsschutz). Die Tests sichern Ablehnung, unveränderte Datei und den
weiterhin erlaubten Löschpfad für offene Einträge ab.
"""
import importlib.machinery
import importlib.util
import json
import os
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
            "vibe_feedback_completed_under_test", str(CLI)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    return module


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


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


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


class FeedbackCompletedModelTest(unittest.TestCase):
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

    def text(self):
        return self.store.read_text(encoding="utf-8")

    def test_flags_only_done_entries_as_completed(self):
        """Vor: F1 done mit Nachweis, F2 offen, F3 in-progress.
        Aktion: feedback_items. Erwartet: completed nur bei F1."""
        self.write_feedback([
            ticket_record("F1", "Erledigter Punkt", type="feedback",
                          state="done", commit=self.commit,
                          test="test_x"),
            ticket_record("F2", "Offener Punkt", type="feedback"),
            ticket_record("F3", "Läuft", type="feedback",
                          state="in-progress"),
        ])

        entries = {entry["id"]: entry
                   for entry in self.cli.feedback_items("proj")}

        self.assertTrue(entries["F1"]["completed"])
        self.assertEqual("erledigt", entries["F1"]["state"])
        self.assertFalse(entries["F2"]["completed"])
        self.assertEqual("offen", entries["F2"]["state"])
        self.assertFalse(entries["F3"]["completed"])
        self.assertEqual("In Progress", entries["F3"]["state"])

    def test_update_rejects_done_entry_without_changing_the_store(self):
        """Vor: F1 done. Aktion: feedback_update.
        Erwartet: ValueError „nicht bearbeitbar", Speicher unverändert."""
        self.write_feedback([ticket_record(
            "F1", "Erledigter Punkt", type="feedback", state="done",
            commit=self.commit, test="test_x")])
        before = self.text()

        with self.assertRaisesRegex(ValueError, "nicht bearbeitbar"):
            self.cli.feedback_update("proj", "F1", "Neuer Titel", "Neu")

        self.assertEqual(self.text(), before)

    def test_update_allows_an_open_entry_with_a_similar_id(self):
        """Vor: F1 done, F2 offen. Aktion: feedback_update F2.
        Erwartet: F2 neu, F1 unverändert."""
        self.write_feedback([
            ticket_record("F1", "Erledigter Punkt", type="feedback",
                          state="done", commit=self.commit, test="test_x"),
            ticket_record("F2", "Offener Punkt", type="feedback"),
        ])

        self.cli.feedback_update("proj", "F2", "Neuer Titel", "Neu")

        records = {item["id"]: item for item in json.loads(
            self.text())["tickets"]}
        self.assertEqual("Neuer Titel", records["F2"]["title"])
        self.assertEqual("done", records["F1"]["state"])

    def test_delete_rejects_done_entry_and_allows_open_entries(self):
        """Vor: F1 done, F2 offen. Aktion: Delete F1, dann F2.
        Erwartet: F1 ValueError und bleibt; F2 wird entfernt."""
        self.write_feedback([
            ticket_record("F1", "Erledigter Punkt", type="feedback",
                          state="done", commit=self.commit, test="test_x"),
            ticket_record("F2", "Offener Punkt", type="feedback"),
        ])
        before = self.text()

        with self.assertRaisesRegex(ValueError,
                                    "bleiben als Nachweis erhalten"):
            self.cli.feedback_delete("proj", "F1")

        self.assertEqual(self.text(), before)
        self.cli.feedback_delete("proj", "F2")
        records = {item["id"]: item for item in json.loads(
            self.text())["tickets"]}
        self.assertEqual(["F1"], list(records))
        self.assertEqual("done", records["F1"]["state"])


class FeedbackCompletedApiFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        cls.commit = init_git_repo(cls.root)
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
            json.dumps({"version": 1, "tickets": [
                ticket_record("F1", "Erledigter Punkt", type="feedback",
                              state="done", commit=self.commit,
                              description="Erste Beschreibung",
                              test="test_x"),
                ticket_record("F2", "Offener Punkt", type="feedback",
                              description="Zweite Beschreibung"),
            ]}, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )

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


class FeedbackCompletedApiTest(FeedbackCompletedApiFixture):
    def test_project_detail_exposes_completed_flag(self):
        status, body = self.request("/api/project?name=proj")

        self.assertEqual(status, 200, body)
        feedback = {entry["id"]: entry for entry in json.loads(body)["feedback"]}
        self.assertTrue(feedback["F1"]["completed"])
        self.assertFalse(feedback["F2"]["completed"])

    def test_api_rejects_update_of_completed_entry_and_keeps_file(self):
        before = self.feedback_text()

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

        self.assertEqual(status, 400, body)
        self.assertIn("nicht bearbeitbar", body)
        self.assertEqual(self.feedback_text(), before)

    def test_api_updates_open_entry(self):
        status, body = self.request(
            "/api/feedback",
            {
                "name": "proj",
                "action": "update",
                "id": "F2",
                "title": "Geänderter Titel",
                "description": "Geänderte Beschreibung",
            },
        )

        self.assertEqual(status, 200, body)
        records = {item["id"]: item for item in json.loads(
            self.feedback_text())["tickets"]}
        self.assertEqual("Geänderter Titel", records["F2"]["title"])
        self.assertEqual("Erledigter Punkt", records["F1"]["title"])
        self.assertEqual("done", records["F1"]["state"])

    def test_api_delete_rejects_completed_entry_and_keeps_file(self):
        """F34 WP7.1: Die API liefert 400 ``ok:false`` statt zu löschen.

        Vorbedingung: F1 abgeschlossen (Nachweis), F2 offen. Aktion: Löschen
        von F1, danach von F2. Erwartung: F1 wird mit derselben Meldung
        abgelehnt, die Datei bleibt byte-gleich; F2 bleibt löschbar.
        Fehlerfall: Die API löscht einen Nachweis oder sperrt offenes Feedback.
        """
        before = self.feedback_text()

        status, body = self.request(
            "/api/feedback", {"name": "proj", "action": "delete", "id": "F1"}
        )

        self.assertEqual(400, status, body)
        data = json.loads(body)
        self.assertIs(data.get("ok"), False, body)
        self.assertIn("bleiben als Nachweis erhalten", body)
        self.assertEqual(self.feedback_text(), before,
                         "Die abgelehnte Löschung veränderte FEEDBACK.md")

        status, body = self.request(
            "/api/feedback", {"name": "proj", "action": "delete", "id": "F2"}
        )

        self.assertEqual(200, status, body)
        records = {item["id"]: item for item in json.loads(
            self.feedback_text())["tickets"]}
        self.assertNotIn("F2", records)
        self.assertEqual("done", records["F1"]["state"],
                         "Das Löschen des offenen Punkts entfernte den Nachweis")

    def test_detail_page_mentions_completed_toggle(self):
        html = served_page(self.request)

        self.assertIn("Abgeschlossene anzeigen", html)
        self.assertIn("nicht bearbeitbar", html)


if __name__ == "__main__":
    unittest.main()
