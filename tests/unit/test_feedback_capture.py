"""Tests für die Feedback-Erfassung mit den Feldern Titel und Beschreibung (F1).

Die Erfassung darf nur noch Titel und Beschreibung anbieten. „Schritte“ und
„Ist“ entfallen; das frühere Feld „Erwartet“ heißt jetzt „Beschreibung“.
Geprüft werden der Markdown-Schreibvorgang, der CLI-Dialog und die Web-API
einschließlich der im Projektdetail ausgelieferten Oberfläche.
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
from unittest import mock

from tests.unit import env_support
from tests.unit.web_page import served_page

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
WEB = REPO / "bin" / "vibe-web.py"

REMOVED_FIELDS = ("Schritte:", "Erwartet:", "Ist:")


def load_cli(vibe_root):
    """Lädt bin/vibe als Modul, ohne main() auszuführen, isoliert.

    Neben ``VIBE`` wird auch ``HOME`` auf das temporäre Prüfverzeichnis
    gesetzt: Eine geerbte persönliche ``config.json`` kann ``runtime`` und
    ``state`` auf produktive Pfade legen (im Läufer: EROFS).
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
            "vibe_feedback_under_test", str(CLI)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    return module


def non_empty_lines(text):
    return [line for line in text.splitlines() if line.strip()]


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
        self.cli = load_cli(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def feedback_text(self):
        return (self.project / "FEEDBACK.md").read_text(encoding="utf-8")


class FeedbackMarkdownTest(FeedbackFixture):
    def test_writes_only_title_and_description(self):
        number = self.cli.add_feedback("proj", "Neuer Punkt", "Nur diese Beschreibung.")

        self.assertEqual(number, 1)
        self.assertEqual(
            non_empty_lines(self.feedback_text()),
            ["- [ ] F1 Neuer Punkt", "  Beschreibung: Nur diese Beschreibung."],
        )
        for field in REMOVED_FIELDS:
            self.assertNotIn(field, self.feedback_text())

    def test_second_entry_keeps_numbering_and_format(self):
        self.cli.add_feedback("proj", "Erster", "Beschreibung A")
        number = self.cli.add_feedback("proj", "Zweiter", "Beschreibung B")

        self.assertEqual(number, 2)
        self.assertEqual(
            non_empty_lines(self.feedback_text()),
            [
                "- [ ] F1 Erster",
                "  Beschreibung: Beschreibung A",
                "- [ ] F2 Zweiter",
                "  Beschreibung: Beschreibung B",
            ],
        )


class FeedbackPromptTest(FeedbackFixture):
    def test_prompts_title_and_description_only(self):
        prompts = []

        def answer(prompt=""):
            prompts.append(prompt)
            return {
                "Titel: ": "Titel aus der CLI",
                "Beschreibung: ": "Beschreibung aus der CLI",
            }.get(prompt, "")

        with mock.patch("builtins.input", answer):
            self.cli.cmd_feedback("proj")

        self.assertEqual(prompts, ["Titel: ", "Beschreibung: "])
        self.assertEqual(
            non_empty_lines(self.feedback_text()),
            [
                "- [ ] F1 Titel aus der CLI",
                "  Beschreibung: Beschreibung aus der CLI",
            ],
        )

    def test_empty_title_creates_no_entry(self):
        with mock.patch("builtins.input", lambda prompt="": ""):
            self.cli.cmd_feedback("proj")

        self.assertFalse((self.project / "FEEDBACK.md").exists())


class FeedbackApiTest(unittest.TestCase):
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
        feedback = self.project / "FEEDBACK.md"
        if feedback.exists():
            feedback.unlink()

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

    def test_api_writes_title_and_description_only(self):
        status, body = self.request(
            "/api/feedback",
            {
                "name": "proj",
                "title": "API-Titel",
                "description": "API-Beschreibung",
            },
        )

        self.assertEqual(status, 200, body)
        self.assertIn("F1 eingetragen", body)
        self.assertEqual(
            non_empty_lines(
                (self.project / "FEEDBACK.md").read_text(encoding="utf-8")
            ),
            ["- [ ] F1 API-Titel", "  Beschreibung: API-Beschreibung"],
        )

    def test_api_ignores_removed_fields(self):
        status, body = self.request(
            "/api/feedback",
            {
                "name": "proj",
                "title": "Alter Aufruf",
                "steps": "Schritt",
                "expected": "Erwartung",
                "ist": "Ist-Zustand",
            },
        )

        self.assertEqual(status, 200, body)
        text = (self.project / "FEEDBACK.md").read_text(encoding="utf-8")
        for field in REMOVED_FIELDS:
            self.assertNotIn(field, text)

    def test_api_rejects_missing_title(self):
        status, body = self.request(
            "/api/feedback", {"name": "proj", "description": "ohne Titel"}
        )

        self.assertEqual(status, 400, body)
        self.assertIn("Titel fehlt", body)
        self.assertFalse((self.project / "FEEDBACK.md").exists())

    def test_detail_page_offers_only_title_and_description(self):
        html = served_page(self.request)

        start = html.index("Feedback eintragen")
        end = html.index("Live-Ausgabe", start)
        card = html[start:end]
        # AP21: Beschriftungen laufen über tr('…'); ältere Stände schrieben
        # den Text direkt. Beide Formen werden erkannt, die Aussage bleibt:
        # genau die Felder Titel und Beschreibung.
        labels = re.findall(
            r"el\('label',\{\},(?:tr\()?'([^']+)'", card
        )
        self.assertEqual(labels, ["Titel", "Beschreibung"])
        self.assertIn("description:f.", card)
        for removed in ("steps", "expected", "ist:"):
            self.assertNotIn(removed, card)


if __name__ == "__main__":
    unittest.main()
