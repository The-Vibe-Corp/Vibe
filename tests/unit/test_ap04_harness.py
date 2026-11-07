"""Tests für die austauschbare Harness-Schicht (AP04).

Die Tests beschreiben das Verhalten der neuen Schicht unabhängig von der
Implementierung: Default bleibt opencode, die Auswahl wird atomar gespeichert,
Pi wird als gleichwertiger Harness beschrieben, und Agentenläufe erhalten für
beide Harnesses eine nachvollziehbare Argumentliste. Externe Programme werden
ausschließlich durch Attrappen in temporären Verzeichnissen ersetzt.
"""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
sys.path.insert(0, str(BIN))

import vibe_harness  # noqa: E402  (bewusster Import nach sys.path-Anpassung)


def write_fake(directory, name, body):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/usr/bin/env bash\n" + body + "\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


FAKE_PI = """\
if [ "$1" = "--version" ]; then
  printf '0.72.0\\n'
  exit 0
fi
if [ "$1" = "--list-models" ]; then
  printf 'anthropic/claude-sonnet\\nopenai/gpt-test\\n'
  exit 0
fi
echo "unerwarteter Aufruf: $*" >&2
exit 2
"""

FAKE_OPENCODE = """\
if [ "$1" = "--version" ]; then
  printf 'opencode v2.1.4\\n'
  exit 0
fi
if [ "$1" = "models" ]; then
  printf 'opencode/model-a\\n'
  exit 0
fi
echo "unerwarteter Aufruf: $*" >&2
exit 2
"""


class HarnessFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / "_toolchain"
        self.project = self.root / "proj"
        self.project.mkdir()
        (self.project / ".opencode" / "agents").mkdir(parents=True)
        self.fakebin = self.root / "fakebin"
        self.fakebin.mkdir()

    def tearDown(self):
        self.tmp.cleanup()


class HarnessSelectionTest(HarnessFixture):
    def test_default_is_opencode_when_no_selection_file_exists(self):
        self.assertEqual(vibe_harness.read_selection(self.state, environ={}), "opencode")

    def test_selection_is_stored_and_survives_a_new_read(self):
        path = vibe_harness.write_selection(self.state, "pi")

        self.assertTrue(path.endswith("harness.json"))
        self.assertEqual(vibe_harness.read_selection(self.state, environ={}), "pi")
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual(data["harness"], "pi")

    def test_unknown_harness_is_rejected_without_touching_the_file(self):
        vibe_harness.write_selection(self.state, "opencode")
        with self.assertRaises(vibe_harness.HarnessError):
            vibe_harness.write_selection(self.state, "unbekannt")

        self.assertEqual(vibe_harness.read_selection(self.state, environ={}), "opencode")

    def test_corrupt_selection_file_is_reported_instead_of_silently_using_opencode(self):
        self.state.mkdir(parents=True)
        path = self.state / "harness.json"
        path.write_text("{kaputt", encoding="utf-8")

        with self.assertRaises(vibe_harness.HarnessError) as caught:
            vibe_harness.read_selection(self.state, environ={})
        self.assertIn("harness.json", str(caught.exception))

    def test_environment_override_wins_and_is_validated(self):
        vibe_harness.write_selection(self.state, "pi")

        self.assertEqual(
            vibe_harness.read_selection(self.state, environ={"VIBE_HARNESS": "opencode"}),
            "opencode",
        )
        with self.assertRaises(vibe_harness.HarnessError):
            vibe_harness.read_selection(self.state, environ={"VIBE_HARNESS": "nein"})

    def test_both_harnesses_are_listed_with_pi_as_first_alternative(self):
        ids = vibe_harness.harness_ids()

        self.assertEqual(ids[0], "opencode")
        self.assertIn("pi", ids)
        self.assertTrue(vibe_harness.definition("pi")["alternative"])


class HarnessProbeTest(HarnessFixture):
    def test_fake_pi_binary_is_reported_ready(self):
        binary = write_fake(self.fakebin, "pi", FAKE_PI)

        result = vibe_harness.probe("pi", binary=str(binary))

        self.assertTrue(result["installed"])
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["version"], "0.72.0")

    def test_missing_pi_is_reported_with_the_binary_name(self):
        result = vibe_harness.probe(
            "pi", binary=str(self.root / "fehlt" / "pi"), runner=lambda argv, timeout: (127, "fehlt")
        )

        self.assertFalse(result["installed"])
        self.assertEqual(result["status"], "missing")
        self.assertIn("pi", result["message"])

    def test_failing_binary_is_reported_as_error(self):
        binary = write_fake(self.fakebin, "pi", "echo kaputt >&2\nexit 7")
        result = vibe_harness.probe("pi", binary=str(binary))

        self.assertFalse(result["installed"])
        self.assertEqual(result["status"], "error")
        self.assertIn("7", result["message"])


class HarnessSetupPlanTest(HarnessFixture):
    def test_pi_plan_names_the_official_installer_and_node_requirement(self):
        plan = vibe_harness.setup_plan("pi", which=lambda name: None)

        self.assertEqual(plan["harness"], "pi")
        self.assertFalse(plan["installed"])
        self.assertEqual(
            plan["install_command"],
            ["npm", "install", "-g", "--ignore-scripts", "@earendil-works/pi-coding-agent"],
        )
        self.assertIn("22.19", plan["hint"])
        self.assertIn("https://pi.dev", plan["official"])

    def test_opencode_plan_keeps_the_existing_npm_package(self):
        plan = vibe_harness.setup_plan("opencode", which=lambda name: None)

        self.assertEqual(plan["install_command"], ["npm", "install", "-g", "opencode-ai"])
        self.assertIn("https://opencode.ai", plan["official"])

    def test_installed_harness_needs_no_install_command(self):
        plan = vibe_harness.setup_plan("pi", which=lambda name: "/usr/bin/" + name)

        self.assertTrue(plan["installed"])
        self.assertEqual(plan["install_command"], [])

    def test_status_reports_selected_harness_and_both_entries(self):
        write_fake(self.fakebin, "pi", FAKE_PI)
        write_fake(self.fakebin, "opencode", FAKE_OPENCODE)

        status = vibe_harness.status(
            self.state,
            environ={"PATH": str(self.fakebin) + os.pathsep + os.environ.get("PATH", "")},
        )

        self.assertEqual(status["selected"], "opencode")
        entries = {item["harness"]: item for item in status["harnesses"]}
        self.assertTrue(entries["opencode"]["installed"])
        self.assertTrue(entries["pi"]["installed"])
        self.assertEqual(entries["pi"]["version"], "0.72.0")


class HarnessRunTest(HarnessFixture):
    def test_opencode_run_command_keeps_the_tested_arguments(self):
        argv = vibe_harness.run_argv(
            "opencode",
            "Aufgabe",
            self.project,
            agent="coder",
            model="opencode/model-a",
            title="proj F1",
            binary="opencode-fake",
            server_url="",
        )

        self.assertEqual(
            argv,
            [
                "opencode-fake",
                "run",
                "--standalone",
                "--auto",
                "--thinking",
                "--agent",
                "coder",
                "--model",
                "opencode/model-a",
                "--title",
                "proj F1",
                "Aufgabe",
            ],
        )

    def test_opencode_uses_a_shared_server_when_one_is_given(self):
        argv = vibe_harness.run_argv(
            "opencode", "Aufgabe", self.project, agent="coder",
            binary="opencode-fake", server_url="http://127.0.0.1:4096",
        )

        self.assertIn("--server", argv)
        self.assertNotIn("--standalone", argv)

    def test_pi_run_command_uses_print_mode_and_the_agent_prompt(self):
        agent = self.project / ".opencode" / "agents" / "coder.md"
        agent.write_text(
            "---\ndescription: Coder\nmode: primary\n---\nDu bist der Coder.\n",
            encoding="utf-8",
        )

        argv = vibe_harness.run_argv(
            "pi",
            "Aufgabe",
            self.project,
            agent="coder",
            model="anthropic/claude-sonnet",
            title="proj F1",
            binary="pi-fake",
        )

        self.assertEqual(argv[:2], ["pi-fake", "--print"])
        self.assertIn("--model", argv)
        self.assertIn("anthropic/claude-sonnet", argv)
        self.assertIn("--name", argv)
        self.assertEqual(argv[-2], "--")
        self.assertIn("Du bist der Coder.", argv[-1])
        self.assertIn("Aufgabe", argv[-1])

    def test_pi_run_without_an_agent_file_is_refused(self):
        with self.assertRaises(vibe_harness.HarnessError) as caught:
            vibe_harness.run_argv("pi", "Aufgabe", self.project, agent="fehlt", binary="pi-fake")

        self.assertIn("fehlt", str(caught.exception))


class HarnessModelListTest(HarnessFixture):
    def test_pi_models_are_parsed_from_the_list_command(self):
        binary = write_fake(self.fakebin, "pi", FAKE_PI)

        result = vibe_harness.list_models("pi", binary=str(binary))

        self.assertTrue(result["ok"])
        self.assertEqual(result["models"], ["anthropic/claude-sonnet", "openai/gpt-test"])

    def test_missing_pi_model_list_is_a_reported_error(self):
        result = vibe_harness.list_models(
            "pi", binary=str(self.fakebin / "pi"), runner=lambda argv, timeout: (127, "fehlt")
        )

        self.assertFalse(result["ok"])
        self.assertIn("pi", result["error"])


class HarnessCliTest(HarnessFixture):
    def env(self, extra=None):
        value = os.environ.copy()
        for key in list(value):
            if key.startswith("VIBE_") or key in ("HOME", "XDG_CONFIG_HOME", "XDG_CONFIG_DIR"):
                value.pop(key, None)
        value.update(
            {
                "VIBE": str(self.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_STATE": str(self.state),
                "VIBE_INSTALL": str(self.state),
                "VIBE_RUNTIME": str(self.root / "_logs"),
                "VIBE_CONFIG_FILE": str(self.root / "home" / ".config" / "vibe" / "config.json"),
                "VIBE_AGENTS_DIR": str(self.root / "home" / ".config" / "opencode" / "agents"),
                "HOME": str(self.root / "home"),
                "PATH": str(self.fakebin) + os.pathsep + value.get("PATH", ""),
            }
        )
        value.update(extra or {})
        return value

    def cli(self, *arguments, env=None):
        return subprocess.run(
            [sys.executable, str(BIN / "vibe"), *arguments],
            env=env or self.env(), capture_output=True, text=True, timeout=60,
        )

    def test_cli_use_switches_the_harness_and_status_names_it(self):
        write_fake(self.fakebin, "pi", FAKE_PI)
        write_fake(self.fakebin, "opencode", FAKE_OPENCODE)

        used = self.cli("harness", "use", "pi")
        self.assertEqual(used.returncode, 0, used.stdout + used.stderr)
        self.assertEqual(vibe_harness.read_selection(self.state, environ={}), "pi")

        status = self.cli("harness", "status")
        self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
        self.assertIn("Harness", status.stdout)
        self.assertIn("pi", status.stdout)
        self.assertIn("0.72.0", status.stdout)

    def test_cli_rejects_an_unknown_harness_and_keeps_the_selection(self):
        vibe_harness.write_selection(self.state, "opencode")

        result = self.cli("harness", "use", "unbekannt")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(vibe_harness.read_selection(self.state, environ={}), "opencode")


if __name__ == "__main__":
    unittest.main()
