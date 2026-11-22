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

BASELINE = """# FEEDBACK — Rückmeldungen an den Agenten

<!-- Vorlage (nicht abhaken):
  - [ ] F99 Kurztitel
    Beschreibung: ...
-->

- [ ] F1 Erster Punkt
  Beschreibung: Erste Beschreibung

- [ ] F2 Zweiter Punkt
  Beschreibung: Zweite Beschreibung
"""


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
        self.feedback = self.project / "FEEDBACK.md"

    def tearDown(self):
        self.tmp.cleanup()

    def write_feedback(self, text):
        self.feedback.write_text(text, encoding="utf-8")

    def text(self):
        return self.feedback.read_text(encoding="utf-8")

    def test_lists_all_feedback_entries_with_description_and_state(self):
        self.write_feedback(
            "# FEEDBACK\n\n"
            "- [ ] F1 Offener Punkt\n"
            "  Beschreibung: Erste Beschreibung\n\n"
            "- [x] F2 Erledigter Punkt\n"
            "  Beschreibung: Zweite Beschreibung\n"
            f"  Commit: {self.commit}; Test: test_x\n\n"
            "- [ ] F3 Blockierter Punkt\n"
            "  Beschreibung: Dritte Beschreibung\n"
            "  BLOCKIERT: fehlende Freigabe\n"
        )

        entries = self.cli.feedback_items("proj")

        self.assertEqual([e["id"] for e in entries], ["F1", "F2", "F3"])
        self.assertEqual(entries[0]["title"], "Offener Punkt")
        self.assertEqual(entries[0]["description"], "Erste Beschreibung")
        self.assertEqual(entries[0]["state"], "offen")
        self.assertEqual(entries[1]["state"], "erledigt")
        self.assertEqual(entries[2]["state"], "BLOCKIERT")

    def test_collects_multiline_description_without_field_labels(self):
        self.write_feedback(
            "- [ ] F1 Alter Punkt\n"
            "  Schritte: Schritt A\n"
            "  Erwartet: Erste Zeile\n"
            "  Zweite Zeile der Beschreibung\n"
            "  Ist: Ist-Zustand\n"
        )

        entries = self.cli.feedback_items("proj")

        self.assertEqual(len(entries), 1)
        self.assertEqual(
            entries[0]["description"],
            "Erste Zeile\nZweite Zeile der Beschreibung",
        )

    def test_update_changes_title_and_description_only(self):
        self.write_feedback(
            "- [ ] F1 Alter Titel\n"
            "  Schritte: Schritt A\n"
            "  Erwartet: Alte Beschreibung\n"
            "  Fortsetzung der alten Beschreibung\n"
            "  Ist: Ist-Zustand\n\n"
            "- [ ] F2 Bleibt unverändert\n"
            "  Beschreibung: Unverändert\n"
        )

        self.cli.feedback_update("proj", "F1", "Neuer Titel", "Neue Beschreibung")

        text = self.text()
        self.assertIn("- [ ] F1 Neuer Titel", text)
        self.assertIn("  Beschreibung: Neue Beschreibung", text)
        self.assertIn("  Schritte: Schritt A", text)
        self.assertIn("  Ist: Ist-Zustand", text)
        self.assertNotIn("Erwartet:", text)
        self.assertNotIn("Fortsetzung der alten Beschreibung", text)
        self.assertIn("- [ ] F2 Bleibt unverändert", text)
        self.assertIn("  Beschreibung: Unverändert", text)

    def test_update_adds_description_when_missing(self):
        self.write_feedback("- [ ] F1 Nur Titel\n")

        self.cli.feedback_update("proj", "F1", "Neuer Titel", "Neue Beschreibung")

        self.assertEqual(
            [line for line in self.text().splitlines() if line.strip()],
            ["- [ ] F1 Neuer Titel", "  Beschreibung: Neue Beschreibung"],
        )

    def test_update_keeps_multiline_description(self):
        self.write_feedback("- [ ] F1 Titel\n  Beschreibung: Alt\n")

        self.cli.feedback_update("proj", "F1", "Titel", "Zeile eins\nZeile zwei")

        entries = self.cli.feedback_items("proj")
        self.assertEqual(entries[0]["description"], "Zeile eins\nZeile zwei")

    def test_update_keeps_done_checkbox(self):
        self.write_feedback("- [x] F1 Alter Titel\n  Beschreibung: Alt\n")

        self.cli.feedback_update("proj", "F1", "Neuer Titel", "Neu")

        self.assertEqual(
            [line for line in self.text().splitlines() if line.strip()],
            ["- [x] F1 Neuer Titel", "  Beschreibung: Neu"],
        )

    def test_update_rejects_empty_title_without_changing_file(self):
        self.write_feedback("- [ ] F1 Titel\n  Beschreibung: Alt\n")
        before = self.text()

        with self.assertRaisesRegex(ValueError, "Titel fehlt"):
            self.cli.feedback_update("proj", "F1", "   ", "Neu")

        self.assertEqual(self.text(), before)

    def test_update_rejects_title_with_line_break_without_changing_file(self):
        self.write_feedback("- [ ] F1 Titel\n  Beschreibung: Alt\n")
        before = self.text()

        with self.assertRaisesRegex(ValueError, "Zeilenumbruch"):
            self.cli.feedback_update("proj", "F1", "Neu\n- [ ] F2 Eingeschmuggelt", "Neu")

        self.assertEqual(self.text(), before)

    def test_update_keeps_file_mode(self):
        self.write_feedback("- [ ] F1 Titel\n  Beschreibung: Alt\n")
        os.chmod(self.feedback, 0o640)

        self.cli.feedback_update("proj", "F1", "Neuer Titel", "Neu")

        self.assertEqual(os.stat(self.feedback).st_mode & 0o777, 0o640)

    def test_update_writes_empty_description_without_trailing_space(self):
        self.write_feedback("- [ ] F1 Titel\n  Beschreibung: Alt\n")

        self.cli.feedback_update("proj", "F1", "Titel", "")

        self.assertEqual(
            [line for line in self.text().splitlines() if line.strip()],
            ["- [ ] F1 Titel", "  Beschreibung:"],
        )

    def test_update_rejects_unknown_id_without_changing_file(self):
        self.write_feedback("- [ ] F1 Titel\n  Beschreibung: Alt\n")
        before = self.text()

        with self.assertRaisesRegex(ValueError, "nicht gefunden"):
            self.cli.feedback_update("proj", "F99", "Neu", "Neu")

        self.assertEqual(self.text(), before)

    def test_delete_removes_only_selected_entry(self):
        self.write_feedback(BASELINE)

        self.cli.feedback_delete("proj", "F1")

        text = self.text()
        self.assertNotIn("F1 Erster Punkt", text)
        self.assertNotIn("Erste Beschreibung", text)
        self.assertIn("- [ ] F2 Zweiter Punkt", text)
        self.assertIn("  Beschreibung: Zweite Beschreibung", text)
        self.assertIn("F99 Kurztitel", text, "Kommentar-Vorlage muss erhalten bleiben")
        self.assertIn("<!-- Vorlage (nicht abhaken):", text)

    def test_delete_rejects_unknown_id_without_changing_file(self):
        self.write_feedback(BASELINE)
        before = self.text()

        with self.assertRaisesRegex(ValueError, "nicht gefunden"):
            self.cli.feedback_delete("proj", "F99")

        self.assertEqual(self.text(), before)


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
        (self.project / "FEEDBACK.md").write_text(BASELINE, encoding="utf-8")

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
        return (self.project / "FEEDBACK.md").read_text(encoding="utf-8")


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
        text = self.feedback_text()
        self.assertIn("- [ ] F1 Geänderter Titel", text)
        self.assertIn("  Beschreibung: Geänderte Beschreibung", text)
        self.assertIn("- [ ] F2 Zweiter Punkt", text)
        self.assertNotIn("Erster Punkt", text)

    def test_api_deletes_existing_entry(self):
        status, body = self.request(
            "/api/feedback", {"name": "proj", "action": "delete", "id": "F2"}
        )

        self.assertEqual(status, 200, body)
        text = self.feedback_text()
        self.assertNotIn("F2 Zweiter Punkt", text)
        self.assertIn("- [ ] F1 Erster Punkt", text)
        self.assertIn("F99 Kurztitel", text)

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
