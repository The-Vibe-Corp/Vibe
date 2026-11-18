"""Tests für die isolierte Projektprüfung (V-002).

Die Tests bauen eigene Fixture-Projekte in temporären Verzeichnissen. Sie
prüfen Erfolg, beabsichtigten Fehlschlag, unbekannte Modi, fehlende Werkzeuge,
die Testvollständigkeit im Vollmodus sowie die Isolation von HOME, VIBE und
Ports. F31 ergänzt den Mittelmodus ``package``: Er führt die Paketprüfung aus
und verlangt nur dann einen Testnachweis, wenn ``VERIFY_TESTS`` konfiguriert
ist. Die produktive Konfiguration des Aufrufers wird dabei nur gelesen.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VERIFY = REPO / "scripts" / "verify.sh"
BROWSER = REPO / "tests" / "browser"

OBSERVED_KEYS = (
    "HOME",
    "VIBE",
    "TMPDIR",
    "XDG_CONFIG_HOME",
    "XDG_CACHE_HOME",
    "XDG_DATA_HOME",
    "XDG_STATE_HOME",
    "PYTHONUSERBASE",
    "VIBE_VERIFY_ROOT",
    "VIBE_VERIFY_SCREENSHOT_DIR",
    "VIBE_UI_PORT",
    "VIBE_TEST_PORT",
    "VIBE_VERIFY_PORT",
    "VIBE_OPENCODE_PORT",
)
PORT_KEYS = (
    "VIBE_UI_PORT",
    "VIBE_TEST_PORT",
    "VIBE_VERIFY_PORT",
    "VIBE_OPENCODE_PORT",
)


def run_verify(*args, project=None, env=None, timeout=120):
    command = ["bash", str(VERIFY), *args]
    if project is not None:
        command.extend(["--project", str(project)])
    environment = os.environ.copy()
    environment.update(env or {})
    return subprocess.run(
        command,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environment,
    )


def make_project(base, lines):
    project = Path(base) / "projekt"
    (project / ".vibe").mkdir(parents=True)
    (project / ".vibe" / "project.env").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return project


def write_script(project, name, body):
    path = Path(project) / name
    path.write_text(body, encoding="utf-8")
    return path


def tree_digest(root):
    root = Path(root)
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return result


def observed_environment(stdout):
    match = re.search(r"^OBSERVED=(\{.*\})$", stdout, flags=re.MULTILINE)
    if not match:
        raise AssertionError("Prüfbefehl hat keine Umgebung ausgegeben:\n" + stdout)
    return json.loads(match.group(1))


class VerifyUsageTest(unittest.TestCase):
    def test_unknown_mode_is_rejected_with_exit_2(self):
        result = run_verify("unbekannt")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("Unbekannter Modus", result.stdout + result.stderr)
        self.assertIn("quick", result.stdout + result.stderr)
        self.assertIn("full", result.stdout + result.stderr)

    def test_missing_mode_prints_usage_and_exits_2(self):
        result = run_verify()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("Aufruf", result.stdout + result.stderr)

    def test_help_lists_exit_codes(self):
        result = run_verify("--help")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for code in ("0", "2", "3", "4", "5", "6"):
            self.assertIn(code, result.stdout)


class VerifyQuickTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.caller_home = self.base / "caller-home"
        (self.caller_home / ".config" / "opencode" / "agents").mkdir(parents=True)
        (self.caller_home / ".config" / "opencode" / "agents" / "privat.md").write_text(
            "produktiv\n", encoding="utf-8"
        )
        self.caller_vibe = self.base / "caller-vibe"
        (self.caller_vibe / "_toolchain").mkdir(parents=True)
        (self.caller_vibe / "_toolchain" / "vibe.json").write_text(
            '{"roots": []}\n', encoding="utf-8"
        )
        (self.caller_vibe / "_toolchain" / "models.json").write_text(
            '{"models": []}\n', encoding="utf-8"
        )
        self.home_before = tree_digest(self.caller_home)
        self.vibe_before = tree_digest(self.caller_vibe)

    def tearDown(self):
        self.tmp.cleanup()

    def test_successful_check_runs_isolated_and_cleans_up(self):
        project = make_project(
            self.base,
            [
                "TYPE=generic",
                'VERIFY_TOOLS="python3"',
                'VERIFY_QUICK="python3 beobachten.py"',
            ],
        )
        write_script(
            project,
            "beobachten.py",
            "import json, os\n"
            f"keys = {OBSERVED_KEYS!r}\n"
            "werte = {key: os.environ.get(key) for key in keys}\n"
            "werte['CWD'] = os.getcwd()\n"
            "print('OBSERVED=' + json.dumps(werte))\n",
        )
        result = run_verify(
            "quick",
            project=project,
            env={
                "HOME": str(self.caller_home),
                "VIBE": str(self.caller_vibe),
                "VIBE_UI_PORT": "9999",
            },
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK: Prüfung 'quick'", result.stdout)

        observed = observed_environment(result.stdout)
        verify_root = Path(observed["VIBE_VERIFY_ROOT"])
        self.assertTrue(verify_root.is_absolute())
        self.assertTrue(observed["HOME"].startswith(str(verify_root)))
        self.assertTrue(observed["VIBE"].startswith(str(verify_root)))
        self.assertTrue(observed["TMPDIR"].startswith(str(verify_root)))
        for key in (
            "XDG_CONFIG_HOME",
            "XDG_CACHE_HOME",
            "XDG_DATA_HOME",
        ):
            self.assertIsNone(
                observed[key],
                f"{key} darf nicht aus der Aufruferumgebung übernommen werden",
            )
        self.assertTrue(observed["XDG_STATE_HOME"].startswith(str(verify_root)))
        self.assertTrue(Path(observed["PYTHONUSERBASE"]).is_absolute())
        self.assertTrue(
            observed["VIBE_VERIFY_SCREENSHOT_DIR"].startswith(str(verify_root))
        )
        self.assertNotEqual(observed["VIBE"], str(self.caller_vibe))
        self.assertNotEqual(observed["HOME"], str(self.caller_home))
        self.assertEqual(observed["CWD"], str(project.resolve()))

        ports = [observed[key] for key in PORT_KEYS]
        for value in ports:
            self.assertRegex(str(value), r"^\d+$")
            self.assertNotIn(value, ("8787", "4096", "9999"))
        self.assertEqual(len(set(ports)), len(ports), "Ports müssen verschieden sein")

        self.assertFalse(
            verify_root.exists(), "Erfolgreiche Prüfung muss ihr Arbeitsverzeichnis löschen"
        )
        self.assertEqual(tree_digest(self.caller_home), self.home_before)
        self.assertEqual(tree_digest(self.caller_vibe), self.vibe_before)

    def test_keep_option_preserves_the_working_directory(self):
        project = make_project(
            self.base,
            ["TYPE=generic", 'VERIFY_QUICK="true"'],
        )
        result = run_verify("quick", "--keep", project=project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        match = re.search(r"Prüfverzeichnis: (\S+)", result.stdout)
        self.assertIsNotNone(match, result.stdout)
        kept = Path(match.group(1))
        self.assertTrue(kept.is_dir())
        self.assertTrue((kept / "home").is_dir())
        self.assertTrue((kept / "vibe").is_dir())

    def test_failing_check_returns_exit_5_and_reports_command_status(self):
        project = make_project(
            self.base,
            ["TYPE=generic", 'VERIFY_QUICK="python3 absichtlich_kaputt.py"'],
        )
        write_script(
            project,
            "absichtlich_kaputt.py",
            "import sys\nprint('beabsichtigter Fehlschlag')\nsys.exit(7)\n",
        )
        result = run_verify("quick", project=project)
        self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
        self.assertIn("beabsichtigter Fehlschlag", result.stdout)
        self.assertIn("Exit 7", result.stdout + result.stderr)
        self.assertIn("FEHLT", result.stdout + result.stderr)

    def test_placeholder_command_is_not_a_passing_check(self):
        project = make_project(
            self.base,
            ["TYPE=generic", 'VERIFY_QUICK="echo TODO"'],
        )
        result = run_verify("quick", project=project)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("VERIFY_QUICK", result.stdout + result.stderr)

    def test_missing_configuration_is_reported(self):
        project = make_project(self.base, ["TYPE=generic"])
        result = run_verify("quick", project=project)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("project.env", result.stdout + result.stderr)


class VerifyTmuxIsolationTest(unittest.TestCase):
    """Ein geerbtes TMUX darf die Prüfung nicht auf den Server des Aufrufers lenken."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_caller_tmux_is_not_handed_to_the_check(self):
        project = make_project(
            self.base,
            ["TYPE=generic", 'VERIFY_QUICK="python3 beobachten.py"'],
        )
        write_script(
            project,
            "beobachten.py",
            "import json, os\n"
            "keys = ('TMUX', 'TMUX_PANE', 'TMUX_TMPDIR')\n"
            "print('OBSERVED=' + json.dumps({key: os.environ.get(key) for key in keys}))\n",
        )

        result = run_verify(
            "quick",
            "--keep",
            project=project,
            env={"TMUX": "/tmp/tmux-1000/default,1,0", "TMUX_PANE": "%0"},
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        observed = observed_environment(result.stdout)
        self.assertIsNone(observed["TMUX"])
        self.assertIsNone(observed["TMUX_PANE"])
        match = re.search(r"Prüfverzeichnis: (\S+)", result.stdout)
        self.assertIsNotNone(match, result.stdout)
        self.assertTrue(
            observed["TMUX_TMPDIR"].startswith(match.group(1)),
            observed["TMUX_TMPDIR"],
        )


class VerifyMissingToolsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_declared_tool_stops_before_the_check(self):
        marker = self.base / "sollte_nicht_entstehen"
        project = make_project(
            self.base,
            [
                "TYPE=generic",
                'VERIFY_TOOLS="vibe-verify-werkzeug-fehlt"',
                f'VERIFY_QUICK="touch {marker}"',
            ],
        )
        result = run_verify("quick", project=project)
        self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
        self.assertIn("vibe-verify-werkzeug-fehlt", result.stdout + result.stderr)
        self.assertFalse(marker.exists(), "Prüfbefehl darf bei fehlendem Werkzeug nicht starten")

    def test_wrapper_reports_missing_python3_with_exit_4(self):
        environment = {
            "PATH": "/nonexistent",
            "HOME": str(self.base),
            "VIBE": str(self.base),
        }
        result = subprocess.run(
            ["/bin/bash", str(VERIFY), "quick"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=30,
            env=environment,
        )
        self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
        self.assertIn("python3", result.stdout + result.stderr)


class VerifyFullTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def make_test_project(self, lines, test_source):
        project = make_project(self.base, lines)
        tests = project / "tests"
        tests.mkdir()
        (tests / "test_beispiel.py").write_text(test_source, encoding="utf-8")
        return project

    def test_full_without_test_structure_is_rejected(self):
        project = make_project(
            self.base,
            ["TYPE=generic", 'VERIFY_FULL="true"'],
        )
        result = run_verify("full", project=project)
        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        self.assertIn("VERIFY_TESTS", result.stdout + result.stderr)

    def test_full_rejects_a_run_without_executed_tests(self):
        project = self.make_test_project(
            [
                "TYPE=generic",
                'VERIFY_FULL="python3 leerlauf.py"',
                'VERIFY_TESTS="tests"',
                'VERIFY_TEST_PATTERN="Ran ([0-9]+) tests?"',
            ],
            "import unittest\n\n"
            "class BeispielTest(unittest.TestCase):\n"
            "    def test_summe(self):\n"
            "        self.assertEqual(1 + 1, 2)\n",
        )
        write_script(project, "leerlauf.py", "print('Ran 0 tests in 0.001s')\n")
        result = run_verify("full", project=project)
        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        self.assertIn("0", result.stdout + result.stderr)
        self.assertIn("Tests", result.stdout + result.stderr)

    def test_full_passes_with_real_tests_and_reports_the_count(self):
        project = self.make_test_project(
            [
                "TYPE=generic",
                'VERIFY_FULL="python3 -m unittest discover -s tests -v"',
                'VERIFY_TESTS="tests"',
                'VERIFY_TEST_PATTERN="Ran ([0-9]+) tests?"',
            ],
            "import unittest\n\n"
            "class BeispielTest(unittest.TestCase):\n"
            "    def test_summe(self):\n"
            "        self.assertEqual(1 + 1, 2)\n",
        )
        result = run_verify("full", project=project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Tests erkannt: 1", result.stdout)
        self.assertIn("OK: Prüfung 'full'", result.stdout)

    def test_full_rejects_fewer_tests_than_configured(self):
        project = self.make_test_project(
            [
                "TYPE=generic",
                'VERIFY_FULL="python3 -m unittest discover -s tests -v"',
                'VERIFY_TESTS="tests"',
                'VERIFY_TEST_PATTERN="Ran ([0-9]+) tests?"',
                "VERIFY_MIN_TESTS=2",
            ],
            "import unittest\n\n"
            "class BeispielTest(unittest.TestCase):\n"
            "    def test_summe(self):\n"
            "        self.assertEqual(1 + 1, 2)\n",
        )
        result = run_verify("full", project=project)
        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        self.assertIn("Minimum 2", result.stdout + result.stderr)


class VerifyPackageTest(unittest.TestCase):
    """Mittelmodus ``package``: Paketprüfung mit optionalem Testnachweis.

    F31: Die Agenten brauchen zwischen ``quick`` und ``full`` einen schnellen,
    belegbaren Modus. ``package`` führt ausschließlich ``VERIFY_PACKAGE`` aus.
    Ist ``VERIFY_TESTS`` gesetzt, gilt derselbe Testnachweis wie in ``full``
    (Testdateien vorhanden, Mindestanzahl erreicht, Exit 6 bei Verstoß). Ohne
    ``VERIFY_TESTS`` besteht kein Nachweiszwang wie in ``quick``.
    """

    BEISPIELTEST = (
        "import unittest\n\n"
        "class BeispielTest(unittest.TestCase):\n"
        "    def test_summe(self):\n"
        "        self.assertEqual(1 + 1, 2)\n"
    )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def make_test_project(self, lines, test_source=None, with_tests=True):
        project = make_project(self.base, lines)
        if with_tests:
            tests = project / "tests"
            tests.mkdir()
            (tests / "test_beispiel.py").write_text(
                self.BEISPIELTEST if test_source is None else test_source,
                encoding="utf-8",
            )
        return project

    def test_package_runs_verify_package_instead_of_quick_or_full(self):
        project = make_project(
            self.base,
            [
                "TYPE=generic",
                'VERIFY_QUICK="echo quick-pruefung"',
                'VERIFY_FULL="echo full-pruefung"',
                'VERIFY_PACKAGE="echo paket-pruefung"',
            ],
        )

        result = run_verify("package", project=project)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK: Prüfung 'package'", result.stdout)
        self.assertIn("paket-pruefung", result.stdout)
        # Kein stiller Rückfall auf die anderen Stufen.
        self.assertNotIn("quick-pruefung", result.stdout)
        self.assertNotIn("full-pruefung", result.stdout)

    def test_package_requires_verify_package_without_falling_back(self):
        marker = self.base / "quick-oder-full-lief"
        project = make_project(
            self.base,
            [
                "TYPE=generic",
                f'VERIFY_QUICK="touch {marker}"',
                f'VERIFY_FULL="touch {marker}"',
            ],
        )

        result = run_verify("package", project=project)

        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("VERIFY_PACKAGE", result.stdout + result.stderr)
        self.assertFalse(
            marker.exists(),
            "package darf ohne VERIFY_PACKAGE nicht quick oder full ausführen",
        )

    def test_package_rejects_a_todo_placeholder(self):
        project = make_project(
            self.base,
            ["TYPE=generic", 'VERIFY_PACKAGE="echo TODO"'],
        )

        result = run_verify("package", project=project)

        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("VERIFY_PACKAGE", result.stdout + result.stderr)
        self.assertIn("TODO", result.stdout + result.stderr)

    def test_package_requires_test_files_when_verify_tests_is_set(self):
        project = make_project(
            self.base,
            [
                "TYPE=generic",
                'VERIFY_PACKAGE="true"',
                'VERIFY_TESTS="tests"',
            ],
        )

        result = run_verify("package", project=project)

        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        self.assertIn("VERIFY_TESTS", result.stdout + result.stderr)

    def test_package_rejects_a_run_without_executed_tests(self):
        project = self.make_test_project(
            [
                "TYPE=generic",
                'VERIFY_PACKAGE="python3 leerlauf.py"',
                'VERIFY_TESTS="tests"',
                'VERIFY_TEST_PATTERN="Ran ([0-9]+) tests?"',
            ]
        )
        write_script(project, "leerlauf.py", "print('Ran 0 tests in 0.001s')\n")

        result = run_verify("package", project=project)

        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        self.assertIn("0", result.stdout + result.stderr)
        self.assertIn("Tests", result.stdout + result.stderr)

    def test_package_passes_with_real_tests_and_reports_the_count(self):
        project = self.make_test_project(
            [
                "TYPE=generic",
                'VERIFY_PACKAGE="python3 -m unittest discover -s tests -v"',
                'VERIFY_TESTS="tests"',
                'VERIFY_TEST_PATTERN="Ran ([0-9]+) tests?"',
            ]
        )

        result = run_verify("package", project=project)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Tests erkannt: 1", result.stdout)
        self.assertIn("OK: Prüfung 'package'", result.stdout)

    def test_package_rejects_fewer_tests_than_configured(self):
        project = self.make_test_project(
            [
                "TYPE=generic",
                'VERIFY_PACKAGE="python3 -m unittest discover -s tests -v"',
                'VERIFY_TESTS="tests"',
                'VERIFY_TEST_PATTERN="Ran ([0-9]+) tests?"',
                "VERIFY_MIN_TESTS=2",
            ]
        )

        result = run_verify("package", project=project)

        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        self.assertIn("Minimum 2", result.stdout + result.stderr)

    def test_package_without_verify_tests_requires_no_test_proof(self):
        project = make_project(
            self.base,
            ["TYPE=generic", 'VERIFY_PACKAGE="echo ohne-testnachweis"'],
        )

        result = run_verify("package", project=project)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ohne-testnachweis", result.stdout)
        self.assertIn("OK: Prüfung 'package'", result.stdout)

    def test_package_does_not_start_the_opencode_service(self):
        # Der opencode-Dienst gehört nur zum Vollmodus; package bleibt schnell.
        fake_bin = self.base / "fake-bin"
        fake_bin.mkdir()
        marker = self.base / "opencode-gestartet"
        fake = fake_bin / "opencode"
        fake.write_text(
            "#!/bin/sh\n"
            f"touch {marker}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        project = make_project(
            self.base,
            ["TYPE=generic", 'VERIFY_PACKAGE="echo paket-ohne-dienst"'],
        )

        result = run_verify(
            "package",
            project=project,
            env={"PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", "")},
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(marker.exists(), "package startete den opencode-Dienst")

    def test_help_names_the_package_mode(self):
        result = run_verify("--help")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("package", result.stdout)

    def test_unknown_mode_lists_package_as_allowed(self):
        result = run_verify("unbekannt")

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("package", result.stdout + result.stderr)


class ScreenshotIsolationTest(unittest.TestCase):
    def test_browser_screenshots_honor_the_verify_directory(self):
        modules = {
            "test_fritz_ui": "F5-fritz.png",
            "test_pause_after_package_ui": "F4-pause.png",
            "test_sandbox_ui": "F7-sandbox.png",
            "test_write_dirs_ui": "F3-schreibrechte.png",
        }
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "screenshots"
            environment = os.environ.copy()
            environment["VIBE_VERIFY_SCREENSHOT_DIR"] = str(target)
            code = (
                "import sys\n"
                f"sys.path.insert(0, {str(BROWSER)!r})\n"
                "name = sys.argv[1]\n"
                "module = __import__(name)\n"
                "print(module.SHOT)\n"
            )
            for module, filename in modules.items():
                result = subprocess.run(
                    [sys.executable, "-c", code, module],
                    cwd=str(REPO),
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env=environment,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(Path(result.stdout.strip()), target / filename)


class RepositoryVerifyTest(unittest.TestCase):
    def test_repository_quick_check_passes(self):
        result = run_verify("quick")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK: Prüfung 'quick'", result.stdout)
        self.assertIn("import-manifest", result.stdout)


if __name__ == "__main__":
    unittest.main()
