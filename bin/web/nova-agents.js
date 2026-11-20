/* AP22 — Agenten (Meilenstein C). Platzhalter für Liste, Wizard und Editor. */
'use strict';

NV.views.agents = function agents(context, token) {
  if (NV.stale(token)) return;
  document.getElementById('nv-main').replaceChildren(
    el('section', {class: 'nv-card'},
      el('h2', {}, tr('Agenten')),
      el('p', {class: 'nv-muted'}, tr('Dieser Bereich wird im nächsten Meilenstein gebaut.'))));
  NV.refreshBell();
};
