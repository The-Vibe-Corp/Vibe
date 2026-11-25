"""Unabhängige Abnahme V-026: Läufe gegen fremde tmux-Aufräumaktionen sichern.

Die Fälle sind aus dem Arbeitspaket und ``SPEC.md`` („Agentenläufe und
Prüfungen“) abgeleitet, nicht aus einem Implementierungsdiff. Jeder
Agentenlauf lebt auf einem eigenen tmux-Server; der Socket-Name entspricht dem
Sitzungsnamen ``vibe-<laufschlüssel>`` (Profil dev hängt ``-dev`` an).
Dashboard und opencode-Server bleiben auf dem Standard-Server.

Testfälle
---------
``RunSessionSocketTest.test_run_start_uses_a_dedicated_socket_named_like_the_session``
    Vorbedingung: Projekt ``proj``, Agent gesetzt, alle externen Grenzen als
    Attrappen. Aktion: ``cmd_run``. Erwartung: ``tmux -L vibe-proj new-session
    -d -s vibe-proj ...`` – Socket und Sitzung sind identisch.
``RunSessionSocketTest.test_dev_profile_appends_dev_to_session_and_socket``
    Vorbedingung: Profil ``dev``. Aktion: ``cmd_run``. Erwartung: Sitzung und
    Socket heißen ``vibe-proj-dev``.
``RunSessionSocketTest.test_status_checks_the_run_session_on_its_own_socket``
    Vorbedingung: kein Registereintrag, tmux meldet die Sitzung. Aktion:
    ``run_state``. Erwartung: ``tmux -L vibe-proj has-session -t vibe-proj``.
``RunSessionSocketTest.test_attach_uses_the_same_socket``
    Vorbedingung: Sitzung läuft. Aktion: ``cmd_attach``. Erwartung:
    ``tmux -L vibe-proj attach -t vibe-proj``.
``RunSessionSocketTest.test_stop_kills_the_session_on_its_own_socket``
    Vorbedingung: laufender Registereintrag mit Sitzung ``vibe-proj``.
    Aktion: ``cmd_stop``. Erwartung: ``tmux -L vibe-proj kill-session -t
    vibe-proj``; nur dieser Lauf wird beendet.
``RunStopIsolationRealTmuxTest.test_stopping_one_run_leaves_the_other_run_and_dashboard_alive``
    Vorbedingung: Dashboard auf dem Standard-Server, zwei Läufe auf eigenen
    Servern. Aktion: echter ``vibe stop`` des ersten Laufs. Erwartung: nur
    dessen Sitzung endet; zweiter Lauf und Dashboard leben weiter.
``RunsSocketTest.test_runs_list_checks_each_record_on_its_session_socket``
    Vorbedingung: laufender Eintrag ``vibe-proj``. Aktion: ``vibe runs list``.
    Erwartung: Abfrage über ``-L vibe-proj``.
``RunsSocketTest.test_runs_prune_marks_orphans_using_the_session_socket``
    Vorbedingung: verwaister Eintrag ``vibe-weg``. Aktion: ``vibe runs prune``.
    Erwartung: Abfrage über ``-L vibe-weg``; Eintrag wird ``ended``.
``SetupLockTest.test_setup_lock_uses_the_run_socket_and_keeps_dashboard_on_default``
    Vorbedingung: laufender Eintrag ``vibe-proj``; Setup-Sperre prüft. Aktion:
    ``running_installation``. Erwartung: Lauf über ``-L vibe-proj``,
    Dashboard-/Server-Sitzungen ohne ``-L``.
``DefaultSocketTest.test_dashboard_start_stays_on_the_default_server`` und
``..._opencode_server_start_stays_on_the_default_server``
    Vorbedingung: keine laufende Sitzung. Aktion: ``cmd_ui start`` bzw.
    ``cmd_server start``. Erwartung: ``new-session`` ohne ``-L``.
``RunnerSignalTest.test_hup/term/int_writes_log_line_and_ends_record``
    Vorbedingung: Läufer arbeitet an einem Paket (opencode-Attrappe schläft).
    Aktion: Signal an die Prozessgruppe. Erwartung: Protokollzeile mit dem
    Signalnamen und Registereintrag ``ended`` mit Notiz
    ``extern beendet (Signal <SIG>)``.
``RunnerSignalTest.test_already_finished_run_stays_unchanged``
    Vorbedingung: Registereintrag wurde extern auf ``finished`` gesetzt.
    Aktion: ``TERM`` an den Läufer. Erwartung: Eintrag bleibt ``finished``
    (kein ``ended``/keine Signalnotiz).
``OrphanCleanupTest.test_new_run_marks_only_orphans_of_its_own_project_ended``
    Vorbedingung: Register mit verwaistem eigenen Eintrag, laufendem eigenen
    Eintrag, fremdem Projekt und nicht prüfbarer Sitzung. Aktion: neuer Lauf.
    Erwartung: nur der verwaiste eigene Eintrag wird ``ended`` mit Notiz
    ``extern beendet (Sitzung fehlt)``; die übrigen bleiben unverändert.
``RegistryNoteTest.test_finish_without_note_omits_the_field`` /
``..._with_note_stores_it``
    Vorbedingung: laufender Registereintrag. Aktion: ``vibe_runs.py finish``
    ohne/mit ``--note``. Erwartung: Feld fehlt bzw. enthält den Text.

Es werden keine Modelle oder Netzverbindungen verwendet. Die meisten
tmux-Aufrufe sind Attrappen; die Signalprüfungen laufen gegen einen echten
bash-Läufer mit einer schlafenden opencode-Attrappe. Die Stopp-Isolation
verwendet eigene, in ``TMUX_TMPDIR`` eingeschlossene tmux-Server.
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"
RUNNER = BIN / "vibe-run.sh"
RUNS = BIN / "vibe_runs.py"
SETUP = REPO / "scripts" / "setup-vibe.py"

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(BIN))
import runner_support as support

DASHBOARD_SESSIONS = ("vibe-ui", "vibe-ui-dev", "vibe-server", "vibe-server-dev")


def load_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def isolated_env(root, home, state, install, runtime, profile="prod"):
    """Umgebung ohne persönliche VIBE-, Sandbox- oder Prüfwerte."""
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
            "VIBE": str(root),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "VIBE_CONFIG_FILE": str(root / "config.json"),
            "VIBE_STORAGE_LOCK_DIR": str(root / "locks"),
            "VIBE_INSTALL": str(install),
            "VIBE_RUNTIME": str(runtime),
            "VIBE_STATE": str(state),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    if profile != "prod":
        env["VIBE_PROFILE"] = profile
    return env


class CliModuleFixture(unittest.TestCase):
    """Lädt ``bin/vibe`` isoliert; alle Pfade liegen in temporären Ordnern."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.install = self.root / "_toolchain"
        self.runtime = self.root / "_logs"
        self.state = self.root / "_state"
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        self.saved_environ = {
            key: os.environ.get(key)
            for key in list(os.environ)
            if key.startswith("VIBE") or key in (
                "VIBE",
                "HOME",
                "XDG_CONFIG_HOME",
                "PYTHONDONTWRITEBYTECODE",
            )
        }
        self.cli = self.load_cli()

    def tearDown(self):
        for key in list(os.environ):
            if key.startswith("VIBE"):
                os.environ.pop(key, None)
        for key in ("HOME", "XDG_CONFIG_HOME", "PYTHONDONTWRITEBYTECODE"):
            os.environ.pop(key, None)
        for key, value in self.saved_environ.items():
            if value is not None:
                os.environ[key] = value
        self.tmp.cleanup()

    def load_cli(self, profile="prod", name="vibe_v026_under_test"):
        env = isolated_env(
            self.root, self.home, self.state, self.install, self.runtime, profile
        )
        old = dict(os.environ)
        try:
            os.environ.clear()
            os.environ.update(env)
            return load_module(CLI, name)
        finally:
            os.environ.clear()
            os.environ.update(old)

    def cli_env(self, **extra):
        env = isolated_env(
            self.root, self.home, self.state, self.install, self.runtime
        )
        env.update({key: str(value) for key, value in extra.items()})
        return env

    def run_cli(self, *args, **extra):
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=str(self.root),
            env=self.cli_env(**extra),
            capture_output=True,
            text=True,
            timeout=60,
        )


class RunSessionSocketTest(CliModuleFixture):
    """Start, Status, Anhängen und Stoppen nutzen denselben Laufsocket."""

    def invoke_cmd_run(self, module=None):
        module = module or self.cli
        calls = []

        class Registry:
            def start(self, **kwargs):
                calls.append(["register", kwargs])
                return {"id": "proj-lauf"}

            def finish(self, *args, **kwargs):
                return None

        def fake_run(argv, **kwargs):
            calls.append(list(argv))
            return 0, ""

        values = {
            "run": fake_run,
            "tmux_has": lambda name: False,
            "tmux_has_session": lambda name: False,
            "project_map": lambda: {"proj": str(self.project)},
            "ppath": lambda name: str(self.project),
            "is_init": lambda name: True,
            "pending_changes": lambda path: "",
            "changed_file": lambda path, name: False,
            "sandbox_status": lambda name: {"enabled": False},
            "pause_after_active": lambda name: False,
            "penv": lambda name: {},
            "vibe_agent_status": lambda: {
                "name": "",
                "model": "",
                "configured": False,
            },
            "require_agent": lambda agent: agent,
            "ensure_opencode_password": lambda: str(
                self.runtime / "opencode.password"
            ),
            "run_agent_selection": lambda name, agent: "",
            "run_registry": lambda: Registry(),
        }
        with mock.patch.multiple(module, **values), mock.patch.object(
            module.vibe_runs, "rotate_log", lambda *args, **kwargs: None
        ):
            module.cmd_run("proj", "tester", out=io.StringIO())
        return calls

    def new_session_call(self, calls):
        sessions = [call for call in calls if "new-session" in call]
        self.assertEqual(len(sessions), 1, calls)
        return sessions[0]

    def test_run_start_uses_a_dedicated_socket_named_like_the_session(self):
        calls = self.invoke_cmd_run()

        argv = self.new_session_call(calls)
        self.assertEqual(argv[0], "tmux", argv)
        self.assertEqual(argv[1:3], ["-L", "vibe-proj"], argv)
        self.assertIn("new-session", argv, argv)
        self.assertEqual(argv[argv.index("-s") + 1], "vibe-proj", argv)

    def test_dev_profile_appends_dev_to_session_and_socket(self):
        module = self.load_cli("dev", "vibe_v026_dev_under_test")
        self.assertEqual(module.PATHS.profile, "dev")
        self.assertEqual(module.sess("proj"), "vibe-proj-dev")

        argv = self.new_session_call(self.invoke_cmd_run(module))
        self.assertEqual(argv[1:3], ["-L", "vibe-proj-dev"], argv)
        self.assertEqual(argv[argv.index("-s") + 1], "vibe-proj-dev", argv)

    def test_status_checks_the_run_session_on_its_own_socket(self):
        calls = []

        class Registry:
            def latest(self, project=None):
                return None

        def fake_run(argv, **kwargs):
            calls.append(list(argv))
            return 0, ""

        with mock.patch.multiple(
            self.cli, run=fake_run, run_registry=lambda: Registry()
        ):
            state = self.cli.run_state("proj")

        self.assertTrue(state["running"], state)
        self.assertIn(
            ["tmux", "-L", "vibe-proj", "has-session", "-t", "vibe-proj"],
            calls,
            calls,
        )

    def test_attach_uses_the_same_socket(self):
        calls = []

        def fake_subprocess(argv, *args, **kwargs):
            calls.append(list(argv))
            return subprocess.CompletedProcess(argv, 0, "", "")

        with mock.patch.object(self.cli, "tmux_has", lambda name: True):
            with mock.patch.object(
                self.cli.subprocess, "run", side_effect=fake_subprocess
            ):
                self.cli.cmd_attach("proj")

        self.assertEqual(
            calls,
            [["tmux", "-L", "vibe-proj", "attach", "-t", "vibe-proj"]],
        )

    def test_stop_kills_the_session_on_its_own_socket(self):
        registry = self.cli.run_registry()
        record = registry.start(
            project=str(self.project),
            name="proj",
            key="proj",
            agent="tester",
            session="vibe-proj",
            log=self.cli.logpath("proj"),
            verify_log=self.cli.logpath("proj", "verify"),
        )
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(list(argv))
            if "show-environment" in argv:
                return 0, "VIBE_MANAGED=run\n"
            if "kill-session" in argv:
                return 0, ""
            return 0, ""

        with mock.patch.multiple(
            self.cli,
            run=fake_run,
            project_map=lambda: {"proj": str(self.project)},
            tmux_has_session=lambda name: True,
        ):
            self.cli.cmd_stop("proj", record["id"])

        killed = [call for call in calls if "kill-session" in call]
        self.assertEqual(len(killed), 1, calls)
        self.assertEqual(
            killed[0],
            ["tmux", "-L", "vibe-proj", "kill-session", "-t", "vibe-proj"],
        )
        self.assertEqual(
            self.cli.run_registry().get(record["id"])["state"], "stopped"
        )


class RunStopIsolationRealTmuxTest(CliModuleFixture):
    """Ein echter ``vibe stop`` beendet nur den eigenen Lauf.

    Dashboard und ein zweiter Lauf liegen auf getrennten tmux-Servern; der
    Stopp des ersten Laufs darf weder den zweiten Lauf noch das Dashboard
    beenden.
    """

    def setUp(self):
        super().setUp()
        self.tmux_dir = self.root / "tmux"
        self.tmux_dir.mkdir()
        self.tmux_dir.chmod(0o700)
        self.tmux_env = {
            "PATH": os.environ.get("PATH", ""),
            "TMUX_TMPDIR": str(self.tmux_dir),
            "TERM": os.environ.get("TERM", "xterm"),
        }
        self.servers = []
        self.default_server = False

    def tearDown(self):
        for socket in self.servers:
            self.tmux("-L", socket, "kill-server")
        if self.default_server:
            self.tmux("kill-server")
        super().tearDown()

    def tmux(self, *args):
        return subprocess.run(
            ["tmux", *args],
            env=self.tmux_env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def start_session(self, socket, session, marker):
        self.servers.append(socket)
        result = self.tmux(
            "-L", socket, "new-session", "-d", "-s", session, "sleep 60"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.tmux(
            "-L", socket, "set-environment", "-t", session,
            self.cli.MANAGED_VAR, marker,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def start_default_session(self, session):
        self.default_server = True
        result = self.tmux("new-session", "-d", "-s", session, "sleep 60")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.tmux(
            "set-environment", "-t", session, self.cli.MANAGED_VAR, "ui"
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def alive(self, socket, session):
        args = ["-L", socket] if socket else []
        return (
            self.tmux(*args, "has-session", "-t", session).returncode == 0
        )

    def real_tmux(self, argv, **kwargs):
        result = subprocess.run(
            argv, env=self.tmux_env, capture_output=True, text=True, timeout=30
        )
        return result.returncode, (result.stdout + result.stderr).strip()

    def test_stopping_one_run_leaves_the_other_run_and_dashboard_alive(self):
        project = str(self.project.resolve())
        self.start_default_session("vibe-ui")
        self.start_session("vibe-eins", "vibe-eins", "run")
        self.start_session("vibe-zwei", "vibe-zwei", "run")
        registry = self.cli.run_registry()
        first = registry.start(
            project=project,
            name="proj",
            key="proj",
            agent="tester",
            session="vibe-eins",
            log=self.cli.logpath("proj"),
            verify_log=self.cli.logpath("proj", "verify"),
        )
        second = registry.start(
            project=project,
            name="proj",
            key="proj",
            agent="tester",
            session="vibe-zwei",
            log=self.cli.logpath("proj"),
            verify_log=self.cli.logpath("proj", "verify"),
        )

        with mock.patch.multiple(
            self.cli,
            run=self.real_tmux,
            project_map=lambda: {"proj": project},
        ):
            self.cli.cmd_stop("proj", first["id"])

        self.assertFalse(
            self.alive("vibe-eins", "vibe-eins"),
            "Der gestoppte Lauf lebt noch",
        )
        self.assertTrue(
            self.alive("vibe-zwei", "vibe-zwei"),
            "Der Stopp hat einen fremden Lauf beendet",
        )
        self.assertTrue(
            self.alive(None, "vibe-ui"),
            "Der Stopp hat das Dashboard beendet",
        )
        stored = self.cli.run_registry()
        self.assertEqual(stored.get(first["id"])["state"], "stopped")
        self.assertEqual(stored.get(second["id"])["state"], "running")


class RunsSocketTest(CliModuleFixture):
    """``vibe runs list`` und ``prune`` prüfen den Socket des Eintrags."""

    def setUp(self):
        super().setUp()
        self.fakebin = self.root / "fakebin"
        self.fakebin.mkdir()
        self.sessions_file = self.root / "tmux-sessions.txt"
        self.sessions_file.write_text("", encoding="utf-8")
        self.calls_file = self.root / "tmux-calls.txt"
        self.calls_file.write_text("", encoding="utf-8")
        tmux = self.fakebin / "tmux"
        tmux.write_text(
            "#!/bin/sh\n"
            'printf \'%s\\n\' "$*" >> "$FAKE_TMUX_CALLS"\n'
            'if [ "$1" = "-L" ]; then shift 2; fi\n'
            'if [ "$1" = "has-session" ]; then\n'
            '  if [ -n "$FAKE_TMUX_HAS_SESSION_RC" ]; then\n'
            '    exit "$FAKE_TMUX_HAS_SESSION_RC"\n'
            "  fi\n"
            '  name=""\n'
            '  prev=""\n'
            '  for arg in "$@"; do\n'
            '    if [ "$prev" = "-t" ]; then name="$arg"; fi\n'
            '    prev="$arg"\n'
            "  done\n"
            '  if [ -n "$name" ] && grep -Fxq -- "$name" "$FAKE_TMUX_SESSIONS" 2>/dev/null; then\n'
            "    exit 0\n"
            "  fi\n"
            "  exit 1\n"
            "fi\n"
            'if [ "$1" = "kill-session" ]; then exit 0; fi\n'
            "exit 1\n",
            encoding="utf-8",
        )
        tmux.chmod(0o755)
        self.project = self.root / "proj"
        self.project.mkdir(exist_ok=True)

    def live_sessions(self, *names):
        self.sessions_file.write_text(
            "\n".join(names) + ("\n" if names else ""), encoding="utf-8"
        )

    def record(self, run_id, state="running", session="", project=None):
        return {
            "id": run_id,
            "project": str(project if project is not None else self.project),
            "name": "proj",
            "key": "proj",
            "agent": "tester",
            "session": session,
            "log": "",
            "verify_log": "",
            "state": state,
            "exit_code": None,
        }

    def runs_path(self):
        return self.root / "_logs" / "runs.json"

    def write_runs(self, records):
        self.runs_path().parent.mkdir(parents=True, exist_ok=True)
        self.runs_path().write_text(
            json.dumps({"runs": records}, indent=1), encoding="utf-8"
        )

    def read_runs(self):
        data = json.loads(self.runs_path().read_text(encoding="utf-8"))
        return {record["id"]: record for record in data.get("runs", [])}

    def run_with_tmux(self, *args, **extra):
        env = {
            "PATH": str(self.fakebin) + os.pathsep + os.environ.get("PATH", ""),
            "FAKE_TMUX_SESSIONS": str(self.sessions_file),
            "FAKE_TMUX_CALLS": str(self.calls_file),
        }
        env.update(extra)
        return self.run_cli(*args, **env)

    def tmux_calls(self):
        return [
            line
            for line in self.calls_file.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def test_runs_list_checks_each_record_on_its_session_socket(self):
        self.write_runs(
            [self.record("live-1", "running", "vibe-proj", self.project)]
        )
        self.live_sessions("vibe-proj")

        result = self.run_with_tmux("runs", "list")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "-L vibe-proj has-session -t vibe-proj",
            self.tmux_calls(),
            self.tmux_calls(),
        )

    def test_runs_prune_marks_orphans_using_the_session_socket(self):
        self.write_runs(
            [self.record("orphan-1", "running", "vibe-weg", self.project)]
        )

        result = self.run_with_tmux("runs", "prune")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.read_runs()["orphan-1"]["state"], "ended")
        self.assertIn(
            "-L vibe-weg has-session -t vibe-weg",
            self.tmux_calls(),
            self.tmux_calls(),
        )


class SetupLockTest(unittest.TestCase):
    """Die Setup-Sperre prüft Laufsitzungen auf deren eigenem Socket."""

    @classmethod
    def setUpClass(cls):
        cls.setup = load_module(SETUP, "setup_vibe_v026_under_test")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "_logs"
        self.runtime.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_setup_lock_uses_the_run_socket_and_keeps_dashboard_on_default(self):
        (self.runtime / "runs.json").write_text(
            json.dumps(
                {
                    "runs": [
                        {
                            "id": "lauf-1",
                            "state": "running",
                            "session": "vibe-proj",
                            "project": str(self.root / "proj"),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        calls = []

        def runner(command, **kwargs):
            calls.append(list(command))
            name = command[-1]
            code = 0 if name == "vibe-proj" else 1
            return subprocess.CompletedProcess(command, code, "", "")

        # Seit 67d53bc erwartet running_installation das Logverzeichnis, aus
        # dem runs.json gelesen wird (nicht mehr den Workspace).
        reasons = self.setup.running_installation(
            self.runtime, runner=runner, which=lambda name: "/fake/tmux"
        )

        self.assertTrue(
            any("lauf-1" in reason for reason in reasons), reasons
        )
        run_call = next(call for call in calls if "vibe-proj" in call)
        self.assertEqual(
            run_call[1:],
            ["-L", "vibe-proj", "has-session", "-t", "vibe-proj"],
            run_call,
        )
        for session in ("vibe-ui", "vibe-server"):
            call = next(call for call in calls if session in call)
            self.assertNotIn("-L", call, call)


class DefaultSocketTest(CliModuleFixture):
    """Dashboard und opencode-Server bleiben auf dem Standard-Server."""

    def test_dashboard_start_stays_on_the_default_server(self):
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(list(argv))
            return 0, ""

        (self.runtime).mkdir(parents=True, exist_ok=True)
        (self.runtime / "web.token").write_text("token\n", encoding="utf-8")
        with mock.patch.multiple(
            self.cli,
            run=fake_run,
            # AP13: Produktion ruft dashboard_health(bind, port).
            dashboard_health=lambda *args, **kwargs: None,
            port_in_use=lambda host, port: False,
            tmux_session_exists=lambda session: False,
            session_owned=lambda session, kind: True,
        ), mock.patch.object(self.cli.time, "sleep", lambda seconds: None), \
                mock.patch.object(self.cli.vibe_paths, "ensure", lambda *a, **k: None):
            self.cli.cmd_ui("start")

        sessions = [call for call in calls if "new-session" in call]
        self.assertEqual(len(sessions), 1, calls)
        self.assertNotIn("-L", sessions[0], sessions[0])

    def test_opencode_server_start_stays_on_the_default_server(self):
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(list(argv))
            return 0, ""

        with mock.patch.multiple(
            self.cli,
            run=fake_run,
            server_health=lambda: None,
            port_in_use=lambda host, port: False,
            tmux_session_exists=lambda session: False,
            session_owned=lambda session, kind: True,
            ensure_opencode_password=lambda: str(
                self.runtime / "opencode.password"
            ),
        ), mock.patch.object(self.cli.time, "sleep", lambda seconds: None), \
                mock.patch.object(
                    self.cli.vibe_opencode, "probe",
                    lambda: mock.Mock(checked=True, message="", version="2"),
                ), mock.patch.object(
                    self.cli.vibe_opencode, "server_command",
                    lambda port, info=None: ["opencode", "serve"],
                ):
            self.cli.cmd_server("start")

        sessions = [call for call in calls if "new-session" in call]
        self.assertEqual(len(sessions), 1, calls)
        self.assertNotIn("-L", sessions[0], sessions[0])


class RunnerCase(unittest.TestCase):
    """Basis für echte Läuferprozesse mit Attrappen für opencode und tmux."""

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
        self.calls = self.root / "opencode.calls"
        self.counter = self.root / "counter"

    def tearDown(self):
        process = getattr(self, "process", None)
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
            process.wait(timeout=10)
        self.tmp.cleanup()

    def write_project(self, max_retries=0):
        support.write_project(
            self.project,
            "TYPE=generic\n"
            "AGENT=tester\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL="true"\n'
            f"MAX_RETRIES={max_retries}\n",
            feedback=[support.ticket_record(
                "F1", "Erstes Paket", type="feedback", description="Test")],
        )
        support.commit_all(self.project, "Ausgangsstand")

    def runner_env(self, fake_mode="complete", extra=None):
        env = isolated_env(
            self.root, self.home, self.state, self.install, self.runtime
        )
        fakebin = support.install_fake_tools(self.root)
        env.update(
            {
                "VIBE_AGENTS_DIR": str(self.agents),
                "VIBE_MAX_PACKAGES": "1",
                "VIBE_RETRY_DELAY": "0",
                "FAKE_CALLS": str(self.calls),
                "FAKE_COUNTER": str(self.counter),
                "FAKE_MODE": fake_mode,
                "FAKE_ARGS_PATH": str(self.root / "opencode.args"),
                "PATH": str(fakebin) + os.pathsep + os.environ.get("PATH", ""),
            }
        )
        if extra:
            env.update({key: str(value) for key, value in extra.items()})
        return env

    def registry(self):
        return load_module(RUNS, "vibe_runs_v026_runner")


class RunnerSignalTest(RunnerCase):
    """HUP, TERM und INT beenden Register und Protokoll nachvollziehbar."""

    def wait_for_running_record(self, timeout=10):
        registry = self.registry().RunRegistry(str(self.runtime))
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.calls.exists() and self.calls.read_text(encoding="utf-8"):
                record = registry.latest(project=str(self.project.resolve()))
                if record and record.get("state") in ("starting", "running"):
                    return record
            time.sleep(0.05)
        self.fail("Der Läufer hat kein Arbeitspaket begonnen")

    def start_hanging_runner(self):
        self.write_project()
        env = self.runner_env("hang")
        self.process = subprocess.Popen(
            ["bash", str(RUNNER), str(self.project)],
            cwd=str(self.project),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        return self.wait_for_running_record()

    def log_text(self):
        path = self.runtime / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def assert_signal_logged(self, name, log, output):
        """Das Protokoll nennt das Signal in einer Abschlusszeile."""
        lines = [line for line in log.splitlines() if name in line]
        self.assertTrue(lines, output)
        self.assertTrue(
            any(
                token in line.lower()
                for line in lines
                for token in ("signal", "extern", "abbruch", "beendet", "empfangen")
            ),
            lines,
        )

    def assert_signal_case(self, signum, name):
        record = self.start_hanging_runner()
        try:
            os.killpg(self.process.pid, signum)
        except ProcessLookupError:
            pass
        output = None
        try:
            output = self.process.communicate(timeout=15)[0]
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except OSError:
                pass
            output = self.process.communicate()[0]
            self.fail("Der Läufer hat das Signal nicht beendet: " + (output or ""))

        log = self.log_text()
        self.assert_signal_logged(name, log, output)
        ended = self.registry().RunRegistry(str(self.runtime)).get(record["id"])
        self.assertIsNotNone(ended, record)
        self.assertEqual(ended["state"], "ended", ended)
        self.assertEqual(ended.get("note"), f"extern beendet (Signal {name})", ended)

    def test_hup_writes_log_line_and_ends_record(self):
        self.assert_signal_case(signal.SIGHUP, "HUP")

    def test_term_writes_log_line_and_ends_record(self):
        self.assert_signal_case(signal.SIGTERM, "TERM")

    def test_int_writes_log_line_and_ends_record(self):
        self.assert_signal_case(signal.SIGINT, "INT")

    def test_already_finished_run_stays_unchanged(self):
        record = self.start_hanging_runner()
        registry = self.registry().RunRegistry(str(self.runtime))
        registry.finish(record["id"], exit_code=0, state="finished")

        os.killpg(self.process.pid, signal.SIGTERM)
        try:
            output = self.process.communicate(timeout=15)[0]
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except OSError:
                pass
            output = self.process.communicate()[0]
            self.fail("Der Läufer hat das Signal nicht beendet: " + (output or ""))

        unchanged = registry.get(record["id"])
        self.assertEqual(unchanged["state"], "finished", unchanged)
        self.assertNotEqual(unchanged.get("note"), "extern beendet (Signal TERM)")


class OrphanCleanupTest(RunnerCase):
    """Ein neuer Lauf räumt nur verwaiste eigene Einträge auf."""

    def fake_tmux(self):
        fakebin = self.root / "fakebin"
        fakebin.mkdir(exist_ok=True)
        calls = self.root / "tmux.calls"
        calls.write_text("", encoding="utf-8")
        script = fakebin / "tmux"
        script.write_text(
            "#!/bin/sh\n"
            'printf \'%s\\n\' "$*" >> "$FAKE_TMUX_CALLS"\n'
            'if [ "$1" = "-L" ]; then shift 2; fi\n'
            'if [ "$1" = "has-session" ]; then\n'
            '  name=""\n'
            '  prev=""\n'
            '  for arg in "$@"; do\n'
            '    if [ "$prev" = "-t" ]; then name="$arg"; fi\n'
            '    prev="$arg"\n'
            "  done\n"
            '  if [ "$name" = "$FAKE_TMUX_UNVERIFIABLE" ]; then exit 2; fi\n'
            '  if grep -Fxq -- "$name" "$FAKE_TMUX_LIVE" 2>/dev/null; then exit 0; fi\n'
            "  exit 1\n"
            "fi\n"
            "exit 1\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return fakebin, calls

    def test_new_run_marks_only_orphans_of_its_own_project_ended(self):
        self.write_project()
        self.runtime.mkdir(exist_ok=True)
        project = str(self.project.resolve())
        foreign = str((self.root / "fremd").resolve())
        records = [
            {
                "id": "orphan-eigen",
                "project": project,
                "name": "proj",
                "key": "proj",
                "agent": "tester",
                "session": "vibe-weg",
                "log": "",
                "verify_log": "",
                "state": "running",
                "exit_code": None,
            },
            {
                "id": "lebt-eigen",
                "project": project,
                "name": "proj",
                "key": "proj",
                "agent": "tester",
                "session": "vibe-lebt",
                "log": "",
                "verify_log": "",
                "state": "running",
                "exit_code": None,
            },
            {
                "id": "orphan-fremd",
                "project": foreign,
                "name": "fremd",
                "key": "fremd",
                "agent": "tester",
                "session": "vibe-weg-fremd",
                "log": "",
                "verify_log": "",
                "state": "running",
                "exit_code": None,
            },
            {
                "id": "unklar-eigen",
                "project": project,
                "name": "proj",
                "key": "proj",
                "agent": "tester",
                "session": "vibe-unklar",
                "log": "",
                "verify_log": "",
                "state": "running",
                "exit_code": None,
            },
        ]
        before = {record["id"]: dict(record) for record in records}
        (self.runtime / "runs.json").write_text(
            json.dumps({"runs": records}, indent=1), encoding="utf-8"
        )
        fakebin, tmux_calls = self.fake_tmux()
        live = self.root / "tmux.live"
        live.write_text("vibe-lebt\n", encoding="utf-8")

        env = self.runner_env(
            "complete",
            {
                "PATH": str(fakebin)
                + os.pathsep
                + self.runner_env("complete")["PATH"],
                "FAKE_TMUX_CALLS": str(tmux_calls),
                "FAKE_TMUX_LIVE": str(live),
                "FAKE_TMUX_UNVERIFIABLE": "vibe-unklar",
            },
        )
        result = subprocess.run(
            ["bash", str(RUNNER), str(self.project)],
            cwd=str(self.project),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=90,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        registry = self.registry().RunRegistry(str(self.runtime))
        runs = {record["id"]: record for record in registry.all()}
        self.assertEqual(runs["orphan-eigen"]["state"], "ended", runs["orphan-eigen"])
        self.assertEqual(
            runs["orphan-eigen"].get("note"), "extern beendet (Sitzung fehlt)"
        )
        for unchanged in ("lebt-eigen", "orphan-fremd", "unklar-eigen"):
            self.assertEqual(
                runs[unchanged], before[unchanged], f"{unchanged} wurde verändert"
            )
        own_new = [
            record
            for run_id, record in runs.items()
            if run_id not in before and record.get("project") == project
        ]
        self.assertTrue(own_new, "Der neue Lauf fehlt im Register")
        self.assertIn(
            "-L vibe-weg has-session -t vibe-weg",
            tmux_calls.read_text(encoding="utf-8").splitlines(),
            tmux_calls.read_text(encoding="utf-8"),
        )


class RegistryNoteTest(unittest.TestCase):
    """``finish`` nimmt ein optionales ``--note`` auf."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = Path(self.tmp.name) / "_logs"
        self.runs = load_module(RUNS, "vibe_runs_v026_note")
        self.registry = self.runs.RunRegistry(str(self.runtime))

    def tearDown(self):
        self.tmp.cleanup()

    def start(self):
        return self.registry.start(
            project="/work/proj",
            name="proj",
            key="proj",
            agent="tester",
            session="vibe-proj",
            log=str(self.runtime / "proj.log"),
            verify_log=str(self.runtime / "proj.verify.log"),
        )

    def finish(self, run_id, *extra):
        return subprocess.run(
            [
                sys.executable,
                str(RUNS),
                "finish",
                "--runtime",
                str(self.runtime),
                "--id",
                run_id,
                "--state",
                "ended",
                *extra,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_finish_without_note_omits_the_field(self):
        record = self.start()

        result = self.finish(record["id"])

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        stored = self.registry.get(record["id"])
        self.assertEqual(stored["state"], "ended")
        self.assertNotIn("note", stored, stored)

    def test_finish_with_note_stores_it(self):
        record = self.start()

        result = self.finish(
            record["id"], "--note", "extern beendet (Signal TERM)"
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        stored = self.registry.get(record["id"])
        self.assertEqual(stored["state"], "ended")
        self.assertEqual(stored.get("note"), "extern beendet (Signal TERM)")


if __name__ == "__main__":
    unittest.main()
