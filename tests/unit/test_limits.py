"""Run behaviour: the removed global limit mode must not influence runs.

The former ``vibe limits stop|continue`` setting (German "Laufverhalten") was
removed completely. A stale ``limits.json`` must be harmless: quota and login
failures always stop the run immediately, regardless of the file's content.

Aufruf: python3 -m unittest tests.unit.test_limits -v
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"
RUNNER = BIN / "vibe-run.sh"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support  # noqa: E402


def isolated_env(root, home, state, install, runtime):
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("VIBE_") or key.startswith("SANDBOX") or key in (
            "VIBE",
            "AGENT",
            "TYPE",
            "VERIFY_QUICK",
            "VERIFY_FULL",
        ):
            env.pop(key, None)
    env.update(
        {
            "VIBE": str(root),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "VIBE_CONFIG_FILE": str(root / "config.json"),
            "VIBE_STORAGE_LOCK_DIR": str(root / "locks"),
            "VIBE_INSTALL": str(install),
            "VIBE_RUNTIME": str(runtime),
            "VIBE_STATE": str(state),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return env


class LimitsRemovalTest(unittest.TestCase):
    """The CLI no longer offers the removed setting or writes its file."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.install = self.root / "_toolchain"
        self.runtime = self.root / "_logs"
        self.state = self.root / "_state"
        self.state.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=str(self.root),
            env=isolated_env(
                self.root, self.home, self.state, self.install, self.runtime
            ),
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_limits_continue_does_not_create_a_config_file(self):
        self.run_cli("limits", "continue")

        self.assertFalse(
            (self.state / "limits.json").exists(),
            "Der entfernte Modus wurde weiterhin persistiert",
        )

    def test_limits_stop_does_not_create_a_config_file(self):
        self.run_cli("limits", "stop")

        self.assertFalse(
            (self.state / "limits.json").exists(),
            "Der entfernte Modus wurde weiterhin persistiert",
        )


class RunnerLimitsTest(unittest.TestCase):
    """Quota/auth always stop immediately, even with a stale limits.json."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        (self.tool_bin / "vibe").write_text(support.FAKE_VIBE, encoding="utf-8")
        (self.tool_bin / "vibe").chmod(0o755)
        self.runtime = self.root / "_logs"
        self.state = self.root / "_state"
        self.state.mkdir()
        self.project = self.root / "proj"
        support.init_repo(self.project)
        self.calls = self.root / "opencode.calls"
        self.counter = self.root / "counter"

    def tearDown(self):
        self.tmp.cleanup()

    def write_project(self, max_retries):
        support.write_project(
            self.project,
            "TYPE=generic\n"
            "AGENT=tester\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL="true"\n'
            f"MAX_RETRIES={max_retries}\n",
            feedback=[support.ticket_record(
                "F1", "Erstes Paket", type="feedback", description="Test")],
        )
        support.commit_all(self.project, "Ausgangsstand")

    def runner_env(self, fake_mode):
        env = isolated_env(
            self.root, self.home, self.state, self.install, self.runtime
        )
        fakebin = support.install_fake_tools(self.root)
        env.update(
            {
                "VIBE_AGENTS_DIR": str(self.agents),
                "VIBE_MAX_PACKAGES": "1",
                "VIBE_RETRY_DELAY": "0",
                "FAKE_CALLS": str(self.calls),
                "FAKE_COUNTER": str(self.counter),
                "FAKE_MODE": fake_mode,
                "FAKE_ARGS_PATH": str(self.root / "opencode.args"),
                "PATH": str(fakebin) + os.pathsep + os.environ.get("PATH", ""),
            }
        )
        return env

    def run_runner(self, fake_mode, max_retries=2):
        self.write_project(max_retries)
        return subprocess.run(
            ["bash", str(RUNNER), str(self.project)],
            cwd=str(self.project),
            env=self.runner_env(fake_mode),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=90,
        )

    def call_lines(self):
        if not self.calls.exists():
            return []
        return self.calls.read_text(encoding="utf-8").splitlines()

    def log_text(self):
        path = self.runtime / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def assert_blocked_immediately(self, mode):
        result = self.run_runner(mode)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(len(self.call_lines()), 1, self.call_lines())
        combined = (self.log_text() + result.stdout).lower()
        self.assertIn("blockiert", combined, combined)
        if mode == "quota":
            self.assertTrue(
                "quota" in combined or "kontingent" in combined, combined
            )
        else:
            self.assertTrue(
                "anmeld" in combined
                or "auth" in combined
                or "401" in combined,
                combined,
            )

    def write_limits(self, text):
        (self.state / "limits.json").write_text(text, encoding="utf-8")

    def test_default_quota_blocks_immediately(self):
        self.assertFalse((self.state / "limits.json").exists())
        self.assert_blocked_immediately("quota")

    def test_default_auth_blocks_immediately(self):
        self.assertFalse((self.state / "limits.json").exists())
        self.assert_blocked_immediately("auth")

    def test_stale_continue_does_not_change_quota_behaviour(self):
        self.write_limits('{"mode": "continue"}\n')
        self.assert_blocked_immediately("quota")

    def test_stale_continue_does_not_change_auth_behaviour(self):
        self.write_limits('{"mode": "continue"}\n')
        self.assert_blocked_immediately("auth")

    def test_stale_stop_does_not_change_quota_behaviour(self):
        self.write_limits('{"mode": "stop"}\n')
        self.assert_blocked_immediately("quota")

    def test_malformed_limits_file_is_harmless_for_quota(self):
        self.write_limits("{ kaputt\n")
        self.assert_blocked_immediately("quota")

    def test_malformed_limits_file_is_harmless_for_auth(self):
        self.write_limits("kein json\n")
        self.assert_blocked_immediately("auth")


if __name__ == "__main__":
    unittest.main()
