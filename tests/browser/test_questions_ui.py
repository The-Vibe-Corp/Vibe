"""Browserabnahme für Rückfragen von Agenten (F16).

Die Tests starten das echte Dashboard auf einem eigenen Port und bedienen es
mit Chromium über Playwright. Eine Rückfrage wird während der geöffneten Seite
gestellt; sie muss samt Auswahlmöglichkeiten erscheinen, eine Benachrichtigung
auslösen und sich über die Oberfläche beantworten lassen.
"""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
WEB = REPO / "bin" / "vibe-web.py"
SHOTS = Path(
    os.environ.get("VIBE_VERIFY_SCREENSHOT_DIR", REPO / "docs" / "features")
)
SHOT = SHOTS / "F16-rueckfragen.png"

# Die Prüfumgebung kann eine produktive vibe-Umgebung erben. Ohne diese Liste
# würde das Dashboard den echten Agentenordner, Zustandsordner und die echte
# Laufzeit lesen und beschreiben.
ISOLATED_ENV = (
    "VIBE",
    "VIBE_NO_CONTAINER",
    "HOME",
    "VIBE_PROFILE",
    "VIBE_INSTALL",
    "VIBE_RUNTIME",
    "VIBE_STATE",
    "VIBE_AGENTS_DIR",
    "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR",
    "VIBE_UI_PORT",
    "VIBE_OPENCODE_PORT",
    "VIBE_UI_BIND",
    "VIBE_CONTAINER",
)


def isolated_env(root, home, port):
    """Umgebung, die ausschließlich im temporären Prüfverzeichnis arbeitet."""
    env = os.environ.copy()
    for key in ISOLATED_ENV:
        env.pop(key, None)
    env.update(
        {
            "VIBE": str(root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(port),
            "HOME": str(home),
            "VIBE_STATE": str(Path(root) / "_toolchain"),
            "VIBE_AGENTS_DIR": str(Path(home) / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(Path(home) / ".config" / "vibe" / "config.json"),
        }
    )
    return env


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class QuestionBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.home = cls.root / "home"
        cls.home.mkdir()
        cls.port = free_port()
        cls.env = isolated_env(cls.root, cls.home, cls.port)
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=cls.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.log_dir / "web.token"
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
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
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
        folder = self.log_dir / "questions"
        if folder.exists():
            for path in folder.iterdir():
                path.unlink()
        state = self.log_dir / "autonomous.json"
        if state.exists():
            state.unlink()
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1000})

    def tearDown(self):
        self.page.close()

    def wait_until(self, predicate, timeout=10, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def ask(self, *arguments):
        result = subprocess.run(
            [sys.executable, str(CLI), "ask", *arguments, "--no-wait", "--project", "proj"],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        match = re.search(r"q[0-9a-f]{12}", result.stdout)
        self.assertIsNotNone(match, result.stdout)
        return match.group(0)

    def answer_files(self):
        folder = self.log_dir / "questions"
        return sorted(folder.glob("*.answer.json")) if folder.exists() else []

    def open_dashboard(self):
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.page.locator("table").first.wait_for()
        self.page.get_by_role("button", name="Projects").wait_for()

    def test_a_question_appears_with_options_and_is_answered(self):
        self.open_dashboard()

        qid = self.ask(
            "Soll die neue Schaltfläche blau werden?",
            "--option", "Ja, blau",
            "--option", "Nein, grau",
        )

        panel = self.page.locator('#questions [data-question="%s"]' % qid)
        panel.wait_for(timeout=10000)
        self.assertIn("Soll die neue Schaltfläche blau werden?", panel.inner_text())
        options = panel.locator("[data-option]")
        self.assertEqual(options.count(), 2)
        self.assertEqual(options.nth(0).inner_text(), "Ja, blau")
        self.assertEqual(options.nth(1).inner_text(), "Nein, grau")

        # Benachrichtigung: sichtbarer Hinweis und Zähler im Seitentitel.
        self.page.locator("#toasts .toast", has_text="Question").wait_for(timeout=10000)
        self.wait_until(
            lambda: "(1)" in self.page.title(),
            message="Der Seitentitel zeigt die offene Rückfrage nicht an",
        )

        SHOTS.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(SHOT))
        self.assertTrue(SHOT.is_file())
        self.assertGreater(SHOT.stat().st_size, 10000)

        panel.get_by_role("button", name="Ja, blau", exact=True).click()

        self.wait_until(
            lambda: self.page.locator("#questions [data-question]").count() == 0,
            message="Die beantwortete Rückfrage bleibt sichtbar",
        )
        self.wait_until(
            lambda: self.page.title() == "vibe",
            message="Der Seitentitel behält den Rückfragen-Zähler",
        )
        answers = self.answer_files()
        self.assertEqual(len(answers), 1)
        answer = json.loads(answers[0].read_text(encoding="utf-8"))
        self.assertEqual(answer["option"], 0)
        self.assertEqual(answer["option_text"], "Ja, blau")
        self.assertEqual(answer["by"], "web")

    def test_a_free_text_answer_is_sent_from_the_ui(self):
        self.open_dashboard()

        qid = self.ask("Wie soll die Begrüßung lauten?")

        panel = self.page.locator('#questions [data-question="%s"]' % qid)
        panel.wait_for(timeout=10000)
        field = panel.get_by_label("Custom answer for " + qid)
        field.fill("Herzlich willkommen")
        panel.get_by_role("button", name="Send answer", exact=True).click()

        self.wait_until(
            lambda: self.page.locator("#questions [data-question]").count() == 0,
            message="Die beantwortete Rückfrage bleibt sichtbar",
        )
        answers = self.answer_files()
        self.assertEqual(len(answers), 1)
        answer = json.loads(answers[0].read_text(encoding="utf-8"))
        self.assertIsNone(answer["option"])
        self.assertEqual(answer["text"], "Herzlich willkommen")

    def test_a_question_can_switch_the_project_to_autonomous_mode(self):
        self.open_dashboard()
        qid = self.ask(
            "Soll ich ohne Rückfrage weitermachen?",
            "--option", "Ja",
            "--option", "Nein",
        )

        panel = self.page.locator('#questions [data-question="%s"]' % qid)
        panel.wait_for(timeout=10000)
        panel.get_by_role("button", name="Decide autonomously", exact=True).click()

        state = self.log_dir / "autonomous.json"
        self.wait_until(
            lambda: state.is_file()
            and json.loads(state.read_text(encoding="utf-8"))["projects"]["proj"]["enabled"],
            message="Der autonome Modus wurde nicht aktiviert",
        )
        self.page.locator(
            "#toasts .toast",
            has_text=re.compile(r"Autonomer Modus|Autonomous mode"),
        ).wait_for(timeout=10000)

    def test_the_project_detail_switches_the_autonomous_mode(self):
        self.open_dashboard()
        self.page.locator("tr.row", has_text="proj").first.click()

        card = self.page.locator("#autonomous")
        card.wait_for(timeout=10000)
        self.assertIn("off", card.inner_text())
        card.get_by_role("button", name="Turn on autonomous mode").click()

        card.get_by_role("button", name="Turn off autonomous mode").wait_for(
            timeout=10000
        )
        state = self.log_dir / "autonomous.json"
        self.assertTrue(
            json.loads(state.read_text(encoding="utf-8"))["projects"]["proj"]["enabled"]
        )

        card.get_by_role("button", name="Turn off autonomous mode").click()
        card.get_by_role("button", name="Turn on autonomous mode").wait_for(
            timeout=10000
        )
        self.assertFalse(
            json.loads(state.read_text(encoding="utf-8"))["projects"].get("proj", {}).get("enabled", False)
        )


if __name__ == "__main__":
    unittest.main()
