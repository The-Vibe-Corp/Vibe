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

var toastBox = document.getElementById('nv-toasts');
function toast(message) {
  if (!toastBox) return;
  var card = el('div', {class: 'nv-toast'}, el('span', {}, String(message)),
    el('button', {class: 'nv-toast-close', type: 'button',
      'aria-label': tr('Meldung schließen'), on: {click: function () { card.remove(); }}}, '×'));
  toastBox.append(card);
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

NV.setFeature = function (id, enabled) {
  var all = featureMap();
  if (enabled) all[id] = true; else delete all[id];
  localStorage.setItem('nv-features', JSON.stringify(all));
  window.dispatchEvent(new CustomEvent('nv:featureschange', {detail: {id: id, on: !!enabled}}));
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
    return Promise.resolve(renderer(context, token)).catch(function (error) {
      if (token !== RENDER_TOKEN) return;
      toast(tr('Ansicht konnte nicht geladen werden: ') + String(error && error.message || error));
    });
  });
}
NV.render = render;

/* ---------- Kopfzeile, Anmeldung und Benachrichtigungen ---------- */

var NAV_KEYS = {home: 'Start', agents: 'Agenten', activity: 'Aktivität', settings: 'Einstellungen'};

function initChrome() {
  var skip = document.querySelector('.nv-skip');
  if (skip) setTx(skip, tr('Zum Inhalt springen'));
  var toggle = document.querySelector('[data-nv-nav-toggle]');
  if (toggle) {
    setTx(toggle, '☰');
    setAttrTx(toggle, 'aria-label', 'Menü');
    setAttrTx(toggle, 'title', 'Menü');
    toggle.addEventListener('click', function () {
      var open = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', open ? 'false' : 'true');
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
    setAttrTx(animToggle.parentNode, 'aria-label', 'Animationen');
    setAttrTx(animToggle.parentNode, 'title', 'Animationen');
    animToggle.addEventListener('change', function () {
      NV.setAnimations(animToggle.checked);
    });
  }
  var themeToggle = document.querySelector('[data-nv-theme-toggle]');
  if (themeToggle) {
    setTx(themeToggle, '◐');
    setAttrTx(themeToggle, 'aria-label', 'Darstellung wechseln');
    setAttrTx(themeToggle, 'title', 'Darstellung wechseln');
    themeToggle.addEventListener('click', function () { NV.toggleTheme(); });
  }
  var bell = document.querySelector('[data-nv-bell]');
  if (bell) {
    setAttrTx(bell, 'aria-label', 'Benachrichtigungen');
    setAttrTx(bell, 'title', 'Benachrichtigungen');
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
    if (event.key === 'Escape') closeBellPanel();
  });
  window.addEventListener('hashchange', function () { render(); });
  window.addEventListener('vibe:langchange', function () {
    retranslateDOM();
    setTimeout(function () { render(); }, 20);
  });
  window.addEventListener('nv:featureschange', function () { render(); });
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

/* Glocke: offene Fragen + laufende Läufe. Weitere Quellen (blockierte Pakete,
   fehlgeschlagene Läufe) kommen in Meilenstein B hinzu — die Liste ist dafür
   schon als Einträge mit Link aufgebaut. */
async function refreshBell() {
  try {
    var questions = await api('/api/questions');
    var projects = await api('/api/projects');
    var open = (questions && questions.questions) || [];
    var running = (projects || []).filter(function (row) { return !!row.running; });
    var count = open.length + running.length;
    var badge = document.querySelector('[data-nv-bell-count]');
    var panel = document.querySelector('[data-nv-bell-panel]');
    if (badge) {
      badge.textContent = String(count);
      if (count) badge.removeAttribute('hidden'); else badge.setAttribute('hidden', '');
    }
    if (panel) {
      var rows = [];
      open.forEach(function (question) {
        var project = String(question.project || '');
        rows.push(el('a', {class: 'nv-bell-item', href: '#/project/' + encodeURIComponent(project)},
          tr('Frage') + ': ' + String(question.text || '') + ' — ' + project));
      });
      running.forEach(function (row) {
        rows.push(el('a', {class: 'nv-bell-item', href: '#/project/' + encodeURIComponent(row.name) + '/output'},
          tr('Lauf läuft') + ': ' + String(row.name)));
      });
      if (!rows.length) {
        rows.push(el('p', {class: 'nv-muted nv-bell-empty'}, tr('Keine Benachrichtigungen gerade')));
      }
      var head = el('div', {class: 'nv-drawer-head'},
        el('span', {class: 'nv-drawer-title'}, tr('Benachrichtigungen')),
        el('button', {class: 'nv-btn nv-ghost nv-close', type: 'button',
          'data-nv-bell-close': '', 'aria-label': tr('Benachrichtigungen schließen'),
          title: tr('Benachrichtigungen schließen')}, '×'));
      // Wichtig: replaceChildren flacht Arrays nicht. Das frühere Übergeben des
      // rows-Arrays erzeugte "[object HTMLDivElement]" im Panel.
      panel.replaceChildren.apply(panel, [head].concat(rows));
    }
  } catch (error) {
    if (error && error.status === 403) showLogin();
  }
}
NV.refreshBell = refreshBell;

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

/* ---------- Boot ---------- */

async function boot() {
  applyTheme();
  applyAnimations();
  initChrome();
  try {
    if (T) await api('/api/login', {token: T});
    await api('/api/projects');
    authorized = true;
    await render();
    refreshBell();
  } catch (error) {
    showLogin();
  }
}

boot();
