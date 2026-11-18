"""Regressionsschutz für Projektverwaltung und Vorlagen (V-008).

Die Tests bilden die vier Akzeptanzkriterien des Arbeitspakets ab:

* Gleiche Projektnamen aus mehreren Entwicklungsordnern bleiben eindeutig,
  Symlink-Aliase erzeugen keine doppelten Projekte.
* Ein Projekt wird über ein ``.git``-Verzeichnis oder eine ``.git``-Datei
  erkannt; nicht lesbare Ordner stören die übrigen Projekte nicht.
* ``vibe init`` ergänzt nur fehlende Dateien und lässt vorhandene Dateien,
  auch kaputte Symlinks, unverändert.
* Das Entfernen eines Entwicklungsordners löscht keine Projektdateien, und
  neue Vorlagentypen werden ohne Codeänderung erkannt.

Alle Tests laufen mit einem temporären Arbeitsbereich und temporären
Vorlagen. Es werden keine echten Modell-, Router- oder Git-Netzwerkaufrufe
ausgeführt.
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"


def load_cli(vibe_root, home):
    """Lädt ``bin/vibe`` als Modul mit isoliertem VIBE und HOME."""
    old = {key: os.environ.get(key) for key in ("VIBE", "VIBE_NO_CONTAINER", "HOME")}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_project_management_under_test", str(CLI)
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


class ProjectFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.workspace = self.base / "ws"
        self.workspace.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.cli = load_cli(self.workspace, self.home)
        self.templates = self.base / "templates"
        write_template(
            self.templates,
            "common",
            {"FEEDBACK.md": "# FEEDBACK entsteht aus der Vorlage\n", "TICKETS.md": "# TICKETS\n"},
        )
        write_template(
            self.templates,
            "generic",
            {
                "AGENTS.md": "# AGENTS fuer {{NAME}}\n\n" + self.cli.GENERAL_RULES + "\n",
                ".vibe/project.env": "TYPE=generic\n",
            },
        )
        self.cli.TPL = str(self.templates)

    def clear_cache(self):
        self.cli._pm.clear()

    def make_project(self, parent, name, git_kind="dir"):
        project = Path(parent) / name
        project.mkdir(parents=True)
        if git_kind == "dir":
            (project / ".git").mkdir()
        elif git_kind == "file":
            (project / ".git").write_text("gitdir: ../.git/modules/" + name + "\n", encoding="utf-8")
        elif git_kind == "vibe":
            (project / ".vibe").mkdir()
        self.clear_cache()
        return project

    def init_project(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.cmd_init("proj")
        return out.getvalue()


class DiscoveryTest(ProjectFixture):
    def test_git_directory_and_git_file_are_both_discovered(self):
        self.make_project(self.workspace, "mit-verzeichnis", "dir")
        self.make_project(self.workspace, "mit-datei", "file")
        self.make_project(self.workspace, "nur-vibe", "vibe")

        self.assertEqual(
            self.cli.projects(), ["mit-datei", "mit-verzeichnis", "nur-vibe"]
        )

    def test_duplicate_names_from_roots_with_equal_basenames_stay_unique(self):
        roots = [self.base / label / "projects" for label in ("a", "b", "c")]
        projects = [self.make_project(root, "alpha") for root in roots]
        for root in roots:
            self.cli.root_add(str(root))

        names = [name for name in self.cli.projects() if name.startswith("alpha")]

        self.assertEqual(len(names), 3, names)
        self.assertEqual(len(set(names)), 3, names)
        paths = {os.path.realpath(self.cli.ppath(name)) for name in names}
        self.assertEqual(paths, {os.path.realpath(project) for project in projects})

    def test_symlink_alias_inside_a_root_does_not_duplicate_the_project(self):
        project = self.make_project(self.workspace, "alpha", "dir")
        (self.workspace / "z-alias").symlink_to(project, target_is_directory=True)
        self.clear_cache()

        self.assertEqual(self.cli.projects(), ["alpha"])
        self.assertEqual(self.cli.ppath("alpha"), str(project))

    def test_symlinked_root_is_not_scanned_twice(self):
        project = self.make_project(self.workspace, "alpha", "dir")
        link = self.base / "ws-link"
        link.symlink_to(self.workspace, target_is_directory=True)

        self.cli.root_add(str(link))
        added = self.cli.root_add(str(link))

        self.assertEqual(os.path.realpath(added), os.path.realpath(self.workspace))
        self.assertEqual(
            [os.path.realpath(root) for root in self.cli.roots()],
            [os.path.realpath(self.workspace)],
        )
        self.assertEqual(self.cli.projects(), ["alpha"])
        self.assertEqual(self.cli.ppath("alpha"), str(project))

    def test_unreadable_project_folder_is_skipped_without_breaking_discovery(self):
        good = self.make_project(self.workspace, "gut", "dir")
        broken = self.make_project(self.workspace, "kaputt", "dir")
        self.clear_cache()
        real_stat = os.stat

        def deny_broken(path, *args, **kwargs):
            if isinstance(path, (str, os.PathLike)) and os.fspath(path).startswith(str(broken)):
                raise PermissionError(13, "Keine Berechtigung", os.fspath(path))
            return real_stat(path, *args, **kwargs)

        with mock.patch.object(self.cli.os, "stat", side_effect=deny_broken):
            found = self.cli.project_map()

        self.assertEqual(found.get("gut"), str(good))
        self.assertNotIn("kaputt", found)

    def test_unreadable_root_does_not_stop_other_roots(self):
        good = self.make_project(self.workspace, "gut", "dir")
        locked = self.base / "gesperrt"
        self.make_project(locked, "versteckt", "dir")
        self.cli.root_add(str(locked))
        self.clear_cache()
        real_listdir = os.listdir

        def deny_locked(path="."):
            if os.path.abspath(os.fspath(path)) == str(locked):
                raise PermissionError(13, "Keine Berechtigung", os.fspath(path))
            return real_listdir(path)

        with mock.patch.object(self.cli.os, "listdir", side_effect=deny_locked):
            found = self.cli.project_map()

        self.assertEqual(found.get("gut"), str(good))
        self.assertNotIn("versteckt", " ".join(found))


class RootsTest(ProjectFixture):
    def test_removing_a_root_keeps_every_project_file(self):
        root = self.base / "entwicklungsordner"
        project = self.make_project(root, "bestand", "dir")
        document = project / "wichtig.txt"
        document.write_text("nicht loeschen\n", encoding="utf-8")
        before = {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }
        self.cli.root_add(str(root))

        self.cli.root_remove(str(root))

        after = {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }
        self.assertEqual(after, before)
        self.assertTrue(root.is_dir())
        self.assertTrue(project.is_dir())
        self.assertEqual(document.read_text(encoding="utf-8"), "nicht loeschen\n")
        self.assertNotIn(os.path.realpath(root), [os.path.realpath(r) for r in self.cli.roots()])

    def test_removing_the_same_root_through_a_symlink_keeps_the_project(self):
        root = self.base / "echt"
        project = self.make_project(root, "bestand", "dir")
        link = self.base / "verknuepfung"
        link.symlink_to(root, target_is_directory=True)
        self.cli.root_add(str(link))

        self.cli.root_remove(str(root))

        self.assertTrue((project / ".git").is_dir())
        self.assertEqual(
            [os.path.realpath(r) for r in self.cli.roots()],
            [os.path.realpath(self.workspace)],
        )


class InitTest(ProjectFixture):
    def setUp(self):
        super().setUp()
        self.project = self.workspace / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text("TYPE=generic\n", encoding="utf-8")
        self.clear_cache()

    def test_init_keeps_existing_files_and_only_adds_missing_ones(self):
        feedback = self.project / "FEEDBACK.md"
        feedback.write_text("# eigener Inhalt\n", encoding="utf-8")
        own = self.project / "NOTIZ.md"
        own.write_text("bleibt\n", encoding="utf-8")

        output = self.init_project()

        self.assertEqual(feedback.read_text(encoding="utf-8"), "# eigener Inhalt\n")
        self.assertEqual(own.read_text(encoding="utf-8"), "bleibt\n")
        self.assertEqual(
            (self.project / "AGENTS.md").read_text(encoding="utf-8"),
            "# AGENTS fuer proj\n\n" + self.cli.GENERAL_RULES + "\n",
        )
        self.assertIn("AGENTS.md", output)

    def test_init_on_an_already_prepared_project_changes_nothing(self):
        self.init_project()
        before = {
            path.relative_to(self.project).as_posix(): path.read_bytes()
            for path in sorted(self.project.rglob("*"))
            if path.is_file()
        }

        output = self.init_project()

        after = {
            path.relative_to(self.project).as_posix(): path.read_bytes()
            for path in sorted(self.project.rglob("*"))
            if path.is_file()
        }
        self.assertEqual(after, before)
        self.assertIn("Nichts zu ergänzen", output)
        self.assertFalse((self.project / ".git").exists())

    def test_init_appends_general_rules_to_an_existing_agents_file(self):
        agents = self.project / "AGENTS.md"
        agents.write_text("# eigene Regel\n", encoding="utf-8")

        output = self.init_project()

        text = agents.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# eigene Regel\n"))
        self.assertEqual(text.count(self.cli.GENERAL_RULES_MARK), 1)
        self.assertIn("Projektordner sauber halten", text)
        self.assertIn("Allgemeine Regeln in AGENTS.md ergänzt", output)

    def test_init_does_not_duplicate_general_rules(self):
        self.init_project()
        agents = self.project / "AGENTS.md"
        first = agents.read_text(encoding="utf-8")

        self.init_project()

        self.assertEqual(agents.read_text(encoding="utf-8"), first)
        self.assertEqual(first.count(self.cli.GENERAL_RULES_MARK), 1)

    def test_init_updates_an_outdated_managed_rules_block_in_place(self):
        agents = self.project / "AGENTS.md"
        agents.write_text(
            "# eigene Regel\n\n"
            + self.cli.GENERAL_RULES_MARK
            + "\n## Alt\n- veraltet\n<!-- /vibe:general-rules -->\n\n## Eigener Rest\n",
            encoding="utf-8",
        )

        output = self.init_project()

        text = agents.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# eigene Regel\n"))
        self.assertIn("Projektordner sauber halten", text)
        self.assertIn("Ordnung im Git halten", text)
        self.assertNotIn("veraltet", text)
        self.assertIn("## Eigener Rest\n", text)
        self.assertEqual(text.count(self.cli.GENERAL_RULES_MARK), 1)
        self.assertIn("aktualisiert", output)

    def test_init_replaces_an_outdated_rules_block_with_the_coding_guidelines(self):
        agents = self.project / "AGENTS.md"
        agents.write_text(
            "# eigene Regel\n\n"
            + self.cli.GENERAL_RULES_MARK
            + "\n## Alt\n- veraltet\n<!-- /vibe:general-rules -->\n\n## Eigener Rest\n",
            encoding="utf-8",
        )

        output = self.init_project()

        text = agents.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# eigene Regel\n"))
        self.assertIn("## Eigener Rest\n", text)
        self.assertNotIn("- veraltet", text)
        for rule in ("KISS", "Clean Code", "Caching", "Invalidierung"):
            self.assertIn(rule, text)
        self.assertIn("aktualisiert", output)

    def test_init_leaves_an_unpaired_rules_marker_unchanged(self):
        agents = self.project / "AGENTS.md"
        original = "# eigene Regel\n\n" + self.cli.GENERAL_RULES_MARK + "\n- ohne Ende\n"
        agents.write_text(original, encoding="utf-8")

        self.init_project()

        self.assertEqual(agents.read_text(encoding="utf-8"), original)

    def test_init_leaves_non_utf8_agents_file_unchanged(self):
        agents = self.project / "AGENTS.md"
        original = b"# eigene Regel\n\xff\n"
        agents.write_bytes(original)

        self.init_project()

        self.assertEqual(agents.read_bytes(), original)

    def test_init_does_not_write_through_a_broken_symlink(self):
        outside = self.base / "ausserhalb.md"
        link = self.project / "FEEDBACK.md"
        link.symlink_to(outside)

        self.init_project()

        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), str(outside))
        self.assertFalse(outside.exists())

    def test_init_does_not_follow_an_agents_symlink(self):
        outside = self.base / "ausserhalb-agents.md"
        outside.write_text("# fremd\n", encoding="utf-8")
        (self.project / "AGENTS.md").symlink_to(outside)

        self.init_project()

        self.assertEqual(outside.read_text(encoding="utf-8"), "# fremd\n")

    def test_init_applies_a_new_template_type_without_code_changes(self):
        write_template(
            self.templates,
            "custom",
            {"AGENTS.md": "# CUSTOM {{NAME}}\n", ".vibe/project.env": "TYPE=custom\n"},
        )

        self.assertIn("custom", self.cli.types())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.cli.cmd_init("proj", "custom")

        self.assertEqual(
            (self.project / "AGENTS.md").read_text(encoding="utf-8"),
            "# CUSTOM proj\n\n" + self.cli.GENERAL_RULES + "\n",
        )
        # Der vorhandene TYPE bleibt erhalten; nur der fehlende TESTER wird
        # ergänzt, damit der Pflicht-Test-Agent auch in bestehenden Projekten
        # eindeutig zugeordnet ist.
        self.assertEqual(
            (self.project / ".vibe" / "project.env").read_text(encoding="utf-8"),
            "TYPE=generic\nTESTER=test-agent\n",
        )
        self.assertIn("als 'custom' vorbereitet", out.getvalue())

    def test_init_adds_the_test_agent_and_tester_to_an_existing_project(self):
        output = self.init_project()

        agent = self.project / ".opencode" / "agents" / "test-agent.md"
        self.assertTrue(agent.is_file())
        self.assertIn("mode: subagent", agent.read_text(encoding="utf-8"))
        env = (self.project / ".vibe" / "project.env").read_text(encoding="utf-8")
        self.assertIn("TESTER=test-agent\n", env)
        self.assertIn("TYPE=generic\n", env)
        self.assertIn("Test-Agent", output)

    def test_init_preserves_an_existing_test_agent_and_tester(self):
        agent = self.project / ".opencode" / "agents" / "test-agent.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("# eigener Test-Agent\n", encoding="utf-8")
        env_path = self.project / ".vibe" / "project.env"
        env_path.write_text("TYPE=generic\nTESTER=eigener-tester\n", encoding="utf-8")

        self.init_project()

        self.assertEqual(agent.read_text(encoding="utf-8"), "# eigener Test-Agent\n")
        self.assertEqual(
            env_path.read_text(encoding="utf-8"),
            "TYPE=generic\nTESTER=eigener-tester\n",
        )

    def test_init_does_not_write_through_a_test_agent_symlink(self):
        outside = self.base / "ausserhalb-test-agent.md"
        agent = self.project / ".opencode" / "agents" / "test-agent.md"
        agent.parent.mkdir(parents=True)
        agent.symlink_to(outside)

        self.init_project()

        self.assertTrue(agent.is_symlink())
        self.assertEqual(os.readlink(agent), str(outside))
        self.assertFalse(outside.exists())


class TemplateRulesTest(ProjectFixture):
    # Verbindliche Mindestmerkmale der gestuften Prüfpraxis (F31). Die Tests
    # legen damit die erwartete Fachlichkeit wörtlich fest; die Umsetzung muss
    # diese Aussagen in den allgemeinen Regeln und allen Vorlagen führen.
    VERIFY_EFFICIENCY_RULE = (
        "Effizienz der Prüfungen (verbindlich)",
        "betroffene Testmodule",
        "VERIFY_PACKAGE",
        "VERIFY_FULL",
        "genau einmal",
        "vor der Abnahme",
        "Änderungen",
        "Code oder Tests",
        "Nachweisumfang",
        "abgeschwächt",
    )

    def assert_efficiency_rule(self, text, source):
        for marker in self.VERIFY_EFFICIENCY_RULE:
            self.assertIn(marker, text, f"{marker!r} fehlt in {source}")

    def test_general_rules_require_tiered_verification(self):
        rules = self.cli.GENERAL_RULES

        self.assert_efficiency_rule(rules, "GENERAL_RULES")
        # Während der Arbeit bleibt die Prüfung klein; die vollständige Suite
        # ist der Abschlussnachweis und wird nicht durch Wiederholungen ersetzt.
        self.assertIn("während der Bearbeitung", rules)

    def test_all_shipped_project_templates_contain_the_verification_efficiency_rule(self):
        templates = sorted((REPO / "templates").glob("*/AGENTS.md"))
        self.assertTrue(templates)
        for path in templates:
            text = path.read_text(encoding="utf-8")
            self.assert_efficiency_rule(text, str(path))

    def test_repository_agents_file_contains_the_verification_efficiency_rule(self):
        path = REPO / "AGENTS.md"
        self.assertTrue(
            path.is_file(),
            "AGENTS.md fehlt im Repository-Wurzelverzeichnis; die Repository-"
            "Regeln können nicht geprüft werden.",
        )
        text = path.read_text(encoding="utf-8")
        self.assert_efficiency_rule(text, str(path))

    def test_all_shipped_project_templates_contain_the_cleanup_rules(self):
        templates = sorted((REPO / "templates").glob("*/AGENTS.md"))
        self.assertTrue(templates)
        for path in templates:
            text = path.read_text(encoding="utf-8")
            self.assertIn(self.cli.GENERAL_RULES_MARK, text, path)
            self.assertIn(self.cli.GENERAL_RULES, text, path)
            for rule in (
                "Projektordner sauber halten",
                "Ordnung im Git halten",
                "Feature-Branch",
                "git status",
                "relevanten Diff",
                "stashen",
                "Force-Push",
            ):
                self.assertIn(rule, text, path)

    def test_general_rules_cover_cleanup_and_git_order(self):
        rules = self.cli.GENERAL_RULES
        self.assertIn("Projektordner sauber halten", rules)
        self.assertIn("Ordnung im Git halten", rules)
        self.assertIn("Feature-Branch", rules)
        self.assertIn("git status", rules)
        self.assertIn("Force-Push", rules)

    def test_all_shipped_project_templates_contain_the_coding_guidelines(self):
        templates = sorted((REPO / "templates").glob("*/AGENTS.md"))
        self.assertTrue(templates)
        for path in templates:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Leitlinien für Coding-Agenten", text, path)
            for rule in ("KISS", "Clean Code", "Caching", "Invalidierung"):
                self.assertIn(rule, text, path)

    def test_general_rules_require_kiss_clean_code_and_safe_caching(self):
        rules = self.cli.GENERAL_RULES
        for rule in (
            "Leitlinien für Coding-Agenten",
            "KISS",
            "Clean Code",
            "Caching",
            "Invalidierung",
            "neuen und bestehenden Projekte",
        ):
            self.assertIn(rule, rules)

    def test_repository_agents_file_contains_the_coding_guidelines(self):
        text = (REPO / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Leitlinien für Coding-Agenten", text)
        for rule in ("KISS", "Clean Code", "Caching", "Invalidierung"):
            self.assertIn(rule, text)

    def test_all_shipped_project_templates_contain_the_test_agent_rule(self):
        templates = sorted((REPO / "templates").glob("*/AGENTS.md"))
        self.assertTrue(templates)
        for path in templates:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Unabhängiger Test-Agent (verbindlich)", text, path)
            for rule in ("TESTER", "test-agent", "ausschließlich", "Reviewer"):
                self.assertIn(rule, text, path)

    def test_all_shipped_project_templates_configure_the_tester(self):
        envs = sorted((REPO / "templates").glob("*/.vibe/project.env"))
        self.assertTrue(envs)
        for path in envs:
            text = path.read_text(encoding="utf-8")
            self.assertIn("TESTER=test-agent", text, path)

    def test_general_rules_require_an_independent_test_agent(self):
        rules = self.cli.GENERAL_RULES
        for rule in (
            "Unabhängiger Test-Agent (verbindlich)",
            "TESTER",
            "test-agent",
            "ausschließlich",
            "Coding- und Review-Agent",
            "kein Nachweis",
        ):
            self.assertIn(rule, rules)

    def test_repository_agents_file_contains_the_test_agent_rule(self):
        text = (REPO / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Unabhängiger Test-Agent (verbindlich)", text)
        for rule in ("TESTER", "test-agent", "ausschließlich"):
            self.assertIn(rule, text)

    def test_shipped_test_agent_template_is_complete(self):
        path = REPO / "templates" / "common" / ".opencode" / "agents" / "test-agent.md"
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text, self.cli.TEST_AGENT_TEMPLATE)
        self.assertIn("description:", text)
        self.assertIn("mode: subagent", text)
        self.assertIn("permission:", text)
        self.assertIn("Testfälle", text)
        self.assertIn("Produktionscode", text)
        self.cli.agent_validate(text)

    def test_all_shipped_project_templates_have_exactly_one_general_rules_marker(self):
        # F31: Jede Vorlage darf genau ein oeffnendes und genau ein
        # schliessendes Markerpaar fuer die allgemeinen Regeln enthalten.
        templates = sorted((REPO / "templates").glob("*/AGENTS.md"))
        self.assertTrue(templates)
        for path in templates:
            text = path.read_text(encoding="utf-8")
            self.assertEqual(
                text.count(self.cli.GENERAL_RULES_MARK), 1,
                f"{path}: oeffnender Marker count != 1",
            )
            self.assertEqual(
                text.count(self.cli.GENERAL_RULES_END), 1,
                f"{path}: schliessender Marker count != 1",
            )


if __name__ == "__main__":
    unittest.main()
