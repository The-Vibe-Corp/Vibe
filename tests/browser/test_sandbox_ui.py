"""Browserabnahme für die Sandbox-Karte im Projektdetail (F7).

Das echte Dashboard läuft auf einem eigenen Port und wird mit Chromium über
Playwright bedient. Geprüft werden Zustandsanzeige, Ein- und Ausschalten,
Build-Werkzeuge, die Prüfung sowie der Screenshot der Karte.
"""
import os
import shutil
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
SHOT = Path(os.environ.get("VIBE_VERIFY_SCREENSHOT_DIR", REPO / "docs" / "features")) / "F7-sandbox.png"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def read_env_file(path):
    data = {}
    if not Path(path).exists():
        return data
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


class SandboxBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert shutil.which("bwrap") is not None, "bubblewrap (bwrap) fehlt"
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.port = free_port()
        env = os.environ.copy()
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.home),
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
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1000})

    def tearDown(self):
        self.page.close()

    def wait_until(self, predicate, timeout=20, message="Bedingung nicht erfüllt"):
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
        self.page.get_by_role("tab", name="Einstellungen", exact=True).click()
        self.page.locator("#sandbox").wait_for()

    def sandbox_card(self):
        return self.page.locator("#sandbox")

    def env_values(self):
        return read_env_file(self.project / ".vibe" / "project.env")

    def toasts(self):
        return self.page.locator("#toasts .toast").all_inner_texts()

    def test_card_switches_on_sets_tools_checks_and_switches_off(self):
        self.open_detail()
        card = self.sandbox_card()
        card.get_by_text("Sandbox (Shell und Build-Werkzeuge)").wait_for()
        self.assertIn("aus", card.inner_text())
        self.assertIn(
            "Ohne Sandbox bleiben Shell-Befehle (bash) außerhalb der Liste möglich.",
            card.inner_text(),
        )

        card.get_by_role("button", name="Sandbox einschalten").click()
        self.wait_until(
            lambda: self.env_values().get("SANDBOX") == "on",
            message="Sandbox wurde nicht eingeschaltet",
        )
        self.wait_until(
            lambda: self.sandbox_card().get_by_text("bereit", exact=True).count() == 1,
            message="Karte zeigt nach dem Einschalten nicht bereit",
        )
        self.assertEqual(self.env_values().get("SANDBOX_TOOLS"), "git python3")
        card = self.sandbox_card()
        self.assertEqual(
            card.get_by_label("Build-Werkzeuge").input_value(), "git python3"
        )
        self.assertIn("Sandbox aktiv", self.page.locator("body").inner_text())
        self.assertIn(
            "Schreibwerkzeug (edit) und Shell-Befehle (bash) können nur",
            self.page.locator("body").inner_text(),
        )
        self.assertIn(
            "Die Sandbox-Konfiguration (.vibe/project.env, .vibe/permissions.json) "
            "ist im Lauf schreibgeschützt.",
            card.inner_text(),
        )

        card.get_by_label("Build-Werkzeuge").fill("git, python3")
        card.get_by_role("button", name="Werkzeuge speichern").click()
        self.wait_until(
            lambda: self.env_values().get("SANDBOX_TOOLS") == "git python3",
            message="Werkzeugliste wurde nicht gespeichert",
        )

        card = self.sandbox_card()
        card.get_by_role("button", name="Prüfen").click()
        self.wait_until(
            lambda: any("Sandbox bereit" in m for m in self.toasts()),
            message="Prüfung meldete keinen bereiten Zustand: "
            + repr(self.toasts()),
        )
        self.assertIn("git", " ".join(self.toasts()))

        SHOT.parent.mkdir(parents=True, exist_ok=True)
        self.sandbox_card().screenshot(path=str(SHOT))
        self.assertTrue(SHOT.exists() and SHOT.stat().st_size > 0)

        self.sandbox_card().get_by_role("button", name="Sandbox ausschalten").click()
        self.wait_until(
            lambda: self.env_values().get("SANDBOX") == "off",
            message="Sandbox wurde nicht ausgeschaltet",
        )
        self.wait_until(
            lambda: self.sandbox_card().get_by_text("aus", exact=True).count() == 1,
            message="Karte zeigt nach dem Ausschalten nicht aus",
        )


if __name__ == "__main__":
    unittest.main()
