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


NEXT_ITEM_ONCE = '''import os, sys
here = os.path.dirname(os.path.abspath(__file__))
count_path = os.path.join(here, "next-calls")
try:
    calls = int(open(count_path, encoding="utf-8").read())
except OSError:
    calls = 0
if calls:
    sys.exit(1)
open(count_path, "w", encoding="utf-8").write("1")
open("/tmp/next_id", "w", encoding="utf-8").write("F1")
open("/tmp/next_block", "w", encoding="utf-8").write(
    "- [ ] F1 Testpaket\\n  Beschreibung: Test\\n"
)
'''

NEXT_ITEM_ALWAYS = '''import sys
open("/tmp/next_id", "w", encoding="utf-8").write("F1")
open("/tmp/next_block", "w", encoding="utf-8").write(
    "- [ ] F1 Testpaket\\n  Beschreibung: Test\\n"
)
'''

FAKE_OPENCODE = '''#!/usr/bin/env bash
printf 'call\\n' >> "$VIBE_FAKE_CALLS"
exit "${VIBE_FAKE_RC:-0}"
'''

FAKE_CURL = '''#!/usr/bin/env bash
exit 7
'''

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
        self.install = self.root / "_toolchain"
        self.tool_bin = self.install / "bin"
        self.tool_bin.mkdir(parents=True)
        self.verify = self.install / "verify"
        self.verify.mkdir()
        self.runtime = self.root / "_logs"
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        shutil.copy(RUNNER, self.tool_bin / "vibe-run.sh")
        shutil.copy(BIN / "vibe_runs.py", self.tool_bin / "vibe_runs.py")
        (self.tool_bin / "vibe").write_text(FAKE_VIBE, encoding="utf-8")
        (self.tool_bin / "vibe").chmod(0o755)
        fakebin = self.root / "fakebin"
        fakebin.mkdir()
        for name, text in (("opencode", FAKE_OPENCODE), ("curl", FAKE_CURL)):
            path = fakebin / name
            path.write_text(text, encoding="utf-8")
            path.chmod(0o755)
        self.calls = self.root / "opencode.calls"
        self.fritz = self.root / "fritz.calls"

    def tearDown(self):
        self.tmp.cleanup()

    def project_env(self, verify, retries=2):
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n"
            "AGENT=tester\n"
            f'VERIFY_FULL="{verify}"\n'
            f"MAX_RETRIES={retries}\n",
            encoding="utf-8",
        )

    def run_runner(self, next_item, verify="true", retries=2, opencode_rc=0, packages=1):
        (self.verify / "next_item.py").write_text(next_item, encoding="utf-8")
        self.project_env(verify, retries)
        env = clean_env(
            self.root,
            self.home,
            VIBE_INSTALL=str(self.install),
            VIBE_RUNTIME=str(self.runtime),
            VIBE_MAX_PACKAGES=str(packages),
            VIBE_FAKE_CALLS=str(self.calls),
            VIBE_FAKE_FRITZ=str(self.fritz),
            VIBE_FAKE_RC=str(opencode_rc),
            PATH=str(self.root / "fakebin") + os.pathsep + os.environ.get("PATH", ""),
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
        result = self.run_runner(NEXT_ITEM_ONCE, verify="printf 'verify-ok\\n'")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.verify / "verify.sh").exists())
        self.assertFalse((self.home / ".config" / "schreibfuchs-verify.sha").exists())
        # Der Lauf hat wirklich ein Arbeitspaket ausgeführt; ein Abbruch vor der
        # Schleife würde sonst ebenfalls mit Exit 0 enden.
        self.assertIn("Arbeitspaket F1", self.log())
        self.assertEqual(
            self.calls.read_text(encoding="utf-8").splitlines(), ["call"]
        )
        self.assertIn("FERTIG", self.log())

    def test_runner_writes_a_separate_verification_log(self):
        result = self.run_runner(NEXT_ITEM_ONCE, verify="printf 'verify-ok\\n'")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Arbeitspaket F1", self.log())
        self.assertIn("=== Abschlussprüfung ===", self.log())
        self.assertIn("verify-ok", self.log())
        self.assertIn("verify-ok", self.log("proj.verify.log"))

    def test_retry_limit_stops_repeating_the_same_package(self):
        result = self.run_runner(
            NEXT_ITEM_ALWAYS, verify="true", retries=1, opencode_rc=1, packages=4
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Arbeitspaket F1", self.log())
        self.assertEqual(len(self.calls.read_text(encoding="utf-8").splitlines()), 2)
        self.assertIn("Überspringe F1 nach 2 Versuchen", self.log())
        self.assertIn("1 Wiederholungen", self.log())

    def test_failed_final_check_returns_its_exit_code(self):
        result = self.run_runner(NEXT_ITEM_ONCE, verify="exit 9")

        self.assertEqual(result.returncode, 9, result.stdout + result.stderr)


class FritzGateTest(CliFixture):
    def test_no_router_reconnect_without_an_explicit_automation_setting(self):
        self.assertFalse(self.cli.fritz_automation())
        with mock.patch.object(self.cli, "fritz_reconnect") as reconnect:
            outcome = self.cli.fritz_auto()
        self.assertFalse(outcome["ran"])
        reconnect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
