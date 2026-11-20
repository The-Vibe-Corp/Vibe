"""Regressionsschutz für die Modularisierung von Weboberfläche und Diensten (V-019).

Die Tests halten drei Zusagen des Arbeitspakets fest:

* Die Oberfläche wird aus getrennten statischen Dateien ausgeliefert; der
  Server liefert nur die freigegebenen Dateien und keine Verzeichnisausbrüche.
* CLI und Web verwenden dieselbe Fachlogik: Die Web-API ruft die
  Kommando-Funktionen der CLI auf und gibt ihnen einen eigenen Ausgabestrom.
* Parallele Anfragen vermischen ihre Ausgabe nicht. Der frühere globale
  ``redirect_stdout`` hätte bei gleichzeitigen Aufrufen Zeilen vertauscht.
"""
import concurrent.futures
import contextlib
import http.client
import importlib.machinery
import importlib.util
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"
SERVICES = REPO / "bin" / "vibe_services.py"
# AP22: die klassische Oberfläche liegt unter /classic, die neue unter /.
CLASSIC = REPO / "bin" / "web" / "classic.html"
INDEX = REPO / "bin" / "web" / "index.html"
CSS = REPO / "bin" / "web" / "styles.css"
JS = REPO / "bin" / "web" / "app.js"

services = None


def setUpModule():
    global services
    sys.path.insert(0, str(REPO / "bin"))
    loader = importlib.machinery.SourceFileLoader("vibe_services_under_test", str(SERVICES))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    services = module


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class CaptureIsolationTest(unittest.TestCase):
    """Der Ausgabestrom gehört zum Aufruf, nicht zum Prozess."""

    def test_parallel_captures_do_not_mix_their_output(self):
        barrier = threading.Barrier(2)
        results = {}
        failures = []

        def noisy(tag, out=None):
            print("start " + tag, file=out)
            barrier.wait(timeout=5)
            print("end " + tag, file=out)

        def worker(tag):
            try:
                results[tag] = services.capture(noisy, tag)
            except BaseException as error:  # noqa: BLE001 - im Test sichtbar machen
                failures.append(error)

        threads = [threading.Thread(target=worker, args=(tag,)) for tag in ("A", "B")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(failures, [], "Thread-Fehler: " + repr(failures))
        self.assertEqual(results["A"], (True, "start A\nend A"))
        self.assertEqual(results["B"], (True, "start B\nend B"))

    def test_capture_writes_only_to_its_own_stream(self):
        process_output = io.StringIO()
        with contextlib.redirect_stdout(process_output):
            ok, message = services.capture(lambda out: print("nur im Aufruf", file=out))

        self.assertTrue(ok)
        self.assertEqual(message, "nur im Aufruf")
        self.assertEqual(process_output.getvalue(), "", "globaler stdout wurde beschrieben")

    def test_capture_reports_system_exit_without_leaking_output(self):
        def failing(out=None):
            print("vor dem Abbruch", file=out)
            raise SystemExit("fachlicher Fehler")

        ok, message = services.capture(failing)
        self.assertFalse(ok)
        self.assertEqual(message, "fachlicher Fehler")


class WebFixture(unittest.TestCase):
    """Startet das echte Dashboard mit frischem VIBE/HOME auf freiem Port."""

    project_names = ("proj",)

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        for name in cls.project_names:
            project = cls.root / name
            (project / ".vibe").mkdir(parents=True)
            (project / ".vibe" / "project.env").write_text("TYPE=generic\n", encoding="utf-8")
            (project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.port = free_port()
        cls.log_path = cls.root / "server.log"
        cls.log_file = open(cls.log_path, "w", encoding="utf-8")
        env = {key: value for key, value in os.environ.items() if not key.startswith("VIBE_")}
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.root / "home"),
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
                raise AssertionError("vibe-web wurde vorzeitig beendet: " + cls.server_log())
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
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

    def request(self, method, path, body=None, token=True):
        if body is not None:
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if token is True:
            headers["X-Token"] = self.token
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            text = response.read().decode("utf-8", "replace")
            return response.status, text, dict(response.getheaders())
        finally:
            connection.close()


class StaticAssetsTest(WebFixture):
    def test_page_is_delivered_from_separate_static_files(self):
        # AP22: die klassische Oberfläche liegt unter /classic; ihre Verdrahtung
        # (styles.css/app.js) bleibt unverändert und wird hier weitergeprüft.
        status, body, headers = self.request("GET", "/classic", token=False)
        self.assertEqual(status, 200, body)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        self.assertIn('href="/static/styles.css"', body)
        self.assertIn('src="/static/app.js"', body)
        self.assertIn('name="vibe-opencode-url"', body)
        # Keine eingebetteten Styles oder Skripte mehr: die Oberfläche besteht
        # aus getrennten Dateien, die der Server einzeln ausliefert.
        self.assertNotIn("<style>", body)
        self.assertNotIn("<script>", body)

    def test_new_shell_is_delivered_from_nova_files(self):
        # AP22: die neue Standard-UI unter / lädt das Nova-Design-System und
        # den Nova-Kern aus getrennten statischen Dateien.
        status, body, headers = self.request("GET", "/", token=False)
        self.assertEqual(status, 200, body)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        self.assertIn('href="/static/nova.css"', body)
        self.assertIn('src="/static/nova-core.js"', body)
        self.assertIn('name="vibe-opencode-url"', body)

    def test_styles_and_scripts_are_served_without_token(self):
        status, css, headers = self.request("GET", "/static/styles.css", token=False)
        self.assertEqual(status, 200, css[:200])
        self.assertIn("text/css", headers.get("Content-Type", ""))
        self.assertIn(".confirm{", css, "Inline-Bestätigung fehlt im Stylesheet")

        status, js, headers = self.request("GET", "/static/app.js", token=False)
        self.assertEqual(status, 200, js[:200])
        self.assertIn("javascript", headers.get("Content-Type", ""))
        self.assertIn("'aria-live':'polite'", js, "Statusbereich fehlt im Skript")
        self.assertNotIn("__OPENCODE_URL__", js, "Platzhalter wurde nicht aufgelöst")

    def test_unknown_and_traversing_asset_paths_are_rejected(self):
        for path in (
            "/static/unbekannt.js",
            "/static/../bin/vibe",
            "/static/%2e%2e/bin/vibe",
            "/static/",
        ):
            with self.subTest(path=path):
                status, body, _ = self.request("GET", path, token=False)
                self.assertEqual(status, 404, body)

    def test_opencode_url_reaches_the_page_without_script_placeholder(self):
        status, body, _ = self.request("GET", "/", token=False)
        self.assertEqual(status, 200, body)
        self.assertNotIn("__OPENCODE_URL__", body)
        self.assertIn("http://", body)


class ParallelApiOutputTest(WebFixture):
    project_names = ("alpha", "beta", "gamma", "delta")

    def test_parallel_init_requests_keep_their_own_message(self):
        names = list(self.project_names)
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(names)) as pool:
            responses = list(
                pool.map(
                    lambda name: (name, self.request("POST", "/api/init", {"name": name})),
                    names,
                )
            )

        for name, (status, body, _) in responses:
            with self.subTest(project=name):
                self.assertEqual(status, 200, body)
                data = json.loads(body)
                self.assertTrue(data["ok"], body)
                self.assertIn(name, data["message"])
                for other in names:
                    if other != name:
                        self.assertNotIn(
                            other,
                            data["message"],
                            "Ausgabe von %s enthält fremdes Projekt %s" % (name, other),
                        )


if __name__ == "__main__":
    unittest.main()
