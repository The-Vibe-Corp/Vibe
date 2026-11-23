"""AP7-Korbat — T-V21: Hash-/Diff-Wächter nach dem Agentenlauf (GH-46).

Die Fälle leiten sich aus TICKETS.md (AP7-Korbat), dem AP12-Audit (T-V21),
dem AP7-Design-Brief und der GH-46-Entscheidung ab, nicht aus einem
Implementierungsdiff:

* Der Läufer erfasst nach dem Transport (Paketstart) den sha256 der
  transportierten Datei ``.vibe/project.env``. Nach der Rückkehr des Agenten
  und vor der Paketprüfung hasht er erneut.
* Weicht die Datei ab oder fehlt sie, blockiert das Paket mit einer Meldung,
  die die veränderte Datei nennt. Es gibt keine Reparaturrunde: Tampering ist
  kein gewöhnlicher Defekt, sondern ein Abbruchgrund. Das Paket wird nicht
  gemergt, das Ticket bleibt offen.
* Unveränderte Dateien blockieren nicht (kein Fehlalarm). Maßgeblich ist der
  Inhalt (sha256), nicht die Änderungszeit: Ein identisches Neuschreiben
  bleibt unverändert.
* Das Löschen einer beim Start vorhandenen ``.vibe/project.env`` ist ebenso
  eine Abweichung vom erfassten Startzustand und blockiert mit Nennung der
  Datei — sonst könnte ein Agent die autoritative Projektkonfiguration
  einfach entfernen.
* ``.vibe/verify-baseline`` wird seit GH-46 nicht mehr transportiert und
  deshalb auch nicht bewacht: Eine beim Paketstart vorhandene lokale Baseline
  darf der Agent im Lauf verändern oder löschen, ohne dass das Paket
  blockiert. Agenten arbeiten in der Arbeitskopie ausschließlich mit der
  committeten ``tests/verify-baseline.json`` aus dem Branch; die lokale
  Bootstrap-Datei ist nicht Teil des Pakets.

Der echte ``bin/vibe-run.sh`` läuft in einer Fake-Toolchain (Muster
``test_ap9_runner_wiring.py``): nachgebildeter Agent, temporäre Installation,
eigenes HOME/VIBE, keine Modellaufrufe, keine produktiven Pfade, begrenzte
Timeouts. Der Agent wird über ``FAKE_TAMPER`` gesteuert
(``runner_support.FAKE_OPENCODE``) und schließt das Paket weiterhin
vollständig ab — ein Block stammt damit eindeutig vom Wächter und nicht von
einer fehlenden Abschlussschranke.

Run:

    python3 -m unittest tests.unit.test_ap7_korbat_runner -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support  # noqa: E402
from tests.unit.test_ap9_runner_wiring import AP9WiringFixture, git  # noqa: E402

PROJECT_ENV = """TYPE=generic
AGENT=test-agent
TESTER=test-agent
REVIEWER=code-reviewer
VERIFY_PACKAGE="true"
VERIFY_FULL="true"
MAX_RETRIES=3
"""

FEEDBACK_ONE = "- [ ] F1 Erstes Paket\n  Beschreibung: Test\n"

BASELINE_TEXT = (
    "{\n"
    '  "version": 1,\n'
    '  "min_tests": 1,\n'
    '  "envs": {}\n'
    "}\n"
)


class HashGuardFixture(AP9WiringFixture):
    """Projekt mit transportierter project.env und optionaler (nicht
    transportierter) lokaler Baseline.

    ``.vibe/`` ist wie im echten Projekt git-ignoriert; ``project.env`` liegt
    damit unversioniert im Projekt und wird vom Transport in die Arbeitskopie
    kopiert. ``verify-baseline`` entsteht ebenfalls im Projektordner, wird
    seit GH-46 aber nicht mehr transportiert. Die Dateien entstehen erst nach
    dem Ausgangscommit, damit keine versionierte Kopie den Transport überdeckt.
    """

    def make_guard_project(self, baseline=False, name="proj"):
        project = self.root / name
        support.init_repo(project)
        (project / ".gitignore").write_text("/.vibe/\n", encoding="utf-8")
        (project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n" + FEEDBACK_ONE, encoding="utf-8"
        )
        (project / "TICKETS.md").write_text("# TICKETS\n\n", encoding="utf-8")
        support.commit_all(project, "Ausgangsstand")
        (project / ".vibe").mkdir()
        (project / ".vibe" / "project.env").write_text(
            PROJECT_ENV, encoding="utf-8"
        )
        if baseline:
            (project / ".vibe" / "verify-baseline").write_text(
                BASELINE_TEXT, encoding="utf-8"
            )
        return project

    # ---------------------------------------------------------- Beobachtung
    def blocked_lines(self, log):
        return [line for line in log.splitlines()
                if line.startswith("BLOCKIERT")]

    def report(self, project):
        path = self.runtime / (project.name + ".report.txt")
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def agent_calls(self):
        """Nicht-Preflight-Aufrufe des nachgebildeten Agenten."""
        path = self.root / "calls.jsonl"
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [line for line in lines
                if line and not line.startswith("preflight")]

    def assert_blocked_for(self, log, changed_file):
        blocked = self.blocked_lines(log)
        self.assertTrue(blocked, "Der Lauf blockiert nicht:\n" + log)
        self.assertTrue(
            any(changed_file in line for line in blocked),
            "Keine BLOCKIERT-Zeile nennt die veränderte Datei %r:\n%s"
            % (changed_file, log),
        )
        self.assertNotIn("FERTIG", log,
                         "Ein blockiertes Paket darf nicht FERTIG melden:\n"
                         + log)
        self.assertNotIn("REPARATUR", log,
                         "Tampering darf keine Reparaturrunde auslösen:\n"
                         + log)
        self.assertEqual(
            1, len(self.agent_calls()),
            "Der Agent wurde erneut aufgerufen (Reparaturrunde): %r"
            % (self.agent_calls(),),
        )

    def assert_not_blocked(self, result, project):
        """Das Paket läuft trotz der Manipulation vollständig durch."""
        log = self.log(project)
        self.assertEqual(0, result.returncode,
                         result.stdout + result.stderr + "\n" + log)
        self.assertIn("FERTIG", log)
        self.assertEqual([], self.blocked_lines(log), log)
        self.assertIn("Geschlossen: F1", self.report(project))


class TamperedProjectEnvTest(HashGuardFixture):
    """T-V21: veränderte ``.vibe/project.env`` blockiert das Paket."""

    def test_tampered_project_env_blocks_and_names_the_file(self):
        """Vorbedingung: Projekt mit transportierter ``.vibe/project.env``;
        der Agent schließt das Paket ab, verändert dabei aber die
        transportierte Projektdatei (``FAKE_TAMPER=append:project.env``).
        Aktion: Läufer einmal ausführen.
        Erwartung: Exit ungleich 0; eine BLOCKIERT-Zeile nennt
        ``.vibe/project.env``; keine Reparaturrunde (genau ein
        Agentenaufruf), kein FERTIG, kein lokaler Merge, Ticket bleibt offen.
        Fehlerfall: Die veränderte Konfiguration wird stillschweigend
        weiterbenutzt (Manipulation der autoritativen Projektwerte).
        """
        project = self.make_guard_project()

        result = self.run_runner(
            project, FAKE_TAMPER="append:project.env"
        )

        self.assertNotEqual(0, result.returncode,
                            result.stdout + result.stderr)
        log = self.log(project)
        self.assert_blocked_for(log, ".vibe/project.env")
        self.assertNotEqual(
            0, git(project, "cat-file", "-e", "HEAD:impl-F1.txt").returncode,
            "Ein blockiertes Paket darf nicht lokal gemergt sein:\n" + log,
        )
        self.assertIn("- [ ] F1",
                      (project / "FEEDBACK.md").read_text(encoding="utf-8"))

    def test_identical_rewrite_is_not_a_block(self):
        """Vorbedingung: Der Agent schreibt ``.vibe/project.env`` mit
        identischem Inhalt neu (``FAKE_TAMPER=rewrite:project.env``).
        Aktion: Läufer einmal ausführen.
        Erwartung: Exit 0 und FERTIG — der Wächter vergleicht den Inhalt
        (sha256), nicht die Änderungszeit.
        Fehlerfall: Ein reines Neuschreiben blockiert ein gesundes Paket
        (Fehlalarm, der jede Agentenrunde blockieren würde).
        """
        project = self.make_guard_project()

        result = self.run_runner(
            project, FAKE_TAMPER="rewrite:project.env"
        )

        log = self.log(project)
        self.assertEqual(0, result.returncode,
                         result.stdout + result.stderr + "\n" + log)
        self.assertIn("FERTIG", log)
        self.assertEqual([], self.blocked_lines(log), log)


class UntouchedFilesTest(HashGuardFixture):
    """T-V21: unveränderte Dateien blockieren nicht."""

    def test_untouched_project_and_baseline_do_not_block(self):
        """Vorbedingung: Projekt mit ``.vibe/project.env`` und einer lokalen
        ``.vibe/verify-baseline``; der Agent verändert keine der Dateien.
        Aktion: Läufer einmal ausführen.
        Erwartung: Exit 0, ``Geschlossen: F1`` im Bericht, kein
        BLOCKIERT-Vermerk — der Wächter greift nur bei Abweichung einer
        transportierten Datei.
        Fehlerfall: Der Wächter blockiert jedes Paket.
        """
        project = self.make_guard_project(baseline=True)

        result = self.run_runner(project)

        log = self.log(project)
        self.assertEqual(0, result.returncode,
                         result.stdout + result.stderr + "\n" + log)
        self.assertEqual([], self.blocked_lines(log), log)
        report = self.report(project)
        self.assertIn("Geschlossen: F1", report)


class DeletedTransportedFileTest(HashGuardFixture):
    """T-V21: Löschen einer beim Start vorhandenen transportierten Datei.

    Der Wächter erfasst den Inhalt beim Paketstart. Fehlt die Datei nach dem
    Agentenlauf, ist das nicht „unverändert", sondern eine Manipulation: Der
    Agent könnte damit unliebsame Projektwerte beseitigen. Die Prüfung darf
    sich deshalb nicht auf ``[ -f datei ]`` verlassen, sondern muss bereits
    das Fehlen als Abweichung vom erfassten Startzustand werten. Das gilt
    ausschließlich für die transportierte ``.vibe/project.env``.
    """

    def test_deleted_project_env_blocks_and_names_the_file(self):
        """Vorbedingung: Projekt mit transportierter ``.vibe/project.env``;
        der Agent löscht die Datei im Lauf
        (``FAKE_TAMPER=delete:project.env``).
        Aktion: Läufer einmal ausführen.
        Erwartung: Exit ungleich 0; eine BLOCKIERT-Zeile nennt
        ``.vibe/project.env``; keine Reparaturrunde, kein Merge, Ticket
        offen.
        Fehlerfall: Die autoritative Projektkonfiguration kann unbemerkt aus
        der Arbeitskopie verschwinden; die Paketprüfung liefe dann ohne die
        vom Projekt vorgegebenen Befehle.
        """
        project = self.make_guard_project()

        result = self.run_runner(
            project, FAKE_TAMPER="delete:project.env"
        )

        self.assertNotEqual(0, result.returncode,
                            result.stdout + result.stderr)
        log = self.log(project)
        self.assert_blocked_for(log, ".vibe/project.env")
        self.assertNotEqual(
            0, git(project, "cat-file", "-e", "HEAD:impl-F1.txt").returncode,
            "Ein blockiertes Paket darf nicht lokal gemergt sein:\n" + log,
        )


class UnwatchedVerifyBaselineTest(HashGuardFixture):
    """GH-46: ``.vibe/verify-baseline`` wird nicht transportiert/bewacht.

    Eine lokale Bootstrap-Baseline ist kein Paketinhalt mehr. Ob der Agent
    eine solche Datei anlegt, verändert oder löscht, darf das Paket nicht
    blockieren; maßgeblich ist allein die committete
    ``tests/verify-baseline.json`` im Branch.
    """

    def test_changed_verify_baseline_present_at_start_does_not_block(self):
        """Vorbedingung: Projekt mit ``.vibe/verify-baseline`` (beim
        Paketstart vorhanden); der Agent verändert sie im Lauf
        (``FAKE_TAMPER=append:verify-baseline``).
        Aktion: Läufer einmal ausführen.
        Erwartung: Exit 0, FERTIG, kein BLOCKIERT — für die nicht
        transportierte Baseline gibt es keinen Wächter.
        Fehlerfall: Der Läufer blockiert wegen einer Datei, die gar nicht Teil
        des Pakets ist, und verhindert so jedes Paket in einem Projekt mit
        lokaler Baseline.
        """
        project = self.make_guard_project(baseline=True)

        result = self.run_runner(
            project, FAKE_TAMPER="append:verify-baseline"
        )

        self.assert_not_blocked(result, project)

    def test_deleted_verify_baseline_present_at_start_does_not_block(self):
        """Vorbedingung: Projekt mit ``.vibe/verify-baseline`` (beim
        Paketstart vorhanden); der Agent löscht sie im Lauf
        (``FAKE_TAMPER=delete:verify-baseline``).
        Aktion: Läufer einmal ausführen.
        Erwartung: Exit 0, FERTIG, kein BLOCKIERT — das Löschen einer nicht
        transportierten Datei ist keine Manipulation am Paket.
        Fehlerfall: Ein veralteter Baseline-Wächter blockiert das Paket,
        obwohl die Baseline nur lokal im Projektordner lag.
        """
        project = self.make_guard_project(baseline=True)

        result = self.run_runner(
            project, FAKE_TAMPER="delete:verify-baseline"
        )

        self.assert_not_blocked(result, project)

    def test_baseline_created_by_the_agent_does_not_block(self):
        """Vorbedingung: Projekt ohne ``.vibe/verify-baseline``; der Agent
        legt die Datei im Lauf selbst an (``FAKE_TAMPER=create:…``).
        Aktion: Läufer einmal ausführen.
        Erwartung: Exit 0, FERTIG — eine im Lauf erzeugte Baseline ist kein
        Abweichungsgrund.
        Fehlerfall: Der Wächter verlangt oder verbietet Dateien, die nicht
        transportiert wurden, und blockiert gesunde Pakete.
        """
        project = self.make_guard_project(baseline=False)

        result = self.run_runner(
            project, FAKE_TAMPER="create:verify-baseline"
        )

        self.assert_not_blocked(result, project)

    def test_deleting_an_absent_baseline_does_not_block(self):
        """Vorbedingung: Projekt ohne ``.vibe/verify-baseline``; der Agent
        „löscht" die nie transportierte Datei
        (``FAKE_TAMPER=delete:verify-baseline``, folgenlos wie ``rm -f``).
        Aktion: Läufer einmal ausführen.
        Erwartung: Exit 0, FERTIG, kein BLOCKIERT — es gibt keinen
        Baseline-Wächter mehr.
        Fehlerfall: Ein Lauf ohne transportierte Baseline blockiert, weil der
        Wächter eine Startdatei unterstellt, die es nie gab.
        """
        project = self.make_guard_project(baseline=False)

        result = self.run_runner(
            project, FAKE_TAMPER="delete:verify-baseline"
        )

        self.assert_not_blocked(result, project)


if __name__ == "__main__":
    unittest.main()
