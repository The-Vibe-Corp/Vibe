"""Browserabnahme für die in AP03 neu aufgebaute Agentenverwaltung.

Die Tests starten das echte Dashboard auf einem eigenen Port und bedienen es
mit Chromium über Playwright. Geprüft wird ausschließlich die in AP03
vereinbarte Oberfläche:

* die allgemeine Agentenliste mit Vibe-Status, Aufgabe, Ergebnis,
  Subagenten-Rechten und Standardmodell,
* der Rollenwechsel über ``select[data-role]`` mit Wirkung in
  ``profiles.json``,
* das Speichern von Ergebnis, Rolle und Subagenten-Rechten aus dem Editor,
* das Prompt-Gerüst mit Aufgabe, Ergebnis und Grenzen,
* die Projekteinstellungen mit Standardauswahl nur für den Vibe-Agenten,
  Einblenden nicht konfigurierter globaler Agenten und unabhängiger
  Modellüberschreibung,
* echte Screenshots der allgemeinen Ansicht und der Projekteinstellungen.

Es findet kein Modellaufruf und kein Netzzugriff außerhalb von Loopback statt.
``opencode`` wird durch ein Ersatzprogramm beantwortet.
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
SHOTS = Path(os.environ.get("VIBE_VERIFY_SCREENSHOT_DIR", REPO / "docs" / "features"))
SHOT_GENERAL = SHOTS / "AP03-agenten.png"
SHOT_PROJECT = SHOTS / "AP03-projekt-agenten.png"

FAKE_OPENCODE = """#!/usr/bin/env bash
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


if __name__ == "__main__":
    unittest.main()
