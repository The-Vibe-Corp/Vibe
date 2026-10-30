"""Abnahme V-016: Dashboard und opencode haben getrennte Lebenszyklen.

Geprüft wird mit echten, isolierten tmux-Sitzungen (eigener ``TMUX_TMPDIR``),
einem echten Dashboard-Prozess auf einem freien Port und Attrappen für
opencode. Es werden keine Modell-, Router- oder Android-Aufrufe ausgeführt.

Die Tests belegen:

* Dashboard beenden stoppt weder Agentenläufe noch opencode.
* opencode stoppen beendet nicht das Dashboard.
* Nur Sitzungen mit der vibe-Markierung werden beendet.
* Aktive SSE-Streams enden beim Beenden sauber; ein geschlossener Browser-Tab
  beendet keine Hintergrundprozesse.
* Ein belegter Port und ein fremder Dienst werden erkannt.
* Ein Neustart des Dashboards lässt Läufe und opencode unberührt.
"""
import http.client
import importlib.machinery
import importlib.util
import itertools
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
from unittest import mock
from pathlib import Path
from urllib.parse import quote

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
WEB = REPO / "bin" / "vibe-web.py"
RUNS = REPO / "bin" / "vibe_runs.py"

FAKE_OPENCODE = """#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  echo 'opencode v2.1.4'
  exit 0
fi
if [ "$1" = "models" ]; then
  echo 'opencode/model-a'
  exit 0
fi
echo "unerwarteter Aufruf: $*" >&2
exit 2
"""




def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for(predicate, timeout=15, interval=0.1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class FakeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = getattr(self.server, "body", b"fremd")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class LifecycleFixture(unittest.TestCase):
    """Isolierte Umgebung mit eigenem tmux-Server und freien Ports."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.runtime = self.root / "_logs"
        self.runtime.mkdir()
        self.install = self.root / "_toolchain"
        self.install.mkdir()
        self.ui_port = free_port()
        self.oc_port = free_port()
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            'TYPE=generic\nAGENT=tester\nVERIFY_FULL="true"\n', encoding="utf-8"
        )
        (self.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        fakebin = self.root / "fakebin"
        fakebin.mkdir()
        opencode = fakebin / "opencode"
        opencode.write_text(FAKE_OPENCODE, encoding="utf-8")
        opencode.chmod(0o755)
        self.tmux_dir = self.root / "tmux"
        self.tmux_dir.mkdir()
        # tmux akzeptiert TMUX_TMPDIR nur ohne fremde Schreibrechte.
        self.tmux_dir.chmod(0o700)
        self.env = os.environ.copy()
        for key in ("TMUX", "TMUX_PANE"):
            self.env.pop(key, None)
        self.env.update(
            {
                "HOME": str(self.home),
                "VIBE": str(self.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_INSTALL": str(self.install),
                "VIBE_UI_PORT": str(self.ui_port),
                "VIBE_OPENCODE_PORT": str(self.oc_port),
                "PATH": str(fakebin) + os.pathsep + self.env.get("PATH", ""),
                "TMUX_TMPDIR": str(self.tmux_dir),
                "TERM": self.env.get("TERM", "xterm"),
            }
        )
        self.fake_servers = []

    def tearDown(self):
        self.tmux("kill-server")
        for server in self.fake_servers:
            server.shutdown()
            server.server_close()
        self.tmp.cleanup()

    # -- Prozesse und Sitzungen -------------------------------------------
    def tmux(self, *args):
        return subprocess.run(
            ["tmux", *args],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def cli(self, *args, timeout=60):
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def session_exists(self, name):
        return self.tmux("has-session", "-t", name).returncode == 0

    def managed_session(self, name, kind):
        result = self.tmux(
            "new-session", "-d", "-s", name, "-e", "VIBE_MANAGED=" + kind,
            "--", "bash", "-lc", "sleep 120",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.session_exists(name))

    def unmanaged_session(self, name):
        result = self.tmux(
            "new-session", "-d", "-s", name, "--", "bash", "-lc", "sleep 120"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.session_exists(name))

    def kill_session(self, name):
        self.tmux("kill-session", "-t", name)

    def reset_sessions(self):
        for name in ("vibe-ui", "vibe-server", "vibe-proj"):
            self.tmux("kill-session", "-t", name)
        for path in (
            self.runtime / "runs.json",
            self.runtime / "runs.lock",
            self.runtime / "runner.active",
        ):
            if path.exists():
                path.unlink()

    def create_record(self, session="vibe-proj"):
        """Legt nur den Registereintrag an, ohne eine Sitzung zu starten."""
        result = subprocess.run(
            [
                sys.executable, str(RUNS), "start",
                "--runtime", str(self.runtime),
                "--project", str(self.project),
                "--name", "proj",
                "--key", "proj",
                "--agent", "tester",
                "--session", session,
            ],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip().splitlines()[-1]

    def start_run(self):
        """Startet einen laufenden Agentenprozess als verwaltete Sitzung.

        Der Prozessinhalt ist für die Lebenszyklusprüfung unerheblich; wichtig
        ist, dass es eine von vibe markierte Sitzung mit Registereintrag ist.
        """
        self.managed_session("vibe-proj", "run")
        return self.create_record()

    def start_managed_server(self):
        self.managed_session("vibe-server", "server")

    def start_dashboard(self):
        result = self.cli("ui", "start")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(wait_for(self.health, 20), result.stdout + result.stderr)

    def health(self):
        try:
            connection = http.client.HTTPConnection(
                "127.0.0.1", self.ui_port, timeout=2
            )
            connection.request("GET", "/api/health")
            response = connection.getresponse()
            body = response.read()
            connection.close()
        except OSError:
            return None
        if response.status != 200:
            return None
        try:
            return json.loads(body)
        except ValueError:
            return None

    def token(self):
        return (self.runtime / "web.token").read_text(encoding="utf-8").strip()

    def post(self, path, payload=None):
        body = json.dumps(payload or {}).encode("utf-8")
        connection = http.client.HTTPConnection("127.0.0.1", self.ui_port, timeout=5)
        connection.request(
            "POST",
            path,
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
                "X-Token": self.token(),
                "Origin": "http://127.0.0.1:" + str(self.ui_port),
                "Sec-Fetch-Site": "same-origin",
            },
        )
        response = connection.getresponse()
        data = json.loads(response.read())
        connection.close()
        return response.status, data

    def open_stream(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.ui_port, timeout=5)
        connection.request(
            "GET",
            "/api/stream?name=proj&kind=run&t=" + quote(self.token()),
        )
        connection.sock.settimeout(10)
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        return connection, response

    def read_stream_to_end(self, response):
        chunks = []
        while True:
            try:
                line = response.readline()
            except (OSError, socket.timeout):
                break
            if not line:
                break
            chunks.append(line)
        return b"".join(chunks)

    def fake_server(self, port, body):
        server = ThreadingHTTPServer(("127.0.0.1", port), FakeHandler)
        server.daemon_threads = True
        server.body = body
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.fake_servers.append(server)
        return server

    def load_cli_module(self):
        old = {key: os.environ.get(key) for key in self.env}
        os.environ.update(self.env)
        try:
            loader = importlib.machinery.SourceFileLoader(
                "vibe_lifecycle_under_test", str(CLI)
            )
            spec = importlib.util.spec_from_loader(loader.name, loader)
            module = importlib.util.module_from_spec(spec)
            loader.exec_module(module)
            return module
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


class ManagedProcessTest(LifecycleFixture):
    """Nur verwaltete Prozesse werden beendet; alle Kombinationen."""

    def stop(self, target, run_id=None):
        if target == "ui":
            return self.cli("ui", "stop")
        if target == "server":
            return self.cli("server", "stop")
        if run_id:
            return self.cli("stop", "proj", run_id)
        return self.cli("stop", "proj")

    def test_every_combination_of_running_processes(self):
        names = ("ui", "server", "run")
        subsets = [
            set(combination)
            for count in range(len(names) + 1)
            for combination in itertools.combinations(names, count)
        ]
        for target in names:
            for present in subsets:
                with self.subTest(target=target, running=sorted(present)):
                    self.reset_sessions()
                    run_id = None
                    if "ui" in present:
                        self.managed_session("vibe-ui", "ui")
                    if "server" in present:
                        self.managed_session("vibe-server", "server")
                    if "run" in present:
                        run_id = self.start_run()

                    result = self.stop(target, run_id)

                    self.assertEqual(
                        result.returncode, 0, result.stdout + result.stderr
                    )
                    self.assertEqual(
                        self.session_exists("vibe-ui"),
                        "ui" in present and target != "ui",
                        "ui nach Stopp von " + target,
                    )
                    self.assertEqual(
                        self.session_exists("vibe-server"),
                        "server" in present and target != "server",
                        "server nach Stopp von " + target,
                    )
                    self.assertEqual(
                        self.session_exists("vibe-proj"),
                        "run" in present and target != "run",
                        "Lauf nach Stopp von " + target,
                    )

    def test_foreign_sessions_with_the_same_name_are_not_stopped(self):
        for target in ("ui", "server", "run"):
            with self.subTest(target=target):
                self.reset_sessions()
                self.unmanaged_session("vibe-ui")
                self.unmanaged_session("vibe-server")
                self.unmanaged_session("vibe-proj")
                run_id = None
                if target == "run":
                    # Ein Registereintrag allein darf eine fremde Sitzung nicht
                    # zu einer verwalteten machen.
                    run_id = self.create_record()

                result = self.stop(target, run_id)

                self.assertNotEqual(
                    result.returncode, 0, result.stdout + result.stderr
                )
                self.assertIn("gehört nicht", result.stdout + result.stderr)
                self.assertTrue(self.session_exists("vibe-ui"))
                self.assertTrue(self.session_exists("vibe-server"))
                self.assertTrue(self.session_exists("vibe-proj"))

    def test_start_refuses_a_foreign_tmux_session(self):
        self.unmanaged_session("vibe-ui")
        self.unmanaged_session("vibe-server")

        ui = self.cli("ui", "start")
        server = self.cli("server", "start")

        self.assertNotEqual(ui.returncode, 0, ui.stdout + ui.stderr)
        self.assertIn("gehört nicht", ui.stdout + ui.stderr)
        self.assertNotEqual(server.returncode, 0, server.stdout + server.stderr)
        self.assertIn("gehört nicht", server.stdout + server.stderr)
        self.assertTrue(self.session_exists("vibe-ui"))
        self.assertTrue(self.session_exists("vibe-server"))

    def test_projects_named_ui_or_server_do_not_use_their_sessions(self):
        for name in ("ui", "server"):
            project = self.root / name
            (project / ".vibe").mkdir(parents=True)
            (project / ".vibe" / "project.env").write_text(
                "TYPE=generic\nAGENT=tester\n", encoding="utf-8"
            )
        module = self.load_cli_module()

        self.assertNotEqual(module.run_key("ui"), "ui")
        self.assertNotEqual(module.run_key("server"), "server")
        self.assertNotEqual(module.sess("ui"), module.ui_session())
        self.assertNotEqual(module.sess("server"), module.server_session())


class SessionMarkerUnitTest(LifecycleFixture):
    """Die Startbefehle markieren ihre tmux-Sitzung als von vibe verwaltet."""

    def fake_run(self, calls):
        def run(argv, **kwargs):
            calls.append(list(argv))
            if "has-session" in argv:
                return 1, ""
            return 0, ""

        return run

    def test_run_start_marks_the_session(self):
        module = self.load_cli_module()
        calls = []

        class Registry:
            def start(self, **kwargs):
                return {"id": "proj-test"}

            def finish(self, *args, **kwargs):
                return None

        with mock.patch.multiple(
            module,
            run=self.fake_run(calls),
            project_map=lambda: {"proj": str(self.project)},
            ppath=lambda name: str(self.project),
            is_init=lambda name: True,
            sandbox_status=lambda name: {"enabled": False},
            pause_after_active=lambda name: False,
            penv=lambda name: {"AGENT": "tester"},
            default_agent=lambda: "tester",
            run_key=lambda name: "proj",
            logpath=lambda name, kind="run": str(self.runtime / (name + ".log")),
            run_registry=lambda: Registry(),
        ), mock.patch.object(
            module.vibe_runs, "rotate_log", lambda *args, **kwargs: None
        ):
            module.cmd_run("proj")

        new_sessions = [call for call in calls if "new-session" in call]
        self.assertEqual(len(new_sessions), 1, calls)
        self.assertIn("-e", new_sessions[0])
        self.assertIn("VIBE_MANAGED=run", new_sessions[0])

    def test_ui_start_marks_the_session(self):
        module = self.load_cli_module()
        calls = []
        with mock.patch.multiple(
            module,
            run=self.fake_run(calls),
            dashboard_health=lambda: None,
            port_in_use=lambda host, port: False,
        ), mock.patch.object(module.time, "sleep", lambda seconds: None):
            module.cmd_ui("start")

        new_sessions = [call for call in calls if "new-session" in call]
        self.assertEqual(len(new_sessions), 1, calls)
        self.assertIn("-e", new_sessions[0])
        self.assertIn("VIBE_MANAGED=ui", new_sessions[0])

    def test_server_start_marks_the_session(self):
        module = self.load_cli_module()
        calls = []
        with mock.patch.multiple(
            module,
            run=self.fake_run(calls),
            server_health=lambda: None,
            port_in_use=lambda host, port: False,
        ), mock.patch.object(
            module.time, "sleep", lambda seconds: None
        ), mock.patch.object(
            module.vibe_opencode,
            "server_command",
            lambda port: ["opencode", "serve"],
        ):
            module.cmd_server("start")

        new_sessions = [call for call in calls if "new-session" in call]
        self.assertEqual(len(new_sessions), 1, calls)
        self.assertIn("-e", new_sessions[0])
        self.assertIn("VIBE_MANAGED=server", new_sessions[0])


class PortTest(LifecycleFixture):
    """Ein belegter Port und ein fremder Dienst werden nicht für vibe gehalten."""

    def test_dashboard_start_refuses_a_foreign_service_on_its_port(self):
        self.fake_server(self.ui_port, b"<html>fremder Dienst</html>")

        result = self.cli("ui", "start")

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("belegt", result.stdout + result.stderr)
        self.assertFalse(self.session_exists("vibe-ui"))

    def test_dashboard_start_refuses_a_foreign_vibe_lookalike(self):
        (self.runtime / "web.instance").write_text("echte-instanz\n", encoding="utf-8")
        self.fake_server(
            self.ui_port,
            b'{"ok":true,"app":"vibe","api":1,"instance":"fremde-instanz"}',
        )

        result = self.cli("ui", "start")

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("belegt", result.stdout + result.stderr)
        self.assertFalse(self.session_exists("vibe-ui"))

    def test_opencode_start_refuses_a_foreign_service_on_its_port(self):
        self.fake_server(self.oc_port, b"<html>fremder Dienst</html>")

        result = self.cli("server", "start")

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("belegt", result.stdout + result.stderr)
        self.assertFalse(self.session_exists("vibe-server"))

    def test_opencode_status_requires_a_healthy_opencode_answer(self):
        self.fake_server(self.oc_port, b"<html>fremder Dienst</html>")
        foreign = self.cli("server", "status")
        self.assertIn("aus", foreign.stdout)

        server = self.fake_servers.pop()
        server.shutdown()
        server.server_close()
        self.fake_server(
            self.oc_port, b'{"healthy":true,"version":"2.1.4"}'
        )
        healthy = self.cli("server", "status")
        self.assertIn("läuft", healthy.stdout)


class DashboardLifecycleTest(LifecycleFixture):
    """Dashboard beenden lässt Läufe und opencode am Leben."""

    def setUp(self):
        super().setUp()
        self.run_id = self.start_run()
        self.start_managed_server()
        self.start_dashboard()

    def test_shutdown_ends_streams_and_keeps_run_and_opencode(self):
        connection, response = self.open_stream()
        first = response.readline()
        self.assertTrue(first.startswith(b"data: "), first)

        status, data = self.post("/api/shutdown")
        self.assertEqual(status, 200, data)
        self.assertTrue(data["ok"])

        rest = self.read_stream_to_end(response)
        connection.close()
        self.assertIn("Dashboard wird beendet".encode(), rest)
        self.assertTrue(wait_for(lambda: not self.session_exists("vibe-ui"), 10))
        self.assertTrue(self.session_exists("vibe-proj"))
        self.assertTrue(self.session_exists("vibe-server"))

    def test_dashboard_stop_command_keeps_run_and_opencode(self):
        result = self.cli("ui", "stop")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(wait_for(lambda: not self.session_exists("vibe-ui"), 10))
        self.assertTrue(self.session_exists("vibe-proj"))
        self.assertTrue(self.session_exists("vibe-server"))

    def test_opencode_stop_keeps_dashboard_and_run(self):
        result = self.cli("server", "stop")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.session_exists("vibe-server"))
        self.assertTrue(self.session_exists("vibe-ui"))
        self.assertTrue(self.session_exists("vibe-proj"))
        self.assertIsNotNone(self.health())

    def test_closed_browser_tab_keeps_dashboard_and_run_alive(self):
        connection, response = self.open_stream()
        self.assertTrue(response.readline().startswith(b"data: "))
        connection.close()

        time.sleep(2.5)

        self.assertIsNotNone(self.health())
        self.assertTrue(self.session_exists("vibe-ui"))
        self.assertTrue(self.session_exists("vibe-proj"))

    def test_restart_keeps_run_and_opencode(self):
        before = self.health()
        self.assertIsNotNone(before)
        status, data = self.post("/api/shutdown")
        self.assertEqual(status, 200, data)
        self.assertTrue(wait_for(lambda: not self.session_exists("vibe-ui"), 10))

        self.start_dashboard()

        after = self.health()
        self.assertIsNotNone(after)
        self.assertNotEqual(before["instance"], after["instance"])
        self.assertTrue(self.session_exists("vibe-proj"))
        self.assertTrue(self.session_exists("vibe-server"))

    def test_sigterm_ends_streams_cleanly(self):
        # Das Dashboard aus setUp belegt den Port bereits; für den direkten
        # Prozess wird ein eigener Port verwendet.
        self.cli("ui", "stop")
        self.assertTrue(wait_for(lambda: not self.session_exists("vibe-ui"), 10))

        port = free_port()
        env = dict(self.env)
        env["VIBE_UI_PORT"] = str(port)
        process = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.addCleanup(lambda: process.poll() is None and process.kill())

        def direct_health():
            try:
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                connection.request("GET", "/api/health")
                response = connection.getresponse()
                ok = response.status == 200
                response.read()
                connection.close()
                return ok
            except OSError:
                return False

        self.assertTrue(wait_for(direct_health, 20))
        token = (self.runtime / "web.token").read_text(encoding="utf-8").strip()
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request(
            "GET", "/api/stream?name=proj&kind=run&t=" + quote(token)
        )
        connection.sock.settimeout(10)
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        self.assertTrue(response.readline().startswith(b"data: "))

        process.terminate()
        rest = self.read_stream_to_end(response)
        connection.close()
        output = process.communicate(timeout=15)[0]

        self.assertEqual(process.returncode, 0, output)
        self.assertIn("vibe-web beendet.", output)
        self.assertIn("Dashboard wird beendet".encode(), rest)
        self.assertTrue(self.session_exists("vibe-proj"))
        self.assertTrue(self.session_exists("vibe-server"))


if __name__ == "__main__":
    unittest.main()
