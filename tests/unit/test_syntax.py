"""Tests für die Syntaxprüfung der importierten Programmdateien (V-001)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check-syntax.py"


def run_check(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )


class RepositorySyntaxTest(unittest.TestCase):
    def test_all_program_files_parse(self):
        result = run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK", result.stdout)


class SyntaxFixtureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "bin").mkdir()
        (self.root / "scripts").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_broken_python_is_reported(self):
        (self.root / "bin" / "vibe").write_text("def broken(:\n", encoding="utf-8")
        result = run_check("--root", str(self.root))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("bin/vibe", result.stdout + result.stderr)

    def test_broken_shell_is_reported(self):
        (self.root / "scripts" / "bad.sh").write_text("if [ 1 -eq 1 ; then\n", encoding="utf-8")
        result = run_check("--root", str(self.root))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("bad.sh", result.stdout + result.stderr)

    def test_broken_json_is_reported(self):
        (self.root / "data.json").write_text('{"a": }\n', encoding="utf-8")
        result = run_check("--root", str(self.root))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("data.json", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
