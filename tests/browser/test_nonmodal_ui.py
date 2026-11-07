"""Browserabnahme für nicht-modale Rückmeldungen und Bestätigungen (F11).

Die Tests starten das echte Dashboard auf einem eigenen Port und bedienen es
mit Chromium über Playwright. Geprüft wird, dass die Oberfläche keine modalen
Browserdialoge (alert/confirm/prompt) mehr öffnet:

* Rückmeldungen erscheinen als nicht blockierende Statusmeldungen
  (aria-live=polite) und die Seite bleibt bedienbar.
* Löschen fragt im Kontext nach (Inline-Bestätigung); Abbrechen lässt den
  Eintrag unverändert.
* Auch das Beenden des Dashboards wird inline bestätigt; Abbrechen beendet
  nichts.

Jeder Test registriert einen Dialog-Handler: ein echter alert/confirm/prompt
würde dort auftauchen und die Assertions verletzen.
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
SHOTS = Path(os.environ.get("VIBE_VERIFY_SCREENSHOT_DIR", REPO / "docs" / "features"))
TOAST_SHOT = SHOTS / "F11-toast.png"
CONFIRM_SHOT = SHOTS / "F11-bestaetigung.png"

FEEDBACK = (
    "# FEEDBACK — Test\n\n"
    "- [ ] F1 Erster Punkt\n"
    "  Beschreibung: Erste Beschreibung\n\n"
    "- [ ] F2 Zweiter Punkt\n"
    "  Beschreibung: Zweite Beschreibung\n"
)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class NonModalBrowserTest(unittest.TestCase):
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
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
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
        self.feedback = self.project / "FEEDBACK.md"
        self.feedback.write_text(FEEDBACK, encoding="utf-8")
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1000})
        self.dialogs = []
        self.page.on("dialog", self._record_dialog)

    def tearDown(self):
        self.page.close()

    def _record_dialog(self, dialog):
        self.dialogs.append({"type": dialog.type, "message": dialog.message})
        dialog.dismiss()

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
        self.page.get_by_text("Feedback eintragen").wait_for()
        self.page.locator("#feedback").wait_for()

    def assert_no_browser_dialog(self):
        self.assertEqual(
            self.dialogs, [], "modaler Browserdialog wurde geöffnet: " + repr(self.dialogs)
        )

    def test_action_feedback_is_a_non_blocking_status_message(self):
        self.open_detail()
        box = self.page.locator("#toasts")
        self.assertEqual(box.get_attribute("role"), "status")
        self.assertEqual(box.get_attribute("aria-live"), "polite")

        form = self.page.locator(".card", has_text="Feedback eintragen")
        form.locator("input").fill("Neuer Punkt aus der Oberfläche")
        form.locator("textarea").fill("Beschreibung aus der Oberfläche")
        form.get_by_role("button", name="Eintragen").click()

        message = self.page.locator("#toasts .toast", has_text="F3 eingetragen")
        message.wait_for()
        self.assertIn("F3 eingetragen", message.inner_text())
        self.assert_no_browser_dialog()
        self.assertEqual(
            self.page.locator("dialog[open]").count(),
            0,
            "es wurde ein modaler Dialog geöffnet",
        )

        SHOTS.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(TOAST_SHOT))
        self.assertTrue(TOAST_SHOT.exists() and TOAST_SHOT.stat().st_size > 0)

        # Die Meldung darf die Bedienung nicht blockieren.
        self.page.get_by_role("button", name="Umgebung").click()
        self.page.get_by_text("Umgebungsprüfung").wait_for()
        self.assert_no_browser_dialog()

        message.get_by_role("button", name="Meldung schließen").click()
        self.wait_until(
            lambda: self.page.locator("#toasts .toast", has_text="F3 eingetragen").count() == 0,
            message="Meldung ließ sich nicht schließen",
        )
        with open(self.feedback, encoding="utf-8") as handle:
            self.assertIn("Neuer Punkt aus der Oberfläche", handle.read())

    def test_delete_asks_inline_and_cancel_keeps_the_entry(self):
        self.open_detail()
        entry = self.page.locator('.fbentry[data-id="F2"]')
        # exact=True: sonst trifft der Locator auch „Ja, löschen“ aus der
        # Bestätigung, sobald diese sichtbar ist.
        delete = entry.get_by_role("button", name="Löschen", exact=True)

        delete.click()
        question = entry.locator(".confirm")
        question.wait_for()
        self.assertIn("wirklich löschen", question.inner_text())
        self.assertFalse(delete.is_visible(), "Löschen-Schaltfläche bleibt daneben aktiv")
        self.assert_no_browser_dialog()
        self.assertIn("F2 Zweiter Punkt", self.feedback.read_text(encoding="utf-8"))

        SHOTS.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(CONFIRM_SHOT))
        self.assertTrue(CONFIRM_SHOT.exists() and CONFIRM_SHOT.stat().st_size > 0)

        question.get_by_role("button", name="Abbrechen").click()
        self.wait_until(
            lambda: entry.locator(".confirm").count() == 0,
            message="Inline-Bestätigung wurde nicht geschlossen",
        )
        self.assertTrue(delete.is_visible(), "Löschen-Schaltfläche ist nach Abbruch versteckt")
        self.assertIn("F2 Zweiter Punkt", self.feedback.read_text(encoding="utf-8"))
        self.assert_no_browser_dialog()

        # Tastatur: Fokus liegt auf der Bestätigung, Escape bricht ab.
        delete.click()
        question.wait_for()
        self.assertEqual(
            self.page.evaluate("document.activeElement.textContent"),
            "Ja, löschen",
            "Fokus liegt nicht auf der Bestätigung",
        )
        self.page.keyboard.press("Escape")
        self.wait_until(
            lambda: entry.locator(".confirm").count() == 0,
            message="Escape hat die Inline-Bestätigung nicht geschlossen",
        )
        self.assertTrue(delete.is_visible(), "Löschen-Schaltfläche ist nach Escape versteckt")
        self.assertIn("F2 Zweiter Punkt", self.feedback.read_text(encoding="utf-8"))
        self.assert_no_browser_dialog()

        delete.click()
        entry.locator(".confirm").get_by_role("button", name="Ja, löschen").click()
        self.wait_until(
            lambda: "F2 Zweiter Punkt" not in self.feedback.read_text(encoding="utf-8"),
            message="Bestätigtes Löschen hat den Punkt nicht entfernt",
        )
        self.page.locator("#toasts .toast", has_text="F2 gelöscht").wait_for()
        self.assert_no_browser_dialog()

    def test_shutdown_asks_inline_and_cancel_keeps_the_dashboard_running(self):
        self.open_detail()
        quit_button = self.page.get_by_role("button", name="Dashboard beenden")
        quit_button.click()

        question = self.page.locator("header .confirm")
        question.wait_for()
        self.assertIn("laufen weiter", question.inner_text())
        self.assert_no_browser_dialog()
        self.assertIsNone(self.proc.poll(), "Dashboard wurde vor der Bestätigung beendet")

        question.get_by_role("button", name="Abbrechen").click()
        self.wait_until(
            lambda: self.page.locator("header .confirm").count() == 0,
            message="Inline-Bestätigung wurde nicht geschlossen",
        )
        self.assertTrue(quit_button.is_visible())
        self.assertIsNone(self.proc.poll(), "Abbrechen hat das Dashboard beendet")
        self.page.get_by_text("Feedback eintragen").wait_for()


if __name__ == "__main__":
    unittest.main()
