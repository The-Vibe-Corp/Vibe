"""Tests für die isolierte Projektprüfung (V-002).

Die Tests bauen eigene Fixture-Projekte in temporären Verzeichnissen. Sie
prüfen Erfolg, beabsichtigten Fehlschlag, unbekannte Modi, fehlende Werkzeuge,
die Testvollständigkeit im Vollmodus sowie die Isolation von HOME, VIBE und
Ports. F31 ergänzt den Mittelmodus ``package``. AP5-Korbat (T-V1) entkoppelt
ihn vom Vollmodus: ``package`` verlangt einen Testnachweis nur noch bei
gesetztem ``VERIFY_PACKAGE_TESTS``; ``VERIFY_TESTS`` steuert ausschließlich
``full``. T-V2 verkürzt den temporären Präfix auf ``vv-`` und erlaubt über
``VIBE_VERIFY_TMP`` einen eigenen Elternordner. Die produktive Konfiguration
des Aufrufers wird dabei nur gelesen.

AP7-Korbat (T-V16) macht ``scripts/verify.sh quick|package|full`` zur
einzigen Prüfschnittstelle: ``VERIFY_QUICK`` ist der einzige ausgeführte
Konfigurationsbefehl. ``package`` führt ``VERIFY_QUICK`` aus (plus optionalen
Testnachweis bei ``VERIFY_PACKAGE_TESTS``), ``full`` baut den Testlauf selbst
über ``run-tests-parallel.py`` aus ``VERIFY_TESTS``/``--tests``.
``VERIFY_PACKAGE`` und ``VERIFY_FULL`` sind keine Befehlsvariablen der Engine
mehr; ``VERIFY_TEST_PATTERN`` entfällt, weil die Zählung aus dem
strukturierten Läuferbericht kommt. Die betroffenen Fälle prüfen dieselbe
Fachlichkeit (Nachweiszwang, Zählung, Ausführung) gegen die neue Semantik;
alle übrigen Zusicherungen bleiben unverändert.
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
