"""Tests für den opencode-Kompatibilitätsadapter (V-007).

Der Adapter kapselt alle Annahmen über die installierte opencode-CLI:

* Version wird über ``opencode --version`` erkannt und gegen geprüfte
  Profile verglichen. Eine lesbare, aber nicht exakt geprüfte Version wird
  als "assumed" geführt und mit dem am besten passenden geprüften Profil
  behandelt; die Meldung nennt weiterhin, dass sie nicht geprüft ist.
  Unlesbare, fehlende und fehlgeschlagene Prüfungen bleiben fail-closed.
* Modelllisting läuft über den Adapter; unerwartete Ausgabe, Fehlercode,
  fehlendes Programm und Zeitüberschreitung werden als Fehler gemeldet.
* Agentenregeln (Verzeichnis, Pflichtfelder, Modi) stammen aus dem Profil.
* Das MCP-Schema wird aus der tatsächlichen Konfiguration erkannt. Für eine
  leere Konfiguration liefert nur das Profil einer geprüften oder als
  "assumed" erkannten Version das Schema; die Meldung nennt dann die
  ungeprüfte Verwendung. Unlesbare Versionen werden nicht auf
  ``mcp.servers`` festgelegt.
* Serverstart verwendet den geprüften Unterbefehl samt Argumentliste.
* Eine erkannte Version unterhalb aller geprüften Profile erhält das älteste
  geprüfte Profil (nicht das neueste).
* Eine nur angenommene Version wird nirgends stillschweigend behandelt: Der
  Serverstart weist vor dem Start auf die ungeprüfte Version hin, und das
  Speichern eines MCP-Servers über die Web-API nennt den Hinweis in der
  Erfolgsmeldung.

Alle externen Aufrufe laufen gegen Fixtures oder Attrappen in temporären
Verzeichnissen. Es werden keine echten Modellaufrufe, MCP-Server oder
opencode-Dienste gestartet. Das echte Dashboard wird als isolierter Prozess
auf freiem Port gestartet; geprüft werden die tatsächlichen HTTP-Antworten,
kein Browser.
"""
import contextlib
import http.client
import importlib.machinery
import importlib.util
import io
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
ADAPTER = BIN / "vibe_opencode.py"
CLI = BIN / "vibe"
MCP = BIN / "vibe_mcp.py"
WEB = BIN / "vibe-web.py"


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


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


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

        self.assertEqual(info.status, "assumed")
        self.assertEqual(info.version, "2.2.0")
        self.assertIn("2.1.4", info.message)
        self.assertIn("nicht geprüft", info.message)

    def test_readable_newer_version_is_assumed_with_the_tested_fallback_profile(self):
        info = self.probe("opencode v2.2.6\n")

        self.assertEqual(info.status, "assumed")
        self.assertEqual(info.version, "2.2.6")
        self.assertEqual(info.profile, self.adapter.PROFILES[self.adapter.TESTED_VERSION])
        self.assertIn("nicht geprüft", info.message)
        self.assertIn("2.1.4", info.message)

    def test_readable_older_version_is_assumed_with_the_fallback_profile(self):
        info = self.probe("opencode v2.0.0\n")

        self.assertEqual(info.status, "assumed")
        self.assertEqual(info.version, "2.0.0")
        self.assertEqual(info.profile["version"], self.adapter.TESTED_VERSION)
        self.assertIn("nicht geprüft", info.message)

    def test_assumed_profile_is_the_highest_checked_version_at_or_below_the_detected_one(self):
        newer = dict(self.adapter.PROFILES[self.adapter.TESTED_VERSION], version="2.9.9")
        self.adapter.PROFILES["2.9.9"] = newer
        self.addCleanup(self.adapter.PROFILES.pop, "2.9.9", None)

        above_all = self.probe("opencode v3.0.0\n")
        between = self.probe("opencode v2.5.0\n")

        self.assertEqual(above_all.status, "assumed")
        self.assertEqual(above_all.profile["version"], "2.9.9")
        self.assertEqual(between.status, "assumed")
        self.assertEqual(between.profile["version"], self.adapter.TESTED_VERSION)

    def test_version_below_all_checked_profiles_is_assumed_with_the_oldest_profile(self):
        newer = dict(self.adapter.PROFILES[self.adapter.TESTED_VERSION], version="2.9.9")
        self.adapter.PROFILES["2.9.9"] = newer
        self.addCleanup(self.adapter.PROFILES.pop, "2.9.9", None)

        info = self.probe("opencode v1.0.0\n")

        self.assertEqual(info.status, "assumed")
        self.assertEqual(info.version, "1.0.0")
        self.assertEqual(info.profile["version"], self.adapter.TESTED_VERSION)
        self.assertIn("nicht geprüft", info.message)

    def test_an_exactly_listed_newer_profile_is_supported_not_assumed(self):
        newer = dict(self.adapter.PROFILES[self.adapter.TESTED_VERSION], version="2.9.9")
        self.adapter.PROFILES["2.9.9"] = newer
        self.addCleanup(self.adapter.PROFILES.pop, "2.9.9", None)

        info = self.probe("opencode v2.9.9\n")

        self.assertEqual(info.status, "supported")
        self.assertEqual(info.version, "2.9.9")

    def test_checked_is_true_only_for_the_exactly_tested_version(self):
        tested = self.probe("opencode v2.1.4\n")
        assumed = self.probe("opencode v2.2.6\n")
        unreadable = self.probe("irgendein Text\n")

        self.assertTrue(tested.checked)
        self.assertTrue(tested.supported)
        self.assertTrue(assumed.supported)
        self.assertFalse(assumed.checked)
        self.assertFalse(unreadable.supported)
        self.assertFalse(unreadable.checked)

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

    def test_assumed_version_lists_models_and_warns(self):
        runner = fake_runner("opencode v2.2.6\n", models_output="opencode/model-a\n")

        result = self.adapter.list_models(runner=runner)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["models"], ["opencode/model-a"])
        self.assertIn("nicht geprüft", result["warning"])
        self.assertEqual(result["version"].status, "assumed")
        self.assertIn(["opencode", "models", "--standalone"], runner.calls)


class ServerCommandTest(AdapterTestCase):
    def test_server_command_uses_the_tested_subcommand_and_argument_list(self):
        info = self.adapter.probe(runner=fake_runner("opencode v2.1.4\n"))

        command = self.adapter.server_command(4096, info=info)

        self.assertEqual(
            command,
            ["opencode", "serve", "--hostname", "127.0.0.1", "--port", "4096"],
        )

    def test_assumed_version_builds_the_server_command_from_the_fallback_profile(self):
        info = self.adapter.probe(runner=fake_runner("opencode v2.2.6\n"))

        command = self.adapter.server_command(4096, info=info)

        self.assertEqual(
            command,
            ["opencode", "serve", "--hostname", "127.0.0.1", "--port", "4096"],
        )
        self.assertEqual(
            self.adapter.require_supported(info),
            self.adapter.PROFILES[self.adapter.TESTED_VERSION],
        )

    def test_unreadable_version_output_is_refused_with_a_clear_message(self):
        info = self.adapter.probe(runner=fake_runner("irgendein Text ohne Version\n"))

        with self.assertRaises(self.adapter.CompatibilityError) as raised:
            self.adapter.server_command(4096, info=info)

        self.assertIn("2.1.4", str(raised.exception))

    def test_error_exit_and_timeout_are_refused(self):
        for runner in (fake_runner("Fehler beim Start\n", 2),
                       fake_runner("Zeitüberschreitung nach 15 s\n", 124)):
            info = self.adapter.probe(runner=runner)

            self.assertFalse(info.supported)
            self.assertFalse(info.profile)
            with self.assertRaises(self.adapter.CompatibilityError):
                self.adapter.server_command(4096, info=info)
            with self.assertRaises(self.adapter.CompatibilityError):
                self.adapter.require_supported(info)

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

    def test_empty_config_uses_the_fallback_profile_for_an_assumed_version(self):
        info = self.adapter.probe(runner=fake_runner("opencode v2.2.6\n"))

        result = self.adapter.detect_mcp_layout({}, info=info)

        self.assertEqual(result["layout"], self.adapter.LAYOUT_SERVERS)
        self.assertEqual(result["source"], "profile")
        self.assertIn("2.2.6", result["message"])
        self.assertTrue(
            any(term in result["message"] for term in ("ungeprüft", "nicht geprüft")),
            result["message"],
        )

    def test_empty_config_is_not_assumed_for_an_unreadable_version(self):
        info = self.adapter.probe(runner=fake_runner("irgendein Text ohne Version\n"))

        result = self.adapter.detect_mcp_layout({}, info=info)

        self.assertEqual(result["layout"], self.adapter.LAYOUT_UNKNOWN)
        self.assertIn("nicht geprüft", result["message"])

    def test_mixed_mcp_block_stays_unknown_for_an_assumed_version(self):
        config = {
            "mcp": {
                "alt": {"type": "local", "command": ["echo"]},
                "unbekannt": {"etwas": "anderes"},
            }
        }
        info = self.adapter.probe(runner=fake_runner("opencode v2.2.6\n"))

        result = self.adapter.detect_mcp_layout(config, info=info)

        self.assertEqual(result["layout"], self.adapter.LAYOUT_UNKNOWN)

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

    def test_assumed_version_writes_with_the_fallback_schema(self):
        write_fake_opencode(self.fakebin, version="opencode v9.9.9")

        self.mcp.save("global", "neu", {"type": "local", "command": ["echo", "neu"]})

        written = self.config.read_text(encoding="utf-8")
        self.assertIn('"mcp"', written)
        self.assertIn('"servers"', written)
        self.assertEqual(list(self.mcp.load("global")[4]), ["neu"])

    def test_unreadable_version_output_refuses_to_write_without_schema_evidence(self):
        write_fake_opencode(self.fakebin, version="opencode ohne erkennbare Versionsnummer")

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


class VibeCliTestCase(unittest.TestCase):
    """Gemeinsame Umgebung: isoliertes VIBE/HOME, opencode-Attrappe im PATH."""

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


class VibeIntegrationTest(VibeCliTestCase):
    """bin/vibe nutzt den Adapter für Modelle und Serverstart."""

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

    def test_server_start_allows_an_assumed_version(self):
        write_fake_opencode(self.fakebin, version="opencode v9.9.9")
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
        self.assertIn("--port " + str(self.cli.PATHS.opencode_port), inner)

    def test_server_start_names_an_assumed_version_before_starting(self):
        write_fake_opencode(self.fakebin, version="opencode v9.9.9")
        out = io.StringIO()
        calls = []
        out_at_new_session = []

        def fake_run(argv, cwd=None, timeout=60, env=None):
            calls.append(list(argv))
            if "has-session" in argv:
                return 1, ""
            if "new-session" in argv:
                out_at_new_session.append(out.getvalue())
            return 0, ""

        with mock.patch.object(self.cli, "run", side_effect=fake_run), \
                mock.patch.object(self.cli, "server_health", side_effect=[None, "ok"]), \
                mock.patch.object(self.cli, "port_in_use", return_value=False), \
                mock.patch.object(self.cli.time, "sleep", return_value=None):
            self.cli.cmd_server("start", out=out)

        self.assertIn("nicht geprüft", out.getvalue())
        new_sessions = [call for call in calls if "new-session" in call]
        self.assertEqual(len(new_sessions), 1, calls)
        self.assertEqual(len(out_at_new_session), 1, calls)
        self.assertIn("nicht geprüft", out_at_new_session[0])

    def test_server_start_refuses_an_unreadable_version(self):
        write_fake_opencode(self.fakebin, version="opencode ohne erkennbare Versionsnummer")
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


class DoctorAssumedVersionTest(VibeCliTestCase):
    """Der Doctor behandelt eine nur angenommene Version als Warnung.

    Review-Befund F26, Runde 2 (Medium): doctor_checks()/cmd_doctor zeigten
    bei einer als assumed erkannten opencode-Version ein glattes OK ohne
    Hinweis. Eine angenommene Version bleibt nutzbar, darf aber nicht wie
    eine geprüfte aussehen: doctor_checks meldet ok=True mit der
    Probe-Meldung als Hinweis, cmd_doctor druckt eine HINWEIS-Zeile statt
    eines glatten OK. Fehlende und unlesbare Versionen bleiben ok=False,
    eine geprüfte Version bekommt keinen Hinweis; ok mit nichtleerem
    Hinweis bleibt damit eindeutig die Warnebene.
    """

    def version_entries(self):
        return [
            (label, ok, hint)
            for label, ok, hint in self.cli.doctor_checks()
            if label.startswith("opencode-Version")
        ]

    def cmd_doctor_output(self, tty=False):
        """Fängt die cmd_doctor-Ausgabe; „im Container" besteht damit (ok=True)."""
        class Output(io.StringIO):
            def isatty(self):
                return tty

        out = Output()
        with mock.patch.object(self.cli, "in_container", return_value=True), \
                contextlib.redirect_stdout(out):
            self.cli.cmd_doctor()
        return out.getvalue()

    def test_doctor_lists_an_assumed_version_with_its_hint(self):
        write_fake_opencode(self.fakebin, version="opencode v9.9.9")

        entries = self.version_entries()

        self.assertEqual(len(entries), 1, entries)
        label, ok, hint = entries[0]
        self.assertIn("9.9.9", label)
        self.assertIn("nicht geprüft", label)
        self.assertTrue(ok, entries)
        self.assertEqual(hint, self.cli.vibe_opencode.probe().message)
        self.assertIn("9.9.9", hint)
        self.assertIn("nicht geprüft", hint)
        self.assertIn(self.cli.vibe_opencode.TESTED_VERSION, hint)

    def test_doctor_keeps_a_missing_opencode_failed(self):
        os.environ["PATH"] = str(self.fakebin)  # kein opencode abgelegt

        entries = self.version_entries()

        self.assertEqual(len(entries), 1, entries)
        label, ok, hint = entries[0]
        self.assertFalse(ok, entries)
        self.assertTrue(hint, entries)
        self.assertEqual(hint, self.cli.vibe_opencode.probe().message)

    def test_doctor_keeps_an_unreadable_version_failed(self):
        write_fake_opencode(
            self.fakebin, version="opencode ohne erkennbare Versionsnummer"
        )

        entries = self.version_entries()

        self.assertEqual(len(entries), 1, entries)
        label, ok, hint = entries[0]
        self.assertFalse(ok, entries)
        self.assertTrue(hint, entries)
        self.assertEqual(hint, self.cli.vibe_opencode.probe().message)

    def test_doctor_lists_a_supported_version_without_a_hint(self):
        write_fake_opencode(self.fakebin)

        entries = self.version_entries()

        self.assertEqual(len(entries), 1, entries)
        label, ok, hint = entries[0]
        self.assertIn(self.cli.vibe_opencode.TESTED_VERSION, label)
        self.assertNotIn("nicht geprüft", label)
        self.assertTrue(ok, entries)
        self.assertEqual(hint, "")

    def test_doctor_output_hints_an_assumed_version_instead_of_plain_ok(self):
        write_fake_opencode(self.fakebin, version="opencode v9.9.9")

        # ANDROID_HOME ist gesetzt, damit der ANDROID_HOME-Check ein reines
        # OK ohne den Hinweistext „source ~/.bashrc im Container" liefert;
        # sonst zählt der Zähler je nach Umgebung 2 statt 1 Zeile.
        with mock.patch.dict(os.environ, {"ANDROID_HOME": "/opt/android-sdk"}):
            text = self.cmd_doctor_output()

        version_lines = [
            line for line in text.splitlines() if "opencode-Version" in line
        ]
        container_lines = [
            line for line in text.splitlines() if "im Container" in line
        ]
        self.assertEqual(len(version_lines), 1, text)
        self.assertIn("HINW", version_lines[0], text)
        self.assertIn("9.9.9", version_lines[0], text)
        self.assertIn("nicht geprüft", version_lines[0], text)
        self.assertIn("->", version_lines[0], text)
        self.assertFalse(version_lines[0].strip().startswith("OK"), text)
        self.assertEqual(len(container_lines), 1, text)
        self.assertTrue(container_lines[0].strip().startswith("OK"), text)
        self.assertNotIn("HINW", container_lines[0], text)

    def test_doctor_output_hints_an_assumed_version_in_yellow(self):
        write_fake_opencode(self.fakebin, version="opencode v9.9.9")

        text = self.cmd_doctor_output(tty=True)

        version_lines = [
            line for line in text.splitlines() if "opencode-Version" in line
        ]
        self.assertEqual(len(version_lines), 1, text)
        self.assertIn(self.cli.C["y"], version_lines[0], text)

    def test_doctor_output_shows_plain_ok_for_a_supported_version(self):
        write_fake_opencode(self.fakebin)

        text = self.cmd_doctor_output()

        version_lines = [
            line for line in text.splitlines() if "opencode-Version" in line
        ]
        self.assertEqual(len(version_lines), 1, text)
        self.assertTrue(version_lines[0].strip().startswith("OK"), text)
        self.assertNotIn("HINW", version_lines[0], text)
        self.assertNotIn("nicht geprüft", version_lines[0], text)


class WebMcpSaveApiTest(unittest.TestCase):
    """Die Web-API nennt in der Erfolgsmeldung eine nicht geprüfte Version.

    Das echte Dashboard (bin/vibe-web.py) läuft als eigener Prozess mit
    temporärem VIBE/HOME, freiem Port und einer opencode-Attrappe (v9.9.9).
    Die Konfiguration ist leer, damit das Speichern über das geprüfte
    Profilschema laufen muss. Geprüft wird die tatsächliche HTTP-Antwort,
    kein Browser.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.fakebin = cls.root / "fakebin"
        write_fake_opencode(cls.fakebin, version="opencode v9.9.9")
        cls.config = cls.home / ".config" / "opencode" / "opencode.json"
        cls.port = free_port()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key == "XDG_CONFIG_HOME":
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "VIBE_INSTALL": str(cls.root / "_toolchain"),
                "VIBE_RUNTIME": str(cls.root / "_logs"),
                "VIBE_STATE": str(cls.root / "_state"),
                "HOME": str(cls.home),
                "XDG_CONFIG_HOME": str(cls.home / ".config"),
                "PATH": str(cls.fakebin) + os.pathsep + env.get("PATH", ""),
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
                    with socket.create_connection(
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

    def save_request(self):
        payload = json.dumps(
            {
                "action": "save",
                "scope": "global",
                "name": "neu",
                "create": True,
                "entry": {"type": "local", "command": ["echo", "neu"]},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {
            "Host": "127.0.0.1:%d" % self.port,
            "X-Token": self.token,
            "Content-Type": "application/json",
        }
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            connection.request("POST", "/api/mcp", body=payload, headers=headers)
            response = connection.getresponse()
            return response.status, response.read().decode("utf-8", "replace")
        finally:
            connection.close()

    def test_save_success_message_names_an_unchecked_version(self):
        status, body = self.save_request()

        self.assertEqual(status, 200, body)
        data = json.loads(body)
        self.assertTrue(data.get("ok"), data)
        self.assertIn("nicht geprüft", data.get("message", ""), body)
        written = self.config.read_text(encoding="utf-8")
        self.assertIn('"servers"', written)


if __name__ == "__main__":
    unittest.main()
