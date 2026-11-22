"""Tests für Installation, Aktualisierung, Rollback und Uninstall (V-018).

Alle schreibenden Tests arbeiten ausschließlich in temporären Verzeichnissen.
Es werden keine Paketmanager, Router oder echten Installationen angefasst.
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SETUP = REPO / "scripts" / "setup-vibe.py"

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

setup = None


def setUpModule():
    global setup
    loader = importlib.machinery.SourceFileLoader("setup_vibe_lifecycle", str(SETUP))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    setup = module


def make_kit(root, version="0.18.0"):
    """Baut ein minimales Repository-Abbild mit Versionsdatei."""
    root = Path(root)
    (root / "bin").mkdir(parents=True)
    for name in PROGRAM_FILES:
        path = root / "bin" / name
        path.write_text(f"#!/usr/bin/env python3\n# {name}\n", encoding="utf-8")
    (root / "bin" / "web").mkdir()
    for name in WEB_FILES:
        (root / "bin" / "web" / name).write_text(f"/* {name} */\n", encoding="utf-8")
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    templates = root / "templates" / "generic" / ".vibe"
    templates.mkdir(parents=True)
    (templates / "project.env").write_text("TYPE=generic\n", encoding="utf-8")
    (root / "templates" / "generic" / "AGENTS.md").write_text("# generic\n", encoding="utf-8")
    (root / "data").mkdir()
    (root / "data" / "models.json").write_text('{"models": []}\n', encoding="utf-8")
    return root


def platform_info(**overrides):
    base = {
        "system": "Linux",
        "os_release": {"ID": "fedora", "VERSION_ID": "44"},
        "exists": lambda path: False,
        "env": {},
        "proc_version": "",
        "which": lambda name: None,
    }
    base.update(overrides)
    return setup.detect_platform(**base)


class InstallLifecycleBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.kit = make_kit(self.root / "kit")
        self.vibe = self.root / "Vibe"
        self.toolchain = self.vibe / "_toolchain"
        self.home = self.root / "home"
        self.home.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, mode="update", timestamp="20261101-120000", kit=None):
        return setup.install_program_files(
            kit or self.kit, self.vibe, mode=mode, timestamp=timestamp
        )

    def run_main(self, args, interactive=False, which=None, runner=None):
        out = io.StringIO()
        # B17: bereinigte Umgebung ohne VIBE_*-Variablen und explizite
        # Temp-Pfade für Installation und Laufzeit.
        environ = {"HOME": str(self.home), "PATH": os.environ.get("PATH", "")}
        code = setup.main(
            list(args) + [
                "--install", str(self.toolchain),
                "--logs", str(self.vibe / "_logs"),
            ],
            output=lambda text="": out.write(str(text) + "\n"),
            which=which or (lambda name: None),
            runner=runner or (lambda command, **kwargs: subprocess.CompletedProcess(command, 1, "", "")),
            platform_info=platform_info(),
            home=self.home,
            kit=self.kit,
            interactive=interactive,
            is_root=False,
            has_sudo=False,
            environ=environ,
        )
        return code, out.getvalue()


class VersionTest(InstallLifecycleBase):
    def test_kit_version_and_commit_are_read_from_the_repository(self):
        info = setup.read_kit_version(self.kit)
        self.assertEqual(info["version"], "0.18.0")
        self.assertIsNone(info["commit"])

    def test_update_records_version_commit_and_source(self):
        self.install()
        recorded = json.loads((self.toolchain / "version.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded["version"], "0.18.0")
        self.assertEqual(recorded["mode"], "update")
        self.assertEqual(Path(recorded["source"]), self.kit.resolve())

    def test_missing_version_file_is_reported_as_unknown_not_guessed(self):
        (self.kit / "VERSION").unlink()
        info = setup.read_kit_version(self.kit)
        self.assertEqual(info["version"], "unbekannt")
        self.assertIsNone(info["commit"])

    def test_repository_ships_a_concrete_version_file(self):
        version_file = REPO / "VERSION"
        self.assertTrue(version_file.is_file(), "VERSION fehlt im Repository")
        info = setup.read_kit_version(REPO)
        self.assertRegex(info["version"], r"^\d+\.\d+\.\d+$")
        self.assertNotEqual(info["version"], "unbekannt")


class PreviewTest(InstallLifecycleBase):
    def test_plan_lists_new_changed_and_unchanged_files(self):
        self.toolchain.mkdir(parents=True)
        (self.toolchain / "bin").mkdir()
        (self.toolchain / "bin" / "vibe").write_text("ALT\n", encoding="utf-8")
        (self.toolchain / "bin" / "vibe_questions.py").write_text(
            (self.kit / "bin" / "vibe_questions.py").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (self.toolchain / "models.json").write_text('{"models": [{"id": "lokal"}]}\n', encoding="utf-8")

        plan = setup.build_install_plan(self.kit, self.vibe, mode="update")
        actions = {entry["path"]: entry["action"] for entry in plan["files"]}
        self.assertEqual(actions["bin/vibe"], "backup")
        self.assertEqual(actions["bin/vibe_questions.py"], "skip")
        self.assertEqual(actions["bin/vibe_storage.py"], "copy")
        self.assertEqual(actions["models.json"], "skip")
        self.assertEqual(plan["version"]["from"], None)
        self.assertEqual(plan["version"]["to"]["version"], "0.18.0")

    def test_preview_does_not_write_anything(self):
        code, output = self.run_main(["--yes", "--preview", "--vibe", str(self.vibe)])
        self.assertEqual(code, 0)
        self.assertIn("Vorschau", output)
        self.assertIn("bin/vibe", output)
        self.assertIn("Version", output)
        self.assertFalse(self.vibe.exists())

    def test_preview_works_while_a_run_is_live(self):
        runtime = self.vibe / "_logs"
        runtime.mkdir(parents=True)
        (runtime / "runs.json").write_text(
            json.dumps({"runs": [{"id": "lauf-1", "state": "running"}]}), encoding="utf-8"
        )
        code, output = self.run_main(["--yes", "--preview", "--vibe", str(self.vibe)])
        self.assertEqual(code, 0)
        self.assertIn("Vorschau", output)


class FreshInstallTest(InstallLifecycleBase):
    def test_fresh_install_copies_all_program_modules_and_writes_version(self):
        self.assertEqual(
            set(PROGRAM_FILES),
            set(setup.PROGRAM_FILES),
            "Testabbild und Setup müssen dieselben Programmmodule kennen",
        )
        result = self.install()
        for name in PROGRAM_FILES:
            self.assertTrue((self.toolchain / "bin" / name).is_file(), name)
        for name in WEB_FILES:
            self.assertTrue((self.toolchain / "bin" / "web" / name).is_file(), name)
        self.assertTrue((self.toolchain / "templates" / "generic" / "AGENTS.md").is_file())
        self.assertTrue((self.toolchain / "models.json").is_file())
        self.assertTrue((self.toolchain / "version.json").is_file())
        self.assertEqual(
            len(result["copied"]), len(PROGRAM_FILES) + len(WEB_FILES) + 3
        )

    def test_verify_installation_reports_a_missing_web_asset(self):
        self.install()
        (self.toolchain / "bin" / "web" / "app.js").unlink()

        failed = [
            check["label"]
            for check in setup.verify_installation(self.vibe)
            if not check["ok"]
        ]

        self.assertIn("Webdatei bin/web/app.js", failed)

    def test_fresh_install_keeps_existing_runtime_data(self):
        self.toolchain.mkdir(parents=True)
        (self.toolchain / "vibe.json").write_text('{"roots": ["/eigenes"]}\n', encoding="utf-8")
        (self.toolchain / "models.json").write_text('{"models": [{"id": "lokal"}]}\n', encoding="utf-8")
        (self.toolchain / "profiles.json").write_text('{"profile": {"eigen": true}}\n', encoding="utf-8")
        logs = self.vibe / "_logs"
        logs.mkdir()
        (logs / "projekt.log").write_text("lauf\n", encoding="utf-8")

        self.install()

        self.assertEqual((self.toolchain / "vibe.json").read_text(encoding="utf-8"), '{"roots": ["/eigenes"]}\n')
        self.assertEqual((self.toolchain / "models.json").read_text(encoding="utf-8"), '{"models": [{"id": "lokal"}]}\n')
        self.assertEqual((self.toolchain / "profiles.json").read_text(encoding="utf-8"), '{"profile": {"eigen": true}}\n')
        self.assertEqual((logs / "projekt.log").read_text(encoding="utf-8"), "lauf\n")


class UpdateTest(InstallLifecycleBase):
    def prepare_old_install(self):
        self.install(timestamp="20261101-100000")
        (self.toolchain / "bin" / "vibe").write_text("ALT\n", encoding="utf-8")
        (self.toolchain / "templates" / "generic" / "AGENTS.md").write_text(
            "# eigene Regel\n", encoding="utf-8"
        )
        (self.toolchain / "vibe.json").write_text('{"roots": ["/eigenes"]}\n', encoding="utf-8")
        (self.toolchain / "models.json").write_text('{"models": [{"id": "lokal"}]}\n', encoding="utf-8")

    def test_update_backs_up_program_and_user_template_and_keeps_runtime(self):
        self.prepare_old_install()
        result = self.install(timestamp="20261101-130000")
        backup = self.toolchain / "backup-20261101-130000"
        self.assertEqual((backup / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n")
        self.assertEqual(
            (backup / "templates" / "generic" / "AGENTS.md").read_text(encoding="utf-8"),
            "# eigene Regel\n",
        )
        self.assertNotEqual((self.toolchain / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n")
        self.assertEqual(
            (self.toolchain / "templates" / "generic" / "AGENTS.md").read_text(encoding="utf-8"),
            "# generic\n",
        )
        self.assertEqual((self.toolchain / "vibe.json").read_text(encoding="utf-8"), '{"roots": ["/eigenes"]}\n')
        self.assertEqual((self.toolchain / "models.json").read_text(encoding="utf-8"), '{"models": [{"id": "lokal"}]}\n')
        meta = json.loads((backup / "backup.json").read_text(encoding="utf-8"))
        self.assertIn("bin/vibe", meta["backed_up"])
        self.assertIn("templates/generic/AGENTS.md", meta["backed_up"])
        self.assertEqual(meta["version_before"]["version"], "0.18.0")

    def test_reuse_on_an_empty_target_records_the_version(self):
        self.install(mode="reuse", timestamp="20261101-141500")
        recorded = json.loads((self.toolchain / "version.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded["version"], "0.18.0")
        self.assertEqual(recorded["mode"], "reuse")
        self.assertEqual(
            [check["label"] for check in setup.verify_installation(self.vibe) if not check["ok"]],
            [],
        )

    def test_reuse_keeps_user_templates_and_programs(self):
        self.prepare_old_install()
        self.install(mode="reuse", timestamp="20261101-140000")
        self.assertEqual((self.toolchain / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n")
        self.assertEqual(
            (self.toolchain / "templates" / "generic" / "AGENTS.md").read_text(encoding="utf-8"),
            "# eigene Regel\n",
        )
        self.assertFalse((self.toolchain / "backup-20261101-140000").exists())

    def test_update_without_changed_files_still_records_the_new_version(self):
        self.install(timestamp="20261101-100000")
        kit = make_kit(self.root / "kit-neu", version="0.19.0")
        self.install(kit=kit, timestamp="20261101-150000")
        recorded = json.loads((self.toolchain / "version.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded["version"], "0.19.0")
        backup = self.toolchain / "backup-20261101-150000"
        self.assertTrue((backup / "backup.json").is_file())


class AbortTest(InstallLifecycleBase):
    def prepare_old_install(self):
        self.install(timestamp="20261101-100000")
        (self.toolchain / "bin" / "vibe").write_text("ALT\n", encoding="utf-8")
        (self.toolchain / "templates" / "generic" / "AGENTS.md").write_text(
            "# eigene Regel\n", encoding="utf-8"
        )

    def test_aborted_update_restores_previous_files_and_keeps_backup(self):
        self.prepare_old_install()
        original_copy = setup._copy_file
        calls = {"count": 0}

        def failing(source, destination):
            calls["count"] += 1
            if calls["count"] == 2:
                raise PermissionError("keine Rechte")
            return original_copy(source, destination)

        setup._copy_file = failing
        try:
            with self.assertRaises(setup.SetupError) as caught:
                self.install(timestamp="20261101-160000")
        finally:
            setup._copy_file = original_copy

        self.assertIn("wiederhergestellt", str(caught.exception))
        self.assertEqual((self.toolchain / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n")
        self.assertEqual(
            (self.toolchain / "templates" / "generic" / "AGENTS.md").read_text(encoding="utf-8"),
            "# eigene Regel\n",
        )
        self.assertTrue((self.toolchain / "backup-20261101-160000" / "backup.json").is_file())

    def test_backup_failure_is_reported_as_setup_error_and_changes_nothing(self):
        self.prepare_old_install()
        original = setup._backup_file

        def denied(*args, **kwargs):
            raise PermissionError("keine Rechte")

        setup._backup_file = denied
        try:
            with self.assertRaises(setup.SetupError) as caught:
                self.install(timestamp="20261101-175000")
        finally:
            setup._backup_file = original

        self.assertIn("Sicherung", str(caught.exception))
        self.assertEqual((self.toolchain / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n")
        self.assertFalse((self.toolchain / "backup-20261101-175000").exists())

    def test_launcher_failure_restores_the_previous_installation(self):
        self.prepare_old_install()
        old_version = (self.toolchain / "version.json").read_text(encoding="utf-8")
        original = setup.install_launcher

        def denied(*args, **kwargs):
            raise setup.SetupError("Startbefehl konnte nicht angelegt werden")

        setup.install_launcher = denied
        try:
            code, output = self.run_main(
                ["--yes", "--update", "--vibe", str(self.vibe)],
                which=lambda name: "/fake/" + name,
            )
        finally:
            setup.install_launcher = original

        self.assertEqual(code, 1)
        self.assertIn("wiederhergestellt", output)
        self.assertEqual((self.toolchain / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n")
        self.assertEqual(
            (self.toolchain / "templates" / "generic" / "AGENTS.md").read_text(encoding="utf-8"),
            "# eigene Regel\n",
        )
        self.assertEqual(
            (self.toolchain / "version.json").read_text(encoding="utf-8"), old_version
        )

    def test_reuse_failure_keeps_the_version_of_an_untouched_installation(self):
        self.install(timestamp="20261101-100000")
        old_version = (self.toolchain / "version.json").read_text(encoding="utf-8")
        original = setup.install_launcher

        def denied(*args, **kwargs):
            raise setup.SetupError("Startbefehl konnte nicht angelegt werden")

        setup.install_launcher = denied
        try:
            code, output = self.run_main(
                ["--yes", "--reuse", "--vibe", str(self.vibe)],
                which=lambda name: "/fake/" + name,
            )
        finally:
            setup.install_launcher = original

        self.assertEqual(code, 1)
        self.assertIn("nichts geändert", output)
        self.assertEqual(
            (self.toolchain / "version.json").read_text(encoding="utf-8"), old_version
        )

    def test_launcher_failure_on_a_fresh_install_removes_the_partial_installation(self):
        original = setup.install_launcher

        def denied(*args, **kwargs):
            raise setup.SetupError("Startbefehl konnte nicht angelegt werden")

        setup.install_launcher = denied
        try:
            code, output = self.run_main(
                ["--yes", "--update", "--vibe", str(self.vibe), "--no-register"],
                which=lambda name: "/fake/" + name,
            )
        finally:
            setup.install_launcher = original

        self.assertEqual(code, 1)
        self.assertIn("nichts geändert", output)
        self.assertFalse((self.toolchain / "version.json").exists())
        self.assertFalse((self.toolchain / "bin" / "vibe").exists())
        self.assertFalse((self.toolchain / "bin" / "web" / "app.js").exists())
        self.assertFalse((self.toolchain / "bin" / "web").exists())
        self.assertFalse((self.toolchain / "templates").exists())
        self.assertFalse(self.toolchain.exists(), "leerer _toolchain-Ordner bleibt zurück")

    def test_missing_permissions_do_not_leave_a_partial_install(self):
        self.prepare_old_install()
        original_copy = setup._copy_file

        def denied(source, destination):
            raise PermissionError("keine Rechte")

        setup._copy_file = denied
        try:
            with self.assertRaises(setup.SetupError):
                self.install(timestamp="20261101-170000")
        finally:
            setup._copy_file = original_copy

        self.assertEqual((self.toolchain / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n")
        recorded = json.loads((self.toolchain / "version.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded["version"], "0.18.0")


class RollbackTest(InstallLifecycleBase):
    def test_rollback_restores_programs_templates_and_version(self):
        self.install(timestamp="20261101-100000")
        old_version = (self.toolchain / "version.json").read_text(encoding="utf-8")
        (self.toolchain / "bin" / "vibe").write_text("ALT\n", encoding="utf-8")
        (self.toolchain / "templates" / "generic" / "AGENTS.md").write_text(
            "# eigene Regel\n", encoding="utf-8"
        )
        (self.toolchain / "vibe.json").write_text('{"roots": ["/eigenes"]}\n', encoding="utf-8")

        kit = make_kit(self.root / "kit-neu", version="0.19.0")
        (kit / "templates" / "generic" / "NEU.md").write_text("# neu\n", encoding="utf-8")
        self.install(kit=kit, timestamp="20261101-180000")
        self.assertTrue((self.toolchain / "templates" / "generic" / "NEU.md").is_file())
        report = setup.rollback(self.vibe)

        self.assertEqual((self.toolchain / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n")
        self.assertEqual(
            (self.toolchain / "templates" / "generic" / "AGENTS.md").read_text(encoding="utf-8"),
            "# eigene Regel\n",
        )
        self.assertFalse((self.toolchain / "templates" / "generic" / "NEU.md").exists())
        self.assertEqual((self.toolchain / "version.json").read_text(encoding="utf-8"), old_version)
        self.assertEqual((self.toolchain / "vibe.json").read_text(encoding="utf-8"), '{"roots": ["/eigenes"]}\n')
        self.assertEqual(report["backup"], "backup-20261101-180000")

    def test_rollback_without_backup_fails_without_changes(self):
        self.install(timestamp="20261101-100000")
        before = (self.toolchain / "bin" / "vibe").read_text(encoding="utf-8")
        with self.assertRaises(setup.SetupError):
            setup.rollback(self.vibe)
        self.assertEqual((self.toolchain / "bin" / "vibe").read_text(encoding="utf-8"), before)

    def test_cli_rollback_restores_the_previous_installation(self):
        self.install(timestamp="20261101-100000")
        (self.toolchain / "bin" / "vibe").write_text("ALT\n", encoding="utf-8")
        self.install(timestamp="20261101-190000")
        code, output = self.run_main(["--yes", "--rollback", "--vibe", str(self.vibe)])
        self.assertEqual(code, 0)
        self.assertIn("Rollback", output)
        self.assertEqual((self.toolchain / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n")

    def test_rollback_refuses_while_a_run_is_live(self):
        self.install(timestamp="20261101-100000")
        (self.toolchain / "bin" / "vibe").write_text("ALT\n", encoding="utf-8")
        self.install(timestamp="20261101-110000")
        (self.toolchain / "bin" / "vibe").write_text("LAUFEND\n", encoding="utf-8")
        runtime = self.vibe / "_logs"
        runtime.mkdir(exist_ok=True)
        (runtime / "runs.json").write_text(
            json.dumps({"runs": [{"id": "lauf-2", "state": "running"}]}), encoding="utf-8"
        )

        code, output = self.run_main(["--yes", "--rollback", "--vibe", str(self.vibe)])

        self.assertEqual(code, 1)
        self.assertIn("wird gerade verwendet", output)
        self.assertEqual(
            (self.toolchain / "bin" / "vibe").read_text(encoding="utf-8"), "LAUFEND\n"
        )

    def test_select_backup_orders_numeric_suffixes_numerically(self):
        self.install(timestamp="20261101-100000")
        for suffix in ("2", "10"):
            backup = self.toolchain / f"backup-20261101-100000-{suffix}"
            backup.mkdir()

        chosen = setup.select_backup(self.vibe)

        self.assertEqual(chosen.name, "backup-20261101-100000-10")

    def test_select_backup_ignores_uninstall_backups(self):
        self.install(timestamp="20261101-100000")
        (self.toolchain / "backup-20261101-100000").mkdir()
        leftover = self.toolchain / "backup-uninstall-20261231-235959"
        (leftover / "templates" / "generic").mkdir(parents=True)
        (leftover / "templates" / "generic" / "AGENTS.md").write_text("# alt\n", encoding="utf-8")

        chosen = setup.select_backup(self.vibe)

        self.assertEqual(chosen.name, "backup-20261101-100000")

    def test_rollback_rejects_a_backup_with_parent_paths(self):
        self.install(timestamp="20261101-100000")
        backup = self.toolchain / "backup-20261101-200000"
        backup.mkdir()
        (backup / "backup.json").write_text(
            json.dumps({"backed_up": ["../ausserhalb.txt"], "created": []}),
            encoding="utf-8",
        )
        outside = self.vibe / "ausserhalb.txt"
        outside.write_text("original\n", encoding="utf-8")

        with self.assertRaises(setup.SetupError):
            setup.rollback(self.vibe)

        self.assertEqual(outside.read_text(encoding="utf-8"), "original\n")


class UninstallTest(InstallLifecycleBase):
    def test_uninstall_removes_programs_and_templates_but_keeps_runtime_and_projects(self):
        self.install(timestamp="20261101-100000")
        (self.toolchain / "vibe.json").write_text('{"roots": ["/eigenes"]}\n', encoding="utf-8")
        (self.toolchain / "models.json").write_text('{"models": [{"id": "lokal"}]}\n', encoding="utf-8")
        (self.toolchain / "costs.json").write_text("{}\n", encoding="utf-8")
        project = self.vibe / "mein-projekt"
        project.mkdir()
        (project / "README.md").write_text("projekt\n", encoding="utf-8")
        logs = self.vibe / "_logs"
        logs.mkdir()
        (logs / "projekt.log").write_text("lauf\n", encoding="utf-8")

        report = setup.uninstall(self.vibe)

        self.assertFalse((self.toolchain / "bin" / "vibe").exists())
        self.assertFalse((self.toolchain / "templates").exists())
        self.assertFalse((self.toolchain / "version.json").exists())
        self.assertEqual((self.toolchain / "vibe.json").read_text(encoding="utf-8"), '{"roots": ["/eigenes"]}\n')
        self.assertEqual((self.toolchain / "models.json").read_text(encoding="utf-8"), '{"models": [{"id": "lokal"}]}\n')
        self.assertEqual((self.toolchain / "costs.json").read_text(encoding="utf-8"), "{}\n")
        self.assertEqual((project / "README.md").read_text(encoding="utf-8"), "projekt\n")
        self.assertEqual((logs / "projekt.log").read_text(encoding="utf-8"), "lauf\n")
        self.assertIn("vibe.json", report["kept"])

    def test_uninstall_requires_yes_without_terminal(self):
        self.install()
        code, output = self.run_main(["--uninstall", "--vibe", str(self.vibe)])
        self.assertEqual(code, 1)
        self.assertIn("--yes", output)
        self.assertTrue((self.toolchain / "bin" / "vibe").is_file())

    def test_uninstall_removes_only_its_own_launcher_symlink(self):
        self.install()
        launcher = self.home / ".local" / "bin" / "vibe"
        launcher.parent.mkdir(parents=True)
        launcher.symlink_to(self.toolchain / "bin" / "vibe")
        other = self.home / ".local" / "bin" / "anderes"
        other.symlink_to(self.root / "irgendwo")

        report = setup.uninstall(self.vibe, home=self.home, remove_launcher=True)

        self.assertFalse(launcher.is_symlink())
        self.assertTrue(other.is_symlink())
        self.assertIn(str(launcher), report["launchers"])

    def test_uninstall_reports_every_removed_launcher(self):
        self.install()
        launcher = self.home / ".local" / "bin" / "vibe"
        launcher.parent.mkdir(parents=True)
        launcher.symlink_to(self.toolchain / "bin" / "vibe")
        command = self.vibe / "vibe.cmd"
        command.write_text("vibe\n", encoding="utf-8")

        report = setup.uninstall(self.vibe, home=self.home, remove_launcher=True)

        self.assertFalse(launcher.is_symlink())
        self.assertFalse(command.exists())
        self.assertEqual(
            sorted(report["launchers"]), sorted([str(launcher), str(command)])
        )

    def test_uninstall_backs_up_changed_templates_before_removal(self):
        self.install(timestamp="20261101-100000")
        edited = self.toolchain / "templates" / "generic" / "AGENTS.md"
        edited.write_text("# eigene Regel\n", encoding="utf-8")

        report = setup.uninstall(self.vibe, timestamp="20261102-090000")

        self.assertFalse((self.toolchain / "templates").exists())
        backup = Path(report["backup"])
        self.assertEqual(backup.name, "backup-uninstall-20261102-090000")
        self.assertEqual(
            (backup / "templates" / "generic" / "AGENTS.md").read_text(encoding="utf-8"),
            "# eigene Regel\n",
        )
        self.assertEqual(
            (backup / "templates" / "generic" / ".vibe" / "project.env").read_text(encoding="utf-8"),
            "TYPE=generic\n",
        )

    def test_uninstall_does_nothing_for_a_missing_installation(self):
        report = setup.uninstall(self.vibe)
        self.assertTrue(report["missing"])
        self.assertEqual(report["removed"], [])

    def test_uninstall_preview_does_not_require_yes(self):
        self.install()
        code, output = self.run_main(["--uninstall", "--dry-run", "--vibe", str(self.vibe)])
        self.assertEqual(code, 0)
        self.assertIn("dry-run", output)
        self.assertTrue((self.toolchain / "bin" / "vibe").is_file())

    def test_uninstall_refuses_while_a_run_is_live(self):
        self.install()
        runtime = self.vibe / "_logs"
        runtime.mkdir(exist_ok=True)
        (runtime / "runs.json").write_text(
            json.dumps({"runs": [{"id": "lauf-3", "state": "running"}]}), encoding="utf-8"
        )

        code, output = self.run_main(["--yes", "--uninstall", "--vibe", str(self.vibe)])

        self.assertEqual(code, 1)
        self.assertIn("wird gerade verwendet", output)
        self.assertTrue((self.toolchain / "bin" / "vibe").is_file())


class RunningGuardTest(InstallLifecycleBase):
    def write_runs(self, records):
        runtime = self.vibe / "_logs"
        runtime.mkdir(exist_ok=True)
        (runtime / "runs.json").write_text(
            json.dumps({"runs": records}), encoding="utf-8"
        )

    def tmux_check(self, live_sessions=()):
        """Fake-tmux: nur die genannten Sitzungen gelten als vorhanden.

        Alle Werkzeuge gelten als vorhanden, damit die Werkzeugprüfung des
        Setups nicht vor der Installationssperre abbricht. Die eigentliche
        Sitzungsprüfung steuert ausschließlich ``runner``.
        """
        live = set(live_sessions)

        def which(name):
            return "/fake/" + name

        def runner(command, **kwargs):
            exists = "has-session" in command and command[-1] in live
            return subprocess.CompletedProcess(command, 0 if exists else 1, "", "")

        return which, runner

    def test_update_refuses_while_a_run_is_live(self):
        self.install(timestamp="20261101-100000")
        (self.toolchain / "bin" / "vibe").write_text("ALT\n", encoding="utf-8")
        self.write_runs(
            [
                {
                    "id": "lauf-1",
                    "state": "running",
                    "session": "vibe-lauf-1",
                    "project": str(self.root / "proj"),
                }
            ]
        )
        which, runner = self.tmux_check({"vibe-lauf-1"})

        code, output = self.run_main(
            ["--yes", "--update", "--vibe", str(self.vibe)],
            which=which,
            runner=runner,
        )

        self.assertEqual(code, 1, output)
        self.assertIn("wird gerade verwendet", output)
        self.assertIn("lauf-1", output)
        self.assertEqual((self.toolchain / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n")

    def test_update_refuses_while_a_starting_run_is_live(self):
        self.install(timestamp="20261101-100000")
        (self.toolchain / "bin" / "vibe").write_text("ALT\n", encoding="utf-8")
        self.write_runs(
            [
                {
                    "id": "lauf-start",
                    "state": "starting",
                    "session": "vibe-lauf-start",
                    "project": str(self.root / "proj"),
                }
            ]
        )
        which, runner = self.tmux_check({"vibe-lauf-start"})

        code, output = self.run_main(
            ["--yes", "--update", "--vibe", str(self.vibe)],
            which=which,
            runner=runner,
        )

        self.assertEqual(code, 1, output)
        self.assertIn("wird gerade verwendet", output)
        self.assertIn("lauf-start", output)
        self.assertEqual((self.toolchain / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n")

    def test_update_proceeds_when_a_running_record_has_no_session(self):
        self.install(timestamp="20261101-100000")
        (self.toolchain / "bin" / "vibe").write_text("ALT\n", encoding="utf-8")
        self.write_runs(
            [
                {
                    "id": "lauf-weg",
                    "state": "running",
                    "session": "vibe-lauf-weg",
                    "project": str(self.root / "proj"),
                }
            ]
        )
        which, runner = self.tmux_check()

        code, output = self.run_main(
            ["--yes", "--update", "--vibe", str(self.vibe)],
            which=which,
            runner=runner,
        )

        self.assertEqual(code, 0, output)
        self.assertNotIn("wird gerade verwendet", output)
        self.assertNotEqual(
            (self.toolchain / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n"
        )

    def test_update_proceeds_when_a_starting_record_has_no_session(self):
        self.install(timestamp="20261101-100000")
        (self.toolchain / "bin" / "vibe").write_text("ALT\n", encoding="utf-8")
        self.write_runs(
            [
                {
                    "id": "lauf-start-weg",
                    "state": "starting",
                    "session": "vibe-lauf-start-weg",
                    "project": str(self.root / "proj"),
                }
            ]
        )
        which, runner = self.tmux_check()

        code, output = self.run_main(
            ["--yes", "--update", "--vibe", str(self.vibe)],
            which=which,
            runner=runner,
        )

        self.assertEqual(code, 0, output)
        self.assertNotIn("wird gerade verwendet", output)
        self.assertNotEqual(
            (self.toolchain / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n"
        )

    def test_update_refuses_conservatively_when_tmux_is_unavailable(self):
        self.install(timestamp="20261101-100000")
        (self.toolchain / "bin" / "vibe").write_text("ALT\n", encoding="utf-8")
        self.write_runs(
            [
                {
                    "id": "lauf-1",
                    "state": "running",
                    "session": "vibe-lauf-1",
                    "project": str(self.root / "proj"),
                }
            ]
        )

        code, output = self.run_main(
            ["--yes", "--update", "--vibe", str(self.vibe)],
            which=lambda name: None,
        )

        self.assertEqual(code, 1, output)
        self.assertIn("wird gerade verwendet", output)
        self.assertEqual((self.toolchain / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n")

    def test_update_refuses_when_the_run_state_is_unreadable(self):
        self.install(timestamp="20261101-100000")
        (self.toolchain / "bin" / "vibe").write_text("ALT\n", encoding="utf-8")
        runtime = self.vibe / "_logs"
        runtime.mkdir(exist_ok=True)
        (runtime / "runs.json").write_text("{kein json", encoding="utf-8")

        code, output = self.run_main(["--yes", "--update", "--vibe", str(self.vibe)])

        self.assertEqual(code, 1)
        self.assertIn("nicht lesbar", output)
        self.assertEqual((self.toolchain / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n")

    def test_force_allows_the_update_of_a_running_installation(self):
        self.install(timestamp="20261101-100000")
        (self.toolchain / "bin" / "vibe").write_text("ALT\n", encoding="utf-8")
        runtime = self.vibe / "_logs"
        runtime.mkdir(exist_ok=True)
        (runtime / "runs.json").write_text(
            json.dumps({"runs": [{"id": "lauf-1", "state": "running"}]}), encoding="utf-8"
        )

        code, output = self.run_main(
            ["--yes", "--update", "--force", "--vibe", str(self.vibe)],
            which=lambda name: "/fake/" + name,
        )

        self.assertEqual(code, 0)
        self.assertNotEqual((self.toolchain / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n")

    def test_force_bypasses_the_guard_of_a_live_session(self):
        self.install(timestamp="20261101-100000")
        (self.toolchain / "bin" / "vibe").write_text("ALT\n", encoding="utf-8")
        self.write_runs(
            [
                {
                    "id": "lauf-live",
                    "state": "running",
                    "session": "vibe-lauf-live",
                    "project": str(self.root / "proj"),
                }
            ]
        )
        which, runner = self.tmux_check({"vibe-lauf-live"})

        blocked, blocked_output = self.run_main(
            ["--yes", "--update", "--vibe", str(self.vibe)],
            which=which,
            runner=runner,
        )

        self.assertEqual(blocked, 1, blocked_output)
        self.assertIn("wird gerade verwendet", blocked_output)
        self.assertEqual(
            (self.toolchain / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n"
        )

        forced, forced_output = self.run_main(
            ["--yes", "--update", "--force", "--vibe", str(self.vibe)],
            which=which,
            runner=runner,
        )

        self.assertEqual(forced, 0, forced_output)
        self.assertNotEqual(
            (self.toolchain / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n"
        )


if __name__ == "__main__":
    unittest.main()
