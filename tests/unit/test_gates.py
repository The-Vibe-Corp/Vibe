"""Gates: Einstellungen, CLI, Läufer-Verdrahtung und Reparatur-Schranke.

Aufruf: python3 -m unittest tests.unit.test_gates -v
"""


# ===========================================================================
# Unabhängige Abnahme „Schrankeneinstellungen“
# ===========================================================================

#!/usr/bin/env python3
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

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support  # noqa: E402

GATE_KEYS = ("repair_rounds", "assist_rounds", "retries", "packages", "override")
DEFAULTS = {
    "repair_rounds": 2,
    "assist_rounds": 10,
    "retries": 2,
    "packages": 80,
    "override": "ask",
}
PROJECT_ENV_KEYS = {
    "repair_rounds": "REPAIR_ROUNDS",
    "assist_rounds": "ASSIST_ROUNDS",
    "retries": "MAX_RETRIES",
    "packages": "MAX_PACKAGES",
    "override": "GATE_OVERRIDE",
}
INVALID_MARKERS = (
    "ungültig", "unlesbar", "defekt", "beschädigt", "kein gültiges", "invalid",
)
# Feste Optionen der Schranken-Rückfrage (AP10) in der dokumentierten Menge;
# die Antwortposition wird je Test aus der tatsächlich angebotenen Liste
# gelesen, damit die Reihenfolge nicht überinterpretiert wird.
GATE_OPTIONS = (
    "Paket überspringen und Lauf fortsetzen",
    "Lauf abbrechen",
    "Agent behebt die Befunde",
)
# Bekannte Reihenfolge der Preflight-Rückfrage (F16/F22, Option 2 = Agent).
PREFLIGHT_OPTIONS = [
    "Erneut prüfen", "Lauf abbrechen", "Agent behebt die Befunde",
]

# GH-48: Arbeitspakete liegen als Ticketdatensätze im Speicher; die alten
# Markdown-Ledger gibt es nicht mehr.
FEEDBACK_ONE = [support.ticket_record(
    "F1", "Erstes Paket", type="feedback", description="Test")]
FEEDBACK_TWO = [
    support.ticket_record("F1", "Erstes Paket", type="feedback",
                          description="Test"),
    support.ticket_record("F2", "Zweites Paket", type="feedback",
                          description="Test"),
]

_MODULE_COUNTER = [0]


def load_module(path, prefix):
    """Lädt ein Modul aus ``bin`` ohne ``sys.path``-Nebenwirkungen."""
    _MODULE_COUNTER[0] += 1
    name = "%s_%d" % (prefix, _MODULE_COUNTER[0])
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def normalize_gates(result):
    """Bringt die Rückgabe von ``effective()`` auf (werte, herkunft, probleme).

    Zulässig sind flache Werte mit separater Herkunftsliste, verschachtelte
    Einträge mit ``value``/``origin`` und eine Klammer wie ``gates`` oder
    ``values``. Jede andere Form ist ein klar benannter Testfehler mit der
    vollständigen Rückgabe.
    """
    if not isinstance(result, dict):
        raise AssertionError(
            "effective() liefert kein Wörterbuch: %r" % (result,))
    problems = []
    for key in ("problems", "probleme", "Probleme", "meldungen"):
        value = result.get(key)
        if isinstance(value, (list, tuple)):
            problems = [str(item) for item in value]
            break
    inner = None
    for key in ("gates", "values", "werte", "schranken"):
        if isinstance(result.get(key), dict):
            inner = result[key]
            break
    source = inner if inner is not None else result
    values, origins = {}, {}
    nested = any(isinstance(source.get(key), dict) for key in GATE_KEYS)
    for key in GATE_KEYS:
        entry = source.get(key)
        if isinstance(entry, dict):
            values[key] = entry.get("value", entry.get("wert"))
            origins[key] = entry.get(
                "origin", entry.get("herkunft",
                                    entry.get("source", entry.get("quelle"))))
        elif entry is not None:
            values[key] = entry
    if not nested and inner is None:
        for key in ("origins", "herkunft", "quellen"):
            extra = result.get(key)
            if isinstance(extra, dict):
                for gate in GATE_KEYS:
                    if gate in extra:
                        origins[gate] = extra[gate]
                break
    missing = [key for key in GATE_KEYS if values.get(key) is None]
    if missing:
        raise AssertionError(
            "effective() liefert keine Werte für %s: %r" % (missing, result))
    return values, origins, problems


def json_contains(data, key, value):
    """Sucht ``key == value`` anywhere in einer verschachtelten Struktur."""
    if isinstance(data, dict):
        if data.get(key) == value:
            return True
        return any(json_contains(item, key, value) for item in data.values())
    if isinstance(data, list):
        return any(json_contains(item, key, value) for item in data)
    return False


def write_project_env_text(**gates):
    """Minimale ``project.env`` mit optionalen Schrankenwerten."""
    lines = [
        "TYPE=generic",
        "AGENT=test-agent",
        "TESTER=test-agent",
        "REVIEWER=code-reviewer",
        'VERIFY_PACKAGE="true"',
        'VERIFY_FULL="true"',
    ]
    for key in ("retries", "repair_rounds", "assist_rounds", "packages",
                "override"):
        if key in gates:
            lines.append("%s=%s" % (PROJECT_ENV_KEYS[key], gates[key]))
    return "\n".join(lines) + "\n"


class GatesModuleTest(unittest.TestCase):
    """``bin/vibe_gates.py`` liefert wirksame Werte samt Herkunft."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self._old_env = os.environ.pop("VIBE_MAX_PACKAGES", None)
        self.module = load_module(
            BIN / "vibe_gates.py", "vibe_gates_ap10_%d" % id(self))

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("VIBE_MAX_PACKAGES", None)
        else:
            os.environ["VIBE_MAX_PACKAGES"] = self._old_env
        self.tmp.cleanup()

    def effective(self, project=None):
        args = [str(self.state)]
        if project is not None:
            args.append(str(project))
        return normalize_gates(self.module.effective(*args))

    def test_defaults_without_any_configuration(self):
        self.assertFalse((self.state / "gates.json").exists())

        values, origins, problems = self.effective()

        self.assertEqual(values, dict(DEFAULTS), values)
        self.assertEqual(problems, [], problems)
        for key in GATE_KEYS:
            self.assertEqual(origins.get(key), "Standard", (key, origins))

    def test_global_gates_file_overrides_the_defaults(self):
        (self.state / "gates.json").write_text(
            json.dumps({"repair_rounds": 3, "override": "off"}),
            encoding="utf-8")

        values, origins, problems = self.effective()

        self.assertEqual(values["repair_rounds"], 3, values)
        self.assertEqual(values["override"], "off", values)
        self.assertEqual(origins["repair_rounds"], "global", origins)
        self.assertEqual(origins["override"], "global", origins)
        self.assertEqual(values["retries"], DEFAULTS["retries"], values)
        self.assertEqual(origins["retries"], "Standard", origins)
        self.assertEqual(problems, [], problems)

    def test_project_env_overrides_the_global_gates(self):
        (self.state / "gates.json").write_text(
            json.dumps({"repair_rounds": 3, "retries": 4}), encoding="utf-8")
        project = self.root / "proj"
        (project / ".vibe").mkdir(parents=True)
        (project / ".vibe" / "project.env").write_text(
            "REPAIR_ROUNDS=1\nASSIST_ROUNDS=5\nMAX_RETRIES=3\n"
            "MAX_PACKAGES=9\nGATE_OVERRIDE=off\n",
            encoding="utf-8")

        values, origins, problems = self.effective(project)

        self.assertEqual(
            values,
            {"repair_rounds": 1, "assist_rounds": 5, "retries": 3,
             "packages": 9, "override": "off"},
            values,
        )
        for key in GATE_KEYS:
            self.assertEqual(origins[key], "projekt", (key, origins))
        self.assertEqual(problems, [], problems)

    def test_vibe_max_packages_environment_wins_for_the_package_gate(self):
        (self.state / "gates.json").write_text(
            json.dumps({"packages": 3}), encoding="utf-8")
        os.environ["VIBE_MAX_PACKAGES"] = "4"
        try:
            values, _origins, problems = self.effective()
        finally:
            os.environ.pop("VIBE_MAX_PACKAGES", None)

        self.assertEqual(values["packages"], 4, values)
        self.assertEqual(problems, [], problems)

    def test_defective_values_are_reported_and_kept_at_the_defaults(self):
        (self.state / "gates.json").write_text(
            json.dumps(
                {"repair_rounds": "viel", "assist_rounds": 4,
                 "override": "immer"}),
            encoding="utf-8")
        project = self.root / "proj"
        (project / ".vibe").mkdir(parents=True)
        (project / ".vibe" / "project.env").write_text(
            "MAX_RETRIES=xyz\n", encoding="utf-8")

        values, _origins, problems = self.effective(project)

        self.assertTrue(problems, "Defekte Werte wurden nicht gemeldet.")
        self.assertEqual(values["repair_rounds"], DEFAULTS["repair_rounds"])
        self.assertEqual(values["override"], DEFAULTS["override"])
        self.assertEqual(values["retries"], DEFAULTS["retries"])
        self.assertEqual(values["assist_rounds"], 4, values)

    def test_corrupt_gates_file_is_reported_and_defaults_apply(self):
        (self.state / "gates.json").write_text("{ kaputt\n", encoding="utf-8")

        values, _origins, problems = self.effective()

        self.assertTrue(problems, "Defekte Datei wurde nicht gemeldet.")
        self.assertEqual(values, dict(DEFAULTS), values)

    def test_save_writes_the_global_file_and_validates_the_value(self):
        self.module.save(str(self.state), "repair_rounds", 4)
        data = json.loads(
            (self.state / "gates.json").read_text(encoding="utf-8"))
        self.assertTrue(
            json_contains(data, "repair_rounds", 4)
            or json_contains(data, "repair_rounds", "4"),
            data,
        )

        before = (self.state / "gates.json").read_bytes()
        with self.assertRaises(ValueError):
            self.module.save(str(self.state), "override", "immer")
        with self.assertRaises(ValueError):
            self.module.save(str(self.state), "unbekannt", 1)
        self.assertEqual((self.state / "gates.json").read_bytes(), before)

        self.module.save(str(self.state), "override", "off")
        data = json.loads(
            (self.state / "gates.json").read_text(encoding="utf-8"))
        self.assertTrue(
            json_contains(data, "override", "off"), data)


class GatesCliTest(unittest.TestCase):
    """``vibe gates`` zeigt, setzt und entfernt Schrankenwerte."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.install = self.root / "_toolchain"
        self.runtime = self.root / "_logs"
        self.state = self.root / "_state"
        self.state.mkdir()
        self.project = self.root / "proj"

    def tearDown(self):
        self.tmp.cleanup()

    def make_project_env(self, text="TYPE=generic\n"):
        (self.project / ".vibe").mkdir(parents=True, exist_ok=True)
        (self.project / ".vibe" / "project.env").write_text(
            text, encoding="utf-8")

    def isolated_env(self):
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
                "VIBE": str(self.root),
                "VIBE_NO_CONTAINER": "1",
                "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
                "VIBE_CONFIG_FILE": str(self.root / "config.json"),
                "VIBE_STORAGE_LOCK_DIR": str(self.root / "locks"),
                "VIBE_INSTALL": str(self.install),
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_STATE": str(self.state),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        return env

    def run_cli(self, *args, cwd=None):
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=str(cwd or self.root),
            env=self.isolated_env(),
            capture_output=True,
            text=True,
            timeout=90,
        )

    def real_output(self, result, context=""):
        """Ausgabe ohne die allgemeine Aufrufhilfe.

        Ein unbekannter CLI-Befehl gibt nur die Hilfe aus (und endet mit
        Exit 0). Das ist kein ``vibe gates``-Ergebnis und zählt als
        Fehlschlag, nicht als Status.
        """
        output = result.stdout + result.stderr
        lowered = output.lower()
        self.assertFalse(
            "aufruf:" in lowered or "usage:" in lowered,
            "Nur die allgemeine Aufrufhilfe erhalten (Befehl unbekannt?)"
            "%s:\n%s" % (context, output),
        )
        return output

    def test_status_without_configuration_shows_defaults_and_standard_origin(
        self,
    ):
        result = self.run_cli("gates", "status")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = self.real_output(result)
        self.assertIn("Standard", output, output)
        self.assertIn("80", output, output)
        self.assertIn("ask", output, output)
        self.assertFalse((self.state / "gates.json").exists())

    def test_gates_without_argument_shows_status(self):
        result = self.run_cli("gates")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = self.real_output(result)
        self.assertIn("Standard", output, output)
        self.assertIn("ask", output, output)

    def test_global_gate_is_persisted_and_shown(self):
        result = self.run_cli("gates", "repair_rounds", "3")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.real_output(result, "beim Setzen")
        self.assertTrue(
            (self.state / "gates.json").is_file(),
            "Die globale Einstellung gehört nach <Zustand>/gates.json",
        )
        data = json.loads(
            (self.state / "gates.json").read_text(encoding="utf-8"))
        self.assertTrue(
            json_contains(data, "repair_rounds", 3)
            or json_contains(data, "repair_rounds", "3"),
            data,
        )

        status = self.run_cli("gates", "status")
        output = self.real_output(status)
        self.assertIn("3", output, output)
        self.assertIn("global", output, output)

    def test_project_gate_is_written_to_project_env_and_shown(self):
        self.make_project_env("TYPE=generic\n")

        result = self.run_cli("gates", "--project", "proj", "assist_rounds", "7")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.real_output(result, "beim Projektsetzen")
        text = (self.project / ".vibe" / "project.env").read_text(
            encoding="utf-8")
        self.assertIn("ASSIST_ROUNDS=7", text, text)
        self.assertIn("TYPE=generic", text, text)

        status = self.run_cli("gates", "status", cwd=self.project)
        output = self.real_output(status)
        self.assertIn("7", output, output)
        self.assertIn("projekt", output, output)

    def test_empty_value_removes_the_project_gate(self):
        self.make_project_env("TYPE=generic\n")
        saved = self.run_cli("gates", "--project", "proj", "assist_rounds", "7")
        self.assertEqual(saved.returncode, 0, saved.stdout + saved.stderr)
        self.real_output(saved, "beim Projektsetzen")

        result = self.run_cli(
            "gates", "--project", "proj", "assist_rounds", "")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.real_output(result, "beim Entfernen")
        text = (self.project / ".vibe" / "project.env").read_text(
            encoding="utf-8")
        self.assertNotIn("ASSIST_ROUNDS", text, text)
        self.assertIn("TYPE=generic", text, text)
        status = self.run_cli("gates", "status", cwd=self.project)
        self.assertIn("Standard", self.real_output(status))

    def test_unknown_gate_and_invalid_values_are_rejected_without_writing(
        self,
    ):
        self.make_project_env("TYPE=generic\n")
        before = (self.project / ".vibe" / "project.env").read_bytes()

        for args in (("foo", "2"), ("repair_rounds", "abc"),
                     ("override", "immer")):
            result = self.run_cli("gates", *args)
            self.assertNotEqual(
                result.returncode, 0, "%s: %s" % (args, result.stdout))
        project_result = self.run_cli(
            "gates", "--project", "proj", "assist_rounds", "abc")
        self.assertNotEqual(
            project_result.returncode, 0,
            project_result.stdout + project_result.stderr)

        self.assertFalse(
            (self.state / "gates.json").is_file(),
            "Bei Ablehnung wurde trotzdem global geschrieben.",
        )
        self.assertEqual(
            (self.project / ".vibe" / "project.env").read_bytes(), before,
            "Bei Ablehnung wurde trotzdem ins Projekt geschrieben.",
        )

    def test_override_gate_accepts_off(self):
        result = self.run_cli("gates", "override", "off")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.real_output(result, "beim Setzen")
        status = self.run_cli("gates", "status")
        output = self.real_output(status)
        self.assertIn("off", output, output)
        self.assertIn("global", output, output)

    def test_project_flag_after_status_shows_the_project_values(self):
        """``--project`` nach ``status`` zeigt die Werte dieses Projekts.

        Review-Befund 2: ``--project`` muss an beliebiger Argumentposition
        erkannt sein, insbesondere bei ``vibe gates status --project <p>``.
        """
        self.make_project_env("TYPE=generic\nREPAIR_ROUNDS=5\n")

        result = self.run_cli("gates", "status", "--project", "proj")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = self.real_output(result, "status --project nach status")
        self.assertIn("Projekt: proj", output, output)
        self.assertRegex(output, r"repair_rounds\s+5\s+projekt")

        # Auch die dokumentierte Position vor dem Unterbefehl bleibt gültig.
        before = self.run_cli("gates", "--project", "proj", "status")
        self.assertEqual(
            before.returncode, 0, before.stdout + before.stderr)
        self.assertRegex(
            self.real_output(before, "--project vor status"),
            r"repair_rounds\s+5\s+projekt",
        )

        # Ohne --project bleibt die globale Anzeige unverändert.
        global_result = self.run_cli("gates", "status")
        self.assertEqual(
            global_result.returncode, 0,
            global_result.stdout + global_result.stderr,
        )
        global_output = self.real_output(global_result, "globale Anzeige")
        self.assertNotIn("Projekt: proj", global_output, global_output)
        self.assertRegex(global_output, r"repair_rounds\s+2\s+Standard")

    def test_corrupt_gates_file_is_reported_with_defaults(self):
        (self.state / "gates.json").write_text("{ kaputt\n", encoding="utf-8")

        result = self.run_cli("gates", "status")

        output = self.real_output(result).lower()
        self.assertTrue(
            any(marker in output for marker in INVALID_MARKERS), output)
        self.assertIn("standard", output, output)
        self.assertIn("80", output, output)


class RunnerFixture(unittest.TestCase):
    """Gemeinsame Umgebung: Repository, Installation, opencode-Attrappe."""

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
        self.state = self.root / "state"
        self.state.mkdir()
        self.fakebin = support.install_fake_tools(self.root)
        self.calls = self.root / "calls.log"
        self.counter = self.root / "counter"
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

    # -- Umgebung -----------------------------------------------------------
    def write_gates(self, **gates):
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / "gates.json").write_text(
            json.dumps(gates), encoding="utf-8")

    def make_project(self, env_text, feedback=FEEDBACK_ONE):
        project = self.root / "proj"
        support.init_repo(project)
        support.write_project(project, env_text, feedback=feedback)
        support.commit_all(project, "Ausgangsstand")
        self.project = project
        return project

    def env(self, **extra):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_") \
                    or key.startswith("SANDBOX"):
                env.pop(key, None)
        for key in (
            "AGENT", "MAX_PACKAGES", "MAX_RETRIES", "REPAIR_ROUNDS",
            "ASSIST_ROUNDS", "GATE_OVERRIDE", "VERIFY_FULL", "VERIFY_PACKAGE",
            "TYPE",
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
                "VIBE_RETRY_DELAY": "0",
                "VIBE_PREFLIGHT_QUESTION_TIMEOUT": "15",
                "VIBE_STORAGE_LOCK_DIR": str(self.home / "locks"),
                "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
                "PATH": str(self.fakebin) + os.pathsep
                        + os.environ.get("PATH", ""),
                "FAKE_CALLS": str(self.calls),
                "FAKE_COUNTER": str(self.counter),
            }
        )
        env.update({key: str(value) for key, value in extra.items()})
        return env

    def run_runner(self, project, **extra):
        return subprocess.run(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(project)],
            cwd=str(project),
            env=self.env(**extra),
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
            env=self.env(**extra),
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return self.proc

    # -- Beobachtung --------------------------------------------------------
    def output(self):
        if self.out_path is None or not self.out_path.exists():
            return ""
        return self.out_path.read_text(encoding="utf-8", errors="replace")

    def log(self, project=None):
        project = project or self.project
        path = self.runtime / (project.name + ".log")
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def combined(self, result, project=None):
        return result.stdout + result.stderr + "\n" + self.log(project)

    def call_lines(self):
        if not self.calls.exists():
            return []
        return self.calls.read_text(encoding="utf-8").splitlines()

    def note_block(self, project, pid):
        """Ticketdatensatz dieser Kennung aus dem GH-48-Speicher."""
        path = project / ".vibe" / "tickets.json"
        if not path.is_file():
            return {}
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        for item in document.get("tickets") or []:
            if item.get("id") == pid:
                return item
        return {}

    # -- Rückfragen (F16) ---------------------------------------------------
    def question_records(self):
        folder = self.runtime / "questions"
        result = []
        if not folder.is_dir():
            return result
        for path in sorted(folder.glob("*.json")):
            if path.name.endswith(".answer.json"):
                continue
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(record, dict) and record.get("id"):
                result.append(record)
        return result

    def open_questions(self):
        folder = self.runtime / "questions"
        return [
            record for record in self.question_records()
            if not (folder / (record["id"] + ".answer.json")).exists()
        ]

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
        folder = self.runtime / "questions"
        folder.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "option": option,
                "option_text": (record.get("options") or [None, None, None])[
                    option] if option is not None else None,
                "text": text,
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "by": "test",
            },
            ensure_ascii=False,
        ) + "\n"
        target = folder / (record["id"] + ".answer.json")
        temporary = folder / (".answer-" + record["id"] + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, target)

    def wait_exit(self, timeout=90):
        try:
            return self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
            raise AssertionError(
                "Läufer lief nach %s s weiter.\n%s" % (timeout, self.output())
            )

    def wait_exit_refusing_questions(self, seen=(), timeout=90):
        """Wartet auf das Ende; jede neue Rückfrage ist ein Testfehler."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for record in self.open_questions():
                if record["id"] not in seen:
                    self.fail(
                        "Es wurde eine Rückfrage gestellt: "
                        + repr(record.get("text", "")))
            if self.proc.poll() is not None:
                return self.proc.returncode
            time.sleep(0.05)
        self.proc.kill()
        self.proc.wait()
        raise AssertionError(
            "Läufer lief nach %s s weiter.\n%s" % (timeout, self.output()))


class RunnerGateWiringTest(RunnerFixture):
    """AP10-1: Der Läufer liest die wirksamen Schranken."""

    def test_runner_uses_the_global_repair_rounds_gate(self):
        self.write_gates(repair_rounds=1)
        project = self.make_project(
            env_text=write_project_env_text(override="off"),
            feedback=FEEDBACK_ONE,
        )

        result = self.run_runner(
            project, FAKE_MODE="no-artifacts", VIBE_MAX_PACKAGES="1")

        combined = self.combined(result, project)
        self.assertEqual(result.returncode, 1, combined)
        self.assertEqual(len(self.call_lines()), 2, self.call_lines())
        self.assertIn("nach 1 Runden", combined, combined)

    def test_project_repair_rounds_override_the_global_gate(self):
        self.write_gates(repair_rounds=1)
        project = self.make_project(
            env_text=write_project_env_text(override="off", repair_rounds=3),
            feedback=FEEDBACK_ONE,
        )

        result = self.run_runner(
            project, FAKE_MODE="no-artifacts", VIBE_MAX_PACKAGES="1")

        combined = self.combined(result, project)
        self.assertEqual(result.returncode, 1, combined)
        self.assertEqual(len(self.call_lines()), 4, self.call_lines())
        self.assertIn("nach 3 Runden", combined, combined)

    def test_global_packages_gate_limits_the_run_without_env_or_project(self):
        self.write_gates(packages=1)
        project = self.make_project(
            env_text=write_project_env_text(), feedback=FEEDBACK_TWO)

        # Kein VIBE_MAX_PACKAGES, kein MAX_PACKAGES im Projekt: die globale
        # Schranke entscheidet.
        result = self.run_runner(project, FAKE_MODE="complete")

        combined = self.combined(result, project)
        self.assertEqual(result.returncode, 0, combined)
        self.assertEqual(len(self.call_lines()), 1, self.call_lines())
        self.assertIn("Durchgang 1/1", self.log(project), self.log(project))

    def test_vibe_max_packages_environment_still_wins_over_the_global_gate(
        self,
    ):
        """Charakterisierung: bestehende Priorität der Umgebungsvariable."""
        self.write_gates(packages=1)
        project = self.make_project(
            env_text=write_project_env_text(packages=9), feedback=FEEDBACK_TWO)

        result = self.run_runner(
            project, FAKE_MODE="complete", VIBE_MAX_PACKAGES="1")

        self.assertEqual(result.returncode, 0, self.combined(result, project))
        self.assertEqual(len(self.call_lines()), 1, self.call_lines())

    def test_global_retries_gate_limits_the_attempts(self):
        self.write_gates(retries=1)
        project = self.make_project(
            env_text=write_project_env_text(), feedback=FEEDBACK_TWO)

        result = self.run_runner(
            project, FAKE_MODE_SEQUENCE="fail,fail,complete",
            VIBE_MAX_PACKAGES="2")

        combined = self.combined(result, project)
        self.assertEqual(result.returncode, 0, combined)
        self.assertEqual(len(self.call_lines()), 3, self.call_lines())
        self.assertIn(
            "Überspringe F1 nach 2 Versuchen", self.log(project),
            self.log(project))
        self.assertIn("Blockiert: F1", combined, combined)
        self.assertIn("Geschlossen: F2", combined, combined)

    def test_assist_rounds_gate_limits_the_preflight_rounds(self):
        project = self.make_project(
            env_text=write_project_env_text(assist_rounds=1),
            feedback=FEEDBACK_ONE,
        )
        (project / "unfertig.txt").write_text("unfertig\n", encoding="utf-8")

        self.start_runner(project, VIBE_PREFLIGHT_ASSIST="1")
        first = self.wait_for_question()
        self.assertEqual(first.get("options"), PREFLIGHT_OPTIONS, first)
        self.answer(first, 2)

        rc = self.wait_exit_refusing_questions({first["id"]}, timeout=60)

        self.assertEqual(rc, 2, self.output())
        preflight_calls = [
            line for line in self.call_lines() if line.startswith("preflight")
        ]
        self.assertEqual(len(preflight_calls), 1, self.call_lines())

    def test_global_override_off_blocks_without_question(self):
        """Schutz: ``override=off`` global stellt keine Rückfrage."""
        self.write_gates(override="off")
        project = self.make_project(
            env_text=write_project_env_text(), feedback=FEEDBACK_TWO)

        result = self.run_runner(
            project, FAKE_MODE="no-artifacts", VIBE_MAX_PACKAGES="2")

        combined = self.combined(result, project)
        self.assertEqual(result.returncode, 1, combined)
        self.assertEqual(len(self.call_lines()), 3, self.call_lines())
        self.assertEqual(self.question_records(), [], self.question_records())
        self.assertIn("Blockiert: F1", combined, combined)

    def test_merge_package_keeps_uncommitted_agents_md_out_of_the_package(self):
        """GH-48: AGENTS.md ist die verbleibende Arbeitsnotiz.

        Eine uncommittete Änderung an AGENTS.md gehört dem Nutzer: Sie wird
        nicht in die Arbeitskopie übernommen (HINWEIS), der Merge geht durch,
        und der lokale Stand bleibt erhalten. Die frühere Ledger-Datei
        TICKETS.md ist ein normales Projektfile und daher kein Sonderfall
        mehr.
        """
        project = self.make_project(
            env_text=write_project_env_text(), feedback=FEEDBACK_ONE)
        agents = project / "AGENTS.md"
        agents.write_text("# Regeln\n", encoding="utf-8")
        support.commit_all(project, "Regeln")
        agents.write_text("# Regeln\nManuell ergänzt\n", encoding="utf-8")

        result = self.run_runner(
            project, FAKE_MODE="complete", VIBE_MAX_PACKAGES="1")

        combined = self.combined(result, project)
        log = self.log(project)
        self.assertEqual(result.returncode, 0, combined)
        self.assertIn("Geschlossen: F1", log, log)
        self.assertIn("AGENTS.md hat nicht committete Änderungen", log, log)
        self.assertNotIn(
            "Uncommittete Änderungen an Arbeitsnotizen werden für den "
            "Merge verworfen", log, log)
        merged = support.git(project, "show", "HEAD:AGENTS.md").stdout
        self.assertNotIn("Manuell ergänzt", merged, merged)
        self.assertIn("Manuell ergänzt",
                      agents.read_text(encoding="utf-8"))
        self.assertEqual(
            support.git(
                project, "cat-file", "-e", "HEAD:impl-F1.txt").returncode,
            0,
            "Der Merge ist trotz uncommitteter Arbeitsnotiz nicht "
            "durchgegangen.",
        )

    def test_merge_without_note_changes_logs_no_discard_warning(self):
        """Regression: Sauberer Stand erzeugt keinen Fehlalarm."""
        project = self.make_project(
            env_text=write_project_env_text(), feedback=FEEDBACK_TWO)

        result = self.run_runner(
            project, FAKE_MODE="complete", VIBE_MAX_PACKAGES="2")

        combined = self.combined(result, project)
        log = self.log(project)
        self.assertEqual(result.returncode, 0, combined)
        self.assertIn("Geschlossen: F1", log, log)
        self.assertIn("Geschlossen: F2", log, log)
        self.assertNotIn(
            "Uncommittete Änderungen an Arbeitsnotizen", log, log)


class BarrierInterfaceTest(unittest.TestCase):
    """AP10-2: Die Schranken-Rückfrage ist in ``vibe_packages`` verfügbar."""

    def test_assist_barrier_is_available_in_vibe_packages(self):
        module = load_module(
            BIN / "vibe_packages.py", "vibe_packages_ap10_barrier")
        self.assertTrue(
            callable(getattr(module, "assist_barrier")),
            "assist_barrier fehlt in bin/vibe_packages.py",
        )


class BarrierDecisionTest(RunnerFixture):
    """AP10-2: Bewusstes Fortsetzen an der Schranke (Nutzerentscheidung)."""

    def test_project_override_off_blocks_immediately_without_question(self):
        project = self.make_project(
            env_text=write_project_env_text(override="off"),
            feedback=FEEDBACK_TWO,
        )

        result = self.run_runner(
            project, FAKE_MODE="no-artifacts", VIBE_MAX_PACKAGES="2")

        combined = self.combined(result, project)
        self.assertEqual(result.returncode, 1, combined)
        self.assertEqual(len(self.call_lines()), 3, self.call_lines())
        self.assertEqual(self.question_records(), [], self.question_records())
        self.assertIn("Blockiert: F1", combined, combined)

    def test_repair_limit_asks_and_skip_continues_with_the_next_package(self):
        project = self.make_project(
            env_text=write_project_env_text(), feedback=FEEDBACK_TWO)

        self.start_runner(
            project,
            FAKE_MODE_SEQUENCE="no-artifacts,no-artifacts,no-artifacts,complete",
            VIBE_MAX_PACKAGES="2",
        )
        record = self.wait_for_question()
        self.assertEqual(
            sorted(record.get("options") or []), sorted(GATE_OPTIONS),
            record)
        self.assertIn("F1", record.get("text") or "", record)
        options = record.get("options") or []
        self.answer(record, options.index("Paket überspringen und Lauf "
                                          "fortsetzen"))
        rc = self.wait_exit(timeout=90)

        output = self.output() + "\n" + self.log(project)
        self.assertEqual(rc, 0, output)
        self.assertEqual(len(self.call_lines()), 4, self.call_lines())
        self.assertIn("Geschlossen: F2", output, output)
        self.assertIn("Blockiert: F1", output, output)
        note = self.note_block(project, "F1")
        self.assertEqual("blocked", note.get("state"), note)
        reason = str(note.get("blocked_reason") or "")
        self.assertTrue(reason, note)
        self.assertTrue(
            re.search(r"(?i)nutzerentscheidung|übersprungen", reason + output),
            "Der Vermerk nennt die Nutzerentscheidung nicht:\n%s" % note,
        )
        self.assertNotEqual(
            support.git(project, "cat-file", "-e", "HEAD:impl-F1.txt").returncode,
            0,
            "F1 wurde trotz fehlenden Nachweises gemergt.",
        )

    def test_abort_option_keeps_the_previous_block_behaviour(self):
        project = self.make_project(
            env_text=write_project_env_text(override="ask"),
            feedback=FEEDBACK_TWO,
        )

        self.start_runner(
            project,
            FAKE_MODE_SEQUENCE="no-artifacts,no-artifacts,no-artifacts,complete",
            VIBE_MAX_PACKAGES="2",
        )
        record = self.wait_for_question()
        self.answer(record, record["options"].index("Lauf abbrechen"))
        rc = self.wait_exit(timeout=90)

        output = self.output() + "\n" + self.log(project)
        self.assertEqual(rc, 1, output)
        self.assertEqual(len(self.call_lines()), 3, self.call_lines())
        self.assertIn("Blockiert: F1", output, output)
        self.assertNotIn("Geschlossen: F2", output, output)
        self.assertNotIn("Geschlossen: F1", output, output)

    def test_agent_option_runs_one_more_repair_round_and_rechecks(self):
        project = self.make_project(
            env_text=write_project_env_text(), feedback=FEEDBACK_ONE)

        self.start_runner(
            project,
            FAKE_MODE_SEQUENCE="no-artifacts,no-artifacts,no-artifacts,complete",
            VIBE_MAX_PACKAGES="1",
        )
        record = self.wait_for_question()
        self.answer(record, record["options"].index("Agent behebt die Befunde"))
        rc = self.wait_exit(timeout=90)

        output = self.output() + "\n" + self.log(project)
        self.assertEqual(rc, 0, output)
        self.assertEqual(len(self.call_lines()), 4, self.call_lines())
        self.assertIn("Geschlossen: F1", output, output)
        self.assertEqual(
            support.git(project, "cat-file", "-e", "HEAD:impl-F1.txt").returncode,
            0,
            "Die zusätzliche Reparatur wurde nicht übernommen.",
        )

    def test_each_further_repair_round_requires_a_new_decision(self):
        project = self.make_project(
            env_text=write_project_env_text(), feedback=FEEDBACK_ONE)

        self.start_runner(
            project, FAKE_MODE="no-artifacts", VIBE_MAX_PACKAGES="1")
        first = self.wait_for_question()
        self.answer(first, first["options"].index("Agent behebt die Befunde"))

        second = self.wait_for_question({first["id"]})
        self.assertNotEqual(first["id"], second["id"])
        self.answer(second, second["options"].index("Lauf abbrechen"))
        rc = self.wait_exit(timeout=90)

        output = self.output() + "\n" + self.log(project)
        self.assertEqual(rc, 1, output)
        self.assertEqual(len(self.call_lines()), 4, self.call_lines())
        self.assertNotIn("Geschlossen: F1", output, output)

    def test_autonomous_mode_skips_without_asking(self):
        project = self.make_project(
            env_text=write_project_env_text(), feedback=FEEDBACK_TWO)
        self.runtime.mkdir(parents=True, exist_ok=True)
        (self.runtime / "autonomous.json").write_text(
            json.dumps(
                {"version": 1,
                 "projects": {"proj": {"enabled": True, "changed": "test"}}},
                ensure_ascii=False),
            encoding="utf-8")

        self.start_runner(
            project,
            FAKE_MODE_SEQUENCE="no-artifacts,no-artifacts,no-artifacts,complete",
            VIBE_MAX_PACKAGES="2",
        )
        rc = self.wait_exit_refusing_questions(timeout=90)

        output = self.output() + "\n" + self.log(project)
        self.assertEqual(rc, 0, output)
        self.assertEqual(len(self.call_lines()), 4, self.call_lines())
        self.assertIn("Geschlossen: F2", output, output)
        self.assertIn("Blockiert: F1", output, output)
        self.assertTrue(
            re.search(r"(?i)autonom", output),
            "Die autonome Entscheidung wird nicht dokumentiert:\n%s" % output,
        )

    def test_unanswered_barrier_question_aborts_like_before(self):
        project = self.make_project(
            env_text=write_project_env_text(), feedback=FEEDBACK_TWO)

        result = self.run_runner(
            project, FAKE_MODE="no-artifacts", VIBE_MAX_PACKAGES="2",
            VIBE_PREFLIGHT_QUESTION_TIMEOUT="2")

        combined = self.combined(result, project)
        self.assertEqual(result.returncode, 1, combined)
        self.assertEqual(len(self.call_lines()), 3, self.call_lines())
        self.assertGreaterEqual(
            len(self.question_records()), 1,
            "Die Rückfrage wurde nicht gestellt: %s" % self.question_records())
        self.assertIn("Blockiert: F1", combined, combined)

    def test_without_question_modules_the_run_aborts_like_before(self):
        (self.tool_bin / "vibe_questions.py").unlink()
        (self.tool_bin / "vibe_autonomous.py").unlink()
        project = self.make_project(
            env_text=write_project_env_text(), feedback=FEEDBACK_TWO)

        result = self.run_runner(
            project, FAKE_MODE="no-artifacts", VIBE_MAX_PACKAGES="2")

        combined = self.combined(result, project)
        self.assertEqual(result.returncode, 1, combined)
        self.assertEqual(len(self.call_lines()), 3, self.call_lines())
        self.assertEqual(self.question_records(), [], self.question_records())
        self.assertIn("Blockiert: F1", combined, combined)


if __name__ == "__main__":
    unittest.main()
