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

  /* Projektliste zuerst, direkt unter der Seitenüberschrift (IA-Fundstück). */
  /* ---------- F33/2b + F34 WP2: Suche über den Projektnamen als NV.search ---------- */
  var searchInput = el('input', {'data-nv-project-search': '',
    placeholder: tr('Projekte suchen'), 'aria-label': tr('Projekte suchen')});
  var searchBox = NV.search({input: searchInput,
    placeholder: tr('Projekte suchen'), oninput: applySearch});
  var searchCount = el('p', {class: 'nv-muted', 'data-nv-search-count': ''});
  var searchRow = el('div', {'data-nv-search-row': ''}, searchBox, searchCount);
  function applySearch() {
    var query = String(searchInput.value || '').trim().toLowerCase();
    var cards = main.querySelectorAll('article[data-nv-project]');
    var n = 0;
    cards.forEach(function (card) {
      var name = String(card.getAttribute('data-nv-project') || '').toLowerCase();
      var match = !query || name.indexOf(query) !== -1;
      if (match) { card.removeAttribute('hidden'); n++; }
      else card.setAttribute('hidden', '');
    });
    /* Die Meldung nennt „n von total“ und endet mit der aktuellen Trefferzahl,
       damit der Zähler nach Eingabe und nach Clear live ablesbar bleibt. */
    setTx(searchCount, tr('{{n}} von {{total}} · Treffer {{n}}',
      {n: n, total: cards.length}));
  }

  /* ---------- F33/2b: Anheften: ★/☆-Knopf per Karte, storage, Sektion ---------- */
  var pinnedSection = el('section', {class: 'nv-section nv-pinned-projects',
    'data-nv-pinned-projects': ''}, el('h2', {}, tr('Angeheftet')));
  var pinnedGrid = el('div', {class: 'nv-grid', 'data-nv-pinned-grid': ''});
  pinnedSection.append(pinnedGrid);
  var grid = el('div', {class: 'nv-grid'});

  function readPinnedProjects() {
    return NV.favoriteProjects();
  }
  function writePinnedProjects(names) {
    NV.setFavoriteProjects(names);
  }
  function toggleProjectPin(card) {
    var name = String(card.getAttribute('data-nv-project') || '');
    var pinned = readPinnedProjects();
    var idx = pinned.indexOf(name);
    if (idx === -1) pinned.push(name); else pinned.splice(idx, 1);
    writePinnedProjects(pinned);
    updatePins();
  }
  function updatePins() {
    var pinned = readPinnedProjects();
    document.querySelectorAll('article[data-nv-project]').forEach(function (card) {
      var name = String(card.getAttribute('data-nv-project') || '');
      var isPinned = pinned.indexOf(name) !== -1;
      var pin = card.querySelector('[data-nv-action="project-pin"]');
      if (pin) {
        pin.setAttribute('aria-pressed', isPinned ? 'true' : 'false');
        setAttrTx(pin, 'aria-label', isPinned ? 'Projekt abheften' : 'Projekt anheften');
        setTx(pin, tr(isPinned ? '★' : '☆'));
      }
      var target = isPinned ? pinnedGrid : grid;
      if (card.parentNode !== target) {
        /* Das Raster misst die Karten direkt nach dem Pin. Das Umsetzen im
           DOM startet die Slide-in-Animation neu und verschiebt eine Karte
           vorübergehend um einige Pixel — im Raster sollen beide gleich hoch
           sitzen. */
        card.style.animation = 'none';
        target.append(card);
      }
    });
  }
  projects.forEach(function (row) {
    var name = String(row.name || '');
    var state = row.running ? 'running' : 'stopped';
    var label = row.running ? tr('läuft') : tr('gestoppt');
    var open = function () { NV.navigate('#/project/' + encodeURIComponent(name)); };
    var isPinned = readPinnedProjects().indexOf(name) !== -1;
    var pin = el('button', {type: 'button', 'data-nv-action': 'project-pin',
      'aria-pressed': isPinned ? 'true' : 'false',
      on: {click: function (event) { event.stopPropagation(); toggleProjectPin(card); }}},
      tr(isPinned ? '★' : '☆'));
    var rowStyle = 'gap: var(--nv-space-3); margin-bottom: var(--nv-space-3)';
    var card = el('article', {class: 'nv-card nv-project', 'data-nv-project': name,
      on: {click: open}},
      el('div', {class: 'nv-row', style: rowStyle},
        el('h3', {class: 'nv-project-name'}, name),
        el('span', {class: 'nv-pill', 'data-nv-run-state': '', 'data-state': state}, label),
        el('span', {class: 'nv-pill nv-type', 'data-nv-type': ''}, String(row.type || ''))),
      el('div', {class: 'nv-row nv-muted nv-project-meta', style: rowStyle},
        el('span', {}, tr('Offene Arbeitspakete') + ': '),
        el('span', {'data-nv-open-count': ''}, String(row.open == null ? 0 : row.open))),
      row.pause_after ? el('span', {class: 'nv-pill nv-warn', 'data-nv-pause-badge': ''}, tr(' Pause')) : null,
      el('div', {class: 'nv-row', style: rowStyle},
        el('a', {class: 'nv-btn nv-secondary', 'data-nv-action': 'open-project',
          href: '#/project/' + encodeURIComponent(name)}, tr('Öffnen'))));
    card.append(pin);
    (isPinned ? pinnedGrid : grid).append(card);
  });
  if (!projects.length) {
    grid.append(el('p', {class: 'nv-muted'}, tr('Keine Projekte gefunden. Entwicklungsordner unten hinzufügen.')));
  }
  var projectsSection = el('section', {class: 'nv-section nv-projects-section',
    'data-nv-projects': ''}, el('h2', {}, tr('Projekte')), grid);

  /* Einstiegshinweis: kompaktes Banner mit Schritt-Chips, dauerhaft schließbar
     über einen echten kleinen Knopf (nicht über einen Text-Link). */
  var guideCard = null;
  if (!localStorage.getItem('nv-guide-dismissed')) {
    guideCard = el('section', {class: 'nv-card nv-guide', 'data-nv-guide': ''},
      el('div', {class: 'nv-guide-head'},
        el('span', {class: 'nv-guide-label'}, tr('Erste Schritte')),
        el('button', {class: 'nv-btn nv-ghost nv-close nv-guide-close', type: 'button',
          'data-nv-guide-dismiss': '',
          'aria-label': tr('Hinweis schließen'), title: tr('Hinweis schließen'),
          on: {click: function () {
            localStorage.setItem('nv-guide-dismissed', '1');
            if (guideCard) guideCard.remove();
          }}}, '×')),
      el('div', {class: 'nv-guide-steps'},
        el('span', {class: 'nv-chip'}, tr('Projektordner verbinden')),
        el('span', {class: 'nv-chip'}, tr('Projekt anlegen oder öffnen')),
        el('span', {class: 'nv-chip'}, tr('Arbeit starten'))));
  }

  /* Schnellaktionen: unter den Projekten und bewusst secondary gehalten,
     damit die Neuanlage der einzige primäre Knopf der Seite bleibt. */
  var quickCard = el('section', {class: 'nv-card nv-card-secondary nv-quick', 'data-nv-quick': ''},
    el('h2', {}, tr('Schnellaktionen')),
    el('div', {class: 'nv-row'},
      el('button', {class: 'nv-btn nv-secondary', type: 'button', on: {click: function () {
        var input = main.querySelector('[data-nv-new-project] input[data-nv-field="name"]');
        if (input) { input.focus(); input.scrollIntoView({block: 'center'}); }
      }}}, tr('Neues Projekt')),
      el('button', {class: 'nv-btn nv-ghost', type: 'button',
        on: {click: function () { NV.navigate('#/agents'); }}}, tr('Neuer Agent')),
      el('button', {class: 'nv-btn nv-ghost', type: 'button',
        on: {click: function () { NV.navigate('#/activity'); }}}, tr('Fragen beantworten'))));

  /* Neuanlage: Typen kommen aus /api/types, danach geht es in den Assistenten.
     Das Formular bleibt sichtbar (die Tests lesen das Typ-Feld direkt), steht
     aber in einer deutlich untergeordneten Karte. */
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
  var newProjectCard = el('section', {class: 'nv-card nv-card-secondary', 'data-nv-new-project': ''},
    el('h2', {}, tr('Neues Projekt (im Standardordner)')),
    el('label', {}, tr('Name')), nameInput,
    el('label', {}, tr('Typ')), typeSelect,
    el('div', {class: 'nv-row'}, createButton), newError);

  /* Auschecken ist technisch und bleibt hinter dem Feature github verborgen. */
  var cloneCard = null;
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
    cloneCard = el('section', {class: 'nv-card nv-card-secondary', 'data-nv-clone': ''},
      el('h2', {}, tr('Aus GitHub auschecken')),
      el('label', {}, tr('GitHub-Adresse zum Auschecken')), urlInput,
      el('div', {class: 'nv-row'}, cloneButton), cloneError);
  }

  /* Entwicklungsordner: Zeilen mit Entfernen, Eingabe und Neu-einlesen.
     Lange Pfade werden auf den Ordnernamen gekürzt; der volle Pfad steht im
     title-Attribut und bleibt als <code> markierbar. */
  var rootError = nvErrorBox();
  var rootInput = el('input', {'data-nv-field': 'root',
    placeholder: tr('/var/mnt/data/.../mein-entwicklungsordner'), 'aria-label': tr('Entwicklungsordner')});
  var rootList = el('div', {class: 'nv-list'});
  function drawRoots(rows) {
    rootList.replaceChildren.apply(rootList, rows.map(function (row) {
      var path = String(row.path || '');
      var parts = path.split('/').filter(Boolean);
      var base = parts.length ? parts[parts.length - 1] : path;
      var shown = parts.length > 1 ? '…/' + base : base;
      return el('div', {class: 'nv-root-row', 'data-nv-root': path},
        el('code', {class: 'nv-root-path', title: path}, shown),
        row.fixed ? el('span', {class: 'nv-pill nv-type'}, tr('Standardliste')) : null,
        el('button', {class: 'nv-btn nv-ghost nv-compact', type: 'button',
          'data-nv-action': 'root-remove', 'aria-label': tr('entfernen'), title: tr('entfernen'),
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
  var rootsCard = el('section', {class: 'nv-card nv-card-secondary', 'data-nv-roots': ''},
    el('h2', {}, tr('Entwicklungsordner')),
    rootList,
    el('label', {}, tr('Ordner hinzufügen')), rootInput,
    el('div', {class: 'nv-row'}, addRoot, scanRoots), rootError);

  var ordered = [searchRow, pinnedSection, projectsSection];
  if (guideCard) ordered.push(guideCard);
  ordered.push(quickCard, newProjectCard);
  if (cloneCard) ordered.push(cloneCard);
  ordered.push(rootsCard);
  main.replaceChildren(el('h2', {class: 'nv-page-title'}, tr('Start')), ...ordered);
  applySearch();
  NV.refreshBell();
};

/* F34 WP2: neue Texte dieser Ansicht (Schlüssel = deutscher Quelltext). */
if (window.VIBE_I18N && typeof VIBE_I18N.extend === 'function') {
  VIBE_I18N.extend({
    en: {'{{n}} von {{total}} · Treffer {{n}}': '{{n}} of {{total}} · hits {{n}}'},
    de: {'{{n}} von {{total}} · Treffer {{n}}': '{{n}} von {{total}} · Treffer {{n}}'}
  });
}
