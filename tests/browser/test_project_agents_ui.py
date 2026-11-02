"""Browserabnahme für die Agentenverwaltung und die Agentenauswahl je Projekt (F17).

Die Tests starten das echte Dashboard auf einem eigenen Port und bedienen es
mit Chromium über Playwright. Geprüft werden:

* Die Modellauswahl im strukturierten Editor wird auch dann gespeichert, wenn
  der Nutzer nicht zusätzlich „In Rohtext übernehmen“ anklickt.
* Die Projekteinstellungen zeigen die Agenten des Projekts mit Auswahl und
  wirksamem Modell.
* Ein abgewählter Agent und eine Modellüberschreibung werden in
  ``<Projekt>/.vibe/agents.json`` gespeichert und nach dem Neuladen angezeigt.

Der Screenshot ``F17-agenten.png`` entsteht in diesem Test und zeigt die
tatsächliche Oberfläche.
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
SHOT = SHOTS / "F17-agenten.png"

FAKE_OPENCODE = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  printf 'opencode v2.1.4\\n'
  exit 0
fi
if [ "$1" = "models" ]; then
  printf 'opencode/start\\nopencode/neu\\nopencode/anderes\\n'
  exit 0
fi
echo 'unerwarteter Aufruf' >&2
exit 2
"""

AGENT = """---
description: Testagent
mode: subagent
model: opencode/start
temperature: 0.1
---
Test-Prompt.
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
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        (cls.root / "_toolchain").mkdir()
        fake_bin = cls.root / "fakebin"
        fake_bin.mkdir()
        fake = fake_bin / "opencode"
        fake.write_text(FAKE_OPENCODE, encoding="utf-8")
        fake.chmod(0o755)
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
        (self.global_agents / "tester.md").write_text(AGENT, encoding="utf-8")
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
        self.page.get_by_role("button", name="Neuer Agent").wait_for()
        self.page.get_by_text("Testagent").wait_for()

    def open_project_settings(self):
        self.page.goto(self.base + "/#t=" + self.token)
        # Ein reiner Hashwechsel löst keine neue Navigation aus; nach dem
        # ersten Aufruf steht die Oberfläche bereits auf der Projektliste.
        # Der Test will aber ausdrücklich den Zustand nach einem echten
        # Neuladen prüfen. Das Token bleibt in der Sitzung erhalten.
        self.page.reload(wait_until="load")
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        self.page.get_by_role("tab", name="Einstellungen", exact=True).click()
        self.page.locator("#project-agents").wait_for()
        self.page.locator('tr[data-project-agent="tester"]').wait_for()

    def agents_config(self):
        path = self.project / ".vibe" / "agents.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def test_model_selection_is_saved_without_manual_render(self):
        self.open_agents()
        self.page.locator('tr[data-agent="tester"][data-scope="global"]').get_by_role(
            "button", name="Bearbeiten"
        ).click()
        self.page.get_by_role("button", name="In Rohtext übernehmen").wait_for()

        # Nur die strukturierte Modellauswahl ändern und direkt speichern.
        # Ohne die F17-Korrektur bleibt diese Änderung im Rohtext unsichtbar
        # und geht beim Speichern verloren.
        self.page.get_by_label("Modell", exact=True).select_option("opencode/neu")
        self.page.get_by_role("button", name="Speichern", exact=True).click()

        path = self.global_agents / "tester.md"
        self.wait_until(
            lambda: "model: opencode/neu" in path.read_text(encoding="utf-8"),
            message="Die Modellauswahl wurde ohne „In Rohtext übernehmen“ nicht gespeichert",
        )
        saved = path.read_text(encoding="utf-8")
        self.assertIn("description: Testagent", saved)

        # Erst wenn die Oberfläche die Antwort des ersten Speicherns
        # verarbeitet hat, ist der Ausgangsstand der Felder aktuell. Sonst
        # könnte die nachlaufende Antwort die folgende Eingabe überschreiben.
        raw = self.page.get_by_label("Datei (Frontmatter + Prompt)")
        self.wait_until(
            lambda: "model: opencode/neu" in raw.input_value(),
            message="Die Oberfläche hat das gespeicherte Modell nicht übernommen",
        )

        # Auch der Prompt ist ein strukturiertes Feld und wird ohne den
        # Zwischenschritt „In Rohtext übernehmen“ gespeichert.
        self.page.get_by_label("Prompt", exact=True).fill("Neuer Prompt.")
        self.page.get_by_role("button", name="Speichern", exact=True).click()
        self.wait_until(
            lambda: "Neuer Prompt." in path.read_text(encoding="utf-8"),
            message="Der Prompt wurde ohne „In Rohtext übernehmen“ nicht gespeichert",
        )

    def test_project_selection_and_model_override_are_saved_and_shown(self):
        self.open_project_settings()
        row = self.page.locator('tr[data-project-agent="tester"]')
        self.assertEqual(row.get_attribute("data-selected"), "ja")
        self.assertIn("opencode/start", row.inner_text())
        # Ein fehlender Fehlerhinweis darf nicht als Text „null“ erscheinen.
        self.assertNotIn("null", self.page.locator("#project-agents").inner_text())
        self.assertIsNone(self.agents_config())

        checkbox = self.page.get_by_label("Agent tester auswählen")
        checkbox.uncheck()
        self.wait_until(
            lambda: (self.agents_config() or {}).get("deaktiviert") == ["tester"],
            message="Der abgewählte Agent wurde nicht gespeichert",
        )
        self.wait_until(
            lambda: self.page.locator('tr[data-project-agent="tester"]').get_attribute(
                "data-selected"
            )
            == "nein",
            message="Die Oberfläche zeigt den abgewählten Agenten nicht",
        )

        self.page.get_by_label("Modell für tester").select_option("opencode/neu")
        self.wait_until(
            lambda: (self.agents_config() or {}).get("modelle")
            == {"tester": "opencode/neu"},
            message="Die Modellüberschreibung wurde nicht gespeichert",
        )
        self.wait_until(
            lambda: "opencode/neu"
            in self.page.locator('tr[data-project-agent="tester"]').inner_text(),
            message="Das wirksame Modell zeigt die Überschreibung nicht",
        )

        SHOTS.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(SHOT))
        self.assertTrue(SHOT.exists() and SHOT.stat().st_size > 0)

        # Nach dem Neuladen bleiben Auswahl und Überschreibung erhalten.
        self.open_project_settings()
        row = self.page.locator('tr[data-project-agent="tester"]')
        self.wait_until(
            lambda: row.get_attribute("data-selected") == "nein",
            message="Die Auswahl ging beim Neuladen verloren",
        )
        self.assertEqual(
            self.page.get_by_label("Modell für tester").input_value(), "opencode/neu"
        )


if __name__ == "__main__":
    unittest.main()
