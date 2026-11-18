"""Paralleler Testläufer ``scripts/run-tests-parallel.py`` (F31).

Der Läufer soll die langen Volläufe verkürzen, ohne Tests zu verlieren:

* Er entdeckt die Testmodule eines Verzeichnisses und startet je Modul einen
  eigenen Prozess ``python3 -m unittest <modul>`` mit dem Arbeitsverzeichnis
  der ``--dir``-Basis (hier das temporäre Repository).
* Jeder Modulblock beginnt mit einer Zeile ``--- <modul> ---``; alle
  ``Ran N tests``-Zeilen bleiben im Gesamtausdruck, damit ``verify.py`` sie
  mit ``VERIFY_TEST_PATTERN`` summieren kann.
* Die Abschlusszeile lautet
  ``Gesamt: <n> Tests, <b>/<m> Module bestanden, <f> fehlgeschlagen``.
* Exit 0 nur, wenn alle Module bestanden wurden. Ein fehlschlagendes Modul
  oder ein Importfehler ergibt Exit 1 und wird namentlich genannt; seine
  Ausgabe bleibt sichtbar.
* ``--jobs 1`` arbeitet sequenziell und liefert dieselben Module und Summen;
  ohne ``--jobs`` laufen die Module parallel (Standard: Anzahl Kerne).

Die Fixture-Module sind bewusst klein und schnell; es werden keine echten
Modell-, Router- oder Netzwerkaufrufe ausgeführt.
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

    def run_runner(self, *extra, timeout=180, env=None):
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


if __name__ == "__main__":
    unittest.main()
