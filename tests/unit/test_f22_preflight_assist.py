"""F22: Ein nicht bestandener Preflight führt über F16 zu einer Rückfrage.

Die Tests leiten das Verhalten aus dem Arbeitspaket und ``SPEC.md`` ab, nicht
aus dem Implementierungsdiff. Geprüft werden:

* Der direkte Aufruf von ``bin/vibe-run.sh`` ohne ``VIBE_PREFLIGHT_ASSIST``
  hält am bisherigen Verhalten fest (Abbruch ohne Rückfrage).
* ``vibe run`` startet den Läufer mit ``VIBE_PREFLIGHT_ASSIST=1``.
* Bei aktivierter Assistenz legt der Läufer eine F16-Rückfrage mit Projekt,
  konkreten Befunden und genau den drei Optionen „Erneut prüfen“, „Lauf
  abbrechen“ und „Agent behebt die Befunde“ an; eine freie Antwort wird als
  Anweisung an den Agenten verstanden, der die Befunde im Projektordner
  beheben soll.
* Eine freie Antwort beauftragt den konfigurierten Agenten im Projektordner;
  nach einem erfolgreichen Agentenlauf wird der Preflight erneut geprüft. Ein
  fehlgeschlagener Agentenlauf beendet den Lauf mit Exit-Code 2, ohne ein
  Arbeitspaket zu starten. Die Assistenz ist auf zehn Agentenrunden begrenzt.
* „Erneut prüfen“ prüft erneut. Ist der Befund behoben, startet das erste
  Arbeitspaket; bleibt er bestehen, folgt eine neue Rückfrage.
* „Lauf abbrechen“ beendet den Lauf mit Exit-Code 2, ohne Agentenaufruf, und
  markiert ein vorhandenes Laufregister als ``blocked``.
* Ohne Antwort endet der Lauf nach ``VIBE_PREFLIGHT_QUESTION_TIMEOUT`` mit
  Exit-Code 2; die Rückfrage bleibt offen und der Abbruchgrund nennt ihre ID.
* Der autonome Modus (F16) verhindert die Rückfrage bzw. beendet laufendes
  Warten sofort. Statt abzubrechen, beauftragt der Läufer den Agenten einmal
  mit einer aus den Befunden abgeleiteten Anweisung. Ist der Befund danach
  behoben, startet das erste Arbeitspaket; andernfalls blockiert der Lauf mit
  den verbleibenden Befunden.
* Ein erfolgreicher Preflight erzeugt keine Rückfrage.
* Bei mehreren Befunden wird zuerst der erste gefragt, danach der nächste
  noch bestehende Befund als eigene Rückfrage.
* Eine unlesbare oder eine nicht angebotene Antwort auf die Rückfrage beendet
  den Lauf mit Exit-Code 2 und einer klaren Meldung statt mit Traceback oder
  einer stillschweigenden erneuten Prüfung.

Es werden keine Modelle, Router oder echten externen Dienste aufgerufen. Der
Agent, ``curl`` und die vibe-CLI sind Attrappen; alle Pfade liegen in einem
temporären Verzeichnis.
"""
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

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"

PROJECT_ENV = """TYPE=generic
AGENT=tester
TESTER=test-agent
REVIEWER=code-reviewer
VERIFY_PACKAGE="true"
VERIFY_FULL="true"
"""

FEEDBACK = "- [ ] F1 Erstes Paket\n  Beschreibung: Test\n"


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
            ensure_general_rules=lambda project: False,
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


if __name__ == "__main__":
    unittest.main()
