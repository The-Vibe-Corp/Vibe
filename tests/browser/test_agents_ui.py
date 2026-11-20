"""Browserabnahme für die allgemeine Agentenverwaltung (AP03).

Die Tests starten das echte Dashboard auf einem eigenen Port und bedienen es
mit Chromium über Playwright. Geprüft werden die in AP03 neu aufgebaute
allgemeine Ansicht und die weiterhin erforderlichen Schutzfunktionen:

* die allgemeine Liste zeigt ausschließlich systemweite Agenten mit Aufgabe,
  Ergebnis, Subagenten-Rechten und Modell,
* der Rollenwechsel schreibt ``profiles.json``,
* der Editor speichert strukturierte Felder und erhält unbekannte
  Frontmatter-Felder,
* ungültiger Rohtext und ungültige strukturierte Werte verändern die Datei
  nicht,
* ein neuer Agent kann angelegt und mit Sicherung gelöscht werden,
* eine Sicherung kann wiederhergestellt werden.

Projektagenten und das frühere Konflikt-/Überschreibungsverhalten werden nicht
mehr erwartet: AP03 erlaubt in Projekten ausschließlich systemweite Agenten.
Der Screenshot ``AP03-agenten.png`` entsteht in ``test_ap03_agents_ui``.
"""
import json
import os
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

FAKE_OPENCODE = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf 'opencode 2.1.4\\n'
    exit 0
    ;;
  models)
    printf 'opencode/test-modell\\nopencode/vibe-modell\\nopencode/neu\\n'
    exit 0
    ;;
esac
exit 2
"""

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
  task: allow
---

Globaler Prompt.
"""

VIBE_AGENT = """---
description: Vibe-Standardagent für Nutzerunterstützung
mode: primary
model: opencode/vibe-modell
permission:
  read: allow
  edit: deny
---

Du unterstützt den Nutzer bei der Benutzung und Konfiguration von vibe.
"""

PROJECT_AGENT = """---
description: Projektlokaler Agent
mode: subagent
permission:
  read: allow
  edit: deny
---

Projekt-Prompt.
"""

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


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def isolated_env(root, home, port, fake_bin):
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
            "VIBE_RUNTIME": str(Path(root) / "_logs"),
            "VIBE_AGENTS_DIR": str(Path(home) / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(Path(home) / ".config" / "vibe" / "config.json"),
            "PATH": str(fake_bin) + os.pathsep + env.get("PATH", ""),
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
        cls.state = cls.root / "_toolchain"
        cls.state.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        fake_bin = cls.root / "fakebin"
        fake_bin.mkdir()
        fake = fake_bin / "opencode"
        fake.write_text(FAKE_OPENCODE, encoding="utf-8")
        fake.chmod(0o755)

        cls._write_fixture()

        cls.port = free_port()
        env = isolated_env(cls.root, cls.home, cls.port, fake_bin)
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
    def _write_fixture(cls):
        (cls.global_agents / "tester.md").write_text(
            GLOBAL_AGENT, encoding="utf-8"
        )
        (cls.global_agents / "vibe-agent.md").write_text(
            VIBE_AGENT, encoding="utf-8"
        )
        project_agents = cls.project / ".opencode" / "agents"
        project_agents.mkdir(parents=True, exist_ok=True)
        (project_agents / "lokal.md").write_text(PROJECT_AGENT, encoding="utf-8")
        (cls.state / "profiles.json").write_text(
            json.dumps({"rollen": {"vibe-agent": "vibe"}}), encoding="utf-8"
        )
        (cls.state / "agent-meta.json").write_text(
            json.dumps({"agents": {"tester": {"result": "Ergebnis global"}}}),
            encoding="utf-8",
        )

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
        # Von opencode gestartete Hilfsprozesse laufen in der Prozessgruppe des
        # Servers und werden vor dem Aufräumen mit beendet.
        try:
            os.killpg(cls.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        cls.tmp.cleanup()

    def setUp(self):
        self._write_fixture()
        backup_dir = self.state / "agent-backups" / "global"
        if backup_dir.exists():
            for item in backup_dir.iterdir():
                item.unlink()
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
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.page.get_by_role("button", name="Agents & Models").click()
        self.page.locator("#agents").wait_for()
        self.page.locator('tr[data-agent="tester"]').wait_for()

    def global_row(self):
        return self.page.locator('tr[data-agent="tester"]')

    def open_global_editor(self):
        self.global_row().get_by_role("button", name="Edit").click()
        self.page.get_by_label("Description", exact=True).wait_for()

    def raw_editor(self):
        return self.page.get_by_label("File (frontmatter + prompt)")

    def backup_files(self):
        folder = self.state / "agent-backups" / "global"
        if not folder.exists():
            return []
        return sorted(folder.iterdir())

    def test_list_shows_only_global_agents_with_aufgabe_ergebnis_rechte_und_modell(self):
        """AK Allgemeine Liste: globaler Agent vollständig, Projektagent nicht."""
        self.open_agents()

        row = self.global_row()
        self.assertEqual(row.count(), 1)
        self.assertIn(
            "Globaler Agent",
            self.page.locator('td[data-aufgabe="tester"]').inner_text(),
        )
        self.assertIn(
            "Ergebnis global",
            self.page.locator('td[data-ergebnis="tester"]').inner_text(),
        )
        self.assertIn(
            "all", self.page.locator('td[data-erlaubt="tester"]').inner_text()
        )
        self.assertIn(
            "opencode/test-modell",
            self.page.locator('td[data-modell="tester"]').inner_text(),
        )
        self.assertEqual(self.page.locator('tr[data-agent="lokal"]').count(), 0)

        self.page.get_by_role("button", name="New agent").click()
        self.page.get_by_label("Role", exact=True).wait_for()
        self.page.get_by_label("Result", exact=True).wait_for()

    def test_role_change_is_saved_in_profiles_and_shown(self):
        """AK Rollen: Änderung über select[data-role] wirkt und bleibt sichtbar."""
        self.open_agents()
        select = self.page.locator('select[data-role="tester"]')
        select.wait_for()
        select.select_option(label="coder")
        self.wait_until(
            lambda: json.loads(
                (self.state / "profiles.json").read_text(encoding="utf-8")
            )
            .get("rollen", {})
            .get("tester")
            == "coder",
            message="Die Rolle wurde nicht in profiles.json gespeichert",
        )

        self.open_agents()
        self.assertEqual(
            self.page.locator('select[data-role="tester"]').input_value(), "coder"
        )

    def test_structured_editor_preserves_unknown_fields_and_saves(self):
        """AK Editor: speichert Felder und erhält unbekannte Frontmatter-Felder."""
        self.open_agents()
        self.open_global_editor()

        self.page.get_by_label("Description", exact=True).fill("Global neu")
        self.page.get_by_label("Mode", exact=True).select_option("primary")
        self.page.get_by_label("Permissions", exact=True).select_option("lesen")
        self.page.get_by_label("Temperature", exact=True).fill("0.7")
        self.page.get_by_label("Max. steps", exact=True).fill("5")
        self.page.get_by_label("Prompt", exact=True).fill("Neuer globaler Prompt.")
        self.page.get_by_role("button", name="Save", exact=True).click()

        path = self.global_agents / "tester.md"
        self.wait_until(
            lambda: "Global neu" in path.read_text(encoding="utf-8"),
            message="Gespeicherter Agent enthält die neue Beschreibung nicht",
        )
        saved = path.read_text(encoding="utf-8")
        self.assertIn("color: blau", saved)
        self.assertIn("tools:\n  write: true", saved)
        self.assertIn("mode: primary", saved)
        self.assertIn("Neuer globaler Prompt.", saved)

    def test_invalid_raw_frontmatter_is_rejected_without_writing(self):
        """AK Schutz: ungültiger Rohtext verändert die Agentendatei nicht."""
        self.open_agents()
        self.open_global_editor()
        path = self.global_agents / "tester.md"
        before = path.read_text(encoding="utf-8")

        self.raw_editor().fill("kein Frontmatter\n")
        self.page.get_by_role("button", name="Save", exact=True).click()
        self.wait_until(
            lambda: self.page.get_by_text("Frontmatter", exact=False).count() > 0,
            message="Fehlermeldung zum ungültigen Frontmatter fehlt",
        )
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_invalid_structured_value_is_rejected_without_writing(self):
        """AK Schutz: ungültige strukturierte Werte verändern die Datei nicht."""
        self.open_agents()
        self.open_global_editor()
        path = self.global_agents / "tester.md"
        before = path.read_text(encoding="utf-8")

        self.page.get_by_label("Temperature", exact=True).fill("heiß")
        self.page.get_by_role("button", name="Save", exact=True).click()
        self.wait_until(
            lambda: self.page.get_by_text("Temperatur muss", exact=False).count() > 0,
            message="Fehlermeldung zur ungültigen Temperatur fehlt",
        )
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_a_new_agent_can_be_created_and_deleted_with_backup(self):
        """AK Erstellen/Löschen: neuer Agent wird angelegt, Löschen sichert."""
        self.open_agents()
        target = self.global_agents / "neuling.md"

        self.page.get_by_role("button", name="New agent").click()
        self.page.get_by_label("Name", exact=True).fill("neuling")
        self.page.get_by_label("Description", exact=True).fill("Frischer Agent")
        self.page.get_by_label("Prompt", exact=True).fill("Arbeite sorgfältig.")
        self.page.get_by_role("button", name="Save", exact=True).click()
        self.wait_until(target.exists, message="Neuer Agent wurde nicht geschrieben")
        text = target.read_text(encoding="utf-8")
        self.assertIn("description: Frischer Agent", text)
        self.assertIn("Arbeite sorgfältig.", text)

        self.open_agents()
        row = self.page.locator('tr[data-agent="neuling"]')
        row.get_by_role("button", name="Edit").click()
        self.page.get_by_role("button", name="Delete").click()
        self.page.get_by_role("button", name="Yes, delete").click()
        self.wait_until(lambda: not target.exists(), message="Agent wurde nicht gelöscht")
        backups = self.backup_files()
        self.assertTrue(backups, "Beim Löschen wurde keine Sicherung angelegt")
        self.assertTrue(
            any("Frischer Agent" in item.read_text(encoding="utf-8") for item in backups)
        )

    def test_restore_brings_back_the_previous_version(self):
        """AK Schutz: eine Sicherung stellt den vorherigen Stand wieder her."""
        self.open_agents()
        self.open_global_editor()
        path = self.global_agents / "tester.md"
        before = path.read_text(encoding="utf-8")

        self.page.get_by_label("Description", exact=True).fill("Zwischenstand")
        self.page.get_by_role("button", name="Save", exact=True).click()
        self.wait_until(
            lambda: "Zwischenstand" in path.read_text(encoding="utf-8"),
            message="Zwischenstand wurde nicht gespeichert",
        )

        self.page.get_by_role("button", name="Show backups").click()
        restore = self.page.get_by_role("button", name="Restore").first
        restore.wait_for()
        restore.click()
        self.page.get_by_role("button", name="Yes, restore").click()
        self.wait_until(
            lambda: path.read_text(encoding="utf-8") == before,
            message="Sicherung wurde nicht wiederhergestellt",
        )


if __name__ == "__main__":
    unittest.main()
