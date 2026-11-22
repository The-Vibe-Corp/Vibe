"""Regressionstests für Ticket- und Feedbackverarbeitung (V-009).

Geprüft werden die Blockstruktur von TICKETS.md und FEEDBACK.md, das Ignorieren
von HTML-Kommentaren, stabile IDs, der Status (``offen``, ``BLOCKIERT``,
``ohne Nachweis``, ``erledigt``), defekte Checkboxen, das Anlegen neuer
Feedbackeinträge und die ID-Vergabe bei gleichzeitigen Zugriffen.

Die Modelltests arbeiten auf echten Dateien in einem temporären Arbeitsbereich
mit eigenem Git-Repository. Die Nebenläufigkeit wird einmal deterministisch
über einen konkurrierenden Schreiber und einmal über echte parallele Prozesse
sowie parallele HTTP-Anfragen an ``bin/vibe-web.py`` geprüft.
"""
import importlib.machinery
import importlib.util
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from tests.unit import env_support

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
WEB = REPO / "bin" / "vibe-web.py"


def load_cli(vibe_root):
    """Lädt bin/vibe als Modul, ohne main() auszuführen, isoliert.

    ``HOME`` und die Pfadquellen werden mitgesetzt, damit keine geerbte
    persönliche Konfiguration produktive Laufzeit-/Zustandsorte vorgibt
    (im Läufer sonst EROFS beim Anlegen von Laufzeitkennungen).
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
            "vibe_ticket_feedback_under_test", str(CLI)
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


class FeedbackFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        self.commit = init_git_repo(self.root)
        self.old_lock_dir = os.environ.get("VIBE_STORAGE_LOCK_DIR")
        os.environ["VIBE_STORAGE_LOCK_DIR"] = str(self.root / "locks")
        self.cli = load_cli(self.root)
        self.feedback = self.project / "FEEDBACK.md"

    def tearDown(self):
        if self.old_lock_dir is None:
            os.environ.pop("VIBE_STORAGE_LOCK_DIR", None)
        else:
            os.environ["VIBE_STORAGE_LOCK_DIR"] = self.old_lock_dir
        self.tmp.cleanup()

    def write_feedback(self, text):
        self.feedback.write_text(text, encoding="utf-8")

    def feedback_text(self):
        return self.feedback.read_text(encoding="utf-8")

    def entries(self):
        return {entry["id"]: entry for entry in self.cli.feedback_items("proj")}

    def open_items(self):
        return {item[0]: (item[1], item[2]) for item in self.cli.open_items("proj")}


class CommentHandlingTest(FeedbackFixture):
    def test_template_and_multiline_comments_are_not_entries(self):
        self.write_feedback(
            "# FEEDBACK\n\n"
            "<!-- Vorlage (nicht abhaken):\n"
            "  - [ ] F99 Kurztitel\n"
            "    Beschreibung: ...\n"
            "-->\n\n"
            "- [ ] F11 Echter Punkt\n"
            "  Beschreibung: Sichtbar\n\n"
            "<!--\n"
            "- [ ] F50 Versteckter Punkt\n"
            "  Beschreibung: Unsichtbar\n"
            "-->\n"
        )

        self.assertEqual(sorted(self.entries()), ["F11"])
        self.assertEqual(self.cli.next_feedback_number(self.feedback), 12)

    def test_inline_comments_are_ignored_in_title_and_description(self):
        self.write_feedback(
            "- [ ] F1 Echter Titel <!-- F98 Versteckt -->\n"
            "  Beschreibung: Sichtbar <!-- ausgeblendet --> Text\n"
        )

        entry = self.entries()["F1"]
        self.assertNotIn("F98", entry["title"])
        self.assertNotIn("Versteckt", entry["title"])
        self.assertNotIn("ausgeblendet", entry["description"])

    def test_commented_ticket_is_not_an_open_item(self):
        (self.project / "TICKETS.md").write_text(
            "# TICKETS\n\n"
            "<!--\n"
            "- [ ] V-99 Erfundene Aufgabe\n"
            "-->\n\n"
            "- [ ] V-1 Echte Aufgabe\n",
            encoding="utf-8",
        )

        self.assertEqual(sorted(self.open_items()), ["V-1"])


class MultilineBlockTest(FeedbackFixture):
    def test_checked_multiline_block_keeps_description_and_proof(self):
        self.write_feedback(
            "- [x] F1 Mehrzeilig\n"
            "  Beschreibung: Erste Zeile\n"
            "  Zweite Zeile\n"
            f"  Commit: {self.commit}; Test: test_x\n"
        )

        entry = self.entries()["F1"]
        self.assertEqual(entry["description"], "Erste Zeile\nZweite Zeile")
        self.assertEqual(entry["state"], "erledigt")
        self.assertEqual({}, self.open_items())

    def test_unindented_proof_line_does_not_belong_to_the_block(self):
        self.write_feedback(
            "- [x] F1 Nachweis außerhalb\n"
            "  Beschreibung: Text\n"
            f"Commit: {self.commit}; Test: test_x\n"
        )

        self.assertEqual(self.entries()["F1"]["state"], "ohne Nachweis")
        self.assertEqual(self.open_items()["F1"], ("Nachweis außerhalb", "ohne Nachweis"))


class BrokenCheckboxTest(FeedbackFixture):
    def test_broken_checkboxes_keep_their_id_and_stay_open(self):
        self.write_feedback(
            "- [X] F1 Großes X\n"
            "  Beschreibung: A\n\n"
            "- [] F2 Leere Klammer\n"
            "  Beschreibung: B\n\n"
            "- [ x ] F3 Leerzeichen in der Klammer\n"
            "  Beschreibung: C\n\n"
            "- [x] F4 Echt erledigt\n"
            "  Beschreibung: D\n"
            f"  Commit: {self.commit}; Test: test_x\n\n"
            "- F5 Ohne Checkbox\n"
            "  Beschreibung: E\n"
        )

        self.assertEqual(
            {ident: entry["state"] for ident, entry in self.entries().items()},
            {
                "F1": "offen",
                "F2": "offen",
                "F3": "offen",
                "F4": "erledigt",
                "F5": "offen",
            },
        )
        self.assertEqual(sorted(self.open_items()), ["F1", "F2", "F3", "F5"])

    def test_update_keeps_a_broken_checkbox_and_the_id(self):
        self.write_feedback(
            "- [] F2 Alter Titel\n"
            "  Beschreibung: Alt\n\n"
            "- [X] F3 Anderer Titel\n"
            "  Beschreibung: Alt\n"
        )

        self.cli.feedback_update("proj", "F2", "Neuer Titel", "Neu")
        self.cli.feedback_update("proj", "F3", "Neuer Titel", "Neu")

        text = self.feedback_text()
        self.assertIn("- [] F2 Neuer Titel", text)
        self.assertIn("- [X] F3 Neuer Titel", text)
        self.assertEqual(sorted(self.entries()), ["F2", "F3"])


class ProofStatusTest(FeedbackFixture):
    def test_checked_entry_without_commit_is_visible_as_missing_proof(self):
        self.write_feedback(
            "- [x] F1 Ohne Commit\n  Beschreibung: Text\n"
        )

        self.assertEqual(self.entries()["F1"]["state"], "ohne Nachweis")
        self.assertFalse(self.entries()["F1"]["completed"])
        self.assertEqual(self.open_items()["F1"], ("Ohne Commit", "ohne Nachweis"))

    def test_checked_entry_without_test_or_file_result_is_missing_proof(self):
        self.write_feedback(
            "- [x] F1 Ohne Ergebnis\n"
            "  Beschreibung: Text\n"
            f"  Commit: {self.commit}\n"
        )

        self.assertEqual(self.entries()["F1"]["state"], "ohne Nachweis")

    def test_checked_entry_with_unknown_commit_is_missing_proof(self):
        self.write_feedback(
            "- [x] F1 Unbekannter Commit\n"
            "  Beschreibung: Text\n"
            "  Commit: deadbeef; Test: test_x\n"
        )

        self.assertEqual(self.entries()["F1"]["state"], "ohne Nachweis")

    def test_valid_proof_is_completed_and_not_open(self):
        self.write_feedback(
            "- [x] F1 Belegt\n"
            "  Beschreibung: Text\n"
            f"  Commit: {self.commit}; Test: test_x\n"
        )

        entry = self.entries()["F1"]
        self.assertEqual(entry["state"], "erledigt")
        self.assertTrue(entry["completed"])
        self.assertEqual({}, self.open_items())

    def test_valid_file_proof_on_the_commit_line_is_accepted(self):
        self.write_feedback(
            "- [x] F1 Mit Dateinachweis\n"
            f"  Commit: {self.commit}; Datei: docs/features/V-009.md\n"
        )

        self.assertEqual(self.entries()["F1"]["state"], "erledigt")


class BlockedEntryTest(FeedbackFixture):
    def test_blocked_entry_with_checkbox_and_proof_is_done(self):
        """AP3-Präzedenz: erledigt > BLOCKIERT.

        Ein Punkt mit gesetztem Häkchen *und* gültigem Nachweis ist erledigt,
        auch wenn im Block zusätzlich ``BLOCKIERT:`` steht. Die frühere
        Erwartung (BLOCKIERT trotz Nachweis) war der Stand vor AP3; heute
        entscheidet der vollständige Nachweis. Der Fall bleibt aussagekräftig:
        Er belegt die dokumentierte Rangfolge und dass erledigte Punkte nicht
        mehr als offen geführt werden.
        """
        self.write_feedback(
            "- [x] F1 Blockiert\n"
            "  Beschreibung: Text\n"
            f"  Commit: {self.commit}; Test: test_x\n"
            "  BLOCKIERT: fehlende Freigabe\n"
        )

        entry = self.entries()["F1"]
        self.assertEqual(entry["state"], "erledigt")
        self.assertTrue(entry["completed"])
        self.assertNotIn("F1", self.open_items())

    def test_blocked_entry_does_not_block_new_ids(self):
        self.write_feedback(
            "- [x] F1 Blockiert\n"
            "  Beschreibung: Text\n"
            "  BLOCKIERT: fehlende Freigabe\n"
        )

        self.assertEqual(self.cli.add_feedback("proj", "Neu", "Beschreibung"), 2)
        self.assertIn("- [ ] F2 Neu", self.feedback_text())

    def test_blocked_ticket_stays_open(self):
        """Ein BLOCKIERT markiertes, offenes Ticket bleibt sichtbar.

        Die Checkbox bleibt hier bewusst ungesetzt: B3/AP3 führen vollständig
        erledigte (angehakte) Einträge nicht mehr als BLOCKIERT/offen. Der
        Zustand ``BLOCKIERT`` muss aber für ein noch offenes Ticket erhalten
        bleiben, damit es nicht stillschweigend aus der Liste verschwindet.
        """
        (self.project / "TICKETS.md").write_text(
            "# TICKETS\n\n"
            "- [ ] V-1 Blockiert\n"
            "  BLOCKIERT: fehlende Freigabe\n",
            encoding="utf-8",
        )

        self.assertEqual(
            self.open_items()["V-1"], ("Blockiert", "BLOCKIERT")
        )


class MissingFilesTest(FeedbackFixture):
    def test_missing_feedback_file_yields_no_items_and_starts_at_one(self):
        self.assertFalse(self.feedback.exists())

        self.assertEqual([], self.cli.feedback_items("proj"))
        self.assertEqual([], self.cli.open_items("proj"))
        self.assertEqual(1, self.cli.next_feedback_number(self.feedback))

    def test_add_feedback_creates_a_missing_file(self):
        number = self.cli.add_feedback("proj", "Neu", "Beschreibung")

        self.assertEqual(1, number)
        self.assertEqual(self.entries()["F1"]["title"], "Neu")

    def test_update_and_delete_report_a_missing_file(self):
        with self.assertRaisesRegex(ValueError, "Keine FEEDBACK.md"):
            self.cli.feedback_update("proj", "F1", "Titel", "Text")
        with self.assertRaisesRegex(ValueError, "Keine FEEDBACK.md"):
            self.cli.feedback_delete("proj", "F1")

    def test_missing_tickets_file_is_ignored(self):
        self.assertFalse((self.project / "TICKETS.md").exists())
        self.write_feedback("- [ ] F1 Offen\n  Beschreibung: Text\n")

        self.assertEqual(sorted(self.open_items()), ["F1"])


class NewEntryTest(FeedbackFixture):
    def test_add_feedback_rejects_empty_title_without_writing(self):
        with self.assertRaisesRegex(ValueError, "Titel fehlt"):
            self.cli.add_feedback("proj", "   ", "Text")

        self.assertFalse(self.feedback.exists())

    def test_add_feedback_rejects_a_line_break_in_the_title(self):
        with self.assertRaisesRegex(ValueError, "Zeilenumbruch"):
            self.cli.add_feedback("proj", "Titel\n- [ ] F2 Eingeschmuggelt", "Text")

        self.assertFalse(self.feedback.exists())

    def test_add_feedback_indents_a_multiline_description(self):
        number = self.cli.add_feedback("proj", "Mehrzeilig", "Zeile eins\nZeile zwei")

        self.assertEqual(1, number)
        self.assertEqual(
            self.entries()["F1"]["description"], "Zeile eins\nZeile zwei"
        )
        self.assertEqual(sorted(self.open_items()), ["F1"])

    def test_new_number_ignores_the_commented_template(self):
        self.write_feedback(
            "# FEEDBACK\n\n"
            "<!-- Vorlage (nicht abhaken):\n"
            "  - [ ] F99 Kurztitel\n"
            "-->\n\n"
            "- [ ] F3 Vorhanden\n"
            "  Beschreibung: Text\n"
        )

        self.assertEqual(4, self.cli.add_feedback("proj", "Neu", "Text"))
        text = self.feedback_text()
        self.assertIn("- [ ] F4 Neu", text)
        self.assertNotIn("F100", text)

    def test_new_number_skips_a_broken_checkbox_entry(self):
        self.write_feedback("- [] F7 Alter Eintrag\n  Beschreibung: Text\n")

        self.assertEqual(8, self.cli.add_feedback("proj", "Neu", "Text"))

    def test_add_feedback_retries_when_the_file_is_created_concurrently(self):
        real_write = self.cli.vibe_storage.write_text
        state = {"injected": False}

        def racing_write(path, text, expected=None, **kwargs):
            if not state["injected"]:
                state["injected"] = True
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(
                        "- [ ] F1 Fremder Schreiber\n  Beschreibung: parallel\n"
                    )
            return real_write(path, text, expected=expected, **kwargs)

        with mock.patch.object(
            self.cli.vibe_storage, "write_text", side_effect=racing_write
        ):
            number = self.cli.add_feedback("proj", "Eigener Eintrag", "Beschreibung")

        self.assertEqual(2, number)
        self.assertEqual(sorted(self.entries()), ["F1", "F2"])


class ConcurrentIdTest(FeedbackFixture):
    def test_conflicting_write_is_retried_with_the_next_free_id(self):
        self.write_feedback("")
        real_write = self.cli.vibe_storage.write_text
        state = {"injected": False}

        def racing_write(path, text, expected=None, **kwargs):
            if not state["injected"]:
                state["injected"] = True
                with open(path, "a", encoding="utf-8") as handle:
                    handle.write("- [ ] F1 Fremder Schreiber\n  Beschreibung: parallel\n")
            return real_write(path, text, expected=expected, **kwargs)

        with mock.patch.object(
            self.cli.vibe_storage, "write_text", side_effect=racing_write
        ):
            number = self.cli.add_feedback("proj", "Eigener Eintrag", "Beschreibung")

        self.assertEqual(2, number)
        self.assertEqual(sorted(self.entries()), ["F1", "F2"])

    def test_parallel_processes_get_unique_ids(self):
        worker = (
            "import importlib.machinery, importlib.util, os, sys, time\n"
            "root, cli_path, start, title = sys.argv[1:5]\n"
            "os.environ['VIBE'] = root\n"
            "os.environ['VIBE_NO_CONTAINER'] = '1'\n"
            "loader = importlib.machinery.SourceFileLoader('vibe_parallel', cli_path)\n"
            "spec = importlib.util.spec_from_loader(loader.name, loader)\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "loader.exec_module(module)\n"
            "delay = float(start) - time.time()\n"
            "if delay > 0:\n"
            "    time.sleep(delay)\n"
            "module.add_feedback('proj', title, 'parallel')\n"
        )
        env = env_support.isolated_environ(
            VIBE=self.root,
            VIBE_NO_CONTAINER="1",
            VIBE_RUNTIME=self.root / "_logs",
            VIBE_STATE=self.root / "_toolchain",
            HOME=self.root / "home",
            VIBE_CONFIG_FILE=(
                self.root / "home" / ".config" / "vibe" / "config.json"
            ),
            VIBE_STORAGE_LOCK_DIR=self.root / "locks",
        )
        start = time.time() + 1.5
        processes = [
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    worker,
                    str(self.root),
                    str(CLI),
                    f"{start:.6f}",
                    f"Parallel {index}",
                ],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for index in range(8)
        ]
        failures = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=60)
            if process.returncode != 0:
                failures.append((stdout, stderr))
        self.assertEqual([], failures)

        text = self.feedback_text()
        numbers = [int(value) for value in re.findall(r"(?m)^- \[ \] F(\d+) ", text)]
        self.assertEqual(8, len(numbers), text)
        self.assertEqual(8, len(set(numbers)), text)
        self.assertEqual(list(range(1, 9)), sorted(numbers))


class FeedbackApiConcurrencyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
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
            VIBE_STORAGE_LOCK_DIR=cls.root / "locks",
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

    def test_parallel_api_requests_get_unique_ids(self):
        feedback = self.project / "FEEDBACK.md"
        if feedback.exists():
            feedback.unlink()

        def create(index):
            payload = (
                '{"name":"proj","title":"Anfrage %d","description":"parallel"}' % index
            ).encode("utf-8")
            request = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/api/feedback",
                data=payload,
                method="POST",
            )
            request.add_header("Host", f"127.0.0.1:{self.port}")
            request.add_header("X-Token", self.token)
            request.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.status, response.read().decode("utf-8")

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(create, range(8)))

        self.assertEqual([200] * 8, [status for status, _ in results], results)
        text = feedback.read_text(encoding="utf-8")
        numbers = [int(value) for value in re.findall(r"(?m)^- \[ \] F(\d+) ", text)]
        self.assertEqual(8, len(numbers), text)
        self.assertEqual(8, len(set(numbers)), text)
        self.assertEqual(list(range(1, 9)), sorted(numbers))


if __name__ == "__main__":
    unittest.main()
