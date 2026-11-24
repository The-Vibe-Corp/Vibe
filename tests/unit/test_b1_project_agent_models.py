"""Abnahme B1: Projektmodelle aus ``.vibe/agents.json`` erreichen opencode.

Hintergrund des Fehlers: ``bin/vibe:run_agent_selection`` liefert bisher nur
die Modellüberschreibung des Startagenten; ``bin/vibe-run.sh`` gibt sie als
``opencode run --model`` weiter. Die übrigen Einträge unter ``modelle`` in
``<Projekt>/.vibe/agents.json`` werden nie gelesen. Vom Orchestrator gestartete
Subagenten verwenden deshalb ihr globales Frontmatter-Modell.

Die Tests beobachten ausschließlich wirksames Verhalten über eine
opencode-Attrappe: Sie protokolliert je Aufruf die Argumente und den Wert von
``OPENCODE_CONFIG_CONTENT``. Damit lässt sich prüfen, welche Agentenmodelle ein
``opencode run`` und ein privater ``opencode serve`` tatsächlich sehen. Es
werden keine Modellaufrufe, keine Anbieteranfragen und keine echten
Installationen verwendet.

Abgedeckte Akzeptanzfälle:

* Alle Einträge aus ``modelle`` werden als wirksame Agenten-Modellüber-
  schreibungen übergeben, nicht nur das ``--model`` des Startagenten.
* Dieselbe wirksame Konfiguration erreicht den privaten ``opencode serve``.
* Vorhandenes ``OPENCODE_CONFIG_CONTENT`` bleibt semantisch erhalten;
  Projektmodelle gewinnen auch gegenüber einer vorhandenen ``agents``-Map;
  das Legacy-Schema ``agent`` bleibt kompatibel.
* Ohne Projektmodelle bleibt vorhandenes ``OPENCODE_CONFIG_CONTENT``
  unverändert.
* Ein erreichbarer gemeinsamer Server wird bei vorhandenen Projektmodellen
  nicht ohne Laufkonfiguration weiterverwendet: ohne Kennwortdatei
  ``--standalone``, mit Kennwortdatei der private Serverpfad. Ohne
  Projektmodelle bleibt die bisherige Wiederverwendung unverändert.
* Eine unlesbare Projektdatei bzw. eine nicht mergefähige Inline-Konfiguration
  scheitert verständlich vor jedem Agentenstart.
* Der bisherige ``--model``-Parameter des Hauptagenten bleibt erhalten;
  globale Agentendateien und ``.vibe/agents.json`` werden nicht verändert.

Die Projektdateien liegen bewusst nur im Integrationsprojekt ``$P``: ``.vibe``
ist dort per ``.gitignore`` ausgeschlossen, sodass die Paket-Arbeitskopie keine
``.vibe/agents.json`` enthält. Damit prüfen die Tests mit, dass der Läufer die
Projektkonfiguration aus ``$P`` liest und nicht aus der Arbeitskopie.
"""
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import runner_support as support  # noqa: E402

PASSWORD = "b1-privat-9031"

# Die Attrappe schreibt zuerst die beobachtete Umgebung und führt danach die
# gemeinsame opencode-Attrappe aus ``runner_support`` aus. Sie ersetzt damit
# weder das Verhalten des Agenten noch das des privaten Servers.
ENV_RECORDING_OPENCODE = r'''#!/usr/bin/env python3
import json
import os
import sys

record = os.environ.get("FAKE_ENV_RECORD")
if record:
    entry = {
        "argv": sys.argv[1:],
        "config": os.environ.get("OPENCODE_CONFIG_CONTENT"),
    }
    with open(record, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

impl = os.environ.get("FAKE_OPENCODE_IMPL")
if not impl:
    raise SystemExit("FAKE_OPENCODE_IMPL fehlt")
os.execv(sys.executable, [sys.executable, impl] + sys.argv[1:])
'''


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def effective_model(config, agent):
    """Löst das wirksame Modell wie opencode auf: ``agents`` vor ``agent``."""
    if not isinstance(config, dict):
        return None
    for key in ("agents", "agent"):
        agents = config.get(key)
        if isinstance(agents, dict):
            entry = agents.get(agent)
            if isinstance(entry, dict) and isinstance(entry.get("model"), str):
                return entry["model"]
    return None


def resolved_agent_fields(config, agent):
    """Sammelt die Felder eines Agenten über beide akzeptierten Schemata."""
    fields = {}
    if not isinstance(config, dict):
        return fields
    for key in ("agent", "agents"):
        agents = config.get(key)
        if isinstance(agents, dict):
            entry = agents.get(agent)
            if isinstance(entry, dict):
                fields.update(entry)
    return fields


class SharedOpenCode:
    """Erreichbarer gemeinsamer opencode-Server für die Wiederverwendungsfälle.

    ``GET /api/info`` antwortet immer mit 200; die Anmeldung wird nicht
    bewertet, weil hier nur die Zielwahl des Läufers geprüft wird.
    """

    def __init__(self, port):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def do_GET(self):
                body = json.dumps({"ok": True}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever)
        self.thread.daemon = True
        outer.requests = []

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


class B1RunnerFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.agents = self.home / ".config" / "opencode" / "agents"
        support.write_agents(self.agents, "test-agent", "code-reviewer", "vibe-agent")
        self.runtime = self.root / "_logs"
        self.install = self.root / "_toolchain"
        self.tool_bin = support.install_runner(self.install)
        self.fakebin = support.install_fake_tools(self.root)
        support.install_real_curl(self.fakebin)
        # Die eigentliche Attrappe liegt daneben; der Name ``opencode`` im
        # PATH gehört der protokollierenden Hülle.
        self.impl = self.fakebin / "opencode_impl"
        self.impl.write_text(support.FAKE_OPENCODE, encoding="utf-8")
        self.impl.chmod(0o755)
        opencode = self.fakebin / "opencode"
        opencode.write_text(ENV_RECORDING_OPENCODE, encoding="utf-8")
        opencode.chmod(0o755)

        self.project = self.root / "proj"
        support.write_project(
            self.project,
            "TYPE=generic\n"
            "AGENT=tester\n"
            "TESTER=test-agent\n"
            "REVIEWER=code-reviewer\n"
            'VERIFY_PACKAGE="true"\n'
            'VERIFY_FULL="true"\n'
            "MAX_RETRIES=0\n",
            feedback=[support.ticket_record(
                "B1", "Testpaket",
                description="Projektmodelle weitergeben")],
        )
        # ``.vibe`` gehört nur zum Integrationsprojekt und ist nicht Teil des
        # Paketbranchs. Die Arbeitskopie enthält deshalb keine agents.json.
        (self.project / ".gitignore").write_text("/.vibe/\n", encoding="utf-8")
        support.init_repo(self.project)
        support.commit_all(self.project)

        self.env_record = self.root / "opencode.env.jsonl"
        self.args_file = self.runtime / "opencode.args"
        self.serve_record = self.root / "serve.record.jsonl"
        self.dead_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.dead_socket.bind(("127.0.0.1", 0))
        self.dead_port = self.dead_socket.getsockname()[1]
        self.addCleanup(self.dead_socket.close)
        self.shared = None
        self.addCleanup(self.stop_shared)
        self.addCleanup(self.kill_leftover_serve)

    # ---------- Dateien und Umgebung ----------

    def config_path(self):
        return self.project / ".vibe" / "agents.json"

    def write_project_models(self, models, aktiv=None):
        """Schreibt die Projektkonfiguration als nicht versionierte Projektdatei."""
        path = self.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 2,
            "aktiv": sorted(aktiv if aktiv is not None else models),
            "modelle": models,
        }
        path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def write_password(self, value=PASSWORD):
        self.runtime.mkdir(parents=True, exist_ok=True)
        path = self.runtime / "opencode.password"
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
        return path

    def env(self, extra=None):
        env = os.environ.copy()
        for key in list(env):
            if (
                key.startswith("VIBE")
                or key.startswith("SANDBOX")
                or key.startswith("FAKE_")
                or key.startswith("OPENCODE_")
            ):
                env.pop(key, None)
        env.update(
            {
                "VIBE": str(self.root),
                "VIBE_INSTALL": str(self.install),
                "VIBE_RUNTIME": str(self.runtime),
                "VIBE_AGENTS_DIR": str(self.agents),
                "VIBE_OPENCODE_PORT": str(self.dead_port),
                "VIBE_MAX_PACKAGES": "1",
                "HOME": str(self.home),
                "VIBE_NO_CONTAINER": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": str(self.fakebin) + os.pathsep + env.get("PATH", ""),
                "FAKE_ARGS_PATH": str(self.args_file),
                "FAKE_ENV_RECORD": str(self.env_record),
                "FAKE_OPENCODE_IMPL": str(self.impl),
                "FAKE_SERVE_RECORD": str(self.serve_record),
                "FAKE_CALLS": str(self.root / "opencode.calls"),
                "FAKE_COUNTER": str(self.root / "counter"),
            }
        )
        if extra:
            env.update(extra)
        return env

    def run_runner(self, *arguments, extra_env=None, timeout=180):
        return subprocess.run(
            ["bash", str(self.tool_bin / "vibe-run.sh"), str(self.project), *arguments],
            cwd=str(self.project),
            env=self.env(extra_env),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def log_text(self):
        path = self.runtime / "proj.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    # ---------- Beobachtung ----------

    def records(self):
        try:
            raw = self.env_record.read_text(encoding="utf-8")
        except OSError:
            return []
        entries = []
        for line in raw.splitlines():
            if line.strip():
                entries.append(json.loads(line))
        return entries

    def run_calls(self):
        return [entry for entry in self.records()
                if entry.get("argv") and entry["argv"][0] == "run"]

    def serve_calls(self):
        return [entry for entry in self.records()
                if entry.get("argv") and entry["argv"][0] == "serve"]

    def config_of(self, entry):
        raw = entry.get("config")
        self.assertIsInstance(
            raw, str,
            "opencode erhielt keine OPENCODE_CONFIG_CONTENT: " + repr(entry))
        return json.loads(raw)

    def assert_models(self, config, expected):
        for agent, model in expected.items():
            self.assertEqual(
                effective_model(config, agent), model,
                f"Agent {agent!r} hat nicht das Projektmodell; Konfiguration: "
                + json.dumps(config, ensure_ascii=False))

    # ---------- Gemeinsamer Server ----------

    def start_shared_server(self):
        port = free_port()
        self.shared = SharedOpenCode(port).start()
        self.addCleanup(self.shared.stop)
        return port

    def stop_shared(self):
        if self.shared is not None:
            self.shared.stop()
            self.shared = None

    def kill_leftover_serve(self):
        """Beendet nur die von diesem Test gestarteten Serverprozesse."""
        pids = set()
        try:
            raw = self.serve_record.read_text(encoding="utf-8")
        except OSError:
            raw = ""
        for line in raw.splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("event") == "listening" and isinstance(entry.get("pid"), int):
                pids.add(entry["pid"])
        try:
            pid_files = list(self.runtime.glob("*.server.pid"))
        except OSError:
            pid_files = []
        for path in pid_files:
            try:
                value = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if value.isdigit():
                pids.add(int(value))
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                continue
        if pids:
            time.sleep(0.5)
            for pid in pids:
                try:
                    os.kill(pid, 0)
                except OSError:
                    continue
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass


MODELS = {
    "tester": "projekt/tester-modell",
    "reviewer": "projekt/reviewer-modell",
    "vibe-agent": "projekt/vibe-modell",
}

EXISTING_CONFIG = {
    "theme": "dark",
    "model": "global/standard",
    "provider": {"firma": {"options": {"timeout": 30}}},
    "agent": {
        "reviewer": {
            "model": "global/reviewer-legacy",
            "description": "Bestehender Reviewer",
            "temperature": 0.2,
        },
        "archivar": {
            "model": "global/archivar",
            "description": "Nicht überschriebener Agent",
        },
    },
    "agents": {
        "reviewer": {
            "model": "global/reviewer-alias",
            "tools": {"bash": False},
        },
    },
}


class RunnerProjectModelsTest(B1RunnerFixture):
    """Projektmodelle erreichen den opencode-Lauf und den privaten Server."""

    def test_all_project_models_are_effective_for_the_opencode_run(self):
        """AK1/AK4: mehrere Modelle wirksam, ``--model`` bleibt, Dateien unverändert."""
        path = self.write_project_models(MODELS)
        agents_before = {
            item.name: item.read_bytes() for item in self.agents.iterdir()
        }
        project_config_before = path.read_bytes()

        result = self.run_runner("tester", "auftrag/start-modell")

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), "Genau ein Agentenaufruf erwartet: "
                         + repr(self.records()))
        config = self.config_of(runs[0])
        self.assert_models(config, MODELS)

        argv = runs[0]["argv"]
        self.assertIn("--model", argv, repr(argv))
        self.assertEqual(
            argv[argv.index("--model") + 1], "auftrag/start-modell",
            "Der bisherige Modellparameter des Hauptagenten ging verloren")
        self.assertEqual(argv[argv.index("--agent") + 1], "tester")

        agents_after = {
            item.name: item.read_bytes() for item in self.agents.iterdir()
        }
        self.assertEqual(
            agents_before, agents_after,
            "Globale Agentendateien wurden verändert")
        self.assertEqual(
            project_config_before, path.read_bytes(),
            ".vibe/agents.json wurde verändert")

    def test_project_models_reach_the_private_server_process(self):
        """AK2: Der private ``opencode serve`` erhält dieselbe wirksame Konfiguration."""
        self.write_project_models(MODELS)
        self.write_password()

        result = self.run_runner("tester", "projekt/tester-modell")

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        serves = self.serve_calls()
        runs = self.run_calls()
        self.assertEqual(1, len(serves), "Genau ein privater Server erwartet: "
                         + repr(self.records()))
        self.assertEqual(1, len(runs), "Genau ein Agentenaufruf erwartet: "
                         + repr(self.records()))

        serve_config = self.config_of(serves[0])
        run_config = self.config_of(runs[0])
        self.assert_models(serve_config, MODELS)
        self.assert_models(run_config, MODELS)
        self.assertEqual(
            serve_config, run_config,
            "Server und Lauf sehen nicht dieselbe wirksame Konfiguration")

        argv = runs[0]["argv"]
        self.assertIn("--server", argv, repr(argv))
        self.assertNotIn("--standalone", argv, repr(argv))
        url = argv[argv.index("--server") + 1]
        self.assertTrue(url.startswith("http://127.0.0.1:"), url)
        self.assertNotIn(str(self.dead_port), url)


class SharedServerTest(B1RunnerFixture):
    """AK: Ein erreichbarer gemeinsamer Server löst keine falsche Modellwahl aus."""

    def shared_url(self, port):
        return "http://127.0.0.1:" + str(port)

    def test_shared_server_is_used_unchanged_without_project_models(self):
        """Kontrolle: ohne Projektmodelle bleibt die Wiederverwendung erhalten."""
        shared_port = self.start_shared_server()

        result = self.run_runner(
            "tester", extra_env={"VIBE_OPENCODE_PORT": str(shared_port)})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), repr(self.records()))
        self.assertEqual(
            [], self.serve_calls(),
            "Ohne Projektmodelle startet kein privater Server")
        argv = runs[0]["argv"]
        self.assertIn("--server", argv, repr(argv))
        self.assertEqual(argv[argv.index("--server") + 1],
                         self.shared_url(shared_port))
        self.assertNotIn("--standalone", argv, repr(argv))

    def test_shared_server_is_not_reused_when_project_models_exist(self):
        """AK: Mit Projektmodellen ohne Kennwortdatei gilt ``--standalone``."""
        self.write_project_models(MODELS)
        shared_port = self.start_shared_server()

        result = self.run_runner(
            "tester", "projekt/tester-modell",
            extra_env={"VIBE_OPENCODE_PORT": str(shared_port)})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), repr(self.records()))
        self.assertEqual(
            [], self.serve_calls(),
            "Ohne Kennwortdatei startet kein privater Server")
        argv = runs[0]["argv"]
        self.assertIn("--standalone", argv, repr(argv))
        self.assertNotIn("--server", argv, repr(argv))
        self.assertNotIn(self.shared_url(shared_port), argv, repr(argv))
        self.assert_models(self.config_of(runs[0]), MODELS)

    def test_shared_server_is_replaced_by_a_private_server_with_project_models(self):
        """AK: Mit Kennwortdatei ersetzt der private Server den gemeinsamen."""
        self.write_project_models(MODELS)
        self.write_password()
        shared_port = self.start_shared_server()

        result = self.run_runner(
            "tester", "projekt/tester-modell",
            extra_env={"VIBE_OPENCODE_PORT": str(shared_port)})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        serves = self.serve_calls()
        runs = self.run_calls()
        self.assertEqual(1, len(serves), "Genau ein privater Server erwartet: "
                         + repr(self.records()))
        self.assertEqual(1, len(runs), repr(self.records()))

        argv = runs[0]["argv"]
        self.assertIn("--server", argv, repr(argv))
        self.assertNotIn("--standalone", argv, repr(argv))
        private_url = argv[argv.index("--server") + 1]
        self.assertTrue(private_url.startswith("http://127.0.0.1:"), private_url)
        self.assertNotEqual(private_url, self.shared_url(shared_port),
                            "Der gemeinsame Server wurde trotz Projektmodellen "
                            "ohne Laufkonfiguration weiterverwendet")

        serve_config = self.config_of(serves[0])
        run_config = self.config_of(runs[0])
        self.assert_models(serve_config, MODELS)
        self.assert_models(run_config, MODELS)
        self.assertEqual(serve_config, run_config)


class ExistingConfigTest(B1RunnerFixture):
    """AK3: Vorhandene Inline-Konfiguration bleibt erhalten."""

    def test_existing_config_is_preserved_and_project_models_win(self):
        """Auch bei vorhandener ``agents``-Map gewinnt das Projektmodell."""
        self.write_project_models({"reviewer": "projekt/reviewer-modell"})

        result = self.run_runner(
            "tester",
            extra_env={"OPENCODE_CONFIG_CONTENT": json.dumps(EXISTING_CONFIG)})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), repr(self.records()))
        config = self.config_of(runs[0])

        for key in ("theme", "model", "provider"):
            self.assertEqual(
                config.get(key), EXISTING_CONFIG[key],
                f"Unbeteiligte Einstellung {key!r} ging verloren")

        fields = resolved_agent_fields(config, "reviewer")
        self.assertEqual(fields.get("description"), "Bestehender Reviewer")
        self.assertEqual(fields.get("temperature"), 0.2)
        self.assertEqual(fields.get("tools"), {"bash": False})
        self.assertEqual(
            effective_model(config, "reviewer"), "projekt/reviewer-modell",
            "Eine vorhandene agents-Map setzt die Projektüberschreibung "
            "wieder außer Kraft")

        # Nicht überschriebene Agenten bleiben unverändert.
        self.assertEqual(effective_model(config, "archivar"),
                         "global/archivar")
        self.assertEqual(
            resolved_agent_fields(config, "archivar").get("description"),
            "Nicht überschriebener Agent")

    def test_legacy_agent_schema_stays_compatible(self):
        """Das alte ``agent``-Schema wird weiterhin gemischt und bleibt erhalten."""
        existing = {
            "theme": "light",
            "agent": {
                "reviewer": {
                    "model": "global/reviewer",
                    "description": "Legacy-Reviewer",
                    "temperature": 0.1,
                },
            },
        }
        self.write_project_models({"reviewer": "projekt/reviewer-modell"})

        result = self.run_runner(
            "tester",
            extra_env={"OPENCODE_CONFIG_CONTENT": json.dumps(existing)})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        config = self.config_of(self.run_calls()[0])
        self.assertEqual(config.get("theme"), "light")
        self.assertEqual(effective_model(config, "reviewer"),
                         "projekt/reviewer-modell")
        fields = resolved_agent_fields(config, "reviewer")
        self.assertEqual(fields.get("description"), "Legacy-Reviewer")
        self.assertEqual(fields.get("temperature"), 0.1)

    def test_jsonc_existing_config_is_accepted_and_merged(self):
        """JSONC (Kommentare, Trailing Commas) wird wie von opencode akzeptiert.

        opencode v2.3.0 akzeptiert in ``OPENCODE_CONFIG_CONTENT`` JSONC. Eine
        Bestandskonfiguration darf deshalb nicht allein wegen eines Kommentars
        oder eines abschließenden Kommas abgelehnt werden. Nach dem
        Zusammenführen ist eine reine JSON-Serialisierung zulässig; Kommentare
        und Formatierung müssen nicht erhalten bleiben.
        """
        jsonc = """{
  // Bestehende Anmerkung des Nutzers
  "theme": "dark",
  "model": "global/standard",
  "agent": {
    "reviewer": {
      "model": "global/reviewer", // wird vom Projekt überschrieben
      "temperature": 0.2,
    },
  },
}
"""
        self.write_project_models({"reviewer": "projekt/reviewer-modell"})

        result = self.run_runner(
            "tester", extra_env={"OPENCODE_CONFIG_CONTENT": jsonc})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), repr(self.records()))
        config = self.config_of(runs[0])
        self.assertEqual(config.get("theme"), "dark")
        self.assertEqual(config.get("model"), "global/standard")
        self.assertEqual(effective_model(config, "reviewer"),
                         "projekt/reviewer-modell")
        self.assertEqual(
            resolved_agent_fields(config, "reviewer").get("temperature"), 0.2)

    def test_jsonc_comment_between_trailing_comma_and_closing_brace(self):
        """Trailing Comma mit Kommentar davor bleibt gültiges JSONC.

        opencode akzeptiert ``{"a": 1, // Kommentar\n}``. Der Scanner darf den
        Trailing Comma deshalb nicht nur dann entfernen, wenn direkt nach dem
        Whitespace die schließende Klammer folgt. Zugleich muss ``//`` in einer
        Zeichenkette (URL) unangetastet bleiben.
        """
        jsonc = """{
  // Bestehende Anmerkung des Nutzers
  "theme": "dark",
  "hinweis": "https://example.invalid/path",
  "agent": {
    "reviewer": {
      "model": "global/reviewer",
      "temperature": 0.2, // Kommentar zwischen Komma und schließender Klammer
    },
  },
}
"""
        self.write_project_models({"reviewer": "projekt/reviewer-modell"})

        result = self.run_runner(
            "tester", extra_env={"OPENCODE_CONFIG_CONTENT": jsonc})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), repr(self.records()))
        config = self.config_of(runs[0])
        self.assertEqual(config.get("theme"), "dark")
        self.assertEqual(config.get("hinweis"), "https://example.invalid/path",
                         "Die URL mit '//' wurde als Kommentar behandelt")
        self.assertEqual(effective_model(config, "reviewer"),
                         "projekt/reviewer-modell")
        self.assertEqual(
            resolved_agent_fields(config, "reviewer").get("temperature"), 0.2)

    def test_without_project_models_existing_config_stays_unchanged(self):
        """Kontrolle: ohne Projektmodelle wird die Inline-Konfiguration nicht angefasst."""
        self.write_project_models({}, aktiv=[])
        existing = {
            "theme": "dark",
            "agent": {"reviewer": {"model": "global/reviewer"}},
            "agents": {"reviewer": {"tools": {"bash": False}}},
        }

        result = self.run_runner(
            "tester",
            extra_env={"OPENCODE_CONFIG_CONTENT": json.dumps(existing)})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertEqual(result.returncode, 0, "Läufer bricht ab:\n" + detail)
        runs = self.run_calls()
        self.assertEqual(1, len(runs), repr(self.records()))
        self.assertEqual(
            self.config_of(runs[0]), existing,
            "Ohne Projektmodelle wurde die vorhandene Konfiguration verändert")


class InvalidConfigurationTest(B1RunnerFixture):
    """AK: Fehlerhafte Konfiguration scheitert vor dem Agentenstart."""

    def assert_no_agent_started(self):
        self.assertEqual([], self.run_calls(),
                         "Agent wurde trotz fehlerhafter Konfiguration gestartet")
        self.assertEqual([], self.serve_calls(),
                         "Privater Server wurde trotz fehlerhafter Konfiguration gestartet")

    def test_unreadable_project_agents_file_aborts_before_agent_start(self):
        path = self.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{kaputt", encoding="utf-8")

        result = self.run_runner("tester")

        detail = result.stdout + result.stderr + self.log_text()
        self.assertNotEqual(
            result.returncode, 0,
            "Unlesbare agents.json fiel still auf globale Modelle zurück:\n"
            + detail)
        self.assert_no_agent_started()
        self.assertTrue(
            re.search(r"agents\.json|Agentenauswahl|Projektkonfiguration|Projektdatei",
                      detail, re.IGNORECASE),
            "Keine verständliche Meldung zur fehlerhaften Projektdatei:\n"
            + detail)

    def test_unmergeable_existing_config_aborts_before_agent_start(self):
        self.write_project_models(MODELS)

        result = self.run_runner(
            "tester",
            extra_env={"OPENCODE_CONFIG_CONTENT": "{kaputt"})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertNotEqual(
            result.returncode, 0,
            "Nicht mergefähige Inline-Konfiguration fiel still auf globale "
            "Modelle zurück:\n" + detail)
        self.assert_no_agent_started()
        self.assertTrue(
            re.search(r"OPENCODE_CONFIG_CONTENT|Konfiguration|Inline",
                      detail, re.IGNORECASE),
            "Keine verständliche Meldung zur Inline-Konfiguration:\n" + detail)

    def test_unterminated_block_comment_is_not_silently_removed(self):
        """Ein offener Blockkommentar darf nicht bis zum Dateiende verschwinden.

        Steht nach einem ansonsten vollständigen Objekt ein nicht
        abgeschlossener ``/*``-Kommentar, wäre die Konfiguration nach dem
        Entfernen scheinbar gültig. Das ist kein gültiges JSONC und muss
        fail-closed vor dem Agentenstart abbrechen.
        """
        existing = """{
  "theme": "dark",
  "agent": {"reviewer": {"model": "global/reviewer"}}
}
/* nicht abgeschlossener Kommentar
"""
        self.write_project_models({"reviewer": "projekt/reviewer-modell"})

        result = self.run_runner(
            "tester",
            extra_env={"OPENCODE_CONFIG_CONTENT": existing})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertNotEqual(
            result.returncode, 0,
            "Ein offener Blockkommentar wurde still entfernt und die "
            "Konfiguration akzeptiert:\n" + detail)
        self.assert_no_agent_started()
        self.assertTrue(
            re.search(r"OPENCODE_CONFIG_CONTENT|Kommentar|Konfiguration|Inline",
                      detail, re.IGNORECASE),
            "Keine verständliche Meldung zum offenen Blockkommentar:\n"
            + detail)

    def test_path_that_is_not_a_regular_file_aborts_before_agent_start(self):
        """Nur FileNotFoundError bedeutet 'keine Projektmodelle'.

        Ein vorhandener, aber nicht als Datei lesbarer Pfad (hier ein
        Verzeichnis an der Stelle von ``agents.json``) ist ein anderer
        ``OSError`` und darf nicht still wie eine fehlende Datei zu globalen
        Modellen führen.
        """
        path = self.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.mkdir()

        result = self.run_runner("tester")

        detail = result.stdout + result.stderr + self.log_text()
        self.assertNotEqual(
            result.returncode, 0,
            "Ein nicht lesbarer Projektpfad wurde wie eine fehlende Datei "
            "behandelt:\n" + detail)
        self.assert_no_agent_started()
        self.assertTrue(
            re.search(r"agents\.json|Agentenauswahl|Projektkonfiguration|Projektdatei|nicht lesbar",
                      detail, re.IGNORECASE),
            "Keine verständliche Meldung zum nicht lesbaren Projektpfad:\n"
            + detail)

    def test_non_object_existing_config_aborts_before_agent_start(self):
        self.write_project_models(MODELS)

        result = self.run_runner(
            "tester",
            extra_env={"OPENCODE_CONFIG_CONTENT": "[]"})

        detail = result.stdout + result.stderr + self.log_text()
        self.assertNotEqual(
            result.returncode, 0,
            "Eine nicht objektförmige Inline-Konfiguration wurde still "
            "überschrieben:\n" + detail)
        self.assert_no_agent_started()
        self.assertTrue(
            re.search(r"OPENCODE_CONFIG_CONTENT|Konfiguration|Inline",
                      detail, re.IGNORECASE),
            "Keine verständliche Meldung zur Inline-Konfiguration:\n" + detail)


if __name__ == "__main__":
    unittest.main()
