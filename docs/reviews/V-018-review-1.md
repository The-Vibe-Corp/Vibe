# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 1
- Minor: 2
- Verdict: **CHANGES REQUIRED**

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Vorschau (zeigt Ziel, Version, Aktion; schreibt nichts) | PASS | `scripts/setup-vibe.py:430-505` (`build_install_plan`, `describe_plan`), Dry-run-Zweig `1281-1295`, `--preview`-Alias `1104-1110` | `PreviewTest.test_plan_lists_new_changed_and_unchanged_files`, `test_preview_does_not_write_anything`, `test_preview_works_while_a_run_is_live` (tests/unit/test_install_lifecycle.py:152-174); E2E-Auszug „Ziel nach der Vorschau nicht angelegt“ (Review-Eingabe) |
| Sicherung ersetzter Dateien | PASS | `install_program_files` `740-772` (`_next_backup_root`, `_backup_file`, `backup.json`) | `UpdateTest.test_update_backs_up_program_and_user_template_and_keeps_runtime` (test_install_lifecycle.py:528ff); `test_update_without_changed_files_still_records_the_new_version`; E2E „Sicherung enthält templates/generic/AGENTS.md“ |
| Versionskennung (Quelle, `version.json`) | PASS (mit Befund im Fehlerpfad) | `read_kit_version` `361-389`, `read_installed_version` `392-404`, Schreiben `785-790`, `--version` `1083-1092` | `VersionTest` (113-135); **aber**: bestehende `version.json` wird im `--reuse`-Fehlerpfad gelöscht (Finding 1) |
| Rollback (jüngste/benannte Sicherung, Entfernen neuer Dateien) | PASS | `select_backup` `827-859`, `rollback`/`_restore_backup` `862-868, 624-674`, CLI `1163-1189` | `RollbackTest` (alle 7 Tests); E2E „Nutzervorlage wiederhergestellt“, „Entfernt (neu seit dem Update): 1“ |
| Laufzeitdaten und persönliche Konfiguration bleiben erhalten | PASS | Plan enthält nur Programm-/Vorlagenpfade (`_install_sources` `418-427`), `models.json`-Skip `463-465`, RUNTIME_FILES nie im Plan (das Paket Union legt `RUNTIME_FILES` nur im Umfang fest) | `FreshInstallTest.test_fresh_install_keeps_existing_runtime_data`; `UninstallTest.test_uninstall_removes_programs_and_templates_but_keeps_runtime_and_projects`; E2E: models.json, vibe.json, _logs, Projekt erhalten |
| Keine Überschreibung mitten im Self-Development | PASS (mit dokumentierter Lücke) | `running_installation` `933-967`; Sperren für Update `1297-1304`, Rollback `1172-1179`, Uninstall `1215-1222`; `--force`-Freigabe | `RunningGuardTest` (3 Tests, test_install_lifecycle.py:588-634); E2E „FEHLER: Die Installation wird gerade verwendet; nichts geändert (Exit 1); --force führt das Update aus“ |
| Uninstall löscht keine Projekte | PASS | `uninstall` `871-930` (entfernt nur `bin/*`, `templates`, `version.json`, eigenen Starter, `vibe.cmd`); Abbruch-Dialog `1190-1239` | `UninstallTest` (8 Tests); E2E „17 Datei(en)/Bereich(e) entfernt; Projekt, models.json, vibe.json, _logs/projekt.log und Sicherung erhalten“ |
| Tests: frische Installation | PASS | `install_program_files` | `FreshInstallTest.test_fresh_install_copies_all_program_modules_and_writes_version` (inkl. Übereinstimmungsprüfung Testabbild/`setup.PROGRAM_FILES`:178-185) |
| Tests: Update | PASS | Sperl-Sicherungspfad | `UpdateTest` (4 Tests) |
| Tests: abgebrochenes Update | PASS | Ausnahmebehandlung `791-815`, `_undo_install` `677-711`, `main` `1351-1368` | `AbortTest` (5 Tests, inkl. Fehlerinjektion `_copy_file`/`install_launcher`) |
| Tests: Rollback | PASS | `rollback`/`select_backup` | `RollbackTest` (7 Tests) |
| Tests: geänderte Nutzervorlagen | PASS | Backup-Aktion auf abweichende Vorlage | `UpdateTest.test_update_backs_up_program_and_user_template_and_keeps_runtime`; `test_reuse_keeps_user_templates_and_programs` |
| Tests: fehlende Rechte | PASS | Sicherungs/OSError-Pfad `766-771` | `AbortTest.test_backup_failure_is_reported_as_setup_error_and_changes_nothing`; `test_missing_permissions_do_not_leave_a_partial_install`; E2E Zielordner 0555 |
| Troubleshooting-Criterion Version-Abgleich | PASS | Viter | Verlängerung |

## Bereichstabelle
| Bereich | Ergebnis |
|---|---|
| Umfang (nur V-018, keine Änderung an verify.sh/verify.py/bestehenden Tests) | **NOT VERIFIED** — Git-Befehle nicht ausführbar; gemäß geliefertem Diff nur die 6 genannten Dateien |
| Testqualität (Assertions, Skips, Aufweichung) | PASS — keine Skips/Catch-alls gefunden, echte Assertions; Rot-Grün-Nachweise nur ausgeliefert |
| Datenverlustrisiken (backup.json, Rollback, Undo) | PASS mit 1 Medium (Reuse-Fehlerpfad) und 1 Minor |
| Pfadvalidierung (Traversal, Symlinks, Sicherung außerhalb) | PASS — `_safe_relative`/`_checked_paths` `603-621`, Resolve-Prüfung in `select_backup` `848-851` |
| Starter/Symlinks | PASS — nur eigener Symlink wird entfernt (`909-916`), Test vorhanden |

## Findings

- [Medium] `scripts/setup-vibe.py:703-705` — `_undo_install` löscht die bestehende `version.json` im `--reuse`-Fehlerpfad
  - Evidence: In `main` (1337-1351) wird `_undo_install` aufgerufen, sobald `install_program_files` erfolgreich war und ein späterer Schritt (`install_launcher`, `register_projects`) mit `SetupError`/`OSError` abbricht. Im `--reuse`-Modus auf einer bestehenden Installation ist `result["backup"]` None und `copied` leer; `_undo_install` entfernt dann aber bedingungslos `toolchain/version.json` (703-705) — die Versionskennung einer unangetasteten Installation geht verloren. Der Ausgabetext „Installation abgebrochen; nichts geändert“ (1365) ist damit unzutreffend. Kein Test deckt diesen Pfad ab (`AbortTest` prüft nur Update- und Frischinstallation).
  - Required fix: Fehlerpfad konkret mit begründeter Ausnahme reparieren: Version.json-Löschung an den Umfang binden, der der Lauf selbst geschrieben hat (Ergebnisflag aus `install_program_files` verwenden), und die Meldung „nichts geändert“ korrigieren; danach einen Regressionstest für `--reuse` auf bestehender Installation mit fehlgeschlagenem Starter nachziehen (zuerst rot sehen) und die Suite erneut laufen lassen.

- [Minor] `scripts/setup-vibe.py:936, 955` — Laufendsperre erkennt nur Standard-Laufzeitpfad und Profile prod/dev
  - Evidence: `running_installation` liest fest `vibe_root/_logs/runs.json` und prüft nur Sitzungen `vibe-ui`, `vibe-ui-dev`, `vibe-server`, `vibe-server-dev`. Die App erlaubt `VIBE_RUNTIME`/`VIBE_STATE` (bin/vibe_paths.py:54-55) und den Konfigurationsschlüssel `runtime` (bin/vibe_paths.py:315-317); beliebige Profile erzeugen `vibe-ui-<profil>` (bin/vibe.py:173-175). Solche Konfigurationen umgehen die Sperre stillschweigend. Der Fall ist in docs/features/V-018.md (Grenzen) für Umgebungsvariable und Profil bereits offengelegt, der config-`runtime`-Schlüssel fehlt dort.
  - Required fix: Nicht blockierend; für ein Folgepaket vorschlagen entweder dieselbe Pfadauflösung wie die App zu nutzen (einschließlich config-`runtime`) oder die Grenzen-Dokumentation um den Konfigurationsschlüssel zu ergänzen.

- [Minor] `scripts/setup-vibe.py:637-643` — Rollback-Fallback ohne `backup.json` spielt Kollisionsnamen mit zurück
  - Evidence: Ist `backup.json` fehlend oder korrupt, wird `backed_up` aus allen Dateien des Sicherungsordners rekonstruiert (639-643). Enthält der Ordner Kollisionskillvarianten aus `_backup_file` (`bin/vibe.1` etc.), würde der Rollback diese Dateien unter ihren unüblichen Namen in die Installation zurückschreiben. Nur bei manipuliertem/verlorenem Meta relevant; `_checked_paths` verhindert weiterhin Ausbrüche aus dem Ziel.
  - Required fix: Nicht blockierend; im Fallback Kollisionsnamen (Suffixmuster aus `_backup_file`) vom Wiedereinspielen ausschließen oder den Rollback bei korruptem Meta mit klarer Fehlermeldung abbrechen.

## Verification
- Change set reviewed: `95b36da..working tree` (Arbeitsbaum v018-implementation). Vollständiger Diff aus der Review-Eingabe (`/tmp/opencode/v18tmp/v018-review-input.md`) vollständig gelesen; Implementierung und Tests im Arbeitsbaum unabhängig per Dateilektüre abgeglichen (setup-vibe.py 350-1412, Tests vollständig, README/manifests-Delta aus dem Diff).
- Git commands run by me: **keine** — der Shell-Zugriff wurde von der Umgebung verweigert (`Permission denied: shell`); kein Git-Werkzeug im Code Mode-Katalog. Branch/HEAD nur über Git-Metadaten verifiziert (`.git/worktrees/v018-implementation/HEAD` → `feature/v-018-lifecycle`). Der Change-Satzumfang (keine Änderung an verify.sh/verify.py/anderen Tests) ist daher **nicht unabhängig verifiziert**; verify.sh wurde inhaltslich gesichtet (enthält keine V-018-Anteile), was eine Unverändertheit nicht belegt.
- Checks with supplied output: Lifecycle-Suite rot auf 95b36da (`failures=5, errors=29`), grün danach (`36 tests, OK`); quick (manifest, Syntax, Geheimnisse) und full (832+56 Tests) mit bwrap-Workspace-Begründung; vollständiger E2E-Lebenszyklus inkl. 0555-Abbruch und aktivem Lauf. Diese Ergebnisse stammen vom Implementierungsagenten; Rot-Grün konnte ich nicht selbst ausführen.
- Checks not independently run: alle Tests, verify.sh quick/full, Git-diff-Verifikation des Umfangs (Shell verweigert), SHA-256-Verifikation des Manifests.
- Important areas inspected: `scripts/setup-vibe.py` (Lebenszyklus, Sperre, Rollback-Pfadvalidierung, Uninstall, Undo), `tests/unit/test_install_lifecycle.py` (36 Tests, keine Skips, keine leer-Assertions), `bin/vibe_paths.py`/`bin/vibe.py`/`bin/vibe_runs.py` (Abgleich von Laufzeitpfad, Sitzungsnamen, `runs.json`-Format und LIVE-States), `docs/features/V-018.md`, `scripts/verify.sh`, Trilium-Note `DqlM21jFH8ET` (existiert, Titel stimmt mit trilium-index überein).
- Remaining risks: Reuse-Fehlerpfad (Finding 1, Medium) corruptiert die Versionskennung; Umfangsprofil des Change-Satzes offen; Abbruchszenarien sind teilweise über Fehlerinjektion statt echter Rechtefehler getestet (in den Grenzen dokumentiert).