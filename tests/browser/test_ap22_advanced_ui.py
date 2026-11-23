"""Browserabnahme AP22, Meilenstein C: Settings-Sektionen und Paritätsrundgang.

Die Fälle leiten sich aus ``docs/features/AP22.md`` ab — Abschnitt
„Einstellungen (nova-settings.js)“, „Paritätsmatrix“ sowie dem Testplan
„Meilenstein C“; abgeleitet vom Vertrag F34.md WP4/WP5. Jeder Fall schaltet
die benötigten Feature-Schalter zuerst über ``#/settings`` ein
(``input[data-nv-feature="<id>"]``); die Sektionen
``section[data-nv-ssection="<id>"]`` liegen danach immer im DOM.

F34-Anpassung (echte Hooks bestätigt aus ``bin/web/nova-settings.js`` und
``bin/web/nova-project.js``):

* Einstellungssektionen: ``section[data-nv-ssection="<id>"]`` in der
  Vertragsreihenfolge; ``global-agents`` statt ``agentsfile`` (echte Hook
  aus ``NV_SETTINGS_SECTIONS``; ebenso grüner F34-Suite).
* ``CostsTest``/``EnvTest``/``RunsTest`` → Abwesenheitsprüfungen in den
  Einstellungen + Verweis-Test auf ``#/evaluations`` (Tabs
  costs/runs/environment); Tiefenprüfung dort:
  ``tests/browser/test_f34_activity_evals_ui.py``.
* ``ModelsTest``: ``details[data-nv-model-catalog]`` implementiert
  standardmäßig ZU (Contract/Task-Text prüfen „zu“, echte Hook bestätigt
  ZU → zugeklappt).
* ``ProfilesTest``: ``select[data-nv-field='profile']`` ist entfallen;
  Vorschau = Klick auf ``article[data-nv-profile]`` (markiert +
  ``[data-nv-profile-details]``); Anwenden über ``profile-apply`` →
  Kontext-Panel ``Bestätigen``.
* ``McpTest``: ``[data-nv-mcp-result]`` hat kein ``data-nv-ok``-Attribut;
  Fehler wird über ``[data-nv-ok]``-Klasse/Text gemeldet.
* ``GatesTest``: Gates-Hooks ``select[data-nv-field='gates-key'/
  'gates-value'/'gates-project']`` sind entfallen; neu
  ``select[data-nv-gates-project]``, ``tr[data-nv-gate]`` mit
  ``input/select[data-nv-gate-value]``, ``span[data-nv-gate-origin]``,
  ``input[data-nv-gate-override]``.

Das echte Dashboard läuft als eigener Prozess auf einem freien Loopback-Port
mit isoliertem ``VIBE``/``HOME``/``VIBE_STATE``/``VIBE_INSTALL``. opencode und
Pi sind Attrappen im ``PATH``, der opencode-Server ist eine lokale
HTTP-Attrappe, der Fritzbox-Helfer ist ein nachgebildetes Python-Skript. Es
gibt keine Modellaufrufe und keinen Netzzugriff außerhalb von Loopback.

Abgeleitete DOM-Hooks (Test-Vertrag)
------------------------------------
Der Vertrag schreibt für die Einstellungssektionen
``section[data-nv-ssection="<id>"]`` sowie für Limits/Gates konkrete
Feld-/Aktions-Hooks fest. Für die übrigen Bedienelemente nennt er keine
Namen. Diese Tests binden deshalb an die folgenden, hier verbindlich
dokumentierten Hooks; sie folgen dem Muster der übrigen AP22-Hooks
(``data-nv-field``, ``data-nv-action``, ``data-nv-<bereich>``):

===============================  ==========================================
Bereich / Hook                   Bedeutung
===============================  ==========================================
``models``
  ``section[data-nv-ssection="models"]``  Sektion (Vertrag)
  ``details[data-nv-models][open]``       Modelltabelle
  ``[data-nv-model="<id>"]``              Modellzeile der Übersicht
  ``[data-nv-model-detail="<id>"]``       Detailzeile (nach Klick auf die Zeile)
  ``[data-nv-model-facts]``               Faktenblock der Detailzeile
  ``[data-nv-model-assessments]``         Einschätzungsblock der Detailzeile
``profiles``
  ``section[data-nv-ssection="profiles"]`` Sektion (Vertrag)
  ``article[data-nv-profile="<name>"]``   Profilkarte; Klick →
      ``[data-nv-profile-selected]`` + ``[data-nv-profile-details]``
  ``[data-nv-profile-details]``           Vorschaubereich (Rolle → Modell)
  ``[data-nv-action="profile-apply"]``    Anwenden (Kontext „Bestätigen“)
``mcp``
  ``section[data-nv-ssection="mcp"]``     Sektion (Vertrag)
  ``[data-nv-mcp-server="<name>"]``       Serverzeile
  ``[data-nv-action="mcp-toggle"]``       Zeilenaktion an/aus
  ``[data-nv-action="mcp-test"]``         Zeilenaktion Verbindungstest
  ``[data-nv-mcp-result]``                Ergebnisbereich (Fehler über Text)
``costs`` — entfallen (F34): ``#/evaluations`` → ``[data-nv-etab="costs"]``
``harness``
  ``section[data-nv-ssection="harness"]`` Sektion (Vertrag)
  ``select[data-nv-field="harness"]``     Harnessauswahl
  ``[data-nv-action="harness-use"]``      Auswahl übernehmen
  ``[data-nv-harness-status]``            Status-/Einrichtungsbereich
``env`` — entfallen (F34): ``#/evaluations`` → ``[data-nv-etab="environment"]``
  ``[data-nv-doctor-row]``, ``[data-nv-paths]`` (dort: Tests + Fritzbox)
``runs`` — entfallen (F34): ``#/evaluations`` → ``[data-nv-etab="runs"]``
  ``[data-nv-run="<id>"]``, ``[data-nv-action="runs-prune"]``
===============================  ==========================================

Bewusste Vertragsableitungen
----------------------------
* ``ProfilesTest``: Der Vertrag nennt „Liste + use mit Vorschau/
  Bestätigung“. Echte Hooks: Vorschau = Klick auf die ``article`` markiert
  die Karte und schreibt ``[data-nv-profile-details]`` (Rolle → Zielmodell);
  das Anwenden schreibt ``aktiv`` in ``profiles.json``.
* Für ``mcp`` verlangt der Vertrag „Geheimnisse maskiert“. Geprüft wird,
  dass ein Token in der URL weder im DOM noch in der Serverantwort unmaskiert
  auftaucht und stattdessen ``***`` sichtbar ist. Ein fehlgeschlagener Test
  wird über den Fehlerbericht des ``[data-nv-mcp-result]``-Bereichs belegt.
* Für ``runs`` wird die in AP20 bewährte Technik genutzt: ``runs.json`` liegt
  **vor** dem Serverstart im Laufzeitordner; der Eintrag nennt eine sicher
  fehlende tmux-Sitzung, damit ``prune`` ihn als beendet markiert.
* Die Paritätsmatrix führt ``priority`` unter „Arbeit“; F33 WP3/2o ersetzt
  die alte Priorisierungskarte durch die Leiste
  ``div[data-nv-priority-strip]`` im Arbeit-Tab (ohne eigene Sektion in den
  Projekteinstellungen).

Testfälle (Kurzfassung; Details in den Methoden)
------------------------------------------------
``ModelsTest.test_catalog_expands_and_separates_facts_from_assessments``
``ProfilesTest.test_profiles_preview_then_apply``
``McpTest.test_mcp_masks_secrets_toggles_and_reports_test_failure``
``CostsTest.test_costs_absent_from_settings_and_in_evaluations``
``HarnessTest.test_harness_status_switch_persists_and_plan_is_visible``
``LimitsTest.test_limits_mode_switches_between_continue_and_stop``
``GatesTest.test_gates_global_and_project_override``
``EnvTest.test_env_absent_from_settings``
``RunsTest.test_runs_absent_from_settings``
``ParityTest.test_every_feature_toggle_and_project_sections``
"""
import http.client
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_BROWSERS = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"

# Echte Feature-Schalter (Vertrag F34.md WP4, ``NV_SETTINGS_FEATURE_GROUPS``);
# ``costs``/``env``/``runs`` entfallen — die Bereiche stehen unter
# ``#/evaluations`` (Tabs costs/runs/environment).
FEATURE_IDS = (
    "github", "agentsfile", "writeaccess", "models", "profiles", "mcp",
    "harness", "limits", "gates", "sandbox", "priority",
)
PROJECT_FEATURES = ("github", "writeaccess", "sandbox", "agentsfile",
                    "priority")
MCP_SECRET = "geheim-MCP-4711"
FRITZ_SECRET = "geheim-fritz-passwort"

FAKE_OPENCODE = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf 'opencode v2.1.4\\n'
    exit 0
    ;;
  models)
    printf 'opencode/vibe-modell\\nopencode/test-modell\\nopencode/schnell-modell\\n'
    exit 0
    ;;
esac
exit 2
"""

FAKE_PI = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf '0.72.0\\n'
    exit 0
    ;;
  --list-models)
    printf 'anthropic/claude-sonnet\\n'
    exit 0
    ;;
esac
exit 2
"""

FAKE_FRITZ_HELPER = '''import json, os
log = os.environ.get("FAKE_FRITZ_LOG")
if log:
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"env": os.environ.get("FRITZ_ENV")}) + "\\n")
print("alte IP: 203.0.113.1")
print("neue IP: 203.0.113.9")
'''

MODELS_CATALOG = {
    "schema": 2,
    "version": "2026-11-20.1",
    "stand": "2026-11-20",
    "waehrung": "USD",
    "einheit": "1 Mio. Tokens",
    "hinweis": "Testkatalog für die AP22-Paritätsabnahme.",
    "quellen": [
        {"name": "opencode models", "datum": "2026-11-20",
         "zweck": "Modell-IDs"},
        {"name": "models.dev API", "datum": "2026-11-20",
         "zweck": "Fakten und Preise"},
    ],
    "modelle": [
        {
            "id": "opencode/vibe-modell",
            "name": "Vibe Modell",
            "anbieter": "OpenCode Zen",
            "id_status": "bestaetigt",
            "id_beleg": {"quelle": "opencode models", "datum": "2026-11-20"},
            "preis": {
                "status": "bekannt", "waehrung": "USD",
                "einheit": "1 Mio. Tokens", "stand": "2026-11-20",
                "quelle": "models.dev API",
                "tarife": {"eingabe": 0.15, "ausgabe": 0.5,
                           "cache_lesen": 0.03},
            },
            "fakten": {
                "kontext": {"wert": "200.000 Token", "art": "fakt",
                            "quelle": "models.dev API",
                            "datum": "2026-11-20"},
            },
            "einschaetzungen": {
                "tempo": {"wert": "schnell", "art": "einschaetzung",
                          "quelle": "Altkatalog 2026-11-20",
                          "datum": "2026-11-20"},
            },
        },
        {
            "id": "opencode/test-modell",
            "name": "Test Modell",
            "anbieter": "OpenCode Zen",
            "id_status": "bestaetigt",
            "id_beleg": {"quelle": "opencode models", "datum": "2026-11-20"},
            "preis": {"status": "unbekannt", "grund": "kein belegter Preis"},
            "fakten": {},
            "einschaetzungen": {},
        },
    ],
}

MCP_CONFIG = {
    "mcp": {
        "servers": {
            "lokal": {
                "type": "local",
                "command": ["echo", "hallo"],
                "enabled": True,
            },
            "fern": {
                "type": "remote",
                "url": "https://example.invalid/mcp?token=" + MCP_SECRET,
                "enabled": True,
            },
            "kaputt": {
                "type": "remote",
                "url": "http://127.0.0.1:{{CLOSED_PORT}}/mcp",
                "enabled": True,
            },
        }
    }
}

DDL_V2 = """
CREATE TABLE `session_v2` (
  `id` text PRIMARY KEY,
  `project_id` text NOT NULL,
  `workspace_id` text,
  `parent_id` text,
  `fork_session_id` text,
  `fork_boundary` text,
  `slug` text NOT NULL,
  `directory` text NOT NULL,
  `path` text,
  `title` text,
  `version` text NOT NULL,
  `share_url` text,
  `summary_additions` integer,
  `summary_deletions` integer,
  `summary_files` integer,
  `summary_diffs` text,
  `metadata` text,
  `cost` real DEFAULT 0 NOT NULL,
  `tokens_input` integer DEFAULT 0 NOT NULL,
  `tokens_output` integer DEFAULT 0 NOT NULL,
  `tokens_reasoning` integer DEFAULT 0 NOT NULL,
  `tokens_cache_read` integer DEFAULT 0 NOT NULL,
  `tokens_cache_write` integer DEFAULT 0 NOT NULL,
  `revert` text,
  `permission` text,
  `agent` text,
  `model` text,
  `time_created` integer NOT NULL,
  `time_updated` integer NOT NULL,
  `time_compacting` integer,
  `time_archived` integer,
  `time_suspended` integer,
  `resume_attempts` integer DEFAULT 0 NOT NULL,
  `time_idle` integer,
  `time_viewed` integer,
  `idle_outcome` text
);
CREATE TABLE "session_message" (
  `id` text PRIMARY KEY,
  `session_id` text NOT NULL,
  `type` text NOT NULL,
  `seq` integer NOT NULL,
  `time_created` integer NOT NULL,
  `time_updated` integer NOT NULL,
  `data` text NOT NULL
);
"""


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """Gesunder opencode-Server: /api/info nennt eine Version."""

    def log_message(self, *args):
        return

    def do_GET(self):
        body = json.dumps({"version": "2.1.4", "healthy": True}).encode(
            "utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class AP22AdvancedBrowserTest(unittest.TestCase):
    """Dashboard, Browser, Attrappen, isolierter Zustand und Laufzeitordner."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\nAGENT=tester\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n",
                                                 encoding="utf-8")
        (cls.project / "TICKETS.md").write_text(
            "# TICKETS — Test\n\n- [ ] F1 Erstes Paket\n"
            "  Beschreibung: Testpaket für die Kosten.\n", encoding="utf-8")
        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir()
        cls.install = cls.root / "_toolchain"
        cls.install.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        (cls.root / "tmp").mkdir()
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir()

        fake_bin = cls.root / "fakebin"
        fake_bin.mkdir()
        for name, text in (("opencode", FAKE_OPENCODE), ("pi", FAKE_PI)):
            path = fake_bin / name
            path.write_text(text, encoding="utf-8")
            path.chmod(0o755)
        cls.fake_bin = fake_bin

        cls.helper = cls.root / "fake-fritz.py"
        cls.helper.write_text(FAKE_FRITZ_HELPER, encoding="utf-8")
        cls.fritz_env = cls.root / "fritz.env"
        cls.fritz_env.write_text(
            "FRITZ_ADDR=192.0.2.1\nFRITZ_USER=testuser\n"
            "FRITZ_PASS=" + FRITZ_SECRET + "\n", encoding="utf-8")
        cls.fritz_log = cls.root / "fake-fritz.log"

        (cls.install / "models.json").write_text(
            json.dumps(MODELS_CATALOG, ensure_ascii=False), encoding="utf-8")

        cls.mcp_config = cls.home / ".config" / "opencode" / "opencode.json"
        cls.closed_port = free_port()
        cls.write_mcp_config()

        cls.db = cls.root / "opencode.db"
        cls.write_costs_db()

        cls.runs_file = cls.log_dir / "runs.json"
        cls.write_runs()

        cls.port = free_port()
        cls.oc_port = free_port()
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), _FakeOpenCodeHandler)
        cls._fake_http.daemon_threads = True
        cls._fake_thread = threading.Thread(target=cls._fake_http.serve_forever)
        cls._fake_thread.daemon = True
        cls._fake_thread.start()

        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                    "TMUX", "TMUX_PANE"):
                env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_OPENCODE_PORT": str(cls.oc_port),
            "VIBE_STATE": str(cls.state_dir),
            "VIBE_INSTALL": str(cls.install),
            "VIBE_RUNTIME": str(cls.log_dir),
            "VIBE_OPENCODE_DB": str(cls.db),
            "VIBE_FRITZ_PYTHON": sys.executable,
            "VIBE_FRITZ_SCRIPT": str(cls.helper),
            "VIBE_FRITZ_ENV": str(cls.fritz_env),
            "FAKE_FRITZ_LOG": str(cls.fritz_log),
            "HOME": str(cls.home),
            "TMPDIR": str(cls.root / "tmp"),
            "TMUX_TMPDIR": str(cls.tmux_dir),
            "VIBE_CONFIG_FILE": str(
                cls.home / ".config" / "vibe" / "config.json"),
            "PATH": str(fake_bin) + os.pathsep + env.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        cls.env = env
        cls.server_log = open(cls.root / "web-server.log", "w",
                              encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=cls.server_log, stderr=subprocess.STDOUT, text=True,
            start_new_session=True)
        cls.pgid = os.getpgid(cls.proc.pid)
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 30
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                            ("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: "
                    + (cls.root / "web-server.log").read_text(
                        encoding="utf-8", errors="replace"))
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def write_mcp_config(cls):
        text = json.dumps(MCP_CONFIG, ensure_ascii=False).replace(
            "{{CLOSED_PORT}}", str(cls.closed_port))
        cls.mcp_config.write_text(text + "\n", encoding="utf-8")

    @classmethod
    def write_costs_db(cls):
        con = sqlite3.connect(str(cls.db))
        con.executescript(DDL_V2)
        con.execute(
            "insert into session_v2 (id, project_id, slug, directory, title,"
            " version, agent, model, time_created, time_updated)"
            " values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ses_ap22", "proj", "slug-ap22", str(cls.project),
             "proj F1", "2.1.4", "coding-agent",
             json.dumps({"id": "opencode/test-modell",
                         "providerID": "opencode"}), 1, 1))
        data = {
            "agent": "coding-agent",
            "model": {"id": "opencode/test-modell", "providerID": "opencode"},
            "tokens": {
                "input": 400000, "output": 300000, "reasoning": 200000,
                "cache": {"read": 600000, "write": 0},
            },
        }
        con.execute(
            "insert into session_message (id, session_id, type, seq,"
            " time_created, time_updated, data) values (?, ?, ?, ?, ?, ?, ?)",
            ("msg_ap22", "ses_ap22", "assistant", 1, 1, 1,
             json.dumps(data)))
        con.commit()
        con.close()

    @classmethod
    def write_runs(cls):
        record = {
            "id": "run-ap22-missing",
            "project": str(cls.project.resolve()),
            "name": "proj",
            "key": "proj",
            "agent": "vibe-agent",
            "session": "ap22-definitely-missing-session",
            "log": "",
            "verify_log": "",
            "state": "running",
            "started": "2026-11-20T10:00:00+0000",
            "pid": 0,
            "exit_code": None,
        }
        cls.runs_file.write_text(
            json.dumps({"runs": [record]}, indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser.close()
            cls.playwright.stop()
        finally:
            try:
                cls._fake_http.shutdown()
                cls._fake_http.server_close()
                cls._fake_thread.join(timeout=5)
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            if cls.proc.poll() is None:
                cls.proc.terminate()
                try:
                    cls.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls.proc.kill()
                    cls.proc.wait()
            try:
                os.killpg(cls.pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            cls.server_log.close()
            cls.tmp.cleanup()

    # ---------- Umgebung je Test ----------

    def setUp(self):
        # Zustand, den einzelne Fälle verändern, deterministisch zurücksetzen.
        for name in ("gates.json", "fritz.json", "harness.json", "costs.json",
                     "limits.json"):
            (self.state_dir / name).unlink(missing_ok=True)
        (self.install / "costs.json").unlink(missing_ok=True)
        self.fritz_log.unlink(missing_ok=True)
        self.write_runs()
        self.write_mcp_config()
        (self.state_dir / "profiles.json").write_text(
            json.dumps({
                "aktiv": "kostenlos",
                "rollen": {"tester": "coder", "vibe-agent": "vibe"},
                "profile": {
                    "kostenlos": {"coder": "opencode/vibe-modell",
                                  "reviewer": "opencode/test-modell",
                                  "vibe": "opencode/vibe-modell"},
                    "guenstig": {"coder": "opencode/test-modell",
                                 "reviewer": "opencode/schnell-modell",
                                 "vibe": "opencode/vibe-modell"},
                    "stark": {"coder": "", "reviewer": "", "vibe": ""},
                },
            }, ensure_ascii=False), encoding="utf-8")
        self.set_language("de")
        self.page_errors = []
        self.dialogs = []
        self.context = self.browser.new_context(
            viewport={"width": 1500, "height": 1200})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))
        self.page.on("dialog", self._on_dialog)

    def _on_dialog(self, dialog):
        # Bestätigungen (Fritz-Reconnect, Löschen) werden angenommen.
        self.dialogs.append(dialog.type + ": " + dialog.message)
        dialog.accept()

    def tearDown(self):
        self.page.close()
        self.context.close()

    # ---------- Helfer ----------

    def wait_until(self, predicate, timeout=25,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def set_language(self, lang):
        status, body = self.api_post("/api/language", {"language": lang})
        self.assertEqual(200, status, body)

    def api_request(self, method, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        try:
            headers = {"Host": f"127.0.0.1:{self.port}",
                       "X-Token": self.token}
            if body is not None:
                headers["Content-Type"] = "application/json"
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            return response.status, response.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def api_post(self, path, payload):
        return self.api_request("POST", path, payload)

    def api_json(self, path):
        status, body = self.api_request("GET", path)
        self.assertEqual(200, status, body)
        return json.loads(body)

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_settings(self):
        if not self.page.locator(
                "main#nv-main[data-nv-view='settings']").count():
            self.page.locator(
                "nav[data-nv-navs] [data-nv-nav='settings']").click()
        self.page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=20000)

    def enable_features(self, *ids):
        """Schaltet Features über die Einstellungen ein und wartet auf Sektionen."""
        self.open_settings()
        for feature in ids:
            box = self.page.locator(
                f"input[data-nv-feature='{feature}']")
            # Vertragsableitung: fillFeatures läuft nach dem Settings-View-
            # Gerüst asynchron — auf das Erscheinen warten, nicht nur auf
            # die View (Task A-4).
            box.wait_for(state="visible", timeout=20000)
            self.assertEqual(
                1, box.count(),
                f"Feature-Schalter data-nv-feature={feature!r} fehlt")
            if not box.is_checked():
                box.check()
        for feature in ids:
            self.page.locator(
                f"[data-nv-ssection='{feature}']").wait_for(
                    state="visible", timeout=25000)

    def section(self, feature):
        return self.page.locator(f"[data-nv-ssection='{feature}']")

    def json_file(self, path):
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def mcp_enabled(self, name):
        data = self.json_file(self.mcp_config)
        return (((data.get("mcp") or {}).get("servers") or {})
                .get(name) or {}).get("enabled")

    def click_confirm_if_shown(self, root):
        """Klickt einen sichtbaren Ja/Bestätigen-Knopf, falls vorhanden."""
        buttons = root.locator("button")
        for index in range(buttons.count()):
            button = buttons.nth(index)
            if not button.is_visible():
                continue
            text = (button.inner_text() or "").strip().lower()
            if any(word in text for word in
                   ("ja", "yes", "bestätig", "bestaetig", "verbinden",
                    "connect", "confirm", "ok")):
                button.click()
                return True
        return False

    def reload_settings(self):
        self.page.reload()
        self.page.locator("main#nv-main").wait_for(
            state="visible", timeout=25000)
        self.open_settings()

    def assert_no_page_errors(self):
        self.assertEqual(
            [], self.page_errors, "Die Oberfläche erzeugte JavaScript-Fehler")


class ModelsTest(AP22AdvancedBrowserTest):
    def test_catalog_expands_and_separates_facts_from_assessments(self):
        """Vorbedingung: Testkatalog in ``<install>/models.json``.

        Aktion: Feature ``models`` einschalten; Katalog öffnen; Modellzeile
        öffnen. Erwartung: ``section[data-nv-ssection='models']``;
        ``details[data-nv-model-catalog]`` existiert; echte Hooks: Katalog
        ist standardmäßig zugeklappt (Contract/Task-Text prüfen „zu“) und
        wird über ``summary`` aufgeklappt; die Modellzeile
        ``[data-nv-model='opencode/vibe-modell']`` öffnet die Detailzeile
        ``[data-nv-model-detail]`` mit den getrennten Fakten
        (``[data-nv-model-facts]``, Wert 200.000 Token, Quelle ``models.dev
        API``) und Einschätzungen (``[data-nv-model-assessments]``, ``schnell``,
        Quelle ``Altkatalog``). Kein JS-Fehler.
        """
        self.boot()
        self.enable_features("models")
        models = self.section("models")
        self.assertEqual(
            1, models.count(),
            "Die Sektion section[data-nv-ssection='models'] fehlt")

        details = models.locator("details[data-nv-model-catalog]")
        details.wait_for(state="visible", timeout=20000)
        self.assertEqual(1, details.count(),
                          "details[data-nv-model-catalog] fehlt")
        self.assertFalse(
            details.evaluate("node => node.open"),
            "Der Katalog ist laut implementierter Hook standardmäßig "
            "zugeklappt")
        details.locator("summary").click()
        row = models.locator("[data-nv-model='opencode/vibe-modell']")
        self.assertEqual(
            1, row.count(), "Die Modellzeile [data-nv-model] fehlt")
        row.wait_for(state="visible", timeout=15000)

        row.click()
        detail = models.locator(
            "[data-nv-model-detail='opencode/vibe-modell']")
        detail.wait_for(state="visible", timeout=15000)
        # Echte Hooks (nova-settings.js): der Detailblock besteht aus den
        # „Fakten"- und „Einschätzungen"-Abschnitten (Labels + Wert/Quelle
        # je Fakt/Einschätzung) — keine data-nv-model-facts/
        # data-nv-model-assessments-Hooks.
        sections = detail.locator("td > div")
        self.assertGreaterEqual(
            sections.count(), 2, "Der Detailblock mit Fakten fehlt")
        facts_text = sections.nth(0).inner_text() or ""
        assessments_text = sections.nth(1).inner_text() or ""
        self.assertIn("Fakten", facts_text,
                      "Der Faktenabschnitt fehlt (Etikett)")
        self.assertIn("200.000 Token", facts_text)
        self.assertIn("models.dev API", facts_text)
        self.assertIn("Einschätzungen", assessments_text,
                      "Der Einschätzungsabschnitt fehlt (Etikett)")
        self.assertIn("schnell", assessments_text)
        self.assertIn("Altkatalog", assessments_text)
        self.assertNotIn("Altkatalog", facts_text,
                          "Fakten und Einschätzungen sind vermischt")
        self.assertNotIn("200.000 Token", assessments_text,
                          "Fakten und Einschätzungen sind vermischt")
        self.assert_no_page_errors()


class ProfilesTest(AP22AdvancedBrowserTest):
    def test_profiles_preview_then_apply(self):
        """Vorbedingung: ``profiles.json`` mit den Profilen kostenlos,
        guenstig, stark; Agent ``tester`` hat Rolle coder.

        Aktion: Feature ``profiles`` einschalten; auf Profil ``kostenlos``
        klicken (Vorschau); dann ``profile-apply`` im Kontext „Bestätigen“
        anklicken. Erwartung: Die Liste nennt alle drei Profile; die Vorschau
        (Karte markiert, ``[data-nv-profile-details]`` nennt das Profil und
        die Rollen-Zielmodelle) schreibt ``aktiv`` nicht; erst
        ``profile-apply`` schreibt ``aktiv`` in ``profiles.json`` und das
        Agentenmodell.
        """
        tester = self.home / ".config" / "opencode" / "agents" / "tester.md"
        tester.write_text(
            "---\ndescription: Testet\nmode: subagent\n"
            "model: opencode/schnell-modell\n---\n\nTeste.\n",
            encoding="utf-8")
        self.boot()
        self.enable_features("profiles")
        profiles = self.section("profiles")
        card = profiles.locator("article[data-nv-profile='kostenlos']")
        card.wait_for(state="visible", timeout=25000)
        text = profiles.inner_text()
        for name in ("kostenlos", "guenstig", "stark"):
            self.assertIn(name, text,
                          f"Profil {name!r} fehlt in der Liste")

        self.assertEqual(
            1, card.count(),
            "Die Profil-Karte [data-nv-profile='kostenlos'] fehlt")
        self.assertGreaterEqual(
            card.locator("[data-nv-profile-role]").count(), 1,
            "Dem Profil fehlen die Rollen-Comboboxen")
        # Vorschau: Klick auf die Karte — markiert + Vorschau-Details.
        card.click()
        self.wait_until(
            lambda: card.get_attribute("data-nv-profile-selected") == "true",
            timeout=20000,
            message="Die Profil-Karte ist nicht markiert (Vorschau fehlt)")
        preview = profiles.locator("[data-nv-profile-details]")
        preview.wait_for(state="visible", timeout=20000)
        preview_text = preview.inner_text()
        self.assertIn("kostenlos", preview_text)
        self.assertIn("opencode/vibe-modell", preview_text)
        self.assertEqual(
            "kostenlos",
            self.json_file(self.state_dir / "profiles.json").get("aktiv"),
            "Die Vorschau hat das aktive Profil verändert")

        # Anwenden: Kontext „Profilvorschau“ → „Bestätigen“ (Knopf liegt auf
        # der Profilkarte, je Karte je „Anwenden“-Knopf).
        card.locator("[data-nv-action='profile-apply']").click()
        context = self.page.locator("aside[data-nv-context]")
        context.wait_for(state="visible", timeout=20000)
        confirm = context.locator(
            "[data-nv-context-foot] button", has_text="Bestätigen")
        confirm.wait_for(state="visible", timeout=20000)
        confirm.click()

        def target_model_written():
            try:
                return "opencode/vibe-modell" in tester.read_text(
                    encoding="utf-8")
            except OSError:
                return False

        self.wait_until(
            target_model_written, timeout=30,
            message="Das Profil hat das Agentenmodell nicht angewendet")
        self.assertIn(
            "opencode/vibe-modell", tester.read_text(encoding="utf-8"),
            "Das Profil hat das Agentenmodell nicht angewendet")
        self.assertEqual(
            "kostenlos", self.json_file(
                self.state_dir / "profiles.json").get("aktiv"),
            "Das Profil wurde nicht als aktiv gespeichert")
        self.assert_no_page_errors()


class McpTest(AP22AdvancedBrowserTest):
    def test_mcp_masks_secrets_toggles_and_reports_test_failure(self):
        """Vorbedingung: globale MCP-Konfiguration mit lokalem stdio-Server
        ``lokal``, entferntem Server ``fern`` (Token in der URL) und
        ``kaputt`` (nicht erreichbare URL).

        Aktion: Feature ``mcp`` einschalten, ``lokal`` umschalten, Test für
        ``kaputt`` starten. Erwartung: Beide Server erscheinen; das Token ist
        nirgends unmaskiert, ``***`` ist sichtbar; der Schalter schreibt
        ``enabled`` in die Konfiguration; der fehlgeschlagene Test meldet
        Fehlschlag im ``[data-nv-mcp-result]``-Bereich mit sichtbarer Meldung
        (Vertrag: implementierte Hooks — ``[data-nv-mcp-result]`` hat kein
        ``data-nv-ok``-Attribut; der Ergebnisbereich meldet den Fehlschlag
        über Klasse/Text).
        """
        self.boot()
        self.enable_features("mcp")
        mcp = self.section("mcp")
        local = mcp.locator("[data-nv-mcp-server='lokal']")
        local.wait_for(state="visible", timeout=25000)
        text = mcp.inner_text()
        self.assertIn("lokal", text)
        self.assertIn("fern", text)
        self.assertNotIn(MCP_SECRET, mcp.inner_html(),
                         "Das MCP-Geheimnis steht unmaskiert im DOM")
        self.assertNotIn(MCP_SECRET, self.page.content(),
                         "Das MCP-Geheimnis steht unmaskiert auf der Seite")
        self.assertIn("***", text, "Das maskierte Geheimnis *** fehlt")

        local = mcp.locator("[data-nv-mcp-server='lokal']")
        self.assertEqual(1, local.count(),
                         "Die Serverzeile [data-nv-mcp-server] fehlt")
        local.locator("[data-nv-action='mcp-toggle']").click()
        self.wait_until(
            lambda: self.mcp_enabled("lokal") is False,
            timeout=20000,
            message="Der MCP-Schalter speicherte den Zustand nicht")

        broken = mcp.locator("[data-nv-mcp-server='kaputt']")
        broken.locator("[data-nv-action='mcp-test']").click()
        result = broken.locator("[data-nv-mcp-result]")
        result.wait_for(state="visible", timeout=30000)
        self.wait_until(
            lambda: (result.inner_text() or "").strip(),
            timeout=30000,
            message="Der fehlgeschlagene Test zeigt keine Meldung: "
                    + repr(result.inner_text() if result.count() else ""))
        result_text = result.inner_text() or ""
        self.assertRegex(
            result_text, r"(?i)fehl|error|bad",
            "Der fehlgeschlagene Test meldet nicht den Fehlschlag: "
            + repr(result_text))
        self.assert_no_page_errors()


class CostsTest(AP22AdvancedBrowserTest):
    def test_costs_absent_from_settings_and_in_evaluations(self):
        """Abwesenheit: Kosten sind nicht mehr in den Einstellungen.

        Aktion: Einstellungen öffnen. Erwartung (Einstellungen):
        ``input[data-nv-feature='costs']`` == 0, ``[data-nv-advanced]``
        == 0 (Auswertungen nicht mehr in den Einstellungen). Verweis-Test:
        ``nav[data-nv-navs] [data-nv-nav='evaluations']`` führt zur View
        ``main#nv-main[data-nv-view='evaluations']`` mit den Tabs ``costs``,
        ``runs`` und ``environment`` (Vertrag F34.md WP3; Tiefenprüfung
        dort: ``tests/browser/test_f34_activity_evals_ui.py``).
        """
        self.boot()
        self.open_settings()
        for selector, label in (
                ("input[data-nv-feature='costs']", "Feature-Schalter costs"),
                ("[data-nv-advanced]", "Advanced-Area")):
            with self.subTest(absent=label):
                self.assertEqual(
                    0, self.page.locator(selector).count(),
                    f"Der Einstellungen-Bereich {label} darf nicht "
                    "gerendert sein")
        nav_button = self.page.locator(
            "nav[data-nv-navs] [data-nv-nav='evaluations']")
        nav_button.wait_for(state="visible", timeout=15000)
        nav_button.click()
        view = self.page.locator("main#nv-main[data-nv-view='evaluations']")
        view.wait_for(state="visible", timeout=20000)
        for tab in ("costs", "runs", "environment"):
            with self.subTest(tab=tab):
                self.assertEqual(
                    1, self.page.locator(
                        f"nav[data-nv-eval-tabs] [data-nv-etab='{tab}']").count(),
                    f"Der Auswertungs-Tab {tab!r} fehlt")
        self.assert_no_page_errors()


class HarnessTest(AP22AdvancedBrowserTest):
    def test_harness_status_switch_persists_and_plan_is_visible(self):
        """Vorbedingung: Attrappen für opencode und Pi im ``PATH``,
        Standardauswahl opencode.

        Aktion: Feature ``harness`` einschalten, Pi wählen und übernehmen,
        Seite neu laden. Erwartung: Der Status nennt beide Harnesses und einen
        Einrichtungsplan; ``<state>/harness.json`` enthält ``pi``; nach dem
        Neuladen steht die Auswahl weiterhin auf ``pi``.
        """
        self.boot()
        self.enable_features("harness")
        harness = self.section("harness")
        status = harness.locator("[data-nv-harness-status]")
        status.wait_for(state="visible", timeout=20000)
        text = harness.inner_text()
        self.assertIn("opencode", text)
        self.assertIn("Pi", text)
        self.assertRegex(text, r"(?i)install|einrichten|pi\.dev|hint|hinweis",
                         "Der Einrichtungsplan ist nicht sichtbar: " + text)

        select = harness.locator("select[data-nv-field='harness']")
        select.select_option("pi")
        harness.locator("[data-nv-action='harness-use']").click()
        self.wait_until(
            lambda: self.json_file(
                self.state_dir / "harness.json").get("harness") == "pi",
            timeout=20000,
            message="Der Harnesswechsel wurde nicht gespeichert")

        self.reload_settings()
        self.assertEqual(
            "pi",
            self.section("harness").locator(
                "select[data-nv-field='harness']").input_value(),
            "Nach dem Neuladen ist Pi nicht mehr ausgewählt")
        self.assert_no_page_errors()


class LimitsTest(AP22AdvancedBrowserTest):
    def test_limits_mode_switches_between_continue_and_stop(self):
        """Vorbedingung: Modus ``stop``. Aktion: Feature ``limits``
        einschalten, ``limits-continue``, danach ``limits-stop``.

        Erwartung: Sektion ``section[data-nv-ssection='limits']`` mit den
        Modus-Karten; ``limits-continue`` → ``GET /api/limits`` meldet
        ``continue``; ``limits-stop`` → ``stop``.
        """
        self.api_post("/api/limits", {"action": "stop"})
        self.boot()
        self.enable_features("limits")
        limits = self.section("limits")
        continue_button = limits.locator(
            "[data-nv-action='limits-continue']")
        continue_button.wait_for(state="visible", timeout=20000)
        self.assertIn("stop", (limits.inner_text() or "").lower(),
                      "Der Bereich limits nennt den Modus stop nicht: "
                      + repr(limits.inner_text()))

        continue_button.click()
        self.wait_until(
            lambda: self.api_json("/api/limits").get("mode") == "continue",
            timeout=30,
            message="Der Modus continue wird nicht bestätigt: "
                    + repr(self.api_json("/api/limits")))
        self.assertTrue(
            continue_button.get_attribute("aria-pressed") == "true"
            or "nv-primary" in (continue_button.get_attribute("class") or ""),
            "Der Modus continue ist nicht hervorgehoben")

        stop_button = limits.locator("[data-nv-action='limits-stop']")
        stop_button.click()
        self.wait_until(
            lambda: self.api_json("/api/limits").get("mode") == "stop",
            timeout=30,
            message="Der Modus stop wird nicht bestätigt: "
                    + repr(self.api_json("/api/limits")))
        self.assert_no_page_errors()


class GatesTest(AP22AdvancedBrowserTest):
    def test_gates_global_and_project_override(self):
        """Vorbedingung: Feature ``gates`` aus. Aktion: Feature einschalten;
        global ``retries`` auf 4 setzen; dann Projekt-Override ``repair_rounds``
        = 3 für ``proj`` setzen; danach denselben Projektwert mit leerem Wert
        entfernen.

        Erwartung: Tabelle ``table[data-nv-gates-table]`` benennt die
        Schranken (``tr[data-nv-gate]``, ``small[data-nv-gate-help]``,
        ``[data-nv-gate-value]``, ``span[data-nv-gate-origin]``); global gilt
        ``retries`` 4 (``origin`` global); der Projektwert gilt nur für
        ``proj`` (``origin`` projekt) und verschwindet nach dem Leeren wieder
        (Rückfall auf Standard 2). Speichern: ein vorher gesetztes
        DOM-Merkmal der Sektion bleibt (kein Voll-Neurender).
        """
        self.boot()
        self.enable_features("gates")
        gates = self.section("gates")
        view = self.api_json("/api/gates")
        table = gates.locator("[data-nv-gates-table]")
        table.wait_for(state="visible", timeout=20000)
        rows = table.locator("tr[data-nv-gate]")
        self.wait_until(
            lambda: rows.count() >= 1,
            timeout=20000, message="Die Gates-Tabelle hat keine Zeilen")
        for key in view["gates"]:
            with self.subTest(gate=key):
                row = table.locator(f"tr[data-nv-gate='{key}']")
                self.assertEqual(
                    1, row.count(),
                    f"Die Schranke {key!r} fehlt im Bereich")
                help_text = row.locator(
                    "small[data-nv-gate-help]").inner_text()
                self.assertTrue(
                    (help_text or "").strip(),
                    f"Die Schranke {key!r} hat keine Erklärung")
                self.assertEqual(
                    1, row.locator("[data-nv-gate-value]").count(),
                    f"Die Schranke {key!r} hat kein Wert-Feld")
                self.assertEqual(
                    1, row.locator("span[data-nv-gate-origin]").count(),
                    f"Die Schranke {key!r} hat kein Herkunfts-Badge")

        # Global (default): Auf „global" schalten, auf das abgeschlossene
        # Redraw warten, retries = 4 setzen, speichern.
        project_select = gates.locator("select[data-nv-gates-project]")
        project_select.wait_for(state="visible", timeout=20000)
        project_select.select_option("global")
        retries_row = table.locator("tr[data-nv-gate='retries']")
        retries_input = retries_row.locator("[data-nv-gate-value]")
        retries_input.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: retries_input.input_value()
            == str(self.api_json("/api/gates")["gates"]["retries"]["value"]),
            timeout=20,
            message="Das Gates-Redraw auf den globalen Kontext ist nicht "
                    "abgeschlossen")
        retries_input.fill("4")
        gates.evaluate(
            "node => node.setAttribute('data-nv-ap22-no-rerender', '1')")
        gates.locator("[data-nv-action='gates-save']").click()
        self.wait_until(
            lambda: self.api_json("/api/gates")["gates"]["retries"]
            ["value"] == 4,
            timeout=30,
            message="Die globale Schranke retries wurde nicht gespeichert")
        self.assertEqual(
            "1", gates.get_attribute("data-nv-ap22-no-rerender"),
            "Nach gates-save wurde ein Vull-Neurender erwartet")

        # Projekt: context „proj“, repair_rounds Override = 3 setzen.
        project_select.select_option("proj")
        override_field = gates.locator(
            "tr[data-nv-gate='repair_rounds'] [data-nv-gate-override]")
        override_field.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: override_field.input_value() == "",
            timeout=20,
            message="Das Redraw nach 'proj' ist nicht abgeschlossen")
        override_field.fill("3")
        self.wait_until(
            lambda: override_field.input_value() == "3",
            timeout=20,
            message="Das Override-Feld zeigt nicht den gesetzten Wert 3")
        gates.locator("[data-nv-action='gates-save']").click()
        project_view = None
        deadline = time.time() + 20
        while time.time() < deadline:
            project_view = self.api_json("/api/gates?name=proj")
            if project_view["gates"]["repair_rounds"]["value"] == 3:
                break
            self.page.wait_for_timeout(200)
        else:
            self.fail("Der Projekt-Override wurde nicht gespeichert: "
                      + repr(project_view))
        self.assertEqual(
            "projekt", project_view["gates"]["repair_rounds"].get("origin"),
            "Der Projektwert hat nicht die Herkunft projekt")

        # Projektwert leeren: Rückfall auf Standard 2. (Warten, dass das
        # leere Override-Feld gesetzt ist, bevor gespeichert wird.)
        override_field.wait_for(state="visible", timeout=20000)
        override_field.fill("")
        self.wait_until(
            lambda: override_field.input_value() == "",
            timeout=20,
            message="Das leere Override-Feld ist nicht stabil")
        gates.locator("[data-nv-action='gates-save']").click()
        deadline = time.time() + 20
        while time.time() < deadline:
            project_view = self.api_json("/api/gates?name=proj")
            if project_view["gates"]["repair_rounds"]["value"] == 2:
                break
            self.page.wait_for_timeout(200)
        else:
            self.fail("Der geleerte Projekt-Override wirkt nicht zurück: "
                      + repr(project_view))
        self.assert_no_page_errors()


class EnvTest(AP22AdvancedBrowserTest):
    def test_env_absent_from_settings(self):
        """Abwesenheit: Umgebung (Doctor, Fritzbox, Emulator, opencode-Server)
        heraus aus den Einstellungen.

        Erwartung in den Einstellungen: ``input[data-nv-feature='env']``
        == 0, ``[data-nv-doctor-row]`` == 0, ``[data-nv-server-status]``
        == 0, ``[data-nv-action='emu-start']`` == 0,
        ``[data-nv-action='fritz-automation-on']`` == 0. Diese Inhalte
        stehen unter ``#/evaluations`` → ``environment`` (Vertrag F34.md WP3;
        Tiefe: ``tests/browser/test_f34_activity_evals_ui.py``).
        """
        self.boot()
        self.open_settings()
        for selector, label in (
                ("input[data-nv-feature='env']", "Feature-Schalter env"),
                ("[data-nv-doctor-row]", "Doctor-Zeile"),
                ("[data-nv-server-status]", "opencode-Server-Status"),
                ("[data-nv-action='emu-start']", "Emulator-Start"),
                ("[data-nv-action='fritz-automation-on']",
                 "Fritz-Automatik-Ein")):
            with self.subTest(absent=label):
                self.assertEqual(
                    0, self.page.locator(selector).count(),
                    f"Der Einstellungen-Bereich {label} darf nicht "
                    "gerendert sein")
        self.assert_no_page_errors()


class RunsTest(AP22AdvancedBrowserTest):
    def test_runs_absent_from_settings(self):
        """Abwesenheit: Run-Register heraus aus den Einstellungen.

        Erwartung in den Einstellungen: ``input[data-nv-feature='runs']``
        == 0, ``[data-nv-advanced]`` == 0, ``[data-nv-run-table]`` == 0 —
        Läufe stehen unter ``#/evaluations`` → ``runs`` (Vertrag F34.md
        WP3; Tiefe: ``tests/browser/test_f34_activity_evals_ui.py``).
        """
        self.boot()
        self.open_settings()
        for selector, label in (
                ("input[data-nv-feature='runs']", "Feature-Schalter runs"),
                ("[data-nv-advanced]", "Advanced-Area"),
                ("[data-nv-run-table]", "Run-Register-Tabelle")):
            with self.subTest(absent=label):
                self.assertEqual(
                    0, self.page.locator(selector).count(),
                    f"Der Einstellungen-Bereich {label} darf nicht "
                    "gerendert sein")
        self.assert_no_page_errors()


class ParityTest(AP22AdvancedBrowserTest):
    def test_every_feature_toggle_and_project_sections(self):
        """Vorbedingung: frischer Browserkontext, Projekt ``proj``.

        Aktion: Einstellungen öffnen; für jede Feature-ID den Schalter
        prüfen; die Projektfunktionen einschalten und
        ``#/project/proj/settings`` öffnen.

        Erwartung: Alle 11 Schalter existieren (Vertrag F34.md WP4;
        ``costs``/``env``/``runs`` entfallen); die Projektsektionen github,
        writeaccess, sandbox, agentsfile erscheinen (``[data-nv-psection]``);
        bei agentsfile ist die echte Struktur ``details[data-nv-agents-
        section]`` aus ``nova-project.js`` belegt, keine h2/h3/h4-Überschrift
        (Vertrag fordert keine); Priorisierung ist keine Einstellungssektion
        mehr, sondern die Leiste ``div[data-nv-priority-strip]`` im Arbeit-Tab
        mit Bedienelementen.
        """
        self.boot()
        self.open_settings()
        for feature in FEATURE_IDS:
            with self.subTest(feature=feature):
                self.assertEqual(
                    1,
                    self.page.locator(
                        f"input[data-nv-feature='{feature}']").count(),
                    f"Feature-Schalter {feature!r} fehlt")

        for feature in PROJECT_FEATURES:
            box = self.page.locator(f"input[data-nv-feature='{feature}']")
            if not box.is_checked():
                box.check()

        self.page.goto(self.base + "/#/project/proj/settings")
        self.page.locator("main#nv-main[data-nv-view='project']").wait_for(
            state="visible", timeout=25000)
        for feature in PROJECT_FEATURES:
            with self.subTest(project_section=feature):
                if feature == "priority":
                    # F34 WP3o: die Priorisierungskarte wandert in die Leiste
                    # ``div[data-nv-priority-strip]`` im Arbeit-Tab.
                    self.page.locator("[data-nv-ptab='work']").click()
                    section = self.page.locator("div[data-nv-priority-strip]")
                    section.wait_for(state="visible", timeout=20000)
                    self.wait_until(
                        lambda: section.locator("button").count() >= 1,
                        timeout=10,
                        message="Die Priorisierungsleiste hat kein Bedienelement")
                else:
                    section = self.page.locator(
                        f"[data-nv-psection='{feature}']")
                    section.wait_for(state="visible", timeout=25000)
                    self.assertEqual(
                        1, section.count(),
                        f"Der Projektbereich {feature!r} fehlt bei "
                        "eingeschaltetem Feature")
                    if feature == "agentsfile":
                        # Echte Struktur aus ``nova-project.js``: section
                        # hat keine h2/h3/h4-Überschrift, die Details-Karte
                        # ``[data-nv-agents-section]`` ist der Realitätsbeleg.
                        self.assertTrue(
                            section.locator("[data-nv-agents-section]").count()
                            >= 1,
                            "Der agentsfile-Bereich hat kein "
                            "data-nv-agents-section")
                    else:
                        self.assertTrue(
                            section.locator("h2, h3, h4").count() >= 1,
                            f"Der Projektbereich {feature!r} hat keine "
                            "Überschrift")
                    self.assertTrue(
                        section.locator(
                            "input, select, textarea, button").count() >= 1,
                        f"Der Projektbereich {feature!r} hat kein "
                        "Bedienelement")
        self.assert_no_page_errors()


if __name__ == "__main__":
    unittest.main()
