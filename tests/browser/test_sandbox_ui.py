"""Browserabnahme für die Sandbox-Karte im Projektdetail (F7).

Das echte Dashboard läuft auf einem eigenen Port und wird mit Chromium über
Playwright bedient. Geprüft werden Zustandsanzeige, Ein- und Ausschalten,
Build-Werkzeuge, die Prüfung sowie der Screenshot der Karte.
"""
import os
import shutil
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
SHOT = Path(os.environ.get("VIBE_VERIFY_SCREENSHOT_DIR", REPO / "docs" / "features")) / "F7-sandbox.png"

# Ambient VIBE_* values would point vibe-web at the productive
# installation; the test must own all runtime paths.
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
    "VIBE_HARNESS",
)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def read_env_file(path):
    data = {}
    if not Path(path).exists():
        return data
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


class SandboxBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert shutil.which("bwrap") is not None, "bubblewrap (bwrap) fehlt"
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        cls.toolchain = cls.root / "_toolchain"
        cls.toolchain.mkdir()
        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.port = free_port()
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.home),
                "VIBE_STATE": str(cls.toolchain),
                "VIBE_INSTALL": str(cls.toolchain),
                "VIBE_RUNTIME": str(cls.log_dir),
                "VIBE_AGENTS_DIR":
                    str(cls.home / ".config" / "opencode" / "agents"),
                "VIBE_CONFIG_FILE":
                    str(cls.home / ".config" / "vibe" / "config.json"),
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
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        self.page = self.browser.new_page(viewport={"width": 1400, "height": 1000})

    def tearDown(self):
        self.page.close()

    def wait_until(self, predicate, timeout=20, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def expand_optional(self, selector):
        """AP7-neutral: klappt einen Abschnitt auf, falls er als <details>
        umgesetzt ist. Auf der Bestandsstruktur (alles sichtbar) bleibt der
        Aufruf ein No-op."""
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

        Aktionen wie Einschalten/Speichern/Ausschalten lösen serverseitig
        einen Refresh aus, der das ganze Detail-DOM asynchron ersetzt und
        optionale Abschnitte wieder einklappt. Der Marker macht diesen
        Ersatz deterministisch erkennbar, damit der Test erst auf dem
        finalen DOM weiterprüft, statt gegen den frisch ersetzten Knoten
        zu klicken.
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
        self.page.get_by_role("tab", name="Einstellungen", exact=True).click()
        self.page.locator("#sandbox").wait_for()
        self.expand_optional("#sandbox")

    def sandbox_card(self):
        return self.page.locator("#sandbox")

    def env_values(self):
        return read_env_file(self.project / ".vibe" / "project.env")

    def toasts(self):
        return self.page.locator("#toasts .toast").all_inner_texts()

    def test_card_switches_on_sets_tools_checks_and_switches_off(self):
        self.open_detail()
        card = self.sandbox_card()
        # AP7: Der Karten-/summary-Titel darf frei gewählt sein („Sandbox
        # (optional)“ statt „Shell und Build-Werkzeuge“); geprüft wird der
        # sichtbare Zustand nach dem Aufklappen.
        self.expand_optional("#sandbox")
        # Runde 2 (Info-Befund): der Aufklapp-Titel des Sandbox-Abschnitts
        # ist Teil des fachlichen UI-Kontrakts („Sandbox (optional)“).
        self.assertIn(
            "Sandbox (optional)",
            self.sandbox_card().locator("> summary").inner_text(),
            "Der Sandbox-Abschnitt trägt den erwarteten Aufklapp-Titel nicht",
        )
        self.assertIn("aus", card.inner_text())
        self.assertIn(
            "Ohne Sandbox bleiben Shell-Befehle (bash) außerhalb der Liste möglich.",
            card.inner_text(),
        )

        self.mark_card("#sandbox")
        card.get_by_role("button", name="Sandbox einschalten").click()
        self.wait_until(
            lambda: self.env_values().get("SANDBOX") == "on",
            message="Sandbox wurde nicht eingeschaltet",
        )
        self.wait_for_card_rebuild(
            "#sandbox",
            "Die Sandbox-Karte wurde nach dem Einschalten nicht neu aufgebaut",
        )
        self.wait_until(
            lambda: self.sandbox_card().get_by_text("bereit", exact=True).count() == 1,
            message="Karte zeigt nach dem Einschalten nicht bereit",
        )
        self.assertEqual(self.env_values().get("SANDBOX_TOOLS"), "git python3")
        # Der Kartenaufbau nach dem Einschalten klappt optionale Abschnitte
        # wieder ein; für die weiteren Prüfungen erneut aufklappen (auch die
        # Schreibrechte-Karte gehört zum AP7-Zustand „Sandbox aktiv“-Text).
        self.expand_optional("#sandbox")
        self.expand_optional("#settings-rechte")
        card = self.sandbox_card()
        self.assertEqual(
            card.get_by_label("Build-Werkzeuge").input_value(), "git python3"
        )
        self.assertIn("Sandbox aktiv", self.page.locator("body").inner_text())
        self.assertIn(
            "Schreibwerkzeug (edit) und Shell-Befehle (bash) können nur",
            self.page.locator("body").inner_text(),
        )
        self.assertIn(
            "Die Sandbox-Konfiguration (.vibe/project.env, .vibe/permissions.json) "
            "ist im Lauf schreibgeschützt.",
            card.inner_text(),
        )

        card.get_by_label("Build-Werkzeuge").fill("git, python3")
        self.mark_card("#sandbox")
        card.get_by_role("button", name="Werkzeuge speichern").click()
        self.wait_until(
            lambda: self.env_values().get("SANDBOX_TOOLS") == "git python3",
            message="Werkzeugliste wurde nicht gespeichert",
        )

        # Der Speichern-Refresh ersetzt das Detail-DOM asynchron und klappt
        # den Abschnitt wieder ein. Erst den neuen DOM-Knoten abwarten, dann
        # aufklappen — sonst rennt der Prüfen-Klick in den DOM-Ersatz.
        self.wait_for_card_rebuild(
            "#sandbox",
            "Die Sandbox-Karte wurde nach dem Werkzeugspeichern nicht neu aufgebaut",
        )
        card = self.sandbox_card()
        self.expand_optional("#sandbox")
        card = self.sandbox_card()
        card.get_by_role("button", name="Prüfen").click()
        self.wait_until(
            lambda: any("Sandbox bereit" in m for m in self.toasts()),
            message="Prüfung meldete keinen bereiten Zustand: "
            + repr(self.toasts()),
        )
        self.assertIn("git", " ".join(self.toasts()))

        SHOT.parent.mkdir(parents=True, exist_ok=True)
        self.expand_optional("#sandbox")
        self.sandbox_card().screenshot(path=str(SHOT))
        self.assertTrue(SHOT.exists() and SHOT.stat().st_size > 0)

        self.mark_card("#sandbox")
        self.sandbox_card().get_by_role("button", name="Sandbox ausschalten").click()
        self.wait_until(
            lambda: self.env_values().get("SANDBOX") == "off",
            message="Sandbox wurde nicht ausgeschaltet",
        )
        self.wait_for_card_rebuild(
            "#sandbox",
            "Die Sandbox-Karte wurde nach dem Ausschalten nicht neu aufgebaut",
        )
        self.expand_optional("#sandbox")
        self.wait_until(
            lambda: self.sandbox_card().get_by_text("aus", exact=True).count() == 1,
            message="Karte zeigt nach dem Ausschalten nicht aus",
        )


if __name__ == "__main__":
    unittest.main()
