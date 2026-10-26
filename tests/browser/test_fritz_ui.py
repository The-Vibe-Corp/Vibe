"""Browserabnahme für den Fritzbox-Reconnect in der Oberfläche (F5).

Der Test startet das echte Dashboard auf einem eigenen Port und bedient es mit
Chromium über Playwright. Geprüft werden die Karte „Fritzbox-Reconnect“ im Tab
„Umgebung“, das Ein- und Ausschalten der Automatik und der manuelle Reconnect.
Der Reconnect läuft gegen einen nachgebildeten Helfer; es wird kein Router
kontaktiert. Der Screenshot des erfolgreichen Reconnects entsteht in diesem
Test.
"""
import json
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
SHOT = REPO / "docs" / "features" / "F5-fritz.png"

FAKE_HELPER = '''import json, os, sys
log = os.environ.get("FAKE_FRITZ_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"env": os.environ.get("FRITZ_ENV")}) + "\\n")
print("alte IP: 203.0.113.1")
print("neue IP: 203.0.113.9")
sys.exit(0)
'''


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class FritzBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True
        )
        cls.helper = cls.root / "fake-fritz.py"
        cls.helper.write_text(FAKE_HELPER, encoding="utf-8")
        cls.env_file = cls.root / "fritz.env"
        cls.env_file.write_text(
            "FRITZ_ADDR=192.0.2.1\n"
            "FRITZ_USER=testuser\n"
            "FRITZ_PASS=geheim-passwort\n",
            encoding="utf-8",
        )
        cls.fritz_log = cls.root / "fake-fritz.log"
        cls.log_dir = cls.root / "_logs"
        cls.port = free_port()
        env = os.environ.copy()
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.root / "home"),
                "VIBE_FRITZ_PYTHON": sys.executable,
                "VIBE_FRITZ_SCRIPT": str(cls.helper),
                "VIBE_FRITZ_ENV": str(cls.env_file),
                "FAKE_FRITZ_LOG": str(cls.fritz_log),
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
        self.settings = self.root / "_toolchain" / "fritz.json"
        if self.settings.exists():
            self.settings.unlink()
        if self.fritz_log.exists():
            self.fritz_log.unlink()
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1100})
        self.page.add_init_script(
            "window.__alerts = []; window.alert = m => window.__alerts.push(m);"
            "window.confirm = () => true;"
        )

    def tearDown(self):
        self.page.close()

    def wait_until(self, predicate, timeout=15, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def fritz_card(self):
        return self.page.locator(".card", has_text="Fritzbox-Reconnect")

    def test_automation_and_manual_reconnect_are_controllable(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.get_by_role("button", name="Umgebung").click()
        card = self.fritz_card()
        card.wait_for()

        self.assertIn("Automatik: aus", card.inner_text())
        self.assertIn("bereit", card.inner_text())
        self.assertIn("standardmäßig aus", card.inner_text())
        self.assertNotIn("geheim-passwort", self.page.content())
        self.assertFalse(self.settings.exists())

        checkbox = card.get_by_role("checkbox")
        checkbox.check()
        card.get_by_role("button", name="Automatik übernehmen").click()
        self.wait_until(
            lambda: self.settings.is_file()
            and json.loads(self.settings.read_text(encoding="utf-8"))["automation"] is True,
            message="Automatik wurde nicht gespeichert",
        )
        self.fritz_card().get_by_text("Automatik: an").wait_for()

        self.fritz_card().get_by_role("button", name="Jetzt neu verbinden").click()
        self.fritz_card().get_by_text("Reconnect erfolgreich").wait_for(timeout=30)
        self.assertIn("neue IP: 203.0.113.9", self.fritz_card().inner_text())
        self.assertTrue(self.fritz_log.is_file())

        SHOT.parent.mkdir(parents=True, exist_ok=True)
        self.fritz_card().screenshot(path=str(SHOT))
        self.assertTrue(SHOT.exists() and SHOT.stat().st_size > 0)

        card = self.fritz_card()
        card.get_by_role("checkbox").uncheck()
        card.get_by_role("button", name="Automatik übernehmen").click()
        self.wait_until(
            lambda: json.loads(self.settings.read_text(encoding="utf-8"))["automation"] is False,
            message="Automatik wurde nicht ausgeschaltet",
        )
        self.fritz_card().get_by_text("Automatik: aus").wait_for()


if __name__ == "__main__":
    unittest.main()
