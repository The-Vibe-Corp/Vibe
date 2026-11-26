/* F34 WP5 — Projektdetail (Überblick, Arbeit, Beschreibung, Einstellungen).
 *
 * Held, Tabs, Überblick (Autonom-Karte, Kacheln, Zustand, Sitzungen), Arbeit
 * (Aktionsleiste, NV.search/Chips, Priorisierung mit Live-Vorschau,
 * integrierte Ticketliste samt Kontext-Panel), Beschreibung mit
 * Schrittübersicht und die neu geordneten Projekteinstellungen. Alle Daten
 * kommen aus den bestehenden /api-Endpunkten; die Ansicht verändert kein
 * Backend-Verhalten. Jede asynchrone Fortsetzung prüft NV.stale(token), bevor
 * sie DOM ersetzt (Render-Rennschutz wie AP21). Die Ausgabe delegiert an
 * NV.output.render().
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

function nvpText(node) {
  return node ? String(node.textContent || '') : '';
}

/* ---------- F34: gemeinsame Bausteine der Projektansicht ---------- */

/* Freundliche relative Zeit für Sitzungszeilen. */
function nvpRelativeTime(value) {
  var stamp = Number(value);
  if (!isFinite(stamp) || stamp <= 0) return tr('unbekannt');
  var seconds = Math.max(0, Math.floor(Date.now() / 1000 - stamp));
  if (seconds < 60) return tr('gerade eben');
  if (seconds < 3600) return tr('vor {{n}} Min.', {n: Math.floor(seconds / 60)});
  if (seconds < 86400) return tr('vor {{n}} Std.', {n: Math.floor(seconds / 3600)});
  return tr('vor {{n}} Tagen', {n: Math.floor(seconds / 86400)});
}

function nvpShortId(value, max) {
  var text = String(value || '');
  var limit = max || 10;
  return text.length > limit ? text.slice(0, limit - 1) + '…' : text;
}

function nvpIsDone(row) {
  var state = String(row && row.state || '');
  return state === 'erledigt' || state === 'done';
}

/* GH-56: Die API liefert den Anzeigezustand (deutsch). Das Board arbeitet mit
   dem Rohzustand aus dem Ticketspeicher; die Zuordnung bleibt hier eindeutig. */
function nvpRawState(row) {
  var state = String(row && row.state || '');
  var map = {
    'Draft': 'draft', 'offen': 'open', 'In Progress': 'in-progress',
    'BLOCKIERT': 'blocked', 'WARTET AUF MERGE': 'waiting-merge',
    'erledigt': 'done', 'draft': 'draft', 'open': 'open',
    'in-progress': 'in-progress', 'blocked': 'blocked',
    'waiting-merge': 'waiting-merge', 'done': 'done'
  };
  return map[state] || '';
}

/* Board-Spalte eines Rohzustands; done hat keine Board-Spalte und lebt im
   Erledigt-Raster unterhalb des Boards (GH-82). */
function nvpColOfState(state) {
  if (state === 'draft') return 'draft';
  if (state === 'in-progress') return 'running';
  if (state === 'done') return 'done';
  return 'ready';
}

/* Priorisierte Reihenfolge: konfiguriert, dann Standard, dann Rest. Jede
   Kennung erscheint genau einmal; erledigte Einträge bleiben im DOM (für den
   Erledigt-Filter) und werden nur standardmäßig ausgeblendet. */
function nvpOrderedItems(view, items) {
  var priority = (view && view.priority) || {};
  var rows = (items || []).filter(function (row) {
    return !!String(row && row.id || '');
  });
  var byId = {};
  var seen = {};
  rows.forEach(function (row) {
    var id = String(row && row.id || '');
    if (seen[id]) return;
    seen[id] = true;
    byId[id] = row;
  });
  var result = [];
  function add(entry) {
    var id = typeof entry === 'string' ? entry : String(entry && entry.id || '');
    if (byId[id] && result.indexOf(byId[id]) < 0) result.push(byId[id]);
  }
  (priority.order || []).forEach(add);
  (priority.standard || []).forEach(add);
  rows.forEach(add);
  return result;
}

/* Paket-ID → Sitzungs-ID für den Resume-Knopf der Karten. GH-99 nutzt die
   dauerhaft am Paket gespeicherte Zuordnung (``packages``), wenn die API sie
   liefert; die flache ``sessions``-Liste bleibt als Rückfall erhalten. */
function nvpSessionMap(view) {
  var payload = (view && view.sessions) || {};
  var map = {};
  function add(entry, packageId) {
    var row = typeof entry === 'string' ? {session: entry} : entry;
    var id = String(packageId != null ? packageId : row && row.package_id || '');
    var session = String(row && (row.session || row.id || row.name) || '');
    if (id && session && !map[id]) map[id] = session;
  }
  (payload.packages || []).forEach(function (pkg) {
    var packageId = String(pkg && pkg.id || '');
    (pkg && pkg.sessions || []).forEach(function (row) { add(row, packageId); });
  });
  var rows = payload.sessions || payload.entries || [];
  rows.forEach(function (row) { add(row); });
  return map;
}

/* Jeder Zustand erhält ein nicht interaktives Badge; der Wechsel läuft über
   die separaten Schaltflächen, DnD oder die Auswahl im Detail. */
function nvpStateBadge(row) {
  var raw = nvpRawState(row);
  var tone = raw === 'blocked' || raw === 'waiting-merge' ? ' nv-warn'
    : raw === 'in-progress' ? ' nv-ok' : ' nv-muted';
  return el('span', {class: 'nv-pill nv-state' + tone,
    'data-nv-state-badge': ''}, nvpStateLabel(raw));
}

function nvpRowKind(row) {
  if (!row) return 'package';
  if (row.__feedback) return nvpFeedbackKind(row);
  return 'package';
}

function nvpKindBadge(kind) {
  var label = kind === 'bug' ? tr('Bug')
    : kind === 'feedback' ? tr('Feedback') : tr('Paket');
  return el('span', {class: 'nv-kind-badge', 'data-nv-kind': kind}, label);
}

/* Linke Farbkante: gleiche Bedienung, unterschiedliche Farbe je Typ. */
function nvpKindColor(kind) {
  if (kind === 'bug') return 'var(--nv-error-text, #b3261e)';
  if (kind === 'feedback') return 'var(--nv-warn-text, #8a5a00)';
  return 'var(--nv-primary, #2b6cb0)';
}

/* ---------- Help: Zustand/Formatierung ---------- */

function nvpStateLabel(state) {
  var raw = nvpRawState({state: state});
  if (raw === 'draft') return tr('Entwurf');
  if (raw === 'open') return tr('Bereit');
  if (raw === 'in-progress') return tr('In Progress');
  if (raw === 'blocked') return tr('Blockiert');
  if (raw === 'waiting-merge') return tr('Bereit zum Merge');
  if (raw === 'done') return tr('Erledigt');
  return '';
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

/* Nächster freier Kennungsvorschlag: höchste vorhandene Nummer + 1. */
function nvpSuggestId(rows, prefix) {
  var highest = 0;
  (rows || []).forEach(function (row) {
    var match = String(row && row.id || '').match(
      new RegExp('^' + prefix + '(\\d+)$', 'i'));
    if (match) highest = Math.max(highest, parseInt(match[1], 10) || 0);
  });
  return prefix + (highest + 1);
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

/* ---------- Arbeit: Board, Liste, Kontext-Panel, Editor ---------- */

/* Eine Karte für Board und mobile Liste. Titel zuerst, Status-Badge nur bei
   Bedarf, danach die Aktionen. Die Karte trägt den Rohzustand als
   data-nv-state, damit Filter und Spaltenzuordnung eindeutig sind. */
function nvpTicketCard(name, token, row, rank, sessions, rows) {
  var id = String(row.id || '');
  var kind = nvpRowKind(row);
  var raw = nvpRawState(row);
  var title = String(row.title || id);
  var description = String(row.description || '');
  var session = String((sessions || {})[id] || '');
  var card = el('article', {
    class: 'nv-card nv-ticket',
    'data-nv-kind': kind,
    'data-nv-state': raw,
    'data-nv-ticket': id,
    'data-nv-search-text': (id + ' ' + title + ' ' + description).toLowerCase(),
    title: title,
    style: 'border-left: 4px solid ' + nvpKindColor(kind) + '; cursor: pointer;'
  });
  if (row.__feedback) card.setAttribute('data-nv-feedback-item', id);
  if (session) card.setAttribute('data-nv-session', session);

  var actions = el('div', {class: 'nv-row nv-ticket-actions'});
  actions.addEventListener('click', function (event) { event.stopPropagation(); });
  actions.append(el('button', {class: 'nv-btn nv-secondary nv-compact',
    type: 'button', 'data-nv-action': 'ticket-details', on: {click: function () {
      nvpOpenTicketDetail(name, token, row, kind);
    }}}, tr('Details')));

  if (raw === 'in-progress' || raw === 'blocked' || raw === 'waiting-merge') {
    actions.append(el('button', {class: 'nv-btn nv-ghost nv-compact',
      type: 'button', 'data-nv-action': 'ticket-resume',
      title: session ? tr('Sitzung fortsetzen') : tr('Keine Sitzung zum Fortsetzen'),
      on: {click: function () { nvpResumeTicket(name, token, session); }}},
    tr('Fortsetzen')));
  }
  if (raw === 'draft') {
    actions.append(el('button', {class: 'nv-btn nv-ghost nv-compact',
      type: 'button', 'data-nv-action': 'ticket-ready',
      title: tr('Gibt das Ticket für die Umsetzung frei'),
      on: {click: function () { nvpMoveTicketState(name, token, card, 'open'); }}},
    tr('Freigeben')));
  }
  if (raw === 'open') {
    actions.append(el('button', {class: 'nv-btn nv-ghost nv-compact',
      type: 'button', 'data-nv-action': 'ticket-draft',
      title: tr('Zieht das Ticket zurück in die Planung'),
      on: {click: function () { nvpMoveTicketState(name, token, card, 'draft'); }}},
    tr('Zurück in Planung')));
  }
  /* Tastaturalternative zur vertikalen DnD-Reihenfolge. */
  actions.append(el('button', {class: 'nv-btn nv-ghost nv-compact',
    type: 'button', 'data-nv-action': 'priority-up', 'aria-label': tr('Nach oben'),
    on: {click: function () { nvpReorderCard(name, token, card, -1); }}}, '↑'));
  actions.append(el('button', {class: 'nv-btn nv-ghost nv-compact',
    type: 'button', 'data-nv-action': 'priority-down', 'aria-label': tr('Nach unten'),
    on: {click: function () { nvpReorderCard(name, token, card, 1); }}}, '↓'));
  if (raw === 'done') {
    actions.append(el('button', {class: 'nv-btn nv-ghost nv-compact',
      type: 'button', 'data-nv-action': 'ticket-copy', on: {click: function () {
        nvpOpenTicketForm(name, token, {
          mode: kind === 'bug' ? 'bug'
            : kind === 'feedback' ? 'feedback' : 'package',
          title: title, description: description, rows: rows
        });
      }}}, tr('Kopieren')));
  }

  card.append(
    el('div', {class: 'nv-ticket-head'},
      nvpKindBadge(kind),
      el('span', {class: 'nv-ticket-id'}, id),
      rank ? el('span', {'data-nv-prio-badge': ''}, 'P' + String(rank)) : null,
      nvpStateBadge(row)),
    el('div', {class: 'nv-ticket-title'}, title),
    actions);
  card.addEventListener('click', function () {
    nvpOpenTicketDetail(name, token, row, kind);
  });
  return card;
}

/* Board mit drei Spalten (Entwurf, Bereit, In Umsetzung). Karten liegen genau
   einmal im DOM; die Spaltenzuordnung kommt aus dem Rohzustand. Erledigte
   Tickets liefert der Aufrufer nicht mehr an das Board (GH-82). */
function nvpWorkBoard(name, token, items, ranks, sessions) {
  var columns = [
    ['draft', tr('Entwurf')],
    ['ready', tr('Bereit zur Implementierung')],
    ['running', tr('In Umsetzung')]
  ];
  var board = el('div', {class: 'nv-work-board', 'data-nv-board': ''});
  var boxes = {};
  columns.forEach(function (def) {
    var cards = el('div', {'data-nv-col-cards': ''});
    var count = el('span', {class: 'nv-pill', 'data-nv-col-count': ''}, '0');
    var empty = el('div', {class: 'nv-empty', 'data-nv-col-empty': ''},
      tr('Keine Tickets in dieser Spalte'));
    board.append(el('article', {class: 'nv-board-col', 'data-nv-col': def[0]},
      el('div', {'data-nv-col-head': ''},
        el('h3', {class: 'nv-col-title'}, def[1]), count),
      cards, empty));
    boxes[def[0]] = cards;
  });
  items.forEach(function (row) {
    var card = nvpTicketCard(name, token, row, ranks[String(row.id || '')],
      sessions, items);
    card.setAttribute('draggable', 'true');
    boxes[nvpColOfState(nvpRawState(row))].append(card);
  });
  nvpWireBoardDnD(board, name, token);
  nvpRefreshColumns(board);
  return board;
}

/* Mobile Liste mit denselben Karten; Touch-Ziele kommen aus dem CSS. */
function nvpWorkList(name, token, items, ranks, sessions) {
  var list = el('div', {class: 'nv-work-list', 'data-nv-work-list': ''});
  items.forEach(function (row) {
    list.append(nvpTicketCard(name, token, row,
      ranks[String(row.id || '')], sessions, items));
  });
  if (!items.length) {
    list.append(el('p', {class: 'nv-muted'}, tr('Keine Einträge')));
  }
  return list;
}

/* GH-82: Erledigte Tickets stehen in einem eigenen responsiven Raster
   unterhalb des Boards bzw. der mobilen Liste. Die Karten bleiben dieselben
   data-*-Hooks, sind aber nicht ziehbar. */
function nvpWorkDoneGrid(name, token, items, ranks, sessions, rows) {
  var cards = el('div', {class: 'nv-work-done-cards',
    'data-nv-work-done-cards': ''});
  items.forEach(function (row) {
    cards.append(nvpTicketCard(name, token, row,
      ranks[String(row.id || '')], sessions, rows));
  });
  return el('section', {class: 'nv-work-done', 'data-nv-work-done-grid': ''},
    el('h3', {class: 'nv-done-title'}, tr('Abgeschlossen')), cards);
}

function nvpIsDoneRow(row) {
  return nvpRawState(row) === 'done';
}

/* Arbeitsfläche: Priorisierung zuerst, darunter Board (Desktop) oder Liste
   (Mobile) und danach das Raster der erledigten Tickets. Es wird genau eine
   der beiden Varianten gebaut, damit kein verborgenes Board im DOM
   zurückbleibt. */
function nvpWorkView(name, token, view, items) {
  var priorityView = (view && view.priority) || {};
  var ranks = nvpRankMap(priorityView.order || []);
  var sessions = nvpSessionMap(view);
  var ordered = nvpOrderedItems(view, items);
  var doneItems = ordered.filter(nvpIsDoneRow);
  var openItems = ordered.filter(function (row) {
    return !nvpIsDoneRow(row);
  });
  var desktop = !!(window.matchMedia
    && window.matchMedia('(min-width: 769px)').matches);
  var surface = desktop
    ? nvpWorkBoard(name, token, openItems, ranks, sessions)
    : nvpWorkList(name, token, openItems, ranks, sessions);
  var children = [];
  /* GH-67: Die Priorisierungsleiste ist eine mobile Ansicht; auf Desktop
     belegt sie weder Platz noch DOM-Fläche. */
  if (!desktop) {
    children.push(nvpPriorityStrip(name, token, view, items, surface));
  }
  children.push(surface);
  children.push(nvpWorkDoneGrid(name, token, doneItems, ranks, sessions,
    ordered));
  return el('div', {class: 'nv-work-view', 'data-nv-work-view': ''}, children);
}

function nvpCardChildren(box) {
  return Array.prototype.slice.call(box.children).filter(function (node) {
    return node.nodeType === 1 && node.hasAttribute('data-nv-ticket');
  });
}

/* Sichtbare Spaltenzähler und Leerhinweise nach jeder DOM-Änderung angleichen. */
function nvpRefreshColumns(root) {
  if (!root || !root.querySelectorAll) return;
  Array.prototype.slice.call(root.querySelectorAll('article[data-nv-col]'))
    .forEach(function (column) {
      var box = column.querySelector('[data-nv-col-cards]');
      if (!box) return;
      var visible = nvpCardChildren(box).filter(function (card) {
        return !card.hasAttribute('hidden');
      });
      var count = column.querySelector('[data-nv-col-count]');
      if (count) setTx(count, String(visible.length));
      var empty = column.querySelector('[data-nv-col-empty]');
      if (empty) {
        if (visible.length) empty.setAttribute('hidden', '');
        else empty.removeAttribute('hidden');
      }
    });
}

/* Projektreihenfolge = DOM-Reihenfolge der Karten (Board spaltenweise, Liste
   von oben nach unten). Speicherung über die bestehende Priorisierungs-API. */
function nvpContentOrder(root) {
  var ids = [];
  if (!root || !root.querySelectorAll) return ids;
  root.querySelectorAll('article[data-nv-ticket]').forEach(function (card) {
    var id = card.getAttribute('data-nv-ticket');
    if (id && ids.indexOf(id) < 0) ids.push(id);
  });
  return ids;
}

function nvpPersistOrder(name, token, root, rollback) {
  var order = nvpContentOrder(root);
  api('/api/priority', {name: name, action: 'set', order: order.join(' ')})
    .then(function (result) {
      if (NV.stale(token)) return;
      if (result && result.ok === false) {
        if (rollback) rollback();
        toast(bt(result.message) || tr('Speichern fehlgeschlagen'));
      } else {
        toast(tr('Reihenfolge gespeichert'));
      }
    }).catch(function (error) {
      if (NV.stale(token)) return;
      if (rollback) rollback();
      toast(tr('Speichern fehlgeschlagen: ')
        + String(error && error.message || error));
    });
}

function nvpRestoreCard(card, origin) {
  if (origin && origin.next && origin.next.parentNode === origin.parent) {
    origin.parent.insertBefore(card, origin.next);
  } else if (origin && origin.parent) {
    origin.parent.appendChild(card);
  }
}

/* Vertikale Tastatur-/Knopf-Reihenfolge; optimistisch mit Rollback. */
function nvpReorderCard(name, token, card, delta) {
  var box = card.parentNode;
  var siblings = nvpCardChildren(box);
  var index = siblings.indexOf(card);
  var target = index + delta;
  if (index < 0 || target < 0 || target >= siblings.length) return;
  var root = card.closest('[data-nv-board], [data-nv-work-list]') || box;
  var origin = {parent: box, next: card.nextSibling};
  var anchor = siblings[target];
  if (delta < 0) box.insertBefore(card, anchor);
  else box.insertBefore(card, anchor.nextSibling);
  nvpRefreshColumns(root);
  nvpPersistOrder(name, token, root, function () {
    nvpRestoreCard(card, origin);
    nvpRefreshColumns(root);
  });
}

function nvpFindCard(id) {
  var cards = document.querySelectorAll('article[data-nv-ticket]');
  for (var index = 0; index < cards.length; index += 1) {
    if (cards[index].getAttribute('data-nv-ticket') === String(id)) {
      return cards[index];
    }
  }
  return null;
}

function nvpStateToggle(name, token, card, state, label, hint) {
  return el('button', {class: 'nv-btn nv-ghost nv-compact', type: 'button',
    'data-nv-action': state === 'draft' ? 'ticket-draft' : 'ticket-ready',
    title: hint,
    on: {click: function () { nvpMoveTicketState(name, token, card, state); }}},
  label);
}

/* Kartenaktionen nach einem Statuswechsel lokal angleichen. */
function nvpSyncCardActions(name, token, card, state) {
  var actions = card.querySelector('.nv-ticket-actions');
  if (!actions) return;
  actions.querySelectorAll(
    '[data-nv-action="ticket-ready"], [data-nv-action="ticket-draft"]')
    .forEach(function (button) { button.remove(); });
  var toggle = state === 'draft'
    ? nvpStateToggle(name, token, card, 'open', tr('Freigeben'),
      tr('Gibt das Ticket für die Umsetzung frei'))
    : state === 'open'
      ? nvpStateToggle(name, token, card, 'draft', tr('Zurück in Planung'),
        tr('Zieht das Ticket zurück in die Planung'))
      : null;
  if (!toggle) return;
  var anchor = actions.querySelector('[data-nv-action="priority-up"]');
  if (anchor) actions.insertBefore(toggle, anchor);
  else actions.append(toggle);
}

/* Teilaktualisierung nach einem Statuswechsel: Zustand, Badge, Aktionen,
   Spalte und Filter werden nachgezogen; erledigte Karten wandern in das
   Erledigt-Raster. */
function nvpSyncCardState(name, token, card, state) {
  var surface = card.closest('[data-nv-board], [data-nv-work-list]');
  var board = card.closest('[data-nv-board]');
  var view = card.closest('[data-nv-work-view]');
  var doneGrid = view
    ? view.querySelector('[data-nv-work-done-cards]') : null;
  card.setAttribute('data-nv-state', state);
  if (state === 'done' && doneGrid) {
    card.removeAttribute('draggable');
    if (card.parentNode !== doneGrid) doneGrid.appendChild(card);
  } else if (board) {
    var box = board.querySelector(
      'article[data-nv-col="' + nvpColOfState(state) + '"] [data-nv-col-cards]');
    if (box && card.parentNode !== box) box.appendChild(card);
  }
  var badge = card.querySelector('[data-nv-state-badge]');
  var next = nvpStateBadge({state: state});
  if (badge && badge.parentNode) badge.parentNode.replaceChild(next, badge);
  nvpSyncCardActions(name, token, card, state);
  if (board) nvpRefreshColumns(board);
  if (surface && typeof surface.__nvApplyFilters === 'function') {
    surface.__nvApplyFilters();
  }
}

/* Zustandswechsel über die Tastatur-Alternativen. */
function nvpMoveTicketState(name, token, card, state) {
  var board = card.closest('[data-nv-board]');
  var origin = {parent: card.parentNode, next: card.nextSibling};
  if (board) {
    var column = board.querySelector(
      'article[data-nv-col="' + nvpColOfState(state) + '"] [data-nv-col-cards]');
    if (column) column.appendChild(card);
    card.setAttribute('data-nv-state', state);
    nvpRefreshColumns(board);
  }
  api('/api/ticket', {name: name, action: 'state', id:
    card.getAttribute('data-nv-ticket'), state: state}).then(function (result) {
    if (NV.stale(token)) return;
    if (!result || result.ok === false) {
      if (board) {
        nvpRestoreCard(card, origin);
        nvpRefreshColumns(board);
      }
      toast(bt(result && result.message) || tr('Statuswechsel fehlgeschlagen'));
      return;
    }
    nvpSyncCardState(name, token, card, state);
  }).catch(function (error) {
    if (NV.stale(token)) return;
    if (board) {
      nvpRestoreCard(card, origin);
      nvpRefreshColumns(board);
    }
    toast(tr('Statuswechsel fehlgeschlagen: ')
      + String(error && error.message || error));
  });
}

/* Board-only Drag & Drop mit Geist, Einfügemarke, Hervorhebung und Rollback. */
function nvpWireBoardDnD(board, name, token) {
  var drag = null;

  function clearDrag() {
    if (!drag) return;
    if (drag.ghost) drag.ghost.remove();
    if (drag.marker) drag.marker.remove();
    if (drag.column) drag.column.classList.remove('nv-drop-target');
    if (drag.card) drag.card.classList.remove('nv-dragging');
    drag = null;
  }

  function dropIndex(box, clientY) {
    var cards = nvpCardChildren(box);
    for (var index = 0; index < cards.length; index += 1) {
      var box2 = cards[index].getBoundingClientRect();
      if (Number(clientY) < box2.top + box2.height / 2) return index;
    }
    return cards.length;
  }

  function insertCard(box, card, index) {
    var cards = nvpCardChildren(box).filter(function (node) {
      return node !== card;
    });
    if (index >= cards.length) box.appendChild(card);
    else box.insertBefore(card, cards[index]);
  }

  board.addEventListener('dragstart', function (event) {
    var card = event.target.closest
      && event.target.closest('article[data-nv-ticket]');
    if (!card || !board.contains(card)) return;
    clearDrag();
    var column = card.closest('article[data-nv-col]');
    var rect = card.getBoundingClientRect();
    /* Der Geist ist ein eigener div-Knoten: ein Klon der Karte würde als
       zweites article[data-nv-ticket] die Karten-Lokatoren verfälschen. */
    var ghost = el('div', {'data-nv-board-ghost': '', 'aria-hidden': 'true',
      class: 'nv-drag-ghost'},
    String(card.querySelector('.nv-ticket-title')
      ? card.querySelector('.nv-ticket-title').textContent : ''));
    ghost.style.cssText = 'position:fixed;z-index:9999;pointer-events:none;'
      + 'opacity:.92;width:' + rect.width + 'px;left:' + rect.left + 'px;'
      + 'top:' + rect.top + 'px;background:var(--nv-surface);'
      + 'border:1px solid var(--nv-border);border-radius:var(--nv-radius);'
      + 'padding:var(--nv-space-3);box-shadow:var(--nv-shadow);';
    document.body.append(ghost);
    card.classList.add('nv-dragging');
    drag = {
      card: card, id: card.getAttribute('data-nv-ticket'),
      sourceCol: column ? column.getAttribute('data-nv-col') : '',
      ghost: ghost, marker: null, column: null, dropIndex: 0
    };
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'move';
      try { event.dataTransfer.setData('text/plain', drag.id); } catch (e) { /* noop */ }
      try { event.dataTransfer.setDragImage(ghost, 16, 16); } catch (e) { /* noop */ }
    }
  });

  board.addEventListener('drag', function (event) {
    if (!drag || !drag.ghost) return;
    drag.ghost.style.left = (Number(event.clientX || 0) + 12) + 'px';
    drag.ghost.style.top = (Number(event.clientY || 0) + 12) + 'px';
  });

  board.addEventListener('dragover', function (event) {
    if (!drag) return;
    var column = event.target.closest
      && event.target.closest('article[data-nv-col]');
    if (!column || !board.contains(column)) return;
    var targetCol = column.getAttribute('data-nv-col');
    var allowed = drag.sourceCol === targetCol
      || (drag.sourceCol === 'draft' && targetCol === 'ready')
      || (drag.sourceCol === 'ready' && targetCol === 'draft');
    if (!allowed) {
      if (drag.marker) drag.marker.remove();
      drag.marker = null;
      if (drag.column) drag.column.classList.remove('nv-drop-target');
      drag.column = null;
      return;
    }
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
    if (drag.column && drag.column !== column) {
      drag.column.classList.remove('nv-drop-target');
    }
    drag.column = column;
    column.classList.add('nv-drop-target');
    var box = column.querySelector('[data-nv-col-cards]');
    if (!box) return;
    if (!drag.marker) {
      drag.marker = el('div', {class: 'nv-drop-marker',
        'data-nv-drop-marker': '', 'aria-hidden': 'true'});
    }
    drag.dropIndex = dropIndex(box, event.clientY);
    var cards = nvpCardChildren(box);
    if (drag.dropIndex >= cards.length) box.append(drag.marker);
    else box.insertBefore(drag.marker, cards[drag.dropIndex]);
  });

  board.addEventListener('drop', function (event) {
    if (!drag) return;
    var card = drag.card;
    var sourceCol = drag.sourceCol;
    var column = drag.column;
    var index = drag.dropIndex;
    var targetCol = column ? column.getAttribute('data-nv-col') : '';
    var box = column ? column.querySelector('[data-nv-col-cards]') : null;
    var target = event.target.closest
      && event.target.closest('article[data-nv-col]');
    if (target && target.getAttribute('data-nv-col') === targetCol) {
      index = dropIndex(box, event.clientY);
    }
    clearDrag();
    if (!column || !box || !card) return;
    event.preventDefault();

    if (sourceCol === targetCol) {
      var siblings = nvpCardChildren(box);
      var from = siblings.indexOf(card);
      if (from >= 0 && index > from) index -= 1;
      var origin = {parent: box, next: card.nextSibling};
      insertCard(box, card, index);
      nvpRefreshColumns(board);
      nvpPersistOrder(name, token, board, function () {
        nvpRestoreCard(card, origin);
        nvpRefreshColumns(board);
      });
      return;
    }

    var originCross = {parent: card.parentNode, next: card.nextSibling};
    insertCard(box, card, index);
    var nextState = targetCol === 'draft' ? 'draft' : 'open';
    card.setAttribute('data-nv-state', nextState);
    nvpRefreshColumns(board);
    api('/api/ticket', {name: name, action: 'state',
      id: card.getAttribute('data-nv-ticket'), state: nextState})
      .then(function (result) {
        if (NV.stale(token)) return;
        if (!result || result.ok === false) {
          nvpRestoreCard(card, originCross);
          nvpRefreshColumns(board);
          toast(bt(result && result.message)
            || tr('Statuswechsel fehlgeschlagen'));
          return;
        }
        nvpSyncCardState(name, token, card, nextState);
      }).catch(function (error) {
        if (NV.stale(token)) return;
        nvpRestoreCard(card, originCross);
        nvpRefreshColumns(board);
        toast(tr('Statuswechsel fehlgeschlagen: ')
          + String(error && error.message || error));
      });
  });

  board.addEventListener('dragend', clearDrag);
}

/* Details und Aktionen stehen im zentralen Kontext-Panel. Abgeschlossene
   Einträge behalten ihren Nachweis: kein Löschen, Bearbeiten bleibt gesperrt. */
function nvpOpenTicketDetail(name, token, row, kind) {
  var id = String(row.id || '');
  var title = String(row.title || id);
  var done = nvpIsDone(row);
  var error = nvpErrorBox();
  var body = el('div', {class: 'nv-stack', 'data-nv-ticket-detail': id},
    el('div', {class: 'nv-row'}, nvpKindBadge(kind),
      el('span', {class: 'nv-pill nv-state'}, nvpStateLabel(row.state))),
    el('h3', {}, title),
    el('p', {class: 'nv-muted'}, el('code', {}, id)),
    el('p', {}, String(row.description || tr('Keine Beschreibung vorhanden.'))));
  var actions = el('div', {class: 'nv-row nv-ticket-detail-actions'});
  if (done) {
    actions.append(el('span', {class: 'nv-pill nv-warn', 'data-nv-done-notice': '',
      title: tr('Abgeschlossene Einträge bleiben als Nachweis erhalten')},
    tr('Abgeschlossene Einträge bleiben als Nachweis erhalten')));
  } else {
    var rawState = nvpRawState(row);
    if (rawState === 'in-progress' || rawState === 'blocked'
        || rawState === 'waiting-merge') {
      actions.append(el('span', {class: 'nv-pill nv-warn',
        'data-nv-runner-state-notice': '',
        title: tr('Zustand wird vom Läufer gesetzt')},
      tr('Zustand wird vom Läufer gesetzt')));
    } else {
      var stateSelect = el('select', {'data-nv-ticket-state-select': '',
        'aria-label': tr('Zustand')});
      stateSelect.append(el('option', {value: 'draft'}, tr('Entwurf')));
      stateSelect.append(el('option', {value: 'open'}, tr('Bereit')));
      stateSelect.value = rawState;
      actions.append(stateSelect);
      actions.append(el('button', {class: 'nv-btn nv-primary', type: 'button',
        'data-nv-action': 'ticket-state-save', on: {click: function () {
          var path = kind === 'package' ? '/api/ticket' : '/api/feedback';
          var nextState = String(stateSelect.value || '');
          nvpPost(name, path, {action: 'state', id: id,
            state: nextState}, 'Gespeichert', token)
            .then(function (result) {
              if (NV.stale(token) || !result || result.ok === false) return;
              NV.context.close();
              var card = nvpFindCard(id);
              if (card) nvpSyncCardState(name, token, card, nextState);
            });
        }}}, tr('Zustand setzen')));
    }
    actions.append(el('button', {class: 'nv-btn nv-secondary', type: 'button',
      'data-nv-action': 'ticket-edit', on: {click: function () {
        nvpOpenTicketForm(name, token, {
          mode: kind, id: id, title: title,
          description: String(row.description || ''),
          state: nvpRawState(row)
        });
      }}}, tr('Bearbeiten')));
    actions.append(el('button', {class: 'nv-btn nv-danger', type: 'button',
      'data-nv-action': 'ticket-delete', on: {click: function () {
        if (!window.confirm(String(tr('wirklich löschen?')) + ' ' + id)) return;
        var path = kind === 'package' ? '/api/ticket' : '/api/feedback';
        nvpPost(name, path, {action: 'delete', id: id}, 'Gelöscht', token)
          .then(function (result) {
            if (NV.stale(token) || !result || result.ok === false) return;
            NV.context.close();
            NV.render();
          });
      }}}, tr('Löschen')));
  }
  body.append(actions, error);
  NV.context.open({title: title, content: body});
}

function nvpResumeTicket(name, token, session) {
  if (!session) {
    toast(tr('Keine Sitzung zum Fortsetzen'));
    return;
  }
  api('/api/sessions', {name: name, action: 'continue', session: session})
    .then(function (result) {
      if (NV.stale(token)) return;
      if (result && result.ok === false) {
        toast(bt(result.message));
        return;
      }
      toast(bt(result && result.message) || tr('Sitzung fortgesetzt'));
    }).catch(function (error) {
      if (!NV.stale(token)) {
        toast(tr('Aktion fehlgeschlagen: ')
          + String(error && error.message || error));
      }
    });
}

/* Der Ticket-Editor nutzt die geteilte Bearbeitungsansicht (GH-57), erhält
   aber die breitere Vollhöhen-Variante und den Marker data-nv-ticket-editor. */
function nvpOpenTicketForm(name, token, options) {
  var opts = options || {};
  var mode = opts.mode || 'package';
  var editing = !!opts.id;
  var titleInput = el('input', {'data-nv-field': 'title', type: 'text',
    value: opts.title || '', 'aria-label': tr('Titel')});
  var descInput = el('textarea', {'data-nv-field': 'description', rows: '4',
    'aria-label': tr('Beschreibung')}, opts.description || '');
  var idInput = el('input', {'data-nv-field': 'id', type: 'text',
    value: opts.id || '', placeholder: tr('leer lassen = automatisch vergeben'),
    'aria-label': tr('Kennung')});
  if (editing) idInput.setAttribute('readonly', '');
  var idHint = el('small', {'data-nv-id-hint': '', class: 'nv-muted'},
    tr('Die Kennung wird automatisch vergeben, wenn das Feld leer bleibt — oder selbst benennen.'));
  if (!editing) {
    idInput.value = nvpSuggestId(opts.rows,
      mode === 'bug' ? 'B' : mode === 'feedback' ? 'F' : 'AP');
  }
  /* B1: Genau ein Typfeld (feature/bug/feedback); die frühere Kategorie ist
     entfallen. Der interne Typ task bleibt Speicher-kompatibel, wird aber
     nicht mehr angeboten. */
  var typeSelect = null;
  if (!editing) {
    var defaultType = opts.type
      || (mode === 'bug' ? 'bug' : mode === 'feedback' ? 'feedback' : 'feature');
    typeSelect = el('select', {'data-nv-field': 'ticket-type',
      'aria-label': tr('Ticket Type')});
    typeSelect.append(el('option', {value: 'feature'}, tr('Feature')));
    typeSelect.append(el('option', {value: 'bug'}, tr('Bug')));
    typeSelect.append(el('option', {value: 'feedback'}, tr('Feedback')));
    typeSelect.value = defaultType;
  }
  /* Neue Tickets starten immer als Entwurf; Übergänge laufen über das Board. */
  var stateSelect = null;
  if (!editing) {
    stateSelect = el('select', {'data-nv-field': 'state',
      'aria-label': tr('Zustand')});
    stateSelect.append(el('option', {value: 'draft'}, tr('Entwurf')));
    stateSelect.value = 'draft';
  }
  var error = nvpErrorBox();

  var heading = mode === 'bug' ? tr('Neuer Bug')
    : mode === 'feedback' ? tr('Neues Feedback')
      : editing ? tr('Arbeitspaket bearbeiten') : tr('Neues Arbeitspaket');

  var form = el('form', {class: 'nv-card nv-ticket-form', 'data-nv-ticket-form': ''},
    el('h3', {}, heading),
    nvpLabel(tr('Kennung'), idInput),
    idHint,
    nvpLabel(tr('Titel'), titleInput),
    nvpLabel(tr('Beschreibung'), descInput),
    typeSelect ? nvpLabel(tr('Tickettyp'), typeSelect) : null,
    stateSelect ? nvpLabel(tr('Zustand'), stateSelect) : null,
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
          var selectedType = typeSelect ? String(typeSelect.value || 'feature') : '';
          var path = '/api/ticket';
          if (editing && (mode === 'bug' || mode === 'feedback')) {
            path = '/api/feedback';
          }
          if (editing) {
            body.action = 'update';
            body.id = String(idInput.value || '');
          } else {
            body.action = 'add';
            body.type = selectedType;
            body.id = String(idInput.value || '');
            /* GH-56/B1: Neue Tickets sind immer Entwürfe. */
            body.state = 'draft';
          }
          try {
            var result = await api(path, Object.assign({name: nvpCurrentName()}, body));
            if (NV.stale(token)) return;
            if (result && result.ok === false) {
              nvpShowError(error, bt(result.message));
              return;
            }
            toast(bt(result && result.message) || tr('Gespeichert'));
            NV.editView.close();
            NV.render();
          } catch (e) {
            nvpShowError(error, tr('Speichern fehlgeschlagen: ') + String(e && e.message || e));
          }
        }}}, tr('Speichern')),
      el('button', {class: 'nv-btn nv-ghost', type: 'button',
        'data-nv-action': 'ticket-cancel', on: {click: function () {
          NV.editView.close();
        }}}, tr('Abbrechen'))),
    error);
  /* GH-56: Der Editor öffnet sich über dem Detail-Panel. Dessen Scrim läge
     sonst über dem Formular und würde „Speichern" blockieren. */
  NV.context.close();
  NV.editView.open({
    title: heading,
    marker: 'data-nv-ticket-editor',
    content: el('div', {'data-nv-ticket-form-wrap': ''}, form)
  });
  titleInput.focus();
}

/* Der Projektname steht im Hash; Formulare holen ihn bei Bedarf dort, damit
   sie auch nach einem Panel-Neuaufbau ohne übergebenen Kontext auskommen. */
function nvpCurrentName() {
  var match = (location.hash || '').match(/#\/?project\/([^/]+)/);
  if (!match) return '';
  try { return decodeURIComponent(match[1]); } catch (e) { return match[1]; }
}

/* Rangkarte aus einer Priorisierungsreihenfolge (Objekte mit id oder reine
   ID-Strings): einzige Quelle für Strip, Speichern und Karten-Badges. */
function nvpRankMap(order) {
  var ranks = {};
  (order || []).forEach(function (entry, index) {
    var id = typeof entry === 'string' ? entry : String(entry && entry.id || '');
    if (id) ranks[id] = index + 1;
  });
  return ranks;
}

/* Badges der Karten lokal nachziehen (ohne NV.render): vorhandenen Text
   aktualisieren, fehlende Badges ergänzen, nicht mehr priorisierte entfernen. */
function nvpUpdateCardBadges(list, ranks) {
  if (!list) return;
  Array.prototype.slice.call(list.querySelectorAll('.nv-ticket')).forEach(function (card) {
    var id = card.getAttribute('data-nv-ticket')
      || card.getAttribute('data-nv-feedback-item') || '';
    var rank = ranks[id];
    var badge = card.querySelector('[data-nv-prio-badge]');
    if (rank) {
      if (!badge) {
        badge = el('span', {'data-nv-prio-badge': ''});
        var idNode = card.querySelector('.nv-ticket-id');
        if (idNode && idNode.parentNode) idNode.parentNode.insertBefore(badge, idNode.nextSibling);
        else {
          var head = card.querySelector('.nv-ticket-head');
          if (head) head.append(badge);
        }
      }
      badge.textContent = 'P' + String(rank);
    } else if (badge) {
      badge.remove();
    }
  });
}

function nvpEntryId(entry) {
  return typeof entry === 'string' ? entry : String(entry && entry.id || '');
}

/* Zählt nur konfigurierte Einträge, die zugleich ein echtes Ready-Ticket
   sind; pausierte Einträge (status != offen) zählen nicht mit. */
function nvpPrioritizedCount(configured, open) {
  return (configured || []).reduce(function (n, entry) {
    var id = nvpEntryId(entry);
    if (!open[id]) return n;
    if (entry && entry.status && entry.status !== 'offen') return n;
    return n + 1;
  }, 0);
}

function nvpPriorityCountLabel(n) {
  return n === 1 ? tr('{{n}} priorisiertes Ticket', {n: n})
    : tr('{{n}} priorisierte Tickets', {n: n});
}

/* Die Priorisierungsleiste steht zwischen Filtern und Liste. Manuell
   priorisierte Einträge stehen zuerst, danach die Standardreihenfolge;
   erledigte Einträge erscheinen nie. Drag & Drop zeigt eine Live-Vorschau
   (Zeiger-Geist + Einfügemarke), ↑/↓ bleiben die Tastaturalternative. */
function nvpPriorityStrip(name, token, view, items, cards) {
  var strip = el('div', {class: 'nv-priority-strip', 'data-nv-priority-strip': ''});
  var priority = (view && view.priority) || {};
  var configured = priority.order || [];
  var standard = priority.standard || [];
  var titles = {};
  var open = {};
  /* GH-56: Die Work-Priorisierung zeigt ausschließlich Ready-Tickets
     (Rohzustand ``open``); Draft und Running gehören in ihre Board-Spalten. */
  (items || []).forEach(function (row) {
    var id = String(row && row.id || '');
    if (!id || nvpRawState(row) !== 'open') return;
    open[id] = true;
    titles[id] = String(row && row.title || id);
  });
  var ids = [];
  function add(entry) {
    var id = nvpEntryId(entry);
    if (!id || !open[id] || ids.indexOf(id) >= 0) return;
    ids.push(id);
    if (!titles[id]) titles[id] = String(entry && entry.title || id);
  }
  configured.forEach(add);
  standard.forEach(add);
  (items || []).forEach(add);
  var ranks = nvpRankMap(configured);
  var count = el('div', {class: 'nv-muted', 'data-nv-prio-count': ''},
    nvpPriorityCountLabel(nvpPrioritizedCount(configured, open)));
  var rowsBox = el('div', {class: 'nv-priority-rows'});
  var marker = el('div', {'data-nv-drop-marker': '', 'aria-hidden': 'true',
    style: 'height:3px;border-radius:2px;background:var(--nv-primary, #2b6cb0);margin:2px 0;'});
  var dragId = null;
  var ghost = null;
  var markerIndex = -1;

  async function saveOrder(order) {
    try {
      var result = await api('/api/priority', {
        name: name, action: 'set', order: order.join(' ')
      });
      if (NV.stale(token)) return;
      if (result && result.ok === false) { toast(bt(result.message)); return; }
      toast(tr('Priorisierung gespeichert'));
      /* Nach dem Speichern ist die ganze Liste die konfigurierte Reihenfolge:
         Ränge, Zähler und Karten-Badges lokal nachziehen statt Voll-Neurender. */
      ranks = nvpRankMap(order);
      setTx(count, nvpPriorityCountLabel(nvpPrioritizedCount(order, open)));
      draw();
      nvpUpdateCardBadges(cards, ranks);
    } catch (e) {
      toast(tr('Speichern fehlgeschlagen: ') + String(e && e.message || e));
    }
  }

  var reset = nvpButton(tr('Zurücksetzen'), 'priority-reset', async function () {
    try {
      var result = await api('/api/priority', {name: name, action: 'set', order: ''});
      if (NV.stale(token)) return;
      if (result && result.ok === false) { toast(bt(result.message)); return; }
      toast(tr('Priorisierung zurückgesetzt'));
      if (!NV.stale(token)) NV.render();
    } catch (e) {
      toast(tr('Speichern fehlgeschlagen: ') + String(e && e.message || e));
    }
  });
  reset.setAttribute('data-nv-priority-reset', '');

  function priorityRows() {
    return Array.prototype.slice.call(rowsBox.querySelectorAll('.nv-priority-row'));
  }
  function clearPreview() {
    if (ghost) { ghost.remove(); ghost = null; }
    marker.remove();
    priorityRows().forEach(function (row) {
      row.style.transform = '';
      row.style.opacity = '';
    });
    markerIndex = -1;
  }
  function targetIndex(clientY) {
    var rows = priorityRows();
    var boxTop = rowsBox.getBoundingClientRect().top;
    var y = Number(clientY) - boxTop;
    for (var index = 0; index < rows.length; index += 1) {
      var middle = rows[index].offsetTop - rowsBox.offsetTop
        + rows[index].offsetHeight / 2;
      /* Kleine Toleranz für Subpixel-/Scroll-Drift zwischen Zeilenmitte und
         Drop-Koordinate: ein Treffer knapp unter der Mitte bleibt „davor“. */
      if (y < middle + 4) return index;
    }
    return rows.length;
  }
  function showMarker(index) {
    if (index === markerIndex) return;
    markerIndex = index;
    var rows = priorityRows();
    var shift = ghost ? ghost.offsetHeight : 34;
    rows.forEach(function (row, rowIndex) {
      row.style.transform = rowIndex >= index
        ? 'translateY(' + shift + 'px)' : '';
    });
    if (index >= rows.length) rowsBox.append(marker);
    else rowsBox.insertBefore(marker, rows[index]);
  }

  strip.addEventListener('dragover', function (event) {
    if (!dragId) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
    showMarker(targetIndex(event.clientY));
  });
  strip.addEventListener('drop', function (event) {
    if (!dragId) return;
    event.preventDefault();
    var source = dragId;
    var insertAt = targetIndex(event.clientY);
    clearPreview();
    dragId = null;
    var next = ids.slice();
    var from = next.indexOf(source);
    if (from < 0) return;
    next.splice(from, 1);
    if (insertAt > from) insertAt -= 1;
    next.splice(insertAt, 0, source);
    ids = next;
    draw();
    saveOrder(ids.slice());
  });

  function draw() {
    rowsBox.replaceChildren();
    if (!ids.length) {
      rowsBox.append(el('p', {class: 'nv-muted'}, tr('Keine offenen Einträge')));
      return;
    }
    ids.forEach(function (id, index) {
      var handle = el('button', {class: 'nv-btn nv-priority-drag', type: 'button',
        'data-nv-drag-handle': '', draggable: 'true',
        'aria-label': tr('Priorität ändern')});
      var upAttrs = {class: 'nv-btn nv-ghost nv-compact', type: 'button',
        'data-nv-action': 'priority-up', 'aria-label': tr('Nach oben'),
        on: {click: function () {
          if (index > 0) {
            var tmp = ids[index - 1]; ids[index - 1] = ids[index]; ids[index] = tmp;
            draw();
            saveOrder(ids.slice());
          }
        }}};
      var downAttrs = {class: 'nv-btn nv-ghost nv-compact', type: 'button',
        'data-nv-action': 'priority-down', 'aria-label': tr('Nach unten'),
        on: {click: function () {
          if (index < ids.length - 1) {
            var tmp = ids[index + 1]; ids[index + 1] = ids[index]; ids[index] = tmp;
            draw();
            saveOrder(ids.slice());
          }
        }}};
      if (index === 0) upAttrs.disabled = '';
      if (index === ids.length - 1) downAttrs.disabled = '';
      var row = el('div', {class: 'nv-priority-row', 'data-nv-priority-id': id},
        handle,
        el('span', {class: 'nv-priority-label'},
          (ranks[id] ? 'P' + ranks[id] + ' ' : '') + id + ' ' + (titles[id] || '')),
        el('button', upAttrs, '↑'),
        el('button', downAttrs, '↓'));
      handle.addEventListener('dragstart', function (event) {
        dragId = id;
        if (event.dataTransfer) {
          event.dataTransfer.effectAllowed = 'move';
          try { event.dataTransfer.setData('text/plain', id); } catch (e) { /* noop */ }
          try {
            var image = document.createElement('img');
            image.src = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';
            event.dataTransfer.setDragImage(image, 0, 0);
          } catch (e) { /* noop */ }
        }
        ghost = row.cloneNode(true);
        ghost.setAttribute('data-nv-drag-ghost', '');
        ghost.removeAttribute('data-nv-priority-id');
        ghost.querySelectorAll('[data-nv-drag-handle], [data-nv-action]').forEach(function (node) {
          node.removeAttribute('data-nv-drag-handle');
          node.removeAttribute('data-nv-action');
        });
        ghost.style.cssText = 'position:fixed;z-index:9999;pointer-events:none;'
          + 'opacity:.92;box-shadow:var(--nv-shadow, 0 6px 18px rgba(0,0,0,.2));'
          + 'background:var(--nv-surface, #fff);padding:6px 10px;border-radius:8px;'
          + 'width:' + row.offsetWidth + 'px;';
        document.body.append(ghost);
        row.style.opacity = '0.35';
        markerIndex = -1;
      });
      handle.addEventListener('drag', function (event) {
        if (!ghost) return;
        ghost.style.left = (Number(event.clientX || 0) + 12) + 'px';
        ghost.style.top = (Number(event.clientY || 0) + 12) + 'px';
      });
      handle.addEventListener('dragend', function () {
        clearPreview();
        dragId = null;
      });
      rowsBox.append(row);
    });
  }
  draw();
  strip.append(count, rowsBox, reset);
  return strip;
}

/* Live-Suche, Typ-Chips, Zustands-Chips und „Erledigte anzeigen“ teilen eine
   Sichtbarkeitsfunktion. Zustands-Chips bilden die Board-Spalten ab; der
   Erledigt-Schalter steuert die Sichtbarkeit des Rasters unterhalb. */
function nvpWireWorkFilters(panel, toggle, doneCount, surface) {
  var search = panel.querySelector('input[data-nv-work-search]');
  if (!search) return;
  var hideDone = true;
  var kind = 'all';
  var state = 'all';
  var kindChips = panel.querySelectorAll('button[data-nv-work-kind]');
  var stateChips = panel.querySelectorAll('button[data-nv-work-state]');

  function cardState(card) {
    var raw = String(card.getAttribute('data-nv-state') || '');
    return raw === 'erledigt' ? 'done' : raw;
  }
  function chipOf(raw) {
    if (raw === 'draft') return 'draft';
    if (raw === 'in-progress') return 'running';
    if (raw === 'done') return 'done';
    return 'ready';
  }
  function cardText(card) {
    var indexed = String(card.getAttribute('data-nv-search-text') || '');
    if (indexed) return indexed;
    var id = card.getAttribute('data-nv-ticket')
      || card.getAttribute('data-nv-feedback-item') || '';
    var title = nvpText(card.querySelector('.nv-ticket-title, .nv-feedback-title'));
    var desc = nvpText(card.querySelector('.nv-ticket-desc, .nv-feedback-desc'));
    return (id + ' ' + title + ' ' + desc).toLowerCase();
  }
  function apply() {
    var query = String(search.value || '').trim().toLowerCase();
    panel.querySelectorAll('[data-nv-ticket], [data-nv-feedback-item]').forEach(function (card) {
      var raw = cardState(card);
      var matches = !query || cardText(card).indexOf(query) >= 0;
      var matchesKind = kind === 'all' || card.getAttribute('data-nv-kind') === kind;
      var matchesState = state === 'all' || chipOf(raw) === state;
      var hiddenDone = hideDone && raw === 'done';
      var hide = !matches || !matchesKind || !matchesState || hiddenDone;
      if (hide) card.setAttribute('hidden', '');
      else card.removeAttribute('hidden');
    });
    toggle.setAttribute('aria-pressed', hideDone ? 'true' : 'false');
    setTx(toggle, hideDone
      ? tr('Erledigte anzeigen') + ' (' + String(doneCount) + ')'
      : tr('Erledigte ausblenden'));
    kindChips.forEach(function (chip) {
      chip.setAttribute('aria-pressed',
        chip.getAttribute('data-nv-work-kind') === kind ? 'true' : 'false');
    });
    stateChips.forEach(function (chip) {
      chip.setAttribute('aria-pressed',
        chip.getAttribute('data-nv-work-state') === state ? 'true' : 'false');
    });
    var doneGrid = panel.querySelector('[data-nv-work-done-grid]');
    if (doneGrid) {
      var visibleDone = Array.prototype.slice.call(
        doneGrid.querySelectorAll('[data-nv-ticket]')).filter(function (card) {
          return !card.hasAttribute('hidden');
        }).length;
      if (hideDone || !visibleDone) doneGrid.setAttribute('hidden', '');
      else doneGrid.removeAttribute('hidden');
    }
    if (surface) nvpRefreshColumns(surface);
  }
  if (surface) surface.__nvApplyFilters = apply;
  search.addEventListener('input', apply);
  toggle.addEventListener('click', function () { hideDone = !hideDone; apply(); });
  kindChips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      kind = chip.getAttribute('data-nv-work-kind') || 'all';
      apply();
    });
  });
  stateChips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      var next = chip.getAttribute('data-nv-work-state') || 'all';
      state = state === next ? 'all' : next;
      apply();
    });
  });
  apply();
}

/* ---------- Überblick: autonomer Modus als große Karte ---------- */

function nvpAutonomousCard(name, token, autonomous) {
  var on = !!(autonomous && autonomous.enabled);
  var input = el('input', {type: 'checkbox', 'data-nv-autonomous': '',
    'aria-label': tr('Autonomer Modus')});
  input.checked = on;
  var state = el('span', {class: 'nv-pill ' + (on ? 'nv-ok' : 'nv-warn'),
    'data-nv-autonomous-state': ''}, on ? tr('aktiv') : tr('inaktiv'));
  input.addEventListener('change', function () {
    var next = !!input.checked;
    setTx(state, next ? tr('aktiv') : tr('inaktiv'));
    state.classList.toggle('nv-ok', next);
    state.classList.toggle('nv-warn', !next);
    nvpPost(name, '/api/autonomous', {action: next ? 'on' : 'off'},
      'Autonomer Modus', token);
  });
  return el('section', {class: 'nv-card nv-autonomous-card',
    'data-nv-autonomous-card': '',
    style: 'padding:var(--nv-space-5, 24px);border:2px solid var(--nv-primary, #2b6cb0);'
      + 'display:flex;flex-wrap:wrap;align-items:center;gap:var(--nv-space-4, 16px);'},
    el('div', {style: 'flex:1 1 24rem;min-width:0;'},
      el('h3', {style: 'margin:0 0 8px;font-size:1.35rem;'}, tr('Autonomer Modus')),
      el('p', {class: 'nv-muted', style: 'margin:0;'},
        tr('Im autonomen Modus sind Rückfragen nicht möglich; der Agent entscheidet offene Punkte selbst'))),
    state,
    el('div', {class: 'nv-row nv-autonomous', 'data-nv-autonomous-row': ''},
      el('small', {class: 'nv-muted'},
        tr('Im autonomen Modus sind Rückfragen nicht möglich; der Agent entscheidet offene Punkte selbst')),
      input));
}

/* ---------- Beschreibung: Leitfaden mit Schrittübersicht ---------- */

/* Schrittüberschriften sind übersetzbare Quelltexte. Der Backend-Titel
   „Produktziel“ erscheint im Deutschen als „Projektziel“. */
function nvpGuideTitle(step) {
  var raw = String(step && step.title || '');
  if (raw === 'Produktziel') return tr('Projektziel');
  return raw ? tr(raw) : tr('Schritt');
}

function nvpAssistantPanel(name, token, guide) {
  var steps = (guide && guide.steps) || [];
  var statusById = {};
  steps.forEach(function (step) {
    statusById[String(step.id || '')] = String(step && step.status || '');
  });
  function filledCount() {
    return steps.filter(function (step) {
      return statusById[String(step.id || '')] === 'gefüllt';
    }).length;
  }
  function progressText(count) {
    return String(count) + ' ' + tr('von') + ' ' + String(steps.length)
      + ' ' + tr('ausgefüllt');
  }
  var progress = el('div', {class: 'nv-muted', 'data-nv-guide-progress': ''},
    progressText(filledCount()));
  var holder = el('div', {class: 'nv-card nv-assistant', 'data-nv-assistant': ''},
    el('div', {class: 'nv-row', style: 'justify-content:space-between;flex-wrap:wrap;'},
      el('h3', {}, tr('Projektleitfaden')),
      progress));
  var nav = el('nav', {'data-nv-guide-nav': '', 'aria-label': tr('Schrittübersicht'),
    style: 'display:flex;flex-wrap:wrap;gap:var(--nv-space-2, 8px);'});
  var content = el('div', {class: 'nv-guide-grid'});
  if (!steps.length) {
    content.append(el('p', {class: 'nv-muted'}, tr('Keine Schritte vorhanden')));
  }
  steps.forEach(function (step, index) {
    var id = String(step.id || '');
    var title = nvpGuideTitle(step);
    var stepBox = el('section', {class: 'nv-guide-step',
      'data-nv-guide-step-id': id, id: 'nv-guide-' + id,
      style: 'scroll-margin-top: 96px;'},
      el('h4', {}, String(index + 1) + '. ' + title),
      el('p', {}, String(step.question || '')),
      el('p', {class: 'nv-muted'}, String(step.help || '')),
      el('textarea', {rows: '6', 'data-nv-answer-field': id,
        'aria-label': tr('Antwort')}, String(step.value || '')));
    nav.append(el('button', {class: 'nv-btn nv-ghost nv-compact', type: 'button',
      'data-nv-guide-step': id,
      'aria-label': tr('Zu Schritt {{n}}', {n: index + 1}),
      on: {click: function () {
        stepBox.scrollIntoView({behavior: 'smooth', block: 'start'});
      }}}, title));
    var buttons = [el('button', {class: 'nv-btn nv-secondary nv-compact', type: 'button',
      on: {click: function () {
        nvpGuideAction(name, token, {action: 'agent', step: id});
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
      'data-nv-answer-save': '',
      on: {click: async function () {
        var answers = {};
        answers[id] = String(stepBox.querySelector('[data-nv-answer-field]').value || '');
        try {
          var result = await api('/api/guide', Object.assign(
            {name: name, action: 'save', answers: answers}));
          if (NV.stale(token)) return;
          if (result && result.ok === false) { toast(bt(result.message)); return; }
          toast(tr('Antwort gespeichert'));
          statusById[id] = answers[id].trim() ? 'gefüllt' : 'offen';
          setTx(progress, progressText(filledCount()));
        } catch (e) {
          toast(tr('Speichern fehlgeschlagen: ') + String(e && e.message || e));
        }
      }}}, tr('Antwort speichern')));
    stepBox.append(el('div', {class: 'nv-row nv-guide-actions'}, buttons));
    content.append(stepBox);
  });
  /* Desktop: Schritte links, Übersicht als rechte Spalte. Schmal: die Leiste
     bricht um und liegt als horizontale Leiste über/unter den Schritten. */
  holder.append(el('div', {
    style: 'display:flex;flex-wrap:wrap;gap:var(--nv-space-5, 24px);align-items:flex-start;'
  },
    el('div', {style: 'flex:1 1 32rem;min-width:0;'}, content),
    el('div', {style: 'flex:0 1 16rem;min-width:min(100%, 12rem);position:sticky;top:96px;'},
      el('h4', {}, tr('Schrittübersicht')), nav)));
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
  var body = el('div', {class: 'nv-list nv-team-grid',
    style: 'display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));'
      + 'gap:var(--nv-space-2, 8px);'});
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
    var values = [];
    var seen = {};
    models.forEach(function (m) {
      var value = String(m && (m.id || m) || '');
      if (value && !seen[value]) { seen[value] = true; values.push(value); }
    });
    var current = String(row.override || row.model || '');
    if (current && !seen[current]) values.push(current);
    var combo = NV.modelCombobox(values, current, {
      onchange: function (value) {
        api('/api/project-agents', {name: name, agent: agent, model: value})
          .then(function (result) {
            if (NV.stale(token)) return;
            if (result && result.ok === false) nvpShowError(error, bt(result.message));
            else toast(bt(result && result.message) || tr('Modell gespeichert'));
          })
          .catch(function (e) { nvpShowError(error, String(e && e.message || e)); });
      }
    });
    combo.setAttribute('data-nv-agent-model', '');
    combo.style.width = '100%';
    body.append(el('div', {class: 'nv-row nv-team-row', 'data-nv-team-agent': agent,
      style: 'gap:var(--nv-space-2, 8px);align-items:center;flex-wrap:wrap;'},
      toggle,
      el('span', {class: 'nv-team-name', style: 'flex:0 0 7rem;white-space:nowrap;'}, agent),
      row.opencode ? el('span', {class: 'nv-tag'}, tr('OpenCode')) : null,
      el('div', {style: 'flex:1 1 14rem;min-width:0;'}, combo)));
  });
  return nvpSection('team', tr('Team'), [body, error]);
}

var NVP_TYPE_HELP = {
  generic: 'Allgemeines Projekt ohne besondere Werkzeuge.',
  android: 'Android-Projekt mit Emulator und Gradle-Werkzeugen.',
  swift: 'Swift-Projekt für Apple-Plattformen.',
  python: 'Python-Projekt mit virtueller Umgebung.',
  node: 'Node- und TypeScript-Projekt mit npm-Werkzeugen.',
  rust: 'Rust-Projekt mit Cargo-Werkzeugen.',
  go: 'Go-Projekt mit den Go-Werkzeugen.'
};

function nvpBasicsSection(name, token, data) {
  var type = String(data.type || '');
  var prepared = !!data.init;
  var typeSelect = el('select', {'data-nv-field': 'type', 'aria-label': tr('Typ')});
  ['generic', 'android', 'swift', 'python', 'node', 'rust', 'go'].forEach(function (value) {
    nvpOption(typeSelect, value, value === type);
  });
  if (type && !Array.prototype.some.call(typeSelect.options, function (o) { return o.value === type; })) {
    nvpOption(typeSelect, type, true);
  }
  var typeHelp = el('small', {'data-nv-type-help': '', class: 'nv-muted'},
    tr(NVP_TYPE_HELP[type] || NVP_TYPE_HELP.generic));
  typeSelect.addEventListener('change', function () {
    setTx(typeHelp, tr(NVP_TYPE_HELP[typeSelect.value] || NVP_TYPE_HELP.generic));
    if (typeSelect.value !== type) confirmBox.removeAttribute('hidden');
    else confirmBox.setAttribute('hidden', '');
  });
  var error = nvpErrorBox();
  var confirmText = el('p', {class: 'nv-muted'}, '');
  var confirmBox = el('div', {class: 'nv-confirm', 'data-nv-type-confirm': '', hidden: ''},
    confirmText,
    el('div', {class: 'nv-row'},
      nvpButton(tr('Ja, Typ ändern'), 'type-confirm-yes', async function () {
        try {
          var result = await api('/api/init', {name: name, type: typeSelect.value});
          if (NV.stale(token)) return;
          if (result && result.ok === false) { nvpShowError(error, bt(result.message)); return; }
          toast(bt(result && result.message) || tr('Projekttyp gespeichert'));
          NV.render();
        } catch (e) {
          nvpShowError(error, tr('Speichern fehlgeschlagen: ') + String(e && e.message || e));
        }
      }, 'nv-primary'),
      nvpButton(tr('Abbrechen'), 'type-confirm-no', function () {
        typeSelect.value = type;
        setTx(typeHelp, tr(NVP_TYPE_HELP[type] || NVP_TYPE_HELP.generic));
        confirmBox.setAttribute('hidden', '');
      })));
  typeSelect.addEventListener('change', function () {
    setTx(confirmText, tr('Den Projekttyp wirklich auf {{type}} ändern? '
      + 'Bestehende Einstellungen bleiben erhalten.', {type: typeSelect.value}));
  });
  var init = prepared ? null : nvpButton(tr('Projekt vorbereiten'), 'init', function () {
    nvpPost(name, '/api/init', {type: typeSelect.value}, 'Vorbereitung gestartet', token)
      .then(function () { if (!NV.stale(token)) NV.render(); });
  }, 'nv-primary');
  return nvpSection('basics', tr('Grundlagen'), [
    el('dl', {class: 'nv-kv nv-kv-list'},
      el('div', {class: 'nv-kv-row'}, el('dt', {}, tr('Pfad')),
        el('dd', {}, el('code', {}, String(data.path || '')))),
      el('div', {class: 'nv-kv-row'}, el('dt', {}, tr('Typ')),
        el('dd', {}, String(type || '-'))),
      el('div', {class: 'nv-kv-row'}, el('dt', {}, '.vibe'),
        el('dd', {}, String(prepared ? tr('Vorhanden') : tr('Fehlt'))))),
    nvpLabel(tr('Typ'), typeSelect), typeHelp,
    init ? el('div', {class: 'nv-row'}, init) : null,
    confirmBox, error
  ]);
}

/* Session-Limit ist eine projektspezifische Einstellung und steht nicht mehr
   im Überblick. Der Wert gilt ausschließlich für dieses Projekt. */
function nvpSessionLimitSection(name, token, sessions) {
  var current = sessions && sessions.limit;
  var input = el('input', {type: 'number', min: '1', max: '100',
    'data-nv-session-limit': '',
    value: current == null ? '' : String(current),
    'aria-label': tr('Sitzungslimit für dieses Projekt')});
  var error = nvpErrorBox();
  var save = nvpButton(tr('Speichern'), 'session-limit-save', async function () {
    nvpShowError(error, '');
    var value = parseInt(String(input.value || '').trim(), 10);
    if (!isFinite(value) || value < 1 || value > 100) {
      nvpShowError(error, tr('Bitte ein Limit zwischen 1 und 100 angeben.'));
      return;
    }
    try {
      var result = await api('/api/sessions', {name: name, action: 'limit', limit: value});
      if (NV.stale(token)) return;
      if (result && result.ok === false) { nvpShowError(error, bt(result.message)); return; }
      toast(bt(result && result.message) || tr('Sitzungslimit gespeichert'));
    } catch (e) {
      nvpShowError(error, String(e && e.message || e));
    }
  }, 'nv-primary');
  return nvpSection('session-limit', tr('Sitzungslimit'), [
    el('p', {class: 'nv-muted'}, tr('gilt nur für dieses Projekt')),
    nvpLabel(tr('Sitzungslimit'), input),
    el('div', {class: 'nv-row'}, save), error
  ]);
}

/* Fehlerbehebung ist nur für Android-Projekte relevant. */
function nvpTroubleshootingSection(name, token, data) {
  if (String(data && data.type || '') !== 'android') return null;
  return nvpSection('troubleshooting', tr('Fehlerbehebung'), [
    el('details', {'data-nv-emulator': ''},
      el('summary', {}, tr('Emulator')),
      el('p', {class: 'nv-muted'},
        tr('nur nötig, wenn etwas nicht funktioniert')),
      el('div', {class: 'nv-row'},
        nvpButton(tr('Emulator starten'), 'emulator-start', function () {
          nvpPost(name, '/api/emu', {action: 'start'}, 'Emulator gestartet', token);
        }, 'nv-primary'),
        nvpButton(tr('Emulator stoppen'), 'emulator-stop', function () {
          nvpPost(name, '/api/emu', {action: 'stop'}, 'Emulator gestoppt', token);
        })))
  ]);
}

/* Git & GitHub: vollständige CLI-Parität als bewusste Aktionen. Die Payloads
   entsprechen eins zu eins der klassischen Karte (app.js githubBody); der
   Zugriff ist je Projekt und der Token wird nie in den DOM geschrieben.
   F34: fünf Blöcke Verbindung → Branches → Synchronisieren → Merge-Request
   → Issues. */
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

  var branchNames = [];
  (g.branches || []).forEach(function (branch) {
    var value = String(branch && branch.name || '');
    if (value && branchNames.indexOf(value) < 0) branchNames.push(value);
  });
  var currentBranch = String(g.branch || '');
  if (currentBranch && currentBranch !== '-' && branchNames.indexOf(currentBranch) < 0) {
    branchNames.unshift(currentBranch);
  }
  function branchSelect(hook, field, placeholder, selected) {
    var select = el('select', {['data-nv-' + hook]: '', 'data-nv-field': field,
      'aria-label': placeholder});
    select.append(el('option', {value: ''}, placeholder));
    branchNames.forEach(function (value) {
      select.append(el('option', {value: value}, value));
    });
    if (selected) select.value = selected;
    return select;
  }

  /* --- Block 1: Verbindung --- */
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
  var autoMergeRow = el('label', {class: 'nv-switch-row', 'data-nv-automerge-switch': ''},
    autoMerge,
    el('span', {class: 'nv-switch-text'},
      el('span', {}, tr('Merge-Requests automatisch mergen')),
      el('small', {}, tr('Merge-Requests automatisch mergen, wenn alle Schranken grün sind (sonst PR-only)'))));

  var connectionState = el('span', {class: 'nv-pill',
    'data-nv-github-connection-state': ''},
    g.repo ? tr('Verknüpft') : tr('Nicht verknüpft'));
  var tokenState = el('span', {class: 'nv-pill ' + (g.auth && g.auth.set ? 'nv-ok' : 'nv-warn'),
    'data-nv-github-token-state': ''},
  g.auth && g.auth.set ? tr('Token hinterlegt') : tr('Kein Token'));
  function syncToken(result) {
    var auth = result && (result.auth || (result.github && result.github.auth));
    if (!auth) return;
    var hasToken = !!auth.set;
    setTx(tokenState, hasToken ? tr('Token hinterlegt') : tr('Kein Token'));
    tokenState.classList.toggle('nv-ok', hasToken);
    tokenState.classList.toggle('nv-warn', !hasToken);
  }
  var authLine = el('div', {class: 'nv-muted', 'data-nv-github-auth': ''},
    g.auth && g.auth.set
      ? tr('GitHub-Zugang eingerichtet.') : tr('Kein Token hinterlegt.'));
  var tokenInput = el('input', {type: 'password', 'data-nv-field': 'github-token',
    placeholder: tr('GitHub-Token einfügen'), 'aria-label': tr('GitHub-Token einfügen')});
  var tokenSave = nvpButton(tr('Token speichern'), 'github-token-save', function () {
    var value = String(tokenInput.value || '').trim();
    if (!value) { nvpShowError(error, tr('Kein Token angegeben.')); return; }
    post({action: 'token.save', token: value}, function (result) {
      if (!result || result.ok === false) return;
      tokenInput.value = '';
      syncToken(result);
      setTx(authLine, tr('GitHub-Zugang eingerichtet.'));
      toast(bt(result.message) || tr('Token gespeichert'));
    });
  }, 'nv-primary');
  var tokenClear = nvpButton(tr('Token entfernen'), 'github-token-clear', function () {
    post({action: 'token.clear'}, function (result) {
      if (!result || result.ok === false) return;
      tokenInput.value = '';
      syncToken(result);
      setTx(authLine, tr('Kein Token hinterlegt.'));
      toast(bt(result.message) || tr('Token entfernt'));
    });
  });
  var connResult = el('div', {class: 'nv-muted', 'data-nv-github-connection': '', hidden: ''});
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
  var link = nvpButton(tr('Mit GitHub verknüpfen'), 'github-link', function () {
    var value = String(repo.value || '').trim();
    if (!value || value.indexOf('/') < 0) {
      nvpShowError(error, tr('Repository in der Form owner/name angeben'));
      return;
    }
    post({action: 'link', url: 'https://github.com/' + value + '.git'}, function (result) {
      if (result && result.ok !== false) {
        setTx(connectionState, tr('Verknüpft'));
        NV.render();
      }
    });
  });
  var unlink = nvpButton(tr('Verknüpfung lösen'), 'github-unlink', function () {
    post({action: 'unlink'}, function (result) {
      if (result && result.ok !== false) {
        setTx(connectionState, tr('Nicht verknüpft'));
        NV.render();
      }
    });
  });
  var save = nvpButton(tr('Einstellungen speichern'), 'github-settings-save', function () {
    post({action: 'settings', enabled: enabled.checked, repo: repo.value.trim(),
      label: label.value.trim(), api: apiBase.value.trim(), base: base.value.trim(),
      auto_merge: autoMerge.checked, issues_enabled: issuesEnabled.checked,
      issues_in_progress: issuesInProgress.value.trim(),
      issues_ready: issuesReady.value.trim(),
      issues_assignee: issuesAssignee.value.trim()}, function (result) {
      if (result && result.ok !== false) {
        setTx(connectionState, repo.value.trim() ? tr('Verknüpft') : tr('Nicht verknüpft'));
        toast(bt(result.message) || tr('Gespeichert'));
      }
    });
  }, 'nv-primary');

  /* --- Block 2: Branches --- */
  var branchRows = el('div', {class: 'nv-list'});
  (g.branches || []).forEach(function (branch) {
    var branchName = String(branch.name || '');
    branchRows.append(el('div', {class: 'nv-row',
      'data-nv-github-branch': branchName},
      el('span', {}, (branch.current ? '* ' : '') + branchName
        + ' (' + tr('Ahead/Behind') + ' ' + (branch.ahead || 0) + '/' + (branch.behind || 0) + ')'),
      nvpButton(tr('Auschecken'), 'github-checkout', function () {
        post({action: 'checkout', branch: branchName}, function (result) {
          if (result && result.ok !== false) NV.render();
        });
      })));
  });
  if (!(g.branches || []).length) {
    branchRows.append(el('p', {class: 'nv-muted'}, tr('Keine lokalen Branches erkannt.')));
  }
  var pushBranch = branchSelect('github-push-branch', 'github-push-branch',
    tr('Quell-Branch wählen'), currentBranch !== '-' ? currentBranch : '');
  var pushTarget = branchSelect('github-push-target', 'github-push-target',
    tr('Ziel-Branch wählen'), '');
  var sourceHelp = el('small', {'data-nv-github-help-source': '', class: 'nv-muted'},
    tr('Quell-Branch: der lokale Branch, dessen Stand übertragen wird'));
  var targetHelp = el('small', {'data-nv-github-help-target': '', class: 'nv-muted'},
    tr('Ziel-Branch: Remote-Branch, der den Stand erhält — leer lassen für denselben Namen'));

  /* --- Block 3: Synchronisieren --- */
  var pull = nvpButton(tr('Pull (aufholen, --ff-only)'), 'github-pull', function () {
    post({action: 'pull'}, function (result) {
      if (result && result.ok !== false) NV.render();
    });
  });
  var fetch = nvpButton(tr('Abrufen (fetch, kein Merge)'), 'github-fetch', function () {
    post({action: 'fetch'}, function (result) {
      if (result && result.ok !== false) NV.render();
    });
  });
  var push = nvpButton(tr('Push'), 'github-push', function () {
    post({action: 'push', branch: String(pushBranch.value || '').trim(),
      target: String(pushTarget.value || '').trim()}, function (result) {
      if (result && result.ok !== false) NV.render();
    });
  }, 'nv-primary');

  /* --- Block 5: Issues (Opt-in) --- */
  var issuesEnabled = el('input', {type: 'checkbox', 'data-nv-field': 'github-issues-enabled',
    'aria-label': tr('Issues-Sync aktivieren (GitHub als Quelle der Wahrheit)')});
  issuesEnabled.checked = !!g.issues_enabled;
  var issuesInProgress = el('input', {type: 'text', 'data-nv-field': 'issues_in_progress',
    value: String(g.issues_in_progress_label || ''), 'aria-label': tr('In-Progress-Label')});
  var issuesReady = el('input', {type: 'text', 'data-nv-field': 'issues_ready',
    value: String(g.issues_ready_label || ''), 'aria-label': tr('Ready-Label')});
  var issuesAssignee = el('input', {type: 'text', 'data-nv-field': 'issues_assignee',
    value: String(g.issues_assignee || ''), 'aria-label': tr('Assignee (leer = alle)')});
  var issuesSync = g.issues_enabled
    ? nvpButton(tr('Issues synchronisieren'), 'issues-sync', function () {
        post({action: 'issues.sync'}, function (result) {
          if (result && result.ok !== false) NV.render();
        });
      }, 'nv-primary')
    : null;

  /* --- Block 4: Merge-Request --- */
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
  var prExplain = el('p', {class: 'nv-muted'},
    tr('Der aktuelle Branch {{source}} wird nach {{target}} übernommen.',
      {source: currentBranch || '-', target: base.value.trim() || currentBranch || '-'}));

  return nvpSection('github', tr('Git & GitHub'), [
    el('h4', {}, tr('Verbindung')),
    el('div', {class: 'nv-row'}, connectionState, tokenState),
    nvpLabel(tr('Repository (owner/name)'), repo),
    el('p', {class: 'nv-muted'}, tr('Status: ')
      + (g.repo ? tr('Verknüpft') : tr('Nicht verknüpft'))
      + (g.branch && g.branch !== '-' ? ' · ' + tr('Branch') + ': ' + currentBranch : '')),
    authLine,
    el('div', {class: 'nv-row'}, tokenInput, tokenSave, tokenClear),
    el('div', {class: 'nv-row'}, connect, link, unlink),
    connResult,
    nvpLabel(tr('GitHub-Verknüpfung aktiv'), enabled),
    nvpLabel(tr('Label für vibe-Aufgaben'), label),
    nvpLabel(tr('API-Adresse'), apiBase),
    nvpLabel(tr('Basis-Branch (optional)'), base),
    autoMergeRow,
    el('div', {class: 'nv-row'}, save),

    el('h4', {}, tr('Branches')),
    el('p', {class: 'nv-muted'}, tr('Aktueller Branch: ') + currentBranch),
    branchRows,
    nvpLabel(tr('Quell-Branch'), pushBranch), sourceHelp,
    nvpLabel(tr('Ziel-Branch'), pushTarget), targetHelp,

    el('h4', {}, tr('Synchronisieren')),
    el('div', {class: 'nv-row'}, pull, fetch, push),

    el('h4', {}, tr('Merge-Request')),
    prExplain,
    el('div', {class: 'nv-row'}, pr, prConfirm), prResult,

    el('h4', {}, tr('Issues als Arbeitspakete')),
    nvpLabel(tr('Issues-Sync aktivieren (GitHub als Quelle der Wahrheit)'), issuesEnabled),
    el('p', {class: 'nv-muted'}, tr('Der einheitliche Sync synchronisiert beidseitig: zieht offene Issues samt Text, pusht neue Tickets, schließt gelöschte Tickets best effort auf GitHub und setzt erledigte Tickets über geschlossene Issues zurück. Ready-Label → offen/lauffähig, ohne Label → Entwurf.')),
    nvpLabel(tr('In-Progress-Label'), issuesInProgress),
    nvpLabel(tr('Ready-Label'), issuesReady),
    nvpLabel(tr('Assignee (leer = alle)'), issuesAssignee),
    el('div', {class: 'nv-row'}, issuesSync),
    error
  ]);
}

function nvpRightsSection(name, token, data) {
  var path = el('input', {type: 'text', 'data-nv-field': 'path',
    placeholder: tr('Verzeichnis'), 'aria-label': tr('Verzeichnis')});
  var list = el('div', {class: 'nv-list',
    style: 'display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));'
      + 'gap:var(--nv-space-2, 8px);'});
  function addRow(dir) {
    var row = el('div', {class: 'nv-row nv-right-row'}, el('code', {}, String(dir)));
    row.append(nvpButton(tr('Löschen'), 'rights-remove', function () {
      nvpPost(name, '/api/rights', {action: 'remove', path: String(dir)},
        'Gelöscht', token).then(function (result) {
          if (!NV.stale(token) || !result || result.ok === false) return;
          row.remove();
        });
    }));
    list.append(row);
  }
  (data.write_dirs || []).forEach(addRow);
  var error = nvpErrorBox();
  var add = nvpButton(tr('Hinzufügen'), 'rights-add', function () {
    var value = String(path.value || '').trim();
    if (!value) return;
    nvpPost(name, '/api/rights', {action: 'add', path: value},
      'Gespeichert', token).then(function (result) {
        if (!NV.stale(token) || !result || result.ok === false) return;
        path.value = '';
        addRow(value);
      });
  }, 'nv-primary');
  return nvpSection('writeaccess', tr('Schreibrechte'), [
    list, nvpLabel(tr('Verzeichnis'), path), el('div', {class: 'nv-row'}, add), error
  ]);
}

function nvpSandboxSection(name, token, sandbox) {
  var info = sandbox || {};
  var enabled = !!info.enabled;
  var toggle = nvpButton(enabled ? tr('Ausschalten') : tr('Einschalten'),
    'sandbox-toggle', function () {
      nvpPost(name, '/api/sandbox', {action: enabled ? 'off' : 'on'},
        'Gespeichert', token).then(function () { if (!NV.stale(token)) NV.render(); });
    }, 'nv-primary');
  var check = nvpButton(tr('Prüfen'), 'sandbox-check', function () {
    nvpPost(name, '/api/sandbox', {action: 'check'}, 'Geprüft', token);
  });
  var writeDirs = (info.write_dirs || []).join(', ') || '-';
  var tools = (info.tools || []).join(', ') || '-';
  return nvpSection('sandbox', tr('Sandbox'), [
    el('p', {}, tr('Die Sandbox grenzt die Arbeit des Agenten ein: '
      + 'Lesen und Arbeiten bleiben im Projekt, nach außen wirkt sie nur '
      + 'über ausdrücklich freigegebene Wege.')),
    el('ul', {},
      el('li', {}, tr('Erlaubt: Lesen im Projekt und Schreiben in freigegebenen Verzeichnissen.')),
      el('li', {}, tr('Verboten: Zugriffe außerhalb des Projekts und ungewollte Netzwerkzugriffe.')),
      el('li', {}, tr('Schreibverzeichnisse: {{dirs}}', {dirs: writeDirs})),
      el('li', {}, tr('Werkzeuge: {{tools}}', {tools: tools}))),
    el('p', {class: 'nv-muted'}, String(info.error || '')
      || tr('Sandbox-Status') + ': ' + (enabled ? tr('aktiv') : tr('inaktiv'))),
    el('div', {class: 'nv-row'}, toggle, check)
  ]);
}

/* AGENTS.md als erste Sektion: einklappbarer, standardmäßig offener Editor
   mit genau einem Textfeld für den vollständigen Dateiinhalt. Sicherungen
   werden mit Zeitstempel ausgewählt und vor der Wiederherstellung benannt.
   Es gibt keinen schreibgeschützten Sonderbereich mehr; vorhandener
   Dateiinhalt bleibt normal editierbar und wird unverändert zurückgeschrieben. */
function nvpAgentsFileText(file) {
  /* Der Server liefert den vollständigen Dateiinhalt als ``text``. */
  return file && typeof file.text === 'string' ? file.text : '';
}

function nvpAgentsFileSection(name, token, view) {
  var file = (view && view.agents_file) || {};
  var text = el('textarea', {rows: '14', 'data-nv-agents-text': '',
    'aria-label': tr('AGENTS.md')}, nvpAgentsFileText(file));
  var digest = String(file.digest || '');
  var error = nvpErrorBox();

  function adoptFile(fresh) {
    if (!fresh) return;
    digest = String(fresh.digest || digest);
    setTx(text, nvpAgentsFileText(fresh));
  }

  function backupLabel(entry) {
    if (entry && typeof entry === 'object') {
      return String(entry.name || entry.label || entry.timestamp
        || entry.ts || entry.time || tr('Sicherung'));
    }
    return String(entry || tr('Sicherung'));
  }
  var backupSelect = el('select', {'data-nv-agents-backup': '',
    'aria-label': tr('Sicherung auswählen')});
  function renderBackupOptions(entries) {
    backupSelect.replaceChildren();
    if (!entries || !entries.length) {
      backupSelect.append(el('option', {value: ''}, tr('Keine Sicherungen vorhanden')));
      return;
    }
    entries.forEach(function (entry) {
      var label = backupLabel(entry);
      backupSelect.append(el('option', {value: label}, label));
    });
  }
  renderBackupOptions(file.backups);
  function selectedBackup() {
    return String(backupSelect.value || '');
  }

  var restoreText = el('p', {class: 'nv-muted'}, '');
  var restoreConfirm = el('div', {class: 'nv-confirm',
    'data-nv-agents-restore-confirm': '', hidden: ''},
  restoreText,
  el('div', {class: 'nv-row'},
    nvpButton(tr('Ja, wiederherstellen'), 'agents-file-restore-confirm', async function () {
      nvpShowError(error, '');
      try {
        var result = await api('/api/agents_file', {
          name: name, action: 'restore', confirm: true,
          backup: selectedBackup()
        });
        if (NV.stale(token)) return;
        if (result && result.ok === false) { nvpShowError(error, bt(result.message)); return; }
        restoreConfirm.setAttribute('hidden', '');
        adoptFile(result && result.agents_file);
        if (result && result.agents_file) {
          renderBackupOptions(result.agents_file.backups);
        }
        toast(bt(result && result.message) || tr('Wiederhergestellt'));
      } catch (e) { nvpShowError(error, String(e && e.message || e)); }
    }, 'nv-primary'),
    nvpButton(tr('Abbrechen'), 'agents-file-restore-cancel', function () {
      restoreConfirm.setAttribute('hidden', '');
    })));

  var save = nvpButton(tr('Speichern'), 'agents-file-save', async function () {
    nvpShowError(error, '');
    try {
      var result = await api('/api/agents_file', {
        name: name, action: 'save',
        text: String(text.value || ''),
        digest: digest
      });
      if (NV.stale(token)) return;
      if (result && result.ok === false) { nvpShowError(error, bt(result.message)); return; }
      if (result && result.agents_file) {
        digest = String(result.agents_file.digest || digest);
      }
      toast(bt(result && result.message) || tr('Gespeichert'));
    } catch (e) { nvpShowError(error, String(e && e.message || e)); }
  }, 'nv-primary');

  var create = file.exists ? null : nvpButton(tr('Vorlage anlegen'), 'agents-file-create', function () {
    nvpPost(name, '/api/agents_file', {action: 'create'}, 'Gespeichert', token)
      .then(function (result) {
        if (NV.stale(token) || !result || result.ok === false) return;
        adoptFile(result.agents_file);
        NV.render();
      });
  });
  var backup = nvpButton(tr('Sicherung anlegen'), 'agents-file-backup', function () {
    nvpPost(name, '/api/agents_file', {action: 'backup'}, 'Gesichert', token)
      .then(function (result) {
        if (NV.stale(token)) return;
        if (result && result.agents_file) {
          renderBackupOptions(result.agents_file.backups);
        }
      });
  });
  var restore = nvpButton(tr('Wiederherstellen'), 'agents-file-restore', function () {
    setTx(restoreText, tr('Sicherung „{{name}}“ wiederherstellen? '
      + 'Der aktuelle Stand wird zuvor gesichert.', {name: selectedBackup() || '-'}));
    restoreConfirm.removeAttribute('hidden');
  });

  var section = nvpSection('agentsfile', 'AGENTS.md', []);
  section.replaceChildren(el('details', {open: '', 'data-nv-agents-section': ''},
    el('summary', {}, tr('AGENTS.md bearbeiten')),
    el('p', {class: 'nv-muted'},
      tr('Der vollständige Inhalt der Datei. Speichern schreibt ihn unverändert zurück.')),
    nvpLabel(tr('AGENTS.md'), text),
    el('div', {class: 'nv-row nv-form-actions'}, save, create, backup, restore),
    nvpLabel(tr('Sicherung auswählen'), backupSelect),
    restoreConfirm,
    error));
  return section;
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

  var heroRow;
  var hero = el('section', {class: 'nv-card nv-hero', 'data-nv-hero': ''},
    heroRow = el('div', {class: 'nv-row'},
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
          .then(function (result) {
            if (NV.stale(token) || !result || result.ok === false) return;
            nvpSyncPauseBadge(true);
          });
      }),
      stopButton));

  function nvpSyncPauseBadge(active) {
    var badge = hero.querySelector('[data-nv-pause-badge]');
    if (active && !badge) {
      heroRow.append(el('span', {class: 'nv-pill nv-warn', 'data-nv-pause-badge': ''},
        tr('Pause nach Paket aktiv')));
    } else if (!active && badge) {
      badge.remove();
    }
  }

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
      : tab === 'output' ? 'Ausgabe' : tab === 'assistant' ? 'Beschreibung'
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
  if (NV.feature('agentsfile')) placeholder(nvpAgentsFileSection(name, token, {}), panels.settings);
  placeholder(nvpBasicsSection(name, token, {}), panels.settings);
  if (NV.feature('sandbox')) placeholder(nvpSandboxSection(name, token, {}), panels.settings);
  placeholder(nvpTeamSection(name, token, {}), panels.settings);
  if (NV.feature('github')) placeholder(nvpGithubSection(name, token, {}), panels.settings);
  if (NV.feature('writeaccess')) placeholder(nvpRightsSection(name, token, {}), panels.settings);
  placeholder(nvpSessionLimitSection(name, token, {}), panels.settings);

  var view = {};
  try {
    var requests = [
      api('/api/project?name=' + enc),
      api('/api/run-state?name=' + enc),
      api('/api/project-agents?name=' + enc),
      api('/api/guide?name=' + enc),
      api('/api/autonomous?name=' + enc),
      api('/api/sessions?name=' + enc),
      /* GH-56: Die Board-Reihenfolge hängt an der gespeicherten
         Priorisierung; deshalb wird sie unabhängig vom optionalen
         Priorisierungs-Feature immer geladen. */
      api('/api/priority?name=' + enc)
    ];
    if (NV.feature('agentsfile')) requests.push(api('/api/agents_file?name=' + enc));
    requests.push(api('/api/global_agents_file'));
    var results = await Promise.all(requests);
    if (NV.stale(token)) return;
    view.data = results[0] || {};
    view.run = results[1] || {};
    view.agents = results[2] || {};
    view.guide = results[3] || {};
    view.autonomous = results[4] || {};
    view.sessions = results[5] || {};
    var cursor = 6;
    view.priority = results[cursor++] || {};
    if (NV.feature('agentsfile')) view.agents_file = results[cursor++];
    view.global_agents = results[cursor++];
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
  nvpSyncPauseBadge(!!data.pause_after);
  nvpStartRunPoll(name, token, pill, stopButton);

  /* ---- Überblick: Autonom-Karte, Kacheln, Zustand, Sitzungen ---- */
  var tickets = data.tickets || [];
  var feedback = data.feedback || [];
  var allItems = tickets.concat(feedback.map(function (row) {
    return Object.assign({}, row, {__feedback: true});
  }));

  panels.overview.append(nvpAutonomousCard(name, token, view.autonomous));

  var tiles = el('div', {class: 'nv-tiles'});
  [
    ['open', nvpCount(tickets, 'offen'), tr('Offene Pakete'),
      tr('Pakete, die noch nicht begonnen wurden')],
    ['progress', nvpCount(tickets, 'In Progress'), tr('In Progress'),
      tr('Pakete, an denen gerade gearbeitet wird')],
    ['blocked', nvpCount(tickets, 'BLOCKIERT'), tr('Blockiert'),
      tr('Pakete mit einer offenen Hürde')],
    ['waiting', nvpCount(tickets, 'WARTET AUF MERGE'), tr('Wartet auf Merge'),
      tr('Fertige Pakete, deren Merge noch aussteht')],
    ['done', nvpCount(tickets, 'erledigt'), tr('Erledigt'),
      tr('Abgeschlossene Pakete mit Nachweis')],
    ['draft', nvpCount(tickets, 'Draft'), tr('Entwurf'),
      tr('Noch nicht freigegebene Pakete')]
  ].forEach(function (tile) {
    tiles.append(el('div', {class: 'nv-card nv-tile', 'data-nv-tile': tile[0],
      title: tile[3]},
      el('div', {class: 'nv-tile-num'}, String(tile[1])),
      el('div', {class: 'nv-tile-label'}, tile[2])));
  });
  panels.overview.append(tiles);

  /* Letztes Arbeitspaket aus der effektiven Reihenfolge: manuell priorisierte
     Einträge zuerst, danach die automatische Standardreihenfolge. */
  var priorityView = view.priority || {};
  var effectiveIds = [];
  function collectEffective(entries) {
    (entries || []).forEach(function (entry) {
      var id = String(entry && entry.id || '');
      if (!id || String(entry.status || '') === 'erledigt'
          || effectiveIds.indexOf(id) >= 0) return;
      effectiveIds.push(id);
    });
  }
  collectEffective(priorityView.order);
  collectEffective(priorityView.standard);
  var lastId = effectiveIds[effectiveIds.length - 1] || '';
  var lastEntry = null;
  [].concat(priorityView.order || [], priorityView.standard || [], allItems)
    .some(function (entry) {
      if (String(entry && entry.id || '') === lastId) {
        lastEntry = entry;
        return true;
      }
      return false;
    });
  var lastText = lastId
    ? lastId + ' · ' + String(lastEntry && lastEntry.title || lastId)
      + ' · ' + nvpStateLabel(lastEntry && (lastEntry.state || lastEntry.status))
    : tr('Kein offenes Arbeitspaket');
  panels.overview.append(el('section', {class: 'nv-card nv-kv', 'data-nv-state-card': ''},
    el('h3', {}, tr('Zustand')),
    el('div', {}, el('strong', {}, tr('Letztes Arbeitspaket') + ': '), lastText),
    el('div', {}, el('strong', {}, tr('Letzter Commit') + ': '),
      el('code', {}, String(data.last || tr('Kein Commit vorhanden')))),
    el('div', {}, el('strong', {}, tr('Prüfung') + ': '),
      String(data.verify_cmd ? tr('Verfügbar') : tr('Nicht konfiguriert')))));

  var sessionBox = el('section', {class: 'nv-card nv-sessions-card'},
    el('h3', {}, tr('Sitzungen')),
    el('div', {'data-nv-sessions': ''}));
  var sessionList = sessionBox.querySelector('[data-nv-sessions]');

  function nvpPackageTitle(packageId) {
    var related = allItems.filter(function (item) {
      return String(item && item.id || '') === packageId;
    })[0];
    return String(related && related.title || '');
  }

  /* Eine Sitzungszeile bleibt kompakt: Agent, Zustand und relative Zeit
     tragen die Orientierung, die technische ID steht nachrangig und
     gekürzt darunter. Der Tooltip nennt die vollständige Session. */
  function nvpSessionLine(row) {
    var session = String(row.session || row.id || row.name || '');
    var resume = nvpButton(tr('Fortsetzen'), 'session-resume', function () {
      nvpPost(name, '/api/sessions', {action: 'continue', session: session},
        'Sitzung fortgesetzt', token);
    }, 'nv-compact');
    resume.setAttribute('title', tr('Setzt diese Sitzung fort'));
    return el('div', {class: 'nv-row nv-session-row',
      style: 'display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr) '
        + 'minmax(0,1fr) auto;gap:var(--nv-space-2, 8px);'
        + 'align-items:center;width:100%;'},
      el('span', {class: 'nv-muted', style: 'min-width:0;'},
        String(row.agent || '-')),
      el('span', {class: 'nv-pill nv-session-state'},
        String(row.state_label || row.state || tr('unbekannt'))),
      el('span', {class: 'nv-muted'}, nvpRelativeTime(row.last_seen)),
      el('span', {style: 'text-align:right;white-space:nowrap;'}, resume),
      el('code', {class: 'nv-session-id', title: session,
        style: 'grid-column:1/-1;font-size:.75rem;color:var(--nv-muted);'},
      nvpShortId(session, 12)));
  }

  /* GH-99: Sitzungen erscheinen im Kontext ihres Arbeitspakets. Bevorzugt
     nutzt die Ansicht das ``packages``-Feld mit der dauerhaft gespeicherten
     Zuordnung; fehlt es, gruppiert sie die flache Liste lokal nach
     ``package_id``. Sitzungen ohne gültige Paketzuordnung erscheinen nicht. */
  var sessionGroups = [];
  var sessionPayload = view.sessions || {};
  var flatRows = sessionPayload.sessions || sessionPayload.entries || [];
  var flatById = {};
  flatRows.forEach(function (row) {
    var session = String(row && (row.session || row.id || row.name) || '');
    if (session && !flatById[session]) flatById[session] = row;
  });
  /* Das Backend darf in ``packages.sessions`` entweder vollständige Zeilen
     oder nur die Session-IDs liefern; beides wird auf eine Zeile abgebildet. */
  function nvpSessionRow(entry) {
    if (typeof entry === 'string') return flatById[entry] || {session: entry};
    return entry || {};
  }
  if (Array.isArray(sessionPayload.packages) && sessionPayload.packages.length) {
    sessionPayload.packages.forEach(function (pkg) {
      var packageId = String(pkg && pkg.id || '');
      var packageRows = (pkg && pkg.sessions) || [];
      if (!packageId || !packageRows.length) return;
      sessionGroups.push({
        package_id: packageId,
        title: String(pkg.title || '') || nvpPackageTitle(packageId),
        rows: packageRows.map(nvpSessionRow)
      });
    });
  } else {
    var byPackage = {};
    flatRows.forEach(function (row) {
      var packageId = String(row && row.package_id || '');
      if (!packageId) return;
      if (!byPackage[packageId]) {
        byPackage[packageId] = {
          package_id: packageId,
          title: nvpPackageTitle(packageId),
          rows: []
        };
        sessionGroups.push(byPackage[packageId]);
      }
      byPackage[packageId].rows.push(row);
    });
  }

  if (!sessionGroups.length) {
    sessionList.append(el('p', {class: 'nv-muted'}, tr('Keine Sitzungen vorhanden')));
  }
  sessionGroups.forEach(function (group) {
    var packageText = group.package_id
      + (group.title ? ' · ' + group.title : '');
    var groupRows = el('div', {class: 'nv-session-rows'});
    group.rows.forEach(function (row) { groupRows.append(nvpSessionLine(row)); });
    sessionList.append(el('div', {class: 'nv-session-group',
      'data-nv-session-group': group.package_id},
      el('div', {class: 'nv-session-group-head'},
        el('span', {'data-nv-session-attach': ''}, packageText)),
      groupRows));
  });
  panels.overview.append(sessionBox);

  /* ---- Arbeit: Aktionsleiste → Filter → Priorisierung → Board/Liste ---- */
  var newRow = el('div', {class: 'nv-row nv-work-actions'},
    nvpButton(tr('Paket anlegen'), 'new-package', function () {
      nvpOpenTicketForm(name, token, {mode: 'package', type: 'feature',
        rows: tickets});
    }, 'nv-primary'),
    nvpButton(tr('Bug melden'), 'new-bug', function () {
      nvpOpenTicketForm(name, token, {mode: 'bug', type: 'bug',
        rows: feedback});
    }),
    nvpButton(tr('Feedback geben'), 'new-feedback', function () {
      nvpOpenTicketForm(name, token, {mode: 'feedback', type: 'feedback',
        rows: feedback});
    }));
  panels.work.append(newRow);

  var hideDoneButton = el('button', {class: 'nv-btn nv-secondary nv-compact',
    type: 'button', 'data-nv-work-hide-done': '', 'aria-pressed': 'true'},
  tr('Erledigte anzeigen') + ' (' + String(nvpCount(tickets, 'erledigt')) + ')');
  var searchInput = el('input', {type: 'search', 'data-nv-work-search': '',
    placeholder: tr('Arbeitspakete suchen'),
    'aria-label': tr('Arbeitspakete suchen')});
  var kindChips = el('div', {class: 'nv-row', 'data-nv-work-kinds': ''});
  [['all', tr('Alle')], ['package', tr('Pakete')], ['bug', tr('Bugs')],
    ['feedback', tr('Feedback')]].forEach(function (def) {
      kindChips.append(el('button', {class: 'nv-btn nv-ghost nv-compact',
        type: 'button', 'data-nv-work-kind': def[0],
        'aria-pressed': def[0] === 'all' ? 'true' : 'false'}, def[1]));
    });
  /* GH-56: Zustands-Chips decken alle Board-Zustände ab und sind mit Board
     und mobiler Liste identisch verdrahtet. */
  var stateChips = el('div', {class: 'nv-row nv-work-states',
    'data-nv-work-states': ''});
  [['draft', tr('Entwurf')], ['ready', tr('Bereit')],
    ['running', tr('In Progress')]]
    .forEach(function (def) {
      stateChips.append(el('button', {class: 'nv-btn nv-ghost nv-compact',
        type: 'button', 'data-nv-work-state': def[0],
        'aria-pressed': 'false'}, def[1]));
    });
  panels.work.append(NV.filterBar(
    NV.search({input: searchInput, placeholder: tr('Arbeitspakete suchen')}),
    kindChips, stateChips));
  /* GH-67: „Erledigte anzeigen“ ist ein eigener Schalter außerhalb der
     Schnellfilter; der frühere Closed-Chip entfällt. */
  panels.work.append(el('div', {class: 'nv-work-show-done',
    'data-nv-work-show-done': ''}, hideDoneButton));

  var workView = nvpWorkView(name, token, view, allItems);
  panels.work.append(workView);
  var surface = workView.querySelector('[data-nv-board], [data-nv-work-list]');

  var backToTop = el('button', {class: 'nv-btn nv-back-to-top', type: 'button',
    'data-nv-back-to-top': '', hidden: '', title: tr('Zurück zum Listenanfang')},
  '↑ ' + tr('Nach oben'));
  backToTop.style.cssText = 'position:fixed;right:24px;bottom:24px;z-index:60;';
  function nvpSyncBackToTop() {
    if (!document.contains(backToTop) || !document.contains(workView)) {
      window.removeEventListener('scroll', nvpSyncBackToTop);
      return;
    }
    var depth = Math.max(window.scrollY || 0,
      document.documentElement.scrollTop || 0);
    if (depth >= 600) backToTop.removeAttribute('hidden');
    else backToTop.setAttribute('hidden', '');
  }
  backToTop.addEventListener('click', function () {
    var top = workView.getBoundingClientRect().top
      + (window.scrollY || 0) - 16;
    window.scrollTo({top: Math.max(0, top), behavior: 'smooth'});
  });
  panels.work.append(backToTop);
  window.addEventListener('scroll', nvpSyncBackToTop, {passive: true});
  nvpSyncBackToTop();
  nvpWireWorkFilters(panels.work, hideDoneButton, nvpCount(tickets, 'erledigt'),
    surface);

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

  /* ---- Beschreibung ---- */
  panels.assistant.append(nvpAssistantPanel(name, token, view.guide));

  /* ---- Einstellungen: AGENTS.md → Basics → Sandbox → Team → GitHub →
     Schreibzugriff → Session-Limit → Fehlerbehebung (nur Android). ---- */
  placeholders.forEach(function (node) { node.remove(); });
  if (NV.feature('agentsfile')) {
    panels.settings.append(nvpAgentsFileSection(name, token, view));
  }
  panels.settings.append(nvpBasicsSection(name, token, data));
  if (NV.feature('sandbox')) {
    panels.settings.append(nvpSandboxSection(name, token, data.sandbox));
  }
  panels.settings.append(nvpTeamSection(name, token, view.agents));
  if (NV.feature('github')) panels.settings.append(nvpGithubSection(name, token, data.github));
  if (NV.feature('writeaccess')) panels.settings.append(nvpRightsSection(name, token, data));
  panels.settings.append(nvpSessionLimitSection(name, token, view.sessions));
  var troubleshooting = nvpTroubleshootingSection(name, token, data);
  if (troubleshooting) panels.settings.append(troubleshooting);

  if (!NV.stale(token)) panels[active].removeAttribute('hidden');
  NV.refreshBell();
};

/* F34 WP5: neue Texte dieser Ansicht (Schlüssel = deutscher Quelltext). */
if (window.VIBE_I18N && typeof VIBE_I18N.extend === 'function') {
  VIBE_I18N.extend({
    en: {
      "gerade eben": "just now",
      "vor {{n}} Min.": "{{n}} min ago",
      "vor {{n}} Std.": "{{n}} h ago",
      "vor {{n}} Tagen": "{{n}} days ago",
      "Paket": "Package",
      "Für diesen Eintrag liegt kein Nachweis vor.": "No proof is available for this entry.",
      "ohne Nachweis": "no proof",
      "Keine Beschreibung vorhanden.": "No description available.",
      "Abgeschlossene Einträge bleiben als Nachweis erhalten": "Completed entries are kept as evidence",
      "Abgeschlossen": "Completed",
      "Zustand wird vom Läufer gesetzt": "Status is set by the runner",
      "Paket abgeschlossen": "Package completed",
      "Keine offenen Einträge": "No open entries",
      "inaktiv": "inactive",
      "Projektziel": "Project goal",
      "Schritt": "Step",
      "von": "of",
      "Schrittübersicht": "Step overview",
      "Zu Schritt {{n}}": "Go to step {{n}}",
      "Ja, Typ ändern": "Yes, change type",
      "Projekttyp gespeichert": "Project type saved",
      "Den Projekttyp wirklich auf {{type}} ändern? ": "Really change the project type to {{type}}? ",
      "Sitzungslimit für dieses Projekt": "Session limit for this project",
      "Bitte ein Limit zwischen 1 und 100 angeben.": "Please enter a limit between 1 and 100.",
      "Sitzungslimit gespeichert": "Session limit saved",
      "gilt nur für dieses Projekt": "applies to this project only",
      "Fehlerbehebung": "Troubleshooting",
      "nur nötig, wenn etwas nicht funktioniert": "only needed when something does not work",
      "Auto-Merge aktivieren (Läufer mergt freigegebene Merge-Requests selbst)": "Enable auto-merge (runner merges approved merge requests itself)",
      "Verknüpft": "Linked",
      "Nicht verknüpft": "Not linked",
      "Token hinterlegt": "Token stored",
      "Kein Token": "No token",
      "GitHub-Zugang eingerichtet.": "GitHub access configured.",
      "Quell-Branch wählen": "Select source branch",
      "Ziel-Branch wählen": "Select target branch",
      "Der aktuelle Branch {{source}} wird nach {{target}} übernommen.": "The current branch {{source}} is transferred to {{target}}.",
      "Verbindung": "Connection",
      "Status: ": "Status: ",
      "Aktueller Branch: ": "Current branch: ",
      "Synchronisieren": "Synchronize",
      "Der einheitliche Sync synchronisiert beidseitig: zieht offene Issues samt Text, pusht neue Tickets, schließt gelöschte Tickets best effort auf GitHub und setzt erledigte Tickets über geschlossene Issues zurück. Ready-Label → offen/lauffähig, ohne Label → Entwurf.": "The unified sync synchronizes both ways: pulls open issues including their text, pushes new tickets, best-effort closes deleted tickets on GitHub, and marks tickets done via closed issues. Ready label → open/runnable, no label → draft.",
      "Zustand setzen": "Set state",
      "Die Sandbox grenzt die Arbeit des Agenten ein: ": "The sandbox confines the agent's work: ",
      "Erlaubt: Lesen im Projekt und Schreiben in freigegebenen Verzeichnissen.": "Allowed: reading in the project and writing in permitted directories.",
      "Verboten: Zugriffe außerhalb des Projekts und ungewollte Netzwerkzugriffe.": "Forbidden: access outside the project and unintended network access.",
      "Schreibverzeichnisse: {{dirs}}": "Write directories: {{dirs}}",
      "Werkzeuge: {{tools}}": "Tools: {{tools}}",
      "Sicherung": "Backup",
      "Gesichert": "Backed up",
      "Sicherung auswählen": "Select backup",
      "Keine Sicherungen vorhanden": "No backups available",
      "Sicherung „{{name}}“ wiederherstellen? ": "Restore backup '{{name}}'? ",
      "AGENTS.md bearbeiten": "Edit AGENTS.md",
      "Pakete, die noch nicht begonnen wurden": "Packages that have not been started",
      "Pakete, an denen gerade gearbeitet wird": "Packages currently in progress",
      "Pakete mit einer offenen Hürde": "Packages with an open blocker",
      "Fertige Pakete, deren Merge noch aussteht": "Finished packages whose merge is still pending",
      "Abgeschlossene Pakete mit Nachweis": "Completed packages with proof",
      "Noch nicht freigegebene Pakete": "Packages not yet approved",
      "Kein offenes Arbeitspaket": "No open work package",
      "Letztes Arbeitspaket": "Last work package",
      "Ohne Paket": "Without package",
      "Setzt diese Sitzung fort": "Resumes this session",
      "Alle": "All",
      "Bugs": "Bugs",
      "Zurück zum Listenanfang": "Back to the start of the list",
      "Details": "Details",
      "Schließen": "Close",
      "Bereit zum Merge": "Ready for Merge",
      "Sitzung fortsetzen": "Resume session",
      "Keine Sitzung zum Fortsetzen": "No session to resume",
      "Reihenfolge gespeichert": "Order saved",
      "Statuswechsel fehlgeschlagen": "Status change failed",
      "Schließen fehlgeschlagen": "Close failed",
      "Ticket geschlossen": "Ticket closed",
      "Ticket {{id}} wirklich schließen?": "Really close ticket {{id}}?",
      "Keine Tickets in dieser Spalte": "No tickets in this column",
      "Allgemeines Projekt ohne besondere Werkzeuge.": "General project without special tools.",
      "Android-Projekt mit Emulator und Gradle-Werkzeugen.": "Android project with emulator and Gradle tools.",
      "Swift-Projekt für Apple-Plattformen.": "Swift project for Apple platforms.",
      "Python-Projekt mit virtueller Umgebung.": "Python project with a virtual environment.",
      "Node- und TypeScript-Projekt mit npm-Werkzeugen.": "Node and TypeScript project with npm tools.",
      "Rust-Projekt mit Cargo-Werkzeugen.": "Rust project with Cargo tools.",
      "Go-Projekt mit den Go-Werkzeugen.": "Go project with the Go tools.",
      /* GH-67: Aktionen tragen keine Statuswörter im sichtbaren Text. */
      "Freigeben": "Release",
      "Gibt das Ticket für die Umsetzung frei": "Releases the ticket for implementation",
      "Zurück in Planung": "Back to planning",
      "Zieht das Ticket zurück in die Planung": "Moves the ticket back to planning",
      "Ticket Type": "Ticket Type",
      "Tickettyp": "Ticket type",
      "{{n}} priorisiertes Ticket": "{{n}} prioritized ticket",
      "{{n}} priorisierte Tickets": "{{n}} prioritized tickets",
      "Ticket abschließen": "Close ticket",
      "Schließt das Ticket dauerhaft und setzt es auf erledigt": "Permanently closes the ticket and marks it done",
      "Bereit zur Implementierung": "Ready for implementation",
      "In Umsetzung": "In progress"
    },
    de: {
      "gerade eben": "gerade eben",
      "vor {{n}} Min.": "vor {{n}} Min.",
      "vor {{n}} Std.": "vor {{n}} Std.",
      "vor {{n}} Tagen": "vor {{n}} Tagen",
      "Paket": "Paket",
      "Für diesen Eintrag liegt kein Nachweis vor.": "Für diesen Eintrag liegt kein Nachweis vor.",
      "ohne Nachweis": "ohne Nachweis",
      "Keine Beschreibung vorhanden.": "Keine Beschreibung vorhanden.",
      "Abgeschlossene Einträge bleiben als Nachweis erhalten": "Abgeschlossene Einträge bleiben als Nachweis erhalten",
      "Abgeschlossen": "Abgeschlossen",
      "Zustand wird vom Läufer gesetzt": "Zustand wird vom Läufer gesetzt",
      "Paket abgeschlossen": "Paket abgeschlossen",
      "Keine offenen Einträge": "Keine offenen Einträge",
      "inaktiv": "inaktiv",
      "Projektziel": "Projektziel",
      "Schritt": "Schritt",
      "von": "von",
      "Schrittübersicht": "Schrittübersicht",
      "Zu Schritt {{n}}": "Zu Schritt {{n}}",
      "Ja, Typ ändern": "Ja, Typ ändern",
      "Projekttyp gespeichert": "Projekttyp gespeichert",
      "Den Projekttyp wirklich auf {{type}} ändern? ": "Den Projekttyp wirklich auf {{type}} ändern? ",
      "Sitzungslimit für dieses Projekt": "Sitzungslimit für dieses Projekt",
      "Bitte ein Limit zwischen 1 und 100 angeben.": "Bitte ein Limit zwischen 1 und 100 angeben.",
      "Sitzungslimit gespeichert": "Sitzungslimit gespeichert",
      "gilt nur für dieses Projekt": "gilt nur für dieses Projekt",
      "Fehlerbehebung": "Fehlerbehebung",
      "nur nötig, wenn etwas nicht funktioniert": "nur nötig, wenn etwas nicht funktioniert",
      "Auto-Merge aktivieren (Läufer mergt freigegebene Merge-Requests selbst)": "Auto-Merge aktivieren (Läufer mergt freigegebene Merge-Requests selbst)",
      "Verknüpft": "Verknüpft",
      "Nicht verknüpft": "Nicht verknüpft",
      "Token hinterlegt": "Token hinterlegt",
      "Kein Token": "Kein Token",
      "GitHub-Zugang eingerichtet.": "GitHub-Zugang eingerichtet.",
      "Quell-Branch wählen": "Quell-Branch wählen",
      "Ziel-Branch wählen": "Ziel-Branch wählen",
      "Der aktuelle Branch {{source}} wird nach {{target}} übernommen.": "Der aktuelle Branch {{source}} wird nach {{target}} übernommen.",
      "Verbindung": "Verbindung",
      "Status: ": "Status: ",
      "Aktueller Branch: ": "Aktueller Branch: ",
      "Synchronisieren": "Synchronisieren",
      "Der einheitliche Sync synchronisiert beidseitig: zieht offene Issues samt Text, pusht neue Tickets, schließt gelöschte Tickets best effort auf GitHub und setzt erledigte Tickets über geschlossene Issues zurück. Ready-Label → offen/lauffähig, ohne Label → Entwurf.": "Der einheitliche Sync synchronisiert beidseitig: zieht offene Issues samt Text, pusht neue Tickets, schließt gelöschte Tickets best effort auf GitHub und setzt erledigte Tickets über geschlossene Issues zurück. Ready-Label → offen/lauffähig, ohne Label → Entwurf.",
      "Zustand setzen": "Zustand setzen",
      "Die Sandbox grenzt die Arbeit des Agenten ein: ": "Die Sandbox grenzt die Arbeit des Agenten ein: ",
      "Erlaubt: Lesen im Projekt und Schreiben in freigegebenen Verzeichnissen.": "Erlaubt: Lesen im Projekt und Schreiben in freigegebenen Verzeichnissen.",
      "Verboten: Zugriffe außerhalb des Projekts und ungewollte Netzwerkzugriffe.": "Verboten: Zugriffe außerhalb des Projekts und ungewollte Netzwerkzugriffe.",
      "Schreibverzeichnisse: {{dirs}}": "Schreibverzeichnisse: {{dirs}}",
      "Werkzeuge: {{tools}}": "Werkzeuge: {{tools}}",
      "Sicherung": "Sicherung",
      "Gesichert": "Gesichert",
      "Sicherung auswählen": "Sicherung auswählen",
      "Keine Sicherungen vorhanden": "Keine Sicherungen vorhanden",
      "Sicherung „{{name}}“ wiederherstellen? ": "Sicherung „{{name}}“ wiederherstellen? ",
      "AGENTS.md bearbeiten": "AGENTS.md bearbeiten",
      "Pakete, die noch nicht begonnen wurden": "Pakete, die noch nicht begonnen wurden",
      "Pakete, an denen gerade gearbeitet wird": "Pakete, an denen gerade gearbeitet wird",
      "Pakete mit einer offenen Hürde": "Pakete mit einer offenen Hürde",
      "Fertige Pakete, deren Merge noch aussteht": "Fertige Pakete, deren Merge noch aussteht",
      "Abgeschlossene Pakete mit Nachweis": "Abgeschlossene Pakete mit Nachweis",
      "Noch nicht freigegebene Pakete": "Noch nicht freigegebene Pakete",
      "Kein offenes Arbeitspaket": "Kein offenes Arbeitspaket",
      "Letztes Arbeitspaket": "Letztes Arbeitspaket",
      "Ohne Paket": "Ohne Paket",
      "Setzt diese Sitzung fort": "Setzt diese Sitzung fort",
      "Alle": "Alle",
      "Bugs": "Bugs",
      "Zurück zum Listenanfang": "Zurück zum Listenanfang",
      "Details": "Details",
      "Schließen": "Schließen",
      "Bereit zum Merge": "Bereit zum Merge",
      "Sitzung fortsetzen": "Sitzung fortsetzen",
      "Keine Sitzung zum Fortsetzen": "Keine Sitzung zum Fortsetzen",
      "Reihenfolge gespeichert": "Reihenfolge gespeichert",
      "Statuswechsel fehlgeschlagen": "Statuswechsel fehlgeschlagen",
      "Schließen fehlgeschlagen": "Schließen fehlgeschlagen",
      "Ticket geschlossen": "Ticket geschlossen",
      "Ticket {{id}} wirklich schließen?": "Ticket {{id}} wirklich schließen?",
      "Keine Tickets in dieser Spalte": "Keine Tickets in dieser Spalte",
      "Allgemeines Projekt ohne besondere Werkzeuge.": "Allgemeines Projekt ohne besondere Werkzeuge.",
      "Android-Projekt mit Emulator und Gradle-Werkzeugen.": "Android-Projekt mit Emulator und Gradle-Werkzeugen.",
      "Swift-Projekt für Apple-Plattformen.": "Swift-Projekt für Apple-Plattformen.",
      "Python-Projekt mit virtueller Umgebung.": "Python-Projekt mit virtueller Umgebung.",
      "Node- und TypeScript-Projekt mit npm-Werkzeugen.": "Node- und TypeScript-Projekt mit npm-Werkzeugen.",
      "Rust-Projekt mit Cargo-Werkzeugen.": "Rust-Projekt mit Cargo-Werkzeugen.",
      "Go-Projekt mit den Go-Werkzeugen.": "Go-Projekt mit den Go-Werkzeugen.",
      /* GH-67 */
      "Freigeben": "Freigeben",
      "Gibt das Ticket für die Umsetzung frei": "Gibt das Ticket für die Umsetzung frei",
      "Zurück in Planung": "Zurück in Planung",
      "Zieht das Ticket zurück in die Planung": "Zieht das Ticket zurück in die Planung",
      "Ticket Type": "Ticket-Typ",
      "Tickettyp": "Tickettyp",
      "{{n}} priorisiertes Ticket": "{{n}} priorisiertes Ticket",
      "{{n}} priorisierte Tickets": "{{n}} priorisierte Tickets",
      "Ticket abschließen": "Ticket abschließen",
      "Schließt das Ticket dauerhaft und setzt es auf erledigt": "Schließt das Ticket dauerhaft und setzt es auf erledigt",
      "Bereit zur Implementierung": "Bereit zur Implementierung",
      "In Umsetzung": "In Umsetzung"
    }
  });
}
