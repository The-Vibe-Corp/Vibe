"""Tests für den Projekttyp ``rebuild`` (F14).

Der Typ ist ein Projektprofil: Vorlage, Rollen, Parität/savegame-Regeln und
ein Werkzeugprüfer, der fehlende Entwicklungsumgebung erkennt und auf
ausdrückliche Bestätigung installiert. Die Tests prüfen das Profil über die
echte CLI, den Agentenvalidator und den Werkzeugprüfer; sie installieren
nichts und rufen keine externen Werkzeuge oder Netze auf.
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
TEMPLATES = REPO / "templates"
PROFILE = TEMPLATES / "rebuild"
ENV_SCRIPT = PROFILE / "scripts" / "rebuild-env.py"

EXPECTED_AGENTS = {
    "rebuild-orchestrator",
    "rebuild-discovery",
    "rebuild-reverse",
    "rebuild-spec",
    "rebuild-architecture",
    "rebuild-implementation",
    "rebuild-parity",
    "rebuild-packaging",
    "rebuild-ci",
}


def load_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def load_cli(vibe_root, home):
    old = {key: os.environ.get(key) for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    try:
        return load_module(CLI, "vibe_rebuild_cli_under_test")
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def read_env(path):
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


class ProfileTest(unittest.TestCase):
    def test_rebuild_type_creates_agents_parity_rules_and_toolcheck(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "ws"
            workspace.mkdir()
            home = root / "home"
            home.mkdir()
            cli = load_cli(workspace, home)
            cli.TPL = str(TEMPLATES)
            self.assertIn("rebuild", cli.types())

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                cli.cmd_new("rebuild-demo", "rebuild")

            project = workspace / "rebuild-demo"
            env = read_env(project / ".vibe" / "project.env")
            self.assertEqual(env["TYPE"], "rebuild")
            self.assertEqual(env["SANDBOX"], "on")
            self.assertIn("rebuild-env.py --check", env["VERIFY_QUICK"])
            self.assertIn("rebuild-env.py --check", env["VERIFY_FULL"])
            self.assertIn("VERIFY_TESTS", env)
            self.assertIn("VERIFY_MIN_TESTS", env)

            sandbox_tools = env["SANDBOX_TOOLS"].split()
            for tool in ("git", "python3", "wine", "java", "ghidra", "gdb", "strace", "objdump", "readelf", "appimagetool", "podman"):
                self.assertIn(tool, sandbox_tools)

            agents = sorted((project / ".opencode" / "agents").glob("*.md"))
            self.assertEqual({path.stem for path in agents}, EXPECTED_AGENTS)
            for path in agents:
                self.assertTrue(cli.agent_validate(path.read_text(encoding="utf-8")), path.name)

            for relative in ("docs/parity.md", "docs/reverse-engineering.md", "scripts/rebuild-env.py", "AGENTS.md"):
                self.assertTrue((project / relative).is_file(), relative)

            parity = (project / "docs" / "parity.md").read_text(encoding="utf-8")
            self.assertIn("Speicherstände", parity)
            self.assertIn("1:1", parity)
            agents_doc = (project / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("rebuild-env.py --check", agents_doc)
            self.assertIn("Speicherstände", agents_doc)

            self.assertTrue((project / ".git").exists())
            self.assertIn("rebuild", output.getvalue())


class ToolCheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module(ENV_SCRIPT, "vibe_rebuild_env_under_test")

    def fake_which(self, present):
        return lambda command: "/fake/bin/" + command if command in present else None

    def all_commands(self, *, omit=()):
        commands = set()
        for tool in self.module.TOOLS:
            commands.update(tool.commands)
        return commands - set(omit)

    def test_missing_required_tool_is_reported_and_blocks(self):
        result = self.module.check(
            which=self.fake_which(self.all_commands(omit=("gdb",))),
            required_groups=("core", "analyse"),
        )

        self.assertFalse(result["ok"])
        self.assertIn("gdb", result["missing_required"])
        self.assertNotIn("gdb", result["missing_optional"])

    def test_missing_optional_tool_is_reported_but_does_not_block(self):
        result = self.module.check(
            which=self.fake_which(self.all_commands(omit=("analyzeHeadless", "ghidra", "appimagetool"))),
            required_groups=("core", "analyse"),
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["missing_required"], [])
        self.assertIn("ghidra", result["missing_optional"])
        self.assertIn("appimagetool", result["missing_optional"])

    def test_install_plan_maps_missing_tools_to_packages_and_manual_steps(self):
        plan = self.module.install_plan(
            ["gdb", "wine", "ghidra"],
            manager="dnf",
            which=self.fake_which({"sudo"}),
            euid=1000,
        )

        self.assertEqual(plan["manager"], "dnf")
        self.assertEqual(len(plan["commands"]), 1)
        command = plan["commands"][0]
        self.assertEqual(command[:3], ["sudo", "dnf", "install"])
        self.assertIn("-y", command)
        self.assertIn("gdb", command)
        self.assertIn("wine", command)
        self.assertNotIn("ghidra", command)
        self.assertEqual([item["tool"] for item in plan["manual"]], ["ghidra"])

    def test_install_plan_prefers_available_package_manager(self):
        plan = self.module.install_plan(
            ["gdb"],
            manager=None,
            which=self.fake_which({"apt-get", "pacman"}),
            euid=0,
        )

        self.assertEqual(plan["manager"], "apt-get")
        self.assertIn("apt-get", plan["commands"][0])

    def test_setup_runs_only_package_commands_and_never_claims_manual_success(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(list(command))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        plan = {
            "manager": "dnf",
            "commands": [["dnf", "install", "-y", "gdb"]],
            "manual": [{"tool": "ghidra", "hint": "manuell"}],
        }
        results = self.module.setup(plan, runner=runner)

        self.assertEqual(calls, [["dnf", "install", "-y", "gdb"]])
        self.assertEqual(results[0]["returncode"], 0)
        self.assertTrue(results[0]["ok"])
        self.assertIn("ghidra", plan["manual"][0]["tool"])

    def test_unknown_required_group_is_rejected_instead_of_silently_ignored(self):
        with self.assertRaises(ValueError):
            self.module.check(
                which=self.fake_which(self.all_commands()),
                required_groups=("core", "analys"),
            )

    def test_project_env_selects_the_required_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".vibe").mkdir()
            (root / ".vibe" / "project.env").write_text(
                'TYPE=rebuild\nREBUILD_REQUIRED_GROUPS="core, reverse"\n',
                encoding="utf-8",
            )
            groups = self.module.read_required_groups(root)
            result = self.module.check(
                which=self.fake_which(self.all_commands(omit=("ghidra", "analyzeHeadless"))),
                required_groups=groups,
            )

            self.assertEqual(groups, ("core", "reverse"))
            self.assertFalse(result["ok"])
            self.assertIn("ghidra", result["missing_required"])


class ToolCheckCliTest(unittest.TestCase):
    def make_tools(self, directory, commands, name="tool"):
        directory.mkdir(parents=True, exist_ok=True)
        for command in commands:
            path = directory / command
            path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def required_commands(self):
        module = load_module(ENV_SCRIPT, "vibe_rebuild_env_cli_catalog")
        commands = []
        for tool in module.TOOLS:
            if tool.group in module.DEFAULT_REQUIRED_GROUPS:
                commands.append(tool.commands[0])
        return commands

    def run_check(self, path, *arguments):
        env = os.environ.copy()
        env["PATH"] = str(path)
        return subprocess.run(
            [sys.executable, str(ENV_SCRIPT), "--check", "--json", *arguments],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )

    def test_cli_check_is_green_with_all_required_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = Path(tmp) / "bin"
            self.make_tools(command, self.required_commands())
            result = self.run_check(command)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["missing_required"], [])

    def test_cli_check_returns_error_and_names_missing_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = Path(tmp) / "bin"
            self.make_tools(command, [name for name in self.required_commands() if name != "gdb"])
            result = self.run_check(command)

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])
            self.assertIn("gdb", payload["missing_required"])

    def test_cli_setup_without_confirmation_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command = root / "bin"
            self.make_tools(command, [name for name in self.required_commands() if name not in ("gdb", "dnf")])
            log = root / "dnf.log"
            dnf = command / "dnf"
            dnf.write_text(f"#!/bin/sh\necho \"$@\" >> {log}\nexit 0\n", encoding="utf-8")
            dnf.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = str(command)
            result = subprocess.run(
                [sys.executable, str(ENV_SCRIPT), "--setup"],
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("Bestätigung", result.stdout)
            self.assertFalse(log.exists())


if __name__ == "__main__":
    unittest.main()
