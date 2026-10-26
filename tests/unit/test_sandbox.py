"""Tests für die optionale Shell-Sandbox je Projekt (F7).

Die Tests prüfen die Projektkonfiguration, die effektiven Schreibverzeichnisse,
die bubblewrap-Argumente und das tatsächliche Verhalten einer laufenden
Sandbox. Der letzte Test startet den echten Paket-Läufer mit einem
Ersatz-opencode und belegt, dass ein sandboxed Lauf ``--standalone`` verwendet
und außerhalb der erlaubten Verzeichnisse nicht schreiben kann.
"""
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
SANDBOX = REPO / "bin" / "vibe_sandbox.py"
WEB = REPO / "bin" / "vibe-web.py"
RUNNER = REPO / "bin" / "vibe-run.sh"
TEMPLATES = REPO / "templates"

TOOL_DEFAULTS = {
    "generic": ["git", "python3"],
    "web": ["git", "node", "npm"],
    "android": ["git", "java", "android", "adb"],
    "docker": ["git", "docker"],
    "openwrt": ["git", "make", "gcc"],
}


def load_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def load_cli(vibe_root):
    """Lädt bin/vibe mit isoliertem VIBE und HOME als Modul."""
    old = {key: os.environ.get(key) for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(Path(vibe_root) / "home")
    try:
        return load_module(CLI, "vibe_sandbox_cli_under_test")
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def read_env_file(path):
    data = {}
    if not Path(path).exists():
        return data
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


class SandboxFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        self.env_file = self.project / ".vibe" / "project.env"
        self.env_file.write_text("TYPE=generic\n", encoding="utf-8")
        self.cli = load_cli(self.root)
        self.sandbox = load_module(SANDBOX, "vibe_sandbox_under_test")
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.root / "home")
        self.home = Path(os.environ["HOME"])
        self.home.mkdir(parents=True, exist_ok=True)
        self.addCleanup(self._restore_home, old_home)

    def _restore_home(self, old_home):
        if old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = old_home
        self.tmp.cleanup()

    def _restore_env(self, key, value):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    def write_env(self, extra=""):
        self.env_file.write_text("TYPE=generic\n" + extra, encoding="utf-8")


class SandboxConfigTest(SandboxFixture):
    def test_existing_project_without_sandbox_setting_stays_off(self):
        status = self.sandbox.status(self.project)

        self.assertFalse(status["enabled"])
        self.assertEqual(status["tools"], [])
        self.assertEqual(
            status["write_dirs"],
            ["/tmp/opencode", os.path.realpath(self.project)],
        )
        self.assertIsNone(status["error"])

    def test_templates_preselect_sandbox_and_build_tools(self):
        for project_type, expected in TOOL_DEFAULTS.items():
            with self.subTest(type=project_type):
                path = TEMPLATES / project_type / ".vibe" / "project.env"
                values = read_env_file(path)
                self.assertEqual(values.get("SANDBOX"), "on")
                tools = values.get("SANDBOX_TOOLS", "").split()
                for tool in expected:
                    self.assertIn(tool, tools)

    def test_cli_on_selects_the_default_tools_of_the_project_type(self):
        status = self.cli.sandbox_set("proj", True)

        values = read_env_file(self.env_file)
        self.assertEqual(values["SANDBOX"], "on")
        self.assertEqual(values["SANDBOX_TOOLS"], "git python3")
        self.assertTrue(status["enabled"])
        self.assertEqual(status["tools"], ["git", "python3"])

    def test_cli_off_keeps_other_lines_and_tools(self):
        self.env_file.write_text(
            "# eigene Notiz\nTYPE=web\nSANDBOX=on\nSANDBOX_TOOLS=\"npm git\"\nAGENT=mein-agent\n",
            encoding="utf-8",
        )

        status = self.cli.sandbox_set("proj", False)

        text = self.env_file.read_text(encoding="utf-8")
        self.assertIn("# eigene Notiz", text)
        self.assertIn("TYPE=web", text)
        self.assertIn("AGENT=mein-agent", text)
        self.assertIn('SANDBOX_TOOLS="npm git"', text)
        values = read_env_file(self.env_file)
        self.assertEqual(values["SANDBOX"], "off")
        self.assertFalse(status["enabled"])

    def test_cli_off_replaces_the_last_of_duplicate_keys(self):
        self.env_file.write_text(
            "TYPE=generic\nSANDBOX=on\nSANDBOX=on\n", encoding="utf-8"
        )

        status = self.cli.sandbox_set("proj", False)

        values = read_env_file(self.env_file)
        self.assertEqual(values["SANDBOX"], "off")
        self.assertFalse(status["enabled"])
        self.assertEqual(
            self.env_file.read_text(encoding="utf-8").count("SANDBOX=on"), 1
        )

    def test_cli_tools_are_normalized_and_persisted(self):
        status = self.cli.sandbox_tools("proj", "  npm, python3   git npm ")

        values = read_env_file(self.env_file)
        self.assertEqual(values["SANDBOX_TOOLS"], "npm python3 git")
        self.assertEqual(status["tools"], ["npm", "python3", "git"])

    def test_cli_tools_reject_control_characters_without_changing_the_file(self):
        before = self.env_file.read_text(encoding="utf-8")

        for invalid in ("git\nrm", "git\x00rm", "git;rm", "git/rm"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.cli.sandbox_tools("proj", invalid)
                self.assertEqual(
                    self.env_file.read_text(encoding="utf-8"), before
                )

    def test_effective_write_dirs_contain_project_permissions_and_tool_caches(self):
        self.write_env('SANDBOX=on\nSANDBOX_TOOLS="npm python3 gradle"\n')
        extra = "/tmp/opencode/f7-extra"
        self.cli.write_dirs_save("proj", [str(self.project), extra])

        status = self.sandbox.status(self.project)

        self.assertTrue(status["enabled"])
        self.assertEqual(status["tools"], ["npm", "python3", "gradle"])
        for expected in (
            os.path.realpath(self.project),
            os.path.realpath(extra),
            os.path.realpath(self.home / ".npm"),
            os.path.realpath(self.home / ".cache" / "pip"),
            os.path.realpath(self.home / ".gradle"),
        ):
            self.assertIn(expected, status["write_dirs"])
        self.assertTrue(
            status["state_dir"].startswith("/tmp/opencode/vibe-sandbox/")
        )

    def test_gradle_user_home_is_writable_when_configured(self):
        self.write_env('SANDBOX=on\nSANDBOX_TOOLS="gradle"\n')
        custom = self.home / "gradle-custom"
        custom.mkdir(parents=True)
        old = os.environ.get("GRADLE_USER_HOME")
        os.environ["GRADLE_USER_HOME"] = str(custom)
        self.addCleanup(self._restore_env, "GRADLE_USER_HOME", old)

        status = self.sandbox.status(self.project)

        self.assertIn(os.path.realpath(custom), status["write_dirs"])

    def test_corrupt_permissions_file_is_reported_and_blocks_the_check(self):
        self.write_env("SANDBOX=on\n")
        (self.project / ".vibe" / "permissions.json").write_text(
            "{kein json", encoding="utf-8"
        )

        status = self.sandbox.status(self.project)
        checked = self.sandbox.check(self.project)

        self.assertTrue(status["enabled"])
        self.assertIn("Schreibrechte nicht lesbar", status["error"])
        self.assertFalse(checked["ok"])
        self.assertIn("Schreibrechte nicht lesbar", checked["message"])


class SandboxCommandTest(SandboxFixture):
    def test_bwrap_arguments_bind_root_read_only_and_write_dirs(self):
        self.write_env('SANDBOX=on\nSANDBOX_TOOLS="git"\n')
        self.cli.write_dirs_save("proj", [str(self.project)])

        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap="/usr/bin/bwrap"
        )

        self.assertEqual(argv[0], "/usr/bin/bwrap")
        self.assertEqual(argv[1:4], ["--ro-bind", "/", "/"])
        self.assertIn("--tmpfs", argv)
        self.assertIn("--unshare-pid", argv)
        self.assertIn("--die-with-parent", argv)
        project = os.path.realpath(self.project)
        self.assertEqual(
            argv[argv.index("--bind", argv.index("--tmpfs") + 1):][:2],
            ["--bind", project],
        )
        for expected in (
            "/tmp/opencode",
            os.path.realpath(self.home / ".npm"),
        ):
            self.assertIn("--bind", argv)
            position = argv.index("--bind", argv.index(expected) - 1)
            self.assertEqual(argv[position:position + 2], ["--bind", expected])
        self.assertIn("XDG_DATA_HOME", argv)
        self.assertIn("XDG_CACHE_HOME", argv)
        self.assertIn("TMPDIR", argv)
        self.assertIn(("--remount-ro", "/tmp"), list(zip(argv, argv[1:])))
        vibe_dir = os.path.join(project, ".vibe")
        self.assertIn(("--ro-bind", vibe_dir), list(zip(argv, argv[1:])))
        self.assertEqual(argv[-2:], ["--", "/bin/true"])

    def test_explicit_tmp_write_dir_is_not_remounted_read_only(self):
        self.write_env('SANDBOX=on\nSANDBOX_TOOLS="git"\n')
        (self.project / ".vibe" / "permissions.json").write_text(
            json.dumps({"write_dirs": [str(self.project), "/tmp"]}),
            encoding="utf-8",
        )

        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap="/usr/bin/bwrap"
        )

        pairs = list(zip(argv, argv[1:]))
        self.assertIn(("--bind", "/tmp"), pairs)
        self.assertNotIn(("--remount-ro", "/tmp"), pairs)

    def test_enabled_flag_reports_documented_active_values(self):
        for value in ("on", "ON", "1", "true", "yes"):
            with self.subTest(value=value):
                self.write_env(f"SANDBOX={value}\n")
                result = subprocess.run(
                    [sys.executable, str(SANDBOX), str(self.project), "--enabled"],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, value)
                self.assertEqual(result.stdout.strip(), "on")
        for value in ("off", "0", "no", "false", ""):
            with self.subTest(value=value):
                self.write_env(f"SANDBOX={value}\n")
                result = subprocess.run(
                    [sys.executable, str(SANDBOX), str(self.project), "--enabled"],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 1, value)
                self.assertEqual(result.stdout.strip(), "off")

    def test_cargo_file_cache_does_not_break_the_sandbox(self):
        self.write_env('SANDBOX=on\nSANDBOX_TOOLS="cargo"\n')
        cargo = self.home / ".cargo"
        cargo.mkdir(parents=True, exist_ok=True)
        (cargo / ".package-cache").write_text("", encoding="utf-8")
        toolbin = self.root / "bin"
        toolbin.mkdir()
        (toolbin / "cargo").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (toolbin / "cargo").chmod(0o755)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(toolbin) + os.pathsep + old_path
        self.addCleanup(self._restore_env, "PATH", old_path)

        checked = self.sandbox.check(self.project)
        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap="/usr/bin/bwrap"
        )

        self.assertTrue(checked["ok"], checked["message"])
        self.assertIn(("--bind", str(cargo)), list(zip(argv, argv[1:])))

    def test_cli_and_sandbox_share_the_write_dir_normalization(self):
        cases = [
            [str(self.project) + "/"],
            ["~"],
            ["~/.npm", "~/.npm", str(self.project)],
            [str(self.home / "link-zum-projekt")],
            [str(self.project)],
        ]
        (self.home / "link-zum-projekt").symlink_to(self.project)
        for write_dirs in cases:
            with self.subTest(write_dirs=write_dirs):
                (self.project / ".vibe" / "permissions.json").write_text(
                    json.dumps({"write_dirs": write_dirs}), encoding="utf-8"
                )
                self.assertEqual(
                    self.cli.write_dirs("proj"),
                    self.sandbox.project_write_dirs(self.project),
                )
        for broken in ({"write_dirs": "keine-liste"}, {"write_dirs": ["relativ"]}):
            with self.subTest(broken=broken):
                (self.project / ".vibe" / "permissions.json").write_text(
                    json.dumps(broken), encoding="utf-8"
                )
                with self.assertRaises(ValueError):
                    self.cli.write_dirs("proj")
                with self.assertRaises(ValueError):
                    self.sandbox.project_write_dirs(self.project)

    def test_android_tools_bind_kvm_and_dri_devices(self):
        self.write_env('SANDBOX=on\nSANDBOX_TOOLS="git android adb"\n')

        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap="/usr/bin/bwrap"
        )

        pairs = list(zip(argv, argv[1:]))
        for device in ("/dev/kvm", "/dev/dri"):
            with self.subTest(device=device):
                self.assertIn(("--dev-bind-try", device), pairs)
        self.assertIn(("--dev-bind-try", "/dev/kvm"), pairs)
        self.assertEqual(pairs.count(("--dev-bind-try", "/dev/kvm")), 1)

    def test_missing_bwrap_fails_closed_without_running_the_command(self):
        self.write_env("SANDBOX=on\nSANDBOX_TOOLS=\"git\"\n")
        marker = self.root / "darf-nicht-entstehen"
        env = os.environ.copy()
        env["VIBE_BWRAP"] = str(self.root / "fehlt-bwrap")
        env["HOME"] = str(self.home)

        result = subprocess.run(
            [
                sys.executable,
                str(SANDBOX),
                str(self.project),
                "--",
                "/bin/sh",
                "-c",
                f"touch {shlex.quote(str(marker))}",
            ],
            capture_output=True,
            text=True,
            env=env,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bubblewrap", result.stderr.lower())
        self.assertFalse(marker.exists())

    def test_disabled_sandbox_executes_the_command_directly(self):
        marker = self.root / "direkt-geschrieben"
        result = subprocess.run(
            [
                sys.executable,
                str(SANDBOX),
                str(self.project),
                "--",
                "/bin/sh",
                "-c",
                f"echo direkt > {shlex.quote(str(marker))}",
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(marker.read_text(encoding="utf-8"), "direkt\n")

    def test_check_reports_a_missing_build_tool(self):
        self.write_env(
            "SANDBOX=on\nSANDBOX_TOOLS=\"definitely-missing-f7-tool\"\n"
        )

        result = self.sandbox.check(self.project)

        self.assertFalse(result["ok"])
        self.assertIn("definitely-missing-f7-tool", result["message"])

    def test_check_passes_with_bwrap_and_available_tools(self):
        self.write_env("SANDBOX=on\nSANDBOX_TOOLS=\"git\"\n")

        result = self.sandbox.check(self.project)

        self.assertTrue(result["ok"], result["message"])
        self.assertIn("bereit", result["message"].lower())

    def test_real_sandbox_allows_write_dirs_and_denies_unlisted_paths(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.write_env("SANDBOX=on\nSANDBOX_TOOLS=\"git\"\n")
        allowed = Path("/tmp/opencode") / f"f7-test-{os.getpid()}-{time.time_ns()}"
        allowed.mkdir(parents=True)
        self.addCleanup(lambda: shutil.rmtree(allowed, ignore_errors=True))
        self.cli.write_dirs_save("proj", [str(self.project), str(allowed)])
        escape = Path("/var/tmp") / (
            "f7-sandbox-escape-" + str(os.getpid()) + "-" + str(time.time_ns())
        )
        self.addCleanup(lambda: escape.unlink() if escape.exists() else None)
        home_escape = Path(os.path.expanduser("~")) / (
            "f7-home-escape-" + str(os.getpid()) + "-" + str(time.time_ns())
        )
        self.addCleanup(lambda: home_escape.unlink() if home_escape.exists() else None)

        script = (
            f"echo ok > {shlex.quote(str(self.project / 'inside.txt'))} && echo PROJEKT_OK; "
            f"echo ok > {shlex.quote(str(allowed / 'aussen.txt'))} && echo ERLAUBT_OK; "
            f"if touch {shlex.quote(str(escape))} 2>/dev/null; then echo ESCAPED; else echo DENIED; fi; "
            f"if touch {shlex.quote(str(home_escape))} 2>/dev/null; then echo HOME_OPEN; else echo HOME_DENIED; fi; "
            "cat /etc/hostname >/dev/null && echo READ_OK"
        )
        result = subprocess.run(
            [
                sys.executable,
                str(SANDBOX),
                str(self.project),
                "--",
                "/bin/sh",
                "-c",
                script,
            ],
            capture_output=True,
            text=True,
            env=dict(os.environ, HOME=os.path.expanduser("~")),
            timeout=60,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PROJEKT_OK", result.stdout)
        self.assertIn("ERLAUBT_OK", result.stdout)
        self.assertIn("DENIED", result.stdout)
        self.assertIn("HOME_DENIED", result.stdout)
        self.assertIn("READ_OK", result.stdout)
        self.assertTrue((self.project / "inside.txt").exists())
        self.assertTrue((allowed / "aussen.txt").exists())
        self.assertFalse(escape.exists())
        self.assertFalse(home_escape.exists())

    def run_sandboxed(self, script):
        return subprocess.run(
            [
                sys.executable,
                str(SANDBOX),
                str(self.project),
                "--",
                "/bin/sh",
                "-c",
                script,
            ],
            capture_output=True,
            text=True,
            env=dict(os.environ, HOME=os.path.expanduser("~")),
            timeout=60,
        )

    def test_real_sandbox_denies_writes_to_the_unlisted_tmp(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.write_env('SANDBOX=on\nSANDBOX_TOOLS="git"\n')
        self.cli.write_dirs_save("proj", [str(self.project)])
        escape = Path("/tmp") / (
            "f7-unlisted-" + str(os.getpid()) + "-" + str(time.time_ns())
        )
        self.addCleanup(lambda: escape.unlink() if escape.exists() else None)

        result = self.run_sandboxed(
            f"if touch {shlex.quote(str(escape))} 2>/dev/null; "
            "then echo TMP_OPEN; else echo TMP_DENIED; fi; "
            'echo ok > "$TMPDIR/tempfile" && echo TMPDIR_OK'
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("TMP_DENIED", result.stdout)
        self.assertIn("TMPDIR_OK", result.stdout)
        self.assertFalse(escape.exists())

    def test_real_sandbox_keeps_the_project_configuration_read_only(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.write_env('SANDBOX=on\nSANDBOX_TOOLS="git"\n')
        self.cli.write_dirs_save("proj", [str(self.project)])
        before = self.env_file.read_text(encoding="utf-8")

        result = self.run_sandboxed(
            "if echo SANDBOX=off >> .vibe/project.env 2>/dev/null; "
            "then echo ENV_OPEN; else echo ENV_DENIED; fi; "
            "if printf '{}' > .vibe/extra.json 2>/dev/null; "
            "then echo VIBE_OPEN; else echo VIBE_DENIED; fi; "
            "if echo ok > normale-datei.txt 2>/dev/null; "
            "then echo PROJEKT_OK; else echo PROJEKT_DENIED; fi"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ENV_DENIED", result.stdout)
        self.assertIn("VIBE_DENIED", result.stdout)
        self.assertIn("PROJEKT_OK", result.stdout)
        self.assertEqual(self.env_file.read_text(encoding="utf-8"), before)
        self.assertFalse((self.project / ".vibe" / "extra.json").exists())


class SandboxRunnerTest(SandboxFixture):
    """Der echte Paket-Läufer muss den Agenten in der Sandbox starten."""

    def test_runner_uses_standalone_sandbox_and_blocks_home_writes(self):
        env, args_file, escape = self.prepare_runner("on")

        result = self.run_runner(env)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        recorded = args_file.read_text(encoding="utf-8")
        self.assertIn("run --standalone", recorded)
        self.assertNotIn("--server", recorded)
        self.assertIn("DENIED", recorded)
        self.assertFalse(escape.exists())

    def test_runner_sandboxes_every_documented_active_value(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        for value in ("on", "TRUE", "yes", "1"):
            with self.subTest(value=value):
                env, args_file, escape = self.prepare_runner(value)

                result = self.run_runner(env)

                self.assertEqual(
                    result.returncode, 0, value + ": " + result.stdout + result.stderr
                )
                recorded = args_file.read_text(encoding="utf-8")
                self.assertIn("run --standalone", recorded, value)
                self.assertIn("DENIED", recorded, value)
                self.assertFalse(escape.exists(), value)

    def test_runner_without_sandbox_module_fails_closed_for_active_setting(self):
        env, args_file, escape = self.prepare_runner("on")
        (self.root / "_toolchain" / "bin" / "vibe_sandbox.py").unlink()

        result = self.run_runner(env)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("vibe_sandbox.py", result.stdout + result.stderr)
        self.assertFalse(args_file.exists())
        self.assertFalse(escape.exists())

    def test_runner_fails_closed_when_sandbox_module_is_broken(self):
        env, args_file, escape = self.prepare_runner("on")
        (self.root / "_toolchain" / "bin" / "vibe_sandbox.py").write_text(
            "def kaputt(:\n", encoding="utf-8"
        )

        result = self.run_runner(env)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Sandbox", result.stdout + result.stderr)
        self.assertFalse(args_file.exists())
        self.assertFalse(escape.exists())

    def prepare_runner(self, sandbox_value):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        toolbin = Path("/tmp/opencode") / (
            "f7-runner-" + str(os.getpid()) + "-" + str(time.time_ns())
        )
        toolbin.mkdir(parents=True)
        self.addCleanup(lambda: shutil.rmtree(toolbin, ignore_errors=True))

        args_file = toolbin / "args.txt"
        escape = Path("/var/tmp") / (
            "f7-runner-escape-" + str(os.getpid()) + "-" + str(time.time_ns())
        )
        self.addCleanup(lambda: escape.unlink() if escape.exists() else None)
        fake_opencode = toolbin / "opencode"
        fake_opencode.write_text(
            "#!/bin/sh\n"
            'printf "%s\\n" "$*" > "$FAKE_ARGS"\n'
            'if touch "$FAKE_ESCAPE" 2>/dev/null; then\n'
            '  echo ESCAPED >> "$FAKE_ARGS"\n'
            "else\n"
            '  echo DENIED >> "$FAKE_ARGS"\n'
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        fake_opencode.chmod(0o755)

        toolchain_bin = self.root / "_toolchain" / "bin"
        toolchain_bin.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SANDBOX, toolchain_bin / "vibe_sandbox.py")

        verify = self.root / "_toolchain" / "verify"
        verify.mkdir(parents=True, exist_ok=True)
        (verify / "ok.txt").write_text("ok\n", encoding="utf-8")
        (verify / "next_item.py").write_text(
            "import sys\n"
            "from pathlib import Path\n"
            "project = Path(sys.argv[1])\n"
            "counter = project / '.fake-count-%s'\n"
            "n = int(counter.read_text()) if counter.exists() else 0\n"
            "if n >= 1:\n"
            "    sys.exit(1)\n"
            "counter.write_text('1')\n"
            "Path('/tmp/next_id').write_text('T-1\\n')\n"
            "Path('/tmp/next_block').write_text('- [ ] T-1 Test\\n')\n"
            % sandbox_value,
            encoding="utf-8",
        )
        digest = hashlib.sha256((verify / "ok.txt").read_bytes()).hexdigest()
        (self.home / ".config").mkdir(parents=True, exist_ok=True)
        (self.home / ".config" / "schreibfuchs-verify.sha").write_text(
            f"{digest}  ok.txt\n", encoding="utf-8"
        )
        self.env_file.write_text(
            "TYPE=generic\n"
            "AGENT=tester\n"
            "VERIFY_QUICK=true\n"
            "VERIFY_FULL=true\n"
            "MAX_PACKAGES=1\n"
            f"SANDBOX={sandbox_value}\n"
            'SANDBOX_TOOLS="git"\n',
            encoding="utf-8",
        )

        env = os.environ.copy()
        env.update(
            {
                "VIBE": str(self.root),
                "VIBE_LOGNAME": "proj",
                "HOME": str(self.home),
                "PATH": str(toolbin) + os.pathsep + env.get("PATH", ""),
                "FAKE_ARGS": str(args_file),
                "FAKE_ESCAPE": str(escape),
                "VIBE_NO_CONTAINER": "1",
            }
        )
        return env, args_file, escape

    def run_runner(self, env):
        return subprocess.run(
            ["bash", str(RUNNER), str(self.project), "tester"],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class SandboxApiTest(unittest.TestCase):
    """Dashboard-API: Sandbox-Zustand lesen und schalten, Tokenpflicht."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True
        )
        cls.port = free_port()
        env = os.environ.copy()
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.root / "home"),
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

    def additional_request(self, path, payload=None, token=True):
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
            with urllib.request.urlopen(req, timeout=60) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            code = error.code
            error.close()
            return code, body

    def env_values(self):
        return read_env_file(self.project / ".vibe" / "project.env")

    def setUp(self):
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )

    def test_detail_exposes_disabled_sandbox_for_existing_project(self):
        status, body = self.additional_request("/api/project?name=proj")

        self.assertEqual(status, 200, body)
        sandbox = json.loads(body)["sandbox"]
        self.assertFalse(sandbox["enabled"])
        self.assertEqual(sandbox["tools"], [])

    def test_api_switches_sandbox_sets_tools_and_runs_the_check(self):
        status, body = self.additional_request(
            "/api/sandbox", {"name": "proj", "action": "on"}
        )
        self.assertEqual(status, 200, body)
        payload = json.loads(body)
        self.assertTrue(payload["sandbox"]["enabled"])
        self.assertEqual(
            payload["sandbox"]["tools"], ["git", "python3"]
        )
        self.assertEqual(self.env_values()["SANDBOX"], "on")

        status, body = self.additional_request(
            "/api/sandbox",
            {"name": "proj", "action": "tools", "tools": "git, python3"},
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(
            json.loads(body)["sandbox"]["tools"], ["git", "python3"]
        )
        self.assertEqual(self.env_values()["SANDBOX_TOOLS"], "git python3")

        status, body = self.additional_request(
            "/api/sandbox", {"name": "proj", "action": "check"}
        )
        self.assertEqual(status, 200, body)
        checked = json.loads(body)["check"]
        self.assertTrue(checked["ok"], checked["message"])

        status, body = self.additional_request(
            "/api/sandbox", {"name": "proj", "action": "off"}
        )
        self.assertEqual(status, 200, body)
        self.assertFalse(json.loads(body)["sandbox"]["enabled"])
        self.assertEqual(self.env_values()["SANDBOX"], "off")

    def test_api_rejects_unknown_action_and_invalid_tool_list(self):
        status, body = self.additional_request(
            "/api/sandbox", {"name": "proj", "action": "foo"}
        )
        self.assertEqual(status, 400, body)
        self.assertIn("Unbekannte Aktion", body)

        status, body = self.additional_request(
            "/api/sandbox",
            {"name": "proj", "action": "tools", "tools": "git;rm"},
        )
        self.assertEqual(status, 400, body)
        self.assertIn("Werkzeugname", body)

    def test_api_requires_token_for_sandbox_changes(self):
        before = self.env_values()

        status, body = self.additional_request(
            "/api/sandbox", {"name": "proj", "action": "on"}, token=False
        )

        self.assertEqual(status, 403, body)
        self.assertEqual(self.env_values(), before)


if __name__ == "__main__":
    unittest.main()
