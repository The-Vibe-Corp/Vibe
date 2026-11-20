/* AP22 — Agenten: Liste, geführter Wizard und Ein-Seiten-Editor.
 *
 * Die Hooks folgen docs/features/AP22.md und dem Moduldocstring von
 * tests/browser/test_ap22_agents_ui.py. Die bestehende API wird unverändert
 * konsumiert (selbe Payloads wie die klassische Oberfläche in app.js).
 */
'use strict';

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
      el('section', {class: 'nv-row nv-agent-head'},
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

/* ---------- Liste ---------- */

function nvAgentList(data, token, wanted) {
  var main = document.getElementById('nv-main');
  var rows = data.agents || [];
  var list = el('div', {class: 'nv-grid', 'data-nv-agent-list': ''});

  rows.forEach(function (row) {
    var name = String(row.name || '');
    var scope = String(row.scope || 'global');
    var description = String(row.description || '');
    var shown = description.length > 120 ? description.slice(0, 117) + '…' : description;
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
            if (!NV.stale(token)) NV.render();
          } catch (error) {
            toast(tr('Löschen fehlgeschlagen: ') + String(error && error.message || error));
          }
        }}}, tr('Ja, löschen')));
    var card = el('article', {class: 'nv-card nv-agent', 'data-nv-agent': name,
      'data-nv-agent-scope': scope},
      el('div', {class: 'nv-row'},
        el('h3', {class: 'nv-agent-name'}, name),
        el('span', {class: 'nv-pill', 'data-nv-agent-scope-badge': ''},
          scope === 'global' ? tr('Global') : tr('Projekt') + ': ' + scope),
        el('span', {class: 'nv-pill', 'data-nv-role': ''}, String(row.role || tr('keine Rolle'))),
        row.is_vibe ? el('span', {class: 'nv-pill nv-type'}, tr('Vibe-Agent')) : null,
        row.valid === false
          ? el('span', {class: 'nv-pill nv-warn', title: tr('Datei ist kein gültiger Agent')},
            tr('ungültig'))
          : null),
      el('p', {class: 'nv-muted', title: description}, shown || tr('Keine Beschreibung')),
      el('div', {class: 'nv-row nv-muted'},
        el('span', {}, tr('Modell') + ': '),
        el('span', {}, String(row.model || '—'))),
      el('div', {class: 'nv-row'},
        el('button', {class: 'nv-btn nv-primary', type: 'button',
          'data-nv-action': 'agent-edit', on: {click: function () {
            NV.navigate(editRoute);
          }}}, tr('Bearbeiten')),
        el('button', {class: 'nv-btn nv-danger', type: 'button',
          'data-nv-action': 'agent-delete', on: {click: function () {
            deleteConfirm.hidden = false;
          }}}, tr('Löschen'))),
      deleteConfirm);
    list.append(card);
  });
  if (!rows.length) {
    list.append(el('p', {class: 'nv-muted'}, tr('Noch keine Agenten vorhanden.')));
  }

  var header = el('section', {class: 'nv-row nv-agent-head'},
    el('h2', {class: 'nv-page-title'}, tr('Agenten')),
    el('button', {class: 'nv-btn nv-primary', type: 'button',
      'data-nv-action': 'agent-new', on: {click: showWizard}}, tr('Neuer Agent')));
  var listSection = el('section', {class: 'nv-section'}, list);
  var wizard = null;

  function showList() {
    if (wizard) wizard.hidden = true;
    listSection.hidden = false;
    header.hidden = false;
  }
  function showWizard() {
    header.hidden = true;
    listSection.hidden = true;
    wizard.hidden = false;
    wizard.querySelector('[data-nv-field="name"]').focus();
  }

  wizard = nvAgentWizard(data, token, showList);
  main.replaceChildren(header, listSection, wizard);
  // Ein Klick auf den Rahmen-Button vor der API-Antwort darf nicht verloren gehen.
  if (wanted && wanted.wizard) { wanted.wizard = false; showWizard(); }
}

/* ---------- Wizard (4 Schritte, eine Seite pro Schritt) ---------- */

function nvAgentWizard(data, token, onCancel) {
  var step = 1;
  var errorBox = nvAgentErrorBox();
  var wizard;
  /* Der Schrittzähler steht im Kopf und wird bei jedem Schritt neu gesetzt;
     setTx merkt sich Key und Variablen für einen Sprachwechsel. */
  var stepLabel = el('span', {class: 'nv-step-indicator'},
    tr('Schritt {{n}} von 4', {n: step}));

  var name = el('input', {'data-nv-field': 'name', 'aria-label': tr('Name'),
    placeholder: tr('z. B. coder')});
  var description = el('input', {'data-nv-field': 'description',
    'aria-label': tr('Beschreibung'), placeholder: tr('Wofür ist der Agent da?')});
  var role = nvAgentSelect(NV_AGENT_ROLES, '', tr('— keine Rolle —'));
  role.setAttribute('data-nv-field', 'role');
  role.setAttribute('aria-label', tr('Rolle'));

  var modelValues = (data.models || []).slice();
  var model = nvAgentSelect(modelValues, '', tr('— Standardmodell —'));
  model.setAttribute('data-nv-field', 'model');
  var mode = nvAgentSelect(NV_AGENT_MODES, 'subagent', null);
  mode.setAttribute('data-nv-field', 'mode');

  var prompt = el('textarea', {'data-nv-field': 'prompt', rows: 8,
    'aria-label': tr('Prompt'),
    placeholder: tr('System-Prompt: Rolle, Regeln, Ausgabeformat')});
  var review = el('div', {class: 'nv-agent-review'});

  function drawReview() {
    review.replaceChildren(
      el('p', {}, el('b', {}, tr('Name') + ': '), String(name.value || '')),
      el('p', {}, el('b', {}, tr('Beschreibung') + ': '), String(description.value || '')),
      el('p', {}, el('b', {}, tr('Rolle') + ': '), String(role.value || tr('keine Rolle'))),
      el('p', {}, el('b', {}, tr('Modell') + ': '), String(model.value || tr('— Standardmodell —'))),
      el('p', {}, el('b', {}, tr('Einsatzart') + ': '), String(mode.value || '')),
      el('p', {}, el('b', {}, tr('Prompt') + ': '), String(prompt.value || '')));
  }

  /* Der Vorlagenknopf benutzt exakt denselben Request wie die klassische UI.
     Die Antwort enthält den fertigen Dateitext in "message" (API-Vertrag). */
  async function template() {
    nvAgentError(errorBox, '');
    try {
      var result = await api('/api/agent_template', {
        description: description.value,
        mode: mode.value,
        model: model.value,
        temperature: '',
        steps: '',
        perm: 'lesen',
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
        model: model.value,
        temperature: '',
        steps: '',
        perm: 'lesen',
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
    el('label', {}, tr('Einsatzart')), mode);
  sections[3] = el('section', {class: 'nv-wizard-step', 'data-nv-step': '3', hidden: ''},
    el('h3', {}, tr('3. Was soll er tun?')),
    el('p', {class: 'nv-muted'}, tr('Die Vorlage erstellt den Dateiinhalt aus deinen Angaben. Danach kannst du ihn frei bearbeiten.')),
    el('button', {class: 'nv-btn', type: 'button',
      'data-nv-action': 'prompt-template', on: {click: template}}, tr('Vorlage einfügen')),
    el('label', {}, tr('Prompt')), prompt);
  sections[4] = el('section', {class: 'nv-wizard-step', 'data-nv-step': '4', hidden: ''},
    el('h3', {}, tr('4. Prüfen und anlegen')),
    el('p', {class: 'nv-muted'}, tr('Prüfe deine Angaben. Danach wird die Agentendatei angelegt.')),
    review,
    el('button', {class: 'nv-btn nv-primary', type: 'button',
      'data-nv-action': 'agent-create', on: {click: create}}, tr('Agent anlegen')));

  function showStep() {
    [1, 2, 3, 4].forEach(function (number) {
      sections[number].hidden = number !== step;
    });
    setTx(stepLabel, tr('Schritt {{n}} von 4', {n: step}));
    /* Auf Schritt 1 gibt es kein Zurück — der Knopf ist dann wirklich
       deaktiviert, nicht nur wirkungslos. */
    back.disabled = step === 1;
    if (step === 4) drawReview();
  }

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
      if (step < 4) { step++; showStep(); }
    }}}, tr('Weiter'));

  wizard = el('section', {class: 'nv-card nv-wizard', 'data-nv-wizard': '', hidden: ''},
    el('div', {class: 'nv-wizard-head'},
      el('h2', {class: 'nv-page-title'}, tr('Neuer Agent')), stepLabel),
    el('p', {class: 'nv-muted'}, tr('In vier kurzen Schritten zu einem neuen Agenten.')),
    sections[1], sections[2], sections[3], sections[4],
    errorBox,
    el('div', {class: 'nv-row nv-wizard-nav'}, back, next,
      el('button', {class: 'nv-btn nv-secondary', type: 'button',
        'data-nv-wizard-cancel': '', on: {click: onCancel}}, tr('Abbrechen'))));
  showStep();
  return wizard;
}

/* ---------- Ein-Seiten-Editor ---------- */

async function nvAgentEditor(name, scope, data, token) {
  var main = document.getElementById('nv-main');
  var projects = data.projects || [];
  var loaded;
  var assignmentViews;
  try {
    var results = await Promise.all([
      api('/api/agent?scope=' + encodeURIComponent(scope) + '&name=' + encodeURIComponent(name))
    ].concat(projects.map(function (project) {
      // Ein fehlender Projektzugriff darf den Agenteneditor nicht blockieren.
      return api('/api/project-agents?name=' + encodeURIComponent(project))
        .catch(function () { return {}; });
    })));
    loaded = results[0];
    assignmentViews = results.slice(1);
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
  var prompt = el('textarea', {'data-nv-field': 'prompt', rows: 8,
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

  /* Projektzuordnung: Schalter und Modell-Override kommen aus
     GET /api/project-agents und werden gemeinsam mit dem Agenten gespeichert. */
  var assignments = [];
  var assignmentList = el('div', {class: 'nv-list'});
  projects.forEach(function (project, index) {
    var view = assignmentViews[index] || {};
    var row = (view.agents || []).find(function (item) { return item.name === name; }) || {};
    var toggle = el('input', {type: 'checkbox', 'data-nv-assign': project,
      'aria-label': tr('Agent in Projekt') + ': ' + name + ' · ' + project});
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
    var override = nvAgentSelect(overrideValues, row.override || '',
      tr('— Modell des Agenten verwenden —'));
    override.setAttribute('data-nv-assign-model', project);
    assignments.push({project: project, toggle: toggle, model: override});
    assignmentList.append(el('div', {class: 'nv-assign-row', 'data-nv-assign-row': project},
      el('label', {}, toggle, ' ', name + ' · ' + String(project)), override));
  });

  var saveButton = el('button', {class: 'nv-btn nv-primary', type: 'button',
    'data-nv-action': 'agent-save', on: {click: save}}, tr('Speichern'));

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
      for (var index = 0; index < assignments.length; index++) {
        var item = assignments[index];
        var assigned = await api('/api/project-agents', {
          name: item.project, agent: name,
          selected: item.toggle.checked, model: item.model.value
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

  var restoreConfirm = null;
  var copyConfirm = null;
  var deleteConfirm = null;
  function showConfirm(which) {
    if (restoreConfirm) restoreConfirm.hidden = which !== 'restore';
    if (copyConfirm) copyConfirm.hidden = which !== 'copy';
    if (deleteConfirm) deleteConfirm.hidden = which !== 'delete';
  }

  var backupButton = el('button', {class: 'nv-btn', type: 'button',
    'data-nv-action': 'agent-backup', on: {click: async function () {
      nvAgentError(errorBox, '');
      try {
        // Es gibt keinen eigenen Backup-Endpunkt: Ein Speichern des
        // unveränderten Standes legt die Sicherung über die bestehende API an.
        var result = await api('/api/agent', {
          action: 'save', scope: scope, name: name,
          text: rawMode ? rawText.value : currentText, expected: digest
        });
        if (!result.ok) { nvAgentError(errorBox, nvAgentMessage(result)); return; }
        digest = result.digest || digest;
        currentText = String(result.text || currentText);
        rawText.value = currentText;
        toast(bt(result.message) || tr('Sicherung angelegt'));
      } catch (error) {
        nvAgentError(errorBox, tr('Sicherung fehlgeschlagen: ')
          + String(error && error.message || error));
      }
    }}}, tr('Sicherung anlegen'));

  restoreConfirm = el('div', {class: 'nv-confirm', hidden: ''},
    el('p', {class: 'nv-muted'}, tr('Die neueste Sicherung wiederherstellen? Der aktuelle Stand wird vorher gesichert.')),
    el('button', {class: 'nv-btn nv-primary', type: 'button', on: {click: async function () {
      try {
        var result = await api('/api/agent', {action: 'restore', scope: scope, name: name});
        if (!result.ok) { nvAgentError(errorBox, nvAgentMessage(result)); return; }
        toast(bt(result.message) || tr('Sicherung wiederhergestellt'));
        if (!NV.stale(token)) NV.render();
      } catch (error) {
        nvAgentError(errorBox, tr('Wiederherstellen fehlgeschlagen: ')
          + String(error && error.message || error));
      }
    }}}, tr('Ja, wiederherstellen')));

  var targets = projects.filter(function (project) { return project !== 'global'; });
  var copyTarget = nvAgentSelect(['global'].concat(targets), targets[0] || 'global', null);
  copyTarget.setAttribute('data-nv-copy-target', '');
  copyConfirm = el('div', {class: 'nv-confirm', hidden: ''},
    el('p', {class: 'nv-muted'}, tr('Wohin soll der Agent kopiert werden?')),
    copyTarget,
    el('button', {class: 'nv-btn nv-primary', type: 'button', on: {click: async function () {
      try {
        var result = await api('/api/agent', {
          action: 'copy', scope: scope, name: name, to: copyTarget.value
        });
        if (!result.ok) { nvAgentError(errorBox, nvAgentMessage(result)); return; }
        toast(bt(result.message) || tr('Agent kopiert'));
        if (!NV.stale(token)) NV.render();
      } catch (error) {
        nvAgentError(errorBox, tr('Kopieren fehlgeschlagen: ')
          + String(error && error.message || error));
      }
    }}}, tr('Ja, kopieren')));

  deleteConfirm = el('div', {class: 'nv-confirm', hidden: ''},
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

  var rawButton = el('button', {class: 'nv-btn', type: 'button', 'data-nv-raw': '',
    on: {click: function () {
      rawMode = !rawMode;
      rawWrap.hidden = !rawMode;
    }}}, tr('Rohtext anzeigen'));
  var restoreButton = el('button', {class: 'nv-btn', type: 'button',
    'data-nv-action': 'agent-restore', on: {click: function () { showConfirm('restore'); }}},
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
      el('button', {class: 'nv-btn nv-ghost', type: 'button',
        on: {click: function () { NV.navigate('#/agents'); }}}, tr('Zurück zur Liste'))),
    el('div', {class: 'nv-agent-fields'},
      el('label', {}, tr('Beschreibung')), description,
      el('div', {class: 'nv-grid'},
        el('div', {}, el('label', {}, tr('Modus')), mode),
        el('div', {}, el('label', {}, tr('Modell')), model),
        el('div', {}, el('label', {}, tr('Rechte')), permissions)),
      el('div', {class: 'nv-grid'},
        el('div', {}, el('label', {}, tr('Temperatur')), temperature),
        el('div', {}, el('label', {}, tr('Max. Schritte')), steps)),
      el('label', {}, tr('Prompt')), prompt),
    el('div', {class: 'nv-row nv-agent-actions'}, saveButton, rawButton, backupButton,
      restoreButton, copyButton, deleteButton),
    rawWrap,
    el('section', {class: 'nv-section'},
      el('h3', {}, tr('Projektzuordnung')),
      el('p', {class: 'nv-muted'}, tr('Lege fest, in welchen Projekten dieser Agent mitarbeitet. Das Modell kann je Projekt abweichen.')),
      assignmentList),
    restoreConfirm, copyConfirm, deleteConfirm,
    errorBox);
  main.replaceChildren(editor);
}
