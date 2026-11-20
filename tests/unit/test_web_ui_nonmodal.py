"""Regressionsschutz für nicht-modale Rückmeldungen in der Oberfläche (F11).

Die fachliche Abnahme leisten die Browsertests in
``tests/browser/test_nonmodal_ui.py``. Dieser Test hält zusätzlich fest, dass
die ausgelieferte Seite keine blockierenden Browserdialoge mehr aufruft und
stattdessen einen Statusbereich sowie Inline-Bestätigungen enthält. Seit V-019
besteht die Seite aus getrennten statischen Dateien; der Test liest HTML,
Stylesheet und Skript, ohne den Server zu starten.
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEB_FILES = (
    REPO / "bin" / "web" / "classic.html",
    REPO / "bin" / "web" / "styles.css",
    REPO / "bin" / "web" / "app.js",
)

BLOCKING = ("alert", "confirm", "prompt")


def page_source():
    return "\n".join(path.read_text(encoding="utf-8") for path in WEB_FILES)


class NonModalPageTest(unittest.TestCase):
    def test_page_offers_live_status_messages_and_inline_confirmation(self):
        page = page_source()
        self.assertIn("id:'toasts'", page, "Statusbereich für Meldungen fehlt")
        self.assertIn("'aria-live':'polite'", page, "Statusbereich ist nicht höflich angekündigt")
        self.assertIn("role:'status'", page, "Statusbereich hat keine ARIA-Rolle")
        self.assertIn("class:'confirm'", page, "Inline-Bestätigung fehlt im Quelltext")
        self.assertIn("role:'group'", page, "Inline-Bestätigung hat keine ARIA-Gruppe")
        self.assertIn(".confirm{", page, "Inline-Bestätigung ist nicht gestaltet")

    def test_page_calls_no_blocking_browser_dialogs(self):
        page = page_source()
        found = {}
        for name in BLOCKING:
            hits = re.findall(r"\b" + name + r"\s*\(", page)
            if hits:
                found[name] = len(hits)
        self.assertEqual(
            found,
            {},
            "blockierende Browserdialoge im Seitenquelltext: " + repr(found),
        )


if __name__ == "__main__":
    unittest.main()
