"""Unit-Abnahme AP14 (Teil 1): Fähigkeitsschicht des Harness.

Arbeitspaket AP14 verlangt eine Ansicht, in der die Arbeit aller laufenden
Agenten live verfolgbar ist und in der dem Hauptagenten und jedem Subagenten
Anweisungen gesendet sowie ein Lauf in derselben Session fortgesetzt werden
können — kompatibel mit jedem konfigurierbaren Harness. Da Pi im Print-Modus
(``--no-session``) weder Zusatzanweisungen empfangen noch eine Session
fortsetzen kann, entscheidet eine reine Fähigkeitsschicht je Harness, welche
Steuermöglichkeiten die Oberfläche anbietet.

Vertrag (feste Schnittstelle):

* ``vibe_harness.supports(name, capability)`` mit den Fähigkeiten
  ``"steer"`` und ``"continue"``:
  - opencode: beide Fähigkeiten wahr.
  - pi: beide Fähigkeiten falsch.
  - Unbekannte oder ungültige Harness-Namen: falsch.
  - Unbekannte oder ungültige Fähigkeiten: falsch.
* Die Funktion ist rein: kein Prozessstart, kein Dateizugriff.

Es werden keine Modellaufrufe ausgeführt und es startet kein Programm.
"""
import builtins
import importlib.machinery
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
HARNESS_PY = REPO / "bin" / "vibe_harness.py"
# vibe_harness importiert Schwestermodule aus bin; ohne Pfad bricht das Laden.
sys.path.insert(0, str(REPO / "bin"))


def load_module(name="vibe_harness_ap14_under_test"):
    """Lädt bin/vibe_harness.py als Testunterlage (ohne Installation)."""
    loader = importlib.machinery.SourceFileLoader(name, str(HARNESS_PY))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


MODULE = load_module()


class SupportsCapabilityTest(unittest.TestCase):
    """AK: Fähigkeitsschicht je Harness — opencode ja, Pi nein, unbekannt nein."""

    def test_opencode_reports_both_capabilities(self):
        self.assertTrue(
            MODULE.supports("opencode", "steer"),
            "opencode muss 'steer' unterstützen (Zusatzanweisungen an den "
            "Hauptagenten und jeden Subagenten).",
        )
        self.assertTrue(
            MODULE.supports("opencode", "continue"),
            "opencode muss 'continue' unterstützen (Fortsetzung in derselben "
            "Session).",
        )

    def test_pi_reports_no_capabilities(self):
        self.assertFalse(
            MODULE.supports("pi", "steer"),
            "Pi läuft im Print-Modus (--no-session): keine Zusatzanweisungen.",
        )
        self.assertFalse(
            MODULE.supports("pi", "continue"),
            "Pi läuft im Print-Modus (--no-session): keine Session-Fortsetzung.",
        )

    def test_unknown_or_invalid_names_report_no_capability(self):
        for name in ("unbekannt", "", None, "   ", "pi2", "open code"):
            for capability in ("steer", "continue"):
                self.assertFalse(
                    MODULE.supports(name, capability),
                    f"Harness {name!r} mit Fähigkeit {capability!r} muss "
                    "falsch melden, nicht abstürzen oder wahr erfinden.",
                )

    def test_unknown_capability_is_rejected_with_false(self):
        for capability in ("unbekannt", "", None, "STEER", "steer "):
            self.assertFalse(
                MODULE.supports("opencode", capability),
                f"Unbekannte Fähigkeit {capability!r} muss falsch melden.",
            )
            self.assertFalse(MODULE.supports("pi", capability))

    def test_supports_is_pure_no_process_no_file_access(self):
        """AK 'kompatibel mit jedem konfigurierbaren Harness': Die Abfrage ist
        rein — kein Prozessstart, kein Dateizugriff. Ein Verstoß bricht den
        Test mit einer klaren Meldung ab."""
        errors = []

        def deny(reason):
            def _deny(*args, **kwargs):
                errors.append(reason)
                raise AssertionError(reason)
            return _deny

        # Prozessstart global sperren (nicht am Modul des Harness), damit der
        # Reinheitsnachweis auch ohne "import subprocess" in vibe_harness gilt.
        with mock.patch(
            "subprocess.Popen", side_effect=deny("Prozessstart Popen")
        ), mock.patch(
            "subprocess.run", side_effect=deny("Prozessstart run")
        ), mock.patch(
            "subprocess.call", side_effect=deny("Prozessstart call")
        ), mock.patch(
            "subprocess.check_output",
            side_effect=deny("Prozessstart check_output"),
        ), mock.patch.object(
            MODULE.os, "system", side_effect=deny("Prozessstart system")
        ), mock.patch.object(
            MODULE.os, "open", side_effect=deny("Dateizugriff os.open")
        ), mock.patch.object(
            builtins, "open", side_effect=deny("Dateizugriff open")
        ):
            results = {
                (name, capability): MODULE.supports(name, capability)
                for name in ("opencode", "pi", "unbekannt")
                for capability in ("steer", "continue")
            }

        self.assertEqual(
            [], errors,
            "supports() darf weder Prozesse starten noch Dateien lesen: "
            + "; ".join(errors),
        )
        self.assertEqual(
            (True, True),
            (results[("opencode", "steer")], results[("opencode", "continue")]),
        )
        self.assertFalse(results[("pi", "steer")])
        self.assertFalse(results[("unbekannt", "continue")])
        # Wiederholte Aufrufe liefern dasselbe Ergebnis (deterministisch).
        self.assertTrue(MODULE.supports("opencode", "steer"))


if __name__ == "__main__":
    unittest.main()
