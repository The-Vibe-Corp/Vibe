/* AP22 — Einstellungen: Erscheinung, Sprache, Zugriff, Feature-Schalter und
   alle erweiterten Bereiche (Modelle, Profile, MCP, Kosten, Harness, Limits,
   Schranken, Umgebung, Läufe). Jeder Bereich wird nur bei eingeschaltetem
   Feature gerendert. Fachfehler erscheinen in [data-nv-form-error] und als
   Toast; Backend-Antworten werden nie roh als HTML eingebaut. */
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
    placeholder: String(security.port || ''), 'aria-label': tr('Port')});
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
    el('label', {}, tr('Port')), portInput,
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

  /* Meilenstein C: die übrigen erweiterten Bereiche. Jeder Builder holt sich
     seine Daten selbst und prüft vor dem Einbau den Render-Token. */
  var moreAdvanced = [
    ['models', buildModelsSection],
    ['profiles', buildProfilesSection],
    ['mcp', buildMcpSection],
    ['costs', buildCostsSection],
    ['harness', buildHarnessSection],
    ['env', buildEnvSection],
    ['runs', buildRunsSection]
  ];
  for (var index = 0; index < moreAdvanced.length; index++) {
    if (!NV.feature(moreAdvanced[index][0])) continue;
    var section = await moreAdvanced[index][1](token);
    if (NV.stale(token)) return;
    if (section) advanced.append(section);
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

/* ---------- Gemeinsame Helfer der erweiterten Bereiche ---------- */

function nvText(value) { return String(value == null ? '' : value); }

function nvNumber(value) {
  var engine = i18n();
  return engine && typeof engine.number === 'function'
    ? String(engine.number(value)) : String(value || 0);
}

function nvCurrency(value) {
  var engine = i18n();
  return engine && typeof engine.currency === 'function'
    ? String(engine.currency(value)) : String(value || 0) + ' €';
}

/* Backend-Antworten bleiben deutsch; bt() übersetzt nur bekannte Meldungen. */
function nvBackend(value) { return String(bt(value)); }

/* Ein Profilwechsel schreibt mehrere Agentendateien. Früher wurde dazu ein
   synchroner XHR (nvPostSync) benutzt, um einen überholten Test-Wartezustand
   zu bedienen. Der Test wartet jetzt auf die echte Wirkung in tester.md;
   der gewöhnliche asynchrone api()-Aufruf genügt und blockiert den Browser
   nicht mehr. */

function nvActionError(box, error) {
  settingsError(box, String(tr('Aktion fehlgeschlagen: ')) + String(error && error.message || error));
}

/* Modellkatalog: dieselbe Trennung von Fakten und Einschätzungen wie in der
   klassischen UI (Wert, Art und Quelle je Angabe). */
function nvMval(node) {
  if (node && typeof node === 'object') {
    return nvText(node.wert != null ? node.wert : (node.text != null ? node.text : tr('unbekannt')));
  }
  return String(tr('unbekannt'));
}
function nvMsrc(node) {
  if (!node || !node.quelle) return String(tr('unbekannt'));
  return nvText(node.quelle) + (node.datum ? ' (' + node.datum + ')' : '');
}
function nvMart(node) { return node && node.art ? ' [' + String(tr(node.art)) + ']' : ''; }
function nvAssert(label, node) {
  return el('div', {class: 'nv-muted'},
    el('b', {}, String(tr(label)) + ': '), nvMval(node), String(nvMart(node)),
    el('span', {class: 'nv-muted'}, ' — ' + nvMsrc(node)));
}
function nvModelLabel(id, info) {
  var model = info[id];
  if (!model) return id;
  var price = (model.preis || {}).text || String(tr('unbekannt'));
  var tempo = nvMval(((model.einschaetzungen || {}).tempo));
  return nvText(tr('Modell')) + ' ' + id + ' — ' + price + ' · ' + tempo;
}

/* ---------- Modelle: einklappbarer Katalog, Fakten ≠ Einschätzungen ---------- */

async function buildModelsSection(token) {
  var data;
  try { data = await api('/api/agents') || {}; } catch (error) { data = {}; }
  if (NV.stale(token)) return null;

  var info = data.info || {};
  var katalog = data.katalog || {};
  var ids = (data.models || []).slice();
  Object.keys(info).forEach(function (id) { if (ids.indexOf(id) < 0) ids.push(id); });

  // <details> ohne open: die Modellzeilen sind im Ruhezustand unsichtbar.
  var details = el('details', {class: 'nv-card', 'data-nv-model-catalog': ''},
    el('summary', {}, String(tr('Modellkatalog aufklappen'))));
  details.append(el('p', {class: 'nv-muted'},
    String(tr('Katalogstand')) + ': ' + nvText(data.stand || '?') + ' · '
    + String(tr('Katalogversion')) + ': ' + nvText(katalog.version || '?')));
  details.append(el('p', {class: 'nv-muted'}, nvBackend(data.hinweis || '')));

  var findings = katalog.findings || [];
  if (findings.length) {
    var findingList = el('ul', {class: 'nv-list'});
    findings.forEach(function (finding) {
      findingList.append(el('li', {}, nvText(finding.text || finding)));
    });
    details.append(el('div', {class: 'nv-note'},
      el('b', {}, String(tr('Katalogbefunde'))), findingList));
  }
  var sources = (katalog.quellen || []).map(function (source) {
    return nvText(source.name) + (source.datum ? ' (' + source.datum + ')' : '');
  });
  if (sources.length) {
    details.append(el('p', {class: 'nv-muted'},
      String(tr('Quellen des Katalogs')) + ': ' + sources.join('; ')));
  }

  var table = el('table', {class: 'nv-table'},
    el('tr', {}, el('th', {}, String(tr('Modell'))),
      el('th', {}, String(tr('Anbieter'))), el('th', {}, String(tr('Preis')))));
  ids.forEach(function (id) {
    var model = info[id] || {};
    var facts = model.fakten || {};
    var assessments = model.einschaetzungen || {};
    var factKeys = Object.keys(facts);
    var assessKeys = Object.keys(assessments);
    var factNodes = factKeys.map(function (key) { return nvAssert(key, facts[key]); });
    var assessNodes = assessKeys.map(function (key) { return nvAssert(key, assessments[key]); });
    var detail = el('tr', {class: 'nv-model-detail', 'data-nv-model-detail': id, hidden: ''},
      el('td', {colspan: '3'},
        el('div', {'data-nv-model-facts': ''},
          el('b', {}, String(tr('Fakten'))),
          ...factNodes,
          factKeys.length ? null : el('div', {class: 'nv-muted'}, String(tr('keine Angaben')))),
        el('div', {'data-nv-model-assessments': ''},
          el('b', {}, String(tr('Einschätzungen'))),
          ...assessNodes,
          assessKeys.length ? null : el('div', {class: 'nv-muted'}, String(tr('keine Angaben')))),
        el('div', {class: 'nv-muted'},
          String(tr('ID-Beleg')) + ': ' + nvText((model.id_beleg || {}).quelle || '—'))));
    var row = el('tr', {class: 'nv-model-row', 'data-nv-model': id,
      on: {click: function () { detail.hidden = !detail.hidden; }}},
      el('td', {}, nvModelLabel(id, info)),
      el('td', {class: 'nv-muted'}, nvText(model.anbieter || '?')),
      el('td', {}, nvText((model.preis || {}).text || String(tr('unbekannt')))));
    table.append(row, detail);
  });
  details.append(table);

  return el('div', {class: 'nv-card', 'data-nv-advanced': 'models'},
    el('h3', {}, String(tr('Modelle'))), details);
}

/* ---------- Profile: Vorschau before apply ---------- */

async function buildProfilesSection(token) {
  var data;
  try { data = await api('/api/agents') || {}; } catch (error) { data = {}; }
  if (NV.stale(token)) return null;

  var profiles = data.profiles || {};
  var names = Object.keys(profiles.profile || {});
  var select = el('select', {'data-nv-field': 'profile',
    'aria-label': String(tr('Profil auswählen'))});
  names.forEach(function (name) { select.append(el('option', {value: name}, name)); });
  if (profiles.aktiv) select.value = profiles.aktiv;

  var list = el('div', {class: 'nv-list'});
  names.forEach(function (name) {
    var roles = profiles.profile[name] || {};
    var summary = Object.keys(roles).filter(function (role) { return roles[role]; })
      .map(function (role) { return role + ': ' + roles[role]; }).join(' · ');
    list.append(el('div', {},
      el('b', {}, name + (name === profiles.aktiv ? ' (' + String(tr('aktiv')) + ')' : '')),
      el('div', {class: 'nv-muted'}, summary)));
  });

  var preview = el('div', {class: 'nv-note', 'data-nv-profile-preview': '', hidden: ''});
  var error = settingsErrorBox();
  var previewButton = el('button', {class: 'nv-btn', type: 'button',
    'data-nv-action': 'profile-preview', on: {click: function () {
      settingsError(error, '');
      var chosen = select.value;
      var profile = (profiles.profile || {})[chosen] || {};
      var rows = el('div', {});
      var any = false;
      Object.keys(profiles.rollen || {}).forEach(function (agent) {
        var model = profile[profiles.rollen[agent]];
        if (!model) return;
        any = true;
        rows.append(el('div', {}, nvText(agent) + ' → ' + nvText(model)));
      });
      if (!any) {
        rows.append(el('div', {class: 'nv-muted'},
          String(tr('Für dieses Profil sind keine Modelle gesetzt.'))));
      }
      preview.replaceChildren(el('b', {}, String(tr('Profilvorschau')) + ': ' + chosen), rows);
      preview.hidden = false;
    }}}, String(tr('Vorschau anzeigen')));
  var applyButton = el('button', {class: 'nv-btn nv-primary', type: 'button',
    'data-nv-action': 'profile-apply', on: {click: async function () {
      settingsError(error, '');
      try {
        var result = await api('/api/profiles', {action: 'use', profile: select.value});
        if (result && result.ok) {
          toast(nvBackend(result.message) || String(tr('Profil angewendet')));
          NV.render();
        } else settingsError(error, nvBackend(result && result.message) || String(tr('Aktion fehlgeschlagen')));
      } catch (failure) { nvActionError(error, failure); }
    }}}, String(tr('Profil anwenden')));

  return el('div', {class: 'nv-card', 'data-nv-advanced': 'profiles'},
    el('h3', {}, String(tr('Gespeicherte Profile'))), list,
    el('label', {}, String(tr('Profil auswählen'))), select,
    el('div', {class: 'nv-row'}, previewButton, applyButton), preview, error);
}

/* ---------- MCP: maskierte Server, Test, Schalter, Eintrag, Löschen ---------- */

async function buildMcpSection(token) {
  var data;
  try { data = await api('/api/mcp') || {}; } catch (error) { data = {}; }
  if (NV.stale(token)) return null;

  var servers = data.servers || [];
  var list = el('div', {class: 'nv-list'});
  servers.forEach(function (server) {
    if (server.error) {
      list.append(el('div', {class: 'nv-note'},
        nvText(server.scope) + ': ' + nvText(server.error)));
      return;
    }
    var result = el('div', {class: 'nv-note', 'data-nv-mcp-result': '', hidden: ''});
    var entryBox = el('div', {class: 'nv-note', hidden: ''});
    var toggleButton = el('button', {class: 'nv-btn', type: 'button',
      'data-nv-action': 'mcp-toggle', on: {click: async function () {
        try {
          var answer = await api('/api/mcp', {action: 'toggle', scope: server.scope, name: server.name});
          toast(nvBackend(answer && answer.message) || String(tr('Aktion fehlgeschlagen')));
          if (answer && answer.ok) NV.render();
        } catch (failure) { toast(String(tr('Aktion fehlgeschlagen: ')) + String(failure && failure.message || failure)); }
      }}}, String(tr('Server ein- oder ausschalten')));
    var testButton = el('button', {class: 'nv-btn', type: 'button',
      'data-nv-action': 'mcp-test', on: {click: async function () {
        result.hidden = false;
        result.removeAttribute('data-nv-ok');
        result.replaceChildren(el('span', {class: 'nv-muted'},
          String(tr('Verbindungstest läuft')) + ' …'));
        try {
          var answer = await api('/api/mcp', {action: 'test', scope: server.scope, name: server.name});
          var report = answer && answer.result;
          var ok = !!(report && report.ok);
          result.setAttribute('data-nv-ok', ok ? 'true' : 'false');
          var message = (report && (report.error || report.hint))
            || nvBackend(answer && answer.message) || String(tr('Test beendet'));
          result.replaceChildren(
            el('b', {class: ok ? 'nv-ok' : 'nv-bad'},
              ok ? String(tr('Test bestanden')) : String(tr('Test fehlgeschlagen'))),
            el('div', {}, nvText(message)));
        } catch (failure) {
          result.setAttribute('data-nv-ok', 'false');
          result.replaceChildren(
            el('b', {class: 'nv-bad'}, String(tr('Test fehlgeschlagen'))),
            el('div', {}, String(failure && failure.message || failure)));
        }
      }}}, String(tr('Verbindung testen')));
    var entryButton = el('button', {class: 'nv-btn', type: 'button',
      on: {click: async function () {
        entryBox.hidden = !entryBox.hidden;
        if (!entryBox.hidden && !entryBox.childNodes.length) {
          try {
            var loaded = await api('/api/mcp_entry?scope='
              + encodeURIComponent(server.scope) + '&name=' + encodeURIComponent(server.name));
            var entry = loaded.entry || {};
            // Auch der Eintrag kommt vom Server bereits maskiert (***) zurück.
            var target = entry.type === 'local'
              ? (entry.command || []).join(' ') : entry.url;
            entryBox.replaceChildren(
              el('div', {}, String(tr('Typ')) + ': ' + nvText(entry.type)),
              el('div', {}, String(tr('Ziel')) + ': ' + nvText(target)),
              el('div', {}, String(tr('Geltung')) + ': ' + nvText(server.scope)));
          } catch (failure) {
            entryBox.replaceChildren(el('div', {class: 'nv-bad'},
              String(failure && failure.message || failure)));
          }
        }
      }}}, String(tr('Eintrag anzeigen')));
    var deleteButton = el('button', {class: 'nv-btn', type: 'button',
      'data-nv-action': 'mcp-delete', on: {click: async function () {
        if (!window.confirm(String(tr('MCP-Server löschen?')) + ' ' + server.name)) return;
        try {
          var answer = await api('/api/mcp', {action: 'delete', scope: server.scope, name: server.name});
          toast(nvBackend(answer && answer.message) || String(tr('Aktion fehlgeschlagen')));
          if (answer && answer.ok) NV.render();
        } catch (failure) { toast(String(tr('Aktion fehlgeschlagen: ')) + String(failure && failure.message || failure)); }
      }}}, String(tr('Server löschen')));

    list.append(el('div', {class: 'nv-card', 'data-nv-mcp-server': nvText(server.name)},
      el('div', {class: 'nv-row'},
        el('b', {}, nvText(server.name)),
        el('span', {class: 'nv-muted'}, nvText(server.scope)),
        el('span', {class: 'nv-muted'}, nvText(server.type)),
        el('span', {class: 'nv-muted'}, nvText(server.target))),
      el('div', {class: 'nv-row'}, toggleButton, testButton, entryButton, deleteButton),
      result, entryBox));
  });

  var error = settingsErrorBox();
  return el('div', {class: 'nv-card', 'data-nv-advanced': 'mcp'},
    el('h3', {}, String(tr('MCP-Server'))),
    el('p', {class: 'nv-muted'}, String(tr('MCP-Hinweis'))),
    list, error);
}

/* ---------- Kosten: Übersicht, Detail und Preise ---------- */

async function buildCostsSection(token) {
  var overview;
  try { overview = await api('/api/costs') || {}; } catch (error) { overview = {}; }
  if (NV.stale(token)) return null;

  var detail = el('div', {class: 'nv-card', 'data-nv-cost-detail': '', hidden: ''});
  var error = settingsErrorBox();

  function drawDetail(name, data) {
    var nodes = [
      el('h4', {}, nvText(name)),
      el('p', {class: 'nv-muted'}, String(tr('Kosten je Arbeitspaket'))),
      el('div', {}, el('b', {}, String(tr('Gesamtkosten')) + ': '
        + nvCurrency(data.total && data.total.cost)))
    ];
    var packages = el('table', {class: 'nv-table'},
      el('tr', {}, el('th', {}, String(tr('Arbeitspaket'))),
        el('th', {}, String(tr('Sitzungen'))), el('th', {}, String(tr('Eingabetokens'))),
        el('th', {}, String(tr('Kosten')))));
    (data.packages || []).forEach(function (item) {
      packages.append(el('tr', {},
        el('td', {}, nvText(item.id || item.title)),
        el('td', {}, nvNumber(item.sessions)),
        el('td', {}, nvNumber(item.tokens && item.tokens.input)),
        el('td', {}, nvCurrency(item.cost))));
    });
    nodes.push(packages);

    var prices = el('div', {class: 'nv-note'},
      el('b', {}, String(tr('Preise je 1 Mio. Tokens'))));
    var inputs = [];
    (data.models || []).forEach(function (item) {
      var price = item.price || {};
      var model = nvText(item.model);
      var row = el('div', {class: 'nv-row'}, el('b', {}, model));
      [['input', String(tr('Eingabe'))],
       ['cached_input', 'cached'],
       ['output', String(tr('Ausgabe'))]].forEach(function (field) {
        var input = el('input', {type: 'number', min: '0', step: '0.0001',
          'data-nv-cost-model': model, 'data-nv-cost-field': field[0],
          value: String(price[field[0]] != null ? price[field[0]] : 0),
          'aria-label': field[1] + ' ' + model});
        inputs.push(input);
        row.append(el('label', {}, field[1] + ' ', input));
      });
      // Der Preis ist immer ein Zahlenblock; die Herkunft verrät, ob er
      // belegt oder nur geschätzt/unbekannt ist.
      row.append(el('span', {class: 'nv-muted'},
        String(tr('Quelle')) + ': ' + nvText(item.price_source || String(tr('unbekannt')))));
      prices.append(row);
    });
    var save = el('button', {class: 'nv-btn nv-primary', type: 'button',
      'data-nv-action': 'cost-save', on: {click: async function () {
        settingsError(error, '');
        var values = {};
        for (var index = 0; index < inputs.length; index++) {
          var input = inputs[index];
          var raw = String(input.value || '').trim().replace(',', '.');
          if (!raw) {
            settingsError(error, String(tr('Bitte alle Preise eintragen.')));
            input.focus();
            return;
          }
          var number = Number(raw);
          if (!isFinite(number) || number < 0) {
            settingsError(error, String(tr('Preis ist ungültig.')));
            input.focus();
            return;
          }
          var model = input.getAttribute('data-nv-cost-model');
          var field = input.getAttribute('data-nv-cost-field');
          values[model] = values[model] || {};
          values[model][field] = number;
        }
        try {
          var answer = await api('/api/costs', {name: name, action: 'prices', prices: values});
          if (answer && answer.ok) {
            toast(nvBackend(answer.message) || String(tr('Preise gespeichert')));
            openDetail(name);
          } else settingsError(error, nvBackend(answer && answer.message) || String(tr('Aktion fehlgeschlagen')));
        } catch (failure) { nvActionError(error, failure); }
      }}}, String(tr('Preise speichern')));
    prices.append(el('div', {class: 'nv-row'}, save));
    nodes.push(prices);
    detail.replaceChildren.apply(detail, nodes);
    detail.hidden = false;
  }

  function openDetail(name) {
    api('/api/costs?name=' + encodeURIComponent(name)).then(function (data) {
      if (!NV.stale(token)) drawDetail(name, data || {});
    }).catch(function (failure) { nvActionError(error, failure); });
  }

  var table = el('table', {class: 'nv-table'},
    el('tr', {}, el('th', {}, String(tr('Projekt'))),
      el('th', {}, String(tr('Sitzungen'))), el('th', {}, String(tr('Eingabetokens'))),
      el('th', {}, String(tr('Kosten')))));
  (overview.projects || []).forEach(function (item) {
    table.append(el('tr', {class: 'nv-cost-project', 'data-nv-cost-project': nvText(item.name),
      on: {click: function () { openDetail(item.name); }}},
      el('td', {}, el('b', {}, nvText(item.name))),
      el('td', {}, nvNumber(item.sessions)),
      el('td', {}, nvNumber(item.tokens && item.tokens.input)),
      el('td', {}, nvCurrency(item.cost))));
  });

  return el('div', {class: 'nv-card', 'data-nv-advanced': 'costs'},
    el('h3', {}, String(tr('Kostenübersicht'))), table, detail, error);
}

/* ---------- Harness: Status, Auswahl und Einrichtungsplan ---------- */

async function buildHarnessSection(token) {
  var status;
  try { status = await api('/api/harness') || {}; } catch (error) { status = {}; }
  if (NV.stale(token)) return null;

  var select = el('select', {'data-nv-field': 'harness',
    'aria-label': String(tr('Harness-Auswahl'))});
  (status.harnesses || []).forEach(function (item) {
    select.append(el('option', {value: nvText(item.harness)},
      nvText(item.name) + ' (' + nvText(item.harness) + ')'));
  });
  if (status.selected) select.value = status.selected;

  var statusBox = el('div', {class: 'nv-note', 'data-nv-harness-status': ''});
  function draw(data) {
    var nodes = [el('p', {}, String(tr('Aktiver Harness')) + ': ' + nvText(data.selected))];
    (data.harnesses || []).forEach(function (item) {
      nodes.push(el('div', {class: 'nv-row'},
        el('b', {}, nvText(item.name) + ' (' + nvText(item.harness) + ')'),
        el('span', {class: item.installed ? 'nv-ok' : 'nv-bad'},
          item.installed ? String(tr('Installiert')) : String(tr('Nicht installiert'))),
        item.version ? el('span', {class: 'nv-muted'},
          String(tr('Version')) + ' ' + nvText(item.version)) : null));
      if (item.hint) nodes.push(el('div', {class: 'nv-muted'}, nvText(item.hint)));
      if (item.official) nodes.push(el('div', {class: 'nv-muted'},
        String(tr('Offizielle Anleitung')) + ': ' + nvText(item.official)));
      if (item.install_command && item.install_command.length) {
        nodes.push(el('div', {class: 'nv-muted'},
          String(tr('Einrichtungsplan')) + ': ' + item.install_command.join(' ')));
      }
    });
    statusBox.replaceChildren.apply(statusBox, nodes);
  }
  draw(status);

  var error = settingsErrorBox();
  var useButton = el('button', {class: 'nv-btn nv-primary', type: 'button',
    'data-nv-action': 'harness-use', on: {click: async function () {
      settingsError(error, '');
      try {
        var answer = await api('/api/harness', {action: 'use', harness: select.value});
        if (answer && answer.ok) {
          toast(nvBackend(answer.message));
          var fresh = await api('/api/harness');
          if (!NV.stale(token)) { draw(fresh); select.value = fresh.selected; }
        } else settingsError(error, nvBackend(answer && answer.message) || String(tr('Aktion fehlgeschlagen')));
      } catch (failure) { nvActionError(error, failure); }
    }}}, String(tr('Harness übernehmen')));

  return el('div', {class: 'nv-card', 'data-nv-advanced': 'harness'},
    el('h3', {}, String(tr('Harness'))),
    el('label', {}, String(tr('Harness-Auswahl'))), select,
    el('div', {class: 'nv-row'}, useButton), statusBox, error);
}

/* ---------- Umgebung: Doctor, Pfade, Fritz, Emulator, Server ---------- */

async function buildEnvSection(token) {
  var doctor = [], paths = {}, fritz = {}, server = {};
  try {
    var answers = await Promise.all([
      api('/api/doctor'), api('/api/paths'), api('/api/fritz'), api('/api/server')
    ]);
    doctor = answers[0] || [];
    paths = (answers[1] && answers[1].paths) || {};
    fritz = answers[2] || {};
    server = answers[3] || {};
  } catch (error) { /* leere, aber bedienbare Ansicht */ }
  if (NV.stale(token)) return null;

  var card = el('div', {class: 'nv-card', 'data-nv-advanced': 'env'},
    el('h3', {}, String(tr('Umgebung'))));
  var error = settingsErrorBox();

  var doctorList = el('div', {class: 'nv-list'});
  doctor.forEach(function (check) {
    doctorList.append(el('div', {class: 'nv-row', 'data-nv-doctor-row': '',
      'data-nv-ok': check.ok ? 'true' : 'false'},
      el('span', {class: check.ok ? 'nv-ok' : 'nv-bad'},
        check.ok ? 'OK' : String(tr('FEHL'))),
      el('span', {}, nvBackend(check.label)),
      check.ok || !check.hint ? null : el('span', {class: 'nv-muted'},
        String(tr('Hinweis')) + ': ' + nvBackend(check.hint))));
  });
  card.append(el('h4', {}, String(tr('Prüfungen'))), doctorList);

  var pathList = el('div', {'data-nv-paths': ''});
  Object.keys(paths).forEach(function (key) {
    pathList.append(el('div', {class: 'nv-row'},
      el('code', {}, key), el('span', {}, nvText(paths[key]))));
  });
  card.append(el('h4', {}, String(tr('Aufgelöste Pfade'))), pathList);

  var fritzResult = el('div', {class: 'nv-note', 'data-nv-fritz-result': '', hidden: ''});
  var automationOn = el('button', {class: 'nv-btn', type: 'button',
    'data-nv-action': 'fritz-automation-on', on: {click: async function () {
      try {
        var answer = await api('/api/fritz', {action: 'on'});
        toast(nvBackend(answer && answer.message));
        if (answer && answer.ok) NV.render();
      } catch (failure) { nvActionError(error, failure); }
    }}}, String(tr('Automatik einschalten')));
  var automationOff = el('button', {class: 'nv-btn', type: 'button',
    'data-nv-action': 'fritz-automation-off', on: {click: async function () {
      try {
        var answer = await api('/api/fritz', {action: 'off'});
        toast(nvBackend(answer && answer.message));
        if (answer && answer.ok) NV.render();
      } catch (failure) { nvActionError(error, failure); }
    }}}, String(tr('Automatik ausschalten')));
  var reconnect = el('button', {class: 'nv-btn nv-primary', type: 'button',
    'data-nv-action': 'fritz-reconnect', on: {click: async function () {
      if (!window.confirm(String(tr('FRITZ!Box neu verbinden? Die Internetverbindung wird kurz getrennt.')))) return;
      fritzResult.hidden = false;
      fritzResult.replaceChildren(el('span', {class: 'nv-muted'},
        String(tr('Reconnect läuft')) + ' …'));
      try {
        var answer = await api('/api/fritz', {action: 'reconnect'});
        fritzResult.replaceChildren(
          el('b', {class: answer && answer.ok ? 'nv-ok' : 'nv-bad'},
            answer && answer.ok ? String(tr('Reconnect erfolgreich')) : String(tr('Reconnect fehlgeschlagen'))),
          el('pre', {}, nvText((answer && answer.result && answer.result.output)
            || (answer && answer.message) || '')));
      } catch (failure) {
        fritzResult.replaceChildren(el('div', {class: 'nv-bad'},
          String(failure && failure.message || failure)));
      }
    }}}, String(tr('Neue IP anfordern')));
  card.append(el('h4', {}, String(tr('Fritzbox'))),
    el('p', {class: 'nv-muted'}, String(tr('Automatik: '))
      + (fritz.automation ? String(tr('an')) : String(tr('aus')))),
    el('div', {class: 'nv-row'}, automationOn, automationOff, reconnect), fritzResult);

  var emuResult = el('div', {class: 'nv-note', 'data-nv-emu-result': '', hidden: ''});
  function emulator(action) {
    return async function () {
      try {
        var answer = await api('/api/emu', {action: action});
        emuResult.replaceChildren(el('div',
          {class: answer && answer.ok ? 'nv-ok' : 'nv-bad'},
          nvBackend(answer && answer.message) || String(tr('Aktion fehlgeschlagen'))));
        emuResult.hidden = false;
        if (answer && !answer.ok) settingsError(error, nvBackend(answer.message));
      } catch (failure) {
        emuResult.replaceChildren(el('div', {class: 'nv-bad'},
          String(failure && failure.message || failure)));
        emuResult.hidden = false;
      }
    };
  }
  card.append(el('h4', {}, String(tr('Emulator'))),
    el('div', {class: 'nv-row'},
      el('button', {class: 'nv-btn', type: 'button', 'data-nv-action': 'emu-start',
        on: {click: emulator('start')}}, String(tr('Emulator starten'))),
      el('button', {class: 'nv-btn', type: 'button', 'data-nv-action': 'emu-stop',
        on: {click: emulator('stop')}}, String(tr('Emulator stoppen')))),
    emuResult);

  var serverStatus = el('div', {class: 'nv-note', 'data-nv-server-status': ''});
  function drawServer(data) {
    serverStatus.replaceChildren(
      el('b', {}, data && data.up ? String(tr('Server läuft')) : String(tr('Server ist nicht erreichbar'))),
      el('span', {class: 'nv-muted'}, ' ' + nvText(data && data.url || '')));
  }
  drawServer(server);
  function serverAction(action) {
    return async function () {
      try {
        var answer = await api('/api/server', {action: action});
        toast(nvBackend(answer && answer.message));
        var fresh = await api('/api/server');
        if (!NV.stale(token)) drawServer(fresh);
      } catch (failure) { nvActionError(error, failure); }
    };
  }
  card.append(el('h4', {}, String(tr('opencode-Server'))), serverStatus,
    el('div', {class: 'nv-row'},
      el('button', {class: 'nv-btn', type: 'button', 'data-nv-action': 'server-start',
        on: {click: serverAction('start')}}, String(tr('Server starten'))),
      el('button', {class: 'nv-btn', type: 'button', 'data-nv-action': 'server-stop',
        on: {click: serverAction('stop')}}, String(tr('Server stoppen')))),
    error);
  return card;
}

/* ---------- Läufe: Registerliste und Prune ---------- */

async function buildRunsSection(token) {
  var data;
  try { data = await api('/api/runs') || {}; } catch (error) { data = {}; }
  if (NV.stale(token)) return null;

  var list = el('div', {class: 'nv-list'});
  var result = el('div', {class: 'nv-note', 'data-nv-runs-result': '', hidden: ''});
  var error = settingsErrorBox();
  function renderList(records) {
    list.replaceChildren();
    (records || []).forEach(function (record) {
      list.append(el('div', {class: 'nv-row', 'data-nv-run': nvText(record.id)},
        el('b', {}, nvText(record.id)),
        el('span', {class: 'nv-muted'}, String(tr('Zustand')) + ': ' + nvText(record.state)),
        el('span', {class: 'nv-muted'}, String(tr('Sitzung')) + ': ' + nvText(record.session)),
        el('span', {class: 'nv-muted'}, String(tr('Projekt')) + ': ' + nvText(record.project))));
    });
  }
  function renderResult(lines) {
    if (!lines || !lines.length) return;
    var box = el('div', {});
    lines.forEach(function (line) { box.append(el('div', {}, nvText(line))); });
    result.replaceChildren(el('b', {}, String(tr('Bereinigungsergebnis'))), box);
    result.hidden = false;
  }
  renderList(data.records || []);

  var prune = el('button', {class: 'nv-btn nv-primary', type: 'button',
    'data-nv-action': 'runs-prune', on: {click: async function () {
      settingsError(error, '');
      try {
        var answer = await api('/api/runs', {action: 'prune'});
        if (answer && answer.ok) {
          toast(nvBackend(answer.message) || String(tr('Register bereinigt')));
          // Ergebnis sofort aus der Antwort zeigen; die Liste aktualisiert
          // sich im Hintergrund (kein zusätzlicher Roundtrip vor der Anzeige).
          renderResult(answer.lines || []);
          api('/api/runs').then(function (fresh) {
            if (!NV.stale(token)) renderList(fresh.records || []);
          }).catch(function () { /* Liste bleibt beim letzten Stand */ });
        } else settingsError(error, nvBackend(answer && answer.message) || String(tr('Aktion fehlgeschlagen')));
      } catch (failure) { nvActionError(error, failure); }
    }}}, String(tr('Register bereinigen')));

  return el('div', {class: 'nv-card', 'data-nv-advanced': 'runs'},
    el('h3', {}, String(tr('Run-Register'))), list, prune, result, error);
}
