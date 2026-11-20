"""Browserabnahme für abgeschlossene Feedback-Punkte (F8).

Die Tests starten das echte Dashboard auf einem eigenen Port und bedienen es
mit Chromium über Playwright. Abgeschlossene Punkte (Checkbox gesetzt und
Nachweis vorhanden) sollen im Standard ausgeblendet und nicht bearbeitbar
sein; gesetzte Punkte ohne Nachweis gelten nicht als abgeschlossen.
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


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def init_git_repo(path):
    """Legt ein Repository mit einem Commit an und liefert dessen Kurzhash."""
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "init",
        ],
        cwd=path,
        check=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class FeedbackCompletedBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        cls.commit = init_git_repo(cls.root)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir()
        cls.port = free_port()
        env = os.environ.copy()
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                # Isolation: Ohne VIBE_RUNTIME würde die persönliche
                # Konfiguration des Entwicklers einen Laufzeitordner
                # außerhalb des Temp-Bereichs wählen (im Sandbox-Lauf
                # schreibgeschützt).
                "VIBE_RUNTIME": str(cls.log_dir),
                # Isolation: Auch der Zustandsordner (vibe.json mit
                # zusätzlichen Entwicklungsordnern) kommt aus der
                # persönlichen Konfiguration. Ohne eigene VIBE_STATE listet
                # die Oberfläche fremde Projekte, und "tr.row" mit
                # Teiltreffer öffnet das falsche Projekt.
                "VIBE_STATE": str(cls.state_dir),
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
        (self.project / "FEEDBACK.md").write_text(
            "# FEEDBACK — Rückmeldungen an den Agenten\n\n"
            "- [x] F1 Erledigter Punkt\n"
            "  Beschreibung: Erste Beschreibung\n"
            f"  Commit: {self.commit}; Test: test_erledigt\n\n"
            "- [x] F2 Ohne Nachweis\n"
            "  Beschreibung: Zweite Beschreibung\n\n"
            "- [ ] F3 Offener Punkt\n"
            "  Beschreibung: Dritte Beschreibung\n",
            encoding="utf-8",
        )
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

    def open_detail(self):
        self.page.goto(self.base + "/classic#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        self.page.get_by_text("Add feedback").wait_for()
        self.page.locator("#feedback").wait_for()

    def toggle(self):
        return self.page.locator("#feedback").get_by_role(
            "button", name=re.compile(r"Abgeschlossene|completed", re.I)
        )

    def test_completed_entries_are_hidden_by_default_and_can_be_shown(self):
        self.open_detail()

        self.assertEqual(
            self.page.locator('.fbentry[data-id="F1"]').count(),
            0,
            "abgeschlossener Punkt F1 ist im Standard sichtbar",
        )
        self.assertEqual(
            self.page.locator('.fbentry[data-id="F3"]').count(),
            1,
            "offener Punkt F3 fehlt",
        )
        self.assertRegex(
            self.toggle().inner_text(),
            r"anzeigen \(1\)|Show completed \(1\)")

        self.toggle().click()

        self.wait_until(
            lambda: self.page.locator('.fbentry[data-id="F1"]').count() == 1,
            message="abgeschlossener Punkt wurde nicht eingeblendet",
        )
        self.assertRegex(
            self.toggle().inner_text(), r"ausblenden|Hide completed")
        self.assertEqual(self.page.locator('.fbentry[data-id="F1"]').count(), 1)

        self.toggle().click()

        self.wait_until(
            lambda: self.page.locator('.fbentry[data-id="F1"]').count() == 0,
            message="abgeschlossener Punkt wurde nicht wieder ausgeblendet",
        )

    def test_completed_entry_offers_no_edit_control(self):
        self.open_detail()
        self.toggle().click()
        self.wait_until(
            lambda: self.page.locator('.fbentry[data-id="F1"]').count() == 1,
            message="abgeschlossener Punkt wurde nicht eingeblendet",
        )

        completed = self.page.locator('.fbentry[data-id="F1"]')
        self.assertEqual(
            completed.get_by_role("button", name="Edit").count(),
            0,
            "abgeschlossener Punkt lässt sich weiterhin bearbeiten",
        )
        self.assertRegex(completed.inner_text(), r"nicht bearbeitbar|read-only")
        self.assertEqual(
            completed.get_by_role("button", name="Delete").count(),
            1,
            "Löschen abgeschlossener Punkte ist nicht mehr möglich",
        )

        open_entry = self.page.locator('.fbentry[data-id="F3"]')
        self.assertEqual(open_entry.get_by_role("button", name="Edit").count(), 1)

    def test_checked_entry_without_proof_stays_visible_and_editable(self):
        self.open_detail()

        unproven = self.page.locator('.fbentry[data-id="F2"]')
        self.assertEqual(
            unproven.count(),
            1,
            "gesetzter Punkt ohne Nachweis wurde wie abgeschlossen ausgeblendet",
        )
        self.assertEqual(unproven.get_by_role("button", name="Edit").count(), 1)


if __name__ == "__main__":
    unittest.main()
