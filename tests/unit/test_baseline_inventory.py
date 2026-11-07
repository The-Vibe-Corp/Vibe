"""Tests für die Bestandsaufnahme: CLI-, API- und UI-Funktionen müssen in docs/baseline.md stehen (V-001)."""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASELINE = REPO / "docs" / "baseline.md"
VIBE_CLI = REPO / "bin" / "vibe"
VIBE_WEB = REPO / "bin" / "vibe-web.py"

ALLOWED_STATUS = {
    "vorhanden und automatisiert geprüft",
    "vorhanden und manuell geprüft",
    "vorhanden, noch nicht geprüft",
    "teilweise vorhanden",
    "fehlt",
}

ROW = re.compile(
    r"^\| (CLI|API|UI) \| `([^`]+)` \| ([^|]+?) \| ([^|]+?) \|$",
    re.MULTILINE,
)


def cli_commands():
    text = VIBE_CLI.read_text(encoding="utf-8")
    if "table = {" not in text or "table[c]()" not in text:
        raise AssertionError("CLI-Tabelle in bin/vibe nicht gefunden")
    block = text.split("table = {", 1)[1].split("table[c]()", 1)[0]
    return set(re.findall(r'"([a-z]+)": lambda', block))


def api_routes():
    text = VIBE_WEB.read_text(encoding="utf-8")
    get_src = text.split("def do_GET", 1)[1].split("def do_POST", 1)[0]
    post_src = text.split("def do_POST", 1)[1].split("def stream", 1)[0]
    get = {("GET", path) for path in re.findall(r'"(/api/[a-z_]+)"', get_src)}
    post = {("POST", path) for path in re.findall(r'"(/api/[a-z_]+)"', post_src)}
    return get | post


class BaselineInventoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not BASELINE.exists():
            raise AssertionError("docs/baseline.md fehlt")
        cls.text = BASELINE.read_text(encoding="utf-8")
        cls.rows = ROW.findall(cls.text)
        cls.documented = {(kind, func) for kind, func, _, _ in cls.rows}

    def test_rows_exist(self):
        self.assertGreaterEqual(len(self.rows), 40, "Bestandsaufnahme ist unvollständig")

    def test_status_vocabulary(self):
        for kind, func, status, evidence in self.rows:
            self.assertIn(
                status.strip(),
                ALLOWED_STATUS,
                f"Unbekannter Prüfstatus für {func}: {status.strip()!r}",
            )
            self.assertTrue(evidence.strip(), f"Beleg fehlt für {func}")

    def test_every_cli_command_is_documented(self):
        missing = {f"vibe {cmd}" for cmd in cli_commands()} - {
            func for kind, func in self.documented if kind == "CLI"
        }
        self.assertEqual(missing, set(), f"Nicht dokumentierte CLI-Kommandos: {sorted(missing)}")

    def test_every_api_route_is_documented(self):
        missing = {f"{method} {path}" for method, path in api_routes()} - {
            func for kind, func in self.documented if kind == "API"
        }
        self.assertEqual(missing, set(), f"Nicht dokumentierte API-Routen: {sorted(missing)}")

    def test_ui_tabs_are_documented(self):
        documented_ui = {func for kind, func in self.documented if kind == "UI"}
        for tab in ("Tab Projekte", "Tab Agenten & Modelle", "Tab MCP-Tools", "Tab Umgebung"):
            self.assertIn(tab, documented_ui)

    def test_missing_original_installers_are_documented(self):
        for token in ("install.sh", "install2.sh", "Uninstaller", "Desktopdatei", "Rollback"):
            self.assertIn(token, self.text, f"Fehlender Installer nicht dokumentiert: {token}")

    def test_evidence_artifacts_are_linked(self):
        for token in ("docs/import-manifest.json", "docs/baseline-installation.sha256"):
            self.assertIn(token, self.text)

    def test_honest_status_summary_is_present(self):
        self.assertIn("noch nicht geprüft", self.text)
        self.assertIn("keine geheimnisse", self.text.lower())


if __name__ == "__main__":
    unittest.main()
