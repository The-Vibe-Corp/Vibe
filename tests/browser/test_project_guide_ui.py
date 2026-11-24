"""Browserabnahme für den Projektassistenten (F9).

Die Tests starten das echte Dashboard auf einem eigenen Port und bedienen es
mit Chromium über Playwright. Der Assistent führt durch die fachlichen
Schritte, legt SPEC.md und fehlende Grundlagen an und übernimmt Agenten-
Entwürfe ausschließlich auf ausdrückliche Anforderung.
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
SHOT = Path(os.environ.get("VIBE_VERIFY_SCREENSHOT_DIR", REPO / "docs" / "features")) / "F9-assistent.png"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def init_git_repo(path):
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


class ProjectGuideBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=test-agent\n", encoding="utf-8"
        )
        init_git_repo(cls.root)
        toolchain = cls.root / "_toolchain"
        toolchain.mkdir()
        shutil.copytree(REPO / "templates", toolchain / "templates")
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
        for name in ("SPEC.md", "TICKETS.md", "AGENTS.md", "FEEDBACK.md", "README.md"):
            path = self.project / name
            if path.exists():
                path.unlink()
        if (self.project / ".vibe" / "guide").exists():
            for draft in (self.project / ".vibe" / "guide").iterdir():
                draft.unlink()
        guide_log = self.log_dir / "proj.guide.log"
        if guide_log.exists():
            guide_log.unlink()
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
        self.page.get_by_role("tab", name="Assistant", exact=True).click()
        self.page.locator("#guide").wait_for()
        self.page.locator('.gstep[data-step="ziel"]').wait_for()

    def step(self, step_id):
        return self.page.locator('.gstep[data-step="%s"]' % step_id)

    def fill(self, step_id, value):
        self.step(step_id).locator("textarea").fill(value)

    def test_guide_lists_steps_and_writes_spec_and_missing_files(self):
        self.open_detail()

        guide = self.page.locator("#guide")
        self.assertRegex(guide.inner_text(), r"0/6 Pflichtschritte|0/6 required steps")
        self.assertEqual(guide.locator(".gstep").count(), 8)
        self.assertIn("SPEC.md", guide.inner_text())
        self.assertFalse((self.project / "SPEC.md").exists())

        answers = {
            "ziel": "Das Projekt prüft Rechnungen.",
            "nutzer": "Buchhaltung im Büro.",
            "umfang": "- Rechnung einlesen",
            "nicht_umfang": "- Mahnwesen",
            "umgebung": "Linux-Container",
            "qualitaet": "Unit-Tests und Prüfskript",
        }
        for step_id, value in answers.items():
            self.fill(step_id, value)

        self.page.get_by_role(
            "button", name="Save answers and create files"
        ).click()

        self.wait_until(
            lambda: "complete" in self.page.locator("#guide").inner_text(),
            message="Assistent meldet die Vollständigkeit nicht",
        )
        self.assertTrue((self.project / "SPEC.md").is_file())
        spec = (self.project / "SPEC.md").read_text(encoding="utf-8")
        self.assertIn("## Produktziel", spec)
        self.assertIn("Das Projekt prüft Rechnungen.", spec)
        self.assertTrue((self.project / "AGENTS.md").is_file())
        self.assertTrue((self.project / "README.md").is_file())
        # GH-48: Der Assistent legt keine Markdown-Ledger mehr an; Tickets
        # entstehen im Dashboard/Ticketspeicher.
        self.assertFalse((self.project / "TICKETS.md").exists())
        self.assertFalse((self.project / "FEEDBACK.md").exists())

        self.assertIn("complete", self.page.locator("#guide").inner_text())

        SHOT.parent.mkdir(parents=True, exist_ok=True)
        self.page.locator("#guide").screenshot(path=str(SHOT))
        self.assertTrue(
            SHOT.exists() and SHOT.stat().st_size > 0,
            "Screenshot der Assistenten-Karte fehlt",
        )

    def test_existing_filled_section_is_not_replaced_when_only_another_step_is_answered(self):
        (self.project / "SPEC.md").write_text(
            "# proj — Produktspezifikation\n\n## Produktziel\n\nBestehendes Ziel.\n",
            encoding="utf-8",
        )
        self.open_detail()

        self.assertRegex(
            self.step("ziel").inner_text(), r"gefüllt|filled")
        self.assertEqual(self.step("ziel").locator("textarea").input_value(), "Bestehendes Ziel.")
        self.fill("umfang", "- Neue Funktion")

        self.page.get_by_role(
            "button", name="Save answers and create files"
        ).click()

        self.wait_until(
            lambda: "Neue Funktion"
            in (self.project / "SPEC.md").read_text(encoding="utf-8"),
            message="neuer Abschnitt wurde nicht geschrieben",
        )
        spec = (self.project / "SPEC.md").read_text(encoding="utf-8")
        self.assertIn("Bestehendes Ziel.", spec)
        self.assertIn("## Produktziel", spec)

    def test_agent_draft_is_only_applied_on_explicit_request(self):
        folder = self.project / ".vibe" / "guide"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "ziel.md").write_text(
            "Vom Agenten entworfenes Ziel.\n", encoding="utf-8"
        )
        self.open_detail()

        draft = self.step("ziel")
        self.assertRegex(draft.inner_text(), r"Entwurf des Agenten|Agent draft")
        self.assertIn("Vom Agenten entworfenes Ziel.", draft.inner_text())
        self.assertFalse((self.project / "SPEC.md").exists())

        draft.get_by_role("button", name="Apply draft").click()

        self.wait_until(
            lambda: not (folder / "ziel.md").exists(),
            message="Entwurf wurde nicht entfernt",
        )
        self.assertTrue((self.project / "SPEC.md").is_file())
        self.assertIn(
            "Vom Agenten entworfenes Ziel.",
            (self.project / "SPEC.md").read_text(encoding="utf-8"),
        )

    def test_finished_agent_run_shows_its_output_even_without_a_draft(self):
        """Ein gescheiterter Agentenlauf darf nicht unsichtbar bleiben."""
        (self.log_dir / "proj.guide.log").write_text(
            "Modus: offen\nError: Agent not found: test-agent\n", encoding="utf-8"
        )

        self.open_detail()

        guide = self.page.locator("#guide")
        self.assertRegex(guide.inner_text(), r"Agentenauftrag|Agent task")
        self.assertRegex(guide.inner_text(), r"beendet|finished")
        self.assertIn("Agent not found: test-agent", guide.inner_text())


if __name__ == "__main__":
    unittest.main()
