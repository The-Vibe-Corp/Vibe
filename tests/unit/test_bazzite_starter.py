"""Abnahme V-017: Bazzite-Starter, Desktopdatei, Icon, Installer und Uninstaller.

Die Tests belegen die fachlich geforderten Fälle mit echten Prozessen und
Attrappen:

* Läuft vibe nicht, wird der Container (falls nötig) gestartet, das Dashboard
  gestartet, die Bereitschaft abgewartet und danach der Browser geöffnet.
* Läuft vibe, wird ausschließlich der Browser geöffnet.
* Ein fremder Dienst auf dem Port wird erkannt und nicht als vibe behandelt.
* Mehrfachklicks erzeugen genau ein Dashboard.
* Pfade mit Leerzeichen und Sonderzeichen bleiben getrennte Argumente.
* Die Menüaktion zum Beenden betrifft ausschließlich das Dashboard.
* Startfehler werden gemeldet und im bereinigten Log dokumentiert; das Token
  erscheint nicht im Log.
* Ein Tokenwechsel wird bei jedem Start neu gelesen.
* Installation und Uninstall berühren nur die verwalteten Dateien.

Es werden keine Modellaufrufe, Router-Aktionen oder produktiven
Konfigurationen verwendet.
"""
import http.server
import importlib.machinery
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STARTER = REPO / "scripts" / "vibe_starter.py"
DESKTOP = REPO / "scripts" / "vibe-desktop.py"
ICON = REPO / "scripts" / "vibe.svg"
PATHS_MODULE = REPO / "bin" / "vibe_paths.py"
CLI = REPO / "bin" / "vibe"

if str(REPO / "bin") not in sys.path:
    sys.path.insert(0, str(REPO / "bin"))


def load(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for(predicate, timeout=20, interval=0.1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class Response:
    """Minimale Antwort eines HTTP-Clients für die Gesundheitsprüfung."""

    def __init__(self, body, status=200):
        self.body = body if isinstance(body, bytes) else body.encode("utf-8")
        self.status = status

    def read(self, amount=-1):
        return self.body if amount is None or amount < 0 else self.body[:amount]

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def opener_for(payload=None, error=None, status=200):
    def opener(url, timeout=None):
        if error is not None:
            raise error
        return Response(json.dumps(payload), status=status)

    return opener


class Recorder:
    """Zeichnet Programmaufrufe auf und kann den Start simulieren."""

    def __init__(self, result=None, callback=None):
        self.calls = []
        self.result = result
        self.callback = callback

    def __call__(self, argv, timeout=None, env=None):
        self.calls.append((list(argv), dict(env or {})))
        if self.callback is not None:
            self.result = self.callback(list(argv))
        if self.result is not None:
            return self.result
        return subprocess.CompletedProcess(list(argv), 0, "", "")

    def commands(self):
        return [call[0] for call in self.calls]


class StarterFixture(unittest.TestCase):
    """Isolierte Pfade mit Leerzeichen und Sonderzeichen im Verzeichnisnamen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        # Bewusst Leerzeichen, Umlaut, Dollar, Apostroph und Klammern im Pfad.
        self.workspace = self.root / "Vibe Code – Prüfung ($x) 'V-017'"
        self.workspace.mkdir()
        self.runtime = self.workspace / "_logs"
        self.install = self.workspace / "_toolchain"
        self.install.mkdir()
        (self.install / "templates").mkdir()
        self.port = free_port()
        self.env = {
            "HOME": str(self.home),
            "VIBE": str(self.workspace),
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_INSTALL": str(self.install),
            "VIBE_STATE": str(self.install),
            "VIBE_UI_PORT": str(self.port),
            "VIBE_OPENCODE_PORT": str(free_port()),
            "VIBE_UI_BIND": "127.0.0.1",
            "VIBE_CONTAINER": "android-dev",
            "VIBE_CONFIG_FILE": str(self.home / ".config" / "vibe" / "config.json"),
            "VIBE_AGENTS_DIR": str(self.home / ".config" / "opencode" / "agents"),
            "PATH": os.environ.get("PATH", ""),
        }
        self.paths_mod = load(PATHS_MODULE, "vibe_paths_v017")
        self.paths = self.paths_mod.resolve(environ=self.env, source=str(REPO))
        self.starter = load(STARTER, "vibe_starter_v017")

    def tearDown(self):
        self.tmp.cleanup()

    def write_token(self, token):
        self.runtime.mkdir(parents=True, exist_ok=True)
        (self.runtime / "web.token").write_text(token + "\n", encoding="utf-8")
        return token

    def write_instance(self, instance):
        self.runtime.mkdir(parents=True, exist_ok=True)
        (self.runtime / "web.instance").write_text(instance + "\n", encoding="utf-8")
        return instance

    def health_payload(self, instance="abc123"):
        return {
            "ok": True,
            "app": "vibe",
            "api": 1,
            "instance": instance,
            "bind": "127.0.0.1",
            "port": self.port,
            "pid": 1234,
        }

    def running(self, token="tok-lauf-1", instance="abc123"):
        self.write_instance(instance)
        self.write_token(token)
        return opener_for(self.health_payload(instance))

    def start(self, opener, runner, **kwargs):
        kwargs.setdefault("inside", True)
        kwargs.setdefault("sleeper", lambda _: None)
        kwargs.setdefault("timeout", 2)
        return self.starter.start(self.paths, self.env, runner=runner, opener=opener, **kwargs)


class ProbeTest(StarterFixture):
    def test_vibe_health_is_recognized_by_app_and_instance(self):
        opener = self.running()
        state, data = self.starter.resolve_state(self.paths, opener=opener)
        self.assertEqual(state, "vibe")
        self.assertEqual(data["instance"], "abc123")

    def test_foreign_service_on_the_port_is_not_vibe(self):
        opener = opener_for({"hello": "world"})
        state, _ = self.starter.resolve_state(self.paths, opener=opener)
        self.assertEqual(state, "foreign")

    def test_vibe_lookalike_with_other_instance_is_foreign(self):
        self.write_instance("erwartet")
        opener = opener_for(self.health_payload("fremd"))
        state, _ = self.starter.resolve_state(self.paths, opener=opener)
        self.assertEqual(state, "foreign")

    def test_missing_instance_file_is_not_trusted(self):
        self.write_token("tok-ohne-instanz")
        opener = opener_for(self.health_payload("irgendeine"))
        state, _ = self.starter.resolve_state(self.paths, opener=opener)
        self.assertEqual(state, "foreign")

    def test_connection_refused_is_absent(self):
        opener = opener_for(error=urllib.error.URLError(ConnectionRefusedError()))
        state, _ = self.starter.resolve_state(self.paths, opener=opener)
        self.assertEqual(state, "absent")

    def test_real_http_server_without_vibe_health_is_foreign(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = b"<html>fremder Dienst</html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            state, _ = self.starter.resolve_state(self.paths)
            self.assertEqual(state, "foreign")
        finally:
            server.shutdown()
            server.server_close()


class StartBehaviourTest(StarterFixture):
    def test_running_dashboard_opens_only_the_browser(self):
        opener = self.running("tok-lauf-1")
        runner = Recorder()
        result = self.start(opener, runner)
        self.assertEqual(result.state, "running")
        commands = runner.commands()
        self.assertEqual(len(commands), 1, commands)
        self.assertEqual(os.path.basename(commands[0][0]), "xdg-open")
        self.assertTrue(commands[0][1].endswith("#t=tok-lauf-1"))
        self.assertFalse(any("ui" in command for command in commands))

    def test_absent_dashboard_starts_container_and_opens_the_browser(self):
        state = {"up": False}

        def opener(url, timeout=None):
            if not state["up"]:
                raise urllib.error.URLError(ConnectionRefusedError())
            return Response(json.dumps(self.health_payload("neuinstanz")))

        def on_call(argv):
            if argv[-2:] == ["ui", "start"]:
                self.write_instance("neuinstanz")
                self.write_token("tok-neu-1")
                state["up"] = True
            return subprocess.CompletedProcess(argv, 0, "", "")

        runner = Recorder(callback=on_call)
        result = self.start(opener, runner, inside=False)
        self.assertEqual(result.state, "started")
        commands = runner.commands()
        self.assertEqual(commands[0][:5], ["distrobox", "enter", "--no-tty", "android-dev", "--"])
        self.assertEqual(commands[0][5], "env")
        self.assertIn("ui", commands[0])
        self.assertIn("start", commands[0])
        self.assertEqual(os.path.basename(commands[-1][0]), "xdg-open")
        self.assertTrue(commands[-1][1].endswith("#t=tok-neu-1"))

    def test_container_environment_makes_no_distrobox_round_trip(self):
        opener = self.running()
        runner = Recorder()
        self.start(opener, runner, inside=True)
        for command in runner.commands():
            self.assertNotIn("distrobox", command)

    def test_foreign_service_blocks_the_start_and_is_reported(self):
        opener = opener_for({"app": "anderer-dienst"})
        runner = Recorder()
        with self.assertRaises(self.starter.StarterError) as caught:
            self.start(opener, runner)
        self.assertIn("fremd", str(caught.exception).lower())
        self.assertEqual(runner.commands(), [])

    def test_stop_only_stops_the_dashboard(self):
        runner = Recorder()
        self.starter.stop(
            self.paths, self.env, runner=runner, inside=True, opener=self.running()
        )
        commands = runner.commands()
        self.assertEqual(commands[-1][-2:], ["ui", "stop"])
        joined = " ".join(" ".join(command) for command in commands)
        self.assertNotIn("server", joined)
        self.assertNotIn("podman", joined)
        self.assertNotIn("distrobox stop", joined)

    def test_stop_when_absent_does_not_enter_container(self):
        runner = Recorder()
        outcome = self.starter.stop(
            self.paths,
            self.env,
            runner=runner,
            inside=True,
            opener=opener_for(error=urllib.error.URLError(ConnectionRefusedError())),
        )
        self.assertEqual(outcome.state, "absent")
        self.assertEqual(runner.commands(), [])

    def test_start_error_is_visible_and_the_log_is_cleaned(self):
        token = "tok-geheim-1"

        def opener(url, timeout=None):
            raise urllib.error.URLError(ConnectionRefusedError())

        def callback(argv):
            self.write_token(token)
            return subprocess.CompletedProcess(
                argv, 2, "", f"Start fehlgeschlagen für #t={token}\n{token}"
            )

        runner = Recorder(callback=callback)
        with self.assertRaises(self.starter.StarterError) as caught:
            self.start(opener, runner)
        message = str(caught.exception)
        self.assertIn("Start", message)
        self.assertNotIn(token, message)
        self.starter.report_error(self.paths, message, self.env, runner=runner)

        log = self.runtime / "desktop-starter.log"
        self.assertTrue(log.is_file())
        content = log.read_text(encoding="utf-8")
        self.assertIn("FEHLER", content)
        self.assertNotIn(token, content)
        # Eine sichtbare Meldung wurde über den Notifier versucht.
        self.assertTrue(any("notify-send" in command[0] for command in runner.commands()))
        self.assertFalse(
            any(os.path.basename(command[0]) == "xdg-open" for command in runner.commands())
        )

    def test_paths_with_spaces_and_special_characters_stay_separate_arguments(self):
        opener = self.running()
        runner = Recorder()
        self.start(opener, runner, inside=True)
        command = runner.commands()[0]
        self.assertEqual(os.path.basename(command[0]), "xdg-open")
        self.assertEqual(len(command), 2)
        self.assertIn(str(self.port), command[1])

        installed_cli = self.install / "bin" / "vibe"
        installed_cli.parent.mkdir(parents=True, exist_ok=True)
        installed_cli.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        installed_cli.chmod(0o755)
        state = {"up": False}

        def start_opener(url, timeout=None):
            if not state["up"]:
                raise urllib.error.URLError(ConnectionRefusedError())
            return Response(json.dumps(self.health_payload("abc123")))

        def on_call(argv):
            if argv[-1] == "start":
                self.write_instance("abc123")
                self.write_token("tok-pfad-1")
                state["up"] = True
            return subprocess.CompletedProcess(argv, 0, "", "")

        runner = Recorder(callback=on_call)
        self.start(start_opener, runner, inside=True)
        start_command = runner.commands()[0]
        self.assertIn(str(installed_cli), start_command)

    def test_browser_override_with_spaces_stays_one_argument(self):
        browser = self.root / "Mein Browser (Test)"
        browser.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        browser.chmod(0o755)
        self.env["VIBE_BROWSER"] = str(browser)
        runner = Recorder()
        self.start(self.running(), runner)
        self.assertEqual(runner.commands()[0][0], str(browser))
        self.assertEqual(len(runner.commands()[0]), 2)

    def test_notifier_path_with_spaces_stays_one_argument(self):
        notifier = self.root / "Mein Melder (Test)"
        notifier.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        notifier.chmod(0o755)
        self.env["VIBE_NOTIFY"] = str(notifier)
        runner = Recorder()
        self.starter.report_error(self.paths, "Testfehler", self.env, runner=runner)
        self.assertEqual(runner.commands()[0][0], str(notifier))

    def test_unexecutable_browser_is_reported_instead_of_crashing(self):
        browser = self.root / "nicht-ausfuehrbar"
        browser.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        browser.chmod(0o644)
        self.env["VIBE_BROWSER"] = str(browser)
        with self.assertRaises(self.starter.StarterError) as caught:
            self.start(self.running(), self.starter.run)
        self.assertIn("Browser", str(caught.exception))
        self.assertIn("nicht ausführbar", str(caught.exception))

    def test_token_change_is_used_on_every_launch(self):
        opener = self.running("tok-erst-1")
        runner = Recorder()
        self.start(opener, runner)
        self.assertTrue(runner.commands()[-1][1].endswith("#t=tok-erst-1"))

        self.write_token("tok-zweit-1")
        runner = Recorder()
        self.start(opener, runner)
        self.assertTrue(runner.commands()[-1][1].endswith("#t=tok-zweit-1"))
        self.assertNotIn("tok-erst-1", runner.commands()[-1][1])

    def test_start_without_token_is_reported_instead_of_opening_a_broken_url(self):
        state = {"up": False}

        def opener(url, timeout=None):
            if not state["up"]:
                raise urllib.error.URLError(ConnectionRefusedError())
            return Response(json.dumps(self.health_payload("abc123")))

        def on_call(argv):
            if argv[-1] == "start":
                self.write_instance("abc123")
                state["up"] = True
            return subprocess.CompletedProcess(argv, 0, "", "")

        runner = Recorder(callback=on_call)
        with self.assertRaises(self.starter.StarterError) as caught:
            self.start(opener, runner)
        self.assertIn("token", str(caught.exception).lower())
        self.assertFalse(
            any(os.path.basename(command[0]) == "xdg-open" for command in runner.commands())
        )

    def test_success_is_logged_without_token(self):
        runner = Recorder()
        self.start(self.running("tok-log-geheim"), runner)
        log = self.runtime / "desktop-starter.log"
        self.assertTrue(log.is_file())
        content = log.read_text(encoding="utf-8")
        self.assertIn("Dashboard läuft bereits", content)
        self.assertNotIn("tok-log-geheim", content)
        self.assertNotIn("#t=", content)


class ConcurrencyTest(StarterFixture):
    def test_double_click_creates_exactly_one_dashboard(self):
        """Zwei gleichzeitige Starter erzeugen eine Dashboard-Sitzung."""
        tmux_dir = self.root / "tmux"
        tmux_dir.mkdir()
        tmux_dir.chmod(0o700)
        browser_log = self.root / "browser.log"
        browser = self.root / "fake-browser"
        browser.write_text(
            "#!/usr/bin/env bash\nprintf '%s\\n' \"$1\" >> " + str(browser_log) + "\n",
            encoding="utf-8",
        )
        browser.chmod(0o755)
        env = dict(self.env)
        env.update(
            {
                "VIBE_NO_CONTAINER": "1",
                "VIBE_BROWSER": str(browser),
                "VIBE_START_TIMEOUT": "30",
                "TMUX_TMPDIR": str(tmux_dir),
                "TERM": env.get("TERM", "xterm"),
                "PATH": str(REPO / "bin") + os.pathsep + env["PATH"],
            }
        )
        for key in ("TMUX", "TMUX_PANE"):
            env.pop(key, None)
        processes = [
            subprocess.Popen(
                [sys.executable, str(STARTER), "start"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(2)
        ]
        try:
            results = [process.communicate(timeout=60) for process in processes]
            for process, (stdout, stderr) in zip(processes, results):
                self.assertEqual(process.returncode, 0, stdout + stderr)
            sessions = subprocess.run(
                ["tmux", "list-sessions", "-F", "#{session_name}"],
                env=env, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(sessions.stdout.split().count("vibe-ui"), 1, sessions.stdout)
            self.assertTrue(wait_for(lambda: browser_log.is_file(), 10))
            self.assertEqual(len(browser_log.read_text(encoding="utf-8").splitlines()), 2)
        finally:
            subprocess.run(
                ["tmux", "kill-session", "-t", "vibe-ui"],
                env=env, capture_output=True, text=True, timeout=30,
            )


class RealDashboardTest(StarterFixture):
    """Echter Dashboard-Start ohne Attrappe, aber mit isolierten Pfaden."""

    def test_real_dashboard_starts_opens_and_stops_with_a_fresh_token(self):
        tmux_dir = self.root / "tmux"
        tmux_dir.mkdir()
        tmux_dir.chmod(0o700)
        browser_log = self.root / "browser-real.log"
        browser = self.root / "fake-browser-real"
        browser.write_text(
            "#!/usr/bin/env bash\nprintf '%s\\n' \"$1\" >> " + str(browser_log) + "\n",
            encoding="utf-8",
        )
        browser.chmod(0o755)
        env = dict(self.env)
        env.update(
            {
                "VIBE_NO_CONTAINER": "1",
                "VIBE_BROWSER": str(browser),
                "TMUX_TMPDIR": str(tmux_dir),
                "TERM": env.get("TERM", "xterm"),
                "PATH": str(REPO / "bin") + os.pathsep + env["PATH"],
            }
        )
        for key in ("TMUX", "TMUX_PANE"):
            env.pop(key, None)
        paths = self.paths_mod.resolve(environ=env, source=str(REPO))
        try:
            result = self.starter.start(
                paths, env, runner=subprocess.run, inside=True,
                timeout=40, sleeper=time.sleep,
            )
            self.assertEqual(result.state, "started")
            self.assertTrue(wait_for(lambda: browser_log.is_file(), 10))
            first_url = browser_log.read_text(encoding="utf-8").strip()
            token_file = self.runtime / "web.token"
            self.assertTrue(token_file.is_file())
            first_token = token_file.read_text(encoding="utf-8").strip()
            self.assertTrue(first_url.endswith("#t=" + first_token))

            second = self.starter.start(
                paths, env, runner=subprocess.run, inside=True,
                timeout=40, sleeper=time.sleep,
            )
            self.assertEqual(second.state, "running")
            urls = browser_log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(urls), 2)
            self.assertEqual(urls[1], first_url)

            self.starter.stop(paths, env, runner=subprocess.run, inside=True)
            self.assertTrue(
                wait_for(lambda: self.starter.resolve_state(paths)[0] == "absent", 20)
            )

            # Neustart erzeugt ein neues Token; der Starter liest es erneut.
            third = self.starter.start(
                paths, env, runner=subprocess.run, inside=True,
                timeout=40, sleeper=time.sleep,
            )
            self.assertEqual(third.state, "started")
            second_token = token_file.read_text(encoding="utf-8").strip()
            self.assertNotEqual(first_token, second_token)
            urls = browser_log.read_text(encoding="utf-8").splitlines()
            self.assertTrue(urls[-1].endswith("#t=" + second_token))
        finally:
            subprocess.run(
                ["tmux", "kill-session", "-t", "vibe-ui"],
                env=env, capture_output=True, text=True, timeout=30,
            )


class StarterCliTest(StarterFixture):
    def cli_env(self):
        env = dict(self.env)
        env.update({"VIBE_NO_CONTAINER": "1", "TERM": env.get("TERM", "xterm")})
        for key in ("TMUX", "TMUX_PANE"):
            env.pop(key, None)
        return env

    def test_status_reports_absent_without_starting_anything(self):
        completed = subprocess.run(
            [sys.executable, str(STARTER), "status"],
            env=self.cli_env(), capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("läuft nicht", completed.stdout)
        self.assertFalse(self.runtime.exists())

    def test_start_failure_is_reported_on_stderr_and_in_the_cleaned_log(self):
        prefix = self.root / "prefix"
        (prefix / "bin").mkdir(parents=True)
        (prefix / "bin" / "vibe_starter.py").write_text(
            STARTER.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (prefix / "bin" / "vibe_paths.py").write_text(
            PATHS_MODULE.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (prefix / "bin" / "vibe").write_text(
            "#!/usr/bin/env bash\necho 'Startfehler im Test' >&2\nexit 3\n",
            encoding="utf-8",
        )
        notifier = self.root / "notifier.log"
        notify = self.root / "fake-notify"
        notify.write_text(
            "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> " + str(notifier) + "\n",
            encoding="utf-8",
        )
        notify.chmod(0o755)
        env = self.cli_env()
        env.update(
            {
                "VIBE_NOTIFY": str(notify),
                "PATH": str(prefix / "bin") + os.pathsep + env["PATH"],
            }
        )
        env["VIBE_RUNTIME"] = str(self.runtime)
        env["VIBE_INSTALL"] = str(self.install)
        env["VIBE_STATE"] = str(self.install)
        completed = subprocess.run(
            [sys.executable, str(prefix / "bin" / "vibe_starter.py"), "start"],
            env=env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("Dashboard konnte nicht gestartet werden", completed.stderr)
        self.assertTrue(notifier.is_file())
        self.assertIn(
            "Dashboard konnte nicht gestartet werden",
            notifier.read_text(encoding="utf-8"),
        )
        log = self.runtime / "desktop-starter.log"
        self.assertTrue(log.is_file())
        self.assertIn("FEHLER", log.read_text(encoding="utf-8"))

    def test_desktop_installer_cli_installs_status_and_uninstalls(self):
        env = dict(self.env)
        env["XDG_DATA_HOME"] = str(self.home / ".local" / "share")
        env["VIBE_NO_CONTAINER"] = "1"
        script = REPO / "scripts" / "vibe-desktop.py"
        installed = subprocess.run(
            [sys.executable, str(script), "install"],
            env=env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(installed.returncode, 0, installed.stderr)
        data_home = Path(env["XDG_DATA_HOME"])
        desktop = data_home / "applications" / "vibe.desktop"
        starter = data_home / "vibe" / "vibe_starter.py"
        self.assertTrue(desktop.is_file())
        self.assertTrue(starter.is_file())
        status = subprocess.run(
            [sys.executable, str(script), "status"],
            env=env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("installiert", status.stdout)
        removed = subprocess.run(
            [sys.executable, str(script), "uninstall"],
            env=env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertFalse(desktop.exists())
        self.assertFalse(starter.exists())


class DesktopInstallTest(StarterFixture):
    def setUp(self):
        super().setUp()
        self.desktop_mod = load(DESKTOP, "vibe_desktop_v017")
        self.data_home = self.home / ".local" / "share"

    def run_install(self, **kwargs):
        return self.desktop_mod.install(
            home=self.home,
            data_home_path=str(self.data_home),
            starter_source=STARTER,
            paths_source=PATHS_MODULE,
            icon_source=ICON,
            **kwargs,
        )

    def test_install_creates_managed_desktop_entry_icon_starter_and_manifest(self):
        result = self.run_install()
        desktop = self.data_home / "applications" / "vibe.desktop"
        icon = self.data_home / "icons" / "hicolor" / "scalable" / "apps" / "vibe.svg"
        starter = self.data_home / "vibe" / "vibe_starter.py"
        paths = self.data_home / "vibe" / "vibe_paths.py"
        manifest = self.data_home / "vibe" / "install-manifest.json"
        self.assertEqual(result["files"][3], str(desktop))
        for path in (desktop, icon, starter, paths, manifest):
            self.assertTrue(path.is_file(), path)
        self.assertEqual(starter.stat().st_mode & 0o777, 0o755)
        text = desktop.read_text(encoding="utf-8")
        self.assertIn("X-Vibe-Managed=true", text)
        self.assertIn("Name=vibe", text)
        self.assertIn("Terminal=false", text)
        self.assertIn("[Desktop Action stop]", text)
        self.assertIn(str(starter), text)
        self.assertIn("Icon=" + str(icon), text)
        data = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(data["managed_by"], "vibe V-017")
        self.assertEqual(len(data["files"]), 4)
        for entry in data["files"].values():
            self.assertEqual(len(entry["sha256"]), 64)

    def test_desktop_exec_quotes_spaces_percent_and_dollar(self):
        entry = self.desktop_mod.desktop_entry(
            "/tmp/Vibe Code 100%/$x/starter.py", "/tmp/Icon 100%.svg"
        )
        exec_line = next(line for line in entry.splitlines() if line.startswith("Exec="))
        self.assertIn('"/tmp/Vibe Code 100%%/\\$x/starter.py"', exec_line)
        self.assertIn("python3", exec_line)
        self.assertTrue(exec_line.endswith("start"))
        icon_line = next(line for line in entry.splitlines() if line.startswith("Icon="))
        self.assertEqual(icon_line, "Icon=/tmp/Icon 100%.svg")

    def test_install_backs_up_foreign_desktop_entry(self):
        target = self.data_home / "applications" / "vibe.desktop"
        target.parent.mkdir(parents=True)
        target.write_text("[Desktop Entry]\nName=Fremd\n", encoding="utf-8")
        result = self.run_install()
        backups = [Path(path) for _, path in result["backups"]]
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "[Desktop Entry]\nName=Fremd\n")
        self.assertIn("X-Vibe-Managed=true", target.read_text(encoding="utf-8"))

    def test_uninstall_removes_only_managed_files(self):
        self.run_install()
        foreign = self.data_home / "applications" / "anderes.desktop"
        foreign.write_text("[Desktop Entry]\nName=Anderes\n", encoding="utf-8")
        runtime_file = self.runtime / "web.token"
        runtime_file.parent.mkdir(parents=True, exist_ok=True)
        runtime_file.write_text("geheim\n", encoding="utf-8")
        project_file = self.workspace / "projekt" / "README.md"
        project_file.parent.mkdir(parents=True)
        project_file.write_text("bleibt\n", encoding="utf-8")
        report = self.desktop_mod.uninstall(
            home=self.home, data_home_path=str(self.data_home)
        )
        self.assertFalse((self.data_home / "applications" / "vibe.desktop").exists())
        self.assertFalse((self.data_home / "vibe" / "vibe_starter.py").exists())
        self.assertTrue(foreign.is_file())
        self.assertTrue(runtime_file.is_file())
        self.assertTrue(project_file.is_file())
        self.assertFalse((self.data_home / "vibe" / "install-manifest.json").exists())
        self.assertEqual(report["kept"], [])

    def test_uninstall_keeps_modified_file(self):
        self.run_install()
        starter = self.data_home / "vibe" / "vibe_starter.py"
        starter.write_text(starter.read_text(encoding="utf-8") + "\n# lokal geändert\n", encoding="utf-8")
        report = self.desktop_mod.uninstall(
            home=self.home, data_home_path=str(self.data_home)
        )
        self.assertTrue(starter.is_file())
        self.assertIn(str(starter), report["kept"])
        manifest = json.loads(
            (self.data_home / "vibe" / "install-manifest.json").read_text(encoding="utf-8")
        )
        self.assertIn(str(starter), manifest["files"])

    def test_uninstall_is_idempotent(self):
        self.run_install()
        first = self.desktop_mod.uninstall(
            home=self.home, data_home_path=str(self.data_home)
        )
        self.assertTrue(first["installed"])
        second = self.desktop_mod.uninstall(
            home=self.home, data_home_path=str(self.data_home)
        )
        self.assertFalse(second["installed"])
        self.assertEqual(second["removed"], [])

    def test_status_reports_missing_and_installed(self):
        before = self.desktop_mod.status(
            home=self.home, data_home_path=str(self.data_home)
        )
        self.assertFalse(before["installed"])
        self.assertIn("nicht installiert", before["problems"])
        self.run_install()
        after = self.desktop_mod.status(
            home=self.home, data_home_path=str(self.data_home)
        )
        self.assertTrue(after["installed"])
        self.assertEqual(after["problems"], [])
        self.assertTrue(all(entry["state"] == "ok" for entry in after["files"]))

    def test_dry_run_writes_nothing(self):
        result = self.run_install(dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertFalse(self.data_home.exists())
        self.assertEqual(len(result["files"]), 4)

    def test_install_is_repeatable_without_backup_of_own_files(self):
        first = self.run_install()
        second = self.run_install()
        self.assertEqual(first["files"], second["files"])
        self.assertEqual(second["backups"], [])
        backups = list(self.data_home.rglob("*.bak-*"))
        self.assertEqual(backups, [])

    def test_icon_is_a_valid_svg_with_a_declared_size(self):
        tree = ET.parse(ICON)
        root = tree.getroot()
        self.assertTrue(root.tag.endswith("svg"))
        self.assertTrue(root.get("viewBox"))
        self.assertTrue(ICON.read_text(encoding="utf-8").strip().startswith("<svg"))

    def test_installed_starter_imports_vibe_paths_next_to_it(self):
        self.run_install()
        starter = self.data_home / "vibe" / "vibe_starter.py"
        env = dict(self.env)
        env.update(
            {
                "VIBE_NO_CONTAINER": "1",
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_INSTALL": str(self.install),
                "VIBE_STATE": str(self.install),
                "VIBE_UI_PORT": str(free_port()),
            }
        )
        completed = subprocess.run(
            [sys.executable, str(starter), "status"],
            env=env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("läuft nicht", completed.stdout)

    def test_desktop_entry_action_stops_only_vibe(self):
        entry = self.desktop_mod.desktop_entry("/tmp/vibe_starter.py", "/tmp/vibe.svg")
        self.assertIn("[Desktop Action stop]", entry)
        action = entry.split("[Desktop Action stop]", 1)[1]
        exec_line = next(line for line in action.splitlines() if line.startswith("Exec="))
        self.assertTrue(exec_line.endswith("stop"))
        self.assertNotIn("server", entry)
        self.assertNotIn("distrobox stop", entry)


if __name__ == "__main__":
    unittest.main()
