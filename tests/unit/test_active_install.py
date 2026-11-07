"""Tests für den Nachweis, dass die aktive Installation unverändert bleibt (V-001)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "active-install.py"
SNAPSHOT = REPO / "docs" / "baseline-installation.sha256"


def run_script(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )


class ActiveInstallSnapshotFixtureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "bin").mkdir()
        (self.root / "templates" / "generic").mkdir(parents=True)
        (self.root / "bin" / "vibe").write_text("print('vibe')\n", encoding="utf-8")
        (self.root / "templates" / "generic" / "AGENTS.md").write_text("regeln\n", encoding="utf-8")
        self.snapshot = self.root / "snapshot.sha256"

    def tearDown(self):
        self.tmp.cleanup()

    def test_snapshot_then_verify_passes(self):
        snap = run_script("snapshot", "--root", str(self.root), "--snapshot", str(self.snapshot))
        self.assertEqual(snap.returncode, 0, snap.stdout + snap.stderr)
        self.assertTrue(self.snapshot.exists())
        self.assertIn("bin/vibe", self.snapshot.read_text(encoding="utf-8"))
        check = run_script("verify", "--root", str(self.root), "--snapshot", str(self.snapshot))
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertIn("unverändert", check.stdout)

    def test_changed_file_is_detected(self):
        run_script("snapshot", "--root", str(self.root), "--snapshot", str(self.snapshot))
        (self.root / "bin" / "vibe").write_text("print('changed')\n", encoding="utf-8")
        check = run_script("verify", "--root", str(self.root), "--snapshot", str(self.snapshot))
        self.assertEqual(check.returncode, 1, check.stdout + check.stderr)
        self.assertIn("geändert", check.stdout + check.stderr)

    def test_added_file_is_detected(self):
        run_script("snapshot", "--root", str(self.root), "--snapshot", str(self.snapshot))
        (self.root / "bin" / "extra.sh").write_text("echo neu\n", encoding="utf-8")
        check = run_script("verify", "--root", str(self.root), "--snapshot", str(self.snapshot))
        self.assertEqual(check.returncode, 1, check.stdout + check.stderr)
        self.assertIn("neu", check.stdout + check.stderr)

    def test_missing_file_is_detected(self):
        run_script("snapshot", "--root", str(self.root), "--snapshot", str(self.snapshot))
        (self.root / "templates" / "generic" / "AGENTS.md").unlink()
        check = run_script("verify", "--root", str(self.root), "--snapshot", str(self.snapshot))
        self.assertEqual(check.returncode, 1, check.stdout + check.stderr)
        self.assertIn("fehlt", check.stdout + check.stderr)


class CommittedSnapshotTest(unittest.TestCase):
    def test_snapshot_file_exists_and_covers_program_files(self):
        self.assertTrue(SNAPSHOT.exists(), "docs/baseline-installation.sha256 fehlt")
        text = SNAPSHOT.read_text(encoding="utf-8")
        self.assertGreaterEqual(len(text.splitlines()), 20)
        self.assertIn("bin/vibe", text)
        self.assertIn("templates/android/.vibe/project.env", text)


if __name__ == "__main__":
    unittest.main()
