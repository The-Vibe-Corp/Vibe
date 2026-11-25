"""Internationalisierung: Modul, Metadaten, Sprache in der UI-Konfiguration und globaler Sprachserver.

Aufruf: python3 -m unittest tests.unit.test_i18n -v
"""


# ===========================================================================
# Unit-Abnahme: i18n-Infrastruktur ohne Browser
# ===========================================================================

import http.client
import importlib.machinery
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
I18N_JS = REPO / "bin" / "web" / "i18n.js"
CLASSIC_HTML = REPO / "bin" / "web" / "classic.html"
NODE = shutil.which("node")

HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const sourcePath = process.argv[1];

function makeStorage(initial) {
  const map = new Map(Object.entries(initial || {}));
  return {
    get length() { return map.size; },
    key(i) {
      const keys = Array.from(map.keys());
      return i >= 0 && i < keys.length ? keys[i] : null;
    },
    getItem(k) { k = String(k); return map.has(k) ? map.get(k) : null; },
    setItem(k, v) { map.set(String(k), String(v)); },
    removeItem(k) { map.delete(String(k)); },
    clear() { map.clear(); },
    dump() { return Object.fromEntries(map); }
  };
}

function boot(storage) {
  const element = {
    lang: '',
    setAttribute(name, value) { this[name] = String(value); },
    getAttribute(name) { return name in this ? this[name] : null; }
  };
  const document = {
    documentElement: element,
    readyState: 'complete',
    cookie: '',
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() { return true; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    getElementById() { return null; },
    createElement() {
      return {style: {}, setAttribute() {}, appendChild() {},
              addEventListener() {}};
    },
    createTextNode() { return {}; },
    head: {appendChild() {}},
    body: {appendChild() {}}
  };
  class CustomEvent {
    constructor(type, options) {
      this.type = type;
      this.detail = options && options.detail;
    }
  }
  class Event {
    constructor(type, options) {
      this.type = type;
      this.detail = options && options.detail;
    }
  }
  const sandbox = {
    console,
    document,
    localStorage: storage,
    matchMedia() {
      return {matches: false, media: '', addListener() {},
              removeListener() {}, addEventListener() {},
              removeEventListener() {}};
    },
    getComputedStyle() { return {}; },
    requestAnimationFrame(callback) { if (callback) callback(0); return 0; },
    cancelAnimationFrame() {},
    Event,
    // Bewusst deutsch: Der Standard muss trotzdem Englisch sein.
    navigator: {language: 'de-DE', languages: ['de-DE', 'de']},
    location: {href: 'http://127.0.0.1/', search: '', hash: ''},
    Intl, JSON, Object, Array, String, Number, Boolean, Date, Math,
    RegExp, Error, Map, Set, Promise, CustomEvent,
    setTimeout, clearTimeout

  };
  sandbox.window = sandbox;
  sandbox.self = sandbox;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(sourcePath, 'utf8'), sandbox,
                  {filename: 'i18n.js'});
  const alias = vm.runInContext(
    "(typeof I18N !== 'undefined') ? I18N : null", sandbox);
  const api = sandbox.VIBE_I18N || alias || sandbox.I18N || null;
  return {api, alias, element, sandbox};
}

const out = {modulePresent: false};
try {
  const storage = makeStorage();
  const first = boot(storage);
  out.modulePresent = !!first.api;
  out.aliasPresent = !!first.alias || !!first.sandbox.I18N
    || !!(first.sandbox.window && first.sandbox.window.VIBE_I18N);
  if (first.api) {
    out.functions = ['available', 'current', 'set', 't']
      .filter(name => typeof first.api[name] === 'function');
    out.available = typeof first.api.available === 'function'
      ? first.api.available() : null;
    out.fresh = typeof first.api.current === 'function'
      ? first.api.current() : null;
    out.freshLang = first.element.lang;
    out.unknown = typeof first.api.t === 'function'
      ? first.api.t('ap21.unknown.key.4711') : null;
    out.interpolated = typeof first.api.t === 'function'
      ? first.api.t('ap21.test.{{name}}', {name: 'Vibe'}) : null;
    out.setError = null;
    try {
      first.api.set('de');
    } catch (error) {
      out.setError = String((error && error.message) || error);
    }
    out.afterDe = typeof first.api.current === 'function'
      ? first.api.current() : null;
    out.afterDeLang = first.element.lang;
    out.stored = storage.dump();

    const second = boot(storage);
    out.persisted = second.api && typeof second.api.current === 'function'
      ? second.api.current() : null;
    try {
      second.api.set('en');
    } catch (error) {
      out.secondSetError = String((error && error.message) || error);
    }
    out.afterEn = second.api && typeof second.api.current === 'function'
      ? second.api.current() : null;
    out.afterEnLang = second.element.lang;
  }
} catch (error) {
  out.error = String((error && error.stack) || error);
}
process.stdout.write(JSON.stringify(out));
"""


@unittest.skipUnless(NODE, "node fehlt: i18n-Unitprüfung nicht ausführbar")
class I18nModuleTest(unittest.TestCase):
    """Reine i18n-Logik aus ``bin/web/i18n.js`` über eine Node-vm."""

    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            [NODE, "-e", HARNESS, str(I18N_JS)],
            capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise AssertionError(
                "Node-vm konnte i18n.js nicht laden (returncode "
                f"{result.returncode}):\n{result.stdout}\n{result.stderr}")
        try:
            cls.data = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as error:
            raise AssertionError(
                "Die i18n-Probe lieferte kein JSON: "
                + repr(result.stdout) + " / " + str(error))

    def test_module_exists_and_exposes_public_api(self):
        """Fall 1: i18n.js stellt VIBE_I18N (Alias I18N) vollständig bereit."""
        self.assertTrue(
            I18N_JS.is_file(),
            "bin/web/i18n.js fehlt (die i18n-Infrastruktur ist nicht "
            "angelegt)")
        data = self.data
        self.assertNotIn("error", data,
                         "i18n.js warf beim Laden einen Fehler: "
                         + repr(data.get("error")))
        self.assertTrue(
            data.get("modulePresent"),
            "window.VIBE_I18N fehlt nach dem Laden von i18n.js: "
            + repr(data))
        self.assertTrue(
            data.get("aliasPresent"),
            "Der Alias I18N ist nicht global erreichbar: " + repr(data))
        self.assertEqual(
            {"available", "current", "set", "t"},
            set(data.get("functions") or []),
            "Die i18n-API ist unvollständig: "
            + repr(data.get("functions")))

    def test_classic_html_loads_i18n_before_app(self):
        """Fall 2: classic.html lädt /static/i18n.js vor /static/app.js."""
        self.assertTrue(
            CLASSIC_HTML.is_file(), "bin/web/classic.html fehlt")
        html = CLASSIC_HTML.read_text(encoding="utf-8")
        i18n_pos = html.find('/static/i18n.js')
        app_pos = html.find('/static/app.js')
        self.assertNotEqual(
            -1, i18n_pos,
            "classic.html lädt /static/i18n.js nicht")
        self.assertNotEqual(
            -1, app_pos,
            "classic.html lädt /static/app.js nicht")
        self.assertLess(
            i18n_pos, app_pos,
            "classic.html lädt i18n.js erst nach app.js: "
            + repr(html[max(0, min(i18n_pos, app_pos) - 40):
                        max(i18n_pos, app_pos) + 40]))

    def test_available_languages_include_english_and_german(self):
        """Fall 3: available() enthält en und de, Englisch zuerst."""
        available = self.data.get("available")
        self.assertIsInstance(
            available, list,
            "available() liefert keine Liste: " + repr(available))
        self.assertTrue(
            {"en", "de"}.issubset(set(available)),
            "available() enthält nicht en und de: " + repr(available))
        self.assertEqual(
            "en", available[0] if available else None,
            "available() beginnt nicht mit Englisch: " + repr(available))

    def test_fresh_profile_defaults_to_english(self):
        """Fall 4: Ohne gespeicherte Wahl ist Englisch Standard.

        Der Browser meldet in der Probe ``de-DE``; das darf den Standard
        nicht überschreiben (Ticket: „standard englisch“).
        """
        self.assertEqual(
            "en", self.data.get("fresh"),
            "current() ist bei frischem Profil nicht 'en': "
            + repr(self.data.get("fresh")))

    def test_set_updates_current_and_html_lang(self):
        """Fall 5: set('de')/set('en') stellen current() und lang sofort um."""
        self.assertIsNone(
            self.data.get("setError"),
            "set('de') warf einen Fehler: " + repr(self.data.get("setError")))
        self.assertEqual(
            "de", self.data.get("afterDe"),
            "set('de') stellt current() nicht um: " + repr(self.data))
        self.assertEqual(
            "de", self.data.get("afterDeLang"),
            "set('de') aktualisiert <html lang> nicht: " + repr(self.data))
        self.assertEqual(
            "en", self.data.get("afterEn"),
            "set('en') stellt current() nicht zurück: " + repr(self.data))
        self.assertEqual(
            "en", self.data.get("afterEnLang"),
            "set('en') aktualisiert <html lang> nicht: "
            + repr(self.data.get("afterEnLang")))

    def test_set_persists_choice_for_next_page_load(self):
        """Fall 6: Die Wahl steht in localStorage und überlebt den Neuaufbau."""
        stored = self.data.get("stored") or {}
        self.assertIn(
            "de", list(stored.values()),
            "set('de') speichert die Sprache nicht in localStorage: "
            + repr(stored))
        self.assertEqual(
            "de", self.data.get("persisted"),
            "Ein neuer Seitenaufbau liest die gespeicherte Sprache nicht: "
            + repr(self.data.get("persisted")))

    def test_unknown_key_returns_key(self):
        """Fall 7: t() liefert bei unbekanntem Key den Key selbst."""
        self.assertEqual(
            "ap21.unknown.key.4711", self.data.get("unknown"),
            "Ein unbekannter Key liefert nicht den Key selbst: "
            + repr(self.data.get("unknown")))

    def test_translation_interpolates_variables(self):
        """Fall 8: t(key, vars) ersetzt {{var}}."""
        value = self.data.get("interpolated")
        self.assertIsInstance(
            value, str,
            "t() mit Variablen liefert keinen String: " + repr(value))
        self.assertIn(
            "Vibe", value,
            "Die Interpolation setzt {{name}} nicht ein: " + repr(value))
        self.assertNotIn(
            "{{", value,
            "Die Interpolation lässt einen Platzhalter stehen: "
            + repr(value))


# ---------------------------------------------------------------------------
# AP21 v2: globale, serverseitig persistierte Sprache.
#
# Die Sprache ist keine Projekt- und keine reine Browser-Einstellung mehr:
# Sie liegt zentral in <state>/ui.json unter "language" (Standard "en").
# Der Server injiziert sie in <html lang> und <meta name="vibe-language">;
# i18n.js liest das Meta-Feld (vollstaendig validiert) vor localStorage.
# ---------------------------------------------------------------------------

META_HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const sourcePath = process.argv[1];
const metaContent = process.argv[2];           // '' = kein Meta-Feld
let initial = {};
try { initial = JSON.parse(process.argv[3] || '{}'); } catch (e) { initial = {}; }

const map = new Map(Object.entries(initial));
const storage = {
  getItem(k) { return map.has(String(k)) ? map.get(String(k)) : null; },
  setItem(k, v) { map.set(String(k), String(v)); },
  removeItem(k) { map.delete(String(k)); },
  clear() { map.clear(); },
  dump() { return Object.fromEntries(map); }
};
const meta = metaContent === '' ? null :
  {getAttribute(n) { return n === 'content' ? metaContent : null; }, content: metaContent};
const element = {
  lang: '',
  setAttribute(name, value) { this[name] = String(value); },
  getAttribute(name) { return name in this ? this[name] : null; }
};
const document = {
  documentElement: element,
  readyState: 'complete',
  cookie: '',
  addEventListener() {}, removeEventListener() {}, dispatchEvent() { return true; },
  querySelector(sel) { return sel.indexOf('vibe-language') !== -1 ? meta : null; },
  querySelectorAll() { return []; },
  getElementById() { return null; },
  createElement() { return {style: {}, setAttribute() {}, appendChild() {}, addEventListener() {}}; },
  createTextNode() { return {}; },
  head: {appendChild() {}}, body: {appendChild() {}}
};
class CustomEvent { constructor(type, options) { this.type = type; this.detail = options && options.detail; } }
class Event { constructor(type, options) { this.type = type; this.detail = options && options.detail; } }
const sandbox = {
  console, document, localStorage: storage, CustomEvent, Event,
  matchMedia() { return {matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}}; },
  getComputedStyle() { return {}; },
  requestAnimationFrame(cb) { if (cb) cb(0); return 0; }, cancelAnimationFrame() {},
  navigator: {language: 'de-DE', languages: ['de-DE', 'de']},
  location: {href: 'http://127.0.0.1/', search: '', hash: ''},
  Intl, JSON, Object, Array, String, Number, Boolean, Date, Math,
  RegExp, Error, Map, Set, Promise, setTimeout, clearTimeout
};
sandbox.window = sandbox; sandbox.self = sandbox; sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(sourcePath, 'utf8'), sandbox, {filename: 'i18n.js'});
const api = sandbox.VIBE_I18N || sandbox.I18N || null;
process.stdout.write(JSON.stringify({
  current: api && typeof api.current === 'function' ? api.current() : null,
  lang: element.lang,
  available: api && typeof api.available === 'function' ? api.available() : null,
  stored: storage.dump()
}));
"""


@unittest.skipUnless(NODE, "node fehlt: Meta-Vorrang-Pruefung nicht ausfuehrbar")
class I18nMetaPriorityTest(unittest.TestCase):
    """i18n.js: Meta 'vibe-language' > localStorage > 'en', voll validiert."""

    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            [NODE, "-e", META_HARNESS, str(I18N_JS),
             "de", json.dumps({"vibe_i18n_lang": "en"})],
            capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise AssertionError("Node-vm (Meta) fehlgeschlagen: "
                                 + result.stdout + result.stderr)
        cls.de_meta = json.loads(result.stdout)

    def probe(self, meta, storage):
        result = subprocess.run(
            [NODE, "-e", META_HARNESS, str(I18N_JS), meta,
             json.dumps(storage)], capture_output=True, text=True, timeout=60)
        self.assertEqual(0, result.returncode,
                         "Node-vm fehlgeschlagen: " + result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_meta_language_wins_over_localstorage(self):
        """Gueltiges Meta 'de' schlaegt abweichenden localStorage-Wert."""
        self.assertEqual("de", self.de_meta.get("current"))
        self.assertEqual("de", self.de_meta.get("lang"))

    def test_meta_language_en_overrides_localstorage_de(self):
        data = self.probe("en", {"vibe_i18n_lang": "de"})
        self.assertEqual("en", data.get("current"))
        self.assertEqual("en", data.get("lang"))

    def test_invalid_meta_is_ignored_and_localstorage_used(self):
        """Ungueltiges Meta ('fr') faellt auf den gueltigen localStorage-Wert."""
        data = self.probe("fr", {"vibe_i18n_lang": "de"})
        self.assertEqual("de", data.get("current"))

    def test_invalid_meta_and_invalid_storage_default_to_english(self):
        data = self.probe("fr", {"vibe_i18n_lang": "xx"})
        self.assertEqual("en", data.get("current"))

    def test_no_meta_uses_localstorage(self):
        data = self.probe("", {"vibe_i18n_lang": "de"})
        self.assertEqual("de", data.get("current"))

    def test_no_meta_no_storage_defaults_to_english(self):
        """Ohne Meta und ohne Speicher ist 'en' der Standard."""
        data = self.probe("", {})
        self.assertEqual("en", data.get("current"))
        self.assertEqual("en", data.get("lang"))


def _load_ui_config():
    """Laedt bin/vibe_ui_config.py direkt (bin/ liegt nicht im sys.path)."""
    path = REPO / "bin" / "vibe_ui_config.py"
    loader = importlib.machinery.SourceFileLoader("vibe_ui_config_ap21", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


class UiConfigLanguageTest(unittest.TestCase):
    """vibe_ui_config: LANGUAGES, DEFAULT_LANGUAGE, validate_language, validate."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = _load_ui_config()

    def test_language_constants(self):
        self.assertEqual(("en", "de"), tuple(self.cfg.LANGUAGES))
        self.assertEqual("en", self.cfg.DEFAULT_LANGUAGE)
        self.assertIn(self.cfg.DEFAULT_LANGUAGE, self.cfg.LANGUAGES)

    def test_validate_language_accepts_supported_codes(self):
        self.assertEqual("en", self.cfg.validate_language("en"))
        self.assertEqual("de", self.cfg.validate_language("de"))

    def test_validate_language_rejects_everything_else(self):
        for value in ("fr", "", None, 42, ["de"], "EN", "de "):
            with self.subTest(value=value):
                with self.assertRaises(self.cfg.ConfigError):
                    self.cfg.validate_language(value)

    def test_validate_keeps_language_and_other_known_fields(self):
        cleaned = self.cfg.validate({"language": "de", "ui_port": 8080})
        self.assertEqual("de", cleaned["language"])
        self.assertEqual(8080, cleaned["ui_port"])

    def test_validate_strips_unknown_and_defaults_language_absent(self):
        cleaned = self.cfg.validate({"unknown": "x"})
        self.assertEqual({}, cleaned)
        self.assertNotIn("language", cleaned)

    def test_validate_rejects_invalid_language(self):
        with self.assertRaises(self.cfg.ConfigError):
            self.cfg.validate({"language": "fr"})


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class GlobalLanguageServerTest(unittest.TestCase):
    """Echter Dashboard-Prozess: GET/POST /api/language und HTML-Injektion."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = _load_ui_config()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.state = cls.root / "_state"
        cls.state.mkdir()
        cls.logs = cls.root / "_logs"
        cls.logs.mkdir()
        cls.home = cls.root / "home"
        (cls.home / ".config" / "opencode" / "agents").mkdir(parents=True)
        cls.other_project = cls.root / "other"
        cls.other_project.mkdir()
        (cls.other_project / "FEEDBACK.md").write_text("# FEEDBACK\nunveraendert\n",
                                                       encoding="utf-8")
        cls.port = _free_port()
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("VIBE") or key.startswith("SANDBOX") or key in (
                    "HOME", "XDG_CONFIG_HOME", "PYTHONDONTWRITEBYTECODE", "TMUX",
                    "TMUX_PANE"):
                env.pop(key, None)
        env.update({
            "VIBE": str(cls.root), "VIBE_NO_CONTAINER": "1",
            "VIBE_UI_PORT": str(cls.port), "VIBE_OPENCODE_PORT": str(_free_port()),
            "VIBE_STATE": str(cls.state), "VIBE_INSTALL": str(cls.root),
            "VIBE_RUNTIME": str(cls.logs),
            "VIBE_AGENTS_DIR": str(cls.home / ".config" / "opencode" / "agents"),
            "VIBE_CONFIG_FILE": str(cls.home / ".config" / "vibe" / "config.json"),
            "HOME": str(cls.home), "PYTHONDONTWRITEBYTECODE": "1",
        })
        cls.log_path = cls.root / "server.log"
        cls.log_file = open(cls.log_path, "w", encoding="utf-8")
        cls.proc = subprocess.Popen(
            [sys.executable, str(REPO / "bin" / "vibe-web.py")], env=env,
            stdout=cls.log_file, stderr=subprocess.STDOUT, text=True)
        token_file = cls.logs / "web.token"
        deadline = time.time() + 30
        while time.time() < deadline:
            if cls.proc.poll() is not None:
                raise AssertionError("vibe-web vorzeitig beendet: "
                                     + cls.log_path.read_text(encoding="utf-8",
                                                              errors="replace"))
            if token_file.exists():
                try:
                    with socket.create_connection(("127.0.0.1", cls.port), timeout=0.5):
                        break
                except OSError:
                    pass
            time.sleep(0.05)
        else:
            raise AssertionError("vibe-web nicht erreichbar")
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
        cls.log_file.close()
        cls.tmp.cleanup()

    def setUp(self):
        # Jeder Test beginnt mit dem englischen Standard (Datei + In-Memory).
        status, body, _ = self.request("POST", "/api/language",
                                       {"language": "en"}, self.token)
        assert status == 200, body

    def request(self, method, path, body=None, token=None):
        if body is not None and not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if token is not None:
            headers["X-Token"] = token
        if body is not None:
            headers["Content-Type"] = "application/json"
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8", "replace"), dict(resp.getheaders())
        finally:
            conn.close()

    def ui_json(self):
        path = self.state / "ui.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def test_get_language_payload(self):
        status, body, _ = self.request("GET", "/api/language", token=self.token)
        self.assertEqual(200, status)
        data = json.loads(body)
        self.assertEqual({"ok": True, "language": "en",
                          "languages": ["en", "de"], "default": "en"}, data)

    def test_get_language_requires_auth(self):
        status, body, _ = self.request("GET", "/api/language")
        self.assertEqual(403, status)
        self.assertEqual("unauthorized", json.loads(body)["error"]["code"])

    def test_get_language_reflects_saved_value(self):
        self.request("POST", "/api/language", {"language": "de"}, self.token)
        status, body, _ = self.request("GET", "/api/language", token=self.token)
        self.assertEqual("de", json.loads(body)["language"])

    def test_post_language_ok_persists_and_preserves_other_fields(self):
        # Ein weiteres, bekanntes ui.json-Feld setzen und danach sprachwechseln.
        status, _, _ = self.request("POST", "/api/security",
                                    {"action": "save", "allowlist": ["127.0.0.1"]},
                                    self.token)
        self.assertEqual(200, status)
        status, body, _ = self.request("POST", "/api/language",
                                       {"language": "de"}, self.token)
        self.assertEqual(200, status)
        self.assertEqual({"ok": True, "language": "de",
                          "message": "Sprache gespeichert"}, json.loads(body))
        data = self.ui_json()
        self.assertEqual("de", data["language"])
        self.assertEqual(["127.0.0.1"], data["allowlist"])
        # Andere Projekte sind nicht betroffen.
        self.assertEqual("# FEEDBACK\nunveraendert\n",
                         (self.other_project / "FEEDBACK.md").read_text(encoding="utf-8"))

    def test_post_language_invalid_returns_400_without_change(self):
        before = (self.state / "ui.json").read_bytes()
        for bad in ({"language": "fr"}, {}, {"language": None}, {"language": 7}):
            with self.subTest(bad=bad):
                status, body, _ = self.request("POST", "/api/language", bad, self.token)
                self.assertEqual(400, status)
                self.assertEqual("invalid_language", json.loads(body)["error"]["code"])
                self.assertEqual(before, (self.state / "ui.json").read_bytes())

    def test_post_language_requires_auth(self):
        status, body, _ = self.request("POST", "/api/language", {"language": "de"})
        self.assertEqual(403, status)
        self.assertEqual("unauthorized", json.loads(body)["error"]["code"])

    def test_page_injects_default_language(self):
        status, html, _ = self.request("GET", "/")
        self.assertEqual(200, status)
        # AP22: die neue Shell trägt zusätzlich Theme/Animations-Attribute am
        # <html>-Element; die Sprachplatzhalter bleiben unverändert wirksam.
        self.assertIn('<html lang="en" data-theme="light" data-animations="on">', html)
        self.assertIn('<meta name="vibe-language" content="en">', html)

    def test_page_injects_saved_language(self):
        self.request("POST", "/api/language", {"language": "de"}, self.token)
        status, html, _ = self.request("GET", "/")
        self.assertEqual(200, status)
        self.assertIn('<html lang="de" data-theme="light" data-animations="on">', html)
        self.assertIn('<meta name="vibe-language" content="de">', html)

    def test_ui_json_roundtrip_language_survives_save(self):
        target = self.cfg.save(str(self.state), {**self.ui_json(), "language": "de"})
        self.assertEqual("de", self.cfg.load(str(self.state))["language"])
        self.assertEqual(str(self.state / "ui.json"), target)
        # Ungueltig wird abgelehnt und laesst die Datei unveraendert.
        with self.assertRaises(self.cfg.ConfigError):
            self.cfg.save(str(self.state), {**self.ui_json(), "language": "xx"})
        self.assertEqual("de", self.cfg.load(str(self.state))["language"])


if __name__ == "__main__":
    unittest.main()
