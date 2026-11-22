"""Unit-Tests F33, WP6.2: AGENTS.md sichern und wiederherstellen.

Ableitung ausschließlich aus ``docs/features/F33.md`` („WP6 — Backend-Verträge“
Punkt 2) und dem Arbeitspaket. Geprüft wird:

* ``agents_file_backup(name)`` legt eine Sicherung der Projekt-AGENTS.md an;
  das Original bleibt unverändert, der Sicherungsname trägt einen Zeitstempel
  und kollidiert bei wiederholten Sicherungen nicht.
* ``agents_file_restore(name)`` stellt die **neueste** Sicherung wieder her und
  legt vorher eine Safety-Sicherung des aktuellen Standes an.
* ``POST /api/agents_file {action:"backup"}`` meldet „AGENTS.md gesichert“,
  ``{action:"restore", confirm:true}`` meldet „AGENTS.md wiederhergestellt“;
  ohne ``confirm:true`` wird abgelehnt und die Datei bleibt unverändert. Jede
  Antwort enthält die aktualisierte ``agents_file``-Ansicht.

Der Vertrag nennt keinen Ablageort und kein Namensschema der Sicherungen. Der
Test prüft daher beobachtbar: Nach der Sicherung existiert eine neue Datei
unterhalb des isolierten Prüfbereichs mit dem Dateiinhalt, und wiederholte
Sicherungen erzeugen verschiedene Dateien. Alle Tests arbeiten in temporären
Verzeichnissen (Muster ``tests/unit/test_f31_agents_file.py``).

ROT-PHASE (2026-11-21, vor der Implementierung von WP6.2)
--------------------------------------------------------
Ausgeführt mit::

    python3 -m unittest tests.unit.test_f33_agents_file_backup -v

Ergebnis: 7 Fälle, 7 rot.

* ``test_backup_stores_the_file_and_keeps_the_original`` — AttributeError:
  ``agents_file_backup`` fehlt.
* ``test_repeated_backups_get_distinct_timestamped_names`` — AttributeError:
  ``agents_file_backup`` fehlt.
* ``test_restore_brings_back_the_newest_backup_with_a_safety_backup`` —
  AttributeError: ``agents_file_backup`` fehlt.
* ``test_restore_without_a_backup_is_rejected`` — AttributeError:
  ``agents_file_restore`` fehlt.
* ``test_backup_reports_the_exact_message_and_view`` — 400 „Unbekannte
  Aktion“ (Endpoint kennt ``action:"backup"`` nicht).
* ``test_restore_with_confirm_brings_back_the_backup`` — 400 „Unbekannte
  Aktion“ (Endpoint kennt ``action:"restore"`` nicht).
* ``test_restore_without_confirm_is_rejected_and_keeps_the_file`` — 400
  „Unbekannte Aktion“ schon bei der Vorbedingung (gültige Sicherung).
"""
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
WEB = REPO / "bin" / "vibe-web.py"

AGENTS_V1 = "# Projekt-AGENTS F33\n\nErster Stand.\n"
AGENTS_V2 = "# Projekt-AGENTS F33\n\nZweiter Stand.\n"
AGENTS_V3 = "# Projekt-AGENTS F33\n\nDritter Stand (nicht gesichert).\n"

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
    "XDG_CONFIG_HOME",
    "VIBE_GLOBAL_AGENTS",
)


def isolated_env(root, home, port=None):
    """Umgebung, die ausschließlich im temporären Prüfverzeichnis arbeitet."""
    env = os.environ.copy()
    for key in ISOLATED_ENV:
        env.pop(key, None)
    env.update({
        "VIBE": str(root),
        "VIBE_NO_CONTAINER": "1",
        "HOME": str(home),
        "VIBE_STATE": str(Path(root) / "_toolchain"),
        "VIBE_AGENTS_DIR": str(Path(home) / ".config" / "opencode" / "agents"),
        "VIBE_CONFIG_FILE": str(Path(home) / ".config" / "vibe" / "config.json"),
    })
    if port is not None:
        env["VIBE_UI_PORT"] = str(port)
    return env


def load_cli(vibe_root, home):
    """Lädt bin/vibe mit isoliertem VIBE/HOME, ohne main() auszuführen."""
    old = {key: os.environ.get(key) for key in ISOLATED_ENV}
    for key in ISOLATED_ENV:
        os.environ.pop(key, None)
    os.environ.update(isolated_env(vibe_root, home))
    os.environ["VIBE_STORAGE_LOCK_DIR"] = str(Path(vibe_root) / "locks")
    try:
        loader = importlib.machinery.SourceFileLoader(
            "vibe_f33_agents_file_backup_under_test", str(CLI))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return module


def snapshot(root):
    """SHA-256 je Datei relativ zum Prüfbereich."""
    root = Path(root)
    digests = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digests[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()).hexdigest()
    return digests


def content_digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class AgentsFileBackupFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.proj = self.root / "proj"
        (self.proj / ".vibe").mkdir(parents=True)
        (self.proj / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (self.proj / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        self.cli = load_cli(self.root, self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def agents_path(self):
        return self.proj / "AGENTS.md"

    def write_agents(self, text):
        self.agents_path().write_text(text, encoding="utf-8")

    def read_agents(self):
        return self.agents_path().read_text(encoding="utf-8")

    def new_files(self, before):
        after = snapshot(self.root)
        return {name: digest for name, digest in after.items()
                if name not in before}

    def assert_backup_of(self, files, text):
        self.assertIn(
            content_digest(text), set(files.values()),
            "Keine neue Sicherungsdatei enthält den erwarteten Inhalt: "
            + repr(sorted(files)))


class AgentsFileBackupFunctionTest(AgentsFileBackupFixture):
    def test_backup_stores_the_file_and_keeps_the_original(self):
        """Vorbedingung: Projekt-AGENTS.md mit Inhalt.

        Aktion: ``agents_file_backup("proj")``.
        Erwartung: Das Original bleibt byte-identisch; eine neue Sicherungsdatei
        enthält genau diesen Inhalt.
        """
        self.write_agents(AGENTS_V1)
        before = snapshot(self.root)
        original = self.agents_path().read_bytes()

        self.cli.agents_file_backup("proj")

        self.assertEqual(self.agents_path().read_bytes(), original,
                         "Die Sicherung veränderte die AGENTS.md")
        files = self.new_files(before)
        self.assertTrue(files, "Es entstand keine Sicherungsdatei")
        self.assert_backup_of(files, AGENTS_V1)

    def test_repeated_backups_get_distinct_timestamped_names(self):
        """Vorbedingung: zwei Stände der AGENTS.md.

        Aktion: Nach jedem Stand eine Sicherung.
        Erwartung: Zwei verschiedene Sicherungsdateien; keine überschreibt die
        andere, beide Inhalte bleiben erhalten.
        """
        self.write_agents(AGENTS_V1)
        before = snapshot(self.root)
        self.cli.agents_file_backup("proj")
        self.write_agents(AGENTS_V2)
        self.cli.agents_file_backup("proj")

        files = self.new_files(before)
        self.assertGreaterEqual(
            len(files), 2,
            "Wiederholte Sicherungen erzeugen keine eigenen Dateien: "
            + repr(sorted(files)))
        contents = set(files.values())
        self.assertIn(content_digest(AGENTS_V1), contents,
                      "Die erste Sicherung ging verloren: "
                      + repr(sorted(files)))
        self.assertIn(content_digest(AGENTS_V2), contents,
                      "Die zweite Sicherung fehlt: " + repr(sorted(files)))
        self.assertEqual(self.read_agents(), AGENTS_V2)

    def test_restore_brings_back_the_newest_backup_with_a_safety_backup(self):
        """Vorbedingung: v1 gesichert, v2 gesichert, v3 ungesichert.

        Aktion: ``agents_file_restore("proj")``.
        Erwartung: Die Datei enthält v2 (neueste Sicherung); eine zusätzliche
        Safety-Sicherung enthält den vorherigen Stand v3.
        """
        self.write_agents(AGENTS_V1)
        self.cli.agents_file_backup("proj")
        self.write_agents(AGENTS_V2)
        self.cli.agents_file_backup("proj")
        self.write_agents(AGENTS_V3)
        before = snapshot(self.root)

        self.cli.agents_file_restore("proj")

        self.assertEqual(
            self.read_agents(), AGENTS_V2,
            "Die Wiederherstellung brachte nicht die neueste Sicherung zurück")
        files = self.new_files(before)
        self.assert_backup_of(files, AGENTS_V3)
        # v1 und v2 bleiben als Sicherungen erhalten.
        all_digests = set(snapshot(self.root).values())
        self.assertIn(content_digest(AGENTS_V1), all_digests)
        self.assertIn(content_digest(AGENTS_V2), all_digests)

    def test_restore_without_a_backup_is_rejected(self):
        """Vorbedingung: keine Sicherung vorhanden.

        Erwartung: ``agents_file_restore`` wirft ``ValueError`` und die Datei
        bleibt unverändert.
        """
        self.write_agents(AGENTS_V1)
        with self.assertRaises(ValueError):
            self.cli.agents_file_restore("proj")
        self.assertEqual(self.read_agents(), AGENTS_V1)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class AgentsFileBackupApiTest(unittest.TestCase):
    """POST /api/agents_file backup/restore gegen ein Server-Fixture."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        cls.port = free_port()
        env = isolated_env(cls.root, cls.home, cls.port)
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=True)
        cls.pgid = os.getpgid(cls.proc.pid)
        token_file = cls.root / "_logs" / "web.token"
        deadline = time.time() + 25
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                            ("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError("vibe-web wurde vorzeitig beendet: " + output)
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        if cls.proc.stdout:
            cls.proc.stdout.close()
        try:
            os.killpg(cls.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        cls.tmp.cleanup()

    def setUp(self):
        self.path = self.project / "AGENTS.md"
        self.path.write_text(AGENTS_V1, encoding="utf-8")
        for item in self.root.rglob("*"):
            if item.is_file() and item != self.path and "AGENTS" in item.name:
                item.unlink()

    def request(self, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data,
            method="POST" if data else "GET")
        req.add_header("Host", f"127.0.0.1:{self.port}")
        req.add_header("X-Token", self.token)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status, json.loads(
                    response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.loads(error.read().decode("utf-8"))
            finally:
                error.close()

    def assert_view(self, payload):
        view = payload.get("agents_file")
        self.assertIsInstance(view, dict, payload)
        for key in ("exists", "before", "managed", "after", "digest"):
            self.assertIn(key, view, "agents_file-Ansicht ohne " + key
                          + ": " + repr(view))
        self.assertTrue(view["exists"], view)

    def test_backup_reports_the_exact_message_and_view(self):
        """Vorbedingung: Projekt-AGENTS.md.

        Aktion: POST ``{action:"backup"}``.
        Erwartung: ``ok``, Meldung exakt „AGENTS.md gesichert“, aktualisierte
        ``agents_file``-Ansicht; die Datei bleibt unverändert.
        """
        status, payload = self.request(
            "/api/agents_file", {"name": "proj", "action": "backup"})
        self.assertEqual(200, status, payload)
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual("AGENTS.md gesichert", payload.get("message"), payload)
        self.assert_view(payload)
        self.assertEqual(self.path.read_text(encoding="utf-8"), AGENTS_V1)

    def test_restore_with_confirm_brings_back_the_backup(self):
        """Vorbedingung: v1 gesichert, danach v2 geschrieben.

        Aktion: POST ``{action:"restore", confirm:true}``.
        Erwartung: Meldung exakt „AGENTS.md wiederhergestellt“, die Datei
        enthält wieder v1, die Antwort bringt die aktualisierte Ansicht.
        """
        status, payload = self.request(
            "/api/agents_file", {"name": "proj", "action": "backup"})
        self.assertEqual(200, status, payload)
        self.path.write_text(AGENTS_V2, encoding="utf-8")

        status, payload = self.request(
            "/api/agents_file",
            {"name": "proj", "action": "restore", "confirm": True})
        self.assertEqual(200, status, payload)
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual(
            "AGENTS.md wiederhergestellt", payload.get("message"), payload)
        self.assert_view(payload)
        self.assertEqual(self.path.read_text(encoding="utf-8"), AGENTS_V1,
                         "Die Wiederherstellung brachte nicht v1 zurück")

    def test_restore_without_confirm_is_rejected_and_keeps_the_file(self):
        """Vorbedingung: v1 gesichert, danach v2 geschrieben.

        Aktion: Erst eine gültige Sicherung, dann POST ``{action:"restore"}``
        ohne ``confirm:true``.
        Erwartung: Die Sicherung bestätigt die Aktion; die Wiederherstellung
        ohne Bestätigung wird abgelehnt (Status 400, ``ok`` falsch) und die
        Datei bleibt v2.
        """
        status, payload = self.request(
            "/api/agents_file", {"name": "proj", "action": "backup"})
        self.assertEqual(200, status, payload)
        self.assertEqual("AGENTS.md gesichert", payload.get("message"), payload)
        self.path.write_text(AGENTS_V2, encoding="utf-8")

        status, payload = self.request(
            "/api/agents_file", {"name": "proj", "action": "restore"})
        self.assertEqual(400, status, payload)
        self.assertFalse(payload.get("ok"), payload)
        self.assertEqual(self.path.read_text(encoding="utf-8"), AGENTS_V2,
                         "Ohne Bestätigung wurde die Datei verändert")


if __name__ == "__main__":
    unittest.main()
