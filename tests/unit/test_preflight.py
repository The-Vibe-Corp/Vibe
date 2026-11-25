"""Preflight: Rollenauflösung, blockierter Laufzustand, Assistenten-Dialog und Selbstreparatur.

Aufruf: python3 -m unittest tests.unit.test_preflight -v
"""


# ===========================================================================
# UI-konfigurierte Agenten für den Lauf freigeben
# ===========================================================================

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
PACKAGES = BIN / "vibe_packages.py"
RUNS = BIN / "vibe_runs.py"
RUNNER = BIN / "vibe-run.sh"


def load_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def project_env(reviewer=None):
    """Projektdatei ohne bzw. mit ausdrücklichem REVIEWER."""
    lines = [
        "TYPE=generic",
        "AGENT=tester",
        "TESTER=test-agent",
    ]
    if reviewer is not None:
        lines.append("REVIEWER=" + reviewer)
    lines.extend(
        [
            'VERIFY_PACKAGE="true"',
            'VERIFY_FULL="true"',
        ]
    )
    return "\n".join(lines) + "\n"


class PreflightProfilesTest(unittest.TestCase):
    """Preflight mit Rollenauflösung aus profiles.json (A1-A4, A6)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        support.init_repo(self.project)
        self.agents = self.root / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        support.write_project(self.project, project_env())
        self.state = self.root / "state"
        self.state.mkdir()
        self.write_profiles({"code-reviewer": "reviewer"})
        support.commit_all(self.project, "Ausgangsstand")
        self.module = load_module(PACKAGES, "vibe_packages_f21_preflight")

    def tearDown(self):
        self.tmp.cleanup()

    def write_profiles(self, rollen):
        (self.state / "profiles.json").write_text(
            json.dumps({"rollen": rollen}), encoding="utf-8"
        )

    def write_raw_profiles(self, text):
        (self.state / "profiles.json").write_text(text, encoding="utf-8")

    def errors(self, reviewer="", state_dir=None):
        return self.module.preflight_errors(
            str(self.project),
            agents_dir=str(self.agents),
            tester="test-agent",
            reviewer=reviewer,
            state_dir=str(self.state) if state_dir is None else state_dir,
        )

    # A1: fehlender REVIEWER wird aus der reviewer-Rolle ergänzt.
    def test_reviewer_role_from_profiles_json_completes_preflight(self):
        """project.env ohne REVIEWER, Rollenauflösung über profiles.json."""
        errors = self.errors()

        self.assertEqual(errors, [])

    def test_project_local_agent_file_satisfies_the_reviewer_role(self):
        """Die Rollenzuordnung darf auch einen projektlokalen Agenten nutzen."""
        (self.agents / "code-reviewer.md").unlink()
        local = self.project / ".opencode" / "agents"
        local.mkdir(parents=True)
        (local / "code-reviewer.md").write_text(
            "---\ndescription: lokaler Reviewer\n---\n", encoding="utf-8"
        )
        support.commit_all(self.project, "lokaler Reviewer")

        errors = self.errors()

        self.assertEqual(errors, [])

    # A2: expliziter REVIEWER bleibt vorrangig.
    def test_explicit_reviewer_argument_wins_over_profiles_role(self):
        """Ein nicht verfügbarer expliziter Reviewer blockiert trotz Rolle."""
        errors = self.errors(reviewer="nicht-vorhanden")

        self.assertTrue(any("REVIEWER" in error for error in errors), errors)
        self.assertTrue(
            any("nicht-vorhanden" in error for error in errors), errors
        )

    def test_project_env_reviewer_wins_over_profiles_role(self):
        """REVIEWER aus project.env hat Vorrang vor der Rollenauflösung."""
        support.write_project(self.project, project_env("nicht-vorhanden"))

        errors = self.errors()

        self.assertTrue(any("REVIEWER" in error for error in errors), errors)
        self.assertTrue(
            any("nicht-vorhanden" in error for error in errors), errors
        )

    # A3: veralteter Rolleneintrag blockiert verfügbaren Agenten nicht.
    def test_unavailable_role_entry_does_not_block_an_available_reviewer(self):
        """Ein zuerst eingetragener, veralteter Reviewer wird übersprungen."""
        self.write_profiles(
            {
                "veralteter-reviewer": "reviewer",
                "code-reviewer": "reviewer",
            }
        )

        errors = self.errors()

        self.assertEqual(errors, [])

    def test_invalid_reviewer_role_names_are_ignored(self):
        """Nur Agentennamen nach der Läufer-Konvention dürfen zählen.

        Pfadanteile, Leerzeichen und Shell-/Sonderzeichen werden ignoriert.
        Eine Datei außerhalb des Agentenordners darf dadurch nicht als
        verfügbarer Reviewer akzeptiert werden.
        """
        cases = [
            ("../ausserhalb", self.root / "ausserhalb.md"),
            ("name mit leerzeichen", self.agents / "name mit leerzeichen.md"),
            ("name;rm", self.agents / "name;rm.md"),
        ]
        for name, path in cases:
            with self.subTest(name=name):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    "---\ndescription: unsicher\n---\n", encoding="utf-8"
                )
                self.addCleanup(path.unlink, missing_ok=True)
                self.write_profiles({name: "reviewer"})

                errors = self.errors()

                self.assertTrue(
                    any("REVIEWER" in error for error in errors), errors
                )

    def test_valid_reviewer_beside_unsafe_entry_remains_usable(self):
        """Ein gültiger Eintrag bleibt nutzbar; der unsichere zählt nie."""
        outside = self.root / "ausserhalb.md"
        outside.write_text(
            "---\ndescription: unsicher\n---\n", encoding="utf-8"
        )
        self.addCleanup(outside.unlink, missing_ok=True)
        self.write_profiles(
            {"../ausserhalb": "reviewer", "code-reviewer": "reviewer"}
        )

        self.assertEqual(self.errors(), [])

        (self.agents / "code-reviewer.md").unlink()

        errors = self.errors()

        self.assertTrue(any("REVIEWER" in error for error in errors), errors)

    # A4: ohne Rolle bzw. ohne verfügbaren Rollenagenten blockiert der Preflight.
    def test_missing_reviewer_role_blocks_with_reviewer_message(self):
        self.write_profiles({"coder": "coder"})

        errors = self.errors()

        self.assertTrue(any("REVIEWER" in error for error in errors), errors)

    def test_reviewer_role_without_available_agent_blocks(self):
        self.write_profiles({"veralteter-reviewer": "reviewer"})

        errors = self.errors()

        self.assertTrue(any("REVIEWER" in error for error in errors), errors)
        self.assertTrue(
            any("veralteter-reviewer" in error for error in errors), errors
        )

    def test_missing_profiles_file_blocks_without_crash(self):
        (self.state / "profiles.json").unlink()

        errors = self.errors()

        self.assertTrue(any("REVIEWER" in error for error in errors), errors)

    def test_broken_profiles_file_blocks_without_crash(self):
        self.write_raw_profiles("{kein gültiges JSON")

        errors = self.errors()

        self.assertTrue(any("REVIEWER" in error for error in errors), errors)

    def test_profiles_with_invalid_roles_structure_blocks_without_crash(self):
        self.write_raw_profiles(json.dumps({"rollen": ["code-reviewer"]}))

        errors = self.errors()

        self.assertTrue(any("REVIEWER" in error for error in errors), errors)

    # A6: bestehende Preflight-Prüfungen bleiben wirksam.
    def test_dirty_worktree_still_blocks_with_role_resolved_reviewer(self):
        (self.project / "unfertig.txt").write_text("x\n", encoding="utf-8")

        errors = self.errors()

        self.assertTrue(any("Arbeitsbaum" in error for error in errors), errors)

    def test_missing_test_agent_still_blocks_with_role_resolved_reviewer(self):
        (self.agents / "test-agent.md").unlink()

        errors = self.errors()

        self.assertTrue(any("TESTER" in error for error in errors), errors)


class PreflightCliTest(unittest.TestCase):
    """CLI-Schnittstelle ``preflight --state`` (A1)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        support.init_repo(self.project)
        self.agents = self.root / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        support.write_project(self.project, project_env())
        self.state = self.root / "state"
        self.state.mkdir()
        (self.state / "profiles.json").write_text(
            json.dumps({"rollen": {"code-reviewer": "reviewer"}}),
            encoding="utf-8",
        )
        support.commit_all(self.project, "Ausgangsstand")

    def tearDown(self):
        self.tmp.cleanup()

    def run_preflight(self, *state_args):
        return subprocess.run(
            [
                sys.executable,
                str(PACKAGES),
                "preflight",
                "--project",
                str(self.project),
                "--agents-dir",
                str(self.agents),
                "--tester",
                "test-agent",
                *state_args,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_cli_preflight_resolves_reviewer_from_state_directory(self):
        result = self.run_preflight("--state", str(self.state))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("BLOCKIERT", result.stdout, result.stdout)

    def test_cli_preflight_without_state_still_blocks_missing_reviewer(self):
        result = self.run_preflight()

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("REVIEWER", result.stdout)


class RunStateBlockedTest(unittest.TestCase):
    """A5: ``blocked`` als gültiger Endzustand im Register."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "_logs"
        self.runs = load_module(RUNS, "vibe_runs_f21_under_test")
        self.registry = self.runs.RunRegistry(str(self.runtime))

    def tearDown(self):
        self.tmp.cleanup()

    def start(self):
        return self.registry.start(
            project="/work/proj",
            name="proj",
            key="proj",
            agent="tester",
            session="vibe-proj",
            log=str(self.runtime / "proj.log"),
            verify_log=str(self.runtime / "proj.verify.log"),
        )

    def test_registry_stores_blocked_as_final_state(self):
        record = self.start()

        result = self.registry.finish(
            record["id"], exit_code=2, state="blocked"
        )

        self.assertEqual(result["state"], "blocked")
        self.assertEqual(result["exit_code"], 2)
        stored = self.registry.get(record["id"])
        self.assertEqual(stored["state"], "blocked")
        self.assertEqual(stored["exit_code"], 2)
        data = json.loads((self.runtime / "runs.json").read_text(encoding="utf-8"))
        self.assertEqual(data["runs"][-1]["state"], "blocked")

    def test_registry_rejects_unknown_final_state(self):
        record = self.start()

        with self.assertRaises(ValueError):
            self.registry.finish(record["id"], exit_code=2, state="kaputt")

        self.assertEqual(self.registry.get(record["id"])["state"], "running")

    def test_cli_finish_accepts_blocked_and_returns_zero(self):
        record = self.start()

        result = subprocess.run(
            [
                sys.executable,
                str(RUNS),
                "finish",
                "--runtime",
                str(self.runtime),
                "--id",
                record["id"],
                "--exit-code",
                "2",
                "--state",
                "blocked",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.registry.get(record["id"])["state"], "blocked")
        self.assertEqual(self.registry.get(record["id"])["exit_code"], 2)

    def test_cli_finish_rejects_unknown_state(self):
        record = self.start()

        result = subprocess.run(
            [
                sys.executable,
                str(RUNS),
                "finish",
                "--runtime",
                str(self.runtime),
                "--id",
                record["id"],
                "--state",
                "kaputt",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(self.registry.get(record["id"])["state"], "running")


class RunnerPreflightProfilesTest(unittest.TestCase):
    """A7: echter Läufer ohne REVIEWER in project.env, Rolle in profiles.json."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        (self.tool_bin / "vibe").write_text(support.FAKE_VIBE, encoding="utf-8")
        (self.tool_bin / "vibe").chmod(0o755)
        self.runtime = self.root / "_logs"
        self.state = self.root / "_state"
        self.state.mkdir()
        (self.state / "profiles.json").write_text(
            json.dumps({"rollen": {"code-reviewer": "reviewer"}}),
            encoding="utf-8",
        )
        self.project = self.root / "proj"
        support.init_repo(self.project)
        support.write_project(
            self.project,
            project_env(),
            feedback=[support.ticket_record(
                "F1", "Erstes Paket", type="feedback",
                description="Test")],
        )
        support.commit_all(self.project, "Ausgangsstand")
        self.calls = self.root / "calls.log"
        self.counter = self.root / "counter"
        self.fakebin = support.install_fake_tools(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def env(self, **extra):
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
                "VIBE_LOGNAME": "proj",
                "VIBE_MAX_PACKAGES": "1",
                "VIBE_RETRY_DELAY": "0",
                "HOME": str(self.home),
                "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
                "FAKE_CALLS": str(self.calls),
                "FAKE_COUNTER": str(self.counter),
                "FAKE_MODE": "complete",
            }
        )
        env.update({key: str(value) for key, value in extra.items()})
        return env

    def log(self):
        path = self.runtime / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def test_runner_passes_preflight_without_reviewer_in_project_env(self):
        result = subprocess.run(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(self.project)],
            cwd=str(self.project),
            env=self.env(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Arbeitspaket F1", self.log())
        self.assertIn("Geschlossen: F1", result.stdout)
        self.assertTrue(self.calls.is_file(), "kein Agentenaufruf erfolgt")
        self.assertEqual(
            len(self.calls.read_text(encoding="utf-8").splitlines()), 1
        )
        self.assertNotIn("REVIEWER fehlt", result.stdout)

    def test_blocked_preflight_finishes_the_run_register_as_blocked(self):
        """Ein vom Preflight blockierter Lauf bleibt nicht auf 'starting'."""
        runs = load_module(RUNS, "vibe_runs_f21_runner_under_test")
        registry = runs.RunRegistry(str(self.runtime))
        record = registry.start(
            project=str(self.project),
            name="proj",
            key="proj",
            agent="tester",
            session="vibe-proj",
            log=str(self.runtime / "proj.log"),
            verify_log=str(self.runtime / "proj.verify.log"),
            run_id="proj-f21",
            state="starting",
        )
        (self.project / "unfertig.txt").write_text("x\n", encoding="utf-8")

        result = subprocess.run(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(self.project)],
            cwd=str(self.project),
            env=self.env(VIBE_RUN_ID=record["id"]),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
        )

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        stored = registry.get(record["id"])
        self.assertIsNotNone(stored)
        self.assertEqual(stored["state"], "blocked")
        self.assertEqual(stored["exit_code"], 2)


# ===========================================================================
# Ein nicht bestandener Preflight führt über zu einer Rückfrage
# ===========================================================================

import importlib.machinery
import importlib.util
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

CLI = REPO / "bin" / "vibe"

PROJECT_ENV = """TYPE=generic
AGENT=tester
TESTER=test-agent
REVIEWER=code-reviewer
VERIFY_PACKAGE="true"
VERIFY_FULL="true"
"""

FEEDBACK = [support.ticket_record(
    "F1", "Erstes Paket", type="feedback", description="Test")]


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
        "HOME",
        "XDG_CONFIG_HOME",
    )
    old = {key: os.environ.get(key) for key in keys}
    os.environ["VIBE"] = str(vibe_root)
    os.environ["VIBE_NO_CONTAINER"] = "1"
    os.environ["HOME"] = str(home)
    # Keine persönliche Konfiguration des ausführenden Nutzers lesen.
    os.environ["XDG_CONFIG_HOME"] = str(home / ".config")
    os.environ["VIBE_CONFIG_FILE"] = str(vibe_root / "config.json")
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
            "vibe_f22_under_test", str(CLI)
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


class PreflightAssistFixture(unittest.TestCase):
    """Isolierter Läufer, Projekt, Laufzeit und Agenten-Attrappen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        (self.tool_bin / "vibe").write_text(support.FAKE_VIBE, encoding="utf-8")
        (self.tool_bin / "vibe").chmod(0o755)
        self.runtime = self.root / "_logs"
        self.state = self.root / "_state"
        self.state.mkdir()
        self.project = self.root / "proj"
        support.init_repo(self.project)
        support.write_project(
            self.project, PROJECT_ENV, feedback=FEEDBACK
        )
        support.commit_all(self.project, "Ausgangsstand")
        self.calls = self.root / "calls.log"
        self.counter = self.root / "counter"
        self.fakebin = support.install_fake_tools(self.root)
        self.proc = None
        self.out_path = None
        self.run_count = 0
        self.handles = []

    def tearDown(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()
        for handle in self.handles:
            handle.close()
        self.tmp.cleanup()

    # -- Umgebung und Start ------------------------------------------------
    def env(self, **extra):
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
                "VIBE_CONFIG_FILE": str(self.root / "config.json"),
                "VIBE_LOGNAME": "proj",
                "VIBE_MAX_PACKAGES": "1",
                "VIBE_RETRY_DELAY": "0",
                "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
                "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
                "FAKE_CALLS": str(self.calls),
                "FAKE_COUNTER": str(self.counter),
                "FAKE_MODE": "complete",
            }
        )
        env.update({key: str(value) for key, value in extra.items()})
        return env

    def start(self, **extra):
        """Startet den Läufer im Hintergrund; Ausgabe geht in eine Datei."""
        env = self.env(**extra)
        self.out_path = self.root / ("runner-%d.out" % self.run_count)
        self.run_count += 1
        handle = self.out_path.open("w", encoding="utf-8")
        self.handles.append(handle)
        self.proc = subprocess.Popen(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(self.project)],
            cwd=str(self.project),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return self.proc

    def output(self):
        if self.out_path is None or not self.out_path.exists():
            return ""
        return self.out_path.read_text(encoding="utf-8", errors="replace")

    def log(self):
        path = self.runtime / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def combined_output(self):
        return self.output() + "\n" + self.log()

    def assert_autonomous_agent_assignment(self, output):
        """Die Beauftragung nennt die autonome Herkunft, nicht den Nutzer."""
        lines = [
            line
            for line in output.splitlines()
            if "Agent" in line and "beauftragt" in line
        ]
        self.assertTrue(
            lines,
            "Keine Protokollzeile zur Agentenbeauftragung:\n" + output,
        )
        assignment = "\n".join(lines)
        self.assertRegex(assignment, r"(?i)autonom")
        self.assertNotIn("Anweisung des Nutzers", assignment)

    def wait_exit(self, timeout=90):
        try:
            return self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
            raise AssertionError(
                "Läufer lief nach %s s weiter.\n%s" % (timeout, self.output())
            )

    def agent_calls(self):
        if not self.calls.is_file():
            return []
        return self.calls.read_text(encoding="utf-8").splitlines()

    def preflight_calls(self):
        """Liefert Preflight-Aufträge mit Arbeitsverzeichnis und Prompt."""
        result = []
        for line in self.agent_calls():
            parts = line.split("\t", 2)
            if not parts or parts[0] != "preflight":
                continue
            prompt = ""
            if len(parts) > 2:
                try:
                    prompt = json.loads(parts[2])
                except json.JSONDecodeError:
                    prompt = parts[2]
            result.append(
                {"cwd": parts[1] if len(parts) > 1 else "", "prompt": prompt}
            )
        return result

    def package_calls(self):
        """Liefert die Aufrufe für Arbeitspakete (ohne Preflight-Aufträge)."""
        return [
            line for line in self.agent_calls()
            if not line.startswith("preflight\t")
        ]

    # -- Rückfragen --------------------------------------------------------
    def question_folder(self):
        return self.runtime / "questions"

    def question_files(self):
        folder = self.question_folder()
        if not folder.is_dir():
            return []
        return sorted(
            path
            for path in folder.iterdir()
            if path.name.endswith(".json")
            and not path.name.endswith(".answer.json")
        )

    def open_questions(self):
        folder = self.question_folder()
        result = []
        for path in self.question_files():
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(record, dict) or "id" not in record:
                continue
            answer = folder / (record["id"] + ".answer.json")
            if answer.exists():
                continue
            result.append(record)
        return result

    def wait_for_question(self, seen=(), timeout=30):
        """Wartet auf eine neue, offene Rückfrage oder erklärt den Abbruch."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for record in self.open_questions():
                if record["id"] not in seen:
                    return record
            if self.proc.poll() is not None:
                # Dem Dateisystem einen kurzen Moment geben, falls der Läufer
                # die Rückfrage unmittelbar vor dem Ende geschrieben hat.
                time.sleep(0.2)
                for record in self.open_questions():
                    if record["id"] not in seen:
                        return record
                raise AssertionError(
                    "Läufer endete ohne erwartete Rückfrage (Exit %s):\n%s"
                    % (self.proc.returncode, self.output())
                )
            time.sleep(0.05)
        raise AssertionError(
            "Keine Rückfrage innerhalb von %s s.\n%s"
            % (timeout, self.output())
        )

    def answer(self, record, option):
        """Beantwortet eine Rückfrage per Auswahl wie das Dashboard."""
        self.answer_text(record, "", option)

    def answer_text(self, record, text, option=None):
        """Beantwortet eine Rückfrage mit Freitext (atomar ersetzt)."""
        folder = self.question_folder()
        folder.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "option": option,
                "text": text,
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "by": "test",
            }
        ) + "\n"
        target = folder / (record["id"] + ".answer.json")
        temporary = folder / (".answer-" + record["id"] + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, target)

    def answer_file(self, record):
        return self.question_folder() / (record["id"] + ".answer.json")

    def write_raw_answer(self, record, payload):
        """Schreibt eine absichtlich ungültige Antwortdatei atomar."""
        folder = self.question_folder()
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / (record["id"] + ".answer.json")
        temporary = folder / (".answer-" + record["id"] + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, target)

    # -- Autonomer Modus und Laufregister ---------------------------------
    def enable_autonomous(self, name="proj"):
        """Schaltet F16 für den Projektnamen ein (F16 führt Projektnamen)."""
        payload = {
            "version": 1,
            "projects": {
                name: {
                    "enabled": True,
                    "changed": "2026-01-01T00:00:00Z",
                }
            },
        }
        target = self.runtime / "autonomous.json"
        self.runtime.mkdir(parents=True, exist_ok=True)
        temporary = self.runtime / ".autonomous.json.tmp"
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(temporary, target)

    def create_run_record(self, run_id="proj-f22"):
        result = subprocess.run(
            [
                sys.executable,
                str(self.tool_bin / "vibe_runs.py"),
                "start",
                "--runtime",
                str(self.runtime),
                "--project",
                str(self.project),
                "--name",
                "proj",
                "--key",
                "proj",
                "--agent",
                "tester",
                "--session",
                "vibe-proj",
                "--id",
                run_id,
                "--state",
                "starting",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return run_id

    def run_record(self, run_id):
        path = self.runtime / "runs.json"
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        for record in data.get("runs", []):
            if record.get("id") == run_id:
                return record
        return None

    # -- Gemeinsame Vorbedingungen ----------------------------------------
    def make_dirty(self, name="unfertig.txt"):
        path = self.project / name
        path.write_text("unfertig\n", encoding="utf-8")
        return path

    def wait_until_clean(self, timeout=10):
        """Wartet, bis Git den Projektordner als sauber meldet (FUSE/NTFS)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = support.git(self.project, "status", "--porcelain")
            if status.returncode == 0 and not status.stdout.strip():
                return
            time.sleep(0.05)
        status = support.git(self.project, "status", "--porcelain")
        raise AssertionError(
            "Projekt wurde nicht sauber:\n" + status.stdout + status.stderr
        )


class DirectRunnerBehaviourTest(PreflightAssistFixture):
    """Verhalten 1: Ohne Assistenz bleibt der bisherige Abbruch erhalten."""

    def test_direct_runner_without_assist_aborts_without_question(self):
        """Mit Assistenz fragt der Läufer; ohne sie bricht er wie bisher ab."""
        self.make_dirty()

        # Positivkontrolle: Mit Assistenz entsteht eine Rückfrage.
        self.start(VIBE_PREFLIGHT_ASSIST="1",
                   VIBE_PREFLIGHT_QUESTION_TIMEOUT="30")
        first = self.wait_for_question()
        self.answer(first, 1)
        self.assertEqual(self.wait_exit(timeout=60), 2)
        questions_before = len(self.question_files())

        # Ohne VIBE_PREFLIGHT_ASSIST bleibt der bisherige Abbruch erhalten.
        self.start()
        rc = self.wait_exit(timeout=60)

        self.assertEqual(rc, 2, self.output())
        self.assertEqual(len(self.question_files()), questions_before)
        self.assertEqual(self.agent_calls(), [])
        self.assertIn("Preflight nicht bestanden", self.combined_output())


class VibeRunLaunchTest(unittest.TestCase):
    """Verhalten 1: ``vibe run`` übergibt die Assistenz an den Läufer."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            PROJECT_ENV, encoding="utf-8"
        )
        self.runtime = self.root / "_logs"
        self.cli = load_cli(self.root, self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def test_vibe_run_starts_runner_with_preflight_assist(self):
        """Der Startbefehl exportiert VIBE_PREFLIGHT_ASSIST=1 für den Läufer."""
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

        with mock.patch.multiple(
            self.cli,
            run=fake_run,
            tmux_has=lambda name: False,
            project_map=lambda: {"proj": str(self.project)},
            ppath=lambda name: str(self.project),
            is_init=lambda name: True,
            changed_file=lambda *args: False,
            sandbox_status=lambda name: {"enabled": False},
            pause_after_active=lambda name: False,
            penv=lambda name: {"AGENT": "tester"},
            default_agent=lambda: "tester",
            run_key=lambda name: "proj",
            logpath=lambda name, kind="run": str(
                self.runtime / (name + ".log")
            ),
            run_registry=lambda: Registry(),
        ), mock.patch.object(
            self.cli.vibe_runs, "rotate_log", lambda *args, **kwargs: None
        ):
            self.cli.cmd_run("proj")

        new_sessions = [call for call in calls if "new-session" in call]
        self.assertEqual(len(new_sessions), 1, calls)
        flattened = " ".join(str(part) for part in new_sessions[0])
        self.assertIn("VIBE_PREFLIGHT_ASSIST=1", flattened)


class QuestionContentTest(PreflightAssistFixture):
    """Verhalten 2: Inhalt und Form der Rückfrage."""

    def test_blocked_preflight_asks_with_project_findings_and_exact_options(self):
        """Die Frage nennt Projekt und Befund, bietet die drei Optionen."""
        self.make_dirty("unfertig.txt")

        self.start(VIBE_PREFLIGHT_ASSIST="1",
                   VIBE_PREFLIGHT_QUESTION_TIMEOUT="30")
        record = self.wait_for_question()

        self.assertIn("proj", record.get("project", ""))
        self.assertIn("Arbeitsbaum", record.get("text", ""))
        self.assertIn("unfertig.txt", record.get("text", ""))
        self.assertEqual(
            record.get("options"),
            ["Erneut prüfen", "Lauf abbrechen", "Agent behebt die Befunde"],
        )
        self.assertIs(record.get("free_text"), True)

        self.answer(record, 1)
        self.assertEqual(self.wait_exit(timeout=60), 2)

    def test_free_text_answer_is_explained_as_agent_instruction(self):
        """Freitext ist erlaubt und wird als Anweisung an den Agenten erklärt."""
        self.make_dirty()

        self.start(VIBE_PREFLIGHT_ASSIST="1",
                   VIBE_PREFLIGHT_QUESTION_TIMEOUT="30")
        record = self.wait_for_question()
        text = record.get("text", "")

        self.assertIs(record.get("free_text"), True)
        self.assertEqual(
            record.get("options"),
            ["Erneut prüfen", "Lauf abbrechen", "Agent behebt die Befunde"],
        )
        self.assertIn("Anweisung", text)
        self.assertIn("Agent", text)

        self.answer(record, 1)
        self.assertEqual(self.wait_exit(timeout=60), 2)


class RetryTest(PreflightAssistFixture):
    """Verhalten 3 und 8: Erneut prüfen, Fortsetzung und Folgebefund."""

    def test_retry_after_fix_runs_the_first_package(self):
        """Behobener Befund: Preflight besteht, F1 wird gestartet und beendet."""
        dirty = self.make_dirty()

        self.start(VIBE_PREFLIGHT_ASSIST="1",
                   VIBE_PREFLIGHT_QUESTION_TIMEOUT="30")
        first = self.wait_for_question()

        dirty.unlink()
        self.wait_until_clean()
        self.answer(first, 0)
        rc = self.wait_exit(timeout=120)

        self.assertEqual(rc, 0, self.output())
        self.assertEqual(self.open_questions(), [])
        self.assertEqual(len(self.agent_calls()), 1)
        self.assertIn("Arbeitspaket F1", self.log())
        self.assertIn("Geschlossen: F1", self.output())

    def test_retry_while_still_blocked_creates_a_new_question(self):
        """Bleibt der Befund, erscheint eine neue Rückfrage statt eines Laufs."""
        self.make_dirty()

        self.start(VIBE_PREFLIGHT_ASSIST="1",
                   VIBE_PREFLIGHT_QUESTION_TIMEOUT="30")
        first = self.wait_for_question()

        self.answer(first, 0)
        second = self.wait_for_question(seen={first["id"]})

        self.assertTrue(self.answer_file(first).is_file())
        self.assertNotEqual(second["id"], first["id"])
        self.assertIn("Arbeitsbaum", second.get("text", ""))
        self.assertEqual(self.agent_calls(), [])

        self.answer(second, 1)
        self.assertEqual(self.wait_exit(timeout=60), 2)
        self.assertEqual(self.agent_calls(), [])

    def test_multiple_findings_are_asked_one_after_another(self):
        """Erst der unsaubere Arbeitsbaum, danach der fehlende Reviewer."""
        dirty = self.make_dirty()
        (self.agents / "code-reviewer.md").unlink()

        self.start(VIBE_PREFLIGHT_ASSIST="1",
                   VIBE_PREFLIGHT_QUESTION_TIMEOUT="30")
        first = self.wait_for_question()
        self.assertIn("Arbeitsbaum", first.get("text", ""))

        dirty.unlink()
        self.wait_until_clean()
        self.answer(first, 0)
        second = self.wait_for_question(seen={first["id"]})
        self.assertTrue(self.answer_file(first).is_file())
        self.assertIn("REVIEWER", second.get("text", ""))

        support.write_agents(self.agents, "code-reviewer")
        self.answer(second, 0)
        rc = self.wait_exit(timeout=120)

        self.assertEqual(rc, 0, self.output())
        self.assertEqual(self.open_questions(), [])
        self.assertEqual(len(self.agent_calls()), 1)
        self.assertIn("Arbeitspaket F1", self.log())


class AbortTest(PreflightAssistFixture):
    """Verhalten 4: Lauf abbrechen beendet ohne Agentenaufruf."""

    def test_abort_ends_with_exit_2_marks_run_blocked_and_answers_question(self):
        """Option „Lauf abbrechen“: Exit 2, Register blocked, Frage beantwortet."""
        run_id = self.create_run_record()
        self.make_dirty()

        self.start(VIBE_PREFLIGHT_ASSIST="1",
                   VIBE_PREFLIGHT_QUESTION_TIMEOUT="30",
                   VIBE_RUN_ID=run_id)
        record = self.wait_for_question()

        self.answer(record, 1)
        rc = self.wait_exit(timeout=60)

        self.assertEqual(rc, 2, self.output())
        self.assertEqual(self.agent_calls(), [])
        self.assertTrue(self.answer_file(record).is_file())
        self.assertEqual(self.open_questions(), [])
        stored = self.run_record(run_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored["state"], "blocked")
        self.assertEqual(stored["exit_code"], 2)


class InvalidAnswerTest(PreflightAssistFixture):
    """Verhalten 9: Unlesbare oder ungültige Antworten enden klar mit Exit 2."""

    def test_corrupt_answer_ends_with_clear_error(self):
        """Eine unlesbare .answer.json beendet den Lauf ohne Traceback."""
        self.make_dirty()

        self.start(VIBE_PREFLIGHT_ASSIST="1",
                   VIBE_PREFLIGHT_QUESTION_TIMEOUT="30")
        record = self.wait_for_question()

        self.write_raw_answer(record, "{kaputt")
        rc = self.wait_exit(timeout=60)
        output = self.combined_output()

        self.assertEqual(rc, 2, output)
        self.assertEqual(self.agent_calls(), [])
        self.assertNotIn("Traceback", output)
        self.assertIn(record["id"], output)
        self.assertIn("nicht lesbar", output.lower())
        self.assertEqual(len(self.question_files()), 1,
                         "Nach der unlesbaren Antwort wurde erneut gefragt.")

    def test_invalid_option_ends_with_clear_error(self):
        """Eine nicht angebotene Option wird nicht als „Erneut prüfen“ gedeutet."""
        dirty = self.make_dirty()

        self.start(VIBE_PREFLIGHT_ASSIST="1",
                   VIBE_PREFLIGHT_QUESTION_TIMEOUT="30")
        record = self.wait_for_question()

        # Der Befund ist behoben; eine gültige „Erneut prüfen“-Antwort würde
        # jetzt das erste Arbeitspaket starten. Die ungültige Option darf das
        # nicht auslösen.
        dirty.unlink()
        self.wait_until_clean()
        self.answer(record, 3)
        rc = self.wait_exit(timeout=60)
        output = self.combined_output()

        self.assertEqual(rc, 2, output)
        self.assertEqual(self.agent_calls(), [])
        self.assertIn(record["id"], output)
        self.assertIn("ungültige antwort", output.lower())
        self.assertEqual(len(self.question_files()), 1,
                         "Die ungültige Option wurde stillschweigend erneut geprüft.")


class TimeoutTest(PreflightAssistFixture):
    """Verhalten 5: Ohne Antwort endet der Lauf nach dem Zeitlimit."""

    def test_timeout_ends_run_with_exit_2_keeps_question_open_and_names_its_id(self):
        """Exit 2, keine Antwort, offene Frage, Abbruchgrund nennt die ID."""
        self.make_dirty()

        self.start(VIBE_PREFLIGHT_ASSIST="1",
                   VIBE_PREFLIGHT_QUESTION_TIMEOUT="2")
        record = self.wait_for_question()
        rc = self.wait_exit(timeout=60)

        self.assertEqual(rc, 2, self.output())
        self.assertEqual(self.agent_calls(), [])
        self.assertFalse(self.answer_file(record).exists())
        self.assertIn(record["id"], self.combined_output())
        open_ids = {entry["id"] for entry in self.open_questions()}
        self.assertIn(record["id"], open_ids)


class AutonomousTest(PreflightAssistFixture):
    """Verhalten 6: Der autonome Modus repariert, statt zu fragen."""

    def test_autonomous_mode_repairs_without_a_question(self):
        """Aktiver Modus: keine Rückfrage, Agent im Projekt, danach F1."""
        self.enable_autonomous("proj")
        self.make_dirty()

        self.start(
            VIBE_PREFLIGHT_ASSIST="1",
            VIBE_PREFLIGHT_QUESTION_TIMEOUT="30",
            FAKE_PREFLIGHT_MODE="fix",
        )
        rc = self.wait_exit(timeout=120)
        output = self.combined_output()

        self.assertEqual(rc, 0, output)
        self.assertEqual(self.question_files(), [])
        calls = self.preflight_calls()
        self.assertEqual(len(calls), 1, calls)
        self.assertEqual(
            os.path.realpath(calls[0]["cwd"]),
            os.path.realpath(str(self.project)),
            "Der autonome Reparatur-Agent lief nicht im Projektordner.",
        )
        self.assertIn("Arbeitsbaum", calls[0]["prompt"])
        self.assertIn("unfertig.txt", calls[0]["prompt"])
        self.assertEqual(len(self.package_calls()), 1)
        self.assertIn("Arbeitspaket F1", self.log())
        self.assertIn("Geschlossen: F1", output)
        self.assert_autonomous_agent_assignment(output)

    def test_enabling_autonomous_during_wait_repairs_instead_of_aborting(self):
        """Während des Wartens eingeschaltet: Agent repariert, dann F1."""
        self.make_dirty()

        self.start(
            VIBE_PREFLIGHT_ASSIST="1",
            VIBE_PREFLIGHT_QUESTION_TIMEOUT="120",
            FAKE_PREFLIGHT_MODE="fix",
        )
        record = self.wait_for_question()
        self.assertEqual(
            record.get("options"),
            ["Erneut prüfen", "Lauf abbrechen", "Agent behebt die Befunde"],
        )

        started = time.monotonic()
        self.enable_autonomous("proj")
        rc = self.wait_exit(timeout=120)
        elapsed = time.monotonic() - started
        output = self.combined_output()

        self.assertEqual(rc, 0, output)
        self.assertLess(elapsed, 15, "Warten endete nicht sofort")
        calls = self.preflight_calls()
        self.assertEqual(len(calls), 1, calls)
        self.assertIn("Arbeitsbaum", calls[0]["prompt"])
        self.assertEqual(len(self.package_calls()), 1)
        self.assertIn("Geschlossen: F1", output)
        self.assert_autonomous_agent_assignment(output)


class AutonomousRepairLimitTest(PreflightAssistFixture):
    """Verhalten 6: Genau eine autonome Reparaturrunde, danach Blockade."""

    def test_failed_autonomous_repair_blocks_after_exactly_one_round(self):
        """Bleibt der Befund, endet der Lauf nach einer Runde ohne Paket."""
        self.enable_autonomous("proj")
        self.make_dirty()

        self.start(
            VIBE_PREFLIGHT_ASSIST="1",
            VIBE_PREFLIGHT_QUESTION_TIMEOUT="30",
            FAKE_PREFLIGHT_MODE="noop",
        )
        rc = self.wait_exit(timeout=120)
        output = self.combined_output()
        calls = self.preflight_calls()

        self.assertEqual(rc, 2, output)
        self.assertEqual(
            len(calls),
            1,
            "Es wurde nicht genau eine autonome Reparaturrunde versucht: %r"
            % (calls,),
        )
        self.assertEqual(self.package_calls(), [])
        self.assertEqual(self.question_files(), [])
        self.assertTrue((self.project / "unfertig.txt").exists())
        self.assertIn("BLOCKIERT", output)
        self.assertIn("Arbeitsbaum", output)
        self.assert_autonomous_agent_assignment(output)


class AutonomousRaceTest(unittest.TestCase):
    """GH-58: Moduswechsel zwischen Prüfung und Frage (Wettlauf)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.state = self.root / "_state"
        self.state.mkdir()
        self.runtime = self.root / "_logs"
        self.runtime.mkdir()
        self.project = self.root / "proj"
        support.init_repo(self.project)
        support.write_project(self.project, PROJECT_ENV, feedback=FEEDBACK)
        support.commit_all(self.project, "Ausgangsstand")
        self.dirty = self.project / "unfertig.txt"
        self.dirty.write_text("unfertig\n", encoding="utf-8")

        bin_dir = str(REPO / "bin")
        if bin_dir not in sys.path:
            sys.path.insert(0, bin_dir)
        self.packages = importlib.import_module("vibe_packages")
        self.questions = importlib.import_module("vibe_questions")
        self.autonomous = importlib.import_module("vibe_autonomous")

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_race_hands_the_findings_to_the_agent_instead_of_unavailable(self):
        """Vorbedingung: Der Preflight blockiert (unsauberer Arbeitsbaum); die
        Modusprüfung sieht den Modus noch als aus, zwischen Prüfung und
        Fragenstellung wird er aktiv, sodass ``create`` mit
        ``AutonomousActiveError`` abbricht.

        Aktion: ``assist_preflight`` wird in-process mit gepatchtem
        ``create`` (Wettlauf) und gepatchter Modusprüfung aufgerufen.

        Erwartung: Ergebnis ``action="agent"`` und ``source="autonomous"``;
        ``create`` wurde genau einmal versucht; die Anweisung nennt den
        Befund; es entsteht keine Rückfragedatei.

        Signifikanz: GH-58/E — der Wettlauf wird als autonome Entscheidung
        behandelt und nicht als „unavailable“ (Regression: Abbruch ohne
        Agentenauftrag).
        """
        with mock.patch.object(self.autonomous, "is_enabled", return_value=False):
            with mock.patch.object(
                self.questions,
                "create",
                side_effect=self.questions.AutonomousActiveError(
                    "Autonomer Modus aktiv; Rückfragen sind nicht möglich."
                ),
            ) as create:
                result = self.packages.assist_preflight(
                    str(self.project),
                    str(self.agents),
                    "test-agent",
                    "code-reviewer",
                    state_dir=str(self.state),
                    runtime=str(self.runtime),
                    project_name="proj",
                    timeout=1,
                )

        self.assertEqual("agent", result["action"])
        self.assertEqual("autonomous", result["source"])
        self.assertEqual(create.call_count, 1)
        self.assertIn("unfertig.txt", result["instruction"])
        self.assertEqual(list((self.runtime / "questions").glob("*.json")), [])


class SuccessfulPreflightTest(PreflightAssistFixture):
    """Verhalten 7: Ein erfolgreicher Preflight fragt nicht."""

    def test_successful_preflight_creates_no_question(self):
        """Erst belegt ein blockierter Lauf die Assistenz, dann fragt Erfolg nicht."""
        dirty = self.make_dirty()

        # Positivkontrolle: Der blockierte Preflight erzeugt eine Rückfrage.
        self.start(VIBE_PREFLIGHT_ASSIST="1",
                   VIBE_PREFLIGHT_QUESTION_TIMEOUT="30")
        first = self.wait_for_question()
        self.answer(first, 1)
        self.assertEqual(self.wait_exit(timeout=60), 2)
        questions_before = len(self.question_files())

        # Sauberer Preflight: F1 läuft durch, es entsteht keine neue Rückfrage.
        dirty.unlink()
        self.wait_until_clean()
        self.start(VIBE_PREFLIGHT_ASSIST="1",
                   VIBE_PREFLIGHT_QUESTION_TIMEOUT="30")
        rc = self.wait_exit(timeout=120)

        self.assertEqual(rc, 0, self.output())
        self.assertEqual(len(self.question_files()), questions_before)
        self.assertEqual(len(self.agent_calls()), 1)
        self.assertIn("Arbeitspaket F1", self.log())


class TextAnswerTest(PreflightAssistFixture):
    """Verhalten 10-14: Freitext beauftragt den Agenten im Projektordner."""

    def test_text_answer_runs_agent_in_project_then_starts_package(self):
        """Anweisung behebt den Befund: Agent im Projekt, danach F1 und Exit 0."""
        self.make_dirty()
        instruction = "Räume den Arbeitsbaum auf und entferne unfertig.txt"

        self.start(VIBE_PREFLIGHT_ASSIST="1",
                   VIBE_PREFLIGHT_QUESTION_TIMEOUT="30",
                   FAKE_PREFLIGHT_MODE="fix")
        record = self.wait_for_question()
        self.answer_text(record, instruction)
        rc = self.wait_exit(timeout=120)
        output = self.combined_output()

        self.assertEqual(rc, 0, output)
        calls = self.preflight_calls()
        self.assertEqual(len(calls), 1, calls)
        self.assertEqual(
            os.path.realpath(calls[0]["cwd"]),
            os.path.realpath(str(self.project)),
            "Der Preflight-Agent lief nicht im Projektordner.",
        )
        self.assertIn(instruction, calls[0]["prompt"])
        self.assertIn("Arbeitsbaum", calls[0]["prompt"])
        self.assertIn("unfertig.txt", calls[0]["prompt"])
        self.assertEqual(len(self.package_calls()), 1)
        self.assertIn("Arbeitspaket F1", self.log())
        self.assertIn("Geschlossen: F1", output)
        self.assertEqual(self.open_questions(), [])

    def test_text_wins_over_a_selected_option(self):
        """Option 0 plus Text beauftragt den Agenten statt nur erneut zu prüfen."""
        self.make_dirty()

        self.start(VIBE_PREFLIGHT_ASSIST="1",
                   VIBE_PREFLIGHT_QUESTION_TIMEOUT="30",
                   FAKE_PREFLIGHT_MODE="fix")
        record = self.wait_for_question()
        self.answer_text(
            record, "Bitte den Arbeitsbaum aufräumen", option=0
        )
        rc = self.wait_exit(timeout=120)
        output = self.combined_output()

        self.assertEqual(rc, 0, output)
        self.assertEqual(len(self.preflight_calls()), 1)
        self.assertEqual(len(self.package_calls()), 1)
        self.assertIn("Arbeitspaket F1", self.log())

    def test_failed_agent_run_ends_with_exit_2_and_no_package(self):
        """Agentenfehler: Exit 2, kein Arbeitspaket, Register blocked."""
        run_id = self.create_run_record()
        self.make_dirty()
        args_path = self.root / "preflight-args"
        instruction = "Bitte die Befunde beheben"

        self.start(VIBE_PREFLIGHT_ASSIST="1",
                   VIBE_PREFLIGHT_QUESTION_TIMEOUT="30",
                   FAKE_PREFLIGHT_MODE="fail",
                   FAKE_ARGS_PATH=str(args_path),
                   VIBE_RUN_ID=run_id)
        record = self.wait_for_question()
        self.answer_text(record, instruction)
        rc = self.wait_exit(timeout=60)
        output = self.combined_output()

        self.assertEqual(rc, 2, output)
        self.assertEqual(self.package_calls(), [])
        calls = self.preflight_calls()
        self.assertEqual(len(calls), 1, calls)
        self.assertEqual(
            os.path.realpath(calls[0]["cwd"]),
            os.path.realpath(str(self.project)),
        )
        self.assertIn(instruction, calls[0]["prompt"])
        self.assertIn("Arbeitsbaum", calls[0]["prompt"])
        self.assertRegex(output, r"(?is)agent.{0,160}fehl")
        self.assertRegex(output, r"(?is)exit[- ]?code\s*1|exit 1")

        argv = [part for part in args_path.read_text(
            encoding="utf-8").split("\0") if part]
        self.assertIn("tester", argv, argv)

        stored = self.run_record(run_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored["state"], "blocked")
        self.assertEqual(stored["exit_code"], 2)

    def test_empty_text_with_option_0_retries_without_agent(self):
        """Ohne Text bleibt Option 0 eine reine erneute Prüfung."""
        self.make_dirty()

        self.start(VIBE_PREFLIGHT_ASSIST="1",
                   VIBE_PREFLIGHT_QUESTION_TIMEOUT="30",
                   FAKE_PREFLIGHT_MODE="fix")
        first = self.wait_for_question()
        self.answer(first, 0)
        second = self.wait_for_question(seen={first["id"]})

        self.assertEqual(self.preflight_calls(), [])
        self.assertEqual(self.package_calls(), [])
        self.assertIn("Arbeitsbaum", second.get("text", ""))

        self.answer(second, 1)
        self.assertEqual(self.wait_exit(timeout=60), 2)
        self.assertEqual(self.preflight_calls(), [])

    def test_ten_agent_rounds_then_exit_2(self):
        """Nach zehn Agentenrunden endet die Assistenz mit Exit 2."""
        self.make_dirty()

        self.start(VIBE_PREFLIGHT_ASSIST="1",
                   VIBE_PREFLIGHT_QUESTION_TIMEOUT="30",
                   FAKE_PREFLIGHT_MODE="noop")
        seen = set()
        for round_number in range(1, 11):
            record = self.wait_for_question(seen=seen)
            seen.add(record["id"])
            self.answer_text(record, "Versuch %d" % round_number)
        rc = self.wait_exit(timeout=120)
        output = self.combined_output()

        self.assertEqual(rc, 2, output)
        calls = self.preflight_calls()
        self.assertEqual(len(calls), 10, calls)
        for round_number, call in enumerate(calls, 1):
            self.assertIn("Versuch %d" % round_number, call["prompt"])
        self.assertEqual(self.package_calls(), [])
        self.assertIn("10", output)


# ===========================================================================
# Blockierte Pakete selbst beheben und Reparatur anbieten
# ===========================================================================

import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support


# ``vibe_packages`` lädt für die Assistenz die F16-Module aus ``bin``.
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))
import vibe_questions  # noqa: E402  (Pfad wird oben ergänzt)

PROJECT_ENV_b9 = """TYPE=generic
AGENT=test-agent
TESTER=test-agent
REVIEWER=code-reviewer
VERIFY_PACKAGE="true"
VERIFY_FULL="true"
MAX_RETRIES=1
"""

FEEDBACK_ONE = [support.ticket_record(
    "F1", "Erstes Paket", type="feedback", description="Test")]
FEEDBACK_TWO = FEEDBACK_ONE + [support.ticket_record(
    "F2", "Zweites Paket", type="feedback", description="Test")]

FINAL_VERIFY_ENV = (
    'VERIFY_FULL=\'echo final > "$VIBE_VERIFY_RUNTIME/final-ran"\''
)

OPTIONS = ["Erneut prüfen", "Lauf abbrechen", "Agent behebt die Befunde"]


# ---------------------------------------------------------------------------
# Nachgebildeter Agent: erzeugt Pakete und repariert Befunde kontrolliert.
# ---------------------------------------------------------------------------
B9_FAKE_AGENT = r'''#!/usr/bin/env python3
"""B9-Testagent ohne Modellaufruf.

B9_MODE steuert das Verhalten:

* ``complete``          — vollständiges Paket, sofort schließbar.
* ``fix-tests``         — Paket lässt den Pakettest scheitern; Reparatur behebt ihn.
* ``fix-gate``          — Paket lässt Doku/Review fehlen; Reparatur ergänzt sie.
* ``persist-gate``      — Doku/Review fehlen dauerhaft; Reparatur ändert nichts.
* ``repair-quota``      — Schrankenbefund; die Reparatur endet mit Quota-Fehler.
* ``fix-integration``   — Paket vollständig; Reparatur räumt den Projektordner auf.
"""
import json
import os
import pathlib
import re
import subprocess
import sys

args = sys.argv[1:]
prompt = args[-1] if args else ""
cwd = pathlib.Path.cwd()
mode = os.environ.get("B9_MODE", "complete")
calls_path = os.environ.get("B9_CALLS")


def log_call(kind):
    if not calls_path:
        return
    record = {"kind": kind, "cwd": str(cwd), "prompt": prompt}
    with open(calls_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def run(*command, check=True):
    return subprocess.run(
        list(command), cwd=str(cwd), check=check,
        capture_output=True, text=True,
    )


def commit(message):
    run("git", "add", "-A")
    staged = subprocess.run(["git", "-C", str(cwd), "diff", "--cached",
                             "--quiet"], check=False)
    if staged.returncode != 0:
        run("git", "commit", "-q", "-m", message)
    return run("git", "rev-parse", "--short", "HEAD").stdout.strip()


def mark_done(pid, short):
    """GH-48: schließt die sichtbare TICKET-<ID>.json ab."""
    path = cwd / ("TICKET-" + pid + ".json")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = {"id": pid, "title": pid, "type": "task",
                  "description": ""}
    record.setdefault("type", "task")
    record.update({"id": pid, "state": "done", "commit": short,
                   "test": "test_" + pid.lower().replace("-", "_")})
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")


def write_evidence(pid):
    (cwd / "docs" / "features").mkdir(parents=True, exist_ok=True)
    (cwd / "docs" / "features" / (pid + ".md")).write_text(
        "# " + pid + "\n\nTestdokumentation.\n", encoding="utf-8"
    )
    (cwd / "docs" / "reviews").mkdir(parents=True, exist_ok=True)
    (cwd / "docs" / "reviews" / (pid + "-review-1.md")).write_text(
        "# Review\n\nVerdict: PASS\n", encoding="utf-8"
    )


def complete_package(pid):
    (cwd / ("impl-" + pid + ".txt")).write_text(pid + "\n", encoding="utf-8")
    if mode == "fix-tests":
        (cwd / "package_test_fail.txt").write_text("rot\n", encoding="utf-8")
    short = commit(pid + ": Umsetzung")
    mark_done(pid, short)
    write_evidence(pid)
    commit(pid + ": Nachweis")


def incomplete_package(pid):
    (cwd / ("impl-" + pid + ".txt")).write_text(pid + "\n", encoding="utf-8")
    short = commit(pid + ": Umsetzung")
    mark_done(pid, short)
    commit(pid + ": Teilnachweis")


match = re.search(r"Arbeitspaket\s+([A-Za-z0-9_-]+)", prompt)
pid = match.group(1) if match else "F1"
if not match:
    repair_pid = re.search(r"\b([A-Z][A-Za-z0-9_-]*\d+)\b", prompt)
    if repair_pid:
        pid = repair_pid.group(1)
# Ein Reparaturauftrag darf den Wortlaut des Pakets wiederholen. Sobald die
# Arbeitskopie bereits eine Umsetzung enthält, ist ein weiterer Aufruf keine
# neue Paketbearbeitung, sondern eine Reparatur.
# GH-48: Der Paket-Prompt enthält keinen "Wortlaut:"-Block mehr, sondern
# verweist auf TICKET-<ID>.json. Ein Reparaturauftrag nennt "Reparatur".
is_package = (
    "Arbeitspaket " in prompt
    and "Reparatur" not in prompt
    and not (cwd / ("impl-" + pid + ".txt")).exists()
)

if is_package:
    log_call("package")
    if mode in ("fix-gate", "persist-gate", "repair-quota"):
        incomplete_package(pid)
    else:
        complete_package(pid)
    sys.exit(0)

log_call("repair")
if mode == "fix-integration":
    target = cwd / "unfertig.txt"
    try:
        target.unlink()
    except FileNotFoundError:
        pass
    run("git", "add", "-A")
    staged = subprocess.run(
        ["git", "-C", str(cwd), "diff", "--cached", "--quiet"],
        check=False,
    )
    if staged.returncode != 0:
        commit("Reparatur: Integrationsstand")
    sys.exit(0)
if mode == "fix-tests":
    target = cwd / "package_test_fail.txt"
    try:
        target.unlink()
    except FileNotFoundError:
        pass
    commit(pid + ": Pakettest repariert")
    sys.exit(0)
if mode == "fix-gate":
    write_evidence(pid)
    commit(pid + ": Reparatur")
    sys.exit(0)
if mode == "repair-quota":
    print("429 rate limit: quota exceeded", file=sys.stderr)
    sys.exit(1)
# persist-gate: absichtlich nichts beheben.
sys.exit(0)
'''


def install_b9_fake_tools(root):
    """Legt opencode-, package-agent- und curl-Attrappen in einem PATH ab."""
    fakebin = root / "fakebin"
    fakebin.mkdir(parents=True, exist_ok=True)
    for name in ("opencode", "package-agent"):
        path = fakebin / name
        path.write_text(B9_FAKE_AGENT, encoding="utf-8")
        path.chmod(0o755)
    curl = fakebin / "curl"
    curl.write_text(support.FAKE_CURL, encoding="utf-8")
    curl.chmod(0o755)
    return fakebin


# GH-48: Der alte Markdown-Gate-Parser (mehrere Commit-Hashes, umbrochene
# Fortsetzungszeilen, Feldgrenzen im Text) ist entfernt. Die Schranke liest
# genau ein commit-Feld aus TICKET-<ID>.json; die Aussagen tragen
# tests/unit/test_package_gates.py und tests/unit/test_gh48_runner_tickets.py.


# ---------------------------------------------------------------------------
# (b) F16-Preflight-Rückfrage: drei Optionen und Aktion ``agent``
# ---------------------------------------------------------------------------
class AssistUnitFixture(unittest.TestCase):
    """Direkter Aufruf der Preflight-Assistenz mit echten F16-Rückfragen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.state = self.root / "state"
        self.state.mkdir()
        self.runtime = self.root / "_logs"
        self.project = self.root / "proj"
        support.init_repo(self.project)
        support.write_project(
            self.project, PROJECT_ENV_b9, feedback=FEEDBACK_ONE
        )
        support.commit_all(self.project, "Ausgangsstand")
        (self.project / "unfertig.txt").write_text(
            "unfertig\n", encoding="utf-8"
        )
        self.packages = load_module(
            PACKAGES, "vibe_packages_b9_assist"
        )
        self.old_lock = os.environ.get("VIBE_STORAGE_LOCK_DIR")
        os.environ["VIBE_STORAGE_LOCK_DIR"] = str(self.root / "locks")

    def tearDown(self):
        if self.old_lock is None:
            os.environ.pop("VIBE_STORAGE_LOCK_DIR", None)
        else:
            os.environ["VIBE_STORAGE_LOCK_DIR"] = self.old_lock
        self.tmp.cleanup()

    def start(self, timeout=20):
        result = {}

        def run():
            result.update(
                self.packages.assist_preflight(
                    str(self.project),
                    str(self.agents),
                    "test-agent",
                    "code-reviewer",
                    state_dir=str(self.state),
                    runtime=str(self.runtime),
                    project_name="proj",
                    timeout=timeout,
                )
            )

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return result, thread

    def wait_question(self, seen=(), timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for record in vibe_questions.open_questions(
                str(self.runtime)
            ):
                if record["id"] not in seen:
                    return record
            time.sleep(0.02)
        raise AssertionError("Keine Rückfrage innerhalb von %s s." % timeout)

    def answer(self, record, option, text=""):
        vibe_questions.answer(
            str(self.runtime), record["id"], option=option,
            text=text, by="test",
        )

    def join(self, thread):
        thread.join(10)
        self.assertFalse(thread.is_alive(), "Assistenz wartete weiter")

    def enable_autonomous(self, name="proj"):
        """Schaltet den autonomen Modus für den Projektnamen ein (F16)."""
        payload = {
            "version": 1,
            "projects": {
                name: {
                    "enabled": True,
                    "changed": "2026-01-01T00:00:00Z",
                }
            },
        }
        self.runtime.mkdir(parents=True, exist_ok=True)
        temporary = self.runtime / ".autonomous.json.tmp"
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(temporary, self.runtime / "autonomous.json")

    def question_files(self):
        folder = self.runtime / "questions"
        if not folder.is_dir():
            return []
        return sorted(
            path
            for path in folder.iterdir()
            if path.name.endswith(".json")
            and not path.name.endswith(".answer.json")
        )


class PreflightAssistOptionsTest(AssistUnitFixture):
    """Verhalten 1-3: feste Reihenfolge, Aktion ``agent`` und Vorrang."""

    def test_assist_offers_three_options_and_option_two_returns_agent_action(self):
        """Option 2 liefert eine aus den Befunden abgeleitete Anweisung."""
        result, thread = self.start()
        record = self.wait_question()

        self.assertEqual(record.get("options"), OPTIONS)

        self.answer(record, 2)
        self.join(thread)

        self.assertEqual(result.get("action"), "agent", result)
        instruction = result.get("instruction", "")
        self.assertTrue(instruction, result)
        self.assertIn("Arbeitsbaum", instruction)
        self.assertIn("unfertig.txt", instruction)

    def test_free_text_wins_over_option_two(self):
        """Freitext ersetzt die Befund-Anweisung auch bei Option 2."""
        result, thread = self.start()
        record = self.wait_question()
        text = "Bitte nur die Notizen prüfen, nichts committen"

        self.answer(record, 2, text)
        self.join(thread)

        self.assertEqual(result.get("action"), "agent", result)
        self.assertEqual(result.get("instruction"), text)

    def test_option_zero_retries_and_option_one_aborts(self):
        """0 prüft erneut (neue Rückfrage), 1 bricht ohne Agentenauftrag ab."""
        result, thread = self.start()
        first = self.wait_question()
        self.assertEqual(first.get("options"), OPTIONS)

        self.answer(first, 0)
        second = self.wait_question(seen={first["id"]})
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(second.get("options"), OPTIONS)

        self.answer(second, 1)
        self.join(thread)

        self.assertEqual(result.get("action"), "abort", result)


class PreflightAutonomousRepairTest(AssistUnitFixture):
    """Verhalten 1 und 4: Autonomer Modus liefert einen Reparaturauftrag.

    Ist der autonome Modus aktiv, entsteht keine F16-Rückfrage und es wird
    nicht gewartet. Die Assistenz liefert stattdessen die Aktion ``agent`` mit
    einer aus den Befunden abgeleiteten Anweisung und der Herkunft
    ``autonomous``. Dasselbe gilt, wenn der Modus erst während des Wartens
    eingeschaltet wird.
    """

    def test_autonomous_active_returns_agent_instruction_without_question(self):
        """Aktiver Modus vor dem Start: kein Warten, Auftrag aus Befunden."""
        self.enable_autonomous()

        result, thread = self.start()
        self.join(thread)

        self.assertEqual(self.question_files(), [])
        self.assertEqual(result.get("action"), "agent", result)
        self.assertEqual(result.get("source"), "autonomous", result)
        instruction = result.get("instruction", "")
        self.assertTrue(instruction, result)
        self.assertIn("Arbeitsbaum", instruction)
        self.assertIn("unfertig.txt", instruction)

    def test_switching_autonomous_during_wait_returns_agent_instruction(self):
        """Während des Wartens eingeschaltet: Warten endet, Auftrag entsteht."""
        result, thread = self.start()
        record = self.wait_question()
        self.assertEqual(record.get("options"), OPTIONS)

        self.enable_autonomous()
        self.join(thread)

        self.assertEqual(result.get("action"), "agent", result)
        self.assertEqual(result.get("source"), "autonomous", result)
        instruction = result.get("instruction", "")
        self.assertTrue(instruction, result)
        self.assertIn("Arbeitsbaum", instruction)
        self.assertIn("unfertig.txt", instruction)

    def test_missing_f16_modules_returns_unavailable(self):
        """Ohne nutzbare F16-Module bleibt der bisherige Zustand ``unavailable``."""
        with mock.patch.object(
            self.packages, "_question_modules", return_value=(None, None)
        ):
            result = self.packages.assist_preflight(
                str(self.project),
                str(self.agents),
                "test-agent",
                "code-reviewer",
                state_dir=str(self.state),
                runtime=str(self.runtime),
                project_name="proj",
                timeout=5,
            )

        self.assertEqual(result.get("action"), "unavailable", result)
        self.assertTrue(result.get("errors"), result)
        self.assertEqual(self.question_files(), [])


# ---------------------------------------------------------------------------
# Gemeinsamer Läufer mit echtem Git und nachgebildeter opencode-Ablage
# ---------------------------------------------------------------------------
class B9RunnerFixture(unittest.TestCase):
    """Isolierter ``bin/vibe-run.sh`` ohne Modell- oder Netzaufrufe."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        (self.tool_bin / "vibe").write_text(
            support.FAKE_VIBE, encoding="utf-8"
        )
        (self.tool_bin / "vibe").chmod(0o755)
        self.runtime = self.root / "_logs"
        self.state = self.root / "state"
        self.state.mkdir()
        self.calls_path = self.root / "b9-calls.jsonl"
        self.fakebin = install_b9_fake_tools(self.root)
        self.project = None
        self.proc = None
        self.out_path = None
        self.handles = []
        self.run_count = 0

    def tearDown(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()
        for handle in self.handles:
            handle.close()
        self.tmp.cleanup()

    def make_project(self, env_text=PROJECT_ENV_b9, feedback=FEEDBACK_ONE,
                     name="proj"):
        project = self.root / name
        support.init_repo(project)
        support.write_project(project, env_text, feedback=feedback)
        support.commit_all(project, "Ausgangsstand")
        self.project = project
        return project

    def env(self, project, **extra):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_") \
                    or key.startswith("B9_"):
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
                "VIBE_PREFLIGHT_QUESTION_TIMEOUT": "15",
                "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
                "VIBE_STORAGE_LOCK_DIR": str(self.home / "locks"),
                "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
                "B9_CALLS": str(self.calls_path),
                "B9_MODE": "complete",
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

    def start_runner(self, project, **extra):
        self.out_path = self.root / ("runner-%d.out" % self.run_count)
        self.run_count += 1
        handle = self.out_path.open("w", encoding="utf-8")
        self.handles.append(handle)
        self.proc = subprocess.Popen(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(project)],
            cwd=str(project),
            env=self.env(project, **extra),
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return self.proc

    def output(self):
        if self.out_path is None or not self.out_path.exists():
            return ""
        return self.out_path.read_text(encoding="utf-8", errors="replace")

    def log(self, project=None):
        project = project or self.project
        path = self.runtime / (project.name + ".log")
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def combined(self, result):
        return result.stdout + result.stderr + "\n" + self.log()

    def wait_exit(self, timeout=90):
        try:
            return self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
            raise AssertionError(
                "Läufer lief nach %s s weiter.\n%s" % (timeout, self.output())
            )

    def calls(self):
        if not self.calls_path.is_file():
            return []
        result = []
        for line in self.calls_path.read_text(
            encoding="utf-8"
        ).splitlines():
            if line.strip():
                result.append(json.loads(line))
        return result

    def kinds(self):
        return [call["kind"] for call in self.calls()]

    def question_folder(self):
        return self.runtime / "questions"

    def question_files(self):
        folder = self.question_folder()
        if not folder.is_dir():
            return []
        return sorted(
            path
            for path in folder.iterdir()
            if path.name.endswith(".json")
            and not path.name.endswith(".answer.json")
        )

    def open_questions(self):
        folder = self.question_folder()
        result = []
        for path in self.question_files():
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(record, dict) or "id" not in record:
                continue
            if (folder / (record["id"] + ".answer.json")).exists():
                continue
            result.append(record)
        return result

    def wait_for_question(self, seen=(), timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for record in self.open_questions():
                if record["id"] not in seen:
                    return record
            if self.proc.poll() is not None:
                time.sleep(0.2)
                for record in self.open_questions():
                    if record["id"] not in seen:
                        return record
                raise AssertionError(
                    "Läufer endete ohne erwartete Rückfrage (Exit %s):\n%s"
                    % (self.proc.returncode, self.output())
                )
            time.sleep(0.05)
        raise AssertionError(
            "Keine Rückfrage innerhalb von %s s.\n%s"
            % (timeout, self.output())
        )

    def answer(self, record, option, text=""):
        folder = self.question_folder()
        folder.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "option": option,
                "text": text,
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "by": "test",
            }
        ) + "\n"
        target = folder / (record["id"] + ".answer.json")
        temporary = folder / (".answer-" + record["id"] + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, target)

    def worktrees(self):
        return [
            path
            for path in (self.runtime / "worktrees").glob("*")
            if path.is_dir()
        ]

    def head(self, project):
        return support.git(
            project, "rev-parse", "HEAD"
        ).stdout.strip()

    def make_dirty(self, project, name="unfertig.txt"):
        path = project / name
        path.write_text("unfertig\n", encoding="utf-8")
        return path


class RunnerPreflightOptionTest(B9RunnerFixture):
    """Option 2 startet den Agenten im Projektordner und danach das Paket."""

    def test_preflight_option_two_runs_the_agent_in_the_project(self):
        project = self.make_project()
        self.make_dirty(project)

        self.start_runner(
            project, VIBE_PREFLIGHT_ASSIST="1", B9_MODE="fix-integration"
        )
        record = self.wait_for_question()

        self.assertEqual(record.get("options"), OPTIONS)
        self.answer(record, 2)
        rc = self.wait_exit(timeout=120)

        self.assertEqual(rc, 0, self.output())
        calls = self.calls()
        self.assertEqual([call["kind"] for call in calls], ["repair", "package"])
        self.assertEqual(
            os.path.realpath(calls[0]["cwd"]),
            os.path.realpath(str(project)),
            "Der Preflight-Agent lief nicht im Projektordner.",
        )
        self.assertIn("Arbeitsbaum", calls[0]["prompt"])
        self.assertIn("unfertig.txt", calls[0]["prompt"])
        self.assertFalse((project / "unfertig.txt").exists())
        self.assertIn("Geschlossen: F1", self.output())
        # Option 2 nutzt die aus den Befunden abgeleitete Anweisung; das
        # Laufprotokoll darf sie nicht als Nutzeranweisung ausgeben.
        self.assertIn(
            "Befunden abgeleiteten Anweisung",
            self.output(),
            "Das Protokoll unterscheidet die Befund-Anweisung nicht.",
        )
        self.assertNotIn(
            "Anweisung des Nutzers",
            self.output(),
            "Option 2 wurde als Nutzeranweisung protokolliert.",
        )


class RunnerPackageRepairTest(B9RunnerFixture):
    """Verhalten 4-6: Pakettest- und Schrankenbefunde im Läufer."""

    def test_gate_finding_is_repaired_in_the_same_worktree_and_merged(self):
        project = self.make_project()
        base = self.head(project)

        result = self.run_runner(
            project, B9_MODE="fix-gate", VIBE_MAX_PACKAGES="1"
        )
        output = self.combined(result)

        self.assertEqual(result.returncode, 0, output)
        calls = self.calls()
        self.assertEqual([call["kind"] for call in calls], ["package", "repair"])
        self.assertEqual(
            os.path.realpath(calls[0]["cwd"]),
            os.path.realpath(calls[1]["cwd"]),
            "Die Reparatur lief nicht im selben Arbeitsbaum.",
        )
        self.assertIn("docs/features/F1.md", calls[1]["prompt"])
        self.assertNotEqual(self.head(project), base, "Paket wurde nicht gemergt")
        merged = support.git(project, "cat-file", "-e", "HEAD:impl-F1.txt")
        self.assertEqual(merged.returncode, 0, merged.stderr)
        self.assertIn("Geschlossen: F1", result.stdout)
        self.assertEqual(self.worktrees(), [], "Arbeitskopie blieb liegen")

    def test_package_test_finding_is_repaired_in_the_same_worktree_and_merged(self):
        env_text = PROJECT_ENV_b9.replace(
            'VERIFY_PACKAGE="true"',
            'VERIFY_PACKAGE="test ! -f package_test_fail.txt"',
        )
        project = self.make_project(env_text=env_text)

        result = self.run_runner(
            project, B9_MODE="fix-tests", VIBE_MAX_PACKAGES="1"
        )
        output = self.combined(result)

        self.assertEqual(result.returncode, 0, output)
        calls = self.calls()
        self.assertEqual([call["kind"] for call in calls], ["package", "repair"])
        self.assertEqual(
            os.path.realpath(calls[0]["cwd"]),
            os.path.realpath(calls[1]["cwd"]),
            "Die Reparatur lief nicht im selben Arbeitsbaum.",
        )
        prompt = calls[1]["prompt"]
        self.assertIn("F1", prompt)
        self.assertRegex(
            prompt, r"(?i)(pakettest|paketprüfung|package_test_fail|nicht grün)"
        )
        self.assertFalse(
            (project / "package_test_fail.txt").exists(),
            "Reparatur wurde nicht gemergt.",
        )
        self.assertIn("Geschlossen: F1", result.stdout)

    def test_persistent_gate_finding_blocks_after_two_repairs_without_merge(self):
        project = self.make_project(feedback=FEEDBACK_TWO)
        base = self.head(project)

        result = self.run_runner(
            project, B9_MODE="persist-gate", VIBE_MAX_PACKAGES="2"
        )
        output = self.combined(result)
        calls = self.calls()

        self.assertEqual(result.returncode, 1, output)
        self.assertEqual(
            [call["kind"] for call in calls],
            ["package", "repair", "repair"],
            "Es wurden nicht genau zwei Reparaturrunden versucht.",
        )
        self.assertEqual(
            len({os.path.realpath(call["cwd"]) for call in calls}),
            1,
            "Die Reparaturrunden liefen nicht im selben Arbeitsbaum.",
        )
        self.assertIn("docs/features/F1.md", calls[1]["prompt"])
        self.assertIn("docs/features/F1.md", calls[2]["prompt"])

        # Kein Merge und kein neues Paket.
        self.assertEqual(self.head(project), base, "Trotz Befund wurde gemergt")
        # ``cat-file -e`` liefert je nach Git-Version 1 oder 128 für einen
        # fehlenden Pfad; entscheidend ist der Nicht-Null-Status.
        self.assertNotEqual(
            support.git(project, "cat-file", "-e", "HEAD:impl-F1.txt").returncode,
            0,
        )
        self.assertNotIn("Geschlossen: F1", result.stdout)
        self.assertFalse(
            any("Arbeitspaket F2" in call["prompt"] for call in calls),
            "Nach dem Befund wurde ein neues Paket gestartet.",
        )
        self.assertIn("BLOCKIERT", output)
        self.assertIn("docs/features/F1.md", output)

    def test_quota_during_repair_blocks_without_second_round_and_names_quota(self):
        """Quota beim Reparatur-Agenten blockiert sofort und ohne zweite Runde."""
        project = self.make_project()
        base = self.head(project)

        result = self.run_runner(
            project, B9_MODE="repair-quota", VIBE_MAX_PACKAGES="1"
        )
        output = self.combined(result)
        calls = self.calls()

        self.assertEqual(result.returncode, 1, output)
        self.assertEqual(
            [call["kind"] for call in calls],
            ["package", "repair"],
            "Nach dem Quota-Fehler wurde eine weitere Reparaturrunde gestartet.",
        )
        self.assertEqual(self.head(project), base, "Trotz Quota-Fehler wurde gemergt")
        self.assertNotEqual(
            support.git(project, "cat-file", "-e", "HEAD:impl-F1.txt").returncode,
            0,
        )
        # Die Quota-Meldung des Agenten steht zwar im Protokoll; entscheidend
        # ist die Klassifizierung durch den Läufer in der BLOCKIERT-Zeile.
        self.assertRegex(
            output,
            r"(?im)^BLOCKIERT:.*(?:Quota|Kontingent)",
            "Der Läufer nennt die Quota-Klassifizierung nicht: %s" % output,
        )


class RunnerIntegrationAssistTest(B9RunnerFixture):
    """Verhalten 7-9: unsauberer Stand am Laufende."""

    def make_integration_project(self):
        env_text = PROJECT_ENV_b9.replace(
            'VERIFY_FULL="true"', FINAL_VERIFY_ENV
        )
        project = self.make_project(env_text=env_text)
        self.make_dirty(project)
        return project

    def start(self, project, assist):
        extra = {
            "VIBE_KEEP_CHANGES": "1",
            "VIBE_MAX_PACKAGES": "1",
            "B9_MODE": "fix-integration",
        }
        if assist:
            extra["VIBE_PREFLIGHT_ASSIST"] = "1"
        self.start_runner(project, **extra)

    def test_dirty_integration_is_repaired_with_assistance_and_final_check_runs(
        self,
    ):
        project = self.make_integration_project()
        marker = self.runtime / "final-ran"

        self.start(project, assist=True)
        record = self.wait_for_question()

        self.assertEqual(record.get("options"), OPTIONS)
        self.answer(record, 2)
        rc = self.wait_exit(timeout=120)
        output = self.output()

        self.assertEqual(rc, 0, output)
        calls = self.calls()
        self.assertEqual([call["kind"] for call in calls], ["package", "repair"])
        self.assertEqual(
            os.path.realpath(calls[1]["cwd"]),
            os.path.realpath(str(project)),
            "Die Reparatur lief nicht im Projektordner.",
        )
        self.assertIn("unfertig.txt", calls[1]["prompt"])
        self.assertRegex(
            calls[1]["prompt"],
            r"(?i)(integrationsstand|arbeitsbaum|nicht sauber)",
        )
        self.assertFalse((project / "unfertig.txt").exists())
        self.assertTrue(marker.is_file(), "Abschlussprüfung lief nicht")
        self.assertEqual(
            support.git(project, "status", "--porcelain").stdout, ""
        )

    def test_dirty_integration_abort_keeps_the_block(self):
        project = self.make_integration_project()
        marker = self.runtime / "final-ran"

        self.start(project, assist=True)
        record = self.wait_for_question()
        self.answer(record, 1)
        rc = self.wait_exit(timeout=120)
        output = self.output()

        self.assertEqual(rc, 1, output)
        self.assertEqual([call["kind"] for call in self.calls()], ["package"])
        self.assertFalse(marker.exists(), "Abschlussprüfung lief trotz Abbruch")
        self.assertIn("Integrationsstand ist nicht sauber", output)
        self.assertTrue((project / "unfertig.txt").exists())

    def test_dirty_integration_without_assistance_keeps_the_block(self):
        project = self.make_integration_project()
        marker = self.runtime / "final-ran"

        self.start(project, assist=False)
        rc = self.wait_exit(timeout=120)
        output = self.output()

        self.assertEqual(rc, 1, output)
        self.assertEqual([call["kind"] for call in self.calls()], ["package"])
        self.assertEqual(self.question_files(), [])
        self.assertFalse(marker.exists(), "Abschlussprüfung lief ohne Assistenz")
        self.assertIn("Integrationsstand ist nicht sauber", output)


if __name__ == "__main__":
    unittest.main()
