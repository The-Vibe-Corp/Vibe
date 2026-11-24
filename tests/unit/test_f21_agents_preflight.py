"""F21: UI-konfigurierte Agenten für den Lauf freigeben.

Die Tests leiten das Verhalten aus dem Arbeitspaket ab, nicht aus dem
Implementierungsdiff:

* Der Preflight ergänzt einen fehlenden REVIEWER aus der Rolle ``reviewer``
  in ``<state>/profiles.json``.
* Ein ausdrücklich gesetzter REVIEWER (Argument oder project.env) bleibt
  vorrangig.
* Bei mehreren reviewer-Rollen gewinnt ein verfügbarer Agent; ein veralteter
  Eintrag blockiert nicht.
* Ohne reviewer-Rolle oder ohne verfügbaren Rollenagenten bleibt der Preflight
  mit einer REVIEWER-Meldung blockiert; kaputte profiles.json stürzt nicht ab.
* ``blocked`` ist ein gültiger Lauf-Endzustand, unbekannte Zustände bleiben
  ungültig.
* Ein unsauberer Arbeitsbaum blockiert weiterhin.
* Der echte ``bin/vibe-run.sh`` kommt ohne REVIEWER in project.env über den
  Preflight, wenn profiles.json die Rolle auflöst (Integrationstest).

Es werden keine Modelle, Router oder echten externen Dienste aufgerufen.
"""
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


if __name__ == "__main__":
    unittest.main()
