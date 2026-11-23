/* F34 WP3 — Aktivität: Kacheln, zentrale Rückfragen und Läufe.
 *
 * Rückfragen kommen aus der gemeinsamen Quelle NV.questions und werden mit
 * NV.questionCard gezeichnet; die Aktivität hält keine eigene Karte mehr.
 * Die Sektion Sessions samt Session-Limit ist bewusst entfernt — Sitzungen
 * werden im jeweiligen Projekt (Überblick) gepflegt.
 *
 * Alle sichtbaren Zeichenketten laufen über tr()/bt(); DOM nur mit el() und
 * Textknoten, nie innerHTML mit dynamischen Inhalten.
 */
'use strict';

/* Einheitlicher Leerzustand: eine kurze, freundliche Zeile pro Bereich —
   auch schon während des Ladens, damit die Karten nicht unfertig wirken. */
function nvActivityEmpty(message) {
  return el('p', {class: 'nv-muted nv-empty'}, message);
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

  /* Rückfragen: Das Projekt steht auf jeder Karte; der Filter wendet die
     Projektwahl auf die Liste an — „Alle Projekte“ zeigt die vollständige
     Liste. Der letzte Stand liegt in questionsData. */
  var questionFilter = '';
  var questionsData = [];
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
    paintQuestions();
  });

  var sessionsHint = el('p', {class: 'nv-muted', 'data-nv-activity-sessions-hint': ''},
    tr('Sitzungen findest du im jeweiligen Projekt (Überblick).'), ' ',
    el('a', {href: '#/'}, tr('Zu den Projekten')));

  document.getElementById('nv-main').replaceChildren(
    el('h2', {class: 'nv-page-title'}, tr('Aktivität')),
    tilesBox,
    el('section', {class: 'nv-card', 'data-nv-questions': ''},
      el('h3', {}, tr('Rückfragen')), questionProjectSelect, questionsHint, questionsBody),
    el('section', {class: 'nv-card', 'data-nv-runs': ''},
      el('h3', {}, tr('Läufe')), runsBody),
    sessionsHint);

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

  /* ---------- Rückfragen (gemeinsame Quelle + gemeinsame Karte) ---------- */
  function paintQuestions() {
    var list = questionsData.filter(function (question) {
      return !questionFilter || String(question.project || '') === questionFilter;
    }).map(function (question) {
      return NV.questionCard(question, {
        onAnswered: function (answered) {
          questionsData = questionsData.filter(function (item) {
            return String(item.id) !== String(answered && answered.id);
          });
          paintQuestions();
        }
      });
    });
    if (!list.length) {
      list.push(nvActivityEmpty(tr('Keine offenen Fragen — nichts wartet auf deine Antwort.')));
    }
    questionsBody.replaceChildren.apply(questionsBody, list);
  }

  var lastSignature = null;
  function loadQuestions() {
    var source = NV.questions && typeof NV.questions.list === 'function'
      ? NV.questions.list() : [];
    var list = Array.isArray(source) ? source : [];
    var signature = list.map(function (question) {
      return [question.id, question.text, question.project, question.agent].join(':');
    }).join('|');
    if (signature === lastSignature) return;
    lastSignature = signature;
    questionsData = list.slice();
    if (!NV.stale(token)) paintQuestions();
  }

  var refresh = NV.questions && typeof NV.questions.refresh === 'function'
    ? NV.questions.refresh() : Promise.resolve();
  Promise.resolve(refresh).then(loadQuestions).catch(function (error) {
    if (!NV.stale(token)) questionsBody.replaceChildren(
      el('p', {class: 'nv-muted'}, tr('Rückfragen konnten nicht geladen werden: ') + String(error && error.message || error)));
  });
  loadQuestions();

  /* Die gemeinsame Quelle wird per Poll im Kern aktualisiert. Solange diese
     Ansicht aktiv ist, übernehmen wir neue Stände lokal — ohne Voll-Neurender
     und ohne eine zweite Kopie der Frage-Karte. */
  var poll = setInterval(function () {
    if (NV.stale(token)) { clearInterval(poll); return; }
    loadQuestions();
  }, 1000);

  /* Die Projektauswahl benötigt die Projektnamen; bis sie da ist, bleibt sie
     verborgen. Die Liste selbst stammt weiterhin aus NV.questions. */
  api('/api/projects').then(function (rows) {
    if (NV.stale(token)) return;
    var names = (rows || []).map(function (row) { return String(row.name); });
    questionProjectSelect.replaceChildren.apply(questionProjectSelect,
      [el('option', {value: ''}, tr('Alle Projekte'))]
        .concat(names.map(function (name) { return el('option', {value: name}, name); })));
    questionFilter = '';
    questionProjectSelect.value = '';
    questionProjectSelect.hidden = false;
  }).catch(function (error) {
    if (!NV.stale(token)) questionsBody.replaceChildren(
      el('p', {class: 'nv-muted'}, tr('Rückfragen konnten nicht geladen werden: ') + String(error && error.message || error)));
  });

  NV.refreshBell();
};

/* F34 WP3: neue Texte dieser Ansicht (Schlüssel = deutscher Quelltext). */
if (window.VIBE_I18N && typeof VIBE_I18N.extend === 'function') {
  VIBE_I18N.extend({
    en: {
      'Sitzungen findest du im jeweiligen Projekt (Überblick).':
        'You will find sessions in each project (Overview).',
      'Zu den Projekten': 'Go to projects'
    },
    de: {
      'Sitzungen findest du im jeweiligen Projekt (Überblick).':
        'Sitzungen findest du im jeweiligen Projekt (Überblick).',
      'Zu den Projekten': 'Zu den Projekten'
    }
  });
}
