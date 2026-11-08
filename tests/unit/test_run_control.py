"""Abnahme V-015: Agentenläufe und Projektprüfungen sind entkoppelt.

Geprüft werden eindeutige Lauf-IDs und Sitzungen, getrennte Logs und
Prüfprotokolle, typabhängige Prüfadapter mit echten Exitcodes, das gezielte
Stoppen eines Laufs, das Wiederholungslimit, die Logrotation und ein
Nicht-Android-Lauf ohne Android-Abnahmedateien. Es werden keine Modell-,
Router- oder Android-Aufrufe ausgeführt.
"""
import hashlib
import importlib.machinery
import importlib.util
import json
import os
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

    def write_project(self, verify, retries, feedback):
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
        (self.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n" + feedback, encoding="utf-8"
        )
        (self.project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")

    def run_runner(
        self, verify="true", retries=2, opencode_rc=0, packages=1, feedback=None
    ):
        feedback = feedback or "- [ ] F1 Testpaket\n  Beschreibung: Test\n"
        self.write_project(verify, retries, feedback)
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
            'if [ "$1" = "has-session" ]; then\n'
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

    def run_cli_with_tmux(self, *args):
        return self.run_cli(
            *args,
            PATH=str(self.fakebin) + os.pathsep + os.environ.get("PATH", ""),
            FAKE_TMUX_SESSIONS=str(self.sessions_file),
            FAKE_TMUX_CALLS=str(self.calls_file),
        )

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


if __name__ == "__main__":
    unittest.main()
