"""Browserabnahme für Arbeitspakete und Bugmeldungen (F15).

Die Tests starten das echte Dashboard auf einem eigenen Port und bedienen es
mit Chromium über Playwright. Geprüft werden Anlegen, Bearbeiten und Löschen
von Arbeitspaketen in TICKETS.md sowie das Melden eines Bugs in FEEDBACK.md.
"""
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
        self.page.get_by_role("tab", name="Work", exact=True).wait_for()

    def test_add_edit_and_delete_a_work_package(self):
        self.open_detail()

        form = self.page.locator("#ticket-new")
        form.locator(
            "input[aria-label='ID des Arbeitspakets'], "
            "input[aria-label='Work package ID']").fill("F18")
        form.locator("input").nth(1).fill("Neues Paket")
        form.locator("textarea").fill("Zeile eins\nZeile zwei")
        form.get_by_role("button", name="Create work package").click()

        self.wait_until(
            lambda: "F18 Neues Paket" in self.ticket_text(),
            message="Neues Arbeitspaket wurde nicht gespeichert",
        )
        text = self.ticket_text()
        self.assertIn("- [ ] F18 Neues Paket", text)
        self.assertIn("  Beschreibung: Zeile eins\n  Zeile zwei", text)
        self.assertIn("- [ ] F15 Arbeitspakete", text)

        entry = self.page.locator('#tickets .fbentry[data-id="F18"]')
        entry.get_by_role("button", name="Edit").click()
        entry.locator("input").fill("Geändertes Paket")
        entry.locator("textarea").fill("Geänderte Beschreibung")
        entry.get_by_role("button", name="Save").click()

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
        entry.get_by_role("button", name="Delete").click()
        entry.locator(".confirm").get_by_role("button", name="Yes, delete").click()
        self.wait_until(
            lambda: "F18 Geändertes Paket" not in self.ticket_text(),
            message="Arbeitspaket wurde nicht gelöscht",
        )
        text = self.ticket_text()
        self.assertIn("- [ ] F15 Arbeitspakete", text)
        self.assertIn("V-001 Erledigtes Paket", text)

    def test_add_work_package_without_an_id_and_use_the_assigned_id(self):
        """F23/AK8: Das Formular-Feld "ID des Arbeitspakets" bleibt leer.
        Server und Oberfläche vergeben dann automatisch eine ID; sie wird
        hier dynamisch gelesen ( Inhaltsliste ) und anschließend bearbeitet
        und gelöscht."""
        self.open_detail()

        form = self.page.locator("#ticket-new")
        # Das ID-Eingabefeld bleibt absichtlich leer.
        form.locator("input").nth(1).fill("Auto Paket")
        form.locator("textarea").fill("Zeile eins\nZeile zwei")
        form.get_by_role("button", name="Create work package").click()

        def assigned_id():
            ids = self.page.eval_on_selector_all(
                "#tickets .fbentry", "els => els.map(e => e.dataset.id)"
            )
            fresh = [i for i in ids if i not in ("F15", "V-001")]
            return fresh[0] if len(fresh) == 1 else None

        self.wait_until(
            lambda: assigned_id() is not None,
            message="Arbeitspaket ohne ID wurde nicht angelegt",
        )
        assigned = assigned_id()
        self.assertTrue(assigned)
        self.assertRegex(assigned, r"[A-Za-z0-9][A-Za-z0-9_.:-]*")

        text = self.ticket_text()
        self.assertIn("- [ ] %s Auto Paket" % assigned, text)
        self.assertIn("  Beschreibung: Zeile eins\n  Zeile zwei", text)
        self.assertIn("- [ ] F15 Arbeitspakete", text)
        self.assertIn("- [x] V-001 Erledigtes Paket", text)

        self.wait_until(
            lambda: f"{assigned} angelegt"
            in "\n".join(
                self.page.locator(".toasttext").all_inner_texts()
            ),
            message="Meldung nennt nicht die tatsächlich vergebene ID",
        )

        entry = self.page.locator(
            '#tickets .fbentry[data-id="%s"]' % assigned
        )
        entry.get_by_role("button", name="Edit").click()
        entry.locator("textarea").fill("Geänderte Beschreibung")
        entry.get_by_role("button", name="Save").click()

        self.wait_until(
            lambda: "  Beschreibung: Geänderte Beschreibung"
            in self.ticket_text()
            and "- [ ] %s Auto Paket" % assigned in self.ticket_text(),
            message="Bearbeitetes Auto-Arbeitspaket wurde nicht gespeichert",
        )

        entry = self.page.locator(
            '#tickets .fbentry[data-id="%s"]' % assigned
        )
        entry.get_by_role("button", name="Delete").click()
        entry.locator(".confirm").get_by_role("button", name="Yes, delete").click()
        self.wait_until(
            lambda: "Auto Paket" not in self.ticket_text(),
            message="Auto-Arbeitspaket wurde nicht gelöscht",
        )
        text = self.ticket_text()
        self.assertIn("- [ ] F15 Arbeitspakete", text)
        self.assertIn("V-001 Erledigtes Paket", text)

    def test_report_a_bug_from_the_ui(self):
        self.open_detail()

        form = self.page.locator("#bug-new")
        form.locator("input").fill("Absturz beim Start")
        form.locator("textarea").fill("Fenster bleibt leer")
        form.get_by_role("button", name="Report bug").click()

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
