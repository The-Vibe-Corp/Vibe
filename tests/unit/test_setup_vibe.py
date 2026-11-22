"""Tests für den universellen Setup-Prozess (F6).

Der Setup-Prozess soll vibe unter Linux (Ubuntu, Fedora, Bazzite, Container)
und Windows installieren, fehlende Werkzeuge nur mit Zustimmung nachinstallieren
und eine bestehende Installation wiederverwenden können, ohne Laufzeitdaten zu
überschreiben. Alle schreibenden Tests arbeiten in temporären Verzeichnissen;
es werden keine Paketmanager, Router oder echten Installationen angefasst.
"""
import ast
import contextlib
import importlib.machinery
import importlib.util
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SETUP = REPO / "scripts" / "setup-vibe.py"
WRAPPER = REPO / "install-vibe.sh"
CMD_WRAPPER = REPO / "setup-vibe.cmd"
PROGRAM_FILES = (
    "vibe",
    "vibe-run.sh",
    "vibe_runs.py",
    "vibe_packages.py",
    "vibe-web.py",
    "vibe_mcp.py",
    "vibe_opencode.py",
    "vibe_models.py",
    "vibe_sandbox.py",
    "vibe_paths.py",
    "vibe_ui_config.py",
    "vibe_storage.py",
    "vibe_guide.py",
    "vibe_questions.py",
    "vibe_autonomous.py",
    "vibe_harness.py",
    "vibe_limits.py",
    "vibe_gates.py",
    "vibe_services.py",
    "vibe_github.py",
    "vibe_issues.py",
    "fritz-reconnect.py",
)
WEB_FILES = (
    "index.html", "styles.css", "app.js", "i18n.js",
    "classic.html", "nova.css", "nova-core.js", "nova-home.js",
    "nova-project.js", "nova-output.js", "nova-agents.js",
    "nova-activity.js", "nova-settings.js",
)


def launcher_sibling_modules():
    """Module, die ``bin/vibe`` beim Start aus demselben Ordner importiert."""
    tree = ast.parse((REPO / "bin" / "vibe").read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        else:
            continue
        for name in names:
            if (REPO / "bin" / (name + ".py")).is_file():
                modules.add(name)
    return sorted(modules)

setup = None


def setUpModule():
    global setup
    loader = importlib.machinery.SourceFileLoader("setup_vibe_under_test", str(SETUP))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    setup = module


def make_kit(root, models=True):
    """Baut ein minimales Repository-Abbild für Installationstests."""
    root = Path(root)
    (root / "bin").mkdir(parents=True)
    for name in PROGRAM_FILES:
        path = root / "bin" / name
        path.write_text(f"#!/usr/bin/env python3\n# {name}\nprint({name!r})\n", encoding="utf-8")
    (root / "bin" / "web").mkdir()
    for name in WEB_FILES:
        (root / "bin" / "web" / name).write_text(f"/* {name} */\n", encoding="utf-8")
    templates = root / "templates" / "generic" / ".vibe"
    templates.mkdir(parents=True)
    (templates / "project.env").write_text("TYPE=generic\n", encoding="utf-8")
    (root / "templates" / "generic" / "AGENTS.md").write_text("# generic\n", encoding="utf-8")
    if models:
        (root / "data").mkdir()
        (root / "data" / "models.json").write_text('{"models": []}\n', encoding="utf-8")
    return root


def platform_info(**overrides):
    base = {
        "system": "Linux",
        "os_release": {},
        "exists": lambda path: False,
        "env": {},
        "proc_version": "",
        "which": lambda name: None,
    }
    base.update(overrides)
    return setup.detect_platform(**base)


class PlatformDetectionTest(unittest.TestCase):
    def test_ubuntu_uses_apt(self):
        info = platform_info(os_release={"ID": "ubuntu", "VERSION_ID": "24.04", "NAME": "Ubuntu"})
        self.assertEqual(info["os"], "linux")
        self.assertEqual(info["family"], "debian")
        self.assertEqual(info["manager"], "apt-get")
        self.assertFalse(info["container"])
        self.assertIn("Ubuntu", info["label"])

    def test_fedora_uses_dnf(self):
        info = platform_info(os_release={"ID": "fedora", "VERSION_ID": "44", "NAME": "Fedora Linux"})
        self.assertEqual(info["family"], "fedora")
        self.assertEqual(info["manager"], "dnf")
        self.assertFalse(info["immutable"])

    def test_bazzite_is_immutable_and_needs_a_container(self):
        info = platform_info(
            os_release={"ID": "bazzite", "VERSION_ID": "41", "NAME": "Bazzite"},
            exists=lambda path: path == "/run/ostree-booted",
        )
        self.assertEqual(info["distro"], "bazzite")
        self.assertEqual(info["family"], "fedora")
        self.assertTrue(info["immutable"])
        self.assertIsNone(info["manager"])

    def test_docker_container_is_detected_but_keeps_its_family(self):
        info = platform_info(
            os_release={"ID": "debian", "VERSION_ID": "12", "NAME": "Debian GNU/Linux"},
            exists=lambda path: path == "/.dockerenv",
        )
        self.assertTrue(info["container"])
        self.assertEqual(info["family"], "debian")
        self.assertEqual(info["manager"], "apt-get")
        self.assertIn("Container", info["label"])

    def test_windows_uses_winget_and_reports_wsl_availability(self):
        info = platform_info(
            system="Windows",
            which=lambda name: r"C:\Windows\System32\wsl.exe" if name == "wsl.exe" else None,
        )
        self.assertEqual(info["os"], "windows")
        self.assertEqual(info["family"], "windows")
        self.assertEqual(info["manager"], "winget")
        self.assertFalse(info["wsl"])
        self.assertTrue(info["wsl_available"])

    def test_wsl_is_detected_inside_linux(self):
        info = platform_info(
            os_release={"ID": "ubuntu", "VERSION_ID": "24.04"},
            env={"WSL_DISTRO_NAME": "Ubuntu"},
        )
        self.assertEqual(info["os"], "linux")
        self.assertTrue(info["wsl"])
        self.assertEqual(info["family"], "debian")

    def test_unknown_distribution_has_no_guessed_package_manager(self):
        info = platform_info(os_release={"ID": "nixos", "NAME": "NixOS"})
        self.assertIsNone(info["family"])
        self.assertIsNone(info["manager"])


class DependencyPlanTest(unittest.TestCase):
    def ubuntu(self):
        return platform_info(os_release={"ID": "ubuntu", "VERSION_ID": "24.04"})

    def report(self, info, present=True):
        return {
            item["name"]: item
            for item in setup.dependency_report(
                info, which=(lambda name: "/usr/bin/" + name) if present else (lambda name: None)
            )
        }

    def test_present_tools_need_no_installation(self):
        info = self.ubuntu()
        report = self.report(info)
        self.assertTrue(all(item["present"] for item in report.values()))
        self.assertEqual(setup.install_commands(info, [], ["sudo"]), [])

    def test_missing_linux_tools_become_one_argument_list(self):
        info = self.ubuntu()
        report = self.report(info, present=False)
        self.assertFalse(report["tmux"]["present"])
        self.assertTrue(report["tmux"]["installable"])
        self.assertEqual(
            setup.install_commands(info, ["tmux", "flock"], ["sudo"]),
            [["sudo", "apt-get", "install", "-y", "tmux", "util-linux"]],
        )

    def test_opencode_is_reported_but_never_installed_silently(self):
        info = self.ubuntu()
        report = self.report(info, present=False)
        self.assertFalse(report["opencode"]["installable"])
        self.assertIn("opencode.ai", report["opencode"]["hint"])
        self.assertEqual(setup.install_commands(info, ["opencode"], ["sudo"]), [])

    def test_opencode_is_installed_through_npm_when_npm_is_available(self):
        info = platform_info(
            os_release={"ID": "ubuntu", "VERSION_ID": "24.04"},
            which=lambda name: "/usr/bin/npm" if name == "npm" else None,
        )
        report = {
            item["name"]: item for item in setup.dependency_report(info, which=lambda name: None)
        }
        self.assertTrue(report["opencode"]["installable"])
        self.assertEqual(
            setup.install_commands(info, ["git", "opencode"], ["sudo"]),
            [
                ["sudo", "apt-get", "install", "-y", "git"],
                ["sudo", "npm", "install", "-g", "opencode-ai"],
            ],
        )

    def test_missing_privileges_prevent_package_installation(self):
        info = self.ubuntu()
        self.assertIsNone(setup.privilege_prefix(info, is_root=False, has_sudo=False))
        self.assertEqual(setup.privilege_prefix(info, is_root=True, has_sudo=False), [])
        self.assertEqual(setup.privilege_prefix(info, is_root=False, has_sudo=True), ["sudo"])
        self.assertEqual(setup.install_commands(info, ["git"], None), [])

    def test_windows_installs_git_but_needs_wsl_for_tmux(self):
        info = platform_info(system="Windows")
        report = self.report(info, present=False)
        self.assertTrue(report["git"]["installable"])
        self.assertFalse(report["tmux"]["installable"])
        self.assertIn("WSL", report["tmux"]["hint"])
        self.assertEqual(
            setup.install_commands(info, ["git", "tmux", "flock"], []),
            [["winget", "install", "--id", "Git.Git", "-e"]],
        )

    def test_bazzite_host_is_not_layered_but_points_to_distrobox(self):
        info = platform_info(
            os_release={"ID": "bazzite"},
            exists=lambda path: path == "/run/ostree-booted",
        )
        report = self.report(info, present=False)
        self.assertFalse(report["tmux"]["installable"])
        self.assertIn("distrobox", report["tmux"]["hint"].lower())
        self.assertIn("setup-vibe.py", report["tmux"]["hint"])
        self.assertNotIn("setup-vibe.sh", report["tmux"]["hint"])
        self.assertEqual(setup.install_commands(info, ["tmux"], ["sudo"]), [])

    def test_bazzite_hint_names_an_existing_setup_script(self):
        info = platform_info(
            os_release={"ID": "bazzite"},
            exists=lambda path: path == "/run/ostree-booted",
        )
        hint = self.report(info, present=False)["tmux"]["hint"]
        self.assertIn("scripts/setup-vibe.py", hint)
        referenced = re.findall(r"[\w./-]+\.(?:py|sh)", hint)
        self.assertTrue(referenced, hint)
        for relative in referenced:
            self.assertTrue((REPO / relative).is_file(), f"{relative} fehlt im Repository")

    def test_python_version_is_checked(self):
        self.assertTrue(setup.python_ok((3, 8)))
        self.assertTrue(setup.python_ok((3, 14)))
        self.assertFalse(setup.python_ok((3, 7)))
        self.assertFalse(setup.python_ok((2, 7)))


class InstallFilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.kit = make_kit(self.root / "kit")
        self.vibe = self.root / "Mein Vibe Ordner"

    def tearDown(self):
        self.tmp.cleanup()

    def test_web_files_cover_all_shipped_web_files(self):
        """WEB_FILES installiert sämtliche Dateien aus ``bin/web``.

        AP21 v2: ``i18n.js`` muss Teil des Installationssatzes sein — ohne
        diesen fehlt ``/static/i18n.js`` im Dashboard und der Sprachumschalter
        reagiert nicht. Der Vergleich ist auf den Verzeichnisinhalt von
        ``bin/web`` (kein Datei fällt unter den Mangel).
        """
        shipped = sorted(p.name for p in (REPO / "bin" / "web").iterdir()
                         if p.is_file())
        self.assertEqual(shipped, sorted(WEB_FILES),
                         "WEB_FILES stimmt nicht mit den Dateien von bin/web überein: "
                         + repr((shipped, WEB_FILES)))

    def test_fresh_install_copies_programs_templates_and_catalog(self):
        result = setup.install_program_files(self.kit, self.vibe, mode="update", timestamp="20261026-120000")
        toolchain = self.vibe / "_toolchain"
        for name in PROGRAM_FILES:
            self.assertTrue((toolchain / "bin" / name).is_file(), name)
        for name in WEB_FILES:
            self.assertTrue((toolchain / "bin" / "web" / name).is_file(), name)
        self.assertTrue(os.access(toolchain / "bin" / "vibe", os.X_OK))
        self.assertTrue((toolchain / "templates" / "generic" / "AGENTS.md").is_file())
        self.assertTrue((toolchain / "templates" / "generic" / ".vibe" / "project.env").is_file())
        self.assertTrue((toolchain / "models.json").is_file())
        self.assertIn("bin/vibe", result["copied"])
        self.assertEqual(result["skipped"], [])

    def test_every_module_imported_by_the_launcher_is_installed(self):
        """Der Startbefehl darf nach einer Installation kein Modul vermissen."""
        launcher = launcher_sibling_modules()
        self.assertIn("vibe_autonomous", launcher)
        expected = {name + ".py" for name in launcher}
        missing = sorted(expected - set(setup.PROGRAM_FILES))
        self.assertEqual(missing, [], "Setup installiert nicht: " + ", ".join(missing))

    def test_installed_launcher_starts_with_all_options(self):
        """Reproduziert den Startfehler nach einem Update mit dem echten Quellstand."""
        setup.install_program_files(REPO, self.vibe, mode="update", timestamp="20261026-120000")
        installed = self.vibe / "_toolchain" / "bin"
        home = self.root / "home"
        home.mkdir()
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(home),
            "VIBE": str(self.vibe),
            "VIBE_NO_CONTAINER": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        result = subprocess.run(
            [sys.executable, str(installed / "vibe"), "types"],
            cwd=str(installed),
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("generic", result.stdout)

    def test_missing_catalog_is_a_warning_not_an_abort(self):
        kit = make_kit(self.root / "kit_ohne_katalog", models=False)
        result = setup.install_program_files(kit, self.vibe, mode="update", timestamp="20261026-120000")
        toolchain = self.vibe / "_toolchain"
        self.assertTrue((toolchain / "bin" / "vibe").is_file())
        self.assertFalse((toolchain / "models.json").exists())
        self.assertTrue(any("models.json" in warning for warning in result["warnings"]))

    def test_runtime_data_is_never_overwritten(self):
        toolchain = self.vibe / "_toolchain"
        toolchain.mkdir(parents=True)
        (toolchain / "vibe.json").write_text('{"roots": ["/eigenes"]}\n', encoding="utf-8")
        (toolchain / "models.json").write_text('{"models": [{"id": "lokal"}]}\n', encoding="utf-8")
        (toolchain / "profiles.json").write_text('{"profile": {"eigen": true}}\n', encoding="utf-8")
        (toolchain / "fritz.json").write_text('{"automation": true}\n', encoding="utf-8")
        logs = self.vibe / "_logs"
        logs.mkdir()
        (logs / "projekt.log").write_text("lauf\n", encoding="utf-8")

        setup.install_program_files(self.kit, self.vibe, mode="update", timestamp="20261026-120000")

        self.assertEqual((toolchain / "vibe.json").read_text(encoding="utf-8"), '{"roots": ["/eigenes"]}\n')
        self.assertEqual((toolchain / "models.json").read_text(encoding="utf-8"), '{"models": [{"id": "lokal"}]}\n')
        self.assertEqual((toolchain / "profiles.json").read_text(encoding="utf-8"), '{"profile": {"eigen": true}}\n')
        self.assertEqual((toolchain / "fritz.json").read_text(encoding="utf-8"), '{"automation": true}\n')
        self.assertEqual((logs / "projekt.log").read_text(encoding="utf-8"), "lauf\n")

    def test_reuse_keeps_existing_programs_and_only_adds_missing_ones(self):
        toolchain = self.vibe / "_toolchain"
        (toolchain / "bin").mkdir(parents=True)
        (toolchain / "bin" / "vibe").write_text("ALT\n", encoding="utf-8")

        result = setup.install_program_files(self.kit, self.vibe, mode="reuse", timestamp="20261026-120000")

        self.assertEqual((toolchain / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n")
        self.assertTrue((toolchain / "bin" / "vibe_mcp.py").is_file())
        self.assertIn("bin/vibe", result["skipped"])
        self.assertIn("bin/vibe_mcp.py", result["copied"])
        self.assertFalse((toolchain / "backup-20261026-120000").exists())

    def test_update_backs_up_changed_programs_and_templates(self):
        toolchain = self.vibe / "_toolchain"
        (toolchain / "bin").mkdir(parents=True)
        (toolchain / "bin" / "vibe").write_text("ALT\n", encoding="utf-8")
        (toolchain / "templates" / "generic").mkdir(parents=True)
        (toolchain / "templates" / "generic" / "AGENTS.md").write_text("ALTE REGEL\n", encoding="utf-8")

        result = setup.install_program_files(self.kit, self.vibe, mode="update", timestamp="20261026-120000")

        self.assertNotEqual((toolchain / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n")
        backup = toolchain / "backup-20261026-120000"
        self.assertEqual((backup / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n")
        self.assertEqual((backup / "templates" / "generic" / "AGENTS.md").read_text(encoding="utf-8"), "ALTE REGEL\n")
        self.assertIn("bin/vibe", result["backed_up"])
        self.assertIn("templates/generic/AGENTS.md", result["backed_up"])

    def test_no_temporary_files_remain(self):
        setup.install_program_files(self.kit, self.vibe, mode="update", timestamp="20261026-120000")
        leftovers = [path for path in (self.vibe / "_toolchain").rglob("*") if ".vibe-setup-" in path.name]
        self.assertEqual(leftovers, [])

    def test_unknown_mode_is_rejected_before_writing(self):
        with self.assertRaises(setup.SetupError):
            setup.install_program_files(self.kit, self.vibe, mode="kaputt", timestamp="20261026-120000")
        self.assertFalse((self.vibe / "_toolchain").exists())


class LauncherTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.vibe = self.root / "Vibe"
        self.home = self.root / "home"
        (self.vibe / "_toolchain" / "bin").mkdir(parents=True)
        (self.vibe / "_toolchain" / "bin" / "vibe").write_text("#!/bin/sh\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_posix_launcher_is_a_symlink_to_the_installed_program(self):
        result = setup.install_launcher(
            self.vibe, self.home, platform_info(os_release={"ID": "ubuntu"}), timestamp="20261026-120000"
        )
        launcher = self.home / ".local" / "bin" / "vibe"
        self.assertTrue(launcher.is_symlink())
        self.assertEqual(launcher.resolve(), (self.vibe / "_toolchain" / "bin" / "vibe").resolve())
        self.assertEqual(result["path"], str(launcher))

    def test_existing_launcher_file_is_backed_up(self):
        launcher = self.home / ".local" / "bin" / "vibe"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("ALT\n", encoding="utf-8")

        setup.install_launcher(
            self.vibe, self.home, platform_info(os_release={"ID": "ubuntu"}), timestamp="20261026-120000"
        )

        self.assertTrue(launcher.is_symlink())
        backup = launcher.with_name("vibe.bak-20261026-120000")
        self.assertEqual(backup.read_text(encoding="utf-8"), "ALT\n")

    def test_windows_launcher_starts_the_python_program(self):
        result = setup.install_launcher(
            self.vibe, self.home, platform_info(system="Windows"), timestamp="20261026-120000"
        )
        launcher = self.vibe / "vibe.cmd"
        content = launcher.read_text(encoding="utf-8")
        self.assertIn("py -3", content)
        self.assertIn("_toolchain\\bin\\vibe", content)
        self.assertFalse((self.home / ".local" / "bin" / "vibe").exists())
        self.assertEqual(result["path"], str(launcher))

    def test_windows_launcher_is_not_rewritten_on_a_second_run(self):
        setup.install_launcher(
            self.vibe, self.home, platform_info(system="Windows"), timestamp="20261026-120000"
        )
        second = setup.install_launcher(
            self.vibe, self.home, platform_info(system="Windows"), timestamp="20261026-130000"
        )
        self.assertIsNone(second["backed_up"])
        self.assertEqual(sorted(path.name for path in self.vibe.glob("vibe.cmd*")), ["vibe.cmd"])


class ProjectRegistrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vibe = Path(self.tmp.name) / "Vibe"
        self.vibe.mkdir()
        (self.vibe / "_toolchain" / "templates" / "generic" / ".vibe").mkdir(parents=True)
        (self.vibe / "_toolchain" / "templates" / "generic" / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (self.vibe / "_toolchain" / "templates" / "android" / ".vibe").mkdir(parents=True)
        (self.vibe / "_toolchain" / "templates" / "android" / ".vibe" / "project.env").write_text(
            "TYPE=android\n", encoding="utf-8"
        )
        common_agent = (
            self.vibe / "_toolchain" / "templates" / "common" / ".opencode" / "agents"
        )
        common_agent.mkdir(parents=True)
        (common_agent / "test-agent.md").write_text(
            "---\ndescription: Test-Agent\nmode: subagent\n---\n\nPrompt\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_existing_project_configuration_is_kept_and_new_projects_are_registered(self):
        existing = self.vibe / "bestand"
        (existing / ".git").mkdir(parents=True)
        (existing / ".vibe").mkdir()
        (existing / ".vibe" / "project.env").write_text("TYPE=web\n", encoding="utf-8")

        new = self.vibe / "neu"
        (new / ".git").mkdir(parents=True)

        worktree = self.vibe / "worktree"
        worktree.mkdir()
        (worktree / ".git").write_text("gitdir: /pfad\n", encoding="utf-8")

        android = self.vibe / "app"
        (android / ".git").mkdir(parents=True)
        (android / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")

        hidden = self.vibe / ".versteckt"
        (hidden / ".git").mkdir(parents=True)
        no_git = self.vibe / "ohne-git"
        no_git.mkdir()

        result = setup.register_projects(self.vibe)

        self.assertEqual((existing / ".vibe" / "project.env").read_text(encoding="utf-8"), "TYPE=web\n")
        self.assertEqual((new / ".vibe" / "project.env").read_text(encoding="utf-8"), "TYPE=generic\n")
        self.assertEqual((worktree / ".vibe" / "project.env").read_text(encoding="utf-8"), "TYPE=generic\n")
        self.assertEqual((android / ".vibe" / "project.env").read_text(encoding="utf-8"), "TYPE=android\n")
        self.assertFalse((hidden / ".vibe").exists())
        self.assertFalse((no_git / ".vibe").exists())
        names = {entry["project"] for entry in result["projects"]}
        self.assertEqual(names, {"bestand", "neu", "worktree", "app"})
        self.assertEqual(result["created"], ["app", "neu", "worktree"])

    def test_existing_and_new_projects_receive_the_test_agent(self):
        existing = self.vibe / "bestand"
        (existing / ".git").mkdir(parents=True)
        (existing / ".vibe").mkdir()
        (existing / ".vibe" / "project.env").write_text("TYPE=web\n", encoding="utf-8")
        new = self.vibe / "neu"
        (new / ".git").mkdir(parents=True)

        result = setup.register_projects(self.vibe)

        for project in (existing, new):
            agent = project / ".opencode" / "agents" / "test-agent.md"
            self.assertTrue(agent.is_file(), project)
            self.assertIn("Test-Agent", agent.read_text(encoding="utf-8"))
        # Die vorhandene Projektkonfiguration bleibt unverändert; TESTER ergänzt
        # der Projektstart, nicht die Installation.
        self.assertEqual(
            (existing / ".vibe" / "project.env").read_text(encoding="utf-8"),
            "TYPE=web\n",
        )
        self.assertEqual(result["test_agent_created"], ["bestand", "neu"])

    def test_register_projects_keeps_an_existing_test_agent(self):
        project = self.vibe / "bestand"
        (project / ".git").mkdir(parents=True)
        (project / ".vibe").mkdir()
        (project / ".vibe" / "project.env").write_text("TYPE=web\n", encoding="utf-8")
        agent = project / ".opencode" / "agents" / "test-agent.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("# eigener Test-Agent\n", encoding="utf-8")

        result = setup.register_projects(self.vibe)

        self.assertEqual(agent.read_text(encoding="utf-8"), "# eigener Test-Agent\n")
        self.assertEqual(result["test_agent_created"], [])


class TargetValidationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.kit = make_kit(self.root / "kit")
        self.home = self.root / "home"
        self.home.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_unsafe_targets_are_rejected(self):
        for bad in ("/", "/usr", "/etc", str(self.home), str(self.kit)):
            with self.assertRaises(setup.SetupError, msg=bad):
                setup.validate_target(bad, self.kit, self.home)

    def test_existing_file_as_target_is_rejected(self):
        target = self.root / "datei"
        target.write_text("x", encoding="utf-8")
        with self.assertRaises(setup.SetupError):
            setup.validate_target(str(target), self.kit, self.home)

    def test_path_with_spaces_is_accepted(self):
        target = self.root / "Mein Vibe Ordner"
        result = setup.validate_target(str(target), self.kit, self.home)
        self.assertEqual(Path(result), target.absolute())

    def test_symlink_to_system_directory_is_rejected(self):
        link = self.root / "usr-link"
        link.symlink_to("/usr", target_is_directory=True)
        with self.assertRaises(setup.SetupError):
            setup.validate_target(str(link), self.kit, self.home)


class CliFlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.kit = make_kit(self.root / "kit")
        self.vibe = self.root / "Vibe"
        self.home = self.root / "home"
        self.home.mkdir()
        self.platform = platform_info(os_release={"ID": "fedora", "VERSION_ID": "44"})
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def runner(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def run_main(self, args, answers=None, which=None, interactive=True, runner=None):
        out = io.StringIO()
        answers = answers or {}
        prompts = []
        # B17: bereinigte Umgebung ohne VIBE_*-Variablen; alle Pfade liegen
        # ausdrücklich unter dem Temp-Root des Tests.
        environ = {"HOME": str(self.home), "PATH": os.environ.get("PATH", "")}

        def input_fn(prompt):
            prompts.append(prompt)
            for needle, answer in answers.items():
                if needle in prompt:
                    return answer
            return ""

        with contextlib.redirect_stdout(out):
            code = setup.main(
                list(args) + [
                    "--install", str(self.vibe / "_toolchain"),
                    "--logs", str(self.vibe / "_logs"),
                ],
                input_fn=input_fn,
                output=lambda text="": out.write(str(text) + "\n"),
                which=which or (lambda name: None),
                runner=runner or self.runner,
                platform_info=self.platform,
                home=self.home,
                kit=self.kit,
                interactive=interactive,
                is_root=False,
                has_sudo=True,
                environ=environ,
            )
        return code, out.getvalue(), prompts

    def test_non_interactive_mode_requires_yes(self):
        code, output, _ = self.run_main(["--vibe", str(self.vibe)], interactive=False)
        self.assertEqual(code, 1)
        self.assertIn("--yes", output)
        self.assertFalse(self.vibe.exists())

    def test_dry_run_writes_nothing_and_runs_no_commands(self):
        notes = platform_info(os_release={"ID": "ubuntu"})
        out = io.StringIO()
        code = setup.main(
            ["--yes", "--dry-run", "--vibe", str(self.vibe),
             "--install", str(self.vibe / "_toolchain"),
             "--logs", str(self.vibe / "_logs")],
            output=lambda text="": out.write(str(text) + "\n"),
            which=lambda name: None,
            runner=self.runner,
            platform_info=notes,
            home=self.home,
            kit=self.kit,
            interactive=False,
            is_root=False,
            has_sudo=True,
            environ={"HOME": str(self.home), "PATH": os.environ.get("PATH", "")},
        )
        self.assertEqual(code, 0)
        self.assertFalse(self.vibe.exists())
        self.assertEqual(self.calls, [])
        self.assertIn("apt-get", out.getvalue())

    def test_declining_dependency_install_runs_no_command(self):
        code, output, _ = self.run_main(
            ["--vibe", str(self.vibe), "--no-register"],
            answers={"installieren": "n"},
        )
        self.assertEqual(code, 2)
        self.assertEqual(self.calls, [])
        self.assertTrue((self.vibe / "_toolchain" / "bin" / "vibe").is_file())
        self.assertIn("opencode.ai", output)

    def test_consent_installs_dependencies_as_argument_lists(self):
        code, output, _ = self.run_main(
            ["--vibe", str(self.vibe), "--no-register"],
            answers={"installieren": "j"},
        )
        self.assertEqual(code, 2)  # opencode bleibt manuell
        self.assertTrue(self.calls)
        command, kwargs = self.calls[0]
        self.assertIsInstance(command, list)
        self.assertEqual(command, ["sudo", "dnf", "install", "-y", "git", "tmux", "util-linux", "curl"])
        self.assertNotIn("shell", kwargs)
        self.assertTrue((self.vibe / "_toolchain" / "bin" / "vibe").is_file())

    def test_failed_package_command_is_reported(self):
        def failing(command, **kwargs):
            self.calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 1, "", "paket kaputt")

        code, output, _ = self.run_main(
            ["--vibe", str(self.vibe), "--no-register"],
            answers={"installieren": "j"},
            runner=failing,
        )
        self.assertEqual(code, 2)
        self.assertIn("endete mit Code 1", output)
        self.assertIn("paket kaputt", output)

    def test_missing_package_program_is_reported(self):
        def raising(command, **kwargs):
            self.calls.append((command, kwargs))
            raise OSError("kein Programm")

        code, output, _ = self.run_main(
            ["--vibe", str(self.vibe), "--no-register"],
            answers={"installieren": "j"},
            runner=raising,
        )
        self.assertEqual(code, 2)
        self.assertIn("FEHLER beim Start", output)

    def test_package_command_timeout_is_reported(self):
        def timing_out(command, **kwargs):
            self.calls.append((command, kwargs))
            raise subprocess.TimeoutExpired(command, 1800)

        code, output, _ = self.run_main(
            ["--vibe", str(self.vibe), "--no-register"],
            answers={"installieren": "j"},
            runner=timing_out,
        )
        self.assertEqual(code, 2)
        self.assertIn("30 Minuten", output)

    def test_install_deps_flag_works_without_terminal(self):
        code, _, _ = self.run_main(
            ["--yes", "--install-deps", "--no-register", "--vibe", str(self.vibe)],
            interactive=False,
        )
        self.assertEqual(code, 2)
        self.assertEqual(self.calls[0][0], ["sudo", "dnf", "install", "-y", "git", "tmux", "util-linux", "curl"])

    def test_successful_install_with_all_tools_returns_zero(self):
        code, output, _ = self.run_main(
            ["--yes", "--no-register", "--vibe", str(self.vibe)],
            which=lambda name: "/fake/" + name,
        )
        self.assertEqual(code, 0)
        self.assertIn("Fertig", output)
        self.assertTrue((self.vibe / "_toolchain" / "bin" / "vibe").is_file())
        self.assertEqual(self.calls, [])

    def test_abort_on_mode_question_changes_nothing(self):
        toolchain = self.vibe / "_toolchain" / "bin"
        toolchain.mkdir(parents=True)
        (toolchain / "vibe").write_text("ALT\n", encoding="utf-8")
        code, output, _ = self.run_main(
            ["--vibe", str(self.vibe)],
            answers={"Bestehende": "q"},
        )
        self.assertEqual(code, 1)
        self.assertIn("abgebrochen", output.lower())
        self.assertEqual((toolchain / "vibe").read_text(encoding="utf-8"), "ALT\n")

    def test_reuse_is_default_for_existing_installation_without_terminal(self):
        toolchain = self.vibe / "_toolchain" / "bin"
        toolchain.mkdir(parents=True)
        (toolchain / "vibe").write_text("ALT\n", encoding="utf-8")
        code, _, _ = self.run_main(
            ["--yes", "--no-register", "--vibe", str(self.vibe)],
            which=lambda name: "/fake/" + name,
            interactive=False,
        )
        self.assertEqual(code, 0)
        self.assertEqual((toolchain / "vibe").read_text(encoding="utf-8"), "ALT\n")


class WrapperTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.vibe = self.root / "Vibe"
        self.home = self.root / "home"
        self.home.mkdir()
        self.fakebin = self.root / "fakebin"
        self.fakebin.mkdir()
        for name in ("git", "tmux", "flock", "curl", "opencode"):
            path = self.fakebin / name
            path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            path.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_vibe_sh_uses_the_python_setup(self):
        env = os.environ.copy()
        # B17: Der Wrapper startet den echten Setup. Erbte der Test eine
        # Produktivumgebung, würde install-vibe.sh die reale Installation
        # aktualisieren. Deshalb ausschließlich Temp-Pfade übergeben.
        for key in (
            "VIBE", "VIBE_PROFILE", "VIBE_INSTALL", "VIBE_STATE",
            "VIBE_RUNTIME", "VIBE_CONFIG_FILE", "VIBE_AGENTS_DIR",
        ):
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(self.vibe),
                "HOME": str(self.home),
                "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
            }
        )
        env.pop("VIBE_NO_CONTAINER", None)
        result = subprocess.run(
            ["bash", str(WRAPPER)],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.vibe / "_toolchain" / "bin" / "vibe").is_file())
        self.assertTrue((self.home / ".local" / "bin" / "vibe").is_symlink())

    def test_windows_wrapper_bootstraps_python_and_calls_the_setup(self):
        self.assertTrue(CMD_WRAPPER.is_file())
        content = CMD_WRAPPER.read_text(encoding="utf-8")
        self.assertIn("py -3", content)
        self.assertIn("scripts\\setup-vibe.py", content)
        self.assertIn("winget install", content)


if __name__ == "__main__":
    unittest.main()
