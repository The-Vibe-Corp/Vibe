"""Dashboard-API für den Prüfmodus ``package`` (F31).

Die Tests starten das echte Dashboard mit einem Fixture-Projekt und sprechen
``POST /api/verify`` über HTTP an. Der Modus ``package`` muss an die gemeinsame
Fachlogik durchgereicht werden und dort ``VERIFY_PACKAGE`` ausführen, nicht
still ``quick`` oder ``full``. Die Prüfungsausgabe erscheint im verify-Stream
(derselbe Protokollstrom, den die Oberfläche zeigt), damit ein Klick auf
„Prüfung package“ denselben Nachweis liefert wie die anderen Stufen.

Alle Laufzeitpfade (VIBE, HOME, Ports) liegen in einem temporären Verzeichnis;
es werden keine echten Modell-, Router- oder MCP-Aufrufe ausgeführt.
"""
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

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"

VERIFY_QUICK_MARKER = "quick-pruefung"
VERIFY_FULL_MARKER = "full-pruefung"
VERIFY_PACKAGE_MARKER = "paket-pruefung"


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class VerifyApiPackageTest(unittest.TestCase):
    """Startet vibe-web.py mit einem Fixture-Projekt und freiem Port."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n"
            f'VERIFY_QUICK="echo {VERIFY_QUICK_MARKER}"\n'
            f'VERIFY_FULL="echo {VERIFY_FULL_MARKER}"\n'
            f'VERIFY_PACKAGE="echo {VERIFY_PACKAGE_MARKER}"\n',
            encoding="utf-8",
        )
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.runtime = cls.root / "_logs"
        cls.port = free_port()
        cls.log_path = cls.root / "server.log"
        cls.log_file = open(cls.log_path, "w", encoding="utf-8")
        # Ambient VIBE_*-Werte dürfen das Dashboard nicht auf die produktive
        # Installation zeigen lassen; der Test besitzt alle Laufzeitpfade.
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("VIBE_")
        }
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "VIBE_RUNTIME": str(cls.runtime),
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
        token_file = cls.runtime / "web.token"
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

    def request(self, method, path, body=None):
        data = None
        headers = {"Host": f"127.0.0.1:{self.port}", "X-Token": self.token}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        try:
            connection.request(method, path, body=data, headers=headers)
            response = connection.getresponse()
            text = response.read().decode("utf-8", "replace")
            return response.status, text
        finally:
            connection.close()

    def wait_for_file_content(self, path, marker, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if path.exists():
                text = path.read_text(encoding="utf-8", errors="replace")
                if marker in text:
                    return text
            time.sleep(0.05)
        content = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        self.fail(
            f"{marker!r} erschien nicht in {path}.\nPrüfprotokoll:\n{content}"
        )

    def open_verify_stream(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        connection.request(
            "GET",
            "/api/stream?name=proj&kind=verify",
            headers={"Host": f"127.0.0.1:{self.port}", "X-Token": self.token},
        )
        connection.sock.settimeout(2)
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        return connection, response

    def read_stream_until(self, response, marker, timeout=15):
        deadline = time.time() + timeout
        chunks = []
        while time.time() < deadline:
            try:
                line = response.readline()
            except (OSError, socket.timeout):
                continue
            if not line:
                break
            chunks.append(line.decode("utf-8", "replace"))
            text = "".join(chunks)
            if marker in text:
                return text
        self.fail(
            f"{marker!r} erschien nicht im verify-Stream:\n" + "".join(chunks)
        )

    def test_api_verify_accepts_package_and_runs_verify_package(self):
        status, body = self.request(
            "POST", "/api/verify", {"name": "proj", "mode": "package"}
        )

        self.assertEqual(status, 200, body)
        data = json.loads(body)
        self.assertTrue(data["ok"], body)
        self.assertIn("Prüfung gestartet", data["message"])

        log_path = self.runtime / "proj.verify.log"
        log_text = self.wait_for_file_content(log_path, VERIFY_PACKAGE_MARKER)
        self.assertIn(
            "echo " + VERIFY_PACKAGE_MARKER,
            log_text,
            "Das Prüfprotokoll nennt nicht den VERIFY_PACKAGE-Befehl",
        )
        self.assertNotIn(VERIFY_QUICK_MARKER, log_text)
        self.assertNotIn(VERIFY_FULL_MARKER, log_text)

        # Die Ausgabe muss auch über den Stream ankommen, den die Oberfläche liest.
        connection, response = self.open_verify_stream()
        try:
            stream_text = self.read_stream_until(response, VERIFY_PACKAGE_MARKER)
        finally:
            connection.close()
        self.assertIn(VERIFY_PACKAGE_MARKER, stream_text)

    def wait_for_stable_file(self, path, timeout=5.0):
        """Wartet, bis eine Datei nicht mehr wächst (asynchrone Prüfausgabe)."""
        deadline = time.time() + timeout
        last = None
        stable_since = None
        while time.time() < deadline:
            current = path.stat().st_size if path.exists() else None
            if current == last:
                if stable_since is not None and time.time() - stable_since >= 0.3:
                    return
            else:
                last = current
                stable_since = time.time()
            time.sleep(0.05)

    def test_api_verify_rejects_an_unknown_mode_without_starting_a_run(self):
        # Fehlerpfad: Ein unbekannter Modus darf nicht still auf quick
        # zurückfallen. Die API muss ok=False melden, die erlaubten Modi
        # nennen und den Prüfstand unverändert lassen (kein neuer Eintrag im
        # verify-Log, kein neuer Datenblock im verify-Stream).
        log_path = self.runtime / "proj.verify.log"
        # Eine vorherige Prüfung kann noch asynchron in das Protokoll
        # schreiben; erst den Ruhezustand abwarten, sonst wäre der Vergleich
        # eine Zeitabhängigkeit.
        self.wait_for_stable_file(log_path)
        before = (
            log_path.read_text(encoding="utf-8", errors="replace")
            if log_path.exists()
            else None
        )

        status, body = self.request(
            "POST", "/api/verify", {"name": "proj", "mode": "voller"}
        )

        self.assertEqual(status, 400, body)
        data = json.loads(body)
        self.assertFalse(data["ok"], body)
        self.assertIn("voller", data["message"])
        self.assertIn("voller", data["error"]["message"])
        for mode in ("quick", "package", "full"):
            self.assertIn(mode, data["message"])

        # Kein Prüflauf: Das Protokoll bleibt byte-gleich (oder weiterhin
        # nicht vorhanden). Ein stiller quick-Fallback würde hier "echo
        # quick-pruefung" hineinschreiben.
        time.sleep(0.5)
        after = (
            log_path.read_text(encoding="utf-8", errors="replace")
            if log_path.exists()
            else None
        )
        self.assertEqual(
            before,
            after,
            "Unbekannter Prüfmodus hat einen Prüflauf gestartet:\n" + (after or ""),
        )
        self.assertNotIn(
            VERIFY_QUICK_MARKER,
            after or "",
            "Unbekannter Modus fiel still auf quick zurück",
        )

        connection, response = self.open_verify_stream()
        try:
            # Das erste Datenpaket ist der Bestand (tail) und wird verworfen;
            # danach dürfen keine weiteren Datenblöcke mehr folgen.
            response.readline()
            deadline = time.time() + 1.5
            extra = []
            while time.time() < deadline:
                try:
                    line = response.readline()
                except (OSError, socket.timeout):
                    break
                if not line:
                    break
                text = line.decode("utf-8", "replace")
                if text.startswith("data:"):
                    extra.append(text)
        finally:
            connection.close()
        self.assertEqual(
            extra,
            [],
            "Unbekannter Prüfmodus schrieb in den verify-Stream: " + "".join(extra),
        )


if __name__ == "__main__":
    unittest.main()
