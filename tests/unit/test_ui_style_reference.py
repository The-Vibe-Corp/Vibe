"""Referenzdatei und klassische UI des UI-Style-Guides.

Aufruf: python3 -m unittest tests.unit.test_ui_style_reference -v

Der Style-Guide wird als ``docs/style.html`` unverändert aus dem Ticket
abgelegt. Die klassische Oberfläche darf vom Restyling der neuen Oberfläche
nicht berührt werden; ihre Dateien werden bytegenau gegen den Ausgangsstand
des Pakets gehalten. Die visuellen Verträge der neuen Oberfläche selbst
prüft ``tests.browser.test_new_ui_style_screenshots`` an gerenderten
Screenshots.
"""
import hashlib
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REFERENCE = REPO / "docs" / "style.html"

# SHA-256 des zugelieferten Quelltexts (Ticketbeschreibung, Abschnitt
# „Code:“), ohne führende/nachfolgende Leerzeilen. Zeilenende-Unterschiede
# werden vor dem Hash normalisiert.
REFERENCE_SHA256 = "fe915d3cadf84e8319c44acb7701abb62e9836d1be4e76fd0b1c064c32cc8e21"
TITLE = "Vibe UI Style Guide — Precise Frames × Technical Density"

# Bytegenaue Ausgangsstände (Start-Commit e845c98) der klassischen UI.
CLASSIC_BASELINE_SHA256 = {
    "bin/web/classic.html": "19ea677f5c3dc3579279fd9b5bf7584612967654b8ec0bbde3818576c78b46b5",
    "bin/web/styles.css": "daac654a2a524dd49561ba2580419bad6209ed8646670e993409b88f5cb0bb1e",
    "bin/web/app.js": "f31477bd61d6722dd9949748a61a2e2de9502db5f930db3d310178fc9e68bf3f",
}


class StyleReferenceFileTest(unittest.TestCase):
    """Die zugelieferte Referenz liegt unverändert in der Dokumentation."""

    def test_reference_style_file_exists(self):
        self.assertTrue(REFERENCE.is_file(),
                        "docs/style.html fehlt als Referenzdatei")

    def test_reference_style_file_matches_supplied_source(self):
        self.assertTrue(REFERENCE.is_file(),
                        "docs/style.html fehlt als Referenzdatei")
        text = REFERENCE.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self.assertEqual(REFERENCE_SHA256, digest,
                         "docs/style.html ist nicht der zugelieferte Quelltext")
        self.assertIn(TITLE, text)


class ClassicUiUntouchedTest(unittest.TestCase):
    """Das Restyling darf die klassische Oberfläche nicht verändern."""

    def test_classic_assets_are_byte_identical_to_baseline(self):
        for relpath, expected in CLASSIC_BASELINE_SHA256.items():
            with self.subTest(path=relpath):
                path = REPO / relpath
                self.assertTrue(path.is_file(), relpath + " fehlt")
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(expected, actual,
                                 relpath + " wurde verändert")


if __name__ == "__main__":
    unittest.main()
