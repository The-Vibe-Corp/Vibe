# Review result — AP10 „Schrankeneinstellungen“

**Datum:** 2026-11-11
**Branch:** `vibe/vibe-AP10-1794424684713445226-374755-9863`
**Basis/Ausgangscommit:** `0e62098`
**Geprüfte Commits:** `5dc56ce` (Implementierung), `d6f1d59` (Doku) — Change set `0e62098..HEAD` (13 Dateien, +3352/−1069), Arbeitsbaum sauber (`git status --short` leer)
**Geprüfte Dateien:** `bin/vibe_gates.py` (neu, vollständig), `bin/vibe` (Diff + relevante Umfeldstellen `set_env_values`, `ppath`, `cmd_answer`), `bin/vibe-run.sh` (Diff + aktuelle Zeilenbereiche), `bin/vibe_packages.py` (Diff + `dirty_report`, `block_span`, `select_package`, `read_env`), `scripts/setup-vibe.py`, `docs/baseline.md`, `docs/import-manifest.json` (Auszug), `docs/features/AP10.md` (neu, vollständig), `tests/unit/test_ap10_gates.py` (neu, vollständig), `tests/unit/runner_support.py`, `test_f27_keep_changes.py`, `test_install_lifecycle.py`, `test_setup_vibe.py`; `SPEC.md`, `TICKETS.md` (AP10), `AGENTS.md`, `.vibe/project.env`, `.gitignore`.

## Summary
- Critical: 0
- High: 0
- Medium: 1
- Minor: 2
- Verdict: CHANGES REQUIRED

## Acceptance criteria

| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Schranken global konfigurierbar (`vibe gates <schranke> <wert>` → `<Zustand>/gates.json`) | PASS | `bin/vibe_gates.py:52-62, 265-281` (DEFAULTS, `save` atomar über `vibe_storage.write_text`); `bin/vibe:4961-4970` | `GatesModuleTest.test_save_writes_the_global_file_and_validates_the_value`, `GatesCliTest.test_global_gate_is_persisted_and_shown`, `test_override_gate_accepts_off`; gelieferte Prüfergebnisse: 31 Tests OK, Regressionscluster 213 OK |
| Schranken je Projekt optional abweichend (`.vibe/project.env`, Priorität Projekt > global > Standard, Entfernen per leerem Wert) | PASS | `bin/vibe_gates.py:64-72, 206-263` (`PROJECT_ENV_KEYS`, `effective` mit Projektwerten/Problemliste); `bin/vibe:971-1014` (`set_env_values` mit `quote`/Zeilenentfernung), `bin/vibe:4947-4977` | `GatesModuleTest.test_project_env_overrides_the_global_gates`, `GatesCliTest.test_project_gate_is_written_to_project_env_and_shown`, `test_empty_value_removes_the_project_gate`, `RunnerGateWiringTest.test_project_repair_rounds_override_the_global_gate`; 31/213 OK |
| Schranken wirken im Läufer (MAXP/MAXR/REPAIR_MAX_ROUNDS/ASSIST_MAX_ROUNDS, `VIBE_MAX_PACKAGES`-Vorrang bleibt) | PASS | `bin/vibe-run.sh:139-171` (Gates-Einlesen, shlex-quoted eval), `:176-185`, `:529-530`, `:572` | `RunnerGateWiringTest` (5 Fälle inkl. `test_vibe_max_packages_environment_still_wins_over_the_global_gate`, `test_assist_rounds_gate_limits_the_preflight_rounds`); 31/213 OK |
| Nutzer kann blockierte Schranke überschreiben und den Lauf bewusst fortsetzen (Rückfrage: überspringen / abbrechen / Agent-Runde / Freitextanweisung; autonomer Modus; Timeout-Fälle) | PASS | `bin/vibe-run.sh:383-441` (`barrier_repair_round`, je Runde neue Entscheidung), `:842-854` (Skip-Pfad); `bin/vibe_packages.py:875-978` (`assist_barrier` analog `assist_preflight`, F16) | `BarrierDecisionTest` (7 Läuferfälle: Skip mit Exit 0 und STOP=0, Abbruch, Agent-Runde, erneute Entscheidung, autonom, Zeitlimit, fehlende Module); 31/213 OK |
| Übersprungenes Paket wird nicht gemergt und künftig nicht erneut gewählt; Ticketbeispiel „BLOCKIERT: … Reparaturlimit“ abgedeckt | PASS | `bin/vibe-run.sh:842-854`; `bin/vibe_packages.py:981-1010` (`mark_blocked`), `:495-501` (`_ready`/`is_blocked`) | `test_repair_limit_asks_and_skip_continues_with_the_next_package` (inkl. `git cat-file`-Assertion, dass `impl-F1.txt` nicht gemergt ist); 31/213 OK |
| Rückfälle sicher: ohne `vibe_gates.py`, defekte Dateien/Werte, ungültige Antworten — blockieren konservativ, nichts wird still überschrieben | PASS | `bin/vibe-run.sh:133-171` (Fallback-Rohwerte, ABBRUCH-Ketten bleiben), `:398-401, 404-414, 428-431` (fail-closed); `bin/vibe:4934-4936` | `test_corrupt_gates_file_is_reported_and_defaults_apply`, `test_without_question_modules_the_run_aborts_like_before`, `test_unknown_gate_and_invalid_values_are_rejected_without_writing`; 31/213 OK |
| Nachweis der Rotphase und der Test-Agent-Herkunft | NOT VERIFIED | — | Behauptet in `docs/features/AP10.md:143-147` („Rotphase: 19 Fehlschläge + 8 Fehler“, Test-Agent); Tests und Implementierung liegen im selben Commit `5dc56ce`, ein Rotphasenprotokoll wurde nicht mitgeliefert und ist aus dem Change set nicht rekonstruierbar. Testqualität selbst ist unabhängig geprüft (echte Läufer-Subprozesse, belastbare Assertions); `TESTER=test-agent` ist in `.vibe/project.env:12` konfiguriert |

## Findings

- [Medium] `bin/vibe-run.sh:449` — merge_package verwirft uncommittete Arbeitsnotiz-Änderungen stillschweigend
  - Evidence: `git -C "$P" checkout -q -- TICKETS.md FEEDBACK.md 2>>"$LOG" || true` verwirft vor dem ff-Merge alle uncommitteten (nicht gestagten) Änderungen an diesen beiden Dateien. In Projekten, in denen die Arbeitsnotizen versioniert sind (im Testfixture der Normalfall), gehen damit auch **manuelle Nutzeränderungen** an TICKETS.md/FEEDBACK.md verloren, die während des Laufs entstehen. Vor AP10 blockierte in diesem Fall der ff-Merge („local changes would be overwritten“ → `FEHLT` → Paket blockiert) und die Änderungen blieben erhalten; das Schutzverhalten wurde entfernt, ohne es zu protokollieren (`|| true`, keine Logzeile). Der Code-Kommentar („Manuelle Notizänderungen aus dieser Zeit sind vom Läufer nicht erzeugt“) und `docs/features/AP10.md:126-135` beschreiben den Reset, verschweigen aber die Folge für manuelle Nutzeränderungen.
  - Required fix: (1) Das Verhalten in `docs/features/AP10.md` ausdrücklich als Datenfolge dokumentieren („manuelle Änderungen an TICKETS.md/FEEDBACK.md während eines Laufs werden beim nächsten Paket-Merge verworfen“). (2) Sichtbarkeit schaffen: vor dem Checkout prüfen, ob tatsächlich Änderungen verworfen würden (z. B. `git -C "$P" diff --quiet -- TICKETS.md FEEDBACK.md`), und in diesem Fall eine WARNUNG ins Laufprotokoll schreiben. Alternativ den Verwurf bei echten Nutzeränderungen unterbrechen. Eine Beweisangleitung für den Verwurf-Fall (Test oder dokumentierte Begründung) nachreichen.

- [Minor] `bin/vibe:4939-4944` — `vibe gates status --project <p>` ignoriert `--project` still
  - Evidence: `--project` wird nur als erstes Argument geparst; bei `vibe gates status --project proj` greift stattdessen `project_for_cwd()`. Der Nutzer erhält im Zweifel die Werte des falschen Projekts bzw. der globalen Einstellung, ohne Warnung.
  - Required fix: Argumentreihenfolge in der Hilfe/Doku als verbindlich benennen oder `--project` auch nach `status` auswerten.

- [Minor] `docs/features/AP10.md:117-122` — zwei Zeilenangaben weichen vom aktuellen Stand ab
  - Evidence: „`MAXP`/`MAXR`-Ketten (`:176-181`)“ — tatsächlich `bin/vibe-run.sh:176-185`; „Skip-Pfad … (`:845-858`)“ — tatsächlich `:842-854`. Die übrigen Referenzen (`:139-171`, `:342-455`, `:529-530`, `:572`) stimmen.
  - Required fix: Zeilenangaben in der Feature-Doku korrigieren (oder auf Funktionsnamen ohne Zeilennummern umstellen, damit Dokumentation nicht bei jeder Änderung veraltet).

## Positive Punkte
- Klare, kohärente Umsetzung der beiden Ticketanforderungen: Schrankenmodul (`vibe_gates.py`) folgt dem bewährten Muster `vibe_limits.py`/V-027 (Validierung vor dem Schreiben, atomarer Schreibzugriff, Probleme werden gemeldet statt still interpretiert), die Rückfrage analog `assist_preflight`/F16 und B9-Reparatur.
- Konsequentes Fail-closed: defekte Schranken/Dateien, fehlende Module, ungültige Antworten und Timeout führen zum bisherigen Blockierverhalten; `GATE_OVERRIDE_EFF != ask` und fehlende F16-Module stellen keine neuen Rückfragen (Schutz gegen Verhaltensänderung für Bestandsnutzer).
- Sicherheit: Werte werden vor Schreiben normiert (Zahlen ≥ 1, `ask`/`off`), `eval` nur mit `shlex.quote` (durchgängiges, bereits etabliertes Muster), atomare Schreibvorgänge über `vibe_storage`; keine Geheimnisse, keine Netz-/Modellaufrufe, Prüfskripte (`verify.sh`) unangetastet.
- Testqualität überzeugt: 31 Fälle mit echten Läufer-Subprozessen, echter F16-Antwortdatei, exakten Aufrufzählungen, Merge-Assertions (`git cat-file`) und bewusst deklarierten Charakterisierungsfällen; Installationslisten-Pflege (`PROGRAM_FILES`, `runner_support`) ist gerechtfertigt und vom Test-Agenten dokumentiert.
- `docs/features/AP10.md` ist fachlich und technisch zutreffend, inklusive ehrlicher Grenzen (Wiederholungspfad unverändert, übersprungenes Paket bleibt blockiert vermerkt) und nachvollziehbarer Einordnung der umgebungsbedingten Full-Prüfungsmeldungen (am Baseline-Commit reproduziert).

## Verification
- Change set reviewed: `0e62098..HEAD` (Commits `5dc56ce`, `d6f1d59`), Arbeitsbaum sauber; neue Dateien (`vibe_gates.py`, `test_ap10_gates.py`, `AP10.md`) vollständig gelesen.
- Git commands run by me: `git status --short`, `git log --oneline -5`, `git diff --stat 0e62098..HEAD`, `git diff 0e62098..HEAD -- <je Datei>`, `git show --stat 5dc56ce`, `git show --stat d6f1d59` (einzelne, nur lesende Aufrufe).
- Checks with supplied output (vom Koordinator, kritisch gewürdigt, nicht wiederholt): 31 AP10-Tests OK; Regressionscluster 213 Tests OK; `verify.sh quick` Exit 0; `verify.sh full` 1560 Tests mit 3 failures/2 errors, alle 5 Meldungen am Baseline-Commit `0e62098` in identischer Umgebung reproduziert (FEEDBACK.md im sauberen Klon, AP04-Pi-Hinweis, Home-Pfad B5.md, playwright) und deshalb als vorbestehend/umgebungsbedingt akzeptiert; f27-Baseline-Meldungen durch dokumentierte, sinnvolle Test-Agent-Pflege (TESTER/REVIEWER aus Fixture-Umgebung) beseitigt, keine abgeschwächten Assertions erkennbar.
- Checks not independently run: alle Build-, Test- und Verify-Läufe.
- Important areas inspected: Gates-Einlesen und Fallback-Ketten in `vibe-run.sh`, Reparatur-/Schleifenlogik mit Rückfragecodes (0/1/2), Skip-Pfad inkl. `mark_blocked`/`SKIP`/`record_block`, `merge_package`-Checkout und `work_note_noise`, `cmd_gates`/`set_env_values`, Prioritätslogik in `effective()`, Test-Fixture-Umgebung (`RunnerFixture`).
- Remaining risks: Rotphase und Test-Agent-Herkunft nur belegt, nicht unabhängig nachprüfbar; Gates werden pro Lauf einmalig gelesen (Änderungen wirken erst im nächsten Lauf — dokumentiert); im dokumentierten Verhalten verbleibt, dass der Wiederholungspfad für Agentenfehler und Quota-/Anmeldeabbrüche keine Rückfrage erhalten (ausdrückliche Grenze in AP10.md, keine Lücke gegenüber dem Ticket).

Verdict: CHANGES REQUIRED — genau ein offener Medium-Befund (stillschweigender Verwurf uncommitteter Arbeitsnotiz-Änderungen beim Merge ohne Dokumentation der Nutzerdatenfolge und ohne Protokollzeile); die beiden Minor-Befunde und die obigen Nachweislücken sind bei der Behebung des Medium-Befunds mitzuerledigen, blockieren aber nicht. Nach Korrektur/Dokumentation und erneuter Prüfung ist PASS erreichbar.
