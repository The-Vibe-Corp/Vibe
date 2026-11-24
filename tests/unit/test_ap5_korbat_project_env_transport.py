"""AP5-Korbat: read-only Einweg-Transport von ``.vibe/project.env``.

Die Fälle leiten sich aus dem Arbeitspaket AP5-Korbat (Abschnitt
„project.env-Transport“) und SPEC.md ab. Geprüft wird über den echten
CLI-Einstieg ``python3 bin/vibe_packages.py copy-notes`` in einem temporären
Projekt mit echter ``git worktree``-Arbeitskopie:

* Existiert ``<projekt>/.vibe/project.env``, wird sie nach
  ``<worktree>/.vibe/project.env`` kopiert (gleicher Inhalt), best effort
  schreibgeschützt (0444), und ``.vibe/project.env`` wird idempotent in die
  Git-Exclude des Worktrees eingetragen.
* Fehlt die Datei, entsteht im Worktree weder ``.vibe/`` noch ein
  Exclude-Eintrag.
* Nur exakt ``project.env`` wird transportiert; ``_secrets.env`` und andere
  ``.vibe/``-Dateien bleiben zurück.
* ``sync-ticket`` (GH-48; früher ``sync-proof``) schreibt nie in die
  Projekt-``project.env`` zurück; die Worktree-Kopie bleibt liegen. Das
  abgeschlossene Paket liegt dabei als ``TICKET-T1.json`` in der Arbeitskopie,
  der Abschluss wird in den Ticketspeicher übernommen.
* Die CLI-Ausgabe enthält eine eigene OK-Zeile mit „project.env“.

GH-46 entfernt den Transport der lokalen Baseline: ``.vibe/verify-baseline``
wird nicht mehr in die Arbeitskopie kopiert und nicht ausgeschlossen. Ein
Projekt mit beiden Dateien transportiert nur ``.vibe/project.env``;
Agenten arbeiten in der Arbeitskopie mit der committeten
``tests/verify-baseline.json`` aus dem Branch.

Es werden keine Modellaufrufe, Netzverbindungen oder produktiven Pfade
verwendet.

Run:

    python3 -m unittest tests.unit.test_ap5_korbat_project_env_transport -v
"""
import importlib.machinery
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "bin" / "vibe_packages.py"

ENV_TEXT = (
    "TYPE=generic\n"
    'VERIFY_QUICK="true"\n'
    'VERIFY_PACKAGE="true"\n'
)

BASELINE_TEXT = (
    "{\n"
    '  "version": 1,\n'
    '  "min_tests": 1,\n'
    '  "envs": {}\n'
    "}\n"
)


def load_module():
    loader = importlib.machinery.SourceFileLoader(
        "vibe_packages_ap5_transport_under_test", str(MODULE)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class ProjectEnvTransportTest(unittest.TestCase):
    """Echtes Projekt-Repository und echte Arbeitskopie."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        support.init_repo(self.project)
        (self.project / "README.md").write_text("basis\n", encoding="utf-8")
        support.commit_all(self.project)
        self.base = support.git(
            self.project, "rev-parse", "HEAD"
        ).stdout.strip()
        (self.project / ".vibe").mkdir()
        self.project_env = self.project / ".vibe" / "project.env"
        self.project_env.write_text(ENV_TEXT, encoding="utf-8")
        # GH-48: Ticket im Projektspeicher statt im Markdown-Ledger.
        support.write_ticket_store(self.project, [
            support.ticket_record("T1", "Paket", type="task")])
        self.worktree = self.add_worktree()
        self.assertFalse((self.worktree / ".vibe").exists(),
                         "Vorbedingung: Arbeitskopie kennt .vibe noch nicht")

    def add_worktree(self, name="wt"):
        worktree = self.root / name
        result = support.git(
            self.project, "worktree", "add", "-q", "-b", "branch-" + name,
            str(worktree), "HEAD",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.addCleanup(self.remove_worktree, worktree, name)
        return worktree

    def remove_worktree(self, worktree, name):
        support.git(self.project, "worktree", "remove", "--force", str(worktree))

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(MODULE), *args],
            cwd=str(self.root),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def copy_notes(self):
        return self.run_cli(
            "copy-notes", "--project", str(self.project),
            "--worktree", str(self.worktree),
        )

    def exclude_path(self):
        result = support.git(
            self.worktree, "rev-parse", "--git-path", "info/exclude"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        path = Path(result.stdout.strip())
        return path if path.is_absolute() else self.worktree / path

    def exclude_lines(self):
        path = self.exclude_path()
        if not path.is_file():
            return []
        return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]

    def chmod_effective(self):
        """True, wenn Schreibschutz auf diesem Dateisystem wirksam ist."""
        probe = self.root / ".chmod-probe"
        probe.write_text("x\n", encoding="utf-8")
        try:
            os.chmod(probe, 0o444)
            return not (stat.S_IMODE(probe.stat().st_mode) & 0o222)
        finally:
            probe.unlink()

    def test_project_env_is_copied_read_only_and_excluded(self):
        """Vorbedingung: Projekt mit ``.vibe/project.env``; Arbeitskopie ohne
        ``.vibe``.
        Aktion: ``copy-notes --project … --worktree …`` ausführen.
        Erwartung: Exit 0; ``.vibe/project.env`` existiert im Worktree mit
        identischem Inhalt; Schreibbits sind nicht gesetzt (0444 best effort);
        die Git-Exclude enthält genau einmal ``.vibe/project.env``; die
        Ausgabe hat eine eigene OK-Zeile mit „project.env“.
        Fehlerfall: fehlende/abweichende Kopie, beschreibbare Datei, fehlender
        oder doppelter Exclude-Eintrag, fehlende OK-Zeile.
        """
        exclude = self.exclude_path()
        exclude.unlink(missing_ok=True)
        self.assertFalse(exclude.exists(), "Vorbedingung: Exclude fehlt")

        result = self.copy_notes()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        copied = self.worktree / ".vibe" / "project.env"
        self.assertTrue(copied.is_file(), "project.env wurde nicht kopiert")
        self.assertEqual(copied.read_text(encoding="utf-8"), ENV_TEXT)
        if self.chmod_effective():
            mode = stat.S_IMODE(copied.stat().st_mode)
            self.assertEqual(0, mode & 0o222,
                             "Die Kopie ist beschreibbar (Modus %o)" % mode)
        self.assertTrue(exclude.is_file(), "Exclude-Datei wurde nicht angelegt")
        lines = self.exclude_lines()
        self.assertEqual(lines.count(".vibe/project.env"), 1, lines)
        self.assertTrue(
            any("OK:" in line and "project.env" in line
                for line in result.stdout.splitlines()),
            "Eigene OK-Zeile für den Transport fehlt:\n" + result.stdout,
        )

    def test_missing_project_env_creates_no_vibe_folder_and_no_exclude(self):
        """Vorbedingung: Projekt ohne ``.vibe/project.env`` (aber mit
        ``.vibe/_secrets.env``); Arbeitskopie ohne ``.vibe``.
        Aktion: ``copy-notes`` ausführen.
        Erwartung: Exit 0; im Worktree entsteht kein ``.vibe/``; die
        Git-Exclude enthält keinen ``.vibe/project.env``-Eintrag; keine
        Transport-OK-Zeile.
        Fehlerfall: leerer Ordner, Exclude-Eintrag oder falsche Erfolgsmeldung.
        """
        (self.project / ".vibe" / "_secrets.env").write_text(
            "GEHEIM=1\n", encoding="utf-8"
        )
        self.project_env.unlink()

        result = self.copy_notes()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.worktree / ".vibe").exists(),
                         "Ohne project.env darf kein .vibe/ entstehen")
        self.assertNotIn(".vibe/project.env", self.exclude_lines())
        self.assertFalse(
            any("OK:" in line and "project.env" in line
                for line in result.stdout.splitlines()),
            result.stdout,
        )

    def test_only_project_env_is_transported_never_secrets(self):
        """Vorbedingung: Projekt-``.vibe`` enthält ``project.env``,
        ``_secrets.env`` und eine weitere Datei.
        Aktion: ``copy-notes`` ausführen.
        Erwartung: Im Worktree liegt ``.vibe/project.env``; ``_secrets.env``
        und die weitere Datei fehlen.
        Fehlerfall: Geheimnis oder fremde Datei wird übertragen.
        """
        (self.project / ".vibe" / "_secrets.env").write_text(
            "GEHEIM=1\n", encoding="utf-8"
        )
        (self.project / ".vibe" / "notizen.txt").write_text(
            "nicht uebertragen\n", encoding="utf-8"
        )

        result = self.copy_notes()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        target = self.worktree / ".vibe"
        self.assertTrue((target / "project.env").is_file())
        self.assertFalse((target / "_secrets.env").exists(),
                         "Geheimnisse dürfen nie transportiert werden")
        self.assertFalse((target / "notizen.txt").exists())

    def test_copy_and_exclude_are_idempotent(self):
        """Vorbedingung: ``copy-notes`` lief bereits einmal.
        Aktion: Projekt-``project.env`` ändern und ``copy-notes`` erneut
        ausführen.
        Erwartung: Die Worktree-Kopie enthält den neuen Projektstand; der
        Exclude-Eintrag bleibt genau einmal vorhanden.
        Fehlerfall: doppelter Exclude-Eintrag oder alter Inhalt.
        """
        first = self.copy_notes()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        updated = ENV_TEXT + "GEAENDERT=ja\n"
        self.project_env.write_text(updated, encoding="utf-8")

        second = self.copy_notes()

        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        copied = self.worktree / ".vibe" / "project.env"
        self.assertEqual(copied.read_text(encoding="utf-8"), updated)
        self.assertEqual(self.exclude_lines().count(".vibe/project.env"), 1,
                         self.exclude_lines())

    def test_sync_ticket_never_writes_the_project_env_back(self):
        """Vorbedingung: ``copy-notes`` hat die Datei transportiert; im
        Worktree liegt ein abgeschlossenes TICKET-T1.json, die Worktree-Kopie
        der project.env wurde lokal geändert. Der Projektstand ist autoritativ.
        Aktion: ``sync-ticket --project … --worktree … --id T1`` ausführen.
        Erwartung: Exit 0; die Projekt-``project.env`` bleibt byte-gleich; die
        Worktree-Kopie bleibt mit ihrem lokalen Inhalt liegen.
        Fehlerfall: Rückschreiben in das Projekt oder Löschen der Kopie.
        """
        first = self.copy_notes()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        local = "TYPE=generic\nLOKAL=1\n"
        copied = self.worktree / ".vibe" / "project.env"
        os.chmod(copied, 0o644)
        copied.write_text(local, encoding="utf-8")
        revision = support.git(
            self.project, "rev-parse", "--short", "HEAD"
        ).stdout.strip()
        record = support.ticket_record(
            "T1", "Paket", type="task", state="done",
            commit=revision, test="test_t1")
        (self.worktree / "TICKET-T1.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        project_before = self.project_env.read_bytes()

        result = self.run_cli(
            "sync-ticket", "--project", str(self.project),
            "--worktree", str(self.worktree), "--id", "T1",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.project_env.read_bytes(), project_before,
                         "sync-ticket darf project.env nie zurückschreiben")
        self.assertEqual(copied.read_text(encoding="utf-8"), local,
                         "Die Worktree-Kopie muss liegen bleiben")

    # ---------------------------------- GH-46: kein verify-baseline-Transport
    def write_project_baseline(self, text=BASELINE_TEXT):
        path = self.project / ".vibe" / "verify-baseline"
        path.write_text(text, encoding="utf-8")
        return path

    def test_verify_baseline_is_not_transported_and_not_excluded(self):
        """Vorbedingung: Projekt mit ``.vibe/project.env`` und
        ``.vibe/verify-baseline``; Arbeitskopie ohne ``.vibe``.
        Aktion: ``copy-notes`` ausführen.
        Erwartung: Exit 0; nur ``.vibe/project.env`` liegt in der Arbeitskopie,
        ``.vibe/verify-baseline`` fehlt dort vollständig; die Git-Exclude
        enthält ``.vibe/project.env`` genau einmal und keinen
        ``.vibe/verify-baseline``-Eintrag (die Baseline wird nicht
        transportiert, Agenten nutzen die committete Kopie aus dem Branch).
        Fehlerfall: Die lokale Baseline wird in die Arbeitskopie kopiert oder
        ausgeschlossen und überdeckt dort die committete Baseline.
        """
        exclude = self.exclude_path()
        exclude.unlink(missing_ok=True)
        self.write_project_baseline()

        result = self.copy_notes()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        target = self.worktree / ".vibe"
        self.assertTrue((target / "project.env").is_file(),
                        "project.env muss weiterhin transportiert werden")
        self.assertEqual(
            (target / "project.env").read_text(encoding="utf-8"), ENV_TEXT
        )
        self.assertFalse(
            (target / "verify-baseline").exists(),
            "Die lokale Baseline darf die committete Baseline nicht überdecken",
        )
        lines = self.exclude_lines()
        self.assertEqual(lines.count(".vibe/project.env"), 1, lines)
        self.assertNotIn(".vibe/verify-baseline", lines,
                         "Kein Exclude-Eintrag für die nicht transportierte "
                         "Baseline: %r" % (lines,))

    def test_repeated_copy_keeps_the_baseline_out_of_the_worktree(self):
        """Vorbedingung: ``copy-notes`` lief bereits einmal; Projekt und
        Baseline existieren weiter, die Projekt-Baseline wurde geändert.
        Aktion: ``copy-notes`` erneut ausführen.
        Erwartung: Exit 0; die Arbeitskopie enthält weiterhin keine
        ``.vibe/verify-baseline``; der Exclude-Eintrag für ``project.env``
        bleibt genau einmal vorhanden und es entsteht kein Baseline-Eintrag.
        Fehlerfall: Ein zweiter Lauf schleust die Baseline doch ein oder
        dupliziert Exclude-Einträge.
        """
        self.write_project_baseline()
        first = self.copy_notes()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        updated = (
            "{\n"
            '  "version": 1,\n'
            '  "min_tests": 2,\n'
            '  "envs": {}\n'
            "}\n"
        )
        self.write_project_baseline(updated)

        second = self.copy_notes()

        self.assertEqual(second.returncode, 0,
                         second.stdout + second.stderr)
        self.assertFalse(
            (self.worktree / ".vibe" / "verify-baseline").exists(),
            "Ein zweiter Lauf darf die Baseline nicht transportieren",
        )
        lines = self.exclude_lines()
        self.assertEqual(lines.count(".vibe/project.env"), 1, lines)
        self.assertNotIn(".vibe/verify-baseline", lines, lines)


if __name__ == "__main__":
    unittest.main()
