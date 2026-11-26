"""Priorität: Auswahlreihenfolge, Läuferbefehl und API.

Aufruf: python3 -m unittest tests.unit.test_priority -v
"""


# ===========================================================================
# Abnahme „Priorisierung der Abarbeitungsreihenfolge“
# ===========================================================================

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

    def test_draft_entries_are_marked_as_entwurf_and_skipped(self):
        """GH-47: Entwürfe sind in der Priorisierung sichtbar, aber nicht
        lauffähig.
        Vorbedingung: ``PACKAGE_ORDER="T1,T2"``; T1 Entwurf, T2 offen.
        Aktion: ``priority_view`` und ``select_package``.
        Erwartung: ``order``/``standard`` weisen T1 als „Entwurf“ aus; die
        wirksame ``queue`` enthält T1 nicht und beginnt mit T2. ``select``
        wählt T2.
        Fehlerfall: Entwürfe gelten als „offen“ oder werden gestartet.
        """
        project = self.project([
            ticket_record("T1", "Entwurf", state="draft", priority="P0"),
            ticket_record("T2", "Offen"),
        ])
        write_env(project / ".vibe" / "project.env",
                  'TYPE=generic\nPACKAGE_ORDER="T1,T2"\n')

        view = self.module.priority_view(project)

        by_id = {entry["id"]: entry for entry in view["order"]}
        self.assertEqual("Entwurf", by_id["T1"]["status"])
        standard = {entry["id"]: entry for entry in view["standard"]}
        self.assertEqual("Entwurf", standard["T1"]["status"])
        self.assertEqual("T2", view["queue"][0]["id"])
        self.assertNotIn("T1", [item["id"] for item in view["queue"]])
        self.assertEqual("T2", self.select(project)["id"])

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


# ===========================================================================
# HTTP-Abnahme „Priorisierung: Speichern-Fehler und neue Bedienstelle“
# ===========================================================================

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

WEB = REPO / "bin" / "vibe-web.py"

# Ambient VIBE_*-Werte (Sandbox/Container) würden vibe-web auf die
# produktive Installation zeigen lassen; der Test besitzt alle Laufzeitpfade.
ISOLATED_ENV_f29 = (
    "VIBE",
    "VIBE_NO_CONTAINER",
    "HOME",
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
    "VIBE_HARNESS",
)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def git_repo(project, *argv):
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
    })
    return subprocess.run(
        ["git", "-C", str(project), *argv],
        capture_output=True, text=True, check=False, timeout=60,
        env=env,
    )


class F29PriorityApiTest(unittest.TestCase):
    """AK 1/2: POST /api/priority des echten, isolierten Dashboards."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        cls.project.mkdir(parents=True)
        git_repo(cls.project, "init", "-q", "-b", "main")
        (cls.project / ".vibe").mkdir(exist_ok=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nTESTER=test-agent\n", encoding="utf-8")
        # Eine nachweislich erledigte Aufgabe und zwei offene Aufgaben —
        # dieselbe Fixture wie in tests/browser/test_ap11_priority_ui.py,
        # damit die Statusanzeige der API (erledigt/offen) prüfbar bleibt.
        git_repo(cls.project, "commit", "--allow-empty", "-q", "-m", "init")
        commit = subprocess.run(
            ["git", "-C", str(cls.project), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()
        def record(tid, title, state="open", **extra):
            item = {
                "id": tid, "title": title, "type": "task", "state": state,
                "description": "", "github": None, "pr_url": "",
                "commit": "", "test": "", "blocked_reason": "",
                "waiting_note": "", "priority": "", "dependencies": [],
                "created": "2026-01-01T00:00:00+00:00",
                "updated": "2026-01-01T00:00:00+00:00",
            }
            item.update(extra)
            return item
        (cls.project / ".vibe" / "tickets.json").write_text(
            json.dumps({"version": 1, "tickets": [
                record("T0", "Erledigte Aufgabe", state="done",
                       description="fertig", commit=commit,
                       test="test_ap11"),
                record("T1", "Erste Aufgabe", description="offen"),
                record("T2", "Zweite Aufgabe", description="offen"),
            ]}, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        (cls.project / ".gitignore").write_text(".vibe/\n", encoding="utf-8")
        cls.env_path = cls.project / ".vibe" / "project.env"
        cls.base_env = "TYPE=generic\nTESTER=test-agent\n"

        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.toolchain = cls.root / "_toolchain"
        cls.toolchain.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.port = free_port()
        env = os.environ.copy()
        for key in ISOLATED_ENV_f29:
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.home),
                "VIBE_STATE": str(cls.toolchain),
                "VIBE_INSTALL": str(cls.toolchain),
                "VIBE_RUNTIME": str(cls.log_dir),
                "VIBE_AGENTS_DIR": str(
                    cls.home / ".config" / "opencode" / "agents"),
                "VIBE_CONFIG_FILE": str(
                    cls.home / ".config" / "vibe" / "config.json"),
            }
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                            ("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: " + output)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.base = f"http://127.0.0.1:{cls.port}"

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
        """Jeder Test startet mit der Grundkonfiguration ohne Priorisierung."""
        self.env_path.write_text(self.base_env, encoding="utf-8")

    # ------------------------------------------------------------ Helfer
    def post_priority(self, body):
        """POST /api/priority; liefert (Statuscode, JSON-Antwort).

        HTTP-Fehler (4xx/5xx) werden wie erfolgreiche Antworten als
        strukturierte JSON-Körper zurückgegeben, damit die Tests genau
        zwischen „strukturierte Ablehnung“ und „Absturz (500)“
        unterscheiden können.
        """
        request = urllib.request.Request(
            self.base + "/api/priority",
            data=json.dumps(body).encode("utf-8"),
            method="POST")
        request.add_header("X-Token", self.token)
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(
                    response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", "replace")
            try:
                return error.code, json.loads(raw)
            except ValueError:
                return error.code, {"raw": raw}

    def env_text(self):
        return self.env_path.read_text(encoding="utf-8")

    # ------------------------------------------------------------ AK 1
    def test_post_set_returns_ok_and_writes_package_order(self):
        """AK 1 — Speichern antwortet erfolgreich und legt PACKAGE_ORDER ab."""
        status, payload = self.post_priority(
            {"name": "proj", "action": "set", "order": "T2,T1"})

        self.assertEqual(200, status,
                         "Speichern antwortete nicht erfolgreich: "
                         + json.dumps(payload, ensure_ascii=False))
        self.assertTrue(payload.get("ok"),
                        "Speichern meldet ok falsch: "
                        + json.dumps(payload, ensure_ascii=False))
        message = payload.get("message", "")
        self.assertIsInstance(message, str)
        self.assertTrue(message.strip(),
                        "Speichern ohne Klartext-Meldung: "
                        + json.dumps(payload, ensure_ascii=False))
        self.assertIn("priority", payload,
                      "Antwort ohne aktualisierte Ansicht (priority): "
                      + json.dumps(payload, ensure_ascii=False))
        queue = [entry.get("id") for entry
                 in payload["priority"].get("queue", [])]
        self.assertEqual(["T2", "T1"], queue,
                         "aktualisierte Ansicht zeigt andere Ordnung: "
                         + json.dumps(payload["priority"],
                                      ensure_ascii=False))

        text = self.env_text()
        self.assertIn("PACKAGE_ORDER", text,
                      "Speichern schrieb kein PACKAGE_ORDER: " + text)
        self.assertLess(text.index("T2"), text.index("T1"),
                        "PACKAGE_ORDER nicht in gewählter Reihenfolge: " + text)
        self.assertIn("TYPE=generic", text,
                      "Speichern beschädigte project.env")
        self.assertIn("TESTER=test-agent", text,
                      "Speichern beschädigte project.env")

    def test_post_clear_returns_ok_and_empties_package_order(self):
        """AK 1 — Leeren antwortet erfolgreich und stellt die Standardordnung her."""
        self.env_path.write_text(
            self.base_env + 'PACKAGE_ORDER="T2,T1"\n', encoding="utf-8")

        status, payload = self.post_priority(
            {"name": "proj", "action": "clear"})

        self.assertEqual(200, status,
                         "Leeren antwortete nicht erfolgreich: "
                         + json.dumps(payload, ensure_ascii=False))
        self.assertTrue(payload.get("ok"),
                        "Leeren meldet ok falsch: "
                        + json.dumps(payload, ensure_ascii=False))
        message = payload.get("message", "")
        self.assertTrue(message.strip(),
                        "Leeren ohne Klartext-Meldung: "
                        + json.dumps(payload, ensure_ascii=False))
        queue = [entry.get("id") for entry
                 in payload.get("priority", {}).get("queue", [])]
        self.assertEqual(["T1", "T2"], queue,
                         "Leeren zeigte nicht die Standardordnung: "
                         + json.dumps(payload, ensure_ascii=False))

        text = self.env_text()
        self.assertNotRegex(
            text, r'(?m)^\s*PACKAGE_ORDER\s*=\s*["\']?\s*[^"\'\s]+',
            "Leeren hinterließ Kennungen in PACKAGE_ORDER: " + text)
        self.assertIn("TYPE=generic", text, "Leeren beschädigte project.env")
        self.assertIn("TESTER=test-agent", text,
                      "Leeren beschädigte project.env")

    def test_post_set_preserves_other_env_lines(self):
        """AK 1 — Speichern erhält die übrigen Zeilen von project.env."""
        self.env_path.write_text(
            "# Projekt-Hinweis\n"
            "TYPE=generic\n"
            "TESTER=test-agent\n",
            encoding="utf-8")

        status, payload = self.post_priority(
            {"name": "proj", "action": "set", "order": "T2,T1"})

        self.assertEqual(200, status,
                         "Speichern antwortete nicht erfolgreich: "
                         + json.dumps(payload, ensure_ascii=False))
        text = self.env_text()
        self.assertIn("# Projekt-Hinweis", text,
                      "Kommentarzeile ging verloren: " + text)
        self.assertIn("TYPE=generic", text, "TYPE-Zeile ging verloren: " + text)
        self.assertIn("TESTER=test-agent", text,
                      "TESTER-Zeile ging verloren: " + text)
        self.assertLess(text.index("T2"), text.index("T1"),
                        "PACKAGE_ORDER nicht in gewählter Reihenfolge: " + text)

    # ------------------------------------------------------------ AK 2
    def test_post_set_rejects_unknown_id_without_change(self):
        """AK 2 — Unbekannte Kennung wird ohne Dateiänderung abgelehnt."""
        before = self.env_text()

        status, payload = self.post_priority(
            {"name": "proj", "action": "set", "order": "X9,T1"})

        self.assertNotEqual(500, status,
                            "Unbekannte Kennung führte zu einem Absturz: "
                            + json.dumps(payload, ensure_ascii=False))
        self.assertFalse(payload.get("ok"),
                         "Unbekannte Kennung meldete Erfolg: "
                         + json.dumps(payload, ensure_ascii=False))
        message = payload.get("message", "")
        self.assertTrue(message.strip(),
                        "Ablehnung ohne Klartext-Fehlermeldung: "
                        + json.dumps(payload, ensure_ascii=False))
        self.assertEqual(before, self.env_text(),
                         "Die Ablehnung veränderte project.env")

    def test_post_unknown_action_is_rejected_without_crash(self):
        """AK 2 — Unbekannte Aktion wird strukturiert abgelehnt."""
        before = self.env_text()

        status, payload = self.post_priority(
            {"name": "proj", "action": "unsinn", "order": "T2,T1"})

        self.assertNotEqual(500, status,
                            "Unbekannte Aktion führte zu einem Absturz: "
                            + json.dumps(payload, ensure_ascii=False))
        self.assertFalse(payload.get("ok"),
                         "Unbekannte Aktion meldete Erfolg: "
                         + json.dumps(payload, ensure_ascii=False))
        message = payload.get("message", "")
        self.assertTrue(message.strip(),
                        "Ablehnung ohne Klartext-Fehlermeldung: "
                        + json.dumps(payload, ensure_ascii=False))
        self.assertEqual(before, self.env_text(),
                         "Die unbekannte Aktion veränderte project.env")

    def test_post_unknown_project_is_rejected_without_crash(self):
        """AK 2 — Unbekanntes Projekt wird ohne Absturz abgelehnt."""
        before = self.env_text()

        status, payload = self.post_priority(
            {"name": "does-not-exist", "action": "set", "order": "T2,T1"})

        self.assertNotEqual(500, status,
                            "Unbekanntes Projekt führte zu einem Absturz: "
                            + json.dumps(payload, ensure_ascii=False))
        self.assertFalse(payload.get("ok"),
                         "Unbekanntes Projekt meldete Erfolg: "
                         + json.dumps(payload, ensure_ascii=False))
        self.assertEqual(before, self.env_text(),
                         "Die Anfrage veränderte project.env")


    # ------------------------- Review Runde 2, Finding M1 (AK-A)
    def write_mixed_sources_fixture(self):
        """Gemischte Quellen für die Standardordnung (AK-A).

        Ersetzt die Grund-Fixture durch: erledigte T0 (mit gültigem
        Nachweis), P0/P1/ohne Priorität, BLOCKIERT-Paket, abhängiges
        Paket und einen FEEDBACK-Eintrag. Stellt beide Dateien nach dem
        Test wieder her.
        """
        store = self.project / ".vibe" / "tickets.json"
        original = store.read_text(encoding="utf-8")
        commit = subprocess.run(
            ["git", "-C", str(self.project), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()
        self.addCleanup(store.write_text, original, encoding="utf-8")

        def record(tid, title, type="task", state="open", **extra):
            item = {
                "id": tid, "title": title, "type": type, "state": state,
                "description": "", "github": None, "pr_url": "",
                "commit": "", "test": "", "blocked_reason": "",
                "waiting_note": "", "priority": "", "dependencies": [],
                "created": "2026-01-01T00:00:00+00:00",
                "updated": "2026-01-01T00:00:00+00:00",
            }
            item.update(extra)
            return item

        store.write_text(
            json.dumps({"version": 1, "tickets": [
                record("T0", "Erledigte Aufgabe", state="done",
                       description="fertig", commit=commit,
                       test="test_ap11"),
                record("T1", "Erste Aufgabe", description="offen",
                       priority="P1"),
                record("T2", "Zweite Aufgabe", description="offen",
                       priority="P0"),
                record("T3", "Dritte Aufgabe",
                       description="ohne Priorität"),
                record("T4", "Gesperrte Aufgabe", state="blocked",
                       description="wartet", blocked_reason="fehlende Freigabe"),
                record("T5", "Abhängige Aufgabe",
                       description="wartet auf T1", dependencies=["T1"]),
                record("F1", "Feedback-Paket", type="feedback",
                       description="offen"),
            ]}, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

    def get_priority(self, name="proj"):
        """GET /api/priority; liefert (Statuscode, JSON-Antwort).

        HTTP-Fehler werden als strukturierte JSON-Körper zurückgegeben,
        damit Abstürze (500) von Ablehnungen unterscheidbar bleiben.
        """
        request = urllib.request.Request(
            self.base + "/api/priority?name=" + urllib.parse.quote(name),
            method="GET")
        request.add_header("X-Token", self.token)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(
                    response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", "replace")
            try:
                return error.code, json.loads(raw)
            except ValueError:
                return error.code, {"raw": raw}

    def test_get_standard_lists_open_packages_in_runner_order(self):
        """AK-A — GET liefert ``standard`` in Läufer-Standardordnung.

        Vorbedingung: gemischte Quellen (TICKETS: T0 erledigt mit Nachweis,
        T2 mit P0, T1 mit P1, T3 ohne Angabe, T4 BLOCKIERT, T5 abhängig
        von T1; FEEDBACK: F1 offen); project.env ohne PACKAGE_ORDER.
        Aktion: GET /api/priority?name=proj mit Token stellen.
        Erwartet: HTTP 200; ``standard`` enthält alle nicht erledigten
        Pakete in Läufer-Standardordnung — Statusvorrang vor Priorität:
        zuerst die offenen TICKETS T2 (P0), T1 (P1), T3 (ohne Angabe) und
        das abhängigkeitsgeblockte, aber offene T5 in Dateireihenfolge,
        dann das offene FEEDBACK F1, zuletzt das BLOCKIERT-Paket T4 (der
        Status BLOCKIERT steht nach ``open``; die Priorität ist innerhalb
        der Statusgruppe sekundär). Die erledigte T0 fehlt; die Felder
        ``order`` und ``queue`` bleiben in der Antwort vorhanden.
        """
        self.write_mixed_sources_fixture()

        status, payload = self.get_priority()

        self.assertEqual(200, status,
                         "GET antwortete nicht erfolgreich: "
                         + json.dumps(payload, ensure_ascii=False))
        self.assertIn("standard", payload,
                      "Antwort ohne Feld standard: "
                      + json.dumps(payload, ensure_ascii=False))
        standard = payload["standard"]
        self.assertIsInstance(standard, list,
                              "standard ist keine Liste: "
                              + json.dumps(payload, ensure_ascii=False))
        self.assertTrue(
            all(isinstance(entry, dict) and "id" in entry
                for entry in standard),
            "standard-Einträge ohne Kennung (id): "
            + json.dumps(payload, ensure_ascii=False))
        self.assertEqual(
            ["T2", "T1", "T3", "T5", "F1", "T4"],
            [entry["id"] for entry in standard],
            "standard zeigt nicht die Läufer-Standardordnung mit "
            "Statusvorrang vor Priorität: "
            + json.dumps(payload, ensure_ascii=False))
        self.assertNotIn(
            "T0", [entry["id"] for entry in standard],
            "die erledigte T0 steht in der Standardordnung: "
            + json.dumps(payload, ensure_ascii=False))
        self.assertIn("order", payload,
                      "bestehendes Feld order fehlt in der Antwort")
        self.assertIn("queue", payload,
                      "bestehendes Feld queue fehlt in der Antwort")

    # ------------------------- Review Runde 2, Finding M1 (AK-B)
    def test_get_order_and_queue_unchanged_without_configuration(self):
        """AK-B — ohne PACKAGE_ORDER bleibt order/queue wie bisher.

        Vorbedingung: Grund-Fixture (T0 erledigt, T1/T2 offen, FEEDBACK
        leer), kein PACKAGE_ORDER-Eintrag. Aktion: GET stellen.
        Erwartet: HTTP 200; ``order`` bleibt leer und ``queue`` zeigt die
        TICKETS-Reihenfolge T1 vor T2 — keine Regression durch das neue
        Feld ``standard``.
        """
        status, payload = self.get_priority()

        self.assertEqual(200, status,
                         "GET antwortete nicht erfolgreich: "
                         + json.dumps(payload, ensure_ascii=False))
        self.assertEqual([], payload.get("order"),
                         "order änderte sich ohne Konfiguration: "
                         + json.dumps(payload, ensure_ascii=False))
        queue = [entry.get("id") for entry in payload.get("queue", [])]
        self.assertEqual(["T1", "T2"], queue,
                         "queue änderte sich ohne Konfiguration: "
                         + json.dumps(payload, ensure_ascii=False))

    def test_get_order_and_queue_unchanged_with_configuration(self):
        """AK-B — mit PACKAGE_ORDER bleibt die GET-Antwort wie bisher.

        Vorbedingung: PACKAGE_ORDER="T2,T0,X9,T1" abgelegt; T0 erledigt
        (mit Nachweis), T1/T2 offen, X9 unbekannt. Aktion: GET stellen.
        Erwartet: HTTP 200; ``order`` nennt die konfigurierten Einträge in
        gespeicherter Reihenfolge mit Status (T2 offen, T0 erledigt,
        X9 fehlt, T1 offen); ``queue`` bleibt die effektive Reihenfolge
        T2 vor T1 ohne erledigte T0.
        """
        self.env_path.write_text(
            self.base_env + 'PACKAGE_ORDER="T2,T0,X9,T1"\n',
            encoding="utf-8")

        status, payload = self.get_priority()

        self.assertEqual(200, status,
                         "GET antwortete nicht erfolgreich: "
                         + json.dumps(payload, ensure_ascii=False))
        order = payload.get("order", [])
        self.assertEqual(["T2", "T0", "X9", "T1"],
                         [entry.get("id") for entry in order],
                         "order-Reihenfolge änderte sich: "
                         + json.dumps(payload, ensure_ascii=False))
        self.assertEqual("offen", order[0].get("status"),
                         "Status von T2 falsch: "
                         + json.dumps(payload, ensure_ascii=False))
        self.assertEqual("erledigt", order[1].get("status"),
                         "Status von T0 falsch: "
                         + json.dumps(payload, ensure_ascii=False))
        self.assertEqual("fehlt", order[2].get("status"),
                         "Status von X9 falsch: "
                         + json.dumps(payload, ensure_ascii=False))
        self.assertEqual("offen", order[3].get("status"),
                         "Status von T1 falsch: "
                         + json.dumps(payload, ensure_ascii=False))
        queue = [entry.get("id") for entry in payload.get("queue", [])]
        self.assertEqual(["T2", "T1"], queue,
                         "effektive Reihenfolge änderte sich: "
                         + json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
