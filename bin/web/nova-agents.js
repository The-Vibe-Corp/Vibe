/* AP22 — Agenten (Meilenstein C). Platzhalter für Liste, Wizard und Editor. */
'use strict';

NV.views.agents = function agents(context, token) {
  if (NV.stale(token)) return;
  document.getElementById('nv-main').replaceChildren(
    el('section', {class: 'nv-card'},
      el('h2', {class: 'nv-page-title'}, tr('Agenten')),
      el('p', {class: 'nv-muted'}, tr('Dieser Bereich wird gerade aufgebaut. Deine Projekte und Arbeitspakete sind sicher — nichts geht verloren.')),
      el('div', {class: 'nv-skeleton', 'aria-hidden': 'true'}),
      el('div', {class: 'nv-skeleton nv-skeleton-short', 'aria-hidden': 'true'}),
      el('div', {class: 'nv-skeleton', 'aria-hidden': 'true'})));
  NV.refreshBell();
};
