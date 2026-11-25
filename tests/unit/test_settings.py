"""Einstellungen: Profile, Standardmodelle, Modelle, globale AGENTS.md und Neustart.

Aufruf: python3 -m unittest tests.unit.test_settings -v
"""


# ===========================================================================
# Unabhängige Unit-Abnahme (Backend-Teil): Settings-Backend-Verträge
# ===========================================================================

import datetime
import http.client
import importlib.machinery
import importlib.util
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
from unittest import mock

from tests.unit import env_support

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"
CLI = REPO / "bin" / "vibe"

USE_TOKEN = object()

# Instanzbeschreibende Variablen, die niemals in Testprozesse vererbt werden.
# Ergänzend zu tests/unit/env_support.py: Die globale AGENTS.md darf nicht aus
# der Läuferumgebung umgeleitet sein; ein evtl. gesetztes Restart-Flag sowie
# Sandbox-/Tmux-Umgebung dürfen den Testserver nicht beeinflussen.
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
    "VIBE_GLOBAL_AGENTS",
    "VIBE_WEB_KEEP_TOKEN",
    "VIBE_SANDBOX_ACTIVE",
    "TMUX",
    "TMUX_PANE",
)

STUB_MODELS = ["opencode/test-modell", "opencode/vibe-modell", "opencode/neu"]

# Fake-opencode mit Aufrufzähler: Jede Ausführung (Probe und models) wird
# protokolliert, damit der Cache-Nutzen von GET /api/agents beweisbar ist.
FAKE_OPENCODE_COUNTING = """#!/usr/bin/env bash
printf 'x\\n' >> {counter}
case "$1" in
  --version)
    printf 'opencode 2.1.4\\n'
    exit 0
    ;;
  models)
    printf '{models}\\n'
    exit 0
    ;;
esac
exit 2
""".replace("{models}", "\n".join(STUB_MODELS))

# Fake-opencode mit unterstützter Version, aber fehlgeschlagenem Modellaufruf.
FAKE_OPENCODE_BROKEN = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf 'opencode 2.1.4\\n'
    exit 0
    ;;
  models)
    printf 'opencode: kein Anbieter verbunden\\n' >&2
    exit 1
    ;;
esac
exit 2
"""


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_port(port, timeout=25.0):
    """Wartet, bis der Loopback-Port eine Verbindung annimmt."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def agent_text(model=None):
    """Gültige Agentendatei mit optionaler Modellzeile."""
    lines = ["---", "description: Testrolle", "mode: subagent"]
    if model:
        lines.append("model: " + model)
    lines.extend(["---", "", "Testprompt."])
    return "\n".join(lines) + "\n"


def _find_values(obj, key):
    """Liefert alle Werte zu ``key`` anywhere in einer verschachtelten Ansicht."""
    found = []
    if isinstance(obj, dict):
        for name, value in obj.items():
            if name == key:
                found.append(value)
            found.extend(_find_values(value, key))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_find_values(item, key))
    return found


def load_vibe_cli(root, home, state, agents_dir):
    """Lädt bin/vibe als In-Prozess-Modul mit isoliertem VIBE/HOME."""
    with env_support.isolated_process_environment(
        VIBE=str(root),
        VIBE_NO_CONTAINER="1",
        HOME=str(home),
        VIBE_RUNTIME=str(root / "_logs"),
        VIBE_STATE=str(state),
        VIBE_AGENTS_DIR=str(agents_dir),
        VIBE_CONFIG_FILE=str(home / ".config" / "vibe" / "config.json"),
        VIBE_STORAGE_LOCK_DIR=str(root / "locks"),
        VIBE_GLOBAL_AGENTS=None,
        VIBE_WEB_KEEP_TOKEN=None,
    ):
        loader = importlib.machinery.SourceFileLoader(
            "vibe_gh57_under_test", str(CLI))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    return module


def load_web_module(runtime_dir):
    """Lädt bin/vibe-web.py als In-Prozess-Modul (Import bleibt nebenwirkungsfrei)."""
    root = Path(runtime_dir).parent
    home = root / "home"
    with env_support.isolated_process_environment(
        VIBE=str(root),
        VIBE_NO_CONTAINER="1",
        HOME=str(home),
        VIBE_RUNTIME=str(runtime_dir),
        VIBE_STATE=str(root / "_toolchain"),
        VIBE_AGENTS_DIR=str(home / ".config" / "opencode" / "agents"),
        VIBE_CONFIG_FILE=str(home / ".config" / "vibe" / "config.json"),
        VIBE_GLOBAL_AGENTS=None,
        VIBE_WEB_KEEP_TOKEN=None,
    ):
        loader = importlib.machinery.SourceFileLoader(
            "vibe_gh57_web_under_test", str(WEB))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Dashboard-Fixture (Muster test_f34_backend.DashboardFixture + Fake-opencode)
# ---------------------------------------------------------------------------

class Gh57Dashboard(unittest.TestCase):
    """Startet das echte Dashboard als eigenen Prozess auf Loopback.

    Unterklassen wählen den Fake-opencode (``FAKE_SCRIPT``) und eine
    optionale ``ui.json`` (``UI_JSON``); jeder Test startet mit
    bereinigtem Zustand.
    """

    FAKE_SCRIPT = FAKE_OPENCODE_COUNTING
    UI_JSON = None

    @classmethod
    def setUpClass(cls):
        cls.start_server()

    @classmethod
    def start_server(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        cls.home = cls.root / "home"
        cls.agents = cls.home / ".config" / "opencode" / "agents"
        cls.agents.mkdir(parents=True)
        cls.toolchain = cls.root / "_toolchain"
        cls.toolchain.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.state = cls.toolchain
        cls.fake_bin = cls.root / "fakebin"
        cls.fake_bin.mkdir()
        cls.counter_file = cls.state / "models-stub-aufrufe.log"
        fake = cls.fake_bin / "opencode"
        fake.write_text(
            cls.FAKE_SCRIPT.replace("{counter}", str(cls.counter_file)),
            encoding="utf-8")
        fake.chmod(0o755)
        cls.port = free_port()
        if cls.UI_JSON is not None:
            (cls.state / "ui.json").write_text(
                json.dumps(cls.UI_JSON), encoding="utf-8")
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "HOME": str(cls.home),
            "VIBE_STATE": str(cls.state),
            "VIBE_INSTALL": str(cls.toolchain),
            "VIBE_RUNTIME": str(cls.log_dir),
            "VIBE_AGENTS_DIR": str(cls.agents),
            "VIBE_CONFIG_FILE": str(
                cls.home / ".config" / "vibe" / "config.json"),
            "PATH": str(cls.fake_bin) + os.pathsep + env.get("PATH", ""),
        })
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
                    "vibe-web wurde vorzeitig beendet: " + cls.server_log())
            if token_file.exists():
                try:
                    with socket.create_connection(
                            ("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            time.sleep(0.05)
        else:
            raise AssertionError(
                "vibe-web ist nicht erreichbar: " + cls.server_log())
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

    def setUp(self):
        """Jeder Fall startet mit bereinigtem Zustand (unabhängige Tests)."""
        (self.state / "models-cache.json").unlink(missing_ok=True)
        self.counter_file.unlink(missing_ok=True)
        for folder in ("profile-backups", "global-agents-backups"):
            backup_dir = self.state / folder
            if backup_dir.exists():
                for item in backup_dir.iterdir():
                    item.unlink()
                backup_dir.rmdir()
        (self.state / "profiles.json").unlink(missing_ok=True)
        (self.home / ".config" / "opencode" / "AGENTS.md").unlink(
            missing_ok=True)

    def request(self, method, path, body=None, token=USE_TOKEN, port=None):
        """HTTP-Anfrage; Standard mit Token und Loopback-Host."""
        if token is USE_TOKEN:
            token = self.token
        port = self.port if port is None else port
        if body is not None:
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {"Host": f"127.0.0.1:{port}"}
        if token is not None:
            headers["X-Token"] = token
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            text = response.read().decode("utf-8", "replace")
            return response.status, text, dict(response.getheaders())
        finally:
            connection.close()

    def post(self, path, body, token=USE_TOKEN, port=None):
        """POST mit Token und Same-Origin-Kontext (Muster AP13/F34)."""
        status, text, _headers = self.request(
            "POST", path, body=body, token=token, port=port)
        return status, json.loads(text)

    def get_json(self, path, token=USE_TOKEN, port=None):
        status, text, _headers = self.request(
            "GET", path, token=token, port=port)
        self.assertEqual(
            200, status, "GET " + path + " lieferte HTTP " + str(status)
            + ": " + text)
        return json.loads(text)

    def write_profiles(self, data):
        (self.state / "profiles.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def backup_names(self, folder):
        directory = self.state / folder
        if not directory.is_dir():
            return []
        return sorted(item.name for item in directory.iterdir() if item.is_file())

    def stub_calls(self):
        if not self.counter_file.exists():
            return 0
        return len(self.counter_file.read_text(encoding="utf-8").splitlines())

    def assert_utc_iso(self, value):
        """ISO-8601-UTC-Zeitstempel (Datum/Zeit + eindeutige UTC-Zone)."""
        self.assertIsInstance(value, str)
        self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.datetime.fromisoformat(normalized)
        self.assertIsNotNone(parsed.utcoffset(),
                             "Zeitstempel ohne Zeitzonenbezug: " + value)
        self.assertEqual(datetime.timedelta(0), parsed.utcoffset(),
                         "Zeitstempel ist nicht UTC: " + value)


class ProfilesApiDashboard(Gh57Dashboard):
    """Dashboard mit funktionierendem Fake-opencode für Profil-/AGENTS-Fälle."""


class ModelsDashboard(Gh57Dashboard):
    """Dashboard mit zählendem Fake-opencode für die Models-Refresh-Verträge."""


class ModelsBrokenDashboard(Gh57Dashboard):
    """Dashboard, dessen Harness-Modellaufruf fehlschlägt."""

    FAKE_SCRIPT = FAKE_OPENCODE_BROKEN


class RestartDashboard(Gh57Dashboard):
    """Eigene Instanz für den Neustartfall: ui.json plant abweichenden Port."""

    @classmethod
    def start_server(cls):
        # Der geplante Port liegt in ui.json vor Serverstart und muss sich vom
        # später gewählten Laufport unterscheiden; die Kollisionsprüfung
        # erfolgt daher nach dem Start (praktisch ausgeschlossen, bricht
        # andernfalls laut statt still).
        cls.planned_port = free_port()
        cls.UI_JSON = {"ui_port": cls.planned_port, "ui_bind": "127.0.0.1"}
        Gh57Dashboard.start_server.__func__(cls)
        if cls.planned_port == cls.port:
            raise AssertionError(
                "Portkollision zwischen Planung und Lauf — Testumgebung "
                "erneut versuchen")


# ---------------------------------------------------------------------------
# Profile: Standard-Nutz, Altbestand, aktiv-Reparatur (In-Prozess CLI)
# ---------------------------------------------------------------------------

class Gh57CliFixture(unittest.TestCase):
    """In-Prozess bin/vibe mit isoliertem Zustand (Muster test_agent_management)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        self.agents.mkdir(parents=True)
        self.state = self.root / "_toolchain"
        self.state.mkdir()
        self.cli = load_vibe_cli(self.root, self.home, self.state, self.agents)
        # Kein echter Modellaufruf: Profil- und Rollenleselogik ruft den
        # Harness nicht; falls eine künftige Implementierung doch, gilt
        # diese feste Liste statt eines Binary-Aufrufs.
        patcher = mock.patch.object(
            self.cli, "models_list",
            return_value=["opencode/test-modell", "opencode/vibe-modell"])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def write_agent(self, name, model=None):
        (self.agents / (name + ".md")).write_text(
            agent_text(model), encoding="utf-8")

    def write_profiles(self, data):
        (self.state / "profiles.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")


STANDARD_PROFILES = ("default", "free", "mid", "high")


class ProfilesSeedTest(Gh57CliFixture):
    """profiles_load säht die vier geschützten Standardprofile."""

    def test_profiles_load_sows_the_four_standard_profiles_on_fresh_state(self):
        self.assertFalse((self.state / "profiles.json").exists())

        data = self.cli.profiles_load()

        self.assertEqual(set(STANDARD_PROFILES), set(data["profile"]),
                         "Frischer Zustand enthält genau die Standardprofile")
        for name in STANDARD_PROFILES:
            values = data["profile"][name]
            self.assertTrue(
                all(not value for value in values.values()),
                "Standardprofil " + name + " beginnt ohne Modellwerte")
        self.assertEqual("default", data["aktiv"])

    def test_profiles_load_keeps_legacy_profiles_and_a_valid_aktiv(self):
        self.write_profiles({
            "aktiv": "kostenlos",
            "rollen": {"tester": "coder"},
            "profile": {
                "kostenlos": {"coder": "opencode/alt-modell"},
                "guenstig": {},
            },
        })

        data = self.cli.profiles_load()

        self.assertEqual({"coder": "opencode/alt-modell"},
                         data["profile"]["kostenlos"])
        self.assertIn("guenstig", data["profile"])
        self.assertEqual({"tester": "coder"}, data["rollen"])
        self.assertEqual("kostenlos", data["aktiv"])
        for name in STANDARD_PROFILES:
            self.assertIn(name, data["profile"])

    def test_profiles_load_repairs_an_invalid_aktiv(self):
        self.write_profiles({
            "aktiv": "gibtsnicht",
            "rollen": {},
            "profile": {"kostenlos": {}},
        })

        data = self.cli.profiles_load()

        self.assertEqual("default", data["aktiv"])


class DefaultRoleModelsTest(Gh57CliFixture):
    """default_role_models(): Rolle → Modell des ersten globalen Agenten."""

    def test_default_role_models_takes_the_first_global_agent_per_role(self):
        self.write_profiles({"rollen": {
            "a-coder": "coder", "b-coder": "coder", "rev": "reviewer"}})
        self.write_agent("a-coder", "opencode/test-modell")
        self.write_agent("b-coder", "opencode/vibe-modell")
        self.write_agent("rev", "opencode/anderes-modell")

        result = self.cli.default_role_models()

        self.assertEqual({
            "coder": "opencode/test-modell",
            "reviewer": "opencode/anderes-modell",
        }, result)

    def test_default_role_models_is_empty_without_role_assignment(self):
        self.assertFalse((self.state / "profiles.json").exists())

        self.assertEqual({}, self.cli.default_role_models())

    def test_default_role_models_reports_empty_for_agents_without_model(self):
        self.write_profiles({"rollen": {"stiller": "coder"}})
        self.write_agent("stiller", None)

        result = self.cli.default_role_models()

        self.assertFalse(result.get("coder"),
                         "Rolle ohne Modell darf keinen Platzhalter liefern")


# ---------------------------------------------------------------------------
# Profile: API-Verträge (create/save/delete/backup/restore)
# ---------------------------------------------------------------------------

class ProfilesApiTest(ProfilesApiDashboard):
    """POST /api/profiles: create, save-Mischung, delete-Schutz, Backup/Restore."""

    def test_create_adds_an_empty_profile(self):
        status, body = self.post("/api/profiles", {
            "action": "create", "name": "Meine Wahl 2"})

        self.assertEqual(200, status, str(body))
        self.assertTrue(body["ok"], str(body))
        info = self.get_json("/api/agents")
        created = info["profiles"]["profile"]["Meine Wahl 2"]
        self.assertTrue(
            all(not value for value in created.values()),
            "Angelegtes Profil beginnt ohne Modellwerte")
        # Grenze 40 Zeichen ist noch gültig.
        status, body = self.post("/api/profiles", {
            "action": "create", "name": "a" * 40})
        self.assertEqual(200, status, str(body))
        self.assertTrue(body["ok"], str(body))

    def test_create_rejects_invalid_standard_and_duplicate_names(self):
        for name in ("", "a/b", "a" * 41, "ähm", "meins!"):
            with self.subTest(name=name):
                status, body = self.post("/api/profiles", {
                    "action": "create", "name": name})
                self.assertFalse(body["ok"], str(body))
                self.assertTrue(body.get("message"), str(body))
        for name in STANDARD_PROFILES:
            with self.subTest(name=name):
                status, body = self.post("/api/profiles", {
                    "action": "create", "name": name})
                self.assertFalse(body["ok"], str(body))
                self.assertTrue(body.get("message"), str(body))
        # Doppelt anlegen ist ebenfalls abgelehnt (erster Lauf legt an).
        _status, first = self.post("/api/profiles", {
            "action": "create", "name": "doppelt"})
        self.assertTrue(first["ok"], str(first))
        _status, body = self.post("/api/profiles", {
            "action": "create", "name": "doppelt"})
        self.assertFalse(body["ok"], str(body))
        info = self.get_json("/api/agents")
        self.assertEqual(
            set(STANDARD_PROFILES) | {"doppelt"},
            set(info["profiles"]["profile"]),
            "Abgelehnte Anlagen dürfen profiles.json nicht verändern")

    def test_save_merges_named_profiles_instead_of_replacing_them(self):
        self.write_profiles({
            "aktiv": "default",
            "rollen": {},
            "profile": {
                "keep": {"coder": "opencode/behalt-modell",
                         "reviewer": "opencode/behalt-review"},
            },
        })

        status, body = self.post("/api/profiles", {
            "action": "save",
            "data": {"rollen": {"tester": "coder"},
                     "profile": {"change": {"coder": "opencode/neu-coder"}}},
        })

        self.assertEqual(200, status, str(body))
        self.assertTrue(body["ok"], str(body))
        profiles = self.get_json("/api/agents")["profiles"]
        self.assertEqual(
            {"coder": "opencode/behalt-modell",
             "reviewer": "opencode/behalt-review"},
            profiles["profile"]["keep"],
            "Nicht übergebene Profile bleiben beim Speichern erhalten")
        self.assertEqual({"coder": "opencode/neu-coder"},
                         profiles["profile"]["change"])
        self.assertEqual({"tester": "coder"}, profiles["rollen"])

    def test_save_rejects_a_non_empty_default_profile_value(self):
        self.write_profiles({
            "aktiv": "default",
            "rollen": {},
            "profile": {"keep": {"coder": "opencode/behalt-modell"}},
        })
        before = (self.state / "profiles.json").read_text(encoding="utf-8")

        status, body = self.post("/api/profiles", {
            "action": "save",
            "data": {"rollen": {},
                     "profile": {"default": {"coder": "opencode/x"}}},
        })

        self.assertFalse(body["ok"], str(body))
        self.assertTrue(body.get("message"), str(body))
        self.assertEqual(
            before, (self.state / "profiles.json").read_text(encoding="utf-8"),
            "Abgelehntes Speichern verändert profiles.json nicht")

    def test_delete_rejects_standard_profiles(self):
        for name in ("default", "free"):
            with self.subTest(name=name):
                status, body = self.post("/api/profiles", {
                    "action": "delete", "name": name})
                self.assertFalse(body["ok"], str(body))
                self.assertIn(
                    "Standardprofil", body.get("message", ""),
                    "Ablehnung muss das Standardprofil benennen")
                info = self.get_json("/api/agents")
                self.assertIn(name, info["profiles"]["profile"])

    def test_delete_removes_a_custom_profile_backs_up_and_falls_back_to_default(
            self):
        self.write_profiles({
            "aktiv": "meins",
            "rollen": {},
            "profile": {"meins": {"coder": "opencode/test-modell"}},
        })

        status, body = self.post("/api/profiles", {
            "action": "delete", "name": "meins"})

        self.assertEqual(200, status, str(body))
        self.assertTrue(body["ok"], str(body))
        info = self.get_json("/api/agents")
        self.assertNotIn("meins", info["profiles"]["profile"])
        self.assertEqual(
            "default", info["profiles"]["aktiv"],
            "Löschen des aktiven Profils fällt auf 'default' zurück")
        self.assertTrue(self.backup_names("profile-backups"),
                        "Vor dem Löschen wurde profiles.json gesichert")

    def test_backup_writes_a_profile_backup_and_names_it(self):
        self.write_profiles({
            "aktiv": "default", "rollen": {}, "profile": {"alt": {}}})

        status, body = self.post("/api/profiles", {"action": "backup"})

        self.assertEqual(200, status, str(body))
        self.assertTrue(body["ok"], str(body))
        names = self.backup_names("profile-backups")
        self.assertEqual(1, len(names), "Genau eine Sicherung wurde abgelegt")
        self.assertIn(names[0], json.dumps(body, ensure_ascii=False),
                      "Antwort nennt den Sicherungsnamen")

    def test_restore_recovers_the_backed_up_state_after_confirmation(self):
        self.write_profiles({
            "aktiv": "alt", "rollen": {"tester": "coder"},
            "profile": {"alt": {"coder": "opencode/alt-modell"}}})
        _status, backup_body = self.post("/api/profiles", {"action": "backup"})
        self.assertTrue(backup_body["ok"], str(backup_body))
        backup_name = self.backup_names("profile-backups")[0]
        status, _saved = self.post("/api/profiles", {
            "action": "save",
            "data": {"rollen": {}, "profile": {"neu": {}}}})
        self.assertEqual(200, status)

        status, body = self.post("/api/profiles", {
            "action": "restore", "name": backup_name, "confirm": True})

        self.assertEqual(200, status, str(body))
        self.assertTrue(body["ok"], str(body))
        view = body.get("profiles")
        self.assertIsInstance(view, dict,
                              "Antwort enthält die neu geladene Ansicht")
        self.assertIn("alt", view["profile"])
        self.assertNotIn("neu", view["profile"])
        self.assertEqual("alt", view["aktiv"])
        self.assertEqual(
            2, len(self.backup_names("profile-backups")),
            "Vor der Wiederherstellung wurde ein Sicherheits-Snapshot gelegt")

    def test_restore_without_confirmation_is_rejected_like_agents_file(self):
        self.write_profiles({
            "aktiv": "default", "rollen": {}, "profile": {"alt": {}}})
        _status, backup_body = self.post("/api/profiles", {"action": "backup"})
        self.assertTrue(backup_body["ok"], str(backup_body))
        backup_name = self.backup_names("profile-backups")[0]
        _status, changed = self.post("/api/profiles", {
            "action": "save",
            "data": {"rollen": {}, "profile": {"neu": {}}}})
        self.assertTrue(changed["ok"], str(changed))

        status, body = self.post("/api/profiles", {
            "action": "restore", "name": backup_name})

        self.assertFalse(body["ok"], str(body))
        self.assertEqual(
            "rejected", body.get("error", {}).get("code"),
            "Fehlermuster wie agents_file (400 rejected)")
        message = body.get("message", "")
        self.assertTrue(
            "confirm" in message or "Bestätigung" in message,
            "Ablehnung verweist auf die Bestätigung: " + message)


# ---------------------------------------------------------------------------
# Profile: Fallback-Kette beim Anwenden (Profil → Rollenmodell → Vibe-Agent)
# ---------------------------------------------------------------------------

class ProfilesApplyFallbackTest(ProfilesApiDashboard):
    """POST /api/profiles {action:'use'} löst die Modellkette je Rolle auf.

    Vertrag (docs/features/GH-57.md, Abschnitt 2, ``use``): ``profile[rolle]``
    → ``default_models[rolle]`` (Modell des ersten globalen Agenten der Rolle)
    → Modell des Vibe-Agenten. Aufgelöste Werte werden wie explizite Werte auf
    Verfügbarkeit geprüft; leere Fallbacks werden mit Hinweis übersprungen,
    ohne etwas zu schreiben.

    Beobachtet wird ausschließlich das nach außen sichtbare Verhalten: die
    ``model:``-Zeile der Agentendateien und die Antwort der API (``ok``,
    ``message``). Die Modellliste stammt aus dem Fake-``opencode`` des
    Dashboards (``STUB_MODELS``), es findet kein echter Modellaufruf statt.

    Fall 1 prüft die Quelle der Kette bewusst über den zweiten Agenten
    derselben Rolle: Bliebe dieser unverändert, wäre der Fall von der heutigen
    Skip-Logik nicht zu unterscheiden (vacuous test); erst wenn er das Modell
    des ERSTEN Agenten erhält, ist „erster Agent als Quelle" beobachtbar.
    """

    PROFILE = "pruefung"

    def write_agent(self, name, model=None):
        (self.agents / (name + ".md")).write_text(
            agent_text(model), encoding="utf-8")

    def agent_file(self, name):
        return (self.agents / (name + ".md")).read_text(encoding="utf-8")

    def model_of(self, name):
        """Modell aus der ``model:``-Zeile der Agentendatei ('' ohne Zeile)."""
        match = re.search(r"^model:[ \t]*(\S+)[ \t]*$",
                          self.agent_file(name), flags=re.M)
        return match.group(1) if match else ""

    def use_profile(self):
        return self.post(
            "/api/profiles", {"action": "use", "profile": self.PROFILE})

    def test_apply_falls_back_to_the_first_global_agent_model_of_the_role(self):
        # Vorbedingung: kein Profilwert für 'coder'; zwei globale Agenten
        # tragen die Rolle und haben jeweils ein eigenes Modell.
        self.write_profiles({
            "aktiv": self.PROFILE,
            "rollen": {"a-coder": "coder", "b-coder": "coder"},
            "profile": {self.PROFILE: {}},
        })
        self.write_agent("a-coder", "opencode/test-modell")
        self.write_agent("b-coder", "opencode/neu")

        status, body = self.use_profile()

        # Erwartung: die Rolle wird mit dem Modell des ERSTEN Agenten belegt
        # (alphabetisch/Dateireihenfolge: a-coder); das Modell des zweiten
        # Agenten ist nicht die Quelle.
        self.assertEqual(200, status, str(body))
        self.assertTrue(body["ok"], str(body))
        self.assertIn("Angewendet", body.get("message", ""), str(body))
        self.assertEqual("opencode/test-modell", self.model_of("a-coder"))
        self.assertEqual(
            "opencode/test-modell", self.model_of("b-coder"),
            "Die Rolle erhält das Modell des ersten Agenten; das eigene "
            "Modell des zweiten Agenten dient nicht als Fallback")

    def test_apply_falls_back_to_the_vibe_agent_model_when_no_role_model_exists(
            self):
        # Vorbedingung: weder Profilwert noch Rollenmodell (der Agent der
        # Rolle hat kein Modell); der Vibe-Agent ist konfiguriert.
        self.write_profiles({
            "aktiv": self.PROFILE,
            "rollen": {"coder-x": "coder", "vibe-agent": "vibe"},
            "profile": {self.PROFILE: {}},
        })
        self.write_agent("coder-x", None)
        self.write_agent("vibe-agent", "opencode/vibe-modell")

        status, body = self.use_profile()

        self.assertEqual(200, status, str(body))
        self.assertTrue(body["ok"], str(body))
        self.assertIn("Angewendet", body.get("message", ""), str(body))
        self.assertEqual(
            "opencode/vibe-modell", self.model_of("coder-x"),
            "Ohne Profil- und Rollenmodell gilt das Modell des Vibe-Agenten")

    def test_apply_skips_an_agent_whose_fallback_model_is_empty(self):
        # Vorbedingung: Profilwert leer, Rollenmodell leer (Agent ohne Modell),
        # kein Vibe-Agent vorhanden.
        self.write_profiles({
            "aktiv": self.PROFILE,
            "rollen": {"coder-x": "coder"},
            "profile": {self.PROFILE: {}},
        })
        self.write_agent("coder-x", None)
        before = self.agent_file("coder-x")

        status, body = self.use_profile()

        # Erwartung: kein Fehler, Hinweis auf das Überspringen, nichts
        # geschrieben (keine Modellzeile).
        self.assertEqual(200, status, str(body))
        self.assertTrue(body["ok"],
                        "Überspringen ist kein Fehler: " + str(body))
        message = body.get("message", "")
        self.assertIn("übersprungen", message,
                      "Der Hinweis nennt das Überspringen: " + message)
        self.assertIn("coder-x", message,
                      "Der Hinweis nennt den betroffenen Agenten: " + message)
        self.assertEqual("", self.model_of("coder-x"),
                         "Ohne aufgelöstes Modell entsteht keine Modellzeile")
        self.assertEqual(before, self.agent_file("coder-x"))

    def test_apply_rejects_an_explicit_unavailable_model_like_today(self):
        # Vorbedingung: der Profilwert ist gesetzt, steht aber nicht in der
        # Modellliste des aktiven Harness.
        self.write_profiles({
            "aktiv": self.PROFILE,
            "rollen": {"coder-x": "coder"},
            "profile": {self.PROFILE: {"coder": "opencode/gibts-nicht"}},
        })
        self.write_agent("coder-x", "opencode/test-modell")
        before = self.agent_file("coder-x")

        status, body = self.use_profile()

        # Erwartung: Fehler wie heute (HTTP 400, ok:false), Meldung nennt
        # Modell und Anbieterhinweis, keine Datei verändert.
        self.assertEqual(400, status, str(body))
        self.assertFalse(body["ok"], str(body))
        message = body.get("message", "")
        self.assertIn("opencode/gibts-nicht", message,
                      "Die Meldung nennt das nicht verfügbare Modell: "
                      + message)
        self.assertIn("Anbieter", message,
                      "Die Meldung verweist auf den Anbieter: " + message)
        self.assertEqual(before, self.agent_file("coder-x"),
                         "Nicht verfügbare Modelle ändern keine Agentendatei")


# ---------------------------------------------------------------------------
# Globale AGENTS.md: Backup-/Restore-Verträge
# ---------------------------------------------------------------------------

class GlobalAgentsFileTest(ProfilesApiDashboard):
    """GET/POST /api/global_agents_file: backups, backup, restore."""

    def agents_md(self):
        return self.home / ".config" / "opencode" / "AGENTS.md"

    def test_view_lists_backups(self):
        view = self.get_json("/api/global_agents_file")

        self.assertIn("backups", view)
        self.assertEqual([], view["backups"])

    def test_backup_requires_an_existing_file_and_then_succeeds(self):
        self.assertFalse(self.agents_md().exists())
        _status, body = self.post("/api/global_agents_file", {
            "action": "backup"})
        self.assertFalse(body["ok"], str(body))
        self.assertTrue(body.get("message"), str(body))
        self.assertEqual([], self.backup_names("global-agents-backups"))

        status, created = self.post("/api/global_agents_file", {
            "action": "create"})
        self.assertEqual(200, status, str(created))
        self.assertTrue(created["ok"], str(created))
        status, body = self.post("/api/global_agents_file", {
            "action": "backup"})

        self.assertEqual(200, status, str(body))
        self.assertTrue(body["ok"], str(body))
        names = self.backup_names("global-agents-backups")
        self.assertEqual(1, len(names))
        view = self.get_json("/api/global_agents_file")
        self.assertEqual(names, view["backups"])

    def test_restore_recovers_content_with_a_safety_snapshot(self):
        self.agents_md().write_text("Inhalt A", encoding="utf-8")
        _status, backup_body = self.post("/api/global_agents_file", {
            "action": "backup"})
        self.assertTrue(backup_body["ok"], str(backup_body))
        backup_name = self.backup_names("global-agents-backups")[0]
        view = self.get_json("/api/global_agents_file")
        _status, saved = self.post("/api/global_agents_file", {
            "action": "save", "text": "Inhalt C", "digest": view["digest"]})
        self.assertTrue(saved["ok"], str(saved))

        status, body = self.post("/api/global_agents_file", {
            "action": "restore", "name": backup_name, "confirm": True})

        self.assertEqual(200, status, str(body))
        self.assertTrue(body["ok"], str(body))
        restored = body.get("view")
        self.assertIsInstance(restored, dict,
                              "Antwort enthält die frische Ansicht")
        self.assertEqual("Inhalt A", restored["text"])
        self.assertTrue(restored.get("digest"))
        self.assertIn("backups", restored)
        self.assertEqual("Inhalt A",
                         self.agents_md().read_text(encoding="utf-8"))
        self.assertEqual(
            2, len(self.backup_names("global-agents-backups")),
            "Sicherheits-Snapshot vor der Wiederherstellung")

    def test_restore_without_confirmation_is_rejected(self):
        self.agents_md().write_text("Inhalt A", encoding="utf-8")
        _status, backup_body = self.post("/api/global_agents_file", {
            "action": "backup"})
        self.assertTrue(backup_body["ok"], str(backup_body))
        backup_name = self.backup_names("global-agents-backups")[0]
        view = self.get_json("/api/global_agents_file")
        _status, saved = self.post("/api/global_agents_file", {
            "action": "save", "text": "Inhalt C", "digest": view["digest"]})
        self.assertTrue(saved["ok"], str(saved))

        status, body = self.post("/api/global_agents_file", {
            "action": "restore", "name": backup_name})

        self.assertFalse(body["ok"], str(body))
        self.assertEqual("rejected", body.get("error", {}).get("code"))
        message = body.get("message", "")
        self.assertTrue(
            "confirm" in message or "Bestätigung" in message,
            "Ablehnung verweist auf die Bestätigung: " + message)
        self.assertEqual("Inhalt C",
                         self.agents_md().read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Models-Refresh: Cache, Stand, Fehler
# ---------------------------------------------------------------------------

class ModelsRefreshTest(ModelsDashboard):
    """POST /api/agents {action:'refresh_models'} und Cache-Nutzung."""

    def test_get_runs_the_harness_live_until_a_cache_exists(self):
        info = self.get_json("/api/agents")

        self.assertEqual(STUB_MODELS, info["models"])
        self.assertEqual("", info["models_stand"])
        self.assertEqual("", info["models_error"])
        self.assertGreaterEqual(
            self.stub_calls(), 1,
            "Ohne Cache läuft GET /api/agents live gegen den Harness")

    def test_refresh_models_writes_the_cache_and_answers_fresh(self):
        status, body = self.post("/api/agents", {"action": "refresh_models"})

        self.assertEqual(200, status, str(body))
        self.assertTrue(body["ok"], str(body))
        cache = json.loads(
            (self.state / "models-cache.json").read_text(encoding="utf-8"))
        self.assert_utc_iso(cache["stand"])
        self.assertEqual(STUB_MODELS, cache["models"])
        stands = _find_values(body, "models_stand")
        self.assertTrue(
            stands, "Antwort enthält die frische agents_info mit models_stand")
        for value in stands:
            self.assertEqual(cache["stand"], value)
        self.assertGreaterEqual(
            self.stub_calls(), 1,
            "Der Refresh holt die Modelle live vom Harness")

    def test_get_reuses_the_cache_without_running_the_harness_again(self):
        _status, refreshed = self.post("/api/agents", {
            "action": "refresh_models"})
        self.assertTrue(refreshed["ok"], str(refreshed))
        cache = json.loads(
            (self.state / "models-cache.json").read_text(encoding="utf-8"))
        calls_after_refresh = self.stub_calls()

        for _round in range(2):
            info = self.get_json("/api/agents")
            self.assertEqual(cache["stand"], info["models_stand"])
            self.assertEqual(cache["models"], info["models"])
            self.assertEqual("", info["models_error"])

        self.assertEqual(
            calls_after_refresh, self.stub_calls(),
            "GET /api/agents nutzt den Cache und startet den Stub nicht erneut")

    def test_agents_info_reports_default_models_and_standard_profiles(self):
        (self.agents / "tester.md").write_text(
            agent_text("opencode/test-modell"), encoding="utf-8")
        self.write_profiles({"rollen": {"tester": "coder"}})

        info = self.get_json("/api/agents")

        self.assertEqual({"coder": "opencode/test-modell"},
                         info["default_models"])
        self.assertEqual(list(STANDARD_PROFILES), info["standard_profiles"])


class ModelsBrokenApiTest(ModelsBrokenDashboard):
    """Fehlerpfad: Live-Fehler sichtbar machen, Cache unangetastet lassen."""

    def test_live_models_error_is_reported_and_a_failed_refresh_keeps_the_cache(
            self):
        info = self.get_json("/api/agents")

        self.assertTrue(info["models_error"],
                        "Fehlgeschlagener Live-Lauf meldet models_error")
        self.assertEqual("", info["models_stand"])
        self.assertEqual([], info["models"])

        cache_path = self.state / "models-cache.json"
        seeded = '{"stand": "2020-01-01T00:00:00Z", "models": ["opencode/alt"]}'
        cache_path.write_text(seeded, encoding="utf-8")
        _status, body = self.post("/api/agents", {"action": "refresh_models"})

        self.assertFalse(body["ok"], str(body))
        self.assertTrue(body.get("message"), str(body))
        self.assertEqual(
            seeded, cache_path.read_text(encoding="utf-8"),
            "Fehlgeschlagener Refresh verändert den Cache nicht")


# ---------------------------------------------------------------------------
# Security-Restart: Antwortfelder, Token-Erhalt, geordneter Neustart
# ---------------------------------------------------------------------------

class SecurityRestartTest(RestartDashboard):
    """POST /api/security {action:'restart'} (eigene Serverinstanz)."""

    def test_restart_answers_with_planned_port_bind_and_token_and_restarts(
            self):
        security = self.get_json("/api/security")
        self.assertTrue(
            security["restart_required"],
            "Vorbedingung: ui.json plant abweichenden Port")

        status, body = self.post("/api/security", {"action": "restart"})

        self.assertEqual(200, status, str(body))
        self.assertTrue(body["ok"], str(body))
        self.assertTrue(body.get("message"), str(body))
        self.assertEqual(self.planned_port, body.get("port"),
                         "Antwort nennt den geplanten Port aus ui.json")
        self.assertEqual("127.0.0.1", body.get("bind"),
                         "Antwort nennt die geplante Bind-Adresse")
        self.assertEqual(self.token, body.get("token"),
                         "Antwort nennt das aktuelle Session-Token")

        self.assertTrue(
            wait_for_port(self.planned_port),
            "Nach der Antwort dient der geplante Port wieder (Neustart)")
        token_file = self.log_dir / "web.token"
        self.assertEqual(
            self.token, token_file.read_text(encoding="utf-8").strip(),
            "Das Session-Token bleibt über den Neustart erhalten")
        # Ab hier dient der neu gestartete Prozess am geplanten Port.
        self.port = self.planned_port
        restarted = self.get_json("/api/security")
        self.assertFalse(
            restarted["restart_required"],
            "Nach dem Neustart stimmen geplanter und laufender Port überein")


class PrepareRuntimeTokenTest(unittest.TestCase):
    """prepare_runtime + VIBE_WEB_KEEP_TOKEN (In-Prozess, ohne Server)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.runtime = cls.root / "_logs"
        cls.runtime.mkdir(parents=True, exist_ok=True)
        cls.web = load_web_module(cls.runtime)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        # Das geladene Modul registriert bin/vibe als sys.modules["vibe"];
        # der Eintrag ist nur für diesen Test gültig.
        sys.modules.pop("vibe", None)

    def token_path(self):
        return self.runtime / "web.token"

    def test_keeps_the_existing_token_when_the_flag_is_set(self):
        self.token_path().write_text("BESTAND-TOKEN", encoding="utf-8")

        with mock.patch.dict(os.environ, {"VIBE_WEB_KEEP_TOKEN": "1"}):
            token, _instance = self.web.prepare_runtime()

        self.assertEqual("BESTAND-TOKEN", token)
        self.assertEqual(
            "BESTAND-TOKEN",
            self.token_path().read_text(encoding="utf-8"))

    def test_generates_a_new_token_without_the_flag(self):
        self.token_path().write_text("BESTAND-TOKEN", encoding="utf-8")

        token, _instance = self.web.prepare_runtime()

        self.assertNotEqual("BESTAND-TOKEN", token)
        self.assertEqual(
            token, self.token_path().read_text(encoding="utf-8"))


class BackendDuplicationSanityTest(unittest.TestCase):
    """Sanity-Check: Duplikate im Backend sind entfernt (Vertrag Punkt 5)."""

    def test_restart_required_security_data_and_reload_ui_data_exist_once(self):
        source = WEB.read_text(encoding="utf-8")
        for name in ("restart_required", "security_data", "reload_ui_data"):
            count = len(
                re.findall(r"^def " + name + r"\(", source, flags=re.M))
            self.assertEqual(
                1, count,
                name + " ist mehrfach definiert "
                "(toter Code wurde nicht entfernt)")


if __name__ == "__main__":
    unittest.main()
