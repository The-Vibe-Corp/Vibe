"""AP7-Korbat / GH-46 — committete Baseline und Repository-Verweis.

Die Fälle leiten sich aus TICKETS.md (GH-46: committete Baseline) und dem
AP7-Design-Brief ab. GH-76 hat den früheren verwalteten deutschen
``GENERAL_RULES``-Block entfernt; die Runner-Logistik steht jetzt im
englischen Plattformtext (``tests.unit.test_gh76_platform_instructions``).
Dieses Modul prüft deshalb nur noch:

* ``tests/verify-baseline.json`` ist die erste committete Baseline für die
  Umgebung ``pi-aarch64-py3.14-namespaces``: Schema v1 (``version`` 1,
  ``min_tests`` 2500) mit schema-konformen Failure-Einträgen
  (``module``/``class``/``signature``) und ohne Hostnamen, IP-Adressen,
  Geheimnisse oder absolute Pfade (öffentliches Repository).
* Die Repository-``AGENTS.md`` verweist auf das reale
  ``docs/verification_baselines.md`` (Unterstrich), nicht auf den früheren
  kaputten Bindestrich-Pfad.

Es werden nur Dateien gelesen; keine Modellaufrufe, kein Netz.

Run:

    python3 -m unittest tests.unit.test_ap7_korbat_rules -v
"""
import json
import socket
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AGENTS = REPO / "AGENTS.md"
MANIFEST = REPO / "tests" / "verify-baseline.json"
BASELINE_DOC = REPO / "docs" / "verification_baselines.md"

ENV_LABEL = "pi-aarch64-py3.14-namespaces"


class BaselineDocumentReferenceTest(unittest.TestCase):
    """GH-76: Der Repository-Verweis nennt die reale Baseline-Datei."""

    def test_agents_file_uses_the_underscore_document(self):
        """Vorbedingung: ``AGENTS.md`` und ``docs/``.
        Aktion: den Baseline-Verweis prüfen.
        Erwartung: ``docs/verification_baselines.md`` ist genannt, der
        Bindestrich-Pfad fehlt und die Datei existiert.
        Fehlerfall: kaputter Verweis oder fehlende Datei.
        """
        text = AGENTS.read_text(encoding="utf-8")
        self.assertIn("docs/verification_baselines.md", text)
        self.assertNotIn("docs/verification-baselines.md", text)
        self.assertTrue(BASELINE_DOC.is_file(),
                        "docs/verification_baselines.md fehlt")


class CommittedBaselineManifestTest(unittest.TestCase):
    """AK: erste committete Baseline v1 ohne Umgebungsdetails."""

    def read(self):
        self.assertTrue(
            MANIFEST.is_file(),
            "tests/verify-baseline.json fehlt (kanonische Baseline)",
        )
        return json.loads(MANIFEST.read_text(encoding="utf-8"))

    def failures(self, data):
        envs = data.get("envs")
        self.assertIsInstance(envs, dict, data)
        self.assertIn(ENV_LABEL, envs, "Umgebungssektion fehlt: %r" % (envs,))
        section = envs[ENV_LABEL]
        self.assertIsInstance(section, dict, section)
        failures = section.get("failures")
        self.assertIsInstance(failures, list, section)
        return failures

    def test_manifest_has_schema_v1_and_the_initial_values(self):
        """Vorbedingung: die committed Baseline.
        Aktion: JSON lesen.
        Erwartung: ``version`` 1, ``min_tests`` 2500 und eine nicht-leere
        Failure-Liste für die Umgebung ``pi-aarch64-py3.14-namespaces``.
        Fehlerfall: Fehlende Datei, falsche Version, abweichende Schwelle oder
        eine leere Umgebungssektion.
        """
        data = self.read()
        self.assertEqual(1, data.get("version"))
        self.assertEqual(2500, data.get("min_tests"))
        self.assertTrue(self.failures(data),
                        "Failures für %r dürfen nicht leer sein" % ENV_LABEL)

    def test_manifest_failure_entries_are_schema_conform(self):
        """Vorbedingung: die committed Baseline.
        Aktion: jeden Failure-Eintrag prüfen.
        Erwartung: Einträge haben genau ``module``/``class``/``signature``;
        ``module`` beginnt mit ``tests.unit.``, ``class`` ist nicht leer und
        ``signature`` hat die Engine-Form ``sha256:<64 hex>``. Die exakte
        Menge der Einträge ist nicht eingefroren, damit spätere Fortschreibung
        per Review den Test nicht bricht.
        Fehlerfall: Schemafremde Einträge oder fehlende Kennungen, die die
        Engine nicht wiedererkennen kann.
        """
        for entry in self.failures(self.read()):
            with self.subTest(entry=entry):
                self.assertIsInstance(entry, dict, entry)
                self.assertEqual(
                    {"module", "class", "signature"}, set(entry), entry
                )
                self.assertIsInstance(entry["module"], str, entry)
                self.assertTrue(entry["module"].startswith("tests.unit."),
                                entry)
                self.assertIsInstance(entry["class"], str, entry)
                self.assertTrue(entry["class"].strip(), entry)
                self.assertIsInstance(entry["signature"], str, entry)
                self.assertRegex(entry["signature"], r"^sha256:[0-9a-f]{64}$")

    def test_manifest_has_only_the_minimal_top_level_fields(self):
        """Vorbedingung: die committed Baseline.
        Aktion: Schlüssel prüfen.
        Erwartung: Nur ``version``, ``min_tests`` und ``envs`` — keine
        Umgebungsbeschreibung, kein Zeitstempel, keine Pfade.
        Fehlerfall: Zusatzfelder transportieren Umgebungsdetails.
        """
        data = self.read()
        self.assertEqual({"version", "min_tests", "envs"}, set(data), data)

    def test_manifest_contains_no_environment_details_or_secrets(self):
        """Vorbedingung: die committed Baseline.
        Aktion: Dateitext auf Umgebungsangaben und Geheimnisse prüfen.
        Erwartung: keine IP-Adressen, kein eigener Hostname, keine absoluten
        Pfade, keine Geheimnis-Schlüssel.
        Fehlerfall: Das öffentliche Repository enthält Umgebungsdetails.
        """
        # Fehlt die Datei, ist das eine Assertion (kanonische Baseline nicht
        # angelegt) und kein FileNotFoundError-ERROR im Fixture.
        self.assertTrue(
            MANIFEST.is_file(),
            "tests/verify-baseline.json fehlt (kanonische Baseline)",
        )
        text = MANIFEST.read_text(encoding="utf-8")
        self.assertNotRegex(text, r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
                            "IP-Adresse in der Baseline")
        hostname = socket.gethostname()
        if hostname and len(hostname) > 2:
            self.assertNotIn(hostname, text, "Hostname in der Baseline")
        for needle in ("/home/", "/Users/", "/opt/", "/var/", "/tmp/", "C:\\"):
            self.assertNotIn(needle, text, "absoluter Pfad %r" % needle)
        self.assertNotRegex(
            text.lower(),
            r"password|passwort|secret|geheim|token|api[_-]?key",
            "Geheimnis-Schlüssel in der Baseline",
        )

    def test_manifest_min_tests_is_a_ratchet_floor(self):
        """Vorbedingung: die committed Baseline.
        Aktion: Schwelle prüfen.
        Erwartung: ``min_tests`` ist mindestens 2500 — eine Senkung wäre nur
        per Review zulässig, nicht durch dieses Paket.
        Fehlerfall: Die Schwelle liegt unter dem operativen Mindestwert.
        """
        data = self.read()
        self.assertGreaterEqual(data.get("min_tests", 0), 2500)


if __name__ == "__main__":
    unittest.main()
