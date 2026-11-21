/* AP22 — Projektansicht (Meilenstein B).
 *
 * Held, Tabs, Überblick, Arbeit (Board/Feedback/Priorisierung), Assistent und
 * Projekteinstellungen. Alle Daten kommen aus den bestehenden /api-Endpunkten;
 * die Ansicht verändert kein Backend-Verhalten. Jede asynchrone Fortsetzung
 * prüft NV.stale(token), bevor sie DOM ersetzt (Render-Rennschutz wie AP21).
 * Die Ausgabe ist bewusst nicht implementiert: Ihr Container delegiert an
 * NV.output.render(name, panel) (Meilenstein B2).
 */
'use strict';

var nvpRunTimer = null;

function nvpErrorBox() {
  return el('div', {class: 'nv-form-error', 'data-nv-form-error': '', hidden: ''});
}

function nvpShowError(box, message) {
  var text = String(message == null ? '' : message);
  box.textContent = text;
  if (text) box.removeAttribute('hidden');
  else box.setAttribute('hidden', '');
  if (text) toast(bt(text));
}

function nvpButton(label, hook, handler, extraClass) {
  return el('button', {
    class: 'nv-btn ' + (extraClass || ''),
    type: 'button',
    'data-nv-action': hook,
    on: {click: handler}
  }, label);
}

function nvpSection(id, title, children) {
  var section = el('section', {class: 'nv-card nv-psection', 'data-nv-psection': id},
    el('h3', {}, title));
  (children || []).forEach(function (child) { if (child) section.append(child); });
  return section;
}

function nvpLabel(text, control) {
  return el('label', {class: 'nv-field'}, el('span', {}, text), control);
}

function nvpOption(select, value, selected) {
  select.append(el('option', {value: value}, value));
  if (selected) select.value = value;
}

/* ---------- Help: Zustand/Formatierung ---------- */

function nvpStateColumn(state) {
  if (state === 'offen') return 'open';
  if (state === 'WARTET AUF MERGE') return 'waiting';
  if (state === 'BLOCKIERT') return 'blocked';
  if (state === 'ohne Nachweis') return 'proof';
  if (state === 'erledigt') return 'done';
  return 'open';
}

function nvpStateLabel(state) {
  if (state === 'offen') return tr('Offen');
  if (state === 'WARTET AUF MERGE') return tr('Wartet auf Merge');
  if (state === 'BLOCKIERT') return tr('Blockiert');
  if (state === 'ohne Nachweis') return tr('Ohne Nachweis');
  if (state === 'erledigt') return tr('Erledigt');
  return tr('Offen');
}

function nvpCount(list, state) {
  return (list || []).filter(function (row) {
    return String(row && row.state || '') === state;
  }).length;
}

/* Die Kennung ist ein zuverlässiger zweiter Hinweis auf die Art: Bugs werden
   mit B…/BUG… angelegt, gewöhnliches Feedback mit F…/FB…. Das Backend liefert
   kind bei korrekt formatierten Blöcken; ältere Blöcke mit „Art“ nach
   „Beschreibung“ werden vom Parser nicht erkannt (siehe Review). */
function nvpFeedbackKind(row) {
  var id = String(row && row.id || '');
  if (/^\s*(?:BUG|B)\s*[-0-9]/i.test(id)) return 'bug';
  return String(row && row.kind || '') === 'bug' ? 'bug' : 'feedback';
}

/* ---------- Held + Lauf-Pille ---------- */

function nvpStartRunPoll(name, token, pill, stopButton) {
  if (nvpRunTimer) { clearInterval(nvpRunTimer); nvpRunTimer = null; }
  var update = async function () {
    if (NV.stale(token)) {
      if (nvpRunTimer) clearInterval(nvpRunTimer);
      nvpRunTimer = null;
      return;
    }
    try {
      var status = await api('/api/run-state?name=' + encodeURIComponent(name));
      if (NV.stale(token)) return;
      var running = !!(status && status.running);
      pill.setAttribute('data-state', running ? 'running' : 'stopped');
      pill.textContent = String(running ? tr('läuft') : tr('gestoppt'));
      if (stopButton) stopButton.hidden = !running;
    } catch (error) { /* Poll darf kurzzeitige Fehler ignorieren. */ }
  };
  update();
  nvpRunTimer = setInterval(update, 4000);
}

function nvpPost(name, path, body, successKey, token) {
  return api(path, Object.assign({name: name}, body || {})).then(function (result) {
    if (NV.stale(token)) return result;
    var message = bt(result && result.message) || tr(successKey);
    toast(message);
    return result;
  }).catch(function (error) {
    toast(tr('Aktion fehlgeschlagen: ') + String(error && error.message || error));
    return null;
  });
}

/* ---------- Arbeit: Board, Feedback, Formular, Priorisierung ---------- */

function nvpBoardColumn(name, column, rows, token) {
  var box = el('div', {class: 'nv-board-col', 'data-nv-col': column},
    el('h3', {}, nvpStateLabel(column === 'open' ? 'offen'
      : column === 'blocked' ? 'BLOCKIERT'
        : column === 'waiting' ? 'WARTET AUF MERGE'
          : column === 'proof' ? 'ohne Nachweis' : 'erledigt')));
  if (!rows.length) {
    box.append(el('p', {class: 'nv-muted'}, tr('Keine Einträge')));
  }
  rows.forEach(function (row) {
    var id = String(row.id || '');
    var isFeedback = !!row.__feedback;
    var title = String(row.title || id);
    var closeError = el('div', {class: 'nv-form-error', 'data-nv-form-error': '', hidden: ''});
    var closeAction = ((column === 'blocked' || column === 'waiting') && !isFeedback)
      ? el('button', {class: 'nv-btn nv-ghost nv-compact', type: 'button',
          'data-nv-action': 'package-close', on: {click: function () {
            nvpShowError(closeError, '');
            api('/api/package', {name: name, id: id, action: 'close'}).then(function (result) {
              if (NV.stale(token)) return;
              if (result && result.ok === false) {
                nvpShowError(closeError, bt(result.message));
                return;
              }
              toast(bt(result && result.message) || tr('Paket abgeschlossen'));
              NV.render();
            }).catch(function (e) {
              if (!NV.stale(token)) nvpShowError(closeError, String(e && e.message || e));
            });
          }}}, tr('Paket abschließen'))
      : null;
    var card = el('article', {
      class: 'nv-card nv-ticket',
      'data-nv-ticket': id,
      'data-nv-state': String(row.state || '')
    },
      el('div', {class: 'nv-ticket-head'},
        el('span', {class: 'nv-ticket-id'}, id),
        el('span', {class: 'nv-pill nv-state' + (row.state === 'WARTET AUF MERGE' ? ' nv-warn' : '')}, nvpStateLabel(row.state))),
      el('div', {class: 'nv-ticket-title'}, title),
      String(row.description || '')
        ? el('div', {class: 'nv-muted nv-ticket-desc'}, String(row.description || '')) : null,
      el('div', {class: 'nv-row nv-ticket-actions'},
        el('button', {class: 'nv-btn nv-ghost nv-compact', type: 'button',
          'data-nv-action': 'ticket-edit', on: {click: function () {
            nvpOpenTicketForm(workPanelRoot(name), token, {
              mode: isFeedback ? 'feedback' : 'package',
              id: id, title: title, description: String(row.description || '')
            });
          }}}, tr('Bearbeiten')),
        el('button', {class: 'nv-btn nv-ghost nv-compact', type: 'button',
          'data-nv-action': 'ticket-delete', on: {click: function () {
            if (!window.confirm(String(tr('wirklich löschen?')) + ' ' + id)) return;
            var body = isFeedback
              ? {action: 'delete', id: id}
              : {action: 'delete', id: id};
            var path = isFeedback ? '/api/feedback' : '/api/ticket';
            nvpPost(name, path, body, 'Gelöscht', token).then(function () {
              if (!NV.stale(token)) NV.render();
            });
          }}}, tr('Löschen')),
        closeAction),
      closeError);
    box.append(card);
  });
  return box;
}

/* Das Formular wird erst beim Klick erzeugt und nach Abbrechen entfernt; so
   bleibt [data-nv-ticket-form] im Ruhezustand vollständig aus dem DOM. */
function workPanelRoot(name) {
  return document.querySelector('main[data-nv-view="project"] section[data-nv-ppanel="work"]');
}

function nvpOpenTicketForm(root, token, options) {
  if (!root) return;
  var existing = root.querySelector('[data-nv-ticket-form]');
  if (existing) existing.remove();
  var mode = options.mode || 'package';
  var editing = !!options.id;
  var titleInput = el('input', {'data-nv-field': 'title', type: 'text',
    value: options.title || '', 'aria-label': tr('Titel')});
  var descInput = el('textarea', {'data-nv-field': 'description', rows: '4',
    'aria-label': tr('Beschreibung')}, options.description || '');
  var idInput = el('input', {'data-nv-field': 'id', type: 'text',
    value: options.id || '', 'aria-label': tr('Kennung')});
  if (editing) idInput.setAttribute('readonly', '');
  var error = nvpErrorBox();

  var heading = mode === 'bug' ? tr('Neuer Bug')
    : mode === 'feedback' ? tr('Neues Feedback')
      : editing ? tr('Arbeitspaket bearbeiten') : tr('Neues Arbeitspaket');

  var form = el('form', {class: 'nv-card nv-ticket-form', 'data-nv-ticket-form': ''},
    el('h3', {}, heading),
    nvpLabel(tr('Kennung'), idInput),
    nvpLabel(tr('Titel'), titleInput),
    nvpLabel(tr('Beschreibung'), descInput),
    el('div', {class: 'nv-row'},
      el('button', {class: 'nv-btn nv-primary', type: 'button',
        'data-nv-action': 'ticket-save', on: {click: async function () {
          nvpShowError(error, '');
          var title = String(titleInput.value || '').trim();
          if (!title) { nvpShowError(error, tr('Titel fehlt')); return; }
          // Der Dienst schreibt beim Update „prefix + title“; ein Titel, den
          // der Nutzer mit der Kennung beginnt, würde die Kennung sonst
          // doppeln. Deshalb den redundanten Prefix entfernen.
          var cleanTitle = title;
          var ident = String(idInput.value || '');
          if (editing && ident && cleanTitle.indexOf(ident + ' ') === 0) {
            cleanTitle = cleanTitle.slice(ident.length + 1);
          }
          var body = {
            title: cleanTitle,
            description: String(descInput.value || '')
          };
          var path = '/api/ticket';
          if (mode === 'bug' || mode === 'feedback') {
            path = '/api/feedback';
            if (!editing && mode === 'bug') body.kind = 'bug';
          }
          if (editing) {
            body.action = 'update';
            body.id = String(idInput.value || '');
          } else {
            body.action = 'add';
            if (mode === 'package') body.id = String(idInput.value || '');
          }
          try {
            var result = await api(path, Object.assign({name: nvpCurrentName()}, body));
            if (NV.stale(token)) return;
            if (result && result.ok === false) {
              nvpShowError(error, bt(result.message));
              return;
            }
            toast(bt(result && result.message) || tr('Gespeichert'));
            NV.render();
          } catch (e) {
            nvpShowError(error, tr('Speichern fehlgeschlagen: ') + String(e && e.message || e));
          }
        }}}, tr('Speichern')),
      el('button', {class: 'nv-btn nv-ghost', type: 'button',
        'data-nv-action': 'ticket-cancel', on: {click: function () { form.remove(); }}},
        tr('Abbrechen'))),
    error);
  root.append(form);
  titleInput.focus();
}

/* Der Projektname steht im Hash; Formulare holen ihn bei Bedarf dort, damit
   sie auch nach einem Panel-Neuaufbau ohne übergebenen Kontext auskommen. */
function nvpCurrentName() {
  var match = (location.hash || '').match(/#\/?project\/([^/]+)/);
  if (!match) return '';
  try { return decodeURIComponent(match[1]); } catch (e) { return match[1]; }
}

function nvpPriorityCard(name, token, view) {
  var card = el('div', {class: 'nv-card nv-priority', 'data-nv-priority': ''},
    el('h3', {}, tr('Priorisierung')));
  /* Zeilen hängen direkt an der Karte (nicht in einem gemeinsamenWrapper):
     so gehört zu jedem Hoch-/Runter-Knopf genau eine Zeile als Vorfahre und
     die Kennung der Zeile ist über den Text eindeutig auffindbar. */
  var save = nvpButton(tr('Speichern'), 'priority-save', async function () {
    var order = Array.prototype.slice.call(card.querySelectorAll('[data-nv-priority-id]'))
      .map(function (row) { return row.getAttribute('data-nv-priority-id'); });
    try {
      var result = await api('/api/priority', {
        name: name, action: 'set', order: order.join(' ')
      });
      if (NV.stale(token)) return;
      if (result && result.ok === false) toast(bt(result.message));
      else toast(tr('Priorisierung gespeichert'));
      if (view && view.priority) {
        var fresh = await api('/api/priority?name=' + encodeURIComponent(name));
        if (!NV.stale(token)) draw(fresh);
      }
    } catch (e) {
      toast(tr('Speichern fehlgeschlagen: ') + String(e && e.message || e));
    }
  }, 'nv-primary');
  card.append(save);

  function draw(data) {
    var configured = (data && data.order) || [];
    var others = (data && data.standard) || (data && data.queue) || [];
    var ids = [];
    var titles = {};
    configured.concat(others).forEach(function (row) {
      var id = String(row && row.id || '');
      if (!id || ids.indexOf(id) >= 0) return;
      ids.push(id);
      titles[id] = String(row && row.title || id);
    });
    function renderRows() {
      card.querySelectorAll('[data-nv-priority-id]').forEach(function (node) { node.remove(); });
      ids.forEach(function (id, index) {
        var upAttrs = {class: 'nv-btn nv-ghost nv-compact', type: 'button',
          'data-nv-action': 'priority-up', 'aria-label': tr('Nach oben'),
          on: {click: function () {
            if (index > 0) {
              var tmp = ids[index - 1]; ids[index - 1] = ids[index]; ids[index] = tmp;
              renderRows();
            }
          }}};
        var downAttrs = {class: 'nv-btn nv-ghost nv-compact', type: 'button',
          'data-nv-action': 'priority-down', 'aria-label': tr('Nach unten'),
          on: {click: function () {
            if (index < ids.length - 1) {
              var tmp = ids[index + 1]; ids[index + 1] = ids[index]; ids[index] = tmp;
              renderRows();
            }
          }}};
        if (index === 0) upAttrs.disabled = '';
        if (index === ids.length - 1) downAttrs.disabled = '';
        var row = el('div', {class: 'nv-priority-row', 'data-nv-priority-id': id},
          el('span', {class: 'nv-priority-label'}, id + ' ' + (titles[id] || '')),
          el('button', upAttrs, '↑'),
          el('button', downAttrs, '↓'));
        card.insertBefore(row, save);
      });
    }
    if (!ids.length) {
      card.insertBefore(el('p', {class: 'nv-muted'}, tr('Keine Einträge')), save);
    } else {
      renderRows();
    }
  }
  draw(view && view.priority);
  return card;
}

/* ---------- Assistent ---------- */

function nvpAssistantPanel(name, token, guide, autonomous) {
  var holder = el('div', {class: 'nv-card nv-assistant', 'data-nv-assistant': ''},
    el('h3', {}, tr('Projektleitfaden')));

  var steps = (guide && guide.steps) || [];
  if (!steps.length) {
    holder.append(el('p', {class: 'nv-muted'}, tr('Keine Schritte vorhanden')));
  }
  steps.forEach(function (step) {
    var id = String(step.id || '');
    var answer = el('textarea', {rows: '2', 'data-nv-answer-field': id,
      'aria-label': tr('Antwort')}, String(step.value || ''));
    var note = el('input', {type: 'text', 'data-nv-note': id,
      placeholder: tr('Notiz'), 'aria-label': tr('Notiz')});
    var stepBox = el('div', {class: 'nv-guide-step'},
      el('h4', {}, String(step.title || id)),
      el('p', {}, String(step.question || '')),
      el('p', {class: 'nv-muted'}, String(step.help || '')),
      el('span', {class: 'nv-pill nv-state'}, String(step.status || '')),
      answer);
    var buttons = [el('button', {class: 'nv-btn nv-ghost nv-compact', type: 'button',
      on: {click: function () {
        nvpGuideAction(name, token, {
          action: 'agent', step: id, note: String(note.value || '')
        });
      }}}, tr('Mit Agent entwerfen'))];
    if (step.draft) {
      buttons.push(el('button', {class: 'nv-btn nv-compact', type: 'button',
        on: {click: function () { nvpGuideAction(name, token, {action: 'draft_apply', step: id}); }}},
        tr('Entwurf übernehmen')));
      buttons.push(el('button', {class: 'nv-btn nv-ghost nv-compact', type: 'button',
        on: {click: function () { nvpGuideAction(name, token, {action: 'draft_discard', step: id}); }}},
        tr('Entwurf verwerfen')));
    }
    buttons.push(el('button', {class: 'nv-btn nv-primary nv-compact', type: 'button',
      on: {click: function () {
        var answers = {};
        answers[id] = String(answer.value || '');
        nvpGuideAction(name, token, {action: 'save', answers: answers});
      }}}, tr('Antwort speichern')));
    stepBox.append(note, el('div', {class: 'nv-row'}, buttons));
    holder.append(stepBox);
  });

  var on = !!(autonomous && autonomous.enabled);
  var auto = el('input', {type: 'checkbox', 'data-nv-autonomous': '', checked: on,
    'aria-label': tr('Autonomer Modus')});
  auto.addEventListener('change', function () {
    nvpPost(name, '/api/autonomous', {action: auto.checked ? 'on' : 'off'},
      'Autonomer Modus', token);
  });
  holder.append(el('div', {class: 'nv-card nv-row nv-autonomous'},
    el('span', {}, tr('Autonomer Modus')), auto));
  return holder;
}

function nvpGuideAction(name, token, body) {
  nvpPost(name, '/api/guide', body, 'Gespeichert', token).then(function () {
    if (!NV.stale(token)) NV.render();
  });
}

/* ---------- Projekteinstellungen ---------- */

function nvpTeamSection(name, token, agents) {
  var rows = (agents && agents.agents) || [];
  var models = (agents && agents.models) || [];
  var body = el('div', {class: 'nv-list'});
  var error = nvpErrorBox();
  if (!rows.length) body.append(el('p', {class: 'nv-muted'}, tr('Keine Agenten vorhanden')));
  rows.forEach(function (row) {
    var agent = String(row.name || '');
    var toggle = el('input', {type: 'checkbox', 'data-nv-agent-toggle': '',
      checked: !!row.selected, 'aria-label': tr('Aktiv')});
    toggle.addEventListener('change', function () {
      api('/api/project-agents', {name: name, agent: agent, selected: toggle.checked})
        .then(function (result) {
          if (NV.stale(token)) return;
          if (result && result.ok === false) nvpShowError(error, bt(result.message));
          else toast(bt(result && result.message) || tr('Agentenauswahl gespeichert'));
        })
        .catch(function (e) { nvpShowError(error, String(e && e.message || e)); });
    });
    var model = el('select', {'data-nv-agent-model': '', 'aria-label': tr('Modell')});
    var current = String(row.override || row.model || '');
    var seen = {};
    models.forEach(function (m) {
      var value = String(m && (m.id || m) || '');
      if (!value || seen[value]) return;
      seen[value] = true;
      nvpOption(model, value, value === current);
    });
    if (current && !seen[current]) nvpOption(model, current, true);
    model.addEventListener('change', function () {
      api('/api/project-agents', {name: name, agent: agent, model: model.value})
        .then(function (result) {
          if (NV.stale(token)) return;
          if (result && result.ok === false) nvpShowError(error, bt(result.message));
          else toast(bt(result && result.message) || tr('Modell gespeichert'));
        })
        .catch(function (e) { nvpShowError(error, String(e && e.message || e)); });
    });
    body.append(el('div', {class: 'nv-row nv-team-row', 'data-nv-team-agent': agent},
      toggle, el('span', {class: 'nv-team-name'}, agent),
      row.opencode ? el('span', {class: 'nv-tag'}, tr('OpenCode')) : null,
      model));
  });
  return nvpSection('team', tr('Team'), [body, error]);
}

function nvpBasicsSection(name, token, data) {
  var type = String(data.type || '');
  var typeSelect = el('select', {'data-nv-field': 'type', 'aria-label': tr('Typ')});
  ['generic', 'android', 'swift', 'python', 'node', 'rust', 'go'].forEach(function (value) {
    nvpOption(typeSelect, value, value === type);
  });
  if (type && !Array.prototype.some.call(typeSelect.options, function (o) { return o.value === type; })) {
    nvpOption(typeSelect, type, true);
  }
  var error = nvpErrorBox();
  var init = nvpButton(tr('Projekt vorbereiten'), 'init', function () {
    nvpPost(name, '/api/init', {type: typeSelect.value}, 'Vorbereitung gestartet', token)
      .then(function () { if (!NV.stale(token)) NV.render(); });
  }, 'nv-primary');
  /* Ein Feld pro Zeile: Beschriftung links, Wert rechts. Als Definitionsliste
     bleibt die Zuweisung auch bei langen Pfaden eindeutig. */
  return nvpSection('basics', tr('Grundlagen'), [
    el('dl', {class: 'nv-kv nv-kv-list'},
      el('div', {class: 'nv-kv-row'}, el('dt', {}, tr('Pfad')),
        el('dd', {}, el('code', {}, String(data.path || '')))),
      el('div', {class: 'nv-kv-row'}, el('dt', {}, tr('Typ')),
        el('dd', {}, String(type || '-'))),
      el('div', {class: 'nv-kv-row'}, el('dt', {}, '.vibe'),
        el('dd', {}, String(data.init ? tr('Vorhanden') : tr('Fehlt'))))),
    nvpLabel(tr('Typ'), typeSelect),
    el('div', {class: 'nv-row'}, init), error
  ]);
}

function nvpChecksSection(name, token, data) {
  var state = el('p', {}, tr('Prüfung') + ': '
    + String(data.verify_cmd ? tr('Verfügbar') : tr('Nicht konfiguriert')));
  var tail = el('pre', {class: 'nv-log', role: 'log'},
    (data.verify_tail || []).join('\n') || String(tr('Kein Prüfprotokoll vorhanden')));
  return nvpSection('checks', tr('Prüfungen'), [state, tail]);
}

function nvpPauseSection(name, token, data) {
  var active = !!data.pause_after;
  var state = el('span', {'data-nv-pause-state': ''},
    active ? tr('Pause angefordert') : tr('Keine Pause angefordert'));
  var toggle = nvpButton(active ? tr('Pause aufheben') : tr('Pause anfordern'),
    'pause-settings-toggle', function () {
      nvpPost(name, '/api/pause', {action: active ? 'off' : 'on'},
        'Pause', token).then(function () { if (!NV.stale(token)) NV.render(); });
    });
  return nvpSection('pause', tr('Pause nach Paket'), [
    el('div', {class: 'nv-row'}, state, toggle)
  ]);
}

function nvpSessionsSection(name, token, sessions) {
  var rows = (sessions && sessions.sessions) || (sessions && sessions.entries) || [];
  var body = el('div', {class: 'nv-list'});
  if (!rows.length) body.append(el('p', {class: 'nv-muted'}, tr('Keine Sitzungen vorhanden')));
  rows.forEach(function (row) {
    var session = String(row.session || row.id || row.name || '');
    body.append(el('div', {class: 'nv-row nv-session-row'},
      el('span', {}, session + ' ' + String(row.project || '')),
      el('span', {class: 'nv-muted', 'data-nv-session-attach': ''},
        (row.package_id || row.worktree_path)
          ? tr('Paket ') + String(row.package_id || '?') + tr(' · Arbeitskopie ') + String(row.worktree_path || '?')
          : ''),
      nvpButton(tr('Fortsetzen'), 'session-resume-settings', function () {
        nvpPost(name, '/api/sessions', {action: 'continue', session: session},
          'Sitzung fortgesetzt', token);
      })));
  });
  var limit = sessions && sessions.limit;
  return nvpSection('sessions', tr('Sitzungen'), [
    el('p', {class: 'nv-muted'}, tr('Sitzungslimit') + ': '
      + (limit == null ? '-' : String(limit))), body
  ]);
}

/* Git & GitHub: vollständige CLI-Parität als bewusste Aktionen. Die Payloads
   entsprechen eins zu eins der klassischen Karte (app.js githubBody); der
   Zugriff ist je Projekt und der Token wird nie in den DOM geschrieben.
   AP4 (T-G0): Auto-Merge-Schalter je Projekt; Standard aus = PR-only (der
   Eigentümer mergt und schließt danach mit "vibe package close"), bei "1"
   mergt der Läufer den freigegebenen PR nach bestandener Schranke selbst. */
function nvpGithubSection(name, token, github) {
  var g = github || {};
  var error = nvpErrorBox();

  function post(body, onResult) {
    return api('/api/github', Object.assign({name: name}, body))
      .then(function (result) {
        if (NV.stale(token)) return result;
        if (result && result.ok === false) nvpShowError(error, bt(result.message));
        else nvpShowError(error, '');
        if (onResult) onResult(result);
        return result;
      })
      .catch(function (e) {
        if (!NV.stale(token)) nvpShowError(error, String(e && e.message || e));
        return null;
      });
  }
  function refresh() {
    if (!NV.stale(token)) NV.render();
  }

  /* --- Aktivierung und Einstellungen --- */
  var enabled = el('input', {type: 'checkbox', 'data-nv-field': 'github-enabled',
    'aria-label': tr('GitHub-Verknüpfung aktiv')});
  enabled.checked = !!g.enabled;
  var repo = el('input', {type: 'text', 'data-nv-field': 'repo',
    value: String(g.repo || ''), placeholder: 'owner/name',
    'aria-label': tr('Repository (owner/name)')});
  var label = el('input', {type: 'text', 'data-nv-field': 'label',
    value: String(g.label || ''), 'aria-label': tr('Label für vibe-Aufgaben')});
  var apiBase = el('input', {type: 'text', 'data-nv-field': 'api',
    value: String(g.api || ''), 'aria-label': tr('API-Adresse')});
  var base = el('input', {type: 'text', 'data-nv-field': 'base',
    value: String(g.base || ''), 'aria-label': tr('Basis-Branch (optional)')});
  var autoMerge = el('input', {type: 'checkbox', 'data-nv-field': 'github-auto-merge',
    'aria-label': tr('Auto-Merge aktivieren (Läufer mergt freigegebene Merge-Requests selbst)')});
  autoMerge.checked = !!g.auto_merge;
  var save = nvpButton(tr('Einstellungen speichern'), 'github-settings-save', function () {
    post({action: 'settings', enabled: enabled.checked, repo: repo.value.trim(),
      label: label.value.trim(), api: apiBase.value.trim(), base: base.value.trim(), auto_merge: autoMerge.checked},
      function (result) {
        if (result && result.ok !== false) {
          toast(bt(result.message) || tr('Gespeichert'));
          refresh();
        }
      });
  }, 'nv-primary');

  /* --- Zugang (Token): nur Quelle/status, niemals der Wert selbst --- */
  function setAuth(source) {
    var text = source === 'umgebung'
      ? tr('GitHub-Zugang über die Umgebung.')
      : source === 'projekt'
        ? tr('GitHub-Projekt-Token gespeichert (verschlüsselt).')
        : source === 'gespeichert'
          ? tr('GitHub-Zugang über den gespeicherten Token.')
          : tr('Kein Token hinterlegt.');
    return tr('GitHub-Zugang: ') + text;
  }
  var authLine = el('div', {class: 'nv-muted', 'data-nv-github-auth': ''},
    setAuth(g.auth && g.auth.set ? g.auth.source : ''));
  var tokenInput = el('input', {type: 'password', 'data-nv-field': 'github-token',
    placeholder: tr('GitHub-Token einfügen'), 'aria-label': tr('GitHub-Token einfügen')});
  var tokenSave = nvpButton(tr('Token speichern'), 'github-token-save', function () {
    var value = String(tokenInput.value || '').trim();
    if (!value) { nvpShowError(error, tr('Kein Token angegeben.')); return; }
    post({action: 'token.save', token: value}, function (result) {
      if (!result || result.ok === false) return;
      tokenInput.value = '';
      var a = result.auth || (result.github && result.github.auth) || {};
      setTx(authLine, setAuth(a.set ? a.source : ''));
      toast(bt(result.message) || tr('Token gespeichert'));
    });
  }, 'nv-primary');
  var tokenClear = nvpButton(tr('Token entfernen'), 'github-token-clear', function () {
    post({action: 'token.clear'}, function (result) {
      if (!result || result.ok === false) return;
      tokenInput.value = '';
      var a = result.auth || (result.github && result.github.auth) || {};
      setTx(authLine, setAuth(a.set ? a.source : ''));
      toast(bt(result.message) || tr('Token entfernt'));
    });
  });

  /* --- Verbindung --- */
  var connect = nvpButton(tr('Verbindung prüfen'), 'github-connection', function () {
    post({action: 'connection'}, function (result) {
      if (!result) return;
      var view = result.connection || {};
      var ok = !!(result.ok && view.ok);
      connResult.setAttribute('data-nv-ok', ok ? 'true' : 'false');
      setTx(connResult, tr('Verbindung: ') + (ok ? tr('OK') : tr('FEHLER'))
        + ' — ' + String(result.message || view.message || ''));
      connResult.removeAttribute('hidden');
    });
  });
  var connResult = el('div', {class: 'nv-muted', 'data-nv-github-connection': '', hidden: ''});

  /* --- Branches mit zeilenlokalem Checkout --- */
  var branchRows = el('div', {class: 'nv-list'});
  (g.branches || []).forEach(function (branch) {
    var branchName = String(branch.name || '');
    branchRows.append(el('div', {class: 'nv-row',
      'data-nv-github-branch': branchName},
      el('span', {}, (branch.current ? '* ' : '') + branchName
        + ' (' + tr('Ahead/Behind') + ' ' + (branch.ahead || 0) + '/' + (branch.behind || 0) + ')'),
      nvpButton(tr('Auschecken'), 'github-checkout', function () {
        post({action: 'checkout', branch: branchName}, function (result) {
          if (result && result.ok !== false) refresh();
        });
      })));
  });
  if (!(g.branches || []).length) {
    branchRows.append(el('p', {class: 'nv-muted'}, tr('Keine lokalen Branches erkannt.')));
  }

  /* --- Pull / Push --- */
  var pull = nvpButton(tr('Pull (aufholen, --ff-only)'), 'github-pull', function () {
    post({action: 'pull'}, function (result) {
      if (result && result.ok !== false) refresh();
    });
  });
  var pushBranch = el('input', {type: 'text', 'data-nv-field': 'github-push-branch',
    placeholder: tr('Quell-Branch'), 'aria-label': tr('Quell-Branch')});
  var pushTarget = el('input', {type: 'text', 'data-nv-field': 'github-push-target',
    placeholder: tr('Ziel-Branch (leer = gleicher Name)'),
    'aria-label': tr('Ziel-Branch (leer = gleicher Name)')});
  var push = nvpButton(tr('Push'), 'github-push', function () {
    post({action: 'push', branch: pushBranch.value.trim(), target: pushTarget.value.trim()},
      function (result) {
        if (result && result.ok !== false) refresh();
      });
  }, 'nv-primary');

  /* --- Verknüpfung herstellen/lösen, Abruf (fetch) --- */
  var link = nvpButton(tr('Mit GitHub verknüpfen'), 'github-link', function () {
    var value = String(repo.value || '').trim();
    if (!value || value.indexOf('/') < 0) {
      nvpShowError(error, tr('Repository in der Form owner/name angeben'));
      return;
    }
    post({action: 'link', url: 'https://github.com/' + value + '.git'}, function (result) {
      if (result && result.ok !== false) refresh();
    });
  });
  var unlink = nvpButton(tr('Verknüpfung lösen'), 'github-unlink', function () {
    post({action: 'unlink'}, function (result) {
      if (result && result.ok !== false) refresh();
    });
  });
  var fetch = nvpButton(tr('Abrufen (fetch, kein Merge)'), 'github-fetch', function () {
    post({action: 'fetch'}, function (result) {
      if (result && result.ok !== false) refresh();
    });
  });

  /* --- Issues als Arbeitspakete --- */
  var issueFilter = el('input', {type: 'text', 'data-nv-field': 'github-issue-label',
    value: String(g.label || 'vibe'), placeholder: tr('Label (leer = alle)'),
    'aria-label': tr('Label-Filter')});
  var issuesResult = el('div', {class: 'nv-muted', 'data-nv-github-issues': '', hidden: ''});
  var loadIssues = nvpButton(tr('Issues laden'), 'github-issues', function () {
    post({action: 'issues', label: issueFilter.value.trim()}, function (result) {
      if (!result) return;
      var ok = result.ok !== false;
      issuesResult.setAttribute('data-nv-ok', ok ? 'true' : 'false');
      if (!ok) {
        setTx(issuesResult, bt(result.message) || tr('Fehler beim Laden der Issues'));
      } else {
        var issues = result.issues || [];
        setTx(issuesResult, issues.length
          ? issues.map(function (issue) {
            return 'GH-' + (issue.number || '') + ' ' + String(issue.title || '');
          }).join(' · ')
          : tr('Keine offenen Issues für dieses Label.'));
      }
      issuesResult.removeAttribute('hidden');
    });
  });
  var importIssues = nvpButton(tr('Issues importieren'), 'github-import', function () {
    post({action: 'import', label: issueFilter.value.trim()}, function (result) {
      if (result && result.ok !== false) refresh();
    });
  });

  /* --- Merge-Request: Anfrage zeigt nur die Bestätigung; erst die
     ausdrückliche Bestätigung löst den REST-Aufruf aus. --- */
  var prConfirm = el('div', {class: 'nv-confirm', 'data-nv-github-pr-confirm': '', hidden: ''},
    el('p', {class: 'nv-muted'}, tr('Merge-Request wirklich stellen? Der aktuelle Branch wird nach origin gepusht und der Merge-Request über GitHub angelegt.')),
    nvpButton(tr('Ja, bestätigen'), 'github-pr-confirm', function () {
      post({action: 'pr', confirm: true}, function (result) {
        if (!result) return;
        prConfirm.setAttribute('hidden', '');
        prResult.setAttribute('data-nv-ok', result.ok !== false ? 'true' : 'false');
        setTx(prResult, String(bt(result.message) || tr('Kein Ergebnis zum Merge-Request')));
        prResult.removeAttribute('hidden');
      });
    }, 'nv-primary'));
  var prResult = el('div', {class: 'nv-muted', 'data-nv-github-pr-result': '', hidden: ''});
  var pr = nvpButton(tr('Merge-Request stellen'), 'github-pr', function () {
    prConfirm.removeAttribute('hidden');
    prResult.setAttribute('hidden', '');
  }, 'nv-primary');

  return nvpSection('github', tr('Git & GitHub'), [
    authLine,
    el('div', {class: 'nv-row'}, tokenInput, tokenSave, tokenClear),
    nvpLabel(tr('GitHub-Verknüpfung aktiv'), enabled),
    nvpLabel(tr('Repository (owner/name)'), repo),
    nvpLabel(tr('Label für vibe-Aufgaben'), label),
    nvpLabel(tr('API-Adresse'), apiBase),
    nvpLabel(tr('Basis-Branch (optional)'), base),
    nvpLabel(tr('Auto-Merge aktivieren (Läufer mergt freigegebene Merge-Requests selbst)'), autoMerge),
    el('div', {class: 'nv-row'}, save, connect),
    el('div', {class: 'nv-row'}, link, unlink, fetch),
    connResult,
    el('h4', {}, tr('Branches')), branchRows,
    el('div', {class: 'nv-row'}, pull, pushBranch, pushTarget, push),
    el('h4', {}, tr('Issues als Arbeitspakete')),
    el('div', {class: 'nv-row'}, issueFilter, loadIssues, importIssues),
    issuesResult,
    el('div', {class: 'nv-row'}, pr, prConfirm), prResult,
    error
  ]);
}

function nvpRightsSection(name, token, data) {
  var path = el('input', {type: 'text', 'data-nv-field': 'path',
    placeholder: tr('Verzeichnis'), 'aria-label': tr('Verzeichnis')});
  var list = el('div', {class: 'nv-list'});
  (data.write_dirs || []).forEach(function (dir) {
    list.append(el('div', {class: 'nv-row'}, el('code', {}, String(dir)),
      nvpButton(tr('Löschen'), 'rights-remove', function () {
        nvpPost(name, '/api/rights', {action: 'remove', path: String(dir)},
          'Gelöscht', token).then(function () { if (!NV.stale(token)) NV.render(); });
      })));
  });
  var error = nvpErrorBox();
  var add = nvpButton(tr('Hinzufügen'), 'rights-add', function () {
    nvpPost(name, '/api/rights', {action: 'add', path: path.value.trim()},
      'Gespeichert', token).then(function () { if (!NV.stale(token)) NV.render(); });
  }, 'nv-primary');
  return nvpSection('writeaccess', tr('Schreibrechte'), [
    list, nvpLabel(tr('Verzeichnis'), path), el('div', {class: 'nv-row'}, add), error
  ]);
}

function nvpSandboxSection(name, token, sandbox) {
  var enabled = !!(sandbox && sandbox.enabled);
  var toggle = nvpButton(enabled ? tr('Ausschalten') : tr('Einschalten'),
    'sandbox-toggle', function () {
      nvpPost(name, '/api/sandbox', {action: enabled ? 'off' : 'on'},
        'Gespeichert', token).then(function () { if (!NV.stale(token)) NV.render(); });
    }, 'nv-primary');
  var check = nvpButton(tr('Prüfen'), 'sandbox-check', function () {
    nvpPost(name, '/api/sandbox', {action: 'check'}, 'Geprüft', token);
  });
  return nvpSection('sandbox', tr('Sandbox'), [
    el('p', {class: 'nv-muted'}, String((sandbox && sandbox.error) || '')
      || tr('Sandbox-Status')),
    el('div', {class: 'nv-row'}, toggle, check)
  ]);
}

function nvpAgentsFileSection(name, token, view) {
  var content = String((view && view.agents_file && view.agents_file.text) || '');
  var text = el('textarea', {rows: '8', 'data-nv-field': 'agents-file',
    'aria-label': 'AGENTS.md'}, content);
  var error = nvpErrorBox();
  var save = nvpButton(tr('Datei speichern'), 'agents-file-save', async function () {
    nvpShowError(error, '');
    try {
      var result = await api('/api/agents_file', {
        name: name, action: 'save', before: content, after: text.value,
        digest: (view && view.agents_file && view.agents_file.digest) || ''
      });
      if (NV.stale(token)) return;
      if (result && result.ok === false) nvpShowError(error, bt(result.message));
      else toast(bt(result && result.message) || tr('Gespeichert'));
    } catch (e) { nvpShowError(error, String(e && e.message || e)); }
  }, 'nv-primary');
  var create = nvpButton(tr('Datei anlegen'), 'agents-file-create', function () {
    nvpPost(name, '/api/agents_file', {action: 'create'}, 'Gespeichert', token)
      .then(function () { if (!NV.stale(token)) NV.render(); });
  });
  return nvpSection('agentsfile', 'AGENTS.md', [
    text, el('div', {class: 'nv-row'}, save, create), error
  ]);
}

/* ---------- Ansicht ---------- */

NV.views.project = async function project(context, token) {
  var name = String(context.name || '');
  var enc = encodeURIComponent(name);
  var tabs = ['overview', 'work', 'output', 'assistant', 'settings'];
  var active = tabs.indexOf(context.tab) >= 0 ? context.tab : 'overview';

  /* Held und Tab-Gerüst stehen synchron — Navigation und Titel hängen nicht
     von der Netzwerkantwort ab. */
  var pill = el('span', {class: 'nv-pill nv-run', 'data-nv-run-state': '',
    'data-state': 'stopped'}, tr('gestoppt'));
  /* Leere Pillen bleiben im DOM (die Hooks werden gezählt), sind aber bis zum
     Vorliegen eines echten Werts ausgeblendet — sonst stehen graue Striche. */
  var branch = el('span', {class: 'nv-pill nv-branch', 'data-nv-branch': '', hidden: ''}, '');
  var typeBadge = el('span', {class: 'nv-pill nv-type', 'data-nv-project-type': '', hidden: ''}, '');
  var stopButton = el('button', {class: 'nv-btn', type: 'button', hidden: '',
    'data-nv-action': 'stop', on: {click: function () {
      nvpPost(name, '/api/stop', {}, 'Gestoppt', token)
        .then(function () { if (!NV.stale(token)) NV.render(); });
    }}}, tr('Stoppen'));

  var hero = el('section', {class: 'nv-card nv-hero', 'data-nv-hero': ''},
    el('div', {class: 'nv-row'},
      el('h2', {class: 'nv-page-title', 'data-nv-project-title': ''}, name),
      pill, branch, typeBadge),
    el('div', {class: 'nv-row nv-hero-actions'},
      nvpButton(tr('Arbeit starten'), 'run', function () {
        nvpPost(name, '/api/run', {}, 'Gestartet', token)
          .then(function () { if (!NV.stale(token)) NV.render(); });
      }, 'nv-primary'),
      nvpButton(tr('Prüfen'), 'verify', function () {
        nvpPost(name, '/api/verify', {mode: 'quick'}, 'Prüfung gestartet', token);
      }),
      el('button', {class: 'nv-btn', type: 'button', 'data-nv-verify': 'full',
        on: {click: function () {
          nvpPost(name, '/api/verify', {mode: 'full'}, 'Vollprüfung gestartet', token);
        }}}, tr('Vollprüfung')),
      nvpButton(tr('Pause anfordern'), 'pause', function () {
        nvpPost(name, '/api/pause', {action: 'request'}, 'Pause', token)
          .then(function () { if (!NV.stale(token)) NV.render(); });
      }),
      stopButton));

  var tabBar = el('div', {class: 'nv-tabs', role: 'tablist'});
  var panels = {};
  tabs.forEach(function (tab) {
    var selected = tab === active;
    tabBar.append(el('button', {class: 'nv-tab', type: 'button', role: 'tab',
      'data-nv-ptab': tab, 'aria-selected': selected ? 'true' : 'false',
      'aria-controls': 'nv-panel-' + tab,
      on: {click: function () {
        NV.navigate('#/project/' + enc + '/' + tab);
      }}}, tr(tab === 'overview' ? 'Überblick' : tab === 'work' ? 'Arbeit'
      : tab === 'output' ? 'Ausgabe' : tab === 'assistant' ? 'Assistent'
        : 'Einstellungen')));
    var panel = el('section', {class: 'nv-card nv-ppanel', role: 'tabpanel',
      id: 'nv-panel-' + tab, 'data-nv-ppanel': tab});
    // Erst nach dem Laden aufdecken: so ist ein sichtbares Panel immer auch
    // bereits mit seinen echten Inhalten gefüllt (kein Leerzustand-Rennen).
    panel.setAttribute('hidden', '');
    panels[tab] = panel;
  });
  /* Lade-Platzhalter liegt außerhalb der Panels: so füllt er sofort die Fläche
     unter den Tabs, ohne das Versprechen zu brechen, dass ein sichtbares Panel
     auch schon seine echten Inhalte trägt. */
  var loading = el('div', {class: 'nv-loading', 'aria-hidden': 'true'},
    el('div', {class: 'nv-skeleton'}),
    el('div', {class: 'nv-skeleton nv-skeleton-short'}),
    el('div', {class: 'nv-skeleton'}));
  document.getElementById('nv-main').replaceChildren(hero, tabBar, loading,
    panels.overview, panels.work, panels.output, panels.assistant, panels.settings);

  /* Feature-Bereiche stehen mit ihren Hook-Karten sofort im DOM (auch bevor
     die API-Antworten da sind); nach dem Laden ersetzen die echten Karten
     diese Platzhalter. So bleibt die Struktur unabhängig von der Latenz. */
  var placeholders = [];
  function placeholder(node, parent) {
    parent.append(node);
    placeholders.push(node);
  }
  if (NV.feature('github')) placeholder(nvpGithubSection(name, token, {}), panels.settings);
  if (NV.feature('writeaccess')) placeholder(nvpRightsSection(name, token, {}), panels.settings);
  if (NV.feature('sandbox')) placeholder(nvpSandboxSection(name, token, {}), panels.settings);
  if (NV.feature('agentsfile')) placeholder(nvpAgentsFileSection(name, token, {}), panels.settings);
  if (NV.feature('priority')) placeholder(nvpPriorityCard(name, token, {}), panels.work);

  var view = {};
  try {
    var requests = [
      api('/api/project?name=' + enc),
      api('/api/run-state?name=' + enc),
      api('/api/project-agents?name=' + enc),
      api('/api/guide?name=' + enc),
      api('/api/autonomous?name=' + enc),
      api('/api/sessions?name=' + enc)
    ];
    if (NV.feature('priority')) requests.push(api('/api/priority?name=' + enc));
    if (NV.feature('agentsfile')) requests.push(api('/api/agents_file?name=' + enc));
    var results = await Promise.all(requests);
    if (NV.stale(token)) return;
    view.data = results[0] || {};
    view.run = results[1] || {};
    view.agents = results[2] || {};
    view.guide = results[3] || {};
    view.autonomous = results[4] || {};
    view.sessions = results[5] || {};
    var cursor = 6;
    if (NV.feature('priority')) view.priority = results[cursor++];
    if (NV.feature('agentsfile')) view.agents_file = results[cursor++];
  } catch (error) {
    if (NV.stale(token)) return;
    loading.remove();
    panels.overview.append(el('p', {class: 'nv-form-error', 'data-nv-form-error': ''},
      tr('Daten konnten nicht geladen werden: ') + String(error && error.message || error)));
    panels[active].removeAttribute('hidden');
    return;
  }

  loading.remove();
  var data = view.data;
  var running = !!(view.run && view.run.running) || !!data.running;
  pill.setAttribute('data-state', running ? 'running' : 'stopped');
  pill.textContent = String(running ? tr('läuft') : tr('gestoppt'));
  stopButton.hidden = !running;
  var branchValue = String(data.branch || '').trim();
  if (branchValue && branchValue !== '-') {
    branch.textContent = branchValue;
    branch.removeAttribute('hidden');
  }
  var typeValue = String(data.type || '').trim();
  if (typeValue) {
    typeBadge.textContent = typeValue;
    typeBadge.removeAttribute('hidden');
  }
  nvpStartRunPoll(name, token, pill, stopButton);

  /* ---- Overview ---- */
  var tickets = data.tickets || [];
  var feedback = data.feedback || [];
  var tiles = el('div', {class: 'nv-tiles'});
  [
    ['open', nvpCount(tickets, 'offen'), tr('Offene Pakete')],
    ['waiting', nvpCount(tickets, 'WARTET AUF MERGE'), tr('Wartet auf Merge')],
    ['blocked', nvpCount(tickets, 'BLOCKIERT'), tr('Blockiert')],
    ['proof', nvpCount(feedback, 'ohne Nachweis'), tr('Ohne Nachweis')],
    ['done', nvpCount(tickets, 'erledigt'), tr('Erledigt')],
    ['feedback', feedback.length, tr('Feedback')]
  ].forEach(function (tile) {
    tiles.append(el('div', {class: 'nv-card nv-tile', 'data-nv-tile': tile[0]},
      el('div', {class: 'nv-tile-num'}, String(tile[1])),
      el('div', {class: 'nv-tile-label'}, tile[2])));
  });
  panels.overview.append(tiles);

  panels.overview.append(el('div', {class: 'nv-card nv-kv'},
    el('h3', {}, tr('Zustand')),
    el('div', {}, tr('Letzter Commit') + ': '),
    el('code', {}, String(data.last || tr('Kein Commit vorhanden'))),
    el('div', {}, tr('Prüfung') + ': '
      + String(data.verify_cmd ? tr('Verfügbar') : tr('Nicht konfiguriert')))));

  var sessionBox = el('div', {'data-nv-sessions': ''},
    el('h3', {}, tr('Sitzungen')));
  var sessionRows = (view.sessions && (view.sessions.sessions || view.sessions.entries)) || [];
  if (!sessionRows.length) {
    sessionBox.append(el('p', {class: 'nv-muted'}, tr('Keine Sitzungen vorhanden')));
  }
  sessionRows.forEach(function (row) {
    var session = String(row.session || row.id || row.name || '');
    sessionBox.append(el('div', {class: 'nv-row nv-session-row'},
      el('span', {}, session),
      el('span', {class: 'nv-muted', 'data-nv-session-attach': ''},
        (row.package_id || row.worktree_path)
          ? tr('Paket ') + String(row.package_id || '?') + tr(' · Arbeitskopie ') + String(row.worktree_path || '?')
          : ''),
      nvpButton(tr('Fortsetzen'), 'session-resume', function () {
        nvpPost(name, '/api/sessions', {action: 'continue', session: session},
          'Sitzung fortgesetzt', token);
      })));
  });
  panels.overview.append(el('section', {class: 'nv-card'}, sessionBox,
    el('a', {class: 'nv-link', href: '#/project/' + enc + '/assistant'},
      tr('Leitfaden') + ' →')));

  /* ---- Work ---- */
  var newRow = el('div', {class: 'nv-row nv-work-actions'},
    nvpButton(tr('Paket anlegen'), 'new-package', function () {
      nvpOpenTicketForm(panels.work, token, {mode: 'package'});
    }, 'nv-primary'),
    nvpButton(tr('Bug melden'), 'new-bug', function () {
      nvpOpenTicketForm(panels.work, token, {mode: 'bug'});
    }),
    nvpButton(tr('Feedback geben'), 'new-feedback', function () {
      nvpOpenTicketForm(panels.work, token, {mode: 'feedback'});
    }));
  panels.work.append(newRow);

  var board = el('div', {class: 'nv-board'});
  ['open', 'waiting', 'blocked', 'proof', 'done'].forEach(function (column) {
    var rows = tickets.concat(feedback.map(function (row) {
      return Object.assign({}, row, {__feedback: true});
    })).filter(function (row) {
      return nvpStateColumn(String(row.state || '')) === column;
    });
    board.append(nvpBoardColumn(name, column, rows, token));
  });
  panels.work.append(board);

  var feedbackBox = el('section', {class: 'nv-card', 'data-nv-feedback': ''},
    el('h3', {}, tr('Feedback')));
  if (!feedback.length) {
    feedbackBox.append(el('p', {class: 'nv-muted'}, tr('Keine Einträge')));
  }
  feedback.forEach(function (row) {
    var isBug = nvpFeedbackKind(row) === 'bug';
    /* Drei Zeilen mit Abstand statt drei Inline-Spans: Art, Titel, Details. */
    feedbackBox.append(el('article', {class: 'nv-card nv-feedback-item',
      'data-nv-feedback-item': String(row.id || '')},
      el('div', {}, el('span', {class: 'nv-pill nv-kind'}, tr(isBug ? 'Bug' : 'Feedback'))),
      el('div', {class: 'nv-feedback-title'}, String(row.title || row.id || '')),
      el('div', {class: 'nv-muted nv-feedback-desc'}, String(row.description || ''))));
  });
  panels.work.append(feedbackBox);

  if (NV.feature('priority')) panels.work.append(nvpPriorityCard(name, token, view));

  /* ---- Output: nur Container, Inhalt kommt aus B2 ---- */
  if (window.NV && NV.output && typeof NV.output.render === 'function') {
    try { NV.output.render(name, panels.output); }
    catch (e) {
      panels.output.append(el('p', {class: 'nv-muted'}, tr('Ausgabe nicht verfügbar')));
    }
  } else {
    panels.output.append(el('p', {class: 'nv-muted'},
      tr('Ausgabe wird gerade aufgebaut …')));
  }

  /* ---- Assistant ---- */
  panels.assistant.append(nvpAssistantPanel(name, token, view.guide, view.autonomous));

  /* ---- Settings ---- */
  placeholders.forEach(function (node) { node.remove(); });
  panels.settings.append(nvpTeamSection(name, token, view.agents));
  panels.settings.append(nvpBasicsSection(name, token, data));
  panels.settings.append(nvpChecksSection(name, token, data));
  panels.settings.append(nvpPauseSection(name, token, data));
  panels.settings.append(nvpSessionsSection(name, token, view.sessions));
  if (NV.feature('github')) panels.settings.append(nvpGithubSection(name, token, data.github));
  if (NV.feature('writeaccess')) panels.settings.append(nvpRightsSection(name, token, data));
  if (NV.feature('sandbox')) panels.settings.append(nvpSandboxSection(name, token, data.sandbox));
  if (NV.feature('agentsfile')) panels.settings.append(nvpAgentsFileSection(name, token, view));

  if (!NV.stale(token)) panels[active].removeAttribute('hidden');
  NV.refreshBell();
};
