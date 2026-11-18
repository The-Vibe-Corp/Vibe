# Review F31 — Runde 8 (unabhängiger code-reviewer, 2026-11-18)

Verifikationsrunde zu docs/reviews/F31-review-7.md (CHANGES REQUIRED).
Der Reviewer erschöpfte sein Schrittlimit; der Text wurde vom Koordinator
unverändert aus der Reviewer-Antwort persistiert (eigenes Schreib- und
Kommando-Werkzeug außer read-only Git stand der Rolle nicht zur Verfügung).

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 1
- Verdict: PASS

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Runde-7-Befund „Timeout-Test fehlt“ behoben | PASS | `tests/unit/test_run_tests_parallel.py:341-358`; `scripts/run-tests-parallel.py:31-34,88-146` | `test_run_tests_parallel.TimeoutTests`; geliefertes Log `tests.unit.test_run_tests_parallel` „Ran 8 tests … OK“; Test deterministisch (sleep-30-Fixture, `--timeout 2`, äußerer Subprozess-Timeout 60, keine Wanduhr-Assertion) |
| Runde-7-Befund „Laufzeit-Artefakt + Fail-Set-Diff“ behoben | PASS | `docs/features/F31.md:258-283` | Artefakte `/tmp/opencode/unit-time.txt` (real 17m24.326s), `/tmp/opencode/f31-final-timing.txt` (real 5m45.643s), `baseline-unit.log` („Ran 1790 tests in 1044.291s“), `f31-final-parallel-run.log` („Gesamt: 1819 Tests …“); Fail-Set-Diff 192 vs. 193, Differenz ausschließlich neuer AGENTS-Test (Log Zeile 2714) |
| Runde-7-Befund „verify.sh-Header-Kommentar“ behoben | PASS | `scripts/verify.sh:3` (`quick|package|full`) | Kopfkommentar stimmt mit tatsächlich akzeptierten Modi überein |
| Runde-7-Befund „Testzahl 1790 belegen“ behoben | PASS | `docs/features/F31.md:219-220` | Zahl 1790 durch `baseline-unit.log` belegt; 159 Browser-Tests/36 Dateien als Baseline benannt |
| Runde-7-Befund „Marker-Begründung + Regressionstest“ behoben | PASS | `docs/features/F31.md:315-332`; `bin/vibe:2304-2356` | `tests/unit/test_project_management.py:585-599` (Marker-Test); Rotphase über Baseline-Templates mit zwei öffnenden Markern (`/tmp/opencode/baseline/templates/{android,docker}/AGENTS.md`) |
| Runde-7-Befund „Platzhalter-Annotation“ behoben | PASS | `docs/reviews/F31-test-agent-report-2.md:3-9` | Redaktionshinweis vorhanden und nachvollziehbar |
| Package-Modus über CLI/Menü/API/UI erreichbar | PASS | `bin/vibe`, `bin/vibe-web.py`, `bin/web/app.js`, `scripts/verify.py` (Diff b7fb398..4640f29) | `tests/unit/test_verify_script.py` (28 Tests, 2 dokumentierte Umgebungsfehler), `tests/unit/test_verify_api_package.py` (2 Tests OK); UI nicht ausgeführt (dokumentierte Einschränkung, Playwright fehlt) |
| Unbekannter Modus wird abgewiesen | PASS | `scripts/verify.py`/`scripts/verify.sh` | `test_verify_script` (Modus-Validierung), geliefertes Log |
| Gestufte Regeln in `GENERAL_RULES` + 5 Templates | PASS | `bin/vibe:112-119`, `2304-2339`; `templates/{android,docker,generic,rebuild,web}/AGENTS.md` | `tests/unit/test_project_management.py:477-485`; Diff `templates/` rein additiv/bereinigend |
| Runner vollständig, dedupliziert, mit Timeout | PASS | `scripts/run-tests-parallel.py:31-34,88-146` | `tests/unit/test_run_tests_parallel.py` (8 Tests, inkl. Timeout) |
| Browser-Akzeptanz | PASS (dokumentierte Einschränkung) | `tests/browser/test_f31_verify_package_ui.py` | Keine Ausführung möglich/nachgewiesen; als offene Limitation dokumentiert, daher nicht blockierend |
| Manifest-/Doku-Synchronität | PASS | `docs/import-manifest.json:936-948`; `docs/features/F31.md` | Manifest-Eintrag mit Begründung; Doku aktualisiert |
| Test-/Artefakt-Integrität | PASS | `git diff b7fb398..4640f29 -- tests/` | Nur 1 Löschung in `test_verify_script.py` (Docstring-Umbruch); keine Skips, keine leeren Tests, keine abgeschwächten Assertions; keine Änderung an Verifikationswerkzeugen unter `$VIBE/_toolchain/verify` |

## Findings

- [Minor] `docs/features/F31.md:219` — Gesamtsumme „1998 Tests“ ist nicht belegbar
  - Evidence: 1790 Unit-Tests (`baseline-unit.log`) + 159 Browser-Tests ergeben 1949, nicht 1998; kein Artefakt im Work-Package nennt 1998. Zusätzlich enthält die Browser-Suite nach Diff 160 Testmethoden in 37 Dateien, während die Doku 159/36 als Baseline ausweist. Die Aussage ist damit weder aus den gelieferten Artefakten ableitbar noch reproduzierbar; sie berührt kein Akzeptanzkriterium, ist aber eine falsche Mengenangabe in der Paketdokumentation.
  - Required fix: Entweder die Gesamtsumme durch ein konkretes Artefakt belegen und auf die tatsächlich gemessene Zahl korrigieren, oder die nicht belegte Gesamtzahl streichen und ausschließlich die belegten Einzelzahlen (1790 Unit, 159/36 Browser als Baseline) nennen.

## Verification
- Change set reviewed: `b7fb398..4640f29` im Review-Worktree `vibe-F31-Fy9H3n`
  (Branch `vibe/vibe-F31-1794981424594254094-346852-9609`), Arbeitsbaum dort sauber, genau ein Commit. Ergänzend geprüft: der
  Mess-Worktree `vibe-F31-3rRbm8` enthält denselben Änderungsumfang, dort jedoch uncommitted (HEAD `b7fb398`, 20 geänderte/neue Pfade laut `git status --short`).
- Git commands run by me: `git status --short`, `git show 4640f29 --stat`, `git diff --stat b7fb398 4640f29`, `git diff b7fb398 4640f29 -- tests/`, `git diff b7fb398 4640f29 -- templates/`, `git diff b7fb398 4640f29 -- bin/ scripts/verify.py scripts/verify.sh`, `git diff --numstat b7fb398 4640f29`, `git log --oneline -3`.
- Checks with supplied output: `tests.unit.test_run_tests_parallel` „Ran 8 tests … OK“; `test_verify_api_package` 2 Tests OK; `test_verify_script` 28 Tests mit 2 dokumentierten Umgebungsfehlern; `test_process_safety` 2 dokumentierte Fehler; `test_project_management` 21 Fail/Error-Zeilen (20 vorbestehend + neuer AGENTS-Test); Parallel-Gesamtlauf „Gesamt: 1819 Tests, 68/102 Module bestanden, 34 fehlgeschlagen“; Laufzeit-Artefakte wie oben. Diese Ergebnisse stammen aus den gelieferten Logs, nicht aus eigenen Läufen.
- Checks not independently run: alle Build-, Test-, Verify- und Skript-Ausführungen (Rollenbeschränkung: keine Kommandoausführung außer read-only Git). Die Aussagen zu Testläufen sind ausschließlich durch gelieferte Artefakte belegt.
- Important areas inspected: `docs/features/F31.md`, `docs/reviews/F31-review-6.md`, `docs/reviews/F31-review-7.md`, `docs/reviews/F31-test-agent-report-2.md`, `FEEDBACK.md:605-608`, `SPEC.md`, `scripts/run-tests-parallel.py`, `scripts/verify.sh`, `scripts/verify.py`, `bin/vibe` (GENERAL_RULES, `ensure_general_rules`, `_agents_file_split`, `cmd_init`), `bin/vibe-web.py`, `bin/web/app.js`, fünf Template-`AGENTS.md`, `tests/unit/test_run_tests_parallel.py`, `tests/unit/test_verify_script.py`, `tests/unit/test_verify_api_package.py`, `tests/unit/test_process_safety.py`, `tests/unit/test_project_management.py`, `tests/browser/test_f31_verify_package_ui.py`, `docs/import-manifest.json`, Artefakte in `/tmp/opencode`.
- Remaining risks: Messlauf entstand im Worktree `vibe-F31-3rRbm8` vor dem Commit (dortige F31.md zeigt noch die ältere 1817/5:42-Tabelle); die Zeilenanker stimmen mit dem Review-Worktree überein, ein Lauf direkt auf `4640f29` ist nicht belegt. `/tmp/opencode`-Artefakte sind flüchtig. Die Rotphase des Timeout-Tests ist nicht gezeigt (dokumentierte Ausnahme, kein TDD-Anspruch). Der vorbestehende Skip `test_ap12_github_readiness` bleibt unverändert. Browser-UI-Nachweis steht aus (Playwright nicht verfügbar). Trilium-Synchronisation wurde nicht geprüft.
