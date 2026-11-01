"""Browserabnahme für Arbeitspakete und Bugmeldungen (F15).

Die Tests starten das echte Dashboard auf einem eigenen Port und bedienen es
mit Chromium über Playwright. Geprüft werden Anlegen, Bearbeiten und Löschen
von Arbeitspaketen in TICKETS.md sowie das Melden eines Bugs in FEEDBACK.md.
"""
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"
SHOTS = Path(
    os.environ.get("VIBE_VERIFY_SCREENSHOT_DIR", REPO / "docs" / "features")
)
SHOT = SHOTS / "F15-arbeitspakete.png"

TICKETS = """# TICKETS — Test

- [ ] F15 Arbeitspakete
  Beschreibung: Bestehendes Paket
  Priorität: P1

- [x] V-001 Erledigtes Paket
  Beschreibung: Fertig
  Commit: abcdef1; Test: test_x
"""

FEEDBACK = """# FEEDBACK — Test

- [ ] F1 Bestehender Punkt
  Beschreibung: Bestehende Beschreibung
"""

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


class WorkPackageBrowserTest(unittest.TestCase):
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
        env = isolated_env(cls.root, cls.home, cls.port)
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
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
        (self.project / "TICKETS.md").write_text(TICKETS, encoding="utf-8")
        (self.project / "FEEDBACK.md").write_text(FEEDBACK, encoding="utf-8")
        (self.log_dir / "proj.log").write_text("Startzeile\n", encoding="utf-8")
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

    def ticket_text(self):
        return (self.project / "TICKETS.md").read_text(encoding="utf-8")

    def feedback_text(self):
        return (self.project / "FEEDBACK.md").read_text(encoding="utf-8")

    def open_detail(self):
        self.page.goto(self.base + "/#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        self.page.locator("#tickets").wait_for()
        self.page.get_by_role("tab", name="Arbeit", exact=True).wait_for()

    def test_add_edit_and_delete_a_work_package(self):
        self.open_detail()

        form = self.page.locator("#ticket-new")
        form.locator("input[aria-label='ID des Arbeitspakets']").fill("F18")
        form.locator("input").nth(1).fill("Neues Paket")
        form.locator("textarea").fill("Zeile eins\nZeile zwei")
        form.get_by_role("button", name="Arbeitspaket anlegen").click()

        self.wait_until(
            lambda: "F18 Neues Paket" in self.ticket_text(),
            message="Neues Arbeitspaket wurde nicht gespeichert",
        )
        text = self.ticket_text()
        self.assertIn("- [ ] F18 Neues Paket", text)
        self.assertIn("  Beschreibung: Zeile eins\n  Zeile zwei", text)
        self.assertIn("- [ ] F15 Arbeitspakete", text)

        entry = self.page.locator('#tickets .fbentry[data-id="F18"]')
        entry.get_by_role("button", name="Bearbeiten").click()
        entry.locator("input").fill("Geändertes Paket")
        entry.locator("textarea").fill("Geänderte Beschreibung")
        entry.get_by_role("button", name="Speichern").click()

        self.wait_until(
            lambda: "F18 Geändertes Paket" in self.ticket_text(),
            message="Bearbeitetes Arbeitspaket wurde nicht gespeichert",
        )
        text = self.ticket_text()
        self.assertIn("- [ ] F18 Geändertes Paket", text)
        self.assertIn("  Beschreibung: Geänderte Beschreibung", text)
        self.assertIn("  Priorität: P1", text)
        self.assertIn("- [ ] F15 Arbeitspakete", text)

        entry = self.page.locator('#tickets .fbentry[data-id="F18"]')
        entry.get_by_role("button", name="Löschen").click()
        entry.locator(".confirm").get_by_role("button", name="Ja, löschen").click()
        self.wait_until(
            lambda: "F18 Geändertes Paket" not in self.ticket_text(),
            message="Arbeitspaket wurde nicht gelöscht",
        )
        text = self.ticket_text()
        self.assertIn("- [ ] F15 Arbeitspakete", text)
        self.assertIn("V-001 Erledigtes Paket", text)

    def test_report_a_bug_from_the_ui(self):
        self.open_detail()

        form = self.page.locator("#bug-new")
        form.locator("input").fill("Absturz beim Start")
        form.locator("textarea").fill("Fenster bleibt leer")
        form.get_by_role("button", name="Bug melden").click()

        self.wait_until(
            lambda: "B1 Absturz beim Start" in self.feedback_text(),
            message="Bugmeldung wurde nicht gespeichert",
        )
        text = self.feedback_text()
        self.assertIn("- [ ] B1 Absturz beim Start", text)
        self.assertIn("  Art: Bug", text)
        self.assertIn("  Beschreibung: Fenster bleibt leer", text)
        self.assertIn("- [ ] F1 Bestehender Punkt", text)

        entry = self.page.locator('#feedback .fbentry[data-id="B1"]')
        entry.wait_for()
        self.assertIn("Bug", entry.inner_text())
        self.assertIn("Absturz beim Start", entry.inner_text())

        SHOTS.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(SHOT))
        self.assertTrue(SHOT.is_file())
        self.assertGreater(SHOT.stat().st_size, 10000)


if __name__ == "__main__":
    unittest.main()
