"""F27: Unterbrochenen Lauf trotz nicht committeter Änderungen neu anstoßen.

Die Tests leiten das Verhalten aus dem Arbeitspaket und ``SPEC.md`` ab, nicht
aus dem Implementierungsdiff. Geprüft werden:

* Der Preflight lässt einen unsauberen Arbeitsbaum nur mit der ausdrücklichen
  Option ``allow_dirty`` zu; ohne sie bleibt der bisherige Abbruch.
* Andere Befunde (kein Git-Repository, detached HEAD, fehlender TESTER oder
  REVIEWER, fehlende Paketprüfung) blockieren auch mit der Option.
* ``vibe run <projekt> --keep-changes`` gibt die Absicht als
  ``VIBE_KEEP_CHANGES=1`` an den Läufer weiter; ohne Option nicht.
* Der Läufer startet mit ``VIBE_KEEP_CHANGES=1`` trotz Änderungen ein Paket,
  ohne die Änderungen zu stagen, zu committen, zu stashen oder
  wiederherzustellen. Ein unsauberer Integrationsstand blockiert weiterhin die
  Gesamtprüfung.
* ``vibe`` aktualisiert den verwalteten AGENTS.md-Block nicht, wenn AGENTS.md
  nicht committete Änderungen hat, und warnt verständlich; ein sauberer Stand
  wird weiterhin aktualisiert.
* ``POST /api/run`` nimmt ``keep_changes`` an, reicht es an den Läufer weiter
  und nennt die zurückbehaltenen Dateien in der Rückmeldung.

Es werden keine Modelle, Router oder echten externen Dienste aufgerufen. Der
Agent, ``tmux`` und ``curl`` sind Attrappen; alle Pfade liegen in temporären
Verzeichnissen.
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"
WEB = BIN / "vibe-web.py"

PROJECT_ENV = """TYPE=generic
AGENT=test-agent
TESTER=test-agent
REVIEWER=code-reviewer
VERIFY_PACKAGE="true"
VERIFY_FULL="true"
"""

FEEDBACK = "- [ ] F1 Erstes Paket\n  Beschreibung: Test\n"

OLD_AGENTS = (
    "# Projekt\n\n"
    "Eigene Regel\n\n"
    "<!-- vibe:general-rules -->\n"
    "ALTER REGELSATZ\n"
    "<!-- /vibe:general-rules -->\n"
)


def load_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def load_cli(vibe_root, home):
    """Lädt ``bin/vibe`` als Modul mit isoliertem VIBE, HOME und XDG."""
    keys = (
        "VIBE",
        "VIBE_NO_CONTAINER",
        "VIBE_INSTALL",
        "VIBE_RUNTIME",
        "VIBE_STATE",
        "VIBE_AGENTS_DIR",
        "VIBE_CONFIG_FILE",
        "VIBE_CONFIG_DIR",
        "VIBE_STORAGE_LOCK_DIR",
        "HOME",
        "XDG_CONFIG_HOME",
    )
    old = {key: os.environ.get(key) for key in keys}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    os.environ["XDG_CONFIG_HOME"] = str(home / ".config")
    os.environ["VIBE_CONFIG_FILE"] = str(vibe_root / "config.json")
    os.environ["VIBE_STORAGE_LOCK_DIR"] = str(vibe_root / "locks")
    for key in (
        "VIBE_CONFIG_DIR",
        "VIBE_INSTALL",
        "VIBE_RUNTIME",
        "VIBE_STATE",
        "VIBE_AGENTS_DIR",
    ):
        os.environ.pop(key, None)
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_f27_under_test", str(CLI)
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


def module_env(root, home):
    """Isolierte Umgebung ohne persönliche VIBE-, Sandbox- oder Prüfwerte."""
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("VIBE_") or key.startswith("SANDBOX") or key in (
            "VIBE",
            "AGENT",
            "TYPE",
            "VERIFY_QUICK",
            "VERIFY_FULL",
        ):
            env.pop(key, None)
    env.update(
        {
            "VIBE": str(root),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(home),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return env


# ---------------------------------------------------------------------------
# Preflight-Modul: allow_dirty
# ---------------------------------------------------------------------------
class PreflightAllowDirtyTest(unittest.TestCase):
    """Verhalten 1-3: Nur der unsaubere Arbeitsbaum ist übersteuerbar."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.packages = load_module(
            BIN / "vibe_packages.py", "vibe_packages_f27_preflight"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def make_project(self, name="proj", env_text=PROJECT_ENV):
        project = self.root / name
        support.init_repo(project)
        support.write_project(project, env_text, feedback=FEEDBACK)
        support.commit_all(project, "Ausgangsstand")
        return project

    def make_dirty(self, project, name="unfertig.txt"):
        path = project / name
        path.write_text("unfertig\n", encoding="utf-8")
        return path

    def test_dirty_tree_is_rejected_by_default_and_allowed_only_explicitly(self):
        project = self.make_project()
        self.make_dirty(project)

        default_errors = self.packages.preflight_errors(
            project, self.agents, "", ""
        )
        strict_errors = self.packages.preflight_errors(
            project, self.agents, "", "", allow_dirty=False
        )
        allowed_errors = self.packages.preflight_errors(
            project, self.agents, "", "", allow_dirty=True
        )

        for errors in (default_errors, strict_errors):
            self.assertTrue(
                any("Arbeitsbaum" in error for error in errors), errors
            )
            self.assertTrue(
                any("unfertig.txt" in error for error in errors), errors
            )
        self.assertFalse(
            any("Arbeitsbaum" in error for error in allowed_errors),
            allowed_errors,
        )
        self.assertEqual(allowed_errors, [], allowed_errors)

    def test_other_findings_still_block_with_allow_dirty(self):
        # Kein Git-Repository.
        plain = self.root / "norepo"
        (plain / ".vibe").mkdir(parents=True)
        (plain / ".vibe" / "project.env").write_text(
            PROJECT_ENV, encoding="utf-8"
        )
        self.make_dirty(plain)
        errors = self.packages.preflight_errors(
            plain, self.agents, "", "", allow_dirty=True
        )
        self.assertTrue(
            any("Kein Git-Repository" in error for error in errors), errors
        )

        # Detached HEAD.
        detached = self.make_project("detached")
        support.git(detached, "checkout", "--detach")
        self.make_dirty(detached)
        errors = self.packages.preflight_errors(
            detached, self.agents, "", "", allow_dirty=True
        )
        self.assertTrue(
            any("Detached HEAD" in error for error in errors), errors
        )
        self.assertFalse(
            any("Arbeitsbaum" in error for error in errors), errors
        )

        # Fehlender TESTER.
        no_tester = self.make_project(
            "no-tester",
            """TYPE=generic
AGENT=test-agent
REVIEWER=code-reviewer
VERIFY_PACKAGE="true"
""",
        )
        self.make_dirty(no_tester)
        errors = self.packages.preflight_errors(
            no_tester, self.agents, "", "", allow_dirty=True
        )
        self.assertTrue(any("TESTER" in error for error in errors), errors)
        self.assertFalse(
            any("Arbeitsbaum" in error for error in errors), errors
        )

        # Fehlender REVIEWER.
        no_reviewer = self.make_project(
            "no-reviewer",
            """TYPE=generic
AGENT=test-agent
TESTER=test-agent
REVIEWER=fehlt
VERIFY_PACKAGE="true"
""",
        )
        self.make_dirty(no_reviewer)
        errors = self.packages.preflight_errors(
            no_reviewer, self.agents, "", "", allow_dirty=True
        )
        self.assertTrue(any("REVIEWER" in error for error in errors), errors)
        self.assertFalse(
            any("Arbeitsbaum" in error for error in errors), errors
        )

        # Fehlende Paketprüfung.
        no_check = self.make_project(
            "no-check",
            """TYPE=generic
AGENT=test-agent
TESTER=test-agent
REVIEWER=code-reviewer
""",
        )
        self.make_dirty(no_check)
        errors = self.packages.preflight_errors(
            no_check, self.agents, "", "", allow_dirty=True
        )
        self.assertTrue(
            any("Paketprüfung fehlt" in error for error in errors), errors
        )
        self.assertFalse(
            any("Arbeitsbaum" in error for error in errors), errors
        )

    def test_assist_preflight_passes_a_dirty_tree_only_with_allow_dirty(self):
        project = self.make_project()
        self.make_dirty(project)

        strict = self.packages.assist_preflight(
            project, self.agents, "", "", runtime=None, allow_dirty=False
        )
        allowed = self.packages.assist_preflight(
            project, self.agents, "", "", runtime=None, allow_dirty=True
        )

        self.assertEqual(strict["action"], "unavailable", strict)
        self.assertTrue(
            any("Arbeitsbaum" in error for error in strict["errors"]),
            strict,
        )
        self.assertEqual(allowed["action"], "pass", allowed)
        self.assertEqual(allowed["errors"], [], allowed)


# ---------------------------------------------------------------------------
# Paket-Läufer: VIBE_KEEP_CHANGES
# ---------------------------------------------------------------------------
class RunnerFixture(unittest.TestCase):
    """Isolierter Läufer mit echtem Mini-Git-Repository."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        (self.tool_bin / "vibe").write_text(support.FAKE_VIBE, encoding="utf-8")
        (self.tool_bin / "vibe").chmod(0o755)
        self.runtime = self.root / "_logs"
        self.state = self.root / "_state"
        self.state.mkdir()
        self.calls = self.root / "calls.log"
        self.counter = self.root / "counter"
        self.fakebin = support.install_fake_tools(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def make_project(self, name="proj", env_text=PROJECT_ENV,
                     feedback=FEEDBACK):
        project = self.root / name
        support.init_repo(project)
        support.write_project(project, env_text, feedback=feedback)
        support.commit_all(project, "Ausgangsstand")
        return project

    def make_dirty(self, project, name="unfertig.txt", text="unfertig\n"):
        path = project / name
        path.write_text(text, encoding="utf-8")
        return path

    def env(self, project, **extra):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_"):
                env.pop(key, None)
        for key in (
            "AGENT",
            "MAX_PACKAGES",
            "MAX_RETRIES",
            "SANDBOX",
            "SANDBOX_TOOLS",
            "VERIFY_FULL",
            "VERIFY_PACKAGE",
        ):
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(self.root),
                "VIBE_INSTALL": str(self.install),
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_STATE": str(self.state),
                "VIBE_AGENTS_DIR": str(self.agents),
                "VIBE_LOGNAME": project.name,
                "VIBE_RETRY_DELAY": "0",
                "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
                "VIBE_STORAGE_LOCK_DIR": str(self.home / "locks"),
                "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
                "FAKE_CALLS": str(self.calls),
                "FAKE_COUNTER": str(self.counter),
                "FAKE_MODE": "complete",
            }
        )
        env.update({key: str(value) for key, value in extra.items()})
        return env

    def run_runner(self, project, **extra):
        return subprocess.run(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(project)],
            cwd=str(project),
            env=self.env(project, **extra),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def agent_calls(self):
        if not self.calls.is_file():
            return []
        return self.calls.read_text(encoding="utf-8").splitlines()

    def log(self, project):
        path = self.runtime / (project.name + ".log")
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def combined(self, result, project):
        return result.stdout + result.stderr + "\n" + self.log(project)


class RunnerKeepChangesTest(RunnerFixture):
    """Verhalten 1, 2, 3 und 6 am echten Läufer."""

    def test_runner_without_keep_changes_blocks_on_dirty_tree(self):
        project = self.make_project()
        self.make_dirty(project)

        result = self.run_runner(project)

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("Arbeitsbaum", result.stdout)
        self.assertIn("unfertig.txt", result.stdout)
        self.assertEqual(self.agent_calls(), [])

    def test_keep_changes_starts_a_package_and_preserves_changes(self):
        project = self.make_project()
        agents = project / "AGENTS.md"
        agents.write_text("Original\n", encoding="utf-8")
        support.commit_all(project, "AGENTS.md ergänzt")
        dirty = self.make_dirty(project)
        agents.write_text("Nutzernachtrag\n", encoding="utf-8")

        before_status = support.git(
            project, "status", "--porcelain=v1", "-uall",
            "--", "AGENTS.md", "unfertig.txt",
        ).stdout
        before_agents = agents.read_bytes()
        before_dirty = dirty.read_bytes()

        result = self.run_runner(
            project, VIBE_KEEP_CHANGES="1", VIBE_MAX_PACKAGES="1"
        )
        output = self.combined(result, project)

        # Der Lauf hat tatsächlich begonnen: genau ein Arbeitspaket lief.
        self.assertEqual(len(self.agent_calls()), 1, output)
        self.assertIn("Arbeitspaket F1", self.log(project))
        self.assertIn("Geschlossen: F1", result.stdout)

        # Die vorhandenen Änderungen bleiben unverändert.
        after_status = support.git(
            project, "status", "--porcelain=v1", "-uall",
            "--", "AGENTS.md", "unfertig.txt",
        ).stdout
        self.assertEqual(after_status, before_status)
        self.assertEqual(agents.read_bytes(), before_agents)
        self.assertEqual(dirty.read_bytes(), before_dirty)

        # Kein Stage, Commit, Stash, Checkout oder Wiederherstellen.
        self.assertEqual(
            support.git(project, "diff", "--cached", "--name-only").stdout, ""
        )
        self.assertEqual(
            support.git(project, "stash", "list").stdout, ""
        )
        tracked = support.git(project, "ls-tree", "-r", "--name-only", "HEAD")
        self.assertNotIn("unfertig.txt", tracked.stdout.splitlines())
        self.assertIn(" M AGENTS.md", after_status)
        self.assertIn("?? unfertig.txt", after_status)

    def test_final_verification_still_blocks_a_dirty_integration_tree(self):
        project = self.make_project(
            "strict",
            env_text=(
                'TYPE=generic\nAGENT=test-agent\nTESTER=test-agent\n'
                'REVIEWER=code-reviewer\nVERIFY_PACKAGE="true"\n'
                'VERIFY_FULL="echo final > \\"$VIBE_RUNTIME/final-ran\\""\n'
            ),
        )
        self.make_dirty(project)
        final_marker = self.runtime / "final-ran"

        result = self.run_runner(
            project, VIBE_KEEP_CHANGES="1", VIBE_MAX_PACKAGES="1"
        )
        output = self.combined(result, project)

        # Das Paket durfte starten, die Gesamtprüfung bleibt aber streng.
        self.assertEqual(len(self.agent_calls()), 1, output)
        self.assertEqual(result.returncode, 1, output)
        self.assertIn("Integrationsstand ist nicht sauber", output)
        self.assertIn("unfertig.txt", output)
        self.assertFalse(
            final_marker.exists(),
            "Die Gesamtprüfung lief trotz unsauberem Integrationsstand.",
        )

    def test_other_findings_block_even_with_keep_changes(self):
        cases = []

        norepo = self.root / "norepo"
        (norepo / ".vibe").mkdir(parents=True)
        (norepo / ".vibe" / "project.env").write_text(
            PROJECT_ENV, encoding="utf-8"
        )
        (norepo / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        (norepo / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
        self.make_dirty(norepo)
        cases.append(("norepo", norepo, "Kein Git-Repository"))

        detached = self.make_project("detached")
        support.git(detached, "checkout", "--detach")
        self.make_dirty(detached)
        cases.append(("detached", detached, "Detached HEAD"))

        no_tester = self.make_project(
            "no-tester",
            """TYPE=generic
AGENT=test-agent
REVIEWER=code-reviewer
VERIFY_PACKAGE="true"
""",
        )
        self.make_dirty(no_tester)
        cases.append(("no-tester", no_tester, "TESTER"))

        no_reviewer = self.make_project(
            "no-reviewer",
            """TYPE=generic
AGENT=test-agent
TESTER=test-agent
REVIEWER=fehlt
VERIFY_PACKAGE="true"
""",
        )
        self.make_dirty(no_reviewer)
        cases.append(("no-reviewer", no_reviewer, "REVIEWER"))

        no_check = self.make_project(
            "no-check",
            """TYPE=generic
AGENT=test-agent
TESTER=test-agent
REVIEWER=code-reviewer
""",
        )
        self.make_dirty(no_check)
        cases.append(("no-check", no_check, "Paketprüfung fehlt"))

        for name, project, expected in cases:
            with self.subTest(name=name):
                result = self.run_runner(
                    project, VIBE_KEEP_CHANGES="1", VIBE_MAX_PACKAGES="1"
                )
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 2, output)
                self.assertIn(expected, output)
                self.assertEqual(self.agent_calls(), [])
                # Der unsaubere Arbeitsbaum ist mit der Option kein
                # blockierender Befund mehr; ein bloßer Hinweis wäre erlaubt.
                self.assertNotIn("BLOCKIERT: Arbeitsbaum", output)


# ---------------------------------------------------------------------------
# CLI: vibe run --keep-changes
# ---------------------------------------------------------------------------
class CliFixture(unittest.TestCase):
    """Geladenes CLI-Modul ohne echte tmux-, Modell- oder Netzaufrufe."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.project = self.root / "proj"
        support.init_repo(self.project)
        support.write_project(self.project, PROJECT_ENV, feedback=FEEDBACK)
        support.commit_all(self.project, "Ausgangsstand")
        self.runtime = self.root / "_logs"
        self.cli = load_cli(self.root, self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def patches(self, **overrides):
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(list(argv))
            if "has-session" in argv:
                return 1, ""
            return 0, ""

        class Registry:
            def start(self, **kwargs):
                return {"id": "proj-test"}

            def finish(self, *args, **kwargs):
                return None

        values = {
            "run": fake_run,
            "tmux_has": lambda name: False,
            "project_map": lambda: {"proj": str(self.project)},
            "ppath": lambda name: str(self.project),
            "is_init": lambda name: True,
            "ensure_test_agent": lambda project: {
                "agent": False,
                "config": False,
            },
            "sandbox_status": lambda name: {"enabled": False},
            "pause_after_active": lambda name: False,
            "penv": lambda name: {"AGENT": "test-agent"},
            "vibe_agent_status": lambda: {
                "name": "",
                "model": "",
                "configured": False,
            },
            "require_agent": lambda agent: agent,
            "ensure_opencode_password": lambda: str(
                self.runtime / "opencode.password"
            ),
            "run_agent_selection": lambda name, agent: "",
            "run_key": lambda name: "proj",
            "sess": lambda name: "vibe-proj",
            "logpath": lambda name, kind="run": str(
                self.runtime / (name + ".log")
            ),
            "run_registry": lambda: Registry(),
            "ensure_general_rules": lambda project: False,
        }
        values.update(overrides)
        return values, calls

    def invoke_main(self, argv, **overrides):
        values, calls = self.patches(**overrides)
        buffer = io.StringIO()
        code = None
        with mock.patch.multiple(self.cli, **values), mock.patch.object(
            self.cli.vibe_runs, "rotate_log", lambda *args, **kwargs: None
        ), mock.patch.dict(
            os.environ, {"VIBE_NO_CONTAINER": "1"}
        ), mock.patch.object(
            sys, "argv", list(argv)
        ), contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(
            buffer
        ):
            try:
                self.cli.main()
            except SystemExit as error:
                code = error.code
        return buffer.getvalue(), calls, code

    def invoke_run(self, **overrides):
        values, calls = self.patches(**overrides)
        buffer = io.StringIO()
        code = None
        with mock.patch.multiple(self.cli, **values), mock.patch.object(
            self.cli.vibe_runs, "rotate_log", lambda *args, **kwargs: None
        ), contextlib.redirect_stderr(buffer):
            try:
                self.cli.cmd_run("proj", out=buffer)
            except SystemExit as error:
                code = error.code
        return buffer.getvalue(), calls, code

    def new_session_calls(self, calls):
        return [call for call in calls if "new-session" in call]


class CliKeepChangesTest(CliFixture):
    """Verhalten 1: Die CLI reicht die Absicht an den Läufer weiter."""

    def test_cli_run_with_keep_changes_exports_the_intent(self):
        output, calls, code = self.invoke_main(
            ["vibe", "run", "proj", "--keep-changes"]
        )

        self.assertIsNone(code, output)
        sessions = self.new_session_calls(calls)
        self.assertEqual(len(sessions), 1, calls)
        flattened = " ".join(sessions[0])
        self.assertIn("VIBE_KEEP_CHANGES=1", flattened)
        self.assertIn("VIBE_PREFLIGHT_ASSIST=1", flattened)
        self.assertNotIn("--keep-changes", flattened)

    def test_cli_run_without_keep_changes_does_not_export_the_intent(self):
        output, calls, code = self.invoke_main(["vibe", "run", "proj"])

        self.assertIsNone(code, output)
        sessions = self.new_session_calls(calls)
        self.assertEqual(len(sessions), 1, calls)
        flattened = " ".join(sessions[0])
        self.assertNotIn("VIBE_KEEP_CHANGES=1", flattened)
        self.assertIn("VIBE_PREFLIGHT_ASSIST=1", flattened)

    def test_cli_run_accepts_an_agent_before_keep_changes(self):
        output, calls, code = self.invoke_main(
            ["vibe", "run", "proj", "test-agent", "--keep-changes"]
        )

        self.assertIsNone(code, output)
        sessions = self.new_session_calls(calls)
        self.assertEqual(len(sessions), 1, calls)
        flattened = " ".join(sessions[0])
        self.assertIn("VIBE_KEEP_CHANGES=1", flattened)
        self.assertIn("test-agent", flattened)
        self.assertNotIn("--keep-changes", flattened)


# ---------------------------------------------------------------------------
# AGENTS.md: verwalteter Block bei Änderungen nicht überschreiben
# ---------------------------------------------------------------------------
class AgentsRulesTest(CliFixture):
    """Verhalten 4: Fremde Änderungen an AGENTS.md bleiben unangetastet."""

    def prepare(self):
        (self.project / "AGENTS.md").write_text(OLD_AGENTS, encoding="utf-8")
        support.commit_all(self.project, "AGENTS.md")

    def test_uncommitted_agents_change_is_not_rewritten_and_warns(self):
        self.prepare()
        changed = OLD_AGENTS.replace(
            "Eigene Regel", "Eigene geänderte Regel"
        )
        (self.project / "AGENTS.md").write_text(changed, encoding="utf-8")

        output, calls, code = self.invoke_run(
            ensure_general_rules=self.cli.ensure_general_rules
        )

        self.assertIsNone(code, output)
        self.assertIn("AGENTS.md", output)
        self.assertRegex(
            output, r"(?is)warn|nicht aktualisiert|unverändert"
        )
        content = (self.project / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(content, changed)
        self.assertIn("ALTER REGELSATZ", content)
        self.assertIn("Eigene geänderte Regel", content)
        self.assertNotIn(self.cli.GENERAL_RULES, content)
        status = support.git(
            self.project, "status", "--porcelain", "--", "AGENTS.md"
        ).stdout
        self.assertIn("M AGENTS.md", status)
        self.assertEqual(len(self.new_session_calls(calls)), 1)

    def test_clean_agents_file_is_still_updated(self):
        self.prepare()

        output, calls, code = self.invoke_run(
            ensure_general_rules=self.cli.ensure_general_rules
        )

        self.assertIsNone(code, output)
        self.assertIn("AGENTS.md", output)
        self.assertRegex(output, r"(?is)aktualisiert")
        content = (self.project / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(self.cli.GENERAL_RULES, content)
        self.assertNotIn("ALTER REGELSATZ", content)
        self.assertEqual(len(self.new_session_calls(calls)), 1)


# ---------------------------------------------------------------------------
# Web-API: POST /api/run mit keep_changes
# ---------------------------------------------------------------------------
FAKE_TMUX = r'''#!/usr/bin/env python3
"""Zeichnet tmux-Aufrufe auf und verhält sich wie ein frischer Server."""
import json
import os
import sys

args = sys.argv[1:]
path = os.environ.get("FAKE_TMUX_LOG")
if path:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"args": args}, ensure_ascii=False) + "\n")

if args[:1] == ["has-session"]:
    sys.exit(1)
if args[:1] == ["show-environment"]:
    sys.stdout.write("unknown variable: VIBE_MANAGED\n")
    sys.exit(1)
sys.exit(0)
'''


def free_port():
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class WebRunApiTest(unittest.TestCase):
    """Verhalten 5: Das Dashboard kann die Absicht über die API senden."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        support.write_agents(cls.agents, "test-agent", "code-reviewer")
        cls.project = cls.root / "proj"
        support.init_repo(cls.project)
        support.write_project(cls.project, PROJECT_ENV, feedback=FEEDBACK)
        project_agent = cls.project / ".opencode" / "agents" / "test-agent.md"
        project_agent.parent.mkdir(parents=True)
        project_agent.write_text(
            "---\ndescription: Testagent\nmode: subagent\n---\n",
            encoding="utf-8",
        )
        support.commit_all(cls.project, "Ausgangsstand")
        (cls.project / "unfertig.txt").write_text(
            "unfertig\n", encoding="utf-8"
        )
        cls.fakebin = cls.root / "fakebin"
        cls.fakebin.mkdir()
        tmux = cls.fakebin / "tmux"
        tmux.write_text(FAKE_TMUX, encoding="utf-8")
        tmux.chmod(0o755)
        cls.tmux_log = cls.root / "tmux.log"
        cls.runtime = cls.root / "_logs"
        cls.port = free_port()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_"):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "VIBE_INSTALL": str(cls.root / "_toolchain"),
                "VIBE_RUNTIME": str(cls.runtime),
                "VIBE_STATE": str(cls.root / "_state"),
                "VIBE_AGENTS_DIR": str(cls.agents),
                "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
                "VIBE_STORAGE_LOCK_DIR": str(cls.home / "locks"),
                "HOME": str(cls.home),
                "XDG_CONFIG_HOME": str(cls.home / ".config"),
                "PATH": str(cls.fakebin) + os.pathsep + env.get("PATH", ""),
                "FAKE_TMUX_LOG": str(cls.tmux_log),
            }
        )
        cls.env = env
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.runtime / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with __import__("socket").create_connection(
                        ("127.0.0.1", cls.port), timeout=0.5
                    ):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError("vibe-web wurde vorzeitig beendet: " + output)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        if cls.proc.stdout:
            cls.proc.stdout.close()
        cls.tmp.cleanup()

    def setUp(self):
        if self.tmux_log.exists():
            self.tmux_log.unlink()

    def request(self, method, path, body=None, token=True):
        import http.client

        headers = {"Host": "127.0.0.1:%d" % self.port}
        if token:
            headers["X-Token"] = self.token
        payload = None
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.port, timeout=15
        )
        try:
            connection.request(method, path, body=payload, headers=headers)
            response = connection.getresponse()
            text = response.read().decode("utf-8", "replace")
            return response.status, text
        finally:
            connection.close()

    def tmux_records(self):
        if not self.tmux_log.exists():
            return []
        return [
            json.loads(line)
            for line in self.tmux_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def new_sessions(self):
        return [
            " ".join(record["args"])
            for record in self.tmux_records()
            if record.get("args", [])[:1] == ["new-session"]
        ]

    def status_snapshot(self):
        return support.git(
            self.project, "status", "--porcelain=v1", "-uall"
        ).stdout

    def test_api_run_with_keep_changes_exports_intent_and_names_files(self):
        before = self.status_snapshot()

        status, body = self.request(
            "POST", "/api/run",
            {"name": "proj", "keep_changes": True},
        )

        self.assertEqual(status, 200, body)
        data = json.loads(body)
        self.assertTrue(data.get("ok"), data)
        message = data.get("message", "")
        self.assertIn("unfertig.txt", message)
        sessions = self.new_sessions()
        self.assertEqual(len(sessions), 1, self.tmux_records())
        self.assertIn("VIBE_KEEP_CHANGES=1", sessions[0])
        self.assertEqual(self.status_snapshot(), before)

    def test_api_run_without_keep_changes_does_not_export_the_intent(self):
        status, body = self.request("POST", "/api/run", {"name": "proj"})

        self.assertEqual(status, 200, body)
        data = json.loads(body)
        self.assertTrue(data.get("ok"), data)
        sessions = self.new_sessions()
        self.assertEqual(len(sessions), 1, self.tmux_records())
        self.assertNotIn("VIBE_KEEP_CHANGES=1", sessions[0])


if __name__ == "__main__":
    unittest.main()
