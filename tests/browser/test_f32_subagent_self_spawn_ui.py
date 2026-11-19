"""Browserabnahme F32 — Subagenten-Parallelisierung in der Agentenverwaltung.

Die Tests starten das echte Dashboard auf einem eigenen Port und bedienen es
mit Chromium über Playwright. Geprüft wird ausschließlich die in F32
vereinbarte Oberfläche:

* Bei „Subagenten-Rechte: ausgewählt“ gibt es für einen gewöhnlichen Agenten
  eine eigene Checkbox „Subagenten des eigenen Typs erlauben
  (Parallelisierung)“. Sie ist standardmäßig ungehakt, lässt sich per Maus und
  Tastatur umschalten, wird gespeichert und nach dem Neuladen wieder angezeigt.
* Der Vibe-Agent erhält statt der Checkbox einen Hinweis, dass er keine
  Subagenten seines eigenen Typs aufruft.
* Bei Modus ``primary`` ist die Checkbox ausgeblendet und ein Hinweis nennt
  den erforderlichen Modus ``subagent``/``all``.
* Das Formular für einen neuen Agenten bietet die Checkbox ungehakt an.
* Bei „keine“ und „alle“ gibt es keine Eigen-Checkbox.

Vertrag für die Umsetzung (Selektoren, damit die Tests die Fachlichkeit und
nicht die Syntax prüfen): Die Checkbox ist ein ``input[type=checkbox]`` mit
dem zugänglichen Namen „Subagenten des eigenen Typs erlauben“ (Label umschließt
die Checkbox oder ``aria-label``). Hinweise stehen im Subagenten-Bereich
``[data-subagents]``. Damit sind die Tests unabhängig von der konkreten
DOM-Reihenfolge, verlangen aber die sichtbare, bedienbare Checkbox.

Es findet kein Modellaufruf und kein Netzzugriff außerhalb von Loopback statt.
``opencode`` wird durch ein Ersatzprogramm beantwortet.
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

OWN_LABEL = "Subagenten des eigenen Typs erlauben"

FAKE_OPENCODE = """#!/usr/bin/env bash
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

ISOLATED_ENV = (
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
        self.page.goto(self.base + "/#t=" + self.token)
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


if __name__ == "__main__":
    unittest.main()
