"""Regression: Aufräumen des eigenen tmux-Servers trifft nie den des Aufrufers.

Ein geerbtes ``TMUX`` gewinnt in tmux gegen ``TMUX_TMPDIR``. Wird beim
Aufräumen nur ``TMUX_TMPDIR`` gesetzt, beendet ``tmux kill-server`` den Server
der Sitzung, in der die Prüfung gestartet wurde – samt Dashboard, opencode und
laufendem Agentenlauf.

Die Tests arbeiten mit echten, aber eigenen tmux-Servern in temporären
Verzeichnissen; der Server des Aufrufers wird nicht angefasst.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.support.tmux_cleanup import cleanup_env


def tmux(environment, *args):
    return subprocess.run(
        ["tmux", *args],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )


class CleanupEnvTest(unittest.TestCase):
    """Die Aufräumumgebung zeigt ausschließlich auf den eigenen Server."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.caller_dir = self.root / "caller"
        self.own_dir = self.root / "own"
        for folder in (self.caller_dir, self.own_dir):
            folder.mkdir()
            # Ohne eigene Rechte ignoriert tmux TMUX_TMPDIR.
            folder.chmod(0o700)
        self.clean = {
            key: value
            for key, value in os.environ.items()
            if key not in ("TMUX", "TMUX_PANE")
        }
        self.start_server(self.caller_dir, "caller")
        self.start_server(self.own_dir, "own")

    def tearDown(self):
        for folder in (self.caller_dir, self.own_dir):
            tmux({**self.clean, "TMUX_TMPDIR": str(folder)}, "kill-server")
        self.tmp.cleanup()

    def start_server(self, folder, name):
        result = tmux(
            {**self.clean, "TMUX_TMPDIR": str(folder)},
            "new-session", "-d", "-s", name,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def socket_path(self, folder):
        return folder / ("tmux-%d" % os.getuid()) / "default"

    def sessions(self, folder):
        result = tmux({**self.clean, "TMUX_TMPDIR": str(folder)}, "ls", "-F", "#{session_name}")
        return [] if result.returncode != 0 else result.stdout.split()

    def test_cleanup_env_drops_the_inherited_client_socket(self):
        inherited = {
            **self.clean,
            "TMUX": str(self.socket_path(self.caller_dir)) + ",1,0",
            "TMUX_PANE": "%0",
        }

        environment = cleanup_env(inherited, self.own_dir)

        self.assertNotIn("TMUX", environment)
        self.assertNotIn("TMUX_PANE", environment)
        self.assertEqual(environment["TMUX_TMPDIR"], str(self.own_dir))
        # Die Eingabe bleibt unverändert.
        self.assertEqual(inherited["TMUX_PANE"], "%0")

    def test_cleanup_env_never_targets_the_callers_server(self):
        inherited = {
            **self.clean,
            "TMUX": str(self.socket_path(self.caller_dir)) + ",1,0",
            "TMUX_PANE": "%0",
        }

        result = tmux(cleanup_env(inherited, self.own_dir), "kill-server")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.sessions(self.caller_dir),
            ["caller"],
            "Der tmux-Server des Aufrufers wurde beendet",
        )
        self.assertEqual(self.sessions(self.own_dir), [])


if __name__ == "__main__":
    unittest.main()
