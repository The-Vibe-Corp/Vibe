"""Tests für die Absicherung der Web-API und den Health-Endpunkt (V-004).

Das Dashboard wird als eigener Prozess mit temporärem VIBE/HOME und freiem Port
gestartet. Geprüft werden die tatsächlichen HTTP-Antworten:

* Health ist ohne Token lesbar, nennt vibe und die konkrete Instanz und gibt
  weder Token noch andere Geheimnisse aus.
* Alle übrigen API-Routen verlangen ein gültiges Token; Schreibzugriffe
  zusätzlich einen Loopback-Host und einen passenden Origin.
* Fehler sind strukturiert (``error.code`` und ``error.message``).
* Ungültiges JSON, fremde Content-Types, fehlende Content-Length und zu große
  Anfragen werden abgelehnt, ohne den Zustand zu verändern.
* Parallele Anfragen werden getrennt geprüft.
* Zugriffslogs enthalten den Pfad, aber nie das Token.
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
        env = os.environ.copy()
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
        for host in ("vibe.example", "127.0.0.1.evil.example", "192.0.2.10"):
            with self.subTest(host=host):
                status, body, _ = self.request(
                    "GET", "/api/health", token=False, host=host
                )
                self.assertEqual(status, 403, body)
                error = json.loads(body)["error"]
                self.assertEqual(error["code"], "forbidden_host")
                self.assertTrue(error["message"])


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
        tmp = tempfile.TemporaryDirectory()
        try:
            root = Path(tmp.name)
            port = free_port()
            env = os.environ.copy()
            env.update(
                {
                    "VIBE": str(root),
                    "VIBE_NO_CONTAINER": "1",
                    "VIBE_UI_PORT": str(port),
                    "VIBE_UI_BIND": "0.0.0.0",
                    "HOME": str(root / "home"),
                }
            )
            result = subprocess.run(
                [sys.executable, str(WEB)],
                env=env,
                capture_output=True,
                text=True,
                timeout=20,
            )
            output = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0, output)
            self.assertIn("Loopback", output)
            self.assertFalse((root / "_logs" / "web.token").exists())
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
