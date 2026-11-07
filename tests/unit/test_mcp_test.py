"""Tests für robuste und begrenzte MCP-Verbindungstests (V-014).

Geprüft werden die Akzeptanzkriterien aus TICKETS.md:

* Der Test führt nur ``initialize`` und ``tools/list`` aus, nie ``tools/call``.
* Unterstützte Transporte (local/stdio und remote/Streamable HTTP) werden
  ausgewiesen; unbekannte Transporte gelten nicht als defekter Server.
* OAuth-Grenzen sind sichtbar: vibe meldet sich nicht an und liest keine
  Tokens.
* Vor dem Test wird auf gestartete Programme beziehungsweise
  Netzverbindungen hingewiesen.
* Zeit-, Ausgabe- und Werkzeuglisten sind begrenzt.
* Prozesse werden samt gestarteter Kindprozesse beendet.
* Fehler werden getrennt (Programm, Timeout, HTTP, Authentisierung, Protokoll,
  Konfiguration) und enthalten keine Geheimnisse.

Alle Server sind lokale Attrappen in temporären Verzeichnissen. Es werden
keine echten MCP-Server, opencode-Dienste oder Modellanbieter aufgerufen.
"""
import importlib.machinery
import importlib.util
import json
import os
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
MCP = BIN / "vibe_mcp.py"

INIT_RESULT = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "protocolVersion": "2025-03-26",
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "mock", "version": "1.0"},
    },
}


def load_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class McpTestFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.vibe_root = self.root / "vibe"
        self.vibe_root.mkdir()
        (self.vibe_root / "_toolchain").mkdir()
        self.env = mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.home),
                "VIBE": str(self.vibe_root),
                "VIBE_NO_CONTAINER": "1",
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tmp.cleanup)
        self.cli = load_module(CLI, "vibe_mcp_test_cli_under_test")
        old_vibe = sys.modules.get("vibe")
        sys.modules["vibe"] = self.cli
        self.addCleanup(self._restore_vibe, old_vibe)
        self.mcp = load_module(MCP, "vibe_mcp_test_under_test")

    @staticmethod
    def _restore_vibe(old_vibe):
        if old_vibe is None:
            sys.modules.pop("vibe", None)
        else:
            sys.modules["vibe"] = old_vibe

    def write_server(self, body, name="fake-mcp.py"):
        path = self.root / name
        path.write_text(body, encoding="utf-8")
        return path

    def local_entry(self, script, **extra):
        entry = {
            "type": "local",
            "command": [sys.executable, str(script)],
            "timeout": 10000,
        }
        entry.update(extra)
        return entry

    def start_http(self, handler):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def stop():
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.addCleanup(stop)
        return "http://127.0.0.1:%d/mcp" % server.server_port


class LocalHandshakeTest(McpTestFixture):
    def test_handshake_reports_tools_and_never_calls_a_tool(self):
        log = self.root / "methods.json"
        server = self.write_server(
            "import json, os, sys\n"
            "methods = []\n"
            "for line in sys.stdin:\n"
            "    message = json.loads(line)\n"
            "    methods.append(message.get('method'))\n"
            "    open(os.environ['METHOD_LOG'], 'w', encoding='utf-8').write("
            "json.dumps(methods))\n"
            "    if message.get('method') == 'initialize':\n"
            "        print(json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {"
            "'protocolVersion': '2025-03-26', 'capabilities': {'tools': {}}, "
            "'serverInfo': {'name': 'mock', 'version': '1.0'}}}), flush=True)\n"
            "    elif message.get('method') == 'tools/list':\n"
            "        print(json.dumps({'jsonrpc': '2.0', 'id': 2, 'result': {"
            "'tools': [{'name': 'ping', 'description': 'Ping-Werkzeug'}]}}), "
            "flush=True)\n"
        )
        entry = self.local_entry(server, environment={"METHOD_LOG": str(log)})

        result = self.mcp.test_local(entry, str(self.root))

        self.assertTrue(result["ok"], result)
        self.assertEqual([tool["name"] for tool in result["tools"]], ["ping"])
        self.assertIn("local", result["transport"])
        self.assertIn("stdio", result["transport"])
        self.assertTrue(result["warning"], "Startwarnung fehlt")
        self.assertIn("tools/call", " ".join(result["notes"]))
        self.assertGreaterEqual(result["limits"]["tools"], len(result["tools"]))
        methods = json.loads(log.read_text(encoding="utf-8"))
        self.assertIn("initialize", methods)
        self.assertIn("tools/list", methods)
        self.assertNotIn("tools/call", methods)

    def test_large_output_is_bounded_and_still_yields_the_handshake(self):
        tools = [{"name": "werkzeug-%d" % i, "description": "x" * 400} for i in range(500)]
        server = self.write_server(
            "import json, sys\n"
            "sys.stderr.write('x' * 1024 * 1024)\n"
            "sys.stderr.flush()\n"
            "sys.stdout.write('x' * 1024 * 1024 + '\\n')\n"
            "sys.stdout.flush()\n"
            "tools = %r\n"
            "for line in sys.stdin:\n"
            "    message = json.loads(line)\n"
            "    if message.get('method') == 'initialize':\n"
            "        print(json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {"
            "'protocolVersion': '2025-03-26', 'serverInfo': {'name': 'gross'}}}), "
            "flush=True)\n"
            "    elif message.get('method') == 'tools/list':\n"
            "        print(json.dumps({'jsonrpc': '2.0', 'id': 2, 'result': {"
            "'tools': tools}}), flush=True)\n" % (tools,)
        )
        entry = self.local_entry(server)

        result = self.mcp.test_local(entry, str(self.root))

        self.assertTrue(result["ok"], result)
        self.assertLessEqual(len(result["tools"]), result["limits"]["tools"])
        self.assertTrue(
            any("begrenzt" in step for step in result["steps"]),
            "Die Begrenzung der Werkzeugliste wird nicht ausgewiesen: %r" % result,
        )
        self.assertLessEqual(len(result["hint"]), 2000)

    def test_child_processes_are_terminated_with_the_test(self):
        pid_file = self.root / "child.pid"
        server = self.write_server(
            "import json, os, subprocess, sys\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; "
            "time.sleep(300)'])\n"
            "open(os.environ['CHILD_PID'], 'w', encoding='utf-8').write(str(child.pid))\n"
            "for line in sys.stdin:\n"
            "    message = json.loads(line)\n"
            "    if message.get('method') == 'initialize':\n"
            "        print(json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {"
            "'protocolVersion': '2025-03-26', 'serverInfo': {'name': 'kind'}}}), "
            "flush=True)\n"
            "    elif message.get('method') == 'tools/list':\n"
            "        print(json.dumps({'jsonrpc': '2.0', 'id': 2, 'result': "
            "{'tools': []}}), flush=True)\n"
        )
        entry = self.local_entry(server, environment={"CHILD_PID": str(pid_file)})

        result = self.mcp.test_local(entry, str(self.root))

        self.assertTrue(result["ok"], result)
        child_pid = int(pid_file.read_text(encoding="utf-8"))
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            self.fail("Kindprozess %d läuft nach dem Test weiter" % child_pid)

    def test_malformed_initialize_result_is_a_protocol_error(self):
        server = self.write_server(
            "import json, sys\n"
            "for line in sys.stdin:\n"
            "    message = json.loads(line)\n"
            "    if message.get('method') == 'initialize':\n"
            "        print(json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': None}), "
            "flush=True)\n"
        )
        entry = self.local_entry(server)

        result = self.mcp.test_local(entry, str(self.root))

        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "protocol")
        self.assertIn("kein gültiges Ergebnis", result["error"])

    def test_unexpected_server_info_is_not_passed_through(self):
        server = self.write_server(
            "import json, sys\n"
            "for line in sys.stdin:\n"
            "    message = json.loads(line)\n"
            "    if message.get('method') == 'initialize':\n"
            "        print(json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {"
            "'protocolVersion': '2025-03-26', 'serverInfo': 'kaputt'}}), flush=True)\n"
            "    elif message.get('method') == 'tools/list':\n"
            "        print(json.dumps({'jsonrpc': '2.0', 'id': 2, 'result': "
            "{'tools': []}}), flush=True)\n"
        )
        entry = self.local_entry(server)

        result = self.mcp.test_local(entry, str(self.root))

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["server"], {})

    def test_output_over_the_limit_is_dropped_and_reported(self):
        server = self.write_server(
            "import json, sys, time\n"
            "line = json.dumps({'x': 'y' * 200}) + '\\n'\n"
            "for _ in range(30000):\n"
            "    sys.stdout.write(line)\n"
            "sys.stdout.flush()\n"
            "time.sleep(30)\n"
        )
        entry = self.local_entry(server, timeout=5000)

        result = self.mcp.test_local(entry, str(self.root))

        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "timeout")
        self.assertIn("Ausgabelimit", result["hint"])

    def test_tools_list_that_never_answers_is_a_timeout(self):
        server = self.write_server(
            "import json, sys, time\n"
            "for line in sys.stdin:\n"
            "    message = json.loads(line)\n"
            "    if message.get('method') == 'initialize':\n"
            "        print(json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {"
            "'protocolVersion': '2025-03-26', 'serverInfo': {'name': 'haengt'}}}), "
            "flush=True)\n"
            "    elif message.get('method') == 'tools/list':\n"
            "        time.sleep(30)\n"
        )
        entry = self.local_entry(server, timeout=5000)

        result = self.mcp.test_local(entry, str(self.root))

        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "timeout")
        self.assertIn("Zeitlimit", result["error"])

    def test_unresponsive_server_hits_the_limit_with_a_timeout_category(self):
        server = self.write_server("import time\ntime.sleep(30)\n")
        entry = self.local_entry(server, timeout=5000)

        result = self.mcp.test_local(entry, str(self.root))

        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "timeout")
        self.assertIn("Zeitlimit", result["error"] + result["hint"])

    def test_secrets_from_the_entry_do_not_appear_in_the_result(self):
        geheimnis = "s3cr3t-local-value"
        server = self.write_server(
            "import json, os, sys\n"
            "sys.stderr.write('Token: ' + os.environ['GEHEIM'] + '\\n')\n"
            "sys.stderr.flush()\n"
            "for line in sys.stdin:\n"
            "    message = json.loads(line)\n"
            "    if message.get('method') == 'initialize':\n"
            "        print(json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {"
            "'protocolVersion': '2025-03-26', "
            "'serverInfo': {'name': os.environ['GEHEIM']}}}), flush=True)\n"
        )
        entry = self.local_entry(
            server,
            command=[sys.executable, str(server), "--token", geheimnis],
            environment={"GEHEIM": geheimnis},
        )

        result = self.mcp.test_local(entry, str(self.root))

        self.assertFalse(result["ok"])
        # Der Server beantwortet nur initialize und läuft weiter: das ist ein
        # Zeitlimit, kein Protokollfehler (siehe test_tools_list_that_never_answers_is_a_timeout).
        self.assertEqual(result["category"], "timeout")
        self.assertNotIn(geheimnis, json.dumps(result, ensure_ascii=False))


class RemoteHandshakeTest(McpTestFixture):
    def handler(self, respond):
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            requests = []

            def log_message(self, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                type(self).requests.append(
                    {"headers": dict(self.headers), "body": body}
                )
                respond(self, body)

        return Handler

    @staticmethod
    def send_json(handler, code, payload, extra_headers=None):
        data = json.dumps(payload).encode("utf-8")
        handler.send_response(code)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(data)))
        for key, value in (extra_headers or {}).items():
            handler.send_header(key, value)
        handler.end_headers()
        handler.wfile.write(data)

    @staticmethod
    def send_empty(handler, code):
        handler.send_response(code)
        handler.send_header("Content-Length", "0")
        handler.end_headers()

    def test_streamable_http_handshake_reports_tools_without_tool_calls(self):
        def respond(handler, body):
            method = body.get("method")
            if method == "initialize":
                self.send_json(
                    handler,
                    200,
                    INIT_RESULT,
                    {"Mcp-Session-Id": "sitzung-1"},
                )
            elif method == "tools/list":
                self.send_json(
                    handler,
                    200,
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "result": {
                            "tools": [{"name": "suche", "description": "Suchen"}]
                        },
                    },
                )
            else:
                self.send_empty(handler, 202)

        Handler = self.handler(respond)
        url = self.start_http(Handler)

        result = self.mcp.test_remote({"type": "remote", "url": url, "timeout": 10000}, "mock")

        self.assertTrue(result["ok"], result)
        self.assertEqual([tool["name"] for tool in result["tools"]], ["suche"])
        self.assertIn("remote", result["transport"])
        self.assertIn("Streamable HTTP", result["transport"])
        self.assertTrue(result["warning"])
        self.assertIn("tools/call", " ".join(result["notes"]))
        methods = [request["body"].get("method") for request in Handler.requests]
        self.assertEqual(methods, ["initialize", "notifications/initialized", "tools/list"])
        self.assertNotIn("tools/call", methods)

    def test_authentication_error_is_separate_and_secret_free(self):
        geheimnis = "s3cr3t-http-value"

        def respond(handler, body):
            data = ("Anmeldung fehlt für " + handler.headers.get("Authorization", "")).encode()
            handler.send_response(401)
            handler.send_header("Content-Type", "text/plain")
            handler.send_header("Content-Length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)

        Handler = self.handler(respond)
        url = self.start_http(Handler)
        entry = {
            "type": "remote",
            "url": url,
            "headers": {"Authorization": "Bearer " + geheimnis},
            "timeout": 10000,
        }

        result = self.mcp.test_remote(entry, "mock")

        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "auth")
        self.assertIn("OAuth", result["hint"])
        self.assertIn("keine Anmeldung", result["hint"])
        self.assertIn("opencode mcp auth", result["hint"])
        self.assertNotIn(geheimnis, json.dumps(result, ensure_ascii=False))

    def test_invalid_protocol_is_reported_as_protocol_error(self):
        def respond(handler, body):
            data = b"das ist kein JSON"
            handler.send_response(200)
            handler.send_header("Content-Type", "text/plain")
            handler.send_header("Content-Length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)

        Handler = self.handler(respond)
        url = self.start_http(Handler)

        result = self.mcp.test_remote({"type": "remote", "url": url, "timeout": 10000}, "mock")

        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "protocol")
        self.assertIn("Streamable HTTP", result["hint"])

    def test_endless_event_stream_returns_after_the_wanted_answer(self):
        def respond(handler, body):
            method = body.get("method")
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream")
            handler.end_headers()
            if method == "initialize":
                payload = INIT_RESULT
                wanted = 1
            elif method == "tools/list":
                payload = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {"tools": [{"name": "dauer"}]},
                }
                wanted = 2
            else:
                handler.wfile.write(b": ok\n\n")
                handler.wfile.flush()
                return
            handler.wfile.write(
                ("data: " + json.dumps(payload) + "\n\n").encode("utf-8")
            )
            handler.wfile.flush()
            try:
                while True:
                    handler.wfile.write(b": weiter\n\n")
                    handler.wfile.flush()
                    time.sleep(0.02)
            except (BrokenPipeError, ConnectionResetError):
                return

        Handler = self.handler(respond)
        url = self.start_http(Handler)
        started = time.time()

        result = self.mcp.test_remote({"type": "remote", "url": url, "timeout": 30000}, "mock")

        self.assertTrue(result["ok"], result)
        self.assertEqual([tool["name"] for tool in result["tools"]], ["dauer"])
        self.assertLess(time.time() - started, 10, "Dauerstream wurde nicht begrenzt")

    def test_malformed_tools_result_is_a_protocol_error(self):
        def respond(handler, body):
            if body.get("method") == "initialize":
                self.send_json(handler, 200, INIT_RESULT)
            elif body.get("method") == "tools/list":
                self.send_json(
                    handler, 200, {"jsonrpc": "2.0", "id": 2, "result": None}
                )
            else:
                self.send_empty(handler, 202)

        Handler = self.handler(respond)
        url = self.start_http(Handler)

        result = self.mcp.test_remote(
            {"type": "remote", "url": url, "timeout": 10000}, "mock"
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "protocol")
        self.assertIn("kein gültiges Ergebnis", result["error"])

    def test_oauth_is_not_performed_and_the_limit_is_visible(self):
        def respond(handler, body):
            if body.get("method") == "initialize":
                self.send_json(handler, 200, INIT_RESULT)
            elif body.get("method") == "tools/list":
                self.send_json(
                    handler, 200, {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}}
                )
            else:
                self.send_empty(handler, 202)

        Handler = self.handler(respond)
        url = self.start_http(Handler)
        entry = {
            "type": "remote",
            "url": url,
            "oauth": {"clientId": "kennung"},
            "timeout": 10000,
        }

        result = self.mcp.test_remote(entry, "mock")

        self.assertTrue(result["ok"], result)
        notes = " ".join(result["notes"])
        self.assertIn("OAuth", notes)
        self.assertIn("keine Anmeldung", notes)
        self.assertIn("opencode mcp auth", notes)


class TransportAndConfigTest(McpTestFixture):
    def test_unknown_transport_is_reported_without_calling_it_broken(self):
        result = self.mcp.test(
            "global", None, {"type": "websocket", "url": "ws://127.0.0.1:1/mcp"}
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "unsupported_transport")
        self.assertIn("local", result["hint"])
        self.assertIn("remote", result["hint"])
        self.assertIn("kein Hinweis auf einen defekten Server", result["hint"])
        self.assertEqual(set(result["supported_transports"]), {"local", "remote"})

    def test_unknown_url_scheme_is_reported_as_unsupported_transport(self):
        result = self.mcp.test(
            "global", None, {"type": "remote", "url": "ws://127.0.0.1:1/mcp"}
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "unsupported_transport")
        self.assertIn("WebSocket", result["hint"])

    def test_invalid_configuration_is_a_configuration_error(self):
        result = self.mcp.test("global", None, {"type": "remote", "url": "keine-url"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "config")
        self.assertIn("Ungültige Konfiguration", result["error"])


if __name__ == "__main__":
    unittest.main()
