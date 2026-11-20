"""Browserabnahme F31: AGENTS.md in der Assistent-Ansicht ansehen und bearbeiten.

Die Tests starten das echte Dashboard (bin/vibe-web.py) auf einem eigenen Port
in einem isolierten Arbeitsbereich mit eigenen Vorlagen und bedienen es mit
Chromium über Playwright. Kein Agent, kein Modell, keine produktiven
HOME-/VIBE-Konfigurationen.

Geprüft wird die in die Assistent-Ansicht (guideCard) integrierte Karte
„AGENTS.md — Regeln für Agenten“:

* Die Karte zeigt den aktuellen Inhalt von AGENTS.md (AK1).
* Der verwaltete Block ist als von vibe verwaltet gekennzeichnet und die Karte
  erklärt, dass dieser Teil bei jedem Agentenlauf aktualisiert und in der
  Bearbeitung geschützt ist (AK2).
* Die freien Teile sind über Textareas bearbeitbar; Speichern schreibt die
  Datei, der Block bleibt byte-identisch (AK3).
* Fehlt AGENTS.md, legt der Button „Aus Vorlage anlegen“ sie aus der
  Typ-Vorlage an (AK6).
* Eine unbekannte POST-Aktion an /api/agents_file wird abgewiesen (AK8).
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

# Installierte Entwicklerabhängigkeit: Chromium nur lesend aus dem
# Nutzer-Cache (Muster tests/browser/test_ap11_priority_ui.py).
_BROWSERS = Path.home() / ".cache" / "ms-playwright"
if _BROWSERS.is_dir():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_BROWSERS))

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"
SHOT = Path(
    os.environ.get("VIBE_VERIFY_SCREENSHOT_DIR", REPO / "docs" / "features")
) / "F31-agents-file.png"


def general_rules():
    """Der verwaltete Block, wie bin/vibe ihn bei jedem Agentenlauf setzt."""
    text = (REPO / "bin" / "vibe").read_text(encoding="utf-8")
    match = re.search(r'GENERAL_RULES = """(.*?)"""', text, re.DOTALL)
    if not match:
        raise RuntimeError("GENERAL_RULES wurde in bin/vibe nicht gefunden")
    return match.group(1)


BLOCK = general_rules()
EXPLANATION = re.compile(
    r"auf den aktuellen Stand gebracht und ist in der Bearbeitung geschützt"
    r"|it brings the block up to date and protects it from editing")
BEFORE = "Kopfteil-F31\n"
AFTER = "\nFußteil-F31\n"

PROJECT_ENV = "TYPE=generic\nAGENT=test-agent\nTESTER=test-agent\nREVIEWER=code-reviewer\n"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def git(project, *argv):
    return subprocess.run(
        ["git", "-C", str(project), *argv], capture_output=True, text=True, check=False
    )


class AgentsFileUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        for name in ("test-agent", "code-reviewer"):
            (cls.agents / (name + ".md")).write_text(
                "---\ndescription: Testagent\nmode: subagent\n---\n", encoding="utf-8"
            )
        cls.project = cls.root / "proj"
        cls.project.mkdir(parents=True)
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(PROJECT_ENV, encoding="utf-8")
        subprocess.run(
            ["git", "init", "-q", "-b", "main", str(cls.project)], check=True,
            capture_output=True,
        )
        git(cls.project, "config", "user.name", "Test")
        git(cls.project, "config", "user.email", "test@example.invalid")
        git(cls.project, "config", "commit.gpgsign", "false")

        toolchain = cls.root / "_toolchain"
        toolchain.mkdir()
        shutil.copytree(REPO / "templates", toolchain / "templates")
        cls.runtime = cls.root / "_logs"
        cls.runtime.mkdir()
        cls.port = free_port()

        # Ambient VIBE_*-Werte (Sandbox/Container) würden vibe-web auf die
        # produktive Installation zeigen lassen; der Test besitzt alle
        # Laufzeitpfade selbst.
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_"):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "VIBE_INSTALL": str(toolchain),
                "VIBE_RUNTIME": str(cls.runtime),
                "VIBE_STATE": str(toolchain),
                "VIBE_AGENTS_DIR": str(cls.agents),
                "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
                "VIBE_STORAGE_LOCK_DIR": str(cls.home / "locks"),
                "HOME": str(cls.home),
                "XDG_CONFIG_HOME": str(cls.home / ".config"),
            }
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        token_file = cls.runtime / "web.token"
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
        cls.base = "http://127.0.0.1:%d" % cls.port
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
        # Frische AGENTS.md je Test: keine Querschieße zwischen den Fällen.
        path = self.project / "AGENTS.md"
        if path.exists():
            path.unlink()
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1000})

    def tearDown(self):
        self.page.close()

    def wait_until(self, predicate, timeout=15, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def open_guide(self):
        self.page.goto(self.base + "/classic#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        self.page.get_by_role("tab", name="Assistant", exact=True).click()
        self.page.locator("#guide").wait_for()

    def agents_card(self):
        """Die AGENTS.md-Karte: innerster Karten-Container mit Speichern-Button.

        Die Karte ist ein Bestandteil der Assistent-Ansicht; sie trägt den
        Titel „AGENTS.md — Regeln für Agenten“ und enthält entweder den
        Speichern-Button oder den Button „Aus Vorlage anlegen“.
        """
        guide = self.page.locator("#guide")
        # has=-Filter verankern den eingebetteten Selektor am Kandidaten-Div,
        # nicht am Vorfahren. Ein an #guide verankerter get_by_role-Locator
        # trafe nie (der Karten-Div liegt INNERHALB von #guide und kann keinen
        # weiteren #guide-Nachfahren enthalten). Deshalb hier page-relativ.
        buttons = self.page.get_by_role(
            "button", name=re.compile(r"^(Speichern|Save)$|^(Aus Vorlage anlegen|Create from template)$")
        )
        return (
            guide.locator("div")
            .filter(has_text=re.compile(r"Regeln für Agenten|rules for agents", re.I))
            .filter(has=buttons)
            .last
        )

    def agents_path(self):
        return self.project / "AGENTS.md"

    def write_agents(self):
        self.agents_path().write_text(BEFORE + BLOCK + AFTER, encoding="utf-8")

    # ---------- AK1 + AK2: Ansicht und Kennzeichnung ----------

    def test_card_shows_content_managed_block_and_explanation(self):
        self.write_agents()
        self.open_guide()
        card = self.agents_card()
        card.wait_for()
        text = card.inner_text()
        self.assertIn("AGENTS.md", text)
        self.assertRegex(text, r"Regeln für Agenten|rules for agents")
        # AK2: Erklärung zum geschützten, bei jedem Lauf aktualisierten Block.
        self.assertRegex(text, EXPLANATION)
        # AK1: Die Karte zeigt die freien Teile und den verwalteten Inhalt.
        boxes = card.get_by_role("textbox")
        self.assertEqual(boxes.count(), 2, "vor/after-Textareas fehlen in der Karte")
        self.assertIn("Kopfteil-F31", boxes.nth(0).input_value())
        self.assertIn("Fußteil-F31", boxes.nth(1).input_value())
        self.assertIn("Ordnung im Git halten", text, "verwalteter Block wird nicht angezeigt")
        SHOT.parent.mkdir(parents=True, exist_ok=True)
        card.screenshot(path=str(SHOT))
        self.assertTrue(SHOT.exists() and SHOT.stat().st_size > 0)

    # ---------- AK3: Bearbeiten und Speichern ----------

    def test_editing_free_part_saves_file_and_keeps_block_identical(self):
        self.write_agents()
        self.open_guide()
        card = self.agents_card()
        card.wait_for()
        boxes = card.get_by_role("textbox")
        # Der freie Teil nach dem Block wird geändert, der Teil davor bleibt.
        target = None
        for index in range(boxes.count()):
            if "Fußteil-F31" in boxes.nth(index).input_value():
                target = boxes.nth(index)
                break
        self.assertIsNotNone(target, "after-Textarea nicht gefunden")
        target.fill("Fußteil-F31 geändert\n")
        card.get_by_role("button", name="Save").click()
        self.wait_until(
            lambda: "Fußteil-F31 geändert" in self.agents_path().read_text(encoding="utf-8"),
            message="Speichern hat AGENTS.md nicht aktualisiert",
        )
        text = self.agents_path().read_text(encoding="utf-8")
        self.assertEqual(text, BEFORE + BLOCK + "Fußteil-F31 geändert\n")

    # ---------- AK6: Aus Vorlage anlegen ----------

    def test_missing_file_can_be_created_from_template(self):
        self.assertFalse(self.agents_path().exists())
        self.open_guide()
        card = self.agents_card()
        card.wait_for()
        card.get_by_role("button", name="Create from template").click()
        self.wait_until(
            lambda: self.agents_path().exists(),
            message="AGENTS.md wurde nicht aus der Vorlage angelegt",
        )
        text = self.agents_path().read_text(encoding="utf-8")
        self.assertIn("# Projekt: proj", text)
        template = (REPO / "templates" / "generic" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(text, template.replace("{{NAME}}", "proj"))
        # Die Karte zeigt danach den Inhalt.
        card = self.agents_card()
        self.wait_until(
            lambda: any(
                "# Projekt: proj" in card.get_by_role("textbox").nth(i).input_value()
                for i in range(max(card.get_by_role("textbox").count(), 1))
            ),
            message="Karte zeigt den neu angelegten Inhalt nicht",
        )

    # ---------- AK8: Web-API ----------

    def test_get_view_and_unknown_post_action_are_rejected(self):
        self.write_agents()
        # GET liefert die Ansicht (AK8, Voraussetzung für die Karte).
        url = self.base + "/api/agents_file?name=proj"
        request = urllib.request.Request(url, headers={"X-Token": self.token})
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual(response.status, 200)
            view = json.loads(response.read().decode("utf-8"))
        self.assertTrue(view["exists"])
        self.assertEqual(view["before"], BEFORE)
        self.assertEqual(view["after"], AFTER)

        # Unbekannte Aktion wird abgewiesen und ändert die Datei nicht.
        body = json.dumps({"name": "proj", "action": "f31-fremd"}).encode("utf-8")
        request = urllib.request.Request(
            self.base + "/api/agents_file", data=body, method="POST",
            headers={"X-Token": self.token, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                status = response.status
        except urllib.error.HTTPError as error:
            status = error.code
        self.assertTrue(400 <= status < 500, "unbekannte Aktion wurde nicht abgewiesen")
        self.assertEqual(
            self.agents_path().read_text(encoding="utf-8"), BEFORE + BLOCK + AFTER
        )


if __name__ == "__main__":
    unittest.main()
