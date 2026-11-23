"""AP7-Korbat — ``run-tests-parallel.py --report`` (T-V17-Zulieferung).

Der Volllauf braucht eine strukturierte Grundlage für Zählung und
Baseline-Vergleich. Die neue Option ``--report PATH`` schreibt nach Abschluss
einen JSON-Bericht:

    {"modules": [{"module", "tests", "passed", "returncode",
                  "error_class", "error_message"}], "total_tests": N}

``error_class``/``error_message`` stammen aus der Modulausgabe (erste
Fehlerzeile) und sind nur bei fehlgeschlagenen Modulen gesetzt, sonst
``null``. Textausgabe und Exitcodes bleiben unverändert (``Ran N``-Vertrag
und ``Gesamt:``-Zeile). Ohne ``--report`` wird nichts geschrieben.

Die Fixture-Module sind klein und schnell; es werden keine echten Modell-,
Router- oder Netzwerkaufrufe ausgeführt.

Run:

    python3 -m unittest tests.unit.test_ap7_korbat_report -v
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "scripts" / "run-tests-parallel.py"

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
