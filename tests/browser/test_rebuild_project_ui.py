"""Browserabnahme für den Projekttyp ``rebuild`` (F14).

Der Test startet das echte Dashboard, prüft die dynamische Typenliste und legt
über die Oberfläche ein Rebuild-Projekt an. Damit ist belegt, dass der neue Typ
ohne UI-Codeänderung auswählbar ist und das vollständige Profil ankommt.
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


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def init_git_repo(path):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "init",
        ],
        cwd=path,
        check=True,
    )


class RebuildProjectBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        init_git_repo(cls.root)
        toolchain = cls.root / "_toolchain"
        toolchain.mkdir()
        shutil.copytree(REPO / "templates", toolchain / "templates")
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.port = free_port()
        env = os.environ.copy()
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                # Isolation: Laufzeit, Zustand und Toolchain stammen sonst aus
                # der persönlichen Konfiguration (im Sandbox-Lauf teilweise
                # schreibgeschützt). Der Test legt seine Toolchain selbst an.
                "VIBE_RUNTIME": str(cls.log_dir),
                "VIBE_INSTALL": str(toolchain),
                "VIBE_STATE": str(cls.root / "_state"),
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

    def test_rebuild_type_is_selectable_and_creates_the_profile(self):
        page = self.browser.new_page(viewport={"width": 1400, "height": 1000})
        try:
            page.goto(self.base + "/classic#t=" + self.token)
            page.locator("#nf select").wait_for()
            page.wait_for_function(
                "() => [...document.querySelectorAll('#nf select option')].some(o => o.value === 'rebuild')"
            )

            page.locator("#nf input").first.fill("rebuild-ui")
            page.locator("#nf select").select_option("rebuild")
            page.get_by_role("button", name="Create and open assistant").click()

            page.get_by_role("tab", name="Work", exact=True).wait_for()
            project = self.root / "rebuild-ui"
            env = (project / ".vibe" / "project.env").read_text(encoding="utf-8")
            self.assertIn("TYPE=rebuild", env)
            self.assertIn("rebuild-env.py --check", env)
            agents = sorted((project / ".opencode" / "agents").glob("*.md"))
            self.assertEqual(len(agents), 10)
            self.assertIn("test-agent", {path.stem for path in agents})
            self.assertTrue((project / "docs" / "parity.md").is_file())
            self.assertTrue((project / "scripts" / "rebuild-env.py").is_file())
        finally:
            page.close()


if __name__ == "__main__":
    unittest.main()
