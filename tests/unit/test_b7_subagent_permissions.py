"""Unabhängige Abnahmetests B7: Subagenten-Rechte beim Regenerieren von Agentendateien.

Auftrag (FEEDBACK.md, B7): Wird eine Agentendatei im GUI auf das
opencode-v2-Format regeneriert, indem eine Rechte-Vorlage (``voll``,
``lesen``, ``lesen_git``) gewählt und gespeichert wird, entsteht bisher
stillschweigend ``subagent * deny`` — auch dann, wenn die Eingabedatei
Subagenten erlaubte (v1 ``task: allow``). Der Orchestrator kann danach keine
Subagenten mehr aufrufen, obwohl die Oberfläche weiterhin „alle“ anzeigt.

Soll (aus dem Arbeitspaket abgeleitet, nicht aus einem Implementierungsdiff):

1. Rechte-Vorlage und Subagenten-Rechte sind zwei unabhängige Dimensionen.
   Eine angewendete Vorlage darf die Subagenten-Policy der *Eingabedatei*
   nicht stillschweigend verändern. Nur die Nicht-subagent-Regeln kommen aus
   der Vorlage; die Subagenten-Regeln geben die Policy der Eingabedatei
   wieder. Ohne vorhandene Subagenten-Regeln gilt der Vorlagen-Standard
   (``subagent * deny``).
2. Eine im selben Request ausdrücklich gesendete Subagenten-Auswahl
   (``task_allowed`` oder ``task_all``) gewinnt gegen die Vorlage.
3. Das gilt end-to-end über ``/api/agent`` (``action=save`` und
   ``action=render``) mit der Payload-Sequenz der klassischen UI — besonders
   für den gemeldeten Fall „save mit ``values:{permission:'voll'}`` ohne
   task-Felder auf einer v1-Datei mit ``task: allow``“.
4. Neuanlage (``agent_template``) und ``agent_render_task`` ohne Vorlage
   bleiben unverändert.

Gruppierung der Testklassen:

* ``RenderFieldsSubagentPolicyTest`` — ``agent_render_fields`` (Serverpfad
  beider GUI-Aktionen) mit Vorlage auf v1-/v2-/blocklosen Eingabedateien.
* ``ExplicitSelectionTest`` — Serverreihenfolge „erst Felder, dann
  Auswahl“ auf Modulebene.
* ``TemplateRegressionTest`` — Charakterisierung von ``agent_template`` und
  ``agent_render_task`` ohne Vorlage (Arbeitspaket Punkt 4).
* ``AgentApiTest`` — echter HTTP-Weg über ``bin/vibe-web.py`` mit der
  Payload-Sequenz der klassischen UI.

Alle Fälle arbeiten ausschließlich in temporären VIBE-/HOME-/State-Pfaden.
Es gibt keine Modellaufrufe, keinen Anbieternetzugriff, keine OAuth-Anmeldung
und keine produktiven MCP-Aufrufe; ``opencode`` ist eine Attrappe.
"""
import importlib.machinery
import importlib.util
import json
import os
import re
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

# Variablen der laufenden Instanz dürfen nie in einen Testprozess gelangen.
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
    "VIBE_UI_BIND",
    "VIBE_OPENCODE_PORT",
    "VIBE_CONTAINER",
    "AGENT",
    "SANDBOX",
    "SANDBOX_TOOLS",
    "VIBE_SANDBOX_ROOT",
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
            "vibe_b7_under_test", str(CLI)
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


# --------------------------------------------------------------------------
# Parser-Helfer: prüfen die Struktur, nicht die Byte-Position der Blöcke.
# --------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.S)


def frontmatter_lines(text):
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise AssertionError("Kein Frontmatter in:\n" + text)
    return match.group(1).splitlines()


def unquote(value):
    value = (value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return json.loads(value)
        except ValueError:
            return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def _key_value(line):
    match = re.match(r"^[ \t]*(?:-[ \t]+)?([A-Za-z_][\w-]*):[ \t]*(.*)$", line)
    if not match:
        return None
    return match.group(1), unquote(match.group(2))


def parse_permissions(text):
    """Liest einen v2-``permissions``-Block als Liste von Regel-Dicts.

    Die Reihenfolge der Regeln bleibt erhalten; ``None`` bedeutet, dass kein
    v2-Block vorhanden ist (z. B. ein v1-``permission``-Block).
    """
    if FRONTMATTER_RE.match(text):
        lines = frontmatter_lines(text)
    else:
        lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(r"^permissions:[ \t]*$", line):
            start = index + 1
            break
    if start is None:
        return None
    rules, current = [], None
    for line in lines[start:]:
        if line and not line.startswith((" ", "\t")):
            break
        if not line.strip():
            continue
        if re.match(r"^[ \t]*-[ \t]+", line):
            if current is not None:
                rules.append(current)
            current = {}
        item = _key_value(line)
        if item is None:
            continue
        if current is None:
            current = {}
        current[item[0]] = item[1]
    if current is not None:
        rules.append(current)
    return rules


def rule_pairs(text, action):
    """(resource, effect)-Paare aller Regeln einer Aktion, in Blockreihenfolge."""
    rules = parse_permissions(text)
    if rules is None:
        raise AssertionError("Kein v2-permissions-Block in:\n" + text)
    return [
        (rule.get("resource"), rule.get("effect"))
        for rule in rules
        if rule.get("action") == action
    ]


def non_subagent_rules(text):
    """Alle Regeln außer ``subagent`` als (action, resource, effect)."""
    rules = parse_permissions(text)
    if rules is None:
        raise AssertionError("Kein v2-permissions-Block in:\n" + text)
    return [
        (rule.get("action"), rule.get("resource"), rule.get("effect"))
        for rule in rules
        if rule.get("action") != "subagent"
    ]


def preset_non_subagent(preset):
    """Erwartete Nicht-subagent-Regeln einer Rechte-Vorlage (AP2-Vertrag)."""
    return [rule for rule in PRESET_RULES[preset] if rule[0] != "subagent"]


def has_top_level_key(text, key):
    return any(
        re.match(r"^" + re.escape(key) + r":[ \t]*(.*)$", line)
        for line in frontmatter_lines(text)
    )


# --------------------------------------------------------------------------
# Eingabedateien
# --------------------------------------------------------------------------

# Produktionsnahe v1-Datei aus dem gemeldeten Fall: der Nutzer hatte
# ``task: allow`` von Hand gesetzt, damit der Orchestrator Subagenten ruft.
V1_TASK_ALLOW_AGENT = """---
description: Orchestrator mit erlaubten Subagenten
mode: primary
model: opencode/orchestrator-modell
permission:
  read: allow
  glob: allow
  grep: allow
  list: allow
  edit: allow
  bash: allow
  task: allow
  webfetch: deny
  websearch: deny
---

Bestehender Prompt.
"""

# v1-Datei mit individueller task-Map (deny-Grundregel plus zwei Freigaben).
V1_TASK_CUSTOM_AGENT = """---
description: Agent mit ausgewaehlten Subagenten
mode: subagent
permission:
  read: allow
  edit: deny
  task:
    "*": deny
    vibe-coder: allow
    tester: allow
---

Individueller Prompt.
"""

# v1-Vorlage „lesen“: Subagenten ausdrücklich gesperrt.
V1_TASK_DENY_AGENT = """---
description: Nur lesen ohne Subagenten
mode: subagent
permission:
  read: allow
  glob: allow
  grep: allow
  list: allow
  edit: deny
  bash: deny
  task: deny
  webfetch: deny
  websearch: deny
---

Lese-Prompt.
"""

# v1-Datei ganz ohne task-Eintrag: daraus darf keine Freigabe erfunden werden.
V1_NO_TASK_AGENT = """---
description: Alt ohne task-Eintrag
mode: subagent
permission:
  read: allow
  glob: allow
  grep: allow
  list: allow
  edit: allow
  bash: allow
  webfetch: deny
  websearch: deny
---

Prompt ohne task.
"""


def v2_agent(rules, description="V2-Agent", mode="subagent", model="opencode/test-modell"):
    lines = ["---", "description: " + description, "mode: " + mode]
    if model:
        lines.append("model: " + model)
    lines.append("permissions:")
    for action, resource, effect in rules:
        lines.append("  - action: " + action)
        lines.append("    resource: " + json.dumps(resource))
        lines.append("    effect: " + effect)
    lines += ["---", "", "Prompt."]
    return "\n".join(lines) + "\n"


V2_SUBAGENT_CUSTOM_RULES = [
    ("read", "*", "allow"),
    ("edit", "*", "deny"),
    ("shell", "*", "deny"),
    ("subagent", "*", "deny"),
    ("subagent", "tester", "allow"),
    ("subagent", "vibe-coder", "allow"),
]

V2_SUBAGENT_CUSTOM_AGENT = v2_agent(
    V2_SUBAGENT_CUSTOM_RULES, description="V2 mit ausgewaehlten Subagenten"
)

V2_SUBAGENT_ALL_AGENT = v2_agent(
    [
        ("read", "*", "allow"),
        ("edit", "*", "deny"),
        ("subagent", "*", "allow"),
    ],
    description="V2 mit allen Subagenten",
)

V2_WITHOUT_SUBAGENT_AGENT = v2_agent(
    [("read", "*", "allow"), ("edit", "*", "deny")],
    description="V2 ohne Subagentenregeln",
)

NO_BLOCK_AGENT = """---
description: Datei ohne Rechteblock
mode: subagent
---

Prompt ohne Rechte.
"""

# Vertrag der Rechte-Vorlagen (AP2 prüft die Vorlagen selbst; B7 nutzt sie als
# erwartete Nicht-subagent-Regeln).
PRESET_RULES = {
    "voll": [
        ("read", "*", "allow"),
        ("glob", "*", "allow"),
        ("grep", "*", "allow"),
        ("edit", "*", "allow"),
        ("shell", "*", "allow"),
        ("subagent", "*", "deny"),
        ("webfetch", "*", "deny"),
        ("websearch", "*", "deny"),
    ],
    "lesen": [
        ("read", "*", "allow"),
        ("glob", "*", "allow"),
        ("grep", "*", "allow"),
        ("edit", "*", "deny"),
        ("shell", "*", "deny"),
        ("subagent", "*", "deny"),
        ("webfetch", "*", "deny"),
        ("websearch", "*", "deny"),
    ],
    "lesen_git": [
        ("read", "*", "allow"),
        ("glob", "*", "allow"),
        ("grep", "*", "allow"),
        ("edit", "*", "deny"),
        ("shell", "*", "deny"),
        ("shell", "git status --short", "allow"),
        ("shell", "git diff *", "allow"),
        ("shell", "git show *", "allow"),
        ("shell", "git log *", "allow"),
        ("subagent", "*", "deny"),
        ("webfetch", "*", "deny"),
        ("websearch", "*", "deny"),
    ],
}


class CliFixture(unittest.TestCase):
    """Temp-VIBE/HOME mit einem Projekt und einem globalen Agentenordner."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        self.agents.mkdir(parents=True)
        self.project = self.make_project("proj")
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

    def write_global(self, name, text):
        path = self.agents / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path


# --------------------------------------------------------------------------
# 1. Vorlage anwenden: Subagenten-Policy der Eingabedatei bleibt erhalten
# --------------------------------------------------------------------------


class RenderFieldsSubagentPolicyTest(CliFixture):
    """``agent_render_fields`` (Serverpfad von „Speichern“ und „In Rohtext übernehmen“).

    Vorbedingung ist jeweils eine Agentendatei im temporären Agentenordner;
    Aktion ist das Anwenden einer Rechte-Vorlage über ``values.permission``;
    Erwartung ist, dass nur die Nicht-subagent-Regeln aus der Vorlage kommen
    und die Subagenten-Rechte die Policy der Eingabedatei wiedergeben.
    """

    def render(self, text, values):
        return self.cli.agent_render_fields("global", text, values)

    def test_v1_task_allow_survives_preset_application(self):
        """Gemeldeter Fall: v1 ``task: allow`` + Vorlage ``voll`` bleibt erlaubt.

        Vorher: Datei erlaubt Subagenten über v1 ``task: allow``.
        Aktion: ``agent_render_fields(..., {"permission": "voll"})``.
        Erwartet: v2-Block ohne v1-Schlüssel, Nicht-subagent-Regeln der Vorlage
        ``voll``, Subagenten-Policy weiterhin „alle“ (allow-Regel vorhanden).
        """
        changed = self.render(V1_TASK_ALLOW_AGENT, {"permission": "voll"})

        self.assertFalse(
            has_top_level_key(changed, "permission"),
            "Der v1-Block 'permission:' wurde nicht auf v2 migriert:\n" + changed,
        )
        self.assertEqual(
            self.cli.agent_task_policy(changed), {"mode": "all", "allowed": []}
        )
        self.assertIn(("*", "allow"), rule_pairs(changed, "subagent"))
        self.assertEqual(non_subagent_rules(changed), preset_non_subagent("voll"))
        self.assertIn("Bestehender Prompt.", changed)
        self.cli.agent_validate(changed)

    def test_v1_custom_task_map_survives_preset_application(self):
        """v1-task-Map (deny + Freigaben) bleibt nach Vorlage ``lesen`` erhalten.

        Vorher: ``task: {"*": deny, "vibe-coder": allow, "tester": allow}``.
        Aktion: Vorlage ``lesen`` anwenden.
        Erwartet: deny-Grundregel plus sortierte Freigaben ``tester``,
        ``vibe-coder``; die Freigaben dürfen nicht auf die Vorlagen-Sperre
        zurückfallen.
        """
        changed = self.render(V1_TASK_CUSTOM_AGENT, {"permission": "lesen"})

        self.assertEqual(
            self.cli.agent_task_policy(changed),
            {"mode": "custom", "allowed": ["tester", "vibe-coder"]},
        )
        self.assertEqual(
            rule_pairs(changed, "subagent"),
            [("*", "deny"), ("tester", "allow"), ("vibe-coder", "allow")],
        )
        self.assertEqual(non_subagent_rules(changed), preset_non_subagent("lesen"))
        self.cli.agent_validate(changed)

    def test_v2_subagent_rules_survive_preset_application(self):
        """Vorhandene v2-Subagenten-Regeln bleiben bei Vorlage ``lesen_git``.

        Vorher: v2-Datei mit ``subagent`` deny + zwei Freigaben (bzw. allow
        für ``*``).
        Aktion: Vorlage ``lesen_git`` anwenden.
        Erwartet: Subagenten-Regeln unverändert, alle anderen Regeln aus der
        Vorlage (inklusive der vier erlaubten Git-Lesebefehle).
        """
        for text in (V2_SUBAGENT_CUSTOM_AGENT, V2_SUBAGENT_ALL_AGENT):
            with self.subTest(text=text.splitlines()[1]):
                before = rule_pairs(text, "subagent")
                changed = self.render(text, {"permission": "lesen_git"})
                self.assertEqual(rule_pairs(changed, "subagent"), before)
                self.assertEqual(
                    non_subagent_rules(changed), preset_non_subagent("lesen_git")
                )
                self.cli.agent_validate(changed)

    def test_v2_without_subagent_rules_gets_template_default_deny(self):
        """Charakterisierung: v2 ohne subagent-Regeln erhält die Vorlagen-Sperre.

        Vorher: v2-Datei nur mit ``read``/``edit``. Aktion: Vorlage ``lesen``.
        Erwartet: genau eine Subagenten-Regel ``* deny`` (keine Regeln
        erfinden, identisch zum bisherigen Verhalten).
        """
        changed = self.render(V2_WITHOUT_SUBAGENT_AGENT, {"permission": "lesen"})

        self.assertEqual(rule_pairs(changed, "subagent"), [("*", "deny")])
        self.assertEqual(non_subagent_rules(changed), preset_non_subagent("lesen"))

    def test_file_without_permission_block_gets_template_default_deny(self):
        """Charakterisierung: Datei ohne Rechteblock erhält Vorlagen-Standard.

        Vorher: Frontmatter ohne ``permission``/``permissions``. Aktion:
        Vorlage ``voll``. Erwartet: neuer v2-Block mit Subagenten-Sperre.
        """
        changed = self.render(NO_BLOCK_AGENT, {"permission": "voll"})

        self.assertFalse(has_top_level_key(changed, "permission"))
        self.assertEqual(rule_pairs(changed, "subagent"), [("*", "deny")])
        self.assertEqual(non_subagent_rules(changed), preset_non_subagent("voll"))

    def test_v1_task_deny_stays_denied_under_preset(self):
        """Guard: eine bestehende Sperre darf nicht in eine Freigabe kippen.

        Vorher: v1 ``task: deny``. Aktion: Vorlage ``voll``. Erwartet:
        Subagenten bleiben gesperrt (genau ``* deny``).
        """
        changed = self.render(V1_TASK_DENY_AGENT, {"permission": "voll"})

        self.assertEqual(
            self.cli.agent_task_policy(changed), {"mode": "none", "allowed": []}
        )
        self.assertEqual(rule_pairs(changed, "subagent"), [("*", "deny")])

    def test_v1_without_task_key_gets_template_default_deny(self):
        """Guard: ohne task-Eintrag wird keine Subagenten-Freigabe erfunden.

        Vorher: v1-Block ohne ``task`` (Standard ohne Eintrag = gesperrt).
        Aktion: Vorlage ``lesen``. Erwartet: Vorlagen-Standard ``* deny``.
        """
        changed = self.render(V1_NO_TASK_AGENT, {"permission": "lesen"})

        self.assertEqual(
            self.cli.agent_task_policy(changed), {"mode": "none", "allowed": []}
        )
        self.assertEqual(rule_pairs(changed, "subagent"), [("*", "deny")])

    def test_empty_permission_value_leaves_the_block_untouched(self):
        """Charakterisierung: ohne gewählte Vorlage bleibt der Block unverändert.

        Vorher: v1 ``task: allow``. Aktion: ``values`` mit ``permission: ""``
        und geänderter Beschreibung. Erwartet: v1-Block bleibt v1-Block,
        Subagenten bleiben erlaubt; nur die Beschreibung ändert sich.
        """
        changed = self.render(
            V1_TASK_ALLOW_AGENT,
            {"permission": "", "description": "Neu beschrieben"},
        )

        self.assertIn("description: Neu beschrieben", changed)
        self.assertTrue(has_top_level_key(changed, "permission"))
        self.assertIsNone(parse_permissions(changed))
        self.assertEqual(
            self.cli.agent_task_policy(changed), {"mode": "all", "allowed": []}
        )


# --------------------------------------------------------------------------
# 2. Serverreihenfolge: erst Felder/Vorlage, dann ausdrückliche Auswahl
# --------------------------------------------------------------------------


class ExplicitSelectionTest(CliFixture):
    """Die ausdrückliche Subagenten-Auswahl gewinnt gegen die Vorlage.

    Die Serverreihenfolge ist ``agent_render_fields`` (Vorlage) und danach
    ``agent_render_task`` (Auswahl aus der Oberfläche); diese Reihenfolge wird
    hier nachgestellt.
    """

    def test_explicit_allowed_list_overrides_preset(self):
        """Vorlage ``voll`` + ``task_allowed=["tester"]`` ergibt nur tester.

        Vorher: v1 ``task: allow`` (würde nach der Korrektur „alle“ ergeben).
        Aktion: Vorlage anwenden, dann Auswahl ``["tester"]``.
        Erwartet: Policy ``custom`` mit genau ``tester`` — die ausdrückliche
        Auswahl gewinnt.
        """
        text = self.cli.agent_render_fields(
            "global", V1_TASK_ALLOW_AGENT, {"permission": "voll"}
        )

        changed = self.cli.agent_render_task("global", text, ["tester"])

        self.assertEqual(
            self.cli.agent_task_policy(changed),
            {"mode": "custom", "allowed": ["tester"]},
        )
        self.assertEqual(
            rule_pairs(changed, "subagent"),
            [("*", "deny"), ("tester", "allow")],
        )
        self.assertEqual(non_subagent_rules(changed), preset_non_subagent("voll"))

    def test_explicit_allow_all_overrides_denied_preset(self):
        """Vorlage ``lesen`` + ``task_all=true`` ergibt „alle“.

        Vorher: v1 ``task: deny``. Aktion: Vorlage anwenden, dann
        ``allow_all=True``. Erwartet: genau ``* allow``.
        """
        text = self.cli.agent_render_fields(
            "global", V1_TASK_DENY_AGENT, {"permission": "lesen"}
        )

        changed = self.cli.agent_render_task("global", text, [], allow_all=True)

        self.assertEqual(
            self.cli.agent_task_policy(changed), {"mode": "all", "allowed": []}
        )
        self.assertEqual(rule_pairs(changed, "subagent"), [("*", "allow")])

    def test_explicit_empty_selection_denies_even_when_input_allowed(self):
        """Vorlage ``voll`` + leere Auswahl („keine“) ergibt gesperrt.

        Vorher: v1 ``task: allow``. Aktion: Vorlage anwenden, dann
        ``agent_render_task(..., [])``. Erwartet: genau ``* deny``.
        """
        text = self.cli.agent_render_fields(
            "global", V1_TASK_ALLOW_AGENT, {"permission": "voll"}
        )

        changed = self.cli.agent_render_task("global", text, [])

        self.assertEqual(
            self.cli.agent_task_policy(changed), {"mode": "none", "allowed": []}
        )
        self.assertEqual(rule_pairs(changed, "subagent"), [("*", "deny")])


# --------------------------------------------------------------------------
# 3. Unverändert: Neuanlage und Auswahl ohne Vorlage
# --------------------------------------------------------------------------


class TemplateRegressionTest(CliFixture):
    """Charakterisierung von ``agent_template`` und ``agent_render_task``.

    Diese Fälle sichern das in Punkt 4 des Arbeitspakets verlangte
    unveränderte Verhalten ab; sie sind am unveränderten Stand grün.
    """

    def test_agent_template_still_denies_subagents_by_default(self):
        """Neuanlage erzeugt weiterhin den Vorlagen-Standard ``subagent * deny``.

        Vorher: keine Datei. Aktion: ``agent_template`` für alle Vorlagen
        (global und Projekt mit Schreibverzeichnissen). Erwartet: Policy
        ``none`` und genau eine Subagenten-Regel ``* deny``.
        """
        for preset in ("voll", "lesen", "lesen_git"):
            with self.subTest(preset=preset):
                text = self.cli.agent_template("Neu", perm=preset)
                self.assertEqual(
                    self.cli.agent_task_policy(text), {"mode": "none", "allowed": []}
                )
                self.assertEqual(rule_pairs(text, "subagent"), [("*", "deny")])

        dirs = self.cli.write_dirs("proj")
        project_text = self.cli.agent_template(
            "Neu", perm="voll", write_dirs=dirs
        )
        self.assertEqual(
            self.cli.agent_task_policy(project_text),
            {"mode": "none", "allowed": []},
        )

    def test_agent_render_task_without_preset_keeps_v1_syntax(self):
        """v1-individueller Block behält ohne Vorlage die v1-task-Syntax.

        Vorher: v1-Datei mit individueller task-Map. Aktion:
        ``agent_render_task(..., ["x"])`` ohne Vorlage. Erwartet: weiterhin
        ``permission:``-Block mit ``task``-Einträgen (keine v2-Umstellung).
        """
        changed = self.cli.agent_render_task(
            "global", V1_TASK_CUSTOM_AGENT, ["x"]
        )

        self.assertTrue(has_top_level_key(changed, "permission"))
        self.assertIsNone(parse_permissions(changed))
        self.assertEqual(
            self.cli.agent_task_policy(changed),
            {"mode": "custom", "allowed": ["x"]},
        )
        self.cli.agent_validate(changed)

    def test_agent_render_task_without_preset_replaces_only_subagent_rules_in_v2(self):
        """v2-Block: Auswahl ohne Vorlage ersetzt nur die Subagenten-Regeln.

        Vorher: v2-Datei mit Subagenten-Regeln. Aktion: ``allow_all=True``
        ohne Vorlage. Erwartet: ``* allow``; alle anderen Regeln unverändert.
        """
        before = parse_permissions(V2_SUBAGENT_CUSTOM_AGENT)
        non_subagent_before = non_subagent_rules(V2_SUBAGENT_CUSTOM_AGENT)

        changed = self.cli.agent_render_task(
            "global", V2_SUBAGENT_CUSTOM_AGENT, [], allow_all=True
        )

        self.assertIsNotNone(before)
        self.assertEqual(rule_pairs(changed, "subagent"), [("*", "allow")])
        self.assertEqual(non_subagent_rules(changed), non_subagent_before)
        self.cli.agent_validate(changed)


# --------------------------------------------------------------------------
# 4. End-to-end über die Web-API mit der Payload-Sequenz der klassischen UI
# --------------------------------------------------------------------------

FAKE_OPENCODE = """#!/usr/bin/env bash
case "$1" in
  --version) printf 'opencode 2.1.4\\n' ;;
  models)
    printf 'opencode/test-modell\\nopencode/orchestrator-modell\\n'
    ;;
esac
exit 0
"""

HELPER_AGENT = v2_agent(
    [("read", "*", "allow"), ("subagent", "*", "deny")],
    description="Hilfsagent",
)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class AgentApiTest(unittest.TestCase):
    """``/api/agent`` (save/render) und ``/api/agent_template`` über HTTP.

    Der Server läuft als Subprozess mit isoliertem VIBE/HOME und einer
    opencode-Attrappe. Die Payloads der Speicher- und Vorschaufälle
    entsprechen der klassischen UI (``bin/web/app.js``): ``save`` sendet nur
    geänderte strukturierte Felder plus Prüfsumme, ``render`` sendet alle
    Formularwerte.
    """

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
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        (cls.agents / "helper.md").write_text(HELPER_AGENT, encoding="utf-8")
        fakebin = cls.root / "fakebin"
        fakebin.mkdir()
        fake = fakebin / "opencode"
        fake.write_text(FAKE_OPENCODE, encoding="utf-8")
        fake.chmod(0o755)
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
        deadline = time.time() + 25
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
        # Nur zum Auswerten von ``agent_task_policy``; der Server läuft separat.
        cls.cli = load_cli(cls.root, cls.home)
        cls.cli._AGENT_VERSION = None

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

    def request(self, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, path),
            data=data,
            method="POST" if data else "GET",
        )
        req.add_header("Host", "127.0.0.1:%d" % self.port)
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

    def write_agent(self, name, text):
        path = self.agents / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def load_agent(self, name):
        status, body = self.request(
            "/api/agent?scope=global&name=" + name
        )
        self.assertEqual(status, 200, body)
        return json.loads(body)

    def render(self, name, text, values):
        return self.request(
            "/api/agent",
            {
                "action": "render",
                "scope": "global",
                "name": name,
                "text": text,
                "values": values,
            },
        )

    def save(self, name, text, values, expected=None, **extra):
        payload = {
            "action": "save",
            "scope": "global",
            "name": name,
            "text": text,
            "create": False,
            "expected": expected,
            "values": values,
        }
        payload.update(extra)
        return self.request("/api/agent", payload)

    def test_save_with_preset_and_without_task_fields_keeps_v1_task_allow(self):
        """Gemeldeter Fall end-to-end: save ``voll`` ohne task-Felder.

        Vorher: globale v1-Datei ``orchestrator`` mit ``task: allow``.
        Aktion: klassische UI-Sequenz — GET (Prüfsumme), dann POST
        ``action=save`` mit ``values:{permission:'voll'}`` und ohne
        ``task_all``/``task_allowed``.
        Erwartet: HTTP 200, Datei im v2-Format, Subagenten weiterhin erlaubt.
        """
        name = "orchestrator"
        path = self.write_agent(name, V1_TASK_ALLOW_AGENT)
        digest = self.load_agent(name)["digest"]

        status, body = self.save(
            name, V1_TASK_ALLOW_AGENT, {"permission": "voll"}, expected=digest
        )

        self.assertEqual(status, 200, body)
        saved = path.read_text(encoding="utf-8")
        self.assertFalse(has_top_level_key(saved, "permission"), saved)
        self.assertEqual(
            self.cli.agent_task_policy(saved), {"mode": "all", "allowed": []}
        )
        self.assertIn(("*", "allow"), rule_pairs(saved, "subagent"))
        self.assertEqual(
            non_subagent_rules(saved), preset_non_subagent("voll")
        )
        self.assertIn("Bestehender Prompt.", saved)
        self.assertEqual(json.loads(body)["text"], saved)

    def test_render_with_full_ui_form_values_keeps_v1_task_allow(self):
        """„In Rohtext übernehmen“ (render) mit allen Formularwerten.

        Vorher: v1-Datei mit ``task: allow``. Aktion: POST ``action=render``
        mit derselben Werte-Menge wie ``app.js`` (Beschreibung, Modus,
        Modell, Temperatur, Schritte, Rechte-Vorlage ``voll``, Prompt).
        Erwartet: Vorschau enthält Subagenten-Freigabe; die Datei bleibt
        unverändert (render schreibt nie).
        """
        name = "orchestrator"
        path = self.write_agent(name, V1_TASK_ALLOW_AGENT)
        values = {
            "description": "Orchestrator mit erlaubten Subagenten",
            "mode": "primary",
            "model": "opencode/orchestrator-modell",
            "temperature": "",
            "steps": "",
            "permission": "voll",
            "prompt": "Bestehender Prompt.",
        }

        status, body = self.render(name, V1_TASK_ALLOW_AGENT, values)

        self.assertEqual(status, 200, body)
        preview = json.loads(body)["text"]
        self.assertEqual(
            self.cli.agent_task_policy(preview), {"mode": "all", "allowed": []}
        )
        self.assertIn(("*", "allow"), rule_pairs(preview, "subagent"))
        self.assertEqual(
            non_subagent_rules(preview), preset_non_subagent("voll")
        )
        self.assertEqual(path.read_text(encoding="utf-8"), V1_TASK_ALLOW_AGENT)

    def test_save_with_preset_keeps_v1_custom_task_map(self):
        """Save mit Vorlage ``lesen`` erhält die individuellen Freigaben.

        Vorher: v1-Datei mit ``task``-Map (deny + ``vibe-coder``/``tester``).
        Aktion: GET-Prüfsumme, POST save mit ``values:{permission:'lesen'}``.
        Erwartet: HTTP 200, deny-Grundregel plus sortierte Freigaben.
        """
        name = "orchestrator"
        path = self.write_agent(name, V1_TASK_CUSTOM_AGENT)
        digest = self.load_agent(name)["digest"]

        status, body = self.save(
            name, V1_TASK_CUSTOM_AGENT, {"permission": "lesen"}, expected=digest
        )

        self.assertEqual(status, 200, body)
        saved = path.read_text(encoding="utf-8")
        self.assertEqual(
            rule_pairs(saved, "subagent"),
            [("*", "deny"), ("tester", "allow"), ("vibe-coder", "allow")],
        )
        self.assertEqual(non_subagent_rules(saved), preset_non_subagent("lesen"))

    def test_save_with_preset_keeps_v2_subagent_rules(self):
        """Save mit Vorlage ``voll`` erhält vorhandene v2-Subagenten-Regeln.

        Vorher: v2-Datei mit deny + zwei Freigaben.
        Aktion: GET-Prüfsumme, POST save mit ``values:{permission:'voll'}``.
        Erwartet: Subagenten-Regeln unverändert; Nicht-subagent-Regeln der
        Vorlage ``voll``.
        """
        name = "orchestrator"
        path = self.write_agent(name, V2_SUBAGENT_CUSTOM_AGENT)
        digest = self.load_agent(name)["digest"]
        before = rule_pairs(V2_SUBAGENT_CUSTOM_AGENT, "subagent")

        status, body = self.save(
            name, V2_SUBAGENT_CUSTOM_AGENT, {"permission": "voll"}, expected=digest
        )

        self.assertEqual(status, 200, body)
        saved = path.read_text(encoding="utf-8")
        self.assertEqual(rule_pairs(saved, "subagent"), before)
        self.assertEqual(non_subagent_rules(saved), preset_non_subagent("voll"))

    def test_save_with_explicit_task_all_wins_over_preset(self):
        """Charakterisierung: ``task_all=true`` im selben Request gewinnt.

        Vorher: v1-Datei mit ``task: deny``. Aktion: save mit Vorlage
        ``lesen`` und ``task_all=true``. Erwartet: Subagenten erlaubt.
        """
        name = "orchestrator"
        path = self.write_agent(name, V1_TASK_DENY_AGENT)
        digest = self.load_agent(name)["digest"]

        status, body = self.save(
            name,
            V1_TASK_DENY_AGENT,
            {"permission": "lesen"},
            expected=digest,
            task_all=True,
        )

        self.assertEqual(status, 200, body)
        saved = path.read_text(encoding="utf-8")
        self.assertEqual(
            self.cli.agent_task_policy(saved), {"mode": "all", "allowed": []}
        )
        self.assertIn(("*", "allow"), rule_pairs(saved, "subagent"))

    def test_save_with_explicit_allowed_list_wins_over_preset(self):
        """Charakterisierung: ``task_allowed`` im selben Request gewinnt.

        Vorher: v1-Datei mit ``task: allow``; global existiert der
        Subagent ``helper``. Aktion: save mit Vorlage ``voll`` und
        ``task_allowed: ["helper"]``. Erwartet: Policy ``custom`` mit
        ``helper`` — nicht die geerbte „alle“-Freigabe.
        """
        name = "orchestrator"
        path = self.write_agent(name, V1_TASK_ALLOW_AGENT)
        digest = self.load_agent(name)["digest"]

        status, body = self.save(
            name,
            V1_TASK_ALLOW_AGENT,
            {"permission": "voll"},
            expected=digest,
            task_allowed=["helper"],
        )

        self.assertEqual(status, 200, body)
        saved = path.read_text(encoding="utf-8")
        self.assertEqual(
            rule_pairs(saved, "subagent"),
            [("*", "deny"), ("helper", "allow")],
        )

    def test_template_api_still_denies_subagents(self):
        """Charakterisierung: ``/api/agent_template`` erzeugt die Vorlagen-Sperre.

        Vorher: keine Datei. Aktion: POST ``/api/agent_template`` mit
        ``perm:'voll'``. Erwartet: erzeugter Text sperrt Subagenten
        (``* deny``) — Neuanlage bleibt unverändert.
        """
        status, body = self.request(
            "/api/agent_template",
            {"scope": "global", "description": "API-Agent", "perm": "voll"},
        )

        self.assertEqual(status, 200, body)
        text = json.loads(body)["message"]
        self.assertEqual(rule_pairs(text, "subagent"), [("*", "deny")])


if __name__ == "__main__":
    unittest.main()
