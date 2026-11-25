"""Projektverwaltung: Anlegen per Klon, lokale Übernahme, Vorlagen und Gerüstdateien.

Aufruf: python3 -m unittest tests.unit.test_project_management -v
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
                "AGENTS.md": "# AGENTS fuer {{NAME}}\n\n",
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
            "# AGENTS fuer proj\n\n",
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

    def test_init_leaves_an_existing_legacy_rules_block_byte_identical(self):
        """Vor: Bestands-AGENTS.md mit altem verwaltetem Block. Aktion:
        ``vibe init``. Erwartet: Datei byte-identisch; kein Update, keine
        zweite Regelquelle, keine Erfolgsmeldung über allgemeine Regeln."""
        agents = self.project / "AGENTS.md"
        original = (
            "# eigene Regel\n\n"
            + self.cli.GENERAL_RULES_MARK
            + "\n## Alt\n- veraltet\n"
            + self.cli.GENERAL_RULES_END
            + "\n\n## Eigener Rest\n"
        )
        agents.write_text(original, encoding="utf-8")

        output = self.init_project()

        self.assertEqual(original, agents.read_text(encoding="utf-8"))
        self.assertNotIn("Allgemeine Regeln", output)

    def test_init_does_not_add_a_rules_block_to_an_existing_agents_file(self):
        """Vor: Bestands-AGENTS.md ohne Marker. Aktion: ``vibe init``.
        Erwartet: unverändert; kein Block, keine Marker, kein Regeltext."""
        agents = self.project / "AGENTS.md"
        agents.write_text("# eigene Regel\n", encoding="utf-8")

        self.init_project()

        self.assertEqual("# eigene Regel\n", agents.read_text(encoding="utf-8"))

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
            "# CUSTOM proj\n",
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


class TemplateFilesTest(ProjectFixture):
    """Vorlagen ohne den früheren deutschen Regelblock (GH-76)."""

    def test_all_shipped_project_templates_configure_the_tester(self):
        envs = sorted((REPO / "templates").glob("*/.vibe/project.env"))
        self.assertTrue(envs)
        for path in envs:
            text = path.read_text(encoding="utf-8")
            self.assertIn("TESTER=test-agent", text, path)

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

    def test_all_shipped_project_templates_are_free_of_the_managed_block(self):
        # GH-76: Der deutsche Pflichtblock lebt nicht mehr in den Vorlagen;
        # die Runner-Logistik kommt aus dem verborgenen Plattformtext.
        templates = sorted((REPO / "templates").glob("*/AGENTS.md"))
        self.assertTrue(templates)
        for path in templates:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(self.cli.GENERAL_RULES_MARK, text, path)
            self.assertNotIn(self.cli.GENERAL_RULES_END, text, path)
            self.assertNotIn("Projektordner sauber halten", text, path)


# ===========================================================================
# Abnahme „Bereit für Github Teil 2“: Auschecken aus GitHub
# ===========================================================================

import importlib.machinery
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


# Isolierte Umgebungsvariablen (Muster tests/unit/test_project_agents.py).
ISOLATED_ENV = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_STORAGE_LOCK_DIR",
    "VIBE_PROFILE", "VIBE_INSTALL", "VIBE_RUNTIME", "VIBE_STATE",
    "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE", "VIBE_CONFIG_DIR",
    "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER", "MAX_PACKAGES", "VERIFY_QUICK", "VERIFY_FULL",
    "AGENT", "SANDBOX", "SANDBOX_TOOLS", "GITHUB_TOKEN", "GH_TOKEN",
)

# Werte der lokalen Vorlage, die mit dem Projekt mitgelieferte
# Einstellungen überschreiben müssen (AP8, Nutzerentscheidung).
LOKALE_REVIEWER = "lokal-reviewer"
LOKALE_SANDBOX = "aus"
LOKALE_QUICK = "echo lokal-quick"
LOKALE_PAKET = "echo lokal-paket"
LOKALE_FULL = "echo lokal-full"

# GH-76: Ein bereits vorhandener Bestandsblock bleibt beim Übernehmen
# byte-identisch; es wird kein neuer Block erzeugt.
LEGACY_AGENTS = (
    "# Repo-Regel\n\n"
    "<!-- vibe:general-rules -->\n"
    "## Alt\n- veraltet\n"
    "<!-- /vibe:general-rules -->\n\n"
    "## Eigener Rest\n"
)
TEST_AGENT_TEMPLATE = "LOKALER-PRUEFAGENT-STAND-4711\n"
TICKETS_TEMPLATE = "# TICKETS-LUECKE-A-LDOK\n"
FEEDBACK_TEMPLATE = "# FEEDBACK-LUECKE-A-LDOK\n"
OPENCODE_JSON_TEMPLATE = '{\n  "$schema": "lokale-opencode-vorlage"\n}\n'

REPO_ENV = (
    "TYPE=generic\n"
    "REVIEWER=repo-reviewer\n"
    "TESTER=repo-tester\n"
    "SANDBOX=an\n"
    'SANDBOX_TOOLS="git,cargo"\n'
    'VERIFY_QUICK="echo repo-quick"\n'
    'VERIFY_PACKAGE="echo repo-paket"\n'
    'VERIFY_FULL="echo repo-full"\n'
    "BENUTZER=EIGEN\n"
    "EXTRA=bleibt\n"
)

GLOBAL_AGENT = """---
description: Globaler Agent
mode: subagent
model: opencode/global-modell
---

Globaler Prompt.
"""

VIBE_AGENT = """---
description: Vibe-Standardagent
mode: primary
model: opencode/vibe-modell
---

Vibe-Prompt.
"""

GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_AUTHOR_DATE": "2005-04-07T22:13:13Z",
    "GIT_COMMITTER_DATE": "2005-04-07T22:13:13Z",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def git(cwd, *argv):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    subprocess.run(["git", *argv], cwd=str(cwd), env=env, check=True,
                   capture_output=True, text=True, timeout=60)


def git_out(cwd, *argv):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(["git", *argv], cwd=str(cwd), env=env, check=True,
                          capture_output=True, text=True, timeout=60).stdout


def load_cli_checkout(vibe_root, home):
    """Lädt ``bin/vibe`` als Modul mit isoliertem VIBE und HOME."""
    old = {key: os.environ.get(key) for key in ISOLATED_ENV}
    for key in ISOLATED_ENV:
        os.environ.pop(key, None)
    os.environ.update({
        "VIBE": str(vibe_root),
        "VIBE_NO_CONTAINER": "1",
        "HOME": str(home),
        "VIBE_AGENTS_DIR": str(Path(home) / ".config" / "opencode" / "agents"),
        "VIBE_CONFIG_FILE": str(Path(home) / ".config" / "vibe" / "config.json"),
    })
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_ap8_github_checkout_under_test", str(CLI)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return module


def write_checkout_templates(templates, typ, files):
    for relative, content in files.items():
        target = Path(templates) / typ / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


class StorageFixture(unittest.TestCase):
    """Temporärer Arbeitsbereich mit lokalen Vorlagen und lokalen Agenten."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "ws"
        self.workspace.mkdir()
        self.home = self.root / "home"
        self.home.mkdir()
        self.install = self.root / "_toolchain"
        self.install.mkdir()
        self.agents = self.home / ".config" / "opencode" / "agents"
        self.agents.mkdir(parents=True)
        # Die Prüfumgebung wird nur für diesen Test gesetzt und danach
        # zurückgebaut: Ohne Rückbau leakt VIBE_STATE/VIBE_STORAGE_LOCK_DIR in
        # nachfolgende Testmodule desselben Prozesses (Fehlbefund Fixlauf 2).
        environment = mock.patch.dict(os.environ, {
            "VIBE_STORAGE_LOCK_DIR": str(self.workspace / "locks"),
            "VIBE_STATE": str(self.install),
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.cli = load_cli_checkout(self.workspace, self.home)
        self.build_local_templates()
        self.build_local_agents()

    # --------------------------------------------- lokale Welt (Vorlagen)
    def build_local_templates(self):
        """Lokale Vorlagen: Genau sie sollen nach dem Clone gelten."""
        templates = self.root / "templates"
        write_checkout_templates(templates, "common", {
            "FEEDBACK.md": FEEDBACK_TEMPLATE,
            "TICKETS.md": TICKETS_TEMPLATE,
            "opencode.json": OPENCODE_JSON_TEMPLATE,
            ".opencode/agents/test-agent.md": TEST_AGENT_TEMPLATE,
        })
        write_checkout_templates(templates, "generic", {
            "AGENTS.md": "# AGENTS fuer {{NAME}}\n\n",
            ".vibe/project.env": (
                "TYPE=generic\n"
                "REVIEWER=" + LOKALE_REVIEWER + "\n"
                "TESTER=test-agent\n"
                "SANDBOX=" + LOKALE_SANDBOX + "\n"
                "SANDBOX_TOOLS=\n"
                "VERIFY_QUICK=" + LOKALE_QUICK + "\n"
                "VERIFY_PACKAGE=" + LOKALE_PAKET + "\n"
                "VERIFY_FULL=" + LOKALE_FULL + "\n"
            ),
        })
        self.cli.TPL = str(templates)

    def build_local_agents(self):
        """Lokal konfigurierte globale Agenten: „tester“ plus Vibe-Agent."""
        (self.agents / "tester.md").write_text(GLOBAL_AGENT, encoding="utf-8")
        (self.agents / "vibe-agent.md").write_text(VIBE_AGENT, encoding="utf-8")
        data = self.cli.profiles_load()
        data["rollen"] = dict(data.get("rollen", {}))
        data["rollen"]["vibe-agent"] = "vibe"
        self.cli.profiles_save(data)

    # --------------------------------------------- Bare-Repositories
    def bare_path(self, name):
        return self.root / "origin" / (name + ".git")

    def seed_bare(self, name, files):
        """Erzeugt eine Bare-Quelle ohne Netz und liefert die file://-Adresse."""
        work = self.root / "seed" / name
        work.mkdir(parents=True)
        for relative, content in files.items():
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        git(work, "init", "-q", "-b", "main")
        git(work, "add", "-A")
        git(work, "commit", "-q", "-m", "seed")
        bare = self.bare_path(name)
        bare.mkdir(parents=True)
        git(bare, "init", "-q", "--bare")
        git(work, "push", "-q", str(bare), "main")
        git(bare, "symbolic-ref", "HEAD", "refs/heads/main")
        self.cli._pm.clear()
        return "file://" + str(bare)

    # --------------------------------------------- hilfreiche Projekte
    def checkout(self, url, name=None):
        """Führt ``checkout_from_github`` aus und listet im Anschluss frisch."""
        out = io.StringIO()
        with redirect_stdout(out):
            result = self.cli.checkout_from_github(url, name=name)
        self.assertTrue(bool(result), "Fehlendes (name, Zusammenfassung)-Ergebnis")
        found, summary = result
        return found, str(summary or "")

    def expect_error(self, url, name=None):
        """Führt das Auschecken aus und liefert die geworfene Ausnahme."""
        with self.assertRaises(Exception) as caught:
            self.checkout(url, name=name)
        self.assertTrue(str(caught.exception).strip(),
                        "Eine Fehlermeldung darf nicht leer sein")
        return caught.exception

    def project_env_path(self, name):
        return self.workspace / name / ".vibe" / "project.env"

    def env_values(self, name):
        return self.cli.read_env(str(self.project_env_path(name)))


# ================================================================ Cloning
class CloneAndProjectTest(StorageFixture):
    """AK1: Auschecken legt ein neues Projekt an; Name aus Parameter oder URL."""

    def test_checkout_clones_the_repository_and_lists_the_new_project(self):
        url = self.seed_bare("koffer", {"README.md": "Koffer-Inhalt\n"})
        self.assertEqual(self.cli.projects(), [])

        found, summary = self.checkout(url)

        self.assertEqual(found, "koffer")
        self.assertTrue(summary.strip(), "Eine Zusammenfassung ist erwartet")
        self.assertTrue((self.workspace / "koffer" / ".git").is_dir())
        self.assertEqual(
            (self.workspace / "koffer" / "README.md").read_text(encoding="utf-8"),
            "Koffer-Inhalt\n",
        )
        # Direkt (ohne jeden Zusatz-Reload) in der Projektliste auffindbar:
        self.assertIn("koffer", self.cli.projects())
        mapping = self.cli.project_map()
        self.assertIn("koffer", mapping)
        self.assertEqual(
            os.path.realpath(mapping["koffer"]),
            os.path.realpath(self.workspace / "koffer"),
        )

    def test_project_name_is_taken_from_the_url_when_not_given(self):
        url = self.seed_bare("mein-koffer", {"README.md": "Inhalt\n"})

        found, _summary = self.checkout(url)

        self.assertEqual(found, "mein-koffer")
        self.assertTrue((self.workspace / "mein-koffer" / ".git").is_dir())
        self.assertIn("mein-koffer", self.cli.projects())

    def test_project_name_is_cleaned_to_the_allowed_pattern(self):
        """Ordnername mit Leer- und Großbuchstaben wird auf das zulässige
        Muster ^[a-z0-9][a-z0-9_-]*$ bereinigt."""
        url = self.seed_bare("Mein Projekt", {"README.md": "Inhalt\n"})

        found, _summary = self.checkout(url)

        self.assertRegex(found, r"^[a-z0-9][a-z0-9_-]*$")
        self.assertTrue((self.workspace / found / ".git").is_dir())
        self.assertIn(found, self.cli.projects())

    def test_given_name_wins_over_the_derived_name(self):
        url = self.seed_bare("autoform", {"README.md": "Inhalt\n"})

        found, _summary = self.checkout(url, name="lager")

        self.assertEqual(found, "lager")
        self.assertTrue((self.workspace / "lager" / "README.md").is_file())
        self.assertFalse((self.workspace / "autoform").exists())
        self.assertIn("lager", self.cli.projects())
        self.assertNotIn("autoform", self.cli.projects())

    def test_remote_origin_points_to_the_checked_out_address(self):
        url = self.seed_bare("adresse", {"README.md": "Inhalt\n"})

        self.checkout(url)

        origin = git_out(self.workspace / "adresse",
                         "remote", "get-url", "origin").strip()
        self.assertEqual(origin, url)


# ============================================================= Übernahme
class LocalAdoptionTest(StorageFixture):
    """AK2: Lokale vibe-Einstellungen überschreiben die Projekteinstellungen."""

    def full_remote(self):
        """Bare-Quelle, die alles mitbringt, was laut Nutzerentscheidung von
        der lokalen Vorlage übernommen/ersetzt werden muss."""
        return self.seed_bare("koffer", {
            "README.md": "Koffer\n",
            ".vibe/project.env": REPO_ENV,
            ".vibe/agents.json": json.dumps({
                "version": 2,
                "aktiv": ["vibe-agent", "fremd", "tester"],
                "modelle": {"fremd": "x/fremd", "tester": "opencode/behalt"},
            }),
            ".opencode/agents/test-agent.md": "# Mitgelieferter V99\n",
            "AGENTS.md": LEGACY_AGENTS,
            "FEEDBACK.md": "# Eigenes Feedback\n",
        })

    def test_missing_project_env_is_created_from_the_local_template(self):
        url = self.seed_bare("blanko", {"README.md": "Inhalt\n"})

        found, _summary = self.checkout(url)

        self.assertTrue(self.project_env_path(found).is_file(),
                        "project.env fehlt nach dem Auschecken")
        values = self.env_values(found)
        self.assertEqual(values.get("TESTER"), "test-agent")
        self.assertEqual(values.get("REVIEWER"), LOKALE_REVIEWER)
        self.assertEqual(values.get("VERIFY_QUICK"), LOKALE_QUICK)
        self.assertIn(values.get("TYPE") or "", self.cli.types())

    def test_local_template_values_overwrite_the_managed_repository_keys(self):
        url = self.full_remote()

        found, _summary = self.checkout(url)

        values = self.env_values(found)
        for key, expected in (
            ("REVIEWER", LOKALE_REVIEWER),
            ("TESTER", "test-agent"),
            ("SANDBOX", LOKALE_SANDBOX),
            ("VERIFY_QUICK", LOKALE_QUICK),
            ("VERIFY_PACKAGE", LOKALE_PAKET),
            ("VERIFY_FULL", LOKALE_FULL),
        ):
            self.assertEqual(values.get(key), expected, key)
        text = self.project_env_path(found).read_text(encoding="utf-8")
        for verboten in ("repo-quick", "repo-paket", "repo-full",
                         "repo-tester", "repo-reviewer"):
            self.assertNotIn(verboten, text, verboten)
        # Eigene, nicht verwaltete Schlüssel bleiben:
        self.assertEqual(values.get("EXTRA"), "bleibt")
        self.assertIn("BENUTZER=EIGEN", text)
        # TYPE steht auf dem erkannten Typ; die verwalteten Werte stammen aus
        # der lokalen Vorlage dieses Typs.
        typ = values.get("TYPE") or ""
        self.assertIn(typ, self.cli.types(), typ)
        template_values = self.cli.read_env(
            os.path.join(self.cli.TPL, typ, ".vibe", "project.env")
        )
        for key in ("REVIEWER", "VERIFY_QUICK"):
            self.assertEqual(values.get(key), template_values.get(key),
                             "Vorlagewert von " + key)

    def test_github_com_url_sets_the_github_link_without_contacting_github(self):
        """github.com-Adresse: GITHUB_REPO=owner/name und GITHUB_ENABLED=1.
        github.com wird dabei nicht kontaktiert — der echte Clone-Tätigkeit
        wird durch eine fiktive, in den Zielordner gestellte Quelle ersetzt."""
        url = "https://github.com/owner/beispiel.git"
        fake_state = {}

        def fake_clone(given_url, given_target):
            self.assertEqual(str(given_url), url)
            fake_state["target"] = str(given_target)
            target = str(given_target)
            os.makedirs(target, exist_ok=True)
            git(target, "init", "-q", "-b", "main")
            (Path(target) / "README.md").write_text("GitHub-Inhalt\n", encoding="utf-8")
            git(target, "add", "-A")
            git(target, "commit", "-q", "-m", "github")
            git(target, "remote", "add", "origin", given_url)
            return 0, "fiktives geklontes Ergebnis"

        # MagicMock als Stand-in: Nur so bleibt die Aufrufprüfung (genau
        # einmal) erhalten; die Prüfung der Argumente macht fake_clone selbst.
        standin = mock.MagicMock(side_effect=fake_clone)
        with mock.patch.object(self.cli.vibe_github, "clone", standin):
            found, _summary = self.checkout(url)

        standin.assert_called_once()
        self.assertEqual(fake_state["target"],
                         str(self.workspace / "beispiel"))
        self.assertEqual(found, "beispiel")
        self.assertIn("beispiel", self.cli.projects())
        values = self.env_values("beispiel")
        self.assertEqual(values.get("GITHUB_REPO"), "owner/beispiel")
        self.assertEqual(values.get("GITHUB_ENABLED"), "1")

    def test_file_remotes_stay_without_github_keys(self):
        url = self.seed_bare("nur-localekle", {"README.md": "Inhalt\n"})

        found, _summary = self.checkout(url)

        values = self.env_values(found)
        self.assertEqual(values.get("GITHUB_REPO") or "", "")
        self.assertIsNone(values.get("GITHUB_ENABLED"))

    def test_an_existing_legacy_rules_block_is_left_byte_identical(self):
        url = self.full_remote()

        found, _summary = self.checkout(url)

        text = (self.workspace / found / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(
            LEGACY_AGENTS, text,
            "Die Übernahme hat einen bestehenden AGENTS.md-Block verändert")

    def test_a_missing_agents_file_is_created_from_the_block_free_template(self):
        url = self.seed_bare("ohne-regeln", {"README.md": "Inhalt\n"})

        found, _summary = self.checkout(url)

        text = (self.workspace / found / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual("# AGENTS fuer " + found + "\n\n", text)
        self.assertNotIn(self.cli.GENERAL_RULES_MARK, text)
        self.assertNotIn(self.cli.GENERAL_RULES_END, text)
        self.assertNotIn("Projektordner sauber halten", text)

    def test_missing_template_files_are_added_and_own_content_survives(self):
        url = self.full_remote()

        found, _summary = self.checkout(url)
        project = self.workspace / found

        self.assertEqual((project / "TICKETS.md").read_text(encoding="utf-8"),
                         TICKETS_TEMPLATE)
        self.assertEqual((project / "opencode.json").read_text(encoding="utf-8"),
                         OPENCODE_JSON_TEMPLATE)
        # Vorhandene Dateien bleiben unverändert:
        self.assertEqual((project / "FEEDBACK.md").read_text(encoding="utf-8"),
                         "# Eigenes Feedback\n")
        self.assertEqual((project / "README.md").read_text(encoding="utf-8"),
                         "Koffer\n")

    def test_the_shipped_test_agent_is_replaced_by_the_local_template(self):
        url = self.full_remote()

        found, _summary = self.checkout(url)

        agent = self.workspace / found / ".opencode" / "agents" / "test-agent.md"
        self.assertEqual(agent.read_text(encoding="utf-8"), TEST_AGENT_TEMPLATE)
        self.assertEqual(self.env_values(found).get("TESTER"), "test-agent")


    def test_unmanaged_keys_keep_the_repository_value_while_managed_keys_move_local(self):
        """Ein Schlüssel, der nicht zur verwalteten Menge gehört, bleibt beim
        mitgelieferten Wert — auch wenn die lokale Vorlage ihn ebenfalls kennt;
        abweichende verwaltete Schlüssel gehen auf den lokalen Stand."""
        template = Path(self.cli.TPL) / "generic" / ".vibe" / "project.env"
        template.write_text(
            template.read_text(encoding="utf-8") + "EXTRA_KEY=lokal-vorlage\n",
            encoding="utf-8",
        )
        url = self.seed_bare("fremdschluessel", {
            "README.md": "fremd\n",
            ".vibe/project.env": (
                "TYPE=generic\n"
                "TESTER=repo-tester\n"
                "EXTRA_KEY=projektwert\n"
                "BENUTZER=EIGEN\n"
            ),
        })

        found, _summary = self.checkout(url)

        values = self.env_values(found)
        self.assertEqual(values.get("EXTRA_KEY"), "projektwert")
        self.assertEqual(values.get("TESTER"), "test-agent")
        self.assertEqual(values.get("REVIEWER"), LOKALE_REVIEWER)
        self.assertIn(values.get("TYPE") or "", self.cli.types())
        self.assertIn(
            "BENUTZER=EIGEN",
            self.project_env_path(found).read_text(encoding="utf-8"),
        )


# ================================================================ Agenten
class AgentRemapTest(StorageFixture):
    """AK3: Aktive Agenten des Projekts werden neu auf lokale Agenten gesetzt."""

    def url_with_agents_config(self, aktiv, modelle):
        return self.seed_bare("agentfuder", {
            "README.md": "Agenten\n",
            ".vibe/project.env": "TYPE=generic\n",
            ".vibe/agents.json": json.dumps({
                "version": 2, "aktiv": aktiv, "modelle": modelle,
            }),
        })

    def test_active_agents_are_limited_to_locally_configured_agents(self):
        url = self.url_with_agents_config(
            aktiv=["vibe-agent", "fremd", "tester"],
            modelle={"fremd": "x/fremd", "tester": "opencode/behalt"},
        )

        self.checkout(url)

        path = self.workspace / "agentfuder" / ".vibe" / "agents.json"
        self.assertTrue(path.is_file(), "agents.json bleibt nach dem Clone gesetzt")
        stored = json.loads(path.read_text(encoding="utf-8"))
        aktiv = sorted(stored["aktiv"])
        self.assertNotIn("fremd", aktiv)
        self.assertIn("vibe-agent", aktiv)
        self.assertIn("tester", aktiv)
        modelle = stored.get("modelle") or {}
        self.assertNotIn("fremd", modelle)
        self.assertEqual(modelle.get("tester"), "opencode/behalt")

    def test_without_agents_file_the_default_selection_stays_active(self):
        url = self.seed_bare("ohne-farbe", {"README.md": "Inhalt\n"})

        self.checkout(url)

        path = self.workspace / "ohne-farbe" / ".vibe" / "agents.json"
        if path.exists():
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(sorted(stored["aktiv"]), ["vibe-agent"])
            self.assertEqual(stored.get("modelle") or {}, {})
        else:
            with mock.patch.object(self.cli, "models_list", return_value=[]):
                rows = self.cli.project_agent_rows("ohne-farbe")
            konfiguriert = sorted(row["name"] for row in rows if row.get("configured"))
            # AP2-Korbat: Die opencode-eigenen Agenten general/explore sind
            # standardmäßig aktiv, aber keine Startagenten.
            self.assertEqual(konfiguriert, ["explore", "general", "vibe-agent"])

    def test_the_summary_names_the_removed_agents(self):
        url = self.url_with_agents_config(
            aktiv=["vibe-agent", "fremd", "tester"],
            modelle={"fremd": "x/fremd", "tester": "opencode/behalt"},
        )

        _found, summary = self.checkout(url)

        self.assertIn("fremd", summary)


# ============================================================== Fehlerfälle
class ErrorCaseTest(StorageFixture):
    """AK4: Fehler verständlich; kein halb angelegtes Projekt."""

    def test_an_invalid_url_is_rejected_with_a_clear_error(self):
        exception = self.expect_error("://kaputt")

        self.assertIsInstance(exception, ValueError, type(exception))
        self.assertIn("Remote-Adresse", str(exception))

    def test_an_invalid_name_is_rejected_with_a_clear_error(self):
        url = self.seed_bare("urform", {"README.md": "Inhalt\n"})

        exception = self.expect_error(url, name="Falscher Name!")

        self.assertIn("Name", str(exception))

    def test_an_existing_project_name_is_rejected_without_changes(self):
        url = self.seed_bare("anderware", {"README.md": "Inhalt\n"})
        existing = self.workspace / "belegt"
        (existing / ".vibe").mkdir(parents=True)
        (existing / ".git").mkdir()
        env_text = "TYPE=generic\nTESTER=eigener-tester\n"
        (existing / ".vibe" / "project.env").write_text(env_text, encoding="utf-8")
        self.cli._pm.clear()

        exception = self.expect_error(url, name="belegt")

        self.assertIn("belegt", str(exception))
        self.assertEqual(
            self.project_env_path("belegt").read_text(encoding="utf-8"), env_text
        )
        self.assertNotIn("anderware", self.cli.projects())
        self.assertFalse((existing / "README.md").exists())

    def test_an_existing_target_folder_rejects_the_checkout(self):
        url = self.seed_bare("lagerhaus", {"README.md": "Inhalt\n"})
        folder = self.workspace / "brotdose"
        folder.mkdir()
        (folder / "markierungsdatei").write_text("bleibt\n", encoding="utf-8")

        exception = self.expect_error(url, name="brotdose")

        self.assertIn("brotdose", str(exception))
        self.assertEqual(
            (folder / "markierungsdatei").read_text(encoding="utf-8"), "bleibt\n"
        )
        self.assertFalse((folder / ".git").exists())

    def test_an_adoption_failure_removes_the_target_folder_and_reports_the_reason(self):
        """Scheitert die lokale Übernahme nach dem Clone, bleibt kein halbes
        Projekt zurück; die Meldung benennt die Ursache."""
        url = self.seed_bare("scheiteruebernahme", {"README.md": "scheitert\n"})

        with mock.patch.object(self.cli, "copy_tree",
                               side_effect=OSError("gesperrt")):
            exception = self.expect_error(url)

        self.assertIsInstance(exception, ValueError, type(exception))
        self.assertIn("Übernahme fehlgeschlagen", str(exception))
        self.assertIn("gesperrt", str(exception))
        self.assertFalse((self.workspace / "scheiteruebernahme").exists())
        self.assertNotIn("scheiteruebernahme", self.cli.projects())

    def test_a_failed_clone_leaves_no_project_folder(self):
        url = "file://" + str(self.bare_path("nicht-da"))

        exception = self.expect_error(url)

        self.assertTrue(str(exception).strip())
        self.assertFalse((self.workspace / "nicht-da").exists())
        self.assertEqual(self.cli.projects(), [])

    def test_a_missing_git_command_is_reported_without_a_project_folder(self):
        url = self.seed_bare("machtzeit", {"README.md": "Inhalt\n"})
        empty_bin = self.root / "ohnegit"
        empty_bin.mkdir()

        with mock.patch.dict(os.environ, {"PATH": str(empty_bin)}):
            exception = self.expect_error(url)

        self.assertIn("git", str(exception).lower())
        self.assertFalse((self.workspace / "machtzeit").exists())
        self.assertEqual(self.cli.projects(), [])


class CloneBehaviorTest(StorageFixture):
    """``vibe_github.clone`` direkt: Argumentliste, kein Restzustand."""

    def test_clone_copies_the_repository_to_the_target(self):
        url = self.seed_bare("ladefinger", {"README.md": "Ladewerk\n"})
        target = self.workspace / "ladefinger"

        rc, message = self.cli.vibe_github.clone(url, target)

        self.assertEqual(rc, 0, message)
        self.assertTrue((target / ".git").is_dir())
        self.assertEqual((target / "README.md").read_text(encoding="utf-8"),
                         "Ladewerk\n")

    def test_clone_reports_a_failed_source_without_a_project_folder(self):
        url = "file://" + str(self.bare_path("leer"))
        target = self.workspace / "leer"

        rc, message = self.cli.vibe_github.clone(url, target)

        self.assertNotEqual(rc, 0)
        self.assertTrue(str(message).strip())
        self.assertFalse(target.exists())

    def test_clone_runs_without_a_shell(self):
        """Die URL wird als ein Argument übergeben: ein in der URL
        versteckter Shell-Befehl wird nicht ausgeführt (Marker bleibt weg)."""
        marker = self.root / "shell-marker"
        url = "file://rueckweg; touch " + str(marker) + " #"
        target = self.workspace / "betrug"

        rc, _message = self.cli.vibe_github.clone(url, target)

        self.assertNotEqual(rc, 0)
        self.assertFalse(marker.exists(), "URL wurde über eine Shell ausgeführt")
        self.assertFalse(target.exists())


class CredentialMaskingTest(StorageFixture):
    """Meldungen dürfen eingebettete Zugangsdaten nicht weitergeben."""

    def test_mask_embedded_credentials_masks_all_urls_and_keeps_plain_ones(self):
        """Mehrzeilige Git-Ausgaben: Zugangsdaten in allen URLs werden zu
        ``***@`` ersetzt; Adressen ohne Zugangsdaten bleiben unverändert."""
        mask = self.cli.vibe_github.mask_embedded_credentials
        text = (
            "fatal: unable to access 'https://nutzer:geheim@github.com/owner/repo.git/'\n"
            "weitere Zeile: https://person:brief@github.com/anderes/repo.git und\n"
            "nur Anmeldung: https://klartext@github.com/ohne/pass.git, aber\n"
            "klar bleibt: https://github.com/owner/plain.git"
        )

        masked = mask(text)

        for geheim in ("geheim", "nutzer:geheim", "person:brief", "brief@", "klartext@"):
            self.assertNotIn(geheim, masked, geheim)
        self.assertEqual(masked.count("***@github.com"), 3)
        self.assertIn("https://github.com/owner/plain.git", masked)
        self.assertIn("fatal: unable to access", masked)
        # Erneutes Maskieren ändert nichts mehr (Idempotenz).
        self.assertEqual(mask(masked), masked)

    def test_clone_masks_embedded_credentials_in_its_message(self):
        """``clone`` gibt Fehlermeldungen von Git nur maskiert weiter; der
        Hinweis auf fehlende Zugangsdaten bleibt erhalten."""
        url = "https://nutzer:geheim@github.com/owner/repo.git"
        target = self.workspace / "maskprobe"

        with mock.patch.object(
            self.cli.vibe_github, "git",
            side_effect=lambda *_args, **_kwargs: (
                128,
                "fatal: unable to access '" + url + "/': could not read "
                "Username for 'https://github.com': Terminal prompts disabled",
            ),
        ) as standin:
            rc, message = self.cli.vibe_github.clone(url, target)

        standin.assert_called_once()
        self.assertNotEqual(rc, 0)
        self.assertNotIn("geheim", message)
        self.assertNotIn("nutzer:", message)
        self.assertIn("***@github.com", message)
        self.assertIn("Zugangsdaten", message)

    def test_clone_failure_without_a_live_service_leaks_no_credentials(self):
        """Echter Ausfallpfad (nur Loopback, kein externer Dienst): die
        Meldung trägt keine Zugangsdaten und es bleibt kein Zielordner."""
        url = "https://nutzer:geheim@127.0.0.1:1/owner/repo.git"
        target = self.workspace / "loopbackprobe"

        rc, message = self.cli.vibe_github.clone(url, target)

        self.assertNotEqual(rc, 0)
        self.assertNotIn("geheim", message)
        self.assertNotIn("nutzer:", message)
        self.assertFalse(target.exists())


# ==================================================================== CLI
def write_cli_templates(install):
    """Vorlagen für Subprozessläufe: TPL liegt unter VIBE_INSTALL/templates."""
    write_checkout_templates(install, "common", {
        "FEEDBACK.md": FEEDBACK_TEMPLATE,
        "TICKETS.md": TICKETS_TEMPLATE,
        "opencode.json": OPENCODE_JSON_TEMPLATE,
        ".opencode/agents/test-agent.md": TEST_AGENT_TEMPLATE,
    })
    write_checkout_templates(install, "generic", {
        "AGENTS.md": "# AGENTS fuer {{NAME}}\n",
        ".vibe/project.env": (
            "TYPE=generic\n"
            "REVIEWER=" + LOKALE_REVIEWER + "\n"
            "TESTER=test-agent\n"
            "SANDBOX=" + LOKALE_SANDBOX + "\n"
            "VERIFY_QUICK=" + LOKALE_QUICK + "\n"
            "VERIFY_PACKAGE=" + LOKALE_PAKET + "\n"
            "VERIFY_FULL=" + LOKALE_FULL + "\n"
        ),
    })


class CommandLineTest(unittest.TestCase):
    """CLI ``vibe clone <url> [name]``: Erfolg meldet klar, Fehler bricht ab."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workspace = self.root / "ws"
        self.workspace.mkdir()
        self.home = self.root / "home"
        self.home.mkdir()
        self.install = self.root / "_toolchain"
        self.install.mkdir()
        self.runtime = self.root / "_logs"
        self.runtime.mkdir()
        write_cli_templates(self.install / "templates")

    def isolated_env(self):
        env = {key: value for key, value in os.environ.items()
               if key not in ISOLATED_ENV}
        env.update({
            "VIBE": str(self.workspace),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(self.home),
            "VIBE_INSTALL": str(self.install),
            "VIBE_STATE": str(self.install),
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_AGENTS_DIR": str(self.home / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(self.home / ".config" / "vibe" / "config.json"),
        })
        env.update(GIT_IDENTITY)
        return env

    def seed_bare(self, name, files):
        work = self.root / "seed" / name
        work.mkdir(parents=True)
        for relative, content in files.items():
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        git(work, "init", "-q", "-b", "main")
        git(work, "add", "-A")
        git(work, "commit", "-q", "-m", "seed")
        bare = self.root / "origin" / (name + ".git")
        bare.mkdir(parents=True)
        git(bare, "init", "-q", "--bare")
        git(work, "push", "-q", str(bare), "main")
        git(bare, "symbolic-ref", "HEAD", "refs/heads/main")
        return "file://" + str(bare)

    def run_cli(self, *argv, env=None):
        return subprocess.run(
            [sys.executable, str(CLI), "clone", *argv],
            cwd=str(self.workspace), env=env or self.isolated_env(),
            capture_output=True, text=True, timeout=120, check=False,
        )

    def test_cli_clone_prints_a_summary_and_creates_the_project(self):
        url = self.seed_bare("scriptor", {"README.md": "Scriptor\n"})

        result = self.run_cli(url)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = result.stdout + result.stderr
        self.assertIn("scriptor", output)
        self.assertTrue((self.workspace / "scriptor" / ".git").is_dir())
        env_text = (self.workspace / "scriptor" / ".vibe" / "project.env").read_text(
            encoding="utf-8"
        )
        self.assertIn("TESTER=test-agent", env_text)

    def test_cli_clone_rejects_invalid_urls_and_existing_names(self):
        bad = self.run_cli("://kaputt")
        self.assertNotEqual(bad.returncode, 0)
        self.assertTrue((bad.stdout + bad.stderr).strip())

        url = self.seed_bare("ontoform", {"README.md": "ontoform\n"})
        existing = self.workspace / "belegt"
        (existing / ".vibe").mkdir(parents=True)
        (existing / ".git").mkdir()
        (existing / ".vibe" / "project.env").write_text("TYPE=generic\n",
                                                        encoding="utf-8")
        reused = self.run_cli(url, "belegt")
        self.assertNotEqual(reused.returncode, 0)
        self.assertIn("belegt", reused.stdout + reused.stderr)
        self.assertFalse((existing / "README.md").exists())
        self.assertFalse((self.workspace / "ontoform").exists())

    def test_cli_clone_reports_a_missing_git(self):
        url = self.seed_bare("ohnewerkzeug", {"README.md": "ohnewerkzeug\n"})
        empty_bin = self.root / "leck"
        empty_bin.mkdir()
        env = self.isolated_env()
        # Kein git im Suchpfad: nur ein leeres Verzeichnis statt PATH sperrt
        # git zuverlässig, ohne Unix-Rechte anzunehmen.
        env["PATH"] = str(empty_bin)

        result = self.run_cli(url, env=env)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("git", (result.stdout + result.stderr).lower())
        self.assertFalse((self.workspace / "ohnewerkzeug").exists())


# ===========================================================================
# C1–C5: Test-Agent-Meldung bei ``init`` und ``adopt``
# ===========================================================================

import contextlib
import importlib.machinery
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path


TEST_AGENT_PATH = ".opencode/agents/test-agent.md"


def load_cli_ap5(vibe_root, home):
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


def write_init_template(templates, typ, files):
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
        self.cli = load_cli_ap5(self.workspace, self.home)
        write_init_template(
            self.templates,
            "common",
            {
                "FEEDBACK.md": "# FEEDBACK aus der Vorlage\n",
                "TICKETS.md": "# TICKETS\n",
            },
        )
        write_init_template(
            self.templates,
            "generic",
            {
                "AGENTS.md": "# AGENTS fuer {{NAME}}\n\n",
                ".vibe/project.env": "TYPE=generic\n",
            },
        )
        self.cli.TPL = str(self.templates)

    def add_test_agent_template(self, content=None):
        """Legt die optionale Test-Agent-Vorlage in ``templates/common`` an."""
        write_init_template(
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


# ===========================================================================
# Vertragstests für Gerüst,.gitignore, Vorlagen und Guide
# ===========================================================================

import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.unit import env_support

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

    def test_cmd_new_copies_the_template_without_a_rules_block(self):
        """GH-76: ``vibe new`` fügt keinen verwalteten Block mehr ein.

        Vor: leeres VIBE. Aktion: ``vibe new p2 generic``. Erwartet:
        AGENTS.md entspricht der Typ-Vorlage mit ersetztem Namen und enthält
        weder Marker noch deutschen Regeltext. Fehlerfall: injizierter Block
        oder veränderter Vorlageninhalt.
        """
        result = self.run_cli("new", "p2", "generic")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        text = (self.root / "p2" / "AGENTS.md").read_text(encoding="utf-8")
        template = (TEMPLATES / "generic" / "AGENTS.md").read_text(
            encoding="utf-8")
        self.assertEqual(template.replace("{{NAME}}", "p2"), text)
        self.assertNotIn(MARK, text)
        self.assertNotIn(END, text)
        self.assertNotIn("Projektordner sauber halten", text)

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
    """Vorlagen ohne den früheren deutschen Regelblock (GH-76)."""

    def test_common_templates_no_longer_contain_the_markdown_ledgers(self):
        """Vor: templates/common. Aktion: Verzeichnis lesen.
        Erwartet: TICKETS.md und FEEDBACK.md fehlen."""
        names = {entry.name for entry in (TEMPLATES / "common").iterdir()}

        self.assertNotIn("TICKETS.md", names)
        self.assertNotIn("FEEDBACK.md", names)

    def test_templates_carry_no_managed_rules_block(self):
        """Vor: alle fünf Vorlagen-AGENTS.md. Aktion: Marker zählen.
        Erwartet: kein Markerpaar und kein deutscher Regeltext; das Gerüst
        kopiert die Vorlage damit unverändert ohne eingefügten Block."""
        templates = sorted(TEMPLATES.glob("*/AGENTS.md"))
        self.assertTrue(templates)
        for path in templates:
            with self.subTest(path=str(path)):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn(MARK, text)
                self.assertNotIn(END, text)
                self.assertNotIn("Projektordner sauber halten", text)

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
