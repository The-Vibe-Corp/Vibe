"""Unit-Abnahme AP19 (Teil 2): Erfassung der Hauptsession im Protokollfilter.

Arbeitspaket AP19 verlangt, dass eine abgebrochene Session exakt
wiederhergestellt und fortgesetzt werden kann. Dafür muss die Hauptsession
eines Laufs überhaupt erst erfasst werden. Der Protokollfilter
``vibe_runs.py stream`` erhält deshalb optionale Argumente:

* ``--sessions <pfad>`` — Registerpfad (``<laufzeit>/sessions.json``),
* ``--session-project <pfad>``, ``--session-name <name>``,
  ``--session-run <id>``, ``--session-agent <agent>``,
  ``--session-harness <name>`` — Zusatzangaben des Eintrags.

Verbindliches Verhalten:

1. Nur mit ``--sessions`` wird das Register gepflegt. Ohne die Option bleibt
   der Filter byte-identisch (keine Datei, keine Ausgabeänderung) — das ist
   die Rückwärtskompatibilität für bestehende Aufrufer und Tests.
2. Erfasst wird ausschließlich die **Hauptsession**: beim ersten Erscheinen
   und bei einem Wechsel, einschließlich der „text-only“-Übernahme am
   Stromende. Kind-Sessions (Subagenten) und Pi-Session-Header erzeugen nie
   einen Eintrag.
3. Der Eintrag entsteht sofort beim Erscheinen der Hauptsession und bleibt
   auch dann erhalten, wenn der Ereignisstrom hart abgebrochen wird (AK5).
4. ``bin/vibe-run.sh`` übergibt die Argumente: vor ``register_start`` ohne
   Lauf-ID (Start-Preflight), danach erneut mit ``--session-run "$RUN_ID"``,
   damit Paket-, Reparatur- und Assistenzsessions die Lauf-ID tragen.

Geprüft wird über echte Prozessläufe des Filters mit Attrappen-Ereignissen
sowie über einen vollständigen Läuferlauf mit opencode-Attrappe
(``tests/unit/runner_support.py``). Es werden keine Modellaufrufe ausgeführt
und keine echten Projekte berührt.
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

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
RUNS = BIN / "vibe_runs.py"
RUNNER = BIN / "vibe-run.sh"

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


def text_event(session, text="Antwort"):
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
        self.run_stream([text_event("ses_attempt1", "Antwort 1")])

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
        self.run_stream([text_event("ses_attempt1")], run_id="lauf-4711")

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
            [text_event("ses_attempt1", "Antwort 1")], sessions=False
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
            text_event("ses_main", "Haupt"),
            text_event("ses_kind", "Kind"),
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
            [text_event("ses_neu", "Zweiter Versuch")], attempt=False
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
            process.stdin.write(json_line(text_event("ses_attempt1", "Anfang")))
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
        cls.text = RUNNER.read_text(encoding="utf-8")
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
            feedback="- [ ] AP19 Sessionerfassung\n  Beschreibung: Test\n",
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


if __name__ == "__main__":
    unittest.main()
