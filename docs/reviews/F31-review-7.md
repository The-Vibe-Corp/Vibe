# Review F31 — Runde 7 (unabhängiger code-reviewer, 2026-11-18)

Verifikationsrunde zu docs/reviews/F31-review-6.md (CHANGES REQUIRED).
Der Reviewer konnte wegen erschöpfter Schrittzahl weder die Datei anlegen
noch python3-Befehle ausführen; der Text wurde vom Koordinator unverändert
aus der Reviewer-Antwort persistiert. Eigene Ausführungen des Reviewers
beschränkten sich auf Git-Befehle und die gelieferten Log-Artefakte.

## Summary
- Critical: 0
- High: 0
- Medium: 2
- Minor: 4
- Verdict: CHANGES REQUIRED

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Prüfmodus `package` in CLI, Menü, API, UI erreichbar | PASS | `scripts/verify.py` `MODES`; `bin/vibe:2199-2235`, Menü `:5510-5523`; `bin/vibe-web.py:1232-1239`; `bin/web/app.js` | `tests/unit/test_verify_script.py` (28 Tests, 2 dokumentierte Umgebungsfehler); `test_verify_api_package.py` (2 OK) im Parallel-Log |
| Unbekannter Modus wird in CLI und API abgelehnt | PASS | `bin/vibe` Fehlermeldung „Unbekannter Prüfmodus … (erlaubt: quick, package, full)“; `bin/vibe-web.py:1819-1824` → HTTP 400 | `test_verify_api_package.py` (400 + unverändertes Log/Stream) per Log bestätigt |
| Gestufte Prüfpraxis in `GENERAL_RULES` und allen 5 Vorlagen | PASS | `bin/vibe` `GENERAL_RULES`; `templates/{android,docker,generic,rebuild,web}/AGENTS.md` | `test_project_management.py` `test_general_rules_require_tiered_verification`, `test_all_shipped_project_templates_contain_the_verification_efficiency_rule` |
| Paralleler Läufer: vollständige Modulentdeckung, keine Doppel-/Verlustläufe | PASS | `scripts/run-tests-parallel.py` (rglob + Dedup, `_FailedTest`, Summenzeile) | `test_run_tests_parallel.py` 7 OK (inkl. `test_nested_test_module_is_discovered_and_run`, `test_no_module_is_executed_twice`) |
| `--timeout` gegen hängende Module | NOT VERIFIED | `scripts/run-tests-parallel.py` implementiert `--timeout` (Default 900, 0 = kein Limit) | Kein Test in `test_run_tests_parallel.py`; `docs/reviews/F31-test-agent-report-2.md` enthält keinen Timeout-Nachweis; behaupteter „Manualnachweis“ fehlt |
| Echte Wirksamkeit (Testzahlen, Fail-Mengen, Laufzeit) | FAIL | `docs/features/F31.md:257-278` | Testzahlen und Fail-Mengen durch Logs belegt (1790 / 1817; genau 2 Zusatzfehler), **Laufzeit 5:42 min / CPU 6:03 min ohne Artefakt** — keine `time`-Ausgabe in `parallel-unit-final.log`, `parallel-unit.log`, `f31_full_test.log` |
| Browser-Abnahme | NOT VERIFIED (zulässig dokumentiert) | `tests/browser/test_f31_verify_package_ui.py` (nur `py_compile`) | `docs/features/F31.md` §Grenzen: ausdrücklich als nicht erbracht gekennzeichnet; Runde-1-Fix erlaubte diese Alternative |
| Manifest- und Dokumentationssynchronität | PASS | `docs/import-manifest.json:936-948` (Delta +21 byte, unabhängig nachgerechnet 4728→4749); `CONTRIBUTING.md`, `docs/features/F31.md` | `tests.unit.test_import_manifest` 8 OK im Parallel-Log |
| Rekursive Modulentdeckung | PASS | `scripts/run-tests-parallel.py` (rglob) | `test_nested_test_module_is_discovered_and_run` OK |
| UTF-8-Dekodierung / `errors="replace"` | PASS | `scripts/run-tests-parallel.py` | im 7-Test-Modul grün; kein separater Grenzfalltest |
| Red-Phase-Nachweis (Runde-1-High) | PASS | Basis `b7fb398`: `MODES=("quick","full")`, API-Fallback, Runner fehlend | Fail-Zustände aus Basis-Code ableitbar; Grün-Seite modulweise im Parallel-Log |
| Test-/Artefaktintegrität (keine geschwächten Assertions, keine Skips) | PASS | `git diff` der Testdateien | Keine `skip`/`assume`/leeren Tests; `test_project_management.py` nur Ergänzungen |

## Findings

- [Medium] `tests/unit/test_run_tests_parallel.py` (gesamte Datei) und `docs/features/F31.md:250-255` — `--timeout` ohne jeden Nachweis
  - Evidence: Der Läufer dokumentiert und implementiert `--timeout` (Default 900, 0 = unbegrenzt, Exit 1 bei Überschreitung), aber es existiert kein Testfall dafür; der in `F31.md`/Testbericht suggerierte Manualnachweis ist in `docs/reviews/F31-test-agent-report-2.md` nicht vorhanden (keine Erwähnung von Timeout/Zeitlimit). Die Abbruch- und Fehlerpfadlogik des Timeouts ist damit unbelegt.
  - Required fix: Entweder einen deterministischen Test ergänzen, der ein hängendes Fixture-Modul mit kleinem `--timeout` abbricht (Exit 1, Modulname sichtbar, keine Endlosblockade), oder die Timeout-Funktion samt Begründung aus dem Leistungsumfang nehmen und die Dokumentation entsprechend korrigieren.

- [Medium] `docs/features/F31.md:257-278` — Laufzeit-/CPU-Angabe der Parallelmessung ohne Artefakt
  - Evidence: Tabelle nennt 5:42 min Wanduhr und 6:03 min CPU für den parallelen Lauf; in den gelieferten Logs (`parallel-unit-final.log`, `parallel-unit.log`, `f31_full_test.log`) fehlt jede `time`-/`real`-Ausgabe. Nur die Baseline ist über `unit-time.txt` (`real 17m24.326s`, `user 4m35.691s`) belegt.
  - Required fix: Die Messung mit aufgezeichnetem `time`-Output (Wanduhr und CPU) erneut belegen und das Artefakt referenzieren — oder die Parallel-Laufzeitangabe als nicht gemessen kennzeichnen und die Wirksamkeitsaussage auf die belegten Test-/Fail-Zahlen stützen.

- [Minor] `scripts/verify.sh:3` — Kopfkommentar nennt weiterhin nur `quick|full`
  - Evidence: Der Modus `package` ist in `verify.py`/CLI/API eingeführt, der Nutzungshinweis im Shell-Wrapper wurde aber nicht nachgezogen; irreführend für Aufrufer.
  - Required fix: Nutzungskommentar um `package` ergänzen.

- [Minor] `docs/features/F31.md:219` — Testzahl „~1840 Unit“ weicht von der gemessenen Zahl ab
  - Evidence: Gemessen wurden 1790 Unit-Tests (Baseline-Log, `Ran 1790 tests`), die Angabe „~1840“ ist nicht durch ein Artefakt gedeckt.
  - Required fix: Zahl auf die belegten 1790 korrigieren oder als Schätzung kennzeichnen.

- [Minor] `docs/features/F31.md:321-322` — Behauptung „Speichern scheitert an der unpaarigen Markerprüfung“ ist falsch
  - Evidence: `_agents_file_split` in `bin/vibe` paart ersten öffnenden mit schließendem Marker (`managed != None`); `agents_file_save` würde daher nicht ablehnen. Korrekt ist nur die Folge, dass `ensure_general_rules` Projektkopfzeilen als verwalteten Inhalt verschluckt. Zudem fehlt ein Regressionstest, der genau ein Markerpaar je Vorlage erzwingt.
  - Required fix: Begründung auf den tatsächlichen Fehlermechanismus (verschluckte Kopfzeilen) reduzieren und einen Vorlagentest ergänzen, der `count(GENERAL_RULES_MARK) == 1` über `templates/*/AGENTS.md` prüft.

- [Minor] `docs/reviews/F31-test-agent-report-2.md:3` — Pfad-Platzhalter nicht als Redaktion kenntlich gemacht
  - Evidence: Der Bericht enthält Platzhalter statt echter Pfade; ohne Hinweis wirkt er wie ein unvollständiger Nachweis. (Die zuvor beanstandeten absoluten Home-Pfade sind bereinigt.)
  - Required fix: Platzhalter als bewusste Redaktion kennzeichnen oder durch reproduzierbare relative Pfade ersetzen.

## Verification
- Change set reviewed: `b7fb398..working tree` (15 modifizierte, 5 unversionierte Dateien, alle F31-bezogen; keine fremden Änderungen).
- Git commands run by me: `git status --short`, `git diff --stat HEAD`, diverse `git diff`/`git show HEAD:<pfad>` (read-only).
- Checks with supplied output: Baseline-Log `Ran 1790 tests in 1044.291s`, `FAILED (failures=72, errors=120, skipped=1)`; Parallel-Log `Gesamt: 1817 Tests, 67/102 Module bestanden, 35 fehlgeschlagen`, 194 Fail-/Error-Zeilen; Differenz exakt die zwei dokumentierten Fälle; `unit-time.txt` bestätigt 17:24 min / 5:39 min CPU.
- Checks not independently run: alle Build-, Test- und Skript-Prüfungen (Reviewer-Rolle; Shell erlaubte nur einzelne Git-Befehle). Die angeforderten `python3`-Kommandos wurden von mir **nicht** ausgeführt.
- Important areas inspected: `bin/vibe`, `bin/vibe-web.py`, `bin/web/app.js`, `scripts/verify.py`, `scripts/run-tests-parallel.py`, 5 Vorlagen-`AGENTS.md`, `docs/import-manifest.json`, `docs/features/F31.md`, `docs/reviews/F31-test-agent-report-2.md`, `tests/unit/{test_run_tests_parallel,test_verify_api_package,test_verify_script,test_project_management,test_process_safety}.py`, `tests/browser/test_f31_verify_package_ui.py`.
- Remaining risks: Parallellaufzeit unbelegt; Timeout-Pfad ungetestet; Browser-Abnahme offen (dokumentiert); vorbestehende Umgebungsfehler (fehlende Root-`AGENTS.md`, Playwright) unverändert.
