# Arbeitsnotizen — Ticket-Nachweis zurückschreiben, ohne sie zu versionieren

Stand: 2026-11-08
Arbeitsbranch: `feature/worknotes-nachweis-sync`
Ausgangsstand: `5e0edfd`
Trilium: `wy5z26KCb7pI` unter „Features“ (`IjRpjYJTtqam`)

## Ziel

`FEEDBACK.md` und `TICKETS.md` sind Werk- und Laufzeitnotizen. Sie werden im
Datei-Editor oder über die vibe-Oberfläche gepflegt. Eine manuelle Änderung
darf den Lauf weder beim Start noch beim Abschluss blockieren. Gleichzeitig
muss der Paketabschluss weiterhin einen Nachweis (`[x]`, `Commit:`, `Test:`)
verlangen, sonst wird ein bereits erledigtes Paket endlos erneut gewählt.

## Ausgangslage und Ursache

- Preflight und Abschlussschranke prüften `git status --porcelain` ungefiltert.
  Solange die Notizen versioniert waren, blockierte jede manuelle Änderung mit
  „Arbeitsbaum ist nicht leer“.
- Nach dem Entfernen aus der Versionierung (`.gitignore`) enthält eine per
  `git worktree add` erzeugte Arbeitskopie die Notizen nicht mehr. Die Schranke
  prüfte aber weiterhin `[x]` und `Commit:`/`Test:` in der Arbeitskopie.
- Der Agent markierte notgedrungen in der Arbeitskopie; nach dem Merge und dem
  Entfernen der Arbeitskopie war der Nachweis verloren. Im Projektordner blieb
  das Paket offen und wurde im nächsten Lauf erneut gewählt. Jeder neue Lauf
  verlangte wegen der gewachsenen Basis einen neuen Commit und verbrauchte
  erneut Kontingent, bis der Lauf mit „Quota/Kontingent …“ abbrach.

## Fachliches Verhalten

- Die beiden Notizen sind Laufzeitstand. Der Läufer trägt sie in
  `.git/info/exclude` ein, damit unversionierte Notizen nicht im Git-Status
  erscheinen. Ein späteres `git add` bleibt möglich.
- Preflight und Abschlussschranke filtern beide Notizpfade aus dem
  Git-Status. Änderungen an anderen Dateien blockieren unverändert.
- Vor jedem Versuch kopiert der Läufer vorhandene Notizen in die Arbeitskopie
  (`copy-notes`). Agent und Schranke sehen damit den aktuellen Ticketstand.
  Fehlt eine Notiz im Projekt, wird sie nicht angelegt.
- Nach bestandener Schranke und erfolgreichem Merge schreibt der Läufer den
  Nachweis in den Projektordner zurück (`sync-proof`), bevor die Arbeitskopie
  entfernt wird:
  - Checkbox des Paketblocks auf `[x]`,
  - Nachweiszeilen (`Commit:`, `Test:`, `Datei:`, `Review:`, `Doku:`) werden
    durch die Angaben aus der Arbeitskopie ersetzt.
- Andere Blöcke, Beschreibungen und manuelle Zeilen bleiben unverändert.
  Mehrfaches Ausführen ändert nichts (idempotent).
- Der Nachweis wird verweigert, wenn der Block in der Arbeitskopie nicht
  abgehakt ist, der Nachweis-Commit fehlt oder `Test:`/`Datei:` fehlt. Dann
  bleibt die Projektnotiz unverändert und der Lauf blockiert mit klarer
  Meldung.

## Technische Umsetzung

- `bin/vibe_packages.py`
  - `WORK_NOTE_FILES`, `is_work_note_path`, `dirty_report`: gefilterter
    Git-Status für Preflight und Schranke.
  - `ensure_project_exclude`: ergänzt `.vibe/tmp/`, `FEEDBACK.md` und
    `TICKETS.md` in `.git/info/exclude`.
  - `copy_work_notes`, `block_span`, `_apply_proof`, `sync_proof` sowie die
    CLI-Befehle `copy-notes` und `sync-proof`.
- `bin/vibe-run.sh`
  - `copy-notes` direkt nach dem Anlegen der Arbeitskopie.
  - `merge_and_cleanup` in `merge_package`, `sync_work_notes`,
    `cleanup_worktree` getrennt; der Nachweis wird nach dem Merge und vor dem
    Entfernen der Arbeitskopie geschrieben.
- `docs/import-manifest.json`: Prüfsummen der beiden geänderten
  Programmdateien aktualisiert (vorgeschriebene Begründung: beabsichtigte
  Änderung an importierten Programmdateien).

## Grenzen

- Sind die Notizen versioniert **und** im Projektordner lokal geändert, blockiert
  bereits die Prüfung des Integrationsstands im Läufer (`bin/vibe-run.sh`,
  `git -C "$P" status --porcelain`), unabhängig von Preflight und Schranke.
  Empfohlen bleibt deshalb der unversionierte Betrieb; der Statusfilter in
  Preflight und Schranke deckt zusätzlich den versionierten Fall ab, solange
  der Integrationsstand sauber ist.
- Ein bereits vor dieser Änderung gemergtes, aber nicht abgehaktes Paket wird
  nicht rückwirkend automatisch nachgetragen. Es muss einmalig von Hand
  abgehakt werden. Für künftige Fälle erkennt die Abschlussschranke seit
  V-023 ein bereits integriertes Paket (Nachweis-Commit als Vorfahre der
  Basis) und der Läufer trägt den Nachweis per `sync-proof` nach
  (`docs/features/V-023.md`).
- Die Änderung wirkt erst nach der Installation im Produktivstand
  (`_toolchain`); das Repository selbst ist der Entwicklungsstand.

## Prüfungen

- `python3 -m unittest discover -s tests/unit -p 'test_worknotes_sync.py' -v`
  — 19 Tests, grün. Herkunft und Rotphase: siehe
  `docs/reviews/worknotes-nachweis-sync-test-agent-report.md`.
- `bash scripts/verify.sh quick` — grün (Manifest, Syntax, Geheimnisse).
- `bash scripts/verify.sh full` — 1089 Unit-Tests, 1 Fehlschlag
  (`test_ap04_setup_harness.test_dry_run_explains_pi_and_its_install_command`),
  am Ausgangsstand `5e0edfd` identisch reproduziert (Bestandsfehler).
- `python3 -m unittest discover -s tests/browser` — 82 Tests, 2 Fehlschläge
  (`test_write_dirs_ui`, `test_central_workflows_ui`), am Ausgangsstand
  identisch reproduziert (Bestandsfehler).

## Dokumentation

- Diese Datei.
- Test-Agenten-Bericht: `docs/reviews/worknotes-nachweis-sync-test-agent-report.md`.
- Reviews: `docs/reviews/worknotes-nachweis-sync-review-1.md` und
  `docs/reviews/worknotes-nachweis-sync-review-2.md`.
- Trilium: `wy5z26KCb7pI` unter „Features“ (`IjRpjYJTtqam`).
