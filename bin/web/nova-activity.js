/* AP22 — Aktivität (Meilenstein B). Platzhalter für Läufe, Sessions und
   Rückfragen; die Glocke der Shell liefert schon die kompakte Sicht. */
'use strict';

NV.views.activity = function activity(context, token) {
  if (NV.stale(token)) return;
  document.getElementById('nv-main').replaceChildren(
    el('section', {class: 'nv-card'},
      el('h2', {}, tr('Aktivität')),
      el('p', {class: 'nv-muted'}, tr('Dieser Bereich wird im nächsten Meilenstein gebaut.'))));
  NV.refreshBell();
};
