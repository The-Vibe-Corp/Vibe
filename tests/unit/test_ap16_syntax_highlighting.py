"""Quellverträge AP16: Hervorhebung der Agentenausgabe.

Die fachliche Abnahme leisten die Browsertests in
``tests/browser/test_ap16_syntax_highlighting_ui.py``. Dieser Test hält
zusätzliche, unabhängig prüfbare Quellverträge fest:

* AK4: Der Protokollinhalt darf nie als HTML interpretiert werden. Die
  ausgelieferte Oberfläche erzeugt Protokollinhalte ausschließlich über
  DOM-Knoten; ``innerHTML`` und verwandte HTML-Injektionsaufrufe dürfen im
  Seitenquelltext nicht vorkommen (F19-Entscheidung, dokumentiert in
  ``docs/features/F19.md``).
* AK6: Der dokumentierte F19-Klassenvertrag für die „Live-Ausgabe“-Karte
  bleibt bestehen: ``bin/web/styles.css`` definiert die ``hl-*``-Regeln
  für ``pre#log``; die Hervorhebung des Lauf-Logs funktioniert weiter.
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEB_FILES = (
    REPO / "bin" / "web" / "index.html",
    REPO / "bin" / "web" / "styles.css",
    REPO / "bin" / "web" / "app.js",
)
# Echte Injektionsaufrufe; der erläuternde F19-Kommentar („kein innerHTML“)
# soll nicht als Treffer zählen.
INJECTION_PATTERN = re.compile(
    r"\.innerHTML\b|\binnerHTML\s*=[^=]|insertAdjacentHTML|"
    r"\bouterHTML\b|document\.write\s*\(")

REQUIRED_HL_CLASSES = ("hl-head", "hl-err", "hl-tool", "hl-sub")


def page_source():
    return "\n".join(path.read_text(encoding="utf-8") for path in WEB_FILES)


class AP16WebUiHighlightingTest(unittest.TestCase):
    def test_web_ui_never_interprets_log_content_as_html(self):
        page = page_source()
        found = INJECTION_PATTERN.findall(page)
        self.assertEqual(
            found, [],
            "Die Oberfläche nutzt HTML-Injektionsaufrufe; Protokollinhalt "
            "darf nie als HTML interpretiert werden: " + repr(found))

    def test_f19_highlight_classes_remain_scoped_to_the_run_log(self):
        styles = (REPO / "bin" / "web" / "styles.css").read_text(
            encoding="utf-8")
        for name in REQUIRED_HL_CLASSES:
            self.assertIn(
                f"pre#log .{name}", styles,
                f"Der dokumentierte F19-Vertrag fehlt: Regel für {name} "
                "ist nicht an pre#log gebunden")


if __name__ == "__main__":
    unittest.main()
