"""Projektagenten: Modellauswahl, Reparatur beim Start und Vorlagen-Vorgaben.

Aufruf: python3 -m unittest tests.unit.test_project_agents -v
"""


import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"
RUNNER = BIN / "vibe-run.sh"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support

GLOBAL_AGENT = """---
description: Globaler Agent
mode: subagent
model: opencode/global-modell
permission:
  read: allow
  edit: deny
---

Globaler Prompt.
"""

PROJECT_AGENT = """---
description: Projektagent
mode: subagent
model: opencode/projekt-modell
permission:
  read: allow
  edit: deny
---

Projekt-Prompt.
"""

OTHER_AGENT = """---
description: Agent eines anderen Projekts
mode: subagent
model: opencode/fremd-modell
permission:
  read: allow
  edit: deny
---

Fremder Prompt.
"""

VIBE_AGENT = """---
description: Vibe-Standardagent
mode: primary
model: opencode/vibe-modell
permission:
  read: allow
  edit: deny
---

Vibe-Prompt.
"""

ISOLATED_ENV = (
    "VIBE",
    "VIBE_NO_CONTAINER",
    "HOME",
    "VIBE_STORAGE_LOCK_DIR",
    "VIBE_PROFILE",
    "VIBE_INSTALL",
    "VIBE_RUNTIME",
    "VIBE_STATE",
    "VIBE_AGENTS_DIR",
    "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR",
    "VIBE_UI_PORT",
    "VIBE_OPENCODE_PORT",
    "VIBE_UI_BIND",
    "VIBE_CONTAINER",
    # Die Läuferumgebung setzt VIBE_MODEL (autonomer Lauf); ohne Bereinigung
    # gäbe der Läufer unerwartet --model an opencode weiter.
    "VIBE_MODEL",
    "MAX_PACKAGES",
    "VERIFY_QUICK",
    "VERIFY_FULL",
    "AGENT",
    "SANDBOX",
    "SANDBOX_TOOLS",
)


def isolated_env(root, home):
    """Umgebung, die ausschließlich im temporären Prüfverzeichnis arbeitet."""
    env = os.environ.copy()
    for key in ISOLATED_ENV:
        env.pop(key, None)
    env.update(
        {
            "VIBE": str(root),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(home),
            "VIBE_STATE": str(Path(root) / "_toolchain"),
            "VIBE_AGENTS_DIR": str(Path(home) / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(Path(home) / ".config" / "vibe" / "config.json"),
        }
    )
    return env


def load_cli(vibe_root, home):
    """Lädt bin/vibe mit isoliertem VIBE/HOME, ohne main() auszuführen."""
    old = {key: os.environ.get(key) for key in ISOLATED_ENV}
    for key in ISOLATED_ENV:
        os.environ.pop(key, None)
    os.environ.update(isolated_env(vibe_root, home))
    os.environ["VIBE_STORAGE_LOCK_DIR"] = str(Path(vibe_root) / "locks")
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_project_agents_under_test", str(CLI)
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


class ProjectAgentsFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        self.agents.mkdir(parents=True)
        self.project = self.make_project("proj")
        self.other = self.make_project("other")
        self.cli = load_cli(self.root, self.home)
        self.cli._AGENT_VERSION = None
        # Kein opencode-Prozess und keine Anbieterabfrage in der Prüfung.
        models = mock.patch.object(self.cli, "models_list", return_value=[])
        models.start()
        self.addCleanup(models.stop)

    def tearDown(self):
        self.cli._AGENT_VERSION = None
        self.tmp.cleanup()

    def make_project(self, name):
        project = self.root / name
        (project / ".vibe").mkdir(parents=True)
        (project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8"
        )
        return project

    def write_agent(self, folder, name, text):
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def write_global(self, name="tester", text=GLOBAL_AGENT):
        return self.write_agent(self.agents, name, text)

    def write_vibe(self):
        """Legt den reservierten Vibe-Agenten samt Rolle an (AP03)."""
        path = self.write_global("vibe-agent", VIBE_AGENT)
        data = self.cli.profiles_load()
        data["rollen"] = dict(data.get("rollen", {}))
        data["rollen"]["vibe-agent"] = "vibe"
        self.cli.profiles_save(data)
        return path

    def write_project_agent(self, project, name="tester", text=PROJECT_AGENT):
        return self.write_agent(project / ".opencode" / "agents", name, text)

    def config_path(self, project):
        return project / ".vibe" / "agents.json"

    def rows(self, project="proj"):
        return {row["name"]: row for row in self.cli.project_agent_rows(project)}

    def select(self, project, agent, selected=None, model=None):
        return self.cli.project_agent_set(project, agent, selected=selected, model=model)


class SelectionTest(ProjectAgentsFixture):
    def test_default_selection_uses_the_vibe_agent_and_opencode_agents(self):
        self.write_vibe()
        self.write_global()
        self.write_project_agent(self.project, "pruefer", PROJECT_AGENT)
        self.write_project_agent(self.other, "fremd", OTHER_AGENT)

        rows = self.rows()

        # AP03: Projekte dürfen nur systemweite Agenten verwenden. Der
        # projektlokale Agent wird nicht angeboten; ohne .vibe/agents.json ist
        # ausschließlich der Vibe-Agent konfiguriert. AP2-Korbat ergänzt die
        # opencode-eigenen Agenten general/explore als keine Dateiagenten.
        self.assertEqual(
            sorted(rows), ["explore", "general", "tester", "vibe-agent"]
        )
        self.assertTrue(rows["vibe-agent"]["configured"])
        self.assertTrue(rows["vibe-agent"]["is_vibe"])
        self.assertFalse(rows["tester"]["configured"])
        self.assertFalse(rows["tester"]["selected"])
        self.assertEqual(rows["vibe-agent"]["model"], "opencode/vibe-modell")
        self.assertEqual(rows["vibe-agent"]["override"], "")
        self.assertNotIn("pruefer", rows)
        for name in ("general", "explore"):
            self.assertIs(rows[name].get("opencode"), True)
            self.assertTrue(rows[name]["configured"])
            self.assertEqual(rows[name]["effective_model"], "")
        # Die Auswahl ist reine Konfiguration: ohne Änderung entsteht keine Datei.
        self.assertFalse(self.config_path(self.project).exists())

    def test_project_local_agent_does_not_shadow_the_global_agent(self):
        self.write_vibe()
        self.write_global()
        self.write_project_agent(self.project)

        rows = self.rows()

        self.assertEqual(
            sorted(rows), ["explore", "general", "tester", "vibe-agent"]
        )
        self.assertEqual(rows["tester"]["scope"], "global")
        self.assertEqual(rows["tester"]["model"], "opencode/global-modell")

    def test_deselected_agent_is_stored_for_one_project_only(self):
        self.write_vibe()
        self.write_global()

        self.select("proj", "tester", selected=True)
        self.select("proj", "tester", selected=False)

        self.assertFalse(self.rows("proj")["tester"]["configured"])
        # Das andere Projekt hat keine eigene Datei: dort ist ebenfalls nur der
        # Vibe-Agent konfiguriert, die Abwahl wirkt also nur im gewählten Projekt.
        self.assertFalse(self.rows("other")["tester"]["configured"])
        stored = json.loads(self.config_path(self.project).read_text(encoding="utf-8"))
        self.assertEqual(stored["version"], 3)
        self.assertNotIn("tester", stored["aktiv"])
        self.assertIn("vibe-agent", stored["aktiv"])
        # Das andere Projekt bleibt ohne eigene Datei und unverändert.
        self.assertFalse(self.config_path(self.other).exists())

    def test_model_override_wins_over_the_agent_file_and_can_be_cleared(self):
        self.write_vibe()
        self.write_global()

        self.select("proj", "tester", selected=True, model="opencode/projekt-speziell")

        row = self.rows("proj")["tester"]
        self.assertEqual(row["model"], "opencode/global-modell")
        self.assertEqual(row["override"], "opencode/projekt-speziell")
        self.assertEqual(row["effective_model"], "opencode/projekt-speziell")
        self.assertEqual(self.rows("other")["tester"]["override"], "")

        self.select("proj", "tester", model="")

        row = self.rows("proj")["tester"]
        self.assertEqual(row["override"], "")
        self.assertEqual(row["effective_model"], "opencode/global-modell")
        stored = json.loads(self.config_path(self.project).read_text(encoding="utf-8"))
        self.assertEqual(stored["modelle"], {})

    def test_agent_of_another_project_cannot_be_selected(self):
        self.write_global()
        self.write_project_agent(self.other, "fremd", OTHER_AGENT)
        before = sorted(self.rows())

        with self.assertRaises(ValueError) as caught:
            self.select("proj", "fremd", selected=False)

        self.assertIn("nicht verfügbar", str(caught.exception))
        self.assertEqual(sorted(self.rows()), before)
        self.assertFalse(self.config_path(self.project).exists())

    def test_invalid_model_is_rejected_without_writing(self):
        self.write_global()

        with self.assertRaises(ValueError) as caught:
            self.select("proj", "tester", model="kein modell mit leerzeichen")

        self.assertIn("Modell", str(caught.exception))
        self.assertFalse(self.config_path(self.project).exists())

    def test_non_string_model_is_rejected_without_writing(self):
        self.write_global()

        with self.assertRaises(ValueError) as caught:
            self.select("proj", "tester", model=123)

        self.assertIn("Zeichenkette", str(caught.exception))
        self.assertFalse(self.config_path(self.project).exists())

    def test_non_boolean_selection_is_rejected_without_writing(self):
        self.write_global()

        with self.assertRaises(ValueError) as caught:
            self.select("proj", "tester", selected="nein")

        self.assertIn("wahr oder falsch", str(caught.exception))
        self.assertFalse(self.config_path(self.project).exists())

    def test_corrupt_config_is_reported_and_never_overwritten(self):
        self.write_global()
        path = self.config_path(self.project)
        path.write_text("{kaputt", encoding="utf-8")

        with self.assertRaises(ValueError) as caught:
            self.rows()

        self.assertIn("kein gültiges JSON", str(caught.exception))
        with self.assertRaises(ValueError):
            self.select("proj", "tester", selected=False)
        self.assertEqual(path.read_text(encoding="utf-8"), "{kaputt")

    def test_unknown_config_keys_are_rejected_instead_of_dropped(self):
        self.write_global()
        path = self.config_path(self.project)
        path.write_text(
            json.dumps(
                {"version": 3, "aktiv": [], "modelle": {}, "farbe": "rot"}
            ),
            encoding="utf-8",
        )

        with self.assertRaises(ValueError) as caught:
            self.rows()

        self.assertIn("farbe", str(caught.exception))
        self.assertIn("farbe", path.read_text(encoding="utf-8"))

    def test_non_string_model_in_the_file_is_reported(self):
        self.write_global()
        path = self.config_path(self.project)
        path.write_text(
            json.dumps(
                {"version": 3, "aktiv": ["tester"], "modelle": {"tester": 5}}
            ),
            encoding="utf-8",
        )

        with self.assertRaises(ValueError) as caught:
            self.rows()

        self.assertIn("Zeichenkette", str(caught.exception))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["modelle"]["tester"], 5)

    def test_concurrent_change_is_refused(self):
        self.write_vibe()
        self.write_global()
        path = self.config_path(self.project)
        path.write_text(
            json.dumps(
                {"version": 3, "aktiv": ["vibe-agent", "tester"], "modelle": {}}
            ),
            encoding="utf-8",
        )
        snapshot = self.cli.vibe_storage.read_snapshot(path)
        path.write_text(
            json.dumps({"version": 3, "aktiv": ["vibe-agent"], "modelle": {}}),
            encoding="utf-8",
        )

        with self.assertRaises(self.cli.vibe_storage.ConcurrentChangeError):
            self.cli.project_agents_save(
                "proj",
                {"version": 3, "aktiv": ["vibe-agent", "tester"], "modelle": {}},
                expected=snapshot.digest,
            )

        stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(stored["aktiv"], ["vibe-agent"])

    def test_cli_lists_selection_and_override(self):
        self.write_vibe()
        self.write_global()
        self.select(
            "proj", "tester", selected=True, model="opencode/projekt-speziell"
        )

        result = subprocess.run(
            [sys.executable, str(CLI), "project-agents", "proj"],
            cwd=str(self.root),
            env=isolated_env(self.root, self.home),
            capture_output=True,
            text=True,
            timeout=60,
        )

        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn("tester", output)
        self.assertIn("opencode/projekt-speziell", output)


class RunSelectionTest(ProjectAgentsFixture):
    def test_run_selection_rejects_a_deselected_agent(self):
        self.write_vibe()
        self.write_global()
        self.select("proj", "tester", selected=True)
        self.select("proj", "tester", selected=False)

        with self.assertRaises(ValueError) as caught:
            self.cli.run_agent_selection("proj", "tester")

        message = str(caught.exception).lower()
        self.assertIn("tester", message)
        self.assertIn("nicht", message)

    def test_run_selection_allows_a_configured_agent_without_override(self):
        self.write_vibe()
        self.write_global()
        self.select("proj", "tester", selected=True)

        self.assertEqual(self.cli.run_agent_selection("proj", "tester"), "")

    def test_run_selection_returns_the_project_override(self):
        self.write_vibe()
        self.write_global()
        self.select(
            "proj", "tester", selected=True, model="opencode/projekt-speziell"
        )

        self.assertEqual(
            self.cli.run_agent_selection("proj", "tester"), "opencode/projekt-speziell"
        )
        with self.assertRaises(ValueError):
            self.cli.run_agent_selection("other", "tester")

    def test_cmd_run_aborts_before_tmux_for_a_deselected_agent(self):
        self.write_vibe()
        self.write_global()
        self.select("proj", "tester", selected=True)
        self.select("proj", "tester", selected=False)

        with mock.patch.object(self.cli, "tmux_has", return_value=False):
            with mock.patch.object(self.cli, "is_init", return_value=True):
                with mock.patch.object(
                    self.cli, "sandbox_status", return_value={"enabled": False}
                ):
                    with mock.patch.object(self.cli, "run") as runner:
                        with self.assertRaises(SystemExit) as caught:
                            self.cli.cmd_run("proj", "tester")

        message = str(caught.exception.code).lower()
        self.assertIn("tester", message)
        self.assertIn("nicht", message)
        runner.assert_not_called()

    def test_cmd_run_passes_the_project_model_override(self):
        self.write_vibe()
        self.write_global()
        self.select(
            "proj", "tester", selected=True, model="opencode/projekt-speziell"
        )
        calls = []
        registry = mock.MagicMock()

        with mock.patch.object(self.cli, "tmux_has", return_value=False):
            with mock.patch.object(self.cli, "is_init", return_value=True):
                with mock.patch.object(
                    self.cli, "sandbox_status", return_value={"enabled": False}
                ):
                    with mock.patch.object(
                        self.cli, "run_registry", return_value=registry
                    ):
                        with mock.patch.object(self.cli.vibe_runs, "rotate_log"):
                            with mock.patch.object(
                                self.cli,
                                "run",
                                side_effect=lambda argv, **kw: calls.append(argv)
                                or (0, ""),
                            ):
                                self.cli.cmd_run("proj", "tester")

        self.assertEqual(len(calls), 1)
        argv = calls[0]
        self.assertEqual(argv[-1], "opencode/projekt-speziell")
        self.assertEqual(argv[-2], "tester")

    def run_with_mocks(self):
        # AP03: Ohne anderen Agenten ist der Vibe-Agent der Standardagent.
        self.write_vibe()
        registry = mock.MagicMock()
        runner = mock.patch.object(self.cli, "run", return_value=(0, ""))
        with mock.patch.object(self.cli, "tmux_has", return_value=False):
            with mock.patch.object(self.cli, "is_init", return_value=True):
                with mock.patch.object(
                    self.cli, "sandbox_status", return_value={"enabled": False}
                ):
                    with mock.patch.object(
                        self.cli, "run_registry", return_value=registry
                    ):
                        with mock.patch.object(self.cli.vibe_runs, "rotate_log"):
                            with runner as fake_run:
                                self.cli.cmd_run("proj", "vibe-agent")
        return registry, fake_run

    def test_cmd_run_leaves_an_existing_legacy_rules_block_untouched(self):
        """GH-76: Der Laufstart aktualisiert keinen AGENTS.md-Block mehr."""
        self.write_global()
        agents = self.project / "AGENTS.md"
        original = (
            "# eigene Regel\n\n"
            + self.cli.GENERAL_RULES_MARK
            + "\n## Alt\n- veraltet\n<!-- /vibe:general-rules -->\n\n## Eigener Rest\n"
        )
        agents.write_text(original, encoding="utf-8")

        self.run_with_mocks()

        self.assertEqual(original, agents.read_text(encoding="utf-8"))

    def test_cmd_run_does_not_add_a_rules_block_to_a_project_without_one(self):
        """GH-76: Ohne vorhandenen Block wird keiner eingefügt."""
        self.write_global()
        agents = self.project / "AGENTS.md"
        agents.write_text("# eigene Regel\n", encoding="utf-8")

        self.run_with_mocks()

        text = agents.read_text(encoding="utf-8")
        self.assertEqual("# eigene Regel\n", text)
        self.assertNotIn(self.cli.GENERAL_RULES_MARK, text)

    def test_cmd_run_does_not_create_a_hardcoded_test_agent(self):
        """35233ff: Der Laufstart legt keinen Test-Agenten und kein TESTER an.

        Der frühere Fall ``test_cmd_run_ensures_the_independent_test_agent…``
        prüfte die mit 35233ff entfernte Mechanik (``ensure_test_agent``).
        Erhalten bleibt die aktuelle Aussage: ``cmd_run`` schreibt weder
        ``.opencode/agents/test-agent.md`` noch ``TESTER=`` in die
        Projektdatei. Die Meldung über tatsächlich kopierte Vorlagen prüft
        ``test_ap5_korbat_init_adopt`` am ``created``-Pfad.
        """
        self.write_global()

        self.run_with_mocks()

        agent = self.project / ".opencode" / "agents" / "test-agent.md"
        self.assertFalse(agent.exists())
        env = (self.project / ".vibe" / "project.env").read_text(encoding="utf-8")
        self.assertNotIn("TESTER=", env)


class RunnerModelTest(unittest.TestCase):
    """Der Läufer gibt eine Modellüberschreibung an ``opencode run`` weiter."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        self.verify = self.install / "verify"
        self.verify.mkdir()
        self.runtime = self.root / "_logs"
        self.project = self.root / "proj"
        self.calls = self.root / "opencode.calls"
        self.args = self.root / "_logs" / "opencode.args"
        self.fakebin = support.install_fake_tools(self.root)
        support.init_repo(self.project)
        (self.project / ".gitignore").write_text(".vibe/\n", encoding="utf-8")
        support.commit_all(self.project)
        (self.project / ".vibe").mkdir()
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n"
            "AGENT=tester\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL="true"\n'
            "MAX_RETRIES=0\n",
            encoding="utf-8",
        )
        # GH-48: Das Paket liegt im Ticketspeicher, nicht in FEEDBACK.md.
        support.write_ticket_store(self.project, [
            support.ticket_record("F1", "Testpaket", type="feedback",
                                  description="Test"),
        ])
        self.env = isolated_env(self.root, self.home)
        self.env.update(
            {
                "VIBE_INSTALL": str(self.install),
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_AGENTS_DIR": str(self.agents),
                "VIBE_MAX_PACKAGES": "1",
                "FAKE_ARGS_PATH": str(self.args),
                "FAKE_CALLS": str(self.calls),
                "FAKE_COUNTER": str(self.root / "counter"),
                "PATH": str(self.fakebin) + os.pathsep + os.environ.get("PATH", ""),
            }
        )

    def tearDown(self):
        self.tmp.cleanup()

    def run_runner(self, *arguments):
        return subprocess.run(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(self.project), *arguments],
            cwd=str(self.project),
            env=self.env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=90,
        )

    def opencode_arguments(self):
        self.assertTrue(self.args.exists(), "opencode wurde nicht aufgerufen")
        return [word for word in self.args.read_text(encoding="utf-8").split("\0") if word]

    def test_model_override_is_forwarded_to_opencode(self):
        result = self.run_runner("tester", "opencode/projekt-speziell")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        arguments = self.opencode_arguments()
        self.assertIn("run", arguments)
        self.assertIn("--model", arguments)
        self.assertEqual(
            arguments[arguments.index("--model") + 1], "opencode/projekt-speziell"
        )
        self.assertEqual(arguments[arguments.index("--agent") + 1], "tester")

    def test_without_override_no_model_flag_is_sent(self):
        result = self.run_runner("tester")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        arguments = self.opencode_arguments()
        self.assertNotIn("--model", arguments)

    def test_invalid_model_aborts_before_opencode(self):
        result = self.run_runner("tester", "kein modell;rm -rf /")

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Modellangabe ungültig", result.stdout + result.stderr)
        self.assertFalse(self.args.exists())


# ===========================================================================
# Ungültigen Startagenten aus der Projektauswahl beheben
# ===========================================================================

import builtins
import contextlib
import errno
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock


VIBE_AGENT_v025 = """---
description: Vibe-Standardagent für Nutzerunterstützung
mode: primary
model: opencode/vibe-modell
permission:
  read: allow
  edit: deny
---

Du unterstützt den Nutzer bei der Benutzung und Konfiguration von vibe.
"""

GLOBAL_AGENT_v025 = """---
description: Global vorhandener Agent
mode: subagent
model: opencode/global-modell
permission:
  read: allow
  edit: deny
---

Globaler Prompt.
"""

# Ausgangsdatei für AK1: AGENT zeigt auf einen nicht mehr vorhandenen Agenten.
MISSING_AGENT_ENV = (
    "TYPE=generic\n"
    "AGENT=alter-agent\n"
    "TESTER=test-agent\n"
    'VERIFY_QUICK="true"\n'
)

# Ausgangsdatei für AK2/AK3: AGENT zeigt auf einen global vorhandenen Agenten.
GLOBAL_AGENT_ENV = (
    "TYPE=generic\n"
    "AGENT=tester\n"
    "TESTER=test-agent\n"
    'VERIFY_QUICK="true"\n'
)

# Die Prüfumgebung erbt eine produktive vibe-Umgebung. Ohne diese Liste würde
# ein Test in den echten Agentenordner, den echten Zustandsordner oder die
# persönliche Konfiguration schreiben.
ISOLATED_ENV_v025 = (
    "VIBE",
    "VIBE_NO_CONTAINER",
    "HOME",
    "VIBE_STORAGE_LOCK_DIR",
    "VIBE_PROFILE",
    "VIBE_INSTALL",
    "VIBE_RUNTIME",
    "VIBE_STATE",
    "VIBE_AGENTS_DIR",
    "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR",
    "VIBE_UI_PORT",
    "VIBE_OPENCODE_PORT",
    "VIBE_UI_BIND",
    "VIBE_CONTAINER",
    "AGENT",
    "MAX_PACKAGES",
)


def isolated_env_v025(root, home):
    """Umgebung, die ausschließlich im temporären Prüfverzeichnis arbeitet."""
    env = os.environ.copy()
    for key in ISOLATED_ENV_v025:
        env.pop(key, None)
    env.update(
        {
            "VIBE": str(root),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(home),
            "VIBE_STATE": str(Path(root) / "_toolchain"),
            "VIBE_AGENTS_DIR": str(Path(home) / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(Path(home) / ".config" / "vibe" / "config.json"),
        }
    )
    return env


def load_cli_for_start_repair(vibe_root, home):
    """Lädt bin/vibe mit isoliertem VIBE/HOME, ohne main() auszuführen."""
    old = {key: os.environ.get(key) for key in ISOLATED_ENV_v025}
    for key in ISOLATED_ENV_v025:
        os.environ.pop(key, None)
    os.environ.update(isolated_env_v025(vibe_root, home))
    os.environ["VIBE_STORAGE_LOCK_DIR"] = str(Path(vibe_root) / "locks")
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_v025_under_test", str(CLI)
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


@contextlib.contextmanager
def failing_writes(path):
    """Simuliert ein Dateisystem, das Schreibzugriffe auf ``path`` verweigert.

    Der Test kennt die spätere Implementierung nicht und blockiert deshalb
    alle üblichen Schreibwege: direkte ``open``-Aufrufe (auch über ``io.open``
    und ``pathlib``), ``os.open`` mit Schreibflags sowie die atomare
    Ersetzung per ``os.replace``/``os.rename``. Lesen bleibt möglich.
    """
    target = os.path.realpath(os.fspath(path))
    real_builtin_open = builtins.open
    real_io_open = io.open
    real_replace = os.replace
    real_rename = os.rename
    real_os_open = os.open

    def is_target(candidate):
        try:
            return os.path.realpath(os.fspath(candidate)) == target
        except TypeError:
            return False

    def refuse(action):
        return OSError(
            errno.EACCES,
            f"{action} verweigert (Testfall V-025)",
            str(path),
        )

    def guarded_open(file, mode="r", *args, **kwargs):
        if is_target(file) and any(flag in mode for flag in "wax+"):
            raise refuse("Schreiben")
        return real_builtin_open(file, mode, *args, **kwargs)

    def guarded_io_open(file, mode="r", *args, **kwargs):
        if is_target(file) and any(flag in mode for flag in "wax+"):
            raise refuse("Schreiben")
        return real_io_open(file, mode, *args, **kwargs)

    def guarded_replace(src, dst, *args, **kwargs):
        if is_target(dst):
            raise refuse("Ersetzen")
        return real_replace(src, dst, *args, **kwargs)

    def guarded_rename(src, dst, *args, **kwargs):
        if is_target(dst):
            raise refuse("Umbenennen")
        return real_rename(src, dst, *args, **kwargs)

    def guarded_os_open(file, flags, *args, **kwargs):
        write_flags = (
            os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        )
        if is_target(file) and flags & write_flags:
            raise refuse("Schreiben")
        return real_os_open(file, flags, *args, **kwargs)

    with mock.patch("builtins.open", guarded_open):
        with mock.patch("io.open", guarded_io_open):
            with mock.patch("os.replace", guarded_replace):
                with mock.patch("os.rename", guarded_rename):
                    with mock.patch("os.open", guarded_os_open):
                        yield


class AgentStartRepairFixture(unittest.TestCase):
    """Temp-VIBE/HOME mit einem Projekt, Agentenordner und Rollen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        self.agents.mkdir(parents=True)
        self.project = self.make_project("proj")
        self.cli = load_cli_for_start_repair(self.root, self.home)
        self.cli._AGENT_VERSION = None
        models = mock.patch.object(self.cli, "models_list", return_value=[])
        models.start()
        self.addCleanup(models.stop)

    def tearDown(self):
        self.cli._AGENT_VERSION = None
        self.tmp.cleanup()

    def make_project(self, name):
        project = self.root / name
        (project / ".vibe").mkdir(parents=True)
        (project / ".vibe" / "project.env").write_text(
            MISSING_AGENT_ENV, encoding="utf-8"
        )
        return project

    # ---------- Aufbau ----------

    def write_global(self, name, text):
        path = self.agents / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def write_vibe(self):
        """Legt den globalen Vibe-Agenten samt Rolle ``vibe`` an."""
        path = self.write_global("vibe-agent", VIBE_AGENT_v025)
        data = self.cli.profiles_load()
        data["rollen"] = dict(data.get("rollen", {}))
        data["rollen"]["vibe-agent"] = "vibe"
        self.cli.profiles_save(data)
        return path

    def write_active_agents(self, names):
        """Schreibt die Projektauswahl (Version 2) mit genau diesen Agenten."""
        path = self.project / ".vibe" / "agents.json"
        path.write_text(
            json.dumps(
                {"version": 2, "aktiv": list(names), "modelle": {}},
                indent=1,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def set_project_env(self, text):
        (self.project / ".vibe" / "project.env").write_text(
            text, encoding="utf-8"
        )

    def set_project_env_bytes(self, data):
        (self.project / ".vibe" / "project.env").write_bytes(data)

    def project_env_text(self):
        return (self.project / ".vibe" / "project.env").read_text(
            encoding="utf-8"
        )

    def project_env_bytes(self):
        return (self.project / ".vibe" / "project.env").read_bytes()

    # ---------- Ausführung ----------

    def run_cmd(self, agent=None, write_error=None):
        """Ruft ``cmd_run`` mit allen externen Grenzen als Attrappen auf.

        Liefert die Aufrufe von ``run`` (tmux) und die gesammelte Ausgabe aus
        ``out`` und ``stderr``. ``write_error`` aktiviert die
        Schreibfehlersimulation für ``.vibe/project.env``.
        """
        calls = []
        out = io.StringIO()
        err = io.StringIO()
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(mock.patch.object(self.cli, "tmux_has", return_value=False))
        stack.enter_context(mock.patch.object(self.cli, "is_init", return_value=True))
        stack.enter_context(
            mock.patch.object(
                self.cli, "sandbox_status", return_value={"enabled": False}
            )
        )
        stack.enter_context(
            mock.patch.object(self.cli, "changed_file", return_value=False)
        )
        stack.enter_context(
            mock.patch.object(
                self.cli, "ensure_opencode_password", return_value=""
            )
        )
        stack.enter_context(
            mock.patch.object(self.cli, "run_registry", return_value=mock.MagicMock())
        )
        stack.enter_context(
            mock.patch.object(self.cli.vibe_runs, "rotate_log")
        )
        stack.enter_context(
            mock.patch.object(
                self.cli,
                "run",
                side_effect=lambda argv, **kwargs: calls.append(argv) or (0, ""),
            )
        )
        if write_error is not None:
            stack.enter_context(failing_writes(write_error))
        with contextlib.redirect_stderr(err):
            self.cli.cmd_run("proj", agent, out=out)
        return calls, out.getvalue() + err.getvalue()

    def assert_started_with(self, calls, agent):
        self.assertEqual(len(calls), 1, "cmd_run hat keinen Start ausgelöst")
        # Der Agent ist das vorletzte Argument; das letzte ist die (leere)
        # Modellüberschreibung des Projekts.
        self.assertEqual(calls[0][-2], agent)


class RepairTest(AgentStartRepairFixture):
    """AK1, AK2, AK6: veralteten Projektagenten erkennen und ersetzen."""

    def test_missing_agent_falls_back_to_vibe_and_repairs_project_env(self):
        """AK1: ``AGENT`` existiert global nicht; Start mit dem Vibe-Agenten."""
        self.write_vibe()

        calls, _output = self.run_cmd()

        self.assert_started_with(calls, "vibe-agent")
        self.assertEqual(
            self.project_env_text(),
            "TYPE=generic\n"
            "AGENT=vibe-agent\n"
            "TESTER=test-agent\n"
            'VERIFY_QUICK="true"\n',
        )

    def test_global_but_inactive_agent_is_repaired(self):
        """AK2: ``AGENT`` existiert global, ist aber im Projekt nicht aktiv."""
        self.write_vibe()
        self.write_global("tester", GLOBAL_AGENT_v025)
        self.write_active_agents(["vibe-agent"])
        self.set_project_env(GLOBAL_AGENT_ENV)

        calls, _output = self.run_cmd()

        self.assert_started_with(calls, "vibe-agent")
        self.assertEqual(
            self.project_env_text(),
            "TYPE=generic\n"
            "AGENT=vibe-agent\n"
            "TESTER=test-agent\n"
            'VERIFY_QUICK="true"\n',
        )

    def test_repair_message_names_old_and_new_agent(self):
        """AK6: Die Ausgabe macht den veralteten und den neuen Agenten sichtbar."""
        self.write_vibe()

        _calls, output = self.run_cmd()

        self.assertIn("alter-agent", output)
        self.assertIn("vibe-agent", output)

    def test_repair_preserves_other_lines_verbatim(self):
        """AK1: Nur die ``AGENT``-Zeile ändert sich, alles andere bleibt."""
        self.write_vibe()
        original = (
            "# Kopfkommentar\n"
            "TYPE=generic\n"
            "AGENT=alter-agent\n"
            "MODEL_OVERRIDE=opencode/bleibt\n"
            "TESTER=test-agent\n"
            'VERIFY_QUICK="true"\n'
        )
        self.set_project_env(original)

        _calls, _output = self.run_cmd()

        self.assertEqual(
            self.project_env_text(),
            original.replace("AGENT=alter-agent", "AGENT=vibe-agent"),
        )


class StableSelectionTest(AgentStartRepairFixture):
    """AK3: gültiger, aktiver Agent bleibt unangetastet."""

    def test_active_agent_is_used_and_env_stays_unchanged(self):
        self.write_vibe()
        self.write_global("tester", GLOBAL_AGENT_v025)
        self.write_active_agents(["vibe-agent", "tester"])
        self.set_project_env(GLOBAL_AGENT_ENV)
        before = self.project_env_text()

        calls, _output = self.run_cmd()

        self.assert_started_with(calls, "tester")
        self.assertEqual(self.project_env_text(), before)


class ExplicitAgentTest(AgentStartRepairFixture):
    """AK4: ein ausdrücklich übergebener Agent wird nicht still ersetzt."""

    def test_explicit_inactive_agent_is_rejected_without_writing(self):
        self.write_vibe()
        self.write_global("tester", GLOBAL_AGENT_v025)
        self.write_active_agents(["vibe-agent"])
        self.set_project_env(GLOBAL_AGENT_ENV)
        before = self.project_env_text()

        with self.assertRaises(SystemExit) as caught:
            self.run_cmd(agent="tester")

        message = str(caught.exception.code).lower()
        self.assertIn("tester", message)
        self.assertIn("nicht", message)
        # Die Projektdatei darf durch die Ablehnung nicht verändert werden.
        self.assertEqual(self.project_env_text(), before)


class WriteErrorTest(AgentStartRepairFixture):
    """AK5: ein Schreibfehler bei der Korrektur bricht den Start nicht ab."""

    def test_write_error_still_starts_with_vibe_and_reports_error(self):
        self.write_vibe()
        before = self.project_env_text()

        calls, output = self.run_cmd(
            write_error=self.project / ".vibe" / "project.env"
        )

        self.assert_started_with(calls, "vibe-agent")
        # Der fehlgeschlagene Schreibvorgang hinterlässt die alte Zeile.
        self.assertEqual(self.project_env_text(), before)
        self.assertTrue(output.strip(), "Der Schreibfehler wurde nicht gemeldet")
        lowered = output.lower()
        self.assertTrue(
            any(hint in lowered for hint in ("konnte", "nicht", "fehl", "schreib")),
            "Die Ausgabe enthält keinen Hinweis auf den Schreibfehler: "
            + output,
        )


class RepairFormatTest(AgentStartRepairFixture):
    """Formaterhalt: Zeilenenden und gequotete Werte bei der Korrektur."""

    def test_repair_preserves_crlf_line_endings(self):
        """Eine CRLF-Projektdatei behält CRLF; nur die AGENT-Zeile ändert sich."""
        self.write_vibe()
        self.set_project_env_bytes(
            b"TYPE=generic\r\n"
            b"AGENT=alter-agent\r\n"
            b"TESTER=test-agent\r\n"
            b'VERIFY_QUICK="true"\r\n'
        )

        calls, _output = self.run_cmd()

        self.assert_started_with(calls, "vibe-agent")
        self.assertEqual(
            self.project_env_bytes(),
            b"TYPE=generic\r\n"
            b"AGENT=vibe-agent\r\n"
            b"TESTER=test-agent\r\n"
            b'VERIFY_QUICK="true"\r\n',
        )

    def test_quoted_agent_value_is_replaced(self):
        """Ein gequoteter AGENT-Wert wird vollständig durch den Vibe-Agenten ersetzt."""
        self.write_vibe()
        self.set_project_env(
            "TYPE=generic\n"
            'AGENT="alter-agent"\n'
            "TESTER=test-agent\n"
        )

        calls, _output = self.run_cmd()

        self.assert_started_with(calls, "vibe-agent")
        self.assertEqual(
            self.project_env_text(),
            "TYPE=generic\n"
            "AGENT=vibe-agent\n"
            "TESTER=test-agent\n",
        )


class RepairHelperGuardTest(AgentStartRepairFixture):
    """Sicherheitsgrenze: die Reparatur schreibt keinen ungültigen Agentennamen."""

    def test_repair_rejects_invalid_agent_names(self):
        """Namen außerhalb von ``NAME_RE`` lösen einen Fehler aus, ohne zu schreiben.

        ``NAME_RE`` erlaubt nur ``^[a-z0-9][a-z0-9_-]*$``; Leerzeichen und
        Shellzeichen dürfen nie in die Projektdatei gelangen.
        """
        self.write_vibe()
        before = self.project_env_bytes()

        for invalid in ("mit leerzeichen", "boese;rm -rf /"):
            with self.subTest(agent=invalid):
                with self.assertRaises((ValueError, SystemExit)) as caught:
                    self.cli.repair_project_agent("proj", invalid)

                message = str(caught.exception).strip()
                self.assertTrue(
                    message, "Der ungültige Agentenname wurde nicht gemeldet"
                )
                self.assertTrue(
                    any(
                        hint in message.lower()
                        for hint in ("agent", "name", "ungültig")
                    ),
                    "Die Meldung benennt den Agentennamen nicht: " + message,
                )
                self.assertEqual(
                    self.project_env_bytes(),
                    before,
                    "Die Projektdatei wurde trotz ungültigem Agentennamen geschrieben",
                )


class TemplateDefaultsTest(unittest.TestCase):
    """Vorlagen-AK: kein fest eingebauter ``AGENT`` in mitgelieferten Projekten."""

    def test_shipped_project_templates_contain_no_agent_entry(self):
        """Jede ``templates/*/.vibe/project.env`` ist frei von ``AGENT=``.

        Geprüft wird die wirksame Zuweisung: Kommentarzeilen zählen nicht,
        weil sie beim Anlegen eines Projekts keine Wirkung entfalten. Fehlt
        jede Vorlage, ist der Test nicht erfüllt, statt leer zu bestehen.
        """
        paths = sorted((REPO / "templates").glob("*/.vibe/project.env"))
        self.assertTrue(
            paths,
            "Keine Projektvorlagen unter templates/*/.vibe/project.env gefunden",
        )
        findings = []
        for path in paths:
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if re.match(r"^AGENT\s*=", stripped):
                    findings.append(
                        f"{path.relative_to(REPO)}:{number}: {line}"
                    )
        self.assertEqual(
            findings,
            [],
            "Mitgelieferte Vorlagen mit fest eingebautem AGENT:\n"
            + "\n".join(findings),
        )


# ===========================================================================
# Abnahme: Projektmodelle aus ``.vibe/agents.json`` erreichen opencode
# ===========================================================================

import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support  # noqa: E402

PASSWORD = "b1-privat-9031"

# Die Attrappe schreibt zuerst die beobachtete Umgebung und führt danach die
# gemeinsame opencode-Attrappe aus ``runner_support`` aus. Sie ersetzt damit
# weder das Verhalten des Agenten noch das des privaten Servers.
ENV_RECORDING_OPENCODE = r'''#!/usr/bin/env python3
import json
import os
import sys

record = os.environ.get("FAKE_ENV_RECORD")
if record:
    entry = {
        "argv": sys.argv[1:],
        "config": os.environ.get("OPENCODE_CONFIG_CONTENT"),
    }
    with open(record, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

impl = os.environ.get("FAKE_OPENCODE_IMPL")
if not impl:
    raise SystemExit("FAKE_OPENCODE_IMPL fehlt")
os.execv(sys.executable, [sys.executable, impl] + sys.argv[1:])
'''


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def effective_model(config, agent):
    """Löst das wirksame Modell wie opencode auf: ``agents`` vor ``agent``."""
    if not isinstance(config, dict):
        return None
    for key in ("agents", "agent"):
        agents = config.get(key)
        if isinstance(agents, dict):
            entry = agents.get(agent)
            if isinstance(entry, dict) and isinstance(entry.get("model"), str):
                return entry["model"]
    return None


def resolved_agent_fields(config, agent):
    """Sammelt die Felder eines Agenten über beide akzeptierten Schemata."""
    fields = {}
    if not isinstance(config, dict):
        return fields
    for key in ("agent", "agents"):
        agents = config.get(key)
        if isinstance(agents, dict):
            entry = agents.get(agent)
            if isinstance(entry, dict):
                fields.update(entry)
    return fields


class SharedOpenCode:
    """Erreichbarer gemeinsamer opencode-Server für die Wiederverwendungsfälle.

    ``GET /api/info`` antwortet immer mit 200; die Anmeldung wird nicht
    bewertet, weil hier nur die Zielwahl des Läufers geprüft wird.
    """

    def __init__(self, port):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def do_GET(self):
                body = json.dumps({"ok": True}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever)
        self.thread.daemon = True
        outer.requests = []

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


class B1RunnerFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer", "vibe-agent")
        self.runtime = self.root / "_logs"
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        self.fakebin = support.install_fake_tools(self.root)
        support.install_real_curl(self.fakebin)
        # Die eigentliche Attrappe liegt daneben; der Name ``opencode`` im
        # PATH gehört der protokollierenden Hülle.
        self.impl = self.fakebin / "opencode_impl"
        self.impl.write_text(support.FAKE_OPENCODE, encoding="utf-8")
        self.impl.chmod(0o755)
        opencode = self.fakebin / "opencode"
        opencode.write_text(ENV_RECORDING_OPENCODE, encoding="utf-8")
        opencode.chmod(0o755)

        self.project = self.root / "proj"
        support.write_project(
            self.project,
            "TYPE=generic\n"
            "AGENT=tester\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL="true"\n'
            "MAX_RETRIES=0\n",
            feedback=[support.ticket_record(
                "B1", "Testpaket",
                description="Projektmodelle weitergeben")],
        )
        # ``.vibe`` gehört nur zum Integrationsprojekt und ist nicht Teil des
        # Paketbranchs. Die Arbeitskopie enthält deshalb keine agents.json.
        (self.project / ".gitignore").write_text("/.vibe/\n", encoding="utf-8")
        support.init_repo(self.project)
        support.commit_all(self.project)

        self.env_record = self.root / "opencode.env.jsonl"
        self.args_file = self.runtime / "opencode.args"
        self.serve_record = self.root / "serve.record.jsonl"
        self.dead_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.dead_socket.bind(("127.0.0.1", 0))
        self.dead_port = self.dead_socket.getsockname()[1]
        self.addCleanup(self.dead_socket.close)
        self.shared = None
        self.addCleanup(self.stop_shared)
        self.addCleanup(self.kill_leftover_serve)

    # ---------- Dateien und Umgebung ----------

    def config_path(self):
        return self.project / ".vibe" / "agents.json"

    def write_project_models(self, models, aktiv=None):
        """Schreibt die Projektkonfiguration als nicht versionierte Projektdatei."""
        path = self.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 2,
            "aktiv": sorted(aktiv if aktiv is not None else models),
            "modelle": models,
        }
        path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def write_password(self, value=PASSWORD):
        self.runtime.mkdir(parents=True, exist_ok=True)
        path = self.runtime / "opencode.password"
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
        return path

    def env(self, extra=None):
        env = os.environ.copy()
        for key in list(env):
            if (
                key.startswith("VIBE")
                or key.startswith("SANDBOX")
                or key.startswith("FAKE_")
                or key.startswith("OPENCODE_")
            ):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(self.root),
                "VIBE_INSTALL": str(self.install),
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_AGENTS_DIR": str(self.agents),
                "VIBE_OPENCODE_PORT": str(self.dead_port),
                "VIBE_MAX_PACKAGES": "1",
                "HOME": str(self.home),
                "VIBE_NO_CONTAINER": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
                "FAKE_ARGS_PATH": str(self.args_file),
                "FAKE_ENV_RECORD": str(self.env_record),
                "FAKE_OPENCODE_IMPL": str(self.impl),
                "FAKE_SERVE_RECORD": str(self.serve_record),
                "FAKE_CALLS": str(self.root / "opencode.calls"),
                "FAKE_COUNTER": str(self.root / "counter"),
            }
        )
        if extra:
            env.update(extra)
        return env

    def run_runner(self, *arguments, extra_env=None, timeout=180):
        return subprocess.run(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(self.project), *arguments],
            cwd=str(self.project),
            env=self.env(extra_env),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def log_text(self):
        path = self.runtime / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    # ---------- Beobachtung ----------

    def records(self):
        try:
            raw = self.env_record.read_text(encoding="utf-8")
        except OSError:
            return []
        entries = []
        for line in raw.splitlines():
            if line.strip():
                entries.append(json.loads(line))
        return entries

    def run_calls(self):
        return [entry for entry in self.records()
                if entry.get("argv") and entry["argv"][0] == "run"]

    def serve_calls(self):
        return [entry for entry in self.records()
                if entry.get("argv") and entry["argv"][0] == "serve"]

    def config_of(self, entry):
        raw = entry.get("config")
        self.assertIsInstance(
            raw, str,
            "opencode erhielt keine OPENCODE_CONFIG_CONTENT: " + repr(entry))
        return json.loads(raw)

    def platform_instructions_path(self, config):
        """GH-76: Die Inline-Konfiguration nennt genau den Plattformtext."""
        instructions = config.get("instructions")
        self.assertIsInstance(
            instructions, list,
            "OPENCODE_CONFIG_CONTENT enthält keine instructions-Liste: "
            + json.dumps(config, ensure_ascii=False))
        self.assertEqual(1, len(instructions), instructions)
        path = Path(instructions[0])
        self.assertTrue(path.is_absolute(), instructions)
        self.assertEqual("platform_instructions.md", path.name)
        self.assertTrue(path.is_file(), "Plattformtext fehlt: " + str(path))
        self.assertIn(
            path.parent.resolve(),
            {self.runtime.resolve(), self.install.resolve()},
            "Plattformtext liegt nicht im Laufzeit-/Zustandsordner: " + str(path))
        text = path.read_text(encoding="utf-8")
        self.assertIn("## Vibe platform instructions", text)
        return path

    def assert_models(self, config, expected):
        for agent, model in expected.items():
            self.assertEqual(
                effective_model(config, agent), model,
                f"Agent {agent!r} hat nicht das Projektmodell; Konfiguration: "
                + json.dumps(config, ensure_ascii=False))

    # ---------- Gemeinsamer Server ----------

    def start_shared_server(self):
        port = free_port()
        self.shared = SharedOpenCode(port).start()
        self.addCleanup(self.shared.stop)
        return port

    def stop_shared(self):
        if self.shared is not None:
            self.shared.stop()
            self.shared = None

    def kill_leftover_serve(self):
        """Beendet nur die von diesem Test gestarteten Serverprozesse."""
        pids = set()
        try:
            raw = self.serve_record.read_text(encoding="utf-8")
        except OSError:
            raw = ""
        for line in raw.splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("event") == "listening" and isinstance(entry.get("pid"), int):
                pids.add(entry["pid"])
        try:
            pid_files = list(self.runtime.glob("*.server.pid"))
        except OSError:
            pid_files = []
        for path in pid_files:
            try:
                value = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if value.isdigit():
                pids.add(int(value))
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                continue
        if pids:
            time.sleep(0.5)
            for pid in pids:
                try:
                    os.kill(pid, 0)
                except OSError:
                    continue
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass


MODELS = {
    "tester": "projekt/tester-modell",
    "reviewer": "projekt/reviewer-modell",
    "vibe-agent": "projekt/vibe-modell",
}

EXISTING_CONFIG = {
    "theme": "dark",
    "model": "global/standard",
    "provider": {"firma": {"options": {"timeout": 30}}},
    "agent": {
        "reviewer": {
            "model": "global/reviewer-legacy",
            "description": "Bestehender Reviewer",
            "temperature": 0.2,
        },
        "archivar": {
            "model": "global/archivar",
            "description": "Nicht überschriebener Agent",
        },
    },
    "agents": {
        "reviewer": {
            "model": "global/reviewer-alias",
            "tools": {"bash": False},
        },
    },
}


class RunnerProjectModelsTest(B1RunnerFixture):
    """Projektmodelle erreichen den opencode-Lauf und den privaten Server."""

    def test_all_project_models_are_effective_for_the_opencode_run(self):
        """AK1/AK4: mehrere Modelle wirksam, ``--model`` bleibt, Dateien unverändert."""
        path = self.write_project_models(MODELS)
        agents_before = {
            item.name: item.read_bytes() for item in self.agents.iterdir()
        }
        project_config_before = path.read_bytes()

        result = self.run_runner("tester", "auftrag/start-modell")

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), "Genau ein Agentenaufruf erwartet: "
                         + repr(self.records()))
        config = self.config_of(runs[0])
        self.assert_models(config, MODELS)
        self.platform_instructions_path(config)

        argv = runs[0]["argv"]
        self.assertIn("--model", argv, repr(argv))
        self.assertEqual(
            argv[argv.index("--model") + 1], "auftrag/start-modell",
            "Der bisherige Modellparameter des Hauptagenten ging verloren")
        self.assertEqual(argv[argv.index("--agent") + 1], "tester")

        agents_after = {
            item.name: item.read_bytes() for item in self.agents.iterdir()
        }
        self.assertEqual(
            agents_before, agents_after,
            "Globale Agentendateien wurden verändert")
        self.assertEqual(
            project_config_before, path.read_bytes(),
            ".vibe/agents.json wurde verändert")

    def test_project_models_reach_the_private_server_process(self):
        """AK2: Der private ``opencode serve`` erhält dieselbe wirksame Konfiguration."""
        self.write_project_models(MODELS)
        self.write_password()

        result = self.run_runner("tester", "projekt/tester-modell")

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        serves = self.serve_calls()
        runs = self.run_calls()
        self.assertEqual(1, len(serves), "Genau ein privater Server erwartet: "
                         + repr(self.records()))
        self.assertEqual(1, len(runs), "Genau ein Agentenaufruf erwartet: "
                         + repr(self.records()))

        serve_config = self.config_of(serves[0])
        run_config = self.config_of(runs[0])
        self.assert_models(serve_config, MODELS)
        self.assert_models(run_config, MODELS)
        self.platform_instructions_path(serve_config)
        self.platform_instructions_path(run_config)
        self.assertEqual(
            serve_config, run_config,
            "Server und Lauf sehen nicht dieselbe wirksame Konfiguration")

        argv = runs[0]["argv"]
        self.assertIn("--server", argv, repr(argv))
        self.assertNotIn("--standalone", argv, repr(argv))
        url = argv[argv.index("--server") + 1]
        self.assertTrue(url.startswith("http://127.0.0.1:"), url)
        self.assertNotIn(str(self.dead_port), url)


class SharedServerTest(B1RunnerFixture):
    """AK: Ein erreichbarer gemeinsamer Server löst keine falsche Modellwahl aus."""

    def shared_url(self, port):
        return "http://127.0.0.1:" + str(port)

    def test_shared_server_without_platform_instructions_is_not_reused(self):
        """GH-76: Ein vorbestehender Server ohne den Plattformtext wird ersetzt.

        Aktion: gemeinsamer Server läuft, keine Projektmodelle, keine
        Kennwortdatei. Erwartung: ``opencode run --standalone`` (der Lauf
        startet seinen eigenen Server mit der Inline-Konfiguration); der
        gemeinsame Server wird nicht kontaktiert und kein privater
        ``serve``-Prozess gestartet. Fehlerfall: Wiederverwendung eines
        Servers, der die Plattformanweisungen nicht kennt.
        """
        shared_port = self.start_shared_server()

        result = self.run_runner(
            "tester", extra_env={"VIBE_OPENCODE_PORT": str(shared_port)})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), repr(self.records()))
        self.assertEqual([], self.serve_calls(),
                         "Ohne Kennwortdatei startet kein privater Server")
        argv = runs[0]["argv"]
        self.assertIn("--standalone", argv, repr(argv))
        self.assertNotIn("--server", argv, repr(argv))
        self.platform_instructions_path(self.config_of(runs[0]))

    def test_shared_server_is_not_reused_when_project_models_exist(self):
        """AK: Mit Projektmodellen ohne Kennwortdatei gilt ``--standalone``."""
        self.write_project_models(MODELS)
        shared_port = self.start_shared_server()

        result = self.run_runner(
            "tester", "projekt/tester-modell",
            extra_env={"VIBE_OPENCODE_PORT": str(shared_port)})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), repr(self.records()))
        self.assertEqual(
            [], self.serve_calls(),
            "Ohne Kennwortdatei startet kein privater Server")
        argv = runs[0]["argv"]
        self.assertIn("--standalone", argv, repr(argv))
        self.assertNotIn("--server", argv, repr(argv))
        self.assertNotIn(self.shared_url(shared_port), argv, repr(argv))
        self.assert_models(self.config_of(runs[0]), MODELS)

    def test_shared_server_is_replaced_by_a_private_server_with_project_models(self):
        """AK: Mit Kennwortdatei ersetzt der private Server den gemeinsamen."""
        self.write_project_models(MODELS)
        self.write_password()
        shared_port = self.start_shared_server()

        result = self.run_runner(
            "tester", "projekt/tester-modell",
            extra_env={"VIBE_OPENCODE_PORT": str(shared_port)})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        serves = self.serve_calls()
        runs = self.run_calls()
        self.assertEqual(1, len(serves), "Genau ein privater Server erwartet: "
                         + repr(self.records()))
        self.assertEqual(1, len(runs), repr(self.records()))

        argv = runs[0]["argv"]
        self.assertIn("--server", argv, repr(argv))
        self.assertNotIn("--standalone", argv, repr(argv))
        private_url = argv[argv.index("--server") + 1]
        self.assertTrue(private_url.startswith("http://127.0.0.1:"), private_url)
        self.assertNotEqual(private_url, self.shared_url(shared_port),
                            "Der gemeinsame Server wurde trotz Projektmodellen "
                            "ohne Laufkonfiguration weiterverwendet")

        serve_config = self.config_of(serves[0])
        run_config = self.config_of(runs[0])
        self.assert_models(serve_config, MODELS)
        self.assert_models(run_config, MODELS)
        self.assertEqual(serve_config, run_config)


class ExistingConfigTest(B1RunnerFixture):
    """AK3: Vorhandene Inline-Konfiguration bleibt erhalten."""

    def test_existing_config_is_preserved_and_project_models_win(self):
        """Auch bei vorhandener ``agents``-Map gewinnt das Projektmodell."""
        self.write_project_models({"reviewer": "projekt/reviewer-modell"})

        result = self.run_runner(
            "tester",
            extra_env={"OPENCODE_CONFIG_CONTENT": json.dumps(EXISTING_CONFIG)})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), repr(self.records()))
        config = self.config_of(runs[0])

        for key in ("theme", "model", "provider"):
            self.assertEqual(
                config.get(key), EXISTING_CONFIG[key],
                f"Unbeteiligte Einstellung {key!r} ging verloren")

        self.platform_instructions_path(config)
        fields = resolved_agent_fields(config, "reviewer")
        self.assertEqual(fields.get("description"), "Bestehender Reviewer")
        self.assertEqual(fields.get("temperature"), 0.2)
        self.assertEqual(fields.get("tools"), {"bash": False})
        self.assertEqual(
            effective_model(config, "reviewer"), "projekt/reviewer-modell",
            "Eine vorhandene agents-Map setzt die Projektüberschreibung "
            "wieder außer Kraft")

        # Nicht überschriebene Agenten bleiben unverändert.
        self.assertEqual(effective_model(config, "archivar"),
                         "global/archivar")
        self.assertEqual(
            resolved_agent_fields(config, "archivar").get("description"),
            "Nicht überschriebener Agent")

    def test_legacy_agent_schema_stays_compatible(self):
        """Das alte ``agent``-Schema wird weiterhin gemischt und bleibt erhalten."""
        existing = {
            "theme": "light",
            "agent": {
                "reviewer": {
                    "model": "global/reviewer",
                    "description": "Legacy-Reviewer",
                    "temperature": 0.1,
                },
            },
        }
        self.write_project_models({"reviewer": "projekt/reviewer-modell"})

        result = self.run_runner(
            "tester",
            extra_env={"OPENCODE_CONFIG_CONTENT": json.dumps(existing)})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        config = self.config_of(self.run_calls()[0])
        self.assertEqual(config.get("theme"), "light")
        self.assertEqual(effective_model(config, "reviewer"),
                         "projekt/reviewer-modell")
        fields = resolved_agent_fields(config, "reviewer")
        self.assertEqual(fields.get("description"), "Legacy-Reviewer")
        self.assertEqual(fields.get("temperature"), 0.1)

    def test_jsonc_existing_config_is_accepted_and_merged(self):
        """JSONC (Kommentare, Trailing Commas) wird wie von opencode akzeptiert.

        opencode v2.3.0 akzeptiert in ``OPENCODE_CONFIG_CONTENT`` JSONC. Eine
        Bestandskonfiguration darf deshalb nicht allein wegen eines Kommentars
        oder eines abschließenden Kommas abgelehnt werden. Nach dem
        Zusammenführen ist eine reine JSON-Serialisierung zulässig; Kommentare
        und Formatierung müssen nicht erhalten bleiben.
        """
        jsonc = """{
  // Bestehende Anmerkung des Nutzers
  "theme": "dark",
  "model": "global/standard",
  "agent": {
    "reviewer": {
      "model": "global/reviewer", // wird vom Projekt überschrieben
      "temperature": 0.2,
    },
  },
}
"""
        self.write_project_models({"reviewer": "projekt/reviewer-modell"})

        result = self.run_runner(
            "tester", extra_env={"OPENCODE_CONFIG_CONTENT": jsonc})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), repr(self.records()))
        config = self.config_of(runs[0])
        self.assertEqual(config.get("theme"), "dark")
        self.assertEqual(config.get("model"), "global/standard")
        self.assertEqual(effective_model(config, "reviewer"),
                         "projekt/reviewer-modell")
        self.assertEqual(
            resolved_agent_fields(config, "reviewer").get("temperature"), 0.2)

    def test_jsonc_comment_between_trailing_comma_and_closing_brace(self):
        """Trailing Comma mit Kommentar davor bleibt gültiges JSONC.

        opencode akzeptiert ``{"a": 1, // Kommentar\n}``. Der Scanner darf den
        Trailing Comma deshalb nicht nur dann entfernen, wenn direkt nach dem
        Whitespace die schließende Klammer folgt. Zugleich muss ``//`` in einer
        Zeichenkette (URL) unangetastet bleiben.
        """
        jsonc = """{
  // Bestehende Anmerkung des Nutzers
  "theme": "dark",
  "hinweis": "https://example.invalid/path",
  "agent": {
    "reviewer": {
      "model": "global/reviewer",
      "temperature": 0.2, // Kommentar zwischen Komma und schließender Klammer
    },
  },
}
"""
        self.write_project_models({"reviewer": "projekt/reviewer-modell"})

        result = self.run_runner(
            "tester", extra_env={"OPENCODE_CONFIG_CONTENT": jsonc})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), repr(self.records()))
        config = self.config_of(runs[0])
        self.assertEqual(config.get("theme"), "dark")
        self.assertEqual(config.get("hinweis"), "https://example.invalid/path",
                         "Die URL mit '//' wurde als Kommentar behandelt")
        self.assertEqual(effective_model(config, "reviewer"),
                         "projekt/reviewer-modell")
        self.assertEqual(
            resolved_agent_fields(config, "reviewer").get("temperature"), 0.2)

    def test_existing_config_keys_survive_and_instructions_are_added(self):
        """GH-76: Ohne Projektmodelle bleiben fremde Schlüssel erhalten; nur
        die ``instructions``-Liste kommt hinzu, keine Agenten-Map."""
        self.write_project_models({}, aktiv=[])
        existing = {
            "theme": "dark",
            "agent": {"reviewer": {"model": "global/reviewer"}},
            "agents": {"reviewer": {"tools": {"bash": False}}},
        }

        result = self.run_runner(
            "tester",
            extra_env={"OPENCODE_CONFIG_CONTENT": json.dumps(existing)})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), repr(self.records()))
        config = self.config_of(runs[0])
        for key in ("theme", "agent", "agents"):
            self.assertEqual(existing[key], config.get(key),
                             "Bestehender Schlüssel ging verloren: " + key)
        self.platform_instructions_path(config)
        self.assertIsNone(effective_model(config, "tester"))

class InvalidConfigurationTest(B1RunnerFixture):
    """AK: Fehlerhafte Konfiguration scheitert vor dem Agentenstart."""

    def assert_no_agent_started(self):
        self.assertEqual([], self.run_calls(),
                         "Agent wurde trotz fehlerhafter Konfiguration gestartet")
        self.assertEqual([], self.serve_calls(),
                         "Privater Server wurde trotz fehlerhafter Konfiguration gestartet")

    def test_unreadable_project_agents_file_aborts_before_agent_start(self):
        path = self.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{kaputt", encoding="utf-8")

        result = self.run_runner("tester")

        detail = result.stdout + result.stderr + self.log_text()
        self.assertNotEqual(
            result.returncode, 0,
            "Unlesbare agents.json fiel still auf globale Modelle zurück:\n"
            + detail)
        self.assert_no_agent_started()
        self.assertTrue(
            re.search(r"agents\.json|Agentenauswahl|Projektkonfiguration|Projektdatei",
                      detail, re.IGNORECASE),
            "Keine verständliche Meldung zur fehlerhaften Projektdatei:\n"
            + detail)

    def test_unmergeable_existing_config_aborts_before_agent_start(self):
        self.write_project_models(MODELS)

        result = self.run_runner(
            "tester",
            extra_env={"OPENCODE_CONFIG_CONTENT": "{kaputt"})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertNotEqual(
            result.returncode, 0,
            "Nicht mergefähige Inline-Konfiguration fiel still auf globale "
            "Modelle zurück:\n" + detail)
        self.assert_no_agent_started()
        self.assertTrue(
            re.search(r"OPENCODE_CONFIG_CONTENT|Konfiguration|Inline",
                      detail, re.IGNORECASE),
            "Keine verständliche Meldung zur Inline-Konfiguration:\n" + detail)

    def test_unterminated_block_comment_is_not_silently_removed(self):
        """Ein offener Blockkommentar darf nicht bis zum Dateiende verschwinden.

        Steht nach einem ansonsten vollständigen Objekt ein nicht
        abgeschlossener ``/*``-Kommentar, wäre die Konfiguration nach dem
        Entfernen scheinbar gültig. Das ist kein gültiges JSONC und muss
        fail-closed vor dem Agentenstart abbrechen.
        """
        existing = """{
  "theme": "dark",
  "agent": {"reviewer": {"model": "global/reviewer"}}
}
/* nicht abgeschlossener Kommentar
"""
        self.write_project_models({"reviewer": "projekt/reviewer-modell"})

        result = self.run_runner(
            "tester",
            extra_env={"OPENCODE_CONFIG_CONTENT": existing})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertNotEqual(
            result.returncode, 0,
            "Ein offener Blockkommentar wurde still entfernt und die "
            "Konfiguration akzeptiert:\n" + detail)
        self.assert_no_agent_started()
        self.assertTrue(
            re.search(r"OPENCODE_CONFIG_CONTENT|Kommentar|Konfiguration|Inline",
                      detail, re.IGNORECASE),
            "Keine verständliche Meldung zum offenen Blockkommentar:\n"
            + detail)

    def test_path_that_is_not_a_regular_file_aborts_before_agent_start(self):
        """Nur FileNotFoundError bedeutet 'keine Projektmodelle'.

        Ein vorhandener, aber nicht als Datei lesbarer Pfad (hier ein
        Verzeichnis an der Stelle von ``agents.json``) ist ein anderer
        ``OSError`` und darf nicht still wie eine fehlende Datei zu globalen
        Modellen führen.
        """
        path = self.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.mkdir()

        result = self.run_runner("tester")

        detail = result.stdout + result.stderr + self.log_text()
        self.assertNotEqual(
            result.returncode, 0,
            "Ein nicht lesbarer Projektpfad wurde wie eine fehlende Datei "
            "behandelt:\n" + detail)
        self.assert_no_agent_started()
        self.assertTrue(
            re.search(r"agents\.json|Agentenauswahl|Projektkonfiguration|Projektdatei|nicht lesbar",
                      detail, re.IGNORECASE),
            "Keine verständliche Meldung zum nicht lesbaren Projektpfad:\n"
            + detail)

    def test_non_object_existing_config_aborts_before_agent_start(self):
        self.write_project_models(MODELS)

        result = self.run_runner(
            "tester",
            extra_env={"OPENCODE_CONFIG_CONTENT": "[]"})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertNotEqual(
            result.returncode, 0,
            "Eine nicht objektförmige Inline-Konfiguration wurde still "
            "überschrieben:\n" + detail)
        self.assert_no_agent_started()
        self.assertTrue(
            re.search(r"OPENCODE_CONFIG_CONTENT|Konfiguration|Inline",
                      detail, re.IGNORECASE),
            "Keine verständliche Meldung zur Inline-Konfiguration:\n" + detail)


if __name__ == "__main__":
    unittest.main()
