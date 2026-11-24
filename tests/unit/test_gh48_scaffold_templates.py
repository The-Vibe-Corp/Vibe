"""GH-48: Vertragstests für Gerüst, .gitignore, Vorlagen und Guide.

Quelle der Ableitung: Arbeitspaket GH-48, ``SPEC.md`` und der verbindliche
Implementierungsvertrag GH-48 (§8 Gerüst, Vorlagen, Guide, .gitignore).
Geprüft wird:

* ``cmd_new`` erzeugt ``.gitignore`` mit ``.vibe/`` **vor** dem initialen
  Commit, daher enthält der Initial-Commit keine ``.vibe``-Datei; der
  Abschlusshinweis nennt das Dashboard statt TICKETS.md.
* ``ensure_gitignore`` ist idempotent und liefert created/appended/False;
  ``cmd_init`` ergänzt bestehende Dateien ohne Überschreiben.
* ``templates/common`` enthält kein TICKETS.md/FEEDBACK.md mehr.
* ``GENERAL_RULES`` in ``bin/vibe`` ist mit dem verwalteten Block aller fünf
  Vorlagen-AGENTS.md identisch und beschreibt den feldbasierten
  Ticketabschluss (Abschnitt „Ticketabschluss", kein „kein Häkchen").
* ``vibe_guide`` führt TICKETS.md/FEEDBACK.md nicht mehr als Projektdateien.

Ausschließlich temporäre ``VIBE``-/``HOME``-Pfade; Git-Kommandos laufen in
Wegwerf-Repositories, keine Netz- oder Modellaufrufe.

Run:

    python3 -m unittest tests.unit.test_gh48_scaffold_templates -v
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.unit import env_support

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
BIN = REPO / "bin"
TEMPLATES = REPO / "templates"
TEMPLATE_TYPES = ("generic", "android", "web", "docker", "rebuild")
MARK = "<!-- vibe:general-rules -->"
END = "<!-- /vibe:general-rules -->"
_CACHE = {}


def load_script(path, name):
    if name not in _CACHE:
        loader = importlib.machinery.SourceFileLoader(name, str(path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[loader.name] = module
        loader.exec_module(module)
        _CACHE[name] = module
    return _CACHE[name]


def cli_module(root):
    """Lädt ``bin/vibe`` mit temporären Pfaden (für GENERAL_RULES)."""
    with env_support.isolated_process_environment(
        VIBE=str(root),
        VIBE_NO_CONTAINER="1",
        HOME=str(Path(root) / "home"),
        VIBE_RUNTIME=str(Path(root) / "_logs"),
        VIBE_STATE=str(Path(root) / "_toolchain"),
        VIBE_CONFIG_FILE=str(Path(root) / "home" / ".config" / "vibe"
                             / "config.json"),
    ):
        return load_script(CLI, "vibe_gh48_scaffold_under_test")


class ScaffoldCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "home").mkdir()
        self.cli = cli_module(self.root)

    def env(self):
        return env_support.isolated_environ(
            VIBE=str(self.root),
            VIBE_NO_CONTAINER="1",
            HOME=str(self.root / "home"),
            VIBE_RUNTIME=str(self.root / "_logs"),
            VIBE_STATE=str(self.root / "_toolchain"),
            VIBE_INSTALL=str(REPO),
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_TERMINAL_PROMPT="0",
        )

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=str(self.root), env=self.env(), stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=180)


class GitignoreTest(ScaffoldCase):
    """``ensure_gitignore`` und die Reihenfolge in ``cmd_new``."""

    def project(self, name="proj"):
        project = self.root / name
        project.mkdir()
        return project

    def ensure(self, project):
        function = getattr(self.cli, "ensure_gitignore", None)
        if function is None:
            raise AssertionError(
                "bin/vibe.ensure_gitignore fehlt (Vertrag GH-48).")
        return function(project)

    def test_missing_file_is_created_with_vibe_directory(self):
        """Vor: Projekt ohne .gitignore. Aktion: ensure_gitignore.
        Erwartet: "created", Datei enthält die Zeile .vibe/."""
        project = self.project()

        result = self.ensure(project)

        self.assertEqual("created", result)
        self.assertEqual([".vibe/"],
                         (project / ".gitignore").read_text(
                             encoding="utf-8").splitlines())

    def test_existing_file_is_appended_without_overwriting(self):
        """Vor: .gitignore mit fremdem Inhalt ohne .vibe-Eintrag. Aktion:
        ensure_gitignore. Erwartet: "appended", fremder Inhalt bleibt, .vibe/
        kommt hinzu."""
        project = self.project()
        path = project / ".gitignore"
        path.write_text("node_modules/\n*.log\n", encoding="utf-8")

        result = self.ensure(project)

        self.assertEqual("appended", result)
        text = path.read_text(encoding="utf-8")
        self.assertIn("node_modules/", text)
        self.assertIn("*.log", text)
        self.assertIn(".vibe/", text.splitlines())

    def test_an_existing_vibe_entry_is_never_touched(self):
        """Vor: .gitignore enthält bereits .vibe/, /.vibe/ bzw. .vibe.
        Aktion: ensure_gitignore. Erwartet: False und byte-identische Datei."""
        for content in ("node_modules/\n.vibe/\n", "/.vibe/\n", ".vibe\n"):
            with self.subTest(content=content):
                project = self.project("p" + str(abs(hash(content))))
                path = project / ".gitignore"
                path.write_text(content, encoding="utf-8")
                before = path.read_bytes()

                self.assertFalse(self.ensure(project))
                self.assertEqual(before, path.read_bytes())

    def test_cmd_new_writes_gitignore_before_the_initial_commit(self):
        """Vor: leeres VIBE. Aktion: vibe new p1 generic.
        Erwartet: .gitignore mit .vibe/ existiert; git ls-files des
        Initial-Commits nennt keine .vibe-Datei; der Hinweis nennt das
        Dashboard statt TICKETS.md."""
        result = self.run_cli("new", "p1", "generic")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        project = self.root / "p1"
        gitignore = project / ".gitignore"
        self.assertTrue(gitignore.is_file())
        self.assertIn(".vibe/", gitignore.read_text(encoding="utf-8"))
        tracked = subprocess.run(
            ["git", "-C", str(project), "ls-files"],
            capture_output=True, text=True, env=self.env(), check=False)
        self.assertEqual(0, tracked.returncode, tracked.stderr)
        self.assertFalse([line for line in tracked.stdout.splitlines()
                          if line == ".vibe" or line.startswith(".vibe/")],
                         tracked.stdout)
        self.assertIn("Dashboard", result.stdout)
        self.assertNotIn("TICKETS.md", result.stdout)

    def test_cmd_init_appends_idempotently_and_mentions_the_gitignore(self):
        """Vor: bestehendes Projekt mit .gitignore ohne .vibe. Aktion:
        vibe init proj zweimal. Erwartet: erster Lauf ergänzt .vibe/ und
        nennt .gitignore in der Ausgabe; der zweite Lauf lässt die Datei
        byte-identisch."""
        project = self.root / "proj"
        (project / ".vibe").mkdir(parents=True)
        (project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        gitignore = project / ".gitignore"
        gitignore.write_text("node_modules/\n", encoding="utf-8")

        first = self.run_cli("init", "proj")

        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        text = gitignore.read_text(encoding="utf-8")
        self.assertIn("node_modules/", text)
        self.assertIn(".vibe/", text.splitlines())
        self.assertIn(".gitignore", first.stdout.lower())
        before = gitignore.read_bytes()

        second = self.run_cli("init", "proj")

        self.assertEqual(0, second.returncode, second.stdout + second.stderr)
        self.assertEqual(before, gitignore.read_bytes())


class TemplateTest(unittest.TestCase):
    """Vorlagen und verwalteter Regelblock."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "home").mkdir()

    def test_common_templates_no_longer_contain_the_markdown_ledgers(self):
        """Vor: templates/common. Aktion: Verzeichnis lesen.
        Erwartet: TICKETS.md und FEEDBACK.md fehlen."""
        names = {entry.name for entry in (TEMPLATES / "common").iterdir()}

        self.assertNotIn("TICKETS.md", names)
        self.assertNotIn("FEEDBACK.md", names)

    def block(self, path):
        text = path.read_text(encoding="utf-8")
        start = text.find(MARK)
        end = text.find(END, start + len(MARK)) if start >= 0 else -1
        self.assertGreaterEqual(start, 0, path)
        self.assertGreater(end, start, path)
        return text[start:end + len(END)].strip()

    def test_general_rules_are_identical_in_all_template_agents_files(self):
        """Vor: GENERAL_RULES aus bin/vibe und fünf Vorlagen-AGENTS.md.
        Aktion: verwaltete Blöcke extrahieren.
        Erwartet: alle fünf Blöcke sind untereinander und mit GENERAL_RULES
        identisch (eine Quelle für alle Projekte)."""
        cli = cli_module(self.root)
        expected = cli.GENERAL_RULES.strip()
        blocks = {kind: self.block(TEMPLATES / kind / "AGENTS.md")
                  for kind in TEMPLATE_TYPES}

        for kind, block in blocks.items():
            with self.subTest(kind=kind):
                self.assertEqual(expected, block)

    def test_general_rules_describe_the_field_based_ticket_close(self):
        """Vor: GENERAL_RULES. Aktion: Text prüfen.
        Erwartet: Abschnitt "## Ticketabschluss" mit .vibe/tickets.json,
        TICKET-<ID>.json, state/commit/test; "kein Häkchen" ist ersetzt."""
        cli = cli_module(self.root)
        rules = cli.GENERAL_RULES

        self.assertIn("## Ticketabschluss", rules)
        self.assertIn(".vibe/tickets.json", rules)
        self.assertIn("TICKET-<ID>.json", rules)
        self.assertIn("state", rules)
        self.assertIn("commit", rules)
        self.assertIn("test", rules)
        self.assertNotIn("kein Häkchen", rules)


class GuideTest(unittest.TestCase):
    """Projektassistent kennt die alten Ledger nicht mehr."""

    def guide_module(self):
        sys.path.insert(0, str(BIN))
        return load_script(BIN / "vibe_guide.py",
                           "vibe_guide_gh48_under_test")

    def test_files_list_has_no_tickets_or_feedback_ledger(self):
        """Vor: vibe_guide.FILES. Aktion: Pfade sammeln.
        Erwartet: TICKETS.md und FEEDBACK.md sind nicht mehr Projektdateien;
        SPEC.md, AGENTS.md, project.env und README.md bleiben."""
        paths = {entry["path"] for entry in self.guide_module().FILES}

        self.assertNotIn("TICKETS.md", paths)
        self.assertNotIn("FEEDBACK.md", paths)
        for expected in ("SPEC.md", "AGENTS.md", ".vibe/project.env",
                         "README.md"):
            self.assertIn(expected, paths)

    def test_readme_template_no_longer_lists_the_ledgers(self):
        """Vor: README-Vorlage des Assistenten. Aktion: erzeugen.
        Erwartet: kein Verweis auf TICKETS.md/FEEDBACK.md."""
        text = self.guide_module()._readme("proj", "Ziel")

        self.assertNotIn("TICKETS.md", text)
        self.assertNotIn("FEEDBACK.md", text)
        self.assertIn("SPEC.md", text)
        self.assertIn("AGENTS.md", text)


if __name__ == "__main__":
    unittest.main()
