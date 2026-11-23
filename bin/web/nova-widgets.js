/* F33 WP2 — Kombobox-Widget (Combobox/Agenten/Wizard/Editor).
 *
 * NV.combobox(values, current, opts) liefert
 * div.nv-combobox[data-nv-combobox][data-nv-field=<field>] mit
 * input[data-nv-combobox-input] (role=combobox, aria-expanded,
 * aria-controls) und ul[data-nv-combobox-list] (role=listbox) mit
 * li[data-nv-combobox-option] (role=option, aria-selected).
 *
 * Verhalten: Klick auf das Eingabefeld öffnet die gefilterte Liste
 * (Teilstring, case-insensitiv); Pfeiltasten navigieren; Enter/Klick
 * wählt; Esc schließt; der Wert steht in data-nv-value am Container und
 * im Eingabefeld. opts.blank erlaubt den leeren Wert (Anzeige opts.blank).
 * opts.onchange bekommt den neuen Wert. Alle Zustände über [hidden] auf
 * der Liste — keine display-Manipulation; DOM nur über el()/Textknoten.
 */
'use strict';

var NV_COMBOBOX_SEQUENCE = 0;

NV.combobox = function (values, current, opts) {
  var options = (values == null ? [] : values).map(function (value) {
    return String(value);
  });
  var blank = opts && opts.blank != null ? String(opts.blank) : null;
  var onchange = opts && typeof opts.onchange === 'function' ? opts.onchange : null;
  var placeholder = (opts && opts.placeholder) || tr('Modell suchen …');

  var list = el('ul', {class: 'nv-combobox-list',
    'data-nv-combobox-list': '', role: 'listbox',
    id: 'nv-combobox-' + (NV_COMBOBOX_SEQUENCE += 1), hidden: ''});
  var input = el('input', {'data-nv-combobox-input': '', type: 'text',
    role: 'combobox', 'aria-expanded': 'false', 'aria-controls': list.id,
    placeholder: placeholder, 'aria-label': placeholder});
  var icon = el('span', {class: 'nv-combobox-icon', 'aria-hidden': 'true'}, '⌕');
  var container = el('div', {class: 'nv-combobox',
    'data-nv-combobox': '', 'data-nv-field': opts && opts.field
      ? String(opts.field) : ''}, icon, input, list);

  var selected = String(current == null ? '' : current);
  var filter = '';
  var active = -1;
  var rendered = [];

  function display() {
    input.value = selected ? String(selected) : (blank || '');
  }

  function buildItems() {
    var items = [];
    if (blank != null) items.push('');
    var needle = filter.toLowerCase();
    options.forEach(function (value) {
      if (!needle || value.toLowerCase().indexOf(needle) >= 0) {
        items.push(value);
      }
    });
    return items;
  }

  function isOpen() { return list.hidden !== true; }

  function markActive() {
    rendered.forEach(function (item, index) {
      item.node.setAttribute('aria-selected', String(index === active));
    });
  }

  function render() {
    rendered = buildItems().map(function (value) {
      var node = el('li', {class: 'nv-combobox-option',
        'data-nv-combobox-option': '', role: 'option', 'aria-selected': 'false'});
      node.append(document.createTextNode(value ? value : (blank || '')));
      node.addEventListener('click', function () { select(value); });
      return {value: value, node: node};
    });
    list.replaceChildren();
    rendered.forEach(function (item) { list.append(item.node); });
    if (active >= rendered.length) {
      active = rendered.length ? 0 : -1;
    } else if (active < 0 && rendered.length) {
      active = 0;
    }
    markActive();
  }

  function open() {
    if (isOpen()) return;
    filter = '';
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    render();
    var wanted = -1;
    for (var i = 0; i < rendered.length; i++) {
      if (rendered[i].value === selected) { wanted = i; break; }
    }
    active = wanted >= 0 ? wanted : 0;
    markActive();
  }

  function close() {
    if (!isOpen()) return;
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    display();
  }

  function select(value) {
    selected = value;
    container.setAttribute('data-nv-value', value);
    close();
    display();
    if (onchange) onchange(value);
  }

  /* F34: Fokus und Klick öffnen die Liste; ein offener Klick klappt sie nicht
     wieder zu. Schließen über Escape oder Klick außerhalb. */
  input.addEventListener('focus', function () { open(); });
  input.addEventListener('click', function () { open(); });

  input.addEventListener('input', function () {
    if (!isOpen()) return;
    filter = input.value;
    render();
  });


  input.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && isOpen()) {
      close();
      return;
    }
    if (event.key === 'Enter' && isOpen()) {
      if (active >= 0 && rendered[active]) {
        event.preventDefault();
        select(rendered[active].value);
      }
      return;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (!isOpen()) open();
      active = event.key === 'ArrowDown'
        ? Math.min(active + 1, Math.max(rendered.length - 1, 0))
        : Math.max(active - 1, 0);
      markActive();
    }
  });

  container.setAttribute('data-nv-value', selected);
  display();
  return container;
};

document.addEventListener('click', function (event) {
  document.querySelectorAll('[data-nv-combobox]').forEach(function (container) {
    if (container.contains(event.target)) return;
    var input = container.querySelector('[data-nv-combobox-input]');
    var list = container.querySelector('[data-nv-combobox-list]');
    if (!input || input.getAttribute('aria-expanded') !== 'true') return;
    if (list) list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
  });
});

/* F34 — gemeinsame Rückfrage-Karte für Postfach und Aktivität.
 * Antworten werden lokal gezeichnet (Karte entfernen, Toast, Zähler/Banner/
 * Glocke über NV.questions aktualisieren); ein Voll-Neurender gibt es nicht.
 */
NV.questionCard = function (question, opts) {
  var q = question || {};
  var id = String(q.id || '');
  var settings = opts || {};
  var options = Array.isArray(q.options) ? q.options.map(String) : [];
  var article = el('article', {class: 'nv-question-card',
    'data-nv-question': '', 'data-nv-question-id': id});
  var meta = [q.project, q.agent].filter(Boolean).map(String).join(' · ');
  if (meta) article.append(el('div', {class: 'nv-question-meta'}, meta));
  article.append(el('p', {class: 'nv-question-text'}, String(q.text || '')));

  var error = el('p', {class: 'nv-form-error', 'data-nv-question-error': '', hidden: ''});
  var fields = [];
  var controls = [];

  function setBusy(busy) {
    if (busy) article.setAttribute('aria-busy', 'true');
    else article.removeAttribute('aria-busy');
    fields.forEach(function (field) { field.disabled = busy; });
    controls.forEach(function (button) { button.disabled = busy; });
  }

  async function send(payload) {
    if (article.getAttribute('aria-busy') === 'true') return;
    error.hidden = true;
    setBusy(true);
    try {
      var body = {action: 'answer', id: id};
      Object.keys(payload).forEach(function (key) { body[key] = payload[key]; });
      var result = await api('/api/questions', body);
      if (result && result.ok === false) {
        throw new Error(bt(result.message) || tr('Antwort nicht gespeichert.'));
      }
      var message = bt(result && result.message) || tr('Antwort gespeichert.');
      article.remove();
      if (NV.questions && typeof NV.questions.remove === 'function') {
        NV.questions.remove(id);
      }
      toast(message);
      if (typeof settings.onAnswered === 'function') settings.onAnswered(q, result);
    } catch (e) {
      error.hidden = false;
      error.textContent = String(e && e.message || e);
    } finally {
      setBusy(false);
    }
  }

  if (options.length) {
    var choices = el('div', {class: 'nv-question-options'});
    options.forEach(function (label, index) {
      var button = el('button', {class: 'nv-btn nv-ghost', type: 'button',
        'data-nv-answer': String(index + 1)}, String(label));
      // Der Hook ist 1-basiert, das Backend erwartet den 0-basierten Index.
      button.addEventListener('click', function () { send({option: index}); });
      controls.push(button);
      choices.append(button);
    });
    article.append(choices);
  }

  if (q.free_text !== false) {
    var field = el('input', {type: 'text', 'data-nv-answer-field': '',
      'data-nv-field': 'answer',
      'aria-label': tr('Eigene Antwort …'), placeholder: tr('Eigene Antwort …')});
    var sendButton = el('button', {class: 'nv-btn nv-primary', type: 'button',
      'data-nv-answer-send': ''}, tr('Antwort senden'));
    sendButton.addEventListener('click', function () {
      var value = String(field.value || '').trim();
      if (!value) {
        error.hidden = false;
        error.textContent = String(tr('Bitte eine Antwort eingeben.'));
        field.focus();
        return;
      }
      send({text: value});
    });
    field.addEventListener('keydown', function (event) {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      sendButton.click();
    });
    fields.push(field);
    controls.push(sendButton);
    article.append(el('div', {class: 'nv-question-answer'}, field, sendButton));
  }

  article.append(error);
  return article;
};
