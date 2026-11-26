/* F34 WP3 — Auswertungen: Kosten, Läufe und Umgebung.
 *
 * Route: #/evaluations/<tab> (costs | runs | environment). Der Tab-Wechsel
 * zeichnet nur denbetroffenen Bereich lokal neu und spiegelt den Tab per
 * history.replaceState in der URL — ohne hashchange und ohne NV.render().
 * Alle Daten stammen aus den echten Endpunkten /api/costs, /api/runs,
 * /api/ui_settings, /api/doctor, /api/paths und /api/harness.
 *
 * DOM nur mit el()/Textknoten; keine innerHTML mit dynamischen Inhalten,
 * keine rohen JSON-Objekte in der Anzeige. Zustände erscheinen als Badges.
 */
'use strict';

var NV_EVAL_TABS = ['costs', 'runs', 'environment'];
var NV_EVAL_PRUNE_STATES = ['finished', 'stopped', 'failed', 'ended', 'paused', 'blocked'];
var NV_EVAL_STATE_LABELS = {
  starting: 'startet', running: 'läuft', finished: 'abgeschlossen',
  stopped: 'gestoppt', paused: 'pausiert', failed: 'fehlgeschlagen',
  ended: 'abgebrochen', blocked: 'blockiert'
};
var NV_EVAL_STATE_CODES = {
  starting: 'running', running: 'running', finished: 'finished',
  stopped: 'stopped', paused: 'paused', failed: 'failed',
  ended: 'aborted', blocked: 'blocked'
};

function nvEvalText(value) { return String(value == null ? '' : value); }

/* GH-114: Zahlen und Beträge folgen der aktiven Sprache. Ohne I18N-Engine
   bleibt Deutsch der Rückfall, wie in der übrigen Nova-Oberfläche. */
function nvEvalLocale() {
  try {
    if (window.VIBE_I18N && typeof VIBE_I18N.locale === 'function') {
      return VIBE_I18N.locale();
    }
  } catch (error) { /* Fallback unten */ }
  return 'de-DE';
}

function nvEvalInt(value) {
  var number = Number(value) || 0;
  try { return new Intl.NumberFormat(nvEvalLocale()).format(number); }
  catch (error) { return String(number).replace(/\B(?=(\d{3})+(?!\d))/g, '.'); }
}

function nvEvalUsd(settings) {
  return String(settings && settings.currency || 'EUR').toUpperCase() === 'USD';
}

function nvEvalRate(settings) {
  var rate = Number(settings && settings.usd_rate);
  return isFinite(rate) && rate > 0 ? rate : 1;
}

/* Preise werden in EUR je 1 Mio. Tokens gespeichert. Die Anzeige folgt der
   globalen Einstellung currency/usd_rate: USD-Werte werden umgerechnet.
   Vier Nachkommastellen halten auch sehr kleine Beträge sichtbar. */
function nvEvalMoney(eurValue, ui) {
  var settings = ui || {};
  var usd = nvEvalUsd(settings);
  var value = (Number(eurValue) || 0) * (usd ? nvEvalRate(settings) : 1);
  var formatted;
  try {
    formatted = new Intl.NumberFormat(nvEvalLocale(), {
      minimumFractionDigits: 4, maximumFractionDigits: 4
    }).format(value);
  } catch (error) {
    formatted = value.toFixed(4).replace('.', ',')
      .replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  }
  return usd ? '$' + formatted : formatted + ' €';
}

/* GH-114: Startwert eines Preisfeldes in der eingestellten Anzeigewährung.
   Zwei bis vier Nachkommastellen halten den Wert lesbar; der rohe EUR-Wert
   wird zusätzlich am Feld hinterlegt, damit unveränderte Felder beim Speichern
   unverändert bleiben (keine Rundungsdrift über den Wechselkurs). */
function nvEvalPriceInput(eurValue, ui) {
  var settings = ui || {};
  var usd = nvEvalUsd(settings);
  var value = (Number(eurValue) || 0) * (usd ? nvEvalRate(settings) : 1);
  var formatted;
  try {
    formatted = new Intl.NumberFormat(nvEvalLocale(), {
      minimumFractionDigits: 2, maximumFractionDigits: 4
    }).format(value);
  } catch (error) { formatted = value.toFixed(2); }
  return usd ? '$' + formatted : formatted + ' €';
}

/* GH-114: Kursanzeige im Editor folgt der aktiven Locale (de-DE: 1,19). */
function nvEvalRateText(value) {
  var number = Number(value);
  if (!isFinite(number)) return nvEvalText(value);
  try {
    return new Intl.NumberFormat(nvEvalLocale(),
      {maximumFractionDigits: 4}).format(number);
  } catch (error) { return String(number).replace('.', ','); }
}

/* GH-114: Toleranter Währungsparser für Preisfelder. Akzeptiert reine
   Dezimalzahlen (1.5), deutsche (1,50 €, 1.234,50 €, 1.234 €), englische
   ($1,500.50, 1,234 €) und Währungscodes. Sind beide Separatortypen
   vorhanden, ist der letzte das Dezimalzeichen und alle früheren sind
   Tausendertrenner. Bei nur einem Separatortyp entscheidet die aktive
   Locale: das Dezimalzeichen bleibt Dezimalzeichen (letztes Vorkommen),
   das Tausenderzeichen wird nur bei gültiger 3er-Gruppierung als
   Tausendertrenner gelesen, sonst als Dezimalzeichen. Leere, negative oder
   nicht numerische Eingaben liefern null. */
function nvEvalGroupedPrice(text, separator) {
  var parts = text.split(separator);
  if (parts.length < 2) return false;
  if (!/^\d{1,3}$/.test(parts[0])) return false;
  for (var index = 1; index < parts.length; index += 1) {
    if (!/^\d{3}$/.test(parts[index])) return false;
  }
  return true;
}

function nvEvalParsePrice(raw) {
  var text = String(raw == null ? '' : raw).replace(/\u00a0/g, ' ').trim();
  if (!text) return null;
  text = text.replace(/[€$]/g, '').replace(/EUR/gi, '').replace(/USD/gi, '');
  text = text.replace(/\s/g, '');
  if (!text || /[^0-9.,]/.test(text)) return null;
  var comma = text.lastIndexOf(',');
  var dot = text.lastIndexOf('.');
  var decimal = '';
  if (comma !== -1 && dot !== -1) {
    decimal = comma > dot ? ',' : '.';
  } else if (comma !== -1 || dot !== -1) {
    var separator = comma !== -1 ? ',' : '.';
    var decimalChar = /^en/i.test(nvEvalLocale()) ? '.' : ',';
    var groupChar = decimalChar === ',' ? '.' : ',';
    if (separator === groupChar && nvEvalGroupedPrice(text, separator)) {
      text = text.replace(/[.,]/g, '');
    } else {
      decimal = separator;
    }
  }
  if (decimal) {
    var index = text.lastIndexOf(decimal);
    var whole = text.slice(0, index).replace(/[.,]/g, '');
    var fraction = text.slice(index + 1).replace(/[.,]/g, '');
    text = whole + '.' + fraction;
  } else if (comma !== -1 || dot !== -1) {
    text = text.replace(/[.,]/g, '');
  }
  if (!/^\d*\.?\d*$/.test(text) || text === '' || text === '.') return null;
  var number = Number(text);
  if (!isFinite(number) || number < 0) return null;
  return number;
}

/* GH-114: strukturiertes Monatsfeld der Detailansicht. Label und Wert
   bleiben getrennte Knoten, damit das Designsystem sie ausrichten kann. */
function nvEvalMonthField(key, label, value) {
  return el('div', {class: 'nv-cost-month-field', 'data-nv-cost-month-field': key},
    el('span', {class: 'nv-cost-month-label'}, label),
    el('strong', {class: 'nv-cost-month-value'}, value));
}

function nvEvalPercent(part, total) {
  var all = Number(total) || 0;
  var value = all ? (Number(part) || 0) / all * 100 : 0;
  try {
    return new Intl.NumberFormat(nvEvalLocale(), {
      minimumFractionDigits: 1, maximumFractionDigits: 1
    }).format(value) + ' %';
  } catch (error) {
    return String(value.toFixed(1)).replace('.', ',') + ' %';
  }
}

function nvEvalMonthKey() {
  var now = new Date();
  return String(now.getFullYear()) + '-'
    + String(now.getMonth() + 1).padStart(2, '0');
}

function nvEvalDuration(record) {
  var start = Date.parse(String(record && record.started || ''));
  var end = Date.parse(String(record && record.ended || ''));
  if (!isFinite(start) || !isFinite(end) || end < start) return '—';
  var seconds = Math.floor((end - start) / 1000);
  var hours = Math.floor(seconds / 3600);
  var minutes = Math.floor((seconds % 3600) / 60);
  var rest = seconds % 60;
  if (hours) return hours + ' h ' + minutes + ' min';
  if (minutes) return minutes + ' min ' + rest + ' s';
  return rest + ' s';
}

function nvEvalStateBadge(state) {
  var key = String(state || '');
  var label = NV_EVAL_STATE_LABELS[key] || 'unbekannt';
  var code = NV_EVAL_STATE_CODES[key] || 'unknown';
  return el('span', {class: 'nv-pill', 'data-nv-run-state': key,
    'data-state': code}, tr(label));
}

function nvEvalBackend(value) { return String(bt(value)); }

function nvEvalErrorBox() {
  return el('p', {class: 'nv-form-error', 'data-nv-eval-error': '', hidden: ''});
}

function nvEvalError(box, value) {
  if (!box) return;
  box.hidden = false;
  box.textContent = nvEvalText(value);
}

function nvEvalClearError(box) {
  if (!box) { return; }
  box.hidden = true;
  box.textContent = '';
}

function nvEvalFail(box, error) {
  nvEvalError(box, String(tr('Aktion fehlgeschlagen: '))
    + String(error && error.message || error));
}

/* Einheitlicher Kopf für die drei Bereiche. */
function nvEvalSection(title, nodes) {
  return el('section', {class: 'nv-card'},
    el('h3', {}, title), nodes);
}

/* ---------- Kosten ---------- */

function nvEvalLoadCosts(panel, token) {
  var summary = el('div', {class: 'nv-stat-grid', 'data-nv-cost-summary': ''});
  var currencyHint = el('small', {class: 'nv-muted',
    'data-nv-cost-currency-hint': '', hidden: ''});
  var empty = el('p', {class: 'nv-muted', 'data-nv-costs-empty': '', hidden: ''});
  var tableWrap = el('div', {class: 'nv-table-wrap'});
  var editor = el('section', {class: 'nv-card', 'data-nv-price-editor': '', hidden: ''});
  var error = nvEvalErrorBox();

  var openPrices = el('button', {class: 'nv-btn nv-primary', type: 'button',
    'data-nv-action': 'cost-prices'}, tr('Preise bearbeiten'));
  panel.replaceChildren(
    nvEvalSection(tr('Kostenübersicht'), [
      el('div', {class: 'nv-toolbar'}, openPrices), currencyHint, empty,
      summary, tableWrap
    ]),
    editor, error);

  var overview = {projects: [], monthly: [], total: {}, global_prices: {}};
  var ui = {currency: 'EUR', usd_rate: 1};
  var detailCache = {};
  var expanded = {};
  var editorOpen = false;
  var editorProject = '';
  var projectAgents = {};
  var projectAgentsLoading = {};

  function money(value) { return nvEvalMoney(value, ui); }

  function stat(label, key, value) {
    return el('div', {class: 'nv-stat', 'data-nv-cost-stat': key},
      el('span', {class: 'nv-muted'}, label), el('strong', {}, value));
  }

  function drawSummary() {
    var total = overview.total || {};
    var tokens = total.tokens || {};
    var monthKey = nvEvalMonthKey();
    var month = (overview.monthly || []).filter(function (row) {
      return String(row && row.month) === monthKey;
    })[0] || {};
    var monthTokens = month.tokens || {};
    summary.replaceChildren(
      stat(tr('Kosten gesamt'), 'total-cost', money(total.cost)),
      stat(tr('Eingabe'), 'total-input', nvEvalInt(tokens.input)),
      stat(tr('davon Cache'), 'total-cached', nvEvalInt(tokens.cached)),
      stat(tr('Ausgabe'), 'total-output', nvEvalInt(tokens.output)),
      stat(tr('Sitzungen'), 'total-sessions', nvEvalInt(total.sessions)),
      stat(tr('Aktueller Monat {{month}}', {month: monthKey}), 'current-month',
        money(month.cost) + ' · ' + tr('Eingabe') + ' ' + nvEvalInt(monthTokens.input)
        + ' · ' + tr('Ausgabe') + ' ' + nvEvalInt(monthTokens.output)),
      stat(tr('Projekte'), 'projects',
        nvEvalInt((overview.projects || []).length)));
  }

  function drawCurrencyHint() {
    var usd = String(ui.currency || 'EUR').toUpperCase() === 'USD';
    currencyHint.hidden = !usd;
    if (usd) {
      var rate = nvEvalText(ui.usd_rate).replace('.', ',');
      currencyHint.replaceChildren(el('span', {}, tr(
        'Beträge in USD: EUR-Wert × {{rate}} (Kurs aus den Einstellungen).',
        {rate: rate})));
    } else {
      currencyHint.replaceChildren();
    }
  }

  function drawEmpty() {
    var available = overview.available !== false;
    empty.hidden = available;
    if (available) { empty.replaceChildren(); return; }
    empty.replaceChildren(
      el('span', {}, tr('Kosten nicht verfügbar: ')), nvEvalText(overview.message),
      ' ', el('a', {href: '#/settings'}, tr('Modellpreise in den Einstellungen')));
  }

  function drawDetail(name, cell) {
    var data = detailCache[name];
    if (!data) {
      cell.replaceChildren(el('p', {class: 'nv-muted'},
        tr('Details werden geladen …')));
      api('/api/costs?name=' + encodeURIComponent(name)).then(function (answer) {
        if (NV.stale(token)) return;
        detailCache[name] = answer || {};
        drawTable();
      }).catch(function (failure) {
        if (!NV.stale(token)) nvEvalError(error, String(failure && failure.message || failure));
      });
      return;
    }
    var months = el('div', {'data-nv-cost-months': ''});
    (data.monthly || []).forEach(function (entry) {
      var tokens = entry.tokens || {};
      var month = el('div', {class: 'nv-cost-month',
        'data-nv-cost-month': nvEvalText(entry.month)},
        el('span', {class: 'nv-pill nv-type'}, nvEvalText(entry.month)),
        nvEvalMonthField('sessions', tr('Sitzungen'), nvEvalInt(entry.sessions)),
        nvEvalMonthField('input', tr('Eingabe'), nvEvalInt(tokens.input)),
        nvEvalMonthField('cached', tr('davon Cache'), nvEvalInt(tokens.cached)),
        nvEvalMonthField('output', tr('Ausgabe'), nvEvalInt(tokens.output)),
        nvEvalMonthField('cost', tr('Kosten'), money(entry.cost)));
      months.append(month);
    });
    var packages = el('table', {class: 'nv-table', 'data-nv-cost-packages': ''});
    packages.append(el('tr', {},
      el('th', {}, tr('Kennung')), el('th', {}, tr('Titel')),
      el('th', {}, tr('Monat')), el('th', {}, tr('Sitzungen')),
      el('th', {}, tr('Eingabe')), el('th', {}, tr('davon Cache')),
      el('th', {}, tr('Ausgabe')), el('th', {}, tr('Kosten')),
      el('th', {}, tr('Preisquelle'))));
    (data.packages || []).forEach(function (item) {
      var tokens = item.tokens || {};
      var models = item.models || [];
      var missing = models.some(function (model) {
        return String(model && model.price_source) === 'unbekannt';
      });
      var source = el('td', {});
      if (missing) {
        source.append(el('span', {class: 'nv-pill nv-warn', 'data-nv-cost-missing': ''},
          tr('Preis fehlt')), ' ');
        var link = el('button', {class: 'nv-btn nv-ghost', type: 'button',
          'data-nv-cost-price-link': ''}, tr('Preise hinterlegen'));
        link.addEventListener('click', function () { openEditor(name); });
        source.append(link);
      } else {
        var known = models.filter(function (model) {
          return model && model.price_source;
        })[0];
        source.append(nvEvalText(known && known.price_source || '—'));
      }
      packages.append(el('tr', {},
        el('td', {}, nvEvalText(item.id || '—')),
        el('td', {}, nvEvalText(item.title || '—')),
        el('td', {}, nvEvalText(item.month || '—')),
        el('td', {}, nvEvalInt(item.sessions)),
        el('td', {}, nvEvalInt(tokens.input)),
        el('td', {}, nvEvalInt(tokens.cached)),
        el('td', {}, nvEvalInt(tokens.output)),
        el('td', {}, money(item.cost)),
        source));
    });
    cell.replaceChildren(months, packages);
  }

  function drawTable() {
    var table = el('table', {class: 'nv-table', 'data-nv-cost-projects': ''});
    table.append(el('tr', {},
      el('th', {}, tr('Projekt')), el('th', {}, tr('Sitzungen')),
      el('th', {}, tr('Eingabe')), el('th', {}, tr('davon Cache')),
      el('th', {}, tr('Ausgabe')), el('th', {}, tr('Kosten')),
      el('th', {}, tr('Anteil'))));
    (overview.projects || []).forEach(function (project) {
      var name = nvEvalText(project.name);
      var tokens = project.tokens || {};
      var isOpen = !!expanded[name];
      var toggle = el('button', {class: 'nv-btn nv-ghost', type: 'button',
        'data-nv-cost-expand': '', 'aria-expanded': isOpen ? 'true' : 'false'},
        isOpen ? tr('Details schließen') : tr('Details'));
      toggle.addEventListener('click', function () {
        expanded[name] = !expanded[name];
        drawTable();
      });
      table.append(el('tr', {'data-nv-cost-project': name},
        el('td', {}, el('div', {class: 'nv-cost-project-cell'},
          toggle,
          el('span', {class: 'nv-cost-name', 'data-nv-cost-name': name,
            title: name}, name))),
        el('td', {}, nvEvalInt(project.sessions)),
        el('td', {}, nvEvalInt(tokens.input)),
        el('td', {}, nvEvalInt(tokens.cached)),
        el('td', {}, nvEvalInt(tokens.output)),
        el('td', {}, money(project.cost)),
        el('td', {}, nvEvalPercent(project.cost, overview.total && overview.total.cost))));
      var detailRow = el('tr', {'data-nv-cost-detail': '',
        'data-nv-cost-for': name, hidden: ''});
      var cell = el('td', {colspan: '7'});
      detailRow.append(cell);
      table.append(detailRow);
      if (isOpen) {
        detailRow.hidden = false;
        drawDetail(name, cell);
      }
    });
    tableWrap.replaceChildren(table);
  }

  function priceMapFor(project) {
    var global = (overview.global_prices || {});
    if (!project) return global;
    var detail = detailCache[project] || {};
    var merged = {};
    Object.keys(global).forEach(function (model) { merged[model] = global[model]; });
    var user = detail.user_prices || {};
    Object.keys(user).forEach(function (model) { merged[model] = user[model]; });
    return merged;
  }

  /* GH-114: Modelle aus allen Quellen sammeln — Preise (global/projekt),
     Nutzung (detail.models) und Agentkonfiguration des Projekts inklusive
     opencode-Subagenten. Die Modell-ID ist der Schlüssel; Duplikate über
     Quellen hinweg werden vermieden. */
  function agentRowsFor(project) {
    var view = projectAgents[project] || {};
    return Array.isArray(view.agents) ? view.agents : [];
  }

  function editorModels(project, prices) {
    var seen = {};
    var list = [];
    function add(value) {
      var id = nvEvalText(value);
      if (!id || id === '-' || seen[id]) return;
      seen[id] = true;
      list.push(id);
    }
    Object.keys(prices || {}).forEach(add);
    var detail = project && detailCache[project];
    (detail && detail.models || []).forEach(function (item) {
      add(item && item.model);
    });
    agentRowsFor(project).forEach(function (agent) {
      add(agent && agent.effective_model);
    });
    return list.sort();
  }

  /* Rollen stammen ausschließlich aus der Nutzung und der Agentkonfiguration.
     packages[].models[].agent wird bewusst nicht übernommen, wenn die
     Agentkonfiguration ein anderes Modell für den Agenten meldet. */
  function editorRoles(project) {
    var roles = {};
    function add(model, agent) {
      var id = nvEvalText(model);
      var name = nvEvalText(agent);
      if (!id || !name) return;
      if (!roles[id]) roles[id] = [];
      if (roles[id].indexOf(name) === -1) roles[id].push(name);
    }
    var detail = project && detailCache[project];
    (detail && detail.models || []).forEach(function (item) {
      (item && item.agents || []).forEach(function (agent) {
        add(item && item.model, agent);
      });
    });
    agentRowsFor(project).forEach(function (agent) {
      add(agent && agent.effective_model, agent && agent.name);
    });
    return roles;
  }

  function loadProjectAgents(project) {
    if (!project || projectAgents[project] || projectAgentsLoading[project]) return;
    projectAgentsLoading[project] = api(
      '/api/project-agents?name=' + encodeURIComponent(project)
    ).then(function (answer) {
      if (NV.stale(token)) return;
      projectAgents[project] = answer || {};
      if (editorOpen && editorProject === project) buildEditor();
    }).catch(function () {
      if (NV.stale(token)) return;
      projectAgents[project] = {agents: []};
      if (editorOpen && editorProject === project) buildEditor();
    });
  }

  function buildEditor() {
    var select = el('select', {'data-nv-price-project': '',
      'aria-label': tr('Projekt für Preise wählen')},
      el('option', {value: ''}, tr('Global')));
    (overview.projects || []).forEach(function (project) {
      select.append(el('option', {value: nvEvalText(project.name)},
        nvEvalText(project.name)));
    });
    select.value = editorProject;
    select.addEventListener('change', function () {
      editorProject = String(select.value || '');
      buildEditor();
      if (editorProject) {
        if (!detailCache[editorProject]) requestDetail(editorProject);
        loadProjectAgents(editorProject);
      }
    });

    var rows = el('div', {class: 'nv-stack'});
    var prices = priceMapFor(editorProject);
    var models = editorModels(editorProject, prices);
    var roles = editorRoles(editorProject);
    if (!models.length) {
      rows.append(el('p', {class: 'nv-muted'},
        tr('Keine Modelle mit bekannten Preisen.')));
    }
    models.forEach(function (model) {
      var price = prices[model] || {};
      var badges = el('div', {class: 'nv-price-agents'});
      (roles[model] || []).forEach(function (agent) {
        badges.append(el('span', {class: 'nv-pill', 'data-nv-price-agent': agent},
          nvEvalText(agent)));
      });
      var fields = el('div', {class: 'nv-price-fields'});
      [['input', tr('Eingabe')], ['cached_input', tr('davon Cache')],
       ['output', tr('Ausgabe')]].forEach(function (field) {
        var eur = price[field[0]] != null ? price[field[0]] : 0;
        var display = nvEvalPriceInput(eur, ui);
        var input = el('input', {type: 'text', inputmode: 'decimal',
          'data-nv-price-field': field[0], 'data-nv-price-model': nvEvalText(model),
          'data-nv-price-eur': nvEvalText(eur),
          'data-nv-price-display': display,
          value: display,
          'aria-label': String(field[1]) + ' ' + nvEvalText(model)});
        fields.append(el('label', {class: 'nv-price-field'},
          el('span', {}, field[1]), input));
      });
      rows.append(el('div', {class: 'nv-price-row', 'data-nv-price-row': model},
        el('div', {class: 'nv-price-model'},
          el('b', {}, nvEvalText(model)), badges), fields));
    });

    var usd = nvEvalUsd(ui);
    var rate = nvEvalRateText(ui.usd_rate);
    var editorError = nvEvalErrorBox();
    var save = el('button', {class: 'nv-btn nv-primary', type: 'button',
      'data-nv-action': 'cost-prices-save'}, tr('Preise speichern'));
    save.addEventListener('click', function () { savePrices(editorError); });
    editor.replaceChildren(
      el('h3', {}, tr('Modellpreise')),
      el('p', {class: 'nv-muted'}, tr(
        'Preise je 1 Mio. Tokens; Rangfolge: Projekt > global > Katalog.')),
      select,
      el('p', {class: 'nv-muted'}, tr(
        'Anzeige in {{currency}}; gespeichert wird EUR je 1 Mio. Tokens (Kurs {{rate}}).',
        {currency: usd ? 'USD' : 'EUR', rate: rate})),
      rows, editorError, el('div', {class: 'nv-row'}, save));
  }

  function requestDetail(name) {
    api('/api/costs?name=' + encodeURIComponent(name)).then(function (answer) {
      if (NV.stale(token)) return;
      detailCache[name] = answer || {};
      if (editorOpen && editorProject === name) buildEditor();
      drawTable();
    }).catch(function (failure) {
      if (!NV.stale(token)) nvEvalError(error, String(failure && failure.message || failure));
    });
  }

  function openEditor(project) {
    editorOpen = true;
    editorProject = nvEvalText(project || '');
    editor.hidden = false;
    buildEditor();
    if (editorProject) {
      if (!detailCache[editorProject]) requestDetail(editorProject);
      loadProjectAgents(editorProject);
    }
  }

  function savePrices(box) {
    nvEvalClearError(box);
    var prices = {};
    var invalid = false;
    var usd = nvEvalUsd(ui);
    var rate = nvEvalRate(ui);
    editor.querySelectorAll('input[data-nv-price-field]').forEach(function (input) {
      var number = nvEvalParsePrice(input.value);
      if (number == null) {
        nvEvalError(box, tr('Preis ist ungültig.'));
        invalid = true;
        return;
      }
      /* Unveränderte Felder übernehmen den rohen EUR-Basiswert. Die Anzeige
         ist bei USD auf vier Nachkommastellen gerundet; ein Rückrechnen über
         den Kurs würde den gespeicherten Wert sonst driften lassen. */
      var shown = nvEvalParsePrice(input.getAttribute('data-nv-price-display'));
      var stored = nvEvalParsePrice(input.getAttribute('data-nv-price-eur'));
      if (shown != null && stored != null && number === shown) {
        number = stored;
      } else if (usd) {
        number = number / rate;
      }
      var model = nvEvalText(input.getAttribute('data-nv-price-model'));
      if (!prices[model]) prices[model] = {};
      prices[model][nvEvalText(input.getAttribute('data-nv-price-field'))] = number;
    });
    if (invalid) return;
    var payload = {action: editorProject ? 'prices' : 'prices_global', prices: prices};
    if (editorProject) payload.name = editorProject;
    api('/api/costs', payload).then(function (answer) {
      if (NV.stale(token)) return;
      if (answer && answer.ok === false) {
        nvEvalError(box, nvEvalBackend(answer.message));
        return;
      }
      toast(nvEvalBackend(answer && answer.message) || tr('Preise gespeichert'));
      var refreshing = [api('/api/costs').catch(function () { return overview; })];
      if (editorProject) {
        refreshing.push(api('/api/costs?name=' + encodeURIComponent(editorProject))
          .catch(function () { return detailCache[editorProject]; }));
      }
      Promise.all(refreshing).then(function (results) {
        if (NV.stale(token)) return;
        overview = results[0] || overview;
        if (editorProject && results[1]) detailCache[editorProject] = results[1];
        draw();
      }).catch(function () { if (!NV.stale(token)) draw(); });
    }).catch(function (failure) { nvEvalFail(box, failure); });
  }

  function draw() {
    drawCurrencyHint();
    drawEmpty();
    drawSummary();
    drawTable();
    if (editorOpen) buildEditor();
  }

  openPrices.addEventListener('click', function () { openEditor(''); });

  Promise.all([
    api('/api/costs').catch(function () { return overview; }),
    api('/api/ui_settings').catch(function () { return ui; })
  ]).then(function (results) {
    if (NV.stale(token)) return;
    overview = results[0] || overview;
    ui = results[1] || ui;
    draw();
  }).catch(function (failure) {
    if (!NV.stale(token)) nvEvalFail(error, failure);
  });
}

/* ---------- Läufe ---------- */

function nvEvalLoadRuns(panel, token) {
  var searchInput = el('input', {type: 'search', 'data-nv-run-search': '',
    placeholder: tr('Läufe durchsuchen'), 'aria-label': tr('Läufe durchsuchen')});
  var search = NV.search({input: searchInput, placeholder: tr('Läufe durchsuchen'),
    oninput: drawRows});
  var stateSelect = el('select', {'data-nv-run-state': '',
    'aria-label': tr('Zustand filtern')},
    el('option', {value: ''}, tr('Alle Zustände')));
  Object.keys(NV_EVAL_STATE_LABELS).forEach(function (state) {
    stateSelect.append(el('option', {value: state}, tr(NV_EVAL_STATE_LABELS[state])));
  });
  stateSelect.addEventListener('change', drawRows);

  var prune = el('button', {class: 'nv-btn', type: 'button',
    'data-nv-action': 'runs-prune'}, tr('Verwaiste beenden'));
  var cleanup = el('button', {class: 'nv-btn nv-danger', type: 'button',
    'data-nv-action': 'runs-cleanup'}, tr('Abgeschlossene entfernen ({{n}})', {n: 0}));
  var result = el('div', {class: 'nv-note', 'data-nv-runs-result': '', hidden: ''});
  var tableWrap = el('div', {class: 'nv-table-wrap'});
  var error = nvEvalErrorBox();
  panel.replaceChildren(
    nvEvalSection(tr('Run-Register'), [
      NV.filterBar(search, stateSelect, prune, cleanup),
      result, tableWrap, error
    ]));

  var records = [];

  function cleanupCount() {
    return records.filter(function (record) {
      return NV_EVAL_PRUNE_STATES.indexOf(String(record && record.state)) !== -1;
    }).length;
  }

  function visibleRows() {
    var query = String(searchInput.value || '').trim().toLowerCase();
    var state = String(stateSelect.value || '');
    return records.filter(function (record) {
      if (state && String(record && record.state) !== state) return false;
      if (!query) return true;
      return [record.id, record.name, record.project, record.session, record.state,
        record.agent].some(function (value) {
        return String(value == null ? '' : value).toLowerCase().indexOf(query) !== -1;
      });
    });
  }

  function drawRows() {
    var table = el('table', {class: 'nv-table', 'data-nv-run-table': ''});
    table.append(el('tr', {},
      el('th', {}, tr('Lauf')), el('th', {}, tr('Projekt')),
      el('th', {}, tr('Zustand')), el('th', {}, tr('Sitzung')),
      el('th', {}, tr('Start')), el('th', {}, tr('Dauer')),
      el('th', {}, tr('bereinigbar'))));
    var rows = visibleRows();
    if (!rows.length) {
      table.append(el('tr', {}, el('td', {colspan: '7'},
        nvEvalEmpty(tr('Keine Läufe im Register.')))));
    }
    rows.forEach(function (record) {
      var project = nvEvalText(record.name || record.project || '—');
      var pruneable = NV_EVAL_PRUNE_STATES.indexOf(String(record.state)) !== -1
        ? el('span', {class: 'nv-muted', 'data-nv-run-pruneable': ''},
          tr('bereinigbar')) : null;
      table.append(el('tr', {'data-nv-run': nvEvalText(record.id)},
        el('td', {}, el('code', {}, nvEvalText(record.id))),
        el('td', {}, project),
        el('td', {}, nvEvalStateBadge(record.state)),
        el('td', {}, record.session
          ? el('code', {}, nvEvalText(record.session)) : el('span', {class: 'nv-muted'}, '—')),
        el('td', {}, nvEvalText(record.started || '—')),
        el('td', {}, nvEvalDuration(record)),
        el('td', {}, pruneable)));
    });
    tableWrap.replaceChildren(table);
  }

  function showLines(lines, headline) {
    if (!lines || !lines.length) return;
    var box = el('div', {});
    lines.forEach(function (line) { box.append(el('div', {}, nvEvalText(line))); });
    result.replaceChildren(el('b', {}, headline), box);
    result.hidden = false;
  }

  function reload() {
    api('/api/runs').then(function (answer) {
      if (NV.stale(token)) return;
      records = (answer && answer.records) || [];
      cleanup.replaceChildren(el('span', {}, tr('Abgeschlossene entfernen ({{n}})',
        {n: cleanupCount()})));
      drawRows();
    }).catch(function (failure) {
      if (!NV.stale(token)) nvEvalFail(error, failure);
    });
  }

  prune.addEventListener('click', function () {
    nvEvalClearError(error);
    api('/api/runs', {action: 'prune'}).then(function (answer) {
      if (NV.stale(token)) return;
      if (answer && answer.ok === false) {
        nvEvalError(error, nvEvalBackend(answer.message));
        return;
      }
      toast(nvEvalBackend(answer && answer.message) || tr('Register bereinigt'));
      showLines(answer && answer.lines, tr('Bereinigungsergebnis'));
      reload();
    }).catch(function (failure) { nvEvalFail(error, failure); });
  });

  cleanup.addEventListener('click', function () {
    nvEvalClearError(error);
    api('/api/runs', {action: 'cleanup'}).then(function (answer) {
      if (NV.stale(token)) return;
      if (answer && answer.ok === false) {
        nvEvalError(error, nvEvalBackend(answer.message));
        return;
      }
      var removed = Number(answer && answer.removed) || 0;
      toast(nvEvalBackend(answer && answer.message)
        || tr('{{n}} entfernt', {n: removed}));
      result.replaceChildren(
        el('b', {}, tr('Bereinigungsergebnis')),
        el('div', {}, tr('{{n}} entfernt', {n: removed})),
        el('div', {}, nvEvalText(answer && answer.message || '')));
      result.hidden = false;
      reload();
    }).catch(function (failure) { nvEvalFail(error, failure); });
  });

  reload();
}

function nvEvalEmpty(message) { return el('p', {class: 'nv-muted nv-empty'}, message); }

/* ---------- Umgebung ---------- */

function nvEvalLoadEnvironment(panel, token) {
  var doctor = el('div', {'data-nv-env-doctor': ''});
  var paths = el('div', {'data-nv-paths': ''});
  var harness = el('div', {'data-nv-harness-status': ''});
  var error = nvEvalErrorBox();
  panel.replaceChildren(
    nvEvalSection(tr('Prüfungen'), doctor),
    nvEvalSection(tr('Aufgelöste Pfade'), paths),
    nvEvalSection(tr('Harness'), harness), error);

  Promise.all([
    api('/api/doctor').catch(function () { return []; }),
    api('/api/paths').catch(function () { return {paths: {}}; }),
    api('/api/harness').catch(function () { return {}; })
  ]).then(function (answers) {
    if (NV.stale(token)) return;
    var checks = Array.isArray(answers[0]) ? answers[0] : [];
    var pathMap = (answers[1] && answers[1].paths) || {};
    var harnessStatus = answers[2] || {};

    var rows = el('div', {class: 'nv-list'});
    checks.forEach(function (check) {
      var ok = !!check.ok;
      rows.append(el('div', {class: 'nv-row', 'data-nv-doctor-row': '',
        'data-nv-ok': ok ? 'true' : 'false'},
        el('span', {class: ok ? 'nv-pill nv-ok' : 'nv-pill nv-warn'},
          ok ? tr('OK') : tr('FEHL')),
        el('span', {}, nvEvalBackend(check.label)),
        ok || !check.hint ? null : el('span', {class: 'nv-muted'},
          tr('Hinweis') + ': ' + nvEvalBackend(check.hint))));
    });
    if (!checks.length) rows.append(nvEvalEmpty(tr('Keine Prüfungen vorhanden.')));
    doctor.replaceChildren(rows);

    var pathRows = el('div', {});
    Object.keys(pathMap).forEach(function (key) {
      pathRows.append(el('div', {class: 'nv-row'},
        el('code', {}, nvEvalText(key)),
        el('span', {}, nvEvalText(pathMap[key]))));
    });
    if (!Object.keys(pathMap).length) {
      pathRows.append(nvEvalEmpty(tr('Keine Pfade vorhanden.')));
    }
    paths.replaceChildren(pathRows);

    var harnessRows = el('div', {});
    harnessRows.append(el('p', {class: 'nv-muted'},
      tr('Auswahl') + ': ' + nvEvalText(harnessStatus.selected || '—')));
    (harnessStatus.harnesses || []).forEach(function (item) {
      harnessRows.append(el('div', {class: 'nv-row'},
        el('b', {}, nvEvalText(item.name || item.harness || '—')),
        el('span', {class: 'nv-muted'}, nvEvalText(item.harness || '')),
        el('span', {class: item.installed ? 'nv-pill nv-ok' : 'nv-pill nv-warn'},
          item.installed ? tr('Installiert') : tr('Nicht installiert'))));
    });
    harness.replaceChildren(harnessRows);
  }).catch(function (failure) {
    if (!NV.stale(token)) nvEvalFail(error, failure);
  });
}

/* ---------- Ansicht und Tab-Wechsel ---------- */

NV.views.evaluations = function evaluations(context, token) {
  if (NV.stale(token)) return;

  function tabFromHash() {
    var match = (location.hash || '').match(/^#\/?evaluations\/([a-z]+)/);
    var tab = match ? match[1] : 'costs';
    return NV_EVAL_TABS.indexOf(tab) !== -1 ? tab : 'costs';
  }

  var active = tabFromHash();
  var nav = el('nav', {class: 'nv-tabs', 'data-nv-eval-tabs': '', role: 'tablist'});
  var panels = {};
  var buttons = {};
  var labels = {
    costs: tr('Kosten'), runs: tr('Läufe'), environment: tr('Umgebung')
  };

  NV_EVAL_TABS.forEach(function (name) {
    var button = el('button', {class: 'nv-btn', type: 'button', role: 'tab',
      'data-nv-etab': name, 'aria-selected': String(name === active)}, labels[name]);
    button.addEventListener('click', function () { activate(name); });
    buttons[name] = button;
    nav.append(button);
    var panel = el('section', {class: 'nv-eval-panel',
      'data-nv-eval-panel': name, role: 'tabpanel', hidden: ''});
    panels[name] = panel;
  });

  document.getElementById('nv-main').replaceChildren(
    el('h2', {class: 'nv-page-title'}, tr('Auswertungen')),
    nav, panels.costs, panels.runs, panels.environment);

  var loaded = {};
  function ensureLoaded(name) {
    if (loaded[name]) return;
    loaded[name] = true;
    if (name === 'costs') nvEvalLoadCosts(panels.costs, token);
    else if (name === 'runs') nvEvalLoadRuns(panels.runs, token);
    else nvEvalLoadEnvironment(panels.environment, token);
  }

  function activate(name) {
    if (NV_EVAL_TABS.indexOf(name) === -1 || NV.stale(token)) return;
    active = name;
    NV_EVAL_TABS.forEach(function (other) {
      buttons[other].setAttribute('aria-selected', String(other === name));
      panels[other].hidden = other !== name;
    });
    var hash = '#/evaluations/' + name;
    if (location.hash !== hash) history.replaceState(null, '', hash);
    ensureLoaded(name);
  }

  activate(active);
  NV.refreshBell();
};

/* F34 WP3: neue Texte dieser Ansicht (Schlüssel = deutscher Quelltext). */
if (window.VIBE_I18N && typeof VIBE_I18N.extend === 'function') {
  VIBE_I18N.extend({
    en: {
      'Kostenübersicht': 'Cost overview',
      'Kosten gesamt': 'Total cost',
      'davon Cache': 'of which cached',
      'Aktueller Monat {{month}}': 'Current month {{month}}',
      'Kosten nicht verfügbar: ': 'Costs unavailable: ',
      'Modellpreise in den Einstellungen': 'Model prices in settings',
      'Preise bearbeiten': 'Edit prices',
      'Beträge in USD: EUR-Wert × {{rate}} (Kurs aus den Einstellungen).':
        'Amounts in USD: EUR value × {{rate}} (rate from settings).',
      'Details': 'Details',
      'Details schließen': 'Hide details',
      'Details werden geladen …': 'Loading details …',
      'Kennung': 'ID',
      'Titel': 'Title',
      'Monat': 'Month',
      'Anteil': 'Share',
      'Preisquelle': 'Price source',
      'Preis fehlt': 'Price missing',
      'Preise hinterlegen': 'Add prices',
      'Modellpreise': 'Model prices',
      'Preise je 1 Mio. Tokens; Rangfolge: Projekt > global > Katalog.':
        'Prices per 1M tokens; precedence: project > global > catalog.',
      'Projekt für Preise wählen': 'Select project for prices',
      'Anzeige in {{currency}}; gespeichert wird EUR je 1 Mio. Tokens (Kurs {{rate}}).':
        'Shown in {{currency}}; stored in EUR per 1M tokens (rate {{rate}}).',
      'Keine Modelle mit bekannten Preisen.': 'No models with known prices.',
      'Preis ist ungültig.': 'Price is invalid.',
      'Preise gespeichert': 'Prices saved',
      'Run-Register': 'Run registry',
      'Läufe durchsuchen': 'Search runs',
      'Zustand filtern': 'Filter by state',
      'Alle Zustände': 'All states',
      'Verwaiste beenden': 'End orphaned runs',
      'Abgeschlossene entfernen ({{n}})': 'Remove completed ({{n}})',
      '{{n}} entfernt': '{{n}} removed',
      'Lauf': 'Run',
      'Dauer': 'Duration',
      'bereinigbar': 'pruneable',
      'startet': 'starting',
      'läuft': 'running',
      'abgeschlossen': 'completed',
      'gestoppt': 'stopped',
      'pausiert': 'paused',
      'fehlgeschlagen': 'failed',
      'abgebrochen': 'aborted',
      'unbekannt': 'unknown',
      'Keine Läufe im Register.': 'No runs in the registry.',
      'FEHL': 'FAIL',
      'OK': 'OK',
      'Hinweis': 'Note',
      'Keine Prüfungen vorhanden.': 'No checks available.',
      'Keine Pfade vorhanden.': 'No paths available.',
      'Auswahl': 'Selection',
      'Installiert': 'Installed',
      'Nicht installiert': 'Not installed'
    },
    de: {
      'Kostenübersicht': 'Kostenübersicht',
      'Kosten gesamt': 'Kosten gesamt',
      'davon Cache': 'davon Cache',
      'Aktueller Monat {{month}}': 'Aktueller Monat {{month}}',
      'Kosten nicht verfügbar: ': 'Kosten nicht verfügbar: ',
      'Modellpreise in den Einstellungen': 'Modellpreise in den Einstellungen',
      'Preise bearbeiten': 'Preise bearbeiten',
      'Beträge in USD: EUR-Wert × {{rate}} (Kurs aus den Einstellungen).':
        'Beträge in USD: EUR-Wert × {{rate}} (Kurs aus den Einstellungen).',
      'Details': 'Details',
      'Details schließen': 'Details schließen',
      'Details werden geladen …': 'Details werden geladen …',
      'Kennung': 'Kennung',
      'Titel': 'Titel',
      'Monat': 'Monat',
      'Anteil': 'Anteil',
      'Preisquelle': 'Preisquelle',
      'Preis fehlt': 'Preis fehlt',
      'Preise hinterlegen': 'Preise hinterlegen',
      'Modellpreise': 'Modellpreise',
      'Preise je 1 Mio. Tokens; Rangfolge: Projekt > global > Katalog.':
        'Preise je 1 Mio. Tokens; Rangfolge: Projekt > global > Katalog.',
      'Projekt für Preise wählen': 'Projekt für Preise wählen',
      'Anzeige in {{currency}}; gespeichert wird EUR je 1 Mio. Tokens (Kurs {{rate}}).':
        'Anzeige in {{currency}}; gespeichert wird EUR je 1 Mio. Tokens (Kurs {{rate}}).',
      'Keine Modelle mit bekannten Preisen.': 'Keine Modelle mit bekannten Preisen.',
      'Preis ist ungültig.': 'Preis ist ungültig.',
      'Preise gespeichert': 'Preise gespeichert',
      'Run-Register': 'Run-Register',
      'Läufe durchsuchen': 'Läufe durchsuchen',
      'Zustand filtern': 'Zustand filtern',
      'Alle Zustände': 'Alle Zustände',
      'Verwaiste beenden': 'Verwaiste beenden',
      'Abgeschlossene entfernen ({{n}})': 'Abgeschlossene entfernen ({{n}})',
      '{{n}} entfernt': '{{n}} entfernt',
      'Lauf': 'Lauf',
      'Dauer': 'Dauer',
      'bereinigbar': 'bereinigbar',
      'startet': 'startet',
      'läuft': 'läuft',
      'abgeschlossen': 'abgeschlossen',
      'gestoppt': 'gestoppt',
      'pausiert': 'pausiert',
      'fehlgeschlagen': 'fehlgeschlagen',
      'abgebrochen': 'abgebrochen',
      'unbekannt': 'unbekannt',
      'Keine Läufe im Register.': 'Keine Läufe im Register.',
      'FEHL': 'FEHL',
      'OK': 'OK',
      'Hinweis': 'Hinweis',
      'Keine Prüfungen vorhanden.': 'Keine Prüfungen vorhanden.',
      'Keine Pfade vorhanden.': 'Keine Pfade vorhanden.',
      'Auswahl': 'Auswahl',
      'Installiert': 'Installiert',
      'Nicht installiert': 'Nicht installiert'
    }
  });
}
