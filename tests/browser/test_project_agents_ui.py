"""Browserabnahme für Agentenauswahl und Modellüberschreibung je Projekt (AP03).

Die Tests starten das echte Dashboard auf einem eigenen Port und bedienen es
mit Chromium über Playwright. Geprüft werden:

* die Modellauswahl im Agenteneditor wird ohne zusätzlichen Zwischenschritt
  gespeichert,
* die Projekteinstellungen zeigen standardmäßig nur den konfigurierten
  Vibe-Agenten; weitere systemweite Agenten lassen sich einblenden,
* projektlokale Agentendateien werden nicht angeboten,
* die Projektauswahl schreibt Version 2 mit ``aktiv`` und lässt den
  Vibe-Agenten konfiguriert.

Das frühere Verhalten mit Projektagenten und Konflikt-/Überschreibungsanzeige
wird nicht mehr erwartet: AP03 erlaubt in Projekten ausschließlich systemweite
Agenten. Die Screenshots der neuen Projektansicht entstehen in
``test_ap03_agents_ui``.
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
    printf 'opencode/start\\nopencode/neu\\nopencode/anderes\\nopencode/vibe-modell\\nopencode/tester-modell\\n'
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

AGENT = """---
description: Testagent
mode: subagent
model: opencode/start
temperature: 0.1
permission:
  read: allow
  edit: deny
  task: allow
---

Test-Prompt.
"""

LOCAL_AGENT = """---
description: Projektlokaler Agent
mode: subagent
model: opencode/lokal-modell
---

Nur im Projekt.
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


class ProjectAgentsBrowserTest(unittest.TestCase):
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
        (cls.global_agents / "tester.md").write_text(AGENT, encoding="utf-8")
        project_agents = cls.project / ".opencode" / "agents"
        project_agents.mkdir(parents=True, exist_ok=True)
        (project_agents / "lokal.md").write_text(LOCAL_AGENT, encoding="utf-8")
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
        self.page = self.browser.new_page(viewport={"width": 1500, "height": 1100})

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
        self.page.locator("#agents").wait_for()
        self.page.locator('tr[data-agent="tester"]').wait_for()

    def open_project_settings(self):
        self.page.goto(self.base + "/#t=" + self.token)
        # Ein reiner Hashwechsel löst keine neue Navigation aus; nach dem
        # ersten Aufruf steht die Oberfläche bereits auf der Projektliste.
        # Der Test prüft ausdrücklich den Zustand nach einem echten Neuladen.
        self.page.reload(wait_until="load")
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        self.page.get_by_role("tab", name="Einstellungen", exact=True).click()
        self.page.locator("#project-agents").wait_for()
        self.page.locator('tr[data-project-agent="vibe-agent"]').wait_for()

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

    def test_editor_model_selection_is_saved_without_manual_render(self):
        """AK Editor: Modell und Prompt werden ohne Zwischenschritt gespeichert."""
        self.open_agents()
        self.page.locator('tr[data-agent="tester"]').get_by_role(
            "button", name="Bearbeiten"
        ).click()
        self.page.get_by_label("Modell", exact=True).wait_for()

        self.page.get_by_label("Modell", exact=True).select_option("opencode/neu")
        self.page.get_by_role("button", name="Speichern", exact=True).click()

        path = self.global_agents / "tester.md"
        self.wait_until(
            lambda: "model: opencode/neu" in path.read_text(encoding="utf-8"),
            message="Die Modellauswahl wurde nicht gespeichert",
        )
        self.assertIn("description: Testagent", path.read_text(encoding="utf-8"))

        # Erst wenn die Oberfläche die Antwort des ersten Speicherns
        # verarbeitet hat, ist der Ausgangsstand der Felder aktuell.
        self.wait_until(
            lambda: self.page.get_by_role(
                "button", name="Speichern", exact=True
            ).is_enabled(),
            message="Der erste Speichervorgang ist nicht abgeschlossen",
        )

        # Editor neu öffnen: Der Ausgangsstand kommt jetzt aus der
        # gespeicherten Datei. Damit hängt der zweite Speichervorgang nicht
        # vom asynchronen Aktualisieren der Feldbasis im ersten Durchlauf ab.
        self.open_agents()
        self.page.locator('tr[data-agent="tester"]').get_by_role(
            "button", name="Bearbeiten"
        ).click()
        self.page.get_by_label("Modell", exact=True).wait_for()
        self.assertEqual(
            self.page.get_by_label("Modell", exact=True).input_value(),
            "opencode/neu",
        )

        self.page.get_by_label("Prompt", exact=True).fill("Neuer Prompt.")
        self.page.get_by_role("button", name="Speichern", exact=True).click()
        self.wait_until(
            lambda: "Neuer Prompt." in path.read_text(encoding="utf-8"),
            message="Der Prompt wurde nicht gespeichert",
        )

    def test_project_settings_default_only_vibe_and_reveal_global_agents(self):
        """AK Projekte: Standard nur Vibe, Einblenden nur systemweiter Agenten."""
        self.open_project_settings()

        vibe = self.page.locator('tr[data-project-agent="vibe-agent"]')
        self.assertEqual(vibe.get_attribute("data-configured"), "ja")
        self.assertTrue(
            self.page.locator('input[data-configure="vibe-agent"]').is_checked()
        )
        self.assertTrue(
            self.page.locator('input[data-configure="vibe-agent"]').is_disabled()
        )

        tester = self.page.locator('tr[data-project-agent="tester"]')
        self.assertFalse(
            self.row_is_visible(tester),
            "Ein nicht konfigurierter Agent ist standardmäßig sichtbar",
        )

        toggle = self.page.locator('input[data-toggle="unconfigured"]')
        self.assertEqual(
            toggle.get_attribute("aria-label"),
            "Nicht konfigurierte Agenten anzeigen",
        )
        toggle.check()
        self.wait_until(
            lambda: self.row_is_visible(
                self.page.locator('tr[data-project-agent="tester"]')
            ),
            message="Der nicht konfigurierte Agent wurde nicht eingeblendet",
        )

        row = self.page.locator('tr[data-project-agent="tester"]')
        self.assertEqual(row.get_attribute("data-configured"), "nein")
        self.assertIn(
            "Testagent", row.locator("td[data-aufgabe]").inner_text()
        )
        self.assertIn(
            "opencode/start", row.locator("td[data-wirksam]").inner_text()
        )
        model = self.page.locator('select[data-model-override="tester"]')
        self.assertEqual(model.get_attribute("aria-label"), "Modell für tester")

        # Projektlokale Agentendateien sind auch nach dem Einblenden nicht
        # Teil der Auswahl.
        self.assertEqual(self.page.locator('tr[data-project-agent="lokal"]').count(), 0)

    def test_project_selection_writes_version_two_and_keeps_vibe(self):
        """AK Projektauswahl: Version 2 mit aktiv; Vibe bleibt konfiguriert."""
        self.open_project_settings()
        self.reveal_unconfigured()

        configure = self.page.locator('input[data-configure="tester"]')
        self.assertEqual(
            configure.get_attribute("aria-label"), "Agent tester konfigurieren"
        )
        configure.check()
        self.wait_until(
            lambda: "tester" in self.agents_config().get("aktiv", []),
            message="Der ausgewählte Agent wurde nicht in 'aktiv' gespeichert",
        )
        config = self.agents_config()
        self.assertEqual(config.get("version"), 2)
        self.assertIn("tester", config.get("aktiv", []))
        self.assertIn("vibe-agent", config.get("aktiv", []))

        # Abwählen entfernt nur den globalen Agenten; der Vibe-Agent bleibt.
        self.reveal_unconfigured()
        self.page.locator('input[data-configure="tester"]').uncheck()
        self.wait_until(
            lambda: "tester" not in self.agents_config().get("aktiv", []),
            message="Der abgewählte Agent wurde nicht aus 'aktiv' entfernt",
        )
        config = self.agents_config()
        self.assertEqual(config.get("version"), 2)
        self.assertIn("vibe-agent", config.get("aktiv", []))


if __name__ == "__main__":
    unittest.main()
