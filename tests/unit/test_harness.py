"""Harness: Auswahl, Prüfung, Lauf, Fähigkeiten, Ereignis-Flags, Pi-Übersetzung und Dashboard-API.

Aufruf: python3 -m unittest tests.unit.test_harness -v
"""


# ===========================================================================
# Tests für die austauschbare Harness-Schicht
# ===========================================================================

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


HARNESS_FAKE_PI = """\
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
        binary = write_fake(self.fakebin, "pi", HARNESS_FAKE_PI)

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
        write_fake(self.fakebin, "pi", HARNESS_FAKE_PI)
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
        binary = write_fake(self.fakebin, "pi", HARNESS_FAKE_PI)

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
        write_fake(self.fakebin, "pi", HARNESS_FAKE_PI)
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


# ===========================================================================
# Unit-Abnahme (Teil 1): Fähigkeitsschicht des Harness
# ===========================================================================

import builtins
import importlib.machinery
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HARNESS_PY = REPO / "bin" / "vibe_harness.py"
# vibe_harness importiert Schwestermodule aus bin; ohne Pfad bricht das Laden.
sys.path.insert(0, str(REPO / "bin"))


def load_module(name="vibe_harness_ap14_under_test"):
    """Lädt bin/vibe_harness.py als Testunterlage (ohne Installation)."""
    loader = importlib.machinery.SourceFileLoader(name, str(HARNESS_PY))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


MODULE = load_module()


class SupportsCapabilityTest(unittest.TestCase):
    """AK: Fähigkeitsschicht je Harness — opencode ja, Pi nein, unbekannt nein."""

    def test_opencode_reports_both_capabilities(self):
        self.assertTrue(
            MODULE.supports("opencode", "steer"),
            "opencode muss 'steer' unterstützen (Zusatzanweisungen an den "
            "Hauptagenten und jeden Subagenten).",
        )
        self.assertTrue(
            MODULE.supports("opencode", "continue"),
            "opencode muss 'continue' unterstützen (Fortsetzung in derselben "
            "Session).",
        )

    def test_pi_reports_no_capabilities(self):
        self.assertFalse(
            MODULE.supports("pi", "steer"),
            "Pi läuft im Print-Modus (--no-session): keine Zusatzanweisungen.",
        )
        self.assertFalse(
            MODULE.supports("pi", "continue"),
            "Pi läuft im Print-Modus (--no-session): keine Session-Fortsetzung.",
        )

    def test_unknown_or_invalid_names_report_no_capability(self):
        for name in ("unbekannt", "", None, "   ", "pi2", "open code"):
            for capability in ("steer", "continue"):
                self.assertFalse(
                    MODULE.supports(name, capability),
                    f"Harness {name!r} mit Fähigkeit {capability!r} muss "
                    "falsch melden, nicht abstürzen oder wahr erfinden.",
                )

    def test_unknown_capability_is_rejected_with_false(self):
        for capability in ("unbekannt", "", None, "STEER", "steer "):
            self.assertFalse(
                MODULE.supports("opencode", capability),
                f"Unbekannte Fähigkeit {capability!r} muss falsch melden.",
            )
            self.assertFalse(MODULE.supports("pi", capability))

    def test_supports_is_pure_no_process_no_file_access(self):
        """AK 'kompatibel mit jedem konfigurierbaren Harness': Die Abfrage ist
        rein — kein Prozessstart, kein Dateizugriff. Ein Verstoß bricht den
        Test mit einer klaren Meldung ab."""
        errors = []

        def deny(reason):
            def _deny(*args, **kwargs):
                errors.append(reason)
                raise AssertionError(reason)
            return _deny

        # Prozessstart global sperren (nicht am Modul des Harness), damit der
        # Reinheitsnachweis auch ohne "import subprocess" in vibe_harness gilt.
        with mock.patch(
            "subprocess.Popen", side_effect=deny("Prozessstart Popen")
        ), mock.patch(
            "subprocess.run", side_effect=deny("Prozessstart run")
        ), mock.patch(
            "subprocess.call", side_effect=deny("Prozessstart call")
        ), mock.patch(
            "subprocess.check_output",
            side_effect=deny("Prozessstart check_output"),
        ), mock.patch.object(
            MODULE.os, "system", side_effect=deny("Prozessstart system")
        ), mock.patch.object(
            MODULE.os, "open", side_effect=deny("Dateizugriff os.open")
        ), mock.patch.object(
            builtins, "open", side_effect=deny("Dateizugriff open")
        ):
            results = {
                (name, capability): MODULE.supports(name, capability)
                for name in ("opencode", "pi", "unbekannt")
                for capability in ("steer", "continue")
            }

        self.assertEqual(
            [], errors,
            "supports() darf weder Prozesse starten noch Dateien lesen: "
            + "; ".join(errors),
        )
        self.assertEqual(
            (True, True),
            (results[("opencode", "steer")], results[("opencode", "continue")]),
        )
        self.assertFalse(results[("pi", "steer")])
        self.assertFalse(results[("unbekannt", "continue")])
        # Wiederholte Aufrufe liefern dasselbe Ergebnis (deterministisch).
        self.assertTrue(MODULE.supports("opencode", "steer"))


# ===========================================================================
# Tests der Harness-Installation
# ===========================================================================

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(BIN))

import vibe_harness  # noqa: E402  (bewusster Import nach sys.path-Anpassung)

PI_COMMAND = [
    "npm", "install", "-g", "--ignore-scripts",
    "@earendil-works/pi-coding-agent",
]


class HarnessInstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.empty_path = self.root / "leer"
        self.empty_path.mkdir()
        self.environ = {"PATH": str(self.empty_path)}

    def tearDown(self):
        self.tmp.cleanup()

    def test_06_missing_npm_reports_exit_127_and_stays_missing(self):
        calls = []

        def runner(argv, timeout):
            calls.append(list(argv))
            if argv[0] == "npm":
                return 127, "npm: command not found"
            return 127, "pi: command not found"

        result = vibe_harness.install(
            "pi", which=lambda name: None, runner=runner,
            environ=self.environ)

        self.assertEqual("pi", result["harness"])
        self.assertEqual(127, result["code"])
        self.assertFalse(result["already"])
        self.assertIn(PI_COMMAND, calls,
                      "Der Registry-Befehl wurde nicht exakt aufgerufen: "
                      + repr(calls))
        self.assertFalse(result["probe"]["installed"],
                         "Die erneute Probe meldet Pi fälschlich als "
                         "installiert: " + repr(result["probe"]))
        self.assertEqual("missing", result["probe"]["status"],
                         "Die erneute Probe meldet nicht 'missing': "
                         + repr(result["probe"]))

    def test_07_successful_runner_triggers_a_fresh_ready_probe(self):
        calls = []

        def runner(argv, timeout):
            calls.append(list(argv))
            if argv[0] == "npm":
                return 0, "added 1 package"
            return 0, "0.72.0"

        result = vibe_harness.install(
            "pi", which=lambda name: None, runner=runner,
            environ=self.environ)

        self.assertEqual("pi", result["harness"])
        self.assertEqual(0, result["code"])
        self.assertFalse(result["already"])
        self.assertIn(PI_COMMAND, calls,
                      "Der Registry-Befehl wurde nicht exakt aufgerufen: "
                      + repr(calls))
        probe = result["probe"]
        self.assertTrue(probe["installed"],
                        "Die erneute Probe meldet Pi nicht als installiert: "
                        + repr(probe))
        self.assertEqual("ready", probe["status"],
                         "Die erneute Probe ist nicht 'ready': " + repr(probe))
        self.assertEqual("0.72.0", probe["version"],
                         "Die erneute Probe liest die Version nicht: "
                         + repr(probe))

    def test_08_already_installed_runs_no_install_command(self):
        calls = []

        def runner(argv, timeout):
            calls.append(list(argv))
            return 0, "0.72.0"

        result = vibe_harness.install(
            "pi", which=lambda name: "/usr/bin/" + name, runner=runner,
            environ=self.environ)

        self.assertEqual("pi", result["harness"])
        self.assertEqual(0, result["code"])
        self.assertTrue(result["already"],
                        "Ein bereits installierter Harness wird nicht als "
                        "already gemeldet: " + repr(result))
        self.assertEqual("", result["output"],
                         "Ein bereits installierter Harness liefert eine "
                         "Befehlsausgabe: " + repr(result))
        self.assertFalse(
            [argv for argv in calls if argv and argv[0] == "npm"],
            "Für einen bereits installierten Harness wurde der "
            "Installationsbefehl ausgeführt: " + repr(calls))

    def test_09_unknown_harness_raises_harness_error(self):
        with self.assertRaises(vibe_harness.HarnessError):
            vibe_harness.install(
                "unbekannt", which=lambda name: None,
                environ=self.environ)


# ===========================================================================
# Unit-Abnahme (Teil 2): Harness-Schnittstelle für Pi-JSON-Ereignisse
# ===========================================================================

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(BIN))

import vibe_harness  # noqa: E402


def write_script(directory, name, body):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


# Erwartete Argumentlisten der Baseline (Reg tests ohne den Befund):
# exakt die Aufrufe aus tests/unit/test_ap04_harness.py (HarnessRunTest).
PI_BASELINE_ARGV = ["pi-fake", "--print", "--no-session", "--",
                    "Du bist der Coder.\n\n---\n\nAufgabe"]
OPENCODE_BASELINE_ARGV = [
    "opencode-fake", "run", "--standalone", "--auto", "--thinking",
    "--agent", "coder", "--model", "opencode/model-a",
    "--title", "proj F1", "Aufgabe",
]


class HarnessArgvFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        agent_dir = self.project / ".opencode" / "agents"
        agent_dir.mkdir(parents=True)
        (agent_dir / "coder.md").write_text(
            "---\ndescription: Coder\nmode: primary\n---\nDu bist der Coder.\n",
            encoding="utf-8",
        )
        self.addCleanup(self.tmp.cleanup)


class PiRunArgvEventsTest(HarnessArgvFixture):
    """AK4: run_argv events-Flag für Pi."""

    # 1. Name: test_pi_events_true_inserts_json_mode_before_the_option_end
    #    [AK4] Vorbedingung: Pi-Agentendatei vorhanden. Aktion:
    #    run_argv("pi", ..., events=True). Erwartung: die Argumente
    #    ["--mode","json"] erscheinen genau einmal, zusammenhängend, vor
    #    der Optionsgrenze "--"; die letzte Aufgabe bleibt das
    #    letzte Argument; "--print"/"--no-session" bleiben.
    #    Fehlerfall: Argumente fehlen, stehen hinter "--" oder das
    #    Baseline-Verhalten ändert sich.
    def test_pi_events_true_inserts_json_mode_before_the_option_end(self):
        argv = vibe_harness.run_argv(
            "pi", "Aufgabe", self.project, agent="coder",
            binary="pi-fake", events=True,
        )

        self.assertIn(["--mode", "json"],
                      [argv[i:i + 2] for i in range(len(argv) - 1)],
                      f"--mode json muss zusammenhängend erscheinen: {argv}")
        self.assertEqual(1, argv.count("--mode"), f"Genau einmal: {argv}")
        self.assertEqual(1, argv.count("json"), f"Genau einmal: {argv}")
        self.assertLess(
            argv.index("--mode"), argv.index("--"),
            "--mode muss vor der Optionsgrenze -- stehen: " + repr(argv),
        )
        stripped = argv.copy()
        del stripped[argv.index("--mode"):argv.index("--mode") + 2]
        self.assertEqual(
            PI_BASELINE_ARGV, stripped,
            "Die restliche Reihenfolge darf sich nicht ändern: " + repr(argv),
        )

    # 2. Name: test_pi_events_false_is_byte_identical_to_ap04_tests [AK4]
    #    Vorbedingung: Pi-Agentendatei vorhanden. Aktion:
    #    run_argv("pi", ..., events=False). Erwartung: exakt die bisher
    #    geprüfte Argumentliste der AP04-Tests (kein --mode, kein json).
    def test_pi_events_false_is_byte_identical_to_ap04_tests(self):
        argv = vibe_harness.run_argv(
            "pi", "Aufgabe", self.project, agent="coder",
            binary="pi-fake", events=False,
        )

        self.assertEqual(PI_BASELINE_ARGV, argv)

    # 3. Name: test_pi_default_without_events_flag_is_unchanged [AK4]
    #    Vorbedingung: wie 2. Aktion: run_argv ohne events-Parameter.
    #    Erwartung: wie bei dem Aufruf der AP04-Tests (default False).
    def test_pi_default_without_events_flag_is_unchanged(self):
        argv = vibe_harness.run_argv(
            "pi", "Aufgabe", self.project, agent="coder", binary="pi-fake",
        )

        self.assertEqual(PI_BASELINE_ARGV, argv)


class OpencodeRunArgvEventsTest(HarnessArgvFixture):
    """AK4: Für opencode ändert sich mit events=True nichts (Regression)."""

    # 1. Name: test_opencode_events_true_changes_nothing [AK4]
    #    Vorbedingung: wie bisher (Agent, Modell, Titel). Aktion:
    #    run_argv("opencode", ..., events=True) und events=False.
    #    Erwartung: beide Aufrufe liefern exakt die bisher geprüfte
    #    Argumentliste; keine Pi-spezifische Einstellung (--mode, --json)
    #    erscheint.
    def test_opencode_events_true_changes_nothing(self):
        plain = vibe_harness.run_argv(
            "opencode", "Aufgabe", self.project, agent="coder",
            model="opencode/model-a", title="proj F1",
            binary="opencode-fake", server_url="",
        )
        events = vibe_harness.run_argv(
            "opencode", "Aufgabe", self.project, agent="coder",
            model="opencode/model-a", title="proj F1",
            binary="opencode-fake", server_url="", events=True,
        )

        self.assertEqual(OPENCODE_BASELINE_ARGV, plain)
        self.assertEqual(plain, events)


FAKE_PI_CLI = """\
#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  printf '0.72.0\\n'
  exit 0
fi
for argument in "$@"; do
  printf '%s\\0' "$argument"
done >> "$FAKE_PI_ARGS_PATH"
printf 'PI_ARGS_RECORD_END\\0' >> "$FAKE_PI_ARGS_PATH"
exit 0
"""


class HarnessCliJsonFlagTest(HarnessArgvFixture):
    """AK4: CLI-Flag --json beim Unterbefehl run ist da und bleibt ohne
    Flag beim bisherigen Verhalten (kein --mode json)."""

    def fakebin(self):
        fake = self.root / "fakebin"
        write_script(fake, "pi", FAKE_PI_CLI)
        return fake

    def env(self):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX"):
                env.pop(key, None)
        env.update({
            "PATH": str(self.fakebin()) + os.pathsep + env.get("PATH", ""),
            "FAKE_PI_ARGS_PATH": str(self.root / "pi.args"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        return env

    def pi_arg_lists(self):
        path = self.root / "pi.args"
        self.assertTrue(path.exists(), "pi wurde nicht aufgerufen")
        raw = path.read_bytes()
        tokens = raw.decode("utf-8", "surrogateescape").split("\0")
        records, current = [], []
        for token in tokens:
            if token == "PI_ARGS_RECORD_END":
                records.append(current)
                current = []
            elif token:
                current.append(token)
        return records

    def cli(self, *extra):
        return subprocess.run(
            [sys.executable, str(BIN / "vibe_harness.py"), "run",
             "--harness", "pi", "--project", str(self.project),
             "--agent", "coder", "--title", "proj B6",
             "--prompt", "Aufgabe von CLI", *extra],
            env=self.env(), capture_output=True, text=True, timeout=60,
        )

    # 1. Name: test_cli_run_json_flag_invokes_pi_with_json_mode [AK4]
    #    Vorbedingung: Pi-Agentendatei im Projekt, Pi-Attrappe im PATH.
    #    Aktion: vibe_harness.py run ... --json. Erwartung: Exit-Code wie
    #    der Agentenprozess (0) und in der protokollierten Argumentliste
    #    stehen --mode und json vor der Optionsgrenze --.
    #    Fehlerfall: --json wird abgewiesen, ignoriert oder falsch
    #    positioniert.
    def test_cli_run_json_flag_invokes_pi_with_json_mode(self):
        result = self.cli("--json")

        self.assertEqual(
            0, result.returncode,
            f"--json muss vorhanden sein: {result.returncode}\n"
            + result.stdout + result.stderr,
        )
        records = self.pi_arg_lists()
        self.assertTrue(records, "pi wurde ohne Argumente aufgerufen")
        argv = records[-1]
        self.assertIn("--mode", argv)
        self.assertIn("json", argv)
        self.assertLess(
            argv.index("--mode"), argv.index("--"),
            "--mode muss vor der Optionsgrenze -- erscheinen",
        )
        self.assertIn("--print", argv)
        self.assertIn("--no-session", argv)

    # 2. Name: test_cli_run_without_json_flag_keeps_previous_behavior [AK4]
    #    Vorbedingung: wie 1. Aktion: vibe_harness.py run ohne --json.
    #    Erwartung: Exit-Code 0 und keine Pi-Ereignisargumente (--mode,
    #    json) in der Argumentliste (bisheriges Verhalten unberührt).
    def test_cli_run_without_json_flag_keeps_previous_behavior(self):
        result = self.cli()

        self.assertEqual(
            0, result.returncode,
            "Ohne --json bleibt das bisherige Verhalten: "
            + result.stdout + result.stderr,
        )
        for argv in self.pi_arg_lists():
            self.assertNotIn("--mode", argv, "Kein --mode ohne --json")
            self.assertNotIn("json", argv, "Kein json ohne --json")


# ===========================================================================
# Unit-Abnahme: (aktiver Agent, Subagenten-Tabs) funktioniert für Pi
# ===========================================================================

import http.client
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

RUNS_PY = BIN / "vibe_runs.py"
WEB = BIN / "vibe-web.py"

sys.path.insert(0, str(BIN))

import vibe_runs  # noqa: E402

PI_SESSION = "ses-pi-4711"
TOOL_CALL = "call_abc123"
PI_BROKEN = "{kaputt"
PI_PLAIN = "Zufällige Ausgabe ohne JSON"


def pi_events(session=PI_SESSION):
    """Pi-JSONL-Ereignisse eines vollständigen einfachen Laufs (Pi-Doku 1.5.0).

    Reihenfolge und Form folgen exakt dem Beispielkapitel der offiziellen
    json.md: Session-Header, message_end für user/assistant (assistant
    content = Blockliste), tool_execution_start/update/end und die
    Rausch-Ereignisse turn_end/agent_end/agent_settled.
    """
    events = [
        {"type": "session", "version": 3, "id": session,
         "timestamp": "2026-01-01T00:00:00.000Z", "cwd": "/proj"},
        {"type": "agent_start"},
        {"type": "message_end",
         "message": {"role": "user", "content": "Arbeitspaket B6",
                     "timestamp": 1735689600000}},
        {"type": "message_end",
         "message": {"role": "assistant", "content": [
             {"type": "thinking", "text": "nachdenkliche Zeile"},
             {"type": "text", "text": "Hallo\nWelt"},
         ]}},
        {"type": "tool_execution_start", "toolCallId": "call_bash1",
         "toolName": "bash", "args": {"command": "ls -la"}},
        {"type": "tool_execution_update", "toolCallId": "call_bash1",
         "toolName": "bash", "args": {"command": "ls -la"},
         "partialResult": {"content": [{"type": "text", "text": "Datei1"}]}},
        {"type": "tool_execution_end", "toolCallId": "call_bash1",
         "toolName": "bash",
         "result": {"content": [{"type": "text", "text": "Datei1"}]},
         "isError": False, "durationMs": 4},
    ]
    return [json.dumps(event, ensure_ascii=False) for event in events]


def pi_task_events():
    """Pi-Ereignisse für ein erfasstes Subagenten-Werkzeug (task)."""
    events = [
        {"type": "tool_execution_start", "toolCallId": TOOL_CALL,
         "toolName": "task",
         "args": {"agent": "general", "description": "Testzusammenfassung",
                  "prompt": "Sammle Infos"}},
        {"type": "tool_execution_update", "toolCallId": TOOL_CALL,
         "toolName": "task",
         "args": {"agent": "general", "description": "Testzusammenfassung"},
         "partialResult": {"content": [{"type": "text", "text": "Teilausgabe"}]}},
        {"type": "tool_execution_end", "toolCallId": TOOL_CALL,
         "toolName": "task",
         "result": {"content": [{"type": "text", "text": "PONG"},
                                {"type": "text", "text": "Zweitzeile"}]},
         "isError": False, "durationMs": 7},
    ]
    return events


class PiTranslateFixture(unittest.TestCase):
    """Vorbedingung je Fall: frischer leerer Zustand (kein Session, keine
    Subagenten)."""

    def setUp(self):
        self.state = {"session": "", "subagents": []}

    def translate(self, event):
        return vibe_runs.translate_pi_event(event, self.state)


class PiEventTranslationTest(PiTranslateFixture):
    """AK1: Pi-Ereignisse werden vollständig in Klartextzeilen übersetzt;
    nichts geht verloren, nichts wird erfunden."""

    # 1. Name: test_pi_session_header_becomes_session_line_without_state [AK1]
    #    Vorbedingung: leerer Zustand. Aktion: Pi-Session-Header übersetzen.
    #    Erwartung: Zeile "[Session] ses-pi-4711"; die Kennung wird NICHT in
    #    den Zustand übernommen (Pi-Läufe sind ephemer, die opencode-
    #    Live-Abfrage darf mit dieser Kennung nie befragt werden).
    #    Fehlerfall: Keine Zeile oder Kennung im Zustand.
    def test_pi_session_header_becomes_session_line_without_state(self):
        event = {"type": "session", "version": 3, "id": PI_SESSION,
                 "timestamp": "2026-01-01T00:00:00.000Z", "cwd": "/proj"}

        lines, _changed = self.translate(event)

        self.assertIn("[Session] " + PI_SESSION, lines)
        self.assertEqual(
            "", self.state["session"],
            "Die ephemere Pi-Session-Kennung darf nicht als Hauptsession "
            "erfasst werden: " + json.dumps(self.state, ensure_ascii=False),
        )

    # 2. Name: test_pi_assistant_text_and_thinking_blocks_become_lines [AK1]
    #    Vorbedingung: leerer Zustand. Aktion: message_end (assistant,
    #    Content = [thinking-Block, text-Block mit Zeilenumbruch]).
    #    Erwartung: Textzeilen je Zeile ("Hallo", "Welt") und
    #    "[Denken] nachdenkliche Zeile" in Content-Reihenfolge.
    #    Fehlerfall: Zeilen fehlen, Reihenfolge falsch oder Roh-JSON.
    def test_pi_assistant_text_and_thinking_blocks_become_lines(self):
        event = {"type": "message_end", "message": {"role": "assistant",
                 "content": [{"type": "thinking", "text": "nachdenkliche Zeile"},
                             {"type": "text", "text": "Hallo\nWelt"}]}}

        lines, _changed = self.translate(event)

        self.assertEqual(
            ["[Denken] nachdenkliche Zeile", "Hallo", "Welt"], lines,
            "Text- und Denkblöcke müssen zeilenweise in Content-Reihenfolge "
            "erscheinen: " + repr(lines),
        )
        self.assertFalse(any(
            line.startswith("{") for line in lines), "Roh-JSON im Protokoll")

    # 3. Name: test_pi_user_message_produces_no_lines [AK1]
    #    Vorbedingung: leerer Zustand. Aktion: message_end (role user).
    #    Erwartung: keine Zeilen (nichts wird erfunden).
    def test_pi_user_message_produces_no_lines(self):
        event = {"type": "message_start",
                 "message": {"role": "user", "content": "Aufgabe"}}

        lines, _changed = self.translate(event)

        self.assertEqual([], lines)

    # 4. Name: test_pi_tool_start_update_end_become_tool_lines [AK1]
    #    Vorbedingung: leerer Zustand. Aktion: bash-Werkzeugereignisse
    #    gemäß Pi-Doku (args.command). Erwartung: Start "[Werkzeug] bash —
    #    läuft: ls -la"; Ende "[Werkzeug] bash — abgeschlossen"; bei
    #    isError dementsprechend "— Fehler". Keine Zustandsänderung.
    def test_pi_tool_start_update_end_become_tool_lines(self):
        start = {"type": "tool_execution_start", "toolCallId": "call_bash1",
                 "toolName": "bash", "args": {"command": "ls -la"}}
        ok = {"type": "tool_execution_end", "toolCallId": "call_bash1",
              "toolName": "bash",
              "result": {"content": [{"type": "text", "text": "Datei1"}]},
              "isError": False, "durationMs": 4}
        bad = {"type": "tool_execution_end", "toolCallId": "call_bash2",
               "toolName": "bash", "result": {"content": []}, "isError": True}

        start_lines, changed = self.translate(start)
        ok_lines, _ = self.translate(ok)
        bad_lines, _ = self.translate(bad)

        self.assertIn("[Werkzeug] bash — läuft: ls -la", start_lines)
        self.assertTrue(any(
            line.startswith("[Werkzeug] bash —") and "abgeschlossen" in line
            for line in ok_lines), f"Ende-Zeile falsch: {ok_lines}")
        self.assertTrue(any(
            line.startswith("[Werkzeug] bash —") and "Fehler" in line
            for line in bad_lines), f"Fehler-Zeile fehlt: {bad_lines}")
        self.assertEqual(
            {"session": "", "subagents": []},
            self.state,
            "Einfache Werkzeugausführung darf keine Subagenten erfinden",
        )

    # 5. Name: test_pi_streaming_and_noise_events_produce_nothing [AK1]
    #    Vorbedingung: leerer Zustand. Aktion: message_update deltas,
    #    turn_start/turn_end, agent_start/agent_end/agent_settled,
    #    queue_update, compaction_start. Erwartung: keine Zeilen, keine
    #    Zustandsänderung (delta-freie Meldung, „Rauschen" bleibt draußen).
    def test_pi_streaming_and_noise_events_produce_nothing(self):
        noise = [
            {"type": "message_update", "usage": {},
             "assistantMessageEvent": {"type": "text_delta",
                                       "contentIndex": 0, "delta": "Hello "}},
            {"type": "turn_start"},
            {"type": "turn_end", "message": {"role": "assistant", "content": []},
             "toolResults": []},
            {"type": "agent_start"},
            {"type": "agent_end", "messages": [], "willRetry": False},
            {"type": "agent_settled", "aborted": False},
            {"type": "queue_update", "steering": [], "followUp": []},
            {"type": "compaction_start", "reason": "threshold"},
        ]
        for event in noise:
            lines, changed = self.translate(event)
            self.assertEqual([], lines, f"Zeilen bei {event.get('type')}")
            self.assertFalse(changed, f"Zustandsänderung bei {event.get('type')}")

        self.assertEqual(
            {"session": "", "subagents": []}, self.state,
            "Rauschereignisse dürfen den Zustand nicht verändern")

    # 6. Name: test_pi_events_without_lines_have_empty_state [AK1]
    #    Vorbedingung: leerer Zustand. Aktion: unknown Ereignistype.
    #    Erwartung: keine Zeilen, keine Zustandsänderung.
    def test_pi_events_without_lines_have_empty_state(self):
        lines, changed = self.translate({"type": "unbekannt"})

        self.assertEqual([], lines)
        self.assertFalse(changed)
        self.assertEqual({"session": "", "subagents": []}, self.state)


class PiSubagentCaptureTest(PiTranslateFixture):
    """AK3: Pi-Subagentenerfassung — Eintrag mit toolCallId als
    Tab-Schlüssel (session), Statusfortschritt und Ausgabeerfassung."""

    # 1. Name: test_pi_task_start_creates_running_entry_with_toolcall_session
    #    [AK3] Vorbedingung: leerer Zustand. Aktion:
    #    tool_execution_start für "task" mit agent/description/prompt.
    #    Erwartung: genau ein Eintrag: session == toolCallId, agent,
    #    description, prompt, status "running", started numerisch, ended 0,
    #    output "".
    #    Fehlerfall: kein Eintrag, falscher Schlüssel oder erfundene Felder.
    def test_pi_task_start_creates_running_entry_with_toolcall_session(self):
        event = pi_task_events()[0]

        _lines, changed = self.translate(event)

        self.assertTrue(changed, "Der neue Eintrag muss als Änderung gelten")
        entries = self.state["subagents"]
        self.assertEqual(1, len(entries), f"Genau ein Eintrag: {entries}")
        entry = entries[0]
        self.assertEqual(TOOL_CALL, entry.get("session"),
                         "toolCallId ist der Tab-Schlüssel (session)")
        self.assertEqual("general", entry.get("agent"))
        self.assertEqual("Testzusammenfassung", entry.get("description"))
        self.assertEqual("Sammle Infos", entry.get("prompt"))
        self.assertEqual("running", entry.get("status"))
        self.assertIsInstance(entry.get("started"), int, "started numerisch")
        self.assertEqual(0, entry.get("ended"), "ended bleibt bis zum Ende 0")

    # 2. Name: test_pi_task_update_captures_partial_result [AK3]
    #    Vorbedingung: laufender task-Eintrag. Aktion: update mit
    #    partialResult (Text). Erwartung: erfasste Ausgabe enthält den
    #    Teilttext; Status bleibt "running"; genau ein Eintrag.
    def test_pi_task_update_captures_partial_result(self):
        self.translate(pi_task_events()[0])
        update = pi_task_events()[1]

        self.translate(update)

        entries = self.state["subagents"]
        self.assertEqual(1, len(entries), f"Kein Doppeltab: {entries}")
        self.assertIn("Teilausgabe", str(entries[0].get("output")))
        self.assertEqual("running", entries[0].get("status"))

    # 3. Name: test_pi_task_end_records_text_output_and_completed_status [AK3]
    #    Vorbedingung: laufender task-Eintrag. Aktion: end mit result
    #    (zwei Text-Blöcke), isError false. Erwartung: kein aktiver Eintrag;
    #    history[] hält status "completed", Ausgabe = Blocktexte zeilenweise
    #    mit \n verbunden ("PONG\nZweitzeile"), ended numerisch und ungleich 0.
    def test_pi_task_end_records_text_output_and_completed_status(self):
        self.translate(pi_task_events()[0])
        end = pi_task_events()[2]

        _lines, changed = self.translate(end)

        self.assertTrue(changed, "Der Abschluss muss als Änderung gelten")
        self.assertEqual(
            [], self.state["subagents"],
            "Der abgeschlossene Eintrag darf nicht aktiv bleiben")
        history = self.state.get("history") or []
        self.assertEqual(
            1, len(history), f"Kein Doppeltab in der Historie: {history}")
        entry = next(
            (item for item in history if item.get("session") == TOOL_CALL), None)
        self.assertIsNotNone(entry, "Kein Historieseintrag für den task: " + str(history))
        self.assertIn("PONG\nZweitzeile", str(entry.get("output")))
        self.assertEqual("completed", entry.get("status"))
        self.assertIsInstance(entry.get("ended"), int)
        self.assertNotEqual(0, entry.get("ended"), "ended beim Abschluss gesetzt")

    # 4. Name: test_pi_failed_task_marks_error_status [AK3]
    #    Vorbedingung: laufender task-Eintrag. Aktion: end mit isError
    #    true. Erwartung: kein aktiver Eintrag; history[] hält status "error"
    #    und ended gesetzt.
    def test_pi_failed_task_marks_error_status(self):
        self.translate(pi_task_events()[0])
        end = {"type": "tool_execution_end", "toolCallId": TOOL_CALL,
               "toolName": "task", "result": {"content": [], "details": {}},
               "isError": True}

        self.translate(end)

        self.assertEqual(
            [], self.state["subagents"],
            "Der fehlgeschlagene Eintrag darf nicht aktiv bleiben")
        history = self.state.get("history") or []
        entry = next(
            (item for item in history if item.get("session") == TOOL_CALL), None)
        self.assertIsNotNone(entry, "Kein Historieseintrag für den Fehler: " + str(history))
        self.assertEqual(
            "error", entry.get("status"),
            f"isError muss den Fehlerstatus setzen: {entry}")
        self.assertNotEqual(0, entry.get("ended"))

    # 5. Name: test_pi_subagent_tool_alias_is_captured_too [AK3]
    #    Vorbedingung: leerer Zustand. Aktion: toolName "subagent".
    #    Erwartung: wie "task"; kein zweiter Eintrag bei Start/Ende, der
    #    abgeschlossene Eintrag liegt in history[].
    def test_pi_subagent_tool_alias_is_captured_too(self):
        start = {"type": "tool_execution_start", "toolCallId": TOOL_CALL,
                 "toolName": "subagent",
                 "args": {"agent": "review", "description": "Prüfung"}}
        end = {"type": "tool_execution_end", "toolCallId": TOOL_CALL,
               "toolName": "subagent", "result": {"content":
               [{"type": "text", "text": "FERTIG"}]}, "isError": False}

        self.translate(start)
        self.translate(end)

        self.assertEqual(
            [], self.state["subagents"],
            "Der abgeschlossene Alias-Eintrag darf nicht aktiv bleiben")
        history = self.state.get("history") or []
        self.assertEqual(
            1, len(history), f"Alias darf keinen Doppeltab geben: {history}")
        self.assertEqual("review", history[0].get("agent"))
        self.assertEqual("completed", history[0].get("status"))
        self.assertIn("FERTIG", str(history[0].get("output")))

    # 6. Name: test_pi_plain_tool_execution_invents_no_entries [AK3]
    #    Vorbedingung: leerer Zustand. Aktion: bash falls start/update/end.
    #    Erwartung: kein erfasster Subagent-Eintrag (keine Attrappen).
    def test_pi_plain_tool_execution_invents_no_entries(self):
        for event in pi_events():
            self.translate(json.loads(event))

        self.assertEqual([], self.state["subagents"],
                         "Einfache Werkzeuge dürfen keinen Tab-Eintrag erzeugen")


class PiStreamFormTest(unittest.TestCase):
    """AK1: stream_events erkennt die Ereignisform automatisch und gibt
    alles in Klartext aus; Nicht-JSON-Zeilen passieren unverändert."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_path = str(Path(self.tmp.name) / "lauf.log.state.json")

    def stream(self, payload, state_path=None):
        collected = []
        vibe_runs.stream_events(
            io.StringIO(payload), collected.append,
            state_path or self.state_path,
        )
        return collected

    # 1. Name: test_stream_passes_non_json_lines_through_unchanged [AK1]
    #    Vorbedingung: keine Zustandsdatei. Aktion: Klartextzeile über
    #    stream_events. Erwartung: unverändert wiedergegeben.
    def test_stream_passes_non_json_lines_through_unchanged(self):
        lines = self.stream(PI_PLAIN + "\n")

        self.assertEqual([PI_PLAIN], lines)

    # 2. Name: test_stream_broken_json_keeps_opencode_prefix [AK1]
    #    Vorbedingung: keine Zustandsdatei. Aktion: defekte JSON-Zeile.
    #    Erwartung: Zeile mit Präfix "opencode: " (bisheriges Rückfall-
    #    verhalten bleibt bestehen, auch wenn die Form nicht erkennbar ist).
    def test_stream_broken_json_keeps_opencode_prefix(self):
        lines = self.stream(PI_BROKEN + "\n")

        self.assertEqual(["opencode: " + PI_BROKEN], lines)

    # 3. Name: test_stream_recognizes_pi_stream_and_translates_all_events
    #    [AK1] Vorbedingung: keine Zustandsdatei. Aktion: vollständiges
    #    Pi-Szenario (Session, Text/Denken, bash, task). Erwartung: alle
    #    Ereignisse als Klartextzeilen, kein Roh-JSON, kein erfundener Text;
    #    der abgeschlossene task-Eintrag liegt in history[] statt in der
    #    aktiven Liste, und der ephemere Sessionschlüssel fehlt.
    def test_stream_recognizes_pi_stream_and_translates_all_events(self):
        payload = "\n".join(
            pi_events() + "\n".join(map(json.dumps, pi_task_events())).splitlines()
        )
        lines = self.stream(payload + "\n")

        expected_without_tool_content = [
            "[Session] " + PI_SESSION,
            "[Denken] nachdenkliche Zeile",
            "Hallo",
            "Welt",
        ]
        for index, candidate in enumerate(expected_without_tool_content):
            self.assertEqual(
                candidate, lines[index],
                f"Zeile {index} falsch: {lines}",
            )
        self.assertFalse(
            [line for line in lines if line.startswith("{")],
            f"Roh-JSON im Klartextstream: {lines}",
        )
        self.assertTrue(
            any("Werkzeug" in line for line in lines),
            "Werkzeugereignisse müssen im Klartextstream erscheinen",
        )

        state = vibe_runs.load_subagent_state(self.state_path)
        self.assertEqual(
            [], state["subagents"],
            "Der abgeschlossene task darf nicht aktiv bleiben: " + str(state))
        history = state.get("history") or []
        self.assertEqual(
            1, len(history), f"Genau der task-Eintrag in history[]: {state}")
        entry = history[0]
        self.assertEqual(TOOL_CALL, entry.get("session"))
        self.assertEqual("completed", entry.get("status"))
        self.assertEqual("PONG\nZweitzeile", entry.get("output"))
        self.assertEqual(
            "", state["session"],
            "Die ephemere Pi-Session darf nie als Hauptsession landen")

    # 4. Name: test_stream_mixed_pi_prefix_does_not_clobber_opencode_session
    #    [AK2] Vorbedingung: opencode-Zustand mit erfasster Sitzung.
    #    Aktion: opencode-Ereignisse gefolgt von einem Pi-Session-Header.
    #    Erwartung: die erfasste opencode-Hauptsitzung wird nicht durch die
    #    ephemere Pi-Kennung überschrieben.
    def test_stream_mixed_pi_prefix_does_not_clobber_opencode_session(self):
        opencode = ('{"type":"text","sessionID":"ses_mop",'
                    '"part":{"type":"text","text":"Bis hierher"}}')
        payload = opencode + "\n" + pi_events()[0] + "\n"
        self.stream(payload)

        state = vibe_runs.load_subagent_state(self.state_path)
        self.assertEqual(
            "ses_mop", state["session"],
            "Pi-Session darf die beibehaltene opencode-Hauptsession nicht "
            "überschreiben: " + json.dumps(state, ensure_ascii=False))


class OpencodeRegressionTest(PiStreamFormTest):
    """AK2: opencode-Verhalten unverändert — bestehende opencode-
    Fixturszenarien produzieren byte-gleiche Protokollzeilen und Zustands-
    datei (Fixtur durch Übersetzen des unveränderten Produktcodes bei der
    Baseline ermittelt und als Literale fixiert)."""

    # Fixtur der opencode-Ereignisse, wie die opencode-Lauftests sie
    # prüfen (z. B. tests/unit/test_output_view_f19_runner.py): Text,
    # Reasoning, Werkzeug, Subagent-Abschluss. Erwartete Zeilen = exakt die
    # Ausgabe der unveränderten translate_event an der Baseline.
    OPENCODE_EVENTS = (
        '{"type":"text","sessionID":"ses_main",'
        '"part":{"type":"text","text":"Zunaechst schaue ich ins Verzeichnis"}}\n'
        '{"type":"reasoning","sessionID":"ses_main",'
        '"part":{"type":"text","text":"Gedanke eins\\nGedanke zwei"}}\n'
        '{"type":"tool_use","sessionID":"ses_main","part":{"tool":"bash",'
        '"state":{"status":"running","input":{"command":"ls -la"}}}}\n'
        '{"type":"tool_use","sessionID":"ses_main","part":{"tool":"subagent",'
        '"state":{"status":"completed","input":{"agent":"general",'
        '"description":"Testzusammenfassung","prompt":"Sammle Infos"},'
        '"output":"PONG"},"metadata":{"metadata":{"sessionID":"ses_child"}}}}\n'
        '{"type":"error","sessionID":"ses_main",'
        '"error":{"data":{"message":"Boom"}}}\n'
        '{"type":"text","sessionID":"ses_main",'
        '"part":{"type":"text","text":"Fertig"}}\n'
    )

    OPENCODE_EXPECTED_LINES = [
        "[Session] ses_main",
        "Zunaechst schaue ich ins Verzeichnis",
        "[Denken] Gedanke eins",
        "[Denken] Gedanke zwei",
        "[Werkzeug] bash \u2014 running: ls -la",
        "[Subagent] general: Testzusammenfassung \u2014 completed",
        "PONG",
        "[Fehler] Boom",
        "Fertig",
    ]

    # 1. Name: test_stream_opencode_events_byte_identical [AK2]
    #    Vorbedingung: keine Zustandsdatei. Aktion: das opencode-Fixtur-
    #    Szenario über den automatisch erkennenden Stream. Erwartung:
    #    byte-gleiche Protokollzeilen zur bisherigen Übersetzung (Liste
    #    zeilengleich identisch) und die erfasste Sessionsdatei mit
    #    Hauptsession und dem abgeschlossenen Subagenten in history[].
    def test_stream_opencode_events_byte_identical(self):
        lines = self.stream(self.OPENCODE_EVENTS)

        self.assertEqual(
            self.OPENCODE_EXPECTED_LINES, lines,
            "Die automatische Formerkennung darf das opencode-Verhalten "
            "nicht verändern",
        )
        state = vibe_runs.load_subagent_state(self.state_path)
        self.assertEqual("ses_main", state["session"])
        self.assertEqual(
            [], state["subagents"],
            "Der abgeschlossene Subagent darf nicht aktiv bleiben: " + str(state))
        history = state.get("history") or []
        self.assertEqual(1, len(history))
        entry = history[0]
        self.assertEqual({
            "session": "ses_child",
            "agent": "general",
            "description": "Testzusammenfassung",
            "prompt": "Sammle Infos",
            "status": "completed",
            "ended": entry.get("ended"),
            "started": entry.get("started"),
            "output": "PONG",
        }, entry)
        self.assertIsInstance(entry.get("started"), int)
        self.assertIsInstance(entry.get("ended"), int)

    # 2. Name: test_stream_mixed_opencode_input_keeps_behavior [AK2]
    #    Vorbedingung: wie 1, plus Nicht-JSON-Zeile und defektes JSON im
    #    selben Stream. Erwartung: Nicht-JSON unverändert, defekt mit
    #    "opencode: "-Präfix, übersetzte Ereignisse unverändert.
    def test_stream_mixed_opencode_input_keeps_behavior(self):
        payload = (
            self.OPENCODE_EVENTS
            + PI_PLAIN + "\n"
            + PI_BROKEN + "\n"
        )

        lines = self.stream(payload)

        self.assertEqual(
            self.OPENCODE_EXPECTED_LINES + [PI_PLAIN, "opencode: " + PI_BROKEN],
            lines,
        )


class PiSubagentApiFixture(unittest.TestCase):
    """Startet das echte Dashboard (bin/vibe-web.py) im isolierten VIBE-Root
    auf einem freien Port (Muster: tests/unit/test_f24_output_agent_ui.py).
    Die Zustandsdatei entsteht ausschließlich über das echte Übersetzungs-
    werkzeug bin/vibe_runs.py stream — dieselbe Quelle wie ein echter Läufer.
    Keine Modellaufrufe, keine externen Dienste (nur localhost)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True)
        cls.log_dir = cls.root / "_logs"
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.port = free_port()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                "TMUX", "TMUX_PANE",
            ):
                env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_INSTALL": str(cls.root / "_toolchain"),
            "VIBE_RUNTIME": str(cls.log_dir),
            "VIBE_STATE": str(cls.root / "_toolchain"),
            "HOME": str(cls.root / "home"),
            "VIBE_CONFIG_FILE": str(
                cls.root / "home" / ".config" / "vibe" / "config.json"),
            "TMPDIR": str(cls.root / "tmp"),
            "TMUX_TMPDIR": str(cls.tmux_dir),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        (cls.root / "tmp").mkdir(parents=True)
        cls.env = env
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=cls.server_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 30
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: " + cls.server_log.name)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()

    @classmethod
    def tearDownClass(cls):
        try:
            if cls.proc.poll() is None:
                cls.proc.terminate()
                try:
                    cls.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls.proc.kill()
                    cls.proc.wait()
        finally:
            cls.server_log.close()
            cls.tmp.cleanup()

    def setUp(self):
        register = self.log_dir / "runs.json"
        if register.exists():
            register.unlink()
        state = self.log_dir / "proj.log.state.json"
        if state.exists():
            state.unlink()

    def register_run(self, state="running"):
        """B11-Anpassung: /api/subagents liefert nur Einträge des aktuellen
        Laufs. Die Pi-erfassten Einträge gehören zum aktuellen Lauf, wenn
        der Lauf registriert ist, bevor der Übersetzungsfilter sie erfasst;
        der Filter setzt ``started`` auf die Erfassungszeit."""
        project = str((self.root / "proj").resolve())
        result = subprocess.run(
            [sys.executable, str(RUNS_PY), "start",
             "--runtime", str(self.log_dir),
             "--project", project,
             "--name", "proj", "--key", "proj", "--agent", "vibe-agent",
             "--state", state],
            env=self.env,
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(
            result.returncode, 0,
            "Vorbedingung Laufregister fehlgeschlagen: "
            + result.stdout + result.stderr)

    def stream_pi_events(self):
        """Vorbedingung: der echte Übersetzungsfilter verarbeitet das
        Pi-Szenario (denselben Weg wie der echte Läufer)."""
        payload = "\n".join(
            pi_events() + "\n".join(map(json.dumps, pi_task_events())).splitlines()
        ) + "\n"
        result = subprocess.run(
            [sys.executable, str(RUNS_PY), "stream",
             "--state", str(self.state_path())],
            env=self.env,
            input=payload,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(
            result.returncode, 0,
            "Vorbedingung fehlgeschlagen: " + result.stdout + result.stderr)

    def call_pi_run(self):
        """Aktion: das Pi-Fixtur-Szenario durch den echten Läufer-Filter."""
        self.register_run()
        return self.stream_pi_events()

    def state_path(self):
        return self.log_dir / "proj.log.state.json"

    def get(self, path):
        """Fachliche Abfrage: GET an die UI-API mit Token (Header und
        t=-Parameter, wie die Oberfläche die Route aufrufen darf)."""
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.port, timeout=15)
        headers = {"X-Token": self.token}
        try:
            connection.request("GET", path + ("&t=" if "?" in path else "?t=") + self.token, headers=headers)
            response = connection.getresponse()
            body = response.read().decode("utf-8", "replace")
            try:
                payload = json.loads(body)
            except ValueError:
                payload = None
            return response.status, payload, body
        finally:
            connection.close()


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class PiSubagentApiTest(PiSubagentApiFixture):
    """AK3: Die unveränderte UI-API arbeitet mit den aus Pi-Ereignissen
    erfassten Zustandsdaten."""

    # 1. Name: test_pi_captured_subagent_appears_in_ui_api [AK3]
    #    Vorbedingung: Pi-Szenario vom echten Übersetzungsfilter in die
    #    Zustandsdatei erfasst. Aktion: GET /api/subagents?name=proj.
    #    Erwartung: 200/ok; der abgeschlossene Tab-Eintrag steht nicht in der
    #    aktiven Liste, bleibt aber mit session == toolCallId, status
    #    "completed", Agent, Beschreibung und Ausgabe in history[] erhalten;
    #    /api/subagent-output liefert die Ausgabe weiterhin.
    def test_pi_captured_subagent_appears_in_ui_api(self):
        self.call_pi_run()

        status, data, raw = self.get("/api/subagents?name=proj")
        self.assertEqual(status, 200, raw)
        self.assertTrue(isinstance(data, dict) and data.get("ok"), raw)
        self.assertEqual(
            [], data.get("subagents") or [],
            "Der abgeschlossene Pi-Subagent darf nicht aktiv gemeldet werden: " + raw)
        self.assertEqual(
            "", data.get("session", ""),
            "Die ephemere Pi-Session darf der API nicht als erfasste "
            "Hauptsitzung gemeldet werden: " + raw)

        state = vibe_runs.load_subagent_state(str(self.state_path()))
        history = [item for item in (state.get("history") or [])
                   if item.get("session") == TOOL_CALL]
        self.assertEqual(1, len(history), "Verlaufseintrag fehlt: " + raw)
        entry = history[0]
        self.assertEqual("completed", entry.get("status"), entry)
        self.assertEqual("general", entry.get("agent"), entry)
        self.assertEqual("Testzusammenfassung", entry.get("description"), entry)
        self.assertIn("PONG", str(entry.get("output") or ""), entry)

        status, detail, detail_raw = self.get(
            "/api/subagent-output?name=proj&session=" + TOOL_CALL)
        self.assertEqual(200, status, detail_raw)
        self.assertTrue(isinstance(detail, dict) and detail.get("ok"), detail_raw)
        self.assertIn("PONG", str(detail.get("text") or ""), detail_raw)

    # 2. Name: test_pi_subagent_output_served_by_ui_api [AK3]
    #    Vorbedingung: wie 1. Aktion: GET /api/subagent-output mit der
    #    toolCallId-Session. Erwartung: ok, Text enthält "PONG\nZweitzeile",
    #    Status "completed".
    def test_pi_subagent_output_served_by_ui_api(self):
        self.call_pi_run()

        status, data, raw = self.get(
            "/api/subagent-output?name=proj&session=" + TOOL_CALL)
        self.assertEqual(status, 200, raw)
        self.assertTrue(isinstance(data, dict) and data.get("ok"), raw)
        self.assertIn("PONG", data.get("text", ""), raw)
        self.assertIn("Zweitzeile", data.get("text", ""), raw)
        self.assertEqual("completed", data.get("status"), raw)


# ===========================================================================
# Unit-Abnahme (Teil 3): Läuferverbindung für Pi über den echten
# ===========================================================================

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RUNNER = REPO / "bin" / "vibe-run.sh"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support  # noqa: E402


# Attrappe: protokolliert die Argumente, gibt Pi-JSONL gemäß der
# Pi-Dokumentation 1.5.0 (docs/json.md) aus und schließt das Arbeitspaket
# so ab, wie die echten Abschlussschranken es verlangen (Muster: die
# opencode-Attrappe in runner_support.py — hier als eigenständiger Text
# des Test-Agenten geschrieben).
FAKE_PI = r'''#!/usr/bin/env python3
"""Pi-Attrappe für die B6-Abnahme (kein echter pi, keine Modellkosten)."""
import json
import os
import pathlib
import re
import subprocess
import sys

args = sys.argv[1:]
message = args[-1] if args else ""
match = re.search(r"Arbeitspaket\s+([A-Za-z0-9_-]+)", message)
pid = match.group(1) if match else "B6"
cwd = pathlib.Path.cwd()

args_path = os.environ.get("FAKE_PI_ARGS_PATH")
if args_path:
    # Je Aufruf wird die Argumentliste NUL-getrennt mit Datensatzende
    # angehängt; der Prompt enthält kein NUL-Byte, die Grenze ist eindeutig.
    with open(args_path, "ab") as handle:
        for argument in args:
            handle.write(argument.encode("utf-8") + b"\0")
        handle.write(b"PI_ARGS_RECORD_END\0")

session = os.environ.get("FAKE_PI_SESSION", "ses-pi-4711")
events = [
    {"type": "session", "version": 3, "id": session,
     "timestamp": "2026-01-01T00:00:00.000Z", "cwd": str(cwd)},
    {"type": "agent_start"},
    {"type": "message_end", "message": {"role": "user", "content": message,
                                        "timestamp": 1735689600000}},
    {"type": "message_end", "message": {"role": "assistant", "content": [
        {"type": "thinking", "text": "nachdenkliche Zeile"},
        {"type": "text", "text": "Hallo\nWelt"},
    ]}},
    {"type": "tool_execution_start", "toolCallId": "call_abc123", "toolName": "task",
     "args": {"agent": "general", "description": "Testzusammenfassung",
              "prompt": "Sammle Infos"}},
    {"type": "tool_execution_update", "toolCallId": "call_abc123",
     "toolName": "task",
     "args": {"agent": "general", "description": "Testzusammenfassung"},
     "partialResult": {"content": [{"type": "text", "text": "Teilausgabe"}]}},
    {"type": "tool_execution_end", "toolCallId": "call_abc123", "toolName": "task",
     "result": {"content": [{"type": "text", "text": "PONG"},
                            {"type": "text", "text": "Zweitzeile"}]},
     "isError": False, "durationMs": 7},
    {"type": "turn_end", "message": {"role": "assistant", "content": []},
     "toolResults": []},
    {"type": "agent_end", "messages": [], "willRetry": False},
    {"type": "agent_settled", "aborted": False},
]
for event in events:
    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
sys.stdout.flush()

if os.environ.get("FAKE_PI_MODE", "complete") == "fail":
    sys.stderr.write("beliebiger Agentenfehler\n")
    sys.exit(1)

counter_path = pathlib.Path(os.environ.get("FAKE_PI_COUNTER", os.devnull))
try:
    counter = int(counter_path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    counter = 0
counter_path.write_text(str(counter + 1), encoding="utf-8")


def run(*command, check=True):
    return subprocess.run(list(command), cwd=cwd, check=check,
                          capture_output=True, text=True)


def complete_ticket(commit):
    """GH-48: schließt die sichtbare TICKET-<ID>.json ab."""
    path = cwd / ("TICKET-" + pid + ".json")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = {"id": pid, "title": pid, "type": "task",
                  "description": ""}
    record.setdefault("type", "task")
    record.update({"id": pid, "state": "done", "commit": commit,
                   "test": "test_" + pid.lower().replace("-", "_")})
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")


(cwd / ("impl-" + pid + ".txt")).write_text(pid + "\n", encoding="utf-8")
run("git", "add", "-A")
run("git", "commit", "-q", "-m", pid + ": Umsetzung")
short = run("git", "rev-parse", "--short", "HEAD").stdout.strip()

complete_ticket(short)

(cwd / "docs" / "features").mkdir(parents=True, exist_ok=True)
(cwd / "docs" / "features" / (pid + ".md")).write_text(
    "# " + pid + "\n\nTestdokumentation.\n", encoding="utf-8")
(cwd / "docs" / "reviews").mkdir(parents=True, exist_ok=True)
(cwd / "docs" / "reviews" / (pid + "-review-1.md")).write_text(
    "# Review\n\nVerdict: PASS\n", encoding="utf-8")
run("git", "add", "-A")
run("git", "commit", "-q", "-m", pid + ": Nachweis")
sys.exit(0)
'''

FAKE_CURL_LOCAL = """#!/usr/bin/env bash
exit 7
"""


class PiRunnerFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        # Pi liest den Prompt-Text der Agentendatei; die Dateien brauchen
        # deshalb einen echten Prompt-Text (Frontmatter wird nicht mitgesendet).
        self.agents.mkdir(parents=True)
        for name in ("tester", "test-agent", "code-reviewer", "reviewer"):
            (self.agents / (name + ".md")).write_text(
                "---\ndescription: Testagent\nmode: primary\n---\n"
                "Du bist der Test-Agent der Arbeitspakete.\n",
                encoding="utf-8",
            )
        self.project = self.root / "proj"
        support.write_project(
            self.project,
            "TYPE=generic\n"
            "AGENT=tester\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL="true"\n'
            "MAX_RETRIES=0\n",
            feedback=[support.ticket_record("B6", "Testpaket",
                                            description="Test")],
        )
        self.tool_bin = support.install_runner(self.root / "_toolchain")
        self.install = self.root / "_toolchain"
        # Harness-Schicht für den Pi-Zweig des Läufers:
        for name in ("vibe_harness.py", "vibe_opencode.py"):
            (self.tool_bin / name).write_text(
                (BIN / name).read_text(encoding="utf-8"), encoding="utf-8")
        # Harness-Auswahl: Pi gewählt (echter Auswahlstand des Läufers).
        (self.install / "harness.json").write_text(
            json.dumps({"harness": "pi"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self.fakebin = support.install_fake_tools(self.root)
        (self.fakebin / "pi").write_text(FAKE_PI, encoding="utf-8")
        self.fakebin_chmod(self.fakebin / "pi")
        support.init_repo(self.project)
        support.commit_all(self.project)
        self.addCleanup(self.tmp.cleanup)

    def fakebin_chmod(self, path):
        mode = path.stat().st_mode | 0o111
        path.chmod(mode)

    def env(self):
        env = os.environ.copy()
        for key in list(env):
            if (
                key.startswith("VIBE")
                or key.startswith("SANDBOX")
                or key.startswith("FAKE_")
                or key
                in (
                    "AGENT",
                    "TESTER",
                    "REVIEWER",
                    "MAX_RETRIES",
                    "VERIFY_QUICK",
                    "VERIFY_FULL",
                    "VERIFY_PACKAGE",
                    "TMUX",
                    "TMUX_PANE",
                )
            ):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(self.root),
                "VIBE_INSTALL": str(self.install),
                "VIBE_RUNTIME": str(self.root / "_logs"),
                "VIBE_AGENTS_DIR": str(self.agents),
                "HOME": str(self.home),
                "VIBE_NO_CONTAINER": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
                "FAKE_PI_ARGS_PATH": str(self.root / "_logs" / "pi.args"),
                "FAKE_PI_SESSION": PI_SESSION,
                "FAKE_PI_COUNTER": str(self.root / "counter"),
                "FAKE_PI_MODE": os.environ.get("B6_FAKE_PI_MODE", "complete"),
            }
        )
        return env

    def command(self):
        # Hausregel NTFS/FUSE: Skripte mit bash <datei> ausführen.
        return ["bash", str(self.tool_bin / "vibe-run.sh"), str(self.project)]

    def run_runner(self):
        result = subprocess.run(
            self.command(),
            env=self.env(),
            cwd=str(self.project),
            capture_output=True,
            text=True,
            timeout=180,
        )
        log = self.log_text()
        return result, log

    def log_lines(self):
        text = self.log_text()
        try:
            return text.splitlines()
        except AttributeError:
            return []

    def log_text(self):
        path = self.root / "_logs" / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def read_state(self):
        path = self.root / "_logs" / "proj.log.state.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            self.fail(
                "Zustandsdatei ist kein gültiges JSON: "
                + path.read_text(encoding="utf-8"))

    def pi_calls(self):
        path = self.root / "_logs" / "pi.args"
        self.assertTrue(path.exists(), "pi wurde nicht aufgerufen")
        tokens = path.read_bytes().decode(
            "utf-8", "surrogateescape").split("\0")
        records, current = [], []
        for token in tokens:
            if token == "PI_ARGS_RECORD_END":
                records.append(current)
                current = []
            elif token:
                current.append(token)
        return records


class PiRunnerSuccessfulRunTest(PiRunnerFixture):
    """AK5 (+ AK1/AK3/AK4): Erfolgreicher Pi-Lauf über den echten Läufer."""

    def run_and_expect_finished(self):
        result, log = self.run_runner()
        self.assertEqual(
            result.returncode, 0, "Läufer bricht ab:\n" + result.stdout + result.stderr)
        self.assertIn(
            "FERTIG", log,
            "Läufer hat die Abnahme nicht gemeldet:\n" + log + "\n" + result.stderr)
        return log

    # 1. Name: test_pi_runner_logs_translated_protocol_without_raw_json
    #    [AK5/AK1] Vorbedingung: harness.json wählt Pi; Pi-Attrappe liefert
    #    die Pi-JSONL-Ereignisse; Arbeitspaket lauffähig. Aktion: echten
    #    vibe-run.sh ausführen. Erwartung: Das Protokoll enthält die
    #    übersetzten Zeilen ("Hallo", "[Session] ses-pi-4711",
    #    "[Denken] nachdenkliche Zeile", "[Werkzeug] task — läuft") als
    #    eigene Zeilen und keine Zeile, die mit "{" beginnt (kein Roh-JSON).
    #    Fehlerfall: Roh-JSON im Protokoll oder fehlende übersetzte Zeilen.
    def test_pi_runner_logs_translated_protocol_without_raw_json(self):
        log = self.run_and_expect_finished()

        lines = self.log_lines()
        raw = [line for line in lines if line.startswith("{")]
        self.assertEqual(
            raw, [], f"Roh-JSON-Zeilen dürfen nicht ins Protokoll:\n{log}")
        for expected in (
            "Hallo",
            "Welt",
            "[Session] " + PI_SESSION,
            "[Denken] nachdenkliche Zeile",
        ):
            self.assertIn(
                expected, lines,
                f"Übersetzte Zeile {expected!r} fehlt im Protokoll:\n" + log)
        self.assertTrue(
            any(line.startswith("[Werkzeug] task — läuft") for line in lines),
            f"Werkzeugstart fehlt im Protokoll: {[line for line in lines if 'Werkzeug' in line]}",
        )

    # 2. Name: test_pi_runner_state_file_captures_subagent_and_no_session
    #    [AK5/AK3] Vorbedingung: wie 1. Aktion: Läufer ausführen und
    #    Zustandsdatei lesen. Erwartung: Der abgeschlossene task-Eintrag liegt
    #    in history[] (session == toolCallId als Tab-Schlüssel, agent,
    #    description, prompt, status "completed", Ausgabe "PONG\nZweitzeile",
    #    started/ended numerisch) und nicht in der aktiven Liste; die
    #    Hauptsession im Zustand bleibt leer (die ephemere Pi-Kennung darf
    #    F25-Ketten nicht fälschen).
    #    Fehlerfall: Zustandsdatei fehlt oder Eintrag falsch.
    def test_pi_runner_state_file_captures_subagent_and_no_session(self):
        self.run_and_expect_finished()

        state = self.read_state()
        self.assertIsNotNone(
            state, "Zustandsdatei fehlt nach dem Pi-Lauf")
        self.assertEqual(
            "", state.get("session", ""),
            "Die ephemere Pi-Session darf nicht als Hauptsession "
            "erfasst werden: " + json.dumps(state, ensure_ascii=False),
        )
        self.assertEqual(
            [], state.get("subagents") or [],
            "Der abgeschlossene task darf nicht aktiv bleiben: " + str(state))
        history = state.get("history") or []
        self.assertEqual(1, len(history), f"Genau der task-Eintrag in history[]: {state}")
        entry = history[0]
        self.assertEqual(TOOL_CALL, entry.get("session"), entry)
        self.assertEqual("general", entry.get("agent"), entry)
        self.assertEqual("Testzusammenfassung", entry.get("description"), entry)
        self.assertEqual("Sammle Infos", entry.get("prompt"), entry)
        self.assertEqual("completed", entry.get("status"), entry)
        self.assertIn("PONG\nZweitzeile", str(entry.get("output") or ""), entry)
        self.assertIsInstance(entry.get("started"), int, entry)
        self.assertIsInstance(entry.get("ended"), int, entry)

    # 3. Name: test_pi_runner_calls_pi_agent_with_json_mode [AK5/AK4]
    #    Vorbedingung: wie 1. Aktion: Läufer ausführen und die von der
    #    Pi-Attrappe protokollierten Argumente lesen. Erwartung: Jeder
    #    Aufruf enthält --print und --no-session; mindestens ein Aufruf
    #    enthält --mode und json, und zwar vor der Optionsgrenze --.
    #    Fehlerfall: Ohne --mode json würde Pi keine Ereignisse liefern
    #    (genau der gemeldete Defekt).
    def test_pi_runner_calls_pi_agent_with_json_mode(self):
        self.run_and_expect_finished()

        records = self.pi_calls()
        self.assertTrue(records, "pi wurde nicht aufgerufen")
        for argv in records:
            self.assertIn(
                "--print", argv, f"Print-Modus fehlt: {argv}")
            self.assertIn(
                "--no-session", argv, f"--no-session fehlt: {argv}")
        self.assertTrue(
            any("--mode" in argv and "json" in argv for argv in records),
            f"kein --mode json-Aufruf: {records}")
        package_calls = [argv for argv in records if "--mode" in argv]
        for argv in package_calls:
            self.assertLess(
                argv.index("--mode"), argv.index("--"),
                f"--mode muss vor der Optionsgrenze -- stehen: {argv}")


class PiRunnerExitCodeTest(PiRunnerFixture):
    """AK5: Der Exit-Code des Agentenprozesses bleibt maßgeblich."""

    def run_in_fail_mode(self):
        env = self.env()
        env["FAKE_PI_MODE"] = "fail"
        result = subprocess.run(
            self.command(), env=env, cwd=str(self.project),
            capture_output=True, text=True, timeout=180,
        )
        return result, self.log_text()

    # 1. Name: test_pi_xrun_agent_exit_code_one_does_not_close_package
    #    [AK5] Vorbedingung: wie oben; Pi-Attrappe endet mit definiertem
    #    Exit-Code 1. Aktion: echten vibe-run.sh ausführen. Erwartung: Das
    #    Protokoll meldet "Agent beendet, Exit-Code 1" und der
    #    Abschlussbericht schließt das Paket nicht ("Geschlossen: keine");
    #    die Abnahme läuft trotzdem regulär zu Ende (bisherige Läufer-
    #    semantik: übersprungenes Paket blockiert den Abschluss nicht).
    #    Fehlerfall: Der Läufer bricht ab oder schließt das Paket fälschlich.
    def test_pi_run_agent_exit_code_one_does_not_close_package(self):
        result, log = self.run_in_fail_mode()

        self.assertEqual(
            result.returncode, 0, "Läufer bricht ab:\n" + log + result.stderr)
        self.assertIn(
            "Agent beendet, Exit-Code 1", log,
            "Der Exit-Code des Pi-Prozesses muss maßgeblich sein:\n" + log)
        self.assertIn(
            "Geschlossen: keine", log,
            "Das Paket darf bei Agentenfehlern nicht geschlossen werden:\n" + log)


# ===========================================================================
# Unit-Abnahme: Pi als gewählter Harness im Dashboard (Backend)
# ===========================================================================

import base64
import http.client
import importlib.machinery
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tests.support.tmux_cleanup import cleanup_env

CLI = REPO / "bin" / "vibe"
WEB_f20 = REPO / "bin" / "vibe-web.py"
RUNS_PY_f20 = REPO / "bin" / "vibe_runs.py"

MAIN_SESSION = "ses_main"
STEER_TEXT = "Prüfe zuerst die Borderstellung"
SERVER_CREDENTIAL = "geheim-PASSWORT-4711"

STATE_FILE = {"session": MAIN_SESSION, "subagents": []}

SESSION_MISSING_MESSAGE = (
    "Die Session des laufenden Agenten ist nicht erfasst"
)


def load_cli_module(name="vibe_f20_api_under_test"):
    """Lädt bin/vibe mit der aktuellen Umgebungsvariablen des Aufrufers."""
    loader = importlib.machinery.SourceFileLoader(name, str(CLI))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """Nachbildung des opencode-Servers: GET meldet Lauffähigkeit, POST nimmt
    eine Zusatzanweisung nur mit gültiger Basic-Auth an. Alle POST-Anfragen
    landen in <runtime>/fake-opencode.requests.jsonl, damit Tests beweisen
    können, ob eine Zustellung (nicht) versucht wurde."""

    context = None  # dict(credential_path, record_path)

    def log_message(self, *args):
        return

    def _signature(self):
        try:
            password = Path(self.context["credential_path"]).read_text(
                encoding="utf-8"
            ).strip()
        except OSError:
            return None
        encoded = base64.b64encode(("opencode:" + password).encode()).decode()
        return "Basic " + encoded

    def do_GET(self):
        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        signature = self._signature()
        header = self.headers.get("Authorization", "")
        auth_ok = signature is not None and header == signature
        user = ""
        if header.startswith("Basic "):
            try:
                decoded = base64.b64decode(header[6:]).decode("utf-8")
                user = decoded.split(":", 1)[0]
            except Exception:
                user = ""
        with open(self.context["record_path"], "a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"path": self.path, "auth_ok": auth_ok, "user": user,
                     "body": body},
                    ensure_ascii=False,
                ) + "\n"
            )
        status = 200 if auth_ok else 401
        payload = json.dumps({"ok": auth_ok}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def make_fake_handler(context):
    def build():
        handler = type("BoundHandler", (BaseHTTPRequestHandler,), {})
        for attribute, value in _FakeOpenCodeHandler.__dict__.items():
            if not attribute.startswith("__"):
                setattr(handler, attribute, value)
        handler.context = context
        return handler
    return build()


class ApiFixture(unittest.TestCase):
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
        cls.state_dir = cls.root / "_toolchain"
        cls.state_dir.mkdir()
        cls.port = free_port()
        cls.oc_port = free_port()
        cls.context = {
            "credential_path": str(cls.root / "_logs" / "opencode.password"),
            "record_path": str(cls.root / "_logs" / "fake-opencode.requests.jsonl"),
        }
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), make_fake_handler(cls.context)
        )
        cls._fake_http.daemon_threads = True
        cls._fake_thread = threading.Thread(target=cls._fake_http.serve_forever)
        cls._fake_thread.daemon = True
        cls._fake_thread.start()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.env = cls.build_env()
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB_f20)],
            env=cls.env,
            stdout=cls.server_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.log_dir / "web.token"
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
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: "
                    + cls.root.joinpath("web-server.log").read_text(
                        encoding="utf-8", errors="replace"
                    )
                )
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.session = cls.sess_name("proj")

    @classmethod
    def build_env(cls):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                "TMUX", "TMUX_PANE",
            ):
                env.pop(key, None)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir()
        cls.tmux_dir.chmod(0o700)
        tmp = cls.root / "tmp"
        tmp.mkdir()
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "VIBE_OPENCODE_PORT": str(cls.oc_port),
                "VIBE_INSTALL": str(cls.state_dir),
                "VIBE_RUNTIME": str(cls.root / "_logs"),
                "VIBE_STATE": str(cls.state_dir),
                "HOME": str(cls.root / "home"),
                "VIBE_CONFIG_FILE": str(
                    cls.root / "home" / ".config" / "vibe" / "config.json"
                ),
                "TMPDIR": str(tmp),
                "TMUX_TMPDIR": str(cls.tmux_dir),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        return env

    @classmethod
    def sess_name(cls, name):
        saved = os.environ.copy()
        try:
            os.environ.update(cls.env)
            module = load_cli_module()
            return module.sess(name)
        finally:
            for key in list(os.environ):
                if key not in saved:
                    os.environ.pop(key, None)
            os.environ.update(saved)

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        cls.server_log.close()
        try:
            cls._fake_http.shutdown()
            cls._fake_http.server_close()
            cls._fake_thread.join(timeout=5)
        except Exception:
            pass
        subprocess.run(
            ["tmux", "kill-server"],
            env=cleanup_env(os.environ, cls.tmux_dir),
            capture_output=True,
            timeout=20,
        )
        cls.tmp.cleanup()

    # ---------- Helfer ----------
    def setUp(self):
        self.reset_state()
        self.password_clear()
        self.clear_requests()
        self.set_selection(None)

    def reset_state(self):
        state = self.root / "_logs" / "proj.log.state.json"
        if state.exists():
            state.unlink()

    def write_state(self, data=STATE_FILE):
        path = self.root / "_logs" / "proj.log.state.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def set_selection(self, harness):
        """Schreibt/entfernt <VIBE_STATE>/harness.json für den Webserver-Prozess."""
        path = self.state_dir / "harness.json"
        if harness is None:
            if path.exists():
                path.unlink()
        else:
            path.write_text(
                json.dumps({"harness": harness}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        return path

    def password_private(self, value=SERVER_CREDENTIAL):
        path = self.root / "_logs" / "opencode.password"
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
        return path

    def password_clear(self):
        path = self.root / "_logs" / "opencode.password"
        if path.exists():
            path.unlink()

    def request(self, method, path, body=None):
        if body is not None and not isinstance(body, (bytes, bytearray)):
            encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        else:
            encoded = body
        headers = {
            "Host": f"127.0.0.1:{self.port}",
            "X-Token": self.token,
            "Origin": f"http://127.0.0.1:{self.port}",
            "Sec-Fetch-Site": "same-origin",
        }
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            connection.request(method, path, body=encoded, headers=headers)
            response = connection.getresponse()
            text = response.read().decode("utf-8", "replace")
            try:
                payload = json.loads(text)
            except ValueError:
                payload = None
            return response.status, payload, text
        finally:
            connection.close()

    def clear_requests(self):
        path = Path(self.context["record_path"])
        if path.exists():
            path.unlink()

    def posts(self):
        """Alle protokollierten POST-Zustellungen an die opencode-Attrappe."""
        path = Path(self.context["record_path"])
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def log_text(self):
        path = self.root / "_logs" / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def touch_run_log(self):
        path = self.root / "_logs" / "proj.log"
        path.write_text(
            "Lauf: proj, Modus: --standalone, Agent: tester\n"
            "=== [proj] Arbeitspaket F20, Versuch 1/3, Durchgang 1/80 ===\n",
            encoding="utf-8",
        )
        return path

    def start_active_run(self):
        """Vorbedingung „aktiver Lauf“: Registereintrag state running plus
        offene tmux-Sitzung, wie im F19-Muster nachgebildet."""
        subprocess.run(
            [
                sys.executable, str(RUNS_PY_f20), "start",
                "--runtime", str(self.root / "_logs"),
                "--project", str(self.project.resolve()),
                "--name", "proj", "--key", "proj", "--agent", "tester",
                "--session", self.session,
                "--state", "running",
            ],
            env=self.env_clean(),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def stop_active_run(self):
        subprocess.run(
            ["tmux", "kill-session", "-t", self.session],
            env=self.env_clean(),
            capture_output=True,
            timeout=20,
        )
        register = self.root / "_logs" / "runs.json"
        if register.exists():
            data = json.loads(register.read_text(encoding="utf-8"))
            for record in reversed(data.get("runs", [])):
                if record.get("session") == self.session and record.get(
                    "state"
                ) in ("running", "starting"):
                    record["state"] = "finished"
            register.write_text(
                json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8",
            )

    def env_clean(self):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                "TMUX", "TMUX_PANE",
            ):
                env.pop(key, None)
        env.update(self.env)
        return env

    def post_steer(self, name="proj", text=STEER_TEXT):
        return self.request("POST", "/api/steer", {"name": name, "text": text})

    def make_delivery_ready(self):
        """Vollständige Zustellbarkeit nachbilden: aktiver Lauf, erfasste
        Session und gespeicherten opencode-Kennworts (nur Testkennwort)."""
        self.start_active_run()
        self.touch_run_log()
        self.write_state()
        status, data, raw = self.request("GET", "/api/run-state?name=proj")
        self.assertEqual(status, 200, raw)
        self.assertTrue(data.get("running"), "Vorbedingung aktiver Lauf fehlgeschlagen: " + raw)
        self.password_private()
        return status

    def tearDown(self):
        self.stop_active_run()
        try:
            self.set_selection(None)
        finally:
            self.password_clear()
            self.reset_state()
            self.clear_requests()


class ServerEndpointTest(ApiFixture):
    """AK A Einzelpins: /api/server meldet Auswahl und Serverfähigkeit."""

    def test_server_reports_pi_without_server_support(self):
        # Vorbedingung: harness.json wählt Pi; Aktion: GET /api/server;
        # Erwartung: harness "pi" und server_supported false.
        self.set_selection("pi")
        status, data, raw = self.request("GET", "/api/server")
        self.assertEqual(status, 200, raw)
        self.assertEqual(data.get("harness"), "pi", raw)
        self.assertFalse(data.get("server_supported", True), raw)

    def test_server_reports_opencode_support_by_default(self):
        # Vorbedingung: keine Auswahl (Default); Aktion: GET /api/server;
        # Erwartung: harness "opencode" und server_supported true.
        status, data, raw = self.request("GET", "/api/server")
        self.assertEqual(status, 200, raw)
        self.assertEqual(data.get("harness"), "opencode", raw)
        self.assertTrue(data.get("server_supported", False), raw)

    def test_server_reports_explicit_opencode_selection_as_supported(self):
        # Vorbedingung: harness.json wählt ausdrücklich opencode;
        # Aktion: GET /api/server; Erwartung: server_supported true.
        self.set_selection("opencode")
        status, data, raw = self.request("GET", "/api/server")
        self.assertEqual(status, 200, raw)
        self.assertEqual(data.get("harness"), "opencode", raw)
        self.assertTrue(data.get("server_supported", False), raw)


class SteerSelectionTest(ApiFixture):
    """AK A: /api/steer bei Pi verständliche Ablehnung ohne Zustellversuch;
    Regression opencode/ohne Auswahl/unbekannte Auswahl wie bisher."""

    def test_steer_with_selected_pi_is_rejected_without_delivery_attempt(self):
        # Vorbedingung: Pi gewählt, aktiver Lauf, erfasste Session, Kennwort
        # gesetzt und erreichbare opencode-Attrappe (volle Zustellbarkeit);
        # Aktion: POST /api/steer;
        # Erwartung: ok:false (HTTP 400, code "rejected"), Pi-Meldung mit
        # Grund, nicht die sessionbezogene Meldung, kein POST an opencode.
        self.set_selection("pi")
        self.make_delivery_ready()
        before = len(self.posts())

        status, data, raw = self.post_steer()
        self.assertEqual(status, 400, raw)
        self.assertEqual(data["error"]["code"], "rejected", raw)
        message = str(data["error"]["message"] or "")
        self.assertTrue(message.strip(), "Ablehnung braucht eine verständliche Meldung")
        self.assertIn("Pi", message, "Meldung muss die Ursache Pi nennen: " + message)
        reason_tokens = (
            "Print", "print", "--no-session", "no-session",
            "Session", "Sitzung", "fortgesetzt", "fortsetzbar",
        )
        self.assertTrue(
            any(token in message for token in reason_tokens),
            "Meldung muss den Print-Modus/die fehlende fortsetzbare Session nennen: "
            + message,
        )
        self.assertNotIn(
            SESSION_MISSING_MESSAGE, message,
            "Bei Pi darf die sessionbezogene Fehlermeldung nicht erscheinen",
        )
        self.assertEqual(
            len(self.posts()), before,
            "Bei Pi darf kein Zustellversuch an den opencode-Server stattfinden",
        )
        self.assertNotIn(
            "Zusatzanweisung an den Agenten übermittelt", self.log_text(),
            "Bei Pi darf keine Kennzeile im Protokoll stehen",
        )
        # Das Kennwort darf in keinem Ergebnis erscheinen.
        self.assertNotIn(SERVER_CREDENTIAL, raw)

    def test_steer_regression_default_selection_is_delivered_as_before(self):
        # Vorbedingung: keine Auswahl (Default opencode), volle Zustellbarkeit;
        # Aktion: POST /api/steer; Erwartung: Erfolg wie bisher inkl. Basic-Auth
        # und Kennzeile im Protokoll.
        self.make_delivery_ready()

        status, data, raw = self.post_steer()
        self.assertEqual(status, 200, raw)
        self.assertTrue(data.get("ok"), raw)
        posts = self.posts()
        self.assertTrue(posts, "opencode-Server hat keine Zustellung erhalten")
        text_found = [post for post in posts if STEER_TEXT in post.get("body", "")]
        self.assertTrue(text_found, f"Zusatztext fehlt in der Zustellung: {posts}")
        self.assertTrue(all(post.get("user") == "opencode" for post in text_found), posts)
        self.assertTrue(all(post.get("auth_ok") for post in text_found), posts)
        self.assertIn(STEER_TEXT, self.log_text())

    def test_steer_regression_explicit_opencode_selection_is_delivered(self):
        # Vorbedingung: harness.json wählt ausdrücklich opencode, volle
        # Zustellbarkeit; Aktion: POST /api/steer; Erwartung: Erfolg wie bisher.
        self.set_selection("opencode")
        self.make_delivery_ready()

        status, data, raw = self.post_steer()
        self.assertEqual(status, 200, raw)
        self.assertTrue(data.get("ok"), raw)
        self.assertTrue(self.posts(), "opencode-Server hat keine Zustellung erhalten")
        self.assertIn(STEER_TEXT, self.log_text())

    def test_unknown_harness_value_keeps_the_previous_behavior(self):
        # Vorbedingung: harness.json enthält einen unbekannten Wert; volle
        # Zustellbarkeit; Aktion: POST /api/steer;
        # Erwartung: bisheriges Verhalten (Zustellversuch/Erfolg), nicht die
        # Pi-Ablehnung und kein Absturz.
        self.set_selection("völlig-unbekannt")
        self.make_delivery_ready()

        status, data, raw = self.post_steer()
        self.assertEqual(status, 200, raw)
        self.assertTrue(data.get("ok"), "Bei unbekannter Auswahl gilt bisheriges Verhalten: " + raw)
        self.assertNotIn("Pi", str(data.get("message") or ""))
        self.assertTrue(self.posts(), "opencode-Server hat keine Zustellung erhalten")
        self.assertIn(STEER_TEXT, self.log_text())

    def test_password_secret_never_leaves_api_results(self):
        # Sicherheitsregression: Das Serverkennwort erscheint in keinem API-
        # Ergebnis, unabhängig von der gewählten Auswahl.
        self.make_delivery_ready()  # legt Kennwortdatei und Fall an
        self.set_selection("pi")
        for method, path in (
            ("GET", "/api/server"),
            ("GET", "/api/run-state?name=proj"),
            ("GET", "/api/projects"),
        ):
            status, data, raw = self.request(method, path)
            self.assertNotIn(SERVER_CREDENTIAL, raw, f"Kennwort in {path}: {raw}")
        self.post_steer()
        for post in self.posts():
            self.assertNotIn(SERVER_CREDENTIAL, json.dumps(post, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
