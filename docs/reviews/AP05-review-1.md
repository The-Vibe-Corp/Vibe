# AP05 — Review 1

Stand: 2026-11-07
Branch: `feature/runner-abschluss-gates`
Geprüfter Stand: `7276b8e8df7fa70916cdfbfe8c30b22e7e7004fe`
Nachbesserung: `9b8639b8ed6c60477a2300ba6ca17b4f7ef42a9b`

## Ergebnis

Erste Runde: **CHANGES REQUIRED** (0 Critical, 2 High, 4 Medium, 3 Minor).
Nachbesserung und gezielte Nachprüfung: **PASS** (0 Critical, 0 High,
0 Medium, 0 Minor).

## Befunde der ersten Runde und Behandlung

### High

1. **Fehlgeschlagenes Anlegen einer Arbeitskopie ließ ein Verzeichnis
   zurück.**
   Behoben in `bin/vibe-run.sh`: Bei einem Fehler von `git worktree add` wird
   das zuvor angelegte `mktemp`-Verzeichnis entfernt und `git worktree prune`
   ausgeführt. Neuer Test:
   `test_failed_worktree_creation_leaves_no_directory`.

2. **Verschmutzter Integrationsstand wurde erst am Laufende erkannt.**
   Behoben in `bin/vibe-run.sh`: Der Paket-Loop prüft vor jedem Paket
   `git -C "$P" status --porcelain` und blockiert bei Änderungen. Neuer Test:
   `test_dirty_integration_tree_between_packages_blocks`.

### Medium

1. **Preflight-Meldung nannte die zu bearbeitende Datei nicht.**
   Behoben in `bin/vibe_packages.py`: Die Meldung nennt jetzt
   `.vibe/project.env` und das Ersetzen von `TODO`. Der Test
   `test_missing_package_check_is_rejected` prüft den Dateinamen.

2. **Mehrere Reviews: ein altes PASS konnte einen neueren Einwand
   überdecken.**
   Behoben in `bin/vibe_packages.py`: `review_order` sortiert numerisch; das
   jüngste Review entscheidet. Neue Tests:
   `test_newer_review_without_pass_blocks_an_older_pass` und
   `test_newer_pass_after_an_older_failure_is_accepted`.

3. **Branch-Namen konnten bei sehr schnellen Läufen kollidieren.**
   Behoben in `bin/vibe-run.sh`: Der Branch-Name enthält jetzt Nanosekunden,
   PID und `$RANDOM`.

4. **Protokollrotation während der Fehlerklassifikation.**
   Bewertet und akzeptiert: Die Rotation läuft ausschließlich vor dem Start
   des Laufs, nicht zwischen Agentenaufruf und Klassifikation. Kein
   zusätzlicher Code nötig.

5. **Kein ausdrücklicher Test für den gemeinsamen Git-Ordner einer
   Arbeitskopie.**
   Behoben: `test_bwrap_arguments_bind_the_shared_git_dir_of_a_worktree` prüft
   die Schreibfreigabe in den bubblewrap-Argumenten.

### Minor

- `VERDICT_PATTERN` erkennt `PASS` korrekt und nicht `PASSING`; keine Änderung.
- Der Agenten-Prompt nennt `TICKETS.md`/`FEEDBACK.md` und `[x]` bereits
  ausdrücklich; keine Änderung.
- Vorlagen behalten `VERIFY_PACKAGE="echo TODO"` bewusst als
  Konfigurationspflicht; die Preflight-Meldung erklärt jetzt den nächsten
  Schritt.

## Prüfungen

- `python3 -m unittest discover -s tests/unit` — 1007 Tests, alle grün.
- `bash scripts/verify.sh quick` — Exit 0.
- Gezielte Module: `tests.unit.test_package_gates` (33 Tests),
  `tests.unit.test_runner_package_gates` (12 Tests).
- `bash scripts/verify.sh full` — siehe Abschlussbericht des Arbeitspakets.

## Grenzen

- Der unabhängige Test-Agent `test-agent` war in dieser Umgebung nicht
  aufrufbar (`permission.rejected`). Die Tests wurden vom Umsetzungsagenten
  geschrieben; diese Grenze ist offen dokumentiert.
- Der F19-Browsertest bleibt offene Folgearbeit.
