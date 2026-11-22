"""Tests für den Fritzbox-Reconnect in der Oberfläche (F5).

Der Reconnect ist eine optionale Altintegration: Nach einem fehlgeschlagenen
Agentenlauf kann der Paket-Läufer eine neue Internet-IP anfordern. Dieses
Arbeitspaket macht die Automatik standardmäßig abschaltbar (Standard: aus) und
über Dashboard/CLI sichtbar und schaltbar; zusätzlich ist ein manueller
Reconnect möglich.

Geprüft werden Modell, CLI, HTTP-API und das tatsächliche Verhalten von
``bin/vibe-run.sh`` mit einer nachgebildeten ``vibe``-Ablage. Es wird **kein**
echter Router kontaktiert: Interpreter, Helfer und Konfigurationsdatei werden
in allen Tests auf temporäre Attrappen umgebogen.
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

from tests.unit import env_support

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
WEB = REPO / "bin" / "vibe-web.py"
RUNNER = REPO / "bin" / "vibe-run.sh"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support

FAKE_HELPER = '''import json, os, sys, time
log = os.environ.get("FAKE_FRITZ_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"env": os.environ.get("FRITZ_ENV"),
                                 "argv": sys.argv[1:]}) + "\\n")
delay_file = os.environ.get("FAKE_FRITZ_DELAY_FILE")
if delay_file and os.path.exists(delay_file):
    time.sleep(float(open(delay_file, encoding="utf-8").read().strip() or "0"))
rc_file = os.environ.get("FAKE_FRITZ_RC_FILE")
rc = 0
if rc_file and os.path.exists(rc_file):
    rc = int(open(rc_file, encoding="utf-8").read().strip() or "0")
print("alte IP: 203.0.113.1")
print("neue IP: 203.0.113.9")
sys.exit(rc)
'''


def load_cli(vibe_root):
    """Lädt bin/vibe als Modul mit isoliertem VIBE und HOME."""
    keys = ("VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_INSTALL", "VIBE_STATE",
            "VIBE_RUNTIME", "VIBE_CONFIG_FILE", "VIBE_AGENTS_DIR", "VIBE_PROFILE")
    old = {key: os.environ.get(key) for key in keys}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(Path(vibe_root) / "home")
    os.environ["VIBE_INSTALL"] = str(Path(vibe_root) / "_toolchain")
    os.environ["VIBE_STATE"] = str(Path(vibe_root) / "_toolchain")
    os.environ["VIBE_RUNTIME"] = str(Path(vibe_root) / "_logs")
    os.environ["VIBE_CONFIG_FILE"] = str(Path(vibe_root) / "home" / "config.json")
    os.environ["VIBE_AGENTS_DIR"] = str(Path(vibe_root) / "home" / "agents")
    os.environ.pop("VIBE_PROFILE", None)
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_fritz_under_test", str(CLI)
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


class FritzModelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.helper = self.root / "fake-fritz.py"
        self.helper.write_text(FAKE_HELPER, encoding="utf-8")
        self.env_file = self.root / "fritz.env"
        self.env_file.write_text(
            "FRITZ_ADDR=192.0.2.1\n"
            "FRITZ_USER=testuser\n"
            "FRITZ_PASS=geheim-passwort\n",
            encoding="utf-8",
        )
        self.log = self.root / "fake-fritz.log"
        self.rc_file = self.root / "fake-rc"
        self.delay_file = self.root / "fake-delay"
        self.old_env = {
            key: os.environ.get(key)
            for key in (
                "VIBE_FRITZ_PYTHON",
                "VIBE_FRITZ_SCRIPT",
                "VIBE_FRITZ_ENV",
                "FAKE_FRITZ_LOG",
                "FAKE_FRITZ_RC_FILE",
                "FAKE_FRITZ_DELAY_FILE",
            )
        }
        os.environ.update(
            {
                "VIBE_FRITZ_PYTHON": sys.executable,
                "VIBE_FRITZ_SCRIPT": str(self.helper),
                "VIBE_FRITZ_ENV": str(self.env_file),
                "FAKE_FRITZ_LOG": str(self.log),
                "FAKE_FRITZ_RC_FILE": str(self.rc_file),
                "FAKE_FRITZ_DELAY_FILE": str(self.delay_file),
            }
        )
        self.cli = load_cli(self.root)
        self.settings = self.root / "_toolchain" / "fritz.json"

    def tearDown(self):
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def calls(self):
        if not self.log.exists():
            return []
        return [
            json.loads(line)
            for line in self.log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_automation_is_off_by_default(self):
        self.assertFalse(self.cli.fritz_automation())
        status = self.cli.fritz_status()

        self.assertFalse(status["automation"])
        self.assertFalse(self.settings.exists())

    def test_automation_can_be_switched_on_and_off(self):
        self.assertTrue(self.cli.fritz_automation_set(True))
        self.assertTrue(self.cli.fritz_automation())
        self.assertEqual(
            json.loads(self.settings.read_text(encoding="utf-8")),
            {"automation": True},
        )
        self.assertTrue(self.cli.fritz_status()["automation"])

        self.assertFalse(self.cli.fritz_automation_set(False))
        self.assertFalse(self.cli.fritz_automation())
        self.assertFalse(self.cli.fritz_status()["automation"])

    def test_automation_set_rejects_non_boolean_input(self):
        with self.assertRaises(ValueError):
            self.cli.fritz_automation_set("true")
        self.assertFalse(self.settings.exists())

    def test_a_broken_settings_file_counts_as_off(self):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text("kaputt\n", encoding="utf-8")

        self.assertFalse(self.cli.fritz_automation())

    def test_status_reports_readiness_without_revealing_the_password(self):
        status = self.cli.fritz_status()

        self.assertTrue(status["configured"])
        self.assertTrue(status["ready"])
        self.assertNotIn("geheim-passwort", json.dumps(status, ensure_ascii=False))
        self.assertNotIn("geheim-passwort", repr(status))
        self.assertEqual(self.calls(), [], "Statusabfrage darf den Router nicht kontaktieren")

    def test_an_incomplete_configuration_is_not_configured(self):
        self.env_file.write_text("FRITZ_ADDR=192.0.2.1\n", encoding="utf-8")

        self.assertFalse(self.cli.fritz_status()["configured"])
        self.assertFalse(self.cli.fritz_status()["ready"])

    def test_status_survives_an_unreadable_configuration(self):
        self.env_file.write_bytes(b"\xff\xfeFRITZ_ADDR=192.0.2.1\n")

        status = self.cli.fritz_status()

        self.assertFalse(status["configured"])
        self.assertFalse(status["ready"])
        self.assertEqual(self.calls(), [])

    def test_status_reports_a_missing_helper_and_interpreter(self):
        os.environ["VIBE_FRITZ_SCRIPT"] = str(self.root / "fehlt.py")
        self.assertFalse(self.cli.fritz_status()["script_ok"])
        self.assertFalse(self.cli.fritz_status()["ready"])

        os.environ["VIBE_FRITZ_SCRIPT"] = str(self.helper)
        os.environ["VIBE_FRITZ_PYTHON"] = str(self.root / "python-fehlt")
        self.assertFalse(self.cli.fritz_status()["python_ok"])
        self.assertFalse(self.cli.fritz_status()["ready"])

    def test_manual_reconnect_is_refused_without_configuration(self):
        self.env_file.unlink()

        with self.assertRaises(ValueError) as raised:
            self.cli.fritz_reconnect()

        self.assertIn("nicht konfiguriert", str(raised.exception))
        self.assertEqual(self.calls(), [])

    def test_manual_reconnect_runs_the_helper_with_the_configured_env(self):
        result = self.cli.fritz_reconnect(timeout=30)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["returncode"], 0)
        self.assertIn("neue IP: 203.0.113.9", result["output"])
        calls = self.calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["env"], str(self.env_file))
        self.assertEqual(calls[0]["argv"], [])

    def test_manual_reconnect_reports_a_failing_helper(self):
        self.rc_file.write_text("2\n", encoding="utf-8")

        result = self.cli.fritz_reconnect(timeout=30)

        self.assertFalse(result["ok"])
        self.assertEqual(result["returncode"], 2)
        self.assertIn("fehlgeschlagen", result["message"])
        self.assertIn("alte IP: 203.0.113.1", result["output"])

    def test_manual_reconnect_respects_the_timeout(self):
        self.delay_file.write_text("5\n", encoding="utf-8")
        started = time.time()

        result = self.cli.fritz_reconnect(timeout=0.5)

        self.assertFalse(result["ok"])
        self.assertIn("Zeit", result["message"])
        self.assertLess(time.time() - started, 4)

    def test_auto_does_nothing_while_automation_is_off(self):
        result = self.cli.fritz_auto()

        self.assertFalse(result["ran"])
        self.assertIn("aus", result["message"])
        self.assertEqual(self.calls(), [])

    def test_auto_reconnects_while_automation_is_on(self):
        self.cli.fritz_automation_set(True)

        result = self.cli.fritz_auto(timeout=30)

        self.assertTrue(result["ran"])
        self.assertTrue(result["result"]["ok"], result)
        self.assertEqual(len(self.calls()), 1)

    def test_auto_does_not_run_without_configuration_even_when_on(self):
        self.cli.fritz_automation_set(True)
        self.env_file.unlink()

        result = self.cli.fritz_auto()

        self.assertFalse(result["ran"])
        self.assertIn("nicht konfiguriert", result["message"])
        self.assertEqual(self.calls(), [])

    def test_cli_toggles_reports_and_guards_the_automatic(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.cmd_fritz("on")
        self.assertIn("Automatik: an", out.getvalue())
        self.assertTrue(self.cli.fritz_automation())

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.cmd_fritz()
        self.assertIn("Automatik: an", out.getvalue())

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.cmd_fritz("off")
        self.assertIn("Automatik: aus", out.getvalue())
        self.assertFalse(self.cli.fritz_automation())

        with self.assertRaises(SystemExit) as raised:
            with contextlib.redirect_stdout(io.StringIO()):
                self.cli.cmd_fritz("auto")
        self.assertEqual(raised.exception.code, 3)
        self.assertEqual(self.calls(), [])

    def test_cli_manual_reconnect_fails_with_exit_code(self):
        self.rc_file.write_text("1\n", encoding="utf-8")

        with self.assertRaises(SystemExit) as raised:
            with contextlib.redirect_stdout(io.StringIO()):
                self.cli.cmd_fritz("reconnect")

        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(len(self.calls()), 1)


class FritzApiFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.helper = cls.root / "fake-fritz.py"
        cls.helper.write_text(FAKE_HELPER, encoding="utf-8")
        cls.env_file = cls.root / "fritz.env"
        cls.env_file.write_text(
            "FRITZ_ADDR=192.0.2.1\n"
            "FRITZ_USER=testuser\n"
            "FRITZ_PASS=geheim-passwort\n",
            encoding="utf-8",
        )
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True
        )
        cls.log = cls.root / "fake-fritz.log"
        cls.rc_file = cls.root / "fake-rc"
        cls.port = free_port()
        # VIBE_UI_BIND/VIBE_UI_PORT und persönliche Konfiguration nicht erben.
        env = env_support.isolated_environ()
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_STATE": str(cls.root / "_toolchain"),
                "VIBE_INSTALL": str(cls.root / "_toolchain"),
                "VIBE_RUNTIME": str(cls.root / "_logs"),
                "VIBE_CONFIG_FILE": str(cls.root / "home" / "config.json"),
                "VIBE_AGENTS_DIR": str(cls.root / "home" / "agents"),
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.root / "home"),
                "VIBE_FRITZ_PYTHON": sys.executable,
                "VIBE_FRITZ_SCRIPT": str(cls.helper),
                "VIBE_FRITZ_ENV": str(cls.env_file),
                "FAKE_FRITZ_LOG": str(cls.log),
                "FAKE_FRITZ_RC_FILE": str(cls.rc_file),
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
        self.settings = self.root / "_toolchain" / "fritz.json"
        if self.settings.exists():
            self.settings.unlink()
        if self.rc_file.exists():
            self.rc_file.unlink()
        if self.log.exists():
            self.log.unlink()
        self.env_file.write_text(
            "FRITZ_ADDR=192.0.2.1\n"
            "FRITZ_USER=testuser\n"
            "FRITZ_PASS=geheim-passwort\n",
            encoding="utf-8",
        )

    def calls(self):
        if not self.log.exists():
            return []
        return [
            json.loads(line)
            for line in self.log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

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
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            code = error.code
            error.close()
            return code, body


class FritzApiTest(FritzApiFixture):
    def test_status_is_available_and_hides_the_password(self):
        status, body = self.request("/api/fritz")

        self.assertEqual(status, 200, body)
        result = json.loads(body)
        self.assertFalse(result["automation"])
        self.assertTrue(result["configured"])
        self.assertTrue(result["ready"])
        self.assertNotIn("geheim-passwort", body)
        self.assertEqual(self.calls(), [], "Statusabfrage darf den Router-Helfer nicht starten")

    def test_api_switches_the_automation(self):
        status, body = self.request(
            "/api/fritz", {"action": "automation", "enabled": True}
        )

        self.assertEqual(status, 200, body)
        result = json.loads(body)
        self.assertTrue(result["ok"], body)
        self.assertTrue(result["fritz"]["automation"])
        self.assertTrue(json.loads(self.settings.read_text(encoding="utf-8"))["automation"])

        status, body = self.request(
            "/api/fritz", {"action": "automation", "enabled": False}
        )
        self.assertEqual(status, 200, body)
        self.assertFalse(json.loads(body)["fritz"]["automation"])

    def test_api_manual_reconnect_returns_the_helper_output(self):
        status, body = self.request("/api/fritz", {"action": "reconnect"})

        self.assertEqual(status, 200, body)
        result = json.loads(body)
        self.assertTrue(result["ok"], body)
        self.assertTrue(result["result"]["ok"])
        self.assertIn("neue IP: 203.0.113.9", result["result"]["output"])
        self.assertEqual(len(self.calls()), 1)

    def test_api_reports_a_failing_reconnect_without_claiming_success(self):
        self.rc_file.write_text("2\n", encoding="utf-8")

        status, body = self.request("/api/fritz", {"action": "reconnect"})

        self.assertEqual(status, 400, body)
        result = json.loads(body)
        self.assertFalse(result["ok"])
        self.assertFalse(result["result"]["ok"])
        self.assertIn("fehlgeschlagen", result["message"])

    def test_api_refuses_reconnect_without_configuration(self):
        self.env_file.unlink()

        status, body = self.request("/api/fritz", {"action": "reconnect"})

        self.assertEqual(status, 400, body)
        self.assertIn("nicht konfiguriert", json.loads(body)["message"])
        self.assertEqual(self.calls(), [])

    def test_api_rejects_non_boolean_automation_values(self):
        for value in ("true", 1, None):
            status, body = self.request(
                "/api/fritz", {"action": "automation", "enabled": value}
            )
            self.assertEqual(status, 400, body)
            self.assertIn("true oder false", json.loads(body)["message"])
            self.assertFalse(self.settings.exists())

    def test_api_requires_token_and_keeps_the_automation(self):
        status, _ = self.request(
            "/api/fritz", {"action": "automation", "enabled": True}, token=False
        )

        self.assertEqual(status, 403)
        self.assertFalse(self.settings.exists())

    def test_api_rejects_an_unknown_action_without_changing_anything(self):
        status, body = self.request("/api/fritz", {"action": "vielleicht"})

        self.assertEqual(status, 400, body)
        self.assertFalse(json.loads(body)["ok"])
        self.assertFalse(self.settings.exists())
        self.assertEqual(self.calls(), [])


FAKE_VIBE = '''#!/usr/bin/env python3
import os, sys
with open(os.environ["FAKE_VIBE_LOG"], "a", encoding="utf-8") as handle:
    handle.write(" ".join(sys.argv[1:]) + "\\n")
project_log = os.environ.get("FAKE_VIBE_PROJECT_LOG")
if project_log:
    with open(project_log, "a", encoding="utf-8") as handle:
        handle.write(os.environ.get("VIBE_PROJECT", "") + "\\n")
rc = int(os.environ.get("FAKE_VIBE_RC", "3"))
print("fritz auto rc=%d" % rc)
sys.exit(rc)
'''

FAKE_SLEEP = '''#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FAKE_SLEEP_LOG"
exit 0
'''


class RunnerFritzTest(unittest.TestCase):
    """Prüft, dass der Paket-Läufer die Automatik über ``vibe fritz auto`` nutzt."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        self.agents = self.root / "home" / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n"
            "AGENT=tester\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL="touch verify.done"\n'
            "MAX_RETRIES=0\n",
            encoding="utf-8",
        )
        (self.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] F1 Testpaket\n  Beschreibung: Test\n",
            encoding="utf-8",
        )
        (self.project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
        self.verify = self.root / "_toolchain" / "verify"
        self.verify.mkdir(parents=True)
        marker = self.verify / "verify-marker.txt"
        marker.write_text("ok\n", encoding="utf-8")
        digest = hashlib.sha256(marker.read_bytes()).hexdigest()
        home_config = self.root / "home" / ".config"
        home_config.mkdir(parents=True, exist_ok=True)
        (home_config / "schreibfuchs-verify.sha").write_text(
            f"{digest}  verify-marker.txt\n", encoding="utf-8"
        )
        self.tool_bin = support.install_runner(self.root / "_toolchain")
        (self.tool_bin / "vibe").write_text(FAKE_VIBE, encoding="utf-8")
        (self.tool_bin / "vibe").chmod(0o755)
        self.fakebin = support.install_fake_tools(self.root)
        sleep = self.fakebin / "sleep"
        sleep.write_text(FAKE_SLEEP, encoding="utf-8")
        sleep.chmod(0o755)
        support.init_repo(self.project)
        support.commit_all(self.project)
        self.vibe_log = self.root / "vibe.invocations"
        self.vibe_project_log = self.root / "vibe.projects"
        self.sleep_log = self.root / "sleep.invocations"

    def tearDown(self):
        self.tmp.cleanup()

    def run_runner(self, vibe_rc):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_") or key in (
                "SANDBOX",
                "SANDBOX_TOOLS",
                "MAX_PACKAGES",
                "MAX_RETRIES",
                "TYPE",
                "VERIFY_FULL",
                "VERIFY_PACKAGE",
                "AGENT",
                "TESTER",
                "REVIEWER",
            ):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(self.root),
                "HOME": str(self.root / "home"),
                "VIBE_STATE": str(self.root / "_toolchain"),
                "VIBE_INSTALL": str(self.root / "_toolchain"),
                "VIBE_RUNTIME": str(self.root / "_logs"),
                "VIBE_CONFIG_FILE": str(self.root / "home" / "config.json"),
                "VIBE_AGENTS_DIR": str(self.agents),
                "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
                "VIBE_LOGNAME": "proj",
                "VIBE_MAX_PACKAGES": "1",
                "VIBE_RETRY_DELAY": "0",
                "FAKE_MODE": "fail",
                "FAKE_CALLS": str(self.root / "opencode.calls"),
                "FAKE_COUNTER": str(self.root / "counter"),
                "FAKE_VIBE_LOG": str(self.vibe_log),
                "FAKE_VIBE_PROJECT_LOG": str(self.vibe_project_log),
                "FAKE_VIBE_RC": str(vibe_rc),
                "FAKE_SLEEP_LOG": str(self.sleep_log),
            }
        )
        return subprocess.run(
            ["bash", str(RUNNER), str(self.project)],
            cwd=str(self.project),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=90,
        )

    def test_runner_asks_the_automation_gate_and_waits_for_a_manual_ip_when_off(self):
        result = self.run_runner(vibe_rc=3)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            self.vibe_log.read_text(encoding="utf-8").splitlines(), ["fritz auto"]
        )
        self.assertFalse(self.sleep_log.exists())
        self.assertIn("fritz auto rc=3", result.stdout)

    def test_runner_reconnects_automatically_when_the_gate_allows_it(self):
        result = self.run_runner(vibe_rc=0)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            self.vibe_log.read_text(encoding="utf-8").splitlines(), ["fritz auto"]
        )
        self.assertEqual(
            self.sleep_log.read_text(encoding="utf-8").splitlines(), ["20"]
        )
        self.assertIn("fritz auto rc=0", result.stdout)

    def test_runner_tells_the_central_reconnect_which_project_continues(self):
        result = self.run_runner(vibe_rc=0)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            self.vibe_project_log.read_text(encoding="utf-8").splitlines(),
            [str(self.project)],
        )
        self.assertIn("fortgesetzt", result.stdout)


if __name__ == "__main__":
    unittest.main()
