# F31 — Test-Agent, Runde 2 (2026-11-17)

> Redaktionelle Anmerkung des Koordinators: Persönliche absolute Pfade
> (Arbeitskopie, /tmp-Entpackverzeichnis) wurden zur Einhaltung der
> Release-Inhaltsregeln (`test_release.ReleaseBuildTest.
> test_repository_content_has_no_personal_home_paths_or_secrets`) durch
> die Platzhalter `<Arbeitskopie vibe-F31-3rRbm8>` und
> `<Basis-Entpackverzeichnis>` ersetzt; die Testaussagen und Ausgaben sind
> unverändert.

Arbeitskopie: <Arbeitskopie vibe-F31-3rRbm8>
Branch: vibe/vibe-F31-1794952034093847392-2175 (keine Commits, keine Branchwechsel)
Basis für Rotphasen: b7fb398 (HEAD), entpackt nach <Basis-Entpackverzeichnis> via `git archive`;
der Arbeitsbaum enthält bereits Produktionsfixes, daher wurden Rotphasen am Basisstand
reproduziert, nicht am Arbeitsbaum. Produktionscode wurde nicht verändert.

## 1. Geänderte Dateien (nur Tests)

| Datei | Änderung |
|---|---|
| tests/unit/test_verify_api_package.py | Neuer Test `test_api_verify_rejects_an_unknown_mode_without_starting_a_run` + Helper `wait_for_stable_file` |
| tests/unit/test_run_tests_parallel.py | Neuer Test `test_nested_test_module_is_discovered_and_run`; `HEADER_RE` erlaubt nun verschachtelte Modulnamen (`tests(?:\.\w+)+`); `run_runner` akzeptiert optional `env`; **ersetzt**: `test_default_runs_modules_in_parallel` (zeitbasiert) durch `test_default_runs_modules_with_overlapping_execution_windows` (Zeitfenster-Überlappung); Fixture `TEST_UEBERLAPPUNG`, `TEST_TOP`, `TEST_NESTED` |

## 2. Aufgabe 1 — API-Fehlerpfad unbekannter Prüfmodus

Test: `VerifyApiPackageTest.test_api_verify_rejects_an_unknown_mode_without_starting_a_run`
Vorbedingung: Dashboard-Fixture wie im vorhandenen Test (eigenes VIBE/HOME/RUNTIME, `VERIFY_QUICK/PACKAGE/FULL` = echo-Marker).
Aktion: `POST /api/verify` mit `{"name": "proj", "mode": "voller"}`.
Erwartung: HTTP 400, `ok=False`, Meldung nennt `voller` und die erlaubten Modi `quick, package, full`; verify-Log bleibt unverändert und enthält keinen quick-Marker; im verify-Stream folgt nach dem Bestands-Tail kein weiterer `data:`-Block.

Rotphase (Basis b7fb398):
```
FAIL: test_api_verify_rejects_an_unknown_mode_without_starting_a_run
  File "<Basis-Entpackverzeichnis>/tests/unit/test_verify_api_package.py", line 240
    self.assertEqual(status, 400, body)
AssertionError: 200 != 400 : {"ok": true, "message": "Prüfung gestartet"}
```
Zusätzlich im Basis-Lauf des vorhandenen Erfolgsfalls sichtbar: das Protokoll enthielt
`$ echo quick-pruefung` statt `paket-pruefung` → der unbekannte/fehlende Modus fiel still
auf `quick` zurück und startete einen Lauf. Genau dagegen prüft der neue Test.

Grün am Arbeitsbaum:
```
test_api_verify_accepts_package_and_runs_verify_package ... ok
test_api_verify_rejects_an_unknown_mode_without_starting_a_run ... ok
Ran 2 tests in 2.995s
OK
```
Hinweis: Die API antwortet auf den Fehlerpfad mit HTTP 400 (strukturiertes `rejected`),
nicht 200; der Test hält dieses beobachtete Vertragsverhalten fest.

## 3. Aufgabe 2 — Verschachteltes Testmodul

Test: `RunTestsParallelTest.test_nested_test_module_is_discovered_and_run`
Fixture: `<tmp>/tests/test_top.py` (2 Tests) und `<tmp>/tests/verschachtelt/test_nested.py`
(3 Tests), dazu leere `tests/__init__.py` und `tests/verschachtelt/__init__.py`, damit
`python3 -m unittest tests.verschachtelt.test_nested` importierbar ist.
Erwartung: beide Blöcke `--- tests.test_top ---` und `--- tests.verschachtelt.test_nested ---`,
Summe 5 Tests, 2/2 Module, Exit 0.

Rotphase (Arbeitsbaum, Läufer noch nicht rekursiv):
```
FAIL: test_nested_test_module_is_discovered_and_run
AssertionError: Lists differ: ['tests.test_top'] != ['tests.test_top', 'tests.verschachtelt.test_nested']
Second list contains 1 additional elements.
First extra element 1: 'tests.verschachtelt.test_nested'
Ran 1 test in 0.108s
FAILED (failures=1)
```
Machbarkeit gegengeprüft: eine Kopie des Läufers mit `base.rglob("test*.py")` liefert exakt
die geforderte Ausgabe (`Gesamt: 5 Tests, 2/2 Module bestanden, 0 fehlgeschlagen`). Die
Fixture verlangt also nur die rekursive Suche, keine weitere Schnittstelle.

## 4. Aufgabe 3 — Flaky-Parallelitätstest ersetzt

Entfernter Test: `test_default_runs_modules_in_parallel` (Wanduhr, `elapsed < 2.6`).
Neuer Test: `test_default_runs_modules_with_overlapping_execution_windows`.
Mechanik: Die drei Fixture-Module schreiben Start-/Endzeit (`time.time()`) ihres Laufs in
`<tmp>/stamps/test_<x>.stamp`; das Verzeichnis kommt über die geerbte Umgebungsvariable
`F31_STAMP_DIR` (nur Test-Fixture, **keine neue Läufer-Schnittstelle**). Der Test fordert
mindestens ein Paar mit `min(end) > max(start)`; eine langsame Maschine verschiebt alle
Fenster gemeinsam und kann den Test nicht mehr kippen.

Rotphase: nicht applicable — Verhaltensänderung des Tests, keine neue Produkteigenschaft.
Der Test ist am aktuellen Stand grün (Läufer arbeitet bereits parallel), dreimal wiederholt:
```
Ran 1 test in 0.902s  OK
Ran 1 test in 0.888s  OK
Ran 1 test in 0.873s  OK
```
Zweck: Eliminierung der vom Reviewer gerügten Flakiness, nicht Abnahme einer neuen Eigenschaft.

## 5. Ausgeführte Checks (echte Ausgaben)

`python3 -m unittest tests.unit.test_verify_api_package -v`
→ Ran 2 tests, OK (2.995s)

`python3 -m unittest tests.unit.test_run_tests_parallel -v`
→ Ran 7 tests, FAILED (failures=1), 2.162s; grün: all_modules, failing_module, import_error,
jobs_one, no_module_twice, overlapping_windows; rot: nested (erwartet, Aufgabe 2).
Keine bestehenden Tests der Dateien wurden beschädigt; genau ein Test wurde ersetzt (siehe 4).
`python3 -m py_compile` beider Dateien: OK.

## 6. NACHTRAG Rotphasen-Dokumentation Runde 1 (26 Tests)

Die Transkripte der ersten Runde liegen in dieser Sitzung nicht mehr vor; die Belege wurden
deshalb am Basisstand b7fb398 mit den Testdateien des Arbeitsbaums erneut ausgeführt
(`git archive HEAD` → <Basis-Entpackverzeichnis>, Testdateien hineinkopiert). Alle Ausschnitte unten sind
tatsächlich beobachtete Ausgaben. Ausnahme: der Browser-Test ist hier nicht reproduzierbar
(Playwright im Environment nicht installiert).

### VerifyPackageTest (11, tests/unit/test_verify_script.py)
Beobachtetes Rot für alle: `FEHLT: Unbekannter Modus 'package'. Erlaubt: quick, full.` (Exit 2)

| Testname | Vorbedingung | Aktion | erwartetes Ergebnis | beobachtete Rotphase |
|---|---|---|---|---|
| test_package_runs_verify_package_instead_of_quick_or_full | Fixture-Projekt mit VERIFY_PACKAGE | `verify.sh package` | Exit 0, nur VERIFY_PACKAGE-Befehl | `AssertionError: 2 != 0 : FEHLT: Unbekannter Modus 'package'. Erlaubt: quick, full.` |
| test_package_requires_verify_package_without_falling_back | VERIFY_PACKAGE fehlt | `verify.sh package` | Exit 3, kein quick/full | `AssertionError: 2 != 3 : FEHLT: Unbekannter Modus 'package'...` |
| test_package_rejects_a_todo_placeholder | VERIFY_PACKAGE="echo TODO" | `verify.sh package` | Exit 3, TODO abgelehnt | `AssertionError: 2 != 3 : FEHLT: Unbekannter Modus 'package'...` |
| test_package_requires_test_files_when_verify_tests_is_set | VERIFY_TESTS>0, keine Testdateien | `verify.sh package` | Exit 6, Testnachweis fehlt | `AssertionError: 2 != 6 : FEHLT: Unbekannter Modus 'package'...` |
| test_package_rejects_a_run_without_executed_tests | Testdatei mit 0 Tests | `verify.sh package` | Exit 6 | `AssertionError: 2 != 6 : FEHLT: Unbekannter Modus 'package'...` |
| test_package_passes_with_real_tests_and_reports_the_count | echte Tests, VERIFY_TESTS=1 | `verify.sh package` | Exit 0, Testzahl gemeldet | `AssertionError: 2 != 0 : FEHLT: Unbekannter Modus 'package'...` |
| test_package_rejects_fewer_tests_than_configured | 1 Test, VERIFY_TESTS=2 | `verify.sh package` | Exit 6 | `AssertionError: 2 != 6 : FEHLT: Unbekannter Modus 'package'...` |
| test_package_without_verify_tests_requires_no_test_proof | kein VERIFY_TESTS | `verify.sh package` | Exit 0 ohne Testnachweis | `AssertionError: 2 != 0 : FEHLT: Unbekannter Modus 'package'...` |
| test_package_does_not_start_the_opencode_service | kein Dashboard-Dienst | `verify.sh package` | Exit 0, kein Dienststart | `AssertionError: 2 != 0 : FEHLT: Unbekannter Modus 'package'...` |
| test_help_names_the_package_mode | — | `verify.sh --help` | Hilfe nennt `package` | `AssertionError: 'package' not found in 'Aufruf: bash scripts/verify.sh quick\|full ...'` |
| test_unknown_mode_lists_package_as_allowed | — | `verify.sh unbekannt` | Meldung nennt package | `AssertionError: 'package' not found in "FEHLT: Unbekannter Modus 'unbekannt'. Erlaubt: quick, full."` |

### CommandBoundaryTest (4 neue, tests/unit/test_process_safety.py)

| Testname | Vorbedingung | Aktion | erwartetes Ergebnis | beobachtete Rotphase |
|---|---|---|---|---|
| test_package_mode_reads_verify_package_from_project_env | project.env mit VERIFY_PACKAGE="printf paket" | `verify_command("proj","package")` | "printf paket" | `VerifyConfigError: Unbekannter Prüfmodus: package (erlaubt: quick, full)` |
| test_package_mode_has_no_quick_or_full_fallback | nur VERIFY_QUICK/FULL gesetzt | `verify_command("proj","package")` | None (kein Fallback) | `VerifyConfigError: Unbekannter Prüfmodus: package (erlaubt: quick, full)` |
| test_package_placeholder_is_rejected_as_configuration_error | VERIFY_PACKAGE="echo TODO" | `verify_command("proj","package")` | ConfigError nennt VERIFY_PACKAGE | `AssertionError: 'VERIFY_PACKAGE' not found in 'Unbekannter Prüfmodus: package (erlaubt: quick, full)'` |
| test_unknown_verify_mode_lists_package_as_allowed | — | `verify_command("proj","paket")` | Meldung nennt package | `AssertionError: 'package' not found in 'Unbekannter Prüfmodus: paket (erlaubt: quick, full)'` |

### TemplateRulesTest (3 neue, tests/unit/test_project_management.py)

| Testname | Vorbedingung | Aktion | erwartetes Ergebnis | beobachtete Rotphase |
|---|---|---|---|---|
| test_general_rules_require_tiered_verification | GENERAL_RULES aus bin/vibe | Abschnitt suchen | Abschnitt "Effizienz der Prüfungen (verbindlich)" | `AssertionError: 'Effizienz der Prüfungen (verbindlich)' fehlt in GENERAL_RULES` |
| test_all_shipped_project_templates_contain_the_verification_efficiency_rule | 5 templates/*/AGENTS.md | Abschnitt suchen | Abschnitt in jeder Vorlage | `AssertionError: 'Effizienz der Prüfungen (verbindlich)' fehlt in <Basis-Entpackverzeichnis>/templates/android/AGENTS.md` |
| test_repository_agents_file_contains_the_verification_efficiency_rule | Repo-Wurzel/AGENTS.md | Datei lesen | Regel vorhanden | `AssertionError: False is not true : AGENTS.md fehlt im Repository-Wurzelverzeichnis; die Repository-Regeln können nicht geprüft werden.` |

### RunTestsParallelTest (6, tests/unit/test_run_tests_parallel.py)
Basisstand b7fb398 enthält `scripts/run-tests-parallel.py` nicht; alle sechs scheiterten
identisch an der fehlenden Datei:

| Testname | Vorbedingung | Aktion | erwartetes Ergebnis | beobachtete Rotphase |
|---|---|---|---|---|
| test_all_modules_run_and_report_their_tests | 3 Fixture-Module | Läufer `--jobs 3` | 3 Blöcke, 6 Tests, Exit 0 | `AssertionError: 2 != 0 : /usr/bin/python3: can't open file '.../scripts/run-tests-parallel.py': [Errno 2] No such file or directory` |
| test_default_runs_modules_in_parallel (in Runde 2 ersetzt) | 3 Module je 1 s | Läufer ohne `--jobs` | Wanduhr < 2.6 s | gleiche Fehlermeldung (fehlende Läuferdatei); Testtext in Runde 2 durch deterministischen Überlappungstest ersetzt |
| test_a_failing_module_is_named_and_its_output_stays_visible | 1 Modul mit fail() | Läufer `--jobs 2` | Exit 1, Modulname + Ausgabe sichtbar | `AssertionError: 2 != 1 : can't open file '.../run-tests-parallel.py'` |
| test_a_module_with_an_import_error_counts_as_failed | 1 Modul mit Importfehler | Läufer `--jobs 2` | Exit 1, Modul gezählt | `AssertionError: 2 != 1 : can't open file '.../run-tests-parallel.py'` |
| test_jobs_one_is_sequential_and_equivalent | 3 Fixture-Module | `--jobs 3` vs. `--jobs 1` | gleiche Module/Summen | `AssertionError: 2 != 0 : can't open file '.../run-tests-parallel.py'` |
| test_no_module_is_executed_twice | 3 Fixture-Module | `--jobs 1` und `--jobs 3` | keine Doppelläufe | `AssertionError: 2 != 0 : can't open file '.../run-tests-parallel.py'` |

### API-Paketfall (1, tests/unit/test_verify_api_package.py)

| Testname | Vorbedingung | Aktion | erwartetes Ergebnis | beobachtete Rotphase |
|---|---|---|---|---|
| test_api_verify_accepts_package_and_runs_verify_package | Dashboard-Fixture | `POST /api/verify {"mode":"package"}` | ok=True, Log/Stream mit paket-pruefung | `AssertionError: 'paket-pruefung' erschien nicht in .../proj.verify.log. Prüfprotokoll: $ echo quick-pruefung ... quick-pruefung` → stiller quick-Fallback |

### Browserabnahme (1, tests/browser/test_f31_verify_package_ui.py)

| Testname | Vorbedingung | Aktion | erwartetes Ergebnis | beobachtete Rotphase |
|---|---|---|---|---|
| test_package_button_runs_the_package_check_and_streams_its_output | Dashboard + Playwright-Browser | Klick "Prüfung package" | Marker im verify-Stream, Screenshot | **nicht reproduziert**: `ModuleNotFoundError: No module named 'playwright'` in dieser Umgebung. Die Rotphase am Basisstand (fehlender package-Button) ist damit nicht erneut belegt; der Browserlauf bleibt offener Punkt aus F31-review-6. |

## 7. Grenzen / offene Punkte

- Aufgabe 1 war am Arbeitsbaum bereits implementiert; die Rotphase ist nur am Basisstand
  b7fb398 beobachtbar (dort: HTTP 200, `ok:true`, „Prüfung gestartet", Log `echo quick-pruefung`).
- Aufgabe 2 ist bis zur Läuferänderung (`rglob`) erwartungsgemäß rot; der Test verlangt keine
  neue Läufer-Schnittstelle, nur rekursive Erfassung.
- Browser-Test nicht ausführbar (Playwright fehlt); keine Browser-/Screenshot-Abnahme durch
  den Test-Agenten.
- Die drei TemplateRules-Erwartungen aus Runde 1 sind laut Review teilweise umstritten
  (gitignorierte AGENTS.md); das ist nicht Gegenstand dieses Test-Auftrags und wurde nicht
  verändert. Die Entscheidung des Koordinators (Musterkonsistenz mit den vorbestehenden
  Geschwistertests, siehe docs/features/F31.md) bleibt bestehen.
- Keine Produktionsänderungen, keine Commits, kein Branchwechsel.

## 8. NACHTRAG Runde 3 (2026-11-18, Review-Fixes aus F31-review-7.md)

Neue Tests (nur Testdateien geändert):
- `tests/unit/test_run_tests_parallel.py::test_timeout_aborts_a_hanging_module`
  (Fixture `TEST_LANGSAM` mit `time.sleep(30)`; Läufer `--timeout 2 --jobs 1`;
  Erwartung Exit 1, Blockkopf, `TIMEOUT`-Hinweis, „Fehlgeschlagene Module:
  tests.test_langsam“, Summenzeile 0/1/1; keine Wanduhr-Assertion).
  Rotphase: nicht applicable — der Test schließt die Evidenzlücke zu bereits
  implementiertem Verhalten und ist am Arbeitsbaum grün.
- `tests/unit/test_project_management.py::TemplateRulesTest.
  test_all_shipped_project_templates_have_exactly_one_general_rules_marker`
  (genau ein öffnender und ein schließender Marker je Vorlage).
  Rotphase am Basisstand b7fb398 (git-archive-Klon): android/docker haben dort
  je zwei öffnende Marker — `AssertionError: 2 != 1`. Grün am Arbeitsbaum.

Ergebnisse: `tests.unit.test_run_tests_parallel` 8 OK;
`TemplateRulesTest` 14 Tests, neuer Marker-Test OK, die bestehenden
Umgebungs-/Vorbestands-Fails unverändert.
