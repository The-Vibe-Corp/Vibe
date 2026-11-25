"""Prüfbaseline: Tri-State, Labels, Vorrang, Ratschen und Signaturnormalisierung.

Aufruf: python3 -m unittest tests.unit.test_verify_baseline -v
"""


# ===========================================================================
# T-/T-/T-: Baseline-Dreizustände, Env, Ratchet
# ===========================================================================

import importlib.machinery
import importlib.util
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_support as support  # noqa: E402

LABEL = "lichter"
OTHER_LABEL = "lichter-2"


class BaselineFixture(support.VerifyFixture):
    """Projekt mit grünem und rotem Testmodul und Hilfen für Baseline-Dateien."""

    def standard_project(self, red=True, labels=None, name="projekt"):
        lines = [
            "TYPE=generic",
            'VERIFY_QUICK="true"',
            'VERIFY_TESTS="tests"',
        ]
        if labels:
            lines.extend(labels)
        project = self.make_project(lines, name=name)
        if red:
            self.write_module(project, "tests/test_rot.py", support.RED_TEST)
        return project

    def add_green_tests(self, project, count=1):
        body = ["import unittest\n\n", "class GruenTest(unittest.TestCase):\n"]
        for index in range(count):
            body.append(
                "    def test_%d(self):\n"
                "        self.assertTrue(True)\n" % index
            )
        self.write_module(project, "tests/test_gut.py", "".join(body))

    def capture(self, project, label=LABEL, *extra):
        """Erzeugt die lokale Baseline über den dokumentierten Schreibweg."""
        return self.verify(
            "full", "--env", label, "--write-baseline", *extra,
            project=project,
        )

    def capture_to_committed(self, project, label=LABEL):
        """Erzeugt die lokale Baseline und macht sie zur committed Baseline."""
        result = self.capture(project, label)
        local = support.local_baseline(project)
        self.assertTrue(
            local.is_file(),
            "--write-baseline schrieb keine lokale Datei:\n"
            + support.output(result),
        )
        data = support.read_baseline(local)
        support.write_baseline(
            support.committed_baseline(project),
            envs=data.get("envs", {}),
            min_tests=data.get("min_tests", 1),
        )
        local.unlink()
        return data


class BaselineTriStateTest(BaselineFixture):
    """T-V17: grün, Baseline-OK, Regression und ungültige Baseline."""

    def test_green_run_exits_0_and_reports_the_result(self):
        """Vorbedingung: alle Tests grün, keine Baseline.
        Aktion: ``full`` ausführen.
        Erwartung: Exit 0; eine ``VERIFY_RESULT:``-Zeile nennt Modus und
        Testanzahl.
        Fehlerfall: Der Volllauf verlangt weiterhin einen frei
        konfigurierten VERIFY_FULL-Befehl.
        """
        project = self.standard_project(red=False)
        self.add_green_tests(project, count=2)
        result = self.verify("full", project=project)
        text = support.output(result)
        self.assertEqual(0, result.returncode, text)
        line = next(
            (item for item in text.splitlines()
             if item.startswith("VERIFY_RESULT:")),
            "",
        )
        self.assertTrue(line, "VERIFY_RESULT-Zeile fehlt:\n" + text)
        self.assertIn("mode=full", line)
        self.assertIn("tests=2", line)

    def test_known_failure_matching_the_baseline_is_baseline_ok(self):
        """Vorbedingung: Ein Modul schlägt rot; die lokale Baseline wird über
        ``--write-baseline`` erzeugt und als committed Baseline hinterlegt.
        Aktion: ``full --env lichter`` ausführen.
        Erwartung: Exit 0, Ausgabe enthält ``BASELINE-OK`` und eine
        ``VERIFY_RESULT:``-Zeile mit ``baseline_ok=1`` und ``env=lichter``;
        das bekannte rote Modul wird aufgelistet.
        Fehlerfall: Bekannte Rote werden als Regression gewertet oder
        stillschweigend verschluckt.
        """
        project = self.standard_project()
        data = self.capture_to_committed(project)
        failures = data["envs"][LABEL]["failures"]
        self.assertTrue(failures, "Die lokale Baseline enthält keinen Fehler")
        self.assertEqual("tests.test_rot", failures[0]["module"])
        self.assertTrue(failures[0]["signature"].startswith("sha256:"),
                        failures[0])
        self.assertTrue(failures[0]["class"], failures[0])

        result = self.verify("full", "--env", LABEL, project=project)
        text = support.output(result)
        self.assertEqual(0, result.returncode, text)
        self.assertIn("BASELINE-OK", text)
        self.assertIn("tests.test_rot", text)
        self.assertRegex(
            text,
            r"(?m)^VERIFY_RESULT:.*baseline_ok=1.*env=lichter",
            "Maschinenlesbare Abschlusszeile fehlt oder ist falsch:\n" + text,
        )

    def test_new_red_module_not_in_the_baseline_exits_7(self):
        """Vorbedingung: committed Baseline mit passendem Label, aber ohne
        Fehler; ein Modul schlägt rot.
        Aktion: ``full --env lichter`` ausführen.
        Erwartung: Exit 7 mit dem roten Modul in der Diff-Ausgabe.
        Fehlerfall: Die Baseline maskiert neue Fehler (Exit 0).
        """
        project = self.standard_project()
        support.write_baseline(
            support.committed_baseline(project),
            envs={LABEL: {"failures": []}},
            min_tests=1,
        )
        result = self.verify("full", "--env", LABEL, project=project)
        text = support.output(result)
        self.assertEqual(7, result.returncode, text)
        self.assertIn("tests.test_rot", text)
        self.assertNotIn("BASELINE-OK", text)

    def test_changed_signature_of_a_known_module_exits_7(self):
        """Vorbedingung: Das rote Modul ist in der Baseline; danach ändert
        sich Fehlerklasse und Meldung (andere Signatur).
        Aktion: ``full --env lichter`` ausführen.
        Erwartung: Exit 7; ein umbenannter Fehler gilt nicht als bekannt.
        Fehlerfall: Nur der Modulname wird verglichen.
        """
        project = self.standard_project()
        self.capture_to_committed(project)
        self.write_module(project, "tests/test_rot.py", support.RED_TEST_OTHER)

        result = self.verify("full", "--env", LABEL, project=project)
        text = support.output(result)
        self.assertEqual(7, result.returncode, text)
        self.assertIn("tests.test_rot", text)

    def test_count_below_the_minimum_exits_6(self):
        """Vorbedingung: zwei grüne Tests, committed ``min_tests=50``.
        Aktion: ``full --env lichter`` ausführen.
        Erwartung: Exit 6 (Testnachweis fehlt).
        Fehlerfall: Zu wenige Tests gelten als bestandener Nachweis.
        """
        project = self.standard_project(red=False)
        self.add_green_tests(project, count=2)
        support.write_baseline(
            support.committed_baseline(project),
            envs={LABEL: {"failures": []}},
            min_tests=50,
        )
        result = self.verify("full", "--env", LABEL, project=project)
        self.assertEqual(6, result.returncode, support.output(result))

    def test_new_red_and_count_below_the_minimum_exits_7(self):
        """Vorbedingung: ``min_tests=50`` und ein neues rotes Modul.
        Aktion: ``full --env lichter`` ausführen.
        Erwartung: Exit 7 — die Regression gewinnt gegen den fehlenden
        Nachweis.
        Fehlerfall: Exit 6 verdeckt den neuen Fehler.
        """
        project = self.standard_project(red=True)
        support.write_baseline(
            support.committed_baseline(project),
            envs={LABEL: {"failures": []}},
            min_tests=50,
        )
        result = self.verify("full", "--env", LABEL, project=project)
        self.assertEqual(7, result.returncode, support.output(result))

    def test_invalid_baseline_json_exits_3(self):
        """Vorbedingung: ``tests/verify-baseline.json`` ist kein JSON.
        Aktion: ``full`` ausführen.
        Erwartung: Exit 3 mit Meldung, die die Baseline-Datei nennt.
        Fehlerfall: Die kaputte Datei wird still ignoriert.
        """
        project = self.standard_project(red=False)
        self.add_green_tests(project)
        support.committed_baseline(project).write_text(
            "{ kein json\n", encoding="utf-8"
        )
        result = self.verify("full", project=project)
        text = support.output(result)
        self.assertEqual(3, result.returncode, text)
        self.assertIn("verify-baseline", text)

    def test_invalid_baseline_schema_exits_3(self):
        """Vorbedingung: Baseline mit unbekannter Version.
        Aktion: ``full`` ausführen.
        Erwartung: Exit 3 (Schemafehler zählt als ungültige Konfiguration).
        Fehlerfall: Unbekannte Schemata werden akzeptiert oder ignoriert.
        """
        project = self.standard_project(red=False)
        self.add_green_tests(project)
        support.write_baseline(
            support.committed_baseline(project), envs={}, min_tests=1,
            version=2,
        )
        result = self.verify("full", project=project)
        text = support.output(result)
        self.assertEqual(3, result.returncode, text)
        self.assertIn("verify-baseline", text)

    def test_package_mode_does_not_consult_the_baseline(self):
        """Vorbedingung: ``VERIFY_PACKAGE_TESTS="tests"`` und ein Modul, das
        in der (passenden) committed Baseline als bekannt rot steht.
        Aktion: ``package --env lichter`` ausführen.
        Erwartung: Exit 5 — der Paketmodus kennt keine Baseline; es gilt
        Fehlerfreiheit.
        Fehlerfall: Die Baseline macht den Paketmodus grün.
        """
        project = self.make_project(
            [
                "TYPE=generic",
                'VERIFY_QUICK="true"',
                'VERIFY_TESTS="tests"',
                'VERIFY_PACKAGE_TESTS="tests"',
            ]
        )
        self.write_module(project, "tests/test_rot.py", support.RED_TEST)
        self.capture_to_committed(project)
        result = self.verify("package", "--env", LABEL, project=project)
        text = support.output(result)
        self.assertEqual(5, result.returncode, text)
        self.assertIn("test_rot", text)


class EnvLabelTest(BaselineFixture):
    """T-V18: exaktes Label, kein Best-Match, lokal schreiben."""

    def test_verify_env_from_project_env_selects_the_section(self):
        """Vorbedingung: ``VERIFY_ENV="lichter"`` in project.env; die lokale
        Baseline stammt aus genau diesem Label.
        Aktion: ``full`` ohne ``--env`` ausführen.
        Erwartung: Exit 0, ``BASELINE-OK``.
        Fehlerfall: Das konfigurierte Label wird ignoriert.
        """
        project = self.standard_project(labels=['VERIFY_ENV="%s"' % LABEL])
        data = self.capture_to_committed(project)
        # Die committed Baseline stammt aus demselben Label; kein --env nötig.
        self.assertIn(LABEL, data["envs"])
        result = self.verify("full", project=project)
        self.assertEqual(0, result.returncode, support.output(result))
        self.assertIn("BASELINE-OK", support.output(result))

    def test_similar_label_does_not_match(self):
        """Vorbedingung: Die Baseline kennt nur ``lichter``; der Lauf nutzt
        ``lichter-2``.
        Aktion: ``full --env lichter-2`` ausführen.
        Erwartung: Exit 7, kein ``BASELINE-OK``; die Meldung nennt den
        Neuaufbau über ``--write-baseline``.
        Fehlerfall: Ein ähnliches Label wird als Treffer akzeptiert
        (Best-Match).
        """
        project = self.standard_project()
        support.write_baseline(
            support.committed_baseline(project),
            envs={LABEL: {"failures": []}},
            min_tests=1,
        )
        result = self.verify("full", "--env", OTHER_LABEL, project=project)
        text = support.output(result)
        self.assertEqual(7, result.returncode, text)
        self.assertNotIn("BASELINE-OK", text)
        self.assertIn("--write-baseline", text)

    def test_green_run_with_mismatched_label_still_exits_0(self):
        """Vorbedingung: Baseline für fremdes Label mit bekanntem Fehler;
        alle Tests grün.
        Aktion: ``full --env lichter`` ausführen.
        Erwartung: Exit 0 — ohne Fehlschläge gibt es keine Regression.
        Fehlerfall: Der Mismatch blockiert einen grünen Lauf.
        """
        project = self.standard_project(red=False)
        self.add_green_tests(project)
        support.write_baseline(
            support.committed_baseline(project),
            envs={
                "anderes": {
                    "failures": [
                        {
                            "module": "tests.test_fremd",
                            "class": "AssertionError",
                            "signature": "sha256:" + "0" * 64,
                        }
                    ]
                }
            },
            min_tests=1,
        )
        result = self.verify("full", "--env", LABEL, project=project)
        self.assertEqual(0, result.returncode, support.output(result))

    def test_write_baseline_preserves_other_env_sections(self):
        """Vorbedingung: Die lokale Baseline enthält bereits eine Sektion
        ``anderes``.
        Aktion: ``full --write-baseline --env lichter`` ausführen.
        Erwartung: ``lichter`` wird ergänzt; die Sektion ``anderes`` bleibt
        unverändert.
        Fehlerfall: Der Schreibvorgang überschreibt die ganze Datei.
        """
        project = self.standard_project()
        other = {
            "failures": [
                {
                    "module": "tests.test_alt",
                    "class": "AssertionError",
                    "signature": "sha256:" + "a" * 64,
                }
            ]
        }
        support.write_baseline(
            support.local_baseline(project),
            envs={"anderes": other},
            min_tests=1,
        )
        result = self.capture(project)
        # Entscheidung D2: --write-baseline ändert das Laufurteil nicht. Die
        # lokale Datei hat keine Sektion für ``lichter`` (Mismatch) und der
        # Lauf ist rot; die Datei wird geschrieben und der Lauf endet mit 7.
        self.assertEqual(7, result.returncode, support.output(result))
        self.assertTrue(support.local_baseline(project).is_file(),
                        support.output(result))
        data = support.read_baseline(support.local_baseline(project))
        self.assertIn(LABEL, data.get("envs", {}))
        self.assertEqual(other, data["envs"].get("anderes"))

    def test_write_baseline_refuses_to_lower_the_minimum(self):
        """Vorbedingung: Die lokale Baseline fordert ``min_tests=3``; der
        Aufruf verlangt ``--min-tests 1``.
        Aktion: ``full --write-baseline --min-tests 1`` ausführen.
        Erwartung: Exit 3; die Datei bleibt bei ``min_tests=3``.
        Fehlerfall: Die Schwelle wird abgesenkt (Baseline-Gaming).
        """
        project = self.standard_project(red=False)
        self.add_green_tests(project, count=3)
        support.write_baseline(
            support.local_baseline(project), envs={}, min_tests=3
        )
        result = self.verify(
            "full", "--env", LABEL, "--write-baseline", "--min-tests", "1",
            project=project,
        )
        self.assertEqual(3, result.returncode, support.output(result))
        data = support.read_baseline(support.local_baseline(project))
        self.assertEqual(3, data["min_tests"],
                         "Die Mindestanzahl wurde abgesenkt")

    def test_write_baseline_marks_the_local_file_as_unversioned(self):
        """Vorbedingung: Ein Lauf mit ``--write-baseline``.
        Aktion: Ausgabe prüfen.
        Erwartung: Sie nennt die lokale Datei, weist auf den unversionierten
        Vorschlag hin und verweist auf die Kanonisierung per Merge-Request.
        Fehlerfall: Der lokale Vorschlag wird als kanonisch dargestellt.
        """
        project = self.standard_project()
        result = self.capture(project)
        text = support.output(result)
        self.assertIn(".vibe/verify-baseline", text)
        self.assertRegex(text.lower(), r"unversioniert|ignoriert")
        self.assertIn("Merge-Request", text)

    def test_baseline_option_overrides_the_committed_manifest(self):
        """Vorbedingung: Die committed Baseline kennt keinen Fehler; eine
        separate Baseline-Datei passt exakt zu Label und Signatur.
        Aktion: ``full --env lichter --baseline <datei>`` ausführen.
        Erwartung: Exit 0, ``BASELINE-OK`` — die Option ersetzt die
        Manifest-Dateien.
        Fehlerfall: ``--baseline`` wird ignoriert.
        """
        project = self.standard_project()
        support.write_baseline(
            support.committed_baseline(project),
            envs={LABEL: {"failures": []}},
            min_tests=1,
        )
        result = self.capture(project)
        local = support.local_baseline(project)
        self.assertTrue(local.is_file(), support.output(result))
        override = self.base / "override-baseline.json"
        override.write_bytes(local.read_bytes())
        local.unlink()

        second = self.verify(
            "full", "--env", LABEL, "--baseline", str(override),
            project=project,
        )
        text = support.output(second)
        self.assertEqual(0, second.returncode, text)
        self.assertIn("BASELINE-OK", text)


class LocalBaselinePrecedenceTest(BaselineFixture):
    """T-V18/D1: die lokale Env-Sektion gilt exklusiv, nicht als Union.

    Präzedenz D1: Die erste Quelle mit einer Sektion für das gewählte Label
    gilt allein. Eine lokale ``.vibe/verify-baseline`` mit derselben
    Env-Sektion überdeckt die gleichnamige Sektion der committed
    ``tests/verify-baseline.json`` vollständig; es entsteht keine
    Vereinigungsmenge der Failure-Einträge. Nur so kann der lokale Vorschlag
    eine Regression nicht über die committed Liste „abwählen", und nur so
    bleibt die kanonische Datei die Untergrenze für den Merge-Request.
    """

    def test_local_env_section_overrides_the_committed_section(self):
        """Vorbedingung: committed Baseline kennt den Fehler von
        ``tests.test_rot``; die lokale Baseline besitzt dieselbe Env-Sektion
        ``lichter``, aber mit leerer Failure-Liste; das Modul schlägt rot.
        Aktion: ``full --env lichter`` ausführen.
        Erwartung: Exit 7 (neue Regression) und kein ``BASELINE-OK`` — die
        lokale Sektion überdeckt die committed Sektion exklusiv.
        Fehlerfall: Beide Sektionen werden vereinigt; der bekannte Fehler aus
        der committed Datei gilt weiter als bekannt (Exit 0) und die
        Regression bliebe unbemerkt.
        """
        project = self.standard_project()
        data = self.capture_to_committed(project)
        failures = data["envs"][LABEL]["failures"]
        self.assertTrue(
            failures,
            "Vorbedingung verletzt: committed Baseline enthält keinen Fehler",
        )
        self.assertEqual("tests.test_rot", failures[0]["module"])
        # Gleiches Label, disjunkte Failure-Liste: lokal leer.
        support.write_baseline(
            support.local_baseline(project),
            envs={LABEL: {"failures": []}},
            min_tests=1,
        )

        result = self.verify("full", "--env", LABEL, project=project)
        text = support.output(result)

        self.assertEqual(7, result.returncode, text)
        self.assertNotIn(
            "BASELINE-OK", text,
            "Die lokale leere Sektion wurde mit der committed Sektion "
            "vereinigt (Union statt D1-Exklusivität):\n" + text,
        )
        self.assertIn("tests.test_rot", text)

    def test_disjoint_local_and_committed_failures_are_not_united(self):
        """Vorbedingung: committed Sektion kennt den Laufzeitfehler; die
        lokale Sektion desselben Labels kennt nur einen anderen (nicht
        auftretenden) Fehler.
        Aktion: ``full --env lichter`` ausführen.
        Erwartung: Exit 7 — nur der lokale Eintrag gilt als bekannt, der
        tatsächliche Fehler ist damit neu.
        Fehlerfall: Die Sektionen werden vereinigt und der committed Eintrag
        macht den Lauf grün (Exit 0).
        """
        project = self.standard_project()
        data = self.capture_to_committed(project)
        self.assertTrue(data["envs"][LABEL]["failures"], data)
        support.write_baseline(
            support.local_baseline(project),
            envs={
                LABEL: {
                    "failures": [
                        {
                            "module": "tests.test_alt",
                            "class": "AssertionError",
                            "signature": "sha256:" + "b" * 64,
                        }
                    ]
                }
            },
            min_tests=1,
        )

        result = self.verify("full", "--env", LABEL, project=project)
        text = support.output(result)

        self.assertEqual(7, result.returncode, text)
        self.assertNotIn(
            "BASELINE-OK", text,
            "Die lokale Sektion wurde mit der committed Sektion vereinigt "
            "(Union statt D1-Exklusivität):\n" + text,
        )
        self.assertIn("tests.test_rot", text)

    def test_local_empty_section_keeps_a_green_run_green(self):
        """Vorbedingung: committed Sektion kennt einen Fehler, die lokale
        Sektion desselben Labels ist leer; alle Tests sind grün.
        Aktion: ``full --env lichter`` ausführen.
        Erwartung: Exit 0 — ohne beobachteten Fehlschlag gibt es keine
        Regression, unabhängig von der überdeckten committed Sektion.
        Fehlerfall: Die Exklusivität blockiert einen gesunden Lauf, weil
        Einträge der committed Datei fehlen.
        """
        project = self.standard_project(red=False)
        self.add_green_tests(project, count=2)
        support.write_baseline(
            support.committed_baseline(project),
            envs={
                LABEL: {
                    "failures": [
                        {
                            "module": "tests.test_alt",
                            "class": "AssertionError",
                            "signature": "sha256:" + "c" * 64,
                        }
                    ]
                }
            },
            min_tests=1,
        )
        support.write_baseline(
            support.local_baseline(project),
            envs={LABEL: {"failures": []}},
            min_tests=1,
        )

        result = self.verify("full", "--env", LABEL, project=project)
        self.assertEqual(0, result.returncode, support.output(result))


class RatchetTest(BaselineFixture):
    """T-V19: effektives Minimum ist monoton."""

    def test_committed_min_tests_raises_the_threshold(self):
        """Vorbedingung: zwei grüne Tests, committed ``min_tests=50``.
        Aktion: ``full`` ausführen.
        Erwartung: Exit 6.
        Fehlerfall: Die committed Schwelle bleibt unberücksichtigt.
        """
        project = self.standard_project(red=False)
        self.add_green_tests(project, count=2)
        support.write_baseline(
            support.committed_baseline(project),
            envs={LABEL: {"failures": []}},
            min_tests=50,
        )
        result = self.verify("full", "--env", LABEL, project=project)
        self.assertEqual(6, result.returncode, support.output(result))

    def test_local_min_tests_raises_the_threshold(self):
        """Vorbedingung: zwei grüne Tests, lokale ``min_tests=50``.
        Aktion: ``full`` ausführen.
        Erwartung: Exit 6.
        Fehlerfall: Die lokale Schwelle bleibt unberücksichtigt.
        """
        project = self.standard_project(red=False)
        self.add_green_tests(project, count=2)
        support.write_baseline(
            support.local_baseline(project), envs={}, min_tests=50
        )
        result = self.verify("full", project=project)
        self.assertEqual(6, result.returncode, support.output(result))

    def test_min_tests_option_raises_the_threshold(self):
        """Vorbedingung: zwei grüne Tests; ``--min-tests 50``.
        Aktion: ``full`` ausführen.
        Erwartung: Exit 6 (die Option ersetzt VERIFY_MIN_TESTS).
        Fehlerfall: ``--min-tests`` wird ignoriert.
        """
        project = self.standard_project(red=False)
        self.add_green_tests(project, count=2)
        result = self.verify(
            "full", "--min-tests", "50", project=project
        )
        self.assertEqual(6, result.returncode, support.output(result))

    def test_write_baseline_writes_at_least_the_effective_minimum(self):
        """Vorbedingung: vier grüne Tests; committed ``min_tests=3``, lokal
        bisher ``min_tests=1``.
        Aktion: ``full --write-baseline`` ausführen.
        Erwartung: Die lokale Datei fordert danach ``min_tests=3`` (Maximum
        aller Quellen).
        Fehlerfall: Der Schreibvorgang setzt eine niedrigere Schwelle.
        """
        project = self.standard_project(red=False)
        self.add_green_tests(project, count=4)
        support.write_baseline(
            support.committed_baseline(project),
            envs={LABEL: {"failures": []}},
            min_tests=3,
        )
        support.write_baseline(
            support.local_baseline(project), envs={}, min_tests=1
        )
        result = self.capture(project)
        self.assertTrue(support.local_baseline(project).is_file(),
                        support.output(result))
        data = support.read_baseline(support.local_baseline(project))
        self.assertEqual(3, data["min_tests"],
                         "min_tests wurde nicht auf das effektive Minimum "
                         "angehoben")


def load_engine():
    """Lädt ``scripts/verify_engine.py`` als Modul (nur Definitionen)."""
    loader = importlib.machinery.SourceFileLoader(
        "verify_engine_ap7_signature_under_test", str(support.ENGINE)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class SignatureNormalizationTest(unittest.TestCase):
    """GH-46: Signaturstabilität über Temp- und Checkout-Wurzeln.

    Die committed Baseline (``tests/verify-baseline.json``) speichert
    ``failure_signature`` = sha256 über Modul, Fehlerklasse und
    ``normalize_message``-Ausgabe. Gelangt eine laufspezifische Temp- oder
    Checkout-Wurzel in die normalisierte Meldung, matcht der Eintrag nie
    wieder bzw. nur in einer einzigen Arbeitskopie — jeder Volllauf meldet
    dann eine falsche neue Regression. Absolute Pfade müssen deshalb
    unabhängig von der Quoting-Umgebung (JSON-String, Python-Repräsentation)
    entfernt werden.
    """

    @classmethod
    def setUpClass(cls):
        cls.engine = load_engine()

    def test_double_quoted_absolute_path_is_replaced(self):
        """Vorbedingung: JSON-artige Meldung mit doppelt gequotetem
        Temp-Pfad (Muster des belegten ``test_sandbox``-Fehlers).
        Aktion: ``normalize_message`` ausführen.
        Erwartung: Die laufspezifische Wurzel ist verschwunden und durch
        ``<pfad>`` ersetzt.
        Fehlerfall: Der Pfad bleibt roh in der Meldung und damit in der
        Signatur; die Baseline matcht bei jedem Volllauf anders.
        """
        message = (
            'AssertionError: Zustand "/tmp/vv-4711/vv-ab12cd/state.json" '
            "ist nicht lesbar"
        )

        normalized = self.engine.normalize_message(message)

        self.assertNotIn("/tmp/vv-4711", normalized, normalized)
        self.assertIn("<pfad>", normalized)

    def test_single_quoted_absolute_path_is_replaced(self):
        """Vorbedingung: FileNotFoundError-Meldung mit einfach gequotetem
        Checkout-Pfad (Muster des belegten ``test_project_management``-
        Fehlers).
        Aktion: ``normalize_message`` ausführen.
        Erwartung: Der Checkout-Pfad ist durch ``<pfad>`` ersetzt.
        Fehlerfall: Die Signatur funktioniert nur in genau dieser
        Arbeitskopie; am Integrationsstand gilt der bekannte Fehler als neu.
        """
        message = (
            "FileNotFoundError: [Errno 2] No such file or directory: "
            "'/var/log/vibe-wt/templates/common/.opencode/agents/test-agent.md'"
        )

        normalized = self.engine.normalize_message(message)

        self.assertNotIn("/var/log/vibe-wt", normalized, normalized)
        self.assertIn("<pfad>", normalized)

    def test_whitespace_prefixed_absolute_path_stays_normalized(self):
        """Vorbedingung: Meldung mit absolutem Pfad nach Whitespace.
        Aktion: ``normalize_message`` ausführen.
        Erwartung: Exakt das Bestandsverhalten: `` <pfad>``; die übrigen
        Normalisierungen (``line <n>``) bleiben erhalten.
        Fehlerfall: Der Fix für gequotete Pfade verdrängt das bisherige
        Verhalten und Baseline-Einträge mit whitespace-getrennten Pfaden
        brechen.
        """
        message = "Error at /tmp/vv-4711/data.json line 12"

        self.assertEqual(
            "Error at <pfad> line <n>",
            self.engine.normalize_message(message),
        )

    def test_signature_is_stable_for_different_temp_roots_in_json(self):
        """Vorbedingung: Zwei Meldungen unterscheiden sich nur in der
        doppelt gequoteten Temp-Wurzel (``vv-aaaa``/``vv-bbbb``).
        Aktion: ``failure_signature`` für beide bilden.
        Erwartung: Identische Signatur — der bekannte ``test_sandbox``-Fehler
        bleibt über Vollläufe hinweg BASELINE-OK.
        Fehlerfall: Jeder Lauf erzeugt eine neue Signatur und damit eine
        falsche „Neue Regression".
        """
        first = (
            'AssertionError: Zustand "/tmp/vv-4711/vv-aaaa/state.json" '
            "ist nicht lesbar"
        )
        second = (
            'AssertionError: Zustand "/tmp/vv-4711/vv-bbbb/state.json" '
            "ist nicht lesbar"
        )

        self.assertEqual(
            self.engine.failure_signature(
                "tests.unit.test_sandbox", "AssertionError", first
            ),
            self.engine.failure_signature(
                "tests.unit.test_sandbox", "AssertionError", second
            ),
        )

    def test_signature_is_stable_for_different_quoted_checkout_roots(self):
        """Vorbedingung: Zwei FileNotFoundError-Meldungen unterscheiden sich
        nur in der einfach gequoteten Checkout-Wurzel.
        Aktion: ``failure_signature`` für beide bilden.
        Erwartung: Identische Signatur — der bekannte Eintrag gilt in jeder
        Arbeitskopie und am Integrationsstand.
        Fehlerfall: Die Baseline matcht nur im Ursprungs-Checkout; der
        Abnahme-Volllauf meldet eine falsche Regression.
        """
        first = (
            "FileNotFoundError: [Errno 2] No such file or directory: "
            "'/var/log/vibe-wt/vibe-GH-46-nrO7K6/templates/common/"
            ".opencode/agents/test-agent.md'"
        )
        second = (
            "FileNotFoundError: [Errno 2] No such file or directory: "
            "'/var/log/vibe-wt/vibe-integration/templates/common/"
            ".opencode/agents/test-agent.md'"
        )

        self.assertEqual(
            self.engine.failure_signature(
                "tests.unit.test_project_management", "FileNotFoundError", first
            ),
            self.engine.failure_signature(
                "tests.unit.test_project_management", "FileNotFoundError", second
            ),
        )

    def test_signature_differs_when_the_error_content_differs(self):
        """Vorbedingung: Zwei Meldungen haben dieselbe Pfadstruktur, aber
        unterschiedlichen Fehlerinhalt (``erhalten 2``/``erhalten 3``).
        Aktion: ``failure_signature`` für beide bilden.
        Erwartung: Unterschiedliche Signaturen — die Normalisierung darf nur
        Pfade und Zeitangaben, nicht den Fehlerinhalt einebnen.
        Fehlerfall: Ein echter neuer Fehler würde als bekannter Fehler
        maskiert (Über-Normalisierung).
        """
        first = 'AssertionError: erwartet 1, erhalten 2 bei "/tmp/vv-4711/a.json"'
        second = 'AssertionError: erwartet 1, erhalten 3 bei "/tmp/vv-4711/a.json"'

        self.assertNotEqual(
            self.engine.failure_signature(
                "tests.unit.test_sandbox", "AssertionError", first
            ),
            self.engine.failure_signature(
                "tests.unit.test_sandbox", "AssertionError", second
            ),
        )


# ===========================================================================
# / — committete Baseline und Repository-Verweis
# ===========================================================================

import json
import socket
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AGENTS = REPO / "AGENTS.md"
MANIFEST = REPO / "tests" / "verify-baseline.json"
BASELINE_DOC = REPO / "docs" / "verification-baselines.md"

ENV_LABEL = "pi-aarch64-py3.14-namespaces"


class BaselineDocumentReferenceTest(unittest.TestCase):
    """GH-76: Der Repository-Verweis nennt die reale Baseline-Datei."""

    def test_agents_file_uses_the_hyphen_document(self):
        """Vorbedingung: ``AGENTS.md`` und ``docs/``.
        Aktion: den Baseline-Verweis prüfen.
        Erwartung: ``docs/verification-baselines.md`` ist genannt, der alte
        Unterstrich-Pfad fehlt und die Datei existiert.
        Fehlerfall: kaputter Verweis oder fehlende Datei.
        """
        text = AGENTS.read_text(encoding="utf-8")
        self.assertIn("docs/verification-baselines.md", text)
        self.assertNotIn("docs/verification_baselines.md", text)
        self.assertTrue(BASELINE_DOC.is_file(),
                        "docs/verification-baselines.md fehlt")


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
