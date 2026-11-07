"""Tests für die Pause nach dem aktuellen Arbeitspaket (F4).

Der Nutzer kann eine Pause anfordern, während ein Arbeitspaket läuft. Der
Agent wird nicht unterbrochen; der Paket-Läufer beendet die laufende Schleife
nach dem aktuellen Paket und startet kein neues. Die Anforderung liegt als
einmalige Markierung im Laufzeitordner ``$VIBE/_logs`` und wird beim
Ausführen verbraucht.

Geprüft werden Modell, CLI, HTTP-API und das tatsächliche Verhalten von
``bin/vibe-run.sh`` mit einem nachgebildeten opencode-Aufruf.
"""
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
WEB = REPO / "bin" / "vibe-web.py"
RUNNER = REPO / "bin" / "vibe-run.sh"


def load_cli(vibe_root):
    """Lädt bin/vibe als Modul mit isoliertem VIBE und HOME."""
    old = {key: os.environ.get(key) for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(Path(vibe_root) / "home")
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_pause_under_test", str(CLI)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return module


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class PauseModelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        self.other = self.root / "zweit"
        for project in (self.project, self.other):
            (project / ".vibe").mkdir(parents=True)
            (project / ".vibe" / "project.env").write_text(
                "TYPE=generic\n", encoding="utf-8"
            )
        self.cli = load_cli(self.root)
        self.flag = self.root / "_logs" / "proj.pause-after"

    def tearDown(self):
        self.tmp.cleanup()

    def test_without_request_no_pause_is_active(self):
        self.assertFalse(self.cli.pause_after_active("proj"))
        self.assertFalse(self.flag.exists())

    def test_request_creates_a_marker_in_the_runtime_folder(self):
        self.cli.pause_after_request("proj")

        self.assertTrue(self.cli.pause_after_active("proj"))
        self.assertTrue(self.flag.is_file())
        self.assertFalse(self.cli.pause_after_active("zweit"))

    def test_cancel_removes_the_request(self):
        self.cli.pause_after_request("proj")

        self.assertTrue(self.cli.pause_after_cancel("proj"))

        self.assertFalse(self.cli.pause_after_active("proj"))
        self.assertFalse(self.flag.exists())
        self.assertFalse(self.cli.pause_after_cancel("proj"))

    def test_cli_rejects_an_unknown_project_without_writing_a_marker(self):
        with self.assertRaises(SystemExit) as raised:
            self.cli.cmd_pause("gibtsnicht", "on")

        self.assertIn("nicht gefunden", str(raised.exception))
        self.assertFalse((self.root / "_logs" / "gibtsnicht.pause-after").exists())

    def test_requests_of_different_projects_are_independent(self):
        self.cli.pause_after_request("proj")

        self.assertTrue(self.cli.pause_after_active("proj"))
        self.assertFalse(self.cli.pause_after_active("zweit"))

        self.cli.pause_after_request("zweit")
        self.cli.pause_after_cancel("proj")

        self.assertFalse(self.cli.pause_after_active("proj"))
        self.assertTrue(self.cli.pause_after_active("zweit"))

    def test_cli_requests_reports_and_releases_the_pause(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.cmd_pause("proj", "on")
        self.assertIn("angefordert", out.getvalue())
        self.assertTrue(self.cli.pause_after_active("proj"))

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.cmd_pause("proj")
        self.assertIn("angefordert", out.getvalue())

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.cmd_pause("proj", "off")
        self.assertIn("aufgehoben", out.getvalue())
        self.assertFalse(self.cli.pause_after_active("proj"))


class PauseApiFixture(unittest.TestCase):
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
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True
        )
        cls.port = free_port()
        env = os.environ.copy()
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.root / "home"),
            }
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.root / "_logs" / "web.token"
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

    @classmethod
    def tearDownClass(cls):
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
        flag = self.root / "_logs" / "proj.pause-after"
        if flag.exists():
            flag.unlink()

    def request(self, path, payload=None, token=True):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            method="POST" if data else "GET",
        )
        req.add_header("Host", f"127.0.0.1:{self.port}")
        if token:
            req.add_header("X-Token", self.token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            code = error.code
            error.close()
            return code, body

    def flag(self):
        return self.root / "_logs" / "proj.pause-after"


class PauseApiTest(PauseApiFixture):
    def test_project_detail_exposes_pause_state(self):
        status, body = self.request("/api/project?name=proj")

        self.assertEqual(status, 200, body)
        self.assertFalse(json.loads(body)["pause_after"])

    def test_api_requests_and_releases_the_pause(self):
        status, body = self.request(
            "/api/pause", {"name": "proj", "action": "on"}
        )
        self.assertEqual(status, 200, body)
        result = json.loads(body)
        self.assertTrue(result["ok"])
        self.assertTrue(result["pause_after"])
        self.assertTrue(self.flag().is_file())

        status, body = self.request("/api/project?name=proj")
        self.assertEqual(status, 200, body)
        self.assertTrue(json.loads(body)["pause_after"])

        status, body = self.request(
            "/api/pause", {"name": "proj", "action": "off"}
        )
        self.assertEqual(status, 200, body)
        self.assertFalse(json.loads(body)["pause_after"])
        self.assertFalse(self.flag().exists())

    def test_api_requires_token_and_keeps_state(self):
        status, _ = self.request(
            "/api/pause", {"name": "proj", "action": "on"}, token=False
        )

        self.assertEqual(status, 403)
        self.assertFalse(self.flag().exists())

    def test_api_rejects_unknown_action_without_changing_anything(self):
        status, body = self.request(
            "/api/pause", {"name": "proj", "action": "spaeter"}
        )

        self.assertEqual(status, 400, body)
        self.assertFalse(json.loads(body)["ok"])
        self.assertFalse(self.flag().exists())

    def test_api_reports_releasing_without_a_request_truthfully(self):
        status, body = self.request(
            "/api/pause", {"name": "proj", "action": "off"}
        )

        self.assertEqual(status, 200, body)
        result = json.loads(body)
        self.assertTrue(result["ok"])
        self.assertFalse(result["pause_after"])
        self.assertIn("Keine Pause", result["message"])
        self.assertFalse(self.flag().exists())


NEXT_ITEM = '''import os, sys
here = os.path.dirname(os.path.abspath(__file__))
count_path = os.path.join(here, "next-calls")
try:
    calls = int(open(count_path, encoding="utf-8").read())
except OSError:
    calls = 0
calls += 1
open(count_path, "w", encoding="utf-8").write(str(calls))
if calls > 2:
    sys.exit(1)
open("/tmp/next_id", "w", encoding="utf-8").write("F%d" % calls)
open("/tmp/next_block", "w", encoding="utf-8").write(
    "- [ ] F%d Testpaket\\n  Beschreibung: Test\\n" % calls
)
'''

FAKE_OPENCODE = '''#!/usr/bin/env bash
printf 'x\\n' >> "$VIBE/_logs/opencode.invocations"
if [ -n "$FAKE_OPENCODE_PAUSE" ]; then
  touch "$VIBE/_logs/$VIBE_LOGNAME.pause-after"
fi
exit 0
'''

FAKE_CURL = '''#!/usr/bin/env bash
exit 7
'''


class RunnerPauseTest(unittest.TestCase):
    """Prüft den echten Paket-Läufer mit einer nachgebildeten opencode-Ablage."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nVERIFY_FULL=\"touch verify.done\"\n", encoding="utf-8"
        )
        (self.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] F1 Testpaket\n  Beschreibung: Test\n",
            encoding="utf-8",
        )
        self.verify = self.root / "_toolchain" / "verify"
        self.verify.mkdir(parents=True)
        (self.verify / "next_item.py").write_text(NEXT_ITEM, encoding="utf-8")
        marker = self.verify / "verify-marker.txt"
        marker.write_text("ok\n", encoding="utf-8")
        digest = hashlib.sha256(marker.read_bytes()).hexdigest()
        home_config = self.root / "home" / ".config"
        home_config.mkdir(parents=True)
        (home_config / "schreibfuchs-verify.sha").write_text(
            f"{digest}  verify-marker.txt\n", encoding="utf-8"
        )
        fakebin = self.root / "fakebin"
        fakebin.mkdir()
        for name, text in (("opencode", FAKE_OPENCODE), ("curl", FAKE_CURL)):
            path = fakebin / name
            path.write_text(text, encoding="utf-8")
            path.chmod(0o755)
        self.flag = self.root / "_logs" / "proj.pause-after"

    def tearDown(self):
        self.tmp.cleanup()

    def run_runner(self, pause_during_first_package=False, max_packages=5):
        env = os.environ.copy()
        env.update(
            {
                "VIBE": str(self.root),
                "HOME": str(self.root / "home"),
                "PATH": str(self.root / "fakebin") + os.pathsep + env.get("PATH", ""),
                "VIBE_LOGNAME": "proj",
                "VIBE_MAX_PACKAGES": str(max_packages),
                "AGENT": "coding-agent_deepseek",
            }
        )
        if pause_during_first_package:
            env["FAKE_OPENCODE_PAUSE"] = "1"
        return subprocess.run(
            ["bash", str(RUNNER), str(self.project)],
            cwd=str(self.project),
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )

    def opencode_calls(self):
        path = self.root / "_logs" / "opencode.invocations"
        if not path.exists():
            return []
        return path.read_text(encoding="utf-8").splitlines()

    def test_runner_processes_packages_normally_without_a_request(self):
        result = self.run_runner()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(self.opencode_calls()), 2)
        self.assertTrue((self.project / "verify.done").exists())

    def test_runner_finishes_the_current_package_and_starts_no_new_one(self):
        result = self.run_runner(pause_during_first_package=True)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(self.opencode_calls()), 1, result.stdout + result.stderr)
        self.assertIn("F1", result.stdout)
        self.assertIn("Agent beendet, Exit-Code 0", result.stdout)
        self.assertIn("PAUSE", result.stdout)
        self.assertFalse(self.flag.exists(), "Pause-Markierung wurde nicht verbraucht")
        self.assertFalse((self.project / "verify.done").exists())

    def test_runner_starts_no_package_when_pause_was_requested_before_start(self):
        self.flag.parent.mkdir(parents=True, exist_ok=True)
        self.flag.write_text("", encoding="utf-8")

        result = self.run_runner()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.opencode_calls(), [])
        self.assertIn("PAUSE", result.stdout)
        self.assertFalse(self.flag.exists())

    def test_pause_is_consumed_so_the_next_run_continues(self):
        first = self.run_runner(pause_during_first_package=True)

        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertEqual(len(self.opencode_calls()), 1, first.stdout + first.stderr)
        self.assertFalse(self.flag.exists())

        second = self.run_runner()

        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(len(self.opencode_calls()), 2, second.stdout + second.stderr)
        self.assertIn("F2", second.stdout)
        self.assertTrue((self.project / "verify.done").exists())

    def test_pause_at_the_package_limit_is_consumed_after_the_loop(self):
        result = self.run_runner(pause_during_first_package=True, max_packages=1)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(self.opencode_calls()), 1, result.stdout + result.stderr)
        self.assertIn("PAUSE: Pause angefordert", result.stdout)
        self.assertFalse(self.flag.exists(), "Pause-Markierung blieb liegen")
        self.assertFalse((self.project / "verify.done").exists())


if __name__ == "__main__":
    unittest.main()
