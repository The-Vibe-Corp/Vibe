/* AP22 — neue Shell: Boot, Auth, Router, Präferenzen, Toasts, Glocke.
 *
 * Bewusst als gewöhnliches Skript ohne Build-Schritt: die Helfer el/tr/bt/api
 * entsprechen den Bestandsmustern aus app.js. Die Ansichtsdateien registrieren
 * ihre Renderer in NV.views; dieser Kern dispatched nur und schützt den Render
 * mit einem Token gegen Rennbedingungen. Der Token aus #t= bleibt nur im
 * Speicher und wird beim Boot gegen einen Session-Cookie getauscht.
 */
'use strict';

var OC_URL = (document.querySelector('meta[name="vibe-opencode-url"]') || {}).content || '';

/* Der Token kommt ausschließlich aus dem Hash und wird sofort aus der URL
   entfernt (wie im Bestand). Er wird nie in localStorage/sessionStorage
   geschrieben. */
var T = (function () {
  var m = location.hash.match(/t=([^&]+)/);
  if (m) history.replaceState(null, '', location.pathname);
  try { return m ? decodeURIComponent(m[1]) : ''; } catch (e) { return m ? m[1] : ''; }
})();

var NV = window.NV = {
  views: {},
  stale: function (token) { return token !== RENDER_TOKEN; },
  token: function () { return T; },
  ocUrl: OC_URL
};

/* ---------- Akzent (F33/4): gültige IDs für data-accent/localStorage. ---------- */
var ACCENT_IDS = ['blue', 'teal', 'cyan', 'green', 'lime', 'yellow',
  'amber', 'orange', 'red', 'pink', 'violet', 'indigo'];
NV.accent = function () {
  var stored = localStorage.getItem('nv-accent');
  return ACCENT_IDS.indexOf(stored) !== -1 ? stored : 'blue';
};
NV.setAccent = function (id) {
  localStorage.setItem('nv-accent', id);
  document.documentElement.setAttribute('data-accent', id);
};
function applyAccent() { NV.setAccent(NV.accent()); }

function errText(j, status) {
  var e = j && j.error;
  return (e && (e.message || e)) || (j && j.message) || ('HTTP ' + status);
}

/* GET wirft auf HTTP-Fehler (der Aufrufer zeigt die Anmeldung), POST liefert
   auch bei 400 das JSON zurück, damit Fachfehler (ok:false) sichtbar bleiben. */
async function api(path, body) {
  var options = body
    ? {method: 'POST', headers: {'X-Token': T, 'Content-Type': 'application/json'}, body: JSON.stringify(body)}
    : {headers: {'X-Token': T}};
  var response = await fetch(path, options);
  var data = await response.json().catch(function () { return {}; });
  if (!response.ok && !body) {
    var error = new Error(errText(data, response.status));
    error.status = response.status;
    throw error;
  }
  return data;
}

/* DOM-only Knotenbau — nie innerHTML mit Server-/Protokoll-/Nutzerinhalt.
   Boxed Strings tragen den Ursprungsschlüssel, damit ein Sprachwechsel nur
   wirklich aus dem Wörterbuch stammende Knoten/Attribute neu übersetzt. */
function el(tag, attrs) {
  var node = document.createElement(tag);
  var all = Array.prototype.slice.call(arguments, 2);
  Object.keys(attrs || {}).forEach(function (key) {
    var value = attrs[key];
    if (key === 'on') {
      Object.keys(value).forEach(function (event) {
        node.addEventListener(event, value[event]);
      });
    } else if (key === 'class') {
      node.className = value;
    } else if (key === 'value') {
      node.value = value;
    } else if (key === 'checked') {
      node.checked = !!value;
    } else {
      node.setAttribute(key, value);
      if (value && value.__i18n) {
        node.__i18nAttrs = node.__i18nAttrs || {};
        node.__i18nAttrs[key] = value.__i18n;
      }
    }
  });
  all.flat().forEach(function (child) {
    if (child === null || child === undefined || child === false) return;
    var text = child.nodeType ? child : document.createTextNode(String(child));
    if (child && child.__i18n) text.__i18n = child.__i18n;
    node.append(text);
  });
  return node;
}

function i18n() { return window.VIBE_I18N || window.I18N; }

function tr(key, vars) {
  var engine = i18n();
  var value = engine && typeof engine.t === 'function' ? engine.t(key, vars) : String(key);
  var boxed = new String(value);
  boxed.__i18n = {key: key, vars: vars};
  return boxed;
}

function setTx(node, value) {
  node.textContent = value;
  if (value && value.__i18n) {
    node.__i18n = value.__i18n;
    node.__i18nOwn = true;
  }
}

function setAttrTx(node, name, key) {
  node.setAttribute(name, String(tr(key)));
  node.__i18nAttrs = node.__i18nAttrs || {};
  node.__i18nAttrs[name] = {key: key, vars: undefined};
}

function setAttrTxVars(node, name, key, vars) {
  node.setAttribute(name, String(tr(key, vars)));
  node.__i18nAttrs = node.__i18nAttrs || {};
  node.__i18nAttrs[name] = {key: key, vars: vars};
}

/* F33/3d: Das Animations-Label trägt aria-label/title "Animationen: an/aus"
   (Zustand im Label); die Glyph/der Glyph-Text bleibt unberührt. */
function setAnimLabel(animToggle) {
  var label = animToggle.closest('label');
  var key = animToggle.checked ? 'Animationen: an' : 'Animationen: aus';
  if (label) setAttrTx(label, 'aria-label', key);
  setAttrTx(animToggle, 'aria-label', key);
  setAttrTx(animToggle, 'title', key);
}

/* Shell-Chrome: das Markup ist sprachneutral (leere Attribute), die deutschen
   Quellschlüssel hier sind die einzige Textquelle. setTx/setAttrTx merken sich
   den Key, damit retranslateDOM() ihn beim Sprachwechsel neu übersetzt. */
function setChromeLabel(node, key, glyph) {
  if (!node) return;
  if (glyph) setTx(node, glyph);
  setAttrTx(node, 'aria-label', key);
  setAttrTx(node, 'title', key);
}

/* Backend-Antworten bleiben im Deutschen (API-Vertrag); die Zuordnung liegt
   clientseitig. Im deutschen Modus wird der Originaltext unverändert gezeigt. */
var NEWS_PHRASES = [
  ['Zugriffssicherheit gespeichert', 'Access security saved'],
  ['Kennwort gesetzt', 'Password set'],
  ['Kennwort entfernt', 'Password removed'],
  ['Ordner existiert nicht: ', 'Folder does not exist: '],
  ['Verzeichnis hinzugefügt', 'Directory added'],
  ['Verzeichnis entfernt', 'Directory removed'],
  ['Unbekannte Aktion', 'Unknown action'],
  ['gespeichert', 'saved'],
  ['gesetzt', 'set'],
  ['entfernt', 'removed'],
  ['fehlgeschlagen', 'failed'],
  ['Android', 'Android']
];

function bt(value) {
  var text = String(value == null ? '' : value);
  if (!text) return text;
  var engine = i18n();
  if (!engine || engine.current() !== 'en') return text;
  if (engine.DICTS && engine.DICTS.en &&
      Object.prototype.hasOwnProperty.call(engine.DICTS.en, text)) return tr(text);
  var out = text;
  NEWS_PHRASES.forEach(function (pair) { out = out.split(pair[0]).join(pair[1]); });
  return out;
}

/* F34: Genau eine Sammlung von Meldungen. Jeder Toast wird zusätzlich als
   Glocken-Eintrag gespeichert (max. 100, neueste zuerst). */
var NOTIFICATIONS_KEY = 'nv-notifications';
var MAX_NOTIFICATIONS = 100;
var toastBox = document.getElementById('nv-toasts');

function readJSON(key, fallback) {
  try {
    var raw = localStorage.getItem(key);
    if (raw == null) return fallback;
    var data = JSON.parse(raw);
    return data == null ? fallback : data;
  } catch (error) { return fallback; }
}

/* Ausblendungen und gesehene Fragen sind sitzungsbezogen (F34-Vertrag). */
function readSessionJSON(key, fallback) {
  try {
    var raw = sessionStorage.getItem(key);
    if (raw == null) return fallback;
    var data = JSON.parse(raw);
    return data == null ? fallback : data;
  } catch (error) { return fallback; }
}
function saveSessionJSON(key, value) {
  try { sessionStorage.setItem(key, JSON.stringify(value)); }
  catch (error) { /* Sitzungsspeicher nicht verfügbar */ }
}

function readNotifications() {
  var data = readJSON(NOTIFICATIONS_KEY, []);
  if (!Array.isArray(data)) return [];
  return data.filter(function (entry) {
    return entry && typeof entry === 'object' && entry.text != null;
  }).map(function (entry) {
    return {
      id: String(entry.id || ''),
      text: String(entry.text),
      kind: String(entry.kind || 'info'),
      href: entry.href ? String(entry.href) : '',
      ts: Number(entry.ts) || 0,
      read: !!entry.read
    };
  });
}

function saveNotifications(entries) {
  try {
    localStorage.setItem(NOTIFICATIONS_KEY,
      JSON.stringify(entries.slice(0, MAX_NOTIFICATIONS)));
  } catch (error) { /* Speicher nicht verfügbar: Peek bleibt trotzdem sichtbar */ }
}

function persistNotification(text, opts) {
  var settings = opts || {};
  var entry = {
    id: 'nv-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8),
    text: String(text == null ? '' : text),
    kind: String(settings.kind || 'info'),
    href: settings.href ? String(settings.href) : '',
    ts: Date.now(),
    read: false
  };
  var all = readNotifications();
  all.unshift(entry);
  saveNotifications(all);
  if (typeof refreshBell === 'function') refreshBell();
  return entry;
}

function toast(message, opts) {
  var text = String(message == null ? '' : message);
  var settings = opts || {};
  if (settings.store !== false) persistNotification(text, settings);
  if (!toastBox) return;
  var card = el('div', {class: 'nv-toast', 'data-nv-toast-auto': ''}, el('span', {}, text),
    el('button', {class: 'nv-toast-close', type: 'button',
      'aria-label': tr('Meldung schließen'), on: {click: function () { card.remove(); }}}, '×'));
  startToastTimer(card);
  toastBox.append(card);
}

/* Öffentliche API für Ansichten: Meldung + Peek + Glocken-Eintrag. */
NV.notify = function (text, opts) { return toast(text, opts); };
NV.notifications = function () { return readNotifications(); };
NV.dismissNotification = function (id) {
  saveNotifications(readNotifications().filter(function (entry) {
    return entry.id !== String(id);
  }));
  renderBell(lastPulse);
};
NV.clearNotifications = function () {
  saveNotifications(readNotifications().map(function (entry) {
    entry.read = true;
    return entry;
  }));
  var dismissed = readDismissedLive();
  liveRows(lastPulse).forEach(function (row) {
    if (dismissed.indexOf(row.key) === -1) dismissed.push(row.key);
  });
  saveDismissedLive(dismissed);
  renderBell(lastPulse);
};

/* F33/3c: Toasts sind kurzlebig — Karten mit data-nv-toast-auto werden
   nach ~6 s selbst entfernt; Hover/Fokus in der Karte pausiert den Timer,
   das manuelle Schließen bleibt immer möglich (der Timer prüft isConnected). */
var TOAST_AUTO_MS = 6000;
function startToastTimer(card) {
  var remaining = TOAST_AUTO_MS;
  var started = 0;
  var timer = null;
  var paused = false;
  function tick() {
    started = Date.now();
    timer = setTimeout(function () {
      timer = null;
      if (card.isConnected) card.remove();
    }, remaining);
  }
  function pause() {
    if (!timer || paused) return;
    clearTimeout(timer);
    timer = null;
    remaining -= Date.now() - started;
    if (remaining < 0) remaining = 0;
    paused = true;
  }
  function resume() {
    if (!paused) return;
    paused = false;
    tick();
  }
  card.addEventListener('mouseenter', pause);
  card.addEventListener('focusin', pause);
  card.addEventListener('mouseleave', resume);
  card.addEventListener('focusout', function (event) {
    if (card.contains(event.relatedTarget)) return;
    resume();
  });
  tick();
}

/* ---------- Präferenzen (localStorage, rein clientseitig) ---------- */

function media(query) {
  return window.matchMedia ? window.matchMedia(query) : null;
}

function resolvedTheme(preference) {
  if (preference === 'dark' || preference === 'light') return preference;
  var query = media('(prefers-color-scheme: dark)');
  return query && query.matches ? 'dark' : 'light';
}

/* Der Select in den Einstellungen zeigt die gespeicherte Präferenz (light,
   dark, auto), data-theme dagegen immer den aufgelösten Wert. Beide Controls
   bleiben so in beide Richtungen synchron. */
NV.themePreference = function () {
  return localStorage.getItem('nv-theme') || 'light';
};

function applyTheme() {
  document.documentElement.setAttribute('data-theme', resolvedTheme(NV.themePreference()));
}

NV.setTheme = function (preference) {
  localStorage.setItem('nv-theme', preference);
  applyTheme();
  var select = document.querySelector('[data-nv-theme-select]');
  if (select) select.value = preference;
};

NV.toggleTheme = function () {
  var current = document.documentElement.getAttribute('data-theme');
  NV.setTheme(current === 'dark' ? 'light' : 'dark');
};

function applyAnimations() {
  var stored = localStorage.getItem('nv-animations');
  if (stored === 'on' || stored === 'off') {
    document.documentElement.setAttribute('data-animations', stored);
    return;
  }
  // Ohne gespeicherte Wahl gilt der Systemwunsch — ohne ihn zu speichern.
  var query = media('(prefers-reduced-motion: reduce)');
  document.documentElement.setAttribute('data-animations', query && query.matches ? 'off' : 'on');
}

NV.setAnimations = function (enabled) {
  localStorage.setItem('nv-animations', enabled ? 'on' : 'off');
  applyAnimations();
};

function featureMap() {
  try { return JSON.parse(localStorage.getItem('nv-features') || '{}') || {}; }
  catch (e) { return {}; }
}

NV.feature = function (id) { return !!featureMap()[id]; };

NV.setFeature = function (id, enabled, options) {
  var all = featureMap();
  if (enabled) all[id] = true; else delete all[id];
  localStorage.setItem('nv-features', JSON.stringify(all));
  var detail = {id: id, on: !!enabled};
  // Die Einstellungen zeichnen ihre Sektionen selbst; ein Voll-Neurender
  // würde dort die Scroll-Position verlieren (GH-57).
  if (options && options.source === 'settings') detail.source = 'settings';
  window.dispatchEvent(new CustomEvent('nv:featureschange', {detail: detail}));
};

/* ---------- Router: Hash → Ansicht, mit RENDER_TOKEN gegen Rennen ---------- */

var RENDER_TOKEN = 0;
var authorized = false;

function route() {
  var hash = (location.hash || '').replace(/^#\/?/, '');
  var parts = hash.split('/').filter(function (part) { return !!part; });
  var head = parts[0] || 'home';
  try {
    if (head === 'project' && parts[1]) {
      return {view: 'project', name: decodeURIComponent(parts[1]), tab: parts[2] || 'overview'};
    }
    if (head === 'agents') {
      return {view: 'agents', name: parts[1] ? decodeURIComponent(parts[1]) : null};
    }
    if (head === 'activity') return {view: 'activity'};
    if (head === 'evaluations') return {view: 'evaluations'};
    if (head === 'settings') return {view: 'settings'};
  } catch (e) { /* defekter Hash fällt auf home zurück */ }
  return {view: 'home'};
}

NV.navigate = function (hash) { location.hash = hash; };

function render() {
  return Promise.resolve().then(function () {
    // Die Glocke darf nicht über einen Routenwechsel hinweg offen bleiben.
    closeBellPanel();
    if (!authorized) { showLogin(); return; }
    var context = route();
    RENDER_TOKEN++;
    var token = RENDER_TOKEN;
    var main = document.getElementById('nv-main');
    main.setAttribute('data-nv-view', context.view);
    document.querySelectorAll('[data-nv-nav]').forEach(function (button) {
      if (button.getAttribute('data-nv-nav') === context.view) {
        button.setAttribute('aria-current', 'page');
      } else {
        button.removeAttribute('aria-current');
      }
    });
    var renderer = NV.views[context.view] || NV.views.home;
    return Promise.resolve(renderer(context, token)).then(function () {
      if (token === RENDER_TOKEN) enhanceView(main);
    }).catch(function (error) {
      if (token !== RENDER_TOKEN) return;
      toast(tr('Ansicht konnte nicht geladen werden: ') + String(error && error.message || error));
    });
  });
}
NV.render = render;

/* ---------- Kopfzeile, Anmeldung und Benachrichtigungen ---------- */

var NAV_KEYS = {home: 'Start', agents: 'Agenten', activity: 'Aktivität',
  evaluations: 'Auswertungen', settings: 'Einstellungen'};

/* F34: Die fünf Navigationspunkte bleiben dauerhaft in der Kopfzeile. Die
   leere aside.nv-side wird nicht mehr als Nav-Container verwendet. */

/* Neutraler Leerzustand für die neue Route, bis WP3 die Ansicht liefert. */
NV.views.evaluations = function (context, token) {
  if (NV.stale(token)) return;
  document.getElementById('nv-main').replaceChildren(
    el('section', {class: 'nv-card'},
      el('h2', {}, tr('Auswertungen')),
      el('p', {class: 'nv-muted'},
        tr('Auswertungen sind hier noch nicht verfügbar.'))));
};

function initChrome() {
  var skip = document.querySelector('.nv-skip');
  if (skip) setTx(skip, tr('Zum Inhalt springen'));
  var toggle = document.querySelector('[data-nv-nav-toggle]');
  if (toggle) {
    setChromeLabel(toggle, 'Menü', '☰');
    toggle.addEventListener('click', function () {
      var open = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', open ? 'false' : 'true');
    });
    /* Der Dimmer ist nur mobil sichtbar; ein Tippen darauf schließt das Menü
       über genau dasselbe Attribut, das auch seine Sichtbarkeit steuert. */
    var scrim = document.querySelector('[data-nv-nav-scrim]');
    if (scrim) scrim.addEventListener('click', function () {
      toggle.setAttribute('aria-expanded', 'false');
    });
  }
  var nav = document.querySelector('[data-nv-navs]');
  if (nav) setAttrTx(nav, 'aria-label', 'Navigation');
  document.querySelectorAll('[data-nv-nav]').forEach(function (button) {
    var view = button.getAttribute('data-nv-nav');
    setTx(button, tr(NAV_KEYS[view] || 'Start'));
    button.addEventListener('click', function () { NV.navigate('#/' + view); });
  });
  var animToggle = document.querySelector('[data-nv-anim-toggle]');
  if (animToggle) {
    animToggle.checked = document.documentElement.getAttribute('data-animations') !== 'off';
    setAnimLabel(animToggle);
    animToggle.addEventListener('change', function () {
      NV.setAnimations(animToggle.checked);
      setAnimLabel(animToggle);
    });
  }
  var themeToggle = document.querySelector('[data-nv-theme-toggle]');
  if (themeToggle) {
    setChromeLabel(themeToggle, 'Darstellung wechseln', '◐');
    themeToggle.addEventListener('click', function () { NV.toggleTheme(); });
  }
  var questionsButton = document.querySelector('[data-nv-questions-button]');
  if (questionsButton) {
    var label = questionsButton.querySelector('.nv-questions-label');
    if (label) setTx(label, tr('Fragen'));
    setChromeLabel(questionsButton, 'Fragen');
    questionsButton.addEventListener('click', function () { NV.questions.openInbox(); });
  }
  var banner = document.querySelector('[data-nv-question-banner]');
  if (banner) {
    // Der Inhalt wird bei jedem Poll neu gezeichnet → Delegation.
    banner.addEventListener('click', function (event) {
      if (event.target.closest('[data-nv-question-banner-open]')) {
        NV.questions.openInbox();
      }
    });
  }
  var contextClose = document.querySelector('[data-nv-context-close]');
  if (contextClose) {
    setChromeLabel(contextClose, 'Kontext schließen', '×');
    contextClose.addEventListener('click', function () { NV.context.close(); });
  }
  var contextScrim = document.querySelector('[data-nv-context-scrim]');
  if (contextScrim) contextScrim.addEventListener('click', function () { NV.context.close(); });
  var bell = document.querySelector('[data-nv-bell]');
  if (bell) {
    setChromeLabel(bell, 'Benachrichtigungen');
    bell.addEventListener('click', function (event) {
      event.stopPropagation();
      var panel = document.querySelector('[data-nv-bell-panel]');
      if (!panel) return;
      var shouldOpen = panel.hidden;
      closeBellPanel();
      if (shouldOpen) {
        panel.hidden = false;
        bell.setAttribute('aria-expanded', 'true');
        bell.classList.add('is-open');
      }
    });
    var panel = document.querySelector('[data-nv-bell-panel]');
    if (panel) {
      // Der Schließen-Knopf wird bei jedem Refresh neu gebaut → Delegation.
      panel.addEventListener('click', function (event) {
        if (event.target.closest('[data-nv-bell-close]')) {
          closeBellPanel();
          bell.focus();
        } else if (event.target.closest('[data-nv-bell-clear]')) {
          event.stopPropagation();
          NV.clearNotifications();
        }
      });
    }
  }
  // Klick außerhalb und Escape schließen die Glocke zuverlässig.
  document.addEventListener('click', function (event) {
    var panel = document.querySelector('[data-nv-bell-panel]');
    if (!panel || panel.hidden) return;
    var wrap = document.querySelector('.nv-bell-wrap');
    if (wrap && wrap.contains(event.target)) return;
    closeBellPanel();
  });
  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return;
    closeBellPanel();
    if (NV.context.isOpen()) NV.context.close();
  });
  window.addEventListener('hashchange', function () { render(); });
  window.addEventListener('vibe:langchange', function () {
    retranslateDOM();
    setTimeout(function () { render(); }, 20);
  });
  window.addEventListener('nv:featureschange', function (event) {
    if (event && event.detail && event.detail.source === 'settings') return;
    var scroll = window.scrollY;
    var pending = render();
    if (pending && typeof pending.then === 'function') {
      pending.then(function () { window.scrollTo(0, scroll); });
    }
  });
  var scheme = media('(prefers-color-scheme: dark)');
  if (scheme && scheme.addEventListener) {
    scheme.addEventListener('change', function () {
      if ((localStorage.getItem('nv-theme') || 'light') === 'auto') applyTheme();
    });
  }
  window.addEventListener('unhandledrejection', function (event) {
    if (event && event.preventDefault) event.preventDefault();
    toast(tr('Aktion fehlgeschlagen: ') + String(event && event.reason && event.reason.message || event && event.reason || ''));
  });
  // Die Schublade sofort mit Kopf, Erklärung und Aktion füllen; die Live-
  // Quellen kommen anschließend asynchron über refreshBell().
  renderBell();
}

function showLogin() {
  authorized = false;
  var input = el('input', {type: 'password', 'data-nv-login-input': '',
    placeholder: tr('Kennwort oder Token'), 'aria-label': tr('Kennwort oder Token')});
  var submit = function () { doLogin(input); };
  var button = el('button', {class: 'nv-btn nv-primary', type: 'button',
    'data-nv-login-submit': '', on: {click: submit}}, tr('Anmelden'));
  input.addEventListener('keydown', function (event) {
    if (event.key === 'Enter') { event.preventDefault(); submit(); }
  });
  var card = el('div', {class: 'nv-card nv-login', 'data-nv-login': ''},
    el('h2', {}, tr('Anmeldung')),
    el('p', {class: 'nv-muted'}, tr('Diese Oberfläche ist geschützt. Bitte Kennwort oder Token eingeben.')),
    el('label', {}, tr('Kennwort oder Token')), input,
    el('div', {class: 'nv-row'}, button));
  document.getElementById('nv-main').replaceChildren(card);
  input.focus();
}

async function doLogin(input) {
  var value = String(input.value || '').trim();
  if (!value) { input.focus(); return; }
  try {
    // Ein Eingabefeld für beides: der Server prüft zuerst das Token und fällt
    // sonst auf das Kennwort zurück. Keiner der Werte erscheint in einer Meldung.
    var result = await api('/api/login', {token: value, password: value});
    if (result.ok) {
      authorized = true;
      await render();
      refreshBell();
    } else {
      toast(bt(result.message) || tr('Anmeldung fehlgeschlagen.'));
    }
  } catch (error) {
    toast(tr('Anmeldung fehlgeschlagen: ') + String(error && error.message || error));
  }
}
NV.logout = function () {
  api('/api/logout', {}).catch(function () {}).then(function () {
    authorized = false;
    showLogin();
  });
};

/* Die Glocke hat genau einen offenen Zustand: Panel sichtbar, aria-expanded
   und Marker am Knopf. Alles andere (Route, Außenklick, Escape, Schließen)
   ruft diesen einen Reset — damit bleibt kein Zustand zurück. */
function closeBellPanel() {
  var panel = document.querySelector('[data-nv-bell-panel]');
  var bell = document.querySelector('[data-nv-bell]');
  if (panel) panel.hidden = true;
  if (bell) {
    bell.removeAttribute('aria-expanded');
    bell.classList.remove('is-open');
  }
}
NV.closeBellPanel = closeBellPanel;

/* Gemeinsame Momentaufnahme für Glocke und Aktivitäts-Kacheln. Quellen sind
   offene Fragen, Läufe (/api/projects) und blockierte Pakete (/api/project je
   Projekt mit offenen Einträgen). Der Detailaufruf ist bewusst auf Projekte
   mit offenen Einträgen beschränkt; die Ansicht bleibt dadurch auch bei vielen
   Projekten klein. Ein fehlgeschlagener Detailaufruf darf die übrigen Quellen
   nicht verdecken. */
NV.pulse = async function pulse() {
  var questions = await api('/api/questions');
  var projects = await api('/api/projects');
  var rows = projects || [];
  var running = rows.filter(function (row) { return row && !!row.running; });
  var failed = rows.filter(function (row) {
    return row && row.run && String(row.run.state || '') === 'failed';
  });
  var withOpen = rows.filter(function (row) { return row && (row.open || 0) > 0; });
  var details = await Promise.all(withOpen.map(function (row) {
    return api('/api/project?name=' + encodeURIComponent(String(row.name)))
      .then(function (data) { return {name: String(row.name), tickets: (data && data.tickets) || []}; })
      .catch(function () { return {name: String(row.name), tickets: []}; });
  }));
  var blocked = [];
  details.forEach(function (detail) {
    detail.tickets.forEach(function (ticket) {
      if (String(ticket && ticket.state || '') === 'BLOCKIERT') {
        blocked.push({project: detail.name, id: String(ticket.id || ''),
          title: String(ticket.title || ticket.id || '')});
      }
    });
  });
  return {questions: (questions && questions.questions) || [], projects: rows,
    running: running, failed: failed, blocked: blocked};
};

/* ---------- Glocke: gespeicherte Einträge + ausblendbare Live-Einträge ---------- */

var LIVE_KEY = 'nv-dismissed-live';
var lastPulse = {questions: [], blocked: [], failed: [], running: []};

function readDismissedLive() {
  var data = readSessionJSON(LIVE_KEY, []);
  return Array.isArray(data) ? data.map(String) : [];
}
function saveDismissedLive(keys) { saveSessionJSON(LIVE_KEY, keys); }

/* Live-Einträge tragen stabile Keys, damit das Ausblenden nur die Glocke
   betrifft: Zähler in Kopfzeile und Banner bleiben bis zur Antwort stehen. */
function liveRows(pulseData) {
  var p = pulseData || lastPulse;
  var rows = [];
  ((p && p.questions) || []).forEach(function (question) {
    var id = String((question && question.id) || '');
    if (!id) return;
    rows.push({key: 'question:' + id,
      text: tr('Frage') + ': ' + String(question.text || ''),
      sub: String(question.project || ''), question: question, href: ''});
  });
  ((p && p.blocked) || []).forEach(function (item) {
    var id = String((item && (item.id || item.title)) || '');
    rows.push({key: 'blocked:' + id,
      text: tr('Blockiert') + ': ' + id, sub: String((item && item.project) || ''),
      href: '#/project/' + encodeURIComponent(String((item && item.project) || '')) + '/work'});
  });
  ((p && p.failed) || []).forEach(function (item) {
    var name = String((item && item.name) || '');
    rows.push({key: 'failed:' + name,
      text: tr('Lauf fehlgeschlagen') + ': ' + name,
      sub: String(((item && item.run) || {}).run_id || ''),
      href: '#/project/' + encodeURIComponent(name) + '/output'});
  });
  ((p && p.running) || []).forEach(function (item) {
    var name = String((item && item.name) || '');
    rows.push({key: 'running:' + name,
      text: tr('Lauf läuft') + ': ' + name, sub: '',
      href: '#/project/' + encodeURIComponent(name) + '/output'});
  });
  return rows;
}

function renderBell(pulseData) {
  if (pulseData) lastPulse = pulseData;
  var stored = readNotifications().filter(function (entry) { return !entry.read; });
  var dismissed = readDismissedLive();
  var live = liveRows().filter(function (row) {
    return dismissed.indexOf(row.key) === -1;
  });
  var count = stored.length + live.length;
  var badge = document.querySelector('[data-nv-bell-count]');
  if (badge) {
    badge.textContent = String(count);
    if (count) badge.removeAttribute('hidden'); else badge.setAttribute('hidden', '');
  }
  var panel = document.querySelector('[data-nv-bell-panel]');
  if (!panel) return;
  var head = el('div', {class: 'nv-drawer-head'},
    el('span', {class: 'nv-drawer-title'}, tr('Benachrichtigungen')),
    el('button', {class: 'nv-btn nv-ghost nv-close', type: 'button',
      'data-nv-bell-close': '', 'aria-label': tr('Benachrichtigungen schließen'),
      title: tr('Benachrichtigungen schließen')}, '×'));
  var explain = el('p', {class: 'nv-bell-explain', 'data-nv-bell-explain': ''},
    tr('Glocke: dauerhafte Hinweise. Toasts: kurzes Feedback.'));
  var clear = el('button', {class: 'nv-btn nv-ghost nv-bell-clear', type: 'button',
    'data-nv-bell-clear': ''}, tr('Alle als gelesen'));
  var list = el('div', {class: 'nv-bell-list'});
  stored.forEach(function (entry) {
    var main = el('div', {class: 'nv-bell-row-main'},
      el('span', {class: 'nv-bell-text'}, entry.text));
    if (entry.kind === 'question') {
      main.append(el('button', {class: 'nv-bell-link', type: 'button',
        'data-nv-notification-open': '', on: {click: function () {
          NV.questions.openInbox();
        }}}, tr('Öffnen')));
    } else if (entry.href) {
      main.append(el('a', {class: 'nv-bell-link', href: entry.href}, tr('Öffnen')));
    }
    list.append(el('div', {class: 'nv-bell-row', 'data-nv-notification': '',
      'data-nv-notification-id': entry.id}, main,
      el('button', {class: 'nv-bell-dismiss', type: 'button',
        'data-nv-notification-dismiss': '', 'aria-label': tr('Eintrag schließen'),
        title: tr('Eintrag schließen'), on: {click: function (event) {
          event.stopPropagation();
          NV.dismissNotification(entry.id);
        }}}, '×')));
  });
  live.forEach(function (row) {
    var main = el('div', {class: 'nv-bell-row-main'},
      el('span', {class: 'nv-bell-text'}, String(row.text)));
    if (row.sub) main.append(el('small', {class: 'nv-bell-sub'}, String(row.sub)));
    if (row.question) {
      main.append(el('button', {class: 'nv-btn nv-ghost nv-bell-answer', type: 'button',
        'data-nv-live-question-open': '', on: {click: function () {
          closeBellPanel();
          NV.questions.openInbox();
        }}}, tr('Antworten')));
    } else if (row.href) {
      main.append(el('a', {class: 'nv-bell-link', href: row.href}, tr('Öffnen')));
    }
    list.append(el('div', {class: 'nv-bell-row nv-bell-live',
      'data-nv-live-item': '', 'data-nv-live-key': row.key}, main,
      el('button', {class: 'nv-bell-dismiss', type: 'button',
        'data-nv-live-dismiss': '',
        'aria-label': tr('Eintrag schließen'), title: tr('Eintrag schließen'),
        on: {click: function (event) {
          event.stopPropagation();
          var keys = readDismissedLive();
          if (keys.indexOf(row.key) === -1) keys.push(row.key);
          saveDismissedLive(keys);
          renderBell();
        }}}, '×')));
  });
  if (!stored.length && !live.length) {
    list.append(el('p', {class: 'nv-muted nv-bell-empty'},
      tr('Keine Benachrichtigungen gerade')));
  }
  panel.replaceChildren(head, explain, clear, list);
}

/* Glocke aus den vertraglichen Quellen auffüllen; ein fehlgeschlagener
   Detailaufruf darf die gespeicherten Einträge nicht verdecken. */
async function refreshBell() {
  try {
    renderBell(await NV.pulse());
  } catch (error) {
    if (error && error.status === 403) showLogin();
    renderBell({questions: NV.questions.list(), blocked: [], failed: [], running: []});
  }
}
NV.refreshBell = refreshBell;

/* ---------- F34: zentrale Rückfragen ---------- */

var SEEN_KEY = 'nv-seen-questions';
var questionsState = {list: [], loading: false, firstLoad: true};

function readSeenQuestions() {
  var data = readSessionJSON(SEEN_KEY, []);
  return Array.isArray(data) ? data.map(String) : [];
}
function saveSeenQuestions(ids) {
  saveSessionJSON(SEEN_KEY, ids.slice(-200));
}

function updateQuestionUI() {
  var open = questionsState.list.length;
  var button = document.querySelector('[data-nv-questions-button]');
  if (button) {
    var count = button.querySelector('[data-nv-questions-count]');
    if (count) {
      count.textContent = String(open);
      if (open) count.removeAttribute('hidden'); else count.setAttribute('hidden', '');
    }
    button.classList.toggle('is-active', open > 0);
    if (open) {
      setAttrTxVars(button, 'aria-label', 'Offene Fragen: {{n}}', {n: open});
    } else {
      setAttrTx(button, 'aria-label', 'Fragen');
    }
  }
  var banner = document.querySelector('[data-nv-question-banner]');
  if (banner) {
    if (!open) {
      banner.hidden = true;
      banner.replaceChildren();
    } else {
      var latest = questionsState.list[questionsState.list.length - 1] || {};
      var text = String(latest.text || '');
      if (text.length > 120) text = text.slice(0, 117) + '…';
      banner.replaceChildren(
        el('span', {class: 'nv-question-banner-count'},
          tr('{{n}} offene Fragen', {n: open})),
        el('span', {class: 'nv-question-banner-text'}, text),
        el('span', {class: 'nv-question-banner-meta'},
          [latest.project, latest.agent].filter(Boolean).map(String).join(' · ')),
        el('button', {class: 'nv-btn nv-primary', type: 'button',
          'data-nv-question-banner-open': ''}, tr('Antworten')));
      banner.hidden = false;
    }
  }
}

async function loadQuestions() {
  if (questionsState.loading || !authorized) return;
  questionsState.loading = true;
  try {
    var data = await api('/api/questions');
    if (!authorized) return;
    var list = (data && Array.isArray(data.questions)) ? data.questions.filter(function (q) {
      return q && q.id != null;
    }) : [];
    var seen = readSeenQuestions();
    var first = questionsState.firstLoad;
    var additions = [];
    list.forEach(function (question) {
      var id = String(question.id);
      if (seen.indexOf(id) === -1) {
        if (!first) additions.push(question);
        seen.push(id);
      }
    });
    questionsState.firstLoad = false;
    saveSeenQuestions(seen);
    questionsState.list = list;
    updateQuestionUI();
    renderBell({questions: list,
      blocked: (lastPulse && lastPulse.blocked) || [],
      failed: (lastPulse && lastPulse.failed) || [],
      running: (lastPulse && lastPulse.running) || []});
    additions.forEach(function (question) {
      NV.notify(tr('Neue Rückfrage') + ': ' + String(question.text || ''),
        {kind: 'question'});
    });
  } catch (error) {
    if (error && error.status === 403) showLogin();
  } finally {
    questionsState.loading = false;
  }
}

NV.questions = {
  list: function () { return questionsState.list.slice(); },
  count: function () { return questionsState.list.length; },
  load: loadQuestions,
  refresh: loadQuestions,
  remove: function (id) {
    var key = String(id);
    questionsState.list = questionsState.list.filter(function (question) {
      return String(question.id) !== key;
    });
    updateQuestionUI();
    renderBell({questions: questionsState.list,
      blocked: (lastPulse && lastPulse.blocked) || [],
      failed: (lastPulse && lastPulse.failed) || [],
      running: (lastPulse && lastPulse.running) || []});
    loadQuestions();
  },
  openInbox: function () {
    if (!NV.questionCard) return;
    var section = el('section', {'data-nv-question-inbox': ''},
      el('h3', {}, tr('Offene Fragen')));
    if (!questionsState.list.length) {
      section.append(el('p', {class: 'nv-empty'}, tr('Keine offenen Fragen.')));
    } else {
      questionsState.list.forEach(function (question) {
        section.append(NV.questionCard(question, {
          onAnswered: function () {
            if (!questionsState.list.length) {
              section.append(el('p', {class: 'nv-empty'}, tr('Keine offenen Fragen.')));
            }
          }
        }));
      });
    }
    NV.context.open({title: tr('Offene Fragen'), content: section});
  }
};

/* Sprachwechsel: nur von tr() stammende Knoten/Attribute umschalten; Daten
   aus Protokollen und Nutzereingaben bleiben unberührt (wie in app.js). */
function retranslateDOM() {
  var walk = function (node) {
    if (node.nodeType === 3) {
      var mark = node.__i18n;
      if (mark && node.parentNode && !node.parentNode.closest('[aria-label="Language"]')) {
        node.nodeValue = String(tr(mark.key, mark.vars));
      }
      return;
    }
    if (node.nodeType !== 1 || node.closest('[aria-label="Language"]')) return;
    var own = node.__i18n;
    if (node.__i18nOwn && own) setTx(node, tr(own.key, own.vars));
    var attrs = node.__i18nAttrs;
    if (attrs) Object.keys(attrs).forEach(function (attribute) {
      var mark = attrs[attribute];
      node.setAttribute(attribute, String(tr(mark.key, mark.vars)));
    });
    Array.prototype.slice.call(node.childNodes).forEach(walk);
  };
  walk(document.body);
}

/* ---------- F34: Kontext-Panel, Suche und Filterleiste ---------- */

/* Beliebige Inhalte (Text, Boxed-String, Knoten, Arrays) in einen Container
   übernehmen — ohne innHTML und ohne Objekte als "[object …]" auszugeben. */
function fillNode(target, value) {
  if (!target) return;
  var holder = el('div', {}, value);
  target.replaceChildren.apply(target, Array.prototype.slice.call(holder.childNodes));
}

var contextPanel = document.querySelector('aside[data-nv-context]');
var contextScrim = document.querySelector('[data-nv-context-scrim]');

NV.context = {
  open: function (options) {
    if (!contextPanel) return;
    var opts = options || {};
    var title = contextPanel.querySelector('[data-nv-context-title]');
    var body = contextPanel.querySelector('[data-nv-context-body]');
    var foot = contextPanel.querySelector('[data-nv-context-foot]');
    fillNode(title, opts.title == null ? '' : opts.title);
    fillNode(body, opts.content == null ? '' : opts.content);
    fillNode(foot, opts.footer == null ? '' : opts.footer);
    contextPanel.hidden = false;
    if (contextScrim) contextScrim.hidden = false;
    document.body.setAttribute('data-nv-context-open', 'true');
  },
  close: function () {
    if (contextPanel) contextPanel.hidden = true;
    if (contextScrim) contextScrim.hidden = true;
    document.body.removeAttribute('data-nv-context-open');
  },
  isOpen: function () { return !!contextPanel && !contextPanel.hidden; }
};

NV.search = function (options) {
  var opts = options || {};
  var input = opts.input;
  if (!input) {
    input = el('input', {type: 'search', 'data-nv-search-input': '',
      placeholder: opts.placeholder || tr('Suchen'),
      'aria-label': opts.placeholder || tr('Suchen')});
  }
  input.setAttribute('type', 'search');
  input.setAttribute('data-nv-search-input', '');
  var icon = el('span', {class: 'nv-search-icon', 'aria-hidden': 'true'}, '⌕');
  var clearLabel = tr('Suche löschen');
  var clear = el('button', {class: 'nv-search-clear', type: 'button',
    'data-nv-search-clear': '', 'aria-label': clearLabel, title: clearLabel}, '×');
  var wrap = el('div', {class: 'nv-search', 'data-nv-search': ''}, icon, input, clear);
  function sync() {
    var hasValue = !!(input.value && String(input.value).length);
    clear.disabled = !hasValue;
  }
  input.addEventListener('input', function () {
    sync();
    if (typeof opts.oninput === 'function') opts.oninput(input.value);
  });
  clear.addEventListener('click', function () {
    input.value = '';
    sync();
    input.dispatchEvent(new Event('input', {bubbles: true}));
    input.focus();
  });
  sync();
  return wrap;
};

NV.filterBar = function () {
  var bar = el('div', {class: 'nv-filter-bar', 'data-nv-filter-bar': ''});
  Array.prototype.slice.call(arguments).forEach(function (child) { bar.append(child); });
  return bar;
};

/* Bestandsansichten (z. B. die Startseite) haben bereits Inputs. Wir hüllen
   sie ein, statt sie zu ersetzen — ihre Listener bleiben damit erhalten. */
function enhanceView(main) {
  if (!main) return;
  main.querySelectorAll('input[type="search"]').forEach(function (input) {
    if (input.closest('[data-nv-search]')) return;
    var parent = input.parentNode;
    if (!parent) return;
    var next = input.nextSibling;
    // NV.search übernimmt das vorhandene Input (Listener bleiben erhalten).
    var wrap = NV.search({input: input, placeholder: input.getAttribute('placeholder')});
    parent.insertBefore(wrap, next);
  });
  var search = main.querySelector('[data-nv-search]');
  if (!search || main.querySelector('[data-nv-filter-bar]')) return;
  var row = search.parentNode;
  if (!row || row === main || row.classList.contains('nv-card')) row = search;
  var bar = NV.filterBar();
  row.parentNode.insertBefore(bar, row);
  bar.append(row);
}

/* ---------- Boot ---------- */

async function boot() {
  applyTheme();
  applyAnimations();
  applyAccent();
  initChrome();
  try {
    if (T) await api('/api/login', {token: T});
    await api('/api/projects');
    authorized = true;
    await render();
    refreshBell();
    loadQuestions();
    // F34: Poll nur bei sichtbarem Tab; Antworten aktualisieren zusätzlich
    // lokal über NV.questions.remove().
    setInterval(function () {
      if (document.visibilityState === 'visible') loadQuestions();
    }, 5000);
  } catch (error) {
    showLogin();
  }
}

boot();
