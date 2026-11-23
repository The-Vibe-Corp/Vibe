"""AP7-Korbat — Agentenregeln (Baseline-Disziplin) und committed Baseline.

Die Fälle leiten sich aus TICKETS.md (AP7-Korbat, Nutzerentscheidung:
„AGENTS.md-Promptregeln ergänzen“), dem AP12-Audit (§5.5, T-V19) und dem
AP7-Design-Brief ab:

* Die Regelquelle ``GENERAL_RULES`` in ``bin/vibe`` enthält die angepasste
  Sektion „Effizienz der Prüfungen“ (verify.sh als einzige Prüfschnittstelle)
  und die neue Sektion „Baseline-Disziplin (verbindlich)“ mit den sechs
  Kernaussagen: Exit 6/7 am Code beheben, monotone Schwellen/Einträge,
  Änderungen nur per geprüftem Merge-Request, ``--write-baseline`` nur als
  lokaler Vorschlag, keine Umgebungsangaben/Geheimnisse, keine
  Selbstreferenz in ``VERIFY_*``.
* Derselbe Block liegt konsistent in allen fünf ``templates/*/AGENTS.md``
  und in der ``AGENTS.md`` des Repositories (Marker-Invariante).
* ``tests/verify-baseline.json`` existiert mit Schema v1 (version=1,
  min_tests=2000, leere envs-Map) und enthält keine Hostnamen, IP-Adressen,
  Geheimnisse oder absoluten Pfade (öffentliches Repository).

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

BASELINE_SECTION = "## Baseline-Disziplin (verbindlich)"
EFFICIENCY_SECTION = "## Effizienz der Prüfungen (verbindlich)"
MARK_START = "<!-- vibe:general-rules -->"
MARK_END = "<!-- /vibe:general-rules -->"


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


class GeneralRulesTest(unittest.TestCase):
    """AK T-V19/AGENTS: eine Regelquelle mit Baseline-Disziplin."""

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

    def test_rules_contain_the_baseline_discipline_exactly_once(self):
        """Vorbedingung: ``GENERAL_RULES`` aus ``bin/vibe``.
        Aktion: Überschrift zählen.
        Erwartung: genau 1 Vorkommen.
        Fehlerfall: Regel fehlt oder ist dupliziert.
        """
        rules = self.cli.GENERAL_RULES
        self.assertEqual(1, rules.count(BASELINE_SECTION), rules)

    def test_baseline_discipline_fixes_exit_codes_in_the_code(self):
        """Vorbedingung: Sektion „Baseline-Disziplin“.
        Aktion: Aussagen zu Exit 7/6 lesen.
        Erwartung: Exit 7 = neue Regression, Exit 6 = fehlender
        Testnachweis; beides ist am Code zu beheben, nie über die Baseline.
        Fehlerfall: Ein Agent könnte Fehler in die Baseline schreiben.
        """
        text = section(self.cli.GENERAL_RULES, BASELINE_SECTION)
        for marker in ("Exit 7", "Exit 6", "Code", "Baseline"):
            self.assertIn(marker, text, "%r fehlt in %r" % (marker, BASELINE_SECTION))

    def test_baseline_discipline_requires_monotone_reviewed_changes(self):
        """Vorbedingung: Sektion „Baseline-Disziplin“.
        Aktion: Aussagen zu Monotonie und Review lesen.
        Erwartung: Schwellen nur erhöhen, Einträge nur entfernen, wenn das
        Modul grün ist; Änderungen nur per geprüftem Merge-Request.
        Fehlerfall: Absenkungen im Alleingang wären erlaubt.
        """
        text = section(self.cli.GENERAL_RULES, BASELINE_SECTION)
        for marker in (
            "monoton",
            "VERIFY_MIN_TESTS",
            "erhöhen",
            "grün",
            "Merge-Request",
            "nie im Alleingang",
        ):
            self.assertIn(marker, text, "%r fehlt in %r" % (marker, BASELINE_SECTION))

    def test_baseline_discipline_makes_write_baseline_a_local_proposal(self):
        """Vorbedingung: Sektion „Baseline-Disziplin“.
        Aktion: Aussage zu ``--write-baseline`` lesen.
        Erwartung: nur lokaler, ignorierter Vorschlag; kanonisch ausschließlich
        per geprüftem Merge-Request.
        Fehlerfall: Der Schreibbefehl gälte als kanonische Änderung.
        """
        text = section(self.cli.GENERAL_RULES, BASELINE_SECTION)
        self.assertIn("--write-baseline", text)
        self.assertRegex(text.lower(), r"unversioniert|ignoriert")
        self.assertIn("Merge-Request", text)

    def test_baseline_discipline_forbids_environment_details(self):
        """Vorbedingung: Sektion „Baseline-Disziplin“.
        Aktion: Aussage zu Umgebungsangaben lesen.
        Erwartung: IP-Adressen, Hostnamen, Geheimnisse und absolute Pfade
        gehören nie in eine Baseline-Datei; das Repository ist öffentlich.
        Fehlerfall: Umgebungsdaten könnten committet werden.
        """
        text = section(self.cli.GENERAL_RULES, BASELINE_SECTION)
        for marker in (
            "IP-Adressen",
            "Hostnamen",
            "Geheimnisse",
            "absolute Pfade",
            "öffentlich",
        ):
            self.assertIn(marker, text, "%r fehlt in %r" % (marker, BASELINE_SECTION))

    def test_baseline_discipline_forbids_self_reference(self):
        """Vorbedingung: Sektion „Baseline-Disziplin“.
        Aktion: Aussage zur Selbstreferenz lesen.
        Erwartung: ``VERIFY_QUICK``/``VERIFY_PACKAGE``/``VERIFY_FULL`` dürfen
        die Prüfung nicht selbst aufrufen (Rekursionsschutz, Exit 3).
        Fehlerfall: Die B1-Falle bleibt eine reine Konvention.
        """
        text = section(self.cli.GENERAL_RULES, BASELINE_SECTION)
        for marker in ("VERIFY_QUICK", "VERIFY_PACKAGE", "VERIFY_FULL",
                       "Rekursionsschutz", "Exit 3"):
            self.assertIn(marker, text, "%r fehlt in %r" % (marker, BASELINE_SECTION))

    def test_efficiency_section_names_verify_sh_as_the_single_interface(self):
        """Vorbedingung: Sektion „Effizienz der Prüfungen“.
        Aktion: Aussagen zur Prüfschnittstelle lesen.
        Erwartung: Die Projektprüfung läuft ausschließlich über
        ``verify.sh quick|package|full``; der Nachweisumfang bleibt erhalten.
        Fehlerfall: Agenten setzen Prüfinhalte weiterhin selbst zusammen.
        """
        text = section(self.cli.GENERAL_RULES, EFFICIENCY_SECTION)
        for marker in (
            "verify.sh",
            "quick|package|full",
            "Prüfschnittstelle",
            "genau einmal",
            "Nachweisumfang",
            "abgeschwächt",
        ):
            self.assertIn(marker, text,
                          "%r fehlt in %r" % (marker, EFFICIENCY_SECTION))

    def test_all_templates_carry_the_baseline_discipline(self):
        """Vorbedingung: alle ``templates/*/AGENTS.md``.
        Aktion: verwalteten Block vergleichen.
        Erwartung: ``GENERAL_RULES`` ist bytengleich enthalten; genau ein
        Markerpaar; die Baseline-Disziplin steht je genau einmal.
        Fehlerfall: Eine Vorlage driftet von der Regelquelle ab.
        """
        self.assertEqual(5, len(TEMPLATES), TEMPLATES)
        for path in TEMPLATES:
            with self.subTest(path=str(path)):
                text = path.read_text(encoding="utf-8")
                self.assertIn(self.cli.GENERAL_RULES, text,
                              "Vorlage weicht von GENERAL_RULES ab")
                self.assertEqual(1, text.count(MARK_START))
                self.assertEqual(1, text.count(MARK_END))
                self.assertEqual(1, text.count(BASELINE_SECTION), path)

    def test_repository_agents_file_carries_the_baseline_discipline(self):
        """Vorbedingung: ``AGENTS.md`` im Repository-Wurzelverzeichnis.
        Aktion: Marker und Block prüfen.
        Erwartung: Der verwaltete Block steht genau einmal und enthält die
        Baseline-Disziplin (Marker-Invariante).
        Fehlerfall: Die Repository-Regeln weichen von der Regelquelle ab.
        """
        self.assertTrue(AGENTS.is_file(), "AGENTS.md fehlt im Repository")
        text = AGENTS.read_text(encoding="utf-8")
        self.assertIn(self.cli.GENERAL_RULES, text)
        self.assertEqual(1, text.count(MARK_START))
        self.assertEqual(1, text.count(MARK_END))
        self.assertEqual(1, text.count(BASELINE_SECTION))


class CommittedBaselineManifestTest(unittest.TestCase):
    """AK: kanonische Baseline v1 ohne Umgebungsdetails."""

    def read(self):
        self.assertTrue(
            MANIFEST.is_file(),
            "tests/verify-baseline.json fehlt (kanonische Baseline)",
        )
        return json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_has_schema_v1_and_the_initial_values(self):
        """Vorbedingung: die committed Baseline.
        Aktion: JSON lesen.
        Erwartung: ``version`` 1, ``min_tests`` 2000, ``envs`` ist eine leere
        Map (Befüllung erfolgt per Review, nicht in diesem Paket).
        Fehlerfall: Fehlende Datei, falsche Version oder abweichende Schwelle.
        """
        data = self.read()
        self.assertEqual(1, data.get("version"))
        self.assertEqual(2000, data.get("min_tests"))
        self.assertEqual({}, data.get("envs"))

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
        Erwartung: ``min_tests`` ist mindestens 2000 — eine Senkung wäre nur
        per Review zulässig, nicht durch dieses Paket.
        Fehlerfall: Die Ausgangsschwelle liegt unter dem vereinbarten Wert.
        """
        data = self.read()
        self.assertGreaterEqual(data.get("min_tests", 0), 2000)


if __name__ == "__main__":
    unittest.main()
