/* GH-57 — Einstellungen: responsive Navigation, Bearbeitungsansicht und die
   zehn Sektionen des Vertrags docs/features/GH-57.md. DOM nur über el() und
   Textknoten, Zustände über [hidden]/[open], Hooks durchgehend data-nv-*.
   Lokale Aktionen zeichnen nur ihre eigene Sektion neu; NV.render() wird
   dafür nicht aufgerufen. */
'use strict';

var NV_SETTINGS_SECTIONS = [
  ['global-agents', 'Globale AGENTS.md', 'Regeln für alle Projekte und die Projektdateien verwalten.'],
  ['appearance', 'Darstellung', 'Farben, Sprache und Anzeige der Preise.'],
  ['access', 'Zugriffssicherheit', 'Anmeldung und Netzwerk des Dashboards.'],
  ['features', 'Funktionen', 'Technische Bereiche ein- oder ausblenden.'],
  ['limits', 'Laufverhalten', 'Wie neue Agentenläufe mit bestehenden Sitzungen umgehen.'],
  ['gates', 'Schranken', 'Qualitäts-Schranken global und je Projekt setzen.'],
  ['models', 'Modelle', 'Modelle des aktiven Harness und ihre Details.'],
  ['profiles', 'Profile', 'Modellzuordnungen je Rolle verwalten und anwenden.'],
  ['mcp', 'MCP-Server', 'Zusätzliche Werkzeuge für Agenten einrichten.'],
  ['harness', 'Harness', 'Installationsstatus und Auswahl des Agenten-Harness.']
];

/* Diese Sektionen gehören zu schaltbaren Funktionen. */
var NV_SETTINGS_FEATURED = {
  limits: true, gates: true, models: true, profiles: true, mcp: true, harness: true
};

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
  limits: 'Fortsetzen oder Stopp für neue Läufe festlegen.',
  gates: 'Qualitäts-Schranken global und je Projekt setzen.',
  sandbox: 'Sandbox-Optionen für Projekte anzeigen.',
  priority: 'Arbeitspakete nach Wichtigkeit sortieren.'
};

var NV_SETTINGS_GATE_HELP = {
  repair_rounds: 'Wie oft ein Arbeitspaket nach Fehlern wiederholt wird, bevor es als beendet gilt.',
  assist_rounds: 'Nach wie vielen nachfolgenden Schritten ein menschlicher Eingriff wiederholt wird.',
  retries: 'Wie oft eine fehlgeschlagene Aktion automatisch wiederholt wird.',
  packages: 'Grenze, wie viele Arbeitspakete pro Lauf anstehen.',
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
function nvField(label, control) {
  return el('label', {class: 'nv-field'}, el('span', {}, label), control);
}
function nvActions() { return el('div', {class: 'nv-form-actions'}); }
function nvFoot() {
  var foot = nvActions();
  Array.prototype.slice.call(arguments).forEach(function (child) {
    if (child) foot.append(child);
  });
  return foot;
}

/* Der Controller der jeweils aktiven Einstellungsansicht wird global
   vorgehalten, damit die Listener nur einmal registriert werden. */
window.addEventListener('nv:featureschange', function () {
  if (NV.settingsController) NV.settingsController.syncFeatures();
});
window.addEventListener('scroll', function () {
  if (NV.settingsController) NV.settingsController.syncScroll();
}, {passive: true});

/* Programmatische Sektionssprünge (Nav-Knopf, Anker) markieren ihr Ziel.
   Nachträglich nachladende Sektionen dürfen diese Markierung nicht
   überschreiben; erst eine echte Scroll-Bewegung hebt sie wieder auf. */
var nvNativeScrollIntoView = Element.prototype.scrollIntoView;
if (!nvNativeScrollIntoView.__nvSettingsMarker) {
  Element.prototype.scrollIntoView = function () {
    var result = nvNativeScrollIntoView.apply(this, arguments);
    if (NV.settingsController && this && this.getAttribute
        && this.hasAttribute('data-nv-ssection')) {
      NV.settingsController.pin(this.getAttribute('data-nv-ssection'));
    }
    return result;
  };
  Element.prototype.scrollIntoView.__nvSettingsMarker = true;
}

/* ------------------------------------------------------------------------- */
/* Ansicht                                                                    */
/* ------------------------------------------------------------------------- */

NV.views.settings = async function settings(context, token) {
  var main = document.getElementById('nv-main');
  var sections = {};
  var links = {};
  var loaded = {};
  var nav = el('nav', {class: 'nv-settings-nav', 'data-nv-settings-nav': '',
    'aria-label': tr('Einstellungsbereiche')});
  var content = el('div', {class: 'nv-settings-content'});

  function markSection(id) {
    Object.keys(links).forEach(function (key) {
      if (key === id) links[key].setAttribute('aria-current', 'true');
      else links[key].removeAttribute('aria-current');
    });
  }

  var pinned = null;
  var pinnedScrollY = 0;
  function pin(id) {
    pinned = id;
    pinnedScrollY = window.scrollY;
    markSection(id);
  }

  NV_SETTINGS_SECTIONS.forEach(function (entry) {
    var id = entry[0];
    var link = el('button', {class: 'nv-btn nv-ghost', type: 'button',
      'data-nv-ssection-link': id,
      on: {click: function () {
        if (document.contains(sections[id])) {
          sections[id].scrollIntoView({block: 'start'});
        } else {
          pin(id);
        }
      }}}, tr(entry[1]));
    links[id] = link;
    nav.append(link);
    var section = el('section', {class: 'nv-card', 'data-nv-ssection': id},
      el('h2', {}, tr(entry[1])),
      el('p', {class: 'nv-muted'}, tr(entry[2])));
    sections[id] = section;
    content.append(section);
  });
  markSection(NV_SETTINGS_SECTIONS[0][0]);

  main.replaceChildren(el('h2', {class: 'nv-page-title'}, tr('Einstellungen')),
    el('div', {class: 'nv-settings-layout', 'data-nv-settings-layout': ''},
      nav, content),
    el('p', {}, el('a', {class: 'nv-link', 'data-nv-classic-link': '',
      href: '/classic'}, tr('Klassische Oberfläche öffnen'))));

  /* Die globale AGENTS.md baut ihr Gerüst sofort auf; alle anderen Bereiche
     folgen nach dem zentralen Datenabruf. */
  fillGlobalAgents(sections['global-agents'], token);
  loaded['global-agents'] = true;
  fillAccess(sections.access, token);
  loaded.access = true;
  fillAppearance(sections.appearance, token);
  loaded.appearance = true;

  var agentsData = {};
  try { agentsData = await api('/api/agents') || {}; }
  catch (error) { agentsData = {}; }
  if (NV.stale(token)) return;

  var loaders = {
    'global-agents': function () { return fillGlobalAgents(sections['global-agents'], token); },
    'appearance': function () { return fillAppearance(sections.appearance, token); },
    'access': function () { fillAccess(sections.access, token); },
    'features': function () { fillFeatures(sections.features); },
    'limits': function () { return fillLimits(sections.limits, token); },
    'gates': function () { return fillGates(sections.gates, token); },
    'models': function () { fillModels(sections.models, agentsData, token); },
    'profiles': function () { fillProfiles(sections.profiles, agentsData, token); },
    'mcp': function () { return fillMcp(sections.mcp, token); },
    'harness': function () { return fillHarness(sections.harness, token); }
  };

  function load(id) {
    if (loaded[id] || !loaders[id] || !document.contains(sections[id])) return;
    loaded[id] = true;
    loaders[id]();
  }

  function syncFeatures() {
    /* Ein ausgeblendeter Bereich verkürzt die Seite; der Scrollstand bleibt
       erhalten, indem die Höhe des Inhalts beibehalten wird. */
    var scroll = window.scrollY;
    content.style.minHeight = '';
    var before = document.documentElement.scrollHeight;
    NV_SETTINGS_SECTIONS.forEach(function (entry) {
      var id = entry[0];
      var visible = !NV_SETTINGS_FEATURED[id] || NV.feature(id);
      sections[id].hidden = !visible;
      links[id].hidden = !visible;
      if (visible) load(id);
    });
    var gatesHost = sections.gates.querySelector('[data-nv-advanced-host]');
    if (gatesHost) {
      if (NV.feature('gates')) gatesHost.setAttribute('data-nv-advanced', 'gates');
      else gatesHost.removeAttribute('data-nv-advanced');
    }
    var after = document.documentElement.scrollHeight;
    if (after < before) {
      content.style.minHeight = (content.offsetHeight + before - after) + 'px';
    }
    window.scrollTo(0, scroll);
  }

  function syncScroll() {
    if (!document.contains(content)) return;
    if (pinned !== null) {
      if (Math.abs(window.scrollY - pinnedScrollY) <= 3) return;
      pinned = null;
    }
    var line = window.innerWidth < 1024 ? 150 : 190;
    var active = null;
    NV_SETTINGS_SECTIONS.forEach(function (entry) {
      var id = entry[0];
      if (sections[id].hidden) return;
      var box = sections[id].getBoundingClientRect();
      if (box.top <= line) active = id;
    });
    if (active) markSection(active);
  }

  NV.settingsController = {syncFeatures: syncFeatures, syncScroll: syncScroll,
    pin: pin};
  syncFeatures();
};

/* ------------------------------------------------------------------------- */
/* 1. Globale AGENTS.md                                                       */
/* ------------------------------------------------------------------------- */

async function fillGlobalAgents(section, token) {
  /* Das Gerüst steht sofort; der Anlegen-Knopf ist damit auch während des
     Datenabrufs im DOM (Bestandsvertrag von F34). */
  var view = {exists: false, digest: '', text: ''};
  var projects = [];
  var digest = '';
  var stateBox = el('div', {class: 'nv-row', 'data-nv-global-agents-state': ''});
  var projectBox = el('div', {class: 'nv-stack', 'data-nv-agents-files': ''});
  var error = settingsErrorBox();
  section.append(el('small', {class: 'nv-note',
    'data-nv-global-agents-hint': ''},
    tr('Diese Regeln gelten für alle Projekte; projektbezogene AGENTS.md ergänzen sie.')),
    stateBox, el('h3', {}, tr('Projektdateien')), projectBox, error);

  function backupsOf(value) {
    var source = (value && value.backups) || (value && value.view
      && value.view.backups) || [];
    return Array.isArray(source) ? source.map(String) : [];
  }

  function openGlobalEditor(text) {
    var textarea = el('textarea', {'data-nv-agents-text': '', rows: '18'},
      nvText(text));
    var restoreSelect = el('select', {'data-nv-agents-backup-select': '',
      'aria-label': tr('Sicherung auswählen')});

    function showBackups(names) {
      restoreSelect.replaceChildren.apply(restoreSelect, names.map(function (name) {
        return el('option', {value: name}, name);
      }));
    }
    showBackups(backupsOf(view));

    var save = el('button', {class: 'nv-btn nv-primary', type: 'button',
      'data-nv-action': 'agents-save', on: {click: async function () {
        settingsError(error, '');
        try {
          var answer = await api('/api/global_agents_file', {
            action: 'save', text: String(textarea.value || ''), digest: digest
          });
          if (answer && answer.ok === false) {
            settingsError(error, nvBackend(answer.message) || tr('Speichern fehlgeschlagen'));
            return;
          }
          digest = String(answer.digest || digest);
          toast(nvBackend(answer && answer.message) || tr('AGENTS.md gespeichert'));
        } catch (failure) {
          settingsError(error, String(failure && failure.message || failure));
        }
      }}}, tr('Speichern'));
    var backup = el('button', {class: 'nv-btn', type: 'button',
      'data-nv-action': 'agents-backup', on: {click: async function () {
        settingsError(error, '');
        try {
          var answer = await api('/api/global_agents_file', {action: 'backup'});
          if (answer && answer.ok === false) {
            settingsError(error, nvBackend(answer.message) || tr('Sichern fehlgeschlagen'));
            return;
          }
          var fresh = answer.view || await api('/api/global_agents_file') || {};
          view = fresh;
          showBackups(backupsOf(fresh));
          toast(nvBackend(answer.message) || tr('AGENTS.md gesichert'));
        } catch (failure) {
          settingsError(error, String(failure && failure.message || failure));
        }
      }}}, tr('Sichern'));
    var restore = el('button', {class: 'nv-btn', type: 'button',
      'data-nv-action': 'agents-restore', on: {click: function () {
        var name = String(restoreSelect.value || '');
        if (!name) return;
        NV.confirmView({title: tr('AGENTS.md wiederherstellen'),
          message: tr('Die aktuelle Datei wird vorher gesichert. Fortfahren?'),
          danger: true,
          onConfirm: async function () {
            try {
              var answer = await api('/api/global_agents_file', {
                action: 'restore', name: name, confirm: true
              });
              if (answer && answer.ok === false) {
                settingsError(error, nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
                return;
              }
              var fresh = answer.view || await api('/api/global_agents_file') || {};
              view = fresh;
              digest = String(fresh.digest || digest);
              showBackups(backupsOf(fresh));
              textarea.value = String(fresh.text || '');
              drawState();
              toast(nvBackend(answer.message) || tr('AGENTS.md wiederhergestellt'));
            } catch (failure) {
              settingsError(error, String(failure && failure.message || failure));
            }
          }});
      }}}, tr('Wiederherstellen'));

    NV.editView.open({title: tr('Globale AGENTS.md bearbeiten'),
      content: el('div', {class: 'nv-stack'}, textarea),
      footer: nvFoot(save, backup, restoreSelect, restore,
        el('button', {class: 'nv-btn', type: 'button',
          on: {click: function () { NV.editView.close(); }}}, tr('Abbrechen')))});
  }

  function drawState() {
    var button = view.exists
      ? el('button', {class: 'nv-btn nv-primary', type: 'button',
        'data-nv-action': 'global-agents-edit',
        on: {click: function () { openGlobalEditor(view.text || ''); }}},
        tr('Bearbeiten'))
      : el('button', {class: 'nv-btn nv-primary', type: 'button',
        'data-nv-action': 'global-agents-create', on: {click: async function () {
          settingsError(error, '');
          try {
            var answer = await api('/api/global_agents_file', {action: 'create'});
            if (answer && answer.ok === false) {
              settingsError(error, nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
              return;
            }
            view = await api('/api/global_agents_file') || {};
            digest = String(view.digest || '');
            drawState();
            openGlobalEditor(view.text || '');
            toast(nvBackend(answer.message) || tr('Vorlage angelegt'));
          } catch (failure) {
            settingsError(error, String(failure && failure.message || failure));
          }
        }}}, tr('Vorlage anlegen'));
    stateBox.replaceChildren(
      el('span', {class: 'nv-muted'},
        view.exists ? tr('Vorhanden') : tr('Datei fehlt')), button);
  }
  drawState();

  try {
    var answers = await Promise.all([
      api('/api/global_agents_file'), api('/api/projects')
    ]);
    view = answers[0] || {exists: false};
    projects = (Array.isArray(answers[1]) ? answers[1] : []).map(function (item) {
      return typeof item === 'string' ? item : (item && item.name || '');
    }).filter(Boolean);
  } catch (failure) { view = {exists: false}; }
  if (NV.stale(token)) return;
  digest = String(view.digest || '');
  drawState();

  projects.forEach(function (name) {
    projectBox.append(el('div', {class: 'nv-row',
      'data-nv-agents-file-row': name},
      el('span', {}, name),
      el('button', {class: 'nv-btn', type: 'button',
        'data-nv-action': 'agents-file-edit', on: {click: async function () {
          var detail;
          try {
            detail = await api('/api/agents_file?name=' + encodeURIComponent(name)) || {};
          } catch (failure) {
            settingsError(error, String(failure && failure.message || failure));
            return;
          }
          var before = el('textarea', {'data-nv-agents-before': '', rows: '16'},
            nvText(detail.before));
          var after = el('textarea', {'data-nv-agents-after': '', rows: '16'},
            nvText(detail.after));
          var fileError = settingsErrorBox();
          var save = el('button', {class: 'nv-btn nv-primary', type: 'button',
            'data-nv-action': 'agents-save', on: {click: async function () {
              try {
                var answer = await api('/api/agents_file', {
                  name: name, action: 'save',
                  before: String(before.value || ''),
                  after: String(after.value || ''),
                  digest: String(detail.digest || '')
                });
                if (answer && answer.ok === false) {
                  settingsError(fileError, nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
                  return;
                }
                detail = answer.agents_file || detail;
                toast(nvBackend(answer.message) || tr('AGENTS.md gespeichert'));
              } catch (failure) {
                settingsError(fileError, String(failure && failure.message || failure));
              }
            }}}, tr('Speichern'));
          var foot = nvActions();
          foot.append(save, el('button', {class: 'nv-btn', type: 'button',
            on: {click: function () { NV.editView.close(); }}}, tr('Abbrechen')));
          NV.editView.open({title: tr('AGENTS.md von ') + name,
            content: el('div', {class: 'nv-stack'},
              el('p', {class: 'nv-note'}, tr('Der verwaltete Block zwischen den Feldern wird von vibe erzeugt und bleibt unverändert.')),
              nvField(tr('Vor dem verwalteten Block'), before),
              nvField(tr('Nach dem verwalteten Block'), after),
              fileError),
            footer: foot});
        }}}, tr('Datei bearbeiten'))));
  });

}

/* ------------------------------------------------------------------------- */
/* 2. Darstellung                                                             */
/* ------------------------------------------------------------------------- */

async function fillAppearance(section, token) {
  var themeSelect = el('select', {'data-nv-theme-select': '',
    'aria-label': tr('Darstellung')});
  [['light', 'Hell'], ['dark', 'Dunkel'], ['auto', 'System']].forEach(function (option) {
    themeSelect.append(el('option', {value: option[0]}, tr(option[1])));
  });
  themeSelect.value = NV.themePreference();
  themeSelect.addEventListener('change', function () { NV.setTheme(themeSelect.value); });
  section.append(nvField(tr('Darstellung'), themeSelect));

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
  var langSelect = el('select', {'data-nv-language-select': '',
    'aria-label': tr('Sprache')});
  [['en', 'English'], ['de', 'Deutsch']].forEach(function (option) {
    langSelect.append(el('option', {value: option[0]}, option[1]));
  });
  langSelect.value = engine && typeof engine.current === 'function'
    ? engine.current() : 'en';
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
    el('p', {class: 'nv-muted'}, tr('ui.language.hint')),
    nvField(tr('Sprache auswählen'), langSelect));

  var currency = {currency: 'EUR', usd_rate: 1.0};
  try { currency = await api('/api/ui_settings') || currency; }
  catch (error) { /* Anzeige bleibt mit Voreinstellung bedienbar */ }
  if (NV.stale(token)) return;

  var currencySelect = el('select', {'data-nv-currency': '',
    'aria-label': tr('Währung')});
  [['EUR', 'EUR'], ['USD', 'USD']].forEach(function (option) {
    currencySelect.append(el('option', {value: option[0]}, option[1]));
  });
  currencySelect.value = currency.currency === 'USD' ? 'USD' : 'EUR';
  var rateInput = el('input', {type: 'number', min: '0.01', max: '100', step: '0.01',
    'data-nv-usd-rate': '', value: String(Number(currency.usd_rate) || 1),
    'aria-label': tr('USD je 1 EUR')});
  var rateRow = nvField(tr('USD je 1 EUR'), rateInput);
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
        var answer = await api('/api/ui_settings', {
          currency: currencySelect.value,
          usd_rate: currencySelect.value === 'USD' ? rate : 1.0
        });
        toast(nvBackend(answer && answer.message) || tr('Währung gespeichert'));
      } catch (failure) {
        settingsError(error, String(failure && failure.message || failure));
      }
    }}}, tr('Speichern'));
  section.append(el('h3', {}, tr('Währung')),
    el('p', {class: 'nv-muted'},
      tr('Preise bleiben in Euro je 1 Mio. Tokens gespeichert und werden nur für die Anzeige umgerechnet.')),
    nvField(tr('Währung auswählen'), currencySelect), rateRow,
    nvFoot(save), error);
}

/* ------------------------------------------------------------------------- */
/* 3. Zugriff                                                                 */
/* ------------------------------------------------------------------------- */

function fillAccess(section, token) {
  var security = {port: '', bind: '', allowlist: [], password_set: false,
    restart_required: false};
  var error = settingsErrorBox();
  var portInput = el('input', {inputmode: 'numeric', 'data-nv-field': 'port',
    'aria-label': tr('Port')});
  var bindInput = el('input', {'data-nv-field': 'bind',
    'aria-label': tr('Bind-Adresse')});
  var allowInput = el('input', {'data-nv-field': 'allowlist',
    'aria-label': tr('IP-Allowlist')});
  var pending = el('p', {class: 'nv-note', 'data-nv-restart-pending': '', hidden: ''},
    tr('Ein neustartpflichtiger Wert wurde gespeichert.'));

  api('/api/security').then(function (answer) {
    if (!answer || NV.stale(token)) return;
    security = answer;
    portInput.placeholder = String(security.port || '');
    bindInput.placeholder = String(security.bind || '');
    allowInput.placeholder = (security.allowlist || []).join(', ');
    pending.hidden = !security.restart_required;
  }).catch(function () { /* Ansicht bleibt lesbar */ });

  var password = el('input', {type: 'password', 'data-nv-field': 'password',
    placeholder: tr('neues Passwort (mind. 8 Zeichen)'),
    'aria-label': tr('Neues Passwort')});
  var repeat = el('input', {type: 'password', 'data-nv-field': 'password-repeat',
    placeholder: tr('Passwort wiederholen'),
    'aria-label': tr('Passwort wiederholen')});

  var network = el('details', {class: 'nv-access-network nv-card',
    'data-nv-network-advanced': ''},
    el('summary', {}, tr('Netzwerk (erweitert)')),
    el('p', {class: 'nv-note'}, tr('Netzwerk-Hinweis')),
    nvField(tr('Port'), portInput),
    nvField(tr('Bind-Adresse'), bindInput),
    nvField(tr('IP-Allowlist'), allowInput),
    nvFoot(el('button', {class: 'nv-btn nv-secondary', type: 'button',
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
        if (String(bindInput.value || '').trim()) {
          update.bind = String(bindInput.value).trim();
        }
        if (String(allowInput.value || '').trim()) {
          update.allowlist = String(allowInput.value).split(/[\s,]+/).filter(Boolean);
        }
        try {
          var answer = await api('/api/security', update);
          if (answer.ok) {
            portInput.value = ''; bindInput.value = ''; allowInput.value = '';
            var required = answer.security
              ? answer.security.restart_required : answer.restart_required;
            pending.hidden = !required;
            toast(bt(answer.message) || tr('Zugriffssicherheit gespeichert'));
          } else settingsError(error, bt(answer.message));
        } catch (failure) {
          settingsError(error, String(failure && failure.message || failure));
        }
      }}}, tr('Speichern'))));

  var restartFoot = nvActions();
  restartFoot.append(el('button', {class: 'nv-btn nv-primary', type: 'button',
    'data-nv-action': 'dashboard-restart', on: {click: function () {
      NV.confirmView({title: tr('Dashboard neu starten'),
        message: tr('Das Dashboard wird kurz unterbrochen. Laufende Agentenläufe bleiben erhalten.'),
        onConfirm: function () { restartDashboard(error); }});
    }}}, tr('Dashboard neu starten')));

  section.append(el('h3', {}, tr('Anmeldung')),
    nvField(tr('Neues Passwort'), password),
    nvField(tr('Passwort wiederholen'), repeat),
    nvFoot(
      el('button', {class: 'nv-btn nv-primary', type: 'button',
        'data-nv-action': 'password-set', on: {click: async function () {
          settingsError(error, '');
          if (String(password.value || '') !== String(repeat.value || '')) {
            settingsError(error, tr('Passwörter stimmen nicht überein'));
            return;
          }
          try {
            var answer = await api('/api/security',
              {action: 'password', password: password.value});
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
            var answer = await api('/api/security',
              {action: 'password', clear: true});
            toast(bt(answer.message) || tr('Kennwort entfernt'));
          } catch (failure) {
            settingsError(error, String(failure && failure.message || failure));
          }
        }}}, tr('Passwort entfernen')),
      el('button', {class: 'nv-btn', type: 'button',
        'data-nv-action': 'logout',
        on: {click: function () { NV.logout(); }}}, tr('Abmelden'))),
    el('h3', {}, tr('Neustart')),
    el('p', {class: 'nv-note', 'data-nv-restart-note': ''},
      tr('Änderungen an Port, Bind-Adresse und Allowlist werden gespeichert und erst nach einem Neustart des Dashboards wirksam.')),
    pending, restartFoot, network, error);
}

async function restartDashboard(errorBox) {
  try {
    var answer = await api('/api/security', {action: 'restart'});
    if (answer && answer.ok === false) {
      settingsError(errorBox, nvBackend(answer.message) || tr('Neustart fehlgeschlagen'));
      return;
    }
    toast(nvBackend(answer && answer.message) || tr('Dashboard neu gestartet'));
    var host = answer && answer.bind && answer.bind !== '0.0.0.0'
      ? answer.bind : location.hostname;
    var origin = location.protocol + '//' + host + ':' + answer.port;
    var token = answer.token || NV.token();
    sessionStorage.setItem('nv-restarted', 'true');
    var deadline = Date.now() + 20000;
    while (Date.now() < deadline) {
      try {
        var health = await fetch(origin + '/api/health',
          {headers: {'X-Token': token}});
        if (health.ok) {
          location.href = origin + '/#t=' + encodeURIComponent(token);
          return;
        }
      } catch (wait) { /* der Server startet noch */ }
      await new Promise(function (resolve) { setTimeout(resolve, 300); });
    }
    settingsError(errorBox, tr('Der Dashboard-Neustart dauert zu lange.'));
  } catch (failure) {
    settingsError(errorBox, String(failure && failure.message || failure));
  }
}

/* ------------------------------------------------------------------------- */
/* 4. Funktionen                                                              */
/* ------------------------------------------------------------------------- */

function fillFeatures(section) {
  var groups = NV_SETTINGS_FEATURE_GROUPS.map(function (group) {
    var rows = group.ids.map(function (id) {
      var box = el('input', {type: 'checkbox', 'data-nv-feature': id,
        checked: NV.feature(id)});
      box.addEventListener('change', function () {
        NV.setFeature(id, box.checked, {source: 'settings'});
      });
      return el('label', {class: 'nv-switch-row'}, box,
        el('span', {class: 'nv-switch-text'},
          el('strong', {}, tr(id)),
          el('small', {}, tr(NV_SETTINGS_FEATURE_HELP[id] || id))));
    });
    return el('div', {class: 'nv-feature-group'},
      el('h3', {}, tr(group.title)), ...rows);
  });
  section.append(el('p', {class: 'nv-muted'},
    tr('Technische Bereiche sind standardmäßig ausgeblendet.')),
    el('div', {class: 'nv-feature-groups', 'data-nv-feature-groups': ''}, ...groups));
}

/* ------------------------------------------------------------------------- */
/* 5. Laufverhalten                                                           */
/* ------------------------------------------------------------------------- */

async function fillLimits(section, token) {
  var limits;
  try { limits = await api('/api/limits') || {mode: 'stop'}; }
  catch (error) { limits = {mode: 'stop'}; }
  if (NV.stale(token)) return;
  var mode = limits.mode === 'continue' ? 'continue' : 'stop';

  var box = el('input', {type: 'checkbox', 'data-nv-limits-mode': '',
    'aria-label': tr('Fortsetzen')});
  box.checked = mode === 'continue';
  var switchRow = el('label', {class: 'label.nv-switch-row'}, box,
    el('span', {class: 'nv-switch-text'},
      el('strong', {}, tr('Fortsetzen')),
      el('small', {}, tr('An = bestehende Sitzung fortsetzen, aus = neue Läufe stoppen.'))));

  box.addEventListener('change', async function () {
    var next = box.checked ? 'continue' : 'stop';
    try {
      var answer = await api('/api/limits', {action: next});
      if (answer && answer.ok === false) {
        box.checked = !box.checked;
        settingsError(error, nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
        return;
      }
      toast(nvBackend(answer && answer.message)
        || tr(next === 'continue' ? 'Fortsetzen' : 'Stopp'));
    } catch (failure) {
      box.checked = !box.checked;
      settingsError(error, String(failure && failure.message || failure));
    }
  });

  var error = settingsErrorBox();
  section.append(el('p', {class: 'nv-muted', 'data-nv-limits-help': ''},
    tr('Fortsetzen lässt neue Läufe an einer vorhandenen Sitzung weiterarbeiten; Stopp beendet neue Läufe, ohne eine Sitzung fortzusetzen. Die Wahl gilt nur für neue Läufe.')),
    switchRow, error);
}

/* ------------------------------------------------------------------------- */
/* 6. Schranken                                                               */
/* ------------------------------------------------------------------------- */

function gateOriginText(origin) {
  var key = ({'Standard': 'Standard', 'global': 'Global',
    'projekt': 'Projekt', 'Umgebung': 'Umgebung'})[String(origin)]
    || String(origin || 'Standard');
  return String(tr(key));
}

async function fillGates(section, token) {
  var view = {gates: {}};
  var projects = [];
  try {
    var answers = await Promise.all([api('/api/gates'), api('/api/projects')]);
    view = answers[0] || {gates: {}};
    projects = (Array.isArray(answers[1]) ? answers[1] : []).map(function (item) {
      return typeof item === 'string' ? item : (item && item.name || '');
    }).filter(Boolean);
  } catch (error) { view = {gates: {}}; }
  if (NV.stale(token)) return;

  var select = el('select', {'data-nv-gates-project': '',
    'aria-label': tr('Projekt')});
  select.append(el('option', {value: 'global'}, tr('Global')));
  projects.forEach(function (name) {
    select.append(el('option', {value: name}, name));
  });
  select.value = 'global';

  var holder = el('div', {class: 'nv-table-wrap'});
  var error = settingsErrorBox();
  var reset = el('button', {class: 'nv-btn', type: 'button',
    'data-nv-action': 'gates-reset',
    title: tr('Gilt nur für ein ausgewähltes Projekt'),
    on: {click: function () {
      var cleared = {};
      Object.keys(view.gates || {}).forEach(function (key) { cleared[key] = ''; });
      send(cleared);
    }}}, tr('Projektabweichungen zurücksetzen'));
  var foot = nvActions();
  foot.append(el('button', {class: 'nv-btn nv-primary', type: 'button',
    'data-nv-action': 'gates-save', on: {click: function () { send(values()); }}},
    tr('Speichern')), reset);

  function values() {
    var result = {};
    holder.querySelectorAll('tr[data-nv-gate]').forEach(function (row) {
      var field = row.querySelector(select.value === 'global'
        ? '[data-nv-gate-value]' : '[data-nv-gate-override]');
      if (field) result[row.getAttribute('data-nv-gate')] = String(field.value || '');
    });
    return result;
  }

  function draw(data) {
    view = data || {gates: {}};
    var table = el('table', {class: 'nv-table', 'data-nv-gates-table': ''});
    if (select.value === 'global') {
      table.append(el('tr', {}, el('th', {}, tr('Schranke')),
        el('th', {}, tr('Wirkung')), el('th', {}, tr('Wert')),
        el('th', {}, tr('Herkunft'))));
    } else {
      table.append(el('tr', {}, el('th', {}, tr('Schranke')),
        el('th', {}, tr('Wirkung')), el('th', {}, tr('Globaler Wert')),
        el('th', {}, tr('Projektwert')), el('th', {}, tr('Wirksam')),
        el('th', {}, tr('Herkunft'))));
    }

    Object.keys(view.gates || {}).forEach(function (key) {
      var entry = view.gates[key] || {};
      var globalValue = nvText(entry.global == null || entry.global === ''
        ? entry.default : entry.global);
      var cells = [el('td', {}, el('b', {}, key)),
        el('td', {}, el('small', {class: 'nv-muted', 'data-nv-gate-help': ''},
          tr(NV_SETTINGS_GATE_HELP[key]
            || 'Quota für diese Schranke begrenzen — Werte nur setzen, die das Ziel wirklich schützen.')))];

      if (select.value === 'global') {
        var field = el('input', {'data-nv-gate-value': '', type: 'text',
          value: nvText(entry.value), placeholder: tr('Standard') + ': '
            + nvText(entry.default), 'aria-label': tr('Wert')});
        cells.push(el('td', {}, field));
      } else {
        var readonly = el('span', {'data-nv-gate-global': ''}, globalValue);
        var override = el('input', {'data-nv-gate-override': '', type: 'text',
          value: nvText(entry.override),
          placeholder: tr('leer = globaler Wert'), 'aria-label': tr('Projektwert')});
        var effective = el('span', {'data-nv-gate-effective': ''},
          nvText(entry.value));
        var origin = el('span', {class: 'nv-badge', 'data-nv-gate-origin': ''},
          gateOriginText(entry.origin));
        var overrideCell = el('td', {}, override);
        function syncOverrideBadge(typed) {
          var badge = overrideCell.querySelector('[data-nv-gate-override-badge]');
          if (badge) badge.remove();
          if (typed && typed !== globalValue) {
            overrideCell.append(el('span', {class: 'nv-badge',
              'data-nv-gate-override-badge': ''}, tr('Weicht ab')));
          }
        }
        override.addEventListener('input', function () {
          var typed = String(override.value || '').trim();
          effective.textContent = typed || globalValue;
          origin.textContent = gateOriginText(typed ? 'projekt'
            : (entry.global ? 'global' : 'Standard'));
          syncOverrideBadge(typed);
        });
        cells.push(el('td', {}, readonly), overrideCell,
          el('td', {}, effective),
          el('td', {}, origin));
        syncOverrideBadge(nvText(entry.override));
      }
      if (select.value === 'global') {
        cells.push(el('td', {}, el('span', {class: 'nv-badge',
          'data-nv-gate-origin': ''}, gateOriginText(entry.origin))));
      }
      table.append(el('tr', {'data-nv-gate': key}, ...cells));
    });
    holder.replaceChildren(table);
    reset.disabled = select.value === 'global';
  }

  async function send(payload) {
    settingsError(error, '');
    try {
      var answer = await api('/api/gates', {
        project: select.value === 'global' ? '' : select.value,
        values: payload
      });
      if (answer && answer.ok === false) {
        settingsError(error, nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
        return;
      }
      var fresh = await api(select.value === 'global'
        ? '/api/gates' : '/api/gates?name=' + encodeURIComponent(select.value));
      draw(fresh || answer);
      toast(nvBackend(answer && answer.message) || tr('Schranken gespeichert'));
    } catch (failure) {
      settingsError(error, String(failure && failure.message || failure));
    }
  }

  select.addEventListener('change', async function () {
    try {
      var fresh = await api(select.value === 'global'
        ? '/api/gates' : '/api/gates?name=' + encodeURIComponent(select.value));
      if (!NV.stale(token)) draw(fresh || {gates: {}});
    } catch (failure) {
      settingsError(error, String(failure && failure.message || failure));
    }
  });

  draw(view);
  /* Der Bestands-Hook data-nv-advanced wird nur bei aktivem Feature gesetzt,
     damit die Ansicht ohne Gates weiterhin frei davon bleibt. */
  var host = el('div', {class: 'nv-stack', 'data-nv-advanced-host': ''});
  if (NV.feature('gates')) host.setAttribute('data-nv-advanced', 'gates');
  host.append(el('p', {class: 'nv-muted', 'data-nv-gates-hint': ''},
    tr('Ein Projektwert überschreibt den globalen Wert; ohne Projektwert gilt der globale Wert oder der Standardwert.')),
    nvField(tr('Projekt'), select), holder, foot, error);
  section.append(host);
}

/* ------------------------------------------------------------------------- */
/* 7. Modelle                                                                 */
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
  var data = agentsData;
  var holder = el('div', {class: 'nv-table-wrap'});
  var stand = el('div', {class: 'nv-muted', 'data-nv-models-stand': ''});
  var details = el('details', {class: 'nv-card', 'data-nv-models': ''},
    el('summary', {}, tr('Modellliste')));
  var refresh = el('button', {class: 'nv-btn nv-primary', type: 'button',
    'data-nv-action': 'models-refresh', on: {click: async function () {
      try {
        var answer = await api('/api/agents', {action: 'refresh_models'}) || {};
        if (answer.ok === false) {
          toast(nvBackend(answer.message) || tr('Aktualisierung fehlgeschlagen'));
          return;
        }
        data = answer.models != null ? answer : data;
        details.open = true;
        draw();
        toast(nvBackend(answer.message) || tr('Modelle aktualisiert'));
      } catch (failure) {
        toast(tr('Aktualisierung fehlgeschlagen: ')
          + String(failure && failure.message || failure));
      }
    }}}, tr('Aktualisieren'));

  function modelDetail(id) {
    var model = (data.info || {})[id] || {};
    var facts = Object.keys(model.fakten || {}).map(function (key) {
      return nvAssert(key, model.fakten[key]);
    });
    var assessments = Object.keys(model.einschaetzungen || {}).map(function (key) {
      return nvAssert(key, model.einschaetzungen[key]);
    });
    var content = el('div', {class: 'nv-stack', 'data-nv-model-detail': ''},
      el('p', {}, el('b', {}, tr('Anbieter') + ': '),
        nvText(model.anbieter || tr('unbekannt'))),
      el('p', {}, el('b', {}, tr('Preis') + ': '),
        nvText((model.preis || {}).text || tr('unbekannt'))),
      el('p', {}, el('b', {}, tr('Status') + ': '),
        nvText(model.status || tr('unbekannt'))),
      el('div', {}, el('b', {}, tr('Fakten')), ...facts,
        facts.length ? null : el('div', {class: 'nv-muted'}, tr('keine Angaben'))),
      el('div', {}, el('b', {}, tr('Einschätzungen')), ...assessments,
        assessments.length ? null : el('div', {class: 'nv-muted'}, tr('keine Angaben'))),
      el('p', {class: 'nv-muted'}, tr('Preisquelle') + ': '
        + nvText((model.preis || {}).quelle || tr('unbekannt'))));
    var foot = nvActions();
    foot.append(el('button', {class: 'nv-btn', type: 'button',
      on: {click: function () { NV.editView.close(); }}}, tr('Schließen')));
    NV.editView.open({title: id, content: content, footer: foot});
  }

  function draw() {
    var ids = (data.models || []).slice();
    Object.keys(data.info || {}).forEach(function (id) {
      if (ids.indexOf(id) < 0) ids.push(id);
    });
    var source = data.models_stand || '';
    stand.replaceChildren(document.createTextNode(
      String(tr('Letzte Aktualisierung')) + ': ' + (source || '—')));
    if (!ids.length) {
      details.open = true;
      holder.replaceChildren(el('div', {class: 'nv-empty',
        'data-nv-models-empty': ''},
        tr('Keine Modelle vorhanden. Mit „Aktualisieren“ werden die Modelle des Harness geladen.'),
        data.models_error ? el('div', {'data-nv-models-error': ''},
          nvText(data.models_error)) : null));
      return;
    }
    var table = el('table', {class: 'nv-table', 'data-nv-models-table': ''},
      el('tr', {}, el('th', {}, tr('Modell')), el('th', {}, tr('Anbieter')),
        el('th', {}, tr('Preis')), el('th', {}, tr('Quelle')),
        el('th', {}, tr('Status'))));
    ids.forEach(function (id) {
      var model = (data.info || {})[id] || {};
      table.append(el('tr', {'data-nv-model': id, class: 'nv-clickable',
        on: {click: function () { modelDetail(id); }}},
        el('td', {}, el('b', {}, id)),
        el('td', {}, nvText(model.anbieter || tr('unbekannt'))),
        el('td', {}, nvText((model.preis || {}).text || tr('unbekannt'))),
        el('td', {}, nvText((model.preis || {}).quelle || tr('unbekannt'))),
        el('td', {}, nvText(model.status || tr('unbekannt')))));
    });
    holder.replaceChildren(table);
  }
  draw();

  var catalog = el('details', {class: 'nv-card', 'data-nv-model-catalog': ''},
    el('summary', {}, tr('Modellkatalog')),
    el('p', {class: 'nv-muted'}, String(tr('Katalogstand')) + ': '
      + nvText(data.stand || tr('unbekannt'))),
    el('p', {class: 'nv-muted'}, String(tr('Quellen')) + ': '
      + ((data.katalog || {}).quellen || []).map(function (source) {
        return nvText(source.name) + (source.datum ? ' (' + source.datum + ')' : '');
      }).join('; ')),
    el('div', {class: 'nv-note'}, el('b', {}, tr('Befunde')),
      el('div', {}, ((data.katalog || {}).findings || []).map(function (finding) {
        return nvText(finding.text || finding);
      }).join(' · ') || tr('keine Angaben'))),
    nvFoot(el('button', {class: 'nv-btn', type: 'button',
      'data-nv-action': 'models-prices',
      on: {click: function () { NV.navigate('#/evaluations/costs'); }}},
      tr('Preise bearbeiten'))));

  var head = nvActions();
  head.append(refresh);
  section.append(head, stand, details, holder, catalog);
}

/* ------------------------------------------------------------------------- */
/* 8. Profile                                                                 */
/* ------------------------------------------------------------------------- */

function standardProfiles(data) {
  var known = (data && data.standard_profiles)
    ? data.standard_profiles : ['default', 'free', 'mid', 'high'];
  return known.map(String);
}

function profileLabel(name) {
  return ({'default': 'Default', 'free': 'Kostenlos', 'mid': 'Mittel',
    'high': 'Hoch'})[String(name)] || String(name);
}

async function fillProfiles(section, agentsData, token) {
  var data = agentsData;
  var backups = [];
  var error = settingsErrorBox();
  var select = el('select', {'data-nv-profiles-select': '',
    'aria-label': tr('Profil')});
  var nameField = el('input', {type: 'text', 'data-nv-profile-name': '',
    placeholder: tr('Name des neuen Profils'), 'aria-label': tr('Name des neuen Profils')});
  var selectedBox = el('span', {'data-nv-profile-selected': ''});
  var standardBadge = el('span', {class: 'nv-badge',
    'data-nv-profile-standard': ''}, tr('Standardprofil'));
  var activeBadge = el('span', {class: 'nv-badge nv-primary',
    'data-nv-profile-active': ''}, tr('Aktiv'));
  var rolesBox = el('div', {class: 'nv-stack', 'data-nv-profile-roles': ''});
  var restoreSelect = el('select', {'data-nv-profile-restore-select': '',
    'aria-label': tr('Sicherung auswählen')});
  var deleteButton, draft = {}, saved = {}, selected = '';

  function profiles() { return data.profiles || {}; }
  function isStandard(name) { return standardProfiles(data).indexOf(name) >= 0; }
  function modelValues() {
    var out = [], seen = {};
    (data.models || []).forEach(function (value) {
      var text = String(value && value.id || value || '');
      if (text && !seen[text]) { seen[text] = true; out.push(text); }
    });
    return out;
  }
  function fallback(role) {
    return String(((data.default_models || {})[role])
      || ((data.vibe_agent || {}).model) || '');
  }
  function currentName() {
    return select.value || profiles().aktiv || 'default';
  }

  function redrawOptions() {
    var names = Object.keys(profiles().profile || {});
    standardProfiles(data).forEach(function (name) {
      if (names.indexOf(name) < 0) names.unshift(name);
    });
    if (!profiles().aktiv) names.sort();
    var wanted = names.indexOf(selected) >= 0 ? selected : (profiles().aktiv || 'default');
    selected = wanted;
    select.replaceChildren.apply(select, names.map(function (name) {
      return el('option', {value: name}, String(tr(profileLabel(name)))
        + (name === profiles().aktiv ? ' · ' + String(tr('Aktiv')) : ''));
    }));
    select.value = wanted;
  }

  function redrawRoles() {
    rolesBox.replaceChildren();
    var profile = (profiles().profile || {})[selected] || {};
    var roles = [];
    Object.keys(profiles().rollen || {}).forEach(function (role) {
      if (roles.indexOf(role) < 0) roles.push(role);
    });
    Object.keys(profiles().profile || {}).forEach(function (name) {
      Object.keys((profiles().profile || {})[name] || {}).forEach(function (role) {
        if (roles.indexOf(role) < 0) roles.push(role);
      });
    });
    roles.sort();
    /* Ohne konfigurierte Rollen bleibt die Zuordnung dennoch bedienbar. */
    if (!roles.length) roles.push('coder');

    if (selected === 'default') {
      roles.forEach(function (role) {
        rolesBox.append(el('div', {class: 'nv-row'},
          el('b', {}, role), el('span', {class: 'nv-muted'},
            '→ ' + (fallback(role) || String(tr('unbekannt'))))));
      });
      rolesBox.append(el('p', {class: 'nv-muted'},
        tr('Das Default-Profil spiegelt die Modelle der Agent-Einstellungen und ist nicht direkt editierbar.')));
      return;
    }
    roles.forEach(function (role) {
      var combo = NV.modelCombobox(modelValues(), saved[role] || '', {
        field: role, blank: tr('Default'),
        resolveDefault: function () { return fallback(role); },
        onchange: function (value) { draft[role] = String(value || ''); }
      });
      combo.setAttribute('data-nv-profile-role', role);
      rolesBox.append(nvField(role, combo));
    });
    if (!roles.length) {
      rolesBox.append(el('p', {class: 'nv-muted'}, tr('Keine Rollen zugeordnet.')));
    }
  }

  function redraw() {
    redrawOptions();
    selectedBox.replaceChildren(document.createTextNode(
      String(tr('Profil')) + ': ' + selected));
    standardBadge.hidden = !isStandard(selected);
    activeBadge.hidden = selected !== profiles().aktiv;
    saved = Object.assign({}, (profiles().profile || {})[selected] || {});
    draft = Object.assign({}, saved);
    redrawRoles();
    deleteButton.disabled = isStandard(selected);
  }

  async function refreshData() {
    try { data = await api('/api/agents') || data; }
    catch (failure) { /* vorhandene Ansicht bleibt nutzbar */ }
    if (!NV.stale(token)) redraw();
  }

  select.addEventListener('change', function () {
    selected = select.value || currentName();
    redraw();
  });

  function showBackups(names) {
    restoreSelect.replaceChildren.apply(restoreSelect, names.map(function (name) {
      return el('option', {value: name}, name);
    }));
  }
  showBackups(backups);

  deleteButton = el('button', {class: 'nv-btn', type: 'button',
    'data-nv-action': 'profile-delete', on: {click: function () {
      var name = currentName();
      NV.confirmView({title: tr('Profil löschen'),
        message: String(tr('Profil löschen?')) + ' ' + name,
        danger: true, onConfirm: async function () {
          try {
            var answer = await api('/api/profiles',
              {action: 'delete', name: name});
            if (answer && answer.ok === false) {
              settingsError(error, nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
              return;
            }
            toast(nvBackend(answer.message) || tr('Profil gelöscht'));
            await refreshData();
          } catch (failure) {
            settingsError(error, String(failure && failure.message || failure));
          }
        }});
    }}}, tr('Löschen'));

  var foot = nvActions();
  foot.append(
    el('button', {class: 'nv-btn nv-primary', type: 'button',
      'data-nv-action': 'profile-new', on: {click: async function () {
        var name = String(nameField.value || '').trim();
        nameField.value = '';
        if (!name) { settingsError(error, tr('Bitte einen Profilnamen eingeben.')); return; }
        try {
          var answer = await api('/api/profiles', {action: 'create', name: name});
          if (answer && answer.ok === false) {
            settingsError(error, nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
            return;
          }
          selected = name;
          toast(nvBackend(answer.message) || tr('Profil angelegt'));
          await refreshData();
        } catch (failure) {
          settingsError(error, String(failure && failure.message || failure));
        }
      }}}, tr('Neues Profil')),
    deleteButton,
    el('button', {class: 'nv-btn nv-primary', type: 'button',
      'data-nv-action': 'profile-save', on: {click: async function () {
        settingsError(error, '');
        try {
          var answer = await api('/api/profiles', {action: 'save',
            data: {rollen: profiles().rollen || {},
              profile: {[selected]: Object.assign({}, draft)}}});
          if (answer && answer.ok === false) {
            settingsError(error, nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
            return;
          }
          saved = Object.assign({}, draft);
          toast(nvBackend(answer.message) || tr('Profil gespeichert'));
        } catch (failure) {
          settingsError(error, String(failure && failure.message || failure));
        }
      }}}, tr('Speichern')),
    el('button', {class: 'nv-btn', type: 'button',
      'data-nv-action': 'profile-cancel', on: {click: function () {
        draft = Object.assign({}, saved);
        redrawRoles();
      }}}, tr('Abbrechen')),
    el('button', {class: 'nv-btn', type: 'button',
      'data-nv-action': 'profile-backup', on: {click: async function () {
        try {
          var answer = await api('/api/profiles', {action: 'backup'});
          if (answer && answer.ok === false) {
            settingsError(error, nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
            return;
          }
          if (answer && answer.backup && backups.indexOf(answer.backup) < 0) {
            backups.push(answer.backup);
          }
          showBackups(backups);
          toast(nvBackend(answer.message) || tr('Profile gesichert'));
        } catch (failure) {
          settingsError(error, String(failure && failure.message || failure));
        }
      }}}, tr('Sichern')),
    restoreSelect,
    el('button', {class: 'nv-btn', type: 'button',
      'data-nv-action': 'profile-restore', on: {click: function () {
        var name = String(restoreSelect.value || '');
        if (!name) return;
        NV.confirmView({title: tr('Profile wiederherstellen'),
          message: tr('Die aktuelle Datei wird vorher gesichert. Fortfahren?'),
          danger: true, onConfirm: async function () {
            try {
              var answer = await api('/api/profiles',
                {action: 'restore', name: name, confirm: true});
              if (answer && answer.ok === false) {
                settingsError(error, nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
                return;
              }
              if (answer && answer.profiles) data.profiles = answer.profiles;
              redraw();
              toast(nvBackend(answer.message) || tr('Profile wiederhergestellt'));
            } catch (failure) {
              settingsError(error, String(failure && failure.message || failure));
            }
          }});
      }}}, tr('Wiederherstellen')),
    el('button', {class: 'nv-btn nv-primary', type: 'button',
      'data-nv-action': 'profile-apply', on: {click: function () {
        var roles = [];
        Object.keys(profiles().rollen || {}).forEach(function (agent) {
          var role = profiles().rollen[agent];
          if (role && roles.indexOf(role) < 0) roles.push(role);
        });
        Object.keys(draft).forEach(function (role) {
          if (roles.indexOf(role) < 0) roles.push(role);
        });
        var lines = roles.map(function (role) {
          return role + ' → ' + (draft[role] || fallback(role) || String(tr('unbekannt')));
        });
        var preview = el('div', {class: 'nv-stack'},
          el('p', {}, String(tr('Profil anwenden')) + ': ' + selected),
          el('p', {class: 'nv-muted'}, lines.join(' · ') || String(tr('keine Angaben'))));
        NV.context.open({title: tr('Profilvorschau'), content: preview,
          footer: nvFoot(
            el('button', {class: 'nv-btn nv-primary', type: 'button',
              on: {click: async function () {
                try {
                  var answer = await api('/api/profiles',
                    {action: 'use', profile: selected});
                  if (answer && answer.ok === false) {
                    settingsError(error, nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
                    return;
                  }
                  data.profiles.aktiv = selected;
                  NV.context.close();
                  redraw();
                  toast(nvBackend(answer.message) || tr('Profil angewendet'));
                } catch (failure) {
                  settingsError(error, String(failure && failure.message || failure));
                }
              }}}, tr('Bestätigen')),
            el('button', {class: 'nv-btn', type: 'button',
              on: {click: function () { NV.context.close(); }}}, tr('Abbrechen')))});
      }}}, tr('Anwenden')));

  /* Ohne Nutzerprofile ist das Default-Profil nur eine lesende Spiegelung;
     dann startet die Auswahl beim ersten editierbaren Standardprofil. */
  var custom = Object.keys(profiles().profile || {}).some(function (name) {
    return standardProfiles(data).indexOf(name) < 0;
  });
  selected = !custom && isStandard(profiles().aktiv) && profiles().aktiv !== 'default'
    ? profiles().aktiv
    : (!custom ? 'free' : (profiles().aktiv || 'default'));
  redraw();
  section.append(nvField(tr('Profil auswählen'), select),
    el('div', {class: 'nv-row'}, selectedBox, standardBadge, activeBadge),
    nvField(tr('Name des neuen Profils'), nameField),
    rolesBox, foot, error);
  if (NV.stale(token)) return;
}

/* ------------------------------------------------------------------------- */
/* 9. MCP-Server                                                              */
/* ------------------------------------------------------------------------- */

function nvParsePairs(text) {
  var pairs = {};
  String(text || '').split(/\r?\n/).forEach(function (line) {
    var at = line.indexOf('=');
    if (at < 1) return;
    pairs[line.slice(0, at).trim()] = line.slice(at + 1).trim();
  });
  return pairs;
}

async function fillMcp(section, token) {
  var data;
  try { data = await api('/api/mcp') || {}; }
  catch (error) { data = {}; }
  if (NV.stale(token)) return;
  var servers = Array.isArray(data.servers) ? data.servers : [];
  var list = el('div', {class: 'nv-stack'});
  var scopeFilter = el('select', {'data-nv-mcp-scope-filter': '',
    'aria-label': tr('Geltungsbereich')});
  scopeFilter.append(el('option', {value: ''}, tr('Alle Bereiche')),
    el('option', {value: 'global'}, tr('Global')));
  (data.projects || []).forEach(function (project) {
    scopeFilter.append(el('option', {value: project}, project));
  });
  var searchWrap = NV.search({placeholder: tr('MCP-Server suchen …'),
    oninput: applyFilter});
  searchWrap.querySelector('[data-nv-search-input]').setAttribute('data-nv-mcp-search', '');
  var add = el('button', {class: 'nv-btn nv-primary', type: 'button',
    'data-nv-action': 'mcp-add', on: {click: function () { openForm(null); }}},
    tr('Hinzufügen'));
  var head = nvActions();
  head.append(add);
  section.append(head,
    el('div', {class: 'nv-filter-bar'}, searchWrap, scopeFilter), list);
  scopeFilter.addEventListener('change', applyFilter);

  function applyFilter() {
    var term = String(searchWrap.querySelector('[data-nv-search-input]').value || '')
      .toLowerCase();
    var scope = scopeFilter.value;
    list.querySelectorAll('[data-nv-mcp-server]').forEach(function (card) {
      var name = card.getAttribute('data-nv-mcp-server') || '';
      var cardScope = card.getAttribute('data-nv-mcp-scope') || '';
      card.hidden = name.toLowerCase().indexOf(term) < 0
        || (!!scope && scope !== cardScope);
    });
  }

  function entryFromForm(fields) {
    var entry = {type: fields.type.value,
      enabled: fields.enabled.checked};
    if (fields.type.value === 'local') {
      entry.command = String(fields.command.value || '').split(/\r?\n/)
        .map(function (line) { return line.trim(); }).filter(Boolean);
      if (fields.cwd.value) entry.cwd = String(fields.cwd.value).trim();
    } else {
      entry.url = String(fields.url.value || '').trim();
      entry.headers = nvParsePairs(fields.headers.value);
      if (fields.noauth.checked) entry.oauth = false;
    }
    if (fields.type.value === 'local') {
      var env = nvParsePairs(fields.env.value);
      if (Object.keys(env).length) entry.environment = env;
    }
    var timeout = Number(fields.timeout.value || 0);
    if (timeout > 0) entry.timeout = Math.round(timeout);
    return entry;
  }

  function testEntry(fields, result, name) {
    result.hidden = false;
    result.replaceChildren(el('span', {class: 'nv-muted'},
      String(tr('Verbindungstest läuft')) + ' …'));
    api('/api/mcp', {action: 'test', scope: fields.scope.value,
      name: name, entry: entryFromForm(fields)}).then(function (answer) {
      var report = answer && answer.result || {};
      var ok = !!report.ok;
      result.replaceChildren(
        el('b', {class: ok ? 'nv-ok' : 'nv-bad'},
          ok ? tr('Test bestanden') : tr('Test fehlgeschlagen')),
        el('div', {}, nvText(report.error || report.hint
          || nvBackend(answer && answer.message) || tr('Test beendet'))));
    }).catch(function (failure) {
      result.replaceChildren(el('b', {class: 'nv-bad'}, tr('Test fehlgeschlagen')),
        el('div', {}, String(failure && failure.message || failure)));
    });
  }

  function openForm(server, detail) {
    var isNew = !server;
    var fields = {
      name: el('input', {type: 'text', 'data-nv-mcp-name': '',
        value: isNew ? '' : server.name}),
      scope: el('select', {'data-nv-mcp-scope': '',
        'aria-label': tr('Geltungsbereich')}),
      type: el('select', {'data-nv-mcp-type': '', 'aria-label': tr('Typ')}),
      command: el('textarea', {'data-nv-mcp-command': '', rows: '5'}),
      env: el('textarea', {'data-nv-mcp-env': '', rows: '4'}),
      cwd: el('input', {type: 'text', 'data-nv-mcp-cwd': ''}),
      url: el('input', {type: 'text', 'data-nv-mcp-url': ''}),
      headers: el('textarea', {'data-nv-mcp-headers': '', rows: '4'}),
      noauth: el('input', {type: 'checkbox', 'data-nv-mcp-noauth': ''}),
      enabled: el('input', {type: 'checkbox', 'data-nv-mcp-enabled': '',
        checked: true}),
      timeout: el('input', {type: 'number', min: '1', 'data-nv-mcp-timeout': ''})
    };
    [['global', tr('Global')]].concat((data.projects || []).map(function (project) {
      return [project, project];
    })).forEach(function (option) {
      fields.scope.append(el('option', {value: option[0]}, option[1]));
    });
    fields.scope.value = isNew ? 'global' : server.scope;
    [['local', tr('Lokal')], ['remote', tr('Extern')]].forEach(function (option) {
      fields.type.append(el('option', {value: option[0]}, option[1]));
    });
    fields.type.value = 'local';
    var entry = (detail && detail.entry) || {};
    if (entry.type === 'remote') fields.type.value = 'remote';
    fields.command.value = (entry.command || []).join('\n');
    fields.env.value = Object.keys(entry.environment || {}).map(function (key) {
      return key + '=' + entry.environment[key];
    }).join('\n');
    fields.cwd.value = String(entry.cwd || '');
    fields.url.value = String(entry.url || '');
    fields.headers.value = Object.keys(entry.headers || {}).map(function (key) {
      return key + '=' + entry.headers[key];
    }).join('\n');
    fields.noauth.checked = entry.oauth === false;
    fields.enabled.checked = entry.enabled !== false;
    fields.timeout.value = String(entry.timeout || '');

    var result = el('div', {class: 'nv-note', 'data-nv-mcp-result': '', hidden: ''});
    var error = settingsErrorBox();
    var foot = nvActions();
    foot.append(el('button', {class: 'nv-btn nv-primary', type: 'button',
      'data-nv-action': 'mcp-save', on: {click: async function () {
        settingsError(error, '');
        fields.name.value = String(fields.name.value || '').trim();
        if (!fields.name.value) {
          settingsError(error, tr('Bitte einen Namen eingeben.'));
          return;
        }
        try {
          var answer = await api('/api/mcp', {
            action: 'save', scope: fields.scope.value,
            name: fields.name.value, entry: entryFromForm(fields),
            create: isNew, old_name: isNew ? null : server.name,
            expected: isNew ? null : (detail && detail.digest) || null
          });
          if (answer && answer.ok === false) {
            settingsError(error, nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
            return;
          }
          NV.editView.close();
          toast(nvBackend(answer.message) || tr('MCP-Server gespeichert'));
          data = await api('/api/mcp') || data;
          servers = Array.isArray(data.servers) ? data.servers : [];
          drawServers();
        } catch (failure) {
          settingsError(error, String(failure && failure.message || failure));
        }
      }}}, tr('Speichern')),
      el('button', {class: 'nv-btn', type: 'button',
        'data-nv-action': 'mcp-test',
        on: {click: function () {
          testEntry(fields, result, fields.name.value);
        }}}, tr('Verbindung testen')),
      el('button', {class: 'nv-btn', type: 'button',
        on: {click: function () { NV.editView.close(); }}}, tr('Abbrechen')));

    NV.editView.open({title: isNew ? tr('MCP-Server hinzufügen')
      : tr('MCP-Server bearbeiten') + ': ' + server.name,
      content: el('div', {class: 'nv-stack'},
        el('p', {class: 'nv-muted'},
          tr('Maskierte Werte bleiben unverändert, wenn sie nicht neu eingegeben werden.')),
        nvField(tr('Name'), fields.name),
        nvField(tr('Geltungsbereich'), fields.scope),
        nvField(tr('Typ'), fields.type),
        nvField(tr('Befehl (ein Argument je Zeile)'), fields.command),
        nvField(tr('Umgebungsvariablen'), fields.env),
        nvField(tr('Arbeitsordner'), fields.cwd),
        nvField(tr('URL'), fields.url),
        nvField(tr('Header'), fields.headers),
        el('label', {class: 'nv-switch-row'}, fields.noauth,
          el('span', {}, tr('OAuth ausschalten'))),
        el('label', {class: 'nv-switch-row'}, fields.enabled,
          el('span', {}, tr('Aktiv'))),
        nvField(tr('Zeitüberschreitung (ms)'), fields.timeout),
        result, error),
      footer: foot});
  }

  async function openEdit(server) {
    try {
      var detail = await api('/api/mcp_entry?scope=' + encodeURIComponent(server.scope)
        + '&name=' + encodeURIComponent(server.name));
      openForm(server, detail || {});
    } catch (failure) {
      toast(tr('Eintrag konnte nicht geladen werden: ')
        + String(failure && failure.message || failure));
    }
  }

  function drawServers() {
    list.replaceChildren();
    if (!servers.length) {
      list.append(el('p', {class: 'nv-empty'}, tr('Keine MCP-Server konfiguriert.')));
    }
    servers.forEach(function (server) {
      if (server.error) {
        list.append(el('div', {class: 'nv-note'},
          nvText(server.scope) + ': ' + nvText(server.error)));
        return;
      }
      var name = nvText(server.name);
      var active = server.enabled !== false;
      var state = NV.stateBadge({on: active});
      state.setAttribute('data-nv-mcp-state', '');
      var toggle = el('button', {class: 'nv-btn', type: 'button',
        'data-nv-action': 'mcp-toggle', on: {click: async function () {
          try {
            var answer = await api('/api/mcp', {action: 'toggle',
              scope: server.scope, name: name});
            if (answer && answer.ok === false) {
              toast(nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
              return;
            }
            active = !active;
            var badge = NV.stateBadge({on: active});
            badge.setAttribute('data-nv-mcp-state', '');
            state.replaceWith(badge);
            state = badge;
            toggle.textContent = String(tr(active ? 'Deaktivieren' : 'Aktivieren'));
            toast(nvBackend(answer && answer.message) || tr('MCP-Server geändert'));
          } catch (failure) {
            toast(tr('Aktion fehlgeschlagen: ')
              + String(failure && failure.message || failure));
          }
        }}}, tr(active ? 'Deaktivieren' : 'Aktivieren'));
      var result = el('div', {class: 'nv-note', 'data-nv-mcp-result': '', hidden: ''});
      list.append(el('article', {class: 'nv-card', 'data-nv-mcp-server': name,
        'data-nv-mcp-scope': nvText(server.scope)},
        el('div', {class: 'nv-row'}, el('h3', {}, name),
          el('span', {class: 'nv-kind-badge'}, nvText(server.scope)), state,
          el('span', {class: 'nv-muted'}, nvText(server.target))),
        el('div', {class: 'nv-row'}, toggle,
          el('button', {class: 'nv-btn', type: 'button',
            'data-nv-action': 'mcp-test', on: {click: async function () {
              result.hidden = false;
              try {
                var answer = await api('/api/mcp', {action: 'test',
                  scope: server.scope, name: name});
                var report = answer && answer.result || {};
                result.replaceChildren(
                  el('b', {class: report.ok ? 'nv-ok' : 'nv-bad'},
                    report.ok ? tr('Test bestanden') : tr('Test fehlgeschlagen')),
                  el('div', {}, nvText(report.error || report.hint
                    || nvBackend(answer && answer.message) || tr('Test beendet'))));
              } catch (failure) {
                result.replaceChildren(el('b', {class: 'nv-bad'},
                  tr('Test fehlgeschlagen')),
                  el('div', {}, String(failure && failure.message || failure)));
              }
            }}}, tr('Verbindung testen')),
          el('button', {class: 'nv-btn', type: 'button',
            'data-nv-action': 'mcp-edit',
            on: {click: function () { openEdit(server); }}}, tr('Bearbeiten')),
          el('button', {class: 'nv-btn', type: 'button',
            'data-nv-action': 'mcp-delete', on: {click: function () {
              NV.confirmView({title: tr('MCP-Server löschen?'),
                message: name, danger: true, onConfirm: async function () {
                  try {
                    var answer = await api('/api/mcp', {action: 'delete',
                      scope: server.scope, name: name});
                    if (answer && answer.ok === false) {
                      toast(nvBackend(answer.message) || tr('Aktion fehlgeschlagen'));
                      return;
                    }
                    data = await api('/api/mcp') || data;
                    servers = Array.isArray(data.servers) ? data.servers : [];
                    drawServers();
                    toast(nvBackend(answer.message) || tr('MCP-Server gelöscht'));
                  } catch (failure) {
                    toast(tr('Aktion fehlgeschlagen: ')
                      + String(failure && failure.message || failure));
                  }
                }});
            }}}, tr('Löschen'))),
        result));
    });
    applyFilter();
  }
  drawServers();
}

/* ------------------------------------------------------------------------- */
/* 10. Harness                                                                */
/* ------------------------------------------------------------------------- */

async function fillHarness(section, token) {
  var status;
  try { status = await api('/api/harness') || {}; }
  catch (error) { status = {}; }
  if (NV.stale(token)) return;

  var select = el('select', {'data-nv-field': 'harness',
    'aria-label': tr('Harness-Auswahl')});
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
    var nodes = [el('p', {}, String(tr('Aktiver Harness')) + ': '
      + nvText(data.selected))];
    (data.harnesses || []).forEach(function (item) {
      nodes.push(el('div', {class: 'nv-card'},
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
            String(tr('Einrichtungsplan')) + ': '
            + item.install_command.join(' ')) : null));
    });
    statusBox.replaceChildren.apply(statusBox, nodes);
  }
  draw(status);

  var foot = nvActions();
  foot.append(el('button', {class: 'nv-btn nv-primary', type: 'button',
    'data-nv-action': 'harness-use', on: {click: async function () {
      settingsError(error, '');
      try {
        var answer = await api('/api/harness',
          {action: 'use', harness: select.value});
        if (answer && answer.ok) toast(nvBackend(answer.message));
        else settingsError(error, nvBackend(answer && answer.message)
          || tr('Aktion fehlgeschlagen'));
        draw(await api('/api/harness'));
      } catch (failure) {
        settingsError(error, String(failure && failure.message || failure));
      }
    }}}, tr('Harness übernehmen')));
  section.append(nvField(tr('Harness-Auswahl'), select), foot,
    statusBox, error, installFeedback);
}

/* ------------------------------------------------------------------------- */
/* Übersetzungen: Schlüssel sind die deutschen Quelltexte.                    */
/* ------------------------------------------------------------------------- */

var NV_SETTINGS_TEXTS = {
  'Einstellungsbereiche': 'Settings sections',
  'Regeln für alle Projekte und die Projektdateien verwalten.': 'Manage rules for all projects and the project files.',
  'Farben, Sprache und Anzeige der Preise.': 'Colours, language and price display.',
  'Anmeldung und Netzwerk des Dashboards.': 'Dashboard sign-in and network.',
  'Technische Bereiche ein- oder ausblenden.': 'Show or hide technical areas.',
  'Wie neue Agentenläufe mit bestehenden Sitzungen umgehen.': 'How new agent runs deal with existing sessions.',
  'Qualitäts-Schranken global und je Projekt setzen.': 'Set quality guards globally and per project.',
  'Modelle des aktiven Harness und ihre Details.': 'Models of the active harness and their details.',
  'Modellzuordnungen je Rolle verwalten und anwenden.': 'Manage and apply model assignments per role.',
  'Zusätzliche Werkzeuge für Agenten einrichten.': 'Set up additional tools for agents.',
  'Installationsstatus und Auswahl des Agenten-Harness.': 'Installation status and selection of the agent harness.',
  'Globale AGENTS.md': 'Global AGENTS.md',
  'Darstellung': 'Appearance',
  'Zugriffssicherheit': 'Access security',
  'Funktionen': 'Features',
  'Laufverhalten': 'Run behaviour',
  'Schranken': 'Guards',
  'Modelle': 'Models',
  'Profile': 'Profile',
  'MCP-Server': 'MCP servers',
  'Harness': 'Harness',
  'Einstellungen': 'Settings',
  'Klassische Oberfläche öffnen': 'Open classic interface',
  'Speichern': 'Save',
  'Abbrechen': 'Cancel',
  'Sichern': 'Back up',
  'Wiederherstellen': 'Restore',
  'Bearbeiten': 'Edit',
  'Aktiv': 'Active',
  'Inaktiv': 'Inactive',
  'Bestätigen': 'Confirm',
  'Bestätigung': 'Confirmation',
  'Aktion fehlgeschlagen': 'Action failed',
  'Speichern fehlgeschlagen': 'Saving failed',
  'Sichern fehlgeschlagen': 'Backup failed',
  'Vorhanden': 'Present',
  'Datei fehlt': 'File missing',
  'Vorlage anlegen': 'Create template',
  'Vorlage angelegt': 'Template created',
  'Bearbeitungsansicht': 'Edit view',
  'Bearbeitung schließen': 'Close editor',
  'Sicherung auswählen': 'Select backup',
  'Globale AGENTS.md bearbeiten': 'Edit global AGENTS.md',
  'AGENTS.md gespeichert': 'AGENTS.md saved',
  'AGENTS.md gesichert': 'AGENTS.md backed up',
  'AGENTS.md wiederherstellen': 'Restore AGENTS.md',
  'AGENTS.md wiederhergestellt': 'AGENTS.md restored',
  'Die aktuelle Datei wird vorher gesichert. Fortfahren?': 'The current file is backed up first. Continue?',
  'Projektdateien': 'Project files',
  'Datei bearbeiten': 'Edit file',
  'AGENTS.md von ': 'AGENTS.md of ',
  'Der verwaltete Block zwischen den Feldern wird von vibe erzeugt und bleibt unverändert.':
    'The managed block between the fields is generated by vibe and stays unchanged.',
  'Vor dem verwalteten Block': 'Before the managed block',
  'Nach dem verwalteten Block': 'After the managed block',
  'Diese Regeln gelten für alle Projekte; projektbezogene AGENTS.md ergänzen sie.':
    'These rules apply to all projects; project-specific AGENTS.md files add to them.',
  'Hell': 'Light', 'Dunkel': 'Dark', 'System': 'System',
  'Akzent': 'Accent',
  'Blau': 'Blue', 'Türkis': 'Teal', 'Cyan': 'Cyan', 'Grün': 'Green',
  'Limette': 'Lime', 'Gelb': 'Yellow', 'Bernstein': 'Amber',
  'Orange': 'Orange', 'Rot': 'Red', 'Pink': 'Pink',
  'Violett': 'Violet', 'Indigo': 'Indigo',
  'Sprache': 'Language',
  'Sprache auswählen': 'Select language',
  'Währung': 'Currency',
  'Währung auswählen': 'Select currency',
  'USD je 1 EUR': 'USD per 1 EUR',
  'Bitte einen gültigen Umrechnungskurs eingeben.': 'Please enter a valid exchange rate.',
  'Währung gespeichert': 'Currency saved',
  'Preise bleiben in Euro je 1 Mio. Tokens gespeichert und werden nur für die Anzeige umgerechnet.':
    'Prices stay stored in euros per 1 million tokens and are converted for display only.',
  'Anmeldung': 'Sign-in',
  'Neues Passwort': 'New password',
  'neues Passwort (mind. 8 Zeichen)': 'new password (at least 8 characters)',
  'Passwort wiederholen': 'Repeat password',
  'Passwort setzen': 'Set password',
  'Passwort entfernen': 'Remove password',
  'Abmelden': 'Sign out',
  'Kennwort gesetzt': 'Password set',
  'Kennwort entfernt': 'Password removed',
  'Passwörter stimmen nicht überein': 'Passwords do not match',
  'Netzwerk (erweitert)': 'Network (advanced)',
  'Netzwerk-Hinweis': 'Network note',
  'Port': 'Port',
  'Bind-Adresse': 'Bind address',
  'IP-Allowlist': 'IP allowlist',
  'Bitte eine gültige Portnummer eingeben.': 'Please enter a valid port number.',
  'Zugriffssicherheit gespeichert': 'Access security saved',
  'Neustart': 'Restart',
  'Dashboard neu starten': 'Restart dashboard',
  'Neu starten': 'Restart',
  'Das Dashboard wird kurz unterbrochen. Laufende Agentenläufe bleiben erhalten.':
    'The dashboard will be briefly unavailable. Running agent sessions continue.',
  'Neustart fehlgeschlagen': 'Restart failed',
  'Dashboard neu gestartet': 'Dashboard restarted',
  'Der Dashboard-Neustart dauert zu lange.': 'The dashboard restart takes too long.',
  'Änderungen an Port, Bind-Adresse und Allowlist werden gespeichert und erst nach einem Neustart des Dashboards wirksam.':
    'Changes to port, bind address and allowlist are saved and take effect only after a dashboard restart.',
  'Ein neustartpflichtiger Wert wurde gespeichert.': 'A value requiring a restart was saved.',
  'Git & Code': 'Git & code',
  'Modelle & Agenten-Extras': 'Models & agent extras',
  'Laufverhalten (Schalter)': 'Run behaviour (switch)',
  'Technische Bereiche sind standardmäßig ausgeblendet.': 'Technical areas are hidden by default.',
  'GitHub verbinden und Projekte von dort auschecken.': 'Connect GitHub and check out projects from there.',
  'Die AGENTS.md eines Projekts bearbeiten.': 'Edit a project\'s AGENTS.md.',
  'Schreibrechte für jedes Projekt festlegen.': 'Set write permissions for each project.',
  'Modellkatalog und Modellauswahl anzeigen.': 'Show model catalogue and model selection.',
  'Gespeicherte Profile ansehen und übernehmen.': 'View and apply saved profiles.',
  'Zusätzliche MCP-Werkzeuge verwalten.': 'Manage additional MCP tools.',
  'Harness-Status und Auswahl anzeigen.': 'Show harness status and selection.',
  'Fortsetzen oder Stopp für neue Läufe festlegen.': 'Set continue or stop for new runs.',
  'Qualitäts-Schranken global und je Projekt setzen.': 'Set quality guards globally and per project.',
  'Sandbox-Optionen für Projekte anzeigen.': 'Show sandbox options for projects.',
  'Arbeitspakete nach Wichtigkeit sortieren.': 'Sort work packages by priority.',
  'Fortsetzen': 'Continue',
  'Stopp': 'Stop',
  'An = bestehende Sitzung fortsetzen, aus = neue Läufe stoppen.':
    'On = continue an existing session, off = stop new runs.',
  'Fortsetzen lässt neue Läufe an einer vorhandenen Sitzung weiterarbeiten; Stopp beendet neue Läufe, ohne eine Sitzung fortzusetzen. Die Wahl gilt nur für neue Läufe.':
    'Continue (Fortsetzen) lets new runs carry on in an existing session; stop (Stopp) ends new runs without resuming a session. The choice applies only to new runs.',
  'Schranke': 'Guard',
  'Wirkung': 'Effect',
  'Wert': 'Value',
  'Herkunft': 'Origin',
  'Globaler Wert': 'Global value',
  'Projektwert': 'Project value',
  'Wirksam': 'Effective',
  'Global': 'Global',
  'Projekt': 'Project',
  'Standard': 'Default',
  'Umgebung': 'Environment',
  'leer = globaler Wert': 'empty = global value',
  'Weicht ab': 'Differs',
  'Projektabweichungen zurücksetzen': 'Reset project overrides',
  'Gilt nur für ein ausgewähltes Projekt': 'Only applies to a selected project',
  'Schranken gespeichert': 'Guards saved',
  'Ein Projektwert überschreibt den globalen Wert; ohne Projektwert gilt der globale Wert oder der Standardwert.':
    'A project value overrides the global value; without one the global value or default applies.',
  'repair_rounds: Wie oft ein Arbeitspaket nach Fehlern wiederholt wird, bevor es als beendet gilt.':
    'repair_rounds: How often a work package is retried after errors before it is considered done.',
  'assist_rounds: Nach wie vielen nachfolgenden Schritten ein menschlicher Eingriff wiederholt wird.':
    'assist_rounds: After how many following steps a human intervention is requested again.',
  'retries: Wie oft eine fehlgeschlagene Aktion automatisch wiederholt wird.':
    'retries: How often a failed action is retried automatically.',
  'packages: Grenze, wie viele Arbeitspakete pro Lauf anstehen.':
    'packages: Limit of work packages queued per run.',
  'override: Ob der Agent bei Schrankenabbruch fragen (ask) oder abbrechen (off) darf.':
    'override: Whether the agent may ask (ask) or abort (off) on a guard stop.',
  'Modellliste': 'Model list',
  'Aktualisieren': 'Refresh',
  'Aktualisierung fehlgeschlagen': 'Refresh failed',
  'Aktualisierung fehlgeschlagen: ': 'Refresh failed: ',
  'Modelle aktualisiert': 'Models updated',
  'Letzte Aktualisierung': 'Last updated',
  'Anbieter': 'Provider',
  'Preis': 'Price',
  'Quelle': 'Source',
  'Status': 'Status',
  'Fakten': 'Facts',
  'Einschätzungen': 'Assessments',
  'Preisquelle': 'Price source',
  'unbekannt': 'unknown',
  'keine Angaben': 'no data',
  'Keine Modelle vorhanden. Mit „Aktualisieren“ werden die Modelle des Harness geladen.':
    'No models available. Use "Refresh" to load the models of the harness.',
  'Modellkatalog': 'Model catalogue',
  'Katalogstand': 'Catalogue date',
  'Befunde': 'Findings',
  'Quellen': 'Sources',
  'Preise bearbeiten': 'Edit prices',
  'Schließen': 'Close',
  'Default': 'Default',
  'Profil': 'Profile',
  'Standardprofil': 'Standard profile',
  'Profil auswählen': 'Select profile',
  'Name des neuen Profils': 'Name of the new profile',
  'Bitte einen Profilnamen eingeben.': 'Please enter a profile name.',
  'Kostenlos': 'Free tier',
  'Mittel': 'Mid tier',
  'Hoch': 'High tier',
  'Profile': 'Profiles',
  'Neues Profil': 'New profile',
  'Profil löschen': 'Delete profile',
  'Profil löschen?': 'Delete profile?',
  'Profil gelöscht': 'Profile deleted',
  'Profil angelegt': 'Profile created',
  'Profil gespeichert': 'Profile saved',
  'Profile gesichert': 'Profiles backed up',
  'Profile wiederherstellen': 'Restore profiles',
  'Profile wiederhergestellt': 'Profiles restored',
  'Profil anwenden': 'Apply profile',
  'Profilvorschau': 'Profile preview',
  'Profil angewendet': 'Profile applied',
  'Das Default-Profil spiegelt die Modelle der Agent-Einstellungen und ist nicht direkt editierbar.':
    'The default profile mirrors the models of the agent settings and cannot be edited directly.',
  'Keine Rollen zugeordnet.': 'No roles assigned.',
  'Typ': 'Type',
  'Lokal': 'Local',
  'Extern': 'Remote',
  'Name': 'Name',
  'Befehl (ein Argument je Zeile)': 'Command (one argument per line)',
  'Umgebungsvariablen': 'Environment variables',
  'Arbeitsordner': 'Working directory',
  'URL': 'URL',
  'Header': 'Headers',
  'OAuth ausschalten': 'Disable OAuth',
  'Zeitüberschreitung (ms)': 'Timeout (ms)',
  'MCP-Server hinzufügen': 'Add MCP server',
  'MCP-Server bearbeiten': 'Edit MCP server',
  'Hinzufügen': 'Add',
  'Bitte einen Namen eingeben.': 'Please enter a name.',
  'MCP-Server gespeichert': 'MCP server saved',
  'MCP-Server geändert': 'MCP server changed',
  'MCP-Server gelöscht': 'MCP server deleted',
  'MCP-Server löschen?': 'Delete MCP server?',
  'MCP-Server suchen …': 'Search MCP servers …',
  'Alle Bereiche': 'All scopes',
  'Geltungsbereich': 'Scope',
  'Maskierte Werte bleiben unverändert, wenn sie nicht neu eingegeben werden.':
    'Masked values stay unchanged unless entered again.',
  'Verbindung testen': 'Test connection',
  'Verbindungstest läuft': 'Connection test running',
  'Test bestanden': 'Test passed',
  'Test fehlgeschlagen': 'Test failed',
  'Test beendet': 'Test finished',
  'Eintrag konnte nicht geladen werden: ': 'Entry could not be loaded: ',
  'Keine MCP-Server konfiguriert.': 'No MCP servers configured.',
  'Harness-Auswahl': 'Harness selection',
  'Harness übernehmen': 'Apply harness',
  'Aktiver Harness': 'Active harness',
  ' (nicht installiert)': ' (not installed)',
  'Installiert': 'Installed',
  'Nicht installiert': 'Not installed',
  'Installieren': 'Install',
  'Installation fehlgeschlagen': 'Installation failed',
  'Version': 'Version',
  'Offizielle Anleitung': 'Official guide',
  'Einrichtungsplan': 'Setup plan'
};

(function () {
  var en = {}, de = {};
  Object.keys(NV_SETTINGS_TEXTS).forEach(function (key) {
    en[key] = NV_SETTINGS_TEXTS[key];
    de[key] = key;
  });
  VIBE_I18N.extend({en: en, de: de});
})();
