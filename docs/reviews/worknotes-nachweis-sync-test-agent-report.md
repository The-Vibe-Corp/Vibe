# Test-Agenten-Bericht: worknotes-nachweis-sync

Stand: 2026-11-08
Rolle: unabhängiger Test-Agent (`TESTER=test-agent` gemäß `.vibe/project.env`)
Arbeitspaket: Ticket-Nachweis aus der Arbeitskopie in den Projektordner zurückschreiben, ohne die Arbeitsnotizen zu versionieren

## Testdatei und Testbefehl

- **Testdatei:** `tests/unit/test_worknotes_sync.py`
- **Testbefehl:**

```bash
python3 -m unittest discover -s tests/unit -p 'test_worknotes_sync.py' -v
```

Die Tests verwenden echte temporäre Git-Repositories und echte
`git worktree`-Arbeitskopien über `tests/unit/runner_support.py`. Es werden
keine Modellaufrufe, keine Netzverbindungen und keine Router-/MCP-Aufrufe
ausgeführt.

## Testfälle

### A1 – Preflight ignoriert Arbeitsnotizen (`PreflightWorkNotesTest`)

| Testname | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|
| `test_modified_versioned_work_notes_do_not_block_the_preflight` | `FEEDBACK.md`/`TICKETS.md` sind versioniert und sauber | Beide Notizen manuell ändern, `preflight_errors` aufrufen | Keine Fehler (`[]`) |
| `test_modified_other_versioned_file_still_blocks_the_preflight` | Notizen und weitere Datei sind versioniert | Notizen und `notiz.txt` ändern | Fehler „Arbeitsbaum“ nennt `notiz.txt`, aber nicht die Notizdateien |
| `test_untracked_work_notes_do_not_block_the_preflight` | Notizen sind aus dem Git-Index entfernt, liegen aber im Projekt | Beide Notizen ändern | Keine Fehler (`[]`) |
| `test_untracked_other_file_still_blocks_the_preflight` | Notizen sind unversioniert | Notizen ändern und `unfertig.txt` anlegen | Fehler nennt `unfertig.txt`, aber nicht die Notizdateien |

### A2 – Abschlussschranke ignoriert Notizen in der Arbeitskopie (`GateWorkNotesTest`)

| Testname | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|
| `test_modified_tracked_notes_do_not_dirty_the_workcopy` | Vollständiges Paket in echter Arbeitskopie, Notizen versioniert | `FEEDBACK.md`/`TICKETS.md` nachträglich ändern | `gate_errors(...) == []` |
| `test_modified_other_file_still_dirties_the_workcopy` | Vollständiges Paket | Notizen und `impl-F1.txt` ändern | Fehler „sauber“ nennt `impl-F1.txt`, nicht die Notizen |
| `test_untracked_notes_do_not_dirty_the_workcopy` | Notizen unversioniert, Arbeitskopie ohne Notizen | Notizen als unversionierte Dateien anlegen/ändern | `gate_errors(...) == []` |
| `test_untracked_other_file_still_dirties_the_workcopy` | Notizen unversioniert | Notizen anlegen und `offen.txt` ergänzen | Fehler nennt `offen.txt`, nicht die Notizen |

### A3 – `copy-notes` (`CopyNotesCommandTest`)

| Testname | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|
| `test_both_existing_notes_are_copied_unchanged` | Projekt mit vorhandenen Notizen, echte Arbeitskopie ohne Notizen | `copy-notes --project P --worktree WT` | Exit 0; beide Dateien in der Arbeitskopie, Inhalt identisch |
| `test_a_note_missing_in_the_project_is_not_created` | `TICKETS.md` fehlt im Projekt, `FEEDBACK.md` vorhanden | `copy-notes` ausführen | Exit 0; `TICKETS.md` wird nicht angelegt, `FEEDBACK.md` wird kopiert |

### A4 – `sync-proof` (`SyncProofCommandTest`)

| Testname | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|
| `test_checkbox_and_proof_lines_reach_the_project_block` | Projektblock `F1` offen; Arbeitskopieblock `F1` auf `[x]` mit `Commit:`, `Test:`, `Review:`, `Doku:` | `sync-proof --project P --worktree WT --id F1` | Exit 0; Projektblock wird `[x]`, alle vier Nachweiszeilen stehen im Projektblock |
| `test_other_blocks_and_manual_changes_stay_untouched` | Projekt hat weitere Blöcke, manuelle Notizzeile, alte Nachweise und Nachbemerkung | `sync-proof` für `F1` | `F2` und manuelle Zeilen unverändert; alte Nachweise ersetzt; `TICKETS.md` unverändert |
| `test_the_command_is_idempotent` | Gültiger Sync-Stand | `sync-proof` zweimal ausführen | Beide Läufe Exit 0; Dateien nach dem zweiten Lauf identisch zum Stand nach dem ersten Lauf |

### A5 – Verweigerungsfälle (`SyncProofCommandTest`)

| Testname | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|
| `test_an_unchecked_block_in_the_workcopy_is_refused` | Arbeitskopieblock `F1` ist `- [ ]`, Nachweiszeilen vorhanden | `sync-proof` für `F1` | Fehler-Exit; Projektdatei unverändert |
| `test_an_incomplete_proof_is_refused` | Arbeitskopieblock `F1` ist `[x]`, aber ohne Nachweiszeilen | `sync-proof` für `F1` | Fehler-Exit; Projektdatei unverändert |
| `test_a_missing_block_aborts_without_changing_the_project` | Arbeitskopie enthält nur Block `F2`, Projekt enthält `F1` | `sync-proof` für `F1` | Fehler-Exit; Projektdatei unverändert |
| `test_a_block_missing_in_the_project_is_refused` | Arbeitskopieblock `F1` ist abgehakt und vollständig, Projekt enthält nur `F2` | `sync-proof` für `F1` | Fehler-Exit; Projektnotiz unverändert |
| `test_a_proof_commit_unknown_to_the_project_is_refused` | Arbeitskopieblock `F1` ist abgehakt, nennt aber `Commit: deadbee`, das das Projekt-Repository nicht kennt | `sync-proof` für `F1` | Fehler-Exit; Projektnotiz unverändert |

### A6 – Isolierte Testumgebung

Alle Tests verwenden echte temporäre Git-Repositories und echte Arbeitskopien
über `runner_support`. Es gibt keine Attrappen, die das fachliche Verhalten
ersetzen. Externe Dienste, Modelle und Netzverbindungen werden nicht
verwendet.

### A7 – Läufer-Verdrahtung (`RunnerWorkNotesTest`)

| Testname | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|
| `test_runner_copies_notes_and_writes_the_proof_back` | Projektnotizen sind unversioniert, `F1` ist offen; echte Installation und nachgebildeter Agent über `runner_support` | `bash bin/vibe-run.sh <projekt>` mit `VIBE_MAX_PACKAGES=1` | Exit 0; Projekt-`FEEDBACK.md` enthält `[x] F1` und die Nachweiszeilen; Code und Feature-Doku sind gemergt; Arbeitskopie und Paketbranch sind entfernt; Notizen bleiben unversioniert |

## Belegte Rotphase vor der Implementierung

Diese Rotphase wurde vor der Implementierung mit den ursprünglich 17 Tests
ausgeführt. Die beiden nachgezogenen Verweigerungstests
(`test_a_block_missing_in_the_project_is_refused`,
`test_a_proof_commit_unknown_to_the_project_is_refused`) wurden erst nach der
Implementierung ergänzt; sie setzen den Befehl voraus und wären vor der
Implementierung bereits an der Verfügbarkeitsprüfung (`sync-proof --help`)
fehlgeschlagen.

**Befehl:**

```bash
python3 -m unittest discover -s tests/unit -p 'test_worknotes_sync.py' -v
```

**Exit-Code:** `1`

**Ergebnis:** `Ran 17 tests` → `FAILED (failures=17)`

Auszug der Fehlschläge:

```text
FAIL: test_modified_versioned_work_notes_do_not_block_the_preflight
AssertionError: Lists differ:
['Arbeitsbaum ist nicht leer:\nM FEEDBACK.md\n M TICKETS.md'] != []

FAIL: test_modified_tracked_notes_do_not_dirty_the_workcopy
AssertionError: Lists differ:
['Arbeitskopie ist nicht sauber:\nM FEEDBACK.md\n M TICKETS.md'] != []

FAIL: test_both_existing_notes_are_copied_unchanged
AssertionError: 2 != 0 : ... invalid choice: 'copy-notes'
  (choose from 'select', 'preflight', 'gate', 'classify', 'status')

FAIL: test_checkbox_and_proof_lines_reach_the_project_block
AssertionError: 2 != 0 : ... invalid choice: 'sync-proof'
  (choose from 'select', 'preflight', 'gate', 'classify', 'status')

FAIL: test_runner_copies_notes_and_writes_the_proof_back
AssertionError: 2 != 0 : BLOCKIERT: Arbeitsbaum ist nicht leer:
?? FEEDBACK.md
?? TICKETS.md
ABBRUCH: Preflight nicht bestanden. Es wurde kein Arbeitspaket gestartet.
```

Die Fehlschläge beruhten auf fehlender Funktionalität, nicht auf Syntax- oder
Umgebungsfehlern.

## Ergebnis nach der Implementierung

**Befehl:**

```bash
python3 -m unittest discover -s tests/unit -p 'test_worknotes_sync.py' -v
```

**Exit-Code:** `0`

**Ergebnis:** `Ran 19 tests in 1.789s` → `OK`

Auszug:

```text
test_a_block_missing_in_the_project_is_refused ... ok
test_a_proof_commit_unknown_to_the_project_is_refused ... ok
test_runner_copies_notes_and_writes_the_proof_back ... ok
...
Ran 19 tests in 1.789s

OK
```

## Herkunft und Autorenschaft

- Die Testdatei `tests/unit/test_worknotes_sync.py` wurde ausschließlich vom
  unabhängigen Test-Agenten erstellt und gepflegt.
- Die Testfälle wurden aus Arbeitspaket, `SPEC.md`, `AGENTS.md` und
  `.vibe/project.env` abgeleitet, nicht aus dem Implementierungsdiff.
- Der Test-Agent hat keine Produktionsdateien, Build-Dateien oder
  Prüfskripte geändert.
- Die beiden nachgezogenen A5-Tests entstanden auf Review-Beanstandung. Sie
  prüfen gezielt das Fehlen des Zielblocks im Projekt und einen im
  Projekt-Repository unbekannten Nachweis-Commit.
- Die Tests enthalten keine Attrappen, die das fachliche Verhalten ersetzen.
  Der nachgebildete Agent in A7 ist ein Testwerkzeug; die eigentliche
  Git-/Datei-Interaktion läuft gegen echte Repositories.

## Verbleibende Lücken

- Die Vollständigkeitsdefinition des Nachweises wird derzeit über
  `Commit:` plus `Test:`/`Datei:` geprüft. Ein teilweiser Nachweis, bei dem
  nur `Review:` oder `Doku:` fehlt, wird nicht separat getestet.
- Der A7-End-to-End-Test verwendet den vorhandenen nachgebildeten Agenten, der
  `Commit:` und `Test:` schreibt. Die Übertragung von `Review:` und `Doku:`
  wird durch die A4-Tests mit vollständigen Nachweiszeilen abgedeckt.
- Es wurde ausschließlich die genannte Testdatei ausgeführt. Die vollständige
  Unit-/Browser-Suite ist Aufgabe der übergreifenden Abnahme.
