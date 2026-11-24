# GH-47 — Test-Agent-Bericht (unabhängige Testvorbereitung)

- Arbeitspaket: GH-47 „Improve Github Issues support“
- Repository/Worktree: `/var/log/custom/vibe-dev/worktrees/vibe-GH-47-UNiWBp`
- Branch: `feature/korbat/gh-47`, Ausgangscommit `07e7ff1`
- Rolle: unabhängiger Test-Agent; nur `tests/**` und dieser Bericht geändert.
- Produktcode (`bin/`, `templates/`, `scripts/`, `docs/features`, `SPEC.md`, `TICKETS.md`) unberührt; keine Commits, kein Branchwechsel.
- Stand: Tests vor der Implementierung geschrieben und am Ausgangsstand tatsächlich ausgeführt (Rotphase dokumentiert). Die Implementierung war zum Zeitpunkt aller Läufe noch der alte Produktstand.

## 1. Ableitungsquellen

- `TICKETS.md`, GH-47 (drei Buttons, unklare Fehlermeldungen, Löschen/Text-Sync, nur lauffähige Tickets).
- `SPEC.md` (Ticketspeicher `.vibe/tickets.json`, Zustände ohne GitHub, Qualität/Abnahme, Sicherheit/Datenintegrität).
- Verbindliche Nutzerentscheidungen, jeweils **Option A**:
  - **q8907138c500b**: Löschen eines verbundenen Tickets schließt das GitHub-Issue best effort (PATCH `state=closed`); bei REST-Fehlschlag bleibt das lokale Löschen bestehen, die Issue-Nummer wird als Tombstone (`github_deletions`) vermerkt, der Sync versucht das Schließen erneut.
  - **q9a10d0cf6e7f**: Bei beidseitiger Textänderung seit dem letzten Sync gewinnt die lokale Fassung (Push); der Konflikt wird gezählt.
  - **q6cbba05d8ca9**: Genau EIN Sync-Button; „Issues laden“/„Issues importieren“ entfallen in Nova, Classic, Web-API (`issues`, `import`), CLI (`issues`, `issues-import`) und Produktcode (`github_issues`, `github_issues_import`, `vibe_github.import_issues_into_tickets`); `vibe_github.list_issues` bleibt.
- Koordinator-Nachträge aus der laufenden Sitzung:
  - exakte Statistikschlüssel: `created`, `updated`, `closed`, `pushed`, `text_pushed`, `text_pulled`, `conflicts`, `closed_remote`.
  - Nova-DOM-Vertrag: `select[data-nv-ticket-state-select]` mit `draft|open|in-progress`, Button `[data-nv-action='ticket-state-save']`, POST `{action:'state', id, state}` an `/api/ticket` bzw. `/api/feedback`; done-Tickets ohne Zustandswahl.
  - Delete-API bei Close-Fehlschlag: `ok` bleibt wahr; Meldung nennt Fehlschlag und erneuten Sync-Versuch.

## 2. Geänderte und neue Dateien

Neu:

1. `tests/unit/test_gh47_issues_backend.py`
2. `tests/unit/test_gh47_surfaces.py`
3. `tests/browser/test_gh47_issues_ui.py`
4. `docs/reviews/GH-47-test-agent-report.md` (dieser Bericht)

Bewusst angepasst:

5. `tests/unit/test_ap3_korbat_issues_backend.py`
6. `tests/unit/test_ap3_korbat_surfaces.py`
7. `tests/unit/test_gh48_tickets_surface.py`
8. `tests/unit/test_ap06_github.py`
9. `tests/unit/test_ap5_korbat_waiting_state.py`
10. `tests/unit/test_ap11_priority.py`
11. `tests/browser/test_ap22_project_ui.py`
12. `tests/browser/test_f33_project_ui.py`

Testinfrastruktur in Bestandsmodulen: Der Loopback-Fake in `test_ap3_korbat_issues_backend.py` verarbeitet PATCH jetzt zusätzlich `title`/`body` und kann per `httpd.fail_patch_numbers` gezielt 403 liefern. Damit sind Text-Sync und Best-effort-Close ohne echtes Netz prüfbar.

## 3. Neue Testfälle

### 3.1 `tests/unit/test_gh47_issues_backend.py` (17 Fälle)

Run: `python3 -m unittest tests.unit.test_gh47_issues_backend -v`

**`StatsContractTest`**
- `test_sync_statistics_use_the_contract_keys` — Vor: Remote-Ready-Issue. Aktion: `sync_issues`. Erwartet: exakt die acht Vertragsschlüssel, alle ganzzahlig.

**`TombstoneSyncTest` (q8907138c500b)**
- `test_failed_close_keeps_tombstone_and_does_not_recreate_the_issue` — Vor: Remote 101 offen, PATCH scheitert, 102 ready; Tombstone 101. Aktion: Sync. Erwartet: kein GH-101, GH-102 entsteht, Tombstone bleibt, `closed_remote == 0`; kein Abbruch.
- `test_successful_retry_closes_the_issue_and_drops_the_tombstone` — Vor: Remote 101 offen, Tombstone 101. Aktion: Sync. Erwartet: Issue geschlossen, Tombstone entfernt, kein GH-101, `closed_remote == 1`.
- `test_tombstone_drops_for_already_closed_or_missing_issues` — Vor: Tombstones 103 (remote geschlossen) und 999 (fehlt). Aktion: Sync. Erwartet: beide entfernt, kein Ticket, kein Abbruch.

**`TextSyncTest` (q9a10d0cf6e7f)**
- `test_pull_creation_sets_a_gh_text_baseline` — Vor: Remote-Ready-Issue. Aktion: Sync. Erwartet: GH-Ticket trägt nichtleeres `gh_text`.
- `test_local_text_change_is_pushed_only_once` — Vor: Baseline; lokaler Titel/Beschreibung geändert. Aktion: Sync zweimal. Erwartet: ein PATCH mit lokalem Titel/Body, `text_pushed == 1`, `gh_text` aktualisiert; zweiter Lauf ohne PATCH/Text-Push.
- `test_remote_text_change_is_pulled_including_the_description` — Vor: Baseline; Remote-Titel und -Beschreibung geändert, lokal unverändert. Aktion: Sync. Erwartet: Titel **und** Beschreibung lokal übernommen, `text_pulled == 1`, kein PATCH.
- `test_conflict_keeps_local_text_counts_it_and_continues` — Vor: Baseline; beide Seiten geändert, zusätzlich neues Remote-Issue. Aktion: Sync. Erwartet: lokale Fassung bleibt und wird gepusht, `conflicts == 1`, neues Ticket entsteht (kein Abbruch).
- `test_missing_baseline_with_different_texts_is_a_conflict` — Vor: lokales Ticket mit `github=203`, abweichender Text, kein `gh_text`. Aktion: Sync. Erwartet: lokale Fassung gewinnt, Push, `conflicts == 1`.
- `test_missing_baseline_with_equal_texts_adopts_without_push` — Vor: gleicher Text beidseitig, kein `gh_text`. Aktion: Sync. Erwartet: `gh_text` gesetzt, kein PATCH, `text_pushed == 0`, `conflicts == 0`.
- `test_done_ticket_text_is_not_synced_in_either_direction` — Vor: erledigtes GH-202 mit altem Text, Remote geändert; neues Ready-Issue. Aktion: Sync. Erwartet: GH-202 textstabil, kein PATCH an 202, GH-201 entsteht.

**`StorePreservationTest`**
- `test_gh_text_survives_a_ticket_update` — Vor: Ticket mit `gh_text`. Aktion: `vibe_tickets.update(title=...)`. Erwartet: `gh_text` bleibt erhalten.
- `test_github_deletions_survives_ticket_writes` — Vor: Dokument mit `github_deletions: [7]`. Aktion: Ticket-Update und neues Ticket. Erwartet: Dokumentenschlüssel bleibt erhalten.

**`IssueStateFixTest` (D)**
- `test_open_state_sets_ready_label_and_survives_the_next_sync` — Vor: GH-101, Remote trägt `in-progress`. Aktion: `set_issue_state(..., "open")`, dann Sync. Erwartet: PATCH setzt `ready` und entfernt `in-progress`; der Sync setzt das Ticket nicht auf `draft` zurück.

**`DraftRunDisciplineTest` (D)**
- `test_only_open_and_in_progress_are_eligible` — Vor: Draft, blocked, waiting-merge, open, in-progress. Aktion: `select_package` zweimal. Erwartet: erst open, dann in-progress; nie draft/blocked/waiting.
- `test_order_and_priority_fallbacks_skip_drafts` — Vor: Draft in `PACKAGE_ORDER` und mit P0; offenes T2. Aktion: `select_package`. Erwartet: T2.
- `test_connected_pull_maps_missing_ready_label_to_draft` — Vor: Remote 101 ohne Ready, 102 mit Ready. Aktion: Sync, dann Select. Erwartet: 101 draft, 102 open, nur GH-102 wählbar.

### 3.2 `tests/unit/test_gh47_surfaces.py` (23 Fälle)

Run: `python3 -m unittest tests.unit.test_gh47_surfaces -v`

**`LegacyGithubActionsRemovedTest` (q6cbba05d8ca9)**
- `test_action_issues_is_unknown_without_network` — Vor: Issues-Sync aktiv. Aktion: `/api/github action=issues`. Erwartet: `ok false`, Meldung „unbekannt“, kein REST.
- `test_action_import_is_unknown_without_network` — dito für `action=import`.
- `test_issues_sync_and_state_remain_available` — Vor: Issues-Sync aktiv, Remote 101. Aktion: `issues.sync`. Erwartet: `ok`, GH-101 entsteht; Sync bleibt erreichbar.

**`ConnectedDeleteApiTest` (q8907138c500b)**
- `test_delete_without_github_reference_is_local_only` — Vor: Issues-Sync aktiv, AP1 ohne GitHub-Bezug. Aktion: `/api/ticket delete`. Erwartet: ok, Ticket weg, kein PATCH, keine Tombstone-Nummer.
- `test_successful_close_deletes_locally_and_names_the_issue` — Vor: GH-101 mit `github=101`. Aktion: Delete. Erwartet: ok, Ticket weg, PATCH `state=closed`, Meldung nennt 101 und „geschlossen“, keine Tombstone-Nummer.
- `test_failed_close_deletes_locally_and_records_a_tombstone` — Vor: GH-101, PATCH 403. Aktion: Delete. Erwartet: `ok` nicht false, Ticket weg, 101 in `github_deletions`, Meldung nennt Fehlschlag + erneuten Sync-Versuch, kein Token.
- `test_failed_close_tombstones_are_deduplicated` — Vor: GH-101 und AP1 zeigen auf Issue 101, PATCH 403. Aktion: beide löschen. Erwartet: `github_deletions == [101]` (genau einmal).
- `test_done_ticket_is_refused_before_any_rest_call` — Vor: erledigtes GH-101. Aktion: Delete. Erwartet: `ok false`, Nachweis-Meldung, Ticket bleibt, kein PATCH.
- `test_feedback_delete_uses_the_connected_path` — Vor: Bug B1 mit `github=101`. Aktion: `/api/feedback delete`. Erwartet: Issue geschlossen, B1 lokal weg, PATCH.
- `test_feedback_delete_without_issue_sync_stays_local` — Vor: Issues-Sync aus, B1 mit `github=101`. Aktion: Feedback-Delete. Erwartet: lokal gelöscht, kein PATCH, keine Tombstone-Nummer.

**`TicketStateApiTest` (D + Nova-Vertrag)**
- `test_state_without_issue_sync_is_local_only` — Vor: Issues-Sync aus, AP1. Aktion: `state=draft`. Erwartet: lokal draft, kein PATCH.
- `test_state_with_github_reference_patches_labels_and_local_state` — Vor: Issues-Sync aktiv, GH-101. Aktion: `state=draft`, dann `open`. Erwartet: draft entfernt Ready/In-Progress lokal+remote; open setzt Ready (Fix) und lokal offen.
- `test_state_with_issue_sync_but_no_github_reference_stays_local` — Vor: Issues-Sync aktiv, AP1 ohne Bezug. Aktion: `state=in-progress`. Erwartet: ok, lokal in-progress, kein PATCH.
- `test_feedback_state_with_github_reference_patches_labels` — Vor: B1 mit `github=101`. Aktion: Feedback-`state=draft`. Erwartet: PATCH entfernt Ready, B1 lokal draft.
- `test_done_ticket_state_is_refused_without_rest` — Vor: erledigtes GH-101. Aktion: `state=open`. Erwartet: `ok false`, bleibt done, kein PATCH.

**`SyncMessageTest` (q9a10d0cf6e7f)**
- `test_conflict_is_reported_in_message_and_statistics` — Vor: Baseline, danach beide Seiten geändert. Aktion: `issues.sync`. Erwartet: Meldung nennt Konflikt, acht Statistikschlüssel, `conflicts == 1`, lokale Fassung bleibt.

**`CliLegacyActionsTest` (q6cbba05d8ca9)**
- `test_cli_issues_is_removed_without_network` — Vor: Issues-Sync aktiv. Aktion: `vibe github proj issues`. Erwartet: Exit != 0, „unbekannt“, kein REST.
- `test_cli_issues_import_is_removed_without_network` — dito für `issues-import`.
- `test_usage_no_longer_offers_issues_or_import` — Vor: `bin/vibe`. Aktion: Quelltext/Docstring. Erwartet: kein `issues-import`; `issues-sync`/`issues-state` bleiben dokumentiert.

**`CliSyncMessageTest` (q9a10d0cf6e7f)**
- `test_sync_output_mentions_text_upload_and_conflicts` — Vor: zwei Baseline-Tickets; lokale Änderung (201) und beidseitige Änderung (202). Aktion: `issues-sync`. Erwartet: Exit 0; Ausgabe enthält „text“, „hochgeladen“, „konflikt“.

**`SurfaceStructureTest` (q6cbba05d8ca9)**
- `test_nova_issues_section_has_exactly_one_sync_and_no_legacy` — Vor: `nvpGithubSection`. Aktion: Struktur. Erwartet: genau ein `issues-sync`, keine `github-issues`/`github-import`, kein `github-issue-label`; Erklärung nennt Synchronisieren, Ready, Entwurf, Schließen.
- `test_classic_issues_section_drops_load_import_and_filter` — Vor: `app.js`. Aktion: Struktur. Erwartet: keine `action:'issues'`/`action:'import'`, keine Buttons „Issues laden“/„Issues importieren“, kein `issueFilter`; Sync über `issues.sync`.
- `test_product_import_helpers_are_removed` — Vor: Produktmodule. Aktion: Attribute/Quelltext. Erwartet: `vibe_github.import_issues_into_tickets` fehlt, `list_issues` bleibt, `bin/vibe` ohne `def github_issues(`/`def github_issues_import(`.

### 3.3 `tests/browser/test_gh47_issues_ui.py` (3 Fälle)

Run: `python3 -m unittest tests.browser.test_gh47_issues_ui -v`

Echtes Dashboard auf freiem Loopback-Port, Chromium headless; GitHub-API-Basis zeigt auf eine geschlossene Loopback-Adresse, der Sync-Button wird nicht ausgelöst.

- `test_issues_section_offers_one_sync_and_no_legacy_actions` — Vor: Issues-Sync aktiv, GitHub-Feature an. Aktion: GitHub-Sektion öffnen. Erwartet: genau ein `[data-nv-action='issues-sync']`; keine `github-issues`/`github-import`/`github-issue-label`; Erklärung nennt Synchronisieren, Ready, Entwurf, Schließen.
- `test_ticket_detail_state_control_changes_draft_to_open` — Vor: AP2 ist Entwurf. Aktion: Arbeit öffnen, AP2 anklicken, `select[data-nv-ticket-state-select]` auf `open`, `ticket-state-save`. Erwartet: Karte zeigt `data-nv-state=Draft`; Select bietet `draft|open|in-progress`, vorbelegt `draft`; nach Speichern AP2 `open`, Karte `data-nv-state=offen`.
- `test_done_and_blocked_tickets_follow_the_state_contract` — Vor: B1 blockiert, AP3 erledigt. Aktion: B1-Detail, dann erledigte anzeigen und AP3 öffnen. Erwartet: B1 hat Zustands-Select ohne Vorbelegung; AP3 hat kein Select/keinen Speichern-Button, sondern den Nachweis-Hinweis.

## 4. Bewusste Bestandsanpassungen

Alle Anpassungen spiegeln die oben genannten Option-A-Entscheidungen; keine Assertion wurde abgeschwächt.

1. **`tests/unit/test_ap3_korbat_issues_backend.py`** — Entscheidung **q9a10d0cf6e7f**.
   - `test_pull_state_is_authoritative_and_descriptions_stay_local` → `test_pull_state_is_authoritative_and_remote_text_updates_are_taken_over`: Beschreibungen bleiben nicht mehr lokal; Zustand bleibt label-autoritativ, Remote-Titel/-Beschreibung werden bei unverändertem Lokalstand gezogen, done-Tickets bleiben textstabil.
   - `test_pull_does_not_duplicate_and_updates_open_tickets`: baut zuerst eine textgleiche Baseline auf, dann Remote-Änderung. Grund: Ohne Baseline wäre die alte Erwartung „Remote-Titel gewinnt“ ein Konfliktfall.
   - Fake erweitert um PATCH `title`/`body` und `fail_patch_numbers` (Testinfrastruktur, kein Produktverhalten).
2. **`tests/unit/test_ap3_korbat_surfaces.py`** — **q8907138c500b/q9a10d0cf6e7f/q6cbba05d8ca9**.
   - `issues.state ... open` setzt jetzt das Ready-Label (statt beide Labels zu entfernen).
   - Sync-Statistik prüft die acht exakten Vertragsschlüssel.
   - Nova-`nvpGithubSection` prüft genau einen Sync und die Abwesenheit der Altabktionen/-filter.
3. **`tests/unit/test_gh48_tickets_surface.py`** — **q6cbba05d8ca9**: Import-Test durch Entfall-Prüfung (`github_issues`, `github_issues_import` fehlen; Sync vorhanden) ersetzt; Docstring angepasst.
4. **`tests/unit/test_ap06_github.py`** — **q6cbba05d8ca9**: `IssuesImportTest` durch `IssuesImportRemovalTest` ersetzt; `ImportCollisionTest` entfällt; `list_issues`-Fälle bleiben unverändert. Docstring nennt den Entfall. (Beim Umbau wurde die Klasse `RemotesMaskingTest` versehentlich mit `DefaultBaseTest` verschmolzen; der Header wurde wiederhergestellt, danach nur noch der beabsichtigte Import-Entfall rot.)
5. **`tests/unit/test_ap5_korbat_waiting_state.py`** — **D**: `status_report` enthält zusätzlich einen Draft und prüft den eigenen `draft`-Bucket; Draft erscheint nicht unter `open`.
6. **`tests/unit/test_ap11_priority.py`** — **D**: Neuer Fall `test_draft_entries_are_marked_as_entwurf_and_skipped`: `priority_view` weist Drafts als „Entwurf“ aus, `queue`/`select_package` überspringen sie.
7. **`tests/browser/test_ap22_project_ui.py`** — **q6cbba05d8ca9**: Parity-Kontrollliste erwartet `issues-sync` und die Abwesenheit von `github-issues`/`github-import`/`github-issue-label`; der alte Netzwerkfehler-Test wurde durch einen Struktur-/Abwesenheitstest ersetzt; der Import-Test wurde durch einen echten Sync-Pull-Test ersetzt. Neuer Helfer `enable_issue_sync_env` inkl. Reload, weil derselbe Hash die Seite sonst nicht neu lädt.
8. **`tests/browser/test_f33_project_ui.py`** — **q6cbba05d8ca9**: Die Reihenfolge „Merge-Request vor Issues“ referenziert jetzt `issues-sync` statt `github-issues`; der Fall aktiviert den Issues-Sync in der Projektkonfiguration.

## 5. Tatsächlich gelaufene Rotphase (Ausgangsstand, Produktcode alt)

Alle Befehle im Worktree, isolierte Temp-Pfade/Fake-REST, kein echtes GitHub/Netz.

| Befehl | Exit | Beobachtung |
| --- | --- | --- |
| `python3 -m unittest tests.unit.test_gh47_issues_backend -v` | 1 | 17 Tests, 9 Failures, 2 Errors. Fehlend: `gh_text` (KeyError in zwei Textfällen), Tombstone-Verarbeitung (Tickets werden neu angelegt, Tombstones bleiben), vier Statistikschlüssel (`'text_pushed' not found in {'created':…}`), `open` setzt kein Ready (`'ready' not in ['bug']`). |
| `python3 -m unittest tests.unit.test_gh47_surfaces -v` | 1 | 23 Tests, 16 Failures. `action=issues`/`action=import` liefern noch `ok:true` und laden/importieren; CLI `issues`/`issues-import` Exit 0; Delete schließt nicht (Issue bleibt `open`) und schreibt keinen Tombstone; `action=state` patcht bei GitHub-Bezug nicht; Nova/Classic enthalten weiterhin Altabktionen/Filter; Sync-Meldung ohne Text-/Konfliktanteile. |
| `python3 -m unittest tests.unit.test_ap3_korbat_issues_backend -v` | 1 | 27 Tests, 1 Failure: `'Remote body 101' != 'lokal 101'` — Beschreibung bleibt lokal (alter Stand). |
| `python3 -m unittest tests.unit.test_ap3_korbat_surfaces -v` (letzter Lauf nach exakter Statistik-Assertion) | 1 | 25 Tests, genau 3 Failures: `open`-PATCH `['bug']` statt `['bug','ready']`; `'text_pushed' not found in {'created': 2, 'updated': 0, 'closed': 0, 'pushed': 1}`; Nova `"'github-issues' unexpectedly found"`. Alle übrigen 22 grün. |
| `python3 -m unittest tests.unit.test_gh48_tickets_surface -v` | 1 | 16 Tests, 1 Failure: `github_issues_import`/`github_issues` existieren noch. |
| `python3 -m unittest tests.unit.test_ap06_github -v` | 1 | 50 Tests, 1 Failure: `import_issues_into_tickets` existiert noch; `list_issues`-Fälle grün. |
| `python3 -m unittest tests.unit.test_ap5_korbat_waiting_state -v` | 1 | 21 Tests, 1 Failure: kein `draft`-Bucket. |
| `python3 -m unittest tests.unit.test_ap11_priority -v` | 1 | 24 Tests, 1 Failure: Draft erscheint als „offen“ statt „Entwurf“. |
| `python3 -m unittest tests.browser.test_gh47_issues_ui -v` | 1 | 3 Tests, 3 Failures: „Issues laden“ noch vorhanden; kein `data-nv-ticket-state-select`; Behinderten-/Done-Vertrag noch nicht erfüllt. Chromium/Playwright war verfügbar, kein Skip. |
| `python3 -m unittest -v` (drei `GithubParityTest`-Fälle) | 1 | Sync-Pull-Test grün (Regressionssicherung), Struktur-/Abwesenheitsfälle rot (Altabktionen/Filter vorhanden). |
| `python3 -m unittest -v tests.browser.test_f33_project_ui.SettingsTabTest.test_github_explains_branches_and_puts_mr_above_issues` | 0 | OK; der Sync-Button existierte bereits, die Anpassung ist reine Regressionssicherung. |
| `python3 -m py_compile` über alle geänderten/neuen Testdateien | 0 | `PYCOMPILE_OK`; keine Syntaxfehler als Rotphase getarnt. |

## 6. Bewusst vorab grüne Fälle (Regressionssicherung)

Diese Fälle sind am Ausgangsstand grün und sichern bestehendes Verhalten, das GH-47 nicht ändern darf:

- `test_only_open_and_in_progress_are_eligible`, `test_order_and_priority_fallbacks_skip_drafts`: `select_package` schloss Drafts schon vor GH-47 aus; die Fälle halten das fest.
- `test_connected_pull_maps_missing_ready_label_to_draft`: Ready-Label-Mapping existierte bereits; sichert die Verbindung von Pull und Laufauswahl.
- `test_gh_text_survives_a_ticket_update` und `test_github_deletions_survives_ticket_writes`: `normalize`/`save` bewahren unbekannte Felder bzw. Dokumentschlüssel bereits; sichert die neue Speicherhaltung ab.
- `test_done_ticket_text_is_not_synced_in_either_direction`: Done-Schutz verhinderte Textänderungen schon; sichert ihn für den neuen Text-Sync.
- `test_delete_without_github_reference_is_local_only`, `test_done_ticket_is_refused_before_any_rest_call`, `test_feedback_delete_without_issue_sync_stays_local`, `test_issues_sync_and_state_remain_available`: lokales Löschen/Schützen und die verbleibenden Sync-/State-Aktionen funktionieren bereits; sie dürfen durch den Umbau nicht kaputtgehen.
- `test_state_without_issue_sync_is_local_only`, `test_state_with_issue_sync_but_no_github_reference_stays_local`, `test_done_ticket_state_is_refused_without_rest`: Offline-/ohne-Bezug-Zustandswechsel und Done-Schutz sind Bestandsverhalten.
- Browser: `test_issues_sync_pulls_open_issues_into_the_store` und der F33-Reihenfolgefall waren am alten Stand grün (Sync-Button existierte), sichern Pull und Reihenfolge nach dem Umbau.

## 7. Grenzen und offene Punkte

- **Browser-Vollregression steht aus.** Nach der Implementierung müssen `tests/browser/test_ap22_project_ui.py` und `tests/browser/test_f33_project_ui.py` als ganze Module laufen; hier wurden nur die vier betroffenen Fälle gezielt ausgeführt. Seitenwirkungen des neuen Reload-Helfers auf andere AP22-Fälle sind nicht ausgeschlossen.
- **Vorbestehende f33-Fehlfälle (nicht GH-47):** `tests/browser/test_f33_project_ui.py` weist 13 vorbestehende Fehlfälle auf (WorkOrder/Priority/Search/Settings-Fälle; die Legacy-Fixture schreibt `TICKETS.md`/`FEEDBACK.md`, das Produkt liest seit GH-48 nur `.vibe/tickets.json`). Vom Koordinator am Branchpunkt `07e7ff1` per `git archive`-Export reproduziert (Repräsentativfälle: 3 failures + 1 error identisch vor allen GH-47-Änderungen). Das ist kein GH-47-Regressor und wird in diesem Paket bewusst **nicht** behoben (fremdes Arbeitsgebiet). Die einzige f33-Anpassung dieses Pakets (MR-vor-Issues-Fall) bleibt davon unberührt und ist grün.
- **Alle Rotläufe beziehen sich auf den alten Produktstand.** Die Tests sind vor der Implementierung geschrieben und rot beobachtet; ein Grün nach Implementierung ist nicht Teil dieses Berichts.
- **Nova-Zustandssteuerung** ist über den vom Koordinator vorgegebenen DOM-Vertrag (`data-nv-ticket-state-select`, `ticket-state-save`) getestet. Falls die Implementierung abweichende Hooks wählt, müssen die Tests bewusst angepasst werden, nicht die Assertions abgeschwächt.
- **Statistikschlüssel** sind exakt fixiert (`text_pushed`, `text_pulled`, `conflicts`, `closed_remote`); die Meldungsprüfung bleibt bewusst Substring-basiert.
- **Tombstone-Helfernamen** in `vibe_tickets` werden nicht geraten; geprüft wird die Dokumentebene (`github_deletions`) über Löschen/Sync sowie die Erhaltung bei Ticket-Schreibvorgängen.
- **Umgebung:** Playwright/Chromium war verfügbar; der neue Browsertest lief wirklich und wurde nicht übersprungen.
- Keine Commits, kein Push, kein Branchwechsel; Produktcode unverändert.

## 8. Korrekturrunde nach der Implementierung

Der Coding-Agent meldete drei Testdefekte (Produktcode bereits umgesetzt). Sie wurden in dieser Runde behoben; es wurde kein neues Testmaterial erfunden.

1. **`tests/unit/test_gh48_tickets_surface.py::test_sync_pulls_states_and_pushes_open_local_tickets`** — **q9a10d0cf6e7f**. Der Fall erwartete noch das alte GH-48-Verhalten „Remote-Titel gewinnt“ bei fehlender `gh_text`-Basislinie. Angepasst: fehlende Basislinie + unterschiedliche Texte ist ein Konflikt; die lokale Fassung bleibt („Alt“), der Konflikt wird in der Sync-Meldung gezählt, ein PATCH überträgt den lokalen Titel, der Zustand kommt weiterhin aus den Labels, GH-103 wird done und AP1 gepusht. Keine Assertion abgeschwächt.
2. **`tests/browser/test_gh47_issues_ui.py::test_issues_section_offers_one_sync_and_no_legacy_actions`** — Locale-Defekt: `(?i)synchronisier` erkannte den englischen UI-Text nicht. Ersetzt durch `(?i)synchroni[sz]` (deckt „synchronisiert“ und „synchronizes“); die Prüfung des einheitlichen Sync-Textes bleibt erhalten.
3. **`tests/browser/test_gh47_issues_ui.py::test_done_and_blocked_tickets_follow_the_state_contract`** — (a) Locale: Nachweis-Regex um `evidence|completed|done` ergänzt (weiterhin `nachweis|erledigt|abgeschlossen`). (b) Das offene Kontext-Panel blockierte `[data-nv-work-hide-done]`; der Test drückt jetzt vor dem Klick `Escape` und wartet, bis das Detail-Panel (`[data-nv-ticket-detail='B1']`) verborgen ist. Die Assertion zur fehlenden Vorbelegung bei `blocked` bleibt unverändert und prüft weiterhin den Produkt-Fix.

Ergebnisse dieser Runde:

| Befehl | Exit | Ergebnis |
| --- | --- | --- |
| `python3 -m py_compile tests/unit/test_gh48_tickets_surface.py tests/browser/test_gh47_issues_ui.py` | 0 | Syntax OK |
| `python3 -m unittest tests.unit.test_gh48_tickets_surface -v` | 0 | vollständig grün |
| `python3 -m unittest tests.browser.test_gh47_issues_ui -v` | 0 | 3/3 grün (echtes Chromium) |
| `python3 -m unittest tests.unit.test_gh47_issues_backend tests.unit.test_gh47_surfaces -v` | 0 | 40 Vertragstests grün |
| `python3 -m py_compile` über die drei geänderten Dateien (`test_gh48_tickets_surface.py`, `test_gh47_issues_ui.py`, `test_ap3_korbat_surfaces.py` nicht erneut geändert) | 0 | Syntax OK |

Damit sind die drei gemeldeten Testdefekte behoben; Produktcode und Testumfang bleiben unverändert, keine Commits.
