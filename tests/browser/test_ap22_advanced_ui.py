"""Browserabnahme AP22, Meilenstein C: erweiterte Bereiche und Paritätsrundgang.

Die Fälle leiten sich aus ``docs/features/AP22.md`` ab — Abschnitt
„Einstellungen (nova-settings.js)“ (erweiterte Bereiche
``[data-nv-advanced="<id>"]``), „Paritätsmatrix“ sowie dem Testplan
„Meilenstein C“. Jeder Fall schaltet die benötigten Feature-Schalter zuerst
über ``#/settings`` ein (``input[data-nv-feature="<id>"]``); die Bereiche
liegen danach ohne Neuladen sichtbar vor.

Das echte Dashboard läuft als eigener Prozess auf einem freien Loopback-Port
mit isoliertem ``VIBE``/``HOME``/``VIBE_STATE``/``VIBE_INSTALL``. opencode und
Pi sind Attrappen im ``PATH``, der opencode-Server ist eine lokale
HTTP-Attrappe, der Fritzbox-Helfer ist ein nachgebildetes Python-Skript. Es
gibt keine Modellaufrufe und keinen Netzzugriff außerhalb von Loopback.

Abgeleitete DOM-Hooks (Test-Vertrag)
------------------------------------
Der Vertrag schreibt für die erweiterten Bereiche nur den Abschnitts-Hook
``[data-nv-advanced="<id>"]`` sowie für Limits/Gates konkrete Feld-/Aktions-
Hooks fest. Für die übrigen Bedienelemente nennt er keine Namen. Diese Tests
binden deshalb an die folgenden, hier verbindlich dokumentierten Hooks; sie
folgen dem Muster der übrigen AP22-Hooks (``data-nv-field``,
``data-nv-action``, ``data-nv-<bereich>``):

===============================  ==========================================
Bereich / Hook                   Bedeutung
===============================  ==========================================
``models``
  ``details[data-nv-model-catalog]``  ein-/ausklappbarer Katalog
  ``[data-nv-model="<id>"]``          Modellzeile der Übersicht
  ``[data-nv-model-detail="<id>"]``  Detailzeile (nach Klick auf die Zeile)
  ``[data-nv-model-facts]``          Faktenblock der Detailzeile
  ``[data-nv-model-assessments]``    Einschätzungsblock der Detailzeile
``profiles``
  ``select[data-nv-field="profile"]`` Profilauswahl
  ``[data-nv-action="profile-preview"]`` Vorschau anfordern (schreibt nicht)
  ``[data-nv-profile-preview]``       Vorschaubereich
  ``[data-nv-action="profile-apply"]`` Profil anwenden
``mcp``
  ``[data-nv-mcp-server="<name>"]``   Serverzeile
  ``[data-nv-action="mcp-toggle"]``   Zeilenaktion an/aus
  ``[data-nv-action="mcp-test"]``     Zeilenaktion Verbindungstest
  ``[data-nv-mcp-result]``            Ergebnisbereich (``data-nv-ok``)
``costs``
  ``[data-nv-cost-project="<name>"]`` Projektzeile der Übersicht
  ``[data-nv-cost-detail]``           Detailbereich
  ``[data-nv-cost-model="<id>"][data-nv-cost-field="input|cached_input|output"]``
  ``[data-nv-action="cost-save"]``    Preise speichern
``harness``
  ``select[data-nv-field="harness"]`` Harnessauswahl
  ``[data-nv-action="harness-use"]``  Auswahl übernehmen
  ``[data-nv-harness-status]``        Status-/Einrichtungsbereich
``env``
  ``[data-nv-doctor-row]``            Doctor-Zeile (``data-nv-ok="true|false"``)
  ``[data-nv-paths]``                 aufgelöste Pfade (aus ``/api/paths``)
  ``[data-nv-action="fritz-automation-on|fritz-automation-off"]``
  ``[data-nv-action="fritz-reconnect"]`` und ``[data-nv-fritz-result]``
  ``[data-nv-action="emu-start|emu-stop"]``
  ``[data-nv-server-status]`` und ``[data-nv-action="server-start|server-stop"]``
``runs``
  ``[data-nv-run="<id>"]``            Registerzeile
  ``[data-nv-action="runs-prune"]``   Register bereinigen
===============================  ==========================================

Bewusste Vertragsableitungen
----------------------------
* Der Vertrag nennt für ``profiles`` „Liste + use mit Vorschau/Bestätigung“.
  Geprüft wird: eine Vorschau (Agent → Zielmodell) ist sichtbar, bevor
  angewendet wird, und das Anwenden schreibt ``aktiv`` in ``profiles.json``.
* Für ``mcp`` verlangt der Vertrag „Geheimnisse maskiert“. Geprüft wird, dass
  ein Token in der URL weder im DOM noch in der Serverantwort unmaskiert
  auftaucht und stattdessen ``***`` sichtbar ist. Ein fehlgeschlagener Test
  wird über ``[data-nv-mcp-result][data-nv-ok="false"]`` mit sichtbarer
  Meldung nachgewiesen (strukturierte Fehleranzeige).
* Für ``runs`` wird die in AP20 bewährte Technik genutzt: ``runs.json`` liegt
  **vor** dem Serverstart im Laufzeitordner; der Eintrag nennt eine sicher
  fehlende tmux-Sitzung, damit ``prune`` ihn als beendet markiert.
* Die Paritätsmatrix führt ``priority`` unter „Arbeit“, der Auftrag zu
  Meilenstein C nennt es zusätzlich als Projektbereich. Der Rundgang
  akzeptiert daher sowohl ``[data-nv-psection="priority"]`` als auch den
  dokumentierten Arbeitsbereich ``[data-nv-priority]``.

Testfälle (Kurzfassung; Details in den Methoden)
------------------------------------------------
``ModelsTest.test_catalog_expands_and_separates_facts_from_assessments``
``ProfilesTest.test_profiles_preview_then_apply``
``McpTest.test_mcp_masks_secrets_toggles_and_reports_test_failure``
``CostsTest.test_costs_overview_detail_and_price_persistence``
``HarnessTest.test_harness_status_switch_persists_and_plan_is_visible``
``LimitsTest.test_limits_mode_switches_between_continue_and_stop``
``GatesTest.test_gates_global_and_project_override``
``EnvTest.test_env_doctor_paths_fritz_emulator_and_server``
``RunsTest.test_runs_prune_marks_missing_session_ended``
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

FEATURE_IDS = (
    "github", "models", "profiles", "mcp", "costs", "harness", "limits",
    "gates", "env", "sandbox", "writeaccess", "agentsfile", "priority",
    "runs",
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
            self.page.locator("[data-nv-nav='settings']").click()
        self.page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=20000)

    def enable_features(self, *ids):
        """Schaltet Features über die Einstellungen ein und wartet auf Bereiche."""
        self.open_settings()
        for feature in ids:
            box = self.page.locator(
                f"input[data-nv-feature='{feature}']")
            self.assertEqual(
                1, box.count(),
                f"Feature-Schalter data-nv-feature={feature!r} fehlt")
            if not box.is_checked():
                box.check()
        for feature in ids:
            self.page.locator(
                f"[data-nv-advanced='{feature}']").wait_for(
                    state="visible", timeout=25000)

    def section(self, feature):
        return self.page.locator(f"[data-nv-advanced='{feature}']")

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
        """Vorbedingung: Feature ``models`` aus, Testkatalog in
        ``<install>/models.json``.

        Aktion: Feature einschalten, Katalog aufklappen, Modellzeile öffnen.
        Erwartung: ``[data-nv-advanced="models"]`` erscheint; der Katalog ist
        zunächst eingeklappt (Modellzeile unsichtbar) und wird über
        ``details[data-nv-model-catalog]`` aufgeklappt. Die Detailzeile trennt
        Fakten (``[data-nv-model-facts]``, Wert 200.000 Token, Quelle
        ``models.dev API``) von Einschätzungen
        (``[data-nv-model-assessments]``, ``schnell``, Quelle
        ``Altkatalog``). Kein JS-Fehler.
        """
        self.boot()
        self.assertEqual(
            0, self.section("models").count(),
            "Der Bereich models ist ohne Feature-Schalter vorhanden")
        self.enable_features("models")
        models = self.section("models")
        row = models.locator("[data-nv-model='opencode/vibe-modell']")
        self.assertEqual(
            1, row.count(), "Die Modellzeile [data-nv-model] fehlt")
        self.assertFalse(
            row.is_visible(),
            "Der Katalog ist ohne Aufklappen bereits sichtbar")

        details = models.locator("details[data-nv-model-catalog]")
        self.assertEqual(1, details.count(),
                         "details[data-nv-model-catalog] fehlt")
        details.locator("summary").click()
        row.wait_for(state="visible", timeout=15000)

        row.click()
        detail = models.locator(
            "[data-nv-model-detail='opencode/vibe-modell']")
        detail.wait_for(state="visible", timeout=15000)
        facts = detail.locator("[data-nv-model-facts]")
        assessments = detail.locator("[data-nv-model-assessments]")
        self.assertEqual(1, facts.count(), "Der Faktenblock fehlt")
        self.assertEqual(1, assessments.count(),
                         "Der Einschätzungsblock fehlt")
        facts_text = facts.inner_text()
        assessment_text = assessments.inner_text()
        self.assertIn("200.000 Token", facts_text)
        self.assertIn("models.dev API", facts_text)
        self.assertIn("fakt", facts_text.lower())
        self.assertIn("schnell", assessment_text)
        self.assertIn("Altkatalog", assessment_text)
        self.assertIn("einsch", assessment_text.lower())
        self.assertNotIn("Altkatalog", facts_text,
                         "Fakten und Einschätzungen sind vermischt")
        self.assertNotIn("200.000 Token", assessment_text,
                         "Fakten und Einschätzungen sind vermischt")
        self.assert_no_page_errors()


class ProfilesTest(AP22AdvancedBrowserTest):
    def test_profiles_preview_then_apply(self):
        """Vorbedingung: ``profiles.json`` mit den Profilen kostenlos,
        guenstig, stark; Agent ``tester`` hat Rolle coder.

        Aktion: Feature ``profiles`` einschalten, Profil ``kostenlos``
        vorsehen, dann anwenden. Erwartung: Die Liste nennt alle drei
        Profile; die Vorschau zeigt ``tester`` mit dem Zielmodell, ohne
        ``profiles.json`` zu verändern; erst ``profile-apply`` schreibt
        ``aktiv`` und das Agentenmodell.
        """
        tester = self.home / ".config" / "opencode" / "agents" / "tester.md"
        tester.write_text(
            "---\ndescription: Testet\nmode: subagent\n"
            "model: opencode/schnell-modell\n---\n\nTeste.\n",
            encoding="utf-8")
        self.boot()
        self.enable_features("profiles")
        profiles = self.section("profiles")
        text = profiles.inner_text()
        for name in ("kostenlos", "guenstig", "stark"):
            self.assertIn(name, text,
                          f"Profil {name!r} fehlt in der Liste")

        select = profiles.locator("select[data-nv-field='profile']")
        select.select_option("kostenlos")
        before = self.json_file(self.state_dir / "profiles.json")
        profiles.locator("[data-nv-action='profile-preview']").click()
        preview = profiles.locator("[data-nv-profile-preview]")
        preview.wait_for(state="visible", timeout=20000)
        preview_text = preview.inner_text()
        self.assertIn("tester", preview_text)
        self.assertIn("opencode/vibe-modell", preview_text)
        self.assertEqual(
            before.get("aktiv"), self.json_file(
                self.state_dir / "profiles.json").get("aktiv"),
            "Die Vorschau hat das aktive Profil bereits verändert")

        profiles.locator("[data-nv-action='profile-apply']").click()

        # Warte auf die echte Wirkung: Das Profil ``kostenlos`` weist der
        # Rolle ``coder`` das Modell ``opencode/vibe-modell`` zu; Agent
        # ``tester`` trägt die Rolle ``coder``. Der frühere Vergleich von
        # ``aktiv`` allein war wirkungslos, weil die Fixture dort bereits
        # ``kostenlos`` einträgt.
        def target_model_written():
            try:
                return "opencode/vibe-modell" in tester.read_text(
                    encoding="utf-8")
            except OSError:
                return False

        self.wait_until(
            target_model_written,
            timeout=20000,
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
        ``enabled`` in die Konfiguration; der fehlgeschlagene Test zeigt
        ``[data-nv-mcp-result][data-nv-ok="false"]`` mit Meldung.
        """
        self.boot()
        self.enable_features("mcp")
        mcp = self.section("mcp")
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
            lambda: result.get_attribute("data-nv-ok") == "false",
            timeout=30000,
            message="Der fehlgeschlagene Test meldet data-nv-ok nicht false: "
                    + repr(result.inner_text() if result.count() else ""))
        self.assertTrue((result.inner_text() or "").strip(),
                        "Der fehlgeschlagene Test zeigt keine Meldung")
        self.assert_no_page_errors()


class CostsTest(AP22AdvancedBrowserTest):
    def test_costs_overview_detail_and_price_persistence(self):
        """Vorbedingung: opencode-Datenbank mit einer Sitzung für Projekt
        ``proj``/Paket ``F1`` und 1 Mio. Eingabe- sowie 500k Ausgabetokens.

        Aktion: Feature ``costs`` einschalten, Projekt öffnen, Preise
        (2 / 0.5 / 4) speichern, Seite neu laden. Erwartung: Übersicht nennt
        ``proj``; der Detailbereich zeigt Tokens und unbekannte Preise; nach
        dem Speichern stehen die Preise in ``<install>/costs.json`` und die
        Kosten 3,1000 € bleiben nach dem Neuladen erhalten.
        """
        self.boot()
        self.enable_features("costs")
        costs = self.section("costs")
        row = costs.locator("[data-nv-cost-project='proj']")
        row.wait_for(state="visible", timeout=20000)
        overview = costs.inner_text()
        self.assertIn("proj", overview)
        self.assertIn("1.000.000", overview.replace(",", "."),
                      "Die Übersicht nennt die Eingabetokens nicht")

        row.click()
        detail = costs.locator("[data-nv-cost-detail]")
        detail.wait_for(state="visible", timeout=20000)
        detail_text = detail.inner_text()
        self.assertIn("opencode/test-modell", detail_text)
        self.assertIn("F1", detail_text)
        self.assertRegex(detail_text, r"unbekannt|unknown|Price unknown")

        for field, value in (("input", "2"), ("cached_input", "0.5"),
                             ("output", "4")):
            costs.locator(
                "input[data-nv-cost-model='opencode/test-modell']"
                f"[data-nv-cost-field='{field}']").fill(value)
        costs.locator("[data-nv-action='cost-save']").click()
        costs_path = self.install / "costs.json"
        self.wait_until(
            lambda: self.json_file(costs_path).get("projects", {})
            .get("proj", {}).get("models", {})
            .get("opencode/test-modell") == {
                "input": 2.0, "cached_input": 0.5, "output": 4.0},
            timeout=20000,
            message="Die Preise wurden nicht gespeichert: "
                    + repr(self.json_file(costs_path)))
        self.wait_until(
            lambda: "3,1" in (self.section("costs").inner_text()
                              .replace(".", ",")),
            timeout=20000,
            message="Die Kosten wurden nicht neu berechnet: "
                    + repr(self.section("costs").inner_text()))

        self.reload_settings()
        self.section("costs").locator(
            "[data-nv-cost-project='proj']").click()
        detail = self.section("costs").locator("[data-nv-cost-detail]")
        detail.wait_for(state="visible", timeout=20000)
        self.assertIn("3,1", detail.inner_text().replace(".", ","),
                      "Die gespeicherten Preise gelten nach dem Reload nicht")
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
        einschalten, ``limits-continue``, dann ``limits-stop``.

        Erwartung: Der Bereich zeigt den Modus; jeder Knopf aktualisiert die
        Anzeige und ``GET /api/limits`` bestätigt den neuen Modus.
        """
        self.api_post("/api/limits", {"action": "stop"})
        self.boot()
        self.enable_features("limits")
        limits = self.section("limits")
        self.assertIn("stop", limits.inner_text().lower())

        limits.locator("[data-nv-action='limits-continue']").click()
        self.wait_until(
            lambda: "continue" in limits.inner_text().lower(),
            timeout=20000,
            message="Der Modus continue wird nicht angezeigt")
        self.assertEqual("continue", self.api_json("/api/limits")["mode"])

        limits.locator("[data-nv-action='limits-stop']").click()
        self.wait_until(
            lambda: "stop" in limits.inner_text().lower(),
            timeout=20000,
            message="Der Modus stop wird nicht angezeigt")
        self.assertEqual("stop", self.api_json("/api/limits")["mode"])
        self.assert_no_page_errors()


class GatesTest(AP22AdvancedBrowserTest):
    def test_gates_global_and_project_override(self):
        """Vorbedingung: Features ``gates`` aus, Projekt ``proj`` vorhanden.

        Aktion: Feature einschalten; global ``retries`` auf 4 setzen; dann
        Projekt-Override ``repair_rounds`` = 3 für ``proj`` setzen; danach
        denselben Projektwert mit leerem Wert entfernen.

        Erwartung: Der Bereich zeigt alle fünf Schlüssel mit Werten; global
        gilt ``retries`` 4 (``origin`` global); der Projektwert gilt nur für
        ``proj`` (``origin`` projekt) und verschwindet nach dem Leeren wieder
        (Rückfall auf Standard 2).
        """
        self.boot()
        self.enable_features("gates")
        gates = self.section("gates")
        view = self.api_json("/api/gates")
        text = gates.inner_text()
        for key, entry in view["gates"].items():
            with self.subTest(gate=key):
                self.assertIn(key, text,
                              f"Die Schranke {key!r} fehlt im Bereich")
                self.assertIn(str(entry["value"]), text,
                              f"Der Wert der Schranke {key!r} fehlt")

        gates.locator("select[data-nv-field='gates-key']").select_option(
            "retries")
        gates.locator("input[data-nv-field='gates-value']").fill("4")
        gates.locator("[data-nv-action='gates-save']").click()
        self.wait_until(
            lambda: self.api_json("/api/gates")["gates"]["retries"]
            ["value"] == 4,
            timeout=20000,
            message="Die globale Schranke retries wurde nicht gespeichert")
        self.wait_until(
            lambda: "4" in gates.inner_text(),
            timeout=20000,
            message="Der neue globale Wert ist nicht sichtbar: "
                    + repr(gates.inner_text()))

        gates.locator("select[data-nv-field='gates-key']").select_option(
            "repair_rounds")
        gates.locator("input[data-nv-field='gates-value']").fill("3")
        gates.locator("input[data-nv-field='gates-project']").fill("proj")
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
            "projekt",
            project_view["gates"]["repair_rounds"].get("origin"),
            "Der Projektwert hat nicht die Herkunft projekt")

        gates.locator("select[data-nv-field='gates-key']").select_option(
            "repair_rounds")
        gates.locator("input[data-nv-field='gates-value']").fill("")
        gates.locator("input[data-nv-field='gates-project']").fill("proj")
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
    def test_env_doctor_paths_fritz_emulator_and_server(self):
        """Vorbedingung: kein Android-Projekt, Fritz-Helfer und -Konfiguration
        vorhanden, gesunder opencode-Server auf dem Attrappen-Port.

        Aktion: Feature ``env`` einschalten; Doctor, Pfade, Fritz-Automatik
        an/aus, Reconnect und Emulator-Start prüfen.

        Erwartung: Doctor-Zeilen mit ok und Fehlschlag samt Hinweis; Pfade aus
        ``/api/paths``; Automatik wird in ``<state>/fritz.json`` gespeichert;
        der Reconnect liefert die neue IP; der Emulator-Start meldet ohne
        Android-Projekt einen Fehler mit „Android“; der Serverstatus ist
        sichtbar, Start/Stop-Knöpfe existieren.
        """
        self.boot()
        self.enable_features("env")
        env = self.section("env")
        env.locator("[data-nv-doctor-row]").first.wait_for(
            state="visible", timeout=25000)
        rows = env.locator("[data-nv-doctor-row]")
        states = [rows.nth(index).get_attribute("data-nv-ok")
                  for index in range(rows.count())]
        self.assertIn("true", states,
                      "Keine bestandene Doctor-Prüfung sichtbar")
        self.assertIn("false", states,
                      "Keine fehlgeschlagene Doctor-Prüfung sichtbar")
        failed = next(rows.nth(index) for index in range(rows.count())
                      if rows.nth(index).get_attribute("data-nv-ok")
                      == "false")
        self.assertRegex(failed.inner_text(), r"(?i)distrobox|android|hinweis"
                         r"|install|fehlt|missing",
                         "Die fehlgeschlagene Doctor-Zeile zeigt keinen "
                         "Hinweis: " + failed.inner_text())

        paths = env.locator("[data-nv-paths]")
        paths_text = paths.inner_text()
        self.assertIn(str(self.state_dir), paths_text,
                      "Der aufgelöste Zustandsordner fehlt in den Pfaden")
        self.assertIn(str(self.log_dir), paths_text,
                      "Der aufgelöste Laufzeitordner fehlt in den Pfaden")

        env.locator("[data-nv-action='fritz-automation-on']").click()
        self.wait_until(
            lambda: self.json_file(
                self.state_dir / "fritz.json").get("automation") is True,
            timeout=20000,
            message="Die Fritz-Automatik wurde nicht eingeschaltet")
        env.locator("[data-nv-action='fritz-automation-off']").click()
        self.wait_until(
            lambda: self.json_file(
                self.state_dir / "fritz.json").get("automation") is False,
            timeout=20000,
            message="Die Fritz-Automatik wurde nicht ausgeschaltet")

        env.locator("[data-nv-action='fritz-reconnect']").click()
        self.page.wait_for_timeout(300)
        self.click_confirm_if_shown(env)
        result = env.locator("[data-nv-fritz-result]")
        result.wait_for(state="visible", timeout=30000)
        self.wait_until(
            lambda: "203.0.113.9" in result.inner_text(),
            timeout=30000,
            message="Der Reconnect zeigt die neue IP nicht: "
                    + repr(result.inner_text() if result.count() else ""))

        env.locator("[data-nv-action='emu-start']").click()
        error = env.locator("[data-nv-form-error], [data-nv-emu-result]")
        error.first.wait_for(state="visible", timeout=20000)
        self.assertIn("Android", env.inner_text(),
                      "Der Emulator-Start meldet keinen Android-Fehler")

        status = env.locator("[data-nv-server-status]")
        status.wait_for(state="visible", timeout=20000)
        self.assertRegex(status.inner_text(),
                         r"(?i)läuft|up|bereit|online|erreichbar",
                         "Der opencode-Serverstatus ist nicht sichtbar: "
                         + status.inner_text())
        self.assertEqual(
            1, env.locator("[data-nv-action='server-start']").count(),
            "Der Startknopf des opencode-Servers fehlt")
        self.assertEqual(
            1, env.locator("[data-nv-action='server-stop']").count(),
            "Der Stopknopf des opencode-Servers fehlt")
        self.assertTrue(self.api_json("/api/server").get("up"),
                        "Die Server-Attrappe gilt nicht als gesund")
        self.assert_no_page_errors()


class RunsTest(AP22AdvancedBrowserTest):
    def test_runs_prune_marks_missing_session_ended(self):
        """Vorbedingung: ``<runtime>/runs.json`` enthält vor dem Serverstart
        einen laufenden Eintrag mit sicher fehlender tmux-Sitzung.

        Aktion: Feature ``runs`` einschalten und „prune“ ausführen.
        Erwartung: Der Eintrag ist in der Registerliste sichtbar; nach dem
        Prune meldet ``GET /api/runs`` den Zustand ``ended`` (die Sitzung
        fehlt) und die UI zeigt die Bereinigung an.
        """
        self.boot()
        self.enable_features("runs")
        runs = self.section("runs")
        entry = runs.locator("[data-nv-run='run-ap22-missing']")
        entry.wait_for(state="visible", timeout=20000)
        self.assertIn("run-ap22-missing", entry.inner_text())

        runs.locator("[data-nv-action='runs-prune']").click()

        def pruned():
            data = self.api_json("/api/runs")
            for record in data.get("records", []):
                if record.get("id") == "run-ap22-missing":
                    return record.get("state") == "ended"
            return False

        self.wait_until(pruned, timeout=30000,
                        message="Prune hat den verwaisten Eintrag nicht "
                                "beendet: " + repr(self.api_json("/api/runs")))
        self.assertRegex(runs.inner_text(), r"(?i)ended|beendet|bereinigt",
                         "Die UI zeigt den bereinigten Zustand nicht")
        self.assert_no_page_errors()


class ParityTest(AP22AdvancedBrowserTest):
    def test_every_feature_toggle_and_project_sections(self):
        """Vorbedingung: frischer Browserkontext, Projekt ``proj``.

        Aktion: Einstellungen öffnen; für jede Feature-ID den Schalter
        prüfen; die fünf Projektfunktionen einschalten und
        ``#/project/proj/settings`` öffnen.

        Erwartung: Alle 14 Schalter existieren; die Projektbereiche github,
        writeaccess, sandbox, agentsfile und priority erscheinen mit einer
        Überschrift und mindestens einem Bedienelement (priority alternativ
        als Arbeitsbereich ``[data-nv-priority]``, siehe Moduldocstring).
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
                    section = self.page.locator(
                        "[data-nv-psection='priority'], [data-nv-priority]")
                else:
                    section = self.page.locator(
                        f"[data-nv-psection='{feature}']")
                self.assertEqual(
                    1, section.count(),
                    f"Der Projektbereich {feature!r} fehlt bei "
                    "eingeschaltetem Feature")
                self.assertTrue(
                    section.locator("h2, h3, h4").count() >= 1,
                    f"Der Projektbereich {feature!r} hat keine Überschrift")
                self.assertTrue(
                    section.locator("input, select, textarea, button").count()
                    >= 1,
                    f"Der Projektbereich {feature!r} hat kein Bedienelement")
        self.assert_no_page_errors()


if __name__ == "__main__":
    unittest.main()
