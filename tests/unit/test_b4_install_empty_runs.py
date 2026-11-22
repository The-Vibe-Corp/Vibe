"""B4: Installer-Sperre bei leerem Laufregister (``runs.json``).

Die Fälle sind unabhängig aus FEEDBACK.md (Eintrag B4), SPEC.md und AGENTS.md
abgeleitet. Geprüft wird ausschließlich ``running_installation`` aus
``scripts/setup-vibe.py`` und dessen drei Nutzer (Update, Uninstall, Rollback).

Alle schreibenden Zugriffe liegen in temporären Verzeichnissen (``tempfile``).
Es werden weder produktive Pfade noch das echte ``HOME``/``VIBE_*`` oder echte
tmux-Sitzungen verwendet. Sitzungsprüfungen laufen über ein injiziertes
Fake-tmux-Muster (``which``/``runner``).
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

# Muss zum Programmabbild von scripts/setup-vibe.py passen; die Integrationstests
# installieren damit eine echte (temporäre) Installation.
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
    # Eindeutiger Modulname: nicht mit test_install_lifecycle.py kollidieren.
    loader = importlib.machinery.SourceFileLoader("setup_vibe_b4", str(SETUP))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    setup = module


def make_kit(root, version="0.18.0"):
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
        self.kit = make_kit(self.root / "kit")
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


if __name__ == "__main__":
    unittest.main()
