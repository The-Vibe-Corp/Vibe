/* AP22 — Aktivität (Meilenstein B): laufende Läufe, Sessions mit Limit und
 * Fortsetzen sowie offene Rückfragen mit Options- und Freitextantwort.
 *
 * Alle sichtbaren Zeichenketten laufen über tr()/bt(); Backend-Meldungen
 * bleiben unübersetzt, sondern werden über bt() nur für bekannte Dokumenttexte
 * umgeschaltet. DOM-only: Rückfrage- und Protokollinhalte werden ausschließlich
 * als Textknoten gesetzt, nie als innerHTML.
 */
'use strict';

/* Einheitlicher Leerzustand: eine kurze, freundliche Zeile pro Bereich —
   auch schon während des Ladens, damit die Karten nicht unfertig wirken. */
function nvActivityEmpty(message) {
  return el('p', {class: 'nv-muted nv-empty'}, message);
}

function nvQuestionCard(question, token, reload) {
  var id = String(question.id || '');

  function submit(body) {
    var payload = {action: 'answer', id: question.id};
    Object.keys(body).forEach(function (key) { payload[key] = body[key]; });
    api('/api/questions', payload).then(async function (result) {
      if (NV.stale(token)) return;
      toast(bt(result && result.message)
        || (result && result.ok ? tr('Antwort gespeichert') : tr('Antwort abgelehnt')));
      if (result && result.ok) {
        var fresh = await api('/api/questions');
        if (!NV.stale(token)) reload(fresh);
      }
      NV.refreshBell();
    }).catch(function (error) {
      toast(tr('Antwort nicht gesendet: ') + String(error && error.message || error));
    });
  }

  var options = (question.options || []).map(function (text, index) {
    var button = el('button', {class: 'nv-btn nv-primary', type: 'button',
      'data-nv-answer': String(index + 1)}, String(text));
    /* 1-basierter DOM-Hook, 0-basierter API-Index (wie in der klassischen UI). */
    button.addEventListener('click', function () { submit({option: index}); });
    return button;
  });

  var field = null;
  var send = null;
  if (question.free_text !== false) {
    field = el('input', {type: 'text', 'data-nv-field': 'answer', maxlength: '4000',
      placeholder: tr('Eigene Antwort …'),
      'aria-label': tr('Eigene Antwort zu ') + id});
    send = el('button', {class: 'nv-btn', type: 'button', 'data-nv-action': 'answer'},
      tr('Antwort senden'));
    var sendFree = function () {
      var text = String(field.value || '').trim();
      if (!text) { field.focus(); return; }
      submit({text: text});
    };
    send.addEventListener('click', sendFree);
    field.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') { event.preventDefault(); sendFree(); }
    });
  }

  return el('article', {class: 'nv-card nv-question', 'data-nv-question': id},
    el('div', {class: 'nv-question-head'},
      el('span', {class: 'nv-pill'}, tr('Rückfrage')),
      question.project ? el('span', {class: 'nv-muted'}, String(question.project)) : null,
      question.agent ? el('span', {class: 'nv-muted'}, tr('Agent: ') + String(question.agent)) : null),
    el('p', {class: 'nv-question-text'}, String(question.text || '')),
    options.length ? el('div', {class: 'nv-question-options'}, options) : null,
    field ? el('div', {class: 'nv-question-free'}, field, send) : null);
}

NV.views.activity = function activity(context, token) {
  if (NV.stale(token)) return;

  /* Zusammenfassung: dieselben Quellen wie die Glocke. Die Kacheln entstehen
     erst mit den echten Zahlen, damit nie ein veralteter Wert sichtbar wird. */
  var tilesBox = el('div', {class: 'nv-tiles', 'data-nv-activity-tiles': ''});
  var questionsBody = el('div', {class: 'nv-questions-body'},
    nvActivityEmpty(tr('Keine offenen Fragen — nichts wartet auf deine Antwort.')));
  var runsBody = el('div', {class: 'nv-runs-body'},
    nvActivityEmpty(tr('Gerade läuft keine Arbeit.')));
  var sessionsBody = el('div', {class: 'nv-sessions-body'},
    nvActivityEmpty(tr('Projekt wählen, um seine Sitzungen zu sehen.')));

  /* Rückfragen: Das Projekt steht auf jeder Karte; der Filter wendet die
     Projektwahl auf die Liste an — „Alle Projekte“ zeigt die vollständige
     Liste. Der letzte Stand liegt in questionsData, paintQuestions bekommt
     ihn über diese Variable, wenn sich die Projektwahl ändert. */
  var questionFilter = '';
  var questionsData = null;
  var questionsHint = el('p', {class: 'nv-muted', 'data-nv-questions-hint': ''},
    tr('Offene Rückfragen aller Projekte — das Projekt steht auf jeder Karte'));
  /* Versteckt bis die Projekte geladen sind: wait_for(visible) beim Test-
     und Nutzerzugriff geht erst dann — erst dann gibt es Auswahlmöglichkeiten
     („Alle Projekte“ + Projekte). */
  var questionProjectSelect = el('select', {
    'data-nv-questions-project': '', 'aria-label': tr('Rückfragen nach Projekt filtern'),
    hidden: ''});
  questionProjectSelect.addEventListener('change', function () {
    questionFilter = questionProjectSelect.value;
    if (questionsData) paintQuestions(questionsData);
  });

  var projectSelect = el('select', {'data-nv-sessions-project': '',
    'aria-label': tr('Projekt auswählen')});
  var limitInput = el('input', {type: 'number', min: '1', max: '100',
    'data-nv-sessions-limit': '', value: '5', 'aria-label': tr('Session-Limit')});
  var limitHint = el('small', {'data-nv-limit-hint': ''},
    tr('Gilt für das oben ausgewählte Projekt und begrenzt die Anzahl gelisteter Sitzungen'));
  var limitSave = el('button', {class: 'nv-btn', type: 'button',
    'data-nv-action': 'sessions-limit-save'}, tr('Limit speichern'));

  document.getElementById('nv-main').replaceChildren(
    el('h2', {class: 'nv-page-title'}, tr('Aktivität')),
    tilesBox,
    el('section', {class: 'nv-card', 'data-nv-questions': ''},
      el('h3', {}, tr('Rückfragen')), questionProjectSelect, questionsHint, questionsBody),
    el('section', {class: 'nv-card', 'data-nv-runs': ''},
      el('h3', {}, tr('Läufe')), runsBody),
    el('section', {class: 'nv-card', 'data-nv-sessions': ''},
      el('h3', {}, tr('Sessions')), projectSelect, sessionsBody,
      el('div', {class: 'nv-row nv-sessions-limit'},
        el('label', {}, tr('Session-Limit')), limitInput, limitHint, limitSave)));

  /* ---------- Zusammenfassung und Läufe (eine gemeinsame Quelle) ---------- */
  NV.pulse().then(function (p) {
    if (NV.stale(token)) return;
    var tiles = el('div', {class: 'nv-tiles'});
    [
      ['running', p.running.length, tr('Laufend')],
      ['questions', p.questions.length, tr('Offene Fragen')],
      ['blocked', p.blocked.length, tr('Blockiert')]
    ].forEach(function (tile) {
      tiles.append(el('div', {class: 'nv-card nv-tile', 'data-nv-tile': tile[0]},
        el('div', {class: 'nv-tile-num'}, String(tile[1])),
        el('div', {class: 'nv-tile-label'}, tile[2])));
    });
    tilesBox.replaceChildren(tiles);

    var list = el('div', {class: 'nv-run-list'});
    if (!p.running.length) {
      list.append(nvActivityEmpty(tr('Gerade läuft keine Arbeit.')));
    }
    p.running.forEach(function (row) {
      var name = String(row.name);
      var stop = el('button', {class: 'nv-btn nv-danger', type: 'button',
        'data-nv-action': 'stop-run'}, tr('Stopp'));
      stop.addEventListener('click', async function () {
        if (!window.confirm(String(tr('Lauf wirklich stoppen?')) + ' ' + name)) return;
        try {
          var result = await api('/api/stop', {name: name});
          if (NV.stale(token)) return;
          toast(bt(result && result.message)
            || (result && result.ok ? tr('Lauf gestoppt.') : tr('Stoppen fehlgeschlagen.')));
          if (!NV.stale(token)) NV.render();
        } catch (error) {
          toast(tr('Stoppen fehlgeschlagen: ') + String(error && error.message || error));
        }
      });
      list.append(el('div', {class: 'nv-run-row', 'data-nv-run': name},
        el('span', {class: 'nv-run-name'}, name),
        el('span', {class: 'nv-pill'}, tr('läuft')),
        el('a', {class: 'nv-btn', href: '#/project/' + encodeURIComponent(name) + '/output',
          'data-nv-action': 'open-output'}, tr('Öffnen')),
        stop));
    });
    runsBody.replaceChildren(list);
  }).catch(function (error) {
    if (!NV.stale(token)) runsBody.replaceChildren(
      el('p', {class: 'nv-muted'}, tr('Läufe konnten nicht geladen werden: ') + String(error && error.message || error)));
  });

  /* ---------- Sessions ---------- */
  function loadSessionsFor(name, limitField) {
    if (!name) { sessionsBody.replaceChildren(nvActivityEmpty(tr('Projekt wählen, um seine Sitzungen zu sehen.'))); return; }
    api('/api/sessions?name=' + encodeURIComponent(name)).then(function (data) {
      if (NV.stale(token)) return;
      var entries = (data && data.sessions) || [];
      limitField.value = String((data && data.limit) || 5);
      var list = el('div', {class: 'nv-session-list'});
      /* Projekt ist gewählt: hier gehört die Leeraussage hin, nicht der
         Hinweis „Projekt wählen“ (der gilt nur ohne Auswahl). */
      if (!entries.length) list.append(nvActivityEmpty(tr('Für dieses Projekt sind keine Sitzungen aufgezeichnet.')));
      var canResume = !!(data && data.resume_supported) && !(data && data.running);
      entries.forEach(function (entry) {
        var resume = null;
        if (canResume) {
          resume = el('button', {class: 'nv-btn', type: 'button',
            'data-nv-action': 'session-resume',
            'aria-label': tr('Session fortsetzen') + ' ' + String(entry.session)},
            tr('Fortsetzen'));
          resume.addEventListener('click', async function () {
            try {
              var result = await api('/api/sessions', {
                name: name, session: String(entry.session), action: 'continue'});
              toast(bt(result && result.message)
                || (result && result.ok ? tr('Der Lauf wird fortgesetzt.') : tr('Fortsetzen abgelehnt.')));
            } catch (error) {
              toast(tr('Fortsetzen nicht gesendet: ') + String(error && error.message || error));
            }
          });
        }
        list.append(el('div', {class: 'nv-session-row'},
          el('span', {class: 'nv-session-id'}, String(entry.session)),
          el('span', {class: 'nv-muted'}, String(entry.agent || '')),
          resume));
      });
      if (entries.length && data && data.resume_supported === false) {
        list.append(el('p', {class: 'nv-muted'},
          tr('Fortsetzen ist bei Pi nicht möglich (--no-session): Pi läuft ohne fortsetzbare Session.')));
      }
      sessionsBody.replaceChildren(list);
    }).catch(function (error) {
      if (!NV.stale(token)) sessionsBody.replaceChildren(
        el('p', {class: 'nv-muted'}, tr('Sessions konnten nicht geladen werden: ') + String(error && error.message || error)));
    });
  }

  api('/api/projects').then(function (rows) {
    if (NV.stale(token)) return;
    var names = (rows || []).map(function (row) { return String(row.name); });
    projectSelect.replaceChildren.apply(projectSelect, names.map(function (name) {
      return el('option', {value: name}, name);
    }));
    questionProjectSelect.replaceChildren.apply(questionProjectSelect,
      [el('option', {value: ''}, tr('Alle Projekte'))]
        .concat(names.map(function (name) { return el('option', {value: name}, name); })));
    questionFilter = '';
    questionProjectSelect.value = '';
    questionProjectSelect.hidden = false;
    if (names.length) {
      projectSelect.value = names[0];
      loadSessionsFor(names[0], limitInput);
    } else {
      sessionsBody.replaceChildren(nvActivityEmpty(tr('Projekt wählen, um seine Sitzungen zu sehen.')));
    }
  }).catch(function (error) {
    if (!NV.stale(token)) sessionsBody.replaceChildren(
      el('p', {class: 'nv-muted'}, tr('Sessions konnten nicht geladen werden: ') + String(error && error.message || error)));
  });

  projectSelect.addEventListener('change', function () {
    loadSessionsFor(projectSelect.value, limitInput);
  });

  limitSave.addEventListener('click', async function () {
    var raw = String(limitInput.value || '').trim();
    var value = Number(raw);
    if (!Number.isInteger(value) || value < 1 || value > 100) {
      toast(tr('Session-Limit ist ungültig.'));
      return;
    }
    try {
      var result = await api('/api/sessions', {
        name: projectSelect.value, action: 'limit', limit: value});
      toast(bt(result && result.message)
        || (result && result.ok ? tr('Limit gespeichert')
          : tr('Limit konnte nicht gespeichert werden: ') + String(result && result.message || '')));
    } catch (error) {
      toast(tr('Limit konnte nicht gespeichert werden: ') + String(error && error.message || error));
    }
  });

  /* ---------- Rückfragen ---------- */
  function paintQuestions(data) {
    questionsData = data || {};
    var list = (questionsData.questions || [])
      .filter(function (question) {
        return !questionFilter || String(question.project || '') === questionFilter;
      })
      .map(function (question) {
        return nvQuestionCard(question, token, paintQuestions);
      });
    if (!list.length) list.push(nvActivityEmpty(tr('Keine offenen Fragen — nichts wartet auf deine Antwort.')));
    questionsBody.replaceChildren.apply(questionsBody, list);
  }
  api('/api/questions').then(function (data) {
    if (!NV.stale(token)) paintQuestions(data);
  }).catch(function (error) {
    if (!NV.stale(token)) questionsBody.replaceChildren(
      el('p', {class: 'nv-muted'}, tr('Rückfragen konnten nicht geladen werden: ') + String(error && error.message || error)));
  });

  NV.refreshBell();
};
