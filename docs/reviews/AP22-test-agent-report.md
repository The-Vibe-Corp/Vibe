# AP22 — Testagent: Testfälle und Rotphase

- **Arbeitspaket:** AP22 „New vibe UI“ (`docs/features/AP22.md`, Vertrag vom
  2026-11-20)
- **Branch:** `feature/m0p/ap22` (Basis `f49940d`)
- **Rolle:** unabhängiger Testagent — nur Tests und dieser Bericht; keine
  Implementierung, keine Commits, keine Änderung an `bin/`, `scripts/`,
  `docs/features/AP22.md` oder `TICKETS.md`.

## Neu angelegte Testdateien

| Datei | Zeilen | Fälle | Prüft |
| --- | --- | --- | --- |
| `tests/unit/test_ap22_web_routes.py` | 754 | 19 | Server-Vertrag: `/`, `/classic`, Statik, `limits`, `gates`, `runs`, `emu`, `paths` |
| `tests/browser/test_ap22_shell_ui.py` | 663 | 12 | Shell-Boot, Anmeldung, Navigation, Theme, Animationen, Sprache, Responsive, Glocke, `/classic`, Router |
| `tests/browser/test_ap22_home_ui.py` | 515 | 6 | Projektkarten, Einstiegshinweis, Neuanlage, Klonen (Feature), Ordner |
| `tests/browser/test_ap22_settings_ui.py` | 670 | 10 | Sektionen, Theme/Animation/Sprache, Kennwort/Port, Feature-Schalter, Limits/Gates, Klassik-Link, Abmelden |

Alle Fälle sind deterministisch und isoliert: temporäre Verzeichnisse, freie
Loopback-Ports, keine echten Projekte, keine Modellaufrufe, Aufräumen in
`tearDownClass`. Browserfälle laufen mit Chromium headless aus dem
Nur-Lese-Cache (`PLAYWRIGHT_BROWSERS_PATH`, ersatzweise
`~/.cache/ms-playwright`).

## Rotphase (Stand ohne Implementierung)

Alle Läufe erfolgten am Basisstand (`f49940d`, ohne AP22-Implementierung).
Die Fehler sind erwartete Rotphase: fehlende `/classic`-Route, fehlende
`data-nv-*`-Hooks, 404 auf den neuen Endpunkten — **keine Harness-Fehler**
(Server startet, Token wird gelesen, Browser startet, HTTP-Antworten kommen
an).

### `tests/unit/test_ap22_web_routes.py`

Befehl: `python3 -m unittest tests.unit.test_ap22_web_routes -v`

```
Ran 19 tests in 4.146s
FAILED (failures=17)
```

17 Fehlschläge, 0 Fehler. Zwei Fälle bestehen bereits am Basisstand, weil sie
Bestandsschutz prüfen und nach der Implementierung weiterhin gelten müssen:
`test_unknown_path_stays_not_found` (404 für unbekannte Pfade mit Token) und
`test_both_pages_keep_the_host_guard` (Host-Guard 403). Alle übrigen Fälle
scheitern an der fehlenden Implementierung.

Repräsentativer Fehler (fehlende `/classic`-Route):

```
FAIL: test_classic_serves_the_old_shell_without_auth (tests.unit.test_ap22_web_routes.ShellRoutingTest.test_classic_serves_the_old_shell_without_auth)
AssertionError: 200 != 403 : {"ok": false, "error": {"code": "unauthorized", "message": "Token fehlt oder falsch"}, "message": "Token fehlt oder falsch"}
```

Zweiter repräsentativer Fehler (fehlende neue Shell):

```
FAIL: test_root_serves_the_new_shell_without_auth (...)
AssertionError: 'data-nv-app' not found in '<!doctype html>…<nav id="nav">…'
```

Einordnung: `/classic` ist unbekannt und fällt in die Tokenpflicht (403);
`/` liefert weiterhin die alte `index.html` ohne `data-nv-app`; die neuen
Endpunkte antworten mit 404, die neuen Statikdateien fehlen
(`/static/nova.css` → 404).

### `tests/browser/test_ap22_shell_ui.py`

Befehl: `python3 -m unittest tests.browser.test_ap22_shell_ui -v`

```
Ran 12 tests in 304.039s
FAILED (errors=12)
```

12 Fehler (Playwright-Timeout), 0 Fehlschläge. Repräsentativ:

```
playwright._impl._errors.TimeoutError: Locator.wait_for: Timeout 25000ms exceeded.
Call log:
  - waiting for locator("main#nv-main[data-nv-view='home']") to be visible
```

Einordnung: Die neue Shell existiert noch nicht; `boot()` findet
`main#nv-main[data-nv-view="home"]` nicht. Auch die Login-Karte
(`[data-nv-login]`) und die alte UI unter `/classic` (403 statt Seite) fehlen,
deshalb Timeout in allen Fällen. Kein Harness-Fehler: Dashboard und Browser
starten, die Token-Datei wird gelesen.

### `tests/browser/test_ap22_home_ui.py`

Befehl: `python3 -m unittest tests.browser.test_ap22_home_ui -v`

```
Ran 6 tests in 152.100s
FAILED (errors=6)
```

6 Fehler (Playwright-Timeout), 0 Fehlschläge. Repräsentativ derselbe
Boot-Timeout auf `main#nv-main[data-nv-view='home']`.

Einordnung: Ohne neue Shell gibt es keine Projektkarten
(`article[data-nv-project]`), keine Einstiegshinweise, kein Typ-Select und
keine Clone-/Ordnerkarten. Der Fixture selbst ist geprüft: zwei Projekte mit
`.vibe/project.env`, Vorlagen `generic`/`web` für `GET /api/types` und
`POST /api/new` sind vorhanden (sonst würde der Lauf schon in
`setUpClass` scheitern).

### `tests/browser/test_ap22_settings_ui.py`

Befehl: `python3 -m unittest tests.browser.test_ap22_settings_ui -v`

```
Ran 10 tests in 254.225s
FAILED (errors=10)
```

10 Fehler (Playwright-Timeout), 0 Fehlschläge. Repräsentativ derselbe
Boot-Timeout auf `main#nv-main[data-nv-view='home']`.

Einordnung: Die Einstellungsseite und ihre Sektionen/Hooks existieren nicht.
`setUp` (Sprache `en`, Kennwort löschen über die Bestands-API) läuft
fehlerfrei — der Server ist also erreichbar.

### Bestands-Browsertest als Rotnachweis der Umstellung

Befehl: `PLAYWRIGHT_BROWSERS_PATH=/home/nutzer/.cache/ms-playwright python3 -m unittest tests.browser.test_tickets_ui -v`

```
Ran 3 tests in 91.417s
FAILED (errors=3)
…
playwright._impl._errors.TimeoutError: Locator.wait_for: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("tr.row").filter(has_text="proj").first to be visible
```

Einordnung: Der Test navigiert jetzt korrekt nach `/classic`; am Basisstand
ist die Route unbekannt (403 `unauthorized`), daher erscheint die alte
Projektliste nicht. Das ist die **beabsichtigte Rotphase** der mechanischen
Umstellung und verschwindet mit der `/classic`-Route. Hinweis: Ohne
`PLAYWRIGHT_BROWSERS_PATH` scheitert der Lauf an der Browser-Suche, weil in
dieser Umgebung `XDG_CACHE_HOME` auf ein leeres Verzeichnis zeigt — reine
Umgebungsfrage, kein Testfehler.

## Mechanische Umstellung der Bestands-Browsertests (alt → `/classic`)

- 42 Dateien in `tests/browser/` angepasst, 60 Navigationsziele
  `"/#t="` → `"/classic#t="` (jeweils `goto`-Aufrufe).
- `tests/browser/test_ap13_security_ui.py`: zusätzlich die beiden
  Login-Karten-Aufrufe `goto(self.base + "/")` → `goto(self.base + "/classic")`.
- Sonst keine Änderungen; die Dateien prüfen weiterhin die alte UI, nun unter
  `/classic`.
- Syntaxprüfung: `python3 -m py_compile tests/browser/*.py` (alle Dateien
  kompilieren).

## Unit-Test-Umstellungen (alt → classic)

1. `tests/unit/web_page.py` — `served_page()` ruft jetzt `GET /classic` ab
   (Assets `/static/styles.css` + `/static/app.js` unverändert); Docstring um
   einen Satz ergänzt, dass die alte Oberfläche seit AP22 unter `/classic`
   liegt. Die nutzenden Tests (`test_feedback_capture`,
   `test_feedback_completed`, `test_feedback_edit_delete`,
   `test_project_guide`, `test_project_write_dirs`, `test_questions`,
   `test_work_packages`) bleiben unverändert.
2. `tests/unit/test_ap21_i18n.py` — `INDEX_HTML` → `CLASSIC_HTML`
   (`bin/web/classic.html`); Fall 2 heißt jetzt
   `test_classic_html_loads_i18n_before_app` (Docstring angepasst);
   Datei-Docstring nennt `classic.html`. Die Seiten-Tests zu
   `__VIBE_LANG__`/`vibe-language` bleiben auf `GET /` (die neue Shell
   ersetzt dieselben Platzhalter) und wurden nicht umgestellt.
3. `tests/unit/test_web_ui_nonmodal.py` — HTML-Quelle in `WEB_FILES` von
   `bin/web/index.html` auf `bin/web/classic.html` umgestellt (der
   Nonmodal-Vertrag gehört zur klassischen UI).

Syntaxprüfung: `python3 -m py_compile tests/unit/web_page.py
tests/unit/test_ap21_i18n.py tests/unit/test_web_ui_nonmodal.py` ohne Fehler.
Die Suiten wurden nicht vollständig ausgeführt (sie sind bis zur
`/classic`-Implementierung rot — beabsichtigt).

## Vertragsunklarheiten (zur Entscheidung durch den Koordinator)

1. **Schranken-Schlüssel groß/klein.** Die Beauftragung nennt
   `{"key":"REPAIR_ROUNDS"}`; `vibe_gates.validate` akzeptiert nur die
   Schlüssel aus `DEFAULTS` (`repair_rounds`, `retries`, …), und
   `PROJECT_ENV_KEYS` bildet genau diese auf `REPAIR_ROUNDS`/`MAX_RETRIES` ab.
   Die Tests verwenden deshalb die `DEFAULTS`-Schlüssel und erwarten die
   Großschreibung nur in `.vibe/project.env`.
2. **Exakte Navigationslabels.** Der Vertrag erlaubt laut Punkt 9
   Wortlautänderungen („Formulierungen dürfen sich ändern“); die Beauftragung
   legt dagegen `Home/Agents/Activity/Settings` und
   `Start/Agenten/Aktivität/Einstellungen` als vertraglich fest. Die Tests
   prüfen die exakten Werte (dokumentiert im Modul-Docstring). Falls der
   Wortlaut frei bleiben soll, müssen diese Assertions gelockert werden.
3. **`/api/emu` Zielprojekt.** Der Vertrag sagt nicht, wie das Projekt gewählt
   wird (Body-Feld? einziges registriertes Projekt?). Der Test nutzt den
   isolierten Arbeitsbereich mit genau einem generischen Projekt und sendet
   nur `{"action":"start"}`.
4. **Fehlende DOM-Hooks.** Für Öffnen-Knopf der Projektkarte, Typ-Badge,
   Bestätigung/Fehleranzeige (Kennwort, Port, Klonen, Ordner) und die Felder
   des Gates-Projekt-Overrides nennt der Vertrag keinen Hook. Die Tests lesen
   diese Stellen über Text bzw. akzeptieren Toast **oder**
   `[data-nv-form-error]`; das ist in den Modul-Docstrings festgehalten.
5. **`GET /api/limits` Form.** Der Vertrag nennt `problem` und `lines`; die
   Beauftragung erlaubt `problem` „None oder fehlend“. Der Test akzeptiert
   `None`/`""` und verlangt `lines` als Liste.
6. **Kennwort-Wiederholung.** `docs/features/AP22.md` sagt nur
   „Wiederholung“; der Test verwendet den in der Beauftragung genannten Hook
   `input[data-nv-field="password-repeat"]`.

## Nicht geprüft / Grenzen

- `/api/runs` nur mit leerem Register (kein Seed eines echten Laufs); die
  Registerzeilen-Form (`id,state,session,project`) ist damit nicht abgedeckt.
- `/api/emu` nur der Fehlerfall ohne Android-Projekt; der Erfolgsfall würde
  ein Android-Projekt und das Emulator-Skript benötigen.
- `/api/paths`: nur die Pflichtfelder `workspace/install/state/runtime/
  agents_dir` und Geheimnisfreiheit; Ports/weitere Felder nicht.
- Gates-Override-UI nur auf Sichtbarkeit der Schlüssel und Existenz eines
  Formularfelds geprüft (kein Hook im Vertrag).
- Skip-Link `.nv-skip`, Tastaturbedienung und Fokusführung sind nicht Teil
  dieser vier Dateien (im Vertrag genannt, aber nicht im beauftragten
  Testumfang).
- Barrierefreiheit/Responsive nur über die genannten Attribute
  (`aria-current`, `aria-expanded`, Sichtbarkeit), kein Screenreader-Test.

## Meilenstein B — Rotphase

Vier Browsersuiten für den Projektarbeitsbereich, zusammen **31 Fälle**
(9 + 8 + 6 + 8), laufen am Stand `a651321` (`feature/m0p/ap22`). Der Stand
enthält nur Platzhalter: `bin/web/nova-project.js` (35 Zeilen: Projekttitel,
fünf Tabs und leere Skelett-Paneele), `bin/web/nova-output.js` (14 Zeilen)
und `bin/web/nova-activity.js` (15 Zeilen) rendern ausschließlich
„Dieser Bereich wird gerade aufgebaut“. Alle Fehlschläge sind deshalb
**beabsichtigte Rotphase** (fehlende Implementierung), **keine
Harness-Fehler**. Beleg: `boot()` und die Navigation warten erfolgreich auf
`main#nv-main[data-nv-view='home|project|activity']` und auf die
Stub-Paneele; die Timeouts setzen erst beim ersten nicht implementierten
`data-nv-*`-Hook ein. Im Projektlauf besteht außerdem
`test_tabs_switch_panels_and_expose_aria` (die Tabs sind im Stub schon
implementiert). `python3 -m py_compile` über alle vier Dateien war ohne
Befund, es musste nichts korrigiert werden.

| Datei | Fälle | Ergebnis |
| --- | --- | --- |
| `tests/browser/test_ap22_project_ui.py` | 9 | 7 Fehlschläge, 9 Fehler (darunter 10 SubTest-Einträge: 5 je Art) |
| `tests/browser/test_ap22_work_ui.py` | 8 | 1 Fehlschlag, 7 Fehler |
| `tests/browser/test_ap22_output_ui.py` | 6 | 1 Fehlschlag, 5 Fehler |
| `tests/browser/test_ap22_activity_ui.py` | 8 | 1 Fehlschlag, 7 Fehler |

### `tests/browser/test_ap22_project_ui.py`

Befehl: `PLAYWRIGHT_BROWSERS_PATH=/home/nutzer/.cache/ms-playwright python3 -m unittest tests.browser.test_ap22_project_ui -v`

```
Ran 9 tests in 199.699s
FAILED (failures=7, errors=9)
```

7 Fehlschläge, 9 Fehler; grün ist nur der Tab-Fall. Die Fehlschläge sind
fünf SubTests von `test_project_settings_sections_and_hidden_features`
(`psection` fehlt komplett) plus `test_basics_has_init_button` und
`test_checks_buttons_and_quick_verify_started`; die Fehler sind fünf
SubTests der Übersichtskacheln plus Held, Pause, Team und Assistent.

Repräsentativ (Held ohne Lauf-Pille):

```
ERROR: test_open_project_from_home_shows_hero (tests.browser.test_ap22_project_ui.ProjectHeroTest.test_open_project_from_home_shows_hero)
playwright._impl._errors.TimeoutError: Locator.wait_for: Timeout 20000ms exceeded.
Call log:
  - waiting for locator("[data-nv-run-state]").first to be visible
```

und (Einstellungssektion):

```
AssertionError: 1 != 0 : Projekteinstellung 'team' fehlt
```

Einordnung: Die Projektansicht liefert bereits `data-nv-project-title` und
die fünf Tabs, aber weder Held-Aktionen, Kacheln, Board, Ausgabe, Assistent
noch `[data-nv-psection]`. Kein Harness-Fehler: Der Held-Fall scheitert erst
nach erfolgreicher Prüfung von Sichtbarkeit und Projekttitel.

### `tests/browser/test_ap22_work_ui.py`

Befehl: `PLAYWRIGHT_BROWSERS_PATH=/home/nutzer/.cache/ms-playwright python3 -m unittest tests.browser.test_ap22_work_ui -v`

```
Ran 8 tests in 200.500s
FAILED (failures=1, errors=7)
```

1 Fehlschlag, 7 Fehler, kein grüner Fall.

Repräsentativ:

```
FAIL: test_columns_and_tickets_follow_the_fixture_states (tests.browser.test_ap22_work_ui.BoardTest.test_columns_and_tickets_follow_the_fixture_states)
AssertionError: 1 != 0 : Board-Spalte 'open' fehlt
```

sowie für die Formulare:

```
playwright._impl._errors.TimeoutError: Locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for locator("[data-nv-action='new-package']").first
```

Einordnung: Das leere Arbeits-Paneel enthält keine Spalten, Karten,
Feedback-Liste, Formulare oder Priorisierung. Die Fehler treten erst nach
`section[data-nv-ppanel='work']` (Stub) auf; Fixtures (`TICKETS.md`,
`FEEDBACK.md`, Feature-Schalter) sind angelegt.

### `tests/browser/test_ap22_output_ui.py`

Befehl: `PLAYWRIGHT_BROWSERS_PATH=/home/nutzer/.cache/ms-playwright python3 -m unittest tests.browser.test_ap22_output_ui -v`

```
Ran 6 tests in 132.844s
FAILED (failures=1, errors=5)
```

1 Fehlschlag, 5 Fehler, kein grüner Fall.

Repräsentativ:

```
FAIL: test_output_without_live_run_shows_log_tail (tests.browser.test_ap22_output_ui.LegacyLogTest.test_output_without_live_run_shows_log_tail)
AssertionError: Die Ausgabe ohne laufenden Lauf zeigt die Protokollzeilen nicht
```

und:

```
playwright._impl._errors.TimeoutError: Locator.wait_for: Timeout 20000ms exceeded.
Call log:
  - waiting for locator("[data-nv-out-overview]") to be visible
```

Einordnung: Die Ausgabe ist ein reiner Platzhalter ohne Übersichtsleiste,
`role="log"`, Subagentenkarten, Steuern, Fortsetzen oder Stop. Lauf,
Zustandsdatei, Protokoll und tmux-Sitzung werden im Fixture erfolgreich
angelegt (sonst wäre `setUp`/`seed_live` gescheitert, nicht der Hook).

### `tests/browser/test_ap22_activity_ui.py`

Befehl: `PLAYWRIGHT_BROWSERS_PATH=/home/nutzer/.cache/ms-playwright python3 -m unittest tests.browser.test_ap22_activity_ui -v`

```
Ran 8 tests in 147.050s
FAILED (failures=1, errors=7)
```

1 Fehlschlag, 7 Fehler, kein grüner Fall.

Repräsentativ:

```
FAIL: test_activity_sections_render (tests.browser.test_ap22_activity_ui.ActivitySectionsTest.test_activity_sections_render)
AssertionError: 1 != 0 : Bereich [data-nv-runs] fehlt
```

und:

```
playwright._impl._errors.TimeoutError: Locator.wait_for: Timeout 20000ms exceeded.
Call log:
  - waiting for locator("[data-nv-sessions] select[data-nv-sessions-project]") to be visible
```

Einordnung: `#/activity` rendert nur Überschrift und Skelett. Die
Rückfrage-JSON liegt vor dem Serverstart im Laufzeitordner, Läufe/Sessions
stehen in den echten Registern — die Fehler betreffen ausschließlich die
fehlenden Anzeige-Hooks.

### Vertragsunklarheiten aus den Testdateien

In den Modul-Docstrings der vier Dateien festgehalten und bewusst so geprüft;
zur Entscheidung durch den Koordinator:

- **Kachel-Zählung** (`project`): Der Vertrag sagt nicht, ob `open` auch
  Feedback-Einträge zählt. Die Fixtures vermeiden die Mehrdeutigkeit
  (`open=2` in beiden Lesarten); `feedback` zählt die Einträge in
  `FEEDBACK.md`.
- **Feedback in der Nachweis-Spalte** (`project`, `work`): „ohne Nachweis“
  entsteht laut Backend nur bei `FEEDBACK.md`; die Fixtures legen deshalb
  Feedback-Einträge mit ungültigem Commit an und erwarten sie als
  Board-Karten in `proof`.
- **Lauf-Pille** (`project`): kein Wert-Hook im Vertrag. Geprüft wird
  `data-state` mit Rückfall auf den sichtbaren Text, erlaubt sind nur
  `running`/`stopped`.
- **Modell-Override** (`project`): kein Speichern-Knopf im Vertrag; erwartet
  wird die unmittelbare Wirkung des `change`-Ereignisses über
  `/api/project-agents`.
- **Autonom-Schalter** (`project`): kein Elementtyp genannt; gelesen werden
  `checked`, `aria-checked` oder `data-on`.
- **Art-Badge** (`work`): kein eigener Hook; geprüft wird der sichtbare Text
  `Bug` bzw. `Feedback` in `article[data-nv-feedback-item]`.
- **Spaltenbeschriftung** (`work`): Wortlaut nicht festgelegt; geprüft
  werden die vier Hooks, `lang="en"` und eine nichtleere Beschriftung.
- **Priorisierungszeilen** (`work`): kein Zeilen-Hook; die Zeile wird über
  Pakettext und den enthaltenen `priority-up`-Knopf gefunden.
- **Löschbestätigung** (`work`, `output`): Format nicht genannt; nativer
  Dialog wird akzeptiert, eine eingebettete Bestätigung wird geklickt.
- **Fokus-Merkmal** (`output`): kein Zustands-Hook; die Karte gilt als
  fokussiert bei Klasse/`data-*` mit `focus` im Namen oder
  `aria-expanded="true"` am Fokus-Knopf — genau eine Karte darf es tragen.
- **„N Subagenten“** (`output`): als Zahl werden die laufenden Subagenten
  erwartet, nicht der Hauptagent.
- **Steuern-Ziel** (`output`): kein Ziel-Select genannt; geprüft werden nur
  Projekt und Text im POST, `session` ist optional.
- **Legacy-Ansicht** (`output`): kein eigener Hook; geprüft wird das
  sichtbare `section[data-nv-ppanel="output"]` samt Protokollzeilen.
- **Glocken-Inhalt** (`activity`): Vertrag nennt Fragen, blockierte Pakete
  und fehlgeschlagene Läufe; Beauftragung und Stand nennen Frage plus
  laufenden Lauf. Geprüft wird die Beauftragung.
- **Läufe-Zeilen** (`activity`): kein Zeilen-Hook; geprüft werden
  Projektname und ein Link/Knopf in die Projekt-/Ausgabeansicht.
- **Sessions-Limit** (`activity`): POST-Form nicht genannt; geprüft wird die
  Persistenz über `GET /api/sessions` und den Reload.
- **Optionsnummer** (`activity`): `[data-nv-answer="<nr>"]` ist 1-basiert,
  das Backend erwartet den 0-basierten Index; Klick auf `1` muss
  `option=0` erzeugen.
- **Leerzustand Läufe** (`activity`): Wortlaut nicht festgelegt; geprüft
  wird ein nichtleerer, sichtbarer Bereich ohne Projektlink.

### Nicht geprüft / Grenzen (Meilenstein B)

- **Live-Streaming.** Die Ausgabe liegt aus der Zustandsdatei
  `proj.log.state.json` vor; `/api/stream` (SSE), Chunk-Timing und
  Nachladen während eines echten Laufs sind ohne Modellaufruf nicht
  abgedeckt.
- **Übersicht-Zusatzfelder.** Prüfstatus (`verify_cmd`), letzter Commit und
  die Fortsetzen-Knöpfe `[data-nv-action="session-resume"]` werden nicht
  geprüft; die Übersichtsuite deckt nur die fünf Kacheln ab.
- **Aktive Feature-Sektionen.** `github`, `writeaccess`, `sandbox`,
  `agentsfile` werden nur auf vollständiges Fehlen bei ausgeschalteten
  Schaltern geprüft; ihr Inhalt bei aktivem Feature gehört zu Meilenstein C.
- **Aktivität-Zusammenfassung.** Die im Vertrag genannten
  Zusammenfassungs-Kacheln, Stop aus der Läufe-Liste und „Fortsetzen“ aus
  den Sessions sind nicht Teil der acht Fälle.
- **Glocken-Sonderfälle.** Blockierte Pakete und fehlgeschlagene Läufe als
  Glocken-Einträge sind nicht geseedet (bewusst: Beauftragung nennt Frage
  und laufenden Lauf).
- **Pause-Rückweg.** Geprüft werden Pause-Datei und Abzeichen; das
  Fortsetzen nach Pause ist nicht abgedeckt.
- **Barrierefreiheit/Responsive.** Nur Rollen/ARIA der Tabs, `role="log"`
  und Sichtbarkeit; kein Screenreader-, Tastatur- oder Mobile-Test des
  Boards (der Vertrag nennt für Meilenstein B keine Breakpoint-Hooks).
- **i18n der neuen Paneele.** Die Suiten laufen mit `lang="en"` und prüfen
  nur einzelne Beschriftungen; eine vollständige Übersetzungsprüfung der
  neuen Bereiche fehlt (AP21 deckt die Shell ab).
