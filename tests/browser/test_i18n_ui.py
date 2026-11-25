"""Sprachumschaltung und I18n-API in der Oberfläche.

Aufruf: python3 -m unittest tests.browser.test_i18n_ui -v
"""


# ===========================================================================
# Browserabnahme: vollständig englische Oberfläche und i18n-Infrastruktur
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

_BROWSERS = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "bin" / "vibe-web.py"
RUNS_PY = REPO / "bin" / "vibe_runs.py"

AGENT = "vibe-agent"
MAIN_SESSION = "ses_main_ap21"
SUB_SESSION = "ses_sub_ap21"
SUB_AGENT = "tester"
SUB_OUTPUT = (
    "AUSGABE-AP21-4711: Der Subagent protokolliert seinen Fortschritt.\n"
    "$ ./scripts/check-werkzeug.sh --verbose\n"
    "+neue Zeile\n-alte Zeile\n")

MAIN_MARKER = "HAUPT-AP21-4711: Hauptagent schreibt sein Protokoll."

# Panel-Kennungen bleiben stabil (AP20-Vertrag), nur die Beschriftungen
# werden übersetzt. Die Tests lesen die Tabs deshalb über aria-controls und
# nicht über ihren (sprachabhängigen) Text.
TABS = {
    "arbeit": "Work",
    "ausgabe": "Output",
    "assistent": "Assistant",
    "einstellungen": "Settings",
}
SETTINGS_NAV = {
    "agenten": "Agents",
    "rechte": "Write access",
    "sandbox": "Sandbox",
    "github": "Git & GitHub",
}

ENGLISH_TAB_LABELS = set(TABS.values())


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _FakeOpenCodeHandler(BaseHTTPRequestHandler):
    """opencode-Attrappe: liefert keine Agentennachrichten.

    Damit greift im Dashboard der State-Fallback: Die Subagentenliste kommt
    aus ``proj.log.state.json``. Kein echter Modellaufruf.
    """

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
        if "/message" in self.path:
            self._send_json(200, {"data": []})
            return
        self._send_json(200, {"ok": True})


# i18n-API im Browser: VIBE_I18N ist der Vertragsname, I18N der Alias.
I18N_PROBE_JS = """() => {
  const api = window.VIBE_I18N
    || (typeof I18N !== 'undefined' ? I18N : null)
    || window.I18N || null;
  return {
    present: !!api,
    aliasPresent: (typeof I18N !== 'undefined' && !!I18N)
      || !!window.I18N,
    functions: api ? ['available', 'current', 'set', 't']
      .filter(name => typeof api[name] === 'function') : [],
    available: api && typeof api.available === 'function'
      ? api.available() : null,
    current: api && typeof api.current === 'function'
      ? api.current() : null,
    stored: (() => {
      const values = [];
      for (let i = 0; i < localStorage.length; i += 1) {
        values.push(localStorage.getItem(localStorage.key(i)));
      }
      return values;
    })(),
  };
}"""

FORMATTER_JS = """(lang) => {
  const api = window.VIBE_I18N
    || (typeof I18N !== 'undefined' ? I18N : null) || {};
  if (typeof api.set === 'function') api.set(lang);
  const num = api.formatNumber || api.number || window.fmtN;
  const cur = api.formatCurrency || api.currency || window.fmtEUR;
  return {
    current: typeof api.current === 'function' ? api.current() : null,
    hasNumber: typeof num === 'function',
    hasCurrency: typeof cur === 'function',
    number: typeof num === 'function' ? String(num(1234.5)) : null,
    currency: typeof cur === 'function' ? String(cur(1234.5)) : null,
  };
}"""


class AP21BrowserTest(unittest.TestCase):
    """Dashboard, Browser, opencode-Attrappe, isoliertes VIBE-Root."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "proj"
        (cls.project / ".vibe").mkdir(parents=True)
        (cls.project / ".vibe" / "project.env").write_text(
            "TYPE=generic\n", encoding="utf-8")
        (cls.project / "FEEDBACK.md").write_text(
            "# FEEDBACK\n\n- [ ] AP21 Englische Sprache\n"
            "  Beschreibung: Test\n", encoding="utf-8")
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
        password.write_text("geheim-AP21-4711", encoding="utf-8")
        password.chmod(0o600)
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

    # ---------- Seeds und Helfer ----------

    def setUp(self):
        register = self.log_dir / "runs.json"
        if register.exists():
            register.unlink()
        (self.log_dir / "proj.log.state.json").unlink(missing_ok=True)
        (self.log_dir / "proj.log").unlink(missing_ok=True)
        (self.state_dir / "harness.json").unlink(missing_ok=True)
        # AP21 v2: Die Sprache ist global in ui.json gespeichert. Vor jedem
        # Test auf den englischen Standard zuruecksetzen (Datei + In-Memory),
        # damit die Faelle unabhaengig sind.
        self.post_language("en")
        self.page_errors = []
        self.dialogs = []
        self.page = self.browser.new_page(
            viewport={"width": 1400, "height": 900})
        self.page.on("pageerror",
                     lambda error: self.page_errors.append(str(error)))
        self.page.on("dialog", self._on_dialog)

    def _on_dialog(self, dialog):
        self.dialogs.append(dialog.type + ": " + dialog.message)
        dialog.dismiss()

    def tearDown(self):
        self.page.close()

    def register_run(self, state="running"):
        result = subprocess.run([
            sys.executable, str(RUNS_PY), "start",
            "--runtime", str(self.log_dir),
            "--project", str(self.project.resolve()),
            "--name", "proj", "--key", "proj", "--agent", AGENT,
            "--state", state,
        ], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0,
                         "Vorbedingung Laufregister fehlgeschlagen: "
                         + result.stdout + result.stderr)

    def write_log(self, lines=None):
        body = list(lines) if lines is not None else [MAIN_MARKER]
        (self.log_dir / "proj.log").write_text(
            "=== Agentenlauf proj ===\n" + "\n".join(body) + "\n",
            encoding="utf-8")

    def sub(self, session, status="running"):
        return {
            "session": session,
            "agent": SUB_AGENT,
            "description": "Prüft die englische Oberfläche",
            "prompt": "Auftrag für " + SUB_AGENT,
            "status": status,
            "started": int(time.time()) + 5,
            "ended": int(time.time()) + 180 if status != "running" else 0,
            "output": SUB_OUTPUT,
        }

    def write_state(self, subs=None, main_session=MAIN_SESSION):
        if subs is None:
            subs = [self.sub(SUB_SESSION)]
        (self.log_dir / "proj.log.state.json").write_text(
            json.dumps({"session": main_session, "subagents": subs},
                       ensure_ascii=False),
            encoding="utf-8")

    def wait_until(self, predicate, timeout=20,
                   message="Bedingung nicht erfüllt"):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            self.page.wait_for_timeout(100)
        self.fail(message)

    def post_language(self, lang, token=None):
        """Setzt die globale Sprache direkt ueber die API (Test-Vorbedingung)."""
        body = json.dumps({"language": lang}).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", "/api/language", body=body, headers={
                "Host": f"127.0.0.1:{self.port}", "X-Token": token or self.token,
                "Content-Type": "application/json"})
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8", "replace")
        finally:
            conn.close()

    def ui_json_language(self):
        path = self.state_dir / "ui.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8")).get("language")

    # ---------- Sprache und Tabs ----------

    def open_settings(self):
        """Oeffnet die globale Navigationsseite 'Settings' (ohne Projekt)."""
        if self.page.locator("#nav button[data-t]").count() == 0:
            self.page.goto(self.base + "/classic#t=" + self.token)
        nav_btn = self.page.locator("[data-t='settings']")
        self.assertEqual(1, nav_btn.count(),
                         "Der globale Nav-Tab [data-t='settings'] fehlt")
        nav_btn.click()
        self.page.locator("#settings-language").wait_for(
            state="visible", timeout=15000)

    def html_lang(self):
        return self.page.evaluate("() => document.documentElement.lang")

    def i18n(self):
        return self.page.evaluate(I18N_PROBE_JS)

    def wait_for_i18n(self, timeout=20):
        self.wait_until(
            lambda: self.i18n().get("present") and
            {"available", "current", "set", "t"}.issubset(
                set(self.i18n().get("functions") or [])),
            timeout=timeout,
            message="window.VIBE_I18N (Alias I18N) ist nicht mit "
                    "available/current/set/t verfügbar: "
                    + repr(self.i18n()))

    def tab_button(self, key):
        """Tab über die stabile Panel-Kopplung, unabhängig von der Sprache."""
        return self.page.locator(
            f"[role='tab'][aria-controls='panel-{key}']").first

    def tab_texts(self):
        texts = {}
        for key in TABS:
            count = self.page.locator(
                f"[role='tab'][aria-controls='panel-{key}']").count()
            self.assertEqual(
                1, count,
                f"Tab für Panel '{key}' fehlt (aria-controls=panel-{key})")
            texts[key] = self.tab_button(key).inner_text().strip()
        return texts

    def _fulfill_run_state(self, route, state):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"running": bool(state["running"]),
                             "pause_after": False}))

    def open_project(self, run_state=None, log_lines=None):
        """Projekt öffnen; ``run_state`` kann den Laufstatus fest vorgeben.

        ``run_state`` ist ein veränderbares Dict (``{"running": True/False}``).
        Es wird vor dem Laden als Antwort für ``/api/run-state`` hinterlegt,
        damit der Test den Statuslabel ohne Abhängigkeit von der
        Laufregister-/tmux-Erkennung prüft (Muster wie AP19).

        ``log_lines`` erlaubt es, das Hauptprotokoll vor dem Öffnen durch
        eigenen Text zu ersetzen (M2: Nutzerdaten bleiben unübersetzt).
        """
        self.register_run("running")
        self.write_log(log_lines)
        self.write_state()
        if run_state is not None:
            self.page.route(
                "**/api/run-state*",
                lambda route: self._fulfill_run_state(route, run_state))
        self.page.goto(self.base + "/classic#t=" + self.token)
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for(state="visible", timeout=20000)
        row.click()
        self.tab_button("arbeit").wait_for(state="visible", timeout=20000)

    def open_tab(self, key):
        self.tab_button(key).click()
        self.page.locator(f"[data-panel='{key}']").wait_for(
            state="visible", timeout=15000)

    def settings_select(self):
        """Der einzige globale Sprachumschalter (auf der Settings-Navseite)."""
        return self.page.locator("select[aria-label='Language']")

    def require_settings_select(self):
        select = self.settings_select()
        self.assertEqual(
            1, select.count(),
            "Es gibt nicht genau einen globalen Sprachumschalter "
            "select[aria-label='Language']")
        return select

    def settings_nav_chip(self, key):
        return self.page.locator(
            f"[data-panel='einstellungen'] .settings-nav "
            f"[data-goto='{key}']")

    def assert_language(self, expected):
        self.assertEqual(
            expected, self.html_lang(),
            f"<html lang> ist {self.html_lang()!r}, erwartet {expected!r}")
        self.assertEqual(
            expected, self.i18n().get("current"),
            "I18N.current() ist nicht " + repr(expected) + ": "
            + repr(self.i18n()))

    def assert_english_tabs(self, timeout=10):
        self.wait_until(
            lambda: self.tab_texts() == TABS,
            timeout=timeout,
            message="Die Tabs tragen nicht die englischen Beschriftungen: "
                    + repr(self.tab_texts()))

    def assert_not_english_tabs(self, timeout=10):
        def done():
            texts = self.tab_texts()
            return not ENGLISH_TAB_LABELS.intersection(set(texts.values()))
        self.wait_until(
            done, timeout=timeout,
            message="Nach dem Sprachwechsel sind Tabs weiterhin englisch "
                    "beschriftet: " + repr(self.tab_texts()))

    def assert_clean_page(self):
        self.assertEqual([], self.page_errors,
                         "Die Oberfläche erzeugte JavaScript-Fehler")
        self.assertEqual([], self.dialogs,
                         "Die Oberfläche öffnete einen Browserdialog")


class DefaultLanguageTest(AP21BrowserTest):
    def test_fresh_profile_defaults_to_english(self):
        """VP2/VP4: Frisches Profil startet englisch, ``<html lang="en">``.

        Vorbedingung: frisches Browserprofil ohne localStorage, aktiver Lauf,
        ein laufender Subagent.
        Aktion: Projekt öffnen; Tabs, Laufstatus und i18n-Zustand auslesen.
        Erwartung: ``lang="en"``; ``I18N.current() === 'en'``; Tabs exakt
        ``Work``/``Output``/``Assistant``/``Settings``; ``#runstate`` zeigt
        ``running``; keine JS-Fehler.
        Fehlerfall: Deutsche Resttexte (heutiger Zustand) oder fehlendes
        ``lang``-Attribut.
        """
        self.open_project()
        self.assert_language("en")
        self.assert_english_tabs()

        run_state = self.page.locator("#runstate").inner_text().strip()
        self.assertEqual(
            "running", run_state,
            f"Der Laufstatus ist {run_state!r}, erwartet 'running'")
        self.assert_clean_page()

    def test_settings_navigation_and_language_selector_are_english(self):
        """VP3/VP4: Einstellungsnavigation und Sprachumschalter sind englisch.

        Vorbedingung: Projekt geöffnet, Englisch aktiv.
        Aktion: Einstellungen öffnen und auslesen.
        Erwartung: Sprungknöpfe ``Agents``, ``Write access``, ``Sandbox``,
        ``Git & GitHub``; der Bereich nennt ``Language``;
        ``select[aria-label="Language"]`` mit genau ``English`` (``en``) und
        ``Deutsch`` (``de``), Wert ``en`` = ``current()``.
        Fehlerfall: Umschalter fehlt oder ist nicht englisch beschriftet.
        """
        self.open_project()
        self.open_tab("einstellungen")

        for key, label in SETTINGS_NAV.items():
            chip = self.settings_nav_chip(key)
            self.assertEqual(
                1, chip.count(),
                f"Der Sprungknopf '{key}' fehlt in der "
                "Einstellungsnavigation")
            chip_text = chip.first.inner_text()
            self.assertIn(
                label, chip_text,
                f"Der Sprungknopf '{key}' ist nicht als {label!r} "
                f"beschriftet: {chip_text!r}")

        # AP21 v2: Kein Sprachumschalter mehr im Projekt-Einstellungs-Tab.
        self.assertEqual(
            0, self.page.locator(
                "[data-panel='einstellungen'] select[aria-label='Language']").count(),
            "Der Sprachumschalter darf nicht mehr im Projekt-Tab liegen")

        # AP21 v2: Die Karte 'Language' liegt auf der globalen Settings-Seite.
        self.open_settings()
        card = self.page.locator("#settings-language")
        self.assertIn(
            "Language", card.inner_text(),
            "Die globale Karte nennt keinen Abschnitt „Language“: "
            + repr(card.inner_text()[:400]))

        select = self.require_settings_select()
        options = self.page.eval_on_selector_all(
            "select[aria-label='Language'] option",
            "nodes => nodes.map(node => [node.value, node.textContent.trim()])")
        self.assertEqual(
            [["en", "English"], ["de", "Deutsch"]], options,
            "Der Sprachumschalter bietet nicht genau English/Deutsch an: "
            + repr(options))
        self.assertEqual("en", select.input_value(),
                         "Der Sprachumschalter steht nicht auf 'en'")
        self.assert_clean_page()

    def test_run_status_shows_running_then_stopped_in_english(self):
        """VP4: Der Laufstatus ist englisch und aktualisiert sich live.

        Vorbedingung: aktiver Lauf, Projekt geöffnet.
        Aktion: ``/api/run-state`` liefert zunächst ``running: true``, dann
        ``running: false`` (Antwort im Browser hinterlegt, damit der Test
        nur das Label prüft).
        Erwartung: ``running``, danach ``stopped`` – ohne Neuladen.
        Fehlerfall: „läuft“/„gestoppt“ oder eingefrorener Status.
        """
        status = {"running": True}
        self.open_project(run_state=status)
        pill = self.page.locator("#runstate")
        self.wait_until(
            lambda: pill.inner_text().strip() == "running",
            timeout=10,
            message="Der laufende Lauf zeigt nicht 'running', sondern "
                    + repr(pill.inner_text().strip()))

        status["running"] = False
        self.wait_until(
            lambda: pill.inner_text().strip() == "stopped",
            timeout=15,
            message="Der beendete Lauf zeigt nicht 'stopped', sondern "
                    + repr(pill.inner_text().strip()))
        self.assert_language("en")
        self.assert_clean_page()


class LanguageSwitchTest(AP21BrowserTest):
    """AP21 v2: Umschalten ueber die globale Settings-Navseite."""

    def switch(self, lang):
        self.open_settings()
        self.require_settings_select().select_option(lang)
        self.wait_until(lambda: self.html_lang() == lang, timeout=15,
                        message=f"<html lang> wurde nicht {lang!r}")
        self.wait_until(lambda: self.i18n().get("current") == lang, timeout=15,
                        message=f"I18N.current() wurde nicht {lang!r}")

    def back_to_project(self):
        """Clientseitig (ohne Reload) vom Nav-Tab zurueck ins Projekt."""
        self.page.locator("[data-t='projects']").click()
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for(state="visible", timeout=20000)
        row.click()
        self.tab_button("arbeit").wait_for(state="visible", timeout=20000)

    def test_selecting_german_translates_visible_areas_without_reload(self):
        """VP3: Deutsch im globalen Umschalter stellt die Oberfläche um.

        Vorbedingung: Projekt geöffnet, Englisch aktiv.
        Aktion: ``de`` im globalen Sprachumschalter wählen; vorher einen
        JS-Marker setzen, der ein Neuladen überführen würde.
        Erwartung: ``lang="de"``, ``current()==='de'``, Nav und Projekt-Tabs
        sind nicht mehr englisch, der Marker lebt weiter; keine JS-Fehler.
        """
        self.open_project()
        self.assert_english_tabs()
        self.page.evaluate("() => { window.__ap21Marker = 'alive'; }")

        self.switch("de")
        marker = self.page.evaluate("() => window.__ap21Marker || null")
        self.assertEqual(
            "alive", marker,
            "Der Sprachwechsel hat die Seite neu geladen (JS-Marker weg)")
        self.assert_language("de")

        self.back_to_project()
        self.assert_not_english_tabs()
        self.assert_clean_page()

    def test_german_choice_survives_reload_and_is_server_side(self):
        """VP3/AP21 v2: Die Wahl steht in ui.json und übersteht ein Neuladen."""
        self.switch("de")
        self.assertEqual("de", self.ui_json_language(),
                         "ui.json enthält die gewählte Sprache nicht")

        self.page.reload()
        self.wait_until(lambda: self.html_lang() == "de", timeout=15,
                        message="Nach dem Neuladen ist <html lang> nicht 'de'")
        self.assert_language("de")
        self.open_settings()
        self.assertEqual(
            "de", self.require_settings_select().input_value(),
            "Der Sprachumschalter steht nach dem Neuladen nicht auf 'de'")
        self.back_to_project()
        self.assert_not_english_tabs()
        self.assert_clean_page()

    def test_switching_back_to_english_restores_english_labels(self):
        """VP3: Der Rückwechsel auf Englisch stellt die englischen Labels her."""
        self.switch("de")
        self.switch("en")
        self.assert_language("en")
        self.assertEqual("en", self.ui_json_language())
        self.back_to_project()
        self.assert_english_tabs()
        self.assert_clean_page()


class GlobalLanguageBrowserTest(AP21BrowserTest):
    """AP21 v2: globale Settings-Seite, All-Sprachen-Umstellung, Fehlerfall."""

    def nav_texts(self):
        return self.page.locator("#nav button[data-t]").all_inner_texts()

    def test_global_settings_tab_exists_last_without_open_project(self):
        """AC1: 'Settings' ist letzter Nav-Tab und ohne Projekt erreichbar."""
        self.page.goto(self.base + "/classic#t=" + self.token)
        keys = self.page.locator("#nav button[data-t]").evaluate_all(
            "nodes => nodes.map(n => n.getAttribute('data-t'))")
        self.assertEqual("settings", keys[-1],
                         "Der globale Settings-Tab ist nicht der letzte: "
                         + repr(keys))
        self.assertEqual(1, keys.count("settings"))
        # Kein Projekt geoeffnet: die Karte muss trotzdem erscheinen.
        self.open_settings()
        self.assertEqual(1, self.require_settings_select().count())
        self.assert_clean_page()

    def test_no_language_select_in_project_settings_tab(self):
        """AC2: Kein Sprachumschalter mehr im Projekt-Einstellungs-Tab."""
        self.open_project()
        self.open_tab("einstellungen")
        self.assertEqual(
            0, self.page.locator(
                "[data-panel='einstellungen'] select[aria-label='Language']").count(),
            "Im Projekt-Tab darf kein Sprachumschalter stehen")

    def test_switch_en_to_de_translates_nav_list_and_all_project_tabs(self):
        """AC4: Nav, Projektliste und alle vier Projekt-Tabs wechseln mit."""
        self.open_project()
        self.assert_english_tabs()
        self.assertIn("Projects", self.nav_texts())

        # Umschalten ueber die globale Settings-Karte.
        self.open_settings()
        self.require_settings_select().select_option("de")
        self.wait_until(lambda: self.html_lang() == "de", timeout=15)
        self.wait_until(lambda: self.i18n().get("current") == "de", timeout=15)

        texts = self.nav_texts()
        self.assertIn("Projekte", texts, "Navigation nicht deutsch: " + repr(texts))
        self.assertNotIn("Projects", texts)

        # Projektliste in der Zielsprache (clientseitig, ohne Reload).
        self.page.locator("[data-t='projects']").click()
        self.wait_until(lambda: self.page.locator("th").count() > 0,
                        timeout=15, message="Projektliste wurde nicht gerendert")
        heads = self.page.locator("th").all_inner_texts()
        self.assertIn("Projekt", heads, "Projektliste nicht deutsch: " + repr(heads))
        self.assertNotIn("Project", heads)

        # Alle vier Projekt-Tabs in der Zielsprache.
        row = self.page.locator("tr.row", has_text="proj").first
        row.wait_for(state="visible", timeout=20000)
        row.click()
        self.tab_button("arbeit").wait_for(state="visible", timeout=20000)
        self.assert_not_english_tabs()
        expected = {"arbeit": "Arbeit", "ausgabe": "Ausgabe",
                    "assistent": "Assistent", "einstellungen": "Einstellungen"}
        self.assertEqual(expected, self.tab_texts())
        self.assert_language("de")
        self.assertEqual("de", self.ui_json_language())
        self.assert_clean_page()

    def test_reload_and_new_browser_context_keep_german(self):
        """AC4: Wahl überlebt Reload und gilt im neuen Browser-Kontext."""
        self.open_settings()
        self.require_settings_select().select_option("de")
        self.wait_until(lambda: self.html_lang() == "de", timeout=15)
        self.assertEqual("de", self.ui_json_language())

        self.page.reload()
        self.wait_until(lambda: self.html_lang() == "de", timeout=15)
        self.assert_language("de")

        # Frischer Browser-Kontext: kein localStorage, aber der Server liefert
        # die Sprache ueber <meta name="vibe-language"> mit.
        context = self.browser.new_context()
        try:
            fresh = context.new_page()
            fresh.goto(self.base + "/classic#t=" + self.token)
            fresh.wait_for_function(
                "() => !!(window.VIBE_I18N || window.I18N)")
            lang = fresh.evaluate("() => document.documentElement.lang")
            current = fresh.evaluate(
                "() => (window.VIBE_I18N || window.I18N).current()")
            self.assertEqual("de", lang, "Neuer Kontext hat nicht <html lang=de>")
            self.assertEqual("de", current, "Neuer Kontext liest die Sprache nicht")
        finally:
            context.close()
        self.assert_clean_page()

    def test_post_failure_shows_toast_and_reverts(self):
        """AC4: POST-Fehler → sichtbarer Toast + Rückfall auf vorherige Sprache."""
        def fail(route):
            if route.request.method == "POST":
                route.fulfill(status=500, content_type="application/json",
                              body=json.dumps({"ok": False,
                                               "error": {"code": "internal_error",
                                                         "message": "Zweckfehler"}}))
            else:
                route.continue_()

        self.page.route("**/api/language", fail)
        self.open_settings()
        self.require_settings_select().select_option("de")
        toast = self.page.locator("#toasts .toast .toasttext").first
        self.wait_until(
            lambda: toast.count() > 0 and "Zweckfehler" in (toast.inner_text() or ""),
            timeout=15,
            message="Kein Fehler-Toast sichtbar: "
                    + repr(self.page.locator("#toasts").inner_text()))
        self.assert_language("en")
        self.assertEqual("en", self.require_settings_select().input_value(),
                         "Der Umschalter ist nicht auf die alte Sprache zurueckgefallen")
        self.assertNotEqual("de", self.ui_json_language(),
                            "ui.json darf bei einem POST-Fehler nicht geaendert werden")
        self.assert_clean_page()


class I18nApiTest(AP21BrowserTest):
    def test_i18n_api_exposes_available_current_and_t(self):
        """VP1/VP5: ``window.VIBE_I18N`` mit Alias und Pflichtfunktionen.

        Vorbedingung: Seite geladen.
        Aktion: Global inspizieren.
        Erwartung: ``available()`` ist eine Liste mit ``en`` und ``de``;
        ``current()`` ist ``en``; ``available``/``current``/``set``/``t``
        sind Funktionen; der Alias ``I18N`` ist erreichbar.
        Fehlerfall: i18n.js fehlt, wird nach app.js geladen oder die API ist
        unvollständig.
        """
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.wait_for_i18n()
        data = self.i18n()

        self.assertTrue(data["present"], "window.VIBE_I18N fehlt")
        self.assertTrue(
            data["aliasPresent"],
            "Der Alias I18N ist nicht global erreichbar")
        self.assertEqual(
            {"available", "current", "set", "t"},
            set(data["functions"]),
            "Die i18n-API ist unvollständig: " + repr(data["functions"]))
        available = data["available"]
        self.assertIsInstance(
            available, list,
            "available() liefert keine Liste: " + repr(available))
        self.assertTrue(
            {"en", "de"}.issubset(set(available)),
            "available() enthält nicht en und de: " + repr(available))
        self.assertEqual(
            "en", data["current"],
            "current() ist bei frischem Profil nicht 'en': "
            + repr(data["current"]))
        self.assert_clean_page()

    def test_unknown_translation_key_returns_the_key(self):
        """VP5: Ein unbekannter Key liefert den Key selbst (kein Crash).

        Vorbedingung: Seite geladen.
        Aktion: ``I18N.t('ap21.unknown.key.4711')``.
        Erwartung: exakt der Key als Rückgabe.
        Fehlerfall: ``undefined``, leerer String oder Exception.
        """
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.wait_for_i18n()
        value = self.page.evaluate(
            "() => { const api = window.VIBE_I18N "
            "|| (typeof I18N !== 'undefined' ? I18N : null); "
            "return api.t('ap21.unknown.key.4711'); }")
        self.assertEqual(
            "ap21.unknown.key.4711", value,
            "Ein unbekannter Key liefert nicht den Key selbst: " + repr(value))
        self.assert_clean_page()

    def test_set_switches_language_and_html_lang_without_reload(self):
        """VP5: ``set`` schaltet sofort um, ohne die Seite zu laden.

        Vorbedingung: Projekt geöffnet, Englisch aktiv.
        Aktion: JS-Marker setzen; ``I18N.set('de')``; danach
        ``I18N.set('en')``.
        Erwartung: ``current()`` und ``<html lang>`` folgen sofort; der
        Marker bleibt; ``Settings`` verschwindet und kehrt zurück.
        Fehlerfall: ``set`` speichert nur, ohne die Oberfläche umzustellen.
        """
        self.open_project()
        self.wait_for_i18n()
        self.page.evaluate("() => { window.__ap21Marker = 'alive'; }")
        self.page.evaluate(
            "() => { const api = window.VIBE_I18N "
            "|| (typeof I18N !== 'undefined' ? I18N : null); api.set('de'); }")
        self.wait_until(
            lambda: self.html_lang() == "de"
            and self.i18n().get("current") == "de",
            timeout=15,
            message="I18N.set('de') hat die Sprache nicht umgestellt: "
                    + repr(self.i18n()) + " lang=" + repr(self.html_lang()))
        self.assert_not_english_tabs()
        self.assertEqual(
            "alive",
            self.page.evaluate("() => window.__ap21Marker || null"),
            "I18N.set('de') hat die Seite neu geladen")

        self.page.evaluate(
            "() => { const api = window.VIBE_I18N "
            "|| (typeof I18N !== 'undefined' ? I18N : null); api.set('en'); }")
        self.wait_until(
            lambda: self.html_lang() == "en"
            and self.i18n().get("current") == "en",
            timeout=15,
            message="I18N.set('en') hat die Sprache nicht zurückgestellt: "
                    + repr(self.i18n()) + " lang=" + repr(self.html_lang()))
        self.assert_english_tabs()
        self.assert_clean_page()

    def test_translation_interpolates_variables(self):
        """VP5: ``t(key, vars)`` löst ``{{var}}`` auf.

        Vorbedingung: Seite geladen.
        Aktion: ``I18N.t('ap21.test.{{name}}', {name: 'Vibe'})``.
        Erwartung: Ergebnis enthält ``Vibe`` und kein ``{{``.
        Fehlerfall: Platzhalter bleibt stehen oder die Interpolation wirft.
        """
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.wait_for_i18n()
        value = self.page.evaluate(
            "() => { const api = window.VIBE_I18N "
            "|| (typeof I18N !== 'undefined' ? I18N : null); "
            "return api.t('ap21.test.{{name}}', {name: 'Vibe'}); }")
        self.assertIsInstance(
            value, str,
            "t() mit Variablen liefert keinen String: " + repr(value))
        self.assertIn(
            "Vibe", value,
            "Die Interpolation setzt {{name}} nicht ein: " + repr(value))
        self.assertNotIn(
            "{{", value,
            "Die Interpolation lässt einen Platzhalter stehen: " + repr(value))
        self.assert_clean_page()


class RegressionTest(AP21BrowserTest):
    def test_ap20_output_overview_and_subagent_containers_remain(self):
        """VP6: Die AP20-Ausgabeansicht bleibt trotz Übersetzung erhalten.

        Vorbedingung: aktiver Lauf, ein laufender Subagent.
        Aktion: Ausgabebereich öffnen und Struktur auslesen.
        Erwartung: ``[data-panel='ausgabe']`` sichtbar; darin eine
        ``.bv-overview`` und ein ``.bv-subs``; englische Oberfläche; keine
        JS-Fehler.
        Fehlerfall: Die Übersetzung entfernt die AP20-Struktur oder benennt
        die Panel-Kennung um.
        """
        self.open_project()
        self.open_tab("ausgabe")
        panel = self.page.locator("[data-panel='ausgabe']")
        panel.wait_for(state="visible", timeout=15000)

        self.assertEqual(
            1, panel.locator(".bv-overview").count(),
            "Die AP20-Statusübersicht .bv-overview fehlt im Ausgabebereich")
        self.assertEqual(
            1, panel.locator(".bv-subs").count(),
            "Der AP20-Container .bv-subs fehlt im Ausgabebereich")
        self.wait_until(
            lambda: panel.locator(
                f"[data-agent-view][data-role='subagent']"
                f"[data-session='{SUB_SESSION}']").count() == 1,
            timeout=20,
            message="Der laufende Subagent erscheint nicht in der "
                    "Ausgabeansicht")
        self.assert_language("en")
        self.assert_clean_page()

    def test_number_and_currency_formatting_follow_the_language(self):
        """VP7: Zahlen/Währung richten sich nach der Sprache (en-US/de-DE).

        Vorbedingung: Projekt geöffnet.
        Aktion: ``I18N.set('en')``/``set('de')`` und den Formatierer
        (``I18N.formatNumber``/``formatCurrency`` bzw. ``fmtN``/``fmtEUR``)
        auf ``1234.5`` anwenden.
        Erwartung: Englisch ``1,234.5``, Deutsch ``1.234,5``; ist ein
        Währungsformatierer vorhanden, gilt dieselbe Trennerlogik.
        Fehlerfall: Die Formatierung bleibt fest auf ``de-DE``.
        """
        self.open_project()

        english = self.page.evaluate(FORMATTER_JS, "en")
        self.assertEqual(
            "en", english.get("current"),
            "Der Formatierer-Test konnte nicht auf Englisch umstellen: "
            + repr(english))
        self.assertTrue(
            english.get("hasNumber"),
            "Kein sprachabhängiger Zahlenformatierer gefunden (erwartet "
            "I18N.formatNumber/I18N.number oder window.fmtN)")
        self.assertIn(
            "1,234.5", english.get("number") or "",
            "Englische Zahlenformatierung ist nicht en-US: "
            + repr(english.get("number")))

        german = self.page.evaluate(FORMATTER_JS, "de")
        self.assertEqual("de", german.get("current"),
                         "Der Formatierer-Test konnte nicht auf Deutsch "
                         "umstellen: " + repr(german))
        self.assertIn(
            "1.234,5", german.get("number") or "",
            "Deutsche Zahlenformatierung ist nicht de-DE: "
            + repr(german.get("number")))

        if english.get("hasCurrency"):
            self.assertIn(
                "1,234.5", english.get("currency") or "",
                "Englische Währungsformatierung ist nicht en-US: "
                + repr(english.get("currency")))
            self.assertIn(
                "1.234,5", german.get("currency") or "",
                "Deutsche Währungsformatierung ist nicht de-DE: "
                + repr(german.get("currency")))
        self.assert_clean_page()


class ComposedAndProtocolTest(AP21BrowserTest):
    """M1/M2: Zusammengesetzte Meldungen und Nutzerdaten beim Sprachwechsel."""

    PROTOCOL_LINE = (
        "PROTOKOLL-AP21-M2: Fehler und Standard bleiben unverändert.")
    MESSAGE_EN = (
        "Unknown IDs in the saved priority list (not in this project): "
        "XX9. They will be removed on the next save.")
    MESSAGE_DE = (
        "Unbekannte Kennungen in der gespeicherten Priorisierung (nicht in "
        "diesem Projekt): XX9. Sie werden beim nächsten Speichern entfernt.")

    def set_package_order(self, value):
        """Schreibt ``PACKAGE_ORDER`` vor dem Öffnen und stellt danach zurück.

        Die Priorisierung wird aus ``.vibe/project.env`` gelesen. Der
        Projektordner ist klassenweit geteilt; der Cleanup verhindert, dass
        die unbekannte Kennung andere Fälle dieser Klasse verändert.
        """
        env = self.project / ".vibe" / "project.env"
        original = env.read_text(encoding="utf-8")
        self.addCleanup(env.write_text, original, encoding="utf-8")
        env.write_text(
            original.rstrip("\n") + "\nPACKAGE_ORDER=" + value + "\n",
            encoding="utf-8")

    def hint_locator(self):
        """Die zusammengesetzte Hinweismeldung der Karte „Offene Pakete“."""
        return self.page.locator(
            "[data-open-packages-card] div.mut", has_text="XX9")

    def hint_text(self):
        locator = self.hint_locator()
        try:
            if locator.count() == 0:
                return ""
            return locator.first.inner_text().strip()
        except Exception:  # Re-Render tauscht den Knoten kurz aus
            return ""

    def set_language(self, lang):
        self.page.evaluate(
            "lang => (window.VIBE_I18N || window.I18N).set(lang)", lang)
        self.wait_until(
            lambda: self.html_lang() == lang,
            timeout=15,
            message=f"<html lang> wurde nicht auf {lang!r} gestellt: "
                    + repr(self.html_lang()))

    def test_composed_message_switches_language_consistently(self):
        """M1: Eine zusammengesetzte Meldung wechselt vollständig die Sprache.

        Vorbedingung: ``PACKAGE_ORDER=XX9`` in ``.vibe/project.env``; die
        Karte „Offene Arbeitspakete“ zeigt deshalb den unbekannten Eintrag
        ``XX9``; Englisch ist aktiv.
        Aktion: Meldung lesen, ``I18N.set('de')``, Meldung erneut lesen,
        ``I18N.set('en')``, Meldung erneut lesen.
        Erwartung: Nach jedem Wechsel ist die Meldung vollständig in genau
        einer Sprache; die Kennung ``XX9`` bleibt unverändert.
        Fehlerfall: Nur ein Fragment wechselt (gemischtsprachige Meldung)
        oder der Hinweis bleibt in der alten Sprache stehen.
        """
        self.set_package_order("XX9")
        self.open_project()
        self.open_tab("arbeit")

        self.wait_until(
            lambda: self.hint_text() == self.MESSAGE_EN,
            timeout=20,
            message="Die zusammengesetzte Meldung ist nicht vollständig "
                    "englisch: " + repr(self.hint_text()))
        english = self.hint_text()
        self.assertNotIn(
            "Unbekannte", english,
            "Englische Meldung enthält noch ein deutsches Fragment: "
            + repr(english))
        self.assertIn("XX9", english,
                      "Die Kennung XX9 fehlt in der englischen Meldung: "
                      + repr(english))

        self.set_language("de")
        self.wait_until(
            lambda: self.hint_text() == self.MESSAGE_DE,
            timeout=20,
            message="Die zusammengesetzte Meldung ist nach dem Wechsel auf "
                    "Deutsch nicht vollständig deutsch: "
                    + repr(self.hint_text()))
        german = self.hint_text()
        self.assertNotIn(
            "Unknown", german,
            "Deutsche Meldung enthält noch ein englisches Fragment: "
            + repr(german))
        self.assertNotIn(
            "They will be removed", german,
            "Deutsche Meldung enthält noch den englischen Folgesatz: "
            + repr(german))
        self.assertIn("XX9", german,
                      "Die Kennung XX9 fehlt in der deutschen Meldung: "
                      + repr(german))

        self.set_language("en")
        self.wait_until(
            lambda: self.hint_text() == self.MESSAGE_EN,
            timeout=20,
            message="Die zusammengesetzte Meldung ist nach dem Rückwechsel "
                    "nicht wieder vollständig englisch: "
                    + repr(self.hint_text()))
        restored = self.hint_text()
        self.assertNotIn("Unbekannte", restored,
                         "Rückwechsel lässt ein deutsches Fragment stehen: "
                         + repr(restored))
        self.assert_clean_page()

    def protocol_lines(self):
        """Alle sichtbaren Protokollzeilen, die die Testkennung tragen."""
        log = self.page.locator(
            "[data-panel='ausgabe'] [data-agent-view][data-role='main'] "
            ".bv-log")
        if log.count() == 0:
            return []
        text = log.first.inner_text()
        return [line.strip() for line in text.splitlines()
                if "PROTOKOLL-AP21-M2" in line]

    def assert_protocol_unchanged(self, stage):
        lines = self.protocol_lines()
        self.assertTrue(
            lines,
            f"{stage}: Der Protokolltext ist nicht sichtbar: "
            + repr(self.page.locator(
                "[data-panel='ausgabe']").inner_text()[:400]))
        for line in lines:
            self.assertEqual(
                self.PROTOCOL_LINE, line,
                f"{stage}: Der Protokolltext wurde verändert: {line!r}")
        joined = "\n".join(lines)
        self.assertNotIn(
            "Error", joined,
            f"{stage}: „Fehler“ wurde als „Error“ übersetzt: {joined!r}")
        self.assertNotIn(
            "Default", joined,
            f"{stage}: „Standard“ wurde als „Default“ übersetzt: {joined!r}")

    def test_protocol_and_user_data_stay_untranslated(self):
        """M2: Protokoll-/Nutzerdaten bleiben beim Sprachwechsel wörtlich.

        Vorbedingung: Das Hauptprotokoll enthält die Nutzerdatenzeile
        ``PROTOKOLL-AP21-M2: Fehler und Standard bleiben unverändert.``;
        die Ausgabe ist geöffnet.
        Aktion: Protokolltext lesen; ``I18N.set('de')``; erneut lesen;
        ``I18N.set('en')``; erneut lesen.
        Erwartung: Der Protokolltext bleibt in allen drei Zuständen wörtlich
        identisch, „Fehler“/„Standard“ werden nie zu „Error“/„Default“.
        Fehlerfall: Der Sprachwechsel greift auf Protokoll-/Nutzerdaten zu.
        """
        self.open_project(log_lines=[self.PROTOCOL_LINE, MAIN_MARKER])
        self.open_tab("ausgabe")

        self.wait_until(
            lambda: self.protocol_lines(),
            timeout=20,
            message="Der Protokolltext erscheint nicht in der Ausgabe: "
                    + repr(self.page.locator(
                        "[data-panel='ausgabe']").inner_text()[:400]))
        before = self.protocol_lines()
        self.assert_protocol_unchanged("Englisch (vor dem Wechsel)")

        self.set_language("de")
        self.page.wait_for_timeout(600)  # Re-Render der aktiven Ansicht
        self.assert_language("de")
        self.assert_not_english_tabs()
        self.assert_protocol_unchanged("Deutsch")
        self.assertEqual(
            before, self.protocol_lines(),
            "Der Protokolltext änderte sich beim Wechsel auf Deutsch")

        self.set_language("en")
        self.page.wait_for_timeout(600)
        self.assert_language("en")
        self.assert_english_tabs()
        self.assert_protocol_unchanged("Englisch (nach dem Rückwechsel)")
        self.assertEqual(
            before, self.protocol_lines(),
            "Der Protokolltext änderte sich beim Rückwechsel auf Englisch")
        self.assert_clean_page()


class ReviewRound2Test(AP21BrowserTest):
    """Review-Runde 2: englische Masken, dynamische Labels und Backend-Toasts.

    Der Fall bildet die vier vom Reviewer benannten Oberflächen ab und prüft
    jede zunächst in Englisch und danach in Deutsch (Umkehrung). Die Prüfung
    ist bewusst eng am sichtbaren Vertrag: exakte englische Texte, keine
    deutschen Reste in den jeweils geprüften Elementen und unveränderte
    Kennungen/Pfade.
    """

    AGENTS_FILE_PATTERN = "**/api/agents_file*"
    # Antwortform von ``vibe.agents_file_view``; hält den Ladezustand an,
    # bis der Test den Text „Loading AGENTS.md …“ geprüft hat.
    AGENTS_FILE_STUB = {
        "exists": True,
        "digest": "review-round2",
        "before": "",
        "managed": "verwalteter Block",
        "after": "",
    }

    def set_language(self, lang):
        self.page.evaluate(
            "lang => (window.VIBE_I18N || window.I18N).set(lang)", lang)
        self.wait_until(
            lambda: self.html_lang() == lang,
            timeout=15,
            message=f"<html lang> wurde nicht auf {lang!r} gestellt: "
                    + repr(self.html_lang()))
        # rerenderView() tauscht die aktive Ansicht nach ~30 ms aus. Der
        # kurze Puffer verhindert, dass Klicks auf einem abgelösten Knoten
        # landen; die inhaltlichen Prüfungen warten zusätzlich explizit.
        self.page.wait_for_timeout(700)

    def text_of(self, locator):
        """Robuster Text eines Locators; Re-Render darf den Knoten tauschen."""
        try:
            if locator.count() == 0:
                return ""
            return locator.first.inner_text().strip()
        except Exception:
            return ""

    def wait_text(self, locator, expected, timeout=20, message=""):
        self.wait_until(
            lambda: self.text_of(locator) == expected,
            timeout=timeout,
            message=message or (
                f"Text ist nicht {expected!r}, sondern "
                + repr(self.text_of(locator))))

    def guide_step(self, step_id):
        return self.page.locator(
            f"#guide .gstep[data-step='{step_id}']")

    def guide_field(self, step_id, selector):
        return self.guide_step(step_id).locator(selector).first

    def expand_optional(self, selector):
        """Klappt einen <details>-Abschnitt auf (Muster aus AP7)."""
        summary = self.page.locator(selector + " > summary")
        if summary.count():
            section = self.page.locator(selector).first
            section.evaluate("el => el.scrollIntoView({block: 'center'})")
            if not section.evaluate("el => !!el.open"):
                summary.click()
                self.wait_until(
                    lambda: section.evaluate("el => !!el.open"),
                    message=f"{selector} ließ sich nicht aufklappen")

    # ---------- Projektassistent ----------

    def assert_guide_language(self, lang):
        if lang == "en":
            header = "Project assistant"
            steps = {
                "ziel": (
                    "Product goal",
                    "What problem does the project solve and what benefit "
                    "does it provide?",
                    "One to three sentences. No technical solution, but the "
                    "domain purpose.",
                    "missing",
                ),
                "nutzer": (
                    "Target group and usage",
                    "Who uses the product and in which situation?",
                    "Roles, typical tasks and the place of use.",
                    "missing",
                ),
            }
            forbidden = [
                "Produktziel", "Zielgruppe", "Welches Problem", "Wer nutzt",
                "Ein bis drei Sätze", "Rollen, typische", "fehlt", "Pflicht",
            ]
        else:
            header = "Projektassistent"
            steps = {
                "ziel": (
                    "Produktziel",
                    "Welches Problem löst das Projekt und welchen Nutzen "
                    "stiftet es?",
                    "Ein bis drei Sätze. Keine technische Lösung, sondern "
                    "der fachliche Zweck.",
                    "fehlt",
                ),
                "nutzer": (
                    "Zielgruppe und Nutzung",
                    "Wer nutzt das Produkt und in welcher Situation?",
                    "Rollen, typische Aufgaben und der Ort der Nutzung.",
                    "fehlt",
                ),
            }
            forbidden = [
                "Product goal", "Target group", "What problem", "Who uses",
                "One to three sentences", "Roles, typical", "missing",
            ]

        self.wait_until(
            lambda: header in self.text_of(self.page.locator("#guide")),
            timeout=20,
            message=f"Der Projektassistent ist nicht {lang}: "
                    + repr(self.text_of(self.page.locator("#guide"))[:400]))
        header_text = self.text_of(self.page.locator("#guide .bar").first)
        self.assertIn(header, header_text,
                      "Der Kopf des Projektassistenten ist nicht in der "
                      f"erwarteten Sprache: {header_text!r}")
        for needle in forbidden:
            self.assertNotIn(
                needle.lower(), header_text.lower(),
                "Der Projektassistent-Kopf enthält einen Text der falschen "
                f"Sprache ({needle!r}): {header_text!r}")

        for step_id, (title, question, help_text, status) in steps.items():
            self.wait_text(
                self.guide_field(step_id, ".bar b"), title,
                message=f"Schritt {step_id!r} hat nicht den Titel {title!r}: "
                        + repr(self.text_of(
                            self.guide_field(step_id, ".bar b"))))
            self.assertEqual(
                question,
                self.text_of(self.guide_field(step_id, "label")),
                f"Die Frage von {step_id!r} ist nicht {lang}: "
                + repr(self.text_of(self.guide_field(step_id, "label"))))
            self.assertEqual(
                help_text,
                self.text_of(self.guide_field(step_id, "div.mut")),
                f"Die Hilfe von {step_id!r} ist nicht {lang}: "
                + repr(self.text_of(self.guide_field(step_id, "div.mut"))))
            self.assertEqual(
                status,
                self.text_of(self.guide_field(step_id, "span.pill")),
                f"Der Status von {step_id!r} ist nicht {lang}: "
                + repr(self.text_of(
                    self.guide_field(step_id, "span.pill"))))
            step_text = self.text_of(self.guide_step(step_id))
            for needle in forbidden:
                self.assertNotIn(
                    needle.lower(), step_text.lower(),
                    f"Schritt {step_id!r} enthält einen Text der falschen "
                    f"Sprache ({needle!r}): {step_text!r}")

    # ---------- Platzhalter, Lade-Text, aria-label ----------

    def hold_agents_file(self):
        """Hält die AGENTS.md-Antwort an, damit der Lade-Text prüfbar ist."""
        held = []
        self.page.route(
            self.AGENTS_FILE_PATTERN, lambda route: held.append(route))
        return held

    def release_agents_file(self, held):
        # Zuerst alle gepufferten Antworten beantworten und erst danach den
        # Handler entfernen. Umgekehrt würde Playwright die noch offenen
        # Routen an das Netz weiterreichen; dann käme die echte Serverantwort
        # (ohne verwalteten Block) statt der Teilansicht.
        while held:
            routes = list(held)
            held.clear()
            for route in routes:
                try:
                    route.fulfill(
                        status=200, content_type="application/json",
                        body=json.dumps(self.AGENTS_FILE_STUB))
                except Exception:
                    pass
        self.page.unroute(self.AGENTS_FILE_PATTERN)

    def assert_agents_file_language(self, lang):
        if lang == "en":
            title = "AGENTS.md — rules for agents"
            aria_before = "AGENTS.md: free section before the managed block"
            aria_after = "AGENTS.md: free section after the managed block"
            # Ohne verwalteten Block ersetzt die Karte den Platzhalter durch
            # einen eigenen Hinweis; beide Texte müssen englisch sein.
            allowed_before = {
                "Free text before the managed block",
                "No managed block present; this section stays empty.",
            }
            placeholder_after = "Free text after the managed block"
            forbidden = [
                "freier Teil", "Freier Text", "Kein verwalteter Block",
            ]
        else:
            title = "AGENTS.md — Regeln für Agenten"
            aria_before = "AGENTS.md: freier Teil vor dem verwalteten Block"
            aria_after = "AGENTS.md: freier Teil nach dem verwalteten Block"
            allowed_before = {
                "Freier Text vor dem verwalteten Block",
                "Kein verwalteter Block vorhanden; dieser Teil bleibt leer.",
            }
            placeholder_after = "Freier Text nach dem verwalteten Block"
            forbidden = [
                "free section", "Free text", "No managed block",
            ]

        before = self.page.locator(
            f"#guide textarea[aria-label='{aria_before}']")
        after = self.page.locator(
            f"#guide textarea[aria-label='{aria_after}']")
        before.wait_for(state="attached", timeout=20000)
        after.wait_for(state="attached", timeout=20000)
        self.assertIn(
            before.first.get_attribute("placeholder"), allowed_before,
            f"Der Platzhalter vor dem Block ist nicht {lang}: "
            + repr(before.first.get_attribute("placeholder")))
        self.assertEqual(
            placeholder_after, after.first.get_attribute("placeholder"),
            f"Der Platzhalter nach dem Block ist nicht {lang}: "
            + repr(after.first.get_attribute("placeholder")))

        guide_text = self.text_of(self.page.locator("#guide"))
        self.assertIn(title, guide_text,
                      f"Die AGENTS.md-Karte ist nicht {lang}: "
                      + repr(guide_text[:400]))
        for needle in forbidden:
            self.assertNotIn(
                needle.lower(), guide_text.lower(),
                f"Die AGENTS.md-Karte enthält einen Text der falschen "
                f"Sprache ({needle!r})")

    def assert_placeholder_language(self, lang):
        if lang == "en":
            placeholder = "/absolute/path"
            aria = "Write directory"
            forbidden = ["/absoluter/pfad", "Schreibverzeichnis"]
        else:
            placeholder = "/absoluter/pfad"
            aria = "Schreibverzeichnis"
            forbidden = ["/absolute/path", "Write directory"]

        field = self.page.locator(
            f"#settings-rechte input[aria-label='{aria}']")
        field.wait_for(state="attached", timeout=15000)
        self.assertEqual(
            placeholder, field.first.get_attribute("placeholder"),
            f"Der Pfad-Platzhalter ist nicht {lang}: "
            + repr(field.first.get_attribute("placeholder")))
        for needle in forbidden:
            self.assertNotIn(
                needle.lower(),
                (field.first.get_attribute("placeholder") or "").lower(),
                f"Der Pfad-Platzhalter enthält einen Text der falschen "
                f"Sprache ({needle!r})")

    def assert_focus_aria_language(self, lang):
        if lang == "en":
            pattern = r"(?i)\bfocus\b"
            forbidden = "fokussieren"
            main_aria = "Focus main agent"
        else:
            pattern = r"(?i)\bfokussieren\b"
            forbidden = "focus"
            main_aria = "Hauptagent fokussieren"

        self.open_tab("ausgabe")
        buttons = self.page.locator(
            "[data-panel='ausgabe'] button[data-focus-session]")
        self.wait_until(
            lambda: buttons.count() >= 2,
            timeout=20,
            message="Der Fokus-Knopf des Subagenten erscheint nicht: "
                    + repr(buttons.count()))
        arias = [
            buttons.nth(index).get_attribute("aria-label") or ""
            for index in range(buttons.count())
        ]
        joined = " | ".join(arias)
        self.assertRegex(
            joined, pattern,
            f"Kein Fokus-aria-label ist {lang}: {joined!r}")
        self.assertNotIn(
            forbidden.lower(), joined.lower(),
            f"Ein Fokus-aria-label ist noch in der falschen Sprache: "
            f"{joined!r}")
        self.assertIn(
            main_aria, arias,
            f"Das aria-label des Hauptagenten ist nicht {main_aria!r}: "
            f"{arias!r}")

    # ---------- Backend-Fehler-Toast ----------

    def assert_rights_error_toast_language(self, lang):
        if lang == "en":
            expected = "already allowed"
            add_label = "Add"
            forbidden = ["bereits erlaubt", "ist bereits", "Verzeichnis"]
        else:
            expected = "bereits erlaubt"
            add_label = "Hinzufügen"
            forbidden = ["already allowed", "directory"]

        self.open_tab("einstellungen")
        self.expand_optional("#settings-rechte")
        field = self.page.locator("#settings-rechte input").first
        field.fill("/tmp/opencode")
        add = self.page.locator("#settings-rechte input + button").first
        self.assertEqual(
            add_label, add.inner_text().strip(),
            f"Der Hinzufügen-Knopf ist nicht {lang}: "
            + repr(add.inner_text()))
        add.click()

        deadline = time.time() + 15
        text = ""
        texts = []
        last_seen = []
        while time.time() < deadline:
            texts = self.page.locator("#toasts .toast").all_inner_texts()
            if texts:
                last_seen = texts
            text = next(
                (candidate.strip() for candidate in texts
                 if expected.lower() in candidate.lower()), "")
            if text:
                break
            self.page.wait_for_timeout(100)
        else:
            self.fail(
                f"Der Backend-Toast ist nicht {lang}: {last_seen!r}")
        self.assertIn("/tmp/opencode", text,
                      "Der Backend-Toast verlor den unveränderten Pfad: "
                      + repr(text))
        for needle in forbidden:
            self.assertNotIn(
                needle.lower(), text.lower(),
                f"Der Backend-Toast enthält einen Text der falschen Sprache "
                f"({needle!r}): {text!r}")

    # ---------- Umgebungsprüfung ----------

    def assert_doctor_language(self, lang):
        if lang == "en":
            header = "Environment check"
            labels = ["VIBE folder writable", "free space on data partition"]
            forbidden = [
                "Umgebungsprüfung", "VIBE-Ordner beschreibbar", "freier Platz",
            ]
        else:
            header = "Umgebungsprüfung"
            labels = ["VIBE-Ordner beschreibbar",
                      "freier Platz auf Datenpartition"]
            forbidden = [
                "Environment check", "VIBE folder writable", "free space",
            ]

        body = self.page.locator("main")
        self.wait_until(
            lambda: header in self.text_of(body),
            timeout=60,
            message=f"Die Umgebungsprüfung ist nicht {lang}: "
                    + repr(self.text_of(body)[:400]))
        # Beim Sprachwechsel stellt ``retranslateDOM`` zuerst die
        # statischen Beschriftungen um; die dynamischen Doctor-Zeilen
        # kommen aus ``/api/doctor`` und werden erst beim folgenden
        # ``rerenderView`` neu aufgebaut. Deshalb auf die Labels warten,
        # statt sie im Übergangsfenster zu prüfen.
        self.wait_until(
            lambda: all(needle in self.text_of(body) for needle in labels),
            timeout=30,
            message=f"Die Doctor-Labels sind nicht {lang}: "
                    + repr(self.text_of(body)[:1000]))
        text = self.text_of(body)
        for needle in labels:
            self.assertIn(
                needle, text,
                f"Das dynamische Doctor-Label {needle!r} fehlt in {lang}: "
                + repr(text[:1000]))
        for needle in forbidden:
            self.assertNotIn(
                needle.lower(), text.lower(),
                f"Die Umgebungsprüfung enthält einen Text der falschen "
                f"Sprache ({needle!r})")

    def open_environment(self):
        self.page.locator("[data-t='env']").click()
        self.page.get_by_text("Environment check", exact=True).wait_for(
            timeout=60000)

    def test_round2_english_surfaces_and_german_reversal(self):
        """Review 2: vier Oberflächen englisch, deutsche Umkehrung intakt.

        Vorbedingung: Projekt geöffnet, ein laufender Subagent, Englisch.
        Aktion/Erwartung: siehe Modul-Dokumentation Punkt 15. Jede Oberfläche
        wird als eigenes Subtest in Englisch und Deutsch geprüft, damit ein
        einzelner Sprachfehler die übrigen Nachweise nicht verdeckt.
        Fehlerfall: Ein dynamischer Servertext, ein Toast, ein Platzhalter
        oder ein aria-label bleibt in der falschen Sprache stehen.
        """
        self.open_project()
        self.open_tab("assistent")
        self.wait_until(
            lambda: "Product goal" in self.text_of(
                self.page.locator("#guide .gstep[data-step='ziel']"))
            or "Projektassistent" in self.text_of(
                self.page.locator("#guide")),
            timeout=20,
            message="Der Projektassistent wurde nicht geladen: "
                    + repr(self.text_of(self.page.locator("#guide"))[:400]))

        with self.subTest(oberflaeche="Projektassistent", sprache="en"):
            self.set_language("en")
            self.assert_guide_language("en")

        with self.subTest(oberflaeche="Projektassistent", sprache="de"):
            self.set_language("de")
            self.assert_guide_language("de")

        # --- Platzhalter, Lade-Text und aria-label ---
        with self.subTest(oberflaeche="Platzhalter/Lade-Text/aria",
                          sprache="en"):
            # Der Lade-Text ist nur sichtbar, solange /api/agents_file
            # antwortet. Die Antwort wird angehalten und nach der Prüfung
            # mit einer gültigen Teilansicht beantwortet.
            held = self.hold_agents_file()
            old_guide = self.page.locator("#guide").element_handle()
            try:
                self.set_language("en")
                if old_guide is not None:
                    self.page.wait_for_function(
                        "element => !element.isConnected",
                        arg=old_guide, timeout=20000)
                self.wait_until(
                    lambda: held,
                    timeout=20,
                    message="Die AGENTS.md-Anfrage wurde nicht abgefangen")
                self.open_tab("assistent")
                guide_text = self.text_of(self.page.locator("#guide"))
                self.assertIn(
                    "Loading AGENTS.md …", guide_text,
                    "Der Lade-Text der AGENTS.md-Karte ist nicht englisch: "
                    + repr(guide_text[:600]))
                self.assertNotIn(
                    "Lade AGENTS.md", guide_text,
                    "Der deutsche Lade-Text ist im englischen Modus sichtbar: "
                    + repr(guide_text[:600]))
            finally:
                self.release_agents_file(held)
            self.assert_agents_file_language("en")

            self.open_tab("einstellungen")
            self.expand_optional("#settings-rechte")
            self.assert_placeholder_language("en")
            self.assert_focus_aria_language("en")

        with self.subTest(oberflaeche="Platzhalter/Lade-Text/aria",
                          sprache="de"):
            self.set_language("de")
            self.assert_agents_file_language("de")
            self.open_tab("einstellungen")
            self.expand_optional("#settings-rechte")
            self.assert_placeholder_language("de")
            self.assert_focus_aria_language("de")

        # --- Backend-Fehler-Toast ---
        with self.subTest(oberflaeche="Backend-Fehler-Toast", sprache="en"):
            self.set_language("en")
            self.assert_rights_error_toast_language("en")

        with self.subTest(oberflaeche="Backend-Fehler-Toast", sprache="de"):
            self.set_language("de")
            self.assert_rights_error_toast_language("de")

        # --- Umgebungsprüfung (Doctor) ---
        with self.subTest(oberflaeche="Umgebungsprüfung", sprache="en"):
            self.set_language("en")
            self.open_environment()
            self.assert_doctor_language("en")

        with self.subTest(oberflaeche="Umgebungsprüfung", sprache="de"):
            self.set_language("de")
            self.assert_doctor_language("de")

        self.assert_clean_page()


class ReviewRound3Test(AP21BrowserTest):
    """Review-Runde 3: Modellwerte, MCP-Toast und Status-Klassen.

    Die Fälle bilden die drei Nachforderungen des Reviewers ab:

    * Modelltabelle und Modellauswahl zeigen die Bewertungswerte aus
      ``data/models.json`` und das Label ``Aufwand, Daten`` im englischen
      Standard englisch; die deutsche Umkehrung bleibt deutsch.
    * Der MCP-Toggle-Toast (``aktiviert``/``deaktiviert``) ist im englischen
      Modus englisch.
    * Schreibrechte-Chip und MCP-Statuspille tragen trotz boxed
      ``tr()``-Strings die zustandsrichtige CSS-Klasse (``bad``/``ok``).

    Geprüft wird ausschließlich die tatsächliche Oberfläche des Dashboards;
    die Modellwerte stammen aus einem eigens angelegten Testkatalog, die
    MCP-Konfiguration aus einer globalen ``opencode.json`` im isolierten
    ``HOME``. Beide Fixtures werden nach dem Test wieder entfernt.
    """

    MODEL_ID = "opencode/beam-free"
    REMOVED_MODEL_ID = "opencode/beam-free-entfernt"
    PROBE_AGENT = "ap21-modell-probe"
    MCP_NAME = "ap21-mcp-pruefserver"

    # ---------- Helfer ----------

    def set_language(self, lang):
        self.page.evaluate(
            "lang => (window.VIBE_I18N || window.I18N).set(lang)", lang)
        self.wait_until(
            lambda: self.html_lang() == lang,
            timeout=15,
            message=f"<html lang> wurde nicht auf {lang!r} gestellt: "
                    + repr(self.html_lang()))
        # rerenderView() tauscht die aktive Ansicht nach ~30 ms aus.
        self.page.wait_for_timeout(700)

    def text_of(self, locator):
        try:
            if locator.count() == 0:
                return ""
            return locator.first.inner_text().strip()
        except Exception:
            return ""

    def wait_text(self, locator, expected, timeout=25, message=""):
        self.wait_until(
            lambda: self.text_of(locator) == expected,
            timeout=timeout,
            message=message or (
                f"Text ist nicht {expected!r}, sondern "
                + repr(self.text_of(locator))))

    def wait_contains(self, locator, needle, timeout=30):
        self.wait_until(
            lambda: needle in self.text_of(locator),
            timeout=timeout,
            message=f"Text {needle!r} fehlt: " + repr(self.text_of(locator)))

    def write_fixture(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.addCleanup(lambda: path.unlink(missing_ok=True))

    # ---------- Fixtures ----------

    @staticmethod
    def assertion(value, art="fakt"):
        return {
            "wert": value,
            "art": art,
            "quelle": "AP21-Testkatalog",
            "datum": "2026-11-19",
        }

    def seed_model_catalog(self):
        """Legt den Katalog unter ``_toolchain/models.json`` an.

        Die Werte sind absichtlich die echten deutschen Bewertungswerte aus
        ``data/models.json``; nur so prüft der Fall die Übersetzung und nicht
        einen künstlichen Schlüssel.
        """
        catalog = {
            "schema": 2,
            "version": "2026-11-19.1",
            "stand": "2026-11-19",
            "waehrung": "USD",
            "einheit": "1 Mio. Tokens",
            "hinweis": "Testkatalog der AP21-Review-Runde 3.",
            "quellen": [
                {"name": "AP21-Testkatalog", "datum": "2026-11-19"},
            ],
            "modelle": [{
                "id": self.MODEL_ID,
                "name": "Beam Free",
                "anbieter": "OpenCode Zen",
                "id_status": "bestaetigt",
                "id_beleg": {
                    "quelle": "AP21-Testkatalog", "datum": "2026-11-19"},
                "preis": {
                    "status": "unbekannt",
                    "grund": "Testkatalog ohne Tarif",
                },
                "fakten": {
                    "daten": self.assertion("keine Daten"),
                    "bild": self.assertion("ja"),
                },
                "einschaetzungen": {
                    "tempo": self.assertion("sehr schnell", "einschaetzung"),
                    "aufwand": self.assertion("hoch", "einschaetzung"),
                    "coder": self.assertion("bedingt", "einschaetzung"),
                    "reviewer": self.assertion("bedingt", "einschaetzung"),
                },
            }, {
                "id": self.REMOVED_MODEL_ID,
                "name": "Beam Free (entfernt)",
                "anbieter": "OpenCode Zen",
                "id_status": "entfernt",
                "entfernt_am": "2026-11-01",
                "entfernt_quelle": "AP21-Testkatalog",
                "preis": {
                    "status": "unbekannt",
                    "grund": "Testkatalog ohne Tarif",
                },
                "fakten": {
                    "daten": self.assertion("keine Daten"),
                    "bild": self.assertion("nein"),
                },
                "einschaetzungen": {
                    "tempo": self.assertion("langsam", "einschaetzung"),
                    "aufwand": self.assertion("gering", "einschaetzung"),
                },
            }],
        }
        self.write_fixture(
            self.root / "_toolchain" / "models.json",
            json.dumps(catalog, ensure_ascii=False, indent=1) + "\n")

    def seed_project_agent(self):
        """Systemweiter Probe-Agent plus Modellüberschreibung im Projekt."""
        agent_md = (
            "---\n"
            "description: AP21 probe agent for the model select\n"
            "mode: subagent\n"
            f"model: {self.MODEL_ID}\n"
            "---\n"
            "Probe.\n")
        self.write_fixture(
            self.root / "home" / ".config" / "opencode" / "agents"
            / f"{self.PROBE_AGENT}.md",
            agent_md)
        self.write_fixture(
            self.project / ".vibe" / "agents.json",
            json.dumps({
                "version": 2,
                "aktiv": [self.PROBE_AGENT],
                "modelle": {self.PROBE_AGENT: self.MODEL_ID},
            }, ensure_ascii=False, indent=1) + "\n")

    def seed_mcp_config(self):
        self.write_fixture(
            self.root / "home" / ".config" / "opencode" / "opencode.json",
            json.dumps({
                "mcp": {
                    self.MCP_NAME: {
                        "type": "local",
                        "command": ["true"],
                        "enabled": True,
                    },
                },
            }, ensure_ascii=False, indent=2) + "\n")

    # ---------- Modelltabelle und Modellauswahl ----------

    def model_row(self):
        return self.page.locator(
            f"tr[data-model-row='{self.MODEL_ID}']").first

    def open_models_card(self):
        self.page.locator("[data-t='agents']").click()
        self.page.locator("#models").wait_for(state="attached", timeout=60000)
        details = self.page.locator("#models details").first
        if not details.evaluate("el => !!el.open"):
            details.locator(":scope > summary").click()
        self.model_row().wait_for(state="visible", timeout=30000)

    def open_model_detail(self, model_id):
        """Öffnet die Detailzeile eines Modells und gibt sie zurück."""
        self.open_models_card()
        row = self.page.locator(
            f"tr[data-model-row='{model_id}']").first
        row.wait_for(state="visible", timeout=30000)
        detail = self.page.locator(
            f"tr[data-model-detail='{model_id}']").first
        if not detail.is_visible():
            row.click()
        detail.wait_for(state="visible", timeout=30000)
        return detail

    def assert_models_table(self, lang):
        if lang == "en":
            headers = [
                "Model", "Provider", "Price", "Speed", "Effort", "Data",
                "Images", "Coder", "Reviewer", "in use",
            ]
            values = [
                "very fast", "high", "no data", "yes",
                "conditional", "conditional",
            ]
            forbidden = [
                "Modell", "Anbieter", "Preis", "Tempo", "Aufwand", "Daten",
                "Bilder", "in Verwendung", "sehr schnell", "hoch",
                "keine Daten", "bedingt",
            ]
        else:
            headers = [
                "Modell", "Anbieter", "Preis", "Tempo", "Aufwand", "Daten",
                "Bilder", "Coder", "Reviewer", "in Verwendung",
            ]
            values = [
                "sehr schnell", "hoch", "keine Daten", "ja",
                "bedingt", "bedingt",
            ]
            forbidden = [
                "Model", "Provider", "Price", "Speed", "Effort", "Data",
                "Images", "in use", "very fast", "high", "no data",
                "conditional",
            ]

        header_texts = [
            text.strip() for text in
            self.page.locator("#models table tr").first.locator(
                "th").all_inner_texts()
        ]
        self.assertEqual(
            headers, header_texts,
            f"Die Kopfzeilen der Modelltabelle sind nicht {lang}: "
            + repr(header_texts))
        for needle in forbidden:
            self.assertNotIn(
                needle, header_texts,
                f"Die Kopfzeilen enthalten einen Text der falschen Sprache "
                f"({needle!r}): {header_texts!r}")

        cells = self.model_row().locator("td")
        cell_texts = [
            cells.nth(index).inner_text().strip() for index in range(10)]
        # Zellen 3..8: Tempo, Aufwand, Daten, Bilder, Coder, Reviewer.
        for offset, value in enumerate(values, start=3):
            self.assertEqual(
                value, cell_texts[offset],
                f"Die Modellzelle {offset} ist nicht {lang}: "
                + repr(cell_texts[offset]))
        cell_text = " | ".join(cell_texts)
        for needle in forbidden:
            self.assertNotIn(
                needle, cell_text,
                f"Die Modellzeile enthält einen Text der falschen Sprache "
                f"({needle!r}): {cell_text!r}")

        # Die Badge-Klasse hängt am deutschen Rohwert und bleibt in beiden
        # Sprachen gleich (Tempo = sehr schnell → ok, Aufwand = hoch → bad).
        self.assertEqual(
            "pill ok",
            self.model_row().locator("td").nth(3).locator(".pill").get_attribute(
                "class"),
            f"Die Tempo-Pille hat in {lang} nicht die Klasse 'ok'")
        self.assertEqual(
            "pill bad",
            self.model_row().locator("td").nth(4).locator(".pill").get_attribute(
                "class"),
            f"Die Aufwand-Pille hat in {lang} nicht die Klasse 'bad'")

    def model_option(self):
        select = self.page.locator(
            f"select[data-model-override='{self.PROBE_AGENT}']")
        select.wait_for(state="attached", timeout=60000)
        option = select.locator(f"option[value='{self.MODEL_ID}']").first
        option.wait_for(state="attached", timeout=30000)
        return option.text_content().strip()

    def assert_model_option(self, lang):
        text = self.model_option()
        if lang == "en":
            expected = ["very fast", "high", "effort, data", "no data"]
            forbidden = ["sehr schnell", "hoch", "Aufwand", "Daten",
                         "keine Daten"]
        else:
            expected = ["sehr schnell", "hoch", "Aufwand, Daten",
                        "keine Daten"]
            forbidden = ["very fast", "high", "effort, data", "no data"]
        for needle in expected:
            self.assertIn(
                needle, text,
                f"Die Modellauswahl zeigt {needle!r} nicht in {lang}: "
                + repr(text))
        for needle in forbidden:
            self.assertNotIn(
                needle, text,
                f"Die Modellauswahl enthält einen Text der falschen Sprache "
                f"({needle!r}): {text!r}")

    def test_models_table_and_select_are_english_and_german_reverses(self):
        """Review 3: Modellwerte und Labels englisch, deutsch unverändert.

        Vorbedingung: Testkatalog mit ``opencode/beam-free`` und ein
        systemweiter Probe-Agent mit Modellüberschreibung; Englisch aktiv.
        Aktion: Modellauswahl in den Projekteinstellungen und Modelltabelle
        in ``[data-t='agents']`` öffnen; beide in Englisch, danach in
        Deutsch lesen.
        Erwartung: ``very fast``, ``high``, ``conditional``, ``no data``,
        ``yes`` und ``effort, data`` sowie die englischen Kopfzeilen; auf
        Deutsch die unveränderten Originalwerte und ``Aufwand, Daten``.
        Fehlerfall: Ein Wert oder das Label bleibt in der falschen Sprache
        oder die Auswahl zeigt den Rohwert.
        """
        self.seed_model_catalog()
        self.seed_project_agent()
        self.open_project()
        self.set_language("en")
        self.assert_language("en")

        with self.subTest(oberflaeche="Modellauswahl", sprache="en"):
            self.open_tab("einstellungen")
            self.assert_model_option("en")

        with self.subTest(oberflaeche="Modelltabelle", sprache="en"):
            self.open_models_card()
            self.assert_models_table("en")

        with self.subTest(oberflaeche="Modelltabelle", sprache="de"):
            self.set_language("de")
            self.assert_language("de")
            self.open_models_card()
            self.assert_models_table("de")

        with self.subTest(oberflaeche="Modellauswahl", sprache="de"):
            # AP21 v2: kein Seiten-Reload. Die Wahl steht im localStorage und
            # waere nach einem Reload durch das Server-Meta ('en') ueberschrieben.
            # Clientseitig ueber die Projektliste zurueck ins Projekt.
            self.page.locator("[data-t='projects']").click()
            row = self.page.locator("tr.row", has_text="proj").first
            row.wait_for(state="visible", timeout=20000)
            row.click()
            self.tab_button("arbeit").wait_for(state="visible", timeout=20000)
            self.open_tab("einstellungen")
            self.assert_model_option("de")

        self.assert_clean_page()

    # ---------- Modell-Detailzeile ----------

    def assert_detail_status(self, lang):
        if lang == "en":
            confirmed = "ID status: confirmed"
            removed = "ID status: removed"
            forbidden = ["ID-Status", "bestaetigt", "entfernt"]
        else:
            confirmed = "ID-Status: bestaetigt"
            removed = "ID-Status: entfernt"
            forbidden = ["ID status", "confirmed", "removed"]

        detail = self.open_model_detail(self.MODEL_ID)
        self.wait_contains(detail, confirmed)
        text = self.text_of(detail)
        self.assertIn(
            confirmed, text,
            f"Der bestätigte ID-Status der Detailzeile ist nicht {lang}: "
            + repr(text[:1000]))
        for needle in forbidden:
            self.assertNotIn(
                needle, text,
                f"Die Detailzeile enthält einen Text der falschen Sprache "
                f"({needle!r}, {lang}): {text[:1000]!r}")

        removed_detail = self.open_model_detail(self.REMOVED_MODEL_ID)
        self.wait_contains(removed_detail, removed)
        removed_text = self.text_of(removed_detail)
        self.assertIn(
            removed, removed_text,
            f"Der entfernte ID-Status der Detailzeile ist nicht {lang}: "
            + repr(removed_text[:1000]))
        for needle in forbidden:
            self.assertNotIn(
                needle, removed_text,
                f"Die Detailzeile des entfernten Modells enthält einen Text "
                f"der falschen Sprache ({needle!r}, {lang}): "
                + repr(removed_text[:1000]))

    def test_model_detail_id_status_follows_language(self):
        """Review 3: ``id_status`` der aufgeklappten Detailzeile.

        Vorbedingung: Testkatalog mit ``bestaetigt`` und ``entfernt``; der
        Probe-Agent hält ``opencode/beam-free`` sichtbar.
        Aktion: Modelltabelle öffnen, die Detailzeile beider Modelle
        aufklappen und ``ID-Status`` lesen; danach auf Deutsch wiederholen.
        Erwartung: Englisch ``ID status: confirmed``/``ID status: removed``;
        deutsch ``ID-Status: bestaetigt``/``ID-Status: entfernt``, jeweils
        ohne den Statuswert der anderen Sprache.
        Fehlerfall: Der Rohwert bleibt deutsch oder Deutsch fällt auf den
        englischen Wörterbuchwert zurück.
        """
        self.seed_model_catalog()
        self.seed_project_agent()
        self.open_project()
        self.set_language("en")
        self.assert_language("en")

        with self.subTest(oberflaeche="Modell-Detailzeile", sprache="en"):
            self.assert_detail_status("en")

        with self.subTest(oberflaeche="Modell-Detailzeile", sprache="de"):
            self.set_language("de")
            self.assert_language("de")
            self.assert_detail_status("de")

        self.assert_clean_page()

    # ---------- MCP-Toggle und Statuspille ----------

    def mcp_row(self):
        return self.page.locator("tr", has_text=self.MCP_NAME).first

    def mcp_pill(self):
        return self.mcp_row().locator("td").nth(4).locator(".pill")

    def open_mcp(self):
        self.page.locator("[data-t='mcp']").click()
        self.mcp_row().wait_for(state="visible", timeout=30000)

    def wait_toast(self, expected, timeout=15):
        toast = self.page.locator("#toasts .toast .toasttext").first
        self.wait_until(
            lambda: self.text_of(toast) == expected,
            timeout=timeout,
            message=f"Der Toast ist nicht {expected!r}, sondern "
                    + repr(self.page.locator(
                        "#toasts .toast .toasttext").all_inner_texts()))

    def assert_mcp_pill(self, label, tone, lang):
        pill = self.mcp_pill()
        self.wait_text(
            pill, label,
            message=f"Die MCP-Statuspille ist in {lang} nicht {label!r}: "
                    + repr(self.text_of(pill)))
        classes = (pill.get_attribute("class") or "").split()
        self.assertIn(
            tone, classes,
            f"Die MCP-Statuspille trägt in {lang} nicht die Klasse {tone!r}: "
            + repr(classes))

    def test_mcp_toggle_toast_and_status_pill_follow_language(self):
        """Review 3: MCP-Toast und Statuspille in beiden Sprachen.

        Vorbedingung: globaler Server ``ap21-mcp-pruefserver`` in der isolierten
        ``opencode.json``, Englisch aktiv.
        Aktion: MCP-Ansicht öffnen; auf Englisch ausschalten, Toast und
        Pille lesen; auf Deutsch wieder einschalten, Toast und Pille lesen.
        Erwartung: ``ap21-mcp-pruefserver deactivated``/``ap21-mcp-pruefserver aktiviert``;
        Pille ``yes``/``no`` (englisch) bzw. ``ja``/``nein`` (deutsch) mit
        Klasse ``ok``/``bad``.
        Fehlerfall: Der Toast bleibt deutsch oder die Pille trägt wegen des
        boxed ``tr()``-Strings die Klasse ``mut``.
        """
        self.seed_mcp_config()
        self.page.goto(self.base + "/classic#t=" + self.token)
        self.wait_for_i18n()
        self.set_language("en")
        self.assert_language("en")

        with self.subTest(oberflaeche="MCP ausschalten", sprache="en"):
            self.open_mcp()
            self.assert_mcp_pill("yes", "ok", "en")
            toggle = self.mcp_row().locator("button").last
            self.assertEqual(
                "Turn off", toggle.inner_text().strip(),
                "Der MCP-Umschaltknopf ist nicht englisch: "
                + repr(toggle.inner_text()))
            toggle.click()
            self.wait_toast(self.MCP_NAME + " deactivated")
            self.assert_mcp_pill("no", "bad", "en")

        with self.subTest(oberflaeche="MCP einschalten", sprache="de"):
            self.set_language("de")
            self.assert_language("de")
            self.open_mcp()
            self.assert_mcp_pill("nein", "bad", "de")
            toggle = self.mcp_row().locator("button").last
            self.assertEqual(
                "Einschalten", toggle.inner_text().strip(),
                "Der MCP-Umschaltknopf ist nicht deutsch: "
                + repr(toggle.inner_text()))
            toggle.click()
            self.wait_toast(self.MCP_NAME + " aktiviert")
            self.assert_mcp_pill("ja", "ok", "de")

        self.assert_clean_page()

    # ---------- Schreibrechte-Chip ----------

    def test_write_access_chip_shows_bad_class_in_both_languages(self):
        """Review 3: Fehler-Chip trägt ``bad`` trotz boxed ``tr()``-String.

        Vorbedingung: absichtlich ungültige ``.vibe/permissions.json``,
        damit ``/api/project`` ``write_dirs_error`` meldet.
        Aktion: Einstellungen öffnen; Chip ``rechte`` in Englisch und
        Deutsch lesen.
        Erwartung: Pille ``Error``/``Fehler`` und Klasse ``bad`` (nicht
        ``mut``) in beiden Sprachen.
        Fehlerfall: ``tone('rechte')`` vergleicht den übersetzten String und
        der Chip bleibt neutral.
        """
        self.write_fixture(
            self.project / ".vibe" / "permissions.json",
            "{ absichtlich kein gültiges JSON\n")
        self.open_project()
        self.set_language("en")
        self.open_tab("einstellungen")

        chip = self.page.locator(
            "[data-panel='einstellungen'] .settings-nav "
            "[data-goto='rechte']")
        chip.wait_for(state="visible", timeout=30000)
        pill = chip.locator(".pill")

        with self.subTest(sprache="en"):
            self.wait_text(pill, "Error")
            classes = (pill.get_attribute("class") or "").split()
            self.assertIn(
                "bad", classes,
                "Der Schreibrechte-Chip trägt im englischen Modus nicht die "
                f"Klasse 'bad': {classes!r}")
            chip_text = chip.inner_text()
            self.assertIn(
                "Write access", chip_text,
                "Der Schreibrechte-Chip ist nicht englisch: "
                + repr(chip_text))
            self.assertNotIn(
                "Fehler", chip_text,
                "Der Schreibrechte-Chip zeigt im englischen Modus den "
                "deutschen Fehlertext: " + repr(chip_text))

        with self.subTest(sprache="de"):
            self.set_language("de")
            self.wait_text(pill, "Fehler")
            classes = (pill.get_attribute("class") or "").split()
            self.assertIn(
                "bad", classes,
                "Der Schreibrechte-Chip trägt im deutschen Modus nicht die "
                f"Klasse 'bad': {classes!r}")
            chip_text = chip.inner_text()
            self.assertIn(
                "Schreibrechte", chip_text,
                "Der Schreibrechte-Chip ist nicht deutsch: "
                + repr(chip_text))
            self.assertNotIn(
                "Error", chip_text,
                "Der Schreibrechte-Chip zeigt im deutschen Modus den "
                "englischen Fehlertext: " + repr(chip_text))

        self.assert_clean_page()

    def test_write_dirs_chip_count_follows_language(self):
        """Review 3: Zähler des Schreibrechte-Chips bei eigener Liste.

        Vorbedingung: gültige eigene ``.vibe/permissions.json`` mit zwei
        Schreibverzeichnissen (Projekt und ``/tmp/opencode``).
        Aktion: Einstellungen öffnen und den Sprungknopf ``rechte`` in
        Englisch und Deutsch lesen.
        Erwartung: Englisch ``2 directories``, deutsch ``2 Verzeichnisse``,
        jeweils mit dem Navigationstext der Sprache und ohne den Zähler der
        anderen Sprache.
        Fehlerfall: Der zusammengesetzte Zähler bleibt deutsch oder die
        Übersetzung entfernt die Anzahl.
        """
        self.write_fixture(
            self.project / ".vibe" / "permissions.json",
            json.dumps(
                {"write_dirs": [str(self.project), "/tmp/opencode"]},
                ensure_ascii=False, indent=1) + "\n")
        self.open_project()
        self.open_tab("einstellungen")
        chip = self.settings_nav_chip("rechte")
        chip.wait_for(state="visible", timeout=30000)

        with self.subTest(sprache="en"):
            self.set_language("en")
            self.wait_text(chip.locator(".pill"), "2 directories")
            chip_text = chip.inner_text()
            self.assertIn(
                "Write access", chip_text,
                "Der Schreibrechte-Chip ist nicht englisch: "
                + repr(chip_text))
            self.assertNotIn(
                "Verzeichnisse", chip_text,
                "Der Schreibrechte-Chip zeigt im englischen Modus den "
                "deutschen Zähler: " + repr(chip_text))

        with self.subTest(sprache="de"):
            self.set_language("de")
            self.wait_text(chip.locator(".pill"), "2 Verzeichnisse")
            chip_text = chip.inner_text()
            self.assertIn(
                "Schreibrechte", chip_text,
                "Der Schreibrechte-Chip ist nicht deutsch: "
                + repr(chip_text))
            self.assertNotIn(
                "directories", chip_text,
                "Der Schreibrechte-Chip zeigt im deutschen Modus den "
                "englischen Zähler: " + repr(chip_text))

        self.assert_clean_page()


if __name__ == "__main__":
    unittest.main()
