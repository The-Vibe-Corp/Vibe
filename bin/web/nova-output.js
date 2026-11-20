/* AP22 — Live-Ausgabe (Meilenstein B/C). Platzhalter, der später durch die
   echte Haupt-/Subagentenansicht ersetzt wird. */
'use strict';

NV.views.output = function output(context, token) {
  if (NV.stale(token)) return;
  document.getElementById('nv-main').replaceChildren(
    el('section', {class: 'nv-card'},
      el('h2', {class: 'nv-page-title'}, tr('Ausgabe')),
      el('p', {class: 'nv-muted'}, tr('Dieser Bereich wird gerade aufgebaut. Deine Projekte und Arbeitspakete sind sicher — nichts geht verloren.')),
      el('div', {class: 'nv-skeleton', 'aria-hidden': 'true'}),
      el('div', {class: 'nv-skeleton nv-skeleton-short', 'aria-hidden': 'true'}),
      el('div', {class: 'nv-skeleton', 'aria-hidden': 'true'})));
};
