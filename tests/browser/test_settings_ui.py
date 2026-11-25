"""Einstellungen: Shell, Profile, Modelle, MCP, Limits, Gates, Harness, Sicherheit und Sprache.

Aufruf: python3 -m unittest tests.browser.test_settings_ui -v
"""


# ===========================================================================
# Browserabnahme, Meilenstein C: Settings-Sektionen und Paritätsrundgang
# ===========================================================================

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

    def await_highlight(self, button, message):
        """Wartet auf die lokale Neuzeichnung nach einer Modusänderung.

        ``GET /api/limits`` kann den neuen Modus bereits bestätigen, während
        die Oberfläche die Karte noch nicht neu gezeichnet hat. Geprüft wird
        unverändert dieselbe Hervorhebung (``aria-pressed`` oder
        ``nv-primary``); nur der Zeitpunkt wird deterministisch.
        """
        self.wait_until(
            lambda: button.get_attribute("aria-pressed") == "true"
            or "nv-primary" in (button.get_attribute("class") or ""),
            timeout=20, message=message)

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
    def test_model_row_opens_editview_with_separated_facts_and_assessments(self):
        """GH-57 (models): Modellzeile öffnet die Edit-View statt Detailzeile.

        Vorbedingung: Testkatalog in ``<install>/models.json``, Feature
        ``models`` an. Aktion: ``details[data-nv-models]`` über ``summary``
        aufklappen, Modellzeile
        ``tr[data-nv-model='opencode/vibe-modell']`` anklicken.
        Erwartung: ``aside[data-nv-editview]`` zeigt
        ``[data-nv-model-detail]`` mit Anbieter/Preis/Status, getrennten
        Blöcken „Fakten“ (200.000 Token, Quelle ``models.dev API``) und
        „Einschätzungen“ (``schnell``, Quelle ``Altkatalog``) sowie der
        Preisquelle; in der Sektion existiert keine eingebettete Detailzeile
        ``tr[data-nv-model-detail]``. Kein JS-Fehler.

        Ersetzt den F34-Stand (eingebettete ``td > div``-Detailzeile in der
        Sektion), der dem GH-57-Vertrag widerspricht; die Fachprüfung
        (Fakten/Einschätzungen getrennt, Preisquelle) bleibt vollständig.
        """
        self.boot()
        self.enable_features("models")
        models = self.section("models")

        details = models.locator("details[data-nv-models]")
        details.wait_for(state="attached", timeout=20000)
        if not details.evaluate("node => node.open"):
            details.locator("summary").click()
            self.wait_until(
                lambda: details.evaluate("node => node.open"),
                timeout=10000,
                message="details[data-nv-models] ließ sich nicht aufklappen")

        row = models.locator("tr[data-nv-model='opencode/vibe-modell']")
        row.wait_for(state="visible", timeout=30000)
        row.click()

        aside = self.page.locator("aside[data-nv-editview]")
        aside.wait_for(state="visible", timeout=20000)
        detail = aside.locator("[data-nv-model-detail]")
        detail.wait_for(state="visible", timeout=20000)
        detail_text = detail.inner_text() or ""
        for label in ("Anbieter", "Preis", "Status", "Fakten",
                      "Einschätzungen", "Preisquelle"):
            with self.subTest(label=label):
                self.assertIn(
                    label, detail_text,
                    "Die Modelldetail-Ansicht nennt %r nicht: %r"
                    % (label, detail_text))

        blocks = detail.evaluate(
            """node => {
                 const result = {};
                 Array.from(node.children).forEach(child => {
                   if (child.tagName !== 'DIV') return;
                   const label = child.querySelector(':scope > b');
                   if (label) result[label.textContent.trim()] = child.innerText;
                 });
                 return result;
               }""")
        facts_text = blocks.get("Fakten", "")
        assessments_text = blocks.get("Einschätzungen", "")
        self.assertIn(
            "200.000 Token", facts_text,
            "Der Faktenblock nennt den Kontextwert nicht: %r" % facts_text)
        self.assertIn(
            "models.dev API", facts_text,
            "Der Faktenblock nennt die Faktenquelle nicht: %r" % facts_text)
        self.assertIn(
            "schnell", assessments_text,
            "Der Einschätzungsblock nennt die Einschätzung nicht: %r"
            % assessments_text)
        self.assertIn(
            "Altkatalog", assessments_text,
            "Der Einschätzungsblock nennt die Einschätzungsquelle nicht: %r"
            % assessments_text)
        self.assertNotIn(
            "Altkatalog", facts_text,
            "Fakten und Einschätzungen sind vermischt: %r" % facts_text)
        self.assertNotIn(
            "200.000 Token", assessments_text,
            "Fakten und Einschätzungen sind vermischt: %r" % assessments_text)
        self.assertRegex(
            detail_text, r"Preisquelle:\s*models\.dev API",
            "Die Preisquelle fehlt in der Detailansicht: %r" % detail_text)
        self.assertEqual(
            0, models.locator("tr[data-nv-model-detail]").count(),
            "Die Modelldetails liegen weiterhin als eingebettete Zeile")
        self.page.keyboard.press("Escape")
        self.assert_no_page_errors()


class ProfilesTest(AP22AdvancedBrowserTest):
    def test_profiles_select_preview_then_apply(self):
        """GH-57 (profiles): Auswahl über select[data-nv-profiles-select] und
        [data-nv-profile-selected]-Anzeige statt article-Karten (F34-Stand
        widerspricht dem Vertrag docs/features/GH-57.md); Anwenden zeigt die
        NV.context-Vorschau und schreibt nach Bestätigen ``aktiv`` und das
        Agentenmodell. Altbestand (kostenlos/guenstig/stark) bleibt als
        nutzerdefinierte Profile auswählbar."""
        tester = self.home / ".config" / "opencode" / "agents" / "tester.md"
        tester.write_text(
            "---\ndescription: Testet\nmode: subagent\n"
            "model: opencode/schnell-modell\n---\n\nTeste.\n",
            encoding="utf-8")
        self.boot()
        self.enable_features("profiles")
        profiles = self.section("profiles")
        select = profiles.locator("select[data-nv-profiles-select]")
        select.wait_for(state="visible", timeout=25000)
        values = select.evaluate(
            "node => Array.from(node.options).map(o => o.value)")
        for name in ("kostenlos", "guenstig", "stark"):
            self.assertIn(name, values, f"Profil {name!r} fehlt in der Auswahl")
        select.select_option("kostenlos")
        display = profiles.locator("[data-nv-profile-selected]")
        self.wait_until(
            lambda: display.count() >= 1
            and "kostenlos" in (display.first.inner_text() or ""),
            timeout=20000, message="Die Auswahl zeigt das Profil nicht an")
        self.assertGreaterEqual(
            profiles.locator("[data-nv-profile-role]").count(), 1,
            "Dem Profil fehlen die Rollen-Comboboxen")
        self.assertEqual(
            "kostenlos",
            self.json_file(self.state_dir / "profiles.json").get("aktiv"),
            "Die Auswahl hat das aktive Profil verändert")
        profiles.locator("[data-nv-action='profile-apply']").click()
        context = self.page.locator("aside[data-nv-context]")
        context.wait_for(state="visible", timeout=20000)
        confirm = context.locator(
            "[data-nv-context-foot] button", has_text="Bestätigen")
        confirm.wait_for(state="visible", timeout=20000)
        confirm.click()
        self.wait_until(
            lambda: "opencode/vibe-modell" in tester.read_text(
                encoding="utf-8"),
            timeout=30, message="Das Profil hat das Agentenmodell nicht "
                                "angewendet")
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


class LimitsModeTest(AP22AdvancedBrowserTest):
    def test_limits_mode_switches_between_continue_and_stop(self):
        """GH-57 (limits): ein Schalter statt Optionskarten.

        Vorbedingung: Modus ``stop``, Feature ``limits`` aus.
        Aktion: Feature einschalten; Schalter
        ``input[type=checkbox][data-nv-limits-mode]`` umlegen, zurücklegen.
        Erwartung: Sektion ``section[data-nv-ssection='limits']``; genau ein
        Schalter in ``label.nv-switch-row``; Erklärung
        ``[data-nv-limits-help]`` nennt die Wirkung; aus = Stopp, an =
        Fortsetzen, jeweils bestätigt durch ``GET /api/limits``; keine
        Modus-Karten ``limits-continue``/``limits-stop``. Ersetzt den
        F34-Stand (Optionskarten), der dem GH-57-Vertrag widerspricht.
        """
        self.api_post("/api/limits", {"action": "stop"})
        self.boot()
        self.enable_features("limits")
        limits = self.section("limits")
        toggle = limits.locator(
            "input[type=checkbox][data-nv-limits-mode]")
        toggle.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            1, limits.locator(
                "input[type=checkbox][data-nv-limits-mode]").count(),
            "Es gibt nicht genau einen Limits-Schalter")
        self.assertEqual(
            0, limits.locator(
                "button[data-nv-action='limits-continue'],"
                " button[data-nv-action='limits-stop']").count(),
            "Die alten Modus-Karten existieren weiterhin")
        help_box = limits.locator("[data-nv-limits-help]")
        help_box.wait_for(state="visible", timeout=20000)
        self.assertRegex(
            (help_box.inner_text() or "") + " " + (limits.inner_text() or ""),
            r"(?i)new run|neue läuf|fortsetz|stopp",
            "Die Limits-Erklärung enthält keine Wirkungsbeschreibung: "
            + repr(limits.inner_text()))
        self.assertFalse(
            toggle.is_checked(),
            "Der Schalter spiegelt den Modus stop nicht (aus = Stopp)")
        self.assertEqual(
            "label.nv-switch-row",
            toggle.evaluate(
                "node => { const l = node.closest('label');"
                " return l ? l.className : ''; }"),
            "Der Schalter liegt nicht in label.nv-switch-row")

        toggle.check()
        self.wait_until(
            lambda: self.api_json("/api/limits").get("mode") == "continue",
            timeout=30,
            message="Der Modus continue wird nicht bestätigt: "
                    + repr(self.api_json("/api/limits")))
        self.assertTrue(toggle.is_checked(),
                         "Der Schalter zeigt den Modus continue nicht")

        toggle.uncheck()
        self.wait_until(
            lambda: self.api_json("/api/limits").get("mode") == "stop",
            timeout=30,
            message="Der Modus stop wird nicht bestätigt: "
                    + repr(self.api_json("/api/limits")))
        self.assertFalse(toggle.is_checked(),
                          "Der Schalter zeigt den Modus stop nicht")
        self.assert_no_page_errors()


class GatesOverrideTest(AP22AdvancedBrowserTest):
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

        # Projektwert leeren: Rückfall auf Standard 2. (Das Leeren wird
        # wiederholt, bis es steht: die Neuzeichnung nach dem Speichern kann
        # das Feld noch ersetzen.)
        override_field.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: (override_field.fill(""),
                     override_field.input_value() == "")[1],
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
                # Die Schalterliste wird asynchron geladen; erst danach
                # zählen (die Erwartung „genau einer“ bleibt unverändert).
                self.wait_until(
                    lambda: self.page.locator(
                        f"input[data-nv-feature='{feature}']").count() >= 1,
                    timeout=20,
                    message=f"Feature-Schalter {feature!r} fehlt")
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


# ===========================================================================
# Browserabnahme: Einstellungen (Erscheinung, Zugriff, Features)
# ===========================================================================

import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402


# Echte Feature-Schalter (Vertrag F34.md WP4, ``NV_SETTINGS_FEATURE_GROUPS`` in
# nova-settings.js): ``costs``/``env``/``runs`` sind entfallen — die Bereiche
# stehen nun unter ``#/evaluations`` (Tabs costs/runs/environment) und werden
# von tests/browser/test_f34_activity_evals_ui.py abgedeckt.
# Echte Sektions-IDs (Vertrag F34.md WP4; ``global-agents`` bestätigt aus
# nova-settings.js + grüner F34-Suite, nicht ``agentsfile``).
SECTIONS = (
    "global-agents", "appearance", "access", "features", "limits", "gates",
    "models", "profiles", "mcp", "harness",
)
AP22_PASSWORD = "ap22-ui-kennwort-42"


class _FakeOpenCodeHandler_ap22(BaseHTTPRequestHandler):
    """opencode-Attrappe: antwortet leer, startet keine Modelle."""

    def log_message(self, *args):
        return

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send_json(200, {"data": []})


class AP22SettingsBrowserTest(unittest.TestCase):
    """Dashboard, Projekt, Browser, opencode-Attrappe, isolierter Zustand."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True)
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir(parents=True, exist_ok=True)
        password = cls.log_dir / "opencode.password"
        password.write_text("geheim-AP22-settings", encoding="utf-8")
        password.chmod(0o600)
        cls.port = free_port()
        cls.oc_port = free_port()
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), _FakeOpenCodeHandler_ap22)
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
            "VIBE_RUNTIME": str(cls.log_dir),
            "HOME": str(cls.root / "home"),
            "TMPDIR": str(cls.root / "tmp"),
            "TMUX_TMPDIR": str(cls.tmux_dir),
            "VIBE_CONFIG_FILE": str(
                cls.root / "home" / ".config" / "vibe" / "config.json"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        cls.env = env
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=cls.server_log, stderr=subprocess.STDOUT, text=True)
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
    def tearDownClass(cls):
        try:
            cls.browser.close()
            cls.playwright.stop()
        finally:
            try:
                cls._fake_http.shutdown()
                cls._fake_http.server_close()
                cls._fake_thread.join(timeout=5)
            except Exception:
                pass
            if cls.proc.poll() is None:
                cls.proc.terminate()
                try:
                    cls.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls.proc.kill()
                    cls.proc.wait()
            cls.server_log.close()
            cls.tmp.cleanup()

    def setUp(self):
        # Unabhängige Vorbedingung: Sprache englisch, kein Kennwort gesetzt.
        self.api_post("/api/language", {"language": "en"})
        self.api_post("/api/security", {"action": "password", "clear": True})
        self.page_errors = []
        self.context = self.browser.new_context(
            viewport={"width": 1400, "height": 900})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))

    def tearDown(self):
        self.page.close()
        self.context.close()

    # ---------- Helfer ----------

    def wait_until(self, predicate, timeout=20,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def api_post(self, path, payload, token=None):
        """POST direkt über HTTP mit Instanz-Token (Test-Vorbedingung)."""
        body = json.dumps(payload).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("POST", path, body=body, headers={
                "Host": f"127.0.0.1:{self.port}",
                "X-Token": token or self.token,
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{self.port}",
                "Sec-Fetch-Site": "same-origin"})
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def api_get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("GET", path, headers={
                "Host": f"127.0.0.1:{self.port}",
                "X-Token": self.token})
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def api_json(self, path):
        status, body = self.api_get(path)
        self.assertEqual(200, status, body)
        return json.loads(body)

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_settings(self):
        self.page.locator("nav[data-nv-navs] [data-nv-nav='settings']").click()
        self.page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=20000)

    def ui_json_path(self):
        return self.state_dir / "ui.json"

    def ui_json(self):
        path = self.ui_json_path()
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def visible_error_text(self):
        parts = []
        for selector in ("#nv-toasts", "[data-nv-form-error]"):
            nodes = self.page.locator(selector)
            for index in range(nodes.count()):
                node = nodes.nth(index)
                if node.is_visible():
                    parts.append((node.inner_text() or "").strip())
        access = self.page.locator("[data-nv-ssection='access']")
        if access.count() and access.is_visible():
            text = access.inner_text() or ""
            for word in ("ungültig", "invalid", "Fehler", "error"):
                if word in text:
                    parts.append(text)
                    break
        return "\n".join(parts)

    def confirmation_visible(self):
        toasts = self.page.locator("#nv-toasts")
        if toasts.count() and toasts.is_visible() and (
                toasts.inner_text() or "").strip():
            return True
        access = self.page.locator("[data-nv-ssection='access']")
        if access.count() and access.is_visible():
            text = (access.inner_text() or "").lower()
            return any(word in text for word in
                       ("gespeichert", "saved", "gesetzt", "set", "success"))
        return False

    def login(self, page, secret):
        page.locator("[data-nv-login] input[data-nv-login-input]").fill(secret)
        page.locator("[data-nv-login] button[data-nv-login-submit]").click()

    def assert_no_page_errors(self):
        self.assertEqual(
            [], self.page_errors, "Die Oberfläche erzeugte JavaScript-Fehler")


class SettingsTest(AP22SettingsBrowserTest):
    # ---------- Sektionen und Erscheinung ----------

    def test_sections_shell_and_classic_link_exist(self):
        """Vorbedingung: angemeldet. Aktion: Einstellungen öffnen.

        Erwartung: die Sektionen ``global-agents``, ``appearance``,
        ``access``, ``features``, ``limits``, ``gates``, ``models``,
        ``profiles``, ``mcp``, ``harness`` existieren und sind sichtbar; die
        Sektionen ``language`` (Sprache steckt in ``appearance``) und
        ``advanced`` (entfallen) existieren nicht; der Klassisch-Link
        ``a[data-nv-classic-link]`` zeigt auf ``/classic``.

        Vertragsableitung: Der Settings-View rendert asynchron — die Helfer
        warten auf die Sektionen (``wait_for``), nicht nur auf die View.
        """
        self.boot()
        self.open_settings()
        for section in SECTIONS:
            with self.subTest(section=section):
                self.page.locator(
                    f"[data-nv-ssection='{section}']").wait_for(
                        state="visible", timeout=15000)
        for section in ("language", "advanced"):
            with self.subTest(absent=section):
                self.assertEqual(
                    0, self.page.locator(
                        f"[data-nv-ssection='{section}']").count(),
                    f"Die Sektion data-nv-ssection={section!r} existiert "
                    "nach F34 nicht mehr")
        self.page.locator("a[data-nv-classic-link]").wait_for(
            state="visible", timeout=15000)
        link = self.page.locator("a[data-nv-classic-link]")
        self.assertEqual(1, link.count(),
                         "Der Klassisch-Link a[data-nv-classic-link] fehlt")
        self.assertTrue(
            (link.get_attribute("href") or "").endswith("/classic"),
            "Der Klassisch-Link zeigt nicht auf /classic: "
            + repr(link.get_attribute("href")))

    def test_theme_select_offers_light_dark_auto(self):
        """Vorbedingung: Einstellungen offen. Aktion: dunkel, dann auto wählen.

        Erwartung: Optionen ``light``/``dark``/``auto``; dunkel setzt
        ``data-theme="dark"``; auto löst auf ``light`` oder ``dark`` auf
        (der Shell-Vertrag kennt nur diese beiden Attributwerte).
        """
        self.boot()
        self.open_settings()
        select = self.page.locator("[data-nv-theme-select]")
        select.wait_for(state="visible", timeout=15000)
        values = select.evaluate(
            "node => Array.from(node.options).map(o => o.value)")
        self.assertEqual(
            ["light", "dark", "auto"], values,
            "Der Theme-Select bietet nicht light/dark/auto: " + repr(values))

        select.select_option("dark")
        self.wait_until(
            lambda: self.page.evaluate(
                "() => document.documentElement.getAttribute('data-theme')")
            == "dark",
            timeout=10,
            message="Die Wahl 'dark' setzte data-theme nicht")

        select.select_option("auto")
        self.wait_until(
            lambda: self.page.evaluate(
                "() => document.documentElement.getAttribute('data-theme')")
            in ("light", "dark"),
            timeout=10,
            message="Die Wahl 'auto' löste kein light/dark auf")

    def test_animations_switch_syncs_with_html_attribute(self):
        """Vorbedingung: Einstellungen offen. Aktion: Schalter aus und ein.

        Erwartung: ``input[data-nv-anim-toggle]`` schaltet
        ``data-animations`` auf ``off`` und zurück auf ``on``.
        """
        self.boot()
        self.open_settings()
        toggle = self.page.locator("input[data-nv-anim-toggle]")
        toggle.wait_for(state="visible", timeout=15000)
        self.assertEqual(
            "on",
            self.page.evaluate(
                "() => document.documentElement.getAttribute('data-animations')"),
            "Der Animations-Standard ist nicht on")

        toggle.uncheck()
        self.wait_until(
            lambda: self.page.evaluate(
                "() => document.documentElement.getAttribute('data-animations')")
            == "off",
            timeout=10,
            message="Der Schalter setzte data-animations nicht auf off")
        toggle.check()
        self.wait_until(
            lambda: self.page.evaluate(
                "() => document.documentElement.getAttribute('data-animations')")
            == "on",
            timeout=10,
            message="Der Schalter setzte data-animations nicht zurück auf on")

    def test_language_select_options_match_contract(self):
        """Vorbedingung: Einstellungen offen. Aktion: Sprachumschalter lesen.

        Erwartung: genau ``English`` (``en``) und ``Deutsch`` (``de``); der
        Wert entspricht ``I18N.current()``.
        """
        self.boot()
        self.open_settings()
        select = self.page.locator("select[aria-label='Language']")
        self.assertEqual(
            1, select.count(),
            "Es gibt nicht genau einen Sprachumschalter")
        options = select.evaluate(
            "node => Array.from(node.options).map(o => [o.value, "
            "o.textContent.trim()])")
        self.assertEqual(
            [["en", "English"], ["de", "Deutsch"]], options,
            "Der Sprachumschalter bietet nicht genau English/Deutsch: "
            + repr(options))
        current = self.page.evaluate(
            """() => {
              const api = window.VIBE_I18N || window.I18N;
              return api && typeof api.current === 'function'
                ? api.current() : null;
            }""")
        self.assertEqual(current, select.input_value(),
                         "Der Umschalter steht nicht auf I18N.current()")

    # ---------- Zugriff ----------

    def test_password_set_login_and_clear(self):
        """Vorbedingung: angemeldet, kein Kennwort. Aktion: Kennwort setzen,
        frischer Kontext (falsch/richtig), Kennwort löschen.

        Erwartung: Bestätigung sichtbar; das falsche Kennwort bleibt auf der
        Login-Karte, das richtige öffnet die Projektliste; nach dem Löschen
        verlangt ein frischer Kontext wieder Token (Kennwort wird abgelehnt).
        """
        self.boot()
        self.open_settings()
        self.page.locator("input[data-nv-field='password']").fill(AP22_PASSWORD)
        self.page.locator("input[data-nv-field='password-repeat']").fill(AP22_PASSWORD)
        self.page.locator("[data-nv-action='password-set']").click()
        # GH-57: [data-nv-restart-note] ist dauerhaft sichtbar und enthält
        # „gespeichert“; confirmation_visible() würde daher sofort True
        # liefern. Beobachtet wird die echte Toast-Bestätigung.
        toasts = self.page.locator("#nv-toasts")
        self.wait_until(
            lambda: toasts.count() >= 1 and toasts.is_visible()
            and bool((toasts.inner_text() or "").strip()),
            timeout=20000,
            message="Nach dem Setzen des Kennworts erscheint keine Bestätigung")
        self.assertTrue(
            self.api_json("/api/security").get("password_set"),
            "Der Server meldet kein gesetztes Kennwort")

        context = self.browser.new_context(
            viewport={"width": 1200, "height": 900})
        try:
            fresh = context.new_page()
            fresh.goto(self.base + "/")
            fresh.locator("[data-nv-login]").wait_for(
                state="visible", timeout=20000)
            self.login(fresh, "falsches-kennwort-ap22")
            fresh.wait_for_timeout(1500)
            self.assertTrue(
                fresh.locator("[data-nv-login]").is_visible(),
                "Ein falsches Kennwort öffnete die Oberfläche")
            self.assertFalse(
                fresh.locator("[data-nv-projects]").is_visible(),
                "Die Projektliste ist nach falschem Kennwort sichtbar")

            self.login(fresh, AP22_PASSWORD)
            fresh.locator("[data-nv-projects]").wait_for(
                state="visible", timeout=20000)
        finally:
            context.close()

        self.page.locator("[data-nv-action='password-clear']").click()
        self.wait_until(
            lambda: not self.api_json("/api/security").get("password_set"),
            timeout=20000,
            message="Das Kennwort wurde nicht entfernt")

        context = self.browser.new_context(
            viewport={"width": 1200, "height": 900})
        try:
            fresh = context.new_page()
            fresh.goto(self.base + "/")
            fresh.locator("[data-nv-login]").wait_for(
                state="visible", timeout=20000)
            self.login(fresh, AP22_PASSWORD)
            fresh.wait_for_timeout(1500)
            self.assertTrue(
                fresh.locator("[data-nv-login]").is_visible(),
                "Das gelöschte Kennwort meldet noch an")
        finally:
            context.close()
        self.assert_no_page_errors()

    def test_port_validation_and_restart_note(self):
        """Vorbedingung: Einstellungen offen. Aktion: ungültigen, dann freien
        Port speichern.

        Erwartung: ``70000`` erzeugt einen sichtbaren Fehler und lässt
        ``ui.json`` byte-gleich; ein freier Port erzeugt den sichtbaren
        Neustart-Hinweis ``[data-nv-restart-note]`` und steht als ``ui_port``
        in ``ui.json``. Die Netzwerk-Felder liegen vertragsgemäß im
        standardmäßig zusammengeklappten ``details[data-nv-network-advanced]``
        und werden vor der Prüfung aufgeklappt.
        """
        self.boot()
        self.open_settings()
        # F33 WP5: Netzwerk ist standardmäßig zusammengeklappt (Vertrag).
        network = self.page.locator("details[data-nv-network-advanced]")
        network.wait_for(state="attached", timeout=15000)
        network.locator("summary").click()
        field = self.page.locator("input[data-nv-field='port']")
        field.wait_for(state="visible", timeout=15000)
        save = self.page.locator("[data-nv-action='security-save']")

        before = (self.ui_json_path().read_bytes()
                  if self.ui_json_path().exists() else None)
        field.fill("70000")
        save.click()
        self.wait_until(
            lambda: self.visible_error_text() != "",
            timeout=20000,
            message="Der ungültige Port erzeugte keinen sichtbaren Fehler")
        after = (self.ui_json_path().read_bytes()
                 if self.ui_json_path().exists() else None)
        self.assertEqual(before, after,
                         "Der ungültige Port veränderte ui.json")

        free = free_port()
        field.fill(str(free))
        save.click()
        self.page.locator("[data-nv-restart-note]").wait_for(
            state="visible", timeout=20000)
        # GH-57: Der Hinweis nennt die Neustart-Befristung ohne den
        # technischen ui.json-Satz (Ticket: Satz ersetzen).
        note_text = (self.page.locator("[data-nv-restart-note]")
                     .inner_text() or "")
        self.assertNotIn(
            "ui.json", note_text,
            "Der Neustart-Hinweis verwendet weiterhin den technischen "
            "ui.json-Satz: " + repr(note_text))
        # GH-57: Bei geplanten, noch nicht wirksamen Port-/Bind-Änderungen
        # zeigt die Oberfläche zusätzlich die Warn-Notiz (restart_required).
        self.page.locator("[data-nv-restart-pending]").wait_for(
            state="visible", timeout=20000)
        self.assertEqual(
            free, self.ui_json().get("ui_port"),
            "ui.json enthält den gespeicherten Port nicht")

        # Aufräumen: laufenden Port wieder eintragen (Neustart-Hinweis weg).
        self.api_post("/api/security", {"action": "save", "port": self.port})
        self.assert_no_page_errors()

    # ---------- Feature-Schalter und erweiterte Bereiche ----------

    def test_all_feature_toggles_exist_and_default_unchecked(self):
        """Vorbedingung: frisches Profil. Aktion: Einstellungen öffnen.

        Erwartung: je dokumentierter Feature-ID ein ``input[data-nv-feature]``,
        alle standardmäßig aus; die IDs ``costs``/``env``/``runs`` existieren
        als Schalter nicht mehr (Auswertungen unter ``#/evaluations``,
        abgedeckt in ``tests/browser/test_f34_activity_evals_ui.py``).
        """
        self.boot()
        self.open_settings()
        for feature in FEATURE_IDS:
            with self.subTest(feature=feature):
                toggle = self.page.locator(
                    f"input[data-nv-feature='{feature}']")
                # Vertragsableitung: Das Settings-View-Gerüst ist synchr.,
                # fillFeatures läuft asynchron nach — auf das Erscheinen
                # warten, nicht auf die View.
                toggle.wait_for(state="visible", timeout=20000)
                self.assertEqual(
                    1, toggle.count(),
                    f"Feature-Schalter data-nv-feature={feature!r} fehlt")
                self.assertFalse(
                    toggle.is_checked(),
                    f"Feature {feature!r} ist standardmäßig eingeschaltet")
        for feature in ("costs", "env", "runs"):
            with self.subTest(absent=feature):
                self.assertEqual(
                    0, self.page.locator(
                        f"input[data-nv-feature='{feature}']").count(),
                    f"Der Feature-Schalter {feature!r} existiert nach F34 "
                    "nicht mehr")

    def test_advanced_limits_appears_and_switches_mode(self):
        """GH-57: Vorbedingung Modus ``stop``, Feature ``limits`` aus. Aktion:
        Feature einschalten (lokales Erscheinen der Sektion), Schalter
        ``input[type=checkbox][data-nv-limits-mode]`` umlegen, zurücklegen.

        Erwartung: Die Sektion erscheint nach dem Einschalten lokal; genau ein
        Schalter in ``label.nv-switch-row``; die Erklärung
        ``[data-nv-limits-help]`` nennt die Wirkung; der Schalter spiegelt
        ``GET /api/limits`` und wechselt ``continue``/``stop``. Das
        „kein Voll-Neurender“-Kriterium sichern ``test_gh57_settings_ui``
        und ``test_f34_settings_ui`` ab (diese Basisklasse besitzt keinen
        Render-Zähler). Ersetzt den F34-Stand (Modus-Karten
        limits-continue/limits-stop), der dem GH-57-Vertrag widerspricht.
        """
        self.api_post("/api/limits", {"action": "stop"})
        self.boot()
        self.open_settings()
        # GH-57: Sektionen gesperrter Features sind vollständig ausgeblendet;
        # das Einschalten lässt die Sektion lokal erscheinen.
        limits = self.page.locator("[data-nv-ssection='limits']")
        self.page.locator("input[data-nv-feature='limits']").wait_for(
            state="visible", timeout=15000)
        self.page.locator("input[data-nv-feature='limits']").check()
        limits.wait_for(state="visible", timeout=20000)

        toggle = limits.locator(
            "input[type=checkbox][data-nv-limits-mode]")
        toggle.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            0, self.page.locator(
                "button[data-nv-action='limits-continue'],"
                " button[data-nv-action='limits-stop']").count(),
            "Die alten Modus-Knöpfe existieren weiterhin")
        help_box = limits.locator("[data-nv-limits-help]")
        help_box.wait_for(state="visible", timeout=20000)
        self.assertRegex(
            (help_box.inner_text() or "") + " " + (limits.inner_text() or ""),
            r"(?i)new run|neue läuf|fortsetz|stopp",
            "Die Limits-Erklärung enthält keine Wirkungsbeschreibung: "
            + repr(limits.inner_text()))
        self.assertFalse(
            toggle.is_checked(),
            "Der Schalter spiegelt den Modus stop nicht (aus = Stopp)")
        self.assertEqual(
            "label.nv-switch-row",
            toggle.evaluate(
                "node => { const l = node.closest('label');"
                " return l ? l.className : ''; }"),
            "Der Schalter liegt nicht in label.nv-switch-row")

        toggle.check()
        self.wait_until(
            lambda: self.api_json("/api/limits").get("mode") == "continue",
            timeout=30,
            message="Der Moduswechsel auf continue wird nicht bestätigt: "
                    + repr(self.api_json("/api/limits")))
        self.assertTrue(toggle.is_checked(),
                         "Der Schalter zeigt den Modus continue nicht")
        toggle.uncheck()
        self.wait_until(
            lambda: self.api_json("/api/limits").get("mode") == "stop",
            timeout=30,
            message="Der Moduswechsel auf stop wird nicht bestätigt: "
                    + repr(self.api_json("/api/limits")))
        self.assertFalse(toggle.is_checked(),
                         "Der Schalter zeigt den Modus stop nicht")
        self.assert_no_page_errors()

    def test_advanced_gates_shows_keys_and_project_form(self):
        """Vorbedingung: Feature ``gates`` aus. Aktion: Schalter an; Wert
        setzen; Speichern.

        Erwartung: Sektion ``section[data-nv-ssection='gates']``; die
        Schrankenschlüssel aus ``GET /api/gates`` je Zeile
        ``tr[data-nv-gate]`` benannt mit ``small[data-nv-gate-help]``,
        ``[data-nv-gate-value]`` und ``span[data-nv-gate-origin]``;
        ``select[data-nv-gates-project]`` bietet ``global`` + Projekte,
        bietet kein Freitextfeld (``input[data-nv-gates-project]`` == 0);
        ``button[data-nv-action='gates-reset']`` vorhanden; nach dem
        Speichern bleibt ein vorher gesetztes DOM-Merkmal der Sektion
        erhalten (kein Voll-Neurender) und der Wert steht in
        ``GET /api/gates``.
        """
        self.boot()
        self.open_settings()
        gates_view = self.api_json("/api/gates")
        self.assertTrue(gates_view.get("ok"), gates_view)

        section = self.page.locator("[data-nv-ssection='gates']")
        section.wait_for(state="visible", timeout=15000)
        self.page.locator("input[data-nv-feature='gates']").wait_for(
            state="visible", timeout=15000)
        self.page.locator("input[data-nv-feature='gates']").check()

        table = section.locator("[data-nv-gates-table]")
        table.wait_for(state="visible", timeout=20000)
        for key in gates_view["gates"]:
            with self.subTest(gate=key):
                row = table.locator(f"tr[data-nv-gate='{key}']")
                self.assertEqual(
                    1, row.count(),
                    f"Die Zeile tr[data-nv-gate={key!r}] fehlt")
                help_text = row.locator(
                    "small[data-nv-gate-help]").inner_text()
                self.assertTrue(
                    (help_text or "").strip(),
                    f"Die Schranke {key!r} hat keine Erklärung")
                self.assertEqual(
                    1, row.locator("[data-nv-gate-value]").count(),
                    f"Die Schranke {key!r} hat kein Wert-Feld")
                # GH-57: Der Vertrag pinnt den Herkunfts-Hook ohne Element-Typ
                # vor (keine Schwächung — das Feld bleibt gefordert).
                self.assertEqual(
                    1, row.locator("[data-nv-gate-origin]").count(),
                    f"Die Schranke {key!r} hat kein Herkunfts-Badge")

        project_select = section.locator("select[data-nv-gates-project]")
        self.assertEqual(
            1, project_select.count(),
            "Die Projektauswahl data-nv-gates-project fehlt")
        options = project_select.evaluate(
            "node => Array.from(node.options).map(o => o.value)")
        self.assertIn("global", options,
                      "Der Gates-Filter bietet 'global' nicht an")
        self.assertGreaterEqual(
            len(options), 1, "Der Gates-Filter hat keine Projektauswahl")
        self.assertEqual(
            0, section.locator("input[data-nv-gates-project]").count(),
            "Der Gates-Projektfilter darf kein Freitextfeld sein")
        self.page.locator("[data-nv-action='gates-reset']").wait_for(
            state="visible", timeout=20000)

        # Global: Auf „global" schalten und auf das abgeschlossene Redraw
        # warten (der Wert im Eingabefeld entspricht dem globalen API-Wert).
        project_select.select_option("global")
        retries_row = section.locator("tr[data-nv-gate='retries']")
        retries_input = retries_row.locator("[data-nv-gate-value]")
        retries_input.wait_for(state="visible", timeout=20000)
        self.wait_until(
            lambda: retries_input.input_value()
            == str(self.api_json("/api/gates")["gates"]["retries"]["value"]),
            timeout=20,
            message="Das Gates-Redraw auf den globalen Kontext ist nicht abgeschlossen")

        # Speichern: Wert setzen, ein DOM-Merkmal setzen, Speichern,
        # API bestätigt — das Merkmal überlebt (kein Voll-Neurender).
        retries_input.fill("4")
        section.evaluate(
            "node => node.setAttribute('data-nv-ap22-no-rerender', '1')")
        save = section.locator("[data-nv-action='gates-save']")
        save.wait_for(state="visible", timeout=20000)
        save.click()
        self.wait_until(
            lambda: self.api_json("/api/gates")["gates"]["retries"]
            ["value"] == 4,
            timeout=30,
            message="Der globale Wert der Schranke retries wurde nicht "
                    "gespeichert: " + repr(self.api_json("/api/gates")))
        self.assertEqual(
            "1", section.get_attribute("data-nv-ap22-no-rerender"),
            "Nach gates-save wurde ein Voll-Neurender erwartet "
            "(das gesetzte DOM-Merkmal ist weg)")
        self.assert_no_page_errors()


class LogoutTest(AP22SettingsBrowserTest):
    def test_logout_shows_login_card_and_blocks_api(self):
        """Vorbedingung: angemeldet. Aktion: ``[data-nv-action="logout"]``.

        Erwartung: Die Login-Karte erscheint wieder; ``GET /api/projects``
        im Browser antwortet 403 (Session beendet).
        """
        self.boot()
        self.open_settings()
        self.page.locator("[data-nv-action='logout']").click()
        self.page.locator("[data-nv-login]").wait_for(
            state="visible", timeout=20000)
        status = self.page.evaluate(
            """async () => {
              const response = await fetch('/api/projects',
                {credentials: 'same-origin'});
              return response.status;
            }""")
        self.assertEqual(403, status,
                         "Nach dem Abmelden ist die API weiterhin erreichbar")


# ===========================================================================
# Browserabnahme: Anmeldung und Karte „Zugriffssicherheit“
# ===========================================================================

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

# Installierte Entwicklerabhängigkeit: Chromium nur lesend aus dem
# Nutzer-Cache (Muster tests/browser/test_ap7_settings_ui.py); niemals in
# einem Test heruntergeladen.
_BROWSERS_ap13 = Path.home() / ".cache" / "ms-playwright"
if _BROWSERS_ap13.is_dir():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_BROWSERS_ap13))

from playwright.sync_api import sync_playwright


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
)


class Ap13SecurityBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8"
        )
        (cls.project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.toolchain = cls.root / "_toolchain"
        cls.toolchain.mkdir()
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir()
        cls.state = cls.toolchain
        cls.port = free_port()
        env = os.environ.copy()
        for key in ISOLATED_ENV:
            env.pop(key, None)
        env.update(
            {
                "VIBE": str(cls.root),
                "VIBE_NO_CONTAINER": "1",
                "VIBE_UI_PORT": str(cls.port),
                "HOME": str(cls.home),
                "VIBE_STATE": str(cls.state),
                "VIBE_INSTALL": str(cls.toolchain),
                "VIBE_RUNTIME": str(cls.log_dir),
                "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode" / "agents"),
                "VIBE_CONFIG_FILE": str(
                    cls.home / ".config" / "vibe" / "config.json"
                ),
            }
        )
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        token_file = cls.log_dir / "web.token"
        deadline = time.time() + 25
        while time.time() < deadline:
            if token_file.exists():
                try:
                    with socket.create_connection(
                        ("127.0.0.1", cls.port), timeout=0.5
                    ):
                        break
                except OSError:
                    pass
            if cls.proc.poll() is not None:
                output = cls.proc.stdout.read() if cls.proc.stdout else ""
                raise AssertionError(
                    "vibe-web wurde vorzeitig beendet: " + output
                )
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill()
                cls.proc.wait()
        if cls.proc.stdout:
            cls.proc.stdout.close()
        cls.tmp.cleanup()

    def setUp(self):
        # Jeder Test beginnt in einem frischen Kontext ohne Session-Cookie
        # und ohne gespeicherte ui.json; die Vorbedingungen hängen nicht
        # von der (alphabetischen) Ausführungsreihenfolge der Tests ab.
        ui_json_path = self.state / "ui.json"
        if ui_json_path.exists():
            ui_json_path.unlink()
        self.context = self.browser.new_context(viewport={"width": 1400, "height": 1000})
        self.page = self.context.new_page()

    def tearDown(self):
        self.page.close()
        self.context.close()

    # ------------------------------------------------------------ Helfer
    def wait_until(self, predicate, timeout=10, message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail(message)

    def login_card(self, page=None):
        """Die Anmeldekarte: Behälter mit Eingabe plus Knopf „Anmelden“."""
        page = page or self.page
        button = page.get_by_role(
            "button", name=re.compile(r"anmelden|sign in|log in", re.I))
        button.wait_for()
        card = page.locator("div.card").filter(has=button)
        card.wait_for()
        self.assertTrue(
            card.locator("input").count() >= 1, "Anmeldekarte ohne Eingabefeld"
        )
        return card

    def login(self, secret, page=None):
        page = page or self.page
        card = self.login_card(page)
        card.locator("input").first.fill(secret)
        card.get_by_role(
            "button", name=re.compile(r"anmelden|sign in|log in", re.I)).first.click()
        self.wait_until(
            lambda: self.project_list_visible(page),
            timeout=10,
            message="Nach dem Anmelden erschien keine Projektliste",
        )

    def project_list_visible(self, page=None):
        return (page or self.page).locator("tr.row").first.is_visible()

    def open_security_card(self):
        self.page.get_by_text("Access security", exact=False).first.click()
        # Warten auf das konkrete Karten-Merkmal (Review-Minor 6): Der
        # Nav-Knopf trägt denselben Text wie die Karte und wäre schon vor
        # dem Karten-Render sichtbar; div#security existiert erst mit der
        # gerenderten Karte.
        self.wait_until(
            lambda: self.page.locator("div#security").count() > 0,
            message="Karte „Zugriffssicherheit“ (div#security) nicht gefunden",
        )

    def security_card(self):
        return self.page.locator(
            "xpath=//*[contains(text(),'Zugriffssicherheit') or "
            "contains(text(),'Access security')]"
            "/ancestor-or-self::*[self::section or self::details or "
            "self::div][1]"
        ).first

    def ui_json(self):
        path = self.state / "ui.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------ Testfälle
    def test_anmeldekarte_ohne_session(self):
        """AK Anmeldekarte. Vorbedingung: Kontext ohne Cookies.

        Aktion: Dashboard öffnen. Erwartet: Eingabe + Knopf „Anmelden“
        sichtbar, Projektliste nicht sichtbar.
        """
        self.page.goto(self.base + "/classic")

        self.login_card()
        self.assertFalse(
            self.project_list_visible(), "Projektliste ohne Anmeldung sichtbar"
        )

    def test_hash_wird_gegen_session_eingetauscht_und_geleert(self):
        """AK Token-Tausch. Vorbedingung: Kontext ohne Cookies.

        Aktion: ``/#t=<token>`` öffnen. Erwartet: Oberfläche sichtbar,
        location.hash leer, sessionStorage.t leer, kein Token in der URL.
        """
        self.page.goto(self.base + "/classic#t=" + self.token)

        self.wait_until(
            lambda: self.project_list_visible(),
            timeout=10,
            message="Nach dem Token-Eintausch erschien keine Projektliste",
        )
        self.assertEqual(
            self.page.evaluate("location.hash"), "", "Hash blieb stehen"
        )
        self.assertEqual(
            self.page.evaluate("sessionStorage.getItem('t') || ''"),
            "",
            "Token liegt weiter im sessionStorage",
        )
        self.assertNotIn("#t=", self.page.url)

        # Neu laden ohne Hash bleibt angemeldet (Session-Cookie).
        self.page.reload()
        self.wait_until(
            lambda: self.project_list_visible(),
            timeout=10,
            message="Nach dem Neuladen fiel die Session weg",
        )

    def test_zugriffssicherheit_karte_zeigt_werte(self):
        """AK Sicherheitskarte. Vorbedingung: angemeldet über ``#t=``.

        Aktion: Karte „Zugriffssicherheit“ öffnen. Erwartet: Karte nennt den
        laufenden Port, die Bind-Adresse 127.0.0.1 und den Passwortstatus
        (nicht gesetzt).
        """
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.wait_until(lambda: self.project_list_visible(), timeout=10)

        self.open_security_card()
        card_text = self.security_card().inner_text()
        self.assertIn(str(self.port), card_text, "Karte nennt den Port nicht")
        self.assertIn("127.0.0.1", card_text, "Karte nennt die Bind-Adresse nicht")
        self.assertTrue(
            re.search(r"passwort|password", card_text, re.I),
            "Karte zeigt keinen Passwortstatus",
        )

    def test_port_aendern_zeigt_neustart_hinweis_und_schreibt_ui_json(self):
        """AK Port ändern. Vorbedingung: angemeldet, kein ui.json.

        Aktion: Port auf einen anderen freien Port ändern, speichern.
        Erwartet: Hinweis „Neustart“ sichtbar; ui.json enthält ui_port.
        """
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.wait_until(lambda: self.project_list_visible(), timeout=10)
        self.assertIsNone(self.ui_json(), "Vorab existierte schon ui.json")

        self.open_security_card()
        card = self.security_card()
        port_field = card.locator("input").first
        new_port = free_port()
        port_field.fill(str(new_port))
        card.get_by_role(
            "button", name=re.compile(r"^\s*(Speichern|Save)\s*$", re.I)).first.click()
        self.wait_until(
            lambda: re.search(r"neustart|restart",
                             self.page.inner_text("body"), re.I),
            timeout=10,
            message="Kein Hinweis auf Neustart nach dem Speichern",
        )
        stored = self.ui_json()
        self.assertIsNotNone(stored, "ui.json wurde nicht geschrieben")
        self.assertEqual(stored.get("ui_port"), new_port)

    def test_passwort_setzen_und_anmeldung_mit_passwort(self):
        """AK Passwort. Vorbedingung: angemeldet.

        Aktion: Passwort in der Karte setzen; frischer Kontext ohne Cookies:
        Anmeldung mit dem Passwort; danach Cookies löschen (Abmeldung).
        Erwartet: Anmeldung gelingt; ohne Cookies erscheint die
        Anmeldekarte wieder.
        """
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.wait_until(lambda: self.project_list_visible(), timeout=10)

        self.open_security_card()
        card = self.security_card()
        password_field = card.locator("input[type=password]").first
        password_field.fill("ap13-ui-paswort-42")
        card.get_by_role(
            "button", name=re.compile(r"passwort|speichern|setzen|password|save|set", re.I)
        ).first.click()
        # Wirksamer Sync-Punkt (Review-Minor 5): Die frühere Bedingung
        # („ap13-ui-paswort-42 nicht in inner_text") konnte nie fehlschlagen,
        # weil Eingabewerte von type=password nie im Klartext-Text stehen.
        # Der Server bestätigt das Setzen mit der Toast-Meldung
        # „Kennwort gesetzt“; darauf warten wir.
        self.wait_until(
            lambda: re.search(
                r"kennwort gesetzt|password set",
                self.page.inner_text("body"), re.I),
            timeout=10,
            message="Keine Bestätigung „Kennwort gesetzt“ nach dem Speichern",
        )

        # Frischer Kontext ohne Cookies: Anmeldung mit dem Passwort.
        fresh = self.browser.new_context(viewport={"width": 1400, "height": 1000})
        fresh_page = fresh.new_page()
        try:
            fresh_page.goto(self.base + "/classic")
            self.login("ap13-ui-paswort-42", page=fresh_page)
        finally:
            fresh.close()

        # Abmeldung: ohne Cookies erscheint wieder die Anmeldekarte.
        self.context.clear_cookies()
        self.page.reload()
        self.wait_until(
            lambda: self.page.get_by_role(
                "button", name=re.compile(r"anmelden|sign in|log in", re.I)
            ).count() > 0,
            timeout=10,
            message="Ohne Cookies erschien keine Anmeldekarte",
        )

    def test_alle_clients_zulassen_entfernt_allowlist(self):
        """AK Alle Clients zulassen. Vorbedingung: angemeldet; ui.json enthält
        vorab eine Allowlist mit mindestens einem Eintrag (192.168.1.0/24);
        gesetzt über den authentifizierten POST im angemeldeten Browser-
        Kontext, weil der Server ui.json beim Start lädt und nach jeder
        security-Aktion neu liest (Schreibvorgang wird verifiziert). Aktion:
        Karte öffnen, Fakt-Zeile „Allowlist“ mit Eintrag prüfen, Knopf „Alle
        Clients zulassen“ anklicken, Inline-Bestätigung bestätigen. Erwartet:
        Dialog warnt vor Zugriff aller Clients im Netz; danach Fakt-Zeile
        „alle Clients erlaubt“, ui.json ohne Allowlist-Einträge,
        GET /api/security (gleiche Session) ohne Allowlist.
        """
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.wait_until(lambda: self.project_list_visible(), timeout=10)

        # Vorbedingung: Allowlist-Eintrag über die gleiche Session setzen
        # und den Schreibvorgang in ui.json prüfen.
        saved = self.page.evaluate(
            "async (tok) => { const r = await fetch('/api/security',"
            "{method:'POST',"
            "headers:{'X-Token':tok,'Content-Type':'application/json'},"
            "body: JSON.stringify({action:'save',"
            "allowlist:['192.168.1.0/24']})}); return await r.json(); }",
            self.token,
        )
        self.assertTrue(
            saved.get("ok"),
            "Vorbedingung: Allowlist-Eintrag nicht gesetzt: " + str(saved),
        )
        before = self.ui_json()
        self.assertIsNotNone(
            before, "Vorbedingung: ui.json wurde nicht geschrieben"
        )
        self.assertEqual(
            before.get("allowlist"), ["192.168.1.0/24"],
            "Vorbedingung: ui.json enthält den Allowlist-Eintrag nicht",
        )

        self.open_security_card()
        card = self.page.locator("#security")
        self.wait_until(
            lambda: card.count() == 1, timeout=5,
            message="Karte „Zugriffssicherheit“ (id=security) nicht gerendert",
        )
        self.wait_until(
            lambda: "192.168.1.0/24" in card.inner_text(), timeout=10,
            message="Fakt-Zeile „Allowlist“ zeigt den Eintrag nicht",
        )

        zulassen = card.get_by_role(
            "button", name=re.compile(r"alle clients zulassen|allow all clients", re.I)
        )
        self.wait_until(
            lambda: zulassen.count() > 0,
            message="Knopf „Alle Clients zulassen“ fehlt in der Sicherheitskarte",
        )
        zulassen.first.click()

        # askInline-Muster (siehe „Passwort entfernen“): ein Bestätigungs-
        # dialog mit Warnung, Bestätigungs- und Abbruchknopf.
        confirm = card.locator("span.confirm")
        self.wait_until(
            lambda: confirm.count() > 0, timeout=5,
            message="Kein Inline-Bestätigungsdialog nach dem Klick",
        )
        dialog_text = confirm.first.inner_text()
        self.assertRegex(
            dialog_text, re.compile("client", re.I),
            "Bestätigungsdialog warnt nicht vor dem Zugriff aller Clients",
        )
        self.assertRegex(
            dialog_text, re.compile(r"netz|network", re.I),
            "Bestätigungsdialog warnt nicht vor dem Zugriff im Netz",
        )
        yes = confirm.first.locator("button").filter(
            has_not_text=re.compile(r"abbrechen|cancel", re.I)
        )
        self.assertEqual(
            yes.count(), 1,
            "Bestätigungsdialog ohne genau einen Bestätigungsknopf",
        )
        yes.click()

        self.wait_until(
            lambda: re.search(r"alle Clients erlaubt|all clients allowed",
                             self.security_card().inner_text()),
            timeout=10,
            message="Fakt-Zeile zeigt nach dem Bestätigen nicht "
                    "„alle Clients erlaubt“",
        )
        self.assertNotIn(
            "192.168.1.0/24", self.security_card().inner_text(),
            "Fakt-Zeile zeigt weiterhin den Netz-Eintrag",
        )

        stored = self.ui_json()
        self.assertIsNotNone(
            stored,
            "ui.json fehlt nach dem Zulassen aller Clients",
        )
        self.assertEqual(
            stored.get("allowlist") or [], [],
            "ui.json enthält weiterhin Allowlist-Einträge",
        )

        view = self.page.evaluate(
            "async () => await (await fetch('/api/security')).json()"
        )
        self.assertTrue(
            view.get("ok"),
            "GET /api/security schlug in der gleichen Session fehl: "
            + str(view),
        )
        self.assertEqual(
            view.get("allowlist") or [], [],
            "GET /api/security meldet weiterhin Allowlist-Einträge",
        )

    def test_allowlist_platzhalter_sagt_leer_ist_unveraendert(self):
        """AK Allowlist-Platzhalter. Vorbedingung: angemeldet, Karte
        „Zugriffssicherheit“ offen. Aktion: Platzhalter der Eingabe mit
        aria-label „IP-Allowlist“ lesen. Erwartet: Er enthält
        „(leer = unverändert)“ und nicht „(leer = alle Clients)“.
        """
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.wait_until(lambda: self.project_list_visible(), timeout=10)
        self.open_security_card()

        card = self.page.locator("#security")
        self.wait_until(
            lambda: card.count() == 1, timeout=5,
            message="Karte „Zugriffssicherheit“ (id=security) nicht gerendert",
        )
        allow_input = card.locator('input[aria-label="IP-Allowlist"], '
                     'input[aria-label="IP allowlist"]')
        self.wait_until(
            lambda: allow_input.count() == 1, timeout=5,
            message="Allowlist-Eingabe (aria-label „IP-Allowlist“) nicht gefunden",
        )
        placeholder = allow_input.get_attribute("placeholder") or ""
        self.assertNotRegex(
            placeholder,
            r"(leer = alle Clients)|\(empty = all clients\)",
            "Platzhalter suggeriert weiterhin, ein leeres Feld setze die "
            "Allowlist auf alle Clients",
        )
        self.assertRegex(
            placeholder,
            r"(leer = unverändert)|\(empty = unchanged\)",
            "Platzhalter sagt nicht, dass ein leeres Feld die Allowlist "
            "unverändert lässt",
        )


# ===========================================================================
# Browserabnahme: Einstellungen (Sektionen, Akzent-Raster, Absences)
# ===========================================================================

import http.client
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402

RUNS_PY = REPO / "bin" / "vibe_runs.py"

PROJECT = "proj"
OTHER = "zweit"
QUESTION_PROJ = "qaaaaaaaaaaaa"
QUESTION_OTHER = "qbbbbbbbbbbbb"
QUESTION_TEXT_PROJ = "F33-FRAGE-PROJ: Soll die Kostenkarte blau werden?"
QUESTION_TEXT_OTHER = "F33-FRAGE-ZWEIT: Soll die Akzentfarbe grün werden?"
ACCENT_IDS = [
    "blue", "teal", "cyan", "green", "lime", "yellow",
    "amber", "orange", "red", "pink", "violet", "indigo",
]

GLOBAL_AGENTS_TEXT = "GLOBALE-REGEL-4711: gilt für alle Projekte.\n"

# Minimale opencode-Datenbank (Struktur wie tests/browser/test_costs_ui.py).


class F33SettingsBrowserTest(unittest.TestCase):
    """Dashboard, zwei Projekte, Fragen, Laufregister, Kosten-Datenbank."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.proj = cls.root / PROJECT
        cls.other = cls.root / OTHER
        for project in (cls.proj, cls.other):
            (project / ".vibe").mkdir(parents=True)
            (project / ".vibe" / "project.env").write_text(
                "TYPE=generic\n", encoding="utf-8")
            (project / "FEEDBACK.md").write_text(
                "# FEEDBACK\n\n- [ ] F1 Erster Punkt\n"
                "  Beschreibung: Testpunkt\n", encoding="utf-8")
            (project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True)
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir(parents=True, exist_ok=True)
        cls.questions = cls.log_dir / "questions"
        cls.questions.mkdir(parents=True, exist_ok=True)

        # Kosten: eine Sitzung mit echten Tokens für die Detailtabelle.
        cls.db = cls.root / "opencode.db"
        con = sqlite3.connect(str(cls.db))
        con.executescript(DDL_V2)
        con.execute(
            "insert into session_v2 (id, project_id, slug, directory, title,"
            " version, agent, model, time_created, time_updated)"
            " values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ses_f33", PROJECT, "slug-f33", str(cls.proj), "proj F1",
             "2.1.4", "coding-agent",
             json.dumps({"id": "model-a", "providerID": "opencode"}), 1, 1))
        con.execute(
            "insert into session_message (id, session_id, type, seq,"
            " time_created, time_updated, data) values (?, ?, ?, ?, ?, ?, ?)",
            ("msg_f33", "ses_f33", "assistant", 1, 1, 1, json.dumps({
                "agent": "coding-agent",
                "model": {"id": "model-a", "providerID": "opencode"},
                "tokens": {"input": 400000, "output": 300000,
                           "reasoning": 200000,
                           "cache": {"read": 600000, "write": 0}},
            })))
        con.commit()
        con.close()

        cls.port = free_port()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                    "TMUX", "TMUX_PANE"):
                env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_STATE": str(cls.state_dir),
            "VIBE_RUNTIME": str(cls.log_dir),
            "VIBE_OPENCODE_DB": str(cls.db),
            "HOME": str(cls.root / "home"),
            "TMPDIR": str(cls.root / "tmp"),
            "TMUX_TMPDIR": str(cls.tmux_dir),
            "VIBE_CONFIG_FILE": str(
                cls.root / "home" / ".config" / "vibe" / "config.json"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        cls.env = env

        # Laufregister-Vorlage: ein abgeschlossener Lauf entsteht mit dem
        # echten Registerformat vor dem Serverstart; je Test wird sie erneut
        # nach runs.json geschrieben.
        failed = subprocess.run([
            sys.executable, str(RUNS_PY), "start",
            "--runtime", str(cls.log_dir),
            "--project", str(cls.proj.resolve()),
            "--name", PROJECT, "--key", PROJECT, "--agent", "vibe-agent",
            "--session", "vibe-f33-failed", "--state", "failed",
        ], env=env, capture_output=True, text=True, timeout=30)
        if failed.returncode != 0:
            raise AssertionError(
                "Vorbedingung fehlgeschlagener Lauf fehlgeschlagen: "
                + failed.stdout + failed.stderr)
        runs_path = cls.log_dir / "runs.json"
        cls.failed_runs_text = runs_path.read_text(encoding="utf-8")
        runs_path.unlink()

        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=cls.server_log, stderr=subprocess.STDOUT, text=True)
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
    def tearDownClass(cls):
        try:
            cls.browser.close()
            cls.playwright.stop()
        finally:
            if cls.proc.poll() is None:
                cls.proc.terminate()
                try:
                    cls.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls.proc.kill()
                    cls.proc.wait()
            cls.server_log.close()
            cls.tmp.cleanup()

    @classmethod
    def write_question_file(cls, qid, project, text):
        (cls.questions / f"{qid}.json").write_text(json.dumps({
            "id": qid,
            "project": project,
            "agent": "tester",
            "text": text,
            "options": ["Ja", "Nein"],
            "free_text": True,
            "created": "2026-11-21T10:00:00Z",
        }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    def setUp(self):
        for path in self.questions.iterdir():
            path.unlink()
        self.write_question_file(QUESTION_PROJ, PROJECT, QUESTION_TEXT_PROJ)
        self.write_question_file(QUESTION_OTHER, OTHER, QUESTION_TEXT_OTHER)
        (self.log_dir / "runs.json").unlink(missing_ok=True)
        self.api_post("/api/language", {"language": "en"})
        self.page_errors = []
        self.context = self.browser.new_context(
            viewport={"width": 1400, "height": 1000})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))

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

    def api_post(self, path, payload):
        body = json.dumps(payload).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("POST", path, body=body, headers={
                "Host": f"127.0.0.1:{self.port}",
                "X-Token": self.token,
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{self.port}",
                "Sec-Fetch-Site": "same-origin"})
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def api_get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("GET", path, headers={
                "Host": f"127.0.0.1:{self.port}", "X-Token": self.token})
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def api_json(self, path):
        status, body = self.api_get(path)
        self.assertEqual(200, status, body)
        return json.loads(body)

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def open_activity(self):
        self.boot()
        self.page.goto(self.base + "/#/activity")
        self.page.locator("main#nv-main[data-nv-view='activity']").wait_for(
            state="visible", timeout=25000)

    def open_settings(self):
        self.boot()
        # Direkt über die Route: unabhängig von doppelten Navigations-
        # Varianten (Desktop/Mobil) und deren Sichtbarkeit.
        self.page.goto(self.base + "/#/settings")
        self.page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=20000)

    def visible_question_ids(self):
        # F34: Die Rückfrage-Karten sind article[data-nv-question] mit
        # data-nv-question-id innerhalb [data-nv-questions]
        # (nova-widgets.js NV.questionCard).
        cards = self.page.locator(
            "[data-nv-questions] article[data-nv-question]")
        result = []
        for index in range(cards.count()):
            card = cards.nth(index)
            if card.is_visible():
                result.append(card.get_attribute("data-nv-question-id"))
        return result

    def toast_text(self):
        toasts = self.page.locator("#nv-toasts")
        return (toasts.inner_text() if toasts.count() else "") or ""

    def assert_no_page_errors(self):
        self.assertEqual(
            [], self.page_errors, "Die Oberfläche erzeugte JavaScript-Fehler")


class ActivityOrderTest(F33SettingsBrowserTest):
    def test_activity_sections_follow_the_contract_order(self):
        """Vorbedingung: eine offene Frage je Projekt.

        Erwartung: Die Bereiche stehen in der Reihenfolge Kacheln →
        Rückfragen → Läufe: ``[data-nv-activity-tiles]`` liegt vor
        ``[data-nv-questions]`` und dieses vor ``[data-nv-runs]``.
        """
        self.open_activity()
        self.page.locator(
            "[data-nv-questions] article[data-nv-question]").first.wait_for(
            state="visible", timeout=20000)
        ordered = self.page.evaluate(
            """() => {
              const selectors = ['[data-nv-activity-tiles]',
                                 '[data-nv-questions]',
                                 '[data-nv-runs]'];
              const nodes = selectors.map(s => document.querySelector(s));
              if (nodes.some(node => !node)) return null;
              return nodes.every((node, index) => index === 0 ||
                (nodes[index - 1].compareDocumentPosition(node)
                 & Node.DOCUMENT_POSITION_FOLLOWING) !== 0);
            }""")
        self.assertIsNotNone(
            ordered, "Mindestens einer der Bereiche Kacheln/Rückfragen/Läufe fehlt")
        self.assertTrue(
            ordered, "Die Aktivitätsbereiche stehen nicht in der Reihenfolge "
                     "Kacheln → Rückfragen → Läufe")
        self.assertEqual(
            0, self.page.locator("[data-nv-sessions]").count(),
            "Der Sessions-Bereich ist in der Aktivität nicht entfernt")
        self.assertEqual(
            0, self.page.locator("[data-nv-sessions-limit]").count(),
            "Der Sessions-Limit-Bereich ist in der Aktivität nicht entfernt")
        self.assertEqual(
            0, self.page.locator("[data-nv-limit-hint]").count(),
            "Der Limit-Hinweis ist in der Aktivität nicht entfernt")
        self.assert_no_page_errors()

    def test_question_project_filter_limits_the_cards(self):
        """Vorbedingung: je eine offene Frage für ``proj`` und ``zweit``.

        Aktion: Im Filter ``select[data-nv-questions-project]`` das Projekt
        ``zweit`` wählen, dann wieder „Alle Projekte“.
        Erwartung: Die Auswahl bietet „Alle Projekte“ und beide Projekte;
        nach der Wahl ist nur die Karte des Projekts sichtbar, „Alle“
        zeigt beide.
        """
        self.open_activity()
        self.page.locator(
            "[data-nv-questions] article[data-nv-question]").first.wait_for(
            state="visible", timeout=20000)
        self.wait_until(
            lambda: len(self.visible_question_ids()) == 2, timeout=20,
            message="Beide offenen Rückfragen sind in der Aktivität "
                    "sichtbar: " + repr(self.visible_question_ids()))
        select = self.page.locator("select[data-nv-questions-project]")
        select.wait_for(state="visible", timeout=20000)
        options = select.evaluate(
            "node => Array.from(node.options).map(o => "
            "[o.value, o.textContent.trim()])")
        self.assertTrue(
            re.search(r"alle projekte|all projects", options[0][1], re.I),
            "Die erste Option des Fragenfilters heißt nicht „Alle Projekte“: "
            + repr(options))
        values = [value for value, _text in options]
        for project in (PROJECT, OTHER):
            self.assertIn(project, values,
                          f"Der Fragenfilter bietet das Projekt {project!r} "
                          "nicht an: " + repr(options))

        select.select_option(OTHER)
        self.wait_until(
            lambda: self.visible_question_ids() == [QUESTION_OTHER],
            timeout=20,
            message="Der Fragenfilter zeigt nach der Projektwahl nicht nur "
                    "die Karte des Projekts: "
                    + repr(self.visible_question_ids()))

        select.select_option(index=0)
        self.wait_until(
            lambda: set(self.visible_question_ids())
            == {QUESTION_PROJ, QUESTION_OTHER},
            timeout=20,
            message="„Alle Projekte“ zeigt nicht wieder beide Rückfragen: "
                    + repr(self.visible_question_ids()))
        self.assert_no_page_errors()

    def test_question_and_limit_hints_are_present(self):
        """Vorbedingung: Aktivität offen.

        Erwartung: ``p[data-nv-questions-hint]`` ist sichtbar und nicht
        leer; ``p[data-nv-activity-sessions-hint]`` ist sichtbar und
        verweist auf die Projekte (Linkziel ``#/``). F34:
        ``[data-nv-limit-hint]`` ist entfallen.
        """
        self.open_activity()
        hint = self.page.locator("p[data-nv-questions-hint]")
        hint.wait_for(state="visible", timeout=20000)
        self.assertTrue((hint.inner_text() or "").strip(),
                        "Der Hinweis zur Rückfragenliste ist leer")
        sessions_hint = self.page.locator("p[data-nv-activity-sessions-hint]")
        sessions_hint.wait_for(state="visible", timeout=20000)
        text = (sessions_hint.inner_text() or "").strip()
        self.assertTrue(
            re.search(r"projekt|project", text, re.I),
            "Der Sitzungs-Hinweis nennt die Projekte nicht: " + repr(text))
        link = sessions_hint.locator("a").first
        self.assertEqual(
            1, link.count(), "Der Sitzungs-Hinweis verweist auf kein Ziel")
        self.assertTrue(
            (link.get_attribute("href") or "").startswith("#/"),
            "Der Link des Sitzungs-Hinweises zielt nicht auf die Projekte: "
            + repr(link.get_attribute("href")))
        self.assertEqual(
            0, self.page.locator("[data-nv-limit-hint]").count(),
            "Der Session-Limit-Hinweis ist in der Aktivität nicht entfernt")
        self.assert_no_page_errors()


class SettingsStructureTest(F33SettingsBrowserTest):
    SETTINGS_SECTIONS = [
        "global-agents", "appearance", "access", "features", "limits",
        "gates", "models", "profiles", "mcp", "harness"]

    def test_settings_sections_in_contract_order(self):
        """Vorbedingung: Einstellungen offen.

        Erwartung: Die Sektionen ``section[data-nv-ssection]`` stehen in
        Vertragsreihenfolge (global-agents, appearance, access, features,
        limits, gates, models, profiles, mcp, harness); die lokale Navigation
        ``nav[data-nv-settings-nav]`` in der gleichen Reihenfolge. Absence:
        ``section[data-nv-ssection='language']`` und die F33-Sektionen
        ``[data-nv-advanced='costs'|'runs'|'env']``.
        """
        self.open_settings()
        ids = self.page.evaluate(
            "() => Array.from(document.querySelectorAll("
            "'section[data-nv-ssection]')).map(n => "
            "n.getAttribute('data-nv-ssection'))")
        self.assertEqual(
            self.SETTINGS_SECTIONS, ids,
            "Die Sektionen stehen nicht in Vertragsreihenfolge: " + repr(ids))
        links = self.page.evaluate(
            "() => Array.from(document.querySelectorAll("
            "'nav[data-nv-settings-nav] button[data-nv-ssection-link]')).map("
            "n => n.getAttribute('data-nv-ssection-link'))")
        self.assertEqual(
            self.SETTINGS_SECTIONS, links,
            "Die lokale Navigation steht nicht in Vertragsreihenfolge: "
            + repr(links))
        for hook in ("section[data-nv-ssection='language']",
                     "[data-nv-advanced='costs']", "[data-nv-advanced='runs']",
                     "[data-nv-advanced='env']"):
            self.assertEqual(
                0, self.page.locator(hook).count(),
                f"{hook} existiert in den Einstellungen, ist in F34 aber "
                "entfernt")
        self.assert_no_page_errors()

    def test_network_advanced_is_collapsed_and_opens(self):
        """Vorbedingung: Einstellungen offen.

        Erwartung: ``details[data-nv-network-advanced]`` liegt in
        ``section[data-nv-ssection='access']``, ist standardmäßig
        geschlossen (Portfeld ``input[data-nv-field='port']`` unsichtbar)
        und öffnet per Klick auf die Zusammenfassung; danach ist das
        Portfeld sichtbar.
        """
        self.open_settings()
        access = self.page.locator("section[data-nv-ssection='access']")
        access.wait_for(state="visible", timeout=20000)
        details = access.locator("details[data-nv-network-advanced]")
        self.assertEqual(
            1, details.count(),
            "Der Netzwerk-Bereich liegt nicht in der Sektion access")
        details.wait_for(state="visible", timeout=20000)
        self.assertFalse(
            details.evaluate("node => node.open"),
            "Der Netzwerk-Bereich ist standardmäßig aufgeklappt")
        port = details.locator("input[data-nv-field='port']")
        self.assertEqual(
            1, port.count(), "Das Portfeld fehlt im Netzwerk-Bereich")
        self.assertFalse(
            port.is_visible() if port.count() else False,
            "Das Portfeld ist trotz geschlossenem Netzwerk-Bereich sichtbar")

        details.locator("summary").first.click()
        self.wait_until(
            lambda: details.evaluate("node => node.open"),
            timeout=15, message="Der Netzwerk-Bereich öffnet sich nicht")
        port.wait_for(state="visible", timeout=15000)
        self.assert_no_page_errors()

    def test_feature_groups_live_in_a_responsive_grid(self):
        """Vorbedingung: Einstellungen offen.

        Erwartung: ``div[data-nv-feature-groups]`` umschließt die
        Feature-Schalter (mindestens ein ``input[data-nv-feature]``).
        """
        self.open_settings()
        groups = self.page.locator("div[data-nv-feature-groups]")
        groups.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(
            groups.locator("input[data-nv-feature]").count(), 1,
            "Im Funktionsraster liegt kein Feature-Schalter")
        self.assert_no_page_errors()

    def test_every_visible_gate_has_a_help_text(self):
        """Vorbedingung: Schranken sind geliefert (GET /api/gates).

        Erwartung: Die Sektion ``section[data-nv-ssection='gates']`` ist
        immer sichtbar (vor dem Einschalten noch ohne Tabelle); nach
        Einschalten des Feature-Schalters ``input[data-nv-feature='gates']``
        zeigt die Tabelle ``table[data-nv-gates-table]`` je Schranke eine
        Zeile ``tr[data-nv-gate]`` mit nichtleerem
        ``small[data-nv-gate-help]``.
        """
        self.open_settings()
        section = self.page.locator("section[data-nv-ssection='gates']")
        section.wait_for(state="visible", timeout=20000)
        # Vertrag: die Sektion ist immer vorhanden; die Tabelle kommt
        # erst mit dem Funktionsschalter gates (nova-settings.js:137).
        self.assertEqual(
            0, section.locator("table[data-nv-gates-table]").count(),
            "Vor dem Einschalten muss die Gates-Tabelle noch nicht liegen")
        toggle = self.page.locator("input[data-nv-feature='gates']")
        toggle.wait_for(state="visible", timeout=20000)
        if not toggle.is_checked():
            toggle.check()
        table = section.locator("table[data-nv-gates-table]")
        table.wait_for(state="visible", timeout=20000)
        gates_view = self.api_json("/api/gates")
        self.assertTrue(gates_view.get("ok"), gates_view)
        keys = list(gates_view["gates"])
        rows = table.locator("tr[data-nv-gate]")
        self.wait_until(
            lambda: rows.count() == len(keys), timeout=20,
            message="Der Schrankenbereich zeigt nicht je Schranke eine "
                    "Zeile: " + repr(rows.count()) + " von " + repr(len(keys)))
        for index in range(rows.count()):
            row = rows.nth(index)
            help_text = row.locator("small[data-nv-gate-help]")
            with self.subTest(gate=row.get_attribute("data-nv-gate")):
                self.assertEqual(
                    1, help_text.count(),
                    "Die Schranke trägt kein small[data-nv-gate-help]")
                self.assertTrue(
                    (help_text.first.inner_text() or "").strip(),
                    "Ein Schranken-Hinweis ist leer")
        self.assert_no_page_errors()


class EvaluationsGroupTest(F33SettingsBrowserTest):
    def test_evaluations_absent_from_settings(self):
        """Vorbedingung: Einstellungen offen, Datenbank mit einer Sitzung.

        Erwartung: In den Einstellungen sind die Auswertungen (Kosten,
        Läufe, Umgebung) entfallen: absence der Feature-Schalter
        ``input[data-nv-feature='costs'|'runs'|'env']`` sowie der F33-Hooks
        ``[data-nv-advanced='costs']``, ``p[data-nv-costs-hint]``,
        ``tr[data-nv-cost-project]``, ``div[data-nv-cost-detail]``,
        ``button[data-nv-action='cost-global-edit']``,
        ``input[data-nv-cost-global-model]``, ``[data-nv-advanced='runs']``,
        ``p[data-nv-runs-hint]``, ``span[data-nv-run-pruneable']``,
        ``[data-nv-advanced='env']`` in den Einstellungen.
        """
        self.open_settings()
        settings = self.page.locator("main#nv-main[data-nv-view='settings']")
        settings.wait_for(state="visible", timeout=20000)
        for feature in ("costs", "runs", "env"):
            self.assertEqual(
                0, settings.locator(
                    f"input[data-nv-feature='{feature}']").count(),
                f"Es gibt den Feature-Schalter {feature!r} noch in den "
                "Einstellungen")
        for hook in (
                "[data-nv-advanced='costs']", "p[data-nv-costs-hint]",
                "tr[data-nv-cost-project]", "div[data-nv-cost-detail]",
                "button[data-nv-action='cost-global-edit']",
                "input[data-nv-cost-global-model]", "[data-nv-advanced='runs']",
                "p[data-nv-runs-hint]", "span[data-nv-run-pruneable]",
                "[data-nv-advanced='env']"):
            with self.subTest(hook=hook):
                self.assertEqual(
                    0, settings.locator(hook).count(),
                    f"{hook} existiert in den Einstellungen, ist in F34 "
                    "aber entfernt")
        self.assert_no_page_errors()

    def test_evaluations_reachable_via_main_nav(self):
        """Vorbedingung: Einstellungen sind zugänglich.

        Aktion: Über den Hauptpunkt
        ``nav[data-nv-navs] [data-nv-nav='evaluations']`` in die
        Auswertungen gehen.

        Erwartung: ``main#nv-main[data-nv-view='evaluations']`` ist
        sichtbar; die drei Tabs ``button[data-nv-etab='costs']``,
        ``button[data-nv-etab='runs']`` und
        ``button[data-nv-etab='environment']`` zeigen.
        """
        self.boot()
        nav = self.page.locator("nav[data-nv-navs] [data-nv-nav='evaluations']")
        nav.wait_for(state="visible", timeout=20000)
        nav.click()
        self.page.locator("main#nv-main[data-nv-view='evaluations']").wait_for(
            state="visible", timeout=25000)
        for name in ("costs", "runs", "environment"):
            tab = self.page.locator(f"button[data-nv-etab='{name}']")
            self.assertEqual(
                1, tab.count(),
                f"Der Tab {name!r} ist in den Auswertungen nicht da")
            tab.wait_for(state="visible", timeout=20000)
        self.assert_no_page_errors()


class RunRegisterTest(F33SettingsBrowserTest):
    def test_run_register_absent_from_settings(self):
        """Vorbedingung: ein abgeschlossener Lauf (``failed``) im Register.

        Erwartung: Das Run-Register ist in den Einstellungen entfallen:
        ``p[data-nv-runs-hint]``, ``span[data-nv-run-pruneable]``,
        ``[data-nv-advanced='runs']`` und ``input[data-nv-feature='runs']``
        sind in den Einstellungen abwesent.
        """
        (self.log_dir / "runs.json").write_text(
            self.failed_runs_text, encoding="utf-8")
        self.open_settings()
        for hook in ("p[data-nv-runs-hint]", "span[data-nv-run-pruneable]",
                     "[data-nv-advanced='runs']",
                     "input[data-nv-feature='runs']"):
            self.assertEqual(
                0, self.page.locator(hook).count(),
                f"{hook} existiert in den Einstellungen, ist in F34 aber "
                "entfernt")
        self.assert_no_page_errors()


class AccentTest(F33SettingsBrowserTest):
    def test_accent_grid_has_twelve_buttons_without_select(self):
        """Vorbedingung: Einstellungen offen, Sprache ``en``.

        Erwartung: ``div[data-nv-accents]`` im Sektion ``appearance``
        bietet exakt die 12 Vertrags-Akzente; je Knopf ein sichtbarer
        ``span.nv-swatch``, ein ``aria-pressed`` und ein übersetzter Name;
        absence ``select[data-nv-accent]``. Die Wahl setzt
        ``html[data-accent]`` und ``localStorage['nv-accent']`` und überlebt
        das Neuladen.
        """
        self.open_settings()
        grid = self.page.locator(
            "[data-nv-ssection='appearance'] div[data-nv-accents]")
        grid.wait_for(state="visible", timeout=20000)
        buttons = grid.locator("button[data-nv-accent]")
        self.assertEqual(12, buttons.count())
        values = self.page.evaluate(
            "() => Array.from(document.querySelectorAll("
            "'div[data-nv-accents] button[data-nv-accent]'))"
            ".map(n => n.getAttribute('data-nv-accent'))")
        self.assertEqual(
            ACCENT_IDS, values,
            "Das Akzent-Raster bietet nicht die 12 Vertragsfarben: "
            + repr(values))
        for index in range(buttons.count()):
            button = buttons.nth(index)
            with self.subTest(accent=values[index]):
                self.assertTrue(button.is_visible())
                self.assertIsNotNone(
                    button.get_attribute("aria-pressed"),
                    "Der Akzent-Knopf trägt kein aria-pressed")
                self.assertTrue(
                    button.locator("span.nv-swatch").is_visible(),
                    "Der Akzent-Knopf trägt keinen sichtbaren span.nv-swatch")
                self.assertTrue(
                    (button.inner_text() or "").strip(),
                    "Der Akzent-Knopf trägt keinen übersetzten Namen")
        self.assertEqual(
            0, self.page.locator("select[data-nv-accent]").count(),
            "Es gibt ein select[data-nv-accent], ist aber in F34 entfernt")

        teal = buttons.nth(ACCENT_IDS.index("teal"))
        teal.click()
        self.wait_until(
            lambda: self.page.evaluate(
                "() => document.documentElement.getAttribute('data-accent')")
            == "teal",
            timeout=15,
            message="Die Akzentwahl setzt html[data-accent] nicht auf teal")
        self.assertEqual(
            "teal",
            self.page.evaluate("() => localStorage.getItem('nv-accent')"),
            "Die Akzentwahl speichert nicht localStorage['nv-accent']")
        self.assertEqual(
            "true", teal.get_attribute("aria-pressed"),
            "Der gewählte Akzent-Knopf ist nicht aria-pressed gesetzt")

        self.page.reload()
        self.page.locator("main#nv-main[data-nv-view='settings']").wait_for(
            state="visible", timeout=25000)
        self.wait_until(
            lambda: self.page.evaluate(
                "() => document.documentElement.getAttribute('data-accent')")
            == "teal",
            timeout=15,
            message="Der Akzent ging beim Reload verloren")
        self.assert_no_page_errors()


class GlobalAgentsFileTest(F33SettingsBrowserTest):
    """Globale AGENTS.md im Einstellungs-Tab (F33 WP5, Koordinator-Entscheidung 6).

    Vorbedingung: Die globale Datei liegt unter ``HOME/.config/opencode/AGENTS.md``;
    jeder Fall legt sie selbst an oder löscht sie, damit die Fälle
    unabhängig bleiben. Der Editor erfolgt unter
    ``section[data-nv-ssection='global-agents']`` (GH-57-Vertrag: flache
    Sektion, Editor in ``NV.editView`` mit ``textarea[data-nv-agents-text]``).
    """

    def setUp(self):
        super().setUp()
        self.global_agents = (
            self.root / "home" / ".config" / "opencode" / "AGENTS.md")
        self.global_agents.parent.mkdir(parents=True, exist_ok=True)
        self.post_requests = []
        self.page.on(
            "request",
            lambda request: self.post_requests.append(request)
            if request.method == "POST" else None)
        # Vor dem ersten Laden der Editor-State setzen, sodass die Sektion
        # sicher eingeschaltet ist.
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.evaluate(
            "() => localStorage.setItem('nv-features', "
            "JSON.stringify({agentsfile: true}))")

    def posts_to(self, path):
        payloads = []
        for request in self.post_requests:
            if request.url.split("?")[0].endswith(path):
                try:
                    payloads.append(json.loads(request.post_data or "{}"))
                except ValueError:
                    payloads.append({})
        return payloads

    def global_view(self):
        return self.api_json("/api/global_agents_file")

    def section(self):
        # GH-57-Vertrag: flache Sektion global-agents ohne details.
        return self.page.locator(
            "section[data-nv-ssection='global-agents']")

    def open_global_agents_editor(self):
        """Öffnet den gemeinsamen Editor über den Bearbeiten-Knopf (GH-57)."""
        section = self.section()
        section.wait_for(state="visible", timeout=20000)
        edit = section.locator(
            "button[data-nv-action='global-agents-edit']")
        edit.wait_for(state="visible", timeout=20000)
        edit.click()
        editor = self.page.locator(
            "aside[data-nv-editview] textarea[data-nv-agents-text]")
        editor.wait_for(state="visible", timeout=20000)
        return editor

    def test_missing_file_shows_hint_and_create_button(self):
        """Vorbedingung: globale AGENTS.md existiert nicht.

        Aktion: Einstellungen öffnen, ``button[data-nv-action=
        "global-agents-create"]`` klicken.
        Erwartung: Ein Hinweis nennt die fehlende Datei; der Klick sendet
        ``POST /api/global_agents_file {action:"create"}``; danach erscheint
        ``textarea[data-nv-agents-text]`` in der Edit-View mit der
        angelegten Vorlage.
        """
        self.global_agents.unlink(missing_ok=True)
        self.open_settings()
        section = self.section()
        section.wait_for(state="visible", timeout=20000)
        text = section.inner_text() or ""
        self.assertTrue(
            re.search(r"fehlt|fehlend|nicht vorhanden|missing|not found",
                      text, re.I),
            "Der Hinweis nennt die fehlende globale AGENTS.md nicht: "
            + repr(text))
        create = section.locator(
            "button[data-nv-action='global-agents-create']")
        self.assertEqual(
            1, create.count(),
            "Der Anlegen-Knopf global-agents-create fehlt bei fehlender Datei")
        create.click()
        self.wait_until(
            lambda: any(payload.get("action") == "create"
                        for payload in self.posts_to("/api/global_agents_file")),
            timeout=20,
            message="Es wurde kein /api/global_agents_file-POST mit "
                    "action=create gesendet: "
                    + repr(self.posts_to("/api/global_agents_file")))
        self.wait_until(
            lambda: self.global_agents.is_file(), timeout=20,
            message="Die globale AGENTS.md wurde nicht angelegt")
        editor = self.page.locator(
            "aside[data-nv-editview] textarea[data-nv-agents-text]")
        editor.wait_for(state="visible", timeout=20000)
        self.assertTrue(
            (editor.input_value() or "").strip(),
            "Der Editor ist nach dem Anlegen nicht mit der Vorlage vorbelegt")
        self.assert_no_page_errors()

    def test_existing_file_editor_prefills_and_saves_with_digest(self):
        """Vorbedingung: globale AGENTS.md mit Text vorhanden.

        Aktion: Text im Editor ändern und speichern.
        Erwartung: ``textarea[data-nv-agents-text]`` ist mit dem aktuellen
        Text vorbelegt; der POST ``{action:"save", text, digest}`` trägt den
        neuen Text und eine Prüfsumme; ein Toast bestätigt; die Datei enthält
        den neuen Text. Ein zweites Speichern nutzt den aktualisierten Digest
        (lokales Digest-Update), nicht die alte Prüfsumme.
        """
        self.global_agents.write_text(GLOBAL_AGENTS_TEXT, encoding="utf-8")
        self.open_settings()
        editor = self.open_global_agents_editor()
        self.assertIn(
            "GLOBALE-REGEL-4711", editor.input_value(),
            "Der Editor ist nicht mit dem aktuellen Text der globalen "
            "AGENTS.md vorbelegt")
        initial = self.global_view()
        self.assertTrue(initial.get("exists"),
                        "Vorbedingung: Die globale Datei wird nicht erkannt")
        new_text = GLOBAL_AGENTS_TEXT + "Neue globale Regel 4711.\n"
        editor.fill(new_text)
        save = self.page.locator(
            "aside[data-nv-editview] button[data-nv-action='agents-save']")
        self.assertEqual(1, save.count(),
                         "Der Speichern-Knopf agents-save fehlt")
        save.click()
        self.wait_until(
            lambda: any(payload.get("action") == "save"
                        for payload in self.posts_to("/api/global_agents_file")),
            timeout=20,
            message="Es wurde kein /api/global_agents_file-POST mit "
                    "action=save gesendet: "
                    + repr(self.posts_to("/api/global_agents_file")))
        payload = [p for p in self.posts_to("/api/global_agents_file")
                   if p.get("action") == "save"][-1]
        self.assertEqual(new_text, payload.get("text"),
                         "Der POST enthält nicht den eingegebenen Text")
        self.assertEqual(
            initial["digest"], payload.get("digest"),
            "Der POST sendet nicht die geladene Prüfsumme der globalen "
            "AGENTS.md")
        self.wait_until(
            lambda: re.search(r"gespeichert|saved", self.toast_text(), re.I)
            is not None, timeout=20,
            message="Das Speichern der globalen AGENTS.md bestätigt nicht: "
                    + repr(self.toast_text()))
        self.wait_until(
            lambda: "Neue globale Regel 4711"
            in self.global_agents.read_text(encoding="utf-8"),
            timeout=20,
            message="Der neue Text steht nicht in der globalen AGENTS.md")

        # Lokales Digest-Update: der nächste Save darf nicht an einer
        # veralteten Prüfsumme scheitern.
        current = self.global_view()
        self.assertTrue(current.get("digest"),
                        "Nach dem Speichern liefert die API keine Prüfsumme")
        second_text = new_text + "Noch eine Regel 4712.\n"
        editor.fill(second_text)
        save.click()
        self.wait_until(
            lambda: len([p for p in self.posts_to("/api/global_agents_file")
                         if p.get("action") == "save"]) >= 2,
            timeout=20,
            message="Ein zweites Speichern wurde nicht gesendet: "
                    + repr(self.posts_to("/api/global_agents_file")))
        second = [p for p in self.posts_to("/api/global_agents_file")
                  if p.get("action") == "save"][-1]
        self.assertEqual(
            current["digest"], second.get("digest"),
            "Das zweite Speichern nutzt nicht den aktualisierten Digest "
            "(lokales Digest-Update fehlt)")
        self.wait_until(
            lambda: "Noch eine Regel 4712"
            in self.global_agents.read_text(encoding="utf-8"),
            timeout=20,
            message="Das zweite Speichern schreibt den Text nicht")
        self.assert_no_page_errors()

    def test_hint_explains_the_scope_of_the_global_file(self):
        """Vorbedingung: globale AGENTS.md vorhanden.

        Erwartung: ``[data-nv-global-agents-hint]`` ist sichtbar und
        erklärt, dass die Regeln für alle Projekte gelten und die
        projektbezogene AGENTS.md sie ergänzt. (GH-57: Hook ohne Element-
        Typ-Vorgabe, Text-Assertionen unverändert.)
        """
        self.global_agents.write_text(GLOBAL_AGENTS_TEXT, encoding="utf-8")
        self.open_settings()
        hint = self.page.locator("[data-nv-global-agents-hint]")
        hint.wait_for(state="visible", timeout=20000)
        text = hint.inner_text() or ""
        self.assertTrue(text.strip(),
                        "Der Hinweis zur globalen AGENTS.md ist leer")
        self.assertTrue(
            re.search(r"alle|all", text, re.I),
            "Der Hinweis sagt nicht, dass die Regeln für alle Projekte "
            "gelten: " + repr(text))
        self.assertTrue(
            re.search(r"projekte|projects?", text, re.I),
            "Der Hinweis nennt die Projekte nicht: " + repr(text))
        self.assertTrue(
            re.search(r"ergänz|supplement|extend|project-specific", text, re.I),
            "Der Hinweis sagt nicht, dass die projektbezogene AGENTS.md die "
            "globalen Regeln ergänzt: " + repr(text))
        self.assert_no_page_errors()


# ===========================================================================
# Browserabnahme, Einstellungen (Nova-Überarbeitung)
# ===========================================================================

import http.client
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402


class _FakeOpenCodeHandler_f34(BaseHTTPRequestHandler):
    """opencode-Attrappe: antwortet leer, startet keine Modelle."""

    def log_message(self, *args):
        return

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send_json(200, {"data": []})


class F34SettingsBrowserTest(unittest.TestCase):
    """Dashboard, Browser, Fake-OpenCode, isolierter Zustand (F34 WP4)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / PROJECT
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n", encoding="utf-8")
        (cls.project / "TICKETS.md").write_text(
            "# TICKETS\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True)
        # Echter MCP-Server in der isolierten HOME: /api/mcp liefert sonst
        # servers=[] und die Kartenprüfung wäre eine Leerlaufprüfung.
        (cls.root / "home" / ".config" / "opencode" / "opencode.json").write_text(
            json.dumps({"mcp": {"servers": {"f34-test-server": {
                "type": "local",
                "command": ["echo", "f34-test-server"],
            }}}}, indent=2) + "\n", encoding="utf-8")
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir(parents=True)
        password = cls.log_dir / "opencode.password"
        password.write_text("f34-ui-kennwort-42", encoding="utf-8")
        password.chmod(0o600)
        cls.port = free_port()
        cls.oc_port = free_port()
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), _FakeOpenCodeHandler_f34)
        cls._fake_http.daemon_threads = True
        cls._fake_thread = threading.Thread(
            target=cls._fake_http.serve_forever)
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
            "VIBE_RUNTIME": str(cls.log_dir),
            "HOME": str(cls.root / "home"),
            "TMPDIR": str(cls.root / "tmp"),
            "TMUX_TMPDIR": str(cls.tmux_dir),
            "VIBE_CONFIG_FILE": str(
                cls.root / "home" / ".config" / "vibe" / "config.json"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        cls.env = env
        cls.server_log = open(cls.root / "web-server.log", "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=cls.server_log, stderr=subprocess.STDOUT, text=True)
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
    def tearDownClass(cls):
        try:
            cls.browser.close()
            cls.playwright.stop()
        finally:
            try:
                cls._fake_http.shutdown()
                cls._fake_http.server_close()
                cls._fake_thread.join(timeout=5)
            except Exception:
                pass
            if cls.proc.poll() is None:
                cls.proc.terminate()
                try:
                    cls.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls.proc.kill()
                    cls.proc.wait()
            cls.server_log.close()
            cls.tmp.cleanup()

    def setUp(self):
        self.global_agents = (
            self.root / "home" / ".config" / "opencode" / "AGENTS.md")
        self.global_agents.parent.mkdir(parents=True, exist_ok=True)
        self._post_requests = []
        self.api_post("/api/language", {"language": "en"})
        self.api_post("/api/security", {"action": "password", "clear": True})
        self.page_errors = []
        self.context = self.browser.new_context(
            viewport={"width": 1400, "height": 900})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))
        self.page.on(
            "request",
            lambda request: self._post_requests.append(request)
            if request.method == "POST" else None)
        self.context.add_init_script(
            "try { localStorage.setItem('nv-features', JSON.stringify("
            "{gates: true, limits: true, models: true, profiles: true, "
            "mcp: true, agentsfile: true})); } catch (error) {}")

    def tearDown(self):
        self.page.close()
        self.context.close()

    # ---------- Helfer ----------

    def wait_until(self, predicate, timeout=20,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def api_post(self, path, payload, token=None):
        body = json.dumps(payload).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("POST", path, body=body, headers={
                "Host": f"127.0.0.1:{self.port}",
                "X-Token": token or self.token,
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{self.port}",
                "Sec-Fetch-Site": "same-origin"})
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def api_get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("GET", path, headers={
                "Host": f"127.0.0.1:{self.port}",
                "X-Token": self.token})
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def api_json(self, path):
        status, body = self.api_get(path)
        self.assertEqual(200, status, body)
        return json.loads(body)

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator(
            "main#nv-main[data-nv-view='home']").wait_for(
                state="visible", timeout=25000)
        self.install_render_counter()

    def open_settings(self):
        self.page.goto(self.base + "/#/settings")
        self.page.locator(
            "main#nv-main[data-nv-view='settings']").wait_for(
                state="visible", timeout=20000)
        self.install_render_counter()

    def enable_features(self, *ids):
        for feature in ids:
            toggle = self.page.locator(f"input[data-nv-feature='{feature}']")
            toggle.wait_for(state="visible", timeout=20000)
            if not toggle.is_checked():
                toggle.check()
        self.page.locator(
            "main#nv-main[data-nv-view='settings']").wait_for(
                state="visible", timeout=20000)

    def posts_to(self, path):
        payloads = []
        for request in self._post_requests:
            if request.url.split("?")[0].endswith(path):
                try:
                    payloads.append(json.loads(request.post_data or "{}"))
                except ValueError:
                    payloads.append({})
        return payloads

    def wait_for_post(self, path, predicate, timeout=20, message=None):
        return self.wait_until(
            lambda: any(predicate(payload) for payload in self.posts_to(path)),
            timeout=timeout, message=message or "Post nicht empfangen")

    def toast_text(self):
        toasts = self.page.locator("#nv-toasts")
        return (toasts.inner_text() if toasts.count() else "") or ""

    def install_render_counter(self):
        """Umhüllt ``NV.render`` mit einem Zähler des TESTGERÜSTS.

        Das Produkt besitzt keinen eigenen Render-Zähler (``NV.render`` wird
        in ``bin/web/nova-core.js`` gesetzt); dieser Helfer hängt sich nach
        dem Laden davor und erhöht ``window.__nvRenderCount`` bei jedem Aufruf
        von ``NV.render``. Ein unveränderter Zähler belegt damit, dass eine
        Aktion keinen Voll-Neurender ausgelöst hat — ohne Umhüllung würde die
        Zusicherung nichts prüfen. Der Helfer ist idempotent (Seite wird nur
        einmal umhüllt); nach einem ``page.goto`` muss er erneut laufen, weil
        der Reload den Zähler zurücksetzt.
        """
        state = self.page.evaluate(
            """() => {
              if (window.__nvRenderCounterInstalled === true) {
                return {ok: true, already: true};
              }
              if (typeof NV === 'undefined'
                  || typeof NV.render !== 'function') {
                return {ok: false, reason: 'NV.render fehlt'};
              }
              var original = NV.render;
              window.__nvRenderCount = 0;
              window.__nvRenderCountOriginal = original;
              NV.render = function () {
                window.__nvRenderCount += 1;
                return original.apply(this, arguments);
              };
              window.__nvRenderCounterInstalled = true;
              return {
                ok: true,
                already: false,
                wrapped: NV.render !== window.__nvRenderCountOriginal,
                countsInBody: String(NV.render)
                  .indexOf('__nvRenderCount') !== -1
              };
            }""")
        self.assertTrue(
            state.get("ok"),
            "Der Render-Zähler konnte nicht installiert werden: %r"
            % (state.get("reason"),))
        if not state.get("already"):
            self.assertTrue(
                state.get("wrapped") and state.get("countsInBody"),
                "Die Umhüllung von NV.render zählt nicht wirklich: %r"
                % (state,))

    def nv_render_count(self):
        """Zählerstand des testseitig umhüllten ``NV.render``.

        Scheitert, wenn der Zähler nicht installiert ist — ein stiller
        Rückfall auf 0 würde eine Zusicherung vortäuschen, die nichts prüft.
        """
        state = self.page.evaluate(
            """() => ({
              installed: window.__nvRenderCounterInstalled === true,
              count: typeof window.__nvRenderCount === 'number'
                ? window.__nvRenderCount : null
            })""")
        self.assertTrue(
            state.get("installed"),
            "Der Render-Zähler ist nicht installiert; nv_render_count() "
            "kann keinen Voll-Neurender ausschließen")
        self.assertIsNotNone(
            state.get("count"),
            "Der Render-Zähler hat keinen numerischen Stand")
        return state["count"]

    def gate_value_differing_from(self, field):
        """Liefert einen gültigen Schrankenwert, der vom Feldwert abweicht.

        Zählschranken werden um eins erhöht; Auswahl-Schranken (``override``)
        wechseln auf die jeweils andere Option. Der Wert bleibt damit
        gültig für ``POST /api/gates`` (bin/vibe_gates.py ``validate``).
        GH-57: Der Vergleichswert darf aus einem nur-lesenden Feld kommen
        (``[data-nv-gate-global]`` ist kein Eingabefeld mehr) — dann wird
        der angezeigte Text gelesen.
        """
        is_input = field.evaluate(
            "node => ['input','select','textarea'].includes("
            "node.tagName.toLowerCase())")
        if is_input:
            current = (field.input_value() or "").strip()
        else:
            current = (field.inner_text() or "").strip()
        if field.evaluate("node => node.tagName.toLowerCase()") == "select":
            options = field.evaluate(
                "node => Array.from(node.options).map(o => o.value)")
            for option in options:
                if option != current:
                    return option
            self.fail(
                "Die Wert-Auswahl %r bietet keinen abweichenden Wert"
                % current)
        try:
            return str(int(current) + 1)
        except ValueError:
            return "1"

    def visible_error_text(self):
        parts = []
        for selector in ("#nv-toasts", "[data-nv-form-error]"):
            nodes = self.page.locator(selector)
            for index in range(nodes.count()):
                node = nodes.nth(index)
                if node.is_visible():
                    parts.append((node.inner_text() or "").strip())
        access = self.page.locator("[data-nv-ssection='access']")
        if access.count() and access.is_visible():
            text = access.inner_text() or ""
            for word in ("ungültig", "invalid", "Fehler", "error"):
                if word in text:
                    parts.append(text)
                    break
        return "\n".join(parts)

    def confirmation_visible(self):
        toasts = self.page.locator("#nv-toasts")
        if toasts.count() and toasts.is_visible() and (
                toasts.inner_text() or "").strip():
            return True
        access = self.page.locator("[data-nv-ssection='access']")
        if access.count() and access.is_visible():
            text = (access.inner_text() or "").lower()
            return any(word in text for word in
                       ("gespeichert", "saved", "gesetzt", "set", "success"))
        return False

    def assert_no_page_errors(self):
        self.assertEqual(
            [], self.page_errors, "Die Oberfläche erzeugte JavaScript-Fehler")


class GlobalAgentsLayoutTest(F34SettingsBrowserTest):
    def test_global_agents_section_flat_hint_and_editview_editor(self):
        """GH-57 (global-agents): flache Sektion, Hinweis, Edit-View mit
        textarea[data-nv-agents-text] rows >= 16. Ersetzt den F34-Stand
        (details[data-nv-global-agents] + Inline-Editor), der dem
        GH-57-Vertrag („flach, keine details-Verschachtelung“, gemeinsamer
        Editor in NV.editView) widerspricht. Ersetzt die frühere Prüfung
        „Sektion ist die erste“ (Deckung: test_f33 SettingsStructureTest)."""
        self.global_agents.write_text(GLOBAL_AGENTS_TEXT, encoding="utf-8")
        self.boot()
        self.open_settings()
        section = self.page.locator("section[data-nv-ssection='global-agents']")
        section.wait_for(state="visible", timeout=20000)
        self.assertEqual(0, section.locator("details").count(),
                         "Die Sektion ist weiterhin details-verschachtelt")
        hint = section.locator("[data-nv-global-agents-hint]")
        hint.wait_for(state="visible", timeout=20000)
        self.assertTrue((hint.inner_text() or "").strip(),
                        "Die Erklärung zur globalen AGENTS.md fehlt")
        edit = section.locator("button[data-nv-action='global-agents-edit']")
        edit.wait_for(state="visible", timeout=20000)
        edit.click()
        aside = self.page.locator("aside[data-nv-editview]")
        aside.wait_for(state="visible", timeout=20000)
        textarea = aside.locator("textarea[data-nv-agents-text]")
        textarea.wait_for(state="visible", timeout=20000)
        rows = textarea.evaluate(
            "node => parseInt(node.getAttribute('rows') || '0', 10)"
            " || node.rows")
        self.assertGreaterEqual(rows, 16, "Editor hat weniger als 16 rows")

    def test_missing_global_agents_file_shows_create_only_when_missing(self):
        """GH-57: Anlegen-Knopf nur bei fehlender Datei; Klick legt die Datei
        an und öffnet den Editor in der Edit-View (statt Inline-Editor)."""
        self.global_agents.unlink(missing_ok=True)
        self.boot()
        self.open_settings()
        section = self.page.locator("section[data-nv-ssection='global-agents']")
        section.wait_for(state="visible", timeout=20000)
        create = section.locator(
            "button[data-nv-action='global-agents-create']")
        self.assertEqual(1, create.count(),
                         "Der Anlegen-Knopf fehlt bei fehlender Datei")
        create.click()
        self.wait_until(lambda: self.global_agents.is_file(), timeout=20,
                        message="Die Vorlage wurde nicht angelegt")
        editor = self.page.locator(
            "aside[data-nv-editview] textarea[data-nv-agents-text]")
        editor.wait_for(state="visible", timeout=20000)
        self.assertTrue((editor.input_value() or "").strip(),
                        "Der Editor ist nicht vorbelegt")
        self.wait_until(
            lambda: self.page.locator(
                "button[data-nv-action='global-agents-create']").count() == 0,
            timeout=15, message="Der Anlegen-Knopf bleibt sichtbar")
        self.assert_no_page_errors()

    def test_global_agents_save_writes_file_and_toasts_without_rerender(self):
        """GH-57: Speichern aus der Edit-View (agents-save) schreibt die Datei,
        bestätigt per Toast und löst keinen Voll-Neurender aus. Der Digest-
        Vergleich liegt in test_f33 (Editor-Vertrag) und
        test_gh57_settings_ui.GlobalAgentsSectionTest."""
        self.global_agents.write_text(GLOBAL_AGENTS_TEXT, encoding="utf-8")
        self.boot()
        self.open_settings()
        section = self.page.locator("section[data-nv-ssection='global-agents']")
        section.locator("button[data-nv-action='global-agents-edit']").click()
        aside = self.page.locator("aside[data-nv-editview]")
        aside.wait_for(state="visible", timeout=20000)
        editor = aside.locator("textarea[data-nv-agents-text]")
        editor.wait_for(state="visible", timeout=20000)
        new_text = GLOBAL_AGENTS_TEXT + "Neue globale Regel 4711.\n"
        editor.fill(new_text)
        render_before = self.nv_render_count()
        aside.locator("button[data-nv-action='agents-save']").click()
        self.wait_for_post(
            "/api/global_agents_file", lambda p: p.get("action") == "save",
            message="Kein POST action=save gesendet")
        self.wait_until(
            lambda: re.search(r"gespeichert|saved", self.toast_text(), re.I),
            timeout=20, message="Kein Bestätigungs-Toast")
        self.wait_until(
            lambda: "Neue globale Regel 4711"
            in self.global_agents.read_text(encoding="utf-8"),
            timeout=20, message="Der neue Text steht nicht in der Datei")
        self.assertEqual(render_before, self.nv_render_count(),
                         "Das Speichern vollneu-rendered")


class AppearanceSectionTest(F34SettingsBrowserTest):
    def test_accent_is_a_raster_of_swatch_buttons_without_select(self):
        """Vorbedingung: Einstellungen offen.

        Erwartung: kein select[data-nv-accent-select]; button[data-nv-accent]
        je Akzent mit span.nv-swatch (nicht transparent) und aria-pressed;
        Auswahl setzt html[data-accent]; Akzentnamen deutsch/englisch verschieden.
        """
        self.boot()
        self.open_settings()
        select = self.page.locator("select[data-nv-accent-select]")
        self.assertEqual(
            0, select.count(),
            "Die Akzentwahl darf kein select[data-nv-accent-select] verwenden")
        buttons = self.page.locator("button[data-nv-accent]")
        buttons.first.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            len(ACCENT_IDS), buttons.count(),
            "Das Akzentraster bietet nicht alle 12 Vertragsfarben")
        active = self.page.evaluate(
            "() => document.documentElement.getAttribute('data-accent')")
        for index, accent_id in enumerate(ACCENT_IDS):
            with self.subTest(accent=accent_id):
                button = buttons.nth(index)
                self.assertEqual(
                    1, button.locator("span.nv-swatch").count(),
                    f"Der Akzent {accent_id} hat kein span.nv-swatch")
                background = button.locator("span.nv-swatch").evaluate(
                    "node => getComputedStyle(node).backgroundColor")
                self.assertNotEqual(
                    "rgba(0, 0, 0, 0)", background,
                    f"Der Swatch des Akzents {accent_id} ist transparent")
                self.assertNotEqual(
                    "transparent", background,
                    f"Der Swatch des Akzents {accent_id} ist transparent")
                pressed = button.get_attribute("aria-pressed")
                expected = "true" if accent_id == active else "false"
                self.assertEqual(
                    expected, pressed,
                    f"Der Akzent {accent_id} hat aria-pressed={pressed!r}, "
                    f"erwartet {expected!r}")

        target = buttons.nth(1)
        target.click()
        self.wait_until(
            lambda: self.page.evaluate(
                "() => document.documentElement.getAttribute('data-accent')")
            == "teal",
            timeout=15, message="Die Akzentwahl setzt html[data-accent] nicht")
        self.assertEqual(
            "teal",
            self.page.evaluate("() => localStorage.getItem('nv-accent')"),
            "Die Akzentwahl speichert nicht localStorage['nv-accent']")

        names = self.page.evaluate(
            "() => { const api = window.VIBE_I18N || window.I18N; "
            "return api && api.DICTS ? {de: api.DICTS.de || {}, en: "
            "api.DICTS.en || {}} : {}; }")
        self.assertTrue(names.get("de"), "Das deutsche Wörterbuch fehlt")
        self.assertTrue(names.get("en"), "Das englische Wörterbuch fehlt")
        for key in ("Blau", "Türkis"):
            with self.subTest(accent=key):
                de_name = names["de"].get(key)
                en_name = names["en"].get(key)
                self.assertIsNotNone(
                    en_name, f"Die englische Akzentbezeichnung für {key} fehlt")
                self.assertNotEqual(
                    de_name, en_name,
                    f"Die Akzentbezeichnung für {key} ist nicht übersetzt")

    def test_currency_select_usd_rate_and_ui_settings_save_persist(self):
        """Vorbedingung: Einstellungen offen, Sprache englisch.

        Aktion: Währungs-Select auf USD, Rate eintragen, Speichern, Reload.
        Erwartung: select[data-nv-currency] mit EUR/USD; input[data-nv-usd-rate]
        nur bei USD; Speichern ruft POST /api/ui_settings auf; nach Reload ist
        die Wahl in ui.json erhalten.
        """
        self.boot()
        self.open_settings()
        select = self.page.locator("select[data-nv-currency]")
        select.wait_for(state="visible", timeout=20000)
        values = select.evaluate(
            "node => Array.from(node.options).map(o => o.value)")
        self.assertEqual(
            ["EUR", "USD"], values, "Der Währung-Select bietet nicht EUR/USD")
        self.assertEqual(
            "EUR", select.input_value(),
            "Der Währung-Select steht nicht auf EUR")
        select.select_option("USD")

        usd_rate = self.page.locator("input[data-nv-usd-rate]")
        usd_rate.wait_for(state="visible", timeout=20000)
        usd_rate.fill("1.25")
        save = self.page.locator(
            "main#nv-main[data-nv-view='settings'] button").filter(
                has_text=re.compile(r"speicher|save", re.I))
        save.first.wait_for(state="visible", timeout=20000)
        self.page.on(
            "request",
            lambda request: self._post_requests.append(request)
            if request.method == "POST" and request.url.split("?")[0].endswith(
                "/api/ui_settings") else None)
        save.first.click()
        self.wait_for_post(
            "/api/ui_settings",
            lambda payload: True, timeout=20,
            message="Es wurde kein POST /api/ui_settings gesendet")

        # Vor dem Speichern stand EUR (siehe oben); nach dem Speichern muss
        # die Auswahl auf USD stehen und der Reload sie erhalten.
        self.assertEqual(
            "USD", select.input_value(),
            "Der Währung-Select steht nach dem Speichern nicht auf USD")
        self.assertEqual(
            "1.25", usd_rate.input_value(),
            "Die USD-Rate steht nach dem Speichern nicht auf 1.25")

        self.page.reload()
        self.page.locator(
            "main#nv-main[data-nv-view='settings']").wait_for(
                state="visible", timeout=25000)
        select = self.page.locator("select[data-nv-currency]")
        select.wait_for(state="visible", timeout=20000)
        usd_rate = self.page.locator("input[data-nv-usd-rate]")
        self.wait_until(
            lambda: usd_rate.is_visible(),
            timeout=20000, message="Das Feld data-nv-usd-rate ist bei USD nicht "
                                  "sichtbar")
        self.assertEqual(
            "USD", select.input_value(),
            "Die Währungs-/USD-Auswahl ging beim Reload nicht verloren")
        self.assertEqual(
            "1.25", usd_rate.input_value(),
            "Die gespeicherte USD-Rate ging beim Reload verloren")
        self.assert_no_page_errors()


class EmptyAreaTest(F34SettingsBrowserTest):
    def test_settings_has_no_evaluations_or_environment_or_ops_areas(self):
        """Vorbedingung: Einstellungen offen.

        Erwartung: keine Auswertungen/Kosten/Run-Register/Umgebung/Fritzbox/
        Emulator/opencode-Server in den Einstellungen.
        """
        self.boot()
        self.open_settings()
        checks = (
            ("[data-nv-cost-summary]", "Kosten-Summary"),
            ("[data-nv-cost-projects]", "Kosten-Projektliste"),
            ("[data-nv-run-table]", "Run-Register-Tabelle"),
            ("[data-nv-env-doctor]", "Umgebungs-Checkliste"),
            ('[data-nv-action="fritz-reconnect"]', "FRITZ-Reconnect-Button"),
            ("[data-nv-emu-result]", "Emulator-Ergebnis"),
            ("[data-nv-server-status]", "opencode-Server-Status"),
            ("[data-nv-ssection='evaluations']", "Auswertungen-Sektion"),
        )
        for selector, label in checks:
            with self.subTest(area=label):
                self.assertEqual(
                    0, self.page.locator(selector).count(),
                    f"Der Einstellungen-Bereich {label} darf nicht gerendert sein")
        self.assert_no_page_errors()


class SettingsNavigationTest(F34SettingsBrowserTest):
    def test_settings_local_section_nav_scrolls_and_activates(self):
        """Vorbedingung: Einstellungen offen, lokale Navigation vorhanden.

        Erwartung: nav[data-nv-settings-nav] mit data-nv-ssection-link; Layout
        div.nv-settings-layout mit max. ~980px Inhalt und Navigation daneben.
        """
        self.boot()
        self.open_settings()
        nav = self.page.locator("nav[data-nv-settings-nav]")
        nav.wait_for(state="visible", timeout=20000)
        links = nav.locator("[data-nv-ssection-link]")
        self.assertGreaterEqual(
            links.count(), 8, "Die lokale Einstellungs-Navigation hat nicht "
                               "mindestens 8 Sektionen")
        layout = self.page.locator("div.nv-settings-layout")
        layout.wait_for(state="visible", timeout=20000)
        content = self.page.locator("div.nv-settings-content")
        content.wait_for(state="visible", timeout=20000)
        boxes = self.page.evaluate(
            """(selectors) => {
               const out = {};
               for (const s of selectors) {
                 const node = document.querySelector(s);
                 const r = node ? node.getBoundingClientRect() : null;
                 out[s] = r ? {y: r.top, x: r.left, width: r.width,
                              height: r.height} : null;
               }
               return out;
             }""",
            ["nav[data-nv-settings-nav]", "div.nv-settings-content"])
        nav_box = boxes["nav[data-nv-settings-nav]"]
        content_box = boxes["div.nv-settings-content"]
        self.assertIsNotNone(nav_box, "nav[data-nv-settings-nav] fehlt")
        self.assertIsNotNone(content_box, "div.nv-settings-content fehlt")
        self.assertLess(
            nav_box["x"] + nav_box["width"],
            content_box["x"] + 0.5,
            "Die Sektionen-Navigation liegt nicht neben dem Inhaltsbereich")
        max_width = content.evaluate(
            "node => parseFloat(getComputedStyle(node).maxWidth) || 0")
        self.assertLessEqual(
            max_width, 980.5, f"Der Inhaltsbereich ist zu breit: {max_width}")


class LimitsTest(F34SettingsBrowserTest):
    def test_limits_single_toggle_posts_mode_and_explains_effect(self):
        """GH-57 (limits): statt zwei Optionskarten gibt es genau einen
        Schalter input[type=checkbox][data-nv-limits-mode] in
        label.nv-switch-row, eine Erklärung [data-nv-limits-help] und einen
        POST /api/limits {action:'continue'|'stop'} ohne Voll-Neurender.
        Ersetzt den F34-Stand (limits-continue/limits-stop-Karten), der dem
        GH-57-Vertrag widerspricht; die Prüfung „Wirkung erklärt“ bleibt."""
        self.boot()
        self.open_settings()
        self.enable_features("limits")
        box = self.page.locator("section[data-nv-ssection='limits']")
        box.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            0, self.page.locator(
                "button[data-nv-action='limits-continue'],"
                " button[data-nv-action='limits-stop']").count(),
            "Die alten Modus-Knöpfe existieren weiterhin")
        help_box = box.locator("[data-nv-limits-help]")
        help_box.wait_for(state="visible", timeout=20000)
        effect = (help_box.inner_text() or "") + " " + (box.inner_text() or "")
        self.assertTrue(
            re.search(r"fortsetz|stopp|neuen|lauf|unterbrech", effect, re.I),
            "Die Limits-Erklärung enthält keine Wirkungsbeschreibung")
        toggle = box.locator("input[type=checkbox][data-nv-limits-mode]")
        toggle.wait_for(state="visible", timeout=20000)
        mode = self.api_json("/api/limits").get("mode")
        self.assertEqual(mode == "continue", toggle.is_checked(),
                        "Der Schalter spiegelt den Modus nicht")
        render_before = self.nv_render_count()
        toggle.click()
        expected = "continue" if mode != "continue" else "stop"
        self.wait_for_post(
            "/api/limits", lambda p: p.get("action") == expected,
            message="Kein POST /api/limits {action:%r}" % expected)
        self.wait_until(
            lambda: self.api_json("/api/limits").get("mode") == expected,
            timeout=20, message="Der Moduswechsel wird nicht bestätigt")
        self.assertEqual(render_before, self.nv_render_count(),
                         "Der Limits-Schalter vollneu-rendered")


class GatesTest(F34SettingsBrowserTest):
    def test_gates_project_select_table_and_override(self):
        """GH-57 (gates): Global-Kontext (Standard) hat vier Spalten (Name,
        Wirkung, editierbarer Wert, Herkunft); der Projektkontext zeigt den
        globalen Wert nur-lesend [data-nv-gate-global] und den Projektwert
        editierbar [data-nv-gate-override]. Die Abweichungs-Badge-Logik
        („Weicht ab“ nur bei abweichendem Projektwert) bleibt unverändert.
        Ersetzt die F34-Fünfspalten-Erwartung (Projektzelle „—“), die dem
        GH-57-Vertrag widerspricht."""
        self.boot()
        self.open_settings()
        self.enable_features("gates")
        view = self.api_json("/api/gates")
        self.assertTrue(view.get("ok"), view)
        section = self.page.locator("section[data-nv-ssection='gates']")
        section.wait_for(state="visible", timeout=20000)
        table = section.locator("[data-nv-gates-table]")
        table.wait_for(state="visible", timeout=20000)
        rows = table.locator("tr[data-nv-gate]")
        self.wait_until(lambda: rows.count() >= 1, timeout=20,
                        message="Die Gates-Tabelle hat keine Zeilen")
        # Global-Kontext (Standard): editierbarer Wert, Herkunft, kein Override.
        for index in range(rows.count()):
            row = rows.nth(index)
            with self.subTest(gate=row.get_attribute("data-nv-gate")):
                self.assertTrue((row.locator(
                    "small[data-nv-gate-help]").first.inner_text()
                    or "").strip(), "Eine Gates-Zeile hat keine Erklärung")
                self.assertEqual(1, row.locator(
                    "[data-nv-gate-value]").count(),
                    "Eine Gates-Zeile hat kein Wert-Feld")
                self.assertEqual(1, row.locator(
                    "[data-nv-gate-origin]").count(),
                    "Eine Gates-Zeile hat kein Herkunfts-Feld")
                self.assertEqual(0, row.locator(
                    "[data-nv-gate-override]").count(),
                    "Im Global-Kontext gibt es ein Override-Feld")
                self.assertEqual(0, row.locator(
                    "span[data-nv-gate-override-badge]").count(),
                    "Im Global-Kontext erscheint ein Abweichungs-Badge")

        project_select = section.locator("select[data-nv-gates-project]")
        project_select.wait_for(state="visible", timeout=20000)
        options = project_select.evaluate(
            "node => Array.from(node.options).map(o => o.value)")
        self.assertIn("global", options, "Der Gates-Filter fehlt 'global'")
        self.assertIn(
            PROJECT, options, "Der Gates-Filter bietet das Projekt nicht an")
        self.assertEqual(
            "global", project_select.input_value(),
            "Die Projektauswahl startet nicht im Global-Kontext (GH-57)")

        # Projektkontext: nur-lesender globaler Wert + Override.
        project_select.select_option(PROJECT)
        first = rows.first
        self.wait_until(
            lambda: first.locator("input[data-nv-gate-override]").count() == 1,
            timeout=20, message="Im Projektkontext fehlt das Override-Feld")
        self.assertTrue(
            first.locator("[data-nv-gate-global]").count() >= 1,
            "Im Projektkontext fehlt der nur-lesende globale Wert")
        gate_key = first.get_attribute("data-nv-gate")
        badge = "span[data-nv-gate-override-badge]"
        deviation = self.gate_value_differing_from(
            first.locator("[data-nv-gate-global]"))
        self.wait_until(
            lambda: (first.locator(
                "input[data-nv-gate-override]").input_value() or "") == "",
            timeout=20,
            message="Der Projektkontext startet mit einem gesetzten "
                    "Override; die Abwesenheitsprüfung wäre nicht eindeutig")
        first.locator("input[data-nv-gate-override]").fill(deviation)
        self.page.locator("button[data-nv-action='gates-save']").click()
        self.wait_until(
            lambda: first.locator(badge).count() == 1, timeout=20,
            message=(
                "Nach dem Speichern des abweichenden Projektwerts %r für %r "
                "fehlt das Abweichungs-Badge %s an genau dieser Zeile "
                "(Erwartung laut docs/features/GH-57.md Gates)"
                % (deviation, gate_key, badge)))
        badge_text = (first.locator(badge).first.inner_text() or "").strip()
        self.assertTrue(
            badge_text, "Das Abweichungs-Badge ist leer")
        self.assertRegex(
            badge_text, re.compile(r"(?i)weicht ab|differs"),
            "Das Abweichungs-Badge benennt die Abweichung nicht: "
            + repr(badge_text))
        without_deviation = 0
        for index in range(rows.count()):
            row = rows.nth(index)
            if row.get_attribute("data-nv-gate") == gate_key:
                continue
            with self.subTest(gate=row.get_attribute("data-nv-gate")):
                self.assertEqual(
                    0, row.locator(badge).count(),
                    "Eine Gates-Zeile ohne Projektabweichung trägt ein "
                    "Abweichungs-Badge")
                without_deviation += 1
        self.assertGreater(
            without_deviation, 0,
            "Die Abwesenheitsprüfung des Badges hatte keine zweite "
            "Gates-Zeile ohne Abweichung")

        # Ausgangszustand wiederherstellen und dabei prüfen, dass das Badge
        # nach dem Entfernen der Abweichung verschwindet.
        first.locator("input[data-nv-gate-override]").fill("")
        self.page.locator("button[data-nv-action='gates-save']").click()
        self.wait_until(
            lambda: first.locator(badge).count() == 0, timeout=20,
            message="Nach dem Leeren des Projektwerts bleibt das "
                    "Abweichungs-Badge stehen")
        view = self.api_json("/api/gates?name=" + PROJECT)
        self.assertIn(
            view["gates"][gate_key].get("override"), ("", None),
            "Der geleerte Projektwert ist serverseitig nicht entfernt")
        self.assert_no_page_errors()

    def test_gates_save_sends_all_values_one_post_without_rerender(self):
        """Vorbedingung: Feature ``gates`` an, Gates offen.

        Aktion: in mehreren Zeilen einen vom Feldwert abweichenden gültigen
        Wert eintragen, Speichern klicken.

        Erwartung: GENAU EIN ``POST /api/gates`` während des Speicherns; die
        Nutzlast trägt den Projektkontext und ALLE Zeilenschlüssel mit genau
        den eingetragenen Werten (``{project, values:{...}}``); der echte
        Render-Zähler (umhülltes ``NV.render``, siehe
        ``install_render_counter``) bleibt unverändert; Reset-Knopf vorhanden.
        """
        self.boot()
        self.open_settings()
        self.enable_features("gates")
        gates = self.page.locator("[data-nv-advanced='gates']")
        gates.wait_for(state="visible", timeout=20000)
        save = self.page.locator("button[data-nv-action='gates-save']")
        save.wait_for(state="visible", timeout=20000)
        project_select = gates.locator("select[data-nv-gates-project]")
        project_select.wait_for(state="visible", timeout=20000)
        context = project_select.input_value()
        field_selector = ("[data-nv-gate-value]" if context == "global"
                          else "[data-nv-gate-override]")
        rows = gates.locator("table[data-nv-gates-table] tr[data-nv-gate]")
        self.wait_until(
            lambda: rows.count() >= 2, timeout=20,
            message="Die Gates-Tabelle hat weniger als zwei Zeilen")

        # In mehreren Zeilen abweichende Werte eintragen; die Nutzlast muss
        # danach ALLE Zeilenschlüssel mit genau diesen Werten tragen.
        changed = []
        for index in range(rows.count()):
            row = rows.nth(index)
            key = row.get_attribute("data-nv-gate")
            field = row.locator(field_selector)
            self.assertEqual(
                1, field.count(),
                "Die Gates-Zeile %r hat kein eindeutiges Eingabefeld %s"
                % (key, field_selector))
            if len(changed) < 2 and key != "override":
                before_value = field.input_value() or ""
                new_value = self.gate_value_differing_from(field)
                field.fill(new_value)
                self.assertNotEqual(
                    before_value, new_value,
                    "Testaufbau: der neue Wert der Zeile %r weicht nicht vom "
                    "Feldwert ab" % (key,))
                changed.append((key, new_value))
        self.assertGreaterEqual(
            len(changed), 2,
            "Es konnten nicht mindestens zwei Gates-Zeilen geändert werden")

        expected_values = {}
        for index in range(rows.count()):
            row = rows.nth(index)
            key = row.get_attribute("data-nv-gate")
            expected_values[key] = (
                row.locator(field_selector).input_value() or "")
        for key, value in changed:
            self.assertEqual(
                value, expected_values.get(key),
                "Testaufbau: der eingetragene Wert der Zeile %r ging im DOM "
                "verloren" % (key,))

        posts_before = len(self.posts_to("/api/gates"))
        render_before = self.nv_render_count()
        save.click()
        self.wait_until(
            lambda: len(self.posts_to("/api/gates")) > posts_before,
            timeout=20, message="Es wurde kein POST /api/gates gesendet")
        # Auf das Ende der Speicherkette warten (Toast nach dem Redraw), damit
        # ein später ausgelöster Voll-Neurender noch im Zähler ankommt.
        self.wait_until(
            lambda: re.search(r"gespeichert|saved", self.toast_text(), re.I)
            is not None, timeout=20,
            message="Das Gates-Speichern bestätigt nicht: "
                    + repr(self.toast_text()))

        payloads = self.posts_to("/api/gates")
        self.assertEqual(
            posts_before + 1, len(payloads),
            "Der Gates-Save sendet nicht genau einen POST /api/gates: "
            + repr(payloads))
        payload = payloads[-1]
        self.assertIn("values", payload,
                      "Der Gates-Save sendet keine Sammel-Nutzlast: "
                      + repr(payload))
        self.assertEqual(
            "" if context == "global" else context,
            str(payload.get("project") or ""),
            "Die Nutzlast trägt nicht den gewählten Projektkontext: "
            + repr(payload))
        self.assertEqual(
            expected_values, payload.get("values"),
            "Die Nutzlast enthält nicht alle Zeilenschlüssel mit den "
            "eingetragenen Werten")

        self.assertEqual(
            render_before, self.nv_render_count(),
            "Das Speichern der Schranken vollneu-rendered (NV.render wurde "
            "während des Speicherns aufgerufen)")
        reset = self.page.locator("button[data-nv-action='gates-reset']")
        reset.wait_for(state="visible", timeout=20000)
        self.assertTrue(reset.is_visible(), "Der Reset-Knopf fehlt")

    def test_gates_reset_button_is_disabled_without_project_context(self):
        """Vorbedingung: Feature ``gates`` an, Gates-Ansicht geöffnet.

        Aktion: Reset-Knopf im Global-Kontext prüfen, Projekt „global“ wählen,
        dann ein Projekt wählen.

        Erwartung: ``select[data-nv-gates-project]`` im Wert „global“;
        Knopf ``button[data-nv-action='gates-reset']`` deaktiviert
        (``disabled``) und trägt Erklärung im ``title`` (Projektkontext nötig);
        nach Wahl eines Projekts ist der Knopf aktiv.
        """
        self.boot()
        self.open_settings()
        self.enable_features("gates")
        gates = self.page.locator("[data-nv-advanced='gates']")
        gates.wait_for(state="visible", timeout=20000)
        reset = self.page.locator(
            "section[data-nv-ssection='gates'] button[data-nv-action='gates-reset']")
        reset.wait_for(state="visible", timeout=20000)
        project_select = self.page.locator(
            "section[data-nv-ssection='gates'] select[data-nv-gates-project]")
        project_select.wait_for(state="visible", timeout=20000)
        options = project_select.evaluate(
            "node => Array.from(node.options).map(o => o.value)")
        self.assertIn("global", options, "Der Gates-Filter fehlt 'global'")
        self.assertIn(PROJECT, options, "Der Gates-Filter bietet das Projekt nicht an")
        project_select.select_option("global")
        self.wait_until(
            lambda: reset.is_disabled(), timeout=15,
            message="Der Reset-Knopf ist im Global-Kontext nicht deaktiviert")
        title = (reset.get_attribute("title") or "").strip()
        self.assertTrue(title, "Der Reset-Knopf trägt im Global-Kontext keine "
                                "title-Erklärung (Projektkontext nötig)")
        self.assertRegex(
            title, re.compile(r"(?i)projekt|project|global"),
            "Die title-Erklärung … fehlt: " + repr(title))
        project_select.select_option(PROJECT)
        self.wait_until(
            lambda: not reset.is_disabled(), timeout=15,
            message="Der Reset-Knopf wird nach Projektwahl nicht aktiv")
        self.assert_no_page_errors()


class ModelsLayoutTest(F34SettingsBrowserTest):
    def test_models_collapsed_refresh_in_head_and_stand_line(self):
        """GH-57 (models): details[data-nv-models] ist standardmäßig
        EINGEKLAPPT (kein open); der Aktualisieren-Knopf steht im
        Sektionskopf und ist auch eingeklappt sichtbar; die Katalog-
        Beschreibung (data-nv-models-hint / „Referenz“-Text) ist entfallen.
        Der Katalog (data-nv-model-catalog) bleibt eingeklappt mit
        models-prices. Ersetzt den F34-Stand (details offen, Refresh im
        Katalog, Hinweistext), der dem GH-57-Vertrag widerspricht."""
        self.boot()
        self.open_settings()
        self.enable_features("models")
        section = self.page.locator("section[data-nv-ssection='models']")
        section.wait_for(state="visible", timeout=20000)
        models = section.locator("details[data-nv-models]")
        models.wait_for(state="attached", timeout=20000)
        self.assertFalse(models.evaluate("node => node.open"),
                         "details[data-nv-models] ist standardmäßig offen")
        refresh = section.locator("button[data-nv-action='models-refresh']")
        self.assertTrue(refresh.is_visible(),
                        "Der Aktualisieren-Knopf ist eingeklappt unsichtbar")
        self.assertEqual(0, section.locator("[data-nv-models-hint]").count(),
                         "Die Katalog-Beschreibung ist nicht entfallen")
        self.assertEqual(1, section.locator(
            "[data-nv-models-stand]").count(),
            "Die Zeile mit dem Aktualisierungsstand fehlt")
        catalog = section.locator("details[data-nv-model-catalog]")
        catalog.wait_for(state="attached", timeout=20000)
        self.assertFalse(catalog.evaluate("node => node.open"),
                         "Der Katalog ist standardmäßig offen")
        catalog.locator("summary").first.click()
        self.wait_until(lambda: catalog.evaluate("node => node.open"),
                        timeout=10, message="Der Katalog lässt sich nicht "
                                            "aufklappen")
        prices = catalog.locator("button[data-nv-action='models-prices']")
        prices.wait_for(state="visible", timeout=20000)
        self.assert_no_page_errors()


class ProfilesLayoutTest(F34SettingsBrowserTest):
    def test_profiles_select_with_role_comboboxes_and_actions(self):
        """GH-57 (profiles): Profilauswahl select[data-nv-profiles-select]
        statt article[data-nv-profile]-Karten; Zuordnungen mit
        [data-nv-profile-role]-Comboboxen; Aktionsknöpfe save/cancel/apply/
        backup vorhanden. Ersetzt den F34-Stand (Profilkarten), der dem
        GH-57-Vertrag widerspricht; Tiefe in test_gh57_settings_ui."""
        self.boot()
        self.open_settings()
        self.enable_features("profiles")
        section = self.page.locator("section[data-nv-ssection='profiles']")
        section.wait_for(state="visible", timeout=20000)
        select = section.locator("select[data-nv-profiles-select]")
        select.wait_for(state="visible", timeout=20000)
        self.assertEqual(0, section.locator("article[data-nv-profile]").count(),
                         "Die Profile erscheinen weiterhin als Karten")
        roles_box = section.locator("[data-nv-profile-roles]")
        roles_box.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(
            section.locator("[data-nv-profile-role]").count(), 1,
            "Es gibt keine Rollen-Combobox")
        for action in ("profile-save", "profile-cancel", "profile-apply",
                       "profile-backup"):
            self.assertEqual(
                1, section.locator(
                    f"button[data-nv-action='{action}']").count(),
                f"Der Knopf {action} fehlt")
        self.assert_no_page_errors()


class McpLayoutTest(F34SettingsBrowserTest):
    def test_mcp_cards_show_state_toggle_and_no_entry_button(self):
        """Vorbedingung: Feature ``mcp`` an.

        Erwartung: ``article[data-nv-mcp-server]`` mit Status-Pille
        ``[data-nv-mcp-state]`` ("Aktiv"/"Inaktiv") und Umschalter
        ``[data-nv-action="mcp-toggle"]`` ("Aktivieren"/"Deaktivieren");
        kein "Eintrag anzeigen"-Knopf; Scope im Bearbeitungsformular wählbar
        ``[data-nv-mcp-scope]``; Filter ``[data-nv-mcp-search]``.
        """
        self.boot()
        self.open_settings()
        self.enable_features("mcp")
        cards = self.page.locator("article[data-nv-mcp-server]")
        cards.first.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(cards.count(), 1, "Keine MCP-Karten")
        state = self.page.locator("span[data-nv-mcp-state]")
        state.first.wait_for(state="visible", timeout=20000)
        toggle = self.page.locator(
            "button[data-nv-action='mcp-toggle']")
        toggle.first.wait_for(state="visible", timeout=20000)
        entry_buttons = self.page.locator(
            "button[data-nv-action='mcp-entry'], button[data-nv-mcp-entry]")
        self.assertEqual(
            0, entry_buttons.count(),
            "Der MCP-Bereich darf keinen 'Eintrag anzeigen'-Knopf haben")
        # Umschalten wirkt nur auf die Karte (Status + Knopftext) und den
        # Speicher — kein Voll-Neurender. Der echte Render-Zähler des
        # Testgerüsts bleibt deshalb unverändert.
        card = cards.first
        server_name = card.get_attribute("data-nv-mcp-server")
        card_state = card.locator("span[data-nv-mcp-state]")
        card_toggle = card.locator("button[data-nv-action='mcp-toggle']")
        state_before = (card_state.inner_text() or "").strip()
        label_before = (card_toggle.inner_text() or "").strip()
        self.assertIn(state_before, ("Active", "Aktiv"),
                      "Statuspille der MCP-Karte ist weder 'Active' noch "
                      "'Aktiv': " + repr(state_before))
        self.assertIn(label_before, ("Deaktivieren", "Deactivate", "Disable"),
                      "Der aktive Server bietet keinen Deaktivieren-Knopf: "
                      + repr(label_before))
        was_enabled = state_before in ("Active", "Aktiv")
        render_before = self.nv_render_count()
        card_toggle.click()
        self.wait_for_post(
            "/api/mcp",
            lambda payload: payload.get("action") == "toggle"
            and payload.get("name") == server_name,
            message="Der Umschalter sendet kein POST /api/mcp {action:'toggle'}: "
                    + repr(self.posts_to("/api/mcp")))
        expected_states = ("Inaktiv", "Inactive") if was_enabled \
            else ("Aktiv", "Active")
        expected_labels = ("Aktivieren", "Activate", "Enable") if was_enabled \
            else ("Deaktivieren", "Deactivate", "Disable")
        self.wait_until(
            lambda: (card_state.inner_text() or "").strip() in expected_states,
            timeout=15,
            message="Die Statuspille wechselt nicht (beobachtet: "
                    + repr((card_state.inner_text() or "").strip()) + ")")
        self.assertIn(
            (card_toggle.inner_text() or "").strip(), expected_labels,
            "Der Knopftext wechselt nicht: "
            + repr((card_toggle.inner_text() or "").strip()))
        self.wait_until(
            lambda: re.search(r"mcp|geändert|changed|aktiviert|deaktiviert",
                              self.toast_text(), re.I) is not None,
            timeout=15,
            message="Der Umschalter bestätigt nicht per Toast: "
                    + repr(self.toast_text()))
        self.assertEqual(
            render_before, self.nv_render_count(),
            "Der MCP-Umschalter vollneu-rendered (NV.render wurde während "
            "des Umschaltens aufgerufen)")

        def mcp_enabled():
            data = self.api_json("/api/mcp")
            for server in data.get("servers") or []:
                if server.get("name") == server_name:
                    return server.get("enabled")
            self.fail("Der MCP-Server %r fehlt in GET /api/mcp"
                      % (server_name,))

        self.wait_until(
            lambda: mcp_enabled() is (not was_enabled), timeout=15,
            message="Der Umschaltzustand ist nicht über GET /api/mcp "
                    "persistiert: " + repr(mcp_enabled()))
        config = json.loads(
            (self.root / "home" / ".config" / "opencode" / "opencode.json")
            .read_text(encoding="utf-8"))
        self.assertIs(
            not was_enabled,
            (config.get("mcp") or {}).get("servers", {}).get(
                server_name, {}).get("enabled"),
            "Der Umschaltzustand ist nicht in der MCP-Konfiguration "
            "persistiert: " + repr(config.get("mcp")))
        # Der Scope wird im Bearbeitungsformular (Edit-View) gewählt —
        # GH-57 öffnet das MCP-Formular in NV.editView statt im Kontext-Panel.
        edit = cards.first.locator("button[data-nv-action='mcp-edit']")
        edit.wait_for(state="visible", timeout=20000)
        edit.click()
        scope = self.page.locator(
            "aside[data-nv-editview] select[data-nv-mcp-scope]")
        scope.wait_for(state="visible", timeout=20000)
        self.assertIn(
            "global",
            scope.evaluate("node => Array.from(node.options).map(o => o.value)"),
            "Der Scope des MCP-Servers ist im Formular nicht wählbar")
        search = self.page.locator("input[data-nv-mcp-search]")
        search.wait_for(state="visible", timeout=20000)
        self.assert_no_page_errors()


# ===========================================================================
# Browserabnahme: Überarbeitete Settings-Ansicht (Shell, Edit-View, Sektionen)
# ===========================================================================

import http.client
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402


GLOBAL_AGENTS_TEXT_gh57 = "GH57-GLOBAL-RULE: gilt für alle Projekte.\n"
FAKE_MODELS = "opencode/test-modell\nopencode/vibe-modell\nopencode/neu\n"

VIBE_AGENT = """---
description: Vibe-Standardagent für Nutzerunterstützung
mode: primary
model: opencode/vibe-modell
---

Vibe-Agent-Prompt.
"""

TESTER_AGENT = """---
description: Tester mit Coder-Rolle
mode: subagent
model: opencode/test-modell
---

Tester-Prompt.
"""

# Standardprofile werden von profiles_load ergänzt (Vertrag §Backend 2);
# „meins" bleibt als nutzerdefiniertes Profil erhalten. Der Coder der
# Agent-Einstellungen (tester → opencode/test-modell) ist das Modell hinter
# „Default" für die Rolle coder.
PROFILES_SEED = {
    "aktiv": "default",
    "rollen": {"tester": "coder", "vibe-agent": "vibe"},
    "profile": {"meins": {"coder": "opencode/vibe-modell"}},
}

MCP_SEED = {"mcp": {"servers": {"gh57-basis-server": {
    "type": "local", "command": ["echo", "basis"], "enabled": True}}}}

FAKE_OPENCODE_gh57 = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf 'opencode 2.1.4\\n'
    exit 0
    ;;
  models)
    if [ -n "$GH57_FAKE_MODELS_FILE" ] && [ -f "$GH57_FAKE_MODELS_FILE" ]; then
      cat "$GH57_FAKE_MODELS_FILE"
    fi
    exit 0
    ;;
esac
exit 2
"""


class _FakeOpenCodeHandler_gh57(BaseHTTPRequestHandler):
    """opencode-Server-Attrappe: antwortet leer, startet keine Modelle."""

    def log_message(self, *args):
        return

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send_json(200, {"data": []})


class GH57SettingsBrowserTest(unittest.TestCase):
    """Dashboard, Browser, opencode-Attrappen, isolierter Zustand (GH-57)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        for name in (PROJECT, OTHER):
            project = cls.root / name
            (project / ".vibe").mkdir(parents=True)
            (project / ".vibe" / "project.env").write_text(
                "TYPE=generic\n", encoding="utf-8")
            (project / "FEEDBACK.md").write_text(
                "# FEEDBACK\n", encoding="utf-8")
            (project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
        (cls.root / "home" / ".config" / "opencode" / "agents").mkdir(
            parents=True, exist_ok=True)
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)
        cls.log_dir = cls.root / "_logs"
        cls.log_dir.mkdir(parents=True)
        password = cls.log_dir / "opencode.password"
        password.write_text("gh57-ui-kennwort-42", encoding="utf-8")
        password.chmod(0o600)

        # opencode-STUB-Binary auf dem PATH (Modelle aus Datei, kein Netz).
        cls.fake_bin = cls.root / "fakebin"
        cls.fake_bin.mkdir()
        stub = cls.fake_bin / "opencode"
        stub.write_text(FAKE_OPENCODE_gh57, encoding="utf-8")
        stub.chmod(0o755)
        cls.models_source = cls.fake_bin / "models.txt"
        cls.models_source.write_text(FAKE_MODELS, encoding="utf-8")

        cls.port = free_port()
        cls.oc_port = free_port()
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), _FakeOpenCodeHandler_gh57)
        cls._fake_http.daemon_threads = True
        cls._fake_thread = threading.Thread(
            target=cls._fake_http.serve_forever)
        cls._fake_thread.daemon = True
        cls._fake_thread.start()

        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                    "TMUX", "TMUX_PANE", "GH57_FAKE_MODELS_FILE"):
                env.pop(key, None)
        env.update({
            "VIBE": str(cls.root),
            "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port),
            "VIBE_OPENCODE_PORT": str(cls.oc_port),
            "VIBE_STATE": str(cls.state_dir),
            "VIBE_RUNTIME": str(cls.log_dir),
            "HOME": str(cls.root / "home"),
            "TMPDIR": str(cls.root / "tmp"),
            "TMUX_TMPDIR": str(cls.tmux_dir),
            "VIBE_CONFIG_FILE": str(
                cls.root / "home" / ".config" / "vibe" / "config.json"),
            "GH57_FAKE_MODELS_FILE": str(cls.models_source),
            "PATH": str(cls.fake_bin) + os.pathsep + env.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        cls.env = env
        cls.server_log = open(cls.root / "web-server.log", "w",
                              encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=env,
            stdout=cls.server_log, stderr=subprocess.STDOUT, text=True)
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
    def tearDownClass(cls):
        try:
            cls.browser.close()
            cls.playwright.stop()
        finally:
            try:
                cls._fake_http.shutdown()
                cls._fake_http.server_close()
                cls._fake_thread.join(timeout=5)
            except Exception:
                pass
            if cls.proc.poll() is None:
                cls.proc.terminate()
                try:
                    cls.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    cls.proc.kill()
                    cls.proc.wait()
            cls.server_log.close()
            cls.tmp.cleanup()

    def setUp(self):
        # Unabhängiger Zustand je Fall: Fachdateien zurücksetzen.
        for name in ("gates.json", "limits.json", "models-cache.json"):
            (self.state_dir / name).unlink(missing_ok=True)
        (self.state_dir / "profiles.json").write_text(
            json.dumps(PROFILES_SEED, ensure_ascii=False) + "\n",
            encoding="utf-8")
        self.models_source.write_text(FAKE_MODELS, encoding="utf-8")
        self.global_agents = (
            self.root / "home" / ".config" / "opencode" / "AGENTS.md")
        self.global_agents.parent.mkdir(parents=True, exist_ok=True)
        self.global_agents.write_text(GLOBAL_AGENTS_TEXT_gh57, encoding="utf-8")
        self.tester_agent = (
            self.root / "home" / ".config" / "opencode" / "agents"
            / "tester.md")
        self.tester_agent.write_text(TESTER_AGENT, encoding="utf-8")
        self.mcp_config = (
            self.root / "home" / ".config" / "opencode" / "opencode.json")
        self.mcp_config.write_text(
            json.dumps(MCP_SEED, ensure_ascii=False) + "\n", encoding="utf-8")
        self.api_post("/api/language", {"language": "en"})
        self.api_post("/api/security", {"action": "password", "clear": True})
        self.page_errors = []
        self._post_requests = []
        self.context = self.browser.new_context(
            viewport={"width": 1400, "height": 900})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))
        self.page.on(
            "request",
            lambda request: self._post_requests.append(request)
            if request.method == "POST" else None)
        self.context.add_init_script(
            "try { localStorage.setItem('nv-features', JSON.stringify("
            "{agentsfile: true, gates: true, limits: true, models: true, "
            "profiles: true, mcp: true, harness: true})); } catch (e) {}")

    def tearDown(self):
        self.page.close()
        self.context.close()

    # ---------- Helfer ----------

    def wait_until(self, predicate, timeout=20,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def api_post(self, path, payload, token=None):
        body = json.dumps(payload).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("POST", path, body=body, headers={
                "Host": f"127.0.0.1:{self.port}",
                "X-Token": token or self.token,
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{self.port}",
                "Sec-Fetch-Site": "same-origin"})
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def api_get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request("GET", path, headers={
                "Host": f"127.0.0.1:{self.port}",
                "X-Token": self.token})
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def api_json(self, path):
        status, body = self.api_get(path)
        self.assertEqual(200, status, body)
        return json.loads(body)

    def boot(self):
        self.page.goto(self.base + "/#t=" + self.token)
        self.page.locator(
            "main#nv-main[data-nv-view='home']").wait_for(
                state="visible", timeout=25000)
        self.install_render_counter()

    def open_settings(self):
        self.page.goto(self.base + "/#/settings")
        self.page.locator(
            "main#nv-main[data-nv-view='settings']").wait_for(
                state="visible", timeout=20000)
        self.install_render_counter()

    def set_viewport(self, width, height):
        self.page.set_viewport_size({"width": width, "height": height})

    def boxes(self, selectors):
        return self.page.evaluate(
            """(selectors) => {
                 const out = {};
                 for (const s of selectors) {
                   const node = document.querySelector(s);
                   const r = node ? node.getBoundingClientRect() : null;
                   out[s] = r ? {x: r.left, y: r.top, w: r.width,
                                 h: r.height, right: r.right,
                                 bottom: r.bottom} : null;
                 }
                 return out;
               }""",
            list(selectors))

    def posts_to(self, path):
        payloads = []
        for request in self._post_requests:
            if request.url.split("?")[0].endswith(path):
                try:
                    payloads.append(json.loads(request.post_data or "{}"))
                except ValueError:
                    payloads.append({})
        return payloads

    def wait_for_post(self, path, predicate, timeout=20,
                      message="Post nicht empfangen"):
        self.wait_until(
            lambda: any(predicate(p) for p in self.posts_to(path)),
            timeout=timeout, message=message)

    def toast_text(self):
        toasts = self.page.locator("#nv-toasts")
        return (toasts.inner_text() if toasts.count() else "") or ""

    def install_render_counter(self):
        """Umhüllt ``NV.render`` mit einem Zähler des Testgerüsts (Muster F34)."""
        state = self.page.evaluate(
            """() => {
              if (window.__nvRenderCounterInstalled === true) {
                return {ok: true, already: true};
              }
              if (typeof NV === 'undefined'
                  || typeof NV.render !== 'function') {
                return {ok: false, reason: 'NV.render fehlt'};
              }
              var original = NV.render;
              window.__nvRenderCount = 0;
              window.__nvRenderCountOriginal = original;
              NV.render = function () {
                window.__nvRenderCount += 1;
                return original.apply(this, arguments);
              };
              window.__nvRenderCounterInstalled = true;
              return {ok: true, already: false,
                      wrapped: NV.render !== window.__nvRenderCountOriginal,
                      countsInBody: String(NV.render)
                        .indexOf('__nvRenderCount') !== -1};
            }""")
        self.assertTrue(state.get("ok"),
                        "Render-Zähler nicht installierbar: %r"
                        % (state.get("reason"),))
        if not state.get("already"):
            self.assertTrue(
                state.get("wrapped") and state.get("countsInBody"),
                "Die Umhüllung von NV.render zählt nicht wirklich: %r"
                % (state,))

    def nv_render_count(self):
        state = self.page.evaluate(
            """() => ({
              installed: window.__nvRenderCounterInstalled === true,
              count: typeof window.__nvRenderCount === 'number'
                ? window.__nvRenderCount : null
            })""")
        self.assertTrue(state.get("installed"),
                        "Render-Zähler nicht installiert")
        self.assertIsNotNone(state.get("count"))
        return state["count"]

    def confirm_in_context(self, timeout=15):
        """Klickt eine sichtbare Bestätigen-Schaltfläche im NV.context."""
        panel = self.page.locator("aside[data-nv-context]")
        deadline = time.time() + timeout
        while time.time() < deadline:
            if panel.count() and panel.first.is_visible():
                buttons = panel.first.locator("button")
                for index in range(buttons.count()):
                    button = buttons.nth(index)
                    if not button.is_visible():
                        continue
                    text = (button.inner_text() or "").strip().lower()
                    if re.search(r"bestätig|bestaetig|confirm|ja\b|yes|ok",
                                 text, re.I):
                        button.click()
                        return True
            self.page.wait_for_timeout(100)
        return False

    def assert_no_page_errors(self):
        self.assertEqual(
            [], self.page_errors, "Die Oberfläche erzeugte JavaScript-Fehler")

    def open_global_agents_edit(self):
        section = self.page.locator(
            "section[data-nv-ssection='global-agents']")
        section.wait_for(state="visible", timeout=20000)
        edit = section.locator("button[data-nv-action='global-agents-edit']")
        edit.wait_for(state="visible", timeout=20000)
        edit.click()
        aside = self.page.locator("aside[data-nv-editview]")
        aside.wait_for(state="visible", timeout=20000)
        return aside

    def section(self, name):
        node = self.page.locator(f"section[data-nv-ssection='{name}']")
        node.wait_for(state="visible", timeout=20000)
        return node


class ShellAndEditViewTest(GH57SettingsBrowserTest):
    MOBILE = {"width": 390, "height": 844}

    def test_mobile_nav_visible_below_header_and_horizontally_scrollable(self):
        """Mobil: Menü sichtbar, scrollbar, unterhalb der Kopfzeile, Anker-Marge."""
        self.set_viewport(self.MOBILE["width"], self.MOBILE["height"])
        self.boot()
        self.open_settings()
        nav = self.page.locator("nav[data-nv-settings-nav]")
        nav.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(
            nav.locator("[data-nv-ssection-link]").count(), 8,
            "Die mobile Navigation bietet nicht alle Sektionen")
        scrollable = nav.evaluate(
            """node => ({sw: node.scrollWidth, cw: node.clientWidth,
                         ox: getComputedStyle(node).overflowX})""")
        self.assertGreater(
            scrollable["sw"], scrollable["cw"],
            "Die mobile Navigation ist nicht horizontal scrollbar: "
            + repr(scrollable))
        self.assertIn(scrollable["ox"], ("auto", "scroll"),
                      "Die mobile Navigation hat kein horizontales Scrollen: "
                      + repr(scrollable))

        def geometry():
            return self.boxes(["header.nv-top", "nav[data-nv-settings-nav]",
                               "section[data-nv-ssection='appearance']"])

        boxes = geometry()
        self.assertIsNotNone(boxes["header.nv-top"], "Kopfzeile fehlt")
        self.assertGreaterEqual(
            boxes["nav[data-nv-settings-nav]"]["y"],
            boxes["header.nv-top"]["bottom"] - 2,
            "Die mobile Navigation überlappt die globale Kopfzeile")
        margin = self.page.locator(
            "section[data-nv-ssection='appearance']").evaluate(
                "node => parseFloat(getComputedStyle(node).scrollMarginTop)"
                " || 0")
        self.assertGreater(
            margin, 0,
            "Sektionsanker haben keinen scroll-margin-top unterhalb der Leiste")

        self.page.evaluate("window.scrollTo(0, 300)")
        self.page.wait_for_timeout(300)
        boxes = geometry()
        self.assertGreaterEqual(
            boxes["nav[data-nv-settings-nav]"]["y"],
            boxes["header.nv-top"]["bottom"] - 2,
            "Beim Scrollen rutscht die mobile Navigation unter/über die "
            "sticky Kopfzeile")
        self.assert_no_page_errors()

    def test_mobile_page_has_no_horizontal_scrolling(self):
        """Mobil: die Seite scrollt nicht horizontal (Vertrag „Einheitliches Layout")."""
        self.set_viewport(self.MOBILE["width"], self.MOBILE["height"])
        self.boot()
        self.open_settings()
        metrics = self.page.evaluate(
            "() => ({sw: document.documentElement.scrollWidth,"
            "       iw: window.innerWidth})")
        self.assertLessEqual(
            metrics["sw"], metrics["iw"] + 2,
            "Die Einstellungen-Seite scrollt auf mobil horizontal: "
            + repr(metrics))
        self.assert_no_page_errors()

    def test_wide_nav_is_sticky_left_and_marks_active_section_on_click(self):
        """Breitbild: sticky linke Navigation, Klick setzt aria-current."""
        self.set_viewport(1440, 900)
        self.boot()
        self.open_settings()
        nav = self.page.locator("nav[data-nv-settings-nav]")
        nav.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            "sticky", nav.evaluate("node => getComputedStyle(node).position"),
            "Die Navigation ist auf Breitbild nicht sticky")
        boxes = self.boxes(["nav[data-nv-settings-nav]",
                            "div.nv-settings-content"])
        self.assertLess(
            boxes["nav[data-nv-settings-nav]"]["right"],
            boxes["div.nv-settings-content"]["x"] + 0.5,
            "Die Navigation liegt nicht links vom Inhalt")
        nav_width = boxes["nav[data-nv-settings-nav]"]["w"]
        self.assertGreaterEqual(
            nav_width, 200,
            "Die Navigationsspalte ist schmaler als 14 rem: %r" % nav_width)
        self.assertLessEqual(
            nav_width, 300,
            "Die Navigationsspalte ist breiter als ~16 rem: %r" % nav_width)

        link = nav.locator("[data-nv-ssection-link='access']")
        link.click()
        self.wait_until(
            lambda: link.get_attribute("aria-current") == "true",
            timeout=15, message="Der geklickte Link trägt kein aria-current")
        current = self.page.evaluate(
            """() => Array.from(document.querySelectorAll(
                   'nav[data-nv-settings-nav] [data-nv-ssection-link]'))
                 .filter(n => n.getAttribute('aria-current') === 'true')
                 .map(n => n.getAttribute('data-nv-ssection-link'))""")
        self.assertEqual(
            ["access"], current,
            "Nach dem Klick ist nicht genau die Ziel-Sektion aktiv: "
            + repr(current))
        self.assert_no_page_errors()

    def test_wide_nav_marks_active_section_on_scroll_sync(self):
        """Breitbild: das Scrollen des Inhalts aktualisiert die Markierung."""
        self.set_viewport(1440, 900)
        self.boot()
        self.open_settings()
        self.page.evaluate(
            "document.querySelector(\"section[data-nv-ssection='models']\")"
            ".scrollIntoView({block: 'start'})")
        link = self.page.locator(
            "nav[data-nv-settings-nav] [data-nv-ssection-link='models']")
        self.wait_until(
            lambda: link.get_attribute("aria-current") == "true",
            timeout=15,
            message="Der Scroll-Sync markiert die sichtbare Sektion models "
                    "nicht mit aria-current")
        self.assert_no_page_errors()

    def test_editview_desktop_width_resize_and_session_storage(self):
        """Desktop: ≥ 30 % Breite, Ziehgriff, sessionStorage, Wiederöffnen."""
        self.boot()
        self.open_settings()
        self.open_global_agents_edit()
        aside = self.page.locator("aside[data-nv-editview]")
        self.assertEqual(
            "true", self.page.get_attribute("body", "data-nv-editview-open"),
            "body[data-nv-editview-open] ist beim Öffnen nicht 'true'")
        self.assertEqual(
            1, self.page.locator("[data-nv-editview-scrim]").count(),
            "Der Scrim der Edit-View fehlt")
        box = aside.bounding_box()
        self.assertIsNotNone(box, "Die Edit-View hat keine Kästchen")
        self.assertGreaterEqual(
            box["y"], 55, "Die Edit-View beginnt nicht unter der Kopfzeile")
        self.assertLessEqual(
            box["y"], 90, "Die Edit-View beginnt unerwartet tief")
        ratio = box["width"] / 1400.0
        self.assertGreaterEqual(
            ratio, 0.29,
            "Die Edit-View ist schmaler als ~30 %% des Viewports: %r" % box)

        handle = self.page.locator("[data-nv-editview-resize]")
        handle_box = handle.bounding_box()
        self.assertIsNotNone(handle_box, "Der Ziehgriff fehlt")
        start_y = handle_box["y"] + handle_box["height"] / 2
        start_x = handle_box["x"] + handle_box["width"] / 2
        self.page.mouse.move(start_x, start_y)
        self.page.mouse.down()
        self.page.mouse.move(start_x - 100, start_y, steps=10)
        self.page.mouse.up()
        self.wait_until(
            lambda: (aside.bounding_box() or {}).get("width", 0)
            >= box["width"] + 60,
            timeout=10, message="Der Ziehgriff ändert die Breite nicht")
        new_box = aside.bounding_box()
        stored = self.page.evaluate(
            "() => sessionStorage.getItem('nv-editview-width')")
        self.assertIsNotNone(
            stored, "Die Breite wurde nicht in sessionStorage gespeichert")
        self.assertAlmostEqual(
            float(stored), new_box["width"], delta=30,
            msg="sessionStorage['nv-editview-width'] passt nicht zur Breite")

        self.page.locator("[data-nv-editview-close]").click()
        self.wait_until(
            lambda: not aside.is_visible(), timeout=10,
            message="Der Schließen-Knopf schließt die Edit-View nicht")
        self.open_global_agents_edit()
        reopened = aside.bounding_box()
        self.assertAlmostEqual(
            reopened["width"], new_box["width"], delta=25,
            msg="Die gewählte Breite überlebt das Wiederöffnen nicht")
        self.page.keyboard.press("Escape")

    def test_editview_is_fullscreen_on_mobile_and_escape_closes(self):
        """Mobil: Vollbild-Ansicht ohne Ziehgriff; Escape schließt."""
        self.set_viewport(self.MOBILE["width"], self.MOBILE["height"])
        self.boot()
        self.open_settings()
        self.open_global_agents_edit()
        aside = self.page.locator("aside[data-nv-editview]")
        box = aside.bounding_box()
        self.assertIsNotNone(box)
        self.assertLessEqual(box["x"], 1, "Die mobile Ansicht startet nicht links")
        self.assertLessEqual(box["y"], 1, "Die mobile Ansicht startet nicht oben")
        self.assertGreaterEqual(
            box["width"], self.MOBILE["width"] * 0.98,
            "Die mobile Ansicht ist nicht bildbreit: %r" % box)
        self.assertGreaterEqual(
            box["height"], self.MOBILE["height"] * 0.95,
            "Die mobile Ansicht ist nicht bildhoch: %r" % box)
        self.assertFalse(
            self.page.locator("[data-nv-editview-resize]").is_visible(),
            "Auf Mobil ist der Ziehgriff ausgeblendet")
        self.page.keyboard.press("Escape")
        self.wait_until(
            lambda: self.page.get_attribute("body", "data-nv-editview-open")
            != "true", timeout=10, message="Escape schließt die Edit-View nicht")
        self.assertFalse(
            aside.is_visible(), "Die Edit-View ist nach Escape sichtbar")
        self.assert_no_page_errors()


class GlobalAgentsSectionTest(GH57SettingsBrowserTest):
    def test_section_is_flat_with_hint_and_editview_editor(self):
        """Flache Sektion, Erklärung, Bearbeiten öffnet Edit-View (rows ≥ 16)."""
        self.boot()
        self.open_settings()
        section = self.section("global-agents")
        self.assertEqual(
            0, section.locator("details").count(),
            "Die Sektion global-agents bleibt details-verschachtelt")
        hint = section.locator("[data-nv-global-agents-hint]")
        hint.wait_for(state="visible", timeout=20000)
        self.assertTrue(
            (hint.inner_text() or "").strip(),
            "Die Erklärung zur globalen AGENTS.md ist leer")
        aside = self.open_global_agents_edit()
        textarea = aside.locator("textarea[data-nv-agents-text]")
        textarea.wait_for(state="visible", timeout=20000)
        rows = textarea.evaluate(
            "node => parseInt(node.getAttribute('rows') || '0', 10)"
            " || node.rows")
        self.assertGreaterEqual(
            rows, 16, "textarea[data-nv-agents-text] hat weniger als 16 rows")
        self.assertIn(
            "GH57-GLOBAL-RULE", textarea.input_value(),
            "Der Editor ist nicht mit dem Dateiinhalt vorbelegt")
        self.page.keyboard.press("Escape")

    def test_missing_global_agents_file_offers_create_only(self):
        """Fehlt die Datei: Anlegen-Knopf, danach Editor und kein Anlegen-Knopf."""
        self.global_agents.unlink(missing_ok=True)
        self.boot()
        self.open_settings()
        section = self.section("global-agents")
        create = section.locator(
            "button[data-nv-action='global-agents-create']")
        create.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            0, section.locator(
                "button[data-nv-action='global-agents-edit']").count(),
            "Bei fehlender Datei gibt es einen Bearbeiten-Knopf")
        create.click()
        self.wait_until(
            lambda: self.global_agents.is_file(), timeout=20,
            message="Die globale AGENTS.md wurde nicht angelegt")
        aside = self.page.locator("aside[data-nv-editview]")
        textarea = aside.locator("textarea[data-nv-agents-text]")
        textarea.wait_for(state="visible", timeout=20000)
        self.assertTrue(
            (textarea.input_value() or "").strip(),
            "Der Editor ist nach dem Anlegen nicht vorbelegt")
        self.wait_until(
            lambda: self.page.locator(
                "button[data-nv-action='global-agents-create']").count() == 0,
            timeout=15, message="Der Anlegen-Knopf bleibt stehen")

    def test_save_writes_file_with_digest_and_toast(self):
        """Speichern: POST mit Text + geladener Prüfsumme, Datei, Toast."""
        self.boot()
        self.open_settings()
        initial = self.api_json("/api/global_agents_file")
        self.assertTrue(initial.get("digest"), "Die API liefert keinen Digest")
        self.open_global_agents_edit()
        textarea = self.page.locator(
            "aside[data-nv-editview] textarea[data-nv-agents-text]")
        new_text = GLOBAL_AGENTS_TEXT_gh57 + "Neue globale Regel 4711.\n"
        textarea.fill(new_text)
        self.page.locator(
            "aside[data-nv-editview] button[data-nv-action='agents-save']"
            ).click()
        self.wait_for_post(
            "/api/global_agents_file",
            lambda p: p.get("action") == "save",
            message="Es wurde kein POST action=save gesendet")
        payload = [p for p in self.posts_to("/api/global_agents_file")
                   if p.get("action") == "save"][-1]
        self.assertEqual(new_text, payload.get("text"),
                         "Der POST trägt nicht den neuen Text")
        self.assertEqual(
            initial["digest"], payload.get("digest"),
            "Der POST sendet nicht die geladene Prüfsumme")
        self.wait_until(
            lambda: "Neue globale Regel 4711"
            in self.global_agents.read_text(encoding="utf-8"),
            timeout=20, message="Die Datei wurde nicht geschrieben")
        self.wait_until(
            lambda: re.search(r"gespeichert|saved", self.toast_text(), re.I)
            is not None, timeout=20,
            message="Das Speichern bestätigt nicht per Toast: "
                    + repr(self.toast_text()))

    def test_backup_restore_and_project_rows(self):
        """Backup/Restore im Fuß; Projektzeilen öffnen den Projekt-Editor."""
        self.boot()
        self.open_settings()
        self.open_global_agents_edit()
        aside = self.page.locator("aside[data-nv-editview]")
        aside.locator("button[data-nv-action='agents-backup']").click()
        self.wait_for_post(
            "/api/global_agents_file", lambda p: p.get("action") == "backup",
            message="Es wurde kein Backup-POST gesendet")
        select = aside.locator("[data-nv-agents-backup-select]")
        self.wait_until(
            lambda: select.count() == 1
            and select.evaluate(
                "node => node.options.length") >= 1,
            timeout=20, message="Die Restore-Auswahl bietet keine Sicherung an")
        select.select_option(index=0)
        aside.locator("button[data-nv-action='agents-restore']").click()
        self.assertTrue(
            self.confirm_in_context(),
            "Der Restore fragt nicht über NV.confirmView ab")
        self.wait_for_post(
            "/api/global_agents_file",
            lambda p: p.get("action") == "restore" and p.get("confirm") is True,
            message="Der Restore sendet keinen bestätigten POST")
        self.page.keyboard.press("Escape")

        row = self.page.locator("[data-nv-agents-file-row='proj']")
        row.wait_for(state="visible", timeout=20000)
        row.locator("button[data-nv-action='agents-file-edit']").click()
        aside = self.page.locator("aside[data-nv-editview]")
        aside.wait_for(state="visible", timeout=20000)
        textareas = aside.locator("textarea")
        self.assertGreaterEqual(
            textareas.count(), 2,
            "Der Projekt-Editor bietet nicht zwei Felder (before/after)")
        self.assertTrue(
            re.search(r"verwalteten block|managed block",
                      (aside.inner_text() or ""), re.I),
            "Der Projekt-Editor weist nicht auf den verwalteten Block hin")
        self.assert_no_page_errors()


class AccessSectionTest(GH57SettingsBrowserTest):
    def test_restart_note_uses_plain_wording_without_ui_json(self):
        """Neuer Hinweistext ohne Techniker-Jargon (Ticket: Satz ersetzen)."""
        self.boot()
        self.open_settings()
        note = self.section("access").locator("[data-nv-restart-note]")
        note.wait_for(state="visible", timeout=20000)
        text = (note.inner_text() or "").strip()
        self.assertTrue(text, "Der Neustart-Hinweis ist leer")
        self.assertRegex(
            text, re.compile(r"neustart|restart", re.I),
            "Der Hinweis nennt den Neustart nicht: " + repr(text))
        self.assertNotIn(
            "ui.json", text,
            "Der Hinweis verwendet weiterhin den technischen ui.json-Satz")

    def test_restart_button_asks_confirmation_and_post_is_intercepted(self):
        """Bestätigung via NV.confirmView; POST abgefangen, kein echter Neustart.

        Dokumentierte Wahl: ``page.route`` fängt POST /api/security ab und
        antwortet ``ok:false`` — der Server wird im Test nie wirklich neu
        gestartet; geprüft wird der gesendete Auftrag.
        """
        self.restart_posts = []
        native_dialogs = []

        def on_dialog(dialog):
            native_dialogs.append(dialog.type)
            dialog.dismiss()

        def intercept(route, request):
            if request.method == "POST":
                try:
                    payload = json.loads(request.post_data or "{}")
                except ValueError:
                    payload = {}
                self.restart_posts.append(payload)
                route.fulfill(status=200, content_type="application/json",
                              body=json.dumps(
                                  {"ok": False,
                                   "message": "vom Test blockiert"}))
                return
            route.continue_()

        self.page.on("dialog", on_dialog)
        self.page.route("**/api/security", intercept)
        self.boot()
        self.open_settings()
        button = self.section("access").locator(
            "button[data-nv-action='dashboard-restart']")
        button.wait_for(state="visible", timeout=20000)
        button.click()
        context_panel = self.page.locator("aside[data-nv-context]")
        self.wait_until(
            lambda: context_panel.count() == 1 and context_panel.is_visible(),
            timeout=15,
            message="Der Neustart-Knopf fragt nicht per NV.confirmView ab")
        self.assertTrue(
            self.confirm_in_context(),
            "Die Bestätigung bietet keinen Bestätigen-Knopf")
        self.wait_until(
            lambda: any(p.get("action") == "restart"
                        for p in self.restart_posts),
            timeout=15, message="Es wurde kein Neustart-POST gesendet")
        self.assertEqual(
            [], native_dialogs,
            "Die Bestätigung nutzt einen nativen window.confirm-Dialog")
        status, _body = self.api_get("/api/health")
        self.assertEqual(
            200, status,
            "Der Server wurde trotz Abfangens des POSTs beendet")
        self.assert_no_page_errors()


class FeaturesSectionTest(GH57SettingsBrowserTest):
    def test_feature_toggle_keeps_scroll_position_and_render_count(self):
        """Feature-Umschalten: kein Scroll-Sprung, kein Voll-Neurender."""
        self.boot()
        self.open_settings()
        self.page.evaluate(
            "window.scrollTo(0, document.documentElement.scrollHeight)")
        self.page.wait_for_timeout(300)
        scroll_before = self.page.evaluate("() => window.scrollY")
        self.assertGreater(scroll_before, 0,
                           "Vorbedingung: die Seite wurde nicht gescrollt")
        render_before = self.nv_render_count()
        toggle = self.page.locator("input[data-nv-feature='gates']")
        toggle.evaluate("node => node.click()")
        section = self.page.locator("section[data-nv-ssection='gates']")
        nav_link = self.page.locator(
            "nav[data-nv-settings-nav] [data-nv-ssection-link='gates']")
        self.wait_until(
            lambda: section.count() == 0 or not section.is_visible(),
            timeout=15, message="Die gates-Sektion verschwindet nicht")
        self.wait_until(
            lambda: nav_link.count() == 0 or not nav_link.is_visible(),
            timeout=15, message="Der Navigations-Eintrag verschwindet nicht")
        self.assertEqual(
            scroll_before, self.page.evaluate("() => window.scrollY"),
            "Das Umschalten setzte die Scroll-Position zurück")
        self.assertEqual(
            render_before, self.nv_render_count(),
            "Das Feature-Umschalten in den Einstellungen vollneu-renderd")
        toggle.evaluate("node => node.click()")
        self.wait_until(
            lambda: section.count() > 0 and section.is_visible(),
            timeout=15, message="Die gates-Sektion erscheint nicht wieder")
        self.assertEqual(
            scroll_before, self.page.evaluate("() => window.scrollY"),
            "Das Wiedereinschalten verschob die Scroll-Position")
        self.assert_no_page_errors()


class LimitsSectionTest(GH57SettingsBrowserTest):
    def test_single_toggle_posts_mode_without_rerender(self):
        """Kompakte Limits-Sektion: ein Schalter, POST, Toast, kein Re-Render."""
        self.boot()
        self.open_settings()
        section = self.section("limits")
        self.assertEqual(
            0, self.page.locator(
                "button[data-nv-action='limits-continue'],"
                " button[data-nv-action='limits-stop']").count(),
            "Die Limits-Sektion hat noch die alten Modus-Knöpfe")
        help_box = section.locator("[data-nv-limits-help]")
        help_box.wait_for(state="visible", timeout=20000)
        self.assertTrue(
            (help_box.inner_text() or "").strip(),
            "Die Erklärung zu Fortsetzen/Stopp fehlt")
        toggle = section.locator("input[type=checkbox][data-nv-limits-mode]")
        toggle.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            1, toggle.count(),
            "Es gibt nicht genau einen Limits-Schalter")
        self.assertEqual(
            "label.nv-switch-row",
            toggle.evaluate(
                "node => { const l = node.closest('label');"
                " return l ? l.className : ''; }"),
            "Der Schalter liegt nicht in label.nv-switch-row")
        mode = self.api_json("/api/limits").get("mode")
        self.assertEqual(
            mode == "continue", toggle.is_checked(),
            "Der Schalter spiegelt den Modus %r nicht" % (mode,))

        render_before = self.nv_render_count()
        toggle.click()
        expected = "continue" if mode != "continue" else "stop"
        self.wait_for_post(
            "/api/limits", lambda p: p.get("action") == expected,
            message="Der Schalter sendet kein POST /api/limits "
                    "{action:%r}" % expected)
        self.wait_until(
            lambda: self.api_json("/api/limits").get("mode") == expected,
            timeout=20, message="GET /api/limits bestätigt den Modus nicht")
        self.wait_until(
            lambda: re.search(r"fortsetz|stopp|continue|stop",
                              self.toast_text(), re.I) is not None,
            timeout=15, message="Der Moduswechsel bestätigt nicht per Toast")
        self.assertEqual(
            render_before, self.nv_render_count(),
            "Der Limits-Schalter vollneu-renderd")
        self.assertEqual(
            expected == "continue", toggle.is_checked(),
            "Der Schalter zeigt den neuen Modus nicht")


class GatesSectionTest(GH57SettingsBrowserTest):
    def test_global_context_is_default_with_editable_values_and_translated_origin(self):
        """Standardkontext global; Werte editierbar; Herkunft übersetzt."""
        self.boot()
        self.open_settings()
        section = self.section("gates")
        select = section.locator("select[data-nv-gates-project]")
        select.wait_for(state="visible", timeout=20000)
        self.assertEqual(
            "global", select.input_value(),
            "Die Projektauswahl startet nicht im Global-Kontext")
        table = section.locator("table[data-nv-gates-table]")
        table.wait_for(state="visible", timeout=20000)
        rows = table.locator("tr[data-nv-gate]")
        self.wait_until(
            lambda: rows.count() >= 1, timeout=20,
            message="Die Gates-Tabelle hat keine Zeilen")
        for index in range(rows.count()):
            row = rows.nth(index)
            with self.subTest(gate=row.get_attribute("data-nv-gate")):
                value = row.locator("[data-nv-gate-value]")
                self.assertEqual(
                    1, value.count(), "Eine Zeile hat kein Wert-Feld")
                self.assertTrue(
                    value.first.evaluate(
                        "node => (node.tagName === 'INPUT'"
                        " || node.tagName === 'SELECT')"
                        " && !node.readOnly && !node.disabled"),
                    "Der Wert im Global-Kontext ist nicht editierbar")
                origin = row.locator("[data-nv-gate-origin]")
                self.assertEqual(
                    1, origin.count(), "Eine Zeile hat keine Herkunft")
                self.assertTrue(
                    (origin.first.inner_text() or "").strip(),
                    "Die Origin-Spalte ist leer (alter Fehler)")

        widths = self.page.evaluate(
            """() => {
                 const s = document.querySelector(
                   "section[data-nv-ssection='gates']");
                 const t = s.querySelector("table[data-nv-gates-table]");
                 const cs = getComputedStyle(s);
                 const inner = s.clientWidth
                   - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
                 return {inner: inner, table: t.getBoundingClientRect().width};
               }""")
        self.assertGreaterEqual(
            widths["table"], 0.9 * widths["inner"],
            "Die Gates-Tabelle nutzt nicht die volle Breite: " + repr(widths))

        origins_en = [
            (rows.nth(i).locator("[data-nv-gate-origin]").first.inner_text()
             or "").strip() for i in range(rows.count())]
        self.api_post("/api/language", {"language": "de"})
        try:
            self.page.reload()
            self.open_settings()
            rows = self.section("gates").locator(
                "table[data-nv-gates-table] tr[data-nv-gate]")
            self.wait_until(
                lambda: rows.count() >= 1, timeout=20,
                message="Die Gates-Tabelle fehlt nach dem Sprachwechsel")
            origins_de = [
                (rows.nth(i).locator("[data-nv-gate-origin]").first.inner_text()
                 or "").strip() for i in range(rows.count())]
        finally:
            self.api_post("/api/language", {"language": "en"})
        self.assertTrue(
            any(text for text in origins_de),
            "Die Herkunft ist im Deutschen leer")
        self.assertTrue(
            any(a != b for a, b in zip(origins_en, origins_de)),
            "Die Herkunft wird nicht übersetzt: en=%r de=%r"
            % (origins_en, origins_de))

    def test_project_context_readonly_global_effective_preview_and_save_under_table(self):
        """Projektkontext: global nur-lesend, Wirksam-Vorschau, Aktionen unten."""
        self.boot()
        self.open_settings()
        section = self.section("gates")
        select = section.locator("select[data-nv-gates-project]")
        select.select_option(PROJECT)
        table = section.locator("table[data-nv-gates-table]")
        rows = table.locator("tr[data-nv-gate]")
        self.wait_until(
            lambda: rows.locator("[data-nv-gate-override]").count() >= 1,
            timeout=20,
            message="Im Projektkontext erscheinen keine Override-Felder")
        for index in range(rows.count()):
            row = rows.nth(index)
            with self.subTest(gate=row.get_attribute("data-nv-gate")):
                readonly = row.locator("[data-nv-gate-global]")
                self.assertEqual(
                    1, readonly.count(),
                    "Eine Zeile zeigt den globalen Wert nicht nur-lesend")
                if readonly.first.evaluate(
                        "node => node.tagName === 'INPUT'"
                        " || node.tagName === 'SELECT'"):
                    self.assertTrue(
                        readonly.first.evaluate(
                            "node => node.readOnly || node.disabled"),
                        "Der globale Wert ist im Projektkontext editierbar")
                self.assertEqual(
                    1, row.locator("[data-nv-gate-effective]").count(),
                    "Eine Zeile hat keine Wirksam-Vorschau")
                self.assertEqual(
                    1, row.locator("[data-nv-gate-origin]").count(),
                    "Eine Zeile hat keine Herkunft")

        retries = table.locator("tr[data-nv-gate='retries']")
        override = retries.locator("[data-nv-gate-override]")
        effective_before = (
            retries.locator("[data-nv-gate-effective]").inner_text() or "")
        posts_before = len(self.posts_to("/api/gates"))
        override.fill("5")
        self.wait_until(
            lambda: "5" in (retries.locator(
                "[data-nv-gate-effective]").inner_text() or ""),
            timeout=10,
            message="Die Wirksam-Vorschau zeigt den getipsten Wert nicht sofort")
        self.assertEqual(
            posts_before, len(self.posts_to("/api/gates")),
            "Das Tippen des Projektwerts sendet bereits einen POST")
        self.assertNotEqual(
            effective_before,
            retries.locator("[data-nv-gate-effective]").inner_text(),
            "Die Wirksam-Vorschau ändert sich beim Tippen nicht")

        expected_values = {}
        for index in range(rows.count()):
            row = rows.nth(index)
            expected_values[row.get_attribute("data-nv-gate")] = (
                row.locator("[data-nv-gate-override]").input_value() or "")
        save = section.locator("button[data-nv-action='gates-save']")
        order = table.evaluate(
            """(table, saveSel) => {
                 const save = document.querySelector(saveSel);
                 return save ? Boolean(
                   table.compareDocumentPosition(save)
                   & Node.DOCUMENT_POSITION_FOLLOWING) : false;
               }""",
            "section[data-nv-ssection='gates'] "
            "button[data-nv-action='gates-save']")
        self.assertTrue(
            order, "Die Aktionszeile liegt nicht unterhalb der Tabelle")
        save.click()
        self.wait_for_post(
            "/api/gates", lambda p: p.get("project") == PROJECT,
            message="Es wurde kein POST /api/gates mit dem Projekt gesendet")
        payload = [p for p in self.posts_to("/api/gates")
                   if p.get("project") == PROJECT][-1]
        self.assertEqual(
            expected_values, payload.get("values"),
            "Der POST enthält nicht alle Zeilenschlüssel mit den Werten")
        self.assertEqual(
            1, section.locator("button[data-nv-action='gates-reset']").count(),
            "Der Reset-Knopf fehlt im Projektkontext")
        self.assert_no_page_errors()


class ModelsSectionTest(GH57SettingsBrowserTest):
    def test_details_collapsed_refresh_always_visible_and_stand_date_after_refresh(self):
        """Eingeklappt, Aktualisieren immer sichtbar, Stand-Datum nach Refresh."""
        self.boot()
        self.open_settings()
        section = self.section("models")
        details = section.locator("details[data-nv-models]")
        details.wait_for(state="attached", timeout=20000)
        self.assertFalse(
            details.evaluate("node => node.open"),
            "details[data-nv-models] ist standardmäßig aufgeklappt")
        refresh = section.locator(
            "button[data-nv-action='models-refresh']")
        self.assertTrue(
            refresh.is_visible(),
            "Der Aktualisieren-Knopf ist im eingeklappten Zustand nicht "
            "sichtbar (Sektionskopf)")
        self.assertEqual(
            0, section.locator("[data-nv-models-hint]").count(),
            "Der Beschreibungstext zum Katalog ist nicht entfallen")
        section_text = section.inner_text() or ""
        self.assertNotRegex(
            section_text, re.compile(r"referenz", re.I),
            "Die Katalog-Beschreibung („Der Katalog ist nur eine Referenz…“) "
            "existiert weiterhin")
        stand = section.locator("[data-nv-models-stand]")
        stand.wait_for(state="attached", timeout=20000)

        cache = self.state_dir / "models-cache.json"
        self.assertFalse(
            cache.exists(), "Vorbedingung: der Modell-Cache existiert bereits")
        refresh.click()
        self.wait_for_post(
            "/api/agents", lambda p: p.get("action") == "refresh_models",
            message="Der Aktualisieren-Knopf sendet kein POST "
                    "{action:'refresh_models'}")
        self.wait_until(
            lambda: cache.exists(), timeout=30,
            message="Der Modell-Cache models-cache.json wurde nicht geschrieben")
        cache_data = json.loads(cache.read_text(encoding="utf-8"))
        self.assertTrue(
            cache_data.get("stand"), "Der Cache trägt kein „stand“-Datum")
        self.wait_until(
            lambda: any(ch.isdigit()
                        for ch in (stand.inner_text() or "")),
            timeout=20,
            message="[data-nv-models-stand] zeigt nach der Aktualisierung "
                    "kein Datum: " + repr(stand.inner_text()))
        self.assert_no_page_errors()

    def test_model_row_opens_editview_detail(self):
        """Modellzeile öffnet die Edit-View-Detailansicht, keine Detailzeile."""
        self.boot()
        self.open_settings()
        section = self.section("models")
        refresh = section.locator("button[data-nv-action='models-refresh']")
        refresh.click()
        rows = section.locator("table[data-nv-models-table] tr[data-nv-model]")
        self.wait_until(
            lambda: rows.count() >= 1, timeout=30,
            message="Nach dem Refresh erscheinen keine Modellzeilen")
        rows.first.click()
        aside = self.page.locator("aside[data-nv-editview]")
        aside.wait_for(state="visible", timeout=20000)
        detail = aside.locator("[data-nv-model-detail]")
        detail.wait_for(state="visible", timeout=20000)
        self.assertTrue(
            (detail.inner_text() or "").strip(),
            "Die Modelldetail-Ansicht ist leer")
        self.assertEqual(
            0, section.locator("tr[data-nv-model-detail]").count(),
            "Die Modelldetails liegen weiterhin als eingebettete Zeile")
        self.page.keyboard.press("Escape")

    def test_empty_state_without_model_data(self):
        """Ohne Modelldaten: leerer Zustand mit Hinweis auf Aktualisieren."""
        try:
            self.models_source.write_text("", encoding="utf-8")
            (self.state_dir / "models-cache.json").unlink(missing_ok=True)
            self.boot()
            self.open_settings()
            section = self.section("models")
            empty = section.locator("[data-nv-models-empty]")
            empty.wait_for(state="visible", timeout=30000)
            self.assertTrue(
                (empty.inner_text() or "").strip(),
                "Der leere Zustand erklärt nichts")
            self.assertTrue(
                section.locator(
                    "button[data-nv-action='models-refresh']").is_visible(),
                "Der Aktualisieren-Knopf fehlt im leeren Zustand")
        finally:
            self.models_source.write_text(FAKE_MODELS, encoding="utf-8")


class ProfilesSectionTest(GH57SettingsBrowserTest):
    def profiles_select(self):
        select = self.page.locator("select[data-nv-profiles-select]")
        select.wait_for(state="visible", timeout=20000)
        return select

    def choose_profile(self, name):
        select = self.profiles_select()
        select.select_option(name)
        display = self.page.locator("[data-nv-profile-selected]")
        self.wait_until(
            lambda: display.count() >= 1
            and name in (display.first.inner_text() or ""),
            timeout=15,
            message="Die Auswahl zeigt das gewählte Profil nicht an")

    def role_combobox(self, role):
        return self.page.locator(f"[data-nv-profile-role='{role}']")

    def open_role_list(self, role):
        combo = self.role_combobox(role)
        combo.wait_for(state="visible", timeout=20000)
        combo.locator("input[data-nv-combobox-input]").click()
        options = self.page.locator("li[data-nv-combobox-option]")
        options.first.wait_for(state="visible", timeout=10000)
        return combo, options

    def choose_role_model(self, role, value):
        combo, options = self.open_role_list(role)
        option = self.page.locator(
            "li[data-nv-combobox-option]", has_text=value).first
        option.click()
        self.wait_until(
            lambda: combo.get_attribute("data-nv-value") == value,
            timeout=10, message="Die Combobox übernahm %r nicht" % value)

    def test_select_lists_standard_and_custom_profiles_with_badges(self):
        """Auswahl führt Standard- und Nutzerprofile; Marker und Badges."""
        self.boot()
        self.open_settings()
        select = self.profiles_select()
        values = select.evaluate(
            "node => Array.from(node.options).map(o => o.value)")
        for name in ("default", "free", "mid", "high", "meins"):
            self.assertIn(
                name, values,
                f"Die Profilauswahl bietet {name!r} nicht an: " + repr(values))
        self.choose_profile("default")
        section = self.section("profiles")
        self.assertGreaterEqual(
            section.locator("[data-nv-profile-standard]").count(), 1,
            "Das Standardprofil trägt keinen Standard-Badge")
        self.assertGreaterEqual(
            section.locator("[data-nv-profile-active]").count(), 1,
            "Das aktive Profil trägt keinen Aktiv-Badge")
        self.assertEqual(
            0, section.locator("article[data-nv-profile]").count(),
            "Die Profile erscheinen weiterhin als Karten")
        self.assert_no_page_errors()

    def test_role_comboboxes_with_default_option_and_default_hint(self):
        """Rollen-Comboboxen mit erster Option „Default“ und Modell-Hinweis."""
        self.boot()
        self.open_settings()
        self.choose_profile("free")
        roles = self.page.locator("[data-nv-profile-roles]")
        roles.wait_for(state="visible", timeout=20000)
        combo, options = self.open_role_list("coder")
        first_text = (options.first.inner_text() or "").strip()
        self.assertRegex(
            first_text, re.compile(r"default", re.I),
            "Die erste Combobox-Option heißt nicht „Default“: "
            + repr(first_text))
        options.first.click()
        hint = self.role_combobox("coder").locator(
            "[data-nv-profile-default-hint]")
        hint.wait_for(state="visible", timeout=15000)
        self.assertIn(
            "opencode/test-modell", hint.inner_text(),
            "Der Default-Hinweis nennt nicht das Modell der "
            "Agent-Einstellungen (Default-Kette): "
            + repr(hint.inner_text()))

    def test_default_profile_is_readonly(self):
        """Default-Profil: keine Comboboxen, lesende Spiegelung, Lösch-Schutz."""
        self.boot()
        self.open_settings()
        self.choose_profile("default")
        section = self.section("profiles")
        self.wait_until(
            lambda: section.locator("[data-nv-profile-role]").count() == 0,
            timeout=15,
            message="Das Default-Profil bietet editierbare Comboboxen an")
        self.assertIn(
            "opencode/test-modell", section.inner_text(),
            "Das Default-Profil spiegelt die Agent-Einstellungen nicht lesend")
        delete = section.locator("button[data-nv-action='profile-delete']")
        self.assertTrue(
            delete.count() == 0 or delete.first.is_disabled(),
            "Das Standardprofil darf nicht löschbar sein")

    def test_create_and_delete_custom_profile(self):
        """Nutzerprofil anlegen und entfernen; Standardprofile bleiben."""
        self.boot()
        self.open_settings()
        section = self.section("profiles")
        name_field = section.locator("[data-nv-profile-name]")
        name_field.wait_for(state="visible", timeout=20000)
        name_field.fill("Sonderprofil")
        section.locator("button[data-nv-action='profile-new']").click()
        self.wait_for_post(
            "/api/profiles", lambda p: p.get("action") == "create",
            message="Das Anlegen sendet kein POST {action:'create'}")
        select = self.profiles_select()
        self.wait_until(
            lambda: "Sonderprofil" in select.evaluate(
                "node => Array.from(node.options).map(o => o.value)"),
            timeout=15, message="Das neue Profil erscheint nicht in der Auswahl")
        select.select_option("Sonderprofil")
        delete = section.locator("button[data-nv-action='profile-delete']")
        self.wait_until(
            lambda: delete.count() == 1 and delete.first.is_enabled(),
            timeout=15, message="Das eigene Profil bietet kein aktives Löschen")
        delete.first.click()
        self.assertTrue(
            self.confirm_in_context(),
            "Das Löschen fragt nicht über NV.confirmView ab")
        self.wait_for_post(
            "/api/profiles",
            lambda p: p.get("action") == "delete"
            and p.get("name") == "Sonderprofil",
            message="Das Löschen sendet keinen POST {action:'delete'}")
        self.wait_until(
            lambda: "Sonderprofil" not in select.evaluate(
                "node => Array.from(node.options).map(o => o.value)"),
            timeout=15, message="Das gelöschte Profil bleibt in der Auswahl")

    def test_save_sends_only_selected_profile_and_cancel_discards(self):
        """Save-POST trägt nur das gewählte Profil; Abbrechen verwirft."""
        self.boot()
        self.open_settings()
        self.choose_profile("meins")
        self.choose_role_model("coder", "opencode/neu")
        save = self.section("profiles").locator(
            "button[data-nv-action='profile-save']")
        save.click()
        self.wait_for_post(
            "/api/profiles", lambda p: p.get("action") == "save",
            message="Das Speichern sendet keinen POST {action:'save'}")
        payload = [p for p in self.posts_to("/api/profiles")
                   if p.get("action") == "save"][-1]
        data = payload.get("data") or {}
        self.assertEqual(
            {"meins"}, set((data.get("profile") or {}).keys()),
            "Der Save-POST enthält nicht genau das gewählte Profil: "
            + repr(payload))
        self.assertIn("rollen", data,
                      "Der Save-POST trägt die Rollen nicht: " + repr(payload))

        self.choose_role_model("coder", "opencode/test-modell")
        cancel = self.section("profiles").locator(
            "button[data-nv-action='profile-cancel']")
        cancel.click()
        self.wait_until(
            lambda: self.role_combobox("coder").get_attribute(
                "data-nv-value") == "opencode/neu",
            timeout=15, message="Abbrechen stellt den gespeicherten Wert "
                                "nicht wieder her")
        saves = [p for p in self.posts_to("/api/profiles")
                 if p.get("action") == "save"]
        self.assertEqual(
            1, len(saves), "Abbrechen hat einen weiteren Save-POST gesendet")

    def test_backup_restore_and_apply_with_preview(self):
        """Backup/Restore mit Bestätigung; Anwenden mit Vorschau und Wirkung."""
        self.boot()
        self.open_settings()
        self.choose_profile("meins")
        section = self.section("profiles")
        section.locator("button[data-nv-action='profile-backup']").click()
        self.wait_for_post(
            "/api/profiles", lambda p: p.get("action") == "backup",
            message="Backup sendet keinen POST {action:'backup'}")
        select = section.locator("[data-nv-profile-restore-select]")
        self.wait_until(
            lambda: select.count() == 1 and select.evaluate(
                "node => node.options.length") >= 1,
            timeout=20, message="Die Restore-Auswahl bleibt leer")
        select.select_option(index=0)
        section.locator("button[data-nv-action='profile-restore']").click()
        self.assertTrue(
            self.confirm_in_context(),
            "Der Restore fragt nicht über NV.confirmView ab")
        self.wait_for_post(
            "/api/profiles",
            lambda p: p.get("action") == "restore"
            and p.get("confirm") is True,
            message="Der Restore sendet keinen bestätigten POST")

        section.locator("button[data-nv-action='profile-apply']").click()
        context_panel = self.page.locator("aside[data-nv-context]")
        self.wait_until(
            lambda: context_panel.count() == 1 and context_panel.is_visible(),
            timeout=15, message="Das Anwenden zeigt keine Vorschau")
        preview_text = context_panel.inner_text() or ""
        self.assertIn(
            "opencode/", preview_text,
            "Die Vorschau nennt kein aufgelöstes Modell: " + repr(preview_text))
        self.assertTrue(
            self.confirm_in_context(),
            "Die Vorschau bietet kein Bestätigen an")

        def applied():
            try:
                path = self.state_dir / "profiles.json"
                return json.loads(path.read_text(encoding="utf-8")).get(
                    "aktiv") == "meins"
            except (OSError, ValueError):
                return False

        self.wait_until(
            applied, timeout=30,
            message="Nach Bestätigen ist „meins“ nicht aktiv")
        self.wait_for_post(
            "/api/profiles", lambda p: p.get("action") == "use",
            message="Das Anwenden sendet keinen POST {action:'use'}")
        self.wait_until(
            lambda: "opencode/vibe-modell"
            in self.tester_agent.read_text(encoding="utf-8"),
            timeout=30, message="Der Tester-Agent hat das Profilmodell "
                                "nicht erhalten")
        self.assert_no_page_errors()


class McpSectionTest(GH57SettingsBrowserTest):
    MCP_FIELDS = (
        "[data-nv-mcp-name]", "[data-nv-mcp-scope]", "[data-nv-mcp-type]",
        "[data-nv-mcp-command]", "[data-nv-mcp-env]", "[data-nv-mcp-cwd]",
        "[data-nv-mcp-url]", "[data-nv-mcp-headers]",
        "[data-nv-mcp-noauth]", "[data-nv-mcp-enabled]",
        "[data-nv-mcp-timeout]")

    def test_add_opens_editview_form_and_saves_via_create(self):
        """Hinzufügen öffnet das Edit-View-Formular; Speichern nutzt create."""
        self.boot()
        self.open_settings()
        section = self.section("mcp")
        add = section.locator("button[data-nv-action='mcp-add']")
        add.wait_for(state="visible", timeout=20000)
        add.click()
        aside = self.page.locator("aside[data-nv-editview]")
        aside.wait_for(state="visible", timeout=20000)
        for selector in self.MCP_FIELDS:
            with self.subTest(field=selector):
                self.assertEqual(
                    1, aside.locator(selector).count(),
                    f"Das MCP-Formular fehlt das Feld {selector}")
        type_select = aside.locator("[data-nv-mcp-type]")
        self.assertIn(
            "local", type_select.evaluate(
                "node => Array.from(node.options).map(o => o.value)"),
            "Der Typ local fehlt")
        self.assertIn(
            "remote", type_select.evaluate(
                "node => Array.from(node.options).map(o => o.value)"),
            "Der Typ remote fehlt")
        for selector in ("mcp-save", "mcp-test"):
            self.assertEqual(
                1, aside.locator(f"button[data-nv-action='{selector}']").count(),
                f"Der Fuß bietet {selector} nicht an")

        aside.locator("[data-nv-mcp-name]").fill("gh57-server")
        aside.locator("[data-nv-mcp-type]").select_option("local")
        aside.locator("[data-nv-mcp-command]").fill("echo\ngh57")
        aside.locator("button[data-nv-action='mcp-save']").click()
        self.wait_for_post(
            "/api/mcp",
            lambda p: p.get("action") == "save" and p.get("create") is True,
            message="Das Anlegen sendet kein POST {action:'save', create:true}")
        self.assertEqual(
            [], [p for p in self.posts_to("/api/mcp")
                 if p.get("action") == "set"],
            "Das Anlegen verwendet weiterhin die ungültige action 'set'")
        payloads = [json.dumps(p) for p in self.posts_to("/api/mcp")]
        self.assertTrue(
            any("gh57-server" in text for text in payloads),
            "Der POST nennt den neuen Server nicht: " + repr(payloads))
        self.wait_until(
            lambda: self.section("mcp").locator(
                "article[data-nv-mcp-server='gh57-server']").count() == 1,
            timeout=20, message="Die neue Server-Karte erscheint nicht")
        self.assert_no_page_errors()

    def test_state_badge_visible_on_mobile_without_overlap(self):
        """Mobil: Status-Badge immer sichtbar und ohne Überlappung."""
        self.set_viewport(390, 844)
        self.boot()
        self.open_settings()
        cards = self.page.locator("article[data-nv-mcp-server]")
        cards.first.wait_for(state="visible", timeout=20000)
        self.assertGreaterEqual(
            cards.count(), 1, "Vorbedingung: keine MCP-Karten")
        badge = cards.first.locator("[data-nv-mcp-state]")
        self.assertTrue(
            badge.is_visible(), "Der Status-Badge ist auf Mobil unsichtbar")
        self.assertTrue(
            (badge.inner_text() or "").strip(),
            "Der Status-Badge hat keinen Text")
        geometry = self.page.evaluate(
            """() => {
                 const card = document.querySelector(
                   "article[data-nv-mcp-server]");
                 const badge = card.querySelector("[data-nv-mcp-state]");
                 const btn = card.querySelector(
                   "button[data-nv-action='mcp-toggle']");
                 const rect = n => { const b = n.getBoundingClientRect();
                   return {l: b.left, r: b.right, t: b.top, b: b.bottom}; };
                 return {badge: rect(badge),
                         btn: btn ? rect(btn) : null,
                         vw: window.innerWidth};
               }""")
        box = geometry["badge"]
        self.assertGreaterEqual(box["l"], 0, "Der Badge ragt links heraus")
        self.assertLessEqual(
            box["r"], geometry["vw"] + 0.5,
            "Der Badge ragt rechts aus dem Viewport")
        button = geometry["btn"]
        if button:
            overlap_x = min(box["r"], button["r"]) - max(box["l"], button["l"])
            overlap_y = min(box["b"], button["b"]) - max(box["t"], button["t"])
            self.assertLessEqual(
                min(overlap_x, overlap_y), 0.5,
                "Der Status-Badge überlappt die Karten-Knöpfe: "
                + repr(geometry))


class HarnessSectionTest(GH57SettingsBrowserTest):
    def test_status_grid_stacks_on_mobile_with_install_button(self):
        """Responsives Harness-Raster; Installationsknopf für Fehlende."""
        self.boot()
        self.open_settings()
        section = self.section("harness")
        status = section.locator("[data-nv-harness-status]")
        status.wait_for(state="visible", timeout=20000)
        cards = status.locator(".nv-card")
        self.wait_until(
            lambda: cards.count() >= 2, timeout=20,
            message="Der Harness-Status zeigt nicht je Harness eine Karte")
        text = section.inner_text() or ""
        self.assertIn("opencode", text)
        self.assertIn("pi", text.lower(),
                      "Der Harness-Status nennt Pi nicht")
        install = section.locator(
            "button[data-nv-action='harness-install']")
        self.assertTrue(
            install.first.is_visible(),
            "Der Installationsknopf für die fehlende Installation fehlt")
        self.assertEqual(
            1, section.locator(
                "[data-nv-harness-install-feedback]").count(),
            "Der Feedback-Bereich für Installationen fehlt")

        self.set_viewport(390, 844)
        self.page.wait_for_timeout(300)
        rects = self.page.evaluate(
            """() => Array.from(document.querySelectorAll(
                   "[data-nv-harness-status] > .nv-card"))
                 .map(n => { const b = n.getBoundingClientRect();
                   return {top: b.top, bottom: b.bottom}; })""")
        for index in range(1, len(rects)):
            self.assertGreaterEqual(
                rects[index]["top"], rects[index - 1]["bottom"] - 1,
                "Auf Mobil überlappen die Harness-Karten: " + repr(rects))
        self.assert_no_page_errors()


class I18nTest(GH57SettingsBrowserTest):
    def test_new_labels_are_translated_to_english(self):
        """Neue Labels sind mit aktiver Sprache en englisch (SPEC.md)."""
        self.boot()
        self.open_settings()
        restart = self.section("access").locator(
            "button[data-nv-action='dashboard-restart']")
        self.assertRegex(
            (restart.inner_text() or "").strip(), re.compile(r"restart", re.I),
            "Der Neustart-Knopf ist nicht englisch beschriftet: "
            + repr(restart.inner_text()))
        add = self.section("mcp").locator(
            "button[data-nv-action='mcp-add']")
        self.assertRegex(
            (add.inner_text() or "").strip(), re.compile(r"add", re.I),
            "Der MCP-Hinzufügen-Knopf ist nicht englisch beschriftet: "
            + repr(add.inner_text()))

        section = self.section("models")
        stand = section.locator("[data-nv-models-stand]")
        stand.wait_for(state="attached", timeout=20000)
        section.locator(
            "button[data-nv-action='models-refresh']").click()
        self.wait_until(
            lambda: any(ch.isdigit() for ch in (stand.inner_text() or "")),
            timeout=30, message="Vorbedingung: kein Stand-Datum nach Refresh")
        text_en = (stand.inner_text() or "").strip()
        self.assertRegex(
            text_en, re.compile(r"updated|last", re.I),
            "Die Aktualisierungs-Zeile ist nicht englisch: " + repr(text_en))
        try:
            self.api_post("/api/language", {"language": "de"})
            self.page.reload()
            self.open_settings()
            text_de = (
                self.section("models").locator(
                    "[data-nv-models-stand]").inner_text() or "").strip()
        finally:
            self.api_post("/api/language", {"language": "en"})
        self.assertRegex(
            text_de, re.compile(r"aktualisier|stand", re.I),
            "Die Aktualisierungs-Zeile ist nicht deutsch: " + repr(text_de))
        self.assertNotEqual(
            text_en, text_de,
            "Die Aktualisierungs-Zeile ist nicht übersetzt")
        self.assert_no_page_errors()


if __name__ == "__main__":
    unittest.main()
