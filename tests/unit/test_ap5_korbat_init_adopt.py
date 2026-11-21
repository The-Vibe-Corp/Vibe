"""AP5-Korbat C1–C5: Test-Agent-Meldung bei ``init`` und ``adopt``.

Die Fälle leiten sich aus dem Arbeitspaket AP5-Korbat (C1–C5) und SPEC.md ab,
nicht aus einem Implementierungsdiff. Der verbindliche Vertrag lautet:

* ``cmd_init`` und ``_adopt_checked_out_project`` laufen ohne ``NameError``
  durch.
* Die Meldung „Unabhängiger Test-Agent ergänzt …“ (init, stdout) und eine
  Notiz in der adopt-Ergebnisliste erscheinen genau dann, wenn die Vorlage
  ``.opencode/agents/test-agent.md`` neu in das Projekt kopiert wurde (Pfad
  relativ in der ``created``-Liste von ``copy_tree``).
* Ohne solche Vorlagendatei bleiben beide still (kein falscher Erfolg).
* Eine bereits vorhandene ``.opencode/agents/test-agent.md`` wird nie
  überschrieben.
* Es wird kein Test-Agent hardcoded angelegt und kein ``TESTER=`` geschrieben
  (Commit 35233ff entfernte das bewusst).

Die Tests bauen eigene Vorlagen in temporären Verzeichnissen (Muster
``tests/unit/test_project_management.py``). Sie verwenden keine produktiven
Pfade, keine Modellaufrufe und keine Netzverbindungen.

Run:

    python3 -m unittest tests.unit.test_ap5_korbat_init_adopt -v
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"

TEST_AGENT_PATH = ".opencode/agents/test-agent.md"


def load_cli(vibe_root, home):
    """Lädt ``bin/vibe`` als Modul mit isoliertem VIBE und HOME."""
    old = {key: os.environ.get(key) for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_ap5_init_adopt_under_test", str(CLI)
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


def write_template(templates, typ, files):
    for relative, content in files.items():
        target = templates / typ / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


class InitAdoptFixture(unittest.TestCase):
    """Eigene Vorlagen und ein vorbereitetes Projekt im Temp-Verzeichnis."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.workspace = self.base / "ws"
        self.workspace.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.templates = self.base / "templates"
        self.cli = load_cli(self.workspace, self.home)
        write_template(
            self.templates,
            "common",
            {
                "FEEDBACK.md": "# FEEDBACK aus der Vorlage\n",
                "TICKETS.md": "# TICKETS\n",
            },
        )
        write_template(
            self.templates,
            "generic",
            {
                "AGENTS.md": "# AGENTS fuer {{NAME}}\n\n"
                + self.cli.GENERAL_RULES
                + "\n",
                ".vibe/project.env": "TYPE=generic\n",
            },
        )
        self.cli.TPL = str(self.templates)

    def add_test_agent_template(self, content=None):
        """Legt die optionale Test-Agent-Vorlage in ``templates/common`` an."""
        write_template(
            self.templates,
            "common",
            {
                TEST_AGENT_PATH: content
                or (
                    "---\n"
                    "description: Unabhaengiger Test-Agent {{NAME}}\n"
                    "mode: subagent\n"
                    "---\n"
                    "\n# Test-Agent\n"
                )
            },
        )

    def make_project(self, name="proj", env_text="TYPE=generic\n"):
        project = self.workspace / name
        (project / ".vibe").mkdir(parents=True)
        (project / ".vibe" / "project.env").write_text(env_text, encoding="utf-8")
        self.cli._pm.clear()
        return project

    def init_project(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.cmd_init("proj")
        return out.getvalue()

    def adopt_project(self, project, name="proj"):
        return self.cli._adopt_checked_out_project(project, name)


class InitTestAgentMessageTest(InitAdoptFixture):
    """C1/C3/C5: ``vibe init`` läuft und meldet nur einen neu angelegten Agenten."""

    def test_init_reports_a_newly_created_test_agent(self):
        """Vorbedingung: ``templates/common`` enthält
        ``.opencode/agents/test-agent.md``; Projekt ``proj`` ist vorhanden.
        Aktion: ``cmd_init("proj")`` ausführen (Ausgabe eingesammelt).
        Erwartung: kein ``NameError``; die Datei existiert im Projekt; die
        Ausgabe enthält „Unabhängiger Test-Agent ergänzt“.
        Fehlerfall: Absturz oder fehlende Erfolgsmeldung trotz Neuanlage.
        """
        self.add_test_agent_template()
        project = self.make_project()

        output = self.init_project()

        self.assertTrue((project / TEST_AGENT_PATH).is_file(),
                        "Die Vorlage wurde nicht in das Projekt kopiert")
        self.assertIn("Unabhängiger Test-Agent ergänzt", output, output)

    def test_init_stays_silent_without_a_test_agent_template(self):
        """Vorbedingung: ``templates/common`` enthält keine Test-Agent-Vorlage.
        Aktion: ``cmd_init("proj")`` ausführen.
        Erwartung: kein ``NameError``; keine Test-Agent-Meldung und keine
        Test-Agent-Datei (still, kein falscher Erfolg).
        Fehlerfall: Meldung ohne Vorlage oder erfundene Datei.
        """
        project = self.make_project()

        output = self.init_project()

        self.assertNotIn("Test-Agent", output, output)
        self.assertFalse((project / TEST_AGENT_PATH).exists(),
                         "Ohne Vorlage darf kein Test-Agent entstehen")

    def test_init_does_not_overwrite_an_existing_test_agent(self):
        """Vorbedingung: Projekt enthält bereits einen eigenen Test-Agenten;
        die Vorlage enthält anderen Inhalt.
        Aktion: ``cmd_init("proj")`` ausführen.
        Erwartung: Der bestehende Inhalt bleibt unverändert; da nichts neu
        angelegt wurde, erscheint keine Test-Agent-Meldung.
        Fehlerfall: Überschreiben des Bestands oder falsche Erfolgsmeldung.
        """
        self.add_test_agent_template()
        project = self.make_project()
        agent = project / TEST_AGENT_PATH
        agent.parent.mkdir(parents=True)
        agent.write_text("# eigener Test-Agent\n", encoding="utf-8")

        output = self.init_project()

        self.assertEqual(agent.read_text(encoding="utf-8"),
                         "# eigener Test-Agent\n")
        self.assertNotIn("Unabhängiger Test-Agent ergänzt", output, output)

    def test_init_does_not_write_a_tester_assignment(self):
        """Vorbedingung: Vorlage mit Test-Agent; ``.vibe/project.env`` enthält
        nur ``TYPE=generic``.
        Aktion: ``cmd_init("proj")`` ausführen.
        Erwartung: Die Datei enthält weiterhin keine ``TESTER=``-Zeile
        (Commit 35233ff entfernte das hardcoded Tester-Verhalten).
        Fehlerfall: ``TESTER=test-agent`` wird wieder eingetragen.
        """
        self.add_test_agent_template()
        project = self.make_project()

        self.init_project()

        env_text = (project / ".vibe" / "project.env").read_text(encoding="utf-8")
        self.assertNotIn("TESTER=", env_text, env_text)


class AdoptTestAgentNoteTest(InitAdoptFixture):
    """C2/C4/C5: Übernahme läuft und notiert nur einen neu angelegten Agenten."""

    def test_adopt_notes_a_newly_created_test_agent(self):
        """Vorbedingung: Vorhandenes Projekt ohne Test-Agent; die Vorlage
        ``templates/common/.opencode/agents/test-agent.md`` existiert.
        Aktion: ``_adopt_checked_out_project(project, "proj")`` ausführen.
        Erwartung: kein ``NameError``; Datei neu angelegt; mindestens eine
        Notiz nennt den Test-Agenten.
        Fehlerfall: Absturz oder fehlende Notiz trotz Neuanlage.
        """
        self.add_test_agent_template()
        project = self.make_project()

        notes = self.adopt_project(project)

        self.assertTrue((project / TEST_AGENT_PATH).is_file())
        self.assertTrue(any("Test-Agent" in note for note in notes), notes)

    def test_adopt_stays_silent_without_a_test_agent_template(self):
        """Vorbedingung: Projekt ohne Test-Agent; keine Vorlagendatei.
        Aktion: ``_adopt_checked_out_project`` ausführen.
        Erwartung: kein ``NameError``; keine Notiz nennt einen Test-Agenten und
        es entsteht keine Datei.
        Fehlerfall: Notiz ohne Anlage.
        """
        project = self.make_project()

        notes = self.adopt_project(project)

        self.assertFalse((project / TEST_AGENT_PATH).exists())
        self.assertFalse(any("Test-Agent" in note for note in notes), notes)

    def test_adopt_preserves_an_existing_test_agent_and_stays_silent(self):
        """Vorbedingung: Projekt enthält bereits einen eigenen Test-Agenten.
        Aktion: ``_adopt_checked_out_project`` ausführen.
        Erwartung: Inhalt unverändert; keine Notiz nennt den Test-Agenten, weil
        nichts neu kopiert wurde (Bestandsschutz von ``copy_tree``).
        Fehlerfall: Überschreiben oder falsche Notiz.
        """
        self.add_test_agent_template()
        project = self.make_project()
        agent = project / TEST_AGENT_PATH
        agent.parent.mkdir(parents=True)
        agent.write_text("# eigener Test-Agent\n", encoding="utf-8")

        notes = self.adopt_project(project)

        self.assertEqual(agent.read_text(encoding="utf-8"),
                         "# eigener Test-Agent\n")
        self.assertFalse(any("Test-Agent" in note for note in notes), notes)

    def test_adopt_does_not_write_a_tester_assignment(self):
        """Vorbedingung: Vorlage mit Test-Agent; Projekt-env ohne ``TESTER``.
        Aktion: ``_adopt_checked_out_project`` ausführen.
        Erwartung: ``.vibe/project.env`` enthält weiterhin keine
        ``TESTER=``-Zeile.
        Fehlerfall: Wieder eingetragenes hardcoded Tester-Verhalten.
        """
        self.add_test_agent_template()
        project = self.make_project()

        self.adopt_project(project)

        env_text = (project / ".vibe" / "project.env").read_text(encoding="utf-8")
        self.assertNotIn("TESTER=", env_text, env_text)


if __name__ == "__main__":
    unittest.main()
