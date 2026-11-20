"""Browserabnahme zentraler Nutzerabläufe und der Releaseanzeige (V-020).

Die Tests starten das echte Dashboard auf einem eigenen Port und bedienen es
mit Chromium über Playwright. Sie prüfen den durchgängigen Hauptablauf
(Projektliste → Projektdetail → Arbeitspaket anlegen → Prüfung starten →
zurück zur Projektliste) sowie die Umgebungs- und Releaseanzeige. Die
Releaseanzeige nennt Version und Commit des laufenden Stands; sie ist die
Grundlage dafür, eine installierte Releasebasis eindeutig zu erkennen.
"""
import json
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

TICKETS = """# TICKETS — Test

- [ ] V-900 Bestehendes Paket
  Beschreibung: Bleibt erhalten
  Priorität: P1
"""

FEEDBACK = """# FEEDBACK — Test

- [ ] F1 Bestehender Punkt
  Beschreibung: Bleibt erhalten
"""


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class CentralWorkflowBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            'TYPE=generic\nVERIFY_QUICK="echo V020-PRUEFUNG"\n', encoding="utf-8"
        )
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True
        )
        toolchain = cls.root / "_toolchain"
        shutil.copytree(REPO / "templates", toolchain / "templates")
        (toolchain / "version.json").write_text(
            json.dumps(
                {
                    "version": "0.18.0",
                    "commit": "abcdef1",
                    "installed_at": "2026-11-03T12:00:00Z",
                    "mode": "update",
                    "source": str(REPO),
                }
            ),
            encoding="utf-8",
        )
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.port = free_port()
        env = os.environ.copy()
        for key in (
            "VIBE_PROFILE",
            "VIBE_INSTALL",
            "VIBE_RUNTIME",
            "VIBE_STATE",
            "VIBE_AGENTS_DIR",
            "VIBE_CONFIG_FILE",
            "VIBE_UI_PORT",
            "VIBE_OPENCODE_PORT",
            "VIBE_UI_BIND",
            "VIBE_CONTAINER",
        ):
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.root / "home"),
                "VIBE_STATE": str(toolchain),
                "VIBE_AGENTS_DIR": str(
                    cls.root / "home" / ".config" / "opencode" / "agents"
                ),
                "VIBE_CONFIG_FILE": str(
                    cls.root / "home" / ".config" / "vibe" / "config.json"
                ),
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
        (self.project / "TICKETS.md").write_text(TICKETS, encoding="utf-8")
        (self.project / "FEEDBACK.md").write_text(FEEDBACK, encoding="utf-8")
        (self.log_dir / "proj.log").write_text("Startzeile\n", encoding="utf-8")
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1000})

    def tearDown(self):
        self.page.close()

    def wait_until(self, predicate, timeout=15, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def ticket_text(self):
        return (self.project / "TICKETS.md").read_text(encoding="utf-8")

    def open_list(self):
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.page.locator("tr.row", has_text="proj").first.wait_for()

    def test_central_flow_lists_opens_creates_and_verifies(self):
        self.open_list()
        row = self.page.locator("tr.row", has_text="proj").first
        cells = row.locator("td")
        self.assertEqual(cells.nth(0).inner_text().strip(), "proj")
        self.assertEqual(cells.nth(1).inner_text().strip(), "generic")
        # Die offene Zahl umfasst Arbeitspakete und Feedback: ein Paket und
        # ein Feedback-Punkt.
        self.assertEqual(cells.nth(3).inner_text().strip(), "2")

        row.click()
        self.page.get_by_role("tab", name="Work", exact=True).wait_for()
        self.assertTrue(self.page.get_by_role("tab", name="Output").is_visible())
        self.assertTrue(
            self.page.locator(".card", has_text="Open work packages (2)").count()
            >= 1
        )

        form = self.page.locator("#ticket-new")
        form.locator(
            "input[aria-label='ID des Arbeitspakets'], "
            "input[aria-label='Work package ID']").fill("V-901")
        form.locator("input").nth(1).fill("Zentraler Ablauf")
        form.locator("textarea").fill("Im Browser angelegt")
        form.get_by_role("button", name="Create work package").click()
        self.wait_until(
            lambda: "- [ ] V-901 Zentraler Ablauf" in self.ticket_text(),
            message="Arbeitspaket wurde nicht gespeichert",
        )

        self.page.get_by_role("button", name="Check quick").click()
        self.wait_until(
            lambda: self.page.locator('[role="tab"][aria-selected="true"]')
            .inner_text()
            .strip()
            == "Output",
            message="Prüfung wechselte nicht zur Ausgabe",
        )
        self.wait_until(
            lambda: "V020-PRUEFUNG"
            in self.page.locator("#log").inner_text(),
            message="Prüfungsausgabe erschien nicht",
        )

        self.page.get_by_role("button", name="← Back").click()
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        self.wait_until(
            lambda: row.locator("td").nth(3).inner_text().strip() == "3",
            message="Projektliste zeigte die neue Paketzahl nicht",
        )

    def test_environment_view_shows_release_and_diagnosis(self):
        self.open_list()
        self.page.get_by_role("button", name="Environment").click()
        self.page.get_by_text("Environment check").wait_for(timeout=60000)

        body = self.page.locator("main").inner_text()
        self.assertIn("Release", body)
        self.assertIn("Environment check", body)
        self.assertIn("Version 0.18.0", body)
        self.assertIn("Commit abcdef1", body)
        self.assertIn("Environment", body)
        self.assertTrue(
            "OK" in body or "FEHL" in body,
            "Umgebungsprüfung zeigte keinen Ergebniszustand: " + body[:400],
        )


if __name__ == "__main__":
    unittest.main()
