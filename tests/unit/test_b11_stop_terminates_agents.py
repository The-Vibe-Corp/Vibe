"""Unabhängige Tests B11/1: Stopp beendet den Agenten wirklich.

Die Fälle sind aus dem Arbeitspaket B11 („stop button … agents still
continue (this is a no go)") und aus ``SPEC.md`` („Agentenläufe und
Prüfungen") abgeleitet, nicht aus einem Implementierungsdiff. Geprüft wird
das beobachtbare Verhalten, nicht ein bestimmter Aufbau des Läufers.

Der Fehler: ``tmux kill-session`` sendet HUP an die Prozessgruppe der Pane.
Der Läufer fängt HUP/TERM/INT, beendet aber nur Protokoll und Register; der
Agentenprozess lebt weiter. Zusätzlich verschiebt bash einen Trap während
einer Vordergrund-Pipeline, bis der laufende Befehl endet. Ein Harness, der
HUP ignoriert, überlebt daher als Waise.

Testfälle
---------
``StopKillsAgentTest.test_hup_stop_kills_agent_that_ignores_hup`` (AK1)
    Vorbedingung: echter Läufer bearbeitet ein Paket; der als ``opencode``
    eingetragene Harness ignoriert HUP und startet einen Unterprozess samt
    Enkelprozess. Aktion: HUP an die Prozessgruppe des Laufs. Erwartung:
    Läufer, Harness, Unter- und Enkelprozess sind innerhalb weniger Sekunden
    beendet; es entstehen keine weiteren Ticks.
``StopKillsAgentTest.test_term_stop_kills_agent_that_ignores_term`` (AK1)
    Vorbedingung wie oben, der Harness ignoriert TERM. Aktion: TERM an die
    Prozessgruppe. Erwartung wie oben.
``StopKillsAgentTest.test_hup_stop_kills_agent_that_ignores_hup_and_term`` (AK1)
    Vorbedingung: Harness ignoriert HUP und TERM gleichzeitig (schlimmster
    Fall). Aktion: HUP. Erwartung: alle Prozesse enden (KILL-Eskalation).
``SignalRegistryTest.test_signal_stop_marks_the_run_ended_with_signal_note``
    (AK2, AK3) Vorbedingung: laufender Lauf mit signalignorierendem Harness.
    Aktion: HUP an die Prozessgruppe. Erwartung: Registerzustand ``ended``
    (nie ``running``), Notiz ``extern beendet (Signal HUP)``, Exit-Code 129,
    Protokollzeile ``ABBRUCH: Lauf extern beendet (Signal HUP).``.
``SignalRegistryTest.test_signal_stop_leaves_an_already_finished_record``
    (AK2) Vorbedingung: Registereintrag wurde extern auf ``finished``
    gesetzt. Aktion: HUP. Erwartung: Eintrag bleibt ``finished`` ohne
    Signalnotiz; alle Prozesse enden trotzdem.
``NormalRunBehaviourTest.test_regular_harness_keeps_signal_end_and_log_line``
    (AK3, grüner Anker) Vorbedingung: Harness mit regulärer
    Signalbehandlung. Aktion: HUP an die Prozessgruppe. Erwartung: Läufer
    endet wie bisher mit 129, Protokollzeile und Registernotiz bleiben,
    keine Prozesse überleben.
``NormalRunBehaviourTest.test_agent_exit_code_comes_from_the_harness``
    (AK3, grüner Anker) Vorbedingung: Harness endet regulär mit Exit-Code 7.
    Aktion: Lauf ohne Signal bis zum Ende. Erwartung: Protokoll nennt
    ``=== Agent beendet, Exit-Code 7 ===``, die Fehlerklasse und das
    Überspringen des Pakets — der Pipeline-Exitcode (tee) wird nicht
    verwendet.
``StopEndpointRealTmuxTest.test_stop_command_ends_the_run_and_shows_no_active_agent``
    (AK1, AK2, AK4) Vorbedingung: echter Lauf in einer echten tmux-Sitzung
    (eigener Socket, isoliertes ``TMUX_TMPDIR``) mit signalignorierendem
    Harness; Registereintrag ``running``. Aktion: ``vibe stop proj`` (wie
    ``/api/stop``). Erwartung: Erfolgsmeldung und Exit-Code 0, Sitzung
    beendet, alle Prozesse tot, Register nicht ``running``, ``run_state``
    meldet ``running == False`` (Projektansicht ohne aktiven Agenten).
``PreflightAssistStopTest.test_hup_during_preflight_assist_ends_the_agent_group``
    (AK1, Review Medium 1) Vorbedingung: unsauberes Projekt, Preflight-
    Assistenz aktiv, Preflight-Agent (signalignorierend, mit Unter- und
    Enkelprozess) läuft; noch kein Registereintrag. Aktion: HUP an die
    Läufersitzung. Erwartung: Agentengruppe samt Unter-/Enkelprozess endet;
    kein Eintrag bleibt ``running``.
``EndPreflightAssistStopTest.test_hup_during_the_end_preflight_marks_the_run_ended``
    (AK1/AK2, Review Medium 1) Vorbedingung: Lauf registriert, Paket
    abgeschlossen, end-Preflight-Assistenz mit signalignorierendem Agenten.
    Aktion: HUP. Erwartung: Agentengruppe endet; Eintrag ``ended`` mit Notiz
    „extern beendet (Signal HUP)“, Exit-Code 129.
``StopAroundStartTest.test_repeated_hup_around_the_attempt_start_leaves_no_orphan``
    (AK1, Review Medium 2) Vorbedingung: laufender Lauf; das Spawn-Fenster
    selbst ist nicht steuerbar. Aktion: HUP unmittelbar nach der
    Versuchstart-Marke, vier Wiederholungen mit Verzug 0/20/50/200 ms.
    Erwartung: nie eine verwaiste Agentengruppe.
``StopAgentGroupFallbackTest.test_hup_trap_with_unassigned_agent_pid_kills_the_running_job``
    (AK1, Review Medium 2, Runde 2) Vorbedingung: die echte
    ``stop_agent_group``-Funktion des Läufers; Jobkontrolle aktiv; ein
    signalignorierender Auftrag läuft in eigener Prozessgruppe; ``AGENT_PID``
    ist noch leer (Rennfenster-Simulation zwischen Auftragsstart und
    Zuweisung). Aktion: Der HUP-Trap — wie der Läufer-Trap im Fenster — ruft
    ``stop_agent_group`` in dieser Lage. Erwartung: Die Auftragsguppe endet
    vollständig (TERM-Eskalation bis KILL). Fehlerfall: Der Auftrag läuft
    als Waise weiter.
``StopAgentGroupFallbackTest.test_stop_with_unassigned_agent_pid_and_no_jobs_is_harmless``
    (AK1) Vorbedingung: leere ``AGENT_PID``-Kennung, keine
    Hintergrundaufträge. Aktion: direkter Aufruf von ``stop_agent_group``.
    Erwartung: wirkungslos und fehlerfrei; die aufrufende Shell bleibt
    unangetastet.
``StopAgentGroupFallbackTest.test_stop_with_assigned_agent_pid_kills_that_group``
    (AK1) Vorbedingung: ``AGENT_PID`` ist der laufende Auftrag. Aktion:
    direkter Aufruf. Erwartung: die Gruppe endet trotz ignorierter
    Signale; der Normalpfad bleibt intakt.

Es werden keine Modelle, Netze, OAuth-Anmeldungen oder produktiven
HOME-/VIBE-Konfigurationen verwendet. Der Dummy-Harness liegt unter
``tests/unit/runner_fixtures/``.
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"
RUNS = BIN / "vibe_runs.py"
FIXTURES = Path(__file__).resolve().parent / "runner_fixtures"

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(BIN))
import runner_support as support

# Großzügige Obergrenze: der Stopp muss „innerhalb weniger Sekunden“ greifen.
STOP_TIMEOUT = 12.0


def load_module(path, name):
    """Lädt ein Python-Modul aus einer Datei ohne Seiteneffekte auf sys.path."""
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def pid_alive(pid):
    """True, solange der Prozess existiert und nicht Zombie/beendet ist."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return False
    fields = stat.rsplit(") ", 1)[-1].split()
    return bool(fields) and fields[0] not in ("Z", "X", "x")


def extract_shell_function(path, name):
    """Liest eine Funktion aus einem Shell-Skript (Header bis schließende Klammer).

    Die fokussierten Rennfenster-Fälle führen die echte Funktion des
    Läufers aus; eine kopierte Nachbildung würde das geprüfte Verhalten
    nur behaupten, nicht prüfen.
    """
    text = path.read_text(encoding="utf-8")
    header = name + "() {"
    start = text.index(header)
    end = text.index("\n}", start)
    return text[start:end + 2]


class RunnerProcessFixture(unittest.TestCase):
    """Startet den echten Läufer mit einem signalignorierenden Harness."""

    ignore = "HUP,TERM"

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
        self.project = self.root / "proj"
        support.init_repo(self.project)
        self.fixture = self.root / "fixture"
        self.fixture.mkdir()
        self.fakebin = support.install_fake_tools(self.root)
        self.install_harness()
        self.process = None
        self.pgid = None
        self.write_project()

    def tearDown(self):
        process = getattr(self, "process", None)
        if process is not None and process.poll() is None:
            try:
                os.killpg(self.pgid or process.pid, signal.SIGKILL)
            except OSError:
                pass
        if process is not None:
            try:
                process.communicate(timeout=10)
            except (subprocess.TimeoutExpired, ValueError, OSError):
                pass
        for pid in self.recorded_pids().values():
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        self.tmp.cleanup()

    def install_harness(self):
        """Legt den signalignorierenden Harness als ``opencode`` in den PATH."""
        for name in ("b11_harness.py", "b11_child.py", "b11_grandchild.py"):
            target = self.fakebin / name
            target.write_text(
                (FIXTURES / name).read_text(encoding="utf-8"), encoding="utf-8"
            )
            target.chmod(0o755)
        opencode = self.fakebin / "opencode"
        opencode.write_text(
            (FIXTURES / "b11_harness.py").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        opencode.chmod(0o755)

    def write_project(self):
        """Projekt mit genau einem offenen Arbeitspaket und erlaubten Agenten."""
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
                "F1", "Erstes Paket", type="feedback",
                description="Test")],
        )
        support.commit_all(self.project, "Ausgangsstand")

    def isolated_env(self):
        """Umgebung ohne persönliche VIBE-, Sandbox- oder Prüfwerte."""
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE_") or key.startswith("SANDBOX") or key in (
                "VIBE",
                "AGENT",
                "TYPE",
                "VERIFY_QUICK",
                "VERIFY_FULL",
                "B11_FIXTURE_DIR",
                "B11_IGNORE",
                "B11_CHILD",
                "B11_EXIT_AFTER",
                "B11_EXIT_CODE",
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

    def runner_env(self, **extra):
        """Umgebung des Läufers; optionale Fixture-Werte überschreiben."""
        env = self.isolated_env()
        env.update(
            {
                "VIBE_AGENTS_DIR": str(self.agents),
                "VIBE_MAX_PACKAGES": "1",
                "VIBE_RETRY_DELAY": "0",
                "VIBE_LOGNAME": "proj",
                "B11_FIXTURE_DIR": str(self.fixture),
                "B11_IGNORE": self.ignore,
                "PATH": str(self.fakebin)
                + os.pathsep
                + os.environ.get("PATH", ""),
            }
        )
        env.update({key: str(value) for key, value in extra.items()})
        return env

    def start_runner(self, **fixture_env):
        """Startet den echten Läufer als eigene Sitzung (eigene Prozessgruppe)."""
        self.fixture_env = {
            key: str(value)
            for key, value in {**{"B11_CHILD": "1"}, **fixture_env}.items()
        }
        self.process = subprocess.Popen(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(self.project)],
            cwd=str(self.project),
            env=self.runner_env(**fixture_env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        self.pgid = os.getpgid(self.process.pid)
        return self.process

    def start_hanging_runner(self, **fixture_env):
        """Startet den Läufer und wartet, bis Harness und Enkelprozess laufen."""
        self.start_runner(**fixture_env)
        self.wait_for_start()
        return self.process

    def wait_for_start(self, timeout=40):
        """Wartet auf PID-Dateien und einen laufenden Registereintrag."""
        expected = ["harness.pid"]
        if getattr(self, "fixture_env", {}).get("B11_CHILD", "1") != "0":
            expected += ["child.pid", "grandchild.pid"]
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if all((self.fixture / name).exists() for name in expected):
                record = self.record()
                if record and record.get("state") in ("starting", "running"):
                    return
            if self.process is not None and self.process.poll() is not None:
                output = self.process.stdout.read() if self.process.stdout else ""
                self.fail(
                    "Der Läufer endete vor dem Agentenstart (Exit "
                    f"{self.process.returncode}):\n{output}\n{self.log_text()}"
                )
            time.sleep(0.05)
        self.fail(
            "Der Läufer hat keinen Agenten gestartet.\nLog:\n" + self.log_text()
        )

    def recorded_pids(self):
        """Alle vom Harness gemeldeten PIDs (nur vorhandene Dateien)."""
        found = {}
        for name in ("harness.pid", "child.pid", "grandchild.pid"):
            path = self.fixture / name
            try:
                value = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if value.isdigit():
                found[name.removesuffix(".pid")] = int(value)
        return found

    def live_pids(self):
        return {
            label: pid
            for label, pid in self.recorded_pids().items()
            if pid_alive(pid)
        }

    def tick_sizes(self):
        sizes = {}
        for path in sorted(self.fixture.glob("*.tick")):
            try:
                sizes[path.name] = path.stat().st_size
            except OSError:
                sizes[path.name] = -1
        return sizes

    def log_text(self):
        path = self.runtime / "proj.log"
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def registry(self):
        return load_module(RUNS, "vibe_b11_runs_under_test").RunRegistry(
            str(self.runtime)
        )

    def record(self):
        try:
            return self.registry().latest(project=str(self.project.resolve()))
        except (OSError, ValueError):
            return None

    def stop_and_expect_death(
        self, signum, name, timeout=STOP_TIMEOUT, send=True
    ):
        """Sendet ``signum`` an die Laufgruppe und prüft das vollständige Ende.

        Mit ``send=False`` wurde das Signal bereits außerhalb gesendet
        (zeitgesteuerte Fälle); die Prüfung ist identisch.
        """
        if send:
            try:
                os.killpg(self.pgid, signum)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None and not self.live_pids():
                break
            time.sleep(0.05)
        runner_alive = self.process.poll() is None
        survivors = self.live_pids()
        before = self.tick_sizes()
        time.sleep(0.3)
        after = self.tick_sizes()
        output = ""
        if not runner_alive:
            try:
                output = self.process.stdout.read() if self.process.stdout else ""
            except (OSError, ValueError):
                output = ""
        problems = []
        if runner_alive:
            problems.append("Der Läufer lebt nach Signal %s weiter." % name)
        if survivors:
            problems.append("Prozesse des Laufs überleben: %r" % survivors)
        if after != before:
            problems.append(
                "Der Agent arbeitet nach dem Stopp weiter (Ticks %r -> %r)."
                % (before, after)
            )
        if problems:
            self.fail(
                "\n".join(problems)
                + "\n--- Läuferausgabe ---\n"
                + output
                + "\n--- Protokoll ---\n"
                + self.log_text()
            )

    def assert_note_is_not_running(self, record):
        self.assertIsNotNone(record, "Kein Registereintrag vorhanden")
        self.assertIn(record.get("state"), ("ended", "stopped"), record)
        self.assertNotEqual(record.get("state"), "running", record)


class StopKillsAgentTest(RunnerProcessFixture):
    """AK1: Ein Stopp beendet die gesamte Prozesskette des Laufs."""

    def test_hup_stop_kills_agent_that_ignores_hup(self):
        """HUP ignoriert: Nach HUP an die Prozessgruppe stirbt die ganze Kette."""
        self.start_hanging_runner(B11_IGNORE="HUP")
        self.assertIsNotNone(self.recorded_pids().get("grandchild"))

        self.stop_and_expect_death(signal.SIGHUP, "HUP")

    def test_term_stop_kills_agent_that_ignores_term(self):
        """TERM ignoriert: Nach TERM an die Prozessgruppe stirbt die Kette."""
        self.start_hanging_runner(B11_IGNORE="TERM")
        self.assertIsNotNone(self.recorded_pids().get("grandchild"))

        self.stop_and_expect_death(signal.SIGTERM, "TERM")

    def test_hup_stop_kills_agent_that_ignores_hup_and_term(self):
        """HUP und TERM ignoriert: Der Stopp eskaliert bis zum sicheren Ende."""
        self.start_hanging_runner(B11_IGNORE="HUP,TERM")
        self.assertIsNotNone(self.recorded_pids().get("grandchild"))

        self.stop_and_expect_death(signal.SIGHUP, "HUP")


class SignalRegistryTest(RunnerProcessFixture):
    """AK2: Der Registereintrag endet sauber und wird nicht überschrieben."""

    def test_signal_stop_marks_the_run_ended_with_signal_note(self):
        """Nach HUP steht der Lauf auf ``ended`` mit Signalnotiz, nie ``running``."""
        self.start_hanging_runner(B11_IGNORE="HUP,TERM")

        self.stop_and_expect_death(signal.SIGHUP, "HUP")

        record = self.record()
        self.assert_note_is_not_running(record)
        self.assertEqual(record.get("state"), "ended", record)
        self.assertEqual(
            record.get("note"), "extern beendet (Signal HUP)", record
        )
        self.assertEqual(record.get("exit_code"), 129, record)
        self.assertIn("extern beendet (Signal HUP)", self.log_text())

    def test_signal_stop_leaves_an_already_finished_record(self):
        """Ein bereits beendeter Eintrag bleibt unverändert (only-live)."""
        self.start_hanging_runner(B11_IGNORE="HUP,TERM")
        record = self.record()
        self.assertIsNotNone(record, "Kein laufender Registereintrag")
        # Vorbedingung: ein anderer Pfad hat den Lauf bereits beendet.
        self.registry().finish(record["id"], exit_code=0, state="finished")

        self.stop_and_expect_death(signal.SIGHUP, "HUP")

        stored = self.registry().get(record["id"])
        self.assertEqual(stored.get("state"), "finished", stored)
        self.assertNotIn("extern beendet", stored.get("note") or "", stored)


class NormalRunBehaviourTest(RunnerProcessFixture):
    """AK3: Das normale Laufverhalten bleibt unverändert."""

    ignore = ""

    def test_regular_harness_keeps_signal_end_and_log_line(self):
        """Reguläre Signalbehandlung: Ende mit 129, Protokoll und Notiz bleiben."""
        self.start_hanging_runner(B11_IGNORE="")

        self.stop_and_expect_death(signal.SIGHUP, "HUP")

        self.assertEqual(self.process.returncode, 129)
        self.assertIn(
            "ABBRUCH: Lauf extern beendet (Signal HUP).", self.log_text()
        )
        record = self.record()
        self.assert_note_is_not_running(record)
        self.assertEqual(record.get("state"), "ended", record)
        self.assertEqual(
            record.get("note"), "extern beendet (Signal HUP)", record
        )

    def test_agent_exit_code_comes_from_the_harness(self):
        """Exit-Code 7 des Harness wird erkannt, nicht der Exit von ``tee``."""
        result = subprocess.run(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(self.project)],
            cwd=str(self.project),
            env=self.runner_env(
                B11_CHILD="0", B11_EXIT_AFTER="0.3", B11_EXIT_CODE="7"
            ),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
        )

        log = self.log_text()
        self.assertIn("=== Agent beendet, Exit-Code 7 ===", log)
        self.assertIn("Fehlerklasse 'other'", log)
        self.assertIn("Überspringe F1", log)
        self.assertNotIn("=== Agent beendet, Exit-Code 0 ===", log)
        self.assertTrue(log, result.stdout + result.stderr)


class StopEndpointRealTmuxTest(RunnerProcessFixture):
    """AK1/AK2/AK4: ``vibe stop`` beendet Lauf und Agenten in echter tmux-Sitzung."""

    ignore = "HUP,TERM"

    def setUp(self):
        super().setUp()
        self.tmux_dir = self.root / "tmux"
        self.tmux_dir.mkdir()
        self.tmux_dir.chmod(0o700)
        # tmux übernimmt PATH für Panes aus der Umgebung des Servers, nicht
        # aus der Sitzungsumgebung. Der Server startet im ersten Aufruf und
        # erbt deshalb hier den PATH mit dem Test-Harness.
        self.tmux_env = {
            "PATH": str(self.fakebin)
            + os.pathsep
            + os.environ.get("PATH", ""),
            "TMUX_TMPDIR": str(self.tmux_dir),
            "TERM": os.environ.get("TERM", "xterm"),
        }
        self.socket = "vibe-proj"

    def tearDown(self):
        self.tmux("-L", self.socket, "kill-server")
        super().tearDown()

    def tmux(self, *args):
        return subprocess.run(
            ["tmux", *args],
            env=self.tmux_env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def cli_env(self):
        env = self.runner_env()
        for key in list(env):
            if key.startswith("B11_") or key == "VIBE_LOGNAME":
                env.pop(key, None)
        env["TMUX_TMPDIR"] = str(self.tmux_dir)
        return env

    def start_run_in_tmux(self):
        """Startet den echten Läufer in einer echten, isolierten tmux-Sitzung."""
        overrides = {
            "VIBE": str(self.root),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "VIBE_CONFIG_FILE": str(self.root / "config.json"),
            "VIBE_STORAGE_LOCK_DIR": str(self.root / "locks"),
            "VIBE_INSTALL": str(self.install),
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_STATE": str(self.state),
            "VIBE_AGENTS_DIR": str(self.agents),
            "VIBE_MAX_PACKAGES": "1",
            "VIBE_RETRY_DELAY": "0",
            "VIBE_LOGNAME": "proj",
            "B11_FIXTURE_DIR": str(self.fixture),
            "B11_IGNORE": self.ignore,
            "PATH": str(self.fakebin)
            + os.pathsep
            + os.environ.get("PATH", ""),
            "TMUX_TMPDIR": str(self.tmux_dir),
        }
        command = "bash {} {} tester".format(
            shlex.quote(str(self.tool_bin / "vibe-run.sh")),
            shlex.quote(str(self.project)),
        )
        args = [
            "-L", self.socket, "new-session", "-d", "-s", self.socket,
            "-c", str(self.project), "-e", "VIBE_MANAGED=run",
        ]
        for key, value in overrides.items():
            args += ["-e", f"{key}={value}"]
        args.append(command)
        result = self.tmux(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.wait_for_start()

    def view_state(self):
        """Lädt den echten CLI-Code und fragt die Projektansicht (run_state)."""
        saved = dict(os.environ)
        try:
            os.environ.clear()
            os.environ.update(self.cli_env())
            module = load_module(CLI, "vibe_b11_stop_view_under_test")
            return module.run_state("proj")
        finally:
            os.environ.clear()
            os.environ.update(saved)

    def session_alive(self):
        return (
            self.tmux(
                "-L", self.socket, "has-session", "-t", self.socket
            ).returncode
            == 0
        )

    def test_stop_command_ends_the_run_and_shows_no_active_agent(self):
        """``vibe stop`` meldet Erfolg, beendet alle Prozesse, Ansicht ist inaktiv."""
        self.start_run_in_tmux()

        result = subprocess.run(
            [sys.executable, str(CLI), "stop", "proj"],
            cwd=str(self.root),
            env=self.cli_env(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Auf das Ende der Prozesskette warten (nicht nur auf die Sitzung).
        deadline = time.monotonic() + STOP_TIMEOUT
        while time.monotonic() < deadline and self.live_pids():
            time.sleep(0.05)
        survivors = self.live_pids()
        session_alive = self.session_alive()
        record = self.record()
        view = self.view_state()

        self.assertEqual(
            result.returncode, 0, result.stdout + result.stderr
        )
        self.assertIn("Beendet:", result.stdout)
        self.assertFalse(session_alive, "Die Laufsitzung lebt noch")
        self.assertEqual(
            survivors, {}, "Prozesse des gestoppten Laufs überleben: %r" % survivors
        )
        self.assert_note_is_not_running(record)
        self.assertIn(record.get("state"), ("ended", "stopped"), record)
        self.assertFalse(view["running"], view)


class PreflightAssistFixture(RunnerProcessFixture):
    """Helfer für Läufe mit Preflight-Assistenz (keine eigenen Testfälle)."""

    ignore = "HUP,TERM"

    def question_folder(self):
        return self.runtime / "questions"

    def wait_for_question(self, timeout=30):
        """Wartet auf eine offene Preflight-Rückfrage (F16-Mechanik)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            folder = self.question_folder()
            if folder.is_dir():
                for path in sorted(folder.iterdir()):
                    if not path.name.endswith(".json"):
                        continue
                    if path.name.endswith(".answer.json"):
                        continue
                    try:
                        record = json.loads(
                            path.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        continue
                    answer = folder / (record["id"] + ".answer.json")
                    if not answer.exists():
                        return record
            if self.process is not None and self.process.poll() is not None:
                self.fail(
                    "Der Läufer endete ohne Preflight-Rückfrage (Exit "
                    f"{self.process.returncode}):\n{self.log_text()}"
                )
            time.sleep(0.05)
        self.fail(
            "Keine Preflight-Rückfrage innerhalb von %s s.\nProtokoll:\n%s"
            % (timeout, self.log_text())
        )

    def answer_free_text(self, record, text):
        """Beantwortet die Rückfrage mit Freitext, wie es das Dashboard tut."""
        folder = self.question_folder()
        folder.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "option": None,
                "text": text,
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "by": "test",
            }
        ) + "\n"
        target = folder / (record["id"] + ".answer.json")
        temporary = folder / (".answer-" + record["id"] + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, target)

    def wait_for_pids(self, names, timeout=40):
        """Wartet, bis der Preflight-Agent seine PID-Dateien geschrieben hat."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if all((self.fixture / name).exists() for name in names):
                return
            if self.process is not None and self.process.poll() is not None:
                self.fail(
                    "Der Läufer endete vor dem Preflight-Agentenstart:\n"
                    + self.log_text()
                )
            time.sleep(0.05)
        self.fail(
            "Der Preflight-Agent hat keine PID-Dateien geschrieben.\n"
            "Protokoll:\n" + self.log_text()
        )

    def assert_no_live_record(self):
        """Kein Registereintrag bleibt ``running``/``starting`` hängen."""
        record = self.record()
        if record is None:
            return
        self.assertNotIn(
            record.get("state"), ("running", "starting"),
            "Der Registereintrag bleibt als laufend hängen: %r" % (record,),
        )



class PreflightAssistStopTest(PreflightAssistFixture):
    """Review Medium 1: Stopp/HUP während der Preflight-Assistenz.

    Die Preflight-Assistenz startet ihrerseits einen Agenten in einer
    Prozessgruppe (``run_agent_in``). Stirbt der Läufer in diesem Fenster an
    einem unabgefangenen Signal, läuft der ``EXIT``-Trap bei Bash nicht; ohne
    eine vor dem ersten Preflight wirksame Signalbehandlung bliebe die
    signalignorierende Preflight-Agentengruppe samt Unter- und Enkelprozess
    als Waise zurück und arbeitete weiter.
    """

    def test_hup_during_preflight_assist_ends_the_agent_group(self):
        """HUP während der Preflight-Assistenz beendet die Agentengruppe.

        Vorbedingung: unsauberes Projekt (Preflight-Befund), Assistenz
        aktiv; der Preflight-Agent (signalignorierender Harness mit Unter-
        und Enkelprozess) läuft; noch kein Registereintrag (Registerstart
        folgt erst nach dem Start-Preflight).
        Aktion: HUP an die Prozessgruppe der Läufersitzung.
        Erwartung: Läufer tot; Preflight-Agentengruppe samt Unter- und
        Enkelprozess tot; keine weiteren Ticks; kein Registereintrag bleibt
        ``running``.
        Fehlerfall: Die Agentengruppe überlebt als Waise und arbeitet
        weiter; ein Eintrag bleibt ``running``.
        """
        (self.project / "unfertig.txt").write_text(
            "unfertig\n", encoding="utf-8"
        )
        self.start_runner(
            VIBE_PREFLIGHT_ASSIST="1",
            VIBE_PREFLIGHT_QUESTION_TIMEOUT="30",
        )
        record = self.wait_for_question()
        self.answer_free_text(record, "Räume den Arbeitsbaum auf")
        self.wait_for_pids(("harness.pid", "child.pid", "grandchild.pid"))

        self.stop_and_expect_death(signal.SIGHUP, "HUP")

        self.assert_no_live_record()


class EndPreflightAssistStopTest(PreflightAssistFixture):
    """Review Medium 1: Stopp/HUP im „end“-Preflight (Eintrag existiert).

    Am Laufende existiert der Registereintrag bereits. Ein HUP während der
    Assistenz muss den Eintrag sauber auf ``ended`` mit Signalnotiz und
    Exit-Code 129 bringen (wie die bestehenden Signal-Tests es pinnen) und
    die Assistenzagentengruppe beenden.
    """

    def install_harness(self):
        """opencode-Attrappe: schließt Pakete ab, hängt in Assistenzaufträgen."""
        hang = (
            "import signal\n"
            "import time\n"
            "signal.signal(signal.SIGHUP, signal.SIG_IGN)\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "if os.environ.get('B11_ASSIST_HANG') == '1' \\\n"
            "        and 'Behebe ausschließlich diese Befunde im Projektordner' "
            "in prompt:\n"
            "    base = pathlib.Path(os.environ['B11_FIXTURE_DIR'])\n"
            "    base.mkdir(parents=True, exist_ok=True)\n"
            "    (base / 'harness.pid').write_text(str(os.getpid()), "
            "encoding='utf-8')\n"
            "    tick = base / 'harness.tick'\n"
            "    while True:\n"
            "        with tick.open('a', encoding='utf-8') as handle:\n"
            "            handle.write('h\\n')\n"
            "        time.sleep(0.05)\n"
        )
        script = support.FAKE_OPENCODE.replace(
            'args_path = os.environ.get("FAKE_ARGS_PATH")',
            hang + 'args_path = os.environ.get("FAKE_ARGS_PATH")',
            1,
        )
        opencode = self.fakebin / "opencode"
        opencode.write_text(script, encoding="utf-8")
        opencode.chmod(0o755)

    def test_hup_during_the_end_preflight_marks_the_run_ended(self):
        """HUP im end-Preflight: Eintrag ``ended`` mit Signalnotiz, Exit 129.

        Vorbedingung: Lauf registriert; das Paket F1 wurde abgeschlossen;
        der Integrationsstand ist unsauber, sodass das end-Preflight eine
        Rückfrage stellt; der Assistenzagent (signalignorierend) läuft.
        Aktion: HUP an die Prozessgruppe der Läufersitzung.
        Erwartung: Läufer endet mit 129; Assistenzagent tot; Registereintrag
        ``ended`` mit Notiz „extern beendet (Signal HUP)“ und Exit-Code 129;
        Protokollzeile vorhanden.
        Fehlerfall: Eintrag bleibt ``running`` oder verliert die Notiz; der
        Agent überlebt.
        """
        self.start_runner(
            VIBE_PREFLIGHT_ASSIST="1",
            VIBE_PREFLIGHT_QUESTION_TIMEOUT="30",
            FAKE_DIRTY_INTEGRATION=str(self.project),
            B11_ASSIST_HANG="1",
        )
        record = self.wait_for_question()
        self.answer_free_text(record, "Räume den Arbeitsbaum auf")
        self.wait_for_pids(("harness.pid",))

        self.stop_and_expect_death(signal.SIGHUP, "HUP")

        self.assertEqual(self.process.returncode, 129, self.log_text())
        stored = self.record()
        self.assertEqual(stored.get("state"), "ended", stored)
        self.assertEqual(
            stored.get("note"), "extern beendet (Signal HUP)", stored
        )
        self.assertEqual(stored.get("exit_code"), 129, stored)
        self.assertIn("extern beendet (Signal HUP)", self.log_text())


class StopAroundStartTest(RunnerProcessFixture):
    """Review Medium 2: Stopp im Fenster zwischen Auftragsstart und PID-Zuweisung.

    Das Fenster zwischen dem Start des Auftrags (``) </dev/null &``) und der
    ``AGENT_PID``-Zuweisung umfasst in der Shell nur Mikrosekunden und ist
    von außen nicht zuverlässig steuerbar. Diese Fälle prüfen deshalb das
    beobachtbare Zielverhalten mit engem Timing und mehreren Wiederholungen:
    Ein Stopp-Signal unmittelbar um den Auftragsstart herum darf die
    Agentengruppe nie als Waise zurücklassen. Ein grüner Einzeldurchlauf
    beweist die Fensterfreiheit nicht; die Wiederholungen erhöhen die
    Trefferwahrscheinlichkeit für den Zeitraum unmittelbar nach dem
    sichtbaren Versuchstart (Protokollmarke „--- Versuch 1/“).
    """

    ignore = "HUP,TERM"

    def hup_when_logged(self, offset, marker, delay=0.0, timeout=40):
        """Sendet HUP, sobald ``marker`` ab ``offset`` im Protokoll erscheint."""
        log_path = self.runtime / "proj.log"
        deadline = time.monotonic() + timeout
        found = False
        while time.monotonic() < deadline:
            try:
                text = log_path.read_text(encoding="utf-8")[offset:]
            except OSError:
                text = ""
            if marker in text:
                found = True
                break
            if self.process is not None and self.process.poll() is not None:
                self.fail(
                    "Der Läufer endete, bevor %r im Protokoll erschien:\n%s"
                    % (marker, self.log_text())
                )
            time.sleep(0.005)
        if not found:
            self.fail(
                "%r erschien nicht innerhalb von %s s im Protokoll.\n%s"
                % (marker, timeout, self.log_text())
            )
        if delay > 0:
            time.sleep(delay)
        try:
            os.killpg(self.pgid, signal.SIGHUP)
        except ProcessLookupError:
            pass

    def test_repeated_hup_around_the_attempt_start_leaves_no_orphan(self):
        """HUP unmittelbar beim Versuchstart: nie eine Waise (4 Wiederholungen).

        Vorbedingung: laufender Lauf mit signalignorierendem Harness; das
        Signal wird bei vier Wiederholungen mit steigendem Verzug (0, 20,
        50 und 200 ms) unmittelbar nach der sichtbaren Versuchstart-Marke
        gesendet — teils vor, teils nach der PID-Zuweisung.
        Aktion: HUP an die Prozessgruppe der Läufersitzung.
        Erwartung: In jeder Wiederholung enden Läufer und die gesamte
        Agentengruppe vollständig; es bleibt nie eine Waise zurück.
        Fehlerfall: Überlebende Prozesse oder weiterlaufende Ticks.
        """
        log_path = self.runtime / "proj.log"
        for repetition, delay in enumerate((0.0, 0.02, 0.05, 0.2)):
            with self.subTest(wiederholung=repetition + 1, verzug=delay):
                offset = log_path.stat().st_size if log_path.exists() else 0
                self.start_runner()
                self.hup_when_logged(offset, "--- Versuch 1/", delay=delay)
                self.stop_and_expect_death(signal.SIGHUP, "HUP", send=False)


class StopAgentGroupFallbackTest(unittest.TestCase):
    """Review Medium 2 (Runde 2): Stopp im Rennfenster nach dem Auftragsstart.

    Zwischen ``) </dev/null &`` und ``AGENT_PID=$!`` kann ein Signal-Trap
    feuern; ``stop_agent_group`` sieht dann einen leeren ``AGENT_PID``.
    Kehrt sie in dieser Lage wirkungslos zurück, läuft die bereits
    gestartete Agentengruppe als Waise weiter — der vom Arbeitspaket
    ausgeschlossene Zustand. Das Mikrosekunden-Fenster selbst ist von
    außen nicht steuerbar (dafür bleibt ``StopAroundStartTest`` der
    E2E-Verhaltensanker); diese Fälle prüfen die deterministisch prüfbare
    Schnittstelle: Die echte Funktion ``stop_agent_group`` aus
    ``bin/vibe-run.sh`` wird in der Fehlerlage ausgeführt — Auftrag läuft
    unter aktiver Jobkontrolle, ``AGENT_PID`` ist leer. Der Trap trifft
    nicht zufällig ins Fenster; die Fensterlage wird hergestellt und der
    Trap darin ausgelöst.

    Der Opferprozess ignoriert HUP und TERM, schreibt Lebenszeichen und
    endet erst nach 120 s; ein Stopp kann ihn also nur über die
    KILL-Eskalation beenden.
    """

    victim_source = (
        "import os, signal, sys, time\n"
        "from pathlib import Path\n"
        "signal.signal(signal.SIGHUP, signal.SIG_IGN)\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "tick, pidfile = sys.argv[1], sys.argv[2]\n"
        "Path(pidfile).write_text(str(os.getpid()), encoding='utf-8')\n"
        "end = time.monotonic() + 120\n"
        "while time.monotonic() < end:\n"
        "    with open(tick, 'a', encoding='utf-8') as handle:\n"
        "        handle.write('t\\n')\n"
        "    time.sleep(0.05)\n"
    )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.victim = self.root / "victim.py"
        self.victim.write_text(self.victim_source, encoding="utf-8")
        self.tick = self.root / "victim.tick"
        self.victim_pid_file = self.root / "victim.pid"
        self.started = []
        self.process = None

    def tearDown(self):
        process = self.process
        if process is not None and process.poll() is None:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except OSError:
                pass
        for pid in self.started + self.orphan_victim_pids():
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        if process is not None:
            try:
                process.communicate(timeout=5)
            except (subprocess.TimeoutExpired, ValueError, OSError):
                pass
        self.tmp.cleanup()

    def function_source(self):
        return extract_shell_function(BIN / "vibe-run.sh", "stop_agent_group")

    def orphan_victim_pids(self):
        """PID eines Überläufers anhand der PID-Datei (Aufräumen im Rot-Fall)."""
        try:
            value = self.victim_pid_file.read_text(encoding="utf-8").strip()
        except OSError:
            return []
        return [int(value)] if value.isdigit() else []

    def write_harness(self, lines):
        """Schreibt eine Hüllshell mit der echten stop_agent_group-Funktion."""
        path = self.root / "harness.sh"
        body = ["set -u", self.function_source()] + lines
        path.write_text("\n".join(body) + "\n", encoding="utf-8")
        return path

    def run_harness(self, path, send_hup=False, timeout=40):
        """Startet die Hüllshell; optional HUP, sobald der Auftrag läuft."""
        self.process = subprocess.Popen(
            ["bash", str(path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        if send_hup:
            deadline = time.monotonic() + 10
            while not (
                self.tick.exists() and self.tick.stat().st_size > 0
            ):
                if self.process.poll() is not None:
                    self.fail("Die Hüllshell endete vor dem Signal.")
                if time.monotonic() > deadline:
                    self.fail("Der Opferprozess ist nie angelaufen.")
                time.sleep(0.02)
            # Nur an die Hüllshell, nicht an die Gruppe: Der Auftrag ignoriert
            # HUP ohnehin — das Signal muss den Trap der Shell erreichen.
            os.kill(self.process.pid, signal.SIGHUP)
        try:
            stdout, _ = self.process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.fail(
                "Die Hüllshell endete nicht innerhalb von %s s." % timeout
            )
        return stdout

    def job_pid_of(self, output):
        match = re.search(r"JOB_PID=(\d+)", output)
        self.assertIsNotNone(match, "Hüllshell meldet keine Auftrag-PID:\n" + output)
        pid = int(match.group(1))
        self.started.append(pid)
        return pid

    def wait_victim_dead(self, pid, timeout=10.0):
        """Fordert das vollständige Ende des Auftrags innerhalb der Frist."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not pid_alive(pid):
                return
            time.sleep(0.05)
        self.fail(
            "Der Auftrag (PID %s) überlebt den Stopp und läuft als Waise "
            "weiter." % pid
        )

    def test_hup_trap_with_unassigned_agent_pid_kills_the_running_job(self):
        """Trap feuert bei leerer Kennung: die laufende Auftragsguppe endet.

        Vorbedingung: echte ``stop_agent_group``; Jobkontrolle aktiv; ein
        signalignorierender Auftrag läuft in eigener Prozessgruppe;
        ``AGENT_PID`` ist noch leer (Rennfenster-Simulation); ein HUP-Trap
        ruft ``stop_agent_group`` — wie der Signal-Trap des Läufers im
        Fenster.
        Aktion: HUP an die Hüllshell, während der Auftrag läuft.
        Erwartung: Der Trap wird ausgeführt und die Auftragsguppe endet
        vollständig (TERM genügt nicht, KILL-Eskalation beendet).
        Fehlerfall: Der Auftrag überlebt als Waise, oder der Trap greift
        nicht.
        """
        harness = self.write_harness([
            "trap 'stop_agent_group; echo TRAP_RAN' HUP",
            'AGENT_PID=""',
            "set -m",
            'python3 "%s" "%s" "%s" </dev/null >/dev/null 2>&1 &'
            % (self.victim, self.tick, self.victim_pid_file),
            "job_pid=$!",
            "sleep 2",
            "echo NO_SIGNAL",
            'echo "JOB_PID=$job_pid"',
        ])
        output = self.run_harness(harness, send_hup=True)

        self.assertIn(
            "TRAP_RAN",
            output,
            "Der HUP-Trap wurde nicht ausgeführt:\n" + output,
        )
        self.wait_victim_dead(self.job_pid_of(output))

    def test_stop_with_unassigned_agent_pid_and_no_jobs_is_harmless(self):
        """Leere Kennung ohne laufende Aufträge: wirkungslos und fehlerfrei.

        Vorbedingung: echte ``stop_agent_group``; ``AGENT_PID`` leer; keine
        Hintergrundaufträge.
        Aktion: direkter Aufruf von ``stop_agent_group`` (derselbe Einstieg,
        den der Trap mit leerer Kennung nimmt).
        Erwartung: Die Funktion kehrt ohne Fehler zurück; die aufrufende
        Shell läuft weiter und bleibt unangetastet.
        Fehlerfall: Abbruch (etwa durch ungeprüte Ersetzung) oder
        Selbstverletzung der eigenen Gruppe.
        """
        harness = self.write_harness([
            "set -m",
            'AGENT_PID=""',
            "stop_agent_group",
            'echo "STOP_RC=$?"',
            "echo AFTER_MARKER",
        ])
        output = self.run_harness(harness)

        self.assertEqual(
            self.process.returncode, 0, output
        )
        self.assertIn("AFTER_MARKER", output, output)

    def test_stop_with_assigned_agent_pid_kills_that_group(self):
        """Normalpfad mit gesetzter Kennung endet die Auftragsggruppe weiter.

        Vorbedingung: echte ``stop_agent_group``; der Auftrag läuft und ist
        als ``AGENT_PID`` eingetragen (Lage nach der Zuweisung).
        Aktion: direkter Aufruf von ``stop_agent_group``.
        Erwartung: Die Gruppe endet trotz ignorierter TERM-Signale; die
        Funktion meldet Erfolg.
        Fehlerfall: Überlebender Auftrag oder gebrochener Normalpfad durch
        eine künftige Fallback-Änderung.
        """
        harness = self.write_harness([
            "set -m",
            'python3 "%s" "%s" "%s" </dev/null >/dev/null 2>&1 &'
            % (self.victim, self.tick, self.victim_pid_file),
            "job_pid=$!",
            'AGENT_PID="$job_pid"',
            "for i in $(seq 1 100); do",
            '  [ -s "%s" ] && break' % self.tick,
            "  sleep 0.05",
            "done",
            "stop_agent_group",
            'echo "STOP_RC=$?"',
            'echo "JOB_PID=$job_pid"',
        ])
        output = self.run_harness(harness)

        self.assertEqual(
            self.process.returncode, 0, output
        )
        self.wait_victim_dead(self.job_pid_of(output))


if __name__ == "__main__":
    unittest.main()
