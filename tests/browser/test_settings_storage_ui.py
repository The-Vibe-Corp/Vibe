"""Persistente Nutzer-Einstellungen: Speichern, Wiederherstellen, Migration, Fallback.

Aufruf: python3 -m unittest tests.browser.test_settings_storage_ui -v

Isolierte Fixture: temporaerer VIBE-Root, eigenes VIBE_STATE/HOME, eigene Ports,
Fake-opencode ohne echte Modellaufrufe. Der Web-Server wird vor jedem Test neu
gestartet, damit kein serverseitiger Zustand aus einem vorherigen Fall in den
naechsten hineinwirkt. Der Neustart mit demselben State-Verzeichnis in
``test_settings_restored_after_restart_in_fresh_context`` simuliert zusätzlich
das erneute Oeffnen der Anwendung bzw. ein Update.
"""

import json
import os
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

_BROWSERS = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"

ACCENT_IDS = (
    "blue", "teal", "cyan", "green", "lime", "yellow", "amber", "orange",
    "red", "pink", "violet", "indigo",
)
THEME = "dark"
ACCENT = "teal"
PROJECT_NAME = "alpha-projekt"
AGENT_NAME = "tester"
AGENT_SCOPE = "global"

FAKE_OPENCODE = """#!/usr/bin/env bash
case "$1" in
  --version)
    printf 'opencode v2.1.4\\n'
    exit 0
    ;;
  models)
    printf 'opencode/vibe-modell\\nopencode/test-modell\\n'
    exit 0
    ;;
esac
exit 2
"""

GLOBAL_AGENT = """---
description: Globaler Agent
mode: subagent
model: opencode/vibe-modell
permission:
  read: allow
  edit: deny
---

Globaler Prompt.
"""


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """opencode-Attrappe: antwortet leer, startet keine Modelle."""

    def log_message(self, *args):
        return

    def do_GET(self):
        body = json.dumps({"data": []}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _names(items):
    """favorite_projects als Namen lesen (String- oder Objektliste zulaessig)."""
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            result.append(str(item.get("name") or item.get("id") or ""))
    return result


def _agent_pairs(items):
    """favorite_agents als (scope, name)-Paare lesen."""
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        if isinstance(item, str):
            result.append((None, item))
        elif isinstance(item, dict):
            result.append((item.get("scope"),
                           str(item.get("name") or item.get("id") or "")))
    return result


class SettingsStorageBrowserTest(unittest.TestCase):
    """Einstellungen am Dateisystem und in der Oberfläche Ende-zu-Ende."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        for name in (PROJECT_NAME, "beta-projekt"):
            project = cls.root / name
            (project / ".vibe").mkdir(parents=True)
            (project / ".vibe" / "project.env").write_text(
                "TYPE=generic\n", encoding="utf-8")
            (project / "FEEDBACK.md").write_text("# FEEDBACK\n", encoding="utf-8")
            (project / "TICKETS.md").write_text("# TICKETS\n", encoding="utf-8")
        agents_dir = cls.root / "home" / ".config" / "opencode" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "tester.md").write_text(GLOBAL_AGENT, encoding="utf-8")
        fake_bin = cls.root / "fakebin"
        fake_bin.mkdir()
        fake = fake_bin / "opencode"
        fake.write_text(FAKE_OPENCODE, encoding="utf-8")
        fake.chmod(0o755)
        (cls.root / "tmp").mkdir(parents=True, exist_ok=True)
        cls.state_dir = cls.root / "_state"
        cls.state_dir.mkdir(parents=True)
        cls.runtime = cls.root / "_runtime"
        cls.runtime.mkdir(parents=True)
        cls.tmux_dir = cls.root / "tmux"
        cls.tmux_dir.mkdir(parents=True)

        cls.port = free_port()
        cls.oc_port = free_port()
        cls._fake_http = ThreadingHTTPServer(
            ("127.0.0.1", cls.oc_port), _FakeOpenCodeHandler)
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
            "VIBE_RUNTIME": str(cls.runtime),
            "HOME": str(cls.root / "home"),
            "TMPDIR": str(cls.root / "tmp"),
            "TMUX_TMPDIR": str(cls.tmux_dir),
            "VIBE_CONFIG_FILE": str(
                cls.root / "home" / ".config" / "vibe" / "config.json"),
            "PATH": str(fake_bin) + os.pathsep + env.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        cls.env = env
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)
        cls.server_seq = 0
        cls.server_log = None
        cls.proc = None
        cls._start_server()

    @classmethod
    def _start_server(cls):
        cls.server_seq += 1
        token_file = cls.runtime / "web.token"
        token_file.unlink(missing_ok=True)
        cls.server_log = open(
            cls.root / f"web-server-{cls.server_seq}.log", "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(WEB)], env=cls.env,
            stdout=cls.server_log, stderr=subprocess.STDOUT, text=True,
            start_new_session=True)
        cls.pgid = os.getpgid(cls.proc.pid)
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
                    + (cls.root / f"web-server-{cls.server_seq}.log").read_text(
                        encoding="utf-8", errors="replace"))
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web ist nicht erreichbar")
        cls.token = token_file.read_text(encoding="utf-8").strip()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def _stop_server(cls):
        proc = getattr(cls, "proc", None)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        pgid = getattr(cls, "pgid", None)
        if pgid is not None:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        if cls.server_log is not None and not cls.server_log.closed:
            cls.server_log.close()

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
            cls._stop_server()
            cls.tmp.cleanup()

    def setUp(self):
        self.settings_path = self.state_dir / "settings.json"
        self.settings_path.unlink(missing_ok=True)
        # Frischer Server pro Fall: kein Cache eines vorherigen Falls.
        self._stop_server()
        self._start_server()
        self.page_errors = []
        self.context = self.browser.new_context(
            viewport={"width": 1400, "height": 1000})
        self.page = self.context.new_page()
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))

    def tearDown(self):
        try:
            self.page.close()
            self.context.close()
        finally:
            self.settings_path.unlink(missing_ok=True)

    # ---------- Helfer ----------

    def wait_until(self, predicate, timeout=20,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.1)
        self.fail(message)

    def boot(self, page=None):
        page = page or self.page
        page.goto(self.base + "/#t=" + self.token)
        page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)

    def goto_view(self, view, page=None):
        page = page or self.page
        page.goto(self.base + "/#/" + view)
        page.locator(f"main#nv-main[data-nv-view='{view}']").wait_for(
            state="visible", timeout=20000)

    def read_settings_file(self):
        if not self.settings_path.exists():
            return None
        try:
            return json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # Waehrend des Schreibens kann kurz ungueltiger Inhalt stehen.
            return None

    def wait_for_settings(self, predicate, timeout=20,
                          message="settings.json nicht wie erwartet geschrieben"):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            last = self.read_settings_file()
            if last is not None and predicate(last):
                return last
            time.sleep(0.1)
        self.fail(message + "; letzter Stand: " + repr(last))

    def meta_settings(self, page=None):
        page = page or self.page
        node = page.locator('meta[name="vibe-settings"]')
        self.assertEqual(1, node.count(), 'meta[name="vibe-settings"] fehlt')
        raw = node.get_attribute("content")
        self.assertIsNotNone(raw, "meta[name=vibe-settings] ohne content")
        return json.loads(raw)

    def local_json(self, key):
        raw = self.page.evaluate("key => localStorage.getItem(key)", key)
        return None if raw is None else json.loads(raw)

    def assert_no_page_errors(self, errors=None):
        self.assertEqual([], self.page_errors if errors is None else errors,
                         "Die Oberfläche erzeugte JavaScript-Fehler")

    def _settings_have_all(self, data):
        settings = data.get("settings") if isinstance(data, dict) else None
        if not isinstance(settings, dict):
            return False
        features = settings.get("features")
        return (settings.get("theme") == THEME
                and settings.get("accent") == ACCENT
                and isinstance(features, dict)
                and bool(features.get("github"))
                and PROJECT_NAME in _names(settings.get("favorite_projects"))
                and (AGENT_SCOPE, AGENT_NAME)
                in _agent_pairs(settings.get("favorite_agents")))

    def pin_project(self):
        card = self.page.locator(
            f"article[data-nv-project='{PROJECT_NAME}']")
        card.wait_for(state="visible", timeout=20000)
        pin = card.locator("[data-nv-action='project-pin']")
        pin.first.click()
        self.wait_until(lambda: self.page.locator(
            f"section[data-nv-pinned-projects] "
            f"article[data-nv-project='{PROJECT_NAME}']").count() == 1,
            message="Projekt kam nicht in die Angeheftet-Sektion")

    def pin_agent(self):
        card = self.page.locator(
            f"article[data-nv-agent='{AGENT_NAME}']"
            f"[data-nv-agent-scope='{AGENT_SCOPE}']")
        card.wait_for(state="visible", timeout=20000)
        pin = card.locator("[data-nv-action='agent-pin']")
        pin.first.click()
        self.wait_until(lambda: self.page.locator(
            f"section[data-nv-pinned-agents] article[data-nv-agent='{AGENT_NAME}']"
            f"[data-nv-agent-scope='{AGENT_SCOPE}']").count() == 1,
            message="Agent kam nicht in die Angeheftet-Sektion")

    # ---------- Faelle ----------

    def test_changes_are_saved_in_state_and_mirrored_to_legacy_storage(self):
        """Theme, Akzent, Feature und beide Pins landen in settings.json.

        Die alten localStorage-Schluessel bleiben zusaetzlich gespiegelt, damit
        bestehende Aufrufer weiterhin funktionieren.
        """
        self.boot()
        self.goto_view("settings")
        select = self.page.locator("[data-nv-theme-select]")
        select.wait_for(state="visible", timeout=20000)
        select.select_option(THEME)
        self.wait_until(lambda: self.page.evaluate(
            "() => document.documentElement.getAttribute('data-theme')") == THEME,
            message="data-theme wurde nicht auf dark gesetzt")

        accent = self.page.locator(
            f"[data-nv-ssection='appearance'] button[data-nv-accent='{ACCENT}']")
        accent.wait_for(state="visible", timeout=20000)
        accent.click()
        self.wait_until(lambda: self.page.evaluate(
            "() => document.documentElement.getAttribute('data-accent')") == ACCENT,
            message="data-accent wurde nicht auf teal gesetzt")

        feature = self.page.locator("input[data-nv-feature='github']")
        feature.wait_for(state="visible", timeout=20000)
        feature.check()
        self.wait_until(lambda: self.page.locator(
            "input[data-nv-feature='github']").is_checked(),
            message="Der Feature-Schalter github blieb aus")

        self.goto_view("home")
        self.pin_project()
        self.goto_view("agents")
        self.pin_agent()

        data = self.wait_for_settings(
            self._settings_have_all,
            message="settings.json enthält nicht alle fünf Einstellungen")
        self.assertEqual(1, data.get("version"), "version ist nicht 1")
        settings = data["settings"]
        self.assertEqual(THEME, settings["theme"])
        self.assertEqual(ACCENT, settings["accent"])
        self.assertTrue(bool(settings["features"]["github"]))
        self.assertIn(PROJECT_NAME, _names(settings["favorite_projects"]))
        self.assertIn((AGENT_SCOPE, AGENT_NAME),
                      _agent_pairs(settings["favorite_agents"]))

        # Legacy-Spiegelung: die alten Schluessel bleiben erhalten.
        self.assertEqual(
            THEME,
            self.page.evaluate("() => localStorage.getItem('nv-theme')"),
            "nv-theme wurde nicht gespiegelt")
        self.assertEqual(
            ACCENT,
            self.page.evaluate("() => localStorage.getItem('nv-accent')"),
            "nv-accent wurde nicht gespiegelt")
        self.assertTrue(
            bool((self.local_json("nv-features") or {}).get("github")),
            "nv-features wurde nicht gespiegelt")
        self.assertIn(
            PROJECT_NAME, self.local_json("nv-pinned-projects") or [],
            "nv-pinned-projects wurde nicht gespiegelt")
        self.assertIn(
            {"scope": AGENT_SCOPE, "name": AGENT_NAME},
            self.local_json("nv-pinned-agents") or [],
            "nv-pinned-agents wurde nicht gespiegelt")
        self.assert_no_page_errors()

    def test_settings_restored_after_restart_in_fresh_context(self):
        """Gleicher State, neuer Prozess, leerer Browser: alles kommt zurueck."""
        self.settings_path.write_text(json.dumps({
            "version": 1,
            "settings": {
                "theme": THEME,
                "accent": ACCENT,
                "features": {"github": True},
                "favorite_projects": [PROJECT_NAME],
                "favorite_agents": [{"scope": AGENT_SCOPE, "name": AGENT_NAME}],
            },
        }), encoding="utf-8")
        # Update/Reopen: derselbe State, neuer Serverprozess, neues Token.
        self._stop_server()
        self._start_server()

        context = self.browser.new_context(
            viewport={"width": 1400, "height": 1000})
        try:
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            self.boot(page=page)
            self.wait_until(lambda: page.evaluate(
                "() => document.documentElement.getAttribute('data-theme')")
                == THEME, message="Theme kam nach dem Neustart nicht zurueck")
            self.wait_until(lambda: page.evaluate(
                "() => document.documentElement.getAttribute('data-accent')")
                == ACCENT, message="Akzent kam nach dem Neustart nicht zurueck")

            meta = self.meta_settings(page=page)
            settings = meta.get("settings") if isinstance(meta, dict) else None
            self.assertIsInstance(settings, dict,
                                  "meta[name=vibe-settings] ohne settings")
            self.assertEqual(THEME, settings.get("theme"))
            self.assertEqual(ACCENT, settings.get("accent"))
            self.assertTrue(bool((settings.get("features") or {}).get("github")))
            self.assertIn(PROJECT_NAME, _names(settings.get("favorite_projects")))
            self.assertIn((AGENT_SCOPE, AGENT_NAME),
                          _agent_pairs(settings.get("favorite_agents")))
            self.assertTrue(page.evaluate(
                "() => !!(window.NV && NV.settingsStored)"),
                "NV.settingsStored ist nicht gesetzt")

            self.goto_view("settings", page=page)
            select = page.locator("[data-nv-theme-select]")
            select.wait_for(state="visible", timeout=20000)
            self.assertEqual(THEME, select.input_value(),
                             "Der Theme-Select steht nicht auf dark")
            accent = page.locator(
                f"button[data-nv-accent='{ACCENT}']")
            accent.wait_for(state="visible", timeout=20000)
            self.assertEqual("true", accent.get_attribute("aria-pressed"),
                             "Der Akzent-Knopf ist nicht ausgewaehlt")
            feature = page.locator("input[data-nv-feature='github']")
            feature.wait_for(state="visible", timeout=20000)
            self.wait_until(lambda: page.locator(
                "input[data-nv-feature='github']").is_checked(),
                message="Der Feature-Schalter github ist nicht aktiv")

            self.goto_view("home", page=page)
            self.wait_until(lambda: page.locator(
                f"section[data-nv-pinned-projects] "
                f"article[data-nv-project='{PROJECT_NAME}']").count() == 1,
                message="Das angeheftete Projekt fehlt nach dem Neustart")
            self.goto_view("agents", page=page)
            self.wait_until(lambda: page.locator(
                f"section[data-nv-pinned-agents] article[data-nv-agent='{AGENT_NAME}']"
                f"[data-nv-agent-scope='{AGENT_SCOPE}']").count() == 1,
                message="Der angeheftete Agent fehlt nach dem Neustart")
            self.assert_no_page_errors(errors)
        finally:
            context.close()

    def test_legacy_local_storage_is_migrated_once_on_first_load(self):
        """Ohne Serverdatei werden die alten Schluessel einmalig übernommen."""
        self.assertFalse(self.settings_path.exists(),
                         "Vorbedingung: settings.json darf nicht existieren")
        seed = {
            "nv-theme": THEME,
            "nv-accent": ACCENT,
            "nv-features": json.dumps({"github": True}),
            "nv-pinned-projects": json.dumps([PROJECT_NAME]),
            "nv-pinned-agents": json.dumps(
                [{"scope": AGENT_SCOPE, "name": AGENT_NAME}]),
        }
        self.context.add_init_script(
            "var seed = %s; var host = %s;"
            "if (location.host === host) {"
            "Object.keys(seed).forEach(function (key) {"
            "if (window.localStorage.getItem(key) === null) {"
            "window.localStorage.setItem(key, seed[key]);}"
            "});}"
            % (json.dumps(seed, ensure_ascii=False),
               json.dumps("127.0.0.1:%d" % self.port)))

        self.boot()
        data = self.wait_for_settings(
            self._settings_have_all,
            message="Die Migration hat settings.json nicht geschrieben")
        self.assertEqual(1, data.get("version"))
        settings = data["settings"]
        self.assertEqual(THEME, settings["theme"])
        self.assertEqual(ACCENT, settings["accent"])
        self.assertTrue(bool(settings["features"]["github"]))
        self.assertIn(PROJECT_NAME, _names(settings["favorite_projects"]))
        self.assertIn((AGENT_SCOPE, AGENT_NAME),
                      _agent_pairs(settings["favorite_agents"]))

        # Nach der Migration ist die Datei massgeblich: ein Reload muss die
        # Werte aus dem Meta-Feld und nicht erneut aus dem Storage ziehen.
        self.page.reload()
        self.page.locator("main#nv-main[data-nv-view='home']").wait_for(
            state="visible", timeout=25000)
        meta = self.meta_settings()
        self.assertTrue(self._settings_have_all(meta),
                        "meta[name=vibe-settings] spiegelt die Migration nicht")
        self.assert_no_page_errors()

    def test_invalid_setting_values_fall_back_per_setting(self):
        """Ein ungueltiger Wert darf gueltige Nachbarwerte nicht verlieren."""
        self.settings_path.write_text(json.dumps({
            "version": 1,
            "settings": {
                "theme": "ultraviolet",
                "accent": ACCENT,
                "features": {"github": True, "from_the_future": True},
                "favorite_projects": [PROJECT_NAME],
                "favorite_agents": "keine-liste",
            },
        }), encoding="utf-8")
        self.boot()

        self.wait_until(lambda: self.page.evaluate(
            "() => document.documentElement.getAttribute('data-accent')")
            == ACCENT, message="Der gueltige Akzent ging verloren")
        resolved = self.page.evaluate(
            "() => document.documentElement.getAttribute('data-theme')")
        self.assertIn(resolved, ("light", "dark"),
                      "Ungueltiges Theme wurde nicht auf einen Standardwert "
                      "zurueckgesetzt: " + repr(resolved))

        self.goto_view("settings")
        select = self.page.locator("[data-nv-theme-select]")
        select.wait_for(state="visible", timeout=20000)
        self.assertIn(select.input_value(), ("light", "dark", "auto"),
                      "Der Theme-Select zeigt einen ungueltigen Wert")
        self.assertEqual(0, self.page.locator(
            "input[data-nv-feature='from_the_future']").count(),
            "Ein unbekanntes Feature erzeugt einen Schalter")
        feature = self.page.locator("input[data-nv-feature='github']")
        feature.wait_for(state="visible", timeout=20000)
        self.wait_until(lambda: self.page.locator(
            "input[data-nv-feature='github']").is_checked(),
            message="Der gueltige Feature-Wert ging verloren")
        accent = self.page.locator(f"button[data-nv-accent='{ACCENT}']")
        accent.wait_for(state="visible", timeout=20000)
        self.assertEqual("true", accent.get_attribute("aria-pressed"),
                         "Der gueltige Akzent ist nicht ausgewaehlt")

        self.goto_view("home")
        self.wait_until(lambda: self.page.locator(
            "section[data-nv-pinned-projects]").is_visible(),
            message="Die Angeheftet-Sektion fehlt")
        self.assertEqual(1, self.page.locator(
            f"section[data-nv-pinned-projects] "
            f"article[data-nv-project='{PROJECT_NAME}']").count(),
            "Das gueltige angeheftete Projekt ging verloren")
        self.goto_view("agents")
        self.page.locator("[data-nv-agent-list]").wait_for(
            state="visible", timeout=20000)
        self.assertEqual(0, self.page.locator(
            "section[data-nv-pinned-agents] article[data-nv-agent]").count(),
            "Ein ungueltiger favorite_agents-Wert erzeugte einen Pin")
        self.assert_no_page_errors()

    def test_malformed_settings_json_falls_back_to_defaults(self):
        """Defektes JSON darf die Oberfläche nicht beschädigen."""
        self.settings_path.write_text("{kein gueltiges json", encoding="utf-8")
        self.boot()
        resolved = self.page.evaluate(
            "() => document.documentElement.getAttribute('data-theme')")
        self.assertIn(resolved, ("light", "dark"),
                      "data-theme ist nach defektem JSON ungueltig: "
                      + repr(resolved))
        self.wait_until(lambda: self.page.evaluate(
            "() => { var value = document.documentElement"
            ".getAttribute('data-accent'); return value !== null; }"),
            message="Es wurde kein Standard-Akzent gesetzt")
        self.assertIn(self.page.evaluate(
            "() => document.documentElement.getAttribute('data-accent')"),
            ACCENT_IDS, "data-accent ist nach defektem JSON ungueltig")
        meta = self.meta_settings()
        effective = meta.get("settings")
        self.assertIsInstance(effective, dict,
                              "meta[name=vibe-settings] ohne gueltige Werte")
        self.assertEqual("light", effective.get("theme"),
                         "Meta-Feld meldet nach defektem JSON kein Standardthema")
        self.assertEqual("blue", effective.get("accent"),
                         "Meta-Feld meldet nach defektem JSON keinen Standardakzent")
        self.assertFalse(bool((effective.get("features") or {}).get("github")))
        self.assertEqual([], effective.get("favorite_projects"))
        self.assertEqual([], effective.get("favorite_agents"))

        self.goto_view("settings")
        feature = self.page.locator("input[data-nv-feature='github']")
        feature.wait_for(state="visible", timeout=20000)
        self.assertFalse(feature.is_checked(),
                         "Ein Feature ist ohne gueltige Datei eingeschaltet")
        self.goto_view("home")
        self.page.locator("section[data-nv-projects]").wait_for(
            state="visible", timeout=20000)
        self.assertEqual(0, self.page.locator(
            "section[data-nv-pinned-projects] article[data-nv-project]").count(),
            "Es gibt Pins ohne gueltige Datei")
        self.assert_no_page_errors()

    def test_large_cjk_favorites_are_persisted(self):
        """200 lange CJK-Namen: UTF-8-Bytes > 64 KiB, JS-Länge < 60000.

        Ein keepalive-Guard, der JS-Zeichen statt UTF-8-Bytes zählt, lässt die
        fetch-Anfrage stillschweigend scheitern; die Datei bleibt dann alt.
        """
        self.boot()
        names = self.page.evaluate(
            "() => { var list = []; "
            "for (var i = 0; i < 200; i += 1) {"
            "list.push(String.fromCharCode(0x4e00 + i).repeat(200));}"
            "return list; }")
        first = chr(0x4E00) * 200
        last = chr(0x4E00 + 199) * 200
        self.assertEqual(200, len(names))
        self.assertEqual(first, names[0])
        self.assertEqual(last, names[-1])
        self.assertLess(sum(len(name) for name in names), 60000,
                        "Vorbedingung: JS-Länge muss unter dem Limit liegen")
        self.assertGreater(
            len(json.dumps({"favorite_projects": names},
                           ensure_ascii=False).encode("utf-8")),
            64 * 1024, "Vorbedingung: UTF-8-Nutzlast muss über 64 KiB liegen")

        # Ein Promise aus page.evaluate wird abgewartet: danach ist der POST
        # abgeschlossen, egal ob er keepalive nutzte oder nicht.
        self.page.evaluate(
            "favorites => NV.saveSettings({favorite_projects: favorites})",
            names)
        data = self.wait_for_settings(
            lambda doc: len((((doc or {}).get("settings") or {})
                             .get("favorite_projects")) or []) == 200,
            timeout=30,
            message="Die grossen Favoriten wurden nicht in settings.json geschrieben")
        persisted = data["settings"]["favorite_projects"]
        self.assertEqual(first, persisted[0])
        self.assertEqual(last, persisted[-1])

        # Reopen: neuer Prozesszustand würde hier denselben Meta-Pfad lesen;
        # ein frischer Browserkontext beweist, dass nichts aus localStorage
        # nachhelfen muss.
        context = self.browser.new_context(
            viewport={"width": 1400, "height": 1000})
        try:
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            self.boot(page=page)
            meta = self.meta_settings(page=page)
            restored = meta["settings"]["favorite_projects"]
            self.assertEqual(200, len(restored))
            self.assertEqual(first, restored[0])
            self.assertEqual(last, restored[-1])

            current = page.evaluate("() => NV.favoriteProjects()")
            self.assertEqual(200, len(current))
            self.assertEqual(first, current[0])
            self.assertEqual(last, current[-1])
            mirror = json.loads(page.evaluate(
                "() => localStorage.getItem('nv-pinned-projects')"))
            self.assertEqual(200, len(mirror))
            self.assertEqual(first, mirror[0])
            self.assertEqual(last, mirror[-1])
            self.assert_no_page_errors(errors)
        finally:
            context.close()

    def test_invalid_favorite_entries_are_not_mirrored_optimistically(self):
        """Zu lange und nicht-string Einträge werden weder gespiegelt noch
        in der Oberfläche angezeigt — Server und Client nutzen dieselben Grenzen.
        """
        self.boot()
        long_name = "x" * (200 + 1)
        projects = [PROJECT_NAME, long_name, 4711, None, "", {"name": "objekt"}]
        agents = [
            {"scope": AGENT_SCOPE, "name": AGENT_NAME},
            {"scope": AGENT_SCOPE, "name": "y" * (200 + 1)},
            {"scope": "z" * (200 + 1), "name": AGENT_NAME},
            {"scope": AGENT_SCOPE, "name": 42},
            "kein-objekt",
        ]

        # Rohen Patch senden: der Server verwirft ungueltige Eintraeze und
        # liefert den bereinigten Stand zurueck, den der Client spiegelt.
        response = self.page.evaluate(
            "patch => NV.saveSettings(patch)",
            {"favorite_projects": projects, "favorite_agents": agents})
        self.assertTrue(response.get("ok"), repr(response))
        data = self.wait_for_settings(
            lambda doc: _names((((doc or {}).get("settings") or {})
                                .get("favorite_projects"))) == [PROJECT_NAME]
            and _agent_pairs((((doc or {}).get("settings") or {})
                              .get("favorite_agents")))
            == [(AGENT_SCOPE, AGENT_NAME)],
            message="Ungueltige Favoriten wurden in settings.json geschrieben")
        self.assertNotIn(long_name, self.settings_path.read_text(encoding="utf-8"))
        self.assertEqual([PROJECT_NAME], data["settings"]["favorite_projects"])
        self.assertEqual(
            [{"scope": AGENT_SCOPE, "name": AGENT_NAME}],
            data["settings"]["favorite_agents"])

        # Die Setter normalisieren vor dem optimistischen Spiegeln.
        self.page.evaluate(
            "args => { NV.setFavoriteProjects(args.projects);"
            "NV.setFavoriteAgents(args.agents); }",
            {"projects": projects, "agents": agents})
        mirrored = self.page.evaluate(
            "() => ({projects: NV.settings.favorite_projects,"
            "agents: NV.settings.favorite_agents,"
            "storedProjects: JSON.parse(localStorage.getItem('nv-pinned-projects')),"
            "storedAgents: JSON.parse(localStorage.getItem('nv-pinned-agents'))})")
        for key in ("projects", "storedProjects"):
            with self.subTest(mirror=key):
                self.assertEqual([PROJECT_NAME], mirrored[key])
        valid_agent = [{"scope": AGENT_SCOPE, "name": AGENT_NAME}]
        for key in ("agents", "storedAgents"):
            with self.subTest(mirror=key):
                self.assertEqual(valid_agent, mirrored[key])

        # Auch die Ansicht zeigt nur die gueltigen Eintraege.
        self.goto_view("home")
        pinned_projects = self.page.locator(
            "section[data-nv-pinned-projects] article[data-nv-project]")
        self.wait_until(lambda: pinned_projects.count() == 1,
                        message="Die Ansicht zeigt nicht genau ein gueltiges Projekt")
        self.assertEqual(
            [PROJECT_NAME], pinned_projects.evaluate_all(
                "nodes => nodes.map(node => node.getAttribute('data-nv-project'))"))
        self.goto_view("agents")
        pinned_agents = self.page.locator(
            "section[data-nv-pinned-agents] article[data-nv-agent]")
        self.wait_until(lambda: pinned_agents.count() == 1,
                        message="Die Ansicht zeigt nicht genau einen gueltigen Agenten")
        self.assertEqual(
            [[AGENT_SCOPE, AGENT_NAME]],
            pinned_agents.evaluate_all(
                "nodes => nodes.map(node => [node.getAttribute('data-nv-agent-scope'),"
                "node.getAttribute('data-nv-agent')])"))
        self.assert_no_page_errors()
