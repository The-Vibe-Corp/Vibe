# Review AP11 — Runde 1

- Datum: 2026-11-11
- Reviewer: code-reviewer (unabhängiger Subagent), Session `ses_e36ffb53cffeMWEXQVbiG4Cw4f`
- Umfang: `9284ae3..18209ae` (Implementierungs-Commit `18209ae`), Ausgangscommit `9284ae3`
- Ticket: TICKETS.md AP11 „Priorisierung der Abarbeitungsreihenfolge"
- Arbeitskopie: sauber (`git status --short` leer), HEAD = 18209ae

Der folgende Report ist unverändert übernommen (Antwort des Reviewers).

---

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 4
- Verdict: PASS

## Acceptance criteria

| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Reihenfolge je Projekt einstellbar (PACKAGE_ORDER in `.vibe/project.env`, Trenner Komma/Semikolon/Leerraum, Dubletten reduziert) | PASS | `bin/vibe_packages.py:407-422` (package_order), `bin/vibe_packages.py:1016-1045` (normalize_order), Ablage `bin/vibe:919-940` (cmd_priority → set_env_values), `bin/vibe-web.py:1069-1090` (POST /api/priority), `bin/web/app.js:740-782` (priorityBody) | `tests/unit/test_ap11_priority.py` — `PriorityCommandLineTest.test_cli_priority_set_writes_package_order_and_preserves_lines` (inkl. CRLF/Kommentar-Erhalt, byte-genau), `test_cli_priority_set_reduces_duplicates_silently`, `test_cli_priority_set_rejects_unknown_ids_without_change`; Browser: `tests/browser/test_ap11_priority_ui.py::test_save_writes_package_order_and_clear_empties_it`; gelieferte Laufausgaben: 23/23 bzw. 4/4 OK |
| Priorisierung verbindlich für Agentenläufe (schlägt Quellen-/Prioritätsordnung; Läufer meldet verbindliche Wahl) | PASS | `bin/vibe_packages.py:452-527` (select_package: Priorisierungsvorrang, `ordered`-Feld), `bin/vibe-run.sh:206-208` (ORDERED), `bin/vibe-run.sh:600-602` (Protokollzeile) | `test_package_order_beats_source_order_and_priority_fields`, `test_ordered_selection_is_marked_in_the_state`, `RunnerCommandTest.test_select_command_honors_the_package_order`; Protokollzeile gegen `bin/vibe-run.sh` geprüft |
| Erledigte Aufgaben werden der Priorisierung entnommen | PASS | `bin/vibe_packages.py:489-500` (`_ready` → done/blocked/deps übersprungen), Ansicht `bin/vibe_packages.py:967-1013` (Status „erledigt"), `bin/vibe:930-936` (Kennzeichnung „erledigt — der Priorisierung entnommen"), kein Lauf-Schreibzugriff auf project.env | `test_done_entries_are_removed_from_the_priority`, `test_a_done_first_entry_never_becomes_the_choice`; Browser-API: `test_priority_api_reports_configured_effective_and_status` (T0 erledigt, queue ohne T0) |
| Ohne Priorisierung unverändertes Verhalten | PASS | `bin/vibe_packages.py:501-514` (Rückfall auf Standardordnung) | `test_without_configuration_tickets_are_selected_before_feedback`, `test_without_configuration_the_priority_field_orders_tickets`, `test_without_configuration_file_order_decides_within_priority`, `test_without_configuration_state_is_not_marked_as_ordered`, `test_cli_priority_clear_empties_and_falls_back` |
| Auswahlstand `next-package.json` mit `ordered` | PASS | `bin/vibe_packages.py:519-527`, `bin/vibe-run.sh:206-208` | `test_ordered_selection_is_marked_in_the_state`, `test_without_configuration_state_is_not_marked_as_ordered`, `RunnerCommandTest.test_select_command_honors_the_package_order` |
| Bedienung CLI `vibe priority` / Dashboard-Abschnitt / API GET/POST | PASS | `bin/vibe:919-940,5245` (Dispatch), `bin/web/app.js:192-226,740-782` (Chip `data-goto="priorisierung"`, `details#settings-priorisierung`), `bin/vibe-web.py:649-652,704,1069-1090`, `bin/vibe_services.py:163-180` (message-Feld) | CLI: `PriorityCommandLineTest` (6 Fälle); Dashboard/API: `test_priority_section_is_details_with_data_goto_chip`, `test_priority_section_shows_the_effective_order`, `test_priority_api_reports_configured_effective_and_status` |
| Dokumentation (Repo + Trilium) | PASS | `docs/features/AP11.md` (fachlich + Entscheidungen + Prüfungen), `docs/baseline.md:175,248-249`, `docs/import-manifest.json:694-705` | Trilium-Note `KrGYItU1tR0u` von mir über MCP gelesen: Titel „AP11 Priorisierung der Abarbeitungsreihenfolge", Labels project=vibe / arbeitspaket=AP11 / branch stimmen; Eintrag in `docs/trilium-index.md:56` |

## Findings

- [Minor] `docs/import-manifest.json:707-718` — doppelter AP11-Änderungseintrag
  - Evidence: Der Eintrag ab Zeile 707 ist inhaltlich identisch mit dem Eintrag ab Zeile 694 (gleiche dateien, datum, grund; nur die Schlüsselreihenfolge unterscheidet sich). Das vermutlich versehentlich doppelt erzeugte Manifestfeld verwässert die Änderungshistorie; `check-import-manifest.py` meldet laut geliefertem Ergebnis trotzdem OK.
  - Required fix: Den redundanten AP11-Eintrag (Z. 707-718) aus dem Manifest entfernen und `python3 scripts/check-import-manifest.py` erneut ausführen.
- [Minor] `bin/vibe_packages.py:967-1013` — priority_view berechnet die Warteschlange durch N+1 vollständige Neuwahlen
  - Evidence: Pro offenem Paket wird `select_package` erneut ausgeführt; jeder Aufruf liest TICKETS/FEEDBACK und project.env neu und führt `done_ids`/`proof_ok` inkl. Git-Subprozessen (`commit_exists`) erneut aus. Bei Projekten mit vielen erledigten Paketen entsteht quadratischer Aufwand pro Dashboard-Laden. Die iterierende Wiederverwendung der Läuferlogik ist eine nachvollziehbare Richtigkeitsentscheidung (dokumentiert in AP11.md:52), daher nur Hinweis, kein Blocker.
  - Required fix: Bei beobachtbarer Verzögerung die Warteschlange in einem Durchlauf ableiten oder `done_ids`/`package_order` pro Aufruf wiederverwenden; nicht vorsorglich optimieren (KISS).
- [Minor] `docs/trilium-index.md:54-55` — AP8-/AP9-Indexzeilen im AP11-Commit
  - Evidence: Die Zeilen für AP8 (`RtG0XQF3SqMN`) und AP9 (`RZaerCNe9ngJ`) wurden erst im Commit 18209ae ergänzt, gehören inhaltlich aber zu den bereits committeten Vorpaketen; der AP11-Commit enthält damit Nachweisdokumentation fremder Arbeitspakete (AGENTS.md: „Commit enthält ausschließlich dieses Arbeitspaket und dessen Nachweise"). Als verspätete Synchronisierung nachvollziehbar, aber nicht im Paketumfang begründet.
  - Required fix: Künftig Verspätungen der Trilium-Indexpflege als eigenen Doku-Commit oder mit klarem Hinweis in der Commit-Meldung ablegen; hier keine Rücknahme erforderlich.
- [Minor] Trilium-Note `KrGYItU1tR0u` — Status-Label „abgeschlossen" vor Reviewabschluss
  - Evidence: Die von mir gelesene Note trägt das Label `status=abgeschlossen`, obwohl die unabhängige Abnahme (dieses Review) zum Zeitpunkt des Schreibens noch offen war; AGENTS.md sieht das Abhaken erst nach finalem PASS vor.
  - Required fix: Status-Label der Note auf den tatsächlichen Prozessstand setzen (z. B. „in Review") und erst nach dem finalen PASS auf „abgeschlossen" zurückstellen.

## Verification

- Change set reviewed: `9284ae3..18209ae` (Arbeitsbaum sauber, `git status --short` leer; HEAD = 18209ae). Keine Materialien fehlten; TICKETS.md AP11 und SPEC.md im Worktree gelesen — SPEC.md enthält keine abweichende Priorisierungsregel, das Ticket ist die fachliche Grundlage.
- Git commands run by me: `git status --short`, `git log --oneline -5`, `git diff 9284ae3..18209ae --stat` sowie Datei-Diffs für alle 12 geänderten Dateien, `git log --all -- tests/unit/test_ap11_priority.py` (Testdatei existiert nur in 18209ae).
- Checks with supplied output (vom Coding-Agenten geliefert, von mir nicht ausführbar/nicht ausgeführt): `bash scripts/verify.sh quick` Exit 0; `python3 -m unittest tests.unit.test_ap11_priority` 23/23 OK; `tests.browser.test_ap11_priority_ui` 4/4 OK; `verify.sh full` 1486 Tests / 5 paketfremde Baseline-Fehlschläge, am Ausgangscommit 9284ae3 identisch; `python3 scripts/check-import-manifest.py` OK (57 Dateien). Rotphase (15 rot / 8 grün; 4 rot Browser) nur dokumentiert, nicht beobachtbar (Testdateien liegen nur im Finalcommit vor).
- Checks not independently run: alle Build-, Test-, Manifest- und Syntaxprüfungen.
- Independently verified by me: vollständiger Diff gegen Ticket/SPEC (nur AP11-Umfang, keine Neuimplementierung, keine Testabschwächung erkennbar — Tests Assertivität und Negativfälle beachten, Skip-Marker fehlen, Assertions nicht leer); Authentifizierung des neuen Endpunkts (Token-Guard `bin/vibe-web.py:549-561`, `known(name)` bei GET und POST); atomare Ablage über `set_env_values` mit ConcurrentChangeError-Behandlung (409); Trilium-Note per MCP gelesen (Existenz, Titel, Labels bestätigt).
- Important areas inspected: `bin/vibe_packages.py` (package_order, select_package, priority_view, normalize_order), `bin/vibe` (cmd_priority, set_env_values, read_env-Semantik), `bin/vibe-run.sh` (select_item/ORDERED), `bin/vibe-web.py`, `bin/vibe_services.py`, `bin/web/app.js`, beide Testdateien vollständig, `docs/features/AP11.md`, Manifest, Baseline-/Trilium-Index.
- Remaining risks: Testautorenschaft (Test-Agent) und die gelieferten Test-/Verifizierungsergebnisse sind dokumentiert, aber nicht aus Git allein beweisbar (keine separaten Test-Commits); die 5 Baseline-Fehlschläge von `verify.sh full` sind als paketfremd und ausgangsidentisch dargestellt — ich habe dies nur über die gelieferten Ergebnisse und AP9.md/AP11.md abgeglichen, nicht selbst ausgeführt. Handeditierte `PACKAGE_ORDER`-Werte mit Inline-Kommentaren würden zusätzliche unbekannte Tokens erzeugen (werden still übersprungen, kein Funktionsfehler).

Verdict begründet: Alle Akzeptanzkriterien sind mit Implementierung und Testnachweisen (gelieferte Läufe + von mir geprüfte Testinhalte) belegt; es liegen ausschließlich Minor-Befunde ohne Blockerwirkung vor. TICKETS.md AP11 ist korrekt weiterhin ungehakt; Commit 18209ae enthält ausschließlich Arbeitspaket- und Nachweisdateien.
