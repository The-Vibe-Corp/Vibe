"""Browserabnahme für das Projektdetail (F2).

Die Tests starten das echte Dashboard auf einem eigenen Port und bedienen es
mit Chromium über Playwright. Geprüft werden Bearbeiten/Löschen vorhandener
Feedback-Punkte, Pause/Fortsetzen der Live-Ausgabe sowie die Höhe und die
Vergrößerung der Live-Ausgabe.
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

BASELINE = """# FEEDBACK — Rückmeldungen an den Agenten

<!-- Vorlage (nicht abhaken):
  - [ ] F99 Kurztitel
    Beschreibung: ...
-->

- [x] F1 Erledigter Punkt
  Beschreibung: Erste Beschreibung

- [ ] F2 Zweiter Punkt
  Beschreibung: Zweite Beschreibung
"""


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class FeedbackBrowserTest(unittest.TestCase):
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
        cls.port = free_port()
        env = os.environ.copy()
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
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
        (self.project / "FEEDBACK.md").write_text(BASELINE, encoding="utf-8")
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

    def feedback_text(self):
        return (self.project / "FEEDBACK.md").read_text(encoding="utf-8")

    def open_detail(self):
        self.page.goto(self.base + "/#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        self.page.get_by_text("Feedback eintragen").wait_for()
        self.page.get_by_role("tab", name="Arbeit", exact=True).wait_for()

    def open_log(self):
        self.page.get_by_role("tab", name="Ausgabe", exact=True).click()
        self.page.locator("#log").wait_for()

    def test_edit_and_delete_existing_feedback_entries(self):
        self.open_detail()

        first = self.page.locator('.fbentry[data-id="F1"]')
        first.get_by_role("button", name="Bearbeiten").click()
        first.locator("input").fill("Geänderter Titel")
        first.locator("textarea").fill("Geänderte Beschreibung")
        first.get_by_role("button", name="Speichern").click()

        self.wait_until(
            lambda: "Geänderter Titel" in self.feedback_text(),
            message="Bearbeiteter Titel wurde nicht gespeichert",
        )
        text = self.feedback_text()
        self.assertIn("- [x] F1 Geänderter Titel", text)
        self.assertIn("  Beschreibung: Geänderte Beschreibung", text)
        self.assertIn("- [ ] F2 Zweiter Punkt", text)
        self.assertIn("F99 Kurztitel", text)

        second = self.page.locator('.fbentry[data-id="F2"]')
        second.get_by_role("button", name="Löschen").click()
        second.locator(".confirm").get_by_role("button", name="Ja, löschen").click()
        self.wait_until(
            lambda: "F2 Zweiter Punkt" not in self.feedback_text(),
            message="Feedback-Punkt wurde nicht gelöscht",
        )
        text = self.feedback_text()
        self.assertIn("- [x] F1 Geänderter Titel", text)
        self.assertIn("F99 Kurztitel", text)

    def test_live_output_can_be_paused_and_resumed(self):
        self.open_detail()
        self.open_log()
        log = self.page.locator("#log")
        self.wait_until(
            lambda: "Startzeile" in log.inner_text(),
            message="Startzeile erschien nicht in der Live-Ausgabe",
        )

        self.page.get_by_role("button", name="Pause", exact=True).click()
        self.wait_until(
            lambda: self.page.get_by_role(
                "button", name="Fortsetzen", exact=True
            ).count()
            == 1,
            message="Pause-Knopf wechselte nicht auf Fortsetzen",
        )
        with open(self.log_dir / "proj.log", "a", encoding="utf-8") as handle:
            handle.write("Während der Pause\n")
            handle.flush()
        self.page.wait_for_timeout(2500)
        self.assertNotIn(
            "Während der Pause",
            log.inner_text(),
            "Pausierte Ausgabe wurde trotzdem angezeigt",
        )

        self.page.get_by_role("button", name="Fortsetzen", exact=True).click()
        self.wait_until(
            lambda: "Während der Pause" in log.inner_text(),
            message="Fortgesetzte Ausgabe zeigte die gepufferten Zeilen nicht",
        )

    def test_live_output_uses_available_height_and_can_be_enlarged(self):
        self.open_detail()
        self.open_log()
        log = self.page.locator("#log")
        self.page.wait_for_timeout(300)
        viewport = self.page.viewport_size
        box = log.bounding_box()
        self.assertIsNotNone(box)
        self.assertGreater(
            box["height"], 500, "Live-Ausgabe nutzt die verfügbare Höhe nicht"
        )
        self.assertGreaterEqual(
            box["y"] + box["height"],
            viewport["height"] - 40,
            "Live-Ausgabe endet nicht am unteren Rand",
        )

        self.page.get_by_role("button", name="Vergrößern", exact=True).click()
        card = self.page.locator(".logcard")
        self.wait_until(
            lambda: card.bounding_box()["width"] >= viewport["width"] - 30,
            message="Live-Ausgabe wurde nicht vergrößert",
        )
        box = card.bounding_box()
        self.assertLessEqual(box["x"], 12)
        self.assertLessEqual(box["y"], 12)
        self.assertGreaterEqual(box["width"], viewport["width"] - 30)
        self.assertGreaterEqual(box["height"], viewport["height"] - 30)
        self.assertEqual(
            self.page.get_by_role("button", name="Verkleinern", exact=True).count(),
            1,
        )

        self.page.keyboard.press("Escape")
        self.wait_until(
            lambda: card.bounding_box()["width"] < viewport["width"] - 100,
            message="Escape verkleinerte die Live-Ausgabe nicht",
        )


if __name__ == "__main__":
    unittest.main()
