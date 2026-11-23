"""AP7-Korbat — T-V13/T-V16: Selbstreferenz-Guards, Frontend/Engine, CLI.

Die Fälle leiten sich aus TICKETS.md (AP7-Korbat), dem AP12-Audit (T-V13,
T-V16) und dem AP7-Design-Brief ab, nicht aus einem Implementierungsdiff:

* Selbstreferenz: ``VERIFY_QUICK``, der einzige ausgeführte
  Konfigurationsbefehl, darf nicht auf ``verify.sh``, ``verify.py`` oder
  ``verify_engine.py`` zeigen. Ein solcher Lauf endet mit Exit 3 und klarer
  Meldung, ohne Rekursion. Nicht auflösbare Tokens mit passendem Basisnamen
  werden fail-safe ebenfalls abgelehnt. Jeder Aufruf ist mit einem
  Subprozess-Zeitlimit begrenzt (B1-Falle).
* ``VIBE_VERIFY_DEPTH``: Wert ≥ 2 endet mit Exit 3; Wert 1 ist ein legitimer
  geschachtelter Lauf. Die ausgeführte Prüfung erhält die Tiefe + 1.
* ``full`` liest ``VERIFY_FULL`` nicht als Befehl, sondern baut den Testlauf
  selbst über ``run-tests-parallel.py``/``VERIFY_TESTS``; ein
  selbstreferenzierender ``VERIFY_FULL``-Wert ruft die Prüfung nicht erneut
  auf. ``VERIFY_TEST_PATTERN`` entfällt.
* ``package`` führt den Inhalt von ``VERIFY_QUICK`` aus; ``VERIFY_PACKAGE``
  wird nicht mehr als Befehl ausgeführt.
* CLI-Vertrag: ``--tests/--jobs/--timeout/--baseline/--env/--min-tests/
  --write-baseline`` werden geparst; unbekannte Optionen und fehlende Werte
  enden mit Exit 2.
* ``scripts/verify.py`` bleibt als dünner Compat-Shim nutzbar und liefert
  dieselben Exitcodes wie ``scripts/verify.sh``.

Alle Läufe verwenden temporäre Fixture-Projekte mit eigenem HOME/VIBE; es
werden keine echten Modell- oder MCP-Aufrufe und keine produktiven Pfade
verwendet.

Run:

    python3 -m unittest tests.unit.test_ap7_korbat_verify -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ap7_verify_support as support  # noqa: E402

REPO = support.REPO
VERIFY = support.VERIFY
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
        text = VERIFY.read_text(encoding="utf-8")
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
        self.assert_guard_rejected("bash %s quick" % VERIFY, "verify.sh")

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
