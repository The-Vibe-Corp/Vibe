/* AP22/F34 — Live-Ausgabe (Meilenstein B): Hauptagent, laufende Subagenten,
 * Fokus, Steuern, Fortsetzen und Stoppen.
 *
 * Der Router der neuen Shell kennt keine eigene Output-Route: `#/project/<name>/output`
 * landet als Tab in der Projektansicht. `nova-project.js` (B1) delegiert für das
 * Panel `[data-nv-ppanel="output"]` an `NV.output.render(name, panelRoot)`. Genau
 * dieser Hook wird hier registriert. Zusätzlich dekoriert dieses Modul den
 * Projekt-Renderer, damit die Ausgabe auch mit dem älteren Projekt-Stub im
 * Output-Tab erscheint. Beide Wege laufen über dieselbe, idempotente
 * Renderfunktion; ein zweiter Aufruf räumt Timer/Stream des ersten auf.
 *
 * Protokollinhalte werden ausschließlich als Textknoten gesetzt — nie als
 * innerHTML. Die Syntaxhervorhebung entspricht der klassischen Ansicht
 * (`renderLogChunk`/`hlLine` aus app.js, F19/AP16): nur `span`-Knoten mit
 * `hl-*`-Klassen, deren Farben nova.css für beide Themes definiert. Zeilen mit
 * Markup-Zeichen bleiben als ein einziger Textknoten wörtlich sichtbar.
 *
 * F34/WP6: Eine kompakte, horizontal scrollende Kopfzusammenfassung zeigt
 * Hauptagent und Subagenten mit Name, Rolle, Zustand, Modell und Sitzung; jede
 * Zeile fokussiert die zugehörige Ausgabe. Haupt- und Subagenten-Protokolle
 * haben eine begrenzte Höhe mit eigenem Scroll und „Alles anzeigen“. Styles,
 * die nova.css (WP1) nicht hergibt, werden lokal über `style` gesetzt — keine
 * CSS-Datei eines anderen WP wird berührt.
 */
'use strict';

/* F19/AP16: Hervorhebung ist reine Darstellung — der Protokolltext bleibt
   unverändert. Die Inline-Treffer werden in Text + span-Knoten zerlegt. */
var NV_HL_INLINE = /(`[^`\n]+`|"[^"\n]+"|\b[0-9a-f]{7,40}\b|(?:[A-Za-z0-9_.\/-]+\/)*[A-Za-z0-9_.-]+\.(?:py|js|css|html|sh|md|json|ya?ml|toml|env|png|txt|log|cfg|ini)\b|\b\d+(?:[.,]\d+)?\b)/g;

function nvHlLineClass(line) {
  if (/^===.*===\s*$/.test(line) || /^diff --git |^@@ /.test(line)) return 'hl-head';
  if (/^\[Fehler\]/.test(line)) return 'hl-err';
  if (/^\[Subagent\]/.test(line)) return 'hl-sub';
  if (/^\[Werkzeug\]/.test(line)) return 'hl-tool';
  if (/^\[Denken\]/.test(line)) return 'hl-think';
  if (/^\s*(?:\$|>)\s/.test(line)) return 'hl-cmd';
  if (/^\+[^ ]/.test(line)) return 'hl-add';
  if (/^-[^ ]/.test(line)) return 'hl-del';
  return '';
}

function nvHlLine(line) {
  var cls = nvHlLineClass(line);
  var span = el('span', cls ? {class: cls} : {});
  /* AP16/AK4: Zeilen mit Markup-Zeichen bleiben ein ungeteilter Textknoten,
     damit "<b>not markup</b>" wörtlich erscheint und nie als HTML gilt. */
  if (/[<>]/.test(line)) { span.append(document.createTextNode(line)); return span; }
  var last = 0;
  var match;
  NV_HL_INLINE.lastIndex = 0;
  while ((match = NV_HL_INLINE.exec(line))) {
    if (match.index > last) span.append(document.createTextNode(line.slice(last, match.index)));
    var token = match[0];
    var kind = 'hl-num';
    if (token[0] === '`') kind = 'hl-code';
    else if (token[0] === '"') kind = 'hl-str';
    else if (/^[0-9a-f]{7,40}$/.test(token)) kind = 'hl-sha';
    else if (/\.[A-Za-z0-9]+$/.test(token)) kind = 'hl-path';
    span.append(el('span', {class: kind}, token));
    last = NV_HL_INLINE.lastIndex;
  }
  if (last < line.length) span.append(document.createTextNode(line.slice(last)));
  return span;
}

function nvRenderLog(text) {
  var frag = document.createDocumentFragment();
  String(text).split('\n').forEach(function (line, index) {
    if (index) frag.append(document.createTextNode('\n'));
    if (line) frag.append(nvHlLine(line));
  });
  return frag;
}

/* F34: kompakte, aber eindeutige Sitzungsanzeige. Der volle Wert bleibt im
   title, damit gekürzte Kennungen nicht unverständlich werden. */
function nvOutShort(value, max) {
  var text = String(value || '');
  var limit = max || 18;
  if (text.length <= limit) return text;
  return text.slice(0, limit - 1) + '…';
}

/* GH-88: Autoscroll nur am Fuß. Jedes Protokoll merkt sich, ob der Nutzer
   am aktuellen Ende ist; neue Zeilen folgen nur dann. Programmgesteuerte
   Scrolls werden über ein Guard-Flag vom Nutzer-Scroll getrennt, damit sie
   den Folgemodus nicht versehentlich umschalten. */
var NV_OUT_FOLLOW_THRESHOLD = 24;

function nvOutFollow(log) {
  var state = {follow: true, guard: false};
  function atEnd() {
    return log.scrollTop + log.clientHeight
      >= log.scrollHeight - NV_OUT_FOLLOW_THRESHOLD;
  }
  function releaseGuard() {
    if (state.guard && typeof window.requestAnimationFrame === 'function') {
      window.requestAnimationFrame(function () { state.guard = false; });
    } else {
      state.guard = false;
    }
  }
  log.addEventListener('scroll', function () {
    if (state.guard) return;
    state.follow = atEnd();
  });
  /* Neue Karten starten am Ende. Fokus/Expand prüfen die Position neu, statt
     eine vom Nutzer gewählte Stelle zu verschieben. */
  state.refresh = function () {
    state.follow = atEnd();
    if (!state.follow) return;
    state.guard = true;
    log.scrollTop = log.scrollHeight;
    releaseGuard();
  };
  state.write = function (fragment) {
    /* Vor dem Neuaufbau die aktuelle Position auswerten: so zählt auch ein
       Nutzer-Scroll, dessen Event noch nicht verarbeitet wurde. */
    var wasFollow = atEnd();
    var previousTop = log.scrollTop;
    state.guard = true;
    log.replaceChildren(fragment);
    if (wasFollow) {
      log.scrollTop = log.scrollHeight;
    } else {
      /* replaceChildren setzt scrollTop auf 0 zurück; die Nutzerposition
         bleibt erhalten (auf den neuen Inhalt begrenzt). */
      log.scrollTop = Math.min(previousTop,
        Math.max(0, log.scrollHeight - log.clientHeight));
    }
    state.follow = wasFollow;
    releaseGuard();
  };
  log.__nvFollow = state;
  return state;
}

var NV_OUTPUT = {
  timer: null,
  stream: null,
  keyHandler: null,
  heroStop: null,
  stamp: 0
};

function nvOutCleanup() {
  if (NV_OUTPUT.timer) { clearInterval(NV_OUTPUT.timer); NV_OUTPUT.timer = null; }
  if (NV_OUTPUT.stream) {
    try { NV_OUTPUT.stream.close(); } catch (error) { /* bereits geschlossen */ }
    NV_OUTPUT.stream = null;
  }
  if (NV_OUTPUT.keyHandler) {
    document.removeEventListener('keydown', NV_OUTPUT.keyHandler);
    NV_OUTPUT.keyHandler = null;
  }
  /* Der Held der Projektansicht trägt denselben Stop-Hook. Solange die
     Ausgabe aktiv ist, gehört der Hook dem Stop-Knopf der Ausgabe; der
     Held behält seinen Klick-Handler und bekommt den Hook beim Aufräumen
     zurück. */
  if (NV_OUTPUT.heroStop && NV_OUTPUT.heroStop.isConnected) {
    NV_OUTPUT.heroStop.setAttribute('data-nv-action', 'stop');
    NV_OUTPUT.heroStop.removeAttribute('data-nv-hero-stop');
  }
  NV_OUTPUT.heroStop = null;
  document.body.classList.remove('nv-out-enlarged-open');
}

NV.output = {
  /* Öffentlicher Vertrag für nova-project.js: render(name, panelRoot).
     `token` ist optional und wird nur vom internen Render-Schutz genutzt. */
  render: function renderOutput(name, panelRoot, token) {
    name = String(name || '');
    if (!panelRoot) return;
    if (token !== undefined && NV.stale(token)) return;

    /* nova-project.js ruft den Hook für alle Tabs. Nur der sichtbare
       Output-Tab bekommt Stream und Steuerung; andere Tabs bleiben leicht. */
    var hidden = panelRoot.hidden === true
      || !!(panelRoot.closest && panelRoot.closest('[hidden]'));
    if (hidden) {
      nvOutCleanup();
      panelRoot.replaceChildren(el('div', {class: 'nv-out nv-out-placeholder'},
        el('p', {class: 'nv-muted'}, tr('Ausgabe'))));
      return;
    }

    nvOutCleanup();
    var existingStop = document.querySelector('[data-nv-action="stop"]');
    if (existingStop) {
      NV_OUTPUT.heroStop = existingStop;
      existingStop.removeAttribute('data-nv-action');
      existingStop.setAttribute('data-nv-hero-stop', '');
    }
    var stamp = ++NV_OUTPUT.stamp;
    function alive() {
      return stamp === NV_OUTPUT.stamp && panelRoot.isConnected
        && (token === undefined || !NV.stale(token));
    }

    var running = false;
    var isPi = false;
    var mainText = '';
    var focusTarget = '';
    var mainSession = '';
    var mainModel = '';
    var mainAgent = '';
    var cards = {};
    var summaryRows = {};
    var expanded = {main: false};
    var lastRunning = null;

    /* ---------- DOM (rein deklarativ, keine Protokoll-innerHTML) ---------- */

    /* F34: Die Zusammenfassung scrollt horizontal, nicht die Seite. Jede Zeile
       ist ein Knopf, der die passende Ausgabe fokussiert und anscrollt. */
    var summary = el('div', {
      class: 'nv-out-summary', 'data-nv-out-summary': '', role: 'group',
      'aria-label': tr('Zusammenfassung'),
      style: 'display:flex; flex-wrap:nowrap; gap:var(--nv-space-3); '
        + 'overflow-x:auto; overflow-y:hidden; max-width:100%; '
        + 'padding-bottom:var(--nv-space-2);'
    });

    function makeSummaryRow(target) {
      var name = el('b', {class: 'nv-out-sum-name'}, '');
      var role = el('span', {class: 'nv-out-sum-role nv-muted', title: tr('Rolle/Agent')}, '');
      var state = el('span', {class: 'nv-pill', 'data-state': 'stopped'}, tr('gestoppt'));
      var model = el('span', {class: 'nv-out-sum-model nv-muted', title: tr('Modell')}, '–');
      var session = el('code', {class: 'nv-out-sum-session', title: ''}, '–');
      var row = el('button', {
        class: 'nv-out-summary-row', type: 'button', 'data-nv-out-summary-row': '',
        'data-nv-summary-target': target, 'data-focus': 'false',
        style: 'flex:0 0 auto; display:flex; flex-wrap:nowrap; align-items:center; '
          + 'gap:var(--nv-space-2); padding:var(--nv-space-2) var(--nv-space-3); '
          + 'text-align:left; max-width:min(38rem,86vw); min-width:0;'
      }, name, role, state,
        el('span', {class: 'nv-muted'}, tr('Modell') + ': '), model,
        el('span', {class: 'nv-muted'}, tr('Sitzung') + ': '), session);
      row.addEventListener('click', function () { focusAndScroll(target); });
      summary.append(row);
      var entry = {node: row, name: name, role: role, state: state,
        model: model, session: session};
      summaryRows[target] = entry;
      return entry;
    }
    makeSummaryRow('main');

    var mainState = el('span', {class: 'nv-pill', 'data-nv-out-main-state': '', 'data-state': 'stopped'}, tr('gestoppt'));
    var mainSessionCode = el('code', {class: 'nv-out-session', 'data-nv-out-session': '', title: ''}, '–');
    var mainFocusText = el('span', {class: 'nv-out-focus-text'}, tr('Fokus'));
    var mainFocusButton = el('button', {class: 'nv-btn nv-ghost', type: 'button',
      'data-nv-action': 'out-focus', 'aria-label': tr('Hauptagent fokussieren'),
      'aria-expanded': 'false'},
      el('span', {class: 'nv-out-icon', 'aria-hidden': 'true'}, '⤢'), ' ', mainFocusText);
    var mainExpandText = el('span', {class: 'nv-out-expand-text'}, tr('Alles anzeigen'));
    var mainExpandButton = el('button', {class: 'nv-btn nv-ghost nv-out-expand', type: 'button',
      'data-nv-log-expand': '', 'data-nv-log-target': 'main', 'aria-expanded': 'false',
      'aria-label': tr('Hauptprotokoll alles anzeigen')},
      el('span', {class: 'nv-out-icon', 'aria-hidden': 'true'}, '↕'), ' ', mainExpandText);

    var mainLog = el('pre', {class: 'nv-log nv-out-main', 'data-nv-out-main': '',
      role: 'log', tabindex: '0', 'aria-label': tr('Hauptagent')});
    var mainFollow = nvOutFollow(mainLog);
    var mainWrap = el('section', {class: 'nv-card nv-out-main-wrap', 'data-nv-out-main-wrap': ''},
      el('div', {class: 'nv-out-main-head'},
        el('b', {}, tr('Hauptagent')), mainState,
        el('span', {class: 'nv-muted'}, tr('Sitzung') + ':'), mainSessionCode,
        el('span', {class: 'nv-out-spacer'}), mainExpandButton, mainFocusButton),
      mainLog);

    /* GH-88: Haupt- und Subagentenkarten liegen in einem gemeinsamen
       responsiven Raster. [data-nv-out-subs] bleibt als Container erhalten
       und nimmt per display:contents direkt am Raster teil. */
    var cardsGrid = el('div', {class: 'nv-out-cards', 'data-nv-out-cards': ''}, mainWrap);
    var subs = el('div', {class: 'nv-out-subs', 'data-nv-out-subs': ''});
    cardsGrid.append(subs);

    var resumeBox = el('section', {class: 'nv-card nv-out-resume', 'data-nv-out-resume': '',
      style: 'padding:var(--nv-space-4);'});
    resumeBox.hidden = true;

    var steerInput = el('input', {type: 'text', 'data-nv-steer': '',
      placeholder: tr('Anweisung an den Agenten'),
      'aria-label': tr('Anweisung an den Agenten')});
    var steerButton = el('button', {class: 'nv-btn nv-primary', type: 'button',
      'data-nv-action': 'steer'}, tr('Anweisung senden'));
    var continueButton = el('button', {class: 'nv-btn', type: 'button',
      'data-nv-action': 'continue', title: tr('Keine Sitzung – Fortsetzen nicht möglich.')},
      tr('Fortsetzen'));
    var continueHint = el('small', {class: 'nv-muted', 'data-nv-continue-hint': ''},
      tr('Sendet ‚weiter‘ an die laufende Sitzung'));
    var continueWrap = el('div', {class: 'nv-out-continue',
      style: 'display:flex; flex-direction:column; gap:2px; min-width:0;'},
      continueButton, continueHint);
    var stopButton = el('button', {class: 'nv-btn nv-danger', type: 'button',
      'data-nv-action': 'stop'}, tr('Stoppen'));
    var piNote = el('p', {class: 'nv-muted nv-out-pi-note'},
      tr('Bei Pi ist das Steuern nicht möglich: Pi läuft im Print-Modus (--no-session) ohne fortsetzbare Session.'));
    piNote.hidden = true;

    var controls = el('div', {class: 'nv-out-controls'},
      el('div', {class: 'nv-out-steer'}, steerInput, steerButton),
      el('div', {class: 'nv-out-actions'}, continueWrap, stopButton),
      piNote);
    stopButton.hidden = true;
    steerInput.hidden = true;
    steerButton.hidden = true;

    /* Steuerblock vor dem Log: auch bei langem Protokoll ohne Scrollen da. */
    panelRoot.replaceChildren(el('div', {class: 'nv-out'},
      summary, controls, cardsGrid, resumeBox));

    /* ---------- Fokus/Vergrößern: genau eine Ausgabe ist flächig ---------- */
    function setLogLimit(target) {
      var card = target === 'main' ? null : cards[target];
      var log = target === 'main' ? mainLog : (card && card.log);
      var button = target === 'main' ? mainExpandButton : (card && card.expandButton);
      var text = target === 'main' ? mainExpandText : (card && card.expandText);
      if (!log || !button || !text) return;
      var open = !!expanded[target];
      var focused = focusTarget === target;
      log.style.maxHeight = (open || focused) ? 'none' : (target === 'main' ? '60vh' : '40vh');
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
      setTx(text, tr(open ? 'Weniger anzeigen' : 'Alles anzeigen'));
      var follow = target === 'main' ? mainFollow : (card && card.follow);
      if (follow && follow.refresh) follow.refresh();
    }

    function applyFocus() {
      if (focusTarget !== 'main' && !cards[focusTarget]) focusTarget = '';
      Object.keys(cards).forEach(function (id) {
        var card = cards[id];
        var on = focusTarget === id;
        card.node.classList.toggle('nv-out-focused', on);
        card.node.classList.toggle('nv-out-enlarged', on);
        card.node.setAttribute('data-focus', on ? 'true' : 'false');
        card.focusButton.setAttribute('aria-expanded', on ? 'true' : 'false');
        setTx(card.focusText, tr(on ? 'Fokus aufheben' : 'Fokus'));
      });
      var mainOn = focusTarget === 'main';
      mainWrap.classList.toggle('nv-out-enlarged', mainOn);
      mainFocusButton.setAttribute('aria-expanded', mainOn ? 'true' : 'false');
      setTx(mainFocusText, tr(mainOn ? 'Fokus aufheben' : 'Fokus'));
      Object.keys(summaryRows).forEach(function (target) {
        summaryRows[target].node.setAttribute('data-focus',
          focusTarget === target ? 'true' : 'false');
      });
      document.body.classList.toggle('nv-out-enlarged-open', !!focusTarget);
      setLogLimit('main');
      Object.keys(cards).forEach(setLogLimit);
    }
    function toggleFocus(id) {
      focusTarget = focusTarget === id ? '' : id;
      applyFocus();
    }
    function focusAndScroll(target) {
      if (target !== 'main' && !cards[target]) return;
      toggleFocus(target);
      var node = target === 'main' ? mainWrap : cards[target].node;
      if (node && node.scrollIntoView) {
        try { node.scrollIntoView({block: 'nearest', inline: 'nearest', behavior: 'smooth'}); }
        catch (error) { node.scrollIntoView(); }
      }
    }
    mainFocusButton.addEventListener('click', function () { toggleFocus('main'); });
    mainExpandButton.addEventListener('click', function () {
      expanded.main = !expanded.main;
      setLogLimit('main');
    });
    NV_OUTPUT.keyHandler = function (event) {
      if (event.key === 'Escape' && focusTarget) {
        event.preventDefault();
        focusTarget = '';
        applyFocus();
      }
    };
    document.addEventListener('keydown', NV_OUTPUT.keyHandler);

    /* ---------- Protokollzeilen als Text ---------- */
    function feedMain(text) {
      if (!text) return;
      mainText = (mainText + text).slice(-120000);
      mainFollow.write(nvRenderLog(mainText));
    }

    function streamMain() {
      var query = '/api/stream?name=' + encodeURIComponent(name)
        + '&kind=run&t=' + encodeURIComponent(NV.token());
      var source;
      try { source = new EventSource(query); } catch (error) { return; }
      NV_OUTPUT.stream = source;
      source.onmessage = function (event) {
        if (!alive()) { source.close(); return; }
        var lines;
        try { lines = JSON.parse(event.data); } catch (error) { lines = [String(event.data)]; }
        var text = (Array.isArray(lines) ? lines.join('\n') : String(lines)) + '\n';
        feedMain(text);
      };
    }

    /* ---------- Zustand und Subagenten ---------- */
    function syncMainMeta() {
      var label = tr(running ? 'läuft' : 'gestoppt');
      mainState.setAttribute('data-state', running ? 'running' : 'stopped');
      setTx(mainState, label);

      var row = summaryRows.main;
      row.state.setAttribute('data-state', running ? 'running' : 'stopped');
      setTx(row.state, label);
      setTx(row.name, mainAgent || tr('Hauptagent'));
      setTx(row.role, tr('Hauptagent'));
      setTx(row.model, mainModel || '–');
      setTx(row.session, mainSession || '–');
      row.session.title = mainSession || '';
      mainSessionCode.textContent = mainSession || '–';
      mainSessionCode.title = mainSession || '';
    }

    function syncContinue() {
      var hasSession = !!mainSession;
      continueButton.disabled = !hasSession;
      continueButton.title = hasSession
        ? tr('Sitzung') + ': ' + mainSession
        : tr('Keine Sitzung – Fortsetzen nicht möglich.');
      setTx(continueHint, hasSession
        ? tr('Sendet ‚weiter‘ an die laufende Sitzung')
        : tr('Ohne Sitzung kann der Lauf nicht fortgesetzt werden.'));
    }

    function syncControls() {
      var canSteer = running && !isPi;
      steerInput.hidden = !canSteer;
      steerButton.hidden = !canSteer;
      stopButton.hidden = !running;
      piNote.hidden = !isPi;
      Object.keys(cards).forEach(function (id) { cards[id].steerRow.hidden = !canSteer; });
      syncContinue();
    }

    function pollState() {
      api('/api/run-state?name=' + encodeURIComponent(name)).then(function (data) {
        if (!alive()) return;
        running = !!(data && data.running);
        syncMainMeta();
        syncControls();
        if (lastRunning !== running) {
          lastRunning = running;
          loadSessions();
        }
      }).catch(function () { /* Laufzustand bleibt beim letzten Stand */ });
    }

    function setCardText(card, text) {
      card.text = String(text || '').slice(-120000);
      card.follow.write(nvRenderLog(card.text));
    }

    function syncSubRow(session, entry, status) {
      var row = summaryRows[session];
      if (!row) return;
      var text = tr(status === 'running' ? 'läuft' : 'gestoppt');
      row.state.setAttribute('data-state', status === 'running' ? 'running' : 'stopped');
      setTx(row.state, text);
      setTx(row.name, String(entry.agent || tr('Subagent')));
      setTx(row.role, String(entry.description || tr('Subagent')));
      setTx(row.model, String(entry.model || '–'));
      setTx(row.session, nvOutShort(session));
      row.session.title = session;
    }

    function makeCard(entry) {
      var session = String(entry.session || '');
      var status = el('span', {class: 'nv-pill', 'data-nv-sub-state': '', 'data-state': 'stopped'});
      var focusText = el('span', {class: 'nv-out-focus-text'}, tr('Fokus'));
      var focusButton = el('button', {class: 'nv-btn nv-ghost', type: 'button',
        'data-nv-sub-focus': '', 'aria-label': tr('Subagent fokussieren'),
        'aria-expanded': 'false'},
        el('span', {class: 'nv-out-icon', 'aria-hidden': 'true'}, '⤢'), ' ', focusText);
      var expandText = el('span', {class: 'nv-out-expand-text'}, tr('Alles anzeigen'));
      var expandButton = el('button', {class: 'nv-btn nv-ghost nv-out-expand', type: 'button',
        'data-nv-log-expand': '', 'data-nv-log-target': session, 'aria-expanded': 'false',
        'aria-label': tr('Subagentenprotokoll alles anzeigen')},
        el('span', {class: 'nv-out-icon', 'aria-hidden': 'true'}, '↕'), ' ', expandText);
      var log = el('pre', {class: 'nv-log nv-out-sub-log', role: 'log', tabindex: '0',
        'aria-label': tr('Subagent') + ': ' + String(entry.agent || '')});
      var follow = nvOutFollow(log);
      var subSteer = el('input', {type: 'text', 'data-nv-sub-steer': '',
        placeholder: tr('Anweisung an den Subagenten'),
        'aria-label': tr('Anweisung an den Subagenten')});
      var subSend = el('button', {class: 'nv-btn nv-secondary', type: 'button',
        'data-nv-sub-steer-send': ''}, tr('Anweisung senden'));
      var steerRow = el('div', {class: 'nv-out-sub-steer'}, subSteer, subSend);
      var sessionCode = el('code', {class: 'nv-out-sub-session'}, nvOutShort(session));
      sessionCode.title = session;
      var node = el('article', {class: 'nv-card nv-out-sub', 'data-nv-out-sub': session,
        'data-focus': 'false'},
        el('div', {class: 'nv-out-sub-head'},
          el('b', {class: 'nv-out-sub-name'}, String(entry.agent || tr('Subagent'))),
          el('span', {class: 'nv-out-sub-role nv-muted'}, String(entry.description || '')),
          status, sessionCode,
          el('span', {class: 'nv-out-spacer'}), expandButton, focusButton),
        log, steerRow);
      var card = {node: node, log: log, status: status, focusButton: focusButton,
        focusText: focusText, expandButton: expandButton, expandText: expandText,
        steerRow: steerRow, follow: follow, text: '', loading: false};
      cards[session] = card;
      expanded[session] = false;
      makeSummaryRow(session);
      syncSubRow(session, entry, entry.status);
      setLogLimit(session);
      focusButton.addEventListener('click', function () { toggleFocus(session); });
      expandButton.addEventListener('click', function () {
        expanded[session] = !expanded[session];
        setLogLimit(session);
      });
      steerRow.hidden = !(running && !isPi);
      subSend.addEventListener('click', async function () {
        var text = String(subSteer.value || '').trim();
        if (!text) { subSteer.focus(); toast(tr('Bitte eine Anweisung eingeben.')); return; }
        subSteer.value = '';
        try {
          var result = await api('/api/steer', {name: name, text: text, session: session});
          if (!alive()) return;
          toast(bt(result && result.message)
            || (result && result.ok ? tr('Anweisung übermittelt.') : tr('Anweisung abgelehnt.')));
        } catch (error) {
          if (!alive()) return;
          toast(tr('Anweisung nicht gesendet: ') + String(error && error.message || error));
        }
      });
      return card;
    }

    function loadCardOutput(entry) {
      var session = String(entry.session || '');
      var card = cards[session];
      if (!card || card.loading) return;
      card.loading = true;
      api('/api/subagent-output?name=' + encodeURIComponent(name)
        + '&session=' + encodeURIComponent(session)).then(function (data) {
        card.loading = false;
        if (!alive() || !card.node.isConnected) return;
        if (data && data.ok && data.text) setCardText(card, data.text);
        else if (!card.text && entry.output) setCardText(card, entry.output);
      }).catch(function () { card.loading = false; });
    }

    function pollAgents() {
      api('/api/subagents?name=' + encodeURIComponent(name)).then(function (data) {
        if (!alive()) return;
        var entries = (data && data.subagents) || [];
        var subsRunning = entries.filter(function (entry) {
          return entry && entry.session && entry.status === 'running';
        });
        mainSession = String((data && data.session) || '');
        mainModel = String((data && data.model) || '');
        mainAgent = String((data && data.agent) || '');
        syncMainMeta();
        syncContinue();

        var wanted = {};
        subsRunning.forEach(function (entry) { wanted[String(entry.session)] = entry; });
        Object.keys(cards).forEach(function (id) {
          if (wanted[id]) return;
          cards[id].node.remove();
          delete cards[id];
          delete expanded[id];
          if (summaryRows[id]) { summaryRows[id].node.remove(); delete summaryRows[id]; }
          if (focusTarget === id) focusTarget = '';
        });
        subsRunning.forEach(function (entry) {
          var session = String(entry.session);
          var card = cards[session] || makeCard(entry);
          if (!card.text && entry.output) setCardText(card, entry.output);
          setTx(card.status, tr(entry.status === 'running' ? 'läuft' : 'gestoppt'));
          card.status.setAttribute('data-state',
            entry.status === 'running' ? 'running' : 'stopped');
          syncSubRow(session, entry, entry.status);
          if (card.node.parentNode !== subs) subs.append(card.node);
        });
        subs.hidden = subsRunning.length === 0;
        applyFocus();
        subsRunning.forEach(loadCardOutput);
      }).catch(function () { /* Liste bleibt beim letzten Stand */ });
    }

    /* ---------- Resume beendeter Läufe: mit Kontext, nicht nackt ---------- */
    function renderResume(sessions) {
      var usable = (sessions || []).filter(function (row) {
        return row && (row.session || row.id);
      });
      resumeBox.replaceChildren();
      if (running || !usable.length) {
        resumeBox.hidden = true;
        return;
      }
      resumeBox.append(
        el('h3', {}, tr('Beendete Läufe fortsetzen')),
        el('p', {class: 'nv-muted'},
          tr('Diese Sitzungen sind beendet. Wähle eine Sitzung, um sie fortzusetzen.')));
      usable.forEach(function (row) {
        var session = String(row.session || row.id || '');
        var pkg = String(row.package_id || row.package || '');
        var context = (pkg ? tr('Paket') + ': ' + pkg + ' · ' : '') + tr('Sitzung') + ': ' + session;
        var button = el('button', {class: 'nv-btn', type: 'button',
          'data-nv-action': 'session-resume', 'data-nv-session': session,
          title: context + ' — ' + tr('Setzt diese Sitzung fort.')}, tr('Fortsetzen'));
        button.addEventListener('click', async function () {
          try {
            var result = await api('/api/sessions', {action: 'continue', session: session});
            if (!alive()) return;
            toast(bt(result && result.message)
              || (result && result.ok ? tr('Sitzung fortgesetzt.') : tr('Sitzung nicht fortgesetzt.')));
            loadSessions();
            pollState();
          } catch (error) {
            if (!alive()) return;
            toast(tr('Sitzung nicht fortgesetzt: ')
              + String(error && error.message || error));
          }
        });
        resumeBox.append(el('div', {class: 'nv-out-resume-row',
          style: 'display:flex; flex-wrap:wrap; align-items:center; '
            + 'gap:var(--nv-space-3); padding:var(--nv-space-3) 0; '
            + 'border-top:1px solid var(--nv-border);'},
          el('div', {style: 'flex:1 1 20rem; min-width:0;'},
            el('b', {}, context), el('br'),
            el('small', {class: 'nv-muted'},
              (row.state_label ? String(row.state_label) + ' · ' : '')
              + tr('Setzt diese Sitzung fort.'))),
          button));
      });
      resumeBox.hidden = false;
    }

    function loadSessions() {
      api('/api/sessions?name=' + encodeURIComponent(name)).then(function (data) {
        if (!alive()) return;
        renderResume((data && data.sessions) || []);
      }).catch(function () { /* Resume-Block bleibt beim letzten Stand */ });
    }

    function checkPi() {
      api('/api/server').then(function (data) {
        if (!alive()) return;
        isPi = String((data && data.harness) || '') === 'pi';
        syncControls();
      }).catch(function () { /* ohne Auskunft gilt opencode */ });
    }

    /* ---------- Steuerung ---------- */
    steerButton.addEventListener('click', async function () {
      var text = String(steerInput.value || '').trim();
      if (!text) { steerInput.focus(); toast(tr('Bitte eine Anweisung eingeben.')); return; }
      steerInput.value = '';
      try {
        var result = await api('/api/steer', {name: name, text: text});
        if (!alive()) return;
        toast(bt(result && result.message)
          || (result && result.ok ? tr('Anweisung übermittelt.') : tr('Anweisung abgelehnt.')));
      } catch (error) {
        toast(tr('Anweisung nicht gesendet: ') + String(error && error.message || error));
      }
    });

    continueButton.addEventListener('click', async function () {
      if (!mainSession) return;
      try {
        var result = await api('/api/continue', {name: name});
        if (!alive()) return;
        toast(bt(result && result.message)
          || (result && result.ok ? tr('Der Lauf wird fortgesetzt.') : tr('Fortsetzen abgelehnt.')));
      } catch (error) {
        toast(tr('Fortsetzen nicht gesendet: ') + String(error && error.message || error));
      }
    });

    stopButton.addEventListener('click', async function () {
      try {
        var result = await api('/api/stop', {name: name});
        if (!alive()) return;
        toast(bt(result && result.message) || (result && result.ok ? tr('Lauf gestoppt.') : tr('Stoppen fehlgeschlagen: ') + String(result && result.message || '')));
      } catch (error) {
        toast(tr('Stoppen fehlgeschlagen: ') + String(error && error.message || error));
      }
      pollState();
    });

    /* ---------- Start und Timer-Disziplin ---------- */
    syncMainMeta();
    syncContinue();
    streamMain();
    pollState();
    pollAgents();
    loadSessions();
    checkPi();
    NV_OUTPUT.timer = setInterval(function () { pollState(); pollAgents(); }, 2000);
  }
};

/* Der Router liefert aktuell keine eigene Output-Ansicht. Diese Definition
   hält den Weg für eine spätere Standalone-Route offen, ohne ihn zu erzwingen. */
NV.views.output = function outputView(context, token) {
  return NV.views.project({view: 'project', name: (context && context.name) || '', tab: 'output'}, token);
};

/* Auch der ältere Projekt-Stub soll die Ausgabe im Output-Tab zeigen. B1s
   endgültiger Renderer ruft den Hook selbst; die Marker-Prüfung verhindert
   dann eine doppelte Ausgabe. */
(function decorateProjectView() {
  var original = NV.views.project;
  if (typeof original !== 'function') return;
  NV.views.project = function (context, token) {
    var result = original.apply(this, arguments);
    return Promise.resolve(result).then(function () {
      if (NV.stale(token)) return;
      if (String((context && context.tab) || '') !== 'output') return;
      var panel = document.querySelector('section[data-nv-ppanel="output"]');
      if (!panel || panel.querySelector('[data-nv-out-cards]')) return;
      NV.output.render((context && context.name) || '', panel, token);
    });
  };
})();

/* F34/WP6: Übersetzungen gehören zur Ansicht. Schlüssel sind die deutschen
   Quelltexte, `de` ist die Identität, `en` die englische Fassung. WP1 stellt
   VIBE_I18N.extend bereit; mehrfaches Erweitern ist erlaubt. */
if (window.VIBE_I18N && typeof VIBE_I18N.extend === 'function') {
  VIBE_I18N.extend({
    de: {
      'Ausgabe': 'Ausgabe',
      'gestoppt': 'gestoppt',
      'läuft': 'läuft',
      'Hauptagent': 'Hauptagent',
      'Hauptagent fokussieren': 'Hauptagent fokussieren',
      'Fokus': 'Fokus',
      'Fokus aufheben': 'Fokus aufheben',
      'Alles anzeigen': 'Alles anzeigen',
      'Weniger anzeigen': 'Weniger anzeigen',
      'Hauptprotokoll alles anzeigen': 'Hauptprotokoll alles anzeigen',
      'Subagentenprotokoll alles anzeigen': 'Subagentenprotokoll alles anzeigen',
      'Anweisung an den Agenten': 'Anweisung an den Agenten',
      'Anweisung an den Subagenten': 'Anweisung an den Subagenten',
      'Anweisung senden': 'Anweisung senden',
      'Bitte eine Anweisung eingeben.': 'Bitte eine Anweisung eingeben.',
      'Anweisung übermittelt.': 'Anweisung übermittelt.',
      'Anweisung abgelehnt.': 'Anweisung abgelehnt.',
      'Anweisung nicht gesendet: ': 'Anweisung nicht gesendet: ',
      'Fortsetzen': 'Fortsetzen',
      'Sendet ‚weiter‘ an die laufende Sitzung': 'Sendet ‚weiter‘ an die laufende Sitzung',
      'Keine Sitzung – Fortsetzen nicht möglich.': 'Keine Sitzung – Fortsetzen nicht möglich.',
      'Ohne Sitzung kann der Lauf nicht fortgesetzt werden.': 'Ohne Sitzung kann der Lauf nicht fortgesetzt werden.',
      'Der Lauf wird fortgesetzt.': 'Der Lauf wird fortgesetzt.',
      'Fortsetzen abgelehnt.': 'Fortsetzen abgelehnt.',
      'Fortsetzen nicht gesendet: ': 'Fortsetzen nicht gesendet: ',
      'Stoppen': 'Stoppen',
      'Lauf gestoppt.': 'Lauf gestoppt.',
      'Stoppen fehlgeschlagen: ': 'Stoppen fehlgeschlagen: ',
      'Bei Pi ist das Steuern nicht möglich: Pi läuft im Print-Modus (--no-session) ohne fortsetzbare Session.': 'Bei Pi ist das Steuern nicht möglich: Pi läuft im Print-Modus (--no-session) ohne fortsetzbare Session.',
      'Subagent': 'Subagent',
      'Subagent fokussieren': 'Subagent fokussieren',
      ' Subagenten': ' Subagenten',
      'Keine laufenden Subagenten.': 'Keine laufenden Subagenten.',
      'Zusammenfassung': 'Zusammenfassung',
      'Rolle/Agent': 'Rolle/Agent',
      'Modell': 'Modell',
      'Sitzung': 'Sitzung',
      'Beendete Läufe fortsetzen': 'Beendete Läufe fortsetzen',
      'Diese Sitzungen sind beendet. Wähle eine Sitzung, um sie fortzusetzen.': 'Diese Sitzungen sind beendet. Wähle eine Sitzung, um sie fortzusetzen.',
      'Paket': 'Paket',
      'Setzt diese Sitzung fort.': 'Setzt diese Sitzung fort.',
      'Sitzung fortgesetzt.': 'Sitzung fortgesetzt.',
      'Sitzung nicht fortgesetzt.': 'Sitzung nicht fortgesetzt.',
      'Sitzung nicht fortgesetzt: ': 'Sitzung nicht fortgesetzt: '
    },
    en: {
      'Ausgabe': 'Output',
      'gestoppt': 'stopped',
      'läuft': 'running',
      'Hauptagent': 'Main agent',
      'Hauptagent fokussieren': 'Focus main agent',
      'Fokus': 'Focus',
      'Fokus aufheben': 'Unfocus',
      'Alles anzeigen': 'Show all',
      'Weniger anzeigen': 'Show less',
      'Hauptprotokoll alles anzeigen': 'Show the entire main log',
      'Subagentenprotokoll alles anzeigen': 'Show the entire subagent log',
      'Anweisung an den Agenten': 'Instruction for the agent',
      'Anweisung an den Subagenten': 'Instruction for the subagent',
      'Anweisung senden': 'Send instruction',
      'Bitte eine Anweisung eingeben.': 'Please enter an instruction.',
      'Anweisung übermittelt.': 'Instruction delivered.',
      'Anweisung abgelehnt.': 'Instruction rejected.',
      'Anweisung nicht gesendet: ': 'Instruction not sent: ',
      'Fortsetzen': 'Continue',
      'Sendet ‚weiter‘ an die laufende Sitzung': 'Sends “continue” to the running session',
      'Keine Sitzung – Fortsetzen nicht möglich.': 'No session — continuing is not possible.',
      'Ohne Sitzung kann der Lauf nicht fortgesetzt werden.': 'Without a session the run cannot be continued.',
      'Der Lauf wird fortgesetzt.': 'The run is being continued.',
      'Fortsetzen abgelehnt.': 'Continue rejected.',
      'Fortsetzen nicht gesendet: ': 'Continue not sent: ',
      'Stoppen': 'Stop',
      'Lauf gestoppt.': 'Run stopped.',
      'Stoppen fehlgeschlagen: ': 'Stop failed: ',
      'Bei Pi ist das Steuern nicht möglich: Pi läuft im Print-Modus (--no-session) ohne fortsetzbare Session.': 'With Pi, steering is not possible: Pi runs in print mode (--no-session) without a resumable session.',
      'Subagent': 'Subagent',
      'Subagent fokussieren': 'Focus subagent',
      ' Subagenten': ' subagents',
      'Keine laufenden Subagenten.': 'No running subagents.',
      'Zusammenfassung': 'Summary',
      'Rolle/Agent': 'Role/agent',
      'Modell': 'Model',
      'Sitzung': 'Session',
      'Beendete Läufe fortsetzen': 'Resume finished runs',
      'Diese Sitzungen sind beendet. Wähle eine Sitzung, um sie fortzusetzen.': 'These sessions have finished. Choose a session to resume it.',
      'Paket': 'Package',
      'Setzt diese Sitzung fort.': 'Resumes this session.',
      'Sitzung fortgesetzt.': 'Session resumed.',
      'Sitzung nicht fortgesetzt.': 'Session not resumed.',
      'Sitzung nicht fortgesetzt: ': 'Session not resumed: '
    }
  });
}
