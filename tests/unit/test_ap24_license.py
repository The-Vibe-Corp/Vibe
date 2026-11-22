"""Unabhängige Abnahmetests für AP24 „Lizenz anpassung der projektes".

Abgeleitet aus TICKETS.md (AP24, Zeilen 1159–1175, „Lizenz anpassung der
projektes") und dem von der Vertraggebung übergebenen Basis (Vertragssatz,
vgl. Abschnitt 2; hier) , ohne die Implementierung zu kennen. Geprüft
werden LICENSE und README.md.

Verträge (TDD-Rotphase): Jeder Fall muss grün bleiben, bis AP24 umgesetzt
ist. Erwartetes Ergebnis „ROT" während der Rotphase; Vorbedingungen sind
die Zustände der Verträge vor Umsetzung (vom Test-Agenten per lesen des
Ist-Zustands vor Implementierung verifiziert: LICENSE ist bisher MIT,
README hat bisher keinen Lizenzabschnitt zum Dual-Modell).

Fälle (Vertragsdetails in TICKETS.md 1173–1175, Verträge auch in
lizenzvertraglichen Abschnitten der Testdateien):

| Fall | Vorbedingung (Ist) | Aktion (geprüft) | Erwartetes Ergebnis (Rotphase) | Fachliche Bedeutung |
|---|---|---|---|---|
| test_license_is_agpl_3_0_only | LICENSE ist bisher MIT (kein kanonischer AGPLv3-Text) | LICENSE-Text lesen; „GNU AFFERO GENERAL PUBLIC LICENSE" als erste kanonische Zeile, „Version 3, 19 November 2007" und „GNU Affero General Public License" prüfen | ROT (alles im MIT-LICENSE nicht enthalten) | LICENSE muss die kanonische AGPL-3.0-only-Lizenz sein (Open-Source-Bezug, Copyleft-Text) |
| test_license_has_no_mit_text | LICENSE ist bisher MIT, enthält „MIT License" | LICENSE-Text lesen; „MIT License" prüfen | ROT („MIT License" ist im LICENSE enthalten) | MIT darf in LICENSE nicht als Lizenz behauptet werden |
| test_license_keeps_project_copyright | LICENSE ist bisher MIT mit „Copyright (c) 2026 M0P" | LICENSE-Text lesen; „Copyright (c) 2026 M0P" prüfen | GRÜN | Projekt-Attribution bleibt im LICENSE erhalten |
| test_readme_states_dual_licensing_model | README bisher ohne Lizenzsatz zum Dual-Modell | README.md lesen; vorgeschriebenen Lizenzsatz (TICKETS.md 1175) und die Referenz „LICENSE" prüfen | ROT (Satz noch nicht im README) | README muss das Dual-Licensing-Modell (AGPL-Variante + kommerzielle Lizenz) dokumentieren |
| test_readme_does_not_claim_mit | README bisher enthält „MIT" (Abschnitt „Mitwirfen und Lizenz") | README.md lesen; „MIT" prüfen | ROT („MIT" ist im README enthalten) | README darf nicht mehr die MIT-Lizenz behaupten |

Ausführung (Arbeitsbaum-Wurzel):

    python3 -m unittest tests.unit.test_ap24_license -v

Standardbibliothek only; keine Netzwerkzugriffe; keine Produktionskonfigurationen.
"""
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Vorgeschriebener Lizenzsatz aus TICKETS.md AP24 (Z. 1175), der im README
# anzugeben ist. Das Ticket enthält höchstens ein „bzw." („proprietär bzw.
# kommerzielle Nutzung"); kein doppelter „bzw." gefunden — der Test prüft
# den Satz exakt wie vom Vergabeberaten übergeben.
LIZENZ_SATZ = (
    "Privatnutzung und AGPL-konforme Nutzung kostenlos; "
    "proprietär bzw. kommerzielle Nutzung ohne AGPL-Pflichten "
    "erfordert eine kommerzielle Lizenz."
)


class LicenseContractTest(unittest.TestCase):
    """AP24-Verträge: LICENSE = AGPL-3.0-only, README = Dual-Modell."""

    def _license_text(self):
        return (REPO / "LICENSE").read_text(encoding="utf-8")

    def _readme_text(self):
        return (REPO / "README.md").read_text(encoding="utf-8")

    def test_license_is_agpl_3_0_only(self):
        """Vertrag: LICENSE = AGPL-3.0-only (kanonischer Text). Rotphase: ROT."""
        text = self._license_text()
        self.assertTrue(
            text.lstrip().startswith("GNU AFFERO GENERAL PUBLIC LICENSE"),
            "LICENSE beginnt nicht mit der kanonischen ersten Zeile "
            "des AGPLv3-Headers",
        )
        self.assertIn(
            "Version 3, 19 November 2007",
            text,
            "LICENSE enthält die kanonische AGPLv3-Versionszeile nicht",
        )
        self.assertIn(
            "GNU Affero General Public License",
            text,
            "LICENSE enthält den kanonischen AGPLv3-Namensverweis nicht",
        )

    def test_license_has_no_mit_text(self):
        """Vertrag: LICENSE enthält nicht „MIT License". Rotphase: ROT."""
        text = self._license_text()
        self.assertNotIn(
            "MIT License",
            text,
            "LICENSE enthält „MIT License“ weiterhin",
        )

    def test_license_keeps_project_copyright(self):
        """Vertrag: Attribution „Copyright (c) 2026 M0P" bleibt erhalten. Grün."""
        text = self._license_text()
        self.assertIn(
            "Copyright (c) 2026 M0P",
            text,
            "Attribution „Copyright (c) 2026 M0P“ des Projekts fehlt im LICENSE",
        )

    def test_readme_states_dual_licensing_model(self):
        """Vertrag: README enthält den vorgeschriebenen Lizenzsatz + Referenz „LICENSE". Rotphase: ROT."""
        readme = self._readme_text()
        self.assertIn(
            LIZENZ_SATZ,
            readme,
            "README enthält den vorgeschriebenen Lizenzsatz "
            "(TICKETS.md AP24 Z. 1175) nicht",
        )
        self.assertIn(
            "LICENSE",
            readme,
            "README enthält die Referenz „LICENSE“ nicht",
        )

    def test_readme_does_not_claim_mit(self):
        """Vertrag: README enthält nicht „MIT". Rotphase: ROT."""
        readme = self._readme_text()
        self.assertNotIn(
            "MIT",
            readme,
            "README behauptet weiterhin die MIT-Lizenz",
        )


if __name__ == "__main__":
    unittest.main()
