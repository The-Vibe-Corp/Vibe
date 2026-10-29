"""Browserabnahme für F10: Der Laufstatus endet automatisch.

Der Test startet das echte Dashboard auf einem eigenen Port mit einem eigenen
tmux-Server (``TMUX_TMPDIR``). Eine nachgebildete, echte tmux-Sitzung steht für
einen laufenden Agentenlauf. Wird sie beendet, muss das Projektdetail den
Zustand ohne Neuladen auf „gestoppt“ umstellen. Der Screenshot entsteht in
diesem Test.
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
SHOT = Path(os.environ.get("VIBE_VERIFY_SCREENSHOT_DIR", REPO / "docs" / "features")) / "F10-autostop.png"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class RunAutostopBrowserTest(unittest.TestCase):
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
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir()
        # Ohne eigene Rechte ignoriert tmux TMUX_TMPDIR und nutzt den
        # gemeinsamen Server des Nutzers.
        cls.tmux_dir.chmod(0o700)
        cls.log_dir = cls.root / "_logs"
        cls.port = free_port()
        env = os.environ.copy()
        # Ein geerbtes TMUX zeigt sonst auf den Server der Sitzung, in der der
        # Test gestartet wurde; kill-server würde fremde Läufe beenden.
        env.pop("TMUX", None)
        env.pop("TMUX_PANE", None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.root / "home"),
                "TMUX_TMPDIR": str(cls.tmux_dir),
            }
        )
        cls.env = env
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
        cls.tmux("kill-server")
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

    @classmethod
    def tmux(cls, *args):
        return subprocess.run(
            ["tmux", *args],
            env=cls.env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def setUp(self):
        self.session = "vibe-proj"
        self.tmux("kill-session", "-t", self.session)
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1000})

    def tearDown(self):
        self.page.close()
        self.tmux("kill-session", "-t", self.session)

    def wait_until(self, predicate, timeout=15, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.1)
        self.fail(message)

    def pill(self):
        # Statusanzeige im Kopf des Projektdetails (kein test-spezifischer Hook).
        return self.page.locator("main > div.bar").first.locator("span.pill").first

    def open_detail(self):
        self.page.goto(self.base + "/#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        self.pill().wait_for()

    def test_detail_switches_to_stopped_when_the_run_ends(self):
        self.assertEqual(
            self.tmux(
                "new-session", "-d", "-s", self.session, "-c", str(self.project),
                "sleep 60",
            ).returncode,
            0,
        )
        self.open_detail()
        pill = self.pill()
        self.wait_until(
            lambda: pill.inner_text().strip() == "läuft",
            message="Laufender Agentenlauf wurde nicht als aktiv angezeigt",
        )

        self.assertIn("aktiv", pill.get_attribute("title") or "")
        self.assertIn("run", pill.get_attribute("class") or "")

        self.assertEqual(self.tmux("kill-session", "-t", self.session).returncode, 0)
        self.wait_until(
            lambda: pill.inner_text().strip() == "gestoppt",
            message="Projektdetail blieb nach dem Ende des Laufs auf aktiv",
        )

        self.assertNotIn("run", pill.get_attribute("class") or "")
        self.assertIn("beendet", pill.get_attribute("title") or "")

        SHOT.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(SHOT))
        self.assertTrue(SHOT.exists() and SHOT.stat().st_size > 0)


if __name__ == "__main__":
    unittest.main()
