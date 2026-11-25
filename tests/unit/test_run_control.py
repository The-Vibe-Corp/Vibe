"""Laufsteuerung: Sockets, Stoppen, Isolation, Signalverhalten und Keep-Changes.

Aufruf: python3 -m unittest tests.unit.test_run_control -v
"""


import hashlib
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"
RUNNER = BIN / "vibe-run.sh"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support


def load_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def clean_env(root, home, **extra):
    """Isolierte Umgebung ohne persönliche VIBE-, Sandbox- oder Prüfwerte."""
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
            "HOME": str(home),
            "VIBE_NO_CONTAINER": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    env.update({key: str(value) for key, value in extra.items()})
    return env


class CliFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.project = self.make_project("proj")
        # Persönliche Pfad-, Profil- und Prüfwerte des Aufrufers dürfen den
        # Testlauf nicht beeinflussen: sonst schreibt der Test in die echte
        # Installation oder Laufzeit.
        inherited = {
            key: os.environ.get(key)
            for key in list(os.environ)
            if key.startswith("VIBE") or key.startswith("VERIFY") or key in ("HOME", "PATH")
        }
        self.saved = inherited
        for key in inherited:
            if key != "PATH":
                os.environ.pop(key, None)
        os.environ.update(
            {
                "HOME": str(self.home),
                "VIBE": str(self.root),
                "VIBE_NO_CONTAINER": "1",
            }
        )
        self.cli = load_module(CLI, "vibe_run_control_under_test")
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for key in [key for key in os.environ if key.startswith("VIBE")]:
            os.environ.pop(key, None)
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def make_project(self, name, env_text="TYPE=generic\n"):
        project = self.root / name
        (project / ".vibe").mkdir(parents=True)
        (project / ".vibe" / "project.env").write_text(env_text, encoding="utf-8")
        if hasattr(self, "cli"):
            self.cli._pm.clear()
        return project

    def cli_env(self, **extra):
        return clean_env(self.root, self.home, **extra)

    def run_cli(self, *args, **extra):
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=str(self.root),
            env=self.cli_env(**extra),
            capture_output=True,
            text=True,
            timeout=60,
        )


class RunIdentityTest(CliFixture):
    def test_same_normalized_names_get_distinct_runs_logs_and_pause_flags(self):
        self.make_project("Alpha Beta")
        self.make_project("Alpha-Beta")
        self.cli._pm.clear()

        names = self.cli.projects()
        self.assertIn("Alpha Beta", names)
        self.assertIn("Alpha-Beta", names)

        first, second = "Alpha Beta", "Alpha-Beta"
        self.assertNotEqual(self.cli.run_key(first), self.cli.run_key(second))
        self.assertNotEqual(self.cli.sess(first), self.cli.sess(second))
        self.assertNotEqual(self.cli.logpath(first), self.cli.logpath(second))
        self.assertNotEqual(
            self.cli.logpath(first, "verify"), self.cli.logpath(second, "verify")
        )
        self.assertNotEqual(
            self.cli.pause_after_path(first), self.cli.pause_after_path(second)
        )

    def test_run_ids_are_unique_even_for_the_same_project_key(self):
        runs = load_module(BIN / "vibe_runs.py", "vibe_runs_ids_under_test")
        first = runs.new_run_id("proj")
        second = runs.new_run_id("proj")
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("proj-"), first)
        self.assertRegex(first, r"^[A-Za-z0-9_-]+$")


class RunRegistryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = Path(self.tmp.name) / "_logs"
        self.runs = load_module(BIN / "vibe_runs.py", "vibe_runs_registry_under_test")
        self.registry = self.runs.RunRegistry(str(self.runtime))

    def tearDown(self):
        self.tmp.cleanup()

    def start(self, project, name="proj", session="vibe-proj"):
        return self.registry.start(
            project=project,
            name=name,
            key=name,
            agent="tester",
            session=session,
            log=str(self.runtime / (name + ".log")),
            verify_log=str(self.runtime / (name + ".verify.log")),
        )

    def test_parallel_projects_keep_independent_records(self):
        first = self.start("/work/a", "a", "vibe-a")
        second = self.start("/work/b", "b", "vibe-b")

        self.assertNotEqual(first["id"], second["id"])
        self.registry.finish(first["id"], exit_code=0, state="finished")
        self.assertEqual(self.registry.get(first["id"])["state"], "finished")
        self.assertEqual(self.registry.get(second["id"])["state"], "running")
        self.assertEqual(self.registry.latest(project="/work/a")["id"], first["id"])
        self.assertEqual(self.registry.latest(project="/work/b")["id"], second["id"])

    def test_log_rotation_keeps_the_newest_archives(self):
        log = self.runtime / "proj.log"
        self.runtime.mkdir(parents=True)
        log.write_text("neu\n", encoding="utf-8")
        (self.runtime / "proj.log.1").write_text("alt-1\n", encoding="utf-8")
        (self.runtime / "proj.log.2").write_text("alt-2\n", encoding="utf-8")

        self.runs.rotate_log(str(log), max_bytes=1, keep=2)

        self.assertFalse(log.exists())
        self.assertEqual((self.runtime / "proj.log.1").read_text(), "neu\n")
        self.assertEqual((self.runtime / "proj.log.2").read_text(), "alt-1\n")
        self.assertFalse((self.runtime / "proj.log.3").exists())

    def test_small_logs_are_not_rotated(self):
        log = self.runtime / "proj.log"
        self.runtime.mkdir(parents=True)
        log.write_text("klein\n", encoding="utf-8")

        self.runs.rotate_log(str(log), max_bytes=4096, keep=2)

        self.assertEqual(log.read_text(encoding="utf-8"), "klein\n")
        self.assertFalse((self.runtime / "proj.log.1").exists())

    def test_direct_runner_key_stays_stable_for_the_same_project(self):
        self.start("/work/a/proj", "proj", "vibe-proj")

        self.assertEqual(
            self.runs.choose_key("/work/a/proj", str(self.runtime)), "proj"
        )

    def test_direct_runner_key_avoids_the_log_of_a_finished_foreign_run(self):
        record = self.start("/work/a/proj", "proj", "vibe-proj")
        self.registry.finish(record["id"], exit_code=0, state="finished")

        key = self.runs.choose_key("/work/b/proj", str(self.runtime))

        self.assertNotEqual(key, "proj")
        self.assertTrue(key.startswith("proj-"), key)
        self.assertRegex(key, r"^[A-Za-z0-9_-]+$")


class VerifyAdapterTest(CliFixture):
    def test_generic_project_is_checked_without_android_files(self):
        (self.project / ".vibe" / "project.env").write_text(
            'TYPE=generic\nVERIFY_QUICK="exit 0"\n', encoding="utf-8"
        )
        self.cli._pm.clear()

        result = self.run_cli("verify", "proj", "quick")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.root / "_toolchain" / "verify").exists())

    def test_missing_check_command_is_a_configuration_error(self):
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nVERIFY_QUICK=\"\"\n", encoding="utf-8"
        )
        self.cli._pm.clear()

        result = self.run_cli("verify", "proj", "quick")

        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("Keine Prüfbefehle", result.stderr)

    def test_todo_placeholder_is_not_a_successful_check(self):
        (self.project / ".vibe" / "project.env").write_text(
            'TYPE=generic\nVERIFY_QUICK="echo TODO"\n', encoding="utf-8"
        )
        self.cli._pm.clear()

        result = self.run_cli("verify", "proj", "quick")

        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("Platzhalter", result.stderr)

    def test_failing_check_returns_its_real_exit_code(self):
        (self.project / ".vibe" / "project.env").write_text(
            'TYPE=generic\nVERIFY_QUICK="exit 7"\n', encoding="utf-8"
        )
        self.cli._pm.clear()

        result = self.run_cli("verify", "proj", "quick")

        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)

    def test_android_uses_project_command_and_external_script_only_as_fallback(self):
        verify_dir = self.root / "_toolchain" / "verify"
        verify_dir.mkdir(parents=True)
        (verify_dir / "verify.sh").write_text("exit 0\n", encoding="utf-8")
        android = self.make_project(
            "android-proj", "TYPE=android\nVERIFY_QUICK=\"\"\n"
        )
        self.cli._pm.clear()

        command = self.cli.verify_command("android-proj", "quick")
        self.assertIn(str(verify_dir / "verify.sh"), command)
        self.assertIn(str(android), command)

        (android / ".vibe" / "project.env").write_text(
            'TYPE=android\nVERIFY_QUICK="exit 0"\n', encoding="utf-8"
        )
        self.cli._pm.clear()
        self.assertEqual(self.cli.verify_command("android-proj", "quick"), "exit 0")

    def test_generic_never_silently_uses_the_android_acceptance_script(self):
        verify_dir = self.root / "_toolchain" / "verify"
        verify_dir.mkdir(parents=True)
        (verify_dir / "verify.sh").write_text("exit 0\n", encoding="utf-8")

        result = self.run_cli("verify", "proj", "quick")

        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("Keine Prüfbefehle", result.stderr)


class RunStateAndStopTest(CliFixture):
    def state_for(self, record, live):
        with mock.patch.object(self.cli, "tmux_has_session", return_value=live):
            return self.cli.run_state("proj")

    def test_ended_process_is_not_reported_as_running(self):
        record = self.cli.run_registry().start(
            project=self.cli._real(self.project),
            name="proj",
            key="proj",
            agent="tester",
            session="vibe-proj",
            log=self.cli.logpath("proj"),
            verify_log=self.cli.logpath("proj", "verify"),
        )

        live = self.state_for(record, True)
        ended = self.state_for(record, False)

        self.assertTrue(live["running"])
        self.assertEqual(live["run_id"], record["id"])
        self.assertEqual(live["agent"], "tester")
        self.assertTrue(live["started"])
        self.assertFalse(ended["running"])
        self.assertEqual(ended["run_id"], record["id"])
        self.assertEqual(ended["state"], "ended")

    def test_a_foreign_record_with_the_same_key_is_not_this_projects_run(self):
        self.cli.run_registry().start(
            project="/irgendwo/anders/proj",
            name="proj",
            key="proj",
            agent="fremd",
            session="vibe-proj",
            log=self.cli.logpath("proj"),
            verify_log=self.cli.logpath("proj", "verify"),
        )

        with mock.patch.object(self.cli, "tmux_has_session", return_value=True):
            state = self.cli.run_state("proj")

        self.assertIsNone(state["run_id"])
        self.assertEqual(state["agent"], "")

    def test_stop_only_kills_the_selected_run(self):
        other = self.make_project("other")
        first = self.cli.run_registry().start(
            project=self.cli._real(self.project),
            name="proj",
            key="proj",
            agent="tester",
            session="vibe-proj",
            log=self.cli.logpath("proj"),
            verify_log=self.cli.logpath("proj", "verify"),
        )
        second = self.cli.run_registry().start(
            project=self.cli._real(other),
            name="other",
            key="other",
            agent="tester",
            session="vibe-other",
            log=self.cli.logpath("other"),
            verify_log=self.cli.logpath("other", "verify"),
        )
        calls = []

        def record_run(argv, **kwargs):
            calls.append(list(argv))
            return 0, ""

        with mock.patch.object(self.cli, "tmux_has_session", return_value=True):
            with mock.patch.object(self.cli, "run", side_effect=record_run):
                self.cli.cmd_stop("proj", first["id"])

        killed = [call for call in calls if "kill-session" in call]
        self.assertEqual(len(killed), 1, calls)
        self.assertIn(first["session"], killed[0])
        self.assertNotIn(second["session"], killed[0])
        self.assertEqual(self.cli.run_registry().get(first["id"])["state"], "stopped")
        self.assertEqual(self.cli.run_registry().get(second["id"])["state"], "running")

    def test_stop_refuses_an_already_finished_run(self):
        record = self.cli.run_registry().start(
            project=self.cli._real(self.project),
            name="proj",
            key="proj",
            agent="tester",
            session="vibe-proj",
            log=self.cli.logpath("proj"),
            verify_log=self.cli.logpath("proj", "verify"),
        )
        self.cli.run_registry().finish(record["id"], exit_code=0, state="finished")
        calls = []

        with mock.patch.object(self.cli, "tmux_has_session", return_value=True):
            with mock.patch.object(
                self.cli, "run", side_effect=lambda argv, **kw: calls.append(argv) or (0, "")
            ):
                self.cli.cmd_stop("proj", record["id"])

        self.assertFalse([call for call in calls if "kill-session" in call])
        self.assertEqual(
            self.cli.run_registry().get(record["id"])["state"], "finished"
        )

    def test_stop_refuses_a_run_id_of_another_project(self):
        other = self.make_project("other")
        self.cli.run_registry().start(
            project=self.cli._real(self.project),
            name="proj",
            key="proj",
            agent="tester",
            session="vibe-proj",
            log=self.cli.logpath("proj"),
            verify_log=self.cli.logpath("proj", "verify"),
        )
        foreign = self.cli.run_registry().start(
            project=self.cli._real(other),
            name="other",
            key="other",
            agent="tester",
            session="vibe-other",
            log=self.cli.logpath("other"),
            verify_log=self.cli.logpath("other", "verify"),
        )
        calls = []

        with mock.patch.object(self.cli, "tmux_has_session", return_value=True):
            with mock.patch.object(
                self.cli, "run", side_effect=lambda argv, **kw: calls.append(argv) or (0, "")
            ):
                with self.assertRaises(SystemExit) as caught:
                    self.cli.cmd_stop("proj", foreign["id"])

        self.assertIn("gehört nicht", str(caught.exception.code))
        self.assertFalse([call for call in calls if "kill-session" in call])


FAKE_VIBE = '''#!/usr/bin/env python3
import os, sys
with open(os.environ["VIBE_FAKE_FRITZ"], "a", encoding="utf-8") as handle:
    handle.write("fritz auto\\n")
print("Fritzbox-Automatik ist aus")
sys.exit(3)
'''


class RunnerV015Test(unittest.TestCase):
    """Führt den echten Läufer mit Attrappen für opencode und Router aus."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        self.verify = self.install / "verify"
        self.verify.mkdir()
        self.runtime = self.root / "_logs"
        self.project = self.root / "proj"
        self.project.mkdir()
        (self.tool_bin / "vibe").write_text(FAKE_VIBE, encoding="utf-8")
        (self.tool_bin / "vibe").chmod(0o755)
        self.fakebin = support.install_fake_tools(self.root)
        self.calls = self.root / "opencode.calls"
        self.counter = self.root / "counter"
        self.fritz = self.root / "fritz.calls"

    def tearDown(self):
        self.tmp.cleanup()

    def write_project(self, verify, retries):
        (self.project / ".vibe").mkdir(parents=True, exist_ok=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n"
            "AGENT=tester\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            f'VERIFY_FULL="{verify}"\n'
            f"MAX_RETRIES={retries}\n",
            encoding="utf-8",
        )
        # GH-48: ein offenes Ticket im Speicher statt FEEDBACK.md. .vibe ist
        # Laufzeitstand und wird nicht versioniert.
        (self.project / ".gitignore").write_text(".vibe/\n", encoding="utf-8")
        support.write_ticket_store(self.project, [support.ticket_record(
            "F1", "Testpaket", type="feedback", description="Test")])

    def run_runner(
        self, verify="true", retries=2, opencode_rc=0, packages=1
    ):
        self.write_project(verify, retries)
        if not (self.project / ".git").exists():
            support.init_repo(self.project)
        support.commit_all(self.project, "Teststand")
        env = clean_env(
            self.root,
            self.home,
            VIBE_INSTALL=str(self.install),
            VIBE_RUNTIME=str(self.runtime),
            VIBE_AGENTS_DIR=str(self.agents),
            VIBE_MAX_PACKAGES=str(packages),
            VIBE_RETRY_DELAY="0",
            FAKE_CALLS=str(self.calls),
            FAKE_COUNTER=str(self.counter),
            FAKE_MODE="fail" if opencode_rc else "complete",
            VIBE_FAKE_FRITZ=str(self.fritz),
            PATH=str(self.fakebin) + os.pathsep + os.environ.get("PATH", ""),
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

    def log(self, name="proj.log"):
        path = self.runtime / name
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def test_generic_run_works_without_android_acceptance_files(self):
        result = self.run_runner(verify="printf 'verify-ok\\n'")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.verify / "verify.sh").exists())
        self.assertFalse((self.home / ".config" / "schreibfuchs-verify.sha").exists())
        # Der Lauf hat wirklich ein Arbeitspaket ausgeführt; ein Abbruch vor der
        # Schleife würde sonst ebenfalls mit Exit 0 enden.
        self.assertIn("Arbeitspaket F1", self.log())
        self.assertEqual(len(self.calls.read_text(encoding="utf-8").splitlines()), 1)
        self.assertIn("FERTIG", self.log())

    def test_runner_writes_a_separate_verification_log(self):
        result = self.run_runner(verify="printf 'verify-ok\\n'")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Arbeitspaket F1", self.log())
        self.assertIn("=== Abschlussprüfung ===", self.log())
        self.assertIn("verify-ok", self.log())
        self.assertIn("verify-ok", self.log("proj.verify.log"))

    def test_retry_limit_stops_repeating_the_same_package(self):
        result = self.run_runner(verify="true", retries=1, opencode_rc=1, packages=4)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Arbeitspaket F1", self.log())
        self.assertEqual(len(self.calls.read_text(encoding="utf-8").splitlines()), 2)
        self.assertIn("Überspringe F1 nach 2 Versuchen", self.log())
        self.assertIn("1 Wiederholungen", self.log())

    def test_failed_final_check_returns_its_exit_code(self):
        result = self.run_runner(verify="exit 9")

        self.assertEqual(result.returncode, 9, result.stdout + result.stderr)


class RunsCommandTest(CliFixture):
    """Abnahme V-024: Registereinträge anzeigen und verwaiste Einträge aufräumen."""

    def setUp(self):
        super().setUp()
        self.fakebin = self.root / "fakebin"
        self.fakebin.mkdir()
        self.sessions_file = self.root / "tmux-sessions.txt"
        self.sessions_file.write_text("", encoding="utf-8")
        self.calls_file = self.root / "tmux-calls.txt"
        self.calls_file.write_text("", encoding="utf-8")
        tmux = self.fakebin / "tmux"
        tmux.write_text(
            "#!/bin/sh\n"
            'printf \'%s\\n\' "$*" >> "$FAKE_TMUX_CALLS"\n'
            'if [ "$1" = "-L" ]; then shift 2; fi\n'
            'if [ "$1" = "has-session" ]; then\n'
            '  if [ -n "$FAKE_TMUX_HAS_SESSION_RC" ]; then\n'
            '    exit "$FAKE_TMUX_HAS_SESSION_RC"\n'
            "  fi\n"
            '  name=""\n'
            '  prev=""\n'
            '  for arg in "$@"; do\n'
            '    if [ "$prev" = "-t" ]; then name="$arg"; fi\n'
            '    prev="$arg"\n'
            "  done\n"
            '  if [ -n "$name" ] && grep -Fxq -- "$name" "$FAKE_TMUX_SESSIONS" 2>/dev/null; then\n'
            "    exit 0\n"
            "  fi\n"
            "  exit 1\n"
            "fi\n"
            'if [ "$1" = "kill-session" ]; then\n'
            "  exit 0\n"
            "fi\n"
            "exit 1\n",
            encoding="utf-8",
        )
        tmux.chmod(0o755)

    def live_sessions(self, *names):
        self.sessions_file.write_text("\n".join(names) + ("\n" if names else ""), encoding="utf-8")

    def record(self, run_id, state="running", session="", project=None, name="proj", key="proj"):
        return {
            "id": run_id,
            "project": str(project if project is not None else self.project),
            "name": name,
            "key": key,
            "agent": "tester",
            "session": session,
            "log": "",
            "verify_log": "",
            "state": state,
            "exit_code": None,
        }

    def runs_path(self):
        return self.root / "_logs" / "runs.json"

    def write_runs(self, records):
        self.runs_path().parent.mkdir(parents=True, exist_ok=True)
        self.runs_path().write_text(
            json.dumps({"runs": records}, indent=1), encoding="utf-8"
        )

    def read_runs(self):
        data = json.loads(self.runs_path().read_text(encoding="utf-8"))
        return {record["id"]: record for record in data.get("runs", [])}

    def run_cli_with_tmux(self, *args, **extra):
        env = {
            "PATH": str(self.fakebin) + os.pathsep + os.environ.get("PATH", ""),
            "FAKE_TMUX_SESSIONS": str(self.sessions_file),
            "FAKE_TMUX_CALLS": str(self.calls_file),
        }
        env.update(extra)
        return self.run_cli(*args, **env)

    def tmux_calls(self):
        return [
            line
            for line in self.calls_file.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def line_for(self, output, run_id):
        for line in output.splitlines():
            if run_id in line:
                return line
        self.fail(f"Registereintrag {run_id} fehlt in der Ausgabe:\n{output}")

    def test_runs_list_shows_state_session_status_and_project_path_without_changes(self):
        missing_project = self.root / "nicht-mehr-da" / "proj"
        self.write_runs(
            [
                self.record("live-1", "running", "vibe-proj", self.project),
                self.record("orphan-1", "running", "vibe-weg", missing_project),
                self.record("done-1", "finished", "vibe-fertig", self.project),
            ]
        )
        self.live_sessions("vibe-proj")
        before = self.runs_path().read_bytes()

        result = self.run_cli_with_tmux("runs", "list")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.runs_path().read_bytes(), before, "runs list darf nichts ändern")

        live_line = self.line_for(result.stdout, "live-1")
        orphan_line = self.line_for(result.stdout, "orphan-1")
        done_line = self.line_for(result.stdout, "done-1")

        self.assertIn("running", live_line)
        self.assertIn("finished", done_line)
        self.assertIn(str(self.project), live_line)
        self.assertIn(str(missing_project), orphan_line)
        self.assertIn("verwaist", orphan_line.lower())
        self.assertNotIn("verwaist", live_line.lower())
        self.assertRegex(live_line, r"(vibe-proj|läuft|aktiv|vorhanden)")

    def test_runs_without_argument_lists_entries_too(self):
        missing_project = self.root / "weg" / "proj"
        self.write_runs(
            [self.record("orphan-1", "running", "vibe-weg", missing_project)]
        )
        before = self.runs_path().read_bytes()

        result = self.run_cli_with_tmux("runs")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.runs_path().read_bytes(), before, "runs darf nichts ändern")
        self.assertIn("orphan-1", result.stdout)
        self.assertIn("verwaist", self.line_for(result.stdout, "orphan-1").lower())

    def test_prune_marks_only_orphaned_live_records_ended(self):
        records = [
            self.record("orphan-running", "running", "vibe-weg-1", self.root / "weg-1" / "proj"),
            self.record("orphan-starting", "starting", "vibe-weg-2", self.root / "weg-2" / "proj"),
            self.record("live", "running", "vibe-live", self.project),
            self.record("done", "finished", "vibe-fertig", self.project),
            self.record("stopped", "stopped", "vibe-gestoppt", self.project),
            self.record("already-ended", "ended", "vibe-weg-3", self.root / "weg-3" / "proj"),
        ]
        before = {record["id"]: dict(record) for record in records}
        self.write_runs(records)
        self.live_sessions("vibe-live")

        result = self.run_cli_with_tmux("runs", "prune")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        runs = self.read_runs()
        self.assertEqual(runs["orphan-running"]["state"], "ended")
        self.assertEqual(runs["orphan-starting"]["state"], "ended")
        for unchanged in ("live", "done", "stopped", "already-ended"):
            self.assertEqual(
                runs[unchanged], before[unchanged], f"{unchanged} darf unverändert bleiben"
            )
        calls = self.tmux_calls()
        self.assertFalse(
            [call for call in calls if "kill-session" in call],
            f"prune darf niemals Sitzungen beenden: {calls}",
        )

    def test_prune_works_when_the_project_directory_is_gone(self):
        missing_project = self.root / "verschwunden" / "proj"
        self.assertFalse(missing_project.exists())
        self.write_runs(
            [self.record("orphan-weg", "running", "vibe-weg", missing_project)]
        )

        result = self.run_cli_with_tmux("runs", "prune")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.read_runs()["orphan-weg"]["state"], "ended")
        self.assertFalse(
            [call for call in self.tmux_calls() if "kill-session" in call]
        )

    def test_runs_list_marks_an_unverifiable_session_not_as_orphaned(self):
        self.write_runs(
            [self.record("unklar-1", "running", "vibe-unklar", self.project)]
        )
        before = self.runs_path().read_bytes()

        result = self.run_cli_with_tmux(
            "runs", "list", FAKE_TMUX_HAS_SESSION_RC="2"
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.runs_path().read_bytes(), before, "runs list darf nichts ändern")
        line = self.line_for(result.stdout, "unklar-1")
        self.assertIn("nicht prüfbar", line.lower())
        self.assertNotIn("verwaist", line.lower())

    def test_prune_keeps_unverifiable_records_and_reports_them(self):
        record = self.record("unklar-1", "running", "vibe-unklar", self.project)
        self.write_runs([record])

        result = self.run_cli_with_tmux(
            "runs", "prune", FAKE_TMUX_HAS_SESSION_RC="2"
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            self.read_runs()["unklar-1"],
            record,
            "ein nicht prüfbarer Eintrag darf nicht als ended markiert werden",
        )
        line = self.line_for(result.stdout, "unklar-1")
        self.assertIn("nicht prüfbar", line.lower())
        summary = [
            candidate
            for candidate in result.stdout.splitlines()
            if "unklar-1" not in candidate and "nicht prüfbar" in candidate.lower()
        ]
        self.assertTrue(summary, f"Zusammenfassung fehlt:\n{result.stdout}")
        self.assertTrue(
            any(re.search(r"\b1\b", candidate) for candidate in summary),
            f"Zusammenfassung muss den Eintrag als nicht prüfbar zählen:\n{result.stdout}",
        )
        self.assertFalse(
            [call for call in self.tmux_calls() if "kill-session" in call]
        )

    def test_prune_reports_records_without_a_session_and_keeps_them(self):
        record = self.record("ohne-sitzung", "running", "", self.project)
        self.write_runs([record])

        result = self.run_cli_with_tmux("runs", "prune")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            self.read_runs()["ohne-sitzung"],
            record,
            "ein Eintrag ohne Sitzungsangabe ist nicht prüfbar und darf nicht verändert werden",
        )
        line = self.line_for(result.stdout, "ohne-sitzung")
        self.assertIn("sitzung", line.lower())
        self.assertFalse(
            [call for call in self.tmux_calls() if "kill-session" in call]
        )


class FritzGateTest(CliFixture):
    def test_no_router_reconnect_without_an_explicit_automation_setting(self):
        self.assertFalse(self.cli.fritz_automation())
        with mock.patch.object(self.cli, "fritz_reconnect") as reconnect:
            outcome = self.cli.fritz_auto()
        self.assertFalse(outcome["ran"])
        reconnect.assert_not_called()


# ===========================================================================
# Unabhängige Abnahme: Läufe gegen fremde tmux-Aufräumaktionen sichern
# ===========================================================================

import importlib.machinery
import importlib.util
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

RUNS = BIN / "vibe_runs.py"
SETUP = REPO / "scripts" / "setup-vibe.py"

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(BIN))
import runner_support as support

DASHBOARD_SESSIONS = ("vibe-ui", "vibe-ui-dev", "vibe-server", "vibe-server-dev")


def load_cli_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def isolated_env(root, home, state, install, runtime, profile="prod"):
    """Umgebung ohne persönliche VIBE-, Sandbox- oder Prüfwerte."""
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
    if profile != "prod":
        env["VIBE_PROFILE"] = profile
    return env


class CliModuleFixture(unittest.TestCase):
    """Lädt ``bin/vibe`` isoliert; alle Pfade liegen in temporären Ordnern."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.install = self.root / "_toolchain"
        self.runtime = self.root / "_logs"
        self.state = self.root / "_state"
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        self.saved_environ = {
            key: os.environ.get(key)
            for key in list(os.environ)
            if key.startswith("VIBE") or key in (
                "VIBE",
                "HOME",
                "XDG_CONFIG_HOME",
                "PYTHONDONTWRITEBYTECODE",
            )
        }
        self.cli = self.load_cli()

    def tearDown(self):
        for key in list(os.environ):
            if key.startswith("VIBE"):
                os.environ.pop(key, None)
        for key in ("HOME", "XDG_CONFIG_HOME", "PYTHONDONTWRITEBYTECODE"):
            os.environ.pop(key, None)
        for key, value in self.saved_environ.items():
            if value is not None:
                os.environ[key] = value
        self.tmp.cleanup()

    def load_cli(self, profile="prod", name="vibe_v026_under_test"):
        env = isolated_env(
            self.root, self.home, self.state, self.install, self.runtime, profile
        )
        old = dict(os.environ)
        try:
            os.environ.clear()
            os.environ.update(env)
            return load_cli_module(CLI, name)
        finally:
            os.environ.clear()
            os.environ.update(old)

    def cli_env(self, **extra):
        env = isolated_env(
            self.root, self.home, self.state, self.install, self.runtime
        )
        env.update({key: str(value) for key, value in extra.items()})
        return env

    def run_cli(self, *args, **extra):
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=str(self.root),
            env=self.cli_env(**extra),
            capture_output=True,
            text=True,
            timeout=60,
        )


class RunSessionSocketTest(CliModuleFixture):
    """Start, Status, Anhängen und Stoppen nutzen denselben Laufsocket."""

    def invoke_cmd_run(self, module=None):
        module = module or self.cli
        calls = []

        class Registry:
            def start(self, **kwargs):
                calls.append(["register", kwargs])
                return {"id": "proj-lauf"}

            def finish(self, *args, **kwargs):
                return None

        def fake_run(argv, **kwargs):
            calls.append(list(argv))
            return 0, ""

        values = {
            "run": fake_run,
            "tmux_has": lambda name: False,
            "tmux_has_session": lambda name: False,
            "project_map": lambda: {"proj": str(self.project)},
            "ppath": lambda name: str(self.project),
            "is_init": lambda name: True,
            "pending_changes": lambda path: "",
            "changed_file": lambda path, name: False,
            "sandbox_status": lambda name: {"enabled": False},
            "pause_after_active": lambda name: False,
            "penv": lambda name: {},
            "vibe_agent_status": lambda: {
                "name": "",
                "model": "",
                "configured": False,
            },
            "require_agent": lambda agent: agent,
            "ensure_opencode_password": lambda: str(
                self.runtime / "opencode.password"
            ),
            "run_agent_selection": lambda name, agent: "",
            "run_registry": lambda: Registry(),
        }
        with mock.patch.multiple(module, **values), mock.patch.object(
            module.vibe_runs, "rotate_log", lambda *args, **kwargs: None
        ):
            module.cmd_run("proj", "tester", out=io.StringIO())
        return calls

    def new_session_call(self, calls):
        sessions = [call for call in calls if "new-session" in call]
        self.assertEqual(len(sessions), 1, calls)
        return sessions[0]

    def test_run_start_uses_a_dedicated_socket_named_like_the_session(self):
        calls = self.invoke_cmd_run()

        argv = self.new_session_call(calls)
        self.assertEqual(argv[0], "tmux", argv)
        self.assertEqual(argv[1:3], ["-L", "vibe-proj"], argv)
        self.assertIn("new-session", argv, argv)
        self.assertEqual(argv[argv.index("-s") + 1], "vibe-proj", argv)

    def test_dev_profile_appends_dev_to_session_and_socket(self):
        module = self.load_cli("dev", "vibe_v026_dev_under_test")
        self.assertEqual(module.PATHS.profile, "dev")
        self.assertEqual(module.sess("proj"), "vibe-proj-dev")

        argv = self.new_session_call(self.invoke_cmd_run(module))
        self.assertEqual(argv[1:3], ["-L", "vibe-proj-dev"], argv)
        self.assertEqual(argv[argv.index("-s") + 1], "vibe-proj-dev", argv)

    def test_status_checks_the_run_session_on_its_own_socket(self):
        calls = []

        class Registry:
            def latest(self, project=None):
                return None

        def fake_run(argv, **kwargs):
            calls.append(list(argv))
            return 0, ""

        with mock.patch.multiple(
            self.cli, run=fake_run, run_registry=lambda: Registry()
        ):
            state = self.cli.run_state("proj")

        self.assertTrue(state["running"], state)
        self.assertIn(
            ["tmux", "-L", "vibe-proj", "has-session", "-t", "vibe-proj"],
            calls,
            calls,
        )

    def test_attach_uses_the_same_socket(self):
        calls = []

        def fake_subprocess(argv, *args, **kwargs):
            calls.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, "", "")

        with mock.patch.object(self.cli, "tmux_has", lambda name: True):
            with mock.patch.object(
                self.cli.subprocess, "run", side_effect=fake_subprocess
            ):
                self.cli.cmd_attach("proj")

        self.assertEqual(
            calls,
            [["tmux", "-L", "vibe-proj", "attach", "-t", "vibe-proj"]],
        )

    def test_stop_kills_the_session_on_its_own_socket(self):
        registry = self.cli.run_registry()
        record = registry.start(
            project=str(self.project),
            name="proj",
            key="proj",
            agent="tester",
            session="vibe-proj",
            log=self.cli.logpath("proj"),
            verify_log=self.cli.logpath("proj", "verify"),
        )
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(list(argv))
            if "show-environment" in argv:
                return 0, "VIBE_MANAGED=run\n"
            if "kill-session" in argv:
                return 0, ""
            return 0, ""

        with mock.patch.multiple(
            self.cli,
            run=fake_run,
            project_map=lambda: {"proj": str(self.project)},
            tmux_has_session=lambda name: True,
        ):
            self.cli.cmd_stop("proj", record["id"])

        killed = [call for call in calls if "kill-session" in call]
        self.assertEqual(len(killed), 1, calls)
        self.assertEqual(
            killed[0],
            ["tmux", "-L", "vibe-proj", "kill-session", "-t", "vibe-proj"],
        )
        self.assertEqual(
            self.cli.run_registry().get(record["id"])["state"], "stopped"
        )


class RunStopIsolationRealTmuxTest(CliModuleFixture):
    """Ein echter ``vibe stop`` beendet nur den eigenen Lauf.

    Dashboard und ein zweiter Lauf liegen auf getrennten tmux-Servern; der
    Stopp des ersten Laufs darf weder den zweiten Lauf noch das Dashboard
    beenden.
    """

    def setUp(self):
        super().setUp()
        self.tmux_dir = self.root / "tmux"
        self.tmux_dir.mkdir()
        self.tmux_dir.chmod(0o700)
        self.tmux_env = {
            "PATH": os.environ.get("PATH", ""),
            "TMUX_TMPDIR": str(self.tmux_dir),
            "TERM": os.environ.get("TERM", "xterm"),
        }
        self.servers = []
        self.default_server = False

    def tearDown(self):
        for socket in self.servers:
            self.tmux("-L", socket, "kill-server")
        if self.default_server:
            self.tmux("kill-server")
        super().tearDown()

    def tmux(self, *args):
        return subprocess.run(
            ["tmux", *args],
            env=self.tmux_env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def start_session(self, socket, session, marker):
        self.servers.append(socket)
        result = self.tmux(
            "-L", socket, "new-session", "-d", "-s", session, "sleep 60"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.tmux(
            "-L", socket, "set-environment", "-t", session,
            self.cli.MANAGED_VAR, marker,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def start_default_session(self, session):
        self.default_server = True
        result = self.tmux("new-session", "-d", "-s", session, "sleep 60")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.tmux(
            "set-environment", "-t", session, self.cli.MANAGED_VAR, "ui"
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def alive(self, socket, session):
        args = ["-L", socket] if socket else []
        return (
            self.tmux(*args, "has-session", "-t", session).returncode == 0
        )

    def real_tmux(self, argv, **kwargs):
        result = subprocess.run(
            argv, env=self.tmux_env, capture_output=True, text=True, timeout=30
        )
        return result.returncode, (result.stdout + result.stderr).strip()

    def test_stopping_one_run_leaves_the_other_run_and_dashboard_alive(self):
        project = str(self.project.resolve())
        self.start_default_session("vibe-ui")
        self.start_session("vibe-eins", "vibe-eins", "run")
        self.start_session("vibe-zwei", "vibe-zwei", "run")
        registry = self.cli.run_registry()
        first = registry.start(
            project=project,
            name="proj",
            key="proj",
            agent="tester",
            session="vibe-eins",
            log=self.cli.logpath("proj"),
            verify_log=self.cli.logpath("proj", "verify"),
        )
        second = registry.start(
            project=project,
            name="proj",
            key="proj",
            agent="tester",
            session="vibe-zwei",
            log=self.cli.logpath("proj"),
            verify_log=self.cli.logpath("proj", "verify"),
        )

        with mock.patch.multiple(
            self.cli,
            run=self.real_tmux,
            project_map=lambda: {"proj": project},
        ):
            self.cli.cmd_stop("proj", first["id"])

        self.assertFalse(
            self.alive("vibe-eins", "vibe-eins"),
            "Der gestoppte Lauf lebt noch",
        )
        self.assertTrue(
            self.alive("vibe-zwei", "vibe-zwei"),
            "Der Stopp hat einen fremden Lauf beendet",
        )
        self.assertTrue(
            self.alive(None, "vibe-ui"),
            "Der Stopp hat das Dashboard beendet",
        )
        stored = self.cli.run_registry()
        self.assertEqual(stored.get(first["id"])["state"], "stopped")
        self.assertEqual(stored.get(second["id"])["state"], "running")


class RunsSocketTest(CliModuleFixture):
    """``vibe runs list`` und ``prune`` prüfen den Socket des Eintrags."""

    def setUp(self):
        super().setUp()
        self.fakebin = self.root / "fakebin"
        self.fakebin.mkdir()
        self.sessions_file = self.root / "tmux-sessions.txt"
        self.sessions_file.write_text("", encoding="utf-8")
        self.calls_file = self.root / "tmux-calls.txt"
        self.calls_file.write_text("", encoding="utf-8")
        tmux = self.fakebin / "tmux"
        tmux.write_text(
            "#!/bin/sh\n"
            'printf \'%s\\n\' "$*" >> "$FAKE_TMUX_CALLS"\n'
            'if [ "$1" = "-L" ]; then shift 2; fi\n'
            'if [ "$1" = "has-session" ]; then\n'
            '  if [ -n "$FAKE_TMUX_HAS_SESSION_RC" ]; then\n'
            '    exit "$FAKE_TMUX_HAS_SESSION_RC"\n'
            "  fi\n"
            '  name=""\n'
            '  prev=""\n'
            '  for arg in "$@"; do\n'
            '    if [ "$prev" = "-t" ]; then name="$arg"; fi\n'
            '    prev="$arg"\n'
            "  done\n"
            '  if [ -n "$name" ] && grep -Fxq -- "$name" "$FAKE_TMUX_SESSIONS" 2>/dev/null; then\n'
            "    exit 0\n"
            "  fi\n"
            "  exit 1\n"
            "fi\n"
            'if [ "$1" = "kill-session" ]; then exit 0; fi\n'
            "exit 1\n",
            encoding="utf-8",
        )
        tmux.chmod(0o755)
        self.project = self.root / "proj"
        self.project.mkdir(exist_ok=True)

    def live_sessions(self, *names):
        self.sessions_file.write_text(
            "\n".join(names) + ("\n" if names else ""), encoding="utf-8"
        )

    def record(self, run_id, state="running", session="", project=None):
        return {
            "id": run_id,
            "project": str(project if project is not None else self.project),
            "name": "proj",
            "key": "proj",
            "agent": "tester",
            "session": session,
            "log": "",
            "verify_log": "",
            "state": state,
            "exit_code": None,
        }

    def runs_path(self):
        return self.root / "_logs" / "runs.json"

    def write_runs(self, records):
        self.runs_path().parent.mkdir(parents=True, exist_ok=True)
        self.runs_path().write_text(
            json.dumps({"runs": records}, indent=1), encoding="utf-8"
        )

    def read_runs(self):
        data = json.loads(self.runs_path().read_text(encoding="utf-8"))
        return {record["id"]: record for record in data.get("runs", [])}

    def run_with_tmux(self, *args, **extra):
        env = {
            "PATH": str(self.fakebin) + os.pathsep + os.environ.get("PATH", ""),
            "FAKE_TMUX_SESSIONS": str(self.sessions_file),
            "FAKE_TMUX_CALLS": str(self.calls_file),
        }
        env.update(extra)
        return self.run_cli(*args, **env)

    def tmux_calls(self):
        return [
            line
            for line in self.calls_file.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def test_runs_list_checks_each_record_on_its_session_socket(self):
        self.write_runs(
            [self.record("live-1", "running", "vibe-proj", self.project)]
        )
        self.live_sessions("vibe-proj")

        result = self.run_with_tmux("runs", "list")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "-L vibe-proj has-session -t vibe-proj",
            self.tmux_calls(),
            self.tmux_calls(),
        )

    def test_runs_prune_marks_orphans_using_the_session_socket(self):
        self.write_runs(
            [self.record("orphan-1", "running", "vibe-weg", self.project)]
        )

        result = self.run_with_tmux("runs", "prune")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.read_runs()["orphan-1"]["state"], "ended")
        self.assertIn(
            "-L vibe-weg has-session -t vibe-weg",
            self.tmux_calls(),
            self.tmux_calls(),
        )


class SetupLockTest(unittest.TestCase):
    """Die Setup-Sperre prüft Laufsitzungen auf deren eigenem Socket."""

    @classmethod
    def setUpClass(cls):
        cls.setup = load_cli_module(SETUP, "setup_vibe_v026_under_test")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "_logs"
        self.runtime.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_setup_lock_uses_the_run_socket_and_keeps_dashboard_on_default(self):
        (self.runtime / "runs.json").write_text(
            json.dumps(
                {
                    "runs": [
                        {
                            "id": "lauf-1",
                            "state": "running",
                            "session": "vibe-proj",
                            "project": str(self.root / "proj"),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        calls = []

        def runner(command, **kwargs):
            calls.append(list(command))
            name = command[-1]
            code = 0 if name == "vibe-proj" else 1
            return subprocess.CompletedProcess(command, code, "", "")

        # Seit 67d53bc erwartet running_installation das Logverzeichnis, aus
        # dem runs.json gelesen wird (nicht mehr den Workspace).
        reasons = self.setup.running_installation(
            self.runtime, runner=runner, which=lambda name: "/fake/tmux"
        )

        self.assertTrue(
            any("lauf-1" in reason for reason in reasons), reasons
        )
        run_call = next(call for call in calls if "vibe-proj" in call)
        self.assertEqual(
            run_call[1:],
            ["-L", "vibe-proj", "has-session", "-t", "vibe-proj"],
            run_call,
        )
        for session in ("vibe-ui", "vibe-server"):
            call = next(call for call in calls if session in call)
            self.assertNotIn("-L", call, call)


class DefaultSocketTest(CliModuleFixture):
    """Dashboard und opencode-Server bleiben auf dem Standard-Server."""

    def test_dashboard_start_stays_on_the_default_server(self):
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(list(argv))
            return 0, ""

        (self.runtime).mkdir(parents=True, exist_ok=True)
        (self.runtime / "web.token").write_text("token\n", encoding="utf-8")
        with mock.patch.multiple(
            self.cli,
            run=fake_run,
            # AP13: Produktion ruft dashboard_health(bind, port).
            dashboard_health=lambda *args, **kwargs: None,
            port_in_use=lambda host, port: False,
            tmux_session_exists=lambda session: False,
            session_owned=lambda session, kind: True,
        ), mock.patch.object(self.cli.time, "sleep", lambda seconds: None), \
                mock.patch.object(self.cli.vibe_paths, "ensure", lambda *a, **k: None):
            self.cli.cmd_ui("start")

        sessions = [call for call in calls if "new-session" in call]
        self.assertEqual(len(sessions), 1, calls)
        self.assertNotIn("-L", sessions[0], sessions[0])

    def test_opencode_server_start_stays_on_the_default_server(self):
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(list(argv))
            return 0, ""

        with mock.patch.multiple(
            self.cli,
            run=fake_run,
            server_health=lambda: None,
            port_in_use=lambda host, port: False,
            tmux_session_exists=lambda session: False,
            session_owned=lambda session, kind: True,
            ensure_opencode_password=lambda: str(
                self.runtime / "opencode.password"
            ),
        ), mock.patch.object(self.cli.time, "sleep", lambda seconds: None), \
                mock.patch.object(
                    self.cli.vibe_opencode, "probe",
                    lambda: mock.Mock(checked=True, message="", version="2"),
                ), mock.patch.object(
                    self.cli.vibe_opencode, "server_command",
                    lambda port, info=None: ["opencode", "serve"],
                ):
            self.cli.cmd_server("start")

        sessions = [call for call in calls if "new-session" in call]
        self.assertEqual(len(sessions), 1, calls)
        self.assertNotIn("-L", sessions[0], sessions[0])


class RunnerCase(unittest.TestCase):
    """Basis für echte Läuferprozesse mit Attrappen für opencode und tmux."""

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
        self.project = self.root / "proj"
        support.init_repo(self.project)
        self.calls = self.root / "opencode.calls"
        self.counter = self.root / "counter"

    def tearDown(self):
        process = getattr(self, "process", None)
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
            process.wait(timeout=10)
        self.tmp.cleanup()

    def write_project(self, max_retries=0):
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

    def runner_env(self, fake_mode="complete", extra=None):
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
        if extra:
            env.update({key: str(value) for key, value in extra.items()})
        return env

    def registry(self):
        return load_cli_module(RUNS, "vibe_runs_v026_runner")


class RunnerSignalTest(RunnerCase):
    """HUP, TERM und INT beenden Register und Protokoll nachvollziehbar."""

    def wait_for_running_record(self, timeout=10):
        registry = self.registry().RunRegistry(str(self.runtime))
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.calls.exists() and self.calls.read_text(encoding="utf-8"):
                record = registry.latest(project=str(self.project.resolve()))
                if record and record.get("state") in ("starting", "running"):
                    return record
            time.sleep(0.05)
        self.fail("Der Läufer hat kein Arbeitspaket begonnen")

    def start_hanging_runner(self):
        self.write_project()
        env = self.runner_env("hang")
        self.process = subprocess.Popen(
            ["bash", str(RUNNER), str(self.project)],
            cwd=str(self.project),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        return self.wait_for_running_record()

    def log_text(self):
        path = self.runtime / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def assert_signal_logged(self, name, log, output):
        """Das Protokoll nennt das Signal in einer Abschlusszeile."""
        lines = [line for line in log.splitlines() if name in line]
        self.assertTrue(lines, output)
        self.assertTrue(
            any(
                token in line.lower()
                for line in lines
                for token in ("signal", "extern", "abbruch", "beendet", "empfangen")
            ),
            lines,
        )

    def assert_signal_case(self, signum, name):
        record = self.start_hanging_runner()
        try:
            os.killpg(self.process.pid, signum)
        except ProcessLookupError:
            pass
        output = None
        try:
            output = self.process.communicate(timeout=15)[0]
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except OSError:
                pass
            output = self.process.communicate()[0]
            self.fail("Der Läufer hat das Signal nicht beendet: " + (output or ""))

        log = self.log_text()
        self.assert_signal_logged(name, log, output)
        ended = self.registry().RunRegistry(str(self.runtime)).get(record["id"])
        self.assertIsNotNone(ended, record)
        self.assertEqual(ended["state"], "ended", ended)
        self.assertEqual(ended.get("note"), f"extern beendet (Signal {name})", ended)

    def test_hup_writes_log_line_and_ends_record(self):
        self.assert_signal_case(signal.SIGHUP, "HUP")

    def test_term_writes_log_line_and_ends_record(self):
        self.assert_signal_case(signal.SIGTERM, "TERM")

    def test_int_writes_log_line_and_ends_record(self):
        self.assert_signal_case(signal.SIGINT, "INT")

    def test_already_finished_run_stays_unchanged(self):
        record = self.start_hanging_runner()
        registry = self.registry().RunRegistry(str(self.runtime))
        registry.finish(record["id"], exit_code=0, state="finished")

        os.killpg(self.process.pid, signal.SIGTERM)
        try:
            output = self.process.communicate(timeout=15)[0]
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except OSError:
                pass
            output = self.process.communicate()[0]
            self.fail("Der Läufer hat das Signal nicht beendet: " + (output or ""))

        unchanged = registry.get(record["id"])
        self.assertEqual(unchanged["state"], "finished", unchanged)
        self.assertNotEqual(unchanged.get("note"), "extern beendet (Signal TERM)")


class OrphanCleanupTest(RunnerCase):
    """Ein neuer Lauf räumt nur verwaiste eigene Einträge auf."""

    def fake_tmux(self):
        fakebin = self.root / "fakebin"
        fakebin.mkdir(exist_ok=True)
        calls = self.root / "tmux.calls"
        calls.write_text("", encoding="utf-8")
        script = fakebin / "tmux"
        script.write_text(
            "#!/bin/sh\n"
            'printf \'%s\\n\' "$*" >> "$FAKE_TMUX_CALLS"\n'
            'if [ "$1" = "-L" ]; then shift 2; fi\n'
            'if [ "$1" = "has-session" ]; then\n'
            '  name=""\n'
            '  prev=""\n'
            '  for arg in "$@"; do\n'
            '    if [ "$prev" = "-t" ]; then name="$arg"; fi\n'
            '    prev="$arg"\n'
            "  done\n"
            '  if [ "$name" = "$FAKE_TMUX_UNVERIFIABLE" ]; then exit 2; fi\n'
            '  if grep -Fxq -- "$name" "$FAKE_TMUX_LIVE" 2>/dev/null; then exit 0; fi\n'
            "  exit 1\n"
            "fi\n"
            "exit 1\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return fakebin, calls

    def test_new_run_marks_only_orphans_of_its_own_project_ended(self):
        self.write_project()
        self.runtime.mkdir(exist_ok=True)
        project = str(self.project.resolve())
        foreign = str((self.root / "fremd").resolve())
        records = [
            {
                "id": "orphan-eigen",
                "project": project,
                "name": "proj",
                "key": "proj",
                "agent": "tester",
                "session": "vibe-weg",
                "log": "",
                "verify_log": "",
                "state": "running",
                "exit_code": None,
            },
            {
                "id": "lebt-eigen",
                "project": project,
                "name": "proj",
                "key": "proj",
                "agent": "tester",
                "session": "vibe-lebt",
                "log": "",
                "verify_log": "",
                "state": "running",
                "exit_code": None,
            },
            {
                "id": "orphan-fremd",
                "project": foreign,
                "name": "fremd",
                "key": "fremd",
                "agent": "tester",
                "session": "vibe-weg-fremd",
                "log": "",
                "verify_log": "",
                "state": "running",
                "exit_code": None,
            },
            {
                "id": "unklar-eigen",
                "project": project,
                "name": "proj",
                "key": "proj",
                "agent": "tester",
                "session": "vibe-unklar",
                "log": "",
                "verify_log": "",
                "state": "running",
                "exit_code": None,
            },
        ]
        before = {record["id"]: dict(record) for record in records}
        (self.runtime / "runs.json").write_text(
            json.dumps({"runs": records}, indent=1), encoding="utf-8"
        )
        fakebin, tmux_calls = self.fake_tmux()
        live = self.root / "tmux.live"
        live.write_text("vibe-lebt\n", encoding="utf-8")

        env = self.runner_env(
            "complete",
            {
                "PATH": str(fakebin)
                + os.pathsep
                + self.runner_env("complete")["PATH"],
                "FAKE_TMUX_CALLS": str(tmux_calls),
                "FAKE_TMUX_LIVE": str(live),
                "FAKE_TMUX_UNVERIFIABLE": "vibe-unklar",
            },
        )
        result = subprocess.run(
            ["bash", str(RUNNER), str(self.project)],
            cwd=str(self.project),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=90,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        registry = self.registry().RunRegistry(str(self.runtime))
        runs = {record["id"]: record for record in registry.all()}
        self.assertEqual(runs["orphan-eigen"]["state"], "ended", runs["orphan-eigen"])
        self.assertEqual(
            runs["orphan-eigen"].get("note"), "extern beendet (Sitzung fehlt)"
        )
        for unchanged in ("lebt-eigen", "orphan-fremd", "unklar-eigen"):
            self.assertEqual(
                runs[unchanged], before[unchanged], f"{unchanged} wurde verändert"
            )
        own_new = [
            record
            for run_id, record in runs.items()
            if run_id not in before and record.get("project") == project
        ]
        self.assertTrue(own_new, "Der neue Lauf fehlt im Register")
        self.assertIn(
            "-L vibe-weg has-session -t vibe-weg",
            tmux_calls.read_text(encoding="utf-8").splitlines(),
            tmux_calls.read_text(encoding="utf-8"),
        )


class RegistryNoteTest(unittest.TestCase):
    """``finish`` nimmt ein optionales ``--note`` auf."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = Path(self.tmp.name) / "_logs"
        self.runs = load_cli_module(RUNS, "vibe_runs_v026_note")
        self.registry = self.runs.RunRegistry(str(self.runtime))

    def tearDown(self):
        self.tmp.cleanup()

    def start(self):
        return self.registry.start(
            project="/work/proj",
            name="proj",
            key="proj",
            agent="tester",
            session="vibe-proj",
            log=str(self.runtime / "proj.log"),
            verify_log=str(self.runtime / "proj.verify.log"),
        )

    def finish(self, run_id, *extra):
        return subprocess.run(
            [
                sys.executable,
                str(RUNS),
                "finish",
                "--runtime",
                str(self.runtime),
                "--id",
                run_id,
                "--state",
                "ended",
                *extra,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_finish_without_note_omits_the_field(self):
        record = self.start()

        result = self.finish(record["id"])

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        stored = self.registry.get(record["id"])
        self.assertEqual(stored["state"], "ended")
        self.assertNotIn("note", stored, stored)

    def test_finish_with_note_stores_it(self):
        record = self.start()

        result = self.finish(
            record["id"], "--note", "extern beendet (Signal TERM)"
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        stored = self.registry.get(record["id"])
        self.assertEqual(stored["state"], "ended")
        self.assertEqual(stored.get("note"), "extern beendet (Signal TERM)")


# ===========================================================================
# Unabhängige Tests /1: Stopp beendet den Agenten wirklich
# ===========================================================================

import importlib.machinery
import importlib.util
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "runner_fixtures"

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(BIN))
import runner_support as support

# Großzügige Obergrenze: der Stopp muss „innerhalb weniger Sekunden“ greifen.
STOP_TIMEOUT = 12.0


def load_stop_module(path, name):
    """Lädt ein Python-Modul aus einer Datei ohne Seiteneffekte auf sys.path."""
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def pid_alive(pid):
    """True, solange der Prozess existiert und nicht Zombie/beendet ist."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return False
    fields = stat.rsplit(") ", 1)[-1].split()
    return bool(fields) and fields[0] not in ("Z", "X", "x")


def extract_shell_function(path, name):
    """Liest eine Funktion aus einem Shell-Skript (Header bis schließende Klammer).

    Die fokussierten Rennfenster-Fälle führen die echte Funktion des
    Läufers aus; eine kopierte Nachbildung würde das geprüfte Verhalten
    nur behaupten, nicht prüfen.
    """
    text = path.read_text(encoding="utf-8")
    header = name + "() {"
    start = text.index(header)
    end = text.index("\n}", start)
    return text[start:end + 2]


class RunnerProcessFixture(unittest.TestCase):
    """Startet den echten Läufer mit einem signalignorierenden Harness."""

    ignore = "HUP,TERM"

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
        self.project = self.root / "proj"
        support.init_repo(self.project)
        self.fixture = self.root / "fixture"
        self.fixture.mkdir()
        self.fakebin = support.install_fake_tools(self.root)
        self.install_harness()
        self.process = None
        self.pgid = None
        self.write_project()

    def tearDown(self):
        process = getattr(self, "process", None)
        if process is not None and process.poll() is None:
            try:
                os.killpg(self.pgid or process.pid, signal.SIGKILL)
            except OSError:
                pass
        if process is not None:
            try:
                process.communicate(timeout=10)
            except (subprocess.TimeoutExpired, ValueError, OSError):
                pass
        for pid in self.recorded_pids().values():
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        self.tmp.cleanup()

    def install_harness(self):
        """Legt den signalignorierenden Harness als ``opencode`` in den PATH."""
        for name in ("b11_harness.py", "b11_child.py", "b11_grandchild.py"):
            target = self.fakebin / name
            target.write_text(
                (FIXTURES / name).read_text(encoding="utf-8"), encoding="utf-8"
            )
            target.chmod(0o755)
        opencode = self.fakebin / "opencode"
        opencode.write_text(
            (FIXTURES / "b11_harness.py").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        opencode.chmod(0o755)

    def write_project(self):
        """Projekt mit genau einem offenen Arbeitspaket und erlaubten Agenten."""
        support.write_project(
            self.project,
            "TYPE=generic\n"
            "AGENT=tester\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL="true"\n'
            "MAX_RETRIES=0\n",
            feedback=[support.ticket_record(
                "F1", "Erstes Paket", type="feedback",
                description="Test")],
        )
        support.commit_all(self.project, "Ausgangsstand")

    def isolated_env(self):
        """Umgebung ohne persönliche VIBE-, Sandbox- oder Prüfwerte."""
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE_") or key.startswith("SANDBOX") or key in (
                "VIBE",
                "AGENT",
                "TYPE",
                "VERIFY_QUICK",
                "VERIFY_FULL",
                "B11_FIXTURE_DIR",
                "B11_IGNORE",
                "B11_CHILD",
                "B11_EXIT_AFTER",
                "B11_EXIT_CODE",
            ):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(self.root),
                "VIBE_NO_CONTAINER": "1",
                "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
                "VIBE_CONFIG_FILE": str(self.root / "config.json"),
                "VIBE_STORAGE_LOCK_DIR": str(self.root / "locks"),
                "VIBE_INSTALL": str(self.install),
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_STATE": str(self.state),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        return env

    def runner_env(self, **extra):
        """Umgebung des Läufers; optionale Fixture-Werte überschreiben."""
        env = self.isolated_env()
        env.update(
            {
                "VIBE_AGENTS_DIR": str(self.agents),
                "VIBE_MAX_PACKAGES": "1",
                "VIBE_RETRY_DELAY": "0",
                "VIBE_LOGNAME": "proj",
                "B11_FIXTURE_DIR": str(self.fixture),
                "B11_IGNORE": self.ignore,
                "PATH": str(self.fakebin)
                + os.pathsep
                + os.environ.get("PATH", ""),
            }
        )
        env.update({key: str(value) for key, value in extra.items()})
        return env

    def start_runner(self, **fixture_env):
        """Startet den echten Läufer als eigene Sitzung (eigene Prozessgruppe)."""
        self.fixture_env = {
            key: str(value)
            for key, value in {**{"B11_CHILD": "1"}, **fixture_env}.items()
        }
        self.process = subprocess.Popen(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(self.project)],
            cwd=str(self.project),
            env=self.runner_env(**fixture_env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        self.pgid = os.getpgid(self.process.pid)
        return self.process

    def start_hanging_runner(self, **fixture_env):
        """Startet den Läufer und wartet, bis Harness und Enkelprozess laufen."""
        self.start_runner(**fixture_env)
        self.wait_for_start()
        return self.process

    def wait_for_start(self, timeout=40):
        """Wartet auf PID-Dateien und einen laufenden Registereintrag."""
        expected = ["harness.pid"]
        if getattr(self, "fixture_env", {}).get("B11_CHILD", "1") != "0":
            expected += ["child.pid", "grandchild.pid"]
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if all((self.fixture / name).exists() for name in expected):
                record = self.record()
                if record and record.get("state") in ("starting", "running"):
                    return
            if self.process is not None and self.process.poll() is not None:
                output = self.process.stdout.read() if self.process.stdout else ""
                self.fail(
                    "Der Läufer endete vor dem Agentenstart (Exit "
                    f"{self.process.returncode}):\n{output}\n{self.log_text()}"
                )
            time.sleep(0.05)
        self.fail(
            "Der Läufer hat keinen Agenten gestartet.\nLog:\n" + self.log_text()
        )

    def recorded_pids(self):
        """Alle vom Harness gemeldeten PIDs (nur vorhandene Dateien)."""
        found = {}
        for name in ("harness.pid", "child.pid", "grandchild.pid"):
            path = self.fixture / name
            try:
                value = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if value.isdigit():
                found[name.removesuffix(".pid")] = int(value)
        return found

    def live_pids(self):
        return {
            label: pid
            for label, pid in self.recorded_pids().items()
            if pid_alive(pid)
        }

    def tick_sizes(self):
        sizes = {}
        for path in sorted(self.fixture.glob("*.tick")):
            try:
                sizes[path.name] = path.stat().st_size
            except OSError:
                sizes[path.name] = -1
        return sizes

    def log_text(self):
        path = self.runtime / "proj.log"
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def registry(self):
        return load_stop_module(RUNS, "vibe_b11_runs_under_test").RunRegistry(
            str(self.runtime)
        )

    def record(self):
        try:
            return self.registry().latest(project=str(self.project.resolve()))
        except (OSError, ValueError):
            return None

    def stop_and_expect_death(
        self, signum, name, timeout=STOP_TIMEOUT, send=True
    ):
        """Sendet ``signum`` an die Laufgruppe und prüft das vollständige Ende.

        Mit ``send=False`` wurde das Signal bereits außerhalb gesendet
        (zeitgesteuerte Fälle); die Prüfung ist identisch.
        """
        if send:
            try:
                os.killpg(self.pgid, signum)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None and not self.live_pids():
                break
            time.sleep(0.05)
        runner_alive = self.process.poll() is None
        survivors = self.live_pids()
        before = self.tick_sizes()
        time.sleep(0.3)
        after = self.tick_sizes()
        output = ""
        if not runner_alive:
            try:
                output = self.process.stdout.read() if self.process.stdout else ""
            except (OSError, ValueError):
                output = ""
        problems = []
        if runner_alive:
            problems.append("Der Läufer lebt nach Signal %s weiter." % name)
        if survivors:
            problems.append("Prozesse des Laufs überleben: %r" % survivors)
        if after != before:
            problems.append(
                "Der Agent arbeitet nach dem Stopp weiter (Ticks %r -> %r)."
                % (before, after)
            )
        if problems:
            self.fail(
                "\n".join(problems)
                + "\n--- Läuferausgabe ---\n"
                + output
                + "\n--- Protokoll ---\n"
                + self.log_text()
            )

    def assert_note_is_not_running(self, record):
        self.assertIsNotNone(record, "Kein Registereintrag vorhanden")
        self.assertIn(record.get("state"), ("ended", "stopped"), record)
        self.assertNotEqual(record.get("state"), "running", record)


class StopKillsAgentTest(RunnerProcessFixture):
    """AK1: Ein Stopp beendet die gesamte Prozesskette des Laufs."""

    def test_hup_stop_kills_agent_that_ignores_hup(self):
        """HUP ignoriert: Nach HUP an die Prozessgruppe stirbt die ganze Kette."""
        self.start_hanging_runner(B11_IGNORE="HUP")
        self.assertIsNotNone(self.recorded_pids().get("grandchild"))

        self.stop_and_expect_death(signal.SIGHUP, "HUP")

    def test_term_stop_kills_agent_that_ignores_term(self):
        """TERM ignoriert: Nach TERM an die Prozessgruppe stirbt die Kette."""
        self.start_hanging_runner(B11_IGNORE="TERM")
        self.assertIsNotNone(self.recorded_pids().get("grandchild"))

        self.stop_and_expect_death(signal.SIGTERM, "TERM")

    def test_hup_stop_kills_agent_that_ignores_hup_and_term(self):
        """HUP und TERM ignoriert: Der Stopp eskaliert bis zum sicheren Ende."""
        self.start_hanging_runner(B11_IGNORE="HUP,TERM")
        self.assertIsNotNone(self.recorded_pids().get("grandchild"))

        self.stop_and_expect_death(signal.SIGHUP, "HUP")


class SignalRegistryTest(RunnerProcessFixture):
    """AK2: Der Registereintrag endet sauber und wird nicht überschrieben."""

    def test_signal_stop_marks_the_run_ended_with_signal_note(self):
        """Nach HUP steht der Lauf auf ``ended`` mit Signalnotiz, nie ``running``."""
        self.start_hanging_runner(B11_IGNORE="HUP,TERM")

        self.stop_and_expect_death(signal.SIGHUP, "HUP")

        record = self.record()
        self.assert_note_is_not_running(record)
        self.assertEqual(record.get("state"), "ended", record)
        self.assertEqual(
            record.get("note"), "extern beendet (Signal HUP)", record
        )
        self.assertEqual(record.get("exit_code"), 129, record)
        self.assertIn("extern beendet (Signal HUP)", self.log_text())

    def test_signal_stop_leaves_an_already_finished_record(self):
        """Ein bereits beendeter Eintrag bleibt unverändert (only-live)."""
        self.start_hanging_runner(B11_IGNORE="HUP,TERM")
        record = self.record()
        self.assertIsNotNone(record, "Kein laufender Registereintrag")
        # Vorbedingung: ein anderer Pfad hat den Lauf bereits beendet.
        self.registry().finish(record["id"], exit_code=0, state="finished")

        self.stop_and_expect_death(signal.SIGHUP, "HUP")

        stored = self.registry().get(record["id"])
        self.assertEqual(stored.get("state"), "finished", stored)
        self.assertNotIn("extern beendet", stored.get("note") or "", stored)


class NormalRunBehaviourTest(RunnerProcessFixture):
    """AK3: Das normale Laufverhalten bleibt unverändert."""

    ignore = ""

    def test_regular_harness_keeps_signal_end_and_log_line(self):
        """Reguläre Signalbehandlung: Ende mit 129, Protokoll und Notiz bleiben."""
        self.start_hanging_runner(B11_IGNORE="")

        self.stop_and_expect_death(signal.SIGHUP, "HUP")

        self.assertEqual(self.process.returncode, 129)
        self.assertIn(
            "ABBRUCH: Lauf extern beendet (Signal HUP).", self.log_text()
        )
        record = self.record()
        self.assert_note_is_not_running(record)
        self.assertEqual(record.get("state"), "ended", record)
        self.assertEqual(
            record.get("note"), "extern beendet (Signal HUP)", record
        )

    def test_agent_exit_code_comes_from_the_harness(self):
        """Exit-Code 7 des Harness wird erkannt, nicht der Exit von ``tee``."""
        result = subprocess.run(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(self.project)],
            cwd=str(self.project),
            env=self.runner_env(
                B11_CHILD="0", B11_EXIT_AFTER="0.3", B11_EXIT_CODE="7"
            ),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
        )

        log = self.log_text()
        self.assertIn("=== Agent beendet, Exit-Code 7 ===", log)
        self.assertIn("Fehlerklasse 'other'", log)
        self.assertIn("Überspringe F1", log)
        self.assertNotIn("=== Agent beendet, Exit-Code 0 ===", log)
        self.assertTrue(log, result.stdout + result.stderr)


class StopEndpointRealTmuxTest(RunnerProcessFixture):
    """AK1/AK2/AK4: ``vibe stop`` beendet Lauf und Agenten in echter tmux-Sitzung."""

    ignore = "HUP,TERM"

    def setUp(self):
        super().setUp()
        self.tmux_dir = self.root / "tmux"
        self.tmux_dir.mkdir()
        self.tmux_dir.chmod(0o700)
        # tmux übernimmt PATH für Panes aus der Umgebung des Servers, nicht
        # aus der Sitzungsumgebung. Der Server startet im ersten Aufruf und
        # erbt deshalb hier den PATH mit dem Test-Harness.
        self.tmux_env = {
            "PATH": str(self.fakebin)
            + os.pathsep
            + os.environ.get("PATH", ""),
            "TMUX_TMPDIR": str(self.tmux_dir),
            "TERM": os.environ.get("TERM", "xterm"),
        }
        self.socket = "vibe-proj"

    def tearDown(self):
        self.tmux("-L", self.socket, "kill-server")
        super().tearDown()

    def tmux(self, *args):
        return subprocess.run(
            ["tmux", *args],
            env=self.tmux_env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def cli_env(self):
        env = self.runner_env()
        for key in list(env):
            if key.startswith("B11_") or key == "VIBE_LOGNAME":
                env.pop(key, None)
        env["TMUX_TMPDIR"] = str(self.tmux_dir)
        return env

    def start_run_in_tmux(self):
        """Startet den echten Läufer in einer echten, isolierten tmux-Sitzung."""
        overrides = {
            "VIBE": str(self.root),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "VIBE_CONFIG_FILE": str(self.root / "config.json"),
            "VIBE_STORAGE_LOCK_DIR": str(self.root / "locks"),
            "VIBE_INSTALL": str(self.install),
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_STATE": str(self.state),
            "VIBE_AGENTS_DIR": str(self.agents),
            "VIBE_MAX_PACKAGES": "1",
            "VIBE_RETRY_DELAY": "0",
            "VIBE_LOGNAME": "proj",
            "B11_FIXTURE_DIR": str(self.fixture),
            "B11_IGNORE": self.ignore,
            "PATH": str(self.fakebin)
            + os.pathsep
            + os.environ.get("PATH", ""),
            "TMUX_TMPDIR": str(self.tmux_dir),
        }
        command = "bash {} {} tester".format(
            shlex.quote(str(self.tool_bin / "vibe-run.sh")),
            shlex.quote(str(self.project)),
        )
        args = [
            "-L", self.socket, "new-session", "-d", "-s", self.socket,
            "-c", str(self.project), "-e", "VIBE_MANAGED=run",
        ]
        for key, value in overrides.items():
            args += ["-e", f"{key}={value}"]
        args.append(command)
        result = self.tmux(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.wait_for_start()

    def view_state(self):
        """Lädt den echten CLI-Code und fragt die Projektansicht (run_state)."""
        saved = dict(os.environ)
        try:
            os.environ.clear()
            os.environ.update(self.cli_env())
            module = load_stop_module(CLI, "vibe_b11_stop_view_under_test")
            return module.run_state("proj")
        finally:
            os.environ.clear()
            os.environ.update(saved)

    def session_alive(self):
        return (
            self.tmux(
                "-L", self.socket, "has-session", "-t", self.socket
            ).returncode
            == 0
        )

    def test_stop_command_ends_the_run_and_shows_no_active_agent(self):
        """``vibe stop`` meldet Erfolg, beendet alle Prozesse, Ansicht ist inaktiv."""
        self.start_run_in_tmux()

        result = subprocess.run(
            [sys.executable, str(CLI), "stop", "proj"],
            cwd=str(self.root),
            env=self.cli_env(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Auf das Ende der Prozesskette warten (nicht nur auf die Sitzung).
        deadline = time.monotonic() + STOP_TIMEOUT
        while time.monotonic() < deadline and self.live_pids():
            time.sleep(0.05)
        survivors = self.live_pids()
        session_alive = self.session_alive()
        record = self.record()
        view = self.view_state()

        self.assertEqual(
            result.returncode, 0, result.stdout + result.stderr
        )
        self.assertIn("Beendet:", result.stdout)
        self.assertFalse(session_alive, "Die Laufsitzung lebt noch")
        self.assertEqual(
            survivors, {}, "Prozesse des gestoppten Laufs überleben: %r" % survivors
        )
        self.assert_note_is_not_running(record)
        self.assertIn(record.get("state"), ("ended", "stopped"), record)
        self.assertFalse(view["running"], view)


class PreflightAssistFixture(RunnerProcessFixture):
    """Helfer für Läufe mit Preflight-Assistenz (keine eigenen Testfälle)."""

    ignore = "HUP,TERM"

    def question_folder(self):
        return self.runtime / "questions"

    def wait_for_question(self, timeout=30):
        """Wartet auf eine offene Preflight-Rückfrage (F16-Mechanik)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            folder = self.question_folder()
            if folder.is_dir():
                for path in sorted(folder.iterdir()):
                    if not path.name.endswith(".json"):
                        continue
                    if path.name.endswith(".answer.json"):
                        continue
                    try:
                        record = json.loads(
                            path.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        continue
                    answer = folder / (record["id"] + ".answer.json")
                    if not answer.exists():
                        return record
            if self.process is not None and self.process.poll() is not None:
                self.fail(
                    "Der Läufer endete ohne Preflight-Rückfrage (Exit "
                    f"{self.process.returncode}):\n{self.log_text()}"
                )
            time.sleep(0.05)
        self.fail(
            "Keine Preflight-Rückfrage innerhalb von %s s.\nProtokoll:\n%s"
            % (timeout, self.log_text())
        )

    def answer_free_text(self, record, text):
        """Beantwortet die Rückfrage mit Freitext, wie es das Dashboard tut."""
        folder = self.question_folder()
        folder.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "option": None,
                "text": text,
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "by": "test",
            }
        ) + "\n"
        target = folder / (record["id"] + ".answer.json")
        temporary = folder / (".answer-" + record["id"] + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, target)

    def wait_for_pids(self, names, timeout=40):
        """Wartet, bis der Preflight-Agent seine PID-Dateien geschrieben hat."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if all((self.fixture / name).exists() for name in names):
                return
            if self.process is not None and self.process.poll() is not None:
                self.fail(
                    "Der Läufer endete vor dem Preflight-Agentenstart:\n"
                    + self.log_text()
                )
            time.sleep(0.05)
        self.fail(
            "Der Preflight-Agent hat keine PID-Dateien geschrieben.\n"
            "Protokoll:\n" + self.log_text()
        )

    def assert_no_live_record(self):
        """Kein Registereintrag bleibt ``running``/``starting`` hängen."""
        record = self.record()
        if record is None:
            return
        self.assertNotIn(
            record.get("state"), ("running", "starting"),
            "Der Registereintrag bleibt als laufend hängen: %r" % (record,),
        )


class PreflightAssistStopTest(PreflightAssistFixture):
    """Review Medium 1: Stopp/HUP während der Preflight-Assistenz.

    Die Preflight-Assistenz startet ihrerseits einen Agenten in einer
    Prozessgruppe (``run_agent_in``). Stirbt der Läufer in diesem Fenster an
    einem unabgefangenen Signal, läuft der ``EXIT``-Trap bei Bash nicht; ohne
    eine vor dem ersten Preflight wirksame Signalbehandlung bliebe die
    signalignorierende Preflight-Agentengruppe samt Unter- und Enkelprozess
    als Waise zurück und arbeitete weiter.
    """

    def test_hup_during_preflight_assist_ends_the_agent_group(self):
        """HUP während der Preflight-Assistenz beendet die Agentengruppe.

        Vorbedingung: unsauberes Projekt (Preflight-Befund), Assistenz
        aktiv; der Preflight-Agent (signalignorierender Harness mit Unter-
        und Enkelprozess) läuft; noch kein Registereintrag (Registerstart
        folgt erst nach dem Start-Preflight).
        Aktion: HUP an die Prozessgruppe der Läufersitzung.
        Erwartung: Läufer tot; Preflight-Agentengruppe samt Unter- und
        Enkelprozess tot; keine weiteren Ticks; kein Registereintrag bleibt
        ``running``.
        Fehlerfall: Die Agentengruppe überlebt als Waise und arbeitet
        weiter; ein Eintrag bleibt ``running``.
        """
        (self.project / "unfertig.txt").write_text(
            "unfertig\n", encoding="utf-8"
        )
        self.start_runner(
            VIBE_PREFLIGHT_ASSIST="1",
            VIBE_PREFLIGHT_QUESTION_TIMEOUT="30",
        )
        record = self.wait_for_question()
        self.answer_free_text(record, "Räume den Arbeitsbaum auf")
        self.wait_for_pids(("harness.pid", "child.pid", "grandchild.pid"))

        self.stop_and_expect_death(signal.SIGHUP, "HUP")

        self.assert_no_live_record()


class EndPreflightAssistStopTest(PreflightAssistFixture):
    """Review Medium 1: Stopp/HUP im „end“-Preflight (Eintrag existiert).

    Am Laufende existiert der Registereintrag bereits. Ein HUP während der
    Assistenz muss den Eintrag sauber auf ``ended`` mit Signalnotiz und
    Exit-Code 129 bringen (wie die bestehenden Signal-Tests es pinnen) und
    die Assistenzagentengruppe beenden.
    """

    def install_harness(self):
        """opencode-Attrappe: schließt Pakete ab, hängt in Assistenzaufträgen."""
        hang = (
            "import signal\n"
            "import time\n"
            "signal.signal(signal.SIGHUP, signal.SIG_IGN)\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "if os.environ.get('B11_ASSIST_HANG') == '1' \\\n"
            "        and 'Behebe ausschließlich diese Befunde im Projektordner' "
            "in prompt:\n"
            "    base = pathlib.Path(os.environ['B11_FIXTURE_DIR'])\n"
            "    base.mkdir(parents=True, exist_ok=True)\n"
            "    (base / 'harness.pid').write_text(str(os.getpid()), "
            "encoding='utf-8')\n"
            "    tick = base / 'harness.tick'\n"
            "    while True:\n"
            "        with tick.open('a', encoding='utf-8') as handle:\n"
            "            handle.write('h\\n')\n"
            "        time.sleep(0.05)\n"
        )
        script = support.FAKE_OPENCODE.replace(
            'args_path = os.environ.get("FAKE_ARGS_PATH")',
            hang + 'args_path = os.environ.get("FAKE_ARGS_PATH")',
            1,
        )
        opencode = self.fakebin / "opencode"
        opencode.write_text(script, encoding="utf-8")
        opencode.chmod(0o755)

    def test_hup_during_the_end_preflight_marks_the_run_ended(self):
        """HUP im end-Preflight: Eintrag ``ended`` mit Signalnotiz, Exit 129.

        Vorbedingung: Lauf registriert; das Paket F1 wurde abgeschlossen;
        der Integrationsstand ist unsauber, sodass das end-Preflight eine
        Rückfrage stellt; der Assistenzagent (signalignorierend) läuft.
        Aktion: HUP an die Prozessgruppe der Läufersitzung.
        Erwartung: Läufer endet mit 129; Assistenzagent tot; Registereintrag
        ``ended`` mit Notiz „extern beendet (Signal HUP)“ und Exit-Code 129;
        Protokollzeile vorhanden.
        Fehlerfall: Eintrag bleibt ``running`` oder verliert die Notiz; der
        Agent überlebt.
        """
        self.start_runner(
            VIBE_PREFLIGHT_ASSIST="1",
            VIBE_PREFLIGHT_QUESTION_TIMEOUT="30",
            FAKE_DIRTY_INTEGRATION=str(self.project),
            B11_ASSIST_HANG="1",
        )
        record = self.wait_for_question()
        self.answer_free_text(record, "Räume den Arbeitsbaum auf")
        self.wait_for_pids(("harness.pid",))

        self.stop_and_expect_death(signal.SIGHUP, "HUP")

        self.assertEqual(self.process.returncode, 129, self.log_text())
        stored = self.record()
        self.assertEqual(stored.get("state"), "ended", stored)
        self.assertEqual(
            stored.get("note"), "extern beendet (Signal HUP)", stored
        )
        self.assertEqual(stored.get("exit_code"), 129, stored)
        self.assertIn("extern beendet (Signal HUP)", self.log_text())


class StopAroundStartTest(RunnerProcessFixture):
    """Review Medium 2: Stopp im Fenster zwischen Auftragsstart und PID-Zuweisung.

    Das Fenster zwischen dem Start des Auftrags (``) </dev/null &``) und der
    ``AGENT_PID``-Zuweisung umfasst in der Shell nur Mikrosekunden und ist
    von außen nicht zuverlässig steuerbar. Diese Fälle prüfen deshalb das
    beobachtbare Zielverhalten mit engem Timing und mehreren Wiederholungen:
    Ein Stopp-Signal unmittelbar um den Auftragsstart herum darf die
    Agentengruppe nie als Waise zurücklassen. Ein grüner Einzeldurchlauf
    beweist die Fensterfreiheit nicht; die Wiederholungen erhöhen die
    Trefferwahrscheinlichkeit für den Zeitraum unmittelbar nach dem
    sichtbaren Versuchstart (Protokollmarke „--- Versuch 1/“).
    """

    ignore = "HUP,TERM"

    def hup_when_logged(self, offset, marker, delay=0.0, timeout=40):
        """Sendet HUP, sobald ``marker`` ab ``offset`` im Protokoll erscheint."""
        log_path = self.runtime / "proj.log"
        deadline = time.monotonic() + timeout
        found = False
        while time.monotonic() < deadline:
            try:
                text = log_path.read_text(encoding="utf-8")[offset:]
            except OSError:
                text = ""
            if marker in text:
                found = True
                break
            if self.process is not None and self.process.poll() is not None:
                self.fail(
                    "Der Läufer endete, bevor %r im Protokoll erschien:\n%s"
                    % (marker, self.log_text())
                )
            time.sleep(0.005)
        if not found:
            self.fail(
                "%r erschien nicht innerhalb von %s s im Protokoll.\n%s"
                % (marker, timeout, self.log_text())
            )
        if delay > 0:
            time.sleep(delay)
        try:
            os.killpg(self.pgid, signal.SIGHUP)
        except ProcessLookupError:
            pass

    def test_repeated_hup_around_the_attempt_start_leaves_no_orphan(self):
        """HUP unmittelbar beim Versuchstart: nie eine Waise (4 Wiederholungen).

        Vorbedingung: laufender Lauf mit signalignorierendem Harness; das
        Signal wird bei vier Wiederholungen mit steigendem Verzug (0, 20,
        50 und 200 ms) unmittelbar nach der sichtbaren Versuchstart-Marke
        gesendet — teils vor, teils nach der PID-Zuweisung.
        Aktion: HUP an die Prozessgruppe der Läufersitzung.
        Erwartung: In jeder Wiederholung enden Läufer und die gesamte
        Agentengruppe vollständig; es bleibt nie eine Waise zurück.
        Fehlerfall: Überlebende Prozesse oder weiterlaufende Ticks.
        """
        log_path = self.runtime / "proj.log"
        for repetition, delay in enumerate((0.0, 0.02, 0.05, 0.2)):
            with self.subTest(wiederholung=repetition + 1, verzug=delay):
                offset = log_path.stat().st_size if log_path.exists() else 0
                self.start_runner()
                self.hup_when_logged(offset, "--- Versuch 1/", delay=delay)
                self.stop_and_expect_death(signal.SIGHUP, "HUP", send=False)


class StopAgentGroupFallbackTest(unittest.TestCase):
    """Review Medium 2 (Runde 2): Stopp im Rennfenster nach dem Auftragsstart.

    Zwischen ``) </dev/null &`` und ``AGENT_PID=$!`` kann ein Signal-Trap
    feuern; ``stop_agent_group`` sieht dann einen leeren ``AGENT_PID``.
    Kehrt sie in dieser Lage wirkungslos zurück, läuft die bereits
    gestartete Agentengruppe als Waise weiter — der vom Arbeitspaket
    ausgeschlossene Zustand. Das Mikrosekunden-Fenster selbst ist von
    außen nicht steuerbar (dafür bleibt ``StopAroundStartTest`` der
    E2E-Verhaltensanker); diese Fälle prüfen die deterministisch prüfbare
    Schnittstelle: Die echte Funktion ``stop_agent_group`` aus
    ``bin/vibe-run.sh`` wird in der Fehlerlage ausgeführt — Auftrag läuft
    unter aktiver Jobkontrolle, ``AGENT_PID`` ist leer. Der Trap trifft
    nicht zufällig ins Fenster; die Fensterlage wird hergestellt und der
    Trap darin ausgelöst.

    Der Opferprozess ignoriert HUP und TERM, schreibt Lebenszeichen und
    endet erst nach 120 s; ein Stopp kann ihn also nur über die
    KILL-Eskalation beenden.
    """

    victim_source = (
        "import os, signal, sys, time\n"
        "from pathlib import Path\n"
        "signal.signal(signal.SIGHUP, signal.SIG_IGN)\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "tick, pidfile = sys.argv[1], sys.argv[2]\n"
        "Path(pidfile).write_text(str(os.getpid()), encoding='utf-8')\n"
        "end = time.monotonic() + 120\n"
        "while time.monotonic() < end:\n"
        "    with open(tick, 'a', encoding='utf-8') as handle:\n"
        "        handle.write('t\\n')\n"
        "    time.sleep(0.05)\n"
    )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.victim = self.root / "victim.py"
        self.victim.write_text(self.victim_source, encoding="utf-8")
        self.tick = self.root / "victim.tick"
        self.victim_pid_file = self.root / "victim.pid"
        self.started = []
        self.process = None

    def tearDown(self):
        process = self.process
        if process is not None and process.poll() is None:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except OSError:
                pass
        for pid in self.started + self.orphan_victim_pids():
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        if process is not None:
            try:
                process.communicate(timeout=5)
            except (subprocess.TimeoutExpired, ValueError, OSError):
                pass
        self.tmp.cleanup()

    def function_source(self):
        return extract_shell_function(BIN / "vibe-run.sh", "stop_agent_group")

    def orphan_victim_pids(self):
        """PID eines Überläufers anhand der PID-Datei (Aufräumen im Rot-Fall)."""
        try:
            value = self.victim_pid_file.read_text(encoding="utf-8").strip()
        except OSError:
            return []
        return [int(value)] if value.isdigit() else []

    def write_harness(self, lines):
        """Schreibt eine Hüllshell mit der echten stop_agent_group-Funktion."""
        path = self.root / "harness.sh"
        body = ["set -u", self.function_source()] + lines
        path.write_text("\n".join(body) + "\n", encoding="utf-8")
        return path

    def run_harness(self, path, send_hup=False, timeout=40):
        """Startet die Hüllshell; optional HUP, sobald der Auftrag läuft."""
        self.process = subprocess.Popen(
            ["bash", str(path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        if send_hup:
            deadline = time.monotonic() + 10
            while not (
                self.tick.exists() and self.tick.stat().st_size > 0
            ):
                if self.process.poll() is not None:
                    self.fail("Die Hüllshell endete vor dem Signal.")
                if time.monotonic() > deadline:
                    self.fail("Der Opferprozess ist nie angelaufen.")
                time.sleep(0.02)
            # Nur an die Hüllshell, nicht an die Gruppe: Der Auftrag ignoriert
            # HUP ohnehin — das Signal muss den Trap der Shell erreichen.
            os.kill(self.process.pid, signal.SIGHUP)
        try:
            stdout, _ = self.process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.fail(
                "Die Hüllshell endete nicht innerhalb von %s s." % timeout
            )
        return stdout

    def job_pid_of(self, output):
        match = re.search(r"JOB_PID=(\d+)", output)
        self.assertIsNotNone(match, "Hüllshell meldet keine Auftrag-PID:\n" + output)
        pid = int(match.group(1))
        self.started.append(pid)
        return pid

    def wait_victim_dead(self, pid, timeout=10.0):
        """Fordert das vollständige Ende des Auftrags innerhalb der Frist."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not pid_alive(pid):
                return
            time.sleep(0.05)
        self.fail(
            "Der Auftrag (PID %s) überlebt den Stopp und läuft als Waise "
            "weiter." % pid
        )

    def test_hup_trap_with_unassigned_agent_pid_kills_the_running_job(self):
        """Trap feuert bei leerer Kennung: die laufende Auftragsguppe endet.

        Vorbedingung: echte ``stop_agent_group``; Jobkontrolle aktiv; ein
        signalignorierender Auftrag läuft in eigener Prozessgruppe;
        ``AGENT_PID`` ist noch leer (Rennfenster-Simulation); ein HUP-Trap
        ruft ``stop_agent_group`` — wie der Signal-Trap des Läufers im
        Fenster.
        Aktion: HUP an die Hüllshell, während der Auftrag läuft.
        Erwartung: Der Trap wird ausgeführt und die Auftragsguppe endet
        vollständig (TERM genügt nicht, KILL-Eskalation beendet).
        Fehlerfall: Der Auftrag überlebt als Waise, oder der Trap greift
        nicht.
        """
        harness = self.write_harness([
            "trap 'stop_agent_group; echo TRAP_RAN' HUP",
            'AGENT_PID=""',
            "set -m",
            'python3 "%s" "%s" "%s" </dev/null >/dev/null 2>&1 &'
            % (self.victim, self.tick, self.victim_pid_file),
            "job_pid=$!",
            "sleep 2",
            "echo NO_SIGNAL",
            'echo "JOB_PID=$job_pid"',
        ])
        output = self.run_harness(harness, send_hup=True)

        self.assertIn(
            "TRAP_RAN",
            output,
            "Der HUP-Trap wurde nicht ausgeführt:\n" + output,
        )
        self.wait_victim_dead(self.job_pid_of(output))

    def test_stop_with_unassigned_agent_pid_and_no_jobs_is_harmless(self):
        """Leere Kennung ohne laufende Aufträge: wirkungslos und fehlerfrei.

        Vorbedingung: echte ``stop_agent_group``; ``AGENT_PID`` leer; keine
        Hintergrundaufträge.
        Aktion: direkter Aufruf von ``stop_agent_group`` (derselbe Einstieg,
        den der Trap mit leerer Kennung nimmt).
        Erwartung: Die Funktion kehrt ohne Fehler zurück; die aufrufende
        Shell läuft weiter und bleibt unangetastet.
        Fehlerfall: Abbruch (etwa durch ungeprüte Ersetzung) oder
        Selbstverletzung der eigenen Gruppe.
        """
        harness = self.write_harness([
            "set -m",
            'AGENT_PID=""',
            "stop_agent_group",
            'echo "STOP_RC=$?"',
            "echo AFTER_MARKER",
        ])
        output = self.run_harness(harness)

        self.assertEqual(
            self.process.returncode, 0, output
        )
        self.assertIn("AFTER_MARKER", output, output)

    def test_stop_with_assigned_agent_pid_kills_that_group(self):
        """Normalpfad mit gesetzter Kennung endet die Auftragsggruppe weiter.

        Vorbedingung: echte ``stop_agent_group``; der Auftrag läuft und ist
        als ``AGENT_PID`` eingetragen (Lage nach der Zuweisung).
        Aktion: direkter Aufruf von ``stop_agent_group``.
        Erwartung: Die Gruppe endet trotz ignorierter TERM-Signale; die
        Funktion meldet Erfolg.
        Fehlerfall: Überlebender Auftrag oder gebrochener Normalpfad durch
        eine künftige Fallback-Änderung.
        """
        harness = self.write_harness([
            "set -m",
            'python3 "%s" "%s" "%s" </dev/null >/dev/null 2>&1 &'
            % (self.victim, self.tick, self.victim_pid_file),
            "job_pid=$!",
            'AGENT_PID="$job_pid"',
            "for i in $(seq 1 100); do",
            '  [ -s "%s" ] && break' % self.tick,
            "  sleep 0.05",
            "done",
            "stop_agent_group",
            'echo "STOP_RC=$?"',
            'echo "JOB_PID=$job_pid"',
        ])
        output = self.run_harness(harness)

        self.assertEqual(
            self.process.returncode, 0, output
        )
        self.wait_victim_dead(self.job_pid_of(output))


# ===========================================================================
# Abnahme: Läufer startet Agenten und Prüfungen ohne Produktivpfade (AK6-AK8)
# ===========================================================================

import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support  # noqa: E402

SANDBOX = REPO / "bin" / "vibe_sandbox.py"

PRODUCTIVE_KEYS = (
    "VIBE",
    "VIBE_PROFILE",
    "VIBE_INSTALL",
    "VIBE_STATE",
    "VIBE_RUNTIME",
    "VIBE_CONFIG_FILE",
    "VIBE_AGENTS_DIR",
)

FEEDBACK_ONE = [support.ticket_record(
    "F1", "Erstes Paket", type="feedback", description="Test")]

GIT_IDENTITY = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}

RECORDING_OPENCODE = r'''#!/usr/bin/env python3
"""Zeichnet Argumente und Prozessumgebung je Aufruf auf."""
import json
import os
import sys

record = os.environ.get("B17_RECORD")
if record:
    with open(record, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(
            {"argv": sys.argv[1:], "env": dict(os.environ)},
            ensure_ascii=False,
        ) + "\n")
os.execvp("package-agent", ["package-agent"] + sys.argv[1:])
'''

FAKE_BWRAP = r'''#!/usr/bin/env python3
"""Zeichnet die bubblewrap-Argumente auf und führt den Befehl aus."""
import json
import os
import sys

args = sys.argv[1:]
record = os.environ.get("B17_BWRAP_RECORD")
if record:
    with open(record, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(args, ensure_ascii=False) + "\n")
if "--" not in args:
    raise SystemExit(0)
command = args[args.index("--") + 1:]
if not command:
    raise SystemExit(0)
os.execvp(command[0], command)
'''


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def read_env_file(path):
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


class RunnerFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")

        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        (self.tool_bin / "vibe").write_text(support.FAKE_VIBE, encoding="utf-8")
        (self.tool_bin / "vibe").chmod(0o755)
        (self.tool_bin / "vibe_sandbox.py").write_text(
            SANDBOX.read_text(encoding="utf-8"), encoding="utf-8"
        )
        self.runtime = self.root / "_logs"
        self.state = self.root / "state"
        self.state.mkdir()

        self.fakebin = self.root / "fakebin"
        self.fakebin.mkdir()
        self.opencode = self.fakebin / "opencode"
        self.opencode.write_text(RECORDING_OPENCODE, encoding="utf-8")
        self.opencode.chmod(0o755)
        self.package_agent = self.fakebin / "package-agent"
        self.package_agent.write_text(support.FAKE_OPENCODE, encoding="utf-8")
        self.package_agent.chmod(0o755)
        (self.fakebin / "curl").write_text(support.FAKE_CURL, encoding="utf-8")
        (self.fakebin / "curl").chmod(0o755)
        self.bwrap = self.fakebin / "bwrap"
        self.bwrap.write_text(FAKE_BWRAP, encoding="utf-8")
        self.bwrap.chmod(0o755)

        self.record_path = self.root / "record.jsonl"
        self.bwrap_record = self.root / "bwrap.jsonl"

    def make_project(self, env_text, name="proj", hide_vibe=False):
        project = self.root / name
        support.init_repo(project)
        support.write_project(project, env_text, feedback=FEEDBACK_ONE)
        if hide_vibe:
            # Reproduziert den Vorfall: Die Arbeitskopie enthält keine .vibe,
            # das Konfigurationsprojekt aber schon.
            exclude = project / ".git" / "info" / "exclude"
            exclude.write_text(".vibe/\n", encoding="utf-8")
        support.commit_all(project, "Ausgangsstand")
        return project

    def verification_project(self, sandbox="off", name="proj"):
        package_env = self.root / (name + "-package.env")
        package_marker = self.root / (name + "-package.marker")
        full_env = self.root / (name + "-full.env")
        full_marker = self.root / (name + "-full.marker")
        env_text = (
            "TYPE=generic\n"
            "AGENT=test-agent\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            "MAX_RETRIES=1\n"
            "VERIFY_PACKAGE='env > \"%s\"; echo paket > \"%s\"'\n"
            "VERIFY_FULL='env > \"%s\"; echo final > \"%s\"'\n"
            "SANDBOX=%s\n"
            'SANDBOX_TOOLS="git"\n'
        ) % (package_env, package_marker, full_env, full_marker, sandbox)
        project = self.make_project(
            env_text, name=name, hide_vibe=(sandbox == "on")
        )
        return project, {
            "package_env": package_env,
            "package_marker": package_marker,
            "full_env": full_env,
            "full_marker": full_marker,
        }

    def android_project(self, name="android"):
        """Projekt mit ``TYPE=android`` und leerem ``VERIFY_FULL``.

        Der Läufer wählt dann den Android-Direktzweig
        ``bash "$V/verify.sh" "$P" full``. Das Prüfskript schreibt seine
        Prozessumgebung und einen Marker; die Hash-Datei lässt ``check_hash``
        den Lauf starten.
        """
        self.android_env = self.root / (name + "-verify.env")
        self.android_marker = self.root / (name + "-verify.marker")
        verify_dir = self.install / "verify"
        verify_dir.mkdir(parents=True)
        script = verify_dir / "verify.sh"
        script.write_text(
            "#!/usr/bin/env bash\n"
            "env > " + shlex.quote(str(self.android_env)) + "\n"
            "echo android > " + shlex.quote(str(self.android_marker)) + "\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        digest = hashlib.sha256(script.read_bytes()).hexdigest()
        hash_file = self.home / ".config" / "schreibfuchs-verify.sha"
        hash_file.parent.mkdir(parents=True, exist_ok=True)
        hash_file.write_text(digest + "  verify.sh\n", encoding="utf-8")
        env_text = (
            "TYPE=android\n"
            "AGENT=test-agent\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            "MAX_RETRIES=1\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL=""\n'
            "SANDBOX=on\n"
            'SANDBOX_TOOLS="git"\n'
        )
        return self.make_project(env_text, name=name, hide_vibe=True)

    def env(self, project, sandbox=False, **extra):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith(("VIBE", "FAKE_", "B17_")):
                env.pop(key, None)
        for key in ("AGENT", "MAX_PACKAGES", "MAX_RETRIES", "SANDBOX",
                    "SANDBOX_TOOLS", "VERIFY_FULL", "VERIFY_PACKAGE"):
            env.pop(key, None)
        env.update({
            "VIBE": str(self.root),
            "VIBE_PROFILE": "prod",
            "VIBE_INSTALL": str(self.install),
            "VIBE_STATE": str(self.state),
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_CONFIG_FILE": str(self.home / ".config" / "vibe" / "config.json"),
            "VIBE_AGENTS_DIR": str(self.agents),
            "VIBE_LOGNAME": project.name,
            "VIBE_MAX_PACKAGES": "1",
            "VIBE_RETRY_DELAY": "0",
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "VIBE_STORAGE_LOCK_DIR": str(self.home / "locks"),
            "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
            "FAKE_COUNTER": str(self.root / "counter"),
            "FAKE_CALLS": str(self.root / "calls.jsonl"),
            "B17_RECORD": str(self.record_path),
            "B17_BWRAP_RECORD": str(self.bwrap_record),
        })
        if sandbox:
            env["VIBE_BWRAP"] = str(self.bwrap)
        env.update(GIT_IDENTITY)
        env.update({key: str(value) for key, value in extra.items()})
        return env

    def run_runner(self, project, sandbox=False, **extra):
        return subprocess.run(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(project)],
            cwd=str(project),
            env=self.env(project, sandbox=sandbox, **extra),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )

    def agent_record(self):
        for record in read_jsonl(self.record_path):
            argv = record.get("argv") or []
            if argv and argv[0] == "run":
                return record
        return None

    def bwrap_records(self):
        return read_jsonl(self.bwrap_record)

    def bwrap_invocation(self, needle):
        for argv in self.bwrap_records():
            if needle in " ".join(argv):
                return argv
        return None


class AgentEnvironmentTest(RunnerFixture):
    """AK6: keine Produktivpfade im Agentenprozess."""

    def test_agent_process_has_no_vibe_paths(self):
        project = self.make_project(
            "TYPE=generic\nAGENT=test-agent\nTESTER=test-agent\n"
            "REVIEWER=code-reviewer\nVERIFY_PACKAGE=\"true\"\n"
            "VERIFY_FULL=\"true\"\nMAX_RETRIES=1\n"
        )

        result = self.run_runner(project)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = self.agent_record()
        self.assertIsNotNone(record, "Kein Agentenaufruf aufgezeichnet")
        present = [key for key in PRODUCTIVE_KEYS if key in record["env"]]
        self.assertEqual(
            [], present,
            "Der Agentenprozess erbt Produktivpfade: " + ", ".join(present),
        )

    def test_agent_process_keeps_its_run_control_variables(self):
        project = self.make_project(
            "TYPE=generic\nAGENT=test-agent\nTESTER=test-agent\n"
            "REVIEWER=code-reviewer\nVERIFY_PACKAGE=\"true\"\n"
            "VERIFY_FULL=\"true\"\nMAX_RETRIES=1\n"
        )

        result = self.run_runner(project)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = self.agent_record()
        self.assertIsNotNone(record)
        self.assertEqual(record["env"].get("VIBE_LOGNAME"), project.name,
                         "Laufsteuer-Variablen dürfen erhalten bleiben")


class QuestionHintTest(RunnerFixture):
    """AK7: Der Prompt nennt die Laufzeit für Rückfragen ausdrücklich."""

    def test_prompt_contains_runtime_for_ask_and_wait(self):
        project = self.make_project(
            "TYPE=generic\nAGENT=test-agent\nTESTER=test-agent\n"
            "REVIEWER=code-reviewer\nVERIFY_PACKAGE=\"true\"\n"
            "VERIFY_FULL=\"true\"\nMAX_RETRIES=1\n"
        )

        result = self.run_runner(project)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = self.agent_record()
        self.assertIsNotNone(record, "Kein Agentenaufruf aufgezeichnet")
        prompt = record["argv"][-1]
        self.assertIn("vibe ask --runtime", prompt)
        self.assertIn("vibe ask --wait", prompt)
        self.assertIn(
            str(self.runtime.resolve()), prompt,
            "Der Prompt nennt den Laufzeitordner des Laufs nicht",
        )
        self.assertIn("--runtime", prompt.split("vibe ask --wait", 1)[1])


class SandboxWiringTest(RunnerFixture):
    """AK8: Sandbox gilt für Agent und Prüfungen, auch ohne .vibe in der Kopie."""

    def test_agent_runs_in_the_sandbox_with_config_project_and_worktree(self):
        project, _paths = self.verification_project(sandbox="on")

        result = self.run_runner(project, sandbox=True)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        invocation = self.bwrap_invocation("opencode")
        self.assertIsNotNone(
            invocation,
            "Der Agent lief nicht über bubblewrap:\n" + result.stdout,
        )
        argv = invocation
        separator = argv.index("--")
        command = argv[separator + 1:]
        self.assertEqual(command[0], "opencode")
        self.assertIn("run", command)

        pairs = [
            (argv[index], argv[index + 1], argv[index + 2])
            for index in range(len(argv) - 2)
            if argv[index] in ("--bind", "--ro-bind", "--ro-bind-try")
        ]
        real_project = os.path.realpath(project)
        chdir = argv[argv.index("--chdir") + 1]
        self.assertTrue(
            chdir.startswith(str(self.runtime.resolve()) + os.sep + "worktrees"),
            "Der Agent läuft nicht in der Paket-Arbeitskopie: " + chdir,
        )
        self.assertIn(("--bind", real_project, real_project), pairs,
                      "Das Konfigurationsprojekt ist nicht schreibbar gebunden")
        self.assertIn(("--bind", chdir, chdir), pairs,
                      "Die Paket-Arbeitskopie ist nicht schreibbar gebunden")
        self.assertIn(
            ("--ro-bind", os.path.join(real_project, ".vibe"),
             os.path.join(real_project, ".vibe")),
            pairs,
            "Die Sandbox liest die Konfiguration nicht aus dem Projekt",
        )

    def test_package_and_final_verification_run_in_the_sandbox(self):
        project, paths = self.verification_project(sandbox="on")

        result = self.run_runner(project, sandbox=True)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(paths["package_marker"].is_file(),
                        "Paketprüfung lief nicht:\n" + result.stdout)
        self.assertTrue(paths["full_marker"].is_file(),
                        "Abschlussprüfung lief nicht:\n" + result.stdout)
        self.assertIsNotNone(
            self.bwrap_invocation(str(paths["package_marker"])),
            "Paketprüfung lief außerhalb der Sandbox",
        )
        self.assertIsNotNone(
            self.bwrap_invocation(str(paths["full_marker"])),
            "Abschlussprüfung lief außerhalb der Sandbox",
        )
        for key in ("package_env", "full_env"):
            values = read_env_file(paths[key])
            leaked = [name for name in PRODUCTIVE_KEYS if name in values]
            self.assertEqual(
                [], leaked,
                "Die Prüfung erbte Produktivpfade: " + ", ".join(leaked),
            )

    def test_android_final_verification_runs_in_the_sandbox_with_clean_environment(self):
        """Review 1/High: Auch der Android-Direktzweig läuft isoliert.

        ``final_verify`` ruft bei leerem ``VERIFY_FULL`` das Abnahmeskript
        direkt auf. Es muss über denselben Sandbox-/Clean-Env-Adapter laufen
        wie die generische Abschlussprüfung und ``VIBE_VERIFY_RUNTIME``
        erhalten.
        """
        project = self.android_project()

        result = self.run_runner(project, sandbox=True)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(
            self.android_marker.is_file(),
            "Die Android-Abschlussprüfung lief nicht:\n" + result.stdout,
        )
        values = read_env_file(self.android_env)
        with self.subTest(check="sandbox"):
            self.assertIsNotNone(
                self.bwrap_invocation("verify.sh"),
                "Die Android-Abschlussprüfung lief außerhalb der Sandbox:\n"
                + result.stdout,
            )
        with self.subTest(check="cleaned-environment"):
            leaked = [key for key in PRODUCTIVE_KEYS if key in values]
            self.assertEqual(
                [], leaked,
                "Die Android-Prüfung erbte Produktivpfade: " + ", ".join(leaked),
            )
        with self.subTest(check="verify-runtime"):
            self.assertTrue(
                "VIBE_VERIFY_RUNTIME" in values,
                "Die Android-Prüfung erhält kein VIBE_VERIFY_RUNTIME",
            )
            self.assertEqual(
                os.path.realpath(self.runtime),
                os.path.realpath(values.get("VIBE_VERIFY_RUNTIME", "")),
                "VIBE_VERIFY_RUNTIME nennt nicht den Laufzeitordner des Laufs",
            )

    def test_verification_without_sandbox_is_unwrapped_but_cleaned(self):
        project, paths = self.verification_project(sandbox="off")

        result = self.run_runner(project)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(paths["package_marker"].is_file())
        self.assertTrue(paths["full_marker"].is_file())
        self.assertIsNone(
            self.bwrap_invocation(str(paths["package_marker"])),
            "Bei SANDBOX=off darf die Paketprüfung nicht gewrappt laufen",
        )
        self.assertIsNone(
            self.bwrap_invocation(str(paths["full_marker"])),
            "Bei SANDBOX=off darf die Abschlussprüfung nicht gewrappt laufen",
        )
        for key in ("package_env", "full_env"):
            values = read_env_file(paths[key])
            leaked = [name for name in PRODUCTIVE_KEYS if name in values]
            self.assertEqual(
                [], leaked,
                "Die Prüfung erbte Produktivpfade: " + ", ".join(leaked),
            )


# ===========================================================================
# Unterbrochenen Lauf trotz nicht committeter Änderungen neu anstoßen
# ===========================================================================

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support

WEB = BIN / "vibe-web.py"

PROJECT_ENV = """TYPE=generic
AGENT=test-agent
TESTER=test-agent
REVIEWER=code-reviewer
VERIFY_PACKAGE="true"
VERIFY_FULL="true"
"""

FEEDBACK = [support.ticket_record(
    "F1", "Erstes Paket", type="feedback", description="Test")]

OLD_AGENTS = (
    "# Projekt\n\n"
    "Eigene Regel\n\n"
    "<!-- vibe:general-rules -->\n"
    "ALTER REGELSATZ\n"
    "<!-- /vibe:general-rules -->\n"
)


def load_keep_changes_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def load_cli(vibe_root, home):
    """Lädt ``bin/vibe`` als Modul mit isoliertem VIBE, HOME und XDG."""
    keys = (
        "VIBE",
        "VIBE_NO_CONTAINER",
        "VIBE_INSTALL",
        "VIBE_RUNTIME",
        "VIBE_STATE",
        "VIBE_AGENTS_DIR",
        "VIBE_CONFIG_FILE",
        "VIBE_CONFIG_DIR",
        "VIBE_STORAGE_LOCK_DIR",
        "HOME",
        "XDG_CONFIG_HOME",
    )
    old = {key: os.environ.get(key) for key in keys}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    os.environ["XDG_CONFIG_HOME"] = str(home / ".config")
    os.environ["VIBE_CONFIG_FILE"] = str(vibe_root / "config.json")
    os.environ["VIBE_STORAGE_LOCK_DIR"] = str(vibe_root / "locks")
    for key in (
        "VIBE_CONFIG_DIR",
        "VIBE_INSTALL",
        "VIBE_RUNTIME",
        "VIBE_STATE",
        "VIBE_AGENTS_DIR",
    ):
        os.environ.pop(key, None)
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_f27_under_test", str(CLI)
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


def module_env(root, home):
    """Isolierte Umgebung ohne persönliche VIBE-, Sandbox- oder Prüfwerte."""
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
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return env


# ---------------------------------------------------------------------------
# Preflight-Modul: allow_dirty
# ---------------------------------------------------------------------------
class PreflightAllowDirtyTest(unittest.TestCase):
    """Verhalten 1-3: Nur der unsaubere Arbeitsbaum ist übersteuerbar."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.packages = load_keep_changes_module(
            BIN / "vibe_packages.py", "vibe_packages_f27_preflight"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def make_project(self, name="proj", env_text=PROJECT_ENV):
        project = self.root / name
        support.init_repo(project)
        support.write_project(project, env_text, feedback=FEEDBACK)
        support.commit_all(project, "Ausgangsstand")
        return project

    def make_dirty(self, project, name="unfertig.txt"):
        path = project / name
        path.write_text("unfertig\n", encoding="utf-8")
        return path

    def test_dirty_tree_is_rejected_by_default_and_allowed_only_explicitly(self):
        project = self.make_project()
        self.make_dirty(project)

        default_errors = self.packages.preflight_errors(
            project, self.agents, "", ""
        )
        strict_errors = self.packages.preflight_errors(
            project, self.agents, "", "", allow_dirty=False
        )
        allowed_errors = self.packages.preflight_errors(
            project, self.agents, "", "", allow_dirty=True
        )

        for errors in (default_errors, strict_errors):
            self.assertTrue(
                any("Arbeitsbaum" in error for error in errors), errors
            )
            self.assertTrue(
                any("unfertig.txt" in error for error in errors), errors
            )
        self.assertFalse(
            any("Arbeitsbaum" in error for error in allowed_errors),
            allowed_errors,
        )
        self.assertEqual(allowed_errors, [], allowed_errors)

    def test_other_findings_still_block_with_allow_dirty(self):
        # Kein Git-Repository.
        plain = self.root / "norepo"
        (plain / ".vibe").mkdir(parents=True)
        (plain / ".vibe" / "project.env").write_text(
            PROJECT_ENV, encoding="utf-8"
        )
        self.make_dirty(plain)
        errors = self.packages.preflight_errors(
            plain, self.agents, "", "", allow_dirty=True
        )
        self.assertTrue(
            any("Kein Git-Repository" in error for error in errors), errors
        )

        # Detached HEAD.
        detached = self.make_project("detached")
        support.git(detached, "checkout", "--detach")
        self.make_dirty(detached)
        errors = self.packages.preflight_errors(
            detached, self.agents, "", "", allow_dirty=True
        )
        self.assertTrue(
            any("Detached HEAD" in error for error in errors), errors
        )
        self.assertFalse(
            any("Arbeitsbaum" in error for error in errors), errors
        )

        # Fehlender TESTER.
        no_tester = self.make_project(
            "no-tester",
            """TYPE=generic
AGENT=test-agent
REVIEWER=code-reviewer
VERIFY_PACKAGE="true"
""",
        )
        self.make_dirty(no_tester)
        errors = self.packages.preflight_errors(
            no_tester, self.agents, "", "", allow_dirty=True
        )
        self.assertTrue(any("TESTER" in error for error in errors), errors)
        self.assertFalse(
            any("Arbeitsbaum" in error for error in errors), errors
        )

        # Fehlender REVIEWER.
        no_reviewer = self.make_project(
            "no-reviewer",
            """TYPE=generic
AGENT=test-agent
TESTER=test-agent
REVIEWER=fehlt
VERIFY_PACKAGE="true"
""",
        )
        self.make_dirty(no_reviewer)
        errors = self.packages.preflight_errors(
            no_reviewer, self.agents, "", "", allow_dirty=True
        )
        self.assertTrue(any("REVIEWER" in error for error in errors), errors)
        self.assertFalse(
            any("Arbeitsbaum" in error for error in errors), errors
        )

        # Fehlende Paketprüfung.
        no_check = self.make_project(
            "no-check",
            """TYPE=generic
AGENT=test-agent
TESTER=test-agent
REVIEWER=code-reviewer
""",
        )
        self.make_dirty(no_check)
        errors = self.packages.preflight_errors(
            no_check, self.agents, "", "", allow_dirty=True
        )
        self.assertTrue(
            any("Paketprüfung fehlt" in error for error in errors), errors
        )
        self.assertFalse(
            any("Arbeitsbaum" in error for error in errors), errors
        )

    def test_assist_preflight_passes_a_dirty_tree_only_with_allow_dirty(self):
        project = self.make_project()
        self.make_dirty(project)

        strict = self.packages.assist_preflight(
            project, self.agents, "", "", runtime=None, allow_dirty=False
        )
        allowed = self.packages.assist_preflight(
            project, self.agents, "", "", runtime=None, allow_dirty=True
        )

        self.assertEqual(strict["action"], "unavailable", strict)
        self.assertTrue(
            any("Arbeitsbaum" in error for error in strict["errors"]),
            strict,
        )
        self.assertEqual(allowed["action"], "pass", allowed)
        self.assertEqual(allowed["errors"], [], allowed)


# ---------------------------------------------------------------------------
# Paket-Läufer: VIBE_KEEP_CHANGES
# ---------------------------------------------------------------------------
class KeepChangesRunnerFixture(unittest.TestCase):
    """Isolierter Läufer mit echtem Mini-Git-Repository."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        (self.tool_bin / "vibe").write_text(support.FAKE_VIBE, encoding="utf-8")
        (self.tool_bin / "vibe").chmod(0o755)
        self.runtime = self.root / "_logs"
        self.state = self.root / "_state"
        self.state.mkdir()
        self.calls = self.root / "calls.log"
        self.counter = self.root / "counter"
        self.fakebin = support.install_fake_tools(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def make_project(self, name="proj", env_text=PROJECT_ENV,
                     feedback=FEEDBACK):
        project = self.root / name
        support.init_repo(project)
        support.write_project(project, env_text, feedback=feedback)
        support.commit_all(project, "Ausgangsstand")
        return project

    def make_dirty(self, project, name="unfertig.txt", text="unfertig\n"):
        path = project / name
        path.write_text(text, encoding="utf-8")
        return path

    def env(self, project, **extra):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_"):
                env.pop(key, None)
        for key in (
            "AGENT",
            "TESTER",
            "REVIEWER",
            "MAX_PACKAGES",
            "MAX_RETRIES",
            "SANDBOX",
            "SANDBOX_TOOLS",
            "VERIFY_FULL",
            "VERIFY_PACKAGE",
        ):
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(self.root),
                "VIBE_INSTALL": str(self.install),
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_STATE": str(self.state),
                "VIBE_AGENTS_DIR": str(self.agents),
                "VIBE_LOGNAME": project.name,
                "VIBE_RETRY_DELAY": "0",
                "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
                "VIBE_STORAGE_LOCK_DIR": str(self.home / "locks"),
                "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
                "FAKE_CALLS": str(self.calls),
                "FAKE_COUNTER": str(self.counter),
                "FAKE_MODE": "complete",
            }
        )
        env.update({key: str(value) for key, value in extra.items()})
        return env

    def run_runner(self, project, **extra):
        return subprocess.run(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(project)],
            cwd=str(project),
            env=self.env(project, **extra),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def agent_calls(self):
        if not self.calls.is_file():
            return []
        return self.calls.read_text(encoding="utf-8").splitlines()

    def log(self, project):
        path = self.runtime / (project.name + ".log")
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def combined(self, result, project):
        return result.stdout + result.stderr + "\n" + self.log(project)


class RunnerKeepChangesTest(KeepChangesRunnerFixture):
    """Verhalten 1, 2, 3 und 6 am echten Läufer."""

    def test_runner_without_keep_changes_blocks_on_dirty_tree(self):
        project = self.make_project()
        self.make_dirty(project)

        result = self.run_runner(project)

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("Arbeitsbaum", result.stdout)
        self.assertIn("unfertig.txt", result.stdout)
        self.assertEqual(self.agent_calls(), [])

    def test_keep_changes_starts_a_package_and_preserves_changes(self):
        project = self.make_project()
        agents = project / "AGENTS.md"
        agents.write_text("Original\n", encoding="utf-8")
        support.commit_all(project, "AGENTS.md ergänzt")
        dirty = self.make_dirty(project)
        agents.write_text("Nutzernachtrag\n", encoding="utf-8")

        before_status = support.git(
            project, "status", "--porcelain=v1", "-uall",
            "--", "AGENTS.md", "unfertig.txt",
        ).stdout
        before_agents = agents.read_bytes()
        before_dirty = dirty.read_bytes()

        result = self.run_runner(
            project, VIBE_KEEP_CHANGES="1", VIBE_MAX_PACKAGES="1"
        )
        output = self.combined(result, project)

        # Der Lauf hat tatsächlich begonnen: genau ein Arbeitspaket lief.
        self.assertEqual(len(self.agent_calls()), 1, output)
        self.assertIn("Arbeitspaket F1", self.log(project))
        self.assertIn("Geschlossen: F1", result.stdout)

        # Die vorhandenen Änderungen bleiben unverändert.
        after_status = support.git(
            project, "status", "--porcelain=v1", "-uall",
            "--", "AGENTS.md", "unfertig.txt",
        ).stdout
        self.assertEqual(after_status, before_status)
        self.assertEqual(agents.read_bytes(), before_agents)
        self.assertEqual(dirty.read_bytes(), before_dirty)

        # Kein Stage, Commit, Stash, Checkout oder Wiederherstellen.
        self.assertEqual(
            support.git(project, "diff", "--cached", "--name-only").stdout, ""
        )
        self.assertEqual(
            support.git(project, "stash", "list").stdout, ""
        )
        tracked = support.git(project, "ls-tree", "-r", "--name-only", "HEAD")
        self.assertNotIn("unfertig.txt", tracked.stdout.splitlines())
        self.assertIn(" M AGENTS.md", after_status)
        self.assertIn("?? unfertig.txt", after_status)

    def test_final_verification_still_blocks_a_dirty_integration_tree(self):
        project = self.make_project(
            "strict",
            env_text=(
                'TYPE=generic\nAGENT=test-agent\nTESTER=test-agent\n'
                'REVIEWER=code-reviewer\nVERIFY_PACKAGE="true"\n'
                'VERIFY_FULL="echo final > \\"$VIBE_RUNTIME/final-ran\\""\n'
            ),
        )
        self.make_dirty(project)
        final_marker = self.runtime / "final-ran"

        result = self.run_runner(
            project, VIBE_KEEP_CHANGES="1", VIBE_MAX_PACKAGES="1"
        )
        output = self.combined(result, project)

        # Das Paket durfte starten, die Gesamtprüfung bleibt aber streng.
        self.assertEqual(len(self.agent_calls()), 1, output)
        self.assertEqual(result.returncode, 1, output)
        self.assertIn("Integrationsstand ist nicht sauber", output)
        self.assertIn("unfertig.txt", output)
        self.assertFalse(
            final_marker.exists(),
            "Die Gesamtprüfung lief trotz unsauberem Integrationsstand.",
        )

    def test_other_findings_block_even_with_keep_changes(self):
        cases = []

        norepo = self.root / "norepo"
        (norepo / ".vibe").mkdir(parents=True)
        (norepo / ".vibe" / "project.env").write_text(
            PROJECT_ENV, encoding="utf-8"
        )
        (norepo / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        (norepo / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
        self.make_dirty(norepo)
        cases.append(("norepo", norepo, "Kein Git-Repository"))

        detached = self.make_project("detached")
        support.git(detached, "checkout", "--detach")
        self.make_dirty(detached)
        cases.append(("detached", detached, "Detached HEAD"))

        no_tester = self.make_project(
            "no-tester",
            """TYPE=generic
AGENT=test-agent
REVIEWER=code-reviewer
VERIFY_PACKAGE="true"
""",
        )
        self.make_dirty(no_tester)
        cases.append(("no-tester", no_tester, "TESTER"))

        no_reviewer = self.make_project(
            "no-reviewer",
            """TYPE=generic
AGENT=test-agent
TESTER=test-agent
REVIEWER=fehlt
VERIFY_PACKAGE="true"
""",
        )
        self.make_dirty(no_reviewer)
        cases.append(("no-reviewer", no_reviewer, "REVIEWER"))

        no_check = self.make_project(
            "no-check",
            """TYPE=generic
AGENT=test-agent
TESTER=test-agent
REVIEWER=code-reviewer
""",
        )
        self.make_dirty(no_check)
        cases.append(("no-check", no_check, "Paketprüfung fehlt"))

        for name, project, expected in cases:
            with self.subTest(name=name):
                result = self.run_runner(
                    project, VIBE_KEEP_CHANGES="1", VIBE_MAX_PACKAGES="1"
                )
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 2, output)
                self.assertIn(expected, output)
                self.assertEqual(self.agent_calls(), [])
                # Der unsaubere Arbeitsbaum ist mit der Option kein
                # blockierender Befund mehr; ein bloßer Hinweis wäre erlaubt.
                self.assertNotIn("BLOCKIERT: Arbeitsbaum", output)


# ---------------------------------------------------------------------------
# CLI: vibe run --keep-changes
# ---------------------------------------------------------------------------
class KeepChangesCliFixture(unittest.TestCase):
    """Geladenes CLI-Modul ohne echte tmux-, Modell- oder Netzaufrufe."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.project = self.root / "proj"
        support.init_repo(self.project)
        support.write_project(self.project, PROJECT_ENV, feedback=FEEDBACK)
        support.commit_all(self.project, "Ausgangsstand")
        self.runtime = self.root / "_logs"
        self.cli = load_cli(self.root, self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def patches(self, **overrides):
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(list(argv))
            if "has-session" in argv:
                return 1, ""
            return 0, ""

        class Registry:
            def start(self, **kwargs):
                return {"id": "proj-test"}

            def finish(self, *args, **kwargs):
                return None

        values = {
            "run": fake_run,
            "tmux_has": lambda name: False,
            "project_map": lambda: {"proj": str(self.project)},
            "ppath": lambda name: str(self.project),
            "is_init": lambda name: True,
            "sandbox_status": lambda name: {"enabled": False},
            "pause_after_active": lambda name: False,
            "penv": lambda name: {"AGENT": "test-agent"},
            "vibe_agent_status": lambda: {
                "name": "",
                "model": "",
                "configured": False,
            },
            "require_agent": lambda agent: agent,
            "ensure_opencode_password": lambda: str(
                self.runtime / "opencode.password"
            ),
            "run_agent_selection": lambda name, agent: "",
            "run_key": lambda name: "proj",
            "sess": lambda name: "vibe-proj",
            "logpath": lambda name, kind="run": str(
                self.runtime / (name + ".log")
            ),
            "run_registry": lambda: Registry(),
        }
        values.update(overrides)
        return values, calls

    def invoke_main(self, argv, **overrides):
        values, calls = self.patches(**overrides)
        buffer = io.StringIO()
        code = None
        with mock.patch.multiple(self.cli, **values), mock.patch.object(
            self.cli.vibe_runs, "rotate_log", lambda *args, **kwargs: None
        ), mock.patch.dict(
            os.environ, {"VIBE_NO_CONTAINER": "1"}
        ), mock.patch.object(
            sys, "argv", list(argv)
        ), contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(
            buffer
        ):
            try:
                self.cli.main()
            except SystemExit as error:
                code = error.code
        return buffer.getvalue(), calls, code

    def invoke_run(self, **overrides):
        values, calls = self.patches(**overrides)
        buffer = io.StringIO()
        code = None
        with mock.patch.multiple(self.cli, **values), mock.patch.object(
            self.cli.vibe_runs, "rotate_log", lambda *args, **kwargs: None
        ), contextlib.redirect_stderr(buffer):
            try:
                self.cli.cmd_run("proj", out=buffer)
            except SystemExit as error:
                code = error.code
        return buffer.getvalue(), calls, code

    def new_session_calls(self, calls):
        return [call for call in calls if "new-session" in call]


class CliKeepChangesTest(KeepChangesCliFixture):
    """Verhalten 1: Die CLI reicht die Absicht an den Läufer weiter."""

    def test_cli_run_with_keep_changes_exports_the_intent(self):
        output, calls, code = self.invoke_main(
            ["vibe", "run", "proj", "--keep-changes"]
        )

        self.assertIsNone(code, output)
        sessions = self.new_session_calls(calls)
        self.assertEqual(len(sessions), 1, calls)
        flattened = " ".join(sessions[0])
        self.assertIn("VIBE_KEEP_CHANGES=1", flattened)
        self.assertIn("VIBE_PREFLIGHT_ASSIST=1", flattened)
        self.assertNotIn("--keep-changes", flattened)

    def test_cli_run_without_keep_changes_does_not_export_the_intent(self):
        output, calls, code = self.invoke_main(["vibe", "run", "proj"])

        self.assertIsNone(code, output)
        sessions = self.new_session_calls(calls)
        self.assertEqual(len(sessions), 1, calls)
        flattened = " ".join(sessions[0])
        self.assertNotIn("VIBE_KEEP_CHANGES=1", flattened)
        self.assertIn("VIBE_PREFLIGHT_ASSIST=1", flattened)

    def test_cli_run_accepts_an_agent_before_keep_changes(self):
        output, calls, code = self.invoke_main(
            ["vibe", "run", "proj", "test-agent", "--keep-changes"]
        )

        self.assertIsNone(code, output)
        sessions = self.new_session_calls(calls)
        self.assertEqual(len(sessions), 1, calls)
        flattened = " ".join(sessions[0])
        self.assertIn("VIBE_KEEP_CHANGES=1", flattened)
        self.assertIn("test-agent", flattened)
        self.assertNotIn("--keep-changes", flattened)


# ---------------------------------------------------------------------------
# AGENTS.md: verwalteter Block bei Änderungen nicht überschreiben
# ---------------------------------------------------------------------------
class AgentsRulesTest(KeepChangesCliFixture):
    """Verhalten 4: ``vibe run`` schreibt AGENTS.md nicht mehr (GH-76)."""

    def prepare(self):
        (self.project / "AGENTS.md").write_text(OLD_AGENTS, encoding="utf-8")
        support.commit_all(self.project, "AGENTS.md")

    def test_uncommitted_agents_change_is_not_rewritten(self):
        self.prepare()
        changed = OLD_AGENTS.replace(
            "Eigene Regel", "Eigene geänderte Regel"
        )
        (self.project / "AGENTS.md").write_text(changed, encoding="utf-8")

        output, calls, code = self.invoke_run()

        self.assertIsNone(code, output)
        self.assertEqual(
            changed, (self.project / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertIn("ALTER REGELSATZ", changed)
        self.assertNotIn("Allgemeine Regeln", output)
        status = support.git(
            self.project, "status", "--porcelain", "--", "AGENTS.md"
        ).stdout
        self.assertIn("M AGENTS.md", status)
        self.assertEqual(len(self.new_session_calls(calls)), 1)

    def test_clean_agents_file_is_left_untouched(self):
        self.prepare()

        output, calls, code = self.invoke_run()

        self.assertIsNone(code, output)
        self.assertEqual(
            OLD_AGENTS,
            (self.project / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertNotIn("Allgemeine Regeln", output)
        self.assertEqual(len(self.new_session_calls(calls)), 1)

# ---------------------------------------------------------------------------
# Web-API: POST /api/run mit keep_changes
# ---------------------------------------------------------------------------
FAKE_TMUX = r'''#!/usr/bin/env python3
"""Zeichnet tmux-Aufrufe auf und verhält sich wie ein frischer Server."""
import json
import os
import sys

args = sys.argv[1:]
# V-026: Laufsitzungen liegen auf einem eigenen tmux-Server; der optionale
# Zusatz ``-L <socket>`` steht dann vor dem eigentlichen Befehl.
if args[:1] == ["-L"] and len(args) > 1:
    args = args[2:]
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
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class WebRunApiTest(unittest.TestCase):
    """Verhalten 5: Das Dashboard kann die Absicht über die API senden."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        support.write_agents(cls.agents, "test-agent", "code-reviewer")
        cls.project = cls.root / "proj"
        support.init_repo(cls.project)
        support.write_project(cls.project, PROJECT_ENV, feedback=FEEDBACK)
        project_agent = cls.project / ".opencode" / "agents" / "test-agent.md"
        project_agent.parent.mkdir(parents=True)
        project_agent.write_text(
            "---\ndescription: Testagent\nmode: subagent\n---\n",
            encoding="utf-8",
        )
        support.commit_all(cls.project, "Ausgangsstand")
        (cls.project / "unfertig.txt").write_text(
            "unfertig\n", encoding="utf-8"
        )
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
        cls.env = env
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
                    with __import__("socket").create_connection(
                        ("127.0.0.1", cls.port), timeout=0.5
                    ):
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
        if self.tmux_log.exists():
            self.tmux_log.unlink()

    def request(self, method, path, body=None, token=True):
        import http.client

        headers = {"Host": "127.0.0.1:%d" % self.port}
        if token:
            headers["X-Token"] = self.token
        payload = None
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.port, timeout=15
        )
        try:
            connection.request(method, path, body=payload, headers=headers)
            response = connection.getresponse()
            text = response.read().decode("utf-8", "replace")
            return response.status, text
        finally:
            connection.close()

    def tmux_records(self):
        if not self.tmux_log.exists():
            return []
        return [
            json.loads(line)
            for line in self.tmux_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def new_sessions(self):
        return [
            " ".join(record["args"])
            for record in self.tmux_records()
            if record.get("args", [])[:1] == ["new-session"]
        ]

    def status_snapshot(self):
        return support.git(
            self.project, "status", "--porcelain=v1", "-uall"
        ).stdout

    def test_api_run_with_keep_changes_exports_intent_and_names_files(self):
        before = self.status_snapshot()

        status, body = self.request(
            "POST", "/api/run",
            {"name": "proj", "keep_changes": True},
        )

        self.assertEqual(status, 200, body)
        data = json.loads(body)
        self.assertTrue(data.get("ok"), data)
        message = data.get("message", "")
        self.assertIn("unfertig.txt", message)
        sessions = self.new_sessions()
        self.assertEqual(len(sessions), 1, self.tmux_records())
        self.assertIn("VIBE_KEEP_CHANGES=1", sessions[0])
        self.assertEqual(self.status_snapshot(), before)

    def test_api_run_without_keep_changes_does_not_export_the_intent(self):
        status, body = self.request("POST", "/api/run", {"name": "proj"})

        self.assertEqual(status, 200, body)
        data = json.loads(body)
        self.assertTrue(data.get("ok"), data)
        sessions = self.new_sessions()
        self.assertEqual(len(sessions), 1, self.tmux_records())
        self.assertNotIn("VIBE_KEEP_CHANGES=1", sessions[0])


if __name__ == "__main__":
    unittest.main()
