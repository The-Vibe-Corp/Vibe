"""Unit-Tests F33, WP6.1: Agenten-Backup ohne Versionshinweis.

Ableitung ausschließlich aus ``docs/features/F33.md`` („WP6 — Backend-Verträge“
Punkt 1) und dem Arbeitspaket, nicht aus einer Implementierung. Geprüft wird:

* ``agent_backup(scope, name)`` legt eine Sicherung der **unveränderten**
  Agentendatei im Sicherungsordner des Bereichs ab; die Datei selbst bleibt
  byte-identisch. Wiederholte Sicherungen sind kollisionsfrei.
* Unbekannte Agenten und unsichere Namen werden ohne Sicherung abgelehnt.
* ``POST /api/agent {action:"backup", scope, name}`` antwortet mit genau
  „Sicherung angelegt“ — ohne Versions-/Modellwarnung, ohne „Hinweis:“ — und
  liefert ``backups``, ``text`` und ``digest``. Ein unbekannter Agent wird
  abgelehnt, ohne eine Sicherung anzulegen.

Alle Tests arbeiten in temporären Verzeichnissen (Muster
``tests/unit/test_agent_management.py``); keine produktiven HOME-/VIBE-Pfade,
keine Modellaufrufe.

ROT-PHASE (2026-11-21, vor der Implementierung von WP6.1)
--------------------------------------------------------
Ausgeführt mit::

    python3 -m unittest tests.unit.test_f33_agent_backup -v

Ergebnis: 6 Fälle, 6 rot.

* ``test_backup_creates_a_copy_and_leaves_the_original_unchanged`` —
  AttributeError: ``agent_backup`` fehlt.
* ``test_repeated_backups_are_collision_free`` — AttributeError:
  ``agent_backup`` fehlt.
* ``test_project_agent_backup_lands_in_the_project_scope_folder`` —
  AttributeError: ``agent_backup`` fehlt.
* ``test_unknown_agent_and_unsafe_names_are_rejected`` — AttributeError:
  ``agent_backup`` fehlt.
* ``test_backup_answers_with_the_exact_message_and_keeps_the_file`` — 400
  „Unbekannte Aktion“ (Endpoint kennt ``action:"backup"`` nicht).
* ``test_unknown_agent_is_rejected_without_a_backup`` — 400 „Unbekannte
  Aktion“ schon bei der Vorbedingung (gültige Sicherung).
"""
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
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
WEB = REPO / "bin" / "vibe-web.py"

AGENT_V1 = """---
description: Erste Beschreibung
mode: subagent
model: opencode/test-modell
---
Erster Prompt.
"""

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
            "vibe_f33_agent_backup_under_test", str(CLI))
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


class AgentBackupFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        self.agents.mkdir(parents=True)
        self.proj = self.root / "proj"
        (self.proj / ".vibe").mkdir(parents=True)
        (self.proj / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8")
        self.cli = load_cli(self.root, self.home)
        self.cli._AGENT_VERSION = None
        # Kein Modelllisting: die Sicherung gehört nicht zur Modellprüfung.
        models = mock.patch.object(self.cli, "models_list", return_value=[])
        models.start()
        self.addCleanup(models.stop)

    def tearDown(self):
        self.cli._AGENT_VERSION = None
        self.tmp.cleanup()

    def global_path(self, name="tester"):
        return self.agents / (name + ".md")

    def project_path(self, name="tester"):
        return self.proj / ".opencode" / "agents" / (name + ".md")

    def write_global(self, name="tester", text=AGENT_V1):
        path = self.global_path(name)
        path.write_text(text, encoding="utf-8")
        return path

    def write_project(self, name="tester", text=AGENT_V1):
        path = self.project_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def backup_files(self, scope, name):
        directory = Path(self.cli.agent_backup_dir(scope))
        return sorted(directory.glob(name + "-*")) if directory.exists() else []


class AgentBackupFunctionTest(AgentBackupFixture):
    def test_backup_creates_a_copy_and_leaves_the_original_unchanged(self):
        """Vorbedingung: globale Agentendatei vorhanden.

        Aktion: ``agent_backup("global", "tester")``.
        Erwartung: Die Datei bleibt byte-identisch; im Sicherungsordner liegt
        eine Datei mit exakt demselben Inhalt.
        """
        path = self.write_global()
        before = path.read_bytes()

        self.cli.agent_backup("global", "tester")

        self.assertEqual(path.read_bytes(), before,
                         "Das Backup veränderte die Agentendatei")
        files = self.backup_files("global", "tester")
        self.assertEqual(1, len(files), "Es entstand keine Sicherung: "
                         + repr([item.name for item in files]))
        self.assertEqual(files[0].read_text(encoding="utf-8"), AGENT_V1,
                         "Die Sicherung enthält nicht den Dateiinhalt")
        self.assertEqual(
            [item.name for item in files], self.cli.agent_backups("global", "tester"),
            "Die Sicherung wird nicht als Sicherung des Agenten gelistet")

    def test_repeated_backups_are_collision_free(self):
        """Vorbedingung: globale Agentendatei.

        Aktion: Zwei Sicherungen ohne Änderung dazwischen.
        Erwartung: Zwei verschiedene Sicherungsdateien mit gleichem Inhalt;
        keine überschreibt die andere.
        """
        path = self.write_global()
        self.cli.agent_backup("global", "tester")
        self.cli.agent_backup("global", "tester")

        files = self.backup_files("global", "tester")
        self.assertEqual(
            2, len({item.name for item in files}),
            "Zwei Sicherungen kollidieren im Namen: "
            + repr([item.name for item in files]))
        for item in files:
            self.assertEqual(item.read_text(encoding="utf-8"), AGENT_V1)
        self.assertEqual(path.read_text(encoding="utf-8"), AGENT_V1)

    def test_project_agent_backup_lands_in_the_project_scope_folder(self):
        """Vorbedingung: Projektagent vorhanden.

        Aktion: ``agent_backup("proj", "tester")``.
        Erwartung: Die Sicherung liegt im Bereich ``proj``; der globale
        Sicherungsordner bleibt leer.
        """
        path = self.write_project()

        self.cli.agent_backup("proj", "tester")

        self.assertEqual(path.read_text(encoding="utf-8"), AGENT_V1)
        project_files = self.backup_files("proj", "tester")
        self.assertEqual(1, len(project_files),
                         "Es entstand keine Sicherung im Projektbereich")
        self.assertEqual([], self.backup_files("global", "tester"),
                         "Die Projektsicherung landete im globalen Ordner")

    def test_unknown_agent_and_unsafe_names_are_rejected(self):
        """Vorbedingung: keine Datei für ``fehlt``.

        Erwartung: Unbekannte Agenten und Pfadanteile werfen ``ValueError``
        und legen keine Sicherung an.
        """
        for scope, name in (("global", "fehlt"), ("global", "../evil"),
                            ("proj", "a/b")):
            with self.subTest(scope=scope, name=name):
                with self.assertRaises(ValueError):
                    self.cli.agent_backup(scope, name)
        self.assertEqual([], self.backup_files("global", "fehlt"))
        self.assertEqual([], self.backup_files("global", "evil"))


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class AgentBackupApiTest(unittest.TestCase):
    """POST /api/agent {action:"backup"} gegen ein echtes Server-Fixture."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8")
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
        self.path = self.agents / "tester.md"
        self.path.write_text(AGENT_V1, encoding="utf-8")
        backups = self.root / "_toolchain" / "agent-backups" / "global"
        if backups.exists():
            for item in backups.iterdir():
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

    def test_backup_answers_with_the_exact_message_and_keeps_the_file(self):
        """Vorbedingung: globale Agentendatei.

        Aktion: POST ``{action:"backup", scope:"global", name:"tester"}``.
        Erwartung: ``ok``, Meldung exakt „Sicherung angelegt“ ohne
        Versions-/Modellwarnung; Antwort enthält ``backups`` (eine Sicherung),
        ``text`` und ``digest``; die Datei bleibt unverändert.
        """
        before = self.path.read_bytes()
        status, payload = self.request(
            "/api/agent", {"action": "backup", "scope": "global",
                           "name": "tester"})
        self.assertEqual(200, status, payload)
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual("Sicherung angelegt", payload.get("message"), payload)
        self.assertNotIn("nicht geprüft", payload.get("message", ""))
        self.assertNotIn("Hinweis:", payload.get("message", ""))
        self.assertEqual(1, len(payload.get("backups") or []), payload)
        self.assertEqual(AGENT_V1, payload.get("text"), payload)
        self.assertTrue(payload.get("digest"), payload)
        self.assertEqual(self.path.read_bytes(), before,
                         "Das Backup veränderte die Agentendatei")
        stored = (self.root / "_toolchain" / "agent-backups" / "global"
                  / payload["backups"][0])
        self.assertTrue(stored.is_file(), "Die Sicherungsdatei fehlt: "
                        + str(stored))
        self.assertEqual(stored.read_text(encoding="utf-8"), AGENT_V1)

    def test_unknown_agent_is_rejected_without_a_backup(self):
        """Vorbedingung: Agent ``tester`` vorhanden, ``fehlt`` nicht.

        Aktion: Erst eine gültige Sicherung, dann POST
        ``{action:"backup", name:"fehlt"}``.
        Erwartung: Die gültige Sicherung bestätigt die Aktion; der unbekannte
        Agent wird abgelehnt (``ok`` falsch, Status 400) und erhält keine
        Sicherung.
        """
        status, payload = self.request(
            "/api/agent", {"action": "backup", "scope": "global",
                           "name": "tester"})
        self.assertEqual(200, status, payload)
        self.assertEqual("Sicherung angelegt", payload.get("message"), payload)

        status, payload = self.request(
            "/api/agent", {"action": "backup", "scope": "global",
                           "name": "fehlt"})
        self.assertEqual(400, status, payload)
        self.assertFalse(payload.get("ok"), payload)
        self.assertTrue((payload.get("message") or "").strip(), payload)
        backups = self.root / "_toolchain" / "agent-backups" / "global"
        self.assertFalse(
            backups.exists() and any(backups.glob("fehlt-*")),
            "Für einen unbekannten Agenten entstand eine Sicherung")


if __name__ == "__main__":
    unittest.main()
