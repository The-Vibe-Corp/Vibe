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

  var list = el('ul', {class: 'nv-combobox-list',
    'data-nv-combobox-list': '', role: 'listbox',
    id: 'nv-combobox-' + (NV_COMBOBOX_SEQUENCE += 1), hidden: ''});
  var input = el('input', {'data-nv-combobox-input': '', type: 'text',
    role: 'combobox', 'aria-expanded': 'false', 'aria-controls': list.id});
  var container = el('div', {class: 'nv-combobox',
    'data-nv-combobox': '', 'data-nv-field': opts && opts.field
      ? String(opts.field) : ''}, input, list);

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

  input.addEventListener('click', function () {
    if (isOpen()) close(); else open();
  });

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
