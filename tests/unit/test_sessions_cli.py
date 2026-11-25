"""Sitzungs-CLI: Listen, Filter, Limit und Fortsetzen.

Aufruf: python3 -m unittest tests.unit.test_sessions_cli -v
"""


# ===========================================================================
# Unit-Abnahme (Teil 3): CLI ``vibe sessions``
# ===========================================================================

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"
RUNS_PY = BIN / "vibe_runs.py"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support  # noqa: E402

PROJECT_ENV = (
    "TYPE=generic\n"
    "AGENT=test-agent\n"
    "TESTER=test-agent\n"
    "REVIEWER=code-reviewer\n"
    'VERIFY_PACKAGE="true"\n'
    'VERIFY_FULL="true"\n'
    "MAX_RETRIES=1\n"
)

# Aufzeichnende tmux-Attrappe: meldet nur die in FAKE_TMUX_LIVE genannten
# Sitzungen als vorhanden (kommagetrennt), sonst wie ein frischer Server.
FAKE_TMUX = r'''#!/usr/bin/env python3
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

live = [item.strip() for item in
        (os.environ.get("FAKE_TMUX_LIVE") or "").split(",") if item.strip()]
target = ""
if "-t" in args:
    position = args.index("-t")
    if position + 1 < len(args):
        target = args[position + 1]
if args[:1] == ["has-session"]:
    sys.exit(0 if target in live else 1)
if args[:1] == ["show-environment"]:
    sys.stdout.write("unknown variable: VIBE_MANAGED\n")
    sys.exit(1)
sys.exit(0)
'''


class SessionsCliFixture(unittest.TestCase):
    """Isolierter Arbeitsbereich mit zwei Projekten und Sessionregister."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        support.write_agents(cls.agents, "test-agent", "code-reviewer")
        cls.install = cls.root / "_toolchain"
        cls.install.mkdir(parents=True)
        (cls.install / "harness.json").unlink(missing_ok=True)
        cls.runtime = cls.root / "_logs"
        cls.state = cls.root / "_state"
        cls.runtime.mkdir(parents=True)
        cls.state.mkdir(parents=True)
        cls.projects = {}
        for name, title in (("proj", "AP19 Projekt"), ("zwei", "Zweites")):
            project = cls.root / name
            support.init_repo(project)
            support.write_project(
                project, PROJECT_ENV,
                feedback=[support.ticket_record(
                    "F1", title, type="feedback", description="Test")],
            )
            support.commit_all(project, "Ausgangsstand")
            cls.projects[name] = project
        cls.fakebin = cls.root / "fakebin"
        cls.fakebin.mkdir()
        tmux = cls.fakebin / "tmux"
        tmux.write_text(FAKE_TMUX, encoding="utf-8")
        tmux.chmod(0o755)
        cls.tmux_log = cls.root / "tmux.log"
        (cls.root / "tmp").mkdir(exist_ok=True)
        cls.addClassCleanup(cls.tmp.cleanup)
        cls._old_env = os.environ.copy()

    @classmethod
    def tearDownClass(cls):
        os.environ.clear()
        os.environ.update(cls._old_env)

    def setUp(self):
        # Frischer Zustand je Testfall.
        for path in (
            self.runtime / "sessions.json",
            self.runtime / "sessions.lock",
            self.runtime / "runs.json",
            self.runtime / "runs.lock",
            self.runtime / "opencode.password",
            self.state / "harness.json",
            self.tmux_log,
        ):
            path.unlink(missing_ok=True)

    # ---------- Umgebung und Aufruf ----------

    def env(self, **extra):
        env = os.environ.copy()
        for key in list(env):
            if (
                key.startswith("VIBE")
                or key.startswith("FAKE_")
                or key.startswith("SANDBOX")
                or key in (
                    "AGENT", "TESTER", "REVIEWER", "MAX_RETRIES",
                    "VERIFY_QUICK", "VERIFY_FULL", "VERIFY_PACKAGE",
                    "TMUX", "TMUX_PANE",
                )
            ):
                env.pop(key, None)
        env.update({
            "VIBE": str(self.root),
            "VIBE_INSTALL": str(self.install),
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_STATE": str(self.state),
            "VIBE_AGENTS_DIR": str(self.agents),
            "VIBE_CONFIG_FILE": str(self.home / ".config" / "vibe" / "config.json"),
            "VIBE_STORAGE_LOCK_DIR": str(self.home / "locks"),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "TMPDIR": str(self.root / "tmp"),
            "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
            "FAKE_TMUX_LOG": str(self.tmux_log),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        env.update(extra)
        return env

    def cli(self, *args, **extra):
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=str(self.root),
            env=self.env(**extra),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=90,
        )

    def output(self, result):
        return (result.stdout or "") + (result.stderr or "")

    # ---------- Seeds ----------

    def seed_sessions(self, entries, limit=5):
        data = {"limit": limit, "sessions": entries}
        (self.runtime / "sessions.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )

    def session(self, session, project="proj", name=None, run_id="",
                agent="vibe-agent", harness="opencode", first=None,
                last=None):
        path = str(self.projects[project])
        return {
            "session": session,
            "project": str(Path(path).resolve()),
            "name": name or project,
            "run_id": run_id,
            "agent": agent,
            "harness": harness,
            "first_seen": int(first if first is not None else (last or 100)),
            "last_seen": int(last if last is not None else 100),
        }

    def add_run(self, run_id, state, project="proj"):
        completed = subprocess.run(
            [
                sys.executable, str(RUNS_PY), "start",
                "--runtime", str(self.runtime),
                "--project", str(Path(self.projects[project]).resolve()),
                "--name", project, "--key", project, "--agent", "test-agent",
                "--session", "vibe-" + project, "--id", run_id,
                "--state", state,
            ],
            env=self.env(),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(
            0, completed.returncode,
            "Vorbedingung Laufregister fehlgeschlagen: "
            + completed.stdout + completed.stderr,
        )

    def select_pi(self):
        (self.state / "harness.json").write_text(
            json.dumps({"harness": "pi"}) + "\n", encoding="utf-8")

    def stored_limit(self):
        path = self.runtime / "sessions.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8")).get("limit")

    def new_session_commands(self):
        if not self.tmux_log.exists():
            return []
        records = [
            json.loads(line)
            for line in self.tmux_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return [
            " ".join(record["args"])
            for record in records
            if record.get("args", [])[:1] == ["new-session"]
        ]

    def continue_exports(self):
        values = []
        for command in self.new_session_commands():
            values.extend(re.findall(r"VIBE_CONTINUE_SESSION=([^\s;\"']+)",
                                     command))
        return values

    def seed_three_states(self):
        """Eine abgebrochene, eine abgeschlossene und eine laufende Session."""
        self.add_run("lauf-ab", "ended")
        self.add_run("lauf-ok", "finished")
        self.add_run("lauf-live", "running")
        self.seed_sessions([
            self.session("ses_ab", run_id="lauf-ab", first=100, last=300),
            self.session("ses_ok", run_id="lauf-ok", first=100, last=200),
            self.session("ses_live", run_id="lauf-live", first=100, last=100),
        ])


class ListTest(SessionsCliFixture):
    """AK1/AK2: Auflistung mit Kennung, Zustandslabel, Agent und Projekt."""

    def test_list_shows_identifier_state_label_agent_and_project(self):
        """Vorbedingung: drei Sessions in den Zuständen abgebrochen,
        abgeschlossen und läuft.
        Aktion: ``vibe sessions list``.
        Erwartung: je Zeile Kennung, deutsches Zustandslabel, Agent und
        Projektname; das Label steht in der Zeile der passenden Session.
        Fehlerfall: Zustand fehlt, englische Labels oder unzuordenbare Zeilen.
        """
        self.seed_three_states()

        result = self.cli("sessions", "list")
        text = self.output(result)

        self.assertEqual(0, result.returncode, text)
        lines = [line for line in text.splitlines() if line.strip()]
        self.assertTrue(lines, "Die Auflistung ist leer: " + text)
        for session, label in (
            ("ses_ab", "abgebrochen"),
            ("ses_ok", "abgeschlossen"),
            ("ses_live", "läuft"),
        ):
            matching = [line for line in lines if session in line]
            self.assertEqual(
                1, len(matching),
                f"Session {session} erscheint nicht genau einmal: {lines}",
            )
            line = matching[0]
            self.assertIn(label, line,
                          f"Zustandslabel {label!r} fehlt für {session}: {line}")
            self.assertIn("vibe-agent", line, line)
            self.assertIn("proj", line, line)

    def test_list_default_shows_the_five_newest_sessions(self):
        """Vorbedingung: sieben Sessions mit aufsteigender Zeit, Standard 5.
        Aktion: ``vibe sessions list`` ohne Optionen.
        Erwartung: die fünf jüngsten (ses_07..ses_03), die zwei ältesten
        fehlen.
        Fehlerfall: mehr/weniger Einträge oder falsche Auswahl.
        """
        self.add_run("lauf-alt", "finished")
        self.seed_sessions([
            self.session("ses_%02d" % index, run_id="lauf-alt",
                         first=index, last=index)
            for index in range(1, 8)
        ])

        text = self.output(self.cli("sessions", "list"))

        for index in range(3, 8):
            self.assertIn("ses_%02d" % index, text,
                          "Junge Session fehlt in der Standardauflistung: " + text)
        for index in (1, 2):
            self.assertNotIn("ses_%02d" % index, text,
                             "Ältere Session erscheint trotz Standard 5: " + text)

    def test_list_limit_option_overrides_the_default(self):
        """Vorbedingung: sieben Sessions.
        Aktion: ``vibe sessions list --limit 2``.
        Erwartung: nur die zwei jüngsten.
        Fehlerfall: Option wirkungslos.
        """
        self.add_run("lauf-alt", "finished")
        self.seed_sessions([
            self.session("ses_%02d" % index, run_id="lauf-alt",
                         first=index, last=index)
            for index in range(1, 8)
        ])

        text = self.output(self.cli("sessions", "list", "--limit", "2"))

        self.assertIn("ses_07", text, text)
        self.assertIn("ses_06", text, text)
        for index in range(1, 6):
            self.assertNotIn("ses_%02d" % index, text,
                             "--limit 2 zeigte zu viele Sessions: " + text)

    def test_list_uses_the_stored_limit(self):
        """Vorbedingung: sieben Sessions, gespeicherter Standard 2.
        Aktion: ``vibe sessions list``.
        Erwartung: zwei Einträge (der gespeicherte Standard gilt).
        Fehlerfall: gespeicherter Standard wird ignoriert.
        """
        self.add_run("lauf-alt", "finished")
        self.seed_sessions([
            self.session("ses_%02d" % index, run_id="lauf-alt",
                         first=index, last=index)
            for index in range(1, 8)
        ], limit=2)

        text = self.output(self.cli("sessions", "list"))

        self.assertIn("ses_07", text, text)
        self.assertIn("ses_06", text, text)
        for index in range(1, 6):
            self.assertNotIn("ses_%02d" % index, text,
                             "Gespeichertes Limit 2 wurde nicht angewandt: " + text)

    def test_list_filters_by_project_name(self):
        """Vorbedingung: Sessions der Projekte proj und zwei.
        Aktion: ``vibe sessions list --project proj``.
        Erwartung: nur Sessions von proj.
        Fehlerfall: fremde Projekte erscheinen.
        """
        self.add_run("lauf-proj", "finished", project="proj")
        self.add_run("lauf-zwei", "finished", project="zwei")
        self.seed_sessions([
            self.session("ses_proj", project="proj", run_id="lauf-proj",
                         first=100, last=200),
            self.session("ses_zwei", project="zwei", run_id="lauf-zwei",
                         first=100, last=100),
        ])

        text = self.output(self.cli("sessions", "list", "--project", "proj"))

        self.assertIn("ses_proj", text, text)
        self.assertNotIn("ses_zwei", text,
                         "Projektfilter ließ fremde Sessions durch: " + text)

    def test_list_searches_the_session_identifier_case_insensitively(self):
        """Vorbedingung: Sessions ``SES_Alpha`` und ``ses_beta``.
        Aktion: ``vibe sessions list alpha`` (klein geschrieben).
        Erwartung: nur ``SES_Alpha``.
        Fehlerfall: Suche ist groß-/kleinschreibungssensitiv oder wirkungslos.
        """
        self.add_run("lauf-a", "finished")
        self.seed_sessions([
            self.session("SES_Alpha", run_id="lauf-a", first=100, last=200),
            self.session("ses_beta", run_id="lauf-a", first=100, last=100),
        ])

        text = self.output(self.cli("sessions", "list", "alpha"))

        self.assertIn("SES_Alpha", text, text)
        self.assertNotIn("ses_beta", text,
                         "Suchtext filterte nicht: " + text)


class ProjectFilterCwdTest(SessionsCliFixture):
    """Review M1: Der Projektfilter darf nicht am Arbeitsverzeichnis hängen.

    ``--project`` ist ein Projektname aus der Projektkarte, kein Pfad. Die
    Auflösung muss unabhängig davon sein, aus welchem Verzeichnis die CLI
    aufgerufen wird; ein unbekannter Name ist ein Fehler, keine leere Liste.
    """

    def seed_one_project_session(self):
        self.add_run("lauf-proj", "finished", project="proj")
        self.seed_sessions([
            self.session("ses_proj", project="proj", run_id="lauf-proj",
                         first=100, last=200),
        ])

    def run_from(self, cwd, *args):
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=str(cwd),
            env=self.env(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=90,
        )

    def test_list_project_filter_works_from_a_foreign_cwd(self):
        """Vorbedingung: Projekt ``proj`` mit erfasster Session; ein leeres
        Fremdverzeichnis, das weder Workspace-Wurzel noch Projekt ist.
        Aktion/Erwartung, zwei Unterfälle:
        (a) ``vibe sessions list --project proj`` aus dem Fremdverzeichnis:
            die Session von proj erscheint (Namensauflösung über die
            Projektkarte, nicht über das CWD).
        (b) ``--project gibtesnicht``: Exit != 0 und eine Meldung, die den
            unbekannten Namen nennt; kein Traceback, keine stille Leerliste.
        Fehlerfall: leere Liste bzw. Exit 0, weil ``--project`` relativ zum
        CWD aufgelöst wird.
        """
        self.seed_one_project_session()
        foreign = self.root / "tmp" / "fremdes-cwd"
        foreign.mkdir(parents=True, exist_ok=True)

        with self.subTest(fall="bekanntes Projekt aus fremdem CWD"):
            result = self.run_from(
                foreign, "sessions", "list", "--project", "proj")
            text = self.output(result)
            self.assertEqual(0, result.returncode, text)
            self.assertIn(
                "ses_proj", text,
                "Der Projektfilter verfehlt das Projekt aus fremdem CWD: "
                + text)

        with self.subTest(fall="unbekanntes Projekt"):
            result = self.run_from(
                foreign, "sessions", "list", "--project", "gibtesnicht")
            text = self.output(result)
            self.assertNotEqual(
                0, result.returncode,
                "Unbekanntes Projekt wurde still als leere Liste behandelt: "
                + text)
            self.assertIn(
                "gibtesnicht", text,
                "Die Fehlermeldung nennt den unbekannten Projektnamen nicht: "
                + text)
            self.assertNotIn(
                "Traceback", text,
                "Unbekanntes Projekt führte zu einem Absturz statt zu einer "
                "Meldung: " + text)


class LimitCommandTest(SessionsCliFixture):
    """AK1: ``vibe sessions limit`` zeigen und setzen."""

    def test_limit_without_value_shows_the_stored_default(self):
        """Vorbedingung: gespeicherter Standard 5.
        Aktion: ``vibe sessions limit``.
        Erwartung: Ausgabe nennt 5; die Datei bleibt unverändert.
        Fehlerfall: kein Wert oder falscher Wert.
        """
        self.seed_sessions([], limit=5)

        result = self.cli("sessions", "limit")
        text = self.output(result)

        self.assertEqual(0, result.returncode, text)
        self.assertRegex(text, r"\b5\b",
                         "Der gespeicherte Standard 5 wird nicht gezeigt: " + text)
        self.assertEqual(5, self.stored_limit())

    def test_limit_with_value_sets_and_persists_it(self):
        """Vorbedingung: gespeicherter Standard 5.
        Aktion: ``vibe sessions limit 7``, danach erneut anzeigen.
        Erwartung: Datei hält 7 und die Anzeige nennt 7.
        Fehlerfall: Wert wird nicht gespeichert.
        """
        self.seed_sessions([], limit=5)

        result = self.cli("sessions", "limit", "7")
        text = self.output(result)

        self.assertEqual(0, result.returncode, text)
        self.assertEqual(7, self.stored_limit(),
                         "Limit 7 wurde nicht gespeichert: " + text)
        self.assertRegex(self.output(self.cli("sessions", "limit")), r"\b7\b")

    def test_limit_rejects_invalid_values_without_writing(self):
        """Vorbedingung: gespeicherter Standard 5.
        Aktion: ``sessions limit`` mit 0, 101, 1000, "viele".
        Erwartung: Exit != 0, verständliche Meldung, Datei bleibt bei 5.
        Fehlerfall: ungültiger Wert wird gespeichert oder still gedeckelt.
        """
        self.seed_sessions([], limit=5)

        for value in ("0", "101", "1000", "viele"):
            with self.subTest(value=value):
                result = self.cli("sessions", "limit", value)
                text = self.output(result)

                self.assertNotEqual(
                    0, result.returncode,
                    f"Ungültiges Limit {value!r} wurde angenommen: " + text,
                )
                self.assertTrue(text.strip(),
                                f"Abbruch ohne Meldung für {value!r}")
                self.assertEqual(
                    5, self.stored_limit(),
                    f"Ungültiges Limit {value!r} wurde gespeichert",
                )


class ResumeTest(SessionsCliFixture):
    """AK3: Fortsetzen über die AP14-Mechanik; jede Ablehnung startet nichts."""

    def test_resume_with_unknown_session_refuses_without_start(self):
        """Vorbedingung: Register ohne diese Kennung.
        Aktion: ``sessions resume proj --session ses_fremd``.
        Erwartung: Exit != 0 mit Meldung; kein neuer Lauf.
        Fehlerfall: Start mit fremder/erfundener Session.
        """
        self.add_run("lauf-ok", "finished")
        self.seed_sessions([self.session("ses_bekannt", run_id="lauf-ok")])

        result = self.cli("sessions", "resume", "proj",
                          "--session", "ses_fremd")
        text = self.output(result)

        self.assertNotEqual(0, result.returncode,
                            "Unbekannte Session wurde fortgesetzt: " + text)
        self.assertTrue(text.strip(), "Ablehnung ohne Meldung")
        self.assertEqual([], self.new_session_commands(),
                         "Trotz unbekannter Session wurde ein Lauf gestartet")

    def test_resume_with_a_session_of_another_project_refuses(self):
        """Vorbedingung: Kennung gehört zu Projekt zwei, aufgerufen wird proj.
        Aktion: ``sessions resume proj --session ses_zwei``.
        Erwartung: Exit != 0 mit Meldung; kein Start.
        Fehlerfall: Projektgrenze wird nicht geprüft.
        """
        self.add_run("lauf-zwei", "finished", project="zwei")
        self.seed_sessions([
            self.session("ses_zwei", project="zwei", run_id="lauf-zwei"),
        ])

        result = self.cli("sessions", "resume", "proj",
                          "--session", "ses_zwei")
        text = self.output(result)

        self.assertNotEqual(0, result.returncode,
                            "Fremde Projekt-Session wurde fortgesetzt: " + text)
        self.assertTrue(text.strip(), "Ablehnung ohne Meldung")
        self.assertEqual([], self.new_session_commands(), text)

    def test_resume_with_last_starts_the_newest_session(self):
        """Vorbedingung: zwei Sessions, die jüngere ist abgeschlossen.
        Aktion: ``sessions resume proj --last``.
        Erwartung: der Startbefehl exportiert ``VIBE_CONTINUE_SESSION`` mit
        der jüngeren Kennung (jeder Zustand ist erlaubt).
        Fehlerfall: falsche Session oder kein Start.
        """
        self.add_run("lauf-alt", "ended")
        self.add_run("lauf-neu", "finished")
        self.seed_sessions([
            self.session("ses_alt", run_id="lauf-alt", first=100, last=100),
            self.session("ses_neu", run_id="lauf-neu", first=100, last=200),
        ])

        result = self.cli("sessions", "resume", "proj", "--last")
        text = self.output(result)

        self.assertEqual(0, result.returncode, text)
        self.assertEqual(
            ["ses_neu"], self.continue_exports(),
            "--last setzte nicht die jüngste Session fort: " + text,
        )

    def test_resume_with_aborted_picks_the_newest_aborted_session(self):
        """Vorbedingung: eine neuere abgeschlossene und zwei abgebrochene
        Sessions.
        Aktion: ``sessions resume proj --aborted``.
        Erwartung: die jüngste abgebrochene Session wird fortgesetzt, nicht
        die neuere abgeschlossene.
        Fehlerfall: falsche Session (dann wäre der Abbruch nicht exakt
        wiederhergestellt).
        """
        self.add_run("lauf-fin", "finished")
        self.add_run("lauf-abt", "ended")
        self.seed_sessions([
            self.session("ses_fin", run_id="lauf-fin", first=100, last=300),
            self.session("ses_abt1", run_id="lauf-abt", first=100, last=100),
            self.session("ses_abt2", run_id="lauf-abt", first=100, last=200),
        ])

        result = self.cli("sessions", "resume", "proj", "--aborted")
        text = self.output(result)

        self.assertEqual(0, result.returncode, text)
        self.assertEqual(
            ["ses_abt2"], self.continue_exports(),
            "--aborted wählte nicht die jüngste abgebrochene Session: " + text,
        )

    def test_resume_without_aborted_session_refuses_without_start(self):
        """Vorbedingung: nur abgeschlossene Sessions.
        Aktion: ``sessions resume proj --aborted``.
        Erwartung: Exit != 0 mit Meldung; kein Start.
        Fehlerfall: es wird irgendeine andere Session gestartet.
        """
        self.add_run("lauf-fin", "finished")
        self.seed_sessions([self.session("ses_fin", run_id="lauf-fin")])

        result = self.cli("sessions", "resume", "proj", "--aborted")
        text = self.output(result)

        self.assertNotEqual(0, result.returncode,
                            "Ohne abgebrochene Session wurde gestartet: " + text)
        self.assertTrue(text.strip(), "Ablehnung ohne Meldung")
        self.assertEqual([], self.new_session_commands(), text)

    def test_resume_refuses_while_a_run_is_active(self):
        """Vorbedingung: laufender Lauf des Projekts (Register und Sitzung).
        Aktion: ``sessions resume proj --session ses_ab``.
        Erwartung: Exit != 0 mit Meldung über den aktiven Lauf; kein Start.
        Fehlerfall: ein zweiter Lauf wird gestartet.
        """
        self.add_run("lauf-live", "running")
        self.seed_sessions([self.session("ses_ab", run_id="lauf-live")])

        result = self.cli(
            "sessions", "resume", "proj", "--session", "ses_ab",
            FAKE_TMUX_LIVE="vibe-proj",
        )
        text = self.output(result)

        self.assertNotEqual(0, result.returncode,
                            "Bei aktivem Lauf wurde fortgesetzt: " + text)
        self.assertIn("Lauf", text,
                      "Meldung nennt den aktiven Lauf nicht: " + text)
        self.assertEqual([], self.new_session_commands(),
                         "Bei aktivem Lauf wurde ein zweiter Lauf gestartet")

    def test_resume_refuses_for_pi_with_a_clear_message(self):
        """Vorbedingung: Harness Pi (harness.json im Zustandsordner).
        Aktion: ``sessions resume proj --session ses_ab``.
        Erwartung: Exit != 0; Meldung nennt Pi und den Print-Modus
        (--no-session); kein Start.
        Fehlerfall: Pi wird gestartet, obwohl es keine Session fortsetzen kann.
        """
        self.add_run("lauf-abt", "ended")
        self.seed_sessions([self.session("ses_ab", run_id="lauf-abt",
                                         harness="pi")])
        self.select_pi()

        result = self.cli("sessions", "resume", "proj", "--session", "ses_ab")
        text = self.output(result)

        self.assertNotEqual(0, result.returncode,
                            "Pi wurde trotz fehlender Fähigkeit gestartet: " + text)
        self.assertIn("Pi", text, "Meldung nennt Pi nicht: " + text)
        self.assertIn("--no-session", text,
                      "Meldung nennt den Print-Modus nicht: " + text)
        self.assertEqual([], self.new_session_commands(), text)

    def test_resume_with_session_starts_exactly_that_session(self):
        """Vorbedingung: zwei Sessions, eine davon abgebrochen.
        Aktion: ``sessions resume proj --session ses_ab``.
        Erwartung: Exit 0; der tmux-Startbefehl exportiert
        ``VIBE_CONTINUE_SESSION=ses_ab`` (AP14-Mechanik unverändert).
        Fehlerfall: falsche Kennung oder kein Start.
        """
        self.add_run("lauf-abt", "ended")
        self.add_run("lauf-fin", "finished")
        self.seed_sessions([
            self.session("ses_ab", run_id="lauf-abt", first=100, last=200),
            self.session("ses_fin", run_id="lauf-fin", first=100, last=100),
        ])

        result = self.cli("sessions", "resume", "proj", "--session", "ses_ab")
        text = self.output(result)

        self.assertEqual(0, result.returncode, text)
        self.assertEqual(
            ["ses_ab"], self.continue_exports(),
            "Der Startbefehl exportiert nicht die gewählte Session: " + text,
        )

    def test_resume_refuses_for_an_unknown_project(self):
        """Vorbedingung: Projekt ``gibtesnicht`` existiert nicht.
        Aktion: ``sessions resume gibtesnicht --last``.
        Erwartung: Exit != 0 mit Meldung; kein Start.
        Fehlerfall: Ausnahme oder Start ohne Projekt.
        """
        result = self.cli("sessions", "resume", "gibtesnicht", "--last")
        text = self.output(result)

        self.assertNotEqual(0, result.returncode,
                            "Unbekanntes Projekt wurde akzeptiert: " + text)
        self.assertTrue(text.strip(), "Ablehnung ohne Meldung")
        self.assertEqual([], self.new_session_commands(), text)


if __name__ == "__main__":
    unittest.main()
