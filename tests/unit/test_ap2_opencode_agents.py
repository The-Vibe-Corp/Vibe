"""Unabhängige Abnahme AP2-Korbat.

Auftrag (TICKETS.md, AP2-Korbat): Agenten-Markdowns müssen die
opencode-v2-Berechtigungssyntax erzeugen (``permissions``-Regelliste,
``shell`` statt ``bash``, ``subagent`` statt ``task``), die opencode-eigenen
Subagenten ``general`` und ``explore`` müssen in der Projekt-Agentenauswahl
umschaltbar und mit einem eigenen Modell versehen werden können.

Die Fälle sind aus dem Arbeitspaket und der angegebenen Soll-Beschreibung
abgeleitet, nicht aus einem Implementierungsdiff. Sie arbeiten ausschließlich
in temporären VIBE-/HOME-Verzeichnissen. Es gibt keine Modellaufrufe, keinen
Anbieternetzugriff und keine Berührung produktiver Konfiguration.

Gruppierung:

* ``A*`` — v2-Berechtigungssyntax in erzeugten Agentendateien.
* ``B*`` — opencode-native Agenten ``general``/``explore`` in
  Projektkonfiguration, CLI, API und Läufer.
* ``Runner*`` — Übergabe an ``OPENCODE_CONFIG_CONTENT`` über die
  opencode-Attrappe (kein Modellaufruf).
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
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"
WEB = BIN / "vibe-web.py"
RUNNER = BIN / "vibe-run.sh"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support  # noqa: E402

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
            "vibe_ap2_under_test", str(CLI)
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
# Parser-Helfer: unabhängig von der genauen Zeilenformatierung der Vorlagen.
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

    Akzeptiert sowohl einen vollständigen Agententext (``---``-Frontmatter)
    als auch einen losen Block. Die Reihenfolge der Regeln bleibt erhalten.
    Gibt ``None`` zurück, wenn kein v2-Block vorhanden ist.
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


def block_rules(block, action=None):
    """Regeln eines ``permission_block``-Ergebnisses (mit oder ohne Kopfzeile)."""
    if isinstance(block, (list, tuple)):
        block = "\n".join(block)
    if not re.search(r"^permissions:[ \t]*$", block, re.M):
        block = "permissions:\n" + block
    rules = parse_permissions(block)
    if rules is None:
        raise AssertionError("Kein v2-permissions-Block:\n" + block)
    if action is None:
        return rules
    return [rule for rule in rules if rule.get("action") == action]


def pair_list(rules):
    return [(rule.get("resource"), rule.get("effect")) for rule in rules]


def rule_map(rules):
    """action -> (resource, effect) für Aktionen mit genau einer Regel."""
    out = {}
    for rule in rules:
        action = rule.get("action")
        if action in out:
            raise AssertionError("Aktion mehrfach vorhanden: " + str(action))
        out[action] = (rule.get("resource"), rule.get("effect"))
    return out


def has_top_level_key(text, key):
    return any(
        re.match(r"^" + re.escape(key) + r":[ \t]*(.*)$", line)
        for line in frontmatter_lines(text)
    )


def assert_no_v1_keys(testcase, text):
    """In neu erzeugten Blöcken darf keine v1-Syntax stehen."""
    testcase.assertFalse(has_top_level_key(text, "permission"),
                         "v1-Schlüssel 'permission:' wurde erzeugt")
    testcase.assertIsNotNone(parse_permissions(text),
                             "v2-Schlüssel 'permissions:' fehlt")
    for line in frontmatter_lines(text):
        testcase.assertFalse(
            re.match(r"^[ \t]+(bash|task|list):", line),
            "v1-Schlüssel in neuem Block: " + line)


def agent_text(extra_frontmatter, prompt="Prompt."):
    return "---\n" + extra_frontmatter.strip("\n") + "\n---\n\n" + prompt + "\n"


V1_LESEN_PERMISSION = """permission:
  read: allow
  glob: allow
  grep: allow
  list: allow
  edit: deny
  bash: deny
  task: deny
  webfetch: deny
  websearch: deny"""

V1_LESEN_AGENT = (
    "---\ndescription: Alt-Lesen\nmode: subagent\n" + V1_LESEN_PERMISSION
    + "\n---\n\nAlt-Prompt.\n"
)

V1_FULL_PERMISSION = """permission:
  read: allow
  glob: allow
  grep: allow
  list: allow
  edit: allow
  bash: allow
  webfetch: deny
  websearch: deny"""

V1_CUSTOM_AGENT = """---
description: Alt mit individuellem Block
mode: subagent
color: blau
permission:
  read: allow
  edit: deny
  task: deny
---

Individueller Prompt.
"""


def v2_agent(rules, description="Agent", mode="subagent", model="opencode/test-modell"):
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


LESEN_RULES = [
    ("read", "*", "allow"),
    ("glob", "*", "allow"),
    ("grep", "*", "allow"),
    ("edit", "*", "deny"),
    ("shell", "*", "deny"),
    ("subagent", "*", "deny"),
    ("webfetch", "*", "deny"),
    ("websearch", "*", "deny"),
]

VOLL_RULES = [
    ("read", "*", "allow"),
    ("glob", "*", "allow"),
    ("grep", "*", "allow"),
    ("edit", "*", "allow"),
    ("shell", "*", "allow"),
    ("subagent", "*", "deny"),
    ("webfetch", "*", "deny"),
    ("websearch", "*", "deny"),
]


class CliFixture(unittest.TestCase):
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
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8"
        )
        return project

    def write_global(self, name, text):
        self.agents.mkdir(parents=True, exist_ok=True)
        path = self.agents / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def write_project_agent(self, project, name, text):
        folder = project / ".opencode" / "agents"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return path

    def config_path(self, project):
        return project / ".vibe" / "agents.json"

    def write_config(self, project, data):
        path = self.config_path(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
        return path


# --------------------------------------------------------------------------
# A1: permission_block erzeugt v2-Regeln
# --------------------------------------------------------------------------

class A1PermissionBlockTest(CliFixture):
    def test_voll_block_uses_v2_rules(self):
        block = self.cli.permission_block("voll")
        if isinstance(block, (list, tuple)):
            block = "\n".join(block)
        rules = block_rules(block)

        self.assertEqual(
            rule_map(rules),
            {
                "read": ("*", "allow"),
                "glob": ("*", "allow"),
                "grep": ("*", "allow"),
                "edit": ("*", "allow"),
                "shell": ("*", "allow"),
                "subagent": ("*", "deny"),
                "webfetch": ("*", "deny"),
                "websearch": ("*", "deny"),
            },
        )
        self.assertNotRegex(block, r"(?m)^[ \t]*(bash|task|list):")

    def test_lesen_block_denies_write_shell_and_subagents(self):
        rules = block_rules(self.cli.permission_block("lesen"))

        self.assertEqual(
            rule_map(rules),
            {
                "read": ("*", "allow"),
                "glob": ("*", "allow"),
                "grep": ("*", "allow"),
                "edit": ("*", "deny"),
                "shell": ("*", "deny"),
                "subagent": ("*", "deny"),
                "webfetch": ("*", "deny"),
                "websearch": ("*", "deny"),
            },
        )

    def test_lesen_git_block_orders_shell_rules_correctly(self):
        rules = block_rules(self.cli.permission_block("lesen_git"))

        self.assertEqual(
            pair_list([rule for rule in rules if rule.get("action") == "shell"]),
            [
                ("*", "deny"),
                ("git status --short", "allow"),
                ("git diff *", "allow"),
                ("git show *", "allow"),
                ("git log *", "allow"),
            ],
        )
        mapped = rule_map([rule for rule in rules if rule.get("action") != "shell"])
        self.assertEqual(mapped["edit"], ("*", "deny"))
        self.assertEqual(mapped["subagent"], ("*", "deny"))
        self.assertEqual(mapped["webfetch"], ("*", "deny"))
        self.assertEqual(mapped["websearch"], ("*", "deny"))

    def test_project_full_block_denies_first_then_allows_each_write_dir(self):
        dirs = ["/tmp/opencode", "/tmp/opencode/projekt"]
        block = self.cli.permission_block("voll", write_dirs=dirs)
        edit = block_rules(block, "edit")

        self.assertEqual(
            pair_list(edit),
            [
                ("*", "deny"),
                ("/tmp/opencode", "allow"),
                ("/tmp/opencode/**", "allow"),
                ("/tmp/opencode/projekt", "allow"),
                ("/tmp/opencode/projekt/**", "allow"),
            ],
        )

    def test_empty_write_dir_list_denies_edits(self):
        block = self.cli.permission_block("voll", write_dirs=[])
        self.assertEqual(pair_list(block_rules(block, "edit")), [("*", "deny")])

    def test_edit_permission_lines_use_v2_list_items(self):
        lines = self.cli.edit_permission_lines(["/tmp/opencode"])
        rules = block_rules("\n".join(lines), "edit")
        self.assertEqual(
            pair_list(rules),
            [
                ("*", "deny"),
                ("/tmp/opencode", "allow"),
                ("/tmp/opencode/**", "allow"),
            ],
        )


# --------------------------------------------------------------------------
# A2: agent_template erzeugt v2-Frontmatter
# --------------------------------------------------------------------------

class A2TemplateTest(CliFixture):
    def test_template_frontmatter_is_v2_and_validates(self):
        for preset in ("lesen", "voll", "lesen_git"):
            with self.subTest(preset=preset):
                text = self.cli.agent_template("Testagent", perm=preset)
                assert_no_v1_keys(self, text)
                self.cli.agent_validate(text)

    def test_project_template_with_write_dirs_uses_v2_edit_rules(self):
        dirs = self.cli.write_dirs("proj")
        text = self.cli.agent_template(
            "Projektagent", perm="voll", write_dirs=dirs
        )

        assert_no_v1_keys(self, text)
        edit = block_rules(text, "edit")
        self.assertEqual(edit[0].get("resource"), "*")
        self.assertEqual(edit[0].get("effect"), "deny")
        resources = [rule["resource"] for rule in edit]
        for directory in dirs:
            self.assertIn(directory, resources)
            self.assertIn(directory + "/**", resources)
        self.cli.agent_validate(text)


# --------------------------------------------------------------------------
# A3: strukturierter Editor erkennt v2-Vorlagen
# --------------------------------------------------------------------------

class A3FieldsTest(CliFixture):
    def test_fields_recognise_global_v2_presets(self):
        for preset in ("lesen", "voll", "lesen_git"):
            with self.subTest(preset=preset):
                text = self.cli.agent_template("Agent", perm=preset)
                fields = self.cli.agent_fields("global", text)
                self.assertEqual(fields["permission"], preset)
                self.assertFalse(fields["permission_custom"])
                self.assertNotIn("permissions", fields["unknown"])

    def test_fields_recognise_project_v2_preset_with_write_dirs(self):
        dirs = self.cli.write_dirs("proj")
        text = self.cli.agent_template("Agent", perm="voll", write_dirs=dirs)

        fields = self.cli.agent_fields("proj", text)

        self.assertEqual(fields["permission"], "voll")
        self.assertFalse(fields["permission_custom"])

    def test_v1_block_is_custom_but_file_stays_readable_and_editable(self):
        fields = self.cli.agent_fields("global", V1_CUSTOM_AGENT)

        self.assertEqual(fields["permission"], "")
        self.assertTrue(fields["permission_custom"])
        self.assertNotIn("permission", fields["unknown"])
        changed = self.cli.agent_render_fields(
            "global", V1_CUSTOM_AGENT, {"description": "Neu"}
        )
        self.assertIn("description: Neu", changed)
        self.assertTrue(has_top_level_key(changed, "permission"),
                        "Der individuelle v1-Block wurde ohne Auftrag verändert")
        self.cli.agent_validate(changed)


# --------------------------------------------------------------------------
# A4: agent_render_fields ersetzt v1/v2 durch v2
# --------------------------------------------------------------------------

class A4RenderFieldsTest(CliFixture):
    def test_render_replaces_a_v1_block_with_v2_and_keeps_unknown_fields(self):
        text = (
            "---\n"
            "description: Alt\n"
            "mode: subagent\n"
            "color: blau\n"
            "tools:\n"
            "  write: true\n"
            "permission:\n"
            "  read: allow\n"
            "  edit: deny\n"
            "  task: deny\n"
            "---\n"
            "\n"
            "Alter Prompt.\n"
        )

        changed = self.cli.agent_render_fields("global", text, {"permission": "lesen"})

        assert_no_v1_keys(self, changed)
        self.assertIn("color: blau", changed)
        self.assertIn("tools:\n  write: true", changed)
        self.assertIn("Alter Prompt.", changed)
        self.assertEqual(pair_list(block_rules(changed, "read")), [("*", "allow")])
        self.assertEqual(pair_list(block_rules(changed, "edit")), [("*", "deny")])
        self.cli.agent_validate(changed)

    def test_render_replaces_a_v2_block(self):
        text = self.cli.agent_template("Agent", perm="voll")

        changed = self.cli.agent_render_fields(
            "global", text, {"permission": "lesen"}
        )

        assert_no_v1_keys(self, changed)
        self.assertEqual(pair_list(block_rules(changed, "edit")), [("*", "deny")])
        self.assertEqual(pair_list(block_rules(changed, "shell")), [("*", "deny")])
        self.cli.agent_validate(changed)

    def test_unknown_permission_preset_is_rejected(self):
        with self.assertRaises(ValueError):
            self.cli.agent_render_fields(
                "global", self.cli.agent_template("Agent"), {"permission": "root"}
            )


# --------------------------------------------------------------------------
# A5: agent_task_policy liest v2-Subagenten-Regeln, v1-Fallback bleibt
# --------------------------------------------------------------------------

class A5TaskPolicyTest(CliFixture):
    def policy(self, rules):
        return self.cli.agent_task_policy(v2_agent(rules))

    def test_star_allow_means_all(self):
        self.assertEqual(
            self.policy([("subagent", "*", "allow")]),
            {"mode": "all", "allowed": []},
        )

    def test_star_deny_means_none(self):
        self.assertEqual(
            self.policy([("subagent", "*", "deny")]),
            {"mode": "none", "allowed": []},
        )

    def test_deny_star_plus_named_allows_is_sorted_custom(self):
        self.assertEqual(
            self.policy(
                [
                    ("subagent", "*", "deny"),
                    ("subagent", "b", "allow"),
                    ("subagent", "a", "allow"),
                ]
            ),
            {"mode": "custom", "allowed": ["a", "b"]},
        )

    def test_later_rules_win(self):
        self.assertEqual(
            self.policy(
                [("subagent", "*", "deny"), ("subagent", "*", "allow")]
            )["mode"],
            "all",
        )
        self.assertEqual(
            self.policy(
                [("subagent", "*", "allow"), ("subagent", "*", "deny")]
            )["mode"],
            "none",
        )
        self.assertEqual(
            self.policy(
                [
                    ("subagent", "a", "allow"),
                    ("subagent", "*", "deny"),
                ]
            )["mode"],
            "none",
        )

    def test_v1_permission_task_fallback_still_works(self):
        self.assertEqual(
            self.cli.agent_task_policy(V1_LESEN_AGENT),
            {"mode": "none", "allowed": []},
        )
        custom = agent_text(
            "description: Alt\nmode: subagent\n"
            "permission:\n  read: allow\n  edit: deny\n"
            "  task:\n    \"*\": deny\n    b: allow\n    a: allow"
        )
        self.assertEqual(
            self.cli.agent_task_policy(custom),
            {"mode": "custom", "allowed": ["a", "b"]},
        )
        allow = agent_text(
            "description: Alt\nmode: subagent\n"
            "permission:\n  read: allow\n  task: allow"
        )
        self.assertEqual(
            self.cli.agent_task_policy(allow), {"mode": "all", "allowed": []}
        )

    def test_generated_template_denies_subagents_by_default(self):
        for preset in ("lesen", "voll", "lesen_git"):
            with self.subTest(preset=preset):
                text = self.cli.agent_template("Agent", perm=preset)
                self.assertEqual(
                    self.cli.agent_task_policy(text),
                    {"mode": "none", "allowed": []},
                )


# --------------------------------------------------------------------------
# A6: agent_render_task schreibt v2-Subagenten-Regeln
# --------------------------------------------------------------------------

class A6RenderTaskTest(CliFixture):
    def test_allow_all_replaces_only_subagent_rules(self):
        text = self.cli.agent_template("Agent", perm="voll")
        before = parse_permissions(text)

        changed = self.cli.agent_render_task("global", text, [], allow_all=True)

        after = parse_permissions(changed) or []
        self.assertEqual(
            pair_list([rule for rule in after if rule.get("action") == "subagent"]),
            [("*", "allow")],
        )
        self.assertEqual(
            [rule for rule in before if rule.get("action") != "subagent"],
            [rule for rule in after if rule.get("action") != "subagent"],
        )
        self.cli.agent_validate(changed)

    def test_no_allowed_agents_writes_subagent_deny(self):
        text = self.cli.agent_template("Agent")

        changed = self.cli.agent_render_task("global", text, [])

        self.assertEqual(
            pair_list(block_rules(changed, "subagent")), [("*", "deny")]
        )
        self.cli.agent_validate(changed)

    def test_custom_agents_write_deny_star_and_sorted_allows(self):
        text = self.cli.agent_template("Agent")

        changed = self.cli.agent_render_task("global", text, ["b", "a"])

        self.assertEqual(
            pair_list(block_rules(changed, "subagent")),
            [("*", "deny"), ("a", "allow"), ("b", "allow")],
        )
        self.cli.agent_validate(changed)

    def test_matching_v1_template_block_is_migrated_completely(self):
        changed = self.cli.agent_render_task(
            "global", V1_LESEN_AGENT, ["x"]
        )

        assert_no_v1_keys(self, changed)
        self.assertIn("Alt-Prompt.", changed)
        self.assertEqual(pair_list(block_rules(changed, "read")), [("*", "allow")])
        self.assertEqual(pair_list(block_rules(changed, "edit")), [("*", "deny")])
        self.assertEqual(pair_list(block_rules(changed, "shell")), [("*", "deny")])
        self.assertEqual(
            pair_list(block_rules(changed, "subagent")),
            [("*", "deny"), ("x", "allow")],
        )
        self.cli.agent_validate(changed)

    def test_individual_v1_block_keeps_v1_task_syntax(self):
        changed = self.cli.agent_render_task("global", V1_CUSTOM_AGENT, ["x"])

        self.assertTrue(has_top_level_key(changed, "permission"))
        self.assertIsNone(parse_permissions(changed))
        self.assertIn("task:", changed)
        self.assertNotIn("subagent:", changed)
        self.assertEqual(
            self.cli.agent_task_policy(changed),
            {"mode": "custom", "allowed": ["x"]},
        )
        self.cli.agent_validate(changed)


# --------------------------------------------------------------------------
# A7: Schreibverzeichnisse mit v2-Blöcken
# --------------------------------------------------------------------------

class A7WriteDirsTest(CliFixture):
    def test_v2_full_grants_write_and_v2_readonly_does_not(self):
        self.assertTrue(
            self.cli._edit_grants_write(self.cli.agent_template("A", perm="voll"))
        )
        self.assertFalse(
            self.cli._edit_grants_write(self.cli.agent_template("A", perm="lesen"))
        )

    def test_rewrite_edit_block_changes_only_edit_rules(self):
        text = self.cli.agent_template(
            "A", perm="voll", write_dirs=["/tmp/opencode"]
        )
        before = parse_permissions(text) or []

        changed = self.cli._rewrite_edit_block(text, ["/tmp/zweites"])

        after = parse_permissions(changed) or []
        self.assertEqual(
            [rule for rule in before if rule.get("action") != "edit"],
            [rule for rule in after if rule.get("action") != "edit"],
        )
        self.assertEqual(
            pair_list([rule for rule in after if rule.get("action") == "edit"]),
            [
                ("*", "deny"),
                ("/tmp/zweites", "allow"),
                ("/tmp/zweites/**", "allow"),
            ],
        )
        self.cli.agent_validate(changed)

    def test_apply_write_dirs_rewrites_a_v2_project_agent(self):
        dirs = ["/tmp/opencode", str(self.project)]
        text = self.cli.agent_template("A", perm="voll", write_dirs=dirs)
        path = self.write_project_agent(self.project, "schreiber", text)
        before = parse_permissions(text) or []

        changed = self.cli.apply_write_dirs(
            "proj", "schreiber", ["/tmp/neu"]
        )

        self.assertEqual(changed, path.read_text(encoding="utf-8"))
        after = parse_permissions(changed) or []
        self.assertEqual(
            [rule for rule in before if rule.get("action") != "edit"],
            [rule for rule in after if rule.get("action") != "edit"],
        )
        self.assertEqual(
            pair_list([rule for rule in after if rule.get("action") == "edit"]),
            [("*", "deny"), ("/tmp/neu", "allow"), ("/tmp/neu/**", "allow")],
        )
        backups = list(
            (self.root / "_toolchain" / "agent-backups" / "proj").glob("*.md")
        )
        self.assertEqual(len(backups), 1)

    def test_apply_write_dirs_to_project_skips_read_only_v2_agents(self):
        writable = self.write_project_agent(
            self.project,
            "schreiber",
            self.cli.agent_template("A", perm="voll", write_dirs=["/tmp/opencode"]),
        )
        readonly = self.write_project_agent(
            self.project,
            "leser",
            self.cli.agent_template("B", perm="lesen"),
        )
        # Ohne eigene permissions.json gelten die Standardverzeichnisse; die
        # Erwartung "/tmp/neu" setzt daher eine ausdrückliche Projektliste voraus.
        self.cli.write_dirs_save("proj", ["/tmp/neu"])

        changed = self.cli.apply_write_dirs_to_project("proj")

        self.assertEqual(changed, ["schreiber"])
        self.assertIn("/tmp/neu", writable.read_text(encoding="utf-8"))
        self.assertEqual(
            readonly.read_text(encoding="utf-8"),
            self.cli.agent_template("B", perm="lesen"),
        )

    def test_v1_blocks_stay_functional(self):
        self.assertTrue(self.cli._edit_grants_write(V1_LESEN_AGENT) is False)
        full = agent_text(
            "description: Alt\nmode: subagent\n" + V1_FULL_PERMISSION
        )
        self.assertTrue(self.cli._edit_grants_write(full))
        changed = self.cli._rewrite_edit_block(full, ["/tmp/opencode"])
        self.assertIn("/tmp/opencode", changed)
        self.cli.agent_validate(changed)


# --------------------------------------------------------------------------
# A8: Hierarchie-Prüfung mit v2-Blöcken
# --------------------------------------------------------------------------

class A8HierarchyTest(CliFixture):
    def test_v2_hierarchy_unknown_and_cycle_rules_unchanged(self):
        self.write_global(
            "a", v2_agent(LESEN_RULES + [("subagent", "b", "allow")])
        )
        self.write_global(
            "b", v2_agent(LESEN_RULES + [("subagent", "a", "allow")])
        )

        with self.assertRaises(ValueError):
            self.cli.agent_validate_hierarchy("a", ["unbekannt"])
        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy("a", ["b"])
        self.assertIn("Zyklus", str(caught.exception))

        self.write_global("b", v2_agent(LESEN_RULES))
        self.assertEqual(self.cli.agent_validate_hierarchy("a", ["b"]), ["b"])

    def test_v2_self_call_allowed_for_subagent_but_not_for_vibe_agent(self):
        self.write_global(
            "a", v2_agent(LESEN_RULES + [("subagent", "a", "allow")])
        )

        self.assertEqual(self.cli.agent_validate_hierarchy("a", ["a"]), ["a"])

        data = self.cli.profiles_load()
        data["rollen"] = {"a": "vibe"}
        self.cli.profiles_save(data)

        with self.assertRaises(ValueError):
            self.cli.agent_validate_hierarchy("a", ["a"])

    def test_primary_agents_stay_unavailable_as_subagents(self):
        self.write_global("a", v2_agent(LESEN_RULES))
        self.write_global("p", v2_agent(LESEN_RULES, mode="primary"))

        with self.assertRaises(ValueError) as caught:
            self.cli.agent_validate_hierarchy("a", ["p"])
        self.assertIn("kein Subagent", str(caught.exception))


# --------------------------------------------------------------------------
# A9: mitgelieferte opencode.json nutzt v2
# --------------------------------------------------------------------------

class A9ShippedConfigTest(unittest.TestCase):
    def test_templates_common_opencode_json_uses_v2_permissions(self):
        path = REPO / "templates" / "common" / "opencode.json"
        data = json.loads(path.read_text(encoding="utf-8"))

        self.assertNotIn("permission", data,
                         "Der v1-Schlüssel 'permission' ist noch vorhanden")
        self.assertIn("permissions", data)
        self.assertIsInstance(data["permissions"], list)
        actions = [rule.get("action") for rule in data["permissions"]]
        self.assertIn("shell", actions)
        self.assertNotIn("bash", json.dumps(data),
                         "Der v1-Schlüssel 'bash' ist noch vorhanden")
        for rule in data["permissions"]:
            self.assertEqual(set(rule), {"action", "resource", "effect"})


# --------------------------------------------------------------------------
# B1: Version 3 der Projekt-Agentenauswahl
# --------------------------------------------------------------------------

class B1ProjectConfigTest(CliFixture):
    def load(self, project="proj"):
        return self.cli.project_agents_load(project)[0]

    def test_missing_file_defaults_to_version_3_with_both_opencode_agents(self):
        config = self.load()

        self.assertEqual(config["version"], 3)
        self.assertEqual(set(config["opencode"]), {"general", "explore"})
        for name in ("general", "explore"):
            self.assertIs(config["opencode"][name]["aktiv"], True)
            self.assertEqual(config["opencode"][name]["modell"], "")
        self.assertNotIn("general", config["aktiv"])
        self.assertNotIn("explore", config["aktiv"])

    def test_version_2_is_migrated_with_opencode_defaults(self):
        self.write_config(
            self.project,
            {"version": 2, "aktiv": ["tester"], "modelle": {}},
        )

        config = self.load()

        self.assertEqual(config["version"], 3)
        self.assertEqual(config["aktiv"], ["tester"])
        self.assertEqual(config["opencode"]["general"]["aktiv"], True)
        self.assertEqual(config["opencode"]["explore"]["modell"], "")

    def test_valid_version_3_roundtrip(self):
        self.write_config(
            self.project,
            {
                "version": 3,
                "aktiv": ["tester"],
                "modelle": {"tester": "opencode/tester-modell"},
                "opencode": {
                    "general": {"aktiv": False, "modell": "free/general"},
                    "explore": {"aktiv": True, "modell": ""},
                },
            },
        )

        config = self.load()

        self.assertEqual(config["version"], 3)
        self.assertEqual(config["opencode"]["general"]["aktiv"], False)
        self.assertEqual(config["opencode"]["general"]["modell"], "free/general")
        self.assertEqual(config["opencode"]["explore"]["aktiv"], True)

    def test_unknown_opencode_agent_name_is_rejected(self):
        self.write_config(
            self.project,
            {"version": 3, "aktiv": [], "modelle": {},
             "opencode": {"build": {"aktiv": True, "modell": ""}}},
        )
        with self.assertRaises(ValueError) as caught:
            self.load()
        self.assertIn("build", str(caught.exception))

    def test_unknown_opencode_entry_field_is_rejected(self):
        self.write_config(
            self.project,
            {"version": 3, "aktiv": [], "modelle": {},
             "opencode": {"general": {"aktiv": True, "farbe": "rot"}}},
        )
        with self.assertRaises(ValueError) as caught:
            self.load()
        self.assertIn("farbe", str(caught.exception))

    def test_aktiv_must_be_a_json_boolean(self):
        self.write_config(
            self.project,
            {"version": 3, "aktiv": [], "modelle": {},
             "opencode": {"general": {"aktiv": "ja", "modell": ""}}},
        )
        with self.assertRaises(ValueError):
            self.load()

    def test_modell_must_be_a_string_and_a_valid_model_pattern(self):
        for value in (5, "kein modell mit leerzeichen"):
            with self.subTest(value=value):
                self.write_config(
                    self.project,
                    {"version": 3, "aktiv": [], "modelle": {},
                     "opencode": {"explore": {"aktiv": True, "modell": value}}},
                )
                with self.assertRaises(ValueError):
                    self.load()

    def test_start_agent_list_rejects_opencode_agents(self):
        for name in ("general", "explore"):
            with self.subTest(name=name):
                self.write_config(
                    self.project,
                    {"version": 3, "aktiv": [name], "modelle": {}},
                )
                with self.assertRaises(ValueError):
                    self.load()

    def test_unknown_top_level_field_is_rejected(self):
        self.write_config(
            self.project,
            {"version": 3, "aktiv": [], "modelle": {}, "farbe": "rot"},
        )
        with self.assertRaises(ValueError) as caught:
            self.load()
        self.assertIn("farbe", str(caught.exception))


# --------------------------------------------------------------------------
# B2: project_agent_rows zeigt opencode-Zeilen
# --------------------------------------------------------------------------

class B2RowsTest(CliFixture):
    def write_global_agents(self):
        self.write_global(
            "vibe-agent",
            v2_agent(LESEN_RULES, mode="primary", model="opencode/vibe-modell"),
        )
        self.write_global(
            "tester", v2_agent(LESEN_RULES, model="opencode/tester-modell")
        )
        data = self.cli.profiles_load()
        data["rollen"] = {"vibe-agent": "vibe"}
        self.cli.profiles_save(data)

    def rows(self):
        return {row["name"]: row for row in self.cli.project_agent_rows("proj")}

    def test_rows_include_general_and_explore_with_marker(self):
        self.write_global_agents()

        rows = self.rows()

        for name in ("general", "explore"):
            self.assertIn(name, rows)
            self.assertIs(rows[name].get("opencode"), True)
        self.assertFalse(rows["tester"].get("opencode", False))

    def test_opencode_rows_reflect_toggle_and_effective_model(self):
        self.write_global_agents()
        self.write_config(
            self.project,
            {
                "version": 3,
                "aktiv": ["vibe-agent"],
                "modelle": {},
                "opencode": {
                    "general": {"aktiv": False, "modell": "free/general"},
                    "explore": {"aktiv": True, "modell": ""},
                },
            },
        )

        rows = self.rows()

        self.assertFalse(rows["general"]["configured"])
        self.assertFalse(rows["general"]["selected"])
        self.assertEqual(rows["general"]["effective_model"], "free/general")
        self.assertTrue(rows["explore"]["configured"])
        self.assertEqual(rows["explore"]["effective_model"], "")

    def test_opencode_rows_are_not_file_agents(self):
        self.write_global_agents()

        inventory = self.cli.project_agent_inventory("proj")
        self.assertNotIn("general", inventory)
        self.assertNotIn("explore", inventory)
        with self.assertRaises(ValueError):
            self.cli.agent_read("global", "general")
        with self.assertRaises(ValueError):
            self.cli.agent_read("global", "explore")


# --------------------------------------------------------------------------
# B3: project_agent_set ändert nur den opencode-Abschnitt
# --------------------------------------------------------------------------

class B3SetTest(CliFixture):
    def write_global_agents(self):
        self.write_global(
            "vibe-agent",
            v2_agent(LESEN_RULES, mode="primary", model="opencode/vibe-modell"),
        )
        self.write_global(
            "tester", v2_agent(LESEN_RULES, model="opencode/tester-modell")
        )
        data = self.cli.profiles_load()
        data["rollen"] = {"vibe-agent": "vibe"}
        self.cli.profiles_save(data)

    def test_toggle_changes_only_the_opencode_section(self):
        self.write_global_agents()
        tester_before = (self.agents / "tester.md").read_bytes()

        self.cli.project_agent_set("proj", "general", selected=False)

        stored = json.loads(self.config_path(self.project).read_text(encoding="utf-8"))
        self.assertEqual(stored["version"], 3)
        self.assertIs(stored["opencode"]["general"]["aktiv"], False)
        self.assertNotIn("general", stored["aktiv"])
        self.assertEqual((self.agents / "tester.md").read_bytes(), tester_before)
        self.assertFalse(self.config_path(self.other).exists())

    def test_model_is_stored_and_can_be_cleared_without_changing_aktiv(self):
        self.write_global_agents()
        self.cli.project_agent_set("proj", "explore", selected=False)

        self.cli.project_agent_set("proj", "explore", model="free/explore")
        stored = json.loads(self.config_path(self.project).read_text(encoding="utf-8"))
        self.assertEqual(stored["opencode"]["explore"]["modell"], "free/explore")
        self.assertIs(stored["opencode"]["explore"]["aktiv"], False)

        self.cli.project_agent_set("proj", "explore", model="")
        stored = json.loads(self.config_path(self.project).read_text(encoding="utf-8"))
        self.assertEqual(stored["opencode"]["explore"].get("modell", ""), "")
        self.assertIs(stored["opencode"]["explore"]["aktiv"], False)

    def test_invalid_values_are_rejected_without_writing(self):
        self.write_global_agents()
        cases = [
            ("general", {"selected": "nein"}),
            ("general", {"model": "kein modell mit leerzeichen"}),
            ("general", {"model": 5}),
        ]
        for agent, kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    self.cli.project_agent_set("proj", agent, **kwargs)
                self.assertFalse(self.config_path(self.project).exists())

    def test_unknown_opencode_agent_is_rejected(self):
        self.write_global_agents()
        with self.assertRaises(ValueError):
            self.cli.project_agent_set("proj", "build", selected=False)
        self.assertFalse(self.config_path(self.project).exists())

    def test_concurrent_change_is_refused(self):
        self.write_global_agents()
        path = self.write_config(
            self.project,
            {"version": 3, "aktiv": ["vibe-agent"], "modelle": {}},
        )
        snapshot = self.cli.vibe_storage.read_snapshot(path)
        path.write_text(
            json.dumps({"version": 3, "aktiv": [], "modelle": {}}),
            encoding="utf-8",
        )

        with self.assertRaises(self.cli.vibe_storage.ConcurrentChangeError):
            self.cli.project_agents_save(
                "proj",
                {"version": 3, "aktiv": ["vibe-agent"], "modelle": {}},
                expected=snapshot.digest,
            )


# --------------------------------------------------------------------------
# B4/A2-API: HTTP-Endpunkte
# --------------------------------------------------------------------------

FAKE_OPENCODE = """#!/usr/bin/env bash
case "$1" in
  --version) printf 'opencode 2.3.0\\n' ;;
  models)
    printf 'opencode/start\\nopencode/free-modell\\nopencode/vibe-modell\\n'
    ;;
esac
exit 0
"""


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class WebApiTest(unittest.TestCase):
    """GET/POST /api/project-agents und POST /api/agent_template."""

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
        (cls.agents / "vibe-agent.md").write_text(
            v2_agent(LESEN_RULES, mode="primary", model="opencode/vibe-modell"),
            encoding="utf-8",
        )
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
        path = self.project / ".vibe" / "agents.json"
        path.unlink(missing_ok=True)

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

    def agent_rows(self):
        status, body = self.request("/api/project-agents?name=proj")
        self.assertEqual(status, 200, body)
        return json.loads(body)["agents"]

    def test_get_contains_opencode_rows(self):
        rows = {row["name"]: row for row in self.agent_rows()}
        for name in ("general", "explore"):
            self.assertIn(name, rows)
            self.assertIs(rows[name].get("opencode"), True)

    def test_post_toggle_and_model_for_opencode_agent(self):
        status, body = self.request(
            "/api/project-agents",
            {"name": "proj", "agent": "general", "selected": False},
        )
        self.assertEqual(status, 200, body)
        rows = {row["name"]: row for row in self.agent_rows()}
        self.assertFalse(rows["general"]["selected"])

        status, body = self.request(
            "/api/project-agents",
            {"name": "proj", "agent": "explore", "model": "free/explore"},
        )
        self.assertEqual(status, 200, body)
        rows = {row["name"]: row for row in self.agent_rows()}
        self.assertEqual(rows["explore"]["effective_model"], "free/explore")

    def test_invalid_post_returns_400_without_writing(self):
        path = self.project / ".vibe" / "agents.json"
        before = path.read_bytes() if path.exists() else None
        for payload in (
            {"name": "proj", "agent": "explore", "model": "bad model"},
            {"name": "proj", "agent": "build", "selected": True},
            {"name": "proj", "agent": "general", "selected": "ja"},
        ):
            with self.subTest(payload=payload):
                status, body = self.request("/api/project-agents", payload)
                self.assertEqual(status, 400, body)
                after = path.read_bytes() if path.exists() else None
                self.assertEqual(after, before)

    def test_agent_template_api_returns_v2_frontmatter(self):
        status, body = self.request(
            "/api/agent_template",
            {"scope": "proj", "description": "API-Agent", "perm": "lesen"},
        )
        self.assertEqual(status, 200, body)
        text = json.loads(body)["message"]
        assert_no_v1_keys(self, text)
        self.assertIn("description: API-Agent", text)


# --------------------------------------------------------------------------
# B7: CLI zeigt opencode-Zeilen
# --------------------------------------------------------------------------

class B7CliTest(CliFixture):
    def test_project_agents_cli_lists_opencode_state_and_model(self):
        self.write_global(
            "vibe-agent",
            v2_agent(LESEN_RULES, mode="primary", model="opencode/vibe-modell"),
        )
        data = self.cli.profiles_load()
        data["rollen"] = {"vibe-agent": "vibe"}
        self.cli.profiles_save(data)
        self.write_config(
            self.project,
            {
                "version": 3,
                "aktiv": ["vibe-agent"],
                "modelle": {},
                "opencode": {
                    "general": {"aktiv": False, "modell": "free/general"},
                    "explore": {"aktiv": True, "modell": "free/explore"},
                },
            },
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
        general = [line for line in output.splitlines() if line.startswith("general")]
        explore = [line for line in output.splitlines() if line.startswith("explore")]
        self.assertTrue(general, output)
        self.assertTrue(explore, output)
        self.assertRegex(general[0], r"nein|aus|verboten|inaktiv")
        self.assertIn("free/general", general[0])
        self.assertIn("free/explore", explore[0])


# --------------------------------------------------------------------------
# B6: Läufer mischt opencode-Einträge in OPENCODE_CONFIG_CONTENT
# --------------------------------------------------------------------------

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


def effective_model(config, agent):
    if not isinstance(config, dict):
        return None
    for key in ("agents", "agent"):
        agents = config.get(key)
        if isinstance(agents, dict):
            entry = agents.get(agent)
            if isinstance(entry, dict) and isinstance(entry.get("model"), str):
                return entry["model"]
    return None


class SharedOpenCode:
    """Erreichbarer gemeinsamer opencode-Server für die Wiederverwendung."""

    def __init__(self, port):
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

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        try:
            self.httpd.shutdown()
        finally:
            self.httpd.server_close()
            self.thread.join(timeout=5)


class RunnerFixture(unittest.TestCase):
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
                "B6", "Testpaket",
                description="opencode-Agenten im Lauf")],
        )
        (self.project / ".gitignore").write_text("/.vibe/\n", encoding="utf-8")
        support.init_repo(self.project)
        support.commit_all(self.project)

        self.env_record = self.root / "opencode.env.jsonl"
        self.args_file = self.runtime / "opencode.args"
        self.serve_record = self.root / "serve.record.jsonl"
        self.shared = None
        self.addCleanup(self.stop_shared)

    def config_path(self):
        return self.project / ".vibe" / "agents.json"

    def write_config(self, data):
        path = self.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def write_opencode(self, general=None, explore=None, modelle=None, aktiv=None):
        data = {
            "version": 3,
            "aktiv": sorted(aktiv if aktiv is not None else (modelle or {})),
            "modelle": modelle or {},
            "opencode": {
                "general": general or {"aktiv": True, "modell": ""},
                "explore": explore or {"aktiv": True, "modell": ""},
            },
        }
        return self.write_config(data)

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
                "VIBE_OPENCODE_PORT": str(free_port()),
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

    def start_shared_server(self):
        port = free_port()
        self.shared = SharedOpenCode(port).start()
        return port

    def stop_shared(self):
        if self.shared is not None:
            self.shared.stop()
            self.shared = None

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

    def records(self):
        try:
            raw = self.env_record.read_text(encoding="utf-8")
        except OSError:
            return []
        return [json.loads(line) for line in raw.splitlines() if line.strip()]

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

    def log_text(self):
        path = self.runtime / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""


class RunnerControlTest(RunnerFixture):
    def test_no_effective_entries_keeps_previous_b1_behaviour(self):
        """Nur Standard-opencode-Einträge (aktiv, kein Modell) sind wirkungslos."""
        self.write_opencode()
        shared_port = self.start_shared_server()

        result = self.run_runner(
            "tester", extra_env={"VIBE_OPENCODE_PORT": str(shared_port)}
        )

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), repr(self.records()))
        self.assertIsNone(
            runs[0].get("config"),
            "Ohne wirksame opencode-Einträge wurde eine Inline-Konfiguration gesetzt")
        argv = runs[0]["argv"]
        self.assertIn("--server", argv, repr(argv))
        self.assertEqual(
            argv[argv.index("--server") + 1],
            "http://127.0.0.1:" + str(shared_port),
            "Die Serverwahl ohne wirksame opencode-Einträge wurde verändert",
        )


class RunnerOpencodeConfigTest(RunnerFixture):
    def test_active_model_is_mixed_into_both_agent_maps(self):
        self.write_opencode(
            general={"aktiv": True, "modell": "free/general"},
            modelle={"tester": "projekt/tester-modell"},
        )

        result = self.run_runner("tester", "auftrag/start-modell")

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), repr(self.records()))
        config = self.config_of(runs[0])
        self.assertEqual(effective_model(config, "general"), "free/general")
        self.assertEqual(config["agent"]["general"]["model"], "free/general")
        self.assertEqual(config["agents"]["general"]["model"], "free/general")
        self.assertEqual(effective_model(config, "tester"), "projekt/tester-modell")

    def test_inactive_agent_disables_only_the_v2_agents_map(self):
        self.write_opencode(
            general={"aktiv": False, "modell": ""},
            explore={"aktiv": False, "modell": ""},
        )

        result = self.run_runner("tester")

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), repr(self.records()))
        config = self.config_of(runs[0])
        for name in ("general", "explore"):
            self.assertIs(config["agents"][name].get("disabled"), True,
                          "opencode-Agent wurde nicht deaktiviert: " + name)
            self.assertNotIn(
                "disabled", config.get("agent", {}).get(name, {}),
                "Deaktivierung landete in der Legacy-agent-Map: " + name)
            self.assertNotIn(
                name, config.get("agent", {}),
                "Deaktivierter Agent wurde als Legacy-agent-Eintrag angelegt: " + name)

    def test_inactive_model_is_not_applied(self):
        self.write_opencode(
            explore={"aktiv": False, "modell": "free/explore"},
        )

        result = self.run_runner("tester")

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, detail)
        config = self.config_of(self.run_calls()[0])
        self.assertIs(config["agents"]["explore"].get("disabled"), True)
        self.assertIsNone(effective_model(config, "explore"),
                          "Ein Modell eines verbotenen opencode-Agenten wurde gesetzt")

    def test_existing_jsonc_config_is_merged_and_preserved(self):
        jsonc = """{
  // Bestehende Anmerkung
  "theme": "dark",
  "agent": {
    "reviewer": {
      "model": "global/reviewer",
      "temperature": 0.2,
    },
  },
}
"""
        self.write_opencode(
            general={"aktiv": True, "modell": "free/general"},
            explore={"aktiv": False, "modell": ""},
        )

        result = self.run_runner(
            "tester", extra_env={"OPENCODE_CONFIG_CONTENT": jsonc}
        )

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, detail)
        config = self.config_of(self.run_calls()[0])
        self.assertEqual(config.get("theme"), "dark")
        self.assertEqual(
            config["agent"]["reviewer"].get("temperature"), 0.2)
        self.assertEqual(effective_model(config, "general"), "free/general")
        self.assertIs(config["agents"]["explore"].get("disabled"), True)
        self.assertNotIn(
            "disabled", config.get("agent", {}).get("explore", {}))

    def test_shared_server_is_not_reused_with_effective_opencode_entry(self):
        self.write_opencode(
            general={"aktiv": True, "modell": "free/general"},
        )
        shared_port = self.start_shared_server()

        result = self.run_runner(
            "tester", extra_env={"VIBE_OPENCODE_PORT": str(shared_port)}
        )

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), repr(self.records()))
        argv = runs[0]["argv"]
        self.assertIn("--standalone", argv, repr(argv))
        self.assertNotIn("--server", argv, repr(argv))
        self.assertNotIn("http://127.0.0.1:" + str(shared_port), argv)
        self.assertEqual(effective_model(self.config_of(runs[0]), "general"),
                         "free/general")


class RunnerInvalidConfigTest(RunnerFixture):
    def assert_no_agent_started(self):
        self.assertEqual([], self.run_calls(),
                         "Agent wurde trotz fehlerhafter Konfiguration gestartet")
        self.assertEqual([], self.serve_calls(),
                         "Privater Server wurde trotz fehlerhafter Konfiguration gestartet")

    def test_invalid_opencode_model_aborts_before_agent_start(self):
        self.write_opencode(
            general={"aktiv": True, "modell": "kein modell mit leerzeichen"},
        )
        secret = "ap2-geheim-4711"

        result = self.run_runner(
            "tester", extra_env={"OPENCODE_SERVER_PASSWORD": secret}
        )

        detail = result.stdout + result.stderr + self.log_text()
        self.assertNotEqual(result.returncode, 0, detail)
        self.assert_no_agent_started()
        self.assertRegex(
            detail,
            r"Agentenauswahl|Modell|opencode",
            "Keine verständliche Meldung zur ungültigen opencode-Konfiguration:\n"
            + detail,
        )
        self.assertNotIn(secret, detail,
                         "Ein Geheimnis wurde im Protokoll ausgegeben")

    def test_unreadable_project_config_aborts_before_agent_start(self):
        path = self.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{kaputt", encoding="utf-8")

        result = self.run_runner("tester")

        detail = result.stdout + result.stderr + self.log_text()
        self.assertNotEqual(result.returncode, 0, detail)
        self.assert_no_agent_started()
        self.assertRegex(
            detail,
            r"agents\.json|Agentenauswahl|Projektkonfiguration|Projektdatei",
            "Keine verständliche Meldung zur fehlerhaften Projektdatei:\n" + detail,
        )


if __name__ == "__main__":
    unittest.main()
