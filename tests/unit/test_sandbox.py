"""Sandbox: Anmeldedaten, bwrap-Argumente, Shared Memory, Zustandsordner und Pi-Agentenverzeichnis.

Aufruf: python3 -m unittest tests.unit.test_sandbox -v
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

# GH-89/F1: Sandbox-Zustand und Host-Ablage der opencode-Daten liegen pro
# Benutzer unter /dev/shm. Der geteilte Host-Ordner /tmp/opencode wird von
# vibe nicht mehr angelegt; /tmp/opencode bleibt nur der Pfad INNERHALB der
# Sandbox. /dev/shm ist auch in der Agenten-Sandbox beschreibbar (dort ist
# /tmp nur lesend eingebunden) und sein 1777-Sticky-Modus trennt die Nutzer.
SANDBOX_STATE_ROOT = f"/dev/shm/vibe-sandbox-{os.getuid()}"
SHORT_STATE_ROOT = f"/dev/shm/vsb-{os.getuid()}"
OPENCODE_STATE_ROOT = f"/dev/shm/vibe-opencode-{os.getuid()}"

from tests.unit import env_support

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support

TOOL_DEFAULTS = {
    "generic": ["git", "python3"],
    "web": ["git", "node", "npm"],
    "android": ["git", "java", "android", "adb"],
    "docker": ["git", "docker"],
    "rebuild": [
        "git", "python3", "wine", "java", "ghidra", "analyzeHeadless",
        "gdb", "strace", "ltrace", "strings", "objdump", "readelf",
        "appimagetool", "linuxdeploy", "patchelf", "podman",
    ],
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
        # Die Vorgabe /tmp/opencode (F3, agentensichtbar) wird auf die
        # per-UID-Host-Ablage abgebildet; der geteilte Host-Ordner selbst
        # bleibt unangetastet.
        self.assertEqual(
            status["write_dirs"],
            [os.path.realpath(OPENCODE_STATE_ROOT), os.path.realpath(self.project)],
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
        # Zusätzliches Schreibverzeichnis unter dem Temp-Root des Tests statt
        # im geteilten Host-Ordner /tmp/opencode.
        extra = self.root / "f7-extra"
        self.cli.write_dirs_save("proj", [str(self.project), str(extra)])

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
            status["state_dir"].startswith(SANDBOX_STATE_ROOT + os.sep)
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
    def test_bwrap_arguments_bind_the_shared_git_dir_of_a_worktree(self):
        self.write_env('SANDBOX=on\nSANDBOX_TOOLS="git"\n')
        support.init_repo(self.project)
        support.commit_all(self.project)
        worktree = self.root / "worktree"
        support.git(self.project, "worktree", "add", "-q", "-b", "test-wt", str(worktree))

        argv = self.sandbox.bwrap_argv(
            worktree, ["/bin/true"], bwrap="/usr/bin/bwrap"
        )

        common = support.git(
            worktree, "rev-parse", "--path-format=absolute", "--git-common-dir"
        ).stdout.strip()
        self.assertTrue(common, "gemeinsamer Git-Ordner nicht ermittelbar")
        self.assertIn(("--bind", os.path.realpath(common)), list(zip(argv, argv[1:])))

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
        # GH-89/F1: Die opencode-Host-Ablage wird als Quelle auf den
        # Sandbox-Pfad /tmp/opencode gebunden (Quelle != Ziel). Der geteilte
        # Host-Ordner selbst wird nicht mehr angelegt oder gebunden.
        pairs = list(zip(argv, argv[1:], argv[2:]))
        opencode_backing = os.path.realpath(OPENCODE_STATE_ROOT)
        self.assertIn(("--bind", opencode_backing, "/tmp/opencode"), pairs)
        self.assertNotIn(("--bind", "/tmp/opencode", "/tmp/opencode"), pairs)
        npm = os.path.realpath(self.home / ".npm")
        self.assertIn(("--bind", npm, npm), pairs)
        self.assertIn("XDG_DATA_HOME", argv)
        self.assertIn("XDG_CACHE_HOME", argv)
        self.assertIn("TMPDIR", argv)
        self.assertIn(("--remount-ro", "/tmp"), list(zip(argv, argv[1:])))
        vibe_dir = os.path.join(project, ".vibe")
        self.assertIn(("--ro-bind", vibe_dir), list(zip(argv, argv[1:])))
        self.assertEqual(argv[-2:], ["--", "/bin/true"])

    def test_runtime_question_folder_is_writable_but_not_the_whole_runtime(self):
        """F16: Der Agent schreibt Rückfragen nur in den eigenen Unterordner."""
        self.write_env('SANDBOX=on\nSANDBOX_TOOLS="git"\n')
        runtime = self.root / "_logs"

        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap="/usr/bin/bwrap", runtime=str(runtime)
        )

        questions = str(runtime / "questions")
        pairs = list(zip(argv, argv[1:]))
        self.assertIn(("--bind", questions), pairs)
        self.assertNotIn(("--bind", str(runtime)), pairs)
        self.assertTrue(Path(questions).is_dir(), "Rückfrageordner wurde nicht angelegt")

    def test_question_binding_precedes_the_tmp_write_protection(self):
        """F16: Auch ein Laufzeitordner unter /tmp bleibt erreichbar."""
        self.write_env('SANDBOX=on\nSANDBOX_TOOLS="git"\n')
        runtime = self.root / "_logs"

        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap="/usr/bin/bwrap", runtime=str(runtime)
        )

        pairs = list(zip(argv, argv[1:]))
        binding = ("--bind", str(runtime / "questions"))
        self.assertIn(binding, pairs)
        self.assertLess(pairs.index(binding), pairs.index(("--remount-ro", "/tmp")))

    def test_without_a_runtime_no_question_folder_is_bound(self):
        self.write_env('SANDBOX=on\nSANDBOX_TOOLS="git"\n')

        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap="/usr/bin/bwrap", runtime=""
        )

        pairs = list(zip(argv, argv[1:]))
        self.assertFalse(
            [pair for pair in pairs if pair[1].endswith(os.sep + "questions")]
        )
        self.assertFalse((self.root / "_logs" / "questions").exists())

    @env_support.skip_if_sandbox_nested
    def test_real_sandbox_allows_questions_but_not_the_web_token(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.write_env('SANDBOX=on\nSANDBOX_TOOLS="git"\n')
        # Der Laufzeitordner liegt außerhalb der erlaubten Schreibverzeichnisse,
        # damit der Test wirklich die zusätzliche Bindung des Rückfrageordners
        # prüft. Das Prüfverzeichnis liegt bewusst im Repository und wird
        # danach wieder entfernt.
        runtime = Path(tempfile.mkdtemp(prefix=".f16-sandbox-", dir=str(REPO)))
        self.addCleanup(lambda: shutil.rmtree(runtime, ignore_errors=True))
        token = runtime / "web.token"
        token.write_text("GEHEIM", encoding="utf-8")
        probe = runtime / "questions" / "probe"
        script = (
            f"echo ok > {shlex.quote(str(probe))} && echo FRAGE_OK; "
            f"if echo x > {shlex.quote(str(token))} 2>/dev/null; "
            "then echo TOKEN_OPEN; else echo TOKEN_DENIED; fi"
        )

        result = subprocess.run(
            [sys.executable, str(SANDBOX), str(self.project), "--", "/bin/sh", "-c", script],
            capture_output=True,
            text=True,
            env=dict(
                os.environ,
                HOME=str(self.home),
                VIBE=str(self.root),
                VIBE_RUNTIME=str(runtime),
            ),
            timeout=60,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FRAGE_OK", result.stdout)
        self.assertIn("TOKEN_DENIED", result.stdout)
        self.assertTrue(probe.is_file())
        self.assertEqual(token.read_text(encoding="utf-8"), "GEHEIM")

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

    @env_support.skip_if_sandbox_nested
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

    @env_support.skip_if_sandbox_nested
    def test_check_passes_with_bwrap_and_available_tools(self):
        self.write_env("SANDBOX=on\nSANDBOX_TOOLS=\"git\"\n")

        result = self.sandbox.check(self.project)

        self.assertTrue(result["ok"], result["message"])
        self.assertIn("bereit", result["message"].lower())

    @env_support.skip_if_sandbox_nested
    def test_real_sandbox_allows_write_dirs_and_denies_unlisted_paths(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.write_env("SANDBOX=on\nSANDBOX_TOOLS=\"git\"\n")
        # GH-89/F1: Das erlaubte Zusatzverzeichnis liegt unter dem Temp-Root
        # des Tests; der geteilte Host-Ordner /tmp/opencode wird nicht mehr
        # beschrieben.
        allowed = self.root / f"f7-test-{os.getpid()}-{time.time_ns()}"
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

    @env_support.skip_if_sandbox_nested
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

    @env_support.skip_if_sandbox_nested
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

    @env_support.skip_if_sandbox_nested
    def test_runner_uses_standalone_sandbox_and_blocks_home_writes(self):
        env, args_file, escape = self.prepare_runner("on")

        result = self.run_runner(env)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        recorded = args_file.read_text(encoding="utf-8")
        self.assertIn("run --standalone", recorded)
        self.assertNotIn("--server", recorded)
        self.assertIn("DENIED", recorded)
        self.assertFalse(escape.exists())

    @env_support.skip_if_sandbox_nested
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
        # GH-89/F1: Der Werkzeugordner liegt unter dem Temp-Root des Tests
        # statt im geteilten Host-Ordner /tmp/opencode. Über die Schreibrechte
        # wird er source==target gebunden und ist damit auch in der Sandbox
        # sichtbar und beschreibbar.
        toolbin = self.root / (
            "f7-runner-" + str(os.getpid()) + "-" + str(time.time_ns())
        )
        toolbin.mkdir(parents=True)
        self.addCleanup(lambda: shutil.rmtree(toolbin, ignore_errors=True))
        (self.project / ".vibe" / "permissions.json").write_text(
            json.dumps({"write_dirs": [str(self.project), str(toolbin)]}),
            encoding="utf-8",
        )

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
            'exec package-agent "$@"\n',
            encoding="utf-8",
        )
        fake_opencode.chmod(0o755)
        package_agent = toolbin / "package-agent"
        package_agent.write_text(support.FAKE_OPENCODE, encoding="utf-8")
        package_agent.chmod(0o755)
        curl = toolbin / "curl"
        curl.write_text(support.FAKE_CURL, encoding="utf-8")
        curl.chmod(0o755)

        toolchain_bin = support.install_runner(self.root / "_toolchain")
        shutil.copy2(SANDBOX, toolchain_bin / "vibe_sandbox.py")
        verify = self.root / "_toolchain" / "verify"
        verify.mkdir(parents=True, exist_ok=True)

        agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(agents, "test-agent", "code-reviewer")
        self.env_file.write_text(
            "TYPE=generic\n"
            "AGENT=tester\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL="true"\n'
            "MAX_RETRIES=0\n"
            f"SANDBOX={sandbox_value}\n"
            'SANDBOX_TOOLS="git"\n',
            encoding="utf-8",
        )
        (self.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] T-1 Test\n  Beschreibung: Test\n",
            encoding="utf-8",
        )
        (self.project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
        support.init_repo(self.project)
        support.commit_all(self.project)

        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_") or key in (
                "AGENT",
                "TESTER",
                "REVIEWER",
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
                "VIBE_INSTALL": str(self.root / "_toolchain"),
                "VIBE_RUNTIME": str(self.root / "_logs"),
                "VIBE_AGENTS_DIR": str(agents),
                "VIBE_LOGNAME": "proj",
                "HOME": str(self.home),
                "PATH": str(toolbin) + os.pathsep + env.get("PATH", ""),
                "FAKE_ARGS": str(args_file),
                "FAKE_ESCAPE": str(escape),
                "FAKE_CALLS": str(self.root / "opencode.calls"),
                "FAKE_COUNTER": str(self.root / "counter"),
                "VIBE_NO_CONTAINER": "1",
            }
        )
        return env, args_file, escape

    def run_runner(self, env):
        return subprocess.run(
            ["bash", str(self.root / "_toolchain" / "bin" / "vibe-run.sh"),
             str(self.project), "tester"],
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
        # VIBE_UI_BIND/VIBE_UI_PORT und persönliche Konfiguration nicht erben:
        # der Testserver muss auf 127.0.0.1 binden.
        env = env_support.isolated_environ(
            VIBE=cls.root,
            VIBE_NO_CONTAINER="1",
            VIBE_UI_PORT=cls.port,
            VIBE_RUNTIME=cls.root / "_logs",
            VIBE_STATE=cls.root / "_toolchain",
            HOME=cls.root / "home",
            VIBE_CONFIG_FILE=(
                cls.root / "home" / ".config" / "vibe" / "config.json"
            ),
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

    @env_support.skip_if_sandbox_nested
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


# ===========================================================================
# Abnahme: opencode-go-Zugangsdaten in der Sandbox (Nutzerentscheidung A)
# ===========================================================================

import contextlib
import importlib.machinery
import importlib.util
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path


MODULE_KEYS = (
    "VIBE", "VIBE_RUNTIME", "VIBE_STATE", "VIBE_SANDBOX_ROOT",
    "VIBE_BWRAP", "XDG_DATA_HOME",
)

# (Typ, Name, SQL) — dieselbe Form, wie sie sqlite_master liefert.
SCHEMA = [
    ("table", "credential",
     "CREATE TABLE `credential` ("
     "`id` text PRIMARY KEY, `integration_id` text, `data` text)"),
    ("table", "account",
     "CREATE TABLE `account` (`id` text PRIMARY KEY, `email` text NOT NULL)"),
    ("table", "account_state",
     "CREATE TABLE `account_state` ("
     "`id` integer PRIMARY KEY, `active_account_id` text)"),
    ("table", "control_account",
     "CREATE TABLE `control_account` ("
     "`email` text PRIMARY KEY, `url` text NOT NULL)"),
    ("table", "migration",
     "CREATE TABLE `migration` "
     "(`id` TEXT PRIMARY KEY, `time_completed` INTEGER NOT NULL)"),
    ("table", "session_v2",
     "CREATE TABLE `session_v2` (`id` text PRIMARY KEY, `project_id` text)"),
    ("table", "session_message",
     "CREATE TABLE `session_message` (`id` text PRIMARY KEY, `session_id` text)"),
    ("table", "kv",
     "CREATE TABLE `kv` (`key` text PRIMARY KEY, `value` text NOT NULL)"),
    ("index", "credential_integration_idx",
     "CREATE INDEX `credential_integration_idx` ON `credential` (`integration_id`)"),
]
CREDENTIAL_OBJECTS = {"credential", "credential_integration_idx"}


def load_sandbox_credentials():
    loader = importlib.machinery.SourceFileLoader(
        "vibe_sandbox_ap1_credentials", str(SANDBOX)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class SandboxCredentialsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nSANDBOX=on\nSANDBOX_TOOLS=\"git\"\n", encoding="utf-8"
        )
        self.home = self.root / "home"
        self.home.mkdir()
        self.xdg = self.root / "xdg"
        self.xdg.mkdir()

        self.old = {key: os.environ.get(key) for key in MODULE_KEYS}
        self.addCleanup(self._restore_env)
        for key in MODULE_KEYS:
            os.environ.pop(key, None)
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        os.environ["XDG_DATA_HOME"] = str(self.xdg)
        os.environ["VIBE_SANDBOX_ROOT"] = str(self.root / "sandbox")
        fake_bwrap = self.root / "fake-bwrap"
        fake_bwrap.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake_bwrap.chmod(0o755)
        os.environ["VIBE_BWRAP"] = str(fake_bwrap)

        self.sandbox = load_sandbox_credentials()

    def _restore_env(self):
        for key, value in self.old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if self.old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.old_home

    def source_db(self):
        return self.xdg / "opencode" / "opencode.db"

    def target_db(self):
        return (
            Path(self.sandbox.state_dir(self.project))
            / "data" / "opencode" / "opencode.db"
        )

    def write_db(self, path, credential_value="test-token", sessions=False,
                 include_credential=True, session_id="source-session"):
        """Legt eine DB mit dem Test-Schema und ausgewählten Zeilen an."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.closing(sqlite3.connect(path)) as connection:
            for kind, name, sql in SCHEMA:
                if not include_credential and name in CREDENTIAL_OBJECTS:
                    continue
                connection.execute(sql)
            names = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")
            }
            if credential_value is not None and "credential" in names:
                connection.execute(
                    'INSERT INTO "credential" VALUES (?, ?, ?)',
                    ("opencode-go", "opencode-go", credential_value),
                )
                connection.execute(
                    'INSERT INTO "account" VALUES (?, ?)',
                    ("acct-1", "test@example.invalid"),
                )
                connection.execute(
                    'INSERT INTO "account_state" VALUES (?, ?)',
                    (1, "acct-1"),
                )
                connection.execute(
                    'INSERT INTO "control_account" VALUES (?, ?)',
                    ("test@example.invalid", "https://example.invalid"),
                )
                connection.execute(
                    'INSERT INTO "migration" VALUES (?, ?)',
                    ("2026-01-01", 1),
                )
            if sessions:
                connection.execute(
                    'INSERT INTO "session_v2" VALUES (?, ?)',
                    (session_id, "source-project"),
                )
                connection.execute(
                    'INSERT INTO "session_message" VALUES (?, ?)',
                    ("source-message", session_id),
                )
                connection.execute(
                    'INSERT INTO "kv" VALUES (?, ?)',
                    ("model-catalog", "source-only"),
                )
            connection.commit()
        return path

    def values(self, path, query):
        with contextlib.closing(sqlite3.connect(path)) as connection:
            return connection.execute(query).fetchall()

    def object_names(self, path, kind):
        with contextlib.closing(sqlite3.connect(path)) as connection:
            return {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type=?", (kind,))
            }

    def bind_pairs(self, argv):
        return [
            (argv[index], argv[index + 1], argv[index + 2])
            for index in range(len(argv) - 2)
            if argv[index] in ("--bind", "--ro-bind", "--ro-bind-try")
        ]

    def test_ak1_schema_and_credentials_are_copied_without_session_data(self):
        """AK1: Schema und Zugangsdaten kopieren, keine Sitzungsdaten."""
        self.write_db(self.source_db(), sessions=True)

        argv = self.sandbox.bwrap_argv(self.project, ["true"])

        self.assertTrue(argv)
        target = self.target_db()
        self.assertTrue(target.is_file(), "Sandbox-DB wurde nicht angelegt")
        self.assertEqual(
            0o600, stat.S_IMODE(target.stat().st_mode),
            "Die neue Datenbank ist nicht nur für den Besucher lesbar")
        tables = self.object_names(target, "table")
        indexes = self.object_names(target, "index")
        for kind, name, _sql in SCHEMA:
            self.assertIn(name, tables if kind == "table" else indexes)
        self.assertIn("sqlite_autoindex_credential_1", indexes)
        self.assertEqual(
            [("opencode-go", "test-token")],
            self.values(
                target,
                'SELECT integration_id, data FROM "credential" ORDER BY id'),
        )
        for table in ("account", "account_state", "control_account", "migration"):
            self.assertEqual(
                1, len(self.values(target, f'SELECT * FROM "{table}"')),
                f"Zugangsdatentabelle {table} wurde nicht kopiert")
        for table in ("session_v2", "session_message", "kv"):
            self.assertEqual(
                [], self.values(target, f'SELECT * FROM "{table}"'),
                f"Sitzungsdaten aus {table} wurden übernommen")

    def test_ak2_existing_credentials_are_not_overwritten(self):
        """AK2: Vorhandene sandbox-lokale Zugangsdaten bleiben unverändert."""
        self.write_db(self.source_db())
        target = self.write_db(
            self.target_db(), credential_value="sandbox-token", sessions=True,
            session_id="sandbox-session",
        )
        before = target.read_bytes()

        argv = self.sandbox.bwrap_argv(self.project, ["true"])

        self.assertTrue(argv)
        self.assertEqual(before, target.read_bytes())
        self.assertEqual(
            [("sandbox-token",)],
            self.values(target, 'SELECT data FROM "credential"'),
        )

    def test_ak3_empty_credentials_are_filled_without_touching_sessions(self):
        """AK3: Upgrade füllt credential auf, lässt Sitzungen unangetastet."""
        self.write_db(self.source_db(), sessions=True)
        target = self.write_db(
            self.target_db(), credential_value=None, sessions=True,
            session_id="sandbox-session",
        )

        argv = self.sandbox.bwrap_argv(self.project, ["true"])

        self.assertTrue(argv)
        self.assertEqual(
            [("opencode-go", "test-token")],
            self.values(
                target,
                'SELECT integration_id, data FROM "credential" ORDER BY id'),
        )
        self.assertEqual(
            [("sandbox-session", "source-project")],
            self.values(target, 'SELECT * FROM "session_v2"'),
        )
        self.assertEqual(
            [("source-message", "sandbox-session")],
            self.values(target, 'SELECT * FROM "session_message"'),
        )
        self.assertEqual(
            [("model-catalog", "source-only")],
            self.values(target, 'SELECT * FROM "kv"'),
        )

    def test_ak4_missing_source_db_creates_no_target_and_does_not_abort(self):
        """AK4: Fehlende Host-DB ist kein Abbruch und erzeugt keine Zieldatei."""
        self.assertFalse(self.source_db().exists())

        argv = self.sandbox.bwrap_argv(self.project, ["true"])

        self.assertTrue(argv)
        self.assertFalse(self.target_db().exists())

    def test_ak5_source_without_credential_table_does_not_abort(self):
        """AK5: Alte Host-DB ohne credential-Tabelle ist kein Abbruch."""
        self.write_db(
            self.source_db(), include_credential=False, sessions=True)

        argv = self.sandbox.bwrap_argv(self.project, ["true"])

        self.assertTrue(argv)
        target = self.target_db()
        if target.exists():
            self.assertNotIn("credential", self.object_names(target, "table"))

    def test_ak6_legacy_auth_json_binding_is_unchanged(self):
        """AK6: auth.json wird weiterhin nur lesend eingebunden."""
        auth = self.home / ".local" / "share" / "opencode" / "auth.json"
        auth.parent.mkdir(parents=True, exist_ok=True)
        auth.write_text("{}\n", encoding="utf-8")
        self.write_db(self.source_db())

        argv = self.sandbox.bwrap_argv(self.project, ["true"])

        data_home = Path(self.sandbox.state_dir(self.project)) / "data"
        self.assertIn(
            ("--ro-bind", str(auth),
             str(data_home / "opencode" / "auth.json")),
            self.bind_pairs(argv),
        )


# ===========================================================================
# Unabhängige Tests für Arbeitspaket (Bug: „Sandbox fehlerhaft“)
# ===========================================================================

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.unit import env_support


# Sichere Grenze für Zustandspfade; nachgeschaltete Werkzeugpfade (Sockets)
# dürfen die AF_UNIX-Grenze von 108 Zeichen nicht erreichen. Die
# Implementierung begrenzt Zustandspfade selbst auf 84 Zeichen
# (STATE_PATH_LIMIT); hier gilt dieselbe Schwelle. Pfade über 84 weichen
# auf die kurze Rückfallform aus.
LIMIT = 84
# Fester Kurzpfad (tmpfs) für den Rückfall, wenn der Zustandsort zu lang wäre
# (per-UID, siehe SANDBOX_STATE_ROOT/SHORT_STATE_ROOT oben).
FALLBACK_ROOT = SHORT_STATE_ROOT


class B5Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="b5-base-")
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        self.env_file = self.project / ".vibe" / "project.env"
        self.env_file.write_text(
            'SANDBOX=on\nSANDBOX_TOOLS="git"\n', encoding="utf-8"
        )
        self.home = self.root / "home"
        self.home.mkdir(parents=True)
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        self.addCleanup(self._restore, "HOME", old_home)
        self.bwrap = shutil.which("bwrap")
        self.sandbox = load_module(SANDBOX, "b5_vibe_sandbox_under_test")

    def _restore(self, key, value):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
        self.tmp.cleanup()

    def override_root_env(self, value):
        old = os.environ.get("VIBE_SANDBOX_ROOT")
        self.addCleanup(self._restore, "VIBE_SANDBOX_ROOT", old)
        if value is None:
            os.environ.pop("VIBE_SANDBOX_ROOT", None)
        else:
            os.environ["VIBE_SANDBOX_ROOT"] = value

    def long_project(self, name_len=200):
        """Projekt mit ausdrücklich sehr langem Namen und langem Vorbereich."""
        name = "b" * name_len
        base = self.root / ("lang-" + "x" * 120)
        project = base / name
        (project / ".vibe").mkdir(parents=True, exist_ok=True)
        (project / ".vibe" / "project.env").write_text(
            'SANDBOX=on\nSANDBOX_TOOLS="git"\n', encoding="utf-8"
        )
        return project

    def cleanup_state_dir(self, project):
        """M5: Den von state_dir(project) bestimmten Zustandsordner leeren.

        Genau der zurückgegebene Pfad, keine anderen Verzeichnisse.
        """
        path = self.sandbox.state_dir(project)
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path

    def shm_project(self):
        """Projektverzeichnis unter /dev/shm, vor dem Lauf aus dem Test-
        prozess angelegt und in die Schreibrechte-Liste aufgenommen."""
        base = Path("/dev/shm") / (
            "b5-proj-" + str(os.getpid()) + "-" + str(time.time_ns())
        )
        project = base / "proj"
        (project / ".vibe").mkdir(parents=True)
        (project / ".vibe" / "project.env").write_text(
            'SANDBOX=on\nSANDBOX_TOOLS="git"\n', encoding="utf-8"
        )
        (project / ".vibe" / "permissions.json").write_text(
            json.dumps({"write_dirs": [str(project)]}),
            encoding="utf-8",
        )
        self.addCleanup(shutil.rmtree, str(base), ignore_errors=True)
        return project

    @staticmethod
    def digest_of(project):
        return hashlib.sha256(
            os.path.realpath(project).encode("utf-8")
        ).hexdigest()[:10]

    def run_sandboxed(self, project, script):
        env = dict(
            os.environ,
            HOME=str(self.home),
            VIBE=str(self.root),
        )
        env.pop("VIBE_SANDBOX_ROOT", None)
        return subprocess.run(
            [sys.executable, str(SANDBOX), str(project), "--", "/bin/sh", "-c", script],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )

    def unique_shm_marker(self, label):
        return "/dev/shm/b5-" + label + "-" + str(os.getpid()) + "-" + str(time.time_ns())


def pair_positions(argv, flag):
    """Positionen, an denen `flag` beginnt; Ziel/Beiwerk folgt dahinter."""
    return [index for index in range(len(argv) - 1) if argv[index] == flag]


def collect_setenv(argv):
    """Tabelle der --setenv-Paare eines bwrap-argv."""
    result = {}
    for first, key, value in zip(argv, argv[1:], argv[2:]):
        if first == "--setenv":
            result[key] = value
    return result


class ShmArgumentTest(B5Fixture):
    """Zu 1: Auf Argumentebene bekommt /dev/shm ein privates tmpfs."""

    def test_bwrap_arguments_mount_a_private_shm_unless_allowed(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.cleanup_state_dir(self.project)
        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap=self.bwrap
        )
        pairs = list(zip(argv, argv[1:]))
        expected = ("--tmpfs", "/dev/shm")
        self.assertIn(expected, pairs)
        self.assertEqual(pairs.count(expected), 1)
        # Nicht erlaubt heißt: kein Binden des Host-Verzeichnisses.
        self.assertNotIn(("--bind", "/dev/shm"), pairs)
        self.assertNotIn(("--ro-bind", "/dev/shm"), pairs)

        # Ausdrücklich erlaubt: kein privates tmpfs, Host-Verzeichnis bleibt
        # über die Schreibfreigabe erreichbar.
        self.project.joinpath(".vibe", "permissions.json").write_text(
            json.dumps({"write_dirs": ["/dev/shm", str(self.project)]}),
            encoding="utf-8",
        )
        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap=self.bwrap
        )
        pairs = list(zip(argv, argv[1:]))
        self.assertNotIn(("--tmpfs", "/dev/shm"), pairs)


    def test_shm_tmpfs_pair_precedes_every_regular_bind_pair(self):
        """M3a: tmpfs-Paar vor jeder --bind-Einleitung (bwrap stapelt Mounts
        in Argumentreihenfolge; danach überschattet der frische Mount
        Bindungen auf /dev/shm-Unterpfade — Defekt aus Runde 1)."""
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.cleanup_state_dir(self.project)
        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap=self.bwrap
        )
        shm_pair = [
            index for index in pair_positions(argv, "--tmpfs")
            if argv[index + 1] == "/dev/shm"
        ]
        self.assertEqual(len(shm_pair), 1)
        bind_positions = pair_positions(argv, "--bind")
        self.assertTrue(bind_positions, "Mindestens eine --bind-Bindung erwartet")
        for index in bind_positions:
            self.assertLess(shm_pair[0], index)

    def test_bind_of_a_project_under_shm_is_not_shadowed_by_the_tmpfs(self):
        """M3a-Variante: Bindung auf einen /dev/shm-Unterpfad (Projektort)
        steht nach dem tmpfs-Paar; /dev/shm selbst bleibt unerlaubt."""
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        project = self.shm_project()
        self.cleanup_state_dir(project)
        argv = self.sandbox.bwrap_argv(
            project, ["/bin/true"], bwrap=self.bwrap
        )
        shm_pair = [
            index for index in pair_positions(argv, "--tmpfs")
            if argv[index + 1] == "/dev/shm"
        ]
        self.assertEqual(
            len(shm_pair), 1,
            "Ohne Freigabe von /dev/shm muss das tmpfs-Paar existieren",
        )
        shm_binds = [
            index for index in range(len(argv) - 1)
            if argv[index] in ("--bind", "--ro-bind")
            and argv[index + 1].startswith("/dev/shm")
        ]
        self.assertTrue(
            shm_binds,
            "Das Projekt unter /dev/shm muss eingebunden werden",
        )
        for index in shm_binds:
            self.assertLess(shm_pair[0], index)


class ShmIsolationTest(B5Fixture):
    """Zu 1: Echte bwrap-Läufe — /dev/shm ist isoliert und schreibbar."""

    @env_support.skip_if_sandbox_nested
    def test_host_shm_content_is_invisible_inside_the_sandbox(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.cleanup_state_dir(self.project)
        host_marker = self.unique_shm_marker("host")
        Path(host_marker).write_text("das-sieht-man-nicht", encoding="utf-8")
        self.addCleanup(lambda: Path(host_marker).unlink(missing_ok=True))

        result = self.run_sandboxed(
            self.project,
            "if [ -f '%s' ]; then echo HOST_SHM_VISIBLE; "
            "else echo HOST_SHM_HIDDEN; fi; "
            "echo inhalt > /dev/shm/b5-probe && echo SHM_WRITABLE "
            "|| echo SHM_DENIED" % shlex.quote(host_marker),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HOST_SHM_HIDDEN", result.stdout)
        self.assertIn("SHM_WRITABLE", result.stdout)
        self.assertIn("das-sieht-man-nicht", Path(host_marker).read_text(encoding="utf-8"))

    @env_support.skip_if_sandbox_nested
    def test_sandbox_shm_content_is_invisible_to_the_host(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.cleanup_state_dir(self.project)
        marker = self.unique_shm_marker("innen")

        result = self.run_sandboxed(
            self.project,
            "echo aus-der-sandbox > %s 2>/dev/null && echo INNEN_OK "
            "|| echo INNEN_GESCHEITERT" % shlex.quote(marker),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("INNEN_OK", result.stdout)
        self.assertFalse(Path(marker).exists())

class ShmProjectRunTest(B5Fixture):
    """Zu M3b (Reviewrunde 1): Echter Lauf mit Projekt unter /dev/shm.

    Genau der Defekt aus Umsetzungsrunde 1: Stand das tmpfs hinter den
    Bindungen, überschattete es die Projekt-Bindung. Sichtbar wird der
    Unterschied außerhalb: Die Projekt-Datei muss nach dem Lauf im
    Testprozess existieren, die Schreibmarke im /dev/shm-Wurzelbereich
    darf nicht auftauchen.
    """

    @env_support.skip_if_sandbox_nested
    def test_project_under_shm_is_writable_and_host_shm_stays_isolated(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        project = self.shm_project()
        self.cleanup_state_dir(project)
        host_marker = self.unique_shm_marker("host-run")

        result = self.run_sandboxed(
            project,
            "echo in-der-sandbox-geschrieben > inside.txt && echo INSIDE_OK "
            "|| echo INSIDE_FAILED; "
            "echo geheim > %s 2>/dev/null && echo MARKER_WRITTEN "
            "|| echo MARKER_DENIED" % shlex.quote(host_marker),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("INSIDE_OK", result.stdout)
        # Die Projekt-Bindung hebt die /dev/shm-Überschattung auf: Die
        # geschriebene Datei ist nach dem Lauf im Testprozess sichtbar.
        self.assertTrue((project / "inside.txt").exists())
        self.assertEqual(
            (project / "inside.txt").read_text(encoding="utf-8"),
            "in-der-sandbox-geschrieben\n",
        )
        # Schreibmarke in einer NICHT erlaubten Stelle unter /dev/shm:
        # frisches tmpfs, nach dem Lauf für den Testprozess unsichtbar.
        self.assertIn("MARKER_WRITTEN", result.stdout)
        self.assertFalse(Path(host_marker).exists())


class BandLimitTest(B5Fixture):
    """Zu M4 (Reviewrunde 1): Ausweichen greift schon im Band 85..100.

    Der Root ist so konstruiert, dass der nicht-ausgewichene Zustandspfad
    über der neuen Begrenzung (84) liegt, aber unter der alten 100er-Grenze
    bliebe: genau dort darf die Implementierung nicht nach der alten Regel
    hängen bleiben.
    """

    def test_state_dir_falls_back_in_the_85_to_100_character_band(self):
        root = "/tmp/opencode/b5-band-" + "z" * 60
        self.override_root_env(root)
        digest = self.digest_of(self.project)
        band_pfad = os.path.join(os.path.abspath(root), "proj-" + digest)
        self.assertGreaterEqual(
            len(band_pfad), 85,
            "Vorbedingung: Pfad muss oberhalb der 84er-Begrenzung liegen",
        )
        self.assertLessEqual(
            len(band_pfad), 100,
            "Vorbedingung: Pfad muss im Band 85..100 liegen",
        )

        self.cleanup_state_dir(self.project)
        result = self.sandbox.state_dir(self.project)

        self.assertTrue(result.startswith(FALLBACK_ROOT + os.sep), result)
        self.assertLess(len(result), 96, result)
        self.assertIn(digest, result)


class StateDirTest(B5Fixture):
    """Zu 2 und 3: Zustandsort bleibt kurz, Rückfall und status()-Konsistenz."""

    def test_state_dir_stays_under_the_limit_for_a_very_long_project_name(self):
        project = self.long_project()
        self.assertGreater(
            len(os.path.basename(os.path.realpath(project))), 100,
            "Vorbedingung: Projektname muss sehr lang sein",
        )

        self.override_root_env(None)
        result = self.sandbox.state_dir(project)
        self.assertLess(len(result), LIMIT, result)

        self.override_root_env("/tmp/opencode")
        result = self.sandbox.state_dir(project)
        self.assertLess(len(result), LIMIT, result)

    def test_state_dir_falls_back_to_the_short_tmpfs_root_with_the_same_digest(self):
        project = self.long_project()
        long_root = "/tmp/opencode/" + "zu-lang-" + "y" * 80
        self.override_root_env(long_root)

        self.cleanup_state_dir(project)
        result = self.sandbox.state_dir(project)

        self.assertTrue(result.startswith(FALLBACK_ROOT + os.sep), result)
        self.assertLess(len(result), LIMIT, result)
        expected_digest = self.digest_of(project)
        tail = result[len(FALLBACK_ROOT) + 1:]
        self.assertTrue(
            tail.endswith("-" + expected_digest) or expected_digest in tail,
            result + " fehlt Projekt-Digest " + expected_digest,
        )

    def test_state_dir_honors_a_short_custom_root(self):
        self.override_root_env("/tmp/opencode/kurze-wald")

        self.cleanup_state_dir(self.project)
        result = self.sandbox.state_dir(self.project)

        self.assertTrue(result.startswith("/tmp/opencode/kurze-wald" + os.sep), result)
        self.assertIn(self.digest_of(self.project), result)

    def test_status_reports_the_same_state_dir_as_state_dir(self):
        for value in (None, "/tmp/opencode", "/tmp/opencode/" + "y" * 80):
            with self.subTest(root=value):
                self.override_root_env(value)
                project = self.long_project()
                self.cleanup_state_dir(project)
                status = self.sandbox.status(project)
                self.assertEqual(status["state_dir"], self.sandbox.state_dir(project))
                self.assertLess(len(status["state_dir"]), LIMIT)

    def test_write_dirs_keep_workflow_directory_in_fallback(self):
        self.override_root_env("/tmp/opencode/" + "y" * 80)
        project = self.long_project()

        self.cleanup_state_dir(project)
        status = self.sandbox.status(project)

        self.assertTrue(status["enabled"])
        for expected in (
            os.path.realpath(project),
            os.path.realpath(OPENCODE_STATE_ROOT),
            status["state_dir"],
        ):
            self.assertIn(expected, status["write_dirs"], expected)


class SetEnvTest(B5Fixture):
    """Zu 4: XDG- und TMPDIR-Belegungen bleiben kurz und zeigen in state_dir."""

    def test_setenv_paths_stay_under_the_limit(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.override_root_env("/tmp/opencode/" + "y" * 80)
        project = self.long_project()

        self.cleanup_state_dir(project)
        argv = self.sandbox.bwrap_argv(
            project, ["/bin/true"], bwrap=self.bwrap
        )
        state_dir = self.sandbox.state_dir(project)

        setenv = collect_setenv(argv)
        for variable in ("XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "TMPDIR"):
            with self.subTest(variable=variable):
                self.assertIn(variable, setenv, "setenv fehlt: " + variable)
                self.assertLess(len(setenv[variable]), LIMIT, setenv[variable])
                self.assertTrue(
                    setenv[variable].startswith(state_dir + os.sep),
                    setenv[variable] + " zeigt nicht in den Zustandsort",
                )


    def test_setenv_from_band_root_stays_below_the_af_unix_limit(self):
        """M4: Auch vom Band-Root (85..100) bleibt TMPDIR samt angenommenem
        tmux-Socket unter der AF_UNIX-Grenze von 108 Zeichen."""
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        root = "/tmp/opencode/b5-band-" + "z" * 60
        self.override_root_env(root)
        project = self.long_project()
        self.cleanup_state_dir(project)

        argv = self.sandbox.bwrap_argv(
            project, ["/bin/true"], bwrap=self.bwrap
        )
        state_dir = self.sandbox.state_dir(project)
        self.assertTrue(state_dir.startswith(FALLBACK_ROOT + os.sep), state_dir)

        setenv = collect_setenv(argv)
        tmpdir = setenv["TMPDIR"]
        tmux_socket = tmpdir + "/tmux-1000/default"
        self.assertEqual(tmpdir, state_dir + os.sep + "tmp", tmpdir)
        self.assertLess(len(tmpdir), 108, tmpdir)
        self.assertLess(len(tmux_socket), 108, tmux_socket)


# ===========================================================================
# Unabhängige Tests für Arbeitspaket (Bug: „Fehler bei Verwendung von
# ===========================================================================

import hashlib
import importlib.machinery
import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.unit import env_support


# Direkte Einträge dieser beiden Wurzeln werden unmittelbar vor und nach
# den echten Läufen verglichen; das Aufräumen des state_dir muss den
# Unterschied vollständig zurücknehmen. Beide Wurzeln sind per-UID.
SANDBOX_ROOTS = (SANDBOX_STATE_ROOT, SHORT_STATE_ROOT)


def setenv_frequencies(argv):
    """Anzahl der --setenv-Einträge je Variablen."""
    result = {}
    for first, key in zip(argv, argv[1:]):
        if first == "--setenv":
            result[key] = result.get(key, 0) + 1
    return result


def bind_triples(argv):
    """Tabelle der Bindungsdreier (Flag, Quelle, Ziel)."""
    return [
        (first, source, target)
        for first, source, target in zip(argv, argv[1:], argv[2:])
        if first in ("--bind", "--ro-bind", "--dev-bind", "--dev-bind-try")
    ]


def roots_snapshot():
    """Liste der direkten Einträge der beiden Sandbox-Zustandswurzeln."""
    items = []
    for root in SANDBOX_ROOTS:
        base = Path(root)
        if base.is_dir():
            items.extend(sorted(str(path) for path in base.iterdir()))
    return items


class B4Fixture(unittest.TestCase):
    def setUp(self):
        # Die aktuelle Agentensitzung kennt /tmp und /var/tmp als
        # schreibgeschützt; der Projektbaum wurde wie bei F16 als
        # Prüfverzeichnis im Repository belegt. Er liegt — anders als der
        # Sandbox-Zustandsordner — nie in einem als Schreibverzeichnis
        # gebundenen Baum, damit die Verneinungsfälle von AK5 beobachtbar
        # bleiben.
        self.tmp = tempfile.TemporaryDirectory(prefix=".b4-", dir=str(REPO))
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        self.env_file = self.project / ".vibe" / "project.env"
        self.env_file.write_text(
            'SANDBOX=on\nSANDBOX_TOOLS="git"\n', encoding="utf-8"
        )
        self.home = self.root / "home"
        self.home.mkdir(parents=True)
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        self.addCleanup(self._restore, "HOME", old_home)
        self.bwrap = shutil.which("bwrap")
        self.sandbox = load_module(SANDBOX, "b4_vibe_sandbox_under_test")

    def _restore(self, key, value):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
        self.tmp.cleanup()

    def cleanup_state_dir(self):
        """Räumt genau den state_dir(project) je Test weg (B5-Regel)."""
        path = self.sandbox.state_dir(self.project)
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path

    def expected_pi_dir(self):
        return os.path.join(self.sandbox.state_dir(self.project), "pi", "agent")

    def run_sandboxed(self, script):
        env = dict(os.environ, HOME=str(self.home), VIBE=str(self.root))
        env.pop("VIBE_SANDBOX_ROOT", None)
        return subprocess.run(
            [sys.executable, str(SANDBOX), str(self.project), "--",
             "/bin/sh", "-c", script],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )


class PiAgentDirSetEnvTest(B4Fixture):
    """AK1: setenv-Paar und Anlage des Pi-Agentenordners im Zustandsort."""

    def test_bwrap_argv_sets_pi_agent_dir_exactly_once_under_state(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.cleanup_state_dir()
        state = self.sandbox.status(self.project)

        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap=self.bwrap
        )

        setenv = collect_setenv(argv)
        pi_dir = setenv.get("PI_CODING_AGENT_DIR")
        self.assertEqual(
            pi_dir, self.expected_pi_dir(),
            "PI_CODING_AGENT_DIR zeigt nicht auf den Zustandsort/pi/agent",
        )
        # Genau ein setenv-Paar für die Variable.
        self.assertEqual(setenv_frequencies(argv).get("PI_CODING_AGENT_DIR"), 1)
        # Verzeichnis nach dem Aufruf vorhanden (Vorbildung).
        self.assertTrue(
            os.path.isdir(pi_dir), "Pi-Agentenordner fehlt nach dem Aufruf"
        )
        # Der Pfad liegt unter dem Zustandsort, der ein Schreibverzeichnis
        # des Laufs ist.
        self.assertIn(state["state_dir"], state["write_dirs"])
        self.assertTrue(pi_dir.startswith(state["state_dir"] + os.sep))

    def test_pi_agent_dir_wins_over_a_preexisting_environment_variable(self):
        """Die Umleitung ist unabhängig von einer umgebungsseits gesetzten
        Variablen (Pi-Option, nicht Nutzerwahl des Laufs)."""
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.cleanup_state_dir()
        old = os.environ.get("PI_CODING_AGENT_DIR")
        os.environ["PI_CODING_AGENT_DIR"] = "/nicht/der/pi-ordner"
        self.addCleanup(self._restore, "PI_CODING_AGENT_DIR", old)

        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap=self.bwrap
        )

        setenv = collect_setenv(argv)
        self.assertEqual(setenv["PI_CODING_AGENT_DIR"], self.expected_pi_dir())
        self.assertTrue(os.path.isdir(self.expected_pi_dir()))


class AuthBindTest(B4Fixture):
    """AK2: auth.json nur lesend in den Pi-Agentenordner gebunden."""

    def setUp(self):
        super().setUp()
        (self.home / ".pi" / "agent").mkdir(parents=True)
        self.auth = self.home / ".pi" / "agent" / "auth.json"
        self.auth.write_text('{"marker":"pruefstand"}', encoding="utf-8")

    def test_auth_json_is_read_only_bound_into_the_pi_agent_dir(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.cleanup_state_dir()

        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap=self.bwrap
        )

        pi_dir = collect_setenv(argv)["PI_CODING_AGENT_DIR"]
        target = os.path.join(pi_dir, "auth.json")
        triples = [
            triple for triple in bind_triples(argv)
            if triple[1] == str(self.auth) or triple[2] == str(self.auth)
        ]
        self.assertEqual(
            len(triples), 1,
            "Mehr als eine Bindung auf auth.json: " + repr(triples),
        )
        self.assertEqual(
            triples[0],
            ("--ro-bind", str(self.auth), target),
            "auth.json muss ausschließlich lesend in den "
            "Pi-Agentenordner gebunden werden",
        )
        # Kein beschreibendes Doppel derselben Quelle.
        pairs = list(zip(argv, argv[1:]))
        self.assertNotIn(("--bind", str(self.auth)), pairs)
        # Das Ziel ist der Pi-Agentenordner, nicht der opencode-Datenort.
        self.assertEqual(os.path.dirname(target), pi_dir)
        self.assertNotEqual(
            os.path.dirname(target),
            os.path.join(
                self.sandbox.state_dir(self.project),
                "data", "opencode",
            ),
        )
        # Die Quelldatei bleibt unverändert vorhanden.
        self.assertEqual(
            self.auth.read_text(encoding="utf-8"), '{"marker":"pruefstand"}'
        )


class MissingAuthTest(B4Fixture):
    """AK3: Fehlende auth.json erzeugt keine Bindung und keinen Abbruch."""

    def test_empty_home_binds_no_auth_file_but_keeps_the_setenv(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.cleanup_state_dir()
        self.assertFalse(
            (self.home / ".pi" / "agent" / "auth.json").exists(),
            "Vorbedingung verletzt: HOME enthält auth.json",
        )

        # Der Aufruf darf nicht an der fehlenden Datei scheitern.
        argv = self.sandbox.bwrap_argv(
            self.project, ["/bin/true"], bwrap=self.bwrap
        )

        for triple in bind_triples(argv):
            for part in (triple[1], triple[2]):
                self.assertFalse(
                    part.endswith("auth.json"),
                    "unerwartete auth.json-Bindung: " + repr(triple),
                )
        # Das setenv bleibt trotzdem erhalten (Pi-Agentenordner angelegt).
        pi_dir = collect_setenv(argv)["PI_CODING_AGENT_DIR"]
        self.assertEqual(pi_dir, self.expected_pi_dir())
        self.assertTrue(os.path.isdir(pi_dir))


class DisabledSandboxTest(B4Fixture):
    """AK4: Ohne Sandbox bleibt --print-command ohne den Pi-Zusatz."""

    def test_print_command_off_shows_plain_command_without_pi_agent_dir(self):
        self.env_file.write_text("TYPE=generic\n", encoding="utf-8")
        # Auch ein vorhandenes auth.json im isolierten HOME ändert am
        # deaktivierten Verhalten nichts.
        (self.home / ".pi" / "agent").mkdir(parents=True, exist_ok=True)
        (self.home / ".pi" / "agent" / "auth.json").write_text(
            '{"marker":true}', encoding="utf-8"
        )

        result = subprocess.run(
            [sys.executable, str(SANDBOX), str(self.project),
             "--print-command", "--", "/bin/sh", "-c", "echo probe"],
            capture_output=True,
            text=True,
            env=dict(os.environ, HOME=str(self.home), VIBE=str(self.root)),
            timeout=30,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        # Plain-Befehl: kein bubblewrap, kein Pi-Zusatz.
        self.assertEqual(
            result.stdout.strip(),
            shlex.join(["/bin/sh", "-c", "echo probe"]),
        )
        self.assertNotIn("PI_CODING_AGENT_DIR", result.stdout + result.stderr)
        self.assertNotIn("bwrap", result.stdout)


class PiAgentDirRunTest(B4Fixture):
    """AK5: Echte bwrap-Läufe — Pi-Agentenordner schreibbar, Host sichtbar."""

    @env_support.skip_if_sandbox_nested
    def test_pi_agent_dir_writable_state_visible_and_home_denied(self):
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        before = roots_snapshot()
        self.cleanup_state_dir()
        pi_dir = self.expected_pi_dir()
        escape = self.home / "darf-nicht-gelingen"
        self.assertFalse(escape.exists())
        script = (
            'echo probe > "$PI_CODING_AGENT_DIR/trust.json.lock" 2>/dev/null '
            "&& echo PI_WRITE_OK || echo PI_WRITE_FAILED; "
            'if cat "$PI_CODING_AGENT_DIR/trust.json.lock" 2>/dev/null '
            "| grep -q probe; then echo PI_READBACK_OK; fi; "
            f"if echo x > {shlex.quote(str(escape))} "
            "2>/dev/null; then echo HOME_OPEN; else echo HOME_DENIED; fi"
        )

        result = self.run_sandboxed(script)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PI_WRITE_OK", result.stdout)
        self.assertNotIn("PI_WRITE_FAILED", result.stdout)
        # Die geschriebene Sperrdatei liegt auf dem Host unter dem
        # Zustandsort (kein flüchtiges tmpfs, kein EROFS-Abbruch).
        lock = Path(pi_dir) / "trust.json.lock"
        self.assertTrue(lock.is_file(), "Sperrdatei fehlt auf dem Host")
        self.assertEqual(lock.read_text(encoding="utf-8"), "probe\n")
        # Fremdes HOME bleibt gesperrt (wie vor B4).
        self.assertIn("HOME_DENIED", result.stdout)
        self.assertFalse(escape.exists())
        # Aufräumbeweis (im Testkörper, damit die leere-Wurzeln-Prüfung
        # NACH dem Entfernen des Zustandsorts sieht; addCleanup läuft LIFO
        # und hätte eine dort registrierte Assertion zu früh ausgeführt).
        # Fremde gleichzeitige Sitzungen ändern die Wurzeln unabhängig von
        # diesem Test; der Abgleich betrachtet deshalb ausschließlich
        # Einträge mit dem SHA-256-Digest dieses Projekts — beide Aussagen
        # bleiben bestehen, nichts wird abgeschwächt.
        state_path = self.sandbox.state_dir(self.project)
        digest = hashlib.sha256(
            os.path.realpath(self.project).encode("utf-8")
        ).hexdigest()[:10]

        def own_entries(paths):
            return [
                path for path in paths
                if os.path.basename(path).endswith("-" + digest)
                or os.path.basename(path) == digest
            ]

        appeared = [
            path for path in roots_snapshot()
            if path not in set(before) and own_entries([path])
        ]
        for path in appeared:
            self.assertTrue(
                path == state_path or path.startswith(state_path + os.sep),
                "Der Lauf hinterließ Einträge außerhalb des Zustandsorts: "
                + repr(path),
            )
        self.assertTrue(
            appeared,
            "Der Lauf hat unter der Sandbox-Wurzel keinen Zustandsort "
            "angelegt",
        )
        # Das standardsmäßig registrierte Aufräumen (cleanup_state_dir)
        # bleibt als Netz für früher scheiternde Assertions erhalten;
        # hier wird zusätzlich konkret aufgeräumt, damit die nachfolgende
        # Prüfung den bereinigten Stand sieht.
        shutil.rmtree(state_path, ignore_errors=True)
        remaining = own_entries(roots_snapshot())
        self.assertEqual(
            remaining, [],
            "Nach dem Aufräumen blieben Einträge unter den "
            "Sandbox-Wurzeln: " + repr(remaining),
        )


# ===========================================================================
# Abnahme: Sandbox-Schnittstelle für Zusatzverzeichnisse und chdir (AK8/AK9)
# ===========================================================================

import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


MODULE_KEYS_b17 = ("VIBE_RUNTIME", "VIBE_SANDBOX_ROOT", "VIBE_BWRAP")


def load_sandbox_argv():
    loader = importlib.machinery.SourceFileLoader(
        "vibe_sandbox_b17", str(SANDBOX)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class SandboxArgvTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nSANDBOX=on\nSANDBOX_TOOLS=\"git\"\n", encoding="utf-8"
        )
        self.copy = self.root / "paket-arbeitskopie"
        self.copy.mkdir()
        self.runtime = self.root / "runtime"
        self.sandbox = load_sandbox_argv()

        self.old = {key: os.environ.get(key) for key in MODULE_KEYS_b17}
        self.addCleanup(self._restore_env)
        for key in MODULE_KEYS_b17:
            os.environ.pop(key, None)
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.root / "home")
        (self.root / "home").mkdir()
        fake_bwrap = self.root / "fake-bwrap"
        fake_bwrap.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake_bwrap.chmod(0o755)
        os.environ["VIBE_BWRAP"] = str(fake_bwrap)

    def _restore_env(self):
        for key, value in self.old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if self.old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.old_home

    def bind_pairs(self, argv):
        return [
            (argv[index], argv[index + 1], argv[index + 2])
            for index in range(len(argv) - 2)
            if argv[index] in ("--bind", "--ro-bind", "--ro-bind-try")
        ]

    def setenv_pairs(self, argv):
        return [
            (argv[index], argv[index + 1], argv[index + 2])
            for index in range(len(argv) - 2)
            if argv[index] == "--setenv"
        ]

    def test_nested_sandbox_marker_is_set_once_before_the_command(self):
        """T-BR2: Der Sandbox-Start trägt den Verschachtelungsmarker.

        Vorbedingung: ``SANDBOX=on`` im Projekt und eine ausführbare
        ``VIBE_BWRAP``-Attrappe (es wird kein bubblewrap gestartet).

        Aktion: ``bwrap_argv`` für einen Sandbox-Start erzeugen.

        Erwartetes Ergebnis: Genau ein Paar
        ``('--setenv', 'VIBE_SANDBOX_ACTIVE', '1')`` steht in der
        Argumentliste, und zwar vor dem ``--``-Trenner. Nur so erbt der
        gestartete Prozess den Marker; die Endprüfung erkennt daran eine
        verschachtelte Sandbox und überspringt bwrap-abhängige Fälle mit
        Begründung, ohne pauschal auf bwrap-Verfügbarkeit zu prüfen.

        Fehlerfall: Marker fehlt, ist doppelt oder steht hinter ``--`` —
        dann erhält der Prozess ihn nicht und ein echter Defekt würde
        durch ein pauschales ``skipUnless`` verdeckt.
        """
        argv = self.sandbox.bwrap_argv(
            self.project, ["true"], runtime=self.runtime
        )

        marker = ("--setenv", "VIBE_SANDBOX_ACTIVE", "1")
        self.assertEqual(self.setenv_pairs(argv).count(marker), 1, argv)
        separator = argv.index("--")
        self.assertLess(
            argv.index("VIBE_SANDBOX_ACTIVE"), separator,
            "Marker steht hinter dem Kommandotrenner und erreicht den "
            "gestarteten Prozess nicht",
        )
        self.assertNotIn("VIBE_SANDBOX_ACTIVE", argv[separator + 1:])

    def test_extra_write_dirs_are_bound_writable(self):
        argv = self.sandbox.bwrap_argv(
            self.project, ["true"],
            runtime=self.runtime,
            extra_write_dirs=[str(self.copy)],
            chdir=str(self.copy),
        )

        self.assertIn(
            ("--bind", str(self.copy), str(self.copy)), self.bind_pairs(argv),
            "Die Paket-Arbeitskopie ist nicht beschreibbar gebunden",
        )

    def test_chdir_overrides_the_working_directory(self):
        argv = self.sandbox.bwrap_argv(
            self.project, ["true"],
            runtime=self.runtime,
            extra_write_dirs=[str(self.copy)],
            chdir=str(self.copy),
        )

        self.assertIn("--chdir", argv)
        self.assertEqual(argv[argv.index("--chdir") + 1], str(self.copy))
        self.assertNotEqual(
            argv[argv.index("--chdir") + 1], os.path.realpath(self.project)
        )

    def test_question_folder_is_writable_and_autonomous_state_read_only(self):
        argv = self.sandbox.bwrap_argv(
            self.project, ["true"], runtime=self.runtime
        )
        questions = str(self.runtime / "questions")
        autonomous = str(self.runtime / "autonomous.json")

        pairs = self.bind_pairs(argv)
        self.assertIn(("--bind", questions, questions), pairs)
        self.assertIn(("--ro-bind-try", autonomous, autonomous), pairs)
        for flag, source, _target in pairs:
            if source == autonomous:
                self.assertEqual(
                    "--ro-bind-try", flag,
                    "autonomous.json darf nicht beschreibbar gebunden werden",
                )

    def test_without_new_arguments_the_previous_behaviour_stays(self):
        argv = self.sandbox.bwrap_argv(self.project, ["true"])

        self.assertEqual(argv[argv.index("--chdir") + 1],
                         os.path.realpath(self.project))
        text = " ".join(argv)
        self.assertNotIn("questions", text)
        self.assertNotIn("autonomous.json", text)


if __name__ == "__main__":
    unittest.main()
