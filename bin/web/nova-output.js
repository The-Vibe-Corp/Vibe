/* AP22 — Live-Ausgabe (Meilenstein B): Hauptagent, laufende Subagenten,
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
    var focusedSession = '';
    var cards = {};

    /* ---------- DOM (rein deklarativ, keine Protokoll-innerHTML) ---------- */
    var overview = el('div', {class: 'nv-out-overview', 'data-nv-out-overview': ''});
    var statePill = el('span', {class: 'nv-pill', 'data-nv-run-state': '', 'data-state': 'stopped'}, tr('gestoppt'));
    var agentLabel = el('span', {class: 'nv-out-agent'});
    var countLabel = el('span', {class: 'nv-out-count'});
    overview.append(statePill, agentLabel, countLabel);

    var mainLog = el('pre', {class: 'nv-log nv-out-main', 'data-nv-out-main': '',
      role: 'log', tabindex: '0', 'aria-label': tr('Hauptagent')});

    var subs = el('div', {class: 'nv-out-subs', 'data-nv-out-subs': ''});

    var steerInput = el('input', {type: 'text', 'data-nv-steer': '',
      placeholder: tr('Anweisung an den Agenten'),
      'aria-label': tr('Anweisung an den Agenten')});
    var steerButton = el('button', {class: 'nv-btn nv-primary', type: 'button',
      'data-nv-action': 'steer'}, tr('Anweisung senden'));
    var continueButton = el('button', {class: 'nv-btn', type: 'button',
      'data-nv-action': 'continue'}, tr('Fortsetzen'));
    var stopButton = el('button', {class: 'nv-btn nv-danger', type: 'button',
      'data-nv-action': 'stop'}, tr('Stoppen'));
    var piNote = el('p', {class: 'nv-muted nv-out-pi-note'},
      tr('Bei Pi ist das Steuern nicht möglich: Pi läuft im Print-Modus (--no-session) ohne fortsetzbare Session.'));
    piNote.hidden = true;

    var controls = el('div', {class: 'nv-out-controls'},
      el('div', {class: 'nv-out-steer'}, steerInput, steerButton),
      el('div', {class: 'nv-out-actions'}, continueButton, stopButton),
      piNote);
    stopButton.hidden = true;
    steerInput.hidden = true;
    steerButton.hidden = true;

    panelRoot.replaceChildren(el('div', {class: 'nv-out'},
      overview, mainLog, subs, controls));

    /* ---------- Fokus: genau eine Karte trägt das Merkmal ---------- */
    function applyFocus() {
      Object.keys(cards).forEach(function (id) {
        var card = cards[id];
        var on = id === focusedSession;
        card.node.classList.toggle('nv-out-focused', on);
        card.node.setAttribute('data-focus', on ? 'true' : 'false');
        card.focusButton.setAttribute('aria-expanded', on ? 'true' : 'false');
        setTx(card.focusButton, tr(on ? 'Fokus aufheben' : 'Fokus'));
      });
    }
    function toggleFocus(id) {
      focusedSession = focusedSession === id ? '' : id;
      applyFocus();
    }
    NV_OUTPUT.keyHandler = function (event) {
      if (event.key === 'Escape' && focusedSession) {
        event.preventDefault();
        focusedSession = '';
        applyFocus();
      }
    };
    document.addEventListener('keydown', NV_OUTPUT.keyHandler);

    /* ---------- Protokollzeilen als Text ---------- */
    function feedMain(text) {
      if (!text) return;
      mainText = (mainText + text).slice(-120000);
      mainLog.replaceChildren(nvRenderLog(mainText));
      mainLog.scrollTop = mainLog.scrollHeight;
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
    function syncControls() {
      var canSteer = running && !isPi;
      steerInput.hidden = !canSteer;
      steerButton.hidden = !canSteer;
      stopButton.hidden = !running;
      piNote.hidden = !isPi;
    }

    function pollState() {
      api('/api/run-state?name=' + encodeURIComponent(name)).then(function (data) {
        if (!alive()) return;
        running = !!(data && data.running);
        statePill.setAttribute('data-state', running ? 'running' : 'stopped');
        setTx(statePill, tr(running ? 'läuft' : 'gestoppt'));
        syncControls();
      }).catch(function () { /* Laufzustand bleibt beim letzten Stand */ });
    }

    function setCardText(card, text) {
      card.text = String(text || '').slice(-120000);
      card.log.replaceChildren(nvRenderLog(card.text));
      card.log.scrollTop = card.log.scrollHeight;
    }

    function makeCard(entry) {
      var session = String(entry.session || '');
      var log = el('pre', {class: 'nv-log nv-out-sub-log'});
      var status = el('span', {class: 'nv-pill'});
      var focusButton = el('button', {class: 'nv-btn nv-ghost', type: 'button',
        'aria-label': tr('Subagent fokussieren'), 'aria-expanded': 'false'}, tr('Fokus'));
      var node = el('article', {class: 'nv-card nv-out-sub', 'data-nv-out-sub': session},
        el('div', {class: 'nv-out-sub-head'},
          el('b', {}, String(entry.agent || tr('Subagent'))),
          status, focusButton),
        log);
      var card = {node: node, log: log, status: status, focusButton: focusButton,
        text: '', loading: false};
      cards[session] = card;
      focusButton.addEventListener('click', function () { toggleFocus(session); });
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
        countLabel.textContent = String(subsRunning.length) + String(tr(' Subagenten'));
        agentLabel.textContent = data && data.agent
          ? String(tr('Hauptagent')) + ': ' + String(data.agent) : '';
        if (!subsRunning.length) countLabel.textContent = String(tr('Keine laufenden Subagenten.'));

        var wanted = {};
        subsRunning.forEach(function (entry) { wanted[String(entry.session)] = entry; });
        Object.keys(cards).forEach(function (id) {
          if (wanted[id]) return;
          cards[id].node.remove();
          delete cards[id];
          if (focusedSession === id) focusedSession = '';
        });
        subsRunning.forEach(function (entry) {
          var session = String(entry.session);
          var card = cards[session] || makeCard(entry);
          if (!card.text && entry.output) setCardText(card, entry.output);
          setTx(card.status, tr(entry.status === 'running' ? 'läuft' : 'gestoppt'));
          if (card.node.parentNode !== subs) subs.append(card.node);
        });
        subs.hidden = subsRunning.length === 0;
        applyFocus();
        subsRunning.forEach(loadCardOutput);
      }).catch(function () { /* Liste bleibt beim letzten Stand */ });
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
    streamMain();
    pollState();
    pollAgents();
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
      if (!panel || panel.querySelector('[data-nv-out-overview]')) return;
      NV.output.render((context && context.name) || '', panel, token);
    });
  };
})();
