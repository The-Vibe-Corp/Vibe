"""AP7-Korbat / GH-46 — generische Agentenregeln und committete Baseline.

Die Fälle leiten sich aus TICKETS.md (GH-46: der verwaltete
``GENERAL_RULES``-Block ist generisch und wandert in die ``AGENTS.md`` jedes
Projekts) und dem AP7-Design-Brief ab:

* Die Regelquelle ``GENERAL_RULES`` in ``bin/vibe`` nennt die Projektprüfung
  ausschließlich über die Prüfbefehle aus ``.vibe/project.env``
  (``VERIFY_QUICK``, ``VERIFY_PACKAGE``, ``VERIFY_FULL``) und behält die
  Stufung der Nachweise (genau einmal vor der Abnahme, Code oder Tests,
  Nachweisumfang). Projektspezifische bzw. Engine-Implementationsdetails der
  vibe-Baseline (``verify.sh``, Exit-Codes, ``--write-baseline``,
  ``VERIFY_MIN_TESTS``, Sektion „Baseline-Disziplin“) gehören nicht in den
  Block, weil er für jedes beliebige Projekt gelten muss.
* Derselbe Block liegt bytengleich in allen fünf ``templates/*/AGENTS.md``
  und in der ``AGENTS.md`` des Repositories (Marker-Invariante).
* ``tests/verify-baseline.json`` ist die erste committete Baseline für die
  Umgebung ``pi-aarch64-py3.14-namespaces``: Schema v1 (``version`` 1,
  ``min_tests`` 2500) mit schema-konformen Failure-Einträgen
  (``module``/``class``/``signature``) und ohne Hostnamen, IP-Adressen,
  Geheimnisse oder absolute Pfade (öffentliches Repository).

Es werden nur Dateien gelesen; keine Modellaufrufe, kein Netz.

Run:

    python3 -m unittest tests.unit.test_ap7_korbat_rules -v
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import socket
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
AGENTS = REPO / "AGENTS.md"
TEMPLATES = sorted((REPO / "templates").glob("*/AGENTS.md"))
MANIFEST = REPO / "tests" / "verify-baseline.json"

EFFICIENCY_SECTION = "## Effizienz der Prüfungen (verbindlich)"
MARK_START = "<!-- vibe:general-rules -->"
MARK_END = "<!-- /vibe:general-rules -->"
ENV_LABEL = "pi-aarch64-py3.14-namespaces"

# GH-46: Der Block gilt generisch für jedes Projekt und enthält deshalb keine
# Engine- oder vibe-Projektimplementationsdetails der Baseline.
FORBIDDEN_RULE_FRAGMENTS = (
    "Baseline-Disziplin",
    "verify.sh",
    "Exit 6",
    "Exit 7",
    "Exit 3",
    "--write-baseline",
    "VERIFY_MIN_TESTS",
)


def load_cli(vibe_root, home):
    """Lädt ``bin/vibe`` als Modul mit isoliertem VIBE und HOME."""
    old = {key: os.environ.get(key)
           for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_ap7_rules_under_test", str(CLI)
        )
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


def section(text, heading):
    """Liefert die Sektion ab ``heading`` bis zur nächsten Überschrift."""
    self_index = text.find(heading)
    if self_index < 0:
        return ""
    rest = text[self_index + len(heading):]
    following = re.search(r"(?m)^## ", rest)
    return rest[:following.start()] if following else rest


def managed_block(text):
    """Liefert den verwalteten Block einschließlich beider Marker."""
    start = text.find(MARK_START)
    end = text.find(MARK_END)
    if start < 0 or end < start:
        return ""
    return text[start:end + len(MARK_END)]


class GeneralRulesTest(unittest.TestCase):
    """AK GH-46: ein generischer Regelblock für jedes Projekt."""

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

    def test_efficiency_section_names_the_project_env_commands(self):
        """Vorbedingung: Sektion „Effizienz der Prüfungen“.
        Aktion: Aussagen zur Prüfschnittstelle lesen.
        Erwartung: Die Projektprüfung läuft ausschließlich über die Befehle
        aus ``.vibe/project.env`` (``VERIFY_QUICK``, ``VERIFY_PACKAGE``,
        ``VERIFY_FULL``); der Nachweisumfang bleibt erhalten (genau einmal vor
        der Abnahme, Code oder Tests).
        Fehlerfall: Agenten setzen Prüfinhalte weiterhin selbst zusammen oder
        der Block nennt eine projektspezifische Prüfdatei statt der
        Projektkonfiguration.
        """
        text = section(self.cli.GENERAL_RULES, EFFICIENCY_SECTION)
        for marker in (
            ".vibe/project.env",
            "VERIFY_QUICK",
            "VERIFY_PACKAGE",
            "VERIFY_FULL",
            "betroffene Testmodule",
            "Prüfschnittstelle",
            "genau einmal",
            "vor der Abnahme",
            "Code oder Tests",
            "Nachweisumfang",
            "abgeschwächt",
        ):
            self.assertIn(marker, text,
                          "%r fehlt in %r" % (marker, EFFICIENCY_SECTION))
        self.assertNotIn("verify.sh", text)
        self.assertNotIn("quick|package|full", text)

    def test_general_rules_stay_generic_no_baseline_implementation_details(self):
        """Vorbedingung: ``GENERAL_RULES`` aus ``bin/vibe``.
        Aktion: Block auf Engine- und Projektdetails durchsuchen.
        Erwartung: keine Sektion „Baseline-Disziplin“, kein ``verify.sh``,
        keine Exit-Codes 3/6/7, kein ``--write-baseline`` und kein
        ``VERIFY_MIN_TESTS`` — der Block muss für jedes Projekt gelten.
        Fehlerfall: vibe-spezifische Testimplementierung wandert in die
        AGENTS.md fremder Projekte.
        """
        rules = self.cli.GENERAL_RULES
        for marker in FORBIDDEN_RULE_FRAGMENTS:
            self.assertNotIn(marker, rules,
                             "%r gehört nicht in den generischen Block" % marker)

    def test_all_templates_carry_the_general_rules_verbatim(self):
        """Vorbedingung: alle ``templates/*/AGENTS.md``.
        Aktion: verwalteten Block vergleichen.
        Erwartung: ``GENERAL_RULES`` ist bytengleich enthalten; genau ein
        Markerpaar; der Block enthält keine Baseline-Implementationsdetails.
        Fehlerfall: Eine Vorlage driftet von der Regelquelle ab.
        """
        self.assertEqual(5, len(TEMPLATES), TEMPLATES)
        for path in TEMPLATES:
            with self.subTest(path=str(path)):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(1, text.count(MARK_START))
                self.assertEqual(1, text.count(MARK_END))
                block = managed_block(text)
                self.assertTrue(block, "Markerpaar fehlt in %s" % path)
                self.assertEqual(self.cli.GENERAL_RULES, block,
                                 "Vorlage weicht von GENERAL_RULES ab: %s" % path)
                for marker in FORBIDDEN_RULE_FRAGMENTS:
                    self.assertNotIn(marker, block,
                                     "%r steht noch in %s" % (marker, path))

    def test_repository_agents_file_carries_the_general_rules_verbatim(self):
        """Vorbedingung: ``AGENTS.md`` im Repository-Wurzelverzeichnis.
        Aktion: Marker und Block prüfen.
        Erwartung: Der verwaltete Block steht genau einmal, ist bytengleich
        zu ``GENERAL_RULES`` und enthält keine Baseline-Implementationsdetails.
        Fehlerfall: Die Repository-Regeln weichen von der Regelquelle ab.
        """
        self.assertTrue(AGENTS.is_file(), "AGENTS.md fehlt im Repository")
        text = AGENTS.read_text(encoding="utf-8")
        self.assertEqual(1, text.count(MARK_START))
        self.assertEqual(1, text.count(MARK_END))
        block = managed_block(text)
        self.assertTrue(block, "Markerpaar fehlt in AGENTS.md")
        self.assertEqual(self.cli.GENERAL_RULES, block,
                         "AGENTS.md weicht von GENERAL_RULES ab")
        for marker in FORBIDDEN_RULE_FRAGMENTS:
            self.assertNotIn(marker, block,
                             "%r steht noch in AGENTS.md" % marker)


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
