# AP7-Korbat — Review Runde 2 (Bestätigung nach Minor-Adressierung)

Reviewer: vibe-reviewer (unabhängig, read-only) · Grundlage: Review Runde 1 (docs/reviews/AP7-Korbat-review-1.md, PASS mit 3 Minor) und deren Adressierung im Arbeitsbaum

Die Antwort des Reviewers wird unverändert wiedergegeben:

---
# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 0
- Verdict: PASS

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Verification evidence |
|---|---|---|---|
| T-V13: Self-Reference-Guard (`verify.sh`/`verify.py`/`verify_engine.py`, fail-safe bei nicht auflösbaren Tokens, Exit 3 mit klarer Meldung; `VIBE_VERIFY_DEPTH` ≥ 2 → Exit 3, Tiefe 1 erlaubt und inkrementiert) | PASS | `scripts/verify_engine.py:68`, `scripts/verify_engine.py:480-501`, `scripts/verify_engine.py:873-889` | `tests/unit/test_ap7_korbat_verify.py:109-215` (`SelfReferenceGuardTest`, 7 Fälle); Rot-/Grünlauf im Test-Agent-Bericht (`docs/reviews/AP7-Korbat-test-agent-report.md` §§3.3, 5.1) |
| T-V16: Refactor Frontend (`scripts/verify.sh`), Engine (`scripts/verify_engine.py`, Isolation unverändert, liest nur `VERIFY_QUICK` als Befehl + Optionsvariablen, `package` führt `VERIFY_QUICK` + opt. `VERIFY_PACKAGE_TESTS` aus, `full` baut `run-tests-parallel.py`-Lauf selbst) und Compat-Shim (`scripts/verify.py` via `os.execv`) | PASS | `scripts/verify.sh:1-17`, `scripts/verify.py:1-18`, `scripts/verify_engine.py:131-216`, `scripts/verify_engine.py:279-360`, `scripts/verify_engine.py:624-738` | `tests/unit/test_ap7_korbat_verify.py:52-107`, `217-449`, `tests/unit/test_verify_script.py:349-706`, `tests/unit/test_verify_api_package.py:49-297`, `tests/browser/test_f31_verify_package_ui.py:64-192` |
| T-V17: Baseline-Manifest (`tests/verify-baseline.json`, Schema v1, `min_tests=2000`, `envs={}`), `run-tests-parallel.py --report PATH`, Dreizustands-Auswertung (Grün Exit 0, Baseline-OK Exit 0 mit Diff + `VERIFY_RESULT:`, Regression Exit 7, Nachweismangel Exit 6, 7 schlägt 6, ungültige Baseline Exit 3), Signatur-Normalisierung ohne Umgebungsdetails (S4) | PASS | `tests/verify-baseline.json:1-5`, `scripts/run-tests-parallel.py:59-65`, `156-162`, `180-238`, `scripts/verify_engine.py:506-573`, `734-860` | `tests/unit/test_ap7_korbat_report.py:66-207` (6 Fälle), `tests/unit/test_ap7_korbat_baseline.py:96-273` (`BaselineTriStateTest`, 9 Fälle), `tests/unit/test_ap7_korbat_rules.py:226-294` (`CommittedBaselineManifestTest`, 4 Fälle) |
| T-V18: Umgebungs-Schlüssel (`--env`/`VERIFY_ENV` explizit, kein Best-Match, Mismatch → Baseline ignoriert + Exit 7 bei Fehlern + `--write-baseline`-Hinweis; `--write-baseline` schreibt nur lokal `.vibe/verify-baseline`, erhält andere Env-Sektionen, ändert Laufurteil nicht [D2]; Präzedenz `--baseline` > lokal > committed exklusiv [D1]) | PASS | `scripts/verify_engine.py:555-586`, `scripts/verify_engine.py:745-851` | `tests/unit/test_ap7_korbat_baseline.py:275-441` (`EnvLabelTest`, 7 Fälle) und `tests/unit/test_ap7_korbat_baseline.py:443-566` (`LocalBaselinePrecedenceTest`, 3 Fälle, Test-Agent-Bericht §12.3: `Ran 23 tests in 32.435s, OK`) |
| T-V19: Monotone Baseline / `VERIFY_MIN_TESTS` Ratchet (effektives Minimum = max über alle Quellen; Senkung bei `--write-baseline` → Exit 3; AGENTS.md-Regeln `Effizienz der Prüfungen` + `Baseline-Disziplin` in `bin/vibe` und allen 5 Templates synchron) | PASS | `scripts/verify_engine.py:760-764`, `scripts/verify_engine.py:826-845`, `bin/vibe:125-153`, `templates/{android,docker,generic,rebuild,web}/AGENTS.md` | `tests/unit/test_ap7_korbat_baseline.py:568-639` (`RatchetTest`, 4 Fälle), `tests/unit/test_ap7_korbat_rules.py:81-224` (`GeneralRulesTest`, 9 Fälle), `tests/unit/test_project_management.py:445-462` |
| T-V20: Runner bleibt minimal (`final_verify`/`run_package_tests`/`verify_run` funktional unverändert, kein Exitcode-6/7-Sonderhandling; Nutzer-Verdrahtung dokumentiert) | PASS | `bin/vibe-run.sh:713-720`, `docs/features/AP7-Korbat.md:143-156`, `docs/betrieb.md:232-259`, `docs/checkliste.md:36-45` | `tests/unit/test_ap9_runner_wiring.py`, `tests/unit/test_ap4_korbat_github.py` (gelieferte Verifikationsausgabe: unverändert grün) |
| T-V21 + Transport: Hash-/Diff-Wächter für `.vibe/project.env` und `.vibe/verify-baseline` (erkennt Veränderung und Löschung einer beim Start vorhandenen Datei, läuft vor jeder `run_package_tests`-Iteration in der `while`-Schleife inkl. nach `repair_round`, `record_block` ohne Reparaturrunde, best effort bei fehlender Startdatei); Transport-Erweiterung in `bin/vibe_packages.py` (1:1, best effort `0444`, idempotenter Git-Exclude, nie zurück) | PASS | `bin/vibe-run.sh:686-712`, `1612-1621`, `1670-1680`, `1695-1697`, `bin/vibe_packages.py:107-109`, `224-282`, `1696-1707` | `tests/unit/test_ap7_korbat_runner.py:133-355` (8 Fälle inkl. `DeletedTransportedFileTest` und `test_deleting_an_absent_baseline_does_not_block`; Rotphase der Löschfälle in §12.2/12.4 belegt, nach Produktionsfix `Ran 8, OK`), `tests/unit/test_ap5_korbat_project_env_transport.py:295-426` (4 neue Fälle + 6 Bestandsfälle) |
| Nutzerentscheidung 1: T-P9 / T-P10 (pi-infra) descopt | PASS | Nicht anwendbar (kein pi-infra-Code im Änderungssatz) | Durch `git status --short` und `git diff --stat d4c24ee` direkt verifiziert |
| Dokumentation & Import-Manifest (`docs/features/AP7-Korbat.md`, `docs/betrieb.md`, `docs/checkliste.md`, `docs/import-manifest.json`) | PASS | `docs/features/AP7-Korbat.md:1-186`, `docs/betrieb.md:163`, `232-259`, `docs/checkliste.md:36-45`, `docs/import-manifest.json:1332-1377` | Gelieferte Ergebnisse von `bash scripts/verify.sh quick` (Exit 0 inkl. aktualisierter `bin/vibe-run.sh`-Prüfsumme in `docs/import-manifest.json:1374-1377`) und `python3 scripts/check-syntax.py` (Exit 0) |

## Findings
- No findings.

## Verification
- Change set reviewed: `d4c24ee..working tree` auf Branch `feature/korbat/ap7-korbat` (Bestätigungsreview Runde 2 über die Adressierung der 3 Minor-Befunde aus `docs/reviews/AP7-Korbat-review-1.md`).
- Git commands run by me: `git status --short`, `git diff d4c24ee --stat`, `git diff d4c24ee -- bin/vibe-run.sh docs/import-manifest.json tests/unit/runner_support.py`.
- Checks evidenced by supplied raw output:
  - Test-Agent-Bericht Runde 5 (`docs/reviews/AP7-Korbat-test-agent-report.md` §12.4):
    - Vor dem Produktionsfix: `python3 -m unittest tests.unit.test_ap7_korbat_runner.DeletedTransportedFileTest -v` → `Ran 2 tests in 5.808s, FAILED (failures=2)`; Gesamtlauf `test_ap7_korbat_runner -v` → `Ran 8 tests in 21.514s, FAILED (failures=2)` (die 5 bisherigen Fälle + der neue Negativfall `test_deleting_an_absent_baseline_does_not_block` grün).
    - `python3 -m unittest tests.unit.test_ap7_korbat_baseline.LocalBaselinePrecedenceTest -v` → `Ran 3 tests in 5.621s, OK`; Gesamtlauf `test_ap7_korbat_baseline` → `Ran 23 tests in 32.435s, OK` (inkl. Union-Gegenprobe).
  - Alle bereits in Review 1 belegten Ausgaben aus Runden 3 und 4 (`round3-redphase.log`, `test_verify_api_package`, `test_f31_verify_package_ui`).
- Checks reported only by the coding agent:
  - Nach dem Produktionsfix in `bin/vibe-run.sh`: `python3 -m unittest tests.unit.test_ap7_korbat_runner` → `Ran 8, OK`.
  - Kombinierter Koordinator-Lauf: `python3 -m unittest tests.unit.test_ap7_korbat_runner tests.unit.test_ap7_korbat_baseline` → `Ran 31, OK`.
  - `bash scripts/verify.sh quick` → Exit 0 (inkl. aktualisiertem Import-Manifest); `python3 scripts/check-syntax.py` → Exit 0.
  - Vorbestands-Gegenprobe `test_b16_runner_wiring.test_diverged_integration_branch_blocks_with_divergiert` am unveränderten HEAD reproduziert und `bin/vibe-run.sh` anschließend byte-identisch zum Manifest-SHA-256 (`23c8e14dc72de993c055d9db9456e40dbad157475e1e55a6b2ca1651fc682789`, 86493 Bytes) wiederhergestellt.
- Checks not independently run: Alle Build-, Test- und sonstigen Nicht-Git-Prüfungen (als read-only Reviewer gemäß Rollenvorgabe nicht selbst ausgeführt).
- Important areas inspected:
  - **Adressierung Minor 1 (`bin/vibe-run.sh:686-712`, `1612-1621`, `1669-1697`):**
    - `guard_transported_files` prüft bei gesetztem Start-Hash (`-n "$PKG_HASH_PROJECT_ENV"` bzw. `-n "$PKG_HASH_BASELINE"`) explizit zuerst `[ ! -f "$WT/.vibe/..." ]` und setzt `TAMPERED_FILE`, bevor der Hash-Vergleich läuft. Fehlt die Datei bereits beim Paketstart (`PKG_HASH_*=""`), greift der Wächter nicht (Best-effort-Semantik gewahrt).
    - Der Aufruf `if ! guard_transported_files; then ...` steht jetzt als erster Schritt innerhalb der `while :; do`-Schleife (`bin/vibe-run.sh:1674-1680`) unmittelbar vor `run_package_tests`, läuft also sowohl nach dem initialen `run_agent` als auch nach jeder Reparaturrunde (`repair_package_finding` → `repair_round`).
    - **Schleifen- und Abbruchlogik:** Bei Manipulation setzt der Block `record_block`, loggt `BLOCKIERT: ...`, setzt `STOP=1` und verlässt mit `break` die innere `while :; do`-Schleife. Unmittelbar nach `done` fängt `if [ "$STOP" = 1 ]; then break; fi` (`bin/vibe-run.sh:1695-1697`) den Zustand ab und bricht die Versuchsschleife ab, ohne nochmals in `if [ "$PACKAGE_OK" != 1 ]` ein zweites `record_block` oder eine doppelte `BLOCKIERT:`-Zeile zu erzeugen.
  - **Adressierung Minor 2 (`docs/features/AP7-Korbat.md:158-167`, `183-186`, `docs/import-manifest.json:1374-1377`):**
    - Der Abschnitt „Hash-/Diff-Wächter (T-V21, Lean)" beschreibt jetzt präzise die Prüfung vor jeder Paketprüfung (inkl. nach Reparaturrunde) sowie das Blockieren bei Veränderung und Löschung einer beim Start vorhandenen Datei.
    - Der letzte Punkt unter „Grenzen" (`docs/features/AP7-Korbat.md:183-186`) gibt den tatsächlichen Stand aus Runde 4 korrekt wieder (echter, grüner Lauf von `tests/browser/test_f31_verify_package_ui.py` unter headless Chromium; Grenze ist die Beschränkung auf Chromium/headless ohne manuelle Tastatur- oder Cross-Browser-Prüfung).
    - `docs/import-manifest.json` ist für `bin/vibe-run.sh` (`bytes: 86493`, neuer `sha256`) nachgezogen.
  - **Adressierung Minor 3 & Test-Agent-Integrität (`tests/unit/test_ap7_korbat_baseline.py:443-566`, `tests/unit/test_ap7_korbat_runner.py:240-355`, `tests/unit/runner_support.py:348-405`, `docs/reviews/AP7-Korbat-test-agent-report.md` §12):**
    - Sämtliche Teständerungen seit Review 1 (`delete:<datei>` in `runner_support.py`, `DeletedTransportedFileTest` + `test_deleting_an_absent_baseline_does_not_block` in `test_ap7_korbat_runner.py`, `LocalBaselinePrecedenceTest` mit 3 Fällen in `test_ap7_korbat_baseline.py`) sind vollständig in §12 des Test-Agent-Berichts dokumentiert, inklusive Rot-Beleg für die Löschfälle vor dem Produktionsfix und Union-Gegenprobe für D1. Keine bestehenden Assertions wurden abgeschwächt; keine unbefugten Dateien wurden verändert.
- Remaining risks:
  - Wie in Review 1 vermerkt: Die Umstellung der autoritativen `.vibe/project.env` im Hauptprojekt (`$P`) auf die `verify.sh`-Wrapper-Verdrahtung und `VERIFY_ENV` sowie die initiale Befüllung von `tests/verify-baseline.json` per Review-Workflow bleiben dokumentierte Nutzerschritte (`docs/features/AP7-Korbat.md`).