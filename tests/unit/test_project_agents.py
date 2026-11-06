"""Abnahme F17: Agentenverwaltung je Projekt.

Geprüft werden die fachlichen Regeln hinter Dashboard und CLI:

* ohne eigene Projektdatei sind alle verfügbaren Agenten ausgewählt und die
  Modelle kommen aus den Agentendateien,
* Auswahl und Modellüberschreibung gelten nur für das jeweilige Projekt,
* ein abgewählter Agent wird für den Agentenlauf abgelehnt,
* die Modellüberschreibung wird an ``opencode run`` weitergegeben,
* ungültige Eingaben verändern keine Datei,
* eine unlesbare Projektdatei wird gemeldet und nicht stillschweigend
  überschrieben.

Die Tests arbeiten auf echten Dateien in einem temporären Arbeitsbereich.
opencode ist im Läufertest eine Attrappe; es findet kein Modellaufruf statt.
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

    def write_project_agent(self, project, name="tester", text=PROJECT_AGENT):
        return self.write_agent(project / ".opencode" / "agents", name, text)

    def config_path(self, project):
        return project / ".vibe" / "agents.json"

    def rows(self, project="proj"):
        return {row["name"]: row for row in self.cli.project_agent_rows(project)}

    def select(self, project, agent, selected=None, model=None):
        return self.cli.project_agent_set(project, agent, selected=selected, model=model)


class SelectionTest(ProjectAgentsFixture):
    def test_default_selection_uses_all_available_agents_and_their_models(self):
        self.write_global()
        self.write_project_agent(self.project, "pruefer", PROJECT_AGENT)
        self.write_project_agent(self.other, "fremd", OTHER_AGENT)

        rows = self.rows()

        self.assertEqual(sorted(rows), ["pruefer", "tester"])
        self.assertEqual(rows["tester"]["scope"], "global")
        self.assertEqual(rows["pruefer"]["scope"], "proj")
        self.assertTrue(all(row["selected"] for row in rows.values()))
        self.assertEqual(rows["tester"]["effective_model"], "opencode/global-modell")
        self.assertEqual(rows["pruefer"]["effective_model"], "opencode/projekt-modell")
        self.assertEqual(rows["tester"]["override"], "")
        # Die Auswahl ist reine Konfiguration: ohne Änderung entsteht keine Datei.
        self.assertFalse(self.config_path(self.project).exists())

    def test_project_agent_shadows_the_global_agent_and_is_listed_once(self):
        self.write_global()
        self.write_project_agent(self.project)

        rows = self.rows()

        self.assertEqual(sorted(rows), ["tester"])
        self.assertEqual(rows["tester"]["scope"], "proj")
        self.assertEqual(rows["tester"]["effective_model"], "opencode/projekt-modell")

    def test_disabled_agent_is_stored_for_one_project_only(self):
        self.write_global()

        self.select("proj", "tester", selected=False)

        self.assertFalse(self.rows("proj")["tester"]["selected"])
        # Das andere Projekt hat keine eigene Datei: dort bleibt der globale
        # Agent ausgewählt, die Abwahl wirkt also nur im gewählten Projekt.
        self.assertTrue(self.rows("other")["tester"]["selected"])
        stored = json.loads(self.config_path(self.project).read_text(encoding="utf-8"))
        self.assertEqual(stored["deaktiviert"], ["tester"])
        # Das andere Projekt bleibt ohne eigene Datei und unverändert.
        self.assertFalse(self.config_path(self.other).exists())

    def test_model_override_wins_over_the_agent_file_and_can_be_cleared(self):
        self.write_global()

        self.select("proj", "tester", model="opencode/projekt-speziell")

        row = self.rows("proj")["tester"]
        self.assertEqual(row["model"], "opencode/global-modell")
        self.assertEqual(row["override"], "opencode/projekt-speziell")
        self.assertEqual(row["effective_model"], "opencode/projekt-speziell")
        self.assertEqual(
            self.rows("other")["tester"]["effective_model"], "opencode/global-modell"
        )

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
            json.dumps({"deaktiviert": [], "modelle": {}, "farbe": "rot"}),
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
            json.dumps({"version": 1, "deaktiviert": [], "modelle": {"tester": 5}}),
            encoding="utf-8",
        )

        with self.assertRaises(ValueError) as caught:
            self.rows()

        self.assertIn("Zeichenkette", str(caught.exception))
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["modelle"]["tester"], 5)

    def test_concurrent_change_is_refused(self):
        self.write_global()
        path = self.config_path(self.project)
        path.write_text(
            json.dumps({"version": 1, "deaktiviert": [], "modelle": {}}),
            encoding="utf-8",
        )
        snapshot = self.cli.vibe_storage.read_snapshot(path)
        path.write_text(
            json.dumps({"version": 1, "deaktiviert": ["tester"], "modelle": {}}),
            encoding="utf-8",
        )

        with self.assertRaises(self.cli.vibe_storage.ConcurrentChangeError):
            self.cli.project_agents_save(
                "proj", {"deaktiviert": [], "modelle": {}}, expected=snapshot.digest
            )

        stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(stored["deaktiviert"], ["tester"])

    def test_cli_lists_selection_and_override(self):
        self.write_global()
        self.select("proj", "tester", model="opencode/projekt-speziell")

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
    def test_run_selection_rejects_a_disabled_agent(self):
        self.write_global()
        self.select("proj", "tester", selected=False)

        with self.assertRaises(ValueError) as caught:
            self.cli.run_agent_selection("proj", "tester")

        self.assertIn("nicht ausgewählt", str(caught.exception))

    def test_run_selection_allows_other_agents_without_model(self):
        self.write_global()
        self.select("proj", "tester", selected=False)

        self.assertEqual(self.cli.run_agent_selection("proj", "build"), "")

    def test_run_selection_returns_the_project_override(self):
        self.write_global()
        self.select("proj", "tester", model="opencode/projekt-speziell")

        self.assertEqual(
            self.cli.run_agent_selection("proj", "tester"), "opencode/projekt-speziell"
        )
        self.assertEqual(self.cli.run_agent_selection("other", "tester"), "")

    def test_cmd_run_aborts_before_tmux_for_a_disabled_agent(self):
        self.write_global()
        self.select("proj", "tester", selected=False)

        with mock.patch.object(self.cli, "tmux_has", return_value=False):
            with mock.patch.object(self.cli, "is_init", return_value=True):
                with mock.patch.object(
                    self.cli, "sandbox_status", return_value={"enabled": False}
                ):
                    with mock.patch.object(self.cli, "run") as runner:
                        with self.assertRaises(SystemExit) as caught:
                            self.cli.cmd_run("proj", "tester")

        self.assertIn("nicht ausgewählt", str(caught.exception.code))
        runner.assert_not_called()

    def test_cmd_run_passes_the_project_model_override(self):
        self.write_global()
        self.select("proj", "tester", model="opencode/projekt-speziell")
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
                                self.cli.cmd_run("proj", "tester")
        return registry, fake_run

    def test_cmd_run_updates_the_managed_rules_of_an_existing_project(self):
        self.write_global()
        agents = self.project / "AGENTS.md"
        agents.write_text(
            "# eigene Regel\n\n"
            + self.cli.GENERAL_RULES_MARK
            + "\n## Alt\n- veraltet\n<!-- /vibe:general-rules -->\n\n## Eigener Rest\n",
            encoding="utf-8",
        )

        self.run_with_mocks()

        text = agents.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# eigene Regel\n"))
        self.assertIn("## Eigener Rest\n", text)
        self.assertNotIn("- veraltet", text)
        for rule in ("KISS", "Clean Code", "Caching", "Invalidierung"):
            self.assertIn(rule, text)

    def test_cmd_run_adds_the_rules_block_to_an_existing_project_without_one(self):
        self.write_global()
        agents = self.project / "AGENTS.md"
        agents.write_text("# eigene Regel\n", encoding="utf-8")

        self.run_with_mocks()

        text = agents.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# eigene Regel\n"))
        self.assertEqual(text.count(self.cli.GENERAL_RULES_MARK), 1)
        for rule in ("KISS", "Clean Code", "Caching", "Invalidierung"):
            self.assertIn(rule, text)

    def test_cmd_run_aborts_when_the_general_rules_cannot_be_updated(self):
        self.write_global()

        with mock.patch.object(self.cli, "tmux_has", return_value=False):
            with mock.patch.object(self.cli, "is_init", return_value=True):
                with mock.patch.object(
                    self.cli, "ensure_general_rules", side_effect=OSError("gesperrt")
                ):
                    with mock.patch.object(self.cli, "run") as runner:
                        with self.assertRaises(SystemExit) as caught:
                            self.cli.cmd_run("proj", "tester")

        self.assertIn("konnten nicht aktualisiert werden", str(caught.exception.code))
        runner.assert_not_called()


FAKE_OPENCODE = """#!/usr/bin/env bash
printf '%s\\n' "$@" >> "$VIBE_FAKE_OPENCODE"
exit 0
"""

FAKE_CURL = """#!/usr/bin/env bash
exit 7
"""

NEXT_ITEM_ONCE = """import os, sys
here = os.path.dirname(os.path.abspath(__file__))
count_path = os.path.join(here, "next-calls")
try:
    calls = int(open(count_path, encoding="utf-8").read())
except OSError:
    calls = 0
if calls:
    sys.exit(1)
open(count_path, "w", encoding="utf-8").write("1")
open("/tmp/next_id", "w", encoding="utf-8").write("F1")
open("/tmp/next_block", "w", encoding="utf-8").write(
    "- [ ] F1 Testpaket\\n  Beschreibung: Test\\n"
)
"""


class RunnerModelTest(unittest.TestCase):
    """Der Läufer gibt eine Modellüberschreibung an ``opencode run`` weiter."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.install = self.root / "_toolchain"
        self.tool_bin = self.install / "bin"
        self.tool_bin.mkdir(parents=True)
        self.verify = self.install / "verify"
        self.verify.mkdir()
        self.runtime = self.root / "_logs"
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        shutil.copy(RUNNER, self.tool_bin / "vibe-run.sh")
        shutil.copy(BIN / "vibe_runs.py", self.tool_bin / "vibe_runs.py")
        self.calls = self.root / "opencode.calls"
        fakebin = self.root / "fakebin"
        fakebin.mkdir()
        for name, text in (("opencode", FAKE_OPENCODE), ("curl", FAKE_CURL)):
            path = fakebin / name
            path.write_text(text, encoding="utf-8")
            path.chmod(0o755)
        (self.verify / "next_item.py").write_text(NEXT_ITEM_ONCE, encoding="utf-8")
        (self.project / ".vibe" / "project.env").write_text(
            'TYPE=generic\nAGENT=tester\nVERIFY_FULL="true"\nMAX_RETRIES=0\n',
            encoding="utf-8",
        )
        self.env = isolated_env(self.root, self.home)
        self.env.update(
            {
                "VIBE_INSTALL": str(self.install),
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_MAX_PACKAGES": "1",
                "VIBE_FAKE_OPENCODE": str(self.calls),
                "PATH": str(fakebin) + os.pathsep + os.environ.get("PATH", ""),
            }
        )

    def tearDown(self):
        self.tmp.cleanup()

    def run_runner(self, *arguments):
        command = ["bash", str(RUNNER), str(self.project), *arguments]
        # Der Läufer legt Sperr- und Arbeitsdateien unter /tmp ab. In einer
        # Prüfumgebung mit schreibgeschütztem /tmp wird ein eigener,
        # schreibbarer Ordner über /tmp gelegt, damit derselbe echte Läufer
        # unverändert geprüft werden kann.
        if not os.access("/tmp", os.W_OK):
            if not shutil.which("bwrap"):
                self.fail("/tmp ist schreibgeschützt und bwrap fehlt; der Läufer kann keine Übergabedateien anlegen.")
            command = ["bwrap", "--dev-bind", "/", "/", "--tmpfs", "/tmp",
                       "--bind", str(self.root), str(self.root), *command]
        return subprocess.run(
            command,
            cwd=str(self.project),
            env=self.env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=90,
        )

    def test_model_override_is_forwarded_to_opencode(self):
        result = self.run_runner("tester", "opencode/projekt-speziell")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        arguments = self.calls.read_text(encoding="utf-8").splitlines()
        self.assertIn("run", arguments)
        self.assertIn("--model", arguments)
        self.assertEqual(
            arguments[arguments.index("--model") + 1], "opencode/projekt-speziell"
        )
        self.assertEqual(arguments[arguments.index("--agent") + 1], "tester")

    def test_without_override_no_model_flag_is_sent(self):
        result = self.run_runner("tester")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        arguments = self.calls.read_text(encoding="utf-8").splitlines()
        self.assertNotIn("--model", arguments)

    def test_invalid_model_aborts_before_opencode(self):
        result = self.run_runner("tester", "kein modell;rm -rf /")

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Modellangabe ungültig", result.stdout + result.stderr)
        self.assertFalse(self.calls.exists())


if __name__ == "__main__":
    unittest.main()
