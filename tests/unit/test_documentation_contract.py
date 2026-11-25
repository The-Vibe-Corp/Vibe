"""Dokumentationsvertrag: SPEC-/AGENTS-Verweise und Plattformanweisungen.

Aufruf: python3 -m unittest tests.unit.test_documentation_contract -v
"""


# ===========================================================================
# (Regeln/SPEC): T-I1
# ===========================================================================

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GITHUB_MODULE = REPO / "bin" / "vibe_github.py"
HARNESS = REPO / "bin" / "vibe_harness.py"
SPEC = REPO / "SPEC.md"

OLD_SPEC_HEADINGS = (
    "## Git Workflow & Branch Rules (Strictly Enforced)",
    "## Git&GitHub Workflow & Branch Rules (Strictly Enforced)",
)

# Die drei Runner-Merge-Aussagen der englischen SPEC (Abschnitt
# "Work packages and feedback").
RUNNER_MERGE_STATEMENTS = (
    "In GitHub mode, the runner fetches the current integration state and "
    "merges it into the feature branch before pushing. Conflicts are "
    "resolved in the package worktree.",
    "Without auto-merge, the runner opens a PR and waits for manual merge "
    "and closure confirmation. The worktree remains registered in the "
    "meantime.",
    "With auto-merge enabled, the runner may squash-merge the approved PR "
    "after all gates pass. Final synchronization and cleanup follow "
    "confirmed merge.",
)


class SpecCanonicalTest(unittest.TestCase):
    """AK T-I1: eine kanonische SPEC-Quelle ohne widersprüchliche Blöcke."""

    def setUp(self):
        self.text = SPEC.read_text(encoding="utf-8")

    def test_both_old_strictly_enforced_sections_are_gone(self):
        """Vorbedingung: ``SPEC.md``.
        Aktion: die beiden alten Git-Überschriften suchen.
        Erwartung: keine ist mehr vorhanden; „Strictly Enforced“ kommt nicht
        mehr vor.
        Fehlerfall: einer der widersprüchlichen Blöcke bleibt stehen.
        """
        for heading in OLD_SPEC_HEADINGS:
            self.assertNotIn(heading, self.text, heading)
        self.assertNotIn("Strictly Enforced", self.text)

    def test_spec_has_no_separate_git_section(self):
        """Vorbedingung: ``SPEC.md``.
        Aktion: Überschriften und die Runner-Merge-Aussagen lesen.
        Erwartung: keine ``## ``-Überschrift nennt Git; der GitHub-Modus,
        der PR-Standard und der bestätigte Auto-Merge sind als
        Produktverhalten formuliert.
        Fehlerfall: eigener Git-Abschnitt oder fehlende Merge-Aussagen.
        """
        headings = [line for line in self.text.splitlines()
                    if line.startswith("## ") and "Git" in line]
        self.assertEqual([], headings, headings)
        for statement in RUNNER_MERGE_STATEMENTS:
            self.assertIn(statement, self.text)

    def test_platform_instructions_own_runner_actions_and_conflict_repair(self):
        """Vorbedingung: ``bin/vibe_harness.py``.
        Aktion: die englische Plattformanweisung lesen.
        Erwartung: der Runner besitzt Worktrees, Branches, Integration, Push,
        PR und Merge; Konflikte werden im Paket-Worktree fortgesetzt, ohne
        zweiten Merge, Abort, Rebase oder pauschale Seitenwahl.
        Fehlerfall: Agentenseitige Git-Aktionen bleiben erlaubt oder der
        Konfliktweg fehlt.
        """
        text = HARNESS.read_text(encoding="utf-8")
        self.assertIn(
            "The runner owns worktrees, branches, integration, push, "
            "PR creation, merge, and cleanup. Do not perform those actions "
            "yourself.",
            text,
        )
        for fragment in ("continue that merge",
                         "Do not start another merge, abort",
                         "rebase",
                         "choose one side wholesale"):
            self.assertIn(fragment, text, "Konfliktweg fehlt: %r" % fragment)

    def test_spec_documents_pr_only_default_and_opt_in_auto_merge(self):
        """Vorbedingung: ``SPEC.md``.
        Aktion: Aussagen zum Merge-Verhalten lesen.
        Erwartung: ohne Auto-Merge bleibt der PR manuell und der Worktree
        registriert; mit Auto-Merge ist der Squash-Merge nach allen Gates
        erlaubt; „Out of scope“ verlangt den konfigurierten Opt-in.
        Fehlerfall: Standard oder Opt-in-Bedingung fehlen.
        """
        self.assertIn(
            "Without auto-merge, the runner opens a PR and waits for manual "
            "merge and closure confirmation.",
            self.text,
        )
        self.assertIn("The worktree remains registered in the meantime.",
                      self.text)
        self.assertIn(
            "With auto-merge enabled, the runner may squash-merge the "
            "approved PR after all gates pass.",
            self.text,
        )
        self.assertIn("Automatic GitHub merge requires the configured opt-in.",
                      self.text)

    def test_no_agent_side_squash_merge_or_force_delete_remains(self):
        """Vorbedingung: ``SPEC.md``.
        Aktion: verbotene Agentenkommandos suchen.
        Erwartung: ``gh pr merge --squash --delete-branch`` und
        ``git branch -D`` kommen nicht mehr vor.
        Fehlerfall: Agentenauftrag enthält weiterhin Merge/Force-Delete.
        """
        self.assertNotIn("gh pr merge --squash --delete-branch", self.text)
        self.assertNotIn("git branch -D", self.text)

    def test_out_of_scope_line_names_authorization_and_auto_merge(self):
        """Vorbedingung: Abschnitt „Out of scope“.
        Aktion: die alte deutsche Zeile und die englische Formulierung suchen.
        Erwartung: Die alte Zeile ohne Freigabebezug ist weg; die englische
        Zeile nennt die Freigabe und den konfigurierten Auto-Merge-Opt-in.
        Fehlerfall: unveränderte alte Aussage oder fehlender Opt-in-Bezug.
        """
        old = ("- Automatische Veröffentlichung, Push, Merge oder Release "
               "ohne Freigabe.")
        self.assertNotIn(old, self.text)
        self.assertIn(
            "- Automatic publication, push, merge, or release without "
            "authorization.",
            self.text,
        )
        self.assertIn("Automatic GitHub merge requires the configured opt-in.",
                      self.text)

    def test_github_module_docstring_describes_auto_merge(self):
        """Vorbedingung: ``bin/vibe_github.py``.
        Aktion: Modul-Docstring/Quelltext lesen.
        Erwartung: „Das Zusammenführen selbst bleibt manuell.“ ist ersetzt;
        ``GITHUB_AUTO_MERGE`` wird als Ausnahme genannt.
        Fehlerfall: veraltete Aussage bleibt stehen.
        """
        text = GITHUB_MODULE.read_text(encoding="utf-8")
        self.assertNotIn("Das Zusammenführen selbst bleibt manuell.", text)
        self.assertIn("GITHUB_AUTO_MERGE", text)


# ===========================================================================
# Hidden platform instructions for runner-managed agent work
# ===========================================================================

import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.unit import env_support

CLI = REPO / "bin" / "vibe"
TEMPLATES = REPO / "templates"
AGENTS = REPO / "AGENTS.md"
BASELINE_DOC = REPO / "docs" / "verification-baselines.md"

MARK_START = "<!-- vibe:general-rules -->"
MARK_END = "<!-- /vibe:general-rules -->"
PLATFORM_FILENAME = "platform_instructions.md"

# The title heading plus the four section headings from the ticket's
# platform suggestion.
SECTION_HEADINGS = (
    "## Vibe platform instructions",
    "### Workspace and checks",
    "### Package evidence and review",
    "### Commit and ticket handoff",
    "### Runner-owned Git operations",
)

# Meaningful, stable fragments the platform text must keep: the verdict gate,
# review file name, ticket handoff file/fields and the runner-owned Git rule.
PLATFORM_FRAGMENTS = (
    "Verdict: PASS",
    "Verdict: CHANGES REQUIRED",
    "docs/reviews/<ID>-review-<round>.md",
    "TICKET-<ID>.json",
    "`state`",
    "`commit`",
    "`test`",
    "The runner owns worktrees, branches, integration, push, PR creation, "
    "merge, and cleanup.",
    "Do not perform those actions yourself.",
    "continue that merge",
    "Do not start another merge, abort, rebase, or choose one side wholesale.",
    "commits with a subject starting `<ID>:`",
)

GERMAN_RULE_HEADINGS = (
    "Projektordner sauber halten",
    "Ordnung im Git halten",
    "Ticketabschluss (verbindlich)",
    "Laufende Instanz nicht verändern (verbindlich)",
    "Effizienz der Prüfungen (verbindlich)",
    "Leitlinien für Coding-Agenten (verbindlich)",
    "Unabhängiger Test-Agent (verbindlich)",
)

# Each template must still carry its own project-type instructions.
TYPE_SPECIFIC_FRAGMENTS = {
    "generic": ("SPEC.md ist maßgeblich", "VERIFY_QUICK"),
    "web": ("Node/npm", "npm test", "Screenshot"),
    "android": ("gradlew testDebugUnitTest", "emulator-start.sh"),
    "docker": ("compose", "Server und Client"),
    "rebuild": ("REBUILD_REQUIRED_GROUPS", "Paritätsmatrix"),
}


def symlink_supported():
    """Probe whether this filesystem allows symlinks (FUSE/NTFS may not)."""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "probe-link"
            os.symlink("probe-target", link)
            if not link.is_symlink():
                return False
            os.remove(link)
    except (OSError, NotImplementedError):
        return False
    return True


SYMLINKS_SUPPORTED = symlink_supported()


def load_cli(vibe_root, home):
    """Load ``bin/vibe`` with isolated VIBE/HOME (no main())."""
    with env_support.isolated_process_environment(
        VIBE=str(vibe_root),
        VIBE_NO_CONTAINER="1",
        HOME=str(home),
        VIBE_STATE=str(vibe_root / "_toolchain"),
        VIBE_RUNTIME=str(vibe_root / "_logs"),
        VIBE_CONFIG_FILE=str(home / "vibe.json"),
        VIBE_STORAGE_LOCK_DIR=str(vibe_root / "locks"),
    ):
        loader = importlib.machinery.SourceFileLoader(
            "vibe_gh76_platform_under_test", str(CLI))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module


class PlatformFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.state = self.root / "state"
        self.state.mkdir()
        self.cli = load_cli(self.root, self.home)

    def environment(self, extra=None):
        env = env_support.isolated_environ(
            VIBE=str(self.root),
            VIBE_INSTALL=str(REPO),
            VIBE_NO_CONTAINER="1",
            HOME=str(self.home),
            VIBE_STATE=str(self.state),
            VIBE_RUNTIME=str(self.root / "_logs"),
            VIBE_CONFIG_FILE=str(self.home / "vibe.json"),
            VIBE_STORAGE_LOCK_DIR=str(self.root / "locks"),
        )
        if extra:
            env.update({key: str(value) for key, value in extra.items()})
        return env

    def run_platform(self, directory, extra_env=None):
        return subprocess.run(
            [sys.executable, str(CLI), "platform-instructions",
             "--directory", str(directory)],
            cwd=str(self.root),
            env=self.environment(extra_env),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def written_path(self):
        return self.state / PLATFORM_FILENAME


class PlatformInstructionsCommandTest(PlatformFixture):
    """Acceptance D and F: the subcommand, its text and its write safety."""

    def test_writes_the_ticket_platform_text_and_prints_its_absolute_path(self):
        """Precondition: empty state directory.
        Action: ``vibe platform-instructions --directory <state>``.
        Expected: exit 0; the last stdout line is the absolute path
        ``<state>/platform_instructions.md``; the file exists and contains
        the five headings in SECTION_HEADINGS plus the stable runner-facing
        fragments; no XML/general-rules marker and no German general-rules
        heading.
        Failure: missing command/file, relative path, wrong or stale text.
        """
        result = self.run_platform(self.state)

        self.assertEqual(0, result.returncode,
                         result.stdout + result.stderr)
        path = self.written_path()
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        self.assertTrue(lines, "Kein Pfad auf stdout: " + repr(result.stdout))
        self.assertEqual(str(path), lines[-1].strip())
        self.assertTrue(path.is_file(), "platform_instructions.md fehlt")
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(SECTION_HEADINGS[0] + "\n"), text[:80])
        for heading in SECTION_HEADINGS:
            self.assertIn(heading, text)
        for fragment in PLATFORM_FRAGMENTS:
            self.assertIn(fragment, text, "Plattformtext-Fragment fehlt: "
                          + repr(fragment))
        self.assertNotIn(MARK_START, text)
        self.assertNotIn(MARK_END, text)
        self.assertNotIn("vibe:general-rules", text)
        self.assertNotIn("<!--", text, "XML-Quotationsmarker im Plattformtext")
        for heading in GERMAN_RULE_HEADINGS:
            self.assertNotIn(heading, text,
                             "Deutsche Regelüberschrift im Plattformtext")

    def test_refreshes_an_existing_file_idempotently(self):
        """Precondition: a previous platform file (then tampered with).
        Action: run the subcommand twice, between them replace the file.
        Expected: both runs exit 0, both print the same path, the second run
        restores exactly the first content (no duplication, no append).
        Failure: append-only write, stale content or a second file.
        """
        first = self.run_platform(self.state)
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        original = self.written_path().read_bytes()

        self.written_path().write_text("tampered\n", encoding="utf-8")
        second = self.run_platform(self.state)

        self.assertEqual(0, second.returncode, second.stdout + second.stderr)
        self.assertEqual(str(self.written_path()),
                         second.stdout.strip().splitlines()[-1])
        self.assertEqual(original, self.written_path().read_bytes())
        self.assertEqual(1, len(list(self.state.glob("platform_instructions*"))))

    def test_platform_constant_matches_the_written_file_without_markers(self):
        """Precondition: ``bin/vibe`` exposes ``PLATFORM_INSTRUCTIONS``.
        Action: compare the constant with the subcommand's file.
        Expected: byte-identical text; the constant carries no marker pair.
        Failure: two drifting sources or markers in the platform text.
        """
        result = self.run_platform(self.state)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        written = self.written_path().read_text(encoding="utf-8")
        self.assertTrue(hasattr(self.cli, "PLATFORM_INSTRUCTIONS"),
                        "bin/vibe.PLATFORM_INSTRUCTIONS fehlt")
        self.assertEqual(written, self.cli.PLATFORM_INSTRUCTIONS)
        self.assertNotIn(MARK_START, self.cli.PLATFORM_INSTRUCTIONS)
        self.assertNotIn(MARK_END, self.cli.PLATFORM_INSTRUCTIONS)

    @unittest.skipUnless(SYMLINKS_SUPPORTED,
                         "os.symlink funktioniert in der Prüfumgebung nicht")
    def test_refuses_to_follow_a_symlinked_destination(self):
        """Precondition: the destination is a symlink to an outside file.
        Action: run the subcommand.
        Expected: non-zero exit; the link target stays byte-identical and the
        destination remains a symlink (nothing is written through it).
        Failure: following the link and overwriting an outside file.
        """
        outside = self.root / "outside.md"
        outside.write_text("fremd\n", encoding="utf-8")
        link = self.written_path()
        os.symlink(outside, link)
        self.assertTrue(link.is_symlink())

        result = self.run_platform(self.state)

        self.assertNotEqual(0, result.returncode,
                            "Symlink wurde als Ziel akzeptiert: "
                            + result.stdout + result.stderr)
        self.assertTrue(link.is_symlink(), "Der Symlink wurde ersetzt")
        self.assertEqual("fremd\n", outside.read_text(encoding="utf-8"))
        self.assertIn("Symlink", result.stdout + result.stderr)

    def test_does_not_touch_a_project_agents_file_or_the_global_config(self):
        """Precondition: a project AGENTS.md and a global opencode config
        exist with sentinel content.
        Action: write the platform file into the state directory.
        Expected: both sentinels stay byte-identical; the platform file lies
        outside the project and outside ``$HOME/.config/opencode``.
        Failure: the new path writes into a project or personal config.
        """
        project = self.root / "proj"
        project.mkdir()
        agents = project / "AGENTS.md"
        agents.write_text("# Projektregel\n", encoding="utf-8")
        global_dir = self.home / ".config" / "opencode"
        global_dir.mkdir(parents=True)
        global_config = global_dir / "opencode.json"
        global_config.write_text('{"theme": "dark"}\n', encoding="utf-8")
        agents_before = agents.read_bytes()
        global_before = global_config.read_bytes()

        result = self.run_platform(self.state)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(agents_before, agents.read_bytes())
        self.assertEqual(global_before, global_config.read_bytes())
        path = Path(result.stdout.strip().splitlines()[-1])
        self.assertEqual(self.state.resolve(), path.parent.resolve())
        self.assertNotEqual(project.resolve(), path.parent.resolve())
        self.assertNotEqual(global_dir.resolve(), path.parent.resolve())
        self.assertFalse(str(path).startswith(str(project.resolve()) + os.sep))


class TemplatesWithoutManagedRulesTest(unittest.TestCase):
    """Acceptance A: templates keep only their type-specific content."""

    def test_all_templates_drop_the_german_general_rules(self):
        """Precondition: all five shipped ``templates/*/AGENTS.md``.
        Action: read each file.
        Expected: no managed marker pair, no German general-rules heading.
        Failure: one template still carries the old mandatory block.
        """
        templates = sorted(TEMPLATES.glob("*/AGENTS.md"))
        self.assertEqual(5, len(templates), templates)
        for path in templates:
            with self.subTest(path=str(path)):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn(MARK_START, text)
                self.assertNotIn(MARK_END, text)
                self.assertNotIn("vibe:general-rules", text)
                for heading in GERMAN_RULE_HEADINGS:
                    self.assertNotIn(heading, text,
                                     "%s enthält noch %r" % (path, heading))

    def test_templates_keep_their_type_specific_content(self):
        """Precondition: the five templates.
        Action: look for type-specific project instructions.
        Expected: each template starts with its ``# Projekt: {{NAME}}``
        header and keeps the distinctive content of its type.
        Failure: removing the block also removed useful template content.
        """
        for kind, fragments in TYPE_SPECIFIC_FRAGMENTS.items():
            path = TEMPLATES / kind / "AGENTS.md"
            text = path.read_text(encoding="utf-8")
            with self.subTest(kind=kind):
                self.assertTrue(text.startswith("# Projekt: {{NAME}}"),
                                "%s: Projektkopf fehlt" % path)
                for fragment in fragments:
                    self.assertIn(fragment, text,
                                  "%s: Typhinweis fehlt: %r"
                                  % (path, fragment))


class AgentsMdReferenceTest(unittest.TestCase):
    """Acceptance G: the repository AGENTS.md links the real baseline doc."""

    def test_agents_md_references_the_hyphen_baseline_document(self):
        """Precondition: repository ``AGENTS.md`` and ``docs/``.
        Action: inspect the baseline reference.
        Expected: ``docs/verification-baselines.md`` is named and the older
        underscore variant is gone; the referenced file exists.
        Failure: a stale path stays or the document is missing.
        """
        text = AGENTS.read_text(encoding="utf-8")
        self.assertIn("docs/verification-baselines.md", text)
        self.assertNotIn("docs/verification_baselines.md", text)
        self.assertTrue(BASELINE_DOC.is_file(),
                        "docs/verification-baselines.md fehlt")


def _instruction_paths(node):
    """Collect all ``instructions`` list entries from a config document tree."""
    found = []
    if isinstance(node, dict):
        instructions = node.get("instructions")
        if isinstance(instructions, list):
            found.extend(item for item in instructions
                         if isinstance(item, str))
        for value in node.values():
            found.extend(_instruction_paths(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_instruction_paths(value))
    return found


class OpencodeInstructionDiscoveryTest(PlatformFixture):
    """Acceptance E: opencode resolves the written file from inline config."""

    @staticmethod
    def opencode_env(home):
        env = env_support.isolated_environ()
        env.update({
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_STATE_HOME": str(home / ".local" / "state"),
        })
        env.pop("OPENCODE_CONFIG_CONTENT", None)
        env.pop("OPENCODE_PASSWORD", None)
        env.pop("OPENCODE_SERVER_PASSWORD", None)
        return env

    def read_config(self, config_content, workdir, home):
        env = self.opencode_env(home)
        if config_content is not None:
            env["OPENCODE_CONFIG_CONTENT"] = config_content
        return subprocess.run(
            ["opencode", "api", "get", "/api/config", "--standalone"],
            cwd=str(workdir),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
        )

    @unittest.skipUnless(shutil.which("opencode"),
                         "opencode ist in der Prüfumgebung nicht verfügbar")
    def test_written_file_is_discovered_as_an_instructions_entry(self):
        """Precondition: opencode binary available; platform file written.
        Action: start a throwaway private loopback server with
        ``OPENCODE_CONFIG_CONTENT={"instructions":[<path>]}`` and read
        ``/api/config``. Expected: the absolute platform path appears in an
        ``instructions`` list. No model call, no shared/running server.
        Failure: opencode ignores the inline instructions entry.
        """
        result = self.run_platform(self.state)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        path = str(self.written_path())
        workdir = self.root / "opencode-work"
        workdir.mkdir()
        home = self.root / "opencode-home"
        home.mkdir()

        baseline = self.read_config(None, workdir, home)
        if baseline.returncode != 0:
            self.skipTest(
                "opencode standalone server in dieser Umgebung nicht nutzbar: "
                + (baseline.stderr or baseline.stdout)[-500:])

        configured = self.read_config(
            json.dumps({"instructions": [path]}), workdir, home)

        self.assertEqual(0, configured.returncode,
                         configured.stdout + configured.stderr)
        try:
            documents = json.loads(configured.stdout)
        except ValueError as error:
            self.fail("opencode /api/config liefert kein JSON: "
                      + str(error) + "\n" + configured.stdout[:1000])
        self.assertIn(path, _instruction_paths(documents),
                      "Die Instruktionsdatei erscheint nicht in /api/config: "
                      + configured.stdout[:2000])


if __name__ == "__main__":
    unittest.main()
