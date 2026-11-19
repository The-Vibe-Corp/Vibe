# AP21 – Test-Agent-Bericht (unabhängige Abnahme i18n/Englisch)

- **Arbeitspaket:** AP21 „Englische Sprache“ (`TICKETS.md`): komplette
  Übersetzung auf Englisch, i18n-Infrastruktur für weitere Sprachen,
  Sprachumschalter in den Einstellungen, Standard Englisch.
- **Worktree (Soll):** `/home/vibe/vibe-logs/worktrees/vibe-AP21-u2YWyJ`
- **Branch:** `feature/m0p/ap21`, Basis `d227f19` (AP20-Stand)
- **Rolle:** unabhängiger Test-Agent (TDD-Rotphase; keine Produktivänderung)
- **Datum:** 2026-11-19
- **Status:** Testsuite fertig und rot gegen den unveränderten Stand
  (Browser 12/12 FAIL, Unit 8/8 FAIL). **Abgabe blockiert durch
  Read-only-Mount des Worktrees** – Abhilfe siehe Abschnitt 1 und 11.

## 1. Blocker: Worktree ist in dieser Sandbox read-only

Der Worktree ist im Sandbox-Namespace des Test-Agenten nicht beschreibbar:

```
$ touch tests/browser/.ap21_probe
touch: cannot touch 'tests/browser/.ap21_probe': Read-only file system
$ mount | grep ' /home '
/dev/vda3 on /home type btrfs (ro,nosuid,nodev,relatime,seclabel,...)
```

Beschreibbar sind nur einzelne Bind-Mounts (`/home/vibe/VibeCode/vibe`,
`.git`, Caches, `/home/vibe/vibe-logs/questions`) sowie der Session-Temp-
Bereich `/tmp/opencode/vibe-sandbox/vibe-949edb757a/tmp/opencode`.
Der Integrationsstand `/home/vibe/VibeCode/vibe` wurde **nicht** verändert.

**Konsequenz:** Die Testdateien und dieser Bericht liegen als
übernahmefertige Kopien unter

```
/tmp/opencode/vibe-sandbox/vibe-949edb757a/tmp/opencode/ap21-deliver/
├── tests/browser/test_ap21_i18n_ui.py
├── tests/unit/test_ap21_i18n.py
└── docs/reviews/AP21-test-agent-report.md
```

Die Rotphase wurde gegen eine **byte-identische Arbeitskopie** des Worktrees
unter `/tmp/opencode/vibe-sandbox/vibe-949edb757a/tmp/opencode/ap21-run`
ausgeführt (nur die beiden Testdateien kamen hinzu). Nachweis gleicher
Produktivstand über SHA-256:

```
7582556c…  bin/web/app.js        (Worktree = Kopie)
db45ba1d…  bin/web/index.html    (Worktree = Kopie)
2530836b…  bin/vibe-web.py       (Worktree = Kopie)
HEAD = d227f19f27480bb67393bd945fb97eb9c14333e6
```

Übernahmebefehle in den Worktree: Abschnitt 11.

## 2. Auftrag und Abgrenzung

Angelegt wurden ausschließlich:

1. `tests/browser/test_ap21_i18n_ui.py` – 12 Browser-Testfälle.
2. `tests/unit/test_ap21_i18n.py` – 8 Unit-Testfälle zur reinen
   i18n-Logik (`bin/web/i18n.js` über eine Node-`vm`, ohne Browser).
3. `docs/reviews/AP21-test-agent-report.md` – dieser Bericht.

Nicht verändert: Produktivdateien (`bin/**`), `index.html`, `app.js`,
`styles.css`, `TICKETS.md`, `SPEC.md`, `docs/baseline.md`, andere
Worktrees. Kein Branchwechsel, kein Commit, kein Push, kein Merge, kein
Stage.

Die Fälle sind aus Ticket/SPEC und dem vom Koordinator vorgegebenen
UI-Vertrag abgeleitet – **nicht** aus einer Implementierung (es gibt noch
keine). Jeder Fall dokumentiert Vorbedingung, Aktion, erwartetes Ergebnis
und Fehlerfall im Modul-Docstring und in der Test-Docstring.

## 3. Vertrag → Testfall-Matrix

| Vertragspunkt | Browser | Unit |
|---|---|---|
| 1 `i18n.js` vor `app.js`, `VIBE_I18N`/`I18N`, `available/current/set/t` | 7 | 1, 2 |
| 2 Standard Englisch, `<html lang="en">` | 1 | 4 |
| 3 Umschalter, Umschalten, Persistenz | 2, 4, 5, 6 | 3, 5, 6 |
| 4 englische Kernlabels (Tabs, Laufstatus, Settings-Nav, `Language`) | 1, 2, 3 | – |
| 5 `available` en/de, Live-Umschaltung, unbekannter Key, `{{var}}` | 7, 8, 9, 10 | 3, 5, 7, 8 |
| 6 AP20-Struktur bleibt (`.bv-overview`, `.bv-subs`) | 11 | – |
| 7 Zahlen/Währung nach Sprache (`en-US`/`de-DE`) | 12 | – |

## 4. Browser-Testfälle (`tests/browser/test_ap21_i18n_ui.py`)

Ablauf je Fall: echtes Dashboard (`bin/vibe-web.py`) auf eigenem Port,
isoliertes `VIBE`-Root, lokale opencode-Attrappe ohne Nachrichten
(State-Fallback), Playwright-Chromium headless, 1400×900.

| # | Testfall | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|---|
| 1 | `test_fresh_profile_defaults_to_english` | frischer Browser-Kontext (kein localStorage), laufender Lauf, 1 laufender Subagent | Projekt öffnen, Tabs/Status lesen | `lang="en"`, `current()==='en'`, Tabs exakt `Work`/`Output`/`Assistant`/`Settings`, `#runstate` = `running`, keine JS-Fehler |
| 2 | `test_settings_navigation_and_language_selector_are_english` | wie 1 | Einstellungen öffnen | Sprungknöpfe `Agents`, `Write access`, `Sandbox`, `Git & GitHub`; Bereich nennt `Language`; `select[aria-label="Language"]` mit genau `English`/`en` + `Deutsch`/`de`, Wert `en` |
| 3 | `test_run_status_shows_running_then_stopped_in_english` | laufender Lauf | `/api/run-state` antwortet erst `running:true`, dann `running:false` (im Browser hinterlegt) | `running` → `stopped` ohne Neuladen |
| 4 | `test_selecting_german_translates_visible_areas_without_reload` | Projekt + Einstellungen offen | JS-Marker setzen, `de` wählen | `lang="de"`, `current()==='de'`, Tabs nicht mehr englisch, Marker überlebt (kein Reload), keine JS-Fehler |
| 5 | `test_german_choice_survives_reload` | Deutsch gewählt | `page.reload()`, Projekt + Einstellungen erneut öffnen | `lang="de"`, Tabs deutsch, Umschalter `de`, `current()==='de'` |
| 6 | `test_switching_back_to_english_restores_english_labels` | Deutsch aktiv | `en` wählen | `lang="en"`, Tabs wieder englisch, `current()==='en'` |
| 7 | `test_i18n_api_exposes_available_current_and_t` | Seite geladen | `window.VIBE_I18N`/`I18N` inspizieren | Global + Alias vorhanden; alle vier Funktionen; `available()` Liste mit `en`,`de`; `current()==='en'` |
| 8 | `test_unknown_translation_key_returns_the_key` | Seite geladen | `t('ap21.unknown.key.4711')` | exakt der Key, kein Fehler |
| 9 | `test_set_switches_language_and_html_lang_without_reload` | Projekt offen | `set('de')`, dann `set('en')` | `current()` und `<html lang>` folgen sofort, Marker überlebt, Tabs wechseln mit |
| 10 | `test_translation_interpolates_variables` | Seite geladen | `t('ap21.test.{{name}}', {name:'Vibe'})` | Ergebnis enthält `Vibe`, kein `{{` |
| 11 | `test_ap20_output_overview_and_subagent_containers_remain` | laufender Lauf + 1 Subagent | Ausgabe öffnen | `[data-panel='ausgabe']` sichtbar, genau eine `.bv-overview` und ein `.bv-subs`, englische Oberfläche, keine JS-Fehler |
| 12 | `test_number_and_currency_formatting_follow_the_language` | Projekt offen | `set('en')`/`set('de')`, Formatierer auf `1234.5` | en: `1,234.5`; de: `1.234,5`; Währungsformatierer (falls vorhanden) mit derselben Trennerlogik |

Technische Festlegungen der Suite:

- Tabs werden **sprachunabhängig** über `[role='tab'][aria-controls='panel-…']`
  angesprochen; die Panel-Kennungen (`arbeit`, `ausgabe`, `assistent`,
  `einstellungen`) bleiben laut AP20-Vertrag stabil.
- Der Laufstatus wird an `#runstate` geprüft (Kopf des Projektdetails).
- Der Sprachumschalter wird exakt über
  `[data-panel='einstellungen'] select[aria-label='Language']` gesucht.
- Fehler werden nur dort als Seitenfehler gewertet, wo die Suite sie
  ausdrücklich prüft (`assert_clean_page`); `pageerror` und Dialoge werden
  aufgezeichnet.
- Der Laufstatus (Fall 3) wird über eine im Browser hinterlegte Antwort für
  `/api/run-state` gesteuert (Muster wie AP19). So prüft der Fall
  ausschließlich die englischen Labels `running`/`stopped` und hängt nicht
  von der tmux-/Register-Erkennung der Testumgebung ab.

## 5. Unit-Testfälle (`tests/unit/test_ap21_i18n.py`)

Die Datei `bin/web/i18n.js` wird in einer Node-`vm` mit Stubs für `window`,
`document` (inkl. `documentElement.lang`), `localStorage`, `navigator`,
`Intl` und DOM-Events geladen. Das ist reine Testinfrastruktur; die
Produktivdatei wird nur gelesen. Fehlt `node`, wird die Suite mit klarer
Begründung übersprungen (Umgebungsvoraussetzung, kein stiller Testverlust).

| # | Testfall | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|---|
| 1 | `test_module_exists_and_exposes_public_api` | – | `i18n.js` laden | Datei vorhanden; `VIBE_I18N` + Alias `I18N`; `available/current/set/t` |
| 2 | `test_index_html_loads_i18n_before_app` | `index.html` | Skriptreihenfolge | `/static/i18n.js` steht vor `/static/app.js` |
| 3 | `test_available_languages_include_english_and_german` | Modul geladen | `available()` | Liste mit `en`, `de`; `en` zuerst |
| 4 | `test_fresh_profile_defaults_to_english` | leerer Speicher, `navigator.language='de-DE'` | `current()` | `'en'` (Standard Englisch schlägt Browsersprache) |
| 5 | `test_set_updates_current_and_html_lang` | Englisch aktiv | `set('de')`, `set('en')` | `current()` und `<html lang>` folgen sofort, kein Fehler |
| 6 | `test_set_persists_choice_for_next_page_load` | `set('de')` ausgeführt | Modul mit demselben Speicher neu laden | Speicher enthält `de`; `current()==='de'` |
| 7 | `test_unknown_key_returns_key` | Modul geladen | `t('ap21.unknown.key.4711')` | exakt der Key |
| 8 | `test_translation_interpolates_variables` | Modul geladen | `t('ap21.test.{{name}}', {name:'Vibe'})` | enthält `Vibe`, kein `{{` |

## 6. Rotphase (echte Läufe, unveränderter Stand)

Ausgeführt im byte-identischen Arbeitskopie-Verzeichnis (Abschnitt 1).
Rohausgaben: `/tmp/opencode/vibe-sandbox/vibe-949edb757a/tmp/opencode/ap21-red-unit.log`
und `…/ap21-red-browser.log`.

### 6.1 Unit

```
$ cd /tmp/opencode/vibe-sandbox/vibe-949edb757a/tmp/opencode/ap21-run
$ PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.unit.test_ap21_i18n -v
…
Ran 8 tests in 0.114s

FAILED (failures=8)
```

Auszug der Fehlergründe (jeweils Ursache, nicht Infrastruktur):

```
AssertionError: False is not true : bin/web/i18n.js fehlt
  (die i18n-Infrastruktur ist nicht angelegt)

AssertionError: -1 == -1 : index.html lädt /static/i18n.js nicht

AssertionError: None is not an instance of <class 'list'> :
  available() liefert keine Liste: None
```

### 6.2 Browser

```
$ PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.browser.test_ap21_i18n_ui -v
…
Ran 12 tests in 102.717s

FAILED (failures=12)
```

Auszüge, die die heutigen Produktbefunde belegen:

```
# Fall 1 – Standardsprache
AssertionError: 'en' != 'de' : <html lang> ist 'de', erwartet 'en'

# Fall 3 – Laufstatus
AssertionError: Der laufende Lauf zeigt nicht 'running', sondern 'läuft'

# Fall 2 – Einstellungen
AssertionError: 'Language' not found in
  'Agenten\n…\nSchreibrechte\nStandardliste\nSandbox\naus\nGit & GitHub\naus\n…'

# Fälle 4–6 – Sprachumschalter
AssertionError: 1 != 0 : Der Sprachumschalter select[aria-label='Language']
  fehlt in den Einstellungen

# Fälle 7–10 – i18n-API
AssertionError: window.VIBE_I18N (Alias I18N) ist nicht mit
  available/current/set/t verfügbar:
  {'present': False, 'aliasPresent': False, 'functions': [], …}

# Fall 11 – AP20-Struktur intakt, nur Sprache falsch
AssertionError: 'en' != 'de' : <html lang> ist 'de', erwartet 'en'
  (die Prüfungen auf .bv-overview und .bv-subs davor waren erfolgreich)

# Fall 12 – Formatierung fest auf de-DE
AssertionError: 'en' != None : … {'current': None, 'hasNumber': True,
  'hasCurrency': True, 'number': '1.234,5', 'currency': '1.234,5000 €'}
```

Damit ist die Rotphase belegt: Jeder Fall scheitert an seinem eigenen
Vertragspunkt; Fall 11 zeigt zusätzlich, dass der AP20-Ausgabebereich messtechnisch erreichbar ist und nur die Sprache fehlt.

## 7. Interpretationen und bewusste Annahmen

Diese Punkte sind im Vertrag nicht bis ins letzte Detail festgelegt; die
Suite legt sie fest, damit Entwicklung und Abnahme dasselbe prüfen:

1. **`<html lang>`** wird als Attribut auf `document.documentElement`
   geprüft; der Wert muss exakt `en` bzw. `de` sein.
2. **`set()` stellt die Oberfläche live um** (kein Reload): Ein
   JS-Marker (`window.__ap21Marker`) überlebt den Wechsel. Das folgt aus
   Vertragspunkt 5 („schaltet um, ohne dass die Seite neu geladen werden
   muss“).
3. **Interpolation auch beim Fallback-Key:** `t('…{{name}}', {name:'Vibe'})`
   muss `Vibe` einsetzen. Ein Key ohne Katalogeintrag wird also erst
   interpoliert und dann unverändert zurückgegeben. Wer das anders löst,
   muss den Fall bewusst anpassen.
4. **Standard Englisch schlägt Browsersprache:** Die Unit-Probe meldet
   `navigator.language='de-DE'`; `current()` muss trotzdem `en` sein
   (Ticket: „standard englisch“).
5. **Formatierer:** Geprüft werden `I18N.formatNumber`/`formatCurrency`
   oder – als Rückfall – die bestehenden globalen `fmtN`/`fmtEUR`
   (`Decimal`/`currency`-Namen sind bewusst nicht erfunden). Erwartet wird
   `1,234.5` (en-US) bzw. `1.234,5` (de-DE).
6. **`aria-label="Language"`** bleibt sprachunabhängig stabil (der Vertrag
   nennt genau diesen Selektor); der sichtbare Abschnittstitel ist
   `Language`.
7. **Tabs** werden über `aria-controls='panel-…'` gefunden, nicht über
   ihren Text; die Panel-Kennungen bleiben (AP20-Vertrag).
8. **`available()`** liefert mindestens `['en','de']`, Englisch zuerst;
   weitere Sprachen sind ausdrücklich erlaubt.
9. **Laufstatus** wird an `#runstate` geprüft; die Antwort von
   `/api/run-state` wird im Test hinterlegt (erst `running: true`, dann
   `false`), damit nur das Label und seine Live-Aktualisierung bewertet
   werden.

## 8. Hinweise für die Implementierung (außerhalb des Testauftrags)

- Statische Dateien sind in `bin/vibe-web.py` über `STATIC_FILES`
  freigegeben. `/static/i18n.js` muss dort ergänzt werden, sonst lädt der
  Browser die Datei nicht (die Suite prüft das indirekt über
  `window.VIBE_I18N`).
- `bin/web/index.html` trägt derzeit `lang="de"`; für Fall 1 muss der
  Startwert `en` sein oder vor dem ersten Rendern gesetzt werden.
- `set()` muss die aktive Oberfläche neu rendern/aktualisieren, nicht nur
  speichern (Fälle 4 und 9).
- `fmtN`/`fmtEUR` sind heute hart auf `'de-DE'`; für Fall 12 muss die
  Locale aus der aktiven Sprache kommen.

## 9. Auswirkungen auf bestehende Suiten (nicht Teil dieser Suite)

Die AP21-Übersetzung macht bestehende Browser-Tests rot, die deutsche
Literale prüfen. Das ist kein Fehler dieser Suite, sondern Folge des
Tickets; die betroffenen Erwartungen müssen im AP21-Paket mit angepasst
werden. Gefunden beim Querlesen:

- `tests/browser/test_ap20_output_overview_ui.py`: Tabs „Ausgabe“, „Ziel“,
  „Zusatzanweisung“, „Fortsetzen“, „Aktive Agenten“, „fokussieren“,
  „vergrößern/verkleinern“.
- `tests/browser/test_ap7_settings_ui.py`: „Arbeit“, „Einstellungen“,
  „Agenten“, „Schreibrechte“.
- `tests/browser/test_project_detail_ui.py`, `test_ap19_sessions_ui.py`
  und weitere: deutsche Tab-/Kartenlabels.

Empfehlung: strukturelle Selektoren (`data-panel`, `aria-controls`,
`data-*`) beibehalten und Textprüfungen auf die englischen Labels
umstellen; der AP20-Vertrag bleibt strukturell gültig (Fall 11).

## 10. Validierung und Abgrenzung

- `python3 -m py_compile` für beide Testdateien: OK.
- Testumfang: 12 Browser-Testmethoden, 8 Unit-Testmethoden.
- Beide Suiten vollständig ausgeführt (Abschnitt 6); keine erfundenen
  Ausgaben, keine übersprungenen Fälle (Node ist vorhanden).
- Keine Produktivdatei angelegt/geändert/gelöscht, kein Commit, kein
  Branchwechsel.
- Die Tests laufen ausschließlich gegen temporäre `VIBE`-Roots und freie
  Ports; keine echten Modellaufrufe, keine produktive Installation.

## 11. Übernahme in den Worktree

Sobald der Worktree beschreibbar ist (Host/Koordinator), genügen:

```bash
SRC=/tmp/opencode/vibe-sandbox/vibe-949edb757a/tmp/opencode/ap21-deliver
DEST=/home/vibe/vibe-logs/worktrees/vibe-AP21-u2YWyJ
install -D -m 0644 "$SRC/tests/browser/test_ap21_i18n_ui.py" \
  "$DEST/tests/browser/test_ap21_i18n_ui.py"
install -D -m 0644 "$SRC/tests/unit/test_ap21_i18n.py" \
  "$DEST/tests/unit/test_ap21_i18n.py"
install -D -m 0644 "$SRC/docs/reviews/AP21-test-agent-report.md" \
  "$DEST/docs/reviews/AP21-test-agent-report.md"
```

Danach im Worktree:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.unit.test_ap21_i18n -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.browser.test_ap21_i18n_ui -v
```

Erwartung nach der AP21-Implementierung: 8/8 und 12/12 grün. Der aktuelle
Rotstand ist in Abschnitt 6 belegt.

## 12. Nachtrag: Nachbesserung H2 (sprachunabhängige Altsuiten, M1/M2)

### 12.1 Ziel und Abgrenzung

Die AP21-Übersetzung stellt die Standardsprache auf `en`. Zahlreiche
Browsersuiten prüften jedoch deutsche Literale und wurden dadurch rot,
obwohl die Fachlichkeit unverändert war. Dieser Nachtrag macht die
betroffenen Suiten sprachunabhängig, ohne Prüftiefe zu reduzieren:
Assertions wurden weder entfernt noch abgeschwächt. Wo der Text das
Prüfziel ist, akzeptieren sie jetzt Deutsch **oder** Englisch; wo ein
stabiler Struktur-Anker existiert, wird dieser bevorzugt.

Geändert wurden ausschließlich Testdateien und dieser Bericht. Kein
Produktivcode, kein Stage, kein Commit.

### 12.2 Neue Fälle M1 und M2

`tests/browser/test_ap21_i18n_ui.py`, Klasse `ComposedAndProtocolTest`:

- **M1 `test_composed_message_switches_language_consistently`**
  Eine aus mehreren Teilen zusammengesetzte Meldung (Hinweisbox mit
  `PACKAGE_ORDER=XX9`) darf nach dem Sprachwechsel nicht gemischtsprachig
  bleiben. Erwartung: Nach `I18N.set('de')` bzw. `set('en')` enthält der
  sichtbare Text keine übersetzbaren deutschen Reste in der englischen
  Fassung (und umgekehrt); die Meldung wird als Ganzes neu gerendert.
- **M2 `test_protocol_and_user_data_stay_untranslated`**
  Protokolltext und Nutzerdaten sind reine Textknoten und dürfen nicht
  übersetzt werden. Erwartung: Ein Protokolltext mit „Fehler“ und
  „Standard“ bleibt vor und nach `I18N.set()` byte-identisch; nur
  UI-Labels wechseln.

Beide Fälle laufen im Pflichtlauf `tests.browser.test_ap21_i18n_ui` mit.

### 12.3 Umstellung der Altsuiten (Auszug)

Systematischer Scan über `tests/browser/`; rund 40 Suiten angepasst.
Beispiele für das Muster „alter Selektor → neuer Selektor“:

| Suite | alt | neu |
|---|---|---|
| `test_ap20_output_overview_ui.py` | `get_by_role("tab", name="Ausgabe")` | `[role='tab'][aria-controls='panel-ausgabe']` |
| `test_ap7_settings_ui.py` | `get_by_role("tab", name="Einstellungen")` | `[role='tab'][aria-controls='panel-einstellungen']` |
| `test_ap20_output_overview_ui.py` | `aria-label*='fokussieren'` | `button[data-focus-session]` |
| `test_ap13_security_ui.py` | `name=re.compile("anmelden")` | `anmelden|sign in|log in` |
| `test_ap13_security_ui.py` | `assertIn("(leer = unverändert)")` | `assertRegex(r"(leer = unverändert)\|\(empty = unchanged\)")` |
| `test_fritz_ui.py` | `assertIn("standardmäßig aus")` | `assertRegex(r"standardmäßig aus\|off by default")` |
| `test_sandbox_ui.py` | `assertIn("Schreibwerkzeug (edit) …")` | `assertRegex(r"Schreibwerkzeug …\|the write tool …")` |
| `test_project_guide_ui.py` | `assertIn("gefüllt")` | `assertRegex(r"gefüllt\|filled")` |
| `test_f32_subagent_self_spawn_ui.py` | `select_option(label="ausgewählt")` | `select_option(value="ausgewählt")` |
| `test_write_dirs_ui.py` | `name="Standard wiederherstellen"` | `name="Restore defaults"` |

Grundsätze:

- Struktur-Anker (`data-panel`, `aria-controls`, `data-*`, `id`,
  `data-model-row`, `data-step`) haben Vorrang vor Text.
- Gemischtsprachige Backend-Meldungen (z. B. „Läuft bereits …“,
  „Kennwort gesetzt“, „Branch … übertragen“) werden per
  `DE|EN`-Regex geprüft, nicht gestrichen.
- Negative Prüfungen wurden von `assertNotIn` auf `assertNotRegex`
  umgestellt, damit die Negation erhalten bleibt.
- Fachliche Fixture-Daten (z. B. Katalogstatus `unbekannt`, `[x]`-Marker)
  bleiben deutsch; sie sind Daten, keine UI-Texte.

### 12.4 Testisolation und Fixture-Korrekturen

- `VIBE_RUNTIME` auf einen Temp-Ordner gesetzt, wo die persönliche
  Konfiguration sonst `/home/vibe/vibe-logs` (im Sandbox-Lauf
  schreibgeschützt) gewählt hätte.
- `VIBE_STATE` (und bei `test_rebuild_project_ui.py` zusätzlich
  `VIBE_INSTALL`) isoliert, damit `vibe.json` keine fremden
  Entwicklungsordner einbringt. Ohne das matchte z. B.
  `tr.row, has_text="proj"` das Projekt „Website“ (Commit-Text enthielt
  „project …“) und öffnete das falsche Projekt.
- `test_f27_keep_changes_ui.py`: Fake-`tmux` entfernt führende
  `-L <socket>`-Argumente, bevor das Unterkommando erkannt wird.
- `test_fritz_ui.py`: `wait_for(timeout=30)` bedeutete 30 ms; auf
  `30000` korrigiert (keine Assertion-Änderung).
- `test_costs_ui.py` / `test_costs_refresh_ui.py`: vor dem Klick auf
  „Costs“ wird der Navigationsknopf abgewartet (Stabilität im
  Gesamtlauf, keine Abschwächung).

### 12.5 Reale Läufe (keine erfundenen Ergebnisse)

Umgebung: `PLAYWRIGHT_BROWSERS_PATH=/home/vibe/.cache/ms-playwright`
(nötig, weil `XDG_CACHE_HOME` im Sandbox-Lauf auf ein leeres Cache zeigt).

Pflichtlauf 1 (fünf Altsuiten):

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.browser.test_ap7_settings_ui tests.browser.test_ap11_priority_ui \
  tests.browser.test_ap20_output_overview_ui \
  tests.browser.test_ap06_github_ui tests.browser.test_ap03_agents_ui -v
```

Ergebnis: **Ran 45 tests in 76.121s — OK** (`/tmp/opencode/ap21-final-five.log`).

Pflichtlauf 2 (AP21 inkl. M1/M2 und Unit):

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.browser.test_ap21_i18n_ui tests.unit.test_ap21_i18n -v
```

Ergebnis: **Ran 22 tests in 21.579s — OK**
(`/tmp/opencode/ap21-final-i18n.log`).

Gesamtlauf der übrigen angepassten Suiten (ohne `ap8`, `rebuild` und
`ap21`, die separat laufen):

- **Ran 182 tests in 326.364s — 181 OK, 1 Fehler**
  (`/tmp/opencode/ap21-final-all.log`).
- Der eine Fehler war `test_costs_refresh_ui` (Navigation `#costs`
  nicht rechtzeitig sichtbar) und trat im Gesamtlauf als Timing-Flake
  auf. Nach der Stabilisierung des Navigations-Wartens liefen
  `test_costs_ui` + `test_costs_refresh_ui` isoliert:
  **Ran 7 tests in 15.624s — OK**.
- Alle übrigen Suiten des Gesamtlaufs waren grün, darunter
  `test_ap13_security_ui`, `test_ap06_github_ui`, `test_f20_harness_ui`,
  `test_f27_keep_changes_ui`, `test_fritz_ui`, `test_feedback_ui`,
  `test_feedback_completed_ui`, `test_project_guide_ui`,
  `test_models_ui`, `test_f32_subagent_self_spawn_ui`,
  `test_b11_output_ui`, `test_b14_subagent_output_ui`,
  `test_f30_subagent_view_ui`, `test_project_detail_ui`.

### 12.6 Offene Punkte / Blocker

- **`test_ap8_checkout_ui.py` (blockiert, kein Testfehler):** Der
  unveränderte Produktivcode `bin/vibe-web.py` wirft bei `POST /api/clone`
  `NameError: name 'agent_note' is not defined`. Clone-/Checkout-Tests
  können deshalb nicht grün laufen. Der Fehler liegt außerhalb des
  Testbereichs und wurde nicht kaschiert.
- **`test_rebuild_project_ui.py` (vorbestehende Fachaweichung):** Der Test
  erwartet `rebuild-env.py --check` in der erzeugten `project.env`.
  `templates/rebuild/.vibe/project.env` (HEAD) enthält diesen Eintrag
  nicht; auch `tests/unit/test_rebuild_profile.py` erwartet ihn. Das ist
  keine Sprachfrage. Die Assertion bleibt unverändert; der Test ist
  deshalb rot und als vorbestehender Template-/Profil-Mismatch gemeldet.

### 12.7 Geänderte Dateien

- `tests/browser/`: 39 Suiten (u. a. `test_ap7_settings_ui.py`,
  `test_ap11_priority_ui.py`, `test_ap20_output_overview_ui.py`,
  `test_ap06_github_ui.py`, `test_ap03_agents_ui.py`,
  `test_ap13_security_ui.py`, `test_feedback_ui.py`,
  `test_feedback_completed_ui.py`, `test_project_guide_ui.py`,
  `test_models_ui.py`, `test_f32_subagent_self_spawn_ui.py`,
  `test_fritz_ui.py`, `test_write_dirs_ui.py`, `test_sandbox_ui.py`,
  `test_costs_ui.py`, `test_costs_refresh_ui.py`).
- `tests/browser/test_ap21_i18n_ui.py`: M1/M2 ergänzt.
- `tests/unit/test_ap21_i18n.py`: unverändert grün.
- `docs/reviews/AP21-test-agent-report.md`: dieser Nachtrag.

## 13. Nachtrag: Review-Runde 2 (ein zusätzlicher Browserfall)

### 13.1 Ziel und Abgrenzung

Der Reviewer forderte einen weiteren Browserfall für vier Oberflächen, die
im englischen Standardmodus vollständig englisch sein müssen, inklusive
dynamischer Servertexte, Toasts, Platzhalter und aria-label. Der Fall prüft
zusätzlich die deutsche Umkehrung. Geändert wurde ausschließlich
`tests/browser/test_ap21_i18n_ui.py` (plus dieser Report); Produktivcode und
andere Tests blieben unberührt.

### 13.2 Neuer Fall

`ReviewRound2Test.test_round2_english_surfaces_and_german_reversal`
(Modul-Dokumentation Punkt 15) prüft je Oberfläche Englisch und Deutsch als
eigene Subtests:

1. **Projektassistent:** exakte Titel, Fragen, Hilfen und Status für
   `ziel`/`nutzer` (EN `Product goal` / `Target group and usage`, Status
   `missing`; DE `Produktziel` / `Zielgruppe und Nutzung`, Status `fehlt`),
   ohne deutsche Reste im jeweiligen Prüfbereich.
2. **Platzhalter, Lade-Text, aria-label:** `/absolute/path` bzw.
   `/absoluter/pfad`; `Loading AGENTS.md …` wird über eine angehaltene
   `/api/agents_file`-Antwort sichtbar gemacht und danach mit einer gültigen
   Teilansicht beantwortet; AGENTS.md-Textareas und der Fokus-Knopf des
   Subagenten (`focus` bzw. `fokussieren`).
3. **Backend-Fehler-Toast:** doppeltes Schreibverzeichnis `/tmp/opencode`
   über `bt()`/`MESSAGE_MAP`; erwartet EN `already allowed`, DE
   `bereits erlaubt`, jeweils ohne Gegenstücke der anderen Sprache.
4. **Umgebungsprüfung:** dynamische Doctor-Labels `VIBE folder writable`
   bzw. `VIBE-Ordner beschreibbar` und `free space on data partition` bzw.
   `freier Platz auf Datenpartition`.

Die Kennungen und Pfade (`ziel`, `nutzer`, `/tmp/opencode`) bleiben in allen
Sprachen unverändert. Es wurden keine Assertions abgeschwächt oder entfernt;
die Prüfung erfolgt über stabile Selektoren (`data-step`, `data-panel`,
`data-focus-session`, `#settings-rechte`) und exakte Texte.

### 13.3 Reales Ergebnis

Ausgeführt wurde nur die AP21-Suite:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.browser.test_ap21_i18n_ui -v
```

Ergebnis: **Ran 15 tests in 47.136s — 14 OK, 1 Fehler**
(`/tmp/opencode/ap21-review2-final.log`).

Der einzige Fehler ist der neue englische Backend-Toast-Subtest:

```text
Der Backend-Toast ist nicht en:
['directory ist bereits allowed: /tmp/opencode\n×']
```

Ursache ist die noch unvollständige Produktivzuordnung: `bt()` ersetzt über
`MESSAGE_PHRASES` nur `Verzeichnis` → `directory` und `erlaubt` → `allowed`;
`ist bereits` bleibt deutsch, und `already allowed` entsteht nicht. Die
deutsche Umkehrung (`Verzeichnis ist bereits erlaubt: /tmp/opencode`) läuft
im selben Fall grün. Die übrigen neuen Nachweise (Projektassistent,
Platzhalter/Lade-Text/aria, Doctor, deutscher Toast) sowie alle 14
bestehenden Tests der Suite sind grün.

Der Fall bleibt bewusst rot, bis der Coding-Agent die Meldung
`Verzeichnis ist bereits erlaubt: …` auf `Directory is already allowed: …`
abbildet; die Assertion wurde nicht an den Zwischenstand angepasst.

### 13.4 Geänderte Dateien

- `tests/browser/test_ap21_i18n_ui.py`: neuer `ReviewRound2Test` und
  Modul-Dokumentation Punkt 15.
- `docs/reviews/AP21-test-agent-report.md`: dieser Nachtrag.

## 14. Nachtrag: Review-Runde 3 (Modelltabelle/-auswahl, MCP-Toast, Pill-Klassen)

### 14.1 Ziel und Abgrenzung

Der Reviewer benannte drei Restpunkte:

1. Modelltabelle und Modellauswahl müssen die Bewertungswerte
   (`sehr schnell`, `hoch`, `bedingt`, `keine Daten`, `ja`) und das Label
   `Aufwand, Daten` im englischen Standard englisch zeigen; die deutsche
   Umkehrung bleibt deutsch.
2. Der MCP-Toggle-Toast (`aktiviert`/`deaktiviert`) muss im englischen Modus
   englisch sein, deutsch unverändert.
3. Schreibrechte-Chip und MCP-Statuspille müssen trotz boxed
   `tr()`-Strings die zustandsrichtige CSS-Klasse (`bad`/`ok`) tragen.

Geändert wurden ausschließlich `tests/browser/test_ap21_i18n_ui.py` (neue
Klasse `ReviewRound3Test`, Modul-Dokumentation Punkte 16–18, Fallzahl im
Docstring) und dieser Report. Kein Produktivcode, kein Stage, kein Commit.

### 14.2 Neue Fälle (Modul-Dokumentation 16–18)

`ReviewRound3Test` ergänzt drei Browserfälle; die bestehenden Klassen bleiben
unverändert:

16. `test_models_table_and_select_are_english_and_german_reverses`
    - Fixture: `_toolchain/models.json` mit `opencode/beam-free`
      (`tempo: sehr schnell`, `aufwand: hoch`, `coder`/`reviewer: bedingt`,
      `fakten.daten: keine Daten`, `fakten.bild: ja`) sowie ein systemweiter
      Probe-Agent `ap21-modell-probe` mit Modellüberschreibung in
      `.vibe/agents.json`, damit Tabelle und Auswahl denselben Eintrag zeigen.
    - Geprüft: englische Kopfzeilen (`Model`, `Provider`, `Price`, `Speed`,
      `Effort`, `Data`, `Images`, `in use`), englische Zellwerte
      (`very fast`, `high`, `no data`, `yes`, `conditional`) und das
      Auswahllabel `effort, data`; danach deutsch die unveränderten Rohwerte
      und `Aufwand, Daten`. Zusätzlich in beiden Sprachen die Badge-Klassen
      der Tempo-Zelle (`ok`) und der Aufwand-Zelle (`bad`), weil die Klasse am
      deutschen Rohwert hängt.
    - Gegenprobe: `assertNotIn` auf alle Werte der jeweils anderen Sprache in
      Kopfzeilen, Zellen und Auswahllabel.
17. `test_mcp_toggle_toast_and_status_pill_follow_language`
    - Fixture: globale `opencode.json` im isolierten `HOME` mit dem lokalen
      Server `ap21-mcp-pruefserver` (aktiv).
    - Geprüft: Pille `yes` mit Klasse `ok`, Knopf `Turn off`, Toast
      `ap21-mcp-pruefserver deactivated`, danach Pille `no` mit `bad`;
      deutsch Pille `nein` mit `bad`, Knopf `Einschalten`, Toast
      `ap21-mcp-pruefserver aktiviert`, Pille `ja` mit `ok`.
18. `test_write_access_chip_shows_bad_class_in_both_languages`
    - Fixture: absichtlich ungültige `.vibe/permissions.json`, damit
      `/api/project` `write_dirs_error` liefert.
    - Geprüft: Chip `rechte` zeigt `Error`/`bad` (englisch) und
      `Fehler`/`bad` (deutsch) sowie den jeweiligen Navigationstext, ohne den
      Fehlertext der anderen Sprache.

Fixture-Dateien werden je Test über `addCleanup` entfernt. Die Fälle lesen
echte Zustände des Dashboards (Katalogdatei, Agentenüberschreibung, globale
MCP-Konfiguration, ungültige Rechte-Datei), keine Mock-Antworten.

### 14.3 Robustheit und Testkorrekturen (keine Assertion abgeschwächt)

- **MCP-Servername:** Der Fixture-Server heißt bewusst
  `ap21-mcp-pruefserver`, nicht `ap21-probe`. Der Produktivcode enthielt
  zwischenzeitlich testnamenspezifische Einträge (`ap21-probe aktiviert`
  usw.); der generische Pfad (`aktiviert`/`deaktiviert`) bleibt der Maßstab.
  Der Test prüft damit die allgemeine Zuordnung, nicht einen Sonderfall.
- **Reload der Modellauswahl:** Ein `goto` auf dieselbe URL mit nur anderem
  Fragment lädt die Seite nicht neu. Der Fall lädt deshalb vor dem
  Sprachwechsel-Neuladen `about:blank`.
- **Doctor-Wartebedingung (Review-Runde 2):** Beim Sprachwechsel übersetzt
  `retranslateDOM()` zuerst die statischen Beschriftungen; die dynamischen
  Doctor-Zeilen aus `/api/doctor` entstehen erst beim asynchronen
  `rerenderView()`. Der Bestandsfall las `main` im Übergangsfenster und war
  dadurch sporadisch rot (englische Doctor-Zeilen bei bereits deutschen
  statischen Labels). `assert_doctor_language` wartet jetzt auf jedes
  erwartete Label (max. 45 s), bevor es die unveränderten `assertIn`/
  `assertNotIn`-Prüfungen ausführt. Das ist eine Wartebedingung, keine
  Abschwächung: Fehlt ein Label dauerhaft, schlägt der Fall mit derselben
  Meldung fehl.
- **Doppelte Klasse entfernt:** Ein beim Einfügen versehentlich doppelt
  vorhandener `ReviewRound3Test`-Block wurde entfernt (genau eine
  Klassendefinition).

### 14.4 Reale Läufe (final, ungekürzt)

Produktstand während der Läufe (unverändert vor/nach dem Lauf, per
`stat`-Vergleich geprüft): `bin/web/app.js` 20:18:18, `bin/web/i18n.js`
20:13:44, `bin/vibe-web.py` 17:29:53, `bin/vibe` 16:51:16,
`tests/browser/test_ap21_i18n_ui.py` 20:26.

Browser-Suite:

```bash
cd /tmp/opencode/ap21-work
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.browser.test_ap21_i18n_ui -v
```

Rohausgabe (`/tmp/opencode/ap21-final2-browser.log`), vollständig:

```text
test_composed_message_switches_language_consistently (tests.browser.test_ap21_i18n_ui.ComposedAndProtocolTest.test_composed_message_switches_language_consistently)
M1: Eine zusammengesetzte Meldung wechselt vollständig die Sprache. ... ok
test_protocol_and_user_data_stay_untranslated (tests.browser.test_ap21_i18n_ui.ComposedAndProtocolTest.test_protocol_and_user_data_stay_untranslated)
M2: Protokoll-/Nutzerdaten bleiben beim Sprachwechsel wörtlich. ... ok
test_fresh_profile_defaults_to_english (tests.browser.test_ap21_i18n_ui.DefaultLanguageTest.test_fresh_profile_defaults_to_english)
VP2/VP4: Frisches Profil startet englisch, ``<html lang="en">``. ... ok
test_run_status_shows_running_then_stopped_in_english (tests.browser.test_ap21_i18n_ui.DefaultLanguageTest.test_run_status_shows_running_then_stopped_in_english)
VP4: Der Laufstatus ist englisch und aktualisiert sich live. ... ok
test_settings_navigation_and_language_selector_are_english (tests.browser.test_ap21_i18n_ui.DefaultLanguageTest.test_settings_navigation_and_language_selector_are_english)
VP3/VP4: Einstellungsnavigation und Sprachumschalter sind englisch. ... ok
test_i18n_api_exposes_available_current_and_t (tests.browser.test_ap21_i18n_ui.I18nApiTest.test_i18n_api_exposes_available_current_and_t)
VP1/VP5: ``window.VIBE_I18N`` mit Alias und Pflichtfunktionen. ... ok
test_set_switches_language_and_html_lang_without_reload (tests.browser.test_ap21_i18n_ui.I18nApiTest.test_set_switches_language_and_html_lang_without_reload)
VP5: ``set`` schaltet sofort um, ohne die Seite zu laden. ... ok
test_translation_interpolates_variables (tests.browser.test_ap21_i18n_ui.I18nApiTest.test_translation_interpolates_variables)
VP5: ``t(key, vars)`` löst ``{{var}}`` auf. ... ok
test_unknown_translation_key_returns_the_key (tests.browser.test_ap21_i18n_ui.I18nApiTest.test_unknown_translation_key_returns_the_key)
VP5: Ein unbekannter Key liefert den Key selbst (kein Crash). ... ok
test_german_choice_survives_reload (tests.browser.test_ap21_i18n_ui.LanguageSwitchTest.test_german_choice_survives_reload)
VP3: Die Sprachwahl übersteht ein Neuladen (localStorage). ... ok
test_selecting_german_translates_visible_areas_without_reload (tests.browser.test_ap21_i18n_ui.LanguageSwitchTest.test_selecting_german_translates_visible_areas_without_reload)
VP3: Deutsch im Umschalter stellt die sichtbare Oberfläche um. ... ok
test_switching_back_to_english_restores_english_labels (tests.browser.test_ap21_i18n_ui.LanguageSwitchTest.test_switching_back_to_english_restores_english_labels)
VP3: Der Rückwechsel auf Englisch stellt die englischen Labels her. ... ok
test_ap20_output_overview_and_subagent_containers_remain (tests.browser.test_ap21_i18n_ui.RegressionTest.test_ap20_output_overview_and_subagent_containers_remain)
VP6: Die AP20-Ausgabeansicht bleibt trotz Übersetzung erhalten. ... ok
test_number_and_currency_formatting_follow_the_language (tests.browser.test_ap21_i18n_ui.RegressionTest.test_number_and_currency_formatting_follow_the_language)
VP7: Zahlen/Währung richten sich nach der Sprache (en-US/de-DE). ... ok
test_round2_english_surfaces_and_german_reversal (tests.browser.test_ap21_i18n_ui.ReviewRound2Test.test_round2_english_surfaces_and_german_reversal)
Review 2: vier Oberflächen englisch, deutsche Umkehrung intakt. ... ok
test_mcp_toggle_toast_and_status_pill_follow_language (tests.browser.test_ap21_i18n_ui.ReviewRound3Test.test_mcp_toggle_toast_and_status_pill_follow_language)
Review 3: MCP-Toast und Statuspille in beiden Sprachen. ... ok
test_models_table_and_select_are_english_and_german_reverses (tests.browser.test_ap21_i18n_ui.ReviewRound3Test.test_models_table_and_select_are_english_and_german_reverses)
Review 3: Modellwerte und Labels englisch, deutsch unverändert. ... ok
test_write_access_chip_shows_bad_class_in_both_languages (tests.browser.test_ap21_i18n_ui.ReviewRound3Test.test_write_access_chip_shows_bad_class_in_both_languages)
Review 3: Fehler-Chip trägt ``bad`` trotz boxed ``tr()``-String. ... ok

----------------------------------------------------------------------
Ran 18 tests in 46.775s

OK
```

Unit-Suite:

```bash
cd /tmp/opencode/ap21-work
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.unit.test_ap21_i18n -v
```

Rohausgabe (`/tmp/opencode/ap21-final2-unit.log`), vollständig:

```text
test_available_languages_include_english_and_german (tests.unit.test_ap21_i18n.I18nModuleTest.test_available_languages_include_english_and_german)
Fall 3: available() enthält en und de, Englisch zuerst. ... ok
test_fresh_profile_defaults_to_english (tests.unit.test_ap21_i18n.I18nModuleTest.test_fresh_profile_defaults_to_english)
Fall 4: Ohne gespeicherte Wahl ist Englisch Standard. ... ok
test_index_html_loads_i18n_before_app (tests.unit.test_ap21_i18n.I18nModuleTest.test_index_html_loads_i18n_before_app)
Fall 2: index.html lädt /static/i18n.js vor /static/app.js. ... ok
test_module_exists_and_exposes_public_api (tests.unit.test_ap21_i18n.I18nModuleTest.test_module_exists_and_exposes_public_api)
Fall 1: i18n.js stellt VIBE_I18N (Alias I18N) vollständig bereit. ... ok
test_set_persists_choice_for_next_page_load (tests.unit.test_ap21_i18n.I18nModuleTest.test_set_persists_choice_for_next_page_load)
Fall 6: Die Wahl steht in localStorage und überlebt den Neuaufbau. ... ok
test_set_updates_current_and_html_lang (tests.unit.test_ap21_i18n.I18nModuleTest.test_set_updates_current_and_html_lang)
Fall 5: set('de')/set('en') stellen current() und lang sofort um. ... ok
test_translation_interpolates_variables (tests.unit.test_ap21_i18n.I18nModuleTest.test_translation_interpolates_variables)
Fall 8: t(key, vars) ersetzt {{var}}. ... ok
test_unknown_key_returns_key (tests.unit.test_ap21_i18n.I18nModuleTest.test_unknown_key_returns_key)
Fall 7: t() liefert bei unbekanntem Key den Key selbst. ... ok

----------------------------------------------------------------------
Ran 8 tests in 0.118s

OK
```

Fallzahlen: **18 Browserfälle**, **8 Unit-Fälle**, beide Suiten vollständig grün.

### 14.5 Frühere Rotphasen und ihre Auflösung

Alle während dieser Runde beobachteten Rotphasen sind behoben; keine
Assertion wurde dafür abgeschwächt:

1. **MCP-Toast blieb deutsch** (`ap21-probe deaktiviert`): Der Produktivstand
   bildete den generischen Toggle-Text noch nicht ab. Der Coding-Agent hat
   `aktiviert`/`deaktiviert` in `bt()` ergänzt; der Test prüft seitdem den
   neutralen Fixture-Namen `ap21-mcp-pruefserver`.
2. **Modellfall ERROR beim Neuladen:** `goto` auf dieselbe URL mit anderem
   Fragment lädt nicht neu; behoben durch `about:blank` vor dem Neuladen.
3. **Doppelte `ReviewRound3Test`-Klasse** nach dem Einfügen: entfernt.
4. **Doctor `de` rot im Gesamtlauf:** Ursache war das Übergangsfenster
   zwischen `retranslateDOM()` und `rerenderView()` (siehe 14.3), nicht ein
   Produktfehler. Der Bestandsfall wartet jetzt auf die dynamischen Labels;
   Einzellauf und Gesamtlauf sind grün.

### 14.6 Geänderte Dateien

- `tests/browser/test_ap21_i18n_ui.py`: `ReviewRound3Test` (3 Fälle),
  Modul-Dokumentation 16–18, Fallzahl 18, Wartebedingung in
  `assert_doctor_language`.
- `docs/reviews/AP21-test-agent-report.md`: dieser Nachtrag.

Beide Dateien sind im Arbeitsbaum ungetrackt (`??`); Stage/Commit/Push
erfolgen durch den Koordinator. Andere ungetrackte/geänderte Dateien im
Worktree stammen nicht aus diesem Testauftrag.

### 14.7 Abgrenzung

Die Läufe belegen den oben genannten Produktstand. Andere Agenten haben im
selben Worktree parallel Product-Code und Suiten verändert; bei einem
abweichenden Stand sind die Läufe zu wiederholen. Nicht Teil dieses Auftrags
und weiterhin außerhalb des Testbereichs: `test_ap8_checkout_ui.py`
(`NameError: agent_note`) und `test_rebuild_project_ui.py`
(Template-/Profil-Mismatch).

---

## 15. AP21 v2 — Rotphase der globalen Sprache (Implementierungs-Agent)

- **Datum:** 2026-11-19
- **Ausgangslage:** Der lose Test-Agent-Loop war wegen Provider-Limit nicht
  verfügbar. Die neuen Abnahmetests für AP21 v2 wurden daher vom
  Implementierungs-Agenten geschrieben. Abschnitt 1–14 dokumentieren die
  ursprüngliche v1-Abnahme; dieser Abschnitt hält die **v2-Rotphase** fest,
  bevor die Produktionsänderungen umgesetzt wurden (red–green–refactor).

### 15.1 Neue/erweiterte Tests (aus dem Vertrag abgeleitet)

`tests/unit/test_ap21_i18n.py` — neue Klassen:

- `I18nMetaPriorityTest` (6 Fälle): Meta `vibe-language` > localStorage > `en`,
  vollständige Validierung (ungültiges Meta wird ignoriert).
- `UiConfigLanguageTest` (6 Fälle): `LANGUAGES`, `DEFAULT_LANGUAGE`,
  `validate_language()`, `validate()` mit/ohne `language`.
- `GlobalLanguageServerTest` (10 Fälle): echter `vibe-web`-Prozess mit
  isoliertem `VIBE_*`-Root; `GET/POST /api/language` (Payload, Auth 403,
  400 `invalid_language` ohne Dateiänderung, Erhalt anderer ui.json-Felder,
  andere Projekte unberührt), HTML-Injektion von `<html lang>` und
  `<meta name="vibe-language">`, ui.json-Roundtrip.

`tests/browser/test_ap21_i18n_ui.py`: globaler Sprachumschalter
(`[data-t='settings'] select[aria-label='Language']`), kein Select mehr im
Projekt-Tab, EN→DE in Nav/Projektliste/vier Projekt-Tabs, Reload, ui.json,
Toast+Rückfall bei POST-Fehler.

### 15.2 Redphase — tatsächlich ausgeführter Befehl

```
$ PLAYWRIGHT_BROWSERS_PATH=/home/vibe/.cache/ms-playwright \
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
    tests.unit.test_ap21_i18n.I18nMetaPriorityTest \
    tests.unit.test_ap21_i18n.UiConfigLanguageTest \
    tests.unit.test_ap21_i18n.GlobalLanguageServerTest -v
...
Ran 21 tests in 1.621s
FAILED (failures=12, errors=10)
```

Beobachtete, erwartete Fehlerbilder (Auszug):

- `test_meta_language_wins_over_localstorage` /
  `test_meta_language_en_overrides_localstorage_de`: `current()` blieb beim
  localStorage-Wert, weil `i18n.js` das Meta-Feld noch nicht las.
- `UiConfigLanguageTest.*`: `AttributeError: module 'vibe_ui_config' has no
  attribute 'LANGUAGES'` bzw. `validate_language` fehlt; `validate()` liess
  `language` noch als unbekanntes Feld fallen.
- `GlobalLanguageServerTest.setUp`: `POST /api/language` lieferte
  `404 {"error":{"code":"not_found"}}` — der Endpunkt existierte noch nicht.
- `test_page_injects_default_language`: `index.html` enthielt noch kein
  `<meta name="vibe-language">`.

Damit ist die Rotphase für jede geforderte v2-Verhaltensweise nachgewiesen:
die Tests scheitern am jeweils fehlenden Produktionsverhalten, nicht an einer
defekten Testumgebung.

### 15.3 Grünphase

Nach den Änderungen A–F (siehe `docs/features/AP21.md`) wurden dieselben
Suiten erneut ausgeführt: `tests.unit.test_ap21_i18n` → **29 Tests, OK**.
Die Browser-Suite und die weiteren Prüfungen sind im Abschnitt
„Verifikation“ von `docs/features/AP21.md` dokumentiert.
