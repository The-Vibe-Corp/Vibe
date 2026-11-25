"""Paralleler Testlauf: Berichtsoption.

Aufruf: python3 -m unittest tests.unit.test_run_tests_parallel -v
"""


import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "scripts" / "run-tests-parallel.py"

HEADER_RE = re.compile(r"^--- (?P<module>tests(?:\.\w+)+) ---$", re.MULTILINE)
SUMMARY_RE = re.compile(
    r"^Gesamt: (?P<tests>\d+) Tests, (?P<passed>\d+)/(?P<modules>\d+) "
    r"Module bestanden, (?P<failed>\d+) fehlgeschlagen$",
    re.MULTILINE,
)
RAN_RE = re.compile(r"Ran (\d+) tests?")

TEST_A = (
    "import unittest\n\n"
    "class ATest(unittest.TestCase):\n"
    "    def test_eins(self):\n"
    "        self.assertTrue(True)\n"
    "    def test_zwei(self):\n"
    "        self.assertEqual(2 + 2, 4)\n"
)
TEST_B = (
    "import unittest\n\n"
    "class BTest(unittest.TestCase):\n"
    "    def test_drei(self):\n"
    "        self.assertEqual(3, 3)\n"
    "    def test_vier(self):\n"
    "        self.assertEqual(4, 4)\n"
    "    def test_fuenf(self):\n"
    "        self.assertTrue(True)\n"
)
TEST_C = (
    "import unittest\n\n"
    "class CTest(unittest.TestCase):\n"
    "    def test_sechs(self):\n"
    "        self.assertIn('a', 'abc')\n"
)
TEST_TOP = (
    "import unittest\n\n"
    "class TopTest(unittest.TestCase):\n"
    "    def test_sieben(self):\n"
    "        self.assertEqual(7, 7)\n"
    "    def test_acht(self):\n"
    "        self.assertTrue(True)\n"
)
TEST_NESTED = (
    "import unittest\n\n"
    "class NestedTest(unittest.TestCase):\n"
    "    def test_neun(self):\n"
    "        self.assertEqual(9, 9)\n"
    "    def test_zehn(self):\n"
    "        self.assertTrue(True)\n"
    "    def test_elf(self):\n"
    "        self.assertIn('b', 'abc')\n"
)
# Fixture-Modul für den Überlappungsnachweis: schreibt Start- und Endzeit
# seines eigenen Laufs in eine Datei unter dem vom Test vorgegebenen
# Verzeichnis. Der Läufer selbst bekommt dafür keine Schnittstelle; das
# Verzeichnis kommt über die geerbte Umgebung (F31_STAMP_DIR).
TEST_UEBERLAPPUNG = (
    "import os, time, unittest\n"
    "from pathlib import Path\n\n\n"
    "class UeberlappungTest(unittest.TestCase):\n"
    "    def test_schreibt_zeitfenster(self):\n"
    "        ziel = Path(os.environ['F31_STAMP_DIR']) / (Path(__file__).stem + '.stamp')\n"
    "        start = time.time()\n"
    "        time.sleep(0.75)\n"
    "        ziel.write_text(str(start) + '\\n' + str(time.time()) + '\\n',\n"
    "                        encoding='utf-8')\n"
    "        self.assertTrue(ziel.exists())\n"
)


TEST_LANGSAM = (
    "import time, unittest\n\n"
    "class LangsamTest(unittest.TestCase):\n"
    "    def test_langsam(self):\n"
    "        time.sleep(30)\n"
)

# Fixture-Modul für F1-6: Ein Modulprozess mit TTY als stdin ließ
# setup-vibe.py (trotz --yes) nach Installationsort/Logverzeichnis fragen und
# lief in den Timeout. Der Läufer muss den Modulen stdin=DEVNULL geben.
TEST_KEIN_TTY = (
    "import sys, unittest\n\n"
    "class KeinTtyTest(unittest.TestCase):\n"
    "    def test_stdin_ist_kein_terminal(self):\n"
    "        self.assertFalse(sys.stdin.isatty())\n"
)


class RunTestsParallelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.tests_dir = self.base / "tests"
        self.tests_dir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write_module(self, name, source):
        (self.tests_dir / (name + ".py")).write_text(source, encoding="utf-8")

    def write_standard_modules(self):
        self.write_module("test_a", TEST_A)
        self.write_module("test_b", TEST_B)
        self.write_module("test_c", TEST_C)

    def run_runner(self, *extra, timeout=180, env=None, stdin=None):
        return subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--dir",
                str(self.tests_dir),
                *extra,
            ],
            cwd=str(self.base),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            stdin=stdin,
        )

    def output(self, result):
        return result.stdout + result.stderr

    def summary(self, result):
        match = SUMMARY_RE.search(self.output(result))
        self.assertIsNotNone(
            match,
            "Abschlusszeile 'Gesamt: <n> Tests, <b>/<m> Module bestanden, "
            "<f> fehlgeschlagen' fehlt:\n" + self.output(result),
        )
        return {key: int(value) for key, value in match.groupdict().items()}

    def headers(self, result):
        return HEADER_RE.findall(self.output(result))

    def test_all_modules_run_and_report_their_tests(self):
        self.write_standard_modules()

        result = self.run_runner("--jobs", "3")

        self.assertEqual(result.returncode, 0, self.output(result))
        self.assertEqual(
            sorted(self.headers(result)),
            ["tests.test_a", "tests.test_b", "tests.test_c"],
        )
        # Jede Modulausführung bleibt mit ihrer eigenen "Ran"-Zeile erhalten.
        self.assertEqual(len(RAN_RE.findall(self.output(result))), 3)
        self.assertEqual(sum(int(count) for count in RAN_RE.findall(self.output(result))), 6)
        summary = self.summary(result)
        self.assertEqual(summary["tests"], 6)
        self.assertEqual(summary["modules"], 3)
        self.assertEqual(summary["passed"], 3)
        self.assertEqual(summary["failed"], 0)

    def test_module_processes_do_not_inherit_a_terminal_on_stdin(self):
        # F1-6: Auch wenn der Läufer selbst an einem TTY hängt, dürfen die
        # Modulprozesse kein TTY als stdin sehen. Sonst fragt setup-vibe.py
        # (trotz --yes) nach Installationsort/Logverzeichnis und blockiert.
        try:
            import pty
        except ImportError:
            self.skipTest("pty ist auf dieser Plattform nicht verfügbar")
        self.write_module("test_tty", TEST_KEIN_TTY)
        master, slave = pty.openpty()
        try:
            result = self.run_runner(stdin=slave)
        finally:
            os.close(master)
            os.close(slave)

        self.assertEqual(result.returncode, 0, self.output(result))
        self.assertEqual(self.summary(result)["failed"], 0, self.output(result))

    def test_default_runs_modules_with_overlapping_execution_windows(self):
        # Deterministischer Parallelitätsnachweis ohne Wanduhrschwelle: Die
        # Fixture-Module schreiben je Start- und Endzeit ihres eigenen Laufs.
        # Überschneiden sich mindestens zwei Zeitfenster, liefen mindestens
        # zwei Module gleichzeitig. Ein langsamer Rechner verschiebt nur alle
        # Zeitstempel gemeinsam und macht den Test nicht flaky.
        stamp_dir = self.base / "stamps"
        stamp_dir.mkdir()
        for name in ("test_a", "test_b", "test_c"):
            self.write_module(name, TEST_UEBERLAPPUNG)
        env = dict(os.environ)
        env["F31_STAMP_DIR"] = str(stamp_dir)

        result = self.run_runner(env=env)

        self.assertEqual(result.returncode, 0, self.output(result))
        self.assertEqual(
            sorted(self.headers(result)),
            ["tests.test_a", "tests.test_b", "tests.test_c"],
        )
        windows = {}
        for name in ("test_a", "test_b", "test_c"):
            stamp = stamp_dir / (name + ".stamp")
            self.assertTrue(
                stamp.exists(),
                f"{name} hat kein Zeitfenster geschrieben:\n" + self.output(result),
            )
            start, end = (
                float(line) for line in stamp.read_text(encoding="utf-8").split()
            )
            windows[name] = (start, end)
        overlap = [
            (first, second)
            for first, (first_start, first_end) in windows.items()
            for second, (second_start, second_end) in windows.items()
            if first < second
            and min(first_end, second_end) > max(first_start, second_start)
        ]
        self.assertTrue(
            overlap,
            "Keine zwei Module liefen gleichzeitig; Zeitfenster: "
            + ", ".join(
                f"{name}={start:.3f}..{end:.3f}"
                for name, (start, end) in sorted(windows.items())
            ),
        )

    def test_nested_test_module_is_discovered_and_run(self):
        # unittest discover arbeitet rekursiv; der Läufer darf ein Modul in
        # einem Unterpaket nicht still auslassen (Vertrag: kein Testverlust).
        self.write_module("test_top", TEST_TOP)
        nested_dir = self.tests_dir / "verschachtelt"
        nested_dir.mkdir()
        # Paketmarker, damit "python3 -m unittest tests.verschachtelt.test_nested"
        # importierbar ist (dieselbe Voraussetzung wie bei unittest discover).
        (self.tests_dir / "__init__.py").write_text("", encoding="utf-8")
        (nested_dir / "__init__.py").write_text("", encoding="utf-8")
        (nested_dir / "test_nested.py").write_text(TEST_NESTED, encoding="utf-8")

        result = self.run_runner("--jobs", "2")
        text = self.output(result)

        self.assertEqual(result.returncode, 0, text)
        self.assertEqual(
            sorted(self.headers(result)),
            ["tests.test_top", "tests.verschachtelt.test_nested"],
        )
        self.assertIn("--- tests.test_top ---", text)
        self.assertIn("--- tests.verschachtelt.test_nested ---", text)
        self.assertEqual(len(RAN_RE.findall(text)), 2)
        self.assertEqual(sum(int(count) for count in RAN_RE.findall(text)), 5)
        summary = self.summary(result)
        self.assertEqual(summary["tests"], 5)
        self.assertEqual(summary["modules"], 2)
        self.assertEqual(summary["passed"], 2)
        self.assertEqual(summary["failed"], 0)

    def test_a_failing_module_is_named_and_its_output_stays_visible(self):
        self.write_standard_modules()
        self.write_module(
            "test_b",
            "import unittest\n\n"
            "class BTest(unittest.TestCase):\n"
            "    def test_drei(self):\n"
            "        self.assertEqual(3, 3)\n"
            "    def test_vier(self):\n"
            "        self.fail('absichtlich-kaputt')\n"
            "    def test_fuenf(self):\n"
            "        self.assertTrue(True)\n",
        )

        result = self.run_runner("--jobs", "2")
        text = self.output(result)

        self.assertEqual(result.returncode, 1, text)
        self.assertIn("tests.test_b", text)
        self.assertIn("absichtlich-kaputt", text)
        summary = self.summary(result)
        self.assertEqual(summary["tests"], 6)
        self.assertEqual(summary["modules"], 3)
        self.assertEqual(summary["passed"], 2)
        self.assertEqual(summary["failed"], 1)

    def test_a_module_with_an_import_error_counts_as_failed(self):
        self.write_standard_modules()
        self.write_module(
            "test_kaputt",
            "import modul_gibt_es_nicht_f31\n\n"
            "import unittest\n\n"
            "class KaputtTest(unittest.TestCase):\n"
            "    def test_egal(self):\n"
            "        self.assertTrue(True)\n",
        )

        result = self.run_runner("--jobs", "2")
        text = self.output(result)

        self.assertEqual(result.returncode, 1, text)
        self.assertIn("tests.test_kaputt", text)
        self.assertIn("modul_gibt_es_nicht_f31", text)
        summary = self.summary(result)
        self.assertEqual(summary["modules"], 4)
        self.assertEqual(summary["passed"], 3)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["tests"], 6, "bestandene Module gingen verloren")

    def test_jobs_one_is_sequential_and_equivalent(self):
        self.write_standard_modules()

        parallel = self.run_runner("--jobs", "3")
        sequential = self.run_runner("--jobs", "1")

        self.assertEqual(parallel.returncode, 0, self.output(parallel))
        self.assertEqual(sequential.returncode, 0, self.output(sequential))
        self.assertEqual(
            sorted(self.headers(parallel)), sorted(self.headers(sequential))
        )
        self.assertEqual(
            sum(int(count) for count in RAN_RE.findall(self.output(parallel))),
            sum(int(count) for count in RAN_RE.findall(self.output(sequential))),
        )
        self.assertEqual(self.summary(parallel), self.summary(sequential))

    def test_no_module_is_executed_twice(self):
        self.write_standard_modules()

        for jobs in ("1", "3"):
            with self.subTest(jobs=jobs):
                result = self.run_runner("--jobs", jobs)
                text = self.output(result)
                self.assertEqual(result.returncode, 0, text)
                headers = self.headers(result)
                self.assertEqual(
                    sorted(headers),
                    ["tests.test_a", "tests.test_b", "tests.test_c"],
                )
                self.assertEqual(len(RAN_RE.findall(text)), 3)
                self.assertEqual(
                    sum(int(count) for count in RAN_RE.findall(text)),
                    6,
                    "Summe der Ran-Zeilen passt nicht zur Fixture",
                )


    def test_timeout_aborts_a_hanging_module(self):
        # Rotphase nicht anwendbar: --timeout ist am Arbeitsbaum bereits
        # implementiert (Evidenzlücke, kein Verhaltens-Red-Test). Der Test
        # ist am aktuellen Stand grün und belegt den Timeout-Pfad.
        self.write_module("test_langsam", TEST_LANGSAM)

        result = self.run_runner("--timeout", "2", "--jobs", "1", timeout=60)
        text = self.output(result)

        self.assertEqual(result.returncode, 1, text)
        self.assertIn("--- tests.test_langsam ---", text)
        self.assertIn("TIMEOUT", text)
        self.assertIn("Fehlgeschlagene Module: tests.test_langsam", text)
        summary = self.summary(result)
        self.assertEqual(summary["tests"], 0)
        self.assertEqual(summary["passed"], 0)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["modules"], 1)


# ===========================================================================
# ``run-tests-parallel.py --report`` (T-)
# ===========================================================================

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


GREEN_ONE = (
    "import unittest\n\n"
    "class GruenTest(unittest.TestCase):\n"
    "    def test_eins(self):\n"
    "        self.assertTrue(True)\n"
    "    def test_zwei(self):\n"
    "        self.assertEqual(2 + 2, 4)\n"
)

RED_ONE = (
    "import unittest\n\n"
    "class RotTest(unittest.TestCase):\n"
    "    def test_drei(self):\n"
    "        self.fail('AP7-REPORT-ROT')\n"
)

ENTRY_KEYS = {
    "module",
    "tests",
    "passed",
    "returncode",
    "error_class",
    "error_message",
}

TIMING_RE = re.compile(r" in \d+\.\d+s")


def normalize(text):
    """Entfernt reine Laufzeitangaben für einen stabilen Textvergleich."""
    return TIMING_RE.sub("", text)


class ReportOptionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.tests_dir = self.base / "tests"
        self.tests_dir.mkdir()
        (self.tests_dir / "test_gut.py").write_text(GREEN_ONE, encoding="utf-8")
        (self.tests_dir / "test_rot.py").write_text(RED_ONE, encoding="utf-8")

    def run_runner(self, *extra, timeout=180):
        return subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--dir", str(self.tests_dir),
                *extra,
            ],
            cwd=str(self.base),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def report(self, name="report.json"):
        path = self.base / name
        self.assertTrue(path.is_file(), "Der JSON-Bericht wurde nicht geschrieben")
        return path, json.loads(path.read_text(encoding="utf-8"))

    def entries(self, data):
        return {entry["module"]: entry for entry in data["modules"]}

    def test_report_contains_a_module_entry_for_every_module(self):
        """Vorbedingung: ein grünes und ein rotes Testmodul.
        Aktion: ``--report`` ausführen.
        Erwartung: Exitcode 1 (rotes Modul, unverändert); der Bericht enthält
        je Modul einen Eintrag mit den vereinbarten Feldern und
        ``total_tests``.
        Fehlerfall: Ohne strukturierten Bericht kann die Engine nicht zählen
        und Baseline-Vergleiche anstellen.
        """
        result = self.run_runner("--report", str(self.base / "report.json"))

        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        _, data = self.report()
        self.assertIn("modules", data)
        self.assertIn("total_tests", data)
        by_module = self.entries(data)
        self.assertEqual({"tests.test_gut", "tests.test_rot"}, set(by_module))
        for entry in by_module.values():
            self.assertTrue(
                ENTRY_KEYS.issubset(entry),
                "Berichtseintrag unvollständig: %r" % entry,
            )

    def test_green_module_entry_has_count_and_no_error_details(self):
        """Vorbedingung: grünes Modul mit zwei Tests.
        Aktion: ``--report`` ausführen.
        Erwartung: ``tests=2``, ``passed`` wahr, ``returncode`` 0,
        ``error_class``/``error_message`` sind ``null``.
        Fehlerfall: Fehlerfelder stehen auch bei grünen Modulen.
        """
        result = self.run_runner("--report", str(self.base / "report.json"))
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        entry = self.entries(self.report()[1])["tests.test_gut"]
        self.assertEqual(2, entry["tests"])
        self.assertIs(True, entry["passed"])
        self.assertEqual(0, entry["returncode"])
        self.assertIsNone(entry["error_class"])
        self.assertIsNone(entry["error_message"])

    def test_red_module_entry_reports_class_and_message(self):
        """Vorbedingung: rotes Modul über ``self.fail("AP7-REPORT-ROT")``.
        Aktion: ``--report`` ausführen.
        Erwartung: ``passed`` falsch, ``returncode`` ungleich 0,
        ``error_class`` ist ``AssertionError`` und ``error_message`` enthält
        die Meldung.
        Fehlerfall: Ein unbekannter Fehler kann später nicht signiert werden.
        """
        result = self.run_runner("--report", str(self.base / "report.json"))
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        entry = self.entries(self.report()[1])["tests.test_rot"]
        self.assertIs(False, entry["passed"])
        self.assertNotEqual(0, entry["returncode"])
        self.assertEqual("AssertionError", entry["error_class"])
        self.assertIn("AP7-REPORT-ROT", entry["error_message"])

    def test_total_tests_matches_the_text_summary(self):
        """Vorbedingung: drei Tests in zwei Modulen.
        Aktion: ``--report`` ausführen.
        Erwartung: ``total_tests`` entspricht der Zahl der ``Gesamt:``-Zeile
        (Ran-N-Vertrag bleibt die Textwahrheit).
        Fehlerfall: Bericht und Textausgabe zählen unterschiedlich.
        """
        result = self.run_runner("--report", str(self.base / "report.json"))
        text = result.stdout + result.stderr
        match = re.search(r"^Gesamt: (\d+) Tests", text, re.MULTILINE)
        self.assertIsNotNone(match, text)
        _, data = self.report()
        self.assertEqual(int(match.group(1)), data["total_tests"])
        self.assertEqual(3, data["total_tests"])

    def test_text_output_and_exit_code_stay_unchanged_without_report(self):
        """Vorbedingung: gleiche Fixture mit und ohne ``--report``.
        Aktion: beide Läufe ausführen.
        Erwartung: gleicher Exitcode und gleicher Text abzüglich
        Laufzeitangaben; ohne ``--report`` entsteht keine Datei.
        Fehlerfall: Die neue Option verändert Ausgabe oder Exitcodes.
        """
        without = self.run_runner("--jobs", "1")
        self.assertEqual(
            [], sorted(self.base.glob("*.json")),
            "Ohne --report wurde eine JSON-Datei geschrieben",
        )

        target = self.base / "mit-report.json"
        with_report = self.run_runner(
            "--jobs", "1", "--report", str(target)
        )

        self.assertEqual(without.returncode, with_report.returncode)
        self.assertEqual(
            normalize(without.stdout + without.stderr),
            normalize(with_report.stdout + with_report.stderr),
        )
        self.assertTrue(target.is_file())

    def test_green_run_writes_a_report_and_exits_0(self):
        """Vorbedingung: nur grüne Module.
        Aktion: ``--report`` ausführen.
        Erwartung: Exit 0; alle Einträge bestanden, ``total_tests`` korrekt.
        Fehlerfall: Der Bericht erscheint nur im Fehlerfall.
        """
        (self.tests_dir / "test_rot.py").unlink()
        result = self.run_runner("--report", str(self.base / "gruen.json"))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        _, data = self.report("gruen.json")
        self.assertEqual(2, data["total_tests"])
        self.assertTrue(all(entry["passed"] for entry in data["modules"]))
        self.assertTrue(all(entry["error_class"] is None
                            for entry in data["modules"]))


if __name__ == "__main__":
    unittest.main()
