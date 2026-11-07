"""Tests für sichere Prozessaufrufe und Pfadübergaben (V-003).

Die Tests belegen vier Eigenschaften:

* externe Programme werden mit Argumentlisten statt über eine Shell gestartet,
* Namen, Pfade und Agenten werden als getrennte Argumente übergeben und können
  keine Shellmetazeichen auslösen,
* projektkonfigurierte Befehle laufen nur an einer ausdrücklich benannten
  Shellgrenze,
* Leseaktionen (Projektliste, Status) führen keine Programme aus dem Projekt
  aus.

Alle Prozesse laufen mit temporärem HOME/VIBE. Es werden keine echten
Modell-, Router- oder MCP-Aufrufe ausgeführt.
"""
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
MCP = REPO / "bin" / "vibe_mcp.py"
RUNNER = REPO / "bin" / "vibe-run.sh"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support


def load_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def load_cli(vibe_root, home):
    """Lädt bin/vibe als Modul mit isoliertem VIBE und HOME."""
    old = {
        key: os.environ.get(key)
        for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME", "PATH")
    }
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    try:
        return load_module(CLI, "vibe_process_safety_under_test")
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class CliFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        self.cli = load_cli(self.root, self.home)
        self.old_env = {
            key: os.environ.get(key)
            for key in ("HOME", "VIBE", "VIBE_NO_CONTAINER", "PATH")
        }
        os.environ.update(
            {
                "HOME": str(self.home),
                "VIBE": str(self.root),
                "VIBE_NO_CONTAINER": "1",
            }
        )
        self.addCleanup(self._restore_environment)

    def _restore_environment(self):
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def make_project(self, name):
        project = self.root / name
        (project / ".vibe").mkdir(parents=True)
        (project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        self.cli._pm.clear()
        return project

    def install_fake_tmux(self):
        bin_dir = self.root / "fake-bin"
        bin_dir.mkdir()
        args_file = self.root / "tmux-args.txt"
        script = bin_dir / "tmux"
        script.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "has-session" ]; then exit 1; fi\n'
            'printf \'%s\\n\' "$@" > "$FAKE_TMUX_ARGS"\n'
            "exit 0\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
        os.environ["FAKE_TMUX_ARGS"] = str(args_file)
        return args_file


class ProcessRunnerTest(CliFixture):
    def test_argument_list_keeps_spaces_quotes_and_shell_metacharacters(self):
        marker = self.root / "darf-nicht-entstehen"
        arguments = [
            "mit leerzeichen",
            "einfaches ' und doppeltes \" Zeichen",
            f"$(touch {marker})",
            "; rm -rf /tmp/nichts",
            "|",
            "&&",
            "> umleitung",
        ]

        code, output = self.cli.run(
            [sys.executable, "-c", "import sys; print('\\n'.join(sys.argv[1:]))"]
            + arguments,
            timeout=20,
        )

        self.assertEqual(code, 0, output)
        self.assertEqual(output.splitlines(), arguments)
        self.assertFalse(marker.exists())

    def test_missing_program_is_reported_instead_of_raising(self):
        name = "vibe-v003-programm-fehlt"

        code, output = self.cli.run([name], timeout=5)

        self.assertEqual(code, 127)
        self.assertIn(name, output)

    def test_timeout_is_reported_with_a_distinct_exit_code(self):
        started = time.monotonic()

        code, output = self.cli.run(
            [sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5
        )

        self.assertEqual(code, 124)
        self.assertIn("Zeitüberschreitung", output)
        self.assertLess(time.monotonic() - started, 5)

    def test_invalid_argument_lists_are_rejected(self):
        for invalid in ([], ["/bin/true", 5], "git status"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.cli.run(invalid)


class CmdRunTest(CliFixture):
    def test_agent_is_rejected_before_tmux_when_it_contains_shell_characters(self):
        args_file = self.install_fake_tmux()
        marker = self.root / "agent-injection"
        malicious = f'agent"; touch {marker}; echo "'

        with self.assertRaises(SystemExit) as caught:
            self.cli.cmd_run("proj", malicious)

        self.assertIn("Agentenname", str(caught.exception.code))
        self.assertFalse(marker.exists())
        self.assertFalse(args_file.exists())

    def test_path_and_agent_are_separate_arguments_not_part_of_the_shell_script(self):
        args_file = self.install_fake_tmux()
        weird = self.root / "proj mit 'Zitat' $(touch${IFS}$HOME${IFS}pwned)"
        (weird / ".vibe").mkdir(parents=True)
        (weird / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        self.cli._pm.clear()

        with contextlib.redirect_stdout(io.StringIO()):
            self.cli.cmd_run(weird.name, "agent-ok")

        lines = args_file.read_text(encoding="utf-8").splitlines()
        self.assertIn(weird.name, lines)
        self.assertIn(str(weird), lines)
        self.assertIn("agent-ok", lines)
        script = lines[lines.index("-lc") + 1]
        self.assertNotIn(str(weird), script)
        self.assertNotIn("agent-ok", script)
        self.assertFalse((self.home / "pwned").exists())

    def test_invalid_project_name_is_rejected(self):
        with self.assertRaises(SystemExit):
            self.cli.cmd_run("../ausserhalb", "agent-ok")


class CmdNewTest(CliFixture):
    def setUp(self):
        super().setUp()
        android = self.root / "_toolchain" / "templates" / "android"
        (android / ".vibe").mkdir(parents=True)
        (android / ".vibe" / "project.env").write_text(
            "TYPE=android\n", encoding="utf-8"
        )

    def install_fake_android(self):
        bin_dir = self.root / "fake-android-bin"
        bin_dir.mkdir()
        args_file = self.root / "android-args.txt"
        script = bin_dir / "android"
        script.write_text(
            "#!/bin/sh\n"
            'printf \'%s\\n\' "$@" > "$FAKE_ANDROID_ARGS"\n'
            'for arg in "$@"; do\n'
            '  case "$arg" in --output=*) mkdir -p "${arg#--output=}";; esac\n'
            "done\n"
            "exit 0\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
        os.environ["FAKE_ANDROID_ARGS"] = str(args_file)
        return args_file

    def test_template_argument_cannot_start_a_second_shell_command(self):
        args_file = self.install_fake_android()
        marker = self.root / "vorlagen-injection"
        template = f"compose; touch {marker}"

        with contextlib.redirect_stdout(io.StringIO()):
            self.cli.cmd_new("sicheres-projekt", "android", template)

        arguments = args_file.read_text(encoding="utf-8").splitlines()
        self.assertIn(template, arguments)
        self.assertNotIn(";", arguments)
        self.assertFalse(marker.exists())

    def test_invalid_project_name_creates_nothing(self):
        with self.assertRaises(SystemExit) as caught:
            self.cli.cmd_new("../ausserhalb", "generic")

        self.assertIn("Name", str(caught.exception.code))
        self.assertFalse((self.root / "ausserhalb").exists())


class CommandBoundaryTest(CliFixture):
    def test_verify_uses_one_explicit_shell_boundary(self):
        (self.project / ".vibe" / "project.env").write_text(
            'TYPE=generic\nVERIFY_QUICK="printf ok"\n', encoding="utf-8"
        )

        self.assertEqual(self.cli.verify_command("proj", "quick"), "printf ok")
        argv = self.cli.verify_argv("proj", "quick")

        self.assertEqual(argv[:2], ["bash", "-lc"])
        self.assertIn("printf ok", argv[2])
        self.assertEqual(len(argv), 3)
        self.assertIsNone(self.cli.verify_argv("proj", "full"))

    def test_android_verify_path_is_quoted_for_the_shell(self):
        toolchain_verify = self.root / "_toolchain" / "verify"
        toolchain_verify.mkdir(parents=True)
        (toolchain_verify / "verify.sh").write_text("exit 0\n", encoding="utf-8")
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=android\n", encoding="utf-8"
        )

        command = self.cli.verify_command("proj", "quick")

        self.assertIn(shlex.quote(str(self.project)), command)
        self.assertIn("verify.sh", command)

    def test_emulator_action_rejects_shell_characters(self):
        marker = self.root / "emu-injection"

        with self.assertRaises(SystemExit) as caught:
            self.cli.cmd_emu(f"start; touch {marker}")

        self.assertIn("emulator", str(caught.exception.code).lower())
        self.assertFalse(marker.exists())


class ReadActionTest(CliFixture):
    def test_read_actions_do_not_execute_project_programs(self):
        project = self.root / "leseprobe"
        (project / ".vibe").mkdir(parents=True)
        fs_marker = self.root / "fsmonitor-gelaufen"
        verify_marker = self.root / "verify-gelaufen"
        emu_marker = self.root / "emulator-gelaufen"
        (project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n"
            f'VERIFY_QUICK="touch {verify_marker}"\n'
            f'VERIFY_FULL="touch {verify_marker}"\n',
            encoding="utf-8",
        )
        scripts = project / "scripts"
        scripts.mkdir()
        emulator = scripts / "emulator-start.sh"
        emulator.write_text(
            "#!/bin/sh\ntouch " + shlex.quote(str(emu_marker)) + "\n",
            encoding="utf-8",
        )
        emulator.chmod(0o755)
        hook = project / "fsmonitor.sh"
        hook.write_text(
            "#!/bin/sh\necho x >> " + shlex.quote(str(fs_marker)) + "\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)
        subprocess.run(["git", "init", "-q"], cwd=project, check=True)
        subprocess.run(
            ["git", "config", "core.fsmonitor", str(hook)],
            cwd=project,
            check=True,
        )
        (project / "datei.txt").write_text("x\n", encoding="utf-8")
        self.cli._pm.clear()

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.cli.cmd_list()
            self.cli.cmd_status("leseprobe")

        self.assertIn("leseprobe", output.getvalue())
        self.assertFalse(fs_marker.exists(), "git fsmonitor wurde ausgeführt")
        self.assertFalse(verify_marker.exists(), "VERIFY_* wurde ausgeführt")
        self.assertFalse(emu_marker.exists(), "Emulator-Skript wurde ausgeführt")


class McpProcessTest(CliFixture):
    def setUp(self):
        super().setUp()
        old_vibe = sys.modules.get("vibe")
        sys.modules["vibe"] = self.cli
        self.addCleanup(self._restore_vibe_module, old_vibe)
        self.mcp = load_module(MCP, "vibe_mcp_process_safety_under_test")

    @staticmethod
    def _restore_vibe_module(old_vibe):
        if old_vibe is None:
            sys.modules.pop("vibe", None)
        else:
            sys.modules["vibe"] = old_vibe

    def write_server(self, directory, body):
        directory.mkdir(parents=True, exist_ok=True)
        server = directory / "fake mcp 'server'.py"
        server.write_text(body, encoding="utf-8")
        return server

    def test_local_server_gets_an_argument_list_with_spaces_and_quotes(self):
        marker = self.root / "mcp-injection"
        log = self.root / "mcp-args.json"
        server = self.write_server(
            self.root / "server mit 'zeichen'",
            "import json, os, sys\n"
            'open(os.environ["FAKE_MCP_LOG"], "w", encoding="utf-8").write(\n'
            "    json.dumps(sys.argv))\n"
            "for line in sys.stdin:\n"
            "    message = json.loads(line)\n"
            '    if message.get("id") == 1:\n'
            "        print(json.dumps({\"jsonrpc\": \"2.0\", \"id\": 1, \"result\": "
            "{\"protocolVersion\": \"2025-03-26\", "
            "\"serverInfo\": {\"name\": \"fake\"}}}), flush=True)\n"
            '    elif message.get("id") == 2:\n'
            "        print(json.dumps({\"jsonrpc\": \"2.0\", \"id\": 2, "
            "\"result\": {\"tools\": [{\"name\": \"ping\"}]}}), flush=True)\n",
        )
        command = [
            sys.executable,
            str(server),
            "argument mit leerzeichen",
            f"$(touch {marker})",
        ]
        entry = {
            "type": "local",
            "command": command,
            "environment": {"FAKE_MCP_LOG": str(log)},
            "timeout": 10000,
        }

        result = self.mcp.test_local(entry, str(self.root))

        self.assertTrue(result["ok"], result)
        # sys.argv enthält den Programmnamen als erstes Element, nicht den Interpreter.
        self.assertEqual(json.loads(log.read_text(encoding="utf-8")), command[1:])
        self.assertFalse(marker.exists())

    def test_missing_program_is_reported(self):
        entry = {
            "type": "local",
            "command": ["vibe-v003-mcp-programm-fehlt"],
            "timeout": 5000,
        }

        result = self.mcp.test_local(entry, str(self.root))

        self.assertFalse(result["ok"])
        self.assertIn("Programm nicht gefunden", result["error"])

    def test_invalid_working_directory_is_reported(self):
        entry = {
            "type": "local",
            "command": ["/bin/true"],
            "cwd": "gibt-es-nicht-v003",
            "timeout": 5000,
        }

        result = self.mcp.test_local(entry, str(self.root))

        self.assertFalse(result["ok"])
        self.assertIn("Arbeitsordner", result["error"])

    def test_unresponsive_server_hits_the_timeout(self):
        entry = {
            "type": "local",
            "command": [sys.executable, "-c", "import time; time.sleep(30)"],
            "timeout": 5000,
        }

        result = self.mcp.test_local(entry, str(self.root))

        self.assertFalse(result["ok"])
        self.assertIn("Keine Antwort auf 'initialize'", result["error"])
        self.assertIn("5 s", result["error"])


class RunnerValidationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nVERIFY_FULL=true\nMAX_PACKAGES=1\n", encoding="utf-8"
        )
        self.vibe_root = self.root / "vibe"
        support.install_runner(self.vibe_root / "_toolchain")
        verify = self.vibe_root / "_toolchain" / "verify"
        verify.mkdir(parents=True)
        (verify / "next_item.py").write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
        (verify / "ok.txt").write_text("ok\n", encoding="utf-8")
        digest = hashlib.sha256((verify / "ok.txt").read_bytes()).hexdigest()
        home = self.root / "home"
        (home / ".config").mkdir(parents=True)
        (home / ".config" / "schreibfuchs-verify.sha").write_text(
            f"{digest}  ok.txt\n", encoding="utf-8"
        )
        self.env = os.environ.copy()
        self.env.update(
            {
                "VIBE": str(self.vibe_root),
                "HOME": str(home),
                "VIBE_NO_CONTAINER": "1",
            }
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_runner_rejects_an_agent_name_with_shell_characters(self):
        marker = self.root / "runner-injection"

        result = subprocess.run(
            ["bash", str(RUNNER), str(self.project), f"agent; touch {marker}"],
            capture_output=True,
            text=True,
            env=self.env,
            timeout=60,
        )

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("Agentenname", result.stdout + result.stderr)
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
