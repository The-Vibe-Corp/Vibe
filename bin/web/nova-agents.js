/* F33 — Agenten: Liste, geführter Wizard und Ein-Seiten-Editor.
 *
 * Die Hooks folgen docs/features/F33.md und dem Moduldocstring von
 * tests/browser/test_f33_agents_ui.py. Die bestehende API wird unverändert
 * konsumiert (selbe Payloads wie die klassische Oberfläche in app.js).
 */
'use strict';

/* F33 WP2: falls WP1 den <script>-Tag in index.html noch nicht ergänzt hat,
   wird nova-widgets.js beim Start nachgeladen, damit NV.combobox sofort
   verfügbar ist. Dynamisch eingefügte Skripte blockieren das Load-Event
   während des Ladens, weshalb der Wizard sie nutzen kann, sobald die Seite
   offen ist. */
(function () {
  if (!(window.NV && typeof NV.combobox === 'function')
      && !document.querySelector('script[src="/static/nova-widgets.js"]')) {
    var script = document.createElement('script');
    script.src = '/static/nova-widgets.js';
    document.head.appendChild(script);
  }
})();

/* /api/agents liefert "roles" nur als Zuordnung Agent → Rolle, nicht als
   Katalog. Die Auswahl kommt deshalb aus bin/vibe ROLE_NAMES. */
var NV_AGENT_ROLES = ['coder', 'reviewer', 'vibe', 'tester', 'analyst',
  'sonstiges', 'content-creator'];
var NV_AGENT_MODES = ['subagent', 'primary', 'all'];

/* Der Kernrouter kennt nur eine Route-Parameterstelle (#/agents/<name>). Der
   Geltungsbereich wird deshalb hier aus dem Hash gelesen:
   #/agents/<scope>/<name> → scope+name, #/agents/<name> → global (Rückwärts-
   kompatibel mit den Bestandsfällen). */
function nvAgentRoute() {
  var raw = (location.hash || '').replace(/^#\/?/, '');
  var parts = raw.split('/').filter(function (part) { return !!part; });
  var decode = function (value) {
    try { return decodeURIComponent(value); } catch (e) { return value; }
  };
  if (parts[0] !== 'agents' || !parts[1]) return {scope: 'global', name: null};
  if (parts.length >= 3) return {scope: decode(parts[1]), name: decode(parts[2])};
  return {scope: 'global', name: decode(parts[1])};
}

function nvAgentErrorBox() {
  return el('div', {class: 'nv-form-error', 'data-nv-form-error': '', hidden: ''});
}

function nvAgentError(box, message) {
  var text = message == null ? '' : String(message);
  box.textContent = bt(text);
  if (text) { box.removeAttribute('hidden'); toast(bt(text)); }
  else box.setAttribute('hidden', '');
}

function nvAgentMessage(result) {
  return bt(result && result.message) || tr('Aktion fehlgeschlagen');
}

function nvAgentSelect(values, current, blank) {
  var select = el('select', {});
  if (blank) select.append(el('option', {value: ''}, blank));
  values.forEach(function (value) {
    select.append(el('option', {value: String(value)}, String(value)));
  });
  if (current) select.value = String(current);
  return select;
}

/* ---------- Einstieg: Liste oder Editor je Route ---------- */

NV.views.agents = async function agents(context, token) {
  var main = document.getElementById('nv-main');
  var route = nvAgentRoute();
  var wanted = {wizard: false};
  if (!route.name) {
    /* Der Rahmen steht sofort: Die Route ist mit dem data-nv-view-Attribut
       sichtbar, bevor die API-Antwort eintrifft. Ohne diesen Rahmen greift
       ein Test (oder ein Nutzer) in einen noch leeren Views-Container. */
    main.replaceChildren(
      el('div', {class: 'nv-toolbar nv-agents-toolbar'},
        el('h2', {class: 'nv-page-title'}, tr('Agenten')),
        el('button', {class: 'nv-btn nv-primary', type: 'button',
          'data-nv-action': 'agent-new', on: {click: function () {
            wanted.wizard = true;
          }}}, tr('Neuer Agent'))),
      el('section', {class: 'nv-section'},
        el('div', {class: 'nv-grid', 'data-nv-agent-list': ''}),
        el('p', {class: 'nv-muted'}, tr('Agenten werden geladen …'))));
  }
  var data;
  try {
    data = await api('/api/agents');
  } catch (error) {
    if (NV.stale(token)) return;
    main.replaceChildren(el('section', {class: 'nv-card'},
      el('h2', {class: 'nv-page-title'}, tr('Agenten')),
      el('p', {class: 'nv-form-error', 'data-nv-form-error': ''},
        tr('Agenten konnten nicht geladen werden: ')
          + String(error && error.message || error))));
    NV.refreshBell();
    return;
  }
  if (NV.stale(token)) return;
  if (route.name) await nvAgentEditor(route.name, route.scope, data, token);
  else nvAgentList(data, token, wanted);
  if (!NV.stale(token)) NV.refreshBell();
};

/* ---------- Liste (2c/2h/2i): Anpinnen, Suche, Tag-Filter ---------- */

function nvAgentPinned() {
  try {
    var raw = localStorage.getItem('nv-pinned-agents');
    var items = raw ? JSON.parse(raw) : [];
    return Array.isArray(items) ? items : [];
  } catch (error) {
    return [];
  }
}

function nvAgentPinStore(items) {
  localStorage.setItem('nv-pinned-agents', JSON.stringify(items));
}

function nvAgentList(data, token, wanted) {
  var main = document.getElementById('nv-main');
  var rows = data.agents || [];
  var searchQuery = '';
  var activeFilters = [];
  var list = el('div', {class: 'nv-grid', 'data-nv-agent-list': ''});
  var pinnedSection = el('section', {class: 'nv-agent-pinned',
    'data-nv-pinned-agents': ''});
  /* Die Suche bleibt über denselben Input erreichbar (data-nv-agent-search),
     wird aber vom gemeinsamen NV.search-Widget gerendert. */
  var searchInput = el('input', {'data-nv-agent-search': '',
    'aria-label': tr('Agenten suchen'), placeholder: tr('Agenten suchen …')});
  var searchBox = NV.search({input: searchInput,
    placeholder: tr('Agenten suchen …'), oninput: function (value) {
      searchQuery = String(value || '');
      renderList();
    }});
  var toolbar = el('div', {class: 'nv-toolbar nv-agents-toolbar'},
    el('h2', {class: 'nv-page-title'}, tr('Agenten')),
    el('div', {'data-nv-agent-search': ''}, searchBox),
    el('button', {class: 'nv-btn nv-primary', type: 'button',
      'data-nv-action': 'agent-new', on: {click: showWizard}}, tr('Neuer Agent')));
  var listSection = el('section', {class: 'nv-section'}, list);
  var wizard = null;

  /* Anpinn-Status: über localStorage['nv-pinned-agents'] ([{scope,name}]). */
  function isPinned(row) {
    return nvAgentPinned().some(function (item) {
      return item && item.name === row.name && item.scope === row.scope;
    });
  }

  function nvAgentTogglePin(row) {
    var pinned = nvAgentPinned();
    var index = pinned.findIndex(function (item) {
      return item.name === row.name && item.scope === row.scope;
    });
    if (index >= 0) pinned.splice(index, 1);
    else pinned.push({scope: row.scope, name: row.name});
    nvAgentPinStore(pinned);
    renderList();
  }

  /* Live-Suche über Name/Beschreibung (Teilstring, case-insensitiv). */
  function searchMatches(row) {
    var needle = searchQuery.toLowerCase();
    if (!needle) return true;
    return String(row.name || '').toLowerCase().indexOf(needle) >= 0
      || String(row.description || '').toLowerCase().indexOf(needle) >= 0;
  }

  /* Tag-Filter: scope (Global/Projekt), Rolle, Vibe-Agent, ungültig.
     Filter und Suche kombinieren sich (UND); erneuter Klick hebt aus. */
  var filterChips = (function () {
    var chips = [
      {id: 'scope:global', kind: 'scope', value: 'global', label: tr('Global')},
      {id: 'scope:project', kind: 'scope', value: 'project', label: tr('Projekt')}
    ];
    rows.forEach(function (row) {
      var id = 'role:' + row.role;
      if (row.role && !chips.some(function (chip) { return chip.id === id; })) {
        chips.push({id: id, kind: 'role', value: String(row.role),
          label: String(row.role)});
      }
    });
    if (rows.some(function (row) { return row.is_vibe; })) {
      chips.push({id: 'vibe', kind: 'vibe', value: 'vibe', label: tr('Vibe-Agent')});
    }
    if (rows.some(function (row) { return row.valid === false; })) {
      chips.push({id: 'invalid', kind: 'invalid', value: 'invalid',
        label: tr('ungültig')});
    }
    return chips;
  })();

  function isActiveFilter(id) {
    return activeFilters.some(function (item) { return item.id === id; });
  }

  function toggleFilter(id) {
    var index = activeFilters.findIndex(function (item) { return item.id === id; });
    if (index >= 0) activeFilters.splice(index, 1);
    else {
      var chip = filterChips.find(function (item) { return item.id === id; });
      if (chip) activeFilters.push(chip);
    }
    renderList();
    tagFilters.querySelectorAll('[data-nv-tag-filter]').forEach(function (button) {
      var pressed = isActiveFilter(button.getAttribute('data-nv-tag-filter'));
      button.setAttribute('aria-pressed', pressed ? 'true' : 'false');
    });
  }

  function tagFilterMatches(row) {
    var index;
    for (index = 0; index < activeFilters.length; index++) {
      var chip = activeFilters[index];
      if (chip.kind === 'scope') {
        if (chip.value === 'global' && row.scope !== 'global') return false;
        if (chip.value === 'project' && row.scope === 'global') return false;
      } else if (chip.kind === 'role') {
        if (String(row.role || '') !== chip.value) return false;
      } else if (chip.kind === 'vibe') {
        if (!row.is_vibe) return false;
      } else if (chip.kind === 'invalid') {
        if (row.valid !== false) return false;
      }
    }
    return true;
  }

  var tagFilters = el('div', {class: 'nv-agent-tag-filters',
    'data-nv-agent-tag-filters': ''},
    filterChips.map(function (chip) {
      return el('button', {class: 'nv-tag-filter', type: 'button',
        'data-nv-tag-filter': chip.id,
        'aria-pressed': isActiveFilter(chip.id) ? 'true' : 'false',
        on: {click: function () { toggleFilter(chip.id); }}}, chip.label);
    }));
  listSection.prepend(tagFilters);

  function nvAgentCard(row) {
    var name = String(row.name || '');
    var scope = String(row.scope || 'global');
    var description = String(row.description || '');
    var shown = description.length > 120 ? description.slice(0, 117) + '…' : description;
    var tags = [];
    if (row.role) tags.push(el('span', {class: 'nv-chip'}, String(row.role)));
    if (row.is_vibe) tags.push(el('span', {class: 'nv-chip'}, tr('Vibe-Agent')));
    if (row.valid === false) tags.push(el('span', {class: 'nv-chip'}, tr('ungültig')));
    if (!tags.length) tags.push(el('span', {class: 'nv-chip'}, tr('keine Rolle')));
    var editRoute = scope === 'global'
      ? '#/agents/' + encodeURIComponent(name)
      : '#/agents/' + encodeURIComponent(scope) + '/' + encodeURIComponent(name);
    var deleteConfirm = el('div', {class: 'nv-confirm', 'data-nv-confirm': '', hidden: ''},
      el('p', {class: 'nv-muted'}, tr('Diesen Agenten löschen? Eine Sicherung bleibt erhalten.')),
      el('button', {class: 'nv-btn nv-danger', type: 'button',
        on: {click: async function () {
          try {
            var result = await api('/api/agent', {
              action: 'delete', scope: scope, name: name});
            if (!result.ok) { toast(bt(result.message) || tr('Löschen fehlgeschlagen.')); return; }
            toast(bt(result.message) || tr('Agent gelöscht'));
            if (!NV.stale(token)) { NV.render(); }
          } catch (error) {
            toast(tr('Löschen fehlgeschlagen: ') + String(error && error.message || error));
          }
        }}}, tr('Ja, löschen')));
    var pinned = isPinned(row);
    var pinLabel = pinned ? 'Lösen' : 'Anpinnen';
    var pin = el('button', {class: 'nv-btn nv-pin', type: 'button',
      'data-nv-action': 'agent-pin',
      'aria-pressed': pinned ? 'true' : 'false', style: 'flex: 0 0 auto',
      on: {click: function () { nvAgentTogglePin(row); }}});
    setAttrTx(pin, 'aria-label', pinLabel);
    setAttrTx(pin, 'title', pinLabel);
    setTx(pin, tr(pinned ? '★' : '☆'));
    return el('article', {class: 'nv-card nv-agent', 'data-nv-agent': name,
      'data-nv-agent-scope': scope},
      el('div', {class: 'nv-row nv-agent-name-row'},
        el('h3', {class: 'nv-agent-name'}, name),
        pin),
      el('div', {class: 'nv-agent-meta',
        style: 'display:flex; flex-wrap:wrap; align-items:center; min-width:0; '
          + 'gap:var(--nv-space-2); margin-bottom:var(--nv-space-2)'},
        el('span', {class: 'nv-pill', 'data-nv-agent-scope-badge': ''},
          scope === 'global' ? tr('Global') : tr('Projekt') + ': ' + scope),
        el('span', {class: 'nv-pill', 'data-nv-role': ''}, String(row.role || tr('keine Rolle'))),
        row.is_vibe ? el('span', {class: 'nv-pill nv-type'}, tr('Vibe-Agent')) : null,
        row.valid === false
          ? el('span', {class: 'nv-pill nv-warn', title: tr('Datei ist kein gültiger Agent')},
            tr('ungültig'))
          : null,
        el('div', {class: 'nv-agent-tags', 'data-nv-agent-tags': '',
          style: 'flex: 1 1 100%'}, tags)),
      el('p', {class: 'nv-muted', title: description}, shown || tr('Keine Beschreibung')),
      el('div', {class: 'nv-row nv-muted'},
        el('span', {}, tr('Modell') + ': '),
        el('span', {}, String(row.model || '—'))),
      el('div', {class: 'nv-row nv-agent-actions'},
        el('button', {class: 'nv-btn nv-primary', type: 'button',
          'data-nv-action': 'agent-edit', on: {click: function () {
            NV.navigate(editRoute);
          }}}, tr('Bearbeiten')),
        el('button', {class: 'nv-btn nv-danger', type: 'button',
          'data-nv-action': 'agent-delete', on: {click: function () {
            deleteConfirm.hidden = false;
          }}}, tr('Löschen'))),
      deleteConfirm);
  }

  function renderList() {
    var pinnedRows = rows.filter(function (row) {
      return isPinned(row);
    });
    list.replaceChildren();
    rows.forEach(function (row) {
      if (isPinned(row) || !searchMatches(row) || !tagFilterMatches(row)) return;
      list.append(nvAgentCard(row));
    });
    if (!list.children.length) {
      list.append(el('p', {class: 'nv-muted'}, tr('Noch keine Agenten vorhanden.')));
    }
    pinnedSection.replaceChildren.apply(pinnedSection,
      [el('h3', {class: 'nv-page-title'}, tr('Angeheftete Agenten'))]
        .concat(pinnedRows.map(nvAgentCard)));
    pinnedSection.hidden = !pinnedRows.length;
    main.replaceChildren(toolbar, pinnedSection, listSection, wizard);
  }

  function showList() {
    if (wizard) wizard.hidden = true;
    listSection.hidden = false;
    toolbar.hidden = false;
  }
  function showWizard() {
    toolbar.hidden = true;
    listSection.hidden = true;
    wizard.hidden = false;
    wizard.querySelector('[data-nv-field="name"]').focus();
  }

  wizard = nvAgentWizard(data, token, showList);
  renderList();
  // Ein Klick auf den Rahmen-Button vor der API-Antwort darf nicht verloren gehen.
  if (wanted && wanted.wizard) { wanted.wizard = false; showWizard(); }
}

/* ---------- Wizard (5 Schritte, eine Seite pro Schritt) ---------- */

function nvAgentHasPrimary(data) {
  return (data.agents || []).some(function (row) {
    return row && row.mode === 'primary';
  });
}

function nvAgentWizard(data, token, onCancel) {
  var step = 1;
  var errorBox = nvAgentErrorBox();
  var wizard;
  /* Der Schrittzähler steht im Kopf und wird bei jedem Schritt neu gesetzt. */
  var stepLabel = el('span', {class: 'nv-step-indicator'},
    tr('Schritt {{n}} von 5', {n: 1}));

  var name = el('input', {'data-nv-field': 'name', 'aria-label': tr('Name'),
    placeholder: tr('z. B. coder')});
  var description = el('input', {'data-nv-field': 'description',
    'aria-label': tr('Beschreibung'), placeholder: tr('Wofür ist der Agent da?')});
  var role = nvAgentSelect(NV_AGENT_ROLES, '', tr('— keine Rolle —'));
  role.setAttribute('data-nv-field', 'role');
  role.setAttribute('aria-label', tr('Rolle'));

  /* Modell als Combobox (WP2): leerer Standardwert über opts.blank. */
  var modelValues = (data.models || []).slice();
  var model = NV.modelCombobox(modelValues, '',
    {field: 'model', blank: tr('— Standardmodell —')});
  model.setAttribute('aria-label', tr('Modell'));

  /* Einsatzart: erklärte Selects; „primary“ entfällt, sobald ein
     Primäragent in /api/agents steht (Auswertung hier, da data vorliegt). */
  var MODE_EXPLANATIONS = {
    subagent: tr('Subagent — wird nur vom Hauptagenten hinzugerufen'),
    all: tr('Agent — eigenständig startbar und als Subagent nutzbar'),
    primary: tr('Primäragent — steuert die anderen Agenten (nur einer)')
  };
  var modeValues = NV_AGENT_MODES.slice();
  if (nvAgentHasPrimary(data)) {
    modeValues = modeValues.filter(function (value) { return value !== 'primary'; });
  }
  /* Die erklärten Optionsshtriche: Aufgaben im Modus „all“ sind
     eigenständig startbar, „subagent“ nur Aufruf durch den Hauptagenten. */
  var mode = el('select', {'data-nv-field': 'mode',
    'aria-label': tr('Einsatzart wählen')});
  modeValues.forEach(function (value) {
    mode.append(el('option', {value: value},
      MODE_EXPLANATIONS[value] || value));
  });
  mode.value = 'subagent';
  var modeHelp = el('p', {class: 'nv-muted', 'data-nv-mode-help': ''});
  function setModeHelp() {
    setTx(modeHelp, mode.value
      ? MODE_EXPLANATIONS[mode.value] : tr('Einsatzart wählen'));
  }
  mode.addEventListener('change', function () { setModeHelp(); });
  setModeHelp();

  /* Rechte (WP2): Werte aus data.perms plus Hilfetext je Auswahl; der
     Template-Aufruf übergibt die gewählte perm. */
  var permValues = Object.keys(data.perms || {});
  var perm = nvAgentSelect(permValues,
    permValues.indexOf('lesen') >= 0 ? 'lesen' : (permValues[0] || ''), null);
  perm.setAttribute('data-nv-field', 'perm');
  var permHelp = el('p', {class: 'nv-muted', 'data-nv-perm-help': ''});
  var PERM_HELP = {
    voll: tr('Voll: lesen, schreiben, Shell'),
    lesen: tr('Nur lesen: Dateien einsehen'),
    lesen_git: tr('Nur lesen + Git lesend: Dateien lesen und Git-Befehle lesend ausführen')
  };
  function setPermHelp() {
    setTx(permHelp, PERM_HELP[perm.value] || tr('Rechte wählen'));
  }
  perm.addEventListener('change', function () { setPermHelp(); });
  setPermHelp();

  var prompt = el('textarea', {'data-nv-field': 'prompt', rows: 12,
    'aria-label': tr('Prompt'),
    placeholder: tr('System-Prompt: Rolle, Regeln, Ausgabeformat')});
  var review = el('div', {class: 'nv-agent-review'});
  function permLabel(value) {
    return String((data.perms || {})[value] || '');
  }
  function drawReview() {
    var rows_ = [
      [tr('Name'), name.value],
      [tr('Beschreibung'), description.value],
      [tr('Rolle'), role.value || tr('keine Rolle')],
      [tr('Modell'), model.getAttribute('data-nv-value') || tr('— Standardmodell —')],
      [tr('Einsatzart'), mode.value],
      [tr('Rechte'), permLabel(perm.value)]
    ];
    review.replaceChildren();
    rows_.forEach(function (row) {
      review.append(el('p', {class: 'nv-agent-review-row'},
        el('b', {}, row[0] + ': '), String(row[1] || '')));
    });
    /* Der Prompt erscheint ausschließlich als formatierter Block — die
       Liste nennt ihn nicht (Falltest: Zeilenumbrüche bleiben sichtbar). */
    review.append(el('pre', {class: 'nv-agent-review-prompt',
      'data-nv-review-prompt': ''}, String(prompt.value || '')));
  }

  /* Der Vorlagenknopf benutzt exakt denselben Request wie die klassische UI.
     Die Antwort enthält den fertigen Dateitext in "message" (API-Vertrag). */
  async function template() {
    nvAgentError(errorBox, '');
    try {
      var result = await api('/api/agent_template', {
        description: description.value,
        mode: mode.value,
        model: model.getAttribute('data-nv-value') || '',
        temperature: '',
        steps: '',
        perm: perm.value,
        prompt: prompt.value,
        scope: 'global'
      });
      if (!result.ok) { nvAgentError(errorBox, nvAgentMessage(result)); return; }
      prompt.value = String(result.message || '');
      toast(bt(tr('Vorlage eingefügt')));
    } catch (error) {
      nvAgentError(errorBox, tr('Vorlage fehlgeschlagen: ')
        + String(error && error.message || error));
    }
  }

  async function create() {
    nvAgentError(errorBox, '');
    var agentName = String(name.value || '').trim();
    if (!agentName) { nvAgentError(errorBox, tr('Name fehlt')); return; }
    var button = wizard.querySelector('[data-nv-action="agent-create"]');
    button.disabled = true;
    try {
      var draft = await api('/api/agent_template', {
        description: description.value,
        mode: mode.value,
        model: model.getAttribute('data-nv-value') || '',
        temperature: '',
        steps: '',
        perm: perm.value,
        prompt: prompt.value,
        scope: 'global'
      });
      if (!draft.ok) { nvAgentError(errorBox, nvAgentMessage(draft)); return; }
      var payload = {
        action: 'save', scope: 'global', name: agentName,
        text: String(draft.message || ''), create: true, expected: null
      };
      if (role.value) payload.role = role.value;
      var result = await api('/api/agent', payload);
      if (!result.ok) { nvAgentError(errorBox, nvAgentMessage(result)); return; }
      toast(bt(result.message) || tr('Agent angelegt'));
      if (!NV.stale(token)) NV.render();
    } catch (error) {
      nvAgentError(errorBox, tr('Anlegen fehlgeschlagen: ')
        + String(error && error.message || error));
    } finally {
      button.disabled = false;
    }
  }

  var sections = {};
  sections[1] = el('section', {class: 'nv-wizard-step', 'data-nv-step': '1'},
    el('h3', {}, tr('1. Wer ist der Agent?')),
    el('label', {}, tr('Name')), name,
    el('label', {}, tr('Beschreibung')), description,
    el('label', {}, tr('Rolle')), role);
  sections[2] = el('section', {class: 'nv-wizard-step', 'data-nv-step': '2', hidden: ''},
    el('h3', {}, tr('2. Wie arbeitet er?')),
    el('label', {}, tr('Modell')), model,
    el('label', {}, tr('Einsatzart')), mode, modeHelp);
  sections[3] = el('section', {class: 'nv-wizard-step', 'data-nv-step': '3', hidden: ''},
    el('h3', {}, tr('3. Rechte')),
    el('label', {}, tr('Rechte')), perm, permHelp);
  sections[4] = el('section', {class: 'nv-wizard-step', 'data-nv-step': '4', hidden: ''},
    el('h3', {}, tr('4. Was soll er tun?')),
    el('p', {class: 'nv-muted'}, tr('Die Vorlage erstellt den Dateiinhalt aus deinen Angaben. Danach kannst du ihn frei bearbeiten.')),
    el('button', {class: 'nv-btn', type: 'button',
      'data-nv-action': 'prompt-template', on: {click: template}}, tr('Vorlage einfügen')),
    el('label', {}, tr('Prompt')), prompt);
  sections[5] = el('section', {class: 'nv-wizard-step', 'data-nv-step': '5', hidden: ''},
    el('h3', {}, tr('5. Prüfen und anlegen')),
    el('p', {class: 'nv-muted'}, tr('Die strukturierten Felder stehen genau einmal; der Prompt nur als formatierter Block.')),
    review);

  function showStep() {
    [1, 2, 3, 4, 5].forEach(function (number) {
      sections[number].hidden = number !== step;
    });
    setTx(stepLabel, tr('Schritt {{n}} von 5', {n: step}));
    /* Auf Schritt 1 gibt es kein Zurück — der Knopf ist dann wirklich
       deaktiviert, nicht nur wirkungslos. */
    back.disabled = step === 1;
    /* Auf Schritt 5 ist der „Weiter“-Knopf tot: Anlegen ist da. */
    next.hidden = step === 5;
    if (step === 5) drawReview();
  }

  var cancelConfirm = null;
  function cancelClick() { cancelConfirm.hidden = !cancelConfirm.hidden; }
  cancelConfirm = el('div', {class: 'nv-wizard-cancel-confirm',
    'data-nv-wizard-cancel-confirm': '', hidden: ''},
    el('p', {class: 'nv-muted'}, tr('Eingaben gehen verloren. Der Wizard schließt sich.')),
    el('button', {class: 'nv-btn nv-secondary', type: 'button',
      on: {click: function () { cancelConfirm.hidden = true; }}}, tr('Weiter ausfüllen')),
    el('button', {class: 'nv-btn nv-primary', type: 'button',
      on: {click: function () { cancelConfirm.hidden = true; onCancel(); }}}, tr('Ja, abbrechen')));

  var back = el('button', {class: 'nv-btn', type: 'button',
    'data-nv-wizard-back': '', on: {click: function () {
      if (step > 1) { step--; showStep(); }
    }}}, tr('Zurück'));
  var next = el('button', {class: 'nv-btn nv-primary', type: 'button',
    'data-nv-wizard-next': '', on: {click: function () {
      nvAgentError(errorBox, '');
      if (step === 1 && !String(name.value || '').trim()) {
        nvAgentError(errorBox, tr('Name fehlt'));
        return;
      }
      if (step < 5) { step++; showStep(); }
    }}}, tr('Weiter'));
  var createButton = el('button', {class: 'nv-btn nv-primary', type: 'button',
    'data-nv-action': 'agent-create', on: {click: create}}, tr('Agent anlegen'));

  wizard = el('section', {class: 'nv-card nv-wizard', 'data-nv-wizard': '', hidden: ''},
    el('div', {class: 'nv-wizard-head'},
      el('h2', {class: 'nv-page-title'}, tr('Neuer Agent')), stepLabel),
    el('p', {class: 'nv-muted'}, tr('In fünf kurzen Schritten zu einem neuen Agenten.')),
    sections[1], sections[2], sections[3], sections[4], sections[5],
    errorBox,
    el('div', {class: 'nv-row nv-wizard-nav'}, back, next, createButton,
      el('button', {class: 'nv-btn nv-secondary', type: 'button',
        'data-nv-wizard-cancel': '', on: {click: cancelClick}}, tr('Abbrechen')),
      cancelConfirm));
  showStep();
  return wizard;
}

/* ---------- Ein-Seiten-Editor (2j/2k) ---------- */

async function nvAgentEditor(name, scope, data, token) {
  var main = document.getElementById('nv-main');
  var projects = data.projects || [];
  var loaded;
  try {
    loaded = await api('/api/agent?scope=' + encodeURIComponent(scope)
      + '&name=' + encodeURIComponent(name));
  } catch (error) {
    if (NV.stale(token)) return;
    main.replaceChildren(el('section', {class: 'nv-card'},
      el('h2', {class: 'nv-page-title'}, tr('Agent bearbeiten')),
      el('p', {class: 'nv-form-error', 'data-nv-form-error': ''},
        tr('Agent konnte nicht geladen werden: ')
          + String(error && error.message || error)),
      el('button', {class: 'nv-btn', type: 'button', on: {click: function () {
        NV.navigate('#/agents');
      }}}, tr('Zurück zur Liste'))));
    return;
  }
  if (NV.stale(token)) return;

  var fields = loaded.fields || {};
  var digest = loaded.digest || null;
  var currentText = String(loaded.text || '');
  var rawMode = false;
  var errorBox = nvAgentErrorBox();
  var models = (data.models || []).slice();
  if (fields.model && models.indexOf(fields.model) < 0) models.push(fields.model);
  var agentRow = (data.agents || []).find(function (row) {
    return row.name === name && row.scope === scope;
  }) || {};

  var description = el('input', {'data-nv-field': 'description',
    'aria-label': tr('Beschreibung'), placeholder: tr('Wofür ist der Agent da?'),
    value: String(fields.description || '')});
  var mode = nvAgentSelect(NV_AGENT_MODES, fields.mode || '', tr('— nicht gesetzt —'));
  mode.setAttribute('data-nv-field', 'mode');
  var model = nvAgentSelect(models, fields.model || '', tr('— Standardmodell —'));
  model.setAttribute('data-nv-field', 'model');
  var temperature = el('input', {'data-nv-field': 'temperature',
    'aria-label': tr('Temperatur'), placeholder: tr('z. B. 0.1'),
    value: String(fields.temperature == null ? '' : fields.temperature)});
  var steps = el('input', {'data-nv-field': 'steps',
    'aria-label': tr('Max. Schritte'), placeholder: tr('z. B. 60'),
    value: String(fields.steps == null ? '' : fields.steps)});
  var permissions = el('select', {'data-nv-field': 'permissions',
    'aria-label': tr('Rechte')},
    el('option', {value: ''}, fields.permission_custom
      ? tr('individuell – unverändert lassen') : tr('— nicht gesetzt —')));
  Object.keys(data.perms || {}).forEach(function (key) {
    permissions.append(el('option', {value: key}, String(data.perms[key])));
  });
  permissions.value = String(fields.permission || '');
  var prompt = el('textarea', {'data-nv-field': 'prompt', rows: 12,
    'aria-label': tr('Prompt'),
    placeholder: tr('System-Prompt: Rolle, Regeln, Ausgabeformat')},
    String(fields.prompt || ''));

  function structuredValues() {
    return {description: description.value, mode: mode.value, model: model.value,
      temperature: temperature.value, steps: steps.value,
      permission: permissions.value, prompt: prompt.value};
  }
  var baseline = structuredValues();

  var rawText = el('textarea', {'data-nv-raw-text': '', rows: 14,
    'aria-label': tr('Datei (Frontmatter + Prompt)')}, currentText);
  var rawWrap = el('div', {class: 'nv-raw-wrap', hidden: ''}, rawText);
  var saveHint = el('p', {class: 'nv-muted', 'data-nv-save-hint': ''});

  /* Projektzuordnung (2j):details steht geschlossen — die Zuordnungen und
     die Modell-Overrides liegen in details[data-nv-assignments] und laden
     beim ersten Öffnen parallel nach. */
  var assignmentRows = [];
  var assignmentsLoaded = false;
  var assignmentsDetails = el('details', {class: 'nv-assignments',
    'data-nv-assignments': ''},
    el('summary', {}, tr('Projektzuordnungen')),
    el('p', {class: 'nv-muted', 'data-nv-assignments-hint': ''},
      tr('Projektzuordnungen werden beim Aufklappen geladen')),
    el('div', {class: 'nv-list', 'data-nv-assignments-list': ''}));
  function renderAssignments() {
    var listNode = assignmentsDetails.querySelector('[data-nv-assignments-list]');
    listNode.replaceChildren();
    assignmentRows.forEach(function (row) {
      listNode.append(row.node);
    });
  }
  async function loadAssignments() {
    if (assignmentsLoaded) return;
    assignmentsLoaded = true;
    try {
      var views = await Promise.all(projects.map(function (project) {
        // Ein fehlender Projektzugriff darf den Editor nicht blockieren.
        return api('/api/project-agents?name=' + encodeURIComponent(project))
          .catch(function () { return {}; });
      }));
      if (NV.stale(token)) return;
      projects.forEach(function (project, index) {
        var view = views[index] || {};
        var row = (view.agents || []).find(function (item) {
          return item.name === name;
        }) || {};
        var toggle = el('input', {type: 'checkbox', 'data-nv-assign': project,
          'aria-label': tr('Agent in Projekt') + ': ' + name + ' · ' + project
            + ' – ' + tr('Zugewiesen')});
        toggle.checked = !!row.selected;
        if (agentRow.is_vibe) {
          // Der Vibe-Agent ist in jedem Projekt zwingend aktiv (API-Regel).
          toggle.checked = true;
          toggle.disabled = true;
        }
        var overrideValues = models.slice();
        if (row.override && overrideValues.indexOf(row.override) < 0) {
          overrideValues.push(row.override);
        }
        var override = NV.modelCombobox(overrideValues, row.override || '',
          {field: 'model', blank: tr('— Modell des Agentens verwenden —')});
        override.setAttribute('data-nv-assign-model', project);
        /* Eine Zeile je Projekt: sichtbarer Projektname, beschrifteter
           Schalter und Modell-Override bleiben zusammen. */
        var toggleLabel = el('label', {class: 'nv-assign-toggle'},
          toggle, el('span', {}, tr('Zugewiesen')));
        var projectName = el('span', {class: 'nv-assign-project'}, project);
        var assignmentRow = el('div', {'data-nv-assign-row': project},
          projectName, toggleLabel, override);
        assignmentRows.push({project: project, toggle: toggle, model: override,
          node: assignmentRow});
      });
      renderAssignments();
    } catch (error) {
      nvAgentError(errorBox, tr('Zuordnungen konnten nicht geladen werden: ')
        + String(error && error.message || error));
    }
  }
  assignmentsDetails.addEventListener('toggle', function () {
    if (assignmentsDetails.open) loadAssignments();
  });

  function setRawMode(enabled) {
    rawMode = enabled;
    rawWrap.hidden = !rawMode;
    rawButton.setAttribute('aria-pressed', rawMode ? 'true' : 'false');
    setTx(rawButton, rawMode
      ? tr('Strukturierte Ansicht') : tr('Rohtext anzeigen'));
    saveButton.setAttribute('data-nv-mode', rawMode ? 'raw' : 'fields');
    setTx(saveButton, rawMode ? tr('Rohtext speichern') : tr('Änderungen speichern'));
    setTx(saveHint, rawMode
      ? tr('Der komplette Rohtext wird gespeichert.')
      : tr('Nur geänderte Felder werden gespeichert.'));
  }

  var saveButton = el('button', {class: 'nv-btn nv-primary', type: 'button',
    'data-nv-action': 'agent-save', on: {click: save}}, tr('Änderungen speichern'));
  var rawButton = el('button', {class: 'nv-btn', type: 'button', 'data-nv-raw': '',
    on: {click: function () { setRawMode(!rawMode); }}}, tr('Rohtext anzeigen'));

  async function save() {
    nvAgentError(errorBox, '');
    saveButton.disabled = true;
    try {
      var payload = {action: 'save', scope: scope, name: name, expected: digest};
      if (rawMode) {
        // Rohtext unverändert an den Server geben: ein Digest-Konflikt muss
        // ablehnen, ohne die Datei von außen zu überschreiben.
        payload.text = rawText.value;
      } else {
        payload.text = currentText;
        var current = structuredValues();
        var changed = {};
        Object.keys(current).forEach(function (key) {
          if (current[key] !== baseline[key]) changed[key] = current[key];
        });
        // Nur geänderte Felder senden, wie im Bestand: freie Rohtextänderungen
        // an anderen Stellen bleiben dadurch erhalten.
        if (Object.keys(changed).length) payload.values = changed;
      }
      var result = await api('/api/agent', payload);
      if (!result.ok) { nvAgentError(errorBox, nvAgentMessage(result)); return; }
      digest = result.digest || digest;
      currentText = String(result.text || payload.text);
      rawText.value = currentText;
      for (var index = 0; index < assignmentRows.length; index++) {
        var item = assignmentRows[index];
        var assigned = await api('/api/project-agents', {
          name: item.project, agent: name,
          selected: item.toggle.checked,
          model: item.model.getAttribute('data-nv-value') || ''
        });
        if (!assigned.ok) { nvAgentError(errorBox, nvAgentMessage(assigned)); return; }
      }
      toast(bt(result.message) || tr('Gespeichert'));
    } catch (error) {
      nvAgentError(errorBox, tr('Speichern fehlgeschlagen: ')
        + String(error && error.message || error));
    } finally {
      saveButton.disabled = false;
    }
  }
  setRawMode(false);

  var backupButton = el('button', {class: 'nv-btn', type: 'button',
    'data-nv-action': 'agent-backup', on: {click: async function () {
      nvAgentError(errorBox, '');
      try {
        var result = await api('/api/agent', {action: 'backup', scope: scope, name: name});
        if (!result.ok) { nvAgentError(errorBox, nvAgentMessage(result)); return; }
        // Die Meldung („Sicherung angelegt“) kommt vom Backend — ohne
        // Versionshinweis anzeigen.
        toast(result.message || tr('Sicherung angelegt'));
      } catch (error) {
        nvAgentError(errorBox, tr('Sicherung fehlgeschlagen: ')
          + String(error && error.message || error));
      }
    }}}, tr('Sicherung anlegen'));

  var restoreConfirm = null;
  var copyConfirm = null;
  var deleteConfirm = null;
  function showConfirm(which) {
    if (restoreConfirm) restoreConfirm.hidden = which !== 'restore';
    if (copyConfirm) copyConfirm.hidden = which !== 'copy';
    if (deleteConfirm) deleteConfirm.hidden = which !== 'delete';
  }

  var restoreInfo = el('span', {class: 'nv-muted', 'data-nv-backup-info': ''});
  var restoreOrder = el('p', {class: 'nv-muted nv-restore-order'},
    tr('Neueste zuerst'));
  var restoreVersion = el('select', {'data-nv-restore-version': '',
    'aria-label': tr('Sicherung auswählen')});
  var restoreConfirmButton = el('button', {class: 'nv-btn nv-primary', type: 'button',
    on: {click: async function () {
      var backup = restoreVersion.value;
      if (!backup) {
        nvAgentError(errorBox, tr('Keine Sicherung ausgewählt.'));
        return;
      }
      try {
        var result = await api('/api/agent', {action: 'restore', scope: scope,
          name: name, backup: backup});
        if (!result.ok) { nvAgentError(errorBox, nvAgentMessage(result)); return; }
        toast(bt(result.message) || tr('Sicherung wiederhergestellt'));
        if (!NV.stale(token)) NV.render();
      } catch (error) {
        nvAgentError(errorBox, tr('Wiederherstellen fehlgeschlagen: ')
          + String(error && error.message || error));
      }
    }}}, tr('Ja, wiederhergestellt'));

  function setRestoreBackups(backups) {
    var restoreBackups = (backups || []).map(function (backup) {
      return String(backup);
    });
    restoreVersion.replaceChildren();
    restoreBackups.forEach(function (backup) {
      restoreVersion.append(el('option', {value: backup}, backup));
    });
    if (restoreBackups.length) {
      restoreVersion.value = restoreBackups[0];
      restoreVersion.disabled = false;
    } else {
      restoreVersion.disabled = true;
    }
    restoreConfirmButton.disabled = !restoreBackups.length;
    setTx(restoreInfo, restoreBackups.length
      ? tr('Letzte Sicherung: {{name}}', {name: restoreBackups[0]})
      : tr('Noch keine Sicherung vorhanden.'));
    restoreOrder.hidden = !restoreBackups.length;
  }

  /* Beim Öffnen der Bestätigung die Sicherungsliste frisch lesen: Sicherungen,
     die seit dem Laden des Editors entstanden sind, müssen auswählbar sein. */
  async function openRestore() {
    try {
      var fresh = await api('/api/agent?scope=' + encodeURIComponent(scope)
        + '&name=' + encodeURIComponent(name));
      if (NV.stale(token)) return;
      setRestoreBackups(fresh.backups || []);
    } catch (error) {
      /* Ohne frische Antwort bleibt die zuletzt bekannte Auswahl nutzbar. */
    }
    if (NV.stale(token)) return;
    showConfirm('restore');
  }

  restoreConfirm = el('div', {class: 'nv-confirm', 'data-nv-confirm': '', hidden: ''},
    restoreInfo,
    el('label', {class: 'nv-restore-version'},
      el('span', {}, tr('Sicherung auswählen')),
      restoreVersion),
    restoreOrder,
    el('p', {class: 'nv-muted'}, tr('Die gewählte Sicherung wiederherstellen? Der aktuelle Stand wird vorher gesichert.')),
    restoreConfirmButton);
  setRestoreBackups(loaded.backups || []);

  var targets = projects.filter(function (project) { return project !== 'global'; });
  var copyTarget = nvAgentSelect(['global'].concat(targets), targets[0] || 'global', null);
  copyTarget.setAttribute('data-nv-copy-target', '');
  copyConfirm = el('div', {class: 'nv-confirm', 'data-nv-confirm': '', hidden: ''},
    el('p', {class: 'nv-muted'}, tr('Nach „{{target}}“ kopieren?',
      {target: copyTarget.value})),
    copyTarget,
    el('button', {class: 'nv-btn nv-primary', type: 'button', on: {click: async function () {
      try {
        var result = await api('/api/agent', {
          action: 'copy', scope: scope, name: name, to: copyTarget.value
        });
        if (!result.ok) { nvAgentError(errorBox, nvAgentMessage(result)); return; }
        toast(bt(result.message) || tr('Kopiert'));
        if (!NV.stale(token)) {
          NV.navigate('#/agents/' + (copyTarget.value === 'global'
            ? encodeURIComponent(name)
            : encodeURIComponent(copyTarget.value) + '/' + encodeURIComponent(name)));
        }
      } catch (error) {
        nvAgentError(errorBox, tr('Kopieren fehlgeschlagen: ')
          + String(error && error.message || error));
      }
    }}}, tr('Ja, kopieren')));

  deleteConfirm = el('div', {class: 'nv-confirm', 'data-nv-confirm': '', hidden: ''},
    el('p', {class: 'nv-muted'}, tr('Diesen Agenten löschen? Eine Sicherung bleibt erhalten.')),
    el('button', {class: 'nv-btn nv-danger', type: 'button', on: {click: async function () {
      try {
        var result = await api('/api/agent', {action: 'delete', scope: scope, name: name});
        if (!result.ok) { nvAgentError(errorBox, nvAgentMessage(result)); return; }
        toast(bt(result.message) || tr('Agent gelöscht'));
        if (!NV.stale(token)) NV.navigate('#/agents');
      } catch (error) {
        nvAgentError(errorBox, tr('Löschen fehlgeschlagen: ')
          + String(error && error.message || error));
      }
    }}}, tr('Ja, löschen')));

  var restoreButton = el('button', {class: 'nv-btn', type: 'button',
    'data-nv-action': 'agent-restore', on: {click: openRestore}},
    tr('Sicherung wiederherstellen'));
  var copyButton = el('button', {class: 'nv-btn', type: 'button',
    'data-nv-action': 'agent-copy', on: {click: function () { showConfirm('copy'); }}},
    tr('Kopieren'));
  var deleteButton = el('button', {class: 'nv-btn nv-danger', type: 'button',
    'data-nv-action': 'agent-delete', on: {click: function () { showConfirm('delete'); }}},
    tr('Löschen'));

  var editor = el('section', {class: 'nv-card nv-agent-editor', 'data-nv-agent-editor': '',
    'data-nv-agent-scope': scope},
    el('div', {class: 'nv-row'},
      el('h2', {class: 'nv-page-title'}, tr('Agent bearbeiten')),
      el('span', {class: 'nv-pill', 'data-nv-agent-scope-badge': ''},
        scope === 'global' ? tr('Global') : tr('Projekt') + ': ' + scope),
      el('span', {class: 'nv-pill'}, name),
      el('button', {class: 'nv-btn nv-secondary', type: 'button',
        'data-nv-action': 'agent-back', 'aria-label': tr('Zurück zur Liste'),
        on: {click: function () {
          /* Wie der Wizard-Abbruch: die Liste sofort anzeigen. Die Route
             per replaceState korrigieren — ein NV.navigate würde über
             hashchange einen zweiten Render auslösen, der die Liste kurz
             durch ein leeres Lade-Rahmen ersetzt. */
          if (!NV.stale(token)) nvAgentList(data, token, null);
          history.replaceState(null, '', '#/agents');
        }}}, tr('Zurück zur Liste'))),
    el('div', {class: 'nv-agent-fields'},
      el('label', {}, tr('Beschreibung')), description,
      el('div', {class: 'nv-grid'},
        el('div', {}, el('label', {}, tr('Modus')), mode),
        el('div', {}, el('label', {}, tr('Modell')), model),
        el('div', {}, el('label', {}, tr('Rechte')), permissions)),
      el('div', {class: 'nv-grid'},
        el('div', {}, el('label', {}, tr('Temperatur')), temperature),
        el('div', {}, el('label', {}, tr('Max. Schritte')), steps)),
      el('label', {}, tr('Prompt')), prompt,
      saveHint,
      el('div', {class: 'nv-row nv-agent-actions'}, saveButton, rawButton, backupButton,
        restoreButton, copyButton, deleteButton)),
    rawWrap,
    assignmentsDetails,
    restoreConfirm, copyConfirm, deleteConfirm,
    errorBox);
  main.replaceChildren(editor);
}

/* F34 WP2: neue Texte der Ansicht (Schlüssel = deutscher Quelltext). */
if (window.VIBE_I18N && typeof VIBE_I18N.extend === 'function') {
  VIBE_I18N.extend({
    en: {'Anpinnen': 'Pin', 'Lösen': 'Unpin'},
    de: {'Anpinnen': 'Anpinnen', 'Lösen': 'Lösen'}
  });
}
