"""Tests für den opencode-Kompatibilitätsadapter (V-007).

Der Adapter kapselt alle Annahmen über die installierte opencode-CLI:

* Version wird über ``opencode --version`` erkannt und gegen ein geprüftes
  Profil (2.1.4) verglichen. Unbekannte, unlesbare oder fehlende Versionen
  werden verständlich gemeldet, nicht geraten.
* Modelllisting läuft über den Adapter; unerwartete Ausgabe, Fehlercode,
  fehlendes Programm und Zeitüberschreitung werden als Fehler gemeldet.
* Agentenregeln (Verzeichnis, Pflichtfelder, Modi) stammen aus dem Profil.
* Das MCP-Schema wird aus der tatsächlichen Konfiguration erkannt. Nur für
  die geprüfte Version darf eine leere Konfiguration das geprüfte Schema
  verwenden; unbekannte Versionen werden nicht auf ``mcp.servers`` festgelegt.
* Serverstart verwendet den geprüften Unterbefehl samt Argumentliste.

Alle externen Aufrufe laufen gegen Fixtures oder Attrappen in temporären
Verzeichnissen. Es werden keine echten Modellaufrufe, MCP-Server oder
opencode-Dienste gestartet.
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
ADAPTER = BIN / "vibe_opencode.py"
CLI = BIN / "vibe"
MCP = BIN / "vibe_mcp.py"


def load_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def fake_runner(version_output, version_rc=0, models_output="", models_rc=0):
    """Liefert eine Attrappe für den Prozessstart des Adapters."""
    calls = []

    def runner(argv, timeout=15):
        calls.append(list(argv))
        if "--version" in argv:
            return version_rc, version_output
        if "models" in argv:
            return models_rc, models_output
        return 2, "unerwarteter Aufruf: " + " ".join(argv)

    runner.calls = calls
    return runner


def write_fake_opencode(directory, version="opencode v2.1.4", models="opencode/model-a\n"):
    """Schreibt eine ausführbare opencode-Attrappe in ein temporäres Verzeichnis."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "opencode"
    path.write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = \"--version\" ]; then\n"
        f"  printf '%b\\n' {version!r}\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"$1\" = \"models\" ]; then\n"
        f"  printf '%b' {models!r}\n"
        "  exit 0\n"
        "fi\n"
        "echo 'unerwarteter Aufruf' >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


class AdapterTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.adapter = load_module(ADAPTER, "vibe_opencode_v007_under_test")

    def tearDown(self):
        self.tmp.cleanup()


class VersionProbeTest(AdapterTestCase):
    def probe(self, output, rc=0):
        return self.adapter.probe(runner=fake_runner(output, rc))

    def test_tested_version_fixture_is_supported(self):
        info = self.probe("opencode v2.1.4\n")

        self.assertEqual(info.status, "supported")
        self.assertEqual(info.version, "2.1.4")
        self.assertIsNotNone(info.profile)
        self.assertEqual(info.profile["mcp_layout"], self.adapter.LAYOUT_SERVERS)

    def test_version_with_banner_and_build_suffix_is_supported(self):
        info = self.probe("opencode 2.1.4 (build 9f3c)\n")

        self.assertEqual(info.status, "supported")
        self.assertEqual(info.version, "2.1.4")

    def test_other_version_is_reported_as_unchecked(self):
        info = self.probe("opencode v2.2.0\n")

        self.assertEqual(info.status, "unknown")
        self.assertEqual(info.version, "2.2.0")
        self.assertIn("2.1.4", info.message)
        self.assertIn("nicht geprüft", info.message)

    def test_unrecognized_output_is_reported_instead_of_guessed(self):
        info = self.probe("irgendein unerwarteter Text\n")

        self.assertEqual(info.status, "unknown")
        self.assertFalse(info.version)
        self.assertIn("nicht erkannt", info.message)
        self.assertIn("2.1.4", info.message)

    def test_missing_binary_is_reported(self):
        info = self.probe("Programm nicht gefunden: opencode", 127)

        self.assertEqual(info.status, "missing")
        self.assertIn("nicht gefunden", info.message)

    def test_error_exit_code_is_reported_with_output(self):
        info = self.probe("Fehler beim Start\n", 2)

        self.assertEqual(info.status, "error")
        self.assertIn("Exit 2", info.message)
        self.assertIn("Fehler beim Start", info.message)

    def test_timeout_is_reported(self):
        info = self.probe("Zeitüberschreitung nach 15 s: opencode", 124)

        self.assertEqual(info.status, "timeout")
        self.assertIn("Zeit", info.message)

    def test_real_runner_handles_missing_binary_error_code_and_timeout(self):
        missing_rc, missing_out = self.adapter.run_command(
            ["vibe-v007-programm-gibt-es-nicht"], timeout=2
        )
        self.assertEqual(missing_rc, 127)
        self.assertIn("nicht gefunden", missing_out)

        failing = self.root / "fail.py"
        failing.write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
        fail_rc, _ = self.adapter.run_command([sys.executable, str(failing)], timeout=5)
        self.assertEqual(fail_rc, 3)

        slow = self.root / "slow.py"
        slow.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
        slow_rc, slow_out = self.adapter.run_command([sys.executable, str(slow)], timeout=0.2)
        self.assertEqual(slow_rc, 124)
        self.assertIn("Zeitüberschreitung", slow_out)


class ModelListingTest(AdapterTestCase):
    def supported(self):
        return self.adapter.probe(runner=fake_runner("opencode v2.1.4\n"))

    def test_models_are_read_from_the_tested_command(self):
        runner = fake_runner(
            "opencode v2.1.4\n",
            models_output="opencode/model-a\nprovider/model-b\n",
        )
        result = self.adapter.list_models(runner=runner)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["models"], ["opencode/model-a", "provider/model-b"])
        self.assertEqual(result["warning"], "")
        self.assertIn(["opencode", "models", "--standalone"], runner.calls)

    def test_unexpected_output_is_an_error_not_an_empty_success(self):
        result = self.adapter.list_models(
            runner=fake_runner("opencode v2.1.4\n", models_output="Keine Modelle verfügbar\n")
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["models"], [])
        self.assertIn("nicht erkannt", result["error"])

    def test_empty_output_is_a_valid_empty_list(self):
        result = self.adapter.list_models(
            runner=fake_runner("opencode v2.1.4\n", models_output="")
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["models"], [])

    def test_error_exit_code_is_reported(self):
        result = self.adapter.list_models(
            runner=fake_runner(
                "opencode v2.1.4\n",
                models_output="Error: Dienst belegt\n",
                models_rc=1,
            )
        )

        self.assertFalse(result["ok"])
        self.assertIn("Exit 1", result["error"])
        self.assertIn("Dienst belegt", result["error"])

    def test_missing_binary_is_reported_without_running_models(self):
        runner = fake_runner("Programm nicht gefunden: opencode", 127)
        result = self.adapter.list_models(runner=runner)

        self.assertFalse(result["ok"])
        self.assertIn("nicht gefunden", result["error"])
        self.assertEqual(runner.calls, [["opencode", "--version"]])

    def test_timeout_is_reported(self):
        result = self.adapter.list_models(
            runner=fake_runner(
                "opencode v2.1.4\n",
                models_output="Zeitüberschreitung nach 30 s: opencode",
                models_rc=124,
            )
        )

        self.assertFalse(result["ok"])
        self.assertIn("Zeit", result["error"])

    def test_unknown_version_still_lists_models_but_warns(self):
        result = self.adapter.list_models(
            runner=fake_runner("opencode v9.9.9\n", models_output="opencode/model-a\n")
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["models"], ["opencode/model-a"])
        self.assertIn("nicht geprüft", result["warning"])


class ServerCommandTest(AdapterTestCase):
    def test_server_command_uses_the_tested_subcommand_and_argument_list(self):
        info = self.adapter.probe(runner=fake_runner("opencode v2.1.4\n"))

        command = self.adapter.server_command(4096, info=info)

        self.assertEqual(
            command,
            ["opencode", "serve", "--hostname", "127.0.0.1", "--port", "4096"],
        )

    def test_unknown_version_is_refused_with_a_clear_message(self):
        info = self.adapter.probe(runner=fake_runner("opencode v2.2.0\n"))

        with self.assertRaises(self.adapter.CompatibilityError) as raised:
            self.adapter.server_command(4096, info=info)

        self.assertIn("2.1.4", str(raised.exception))
        self.assertIn("nicht geprüft", str(raised.exception))

    def test_missing_binary_is_refused(self):
        info = self.adapter.probe(runner=fake_runner("", 127))

        with self.assertRaises(self.adapter.CompatibilityError) as raised:
            self.adapter.server_command(4096, info=info)

        self.assertIn("nicht gefunden", str(raised.exception))

    def test_invalid_port_is_rejected(self):
        info = self.adapter.probe(runner=fake_runner("opencode v2.1.4\n"))

        for port in (0, -1, 65536, "4096"):
            with self.assertRaises(ValueError):
                self.adapter.server_command(port, info=info)


class AgentRulesTest(AdapterTestCase):
    def test_project_agent_directory_comes_from_the_profile(self):
        self.assertEqual(
            self.adapter.agent_directory("/projekt"),
            os.path.join("/projekt", ".opencode", "agents"),
        )

    def test_valid_frontmatter_and_prompt_are_accepted(self):
        self.adapter.validate_agent(
            {"description": "Prüft Änderungen", "mode": "subagent"}, "Prompt.\n"
        )

    def test_missing_description_is_rejected(self):
        with self.assertRaises(ValueError) as raised:
            self.adapter.validate_agent({"mode": "all"}, "Prompt.\n")

        self.assertIn("description", str(raised.exception))

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError) as raised:
            self.adapter.validate_agent(
                {"description": "Prüft", "mode": "irgendwas"}, "Prompt.\n"
            )

        self.assertIn("mode", str(raised.exception))

    def test_empty_prompt_is_rejected(self):
        with self.assertRaises(ValueError) as raised:
            self.adapter.validate_agent({"description": "Prüft"}, "   \n")

        self.assertIn("Prompt", str(raised.exception))


class McpLayoutTest(AdapterTestCase):
    def supported(self):
        return self.adapter.probe(runner=fake_runner("opencode v2.1.4\n"))

    def test_servers_layout_is_detected_from_the_configuration(self):
        config = {"mcp": {"servers": {"alt": {"type": "local", "command": ["echo"]}}}}

        result = self.adapter.detect_mcp_layout(config, info=self.supported())

        self.assertEqual(result["layout"], self.adapter.LAYOUT_SERVERS)
        self.assertEqual(list(result["servers"]), ["alt"])
        self.assertEqual(result["source"], "config")

    def test_classic_layout_is_detected_from_the_configuration(self):
        config = {"mcp": {"alt": {"type": "local", "command": ["echo"]}}}

        result = self.adapter.detect_mcp_layout(config, info=self.supported())

        self.assertEqual(result["layout"], self.adapter.LAYOUT_CLASSIC)
        self.assertEqual(list(result["servers"]), ["alt"])
        self.assertEqual(result["source"], "config")

    def test_mixed_classic_block_is_not_treated_as_writable_classic(self):
        config = {
            "mcp": {
                "alt": {"type": "local", "command": ["echo"]},
                "unbekannt": {"etwas": "anderes"},
            }
        }

        result = self.adapter.detect_mcp_layout(config, info=self.supported())

        self.assertEqual(result["layout"], self.adapter.LAYOUT_UNKNOWN)
        self.assertIn("zugeordnet", result["message"])

    def test_empty_config_uses_the_verified_schema_for_the_tested_version(self):
        result = self.adapter.detect_mcp_layout({}, info=self.supported())

        self.assertEqual(result["layout"], self.adapter.LAYOUT_SERVERS)
        self.assertEqual(result["source"], "profile")

    def test_empty_config_is_not_assumed_for_an_unknown_version(self):
        info = self.adapter.probe(runner=fake_runner("opencode v2.2.0\n"))

        result = self.adapter.detect_mcp_layout({}, info=info)

        self.assertEqual(result["layout"], self.adapter.LAYOUT_UNKNOWN)
        self.assertIn("nicht geprüft", result["message"])

    def test_unknown_mcp_shape_is_not_interpreted_as_servers(self):
        config = {"mcp": {"unbekannt": {"etwas": "anderes"}}}

        result = self.adapter.detect_mcp_layout(config, info=self.supported())

        self.assertEqual(result["layout"], self.adapter.LAYOUT_UNKNOWN)
        self.assertIn("zugeordnet", result["message"])


class McpIntegrationTest(unittest.TestCase):
    """vibe_mcp verwendet den Adapter statt einer Versionsannahme."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.config = self.home / ".config" / "opencode" / "opencode.json"
        self.config.parent.mkdir(parents=True)
        self.fakebin = self.root / "fakebin"
        self.env = mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.home),
                "VIBE": str(self.root / "vibe"),
                "VIBE_NO_CONTAINER": "1",
                "PATH": str(self.fakebin) + os.pathsep + os.environ.get("PATH", ""),
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tmp.cleanup)
        self.cli = load_module(CLI, "vibe_opencode_mcp_under_test")
        sys.modules["vibe"] = self.cli
        self.addCleanup(sys.modules.pop, "vibe", None)
        self.mcp = load_module(MCP, "vibe_mcp_opencode_under_test")

    def test_classic_config_is_read_without_assuming_servers(self):
        self.config.write_text(
            '{"mcp": {"alt": {"type": "local", "command": ["echo"]}}}\n',
            encoding="utf-8",
        )
        write_fake_opencode(self.fakebin)

        path, _text, _data, layout, servers, _digest = self.mcp.load("global")

        self.assertEqual(layout, "classic")
        self.assertEqual(list(servers), ["alt"])
        self.assertEqual(str(self.config), path)

    def test_tested_version_may_create_a_config_with_the_verified_layout(self):
        write_fake_opencode(self.fakebin)

        self.mcp.save("global", "neu", {"type": "local", "command": ["echo", "neu"]})

        written = self.config.read_text(encoding="utf-8")
        self.assertIn('"mcp"', written)
        self.assertIn('"servers"', written)
        self.assertEqual(list(self.mcp.load("global")[4]), ["neu"])

    def test_unknown_version_refuses_to_write_without_schema_evidence(self):
        write_fake_opencode(self.fakebin, version="opencode v9.9.9")

        with self.assertRaises(ValueError) as raised:
            self.mcp.save("global", "neu", {"type": "local", "command": ["echo"]})

        self.assertIn("nicht geprüft", str(raised.exception))
        self.assertFalse(self.config.exists())

    def test_mixed_classic_config_is_refused_and_kept_unchanged(self):
        original = (
            '{"mcp": {"alt": {"type": "local", "command": ["echo"]},'
            ' "unbekannt": {"etwas": "anderes"}}}\n'
        )
        self.config.write_text(original, encoding="utf-8")
        write_fake_opencode(self.fakebin)

        with self.assertRaises(ValueError) as raised:
            self.mcp.save("global", "neu", {"type": "local", "command": ["echo"]})

        self.assertIn("nicht feststellbar", str(raised.exception))
        self.assertEqual(self.config.read_text(encoding="utf-8"), original)


class VibeIntegrationTest(unittest.TestCase):
    """bin/vibe nutzt den Adapter für Modelle und Serverstart."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.fakebin = self.root / "fakebin"
        self.env = mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.home),
                "VIBE": str(self.root / "vibe"),
                "VIBE_NO_CONTAINER": "1",
                "PATH": str(self.fakebin) + os.pathsep + os.environ.get("PATH", ""),
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tmp.cleanup)
        self.cli = load_module(CLI, "vibe_opencode_cli_under_test")

    def test_models_list_uses_the_adapter(self):
        write_fake_opencode(self.fakebin, models="opencode/model-a\nprovider/model-b\n")

        self.assertEqual(self.cli.models_list(), ["opencode/model-a", "provider/model-b"])

    def test_agent_validation_uses_the_adapter_rules(self):
        with self.assertRaises(ValueError) as raised:
            self.cli.agent_validate("---\nmode: all\n---\nPrompt\n")

        self.assertIn("description", str(raised.exception))

    def test_server_start_uses_the_tested_command(self):
        write_fake_opencode(self.fakebin)
        calls = []

        def fake_run(argv, cwd=None, timeout=60, env=None):
            calls.append(list(argv))
            if "has-session" in argv:
                return 1, ""
            return 0, ""

        with mock.patch.object(self.cli, "run", side_effect=fake_run), \
                mock.patch.object(self.cli, "server_health", side_effect=[None, "ok"]), \
                mock.patch.object(self.cli, "port_in_use", return_value=False), \
                mock.patch.object(self.cli.time, "sleep", return_value=None):
            self.cli.cmd_server("start")

        tmux = [call for call in calls if call and call[0] == "tmux"]
        new_sessions = [call for call in tmux if "new-session" in call]
        self.assertEqual(len(new_sessions), 1, calls)
        inner = new_sessions[0][-1]
        self.assertIn("opencode serve", inner)
        self.assertIn("--hostname 127.0.0.1", inner)
        self.assertIn("--port " + str(self.cli.PATHS.opencode_port), inner)

    def test_server_start_refuses_an_unknown_version(self):
        write_fake_opencode(self.fakebin, version="opencode v9.9.9")
        calls = []

        def fake_run(argv, cwd=None, timeout=60, env=None):
            calls.append(list(argv))
            if "has-session" in argv:
                return 1, ""
            return 0, ""

        with mock.patch.object(self.cli, "run", side_effect=fake_run), \
                mock.patch.object(self.cli, "server_health", return_value=None), \
                mock.patch.object(self.cli, "port_in_use", return_value=False):
            with self.assertRaises(SystemExit) as raised:
                self.cli.cmd_server("start")

        self.assertIn("2.1.4", str(raised.exception))
        self.assertFalse(
            [call for call in calls if call and "new-session" in call],
            calls,
        )

    def test_doctor_reports_the_compatibility_status(self):
        write_fake_opencode(self.fakebin)

        checks = dict((label, ok) for label, ok, _hint in self.cli.doctor_checks())

        matching = [label for label in checks if label.startswith("opencode-Version")]
        self.assertEqual(len(matching), 1, list(checks))
        self.assertTrue(checks[matching[0]], checks)


if __name__ == "__main__":
    unittest.main()
