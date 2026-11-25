"""Prüfskript: Architektur, Shim-Kompatibilität, Modi und CLI-Vertrag.

Aufruf: python3 -m unittest tests.unit.test_verify_script -v
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
    """Vollmodus: Der Läufer baut den Testlauf selbst (AP7-Korbat, T-V16).

    ``full`` führt ``VERIFY_FULL`` nicht mehr aus, sondern startet
    ``run-tests-parallel.py`` mit den Specs aus ``VERIFY_TESTS``. Die Zählung
    stammt aus dem Läuferbericht; ``VERIFY_TEST_PATTERN`` wird nicht mehr
    ausgewertet.
    """

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
        # Ein gesetztes VERIFY_FULL ist kein Testnachweis mehr: ohne
        # VERIFY_TESTS-Spezifikation fehlt der Nachweis (Exit 6).
        project = make_project(
            self.base,
            ["TYPE=generic", 'VERIFY_FULL="true"'],
        )
        result = run_verify("full", project=project)
        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        self.assertIn("VERIFY_TESTS", result.stdout + result.stderr)

    def test_full_rejects_a_run_without_executed_tests(self):
        """Ein Lauf ohne ausgeführte Tests ist kein bestandener Nachweis.

        Vorbedingung: ``VERIFY_TESTS="tests"``; das einzige Testmodul enthält
        keinen Testfall (``Ran 0 tests``).
        Aktion: ``full`` ausführen.
        Erwartung: Exit 6; die Meldung nennt 0 Tests.
        Fehlerfall: Ein leerer Lauf gilt als Vollnachweis.
        """
        project = self.make_test_project(
            ["TYPE=generic", 'VERIFY_TESTS="tests"'],
            "import unittest\n\n# Dieses Modul enthält keinen Testfall.\n",
        )
        result = run_verify("full", project=project)
        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        self.assertIn("0", result.stdout + result.stderr)
        self.assertIn("Tests", result.stdout + result.stderr)

    def test_full_passes_with_real_tests_and_reports_the_count(self):
        project = self.make_test_project(
            ["TYPE=generic", 'VERIFY_TESTS="tests"'],
            "import unittest\n\n"
            "class BeispielTest(unittest.TestCase):\n"
            "    def test_summe(self):\n"
            "        self.assertEqual(1 + 1, 2)\n",
        )
        result = run_verify("full", project=project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # Die Testanzahl steht in der maschinenlesbaren Abschlusszeile
        # (AP7-Korbat: ``VERIFY_RESULT: mode=full tests=N …``).
        self.assertRegex(result.stdout, r"(?m)^VERIFY_RESULT: .*\btests=1\b")
        self.assertIn("OK: Prüfung 'full'", result.stdout)

    def test_full_rejects_fewer_tests_than_configured(self):
        project = self.make_test_project(
            ["TYPE=generic", 'VERIFY_TESTS="tests"', "VERIFY_MIN_TESTS=2"],
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
    belegbaren Modus. AP7-Korbat (T-V16) vereinheitlicht die
    Prüfschnittstelle: ``package`` führt ``VERIFY_QUICK`` aus; ``VERIFY_PACKAGE``
    ist keine Befehlsvariable der Engine mehr. AP5-Korbat (T-V1) entkoppelt den
    Nachweis vom Vollmodus: Nur ein gesetztes ``VERIFY_PACKAGE_TESTS`` verlangt
    Testdateien, eine Mindestanzahl und Exit 6 bei Verstoß. ``VERIFY_TESTS``
    gilt ausschließlich für ``full``; ein gesetztes ``VERIFY_TESTS`` macht
    ``package`` nicht nachweispflichtig. Ohne ``VERIFY_PACKAGE_TESTS`` besteht
    kein Nachweiszwang wie in ``quick``.
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

    def test_package_runs_verify_quick_instead_of_package_or_full(self):
        """Vorbedingung: ``VERIFY_QUICK``, ``VERIFY_FULL`` und
        ``VERIFY_PACKAGE`` sind unterscheidbare Marker-Befehle.
        Aktion: ``package`` ausführen.
        Erwartung: Exit 0; der ``VERIFY_QUICK``-Marker erscheint, die Marker
        von ``VERIFY_PACKAGE`` und ``VERIFY_FULL`` nicht.
        Fehlerfall: ``package`` führt weiterhin ``VERIFY_PACKAGE`` aus oder
        fällt still auf eine andere Stufe zurück.
        """
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
        self.assertIn("quick-pruefung", result.stdout)
        # Kein stiller Rückfall auf die anderen Stufen.
        self.assertNotIn("paket-pruefung", result.stdout)
        self.assertNotIn("full-pruefung", result.stdout)

    def test_package_requires_verify_quick_without_falling_back(self):
        """Vorbedingung: ``VERIFY_QUICK`` fehlt; ``VERIFY_PACKAGE`` und
        ``VERIFY_FULL`` würden eine Markerdatei anlegen.
        Aktion: ``package`` ausführen.
        Erwartung: Exit 3; die Meldung nennt ``VERIFY_QUICK``; keine der
        Markerdateien entsteht.
        Fehlerfall: ``package`` akzeptiert die alten Befehlsvariablen.
        """
        marker = self.base / "quick-oder-full-lief"
        project = make_project(
            self.base,
            [
                "TYPE=generic",
                f'VERIFY_PACKAGE="touch {marker}"',
                f'VERIFY_FULL="touch {marker}"',
            ],
        )

        result = run_verify("package", project=project)

        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("VERIFY_QUICK", result.stdout + result.stderr)
        self.assertFalse(
            marker.exists(),
            "package darf ohne VERIFY_QUICK nicht package oder full ausführen",
        )

    def test_package_rejects_a_todo_placeholder(self):
        project = make_project(
            self.base,
            ["TYPE=generic", 'VERIFY_QUICK="echo TODO"'],
        )

        result = run_verify("package", project=project)

        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("VERIFY_QUICK", result.stdout + result.stderr)
        self.assertIn("TODO", result.stdout + result.stderr)

    def test_package_requires_test_files_when_package_tests_is_set(self):
        """Vorbedingung: ``VERIFY_PACKAGE_TESTS="tests"``, aber kein
        Testordner im Projekt.
        Aktion: ``package`` ausführen.
        Erwartung: Exit 6 (der Nachweiszwang stammt aus der Paket-Einstellung).
        Fehlerfall: fehlende Teststruktur wird als Erfolg gewertet.
        """
        project = make_project(
            self.base,
            [
                "TYPE=generic",
                'VERIFY_QUICK="true"',
                'VERIFY_PACKAGE_TESTS="tests"',
            ],
        )

        result = run_verify("package", project=project)

        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)

    def test_package_rejects_a_run_without_executed_tests(self):
        """Vorbedingung: ``VERIFY_PACKAGE_TESTS="tests"``; das einzige
        Testmodul enthält keinen Testfall („Ran 0 tests“).
        Aktion: ``package`` ausführen.
        Erwartung: Exit 6; die Meldung nennt 0 Tests.
        Fehlerfall: ein Lauf ohne ausgeführte Tests gilt als Nachweis.
        """
        project = self.make_test_project(
            ["TYPE=generic", 'VERIFY_QUICK="true"', 'VERIFY_PACKAGE_TESTS="tests"'],
            test_source="import unittest\n\n# Dieses Modul enthält keinen "
                        "Testfall.\n",
        )

        result = run_verify("package", project=project)

        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        self.assertIn("0", result.stdout + result.stderr)
        self.assertIn("Tests", result.stdout + result.stderr)

    def test_package_passes_with_real_tests_and_reports_the_count(self):
        """Vorbedingung: ``VERIFY_PACKAGE_TESTS="tests"`` und echte Tests, die
        der eingebaute Testläufer ausführt.
        Aktion: ``package`` ausführen.
        Erwartung: Exit 0; „Tests erkannt: 1“.
        Fehlerfall: Nachweis wird nicht gezählt.
        """
        project = self.make_test_project(
            ["TYPE=generic", 'VERIFY_QUICK="true"', 'VERIFY_PACKAGE_TESTS="tests"']
        )

        result = run_verify("package", project=project)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Tests erkannt: 1", result.stdout)
        self.assertIn("OK: Prüfung 'package'", result.stdout)

    def test_package_rejects_fewer_tests_than_configured(self):
        """Vorbedingung: ``VERIFY_PACKAGE_TESTS="tests"``,
        ``VERIFY_MIN_TESTS=2`` und nur ein ausgeführter Test.
        Aktion: ``package`` ausführen.
        Erwartung: Exit 6 mit „Minimum 2“.
        Fehlerfall: zu wenige Tests gelten als bestanden.
        """
        project = self.make_test_project(
            [
                "TYPE=generic",
                'VERIFY_QUICK="true"',
                'VERIFY_PACKAGE_TESTS="tests"',
                "VERIFY_MIN_TESTS=2",
            ]
        )

        result = run_verify("package", project=project)

        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        self.assertIn("Minimum 2", result.stdout + result.stderr)

    def test_package_without_package_tests_requires_no_test_proof(self):
        """Vorbedingung: kein ``VERIFY_PACKAGE_TESTS``; nur der statische
        ``VERIFY_QUICK``-Befehl.
        Aktion: ``package`` ausführen.
        Erwartung: Exit 0; der Befehl läuft, kein Testnachweis wird verlangt.
        Fehlerfall: statische Paketprüfung wird ohne Teststruktur abgelehnt.
        """
        project = make_project(
            self.base,
            ["TYPE=generic", 'VERIFY_QUICK="echo ohne-testnachweis"'],
        )

        result = run_verify("package", project=project)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ohne-testnachweis", result.stdout)
        self.assertIn("OK: Prüfung 'package'", result.stdout)

    def test_package_stays_static_even_when_verify_tests_is_set(self):
        """Vorbedingung: ``VERIFY_TESTS="tests"`` ist gesetzt (Vollmodus-
        Einstellung), ``VERIFY_PACKAGE_TESTS`` fehlt; kein Testordner.
        Aktion: ``package`` ausführen.
        Erwartung: Exit 0; der statische ``VERIFY_QUICK``-Befehl genügt. Die
        Vollmodus-Einstellung darf den Paketmodus nicht nachweispflichtig
        machen (Entkopplung T-V1).
        Fehlerfall: ``package`` verlangt wegen ``VERIFY_TESTS`` Testdateien.
        """
        project = make_project(
            self.base,
            [
                "TYPE=generic",
                'VERIFY_QUICK="echo paket-statisch"',
                'VERIFY_TESTS="tests"',
            ],
        )

        result = run_verify("package", project=project)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("paket-statisch", result.stdout)
        self.assertIn("OK: Prüfung 'package'", result.stdout)

    def test_full_still_requires_verify_tests_and_ignores_verify_package_tests(self):
        """Vorbedingung: ``VERIFY_FULL`` und ``VERIFY_PACKAGE_TESTS`` sind
        gesetzt, ``VERIFY_TESTS`` fehlt.
        Aktion: ``full`` ausführen.
        Erwartung: Exit 6; die Meldung verlangt ``VERIFY_TESTS``. Die
        Paket-Einstellung und ein gesetztes VERIFY_FULL ersetzen den
        Vollnachweis nicht.
        Fehlerfall: ``full`` akzeptiert die Paket-Einstellung als Nachweis.
        """
        project = self.make_test_project(
            [
                "TYPE=generic",
                'VERIFY_FULL="python3 -m unittest discover -s tests -v"',
                'VERIFY_PACKAGE_TESTS="tests"',
            ]
        )

        result = run_verify("full", project=project)

        self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
        self.assertIn("VERIFY_TESTS", result.stdout + result.stderr)

    def test_help_names_the_package_test_key(self):
        """Vorbedingung: ``--help``.
        Aktion: Hilfe ausgeben.
        Erwartung: ``VERIFY_PACKAGE_TESTS`` wird genannt.
        Fehlerfall: Die neue Entkopplung ist nicht dokumentiert.
        """
        result = run_verify("--help")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("VERIFY_PACKAGE_TESTS", result.stdout)

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
            ["TYPE=generic", 'VERIFY_QUICK="echo paket-ohne-dienst"'],
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


class VerifyTempDirectoryTest(unittest.TestCase):
    """T-V2: kurzer Präfix ``vv-`` und optionaler Elternordner ``VIBE_VERIFY_TMP``."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.tmpdir = self.base / "tmpdir"
        self.tmpdir.mkdir()

    def temp_dir_from_output(self, output):
        match = re.search(r"Prüfverzeichnis: (\S+)", output)
        self.assertIsNotNone(match, output)
        return Path(match.group(1))

    def test_default_temp_directory_uses_the_short_prefix(self):
        """Vorbedingung: Prüfung ohne ``VIBE_VERIFY_TMP``; ``TMPDIR`` zeigt auf
        ein eigenes Temp-Verzeichnis.
        Aktion: ``quick --keep`` ausführen, damit der Pfad sichtbar bleibt.
        Erwartung: Der Verzeichnisname beginnt mit ``vv-`` (nicht mit dem alten
        langen ``vibe-verify-``).
        Fehlerfall: langer Präfix bleibt (tmux-Socket-Limit).
        """
        project = make_project(
            self.base, ["TYPE=generic", 'VERIFY_QUICK="true"'])

        result = run_verify(
            "quick", "--keep", project=project, env={"TMPDIR": str(self.tmpdir)}
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        kept = self.temp_dir_from_output(result.stdout)
        self.assertTrue(kept.name.startswith("vv-"), kept.name)
        self.assertFalse(kept.name.startswith("vibe-verify-"), kept.name)
        self.assertEqual(kept.resolve().parent, self.tmpdir.resolve())

    def test_vibe_verify_tmp_places_the_directory_under_the_configured_folder(self):
        """Vorbedingung: ``VIBE_VERIFY_TMP`` zeigt auf einen eigenen Ordner.
        Aktion: ``quick --keep`` ausführen.
        Erwartung: Das Prüfverzeichnis liegt direkt unterhalb dieses Ordners und
        nutzt den kurzen Präfix.
        Fehlerfall: ``VIBE_VERIFY_TMP`` wird ignoriert.
        """
        verify_tmp = self.base / "kurz"
        verify_tmp.mkdir()
        project = make_project(
            self.base, ["TYPE=generic", 'VERIFY_QUICK="true"'])

        result = run_verify(
            "quick", "--keep", project=project,
            env={"VIBE_VERIFY_TMP": str(verify_tmp)},
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        kept = self.temp_dir_from_output(result.stdout)
        self.assertEqual(kept.resolve().parent, verify_tmp.resolve())
        self.assertTrue(kept.name.startswith("vv-"), kept.name)
        self.assertTrue(kept.is_dir())

    def test_vibe_verify_tmp_is_still_cleaned_up_without_keep(self):
        """Vorbedingung: ``VIBE_VERIFY_TMP`` gesetzt; Erfolg ohne ``--keep``.
        Aktion: ``quick`` ausführen.
        Erwartung: Das Prüfverzeichnis wird entfernt, der konfigurierte
        Elternordner bleibt bestehen (Aufräumen unverändert).
        Fehlerfall: Das kurze Verzeichnis bleibt liegen oder der Elternordner
        wird gelöscht.
        """
        verify_tmp = self.base / "kurz"
        verify_tmp.mkdir()
        project = make_project(
            self.base, ["TYPE=generic", 'VERIFY_QUICK="true"'])

        result = run_verify(
            "quick", project=project,
            env={"VIBE_VERIFY_TMP": str(verify_tmp)},
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        used = self.temp_dir_from_output(result.stdout)
        self.assertFalse(used.exists(), "Prüfverzeichnis wurde nicht entfernt")
        self.assertTrue(verify_tmp.is_dir(), "Elternordner darf bleiben")


class ScreenshotIsolationTest(unittest.TestCase):
    def test_browser_screenshots_honor_the_verify_directory(self):
        modules = {
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


# ===========================================================================
# T-/T-: Selbstreferenz-Guards, Frontend/Engine, CLI
# ===========================================================================

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_support as support  # noqa: E402

REPO_ap7 = support.REPO
VERIFY_ap7 = support.VERIFY
VERIFY_PY = support.VERIFY_PY
ENGINE = support.ENGINE

OBSERVE_DEPTH = (
    "import os\n"
    "print('TIEFE=' + str(os.environ.get('VIBE_VERIFY_DEPTH')))\n"
)


class ArchitectureTest(unittest.TestCase):
    """T-V16: Frontend ``verify.sh`` + Kern ``verify_engine.py`` + Shim."""

    def test_engine_module_exists_and_frontend_uses_it(self):
        """Vorbedingung: ``scripts/verify.sh`` und ``scripts/verify_engine.py``.
        Aktion: Dateien lesen.
        Erwartung: Die Engine existiert; das Frontend verweist auf sie.
        Fehlerfall: Keine Trennung, das Frontend bliebe die alte Logik.
        """
        self.assertTrue(ENGINE.is_file(), "scripts/verify_engine.py fehlt")
        text = VERIFY_ap7.read_text(encoding="utf-8")
        self.assertIn("verify_engine.py", text,
                      "verify.sh leitet nicht an verify_engine.py weiter")

    def test_verify_py_is_a_delegating_compat_shim(self):
        """Vorbedingung: ``scripts/verify.py``.
        Aktion: Quelle lesen.
        Erwartung: Der Shim delegiert per ``execv`` an ``verify_engine.py``
        und trägt keine eigene Prüflogik.
        Fehlerfall: ``verify.py`` bleibt eine zweite Implementierung.
        """
        text = VERIFY_PY.read_text(encoding="utf-8")
        self.assertIn("verify_engine.py", text,
                      "verify.py delegiert nicht an verify_engine.py")
        self.assertIn("execv", text,
                      "verify.py muss mit os.execv denselben argv übergeben")


class ShimCompatibilityTest(support.VerifyFixture):
    """T-V16: ``python3 scripts/verify.py`` bleibt gültiger Aufrufer."""

    def test_verify_py_and_verify_sh_agree_on_unknown_mode(self):
        for runner in (support.run_verify, support.run_verify_py):
            with self.subTest(runner=runner.__name__):
                result = runner("unbekannt", env=self.env())
                self.assertEqual(2, result.returncode,
                                 support.output(result))

    def test_verify_py_and_verify_sh_agree_on_missing_configuration(self):
        empty = self.base / "ohne-konfiguration"
        empty.mkdir()
        for runner in (support.run_verify, support.run_verify_py):
            with self.subTest(runner=runner.__name__):
                result = runner("quick", project=empty, env=self.env())
                self.assertEqual(3, result.returncode,
                                 support.output(result))
                self.assertIn("project.env", support.output(result))

    def test_verify_py_and_verify_sh_agree_on_a_successful_quick_run(self):
        project = self.make_project(["TYPE=generic", 'VERIFY_QUICK="true"'])
        for runner in (support.run_verify, support.run_verify_py):
            with self.subTest(runner=runner.__name__):
                result = runner("quick", project=project, env=self.env())
                self.assertEqual(0, result.returncode,
                                 support.output(result))


class SelfReferenceGuardTest(support.VerifyFixture):
    """T-V13: Selbstpfad-Wächter für ``VERIFY_QUICK`` (B1-Rekursionsfalle)."""

    def assert_guard_rejected(self, command, expected_token="verify"):
        project = self.make_project(
            ["TYPE=generic", 'VERIFY_QUICK="%s"' % command]
        )
        # Subprozess-Zeitlimit: Eine fehlende Sperre darf den Test nie
        # endlos rekursiv laufen lassen (B1).
        result = self.verify("quick", project=project, timeout=120)
        text = support.output(result)
        self.assertEqual(3, result.returncode, text)
        self.assertIn("VERIFY_QUICK", text,
                      "Die Meldung muss die Variable nennen:\n" + text)
        self.assertRegex(
            text.lower(),
            r"rekursion|rekursiv",
            "Die Meldung muss auf die Rekursionsfalle hinweisen:\n" + text,
        )
        self.assertIn(expected_token, text)

    def test_quick_pointing_to_this_verify_sh_is_rejected(self):
        """Vorbedingung: ``VERIFY_QUICK`` ruft genau dieses verify.sh auf.
        Aktion: ``quick`` ausführen (Zeitlimit).
        Erwartung: Exit 3, Meldung nennt Variable und Rekursionsfalle; kein
        zweiter Prüflauf.
        Fehlerfall: Endlose Selbstrekursion (B1).
        """
        self.assert_guard_rejected("bash %s quick" % VERIFY_ap7, "verify.sh")

    def test_quick_with_relative_self_path_is_rejected(self):
        """Vorbedingung: ``VERIFY_QUICK`` enthält den relativen Pfad
        ``scripts/verify.sh`` (Aufruf aus der Projektwurzel).
        Aktion: ``quick`` ausführen.
        Erwartung: Exit 3; der relative Pfad wird nicht als fremder Befehl
        geduldet.
        Fehlerfall: Der Wächter prüft nur absolute Pfade.
        """
        self.assert_guard_rejected("bash scripts/verify.sh quick")

    def test_quick_with_unresolvable_verify_basename_is_rejected(self):
        """Vorbedingung: ``VERIFY_QUICK`` nennt ``gibtsnicht/verify.sh``.
        Aktion: ``quick`` ausführen.
        Erwartung: Exit 3 (fail-safe, obwohl das Token nicht auflösbar ist).
        Fehlerfall: Unbekannter Pfad wird ausgeführt.
        """
        self.assert_guard_rejected("bash gibtsnicht/verify.sh quick")

    def test_quick_pointing_to_verify_py_is_rejected(self):
        """Vorbedingung: ``VERIFY_QUICK`` ruft ``scripts/verify.py`` auf.
        Aktion: ``quick`` ausführen.
        Erwartung: Exit 3; auch der Compat-Shim ist ein laufendes Skript.
        Fehlerfall: Nur verify.sh gilt als geschützt.
        """
        self.assert_guard_rejected(
            "python3 %s quick" % VERIFY_PY, "verify.py"
        )

    def test_quick_pointing_to_verify_engine_is_rejected(self):
        """Vorbedingung: ``VERIFY_QUICK`` ruft ``verify_engine.py`` auf.
        Aktion: ``quick`` ausführen.
        Erwartung: Exit 3.
        Fehlerfall: Der Kern ist nicht als laufendes Skript erkannt.
        """
        self.assert_guard_rejected(
            "python3 %s quick" % ENGINE, "verify_engine.py"
        )

    def test_depth_two_is_rejected_as_recursion(self):
        """Vorbedingung: ``VIBE_VERIFY_DEPTH=2`` in der Umgebung.
        Aktion: ``quick`` mit einem harmlosen Befehl ausführen.
        Erwartung: Exit 3 mit Rekursionsmeldung; der Befehl läuft nicht.
        Fehlerfall: Verschachtelung wird unbegrenzt fortgesetzt.
        """
        project = self.make_project(
            ["TYPE=generic", 'VERIFY_QUICK="touch sollte_nicht_laufen"']
        )
        result = self.verify(
            "quick", project=project, VIBE_VERIFY_DEPTH=2
        )
        text = support.output(result)
        self.assertEqual(3, result.returncode, text)
        self.assertIn("VIBE_VERIFY_DEPTH", text)
        self.assertRegex(text.lower(), r"rekursion|rekursiv|tiefe")
        self.assertFalse((project / "sollte_nicht_laufen").exists(),
                         "Der Prüfbefehl lief trotz Tiefenwächter")

    def test_depth_one_runs_normally_and_increments_the_child_depth(self):
        """Vorbedingung: ``VIBE_VERIFY_DEPTH=1`` (legitimer geschachtelter
        Lauf, z. B. eine Fixture innerhalb eines Volllaufs).
        Aktion: ``quick`` mit einem Beobachter ausführen.
        Erwartung: Exit 0; die ausgeführte Prüfung sieht die Tiefe 2.
        Fehlerfall: Tiefe 1 wird fälschlich blockiert oder nicht erhöht.
        """
        project = self.make_project(
            ["TYPE=generic", 'VERIFY_QUICK="python3 tiefe.py"']
        )
        self.write_module(project, "tiefe.py", OBSERVE_DEPTH)
        result = self.verify(
            "quick", project=project, VIBE_VERIFY_DEPTH=1
        )
        text = support.output(result)
        self.assertEqual(0, result.returncode, text)
        self.assertIn("TIEFE=2", text,
                      "Die Prüfung erhielt nicht VIBE_VERIFY_DEPTH = 1 + 1:\n"
                      + text)


class FullModeTest(support.VerifyFixture):
    """T-V16: ``full`` baut den Testlauf selbst und liest VERIFY_FULL nicht."""

    def test_full_ignores_verify_full_as_a_command_and_hints(self):
        """Vorbedingung: ``VERIFY_FULL`` ist ein fremder Befehl mit
        Marker, ``VERIFY_TESTS`` zeigt auf grüne Tests.
        Aktion: ``full`` ausführen.
        Erwartung: Exit 0, der Marker des VERIFY_FULL-Befehls erscheint
        nicht (er wurde nicht ausgeführt); die Ausgabe weist auf VERIFY_FULL
        hin (Hinweis, kein Fehler).
        Fehlerfall: ``full`` führt weiterhin VERIFY_FULL aus.
        """
        project = self.make_project(
            [
                "TYPE=generic",
                'VERIFY_FULL="echo AP7-JUNK-FULL"',
                'VERIFY_TESTS="tests"',
            ]
        )
        self.write_module(project, "tests/test_gut.py", support.GREEN_TEST)
        result = self.verify("full", project=project)
        text = support.output(result)
        self.assertEqual(0, result.returncode, text)
        self.assertNotIn("AP7-JUNK-FULL", text,
                         "VERIFY_FULL wurde als Befehl ausgeführt:\n" + text)
        self.assertIn("VERIFY_FULL", text,
                      "Der Hinweis auf den nicht gelesenen VERIFY_FULL fehlt")

    def test_full_runs_the_built_in_parallel_runner(self):
        """Vorbedingung: grüne Tests in ``VERIFY_TESTS``.
        Aktion: ``full`` ausführen.
        Erwartung: Exit 0; die Ausgabe stammt vom eingebauten Läufer
        (Modulblock und ``Gesamt:``-Zeile).
        Fehlerfall: ``full`` ruft einen frei konfigurierten Befehl auf.
        """
        project = self.make_project(
            ["TYPE=generic", 'VERIFY_TESTS="tests"']
        )
        self.write_module(project, "tests/test_gut.py", support.GREEN_TEST)
        result = self.verify("full", project=project)
        text = support.output(result)
        self.assertEqual(0, result.returncode, text)
        self.assertIn("--- tests.test_gut ---", text)
        self.assertIn("Gesamt:", text)
        self.assertIn("AP7-GRUEN-GELAUFEN", text)

    def test_full_does_not_recurse_when_verify_full_names_verify_sh(self):
        """Vorbedingung: ``VERIFY_FULL="bash scripts/verify.sh full"``
        (selbstreferenzierender Wrapper-Wert), ``VERIFY_TESTS`` grün.
        Aktion: ``full`` ausführen (Zeitlimit).
        Erwartung: Exit 0; der eingebaute Volllauf läuft genau einmal
        (eine ``Gesamt:``-Zeile), kein Selbstaufruf.
        Fehlerfall: Jede Instanz startet eine neue (B1).
        """
        project = self.make_project(
            [
                "TYPE=generic",
                'VERIFY_FULL="bash scripts/verify.sh full"',
                'VERIFY_TESTS="tests"',
            ]
        )
        self.write_module(project, "tests/test_gut.py", support.GREEN_TEST)
        result = self.verify("full", project=project, timeout=120)
        text = support.output(result)
        self.assertEqual(0, result.returncode, text)
        self.assertEqual(1, text.count("Gesamt:"),
                         "Der Volllauf lief mehrfach (Selbstaufruf):\n" + text)
        self.assertIn("AP7-GRUEN-GELAUFEN", text)

    def test_verify_test_pattern_is_not_evaluated(self):
        """Vorbedingung: ``VERIFY_TEST_PATTERN`` ist ein ungültiger Ausdruck
        und würde 0 Tests zählen; die Tests sind grün.
        Aktion: ``full`` ausführen.
        Erwartung: Exit 0 — die Zählung kommt aus dem Testläufer-Bericht,
        nicht mehr aus dem Muster.
        Fehlerfall: ``VERIFY_TEST_PATTERN`` bleibt Pflicht oder wird
        ausgewertet.
        """
        project = self.make_project(
            [
                "TYPE=generic",
                'VERIFY_TESTS="tests"',
                'VERIFY_TEST_PATTERN="("',
            ]
        )
        self.write_module(project, "tests/test_gut.py", support.GREEN_TEST)
        result = self.verify("full", project=project)
        self.assertEqual(0, result.returncode, support.output(result))


class PackageModeTest(support.VerifyFixture):
    """T-V16: ``package`` führt VERIFY_QUICK aus, VERIFY_PACKAGE nie."""

    def test_package_does_not_execute_verify_package_as_a_command(self):
        """Vorbedingung: ``VERIFY_QUICK="true"``; ``VERIFY_PACKAGE`` würde
        eine Markerdatei anlegen.
        Aktion: ``package`` ausführen.
        Erwartung: Exit 0; die Markerdatei entsteht nicht.
        Fehlerfall: ``VERIFY_PACKAGE`` wird weiterhin als Befehl ausgeführt.
        """
        marker = self.base / "paket-befehl-lief"
        project = self.make_project(
            [
                "TYPE=generic",
                'VERIFY_QUICK="true"',
                'VERIFY_PACKAGE="touch %s"' % marker,
            ]
        )
        result = self.verify("package", project=project)
        self.assertEqual(0, result.returncode, support.output(result))
        self.assertFalse(marker.exists(),
                         "VERIFY_PACKAGE wurde als Befehl ausgeführt")


class CliContractTest(support.VerifyFixture):
    """T-V16: gemeinsamer CLI-Vertrag von Frontend/Engine."""

    def help_text(self):
        result = self.verify("--help")
        self.assertEqual(0, result.returncode, support.output(result))
        return result.stdout

    def test_help_lists_the_new_options(self):
        text = self.help_text()
        for option in (
            "--tests",
            "--jobs",
            "--timeout",
            "--baseline",
            "--env",
            "--min-tests",
            "--write-baseline",
        ):
            self.assertIn(option, text,
                          "%s fehlt in der Hilfe:\n%s" % (option, text))

    def test_tests_option_overrides_the_configured_specs(self):
        """Vorbedingung: ``VERIFY_TESTS`` zeigt auf ein rotes Modul; ein
        grünes Verzeichnis existiert daneben.
        Aktion: ``full --tests <grün>`` ausführen.
        Erwartung: Exit 0; nur das per Option genannte Modul läuft.
        Fehlerfall: ``--tests`` wird ignoriert.
        """
        project = self.make_project(
            ["TYPE=generic", 'VERIFY_TESTS="tests_rot"']
        )
        self.write_module(project, "tests_rot/test_rot.py", support.RED_TEST)
        self.write_module(project, "tests_gut/test_gut.py", support.GREEN_TEST)
        result = self.verify(
            "full", "--tests", "tests_gut", project=project
        )
        text = support.output(result)
        self.assertEqual(0, result.returncode, text)
        self.assertIn("AP7-GRUEN-GELAUFEN", text)
        self.assertNotIn("tests.test_rot", text)

    def test_multiple_tests_options_run_each_directory(self):
        project = self.make_project(["TYPE=generic", 'VERIFY_QUICK="true"'])
        self.write_module(
            project,
            "tests_a/test_a.py",
            "import unittest\n\n"
            "class ATest(unittest.TestCase):\n"
            "    def test_a(self):\n"
            "        print('AP7-DIR-A')\n",
        )
        self.write_module(
            project,
            "tests_b/test_b.py",
            "import unittest\n\n"
            "class BTest(unittest.TestCase):\n"
            "    def test_b(self):\n"
            "        print('AP7-DIR-B')\n",
        )
        result = self.verify(
            "full",
            "--tests", "tests_a",
            "--tests", "tests_b",
            project=project,
        )
        text = support.output(result)
        self.assertEqual(0, result.returncode, text)
        self.assertIn("AP7-DIR-A", text)
        self.assertIn("AP7-DIR-B", text)

    def test_numeric_and_label_options_are_accepted(self):
        project = self.make_project(
            ["TYPE=generic", 'VERIFY_TESTS="tests"']
        )
        self.write_module(project, "tests/test_gut.py", support.GREEN_TEST)
        result = self.verify(
            "full",
            "--tests", "tests",
            "--jobs", "1",
            "--timeout", "60",
            "--min-tests", "1",
            "--env", "lichter",
            project=project,
        )
        self.assertEqual(0, result.returncode, support.output(result))

    def test_baseline_option_is_accepted(self):
        baseline = self.base / "override-baseline.json"
        support.write_baseline(baseline, envs={}, min_tests=1)
        project = self.make_project(
            ["TYPE=generic", 'VERIFY_TESTS="tests"']
        )
        self.write_module(project, "tests/test_gut.py", support.GREEN_TEST)
        result = self.verify(
            "full", "--tests", "tests", "--baseline", str(baseline),
            project=project,
        )
        self.assertEqual(0, result.returncode, support.output(result))

    def test_unknown_option_is_a_usage_error(self):
        result = self.verify("full", "--quatsch")
        self.assertEqual(2, result.returncode, support.output(result))

    def test_option_without_value_is_a_usage_error(self):
        for option in (
            "--tests",
            "--jobs",
            "--timeout",
            "--baseline",
            "--env",
            "--min-tests",
        ):
            with self.subTest(option=option):
                result = self.verify("full", option)
                self.assertEqual(2, result.returncode,
                                 support.output(result))


if __name__ == "__main__":
    unittest.main()
