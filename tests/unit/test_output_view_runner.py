"""Ausgabeansicht (Läufer): Stream-Erfassung, Relay, Hintergrund-Subagenten und Dashboard.

Aufruf: python3 -m unittest tests.unit.test_output_view_runner -v
"""


import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "bin" / "vibe-run.sh"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support

MAIN_SESSION = "ses_main"
CHILD_SESSION = "ses_child"
FAKE_COMPLETED_TEXT = "PONG"


def fake_output(subagents=False):
    """Ereignisse im opencode-JSON-Format, wie sie der Läufer filtert."""
    lines = [
        '{"type":"text","sessionID":"%s","part":{"type":"text","text":"Hallo"}}'
        % MAIN_SESSION
    ]
    if subagents:
        lines.append(
            '{"type":"tool_use","sessionID":"%s","part":{"tool":"subagent",'
            '"state":{"status":"completed","input":{"agent":"general",'
            '"description":"Testzusammenfassung","prompt":"Sammle Infos"},'
            '"output":"%s"},"metadata":{"metadata":{"sessionID":"%s"}}}}'
            % (MAIN_SESSION, FAKE_COMPLETED_TEXT, CHILD_SESSION)
        )
        lines.append(
            '{"type":"tool_use","sessionID":"%s","part":{"tool":"subagent",'
            '"state":{"status":"running","input":{"agent":"general",'
            '"description":"Sammlung laeuft","prompt":"War auch läuft"},'
            '"output":""}}}' % MAIN_SESSION
        )
    return "\n".join(lines) + "\n"


class RunnerFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
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
            feedback=[support.ticket_record("F19", "Testpaket",
                                            type="feedback",
                                            description="Test")],
        )
        self.tool_bin = support.install_runner(self.root / "_toolchain")
        self.fakebin = support.install_fake_tools(self.root)
        support.init_repo(self.project)
        support.commit_all(self.project)
        self.calls = self.root / "opencode.calls"
        self.counter = self.root / "counter"
        self.addCleanup(self.tmp.cleanup)

    def env(self, subagents=False):
        env = os.environ.copy()
        for key in list(env):
            if (
                key.startswith("VIBE")
                or key.startswith("SANDBOX")
                or key.startswith("FAKE_")
                or key
                in (
                    "AGENT",
                    "TESTER",
                    "REVIEWER",
                    "MAX_RETRIES",
                    "VERIFY_QUICK",
                    "VERIFY_FULL",
                    "VERIFY_PACKAGE",
                    "TMUX",
                    "TMUX_PANE",
                )
            ):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(self.root),
                "VIBE_INSTALL": str(self.root / "_toolchain"),
                "VIBE_RUNTIME": str(self.root / "_logs"),
                "VIBE_AGENTS_DIR": str(self.agents),
                "HOME": str(self.home),
                "VIBE_NO_CONTAINER": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
                "FAKE_ARGS_PATH": str(self.root / "_logs" / "opencode.args"),
                "FAKE_OUTPUT": fake_output(subagents),
                "FAKE_CALLS": str(self.calls),
                "FAKE_COUNTER": str(self.counter),
            }
        )
        return env

    def command(self):
        return ["bash", str(self.tool_bin / "vibe-run.sh"), str(self.project)]

    def run_runner(self, subagents=False):
        result = subprocess.run(
            self.command(),
            env=self.env(subagents=subagents),
            cwd=str(self.project),
            capture_output=True,
            text=True,
            timeout=90,
        )
        log = self.log_text()
        self.assertEqual(
            result.returncode, 0, "Läufer bricht ab:\n" + result.stdout + result.stderr
        )
        self.assertIn(
            "FERTIG",
            log,
            "Läufer hat die Abnahme nicht gemeldet:\n" + log + "\n" + result.stderr,
        )
        return result

    def log_text(self):
        path = self.root / "_logs" / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def read_state(self):
        path = self.root / "_logs" / "proj.log.state.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            self.fail("Zustandsdatei ist kein gültiges JSON: " + path.read_text(encoding="utf-8"))

    def opencode_args(self):
        path = self.root / "_logs" / "opencode.args"
        self.assertTrue(path.exists(), "opencode wurde nicht aufgerufen")
        return [word for word in path.read_text(encoding="utf-8").split("\0") if word]


class RunnerLogTest(RunnerFixture):
    """Menschenlesbares Protokoll statt Roh-JSON (Grundlage der Ausgabeansicht)."""

    def test_runner_logs_only_human_readable_lines(self):
        self.run_runner()

        log = self.log_text()
        self.assertIn("Hallo", log, "Ereignistext fehlt im Laufprotokoll")
        bad = [line for line in log.splitlines() if line.startswith("{")]
        self.assertEqual(
            bad, [], "Roh-JSON-Zeilen dürfen nicht ins menschliche Protokoll:\n" + log
        )

    def test_runner_calls_opencode_with_format_json(self):
        self.run_runner()

        args = self.opencode_args()
        self.assertEqual(
            "run", args[0], "Fake wurde nicht als 'opencode run' aufgerufen: " + repr(args)
        )
        for token in ("--format", "json"):
            self.assertIn(token, args, f"Argument {token} fehlt: {args}")

    def test_runner_without_subagents_writes_no_fake_entries(self):
        """Fehlende Erfassung: keine Attrappen, keine falsche Hauptsession."""
        self.run_runner()

        state = self.read_state()
        if state is not None:
            self.assertEqual(
                state.get("session"),
                MAIN_SESSION,
                f"Hauptsession falsch oder nicht erfasst: {state}",
            )
            self.assertEqual(
                [], state.get("subagents") or [], f"Subagenten erfunden: {state}"
            )

    def test_runner_still_runs_packages_and_verification(self):
        self.run_runner()
        self.assertIn(
            "Arbeitspaket F19",
            self.log_text(),
            "Der Paketlauf selbst wurde durch die Protokollierung beschädigt",
        )


class RunnerSubagentStateTest(RunnerFixture):
    """Erfasste Subagenten in der Zustandsdatei (Grundlage der Subagentenansicht)."""

    def test_state_file_records_completed_and_running_subagents(self):
        self.run_runner(subagents=True)

        state = self.read_state()
        self.assertIsNotNone(state, "Zustandsdatei fehlt nach Subagenten-Ereignissen")
        self.assertEqual(
            state.get("session"), MAIN_SESSION, f"Hauptsession falsch erfasst: {state}"
        )
        entries = state.get("subagents")
        self.assertIsInstance(entries, list, f"subagents keine Liste: {state}")
        self.assertEqual(2, len(entries), f"Falsche Anzahl erfasster Subagenten: {state}")

        completed, running = entries

        self.assertEqual(
            completed.get("session"),
            CHILD_SESSION,
            f"Sub-Session fehlt oder falsch: {completed}",
        )
        self.assertEqual("general", completed.get("agent"), f"Agent fehlt: {completed}")
        self.assertEqual(
            "Testzusammenfassung",
            completed.get("description"),
            f"Beschreibung fehlt: {completed}",
        )
        self.assertEqual(
            "completed", completed.get("status"), f"Status falsch erfasst: {completed}"
        )
        self.assertIn(
            FAKE_COMPLETED_TEXT,
            str(completed.get("output") or ""),
            f"Ausgabe fehlt: {completed}",
        )
        self.assertIsInstance(
            completed.get("prompt"), str, f"Prompt fehlt (auch leer erlaubt): {completed}"
        )
        self.assertIsInstance(
            completed.get("started"), int, f"Started muss numerisch sein: {completed}"
        )
        self.assertIsInstance(
            completed.get("ended"), int, f"Ended muss numerisch sein: {completed}"
        )

        self.assertEqual(
            "running", running.get("status"), f"Status bei laufendem Subagenten: {running}"
        )
        self.assertEqual("general", running.get("agent"), f"Agent fehlt: {running}")
        self.assertIsInstance(
            running.get("ended", 0), int, f"Ended muss numerisch sein (0 erlaubt): {running}"
        )


# ===========================================================================
# Unit-Abnahme (Teil 2): Erfassung der Hauptsession im Protokollfilter
# ===========================================================================

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

BIN = REPO / "bin"
RUNS = BIN / "vibe_runs.py"
RUNNER_ap19 = BIN / "vibe-run.sh"

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(BIN))
import runner_support as support  # noqa: E402

MODULE = None


def load_module():
    """Lädt bin/vibe_runs.py als Testunterlage (ohne Installation)."""
    global MODULE
    if MODULE is None:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_runs_ap19_capture_under_test", str(RUNS))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        MODULE = module
    return MODULE


def capture_text_event(session, text="Antwort"):
    """Ereignis, wie es opencode --format json je Nachricht ausgibt."""
    return {
        "type": "text",
        "sessionID": session,
        "part": {"type": "text", "text": text},
    }


def json_line(event):
    return json.dumps(event, ensure_ascii=False) + "\n"


PROJECT_ENV = (
    "TYPE=generic\n"
    "AGENT=test-agent\n"
    "TESTER=test-agent\n"
    "REVIEWER=code-reviewer\n"
    'VERIFY_PACKAGE="true"\n'
    'VERIFY_FULL="true"\n'
    "MAX_RETRIES=1\n"
)


class StreamCaptureFixture(unittest.TestCase):
    """Temporärer Laufzeitordner, echtes Projekt, Aufruf über den Filter-CLI."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "_logs"
        self.runtime.mkdir(parents=True)
        self.project = self.root / "proj"
        self.project.mkdir(parents=True)
        self.state_path = self.runtime / "proj.log.state.json"
        self.sessions_path = self.runtime / "sessions.json"
        self.addCleanup(self.tmp.cleanup)
        self.module = load_module()

    # ---------- Helfer ----------

    def stream_args(self, sessions=True, run_id="", attempt=True,
                    state=None):
        args = [
            sys.executable, str(RUNS), "stream",
            "--state", str(state or self.state_path),
        ]
        if attempt:
            args.append("--attempt")
        if sessions:
            args += [
                "--sessions", str(self.sessions_path),
                "--session-project", str(self.project),
                "--session-name", "proj",
                "--session-agent", "vibe-agent",
                "--session-harness", "opencode",
            ]
            if run_id:
                args += ["--session-run", run_id]
        return args

    def run_stream(self, events, sessions=True, run_id="", attempt=True):
        """Leitet die Ereignisse einmal durch den Filter; liefert stdout."""
        payload = "".join(json_line(event) for event in events)
        completed = subprocess.run(
            self.stream_args(sessions=sessions, run_id=run_id,
                             attempt=attempt),
            input=payload,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(
            0, completed.returncode,
            "Der Protokollfilter brach ab: " + completed.stdout + completed.stderr,
        )
        return completed.stdout

    def write_state(self, session, subagents=None):
        self.state_path.write_text(
            json.dumps({"session": session, "subagents": subagents or []},
                       ensure_ascii=False),
            encoding="utf-8",
        )

    def entries(self):
        if not self.sessions_path.exists():
            return []
        data = json.loads(self.sessions_path.read_text(encoding="utf-8"))
        return data.get("sessions") or []

    def sessions_of_entries(self):
        return [entry.get("session") for entry in self.entries()]


class StreamCaptureTest(StreamCaptureFixture):
    """AK2/AK5: Erfassung der Hauptsession durch den Protokollfilter."""

    def test_main_session_is_captured_with_all_given_values(self):
        """Vorbedingung: leeres Register, Projekt und Filteraufruf mit allen
        Zusatzangaben.
        Aktion: ein Ereignis der Hauptsession durch den Filter leiten.
        Erwartung: genau ein Registereintrag mit Kennung, realem Projektpfad,
        Projektname, Agent und Harness; ``run_id`` bleibt leer.
        Fehlerfall: kein Eintrag oder falsche Zuordnung.
        """
        self.run_stream([capture_text_event("ses_attempt1", "Antwort 1")])

        entries = self.entries()
        self.assertEqual(1, len(entries),
                         "Die Hauptsession wurde nicht erfasst: " + repr(entries))
        entry = entries[0]
        self.assertEqual("ses_attempt1", entry.get("session"), entry)
        self.assertEqual(
            os.path.realpath(str(self.project)),
            os.path.realpath(str(entry.get("project"))),
            "Der Eintrag hält nicht den realen Projektpfad: " + repr(entry),
        )
        self.assertEqual("proj", entry.get("name"), entry)
        self.assertEqual("vibe-agent", entry.get("agent"), entry)
        self.assertEqual("opencode", entry.get("harness"), entry)
        self.assertEqual("", entry.get("run_id"), entry)

    def test_session_run_value_is_stored_in_the_entry(self):
        """Vorbedingung: Filteraufruf mit ``--session-run lauf-4711``.
        Aktion: ein Hauptsession-Ereignis leiten.
        Erwartung: ``run_id`` des Eintrags ist exakt ``lauf-4711``.
        Fehlerfall: Lauf-ID fehlt oder wird verfälscht (Zustandsableitung
        wäre dann „unbekannt“).
        """
        self.run_stream([capture_text_event("ses_attempt1")], run_id="lauf-4711")

        entries = self.entries()
        self.assertEqual(1, len(entries), entries)
        self.assertEqual("lauf-4711", entries[0].get("run_id"), entries[0])

    def test_without_sessions_option_nothing_is_written(self):
        """AK6: Vorbedingung: Filteraufruf ohne ``--sessions``.
        Aktion: Hauptsession-Ereignis leiten.
        Erwartung: keine ``sessions.json``; die Ausgabe bleibt die bisherige
        ``[Session]``-Zeile (Rückwärtskompatibilität).
        Fehlerfall: Registerdatei entsteht oder Ausgabe weicht ab.
        """
        stdout = self.run_stream(
            [capture_text_event("ses_attempt1", "Antwort 1")], sessions=False
        )

        self.assertFalse(
            self.sessions_path.exists(),
            "Ohne --sessions wurde ein Sessionregister geschrieben: "
            + str(self.sessions_path),
        )
        self.assertIn("[Session] ses_attempt1", stdout,
                      "Bestehende Ausgabe verändert: " + stdout)
        self.assertIn("Antwort 1", stdout, stdout)

    def test_child_session_events_never_create_entries(self):
        """Vorbedingung: Hauptsession ``ses_main`` bereits im Zustand.
        Aktion: Ereignisse der Hauptsession und einer Kind-Session leiten
        (``--attempt``: die Kind-Session ist ein Subagent).
        Erwartung: nur ``ses_main`` steht im Register; die Kind-Session nie.
        Fehlerfall: Subagenten-Sessions erscheinen als fortsetzbare Sessions.
        """
        self.write_state("ses_main")

        self.run_stream([
            capture_text_event("ses_main", "Haupt"),
            capture_text_event("ses_kind", "Kind"),
        ])

        self.assertEqual(["ses_main"], self.sessions_of_entries(),
                         "Kind-Session wurde als Hauptsession erfasst")

    def test_pi_session_header_never_creates_an_entry(self):
        """Vorbedingung: leerer Zustand, Pi-Ereignisstrom.
        Aktion: Pi-Session-Header und eine Nachricht leiten.
        Erwartung: kein Registereintrag (Pi läuft mit ``--no-session``; die
        Kennung ist ephemeral).
        Fehlerfall: Pi-Kennung wird erfasst und wäre fälschlich fortsetzbar.
        """
        self.run_stream([
            {"type": "session", "id": "pi_ses_4711"},
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Pi-Antwort"}],
                },
            },
        ])

        self.assertEqual([], self.entries(),
                         "Pi-Session-Header erzeugte einen Eintrag: "
                         + repr(self.entries()))

    def test_text_only_session_is_captured_when_promoted_at_stream_end(self):
        """Vorbedingung: Zustand hält ``ses_alt``; Strom ohne ``--attempt``
        mit ausschließlich Text einer fremden Session (F25-Zweitversuch).
        Aktion: Strom leiten.
        Erwartung: die am Stromende übernommene Hauptsession ``ses_neu``
        steht im Register; ``ses_alt`` nicht (in diesem Strom nie gesehen).
        Fehlerfall: die Übernahme am Stromende wird nicht erfasst und die
        Session bleibt unauffindbar.
        """
        self.write_state("ses_alt")

        self.run_stream(
            [capture_text_event("ses_neu", "Zweiter Versuch")], attempt=False
        )

        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual("ses_neu", state.get("session"),
                         "Vorbedingung nicht erfüllt: " + repr(state))
        self.assertEqual(["ses_neu"], self.sessions_of_entries(),
                         "Text-only-Übernahme am Stromende wurde nicht erfasst")

    def test_hard_aborted_stream_keeps_the_entry(self):
        """AK5: Vorbedingung: laufender Filterprozess mit ``--session-run``.
        Aktion: ein Hauptsession-Ereignis einspeisen, auf den Registereintrag
        warten und den Prozess hart beenden (SIGKILL, wie ein Absturz).
        Erwartung: der Eintrag existiert weiterhin, trägt die Lauf-ID und ist
        über ``session_overview`` mit Zustand des Laufs auffindbar.
        Fehlerfall: der Eintrag entsteht erst am Stromende und geht beim
        Abbruch verloren.
        """
        self.module.RunRegistry(str(self.runtime)).start(
            project=str(self.project), name="proj", key="proj",
            agent="vibe-agent", session="vibe-proj", run_id="lauf-4711",
            state="running",
        )
        process = subprocess.Popen(
            self.stream_args(run_id="lauf-4711"),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            process.stdin.write(json_line(capture_text_event("ses_attempt1", "Anfang")))
            process.stdin.flush()

            deadline = time.time() + 20
            while time.time() < deadline and not self.entries():
                time.sleep(0.05)
            self.assertEqual(
                ["ses_attempt1"], self.sessions_of_entries(),
                "Der Eintrag entstand nicht vor dem Abbruch des Stroms",
            )
        finally:
            process.kill()
            process.wait(timeout=20)
            for stream in (process.stdin, process.stdout, process.stderr):
                try:
                    stream.close()
                except OSError:
                    pass

        entries = self.entries()
        self.assertEqual(
            1, len(entries),
            "Nach dem Hartabbruch fehlt der Eintrag: " + repr(entries),
        )
        self.assertEqual("lauf-4711", entries[0].get("run_id"), entries[0])

        overview = self.module.session_overview(
            str(self.runtime), project=str(self.project))
        self.assertEqual(
            ["ses_attempt1"], [item["session"] for item in overview],
            "Die abgebrochene Session ist nicht auffindbar: " + repr(overview),
        )
        self.assertEqual("running", overview[0].get("state"), overview[0])
        self.assertEqual("läuft", overview[0].get("state_label"), overview[0])


class RunnerWiringTextTest(unittest.TestCase):
    """AK5: ``bin/vibe-run.sh`` übergibt die Erfassungsargumente richtig."""

    @classmethod
    def setUpClass(cls):
        cls.text = RUNNER_ap19.read_text(encoding="utf-8")
        cls.assignments = [
            match.start()
            for match in re.finditer(r"(?m)^STREAM_FILTER=\(", cls.text)
        ]

    def test_filter_is_configured_twice(self):
        """Vorbedingung: Läuferskript gelesen.
        Aktion: Zuweisungen an ``STREAM_FILTER`` zählen.
        Erwartung: mindestens zwei — vor und nach ``register_start``.
        Fehlerfall: nur ein Filteraufruf, Paketsessions blieben ohne Lauf-ID.
        """
        self.assertGreaterEqual(
            len(self.assignments), 2,
            "STREAM_FILTER wird nur einmal gesetzt; nach register_start fehlt "
            "die Lauf-ID: " + repr(self.assignments),
        )

    def test_preflight_filter_captures_without_run_id(self):
        """Vorbedingung: erste Filterzuweisung (Start-Preflight).
        Aktion: Argumente prüfen.
        Erwartung: ``--sessions "$RUNTIME/sessions.json"`` sowie Projekt,
        Name, Agent und Harness; keine ``--session-run``.
        Fehlerfall: Preflight-Sessions tragen eine falsche/fehlende Zuordnung
        oder werden gar nicht erfasst.
        """
        first = self.text[self.assignments[0]:
                          self.assignments[1] if len(self.assignments) > 1
                          else len(self.text)]

        for expected in (
            "--sessions",
            '"$RUNTIME/sessions.json"',
            "--session-project",
            '"$P"',
            "--session-name",
            '"$NAME"',
            "--session-agent",
            '"$AGENT"',
            "--session-harness",
            '"$HARNESS"',
        ):
            self.assertIn(expected, first,
                          f"{expected} fehlt in der Filterzuweisung: {first!r}")
        self.assertNotIn(
            "--session-run", first,
            "Der Start-Preflight darf keine Lauf-ID übergeben: " + first,
        )

    def test_package_filter_runs_after_register_start_with_the_run_id(self):
        """Vorbedingung: zweite Filterzuweisung.
        Aktion: Position gegen den Aufruf ``register_start`` prüfen.
        Erwartung: sie steht nach ``register_start`` und enthält
        ``--session-run "$RUN_ID"`` sowie den Registerpfad.
        Fehlerfall: Paketsessions bleiben ohne Lauf-ID (Zustand „unbekannt“).
        """
        call = re.search(r"(?m)^register_start\s*$", self.text)
        self.assertIsNotNone(
            call, "Aufruf 'register_start' fehlt im Läuferskript")
        if len(self.assignments) < 2:
            self.fail(
                "Nach register_start fehlt die zweite Filterzuweisung; ohne "
                "sie tragen Paketsessions keine Lauf-ID"
            )
        second = self.text[self.assignments[1]:]

        self.assertGreater(
            self.assignments[1], call.start(),
            "Die zweite Filterzuweisung steht vor register_start; RUN_ID ist "
            "dort noch nicht bekannt",
        )
        self.assertIn('--session-run "$RUN_ID"', second,
                      "Die Lauf-ID wird dem Filter nicht übergeben: " + second[:600])
        self.assertIn("--sessions", second, second[:600])


class RunnerCaptureFixture(unittest.TestCase):
    """Läufer, opencode-Attrappe und isoliertes Projekt mit einem Paket."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        # Echte Harness-Schicht, damit der Läufer den Produktionspfad benutzt.
        for name in ("vibe_harness.py", "vibe_opencode.py", "vibe_storage.py"):
            (self.tool_bin / name).write_text(
                (BIN / name).read_text(encoding="utf-8"), encoding="utf-8"
            )
        (self.tool_bin / "vibe").write_text(support.FAKE_VIBE, encoding="utf-8")
        (self.tool_bin / "vibe").chmod(0o755)
        self.runtime = self.root / "_logs"
        self.project = self.root / "proj"
        support.init_repo(self.project)
        support.write_project(
            self.project, PROJECT_ENV,
            feedback=[support.ticket_record(
                "AP19", "Sessionerfassung", description="Test")],
        )
        support.commit_all(self.project, "Ausgangsstand")
        self.calls = self.root / "calls.log"
        self.counter = self.root / "counter"
        self.args = self.root / "opencode.args"
        self.fakebin = support.install_fake_tools(self.root)
        self.addCleanup(self.tmp.cleanup)
        self.module = load_module()

    def env(self, **extra):
        env = os.environ.copy()
        for key in list(env):
            if (
                key.startswith("VIBE")
                or key.startswith("SANDBOX")
                or key.startswith("FAKE_")
                or key in (
                    "AGENT", "TESTER", "REVIEWER", "MAX_RETRIES",
                    "VERIFY_QUICK", "VERIFY_FULL", "VERIFY_PACKAGE",
                )
            ):
                env.pop(key, None)
        env.update({
            "VIBE": str(self.root),
            "VIBE_INSTALL": str(self.install),
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_AGENTS_DIR": str(self.agents),
            "VIBE_LOGNAME": "proj",
            "VIBE_RETRY_DELAY": "0",
            "HOME": str(self.home),
            "VIBE_NO_CONTAINER": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
            "FAKE_CALLS": str(self.calls),
            "FAKE_COUNTER": str(self.counter),
            "FAKE_ARGS_PATH": str(self.args),
        })
        env.update(extra)
        return env

    def run_runner(self, **extra):
        return subprocess.run(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(self.project)],
            cwd=str(self.project),
            env=self.env(**extra),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=180,
        )

    def log_text(self):
        path = self.runtime / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def session_entries(self):
        path = self.runtime / "sessions.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("sessions") or []

    def runs(self):
        path = self.runtime / "runs.json"
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8")).get("runs") or []


class RunnerCaptureTest(RunnerCaptureFixture):
    """AK5: der echte Läuferlauf erfasst seine Hauptsession mit Lauf-ID."""

    def test_runner_captures_the_package_session_with_its_run_id(self):
        """Vorbedingung: Projekt mit einem offenen Paket, opencode-Attrappe
        liefert die Session ``ses_attempt1``.
        Aktion: den Läufer vollständig ausführen.
        Erwartung: ``sessions.json`` enthält diese Session mit Projektpfad,
        Projektname, Agent, Harness opencode und der Lauf-ID des Laufs; die
        Session ist danach mit Zustand „abgeschlossen“ auffindbar.
        Fehlerfall: keine Erfassung oder Eintrag ohne Lauf-ID (dann wäre der
        Zustand „unbekannt“ und die Session nicht gezielt fortsetzbar).
        """
        result = self.run_runner(FAKE_MODE_SEQUENCE="complete")

        self.assertEqual(
            0, result.returncode,
            "Läufer bricht ab:\n" + result.stdout + result.stderr,
        )
        log = self.log_text()
        self.assertIn("FERTIG", log, "Lauf ohne Abnahme:\n" + log)

        runs = self.runs()
        self.assertEqual(1, len(runs), "Laufregister unerwartet: " + repr(runs))
        run_id = runs[0].get("id")

        entries = [entry for entry in self.session_entries()
                   if entry.get("session") == "ses_attempt1"]
        self.assertEqual(
            1, len(entries),
            "Die Paketsession wurde nicht erfasst: "
            + repr(self.session_entries()),
        )
        entry = entries[0]
        self.assertEqual(run_id, entry.get("run_id"),
                         "Der Eintrag trägt nicht die Lauf-ID: " + repr(entry))
        self.assertEqual("proj", entry.get("name"), entry)
        self.assertEqual("test-agent", entry.get("agent"), entry)
        self.assertEqual("opencode", entry.get("harness"), entry)
        self.assertEqual(
            os.path.realpath(str(self.project)),
            os.path.realpath(str(entry.get("project"))),
            "Der Eintrag hält nicht den realen Projektpfad: " + repr(entry),
        )

        overview = self.module.session_overview(
            str(self.runtime), project=str(self.project))
        found = [item for item in overview
                 if item.get("session") == "ses_attempt1"]
        self.assertEqual(
            1, len(found),
            "Die Session ist nicht auffindbar: " + repr(overview),
        )
        self.assertEqual("finished", found[0].get("state"), found[0])
        self.assertEqual("abgeschlossen", found[0].get("state_label"), found[0])


# ===========================================================================
# Unit-Abnahme (Teil 2): Live-Erfassung von Subagenten im Stream-Filter
# ===========================================================================

import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(BIN))

import vibe_runs  # noqa: E402

MAIN_SESSION_b11 = "ses_main_b11"
CHILD_A = "ses_kind_a"
CHILD_B = "ses_kind_b"
RUNNING_C = "ses_kind_laufend"


def relay_text_event(session, text):
    return {"type": "text", "sessionID": session,
            "part": {"type": "text", "text": text}}


def reasoning_event(session, text):
    return {"type": "reasoning", "sessionID": session,
            "part": {"type": "text", "text": text}}


def tool_event(session, tool, command):
    return {"type": "tool_use", "sessionID": session,
            "part": {"tool": tool,
                     "state": {"status": "running",
                               "input": {"command": command}}}}


def completed_task_event(session, child, output):
    return {
        "type": "tool_use",
        "sessionID": session,
        "part": {
            "tool": "task",
            "state": {
                "status": "completed",
                "input": {"agent": "general", "description": "Kind " + child},
                "metadata": {"metadata": {"sessionID": child}},
                "output": output,
            },
        },
    }


class StreamRelayFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_path = Path(self.tmp.name) / "proj.log.state.json"

    def feed(self, events, raw_lines=()):
        payload = "\n".join([json.dumps(event, ensure_ascii=False)
                             for event in events] + list(raw_lines)) + "\n"
        emitted = []
        vibe_runs.stream_events(
            io.StringIO(payload), emitted.append, str(self.state_path))
        return emitted

    def state(self):
        return vibe_runs.load_subagent_state(str(self.state_path))

    def entry(self, session):
        return next((item for item in self.state()["subagents"]
                     if item.get("session") == session), None)

    def establish_main(self):
        self.feed([relay_text_event(MAIN_SESSION_b11, "Hauptagent arbeitet")])


class LiveChildCaptureTest(StreamRelayFixture):
    """AK7: fremde sessionID -> laufender Subagent mit Teilausgabe."""

    def test_child_session_events_create_a_running_subagent_with_output(self):
        """AK7: Kind-Ereignisse erzeugen einen laufenden Subagenten.

        Vorbedingung: leerer Zustand, Hauptsession-Ereignis zuerst.
        Aktion: Text, Denken und Werkzeug des Kindes ses_kind_a.
        Erwartung: Hauptsession bleibt ses_main_b11; ein Eintrag ses_kind_a,
        Status running, ended 0; Ausgabe enthält Text, "[Denken] " und
        "[Werkzeug] bash" samt "ls -la".
        Fehlerfall: Kein Eintrag, überschriebene Hauptsession oder fehlende
        Teilausgabe.
        """
        self.establish_main()

        self.feed([
            relay_text_event(CHILD_A, "Teilausgabe A"),
            reasoning_event(CHILD_A, "Kind denkt nach"),
            tool_event(CHILD_A, "bash", "ls -la"),
        ])

        state = self.state()
        self.assertEqual(
            MAIN_SESSION_b11, state["session"],
            "Die Hauptsession wurde durch Kind-Ereignisse überschrieben: "
            + json.dumps(state, ensure_ascii=False))
        entry = self.entry(CHILD_A)
        self.assertIsNotNone(
            entry, "Für die Kind-Session wurde kein laufender Subagent "
                   "angelegt: " + json.dumps(state, ensure_ascii=False))
        self.assertEqual("running", entry.get("status"), entry)
        self.assertEqual(0, entry.get("ended"), entry)
        self.assertIsInstance(entry.get("started"), int, entry)
        output = str(entry.get("output") or "")
        for expected in ("Teilausgabe A", "[Denken] Kind denkt nach",
                         "[Werkzeug] bash", "ls -la"):
            self.assertIn(expected, output,
                          f"Teilausgabe {expected!r} fehlt in {output!r}")

    def test_two_child_sessions_are_tracked_in_parallel(self):
        """AK7: zwei parallele Kinder werden getrennt erfasst.

        Vorbedingung: Hauptsession erfasst.
        Aktion: verschachtelte Text-/Werkzeugereignisse von ses_kind_a und
        ses_kind_b.
        Erwartung: zwei laufende Einträge; A-Ausgabe nur in A, B-Ausgabe nur
        in B; kein Eintrag für die Hauptsession.
        Fehlerfall: Eintrag fehlt, Ausgaben vermischt oder Hauptsession als
        Subagent erfunden.
        """
        self.establish_main()

        self.feed([
            relay_text_event(CHILD_A, "A-ERSTE-4711"),
            relay_text_event(CHILD_B, "B-ERSTE-4711"),
            reasoning_event(CHILD_A, "A-DENKEN-4711"),
            tool_event(CHILD_B, "bash", "b-command-4711"),
            relay_text_event(CHILD_A, "A-ZWEITE-4711"),
        ])

        entries = {item.get("session"): item
                   for item in self.state()["subagents"]}
        self.assertEqual(
            {CHILD_A, CHILD_B}, set(entries),
            "Nicht genau die beiden laufenden Kinder wurden erfasst: "
            + json.dumps(list(entries), ensure_ascii=False))
        output_a = str(entries[CHILD_A].get("output") or "")
        output_b = str(entries[CHILD_B].get("output") or "")
        self.assertIn("A-ERSTE-4711", output_a, output_a)
        self.assertIn("A-ZWEITE-4711", output_a, output_a)
        self.assertIn("[Denken] A-DENKEN-4711", output_a, output_a)
        self.assertNotIn("B-ERSTE-4711", output_a,
                         "Ausgabe von B landete bei A: " + output_a)
        self.assertIn("B-ERSTE-4711", output_b, output_b)
        self.assertIn("b-command-4711", output_b, output_b)
        self.assertNotIn("A-ERSTE-4711", output_b,
                         "Ausgabe von A landete bei B: " + output_b)
        self.assertEqual("running", entries[CHILD_A].get("status"), entries)
        self.assertEqual("running", entries[CHILD_B].get("status"), entries)

    def test_task_completion_ends_the_matching_child_only(self):
        """AK7: task/completed beendet genau das zugehörige Kind.

        Vorbedingung: ses_kind_a und ses_kind_b laufen aus dem Ereignisstrom.
        Aktion: task/completed-Ereignis der Hauptsession mit Kind A.
        Erwartung: A completed mit ended ungleich 0, B weiter running mit
        ended 0; Hauptsession unverändert.
        Fehlerfall: Abschluss ignoriert, falsches Kind oder beide beendet.
        """
        self.establish_main()
        self.feed([relay_text_event(CHILD_A, "A-läuft"),
                   relay_text_event(CHILD_B, "B-läuft")])

        self.feed([completed_task_event(MAIN_SESSION_b11, CHILD_A, "FERTIG-A")])

        entry_a = self.entry(CHILD_A)
        entry_b = self.entry(CHILD_B)
        self.assertIsNotNone(entry_a, "Kind A fehlt")
        self.assertIsNotNone(entry_b, "Kind B fehlt")
        self.assertEqual("completed", entry_a.get("status"),
                         f"Kind A wurde nicht abgeschlossen: {entry_a}")
        self.assertNotEqual(0, entry_a.get("ended"), entry_a)
        self.assertEqual("running", entry_b.get("status"),
                         f"Kind B wurde fälschlich beendet: {entry_b}")
        self.assertEqual(0, entry_b.get("ended"), entry_b)
        self.assertIn("B-läuft", str(entry_b.get("output") or ""), entry_b)
        self.assertEqual(MAIN_SESSION_b11, self.state()["session"])


class NoInventionTest(StreamRelayFixture):
    """AK7: ohne Kind-Ereignisse entstehen keine Subagenten."""

    def test_events_without_child_sessions_invent_no_subagents(self):
        """AK7: nur Hauptsession-Ereignisse erzeugen keine Subagenten.

        Vorbedingung: leerer Zustand.
        Aktion: Text, Denken und gewöhnliches Werkzeug der Hauptsession.
        Erwartung: Kein Subagenteneintrag; Hauptsession bleibt erfasst.
        Fehlerfall: Erfundene Subagenten.
        """
        self.feed([
            relay_text_event(MAIN_SESSION_b11, "Haupttext"),
            reasoning_event(MAIN_SESSION_b11, "Hauptdenken"),
            tool_event(MAIN_SESSION_b11, "bash", "git status"),
        ])

        state = self.state()
        self.assertEqual(MAIN_SESSION_b11, state["session"], state)
        self.assertEqual([], state["subagents"],
                         "Der Filter hat Subagenten erfunden: "
                         + json.dumps(state, ensure_ascii=False))


class RobustnessTest(StreamRelayFixture):
    """AK7: defekte Zeilen schaden der Erfassung nicht."""

    def test_broken_lines_do_not_break_capture(self):
        """AK7: defekte JSON-Zeile, danach Kind-Ereignis.

        Vorbedingung: Hauptsession erfasst.
        Aktion: Zeile "{kaputt" und anschließend ein Kind-Text.
        Erwartung: Kein Absturz; Kind wird laufend erfasst; die defekte Zeile
        bleibt im Klartext sichtbar; Zustandsdatei ist gültiges JSON.
        Fehlerfall: Ausnahme, verlorene Erfassung oder beschädigter Zustand.
        """
        self.establish_main()

        emitted = self.feed(
            [relay_text_event(CHILD_A, "TROTZ-FEHLER-4711")], raw_lines=["{kaputt"])

        self.assertTrue(any("kaputt" in line for line in emitted),
                        "Die defekte Zeile verschwand aus dem Klartext: "
                        + repr(emitted))
        entry = self.entry(CHILD_A)
        self.assertIsNotNone(entry, "Kind nach defekter Zeile nicht erfasst")
        self.assertIn("TROTZ-FEHLER-4711", str(entry.get("output") or ""))
        json.loads(self.state_path.read_text(encoding="utf-8"))


class BoundedStateTest(StreamRelayFixture):
    """AK6/7: Zustandsdatei wächst nicht unbegrenzt."""

    def test_state_file_stays_bounded_with_many_finished_subagents(self):
        """AK6/7: viele abgeschlossene Kinder bleiben begrenzt.

        Vorbedingung: Hauptsession erfasst.
        Aktion: 60 Kinder mit je 3 000 Zeichen Ausgabe abschließen, danach
        ein laufendes Kind.
        Erwartung: höchstens 50 Einträge, Datei unter 256 KiB, laufendes
        Kind vorhanden.
        Fehlerfall: unbegrenztes Wachstum oder Verlust des laufenden
        Eintrags.
        """
        self.establish_main()
        payload = "K" * 3000
        for index in range(60):
            child = f"ses_kind_{index:02d}"
            self.feed([
                relay_text_event(child, payload),
                completed_task_event(MAIN_SESSION_b11, child, payload),
            ])
        self.feed([relay_text_event(RUNNING_C, "LAUFEND-4711")])

        state = self.state()
        entries = state["subagents"]
        self.assertLessEqual(
            len(entries), 50,
            f"Die Zustandsdatei hält {len(entries)} Einträge und wächst "
            f"unbegrenzt: {sorted(item.get('session') for item in entries)[:5]} …")
        size = self.state_path.stat().st_size
        self.assertLess(
            size, 256 * 1024,
            f"Die Zustandsdatei ist mit {size} Bytes unbegrenzt gewachsen")
        running = self.entry(RUNNING_C)
        self.assertIsNotNone(
            running, "Der laufende Subagent wurde beim Begrenzen entfernt")
        self.assertEqual("running", running.get("status"), running)


class AttemptContextTest(StreamRelayFixture):
    """Review Minor 2: Erfassung mit gesetztem ``attempt``-Kontext.

    Der Produktionspfad (``vibe-run.sh``) ruft den Filter immer mit
    ``--attempt`` auf. Diese Fälle prüfen die Pinning- und Kind-Erfassung
    des Versuchsmodus direkt statt nur über die F25-Suite:

    * Das erste Ereignis des Stroms pinnt die Hauptsession des Versuchs.
    * Abweichende Sessions werden als laufende Kinder erfasst.
    * Innerhalb eines Stroms bleibt die Hauptsession bestehen (erstes
      Ereignis gewinnt); ein zweiter Versuch (neuer ``stream_events``-Aufruf)
      ersetzt die Hauptsession („zuletzt gewinnt“), ohne ein Kind zu
      erzeugen.
    """

    VERSUCH_1 = "ses_versuch_eins"
    VERSUCH_2 = "ses_versuch_zwei"

    def feed_attempt(self, events):
        payload = "\n".join(
            json.dumps(event, ensure_ascii=False) for event in events) + "\n"
        emitted = []
        vibe_runs.stream_events(
            io.StringIO(payload), emitted.append, str(self.state_path),
            attempt=True)
        return emitted

    def test_attempt_pins_the_first_session_and_takes_others_as_children(self):
        """Mit attempt: erstes Ereignis pinnt, Kinder werden erfasst.

        Vorbedingung: leerer Zustand.
        Aktion: Strom 1 (``attempt=True``) mit erstem Ereignis
        ses_versuch_eins, danach Kind ses_kind_a; Strom 2 (neuer Aufruf,
        ``attempt=True``) mit ses_versuch_zwei.
        Erwartung: Nach Strom 1 ist ses_versuch_eins die Hauptsession und
        ses_kind_a ein laufender Eintrag mit Ausgabe; nach Strom 2 ist
        ses_versuch_zwei die Hauptsession, ohne dass dafür ein Kind-Eintrag
        entsteht; das erfasste Kind bleibt erhalten.
        Fehlerfall: Das Kind wird als Hauptsession übernommen, das Kind
        fehlt, oder der zweite Versuch wird als Kind erfasst.
        """
        self.feed_attempt([
            relay_text_event(self.VERSUCH_1, "Versuch eins"),
            relay_text_event(CHILD_A, "Kind arbeitet"),
        ])

        state = self.state()
        self.assertEqual(
            self.VERSUCH_1, state["session"],
            "Das erste Ereignis pinnte nicht die Hauptsession des Versuchs: "
            + json.dumps(state, ensure_ascii=False))
        entry = self.entry(CHILD_A)
        self.assertIsNotNone(
            entry, "Die abweichende Session wurde nicht als Kind erfasst: "
            + json.dumps(state, ensure_ascii=False))
        self.assertEqual("running", entry.get("status"), entry)
        self.assertIn("Kind arbeitet", str(entry.get("output") or ""), entry)

        self.feed_attempt([relay_text_event(self.VERSUCH_2, "Versuch zwei")])

        state = self.state()
        self.assertEqual(
            self.VERSUCH_2, state["session"],
            "Der zweite Versuch hat die Hauptsession nicht ersetzt: "
            + json.dumps(state, ensure_ascii=False))
        sessions = [item.get("session") for item in state["subagents"]]
        self.assertNotIn(
            self.VERSUCH_2, sessions,
            "Die neue Hauptsession wurde fälschlich als Kind erfasst: "
            + json.dumps(sessions, ensure_ascii=False))
        self.assertIn(
            CHILD_A, sessions,
            "Das zuvor erfasste Kind ging beim Versuchswechsel verloren: "
            + json.dumps(sessions, ensure_ascii=False))


class OutputBudgetTest(StreamRelayFixture):
    """Review Medium 3: Ausgabebudget je Subagent-Eintrag.

    Vereinbarte Semantik: Der gespeicherte ``output`` eines Eintrags bleibt
    auf einen Tail von höchstens 64 KiB begrenzt (Anfang verworfen, Ende
    erhalten). Die Begrenzung betrifft abgelaufene Inhalte; laufende
    Einträge behalten den jeweils letzten Stand. Die Gesamtdatei bleibt
    dadurch begrenzt. ``/api/subagents`` liefert ``output`` höchstens als
    Tail von 4 KiB (eigener Fall in ``test_b11_output_view_api.py``);
    ``/api/subagent-output`` bleibt das vollwertige Live-Pfadangebot.
    """

    TAIL_BUDGET = 64 * 1024

    def test_huge_child_output_is_kept_only_as_a_tail(self):
        """Große Kind-Ausgabe wird nur als 64-KiB-Tail gespeichert.

        Vorbedingung: Hauptsession erfasst; ein Kind läuft.
        Aktion: mehrere Kind-Ereignisse mit zusammen deutlich über 64 KiB
        Ausgabe; das erste enthält ANFANG-4711, das letzte ENDE-4711;
        danach Abschluss mit leerer Ergebnis-Ausgabe.
        Erwartung: Die gespeicherte Ausgabe bleibt auf 64 KiB begrenzt,
        der Anfang ist verworfen, das Ende erhalten; die Zustandsdatei
        bleibt unter 256 KiB; nach dem Abschluss gilt die Begrenzung
        weiterhin und der Eintrag ist ``completed``.
        Fehlerfall: Unbegrenztes Wachstum des ``output``-Felds oder
        Verlust des Endes.
        """
        self.establish_main()

        # Ein Strom wie der Produktionspfad: Hauptsession- und Kind-Ereignisse
        # durchmischt. (Ein Strom mit ausschließlich Text einer einzigen
        # fremden Session wäre laut F25-Kompatibilität ein neuer Versuch und
        # würde die Hauptsession ersetzen.)
        events = [relay_text_event(CHILD_A, "ANFANG-4711 " + "a" * 8000)]
        for index in range(24):
            events.append(relay_text_event(MAIN_SESSION_b11, "Haupt weiter %d" % index))
            events.append(
                relay_text_event(CHILD_A, "BLOCK-%02d-4711 %s" % (index, "b" * 10000)))
        events.append(relay_text_event(MAIN_SESSION_b11, "Haupt fertig"))
        events.append(relay_text_event(CHILD_A, "ENDE-4711"))
        events.append(completed_task_event(MAIN_SESSION_b11, CHILD_A, ""))
        self.feed(events)

        entry = self.entry(CHILD_A)
        self.assertIsNotNone(entry, "Das Kind wurde nicht erfasst")
        self.assertEqual("completed", entry.get("status"), entry)
        output = str(entry.get("output") or "")
        size = len(output.encode("utf-8"))
        self.assertLessEqual(
            size, self.TAIL_BUDGET,
            "Die gespeicherte Ausgabe ist mit %d Bytes unbegrenzt gewachsen"
            % size)
        self.assertNotIn(
            "ANFANG-4711", output,
            "Der Anfang wurde nicht verworfen (Tail-Semantik)")
        self.assertIn(
            "ENDE-4711", output,
            "Das Ende der Ausgabe ging verloren:\n" + output[-200:])
        state_size = self.state_path.stat().st_size
        self.assertLess(
            state_size, 256 * 1024,
            "Die Zustandsdatei ist mit %d Bytes unbegrenzt gewachsen"
            % state_size)


# ===========================================================================
# Unit-Abnahme: Hintergrund-Subagenten bleiben sichtbar
# ===========================================================================

import base64
import http.client
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(BIN))

import vibe_runs  # noqa: E402

MAIN_SESSION_b12 = "ses_main_b12"
AGENT = "code-reviewer"
DESCRIPTION = "Reviewer-Verfügbarkeit prüfen"
PROMPT = "Prüfe die Reviewer-Verfügbarkeit."
BACKGROUND_OUTPUT = (
    "The subagent is working in the background "
    "(sessionID: ses_kind_a). You will receive a <subagent> message "
    "when it goes idle."
)
TAIL_BUDGET = 64 * 1024
SERVER_CREDENTIAL = "geheim-B12-4711"


# ---------------------------------------------------------------------------
# Teil 1: Ereignisübersetzung (vibe_runs.translate_event / stream_events)
# ---------------------------------------------------------------------------

def background_text_event(session, text):
    return {"type": "text", "sessionID": session,
            "part": {"type": "text", "text": text}}


def subagent_task_event(session, child, metadata, status="completed",
                        agent=AGENT, description=DESCRIPTION, output=""):
    """Ein task/subagent-Werkzeugereignis der Hauptsession.

    ``metadata`` ist der Wert von ``part.state.metadata``; ``status`` der Wert
    von ``part.state.status``. opencode ≥ 2.3 liefert die flache Form
    ``{"sessionID": <kind>, "status": "running"}`` mit ``status="completed"``
    am Zustand; ältere Stände verschachteln ``metadata.metadata`` ohne
    Statusfeld.
    """
    return {
        "type": "tool_use",
        "sessionID": session,
        "part": {
            "tool": "task",
            "state": {
                "status": status,
                "input": {
                    "agent": agent,
                    "description": description,
                    "prompt": PROMPT,
                },
                "metadata": metadata,
                "output": output,
            },
        },
    }


class TranslateFixture(unittest.TestCase):
    """Direkter Aufruf der Übersetzung mit einem Zustand im Speicher."""

    def setUp(self):
        self.state = {"session": "", "subagents": []}

    def feed(self, events):
        """Wendet Ereignisse nacheinander an und sammelt die Zeilen."""
        lines = []
        for event in events:
            event_lines, _changed = vibe_runs.translate_event(event, self.state)
            lines.extend(event_lines)
        return lines

    def entry(self, session):
        return next((item for item in self.state["subagents"]
                     if item.get("session") == session), None)

    def establish_main(self):
        self.feed([background_text_event(MAIN_SESSION_b12, "Hauptagent arbeitet")])


class BackgroundSubagentTest(TranslateFixture):
    """AK1: Metadaten-Status macht den Hintergrund-Subagenten sichtbar."""

    def test_flat_running_metadata_keeps_background_subagent_running(self):
        """AK1/AK5: Hintergrund-Subagent läuft, Zeile zeigt running.

        Vorbedingung: Hauptsession erfasst; opencode ≥ 2.3-Form.
        Aktion: tool_use der Hauptsession, Werkzeug ``task``,
        ``state.status="completed"``, ``state.metadata={"sessionID":
        ses_kind_a, "status": "running"}``, Tool-Output als Text.
        Erwartung: Genau ein Eintrag mit session=ses_kind_a, status
        "running", ended 0, gestartet gesetzt, Agent/Beschreibung/Prompt aus
        state.input; Ausgabe enthält den Tool-Output; Hauptsession
        unverändert; Zeile "[Subagent] code-reviewer: … — running", keine
        Subagentenzeile mit "— completed".
        Fehlerfall: Eintrag erscheint als "completed" (Aktueller Fehler) oder
        die Hauptsession wird verändert.
        """
        self.establish_main()

        lines = self.feed([subagent_task_event(
            MAIN_SESSION_b12, CHILD_A,
            {"sessionID": CHILD_A, "status": "running"},
            status="completed", output=BACKGROUND_OUTPUT)])

        state = self.state
        self.assertEqual(MAIN_SESSION_b12, state["session"], state)
        self.assertEqual(
            1, len(state["subagents"]),
            "Es muss genau einen Subagenteneintrag geben: "
            + json.dumps(state, ensure_ascii=False))
        entry = self.entry(CHILD_A)
        self.assertIsNotNone(entry, "Kein Eintrag für die Kind-Session: "
                             + json.dumps(state, ensure_ascii=False))
        self.assertEqual(
            "running", entry.get("status"),
            "Der Hintergrund-Subagent gilt fälschlich als abgeschlossen: "
            + json.dumps(entry, ensure_ascii=False))
        self.assertEqual(0, entry.get("ended"),
                         "Ein laufender Eintrag darf kein ended haben: "
                         + json.dumps(entry, ensure_ascii=False))
        self.assertIsInstance(entry.get("started"), int, entry)
        self.assertEqual(AGENT, entry.get("agent"), entry)
        self.assertEqual(DESCRIPTION, entry.get("description"), entry)
        self.assertEqual(PROMPT, entry.get("prompt"), entry)
        self.assertIn("The subagent is working in the background",
                      str(entry.get("output") or ""), entry)
        self.assertIn(
            f"[Subagent] {AGENT}: {DESCRIPTION} — running", lines, lines)
        completed_lines = [line for line in lines
                           if line.startswith("[Subagent]")
                           and line.rstrip().endswith("— completed")]
        self.assertEqual([], completed_lines,
                         "Die Subagentenzeile meldet einen Abschluss: "
                         + repr(completed_lines))

    def test_stream_filter_publishes_running_subagent_line(self):
        """AK1/AK5: Der Stream-Filter gibt die laufende Zeile aus.

        Vorbedingung: leerer Zustand; Aufruf über ``stream_events`` wie in der
        Produktion.
        Aktion: Hauptsession-Text, danach das opencode-2.3-task-Ereignis mit
        Metadaten-Status "running".
        Erwartung: Der Ausgabestrom enthält genau eine Subagentenzeile und sie
        endet auf "— running"; die Zustandsdatei hält einen laufenden Eintrag.
        Fehlerfall: Die Zeile meldet "— completed" (Aktueller Fehler) oder der
        Eintrag wird als abgeschlossen gespeichert.
        """
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "proj.log.state.json"
            payload = "\n".join(json.dumps(event, ensure_ascii=False)
                                for event in [
                                    background_text_event(MAIN_SESSION_b12, "Hauptagent"),
                                    subagent_task_event(
                                        MAIN_SESSION_b12, CHILD_A,
                                        {"sessionID": CHILD_A,
                                         "status": "running"},
                                        status="completed",
                                        output=BACKGROUND_OUTPUT),
                                ]) + "\n"
            emitted = []
            vibe_runs.stream_events(
                io.StringIO(payload), emitted.append, str(state_path))

            # Strukturkorrektur (Coding-Agent-Rückmeldung): Die Zustandsdatei
            # wird noch innerhalb des TemporaryDirectory gelesen und geprüft;
            # nach dem Verlassen wäre sie bereits gelöscht. Die fachlichen
            # Assertionen bleiben unverändert.
            self.assertIn(
                f"[Subagent] {AGENT}: {DESCRIPTION} — running", emitted,
                emitted)
            subagent_lines = [line for line in emitted
                              if line.startswith("[Subagent]")]
            self.assertEqual(
                1, len(subagent_lines),
                "Es soll genau eine Subagentenzeile geben: " + repr(emitted))
            state = vibe_runs.load_subagent_state(str(state_path))
            entry = next(
                (item for item in state["subagents"]
                 if item.get("session") == CHILD_A), None)
            self.assertIsNotNone(entry, "Kein Eintrag in der Zustandsdatei: "
                                 + json.dumps(state, ensure_ascii=False))
            self.assertEqual("running", entry.get("status"), entry)
            self.assertEqual(0, entry.get("ended"), entry)

    def test_background_subagent_output_is_tail_capped(self):
        """AK1: Auch die Hintergrund-Ausgabe bleibt ein 64-KiB-Tail.

        Vorbedingung: Hauptsession erfasst.
        Aktion: task-Ereignis mit rund 70 KiB Ausgabe (ANFANG-4711 am Anfang,
        ENDE-4711 am Ende) und Metadaten-Status "running".
        Erwartung: gespeicherte Ausgabe höchstens 64 KiB, Anfang verworfen,
        Ende erhalten; Status bleibt "running".
        Fehlerfall: Unbegrenztes Wachstum oder Verlust des Endes.
        """
        self.establish_main()
        huge = ("ANFANG-4711\n" + "m" * 70_000 + "\nENDE-4711")

        self.feed([subagent_task_event(
            MAIN_SESSION_b12, CHILD_A, {"sessionID": CHILD_A, "status": "running"},
            status="completed", output=huge)])

        entry = self.entry(CHILD_A)
        self.assertIsNotNone(entry, "Kein Eintrag für die Kind-Session")
        output = str(entry.get("output") or "")
        self.assertLessEqual(
            len(output.encode("utf-8")), TAIL_BUDGET,
            "Die gespeicherte Ausgabe ist mit %d Bytes unbegrenzt" % len(output))
        self.assertNotIn("ANFANG-4711", output,
                         "Der Anfang wurde nicht verworfen (Tail-Semantik)")
        self.assertIn("ENDE-4711", output,
                      "Das Ende der Ausgabe ging verloren:\n" + output[-200:])
        self.assertEqual("running", entry.get("status"), entry)


class SyncLegacyBehaviorTest(TranslateFixture):
    """AK2: Synchrones und Alt-Verhalten ändert sich nicht."""

    def test_alt_metadata_without_status_stays_completed(self):
        """AK2: Alt-Form ohne Statusfeld bleibt completed.

        Vorbedingung: Hauptsession erfasst; opencode ≤ 2.2.6-Form.
        Aktion: task-Ereignis, ``state.status="completed"``, Metadaten
        ``{"metadata": {"sessionID": ses_kind_a}}`` ohne Statusfeld.
        Erwartung: Eintrag status "completed" mit ended > 0; Zeile meldet
        "— completed".
        Fehlerfall: Der Eintrag wird laufend gehalten oder endet nie.
        """
        self.establish_main()

        lines = self.feed([subagent_task_event(
            MAIN_SESSION_b12, CHILD_A, {"metadata": {"sessionID": CHILD_A}},
            status="completed", output="FERTIG-A")])

        entry = self.entry(CHILD_A)
        self.assertIsNotNone(entry, "Kein Eintrag für die Kind-Session")
        self.assertEqual("completed", entry.get("status"), entry)
        self.assertNotEqual(0, entry.get("ended"),
                            "Ein abgeschlossener Eintrag braucht ended: "
                            + json.dumps(entry, ensure_ascii=False))
        self.assertIn(
            f"[Subagent] {AGENT}: {DESCRIPTION} — completed", lines, lines)

    def test_flat_metadata_with_explicit_status_follows_it(self):
        """AK2: Flache Metadaten mit bekanntem Status gelten weiter.

        Vorbedingung: Hauptsession erfasst.
        Aktion: task-Ereignis mit flachen Metadaten
        ``{"sessionID": ses_kind_a, "status": "completed"}`` und
        ``state.status="completed"``.
        Erwartung: Eintrag status "completed" mit ended > 0.
        Fehlerfall: Die Metadaten werden ignoriert oder der Eintrag bleibt
        fälschlich laufend.
        """
        self.establish_main()

        self.feed([subagent_task_event(
            MAIN_SESSION_b12, CHILD_A,
            {"sessionID": CHILD_A, "status": "completed"},
            status="completed", output="FERTIG-A")])

        entry = self.entry(CHILD_A)
        self.assertIsNotNone(entry, "Kein Eintrag für die Kind-Session")
        self.assertEqual("completed", entry.get("status"), entry)
        self.assertNotEqual(0, entry.get("ended"), entry)

    def test_metadata_without_known_status_falls_back_to_tool_state(self):
        """AK2/Fehlerfall: Unbekannter oder fehlender Status → state.status.

        Vorbedingung: Hauptsession erfasst.
        Aktion: Erst flache Metadaten ohne Statusfeld, dann mit unbekanntem
        Statuswert "wartet-auf-freigabe"; beide mit
        ``state.status="completed"``.
        Erwartung: Beide Male Eintrag status "completed" mit ended > 0; kein
        laufender Eintrag.
        Fehlerfall: Ein unbekannter Statuswert hält den Eintrag künstlich
        am Laufen.
        """
        self.establish_main()

        self.feed([subagent_task_event(
            MAIN_SESSION_b12, CHILD_A, {"sessionID": CHILD_A},
            status="completed", output="FERTIG-A")])
        entry = self.entry(CHILD_A)
        self.assertEqual("completed", entry.get("status"), entry)
        self.assertNotEqual(0, entry.get("ended"), entry)

        self.feed([subagent_task_event(
            MAIN_SESSION_b12, CHILD_B,
            {"sessionID": CHILD_B, "status": "wartet-auf-freigabe"},
            status="completed", output="FERTIG-B")])
        entry_b = self.entry(CHILD_B)
        self.assertIsNotNone(entry_b, "Kein Eintrag für ses_kind_b")
        self.assertEqual("completed", entry_b.get("status"), entry_b)
        self.assertNotEqual(0, entry_b.get("ended"), entry_b)
        self.assertEqual("completed", self.entry(CHILD_A).get("status"),
                         "Der erste Eintrag wurde verändert")


class RevivalTest(TranslateFixture):
    """AK3: Kind-Ereignisse nach Abschluss beleben den Eintrag wieder."""

    def test_finished_entry_is_revived_by_later_child_events(self):
        """AK3: Abschluss + nachfolgende Kind-Ereignisse → wieder running.

        Vorbedingung: Hauptsession erfasst; ses_kind_a über das Alt-Form-
        task-Ereignis abgeschlossen, ses_kind_b (anderes Kind) ebenfalls
        abgeschlossen.
        Aktion: Danach text-, reasoning- und tool_use-Ereignisse von
        ses_kind_a.
        Erwartung: ses_kind_a ist wieder status "running" mit ended 0; die
        Ausgabe enthält den alten Abschluss-Text und die neuen Teilausgaben;
        ses_kind_b bleibt unverändert "completed".
        Fehlerfall: Der Eintrag bleibt abgeschlossen (Aktueller Fehler), die
        Ausgabe geht verloren oder ses_kind_b wird mitbelebt.
        """
        self.establish_main()
        self.feed([
            subagent_task_event(
                MAIN_SESSION_b12, CHILD_A, {"metadata": {"sessionID": CHILD_A}},
                status="completed", output="ABSCHLUSS-A-4711"),
            subagent_task_event(
                MAIN_SESSION_b12, CHILD_B, {"metadata": {"sessionID": CHILD_B}},
                status="completed", output="ABSCHLUSS-B-4711"),
        ])
        self.assertEqual("completed", self.entry(CHILD_A).get("status"))
        self.assertEqual("completed", self.entry(CHILD_B).get("status"))

        self.feed([
            background_text_event(CHILD_A, "NACHLESE-4711"),
            reasoning_event(CHILD_A, "Kind denkt erneut nach"),
            {"type": "tool_use", "sessionID": CHILD_A,
             "part": {"tool": "bash",
                      "state": {"status": "running",
                                "input": {"command": "git status"}}}},
        ])

        entry_a = self.entry(CHILD_A)
        self.assertEqual(
            "running", entry_a.get("status"),
            "Der abgeschlossene Eintrag wurde durch Kind-Ereignisse nicht "
            "wiederbelebt: " + json.dumps(entry_a, ensure_ascii=False))
        self.assertEqual(0, entry_a.get("ended"),
                         "Der wiederbelebte Eintrag darf kein ended haben: "
                         + json.dumps(entry_a, ensure_ascii=False))
        output = str(entry_a.get("output") or "")
        for expected in ("ABSCHLUSS-A-4711", "NACHLESE-4711",
                         "[Denken] Kind denkt erneut nach",
                         "[Werkzeug] bash", "git status"):
            self.assertIn(expected, output,
                          f"Ausgabeteil {expected!r} fehlt:\n{output[-300:]}")
        entry_b = self.entry(CHILD_B)
        self.assertEqual(
            "completed", entry_b.get("status"),
            "Das unbelebte Kind wurde fälschlich verändert: "
            + json.dumps(entry_b, ensure_ascii=False))
        self.assertNotEqual(0, entry_b.get("ended"), entry_b)


# ---------------------------------------------------------------------------
# Teil 2: Dashboard-Herabstufung (/api/subagents, AK4)
# ---------------------------------------------------------------------------

WEB = REPO / "bin" / "vibe-web.py"
RUNS_PY = REPO / "bin" / "vibe_runs.py"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """Lokaler opencode-Testserver ohne Modellaufrufe.

    ``GET /api/session?limit=100`` liefert die Session-Liste aus
    ``sessions_path``; ``GET /api/session/active`` die Aktivkarte aus
    ``active_path``. Mit ``fail`` wird jede Anfrage mit 500 beantwortet
    („Server unbrauchbar“). Jede Anfrage wird protokolliert.
    """

    context = None

    def log_message(self, *args):
        return

    def _record(self):
        with open(self.context["record_path"], "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "method": self.command,
                "path": self.path,
                "auth_ok": self._auth_ok(),
            }, ensure_ascii=False) + "\n")

    def _auth_ok(self):
        try:
            password = Path(self.context["credential_path"]).read_text(
                encoding="utf-8").strip()
        except OSError:
            return False
        encoded = base64.b64encode(("opencode:" + password).encode()).decode()
        return self.headers.get("Authorization", "") == "Basic " + encoded

    def _read_json(self, key, fallback):
        try:
            return json.loads(Path(self.context[key]).read_text(
                encoding="utf-8"))
        except (OSError, ValueError, KeyError):
            return fallback

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._record()
        if not self._auth_ok():
            self._send_json(401, {"ok": False})
            return
        if self.context.get("fail"):
            self._send_json(500, {"ok": False})
            return
        if "/api/session/active" in self.path:
            payload = self._read_json("active_path", {"data": {}})
        elif "/api/session" in self.path:
            payload = self._read_json("sessions_path", {"data": []})
        else:
            payload = {"ok": True}
        self._send_json(200, payload)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self._record()
        if self._auth_ok():
            self._send_json(200, {"ok": True})
        else:
            self._send_json(401, {"ok": False})


def make_fake_handler(context):
    def build():
        handler = type("BoundHandler", (BaseHTTPRequestHandler,), {})
        for attribute, value in _FakeOpenCodeHandler.__dict__.items():
            if not attribute.startswith("__"):
                setattr(handler, attribute, value)
        handler.context = context
        return handler
    return build()


FAKE_TMUX = r'''#!/usr/bin/env python3
"""Zeichnet tmux-Aufrufe auf; verhält sich wie ein frischer Server."""
import json
import os
import sys

args = sys.argv[1:]
if args[:1] == ["-L"] and len(args) > 1:
    args = args[2:]
path = os.environ.get("FAKE_TMUX_LOG")
if path:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"args": args}, ensure_ascii=False) + "\n")
if args[:1] == ["has-session"]:
    sys.exit(1)
if args[:1] == ["show-environment"]:
    sys.stdout.write("unknown variable: VIBE_MANAGED\n")
    sys.exit(1)
sys.exit(0)
'''


class DashboardFixture(unittest.TestCase):
    """Dashboard, isoliertes Projekt, tmux- und opencode-Attrappe."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        cls.project.mkdir()
        (cls.project / ".vibe").mkdir()
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=test-agent\nTESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL="true"\n',
            encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] B12 Hintergrund-Subagenten\n"
            "  Beschreibung: Test\n",
            encoding="utf-8")
        agent_path = cls.project / ".opencode" / "agents" / "test-agent.md"
        agent_path.parent.mkdir(parents=True)
        agent_path.write_text(
            "---\ndescription: Testagent\nmode: primary\n---\n"
            "Du bist der Coding-Agent der Arbeitspakete.\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", "-b", "main", str(cls.project)],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(cls.project), "config", "user.name",
                        "Test"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(cls.project), "config", "user.email",
                        "test@example.invalid"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(cls.project), "add", "-A"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(cls.project), "commit", "-q", "-m",
                        "Ausgangsstand"], check=True, capture_output=True)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        for name in ("test-agent", "code-reviewer"):
            (cls.agents / (name + ".md")).write_text(
                "---\ndescription: Testagent\nmode: primary\n---\n"
                "Du bist der Coding-Agent der Arbeitspakete.\n",
                encoding="utf-8")
        cls.fakebin = cls.root / "fakebin"
        cls.fakebin.mkdir()
        tmux = cls.fakebin / "tmux"
        tmux.write_text(FAKE_TMUX, encoding="utf-8")
        tmux.chmod(0o755)
        cls.tmux_log = cls.root / "tmux.log"
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.port = free_port()
        cls.oc_port = free_port()
        cls.context = {
            "credential_path": str(cls.log_dir / "opencode.password"),
            "record_path": str(cls.root / "fake-opencode.requests.jsonl"),
            "sessions_path": str(cls.root / "sessions.json"),
            "active_path": str(cls.root / "active.json"),
            "fail": False,
        }
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), make_fake_handler(cls.context))
        cls._fake_http.daemon_threads = True
        cls._fake_thread = threading.Thread(target=cls._fake_http.serve_forever)
        cls._fake_thread.daemon = True
        cls._fake_thread.start()
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.env = cls.build_env()
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=cls.env,
            stdout=cls.server_log, stderr=subprocess.STDOUT, text=True)
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 30
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                            ("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: "
                    + (cls.root / "web-server.log").read_text(
                        encoding="utf-8", errors="replace"))
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()

    @classmethod
    def build_env(cls):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_") or key in (
                    "TMUX", "TMUX_PANE"):
                env.pop(key, None)
        (cls.root / "tmp").mkdir(exist_ok=True)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_OPENCODE_PORT": str(cls.oc_port),
            "VIBE_INSTALL": str(cls.root / "_toolchain"),
            "VIBE_RUNTIME": str(cls.log_dir),
            "VIBE_STATE": str(cls.state_dir),
            "VIBE_AGENTS_DIR": str(cls.agents),
            "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
            "VIBE_STORAGE_LOCK_DIR": str(cls.home / "locks"),
            "HOME": str(cls.home),
            "XDG_CONFIG_HOME": str(cls.home / ".config"),
            "TMPDIR": str(cls.root / "tmp"),
            "PATH": str(cls.fakebin) + os.pathsep + env.get("PATH", ""),
            "FAKE_TMUX_LOG": str(cls.tmux_log),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        return env

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        cls.server_log.close()
        try:
            cls._fake_http.shutdown()
            cls._fake_http.server_close()
            cls._fake_thread.join(timeout=5)
        except Exception:
            pass
        cls.tmp.cleanup()

    # ---------- Helfer ----------

    def setUp(self):
        for path in (self.log_dir / "proj.log.state.json",
                     self.log_dir / "runs.json",
                     self.state_dir / "harness.json",
                     self.tmux_log,
                     self.log_dir / "opencode.password",
                     Path(self.context["record_path"]),
                     Path(self.context["sessions_path"]),
                     Path(self.context["active_path"])):
            if path.exists():
                path.unlink()
        self.context["fail"] = False

    def tearDown(self):
        self.context["fail"] = False

    def register_run(self, state="running"):
        result = subprocess.run([
            sys.executable, str(RUNS_PY), "start",
            "--runtime", str(self.log_dir),
            "--project", str(self.project.resolve()),
            "--name", "proj", "--key", "proj", "--agent", "test-agent",
            "--state", state,
        ], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0,
                         "Vorbedingung Laufregister fehlgeschlagen: "
                         + result.stdout + result.stderr)

    def password_private(self, value=SERVER_CREDENTIAL):
        path = self.log_dir / "opencode.password"
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
        return path

    def write_state(self, entry):
        """Legt Zustandsdatei mit Hauptsession und einem Eintrag an."""
        now = int(time.time())
        entry = dict(entry)
        entry.setdefault("session", CHILD_A)
        entry.setdefault("agent", AGENT)
        entry.setdefault("description", DESCRIPTION)
        entry.setdefault("prompt", PROMPT)
        entry.setdefault("status", "running")
        entry.setdefault("started", now + 2)
        entry.setdefault("ended", 0)
        entry.setdefault("output", "B12-LIVE-AUSGABE")
        path = self.log_dir / "proj.log.state.json"
        path.write_text(json.dumps(
            {"session": MAIN_SESSION_b12, "subagents": [entry]},
            ensure_ascii=False), encoding="utf-8")
        return path

    def write_server_view(self, child_known=True, child_active=False):
        """Bestimmt, was die opencode-Attrappe über die Kind-Session meldet."""
        sessions = []
        if child_known:
            sessions.append({
                "id": CHILD_A,
                "parentID": MAIN_SESSION_b12,
                "agent": AGENT,
                "title": DESCRIPTION,
                "time": {"created": 1700000000000, "updated": 1700000005000},
            })
        Path(self.context["sessions_path"]).write_text(
            json.dumps({"data": sessions}, ensure_ascii=False),
            encoding="utf-8")
        active = {CHILD_A: {"type": "running"}} if child_active else {}
        Path(self.context["active_path"]).write_text(
            json.dumps({"data": active}, ensure_ascii=False),
            encoding="utf-8")

    def request(self, method, path, body=None):
        encoded = (json.dumps(body, ensure_ascii=False).encode("utf-8")
                   if body is not None else None)
        headers = {
            "Host": f"127.0.0.1:{self.port}",
            "X-Token": self.token,
            "Origin": f"http://127.0.0.1:{self.port}",
            "Sec-Fetch-Site": "same-origin",
        }
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.port, timeout=20)
        try:
            connection.request(method, path, body=encoded, headers=headers)
            response = connection.getresponse()
            text = response.read().decode("utf-8", "replace")
            try:
                payload = json.loads(text)
            except ValueError:
                payload = None
            return response.status, payload, text
        finally:
            connection.close()

    def get_subagents(self):
        return self.request("GET", "/api/subagents?name=proj")

    def list_entries(self):
        status, data, raw = self.get_subagents()
        self.assertEqual(200, status, raw)
        self.assertTrue(
            bool(data) and data.get("ok") is True,
            "Die Subagentenliste sollte geliefert werden: " + raw)
        return [entry for entry in (data or {}).get("subagents") or []]

    def requests(self):
        path = Path(self.context["record_path"])
        if not path.exists():
            return []
        return [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines() if line.strip()]


class DashboardDowngradeTest(DashboardFixture):
    """AK4: Herabstufung am geteilten Server, Grenzen ohne Server."""

    def test_dashboard_downgrades_running_entry_when_child_is_known_and_inactive(
            self):
        """AK4a: Bekannte, inaktive Kind-Session → completed.

        Vorbedingung: laufender Registereintrag; Zustandsdatei mit
        Hauptsession und laufendem Eintrag ses_kind_a; opencode-Attrappe
        meldet ses_kind_a in /api/session (parentID = Hauptsession) und NICHT
        in /api/session/active.
        Aktion: GET /api/subagents.
        Erwartung: Der Eintrag erscheint mit status "completed".
        Fehlerfall: Der Eintrag bleibt "running" (Aktueller Fehler).
        """
        self.password_private()
        self.register_run("running")
        self.write_state({})
        self.write_server_view(child_known=True, child_active=False)

        entries = self.list_entries()

        matching = [entry for entry in entries
                    if entry.get("session") == CHILD_A]
        self.assertEqual(
            1, len(matching),
            "Der Eintrag der Kind-Session fehlt in der Liste: "
            + json.dumps(entries, ensure_ascii=False))
        self.assertEqual(
            "completed", matching[0].get("status"),
            "Der Hintergrund-Subagent wurde nach Serverlage nicht "
            "herabgestuft: " + json.dumps(matching[0], ensure_ascii=False))

    def test_dashboard_keeps_running_entry_when_child_is_active(self):
        """AK4b: Aktive Kind-Session bleibt running.

        Vorbedingung: wie AK4a, aber die Attrappe meldet ses_kind_a in
        /api/session/active mit type "running".
        Aktion: GET /api/subagents.
        Erwartung: Der Eintrag erscheint mit status "running".
        Fehlerfall: Fälschliche Herabstufung trotz Aktivität.
        """
        self.password_private()
        self.register_run("running")
        self.write_state({})
        self.write_server_view(child_known=True, child_active=True)

        entries = self.list_entries()

        matching = [entry for entry in entries
                    if entry.get("session") == CHILD_A]
        self.assertEqual(1, len(matching), json.dumps(entries, ensure_ascii=False))
        self.assertEqual(
            "running", matching[0].get("status"),
            "Der aktive Subagent wurde fälschlich beendet: "
            + json.dumps(matching[0], ensure_ascii=False))

    def test_dashboard_keeps_running_entry_without_password(self):
        """AK4c: Ohne Kennwort bleibt running, kein Serveraufruf.

        Vorbedingung: laufender Registereintrag und Zustandsdatei wie AK4a;
        keine Kennwortdatei; Attrappe meldet die Kind-Session als bekannt und
        inaktiv.
        Aktion: GET /api/subagents.
        Erwartung: Der Eintrag erscheint mit status "running"; es gab keinen
        HTTP-Aufruf an die opencode-Attrappe.
        Fehlerfall: Erfundener Abschluss oder Serverabfrage ohne Kennwort.
        """
        self.register_run("running")
        self.write_state({})
        self.write_server_view(child_known=True, child_active=False)

        entries = self.list_entries()

        matching = [entry for entry in entries
                    if entry.get("session") == CHILD_A]
        self.assertEqual(1, len(matching), json.dumps(entries, ensure_ascii=False))
        self.assertEqual(
            "running", matching[0].get("status"),
            "Ohne Kennwort darf kein Abschluss erfunden werden: "
            + json.dumps(matching[0], ensure_ascii=False))
        self.assertEqual(
            [], self.requests(),
            "Ohne Kennwort wurde trotzdem der Server gefragt: "
            + json.dumps(self.requests(), ensure_ascii=False))

    def test_dashboard_keeps_running_entry_when_server_fails(self):
        """AK4c/Fehlerfall: Unbrauchbarer Server erfundet keinen Abschluss.

        Vorbedingung: wie AK4a, aber die Attrappe beantwortet jede Anfrage
        mit 500 (Server unbrauchbar).
        Aktion: GET /api/subagents.
        Erwartung: Der Eintrag erscheint mit status "running".
        Fehlerfall: Ein Fehler wird still als Abschluss interpretiert.
        """
        self.password_private()
        self.register_run("running")
        self.write_state({})
        self.write_server_view(child_known=True, child_active=False)
        self.context["fail"] = True

        entries = self.list_entries()

        matching = [entry for entry in entries
                    if entry.get("session") == CHILD_A]
        self.assertEqual(1, len(matching), json.dumps(entries, ensure_ascii=False))
        self.assertEqual(
            "running", matching[0].get("status"),
            "Ein Serverfehler darf nicht als Abschluss gelten: "
            + json.dumps(matching[0], ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
