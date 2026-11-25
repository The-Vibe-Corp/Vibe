"""Lizenzvertrag.

Aufruf: python3 -m unittest tests.unit.test_license -v
"""


# ===========================================================================
# Unabhängige Abnahmetests für „Lizenz anpassung der projektes"
# ===========================================================================

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
