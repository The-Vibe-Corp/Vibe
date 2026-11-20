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

Befehl: `PLAYWRIGHT_BROWSERS_PATH=/home/vibe/.cache/ms-playwright python3 -m unittest tests.browser.test_tickets_ui -v`

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
