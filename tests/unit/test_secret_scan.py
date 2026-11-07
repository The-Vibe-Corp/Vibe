"""Tests für die reproduzierbare Geheimnisprüfung (V-001)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check-no-secrets.py"

# Absichtlich zusammengesetzt, damit diese Testdatei selbst nicht als Geheimnis
# erkannt wird. Die Zeichenfolgen sind erfunden.
AWS_KEY = "AKIA" + "ABCDEFGHIJKLMNOP"
LONG_VALUE = "Q7" + "mZ4tR9xL2pV8nB6k"


def run_check(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )


class RepositorySecretScanTest(unittest.TestCase):
    def test_repository_contains_no_detectable_secrets(self):
        result = run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK", result.stdout)


class SecretScanFixtureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_detects_aws_access_key(self):
        (self.root / "config.txt").write_text("aws = " + AWS_KEY + "\n", encoding="utf-8")
        result = run_check("--root", str(self.root))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("config.txt", result.stdout + result.stderr)
        self.assertIn("AWS", result.stdout + result.stderr)

    def test_detects_quoted_credential(self):
        line = "api_key = \"" + LONG_VALUE + "@example\"\n"
        (self.root / "settings.json").write_text(line, encoding="utf-8")
        result = run_check("--root", str(self.root))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("settings.json", result.stdout + result.stderr)

    def test_detects_dotenv_password(self):
        line = "DATABASE_" + "PASSWORD=" + LONG_VALUE + "\n"
        (self.root / ".env").write_text(line, encoding="utf-8")
        result = run_check("--root", str(self.root))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(".env", result.stdout + result.stderr)

    def test_ignores_environment_placeholders(self):
        (self.root / "mcp.json").write_text(
            '{"headers": {"Authorization": "Bearer {env:TOKEN}"}}\n', encoding="utf-8"
        )
        result = run_check("--root", str(self.root))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
