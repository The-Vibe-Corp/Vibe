"""Browserabnahme für die dynamischen Schreibrechte je Projekt (F3).

Die Tests starten das echte Dashboard auf einem eigenen Port und bedienen es
mit Chromium über Playwright. Geprüft werden die Karte „Schreibrechte
(Agenten)“ im Projektdetail, das Hinzufügen und Entfernen eines Verzeichnisses,
das Zurücksetzen auf die Standardliste und das Anwenden auf vorhandene
Projektagenten.
"""
import json
import os
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
SHOT = Path(os.environ.get("VIBE_VERIFY_SCREENSHOT_DIR", REPO / "docs" / "features")) / "F3-schreibrechte.png"

AGENT = """---
description: Projektagent für die Browserprüfung
mode: subagent
permission:
  read: allow
  glob: allow
  grep: allow
  list: allow
  edit: allow
  bash: allow
  webfetch: deny
  websearch: deny
---

Du änderst ausschließlich Dateien im Projekt.
"""

READ_ONLY = """---
description: Nur lesender Projektagent
mode: subagent
permission:
  read: allow
  edit: deny
---

Nur lesen.
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


class WriteDirsBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        (cls.root / "_toolchain").mkdir()
        cls.port = free_port()
        env = os.environ.copy()
        # Ambient VIBE_* values (sandbox/container) would point vibe-web at the
        # productive installation; the test must own all runtime paths.
        for key in ISOLATED_ENV:
            env.pop(key, None)
        cls.home = cls.root / "home"
        cls.home.mkdir()
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.home),
                "VIBE_STATE": str(cls.root / "_toolchain"),
                "VIBE_RUNTIME": str(cls.log_dir),
                "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode" / "agents"),
                "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
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
        permissions = self.project / ".vibe" / "permissions.json"
        if permissions.exists():
            permissions.unlink()
        agents = self.project / ".opencode" / "agents"
        if agents.exists():
            for path in agents.iterdir():
                path.unlink()
            agents.rmdir()
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

    def toasts(self):
        return self.page.locator("#toasts .toast").all_inner_texts()

    def expand_optional(self, selector):
        """AP7-neutral: klappt einen Abschnitt auf, falls er als <details>
        umgesetzt ist. Auf der Bestandsstruktur bleibt der Aufruf ein No-op."""
        summary = self.page.locator(selector + " > summary")
        if summary.count():
            section = self.page.locator(selector).first
            section.evaluate("el => el.scrollIntoView({block: 'center'})")
            if not section.evaluate("el => !!el.open"):
                summary.click()
                self.wait_until(
                    lambda: section.evaluate("el => !!el.open"),
                    message="%s ließ sich nicht aufklappen" % selector,
                )

    def mark_card(self, selector):
        """Markiert den aktuellen DOM-Knoten einer Karte.

        Aktionen wie Hinzufügen/Entfernen/Zurücksetzen lösen serverseitig
        einen Refresh aus, der das ganze Detail-DOM asynchron ersetzt und
        optionale Abschnitte wieder einklappt. Der Marker macht diesen
        Ersatz deterministisch erkennbar, damit der Test erst auf dem
        finalen DOM weiterprüft.
        """
        self.page.locator(selector).first.evaluate(
            "el => { el.dataset.staleMarker = '1' }")

    def wait_for_card_rebuild(self, selector, message):
        self.wait_until(
            lambda: self.page.evaluate(
                "sel => { const el = document.querySelector(sel);"
                " return !!(el && !el.dataset.staleMarker) }",
                selector,
            ),
            message=message,
        )

    def open_detail(self):
        self.page.goto(self.base + "/#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        self.page.get_by_role("tab", name="Settings", exact=True).click()
        self.page.get_by_text("Write access (agents)").wait_for()
        self.expand_optional("#settings-rechte")

    def rights_card(self):
        return self.page.locator(".card", has_text="Write access (agents)")

    def stored_dirs(self):
        path = self.project / ".vibe" / "permissions.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))["write_dirs"]
        except FileNotFoundError:
            # The server may rewrite the file between exists() and read().
            return None

    def write_agent(self):
        folder = self.project / ".opencode" / "agents"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "proj-agent.md"
        path.write_text(AGENT, encoding="utf-8")
        return path

    def test_card_lists_defaults_and_persists_add_and_remove(self):
        self.open_detail()
        card = self.rights_card()
        project_path = os.path.realpath(self.project)

        card.get_by_text("/tmp/opencode", exact=True).wait_for()
        card.get_by_text(project_path, exact=True).wait_for()
        self.assertIn("Default list active.", card.inner_text())
        self.assertRegex(
            card.inner_text(),
            r"die Liste ist keine Sandbox|the list is not a sandbox")

        extra = "/tmp/opencode/f3-ui"
        self.mark_card("#settings-rechte")
        card.get_by_placeholder("/absoluter/pfad").fill(extra)
        card.get_by_role("button", name="Add").click()
        self.wait_until(
            lambda: self.stored_dirs() is not None
            and os.path.realpath(extra) in self.stored_dirs(),
            message="Hinzugefügtes Verzeichnis wurde nicht gespeichert",
        )
        self.wait_for_card_rebuild(
            "#settings-rechte",
            "Die Schreibrechte-Karte wurde nach dem Hinzufügen nicht neu aufgebaut",
        )
        self.expand_optional("#settings-rechte")
        card.get_by_text(os.path.realpath(extra), exact=True).wait_for()
        self.assertIn("Custom list active.", card.inner_text())

        row = card.locator(".bar", has_text=os.path.realpath(extra))
        self.mark_card("#settings-rechte")
        row.get_by_role("button", name="Remove").click()
        self.wait_until(
            lambda: self.stored_dirs() is not None
            and os.path.realpath(extra) not in self.stored_dirs(),
            message="Entferntes Verzeichnis steht noch in der Datei",
        )
        self.assertEqual(
            self.stored_dirs(), ["/tmp/opencode", project_path]
        )

        self.wait_for_card_rebuild(
            "#settings-rechte",
            "Die Schreibrechte-Karte wurde nach dem Entfernen nicht neu aufgebaut",
        )
        self.expand_optional("#settings-rechte")
        self.rights_card().get_by_role(
            "button", name="Restore defaults").click()
        self.rights_card().locator(".confirm").first.wait_for(
            state="visible", timeout=10000)
        self.mark_card("#settings-rechte")
        self.rights_card().locator(".confirm").get_by_role(
            "button", name="Yes, reset").click()
        self.wait_until(
            lambda: self.stored_dirs() is None,
            message="Zurücksetzen entfernte die eigene Liste nicht",
        )
        # Der Erfolg baut die Karte asynchron neu (und klappt den Abschnitt
        # wieder ein); erst den neuen DOM-Knoten abwarten, dann aufklappen
        # und den Text prüfen.
        self.wait_for_card_rebuild(
            "#settings-rechte",
            "Die Schreibrechte-Karte wurde nach dem Zurücksetzen nicht neu aufgebaut",
        )
        self.expand_optional("#settings-rechte")
        card.get_by_text("Default list active.").wait_for()

    def test_agent_editor_is_global_and_uses_open_write_rights(self):
        """AP03: Der Editor legt ausschließlich systemweite Agenten an."""
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.get_by_role("button", name="Agents & Models").click()
        self.page.get_by_role("button", name="New agent").click()

        form = self.page.locator(".card", has_text="File (frontmatter + prompt)")
        geltung = form.get_by_label("Scope", exact=True)
        geltung.wait_for()
        self.assertTrue(geltung.is_disabled())
        self.assertEqual(geltung.input_value(), "global")
        self.assertEqual(
            geltung.evaluate("el => [...el.options].map(o => o.value)"),
            ["global"],
        )

        form.get_by_label("Permissions", exact=True).select_option("voll")
        form.get_by_role("button", name="Generate file from inputs").click()

        raw = form.locator("textarea.raw")
        self.wait_until(
            lambda: "  edit: allow" in raw.input_value(),
            message="Globale Vorlage wurde eingeschränkt",
        )
        text = raw.input_value()
        self.assertNotIn('"*": deny', text)
        self.assertNotIn(
            f'"{os.path.realpath(self.project)}/**": allow', text
        )
        form.get_by_text(
            "Global: full write access without directory limit."
        ).wait_for()

    def test_apply_keeps_read_only_agent_unchanged(self):
        folder = self.project / ".opencode" / "agents"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "nur-lesen.md"
        path.write_text(READ_ONLY, encoding="utf-8")
        self.open_detail()

        self.rights_card().get_by_role(
            "button", name="Apply to project agents"
        ).click()

        self.wait_until(
            lambda: any("Nichts geändert" in m for m in self.toasts()),
            message="Keine Rückmeldung für unveränderte Agenten",
        )
        self.assertEqual(path.read_text(encoding="utf-8"), READ_ONLY)

    def test_apply_writes_edit_block_and_screenshot(self):
        agent = self.write_agent()
        self.open_detail()
        card = self.rights_card()
        previous_card = card.element_handle()

        card.get_by_role("button", name="Apply to project agents").click()
        self.wait_until(
            lambda: '    "*": deny' in agent.read_text(encoding="utf-8"),
            message="Schreibrechte wurden nicht auf den Projektagenten angewendet",
        )

        text = agent.read_text(encoding="utf-8")
        self.assertNotIn("  edit: allow", text)
        self.assertIn(f'    "{os.path.realpath(self.project)}/**": allow', text)
        self.assertIn('    "/tmp/opencode/**": allow', text)
        self.assertIn("  bash: allow", text)
        self.assertIn("Du änderst ausschließlich Dateien im Projekt.", text)

        # Nach dem Anwenden lädt detail(name) das Projektdetail neu. Erst wenn die
        # alte Karte aus dem DOM entfernt und die neue aufgebaut ist, ist der
        # Screenshot stabil; sonst kann Playwright ein abgelöstes Element treffen.
        self.page.wait_for_function(
            "element => !element.isConnected", arg=previous_card
        )
        shot_card = self.rights_card()
        self.expand_optional("#settings-rechte")
        shot_card.get_by_text("Default list active.").wait_for()

        SHOT.parent.mkdir(parents=True, exist_ok=True)
        shot_card.screenshot(path=str(SHOT))
        self.assertTrue(SHOT.exists() and SHOT.stat().st_size > 0)


if __name__ == "__main__":
    unittest.main()
