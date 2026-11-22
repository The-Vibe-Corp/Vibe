"""Unit-Abnahme B3: Automatische Anlagen der opencode-Kennwortdatei beim
Agentenlauf (Arbeitspaket B3, Bug „Nachricht an Agent senden wirft Fehler").

Aus Arbeitspaket B3 und SPEC.md abgeleitete Anforderungen:

* AK1 — Beim Start eines Agentenlaufes über ``vibe.cmd_run`` wird
  ``<runtime>/opencode.password`` automatisch angelegt, wenn sie fehlt. Die
  Datei ist nichtleer, liegt im Laufzeitordner (nicht im Repository) und ist
  mit restriktiven Rechten (0600) angelegt, soweit das Dateisystem sie trägt
  (FUSE/NTFS-Toleranz).
* AK2 — Eine bereits vorhandene, nichtleere Kennwortdatei bleibt vom
  Laufstart unverändert (kein neues Kennwort).
* AK3 — Nach einem Laufstart, der die Kennwortdatei automatisch angelegt
  hat, lehnt ``POST /api/steer`` die Zusatzanweisung NICHT mehr mit „
  Kennwortdatei fehlt" ab; die Zustellung gegen einen opencode-Server-Ersatz
  (vertraglich wie in ``tests/unit/test_output_view_f19_api.py``: POST wird
  nur mit gültigem Basic-Auth — Benutzer „opencode" mit dem Kennwort aus der
  Laufzeitdatei — angenommen) erfolgt mit gültigen Anmeldedaten
  (``auth_ok``, HTTP 2xx).

Es werden keine echten Modellaufrufe getätigt und kein tmux gestartet: Die
externen Grenzen von ``cmd_run`` (tmux, Laufregister, Regel-/Test-Agent-Setup)
liegen in diesem Test als Attrappen; genau die Kennwortdatei- und die
Zustellungslogik selbst werden wirklich mit echten Dateien/Echt-HTTP benutzt.
"""

import base64
import http.client
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

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "bin"
CLI = BIN / "vibe"
WEB = BIN / "vibe-web.py"
RUNS_PY = BIN / "vibe_runs.py"

PASSWORD_NAME = "opencode.password"
BESTAND_PASSWORD = "bestands-kennwort-fuer-b3-unveraendert"
STEER_TEXT = "Prüfe zuerst die Borderstellung"

MAIN_SESSION = "ses_b3_main"

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
    loader = importlib.machinery.SourceFileLoader(name, str(CLI))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


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
                    with mock.patch.object(
                        self.cli, "ensure_general_rules", return_value=False
                    ):
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
            [sys.executable, str(WEB)],
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

    def post_steer(self, name="proj", text=STEER_TEXT):
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
                sys.executable, str(RUNS_PY), "start",
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
        found = [post for post in posts if STEER_TEXT in post.get("body", "")]
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
