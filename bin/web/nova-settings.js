/* F34 WP4 — Einstellungen: lokale Navigation, globale AGENTS.md, Darstellung,
   Zugriff, Funktionen, Limits, Schranken, Modelle, Profile, MCP und Harness.
   Die Ansicht baut ihr Gerüst sofort und füllt die Bereiche nach ihren
   Datenabrufen. Lokale Aktionen zeichnen nur ihre eigene Karte neu und zeigen
   einen Toast; NV.render() wird dafür nicht aufgerufen. DOM nur mit el() und
   Textknoten, Zustände über [hidden]/[open], Hooks durchgehend data-nv-*. */
'use strict';

var NV_SETTINGS_SECTIONS = [
  ['global-agents', 'Globale AGENTS.md'],
  ['appearance', 'Darstellung'],
  ['access', 'Zugriffssicherheit'],
  ['features', 'Funktionen'],
  ['limits', 'Laufverhalten'],
  ['gates', 'Schranken'],
  ['models', 'Modelle'],
  ['profiles', 'Profile'],
  ['mcp', 'MCP-Server'],
  ['harness', 'Harness']
];

/* Akzent-Raster: id, sichtbare Farbe und deutscher Quellschlüssel. */
var NV_SETTINGS_ACCENTS = [
  {id: 'blue', color: '#2457c5', name: 'Blau'},
  {id: 'teal', color: '#0f766e', name: 'Türkis'},
  {id: 'cyan', color: '#0e7490', name: 'Cyan'},
  {id: 'green', color: '#15803d', name: 'Grün'},
  {id: 'lime', color: '#4d7c0f', name: 'Limette'},
  {id: 'yellow', color: '#854d0e', name: 'Gelb'},
  {id: 'amber', color: '#b45309', name: 'Bernstein'},
  {id: 'orange', color: '#c2410c', name: 'Orange'},
  {id: 'red', color: '#b4232c', name: 'Rot'},
  {id: 'pink', color: '#be185d', name: 'Pink'},
  {id: 'violet', color: '#6d28d9', name: 'Violett'},
  {id: 'indigo', color: '#4338ca', name: 'Indigo'}
];

/* Die Bereiche Kosten, Läufe, Umgebung, Prüfungen, Fritzbox, Emulator und
   opencode-Server sind aus den Einstellungen entfernt (F34 WP3/WP7). */
var NV_SETTINGS_FEATURE_GROUPS = [
  {title: 'Git & Code', ids: ['github', 'agentsfile', 'writeaccess']},
  {title: 'Modelle & Agenten-Extras', ids: ['models', 'profiles', 'mcp', 'harness']},
  {title: 'Laufverhalten', ids: ['limits', 'gates', 'sandbox', 'priority']}
];

var NV_SETTINGS_FEATURE_HELP = {
  github: 'GitHub verbinden und Projekte von dort auschecken.',
  agentsfile: 'Die AGENTS.md eines Projekts bearbeiten.',
  writeaccess: 'Schreibrechte für jedes Projekt festlegen.',
  models: 'Modellkatalog und Modellauswahl anzeigen.',
  profiles: 'Gespeicherte Profile ansehen und übernehmen.',
  mcp: 'Zusätzliche MCP-Werkzeuge verwalten.',
  harness: 'Harness-Status und Auswahl anzeigen.',
  limits: 'Grenzen für Agentenläufe festlegen.',
  gates: 'Qualitäts-Schranken global und je Projekt setzen.',
  sandbox: 'Sandbox-Optionen für Projekte anzeigen.',
  priority: 'Arbeitspakete nach Wichtigkeit sortieren.'
};

/* Deutsche Kurzerklärung je Schranke; fällt auf einen allgemeinen Text zurück. */
var NV_SETTINGS_GATE_HELP = {
  repair_rounds: 'Wie oft ein Arbeitspaket nach Fehlern wiederholt wird, bevor es als beendet gilt.',
  assist_rounds: 'Nach wie vielen nachfolgenden Schritten ein menschlicher Eingriff wiederholt wird.',
  retries: 'Wie oft eine fehlgeschlagene Aktion automatisch wiederholt wird.',
  packages: 'Grenze, wie viele Arbeitspakete pro Lauf anstehen; sobald ein Paket endet, wird das nächste gestartet.',
  override: 'Ob der Agent bei Schrankenabbruch fragen (ask) oder abbrechen (off) darf.'
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

function nvText(value) { return String(value == null ? '' : value); }
function nvBackend(value) { return String(bt(value)); }

/* ------------------------------------------------------------------------- */
/* Ansicht                                                                    */
/* ------------------------------------------------------------------------- */

NV.views.settings = async function settings(context, token) {
  var main = document.getElementById('nv-main');
  var sections = {};
  var links = {};

  function markSection(id) {
    Object.keys(links).forEach(function (key) {
      if (key === id) links[key].setAttribute('aria-current', 'true');
      else links[key].removeAttribute('aria-current');
    });
  }

  var nav = el('nav', {class: 'nv-settings-nav', 'data-nv-settings-nav': '',
    'aria-label': tr('Einstellungsbereiche'),
    style: 'flex: 0 0 12rem; max-width: 12rem; overflow-x: auto; flex-wrap: nowrap;'});
  var content = el('div', {class: 'nv-settings-content'});
  NV_SETTINGS_SECTIONS.forEach(function (entry) {
    var id = entry[0];
    var link = el('button', {class: 'nv-btn nv-ghost', type: 'button',
      'data-nv-ssection-link': id,
      on: {click: function () {
        markSection(id);
        if (sections[id] && sections[id].scrollIntoView) {
          sections[id].scrollIntoView({behavior: 'smooth', block: 'start'});
        }
      }}}, tr(entry[1]));
    links[id] = link;
    nav.append(link);
    var section = el('section', {class: 'nv-card', 'data-nv-ssection': id},
      el('h2', {}, tr(entry[1])));
    sections[id] = section;
    content.append(section);
  });
  markSection(NV_SETTINGS_SECTIONS[0][0]);

  main.replaceChildren(el('h2', {class: 'nv-page-title'}, tr('Einstellungen')),
    el('div', {class: 'nv-settings-layout'}, nav, content),
    el('p', {}, el('a', {class: 'nv-link', 'data-nv-classic-link': '', href: '/classic'},
      tr('Klassische Oberfläche öffnen'))));

  /* Reihenfolge der Füllung entspricht der Reihenfolge der Sektionen; die
     Grundkarten stehen bereits im DOM, damit die Navigation stabil bleibt. */
  await fillGlobalAgents(sections['global-agents'], token);
  if (NV.stale(token)) return;
  await fillAppearance(sections.appearance, token);
  if (NV.stale(token)) return;
  fillAccess(sections.access, token);
  fillFeatures(sections.features);
  if (NV.feature('limits')) await fillLimits(sections.limits, token);
  if (NV.stale(token)) return;
  if (NV.feature('gates')) await fillGates(sections.gates, token);
  if (NV.stale(token)) return;

  var agentsData = {};
  try { agentsData = await api('/api/agents') || {}; }
  catch (error) { agentsData = {}; }
  if (NV.stale(token)) return;
  if (NV.feature('models')) fillModels(sections.models, agentsData, token);
  if (NV.feature('profiles')) fillProfiles(sections.profiles, agentsData, token);
  if (NV.feature('mcp')) await fillMcp(sections.mcp, token);
  if (NV.stale(token)) return;
  await fillHarness(sections.harness, token);
  if (NV.stale(token)) return;

  NV.refreshBell();
};

/* ------------------------------------------------------------------------- */
/* 1. Globale AGENTS.md                                                       */
/* ------------------------------------------------------------------------- */

async function fillGlobalAgents(section, token) {
  var view;
  try { view = await api('/api/global_agents_file') || {}; }
  catch (error) { view = {exists: false, digest: '', text: ''}; }
  if (NV.stale(token)) return;

  var digest = String(view && view.digest || '');
  var hint = el('small', {class: 'nv-note', 'data-nv-global-agents-hint': ''},
    tr('Diese Regeln gelten für alle Projekte; projektbezogene AGENTS.md ergänzen sie.'));
  var error = settingsErrorBox();
  var editor = el('div', {'data-nv-global-agents-editor': ''});
  var createRow = el('div', {class: 'nv-row'});
  var details = el('details', {class: 'nv-card', 'data-nv-global-agents': '', open: ''},
    el('summary', {}, tr('Regeln für alle Projekte bearbeiten')), hint, editor, createRow, error);
  section.append(details);

  function showEditor(text) {
    var textarea = el('textarea', {'data-nv-global-agents': '', rows: '18'},
      nvText(text));
    var save = el('button', {class: 'nv-btn nv-primary', type: 'button',
      'data-nv-action': 'global-agents-save', on: {click: async function () {
        settingsError(error, '');
        try {
          var answer = await api('/api/global_agents_file', {action: 'save',
            text: String(textarea.value || ''), digest: digest});
          if (answer && answer.ok) {
            digest = String(answer.digest || digest);
            toast(nvBackend(answer.message) || tr('Globale AGENTS.md gespeichert'));
          } else settingsError(error, nvBackend(answer && answer.message)
            || tr('Aktion fehlgeschlagen'));
        } catch (failure) {
          settingsError(error, String(failure && failure.message || failure));
        }
      }}}, tr('Speichern'));
    editor.replaceChildren(textarea, el('div', {class: 'nv-row'}, save));
    createRow.hidden = true;
    editor.hidden = false;
  }

  if (view.exists) {
    showEditor(view.text || '');
  } else {
    editor.hidden = true;
    var create = el('button', {class: 'nv-btn nv-primary', type: 'button',
      'data-nv-action': 'global-agents-create', on: {click: async function () {
        settingsError(error, '');
        try {
          var answer = await api('/api/global_agents_file', {action: 'create'});
          if (answer && answer.ok === false) {
            settingsError(error, nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
            return;
          }
          var fresh = await api('/api/global_agents_file') || {};
          if (NV.stale(token)) return;
          digest = String(fresh.digest || '');
          showEditor(fresh.text || '');
          toast(nvBackend(answer && answer.message) || tr('Vorlage angelegt'));
        } catch (failure) {
          settingsError(error, String(failure && failure.message || failure));
        }
      }}}, tr('Vorlage anlegen'));
    createRow.append(el('p', {class: 'nv-muted'},
      tr('Die globale AGENTS.md fehlt noch. Mit der Vorlage legst du Regeln für alle Projekte an.')), create);
  }
}

/* ------------------------------------------------------------------------- */
/* 2. Darstellung: Akzent, Darstellung, Sprache, Währung                      */
/* ------------------------------------------------------------------------- */

async function fillAppearance(section, token) {
  var themeSelect = el('select', {'data-nv-theme-select': '', 'aria-label': tr('Darstellung')});
  [['light', 'Hell'], ['dark', 'Dunkel'], ['auto', 'System']].forEach(function (option) {
    themeSelect.append(el('option', {value: option[0]}, tr(option[1])));
  });
  themeSelect.value = NV.themePreference();
  themeSelect.addEventListener('change', function () { NV.setTheme(themeSelect.value); });
  section.append(el('label', {}, tr('Darstellung')), themeSelect);

  var accentGrid = el('div', {class: 'nv-grid', 'data-nv-accents': ''});
  var accentButtons = [];
  var active = NV.accent();
  NV_SETTINGS_ACCENTS.forEach(function (accent) {
    var swatch = el('span', {class: 'nv-swatch', 'aria-hidden': 'true',
      style: 'display:inline-block;width:1.4rem;height:1.4rem;border-radius:0.35rem;'
        + 'background-color:' + accent.color + ';'});
    var button = el('button', {class: 'nv-btn', type: 'button',
      'data-nv-accent': accent.id,
      'aria-pressed': String(accent.id === active),
      'aria-label': tr(accent.name),
      on: {click: function () {
        NV.setAccent(accent.id);
        accentButtons.forEach(function (other) {
          other.setAttribute('aria-pressed',
            String(other.getAttribute('data-nv-accent') === accent.id));
        });
      }}}, swatch, el('span', {}, tr(accent.name)));
    accentButtons.push(button);
    accentGrid.append(button);
  });
  section.append(el('h3', {}, tr('Akzent')), accentGrid);

  var engine = i18n();
  var langSelect = el('select', {'data-nv-language-select': '', 'aria-label': tr('Sprache')});
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
      var result = await api('/api/language', {language: next});
      if (!result.ok) throw new Error(errText(result, 400));
      engine.set(next);
      toast(bt(result.message) || tr('Sprache gespeichert'));
    } catch (error) {
      langSelect.value = previous;
      toast(tr('Sprache konnte nicht gespeichert werden: ')
        + String(error && error.message || error));
    } finally { langSelect.disabled = false; }
  });
  section.append(el('h3', {}, tr('Sprache')),
    el('p', {class: 'nv-muted'}, tr('ui.language.hint')), langSelect);

  var currency = {currency: 'EUR', usd_rate: 1.0};
  try { currency = await api('/api/ui_settings') || currency; }
  catch (error) { /* Anzeige bleibt mit Voreinstellung bedienbar */ }
  if (NV.stale(token)) return;

  var currencySelect = el('select', {'data-nv-currency': '', 'aria-label': tr('Währung')});
  [['EUR', 'EUR'], ['USD', 'USD']].forEach(function (option) {
    currencySelect.append(el('option', {value: option[0]}, option[1]));
  });
  currencySelect.value = currency.currency === 'USD' ? 'USD' : 'EUR';
  var rateInput = el('input', {type: 'number', min: '0.01', max: '100', step: '0.01',
    'data-nv-usd-rate': '', value: String(Number(currency.usd_rate) || 1),
    'aria-label': tr('USD je 1 EUR')});
  var rateRow = el('label', {}, tr('USD je 1 EUR'), rateInput);
  rateRow.hidden = currencySelect.value !== 'USD';
  currencySelect.addEventListener('change', function () {
    rateRow.hidden = currencySelect.value !== 'USD';
  });
  var error = settingsErrorBox();
  var save = el('button', {class: 'nv-btn nv-primary', type: 'button',
    'data-nv-action': 'ui-settings-save', on: {click: async function () {
      settingsError(error, '');
      var rate = Number(String(rateInput.value || '').replace(',', '.'));
      if (currencySelect.value === 'USD'
          && (!isFinite(rate) || rate < 0.01 || rate > 100)) {
        settingsError(error, tr('Bitte einen gültigen Umrechnungskurs eingeben.'));
        return;
      }
      try {
        var answer = await api('/api/ui_settings', {currency: currencySelect.value,
          usd_rate: currencySelect.value === 'USD' ? rate : 1.0});
        toast(nvBackend(answer && answer.message) || tr('Währung gespeichert'));
      } catch (failure) {
        settingsError(error, String(failure && failure.message || failure));
      }
    }}}, tr('Speichern'));
  section.append(el('h3', {}, tr('Währung')),
    el('p', {class: 'nv-muted'},
      tr('Preise bleiben in Euro je 1 Mio. Tokens gespeichert und werden nur für die Anzeige umgerechnet.')),
    currencySelect, rateRow, el('div', {class: 'nv-row'}, save), error);
}

/* ------------------------------------------------------------------------- */
/* 3. Zugriff (bestehend)                                                     */
/* ------------------------------------------------------------------------- */

function fillAccess(section, token) {
  var security = {port: '', bind: '', allowlist: [], password_set: false};
  api('/api/security').then(function (answer) {
    if (answer && !NV.stale(token)) {
      security = answer;
      portInput.placeholder = String(security.port || '');
      bindInput.placeholder = String(security.bind || '');
      allowInput.placeholder = (security.allowlist || []).join(', ');
    }
  }).catch(function () { /* Ansicht bleibt lesbar */ });

  var password = el('input', {type: 'password', 'data-nv-field': 'password',
    placeholder: tr('neues Passwort (mind. 8 Zeichen)'), 'aria-label': tr('Neues Passwort')});
  var repeat = el('input', {type: 'password', 'data-nv-field': 'password-repeat',
    placeholder: tr('Passwort wiederholen'), 'aria-label': tr('Passwort wiederholen')});
  var portInput = el('input', {inputmode: 'numeric', 'data-nv-field': 'port',
    'aria-label': tr('Port')});
  var bindInput = el('input', {'data-nv-field': 'bind', 'aria-label': tr('Bind-Adresse')});
  var allowInput = el('input', {'data-nv-field': 'allowlist', 'aria-label': tr('IP-Allowlist')});
  var error = settingsErrorBox();
  var network = el('details', {class: 'nv-access-network nv-card',
    'data-nv-network-advanced': ''},
    el('summary', {}, tr('Netzwerk (erweitert)')),
    el('p', {class: 'nv-note'}, tr('Netzwerk-Hinweis')),
    el('label', {}, tr('Port')), portInput,
    el('label', {}, tr('Bind-Adresse')), bindInput,
    el('label', {}, tr('IP-Allowlist')), allowInput,
    el('div', {class: 'nv-row'}, el('button', {class: 'nv-btn nv-secondary', type: 'button',
      'data-nv-action': 'security-save', on: {click: async function () {
        settingsError(error, '');
        var update = {action: 'save'};
        var rawPort = String(portInput.value || '').trim();
        if (rawPort) {
          if (!/^\d+$/.test(rawPort)) {
            settingsError(error, tr('Bitte eine gültige Portnummer eingeben.'));
            return;
          }
          update.port = Number(rawPort);
        }
        if (String(bindInput.value || '').trim()) update.bind = String(bindInput.value).trim();
        if (String(allowInput.value || '').trim()) {
          update.allowlist = String(allowInput.value).split(/[\s,]+/).filter(Boolean);
        }
        try {
          var answer = await api('/api/security', update);
          if (answer.ok) {
            portInput.value = ''; bindInput.value = ''; allowInput.value = '';
            toast(bt(answer.message) || tr('Zugriffssicherheit gespeichert'));
          } else settingsError(error, bt(answer.message));
        } catch (failure) {
          settingsError(error, String(failure && failure.message || failure));
        }
      }}}, tr('Speichern'))),
    el('p', {class: 'nv-note', 'data-nv-restart-note': ''},
      tr('Änderungen an Port, Bind-Adresse und Allowlist werden in ui.json gespeichert und wirken erst nach einem Neustart des Dashboards.')));

  section.append(el('div', {class: 'nv-access-signin'},
    el('h3', {}, tr('Anmeldung')),
    el('label', {}, tr('Neues Passwort')), password,
    el('label', {}, tr('Passwort wiederholen')), repeat,
    el('div', {class: 'nv-row'},
      el('button', {class: 'nv-btn nv-primary', type: 'button',
        'data-nv-action': 'password-set', on: {click: async function () {
          settingsError(error, '');
          if (String(password.value || '') !== String(repeat.value || '')) {
            settingsError(error, tr('Passwörter stimmen nicht überein'));
            return;
          }
          try {
            var answer = await api('/api/security', {action: 'password', password: password.value});
            if (answer.ok) {
              password.value = ''; repeat.value = '';
              toast(bt(answer.message) || tr('Kennwort gesetzt'));
            } else settingsError(error, bt(answer.message));
          } catch (failure) {
            settingsError(error, String(failure && failure.message || failure));
          }
        }}}, tr('Passwort setzen')),
      el('button', {class: 'nv-btn', type: 'button',
        'data-nv-action': 'password-clear', on: {click: async function () {
          try {
            var answer = await api('/api/security', {action: 'password', clear: true});
            toast(bt(answer.message) || tr('Kennwort entfernt'));
          } catch (failure) {
            settingsError(error, String(failure && failure.message || failure));
          }
        }}}, tr('Passwort entfernen')),
      el('button', {class: 'nv-btn', type: 'button',
        'data-nv-action': 'logout', on: {click: function () { NV.logout(); }}}, tr('Abmelden')))),
    network, error);
}

/* ------------------------------------------------------------------------- */
/* 4. Funktionsschalter                                                       */
/* ------------------------------------------------------------------------- */

function fillFeatures(section) {
  var groups = NV_SETTINGS_FEATURE_GROUPS.map(function (group) {
    var rows = group.ids.map(function (id) {
      var box = el('input', {type: 'checkbox', 'data-nv-feature': id, checked: NV.feature(id)});
      box.addEventListener('change', function () { NV.setFeature(id, box.checked); });
      return el('label', {class: 'nv-switch-row'}, box,
        el('span', {class: 'nv-feature-text'},
          el('strong', {}, tr(id)),
          el('small', {}, tr(NV_SETTINGS_FEATURE_HELP[id] || id))));
    });
    return el('div', {class: 'nv-feature-group'}, el('h3', {}, tr(group.title)), ...rows);
  });
  section.append(el('p', {class: 'nv-muted'},
    tr('Technische Bereiche sind standardmäßig ausgeblendet.')),
    el('div', {class: 'nv-feature-groups', 'data-nv-feature-groups': ''}, ...groups));
}

/* ------------------------------------------------------------------------- */
/* 5. Laufverhalten / Limits                                                  */
/* ------------------------------------------------------------------------- */

async function fillLimits(section, token) {
  var limits;
  try { limits = await api('/api/limits') || {mode: 'stop'}; }
  catch (error) { limits = {mode: 'stop'}; }
  if (NV.stale(token)) return;
  var mode = limits.mode === 'continue' ? 'continue' : 'stop';

  var box = el('div', {class: 'nv-grid', 'data-nv-advanced': 'limits'});
  var buttons = {};
  [
    {id: 'continue', title: 'Fortsetzen', effect: 'Neue Läufe setzen eine vorhandene Sitzung fort und arbeiten dort weiter.'},
    {id: 'stop', title: 'Stopp', effect: 'Neue Läufe werden gestoppt, statt eine bestehende Sitzung fortzusetzen.'}
  ].forEach(function (option) {
    var button = el('button', {class: 'nv-btn', type: 'button',
      'data-nv-action': 'limits-' + option.id,
      'aria-pressed': String(option.id === mode),
      on: {click: async function () {
        try {
          var answer = await api('/api/limits', {action: option.id});
          if (answer && answer.ok === false) {
            toast(nvBackend(answer.message) || tr('Speichern fehlgeschlagen'));
            return;
          }
          mode = option.id;
          Object.keys(buttons).forEach(function (key) {
            buttons[key].setAttribute('aria-pressed', String(key === mode));
            if (key === mode) buttons[key].classList.add('nv-primary');
            else buttons[key].classList.remove('nv-primary');
          });
          toast(nvBackend(answer && answer.message) || tr('Laufverhalten gespeichert'));
        } catch (failure) {
          toast(tr('Speichern fehlgeschlagen: ') + String(failure && failure.message || failure));
        }
      }}}, tr(option.title));
    buttons[option.id] = button;
    if (option.id === mode) button.classList.add('nv-primary');
    box.append(el('div', {class: 'nv-card'},
      el('h4', {}, tr(option.title)),
      el('p', {}, tr(option.effect)), button));
  });
  section.append(box,
    el('p', {class: 'nv-muted'},
      tr('Die Einstellung gilt für neue Läufe; eine bereits laufende Sitzung bleibt unberührt.')));
}

/* ------------------------------------------------------------------------- */
/* 6. Schranken / Gates                                                       */
/* ------------------------------------------------------------------------- */

async function fillGates(section, token) {
  var view;
  var projects = [];
  try {
    var answers = await Promise.all([api('/api/gates'), api('/api/projects')]);
    view = answers[0] || {gates: {}};
    projects = Array.isArray(answers[1]) ? answers[1].map(function (item) {
      return typeof item === 'string' ? item : (item.name || '');
    }).filter(Boolean) : [];
  } catch (error) { view = {gates: {}}; }
  if (NV.stale(token)) return;

  var projectSelect = el('select', {'data-nv-gates-project': '', 'aria-label': tr('Projekt')});
  projectSelect.append(el('option', {value: 'global'}, tr('Global')));
  projects.forEach(function (name) {
    projectSelect.append(el('option', {value: name}, name));
  });
  projectSelect.value = projects.length ? projects[0] : 'global';

  var tableHolder = el('div', {class: 'nv-table-wrap'});
  var error = settingsErrorBox();
  var current = view;
  var resetBtn = el('button', {class: 'nv-btn', type: 'button',
    'data-nv-action': 'gates-reset', title: tr('Gilt nur für ein ausgewähltes Projekt'),
    on: {click: function () {
      var cleared = {};
      Object.keys((current && current.gates) || {}).forEach(function (key) {
        cleared[key] = null;
      });
      if (Object.keys(cleared).length) send(cleared, 'Projektabweichungen zurückgesetzt');
    }}}, tr('Projektabweichungen zurücksetzen'));

  function syncResetButton() {
    resetBtn.disabled = projectSelect.value === 'global';
  }

  function gateHelp(key) {
    return tr(NV_SETTINGS_GATE_HELP[key]
      || 'Quota für diese Schranke begrenzen — Werte nur setzen, die das Ziel wirklich schützen.');
  }

  function draw(data) {
    current = data;
    var table = el('table', {class: 'nv-table', 'data-nv-gates-table': ''},
      el('tr', {}, el('th', {}, tr('Schranke')), el('th', {}, tr('Wirkung')),
        el('th', {}, tr('Wert')), el('th', {}, tr('Herkunft')),
        el('th', {}, tr('Projektwert'))));
    Object.keys(data.gates || {}).forEach(function (key) {
      var entry = data.gates[key] || {};
      var valueField;
      if (key === 'override') {
        valueField = el('select', {'data-nv-gate-value': '', 'aria-label': tr('Wert')});
        ['ask', 'off'].forEach(function (option) {
          valueField.append(el('option', {value: option},
            option === 'ask' ? tr('Fragen') : tr('Abbrechen')));
        });
        valueField.value = String(entry.value == null ? '' : entry.value);
      } else {
        valueField = el('input', {'data-nv-gate-value': '', type: 'text',
          value: nvText(entry.value), 'aria-label': tr('Wert')});
      }
      var cells = [
        el('td', {}, el('b', {}, key)),
        el('td', {}, el('small', {class: 'nv-muted', 'data-nv-gate-help': ''}, gateHelp(key))),
        el('td', {}, valueField),
        el('td', {}, el('span', {class: 'nv-badge', 'data-nv-gate-origin': ''},
          tr(nvText(entry.origin || 'Standard'))))
      ];
      var overrideField = el('input', {'data-nv-gate-override': '', type: 'text',
        value: nvText(entry.override), placeholder: tr('Globaler Wert'),
        'aria-label': tr('Projektwert')});
      var deviation = nvText(entry.override) !== ''
        && nvText(entry.override) !== nvText(entry.global);
      var overrideCell = el('td', {}, overrideField,
        deviation ? el('span', {class: 'nv-badge', 'data-nv-gate-override-badge': ''},
          tr('Weicht ab')) : null);
      cells.push(projectSelect.value === 'global'
        ? el('td', {}, el('span', {class: 'nv-muted'}, tr('—'))) : overrideCell);
      table.append(el('tr', {'data-nv-gate': key}, ...cells));
    });
    tableHolder.replaceChildren(table);
    syncResetButton();
  }
  draw(view);

  function valuesFromTable() {
    var values = {};
    tableHolder.querySelectorAll('[data-nv-gate]').forEach(function (row) {
      var key = row.getAttribute('data-nv-gate');
      var field = projectSelect.value === 'global'
        ? row.querySelector('[data-nv-gate-value]')
        : row.querySelector('[data-nv-gate-override]');
      if (!field) return;
      values[key] = String(field.value || '');
    });
    return values;
  }

  async function send(values, message) {
    settingsError(error, '');
    try {
      var answer = await api('/api/gates', {
        project: projectSelect.value === 'global' ? '' : projectSelect.value,
        values: values
      });
      if (answer && answer.ok === false) {
        settingsError(error, nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
        return;
      }
      draw(answer || view);
      toast(nvBackend(answer && answer.message) || tr(message));
    } catch (failure) {
      settingsError(error, String(failure && failure.message || failure));
    }
  }

  projectSelect.addEventListener('change', async function () {
    syncResetButton();
    try {
      var path = projectSelect.value === 'global'
        ? '/api/gates' : '/api/gates?name=' + encodeURIComponent(projectSelect.value);
      var fresh = await api(path) || {gates: {}};
      if (!NV.stale(token)) draw(fresh);
    } catch (failure) { settingsError(error, String(failure && failure.message || failure)); }
  });

  section.append(el('div', {class: 'nv-grid', 'data-nv-advanced': 'gates'},
    el('label', {}, tr('Projekt')), projectSelect, tableHolder,
    el('div', {class: 'nv-row'},
      el('button', {class: 'nv-btn nv-primary', type: 'button',
        'data-nv-action': 'gates-save', on: {click: function () {
          send(valuesFromTable(), 'Schranken gespeichert');
        }}}, tr('Speichern')),
      resetBtn),
    el('p', {class: 'nv-muted'},
      tr('Ohne Projektwert gilt der globale Wert oder die Voreinstellung; Änderungen wirken auf neue Läufe.')),
    error));
}

/* ------------------------------------------------------------------------- */
/* 7. Modelle und Modellkatalog                                               */
/* ------------------------------------------------------------------------- */

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

function nvAssert(label, node) {
  return el('div', {class: 'nv-muted'},
    el('b', {}, String(tr(label)) + ': '), nvMval(node),
    el('span', {class: 'nv-muted'}, ' — ' + nvMsrc(node)));
}

function fillModels(section, agentsData, token) {
  var holder = el('div', {class: 'nv-table-wrap'});

  function draw(data) {
    var info = data.info || {};
    var ids = (data.models || []).slice();
    Object.keys(info).forEach(function (id) { if (ids.indexOf(id) < 0) ids.push(id); });

    var table = el('table', {class: 'nv-table'},
      el('tr', {}, el('th', {}, tr('Modell')), el('th', {}, tr('Anbieter')),
        el('th', {}, tr('Preis')), el('th', {}, tr('Quelle')), el('th', {}, tr('Status'))));
    ids.forEach(function (id) {
      var model = info[id] || {};
      var facts = Object.keys(model.fakten || {}).map(function (key) {
        return nvAssert(key, model.fakten[key]);
      });
      var assessments = Object.keys(model.einschaetzungen || {}).map(function (key) {
        return nvAssert(key, model.einschaetzungen[key]);
      });
      var detail = el('tr', {'data-nv-model-detail': id, hidden: ''},
        el('td', {colspan: '5'},
          el('div', {}, el('b', {}, tr('Fakten')), ...facts,
            facts.length ? null : el('div', {class: 'nv-muted'}, tr('keine Angaben'))),
          el('div', {}, el('b', {}, tr('Einschätzungen')), ...assessments,
            assessments.length ? null : el('div', {class: 'nv-muted'}, tr('keine Angaben'))),
          el('div', {class: 'nv-muted'},
            String(tr('Preisquelle')) + ': '
            + nvText((model.preis || {}).quelle || tr('unbekannt')))));
      var row = el('tr', {'data-nv-model': id, class: 'nv-clickable',
        on: {click: function () { detail.hidden = !detail.hidden; }}},
        el('td', {}, el('b', {}, id)),
        el('td', {}, nvText(model.anbieter || tr('unbekannt'))),
        el('td', {}, nvText((model.preis || {}).text || tr('unbekannt'))),
        el('td', {}, nvText(((model.preis || {}).quelle) || tr('unbekannt'))),
        el('td', {}, nvText(model.status || (model.einschaetzungen || {}).status || tr('unbekannt'))));
      table.append(row, detail);
    });
    holder.replaceChildren(table);
  }
  draw(agentsData);

  var catalog = el('details', {class: 'nv-card', 'data-nv-model-catalog': ''},
    el('summary', {}, tr('Modellkatalog')),
    el('p', {class: 'nv-muted'},
      String(tr('Katalogstand')) + ': ' + nvText(agentsData.stand || tr('unbekannt'))),
    el('p', {class: 'nv-muted'}, nvBackend(agentsData.hinweis || '')),
    el('p', {class: 'nv-muted'},
      String(tr('Quellen')) + ': '
      + ((agentsData.katalog || {}).quellen || []).map(function (source) {
        return nvText(source.name) + (source.datum ? ' (' + source.datum + ')' : '');
      }).join('; ')),
    el('div', {class: 'nv-note'},
      el('b', {}, tr('Befunde')),
      el('div', {}, ((agentsData.katalog || {}).findings || []).map(function (finding) {
        return nvText(finding.text || finding);
      }).join(' · ') || tr('keine Angaben'))),
    el('div', {class: 'nv-row'},
      el('button', {class: 'nv-btn', type: 'button', 'data-nv-action': 'models-prices',
        on: {click: function () { NV.navigate('#/evaluations/costs'); }}}, tr('Preise bearbeiten')),
      el('button', {class: 'nv-btn', type: 'button', 'data-nv-action': 'models-refresh',
        on: {click: async function () {
          try {
            var fresh = await api('/api/agents') || {};
            if (NV.stale(token)) return;
            draw(fresh);
            agentsData = fresh;
            toast(tr('Modellkatalog neu geladen'));
          } catch (failure) {
            toast(tr('Aktion fehlgeschlagen: ') + String(failure && failure.message || failure));
          }
        }}}, tr('Katalog neu laden'))),
    el('p', {class: 'nv-muted', 'data-nv-models-hint': ''},
      tr('Der Katalog ist nur eine Referenz; Preise werden im Kosten-Dashboard gepflegt.')));

  section.append(el('details', {class: 'nv-card', 'data-nv-models': '', open: ''},
    el('summary', {}, tr('Modelle')), holder), catalog);
}

/* ------------------------------------------------------------------------- */
/* 8. Profile                                                                 */
/* ------------------------------------------------------------------------- */

async function fillProfiles(section, agentsData, token) {
  var profiles = agentsData.profiles || {};
  var modelIds = (agentsData.models || []).map(function (item) {
    return typeof item === 'string' ? item : (item.id || '');
  }).filter(Boolean);
  var names = Object.keys(profiles.profile || {});
  var roles = [];
  Object.keys(profiles.rollen || {}).forEach(function (role) {
    if (roles.indexOf(role) < 0) roles.push(role);
  });
  names.forEach(function (name) {
    Object.keys((profiles.profile || {})[name] || {}).forEach(function (role) {
      if (roles.indexOf(role) < 0) roles.push(role);
    });
  });
  roles.sort();

  var error = settingsErrorBox();
  var cards = [];
  var detailsBox = el('div', {class: 'nv-note', 'data-nv-profile-details': ''});
  names.forEach(function (name) {
    var profile = (profiles.profile || {})[name] || {};
    var roleFields = {};
    var combos = el('div', {class: 'nv-grid'});
    roles.forEach(function (role) {
      var combo = NV.combobox(modelIds, profile[role] || '', {
        placeholder: tr('Modell suchen …'), field: role,
        onchange: function (value) { roleFields[role] = value; }
      });
      combo.setAttribute('data-nv-profile-role', role);
      combos.append(el('label', {}, tr(role)), combo);
    });
    var card = el('article', {class: 'nv-card', 'data-nv-profile': name,
      on: {click: function () {
        cards.forEach(function (other) { other.removeAttribute('data-nv-profile-selected'); });
        card.setAttribute('data-nv-profile-selected', 'true');
        detailsBox.replaceChildren(el('b', {}, String(tr('Profil')) + ': ' + name),
          el('span', {}, Object.keys(profile).filter(function (role) {
            return !!profile[role];
          }).map(function (role) {
            return role + ': ' + profile[role];
          }).join(' · ') || tr('keine Angaben')));
      }}},
      el('div', {class: 'nv-row'}, el('h3', {}, name),
        name === profiles.aktiv ? el('span', {class: 'nv-badge'}, tr('Aktiv')) : null),
      combos,
      el('div', {class: 'nv-row'},
        el('button', {class: 'nv-btn', type: 'button', 'data-nv-action': 'profile-save',
          on: {click: async function () {
            settingsError(error, '');
            var all = {};
            cards.forEach(function (other) {
              var values = {};
              roles.forEach(function (role) {
                var field = other.querySelector('[data-nv-profile-role="' + role + '"]');
                values[role] = field ? String(field.getAttribute('data-nv-value') || '') : '';
              });
              all[other.getAttribute('data-nv-profile')] = values;
            });
            var assignment = {};
            roles.forEach(function (role) { assignment[role] = role; });
            try {
              var answer = await api('/api/profiles', {action: 'save',
                data: {rollen: Object.keys(profiles.rollen || {}).length
                  ? profiles.rollen : assignment, profile: all}});
              if (answer && answer.ok === false) {
                settingsError(error, nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
                return;
              }
              profiles.profile = all;
              profiles.rollen = Object.keys(profiles.rollen || {}).length
                ? profiles.rollen : assignment;
              toast(nvBackend(answer && answer.message) || tr('Profile gespeichert'));
            } catch (failure) {
              settingsError(error, String(failure && failure.message || failure));
            }
          }}}, tr('Speichern')),
        el('button', {class: 'nv-btn nv-primary', type: 'button',
          'data-nv-action': 'profile-apply', on: {click: function () {
            var preview = el('div', {class: 'nv-stack'},
              el('p', {}, String(tr('Profil anwenden')) + ': ' + name),
              el('p', {class: 'nv-muted'}, Object.keys(profile).map(function (role) {
                return role + ' → ' + String(profile[role] || tr('unbekannt'));
              }).join(' · ') || tr('keine Angaben')));
            NV.context.open({title: tr('Profilvorschau'), content: preview,
              footer: el('div', {class: 'nv-row'},
                el('button', {class: 'nv-btn nv-primary', type: 'button',
                  on: {click: async function () {
                    try {
                      var answer = await api('/api/profiles', {action: 'use', profile: name});
                      if (answer && answer.ok === false) {
                        settingsError(error, nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
                        return;
                      }
                      profiles.aktiv = name;
                      NV.context.close();
                      toast(nvBackend(answer && answer.message) || tr('Profil angewendet'));
                    } catch (failure) {
                      settingsError(error, String(failure && failure.message || failure));
                    }
                  }}}, tr('Bestätigen')),
                el('button', {class: 'nv-btn', type: 'button',
                  on: {click: function () { NV.context.close(); }}}, tr('Abbrechen')))});
          }}}, tr('Anwenden'))));
    cards.push(card);
    section.append(card);
  });
  if (!names.length) {
    section.append(el('p', {class: 'nv-muted'}, tr('Keine Profile vorhanden.')));
  }
  section.append(detailsBox, error);
  if (names.length) cards[0].click();
}

/* ------------------------------------------------------------------------- */
/* 9. MCP-Server                                                              */
/* ------------------------------------------------------------------------- */

async function fillMcp(section, token) {
  var data;
  try { data = await api('/api/mcp') || {}; }
  catch (error) { data = {}; }
  if (NV.stale(token)) return;
  var servers = Array.isArray(data.servers) ? data.servers : [];

  var list = el('div', {class: 'nv-stack'});
  var scopeFilter = el('select', {'data-nv-mcp-scope-filter': '', 'aria-label': tr('Geltungsbereich')});
  scopeFilter.append(el('option', {value: ''}, tr('Alle Bereiche')),
    el('option', {value: 'global'}, tr('Global')));
  (data.projects || []).forEach(function (project) {
    scopeFilter.append(el('option', {value: project}, project));
  });

  var searchWrap = NV.search({placeholder: tr('MCP-Server suchen …'), oninput: applyFilter});
  searchWrap.querySelector('[data-nv-search-input]').setAttribute('data-nv-mcp-search', '');
  section.append(el('div', {class: 'nv-filter-bar', 'data-nv-filter-bar': ''},
    searchWrap, scopeFilter));
  section.append(list);

  function applyFilter() {
    var term = String(searchWrap.querySelector('[data-nv-search-input]').value || '').toLowerCase();
    var scope = scopeFilter.value;
    list.querySelectorAll('[data-nv-mcp-server]').forEach(function (card) {
      var name = card.getAttribute('data-nv-mcp-server') || '';
      var cardScope = card.getAttribute('data-nv-mcp-scope') || '';
      card.hidden = name.toLowerCase().indexOf(term) < 0
        || (!!scope && scope !== cardScope);
    });
  }
  scopeFilter.addEventListener('change', applyFilter);

  servers.forEach(function (server) {
    if (server.error) {
      list.append(el('div', {class: 'nv-note'},
        nvText(server.scope) + ': ' + nvText(server.error)));
      return;
    }
    var name = nvText(server.name);
    var active = server.enabled !== false;
    var state = el('span', {class: active ? 'nv-badge' : 'nv-kind-badge',
      'data-nv-mcp-state': ''}, active ? tr('Aktiv') : tr('Inaktiv'));
    var toggle = el('button', {class: 'nv-btn', type: 'button',
      'data-nv-action': 'mcp-toggle',
      on: {click: async function () {
        try {
          var answer = await api('/api/mcp', {action: 'toggle',
            scope: server.scope, name: name});
          if (answer && answer.ok === false) {
            toast(nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
            return;
          }
          active = !active;
          state.textContent = active ? String(tr('Aktiv')) : String(tr('Inaktiv'));
          toggle.textContent = String(tr(active ? 'Deaktivieren' : 'Aktivieren'));
          toast(nvBackend(answer && answer.message) || tr('MCP-Server geändert'));
        } catch (failure) {
          toast(tr('Aktion fehlgeschlagen: ') + String(failure && failure.message || failure));
        }
      }}}, tr(active ? 'Deaktivieren' : 'Aktivieren'));

    var result = el('div', {class: 'nv-note', 'data-nv-mcp-result': '', hidden: ''});
    var testButton = el('button', {class: 'nv-btn', type: 'button',
      'data-nv-action': 'mcp-test', on: {click: async function () {
        result.hidden = false;
        result.replaceChildren(el('span', {class: 'nv-muted'},
          String(tr('Verbindungstest läuft')) + ' …'));
        try {
          var answer = await api('/api/mcp', {action: 'test', scope: server.scope, name: name});
          var report = answer && answer.result;
          var ok = !!(report && report.ok);
          result.replaceChildren(
            el('b', {class: ok ? 'nv-ok' : 'nv-bad'},
              ok ? tr('Test bestanden') : tr('Test fehlgeschlagen')),
            el('div', {}, nvText((report && (report.error || report.hint))
              || nvBackend(answer && answer.message) || tr('Test beendet'))));
        } catch (failure) {
          result.replaceChildren(el('b', {class: 'nv-bad'}, tr('Test fehlgeschlagen')),
            el('div', {}, String(failure && failure.message || failure)));
        }
      }}}, tr('Verbindung testen'));

    list.append(el('article', {class: 'nv-card', 'data-nv-mcp-server': name,
      'data-nv-mcp-scope': nvText(server.scope)},
      el('div', {class: 'nv-row'}, el('h3', {}, name),
        el('span', {class: 'nv-kind-badge'}, nvText(server.scope)), state,
        el('span', {class: 'nv-muted'}, nvText(server.target))),
      el('div', {class: 'nv-row'}, toggle, testButton,
        el('button', {class: 'nv-btn', type: 'button', 'data-nv-action': 'mcp-edit',
          on: {click: function () {
            var scopeSelect = el('select', {'data-nv-mcp-scope': '',
              'aria-label': tr('Geltungsbereich')});
            [['global', tr('Global')]].concat((data.projects || []).map(function (project) {
              return [project, project];
            })).forEach(function (option) {
              scopeSelect.append(el('option', {value: option[0]}, option[1]));
            });
            scopeSelect.value = server.scope;
            NV.context.open({title: tr('MCP-Server bearbeiten') + ': ' + name,
              content: el('div', {class: 'nv-stack'},
                el('p', {class: 'nv-muted'},
                  tr('Der Eintrag wird maskiert angezeigt; Geheimnisse bleiben verborgen.')),
                el('label', {}, tr('Geltungsbereich')), scopeSelect),
              footer: el('div', {class: 'nv-row'},
                el('button', {class: 'nv-btn nv-primary', type: 'button',
                  on: {click: async function () {
                    try {
                      var answer = await api('/api/mcp', {action: 'set',
                        scope: scopeSelect.value, name: name});
                      if (answer && answer.ok === false) {
                        toast(nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
                        return;
                      }
                      NV.context.close();
                      toast(nvBackend(answer && answer.message) || tr('MCP-Server gespeichert'));
                    } catch (failure) {
                      toast(tr('Aktion fehlgeschlagen: ') + String(failure && failure.message || failure));
                    }
                  }}}, tr('Speichern')),
                el('button', {class: 'nv-btn', type: 'button',
                  on: {click: function () { NV.context.close(); }}}, tr('Abbrechen')))});
          }}}, tr('Bearbeiten')),
        el('button', {class: 'nv-btn', type: 'button', 'data-nv-action': 'mcp-delete',
          on: {click: async function () {
            if (!window.confirm(String(tr('MCP-Server löschen?')) + ' ' + name)) return;
            try {
              var answer = await api('/api/mcp', {action: 'delete', scope: server.scope, name: name});
              if (answer && answer.ok === false) {
                toast(nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
                return;
              }
              toast(nvBackend(answer && answer.message) || tr('MCP-Server gelöscht'));
            } catch (failure) {
              toast(tr('Aktion fehlgeschlagen: ') + String(failure && failure.message || failure));
            }
          }}}, tr('Löschen'))),
      result));
  });

  if (!servers.length) {
    list.append(el('p', {class: 'nv-muted'}, tr('Keine MCP-Server konfiguriert.')));
  }
}

/* ------------------------------------------------------------------------- */
/* 10. Harness (bestehend, jetzt als Raster)                                  */
/* ------------------------------------------------------------------------- */

async function fillHarness(section, token) {
  var status;
  try { status = await api('/api/harness') || {}; }
  catch (error) { status = {}; }
  if (NV.stale(token)) return;

  var select = el('select', {'data-nv-field': 'harness', 'aria-label': tr('Harness-Auswahl')});
  var error = settingsErrorBox();
  var statusBox = el('div', {class: 'nv-grid', 'data-nv-harness-status': ''});
  var installFeedback = el('div', {class: 'nv-note',
    'data-nv-harness-install-feedback': '', hidden: ''});

  function syncSelect(data) {
    var options = (data.harnesses || []).map(function (item) {
      var option = el('option', {value: nvText(item.harness)},
        nvText(item.name) + ' (' + nvText(item.harness) + ')'
        + (item.installed ? '' : String(tr(' (nicht installiert)'))));
      if (!item.installed) option.setAttribute('disabled', '');
      return option;
    });
    select.replaceChildren.apply(select, options);
    select.value = data.selected || select.value;
  }

  function installButton(id) {
    return el('button', {class: 'nv-btn nv-secondary', type: 'button',
      'data-nv-action': 'harness-install', 'data-nv-harness': nvText(id),
      on: {click: async function () {
        settingsError(error, '');
        try {
          var answer = await api('/api/harness', {action: 'install', harness: id});
          installFeedback.replaceChildren(el('span', {},
            nvBackend(answer && answer.message) || tr('Installation fehlgeschlagen')));
          installFeedback.hidden = false;
          if (answer && answer.ok && !NV.stale(token)) {
            draw(await api('/api/harness'));
          }
        } catch (failure) {
          installFeedback.replaceChildren(el('span', {},
            String(failure && failure.message || failure)));
          installFeedback.hidden = false;
        }
      }}}, tr('Installieren'));
  }

  function draw(data) {
    syncSelect(data);
    var nodes = [el('p', {}, String(tr('Aktiver Harness')) + ': ' + nvText(data.selected))];
    (data.harnesses || []).forEach(function (item) {
      var row = el('div', {class: 'nv-card'},
        el('h4', {}, nvText(item.name) + ' (' + nvText(item.harness) + ')'),
        el('span', {class: item.installed ? 'nv-ok' : 'nv-bad'},
          item.installed ? tr('Installiert') : tr('Nicht installiert')),
        item.installed ? null : installButton(item.harness),
        item.version ? el('span', {class: 'nv-muted'},
          String(tr('Version')) + ' ' + nvText(item.version)) : null,
        item.hint ? el('div', {class: 'nv-muted'}, nvText(item.hint)) : null,
        item.official ? el('div', {class: 'nv-muted'},
          String(tr('Offizielle Anleitung')) + ': ' + nvText(item.official)) : null,
        item.install_command && item.install_command.length
          ? el('div', {class: 'nv-muted'},
            String(tr('Einrichtungsplan')) + ': ' + item.install_command.join(' '))
          : null);
      nodes.push(row);
    });
    statusBox.replaceChildren.apply(statusBox, nodes);
  }
  draw(status);

  section.append(el('label', {}, tr('Harness-Auswahl')), select,
    el('div', {class: 'nv-row'}, el('button', {class: 'nv-btn nv-primary', type: 'button',
      'data-nv-action': 'harness-use', on: {click: async function () {
        settingsError(error, '');
        try {
          var answer = await api('/api/harness', {action: 'use', harness: select.value});
          if (answer && answer.ok) {
            toast(nvBackend(answer.message));
            draw(await api('/api/harness'));
          } else {
            settingsError(error, nvBackend(answer && answer.message)
              || tr('Aktion fehlgeschlagen'));
            draw(await api('/api/harness'));
          }
        } catch (failure) {
          settingsError(error, String(failure && failure.message || failure));
        }
      }}}, tr('Harness übernehmen'))),
    statusBox, error, installFeedback);
}

/* ------------------------------------------------------------------------- */
/* Übersetzungen: Schlüssel sind die deutschen Quelltexte.                    */
/* ------------------------------------------------------------------------- */

VIBE_I18N.extend({
  en: {
    'Einstellungsbereiche': 'Settings sections',
    'Globale AGENTS.md': 'Global AGENTS.md',
    'Darstellung': 'Appearance',
    'Zugriffssicherheit': 'Access security',
    'Funktionen': 'Features',
    'Laufverhalten': 'Run behaviour',
    'Schranken': 'Guards',
    'Modelle': 'Models',
    'Profile': 'Profiles',
    'MCP-Server': 'MCP servers',
    'Regeln für alle Projekte bearbeiten': 'Edit rules for all projects',
    'Die globale AGENTS.md fehlt noch. Mit der Vorlage legst du Regeln für alle Projekte an.':
      'The global AGENTS.md is missing. Use the template to create rules for all projects.',
    'Vorlage angelegt': 'Template created',
    'Globale AGENTS.md gespeichert': 'Global AGENTS.md saved',
    'Akzent': 'Accent',
    'Blau': 'Blue', 'Türkis': 'Teal', 'Cyan': 'Cyan', 'Grün': 'Green',
    'Limette': 'Lime', 'Gelb': 'Yellow', 'Bernstein': 'Amber',
    'Orange': 'Orange', 'Rot': 'Red', 'Pink': 'Pink',
    'Violett': 'Violet', 'Indigo': 'Indigo',
    'Währung': 'Currency',
    'USD je 1 EUR': 'USD per 1 EUR',
    'Bitte einen gültigen Umrechnungskurs eingeben.': 'Please enter a valid exchange rate.',
    'Währung gespeichert': 'Currency saved',
    'Preise bleiben in Euro je 1 Mio. Tokens gespeichert und werden nur für die Anzeige umgerechnet.':
      'Prices stay stored in euros per 1 million tokens and are converted for display only.',
    'Fortsetzen': 'Continue',
    'Stopp': 'Stop',
    'Neue Läufe setzen eine vorhandene Sitzung fort und arbeiten dort weiter.':
      'New runs continue an existing session and carry on there.',
    'Neue Läufe werden gestoppt, statt eine bestehende Sitzung fortzusetzen.':
      'New runs are stopped instead of continuing an existing session.',
    'Die Einstellung gilt für neue Läufe; eine bereits laufende Sitzung bleibt unberührt.':
      'The setting applies to new runs; a running session is not affected.',
    'Laufverhalten gespeichert': 'Run behaviour saved',
    'Wirkung': 'Effect',
    'Wert': 'Value',
    'Herkunft': 'Origin',
    'Projektwert': 'Project value',
    'Globaler Wert': 'Global value',
    'Weicht ab': 'Differs',
    'Fragen': 'Ask',
    'Abbrechen': 'Cancel',
    'Schranken gespeichert': 'Guards saved',
    'Projektabweichungen zurückgesetzt': 'Project overrides reset',
    'Ohne Projektwert gilt der globale Wert oder die Voreinstellung; Änderungen wirken auf neue Läufe.':
      'Without a project value the global value or default applies; changes affect new runs.',
    'Globale': 'Global',
    'Quelle': 'Source',
    'Status': 'Status',
    'Anbieter': 'Provider',
    'Fakten': 'Facts',
    'Einschätzungen': 'Assessments',
    'Preisquelle': 'Price source',
    'Modellkatalog': 'Model catalogue',
    'Katalogstand': 'Catalogue date',
    'Befunde': 'Findings',
    'Quellen': 'Sources',
    'Preise bearbeiten': 'Edit prices',
    'Katalog neu laden': 'Reload catalogue',
    'Modellkatalog neu geladen': 'Model catalogue reloaded',
    'Der Katalog ist nur eine Referenz; Preise werden im Kosten-Dashboard gepflegt.':
      'The catalogue is reference only; prices are managed in the costs dashboard.',
    'Aktiv': 'Active',
    'Aktivieren': 'Activate',
    'Deaktivieren': 'Deactivate',
    'Anwenden': 'Apply',
    'Profil anwenden': 'Apply profile',
    'Profilvorschau': 'Profile preview',
    'Bestätigen': 'Confirm',
    'Profile gespeichert': 'Profiles saved',
    'Profil angewendet': 'Profile applied',
    'Keine Profile vorhanden.': 'No profiles available.',
    'MCP-Server suchen …': 'Search MCP servers …',
    'Alle Bereiche': 'All scopes',
    'Geltungsbereich': 'Scope',
    'Inaktiv': 'Inactive',
    'MCP-Server bearbeiten': 'Edit MCP server',
    'Der Eintrag wird maskiert angezeigt; Geheimnisse bleiben verborgen.':
      'The entry is shown masked; secrets stay hidden.',
    'Bearbeiten': 'Edit',
    'Löschen': 'Delete',
    'Verbindung testen': 'Test connection',
    'Verbindungstest läuft': 'Connection test running',
    'Test bestanden': 'Test passed',
    'Test fehlgeschlagen': 'Test failed',
    'Test beendet': 'Test finished',
    'MCP-Server geändert': 'MCP server changed',
    'MCP-Server gespeichert': 'MCP server saved',
    'MCP-Server gelöscht': 'MCP server deleted',
    'Keine MCP-Server konfiguriert.': 'No MCP servers configured.',
    'MCP-Server löschen?': 'Delete MCP server?',
    'unbekannt': 'unknown',
    'keine Angaben': 'no data'
  },
  de: {
    'Einstellungsbereiche': 'Einstellungsbereiche',
    'Globale AGENTS.md': 'Globale AGENTS.md',
    'Darstellung': 'Darstellung',
    'Zugriffssicherheit': 'Zugriffssicherheit',
    'Funktionen': 'Funktionen',
    'Laufverhalten': 'Laufverhalten',
    'Schranken': 'Schranken',
    'Modelle': 'Modelle',
    'Profile': 'Profile',
    'MCP-Server': 'MCP-Server',
    'Regeln für alle Projekte bearbeiten': 'Regeln für alle Projekte bearbeiten',
    'Die globale AGENTS.md fehlt noch. Mit der Vorlage legst du Regeln für alle Projekte an.':
      'Die globale AGENTS.md fehlt noch. Mit der Vorlage legst du Regeln für alle Projekte an.',
    'Vorlage angelegt': 'Vorlage angelegt',
    'Globale AGENTS.md gespeichert': 'Globale AGENTS.md gespeichert',
    'Akzent': 'Akzent',
    'Blau': 'Blau', 'Türkis': 'Türkis', 'Cyan': 'Cyan', 'Grün': 'Grün',
    'Limette': 'Limette', 'Gelb': 'Gelb', 'Bernstein': 'Bernstein',
    'Orange': 'Orange', 'Rot': 'Rot', 'Pink': 'Pink',
    'Violett': 'Violett', 'Indigo': 'Indigo',
    'Währung': 'Währung',
    'USD je 1 EUR': 'USD je 1 EUR',
    'Bitte einen gültigen Umrechnungskurs eingeben.': 'Bitte einen gültigen Umrechnungskurs eingeben.',
    'Währung gespeichert': 'Währung gespeichert',
    'Preise bleiben in Euro je 1 Mio. Tokens gespeichert und werden nur für die Anzeige umgerechnet.':
      'Preise bleiben in Euro je 1 Mio. Tokens gespeichert und werden nur für die Anzeige umgerechnet.',
    'Fortsetzen': 'Fortsetzen',
    'Stopp': 'Stopp',
    'Neue Läufe setzen eine vorhandene Sitzung fort und arbeiten dort weiter.':
      'Neue Läufe setzen eine vorhandene Sitzung fort und arbeiten dort weiter.',
    'Neue Läufe werden gestoppt, statt eine bestehende Sitzung fortzusetzen.':
      'Neue Läufe werden gestoppt, statt eine bestehende Sitzung fortzusetzen.',
    'Die Einstellung gilt für neue Läufe; eine bereits laufende Sitzung bleibt unberührt.':
      'Die Einstellung gilt für neue Läufe; eine bereits laufende Sitzung bleibt unberührt.',
    'Laufverhalten gespeichert': 'Laufverhalten gespeichert',
    'Wirkung': 'Wirkung',
    'Wert': 'Wert',
    'Herkunft': 'Herkunft',
    'Projektwert': 'Projektwert',
    'Globaler Wert': 'Globaler Wert',
    'Weicht ab': 'Weicht ab',
    'Fragen': 'Fragen',
    'Abbrechen': 'Abbrechen',
    'Schranken gespeichert': 'Schranken gespeichert',
    'Projektabweichungen zurückgesetzt': 'Projektabweichungen zurückgesetzt',
    'Ohne Projektwert gilt der globale Wert oder die Voreinstellung; Änderungen wirken auf neue Läufe.':
      'Ohne Projektwert gilt der globale Wert oder die Voreinstellung; Änderungen wirken auf neue Läufe.',
    'Globale': 'Globale',
    'Quelle': 'Quelle',
    'Status': 'Status',
    'Anbieter': 'Anbieter',
    'Fakten': 'Fakten',
    'Einschätzungen': 'Einschätzungen',
    'Preisquelle': 'Preisquelle',
    'Modellkatalog': 'Modellkatalog',
    'Katalogstand': 'Katalogstand',
    'Befunde': 'Befunde',
    'Quellen': 'Quellen',
    'Preise bearbeiten': 'Preise bearbeiten',
    'Katalog neu laden': 'Katalog neu laden',
    'Modellkatalog neu geladen': 'Modellkatalog neu geladen',
    'Der Katalog ist nur eine Referenz; Preise werden im Kosten-Dashboard gepflegt.':
      'Der Katalog ist nur eine Referenz; Preise werden im Kosten-Dashboard gepflegt.',
    'Aktiv': 'Aktiv',
    'Aktivieren': 'Aktivieren',
    'Deaktivieren': 'Deaktivieren',
    'Anwenden': 'Anwenden',
    'Profil anwenden': 'Profil anwenden',
    'Profilvorschau': 'Profilvorschau',
    'Bestätigen': 'Bestätigen',
    'Profile gespeichert': 'Profile gespeichert',
    'Profil angewendet': 'Profil angewendet',
    'Keine Profile vorhanden.': 'Keine Profile vorhanden.',
    'MCP-Server suchen …': 'MCP-Server suchen …',
    'Alle Bereiche': 'Alle Bereiche',
    'Geltungsbereich': 'Geltungsbereich',
    'Inaktiv': 'Inaktiv',
    'MCP-Server bearbeiten': 'MCP-Server bearbeiten',
    'Der Eintrag wird maskiert angezeigt; Geheimnisse bleiben verborgen.':
      'Der Eintrag wird maskiert angezeigt; Geheimnisse bleiben verborgen.',
    'Bearbeiten': 'Bearbeiten',
    'Löschen': 'Löschen',
    'Verbindung testen': 'Verbindung testen',
    'Verbindungstest läuft': 'Verbindungstest läuft',
    'Test bestanden': 'Test bestanden',
    'Test fehlgeschlagen': 'Test fehlgeschlagen',
    'Test beendet': 'Test beendet',
    'MCP-Server geändert': 'MCP-Server geändert',
    'MCP-Server gespeichert': 'MCP-Server gespeichert',
    'MCP-Server gelöscht': 'MCP-Server gelöscht',
    'Keine MCP-Server konfiguriert.': 'Keine MCP-Server konfiguriert.',
    'MCP-Server löschen?': 'MCP-Server löschen?',
    'unbekannt': 'unbekannt',
    'keine Angaben': 'keine Angaben'
  }
});
