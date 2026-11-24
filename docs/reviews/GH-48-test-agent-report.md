# GH-48 – Bericht des unabhängigen Test-Agenten

Arbeitspaket: GH-48 „Improve ticket system" (GitHub #48)
Worktree: `/var/log/custom/vibe-dev/worktrees/vibe-GH-48-7su7Ui`
Branch: `feature/korbat/gh-48`
Grundlage: Ticket GH-48, `SPEC.md` und der verbindliche
Implementierungsvertrag GH-48. Es gibt noch keinen Implementierungsdiff; alle
Fälle sind aus dem Vertrag abgeleitet.

Alle Tests laufen mit `tempfile`-Projekten, isoliertem `HOME`/`VIBE` und ohne
Netz- oder Modellaufrufe. GitHub-REST ausschließlich über Loopback-Fakes.

## 1. Neue Testdateien

| Datei | Zweck | Fälle |
|---|---|---|
| `tests/unit/test_gh48_ticket_store.py` | Speicherkern `bin/vibe_tickets.py` | 30 |
| `tests/unit/test_gh48_tickets_surface.py` | Oberflächen in `bin/vibe` inkl. GitHub-Ebene und `package_close` | 16 |
| `tests/unit/test_gh48_runner_tickets.py` | Läufer `bin/vibe_packages.py` | 29 |
| `tests/unit/test_gh48_scaffold_templates.py` | `.gitignore`, Gerüst, Vorlagen, Guide | 10 |
| `tests/unit/test_gh48_web_api.py` | `/api/ticket`, `/api/feedback`, `project_detail` | 11 |
| `tests/browser/test_gh48_tickets_ui.py` | Dashboard-Oberfläche mit Speicher | 3 |

Geändert: `tests/unit/runner_support.py` (GH-48-Modul in der
Installationskopie, Helfer `write_ticket_store`), `tests/unit/test_worknotes_sync.py`
(auf den neuen Vertrag überführt, 19 → 16 Fälle).

## 2. Fallbeschreibungen

### 2.1 `test_gh48_ticket_store.py` – Speicherkern (30 Fälle)

| Fall | Vor | Aktion | Erwartet |
|---|---|---|---|
| `test_a_missing_store_reads_as_an_empty_list` | kein `.vibe/tickets.json` | `load` | `[]` |
| `test_save_creates_folder_and_document_with_version_and_newline` | kein Speicher | `save` | Ordner+Datei, `{"version":1,"tickets":[…]}` , indent=1, Endzeilenumbruch, Umlaute unescaped |
| `test_load_returns_the_saved_tickets` | gespeicherte Tickets | `load` | Reihenfolge und Typen erhalten |
| `test_invalid_json_is_reported_and_never_repaired` | defektes JSON | `load` | `ValueError` „Ticketspeicher unlesbar" + Pfad; Datei byte-identisch |
| `test_a_conflicting_write_is_reported_and_preserves_foreign_state` | Prüfsumme veraltet, Datei extern geändert | `save(expected=…)` | `ValueError` mit Konflikt; fremder Stand bleibt |
| `test_unknown_keys_…_survive_a_rewrite` | Zusatzschlüssel Dokument/Ticket | `load`+`save` | Zusatzschlüssel erhalten |
| `test_unknown_fields_of_an_updated_ticket_are_kept` | Ticket mit Zusatzfeld | `update` | Zusatzfeld bleibt |
| `test_defaults_fill_all_contract_fields` | Minimalticket | `normalize` | type=task, state=open, Leerfelder, github=None, dependencies=[] |
| `test_id_must_end_with_digits_and_start_with_a_letter` | GH-48/AP7/T-01/B12/F3 gültig; 48/AP/-AP1/„AP 1"/leer | `normalize` | gültig bzw. `ValueError` |
| `test_title_is_required_and_single_line` | fehlend/leer/mehrzeilig | `normalize` | `ValueError`; einzeilig wird getrimmt |
| `test_type_and_state_are_closed_enumerations` | Vertragswerte + Fremdwerte | `normalize` | Werte gültig, „chore"/„erledigt" nicht |
| `test_commit_must_be_a_hex_hash_of_7_to_40_characters` | 7/40 Hex, 6 Zeichen, Nicht-Hex | `normalize` | gültig bzw. `ValueError` |
| `test_done_requires_commit_and_test` | done ohne/nur Commit/nur Test/beides | `normalize` | erste drei `ValueError`, beides gültig |
| `test_priority_is_empty_or_p0_to_p8` | "",P0,P8,P9 | `normalize` | P9 `ValueError` |
| `test_github_is_an_integer_and_dependencies_a_list_of_ids` | github=12, dependencies-Liste | `normalize` | Werte bleiben; String/ungültige ID `ValueError` |
| `test_auto_ids_follow_the_type_prefix` | leerer Speicher | `add` task/bug/feedback/feature | AP1, B1, F1, eigene FEAT-1 |
| `test_auto_ids_continue_after_the_highest_number` | AP9 | `add` | AP10 |
| `test_an_explicit_id_is_validated_and_must_be_unique` | AP1 existiert | `add` | Duplikat/ungültig `ValueError` |
| `test_gh_prefix_ids_are_reserved_for_issue_imports` | leer | `add(tid="GH-7")` | `ValueError` (Interpretation, s. §6) |
| `test_created_and_updated_are_iso_utc_and_updated_changes` | altes `updated` | `update` | created bleibt, updated neuer ISO-UTC-Wert |
| `test_update_is_a_partial_update_and_validates` | AP1 offen | `update` state/priority | Teilupdate; unbekannt/ungültig `ValueError` |
| `test_update_refuses_done_without_proof` | AP1 offen | `update(state=done)` | `ValueError`, bleibt offen |
| `test_delete_removes_exactly_one_ticket` | AP1, AP2 | `delete` AP1 | nur AP2 bleibt; unbekannt `ValueError` |
| `test_done_tickets_are_protected_from_delete_and_editing` | AP1 done | `delete`/`update` Titel/Beschreibung | jeweils `ValueError`, Speicher unverändert |
| `test_find_and_find_by_github` | AP1(github 5), AP2 | `find`/`find_by_github` | Treffer/None |
| `test_next_number_uses_the_exact_prefix` | AP3, AP7, GH-48, B9 | `next_number` | AP→8, B→10, F→1 |
| `test_display_state_uses_the_known_labels` | je Zustand | `display_state` | erledigt/BLOCKIERT/WARTET AUF MERGE/In Progress/Draft/offen |
| `test_file_name_follows_the_template` | AP7/GH-48 | `ticket_file_name` | TICKET-AP7.json / TICKET-GH-48.json |
| `test_write_and_read_roundtrip` | normiertes Ticket | write/read | identisches Ticket, Endzeilenumbruch |
| `test_broken_or_invalid_files_raise_value_error` | defektes JSON, fehlender Titel, state „erledigt" | `read_ticket_file` | `ValueError` je Fall |

### 2.2 `test_gh48_tickets_surface.py` – Oberflächen (16 Fälle)

| Fall | Vor | Aktion | Erwartet |
|---|---|---|---|
| `test_ticket_items_read_task_and_feature_rows_from_the_store` | task/feature/done/bug/feedback | `ticket_items` | nur task/feature; Felder id,title,description,state,completed,status,github |
| `test_feedback_items_read_bug_and_feedback_rows_with_kind` | Bug B1, Feedback F1 (blockiert) | `feedback_items` | kind bug/feedback, BLOCKIERT, github |
| `test_open_items_list_all_unfinished_tickets_in_store_order` | offen/in-progress/draft/blockiert/done | `open_items` | alle außer done, Speicherreihenfolge, Anzeigezustand |
| `test_missing_store_yields_empty_rows` | kein Speicher | alle Leseflächen | leere Listen |
| `test_add_ticket_creates_a_missing_store_with_ap_id` | kein Speicher/TICKETS.md | `add_ticket` | AP1, Datei angelegt, task/open |
| `test_add_ticket_accepts_an_explicit_id_and_continues_auto_ids` | AP7 | `add_ticket` | AP8 danach |
| `test_add_ticket_rejects_duplicate_and_invalid_ids` | AP1 existiert | `add_ticket` | `ValueError`, Speicher unverändert |
| `test_add_feedback_and_add_bug_store_the_distinct_types` | leer | `add_feedback`/`add_bug` | F1 feedback, B1 bug, F2 feedback |
| `test_ticket_update_changes_only_title_and_description` | AP1 offen | `ticket_update` | Titel/Beschreibung neu, Typ/Zustand unverändert |
| `test_done_tickets_stay_protected_against_edit_and_delete` | AP2 done | update/delete | `ValueError`, Datei unverändert |
| `test_feedback_update_and_delete_follow_the_same_rules` | F1, B1 offen | update F1/delete B1 | F1 neu, B1 weg, andere bleiben |
| `test_unknown_ticket_reports_the_ticket_store_not_the_legacy_files` | X9 fehlt | update/delete | Meldung nennt „Ticketspeicher", nicht TICKETS.md/FEEDBACK.md |
| `test_import_creates_gh_tickets_in_the_store` | Remote 101(bug)/102/PR | `github_issues_import` | GH-101 bug, GH-102 task, PR ignoriert, kein Markdown |
| `test_sync_pulls_states_and_pushes_open_local_tickets` | AP1 ohne GitHub, GH-101 offen, GH-103 geschlossen | `github_issues_sync` | Titel/Zustand gepullt, GH-103 done, AP1 erhält Nummer, POST nur AP1 |
| `test_state_action_maps_ready_to_open_and_keeps_draft` | GH-101 offen | `github_issues_state` | draft→draft, ready→open, in-progress→in-progress; PATCH; „erledigt" `ValueError` |
| `test_package_close_uses_sync_ticket_without_require_commit` | registrierter Worktree, aktive GitHub-Verknüpfung, gemergter PR | `package_close` | `sync_ticket(..., require_commit=False)`, kein `sync_proof` |

### 2.3 `test_gh48_runner_tickets.py` – Läufer (29 Fälle)

| Fall | Vor | Aktion | Erwartet |
|---|---|---|---|
| `test_open_and_in_progress_are_candidates_in_store_order` | AP1 offen, AP2 in-progress | `select_package` | AP1, skip→AP2; Zeilenfelder |
| `test_draft_blocked_waiting_and_done_are_never_selected` | nur draft/blocked/waiting/done | `select_package` | `None` |
| `test_package_order_wins_over_priority_and_position` | PACKAGE_ORDER AP2 AP1, P0/P1 | `select_package` | AP2, ordered=True |
| `test_standard_order_is_priority_then_store_position` | B1 erst, AP1 P1, AP2 P0, AP3 ohne | `select_package` | AP2, AP1, AP3, B1 |
| `test_a_known_dependency_must_be_done` | AP2 hängt von AP1 | `select_package` | erst AP1, nach done AP2; unbekannte Abhängigkeit blockiert nicht |
| `test_prefer_reattaches_even_a_blocked_package` | AP2 blockiert | `prefer=AP2` | AP2; unbekanntes prefer ignoriert |
| `test_complete_package_passes_without_findings` | Commit, docs, Review PASS, sauber, TICKET done | `gate_errors` | `[]` |
| `test_missing_ticket_file_is_a_finding` | TICKET-Datei fehlt | `gate_errors` | Befund nennt Datei |
| `test_unreadable_ticket_file_is_a_finding` | defektes JSON | `gate_errors` | Befund nennt Datei/Lesbarkeit |
| `test_state_must_be_done` | state=in-progress | `gate_errors` | Befund nennt state/done |
| `test_commit_must_exist_in_the_repository` | commit=deadbee | `gate_errors` | Befund nennt commit/deadbee |
| `test_test_field_must_not_be_empty` | test="" | `gate_errors` | Befund nennt test |
| `test_already_integrated_package_passes_without_new_commits` | Paketcommit ist Vorfahre der Basis | `gate_errors` | `[]` |
| `test_docs_review_and_clean_checks_are_unchanged` | Doku fehlt, Review FAIL, uncommittete Datei | `gate_errors` | drei Befunde |
| `test_a_complete_ticket_is_taken_over_and_clears_block_fields` | Projekt AP1 blocked, Arbeitskopie done+pr_url | `sync_ticket(require_commit=False)` | Übernahme; blocked_reason/waiting_note geräumt |
| `test_require_commit_rejects_a_commit_unknown_to_the_project` | commit unbekannt | `sync_ticket` | changed=False, Speicher unverändert |
| `test_missing_or_incomplete_source_is_refused_without_change` | Datei fehlt/defekt/state offen | `sync_ticket` | jeweils False + Grund, unverändert |
| `test_a_ticket_missing_in_the_project_is_refused` | X9 nur in Arbeitskopie | `sync_ticket` | False, kein X9 |
| `test_mark_blocked_sets_state_and_reason_idempotently` | AP1 offen | `mark_blocked` zweimal | blocked+reason; zweiter Lauf False |
| `test_mark_waiting_merge_sets_note_and_pr_url` | AP1 offen | `mark_waiting_merge` | waiting-merge+note+pr_url; idempotent |
| `test_status_report_groups_by_store_state` | fünf Zustände | `status_report` | open=[AP1,AP2], waiting/blocked/done korrekt |
| `test_priority_view_reports_status_and_effective_queue` | PACKAGE_ORDER mit done/fehlt | `priority_view` | Status erledigt/offen/fehlt; queue AP2,AP1,B1 |
| `test_normalize_order_deduplicates_and_rejects_unknown_ids` | AP2,AP1,AP2/X9 | `normalize_order` | Dedupe; X9 `ValueError` |
| `test_copy_work_notes_transfers_only_agents_md` | AGENTS.md + alte Ledger | `copy_work_notes` | nur AGENTS.md |
| `test_transport_ticket_writes_a_visible_file_and_excludes_it` | AP1 im Speicher, echte Arbeitskopie | `transport_ticket` zweimal | Datei in Wurzel, genau ein Exclude-Eintrag |
| `test_transport_ticket_missing_in_the_store_fails` | AP9 fehlt | `transport_ticket` | ok=False, keine Datei/kein Eintrag |
| `test_copy_notes_id_transports_the_ticket_and_reports_missing_ones` | AP1/AP9 | CLI `copy-notes --id` | AP1 Exit 0 + OK + Datei; AP9 Exit 1 + FEHLT |
| `test_is_work_note_path_covers_ticket_files_at_the_root_only` | Stamm/Unterordner/andere Endung | `is_work_note_path` | nur Stamm-TICKET-*.json und AGENTS.md |
| `test_project_exclude_mentions_only_current_work_notes` | Git-Projekt | `ensure_project_exclude` | `.vibe/tmp/` + AGENTS.md, keine Ledger |

### 2.4 `test_gh48_scaffold_templates.py` – Gerüst/Vorlagen (10 Fälle)

| Fall | Vor | Aktion | Erwartet |
|---|---|---|---|
| `test_missing_file_is_created_with_vibe_directory` | keine `.gitignore` | `ensure_gitignore` | „created", Zeile `.vibe/` |
| `test_existing_file_is_appended_without_overwriting` | fremder Inhalt | `ensure_gitignore` | „appended", Inhalt bleibt |
| `test_an_existing_vibe_entry_is_never_touched` | `.vibe/`, `/.vibe/`, `.vibe` | `ensure_gitignore` | False, byte-identisch |
| `test_cmd_new_writes_gitignore_before_the_initial_commit` | leeres VIBE | `vibe new p1 generic` | `.vibe/` in `.gitignore`, keine `.vibe`-Datei in `git ls-files`, Hinweis „Dashboard", nicht TICKETS.md |
| `test_cmd_init_appends_idempotently_and_mentions_the_gitignore` | Projekt mit `.gitignore` | `vibe init proj` zweimal | ergänzt, Hinweis auf `.gitignore`, zweiter Lauf identisch |
| `test_common_templates_no_longer_contain_the_markdown_ledgers` | `templates/common` | Verzeichnis lesen | kein TICKETS.md/FEEDBACK.md |
| `test_general_rules_are_identical_in_all_template_agents_files` | GENERAL_RULES + 5 AGENTS.md | Blöcke extrahieren | alle identisch |
| `test_general_rules_describe_the_field_based_ticket_close` | GENERAL_RULES | Text prüfen | „## Ticketabschluss", `.vibe/tickets.json`, `TICKET-<ID>.json`, state/commit/test; kein „kein Häkchen" |
| `test_files_list_has_no_tickets_or_feedback_ledger` | `vibe_guide.FILES` | Pfade sammeln | Ledger fehlen, SPEC/AGENTS/project.env/README bleiben |
| `test_readme_template_no_longer_lists_the_ledgers` | README-Vorlage | `_readme` | keine Ledger-Verweise |

### 2.5 `test_gh48_web_api.py` – Web-API (11 Fälle)

| Fall | Vor | Aktion | Erwartet |
|---|---|---|---|
| `test_add_offline_defaults_to_open` | kein Speicher, offline | POST `/api/ticket` add | ok, AP1 open |
| `test_add_accepts_an_optional_state` | offline | add mit state=draft | AP1 draft |
| `test_feedback_add_creates_bug_and_feedback_types` | offline | `/api/feedback` add (bug/ohne kind) | B1 bug, F1 feedback |
| `test_state_action_allows_draft_open_and_in_progress` | AP1 offen | state draft/open/in-progress | jeweils ok, Zustand folgt |
| `test_state_action_rejects_runner_and_github_states` | AP1 offen | state done/blocked/waiting-merge | ok falsch, Meldung nennt Zustand, bleibt offen |
| `test_state_action_rejects_unknown_ticket` | leerer Speicher | state X9 | ok falsch, kein Ticket |
| `test_update_and_delete_open_ticket` | AP1 offen | update, delete | Titel neu, dann entfernt |
| `test_done_ticket_cannot_be_deleted_or_edited_via_the_api` | AP2 done | update/delete | ok falsch, Datei unverändert |
| `test_connected_add_creates_the_issue_first_and_the_gh_ticket` | Issues aktiv, Loopback | add category=bug | ein Issue-POST, GH-201 bug |
| `test_project_detail_assigns_tickets_and_feedback` | task/feature/bug/feedback | GET `/api/project` | tickets task/feature, feedback bug/feedback + kind |
| `test_new_actions_still_require_the_token` | AP1 im Speicher | POST ohne Token | 403, Speicher unverändert |

### 2.6 `test_worknotes_sync.py` – überführt (16 Fälle)

| Fall | Vor | Aktion | Erwartet |
|---|---|---|---|
| `test_modified_agents_md_does_not_block_the_preflight` | AGENTS.md geändert | Preflight | `[]` |
| `test_untracked_agents_md_does_not_block_the_preflight` | AGENTS.md unversioniert | Preflight | `[]` |
| `test_untracked_ticket_file_does_not_block_the_preflight` | `TICKET-AP1.json` unversioniert | Preflight | `[]` |
| `test_other_modified_file_still_blocks_the_preflight` | `notiz.txt` geändert | Preflight | Befund nennt notiz.txt, nicht AGENTS.md |
| `test_other_untracked_file_still_blocks_the_preflight` | `unfertig.txt` | Preflight | Befund nennt unfertig.txt |
| `test_ticket_file_in_a_subfolder_still_blocks_the_preflight` | `sub/TICKET-AP1.json` | Preflight | Arbeitsbaum-Befund für `sub/` |
| `test_modified_agents_md_does_not_dirty_the_workcopy` | Paket komplett, AGENTS.md geändert | `gate_errors` | `[]` |
| `test_ticket_files_do_not_dirty_the_workcopy` | Paket komplett, weitere TICKET-Datei | `gate_errors` | `[]` |
| `test_modified_other_file_still_dirties_the_workcopy` | `impl-AP7.txt` geändert | `gate_errors` | Sauberkeitsbefund |
| `test_agents_and_project_env_are_transported_without_ledgers` | AGENTS.md + project.env + altes TICKETS.md | `copy-notes` ohne `--id` | AGENTS.md + project.env kopiert, TICKETS.md nicht |
| `test_without_id_no_ticket_is_transported` | AP1 im Speicher | `copy-notes` ohne `--id` | keine TICKET-Datei |
| `test_a_complete_ticket_reaches_the_project_store` | AP1 offen, Arbeitskopie done | `sync-ticket` | Exit 0, OK, Übernahme aller Nachweisfelder |
| `test_a_ticket_that_is_not_done_is_refused` | state=in-progress | `sync-ticket` | Exit 1, FEHLT, unverändert |
| `test_a_missing_ticket_file_is_refused` | Datei fehlt | `sync-ticket` | Exit 1, FEHLT, unverändert |
| `test_an_unknown_proof_commit_is_refused` | commit=deadbee | `sync-ticket` | Exit 1, FEHLT, unverändert |
| `test_a_ticket_missing_in_the_project_is_refused` | X9 nur in Arbeitskopie | `sync-ticket` | Exit 1, FEHLT, kein X9 |

### 2.7 `tests/browser/test_gh48_tickets_ui.py` – Browser (3 Fälle)

| Fall | Vor | Aktion | Erwartet |
|---|---|---|---|
| `test_ticket_and_feedback_forms_offer_the_contract_states` | Speicher, kein TICKETS.md | Detailansicht | beide Formulare: Optionen draft/open/in-progress, Voreinstellung open |
| `test_create_a_draft_ticket_offline_and_show_its_state` | Speicher | Ticket mit state=draft anlegen | Speicher state=draft, Karte „Draft", kein TICKETS.md |
| `test_existing_states_from_the_store_are_displayed` | in-progress/blockiert/done | Detailansicht | „In Progress", „BLOCKIERT", „erledigt"; kein „ohne Nachweis" |

Bei fehlendem Playwright wird das Modul übersprungen; fehlt Chromium, wird in
`setUpClass` mit Begründung geskippt. In dieser Umgebung sind Playwright und
Chromium vorhanden, der Fall läuft wirklich (Rotlauf siehe §3).

## 3. Rotlauf (vor der Implementierung)

Alle Befehle wurden tatsächlich ausgeführt.

| Befehl | Ergebnis |
|---|---|
| `python3 -m unittest tests.unit.test_gh48_ticket_store` | Ran 30 tests, FAILED (failures=51); Ursache: `bin/vibe_tickets.py fehlt` |
| `python3 -m unittest tests.unit.test_gh48_tickets_surface` | Ran 16, FAILED (failures=6, errors=8); alte Ledger-Semantik, fehlende `state`-Aktion, fehlendes `sync_ticket` |
| `python3 -m unittest tests.unit.test_gh48_runner_tickets` | Ran 29, FAILED (failures=22, errors=6); alte Block-Schranke, fehlende `transport_ticket`/`sync_ticket` |
| `python3 -m unittest tests.unit.test_gh48_scaffold_templates` | Ran 10, FAILED (failures=11); kein `ensure_gitignore`, alte Vorlagen/Guide |
| `python3 -m unittest tests.unit.test_gh48_web_api` | Ran 11, FAILED (failures=7, errors=1); keine `state`-Aktion, kein Speicher |
| `python3 -m unittest tests.browser.test_gh48_tickets_ui` | Ran 3, FAILED (errors=4); keine Zustandsauswahl, keine Speicherkarten |
| `python3 -m unittest tests.unit.test_worknotes_sync` | Ran 16, FAILED (failures=10); TICKET-Datei blockiert, alte Ledger werden kopiert, `sync-ticket` fehlt |
| `bash scripts/verify.sh quick` | Exit 0: Manifest, Syntax (257 Python/8 Bash/4 JSON), Secrets OK |
| `python3 -m unittest tests.unit.test_ap10_gates` | Ran 34, OK – Nachweis, dass die `runner_support`-Änderung bestehende Läufer-Tests nicht bricht |
| `python3 -m unittest tests.unit.test_b16_branch_name` | Ran 20, OK |

Bereits heute erfüllte Fälle (bewusst kein künstliches Rot): einzelne
Preflight-Fälle zu AGENTS.md, `test_draft_blocked_waiting_and_done_are_never_selected`
(leerer Speicher → `None`), einzelne Web-Ablehnungen ohne Zustandsbezug (durch
die verschärfte Meldungsprüfung wieder rot) und die Token-Pflicht.

## 4. Bestandsumstellung – Inventar

| Modul | Status | Begründung |
|---|---|---|
| `test_worknotes_sync.py` | **überführt** (19→16) | Kern der alten Ledger-Notizen; jetzt AGENTS.md/TICKET-Datei, `copy-notes --id`, `sync-ticket` |
| `runner_support.py` | **erweitert** | kopiert `vibe_tickets.py` (bedingt, damit ältere Stände laufen), Helfer `write_ticket_store` |
| `test_ticket_feedback_processing.py` | offen | alter Markdown-Parser/Blöcke; braucht vollständige Neuableitung auf Speicher |
| `test_feedback_entries.py` | offen | prüft Einrückungs-/Blockregeln des Ledgers (entfallen) |
| `test_feedback_completed.py` | offen | `completed`/done-Schutz jetzt über Speicher; neue Fälle in 2.2 abgedeckt, Altmodul prüft FEEDBACK.md |
| `test_feedback_edit_delete.py` | offen | FEEDBACK.md-Textformat |
| `test_feedback_capture.py` | offen | FEEDBACK.md-Format, Prompt und UI-Felder |
| `test_work_packages.py` | offen | TICKETS.md-Parser |
| `test_b6_ticket_marker_states.py` | offen | 56 Fälle zu BLOCKIERT/WARTET/DRAFT-Markern; Marker sind durch Speicherzustände ersetzt |
| `test_ap5_korbat_waiting_state.py` | offen | WARTET-Marker in Markdown; Vertragsfälle in 2.3 |
| `test_gate_already_integrated.py` | offen | Already-Integrated-Regel bleibt, Quelle jetzt TICKET-Datei; Kernfall in 2.3 |
| `test_runner_package_gates.py`, `test_package_gates.py` | offen | Gate-Fälle auf Markdown-Ticketblöcken |
| `test_f34_backend.py` | offen | done-Schutz auf Markdown-Ledger |
| `test_b3_merged_waiting.py` | offen | Wartezustand über Markdown |
| `test_ap3_korbat_issues_backend.py` | offen | großer Issues-Sync-Test auf TICKETS.md; neue Vertragsfälle in 2.2 |
| `test_ap5_korbat_init_adopt.py`, `test_ap4_korbat_github.py`, `test_ap9_github.py`, `test_ap9_runner_github.py`, `test_b16_github_closure.py` | offen | GitHub-Ebene schreibt künftig in den Speicher |
| `test_project_guide.py` | offen, **baseline-rot** | Berührt TICKETS/FEEDBACK im Guide; Baseline-Eintrag bleibt unangetastet |
| `test_install_lifecycle.py`, `test_project_management.py` | offen, **baseline-rot** | Lebenszyklus/Gerüst mit Ledger-Dateien; baseline-rot unverändert |
| `test_ap4_korbat_rules.py` | offen, **baseline-rot** | Regeln/Vorlagen; baseline-rot unverändert |
| `test_setup_vibe.py`, `test_web_api_security.py`, `test_f29_priority_api.py`, `test_ap11_priority.py` | offen | nutzen noch Ledger-Fixtures; Security-Assertions wurden nicht abgeschwächt |
| Browser `test_tickets_ui.py`, `test_feedback_ui.py`, `test_feedback_completed_ui.py`, `test_project_guide_ui.py`, `test_ap22_project_ui.py`, `test_central_workflows_ui.py` | offen | bedienen die alten Markdown-Formulare/Ledger |

Diese Module sind bewusst unangetastet, weil eine vertragstreue Neuableitung
je Modul mehrere Stunden umfasst und der Auftrag bei zu großem Umfang die
Priorisierung P0 > P1 > P2 zulässt. Sie werden nach der Implementierung rot
sein, bis sie überführt sind; das ist **kein** neuer Regressionsbefall der
Baseline, sondern offene Testmigration.

## 5. Baseline-Auswirkungen

- Keine der 15 baseline-rot verzeichneten Module wurde verändert
  (`test_ap12_github_readiness`, `test_ap4_korbat_rules`,
  `test_ap8_github_checkout`, `test_b13_private_server_runner`,
  `test_b16_runner_wiring`, `test_b17_isolation`, `test_b4_install_empty_runs`,
  `test_b4_pi_agent_dir`, `test_b5_sandbox`, `test_install_lifecycle`,
  `test_project_guide`, `test_project_management`, `test_rebuild_profile`,
  `test_release`, `test_sandbox`). Deren Alt-Einträge bleiben gültig.
- `tests/verify-baseline.json` und `VERIFY_MIN_TESTS` wurden nicht angefasst.
- Netto-Testzahl: +96 Unit-Fälle (neue Module) − 3 (worknotes) + 3 Browser.
  `tests/unit` bleibt deutlich über 2500; keine Streckung, keine Löschung.

## 6. Grenzen, Annahmen und offene Punkte

1. **Kein Volllauf**: Der verbindliche Volllauf (`bash scripts/verify.sh full`)
   gehört zur Abnahme nach der Implementierung; hier lief nur `quick` plus
   zielgerichtete Module. Ein Volllauf jetzt wäre durch die bewusst offenen
   Altmodule ohnehin rot und nicht aussagekräftig.
2. **GH-IDs in `add`**: Der Vertrag sagt „GH-Präfix-IDs sind Issue-Importen
   vorbehalten". Der Test wertet das als `ValueError` bei freier Anlage. Falls
   die Implementierung die ID nur intern schützt, ist der Fall anzupassen.
3. **Geschlossenes Issue → done**: Vertrag §6 fordert `state=done`, die
   Done-Invariante verlangt commit+test. Der Test prüft nur `state`/`github`,
   nicht künstliche Nachweise; die Implementierung muss den internen Übergang
   dokumentieren.
4. **`transport_ticket`-Meldung**: Rückgabe ist `(ok, exclude_ok)`; die
   „klare Meldung" bei fehlendem Ticket wird über die CLI (`FEHLT:`) geprüft.
5. **UI-Zustandsfeld**: Der Browser-Test erwartet Optionswerte
   `draft|open|in-progress` (nicht Labels) und Voreinstellung `open`.
6. **`cmd_init`-Hinweis**: geprüft wird, dass die Ausgabe `.gitignore` nennt;
   der genaue Wortlaut ist nicht vertraglich fixiert.
7. **`_adopt_checked_out_project`** (Hinweis in `notes`) ist nicht direkt
   getestet; dafür wäre eine vollständige Checkout-Fixture nötig.
8. **HTTP-Ablehnungen** der neuen Aktionen akzeptieren 200 oder 400 mit
   `ok=false`; nur 500 gilt als Defekt (bestehende API-Konvention).
9. **Browser**: Playwright/Chromium sind vorhanden; der Fall läuft echt. Auf
   Umgebungen ohne Chromium skippt er mit Begründung statt zu täuschen.
10. **Testnamen** sind stabil gehalten, damit der Implementierer sie als
    Abnahmeliste nutzen kann.

## 7. Abschlussstatus

`partially complete`: P0 (alle neuen Vertragstests) und eine zentrale
P1-Überführung (`test_worknotes_sync.py`) sind fertig und rot ausgeführt;
P1-Rest und P2-Bestandsmigration sind offen (§4). Die Produktdateien
(`bin/`, `templates/`, `docs/features`, `SPEC.md`, `.vibe`,
`docs/import-manifest.json`) wurden nicht verändert.

## 8. Runde 2 — Greenkeeper und Bestandsmigration

Grundlage: Implementierung abgeschlossen; P0-Fälle aus Runde 1 repariert,
danach P1/P2 auf den Vertrag überführt. Jedes Modul wurde tatsächlich
ausgeführt.

### 8.1 P0 (koordinatorseitig als test-eigen gerückt)

| Fall | Korrektur |
|---|---|
| `test_missing_store_yields_empty_rows` | in `MissingStoreTest` ohne `write_store` verschoben; Vorbedingung „kein Speicher" gilt |
| `test_package_close_uses_sync_ticket_without_require_commit` | patcht nur `vibe_packages.sync_ticket` (call_count + `require_commit=False`); `sync_proof` wird als vertragsgemäß entfernt nachgewiesen |
| Browser `test_existing_states_from_the_store_are_displayed` | prüft Ausblenden im Standard und Einblenden über den Toggle, dann „erledigt" |
| `transport_ticket` (Zusatzbefund) | `.git` ist in einer Arbeitskopie eine Datei; Exclude-Pfad über `git rev-parse --git-path info/exclude` |

### 8.2 P1 — Läufer-Greenkeeper (alle grün)

| Modul | Umfang | Ergebnis | Anmerkung |
|---|---|---|---|
| test_ap10_gates | 34 | OK | Fixtures auf `ticket_record`; Merge-Notizfall auf AGENTS.md |
| test_b16_branch_name | 20 | OK | Titel aus dem Speicher statt Markdown |
| test_runner_package_gates | 12 | OK | Speicher-Fixtures; leerer Commit tolerant |
| test_package_gates | 33 | OK | Auswahl/Gate auf Speicher + `TICKET-Datei` |
| test_gate_already_integrated | 24 | OK | Already-Integrated mit `TICKET-<ID>.json`; alte Markdown-Notiz zählt nicht mehr |
| test_b3_merged_waiting | 7 | OK | 19 Marker-/Parserfälle entfernt (Zustände sind Felder; Aussage in GH-48-Modulen); UI-Abschluss bleibt |
| test_ap5_korbat_waiting_state | 21 | OK | Marker-Unit entfernt, CLI/Auswahl/Nova auf Speicher |
| test_b6_ticket_marker_states | 14 | OK | 56 Markerfälle durch 14 Speicherzustandsfälle ersetzt |

`tests/unit/runner_support.py`: `write_project` schreibt `project.env` +
`.gitignore(.vibe/)` + optional den Ticketspeicher; `ticket_record` und
`write_ticket_store`; Fake-Agent schließt `TICKET-<ID>.json` ab.

### 8.3 P2 — Bestandsmodule (alle grün)

| Modul | Umfang | Ergebnis |
|---|---|---|
| test_f34_backend | 17 | OK |
| test_f29_priority_api | 9 | OK |
| test_ap11_priority | 23 | OK |
| test_ap3_korbat_issues_backend | 27 | OK (Config-Fälle erhalten; 25 Ledger-Fälle ersetzt) |
| test_ap4_korbat_github | 21 | OK |
| test_ap9_runner_wiring | 3 | OK |
| test_feedback_capture | 8 | OK |
| test_feedback_completed | 9 | OK |
| test_feedback_edit_delete | 20 | OK |
| test_work_packages | 27 | OK |
| test_ticket_feedback_processing | 9 | OK (Parserfälle ersetzt; Parallelitätsfälle erhalten) |
| test_feedback_entries | 3 | OK (unverändert) |
| test_ap5_korbat_init_adopt | 8 | OK (unverändert) |
| test_web_api_security | 22 | OK (unverändert) |
| test_lifecycle | 17 | OK (unverändert) |
| test_ap9_github | 44 | OK (unverändert) |
| test_ap9_runner_github | 17 | OK (unverändert) |
| test_b16_github_closure | 18 | OK (unverändert) |

Begründete Löschungen ohne Aussageverlust: Markdown-Parser-, Kommentar-,
Checkbox- und Markerfälle, deren Verhalten durch `test_gh48_ticket_store`,
`test_gh48_tickets_surface`, `test_gh48_runner_tickets`, `test_package_gates`
und `test_b6_ticket_marker_states` abgedeckt ist (Speicherfelder statt Text).

## 9. Runde 3 — Setup-Fixture, Browser, Abschluss

### 9.1 Setup-Fixture

`tests/unit/test_setup_vibe.py` führt eine eigene `PROGRAM_FILES`-Kopie; sie
enthält jetzt `vibe_tickets.py` (analog zu `vibe_issues.py`).
`python3 -m unittest tests.unit.test_setup_vibe -v` → **Ran 50, OK**.

### 9.2 Browser-Bestand (alle grün)

| Modul | Umfang | Ergebnis | Änderung |
|---|---|---|---|
| test_tickets_ui | 3 | OK | Fixtures/Assertions auf Speicher; Anlegen/Bearbeiten/Löschen + Bug |
| test_feedback_ui | 3 | OK | Speicher; offene Einträge bearbeitbar |
| test_feedback_completed_ui | 3 | OK | done mit Nachweis; „ohne Nachweis"-Fall durch `in-progress` ersetzt |
| test_ap22_project_ui | 20 | OK | Speicher; Kachelzahlen unverändert; Nachweis-Badge durch Zustandspill ersetzt; GitHub-Import-Fall auf dokumentiertes Verhalten |
| test_project_guide_ui | 4 | OK | Assistent erzeugt keine Ledger mehr |
| test_central_workflows_ui | 2 | OK | Speicher und offene Zahl |

Playwright und Chromium sind in dieser Umgebung verfügbar; die Module liefen
echt (kein Skip). `tests.browser.test_gh48_tickets_ui` → **Ran 3, OK**.

AP22-Anmerkung: Der Import von GitHub-Issues übernimmt laut GH-48-Umsetzung
alle offenen Issues (derselbe Pfad wie der Sync); der Label-Filter der
Oberfläche wirkt nur noch auf „Issues laden". Der Test dokumentiert dieses
Verhalten. Falls der Label-Filter auch beim Import gelten soll, ist das eine
Produktentscheidung außerhalb des Testauftrags.

### 9.3 Baseline-Entscheidungen

- Keines der 15 in `tests/verify-baseline.json` verzeichneten Module wurde
  verändert. `tests/verify-baseline.json` und `VERIFY_MIN_TESTS` blieben
  unberührt.
- Die vier fachnahen Baseline-Module `test_ap4_korbat_rules`,
  `test_project_guide`, `test_project_management`, `test_install_lifecycle`
  wurden nicht angefasst; ihre Klasse/Signatur-Einträge bleiben unverändert.
- Kein Exit-7-Risiko aus diesem Arbeitspaket: alle berührten Module sind grün.

### 9.4 Produktdefekt (gemeldet, inzwischen behoben)

`scripts/setup-vibe.py` führte `vibe_tickets.py` nicht in `PROGRAM_FILES`;
nach einer Installation fehlte das Modul und `bin/vibe` startete nicht
(`test_setup_vibe`, 2 Fälle, plus 15 Folgefälle im Kit). Der Coder hat die
Liste ergänzt; der Test spiegelt sie nun ebenfalls.

### 9.5 Ausgeführte Abschlussbefehle

```
python3 -m unittest tests.unit.test_gh48_ticket_store \
  tests.unit.test_gh48_tickets_surface tests.unit.test_gh48_runner_tickets \
  tests.unit.test_gh48_scaffold_templates tests.unit.test_gh48_web_api \
  tests.unit.test_worknotes_sync tests.unit.test_setup_vibe \
  tests.unit.test_ap3_korbat_issues_backend tests.unit.test_ap10_gates \
  tests.unit.test_b16_branch_name -v
→ Ran 243 tests, OK

python3 -m unittest tests.browser.test_gh48_tickets_ui -v
→ Ran 3 tests, OK

bash scripts/verify.sh quick
→ Exit 0 (Manifest, Syntax 258 Python/8 Bash/4 JSON, Secrets)

Testzahl tests/unit (Methoden): 2668 > VERIFY_MIN_TESTS=2500.
Kein Volllauf ausgeführt (gehört zur Abnahme).
```

### 9.6 Verbleibende Punkte

- Keine offenen Testfälle im GH-48-Umfang; alle migrierten Module grün.
- Offene Produktfrage: Label-Filter beim GitHub-Import (siehe 9.2) —
  Entscheidung liegt beim Koordinator/Coder, nicht beim Test-Agenten.
- Der Volllauf (`scripts/run-tests-parallel.py --dir tests/unit`) wurde
  bewusst nicht ausgeführt; die Abnahme führt ihn aus.

## 10. Runde 4 — Review-Befunde (High + Minor)

Grundlage: `docs/reviews/GH-48-review-1.md`. Der Coder hat beide
Produktseiten korrigiert; hier wurden nur die Testverträge nachgezogen.

### 10.1 High: Doppelprefix in der API-Meldung

Befund: `bin/vibe-web.py` meldete bei Bug-/Feedback-Anlage „BB1/FF1
eingetragen"; die bisherigen `assertIn`-Prüfungen konnten das nicht
entdecken. Korrektur:

- `tests/unit/test_feedback_capture.py`: `message` aus der JSON-Antwort wird
  **exakt** mit `"F1 eingetragen"` verglichen (kein Substring).
- `tests/unit/test_work_packages.py`: `message` exakt `"B1 eingetragen"`
  beim Bug; zusätzlich die Auto-ID-Meldung der Ticket-Anlage exakt
  `"<ID> angelegt"` (gleiche Fehlerklasse).

Damit schlägt „BB1 eingetragen"/„FF1 eingetragen" künftig fehl.

### 10.2 Minor: Auswahlordnung ohne Typ-Tiebreaker

Befund: Die Standardordnung soll strikt `(priority, Speicherposition)` sein;
`_type_rank` als Tiebreaker ist entfernt. Der Vertragstest
`test_standard_order_is_priority_then_store_position` erwartet jetzt
**[AP2, AP1, B1, AP3]** (B1 steht im Speicher vor AP3 und hat gleiche
Priorität wie AP3). Docstring hält ausdrücklich fest, dass die alte Trennung
TICKETS vor FEEDBACK entfällt und bei gleicher Priorität nur die
Speicherposition zählt.

### 10.3 Ausgeführte Befehle

```
python3 -m unittest tests.unit.test_gh48_runner_tickets -v
→ Ran 29 tests, OK

python3 -m unittest tests.unit.test_work_packages tests.unit.test_feedback_capture -v
→ Ran 35 tests, OK

python3 -m unittest tests.unit.test_gh48_ticket_store \
  tests.unit.test_gh48_tickets_surface tests.unit.test_gh48_runner_tickets \
  tests.unit.test_gh48_scaffold_templates tests.unit.test_gh48_web_api \
  tests.unit.test_worknotes_sync tests.unit.test_setup_vibe \
  tests.unit.test_ap3_korbat_issues_backend tests.unit.test_ap10_gates \
  tests.unit.test_b16_branch_name -v
→ Ran 243 tests, OK

bash scripts/verify.sh quick
→ Exit 0 (Manifest, Syntax 258 Python/8 Bash/4 JSON, Secrets)
```

### 10.4 Offene Punkte

- Keine offenen Testpunkte aus den Review-Befunden.
- Unverändert: Produktfrage zum Label-Filter beim GitHub-Import (§9.2) sowie
  der Volllauf als Abnahmeschritt.

## 11. Runde 5 — Abnahme-Volllauf: Überführung der Regressionen

### 11.1 Ausgangslage

Der Abnahme-Volllauf (`bash scripts/verify.sh full`, Umgebung
`pi-aarch64-py3.14-namespaces`) endete mit **Exit 7** und meldete **31 neue
Regressionen**. Ursache war durchweg die GH-48-Umstellung selbst: Die
Testmodule prüften noch die alten Markdown-Ledger (`TICKETS.md`,
`FEEDBACK.md`), den alten Ledger-Nachweis (`[x]`, `Status:`) oder den alten
CLI-Namen `sync-proof`. Nach GH-48 liegen Tickets in `.vibe/tickets.json`,
der Abschluss in der sichtbaren `TICKET-<ID>.json`, und `.vibe/` ist
Laufzeitstand (nicht versioniert). Die 31 Rotfälle verteilen sich auf die 30
unten überführten Module und `test_ap7_korbat_rules` (unversionierter
Stamm-`AGENTS.md`, siehe 11.3).

Die **12 übrigen Baseline-Module** blieben unangetastet; `git diff ad00c0b`
ist für sie leer: `test_ap12_github_readiness`, `test_ap8_github_checkout`,
`test_b17_isolation`, `test_b4_install_empty_runs`, `test_b4_pi_agent_dir`,
`test_b5_sandbox`, `test_install_lifecycle`, `test_project_guide`,
`test_project_management`, `test_rebuild_profile`, `test_release`,
`test_sandbox`. Ihre Alt-Einträge in `tests/verify-baseline.json` bleiben
gültig; die Datei wurde in dieser Runde nicht verändert.

### 11.2 Überführte Module (alle tatsächlich ausgeführt)

| Modul (Fälle) | Ursache der Rotmeldung | Maßnahme | Ergebnis |
|---|---|---|---|
| `test_ap14_runner_continue` (7) | Fixture schrieb den Auftrag als `FEEDBACK.md`-Zeile; IDs `AP14A/AP14B` verletzen die GH-48-ID-Regel (Buchstaben + Ziffern) | `support.ticket_record`; IDs `AP14-1`/`AP14-2`, Assertions mitgezogen | Ran 7, OK |
| `test_ap19_runner_capture` (11) | `FEEDBACK.md`-Fixture | `ticket_record` im Speicher | Ran 11, OK |
| `test_ap2_opencode_agents` (64) | Runner-Fixture auf Ledger | Speicher-Fixture | Ran 64, OK |
| `test_b11_stop_terminates_agents` (14) | Ledger-Fixture | Speicher-Fixture | Ran 14, OK |
| `test_b6_pi_runner_events` (4) | Fake-Agent hakte `TICKETS.md`/`FEEDBACK.md` ab; Prompt enthält keinen `Wortlaut:`-Block mehr | `complete_ticket` schreibt `TICKET-B6.json` auf `state=done`; Fixture auf Speicher | Ran 4, OK |
| `test_b9_self_repair` (14) | Reparatur- und Gate-Fixtures hingen am Markdown-Nachweis; 4 Gate-Fälle parsten Commit-**Listen** aus `FEEDBACK.md` | Nachweis über `TICKET-<ID>.json`; Reparaturerkennung über „Reparatur“ statt „Wortlaut:“; 4 Parser-Fälle entfernt (der Vertrag kennt genau ein Commit-Hash-Feld; Abdeckung in `test_gh48_ticket_store` und `test_package_gates`); Commit nur bei gestagten Änderungen | Ran 14, OK |
| `test_f21_agents_preflight` (22) | Ledger-Fixture; ein Fall commitete unnötig `.vibe/project.env` | Speicher-Fixture; Commit entfernt | Ran 22, OK |
| `test_f22_preflight_assist` (20) | `FEEDBACK`-Konstante | `ticket_record` | Ran 20, OK |
| `test_f25_session_continue` (16) | Ledger-Fixture; `commit_all` ohne Änderung (`.vibe/` ist ignoriert) | Speicher-Fixture; Commit nur bei gestagten Änderungen | Ran 16, OK |
| `test_f27_keep_changes` (14) | Ledger-Konstante | Speicher-Fixture | Ran 14, OK |
| `test_f31_inherited_opencode_password` (4) | Fall commitete die Laufzeitdatei `.vibe/project.env` | Commit entfernt; Datei bleibt für den Läufer lesbar | Ran 4, OK |
| `test_output_view_f19_runner` (5) | Ledger-Fixture | Speicher-Fixture | Ran 5, OK |
| `test_b1_project_agent_models` (15) | Ledger-Fixture | Speicher-Fixture | Ran 15, OK |
| `test_run_control` (30) | `FEEDBACK.md`/`TICKETS.md`-Fixture | Speicher + `.gitignore`; Signatur von `write_project` bereinigt | Ran 30, OK |
| `test_v026_run_isolation` (18) | Ledger-Fixture | Speicher-Fixture | Ran 18, OK |
| `test_v027_limits` (16) | Ledger-Fixture | Speicher-Fixture | Ran 16, OK |
| `test_b13_private_server_runner` (10) | Ledger-Fixture | Speicher-Fixture | Ran 10, OK (1 Skip); Baseline-Restrot entfällt, Eintrag überfällig, **unangetastet** |
| `test_ap4_korbat_rules` (11) | SPEC-Assertion prüfte den englischen Kanontext; die SPEC führt die deutsche Fassung | Assertion auf den deutschen Wortlaut umgestellt | Ran 11, OK; Baseline-Eintrag überfällig, **unangetastet** |
| `test_b16_runner_wiring` (6) | Ledger-Fixture; Wartezustand wurde aus `FEEDBACK.md` gelesen | Speicher-Fixture; `waiting-merge`, `waiting_note`, `blocked_reason` über Felder | Ran 6, **1 Failure = exakte Alt-Baseline-Signatur** (11.4) |
| `test_pause_after_package` (16) | Ledger-Fixture; Repo-Init kam erst nach dem Schreiben | Repo + `.gitignore` vor dem Speicher | Ran 16, OK |
| `test_project_agents` (25) | `RunnerModelTest` schrieb `FEEDBACK.md`/`TICKETS.md` | Speicher-Fixture | Ran 25, OK |
| `test_ap7_korbat_runner` (8) | Hash-Guard-Fixture auf Ledger; Blockiert-Prüfung las `FEEDBACK.md` | Speicher; offener Zustand über `state` | Ran 8, OK |
| `test_ap5_korbat_project_env_transport` (7) | `sync-proof` und Ledger-Nachweis | `sync-ticket` und `TICKET-T1.json` (Test umbenannt) | Ran 7, OK |
| `test_ap3_korbat_surfaces` (25) | Alle Assertions lasen Markdown-Blöcke/`Status:`-Zeilen | Speicherfelder; zwei Fälle vertragstreu umbenannt: `state=open` als Vorgabe, `state=draft` nur bei ausdrücklicher Angabe | Ran 25, OK |
| `test_ap4_korbat_worktrees_sessions` (27) | Arbeitskopie erhielt `FEEDBACK.md`/`TICKETS.md`-Kopien; `package close` prüfte den Ledger | Kopien entfernt, `TICKET-F1.json` im Worktree, Abschluss über `state`/`commit`/`test`; `shlex`-Import nachgezogen, `shutil`-Kopien entfallen | Ran 27, OK |
| `test_ap19_sessions_cli` (19) | Ledger-Fixture | Speicher-Fixture | Ran 19, OK |
| `test_costs` (36) | `package_ids`/Titel kamen aus `FEEDBACK.md`/`TICKETS.md` | `write_tickets`-Helfer, Speicher | Ran 36, OK |
| `test_costs_refresh` (9) | erbt `CostFixture` aus `test_costs` | keine eigene Änderung nötig; die migrierte Basis-Fixture wirkt | Ran 9, OK |
| `test_fritz_reconnect` (28) | Ledger-Fixture | Speicher + `.gitignore` | Ran 28, OK |
| `test_ap06_github` (54) | Import/Idempotenz/Kollision schrieben und lasen `TICKETS.md` | Speicher; Kollisionstest auf das dokumentierte Retry-Verhalten umgestellt (`added=1`, Fremd- und Importticket bleiben) | Ran 54, OK |

### 11.3 Produktbefunde

1. **TYPE-Kollision in `bin/vibe-run.sh`.** Die Paketauswahl exportierte den
   Tickettyp als `TYPE` und überschrieb damit den Projekttyp aus
   `.vibe/project.env` (z. B. `android`); die typabhängige Abnahme lief ins
   Leere. Der Coder hat den Namen auf `TICKET_TYPE` geändert
   (`bin/vibe-run.sh:514`). Nachweis: `tests.unit.test_b17_runner_isolation`
   → **Ran 7, OK** (enthält den Android-Abnahmefall im Sandkasten). Am Test
   war dafür nur die Speicher-Fixture nötig.
2. **Stamm-`AGENTS.md` gedriftet.** Die Datei ist über `.gitignore:23`
   (`/AGENTS.md`) eine unversionierte Nutzerdatei; ihr verwalteter
   Regelblock wich seit GH-46 von `GENERAL_RULES` ab. Der Coder hat den
   Block byte-identisch synchronisiert. Nachweis:
   `tests.unit.test_ap7_korbat_rules` → **Ran 9, OK**, insbesondere
   `test_repository_agents_file_carries_the_general_rules_verbatim`. Dieser
   Fall war der 31. Rotfall; am Test wurde nichts geändert. Der notwendige
   Nutzer-Handgriff am Integrationsstand ist in `docs/features/GH-48.md`
   unter „Nach dem Merge: Nutzer-Handgriffe“ dokumentiert.

### 11.4 Baseline-Abgleich `test_b16_runner_wiring`

```
python3 -m unittest tests.unit.test_b16_runner_wiring -v
→ Ran 6 tests, FAILED (failures=1)

FAIL: test_diverged_integration_branch_blocks_with_divergiert
      (tests.unit.test_b16_runner_wiring.DivergenceTest)
AssertionError: '' is not true : 0 verwaiste Einträge beendet, 0 laufen
weiter, 0 nicht prüfbar. …
```

Der Fehler ist der bekannte Alt-Bestand: Der Lauf bricht zwar ab
(„ABBRUCH: Der Lauf ist blockiert“), aber die erwartete `BLOCKIERT:`-Zeile
mit „divergiert“ entsteht in dieser Umgebung nicht. Die Signatur wurde mit
denselben Funktionen reproduziert, die der Prüfbericht nutzt
(`scripts/run-tests-parallel.py: error_details`,
`scripts/verify_engine.py: failure_signature`):

- Klasse: `AssertionError`
- Meldung: `'' is not true : 0 verwaiste Einträge beendet, 0 laufen weiter, 0 nicht prüfbar.`
- Signatur: `sha256:0c2a6bec59b9ddee0f95b5d27e168310b0a1cf77db17d4c9f69c66a68d650a2e`
- Committed Baseline (`tests.unit.test_b16_runner_wiring`): identisch.

Damit entspricht der Restrot exakt dem Baseline-Eintrag (Testname,
Klasse und Signatur); am Branchpunkt war derselbe Fall bereits identisch
reproduziert worden. **Keine Test- und keine Baseline-Änderung.** Der
Läufer-Volllauf wertet den Fall folglich als bekannt rot
(`BASELINE-OK`), sofern die Umgebung dem Label
`pi-aarch64-py3.14-namespaces` entspricht.

### 11.5 Umgebungsabweichung

Das Protokoll des ursprünglichen Abnahme-Volllaufs
(`/tmp/…/sh_20b4a5a0d001scVExuQBTnJ5FD.out`) war in den späteren Sitzungen
nicht mehr lesbar; der Pfad existiert nicht mehr. Die Diagnosen wurden
deshalb direkt über Modulausführungen gewonnen (Tabelle 11.2). Die
Zuordnung „Modul → Ursache“ stützt sich auf den Testdiff gegen `ad00c0b`
und die tatsächlichen Läufe, nicht auf das verlorene Protokoll.

### 11.6 Ausgeführte Befehle (alle selbst beobachtet)

```
python3 -m unittest tests.unit.test_project_agents -v
→ Ran 25 tests, OK

python3 -m unittest tests.unit.test_b17_runner_isolation
→ Ran 7 tests, OK

python3 -m unittest tests.unit.test_ap7_korbat_rules
→ Ran 9 tests, OK

python3 -m unittest tests.unit.test_b16_runner_wiring -v
→ Ran 6 tests, FAILED (failures=1), Alt-Signatur (11.4)

# 30 Module aus 11.2 parallel (xargs -P 6, je eigenes unittest-Modul):
→ 29 × OK, test_b16_runner_wiring 1 Failure (Alt-Signatur)
→ Summe der Modulfälle: 555

bash scripts/verify.sh quick
→ Exit 0
   OK: 71 Dateien stimmen mit docs/import-manifest.json überein.
   OK: 258 Python-, 8 Bash- und 4 JSON-Datei(en) syntaktisch geprüft.
   OK: keine Geheimnisse erkannt.

grep -rc "def test_" tests/unit --include="test_*.py" | awk -F: '{s+=$2} END {print s}'
→ 2661  (> VERIFY_MIN_TESTS=2500)
```

Kein Volllauf in dieser Runde (der Läufer führt sein eigenes Vollgate auf dem
Integrationsstand aus), keine Produkt- und keine Baseline-Änderung durch den
Test-Agenten.

### 11.7 Restzustand

- Alle 30 überführten Module sind grün; einzige Ausnahme ist
  `test_b16_runner_wiring` mit der exakten Alt-Baseline-Signatur (11.4).
- `test_b13_private_server_runner` und `test_ap4_korbat_rules` sind grün,
  ihre Baseline-Einträge sind damit überfällig. Sie wurden hier bewusst
  **nicht** entfernt; das gehört in eine reviewte Baseline-Änderung.
- `test_ap7_korbat_rules` und `test_b17_runner_isolation` sind grün
  (Produktbefunde 11.3).
- Keine offenen Testpunkte aus GH-48; Testzahl 2661 bei Mindestmaß 2500.

## 12. Runde 6 — b13-Basisfall

### 12.1 Diagnose

Der zweite Abnahme-Volllauf meldete genau eine neue Regression:
`tests.unit.test_b13_private_server_runner` mit `RuntimeError`
(`sha256:231d9084…`). Ursache war ausschließlich die Fixture, nicht die
fachliche Prüfung:

- `B13RunnerFixture` schreibt in
  `SandboxPrivateServerTest.test_sandboxed_run_starts_the_private_server_inside_the_sandbox`
  nur `.vibe`-Dateien (`project.env`-Ergänzung, `permissions.json`).
- GH-48 legt `.vibe/` als Laufzeitstand in die `.gitignore` der
  Fixture-Projekte (`runner_support.write_project`). Am Branchpunkt
  (`ad00c0b`) existierte diese `.gitignore`-Zeile nicht; dort entstanden
  `FEEDBACK.md`/`TICKETS.md` mit committbarem Inhalt.
- Das strenge `support.commit_all(self.project)` läuft deshalb mit
  „nothing to commit, working tree clean“ in einen `RuntimeError` und bricht
  den Fall vor seiner eigentlichen Assertion ab.
- Der Fall wird nur in bereinigter Umgebung ausgeführt (ohne
  `VIBE_SANDBOX_ACTIVE`), wie `verify.sh full` sie setzt; in der
  Agenten-Shell (`VIBE_SANDBOX_ACTIVE=1`) greift
  `env_support.skip_if_sandbox_nested` und der Fall wird übersprungen.

### 12.2 Maßnahme (keine Abschwächung)

In `tests/unit/test_b13_private_server_runner.py` ersetzt ein lokaler Helfer
`commit_changed_fixture_state(project)` das strenge Commit an genau dieser
Stelle:

- Er prüft zuerst `git status --porcelain`; nur bei nichtleerem Stand wird
  `support.commit_all(project)` aufgerufen.
- Ein leerer Stand ist zulässig (das Projekt ist dann bereits committet) und
  kein Testfehler; ein Git-Fehler beim Statusabruf bleibt ein Fehler.
- Die fachlichen Assertionen des Falls (Rückgabecode 0, „Sandbox: on“,
  genau ein Serve-Aufruf, TMPDIR im Sandbox-Zustandsordner, Serverdatei
  entfernt) sind unverändert. Es wurde nichts geskippt und keine Erwartung
  abgeschwächt.

### 12.3 Entscheidungsregel — Ausgang: Signatur stabil und bereits Baseline

Der Fall wurde zweimal in bereinigter Umgebung mit je frischem
`tempfile`-Projekt ausgeführt; Fehlerklasse und Meldung wurden mit denselben
Funktionen bestimmt, die der Prüfbericht nutzt
(`scripts/run-tests-parallel.py: error_details`, d. h. erste
Traceback-Ausnahme, und `scripts/verify_engine.py: failure_signature`):

| Lauf | Klasse | Meldung (normalisiert) | Signatur |
|---|---|---|---|
| 1 | `AssertionError` | `2 != 0 : Läufer bricht ab:` | `sha256:6b4d5e86d4f2f0bc301b68b29c2dabb1672925b24eac926a8b5d10f7bf39a632` |
| 2 | `AssertionError` | `2 != 0 : Läufer bricht ab:` | `sha256:6b4d5e86d4f2f0bc301b68b29c2dabb1672925b24eac926a8b5d10f7bf39a632` |

Beide Läufe sind identisch, enthalten also keine volatilen Laufkennungen;
die Normalisierung entfernt die unterschiedlichen Temp-Pfade
(`…/tmpy7yfdgar/…` vs. `…/tmpohl5vr8_/…`) vollständig. Die Signatur ist
zugleich **exakt der bestehende Baseline-Eintrag** für dieses Modul
(`AssertionError`, `sha256:6b4d5e86…`) in
`tests/verify-baseline.json` (Umgebung
`pi-aarch64-py3.14-namespaces`).

Damit tritt der erwartete Fall ein, dass **keine neue Signatur entsteht**:
`verify_engine.known_signature` vergleicht Modul und Signatur; der Fall wird
vom Volllauf als bekannt rot (`BASELINE-OK`) gewertet. Ein zusätzlicher
Eintrag mit gleicher Modul-/Signaturkombination wäre ein Duplikat ohne
Wirkung und wurde deshalb **nicht** ergänzt; `tests/verify-baseline.json`
bleibt in dieser Runde unverändert, ebenso `VERIFY_MIN_TESTS` (2500) und der
Alt-Eintrag. Ein Umgebungs-Skip (Variante „Signatur instabil“) war nicht
erforderlich.

### 12.4 Evidenz zur Baseline-Kontinuität

- Der Alt-Eintrag ist `AssertionError` mit `sha256:6b4d5e86…`. Da die
  Signatur Modul, Klasse und normalisierte Meldung umfasst, stammt er aus
  genau dieser Fehlerklasse und Meldung, also aus derselben Ursachenfamilie
  „bwrap in dieser Umgebung nicht startbar“ (vgl. `test_sandbox`-Baseline).
- Die reale Assertion zeigt unverändert diese Umgebungsbedingung: Der Läufer
  endet mit `rc 2` („ABBRUCH: Sandbox ist eingeschaltet, aber nicht
  startbar. Der Agent läuft nicht ohne Sandbox.“), weil der Kernel
  unprivilegierte Benutzernamensräume verbietet (`bwrap: No permissions to
  create a new namespace …`). Es ist kein Codefehler und keine GH-48-Regression.
- Gegenprobe Branchpunkt: `git show ad00c0b:tests/unit/runner_support.py`
  enthält weder `.gitignore`-Erzeugung noch `.vibe`-Ledger; die damalige
  Fixture committete `FEEDBACK.md`/`TICKETS.md` und lief deshalb nicht in den
  Fixture-Crash. Der ursprüngliche Alt-Eintrag konnte also nur aus der
  fachlichen Assertion stammen — genau der Signatur, die nach dem Fixture-Fix
  wieder erreicht wird.
- Nur der Fehlerort im Traceback hat sich verschoben (Zeile 643
  Fixture-Commit → Zeile 690 fachliche Assertion); Meldungstext und Klasse
  sind unverändert, was die identische Signatur belegt.

### 12.5 Ausgeführte Befehle (alle selbst beobachtet)

```
# vor dem Fix (Rotlauf, bereinigte Umgebung):
env -u VIBE_SANDBOX_ACTIVE python3 -m unittest tests.unit.test_b13_private_server_runner -v
→ Ran 10 tests, FAILED (errors=1)
   ERROR test_sandboxed_run_…: RuntimeError: On branch main
   nothing to commit, working tree clean (Zeile 643)

# nach dem Fix, Lauf 1 (bereinigte Umgebung, frisches Tempverzeichnis):
env -u VIBE_SANDBOX_ACTIVE python3 -m unittest tests.unit.test_b13_private_server_runner -v
→ Ran 10 tests, FAILED (failures=1)
   AssertionError „2 != 0 : Läufer bricht ab:“
   Signatur sha256:6b4d5e86… (12.3)

# nach dem Fix, Lauf 2 (bereinigte Umgebung, frisches Tempverzeichnis):
env -u VIBE_SANDBOX_ACTIVE python3 -m unittest tests.unit.test_b13_private_server_runner -v
→ Ran 10 tests, FAILED (failures=1)
   identische Klasse/Meldung/Signatur sha256:6b4d5e86…

# normaler Lauf (Agenten-Sandbox, VIBE_SANDBOX_ACTIVE=1):
python3 -m unittest tests.unit.test_b13_private_server_runner -v
→ Ran 10 tests, OK (skipped=1)

bash scripts/verify.sh quick
→ Exit 0
   OK: 71 Dateien stimmen mit docs/import-manifest.json überein.
   OK: 258 Python-, 8 Bash- und 4 JSON-Datei(en) syntaktisch geprüft.
   OK: keine Geheimnisse erkannt.
```

Kein Volllauf in dieser Runde (der Läufer führt sein eigenes Vollgate auf dem
Integrationsstand aus); keine Produktänderung, keine Baseline-Änderung und
keine Änderung der Testanzahl (2661).
