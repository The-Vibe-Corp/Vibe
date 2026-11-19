"""Abnahme B16: Branch- und Abschlussregeln in ``GENERAL_RULES`` und Vorlagen.

Die Testfälle leiten sich aus Arbeitspaket B16 (FEEDBACK.md), Anforderung D,
ab: ``GENERAL_RULES`` in ``bin/vibe`` und der verwaltete Block in allen
``templates/*/AGENTS.md`` erhalten zwei neue Punkte unter „Ordnung im Git
halten“:

* Branch-Regeln: ``feature/...`` und das konfigurierbare
  ``PACKAGE_BRANCH_PATTERN``.
* Abschluss nur mit Push und Merge-Request bei aktivierter Verknüpfung.

Bestehende Tests (``test_project_management.py``, ``test_ap06_github.py``)
verlangen, dass die Vorlagen den ``GENERAL_RULES``-Block exakt enthalten.
Dieses Modul ergänzt die inhaltliche Prüfung der neuen Punkte. Es werden
keine Modellaufrufe und keine externen Dienste verwendet.

Run:

    python3 -m unittest tests.unit.test_b16_git_rules -v
"""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"


def load_cli(vibe_root, home):
    """Lädt ``bin/vibe`` als Modul mit isoliertem VIBE und HOME."""
    old = {key: os.environ.get(key)
           for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_b16_git_rules_under_test", str(CLI))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class GitRulesTest(unittest.TestCase):
    """AK D: Die Regeln nennen Branch-Muster und die harte Abschlussschranke."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / "vibe").mkdir()
        (root / "home").mkdir()
        cls.cli = load_cli(root / "vibe", root / "home")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def git_section(text):
        return text.split("## Ordnung im Git halten", 1)[1].split("\n## ", 1)[0]

    def assert_b16_rules(self, text, source):
        section = self.git_section(text)
        for marker in ("feature/", "PACKAGE_BRANCH_PATTERN"):
            self.assertIn(marker, section,
                          f"{marker!r} fehlt in {source} (Branch-Regeln)")
        for marker in ("Push", "Merge-Request", "aktivier"):
            self.assertIn(marker, section,
                          f"{marker!r} fehlt in {source} "
                          "(Abschluss nur mit Push und Merge-Request)")

    def test_general_rules_require_branch_pattern_and_completion_gate(self):
        self.assert_b16_rules(self.cli.GENERAL_RULES, "GENERAL_RULES")

    def test_all_shipped_templates_contain_the_new_rules(self):
        templates = sorted((REPO / "templates").glob("*/AGENTS.md"))
        self.assertTrue(templates, "Keine Vorlagen gefunden")
        for path in templates:
            with self.subTest(path=str(path)):
                text = path.read_text(encoding="utf-8")
                # Der verwaltete Block bleibt in den Vorlagen identisch.
                self.assertIn(self.cli.GENERAL_RULES, text, path)
                self.assert_b16_rules(text, str(path))


if __name__ == "__main__":
    unittest.main()
