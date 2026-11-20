/* AP22 — Einstellungen: Erscheinung, Sprache, Zugriff, Feature-Schalter und
   die erweiterten Bereiche limits/gates. Weitere erweiterte Bereiche folgen
   in Meilenstein C; hier wird für sie noch nichts gerendert.
   Fachfehler erscheinen in [data-nv-form-error] und als Toast. */
'use strict';

var NV_FEATURES = [
  'github', 'models', 'profiles', 'mcp', 'costs', 'harness', 'limits',
  'gates', 'env', 'sandbox', 'writeaccess', 'agentsfile', 'priority', 'runs'
];

/* Drei verständliche Gruppen statt 14 ungeordneter Zeilen. Die Reihenfolge
   ist bewusst nach Nutzerinteresse, nicht nach Interna gewählt. */
var NV_FEATURE_GROUPS = [
  {title: 'Git & Code', ids: ['github', 'agentsfile', 'writeaccess']},
  {title: 'Modelle & Agenten-Extras', ids: ['models', 'profiles', 'mcp', 'costs', 'harness']},
  {title: 'Infrastruktur & Diagnose', ids: ['limits', 'gates', 'env', 'sandbox', 'priority', 'runs']}
];

/* Ein kurzer, laienverständlicher Hilfesatz je Schalter (deutsche
   Quellschlüssel, en/de im Wörterbuch). */
var NV_FEATURE_HELP = {
  github: 'GitHub verbinden und Projekte von dort auschecken.',
  agentsfile: 'Die AGENTS.md eines Projekts bearbeiten.',
  writeaccess: 'Schreibrechte für jedes Projekt festlegen.',
  models: 'Modellkatalog und Modellauswahl anzeigen.',
  profiles: 'Gespeicherte Profile ansehen und übernehmen.',
  mcp: 'Zusätzliche MCP-Werkzeuge verwalten.',
  costs: 'Kostenübersicht und Preise anzeigen.',
  harness: 'Harness-Status und Auswahl anzeigen.',
  limits: 'Grenzen für Agentenläufe festlegen.',
  gates: 'Qualitäts-Schranken global und je Projekt setzen.',
  env: 'Umgebung prüfen und Dienste wie Emulator oder Server steuern.',
  sandbox: 'Sandbox-Optionen für Projekte anzeigen.',
  priority: 'Arbeitspakete nach Wichtigkeit sortieren.',
  runs: 'Run-Register ansehen und bereinigen.'
};

function settingsErrorBox() {
  return el('div', {class: 'nv-form-error', 'data-nv-form-error': '', hidden: ''});
}

function settingsError(box, message) {
  var text = String(message || '');
  box.textContent = text;
  if (text) { box.removeAttribute('hidden'); toast(bt(text)); }
  else box.setAttribute('hidden', '');
}

NV.views.settings = async function settings(context, token) {
  var engine = i18n();
  var security = {port: '', bind: '', allowlist: [], password_set: false, restart_required: false};
  try { security = await api('/api/security') || security; } catch (error) { /* Ansicht bleibt lesbar */ }
  if (NV.stale(token)) return;

  var main = document.getElementById('nv-main');
  var cards = [];

  /* ---------- Erscheinung ---------- */
  var themeSelect = el('select', {'data-nv-theme-select': '', 'aria-label': tr('Darstellung')});
  [['light', 'Hell'], ['dark', 'Dunkel'], ['auto', 'System']].forEach(function (option) {
    themeSelect.append(el('option', {value: option[0]}, tr(option[1])));
  });
  // Der Select zeigt die Präferenz, NV.setTheme hält ihn bei Header-Wechsel
  // aktuell; data-theme bleibt der aufgelöste Wert.
  themeSelect.value = NV.themePreference();
  themeSelect.addEventListener('change', function () { NV.setTheme(themeSelect.value); });
  cards.push(el('section', {class: 'nv-card', 'data-nv-ssection': 'appearance'},
    el('h2', {}, tr('Erscheinung')),
    el('label', {}, tr('Darstellung')), themeSelect));

  /* ---------- Sprache (global, serverseitig wie im Bestand) ---------- */
  var langSelect = el('select', {'aria-label': 'Language'});
  [['en', 'English'], ['de', 'Deutsch']].forEach(function (option) {
    langSelect.append(el('option', {value: option[0]}, option[1]));
  });
  langSelect.value = engine && typeof engine.current === 'function' ? engine.current() : 'en';
  langSelect.addEventListener('change', async function () {
    var next = langSelect.value;
    var previous = engine.current();
    if (next === previous) return;
    langSelect.disabled = true;
    try {
      // Erst speichern, dann lokal umschalten: der Reload danach liest die
      // Sprache aus dem Meta-Feld und darf nicht auf den alten Stand fallen.
      var result = await api('/api/language', {language: next});
      if (!result.ok) throw new Error(errText(result, 400));
      engine.set(next);
      toast(bt(result.message) || tr('Sprache gespeichert'));
    } catch (error) {
      langSelect.value = previous;
      toast(tr('Sprache konnte nicht gespeichert werden: ') + String(error && error.message || error));
    } finally {
      langSelect.disabled = false;
    }
  });
  cards.push(el('section', {class: 'nv-card', 'data-nv-ssection': 'language'},
    el('h2', {}, tr('Sprache')),
    el('p', {class: 'nv-muted'}, tr('ui.language.hint')), langSelect));

  /* ---------- Zugriff: Anmeldung prominent, Netzwerk untergeordnet ---------- */
  var password = el('input', {type: 'password', 'data-nv-field': 'password',
    placeholder: tr('neues Passwort (mind. 8 Zeichen)'), 'aria-label': tr('Neues Passwort')});
  var repeat = el('input', {type: 'password', 'data-nv-field': 'password-repeat',
    placeholder: tr('Passwort wiederholen'), 'aria-label': tr('Passwort wiederholen')});
  var portInput = el('input', {inputmode: 'numeric', 'data-nv-field': 'port',
    placeholder: String(security.port || ''), 'aria-label': 'Port'});
  var bindInput = el('input', {'data-nv-field': 'bind',
    placeholder: String(security.bind || ''), 'aria-label': tr('Bind-Adresse')});
  var allowInput = el('input', {'data-nv-field': 'allowlist',
    placeholder: (security.allowlist || []).join(', '), 'aria-label': tr('IP-Allowlist')});
  var accessError = settingsErrorBox();
  var note = el('p', {class: 'nv-note', 'data-nv-restart-note': ''},
    tr('Änderungen an Port, Bind-Adresse und Allowlist werden in ui.json gespeichert und wirken erst nach einem Neustart des Dashboards.'));
  var passwordSet = el('button', {class: 'nv-btn nv-primary', type: 'button',
    'data-nv-action': 'password-set', on: {click: async function () {
      settingsError(accessError, '');
      if (String(password.value || '') !== String(repeat.value || '')) {
        settingsError(accessError, tr('Passwörter stimmen nicht überein'));
        return;
      }
      try {
        var result = await api('/api/security', {action: 'password', password: password.value});
        if (result.ok) {
          password.value = ''; repeat.value = '';
          toast(bt(result.message) || tr('Kennwort gesetzt'));
        } else settingsError(accessError, bt(result.message));
      } catch (error) { settingsError(accessError, String(error && error.message || error)); }
    }}}, tr('Passwort setzen'));
  var passwordClear = el('button', {class: 'nv-btn', type: 'button',
    'data-nv-action': 'password-clear', on: {click: async function () {
      try {
        var result = await api('/api/security', {action: 'password', clear: true});
        toast(bt(result.message) || tr('Kennwort entfernt'));
      } catch (error) { settingsError(accessError, String(error && error.message || error)); }
    }}}, tr('Passwort entfernen'));
  var securitySave = el('button', {class: 'nv-btn nv-secondary', type: 'button',
    'data-nv-action': 'security-save', on: {click: async function () {
      settingsError(accessError, '');
      var update = {action: 'save'};
      var rawPort = String(portInput.value || '').trim();
      if (rawPort) {
        if (!/^\d+$/.test(rawPort)) {
          settingsError(accessError, tr('Bitte eine gültige Portnummer eingeben.'));
          return;
        }
        update.port = Number(rawPort);
      }
      if (String(bindInput.value || '').trim()) update.bind = String(bindInput.value).trim();
      if (String(allowInput.value || '').trim()) {
        update.allowlist = String(allowInput.value).split(/[\s,]+/).filter(Boolean);
      }
      try {
        var result = await api('/api/security', update);
        if (result.ok) {
          portInput.value = ''; bindInput.value = ''; allowInput.value = '';
          toast(bt(result.message) || tr('Zugriffssicherheit gespeichert'));
        } else settingsError(accessError, bt(result.message));
      } catch (error) { settingsError(accessError, String(error && error.message || error)); }
    }}}, tr('Speichern'));
  var logout = el('button', {class: 'nv-btn', type: 'button',
    'data-nv-action': 'logout', on: {click: function () { NV.logout(); }}}, tr('Abmelden'));

  var signIn = el('div', {class: 'nv-access-signin'},
    el('h3', {}, tr('Anmeldung')),
    el('label', {}, tr('Neues Passwort')), password,
    el('label', {}, tr('Passwort wiederholen')), repeat,
    el('div', {class: 'nv-row'}, passwordSet, passwordClear, logout));
  var network = el('div', {class: 'nv-access-network'},
    el('h3', {}, tr('Netzwerk (erweitert)')),
    el('p', {class: 'nv-note'}, tr('Netzwerk-Hinweis')),
    el('label', {}, 'Port'), portInput,
    el('label', {}, tr('Bind-Adresse')), bindInput,
    el('label', {}, tr('IP-Allowlist')), allowInput,
    el('div', {class: 'nv-row'}, securitySave), note);
  cards.push(el('section', {class: 'nv-card', 'data-nv-ssection': 'access'},
    el('h2', {}, tr('Zugriffssicherheit')), signIn, network, accessError));

  /* ---------- Feature-Schalter (alle standardmäßig aus) ---------- */
  var featureRows = NV_FEATURE_GROUPS.map(function (group) {
    var rows = group.ids.map(function (id) {
      var box = el('input', {type: 'checkbox', 'data-nv-feature': id, checked: NV.feature(id)});
      box.addEventListener('change', function () { NV.setFeature(id, box.checked); });
      return el('label', {class: 'nv-switch-row'}, box,
        el('span', {class: 'nv-feature-text'},
          el('strong', {}, id),
          el('small', {}, tr(NV_FEATURE_HELP[id] || id))));
    });
    return el('div', {class: 'nv-feature-group'},
      el('h3', {}, tr(group.title)), ...rows);
  });
  cards.push(el('section', {class: 'nv-card', 'data-nv-ssection': 'features'},
    el('h2', {}, tr('Funktionen')),
    el('p', {class: 'nv-muted'}, tr('Technische Bereiche sind standardmäßig ausgeblendet.')),
    featureRows));

  /* ---------- Erweiterte Bereiche (nur mit eingeschaltetem Feature) ---------- */
  var advanced = el('section', {class: 'nv-section', 'data-nv-ssection': 'advanced'},
    el('h2', {}, tr('Erweiterte Bereiche')));

  if (NV.feature('limits')) {
    var limits = {mode: 'stop', lines: []};
    try { limits = await api('/api/limits') || limits; } catch (error) { /* Default anzeigen */ }
    if (NV.stale(token)) return;
    var limitsBox = el('div', {class: 'nv-card', 'data-nv-advanced': 'limits'},
      el('h3', {}, tr('Limits')),
      el('p', {}, tr('Modus') + ': ' + String(limits.mode || 'stop')),
      el('div', {class: 'nv-row'},
        el('button', {class: 'nv-btn', type: 'button', 'data-nv-action': 'limits-continue',
          on: {click: async function () { await changeLimit('continue', token); }}}, tr('Fortsetzen')),
        el('button', {class: 'nv-btn', type: 'button', 'data-nv-action': 'limits-stop',
          on: {click: async function () { await changeLimit('stop', token); }}}, tr('Stopp'))));
    advanced.append(limitsBox);
  }

  if (NV.feature('gates')) {
    var gates = {gates: {}, lines: []};
    try { gates = await api('/api/gates') || gates; } catch (error) { /* leere Ansicht */ }
    if (NV.stale(token)) return;
    var table = el('div', {class: 'nv-list'});
    Object.keys(gates.gates || {}).forEach(function (key) {
      table.append(el('div', {class: 'nv-row'},
        el('code', {}, key),
        el('span', {}, String(gates.gates[key].value)),
        el('span', {class: 'nv-muted'}, String(gates.gates[key].origin))));
    });
    var gateKey = el('select', {'data-nv-field': 'gates-key', 'aria-label': tr('Schranke')});
    Object.keys(gates.gates || {}).forEach(function (key) {
      gateKey.append(el('option', {value: key}, key));
    });
    var gateValue = el('input', {'data-nv-field': 'gates-value', 'aria-label': tr('Wert')});
    var gateProject = el('input', {'data-nv-field': 'gates-project',
      placeholder: tr('Projekt (optional)'), 'aria-label': tr('Projekt (optional)')});
    var gateError = settingsErrorBox();
    var gateSave = el('button', {class: 'nv-btn nv-secondary', type: 'button',
      'data-nv-action': 'gates-save', on: {click: async function () {
        settingsError(gateError, '');
        var body = {key: gateKey.value, value: String(gateValue.value || '')};
        var project = String(gateProject.value || '').trim();
        if (project) body.project = project;
        try {
          var result = await api('/api/gates', body);
          if (result.ok) { gateValue.value = ''; NV.render(); }
          else settingsError(gateError, bt(result.message) || tr('Speichern fehlgeschlagen'));
        } catch (error) {
          settingsError(gateError, tr('Speichern fehlgeschlagen: ') + String(error && error.message || error));
        }
      }}}, tr('Speichern'));
    advanced.append(el('div', {class: 'nv-card', 'data-nv-advanced': 'gates'},
      el('h3', {}, tr('Schranken')), table,
      el('label', {}, tr('Schranke')), gateKey,
      el('label', {}, tr('Wert')), gateValue,
      el('label', {}, tr('Projekt (optional)')), gateProject,
      el('div', {class: 'nv-row'}, gateSave), gateError));
  }

  cards.push(advanced);
  cards.push(el('p', {}, el('a', {class: 'nv-link', 'data-nv-classic-link': '', href: '/classic'},
    tr('Klassische Oberfläche öffnen'))));

  main.replaceChildren(el('h2', {class: 'nv-page-title'}, tr('Einstellungen')), ...cards);
  NV.refreshBell();
};

async function changeLimit(mode, token) {
  try {
    var result = await api('/api/limits', {action: mode});
    if (!result.ok) toast(bt(result.message) || tr('Speichern fehlgeschlagen'));
  } catch (error) {
    toast(tr('Speichern fehlgeschlagen: ') + String(error && error.message || error));
  }
  if (!NV.stale(token)) NV.render();
}
