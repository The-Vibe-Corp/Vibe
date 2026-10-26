"""Browserabnahme für die Pause nach dem aktuellen Arbeitspaket (F4).

Der Test startet das echte Dashboard auf einem eigenen Port und bedient es mit
Chromium über Playwright. Geprüft wird, dass die Pause im Projektdetail
angefordert und wieder aufgehoben werden kann, dass der Zustand im
Projektüberblick sichtbar ist und dass die Anforderung als Laufzeitmarkierung
geschrieben wird. Der Screenshot der aktivierten Pause entsteht in diesem Test.
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
SHOT = Path(os.environ.get("VIBE_VERIFY_SCREENSHOT_DIR", REPO / "docs" / "features")) / "F4-pause.png"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class PauseBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] F1 Testpaket\n  Beschreibung: Test\n",
            encoding="utf-8",
        )
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True
        )
        cls.log_dir = cls.root / "_logs"
        cls.port = free_port()
        env = os.environ.copy()
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.root / "home"),
            }
        )
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
        self.flag = self.log_dir / "proj.pause-after"
        if self.flag.exists():
            self.flag.unlink()
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1000})
        self.page.add_init_script(
            "window.__alerts = []; window.alert = m => window.__alerts.push(m);"
            "window.confirm = () => true;"
        )

    def tearDown(self):
        self.page.close()

    def wait_until(self, predicate, timeout=10, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def open_detail(self):
        self.page.goto(self.base + "/#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        self.page.get_by_text("Arbeitspaket-Pause").wait_for()

    def pause_card(self):
        return self.page.locator(".card", has_text="Arbeitspaket-Pause")

    def test_pause_is_requested_without_stopping_the_run_and_can_be_released(self):
        self.open_detail()
        card = self.pause_card()
        self.assertIn("keine Pause", card.inner_text())
        self.assertIn("Der laufende Agent wird nicht unterbrochen.", card.inner_text())
        self.assertFalse(self.flag.exists())

        card.get_by_role("button", name="Nach aktuellem Paket anhalten").click()
        self.wait_until(
            lambda: self.flag.is_file(),
            message="Pause-Markierung wurde nicht geschrieben",
        )
        reloaded = self.pause_card()
        reloaded.get_by_text("Pause angefordert").wait_for()
        self.assertIn("Nach dem aktuellen Arbeitspaket", reloaded.inner_text())
        reloaded.get_by_role("button", name="Pause aufheben").wait_for()

        SHOT.parent.mkdir(parents=True, exist_ok=True)
        reloaded.screenshot(path=str(SHOT))
        self.assertTrue(SHOT.exists() and SHOT.stat().st_size > 0)

        reloaded.get_by_role("button", name="Pause aufheben").click()
        self.wait_until(
            lambda: not self.flag.exists(),
            message="Pause-Markierung wurde nicht entfernt",
        )
        self.pause_card().get_by_text("keine Pause").wait_for()

    def test_project_list_marks_a_requested_pause(self):
        self.open_detail()
        self.pause_card().get_by_role(
            "button", name="Nach aktuellem Paket anhalten"
        ).click()
        self.wait_until(lambda: self.flag.is_file(), message="Pause fehlt")

        self.page.get_by_role("button", name="← zurück").click()
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.get_by_text("Pause").wait_for()


if __name__ == "__main__":
    unittest.main()
