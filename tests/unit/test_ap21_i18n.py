"""Unit-Abnahme AP21: i18n-Infrastruktur ohne Browser.

Ticket AP21 verlangt eine Sprachinfrastruktur (i18n), die weitere Sprachen
erlaubt, sowie Englisch als Standard. Diese Suite prüft die reine
i18n-Logik direkt gegen ``bin/web/i18n.js`` – ohne Dashboard und ohne
Netzwerk. Dafür wird die Datei in einer schlanken Node-``vm``-Umgebung mit
Stubs für ``window``, ``document`` und ``localStorage`` ausgeführt; das
entspricht dem Browser-Global, ohne einen Browser zu starten.

Verbindlicher Vertrag (aus dem Ticket abgeleitet):

* ``bin/web/i18n.js`` existiert und lädt **vor** ``app.js``
  (``index.html``).
* Global ``window.VIBE_I18N`` mit Alias ``I18N`` und den Funktionen
  ``available()``, ``current()``, ``set(lang)``, ``t(key, vars?)``.
* ``available()`` enthält ``en`` und ``de`` (weitere Sprachen ergänzbar),
  Englisch zuerst.
* Frisches Profil ohne gespeicherte Wahl: ``current() === 'en'`` – auch wenn
  der Browser selbst auf Deutsch steht („standard englisch“).
* ``set('de')`` aktualisiert ``<html lang>`` und speichert die Wahl in
  ``localStorage``; ein neuer Seitenaufbau mit demselben Speicher liest
  ``de``.
* Unbekannter Key liefert den Key selbst; ``{{var}}`` wird interpoliert.

Testfälle (8):

1. ``test_module_exists_and_exposes_public_api``
   Vorbedingung: ``bin/web/i18n.js`` vorhanden.
   Aktion: Modul in der Node-vm laden; Global inspizieren.
   Erwartung: ``VIBE_I18N`` und Alias ``I18N`` vorhanden; alle vier
   Funktionen vorhanden.
   Fehlerfall: Datei fehlt, Global fehlt oder API unvollständig.

2. ``test_index_html_loads_i18n_before_app``
   Vorbedingung: ``bin/web/index.html``.
   Aktion: Reihenfolge der ``<script src=…>``-Tags prüfen.
   Erwartung: ``/static/i18n.js`` steht vor ``/static/app.js``.
   Fehlerfall: Skript fehlt oder wird nach ``app.js`` geladen.

3. ``test_available_languages_include_english_and_german``
   Vorbedingung: Modul geladen.
   Aktion: ``available()`` auslesen.
   Erwartung: Liste mit ``en`` und ``de``, ``en`` zuerst.
   Fehlerfall: Nur eine Sprache oder keine Liste.

4. ``test_fresh_profile_defaults_to_english``
   Vorbedingung: leerer ``localStorage``, ``navigator.language = 'de-DE'``.
   Aktion: ``current()`` auslesen.
   Erwartung: ``'en'``.
   Fehlerfall: Die Oberfläche übernimmt die Browsersprache statt Englisch.

5. ``test_set_updates_current_and_html_lang``
   Vorbedingung: Modul geladen, Englisch aktiv.
   Aktion: ``set('de')``, dann ``set('en')``.
   Erwartung: ``current()`` und ``document.documentElement.lang`` folgen
   jeweils sofort; kein Fehler.
   Fehlerfall: ``set`` ohne Wirkung auf ``current()``/``lang``.

6. ``test_set_persists_choice_for_next_page_load``
   Vorbedingung: ``set('de')`` wurde ausgeführt.
   Aktion: Modul mit demselben ``localStorage``-Inhalt neu laden
   (Seitenaufbau simulieren).
   Erwartung: ``current() === 'de'``; der Speicher enthält den Wert ``de``.
   Fehlerfall: Wahl geht beim Neuladen verloren.

7. ``test_unknown_key_returns_key``
   Vorbedingung: Modul geladen.
   Aktion: ``t('ap21.unknown.key.4711')``.
   Erwartung: exakt der Key.
   Fehlerfall: ``undefined``/leerer String/Exception.

8. ``test_translation_interpolates_variables``
   Vorbedingung: Modul geladen.
   Aktion: ``t('ap21.test.{{name}}', {name: 'Vibe'})``.
   Erwartung: Ergebnis enthält ``Vibe`` und kein ``{{``.
   Fehlerfall: Platzhalter bleibt stehen.

Die Node-vm ist reine Testinfrastruktur; die Produktivdatei wird nur
gelesen. Fehlt ``node``, meldet die Suite den Test als übersprungen
(Umgebungsvoraussetzung, kein Testverlust).
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
I18N_JS = REPO / "bin" / "web" / "i18n.js"
INDEX_HTML = REPO / "bin" / "web" / "index.html"
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

    def test_index_html_loads_i18n_before_app(self):
        """Fall 2: index.html lädt /static/i18n.js vor /static/app.js."""
        self.assertTrue(
            INDEX_HTML.is_file(), "bin/web/index.html fehlt")
        html = INDEX_HTML.read_text(encoding="utf-8")
        i18n_pos = html.find('/static/i18n.js')
        app_pos = html.find('/static/app.js')
        self.assertNotEqual(
            -1, i18n_pos,
            "index.html lädt /static/i18n.js nicht")
        self.assertNotEqual(
            -1, app_pos,
            "index.html lädt /static/app.js nicht")
        self.assertLess(
            i18n_pos, app_pos,
            "index.html lädt i18n.js erst nach app.js: "
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


if __name__ == "__main__":
    unittest.main()
