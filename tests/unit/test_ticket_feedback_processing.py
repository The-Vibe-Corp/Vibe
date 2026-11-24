"""GH-48: Ticket-/Feedbackverarbeitung auf dem JSON-Ticketspeicher.

Ersetzt die früheren Markdown-Parser-Fälle (Kommentare, eingerückte Blöcke,
defekte Checkboxen). Diese Regeln existieren nicht mehr: Tickets sind
Datensätze mit Feldern. Erhalten bleiben die fachlich tragenden Aussagen:
mehrzeilige Beschreibungen, Eingabevalidierung, Reihenfolge der Auto-IDs,
Konflikt-Wiederholung und eindeutige IDs bei parallelen Schreibern
(Prozesse und HTTP-Anfragen).

Keine Modellaufrufe, keine externen Dienste; alles in temporären Pfaden.

Run:

    python3 -m unittest tests.unit.test_ticket_feedback_processing -v
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
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from tests.unit import env_support

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
WEB = REPO / "bin" / "vibe-web.py"


def load_cli(vibe_root):
    with env_support.isolated_process_environment(
        VIBE=str(vibe_root),
        VIBE_NO_CONTAINER="1",
        HOME=str(Path(vibe_root) / "home"),
        VIBE_RUNTIME=str(Path(vibe_root) / "_logs"),
        VIBE_STATE=str(Path(vibe_root) / "_toolchain"),
        VIBE_CONFIG_FILE=str(Path(vibe_root) / "home" / ".config" / "vibe"
                             / "config.json"),
    ):
        loader = importlib.machinery.SourceFileLoader(
            "vibe_ticket_feedback_under_test", str(CLI))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    return module


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
            "TYPE=generic\n", encoding="utf-8")
        self.old_lock_dir = os.environ.get("VIBE_STORAGE_LOCK_DIR")
        os.environ["VIBE_STORAGE_LOCK_DIR"] = str(self.root / "locks")
        self.cli = load_cli(self.root)
        self.store = self.project / ".vibe" / "tickets.json"

    def tearDown(self):
        if self.old_lock_dir is None:
            os.environ.pop("VIBE_STORAGE_LOCK_DIR", None)
        else:
            os.environ["VIBE_STORAGE_LOCK_DIR"] = self.old_lock_dir
        self.tmp.cleanup()

    def records(self):
        if not self.store.is_file():
            return {}
        return {item["id"]: item for item in json.loads(
            self.store.read_text(encoding="utf-8"))["tickets"]}


class EntryHandlingTest(FeedbackFixture):
    def test_add_keeps_a_multiline_description(self):
        """Vor: leerer Speicher. Aktion: add_feedback mehrzeilig.
        Erwartet: F1 mit beiden Zeilen im description-Feld."""
        number = self.cli.add_feedback("proj", "Titel",
                                       "Zeile eins\nZeile zwei")

        self.assertEqual("F1", number)
        self.assertEqual("Zeile eins\nZeile zwei",
                         self.records()["F1"]["description"])

    def test_comment_like_text_is_plain_description(self):
        """Vor: Beschreibung enthält HTML-Kommentarzeichen.
        Aktion: add_feedback. Erwartet: Text bleibt unverändert im Feld —
        es gibt keine Kommentar-Syntax mehr."""
        text = "<!-- alter Hinweis -->\nZeile zwei"

        self.cli.add_feedback("proj", "Titel", text)

        self.assertEqual(text, self.records()["F1"]["description"])

    def test_update_keeps_other_fields(self):
        """Vor: Ticket mit Priorität/Zusatzfeld. Aktion: update.
        Erwartet: Titel/Beschreibung neu, übrige Felder unverändert."""
        (self.project / ".vibe" / "tickets.json").write_text(
            json.dumps({"version": 1, "tickets": [{
                "id": "F1", "title": "Alt", "type": "feedback",
                "state": "open", "description": "Alt", "priority": "P1",
                "custom": "bleibt",
                "created": "2026-01-01T00:00:00+00:00",
                "updated": "2026-01-01T00:00:00+00:00"}]},
                ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

        self.cli.feedback_update("proj", "F1", "Neu", "Neu")

        record = self.records()["F1"]
        self.assertEqual("Neu", record["title"])
        self.assertEqual("P1", record["priority"])
        self.assertEqual("bleibt", record["custom"])

    def test_add_rejects_empty_title_without_writing(self):
        """Vor: leerer Speicher. Aktion: add mit Leertitel.
        Erwartet: ValueError, kein Ticket."""
        with self.assertRaises(ValueError):
            self.cli.add_feedback("proj", "   ")

        self.assertEqual({}, self.records())

    def test_add_rejects_a_line_break_in_the_title(self):
        """Vor: leerer Speicher. Aktion: add mit mehrzeiligem Titel.
        Erwartet: ValueError, kein Ticket."""
        with self.assertRaises(ValueError):
            self.cli.add_feedback("proj", "Zeile\nZwei")

        self.assertEqual({}, self.records())

    def test_missing_store_starts_numbering_at_one(self):
        """Vor: kein Speicher. Aktion: add_feedback.
        Erwartet: F1, Speicher wird angelegt (GH-48: keine Ledger-Pflicht)."""
        self.assertEqual("F1", self.cli.add_feedback("proj", "Erster"))

        self.assertTrue(self.store.is_file())
        self.assertEqual(["F1"], list(self.records()))


class ConcurrentIdTest(FeedbackFixture):
    def test_conflicting_write_is_retried_with_the_next_free_id(self):
        """Vor: leerer Speicher; ein fremder Schreiber legt beim ersten
        Schreibversuch F1 an. Aktion: add_feedback.
        Erwartet: der eigene Eintrag erhält F2; beide bleiben erhalten."""
        (self.project / ".vibe" / "tickets.json").write_text(
            json.dumps({"version": 1, "tickets": []},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        real_write = self.cli.vibe_storage.write_text
        state = {"injected": False}

        def racing_write(path, text, expected=None, **kwargs):
            if not state["injected"]:
                state["injected"] = True
                current = json.loads(Path(path).read_text(encoding="utf-8"))
                current["tickets"].append({
                    "id": "F1", "title": "Fremder Schreiber",
                    "type": "feedback", "state": "open",
                    "description": "parallel", "github": None,
                    "pr_url": "", "commit": "", "test": "",
                    "blocked_reason": "", "waiting_note": "",
                    "priority": "", "dependencies": [],
                    "created": "2026-01-01T00:00:00+00:00",
                    "updated": "2026-01-01T00:00:00+00:00"})
                Path(path).write_text(
                    json.dumps(current, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
            return real_write(path, text, expected=expected, **kwargs)

        with mock.patch.object(self.cli.vibe_storage, "write_text",
                               side_effect=racing_write):
            number = self.cli.add_feedback("proj", "Eigener Eintrag",
                                           "Beschreibung")

        self.assertEqual("F2", number)
        self.assertEqual(["F1", "F2"], sorted(self.records()))

    def test_parallel_processes_get_unique_ids(self):
        """Vor: kein Speicher, acht parallele Prozesse. Aktion: add_feedback.
        Erwartet: F1..F8, jede ID genau einmal."""
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
            VIBE_CONFIG_FILE=str(self.root / "home" / ".config" / "vibe"
                                 / "config.json"),
            VIBE_STORAGE_LOCK_DIR=self.root / "locks",
        )
        start = time.time() + 1.5
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", worker, str(self.root), str(CLI),
                 f"{start:.6f}", f"Parallel {index}"],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True)
            for index in range(8)
        ]
        failures = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=60)
            if process.returncode != 0:
                failures.append((stdout, stderr))
        self.assertEqual([], failures)

        identifiers = sorted(self.records())
        self.assertEqual([f"F{index}" for index in range(1, 9)], identifiers)


class FeedbackApiConcurrencyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        cls.port = free_port()
        env = env_support.isolated_environ(
            VIBE=cls.root,
            VIBE_NO_CONTAINER="1",
            VIBE_UI_PORT=cls.port,
            VIBE_RUNTIME=cls.root / "_logs",
            VIBE_STATE=cls.root / "_toolchain",
            HOME=cls.root / "home",
            VIBE_CONFIG_FILE=str(cls.root / "home" / ".config" / "vibe"
                                 / "config.json"),
            VIBE_STORAGE_LOCK_DIR=cls.root / "locks",
        )
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

    def test_parallel_api_requests_get_unique_ids(self):
        """Vor: kein Speicher, acht parallele HTTP-Anfragen. Aktion:
        POST /api/feedback. Erwartet: 8x 200 und F1..F8 ohne Duplikate."""
        store = self.project / ".vibe" / "tickets.json"
        if store.exists():
            store.unlink()

        def create(index):
            payload = (
                '{"name":"proj","title":"Anfrage %d","description":"parallel"}'
                % index).encode("utf-8")
            request = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/api/feedback",
                data=payload, method="POST")
            request.add_header("Host", f"127.0.0.1:{self.port}")
            request.add_header("X-Token", self.token)
            request.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.status, response.read().decode("utf-8")

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(create, range(8)))

        self.assertEqual([200] * 8, [status for status, _ in results], results)
        document = json.loads(store.read_text(encoding="utf-8"))
        identifiers = [item["id"] for item in document["tickets"]]
        self.assertEqual(8, len(identifiers), identifiers)
        self.assertEqual([f"F{index}" for index in range(1, 9)],
                         sorted(identifiers))


if __name__ == "__main__":
    unittest.main()
