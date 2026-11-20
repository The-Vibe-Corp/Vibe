/* AP22 — Projektansicht (Meilenstein B). Dieser Stub hält bereits den
   Projekttitel und die Panel-Hooks, damit Navigation und Neuanlage-Test den
   Weg in den Assistenten finden. Die eigentlichen Panels folgen in B. */
'use strict';

NV.views.project = function project(context, token) {
  if (NV.stale(token)) return;
  var name = String(context.name || '');
  var tabs = ['overview', 'work', 'output', 'assistant', 'settings'];
  var active = tabs.indexOf(context.tab) >= 0 ? context.tab : 'overview';
  var tabBar = el('div', {class: 'nv-tabs', role: 'tablist'});
  var panels = [];

  tabs.forEach(function (tab) {
    var selected = tab === active;
    tabBar.append(el('button', {class: 'nv-tab', type: 'button', role: 'tab',
      'data-nv-ptab': tab, 'aria-selected': selected ? 'true' : 'false',
      on: {click: function () { NV.navigate('#/project/' + encodeURIComponent(name) + '/' + tab); }}},
      tr(tab === 'overview' ? 'Überblick' : tab === 'work' ? 'Arbeit' :
        tab === 'output' ? 'Ausgabe' : tab === 'assistant' ? 'Assistent' : 'Einstellungen')));
    var panel = el('section', {class: 'nv-card', role: 'tabpanel', 'data-nv-ppanel': tab});
    if (!selected) panel.setAttribute('hidden', '');
    panel.append(el('h3', {}, tr(tab === 'overview' ? 'Überblick' : tab === 'work' ? 'Arbeit' :
      tab === 'output' ? 'Ausgabe' : tab === 'assistant' ? 'Assistent' : 'Einstellungen')),
      el('p', {class: 'nv-muted'}, tr('Dieser Bereich wird gerade aufgebaut. Deine Projekte und Arbeitspakete sind sicher — nichts geht verloren.')),
      el('div', {class: 'nv-skeleton', 'aria-hidden': 'true'}),
      el('div', {class: 'nv-skeleton nv-skeleton-short', 'aria-hidden': 'true'}));
    panels.push(panel);
  });

  document.getElementById('nv-main').replaceChildren(
    el('div', {class: 'nv-row'}, el('h2', {class: 'nv-page-title', 'data-nv-project-title': ''}, name)),
    tabBar, ...panels);
  NV.refreshBell();
};
