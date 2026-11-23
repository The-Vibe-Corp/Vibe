"""AP7-Korbat — T-V17/T-V18/T-V19: Baseline-Dreizustände, Env, Ratchet.

Die Fälle leiten sich aus TICKETS.md (AP7-Korbat), dem AP12-Audit (T-V17,
T-V18, T-V19) und dem AP7-Design-Brief ab, nicht aus einem Implementierungsdiff:

* ``full`` bewertet drei Zustände: grün (Exit 0), Baseline-OK (bekannte
  Fehlschläge, gleiche Signaturen, Zählung ≥ Minimum → Exit 0 mit
  ``BASELINE-OK`` und ``VERIFY_RESULT:``-Zeile) und Regression (Exit 7 bei
  neuen/geänderten Fehlern, Exit 6 bei zu wenigen Tests; 7 gewinnt).
  Eine ungültige Baseline endet mit Exit 3, nie mit stillem Ignorieren.
  ``package`` kennt keine Baseline.
* Env-Label ausschließlich explizit (``--env``/``VERIFY_ENV``). Ein ähnliches
  Label gilt nicht als Treffer; ein Mismatch ignoriert die Baseline und
  erklärt den Weg zum Neuaufbau. ``--write-baseline`` schreibt nur die lokale
  Datei, lässt andere Env-Sektionen unangetastet und weist auf den
  unversionierten Vorschlag hin.
* Präzedenz D1: ``--baseline`` > lokal > committed. Die erste Quelle mit einer
  Sektion für das gewählte Label gilt exklusiv; eine lokale Sektion überdeckt
  die gleichnamige committed Sektion vollständig (keine Union).
* Ratchet: effektives Minimum = max(VERIFY_MIN_TESTS, min_tests der
  committed Baseline, min_tests der lokalen Baseline); Senkungen werden
  abgelehnt.

Signaturen werden nicht hartcodiert: Der Test erzeugt sie über den
dokumentierten ``--write-baseline``-Weg und verwendet sie danach als
committed Baseline. So bleibt der Test unabhängig von der Hash-Formel.

Alle Läufe verwenden temporäre Fixture-Projekte mit eigenem HOME/VIBE; es
werden keine echten Modell- oder MCP-Aufrufe und keine produktiven Pfade
verwendet.

Run:

    python3 -m unittest tests.unit.test_ap7_korbat_baseline -v
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ap7_verify_support as support  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
