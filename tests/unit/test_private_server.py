"""Privater opencode-Server des Läufers: Start, Ende, Passwortvererbung und Steuerung.

Aufruf: python3 -m unittest tests.unit.test_private_server -v
"""


# ===========================================================================
# Unit-Abnahme (Teil 1): privater opencode-Server des Paket-Läufers
# ===========================================================================

import base64
import http.client
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "bin" / "vibe-run.sh"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support  # noqa: E402

from tests.unit import env_support  # noqa: E402
import test_harness as b6_support  # noqa: E402

MAIN_SESSION = "ses_b13"
PASSWORD = "b13-privat-4711"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def load_sandbox_module():
    """Lädt bin/vibe_sandbox.py als Modul (für state_dir-Berechnung)."""
    loader = importlib.machinery.SourceFileLoader(
        "vibe_sandbox_under_test_b13", str(REPO / "bin" / "vibe_sandbox.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def read_jsonl(path):
    """Liest eine JSONL-Datei; fehlt sie, ist die Liste leer."""
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    entries = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries


def commit_changed_fixture_state(project):
    """Commitet den Fixture-Stand nur, wenn es tatsächlich Änderungen gibt.

    GH-48 führt ``.vibe/`` als Laufzeitstand in die .gitignore der
    Fixture-Projekte ein. Ein Fall, der ausschließlich ``.vibe``-Dateien
    schreibt, hat deshalb nichts zu committen; ein leerer Commit ist an
    dieser Stelle kein Testfehler und darf den Lauf nicht abbrechen. Die
    fachlichen Assertionen des Falls bleiben unverändert.
    """
    status = support.git(project, "status", "--porcelain")
    if status.returncode != 0:
        raise RuntimeError(status.stdout + status.stderr)
    if status.stdout.strip():
        support.commit_all(project)


class SharedFakeOpenCode:
    """Erreichbarer „gemeinsamer Server“ für AK9 (Testprozess-Thread).

    GET /api/info wird nur mit korrekter Basic-Auth-Anmeldung
    ``opencode:<Kennwort aus credential_path>`` mit 200 beantwortet.
    """

    def __init__(self, port, credential_path):
        self.credential_path = str(credential_path)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), self._handler())
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever)
        self.thread.daemon = True

    def _handler(self):
        context = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def do_GET(self):
                try:
                    password = Path(context.credential_path).read_text(
                        encoding="utf-8").strip()
                except OSError:
                    password = ""
                expected = base64.b64encode(
                    ("opencode:" + password).encode("utf-8")).decode("ascii")
                ok = self.headers.get(
                    "Authorization", "") == "Basic " + expected
                body = json.dumps({"ok": ok}).encode("utf-8")
                self.send_response(200 if ok else 401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


class B13RunnerFixture(unittest.TestCase):
    """Läufer-Installation, Projekt-Attrappe, opencode-/curl-Attrappen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        self.runtime = self.root / "_logs"
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        self.fakebin = support.install_fake_tools(self.root)
        support.install_real_curl(self.fakebin)
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
            feedback=[support.ticket_record("B13", "Testpaket",
                                            type="feedback",
                                            description="Test")],
        )
        support.init_repo(self.project)
        support.commit_all(self.project)
        # Toter gemeinsamer Server: gebundener Socket ohne listen() —
        # Verbindungen werden zuverlässig abgewiesen.
        self.dead_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.dead_socket.bind(("127.0.0.1", 0))
        self.dead_port = self.dead_socket.getsockname()[1]
        self.addCleanup(self.dead_socket.close)
        self.serve_record = self.root / "serve.record.jsonl"
        self.args_file = self.runtime / "opencode.args"
        self.sandbox_root = None
        self.addCleanup(self.kill_leftover_serve)

    # ---------- Helfer ----------

    def password_file(self):
        return self.runtime / "opencode.password"

    def write_password(self, value=PASSWORD):
        self.runtime.mkdir(parents=True, exist_ok=True)
        path = self.password_file()
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
        return path

    def server_file(self):
        return self.runtime / "proj.log.server.json"

    def server_log_file(self):
        return self.runtime / "proj.log.server.log"

    def log_text(self):
        path = self.runtime / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def env(self, oc_port=None):
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
                "VIBE_INSTALL": str(self.install),
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_AGENTS_DIR": str(self.agents),
                "VIBE_OPENCODE_PORT": str(self.dead_port if oc_port is None
                                          else oc_port),
                "HOME": str(self.home),
                "VIBE_NO_CONTAINER": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
                "FAKE_ARGS_PATH": str(self.args_file),
                "FAKE_SERVE_RECORD": str(self.serve_record),
                "FAKE_SERVE_DELAY": "0.4",
                "FAKE_CALLS": str(self.root / "opencode.calls"),
                "FAKE_COUNTER": str(self.root / "counter"),
            }
        )
        return env

    def command(self):
        # Hausregel NTFS/FUSE: Skripte mit bash <datei> ausführen.
        return ["bash", str(self.tool_bin / "vibe-run.sh"), str(self.project)]

    def run_runner(self, env=None, timeout=180):
        return subprocess.run(
            self.command(),
            env=env if env is not None else self.env(),
            cwd=str(self.project),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def arg_records(self):
        self.assertTrue(
            self.args_file.exists(), "opencode wurde nicht aufgerufen")
        return support.opencode_arg_records(self.args_file)

    def run_records(self):
        return [record for record in self.arg_records()
                if record and record[0] == "run"]

    def serve_records(self):
        return read_jsonl(self.serve_record)

    def listening_events(self):
        return [entry for entry in self.serve_records()
                if entry.get("event") == "listening"]

    def kill_leftover_serve(self):
        """Beendet von der Attrappe gestartete Serverprozesse (Sauberkeit).

        Die Sandbox tearingt ihre Wraps selbst über --die-with-parent ab;
        hier werden nur direkte (nicht sandboxierte) Attrappenprozesse
        beendet.
        """
        for entry in read_jsonl(self.serve_record):
            pid = entry.get("pid")
            tmpdir = str(entry.get("tmpdir") or "")
            sandboxed = tmpdir.startswith("/tmp/opencode/vibe-sandbox/") \
                or "/vsb/" in tmpdir \
                or (self.sandbox_root is not None
                    and tmpdir.startswith(str(self.sandbox_root)))
            if (entry.get("event") == "listening"
                    and isinstance(pid, int) and not sandboxed):
                # Kennungen innerhalb einer Sandbox-PID-Umgebung sind vom
                # Host aus nicht adressierbar; die Sandbox raeumt selbst auf.
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
        if self.serve_record.exists():
            time.sleep(0.2)

    def assert_no_password_leak(self, password, *texts):
        """Kennwort darf in keinen der Texte auftauchen."""
        for label, text in texts:
            self.assertNotIn(
                password, text,
                f"Kennwort ist im {label} gelandet")


class PrivateServerStartTest(B13RunnerFixture):
    """AK1/AK2: Der Lauf startet den privaten Server und zieht ihn heran."""

    def test_run_starts_private_server_and_uses_it_exclusively(self):
        """AK1+AK2: Privater Server, --server-Ziel, Serverdatei, Geheimhaltung.

        Vorbedingung: kein gemeinsamer Server am freien Port; Kennwortdatei
        nichtleer; Läufer-Attrappe zeichnet opencode-Aufrufe und Serve-
        Beobachtungen auf.
        Aktion: ``vibe-run.sh <projekt>``.
        Erwartung: genau ein ``serve``-Aufruf; Agentenaufruf enthält
        ``--server http://127.0.0.1:<Port>`` und kein ``--standalone``;
        die Attrappe hat vorher GET /api/info mit korrekter Basic-Auth
        beantwortet; ``proj.log.server.json`` enthält gültige Loopback-URL,
        zugehörigen Port und den Kennwortdateipfad; Kennwort taucht weder in
        opencode-Argumenten, Serverdatei noch Protokollen auf;
        ``proj.log.server.log`` enthält die Serverausgabe, das Laufprotokoll
        nicht. Da der Lauf die Serverdatei beim Laufende entfernt (AK5/AK6),
        wird ihr Inhalt während des Laufs beobachtet: Ein Hintergrund-Thread
        sichert Dateiinhalt und Beobachtungszeitpunkt, sobald die Datei
        gültiges JSON enthält; geprüft wird der eingefangene Inhalt, und die
        Datei muss nach dem Laufende weg sein.
        Fehlerfall: --standalone bleibt, Serverdatei fehlt/fehlerhaft,
        Kennwort in argv/Protokoll, Serverausgabe im Laufprotokoll.
        """
        self.write_password()
        server_json = self.server_file()
        started = time.monotonic()
        # AK5/AK6 entfernen die Serverdatei beim Laufende; AK1 prüft ihren
        # Inhalt deshalb am Beobachtungszeitpunkt während des Laufs: Ein
        # Hintergrund-Thread sichert Inhalt und Zeitpunkt, sobald die Datei
        # existiert und gültiges JSON enthält (Teilschreibungen werden nicht
        # eingefangen).
        captured = {}
        stop = threading.Event()

        def capture_server_file():
            while not stop.is_set():
                try:
                    raw = server_json.read_text(encoding="utf-8")
                    data_seen = json.loads(raw)
                except (OSError, ValueError):
                    stop.wait(0.01)
                    continue
                captured["raw"] = raw
                captured["data"] = data_seen
                captured["at"] = time.monotonic()
                return

        observer = threading.Thread(target=capture_server_file, daemon=True)
        observer.start()
        try:
            result = self.run_runner()
        finally:
            ended = time.monotonic()
            stop.set()
            observer.join(timeout=10)
        log = self.log_text()
        self.assertEqual(
            result.returncode, 0, "Läufer bricht ab:\n" + result.stdout
            + result.stderr + "\n" + log)
        self.assertIn("FERTIG", log)

        serve_records = self.arg_records()
        serve_calls = [record for record in serve_records
                       if record and record[0] == "serve"]
        self.assertEqual(
            1, len(serve_calls),
            "Genau ein privater Server je Lauf erwartet: " + repr(serve_calls))
        run_calls = self.run_records()
        self.assertTrue(run_calls, "Agent wurde nicht gestartet")

        listening = self.listening_events()
        self.assertTrue(
            listening, "Der private Server lauschte nie: "
            + repr(self.serve_records()))
        bound_port = listening[0]["port_bound"]
        self.assertIsInstance(bound_port, int)
        self.assertGreater(bound_port, 0)

        url = "http://127.0.0.1:" + str(bound_port)
        for record in run_calls:
            self.assertIn("--server", record, repr(record))
            self.assertIn(url, record, repr(record))
            self.assertNotIn("--standalone", record, repr(record))

        health = [entry for entry in self.serve_records()
                  if entry.get("method") == "GET" and "/api/info" in entry.get("path", "")]
        self.assertTrue(
            health, "Der Server wurde nie auf Gesundheit geprüft")
        self.assertTrue(
            any(entry.get("auth_ok") for entry in health),
            "Die Gesundheitsprüfung kam ohne gültige Basic-Auth-Anmeldung: "
            + repr(health))

        self.assertTrue(
            captured,
            "Serverdatei wurde während des Laufs nicht angelegt oder nicht "
            "als gültiges JSON beobachtet")
        self.assertTrue(
            started <= captured["at"] <= ended,
            "Die Serverdatei wurde nicht während des Laufs beobachtet")
        self.assertFalse(
            server_json.exists(),
            "Serverdatei wurde beim Laufende nicht entfernt (AK5/AK6)")
        data = captured["data"]
        url_value = str(data.get("url") or "")
        self.assertTrue(url_value.startswith("http://127.0.0.1:"),
                        f"URL ist nicht Loopback: {url_value!r}")
        self.assertEqual(
            bound_port, int(data.get("port")),
            f"Port in Serverdatei stimmt nicht: {data}")
        password_file_value = str(data.get("password_file") or "")
        self.assertTrue(password_file_value, "password_file fehlt")
        referenced = Path(password_file_value)
        self.assertTrue(
            referenced.exists(), f"Kennwortdatei fehlt: {password_file_value}")
        self.assertEqual(
            PASSWORD, referenced.read_text(encoding="utf-8").strip(),
            "Kennwortdatei der Serverdatei passt nicht zur Anmeldung")

        self.assert_no_password_leak(
            PASSWORD,
            ("opencode-Argumenten", self.args_file.read_bytes().decode(
                "utf-8", "surrogateescape")),
            ("Serverdatei", captured["raw"]),
            ("Laufprotokoll", log),
            ("Läufer-Ausgabe", result.stdout + result.stderr),
        )

        server_log = self.server_log_file()
        self.assertTrue(
            server_log.exists(), "Serverausgabe-Datei fehlt: "
            + repr(sorted(p.name for p in self.runtime.iterdir())))
        self.assertIn(
            "SERVE_FAKE_START", server_log.read_text(encoding="utf-8"),
            "Serverausgabe erreichte nicht die eigene Datei")
        self.assertNotIn(
            "SERVE_FAKE_START", log,
            "Serverausgabe gehört nicht ins Laufprotokoll")

    def test_run_aborts_when_the_private_server_never_becomes_healthy(self):
        """AK1: Ohne gesunden Server startet der Agent nicht.

        Vorbedingung: Kennwortdatei nichtleer; die Serve-Attrappe lauscht
        nie (FAKE_SERVE_NEVER=1).
        Aktion: ``vibe-run.sh <projekt>``.
        Erwartung: Der Lauf bricht mit verständlicher Meldung ab; es gibt
        keinen ``opencode run``-Aufruf.
        Fehlerfall: Der Agent startet trotzdem gegen einen toten Server.
        """
        self.write_password()
        env = self.env()
        env["FAKE_SERVE_NEVER"] = "1"
        env.pop("FAKE_SERVE_DELAY", None)
        result = self.run_runner(env=env, timeout=120)

        self.assertNotEqual(
            result.returncode, 0,
            "Der Lauf startete den Agenten ohne gesunden privaten Server")
        run_calls = self.run_records()
        self.assertFalse(
            run_calls,
            "Agent wurde ohne gesunden Server gestartet: " + repr(run_calls))
        detail = result.stdout + result.stderr + self.log_text()
        self.assertTrue(
            detail.strip(), "Abbruch ohne verständliche Meldung")

    def test_server_output_goes_to_the_dedicated_file(self):
        """AK2: Serverausgabe landet nur in <Laufprotokoll>.server.log.

        Vorbedingung: wie AK1-Lauf.
        Aktion: Lauf ausführen und beide Protokolldateien lesen.
        Erwartung: server.log existiert mit Servermarkierung; Laufprotokoll
        ohne Servermarkierung.
        Fehlerfall: Serverausgabe im Laufprotokoll oder fehlende Datei.
        """
        self.write_password()
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        log = self.log_text()
        server_log = self.server_log_file()
        self.assertTrue(server_log.exists(), "server.log fehlt")
        self.assertIn("SERVE_FAKE_START",
                      server_log.read_text(encoding="utf-8"))
        self.assertNotIn("SERVE_FAKE_START", log)


class PrivateServerEndTest(B13RunnerFixture):
    """AK5: Beim Laufende ist der private Server weg."""

    def test_run_end_stops_the_private_server_and_removes_the_server_file(self):
        """AK5: Ende räumt Server und Serverdatei weg.

        Vorbedingung: Kennwortdatei nichtleer; Lauf läuft durch.
        Aktion: Lauf ausführen, danach Serverdatei und Port prüfen.
        Erwartung: ``proj.log.server.json`` existiert nicht mehr; eine
        Verbindung auf den Port des privaten Servers wird abgewiesen.
        Fehlerfall: Serverdatei bleibt liegen oder der Server lauscht
        weiter.
        """
        self.write_password()
        result = self.run_runner()
        log = self.log_text()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        self.assertFalse(
            self.server_file().exists(),
            "Serverdatei wurde beim Laufende nicht entfernt")
        listening = self.listening_events()
        self.assertTrue(listening, "Es wurde nie ein Server gestartet")
        port = listening[0]["port_bound"]
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                with socket.create_connection(
                        ("127.0.0.1", port), timeout=0.5):
                    time.sleep(0.1)
            except OSError:
                break
        else:
            self.fail("Der private Server lauscht nach dem Laufende weiter")
        self.assert_no_password_leak(PASSWORD, ("Laufprotokoll", log))


class StandaloneFallbackTest(B13RunnerFixture):
    """AK4: Ohne nutzbares Kennwort bleibt es beim bisherigen Verhalten."""

    def test_run_without_password_file_stays_standalone(self):
        """AK4: Fehlende Kennwortdatei → --standalone, keine Serverdatei.

        Vorbedingung: keine ``opencode.password`` im Laufzeitordner.
        Aktion: ``vibe-run.sh <projekt>``.
        Erwartung: Agentenaufruf mit ``--standalone``, kein ``serve``-Aufruf,
        keine ``proj.log.server.json``.
        Fehlerfall: Ein privater Server wird trotzdem gestartet.
        """
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        run_calls = self.run_records()
        self.assertTrue(run_calls, "Agent wurde nicht gestartet")
        for record in run_calls:
            self.assertIn("--standalone", record, repr(record))
        self.assertEqual(
            [], [record for record in self.arg_records()
                 if record and record[0] == "serve"],
            "Ohne Kennwortdatei startet kein privater Server")
        self.assertFalse(self.server_file().exists())

    def test_run_with_empty_password_file_stays_standalone(self):
        """AK4: Leere Kennwortdatei gilt wie fehlende.

        Vorbedingung: ``opencode.password`` existiert, ist aber leer.
        Aktion: ``vibe-run.sh <projekt>``.
        Erwartung: wie fehlende Datei (--standalone, kein Server, keine
        Serverdatei).
        Fehlerfall: Leere Datei löst eine Serveranmeldung aus.
        """
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.password_file().write_text("   \n", encoding="utf-8")

        result = self.run_runner()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        run_calls = self.run_records()
        self.assertTrue(run_calls, "Agent wurde nicht gestartet")
        for record in run_calls:
            self.assertIn("--standalone", record, repr(record))
        self.assertEqual(
            [], [record for record in self.arg_records()
                 if record and record[0] == "serve"],
            "Mit leerer Kennwortdatei startet kein privater Server")
        self.assertFalse(self.server_file().exists())


class SandboxPrivateServerTest(B13RunnerFixture):
    """AK6: Der private Server läuft innerhalb der Sandbox-Wrapping-Kette."""

    @env_support.skip_if_sandbox_nested
    def test_sandboxed_run_starts_the_private_server_inside_the_sandbox(self):
        """AK6: Sandbox-Lauf hüllt auch den privaten Server ein.

        Vorbedingung: bubblewrap (bwrap) vorhanden; Projektumgebung mit
        SANDBOX=on und SANDBOX_TOOLS=\"git\" (bewertet über
        vibe_sandbox.py --enabled); vibe_sandbox.py liegt in der
        Testinstallation; VIBE_SANDBOX_ROOT zeigt auf eine kontrollierte
        Fixture-Wurzel; Kennwortdatei nichtleer; die Laufzeit und das
        Projekt sind als Schreibverzeichnisse freigeben und committet; die
        Beobachtungsdateien liegen unter /tmp/opencode (dort auch in der
        Sandbox beschreibbar).
        Aktion: ``vibe-run.sh <projekt>``.
        Erwartung: Der Lauf meldet „Sandbox: on“; Agentenaufruf mit
        ``--server http://127.0.0.1:<Port>`` statt --standalone; genau ein
        Serve-Aufruf; dessen TMPDIR ist exakt der Tempordner des
        Sandbox-Zustandsordners des Integrationsprojekts
        (``state_dir(P)/tmp``, berechnet mit demselben Modul und
        VIBE_SANDBOX_ROOT), unabhängig vom äußeren TMPDIR; die Serverdatei
        wird beim Laufende entfernt. Der Zustandsort gehört zum Projekt,
        nicht zur Arbeitskopie: Der private Server wird mit ``$P`` als
        Sandbox-Projektargument gestartet (nur chdir/write-dir wechseln),
        damit Sandbox-Zustand und opencode-DB pro Integrationsprojekt
        bleiben und nicht je Arbeitskopie doppelte Sitzungslogs entstehen.
        Fehlerfall: Sandbox bleibt aus (unverpackter Server), Agent läuft
        mit --standalone, TMPDIR entstammt der Umgebung, Serverdatei bleibt
        liegen.
        """
        self.assertIsNotNone(shutil.which("bwrap"), "bubblewrap (bwrap) fehlt")
        self.write_password()
        # Sandbox wirklich einschalten: Der Läufer bewertet SANDBOX über
        # vibe_sandbox.py anhand .vibe/project.env; ohne Eintrag bliebe sie
        # aus und der private Server liefe unverpackt.
        env_file = self.project / ".vibe" / "project.env"
        env_file.write_text(
            env_file.read_text(encoding="utf-8")
            + "SANDBOX=on\n"
            + 'SANDBOX_TOOLS="git"\n',
            encoding="utf-8")
        # Schreibrechte für Laufzeit und Projekt: Die Attrappe schließt das
        # Paket im Arbeitsbaum unter $RUNTIME/worktrees ab.
        (self.project / ".vibe" / "permissions.json").write_text(
            json.dumps({"write_dirs": [
                os.path.realpath(self.project),
                os.path.realpath(self.runtime),
            ]}),
            encoding="utf-8")
        commit_changed_fixture_state(self.project)
        # vibe_sandbox.py gehört zur Installation; der Läufer bricht sonst
        # ab, sobald SANDBOX gesetzt ist.
        shutil.copy(REPO / "bin" / "vibe_sandbox.py",
                    self.tool_bin / "vibe_sandbox.py")
        # Kontrollierte, kurze Sandbox-Wurzel: Der Zustandsordner ist damit
        # deterministisch berechenbar und hängt nicht vom äußeren TMPDIR
        # oder vom Nutzerzustand ab.
        self.sandbox_root = Path("/tmp/opencode") / (
            "b13-sbstate-" + str(os.getpid()) + "-" + str(time.time_ns()))
        self.sandbox_root.mkdir(parents=True)
        self.addCleanup(lambda: shutil.rmtree(
            self.sandbox_root, ignore_errors=True))
        # Beobachtungsdateien müssen auch innerhalb der Sandbox beschreibbar
        # sein: /tmp/opencode ist immer gebunden.
        observed = Path("/tmp/opencode") / (
            "b13-obs-" + str(os.getpid()) + "-" + str(time.time_ns()))
        observed.mkdir(parents=True)
        self.addCleanup(lambda: shutil.rmtree(observed, ignore_errors=True))
        env = self.env()
        env["FAKE_SERVE_RECORD"] = str(observed / "serve.record.jsonl")
        env["FAKE_ARGS_PATH"] = str(observed / "opencode.args")
        env["FAKE_CALLS"] = str(observed / "opencode.calls")
        env["FAKE_COUNTER"] = str(observed / "counter")
        env["VIBE_SANDBOX_ROOT"] = str(self.sandbox_root)
        self.args_file = Path(env["FAKE_ARGS_PATH"])
        self.serve_record = Path(env["FAKE_SERVE_RECORD"])
        result = self.run_runner(env=env, timeout=300)

        log = self.log_text()
        detail = result.stdout + result.stderr + log
        self.assertEqual(
            result.returncode, 0, "Läufer bricht ab:\n" + detail)
        self.assertIn("FERTIG", log)
        self.assertIn(
            "Sandbox: on", log,
            "Der Lauf bewertete die Sandbox nicht als eingeschaltet:\n" + log)

        run_calls = self.run_records()
        listening = self.listening_events()
        self.assertTrue(
            listening, "In der Sandbox startete kein privater Server")
        self.assertEqual(
            1, len(listening), "Genau ein privater Server je Lauf")
        bound_port = listening[0]["port_bound"]
        tmpdir = str(listening[0].get("tmpdir") or "")
        # Die Arbeitskopie entnimmt dem Laufprotokoll (Versuch-Zeile). Der
        # private Server behält $P als Sandbox-Projektargument; sein
        # Zustandsordner wird deshalb aus dem Integrationsprojekt berechnet
        # (nicht aus der Arbeitskopie) und mit demselben Sandbox-Modul sowie
        # derselben VIBE_SANDBOX_ROOT wie im Lauf ermittelt.
        attempts = re.findall(r"--- Versuch \d+/\d+ für \S+ in (\S+) ---", log)
        self.assertTrue(
            attempts, "Arbeitskopie fehlt im Laufprotokoll:\n" + log)
        worktree = attempts[-1]
        self.assertNotEqual(
            os.path.realpath(worktree), os.path.realpath(self.project),
            "Die Versuch-Zeile nennt keine eigene Arbeitskopie")
        sandbox = load_sandbox_module()
        old_root = os.environ.get("VIBE_SANDBOX_ROOT")
        os.environ["VIBE_SANDBOX_ROOT"] = str(self.sandbox_root)
        try:
            expected_state = sandbox.state_dir(self.project)
        finally:
            if old_root is None:
                os.environ.pop("VIBE_SANDBOX_ROOT", None)
            else:
                os.environ["VIBE_SANDBOX_ROOT"] = old_root
        self.assertEqual(
            Path(tmpdir), Path(expected_state) / "tmp",
            "Der private Server lief nicht im Zustandsordner der Sandbox "
            "(TMPDIR=" + repr(tmpdir) + ", erwartet "
            + repr(str(Path(expected_state) / "tmp")) + ")")
        url = "http://127.0.0.1:" + str(bound_port)
        for record in run_calls:
            self.assertIn("--server", record, repr(record))
            self.assertIn(url, record, repr(record))
            self.assertNotIn("--standalone", record, repr(record))
        self.assertFalse(
            self.server_file().exists(),
            "Serverdatei wurde beim Laufende nicht entfernt")


class PreflightWriteDirChangeTest(B13RunnerFixture):
    """AP1: Der private Server gehört zum Zielverzeichnis, nicht nur zum Lauf."""

    def test_preflight_server_is_restarted_for_the_package_worktree(self):
        """AP1: Preflight-Assistent in $P, Paket danach in $WT.

        Vorbedingung: Kennwortdatei nichtleer; autonome Reparatur für „proj“
        eingeschaltet; uncommittete Datei im Integrationsprojekt; Assistenz
        aktiv; ``FAKE_PREFLIGHT_MODE=fix``; ``VIBE_MAX_PACKAGES=1``. Die
        opencode-Attrappe zeichnet pro Server ``cwd`` und ``term`` auf; es
        wird keine Sandbox und kein echtes bwrap benötigt.
        Aktion: ``vibe-run.sh <projekt>``.
        Erwartung: zwei ``listening``-Ereignisse — das erste mit cwd=$P aus
        der Preflight-Reparatur, das zweite mit cwd=$WT aus der Versuch-Zeile
        des Pakets — und dazwischen mindestens ein ``term``-Ereignis. Der
        Lauf endet erfolgreich.
        Fehlerfall: Der gesunde Preflight-Server wird weiterverwendet; die
        Arbeitskopie wäre dann nur lesend eingebunden (nur ein listening mit
        cwd=$P).
        """
        self.write_password()
        (self.project / "unfertig.txt").write_text(
            "unfertig\n", encoding="utf-8")
        self.runtime.mkdir(parents=True, exist_ok=True)
        (self.runtime / "autonomous.json").write_text(
            json.dumps({
                "version": 1,
                "projects": {
                    "proj": {
                        "enabled": True,
                        "changed": "2026-01-01T00:00:00Z",
                    }
                },
            }),
            encoding="utf-8",
        )
        env = self.env()
        env.update({
            "VIBE_PREFLIGHT_ASSIST": "1",
            "VIBE_PREFLIGHT_QUESTION_TIMEOUT": "20",
            "FAKE_PREFLIGHT_MODE": "fix",
            "VIBE_MAX_PACKAGES": "1",
        })

        result = self.run_runner(env=env, timeout=240)

        log = self.log_text()
        detail = result.stdout + result.stderr + log
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        self.assertIn("FERTIG", log)
        attempts = re.findall(r"--- Versuch \d+/\d+ für \S+ in (\S+) ---", log)
        self.assertTrue(attempts, "Paketversuch fehlt im Laufprotokoll:\n" + log)
        worktree = attempts[-1]

        listening = self.listening_events()
        self.assertEqual(
            2, len(listening),
            "Es wurden nicht zwei Server gestartet (einer je Zielverzeichnis):\n"
            + repr(self.serve_records()) + "\n" + detail)
        self.assertEqual(
            os.path.realpath(self.project),
            os.path.realpath(str(listening[0].get("cwd") or "")),
            "Der erste Server lief nicht im Integrationsprojekt $P")
        self.assertEqual(
            os.path.realpath(worktree),
            os.path.realpath(str(listening[1].get("cwd") or "")),
            "Der zweite Server lief nicht in der Paket-Arbeitskopie $WT")
        events = [entry.get("event") for entry in self.serve_records()]
        listening_positions = [
            index for index, event in enumerate(events) if event == "listening"
        ]
        self.assertEqual(2, len(listening_positions), repr(events))
        self.assertTrue(
            any(event == "term" for event in events[
                listening_positions[0] + 1:listening_positions[1]]),
            "Zwischen den beiden Servern wurde kein term protokolliert: "
            + repr(events))


class PiNoPrivateServerTest(B13RunnerFixture):
    """AK7: Pi-Läufe starten keinen privaten Server."""

    def test_pi_run_starts_no_private_server(self):
        """AK7: Harness pi → kein serve, keine Serverdatei.

        Vorbedingung: harness.json wählt pi; Kennwortdatei nichtleer; die
        Pi-Attrappe liegt im PATH.
        Aktion: ``vibe-run.sh <projekt>``.
        Erwartung: Der Lauf verwendet Pi, ruft ``opencode serve`` nie auf und
        legt keine ``proj.log.server.json`` an.
        Fehlerfall: Pi-Lauf startet trotzdem einen privaten Server.
        """
        (self.install / "harness.json").write_text(
            json.dumps({"harness": "pi"}, ensure_ascii=False) + "\n",
            encoding="utf-8")
        # Pi liest den Prompt-Text der Agentendatei; der gewählte Agent muss
        # als Datei vorliegen (Projektagenten haben Vorrang).
        project_agent = self.project / ".opencode" / "agents" / "tester.md"
        project_agent.parent.mkdir(parents=True, exist_ok=True)
        project_agent.write_text(
            "---\ndescription: Testagent\nmode: primary\n---\n"
            "Du bist der Coding-Agent der Arbeitspakete.\n",
            encoding="utf-8")
        support.commit_all(self.project)
        (self.tool_bin / "vibe_harness.py").write_text(
            (REPO / "bin" / "vibe_harness.py").read_text(encoding="utf-8"),
            encoding="utf-8")
        (self.tool_bin / "vibe_opencode.py").write_text(
            (REPO / "bin" / "vibe_opencode.py").read_text(encoding="utf-8"),
            encoding="utf-8")
        (self.fakebin / "pi").write_text(
            b6_support.FAKE_PI, encoding="utf-8")
        (self.fakebin / "pi").chmod(0o755)
        self.write_password()
        env = self.env()
        env["FAKE_PI_ARGS_PATH"] = str(self.root / "pi.args")
        env["FAKE_PI_SESSION"] = "ses-pi-b13"
        env["FAKE_PI_COUNTER"] = str(self.root / "pi.counter")

        result = self.run_runner(env=env)

        self.assertEqual(
            result.returncode, 0,
            "Läufer bricht ab:\n" + result.stdout + result.stderr)
        self.assertTrue(
            (self.root / "pi.args").exists(), "Pi wurde nicht aufgerufen")
        self.assertEqual(
            [], [record for record in support.opencode_arg_records(
                self.args_file)
                 if record and record[0] == "serve"],
            "Pi-Läufe starten keinen privaten opencode-Server")
        self.assertFalse(
            self.server_file().exists(), "Pi-Lauf schrieb eine Serverdatei")


class SharedServerKeptTest(B13RunnerFixture):
    """AK9: Erreichbarer gemeinsamer Server behält das bisherige Ziel."""

    def test_reachable_shared_server_keeps_the_shared_target(self):
        """AK9: Gemeinsamer Server erreichbar → --server auf diesen Port.

        Vorbedingung: ein erreichbarer „gemeinsamer“ Server am Port aus
        VIBE_OPENCODE_PORT, der GET /api/info nur mit korrekter Basic-Auth
        beantwortet; Kennwortdatei nichtleer.
        Aktion: ``vibe-run.sh <projekt>``.
        Erwartung: Agentenaufruf mit ``--server http://127.0.0.1:<Port>``,
        kein ``serve``-Aufruf, keine ``proj.log.server.json``.
        Fehlerfall: Trotz erreichbarem gemeinsamen Server wird ein privater
        Server gestartet.
        """
        self.write_password()
        shared_port = free_port()
        shared = SharedFakeOpenCode(shared_port, self.password_file()).start()
        self.addCleanup(shared.stop)
        env = self.env(oc_port=shared_port)

        result = self.run_runner(env=env)

        self.assertEqual(
            result.returncode, 0,
            "Läufer bricht ab:\n" + result.stdout + result.stderr)
        run_calls = self.run_records()
        self.assertTrue(run_calls, "Agent wurde nicht gestartet")
        url = "http://127.0.0.1:" + str(shared_port)
        for record in run_calls:
            self.assertIn("--server", record, repr(record))
            self.assertIn(url, record, repr(record))
        self.assertEqual(
            [], [record for record in self.arg_records()
                 if record and record[0] == "serve"],
            "Bei erreichbarem gemeinsamen Server startet kein privater")
        self.assertFalse(
            self.server_file().exists(),
            "Bei gemeinsamen Server entsteht keine Serverdatei")


# ===========================================================================
# Unit-Abnahme (Teil 2): Zusatzanweisungen an den privaten Server
# ===========================================================================

import base64
import http.client
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

WEB = REPO / "bin" / "vibe-web.py"
RUNS_PY = REPO / "bin" / "vibe_runs.py"

MAIN_SESSION_b13 = "ses_main"
CHILD_SESSION = "ses_child"
FOREIGN_SESSION = "ses_fremd"
STEER_TEXT = "B13: Bitte das Paket F19 nachziehen"
SERVER_CREDENTIAL = PASSWORD


class _PrivateServerHandler(BaseHTTPRequestHandler):
    """Lokaler „privater opencode-Server“ des aktiven Laufs.

    Alle Anfragen werden protokolliert; nur mit korrekter Basic-Auth-
    Anmeldung ``opencode:<Kennwort aus credential_path>`` antwortet er mit
    200, sonst mit 401.
    """

    context = None

    def log_message(self, *args):
        return

    def _record(self, body=""):
        with open(self.context["record_path"], "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "method": self.command,
                "path": self.path,
                "auth_ok": self._auth_ok(),
                "body": body,
            }, ensure_ascii=False) + "\n")

    def _auth_ok(self):
        try:
            password = Path(self.context["credential_path"]).read_text(
                encoding="utf-8").strip()
        except OSError:
            return False
        encoded = base64.b64encode(("opencode:" + password).encode()).decode()
        return self.headers.get("Authorization", "") == "Basic " + encoded

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._record()
        self._send_json(200, {"ok": self._auth_ok()})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        self._record(body)
        self._send_json(200 if self._auth_ok() else 401, {"ok": self._auth_ok()})


def make_private_handler(context):
    def build():
        handler = type("BoundHandler", (BaseHTTPRequestHandler,), {})
        for attribute, value in _PrivateServerHandler.__dict__.items():
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


class B13SteerFixture(unittest.TestCase):
    """Dashboard mit totem gemeinsamen Server und privatem Testserver."""

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
            "# FEEDBACK\n\n- [ ] B13 Steuerung\n  Beschreibung: Test\n",
            encoding="utf-8")
        agent_path = cls.project / ".opencode" / "agents" / "test-agent.md"
        agent_path.parent.mkdir(parents=True)
        agent_path.write_text(
            "---\ndescription: Testagent\nmode: primary\n---\n"
            "Du bist der Coding-Agent der Arbeitspakete.\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", "-b", "main", str(cls.project)],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", cls.project, "config", "user.name",
                        "Test"], check=True, capture_output=True)
        subprocess.run(["git", "-C", cls.project, "config", "user.email",
                        "test@example.invalid"], check=True, capture_output=True)
        subprocess.run(["git", "-C", cls.project, "add", "-A"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", cls.project, "commit", "-q", "-m",
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
        # Toter gemeinsamer Server: gebundener Socket ohne listen(); alle
        # Verbindungen dorthin werden zuverlässig abgewiesen (Bug-Nachbild).
        cls.dead_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cls.dead_socket.bind(("127.0.0.1", 0))
        cls.dead_port = cls.dead_socket.getsockname()[1]
        # Privater Server des Laufs (Testprozess-Thread).
        cls.priv_port = None
        cls.context = {
            "credential_path": str(cls.log_dir / "opencode.password"),
            "record_path": str(cls.root / "private-server.requests.jsonl"),
        }
        cls.port = cls.free_port()
        cls.web_log_path = cls.root / "web-server.log"
        cls.env = cls.build_env()
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=cls.env,
            stdout=open(cls.web_log_path, "w", encoding="utf-8"),
            stderr=subprocess.STDOUT, text=True)
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
                    + cls.web_log_path.read_text(
                        encoding="utf-8", errors="replace"))
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()

    @classmethod
    def free_port(cls):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

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
            "VIBE_OPENCODE_PORT": str(cls.dead_port),
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
        cls.dead_socket.close()
        cls.tmp.cleanup()

    # ---------- Helfer ----------

    def setUp(self):
        for path in (self.log_dir / "proj.log.state.json",
                     self.log_dir / "proj.log.server.json",
                     self.log_dir / "runs.json",
                     self.state_dir / "harness.json",
                     self.tmux_log,
                     Path(self.context["record_path"]),
                     Path(self.context["credential_path"])):
            if path.exists():
                path.unlink()
        if self.priv_port is not None:
            self.stop_private_server()

    def start_private_server(self):
        """Startet den lokalen privaten Server auf einem freien Port."""
        port = self.free_port()
        self.priv_http = ThreadingHTTPServer(
            ("127.0.0.1", port), make_private_handler(self.context))
        self.priv_http.daemon_threads = True
        self.priv_thread = threading.Thread(target=self.priv_http.serve_forever)
        self.priv_thread.daemon = True
        self.priv_thread.start()
        self.priv_port = port
        return port

    def stop_private_server(self):
        self.priv_http.shutdown()
        self.priv_http.server_close()
        self.priv_thread.join(timeout=5)
        self.priv_port = None

    def password_file(self):
        return self.log_dir / "opencode.password"

    def write_password(self, value=PASSWORD):
        path = self.password_file()
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
        return path

    def server_file(self):
        return self.log_dir / "proj.log.server.json"

    def write_server_file(self, url=None, port=None, password_file=None,
                          raw=None):
        """Schreibt die Serverdatei des aktiven Laufs (Läufer-Nachbildung)."""
        if raw is None:
            data = {
                "url": url or "http://127.0.0.1:%d" % self.priv_port,
                "port": port if port is not None else self.priv_port,
                "password_file": password_file
                or str(self.password_file()),
            }
            raw = json.dumps(data, ensure_ascii=False)
        self.server_file().write_text(raw, encoding="utf-8")
        return self.server_file()

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

    def write_state(self, data):
        path = self.log_dir / "proj.log.state.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def running_entry(self, session, agent, started):
        return {
            "session": session,
            "agent": agent,
            "description": agent + " arbeitet",
            "prompt": "Kurzer Auftrag",
            "status": "running",
            "started": int(started),
            "ended": 0,
            "output": "",
        }

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

    def post_steer(self, session=None):
        body = {"name": "proj", "text": STEER_TEXT}
        if session is not None:
            body["session"] = session
        return self.request("POST", "/api/steer", body)

    def private_requests(self):
        path = Path(self.context["record_path"])
        if not path.exists():
            return []
        return [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines()
                if line.strip()]

    def deliveries(self):
        return [entry for entry in self.private_requests()
                if entry["method"] == "POST" and "/prompt" in entry["path"]]

    @staticmethod
    def ok_flag(payload):
        return bool(payload) and payload.get("ok") is True

    @staticmethod
    def message_of(payload):
        if not isinstance(payload, dict):
            return ""
        return str(payload.get("message")
                   or (payload.get("error") or {}).get("message") or "")

    def assert_no_password_leak(self, raw):
        self.assertNotIn(
            PASSWORD, raw, "Das Kennwort erscheint in der API-Antwort")
        log = self.log_dir / "proj.log"
        if log.exists():
            self.assertNotIn(
                PASSWORD, log.read_text(encoding="utf-8"),
                "Das Kennwort steht im Laufprotokoll")
        if self.web_log_path.exists():
            self.assertNotIn(
                PASSWORD, self.web_log_path.read_text(
                    encoding="utf-8", errors="replace"),
                "Das Kennwort steht im Dashboard-Protokoll")


class PrivateDeliveryTest(B13SteerFixture):
    """AK3: Zustellung an den privaten Server des aktiven Laufs."""

    def test_steer_delivers_to_the_private_server_of_the_active_run(self):
        """AK3: Anweisung erreicht den privaten Server statt Connection refused.

        Vorbedingung: aktiver Lauf, Hauptsession ses_main erfasst, gültige
        Kennwortdatei, gültige Serverdatei auf den lokalen privaten
        Testserver; gemeinsamer Port ist abgewiesen.
        Aktion: POST /api/steer.
        Erwartung: ok:true mit Übermittelt-Meldung; genau eine Zustellung an
        ``/api/session/ses_main/prompt`` mit korrekter Basic-Auth („opencode:
        Kennwort aus der Datei“) und dem Anweisungstext; Kennwort in keiner
        Antwort und keinem Protokoll.
        Fehlerfall: „Connection refused“, Zustellung am gemeinsamen Server
        oder falsche Anmeldung.
        """
        self.start_private_server()
        self.write_password()
        self.register_run("running")
        now = int(time.time())
        self.write_state({
            "session": MAIN_SESSION_b13,
            "subagents": [self.running_entry(CHILD_SESSION, "tester",
                                             now + 10)],
        })
        self.write_server_file()

        status, data, raw = self.post_steer()

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data),
                        f"Zustellung am privaten Server schlug fehl: {raw}")
        self.assertTrue(self.message_of(data).strip(), raw)
        posts = self.deliveries()
        self.assertEqual(1, len(posts), f"Genau eine Zustellung: {posts}")
        self.assertEqual(f"/api/session/{MAIN_SESSION_b13}/prompt",
                         posts[0]["path"], posts)
        self.assertTrue(posts[0]["auth_ok"], posts)
        self.assertIn(STEER_TEXT, posts[0]["body"], posts)
        self.assert_no_password_leak(raw)

    def test_steer_targets_a_running_subagent_via_the_private_server(self):
        """AK3: Zielgenaue Zustellung an einen laufenden Subagenten.

        Vorbedingung: wie Haupttest; laufender Subagent ses_child.
        Aktion: POST /api/steer mit session=ses_child.
        Erwartung: ok:true; Zustellung an ``/api/session/ses_child/prompt``.
        Fehlerfall: Falsches Ziel oder Zustellung an die Hauptsession.
        """
        self.start_private_server()
        self.write_password()
        self.register_run("running")
        now = int(time.time())
        self.write_state({
            "session": MAIN_SESSION_b13,
            "subagents": [self.running_entry(CHILD_SESSION, "tester",
                                             now + 10)],
        })
        self.write_server_file()

        status, data, raw = self.post_steer(session=CHILD_SESSION)

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data), raw)
        posts = self.deliveries()
        self.assertEqual(1, len(posts), posts)
        self.assertEqual(f"/api/session/{CHILD_SESSION}/prompt",
                         posts[0]["path"], posts)
        self.assertTrue(posts[0]["auth_ok"], posts)

    def test_steer_accepts_a_localhost_server_url(self):
        """AK3: Auch localhost ist als Loopback-URL zulässig.

        Vorbedingung: Serverdatei mit URL ``http://localhost:<Port>``.
        Aktion: POST /api/steer.
        Erwartung: ok:true mit Zustellung am Port der URL.
        Fehlerfall: Die localhost-URL wird abgelehnt.
        """
        self.start_private_server()
        self.write_password()
        self.register_run("running")
        self.write_state({"session": MAIN_SESSION_b13, "subagents": []})
        self.write_server_file(url="http://localhost:%d" % self.priv_port)

        status, data, raw = self.post_steer()

        self.assertEqual(200, status, raw)
        self.assertTrue(self.ok_flag(data),
                        f"localhost-URL wurde nicht akzeptiert: {raw}")
        self.assertEqual(1, len(self.deliveries()), self.private_requests())


class PreviousPathTest(B13SteerFixture):
    """AK4/AK8: Rückfall auf den bisherigen Pfad bzw. verständliche Ablehnung."""

    def test_steer_without_a_server_file_keeps_the_previous_path(self):
        """AK4: Ohne Serverdatei bleibt der bisherige Weg unverändert.

        Vorbedingung: aktiver Lauf, Kennwortdatei gesetzt, keine
        Serverdatei; gemeinsamer Port abgewiesen.
        Aktion: POST /api/steer.
        Erwartung: ok:false mit nichtleerer Meldung; keine Zustellung am
        privaten Testserver.
        Fehlerfall: Zustellung trotz fehlender Serverdatei.
        """
        self.write_password()
        self.register_run("running")
        self.write_state({"session": MAIN_SESSION_b13, "subagents": []})

        status, data, raw = self.post_steer()

        self.assertIn(status, (200, 400), raw)
        self.assertFalse(self.ok_flag(data), raw)
        self.assertTrue(self.message_of(data).strip(), raw)
        self.assertEqual([], self.deliveries(), self.private_requests())

    def test_steer_without_password_file_rejects_understandably(self):
        """AK4: Fehlende/leere Kennwortdatei → verständliche Meldung.

        Vorbedingung: aktive Lauf mit erfasster Session, aber ohne
        Kennwortdatei (und zweiteilige Variante: leere Datei); keine
        Serverdatei.
        Aktion: POST /api/steer.
        Erwartung: ok:false; die Meldung nennt das fehlende Kennwort und ist
        nicht die rohe Verbindungsfehlermeldung; keine Zustellung.
        Fehlerfall: „Connection refused“ statt verständlicher Ablehnung.
        """
        for variant in ("fehlt", "leer"):
            with self.subTest(variant=variant):
                self.setUp()
                if variant == "leer":
                    self.password_file().write_text(
                        "   \n", encoding="utf-8")
                self.register_run("running")
                self.write_state({"session": MAIN_SESSION_b13, "subagents": []})

                status, data, raw = self.post_steer()

                self.assertIn(status, (200, 400), raw)
                self.assertFalse(self.ok_flag(data), raw)
                message = self.message_of(data)
                self.assertIn(
                    "Kennwort", message,
                    f"Verständliche Ablehnung nennt das Kennwort: {message}")
                self.assertNotIn(
                    "Connection refused", message,
                    f"Rohe Fehlermeldung erreicht den Nutzer: {message}")
                self.assertEqual([], self.deliveries(),
                                 self.private_requests())

    def test_steer_ignores_a_broken_server_file(self):
        """AK8: Defektes JSON wird nicht angenommen.

        Vorbedingung: ``proj.log.server.json`` enthält kein gültiges JSON;
        privater Testserver läuft.
        Aktion: POST /api/steer.
        Erwartung: ok:false mit nichtleerer Meldung; keine Zustellung am
        privaten Server.
        Fehlerfall: Die defekte Datei wird trotzdem verwendet.
        """
        self.start_private_server()
        self.write_password()
        self.register_run("running")
        self.write_state({"session": MAIN_SESSION_b13, "subagents": []})
        self.write_server_file(raw="{kein json")

        status, data, raw = self.post_steer()

        self.assertIn(status, (200, 400), raw)
        self.assertFalse(self.ok_flag(data), raw)
        self.assertTrue(self.message_of(data).strip(), raw)
        self.assertEqual([], self.deliveries(), self.private_requests())

    def test_steer_ignores_a_server_file_without_usable_url(self):
        """AK8: Datei ohne gültigen Port wird nicht angenommen.

        Vorbedingung: Serverdatei nur mit ``password_file``, ohne URL/Port;
        privater Testserver läuft.
        Aktion: POST /api/steer.
        Erwartung: ok:false mit nichtleerer Meldung; keine Zustellung.
        Fehlerfall: Der fehlende Port wird still ergänzt oder es wird
        trotzdem gesendet.
        """
        self.start_private_server()
        self.write_password()
        self.register_run("running")
        self.write_state({"session": MAIN_SESSION_b13, "subagents": []})
        self.write_server_file(raw=json.dumps(
            {"password_file": str(self.password_file())}))

        status, data, raw = self.post_steer()

        self.assertIn(status, (200, 400), raw)
        self.assertFalse(self.ok_flag(data), raw)
        self.assertTrue(self.message_of(data).strip(), raw)
        self.assertEqual([], self.deliveries(), self.private_requests())

    def test_steer_ignores_a_non_loopback_server_url(self):
        """AK8: Fremde Hosts werden nicht angenommen.

        Vorbedingung: Serverdatei mit URL ``http://example.invalid:<Port>``;
        zusätzlich lauscht lokal ein Server am selben Port auf 127.0.0.1, um zu
        belegen, dass nichts „in der Nähe“ zugestellt wird; privater
        Testserver läuft.
        Aktion: POST /api/steer.
        Erwartung: ok:false mit nichtleerer Meldung; keine Zustellung am
        lokalen Auffang-Servers am selben Port und keine am privaten
        Testserver.
        Fehlerfall: Die fremde URL wird akzeptiert oder der Host still
        durch Loopback ersetzt.
        """
        self.start_private_server()
        self.write_password()
        self.register_run("running")
        self.write_state({"session": MAIN_SESSION_b13, "subagents": []})

        class CatchHandler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                self.send_response(200)
                self.end_headers()

        catch_port = self.free_port()
        catcher = ThreadingHTTPServer(("127.0.0.1", catch_port), CatchHandler)
        catcher.daemon_threads = True
        catcher.requests = []
        thread = threading.Thread(target=catcher.serve_forever)
        thread.daemon = True
        thread.start()
        try:
            self.write_server_file(url="http://example.invalid:%d" % catch_port,
                                   port=catch_port)

            status, data, raw = self.post_steer()
        finally:
            catcher.shutdown()
            catcher.server_close()
            thread.join(timeout=5)

        self.assertIn(status, (200, 400), raw)
        self.assertFalse(self.ok_flag(data), raw)
        self.assertTrue(self.message_of(data).strip(), raw)
        self.assertEqual([], self.deliveries(), self.private_requests())


class PiSteerKeptTest(B13SteerFixture):
    """AK7: Pi-Ablehnung bleibt auch mit Serverdatei bestehen."""

    def test_pi_steer_stays_forbidden_even_with_a_server_file(self):
        """AK7: Pi wird auch mit privatem Server nicht gesteuert.

        Vorbedingung: harness.json wählt pi; aktiver Lauf; gültige
        Serverdatei und Kennwortdatei; privater Testserver läuft.
        Aktion: POST /api/steer.
        Erwartung: ok:false mit der bekannten Meldung „Zusatzanweisungen
        sind bei Pi nicht möglich“; keine Zustellung.
        Fehlerfall: Die Serverdatei umgeht die Pi-Ablehnung.
        """
        self.start_private_server()
        self.write_password()
        (self.state_dir / "harness.json").write_text(
            json.dumps({"harness": "pi"}, ensure_ascii=False) + "\n",
            encoding="utf-8")
        self.register_run("running")
        self.write_state({"session": MAIN_SESSION_b13, "subagents": []})
        self.write_server_file()

        status, data, raw = self.post_steer()

        self.assertIn(status, (200, 400), raw)
        self.assertFalse(self.ok_flag(data), raw)
        message = self.message_of(data)
        self.assertIn("Zusatzanweisungen sind bei Pi nicht möglich",
                      message, f"Bekannter Hinweistext fehlt: {message}")
        self.assertEqual([], self.deliveries(), self.private_requests())


# ===========================================================================
# Unit-Abnahme: geerbtes OPENCODE_PASSWORD erreicht den Server nicht
# ===========================================================================

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

CLI = REPO / "bin" / "vibe"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support  # noqa: E402

# Kennwort aus der Laufzeitdatei (B13-Verhalten): Length 15.
FILE_PASSWORD = PASSWORD
# Veraltete geerbte Belegung aus der Startumgebung: andere Länge (18), damit
# ein vererbter Wert anhand der Länge vom Datei-Kennwort unterscheidbar ist.
STALE_PASSWORD = "veraltet-16zeichen"
# Kennwort für den gemeinsamen Server (AK3), deutlich länger als der
# geerbte Wert.
SHARED_PASSWORD = "gemeinsam-32-zeichen-kennwort-f31"


class PrivateServerIgnoresInheritedPasswordTest(B13RunnerFixture):
    """AK1/AK2: Der private Server erbt kein OPENCODE_PASSWORD."""

    def listening_entry(self):
        entries = self.listening_events()
        self.assertTrue(
            entries, "Der private Server lauschte nie: "
            + repr(self.serve_records()))
        return entries[0]

    def assert_health_checked_with_file_password(self):
        """Die Gesundheitsprüfung kam mit gültiger Anmeldung an."""
        health = [entry for entry in self.serve_records()
                  if entry.get("method") == "GET"
                  and "/api/info" in entry.get("path", "")]
        self.assertTrue(
            health, "Der Server wurde nie auf Gesundheit geprüft")
        self.assertTrue(
            any(entry.get("auth_ok") for entry in health),
            "Die Gesundheitsprüfung scheiterte: "
            + repr(health))

    def assert_no_password_leak(self):
        """AK4: Kein Kennwortwert im Klartext in den Testartefakten."""
        record = (self.serve_record.read_text(encoding="utf-8")
                  if self.serve_record.exists() else "")
        args = (self.args_file.read_bytes().decode("utf-8", "surrogateescape")
                if self.args_file.exists() else "")
        log = self.log_text()
        for label, text in (
            ("Serve-Record", record),
            ("opencode-Argumenten", args),
            ("Laufprotokoll", log),
        ):
            for name, value in (
                ("Datei-Kennwort", FILE_PASSWORD),
                ("geerbtes Kennwort", STALE_PASSWORD),
            ):
                self.assertNotIn(
                    value, text,
                    f"Der {name} ist im {label} gelandet")

    def test_inherited_opencode_password_is_absent_from_the_server_env(self):
        """AK1: Geerbtes OPENCODE_PASSWORD erreicht den privaten Server nicht.

        Vorbedingung: Kennwortdatei ``$RUNTIME/opencode.password`` nichtleer;
        die Startumgebung des Läufers enthält eine veraltete
        ``OPENCODE_PASSWORD``-Belegung; Attrappen zeichnen opencode-Aufrufe
        und Serve-Beobachtungen auf.
        Aktion: ``vibe-run.sh <projekt>``.
        Erwartung: Der Lauf läuft durch (FERTIG); genau ein ``serve``-Aufruf;
        im ``listening``-Record der Attrappe ist ``OPENCODE_PASSWORD``
        abwesend (present False, Länge 0), während
        ``OPENCODE_SERVER_PASSWORD`` vorhanden ist und exakt die Länge des
        Datei-Kennworts hat; die Gesundheitsprüfung (GET /api/info) wird mit
        gültiger Basic-Auth aus der Kennwortdatei beantwortet; der
        Agentenaufruf nutzt ``--server http://127.0.0.1:<Port>`` ohne
        ``--standalone``; kein Kennwortwert steht im Klartext in einem
        Artefakt (AK4).
        Fehlerfall: Die Attrappe beobachtet eine ``OPENCODE_PASSWORD``-
        Belegung in ihrer eigenen Umgebung oder der Lauf scheitert an der
        Gesundheitsprüfung.
        """
        self.write_password()
        env = self.env()
        env.pop("OPENCODE_PASSWORD", None)
        env["OPENCODE_PASSWORD"] = STALE_PASSWORD

        result = self.run_runner(env=env)

        log = self.log_text()
        self.assertEqual(
            result.returncode, 0, "Läufer bricht ab:\n" + result.stdout
            + result.stderr + "\n" + log)
        self.assertIn("FERTIG", log)

        serve_calls = [record for record in self.arg_records()
                       if record and record[0] == "serve"]
        self.assertEqual(
            1, len(serve_calls),
            "Genau ein privater Server je Lauf erwartet: " + repr(serve_calls))

        entry = self.listening_entry()
        self.assertFalse(
            entry.get("opencode_password_present"),
            "Der private Server-Prozess erbte ein OPENCODE_PASSWORD: "
            + repr({key: entry[key] for key in entry
                    if "password" in key}))
        self.assertEqual(
            0, entry.get("opencode_password_len"),
            "Die Länge eines geerbten OPENCODE_PASSWORD wurde beobachtet")
        self.assertTrue(
            entry.get("server_password_present"),
            "OPENCODE_SERVER_PASSWORD fehlte im Serverprozess")
        self.assertEqual(
            len(FILE_PASSWORD), entry.get("server_password_len"),
            "OPENCODE_SERVER_PASSWORD stammt nicht aus der Kennwortdatei")

        self.assert_health_checked_with_file_password()

        run_calls = self.run_records()
        self.assertTrue(run_calls, "Agent wurde nicht gestartet")
        bound_port = entry["port_bound"]
        url = "http://127.0.0.1:" + str(bound_port)
        for record in run_calls:
            self.assertIn("--server", record, repr(record))
            self.assertIn(url, record, repr(record))
            self.assertNotIn("--standalone", record, repr(record))

        self.assert_no_password_leak()

    def test_without_inherited_password_b13_behaviour_is_unchanged(self):
        """AK2: Ohne geerbtes OPENCODE_PASSWORD bleibt B13 unverändert.

        Vorbedingung: Kennwortdatei nichtleer; die Startumgebung enthält
        kein ``OPENCODE_PASSWORD``.
        Aktion: ``vibe-run.sh <projekt>``.
        Erwartung: wie B13: Lauf läuft durch (FERTIG), genau ein
        ``serve``-Aufruf, ``OPENCODE_PASSWORD`` abwesend im Serverprozess,
        ``OPENCODE_SERVER_PASSWORD`` mit Datei-Kennwort-Länge, Gesundheits-
        prüfung gültig, Agent mit ``--server`` ohne ``--standalone``.
        Fehlerfall: Abweichendes B13-Verhalten (Regression).
        """
        self.write_password()
        env = self.env()
        env.pop("OPENCODE_PASSWORD", None)

        result = self.run_runner(env=env)

        log = self.log_text()
        self.assertEqual(
            result.returncode, 0, "Läufer bricht ab:\n" + result.stdout
            + result.stderr + "\n" + log)
        self.assertIn("FERTIG", log)

        serve_calls = [record for record in self.arg_records()
                       if record and record[0] == "serve"]
        self.assertEqual(
            1, len(serve_calls),
            "Genau ein privater Server je Lauf erwartet: " + repr(serve_calls))

        entry = self.listening_entry()
        self.assertFalse(
            entry.get("opencode_password_present"),
            "Ohne Belegung in der Startumgebung tauchte OPENCODE_PASSWORD "
            "im Serverprozess auf")
        self.assertTrue(
            entry.get("server_password_present"),
            "OPENCODE_SERVER_PASSWORD fehlte im Serverprozess")
        self.assertEqual(
            len(FILE_PASSWORD), entry.get("server_password_len"),
            "OPENCODE_SERVER_PASSWORD stammt nicht aus der Kennwortdatei")

        self.assert_health_checked_with_file_password()

        run_calls = self.run_records()
        self.assertTrue(run_calls, "Agent wurde nicht gestartet")
        url = "http://127.0.0.1:" + str(entry["port_bound"])
        for record in run_calls:
            self.assertIn("--server", record, repr(record))
            self.assertIn(url, record, repr(record))
            self.assertNotIn("--standalone", record, repr(record))

        self.assert_no_password_leak()

    def define_project_env_password(self):
        """AK1b: Belegt OPENCODE_PASSWORD in der .vibe/project.env.

        Der Wert steht genau einmal in der Datei, in doppelten
        Anführungszeichen — so exportiert ``set -a; . file; set +a`` ihn,
        wie der Läufer die Projektdatei einliest. Der Baum wird neu
        committet, damit der Läufer an einem sauberen Stand startet.
        """
        env_file = self.project / ".vibe" / "project.env"
        self.assertTrue(env_file.exists())
        text = env_file.read_text(encoding="utf-8")
        line = 'OPENCODE_PASSWORD="' + STALE_PASSWORD + '"\n'
        self.assertNotIn("OPENCODE_PASSWORD=", text)
        env_file.write_text(text + line, encoding="utf-8")
        self.assertEqual(
            1, env_file.read_text(encoding="utf-8").count(line.strip()),
            "OPENCODE_PASSWORD muss genau einmal in der Projektdatei stehen")
        # GH-48: .vibe/ ist Laufzeitstand und wird nicht versioniert; der
        # Läufer liest die Datei direkt. Ein Commit ist weder nötig noch
        # möglich.

    def test_project_env_opencode_password_is_absent_from_the_server_env(self):
        """AK1b: OPENCODE_PASSWORD aus .vibe/project.env erreicht den Server nicht.

        Vorbedingung: Kennwortdatei ``$RUNTIME/opencode.password`` nichtleer;
        die übergeordnete Prozessumgebung enthält KEIN ``OPENCODE_PASSWORD``;
        die ``.vibe/project.env`` des Testprojekts definiert
        ``OPENCODE_PASSWORD="<veralteter Attrappenwert>"`` (genau eine Zeile);
        Attrappen zeichnen opencode-Aufrufe und Serve-Beobachtungen auf.
        Aktion: ``vibe-run.sh <projekt>``.
        Erwartung: Der Lauf läuft durch (FERTIG); genau ein ``serve``-Aufruf;
        im ``listening``-Record der Attrappe ist ``OPENCODE_PASSWORD``
        abwesend (present False, Länge 0), während
        ``OPENCODE_SERVER_PASSWORD`` vorhanden ist und exakt die Länge des
        Datei-Kennworts hat; die Gesundheitsprüfung (GET /api/info) wird mit
        gültiger Basic-Auth aus der Kennwortdatei beantwortet; der
        Agentenaufruf nutzt ``--server http://127.0.0.1:<Port>`` ohne
        ``--standalone``; kein Kennwortwert steht im Klartext in einem
        Artefakt (AK4).
        Fehlerfall: Das späte Einlesen der Projektdatei exportiert den
        ``OPENCODE_PASSWORD``-Wert erneut und die Attrappe beobachtet eine
        Belegung in ihrer eigenen Umgebung, oder der Lauf scheitert an der
        Gesundheitsprüfung (401), weil der falsche Wert das Datei-Kennwort
        schlägt.
        """
        self.write_password()
        self.define_project_env_password()
        env = self.env()
        env.pop("OPENCODE_PASSWORD", None)

        result = self.run_runner(env=env)

        log = self.log_text()
        self.assertEqual(
            result.returncode, 0, "Läufer bricht ab:\n" + result.stdout
            + result.stderr + "\n" + log)
        self.assertIn("FERTIG", log)

        serve_calls = [record for record in self.arg_records()
                       if record and record[0] == "serve"]
        self.assertEqual(
            1, len(serve_calls),
            "Genau ein privater Server je Lauf erwartet: " + repr(serve_calls))

        entry = self.listening_entry()
        self.assertFalse(
            entry.get("opencode_password_present"),
            "Der private Server-Prozess erhielt ein OPENCODE_PASSWORD aus "
            "der Projektdatei: "
            + repr({key: entry[key] for key in entry
                    if "password" in key}))
        self.assertEqual(
            0, entry.get("opencode_password_len"),
            "Die Länge eines aus der Projektdatei exportierten "
            "OPENCODE_PASSWORD wurde beobachtet")
        self.assertTrue(
            entry.get("server_password_present"),
            "OPENCODE_SERVER_PASSWORD fehlte im Serverprozess")
        self.assertEqual(
            len(FILE_PASSWORD), entry.get("server_password_len"),
            "OPENCODE_SERVER_PASSWORD stammt nicht aus der Kennwortdatei")

        self.assert_health_checked_with_file_password()

        run_calls = self.run_records()
        self.assertTrue(run_calls, "Agent wurde nicht gestartet")
        bound_port = entry["port_bound"]
        url = "http://127.0.0.1:" + str(bound_port)
        for record in run_calls:
            self.assertIn("--server", record, repr(record))
            self.assertIn(url, record, repr(record))
            self.assertNotIn("--standalone", record, repr(record))

        self.assert_no_password_leak()


# Attrappe des opencode-CLI für ``vibe server start`` (AK3): ``--version``
# antwortet wie die geprüfte Version; ``serve`` schreibt nur Anwesenheit und
# Länge der Kennwortvariablen in den Record (AK4: nie der Wert) und endet —
# die tmux-Sitzung beendet sich damit selbst.
FAKE_VIBE_OPENCODE = r"""#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
if args and args[0] == "--version":
    print("opencode v2.1.4")
    sys.exit(0)
if args and args[0] == "serve":
    record = os.environ.get("FAKE_SERVE_RECORD", "")

    def password_shape(name):
        value = os.environ.get(name)
        return bool(value), (len(value) if value is not None else 0)

    op_present, op_len = password_shape("OPENCODE_PASSWORD")
    server_present, server_len = password_shape("OPENCODE_SERVER_PASSWORD")
    if record:
        with open(record, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "event": "listening",
                "opencode_password_present": op_present,
                "opencode_password_len": op_len,
                "server_password_present": server_present,
                "server_password_len": server_len,
            }, ensure_ascii=False) + "\n")
    sys.exit(0)
sys.stderr.write("unerwarteter Aufruf: %s\n" % " ".join(args))
sys.exit(2)
"""

FAKE_CURL_DEAD = """#!/usr/bin/env bash
exit 7
"""


class SharedServerIgnoresInheritedPasswordTest(unittest.TestCase):
    """AK3: ``vibe server start`` vererbt kein OPENCODE_PASSWORD.

    Echter tmux auf isoliertem Socket (TMUX_TMPDIR); die Attrappe des
    opencode-CLI zeichnet die eigene Umgebung auf. Der gemeinsame Server
    „startet“ mit einer Attrappe, die sich sofort beendet — die
    Gesundheitsprüfung bleibt unbeantwortet, der Startbefehl meldet das als
    „angestoßen“ und endet erfolgreich.
    """

    def setUp(self):
        if shutil.which("tmux") is None:
            raise unittest.SkipTest("tmux ist nicht verfügbar")
        self.tmp = tempfile.TemporaryDirectory(prefix="f31-server-",
                                               dir="/tmp/opencode")
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.home = self.root / "home"
        self.home.mkdir()
        self.fakebin = self.root / "fakebin"
        self.fakebin.mkdir()
        # bash -lc der tmux-Kette liest ~/.bashrc; dort bleibt der PATH der
        # Attrappen erhalten, unabhängig von /etc/profile.
        (self.home / ".bashrc").write_text(
            "export PATH=" + str(self.fakebin) + ":$PATH\n", encoding="utf-8")
        self.runtime = self.root / "_logs"
        self.runtime.mkdir()
        opencode = self.fakebin / "opencode"
        opencode.write_text(FAKE_VIBE_OPENCODE, encoding="utf-8")
        opencode.chmod(0o755)
        curl = self.fakebin / "curl"
        curl.write_text(FAKE_CURL_DEAD, encoding="utf-8")
        curl.chmod(0o755)
        self.tmux_dir = self.root / "tmux"
        self.tmux_dir.mkdir()
        # tmux akzeptiert TMUX_TMPDIR nur ohne fremde Schreibrechte.
        self.tmux_dir.chmod(0o700)
        self.record = self.root / "serve.record.jsonl"
        (self.runtime / "opencode.password").write_text(
            SHARED_PASSWORD + "\n", encoding="utf-8")
        self.env = os.environ.copy()
        for key in ("TMUX", "TMUX_PANE"):
            self.env.pop(key, None)
        self.env.update({
            "HOME": str(self.home),
            "VIBE": str(self.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_RUNTIME": str(self.runtime),
            "VIBE_INSTALL": str(self.root / "_toolchain"),
            "VIBE_OPENCODE_PORT": str(free_port()),
            "PATH": str(self.fakebin) + os.pathsep + self.env.get("PATH", ""),
            "TMUX_TMPDIR": str(self.tmux_dir),
            "TERM": self.env.get("TERM", "xterm"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "OPENCODE_PASSWORD": STALE_PASSWORD,
            "FAKE_SERVE_RECORD": str(self.record),
        })

    def tearDown(self):
        # Nur der isolierte tmux-Server dieser Umgebung; die Attrappe endet
        # von selbst, es bleibt kein Serverprozess zurück.
        subprocess.run(
            ["tmux", "kill-server"], env=self.env,
            capture_output=True, text=True, timeout=30)

    def test_server_start_does_not_inherit_opencode_password(self):
        """AK3: Die tmux-Sitzung des gemeinsamen Servers erbt nichts.

        Vorbedingung: Kennwortdatei in der Laufzeit nichtleer; die
        Startumgebung von ``vibe server start`` enthält eine veraltete
        ``OPENCODE_PASSWORD``-Belegung; echte tmux-Sitzung auf isoliertem
        Socket; die opencode-Attrappe zeichnet ihre Umgebung auf.
        Aktion: ``vibe server start``.
        Erwartung: Der Befehl endet erfolgreich; die tmux-Kette startete
        ``opencode serve`` (genau ein Record), dessen Umgebung kein
        ``OPENCODE_PASSWORD`` enthält (present False, Länge 0) und dessen
        ``OPENCODE_SERVER_PASSWORD`` die Kennwortdatei-Länge hat, nicht die
        Länge des geerbten Werts; kein Kennwortwert steht im Klartext in
        Record oder Ausgabe (AK4).
        Fehlerfall: Die Attrappe beobachtet eine ``OPENCODE_PASSWORD``-
        Belegung in ihrer Umgebung.
        """
        result = subprocess.run(
            [sys.executable, str(CLI), "server", "start"],
            env=self.env, cwd=str(self.root),
            capture_output=True, text=True, timeout=120)

        self.assertEqual(
            result.returncode, 0, "vibe server start bricht ab:\n"
            + result.stdout + result.stderr)
        deadline = time.time() + 5
        while not self.record.exists() and time.time() < deadline:
            time.sleep(0.1)
        entries = read_jsonl(self.record)
        self.assertEqual(
            1, len(entries),
            "Genau ein opencode-serve-Aufruf erwartet: " + repr(entries))
        entry = entries[0]
        self.assertFalse(
            entry.get("opencode_password_present"),
            "Der Serverprozess der tmux-Sitzung erbte ein "
            "OPENCODE_PASSWORD: " + repr({key: entry[key] for key in entry
                                          if "password" in key}))
        self.assertEqual(
            0, entry.get("opencode_password_len"),
            "Die Länge eines geerbten OPENCODE_PASSWORD wurde beobachtet")
        self.assertTrue(
            entry.get("server_password_present"),
            "OPENCODE_SERVER_PASSWORD fehlte im Serverprozess")
        self.assertEqual(
            len(SHARED_PASSWORD), entry.get("server_password_len"),
            "OPENCODE_SERVER_PASSWORD stammt nicht aus der Kennwortdatei")
        self.assertNotEqual(
            len(STALE_PASSWORD), entry.get("server_password_len"),
            "OPENCODE_SERVER_PASSWORD stimmt mit dem geerbten Wert überein")

        raw = self.record.read_text(encoding="utf-8")
        out = result.stdout + result.stderr
        for name, value in (
            ("Datei-Kennwort", SHARED_PASSWORD),
            ("geerbtes Kennwort", STALE_PASSWORD),
        ):
            self.assertNotIn(
                value, raw,
                f"Der {name} ist im Serve-Record gelandet")
            self.assertNotIn(
                value, out,
                f"Der {name} ist in der Befehlsausgabe gelandet")


# ===========================================================================
# Unit-Abnahme: Automatische Anlagen der opencode-Kennwortdatei beim
# ===========================================================================

import base64
import http.client
import contextlib
import importlib.machinery
import importlib.util
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

BIN = REPO / "bin"
CLI_b3 = BIN / "vibe"
WEB_b3 = BIN / "vibe-web.py"
RUNS_PY_b3 = BIN / "vibe_runs.py"

PASSWORD_NAME = "opencode.password"
BESTAND_PASSWORD = "bestands-kennwort-fuer-b3-unveraendert"
STEER_TEXT_b3 = "Prüfe zuerst die Borderstellung"

MAIN_SESSION_b3 = "ses_b3_main"

VIBE_AGENT = """---
description: Vibe-Standardagent für den Testlauf
mode: primary
model: opencode/vibe-test-modell
permission:
  read: allow
  edit: deny
---

Du unterstützt den Testlauf.
"""

# Die Prüfumgebung darf produktive VIBE-/HOME-Konfigurationen nicht berühren.
ISOLATED_ENV = (
    "VIBE",
    "VIBE_NO_CONTAINER",
    "HOME",
    "VIBE_STORAGE_LOCK_DIR",
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
    "AGENT",
    "SANDBOX",
    # Wird im Prozess gesetzt und muss vollständig restoriert werden, damit
    # nachfolgende Tests (z. B. tempfile.gettempdir()-Fundorte) unverändert
    # anlaufen.
    "TMPDIR",
    "TMUX_TMPDIR",
)


def isolated_env(root, home, ui_port=None, opencode_port=None):
    """Umgebung, die ausschließlich im Prüfverzeichnis arbeitet."""
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
            "TMUX", "TMUX_PANE",
        ):
            env.pop(key, None)
    root, home = Path(root), Path(home)
    env.update(
        {
            "VIBE": str(root),
            "VIBE_NO_CONTAINER": "1",
            "HOME": str(home),
            "VIBE_INSTALL": str(root / "_toolchain"),
            "VIBE_RUNTIME": str(root / "_logs"),
            "VIBE_STATE": str(root / "_toolchain"),
            "VIBE_AGENTS_DIR": str(home / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(home / ".config" / "vibe" / "config.json"),
            "VIBE_STORAGE_LOCK_DIR": str(root / "locks"),
        }
    )
    if ui_port is not None:
        env["VIBE_UI_PORT"] = str(ui_port)
    if opencode_port is not None:
        env["VIBE_OPENCODE_PORT"] = str(opencode_port)
    return env


def load_cli(name="vibe_b3_under_test"):
    """Lädt bin/vibe mit der aktuellen Umgebungsvariablen des Aufrufers."""
    loader = importlib.machinery.SourceFileLoader(name, str(CLI_b3))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def modes_supported(directory):
    """0o600-Rechte der Prüfumgebung (FUSE/NTFS-Toleranz)."""
    probe = Path(directory) / ".perm-probe"
    try:
        probe.write_text("x", encoding="utf-8")
        probe.chmod(0o600)
        supported = stat.S_IMODE(probe.stat().st_mode) & 0o077 == 0
    except OSError:
        supported = False
    finally:
        try:
            probe.unlink()
        except OSError:
            pass
    return supported


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """Server-Ersatz mit demselben Vertrag wie in
    tests/unit/test_output_view_f19_api.py: POST nimmt eine Zusatzanweisung
    nur mit gültigem Basic-Auth (Benutzer „opencode" und Kennwort aus der
    Datei ``credential_path``) an. Jede Anfrage wird nach ``record_path``
    protokolliert, damit der Test die tatsächliche Zustellung nachweisen kann."""

    context = None

    def log_message(self, *args):
        return

    def _signature(self):
        try:
            password = Path(self.context["credential_path"]).read_text(
                encoding="utf-8"
            ).strip()
        except OSError:
            return None
        encoded = base64.b64encode(("opencode:" + password).encode()).decode()
        return "Basic " + encoded

    def do_GET(self):
        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        signature = self._signature()
        header = self.headers.get("Authorization", "")
        auth_ok = signature is not None and header == signature
        user = ""
        if header.startswith("Basic "):
            try:
                decoded = base64.b64decode(header[6:]).decode("utf-8")
                user = decoded.split(":", 1)[0]
            except Exception:
                user = ""
        with open(self.context["record_path"], "a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "path": self.path,
                        "auth_ok": auth_ok,
                        "user": user,
                        "body": body,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        status = 200 if auth_ok else 401
        payload = json.dumps({"ok": auth_ok}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class B3RunFixture(unittest.TestCase):
    """Temporäre VIBE-/HOME-Umgebung mit Projekt und Vibe-Agenten.

    ``cmd_run`` startet ohne tmux: Die tmux-Sitzung, das Laufregister und das
    Setup der Regeln/des Test-Agenten liegen als Attrappen. Dateisystemseitig
    läuft alles echt — genau einschließlich der Kennwortdatei."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        agents = self.home / ".config" / "opencode" / "agents"
        agents.mkdir(parents=True)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (self.root / "_logs").mkdir(exist_ok=True)
        self.saved_env = {key: os.environ.get(key) for key in ISOLATED_ENV}
        for key in ISOLATED_ENV:
            os.environ.pop(key, None)
        os.environ.update(isolated_env(self.root, self.home))
        try:
            self.cli = load_cli()
        finally:
            for key, value in self.saved_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        models = mock.patch.object(self.cli, "models_list", return_value=[])
        models.start()
        self.addCleanup(models.stop)

    def write_vibe(self, name="vibe-agent"):
        path = self.home / ".config" / "opencode" / "agents" / (name + ".md")
        path.write_text(VIBE_AGENT, encoding="utf-8")
        data = self.cli.profiles_load()
        data.setdefault("rollen", {})[name] = "vibe"
        self.cli.profiles_save(data)
        return path

    def start_run(self, name="proj", agent=None):
        """Startet cmd_run mit allen externen Grenzen als Attrappen."""
        calls = []
        self.run_mock = mock.Mock(
            side_effect=lambda argv, **kwargs: calls.append(argv) or (0, "")
        )
        registry = mock.MagicMock()
        with mock.patch.object(self.cli, "tmux_has", return_value=False):
            with mock.patch.object(self.cli, "is_init", return_value=True):
                with mock.patch.object(
                    self.cli, "sandbox_status", return_value={"enabled": False}
                ):
                    with contextlib.nullcontext():
                        with mock.patch.object(
                            self.cli, "run_registry", return_value=registry
                        ):
                            with mock.patch.object(
                                self.cli.vibe_runs, "rotate_log"
                            ):
                                with mock.patch.object(
                                    self.cli, "run", self.run_mock
                                ):
                                    self.cli.cmd_run(name, agent)
        return calls

    @property
    def password_path(self):
        return self.root / "_logs" / PASSWORD_NAME


class AutoSetupOnRunStartTest(B3RunFixture):
    """AK1/AK2: Anlage der Kennwortdatei beim Laufstart; Bestand bleibt."""

    def test_run_start_creates_missing_password_file_in_runtime(self):
        # AK1: Vorbedingung — die Kennwortdatei fehlt.
        self.assertFalse(self.password_path.exists())
        self.write_vibe()

        calls = self.start_run()

        # Der Laufstart ist tatsächlich durchgelaufen (tmux-Aufruf bereit).
        self.assertTrue(self.run_mock.called, "cmd_run hat den Laufstart nicht erreicht")
        self.assertTrue(
            self.password_path.exists(),
            "AK1 verletzt: Kennwortdatei wurde beim Laufstart nicht automatisch angelegt",
        )
        value = self.password_path.read_text(encoding="utf-8").strip()
        self.assertTrue(value, "Angelegte Kennwortdatei ist leer")
        # Laufzeitdatei (VIBE_RUNTIME/_logs), nicht das Repository oder VIBE selbst.
        self.assertEqual(self.password_path, self.root / "_logs" / PASSWORD_NAME)
        self.assertEqual(str(self.cli.LOGS), str(self.root / "_logs"))
        # 0600, soweit das Dateisystem Unix-Rechte trägt (FUSE/NTFS-Toleranz).
        if modes_supported(self.root / "_logs"):
            self.assertEqual(
                stat.S_IMODE(self.password_path.stat().st_mode) & 0o077,
                0,
                "Kennwortdatei ist für Gruppe/Others lesbar",
            )

    def test_existing_password_file_survives_run_start(self):
        # AK2: Vorbedingung — nichtleere bestehende Datei.
        self.write_vibe()
        self.password_path.write_text(BESTAND_PASSWORD + "\n", encoding="utf-8")
        before = self.password_path.read_text(encoding="utf-8")

        self.start_run()

        self.assertTrue(self.run_mock.called, "cmd_run hat den Laufstart nicht erreicht")
        after = self.password_path.read_text(encoding="utf-8")
        self.assertEqual(
            before,
            after,
            "AK2 verletzt: bestehendes Kennwort wurde beim Laufstart neu gerollt",
        )


class SteerAfterAutoSetupTest(B3RunFixture):
    """AK3: Nach automatischer Anlage akzeptiert POST /api/steer die
    Zustellung mit dem automatisch angelegten Kennwort (Echt-HTTP gegen
    opencode-Server-Ersatz, Vertrag wie in test_output_view_f19_api.py)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        agents = cls.home / ".config" / "opencode" / "agents"
        agents.mkdir(parents=True)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        cls.ui_port = free_port()
        cls.oc_port = free_port()
        cls.context = {
            "credential_path": str(cls.root / "_logs" / PASSWORD_NAME),
            "record_path": str(cls.root / "_logs" / "fake-opencode.requests.jsonl"),
        }
        handler = type("BoundHandler", (BaseHTTPRequestHandler,), {})
        for attribute, value in _FakeOpenCodeHandler.__dict__.items():
            if not attribute.startswith("__"):
                setattr(handler, attribute, value)
        handler.context = cls.context
        cls._fake_http = ThreadingHTTPServer(("127.0.0.1", cls.oc_port), handler)
        cls._fake_http.daemon_threads = True
        cls._thread = threading.Thread(target=cls._fake_http.serve_forever)
        cls._thread.daemon = True
        cls._thread.start()

        cls.env = isolated_env(
            cls.root, cls.home,
            ui_port=cls.ui_port, opencode_port=cls.oc_port,
        )
        # Das Dashboard verhält sich im Subprozess wie in
        # tests/unit/test_output_view_f19_api.py (eigener Port, eigene Ports,
        # isoliertes HOME/TMP/Tmux-Sitzungsordner).
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir()
        cls.tmux_env = dict(cls.env)
        cls.tmux_env["TMUX_TMPDIR"] = str(cls.tmux_dir)
        cls.tmp_dir = cls.root / "tmp"
        cls.tmp_dir.mkdir()
        cls.env["TMPDIR"] = str(cls.tmp_dir)
        cls.env["TMUX_TMPDIR"] = str(cls.tmux_dir)
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB_b3)],
            env=cls.env,
            stdout=cls.server_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.root / "_logs" / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                        ("127.0.0.1", cls.ui_port), timeout=0.5
                    ):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: "
                    + cls.root.joinpath("web-server.log").read_text(
                        encoding="utf-8", errors="replace"
                    )
                )
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()

        # Sitzungsname des Laufprojekts mit derselben Projektlogik bestimmen,
        # die auch cmd_run benutzt.
        cls.saved_env = {key: os.environ.get(key) for key in ISOLATED_ENV}
        for key in ISOLATED_ENV:
            os.environ.pop(key, None)
        os.environ.update(cls.env)
        try:
            module = load_cli("vibe_b3_session_probe")
            cls.session = module.sess("proj")
        finally:
            for key, value in cls.saved_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

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
            cls._thread.join(timeout=5)
        except Exception:
            pass
        cls.tmp.cleanup()

    def setUp(self):
        # Bestehender Zustand aus früheren Aufrufen wird entfernt.
        state = self.root / "_logs" / "proj.log.state.json"
        if state.exists():
            state.unlink()
        requests = self.root / "_logs" / "fake-opencode.requests.jsonl"
        if requests.exists():
            requests.unlink()
        if self.password_path.exists():
            self.password_path.unlink()
        # Das CLI-Modul wird in derselben Umgebung wie das Dashboard geladen;
        # LAUFZEIT- und Sitzungslogik stimmen dadurch überein.
        self.saved_env = {key: os.environ.get(key) for key in ISOLATED_ENV}
        for key in ISOLATED_ENV:
            os.environ.pop(key, None)
        os.environ.update(self.env)
        try:
            self.cli = load_cli("vibe_b3_run_under_test")
        finally:
            for key, value in self.saved_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        models = mock.patch.object(self.cli, "models_list", return_value=[])
        models.start()
        self.addCleanup(models.stop)

    def post_steer(self, name="proj", text=STEER_TEXT_b3):
        """POST /api/steer mit gültigem Token und CSRF-Kontext (gleiches
        Muster wie in tests/unit/test_output_view_f19_api.py)."""
        headers = {"X-Token": self.token}
        if text is not None:
            encoded = json.dumps({"name": name, "text": text}, ensure_ascii=False).encode("utf-8")
        else:
            encoded = None
        headers.update(
            {
                "Host": f"127.0.0.1:{self.ui_port}",
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{self.ui_port}",
                "Sec-Fetch-Site": "same-origin",
            }
        )
        connection = http.client.HTTPConnection("127.0.0.1", self.ui_port, timeout=20)
        try:
            connection.request("POST", "/api/steer", body=encoded, headers=headers)
            response = connection.getresponse()
            raw = response.read().decode("utf-8", "replace")
            try:
                payload = json.loads(raw)
            except ValueError:
                payload = None
            return response.status, payload, raw
        finally:
            connection.close()

    def make_run_active(self):
        """Vorbedingung „aktiver Lauf": Registereintrag (state running) über
        die echte Laufregister-CLI — dieselben Bausteine eines echten Läufers."""
        subprocess.run(
            [
                sys.executable, str(RUNS_PY_b3), "start",
                "--runtime", str(self.root / "_logs"),
                "--project", str(self.project.resolve()),
                "--name", "proj", "--key", "proj", "--agent", "vibe-agent",
                "--session", self.session,
                "--state", "running",
            ],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Session-Erfassung wie in F19 (Eingabedatei der Läufer-Erfassung).
        (self.root / "_logs" / "proj.log.state.json").write_text(
            json.dumps({"session": self.session, "subagents": []}, ensure_ascii=False),
            encoding="utf-8",
        )

    def delivered_posts(self):
        path = self.context["record_path"]
        if not Path(path).exists():
            return []
        return [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_auto_created_password_authenticates_steer_delivery(self):
        # Vorbedingung: Kennwortdatei fehlt.
        self.assertFalse(self.password_path.exists())
        # Ohne aktiven Lauf gibt es die gewohnte Verweigerung.
        status, data, raw = self.post_steer()
        self.assertNotEqual(200, status)
        self.assertEqual(status, 400, raw)
        self.assertEqual(data["error"]["code"], "rejected", raw)
        self.assertEqual([], self.delivered_posts(), raw)

        # Laufstart, der die Kennwortdatei automatisch anlegen muss (AK1/AK3).
        self.make_run_active()
        self.write_vibe()
        self.start_run()
        self.assertTrue(self.run_mock.called, "cmd_run hat den Laufstart nicht erreicht")

        status, data, raw = self.post_steer()
        self.assertEqual(
            200,
            status,
            "AK3 verletzt: Zusatzanweisung wurde nach dem Laufstart nicht "
            "übermittelt (Kennwortdatei wurde nicht automatisch angelegt): " + raw,
        )
        self.assertTrue(data.get("ok"), raw)
        self.assertTrue(str(data.get("message") or "").strip(), raw)

        # Die automatische Anlage ist tatsächlich erfolgt (AK1).
        self.assertTrue(self.password_path.exists())
        credential = self.password_path.read_text(encoding="utf-8").strip()
        self.assertTrue(credential, "Kennwortdatei blieb leer")

        posts = self.delivered_posts()
        self.assertTrue(posts, "opencode-Server-Ersatz hat keine Zustellung erhalten")
        found = [post for post in posts if STEER_TEXT_b3 in post.get("body", "")]
        self.assertTrue(found, f"Zusatztext fehlt in der Zustellung: {posts}")
        for post in found:
            self.assertTrue(post.get("auth_ok"), post)
            self.assertEqual(post.get("user"), "opencode", post)
        # Das Kennwort selbst liegt nicht in der Antwort.
        self.assertNotIn(credential, raw)

        # Zusätzlich abgeleitet aus AK1 („Neuer Kennwortinhalt bleibt geheim"):
        # das Kennwort erscheint in keinem API-Ergebnis und in keiner
        # anderen Laufzeitdatei außer der Kennwortdatei selbst.
        credential = self.password_path.read_text(encoding="utf-8").strip()
        for path in (self.root / "_logs").iterdir():
            if path.is_file() and path.name != PASSWORD_NAME:
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                self.assertNotIn(credential, content, f"Kennwort in {path}")


if __name__ == "__main__":
    unittest.main()
