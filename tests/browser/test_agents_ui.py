"""Browserabnahme für die Agentenverwaltung (V-010).

Die Tests starten das echte Dashboard auf einem eigenen Port und bedienen es
mit Chromium über Playwright. Geprüft werden:

* sichtbare Namenskonflikte und die tatsächliche Priorität
  (Projektagent überschreibt gleichnamigen globalen Agenten),
* der strukturierte Editor, der unbekannte Frontmatter-Felder erhält,
* die Ablehnung ungültigen Rohtexts ohne Änderung der Datei,
* das Kopieren auf ein vorhandenes Ziel ohne Überschreiben,
* die Wiederherstellung einer Sicherung.

Der Screenshot ``V-010-agenten.png`` entsteht in diesem Test und zeigt die
tatsächliche Oberfläche.
"""
import os
import shutil
import signal
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
SHOT = SHOTS / "V-010-agenten.png"

GLOBAL_AGENT = """---
description: Globaler Agent
mode: subagent
model: opencode/test-modell
temperature: 0.1
color: blau
tools:
  write: true
permission:
  read: allow
  edit: deny
---

Globaler Prompt.
"""

PROJECT_AGENT = """---
description: Projektagent überschreibt global
mode: subagent
permission:
  read: allow
  edit: deny
---

Projekt-Prompt.
"""


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# Die Prüfumgebung erbt eine produktive vibe-Umgebung. Ohne diese Liste würde
# das Dashboard den echten Agentenordner und den echten Zustandsordner lesen
# und beschreiben.
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


class AgentsBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        cls.home = cls.root / "home"
        cls.global_agents = cls.home / ".config" / "opencode" / "agents"
        cls.global_agents.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.port = free_port()
        env = isolated_env(cls.root, cls.home, cls.port)
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        cls.pgid = os.getpgid(cls.proc.pid)
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
        # Von opencode gestartete Hilfsprozesse (npx) können noch in das
        # temporäre HOME schreiben. Sie laufen in der Prozessgruppe des Servers
        # und werden vor dem Aufräumen mit beendet.
        try:
            os.killpg(cls.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        cls.tmp.cleanup()

    def setUp(self):
        (self.global_agents / "tester.md").write_text(
            GLOBAL_AGENT, encoding="utf-8"
        )
        project_agents = self.project / ".opencode" / "agents"
        project_agents.mkdir(parents=True, exist_ok=True)
        (project_agents / "tester.md").write_text(PROJECT_AGENT, encoding="utf-8")
        shutil.rmtree(self.root / "_toolchain" / "agent-backups", ignore_errors=True)
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

    def open_agents(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.get_by_role("button", name="Agenten & Modelle").click()
        self.page.get_by_role("button", name="Neuer Agent").wait_for()
        self.page.get_by_text("Globaler Agent").wait_for()

    def global_row(self):
        return self.page.locator('tr[data-agent="tester"][data-scope="global"]')

    def project_row(self):
        return self.page.locator('tr[data-agent="tester"][data-scope="proj"]')

    def open_global_editor(self):
        self.global_row().get_by_role("button", name="Bearbeiten").click()
        self.page.get_by_role("button", name="In Rohtext übernehmen").wait_for()

    def raw_editor(self):
        return self.page.get_by_label("Datei (Frontmatter + Prompt)")

    def test_list_shows_conflict_and_actual_priority(self):
        self.open_agents()

        # Die Beschreibung des Projektagenten enthält denselben Wortlaut wie die
        # Priorität. Deshalb wird hier die eigene Spalte der jeweiligen Zeile geprüft.
        self.assertEqual(
            self.project_row().locator("td.prio").inner_text().strip(),
            "überschreibt global",
        )
        self.assertIn(
            "wird überschrieben", self.global_row().locator("td.prio").inner_text()
        )
        self.assertEqual(
            self.global_row().locator(".pill.warn", has_text="Konflikt").count(), 1
        )
        self.assertEqual(
            self.project_row().locator(".pill.warn", has_text="Konflikt").count(), 1
        )

        SHOTS.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(SHOT))
        self.assertTrue(SHOT.exists() and SHOT.stat().st_size > 0)

    def test_structured_editor_preserves_unknown_fields_and_saves(self):
        self.open_agents()
        self.open_global_editor()

        unknown = self.page.locator("#agent-unknown").inner_text()
        self.assertIn("color", unknown)
        self.assertIn("tools", unknown)

        self.page.get_by_label("Beschreibung").fill("Global neu")
        self.page.get_by_label("Modus").select_option("primary")
        self.page.get_by_label("Rechte").select_option("lesen")
        self.page.get_by_label("Temperatur").fill("0.7")
        self.page.get_by_label("Max. Schritte").fill("5")
        self.page.get_by_label("Prompt", exact=True).fill("Neuer globaler Prompt.")
        self.page.get_by_role("button", name="In Rohtext übernehmen").click()

        self.wait_until(
            lambda: "Global neu" in self.raw_editor().input_value(),
            message="Strukturierte Änderung erschien nicht im Rohtext",
        )
        raw = self.raw_editor().input_value()
        self.assertIn("color: blau", raw)
        self.assertIn("tools:\n  write: true", raw)
        self.assertIn("Neuer globaler Prompt.", raw)

        self.page.get_by_role("button", name="Speichern", exact=True).click()
        self.wait_until(
            lambda: "Global neu"
            in (self.global_agents / "tester.md").read_text(encoding="utf-8"),
            message="Gespeicherter Agent enthält die neue Beschreibung nicht",
        )
        saved = (self.global_agents / "tester.md").read_text(encoding="utf-8")
        self.assertIn("color: blau", saved)
        self.assertIn("tools:\n  write: true", saved)
        self.assertIn("mode: primary", saved)

    def test_invalid_raw_frontmatter_is_rejected_without_writing(self):
        self.open_agents()
        self.open_global_editor()
        before = (self.global_agents / "tester.md").read_text(encoding="utf-8")

        self.raw_editor().fill("kein Frontmatter\n")
        self.page.get_by_role("button", name="Speichern", exact=True).click()
        self.wait_until(
            lambda: self.page.get_by_text("Frontmatter", exact=False).count() > 0,
            message="Fehlermeldung zum ungültigen Frontmatter fehlt",
        )
        self.assertEqual(
            (self.global_agents / "tester.md").read_text(encoding="utf-8"), before
        )

    def test_invalid_structured_value_is_rejected_without_writing(self):
        self.open_agents()
        self.open_global_editor()
        before = (self.global_agents / "tester.md").read_text(encoding="utf-8")
        raw_before = self.raw_editor().input_value()

        self.page.get_by_label("Temperatur").fill("heiß")
        self.page.get_by_role("button", name="In Rohtext übernehmen").click()
        self.wait_until(
            lambda: self.page.get_by_text("Temperatur muss", exact=False).count() > 0,
            message="Fehlermeldung zur ungültigen Temperatur fehlt",
        )
        self.assertEqual(
            (self.global_agents / "tester.md").read_text(encoding="utf-8"), before
        )
        self.assertEqual(self.raw_editor().input_value(), raw_before)

    def test_copy_to_an_existing_target_is_refused(self):
        self.open_agents()
        self.open_global_editor()
        before = (self.project / ".opencode" / "agents" / "tester.md").read_text(
            encoding="utf-8"
        )

        self.page.get_by_label("Kopieren nach …").select_option("proj")
        self.page.get_by_role("button", name="Kopieren").click()
        self.wait_until(
            lambda: self.page.get_by_text("existiert", exact=False).count() > 0,
            message="Fehlermeldung für vorhandenes Ziel fehlt",
        )
        self.assertEqual(
            (self.project / ".opencode" / "agents" / "tester.md").read_text(
                encoding="utf-8"
            ),
            before,
        )

    def test_a_new_agent_can_be_created_and_deleted(self):
        self.open_agents()
        target = self.global_agents / "neuling.md"

        self.page.get_by_role("button", name="Neuer Agent").click()
        self.page.get_by_label("Name").fill("neuling")
        self.page.get_by_label("Beschreibung").fill("Frischer Agent")
        self.page.get_by_label("Prompt", exact=True).fill("Arbeite sorgfältig.")
        self.page.get_by_role("button", name="Datei aus Eingaben erzeugen").click()
        self.wait_until(
            lambda: "Frischer Agent" in self.raw_editor().input_value(),
            message="Vorlage übernahm die Beschreibung nicht",
        )

        self.page.get_by_role("button", name="Speichern", exact=True).click()
        self.wait_until(target.exists, message="Neuer Agent wurde nicht geschrieben")
        text = target.read_text(encoding="utf-8")
        self.assertIn("description: Frischer Agent", text)
        self.assertIn("Arbeite sorgfältig.", text)

        row = self.page.locator('tr[data-agent="neuling"][data-scope="global"]')
        row.get_by_role("button", name="Bearbeiten").click()
        self.page.get_by_role("button", name="Löschen").click()
        self.page.get_by_role("button", name="Ja, löschen").click()
        self.wait_until(lambda: not target.exists(), message="Agent wurde nicht gelöscht")

    def test_restore_brings_back_the_previous_version(self):
        self.open_agents()
        self.open_global_editor()
        before = (self.global_agents / "tester.md").read_text(encoding="utf-8")

        self.page.get_by_label("Beschreibung").fill("Zwischenstand")
        self.page.get_by_role("button", name="In Rohtext übernehmen").click()
        self.page.get_by_role("button", name="Speichern", exact=True).click()
        self.wait_until(
            lambda: "Zwischenstand"
            in (self.global_agents / "tester.md").read_text(encoding="utf-8"),
            message="Zwischenstand wurde nicht gespeichert",
        )

        self.page.get_by_role("button", name="Sicherungen anzeigen").click()
        restore = self.page.get_by_role("button", name="Wiederherstellen").first
        restore.wait_for()
        restore.click()
        self.page.get_by_role("button", name="Ja, wiederherstellen").click()
        self.wait_until(
            lambda: (self.global_agents / "tester.md").read_text(encoding="utf-8")
            == before,
            message="Sicherung wurde nicht wiederhergestellt",
        )


if __name__ == "__main__":
    unittest.main()
