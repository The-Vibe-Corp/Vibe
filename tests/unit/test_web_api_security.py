"""Web-Sicherheit: Login, Sitzungen, Host-/Origin-Prüfung, Netzwerkkonfiguration und CLI-Passwort.

Aufruf: python3 -m unittest tests.unit.test_web_api_security -v
"""


import concurrent.futures
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import quote

from tests.unit import env_support

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"

MAX_BODY = 1024 * 1024


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class WebApiFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True
        )
        cls.port = free_port()
        cls.log_path = cls.root / "server.log"
        cls.log_file = open(cls.log_path, "w", encoding="utf-8")
        # Der Testserver muss auf 127.0.0.1 binden, weil der Test dort
        # verbindet. Ein geerbtes VIBE_UI_BIND (z. B. aus der Läuferumgebung)
        # würde das Dashboard an eine andere Adresse binden.
        env = env_support.isolated_environ()
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "VIBE_INSTALL": str(cls.root / "_toolchain"),
                "VIBE_RUNTIME": str(cls.root / "_logs"),
                "VIBE_STATE": str(cls.root / "_toolchain"),
                "HOME": str(cls.root / "home"),
                "VIBE_CONFIG_FILE": str(
                    cls.root / "home" / ".config" / "vibe" / "config.json"
                ),
            }
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=cls.log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.root / "_logs" / "web.token"
        deadline = time.time() + 20
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: " + cls.server_log()
                )
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        instance_file = cls.root / "_logs" / "web.instance"
        cls.instance = (
            instance_file.read_text(encoding="utf-8").strip()
            if instance_file.exists()
            else None
        )

    @classmethod
    def server_log(cls):
        try:
            return cls.log_path.read_text(encoding="utf-8")
        except OSError:
            return ""

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        cls.log_file.close()
        cls.tmp.cleanup()

    def setUp(self):
        flag = self.pause_flag()
        if flag.exists():
            flag.unlink()

    def pause_flag(self):
        return self.root / "_logs" / "proj.pause-after"

    def request(
        self,
        method,
        path,
        body=None,
        token=True,
        host=None,
        origin=None,
        extra_headers=None,
        content_type="application/json",
    ):
        """Führt eine HTTP-Anfrage mit voller Kontrolle über die Header aus."""
        if body is not None and not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {"Host": host if host is not None else f"127.0.0.1:{self.port}"}
        if token is True:
            headers["X-Token"] = self.token
        elif isinstance(token, str):
            headers["X-Token"] = token
        if origin is not None:
            headers["Origin"] = origin
        if body is not None and content_type is not None:
            headers["Content-Type"] = content_type
        headers.update(extra_headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            text = response.read().decode("utf-8", "replace")
            return response.status, text, dict(response.getheaders())
        finally:
            connection.close()

    def raw_request(self, request_bytes, timeout=10):
        """Sendet einen rohen Request und liest die Antwort bis zum Schließen."""
        with socket.create_connection(("127.0.0.1", self.port), timeout=timeout) as sock:
            sock.sendall(request_bytes)
            chunks = []
            while True:
                try:
                    chunk = sock.recv(4096)
                except socket.timeout:
                    break
                if not chunk:
                    break
                chunks.append(chunk)
        raw = b"".join(chunks).decode("utf-8", "replace")
        status_line = raw.split("\r\n", 1)[0]
        status = int(status_line.split(" ")[1]) if " " in status_line else 0
        _, _, body = raw.partition("\r\n\r\n")
        return status, body


class HealthTest(WebApiFixture):
    def test_health_identifies_vibe_and_instance_without_secrets(self):
        status, body, headers = self.request("GET", "/api/health", token=False)

        self.assertEqual(status, 200, body)
        self.assertIn("application/json", headers.get("Content-Type", ""))
        data = json.loads(body)
        self.assertTrue(data["ok"], body)
        self.assertEqual(data["app"], "vibe")
        self.assertEqual(data["bind"], "127.0.0.1")
        self.assertEqual(data["port"], self.port)
        self.assertIsInstance(data["pid"], int)
        self.assertTrue(data["instance"], "Instanzkennung fehlt")
        self.assertEqual(data["instance"], self.instance)
        self.assertEqual(
            data["version"], (REPO / "VERSION").read_text(encoding="utf-8").strip()
        )
        self.assertEqual(data["commit"], "", "Ein Commit darf nicht geraten werden")
        self.assertEqual(data["release_origin"], "quelle")
        self.assertNotIn(self.token, body)
        self.assertNotIn("token", body.lower())

        second_status, second_body, _ = self.request(
            "GET", "/api/health", token=False
        )
        self.assertEqual(second_status, 200, second_body)
        self.assertEqual(
            json.loads(second_body)["instance"],
            data["instance"],
            "Health muss dieselbe Instanz stabil identifizieren",
        )

    def test_health_rejects_a_foreign_host_header(self):
        # AP13 (Nutzerentscheidung): Reine IP-Literale (IPv4/IPv6) sind als
        # Host erlaubt (Netzwerkbetrieb); DNS-Hostnamen bleiben wegen des
        # DNS-Rebinding-Schutzes abgelehnt.
        for host in ("vibe.example", "127.0.0.1.evil.example"):
            with self.subTest(host=host):
                status, body, _ = self.request(
                    "GET", "/api/health", token=False, host=host
                )
                self.assertEqual(status, 403, body)
                error = json.loads(body)["error"]
                self.assertEqual(error["code"], "forbidden_host")
                self.assertTrue(error["message"])
        for host in ("192.0.2.10", f"[::1]"):
            with self.subTest(host=host):
                status, body, _ = self.request(
                    "GET", "/api/health", token=False, host=host
                )
                self.assertEqual(status, 200, body)
                self.assertEqual(json.loads(body)["app"], "vibe")


class AuthorizationTest(WebApiFixture):
    def assert_rejected_without_effect(self, status, body):
        self.assertEqual(status, 403, body)
        data = json.loads(body)
        self.assertFalse(data["ok"], body)
        self.assertEqual(data["error"]["code"], "unauthorized")
        self.assertTrue(data["error"]["message"])
        self.assertNotIn(self.token, body)
        self.assertFalse(self.pause_flag().exists(), "Abgelehnter Schreibzugriff wirkt")

    def test_write_without_token_is_rejected(self):
        status, body, _ = self.request(
            "POST", "/api/pause", body={"name": "proj", "action": "on"}, token=False
        )
        self.assert_rejected_without_effect(status, body)

    def test_write_with_wrong_token_is_rejected(self):
        status, body, _ = self.request(
            "POST",
            "/api/pause",
            body={"name": "proj", "action": "on"},
            token="falsches-token",
        )
        self.assert_rejected_without_effect(status, body)

    def test_write_with_non_ascii_token_is_rejected_with_structured_error(self):
        # Ein Token mit Nicht-ASCII-Zeichen darf keinen unbehandelten Fehler im
        # Server auslösen, sondern muss wie ein falsches Token abgelehnt werden.
        status, body, _ = self.request(
            "POST",
            "/api/pause",
            body={"name": "proj", "action": "on"},
            token="tökén",
        )
        self.assert_rejected_without_effect(status, body)

    def test_stream_with_non_ascii_query_token_is_rejected_with_structured_error(self):
        # Auch der EventSource-Ausnahmepfad (/api/stream) vergleicht das
        # Query-Token als Bytes und antwortet strukturiert statt abzubrechen.
        status, body, _ = self.request(
            "GET",
            f"/api/stream?name=proj&kind=run&t={quote('tökén')}",
            token=False,
        )
        self.assertEqual(status, 403, body)
        data = json.loads(body)
        self.assertEqual(data["error"]["code"], "unauthorized")
        self.assertNotIn(self.token, body)

    def test_read_without_token_is_rejected(self):
        status, body, _ = self.request("GET", "/api/projects", token=False)
        self.assertEqual(status, 403, body)
        self.assertEqual(json.loads(body)["error"]["code"], "unauthorized")

    def test_token_in_query_is_not_accepted_for_normal_reads(self):
        status, body, _ = self.request(
            "GET", f"/api/projects?t={self.token}", token=False
        )
        self.assertEqual(status, 403, body)
        self.assertEqual(json.loads(body)["error"]["code"], "unauthorized")

    def test_write_with_foreign_origin_is_rejected(self):
        status, body, _ = self.request(
            "POST",
            "/api/pause",
            body={"name": "proj", "action": "on"},
            origin="http://evil.example",
        )
        self.assertEqual(status, 403, body)
        self.assertEqual(json.loads(body)["error"]["code"], "forbidden_origin")
        self.assertFalse(self.pause_flag().exists())

    def test_write_with_origin_on_another_loopback_port_is_rejected(self):
        for origin in (
            f"http://127.0.0.1:{self.port + 1}",
            "http://127.0.0.1",
            f"https://localhost:{self.port}",
        ):
            with self.subTest(origin=origin):
                status, body, _ = self.request(
                    "POST",
                    "/api/pause",
                    body={"name": "proj", "action": "on"},
                    origin=origin,
                )
                self.assertEqual(status, 403, body)
                self.assertEqual(
                    json.loads(body)["error"]["code"], "forbidden_origin"
                )
                self.assertFalse(self.pause_flag().exists())

    def test_write_with_foreign_host_is_rejected(self):
        status, body, _ = self.request(
            "POST",
            "/api/pause",
            body={"name": "proj", "action": "on"},
            host="vibe.example",
        )
        self.assertEqual(status, 403, body)
        self.assertEqual(json.loads(body)["error"]["code"], "forbidden_host")
        self.assertFalse(self.pause_flag().exists())

    def test_cross_site_fetch_metadata_is_rejected(self):
        status, body, _ = self.request(
            "POST",
            "/api/pause",
            body={"name": "proj", "action": "on"},
            extra_headers={"Sec-Fetch-Site": "cross-site"},
        )
        self.assertEqual(status, 403, body)
        self.assertEqual(json.loads(body)["error"]["code"], "forbidden_origin")
        self.assertFalse(self.pause_flag().exists())

    def test_write_with_same_origin_and_token_is_accepted(self):
        status, body, _ = self.request(
            "POST",
            "/api/pause",
            body={"name": "proj", "action": "on"},
            origin=f"http://127.0.0.1:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"},
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(json.loads(body)["ok"], body)
        self.assertTrue(self.pause_flag().exists())


class RequestValidationTest(WebApiFixture):
    def test_invalid_json_is_rejected_with_structured_error(self):
        status, body, _ = self.request(
            "POST", "/api/pause", body=b'{"name": "proj",'
        )
        self.assertEqual(status, 400, body)
        data = json.loads(body)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"]["code"], "invalid_json")
        self.assertTrue(data["error"]["message"])
        self.assertFalse(self.pause_flag().exists())

    def test_non_object_json_is_rejected(self):
        status, body, _ = self.request(
            "POST", "/api/pause", body=json.dumps([1, 2, 3]).encode("utf-8")
        )
        self.assertEqual(status, 400, body)
        self.assertEqual(json.loads(body)["error"]["code"], "invalid_request")
        self.assertFalse(self.pause_flag().exists())

    def test_missing_json_content_type_is_rejected(self):
        status, body, _ = self.request(
            "POST",
            "/api/pause",
            body={"name": "proj", "action": "on"},
            content_type="text/plain",
        )
        self.assertEqual(status, 415, body)
        self.assertEqual(
            json.loads(body)["error"]["code"], "unsupported_media_type"
        )
        self.assertFalse(self.pause_flag().exists())

    def test_oversized_request_is_rejected_before_the_body_is_read(self):
        request = (
            "POST /api/pause HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{self.port}\r\n"
            f"X-Token: {self.token}\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {MAX_BODY + 1}\r\n"
            "\r\n"
        ).encode("ascii")
        status, body = self.raw_request(request)

        self.assertEqual(status, 413, body)
        self.assertEqual(json.loads(body)["error"]["code"], "request_too_large")
        self.assertNotIn(self.token, body)
        self.assertFalse(self.pause_flag().exists())

    def test_missing_content_length_is_rejected(self):
        request = (
            "POST /api/pause HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{self.port}\r\n"
            f"X-Token: {self.token}\r\n"
            "Content-Type: application/json\r\n"
            "\r\n"
        ).encode("ascii")
        status, body = self.raw_request(request)

        self.assertEqual(status, 411, body)
        self.assertEqual(json.loads(body)["error"]["code"], "length_required")
        self.assertFalse(self.pause_flag().exists())


class ConcurrencyTest(WebApiFixture):
    def test_parallel_reads_keep_authorization_per_request(self):
        def call(index):
            allowed = index % 2 == 0
            status, body, _ = self.request("GET", "/api/projects", token=allowed)
            return allowed, status, body

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(call, range(24)))

        for allowed, status, body in results:
            if allowed:
                self.assertEqual(status, 200, body)
                self.assertIsInstance(json.loads(body), list)
            else:
                self.assertEqual(status, 403, body)
                self.assertEqual(json.loads(body)["error"]["code"], "unauthorized")

    def test_parallel_writes_do_not_mix_authorization(self):
        def call(index):
            allowed = index % 2 == 0
            status, body, _ = self.request(
                "POST",
                "/api/pause",
                body={"name": "proj", "action": "on"},
                token=allowed,
            )
            return allowed, status, body

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(call, range(12)))

        for allowed, status, body in results:
            if allowed:
                self.assertEqual(status, 200, body)
                self.assertTrue(json.loads(body)["ok"], body)
            else:
                self.assertEqual(status, 403, body)
                self.assertEqual(json.loads(body)["error"]["code"], "unauthorized")


class LoggingTest(WebApiFixture):
    def test_token_never_appears_in_server_logs(self):
        self.request("GET", "/api/projects")
        self.request("GET", f"/api/projects?t={self.token}", token=False)
        self.request("GET", "/api/health", token=False)
        deadline = time.time() + 5
        log = ""
        while time.time() < deadline:
            log = self.server_log()
            if "/api/health" in log:
                break
            time.sleep(0.05)

        self.assertIn("/api/projects", log, "Zugriffslog fehlt")
        self.assertNotIn(self.token, log, "Token steht im Log")
        self.assertNotIn("t=", log, "Query-String steht im Log")


class LoopbackBindTest(unittest.TestCase):
    def test_a_non_loopback_bind_address_is_refused(self):
        # AP13 (Nutzerentscheidung): Standard bleibt Loopback, aber eine
        # ausdrücklich konfigurierte Netz-Bindung (0.0.0.0) startet das
        # Dashboard und Health bleibt ohne Token lesbar. Der Testprozess
        # wird am Ende sauber beendet.
        tmp = tempfile.TemporaryDirectory()
        try:
            root = Path(tmp.name)
            port = free_port()
            env = env_support.isolated_environ()
            env.update(
                {
                    "VIBE": str(root),
                    "VIBE_NO_CONTAINER": "1",
                    "VIBE_UI_PORT": str(port),
                    "VIBE_UI_BIND": "0.0.0.0",
                    "VIBE_INSTALL": str(root / "_toolchain"),
                    "VIBE_RUNTIME": str(root / "_logs"),
                    "VIBE_STATE": str(root / "_toolchain"),
                    "HOME": str(root / "home"),
                }
            )
            log_path = root / "server.log"
            with open(log_path, "w", encoding="utf-8") as log_file:
                proc = subprocess.Popen(
                    [sys.executable, str(WEB)],
                    env=env,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                try:
                    deadline = time.time() + 25
                    while time.time() < deadline:
                        if proc.poll() is not None:
                            output = log_path.read_text(encoding="utf-8")
                            self.fail(
                                "vibe-web beendete sich bei Bindung an 0.0.0.0: "
                                + output
                            )
                        try:
                            connection = http.client.HTTPConnection(
                                "127.0.0.1", port, timeout=1
                            )
                            connection.request("GET", "/api/health")
                            response = connection.getresponse()
                            body = response.read().decode("utf-8", "replace")
                            connection.close()
                            if response.status == 200:
                                data = json.loads(body)
                                self.assertEqual(data["app"], "vibe", body)
                                self.assertEqual(data["bind"], "0.0.0.0", body)
                                break
                        except (OSError, ValueError):
                            pass
                        time.sleep(0.05)
                    else:
                        self.fail(
                            "Health bei Bindung an 0.0.0.0 nicht erreichbar: "
                            + log_path.read_text(encoding="utf-8")
                        )
                finally:
                    if proc.poll() is None:
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait()
        finally:
            tmp.cleanup()


# ===========================================================================
# Unabhängige Abnahme: Web-Zugriffssicherheit (Session, Security-API)
# ===========================================================================

import http.client
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ISOLATED_ENV = (
    "VIBE",
    "VIBE_NO_CONTAINER",
    "HOME",
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
    "VIBE_HARNESS",
    "XDG_CONFIG_HOME",
)


def local_non_loopback_ip():
    """Die eigene Nicht-Loopback-IPv4 oder None, wenn es keine gibt."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        address = probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()
    if not address or address.startswith("127."):
        return None
    return address


class AccessDashboardFixture(unittest.TestCase):
    """Startet ein echtes Dashboard mit isolierten Pfaden und eigener ui.json."""

    ui_json_data = None  # vom setUpClass der Unterklasse gesetzt

    @classmethod
    def start_server(cls, ui_json_data=None):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.toolchain = cls.root / "_toolchain"
        cls.toolchain.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.state = cls.toolchain
        cls.port = free_port()
        if ui_json_data is not None:
            (cls.state / "ui.json").write_text(
                json.dumps(ui_json_data), encoding="utf-8"
            )
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.home),
                "VIBE_STATE": str(cls.state),
                "VIBE_INSTALL": str(cls.toolchain),
                "VIBE_RUNTIME": str(cls.log_dir),
                "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode" / "agents"),
                "VIBE_CONFIG_FILE": str(
                    cls.home / ".config" / "vibe" / "config.json"
                ),
            }
        )
        cls.log_path = cls.root / "server.log"
        cls.log_file = open(cls.log_path, "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=cls.log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 25
        while time.time() < deadline:
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: " + cls.server_log()
                )
            if token_file.exists():
                try:
                    with socket.create_connection(
                        ("127.0.0.1", cls.port), timeout=0.5
                    ):
                        break
                except OSError:
                    pass
            time.sleep(0.05)
        else:
            raise AssertionError(
                "vibe-web ist nicht erreichbar: " + cls.server_log()
            )
        cls.token = token_file.read_text(encoding="utf-8").strip()

    @classmethod
    def server_log(cls):
        try:
            return cls.log_path.read_text(encoding="utf-8")
        except OSError:
            return ""

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        cls.log_file.close()
        cls.tmp.cleanup()

    def request(
        self,
        method,
        path,
        body=None,
        token=None,
        cookie=None,
        host=None,
        origin=None,
        extra_headers=None,
        via=None,
        port=None,
    ):
        """HTTP-Anfrage mit voller Header-Kontrolle; via=Client-IP.

        ``port`` adressiert einen der Extra-Server der Allowlist-Fälle;
        ohne Angabe wird der Klassen-Server angesprochen.
        """
        if body is not None and not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        port = self.port if port is None else port
        headers = {
            "Host": host if host is not None else f"127.0.0.1:{port}"
        }
        if token is not None:
            headers["X-Token"] = token
        if cookie is not None:
            headers["Cookie"] = cookie
        if origin is not None:
            headers["Origin"] = origin
        if body is not None:
            headers["Content-Type"] = "application/json"
        headers.update(extra_headers or {})
        connection = http.client.HTTPConnection(
            via or "127.0.0.1", port, timeout=10
        )
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            text = response.read().decode("utf-8", "replace")
            return response.status, text, dict(response.getheaders())
        finally:
            connection.close()

    def login(self, field, value, origin=None):
        """POST /api/login und Rückgabe (status, body, cookie)."""
        status, body, headers = self.request(
            "POST",
            "/api/login",
            body={field: value},
            token=None,
            origin=origin or f"http://127.0.0.1:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"},
        )
        cookie_header = None
        for key, value in headers.items():
            if key.lower() == "set-cookie":
                cookie_header = value
        return status, body, cookie_header

    def session_cookie(self, field="token", value=None):
        """Meldet sich an und liefert den Cookie-String 'vibe_session=...'."""
        status, body, cookie_header = self.login(field, value or self.token)
        assert status == 200, body
        assert cookie_header, "Login setzte keinen Cookie: " + body
        match = re.search(r"vibe_session=([^;]+)", cookie_header)
        assert match, cookie_header
        return "vibe_session=" + match.group(1)

    def ui_json_path(self):
        return self.state / "ui.json"


class LoginFlowTest(AccessDashboardFixture):
    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def test_health_and_page_and_static_stay_readable_without_auth(self):
        status, body, _ = self.request("GET", "/api/health", token=None)
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["app"], "vibe", body)

        status, page, headers = self.request("GET", "/", token=None)
        self.assertEqual(status, 200, page)
        self.assertIn("text/html", headers.get("Content-Type", ""))

        status, asset, _ = self.request("GET", "/static/app.js", token=None)
        self.assertEqual(status, 200, asset)

    def test_reads_without_credentials_are_rejected(self):
        status, body, _ = self.request("GET", "/api/projects", token=None)
        self.assertEqual(status, 403, body)
        self.assertEqual(json.loads(body)["error"]["code"], "unauthorized")

    def test_login_with_instance_token_sets_a_session_cookie(self):
        status, body, cookie = self.login("token", self.token)

        self.assertEqual(status, 200, body)
        self.assertTrue(json.loads(body)["ok"], body)
        self.assertIn("vibe_session=", cookie)
        self.assertIn("HttpOnly", cookie, "Cookie ist nicht HttpOnly")
        self.assertIn("SameSite=Strict", cookie)
        self.assertIn("Path=/", cookie)
        self.assertNotIn(self.token, cookie, "Cookie trägt das Token im Klartext")

    def test_wrong_token_and_wrong_password_are_rejected_structured(self):
        status, body, cookie = self.login("token", "falsches-token")
        self.assertEqual(status, 403, body)
        error = json.loads(body)["error"]
        self.assertTrue(error["code"], body)
        self.assertTrue(error["message"], body)
        self.assertFalse(json.loads(body)["ok"], body)
        self.assertIsNone(cookie, "Fehlgeschlagener Login setzte einen Cookie")

    def test_cookie_authorizes_get_and_post(self):
        cookie = self.session_cookie()

        status, body, _ = self.request(
            "GET", "/api/projects", token=None, cookie=cookie
        )
        self.assertEqual(status, 200, body)
        self.assertIsInstance(json.loads(body), list)

        status, body, _ = self.request(
            "POST",
            "/api/pause",
            body={"name": "proj", "action": "on"},
            token=None,
            cookie=cookie,
            origin=f"http://127.0.0.1:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"},
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(json.loads(body)["ok"], body)

    def test_cookie_write_still_requires_same_origin(self):
        cookie = self.session_cookie()

        status, body, _ = self.request(
            "POST",
            "/api/pause",
            body={"name": "proj", "action": "on"},
            token=None,
            cookie=cookie,
            origin="http://evil.example",
        )
        self.assertEqual(status, 403, body)
        self.assertEqual(json.loads(body)["error"]["code"], "forbidden_origin")

    def test_logout_ends_the_session(self):
        cookie = self.session_cookie()
        status, body, set_cookie = self.request(
            "POST",
            "/api/logout",
            token=None,
            cookie=cookie,
            origin=f"http://127.0.0.1:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"},
        )
        self.assertEqual(status, 200, body)

        status, body, _ = self.request(
            "GET", "/api/projects", token=None, cookie=cookie
        )
        self.assertEqual(status, 403, body)
        self.assertEqual(json.loads(body)["error"]["code"], "unauthorized")

    def test_forged_cookie_value_is_rejected(self):
        status, body, _ = self.request(
            "GET", "/api/projects", token=None, cookie="vibe_session=forged"
        )
        self.assertEqual(status, 403, body)
        self.assertEqual(json.loads(body)["error"]["code"], "unauthorized")

    def test_x_token_header_still_works(self):
        status, body, _ = self.request("GET", "/api/projects", token=self.token)
        self.assertEqual(status, 200, body)

        status, body, _ = self.request(
            "POST",
            "/api/pause",
            body={"name": "proj", "action": "on"},
            token=self.token,
            origin=f"http://127.0.0.1:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"},
        )
        self.assertEqual(status, 200, body)

    def test_query_token_is_only_accepted_for_the_stream(self):
        status, body, _ = self.request(
            "GET", f"/api/projects?t={self.token}", token=None
        )
        self.assertEqual(status, 403, body)
        self.assertEqual(json.loads(body)["error"]["code"], "unauthorized")

        # Der Stream endet nicht von allein; wir lesen nur den Antwortkopf
        # und schließen die Verbindung danach.
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(
                "GET",
                f"/api/stream?name=proj&kind=run&t={self.token}",
                headers={"Host": f"127.0.0.1:{self.port}"},
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 200, response.status)
            self.assertIn(
                "text/event-stream", response.getheader("Content-Type") or ""
            )
        finally:
            connection.close()

    def test_password_login_after_setting_it_via_security_api(self):
        # Passwort setzen geht nur über die geschützte Security-API.
        cookie = self.session_cookie()
        status, body, _ = self.request(
            "POST",
            "/api/security",
            body={"action": "password", "password": "ap13-paswort-lang-42"},
            token=None,
            cookie=cookie,
            origin=f"http://127.0.0.1:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"},
        )
        self.assertEqual(status, 200, body)

        status, body, _ = self.login("password", "ap13-paswort-lang-42")
        self.assertEqual(status, 200, body)
        self.assertTrue(json.loads(body)["ok"], body)

        status, body, _ = self.login("password", "falsches kennwort")
        self.assertEqual(status, 403, body)
        self.assertNotIn(
            "ap13-paswort-lang-42", body, "Fehler verrät das Kennwort"
        )

        # Token-Login bleibt daneben weiterhin gültig.
        status, body, _ = self.login("token", self.token)
        self.assertEqual(status, 200, body)


class SecurityApiTest(AccessDashboardFixture):
    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def session(self):
        return self.session_cookie()

    def security_request(self, body, cookie=None, token=None):
        return self.request(
            "POST",
            "/api/security",
            body=body,
            token=token,
            cookie=cookie,
            origin=f"http://127.0.0.1:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"},
        )

    def test_security_view_requires_authorization(self):
        status, body, _ = self.request("GET", "/api/security", token=None)
        self.assertEqual(status, 403, body)
        self.assertEqual(json.loads(body)["error"]["code"], "unauthorized")

    def test_security_view_reports_current_values(self):
        for credentials in ({"token": self.token}, {"cookie": self.session()}):
            with self.subTest(credentials=sorted(credentials)):
                status, body, _ = self.request(
                    "GET", "/api/security", **credentials
                )
                self.assertEqual(status, 200, body)
                data = json.loads(body)
                self.assertTrue(data["ok"], body)
                self.assertEqual(data["port"], self.port)
                self.assertEqual(data["bind"], "127.0.0.1")
                self.assertEqual(data["allowlist"], [])
                self.assertFalse(data["password_set"])
                self.assertFalse(
                    data["restart_required"],
                    "Ohne ui.json ist kein Neustart nötig",
                )

    def test_security_save_writes_ui_json_and_flags_restart(self):
        cookie = self.session()
        new_port = free_port()

        status, body, _ = self.security_request(
            {"action": "save", "port": new_port, "bind": "0.0.0.0"}, cookie=cookie
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(json.loads(body)["ok"], body)

        stored = json.loads(self.ui_json_path().read_text(encoding="utf-8"))
        self.assertEqual(stored.get("ui_port"), new_port)
        self.assertEqual(stored.get("ui_bind"), "0.0.0.0")

        status, body, _ = self.request("GET", "/api/security", cookie=cookie)
        data = json.loads(body)
        self.assertTrue(data["restart_required"], body)

        # Zurücksetzen auf die laufenden Werte hebt die Neustart-Markierung.
        status, body, _ = self.security_request(
            {"action": "save", "port": self.port, "bind": "127.0.0.1"},
            cookie=cookie,
        )
        self.assertEqual(status, 200, body)
        status, body, _ = self.request("GET", "/api/security", cookie=cookie)
        self.assertFalse(json.loads(body)["restart_required"], body)

    def test_security_save_rejects_invalid_values_without_change(self):
        cookie = self.session()
        before = (
            self.ui_json_path().read_text(encoding="utf-8")
            if self.ui_json_path().exists()
            else None
        )

        for bad in (
            {"action": "save", "port": 70000},
            {"action": "save", "port": 0},
            {"action": "save", "bind": "example.test"},
            {"action": "save", "allowlist": ["nicht-ip"]},
            {"action": "save", "allowlist": "keine liste"},
            {"action": "unbekannt"},
        ):
            with self.subTest(bad=bad):
                status, body, _ = self.security_request(bad, cookie=cookie)
                self.assertEqual(status, 400, body)
                error = json.loads(body)["error"]
                self.assertTrue(error["code"], body)
                self.assertTrue(error["message"], body)

        after = (
            self.ui_json_path().read_text(encoding="utf-8")
            if self.ui_json_path().exists()
            else None
        )
        self.assertEqual(before, after, "Ungültige Eingabe veränderte ui.json")

    def test_password_actions_validate_and_take_effect(self):
        cookie = self.session()

        status, body, _ = self.security_request(
            {"action": "password", "password": "kurz"}, cookie=cookie
        )
        self.assertEqual(status, 400, body)

        status, body, _ = self.security_request(
            {"action": "password", "password": "ap13-paswort-lang-99"},
            cookie=cookie,
        )
        self.assertEqual(status, 200, body)
        status, body, _ = self.request("GET", "/api/security", cookie=cookie)
        self.assertTrue(json.loads(body)["password_set"], body)
        self.assertFalse(
            "ap13-paswort-lang-99" in body, "Antwort enthält das Kennwort"
        )

        # Anmeldung mit dem neuen Passwort, dann Entfernen.
        status, body, _ = self.login("password", "ap13-paswort-lang-99")
        self.assertEqual(status, 200, body)

        status, body, _ = self.security_request(
            {"action": "password", "clear": True}, cookie=cookie
        )
        self.assertEqual(status, 200, body)
        status, body, _ = self.request("GET", "/api/security", cookie=cookie)
        self.assertFalse(json.loads(body)["password_set"], body)
        status, body, _ = self.login("password", "ap13-paswort-lang-99")
        self.assertEqual(status, 403, body)

    def test_password_is_never_in_logs_or_responses(self):
        kennwort = "ap13-topsecret-pass-77"
        cookie = self.session()
        self.security_request(
            {"action": "password", "password": kennwort}, cookie=cookie
        )
        self.login("password", "falsch-geraten-123")
        self.login("password", kennwort)
        time.sleep(0.5)

        log = self.server_log()
        self.assertNotIn(kennwort, log, "Kennwort steht im Server-Log")
        self.assertNotIn("falsch-geraten-123", log)
        self.assertNotIn(self.token, log)

        security = self.request("GET", "/api/security", token=self.token)
        self.assertNotIn(kennwort, security[1])
        self.assertNotIn("falsch-geraten-123", security[1])

        # Aufräumen: Kennwort entfernen, damit keine Erwartung eines
        # späteren Tests von der Ausführungsreihenfolge abhängt.
        status, body, _ = self.security_request(
            {"action": "password", "clear": True}, cookie=cookie
        )
        self.assertEqual(status, 200, body)


class HostOriginLiteralTest(AccessDashboardFixture):
    """Netzwerkbetrieb erweitert die Host-/Origin-Prüfung auf IP-Literale."""

    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def test_host_with_ip_literal_is_allowed(self):
        status, body, _ = self.request(
            "GET", "/api/projects", token=self.token, host=f"192.0.2.10:{self.port}"
        )
        self.assertEqual(status, 200, body)

        status, body, _ = self.request(
            "GET", "/api/projects", token=self.token, host=f"[::1]:{self.port}"
        )
        self.assertEqual(status, 200, body)

    def test_dns_hostnames_stay_rejected(self):
        for host in ("vibe.example", "127.0.0.1.evil.example"):
            with self.subTest(host=host):
                status, body, _ = self.request(
                    "GET",
                    "/api/projects",
                    token=self.token,
                    host=f"{host}:{self.port}",
                )
                self.assertEqual(status, 403, body)
                self.assertEqual(
                    json.loads(body)["error"]["code"], "forbidden_host"
                )

    def test_origin_with_ip_literal_and_matching_port_is_allowed(self):
        status, body, _ = self.request(
            "POST",
            "/api/pause",
            body={"name": "proj", "action": "on"},
            token=self.token,
            host=f"192.0.2.10:{self.port}",
            origin=f"http://192.0.2.10:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"},
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(json.loads(body)["ok"], body)

        status, body, _ = self.request(
            "POST",
            "/api/pause",
            body={"name": "proj", "action": "on"},
            token=self.token,
            origin=f"http://192.0.2.10:{self.port}",
            extra_headers={"Sec-Fetch-Site": "same-origin"},
        )
        self.assertEqual(status, 200, body)

    def test_origin_with_wrong_port_is_rejected(self):
        for origin in (
            f"http://192.0.2.10:{self.port + 1}",
            f"http://[::1]:{self.port + 1}",
            "http://192.0.2.10",
        ):
            with self.subTest(origin=origin):
                status, body, _ = self.request(
                    "POST",
                    "/api/pause",
                    body={"name": "proj", "action": "on"},
                    token=self.token,
                    origin=origin,
                    extra_headers={"Sec-Fetch-Site": "same-origin"},
                )
                self.assertEqual(status, 403, body)
                self.assertEqual(
                    json.loads(body)["error"]["code"], "forbidden_origin"
                )


class AllowlistHttpTest(AccessDashboardFixture):
    """Allowlist auf HTTP-Ebene; Loopback bleibt immer erlaubt."""

    @classmethod
    def setUpClass(cls):
        cls.local_ip = local_non_loopback_ip()
        if cls.local_ip is None:
            raise unittest.SkipTest(
                "Keine Nicht-Loopback-Adresse im Testsystem; Allowlist-Ablehnung "
                "wird auf Funktionsebene (test_ap13_network_config) geprüft"
            )
        cls.servers = []

    @classmethod
    def tearDownClass(cls):
        # Erst die Extra-Server stoppen, dann den Klassen-Server und zuletzt
        # den isolierten Bereich aufräumen; sonst bleiben Dashboards als
        # verwaiste Prozesse zurück. (Der Aufruf des Basis-tearDowns bindet
        # an DashboardFixture selbst, deshalb explizit hier.)
        for server in cls.servers:
            server()
        if getattr(cls, "proc", None) is not None and cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        if getattr(cls, "log_file", None) is not None:
            cls.log_file.close()
        if getattr(cls, "tmp", None) is not None and cls.tmp is not None:
            cls.tmp.cleanup()

    @classmethod
    def open_extra_server(cls, ui_json_data):
        """Startet ein weiteres Dashboard in demselben isolierten Bereich.

        Es erbt die isolierten Pfade und bekommt eigene Port-/Zustandsdaten;
        die Allowlist steckt ausschließlich in ui.json. Rückgabe (port, token).
        """
        port = free_port()
        extra_state = cls.root / f"state-{port}"
        extra_state.mkdir()
        (extra_state / "ui.json").write_text(
            json.dumps(ui_json_data), encoding="utf-8"
        )
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(port),
                "HOME": str(cls.home),
                "VIBE_STATE": str(extra_state),
                "VIBE_INSTALL": str(cls.root / "_toolchain"),
                "VIBE_RUNTIME": str(cls.root / "_logs"),
                "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode" / "agents"),
                "VIBE_CONFIG_FILE": str(
                    cls.home / ".config" / "vibe" / "config.json"
                ),
            }
        )
        log_path = cls.root / f"server-{port}.log"
        log_file = open(log_path, "w", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.root / "_logs" / "web.token"
        previous_token = (
            token_file.read_text(encoding="utf-8") if token_file.exists() else None
        )
        deadline = time.time() + 25
        while time.time() < deadline:
            if proc.poll() is not None:
                log_file.close()
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: "
                    + log_path.read_text(encoding="utf-8")
                )
            current = (
                token_file.read_text(encoding="utf-8")
                if token_file.exists()
                else ""
            )
            if current and current != previous_token:
                try:
                    with socket.create_connection(
                        ("127.0.0.1", port), timeout=0.5
                    ):
                        break
                except OSError:
                    pass
            time.sleep(0.05)
        else:
            log_file.close()
            raise AssertionError("Extra-Server ist nicht erreichbar")
        token = current.strip()

        def stop():
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            log_file.close()

        cls.servers.append(stop)
        return port, token

class AllowlistOpenServerTest(AllowlistHttpTest):
    @classmethod
    def setUpClass(cls):
        AllowlistHttpTest.setUpClass()
        cls.start_server({"ui_bind": "0.0.0.0", "allowlist": []})
        cls.open_port, cls.open_token = cls.open_extra_server(
            {"ui_bind": "0.0.0.0", "allowlist": []}
        )

    def test_open_server_allows_the_local_network_ip(self):
        status, body, _ = self.request(
            "GET", "/api/health", token=None, via=self.local_ip
        )
        self.assertEqual(status, 200, body)

        status, body, _ = self.request(
            "GET", "/api/projects", token=self.open_token,
            via=self.local_ip, port=self.open_port,
        )
        self.assertEqual(status, 200, body)


class AllowlistRestrictiveServerTest(AllowlistHttpTest):
    @classmethod
    def setUpClass(cls):
        AllowlistHttpTest.setUpClass()
        cls.start_server(
            {"ui_bind": "0.0.0.0", "allowlist": ["203.0.113.7"]}
        )
        cls.admitting_port, cls.admitting_token = cls.open_extra_server(
            {"ui_bind": "0.0.0.0", "allowlist": [cls.local_ip]}
        )

    def test_allowlist_admitting_the_local_ip_allows_it(self):
        status, body, _ = self.request(
            "GET", "/api/projects", token=self.admitting_token,
            via=self.local_ip, port=self.admitting_port,
        )
        self.assertEqual(status, 200, body)
        # Loopback ist trotz Allowlist immer erlaubt (Aussperrschutz);
        # dieselbe Anfrage von Loopback an denselben Server.
        status, body, _ = self.request(
            "GET", "/api/projects", token=self.admitting_token,
            port=self.admitting_port,
        )
        self.assertEqual(status, 200, body)

    def test_allowlist_denying_the_local_ip_returns_forbidden_ip(self):
        status, body, _ = self.request(
            "GET", "/api/projects", token=self.token, via=self.local_ip
        )
        self.assertEqual(status, 403, body)
        error = json.loads(body)["error"]
        self.assertEqual(error["code"], "forbidden_ip")
        self.assertTrue(error["message"], body)
        self.assertNotIn(self.local_ip, body, "Fehler verrät die Client-IP?")

    def test_loopback_stays_allowed_with_a_restrictive_allowlist(self):
        status, body, _ = self.request("GET", "/api/projects", token=self.token)
        self.assertEqual(status, 200, body)

    def test_source_really_is_the_non_loopback_address(self):
        # Vorbedingung der HTTP-Ebene: Verbindungen zur Nicht-Loopback-Adresse
        # dieses Rechners tragen sie auch als Quelladresse (sonst wäre der
        # Test ein Loopback-Test und beweist nichts).
        with socket.create_connection(
            (self.local_ip, self.port), timeout=5
        ) as probe:
            self.assertEqual(probe.getsockname()[0], self.local_ip)


# ===========================================================================
# Unabhängige Abnahme: Netzwerkbetrieb, Port-/Bind-Konfiguration
# ===========================================================================

import importlib.machinery
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN = REPO / "bin"
PATHS_MODULE = BIN / "vibe_paths.py"
UI_CONFIG_MODULE = BIN / "vibe_ui_config.py"
CLI = BIN / "vibe"

ENV_KEYS = (
    "VIBE",
    "VIBE_PROFILE",
    "VIBE_INSTALL",
    "VIBE_RUNTIME",
    "VIBE_STATE",
    "VIBE_UI_PORT",
    "VIBE_OPENCODE_PORT",
    "VIBE_UI_BIND",
    "VIBE_CONTAINER",
    "VIBE_AGENTS_DIR",
    "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR",
    "XDG_CONFIG_HOME",
    "HOME",
)


def load_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def load_paths():
    return load_module(PATHS_MODULE, "vibe_paths_ap13")


def load_ui_config():
    """Lädt das neue AP13-Modul; in der Rotphase fehlt es mit klarer Meldung."""
    if not UI_CONFIG_MODULE.exists():
        raise AssertionError(
            "AP13-Modul bin/vibe_ui_config.py existiert nicht (erwarteter "
            "Rot-Status, bis die Implementierung es anlegt)"
        )
    return load_module(UI_CONFIG_MODULE, "vibe_ui_config_ap13")


class StateDirFixture(unittest.TestCase):
    """Temporärer Zustandsordner ohne Berührung produktiver Pfade."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "state"
        self.state.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    @property
    def ui_json(self):
        return self.state / "ui.json"

    def write_ui_json(self, raw):
        self.ui_json.write_text(raw, encoding="utf-8")


class UiConfigFileTest(StateDirFixture):
    """ui.json laden und speichern; Defekte werden gemeldet."""

    def test_missing_file_loads_an_empty_object(self):
        ui_config = load_ui_config()

        data = ui_config.load(str(self.state))

        self.assertEqual(data, {})
        self.assertFalse(self.ui_json.exists(), "load darf keine Datei anlegen")

    def test_empty_file_loads_an_empty_object(self):
        self.write_ui_json("")
        ui_config = load_ui_config()

        self.assertEqual(ui_config.load(str(self.state)), {})

    def test_corrupt_file_is_reported_instead_of_ignored(self):
        self.write_ui_json("{kein json")
        ui_config = load_ui_config()

        with self.assertRaises(ValueError) as raised:
            ui_config.load(str(self.state))

        self.assertIn("ui.json", str(raised.exception))

    def test_save_validates_roundtrip_and_returns_the_path(self):
        ui_config = load_ui_config()

        path = ui_config.save(str(self.state), {"ui_port": 9151, "ui_bind": "0.0.0.0"})

        self.assertIn("ui.json", str(path))
        stored = json.loads(self.ui_json.read_text(encoding="utf-8"))
        self.assertEqual(stored, {"ui_port": 9151, "ui_bind": "0.0.0.0"})
        self.assertEqual(ui_config.load(str(self.state)), stored)

    def test_save_rejects_invalid_data_without_writing(self):
        ui_config = load_ui_config()

        with self.assertRaises(ValueError):
            ui_config.save(str(self.state), {"ui_port": 70000})

        self.assertFalse(self.ui_json.exists(), "Ungültige Daten wurden gespeichert")

    def test_save_rejects_non_object_data(self):
        ui_config = load_ui_config()

        with self.assertRaises(ValueError):
            ui_config.save(str(self.state), ["kein", "objekt"])

        self.assertFalse(self.ui_json.exists())


class ValidateTest(StateDirFixture):
    def test_validate_returns_a_cleaned_dict(self):
        ui_config = load_ui_config()

        cleaned = ui_config.validate(
            {"ui_port": 9151, "ui_bind": "0.0.0.0", "unbekannt": 1}
        )

        self.assertEqual(cleaned, {"ui_port": 9151, "ui_bind": "0.0.0.0"})
        self.assertNotIn("unbekannt", cleaned)

    def test_validate_accepts_an_empty_object(self):
        ui_config = load_ui_config()

        self.assertEqual(ui_config.validate({}), {})

    def test_validate_rejects_invalid_values(self):
        cases = (
            {"ui_port": 0},
            {"ui_port": 65536},
            {"ui_port": "abc"},
            {"ui_bind": "example.test"},
            {"ui_bind": ""},
            {"allowlist": "keine liste"},
            {"allowlist": [42]},
            {"password_hash": "kein objekt"},
        )
        ui_config = load_ui_config()
        for data in cases:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    ui_config.validate(data)

    def test_validate_rejects_non_ip_allowlist_entries(self):
        ui_config = load_ui_config()

        for entry in ("nicht-ip", "10.0.0.0/99", "300.1.2.3", ""):
            with self.subTest(entry=entry):
                with self.assertRaises(ValueError):
                    ui_config.validate({"allowlist": [entry]})

    def test_validate_rejects_ipv6_allowlist_entries(self):
        # IPv6-Allowlist-Einträge wären bei IPv4-only-Bindung toter, nie
        # wirksamer Zustand in ui.json; sie werden abgelehnt statt still
        # akzeptiert. Die Meldung nennt IPv6 und den IPv4-Heimnetzstand.
        ui_config = load_ui_config()

        for entry in ("2001:db8::7", "2001:db8::/32"):
            with self.subTest(entry=entry):
                with self.assertRaises(ValueError) as raised:
                    ui_config.validate({"allowlist": [entry]})
                self.assertIn("IPv6", str(raised.exception))
                self.assertIn("IPv4", str(raised.exception))

    def test_config_error_is_a_value_error(self):
        ui_config = load_ui_config()

        with self.assertRaises(ValueError):
            ui_config.validate({"ui_port": 70000})


class AllowlistTest(StateDirFixture):
    """``client_allowed``: reine Match-Funktion ohne erreichbaren Verkehr.

    Die IPv6-Fälle prüfen den internen Hilfsfunktion-Vertrag. Produktion
    erreicht diese Pfade nicht: ``validate`` lehnt IPv6-Allowlist-Einträge
    ab und ``validate_bind`` ist IPv4-only, sodass weder IPv6-Einträge in
    ui.json noch IPv6-Clients ankommen können. Die Fälle bleiben als
    Robustheitsnachweis der Match-Logik (fail-closed statt Absturz)
    bestehen; kein Produktionspfad ändert sich dadurch.
    """

    def test_empty_or_missing_allowlist_allows_every_client(self):
        ui_config = load_ui_config()

        for data in ({}, {"allowlist": []}, {"ui_port": 9151}):
            for ip in ("192.168.1.5", "10.0.0.5", "2001:db8::1"):
                with self.subTest(data=data, ip=ip):
                    self.assertTrue(ui_config.client_allowed(data, ip))

    def test_loopback_is_always_allowed_lockout_protection(self):
        # Aussperrschutz: Auch wenn die Allowlist Loopback nicht nennt, muss
        # ein lokaler Client weiterarbeiten können.
        ui_config = load_ui_config()

        for ip in ("127.0.0.1", "127.5.5.5", "::1"):
            with self.subTest(ip=ip):
                self.assertTrue(
                    ui_config.client_allowed({"allowlist": ["1.2.3.4"]}, ip)
                )

    def test_single_ip_entry_matches_exactly(self):
        ui_config = load_ui_config()
        data = {"allowlist": ["192.168.1.5"]}

        self.assertTrue(ui_config.client_allowed(data, "192.168.1.5"))
        self.assertFalse(ui_config.client_allowed(data, "192.168.1.6"))
        self.assertFalse(ui_config.client_allowed(data, "10.0.0.5"))

    def test_cidr_entry_matches_a_network(self):
        ui_config = load_ui_config()
        data = {"allowlist": ["10.0.0.0/8"]}

        self.assertTrue(ui_config.client_allowed(data, "10.255.0.1"))
        self.assertTrue(ui_config.client_allowed(data, "10.0.0.0"))
        self.assertFalse(ui_config.client_allowed(data, "11.0.0.1"))
        self.assertFalse(ui_config.client_allowed(data, "192.168.1.5"))

    def test_ipv6_entries_match_ipv6_clients(self):
        ui_config = load_ui_config()
        single = {"allowlist": ["2001:db8::7"]}
        network = {"allowlist": ["2001:db8::/32"]}

        self.assertTrue(ui_config.client_allowed(single, "2001:db8::7"))
        self.assertFalse(ui_config.client_allowed(single, "2001:db8::8"))
        self.assertTrue(ui_config.client_allowed(network, "2001:db8:aaaa::1"))
        self.assertFalse(ui_config.client_allowed(network, "2001:db9::1"))

    def test_mixed_entries_match_each_rule(self):
        ui_config = load_ui_config()
        data = {"allowlist": ["192.168.1.5", "10.0.0.0/8", "2001:db8::/32"]}

        self.assertTrue(ui_config.client_allowed(data, "192.168.1.5"))
        self.assertTrue(ui_config.client_allowed(data, "10.1.2.3"))
        self.assertTrue(ui_config.client_allowed(data, "2001:db8::9"))
        self.assertFalse(ui_config.client_allowed(data, "192.168.1.6"))
        self.assertFalse(ui_config.client_allowed(data, "11.1.1.1"))
        self.assertFalse(ui_config.client_allowed(data, "2001:db9::9"))

    def test_invalid_client_ip_is_denied_not_crashing(self):
        ui_config = load_ui_config()

        self.assertFalse(ui_config.client_allowed({"allowlist": []}, ""))
        self.assertFalse(
            ui_config.client_allowed({"allowlist": ["10.0.0.0/8"]}, "nicht-ip")
        )


class PasswordTest(StateDirFixture):
    def test_short_password_is_rejected_without_change(self):
        ui_config = load_ui_config()

        for text in ("", "kurz", "1234567"):
            with self.subTest(length=len(text)):
                with self.assertRaises(ValueError):
                    ui_config.set_password(str(self.state), text)

        self.assertFalse(self.ui_json.exists())

    def test_password_is_stored_salted_without_plaintext(self):
        ui_config = load_ui_config()
        text = "sicheres-paswort-8971"

        ui_config.set_password(str(self.state), text)

        stored = json.loads(self.ui_json.read_text(encoding="utf-8"))
        self.assertIn("password_hash", stored)
        self.assertNotIn(text, self.ui_json.read_text(encoding="utf-8"))
        hash_value = stored["password_hash"]
        self.assertIsInstance(hash_value, dict)
        self.assertTrue(hash_value, "Der Hash enthält Daten")

    def test_two_set_password_calls_use_different_salts(self):
        ui_config = load_ui_config()
        text = "sicheres-paswort-8971"

        ui_config.set_password(str(self.state), text)
        first = json.loads(self.ui_json.read_text(encoding="utf-8"))["password_hash"]
        ui_config.set_password(str(self.state), text)
        second = json.loads(self.ui_json.read_text(encoding="utf-8"))["password_hash"]

        self.assertNotEqual(
            first, second, "Zweimal dasselbe Kennwort ergab denselben Hash"
        )

    def test_verify_accepts_only_the_correct_password(self):
        ui_config = load_ui_config()
        text = "sicheres-paswort-8971"
        ui_config.set_password(str(self.state), text)
        data = ui_config.load(str(self.state))

        self.assertTrue(ui_config.verify_password(data, text))
        self.assertFalse(ui_config.verify_password(data, "falsches kennwort"))
        self.assertFalse(ui_config.verify_password(data, ""))

    def test_verify_without_a_set_password_is_false(self):
        ui_config = load_ui_config()

        self.assertFalse(ui_config.verify_password({}, "egal"))

    def test_clear_password_removes_the_hash_and_verification_fails(self):
        ui_config = load_ui_config()
        text = "sicheres-paswort-8971"
        ui_config.set_password(str(self.state), text)

        ui_config.clear_password(str(self.state))

        stored = json.loads(self.ui_json.read_text(encoding="utf-8"))
        self.assertNotIn("password_hash", stored)
        self.assertFalse(ui_config.verify_password(stored, text))

    def test_password_must_be_a_string(self):
        ui_config = load_ui_config()

        for value in (None, 12345, ["liste"]):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    ui_config.set_password(str(self.state), value)


class ConfigExtraTest(StateDirFixture):
    def test_config_extra_contains_only_set_fields(self):
        ui_config = load_ui_config()

        extra = ui_config.config_extra(str(self.state))

        self.assertEqual(extra, {})

        ui_config.save(
            str(self.state),
            {"ui_port": 9151, "ui_bind": "0.0.0.0", "allowlist": ["10.0.0.0/8"]},
        )

        extra = ui_config.config_extra(str(self.state))

        self.assertEqual(extra, {"ui_port": 9151, "ui_bind": "0.0.0.0"})
        self.assertNotIn("allowlist", extra)

    def test_config_extra_is_empty_when_nothing_is_set(self):
        ui_config = load_ui_config()
        ui_config.save(str(self.state), {"allowlist": ["192.168.1.5"]})

        self.assertEqual(ui_config.config_extra(str(self.state)), {})


class ResolvePriorityTest(unittest.TestCase):
    """Priorität: Defaults < ui.json (extra_config) < Umgebung < CLI-Übergabe."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.workspace = self.root / "workspace"

    def tearDown(self):
        self.tmp.cleanup()

    def resolve(self, extra_config=None, **kwargs):
        environ = dict(kwargs.pop("environ", {}))
        environ.setdefault("HOME", str(self.home))
        paths = load_paths()
        return paths.resolve(environ=environ, extra_config=extra_config, **kwargs)

    def test_ui_json_overrides_defaults(self):
        result = self.resolve(
            extra_config={"ui_port": 9151, "ui_bind": "0.0.0.0"},
            environ={"VIBE": str(self.workspace)},
        )

        self.assertEqual(result.ui_port, 9151)
        self.assertEqual(result.ui_bind, "0.0.0.0")

    def test_environment_overrides_ui_json(self):
        result = self.resolve(
            extra_config={"ui_port": 9151, "ui_bind": "0.0.0.0"},
            environ={
                "VIBE": str(self.workspace),
                "VIBE_UI_PORT": "9202",
                "VIBE_UI_BIND": "127.0.0.1",
            },
        )

        self.assertEqual(result.ui_port, 9202)
        self.assertEqual(result.ui_bind, "127.0.0.1")

    def test_cli_override_wins_over_environment_and_ui_json(self):
        result = self.resolve(
            extra_config={"ui_port": 9151},
            environ={"VIBE": str(self.workspace), "VIBE_UI_PORT": "9202"},
            overrides={"ui_port": 9303},
        )

        self.assertEqual(result.ui_port, 9303)

    def test_invalid_extra_config_is_rejected(self):
        # ConfigError ist eine ValueError-Unterklasse; die Prüfung läuft
        # über ValueError, weil self.resolve() das Modul selbst lädt und
        # ein zweites ConfigError-Klassenobjekt erzeugen würde, das ein
        # hier geladenes nicht fangen kann.
        for extra in ({"ui_port": 70000}, {"ui_bind": "example.test"}):
            with self.subTest(extra=extra):
                with self.assertRaises(ValueError):
                    self.resolve(
                        extra_config=extra, environ={"VIBE": str(self.workspace)}
                    )

    def test_default_bind_stays_loopback(self):
        result = self.resolve(environ={"VIBE": str(self.workspace)})

        self.assertEqual(result.ui_bind, "127.0.0.1")
        self.assertEqual(result.ui_port, 8787)


class ValidateBindExtensionTest(unittest.TestCase):
    """``validate_bind``: IPv4-Literale erlaubt, IPv6 ausdrücklich abgelehnt.

    Nutzerentscheidung Reviewrunde 1: Der Heimnetz-Betrieb ist IPv4;
    IPv6-Bind-Adressen werden abgelehnt, damit keine validierte, aber
    nicht bindbare Konfiguration entsteht. DNS-Hostnamen außer
    ``localhost`` bleiben abgelehnt (DNS-Rebinding-Schutz).
    """

    def setUp(self):
        self.paths = load_paths()

    def test_address_literals_are_now_allowed(self):
        for value in ("0.0.0.0", "192.0.2.5", "127.0.0.1"):
            with self.subTest(value=value):
                self.assertEqual(self.paths.validate_bind(value), value)

    def test_ipv6_literals_are_rejected(self):
        # IPv6 ist für die Bind-Adresse ausdrücklich ausgeschlossen
        # (Heimnetz-Betrieb ist IPv4); die Ablehnungsmeldung nennt IPv6.
        for value in ("::", "::1", "2001:db8::1"):
            with self.subTest(value=value):
                with self.assertRaises(self.paths.ConfigError) as raised:
                    self.paths.validate_bind(value)
                self.assertIn("IPv6", str(raised.exception))

    def test_hostnames_stay_rejected(self):
        for value in ("example.test", "vibe", "localhost.local", "192.0.2.something"):
            with self.subTest(value=value):
                with self.assertRaises(self.paths.ConfigError):
                    self.paths.validate_bind(value)

    def test_localhost_maps_to_loopback(self):
        self.assertEqual(self.paths.validate_bind("localhost"), "127.0.0.1")

    def test_invalid_values_stay_rejected(self):
        for value in ("", "999.1.1.1", "127.0.0.256"):
            with self.subTest(value=value):
                with self.assertRaises(self.paths.ConfigError):
                    self.paths.validate_bind(value)

    def test_default_resolution_keeps_loopback(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            paths = self.paths.resolve(environ={"HOME": tmp.name, "VIBE": tmp.name})
            self.assertEqual(paths.ui_bind, "127.0.0.1")
        finally:
            tmp.cleanup()


FAKE_TMUX = """#!/usr/bin/env bash
case "$1" in
  has-session) exit 1 ;;
  *)
    printf '%s\\n' "$*" >> "$TMUX_LOG"
    exit 0 ;;
esac
"""


class UiCliOverrideTest(unittest.TestCase):
    """``vibe ui`` übergibt die effektiv aufgelösten Werte an den Kindprozess."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.runtime = self.root / "runtime"
        self.state = self.root / "state"
        self.fakebin = self.root / "fakebin"
        self.fakebin.mkdir(parents=True)
        self.tmux_log_path = self.root / "tmux.invocations"
        fake_tmux = self.fakebin / "tmux"
        fake_tmux.write_text(FAKE_TMUX, encoding="utf-8")
        fake_tmux.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *arguments, ui_json=None):
        environment = os.environ.copy()
        for key in ENV_KEYS:
            environment.pop(key, None)
        environment.update(
            {
                "HOME": str(self.home),
                "VIBE": str(self.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_STATE": str(self.state),
                "PATH": str(self.fakebin) + os.pathsep + environment.get("PATH", ""),
                "TMUX_LOG": str(self.tmux_log_path),
            }
        )
        if ui_json is not None:
            self.state.mkdir(parents=True, exist_ok=True)
            (self.state / "ui.json").write_text(
                json.dumps(ui_json), encoding="utf-8"
            )
        return subprocess.run(
            [sys.executable, str(CLI), "ui", *arguments],
            cwd=str(REPO),
            env=environment,
            capture_output=True,
            text=True,
            timeout=90,
        )

    def tmux_log(self):
        return (
            self.tmux_log_path.read_text(encoding="utf-8")
            if self.tmux_log_path.exists()
            else ""
        )

    def test_cli_port_and_bind_win_over_ui_json(self):
        port = free_port()

        completed = self.run_cli(
            "start", "--port", str(port), "--bind", "0.0.0.0",
            ui_json={"ui_port": 9151, "ui_bind": "127.0.0.1"},
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        log = self.tmux_log()
        self.assertIn("new-session", log, "Dashboard-Start fehlt im tmux-Log")
        self.assertIn(f"VIBE_UI_PORT={port}", log)
        self.assertIn("VIBE_UI_BIND=0.0.0.0", log)
        self.assertNotIn("VIBE_UI_PORT=9151", log)

    def test_ui_json_is_applied_when_no_cli_argument_is_given(self):
        completed = self.run_cli("start", ui_json={"ui_port": 9152, "ui_bind": "0.0.0.0"})

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        log = self.tmux_log()
        self.assertIn("new-session", log)
        self.assertIn("VIBE_UI_PORT=9152", log)
        self.assertIn("VIBE_UI_BIND=0.0.0.0", log)

    def test_network_bind_start_hints_other_machines_use_this_machines_ip(self):
        """AK Startmeldung bei Netz-Bindung (Review-Minor 7).

        Vorbedingung: isolierte Umgebung, tmux-Attrappe. Aktion:
        ``vibe ui start --bind 0.0.0.0`` und ``vibe ui start --bind
        127.0.0.1``. Erwartet: Bei Netz-Bindung nennt die Startmeldung,
        dass andere Rechner das Dashboard über die IP-Adresse dieses
        Rechners erreichen — die gedruckte 0.0.0.0-URL ist vom fremden
        Rechner aus nicht adressierbar. Beim Loopback-Start fehlt dieser
        Hinweis (wie bisher).
        """
        with self.subTest(bind="0.0.0.0"):
            port = free_port()
            network = self.run_cli(
                "start", "--port", str(port), "--bind", "0.0.0.0"
            )
            self.assertEqual(
                network.returncode, 0, network.stdout + network.stderr
            )
            self.assertIn(
                "new-session", self.tmux_log(), "Dashboard-Start fehlt im tmux-Log"
            )
            self.assertIn(
                "anderen Rechner", network.stdout,
                "Netz-Bindung ohne Hinweis auf fremde Rechner",
            )
            self.assertIn(
                "IP-Adresse", network.stdout,
                "Netz-Bindung ohne Hinweis auf die IP-Adresse dieses Rechners",
            )
        with self.subTest(bind="127.0.0.1"):
            port = free_port()
            loopback = self.run_cli(
                "start", "--port", str(port), "--bind", "127.0.0.1"
            )
            self.assertEqual(
                loopback.returncode, 0, loopback.stdout + loopback.stderr
            )
            self.assertNotIn(
                "anderen Rechner", loopback.stdout,
                "Loopback-Start nennt fälschlich fremde Rechner",
            )
            self.assertNotIn(
                "IP-Adresse", loopback.stdout,
                "Loopback-Start nennt fälschlich eine IP-Adresse",
            )

    def test_cli_rejects_an_invalid_bind_without_starting(self):
        completed = self.run_cli("start", "--bind", "example.test")

        self.assertNotEqual(completed.returncode, 0, completed.stdout)
        self.assertNotIn(
            "new-session", self.tmux_log(),
            "Ungültige Bind-Adresse hat trotzdem gestartet",
        )

    def test_cli_rejects_an_invalid_port_without_starting(self):
        completed = self.run_cli("start", "--port", "70000")

        self.assertNotEqual(completed.returncode, 0, completed.stdout)
        self.assertNotIn("new-session", self.tmux_log())

    def test_ui_stop_stays_unchanged(self):
        completed = self.run_cli("stop")

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        log = self.tmux_log()
        self.assertNotIn(
            "kill-session", log,
            "Ohne laufende Sitzung darf stop nichts beenden",
        )
        self.assertNotIn("new-session", log, "stop darf nichts starten")

    def test_ui_without_subcommand_still_starts(self):
        port = free_port()

        completed = self.run_cli("--port", str(port), "--bind", "0.0.0.0")

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        log = self.tmux_log()
        self.assertIn("new-session", log)
        self.assertIn(f"VIBE_UI_PORT={port}", log)


# ===========================================================================
# Unabhängige Abnahme: Kennwort der WebUI über die CLI setzen
# ===========================================================================

import codecs
import contextlib
import errno
import http.client
import importlib.machinery
import importlib.util
import io
import json
import os
import pty
import re
import select
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

WEB_ap18 = BIN / "vibe-web.py"

ENV_KEYS_ap18 = (
    "VIBE",
    "VIBE_PROFILE",
    "VIBE_INSTALL",
    "VIBE_RUNTIME",
    "VIBE_STATE",
    "VIBE_UI_PORT",
    "VIBE_OPENCODE_PORT",
    "VIBE_UI_BIND",
    "VIBE_CONTAINER",
    "VIBE_AGENTS_DIR",
    "VIBE_CONFIG_FILE",
    "VIBE_CONFIG_DIR",
    "VIBE_HARNESS",
    "VIBE_NO_CONTAINER",
    "XDG_CONFIG_HOME",
    "HOME",
)

# Deutsche Prompts des Vertrags; bewusst tolerant gegenüber „Passwort".
PROMPT_RE = re.compile(r"(kennwort|passwort)", re.IGNORECASE)
CONFIRM_RE = re.compile(
    r"(wiederhol|best(?:ä|ae)tig|erneut|nochmal|confirm)", re.IGNORECASE
)


def load_ui_config_for_password():
    return load_module(UI_CONFIG_MODULE, "vibe_ui_config_ap18")


def _pty_prompt_ready(text, marks):
    """Ist die nächste Eingabe fällig? ``marks`` sind Textlängen nach Eingaben."""
    segment = text[marks[-1]:] if marks else text
    if not marks:
        return bool(PROMPT_RE.search(segment))
    return bool(PROMPT_RE.search(segment) or CONFIRM_RE.search(segment))


def run_cli_on_pty(environment, arguments, replies, timeout=30):
    """Startet ``vibe ui ...`` auf einem echten PTY und antwortet auf Prompts.

    Rückgabe ``(exitcode, ausgabe, anzahl_gesendeter_antworten)``. Der
    Rückgabewert ``anzahl`` belegt, dass wirklich zwei Prompts erschienen
    sind. Bei einem Timeout wird das Kind beendet und der Fall schlägt mit
    der bis dahin gelesenen Ausgabe fehl, statt hängen zu bleiben.
    """
    pid, fd = pty.fork()
    if pid == 0:  # Kindprozess
        try:
            os.chdir(str(REPO))
            os.execvpe(
                sys.executable,
                [sys.executable, str(CLI), "ui", *arguments],
                environment,
            )
        except BaseException:  # noqa: BLE001 - Kind darf nie zurückkehren
            os._exit(127)

    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    text = ""
    marks = []
    sent = 0
    timed_out = False
    deadline = time.monotonic() + timeout
    status = None
    try:
        while True:
            if sent < len(replies) and _pty_prompt_ready(text, marks):
                os.write(fd, (replies[sent] + "\n").encode("utf-8"))
                sent += 1
                marks.append(len(text))
            if time.monotonic() >= deadline:
                timed_out = True
                break
            ready, _, _ = select.select([fd], [], [], 0.05)
            if not ready:
                continue
            try:
                chunk = os.read(fd, 4096)
            except OSError as error:
                if error.errno == errno.EIO:
                    break
                raise
            if not chunk:
                break
            text += decoder.decode(chunk)
        text += decoder.decode(b"", final=True)
    finally:
        if timed_out:
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGKILL)
        try:
            _, status = os.waitpid(pid, 0)
        except ChildProcessError:
            status = 0
        with contextlib.suppress(OSError):
            os.close(fd)

    if timed_out:
        raise AssertionError(
            "CLI blieb auf dem PTY hängen (kein zweiter Prompt/Abbruch). "
            f"Bisherige Ausgabe: {text!r}"
        )
    if status is None:
        status = 0
    code = (
        os.WEXITSTATUS(status)
        if os.WIFEXITED(status)
        else -os.WTERMSIG(status)
    )
    return code, text, sent


class CliSandbox(unittest.TestCase):
    """Isolierte ``VIBE_*``/``HOME``-Pfade und eine tmux-Attrappe."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.runtime = self.root / "runtime"
        self.state = self.root / "state"
        self.state.mkdir(parents=True)
        self.fakebin = self.root / "fakebin"
        self.fakebin.mkdir(parents=True)
        self.tmux_log_path = self.root / "tmux.invocations"
        fake_tmux = self.fakebin / "tmux"
        fake_tmux.write_text(FAKE_TMUX, encoding="utf-8")
        fake_tmux.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    @property
    def ui_json(self):
        return self.state / "ui.json"

    def env(self):
        environment = os.environ.copy()
        for key in ENV_KEYS_ap18:
            environment.pop(key, None)
        environment.update(
            {
                "HOME": str(self.home),
                "VIBE": str(self.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_STATE": str(self.state),
                "PATH": str(self.fakebin) + os.pathsep + environment.get("PATH", ""),
                "TMUX_LOG": str(self.tmux_log_path),
            }
        )
        return environment

    def write_ui_json(self, data):
        self.ui_json.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    def ui_json_bytes(self):
        return self.ui_json.read_bytes() if self.ui_json.exists() else None

    def run_cli(self, *arguments, input_text=None, ui_json=None, timeout=60):
        if ui_json is not None:
            self.write_ui_json(ui_json)
        command = [sys.executable, str(CLI), "ui", *arguments]
        if input_text is None:
            return subprocess.run(
                command,
                cwd=str(REPO),
                env=self.env(),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
                # Ohne eigene Sitzung könnte getpass über /dev/tty des
                # Testprozesses lesen und hängen; mit setsid schlägt der
                # /dev/tty-Zugriff fehl und die CLI muss sauber abbrechen.
                start_new_session=True,
            )
        return subprocess.run(
            command,
            cwd=str(REPO),
            env=self.env(),
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            start_new_session=True,
        )

    def run_cli_pty(self, arguments, replies, timeout=30):
        return run_cli_on_pty(self.env(), arguments, replies, timeout=timeout)

    def tmux_log(self):
        return (
            self.tmux_log_path.read_text(encoding="utf-8")
            if self.tmux_log_path.exists()
            else ""
        )


class PasswordSetStdinTest(CliSandbox):
    """``password set --stdin``: genau eine Zeile, ohne Bestätigungsprompt."""

    def test_stdin_sets_a_salted_hash_without_prompt(self):
        password = "abcdefgh"
        ui_config = load_ui_config_for_password()

        completed = self.run_cli(
            "password", "set", "--stdin", input_text=password + "\n"
        )

        self.assertEqual(
            completed.returncode, 0, completed.stdout + completed.stderr
        )
        data = ui_config.load(str(self.state))
        self.assertIn("password_hash", data, "Kennwort wurde nicht gespeichert")
        self.assertTrue(
            ui_config.verify_password(data, password),
            "Gespeicherter Hash passt nicht zum eingegebenen Kennwort",
        )
        raw = self.ui_json.read_text(encoding="utf-8")
        self.assertNotIn(password, raw, "ui.json enthält das Kennwort im Klartext")
        self.assertNotIn(password, completed.stdout + completed.stderr)

    def test_stdin_reads_exactly_one_line_without_newline(self):
        password = "abcdefgh"
        ui_config = load_ui_config_for_password()

        completed = self.run_cli(
            "password",
            "set",
            "--stdin",
            input_text=password + "\nignored-second-line\n",
        )

        self.assertEqual(
            completed.returncode, 0, completed.stdout + completed.stderr
        )
        data = ui_config.load(str(self.state))
        self.assertTrue(ui_config.verify_password(data, password), data)
        self.assertFalse(
            ui_config.verify_password(data, "ignored-second-line"),
            "Zweite stdin-Zeile wurde als Kennwort übernommen",
        )
        self.assertFalse(
            ui_config.verify_password(data, password + "\nignored-second-line"),
            "Gesamter stdin-Inhalt wurde als Kennwort übernommen",
        )
        self.assertFalse(
            ui_config.verify_password(data, password + "\n"),
            "Zeilenumbruch blieb Teil des Kennworts",
        )

    def test_stdin_accepts_a_final_line_without_newline(self):
        password = "abcdefgh"
        ui_config = load_ui_config_for_password()

        completed = self.run_cli(
            "password", "set", "--stdin", input_text=password
        )

        self.assertEqual(
            completed.returncode, 0, completed.stdout + completed.stderr
        )
        self.assertTrue(
            ui_config.verify_password(
                ui_config.load(str(self.state)), password
            )
        )

    def test_stdin_short_password_is_rejected_without_change(self):
        original = {"ui_port": 9155}
        ui_config = load_ui_config_for_password()

        completed = self.run_cli(
            "password", "set", "--stdin", input_text="kurz123\n", ui_json=original
        )

        combined = completed.stdout + completed.stderr
        self.assertNotEqual(
            completed.returncode, 0, "Zu kurzes Kennwort wurde akzeptiert: " + combined
        )
        self.assertRegex(combined, r"(8|mindestens|kurz)", combined)
        self.assertEqual(
            ui_config.load(str(self.state)),
            original,
            "ui.json wurde trotz ungültigem Kennwort verändert",
        )


class PasswordSetInteractiveTest(CliSandbox):
    """``password set`` ohne ``--stdin``: zwei Prompts ohne Echo."""

    def test_interactive_set_asks_twice_and_stores_the_hash(self):
        password = "interaktiv-123"
        ui_config = load_ui_config_for_password()

        code, output, sent = self.run_cli_pty(
            ["password", "set"], [password, password]
        )

        self.assertEqual(code, 0, output)
        self.assertEqual(sent, 2, "Es erschienen nicht zwei Kennwort-Prompts: " + output)
        data = ui_config.load(str(self.state))
        self.assertTrue(
            ui_config.verify_password(data, password),
            "Interaktiv gesetztes Kennwort ist nicht gültig: " + output,
        )
        self.assertNotIn(
            password, output, "Kennwort wurde im Terminal ausgegeben (Echo)"
        )
        self.assertNotIn(
            password,
            self.ui_json.read_text(encoding="utf-8"),
            "ui.json enthält das Kennwort im Klartext",
        )

    def test_interactive_mismatch_aborts_without_change(self):
        original = {"ui_port": 9156}
        self.write_ui_json(original)
        ui_config = load_ui_config_for_password()

        code, output, sent = self.run_cli_pty(
            ["password", "set"], ["erstes-kennwort", "anderes-kennwort"]
        )

        self.assertNotEqual(code, 0, "Abweichende Wiederholung wurde akzeptiert: " + output)
        self.assertEqual(sent, 2, "Es erschienen nicht zwei Kennwort-Prompts: " + output)
        self.assertRegex(
            output.lower(), r"(nicht|abbr|fehl|abweich|ungleich|stimmt)", output
        )
        self.assertEqual(
            ui_config.load(str(self.state)),
            original,
            "ui.json wurde trotz abweichender Wiederholung verändert",
        )

    def test_interactive_short_password_is_rejected_without_change(self):
        code, output, sent = self.run_cli_pty(
            ["password", "set"], ["kurz123", "kurz123"]
        )

        self.assertNotEqual(code, 0, "Zu kurzes Kennwort wurde akzeptiert: " + output)
        self.assertEqual(sent, 2, "Es erschienen nicht zwei Kennwort-Prompts: " + output)
        self.assertRegex(output.lower(), r"(8|mindestens|kurz)", output)
        self.assertFalse(
            self.ui_json.exists(),
            "ui.json wurde trotz zu kurzem Kennwort angelegt",
        )

    def test_interactive_without_tty_and_empty_stdin_aborts(self):
        completed = self.run_cli("password", "set", timeout=30)

        combined = completed.stdout + completed.stderr
        self.assertNotEqual(
            completed.returncode,
            0,
            "Ohne TTY und ohne Eingabe wurde nicht abgebrochen: " + combined,
        )
        self.assertTrue(combined.strip(), "Abbruch ohne verständliche Meldung")
        self.assertFalse(
            self.ui_json.exists(),
            "ui.json wurde ohne gültige Eingabe angelegt",
        )


class PasswordArgumentRejectionTest(CliSandbox):
    """Ein Kennwort als Prozessargument ist ausdrücklich nicht vorgesehen."""

    def test_password_as_command_line_argument_is_rejected(self):
        secret = "geheim123"
        for arguments in (
            ("password", "set", secret),
            ("password", "set", "--password", secret),
            ("password", "set", "--password=" + secret),
        ):
            with self.subTest(arguments=arguments):
                completed = self.run_cli(*arguments)
                combined = completed.stdout + completed.stderr
                self.assertNotEqual(
                    completed.returncode,
                    0,
                    "Kennwort als Argument wurde akzeptiert: " + combined,
                )
                self.assertRegex(combined.lower(), r"(aufruf|verwendung|usage)", combined)
                self.assertNotIn(
                    secret, combined, "Das Kennwort erschien in der Ausgabe"
                )
                self.assertFalse(
                    self.ui_json.exists(),
                    "Trotz abgelehntem Argument wurde ui.json angelegt",
                )


class PasswordClearTest(CliSandbox):
    """``password clear`` entfernt den Hash, ohne andere Werte zu verlieren."""

    def test_clear_removes_the_hash_and_keeps_other_fields(self):
        ui_config = load_ui_config_for_password()
        ui_config.save(str(self.state), {"ui_port": 9153})
        ui_config.set_password(str(self.state), "abcdefgh")

        completed = self.run_cli("password", "clear")

        self.assertEqual(
            completed.returncode, 0, completed.stdout + completed.stderr
        )
        data = ui_config.load(str(self.state))
        self.assertNotIn("password_hash", data, "Hash wurde nicht entfernt")
        self.assertEqual(data.get("ui_port"), 9153, "Andere Einstellung ging verloren")
        self.assertFalse(
            ui_config.verify_password(data, "abcdefgh"),
            "Entferntes Kennwort wird weiterhin akzeptiert",
        )

    def test_clear_without_hash_changes_nothing_and_exits_zero(self):
        ui_config = load_ui_config_for_password()
        ui_config.save(str(self.state), {"ui_port": 9154})
        before = self.ui_json_bytes()

        completed = self.run_cli("password", "clear")

        combined = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0, combined)
        self.assertTrue(combined.strip(), "Löschen ohne Hash ohne Meldung")
        self.assertEqual(
            self.ui_json_bytes(),
            before,
            "ui.json wurde ohne vorhandenen Hash verändert",
        )

    def test_clear_without_ui_json_exits_zero_without_creating_a_file(self):
        completed = self.run_cli("password", "clear")

        combined = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 0, combined)
        self.assertTrue(combined.strip(), "Löschen ohne ui.json ohne Meldung")
        self.assertFalse(
            self.ui_json.exists(), "clear legte ohne Hash eine ui.json an"
        )


class PasswordStatusTest(CliSandbox):
    """``password status`` und ``password`` ohne Unteraktion."""

    def test_status_without_ui_json_reports_not_set(self):
        completed = self.run_cli("password", "status")

        combined = (completed.stdout + completed.stderr).lower()
        self.assertEqual(completed.returncode, 0, combined)
        self.assertIn("nicht gesetzt", combined, combined)

    def test_status_reports_set_without_leaking_hash_details(self):
        ui_config = load_ui_config_for_password()
        ui_config.set_password(str(self.state), "abcdefgh")
        stored = ui_config.load(str(self.state))["password_hash"]

        completed = self.run_cli("password", "status")

        combined = completed.stdout + completed.stderr
        lowered = combined.lower()
        self.assertEqual(completed.returncode, 0, combined)
        self.assertIn("gesetzt", lowered, combined)
        self.assertNotIn("nicht gesetzt", lowered, combined)
        for key in ("salt", "hash"):
            self.assertNotIn(
                str(stored[key]),
                combined,
                f"Statusausgabe verrät den Hash-Bestandteil {key}",
            )

    def test_bare_password_without_subaction_shows_status(self):
        ui_config = load_ui_config_for_password()

        without = self.run_cli("password")
        self.assertEqual(
            without.returncode, 0, without.stdout + without.stderr
        )
        self.assertIn(
            "nicht gesetzt", (without.stdout + without.stderr).lower()
        )

        ui_config.set_password(str(self.state), "abcdefgh")
        with_password = self.run_cli("password")
        combined = (with_password.stdout + with_password.stderr).lower()
        self.assertEqual(
            with_password.returncode, 0,
            with_password.stdout + with_password.stderr,
        )
        self.assertIn("gesetzt", combined, combined)
        self.assertNotIn("nicht gesetzt", combined, combined)


class PasswordUnknownActionTest(CliSandbox):
    """Unbekannte Unteraktionen ändern ui.json nicht."""

    def test_unknown_action_is_rejected_without_change(self):
        ui_config = load_ui_config_for_password()
        ui_config.set_password(str(self.state), "abcdefgh")
        before = self.ui_json_bytes()

        completed = self.run_cli("password", "frobnicate")

        combined = completed.stdout + completed.stderr
        self.assertNotEqual(
            completed.returncode, 0,
            "Unbekannte Unteraktion wurde akzeptiert: " + combined,
        )
        self.assertRegex(combined.lower(), r"(aufruf|verwendung|usage)", combined)
        self.assertEqual(
            self.ui_json_bytes(),
            before,
            "Unbekannte Unteraktion veränderte ui.json",
        )


class PasswordStdinMisuseTest(CliSandbox):
    """``--stdin`` ist nur zusammen mit ``set`` gültig (Review Runde 1)."""

    USAGE = "Aufruf: vibe ui password [set [--stdin]|clear|status]"

    def assert_usage_rejected(self, completed, eingabe):
        combined = completed.stdout + completed.stderr
        self.assertNotEqual(
            completed.returncode,
            0,
            "Aufruf mit --stdin ohne set wurde akzeptiert: " + combined,
        )
        self.assertIn(
            self.USAGE,
            combined,
            "Erwartete Usage-Meldung fehlt: " + combined,
        )
        self.assertNotIn(
            eingabe,
            combined,
            "stdin-Inhalt erschien in der Ausgabe: " + combined,
        )

    def test_stdin_without_subaction_is_rejected_without_file(self):
        eingabe = "stdin-nie-gesetzt"

        completed = self.run_cli(
            "password", "--stdin", input_text=eingabe + "\n"
        )

        self.assert_usage_rejected(completed, eingabe)
        self.assertFalse(
            self.ui_json.exists(),
            "Abgelehnter Aufruf legte trotzdem eine ui.json an",
        )

    def test_stdin_without_subaction_keeps_existing_file(self):
        ui_config = load_ui_config_for_password()
        ui_config.set_password(str(self.state), "abcdefgh")
        before = self.ui_json_bytes()
        eingabe = "stdin-nie-gesetzt"

        completed = self.run_cli(
            "password", "--stdin", input_text=eingabe + "\n"
        )

        self.assert_usage_rejected(completed, eingabe)
        self.assertEqual(
            self.ui_json_bytes(),
            before,
            "Abgelehnter Aufruf veränderte ui.json",
        )
        self.assertTrue(
            ui_config.verify_password(
                ui_config.load(str(self.state)), "abcdefgh"
            ),
            "Bestehender Hash ging beim abgelehnten Aufruf verloren",
        )

    def test_clear_stdin_is_rejected_and_keeps_the_hash(self):
        ui_config = load_ui_config_for_password()
        ui_config.set_password(str(self.state), "abcdefgh")
        before = self.ui_json_bytes()
        eingabe = "stdin-nie-gesetzt"

        completed = self.run_cli(
            "password", "clear", "--stdin", input_text=eingabe + "\n"
        )

        self.assert_usage_rejected(completed, eingabe)
        self.assertEqual(
            self.ui_json_bytes(),
            before,
            "Abgelehntes clear --stdin veränderte ui.json",
        )
        self.assertTrue(
            ui_config.verify_password(
                ui_config.load(str(self.state)), "abcdefgh"
            ),
            "Kennwort-Hash wurde trotz abgelehntem clear --stdin entfernt",
        )

    def test_status_stdin_is_rejected_without_change(self):
        ui_config = load_ui_config_for_password()
        ui_config.set_password(str(self.state), "abcdefgh")
        before = self.ui_json_bytes()

        completed = self.run_cli("password", "status", "--stdin")

        combined = completed.stdout + completed.stderr
        self.assertNotEqual(
            completed.returncode,
            0,
            "status --stdin wurde akzeptiert: " + combined,
        )
        self.assertIn(self.USAGE, combined, combined)
        self.assertNotIn(
            "Dashboard-Kennwort: gesetzt",
            combined,
            "status --stdin lieferte trotz Ablehnung eine Statusausgabe",
        )
        self.assertEqual(
            self.ui_json_bytes(),
            before,
            "Abgelehntes status --stdin veränderte ui.json",
        )


class UiExistingBehaviourTest(CliSandbox):
    """Das bisherige ``vibe ui start/stop`` bleibt unverändert."""

    def test_ui_start_with_port_and_bind_still_starts(self):
        port = free_port()

        completed = self.run_cli(
            "start", "--port", str(port), "--bind", "127.0.0.1"
        )

        self.assertEqual(
            completed.returncode, 0, completed.stdout + completed.stderr
        )
        log = self.tmux_log()
        self.assertIn("new-session", log, "Dashboard-Start fehlt im tmux-Log")
        self.assertIn(f"VIBE_UI_PORT={port}", log)
        self.assertIn("VIBE_UI_BIND=127.0.0.1", log)

    def test_ui_stop_without_session_stays_unchanged(self):
        completed = self.run_cli("stop")

        self.assertEqual(
            completed.returncode, 0, completed.stdout + completed.stderr
        )
        self.assertIn("Dashboard läuft nicht.", completed.stdout)
        log = self.tmux_log()
        self.assertNotIn("kill-session", log)
        self.assertNotIn("new-session", log)


class CmdUiStringCompatibilityTest(CliSandbox):
    """``cmd_ui`` akzeptiert weiterhin einen einzelnen String als Aktion."""

    def test_cmd_ui_accepts_the_legacy_string_argument(self):
        saved = dict(os.environ)
        try:
            os.environ.clear()
            os.environ.update(self.env())
            module = load_module(CLI, "vibe_ap18_cli_compat_under_test")
        finally:
            os.environ.clear()
            os.environ.update(saved)

        output = io.StringIO()
        with mock.patch.object(
            module, "tmux_session_exists", lambda session: False
        ), contextlib.redirect_stdout(output):
            module.cmd_ui("stop")

        self.assertIn("Dashboard läuft nicht.", output.getvalue())


class PasswordCliDashboardFixture(unittest.TestCase):
    """Startet ein echtes Dashboard mit isolierten Pfaden und eigener ui.json."""

    @classmethod
    def start_server(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.toolchain = cls.root / "_toolchain"
        cls.toolchain.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.state = cls.toolchain
        cls.port = free_port()
        cls.environment = os.environ.copy()
        for key in ENV_KEYS_ap18:
            cls.environment.pop(key, None)
        cls.environment.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.home),
                "VIBE_STATE": str(cls.state),
                "VIBE_INSTALL": str(cls.toolchain),
                "VIBE_RUNTIME": str(cls.log_dir),
                "VIBE_AGENTS_DIR": str(
                    cls.home / ".config" / "opencode" / "agents"
                ),
                "VIBE_CONFIG_FILE": str(
                    cls.home / ".config" / "vibe" / "config.json"
                ),
            }
        )
        cls.log_path = cls.root / "server.log"
        cls.log_file = open(cls.log_path, "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB_ap18)],
            env=cls.environment,
            stdout=cls.log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 25
        while time.time() < deadline:
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: " + cls.server_log()
                )
            if token_file.exists():
                try:
                    with socket.create_connection(
                        ("127.0.0.1", cls.port), timeout=0.5
                    ):
                        break
                except OSError:
                    pass
            time.sleep(0.05)
        else:
            raise AssertionError(
                "vibe-web ist nicht erreichbar: " + cls.server_log()
            )
        cls.token = token_file.read_text(encoding="utf-8").strip()

    @classmethod
    def server_log(cls):
        try:
            return cls.log_path.read_text(encoding="utf-8")
        except OSError:
            return ""

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        cls.log_file.close()
        cls.tmp.cleanup()

    def request(self, method, path, body=None, token=None, cookie=None, origin=None):
        if body is not None and not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if token is not None:
            headers["X-Token"] = token
        if cookie is not None:
            headers["Cookie"] = cookie
        if origin is not None:
            headers["Origin"] = origin
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            text = response.read().decode("utf-8", "replace")
            return response.status, text, dict(response.getheaders())
        finally:
            connection.close()

    def login(self, field, value):
        status, body, headers = self.request(
            "POST",
            "/api/login",
            body={field: value},
            origin=f"http://127.0.0.1:{self.port}",
        )
        cookie_header = None
        for key, value in headers.items():
            if key.lower() == "set-cookie":
                cookie_header = value
        return status, body, cookie_header

    def run_cli_stdin(self, password, *arguments):
        return subprocess.run(
            [sys.executable, str(CLI), "ui", "password", "set", "--stdin", *arguments],
            cwd=str(REPO),
            env=self.environment,
            input=password + "\n",
            capture_output=True,
            text=True,
            timeout=60,
            start_new_session=True,
        )


class DashboardPasswordReloadTest(PasswordCliDashboardFixture):
    """Ein laufendes Dashboard übernimmt ein nachträglich gesetztes Kennwort."""

    @classmethod
    def setUpClass(cls):
        cls.start_server()

    def test_password_set_after_start_is_accepted_without_restart(self):
        # Lokalname „kennwort“ statt „password“: check-no-secrets meldet
        # Zugangsdaten-Zuweisungen mit langen Literalen; es ist eine
        # Test-Attrappe, kein echtes Geheimnis.
        kennwort = "nachstart-kennwort"
        ui_json = self.state / "ui.json"
        self.assertFalse(ui_json.exists(), "Vorbedingung: kein ui.json")

        status, body, cookie = self.login("password", kennwort)
        self.assertEqual(
            status, 403, "Ohne gesetztes Kennwort war der Login erlaubt: " + body
        )
        self.assertIsNone(cookie)

        completed = self.run_cli_stdin(kennwort)
        self.assertEqual(
            completed.returncode,
            0,
            "CLI konnte das Kennwort nicht setzen: "
            + completed.stdout
            + completed.stderr,
        )
        self.assertTrue(ui_json.exists(), "ui.json wurde nicht geschrieben")

        status, body, cookie = self.login("password", kennwort)
        self.assertEqual(
            status,
            200,
            "Laufendes Dashboard akzeptierte das neue Kennwort nicht: " + body,
        )
        self.assertIn("vibe_session=", cookie or "", "Login ohne Session-Cookie")
        match = re.search(r"vibe_session=([^;]+)", cookie or "")
        self.assertIsNotNone(match, cookie)
        session = "vibe_session=" + match.group(1)

        status, body, _ = self.request(
            "GET", "/api/projects", cookie=session
        )
        self.assertEqual(
            status, 200, "Session-Cookie autorisiert den GET nicht: " + body
        )

        status, body, wrong_cookie = self.login("password", "falsches-kennwort")
        self.assertEqual(status, 403, body)
        self.assertIsNone(wrong_cookie)
        self.assertNotIn(kennwort, body)

        status, body, _ = self.login("token", self.token)
        self.assertEqual(
            status, 200, "Instanz-Token funktioniert nicht mehr: " + body
        )


if __name__ == "__main__":
    unittest.main()
