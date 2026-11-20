/* AP22 — Startseite: Projektkarten, Einstiegshinweis, Neuanlage, Klonen
   (Feature github) und Entwicklungsordner. Alle Fehler erscheinen in der
   jeweiligen Karte unter [data-nv-form-error] und zusätzlich als Toast. */
'use strict';

function nvErrorBox() {
  return el('div', {class: 'nv-form-error', 'data-nv-form-error': '', hidden: ''});
}

function nvShowError(box, message) {
  var text = String(message || '');
  box.textContent = text;
  if (text) box.removeAttribute('hidden'); else box.setAttribute('hidden', '');
  if (text) toast(bt(text));
}

NV.views.home = async function home(context, token) {
  var projects = [];
  var types = [];
  var roots = [];
  try {
    var data = await Promise.all([
      api('/api/projects'), api('/api/types'), api('/api/roots')
    ]);
    projects = data[0] || [];
    types = data[1] || [];
    roots = data[2] || [];
  } catch (error) {
    if (NV.stale(token)) return;
    document.getElementById('nv-main').replaceChildren(
      el('section', {class: 'nv-card'}, el('h2', {}, tr('Start')),
        el('p', {class: 'nv-form-error', 'data-nv-form-error': ''},
          tr('Daten konnten nicht geladen werden: ') + String(error && error.message || error))));
    return;
  }
  if (NV.stale(token)) return;

  var main = document.getElementById('nv-main');
  var cards = [];

  /* Einstiegshinweis: einmal schließen, dauerhaft im Browser merken. */
  if (!localStorage.getItem('nv-guide-dismissed')) {
    var guide = el('section', {class: 'nv-card nv-guide', 'data-nv-guide': ''},
      el('h2', {}, tr('Erste Schritte')),
      el('ol', {},
        el('li', {}, tr('Projektordner verbinden')),
        el('li', {}, tr('Projekt anlegen oder öffnen')),
        el('li', {}, tr('Arbeit starten'))),
      el('button', {class: 'nv-btn nv-ghost', type: 'button', 'data-nv-guide-dismiss': '',
        on: {click: function () {
          localStorage.setItem('nv-guide-dismissed', '1');
          guide.remove();
        }}}, tr('Hinweis schließen')));
    cards.push(guide);
  }

  /* Schnellaktionen: wenige Klicks zu den häufigsten Zielen. */
  cards.push(el('section', {class: 'nv-card', 'data-nv-quick': ''},
    el('h2', {}, tr('Schnellaktionen')),
    el('div', {class: 'nv-row'},
      el('button', {class: 'nv-btn nv-primary', type: 'button', on: {click: function () {
        var input = main.querySelector('[data-nv-new-project] input[data-nv-field="name"]');
        if (input) { input.focus(); input.scrollIntoView({block: 'center'}); }
      }}}, tr('Neues Projekt')),
      el('button', {class: 'nv-btn', type: 'button',
        on: {click: function () { NV.navigate('#/agents'); }}}, tr('Neuer Agent')),
      el('button', {class: 'nv-btn', type: 'button',
        on: {click: function () { NV.navigate('#/activity'); }}}, tr('Fragen beantworten')))));

  /* Projektliste. */
  var grid = el('div', {class: 'nv-grid', 'data-nv-projects': ''});
  projects.forEach(function (row) {
    var name = String(row.name || '');
    var state = row.running ? 'running' : 'stopped';
    var label = row.running ? tr('läuft') : tr('gestoppt');
    var card = el('article', {class: 'nv-card nv-project', 'data-nv-project': name},
      el('div', {class: 'nv-row'},
        el('h3', {class: 'nv-project-name', on: {click: function () {
          NV.navigate('#/project/' + encodeURIComponent(name));
        }}}, name),
        el('span', {class: 'nv-pill', 'data-nv-run-state': '', 'data-state': state}, label),
        el('span', {class: 'nv-pill nv-type', 'data-nv-type': ''}, String(row.type || ''))),
      el('div', {class: 'nv-row nv-muted'},
        el('span', {}, tr('Offene Pakete') + ': '),
        el('span', {'data-nv-open-count': ''}, String(row.open == null ? 0 : row.open))),
      row.pause_after ? el('span', {class: 'nv-pill nv-warn', 'data-nv-pause-badge': ''}, tr(' Pause')) : null,
      el('a', {class: 'nv-btn nv-primary', 'data-nv-action': 'open-project',
        href: '#/project/' + encodeURIComponent(name)}, tr('Öffnen')));
    grid.append(card);
  });
  if (!projects.length) {
    grid.append(el('p', {class: 'nv-muted'}, tr('Keine Projekte gefunden. Entwicklungsordner unten hinzufügen.')));
  }
  cards.push(el('section', {class: 'nv-section'}, el('h2', {}, tr('Projekte')), grid));

  /* Neuanlage: Typen kommen aus /api/types, danach geht es in den Assistenten. */
  var nameInput = el('input', {'data-nv-field': 'name',
    placeholder: tr('projektname (a-z, 0-9, -)'), 'aria-label': tr('Name')});
  var typeSelect = el('select', {'data-nv-field': 'type', 'aria-label': tr('Typ')});
  var typeValues = types.map(function (item) {
    return typeof item === 'string' ? item : String(item && (item.type || item.name) || '');
  }).filter(Boolean);
  if (!typeValues.length) typeValues = ['generic'];
  typeValues.forEach(function (value) {
    typeSelect.append(el('option', {value: value}, value));
  });
  var newError = nvErrorBox();
  var createButton = el('button', {class: 'nv-btn nv-primary', type: 'button',
    'data-nv-action': 'create-project', on: {click: async function () {
      var value = String(nameInput.value || '').trim();
      nvShowError(newError, '');
      if (!value) { nvShowError(newError, tr('Name fehlt')); return; }
      createButton.disabled = true;
      try {
        var result = await api('/api/new', {name: value, type: typeSelect.value});
        if (result.ok) {
          NV.navigate('#/project/' + encodeURIComponent(value) + '/assistant');
        } else {
          nvShowError(newError, bt(result.message) || tr('Anlegen fehlgeschlagen'));
        }
      } catch (error) {
        nvShowError(newError, tr('Anlegen fehlgeschlagen: ') + String(error && error.message || error));
      } finally {
        createButton.disabled = false;
      }
    }}}, tr('Anlegen'));
  cards.push(el('section', {class: 'nv-card', 'data-nv-new-project': ''},
    el('h2', {}, tr('Neues Projekt (im Standardordner)')),
    el('label', {}, tr('Name')), nameInput,
    el('label', {}, tr('Typ')), typeSelect,
    el('div', {class: 'nv-row'}, createButton), newError));

  /* Auschecken ist technisch und bleibt hinter dem Feature github verborgen. */
  if (NV.feature('github')) {
    var urlInput = el('input', {'data-nv-field': 'url',
      placeholder: tr('GitHub-Adresse zum Auschecken'), 'aria-label': tr('GitHub-Adresse zum Auschecken')});
    var cloneError = nvErrorBox();
    var cloneButton = el('button', {class: 'nv-btn', type: 'button',
      'data-nv-action': 'clone', on: {click: async function () {
        nvShowError(cloneError, '');
        cloneButton.disabled = true;
        try {
          var result = await api('/api/clone', {url: String(urlInput.value || '').trim()});
          if (result.ok) {
            toast(bt(result.message) || tr('Projekt ausgecheckt'));
            NV.render();
          } else {
            nvShowError(cloneError, bt(result.message) || tr('Auschecken fehlgeschlagen'));
          }
        } catch (error) {
          nvShowError(cloneError, tr('Auschecken fehlgeschlagen: ') + String(error && error.message || error));
        } finally {
          cloneButton.disabled = false;
        }
      }}}, tr('Auschecken'));
    cards.push(el('section', {class: 'nv-card', 'data-nv-clone': ''},
      el('h2', {}, tr('Aus GitHub auschecken')),
      el('label', {}, tr('GitHub-Adresse zum Auschecken')), urlInput,
      el('div', {class: 'nv-row'}, cloneButton), cloneError));
  }

  /* Entwicklungsordner: Zeilen mit Entfernen, Eingabe und Neu-einlesen. */
  var rootError = nvErrorBox();
  var rootInput = el('input', {'data-nv-field': 'root',
    placeholder: tr('/var/mnt/data/.../mein-entwicklungsordner'), 'aria-label': tr('Entwicklungsordner')});
  var rootList = el('div', {class: 'nv-list'});
  function drawRoots(rows) {
    rootList.replaceChildren.apply(rootList, rows.map(function (row) {
      var path = String(row.path || '');
      return el('div', {class: 'nv-row', 'data-nv-root': path},
        el('span', {}, path + (row.fixed ? ' (' + tr('Standardliste') + ')' : '')),
        el('button', {class: 'nv-btn nv-ghost', type: 'button', 'data-nv-action': 'root-remove',
          on: {click: async function () {
            try {
              var result = await api('/api/roots', {action: 'remove', path: path});
              if (!result.ok) nvShowError(rootError, bt(result.message));
              NV.render();
            } catch (error) { nvShowError(rootError, String(error && error.message || error)); }
          }}}, tr('entfernen')));
    }));
  }
  drawRoots(roots);
  var addRoot = el('button', {class: 'nv-btn', type: 'button', 'data-nv-action': 'root-add',
    on: {click: async function () {
      nvShowError(rootError, '');
      try {
        var result = await api('/api/roots', {action: 'add', path: String(rootInput.value || '').trim()});
        if (result.ok) { rootInput.value = ''; NV.render(); }
        else nvShowError(rootError, bt(result.message) || tr('Ordner konnte nicht hinzugefügt werden'));
      } catch (error) {
        nvShowError(rootError, tr('Ordner konnte nicht hinzugefügt werden: ') + String(error && error.message || error));
      }
    }}}, tr('Ordner hinzufügen'));
  var scanRoots = el('button', {class: 'nv-btn', type: 'button', 'data-nv-action': 'root-scan',
    on: {click: async function () {
      try {
        var result = await api('/api/roots', {action: 'scan'});
        if (result.ok) NV.render();
        else nvShowError(rootError, bt(result.message));
      } catch (error) { nvShowError(rootError, String(error && error.message || error)); }
    }}}, tr('Neu einlesen'));
  cards.push(el('section', {class: 'nv-card', 'data-nv-roots': ''},
    el('h2', {}, tr('Entwicklungsordner')),
    rootList,
    el('label', {}, tr('Ordner hinzufügen')), rootInput,
    el('div', {class: 'nv-row'}, addRoot, scanRoots), rootError));

  main.replaceChildren(el('h2', {}, tr('Start')), ...cards);
  NV.refreshBell();
};
