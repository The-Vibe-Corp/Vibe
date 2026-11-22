"""AP03 — Agentenverwaltung: Backend- und Unit-Tests.

Diese Datei prüft ausschließlich die in AP03 neu vereinbarte Backend-Schnittstelle.
Sie leitet die Fälle aus dem Arbeitspaket, der SPEC.md und den AGENTS.md ab und
arbeitet in einem vollständig temporären VIBE-/HOME-Verzeichnis. Es findet kein
Modellaufruf, kein tmux-Start und kein Netzzugriff statt; ``models_list`` wird
durch eine leere Liste ersetzt.

Zuordnung der Testklassen zu den Akzeptanzkriterien des Arbeitspakets:

* ``VibeRoleTest`` / ``VibeRunGateTest`` — Rollen und Standardagent ``vibe``.
* ``AgentMetadataTest`` — Aufgabe/Ergebnis je Agent ohne Änderung der Agentendatei.
* ``HierarchyTest`` — Rechte, erlaubte Subagenten und Zyklusprüfung.
* ``ProjectConfigurationTest`` — ausschließlich globale Agenten, Version 2,
  Vibe-Standardauswahl und Modellüberschreibung.
* ``AgentTemplateTest`` — gültiges Frontmatter und Prompt-Gerüst.
* ``UiInfoTest`` — Daten für die allgemeine und die Projekt-UI.
* ``AgentApiTest`` — die Web-API übernimmt ``result``, ``task_allowed`` und
  ``role`` atomar.
"""
import importlib.machinery
import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"
WEB = BIN / "vibe-web.py"
SERVICES = BIN / "vibe_services.py"

AGENT_BASE = """---
description: Erste Beschreibung
mode: subagent
model: opencode/test-modell
permission:
  read: allow
  edit: deny
---

Erster Prompt.
"""

VIBE_AGENT = """---
description: Vibe-Standardagent für Nutzerunterstützung
mode: primary
model: opencode/vibe-modell
permission:
  read: allow
  edit: deny
---

Du unterstützt den Nutzer bei der Benutzung und Konfiguration von vibe.
"""

VIBE_AGENT_NO_MODEL = """---
description: Vibe-Agent ohne Modell
mode: primary
permission:
  read: allow
  edit: deny
---

Du unterstützt den Nutzer bei der Benutzung und Konfiguration von vibe.
"""

# Die Prüfumgebung erbt eine produktive vibe-Umgebung. Ohne diese Liste würde
# ein Test in den echten Agentenordner, den echten Zustandsordner oder die
# persönliche Konfiguration schreiben.
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
    "AGENT",
)


def isolated_env(root, home, port=None):
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
    if port is not None:
        env["VIBE_UI_PORT"] = str(port)
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
            "vibe_ap03_under_test", str(CLI)
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


def load_services():
    """Lädt bin/vibe_services.py mit den Modulen aus bin/."""
    sys.path.insert(0, str(BIN))
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_services_ap03_under_test", str(SERVICES)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    finally:
        try:
            sys.path.remove(str(BIN))
        except ValueError:
            pass
    return module


def field(value, name):
    """Liest ein Feld aus einem Dict oder einem Objekt; die Schnittstelle erlaubt beides."""
    if isinstance(value, dict):
        return value[name]
    return getattr(value, name)


def task_agent(allowed, mode="subagent", model="opencode/test-modell", task=None):
    """Agentendatei mit einem ``permission.task``-Block."""
    lines = ["---", "description: Agent", "mode: " + mode]
    if model:
        lines.append("model: " + model)
    lines += ["permission:", "  read: allow", "  edit: deny"]
    if task is not None:
        lines.append("  task: " + task)
    else:
        lines.append("  task:")
        lines.append('    "*": deny')
        for agent in allowed:
            lines.append("    " + agent + ": allow")
    lines += ["---", "", "Prompt."]
    return "\n".join(lines) + "\n"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Ap03Fixture(unittest.TestCase):
    """Temp-VIBE/HOME mit einem Projekt und einem globalen Agentenordner."""

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
            "TYPE=generic\n", encoding="utf-8"
        )
        return project

    def write_global(self, name="tester", text=AGENT_BASE):
        path = self.agents / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def write_project_agent(self, project, name="lokal", text=AGENT_BASE):
        folder = project / ".opencode" / "agents"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def set_roles(self, roles):
        data = self.cli.profiles_load()
        data["rollen"] = dict(roles)
        self.cli.profiles_save(data)

    def write_vibe(self, name="vibe-agent", text=VIBE_AGENT):
        path = self.write_global(name, text)
        roles = dict(self.cli.profiles_load().get("rollen", {}))
        roles[name] = "vibe"
        self.set_roles(roles)
        return path

    def config_path(self, project=None):
        return (project or self.project) / ".vibe" / "agents.json"

    def rows(self, project="proj"):
        return {row["name"]: row for row in self.cli.project_agent_rows(project)}

    def cmd_run(self, project="proj", agent=None):
        """Ruft cmd_run mit allen externen Grenzen als Attrappen auf."""
        calls = []
        self.run_mock = mock.Mock(
            side_effect=lambda argv, **kwargs: calls.append(argv) or (0, "")
        )
        registry = mock.MagicMock()
        with mock.patch.object(self.cli, "tmux_has", return_value=False):
            with mock.patch.object(self.cli, "is_init", return_value=True):
                with mock.patch.object(
                    self.cli, "sandbox_status", return_value={"enabled": False}
                ):
                    with mock.patch.object(
                        self.cli, "ensure_general_rules", return_value=False
                    ):
                        with mock.patch.object(
                            self.cli, "run_registry", return_value=registry
                        ):
                            with mock.patch.object(
                                self.cli.vibe_runs, "rotate_log"
                            ):
                                with mock.patch.object(
                                    self.cli, "run", self.run_mock
                                ):
                                    self.cli.cmd_run(project, agent)
        return calls


class VibeRoleTest(Ap03Fixture):
    """AK Rollen und Vibe-Agent."""

    def test_role_assignment_and_removal_for_non_vibe(self):
        self.write_global("tester")

        self.cli.agent_role_set("tester", "coder")
        self.assertEqual(
            self.cli.profiles_load()["rollen"].get("tester"), "coder"
        )

        self.cli.agent_role_set("tester", "")
        self.assertNotIn("tester", self.cli.profiles_load()["rollen"])

    def test_vibe_role_is_unique_and_cannot_be_removed_without_replacement(self):
        self.write_global("vibe-agent")
        self.write_global("second")

        self.cli.agent_role_set("vibe-agent", "vibe")
        self.assertEqual(self.cli.vibe_agent_name(), "vibe-agent")

        with self.assertRaises(ValueError):
            self.cli.agent_role_set("vibe-agent", "")
        with self.assertRaises(ValueError):
            self.cli.agent_role_set("vibe-agent", "coder")
        self.assertEqual(self.cli.vibe_agent_name(), "vibe-agent")

        # Umsetzen ist nur durch gleichzeitige Zuweisung an einen anderen
        # Agenten möglich; danach darf genau einer die Rolle tragen.
        self.cli.agent_role_set("second", "vibe")
        roles = self.cli.profiles_load()["rollen"]
        vibe_names = [name for name, role in roles.items() if role == "vibe"]
        self.assertEqual(vibe_names, ["second"])
        self.assertEqual(self.cli.vibe_agent_name(), "second")

    def test_vibe_agent_status_without_agent_reports_missing(self):
        status = self.cli.vibe_agent_status()

        self.assertFalse(field(status, "name"))
        self.assertFalse(field(status, "configured"))
        self.assertTrue(field(status, "missing_model"))

    def test_vibe_agent_status_without_model_reports_missing_model(self):
        self.write_global("vibe-agent", VIBE_AGENT_NO_MODEL)
        self.set_roles({"vibe-agent": "vibe"})

        status = self.cli.vibe_agent_status()

        self.assertEqual(field(status, "name"), "vibe-agent")
        self.assertFalse(field(status, "model"))
        self.assertFalse(field(status, "configured"))
        self.assertTrue(field(status, "missing_model"))

    def test_vibe_agent_status_with_model_is_configured(self):
        self.write_vibe()

        status = self.cli.vibe_agent_status()

        self.assertEqual(field(status, "name"), "vibe-agent")
        self.assertEqual(field(status, "model"), "opencode/vibe-modell")
        self.assertTrue(field(status, "configured"))
        self.assertFalse(field(status, "missing_model"))


class VibeRunGateTest(Ap03Fixture):
    """AK Rollen und Vibe-Agent: Projekte starten nur mit konfiguriertem Vibe-Agenten."""

    def test_cmd_run_aborts_without_a_vibe_agent(self):
        self.write_global("tester")

        with self.assertRaises(SystemExit) as caught:
            self.cmd_run()

        message = str(caught.exception.code).lower()
        self.assertTrue(
            "vibe-agent" in message or "vibe agent" in message, message
        )
        self.run_mock.assert_not_called()

    def test_cmd_run_aborts_when_the_vibe_agent_has_no_model(self):
        self.write_global("vibe-agent", VIBE_AGENT_NO_MODEL)
        self.set_roles({"vibe-agent": "vibe"})

        with self.assertRaises(SystemExit) as caught:
            self.cmd_run()

        message = str(caught.exception.code).lower()
        self.assertIn("vibe", message)
        self.assertIn("modell", message)
        self.run_mock.assert_not_called()

    def test_cmd_run_aborts_without_a_model_even_when_agent_is_set(self):
        # Ein Vibe-Agent ohne Modell sperrt jeden Lauf, auch wenn in der
        # Projektdatei noch ein alter AGENT-Eintrag steht. Die Ausnahme für
        # Altbestände gilt nur, solange gar kein Vibe-Agent definiert ist.
        self.write_global("tester")
        self.write_vibe("vibe-agent", VIBE_AGENT_NO_MODEL)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8"
        )

        with self.assertRaises(SystemExit) as caught:
            self.cmd_run()

        message = str(caught.exception.code).lower()
        self.assertIn("vibe", message)
        self.assertIn("modell", message)
        self.run_mock.assert_not_called()

    def test_cmd_run_uses_the_vibe_agent_when_no_agent_is_configured(self):
        self.write_vibe()

        calls = self.cmd_run()

        self.assertEqual(len(calls), 1)
        # Der Agent ist das vorletzte Argument; das letzte ist die (leere)
        # Modellüberschreibung des Projekts.
        self.assertEqual(calls[0][-2], "vibe-agent")

    def test_cmd_run_prefers_the_vibe_agent_over_a_coder_role(self):
        self.write_vibe()
        self.write_global("tester")
        self.set_roles({"vibe-agent": "vibe", "tester": "coder"})

        calls = self.cmd_run()

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][-2], "vibe-agent")


class AgentMetadataTest(Ap03Fixture):
    """AK Aufgaben/Ergebnisse: eigene Zustandsdatei statt Agentendatei."""

    def test_agent_result_is_stored_outside_the_agent_file(self):
        path = self.write_global("tester")
        before = path.read_text(encoding="utf-8")

        self.cli.agent_result_set("tester", "Ergebnis: fertig")
        self.assertEqual(self.cli.agent_result("tester"), "Ergebnis: fertig")
        self.assertEqual(path.read_text(encoding="utf-8"), before)

        meta = self.cli.agent_meta_load()
        self.assertIn("Ergebnis: fertig", json.dumps(meta, ensure_ascii=False))

        self.cli.agent_result_set("tester", "")
        self.assertEqual(self.cli.agent_result("tester"), "")

    def test_agent_meta_save_roundtrip(self):
        self.write_global("tester")
        self.cli.agent_result_set("tester", "gespeichert")

        meta = self.cli.agent_meta_load()
        self.cli.agent_meta_save(meta)

        self.assertEqual(self.cli.agent_result("tester"), "gespeichert")

    def test_agents_all_exposes_result_role_vibe_and_model_state(self):
        self.write_vibe()
        self.write_global("helper", task_agent(["vibe-agent"]))
        self.write_global("ohne-modell", VIBE_AGENT_NO_MODEL)
        self.cli.agent_result_set("helper", "hilft")
        self.set_roles({"vibe-agent": "vibe", "helper": "coder"})

        rows = {
            row["name"]: row
            for row in self.cli.agents_all()
            if row["scope"] == "global"
        }

        self.assertTrue(rows["vibe-agent"]["is_vibe"])
        self.assertFalse(rows["helper"]["is_vibe"])
        self.assertFalse(rows["vibe-agent"]["model_missing"])
        self.assertTrue(rows["ohne-modell"]["model_missing"])
        self.assertEqual(rows["helper"]["result"], "hilft")
        self.assertEqual(rows["helper"]["allowed_agents"], ["vibe-agent"])
        self.assertEqual(rows["helper"]["role"], "coder")


class HierarchyTest(Ap03Fixture):
    """AK Hierarchie und Berechtigungen."""

    def test_agent_task_policy_reads_all_none_and_custom(self):
        allowed = self.cli.agent_task_policy(task_agent([], task="allow"))
        self.assertEqual(allowed["mode"], "all")

        denied = self.cli.agent_task_policy(task_agent([], task="deny"))
        self.assertEqual(denied["mode"], "none")

        custom = self.cli.agent_task_policy(task_agent(["b", "a"]))
        self.assertEqual(custom["mode"], "custom")
        self.assertEqual(custom["allowed"], ["a", "b"])

    def test_agent_render_task_writes_a_permission_object_and_preserves_fields(self):
        self.write_global("a", task_agent([]))
        self.write_global("b", task_agent([]))

        rendered = self.cli.agent_render_task(
            "global", AGENT_BASE, ["b", "a"]
        )

        policy = self.cli.agent_task_policy(rendered)
        self.assertEqual(policy["mode"], "custom")
        self.assertEqual(policy["allowed"], ["a", "b"])
        # Alle anderen Frontmatter-Zeilen und der Prompt bleiben erhalten.
        self.assertIn("description: Erste Beschreibung", rendered)
        self.assertIn("mode: subagent", rendered)
        self.assertIn("model: opencode/test-modell", rendered)
        self.assertIn("edit: deny", rendered)
        self.assertIn("Erster Prompt.", rendered)
        # Das Ergebnis ist weiterhin ein gültiger Agent.
        self.cli.agent_validate(rendered)

    def test_agent_render_task_all_writes_task_allow(self):
        rendered = self.cli.agent_render_task("global", AGENT_BASE, [], allow_all=True)

        policy = self.cli.agent_task_policy(rendered)
        self.assertEqual(policy["mode"], "all")
        self.assertIn("description: Erste Beschreibung", rendered)
        self.cli.agent_validate(rendered)

    def test_agent_validate_hierarchy_rejects_unknown_and_cycles(self):
        # F32 erlaubt den Selbstaufruf eines gewöhnlichen Subagenten. Die
        # vollständige Abdeckung (erlaubt und abgelehnt) liegt in
        # test_f32_subagent_self_spawn.py; hier bleiben nur die unveränderten
        # Regeln für unbekannte Agenten und echte Zyklen.
        self.write_global("a", task_agent(["b"]))
        self.write_global("b", task_agent(["a"]))

        with self.assertRaises(ValueError):
            self.cli.agent_validate_hierarchy("a", ["unbekannt"])
        with self.assertRaises(ValueError):
            self.cli.agent_validate_hierarchy("a", ["b"])

        # Ohne Rückkante ist dieselbe Beziehung zulässig.
        self.write_global("b", task_agent([]))
        self.cli.agent_validate_hierarchy("a", ["b"])

    def test_agent_validate_hierarchy_accepts_only_global_subagents(self):
        self.write_global("a", task_agent([]))
        self.write_global("primary", task_agent([], mode="primary"))
        self.write_global("alle", task_agent([], mode="all"))
        self.write_project_agent(self.project, "lokal", task_agent([]))

        with self.assertRaises(ValueError):
            self.cli.agent_validate_hierarchy("a", ["primary"])
        with self.assertRaises(ValueError):
            self.cli.agent_validate_hierarchy("a", ["lokal"])

        # Globale Agenten mit mode subagent oder all dürfen aufgerufen werden.
        self.cli.agent_validate_hierarchy("a", ["alle"])


class ProjectConfigurationTest(Ap03Fixture):
    """AK Projektkonfiguration: globale Agenten, Version 2, Vibe als Standard."""

    def test_missing_config_activates_only_the_vibe_agent(self):
        self.write_vibe()
        self.write_global("tester")

        rows = self.rows()

        self.assertTrue(rows["vibe-agent"]["configured"])
        self.assertTrue(rows["vibe-agent"]["is_vibe"])
        self.assertFalse(rows["tester"]["configured"])
        self.assertFalse(rows["tester"]["selected"])
        self.assertFalse(self.config_path().exists())

    def test_version_1_is_migrated_to_version_3_without_losing_overrides(self):
        self.write_vibe()
        self.write_global("tester")
        self.write_global("other")
        self.config_path().write_text(
            json.dumps(
                {
                    "version": 1,
                    "deaktiviert": ["other"],
                    "modelle": {"tester": "opencode/override"},
                }
            ),
            encoding="utf-8",
        )

        config, _snapshot = self.cli.project_agents_load("proj")
        self.assertEqual(config["version"], 3)
        self.assertEqual(set(config["aktiv"]), {"vibe-agent", "tester"})
        self.assertNotIn("other", config["aktiv"])

        rows = self.rows()
        self.assertTrue(rows["vibe-agent"]["configured"])
        self.assertTrue(rows["tester"]["configured"])
        self.assertFalse(rows["other"]["configured"])
        self.assertEqual(rows["tester"]["override"], "opencode/override")
        self.assertEqual(rows["tester"]["effective_model"], "opencode/override")

    def test_project_agent_inventory_only_offers_global_agents(self):
        self.write_vibe()
        self.write_global("tester")
        self.write_project_agent(self.project, "lokal")

        inventory = self.cli.project_agent_inventory("proj")

        self.assertIn("vibe-agent", inventory)
        self.assertIn("tester", inventory)
        self.assertNotIn("lokal", inventory)

    def test_project_agent_rows_exposes_the_required_fields(self):
        self.write_vibe()
        self.write_global("tester")
        self.cli.agent_result_set("tester", "Ergebnis des Testers")

        row = self.rows()["tester"]

        for key in (
            "configured",
            "selected",
            "is_vibe",
            "model",
            "effective_model",
            "override",
            "result",
            "role",
            "allowed_agents",
        ):
            self.assertIn(key, row)
        self.assertFalse(row["configured"])
        self.assertEqual(row["selected"], row["configured"])
        self.assertFalse(row["is_vibe"])
        self.assertEqual(row["result"], "Ergebnis des Testers")
        self.assertEqual(row["role"], "")
        self.assertIsInstance(row["allowed_agents"], list)

    def test_project_agent_set_refuses_deselecting_the_vibe_agent(self):
        self.write_vibe()
        self.write_global("tester")

        with self.assertRaises(ValueError):
            self.cli.project_agent_set("proj", "vibe-agent", selected=False)

        self.assertFalse(self.config_path().exists())
        self.assertTrue(self.rows()["vibe-agent"]["configured"])

    def test_project_agent_set_rejects_project_local_and_unknown_agents(self):
        self.write_vibe()
        self.write_project_agent(self.project, "lokal")

        with self.assertRaises(ValueError):
            self.cli.project_agent_set("proj", "lokal", selected=False)
        with self.assertRaises(ValueError):
            self.cli.project_agent_set("proj", "unbekannt", selected=False)

        self.assertFalse(self.config_path().exists())

    def test_model_override_is_independent_of_selection(self):
        self.write_vibe()
        self.write_global("tester")

        self.cli.project_agent_set("proj", "tester", model="opencode/override")

        row = self.rows()["tester"]
        self.assertFalse(row["configured"])
        self.assertEqual(row["override"], "opencode/override")
        stored = json.loads(self.config_path().read_text(encoding="utf-8"))
        self.assertEqual(stored["version"], 3)
        self.assertNotIn("tester", stored["aktiv"])
        self.assertEqual(stored["modelle"]["tester"], "opencode/override")

    def test_run_agent_selection_rejects_unconfigured_and_returns_override(self):
        self.write_vibe()
        self.write_global("tester")

        with self.assertRaises(ValueError):
            self.cli.run_agent_selection("proj", "tester")

        self.assertEqual(self.cli.run_agent_selection("proj", "vibe-agent"), "")

        self.cli.project_agent_set(
            "proj", "tester", selected=True, model="opencode/override"
        )
        self.assertEqual(
            self.cli.run_agent_selection("proj", "tester"), "opencode/override"
        )

        self.cli.project_agent_set("proj", "tester", selected=False)
        with self.assertRaises(ValueError):
            self.cli.run_agent_selection("proj", "tester")


class AgentTemplateTest(Ap03Fixture):
    """AK Agent speichern: Vorlage und Prompt-Gerüst."""

    def test_agent_template_still_produces_valid_frontmatter(self):
        text = self.cli.agent_template(
            "Neuer Agent", model="opencode/test-modell", prompt="Aufgabe"
        )

        self.assertTrue(text.startswith("---\n"))
        fields = self.cli.agent_validate(text)
        self.assertEqual(fields["description"], "Neuer Agent")

    def test_prompt_scaffold_contains_the_required_sections(self):
        text = self.cli.agent_prompt_scaffold(
            "Die Aufgabe", "Das Ergebnis", "Die Grenze"
        )

        for expected in (
            "## Aufgabe",
            "## Ergebnis",
            "## Grenzen",
            "Die Aufgabe",
            "Das Ergebnis",
            "Die Grenze",
        ):
            self.assertIn(expected, text)
        # Der Satz zur Abkapselung darf "Abkapselung" oder "abgekapselt" heißen.
        self.assertIn("kapsel", text.lower())

        without_limits = self.cli.agent_prompt_scaffold("A", "E")
        self.assertIn("## Grenzen", without_limits)


class UiInfoTest(Ap03Fixture):
    """AK UI-Daten aus vibe_services."""

    def setUp(self):
        super().setUp()
        self.services = load_services()

    def agent_row(self, data, name):
        for key in ("agents", "global_agents"):
            rows = data.get(key) or []
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict) and row.get("name") == name:
                        return row
        self.fail(f"Agent {name!r} fehlt in der UI-Antwort: {data!r}")

    def test_agents_info_exposes_vibe_status_roles_and_agent_fields(self):
        self.write_vibe()
        self.write_global("tester")
        self.cli.agent_result_set("tester", "UI-Ergebnis")
        self.set_roles({"vibe-agent": "vibe", "tester": "coder"})

        data = self.services.agents_info(self.cli)

        self.assertIn("vibe_agent", data)
        self.assertEqual(field(data["vibe_agent"], "name"), "vibe-agent")
        self.assertTrue(field(data["vibe_agent"], "configured"))
        self.assertIn("roles", data)
        self.assertEqual(data["roles"].get("tester"), "coder")
        self.assertIn("global_agents", data)

        row = self.agent_row(data, "tester")
        self.assertEqual(row["result"], "UI-Ergebnis")
        self.assertEqual(row["role"], "coder")
        self.assertIn("allowed_agents", row)
        self.assertIn("model_missing", row)

    def test_project_agents_info_exposes_configuration_and_unconfigured_count(self):
        self.write_vibe()
        self.write_global("tester")
        self.cli.agent_result_set("tester", "Projekt-Ergebnis")

        data = self.services.project_agents_info(self.cli, "proj")

        rows = {row["name"]: row for row in data["agents"]}
        self.assertTrue(rows["vibe-agent"]["configured"])
        self.assertTrue(rows["vibe-agent"]["is_vibe"])
        self.assertFalse(rows["tester"]["configured"])
        for key in ("result", "role", "allowed_agents"):
            self.assertIn(key, rows["tester"])
        self.assertEqual(rows["tester"]["result"], "Projekt-Ergebnis")
        self.assertEqual(data["available_unconfigured"], 1)


class AgentApiTest(unittest.TestCase):
    """AK Agent speichern: Web-API übernimmt die neuen Felder atomar."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.agents / "vibe-agent.md").write_text(VIBE_AGENT, encoding="utf-8")
        (cls.agents / "helper.md").write_text(
            task_agent([]), encoding="utf-8"
        )
        (cls.agents / "tester.md").write_text(AGENT_BASE, encoding="utf-8")
        state = cls.root / "_toolchain"
        state.mkdir()
        (state / "profiles.json").write_text(
            json.dumps({"rollen": {"vibe-agent": "vibe"}}), encoding="utf-8"
        )
        # Der Server ruft beim Speichern ``opencode --version`` und
        # ``opencode models`` auf. Beide werden hier durch ein schnelles
        # Ersatzprogramm beantwortet; es findet kein echter Modellaufruf statt.
        fakebin = cls.root / "fakebin"
        fakebin.mkdir()
        fake_opencode = fakebin / "opencode"
        fake_opencode.write_text(
            "#!/usr/bin/env bash\n"
            "case \"$1\" in\n"
            "  --version) printf 'opencode 2.1.4\\n' ;;\n"
            "  models) printf 'opencode/test-modell\\nopencode/vibe-modell\\nopencode/helper-modell\\n' ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        fake_opencode.chmod(0o755)
        cls.port = free_port()
        env = isolated_env(cls.root, cls.home, cls.port)
        env["PATH"] = str(fakebin) + os.pathsep + env.get("PATH", "")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        cls.pgid = os.getpgid(cls.proc.pid)
        token_file = cls.root / "_logs" / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
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
        cls.cli = load_cli(cls.root, cls.home)

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
        try:
            os.killpg(cls.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        cls.tmp.cleanup()

    def setUp(self):
        self.path = self.agents / "tester.md"
        self.path.write_text(AGENT_BASE, encoding="utf-8")

    def request(self, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            method="POST" if data else "GET",
        )
        req.add_header("Host", f"127.0.0.1:{self.port}")
        req.add_header("X-Token", self.token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            code = error.code
            error.close()
            return code, body

    def digest(self):
        status, body = self.request("/api/agent?scope=global&name=tester")
        self.assertEqual(status, 200, body)
        return json.loads(body)["digest"]

    def test_api_save_accepts_result_task_allowed_and_role(self):
        status, body = self.request(
            "/api/agent",
            {
                "action": "save",
                "scope": "global",
                "name": "tester",
                "text": AGENT_BASE,
                "values": {"description": "Neu beschrieben"},
                "result": "Fertig",
                "task_allowed": ["helper"],
                "role": "coder",
                "expected": self.digest(),
            },
        )

        self.assertEqual(status, 200, body)
        saved = self.path.read_text(encoding="utf-8")
        self.assertIn("description: Neu beschrieben", saved)
        self.assertEqual(self.cli.agent_result("tester"), "Fertig")
        self.assertEqual(
            self.cli.profiles_load()["rollen"].get("tester"), "coder"
        )
        policy = self.cli.agent_task_policy(saved)
        self.assertEqual(policy["mode"], "custom")
        self.assertEqual(policy["allowed"], ["helper"])

    def test_api_save_rejects_invalid_new_values_without_touching_the_file(self):
        broken = (
            {"result": 123},
            {"task_allowed": "helper"},
            {"task_allowed": ["unbekannt"]},
            {"role": 123},
        )
        for payload in broken:
            with self.subTest(payload=payload):
                status, body = self.request(
                    "/api/agent",
                    {
                        "action": "save",
                        "scope": "global",
                        "name": "tester",
                        "text": AGENT_BASE,
                        **payload,
                    },
                )
                self.assertEqual(status, 400, body)
                self.assertEqual(
                    self.path.read_text(encoding="utf-8"), AGENT_BASE
                )


if __name__ == "__main__":
    unittest.main()
