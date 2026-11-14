"""Browserabnahme F27: „Trotz Änderungen starten“ im Projektdetail.

Der Test startet das echte Dashboard auf einem eigenen Port. ``tmux`` ist eine
Attrappe, die die Aufrufe aufzeichnet; es wird kein Agent und kein Modell
gestartet.

Geprüft wird:

* Bei einem unsauberen Projekt bietet das Detail die Aktion „Trotz Änderungen
  starten“ an.
* Die Aktion verlangt eine Bestätigung.
* Nach der Bestätigung startet der Lauf mit ``VIBE_KEEP_CHANGES=1`` und die
  Rückmeldung nennt die zurückbehaltenen Dateien.
* Bei einem sauberen Projekt ist die Aktion nicht nutzbar.

Die Datei ``F27-trotz-aenderungen.png`` entsteht in diesem Test und zeigt die
tatsächliche Oberfläche.
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
SHOTS = Path(os.environ.get("VIBE_VERIFY_SCREENSHOT_DIR", REPO / "docs" / "features"))
SHOT = SHOTS / "F27-trotz-aenderungen.png"

PROJECT_ENV = """TYPE=generic
AGENT=test-agent
TESTER=test-agent
REVIEWER=code-reviewer
VERIFY_PACKAGE="true"
VERIFY_FULL="true"
"""

FEEDBACK = "# FEEDBACK\n\n- [ ] F1 Erstes Paket\n  Beschreibung: Test\n"

FAKE_TMUX = r'''#!/usr/bin/env python3
"""Zeichnet tmux-Aufrufe auf und verhält sich wie ein frischer Server."""
import json
import os
import sys

args = sys.argv[1:]
path = os.environ.get("FAKE_TMUX_LOG")
if path:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"args": args}, ensure_ascii=False) + "\n")

if args[:1] == ["has-session"]:
    sys.exit(1)
if args[:1] == ["show-environment"]:
    sys.stdout.write("unknown variable: VIBE_MANAGED\n")
    sys.exit(1)
sys.exit(0)
'''


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def git(project, *args):
    return subprocess.run(
        ["git", "-C", str(project), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def init_repo(project):
    project.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(project)],
        check=True,
        capture_output=True,
        text=True,
    )
    git(project, "config", "user.name", "Test")
    git(project, "config", "user.email", "test@example.invalid")
    git(project, "config", "commit.gpgsign", "false")


def commit_all(project, message):
    git(project, "add", "-A")
    result = git(project, "commit", "-q", "-m", message)
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)


def write_project(root, name, agents):
    project = root / name
    init_repo(project)
    (project / ".vibe").mkdir(parents=True, exist_ok=True)
    (project / ".vibe" / "project.env").write_text(
        PROJECT_ENV, encoding="utf-8"
    )
    (project / "FEEDBACK.md").write_text(FEEDBACK, encoding="utf-8")
    (project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
    project_agent = project / ".opencode" / "agents" / "test-agent.md"
    project_agent.parent.mkdir(parents=True)
    project_agent.write_text(
        "---\ndescription: Testagent\nmode: subagent\n---\n",
        encoding="utf-8",
    )
    commit_all(project, "Ausgangsstand")
    return project


class KeepChangesUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        for name in ("test-agent", "code-reviewer"):
            (cls.agents / (name + ".md")).write_text(
                "---\ndescription: Testagent\nmode: subagent\n---\n",
                encoding="utf-8",
            )
        cls.dirty = write_project(cls.root, "dirtyproj", cls.agents)
        (cls.dirty / "unfertig.txt").write_text(
            "unfertig\n", encoding="utf-8"
        )
        cls.clean = write_project(cls.root, "cleanproj", cls.agents)

        cls.fakebin = cls.root / "fakebin"
        cls.fakebin.mkdir()
        tmux = cls.fakebin / "tmux"
        tmux.write_text(FAKE_TMUX, encoding="utf-8")
        tmux.chmod(0o755)
        cls.tmux_log = cls.root / "tmux.log"

        cls.runtime = cls.root / "_logs"
        cls.port = free_port()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_"):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "VIBE_INSTALL": str(cls.root / "_toolchain"),
                "VIBE_RUNTIME": str(cls.runtime),
                "VIBE_STATE": str(cls.root / "_state"),
                "VIBE_AGENTS_DIR": str(cls.agents),
                "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
                "VIBE_STORAGE_LOCK_DIR": str(cls.home / "locks"),
                "HOME": str(cls.home),
                "XDG_CONFIG_HOME": str(cls.home / ".config"),
                "PATH": str(cls.fakebin) + os.pathsep + env.get("PATH", ""),
                "FAKE_TMUX_LOG": str(cls.tmux_log),
            }
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.runtime / "web.token"
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
        if self.tmux_log.exists():
            self.tmux_log.unlink()
        self.page = self.browser.new_page(
            viewport={"width": 1400, "height": 1000}
        )
        # Ein nativer Bestätigungsdialog würde den Lauf sonst still abbrechen.
        self.dialog_seen = False

        def on_dialog(dialog):
            self.dialog_seen = True
            dialog.accept()

        self.page.on("dialog", on_dialog)

    def tearDown(self):
        self.page.close()

    def wait_until(self, predicate, timeout=15, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def open_detail(self, name):
        self.page.goto(self.base + "/#t=" + self.token)
        row = self.page.locator("tr.row", has_text=name).first
        row.wait_for()
        row.click()
        self.page.get_by_role("button", name="← zurück").wait_for()

    def new_sessions(self):
        if not self.tmux_log.exists():
            return []
        records = [
            json.loads(line)
            for line in self.tmux_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return [
            " ".join(record["args"])
            for record in records
            if record.get("args", [])[:1] == ["new-session"]
        ]

    def test_dirty_project_offers_keep_changes_with_confirmation_and_files(self):
        self.open_detail("dirtyproj")
        button = self.page.get_by_role(
            "button", name="Trotz Änderungen starten"
        )
        button.wait_for()
        self.assertTrue(button.is_visible())

        SHOTS.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(SHOT))
        self.assertTrue(SHOT.exists() and SHOT.stat().st_size > 0)

        button.click()
        group = self.page.locator(".confirm")
        try:
            group.wait_for(timeout=5000)
        except Exception:
            # Ein nativer Dialog wurde bereits automatisch bestätigt.
            group = None
        confirmed = bool(group is not None and group.count())
        if confirmed:
            yes = group.get_by_role("button").filter(has_not_text="Abbrechen")
            self.assertGreater(
                yes.count(), 0, "Bestätigung bot keine Zustimmung an"
            )
            yes.first.click()
        else:
            confirmed = self.dialog_seen
        self.assertTrue(
            confirmed,
            "„Trotz Änderungen starten“ startete ohne Bestätigung.",
        )

        toasts = self.page.locator("#toasts .toast").filter(
            has_text="unfertig.txt"
        )
        self.wait_until(
            lambda: toasts.count() > 0,
            message="Die Rückmeldung nannte die zurückbehaltene Datei nicht",
        )
        sessions = self.new_sessions()
        self.assertEqual(len(sessions), 1, sessions)
        self.assertIn("VIBE_KEEP_CHANGES=1", sessions[0])
        self.assertEqual(
            (self.dirty / "unfertig.txt").read_text(encoding="utf-8"),
            "unfertig\n",
        )

    def test_clean_project_does_not_offer_an_enabled_keep_changes_action(self):
        self.open_detail("cleanproj")
        self.page.get_by_role("tab", name="Arbeit", exact=True).wait_for()

        button = self.page.get_by_role(
            "button", name="Trotz Änderungen starten"
        )
        if button.count():
            self.assertFalse(
                button.first.is_visible() and button.first.is_enabled(),
                "Sauberes Projekt bot die Aktion „Trotz Änderungen starten“ an",
            )


if __name__ == "__main__":
    unittest.main()
