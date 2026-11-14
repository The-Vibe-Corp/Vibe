# AP8 — Bericht des unabhängigen Test-Agenten (Rotphase)

Datum: 2026-11-10
Rolle: Pflicht-Test-Agent für AP8 (TICKETS.md: „Bereit für Github Teil 2“).
Auftrag: Projekt aus GitHub auschecken und als neues Projekt im Projektordner
anlegen; lokale vibe-Einstellungen überschreiben die Projekteinstellungen; die
im Projekt aktiven Agenten werden auf die lokal konfigurierten Agenten
angepasst. Bindende Nutzerentscheidung: Das Repository enthält im Idealfall nur
Projektcode; die vibe-Einstellungen passt jeder Nutzer individuell an seine
vibe-Instanz an (analog wie bei einer IDE). Nach dem Auschecken gelten daher
die lokalen Einstellungen.

Die Testfälle wurden aus Arbeitspaket, SPEC.md und AGENTS.md abgeleitet —
nicht aus einem Implementierungsdiff (es gab keinen). Produktionsdateien,
Prüfskripte und bestehende Tests wurden nicht verändert.

## Ablagepfade

| Datei | Inhalt |
|---|---|
| `tests/unit/test_ap8_github_checkout.py` | 28 Unit-Tests |
| `tests/browser/test_ap8_checkout_ui.py` | 4 Browser-Tests |
| `docs/reviews/AP8-test-agent-report.md` | dieser Bericht |

Ablageort-Schrittprüfung: Das Anlegen einer Probe-Datei im Worktree war
erlaubt, daher liegen die Testdateien direkt in `tests/unit/` und
`tests/browser/` (keine `/tmp/opencode/ap8-tests`-Zwischenablage nötig).
Der Coding-Agent übernimmt sie unverändert in den Paketbranch.

## Testbefehle

- Unit: `python3 -m unittest tests.unit.test_ap8_github_checkout -v`
- Browser: `python3 -m unittest tests.browser.test_ap8_checkout_ui -v`
- Regressionsrahmen danach: `bash scripts/verify.sh quick` und
  `bash scripts/verify.sh full`

## Prüfungsumgebung der Tests

- Temporäre VIBE-/HOME-Verzeichnisse, keine produktiven Pfade, keine
  Modellaufrufe, keine echte GitHub-Anfrage, kein Verlass auf wirksame
  Unix-Rechte (FUSE/NTFS-neutral).
- Clone-Abläufe laufen ausschließlich gegen lokale Bare-Repositories über
  `file://`. github.com-Adressen werden über die URL-Analyse geprüft; der
  eigentliche Clone-Tätigkeit ist in zwei Tests durch eine fiktive Quelle
  ersetzt (`mock.patch.object` auf `vibe_github.clone`), ohne dass
  github.com kontaktiert wird.
- Browser: Dashboard als echter Prozess gegen eine Fake-Toolchain; die lokalen
  Vorlagen liegen in der betroffenen Installation (`VIBE_INSTALL/templates`);
  Fake-`opencode`/`pi` im PATH; der Dashboard-Token wird aus `_logs/web.token`
  gelesen; Muster wie `tests/browser/test_ap06_github_ui.py`.

## Testfälle und Zuordnung zu den Akzeptanzkriterien

### Unit (`tests/unit/test_ap8_github_checkout.py`)

AK1 — Anlage des Projekts, Name (Klasse `CloneAndProjectTest`):
- `test_checkout_clones_the_repository_and_lists_the_new_project`: Ziel
  `VIBE/<name>`, `.git`-Verzeichnis, Dateiinhalte Originalgetreu; **direkt**
  nach dem Aufruf (ohne jeden manuellen Neuladeweg) in `projects()` und
  `project_map()` auffindbar; Zusammenfassung nicht leer.
- `test_project_name_is_taken_from_the_url_when_not_given` (`mein-koffer.git`
  → `mein-koffer`).
- `test_project_name_is_cleaned_to_the_allowed_pattern`: Name ohne Parameter
  wird auf `^[a-z0-9][a-z0-9_-]*$` bereinigt.
- `test_given_name_wins_over_the_derived_name`: Parameter schlägt URL-Ableitung.

AK2 — Lokale Übernahme (Klasse `LocalAdoptionTest`):
- `test_missing_project_env_is_created_from_the_local_template` (a)
- `test_local_template_values_overwrite_the_managed_repository_keys` (a):
  verwaltete Schlüssel (`TYPE, REVIEWER, TESTER, SANDBOX, SANDBOX_TOOLS,
  VERIFY_QUICK, VERIFY_PACKAGE, VERIFY_FULL`) durch lokale Vorlagewerte
  ersetzt; eigene nicht verwaltete Schlüssel bleiben; `TYPE` steht auf dem
  erkannten Typ und die verwalteten Werte stammen aus der lokalen Vorlage
  dieses Typs.
- `test_github_com_url_sets_the_github_link_without_contacting_github` (b):
  `GITHUB_REPO=owner/beispiel`, `GITHUB_ENABLED=1`.
- `test_file_remotes_stay_without_github_keys` (b): hinter `file://` bleiben
  GitHub-Schlüssel ungesetzt.
- `test_remote_origin_points_to_the_checked_out_address` (b)
- `test_the_managed_rules_block_is_brought_to_the_local_state` (c)
- `test_a_missing_agents_file_is_created_with_the_rules` (c)
- `test_the_shipped_test_agent_is_replaced_by_the_local_template` (d)
- `test_missing_template_files_are_added_and_own_content_survives` (e):
  TICKETS.md/opencode.json ergänzt; vorhandene FEEDBACK.md/README.md unverändert.

AK3 — Agenten-Neumapping (Klasse `AgentRemapTest`):
- `test_active_agents_are_limited_to_locally_configured_agents`: mitgelieferte
  `agents.json` {`aktiv: [vibe-agent, fremd, tester]`, `modelle: {fremd, tester}`}
  → „fremd“ aus `aktiv` und `modelle` entfernt, „vibe-agent“ bleibt aktiv,
  „tester“ bleibt inklusive überschriebenem Modell.
- `test_without_agents_file_the_default_selection_stays_active`: ohne
  Datei gilt der Standard (nur Vibe-Agent).
- `test_the_summary_names_the_removed_agents`: die Zusammenfassung nennt den
  entfernten Agenten („fremd“).

AK4 — Fehlerfälle ohne Restzustand (Klassen `ErrorCaseTest`,
`CloneBehaviorTest`, `CommandLineTest`):
- `test_an_invalid_url_is_rejected_with_a_clear_error` (ValueError,
  „Remote-Adresse“, Anbindung an bestehende `vibe_github.parse_remote_url`)
- `test_an_invalid_name_is_rejected_with_a_clear_error`
- `test_an_existing_project_name_is_rejected_without_changes`
- `test_an_existing_target_folder_rejects_the_checkout`
- `test_a_failed_clone_leaves_no_project_folder`
- `test_a_missing_git_command_is_reported_without_a_project_folder`
  (PATH enthält kein git)
- `CloneBehaviorTest.test_clone_copies_the_repository_to_the_target` (rc 0)
- `CloneBehaviorTest.test_clone_reports_a_failed_source_without_a_project_folder`
  (rc != 0, Meldung nicht leer, kein Zielordner)
- `CloneBehaviorTest.test_clone_runs_without_a_shell` (Argumentliste; eine in
  der URL versteckte Shell-Folge `; touch …` bleibt unwirksam)
- `test_cli_clone_prints_a_summary_and_creates_the_project` (CLI-Erfolg, AK1)
- `test_cli_clone_rejects_invalid_urls_and_existing_names`
- `test_cli_clone_reports_a_missing_git`

### Browser (`tests/browser/test_ap8_checkout_ui.py`)

AK5 — Dashboard (Klasse `CheckoutUiTest`):
- `test_the_project_list_offers_the_github_checkout_card`: Karte „Neues
  Projekt“ enthält ein URL-Feld (Bezeichnung passend auf
  `URL|Adresse|GitHub|auschecken|Remote` in `aria-label`/`placeholder`) und
  genau einen Knopf „Aus GitHub auschecken“.
- `test_checkout_from_a_local_file_url_creates_and_opens_the_project`:
  Erfolg legt das Projekt an (`.vibe/project.env` aus der lokalen Vorlage mit
  `TESTER=test-agent` und `TYPE=`, keine `GITHUB_REPO`-Zeile), AGENTS.md
  trägt die lokalen Regeln („Projektordner sauber halten“), die neue Zeile
  erscheint in der Liste, das Projekt öffnet sich (Überschrift) und die
  origin-Adresse stimmt mit der Quelle überein.
- `test_the_clone_api_creates_the_project_and_requires_the_token`:
  `POST /api/clone` mit gültigem Dashboard-Token liefert
  `{ok, message, project}` und legt das Projekt an; ohne Token kein Erfolg;
  ungültige URL liefert strukturierten Fehler und legt nichts an.
- `test_an_invalid_url_reports_an_error_and_keeps_the_form_usable`: Klar
  gemeldeter Fehler, kein halb angelegtes Projekt, die Karte bleibt ohne
  blockierenden Dialog nutzbar.

## Rotphasen-Nachweis (vor der Implementierung)

### Unit

- Befehl: `python3 -m unittest tests.unit.test_ap8_github_checkout -v`
- **Exit-Code: 1**
- Zusammenfassung: `Ran 28 tests … FAILED (failures=7, errors=19)`
- Ursachen: `AttributeError: module … has no attribute
  'checkout_from_github'` (19 Fehler + einige Assertions-Fehler),
  `mock.patch.object(..., 'clone')` wegen fehlendem `vibe_github.clone`
  (AttributeError), CLI-Subbefehl „clone“ nicht vorhanden (Exitcode != 0,
  kein Projekt angelegt). Vollständiges Protokoll: `/tmp/opencode/ap8-red-unit.log`
  (temporär, nicht Teil des Repos).

### Browser

- Befehl: `python3 -m unittest tests.browser.test_ap8_checkout_ui -v`
- **Exit-Code: 1**
- Zusammenfassung: `Ran 4 tests … FAILED (failures=3, errors=1)`
- Kernaussage: „kein URL-Feld gefunden; Felder: ['projektname (a-z, 0-9, -)',
  'nur Android: Vorlage aus \"android create --list\"']“ — die Karte
  „Neues Projekt“ hat heute kein URL-Feld und keinen Knopf „Aus GitHub
  auschecken“; `/api/clone` ist nicht vorhanden; die übrigen Abläufe
  scheitern entsprechend. Protokoll: `/tmp/opencode/ap8-red-browser.log`
  (temporär, nicht Teil des Repos).

## Sonderlage in der Rotphase

Zwei Unit-Tests sind vorab grün, weil ein Fehlschlag heute trivial nichts
hinterlässt: `test_a_failed_clone_leaves_no_project_folder` und
`test_a_missing_git_command_is_reported_without_a_project_folder`. Ihr
angemessener Wert zeigt sich erst mit der Implementierung: Sobald
`checkout_from_github` existiert, wird der Fehlerpfad tatsächlich erreicht.
Ich habe diese Tests nicht abgeschwächt; auch die übrigen Assertions wurden
nicht relativiert.

## Hinweise für den Coding-Agenten

- Testbefehle stehen oben; die Grünfahrt wird erwartet, wenn AP8 die
  beschriebenen Schnittstellen-Verträge erfüllt: `vibe_github.clone(url,
  zielordner)` -> `(rc, Meldung)`, `vibe.checkout_from_github(url, name=None)`
  -> `(name, Zusammenfassung)`, CLI `vibe clone <url> [name]`, Web-API
  `POST /api/clone` (`{ok, message, project}`), Karte „Neues Projekt“ mit
  URL-Feld und Knopf „Aus GitHub auschecken“.
- Verwaltetes Verhalten, das ich absichtlich festnagle: Projektaufindung
  **direkt** nach `checkout_from_github` (kein manueller Neuladeaufruf),
  Test-Agent-Datei wird durch die lokale Vorlage ersetzt (nicht nur
  ergänzt), origin zeigt auf die ausgecheckte Adresse, die Zusammenfassung
  nennt die entfernten Agenten.
- Auswahl der Vorlagewerte im Unit-Test: Mit nur einer bereitgestellten
  Vorlagenart (`generic`) ist „erkannter Typ“ eindeutig; falls die
  Typ-Erkennung mehr Merkmale nutzt, muss sie auf einen Typ aus
  `types()` fallen, dessen lokale Vorlage die verwalteten Schlüssel liefert.
- Am UI-Texte-Muster: Die Eingabe ist über `aria-label` oder `placeholder`
  mit den Begriffen `URL|Adresse|GitHub|auschecken|Remote` auffindbar; der
  Knopf heißt textlich „Aus GitHub … auschecken“ (Fallausschlag nicht
  schreibdifferenziert geprüft, Umlaut erlaubt: „auschecken“).

## Offene Grenzen und Lücken (Det: Diese Nachweise liefert kein Test)

- Ein echter Clone von github.com über das echte Netz, Authentisierung mit
  einem echten Personal Access Token und Team-Realitäten sind hier
  ausdrücklich nicht nachweisbar (dauerhafte Grenze des Testschutzs; echte
  Bazzite-Abnahme bleibt weiter erforderlich).
- Die Lehre, ob „erkannter Typ“ auch für Typen mit mehreren Vorlagenkandidaten
  korrekt liegt, ist nicht belegt (nur ein Standardtyp in der Testvorlage).
- Barrierefreiheit, Kontrast, Tastaturhaltung im neuen Kartenabschnitt sind
  nicht Gegenstand dieser Tests.

Ausdrücklich: Die Tests wurden vor der Implementierung geschrieben und
bereits einmal genuin ausgeführt (Rotphase, Exit 1). Eine wiederholte
Ausführung nach der Implementierung liegt (entweder von mir nachgezogen oder
durch den Coding-Agenten im Paketverlauf) beim zweiten Durchlauf fest.

## Fixlauf 1 (2026-11-11, nach Implementierung)

Anlass: Der Coding-Agent meldete „28 Tests, 1 Fehler, 1 Fehlschlag“ und
ermittelte, dass beide Befunde nicht am fachlichen Verhalten durch meine
Tests behindert wurden: genau ein Befund war ein Testfehler in meiner Datei,
ein Befund lag in der Implementierung (Quoting) und wurde behoben.

### Geänderte Testzeilen (nur meine Testdateien)

- `tests/unit/test_ap8_github_checkout.py`,
  `LocalAdoptionTest.test_github_com_url_sets_the_github_link_without_contacting_github`:
  Der Patch-Aufruf
  `mock.patch.object(self.cli.vibe_github, "clone", fake_clone) as standin`
  gab `standin` als die übergebene Funktion selbst zurück (Patch mit
  explizitem `new`), nicht als Magic-Objekt; `standin.assert_called_once()`
  schlug daher mit `AttributeError: 'function' object has no attribute
  'assert_called_once'` fehl — unabhängig von jeder Implementierungsmöglichkeit.
  Korrektur (minimal, Produktlogik unverändert):
  `standin = mock.MagicMock(side_effect=fake_clone)`; `mock.patch.object(
  self.cli.vibe_github, "clone", standin)`. Die Aufrufprüfung
  (`assert_called_once`, Argumente URL und Zielordner über `fake_clone`)
  blieb erhalten; alle übrigen Assertions blieben unverändert.
- `tests/browser/test_ap8_checkout_ui.py`,
  `test_the_clone_api_creates_the_project_and_requires_the_token`:
  Die Seite wurde nie geladen; `fetch('/api/clone')` lief im Browserkontext
  `about:blank` und scheiterte mit „Failed to parse URL from /api/clone“.
  Korrektur: `self.open_project_list()` vor dem ersten `fetch`-Aufruf —
  die API läuft danach über die tatsächlich geladene Oberfläche.

### Beleg nach der Korrektur

- Einzellauf `test_github_com_url_sets_the_github_link_without_contacting_github`
  → OK (`Ran 1 test`, Exit 0).
- Einzellauf `test_cli_clone_prints_a_summary_and_creates_the_project` → OK
  (`Ran 1 test`, Exit 0) — das behobene Behoben-Quotingfall ist grün.
- Gesamtsuite Unit: `python3 -m unittest tests.unit.test_ap8_github_checkout -v`
  → **Exit 0**, `Ran 28 tests … OK` (Protokoll `/tmp/opencode/ap8-unit-fix1b.log`).
- Gesamtsuite Browser: `python3 -m unittest tests.browser.test_ap8_checkout_ui -v`
  → **Exit 1**, `Ran 4 tests … FAILED (failures=1, errors=1)`
  (Protokoll `/tmp/opencode/ap8-browser-fix1b.log`); 2 von 4 Browser-Tests sind
  grün (`test_the_project_list_offers_the_github_checkout_card`,
  `test_an_invalid_url_reports_an_error_and_keeps_the_form_usable`).

### Gemeldeter Implementierungsdefekt (kein Testfehler; nicht von mir behoben)

Beide verbleibenden Browser-Fehlschläge haben dieselbe Ursache. Beleg über ein
Diagnoselauf (Wegwerf-Skript unter `/tmp/opencode/ap8-diag`, nicht Teil
des Repos):

- Die Oberfläche klickt den Knopf „Aus GitHub auschecken“; Dashboards
  rufen `POST /api/clone` auf; der Projektordner entsteht real (vorbereitete
  Datei `.vibe/project.env` existiert, Zeile „aushang“ erscheint in der
  Projektliste) — aber die Antwort ist HTTP 500 mit
  `UnboundLocalError: cannot access local variable 'ok' where it is not
  associated with a value`.
- Betroffener Ort: `bin/vibe-web.py`, Zweig `elif u.path == "/api/clone":`
  (in der Erfolgszeile steht `found, msg = vibe.checkout_from_github(...)`
  und `extra["project"] = found`; `ok` wird im Erfolgs-Pfad nie gesetzt.
  im Fehler-Pfad aber schon — deshalb bricht die Antwort-Erzeugung).
- Auswirkung: Der Dashboard-Aufruf meldet dem Browser einen Fehlschlag, die
  Oberfläche markiert „Fehler“ und öffnet nicht das Projekt
  (`test_checkout_from_a_local_file_url_creates_and_opens_the_project` scheitert
  beim Warten auf die Projektüberschrift) und die API meldet
  `ok: false` statt `{ok: true, message, project}`
  (`test_the_clone_api_creates_the_project_and_requires_the_token` scheitert
  bei `assertEqual(status, 200)`, da der Server intern 500 liefert).
- Erforderliche Korrektur an `bin/vibe-web.py`: Im Erfolgs-Pfad auch
  `ok` setzen (zum Beispiel `ok, msg = True, msg`), sodass die erwartete
  Antwort `{ok: true, message, project}` entsteht. Diese Korrektur ist
  Sache des Coding-Agenten; ich habe an Produktionsdateien nichts geändert.
  Umwege (etwa die Fehlermeldung der Oberfläche als Erfolgsnachweis zu
  werten) bleiben als Lösungen unzulässig und der Test verlangt den
  fachlich korrekten Antwortzustand weiter.

## Fixlauf 2 (2026-11-11): Umgebungsrückbau in `StorageFixture.setUp`

### Defekt

`StorageFixture.setUp` (tests/unit/test_ap8_github_checkout.py) setzte ohne
Rückbau:

    os.environ["VIBE_STORAGE_LOCK_DIR"] = str(self.workspace / "locks")
    os.environ["VIBE_STATE"] = str(self.install)

Diese Werte blieben nach dem Test im Prozess bestehen und konnten nachfolgende
Testmodule desselben Prozesses beeinflussen (Storage- und
Projektschreibverzeichnis-Module laden `bin/vibe` neu; `vibe_paths.resolve()`
liest `VIBE_STATE` aus der Umgebung). Meldung des Coding-Agenten:
`tests.unit.test_ap8_github_checkout tests.unit.test_storage.McpStorageTest`
→ `test_save_keeps_other_servers_and_creates_collision_free_backups`
(AssertionError 8 != 2), `test_restore_brings_back_the_previous_configuration`
(['g'] != ['alt']).

### Änderung (nur meine Testdatei)

Die beiden Zuweisungen wurden durch `mock.patch.dict(os.environ, {...})`
ersetzt; der Patch wird mit `environment.start()` und
`self.addCleanup(environment.stop)` automatisch zurückgebaut. Inhaltliche
Testfälle und Assertions blieben unverändert.

### Zusatzprüfung auf weitere dauerhafte Umgebungsänderungen

Geprüft mit grep über die Datei: Es gibt keine weiteren dauerhaften
`os.environ`-Schreibzugriffe. `load_cli` sichert alle `ISOLATED_ENV`-Schlüssel
vorher und stellt sie im `finally` wieder her; `ErrorCaseTest` nutzt
`mock.patch.dict` für den PATH-Fall; `CommandLineTest` baut ausschließlich ein
lokales Env-Wörterbuch für Subprozesse. Die Browser-Datei enthält nur das
etablierte `os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", …)` (gleiche
Zeile wie in `tests/browser/test_ap06_github_ui.py`); daran habe ich nichts
geändert. Ein Umgebungs-Snapshot-Lauf je Einzeltest (Treiberskript
`/tmp/opencode/ap8-diag/leakfind.py`, nicht Teil des Repos) meldete nach der
Korrektur für alle 28 Tests: **TOTAL: 0** (kein neuer, entfernter oder
veränderter Umgebungsschlüssel).

### Ausgeführte Befehle und tatsächliche Ergebnisse

Wichtige Nebenbeobachtung zuerst: Die Sitzungsumgebung, in der ich die
Prüfungen ausführe, trägt produktive `VIBE_*`-Variablen (darunter
`VIBE_STATE` auf die produktive `_toolchain`). `scripts/verify.py` entfernt
alle geerbten `VIBE_*`-Variablen (Funktion `prepare_environment`); die
`test_storage`-Festures isolieren ihrerseits nur `HOME` und
`VIBE_STORAGE_LOCK_DIR`. Deshalb habe ich alle nachfolgenden Läufe in einer
desinfizierten Umgebung ausgeführt (Muster `prepare_environment`: alle
`VIBE_*`/`XDG_*`, TMUX und PYTHONPATH entfernt, frisches temporäres HOME,
Wrapper `/tmp/opencode/ap8-diag/sanitized-run.sh`, nicht Teil des Repos;
vorher `rm -rf /tmp/opencode/ap8-env`).

1. `python3 -m unittest tests.unit.test_ap8_github_checkout -v`
   - in der Sitzungsumgebung: **Exit 0**, `Ran 28 tests … OK`
   - desinfiziert: **Exit 0**, `Ran 28 tests … OK`
   (Protokoll `/tmp/opencode/ap8-fix2-unit-clean.log`)
2. Kontaminationsnachweis:
   `python3 -m unittest tests.unit.test_ap8_github_checkout
   tests.unit.test_storage.McpStorageTest
   tests.unit.test_storage.AgentStorageTest tests.unit.test_project_write_dirs -v`
   - desinfiziert: **Exit 0**, `Ran 80 tests … OK` — die beiden zuvor
     kontaminierten Failures (69 != 2; ['g'] != ['alt']) treten nicht mehr auf.
   (Protokoll `/tmp/opencode/ap8-fix2-combined-clean.log`)
   - Zur Einordnung auch vorab isoliert desinfiziert:
     `python3 -m unittest tests.unit.test_storage.McpStorageTest
     tests.unit.test_storage.AgentStorageTest` → **Exit 0**, `Ran 12 tests … OK`.
3. `python3 -m unittest discover -s tests/unit`
   - desinfiziert, nur zur Information: **Exit 1**, `Ran 1394 tests`,
     `FAILED (failures=6)`. Die sechs Befunde liegen allesamt paketfremd und
     betreffen weder AP8, Storage noch die Schreibverzeichnisse:
     `test_ap04_setup_harness.SetupHarnessTest.test_dry_run_explains_pi_and_its_install_command`,
     `test_f27_keep_changes.RunnerKeepChangesTest.test_other_findings_block_even_with_keep_changes`
     (drei Parametervarianten no-tester/no-reviewer/no-check; Arbeitskopien
     unter `_logs/worktrees`), `test_release.ReleaseBuildTest.
     test_repository_content_has_no_personal_home_paths_or_secrets`
     (Home-Pfad in `docs/features/B4.md`), `test_verify_script.
     ScreenshotIsolationTest.test_browser_screenshots_honor_the_verify_directory`.
   (Protokoll `/tmp/opencode/ap8-fix2-discover.log`)
   - Der offizielle Abnahmevergleich bleibt `bash scripts/verify.sh full`
     mit der vom Coding-Agenten beschriebenen Baseline-Bewertung.

### Grenzen

- Ein Läufergebnis „grün“ außerhalb der desinfizierten Umgebung ist in dieser
  Sitzung kein aussagekräftiger Nachweis: Die produktiven `VIBE_*`-Variablen
  der Sitzung selbst können Festures ohne eigene VIBE-Isolation (wie
  `test_storage`) auch ohne AP8-Beteiligung kippen; das habe ich nachgestellt
  (`McpStorageTest` isoliert in der Sitzungsumgebung: 3 Failures; desinfiziert:
  grün). Dies ist eine Eigenschaft der Prüfumgebung, kein Defekt meiner Datei.
- Der `discover`-Lauf ersetzt nicht `verify.sh full` (kein
  opencode-Dienst, keine Browser-Sektion); die dortigen 6 Failures habe ich
  nur zugeordnet, nicht behoben.

## Fixlauf 3 (2026-11-11): Regressionstests für Review-Runde 1 (AP8-review-1.md)

Anlass: Review-Runde 1 beanstandete ungedeckte Verhaltensweisen; die
Implementierung ist auf Coding-Seite bereits behoben. Ich habe die geforderten
Regressionstests ergänzt — ohne Implementierungsänderung. Diese Tests sind
nachträgliche Absicherung bereits korrigierten Verhaltens; eine Rotphase ist
hier nicht mehr erzeugbar (der Fix liegt vor), was ich ausdrücklich so
vermerke statt einen künstlichen Rotlauf zu behaupten.

### Ergänzte Testfälle (tests/unit/test_ap8_github_checkout.py, 33 Tests gesamt)

Klasse `CredentialMaskingTest(StorageFixture)` — Befund Medium (A):
- `test_mask_embedded_credentials_masks_all_urls_and_keeps_plain_ones`
  - Vorbedingung: Modul geladen; mehrzeiliger Freitext mit drei URLs mit
    Zugangsdaten (nutzer:geheim, person:brief, klartext ohne Passwort) und
    einer klaren URL.
  - Aktion: `vibe_github.mask_embedded_credentials(text)`.
  - Erwartet: keine Zugangsdaten im Ergebnis (auch keine Teilzeichenketten
    wie `brief@`), dreimal `***@github.com`, klare URL unverändert, Maskieren
    ist idempotent.
- `test_clone_masks_embedded_credentials_in_its_message`
  - Vorbedingung: Bare-Adresse mit Zugangsdaten in der URL; die
    Git-Ausführung an der Naht von `clone` (Modulfunktion `git`) liefert eine
    mehrzeilige Fehlerausgabe mit den Zugangsdaten (Simulation, kein Netz).
  - Aktion: `vibe_github.clone(url, ziel)`.
  - Erwartet: rc != 0; Meldung enthält weder `geheim` noch `nutzer:geheim`,
    dafür `***@github.com`; der Auth-Hinweis („Zugangsdaten") bleibt erhalten;
    Git-Aufruf genau einmal.
- `test_clone_failure_without_a_live_service_leaks_no_credentials`
  - Vorbedingung: realer Ausfallpfad gegen 127.0.0.1:1 (nur Loopback, kein
    externer Dienst).
  - Erwartet: rc != 0, Meldung ohne Zugangsdaten, kein Zielordner bleibt
    zurück.

Klasse `LocalAdoptionTest` — Befund Minor (B):
- `test_unmanaged_keys_keep_the_repository_value_while_managed_keys_move_local`
  - Vorbedingung: lokale Vorlage enthält zusätzlich einen nicht verwalteten
    Schlüssel (`EXTRA_KEY=lokal-vorlage`); mitgelieferte project.env enthält
    `EXTRA_KEY=projektwert`, `TESTER=repo-tester`, `TYPE=generic`,
    `BENUTZER=EIGEN`.
  - Erwartet: `EXTRA_KEY` bleibt `projektwert` (nicht verwaltet → mitgelieferter
    Wert gewinnt, selbst wenn die lokale Vorlage ihn kennt); abweichende
    verwaltete Schlüssel gehen auf den lokalen Stand (`TESTER=test-agent`,
    `REVIEWER=lokal-reviewer`); `TYPE` auf erkannten Typ; eigener Schlüssel
    `BENUTZER=EIGEN` bleibt.

Klasse `ErrorCaseTest` — Befund Minor (C):
- `test_an_adoption_failure_removes_the_target_folder_and_reports_the_reason`
  - Vorbedingung: echte Bare-Quelle; die Übernahme scheitert zuverlässig durch
    `mock.patch.object(cli, "ensure_general_rules", side_effect=OSError(
    "gesperrt"))` — derselbe Mock-Ansatz wie in bestehenden Tests
    (tests/unit/test_project_agents.py), statt unzuverlässiger
    Dateirechte auf FUSE/NTFS.
  - Erwartet: `ValueError` mit „Übernahme fehlgeschlagen" und Ursachentext
    („gesperrt"); der Zielordner ist entfernt; das Projekt ist nicht in der
    Projektliste.

### Ausgeführte Befehle und Ergebnisse

- Wrapper wie Fixlauf 2 (desinfizierte Umgebung, frisches temporäres HOME,
  keine geerbten `VIBE_*`-Variablen; vorher `rm -rf /tmp/opencode/ap8-env`).
- `python3 -m unittest tests.unit.test_ap8_github_checkout -v`
  → **Exit 0**, `Ran 33 tests … OK` (Protokoll `/tmp/opencode/ap8-fix3-unit2.log`).
- Alle fünf neuen Tests laufen und sind grün (Einzelnachweise im Protokoll:
  3× `CredentialMaskingTest`, 1× unverwalteter Schlüssel, 1× Übernahme-Aufräumen).
- Zwischenbefund (mein Testfehler, behoben): Die erste Fassung von
  `test_mask_embedded_credentials…` scheiterte an `assertNotIn("nutzer:", …)`,
  weil „nutzer:" Teilzeichenkette des Freitextworts „Benutzer:" war. Korrektur:
  Prüfwörter präzisiert (`nutzer:geheim` statt `nutzer:`) und Freitextwort
  geändert („Anmeldung"). Keine Implementierungsberührung.
- Gegen die tatsächliche Implementierung scheitert kein Fall; es gibt keinen
  neuen Befund an der Implementierung aus diesem Fixlauf.
- Grenze: Ein Nachweis der Maskierung über eine echte Git-Fehlerausgabe mit
  Zugangsdaten ist ohne Netz/echte Authentisierung nicht erzwingbar (git
  selbst maskiert Zugangsdaten in den geprüften Ausfallpfaden bereits); der
  Nachweis läuft deshalb über die genau beschriebene Naht (`clone()` wendet
  `mask_embedded_credentials(_auth_guidance(out))` an) plus einen
  realen Loopback-Ausfallpfad ohne Zugangsdaten-Leak.
