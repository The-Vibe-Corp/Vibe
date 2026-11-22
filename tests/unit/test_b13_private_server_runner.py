"""Unit-Abnahme B13 (Teil 1): privater opencode-Server des Paket-Läufers.

Arbeitspaket B13 „Anweisung senden gibt Fehler“ (Bug): Ein Lauf ohne
erreichbaren gemeinsamen opencode-Server lief mit ``--standalone``; das
Dashboard konnte deshalb keine Zusatzanweisung zustellen („Connection
refused“). Vereinbartes Verhalten (umsetzungsneutral):

* Ist weder Harness opencode noch gemeinsamer Server erreichbar, aber die
  Kennwortdatei ``$RUNTIME/opencode.password`` nichtleer lesbar, startet der
  Lauf EINEN privaten opencode-Server auf 127.0.0.1 mit freiem TCP-Port,
  belegt ``OPENCODE_SERVER_PASSWORD`` über die bereits exportierte
  Umgebungsvariable, wartet auf die Gesundheit (GET /api/info mit Basic-
  Auth), übergibt ``--server http://127.0.0.1:<Port>`` an ``opencode run``
  und schreibt ``<Laufprotokoll>.server.json`` mit mindestens ``url``,
  ``port`` und ``password_file``. [AK1, AK2]
* Server-Ausgabe geht in ``<Laufprotokoll>.server.log``, nicht in das
  Laufprotokoll. [AK2]
* Ohne/leerer Kennwortdatei bleibt es bei ``--standalone`` ohne
  Serverdatei. [AK4]
* Beim Laufende wird der private Server beendet und die Serverdatei
  entfernt. [AK5]
* In der Sandbox läuft der private Server innerhalb der Wrapping-Kette
  (derselbe Mechanismus wie der Agent). [AK6]
* Pi-Läufe starten keinen privaten Server. [AK7]
* Ein erreichbarer gemeinsamer Server behält den gemeinsamen
  ``--server``-Zielport; kein privater Server. [AK9]

Der Agent wird durch die opencode-Attrappe aus ``runner_support.py``
ersetzt (mit Server-Zweig für ``opencode serve``); ``curl`` erhält eine
echte HTTP-Attrappe, damit Gesundheitsprüfungen wirklich ankommen. Keine
Modellaufrufe, keine produktive Installation, keine externen Dienste.
"""
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
import test_b6_pi_runner_events as b6_support  # noqa: E402

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
            feedback="- [ ] B13 Testpaket\n  Beschreibung: Test\n",
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
        support.commit_all(self.project)
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


if __name__ == "__main__":
    unittest.main()
