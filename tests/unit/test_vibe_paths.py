"""Tests für Pfadmodell und Konfigurationspriorität (V-006).

Geprüft wird das Modul ``bin/vibe_paths.py`` und seine Verwendung in
``bin/vibe``, ``bin/vibe-web.py``, ``bin/vibe_mcp.py`` und
``bin/vibe-run.sh``:

* Quellen, Installation, Laufzeit und Zustand sind getrennte, benannte Pfade.
* Das Dev-Profil nutzt einen eigenen Arbeitsbereich, eigene Ports und eine
  eigene tmux-Sitzung; die produktive Instanz bleibt unberührt.
* Persönliche Einstellungen überschreiben mitgelieferte Defaults; Umgebung
  und ausdrückliche Übergaben überschreiben in dieser Reihenfolge die Datei.
* Fehlende Verzeichnisse werden bei der Auflösung nicht angelegt; erst ein
  ausdrücklicher Aufruf von ``ensure()`` erzeugt sie.
* Pfade mit Leerzeichen bleiben ein einziger Pfad — im CLI, im Dashboard und
  im Paketläufer.
* Der Import von ``bin/vibe`` und ``bin/vibe-web.py`` startet keine Prozesse,
  öffnet keinen Server und schreibt keine Laufzeitdateien.
"""
import contextlib
import hashlib
import http.client
import importlib.machinery
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "bin" / "vibe"
WEB = REPO / "bin" / "vibe-web.py"
MCP = REPO / "bin" / "vibe_mcp.py"
RUNNER = REPO / "bin" / "vibe-run.sh"
PATHS_MODULE = REPO / "bin" / "vibe_paths.py"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support

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
    "VIBE_NO_CONTAINER",
    "XDG_CONFIG_HOME",
    "HOME",
)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def load_paths_module():
    """Lädt bin/vibe_paths.py unter einem eigenen Modulnamen."""
    loader = importlib.machinery.SourceFileLoader("vibe_paths_v006", str(PATHS_MODULE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def load_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@contextlib.contextmanager
def clean_environment(values):
    """Setzt eine isolierte Umgebung und stellt sie danach wieder her."""
    saved = {key: os.environ.get(key) for key in ENV_KEYS}
    for key in ENV_KEYS:
        os.environ.pop(key, None)
    os.environ.update({key: str(value) for key, value in values.items()})
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def write_config(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class PathResolutionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.workspace = self.root / "workspace"
        self.paths = load_paths_module()

    def tearDown(self):
        self.tmp.cleanup()

    def resolve(self, **kwargs):
        environ = {"HOME": str(self.home)}
        environ.update(kwargs.pop("environ", {}))
        return self.paths.resolve(environ=environ, **kwargs)

    def test_default_profile_separates_source_installation_and_runtime(self):
        result = self.resolve(environ={"VIBE": str(self.workspace)})

        self.assertEqual(result.profile, "prod")
        self.assertEqual(result.workspace, str(self.workspace))
        self.assertEqual(result.install, str(self.workspace / "_toolchain"))
        self.assertEqual(result.runtime, str(self.workspace / "_logs"))
        self.assertEqual(result.state, result.install)
        self.assertEqual(result.source, str(REPO))
        self.assertEqual(result.code_bin, str(REPO / "bin"))
        self.assertEqual(result.ui_port, 8787)
        self.assertEqual(result.opencode_port, 4096)
        self.assertEqual(result.opencode_url, "http://127.0.0.1:4096")
        self.assertEqual(result.ui_bind, "127.0.0.1")
        self.assertEqual(result.container, "android-dev")
        self.assertEqual(
            result.agents_dir, str(self.home / ".config" / "opencode" / "agents")
        )
        self.assertEqual(
            result.config_file, str(self.home / ".config" / "vibe" / "config.json")
        )

    def test_workspace_with_spaces_stays_a_single_path(self):
        spacey = self.root / "mein arbeitsbereich"

        result = self.resolve(environ={"VIBE": str(spacey)})

        self.assertEqual(result.workspace, str(spacey))
        self.assertEqual(result.install, str(spacey / "_toolchain"))
        self.assertEqual(result.runtime, str(spacey / "_logs"))
        self.assertEqual(result.child_env()["VIBE"], str(spacey))

        self.paths.ensure(result, "runtime")
        self.assertTrue((spacey / "_logs").is_dir())

    def test_dev_profile_uses_its_own_paths_and_ports(self):
        dev = self.root / "dev arbeitsbereich"

        result = self.resolve(profile="dev", environ={"VIBE": str(dev)})

        self.assertEqual(result.profile, "dev")
        self.assertEqual(result.workspace, str(dev))
        self.assertEqual(result.install, str(dev / "_toolchain"))
        self.assertEqual(result.runtime, str(dev / "_logs"))
        self.assertEqual(result.ui_port, 8788)
        self.assertEqual(result.opencode_port, 4097)
        self.assertEqual(result.source, str(REPO))
        self.assertEqual(result.code_bin, str(REPO / "bin"))

    def test_dev_profile_has_a_default_workspace_next_to_production(self):
        result = self.resolve(profile="dev")

        self.assertEqual(result.workspace, str(self.home / "VibeCode-dev"))
        self.assertNotEqual(result.workspace, self.paths.default_workspace({"HOME": str(self.home)}))
        self.assertEqual(result.ui_port, 8788)

    def test_dev_profile_refuses_the_productive_default_workspace(self):
        productive = self.paths.default_workspace({"HOME": str(self.home)})

        with self.assertRaises(self.paths.ConfigError) as raised:
            self.resolve(profile="dev", environ={"VIBE": productive})

        self.assertIn("produktiv", str(raised.exception).lower())
        self.assertIn("VIBE_RUNTIME", str(raised.exception))

    def test_dev_profile_refuses_configured_productive_paths(self):
        write_config(
            self.home / ".config" / "vibe" / "config.json",
            {"workspace": str(self.workspace)},
        )

        with self.assertRaises(self.paths.ConfigError) as raised:
            self.resolve(profile="dev", environ={"VIBE": str(self.workspace)})

        self.assertIn("produktiven", str(raised.exception))
        self.assertIn("VIBE_RUNTIME", str(raised.exception))

    def test_dev_profile_allows_a_shared_workspace_with_separate_paths(self):
        write_config(
            self.home / ".config" / "vibe" / "config.json",
            {"workspace": str(self.workspace)},
        )
        separate = {
            "install": str(self.root / "dev-toolchain"),
            "runtime": str(self.root / "dev-logs"),
            "state": str(self.root / "dev-state"),
        }

        result = self.resolve(
            profile="dev",
            environ={"VIBE": str(self.workspace)},
            overrides=separate,
        )

        self.assertEqual(result.workspace, str(self.workspace))
        self.assertEqual(result.install, separate["install"])
        self.assertEqual(result.runtime, separate["runtime"])
        self.assertEqual(result.state, separate["state"])

    def test_missing_directories_are_not_created_by_resolution(self):
        missing = self.root / "fehlt-noch"

        result = self.resolve(environ={"VIBE": str(missing)})

        self.assertFalse(missing.exists())
        for path in (result.workspace, result.install, result.runtime, result.state):
            self.assertFalse(Path(path).exists(), path)

    def test_ensure_creates_only_the_requested_directories(self):
        result = self.resolve(environ={"VIBE": str(self.workspace)})

        created = self.paths.ensure(result, "runtime")

        self.assertTrue((self.workspace / "_logs").is_dir())
        self.assertFalse((self.workspace / "_toolchain").exists())
        self.assertEqual([str(self.workspace / "_logs")], created)

    def test_personal_settings_override_defaults(self):
        config = self.home / ".config" / "vibe" / "config.json"
        write_config(
            config,
            {
                "workspace": str(self.root / "eigener Arbeitsbereich"),
                "ui_port": 9101,
                "opencode_port": 9102,
                "ui_bind": "localhost",
                "container": "eigener-container",
                "agents_dir": str(self.root / "agents"),
                "state": str(self.root / "state"),
            },
        )

        result = self.resolve()

        self.assertEqual(result.config_file, str(config))
        self.assertEqual(result.workspace, str(self.root / "eigener Arbeitsbereich"))
        self.assertEqual(result.state, str(self.root / "state"))
        self.assertEqual(
            result.install, str(self.root / "eigener Arbeitsbereich" / "_toolchain")
        )
        self.assertEqual(result.ui_port, 9101)
        self.assertEqual(result.opencode_port, 9102)
        self.assertEqual(result.opencode_url, "http://127.0.0.1:9102")
        self.assertEqual(result.ui_bind, "127.0.0.1")
        self.assertEqual(result.container, "eigener-container")
        self.assertEqual(result.agents_dir, str(self.root / "agents"))

    def test_profile_sections_override_top_level_settings(self):
        dev = self.root / "dev"
        write_config(
            self.home / ".config" / "vibe" / "config.json",
            {
                "ui_port": 9101,
                "profiles": {"dev": {"ui_port": 9203, "container": "dev-box"}},
            },
        )

        productive = self.resolve(environ={"VIBE": str(self.workspace)})
        development = self.resolve(profile="dev", environ={"VIBE": str(dev)})

        self.assertEqual(productive.ui_port, 9101)
        self.assertEqual(productive.container, "android-dev")
        self.assertEqual(development.ui_port, 9203)
        self.assertEqual(development.container, "dev-box")
        self.assertEqual(development.runtime, str(dev / "_logs"))

    def test_environment_overrides_personal_settings(self):
        write_config(
            self.home / ".config" / "vibe" / "config.json",
            {"ui_port": 9101, "opencode_port": 9102, "container": "aus-datei"},
        )

        result = self.resolve(
            environ={
                "VIBE_UI_PORT": "9202",
                "VIBE_OPENCODE_PORT": "9204",
                "VIBE_CONTAINER": "aus-umgebung",
                "VIBE": str(self.workspace),
            }
        )

        self.assertEqual(result.ui_port, 9202)
        self.assertEqual(result.opencode_port, 9204)
        self.assertEqual(result.container, "aus-umgebung")

    def test_explicit_override_wins_over_environment_and_settings(self):
        write_config(
            self.home / ".config" / "vibe" / "config.json", {"ui_port": 9101}
        )

        result = self.resolve(
            environ={"VIBE_UI_PORT": "9202", "VIBE": str(self.workspace)},
            overrides={"ui_port": 9303, "runtime": str(self.root / "runtime")},
        )

        self.assertEqual(result.ui_port, 9303)
        self.assertEqual(result.runtime, str(self.root / "runtime"))

    def test_dev_profile_does_not_touch_the_productive_workspace(self):
        prod = self.root / "prod"
        prod_runtime = prod / "_logs"
        prod_runtime.mkdir(parents=True)
        sentinel = prod_runtime / "web.token"
        sentinel.write_text("prod", encoding="utf-8")
        before = sorted(path.relative_to(prod) for path in prod.rglob("*"))
        dev = self.root / "dev"

        result = self.resolve(profile="dev", environ={"VIBE": str(dev)})
        self.paths.ensure(result, "runtime", "state")

        self.assertTrue(dev.is_dir())
        self.assertEqual(sorted(path.relative_to(prod) for path in prod.rglob("*")), before)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "prod")

    def test_invalid_ports_are_rejected(self):
        for key in ("VIBE_UI_PORT", "VIBE_OPENCODE_PORT"):
            for value in ("70000", "0", "abc", "-1", "80.5"):
                with self.subTest(key=key, value=value):
                    with self.assertRaises(self.paths.ConfigError):
                        self.resolve(
                            environ={"VIBE": str(self.workspace), key: value}
                        )

    def test_bind_accepts_ip_literals_and_still_rejects_hostnames(self):
        # AP13 (Nutzerentscheidung, Reviewrunde 1): Standard bleibt Loopback,
        # eine ausdrücklich konfigurierte Netz-Bindung ist nur noch als
        # IPv4-Adressliteral (inklusive 0.0.0.0) zulässig; IPv6 wird für die
        # Bind-Adresse ausdrücklich ausgeschlossen (Heimnetz — IPv4 genügt).
        # Hostnamen außer "localhost" bleiben abgelehnt
        # (DNS-Rebinding-Schutz).
        for value in ("0.0.0.0", "192.0.2.5"):
            with self.subTest(value=value):
                try:
                    result = self.resolve(
                        environ={"VIBE": str(self.workspace), "VIBE_UI_BIND": value}
                    )
                except self.paths.ConfigError as error:
                    self.fail(f"Adressliteral {value!r} wurde abgelehnt: {error}")
                self.assertEqual(result.ui_bind, value)
        for value in ("::", "::1", "2001:db8::1"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.resolve(
                        environ={"VIBE": str(self.workspace), "VIBE_UI_BIND": value}
                    )
        for value in ("example.test", "vibe", "192.0.2.something"):
            with self.subTest(value=value):
                with self.assertRaises(self.paths.ConfigError):
                    self.resolve(
                        environ={"VIBE": str(self.workspace), "VIBE_UI_BIND": value}
                    )

    def test_corrupt_personal_config_is_reported_instead_of_ignored(self):
        config = self.home / ".config" / "vibe" / "config.json"
        config.parent.mkdir(parents=True)
        config.write_text("{kein json", encoding="utf-8")

        with self.assertRaises(self.paths.ConfigError) as raised:
            self.resolve(environ={"VIBE": str(self.workspace)})

        self.assertIn(str(config), str(raised.exception))

    def test_broken_profile_section_is_reported(self):
        write_config(
            self.home / ".config" / "vibe" / "config.json",
            {"profiles": {"dev": ["kein", "objekt"]}},
        )

        with self.assertRaises(self.paths.ConfigError) as raised:
            self.resolve(profile="dev", environ={"VIBE": str(self.root / "dev")})

        self.assertIn("profiles.dev", str(raised.exception))


class ImportSideEffectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.workspace = self.root / "vibe"
        self.workspace.mkdir()
        self.saved_vibe = sys.modules.get("vibe")

    def tearDown(self):
        sys.modules.pop("vibe", None)
        if self.saved_vibe is not None:
            sys.modules["vibe"] = self.saved_vibe
        self.tmp.cleanup()

    def test_importing_the_cli_starts_no_process_and_writes_nothing(self):
        env = {"VIBE": self.workspace, "HOME": self.home, "VIBE_NO_CONTAINER": "1"}
        with clean_environment(env), mock.patch("subprocess.Popen") as popen, \
                mock.patch("subprocess.run") as run, mock.patch("os.execvp") as execvp:
            module = load_module(CLI, "vibe_import_v006")

        self.assertEqual(module.PATHS.workspace, str(self.workspace))
        self.assertEqual(module.PATHS.ui_port, 8787)
        popen.assert_not_called()
        run.assert_not_called()
        execvp.assert_not_called()
        self.assertFalse((self.workspace / "_logs").exists())
        self.assertFalse((self.workspace / "_toolchain").exists())
        self.assertFalse(self.home.exists())

    def test_importing_the_web_module_writes_no_token_or_instance_file(self):
        env = {"VIBE": self.workspace, "HOME": self.home, "VIBE_NO_CONTAINER": "1"}
        with clean_environment(env), mock.patch("subprocess.Popen") as popen, \
                mock.patch("subprocess.run") as run, mock.patch("os.execvp") as execvp, \
                mock.patch("http.server.ThreadingHTTPServer.__init__",
                           side_effect=AssertionError("Server darf beim Import nicht starten")):
            module = load_module(WEB, "vibe_web_import_v006")

        self.assertEqual(module.PATHS.workspace, str(self.workspace))
        self.assertEqual(module.PORT, 8787)
        self.assertIsNone(module.SRV)
        self.assertIsNone(module.TOKEN)
        self.assertIsNone(module.INSTANCE)
        popen.assert_not_called()
        run.assert_not_called()
        execvp.assert_not_called()
        self.assertFalse((self.workspace / "_logs").exists())
        self.assertFalse((self.workspace / "_logs" / "web.token").exists())
        self.assertFalse((self.workspace / "_logs" / "web.instance").exists())

    def test_importing_the_paths_module_starts_no_process(self):
        env = {"HOME": self.home, "VIBE": self.workspace}
        with clean_environment(env), mock.patch("subprocess.Popen") as popen, \
                mock.patch("subprocess.run") as run, mock.patch("os.execvp") as execvp:
            module = load_paths_module()

        self.assertEqual(module.default_workspace({"HOME": str(self.home)}),
                         str(self.home / "VibeCode"))
        popen.assert_not_called()
        run.assert_not_called()
        execvp.assert_not_called()


class CommandLinePathsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.config_dir = self.home / ".config"

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *arguments, env=None):
        environment = os.environ.copy()
        for key in ENV_KEYS:
            environment.pop(key, None)
        environment.update(
            {
                "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.config_dir),
                "VIBE": str(self.workspace),
                "VIBE_NO_CONTAINER": "1",
            }
        )
        environment.update(env or {})
        return subprocess.run(
            [sys.executable, str(CLI), "paths", *arguments],
            cwd=str(REPO),
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_cli_json_reports_the_resolved_paths_and_configured_ports(self):
        write_config(
            self.config_dir / "vibe" / "config.json",
            {"ui_port": 9151, "opencode_port": 9152},
        )

        completed = self.run_cli("--json")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        data = json.loads(completed.stdout)
        self.assertEqual(data["profile"], "prod")
        self.assertEqual(data["workspace"], str(self.workspace))
        self.assertEqual(data["install"], str(self.workspace / "_toolchain"))
        self.assertEqual(data["runtime"], str(self.workspace / "_logs"))
        self.assertEqual(data["state"], str(self.workspace / "_toolchain"))
        self.assertEqual(data["source"], str(REPO))
        self.assertEqual(data["ui_port"], 9151)
        self.assertEqual(data["opencode_port"], 9152)
        self.assertFalse((self.workspace / "_logs").exists())

    def test_cli_dev_profile_reports_its_own_port_and_workspace_with_spaces(self):
        dev = self.root / "dev arbeitsbereich"

        completed = self.run_cli(
            "--json", env={"VIBE_PROFILE": "dev", "VIBE": str(dev)}
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        data = json.loads(completed.stdout)
        self.assertEqual(data["profile"], "dev")
        self.assertEqual(data["workspace"], str(dev))
        self.assertEqual(data["ui_port"], 8788)
        self.assertEqual(data["opencode_port"], 4097)
        self.assertFalse(dev.exists())

    def test_cli_rejects_an_invalid_port_with_a_message(self):
        completed = self.run_cli("--json", env={"VIBE_UI_PORT": "70000"})

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Port", completed.stderr)
        self.assertEqual(completed.stdout.strip(), "")

    def test_cli_rejects_an_unknown_argument(self):
        completed = self.run_cli("--json", "unbekannt")

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("paths", completed.stderr)


class StatePathUsageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.workspace = self.root / "vibe"
        self.state = self.root / "state"
        self.saved_vibe = sys.modules.get("vibe")

    def tearDown(self):
        sys.modules.pop("vibe", None)
        if self.saved_vibe is not None:
            sys.modules["vibe"] = self.saved_vibe
        self.tmp.cleanup()

    def test_writable_configuration_and_backups_use_the_state_directory(self):
        env = {
            "VIBE": self.workspace,
            "VIBE_STATE": self.state,
            "HOME": self.home,
            "VIBE_NO_CONTAINER": "1",
        }
        with clean_environment(env):
            vibe = load_module(CLI, "vibe_state_v006")
            sys.modules["vibe"] = vibe
            mcp = load_module(MCP, "vibe_mcp_state_v006")

        self.assertEqual(vibe.CONF, str(self.state / "vibe.json"))
        self.assertEqual(vibe.PROFILES_FILE, str(self.state / "profiles.json"))
        self.assertEqual(vibe.FRITZ_SETTINGS, str(self.state / "fritz.json"))
        self.assertEqual(
            vibe.agent_backup_dir("global"), str(self.state / "agent-backups" / "global")
        )
        self.assertEqual(mcp.backup_dir(), str(self.state / "config-backups"))
        self.assertFalse(
            self.state.exists(), "Import darf den Zustandsordner nicht anlegen"
        )


class WebConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.workspace = self.root / "vibe"
        self.workspace.mkdir()
        self.config = self.home / ".config" / "vibe" / "config.json"
        self.port = free_port()
        self.proc = None
        self.log = None

    def tearDown(self):
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        if self.log is not None:
            self.log.close()
        self.tmp.cleanup()

    def environment(self, **extra):
        environment = os.environ.copy()
        for key in ENV_KEYS:
            environment.pop(key, None)
        environment.update(
            {
                "HOME": str(self.home),
                "VIBE": str(self.workspace),
                "VIBE_NO_CONTAINER": "1",
            }
        )
        environment.update(extra)
        return environment

    def start(self, environment):
        self.log = open(self.root / "web.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=environment,
            stdout=self.log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return self.wait_for_health()

    def wait_for_health(self):
        deadline = time.time() + 25
        while time.time() < deadline:
            if self.proc.poll() is not None:
                self.fail(
                    "vibe-web wurde vorzeitig beendet: "
                    + (self.root / "web.log").read_text(encoding="utf-8")
                )
            try:
                connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=1)
                connection.request("GET", "/api/health")
                response = connection.getresponse()
                body = response.read()
                connection.close()
                if response.status == 200:
                    return json.loads(body)
            except (OSError, ValueError):
                pass
            time.sleep(0.1)
        self.fail(
            "Health-Endpunkt auf dem konfigurierten Port nicht erreichbar: "
            + (self.root / "web.log").read_text(encoding="utf-8")
        )

    def test_web_uses_port_and_opencode_url_from_the_personal_configuration(self):
        write_config(self.config, {"ui_port": self.port, "opencode_port": 4199})

        payload = self.start(self.environment())

        self.assertEqual(payload["app"], "vibe")
        self.assertEqual(payload["port"], self.port)
        self.assertEqual(payload["bind"], "127.0.0.1")
        token = (self.workspace / "_logs" / "web.token").read_text(encoding="utf-8").strip()
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request("GET", "/api/server", headers={"X-Token": token})
        response = connection.getresponse()
        server = json.loads(response.read())
        connection.close()
        self.assertEqual(server["url"], "http://127.0.0.1:4199")
        self.assertTrue((self.workspace / "_logs" / "web.instance").is_file())
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request("GET", "/")
        page = connection.getresponse().read().decode("utf-8")
        connection.close()
        self.assertIn("http://127.0.0.1:4199", page)
        self.assertNotIn("http://127.0.0.1:4096", page)

    def test_web_uses_a_workspace_with_spaces(self):
        spacey = self.root / "vibe arbeitsbereich"
        write_config(self.config, {"ui_port": self.port})

        payload = self.start(self.environment(VIBE=str(spacey)))

        self.assertEqual(payload["port"], self.port)
        self.assertTrue((spacey / "_logs" / "web.token").is_file())
        self.assertTrue((spacey / "_logs" / "web.instance").is_file())
        self.assertFalse((self.workspace / "_logs").exists())


class RunnerPathsTest(unittest.TestCase):
    """Der Paketläufer folgt den aufgelösten Installations- und Laufzeitpfaden."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "proj"
        (self.project / ".vibe").mkdir(parents=True)
        self.agents = self.root / "home" / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer")
        (self.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n"
            "AGENT=tester\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL="true"\n'
            "MAX_RETRIES=0\n",
            encoding="utf-8",
        )
        (self.project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
        (self.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        self.install = self.root / "eigene toolchain"
        self.verify = self.install / "verify"
        self.verify.mkdir(parents=True)
        support.install_runner(self.install)
        self.runtime = self.root / "eigene logs"
        self.curl_log = self.root / "curl.invocations"
        fakebin = self.root / "fakebin"
        fakebin.mkdir()
        self.fakebin = fakebin
        fake_curl = fakebin / "curl"
        fake_curl.write_text(
            '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$FAKE_CURL_LOG"\nexit 7\n',
            encoding="utf-8",
        )
        fake_curl.chmod(0o755)
        support.init_repo(self.project)
        support.commit_all(self.project)

    def tearDown(self):
        self.tmp.cleanup()

    def test_runner_uses_the_configured_installation_and_runtime_directory(self):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("FAKE_") or key in (
                "SANDBOX",
                "SANDBOX_TOOLS",
                "AGENT",
                "TESTER",
                "REVIEWER",
                "MAX_RETRIES",
                "VERIFY_FULL",
                "VERIFY_PACKAGE",
            ):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(self.root),
                "VIBE_INSTALL": str(self.install),
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_AGENTS_DIR": str(self.agents),
                "VIBE_OPENCODE_PORT": "4198",
                "HOME": str(self.root / "home"),
                "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
                "VIBE_LOGNAME": "proj",
                "VIBE_MAX_PACKAGES": "1",
                "FAKE_CURL_LOG": str(self.curl_log),
            }
        )

        completed = subprocess.run(
            ["bash", str(RUNNER), str(self.project)],
            cwd=str(self.project),
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("Keine offenen Arbeitspakete mehr.", completed.stdout)
        self.assertTrue((self.runtime / "proj.log").is_file())
        self.assertFalse((self.root / "_logs").exists())
        self.assertIn(
            "http://127.0.0.1:4198/global/health",
            self.curl_log.read_text(encoding="utf-8"),
        )


class UiSessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.saved_vibe = sys.modules.get("vibe")

    def tearDown(self):
        sys.modules.pop("vibe", None)
        if self.saved_vibe is not None:
            sys.modules["vibe"] = self.saved_vibe
        self.tmp.cleanup()

    def load_cli(self, **environment):
        env = {
            "HOME": str(self.home),
            "VIBE_NO_CONTAINER": "1",
            **environment,
        }
        with clean_environment(env):
            return load_module(CLI, "vibe_ui_session_v006")

    def test_production_profile_keeps_the_original_session_name(self):
        module = self.load_cli(VIBE=str(self.root / "prod"))

        self.assertEqual(module.ui_session(), "vibe-ui")
        self.assertEqual(module.sess("proj"), "vibe-proj")
        self.assertEqual(module.PATHS.profile, "prod")

    def test_dev_profile_uses_its_own_session_and_child_environment(self):
        dev = self.root / "dev"
        module = self.load_cli(VIBE_PROFILE="dev", VIBE=str(dev))

        self.assertEqual(module.ui_session(), "vibe-ui-dev")
        child = module.PATHS.child_env()
        self.assertEqual(child["VIBE"], str(dev))
        self.assertEqual(child["VIBE_PROFILE"], "dev")
        self.assertEqual(child["VIBE_RUNTIME"], str(dev / "_logs"))
        self.assertEqual(child["VIBE_OPENCODE_PORT"], "4097")
        self.assertFalse(dev.exists())

    def test_dev_profile_controls_only_its_own_agent_session(self):
        dev = self.root / "dev"
        module = self.load_cli(VIBE_PROFILE="dev", VIBE=str(dev))

        self.assertEqual(module.sess("proj"), "vibe-proj-dev")
        self.assertNotEqual(module.sess("proj"), "vibe-proj")
        calls = []

        def record(argv, **kwargs):
            calls.append(list(argv))
            return 0, ""

        # V-016: cmd_stop beendet nur markierte Sitzungen. Die Attrappe liefert
        # keine Umgebungsauskunft; die Markierung wird deshalb hier gesetzt.
        with mock.patch.object(module, "run", side_effect=record), \
                mock.patch.object(module, "session_marker", return_value="run"):
            module.cmd_stop("proj")

        self.assertTrue(calls, "cmd_stop hat kein tmux-Kommando ausgeführt")
        self.assertIn("vibe-proj-dev", calls[-1])
        self.assertNotIn("vibe-proj", calls[-1])


if __name__ == "__main__":
    unittest.main()
