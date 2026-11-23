"""Browserabnahme für den Prüfbutton ``Prüfung package`` (F31).

Die Projektdetail-Ansicht bietet neben ``Prüfung quick`` und ``Prüfung full``
einen dritten, schnellen Mittelweg. AP7-Korbat (T-V16) macht ``verify.sh`` zur
einzigen Prüfschnittstelle: Der Paketmodus führt ``VERIFY_QUICK`` aus;
``VERIFY_PACKAGE`` und ``VERIFY_FULL`` sind keine Befehlsvariablen der Engine
mehr. Der Test startet das echte Dashboard mit einem Fixture-Projekt, dessen
``VERIFY_QUICK`` einen eindeutigen Marker ausgibt, klickt den Button und
erwartet den Marker im Ausgabebereich (verify-Stream). Der Screenshot
``F31-paketpruefung.png`` entsteht in diesem Test und zeigt die tatsächliche
Oberfläche.
"""
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
SHOTS = Path(os.environ.get("VIBE_VERIFY_SCREENSHOT_DIR", REPO / "docs" / "features"))
SHOT = SHOTS / "F31-paketpruefung.png"

PACKAGE_MARKER = "paket-pruefung-marker"

# Ambient VIBE_* values would point vibe-web at the productive installation;
# the test must own all runtime paths.
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

FEEDBACK = "# FEEDBACK — Test\n\n- [ ] F1 Erster Punkt\n"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class VerifyPackageUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        # Dokumentierte Nutzer-Verdrahtung (AP7-Design, T-V20): Das Dashboard
        # führt VERIFY_PACKAGE unverändert aus. Der autoritative Wert ruft
        # deshalb den verify.sh-Wrapper auf; die Engine führt dann VERIFY_QUICK
        # aus (einzige Prüfschnittstelle).
        wrapper = "bash %s package --project %s" % (
            REPO / "scripts" / "verify.sh", cls.project)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n"
            f'VERIFY_QUICK="echo {PACKAGE_MARKER}"\n'
            'VERIFY_FULL="echo full-pruefung-marker"\n'
            f'VERIFY_PACKAGE="{wrapper}"\n',
            encoding="utf-8",
        )
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(parents=True)
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
                "HOME": str(cls.root / "home"),
                "VIBE_RUNTIME": str(cls.log_dir),
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
        (self.project / "FEEDBACK.md").write_text(FEEDBACK, encoding="utf-8")
        (self.log_dir / "proj.log").write_text("Startzeile\n", encoding="utf-8")
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

    def open_detail(self):
        self.page.goto(self.base + "/classic#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for()
        row.click()
        self.page.get_by_role("tab", name="Work", exact=True).wait_for()

    def test_package_button_runs_the_package_check_and_streams_its_output(self):
        self.open_detail()
        arbeit = self.page.locator('[role="tabpanel"][data-panel="arbeit"]')

        # Alle drei Prüfstufen bleiben nebeneinander erreichbar.
        for label in ("Check quick", "Check package", "Check full"):
            self.assertTrue(
                arbeit.get_by_role("button", name=label).is_visible(),
                f"Button {label!r} fehlt in der Projektansicht",
            )

        arbeit.get_by_role("button", name="Check package").click()
        self.wait_until(
            lambda: self.page.locator('[role="tab"][aria-selected="true"]')
            .inner_text()
            .strip()
            == "Output",
            message="Prüfung package wechselte nicht zur Ausgabe",
        )
        self.assertTrue(
            self.page.locator('[role="tabpanel"][data-panel="ausgabe"]').is_visible()
        )
        self.wait_until(
            lambda: PACKAGE_MARKER in self.page.locator("#log").inner_text(),
            message="Ausgabe von VERIFY_QUICK erschien nicht im Ausgabebereich",
        )
        log = self.page.locator("#log").inner_text()
        self.assertIn("verify.sh", log,
                      "Der Paketknopf lief nicht über den verify.sh-Wrapper")
        self.assertNotIn("full-pruefung-marker", log)

        SHOTS.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(SHOT))
        self.assertTrue(SHOT.exists() and SHOT.stat().st_size > 0)


if __name__ == "__main__":
    unittest.main()
