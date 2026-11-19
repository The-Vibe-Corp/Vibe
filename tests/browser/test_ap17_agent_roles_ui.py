"""AP17 — Browserabnahme der neuen Agentenrollen.

Der Test startet das echte Dashboard auf einem eigenen Port und bedient es mit
Chromium über Playwright. Geprüft wird ausschließlich die in AP17 vereinbarte
Oberfläche:

* das Rollen-Auswahlfeld pro globalem Agenten bietet neben coder, reviewer und
  vibe auch tester, analyst, sonstiges und content-creator an,
* die Auswahl ``tester`` wird über die echte Web-API in ``profiles.json``
  gespeichert und ist nach dem Neuladen der Agentenliste weiterhin sichtbar.

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

NEW_ROLES = ("tester", "analyst", "sonstiges", "content-creator")
EXISTING_ROLES = ("coder", "reviewer", "vibe")

FAKE_OPENCODE = """#!/usr/bin/env bash
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
permission:
  read: allow
  edit: deny
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
---

Hilf beim Testen.
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
    "AGENT",
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
        self.page.goto(self.base + "/#t=" + self.token)
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


if __name__ == "__main__":
    unittest.main()
