"""Installationslebenszyklus: Update, Deinstallation und Rollback bei leerem Laufregister sowie Isolation.

Aufruf: python3 -m unittest tests.unit.test_install_lifecycle -v
"""


def setUpModule():
    global setup
    loader = importlib.machinery.SourceFileLoader("setup_vibe_lifecycle", str(SETUP))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    setup = module
    # Eindeutiger Modulname: nicht mit test_install_lifecycle.py kollidieren.
    loader = importlib.machinery.SourceFileLoader("setup_vibe_b4", str(SETUP))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    setup = module
    loader = importlib.machinery.SourceFileLoader("setup_vibe_b17", str(SETUP))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    setup = module


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
    # F33: Web-Dateien-Einträge auf den Stand von scripts/setup-vibe.py bringen.
    "nova-widgets.js", "vibe.svg",
)

setup = None


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
            kit or self.kit, self.toolchain, mode=mode, timestamp=timestamp
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

        plan = setup.build_install_plan(self.kit, self.toolchain, mode="update")
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
            for check in setup.verify_installation(self.toolchain)
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
            [check["label"] for check in setup.verify_installation(self.toolchain) if not check["ok"]],
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
        report = setup.rollback(self.toolchain)

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
            setup.rollback(self.toolchain)
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

        chosen = setup.select_backup(self.toolchain)

        self.assertEqual(chosen.name, "backup-20261101-100000-10")

    def test_select_backup_ignores_uninstall_backups(self):
        self.install(timestamp="20261101-100000")
        (self.toolchain / "backup-20261101-100000").mkdir()
        leftover = self.toolchain / "backup-uninstall-20261231-235959"
        (leftover / "templates" / "generic").mkdir(parents=True)
        (leftover / "templates" / "generic" / "AGENTS.md").write_text("# alt\n", encoding="utf-8")

        chosen = setup.select_backup(self.toolchain)

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
            setup.rollback(self.toolchain)

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

        report = setup.uninstall(self.toolchain)

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

        report = setup.uninstall(self.toolchain, home=self.home, remove_launcher=True)

        self.assertFalse(launcher.is_symlink())
        self.assertTrue(other.is_symlink())
        self.assertIn(str(launcher), report["launchers"])

    def test_uninstall_reports_every_removed_launcher(self):
        self.install()
        launcher = self.home / ".local" / "bin" / "vibe"
        launcher.parent.mkdir(parents=True)
        launcher.symlink_to(self.toolchain / "bin" / "vibe")
        command = self.toolchain / "vibe.cmd"
        command.write_text("vibe\n", encoding="utf-8")

        report = setup.uninstall(self.toolchain, home=self.home, remove_launcher=True)

        self.assertFalse(launcher.is_symlink())
        self.assertFalse(command.exists())
        self.assertEqual(
            sorted(report["launchers"]), sorted([str(launcher), str(command)])
        )

    def test_uninstall_backs_up_changed_templates_before_removal(self):
        self.install(timestamp="20261101-100000")
        edited = self.toolchain / "templates" / "generic" / "AGENTS.md"
        edited.write_text("# eigene Regel\n", encoding="utf-8")

        report = setup.uninstall(self.toolchain, timestamp="20261102-090000")

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
        report = setup.uninstall(self.toolchain)
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


# ===========================================================================
# Installer-Sperre bei leerem Laufregister (``runs.json``)
# ===========================================================================

import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


# Muss zum Programmabbild von scripts/setup-vibe.py passen; die Integrationstests
# installieren damit eine echte (temporäre) Installation.


def make_b4_kit(root, version="0.18.0"):
    """Baut ein minimales Repository-Abbild mit Versionsdatei."""
    root = Path(root)
    (root / "bin").mkdir(parents=True)
    for name in PROGRAM_FILES:
        (root / "bin" / name).write_text(
            f"#!/usr/bin/env python3\n# {name}\n", encoding="utf-8"
        )
    (root / "bin" / "web").mkdir()
    for name in WEB_FILES:
        (root / "bin" / "web" / name).write_text(f"/* {name} */\n", encoding="utf-8")
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    templates = root / "templates" / "generic" / ".vibe"
    templates.mkdir(parents=True)
    (templates / "project.env").write_text("TYPE=generic\n", encoding="utf-8")
    (root / "templates" / "generic" / "AGENTS.md").write_text(
        "# generic\n", encoding="utf-8"
    )
    (root / "data").mkdir()
    (root / "data" / "models.json").write_text('{"models": []}\n', encoding="utf-8")
    return root


class RuntimeFixture(unittest.TestCase):
    """Nur ein temporärer Laufzeitordner; keine Installation nötig."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.logs = self.root / "logs"
        self.logs.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    @property
    def runs_path(self):
        return self.logs / "runs.json"

    def write_runs_text(self, text):
        self.runs_path.write_text(text, encoding="utf-8")

    def write_live_run(self, run_id, state="running"):
        session = "vibe-" + run_id
        self.write_runs_text(
            json.dumps(
                {
                    "runs": [
                        {
                            "id": run_id,
                            "state": state,
                            "session": session,
                            "project": str(self.root / "proj"),
                        }
                    ]
                }
            )
        )
        return session

    @staticmethod
    def no_tmux(name):
        return None

    @staticmethod
    def fake_tmux(live_sessions=()):
        """Fake-tmux: nur genannte Sitzungen gelten als vorhanden."""
        live = set(live_sessions)

        def which(name):
            return "/fake/tmux" if name == "tmux" else None

        def runner(command, **kwargs):
            exists = "has-session" in command and command[-1] in live
            return subprocess.CompletedProcess(command, 0 if exists else 1, "", "")

        return which, runner


class EmptyRunStateDirectTest(RuntimeFixture):
    """Direkte Vertragsprüfung von ``running_installation`` (AK1, AK2, AK4, AK6)."""

    def reasons(self):
        return setup.running_installation(self.logs, which=self.no_tmux)

    def test_missing_runs_file_is_not_a_block_reason(self):
        # Bestandsvertrag / Schutzwache: fehlende Datei sperrt nicht.
        self.assertFalse(self.runs_path.exists())
        self.assertEqual([], self.reasons())

    def test_empty_runs_file_is_not_a_block_reason(self):
        # AK1: vorhandene 0-Byte-Datei enthält nachweislich keine Läufe.
        self.write_runs_text("")
        self.assertEqual(0, self.runs_path.stat().st_size)
        self.assertEqual([], self.reasons())

    def test_whitespace_only_runs_file_is_not_a_block_reason(self):
        # AK2: reiner Leerraum ist wie leer zu behandeln.
        for content in ("\n", "  \n\t \n"):
            with self.subTest(content=content):
                self.write_runs_text(content)
                self.assertEqual([], self.reasons())

    def test_non_empty_unreadable_runs_file_remains_a_block_reason(self):
        # AK3: nicht-leerer, kaputter Inhalt sperrt konservativ.
        self.write_runs_text("{kein json")
        reasons = self.reasons()
        self.assertEqual(1, len(reasons))
        self.assertIn("ist nicht lesbar", reasons[0])
        self.assertIn(str(self.runs_path), reasons[0])

    def test_oserror_when_reading_the_runs_path_remains_a_block_reason(self):
        # AK4: ein Verzeichnis anstelle der Datei erzwingt beim Lesen
        # IsADirectoryError (OSError). Kein chmod, weil Rechteänderungen auf
        # FUSE/NTFS nicht verlässlich wirken.
        self.runs_path.mkdir()
        self.assertTrue(self.runs_path.is_dir())
        reasons = self.reasons()
        self.assertEqual(1, len(reasons))
        self.assertIn("ist nicht lesbar", reasons[0])
        self.assertIn(str(self.runs_path), reasons[0])

    def test_live_run_with_existing_session_remains_a_block_reason(self):
        # AK6: running-Eintrag mit existierender tmux-Sitzung sperrt weiterhin.
        session = self.write_live_run("lauf-live", state="running")
        which, runner = self.fake_tmux({session})
        reasons = setup.running_installation(self.logs, runner=runner, which=which)
        self.assertEqual(1, len(reasons))
        self.assertIn("lauf-live", reasons[0])
        self.assertIn("running", reasons[0])


class InstallerFixture(RuntimeFixture):
    """Echte temporäre Installation plus bereinigter CLI-Harness."""

    def setUp(self):
        super().setUp()
        self.kit = make_b4_kit(self.root / "kit")
        self.vibe = self.root / "Vibe"
        self.toolchain = self.vibe / "_toolchain"
        self.home = self.root / "home"
        self.home.mkdir()
        # Die CLI prüft das Laufregister im Logverzeichnis ``--logs``.
        self.logs = self.vibe / "_logs"

    def install(self, mode="update", timestamp="20261101-100000"):
        # ``install_program_files`` erwartet das Installationsziel (Toolchain),
        # genau wie ``main`` es mit ``--install`` übergibt.
        return setup.install_program_files(
            self.kit, self.toolchain, mode=mode, timestamp=timestamp
        )

    def prepare_update(self):
        """Bestehende Installation mit klar erkennbarer alter Programmdatei."""
        self.install(timestamp="20261101-100000")
        (self.toolchain / "bin" / "vibe").write_text("ALT\n", encoding="utf-8")

    def run_main(self, args, which=None, runner=None):
        out = io.StringIO()
        # Bereinigte Umgebung: kein VIBE_INSTALL, kein produktives HOME.
        environ = {"HOME": str(self.home), "PATH": os.environ.get("PATH", "")}
        code = setup.main(
            list(args) + [
                "--install", str(self.toolchain),
                "--logs", str(self.vibe / "_logs"),
            ],
            output=lambda text="": out.write(str(text) + "\n"),
            which=which or (lambda name: None),
            runner=runner or (
                lambda command, **kwargs: subprocess.CompletedProcess(
                    command, 1, "", ""
                )
            ),
            platform_info=platform_info(),
            home=self.home,
            kit=self.kit,
            interactive=False,
            is_root=False,
            has_sudo=False,
            environ=environ,
        )
        return code, out.getvalue()

    @staticmethod
    def all_tools(name):
        return "/fake/" + name


class UpdateWithEmptyRunsTest(InstallerFixture):
    """AK1/AK2/AK3/AK4 aus Sicht des ``--update``-Pfads."""

    def test_update_runs_through_with_an_empty_runs_file(self):
        self.prepare_update()
        self.logs.mkdir(parents=True)
        self.write_runs_text("")
        self.assertEqual(0, self.runs_path.stat().st_size)

        code, output = self.run_main(
            ["--yes", "--update", "--vibe", str(self.vibe)],
            which=self.all_tools,
        )

        self.assertEqual(0, code, output)
        self.assertNotIn("wird gerade verwendet", output)
        self.assertNotIn("nicht lesbar", output)
        self.assertNotEqual(
            "ALT\n", (self.toolchain / "bin" / "vibe").read_text(encoding="utf-8")
        )

    def test_update_runs_through_with_a_whitespace_only_runs_file(self):
        self.prepare_update()
        self.logs.mkdir(parents=True)
        self.write_runs_text("\n")

        code, output = self.run_main(
            ["--yes", "--update", "--vibe", str(self.vibe)],
            which=self.all_tools,
        )

        self.assertEqual(0, code, output)
        self.assertNotIn("wird gerade verwendet", output)
        self.assertNotEqual(
            "ALT\n", (self.toolchain / "bin" / "vibe").read_text(encoding="utf-8")
        )

    def test_update_still_refuses_a_non_empty_unreadable_runs_file(self):
        # AK3: Bestandsvertrag RunningGuardTest bleibt ungeschwächt.
        self.prepare_update()
        self.logs.mkdir(parents=True)
        self.write_runs_text("{kein json")

        code, output = self.run_main(
            ["--yes", "--update", "--vibe", str(self.vibe)],
            which=self.all_tools,
        )

        self.assertEqual(1, code, output)
        self.assertIn("wird gerade verwendet", output)
        self.assertIn("nicht lesbar", output)
        self.assertEqual(
            "ALT\n", (self.toolchain / "bin" / "vibe").read_text(encoding="utf-8")
        )

    def test_update_still_refuses_when_the_runs_path_is_unreadable(self):
        # AK4: OSError beim Lesen (hier: Verzeichnis statt Datei).
        self.prepare_update()
        self.logs.mkdir(parents=True)
        self.runs_path.mkdir()

        code, output = self.run_main(
            ["--yes", "--update", "--vibe", str(self.vibe)],
            which=self.all_tools,
        )

        self.assertEqual(1, code, output)
        self.assertIn("wird gerade verwendet", output)
        self.assertIn("nicht lesbar", output)
        self.assertEqual(
            "ALT\n", (self.toolchain / "bin" / "vibe").read_text(encoding="utf-8")
        )

    def test_update_still_refuses_a_running_run_with_live_session(self):
        # AK6: running + existierende tmux-Sitzung sperrt weiterhin.
        self.prepare_update()
        self.logs.mkdir(parents=True)
        session = self.write_live_run("lauf-live", state="running")
        which, runner = RuntimeFixture.fake_tmux({session})

        code, output = self.run_main(
            ["--yes", "--update", "--vibe", str(self.vibe)],
            which=which,
            runner=runner,
        )

        self.assertEqual(1, code, output)
        self.assertIn("wird gerade verwendet", output)
        self.assertIn("lauf-live", output)
        self.assertEqual(
            "ALT\n", (self.toolchain / "bin" / "vibe").read_text(encoding="utf-8")
        )

    def test_update_still_refuses_a_starting_run_with_live_session(self):
        # AK6: starting + existierende tmux-Sitzung sperrt weiterhin.
        self.prepare_update()
        self.logs.mkdir(parents=True)
        session = self.write_live_run("lauf-start", state="starting")
        which, runner = RuntimeFixture.fake_tmux({session})

        code, output = self.run_main(
            ["--yes", "--update", "--vibe", str(self.vibe)],
            which=which,
            runner=runner,
        )

        self.assertEqual(1, code, output)
        self.assertIn("wird gerade verwendet", output)
        self.assertIn("lauf-start", output)
        self.assertEqual(
            "ALT\n", (self.toolchain / "bin" / "vibe").read_text(encoding="utf-8")
        )


class UninstallWithEmptyRunsTest(InstallerFixture):
    """AK5: Uninstall wird durch ein leeres Register nicht blockiert."""

    def test_uninstall_runs_through_with_an_empty_runs_file(self):
        self.install()
        self.logs.mkdir(parents=True)
        self.write_runs_text("")

        code, output = self.run_main(
            ["--yes", "--uninstall", "--vibe", str(self.vibe)],
            which=self.all_tools,
        )

        self.assertEqual(0, code, output)
        self.assertNotIn("wird gerade verwendet", output)
        self.assertFalse((self.toolchain / "bin" / "vibe").exists())

    def test_uninstall_still_refuses_a_running_run_with_live_session(self):
        self.install()
        self.logs.mkdir(parents=True)
        session = self.write_live_run("lauf-live", state="running")
        which, runner = RuntimeFixture.fake_tmux({session})

        code, output = self.run_main(
            ["--yes", "--uninstall", "--vibe", str(self.vibe)],
            which=which,
            runner=runner,
        )

        self.assertEqual(1, code, output)
        self.assertIn("wird gerade verwendet", output)
        self.assertIn("lauf-live", output)
        self.assertTrue((self.toolchain / "bin" / "vibe").is_file())


class RollbackWithEmptyRunsTest(InstallerFixture):
    """AK5: Rollback wird durch ein leeres Register nicht blockiert."""

    def prepare_rollback(self):
        self.install(timestamp="20261101-100000")
        (self.toolchain / "bin" / "vibe").write_text("ALT\n", encoding="utf-8")
        self.install(timestamp="20261101-180000")

    def test_rollback_runs_through_with_an_empty_runs_file(self):
        self.prepare_rollback()
        self.logs.mkdir(parents=True, exist_ok=True)
        self.write_runs_text("")

        code, output = self.run_main(
            ["--yes", "--rollback", "--vibe", str(self.vibe)],
            which=self.all_tools,
        )

        self.assertEqual(0, code, output)
        self.assertNotIn("wird gerade verwendet", output)
        self.assertIn("Rollback", output)
        self.assertEqual(
            "ALT\n", (self.toolchain / "bin" / "vibe").read_text(encoding="utf-8")
        )

    def test_rollback_still_refuses_a_running_run_with_live_session(self):
        self.prepare_rollback()
        self.logs.mkdir(parents=True, exist_ok=True)
        session = self.write_live_run("lauf-live", state="running")
        which, runner = RuntimeFixture.fake_tmux({session})

        code, output = self.run_main(
            ["--yes", "--rollback", "--vibe", str(self.vibe)],
            which=which,
            runner=runner,
        )

        self.assertEqual(1, code, output)
        self.assertIn("wird gerade verwendet", output)
        self.assertIn("lauf-live", output)
        self.assertNotEqual(
            "ALT\n", (self.toolchain / "bin" / "vibe").read_text(encoding="utf-8")
        )


# ===========================================================================
# Abnahme: Testläufe dürfen die laufende Instanz nicht verändern
# ===========================================================================

import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

WRAPPER = REPO / "install-vibe.sh"


# Variablen, die im Vorfall Produktivpfade trugen. Ein Test darf sie nie aus
# dem Prozess erben; die Vorfall-Umgebung wird nur als ``environ`` übergeben.
INCIDENT_KEYS = (
    "VIBE",
    "VIBE_PROFILE",
    "VIBE_INSTALL",
    "VIBE_STATE",
    "VIBE_RUNTIME",
    "VIBE_CONFIG_FILE",
    "VIBE_AGENTS_DIR",
)


def make_b17_kit(root, version="0.18.0"):
    """Minimales Kit-Abbild; alle Programmdateien und Vorlagen sind vorhanden."""
    root = Path(root)
    (root / "bin").mkdir(parents=True)
    for name in PROGRAM_FILES:
        (root / "bin" / name).write_text(
            "#!/usr/bin/env python3\n# " + name + "\n", encoding="utf-8"
        )
    (root / "bin" / "web").mkdir()
    for name in WEB_FILES:
        (root / "bin" / "web" / name).write_text("/* " + name + " */\n", encoding="utf-8")
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    templates = root / "templates" / "generic" / ".vibe"
    templates.mkdir(parents=True)
    (templates / "project.env").write_text("TYPE=generic\n", encoding="utf-8")
    (root / "templates" / "generic" / "AGENTS.md").write_text("# generic\n", encoding="utf-8")
    (root / "data").mkdir()
    (root / "data" / "models.json").write_text('{"models": []}\n', encoding="utf-8")
    return root


def essential_which(name):
    """Alle benötigten Werkzeuge gelten als vorhanden, tmux aber nicht.

    ``tmux`` bleibt absichtlich unsichtbar: ``running_installation`` soll keine
    Sitzung prüfen und damit keine echte Umgebung des Rechners anfassen.
    """
    return None if name == "tmux" else "/fake/" + name


def platform_info_for_isolation():
    return {
        "os": "linux",
        "distro": "ubuntu",
        "family": "debian",
        "manager": "apt-get",
        "container": True,
        "immutable": False,
        "wsl": False,
        "wsl_available": False,
        "npm_available": True,
        "label": "Test-Container",
        "release": {},
    }


def snapshot(root):
    """SHA-256 je Datei relativ zum Wurzelordner."""
    root = Path(root)
    digests = {}
    if not root.exists():
        return digests
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digests[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return digests


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


class B17Base(unittest.TestCase):
    """Fake-Produktivbereich und ein davon getrennter Temp-Prüfbereich."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

        # Fake-Produktivbereich: sieht aus wie die laufende Installation des
        # Vorfalls, liegt aber vollständig unter tempfile.
        self.prod_root = self.root / "produktion"
        self.fake_home = self.prod_root / "home"
        self.fake_workspace = self.prod_root / "VibeCode"
        self.fake_install = self.fake_workspace / "_toolchain"
        # Eigener Laufzeitordner (nicht <workspace>/_logs), damit ein
        # unveränderter Reuse-Lauf die Fake-Konfiguration nicht neu schreibt.
        self.fake_runtime = self.prod_root / "runtime"
        self.fake_config = self.fake_home / ".config" / "vibe" / "config.json"
        self._make_fake_installation()

        # Prüfbereich: alle schreibenden Soll-Pfade.
        self.temp_root = self.root / "pruefung"
        self.temp_root.mkdir()

        self.kit = make_b17_kit(self.root / "kit")

        self.incident_environ = {
            "HOME": str(self.fake_home),
            "VIBE": str(self.fake_workspace),
            "VIBE_INSTALL": str(self.fake_install),
            "VIBE_STATE": str(self.fake_install),
            "VIBE_RUNTIME": str(self.fake_runtime),
            "VIBE_CONFIG_FILE": str(self.fake_config),
            "PATH": os.environ.get("PATH", ""),
        }

    def _make_fake_installation(self):
        (self.fake_install / "bin").mkdir(parents=True)
        (self.fake_install / "bin" / "vibe").write_text(
            "#!/bin/sh\necho vibe\n", encoding="utf-8"
        )
        write_json(self.fake_install / "harness.json", {"harness": "opencode"})
        write_json(
            self.fake_install / "version.json",
            {"version": "0.1.0", "mode": "update", "source": str(self.fake_install)},
        )
        write_json(
            self.fake_config,
            {
                "profiles": {
                    "prod": {
                        "workspace": str(self.fake_workspace),
                        "install": str(self.fake_install),
                        "state": str(self.fake_install),
                        "runtime": str(self.fake_runtime),
                    }
                }
            },
        )

    def runner(self, command, **kwargs):
        return subprocess.CompletedProcess(command, 1, "", "")

    def run_main(self, args, environ=None, kit=None):
        out = io.StringIO()
        code = setup.main(
            list(args),
            output=lambda text="": out.write(str(text) + "\n"),
            which=essential_which,
            runner=self.runner,
            platform_info=platform_info_for_isolation(),
            kit=kit or self.kit,
            interactive=False,
            is_root=True,
            has_sudo=False,
            environ=self.incident_environ if environ is None else environ,
        )
        return code, out.getvalue()

    def clean_environ(self, home):
        return {"HOME": str(home), "PATH": os.environ.get("PATH", "")}

    def assert_prod_unchanged(self, before):
        self.assertEqual(before, snapshot(self.prod_root),
                         "Der Fake-Produktivbereich wurde verändert")
        self.assertEqual(
            [], sorted(self.fake_install.glob("backup-*")),
            "Im Fake-Produktivbereich entstand eine Sicherung",
        )


class MainEnvironTest(B17Base):
    """AK1: main löst alle Pfade aus dem übergebenen environ auf."""

    def test_dry_run_resolves_defaults_from_the_given_environ(self):
        home = self.temp_root / "home"
        workspace = self.temp_root / "Workspace"
        install = self.temp_root / "toolchain"
        runtime = self.temp_root / "logs"
        environ = {
            "HOME": str(home),
            "VIBE": str(workspace),
            "VIBE_INSTALL": str(install),
            "VIBE_RUNTIME": str(runtime),
            "PATH": os.environ.get("PATH", ""),
        }

        code, output = self.run_main(["--yes", "--dry-run"], environ=environ)

        self.assertEqual(code, 0, output)
        self.assertIn(str(workspace), output)
        self.assertIn(str(install), output)
        self.assertIn(str(runtime), output)
        self.assertIn(
            str(home / ".config" / "vibe" / "config.json"), output,
            "Die dry-run-Ausgabe nennt nicht den Konfigurationspfad aus environ",
        )
        # Eine Vorschau schreibt nichts.
        self.assertFalse(workspace.exists(), output)
        self.assertFalse(install.exists(), output)

    def test_closing_hint_reads_the_given_environ(self):
        home = self.temp_root / "home"
        workspace = self.temp_root / "Workspace"
        install = self.temp_root / "toolchain"
        runtime = self.temp_root / "logs"
        other_vibe = self.temp_root / "andere-quelle"
        environ = {
            "HOME": str(home),
            "VIBE": str(other_vibe),
            "PATH": os.environ.get("PATH", ""),
        }

        code, output = self.run_main(
            ["--yes", "--skip-deps", "--no-launcher", "--no-register",
             "--vibe", str(workspace), "--install", str(install),
             "--logs", str(runtime)],
            environ=environ,
        )

        self.assertEqual(code, 0, output)
        self.assertIn("Hinweis: VIBE=" + str(other_vibe), output)
        self.assertFalse(other_vibe.exists(), output)


class UpdateGuardTest(B17Base):
    """AK2: --update auf die laufende Instanz wird ohne --source verweigert."""

    def test_update_on_the_running_instance_is_refused_without_writes(self):
        before = snapshot(self.prod_root)
        temp_workspace = self.temp_root / "Arbeitsbereich"

        code, output = self.run_main([
            "--vibe", str(temp_workspace), "--update", "--yes",
            "--skip-deps", "--no-launcher", "--no-register",
        ])

        self.assertEqual(code, 1, output)
        self.assertIn("--source", output,
                      "Die Verweigerung muss die autorisierte Quelle nennen")
        self.assert_prod_unchanged(before)
        self.assertFalse(temp_workspace.exists(),
                         "Trotz Verweigerung wurde ein Workspace angelegt")

    def test_update_with_an_explicit_install_on_the_running_instance_is_refused(self):
        """Review 1/Medium: Ein explizites ``--install`` befreit den Guard nicht.

        Zeigt ``--install`` auf die erkannte laufende Installation, ist das
        ebenso eine Aktualisierung der laufenden Instanz wie das implizit
        aufgelöste Ziel. Ohne ``--source`` darf sie nichts schreiben.
        """
        before = snapshot(self.prod_root)

        code, output = self.run_main([
            "--vibe", str(self.fake_workspace), "--install", str(self.fake_install),
            "--update", "--yes", "--skip-deps", "--no-launcher", "--no-register",
        ])

        self.assertEqual(code, 1, output)
        self.assertIn("--source", output,
                      "Die Verweigerung muss die autorisierte Quelle nennen")
        self.assert_prod_unchanged(before)

    def test_update_with_an_explicit_install_and_source_is_allowed(self):
        """Gegenprobe: ``--source`` autorisiert dasselbe explizite Ziel."""
        kit = make_b17_kit(self.temp_root / "kit-quelle", version="9.9.9")

        code, output = self.run_main([
            "--vibe", str(self.fake_workspace), "--install", str(self.fake_install),
            "--update", "--yes", "--skip-deps", "--no-launcher", "--no-register",
            "--source", str(kit),
        ])

        self.assertEqual(code, 0, output)
        recorded = json.loads(
            (self.fake_install / "version.json").read_text(encoding="utf-8")
        )
        self.assertEqual(recorded["version"], "9.9.9",
                         "Das autorisierte Update hat die Installation nicht aktualisiert")
        self.assertEqual(Path(recorded["source"]), kit.resolve())

    def test_dry_run_on_the_running_instance_is_allowed_and_explains_the_guard(self):
        before = snapshot(self.prod_root)

        code, output = self.run_main(["--yes", "--dry-run", "--update"])

        self.assertEqual(code, 0, output)
        self.assertIn("--source", output,
                      "Auch die Vorschau muss den Guard-Hinweis zeigen")
        self.assert_prod_unchanged(before)

    def test_reuse_on_the_running_instance_is_not_blocked(self):
        """``--reuse`` ist keine autorisierte Aktualisierung.

        Der Guard betrifft nur ``--update``. Wiederverwenden darf fehlende
        Dateien ergänzen, aber keine vorhandenen überschreiben und keine
        Sicherung anlegen. Die globale Konfiguration bleibt unverändert.
        """
        config_before = snapshot(self.fake_home)
        existing = {}
        for name in ("bin/vibe", "harness.json", "version.json"):
            path = self.fake_install / name
            existing[name] = path.read_bytes()

        code, output = self.run_main([
            "--reuse", "--yes", "--skip-deps", "--no-launcher", "--no-register",
            "--vibe", str(self.fake_workspace), "--logs", str(self.fake_runtime),
        ])

        self.assertEqual(code, 0, output)
        for name, content in existing.items():
            self.assertEqual(
                (self.fake_install / name).read_bytes(), content,
                "Wiederverwenden hat " + name + " überschrieben",
            )
        self.assertEqual(
            [], sorted(self.fake_install.glob("backup-*")),
            "Wiederverwenden legte eine Sicherung an",
        )
        self.assertEqual(
            config_before, snapshot(self.fake_home),
            "Wiederverwenden hat die Konfiguration neu geschrieben",
        )


class IsolatedUpdateTest(B17Base):
    """AK4/AK5: Ein Test-Update schreibt ausschließlich unter den Temp-Root."""

    def test_test_update_writes_only_into_the_temp_root(self):
        """AK5: Ein Test--update schreibt ausschließlich in den Temp-Root.

        Die Prüf-Installation simuliert eine bestehende Installation. Nach dem
        Update liegen Programmdateien, Sicherung, ``version.json`` und die
        Konfiguration unter dem Temp-Root; der Fake-Produktivbereich bleibt
        byte-identisch.
        """
        before = snapshot(self.prod_root)
        home = self.temp_root / "home"
        workspace = self.temp_root / "Workspace"
        install = self.temp_root / "toolchain"
        runtime = self.temp_root / "logs"
        (install / "bin").mkdir(parents=True)
        (install / "bin" / "vibe").write_text("ALT\n", encoding="utf-8")

        code, output = self.run_main(
            ["--update", "--yes", "--skip-deps", "--no-launcher",
             "--no-register", "--vibe", str(workspace),
             "--install", str(install), "--logs", str(runtime)],
            environ=self.clean_environ(home),
        )

        self.assertEqual(code, 0, output)
        self.assertNotEqual(
            (install / "bin" / "vibe").read_text(encoding="utf-8"), "ALT\n",
            "Das Test--update hat die Prüf-Installation nicht aktualisiert",
        )
        self.assertTrue((install / "harness.json").is_file(), output)
        self.assertTrue((install / "version.json").is_file(), output)
        self.assertTrue(
            list(install.glob("backup-*")),
            "Das Update legte keine Sicherung unter dem Temp-Root an",
        )
        recorded = json.loads(
            (install / "version.json").read_text(encoding="utf-8")
        )
        self.assertEqual(Path(recorded["source"]), self.kit.resolve())
        config_path = home / ".config" / "vibe" / "config.json"
        self.assertTrue(config_path.is_file(), output)
        data = json.loads(config_path.read_text(encoding="utf-8"))
        prod = data["profiles"]["prod"]
        self.assertEqual(prod["workspace"], str(workspace))
        self.assertEqual(prod["install"], str(install))
        self.assertEqual(prod["runtime"], str(runtime))
        self.assert_prod_unchanged(before)

    def test_environ_install_target_wins_without_a_cli_option(self):
        before = snapshot(self.prod_root)
        home = self.temp_root / "home"
        workspace = self.temp_root / "EnvironWorkspace"
        install = self.temp_root / "environ-toolchain"
        runtime = self.temp_root / "environ-logs"
        environ = {
            "HOME": str(home),
            "VIBE": str(workspace),
            "VIBE_INSTALL": str(install),
            "VIBE_RUNTIME": str(runtime),
            "PATH": os.environ.get("PATH", ""),
        }

        code, output = self.run_main(
            ["--yes", "--skip-deps", "--no-launcher", "--no-register"],
            environ=environ,
        )

        self.assertEqual(code, 0, output)
        self.assertTrue((install / "bin" / "vibe").is_file(),
                        "Das Installationsziel kam nicht aus environ:\n" + output)
        self.assertFalse(
            (home / "VibeCode" / "_toolchain").exists(),
            "Das Standardziel der Prozessumgebung wurde verwendet",
        )
        config_path = home / ".config" / "vibe" / "config.json"
        self.assertTrue(config_path.is_file(), output)
        data = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(data["profiles"]["prod"]["install"], str(install))
        self.assertEqual(data["profiles"]["prod"]["runtime"], str(runtime))
        self.assert_prod_unchanged(before)


class SourceOptionTest(B17Base):
    """AK3: --source benennt die autorisierte Quelle ausdrücklich."""

    def test_update_with_an_explicit_source_updates_the_instance(self):
        kit = make_b17_kit(self.temp_root / "kit-quelle", version="9.9.9")

        code, output = self.run_main([
            "--update", "--yes", "--skip-deps", "--no-launcher",
            "--no-register", "--vibe", str(self.fake_workspace),
            "--source", str(kit),
        ])

        self.assertEqual(code, 0, output)
        recorded = json.loads(
            (self.fake_install / "version.json").read_text(encoding="utf-8")
        )
        self.assertEqual(recorded["version"], "9.9.9")
        self.assertEqual(Path(recorded["source"]), kit.resolve(),
                         "version.json nennt nicht die benannte Quelle")

    def test_source_with_a_broken_directory_changes_nothing(self):
        before = snapshot(self.prod_root)
        broken = self.temp_root / "kaputte-quelle"
        broken.mkdir()

        code, output = self.run_main([
            "--update", "--yes", "--skip-deps", "--no-launcher",
            "--no-register", "--vibe", str(self.fake_workspace),
            "--source", str(broken),
        ])

        self.assertEqual(code, 1, output)
        self.assertIn("Unvollständiges Quellverzeichnis", output)
        self.assert_prod_unchanged(before)

    def test_install_wrapper_names_its_own_source(self):
        text = WRAPPER.read_text(encoding="utf-8")

        self.assertIn("--source", text)
        self.assertIn('"$KIT"', text)


if __name__ == "__main__":
    unittest.main()
