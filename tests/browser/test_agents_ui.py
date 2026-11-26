"""Agenten-Oberfläche: Liste, Assistent, Editor, Zuweisung und Projektbereich.

Aufruf: python3 -m unittest tests.browser.test_agents_ui -v
"""


import json
import os
import re
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


# ===========================================================================
# Browserabnahme für die in neu aufgebaute Agentenverwaltung
# ===========================================================================

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

SHOTS = Path(os.environ.get("VIBE_VERIFY_SCREENSHOT_DIR", REPO / "docs" / "features"))
SHOT_GENERAL = SHOTS / "AP03-agenten.png"
SHOT_PROJECT = SHOTS / "AP03-projekt-agenten.png"

FAKE_OPENCODE_ap03 = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf 'opencode 2.1.4\\n'
    exit 0
    ;;
  models)
    printf 'opencode/vibe-modell\\nopencode/tester-modell\\nopencode/helper-modell\\nopencode/start\\nopencode/neu\\nopencode/anderes\\n'
    exit 0
    ;;
esac
exit 2
"""


TESTER_AGENT = """---
description: Testet die Anwendung gründlich
mode: subagent
model: opencode/tester-modell
temperature: 0.1
permission:
  read: allow
  edit: deny
  task: allow
---

Teste die Anwendung.
"""

HELPER_AGENT = """---
description: Hilft beim Testen
mode: subagent
model: opencode/helper-modell
permission:
  read: allow
  edit: deny
  task:
    "*": deny
---

Hilf beim Testen.
"""

LOCAL_AGENT = """---
description: Projektlokaler Agent
mode: subagent
model: opencode/lokal-modell
---

Nur im Projekt sichtbar.
"""


def isolated_env_ap03(root, home, port, fake_bin):
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


class Ap03AgentsBrowserTest(unittest.TestCase):
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
        fake.write_text(FAKE_OPENCODE_ap03, encoding="utf-8")
        fake.chmod(0o755)

        cls._write_fixture()

        cls.port = free_port()
        env = isolated_env_ap03(cls.root, cls.home, cls.port, fake_bin)
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
        (cls.global_agents / "vibe-agent.md").write_text(
            VIBE_AGENT, encoding="utf-8"
        )
        (cls.global_agents / "tester.md").write_text(TESTER_AGENT, encoding="utf-8")
        (cls.global_agents / "helper.md").write_text(HELPER_AGENT, encoding="utf-8")
        project_agents = cls.project / ".opencode" / "agents"
        project_agents.mkdir(parents=True, exist_ok=True)
        (project_agents / "lokal.md").write_text(LOCAL_AGENT, encoding="utf-8")
        (cls.state / "profiles.json").write_text(
            json.dumps({"rollen": {"vibe-agent": "vibe"}}), encoding="utf-8"
        )
        (cls.state / "agent-meta.json").write_text(
            json.dumps({"agents": {"tester": {"result": "Bericht vorhanden"}}}),
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
        try:
            os.killpg(cls.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        cls.tmp.cleanup()

    def setUp(self):
        self._write_fixture()
        agents_json = self.project / ".vibe" / "agents.json"
        if agents_json.exists():
            agents_json.unlink()
        self.page = self.browser.new_page(viewport={"width": 1500, "height": 1100})

    def tearDown(self):
        self.page.close()

    # ------------------------------------------------------------------ Helfer
    def wait_until(self, predicate, timeout=10, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def open_agents(self):
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.page.locator("button[data-t='agents']").click()
        self.page.locator("#agents").wait_for()
        self.page.locator('tr[data-agent="tester"]').wait_for()

    def open_editor(self, name="tester"):
        self.page.locator(f'tr[data-agent="{name}"]').get_by_role(
            "button", name="Edit"
        ).click()
        self.page.get_by_label("Description", exact=True).wait_for()

    def open_project_settings(self):
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.page.reload(wait_until="load")
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        self.page.locator("[role='tab'][aria-controls='panel-einstellungen']").click()
        self.page.locator("#project-agents").wait_for()
        self.page.locator('tr[data-project-agent="vibe-agent"]').wait_for()

    def profiles(self):
        path = self.state / "profiles.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def roles(self):
        return self.profiles().get("rollen", {})

    def result(self, name):
        path = self.state / "agent-meta.json"
        if not path.exists():
            return ""
        data = json.loads(path.read_text(encoding="utf-8"))
        return (data.get("agents") or {}).get(name, {}).get("result", "")

    def agents_config(self):
        path = self.project / ".vibe" / "agents.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def row_is_visible(self, locator):
        return locator.count() > 0 and locator.first.is_visible()

    def reveal_unconfigured(self):
        if not self.row_is_visible(
            self.page.locator('tr[data-project-agent="tester"]')
        ):
            self.page.locator('input[data-toggle="unconfigured"]').check()
            self.page.locator('tr[data-project-agent="tester"]').wait_for()

    # ---------------------------------------------------------------- Testfälle
    def test_01_general_list_has_vibe_status_and_global_agent_fields(self):
        """AK UI allgemein: Vibe-Status und vollständige globale Agentenzeile."""
        self.open_agents()

        status = self.page.locator("#vibe-status")
        status.wait_for()
        status_text = status.inner_text()
        self.assertIn("Vibe agent", status_text)
        self.assertIn("vibe-agent", status_text)
        self.assertIn("opencode/vibe-modell", status_text)

        row = self.page.locator('tr[data-agent="tester"]')
        self.assertEqual(row.count(), 1)
        self.assertIn(
            "Testet die Anwendung gründlich",
            self.page.locator('td[data-aufgabe="tester"]').inner_text(),
        )
        self.assertIn(
            "Bericht vorhanden",
            self.page.locator('td[data-ergebnis="tester"]').inner_text(),
        )
        self.assertIn(
            "all", self.page.locator('td[data-erlaubt="tester"]').inner_text()
        )
        self.assertIn(
            "opencode/tester-modell",
            self.page.locator('td[data-modell="tester"]').inner_text(),
        )

        # Projektlokale Agentendateien gehören nicht in die allgemeine Liste.
        self.assertEqual(self.page.locator('tr[data-agent="lokal"]').count(), 0)

        # Der Editor ist über „Neuer Agent“ erreichbar und bietet die
        # AP03-Felder an.
        self.page.get_by_role("button", name="New agent").click()
        self.page.get_by_label("Description", exact=True).wait_for()
        self.page.get_by_label("Role", exact=True).wait_for()
        self.page.get_by_label("Result", exact=True).wait_for()
        self.page.get_by_label("Subagent permissions", exact=True).wait_for()

    def test_02_role_change_updates_profiles_json_and_is_shown(self):
        """AK Rollen: select[data-role] schreibt profiles.json und bleibt sichtbar."""
        self.open_agents()

        select = self.page.locator('select[data-role="tester"]')
        select.wait_for()
        values = select.locator("option").evaluate_all(
            "nodes => nodes.map(node => node.value)"
        )
        self.assertEqual(
            sorted(values),
            sorted(
                [
                    "",
                    "coder",
                    "reviewer",
                    "vibe",
                    "tester",
                    "analyst",
                    "sonstiges",
                    "content-creator",
                ]
            ),
        )

        select.select_option("coder")
        self.wait_until(
            lambda: self.roles().get("tester") == "coder",
            message="Der Rollenwechsel wurde nicht in profiles.json gespeichert",
        )

        self.open_agents()
        self.assertEqual(
            self.page.locator('select[data-role="tester"]').input_value(), "coder"
        )

    def test_03_editor_saves_result_role_and_subagent_rights(self):
        """AK Editor: Ergebnis, Rolle und Subagenten-Rechte werden wirksam."""
        self.open_agents()
        self.open_editor()

        self.page.get_by_label("Result", exact=True).fill("Fertiger Prüfbericht")
        self.page.get_by_label("Role", exact=True).select_option(label="reviewer")
        self.page.get_by_label("Subagent permissions", exact=True).select_option(
            label="selected"
        )

        checkbox = self.page.locator('input[data-subagent="helper"]')
        checkbox.wait_for()
        self.assertEqual(checkbox.get_attribute("aria-label"), "Subagent helper")
        checkbox.check()
        self.page.get_by_role("button", name="Save", exact=True).click()

        self.wait_until(
            lambda: self.roles().get("tester") == "reviewer",
            message="Die Rolle wurde nicht in profiles.json gespeichert",
        )
        self.wait_until(
            lambda: self.result("tester") == "Fertiger Prüfbericht",
            message="Das Ergebnis wurde nicht in agent-meta.json gespeichert",
        )
        agent_file = self.global_agents / "tester.md"
        saved = agent_file.read_text(encoding="utf-8")
        self.assertIn("task:", saved)
        self.assertIn('"*": deny', saved)
        self.assertIn("helper: allow", saved)
        self.assertIn("description: Testet die Anwendung gründlich", saved)

        # Der Editor bleibt nach dem Speichern offen und zeigt den neuen Stand.
        self.assertTrue(self.page.get_by_label("Result", exact=True).is_visible())
        self.wait_until(
            lambda: self.page.get_by_label("Result", exact=True).input_value()
            == "Fertiger Prüfbericht",
            message="Der Editor zeigt das gespeicherte Ergebnis nicht",
        )
        self.assertEqual(
            self.page.get_by_label("Role", exact=True).input_value(), "reviewer"
        )
        self.assertEqual(
            self.page.get_by_label("Subagent permissions", exact=True).input_value(),
            "ausgewählt",
        )
        self.assertTrue(
            self.page.locator('input[data-subagent="helper"]').is_checked()
        )

        # Ein erneutes Speichern ist ohne erneutes Öffnen möglich.
        self.page.get_by_label("Result", exact=True).fill("Zweiter Stand")
        self.page.get_by_role("button", name="Save", exact=True).click()
        self.wait_until(
            lambda: self.result("tester") == "Zweiter Stand",
            message="Ein zweites Speichern im offenen Editor war nicht möglich",
        )

    def test_04_prompt_scaffold_contains_the_required_sections(self):
        """AK Prompt-Unterstützung: Aufgabe, Ergebnis und Grenzen als Gerüst."""
        self.open_agents()
        self.open_editor()

        self.page.get_by_label("Description", exact=True).fill("Prüft die Anwendung")
        self.page.get_by_label("Result", exact=True).fill("Prüfbericht")
        self.page.get_by_role("button", name="Prompt scaffold").click()

        prompt = self.page.get_by_label("Prompt", exact=True)
        self.wait_until(
            lambda: "## Aufgabe" in prompt.input_value(),
            message="Das Prompt-Gerüst wurde nicht in das Prompt-Feld übernommen",
        )
        value = prompt.input_value()
        for expected in (
            "## Aufgabe",
            "## Ergebnis",
            "## Grenzen",
            "Prüft die Anwendung",
            "Prüfbericht",
        ):
            self.assertIn(expected, value)

    def test_05_project_settings_default_vibe_toggle_and_model_override(self):
        """AK Projekte: nur Vibe standardmäßig, globale Agenten einblendbar."""
        self.open_project_settings()

        vibe_row = self.page.locator('tr[data-project-agent="vibe-agent"]')
        self.assertEqual(vibe_row.get_attribute("data-configured"), "ja")
        vibe_checkbox = self.page.locator('input[data-configure="vibe-agent"]')
        self.assertTrue(vibe_checkbox.is_checked())
        self.assertTrue(vibe_checkbox.is_disabled())

        tester_row = self.page.locator('tr[data-project-agent="tester"]')
        self.assertFalse(
            self.row_is_visible(tester_row),
            "Ein nicht konfigurierter Agent ist standardmäßig sichtbar",
        )

        toggle = self.page.locator('input[data-toggle="unconfigured"]')
        self.assertEqual(
            toggle.get_attribute("aria-label"),
            "Show unconfigured agents",
        )
        toggle.check()
        self.wait_until(
            lambda: self.row_is_visible(
                self.page.locator('tr[data-project-agent="tester"]')
            ),
            message="Die Checkbox blendet den nicht konfigurierten Agenten nicht ein",
        )

        # Projektlokale Agentendateien werden auch nach dem Einblenden nicht
        # angeboten.
        self.assertEqual(self.page.locator('tr[data-project-agent="lokal"]').count(), 0)

        row = self.page.locator('tr[data-project-agent="tester"]')
        self.assertEqual(row.get_attribute("data-configured"), "nein")
        self.assertIn(
            "Testet die Anwendung", row.locator("td[data-aufgabe]").inner_text()
        )
        self.assertIn(
            "Bericht vorhanden", row.locator("td[data-ergebnis]").inner_text()
        )
        self.assertIn("all", row.locator("td[data-erlaubt]").inner_text())
        self.assertIn(
            "opencode/tester-modell", row.locator("td[data-wirksam]").inner_text()
        )

        model = self.page.locator('select[data-model-override="tester"]')
        self.assertEqual(model.get_attribute("aria-label"), "Model for tester")

        # Eine Modellüberschreibung wirkt unabhängig von der Auswahl und
        # verändert ausschließlich die Projekteinstellungen.
        agent_before = (self.global_agents / "tester.md").read_text(encoding="utf-8")
        model.select_option("opencode/neu")
        self.wait_until(
            lambda: self.agents_config().get("modelle", {}).get("tester")
            == "opencode/neu",
            message="Die Modellüberschreibung wurde nicht gespeichert",
        )
        config = self.agents_config()
        self.assertEqual(config.get("version"), 3)
        self.assertEqual(config.get("modelle", {}).get("tester"), "opencode/neu")
        self.assertNotIn("tester", config.get("aktiv", []))
        self.assertIn("vibe-agent", config.get("aktiv", []))
        self.assertEqual(
            (self.global_agents / "tester.md").read_text(encoding="utf-8"),
            agent_before,
        )

        # Konfigurieren schreibt die aktive Liste in derselben Version 3.
        self.reveal_unconfigured()
        configure = self.page.locator('input[data-configure="tester"]')
        self.assertEqual(
            configure.get_attribute("aria-label"), "Agent tester configure"
        )
        configure.check()
        self.wait_until(
            lambda: "tester" in self.agents_config().get("aktiv", []),
            message="Der konfigurierte Agent wurde nicht in 'aktiv' gespeichert",
        )
        config = self.agents_config()
        self.assertEqual(config.get("version"), 3)
        self.assertIn("vibe-agent", config.get("aktiv", []))
        self.assertEqual(config.get("modelle", {}).get("tester"), "opencode/neu")

        # Der Vibe-Agent bleibt auch nach den Änderungen geschützt.
        self.assertTrue(
            self.page.locator('input[data-configure="vibe-agent"]').is_checked()
        )
        self.assertTrue(
            self.page.locator('input[data-configure="vibe-agent"]').is_disabled()
        )

    def test_06_screenshots_are_real_png_files(self):
        """AK Nachweis: echte Aufnahmen der allgemeinen und Projektansicht."""
        SHOTS.mkdir(parents=True, exist_ok=True)

        self.open_agents()
        self.page.locator("#vibe-status").wait_for()
        self.page.screenshot(path=str(SHOT_GENERAL))

        self.open_project_settings()
        self.page.locator('input[data-toggle="unconfigured"]').check()
        self.page.locator('tr[data-project-agent="tester"]').wait_for()
        self.page.screenshot(path=str(SHOT_PROJECT))

        for shot in (SHOT_GENERAL, SHOT_PROJECT):
            self.assertTrue(shot.exists(), "Screenshot fehlt: " + str(shot))
            self.assertGreater(shot.stat().st_size, 1000, "Screenshot ist leer")
            self.assertEqual(shot.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")


# ===========================================================================
# Browserabnahme der neuen Agentenrollen
# ===========================================================================

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


NEW_ROLES = ("tester", "analyst", "sonstiges", "content-creator")
EXISTING_ROLES = ("coder", "reviewer", "vibe")

FAKE_OPENCODE_ap17 = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf 'opencode 2.1.4\\n'
    exit 0
    ;;
  models)
    printf 'opencode/vibe-modell\\nopencode/tester-modell\\nopencode/helper-modell\\n'
    exit 0
    ;;
esac
exit 2
"""


TESTER_AGENT_ap17 = """---
description: Testet die Anwendung gründlich
mode: subagent
model: opencode/tester-modell
permission:
  read: allow
  edit: deny
---

Teste die Anwendung.
"""

HELPER_AGENT_ap17 = """---
description: Hilft beim Testen
mode: subagent
model: opencode/helper-modell
permission:
  read: allow
  edit: deny
---

Hilf beim Testen.
"""

ISOLATED_ENV_ap17 = (
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
    "AGENT",
)


def isolated_env_ap17(root, home, port, fake_bin):
    env = os.environ.copy()
    for key in ISOLATED_ENV_ap17:
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


class Ap17AgentRolesBrowserTest(unittest.TestCase):
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
        fake.write_text(FAKE_OPENCODE_ap17, encoding="utf-8")
        fake.chmod(0o755)

        cls._write_fixture()

        cls.port = free_port()
        env = isolated_env_ap17(cls.root, cls.home, cls.port, fake_bin)
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
                    with socket.create_connection(
                        ("127.0.0.1", cls.port), timeout=0.5
                    ):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: " + output
                )
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def _write_fixture(cls):
        (cls.global_agents / "vibe-agent.md").write_text(
            VIBE_AGENT, encoding="utf-8"
        )
        (cls.global_agents / "tester.md").write_text(
            TESTER_AGENT_ap17, encoding="utf-8"
        )
        (cls.global_agents / "helper.md").write_text(
            HELPER_AGENT_ap17, encoding="utf-8"
        )
        (cls.state / "profiles.json").write_text(
            json.dumps({"rollen": {"vibe-agent": "vibe"}}), encoding="utf-8"
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
        try:
            os.killpg(cls.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        cls.tmp.cleanup()

    def setUp(self):
        self._write_fixture()
        agents_json = self.project / ".vibe" / "agents.json"
        if agents_json.exists():
            agents_json.unlink()
        self.page = self.browser.new_page(
            viewport={"width": 1500, "height": 1100}
        )

    def tearDown(self):
        self.page.close()

    # ------------------------------------------------------------------ Helfer
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

    def roles(self):
        path = self.state / "profiles.json"
        return json.loads(path.read_text(encoding="utf-8")).get("rollen", {})

    # ---------------------------------------------------------------- Testfälle
    def test_01_role_select_offers_the_new_roles(self):
        """Name: Rollenauswahl bietet alle vier neuen Rollen an.

        Vorbedingung: Dashboard läuft; die Agentenliste zeigt den globalen
        Agenten ``tester``.
        Aktion: Das Auswahlfeld ``select[data-role="tester"]`` wird geöffnet
        und seine Optionen werden gelesen.
        Erwartetes Ergebnis: Die Werte enthalten tester, analyst, sonstiges
        und content-creator sowie weiterhin coder, reviewer und vibe.
        """
        self.open_agents()

        select = self.page.locator('select[data-role="tester"]')
        select.wait_for()
        values = select.locator("option").evaluate_all(
            "nodes => nodes.map(node => node.value)"
        )

        for role in NEW_ROLES:
            self.assertIn(role, values)
        for role in EXISTING_ROLES:
            self.assertIn(role, values)

    def test_02_tester_role_is_saved_and_shown_after_reload(self):
        """Name: Auswahl tester wird gespeichert und nach Neuladen angezeigt.

        Vorbedingung: Dashboard läuft; ``tester`` hat noch keine Rolle.
        Aktion: Im Rollenauswahlfeld wird ``tester`` gewählt; anschließend
        wird die Agentenliste neu geöffnet.
        Erwartetes Ergebnis: ``profiles.json`` enthält unter ``rollen`` den
        Eintrag ``tester: tester``; das Auswahlfeld zeigt nach dem Neuladen
        weiterhin ``tester``.
        """
        self.open_agents()

        select = self.page.locator('select[data-role="tester"]')
        select.wait_for()
        select.select_option("tester", timeout=5000)

        self.wait_until(
            lambda: self.roles().get("tester") == "tester",
            message="Die Rolle tester wurde nicht in profiles.json gespeichert",
        )

        self.open_agents()
        self.assertEqual(
            self.page.locator('select[data-role="tester"]').input_value(),
            "tester",
        )


# ===========================================================================
# Browserabnahme, Meilenstein C: Agenten (Liste, Wizard, Ein-Seiten-Editor)
# ===========================================================================

import http.client
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

_BROWSERS = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402


FAKE_OPENCODE_ap22 = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf 'opencode v2.1.4\\n'
    exit 0
    ;;
  models)
    printf 'opencode/vibe-modell\\nopencode/test-modell\\nopencode/schnell-modell\\n'
    exit 0
    ;;
esac
exit 2
"""

GLOBAL_AGENT_ap22 = """---
description: Globaler Agent
mode: subagent
model: opencode/vibe-modell
temperature: 0.1
steps: 5
permission:
  read: allow
  edit: deny
  task: allow
---

Globaler Prompt.
"""


BROKEN_AGENT = """---
description: Defekter Agent
mode: quatsch
---

Defekter Prompt.
"""

# Review-Fix AP22: derselbe Name in beiden Geltungsbereichen mit
# unterschiedlicher Beschreibung. Der Editor darf niemals den globalen Agenten
# laden oder überschreiben, wenn der projektbezogene gemeint ist.
SHARED_GLOBAL_AGENT = """---
description: Globaler geteilter Agent
mode: subagent
model: opencode/vibe-modell
---

Globaler geteilter Prompt.
"""

SHARED_PROJECT_AGENT = """---
description: Projektgebundener Agent
mode: subagent
model: opencode/test-modell
---

Projektgebundener Prompt.
"""

CATALOG = {
    "schema": 2,
    "version": "2026-11-20.1",
    "stand": "2026-11-20",
    "waehrung": "USD",
    "einheit": "1 Mio. Tokens",
    "hinweis": "Testkatalog für die AP22-Agentenabnahme.",
    "quellen": [],
    "modelle": [
        {
            "id": "opencode/vibe-modell",
            "name": "Vibe Modell",
            "anbieter": "OpenCode Zen",
            "id_status": "bestaetigt",
            "id_beleg": {"quelle": "opencode models", "datum": "2026-11-20"},
        }
    ],
}


class Ap22AgentsBrowserTest(unittest.TestCase):
    """Dashboard, Browser, opencode-Attrappe, isoliertes VIBE-Root."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        cls.home = cls.root / "home"
        cls.agents_dir = cls.home / ".config" / "opencode" / "agents"
        cls.agents_dir.mkdir(parents=True)
        cls.state = cls.root / "_state"
        cls.state.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        (cls.state / "models.json").write_text(
            json.dumps(CATALOG, ensure_ascii=False), encoding="utf-8")
        fake_bin = cls.root / "fakebin"
        fake_bin.mkdir()
        fake = fake_bin / "opencode"
        fake.write_text(FAKE_OPENCODE_ap22, encoding="utf-8")
        fake.chmod(0o755)
        (cls.root / "tmp").mkdir()
        (cls.root / "tmux").mkdir()

        cls.port = free_port()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                    "TMUX", "TMUX_PANE"):
                env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_STATE": str(cls.state),
            "VIBE_RUNTIME": str(cls.log_dir),
            "HOME": str(cls.home),
            "TMPDIR": str(cls.root / "tmp"),
            "TMUX_TMPDIR": str(cls.root / "tmux"),
            "VIBE_CONFIG_FILE": str(
                cls.home / ".config" / "vibe" / "config.json"),
            "PATH": str(fake_bin) + os.pathsep + env.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        cls.env = env
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=cls.server_log, stderr=subprocess.STDOUT, text=True,
            start_new_session=True)
        cls.pgid = os.getpgid(cls.proc.pid)
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 30
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                            ("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: "
                    + (cls.root / "web-server.log").read_text(
                        encoding="utf-8", errors="replace"))
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser.close()
            cls.playwright.stop()
        finally:
            if cls.proc.poll() is None:
                cls.proc.terminate()
                try:
                    cls.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls.proc.kill()
                    cls.proc.wait()
            try:
                os.killpg(cls.pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            cls.server_log.close()
            cls.tmp.cleanup()

    # ---------- Umgebung je Test ----------

    def setUp(self):
        self._reset_fixture()
        self.page_errors = []
        self.dialogs = []
        self.context = self.browser.new_context(
            viewport={"width": 1500, "height": 1100})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))
        self.page.on("dialog", self._on_dialog)

    def _on_dialog(self, dialog):
        # Bestätigungen (Löschen/Wiederherstellen) werden angenommen; ein
        # eigener Bestätigungsdialog ist im Vertrag nicht benannt.
        self.dialogs.append(dialog.type + ": " + dialog.message)
        dialog.accept()

    def tearDown(self):
        self.page.close()
        self.context.close()

    # ---------- Fixture und Helfer ----------

    def _reset_fixture(self):
        """Schreibt die Agenten-Fixture neu und räumt Sicherungen auf."""
        for item in self.agents_dir.glob("*.md"):
            item.unlink()
        (self.agents_dir / "tester.md").write_text(
            GLOBAL_AGENT_ap22, encoding="utf-8")
        (self.agents_dir / "vibe-agent.md").write_text(
            VIBE_AGENT, encoding="utf-8")
        (self.agents_dir / "defekt.md").write_text(
            BROKEN_AGENT, encoding="utf-8")
        (self.agents_dir / "shared.md").write_text(
            SHARED_GLOBAL_AGENT, encoding="utf-8")
        (self.state / "profiles.json").write_text(
            json.dumps({"rollen": {"vibe-agent": "vibe", "tester": "coder"}},
                       ensure_ascii=False), encoding="utf-8")
        backups = self.state / "agent-backups"
        if backups.exists():
            for item in sorted(backups.rglob("*"), reverse=True):
                if item.is_file():
                    item.unlink()
        agents_json = self.project / ".vibe" / "agents.json"
        if agents_json.exists():
            agents_json.unlink()
        project_agents = self.project / ".opencode" / "agents"
        if project_agents.exists():
            for item in project_agents.glob("*.md"):
                item.unlink()
        project_agents.mkdir(parents=True, exist_ok=True)
        # Review-Fix AP22: gleicher Name wie der globale Agent, aber eigener
        # Geltungsbereich und eigene Beschreibung.
        (project_agents / "shared.md").write_text(
            SHARED_PROJECT_AGENT, encoding="utf-8")

    def wait_until(self, predicate, timeout=20,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_agents(self):
        self.boot()
        self.page.goto(self.base + "/#/agents")
        self.page.locator("main#nv-main[data-nv-view='agents']").wait_for(
            state="visible", timeout=25000)

    def open_editor(self, name="tester"):
        self.boot()
        self.page.goto(self.base + f"/#/agents/{name}")
        self.page.locator("[data-nv-agent-editor]").wait_for(
            state="visible", timeout=25000)

    def open_scoped_editor(self, scope, name):
        """Öffnet den Editor eines Geltungsbereichs (Review-Fix AP22)."""
        self.boot()
        self.page.goto(self.base + f"/#/agents/{scope}/{name}")
        self.page.locator("[data-nv-agent-editor]").wait_for(
            state="visible", timeout=20000)

    def project_agent_file(self, name):
        return self.project / ".opencode" / "agents" / f"{name}.md"

    def open_wizard(self):
        """Öffnet die Agentenliste und stellt den Wizard sicher."""
        self.open_agents()
        wizard = self.page.locator("[data-nv-wizard]")
        if not (wizard.count() and wizard.first.is_visible()):
            self.page.locator("[data-nv-action='agent-new']").click()
        wizard.first.wait_for(state="visible", timeout=20000)
        return wizard.first

    def wizard_next(self):
        self.page.locator("[data-nv-wizard-next]").click()

    def goto_step(self, step):
        self.page.locator(
            f"[data-nv-wizard] section[data-nv-step='{step}']").wait_for(
                state="visible", timeout=15000)

    def card(self, name):
        return self.page.locator(f"article[data-nv-agent='{name}']")

    def visible_error(self, root):
        """True, wenn ein sichtbarer Formularfehler im Bereich steht."""
        errors = root.locator("[data-nv-form-error]")
        for index in range(errors.count()):
            if errors.nth(index).is_visible():
                return True
        return False

    def error_text(self, root):
        errors = root.locator("[data-nv-form-error]")
        for index in range(errors.count()):
            if errors.nth(index).is_visible():
                return (errors.nth(index).inner_text() or "").strip()
        return ""

    def api_json(self, path):
        return self.page.evaluate(
            """async (path) => {
              const response = await fetch(path);
              return await response.json();
            }""", path)

    def backup_files(self):
        folder = self.state / "agent-backups" / "global"
        if not folder.exists():
            return []
        return sorted(folder.glob("tester-*.md"))

    def click_confirm_if_shown(self, root):
        """Klickt einen sichtbaren „Ja/Bestätigen“-Knopf, falls vorhanden."""
        buttons = root.locator("button")
        for index in range(buttons.count()):
            button = buttons.nth(index)
            if not button.is_visible():
                continue
            text = (button.inner_text() or "").strip()
            if re.match(r"(?i)^(ja|yes|bestätig|bestaetig|confirm|ok)\b", text):
                button.click()
                return True
        return False

    def assert_clean_page(self):
        self.assertEqual(
            [], self.page_errors, "Die Oberfläche erzeugte JavaScript-Fehler")

    def post_language(self, lang):
        body = json.dumps({"language": lang}).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", "/api/language", body=body, headers={
                "Host": f"127.0.0.1:{self.port}", "X-Token": self.token,
                "Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, response.read().decode("utf-8", "replace")
        finally:
            conn.close()


class ListTest(Ap22AgentsBrowserTest):
    def test_list_shows_agents_with_role_model_and_description(self):
        """Vorbedingung: globale Agenten ``tester`` (Rolle coder) und
        ``vibe-agent`` (Rolle vibe) liegen als Dateien vor.

        Aktion: ``#/agents`` öffnen. Erwartung: ``div[data-nv-agent-list]``
        mit je einer Karte ``article[data-nv-agent=…]``; ``tester`` zeigt
        Rolle ``[data-nv-role]`` = coder, Modell und Beschreibung; der
        ``is_vibe``-Agent ist als solcher erkennbar; der Neuanlage-Knopf
        ``[data-nv-action="agent-new"]`` existiert.
        """
        self.open_agents()
        self.assertEqual(
            1, self.page.locator("[data-nv-agent-list]").count(),
            "Die Agentenliste div[data-nv-agent-list] fehlt")
        tester = self.card("tester")
        tester.wait_for(state="visible", timeout=20000)

        role = tester.locator("[data-nv-role]")
        self.assertEqual(1, role.count(),
                         "Die Rollen-Markierung [data-nv-role] fehlt")
        self.assertEqual("coder", (role.inner_text() or "").strip().lower(),
                         "Die Rolle des Agenten tester wird nicht angezeigt")
        text = tester.inner_text()
        self.assertIn("opencode/vibe-modell", text,
                      "Das Modell des Agenten tester fehlt in der Karte")
        self.assertIn("Globaler Agent", text,
                      "Die Beschreibung des Agenten tester fehlt in der Karte")

        vibe = self.card("vibe-agent")
        self.assertEqual(1, vibe.count(), "Der Vibe-Agent fehlt in der Liste")
        self.assertRegex(
            vibe.inner_text(), r"(?i)vibe",
            "Der Vibe-Status ist an der Karte nicht erkennbar")

        self.assertEqual(
            1, self.page.locator("[data-nv-action='agent-new']").count(),
            "Der Neuanlage-Knopf [data-nv-action='agent-new'] fehlt")
        self.assert_clean_page()

    def test_list_marks_an_invalid_agent_file(self):
        """Vorbedingung: ``defekt.md`` hat einen ungültigen Modus
        (``mode: quatsch``) und ist damit fachlich ungültig.

        Aktion: Liste öffnen. Erwartung: Die Karte ``defekt`` existiert und
        trägt eine ungültig-Markierung (Text „ungültig“/„invalid“, da der
        Vertrag keinen eigenen Hook nennt).
        """
        self.open_agents()
        card = self.card("defekt")
        card.wait_for(state="visible", timeout=20000)
        self.assertRegex(
            card.inner_text(), r"(?i)ungültig|ungueltig|invalid|defekt",
            "Die defekte Agentendatei ist nicht als ungültig markiert: "
            + card.inner_text())

    @staticmethod
    def _vertical_center(box):
        """Mittelpunkt einer bounding_box auf der y-Achse."""
        return box["y"] + box["height"] / 2.0

    def test_header_search_and_new_agent_share_a_vertical_center(self):
        """Vorbedingung: Agentenliste ``#/agents`` mit Suchleiste und
        „Neuer Agent“-Knopf in der Kopfzeile.

        Aktion: Die Positionen von Titel, Sucheingabe und Neuanlage-Knopf
        messen. Erwartung: Alle drei Elemente liegen auf einer gemeinsamen
        optischen Mittelachse (vertikal zentriert), und die horizontalen
        Abstände zwischen Titel→Suche und Suche→Knopf sind gleich groß
        (konsistentes, ausgewogenes Padding). Die TN tolerieren 4 px.
        """
        self.open_agents()
        search = self.page.locator("input[data-nv-agent-search]")
        search.wait_for(state="visible", timeout=20000)
        title = self.page.locator(".nv-toolbar h2.nv-page-title")
        new_btn = self.page.locator("[data-nv-action='agent-new']")
        search_box = self.page.locator("[data-nv-search]")
        boxes = {
            "title": title.bounding_box(),
            "search": search.bounding_box(),
            "new": new_btn.bounding_box(),
            "searchWrap": search_box.bounding_box(),
        }
        for name, box in boxes.items():
            self.assertIsNotNone(box, f"{name} hat keine messbare Position")
        center_title = self._vertical_center(boxes["title"])
        center_search = self._vertical_center(boxes["search"])
        center_new = self._vertical_center(boxes["new"])
        self.assertLessEqual(
            abs(center_search - center_new), 4,
            "Suchleiste und 'Neuer Agent' sind nicht vertikal ausgerichtet: "
            f"Suche-Mitte {center_search}, Knopf-Mitte {center_new}")
        self.assertLessEqual(
            abs(center_title - center_new), 4,
            "Titel und 'Neuer Agent' sind nicht vertikal ausgerichtet: "
            f"Titel-Mitte {center_title}, Knopf-Mitte {center_new}")
        gap_title_search = (boxes["searchWrap"]["x"]
                            - (boxes["title"]["x"] + boxes["title"]["width"]))
        gap_search_new = (boxes["new"]["x"]
                          - (boxes["searchWrap"]["x"]
                             + boxes["searchWrap"]["width"]))
        self.assertLessEqual(
            abs(gap_title_search - gap_search_new), 4,
            "Die Abstände in der Kopfzeile sind ungleichmäßig: "
            f"Titel→Suche {gap_title_search}, Suche→Knopf {gap_search_new}")
        self.assert_clean_page()

    def test_agent_card_action_buttons_are_bottom_aligned_across_cards(self):
        """Vorbedingung: Agentenliste mit mindestens zwei Karten
        unterschiedlicher Inhaltshöhe (u. a. ``vibe-agent`` mit extra Chip).

        Aktion: Die Positionen von Bearbeiten/Löschen auf jeder Karte
        messen. Erwartung: Auf jeder Karte liegen beide Knöpfe auf derselben
        Zeile, und über alle Karten hinweg auf identischer vertikaler
        Position und mit identischem Abstand zum Kartenunterrand — unabhängig
        von der Höhe des Karteninhalts. Toleranz 3 px.
        """
        self.open_agents()
        cards = self.page.locator("[data-nv-agent-list] article[data-nv-agent]")
        cards.first.wait_for(state="visible", timeout=20000)
        # Die Karten-Einblendanimation verschiebt die Messwerte um einige px;
        # für die Geometriemessung wird sie abgeschaltet (CSS-Hook aus nova.css).
        self.page.evaluate(
            "() => document.documentElement.setAttribute('data-animations','off')")
        self.page.wait_for_timeout(150)
        self.assertGreaterEqual(
            cards.count(), 2,
            "Es gibt weniger als zwei Karten — die Ausrichtung ist nicht prüfbar")
        button_y = []
        bottom_gaps = []
        for index in range(cards.count()):
            card = cards.nth(index)
            card_box = card.bounding_box()
            edit_box = card.locator(
                "[data-nv-action='agent-edit']").bounding_box()
            delete_box = card.locator(
                "[data-nv-action='agent-delete']").bounding_box()
            self.assertIsNotNone(edit_box, "Bearbeiten-Knopf ohne Position")
            self.assertIsNotNone(delete_box, "Löschen-Knopf ohne Position")
            self.assertIsNotNone(card_box, "Karte ohne Position")
            self.assertLessEqual(
                abs(edit_box["y"] - delete_box["y"]), 3,
                f"Bearbeiten und Löschen stehen auf Karte {index} nicht auf "
                "einer Zeile")
            button_y.append(edit_box["y"])
            bottom_gaps.append((card_box["y"] + card_box["height"])
                               - (edit_box["y"] + edit_box["height"]))
        self.assertLessEqual(
            max(button_y) - min(button_y), 3,
            "Die Aktionsknöpfe liegen nicht auf derselben Höhe über allen "
            f"Karten: {button_y}")
        self.assertLessEqual(
            max(bottom_gaps) - min(bottom_gaps), 3,
            "Der Abstand der Knöpfe zum Kartenunterrand ist nicht "
            f"einheitlich: {bottom_gaps}")
        self.assertLessEqual(
            max(bottom_gaps), 30,
            "Die Aktionsknöpfe sind nicht am unteren Kartenrand ausgerichtet: "
            f"{bottom_gaps}")
        self.assert_clean_page()


class WizardCreateTest(Ap22AgentsBrowserTest):
    def test_wizard_has_four_steps_and_the_role_catalog(self):
        """Vorbedingung: angemeldet. Aktion: Agentenansicht öffnen und
        (falls nötig) „Neuer Agent“ klicken.

        Erwartung: ``[data-nv-wizard]`` mit den vier Schritten; Schritt 1
        trägt Name ``[data-nv-field="name"]`` und Rollen-Select
        ``[data-nv-field="role"]``; der Katalog enthält die dokumentierten
        Rollen coder, reviewer, tester, analyst, content-creator, sonstiges.
        """
        wizard = self.open_wizard()
        for step in (1, 2, 3, 4):
            self.assertEqual(
                1, wizard.locator(f"section[data-nv-step='{step}']").count(),
                f"Wizard-Schritt {step} fehlt")
        self.goto_step(1)
        self.assertEqual(1, wizard.locator(
            "[data-nv-field='name']").count(),
            "Das Namensfeld des Wizards fehlt")
        role = wizard.locator("select[data-nv-field='role']")
        self.assertEqual(1, role.count(),
                         "Der Rollen-Select des Wizards fehlt")
        options = role.locator("option").evaluate_all(
            "nodes => nodes.map(node => node.value)")
        for expected in ("coder", "reviewer", "tester", "analyst",
                         "content-creator", "sonstiges"):
            self.assertIn(expected, options,
                          f"Die Rolle {expected!r} fehlt im Rollen-Select: "
                          + repr(options))

    def test_wizard_model_select_lists_connected_models(self):
        """Vorbedingung: die opencode-Attrappe meldet drei Modelle.

        Aktion: Wizard öffnen, Schritt 1 ausfüllen, weiter zu Schritt 2.
        Erwartung: die Modell-Combobox ``div[data-nv-combobox][data-nv-field="model"]``
        ist sichtbar und bietet nach dem Öffnen die gemeldeten Modelle
        (u. a. ``opencode/vibe-modell``) als Optionen an.
        """
        wizard = self.open_wizard()
        self.goto_step(1)
        wizard.locator("[data-nv-field='name']").fill("modellprobe")
        self.wizard_next()
        self.goto_step(2)
        # F33 WP2: das Modell ist eine Combobox (kein select); die Optionsliste
        # wird erst durch einen Klick auf das Eingabefeld geöffnet.
        model = wizard.locator(
            "div[data-nv-combobox][data-nv-field='model']")
        model.wait_for(state="visible", timeout=15000)
        model.locator("input[data-nv-combobox-input]").click()
        options = model.locator("li[data-nv-combobox-option]").all_inner_texts()
        self.assertIn("opencode/vibe-modell", options,
                      "Die Modell-Combobox bietet die verbundenen Modelle "
                      "nicht an: " + repr(options))

    def test_prompt_template_fills_the_prompt_field(self):
        """Vorbedingung: Wizard mit Name und Beschreibung.

        Aktion: bis Schritt 4 navigieren, Vorlagenknopf
        ``[data-nv-action="prompt-template"]`` klicken. Erwartung: Das
        Prompt-Feld ``textarea[data-nv-field="prompt"]`` ist vorher leer und
        wird durch die Vorlage (POST ``/api/agent_template``) gefüllt; ein
        Hilfetext ist sichtbar; kein Formularfehler.
        """
        wizard = self.open_wizard()
        self.goto_step(1)
        wizard.locator("[data-nv-field='name']").fill("vorlagenprobe")
        wizard.locator("[data-nv-field='description']").fill(
            "Prüft die Vorlage")
        self.wizard_next()
        self.goto_step(2)
        # F33 WP2: Schritt 3 ist neu (Rechte); der Prompt steht in Schritt 4.
        self.wizard_next()
        self.goto_step(3)
        self.wizard_next()
        self.goto_step(4)
        prompt = wizard.locator("textarea[data-nv-field='prompt']")
        prompt.wait_for(state="visible", timeout=15000)
        self.assertEqual("", prompt.input_value(),
                         "Das Prompt-Feld ist vor der Vorlage nicht leer")
        helper = wizard.locator("[data-nv-step='4'] .nv-muted")
        self.assertTrue(
            helper.count() and helper.first.is_visible(),
            "Der Hilfetext zum Prompt fehlt in Schritt 4")
        wizard.locator("[data-nv-action='prompt-template']").click()
        self.wait_until(
            lambda: len(prompt.input_value().strip()) > 0,
            timeout=15000,
            message="Der Vorlagenknopf füllte das Prompt-Feld nicht")
        self.assertFalse(self.visible_error(wizard),
                         "Die Vorlage erzeugte einen Formularfehler")

    def test_create_adds_the_agent_file_and_the_list_card(self):
        """Vorbedingung: Wizard, kein Agent ``neuling``.

        Aktion: alle Schritte ausfüllen, Schritt 5 prüfen, „Anlegen“.
        Erwartung: ``~/.config/opencode/agents/neuling.md`` existiert mit
        Beschreibung und Prompt; die Liste zeigt eine Karte ``neuling``.
        """
        wizard = self.open_wizard()
        self.goto_step(1)
        wizard.locator("[data-nv-field='name']").fill("neuling")
        wizard.locator("[data-nv-field='description']").fill(
            "Frischer Agent")
        wizard.locator("[data-nv-field='role']").select_option("coder")
        self.wizard_next()
        self.goto_step(2)
        # F33 WP2: Modell als Combobox in Schritt 2; Auswahl über Eingabefeld
        # und Optionsliste statt select_option.
        model = wizard.locator(
            "div[data-nv-combobox][data-nv-field='model']")
        model.locator("input[data-nv-combobox-input]").click()
        model.locator("li[data-nv-combobox-option]",
                      has_text="opencode/test-modell").first.click()
        self.assertEqual(
            "opencode/test-modell", model.get_attribute("data-nv-value"),
            "Die Modellauswahl wurde nicht übernommen")
        self.wizard_next()
        self.goto_step(3)
        # F33 WP2: Schritt 3 ist neu (Rechte); der vorgegebene Standard genügt.
        self.wizard_next()
        self.goto_step(4)
        wizard.locator("textarea[data-nv-field='prompt']").fill(
            "Arbeite sorgfältig.")
        self.wizard_next()
        self.goto_step(5)
        # F33 WP2: Prüfen & Anlegen ist Schritt 5 (statt 4).
        self.assertIn("neuling",
                      wizard.locator("[data-nv-step='5']").inner_text(),
                      "Die Prüfseite nennt den Agentennamen nicht")

        wizard.locator("[data-nv-action='agent-create']").click()
        target = self.agents_dir / "neuling.md"
        self.wait_until(target.exists, timeout=20000,
                        message="Der neue Agent wurde nicht geschrieben")
        text = target.read_text(encoding="utf-8")
        self.assertIn("description: Frischer Agent", text)
        self.assertIn("Arbeite sorgfältig.", text)

        # Das Ziel nach dem Anlegen ist im Vertrag nicht genannt: Die Karte
        # wird in der Liste geprüft; bleibt der Wizard stehen, wird die Liste
        # über die dokumentierte Route geöffnet.
        card = self.card("neuling")
        if not (card.count() and card.first.is_visible()):
            self.page.goto(self.base + "/#/agents")
        card.first.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            "coder",
            (card.first.locator("[data-nv-role]").inner_text() or "")
            .strip().lower(),
            "Die neue Karte zeigt die gewählte Rolle nicht")

    def test_missing_name_shows_a_form_error_and_writes_nothing(self):
        """Vorbedingung: Wizard, kein Name eingegeben.

        Aktion: Weiter/Anlegen ohne Namen versuchen. Erwartung: In der
        Wizard-Karte erscheint ein sichtbarer Formularfehler
        ``[data-nv-form-error]`` (Vertrag: jede Formular-Karte zeigt
        Validierungsfehler dort); es entsteht keine neue Agentendatei.
        """
        before = {item.name for item in self.agents_dir.glob("*.md")}
        wizard = self.open_wizard()
        self.goto_step(1)
        for _ in range(3):
            if self.visible_error(wizard):
                break
            self.wizard_next()
            self.page.wait_for_timeout(300)
        if not self.visible_error(wizard):
            create = wizard.locator("[data-nv-action='agent-create']")
            if create.count() and create.first.is_visible():
                create.first.click()
        self.wait_until(
            lambda: self.visible_error(wizard),
            timeout=15000,
            message="Ohne Namen erscheint kein Formularfehler")
        after = {item.name for item in self.agents_dir.glob("*.md")}
        self.assertEqual(before, after,
                         "Trotz fehlendem Namen wurde eine Agentendatei "
                         "geschrieben")


class StructuredEditorTest(Ap22AgentsBrowserTest):
    def test_editor_shows_all_structured_fields_on_one_page(self):
        """Vorbedingung: Agent ``tester`` liegt vor.

        Aktion: ``#/agents/tester`` öffnen. Erwartung:
        ``[data-nv-agent-editor]`` enthält Beschreibung, Modus, Modell,
        Temperatur, Schritte, Rechte und Prompt — alle auf einer Seite; der
        Prompt ist ein Textfeld (textarea). Die Hooks sind im Moduldocstring
        dokumentiert.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        expected = {
            "description": "input",
            "mode": "select",
            "model": "select",
            "temperature": "input",
            "steps": "input",
            "permissions": "select",
            "prompt": "textarea",
        }
        for field, tag in expected.items():
            locator = editor.locator(f"{tag}[data-nv-field='{field}']")
            self.assertEqual(
                1, locator.count(),
                f"Das Feld {field!r} fehlt als {tag} im Ein-Seiten-Editor")
            self.assertTrue(locator.is_visible(),
                            f"Das Feld {field!r} ist nicht sichtbar")
        self.assertEqual(
            "0.1", editor.locator(
                "input[data-nv-field='temperature']").input_value(),
            "Der Editor zeigt die gespeicherte Temperatur nicht")
        self.assertIn(
            "Globaler Prompt.",
            editor.locator("textarea[data-nv-field='prompt']").input_value(),
            "Der Editor zeigt den Prompt nicht")

    def test_save_persists_the_description_across_reload(self):
        """Vorbedingung: Editor ``tester``.

        Aktion: Beschreibung ändern, ``agent-save`` klicken, Seite neu laden.
        Erwartung: Die Datei enthält die neue Beschreibung; nach dem Reload
        zeigt das Feld den neuen Wert.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        field = editor.locator("input[data-nv-field='description']")
        field.fill("Geänderte Beschreibung")
        editor.locator("[data-nv-action='agent-save']").click()
        target = self.agents_dir / "tester.md"
        self.wait_until(
            lambda: "Geänderte Beschreibung" in target.read_text(
                encoding="utf-8"),
            timeout=20000,
            message="Die geänderte Beschreibung wurde nicht gespeichert")
        self.assertFalse(self.visible_error(editor),
                         "Das Speichern meldete einen Formularfehler")

        self.page.reload()
        self.page.locator("[data-nv-agent-editor]").wait_for(
            state="visible", timeout=25000)
        self.assertEqual(
            "Geänderte Beschreibung",
            self.page.locator(
                "[data-nv-agent-editor] input[data-nv-field='description']"
            ).input_value(),
            "Nach dem Reload zeigt der Editor nicht die gespeicherte "
            "Beschreibung")

    def test_raw_mode_shows_frontmatter_and_saves_raw_text(self):
        """Vorbedingung: Editor ``tester``.

        Aktion: ``[data-nv-raw]`` aktivieren, Rohtext ansehen und ergänzen,
        speichern. Erwartung: ``textarea[data-nv-raw-text]`` zeigt den
        vollständigen Text mit ``---``-Frontmatter; die Rohtext-Änderung
        landet in der Datei, ohne Formularfehler.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        editor.locator("[data-nv-raw]").click()
        raw = editor.locator("textarea[data-nv-raw-text]")
        raw.wait_for(state="visible", timeout=15000)
        text = raw.input_value()
        self.assertTrue(text.startswith("---"),
                        "Der Rohmodus zeigt kein Frontmatter: " + text[:60])
        self.assertIn("description: Globaler Agent", text)

        raw.fill(text.rstrip() + "\nZusatz aus dem Rohtext.\n")
        editor.locator("[data-nv-action='agent-save']").click()
        target = self.agents_dir / "tester.md"
        self.wait_until(
            lambda: "Zusatz aus dem Rohtext." in target.read_text(
                encoding="utf-8"),
            timeout=20000,
            message="Der geänderte Rohtext wurde nicht gespeichert")
        self.assertFalse(self.visible_error(editor),
                         "Der unveränderte Digest erzeugte einen Konflikt")

    def test_raw_mode_conflict_shows_a_form_error_without_writing(self):
        """Vorbedingung: Editor ``tester`` im Rohmodus, Datei wurde danach
        außerhalb der Oberfläche verändert (abweichender Digest).

        Aktion: Rohtext bearbeiten und speichern. Erwartung: Der Server
        lehnt den veralteten Stand ab (Bestand: Digest-Konflikt); die
        Oberfläche zeigt ``[data-nv-form-error]``; die externe Änderung
        bleibt erhalten (nichts wird überschrieben).
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        editor.locator("[data-nv-raw]").click()
        raw = editor.locator("textarea[data-nv-raw-text]")
        raw.wait_for(state="visible", timeout=15000)

        external = (GLOBAL_AGENT_ap22
                    .replace("Globaler Agent", "Extern geändert")
                    .replace("Globaler Prompt.", "Externer Prompt."))
        (self.agents_dir / "tester.md").write_text(external, encoding="utf-8")

        raw.fill(raw.input_value().rstrip() + "\nÄnderung aus der Oberfläche.\n")
        editor.locator("[data-nv-action='agent-save']").click()
        self.wait_until(
            lambda: self.visible_error(editor),
            timeout=20000,
            message="Der Digest-Konflikt wird nicht als Formularfehler "
                    "angezeigt")
        self.assertIn(
            "Externer Prompt.",
            (self.agents_dir / "tester.md").read_text(encoding="utf-8"),
            "Der Konflikt überschrieb trotzdem die externe Änderung")

    def test_backup_action_creates_a_backup_entry(self):
        """Vorbedingung: Agent ``tester`` ohne Sicherungen.

        Aktion: ``[data-nv-action="agent-backup"]`` klicken. Erwartung: Im
        Sicherungsordner ``<state>/agent-backups/global`` entsteht eine
        Sicherung des Agenten (Bestandsablage der API).
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        before = len(self.backup_files())
        editor.locator("[data-nv-action='agent-backup']").click()
        self.wait_until(
            lambda: len(self.backup_files()) > before,
            timeout=20000,
            message="Die Sicherung wurde nicht angelegt")
        newest = self.backup_files()[-1].read_text(encoding="utf-8")
        self.assertIn("Globaler Agent", newest,
                      "Die Sicherung enthält nicht den Agentenstand")

    def test_restore_brings_back_the_previous_version(self):
        """Vorbedingung: Agent ``tester``.

        Aktion: Beschreibung ändern und speichern (legt eine Sicherung an),
        erneut ändern und speichern, dann
        ``[data-nv-action="agent-restore"]`` ausführen (Bestätigung wird
        angenommen). Erwartung: Die Datei enthält wieder den vorherigen
        Stand; nach dem Reload zeigt der Editor ihn an.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        field = editor.locator("input[data-nv-field='description']")
        target = self.agents_dir / "tester.md"

        field.fill("Erste Fassung")
        editor.locator("[data-nv-action='agent-save']").click()
        self.wait_until(lambda: "Erste Fassung" in target.read_text(
            encoding="utf-8"), timeout=20000,
            message="Die erste Fassung wurde nicht gespeichert")

        field.fill("Zweite Fassung")
        editor.locator("[data-nv-action='agent-save']").click()
        self.wait_until(lambda: "Zweite Fassung" in target.read_text(
            encoding="utf-8"), timeout=20000,
            message="Die zweite Fassung wurde nicht gespeichert")

        editor.locator("[data-nv-action='agent-restore']").click()
        self.page.wait_for_timeout(300)
        self.click_confirm_if_shown(self.page.locator("[data-nv-agent-editor]"))
        self.wait_until(
            lambda: "Erste Fassung" in target.read_text(encoding="utf-8"),
            timeout=20000,
            message="Die Sicherung wurde nicht wiederhergestellt")

        self.page.reload()
        self.page.locator("[data-nv-agent-editor]").wait_for(
            state="visible", timeout=25000)
        self.assertEqual(
            "Erste Fassung",
            self.page.locator(
                "[data-nv-agent-editor] input[data-nv-field='description']"
            ).input_value(),
            "Der Editor zeigt nach der Wiederherstellung nicht den "
            "Sicherungsstand")

    @staticmethod
    def _backup_option_index(values, backup_name):
        """Findet die Option, die zu einer konkreten Sicherungsdatei gehört.

        Der Vertrag übergibt die Sicherungsnamen aus ``GET /api/agent`` als
        Optionswerte; als Fallback werden auch Datesnamen ohne ``.md`` und
        Teiltreffer akzeptiert.
        """
        stem = backup_name[:-3] if backup_name.endswith(".md") else backup_name
        for index, value in enumerate(values):
            if value == backup_name or value == stem:
                return index
        for index, value in enumerate(values):
            if stem in value or backup_name in value:
                return index
        return None

    def test_restore_selects_an_older_backup_and_restores_that_version(self):
        """Vorbedingung: Agent ``tester``. Zwei Speichervorgänge erzeugen zwei
        Sicherungen: die älteste enthält den Ursprung („Globaler Agent“), die
        neueste den Zwischenstand („Zwischenstand“); aktuell ist „Aktuell“.

        Aktion: ``agent-restore`` öffnen, in der Versionsauswahl bewusst die
        ÄLTESTE Sicherung wählen und bestätigen. Erwartung: Die Bestätigung
        bietet eine Auswahl mit mindestens zwei Versionen; genau die gewählte
        (ältere) Version wird wiederhergestellt — nicht die neueste. Der
        Ursprung steht wieder in der Datei, der Zwischenstand ist verschwunden.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        field = editor.locator("input[data-nv-field='description']")
        target = self.agents_dir / "tester.md"

        field.fill("Zwischenstand")
        editor.locator("[data-nv-action='agent-save']").click()
        self.wait_until(
            lambda: "Zwischenstand" in target.read_text(encoding="utf-8"),
            timeout=20000,
            message="Der Zwischenstand wurde nicht gespeichert")

        field.fill("Aktuell")
        editor.locator("[data-nv-action='agent-save']").click()
        self.wait_until(
            lambda: "Aktuell" in target.read_text(encoding="utf-8"),
            timeout=20000,
            message="Der aktuelle Stand wurde nicht gespeichert")

        backups = self.backup_files()
        self.assertGreaterEqual(
            len(backups), 2, "Es wurden nicht mindestens zwei Sicherungen angelegt")
        oldest = backups[0]
        self.assertIn("Globaler Agent", oldest.read_text(encoding="utf-8"))

        # Der Editor lädt die Sicherungsliste beim Öffnen. Nach den zwei
        # Speichervorgängen neu öffnen, damit die Auswahl beide Versionen
        # anbietet (wie beim Rückkehr eines Nutzers in den Dialog).
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        editor.locator("[data-nv-action='agent-restore']").click()
        confirm = editor.locator("[data-nv-confirm]:visible")
        confirm.wait_for(state="visible", timeout=15000)
        chooser = confirm.locator("select")
        self.assertEqual(
            1, chooser.count(),
            "Die Restore-Bestätigung bietet keine Versionsauswahl (select) an")
        values = chooser.locator("option").evaluate_all(
            "nodes => nodes.map(node => node.value)")
        self.assertGreaterEqual(
            len(values), 2,
            "Die Versionsauswahl bietet weniger als zwei Versionen an: "
            + repr(values))
        index = self._backup_option_index(values, oldest.name)
        self.assertIsNotNone(
            index,
            "Die älteste Sicherung ist in der Versionsauswahl nicht "
            f"auswählbar: {oldest.name} nicht in {values}")
        chooser.select_option(index=index)
        self.assertTrue(
            self.click_confirm_if_shown(confirm),
            "Die Restore-Bestätigung hat keinen Ja-Knopf")
        self.wait_until(
            lambda: ("Globaler Agent" in target.read_text(encoding="utf-8")
                     and "Zwischenstand" not in target.read_text(encoding="utf-8")),
            timeout=20000,
            message="Die ausgewählte ältere Sicherung wurde nicht "
                    "wiederhergestellt (stattdessen wurde die neueste "
                    "verwendet)")

    def test_copy_creates_a_copy_that_appears_in_the_list(self):
        """Vorbedingung: Agent ``tester`` (global).

        Aktion: Im Editor ``[data-nv-action="agent-copy"]`` ausführen
        (etwaige Bestätigung/Zielauswahl wird bedient). Erwartung: Über
        ``GET /api/agents`` erscheint ein weiterer Eintrag; die Liste zeigt
        für ``tester`` mindestens zwei Karten (global + Kopie im Projekt).

        Der Vertrag nennt weder Zielbereich noch Namen der Kopie; die API
        kopiert in einen anderen Geltungsbereich unter demselben Namen. Der
        Test akzeptiert daher dieselbe Karte (zweiter Geltungsbereich) wie
        auch einen abgeleiteten Namen ``tester-…``.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        before = len(self.api_json("/api/agents").get("agents") or [])

        editor.locator("[data-nv-action='agent-copy']").click()
        self.page.wait_for_timeout(300)
        dialogs = self.page.locator("[data-nv-agent-editor] select")
        for index in range(dialogs.count()):
            select = dialogs.nth(index)
            options = select.locator("option").evaluate_all(
                "nodes => nodes.map(node => node.value)")
            if "proj" in options:
                select.select_option("proj")
        self.click_confirm_if_shown(editor)

        self.wait_until(
            lambda: len(self.api_json("/api/agents").get("agents") or [])
            > before,
            timeout=20000,
            message="Das Kopieren legte keinen weiteren Agenten an")

        self.page.goto(self.base + "/#/agents")
        self.page.locator("[data-nv-agent-list]").wait_for(
            state="visible", timeout=20000)
        names = self.page.locator(
            "[data-nv-agent-list] article[data-nv-agent]").evaluate_all(
                "nodes => nodes.map(node => node.getAttribute('data-nv-agent'))")
        copies = [name for name in names if name == "tester"
                  or name.startswith("tester-")]
        self.assertGreaterEqual(
            len(copies), 2,
            "Die Kopie erscheint nicht als eigene Karte in der Liste: "
            + repr(names))

    def test_delete_removes_the_agent_file(self):
        """Vorbedingung: Agent ``tester``.

        Aktion: ``[data-nv-action="agent-delete"]`` klicken; eine etwaige
        native Bestätigung wird angenommen. Erwartung: Die Agentendatei ist
        entfernt (die API legt vorher eine Sicherung an), die Karte
        verschwindet aus der Liste.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        target = self.agents_dir / "tester.md"
        editor.locator("[data-nv-action='agent-delete']").click()
        self.page.wait_for_timeout(300)
        self.click_confirm_if_shown(editor)
        self.wait_until(lambda: not target.exists(), timeout=20000,
                        message="Der Agent wurde nicht gelöscht")
        self.assertTrue(self.backup_files(),
                        "Beim Löschen wurde keine Sicherung angelegt")

        self.page.goto(self.base + "/#/agents")
        self.page.locator("[data-nv-agent-list]").wait_for(
            state="visible", timeout=20000)
        self.assertEqual(0, self.card("tester").count(),
                         "Die gelöschte Karte steht weiterhin in der Liste")


class AssignmentTest(Ap22AgentsBrowserTest):
    def test_project_toggle_and_model_override_are_saved(self):
        """Vorbedingung: Projekt ``proj`` (generic), Agent ``tester`` noch
        nicht zugeordnet.

        Aktion: Im Editor den Schalter ``[data-nv-assign="proj"]`` aktivieren,
        im Modell-Override ``div[data-nv-assign-model="proj"]`` ein Modell
        wählen und speichern. Erwartung: ``GET /api/project-agents?name=proj``
        führt ``tester`` als gewählt (``selected``) und mit
        ``override=opencode/test-modell``; nach dem Reload sind Schalter und
        Override weiterhin gesetzt. Die Zuordnungen liegen vertragsgemäß im
        standardmäßig geschlossenen ``details[data-nv-assignments]`` und
        werden beim Aufklappen nachgeladen.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        # F33 WP2: Zuordnungen erst beim Aufklappen laden (Vertrag).
        details = editor.locator("details[data-nv-assignments]")
        details.locator("summary").click()
        toggle = editor.locator("[data-nv-assign='proj']")
        toggle.wait_for(state="visible", timeout=15000)
        if not toggle.is_checked():
            toggle.check()
        # F33 WP2: der Override ist eine Combobox (kein select).
        override = editor.locator(
            "div[data-nv-combobox][data-nv-assign-model='proj']")
        override.wait_for(state="visible", timeout=15000)
        override.locator("input[data-nv-combobox-input]").click()
        override.locator("li[data-nv-combobox-option]",
                         has_text="opencode/test-modell").first.click()
        self.assertEqual(
            "opencode/test-modell", override.get_attribute("data-nv-value"),
            "Die Modellüberschreibung wurde nicht übernommen")
        editor.locator("[data-nv-action='agent-save']").click()

        def assigned():
            data = self.api_json("/api/project-agents?name=proj")
            rows = {row.get("name"): row for row in data.get("agents") or []}
            row = rows.get("tester") or {}
            return row.get("selected") is True and row.get(
                "override") == "opencode/test-modell"

        self.wait_until(assigned, timeout=20000,
                        message="Die Projektzuordnung wurde nicht gespeichert")

        self.page.reload()
        self.page.locator("[data-nv-agent-editor]").wait_for(
            state="visible", timeout=25000)
        editor = self.page.locator("[data-nv-agent-editor]")
        # F33 WP2: nach dem Reload ist das details wieder geschlossen.
        editor.locator("details[data-nv-assignments] summary").click()
        toggle = editor.locator("[data-nv-assign='proj']")
        toggle.wait_for(state="visible", timeout=15000)
        self.assertTrue(
            toggle.is_checked(),
            "Nach dem Reload ist der Projekt-Schalter nicht mehr gesetzt")
        override = editor.locator(
            "div[data-nv-combobox][data-nv-assign-model='proj']")
        override.wait_for(state="visible", timeout=15000)
        self.assertEqual(
            "opencode/test-modell", override.get_attribute("data-nv-value"),
            "Nach dem Reload fehlt die Modellüberschreibung")

    def test_assignment_checkbox_has_an_explicit_assign_label(self):
        """Vorbedingung: Editor ``tester``, Projektzuordnungen aufgeklappt.

        Aktion: Die barrierefreie Beschriftung des Projekt-Schalters prüfen.
        Erwartung: Die Checkbox besitzt einen zugänglichen Namen, der klar
        macht, wofür sie steht — „Assign“ bzw. „Zugewiesen“ (oder eine
        gleichbedeutende, explizite Beschriftung). Ein bloßer Intername wie
        „Agent in Projekt: tester · proj“ genügt nicht.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        details = editor.locator("details[data-nv-assignments]")
        details.locator("summary").click()
        toggle = editor.locator("[data-nv-assign='proj']")
        toggle.wait_for(state="visible", timeout=15000)

        labeled = editor.get_by_role(
            "checkbox", name=re.compile(r"assign|zugewiesen", re.IGNORECASE))
        self.assertGreaterEqual(
            labeled.count(), 1,
            "Keine Projekt-Checkbox hat eine ausdrückliche "
            "'Assign'/'Zugewiesen'-Beschriftung; zugängliche Namen: "
            + repr([editor.locator("[data-nv-assign]").nth(i).get_attribute(
                "aria-label")
                for i in range(editor.locator("[data-nv-assign]").count())]))
        matches_proj = any(
            labeled.nth(index).get_attribute("data-nv-assign") == "proj"
            for index in range(labeled.count()))
        self.assertTrue(
            matches_proj,
            "Der Projekt-Schalter von 'proj' trägt keine explizite "
            "'Assign'/'Zugewiesen'-Beschriftung")


class AssignmentLayoutTest(Ap22AgentsBrowserTest):
    """Zwei Projekte, um „eine Zeile pro Projekt“ wirklich zu prüfen."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.zweitprojekt = cls.root / "zweitprojekt"
        (cls.zweitprojekt / ".vibe").mkdir(parents=True)
        (cls.zweitprojekt / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8")
        (cls.zweitprojekt / ".opencode" / "agents").mkdir(
            parents=True, exist_ok=True)

    def test_each_project_renders_exactly_one_assignment_row_with_visible_name(self):
        """Vorbedingung: zwei Projekte ``proj`` und ``zweitprojekt``; Editor
        ``tester`` mit aufgeklappten Projektzuordnungen.

        Aktion: Die Zuordnungszeilen im DOM untersuchen. Erwartung: Genau eine
        Zeile pro Projekt; diese Zeile enthält genau eine Checkbox und die
        zugehörige Modell-Auswahl; der Projektname ist in der Zeile sichtbar.
        Checkbox und Modell dürfen nicht als getrennte Geschwister in einer
        gemeinsamen Liste landen.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        details = editor.locator("details[data-nv-assignments]")
        details.locator("summary").click()
        list_node = editor.locator("[data-nv-assignments-list]")
        self.wait_until(
            lambda: editor.locator("[data-nv-assign]").count() >= 2,
            timeout=15,
            message="Es wurden nicht die Schalter beider Projekte geladen")
        info = list_node.evaluate("""(node) => {
          return Array.from(node.querySelectorAll('[data-nv-assign]')).map(cb => {
            const project = cb.getAttribute('data-nv-assign');
            const model = node.querySelector(
              '[data-nv-assign-model="' + project + '"]');
            const row = cb.closest('[data-nv-assign-row]') || cb.parentElement;
            return {
              project: project,
              rowText: row ? row.textContent.trim() : '',
              checkboxesInRow: row
                ? row.querySelectorAll('[data-nv-assign]').length : -1,
              modelInRow: !!(row && model && row.contains(model))
            };
          });
        }""")
        self.assertEqual(
            2, len(info),
            "Es wird nicht genau eine Zeile pro Projekt erzeugt: " + repr(info))
        self.assertEqual(
            {"proj", "zweitprojekt"}, {row["project"] for row in info},
            "Die Zeilen decken nicht beide Projekte ab: " + repr(info))
        for row in info:
            self.assertEqual(
                1, row["checkboxesInRow"],
                f"Projekt {row['project']!r} hat nicht genau eine eigene Zeile: "
                + repr(info))
            self.assertTrue(
                row["modelInRow"],
                f"Die Modell-Auswahl von {row['project']!r} steht nicht in "
                "derselben Zeile wie die Checkbox: " + repr(info))
            self.assertIn(
                row["project"], row["rowText"],
                f"Der Projektname {row['project']!r} ist nicht sichtbar: "
                + repr(info))
        self.assert_clean_page()


class ProjectScopeTest(Ap22AgentsBrowserTest):
    """Review-Fix AP22: Projekt-Agenten sind nicht die globalen Agenten.

    ``shared`` liegt bewusst zweimal vor — global und projektbezogen in
    ``proj`` — und trägt unterschiedliche Beschreibungen. Die Oberfläche muss
    beide Karten unterscheidbar machen, beim Bearbeiten den richtigen
    Geltungsbereich adressieren und beim Speichern/Löschen ausschließlich die
    gemeinte Datei verändern.
    """

    def test_list_shows_scope_badges_for_same_named_agents(self):
        """Vorbedingung: ``shared`` existiert global und in Projekt ``proj``
        mit unterschiedlicher Beschreibung.

        Aktion: ``#/agents`` öffnen. Erwartung: Je eine Karte
        ``article[data-nv-agent="shared"]`` mit
        ``data-nv-agent-scope="global"`` bzw. ``"proj"``; jede Karte trägt
        genau eine Geltungsbereichs-Markierung
        ``[data-nv-agent-scope-badge]`` (global vs. Projekt) und die eigene
        Beschreibung.
        """
        self.open_agents()
        global_card = self.page.locator(
            "article[data-nv-agent='shared'][data-nv-agent-scope='global']")
        project_card = self.page.locator(
            "article[data-nv-agent='shared'][data-nv-agent-scope='proj']")

        def both_scoped():
            return (global_card.count() == 1 and project_card.count() == 1
                    and global_card.first.is_visible()
                    and project_card.first.is_visible())

        self.wait_until(
            both_scoped, timeout=20,
            message="Gleichnamige globale und projektbezogene Agenten sind "
                    "in der Liste nicht über ihren Geltungsbereich "
                    "unterscheidbar")

        global_badge = global_card.locator("[data-nv-agent-scope-badge]")
        project_badge = project_card.locator("[data-nv-agent-scope-badge]")
        self.assertEqual(
            1, global_badge.count(),
            "Der globalen Karte fehlt die Geltungsbereichs-Markierung")
        self.assertEqual(
            1, project_badge.count(),
            "Der projektbezogenen Karte fehlt die "
            "Geltungsbereichs-Markierung")
        self.assertRegex(
            (global_badge.inner_text() or "").strip(), r"(?i)global",
            "Die globale Karte ist nicht als global markiert")
        self.assertRegex(
            (project_badge.inner_text() or "").strip(),
            r"(?i)proj|projekt",
            "Die projektbezogene Karte ist nicht als Projekt-Agent markiert")

        self.assertIn(
            "Globaler geteilter Agent", global_card.inner_text(),
            "Die globale Karte zeigt nicht die globale Beschreibung")
        self.assertIn(
            "Projektgebundener Agent", project_card.inner_text(),
            "Die projektbezogene Karte zeigt nicht die "
            "projektbezogene Beschreibung")

    def test_project_card_edit_opens_project_scoped_editor(self):
        """Vorbedingung: ``shared`` global und in ``proj``.

        Aktion: Auf der projektbezogenen Karte
        ``[data-nv-action="agent-edit"]`` klicken. Erwartung: Die Route ist
        ``#/agents/proj/shared``, der Editor trägt
        ``data-nv-agent-scope="proj"`` und zeigt die projektbezogene
        Beschreibung sowie das projektbezogene Modell — nicht den globalen
        Agenten.
        """
        self.open_agents()
        project_card = self.page.locator(
            "article[data-nv-agent='shared'][data-nv-agent-scope='proj']")
        self.wait_until(
            lambda: project_card.count() == 1,
            timeout=20,
            message="Die projektbezogene Karte des Agenten shared fehlt")
        project_card.locator("[data-nv-action='agent-edit']").click()

        self.wait_until(
            lambda: self.page.url.endswith("#/agents/proj/shared"),
            timeout=20,
            message="Der Projekt-Agent wird nicht über den "
                    "projektbezogenen Pfad geöffnet: " + self.page.url)
        editor = self.page.locator("[data-nv-agent-editor]")
        editor.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            "proj", editor.get_attribute("data-nv-agent-scope"),
            "Der Editor weist den projektbezogenen Geltungsbereich nicht aus")
        self.assertEqual(
            "Projektgebundener Agent",
            editor.locator(
                "input[data-nv-field='description']").input_value(),
            "Der Editor zeigt die Beschreibung des globalen Agenten statt "
            "der projektbezogenen")
        self.assertEqual(
            "opencode/test-modell",
            editor.locator("select[data-nv-field='model']").input_value(),
            "Der Editor zeigt das Modell des globalen Agenten statt des "
            "projektbezogenen")
        self.assertIn(
            "Projektgebundener Prompt.",
            editor.locator("textarea[data-nv-field='prompt']").input_value(),
            "Der Editor zeigt den globalen Prompt statt des "
            "projektbezogenen")

    def test_save_project_agent_keeps_global_file_unchanged(self):
        """Vorbedingung: ``shared`` global und in ``proj``.

        Aktion: Projekt-Editor ``#/agents/proj/shared`` öffnen, Beschreibung
        auf ``Projekt geändert`` setzen und speichern. Erwartung: Nur
        ``proj/.opencode/agents/shared.md`` ändert sich; die globale Datei
        ``~/.config/opencode/agents/shared.md`` bleibt byte-gleich.
        """
        self.open_scoped_editor("proj", "shared")
        editor = self.page.locator("[data-nv-agent-editor]")
        editor.locator("input[data-nv-field='description']").fill(
            "Projekt geändert")
        editor.locator("[data-nv-action='agent-save']").click()

        project_file = self.project_agent_file("shared")
        global_file = self.agents_dir / "shared.md"
        self.wait_until(
            lambda: "Projekt geändert" in project_file.read_text(
                encoding="utf-8"),
            timeout=20,
            message="Die Änderung wurde nicht in die projektbezogene "
                    "Agentendatei geschrieben")
        self.assertEqual(
            SHARED_GLOBAL_AGENT, global_file.read_text(encoding="utf-8"),
            "Das Speichern des Projekt-Agenten überschrieb die globale "
            "Agentendatei")
        project_text = project_file.read_text(encoding="utf-8")
        self.assertIn(
            "Projektgebundener Prompt.", project_text,
            "Die projektbezogene Agentendatei wurde nicht gezielt geändert")
        self.assertNotIn(
            "Globaler geteilter Prompt.", project_text,
            "Die projektbezogene Datei enthält den globalen Prompt")

    def test_card_delete_removes_project_agent_but_keeps_global(self):
        """Vorbedingung: ``shared`` global und in ``proj``.

        Aktion: Auf der projektbezogenen Karte
        ``article[data-nv-agent="shared"][data-nv-agent-scope="proj"]``
        ``[data-nv-action="agent-delete"]`` ausführen (Dialog oder inline
        angebotene Bestätigung wird angenommen). Erwartung: Der Löschknopf
        liegt auf der Karte (Review-Befund 7); nur die projektbezogene Datei
        ist entfernt, die globale bleibt bestehen; die Liste zeigt danach nur
        noch die globale Karte ``data-nv-agent-scope="global"``.
        """
        self.open_agents()
        project_card = self.page.locator(
            "article[data-nv-agent='shared'][data-nv-agent-scope='proj']")
        self.wait_until(
            lambda: project_card.count() == 1,
            timeout=20,
            message="Die projektbezogene Karte des Agenten shared fehlt")
        delete = project_card.locator("[data-nv-action='agent-delete']")
        self.assertEqual(
            1, delete.count(),
            "Die Agentenkarte bietet keinen Löschknopf "
            "[data-nv-action='agent-delete']")
        project_file = self.project_agent_file("shared")
        global_file = self.agents_dir / "shared.md"
        delete.first.click()
        self.page.wait_for_timeout(300)
        # Der Bestätigungsweg ist nicht vorgeschrieben: Dialog (wird in
        # setUp angenommen) oder sichtbarer Inline-Knopf in Karte/Seite.
        for root in (project_card, self.page.locator("[data-nv-confirm]"),
                     self.page.locator("[role='dialog']"), self.page):
            if self.click_confirm_if_shown(root):
                break
        self.wait_until(
            lambda: not project_file.exists(), timeout=20,
            message="Der Projekt-Agent wurde nicht gelöscht")
        self.assertTrue(
            global_file.exists(),
            "Das Löschen des Projekt-Agenten entfernte die globale Datei")
        self.assertEqual(
            SHARED_GLOBAL_AGENT, global_file.read_text(encoding="utf-8"),
            "Das Löschen des Projekt-Agenten veränderte die globale Datei")

        self.page.goto(self.base + "/#/agents")
        self.page.locator("[data-nv-agent-list]").wait_for(
            state="visible", timeout=20000)
        self.assertEqual(
            1, self.page.locator(
                "article[data-nv-agent='shared']"
                "[data-nv-agent-scope='global']").count(),
            "Nach dem Löschen fehlt die globale Karte des Agenten shared")
        self.assertEqual(
            0, self.page.locator(
                "article[data-nv-agent='shared']"
                "[data-nv-agent-scope='proj']").count(),
            "Die gelöschte projektbezogene Karte steht weiterhin in der "
            "Liste")


# ===========================================================================
# Browserabnahme — Subagenten-Parallelisierung in der Agentenverwaltung
# ===========================================================================

import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright


OWN_LABEL = "Subagenten des eigenen Typs erlauben"

FAKE_OPENCODE_f32 = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf 'opencode 2.1.4\\n'
    exit 0
    ;;
  models)
    printf 'opencode/vibe-modell\\nopencode/tester-modell\\nopencode/helper-modell\\nopencode/neu\\n'
    exit 0
    ;;
esac
exit 2
"""


# F32 Runde 2: Ein gewöhnlicher Subagent mit bestehender Selbstfreigabe.
# Genau dieser Zustand darf nicht über eine reine Rollenänderung zum
# Vibe-Agenten werden (Review High 1).
TESTER_SELF_AGENT = """---
description: Testet die Anwendung gründlich
mode: subagent
model: opencode/tester-modell
temperature: 0.1
permission:
  read: allow
  edit: deny
  task:
    "*": deny
    tester: allow
---

Teste die Anwendung.
"""


ISOLATED_ENV_f32 = (
    "VIBE",
    "VIBE_NO_CONTAINER",
    "HOME",
    "VIBE_STORAGE_LOCK_DIR",
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


def isolated_env_f32(root, home, port, fake_bin):
    env = os.environ.copy()
    for key in ISOLATED_ENV_f32:
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


class F32SubagentUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )

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
        fake.write_text(FAKE_OPENCODE_f32, encoding="utf-8")
        fake.chmod(0o755)

        cls._write_fixture()

        cls.port = free_port()
        env = isolated_env_f32(cls.root, cls.home, cls.port, fake_bin)
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
        (cls.global_agents / "vibe-agent.md").write_text(
            VIBE_AGENT, encoding="utf-8"
        )
        (cls.global_agents / "tester.md").write_text(
            TESTER_AGENT, encoding="utf-8"
        )
        (cls.global_agents / "helper.md").write_text(
            HELPER_AGENT, encoding="utf-8"
        )
        (cls.state / "profiles.json").write_text(
            json.dumps({"rollen": {"vibe-agent": "vibe"}}), encoding="utf-8"
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
        try:
            os.killpg(cls.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        cls.tmp.cleanup()

    def setUp(self):
        self._write_fixture()
        agents_json = self.project / ".vibe" / "agents.json"
        if agents_json.exists():
            agents_json.unlink()
        self.page = self.browser.new_page(viewport={"width": 1500, "height": 1200})

    def tearDown(self):
        self.page.close()

    # ------------------------------------------------------------------ Helfer
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

    def reload_agents(self):
        self.page.reload(wait_until="load")
        self.page.get_by_role("button", name="Agents & Models").click()
        self.page.locator("#agents").wait_for()
        self.page.locator('tr[data-agent="tester"]').wait_for()

    def open_editor(self, name="tester"):
        self.page.locator(f'tr[data-agent="{name}"]').get_by_role(
            "button", name="Edit"
        ).click()
        self.page.get_by_label("Description", exact=True).wait_for()

    def own_checkbox(self):
        """Die F32-Checkbox über ihren zugänglichen Namen."""
        return self.page.get_by_role(
            "checkbox", name=re.compile(
                r"Subagenten des eigenen Typs erlauben|allow subagents of the same type",
                re.I))

    def subagents_box_text(self):
        return self.page.locator("[data-subagents]").inner_text().lower()

    def agent_text(self, name):
        path = self.global_agents / (name + ".md")
        return path.read_text(encoding="utf-8")

    def wait_for_agent_text(self, name, predicate, message):
        path = self.global_agents / (name + ".md")

        def check():
            if not path.exists():
                return False
            return predicate(path.read_text(encoding="utf-8"))

        self.wait_until(check, message=message)

    def roles(self):
        """Rollen aus profiles.json (geschrieben vom Testserver)."""
        return json.loads(
            (self.state / "profiles.json").read_text(encoding="utf-8")
        )["rollen"]

    def toasts_text(self):
        return self.page.locator("#toasts").inner_text().lower()

    def wait_for_toast(self, needle, message):
        deadline = time.time() + 10
        seen = []
        while time.time() < deadline:
            shown = self.toasts_text()
            if needle in shown:
                return
            if shown and shown not in seen:
                seen.append(shown)
            time.sleep(0.05)
        history = " | ".join(text.replace("\n", " | ") for text in seen) or "(kein Toast)"
        self.fail(message + " — angezeigt: " + history)

    # ---------------------------------------------------------------- Testfälle
    def test_01_regular_agent_enables_self_spawn_persists_and_removes_it(self):
        """AK UI: Eigen-Checkbox ist standardmäßig aus, speichert und bleibt erhalten."""
        self.open_agents()
        self.open_editor("tester")
        self.page.get_by_label("Subagent permissions", exact=True).select_option(
            value="ausgewählt"
        )

        own = self.own_checkbox()
        own.wait_for()
        self.assertFalse(
            own.is_checked(),
            "Der Selbstaufruf darf kein Standard sein (Checkbox ungehakt)",
        )

        own.check()
        self.page.get_by_role("button", name="Save", exact=True).click()
        self.wait_for_agent_text(
            "tester",
            lambda text: "tester: allow" in text,
            "Der Selbstaufruf wurde nicht in die Agentendatei geschrieben",
        )
        saved = self.agent_text("tester")
        self.assertIn('"*": deny', saved)
        self.assertIn("tester: allow", saved)
        self.assertIn("description: Testet die Anwendung gründlich", saved)

        # Editor neu laden: Der Haken muss aus der gespeicherten Datei kommen.
        self.reload_agents()
        self.open_editor("tester")
        self.assertEqual(
            self.page.get_by_label("Subagent permissions", exact=True).input_value(),
            "ausgewählt",
        )
        own = self.own_checkbox()
        own.wait_for()
        self.assertTrue(own.is_checked(), "Der gespeicherte Haken fehlt nach dem Neuladen")

        # Abwählen und speichern entfernt den Eigennamen wieder.
        own.uncheck()
        self.page.get_by_role("button", name="Save", exact=True).click()
        self.wait_for_agent_text(
            "tester",
            lambda text: "task: deny" in text,
            "Das Abwählen wurde nicht gespeichert",
        )
        self.assertNotIn("tester: allow", self.agent_text("tester"))

    def test_02_own_checkbox_is_keyboard_operable(self):
        """AK UI: Die Eigen-Checkbox ist fokussierbar und mit Space bedienbar."""
        self.open_agents()
        self.open_editor("tester")
        self.page.get_by_label("Subagent permissions", exact=True).select_option(
            value="ausgewählt"
        )
        own = self.own_checkbox()
        own.wait_for()

        own.focus()
        self.assertTrue(
            own.evaluate("element => element === document.activeElement"),
            "Die Eigen-Checkbox nimmt keinen Tastaturfokus an",
        )
        self.page.keyboard.press("Space")
        self.assertTrue(own.is_checked(), "Space hat die Checkbox nicht aktiviert")
        self.page.keyboard.press("Space")
        self.assertFalse(own.is_checked(), "Space hat die Checkbox nicht deaktiviert")

    def test_03_vibe_agent_gets_hint_instead_of_own_checkbox(self):
        """AK UI: Der Vibe-Agent sieht einen Hinweis, keine Eigen-Checkbox."""
        self.open_agents()
        self.open_editor("vibe-agent")
        self.page.get_by_label("Subagent permissions", exact=True).select_option(
            value="ausgewählt"
        )

        self.assertEqual(
            self.own_checkbox().count(),
            0,
            "Der Vibe-Agent darf keine Eigen-Checkbox anbieten",
        )
        text = self.subagents_box_text()
        self.assertIn("vibe", text, "Der Hinweis zum Vibe-Agenten fehlt")
        self.assertRegex(
            text,
            r"eigenen typs|own type",
            "Der Hinweis muss den Selbstaufruf des eigenen Typs nennen",
        )

    def test_04_primary_mode_hides_own_checkbox_with_mode_hint(self):
        """AK UI: mode primary blendet die Eigen-Checkbox aus und erklärt warum."""
        self.open_agents()
        self.open_editor("tester")
        self.page.get_by_label("Subagent permissions", exact=True).select_option(
            value="ausgewählt"
        )
        self.own_checkbox().wait_for()

        self.page.get_by_label("Mode", exact=True).select_option("primary")
        self.assertEqual(
            self.own_checkbox().count(),
            0,
            "Bei mode primary darf keine Eigen-Checkbox erscheinen",
        )
        text = self.subagents_box_text()
        self.assertRegex(
            text, r"modus|mode", "Der Hinweis zum erforderlichen Modus fehlt"
        )
        self.assertIn("subagent", text)
        self.assertRegex(text, r"\ball\b")

        # Zurück auf subagent: Checkbox erscheint wieder (ausgeblendet, nicht
        # dauerhaft entfernt).
        self.page.get_by_label("Mode", exact=True).select_option("subagent")
        self.own_checkbox().wait_for()

    def test_05_new_agent_offers_unchecked_own_checkbox(self):
        """AK UI: Auch neue Agenten können den Selbstaufruf wählen, aber nie als Standard."""
        self.open_agents()
        self.page.get_by_role("button", name="New agent").click()
        self.page.get_by_label("Description", exact=True).wait_for()

        # Initial steht „keine“: keine Eigen-Checkbox.
        self.assertEqual(self.own_checkbox().count(), 0)

        self.page.get_by_label("Name", exact=True).fill("neu")
        self.page.get_by_label("Subagent permissions", exact=True).select_option(
            value="ausgewählt"
        )
        own = self.own_checkbox()
        own.wait_for()
        self.assertFalse(own.is_checked(), "Die Checkbox darf nicht vorausgewählt sein")
        self.assertFalse(
            (self.global_agents / "neu.md").exists(),
            "Ohne Speichern darf keine Agentendatei entstehen",
        )

    def test_06_no_own_checkbox_for_none_and_all(self):
        """AK UI: Bei „keine“ und „alle“ gibt es keine Eigen-Checkbox (grüner Anker)."""
        self.open_agents()
        self.open_editor("tester")

        # Ausgangsstand: 'task: allow' → „alle“.
        self.assertEqual(
            self.page.get_by_label("Subagent permissions", exact=True).input_value(),
            "alle",
        )
        self.assertEqual(self.own_checkbox().count(), 0)

        self.page.get_by_label("Subagent permissions", exact=True).select_option(
            value="keine"
        )
        self.assertEqual(self.own_checkbox().count(), 0)

        self.page.get_by_label("Subagent permissions", exact=True).select_option(
            value="alle"
        )
        self.assertEqual(self.own_checkbox().count(), 0)

    def test_07_list_role_dropdown_rejects_vibe_for_self_spawn_agent(self):
        """F32 Runde 2: Das Rollen-Dropdown der Liste prüft die Selbstfreigabe.

        Vorbedingung: 'tester' ist gewöhnlicher Subagent mit Selbstfreigabe
        ('tester: allow' im task-Block); 'vibe-agent' trägt die Rolle vibe.
        Aktion: In der Agentenliste die Rolle von 'tester' auf „vibe“ stellen —
        genau der Weg, der in Runde 1 ohne Prüfung direkt ``agent_role_set``
        aufrief.
        Erwartung: sichtbare Ablehnung („nicht der Vibe-Agent werden“), das
        Dropdown springt auf den alten Wert zurück und 'tester' bekommt keine
        vibe-Rolle.
        """
        (self.global_agents / "tester.md").write_text(
            TESTER_SELF_AGENT, encoding="utf-8"
        )
        self.open_agents()
        role = self.page.locator('select[data-role="tester"]')
        self.assertEqual(role.input_value(), "", "tester darf anfangs keine Rolle haben")

        role.select_option("vibe")

        self.wait_for_toast(
            "nicht der vibe-agent werden",
            "Die Ablehnung des Rollenwechsels wurde nicht angezeigt",
        )
        self.assertEqual(
            role.input_value(),
            "",
            "Das Rollen-Dropdown muss nach der Ablehnung auf den alten Wert zurückspringen",
        )
        roles = self.roles()
        self.assertNotEqual(
            roles.get("tester"), "vibe",
            "tester mit Selbstfreigabe darf nicht Vibe-Agent werden",
        )
        self.assertEqual(
            roles.get("vibe-agent"), "vibe",
            "Der bisherige Vibe-Agent muss seine Rolle behalten",
        )

    def test_08_editor_role_change_keeps_rejection_when_self_allow_exists(self):
        """F32 Runde 2: Editor-Speichern mit *nur* geänderter Rolle wird geprüft.

        Vorbedingung: 'tester' mit Selbstfreigabe ('tester: allow').
        Aktion: Im Editor ausschließlich die Rolle auf „vibe“ stellen und
        speichern — ohne Änderung an den Subagenten-Rechten. Die Oberfläche
        sendet dann nur ``role``, aber kein ``task_allowed`` (der Weg aus
        Review High 1).
        Erwartung: sichtbare Ablehnung, die Agentendatei bleibt unverändert
        (die Selbstfreigabe geht nicht verloren) und 'tester' wird nicht
        Vibe-Agent.
        """
        path = self.global_agents / "tester.md"
        path.write_text(TESTER_SELF_AGENT, encoding="utf-8")
        before = path.read_text(encoding="utf-8")

        self.open_agents()
        self.open_editor("tester")
        self.page.get_by_label("Role", exact=True).select_option("vibe")
        self.page.get_by_role("button", name="Save", exact=True).click()

        self.wait_for_toast(
            "eigenen typs",
            "Der Editor-Speichervorgang wurde nicht abgelehnt",
        )
        self.assertEqual(
            path.read_text(encoding="utf-8"),
            before,
            "Die Agentendatei darf bei einer abgelehnten Rollenänderung unverändert bleiben",
        )
        roles = self.roles()
        self.assertNotEqual(roles.get("tester"), "vibe")
        self.assertEqual(
            roles.get("vibe-agent"), "vibe",
            "Der bisherige Vibe-Agent muss seine Rolle behalten",
        )


# ===========================================================================
# Browserabnahme: Combobox, Agentenliste, Wizard und Editor
# ===========================================================================

import http.client
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402


FAKE_OPENCODE_f33 = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf 'opencode v2.1.4\\n'
    exit 0
    ;;
  models)
    printf 'opencode/vibe-modell\\nopencode/test-modell\\nopencode/schnell-modell\\n'
    exit 0
    ;;
esac
exit 2
"""

GLOBAL_AGENT_f33 = """---
description: Globaler Agent
mode: subagent
model: opencode/vibe-modell
permission:
  read: allow
  edit: deny
---

Globaler Prompt.
"""

SECOND_AGENT = """---
description: Zweiter Agent
mode: subagent
model: opencode/test-modell
permission:
  read: allow
  edit: deny
---

Zweiter Prompt.
"""


PROJECT_AGENT_f33 = """---
description: Projektgebundener Agent
mode: subagent
model: opencode/schnell-modell
permission:
  read: allow
  edit: deny
---

Projekt-Prompt.
"""

PRIMARY_AGENT = """---
description: Primaeragent Test
mode: primary
model: opencode/vibe-modell
permission:
  read: allow
  edit: deny
---

Steuert die anderen Agenten.
"""


class F33AgentsTest(unittest.TestCase):
    """Dashboard, Browser, opencode-Attrappe, isoliertes VIBE-Root."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        cls.home = cls.root / "home"
        cls.agents_dir = cls.home / ".config" / "opencode" / "agents"
        cls.agents_dir.mkdir(parents=True)
        cls.state = cls.root / "_state"
        cls.state.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        fake_bin = cls.root / "fakebin"
        fake_bin.mkdir()
        fake = fake_bin / "opencode"
        fake.write_text(FAKE_OPENCODE_f33, encoding="utf-8")
        fake.chmod(0o755)
        (cls.root / "tmp").mkdir()
        (cls.root / "tmux").mkdir()

        cls.port = free_port()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                    "TMUX", "TMUX_PANE"):
                env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_STATE": str(cls.state),
            "VIBE_RUNTIME": str(cls.log_dir),
            "HOME": str(cls.home),
            "TMPDIR": str(cls.root / "tmp"),
            "TMUX_TMPDIR": str(cls.root / "tmux"),
            "VIBE_CONFIG_FILE": str(
                cls.home / ".config" / "vibe" / "config.json"),
            "PATH": str(fake_bin) + os.pathsep + env.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        cls.env = env
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=cls.server_log, stderr=subprocess.STDOUT, text=True,
            start_new_session=True)
        cls.pgid = os.getpgid(cls.proc.pid)
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 30
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                            ("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: "
                    + (cls.root / "web-server.log").read_text(
                        encoding="utf-8", errors="replace"))
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser.close()
            cls.playwright.stop()
        finally:
            if cls.proc.poll() is None:
                cls.proc.terminate()
                try:
                    cls.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls.proc.kill()
                    cls.proc.wait()
            try:
                os.killpg(cls.pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            cls.server_log.close()
            cls.tmp.cleanup()

    def setUp(self):
        self._reset_fixture()
        # GH-117: angeheftete Agenten und weitere Einstellungen stehen jetzt
        # auch serverseitig; ohne Reset startet der nächste Fall mit Pins aus
        # dem vorherigen Fall. Das neue Browserprofil hat leeren localStorage.
        (self.state / "settings.json").unlink(missing_ok=True)
        self.post_language("en")
        self.page_errors = []
        self.requests = []
        self.context = self.browser.new_context(
            viewport={"width": 1500, "height": 1100})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))
        self.page.on("request",
                     lambda request: self.requests.append(request.url))

    def tearDown(self):
        self.page.close()
        self.context.close()

    # ---------- Fixture und Helfer ----------

    def _reset_fixture(self):
        """Schreibt die Agenten-Fixture neu und räumt Sicherungen auf."""
        for item in self.agents_dir.glob("*.md"):
            item.unlink()
        (self.agents_dir / "tester.md").write_text(
            GLOBAL_AGENT_f33, encoding="utf-8")
        (self.agents_dir / "zweiter.md").write_text(
            SECOND_AGENT, encoding="utf-8")
        (self.agents_dir / "defekt.md").write_text(
            BROKEN_AGENT, encoding="utf-8")
        (self.state / "profiles.json").write_text(
            json.dumps({"rollen": {"tester": "coder"}},
                       ensure_ascii=False), encoding="utf-8")
        backups = self.state / "agent-backups"
        if backups.exists():
            for item in sorted(backups.rglob("*"), reverse=True):
                if item.is_file():
                    item.unlink()
        agents_json = self.project / ".vibe" / "agents.json"
        if agents_json.exists():
            agents_json.unlink()
        project_agents = self.project / ".opencode" / "agents"
        project_agents.mkdir(parents=True, exist_ok=True)
        for item in project_agents.glob("*.md"):
            item.unlink()
        (project_agents / "projhelfer.md").write_text(
            PROJECT_AGENT_f33, encoding="utf-8")

    def wait_until(self, predicate, timeout=20,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def post_language(self, lang):
        body = json.dumps({"language": lang}).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", "/api/language", body=body, headers={
                "Host": f"127.0.0.1:{self.port}", "X-Token": self.token,
                "Content-Type": "application/json"})
            conn.getresponse().read()
        finally:
            conn.close()

    def post_json(self, path, payload):
        body = json.dumps(payload).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", path, body=body, headers={
                "Host": f"127.0.0.1:{self.port}", "X-Token": self.token,
                "Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, json.loads(
                response.read().decode("utf-8", "replace") or "{}")
        finally:
            conn.close()

    def create_primary_agent(self, name="chief"):
        status, data = self.post_json("/api/agent", {
            "action": "save",
            "scope": "global",
            "name": name,
            "text": PRIMARY_AGENT,
            "create": True,
        })
        self.assertEqual(200, status,
                         "Der Test konnte keinen Primäragenten anlegen")
        self.assertTrue(data.get("ok"),
                        "Der Test konnte keinen Primäragenten anlegen: "
                        + repr(data))

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_agents(self):
        self.boot()
        self.page.goto(self.base + "/#/agents")
        self.page.locator("main#nv-main[data-nv-view='agents']").wait_for(
            state="visible", timeout=25000)
        self.page.locator("[data-nv-agent-list]").wait_for(
            state="visible", timeout=20000)

    def open_editor(self, name="tester"):
        self.boot()
        self.page.goto(self.base + f"/#/agents/{name}")
        self.page.locator("[data-nv-agent-editor]").wait_for(
            state="visible", timeout=25000)

    def open_wizard(self):
        self.open_agents()
        wizard = self.page.locator("[data-nv-wizard]")
        if not (wizard.count() and wizard.first.is_visible()):
            self.page.locator("[data-nv-action='agent-new']").click()
        wizard.first.wait_for(state="visible", timeout=20000)
        return wizard.first

    def wizard_goto(self, step, name="wizardprobe"):
        """Öffnet den Wizard, füllt den Namen und geht bis ``step``."""
        wizard = self.open_wizard()
        wizard.locator("[data-nv-field='name']").fill(name)
        for _ in range(step - 1):
            self.page.locator("[data-nv-wizard-next]").click()
            self.page.wait_for_timeout(150)
        wizard.locator(f"section[data-nv-step='{step}']").wait_for(
            state="visible", timeout=15000)
        return wizard

    def card(self, name, scope=None):
        selector = f"article[data-nv-agent='{name}']"
        if scope:
            selector += f"[data-nv-agent-scope='{scope}']"
        return self.page.locator(selector)

    def select_options(self, select):
        return select.locator("option").evaluate_all(
            "nodes => nodes.map(n => [n.value, (n.textContent || '').trim()])")

    def toast_text(self):
        nodes = self.page.locator("#nv-toasts .nv-toast")
        return "\n".join(nodes.all_inner_texts())

    def backup_files(self):
        folder = self.state / "agent-backups" / "global"
        if not folder.exists():
            return []
        return sorted(folder.glob("tester-*.md"))

    def confirmation_text(self):
        """Sichtbarer Bestätigungstext; fällt auf den Editor zurück."""
        for selector in ("[data-nv-confirm]:visible", "[role='dialog']:visible"):
            nodes = self.page.locator(selector)
            if nodes.count():
                return nodes.first.inner_text()
        return self.page.locator("[data-nv-agent-editor]").inner_text()

    def assert_no_page_errors(self):
        self.assertEqual(
            [], self.page_errors, "Die Oberfläche erzeugte JavaScript-Fehler")


class ComboboxWidgetTest(F33AgentsTest):
    def test_combobox_opens_filters_selects_and_closes(self):
        """Vorbedingung: angemeldet. Aktion: ``NV.combobox`` mit vier Werten
        direkt erzeugen und bedienen.

        Erwartung: Container ``div[data-nv-combobox][data-nv-field]`` mit
        ``input[role=combobox]`` und ``ul[data-nv-combobox-list]``; Klick
        öffnet (``aria-expanded="true"``); Eingabe „BETA“ filtert
        case-insensitiv auf den einen Treffer; Pfeil ab + Enter wählt und
        setzt ``data-nv-value`` samt Eingabewert; Esc schließt die Liste.
        """
        self.boot()
        created = self.page.evaluate(
            """() => {
              const host = document.createElement('div');
              host.id = 'cb-probe';
              document.body.appendChild(host);
              if (!window.NV || typeof NV.combobox !== 'function') return false;
              const node = NV.combobox(
                ['alpha-model', 'beta-model', 'gamma-model', 'alpha-zwei'],
                'alpha-model', {field: 'model'});
              host.appendChild(node);
              return true;
            }""")
        self.assertTrue(created, "NV.combobox ist nicht verfügbar")
        container = self.page.locator(
            "#cb-probe div[data-nv-combobox][data-nv-field='model']")
        self.assertEqual(1, container.count(),
                         "Der Combobox-Container trägt nicht "
                         "data-nv-combobox/data-nv-field")
        field = container.locator("input[data-nv-combobox-input]")
        self.assertEqual(1, field.count(),
                         "Das Combobox-Eingabefeld fehlt")
        self.assertEqual("combobox", field.get_attribute("role"),
                         "Das Eingabefeld hat nicht role=combobox")
        self.assertNotEqual(
            "true", field.get_attribute("aria-expanded"),
            "Die Liste ist ohne Klick bereits geöffnet")
        self.assertEqual(
            1, container.locator("ul[data-nv-combobox-list]").count(),
            "Die Combobox-Liste ul[data-nv-combobox-list] fehlt")

        field.click()
        self.wait_until(
            lambda: field.get_attribute("aria-expanded") == "true",
            timeout=10,
            message="Der Klick öffnet die Combobox nicht (aria-expanded)")
        options = container.locator("li[data-nv-combobox-option]")
        self.assertGreaterEqual(options.count(), 4,
                                "Die geöffnete Liste zeigt nicht alle Werte")

        field.fill("BETA")
        self.wait_until(
            lambda: options.count() == 1,
            timeout=10,
            message="Die Eingabe filtert die Liste nicht case-insensitiv")
        self.assertIn("beta-model", (options.first.inner_text() or "").lower(),
                      "Der gefilterte Treffer ist nicht beta-model")

        field.press("ArrowDown")
        field.press("Enter")
        self.wait_until(
            lambda: container.get_attribute("data-nv-value") == "beta-model",
            timeout=10,
            message="Enter übernimmt die Auswahl nicht in data-nv-value")
        self.assertEqual(
            "beta-model", field.input_value(),
            "Der gewählte Wert steht nicht im Eingabefeld")

        field.click()
        self.wait_until(
            lambda: field.get_attribute("aria-expanded") == "true",
            timeout=10,
            message="Die Combobox ließ sich nicht erneut öffnen")
        field.press("Escape")
        self.wait_until(
            lambda: field.get_attribute("aria-expanded") != "true",
            timeout=10,
            message="Esc schließt die Combobox nicht")
        self.assertFalse(
            container.locator("ul[data-nv-combobox-list]").is_visible(),
            "Die Liste bleibt nach Esc sichtbar")
        self.assert_no_page_errors()


class AgentListTest(F33AgentsTest):
    def test_pinning_moves_agent_to_pinned_section_and_persists(self):
        """Vorbedingung: globale Agenten ``tester``/``zweiter``, Projektagent
        ``projhelfer``, nichts angeheftet.

        Aktion: Anpinn-Knopf der Karte ``tester`` klicken, dann erneut.
        Erwartung: ``aria-pressed`` false → true; die Karte steht in
        ``section[data-nv-pinned-agents]`` oberhalb der Liste;
        ``localStorage['nv-pinned-agents']`` enthält
        ``{"scope":"global","name":"tester"}``. Erneuter Klick hebt auf
        (Storage leer, Karte nicht mehr angeheftet).
        """
        self.open_agents()
        card = self.card("tester", "global")
        card.wait_for(state="visible", timeout=20000)
        pin = card.locator("[data-nv-action='agent-pin']")
        self.assertEqual(
            1, pin.count(),
            "Die Agentenkarte hat keinen Anpinn-Knopf "
            "[data-nv-action='agent-pin']")
        self.assertNotEqual(
            "true", pin.first.get_attribute("aria-pressed"),
            "Die Karte ist ohne Zutun bereits angeheftet")

        pin.first.click()
        self.wait_until(
            lambda: pin.first.get_attribute("aria-pressed") == "true",
            timeout=10,
            message="Der Anpinn-Knopf setzt aria-pressed nicht auf true")
        pinned = self.page.locator("section[data-nv-pinned-agents]")
        pinned.wait_for(state="visible", timeout=10000)
        self.assertEqual(
            1, pinned.locator(
                "article[data-nv-agent='tester']"
                "[data-nv-agent-scope='global']").count(),
            "Die angeheftete Karte fehlt in section[data-nv-pinned-agents]")
        stored = json.loads(self.page.evaluate(
            "() => window.localStorage.getItem('nv-pinned-agents')") or "[]")
        self.assertTrue(
            any(isinstance(item, dict)
                and item.get("name") == "tester"
                and item.get("scope") == "global"
                for item in stored),
            "nv-pinned-agents enthält nicht {scope:global,name:tester}: "
            + repr(stored))
        pinned_box = pinned.bounding_box()
        list_box = self.page.locator("[data-nv-agent-list]").bounding_box()
        self.assertIsNotNone(pinned_box)
        self.assertIsNotNone(list_box)
        self.assertLess(
            pinned_box["y"], list_box["y"],
            "Die angeheftete Sektion steht nicht oberhalb der Liste")

        pin.first.click()
        self.wait_until(
            lambda: pin.first.get_attribute("aria-pressed") == "false",
            timeout=10,
            message="Der erneute Klick hebt das Anheften nicht auf")
        stored = json.loads(self.page.evaluate(
            "() => window.localStorage.getItem('nv-pinned-agents')") or "[]")
        self.assertEqual([], stored,
                         "nv-pinned-agents ist nach dem Aufheben nicht leer: "
                         + repr(stored))
        self.assertEqual(
            0, pinned.locator(
                "article[data-nv-agent='tester']"
                "[data-nv-agent-scope='global']").count(),
            "Die Karte bleibt nach dem Aufheben angeheftet")
        self.assert_no_page_errors()

    def test_search_filters_agent_cards_live(self):
        """Vorbedingung: Agenten mit unterschiedlichen Namen/Beschreibungen.

        Aktion: ``input[data-nv-agent-search]`` mit „Zweiter“ füllen, dann
        leeren. Erwartung: Nur ``zweiter`` bleibt sichtbar (Treffer in der
        Beschreibung), ``tester``/``defekt`` werden verborgen; nach dem Leeren
        sind wieder alle Karten sichtbar.
        """
        self.open_agents()
        search = self.page.locator("input[data-nv-agent-search]")
        search.wait_for(state="visible", timeout=20000)
        search.fill("Zweiter")
        self.wait_until(
            lambda: self.card("zweiter").is_visible()
            and not self.card("tester").is_visible(),
            timeout=10,
            message="Die Agentensuche filtert die Karten nicht live")
        self.assertFalse(self.card("defekt").is_visible(),
                         "Die Suche blendet defekt trotz Nichttreffer ein")

        search.fill("")
        self.wait_until(
            lambda: self.card("tester").is_visible()
            and self.card("defekt").is_visible(),
            timeout=10,
            message="Nach dem Leeren sind nicht wieder alle Karten sichtbar")
        self.assert_no_page_errors()

    def test_tag_filter_toggles_cards(self):
        """Vorbedingung: globaler Agent ``tester`` und Projektagent
        ``projhelfer``.

        Aktion: Tag-Filter „Global“ klicken, dann erneut.
        Erwartung: ``div[data-nv-agent-tag-filters]`` enthält
        ``button[data-nv-tag-filter]``; der Global-Filter blendet den
        Projektagenten aus (``aria-pressed="true"``), der erneute Klick hebt
        den Filter auf und zeigt ihn wieder.
        """
        self.open_agents()
        filters = self.page.locator("div[data-nv-agent-tag-filters]")
        filters.wait_for(state="visible", timeout=20000)
        chips = filters.locator("button[data-nv-tag-filter]")
        self.assertGreaterEqual(
            chips.count(), 1,
            "Die Tag-Filter-Leiste enthält keine Umschalt-Chips")
        global_filter = filters.locator(
            "button[data-nv-tag-filter]", has_text=re.compile("global", re.I))
        self.assertGreaterEqual(
            global_filter.count(), 1,
            "Es gibt keinen Global-Tag-Filter")
        project_card = self.card("projhelfer")
        project_card.wait_for(state="visible", timeout=20000)

        global_filter.first.click()
        self.wait_until(
            lambda: not project_card.is_visible(),
            timeout=10,
            message="Der Global-Filter blendet den Projektagenten nicht aus")
        self.assertEqual(
            "true", global_filter.first.get_attribute("aria-pressed"),
            "Der aktive Tag-Filter setzt aria-pressed nicht auf true")
        self.assertTrue(self.card("tester").is_visible(),
                        "Der Global-Filter blendet globale Karten aus")

        global_filter.first.click()
        self.wait_until(
            lambda: project_card.is_visible(),
            timeout=10,
            message="Der erneute Klick hebt den Tag-Filter nicht auf")
        self.assertNotEqual(
            "true", global_filter.first.get_attribute("aria-pressed"),
            "Der aufgehobene Filter lässt aria-pressed auf true")
        self.assert_no_page_errors()

    def test_name_and_tags_are_separate_rows(self):
        """Vorbedingung: Agent ``tester`` mit Rolle (Tag vorhanden).

        Aktion: Karte messen. Erwartung: ``h3.nv-agent-name`` und
        ``div[data-nv-agent-tags]`` existieren; die Tags sind kein Kind des
        Namens und stehen vollständig unter der Namenszeile (Tags-Oberkante
        nicht über der Namensunterkante) — keine Überblendung.
        """
        self.open_agents()
        card = self.card("tester", "global")
        card.wait_for(state="visible", timeout=20000)
        name = card.locator("h3.nv-agent-name")
        self.assertEqual(1, name.count(),
                         "Die Karte hat keinen Namen h3.nv-agent-name")
        tags = card.locator("div[data-nv-agent-tags]")
        self.assertEqual(1, tags.count(),
                         "Die Karte hat keine Tag-Zeile "
                         "div[data-nv-agent-tags]")
        self.assertEqual(
            0, name.locator("[data-nv-agent-tags]").count(),
            "Die Tags liegen innerhalb des Namens statt in einer eigenen Zeile")
        self.assertTrue(tags.is_visible(), "Die Tag-Zeile ist nicht sichtbar")
        name_box = name.bounding_box()
        tags_box = tags.bounding_box()
        self.assertIsNotNone(name_box, "Der Name hat keine Position")
        self.assertIsNotNone(tags_box, "Die Tag-Zeile hat keine Position")
        self.assertGreaterEqual(
            tags_box["y"], name_box["y"] + name_box["height"] - 1,
            "Die Tags überblenden die Namenszeile: "
            f"Name {name_box}, Tags {tags_box}")
        self.assert_no_page_errors()


class WizardTest(F33AgentsTest):
    def test_wizard_has_five_steps_and_step_indicator(self):
        """Vorbedingung: angemeldet, Wizard geöffnet.

        Aktion: Schritte zählen, Indikator auf Schritt 1 und 2 lesen.
        Erwartung: Genau fünf ``section[data-nv-step="1..5"]``; der Indikator
        nennt „Schritt 1 von 5“ (bzw. „Step 1 of 5“) und nach „Weiter“
        „Schritt 2 von 5“.
        """
        wizard = self.open_wizard()
        for step in (1, 2, 3, 4, 5):
            self.assertEqual(
                1, wizard.locator(f"section[data-nv-step='{step}']").count(),
                f"Wizard-Schritt {step} fehlt")
        self.assertEqual(
            0, wizard.locator("section[data-nv-step='6']").count(),
            "Der Wizard hat mehr als fünf Schritte")
        self.assertRegex(
            wizard.inner_text(), r"(?i)(schritt|step)\s*1\s*(von|of)\s*5",
            "Der Schrittzähler nennt nicht „Schritt 1 von 5“: "
            + wizard.inner_text()[:200])

        wizard.locator("[data-nv-field='name']").fill("zaehlprobe")
        self.page.locator("[data-nv-wizard-next]").click()
        self.wait_until(
            lambda: re.search(r"(?i)(schritt|step)\s*2\s*(von|of)\s*5",
                              wizard.inner_text()) is not None,
            timeout=10,
            message="Der Schrittzähler folgt dem Wechsel nicht (2 von 5)")
        self.assert_no_page_errors()

    def test_step_two_explains_modes_and_names_all_as_agent(self):
        """Vorbedingung: kein Primäragent in der Fixture.

        Aktion: Schritt 2 öffnen, Modus-Optionen lesen.
        Erwartung: ``select[data-nv-field="mode"]`` bietet subagent, all und
        primary; jede Option trägt eine Erklärung (länger als der Wert); die
        Option ``all`` heißt sichtbar „Agent“ (nicht „all“). Das Modell ist
        eine Combobox (``div[data-nv-combobox][data-nv-field="model"]``) mit
        leerer Standardoption („— Standardmodell —“).
        """
        wizard = self.wizard_goto(2)
        mode = wizard.locator("select[data-nv-field='mode']")
        mode.wait_for(state="visible", timeout=15000)
        options = dict(self.select_options(mode))
        for value in ("subagent", "all", "primary"):
            self.assertIn(value, options,
                          f"Die Einsatzart {value!r} fehlt: {options}")
            self.assertGreater(
                len(options[value]), len(value) + 3,
                f"Die Option {value!r} ist nicht erklärt: {options[value]!r}")
        self.assertNotEqual(
            "all", options["all"].strip().lower(),
            "Die Option all heißt sichtbar weiterhin „all“")
        self.assertRegex(
            options["all"], r"(?i)agent",
            "Die Option all wird nicht als „Agent“ bezeichnet: "
            + repr(options["all"]))

        combobox = wizard.locator(
            "div[data-nv-combobox][data-nv-field='model']")
        self.assertEqual(
            1, combobox.count(),
            "Das Modellfeld ist keine Combobox "
            "(div[data-nv-combobox][data-nv-field=model])")
        field = combobox.locator("input[data-nv-combobox-input]")
        field.click()
        options_text = combobox.locator(
            "li[data-nv-combobox-option]").all_inner_texts()
        self.assertTrue(
            any(re.search(r"(?i)standard", text) for text in options_text),
            "Der Modell-Combobox fehlt die leere Standardoption: "
            + repr(options_text))
        self.assert_no_page_errors()

    def test_mode_help_updates_with_the_selection(self):
        """Vorbedingung: Wizard Schritt 2.

        Aktion: ``p[data-nv-mode-help]`` lesen, dann all, subagent und primary
        wählen. Erwartung: Der Hilfetext ist sichtbar, nicht leer und ändert
        sich je Auswahl; er nennt die gewählte Einsatzart (agent/subagent/
        primary).
        """
        wizard = self.wizard_goto(2)
        help_text = wizard.locator("p[data-nv-mode-help]")
        help_text.wait_for(state="visible", timeout=15000)
        initial = (help_text.inner_text() or "").strip()
        self.assertTrue(initial, "Der Modus-Hilfetext ist leer")
        mode = wizard.locator("select[data-nv-field='mode']")

        mode.select_option("all")
        self.wait_until(
            lambda: (help_text.inner_text() or "").strip() != initial,
            timeout=10,
            message="Der Modus-Hilfetext folgt der Auswahl all nicht")
        self.assertRegex(
            help_text.inner_text(), r"(?i)agent",
            "Der Hilfetext zu all nennt nicht „Agent“")
        all_help = help_text.inner_text()

        mode.select_option("subagent")
        self.wait_until(
            lambda: (help_text.inner_text() or "").strip() != all_help.strip(),
            timeout=10,
            message="Der Modus-Hilfetext folgt der Auswahl subagent nicht")
        self.assertRegex(
            help_text.inner_text(), r"(?i)subagent",
            "Der Hilfetext zu subagent nennt nicht „Subagent“")

        mode.select_option("primary")
        self.wait_until(
            lambda: re.search(r"(?i)primary|primär",
                              help_text.inner_text() or "") is not None,
            timeout=10,
            message="Der Hilfetext zu primary erklärt die Einsatzart nicht")
        self.assert_no_page_errors()

    def test_primary_option_exists_without_a_primary_agent(self):
        """Vorbedingung: kein Agent mit ``mode: primary`` in der Fixture.

        Aktion: Wizard Schritt 2 öffnen. Erwartung:
        ``select[data-nv-field="mode"]`` bietet die Option ``primary`` an.
        """
        wizard = self.wizard_goto(2)
        mode = wizard.locator("select[data-nv-field='mode']")
        values = [value for value, _text in self.select_options(mode)]
        self.assertIn(
            "primary", values,
            "Ohne Primäragenten fehlt die Option primary: " + repr(values))

    def test_primary_option_is_hidden_when_a_primary_agent_exists(self):
        """Vorbedingung: per API angelegter Agent ``chief`` mit
        ``mode: primary`` (POST /api/agent action=save).

        Aktion: Wizard Schritt 2 öffnen. Erwartung: Die Option ``primary``
        fehlt in ``select[data-nv-field="mode"]``, weil bereits ein
        Primäragent existiert.
        """
        self.create_primary_agent("chief")
        wizard = self.wizard_goto(2)
        mode = wizard.locator("select[data-nv-field='mode']")
        values = [value for value, _text in self.select_options(mode)]
        self.assertNotIn(
            "primary", values,
            "Trotz vorhandenem Primäragenten bietet der Wizard primary an: "
            + repr(values))
        self.assertIn("all", values,
                      "Der Wizard bietet die Einsatzart all nicht mehr an")

    def test_step_three_offers_permissions_and_uses_the_choice(self):
        """Vorbedingung: Wizard.

        Aktion: Schritt 3 öffnen, ``select[data-nv-field="perm"]`` und
        ``p[data-nv-perm-help]`` lesen, ``voll`` wählen, zu Schritt 4 gehen
        und die Prompt-Vorlage anfordern.
        Erwartung: Der Rechte-Select bietet mehrere Optionen (u. a. ``voll``),
        der Hilfetext ändert sich mit der Auswahl; der Template-Abruf
        (``POST /api/agent_template``) übergibt ``perm: "voll"`` statt fest
        ``lesen``.
        """
        wizard = self.wizard_goto(3)
        perm = wizard.locator("select[data-nv-field='perm']")
        perm.wait_for(state="visible", timeout=15000)
        values = [value for value, _text in self.select_options(perm)]
        self.assertGreaterEqual(len(values), 2,
                                "Der Rechte-Select bietet keine Auswahl: "
                                + repr(values))
        self.assertIn("voll", values,
                      "Die Rechte-Option voll fehlt: " + repr(values))
        perm_help = wizard.locator("p[data-nv-perm-help]")
        perm_help.wait_for(state="visible", timeout=10000)
        initial_help = (perm_help.inner_text() or "").strip()
        self.assertTrue(initial_help, "Der Rechte-Hilfetext ist leer")

        perm.select_option("voll")
        self.wait_until(
            lambda: (perm_help.inner_text() or "").strip() != initial_help,
            timeout=10,
            message="Der Rechte-Hilfetext folgt der Auswahl nicht")

        captured = {}

        def remember(request):
            if "/api/agent_template" in request.url and request.method == "POST":
                try:
                    captured["body"] = json.loads(request.post_data or "{}")
                except ValueError:
                    captured["body"] = {}

        self.page.on("request", remember)
        self.page.locator("[data-nv-wizard-next]").click()
        wizard.locator("section[data-nv-step='4']").wait_for(
            state="visible", timeout=15000)
        wizard.locator("[data-nv-action='prompt-template']").click()
        self.wait_until(
            lambda: "body" in captured, timeout=15,
            message="Der Vorlagenknopf löste keinen Template-Abruf aus")
        self.assertEqual(
            "voll", captured["body"].get("perm"),
            "Der Template-Aufruf übergibt nicht die gewählte Berechtigung: "
            + repr(captured["body"]))
        self.assert_no_page_errors()

    def test_step_four_prompt_is_large(self):
        """Vorbedingung: Wizard Schritt 4.

        Aktion: Prompt-Feld messen. Erwartung:
        ``textarea[data-nv-field="prompt"]`` hat ``rows >= 12`` und ist
        veränderbar (nicht ``disabled``/``readonly``).
        """
        wizard = self.wizard_goto(4)
        prompt = wizard.locator("textarea[data-nv-field='prompt']")
        prompt.wait_for(state="visible", timeout=15000)
        rows = prompt.get_attribute("rows")
        self.assertIsNotNone(rows, "Das Prompt-Feld hat kein rows-Attribut")
        self.assertGreaterEqual(
            int(rows), 12,
            "Das Prompt-Feld ist zu klein (rows=" + str(rows) + ")")
        self.assertFalse(prompt.is_disabled(), "Das Prompt-Feld ist deaktiviert")
        self.assertNotEqual(
            "true", (prompt.get_attribute("readonly") or "").lower(),
            "Das Prompt-Feld ist schreibgeschützt")
        self.assert_no_page_errors()

    def test_step_five_lists_fields_once_and_formats_the_prompt(self):
        """Vorbedingung: Wizard bis Schritt 4, Prompt mit zwei Zeilen.

        Aktion: Weiter zu Schritt 5. Erwartung: Die strukturierten Felder
        stehen genau einmal (der Agentenname erscheint einmal); der Prompt
        steht ausschließlich im formatierten Block
        ``pre[data-nv-review-prompt]`` mit sichtbarem Zeilenumbruch
        (``white-space: pre-wrap``) — nicht zusätzlich als Fließtext in der
        Feldliste.
        """
        wizard = self.wizard_goto(4, "reviewprobe")
        prompt = wizard.locator("textarea[data-nv-field='prompt']")
        prompt.fill("Zeile eins\nZeile zwei")
        self.page.locator("[data-nv-wizard-next]").click()
        step5 = wizard.locator("section[data-nv-step='5']")
        step5.wait_for(state="visible", timeout=15000)

        review = step5.locator("pre[data-nv-review-prompt]")
        self.assertEqual(
            1, review.count(),
            "Der formatierte Prompt-Block pre[data-nv-review-prompt] fehlt")
        review_text = review.inner_text()
        self.assertIn("Zeile eins", review_text)
        self.assertIn("Zeile zwei", review_text)
        self.assertIn(
            "\n", review_text,
            "Der Prompt-Block zeigt den Zeilenumbruch nicht an")
        white_space = review.evaluate(
            "node => getComputedStyle(node).whiteSpace")
        self.assertIn(
            white_space, ("pre-wrap", "break-spaces"),
            "Der Prompt-Block bricht Zeilen nicht sichtbar um: "
            + repr(white_space))

        text = step5.inner_text()
        self.assertEqual(
            1, text.count("Zeile eins"),
            "Der Prompt erscheint doppelt auf der Prüfseite: " + text)
        self.assertEqual(
            1, text.count("reviewprobe"),
            "Die strukturierten Felder nennen den Namen mehrfach: " + text)
        self.assert_no_page_errors()

    def test_create_is_reachable_without_scrolling_on_step_five(self):
        """Vorbedingung: Wizard bis Schritt 4 mit sehr langem Prompt (80
        Zeilen).

        Aktion: Weiter zu Schritt 5, Position des Anlegen-Knopfs messen.
        Erwartung: ``button[data-nv-action="agent-create"]`` liegt sichtbar im
        Viewport (sticky Aktionsleiste, kein Scrollen nötig); der
        „Weiter“-Knopf ``[data-nv-wizard-next]`` ist auf Schritt 5 nicht
        sichtbar (kein toter Knopf).
        """
        wizard = self.wizard_goto(4, "langprompt")
        wizard.locator("textarea[data-nv-field='prompt']").fill(
            "\n".join(f"Zeile {index} des langen Prompts" for index in range(1, 81)))
        self.page.locator("[data-nv-wizard-next]").click()
        wizard.locator("section[data-nv-step='5']").wait_for(
            state="visible", timeout=15000)

        create = wizard.locator("[data-nv-action='agent-create']")
        create.wait_for(state="visible", timeout=10000)
        box = create.bounding_box()
        self.assertIsNotNone(box, "Der Anlegen-Knopf hat keine Position")
        viewport = self.page.viewport_size
        self.assertGreaterEqual(box["y"], 0,
                                "Der Anlegen-Knopf liegt über dem Viewport")
        self.assertLessEqual(
            box["y"] + box["height"], viewport["height"] + 1,
            "Der Anlegen-Knopf liegt unterhalb des Viewports und ist nur "
            f"nach Scrollen erreichbar: {box} bei {viewport}")

        next_button = self.page.locator("[data-nv-wizard-next]")
        self.assertFalse(
            next_button.is_visible() if next_button.count() else False,
            "Auf Schritt 5 ist der tote „Weiter“-Knopf sichtbar")
        self.assert_no_page_errors()

    def test_cancel_warns_inline_before_discarding(self):
        """Vorbedingung: Wizard Schritt 1 mit eingegebenem Namen.

        Aktion: „Abbrechen“ klicken. Erwartung: Es erscheint die Inline-Warnung
        ``div[data-nv-wizard-cancel-confirm]`` mit „Ja, abbrechen“; der Wizard
        bleibt zunächst offen und der Name erhalten (kein Datenverlust ohne
        Bestätigung); erst der bestätigte Abbruch schließt den Wizard.
        """
        wizard = self.open_wizard()
        name = wizard.locator("[data-nv-field='name']")
        name.fill("abbrechprobe")
        self.page.locator("[data-nv-wizard-cancel]").click()

        confirm = wizard.locator("div[data-nv-wizard-cancel-confirm]")
        confirm.wait_for(state="visible", timeout=10000)
        self.assertRegex(
            confirm.inner_text(), r"(?i)verloren|lost|abbrechen|cancel",
            "Die Abbruch-Warnung erklärt den Datenverlust nicht: "
            + repr(confirm.inner_text()))
        yes = confirm.locator(
            "button", has_text=re.compile(r"ja,?\s*abbrechen|yes,?\s*cancel", re.I))
        self.assertGreaterEqual(
            yes.count(), 1,
            "Die Abbruch-Warnung bietet keinen „Ja, abbrechen“-Knopf")
        self.assertTrue(wizard.is_visible(),
                        "Der Wizard schließt sich vor der Bestätigung")
        self.assertEqual(
            "abbrechprobe", name.input_value(),
            "Die Eingaben gingen vor der Bestätigung verloren")

        yes.first.click()
        self.wait_until(
            lambda: not wizard.is_visible(), timeout=10,
            message="Der bestätigte Abbruch schließt den Wizard nicht")
        self.assertTrue(
            self.page.locator("[data-nv-agent-list]").is_visible(),
            "Nach dem Abbruch erscheint die Agentenliste nicht")
        self.assert_no_page_errors()


class EditorTest(F33AgentsTest):
    def test_assignments_are_loaded_only_after_expanding(self):
        """Vorbedingung: Agent ``tester``, Projekt ``proj``.

        Aktion: Editor öffnen, kurz warten, dann
        ``details[data-nv-assignments]`` aufklappen.
        Erwartung: Vor dem Aufklappen kein Abruf von ``/api/project-agents``;
        die Details sind geschlossen und enthalten den Platzhalter
        ``p[data-nv-assignments-hint]``; erst nach dem Aufklappen wird geladen
        (Request sichtbar) und die Zuordnung ``input[data-nv-assign="proj"]``
        erscheint.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        editor.wait_for(state="visible", timeout=20000)
        self.page.wait_for_timeout(800)
        self.assertFalse(
            any("/api/project-agents" in url for url in self.requests),
            "Der Editor lädt die Projektzuordnungen bereits beim Rendern")

        details = editor.locator("details[data-nv-assignments]")
        self.assertEqual(
            1, details.count(),
            "Die Projektzuordnungen liegen nicht in "
            "details[data-nv-assignments]")
        self.assertIsNone(details.get_attribute("open"),
                          "details[data-nv-assignments] ist standardmäßig offen")
        self.assertEqual(
            1, details.locator("p[data-nv-assignments-hint]").count(),
            "Der Platzhalter p[data-nv-assignments-hint] fehlt")

        summary = details.locator("summary")
        if summary.count():
            summary.first.click()
        else:
            details.first.click()
        self.wait_until(
            lambda: any("/api/project-agents" in url for url in self.requests),
            timeout=15,
            message="Beim Aufklappen wird /api/project-agents nicht geladen")
        editor.locator("input[data-nv-assign='proj']").wait_for(
            state="visible", timeout=15000)
        self.assert_no_page_errors()

    def test_back_button_is_secondary_and_returns_to_list(self):
        """Vorbedingung: Editor ``tester``.

        Aktion: ``button[data-nv-action="agent-back"]`` prüfen und klicken.
        Erwartung: Der Knopf ist sichtbar, trägt die Klasse ``nv-secondary``
        und ein ``aria-label``; der Klick öffnet die Agentenliste
        (``data-nv-view="agents"``).
        """
        self.open_editor("tester")
        back = self.page.locator("button[data-nv-action='agent-back']")
        back.wait_for(state="visible", timeout=15000)
        classes = (back.get_attribute("class") or "").split()
        self.assertIn(
            "nv-secondary", classes,
            "Der Zurück-Knopf ist nicht als nv-secondary gestaltet: "
            + repr(classes))
        self.assertTrue(
            (back.get_attribute("aria-label") or "").strip(),
            "Der Zurück-Knopf hat kein aria-label")
        back.click()
        self.page.locator("main#nv-main[data-nv-view='agents']").wait_for(
            state="visible", timeout=20000)
        self.assertTrue(
            self.page.locator("[data-nv-agent-list]").is_visible(),
            "Nach dem Zurück-Klick erscheint die Agentenliste nicht")
        self.assert_no_page_errors()

    def test_raw_toggle_changes_label_and_save_mode(self):
        """Vorbedingung: Editor ``tester`` im Feldmodus.

        Aktion: ``[data-nv-raw]`` klicken, Beschriftung und Speichermodus
        lesen. Erwartung: Die Beschriftung wechselt von „Rohtext anzeigen“ zu
        „Strukturierte Ansicht“ (``aria-pressed`` false → true); der
        Speichern-Knopf trägt sonst ``data-nv-mode="fields"`` („Änderungen
        speichern") und im Rohtextmodus ``data-nv-mode="raw"`` („Rohtext
        speichern"); ``p[data-nv-save-hint]`` nennt den gespeicherten Umfang
        und ändert sich mit dem Modus.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        raw = editor.locator("[data-nv-raw]")
        raw.wait_for(state="visible", timeout=15000)
        save = editor.locator("[data-nv-action='agent-save']")
        hint = editor.locator("p[data-nv-save-hint]")
        hint.wait_for(state="visible", timeout=10000)
        fields_hint = (hint.inner_text() or "").strip()
        self.assertTrue(fields_hint, "Der Speicher-Hinweis ist leer")
        self.assertRegex(
            raw.inner_text(), r"(?i)rohtext|raw",
            "Der Umschalter heißt nicht „Rohtext anzeigen“: "
            + repr(raw.inner_text()))
        self.assertNotEqual(
            "true", raw.get_attribute("aria-pressed"),
            "Der Rohtextmodus ist ohne Klick bereits aktiv")
        self.assertEqual(
            "fields", save.get_attribute("data-nv-mode"),
            "Der Speichern-Knopf trägt im Feldmodus nicht "
            "data-nv-mode=fields")
        self.assertRegex(
            save.inner_text(), r"(?i)änderungen|changes",
            "Der Speichern-Knopf heißt im Feldmodus nicht "
            "„Änderungen speichern“: " + repr(save.inner_text()))

        raw.click()
        self.wait_until(
            lambda: raw.get_attribute("aria-pressed") == "true",
            timeout=10,
            message="Der Umschalter setzt aria-pressed nicht auf true")
        self.assertRegex(
            raw.inner_text(), r"(?i)struktur|structured",
            "Der Umschalter heißt im Rohtextmodus nicht "
            "„Strukturierte Ansicht“: " + repr(raw.inner_text()))
        self.assertEqual(
            "raw", save.get_attribute("data-nv-mode"),
            "Der Speichern-Knopf trägt im Rohtextmodus nicht "
            "data-nv-mode=raw")
        self.assertRegex(
            save.inner_text(), r"(?i)rohtext|raw",
            "Der Speichern-Knopf heißt im Rohtextmodus nicht "
            "„Rohtext speichern“: " + repr(save.inner_text()))
        self.wait_until(
            lambda: (hint.inner_text() or "").strip() != fields_hint,
            timeout=10,
            message="Der Speicher-Hinweis nennt den Rohtextmodus nicht")
        self.assert_no_page_errors()

    def test_copy_confirmation_names_the_target(self):
        """Vorbedingung: Editor ``tester``, Projekt ``proj``.

        Aktion: ``[data-nv-action="agent-copy"]`` klicken. Erwartung: Die
        sichtbare Bestätigung nennt das Ziel deutlich („Nach 'proj'
        kopieren?" / „Copy to 'proj'?“), nicht nur eine stumme Auswahl.
        """
        self.open_editor("tester")
        editor = self.page.locator("[data-nv-agent-editor]")
        editor.locator("[data-nv-action='agent-copy']").click()
        self.wait_until(
            lambda: re.search(
                r"(?i)(nach|to)\s*['\"„]?proj", self.confirmation_text())
            is not None,
            timeout=15,
            message="Die Kopier-Bestätigung nennt das Ziel nicht deutlich: "
                    + repr(self.confirmation_text()[:300]))
        self.assert_no_page_errors()

    def test_backup_toast_says_backup_created_without_version_warning(self):
        """Vorbedingung: Agent ``tester`` ohne Sicherungen.

        Aktion: ``[data-nv-action="agent-backup"]`` klicken.
        Erwartung: Es entsteht eine Sicherungsdatei; der Toast meldet
        „Sicherung angelegt“ (Backend-Aktion ``backup`` aus WP6) und enthält
        keinen Versions-/Modellhinweis („nicht geprüft“).
        """
        self.open_editor("tester")
        before = len(self.backup_files())
        self.page.locator("[data-nv-action='agent-backup']").click()
        self.wait_until(
            lambda: "Sicherung angelegt" in self.toast_text(),
            timeout=25,
            message="Der Sicherungs-Toast meldet nicht „Sicherung angelegt“: "
                    + repr(self.toast_text()))
        self.assertNotIn(
            "nicht geprüft", self.toast_text(),
            "Der Sicherungs-Toast enthält weiterhin einen Versionshinweis: "
            + repr(self.toast_text()))
        self.wait_until(
            lambda: len(self.backup_files()) > before, timeout=15,
            message="Die Sicherung wurde nicht angelegt")
        self.assert_no_page_errors()

    def test_restore_shows_the_last_backup_info(self):
        """Vorbedingung: Agent ``tester`` mit angelegter Sicherung.

        Aktion: Sicherung anlegen, Editor neu laden,
        ``[data-nv-action="agent-restore"]`` klicken.
        Erwartung: Die Bestätigung zeigt ``span[data-nv-backup-info]`` mit
        einem Hinweis auf die letzte Sicherung (aus ``GET /api/agent`` →
        ``backups``).
        """
        self.open_editor("tester")
        self.page.locator("[data-nv-action='agent-backup']").click()
        self.wait_until(
            lambda: "Sicherung angelegt" in self.toast_text(),
            timeout=25,
            message="Die Vorbedingung (Sicherung anlegen) scheiterte: "
                    + repr(self.toast_text()))

        self.page.reload()
        self.page.locator("[data-nv-agent-editor]").wait_for(
            state="visible", timeout=25000)
        self.page.locator("[data-nv-action='agent-restore']").click()
        info = self.page.locator("span[data-nv-backup-info]")
        info.wait_for(state="visible", timeout=15000)
        text = (info.inner_text() or "").strip()
        self.assertTrue(text, "span[data-nv-backup-info] ist leer")
        self.assertRegex(
            text, r"(?i)sicherung|backup",
            "span[data-nv-backup-info] nennt die Sicherung nicht: "
            + repr(text))
        self.assert_no_page_errors()


if __name__ == "__main__":
    unittest.main()
