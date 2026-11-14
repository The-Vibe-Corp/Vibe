"""Tests für den zentralen Internet-Reconnect mehrerer Projekte (F18).

Laufen mehrere Projekte gleichzeitig, können mehrere Agentenläufe an einem
Anbieterlimit scheitern. Der Reconnect betrifft aber immer den ganzen Router:
Deshalb darf höchstens ein Reconnect gleichzeitig laufen. Die übrigen Projekte
warten auf dessen Ergebnis, werden darüber informiert und setzen ihren Lauf
danach fort.

Alle Tests arbeiten in temporären Verzeichnissen und gegen einen nachgebildeten
Helfer. Es wird **kein** Router kontaktiert.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"

FAKE_HELPER = '''import json, os, sys, time
with open(os.environ["FAKE_FRITZ_LOG"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps({
        "pid": os.getpid(),
        "start": time.time(),
        "project": os.environ.get("VIBE_PROJECT", ""),
    }) + "\\n")
delay = os.environ.get("FAKE_FRITZ_DELAY", "")
if delay:
    time.sleep(float(delay))
print("alte IP: 203.0.113.1")
print("neue IP: 203.0.113.9")
sys.exit(int(os.environ.get("FAKE_FRITZ_RC", "0")))
'''

REMOVED_ENV = (
    "VIBE_FRITZ_REUSE_SECONDS",
    "VIBE_FRITZ_WAIT_SECONDS",
    "VIBE_PROJECT",
    "FAKE_FRITZ_DELAY",
    "FAKE_FRITZ_RC",
    "VIBE_STATE",
    "VIBE_INSTALL",
    "VIBE_RUNTIME",
    "VIBE_CONFIG_FILE",
    "VIBE_AGENTS_DIR",
    "VIBE_PROFILE",
)


class CentralReconnectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name in ("_toolchain", "_logs", "home"):
            (self.root / name).mkdir()
        self.helper = self.root / "fake-fritz.py"
        self.helper.write_text(FAKE_HELPER, encoding="utf-8")
        self.helper_log = self.root / "helper.jsonl"
        self.env_file = self.root / "fritz.env"
        self.env_file.write_text(
            "FRITZ_ADDR=192.0.2.1\n"
            "FRITZ_USER=testuser\n"
            "FRITZ_PASS=geheim-passwort\n",
            encoding="utf-8",
        )
        self.state_file = self.root / "_toolchain" / "fritz-reconnect.json"
        self.waiters_file = self.root / "_toolchain" / "fritz-reconnect-waiters.jsonl"
        self.processes = []
        self.automation(True)

    def tearDown(self):
        for process in self.processes:
            if process.poll() is None:
                process.kill()
                process.wait()
            if process.stdout:
                process.stdout.close()
        self.tmp.cleanup()

    def automation(self, enabled):
        (self.root / "_toolchain" / "fritz.json").write_text(
            json.dumps({"automation": enabled}) + "\n", encoding="utf-8"
        )

    def env(self, project=None, **extra):
        env = os.environ.copy()
        for key in REMOVED_ENV:
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(self.root),
                "VIBE_NO_CONTAINER": "1",
                "HOME": str(self.root / "home"),
                "VIBE_STATE": str(self.root / "_toolchain"),
                "VIBE_INSTALL": str(self.root / "_toolchain"),
                "VIBE_RUNTIME": str(self.root / "_logs"),
                "VIBE_CONFIG_FILE": str(self.root / "home" / "config.json"),
                "VIBE_AGENTS_DIR": str(self.root / "home" / "agents"),
                "VIBE_FRITZ_PYTHON": sys.executable,
                "VIBE_FRITZ_SCRIPT": str(self.helper),
                "VIBE_FRITZ_ENV": str(self.env_file),
                "FAKE_FRITZ_LOG": str(self.helper_log),
            }
        )
        if project is not None:
            env["VIBE_PROJECT"] = project
        env.update({key: str(value) for key, value in extra.items()})
        return env

    def cli(self, *args, project=None, **extra):
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            env=self.env(project, **extra),
            cwd=str(self.root),
            capture_output=True,
            text=True,
            timeout=90,
        )

    def start(self, project, **extra):
        process = subprocess.Popen(
            [sys.executable, str(CLI), "fritz", "auto"],
            env=self.env(project, **extra),
            cwd=str(self.root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.processes.append(process)
        return process

    def calls(self):
        if not self.helper_log.exists():
            return []
        return [
            json.loads(line)
            for line in self.helper_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def state(self):
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except OSError:
            return {}

    def wait_until_running(self, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.state().get("state") == "running":
                return self.state()
            time.sleep(0.05)
        self.fail("Der zentrale Reconnect wurde nicht als laufend veröffentlicht")

    def finish(self, process, timeout=60):
        output = process.communicate(timeout=timeout)[0]
        if process in self.processes:
            self.processes.remove(process)
        return process.returncode, output


class SharedReconnectTest(CentralReconnectTest):
    def test_simultaneous_projects_share_one_reconnect(self):
        owner = self.start("projekt-a", FAKE_FRITZ_DELAY="3")
        self.wait_until_running()
        waiting_b = self.start("projekt-b", FAKE_FRITZ_DELAY="3")
        waiting_c = self.start("projekt-c", FAKE_FRITZ_DELAY="3")

        owner_rc, owner_out = self.finish(owner)
        b_rc, b_out = self.finish(waiting_b)
        c_rc, c_out = self.finish(waiting_c)

        self.assertEqual(owner_rc, 0, owner_out)
        self.assertEqual(b_rc, 0, b_out)
        self.assertEqual(c_rc, 0, c_out)
        self.assertEqual(len(self.calls()), 1, "genau ein Reconnect für alle Projekte")
        for output in (owner_out, b_out, c_out):
            self.assertIn("neue IP: 203.0.113.9", output)
        for output in (b_out, c_out):
            self.assertIn("kein zweiter Reconnect", output)
        self.assertIn("fortgesetzt", owner_out)

        state = self.state()
        self.assertEqual(state["state"], "done")
        self.assertTrue(state["ok"])
        self.assertEqual(state["owner"], "projekt-a")
        self.assertIn("projekt-b", state["affected"])
        self.assertIn("projekt-c", state["affected"])

    def test_a_failed_reconnect_is_reported_to_all_projects_and_not_repeated(self):
        owner = self.start("projekt-a", FAKE_FRITZ_DELAY="2", FAKE_FRITZ_RC="2")
        self.wait_until_running()
        waiting = self.start("projekt-b", FAKE_FRITZ_DELAY="2", FAKE_FRITZ_RC="2")

        owner_rc, owner_out = self.finish(owner)
        waiting_rc, waiting_out = self.finish(waiting)

        self.assertEqual(owner_rc, 1, owner_out)
        self.assertEqual(waiting_rc, 1, waiting_out)
        self.assertEqual(len(self.calls()), 1)
        self.assertIn("fehlgeschlagen", waiting_out)
        self.assertIn("kein zweiter Reconnect", waiting_out)
        self.assertFalse(self.state()["ok"])

    def test_a_waiting_project_never_starts_a_second_reconnect(self):
        owner = self.start("projekt-a", FAKE_FRITZ_DELAY="2")
        self.wait_until_running()

        waiting = subprocess.run(
            [sys.executable, str(CLI), "fritz", "auto"],
            env=self.env("projekt-b", VIBE_FRITZ_WAIT_SECONDS="0.2"),
            cwd=str(self.root),
            capture_output=True,
            text=True,
            timeout=60,
        )

        self.assertEqual(waiting.returncode, 3, waiting.stdout + waiting.stderr)
        self.assertIn("kein zweiter Reconnect", waiting.stdout)
        self.assertIn("läuft", waiting.stdout)
        self.assertEqual(len(self.calls()), 1, "das Warten startet keinen Helfer")
        self.finish(owner)
        self.assertEqual(len(self.calls()), 1)

    def test_a_recent_reconnect_is_reused_and_expires(self):
        first = self.cli("fritz", "auto", project="projekt-a")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertEqual(len(self.calls()), 1)

        reused = self.cli("fritz", "auto", project="projekt-b")
        self.assertEqual(reused.returncode, 0, reused.stdout + reused.stderr)
        self.assertIn("bereits", reused.stdout)
        self.assertIn("kein zweiter Reconnect", reused.stdout)
        self.assertEqual(len(self.calls()), 1)

        expired = self.cli(
            "fritz", "auto", project="projekt-c", VIBE_FRITZ_REUSE_SECONDS="0"
        )
        self.assertEqual(expired.returncode, 0, expired.stdout + expired.stderr)
        self.assertEqual(len(self.calls()), 2)

    def test_automation_off_still_means_no_reconnect(self):
        self.automation(False)

        result = self.cli("fritz", "auto", project="projekt-a")

        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("aus", result.stdout)
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.state_file.exists())


class CentralReconnectIntegrationTest(CentralReconnectTest):
    def test_a_manual_reconnect_participates_in_the_central_control(self):
        manual = self.cli("fritz", "reconnect")
        self.assertEqual(manual.returncode, 0, manual.stdout + manual.stderr)
        self.assertEqual(len(self.calls()), 1)

        project = self.cli("fritz", "auto", project="projekt-b")

        self.assertEqual(project.returncode, 0, project.stdout + project.stderr)
        self.assertIn("bereits", project.stdout)
        self.assertEqual(len(self.calls()), 1, "kein zweiter Reconnect nach dem manuellen")

    def test_status_reports_the_central_result(self):
        first = self.cli("fritz", "auto", project="projekt-a")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)

        status = self.cli("fritz")

        self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
        self.assertIn("Zentral", status.stdout)
        self.assertIn("zuletzt erfolgreich", status.stdout)
        self.assertIn("projekt-a", status.stdout)
        self.assertEqual(len(self.calls()), 1, "Statusabfrage startet keinen Helfer")

    def test_a_project_name_with_control_characters_is_published_cleanly(self):
        result = self.cli(
            "fritz", "auto", project="projekt\n\x1b[31mrot"
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        owner = self.state()["owner"]
        self.assertNotIn("\n", owner)
        self.assertNotIn("\x1b", owner)
        self.assertIn("projekt", owner)


if __name__ == "__main__":
    unittest.main()
