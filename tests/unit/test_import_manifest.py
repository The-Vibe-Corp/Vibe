"""Tests für die reproduzierbare Prüfung des Importmanifests (V-001)."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check-import-manifest.py"


def run_check(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )


def write_manifest(root, scopes, paths):
    entries = []
    for rel in paths:
        data = (root / rel).read_bytes()
        entries.append(
            {
                "path": rel,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
            }
        )
    manifest = {
        "version": 1,
        "stand": "2026-01-01",
        "quelle": "Testfixture",
        "hinweis": "Nur für Tests",
        "scopes": scopes,
        "files": entries,
    }
    path = root / "import-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


class RepositoryManifestTest(unittest.TestCase):
    def test_repository_matches_committed_manifest(self):
        result = run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK", result.stdout)

    def test_manifest_covers_all_imported_program_files(self):
        manifest = json.loads((REPO / "docs" / "import-manifest.json").read_text(encoding="utf-8"))
        paths = [entry["path"] for entry in manifest["files"]]
        self.assertEqual(len(paths), len(set(paths)), "Manifest enthält doppelte Pfade")
        for expected in (
            "install-vibe.sh",
            "bin/vibe",
            "bin/vibe-run.sh",
            "bin/vibe-web.py",
            "bin/vibe_mcp.py",
            "data/models.json",
            "templates/android/.vibe/project.env",
            "templates/common/opencode.json",
        ):
            self.assertIn(expected, paths)
        self.assertGreaterEqual(len(paths), 20)


class ManifestCheckFailureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "bin").mkdir()
        (self.root / "data").mkdir()
        (self.root / "bin" / "app.py").write_text("print('a')\n", encoding="utf-8")
        (self.root / "data" / "values.json").write_text('{"a": 1}\n', encoding="utf-8")
        self.manifest = write_manifest(
            self.root, ["bin", "data"], ["bin/app.py", "data/values.json"]
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_unchanged_tree_passes(self):
        result = run_check("--root", str(self.root), "--manifest", str(self.manifest))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("2 Dateien", result.stdout)

    def test_changed_file_fails(self):
        (self.root / "bin" / "app.py").write_text("print('b')\n", encoding="utf-8")
        result = run_check("--root", str(self.root), "--manifest", str(self.manifest))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Prüfsumme", result.stdout + result.stderr)

    def test_missing_file_fails(self):
        (self.root / "data" / "values.json").unlink()
        result = run_check("--root", str(self.root), "--manifest", str(self.manifest))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("nicht vorhanden", result.stdout + result.stderr)

    def test_unlisted_extra_file_fails(self):
        (self.root / "bin" / "extra.py").write_text("print('x')\n", encoding="utf-8")
        result = run_check("--root", str(self.root), "--manifest", str(self.manifest))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("nicht im Manifest", result.stdout + result.stderr)

    def test_missing_scope_fails(self):
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        manifest["scopes"].append("missing")
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        result = run_check("--root", str(self.root), "--manifest", str(self.manifest))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("existiert nicht", result.stdout + result.stderr)

    def test_path_outside_scope_is_rejected(self):
        outside = self.root / "outside.txt"
        outside.write_text("x\n", encoding="utf-8")
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        manifest["files"].append(
            {
                "path": "outside.txt",
                "sha256": hashlib.sha256(b"x\n").hexdigest(),
                "bytes": 2,
            }
        )
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        result = run_check("--root", str(self.root), "--manifest", str(self.manifest))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("außerhalb", result.stdout + result.stderr)

if __name__ == "__main__":
    unittest.main()
