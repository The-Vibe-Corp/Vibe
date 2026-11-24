"""Abnahme AP11 „Priorisierung der Abarbeitungsreihenfolge“ (GH-48-Fassung).

Die Reihenfolge der Tickets ist je Projekt über ``PACKAGE_ORDER`` in
``.vibe/project.env`` einstellbar und für die Agenten verbindlich; erledigte
Tickets werden der Priorisierung entnommen. Seit GH-48 stammt die Reihenfolge
aus dem Ticketspeicher ``.vibe/tickets.json`` — es gibt keine getrennten
Markdown-Quellen mehr.

Geprüfte Einstiegspunkte: ``select_package``, das Subkommando ``select`` von
``bin/vibe_packages.py`` als echter Prozess und die CLI ``vibe priority``.
Keine Modellaufrufe, keine externen Dienste, keine produktiven Pfade.

Run:

    python3 -m unittest tests.unit.test_ap11_priority -v
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PACKAGES = REPO / "bin" / "vibe_packages.py"
CLI = REPO / "bin" / "vibe"

ISOLATED_ENV = (
    "VIBE", "VIBE_NO_CONTAINER", "HOME", "VIBE_PROFILE", "VIBE_INSTALL",
    "VIBE_RUNTIME", "VIBE_STATE", "VIBE_AGENTS_DIR", "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR", "VIBE_UI_PORT", "VIBE_OPENCODE_PORT", "VIBE_UI_BIND",
    "VIBE_CONTAINER", "VIBE_HARNESS", "GITHUB_TOKEN", "GH_TOKEN",
)

GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}

STAMP = "2026-01-01T00:00:00+00:00"


def load_packages():
    loader = importlib.machinery.SourceFileLoader(
        "vibe_packages_ap11_under_test", str(PACKAGES))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    loader.exec_module(module)
    return module


def ticket_record(tid, title, type="task", state="open", **extra):
    record = {
        "id": tid, "title": title, "type": type, "state": state,
        "description": "", "github": None, "pr_url": "", "commit": "",
        "test": "", "blocked_reason": "", "waiting_note": "",
        "priority": "", "dependencies": [],
        "created": STAMP, "updated": STAMP,
    }
    record.update(extra)
    return record


def write_env(env_path, text):
    path = Path(env_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def env_values(path):
    values = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def package_order(env_path):
    raw = env_values(env_path).get("PACKAGE_ORDER", "")
    return [token for token in re.split(r"[,;\s]+", raw) if token]


def git(project, *argv):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update(GIT_IDENTITY)
    return subprocess.run(
        ["git", "-C", str(project), *argv],
        capture_output=True, text=True, check=False, timeout=60, env=env)


def git_commit(project):
    git(project, "add", "-A")
    result = git(project, "commit", "-q", "-m", "Teststand")
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)
    return git(project, "rev-parse", "--short", "HEAD").stdout.strip()


def write_store(project, records):
    path = Path(project) / ".vibe" / "tickets.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "tickets": list(records)},
                   ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    return path


def read_store(project):
    document = json.loads(
        (Path(project) / ".vibe" / "tickets.json").read_text(encoding="utf-8"))
    return {item["id"]: item for item in document["tickets"]}


def make_project(root, name="proj", records=None, env_text=""):
    """Minimales Git-Projekt mit GH-48-Ticketspeicher und project.env."""
    project = Path(root) / name
    project.mkdir(parents=True, exist_ok=True)
    git(project, "init", "-q", "-b", "main")
    (project / ".vibe").mkdir(exist_ok=True)
    write_env(project / ".vibe" / "project.env",
              env_text or "TYPE=generic\nTESTER=test-agent\n")
    (project / ".gitignore").write_text(".vibe/\n", encoding="utf-8")
    write_store(project, records or [])
    git_commit(project)
    return project


def new_proof_commit(project):
    (Path(project) / "umsetzung.txt").write_text("x\n", encoding="utf-8")
    return git_commit(project)


OPEN_TICKETS = [
    ticket_record("T1", "Erste Aufgabe", description="offen"),
    ticket_record("T2", "Zweite Aufgabe", description="offen"),
]


class SelectionOrderTest(unittest.TestCase):
    """AK 1–7: Auswahl mit und ohne Priorisierung auf dem Speicher."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.module = load_packages()

    def project(self, records=None, env_text=""):
        return make_project(self.root, records=records or OPEN_TICKETS,
                            env_text=env_text)

    def select(self, project, **kwargs):
        kwargs.setdefault("state_path", str(self.root / "next.json"))
        return self.module.select_package(project, **kwargs)

    def test_without_configuration_selection_uses_store_order(self):
        project = self.project(OPEN_TICKETS + [ticket_record(
            "F1", "Feedbackaufgabe", type="feedback")])

        selected = self.select(project)

        self.assertEqual("T1", selected["id"])
        self.assertNotIn("source", selected)

    def test_without_configuration_the_priority_field_orders_tickets(self):
        project = self.project([
            ticket_record("T1", "Später", priority="P2"),
            ticket_record("T2", "Sofort", priority="P0"),
        ])

        selected = self.select(project)

        self.assertEqual("T2", selected["id"])

    def test_without_configuration_file_order_decides_within_priority(self):
        project = self.project([
            ticket_record("T1", "Erste", priority="P1"),
            ticket_record("T2", "Zweite", priority="P1"),
        ])

        selected = self.select(project)

        self.assertEqual("T1", selected["id"])

    def test_without_configuration_state_is_not_marked_as_ordered(self):
        project = self.project()

        selected = self.select(project)

        self.assertFalse(selected["ordered"])
        state = json.loads((self.root / "next.json").read_text(
            encoding="utf-8"))
        self.assertNotEqual(True, state.get("ordered"))

    def test_package_order_beats_priority_fields(self):
        project = self.project(
            [ticket_record("T1", "Wichtig", priority="P0"),
             ticket_record("T2", "Zweit", priority="P1")],
            env_text='TYPE=generic\nPACKAGE_ORDER="T2,T1"\n')

        selected = self.select(project)

        self.assertEqual("T2", selected["id"])
        self.assertTrue(selected["ordered"])

    def test_package_order_accepts_comma_semicolon_and_whitespace(self):
        project = self.project(
            OPEN_TICKETS,
            env_text='TYPE=generic\nPACKAGE_ORDER="T2,T1; F1  X9"\n')

        self.assertEqual(["T2", "T1", "F1", "X9"],
                         package_order(project / ".vibe" / "project.env"))
        self.assertEqual("T2", self.select(project)["id"])

    def test_quoted_package_order_with_spaces_is_understood(self):
        project = self.project(
            OPEN_TICKETS,
            env_text='TYPE=generic\nPACKAGE_ORDER="T2 T1"\n')

        self.assertEqual("T2", self.select(project)["id"])

    def test_done_entries_are_removed_from_the_priority(self):
        project = self.project()
        commit = new_proof_commit(project)
        write_store(project, [
            ticket_record("T0", "Erledigt", state="done", commit=commit,
                          test="test_t0"),
            ticket_record("T1", "Erste Aufgabe"),
        ])
        write_env(project / ".vibe" / "project.env",
                  'TYPE=generic\nPACKAGE_ORDER="T0,T1"\n')

        view = self.module.priority_view(project)

        self.assertEqual("erledigt",
                         {entry["id"]: entry for entry in view["order"]}
                         ["T0"]["status"])
        self.assertEqual("T1", self.select(project)["id"])

    def test_a_done_first_entry_never_becomes_the_choice(self):
        project = self.project()
        commit = new_proof_commit(project)
        write_store(project, [
            ticket_record("T0", "Erledigt", state="done", commit=commit,
                          test="test_t0"),
            ticket_record("T1", "Erste Aufgabe"),
        ])
        write_env(project / ".vibe" / "project.env",
                  'TYPE=generic\nPACKAGE_ORDER="T0,T1"\n')

        self.assertEqual("T1", self.select(project)["id"])

    def test_blocked_entries_in_the_priority_are_skipped(self):
        project = self.project([
            ticket_record("T1", "Blockiert", state="blocked",
                          blocked_reason="extern"),
            ticket_record("T2", "Offen"),
        ])
        write_env(project / ".vibe" / "project.env",
                  'TYPE=generic\nPACKAGE_ORDER="T1,T2"\n')

        self.assertEqual("T2", self.select(project)["id"])

    def test_dependency_blocked_entries_in_the_priority_are_skipped(self):
        project = self.project([
            ticket_record("T1", "Abhängig", dependencies=["T3"]),
            ticket_record("T2", "Offen"),
            ticket_record("T3", "Grundlage"),
        ])
        write_env(project / ".vibe" / "project.env",
                  'TYPE=generic\nPACKAGE_ORDER="T1,T2"\n')

        self.assertEqual("T2", self.select(project)["id"])

    def test_unknown_and_duplicate_ids_are_skipped_silently(self):
        project = self.project()
        write_env(project / ".vibe" / "project.env",
                  'TYPE=generic\nPACKAGE_ORDER="X9,T2,T2,T1"\n')

        self.assertEqual("T2", self.select(project)["id"])

    def test_skip_list_applies_to_ordered_entries(self):
        project = self.project()
        write_env(project / ".vibe" / "project.env",
                  'TYPE=generic\nPACKAGE_ORDER="T1,T2"\n')

        selected = self.select(project, skip={"T1"})

        self.assertEqual("T2", selected["id"])

    def test_ordered_selection_is_marked_in_the_state(self):
        project = self.project()
        write_env(project / ".vibe" / "project.env",
                  'TYPE=generic\nPACKAGE_ORDER="T2,T1"\n')

        selected = self.select(project)

        self.assertEqual("T2", selected["id"])
        state = json.loads((self.root / "next.json").read_text(
            encoding="utf-8"))
        self.assertTrue(state["ordered"])


class RunnerCommandTest(unittest.TestCase):
    """AK 2/5/6: Das echte Subkommando ``vibe_packages.py select``."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = make_project(self.root, records=OPEN_TICKETS)
        self.state = self.root / "state.json"

    def set_order(self, raw):
        write_env(self.project / ".vibe" / "project.env",
                  "TYPE=generic\nTESTER=test-agent\n"
                  'PACKAGE_ORDER="%s"\n' % raw)

    def run_select(self, *extra):
        return subprocess.run(
            [sys.executable, str(PACKAGES), "select",
             "--project", str(self.project), "--state", str(self.state),
             *extra],
            capture_output=True, text=True, check=False, timeout=120)

    def test_select_command_honors_the_package_order(self):
        self.set_order("T2,T1")

        result = self.run_select()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("T2", result.stdout.strip())
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(True, state.get("ordered"))

    def test_select_command_skips_unknown_ids_without_failure(self):
        self.set_order("X9,T2")

        result = self.run_select()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("T2", result.stdout.strip())

    def test_select_command_applies_the_skip_list(self):
        write_store(self.project, OPEN_TICKETS + [
            ticket_record("F1", "Feedbackaufgabe", type="feedback")])
        self.set_order("F1,T2")

        result = self.run_select("--skip", "F1")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("T2", result.stdout.strip())


class PriorityCommandLineTest(unittest.TestCase):
    """AK 5/8: CLI ``vibe priority <projekt> [set|clear]``."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = self.root = Path(self.tmp.name)
        self.project = make_project(self.workspace, records=OPEN_TICKETS)
        self.env_path = self.project / ".vibe" / "project.env"
        (self.workspace / "home").mkdir()

    def isolated_env(self):
        env = {key: value for key, value in os.environ.items()
               if key not in ISOLATED_ENV}
        env.update({
            "VIBE": str(self.workspace),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(self.workspace / "home"),
            "VIBE_INSTALL": str(self.workspace / "_toolchain"),
            "VIBE_STATE": str(self.workspace / "_toolchain"),
            "VIBE_RUNTIME": str(self.workspace / "_logs"),
            "VIBE_AGENTS_DIR": str(
                self.workspace / "home" / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(
                self.workspace / "home" / ".config" / "vibe" / "config.json"),
            "NO_PROXY": "127.0.0.1,localhost",
        })
        env.update(GIT_IDENTITY)
        return env

    def run_cli(self, *argv):
        return subprocess.run(
            [sys.executable, str(CLI), *argv],
            cwd=str(self.workspace), env=self.isolated_env(),
            capture_output=True, text=True, check=False, timeout=180)

    def run_select(self):
        return subprocess.run(
            [sys.executable, str(PACKAGES), "select",
             "--project", str(self.project)],
            capture_output=True, text=True, check=False, timeout=120)

    def read_env_file(self):
        return self.env_path.read_text(encoding="utf-8")

    def test_cli_priority_shows_configured_and_effective_order(self):
        write_env(self.env_path, "TYPE=generic\nTESTER=test-agent\n"
                  'PACKAGE_ORDER="T2,T1"\n')

        result = self.run_cli("priority", "proj")
        text = result.stdout + result.stderr

        self.assertEqual(0, result.returncode, text)
        self.assertIn("T2", text)
        self.assertIn("T1", text)
        self.assertLess(text.index("T2"), text.index("T1"), text)

    def test_cli_priority_without_configuration_shows_effective_order(self):
        result = self.run_cli("priority", "proj")

        text = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, text)
        self.assertIn("Standardordnung", text)
        self.assertIn("T1", text)

    def test_cli_priority_set_writes_package_order_and_preserves_lines(self):
        write_env(self.env_path,
                  "# Kommentar bleibt\nTYPE=generic\nTESTER=test-agent\n")

        result = self.run_cli("priority", "proj", "set", "T2,T1")

        text = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, text)
        content = self.read_env_file()
        self.assertIn("# Kommentar bleibt", content)
        self.assertIn("TYPE=generic", content)
        self.assertIn("TESTER=test-agent", content)
        self.assertEqual(["T2", "T1"],
                         package_order(self.env_path))

    def test_cli_priority_set_rejects_unknown_ids_without_change(self):
        write_env(self.env_path, "TYPE=generic\nTESTER=test-agent\n")
        before = self.read_env_file()

        result = self.run_cli("priority", "proj", "set", "X9,T1")

        self.assertNotEqual(0, result.returncode, result.stdout
                            + result.stderr)
        self.assertIn("X9", result.stdout + result.stderr)
        self.assertEqual(before, self.read_env_file())

    def test_cli_priority_set_reduces_duplicates_silently(self):
        result = self.run_cli("priority", "proj", "set", "T2,T1,T2")

        text = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, text)
        self.assertEqual(["T2", "T1"], package_order(self.env_path))

    def test_cli_priority_clear_empties_and_falls_back(self):
        write_env(self.env_path, "TYPE=generic\nTESTER=test-agent\n"
                  'PACKAGE_ORDER="T2,T1"\n')

        result = self.run_cli("priority", "proj", "clear")

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual([], package_order(self.env_path))
        selected = self.run_select()
        self.assertEqual("T1", selected.stdout.strip())


if __name__ == "__main__":
    unittest.main()
