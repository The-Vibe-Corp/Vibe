# TICKETS — vibe

SPEC.md ist maßgeblich.
Reihenfolge: P0 vor P1 vor P2; Abhängigkeiten beachten.
Jedes Ticket ist genau ein Arbeitspaket.
Abhaken nur nach erfüllten Kriterien, erfolgreichen relevanten Tests und Review.
Nachweise unter dem Ticket: Commit, Testbefehle, Reviewdatei, Dokumentation.
Ein fehlender externer Dienst bedeutet BLOCKIERT, nicht erledigt.

- [x] AP01 GUideline ergänzungen für coding agents
  Beschreibung: die guidelines für coding agents sollen um folgende aspekte verpflichtend ergänzt werden:
  
  - KISS als verpflichtendes Prinzip
  - Clean Code als code style/guideline
  - Caching als performance optimierung (aber mit entsprechend notwendiger invalidierung)
  dies soll für alle neuen, aber auch für bestehende projekte gelten und automatisch übernommen werden
  Commit: `5a2e628`; Test: test_general_rules_require_kiss_clean_code_and_safe_caching,
  test_all_shipped_project_templates_contain_the_coding_guidelines,
  test_repository_agents_file_contains_the_coding_guidelines,
  test_init_replaces_an_outdated_rules_block_with_the_coding_guidelines,
  test_cmd_run_updates_the_managed_rules_of_an_existing_project,
  test_cmd_run_adds_the_rules_block_to_an_existing_project_without_one,
  test_cmd_run_aborts_when_the_general_rules_cannot_be_updated
  (tests/unit/test_project_management.py, tests/unit/test_project_agents.py; 7 Tests).
  Prüfungen: `bash scripts/verify.sh quick` Exit 0; `bash scripts/verify.sh full`
  Exit 0 (863 Unit- + 58 Browser-Tests, 921 erkannt) in Bubblewrap-Umgebung mit
  beschreibbarem `/tmp` und ohne geerbtes `SANDBOX`.
  Review: `docs/reviews/AP01-review-1.md` (PASS; 0 Critical/High/Medium, 3 Minor).
  Dokumentation: `docs/features/AP01.md`; Trilium `B34A8yyWkjCo`.

- [x] AP02 Verpflichtender Test Agent
  Beschreibung: Für jedes Projekt (bestehend und neu) muss es einen Agenten
  geben, welcher eigenständig und unabhängig die Tests schreibt. Dieser darf
  nicht von dem Coding- oder Reviewer-Agenten beeinflusst werden. Sein Ziel ist
  es, sinnvolle Tests für die jeweilige Aufgabe zu erstellen, zu beschreiben und
  zu coden, so dass diese vom Reviewer oder Coding-Agenten aufgerufen werden
  können.

  Nur der Test-Agent darf Tests schreiben und nur diese Tests zählen.
  Commit: `fc102b2`; Test: test_init_adds_the_test_agent_and_tester_to_an_existing_project,
  test_init_preserves_an_existing_test_agent_and_tester,
  test_init_does_not_write_through_a_test_agent_symlink,
  test_all_shipped_project_templates_contain_the_test_agent_rule,
  test_all_shipped_project_templates_configure_the_tester,
  test_general_rules_require_an_independent_test_agent,
  test_repository_agents_file_contains_the_test_agent_rule,
  test_shipped_test_agent_template_is_complete,
  test_cmd_run_ensures_the_independent_test_agent_for_an_existing_project,
  test_cmd_run_aborts_when_the_test_agent_cannot_be_created,
  test_existing_and_new_projects_receive_the_test_agent,
  test_register_projects_keeps_an_existing_test_agent
  (tests/unit/test_project_management.py, tests/unit/test_project_agents.py,
  tests/unit/test_setup_vibe.py; 13 Tests inkl. angepasstem Bestandstest).
  Prüfungen: `bash scripts/verify.sh quick` Exit 0; `bash scripts/verify.sh full`
  Exit 0 (875 Unit- + 58 Browser-Tests, 933 erkannt) in Bubblewrap-Umgebung mit
  beschreibbarem `/tmp` und ohne geerbtes `SANDBOX`/`VIBE_*`.
  Review: `docs/reviews/AP02-review-1.md` (PASS; 0 Critical/High/Medium, 4 Minor).
  Dokumentation: `docs/features/AP02.md`; Trilium `3XWCoX6XbDy7`.

- [x] V-001 Unveränderten Bestand aufnehmen und absichern
  Priorität: P0
  Abhängigkeiten: keine
  Umfang: Importmanifest prüfen, Dateien und externe Abhängigkeiten erfassen,
  CLI-Kommandos, API-Routen und UI-Funktionen inventarisieren.
  Akzeptanz: docs/baseline.md enthält je Funktion den tatsächlichen Prüfstatus;
  importierte Dateien stimmen mit dem Manifest überein; keine Geheimnisse im Git;
  aktive Installation unverändert; fehlende ursprüngliche Installer dokumentiert.
  Tests: reproduzierbare Manifestprüfung; Syntaxchecks; keine echten Modellaufrufe.

- [x] V-002 Sichere Entwicklungs- und Prüfumgebung einrichten
  Priorität: P0
  Abhängigkeiten: V-001
  Umfang: scripts/verify.sh quick|full, Teststruktur, isolierte Fixtures.
  Akzeptanz: temporäre HOME-/VIBE-Verzeichnisse, eigene Ports und klare Exitcodes;
  fehlende Tests gelten nicht als grüne vollständige Abnahme;
  Projekt über .vibe/project.env ohne Android-Abnahme prüfbar.
  Tests: erfolgreicher Check, absichtlich fehlschlagender Check, unbekannter Modus,
  fehlende Werkzeuge; produktive Konfiguration bleibt unverändert.
  Commit: 8db7223; Test: tests.unit.test_verify_script.VerifyQuickTest.test_successful_check_runs_isolated_and_cleans_up
  Prüfungen: `bash scripts/verify.sh quick` Exit 0; `bash scripts/verify.sh full` Exit 0 (257 Tests erkannt)
  Review: docs/reviews/V-002-review-1.md (PASS, keine Critical/High/Medium)
  Dokumentation: docs/features/V-002.md; Trilium `fo1x30HjK74P`

- [x] V-003 Prozessaufrufe und Eingaben absichern
  Priorität: P0
  Abhängigkeiten: V-002
  Umfang: alle externen Aufrufe und Pfadübergaben prüfen.
  Akzeptanz: Argumentlisten für strukturierte Aufrufe; explizite Shellgrenzen;
  keine Befehlsinjektion über Namen, Pfade oder Agenten;
  Leseaktionen führen keine Projektprogramme aus.
  Tests: Leerzeichen, Anführungszeichen, Shellmetazeichen, ungültige Pfade,
  fehlerhafte Programme und Timeout.
  Commit: ba0dafe; Test: tests.unit.test_process_safety.ProcessRunnerTest.test_argument_list_keeps_spaces_quotes_and_shell_metacharacters
  Prüfungen: `bash scripts/verify.sh quick` Exit 0; `bash scripts/verify.sh full` Exit 0 (275 Tests erkannt)
  Review: docs/reviews/V-003-review-1.md (PASS, keine Critical/High/Medium; 2 Minor)
  Dokumentation: docs/features/V-003.md; Trilium `yaaK4lPOlg99`

- [x] V-004 Web-API absichern und Health-Endpunkt ergänzen
  Priorität: P0
  Abhängigkeiten: V-002
  Umfang: Authentisierung, Host-/Origin-Prüfung, Requestlimits, Health.
  Akzeptanz: nur Loopback; nicht autorisierte Schreibzugriffe abgelehnt;
  Health identifiziert vibe und seine Instanz ohne Geheimnisse auszugeben;
  keine Tokens in Logs; strukturierte Fehler.
  Tests: fehlendes/falsches Token, fremder Origin/Host, ungültiges JSON,
  übergroße Requests, parallele Anfragen.
  Commit: 94893cd; Test: tests/unit/test_web_api_security.py (22 Tests)
  Prüfungen: bash scripts/verify.sh quick (Exit 0); bash scripts/verify.sh full (Exit 0, 297 Tests)
  Review: docs/reviews/V-004-review-1.md (PASS), -2.md (PASS), -3.md (PASS)
  Dokumentation: docs/features/V-004.md; Trilium `VrwC3K1wD5hI`

- [x] V-005 Atomare Dateizugriffe und sichere Sicherungen
  Priorität: P0
  Abhängigkeiten: V-002
  Umfang: gemeinsame Storage-Schicht für Konfigurationen und Agenten.
  Akzeptanz: konkurrierende Änderungen erkannt; atomare Writes;
  kollisionsfreie Sicherungen; Wiederherstellung möglich;
  kein falsches Sicherheitsversprechen auf FUSE/NTFS.
  Tests: gleichzeitiges Speichern, Schreibfehler, unterbrochener Write,
  Namenskollision bei Sicherungen, Restore.
  Commit: c9cdd49; Test: tests/unit/test_storage.py (32 Tests, u. a.
  test_concurrent_saving_allows_exactly_one_writer,
  test_interrupted_write_leaves_target_untouched,
  test_backups_in_the_same_microsecond_do_not_collide)
  Prüfungen: `bash scripts/verify.sh quick` Exit 0; `bash scripts/verify.sh full` Exit 0
  (317 Unit- + 14 Browser-Tests, 331 erkannt) im geprüften Stand /tmp/vibe-v005-build
  Review: docs/reviews/V-005-review-1.md (CHANGES REQUIRED), -2.md (CHANGES REQUIRED),
  -3.md (CHANGES REQUIRED), -4.md (PASS, keine Critical/High/Medium/Minor)
  Dokumentation: docs/features/V-005.md; Trilium `XQO2Qcrg1tvI`

- [x] V-006 Quellen-, Installations- und Laufzeitpfade trennen
  Priorität: P0
  Abhängigkeiten: V-001, V-005
  Umfang: Pfadmodell und Konfigurationspriorität definieren.
  Akzeptanz: separates Dev-Profil; produktive Instanz unverändert;
  Pfade und Ports konfigurierbar; Modulimport ohne Nebenwirkungen;
  persönliche Einstellungen überschreiben Defaults.
  Tests: alternativer Arbeitsbereich, fehlende Verzeichnisse, Leerzeichen,
  abweichender Port, Import ohne Prozessstart.
  Commit: fb85817; Test: tests/unit/test_vibe_paths.py (32 Tests, u. a.
  test_dev_profile_controls_only_its_own_agent_session,
  test_dev_profile_uses_its_own_paths_and_ports,
  test_importing_the_web_module_writes_no_token_or_instance_file)
  Prüfungen: `bash scripts/verify.sh quick` Exit 0; `bash scripts/verify.sh full` Exit 0
  (425 Unit- + 34 Browser-Tests, 459 erkannt) im isolierten Prüfstand mit schreibbarem /tmp
  Review: docs/reviews/V-006-review-1.md (CHANGES REQUIRED), docs/reviews/V-006-review-2.md (PASS, 0 Critical/High/Medium, 2 Minor)
  Dokumentation: docs/features/V-006.md; Trilium `f0Mq8GVg7hhf`

- [x] V-007 opencode-Kompatibilitätsadapter erstellen
  Priorität: P0
  Abhängigkeiten: V-001, V-002
  Umfang: tatsächlich installierte Version und unterstützte CLI/API erfassen.
  Akzeptanz: docs/compatibility.md nennt geprüfte Version und Verfahren;
  Modelllisting, Agenten, MCP und Serverstart über einen Adapter;
  keine ungeprüfte mcp.servers-Annahme; unbekannte Version verständlich behandelt.
  Tests: Fixtures unterstützter Versionen, unerwartete Ausgabe, fehlendes Binary,
  Fehlercode und Timeout.
  Commit: 87d1d12; Test: tests/unit/test_opencode_adapter.py (39 Tests, u. a.
  test_tested_version_fixture_is_supported,
  test_mixed_classic_config_is_refused_and_kept_unchanged)
  Prüfungen: `bash scripts/verify.sh quick` Exit 0; `bash scripts/verify.sh full` Exit 0
  (464 Unit- + 34 Browser-Tests, 498 erkannt) im isolierten Prüfstand mit schreibbarem /tmp
  Review: docs/reviews/V-007-review-1.md (CHANGES REQUIRED, 1 Medium),
  docs/reviews/V-007-review-2.md (PASS, 0 Critical/High/Medium, 1 Minor)
  Dokumentation: docs/compatibility.md, docs/features/V-007.md; Trilium `B8WSE271Yfe5`

- [x] V-008 Projektverwaltung und Vorlagen regressionssicher machen
  Priorität: P1
  Abhängigkeiten: V-003, V-006
  Umfang: Roots, Discovery, Init und Neuanlage.
  Akzeptanz: gleiche Projektnamen eindeutig; Init erhält bestehende Dateien;
  Entfernen eines Roots löscht nichts; Typen sind erweiterbar.
  Tests: Git-Verzeichnis und Git-Datei, doppelte Namen, Symlinks,
  nicht lesbare Ordner, bereits vorbereitetes Projekt.
  Commit: 3763532; Test: tests/unit/test_project_management.py (12 Tests, u. a.
  test_duplicate_names_from_roots_with_equal_basenames_stay_unique,
  test_init_does_not_write_through_a_broken_symlink)
  Prüfungen: `python3 -m unittest tests.unit.test_project_management -v` 12 Tests OK;
  `bash scripts/verify.sh quick` Exit 0; `bash scripts/verify.sh full` Exit 0
  (476 Unit- + 34 Browser-Tests, 510 erkannt) im isolierten Prüfstand mit schreibbarem /tmp
  Review: docs/reviews/V-008-review-1.md (PASS, 0 Critical/High/Medium, 3 Minor),
  docs/reviews/V-008-review-2.md (PASS, 0 Critical/High/Medium, 0 Minor)
  Dokumentation: docs/features/V-008.md; Trilium `SC3Jtp3csTnz`

- [x] V-009 Ticket- und Feedbackverarbeitung stabilisieren
  Priorität: P1
  Abhängigkeiten: V-005
  Umfang: Parser, IDs, Status und neue Feedbackeinträge.
  Akzeptanz: Kommentare ignoriert; stabile IDs; BLOCKIERT bleibt offen;
  fehlende Nachweise werden sichtbar; keine Doppel-IDs bei Parallelzugriff.
  Tests: mehrzeilige Blöcke, Kommentare, defekte Checkboxen, fehlender Commit,
  gleichzeitige Einträge und nicht vorhandene Dateien.
  Commit: 46138e3; Test: tests/unit/test_ticket_feedback_processing.py (28 Tests, u. a.
  test_template_and_multiline_comments_are_not_entries,
  test_broken_checkboxes_keep_their_id_and_stay_open,
  test_parallel_processes_get_unique_ids,
  test_parallel_api_requests_get_unique_ids)
  Prüfungen: `python3 -m unittest tests.unit.test_ticket_feedback_processing -v`
  28 Tests OK; `python3 -m unittest tests.unit.test_feedback_capture
  tests.unit.test_feedback_edit_delete tests.unit.test_feedback_completed
  tests.unit.test_feedback_entries -v` 40 Tests OK;
  `bash scripts/verify.sh quick` Exit 0; `bash scripts/verify.sh full` Exit 0
  (504 Unit- + 34 Browser-Tests, 538 erkannt) im Mount-Namespace mit tmpfs auf /tmp
  Review: docs/reviews/V-009-review-1.md (PASS, 0 Critical/High/Medium, 1 Minor)
  Dokumentation: docs/features/V-009.md; Trilium `jFyT2V8u3yij`

- [x] V-010 Agentenverwaltung vervollständigen
  Priorität: P1
  Abhängigkeiten: V-005, V-007
  Umfang: globale und projektbezogene CRUD-Funktionen.
  Akzeptanz: strukturierter und Rohtexteditor; sichere Validierung;
  Konflikte und tatsächliche Prioritäten sichtbar; keine festen Kernagentennamen;
  unbekannte Felder erhalten; Restore möglich.
  Tests: ungültiges Frontmatter, Duplikate, Projektüberschattung,
  Traversal, Kopieren auf vorhandenes Ziel, Browserworkflow.
  Commit: 4a9f2d8; Test: tests/unit/test_agent_management.py (24 Tests, u. a.
  test_invalid_frontmatter_is_rejected_without_touching_the_file,
  test_project_agent_overrides_global_agent_and_shadowing_is_visible,
  test_copy_to_an_existing_target_is_refused_and_changes_nothing,
  test_path_traversal_and_invalid_names_are_rejected,
  test_structured_fields_preserve_unknown_frontmatter_fields,
  test_restore_brings_back_the_previous_version);
  tests/browser/test_agents_ui.py (7 Tests, u. a.
  test_list_shows_conflict_and_actual_priority,
  test_invalid_raw_frontmatter_is_rejected_without_writing,
  test_copy_to_an_existing_target_is_refused)
  Prüfungen: Rot gegen a013a53: `Ran 24 tests`, `FAILED (failures=8, errors=30)`;
  `python3 -m unittest discover -s tests/unit -p test_agent_management.py -v`
  24 Tests OK; `python3 -m unittest discover -s tests/browser -p test_agents_ui.py -v`
  7 Tests OK; `bash scripts/verify.sh quick` Exit 0; `bash scripts/verify.sh full`
  Exit 0 (553 Unit- + 41 Browser-Tests, 594 erkannt) im Mount-Namespace mit
  tmpfs auf /tmp und ohne SANDBOX/SANDBOX_TOOLS.
  Review: docs/reviews/V-010-review-1.md (PASS, 0 Critical/High/Medium, 2 Minor)
  Dokumentation: docs/features/V-010.md; Trilium `KkhQ6sa4w0qz`

- [x] V-011 Modellkatalog bereinigen und belegbar machen
  Priorität: P1
  Abhängigkeiten: V-007
  Umfang: lokalen Altkatalog prüfen und versionierten öffentlichen Katalog erzeugen.
  Akzeptanz: jede nicht triviale Angabe mit Quelle/Datum;
  unbekannte Werte zulässig; Fakten und Einschätzungen getrennt;
  keine ungeprüften Preise oder Modell-IDs übernommen;
  ausklappbare Tabelle und Detailzeilen erhalten.
  Tests: fehlende Quellen, veraltete Preise, unbekannte Modelle,
  entfernte Modelle, Währung und Tarifeinheiten, Browserdarstellung.
  Commit: 13f2876; Test: tests/unit/test_model_catalog.py (33 Tests, u. a.
  test_missing_source_is_reported, test_outdated_price_is_reported,
  test_legacy_paid_price_is_not_adopted,
  test_removed_model_is_reported_against_current_list);
  tests/browser/test_models_ui.py (6 Tests, u. a.
  test_table_is_collapsed_and_expands,
  test_detail_separates_facts_and_assessments_with_sources,
  test_unknown_model_has_no_assessment)
  Prüfungen: Rot gegen 2d78d04: `FileNotFoundError` für `bin/vibe_models.py`,
  `Ran 0 tests`, `FAILED (errors=3)`; Browser-Timeout für
  `#models > details > summary`, `FAILED (errors=1)`. Grün:
  `python3 -m unittest tests.unit.test_model_catalog -v` 33 Tests OK;
  `python3 -m unittest tests.browser.test_models_ui -v` 6 Tests OK;
  `bash scripts/verify.sh quick` Exit 0; `bash scripts/verify.sh full`
  Exit 0 (586 Unit- + 47 Browser-Tests, 633 erkannt) im Mount-Namespace mit
  tmpfs auf `/tmp` und ohne SANDBOX/SANDBOX_TOOLS.
  Review: docs/reviews/V-011-review-1.md, -2.md, -3.md
  (PASS, 0 Critical/High/Medium, 2 Minor)
  Dokumentation: docs/features/V-011.md; Trilium `rKViBnJz9ZNZ`

- [ ] V-012 Modellprofile transaktional anwenden
  Priorität: P1
  Abhängigkeiten: V-005, V-010, V-011
  Umfang: Profile und frei zuordenbare Rollen, global und projektbezogen.
  Akzeptanz: Änderungsvorschau; vollständige Vorvalidierung; Rollback;
  leeres Profil kein Erfolg; Abweichungen sichtbar; kein automatischer
  kostenpflichtiger Fallback; Anbieterzugang getrennt von Modellwahl.
  Tests: ungültiger zweiter Agent, Fehler beim zweiten Write,
  nicht verfügbares Modell, leeres Profil, manuelle Modelländerung.

- [x] V-013 MCP-Konfiguration verlustarm bearbeiten
  Priorität: P1
  Abhängigkeiten: V-005, V-007
  Umfang: globale/projektbezogene CRUD-Funktionen und Status.
  Akzeptanz: tatsächliches Schema verwendet; nicht unterstützte Felder nicht
  blind angeboten; Kommentare/unbekannte Einstellungen erhalten oder explizite
  Warnung mit Vorschau; maskierte Geheimnisse unverändert erhalten.
  Tests: JSONC-Kommentare, Trailing Commas, unbekannte Schlüssel,
  mehrere Konfigurationsdateien, Rename-Konflikte, geheime URL-Parameter.
  Commit: b18184f; Test: tests/unit/test_mcp_config.py (25 Tests, u. a.
  test_comments_trailing_commas_and_unknown_settings_survive_saving,
  test_file_priority_matches_opencode_mcp_add,
  test_unknown_field_of_an_existing_entry_is_preserved_but_new_ones_are_rejected,
  test_masked_secrets_are_restored_when_other_parts_change,
  test_duplicate_secret_url_parameters_are_not_silently_rewritten)
  Prüfungen: `python3 -m unittest tests.unit.test_mcp_config -v` 25 Tests OK;
  `bash scripts/verify.sh quick` Exit 0; `bash scripts/verify.sh full` Exit 5
  (529 Tests, 10 Failures + 5 Errors) — dieselben 15 vorbestehenden
  Umgebungsfehler wie auf dem sauberen Ausgangscommit `7ba22ab` (504 Tests):
  SANDBOX=on ohne `vibe_sandbox.py` im temporären Projekt bzw. bwrap mit
  offenem HOME.
  Review: docs/reviews/V-013-review-1.md (CHANGES REQUIRED, 2 Medium/2 Minor),
  docs/reviews/V-013-review-2.md (PASS, 0 Critical/High/Medium, 1 Minor)
  Dokumentation: docs/features/V-013.md; Trilium `mtlfH63g6rLt`

- [x] V-014 MCP-Verbindungstests robust und begrenzt ausführen
  Priorität: P1
  Abhängigkeiten: V-003, V-013
  Umfang: Handshake, Werkzeugliste und Diagnose.
  Akzeptanz: kein automatisches tools/call; unterstützte Transporte angegeben;
  OAuth-Grenzen deutlich; Startwarnung; Limits und vollständiges Prozesscleanup;
  keine Geheimnisse in Ausgabe.
  Tests: lokaler Mockserver, HTTP-Mockserver, Authfehler, Protokollfehler,
  Dauerstream, große Ausgabe, Kindprozess, Timeout, unbekannter Transport.
  Commit: 2838c33; Test: tests/unit/test_mcp_test.py (18 Tests, u. a.
  test_handshake_reports_tools_and_never_calls_a_tool,
  test_child_processes_are_terminated_with_the_test,
  test_endless_event_stream_returns_after_the_wanted_answer,
  test_unknown_transport_is_reported_without_calling_it_broken)
  Prüfungen: bash scripts/verify.sh quick (Exit 0); bash scripts/verify.sh full
  (Exit 0, 604 Unit- und 47 Browsertests, 651 erkannt)
  Review: docs/reviews/V-014-review-1.md (CHANGES REQUIRED, 1 Medium/3 Minor),
  docs/reviews/V-014-review-2.md (PASS, 0 Critical/High/Medium/Minor)
  Dokumentation: docs/features/V-014.md; docs/compatibility.md;
  Trilium `yNkNwN9tHGbU`

- [x] V-015 Agentenläufe und Projektprüfungen entkoppeln
  Priorität: P1
  Abhängigkeiten: V-003, V-007, V-009
  Umfang: Laufstatus, eindeutige IDs, Logs und typabhängige Prüfadapter.
  Akzeptanz: nicht-Android ohne Android-Dateien ausführbar;
  Exitcodes korrekt; Projektkollisionen ausgeschlossen;
  Stoppen betrifft nur den gewählten Lauf; keine automatische
  Router-Neuverbindung oder Limitumgehung.
  Tests: parallele Projekte, gleiche normalisierte Namen, fehlender Prüfbefehl,
  Fehlerexit, beendeter Prozess, Wiederholungslimit, Logrotation.
  Commit: cf73906; Test: tests/unit/test_run_control.py (23 Tests, u. a.
  test_same_normalized_names_get_distinct_runs_logs_and_pause_flags,
  test_retry_limit_stops_repeating_the_same_package,
  test_stop_only_kills_the_selected_run)
  Prüfungen: `python3 -m unittest tests.unit.test_run_control -v` 23 Tests OK;
  `bash scripts/verify.sh quick` Exit 0; `bash scripts/verify.sh full` Exit 0
  (627 Unit- + 47 Browser-Tests, 674 erkannt) im Mount-Namespace mit tmpfs auf
  /tmp (schreibgeschütztes /tmp im Prüfcontainer, Staging-Pfad von next_item.py).
  Review: docs/reviews/V-015-review-1.md (PASS, 0 Critical/High/Medium, 4 Minor)
  Dokumentation: docs/features/V-015.md; Trilium `DqTH63j8L7qv`

- [x] V-016 Dashboard- und opencode-Lebenszyklus getrennt prüfen
  Priorität: P1
  Abhängigkeiten: V-004, V-015
  Umfang: Starten und Beenden beider Anwendungen.
  Akzeptanz: Dashboard beenden stoppt weder Agentenläufe noch opencode;
  opencode stoppen beendet nicht vibe; nur verwaltete Prozesse werden beendet;
  aktive Streams und Hintergrundthreads sauber behandelt.
  Tests: alle Kombinationen laufender Prozesse; Neustart; belegter Port;
  Browser-Tab schließen; Beenden während eines aktiven Agentenlaufs.
  Commit: 70b029d; Test: tests/unit/test_lifecycle.py (17 Tests, u. a.
  test_every_combination_of_running_processes,
  test_foreign_sessions_with_the_same_name_are_not_stopped,
  test_shutdown_ends_streams_and_keeps_run_and_opencode,
  test_sigterm_ends_streams_cleanly)
  Prüfungen: `python3 -m unittest tests.unit.test_lifecycle -v` 17 Tests OK;
  `bash scripts/verify.sh quick` Exit 0; `bash scripts/verify.sh full` Exit 0
  (644 Unit- + 47 Browser-Tests, 691 erkannt) im Mount-Namespace mit tmpfs auf
  /tmp (schreibgeschütztes /tmp im Prüfcontainer, Staging-Pfad von next_item.py).
  Review: docs/reviews/V-016-review-1.md (PASS, 0 Critical/High/Medium, 2 Minor)
  Dokumentation: docs/features/V-016.md; Trilium `hv8eqCTudXhH`

- [x] V-017 Bazzite-Starter produktionsreif integrieren
  Priorität: P1
  Abhängigkeiten: V-004, V-006, V-016
  Umfang: Host-Installer, Desktopdatei, Icon, Starter und Uninstaller.
  Akzeptanz: läuft nicht -> starten und Browser öffnen;
  läuft -> nur Browser öffnen; fremder Dienst erkannt;
  Mehrfachklicks erzeugen eine Instanz; Pfade korrekt gequotet;
  Menüaktion beendet nur vibe; Fehler sichtbar.
  Tests: Mocktests und echte manuelle Bazzite-Abnahme;
  Container aus/an, Dashboard aus/an, Startfehler, Doppelklick,
  Tokenwechsel, Sonderzeichen im Pfad.
  Commit: f9c0af2; Test: test_double_click_creates_exactly_one_dashboard
  (tests/unit/test_bazzite_starter.py, 37 Tests);
  Prüfung: bash scripts/verify.sh quick/full;
  Review: docs/reviews/V-017-review-1.md;
  Doku: docs/features/V-017.md, docs/features/V-017-bazzite.txt,
  Trilium qB4ymeCudpPf.

- [x] V-018 Installation, Aktualisierung und Rollback implementieren
  Priorität: P1
  Abhängigkeiten: V-006, V-017
  Umfang: reproduzierbare Installation aus dem Repository.
  Akzeptanz: Vorschau, Sicherung, Versionskennung und Rollback;
  Laufzeitdaten und persönliche Konfiguration bleiben erhalten;
  keine Überschreibung der produktiven Instanz mitten im Self-Development;
  Uninstall löscht keine Projekte.
  Tests: frische Installation, Update, abgebrochenes Update, Rollback,
  geänderte Nutzervorlagen, fehlende Rechte.
  Commit: `2d214f0`; Test:
  test_reuse_failure_keeps_the_version_of_an_untouched_installation,
  test_fresh_install_copies_all_program_modules_and_writes_version
  (tests/unit/test_install_lifecycle.py, 37 Tests);
  Prüfung: `bash scripts/verify.sh quick` Exit 0;
  `bash scripts/verify.sh full` Exit 0 (833 Unit- + 56 Browser-Tests,
  889 erkannt);
  Review: docs/reviews/V-018-review-1.md, docs/reviews/V-018-review-2.md;
  Doku: docs/features/V-018.md, Trilium DqlM21jFH8ET.

- [x] V-019 Frontend und Backend schrittweise modularisieren
  Priorität: P2
  Abhängigkeiten: V-008 bis V-018
  Umfang: gemeinsame Dienste, Adapter und separate statische Webdateien.
  Akzeptanz: CLI/Web nutzen dieselbe Fachlogik; keine globale stdout-Umleitung
  in parallelen Requests; keine funktionale Neuentwicklung nebenbei.
  Tests: gesamte vorhandene Regressionssuite vor und nach jedem Teilschritt;
  parallele API-Requests ohne vermischte Ausgabe.
  Commit: 2a06797; Test: test_parallel_captures_do_not_mix_their_output,
  test_parallel_init_requests_keep_their_own_message
  (tests/unit/test_web_modularization.py, 8 Tests).
  Prüfungen: `bash scripts/verify.sh quick` Exit 0;
  `bash scripts/verify.sh full` Exit 0 (842 Unit- + 56 Browser-Tests,
  898 erkannt; Ausgangsstand `d0c33cf`: 833 + 56, 889 erkannt) im
  bubblewrap-Namespace mit tmpfs auf /tmp und Arbeitsbaum unter /tmp/work.
  Review: `docs/reviews/V-019-review-1.md` (PASS, 0 Critical/High/Medium,
  1 Minor).
  Dokumentation: `docs/features/V-019.md`; Trilium `FM5vVshvuXzR`.

- [x] V-020 Browserabnahme, Dokumentation und Releasebasis
  Priorität: P2
  Abhängigkeiten: V-008 bis V-019
  Umfang: echte Browsertests, Handbuch, Diagnose- und Betriebsanleitung.
  Akzeptanz: zentrale Nutzerabläufe automatisiert im Browser;
  dokumentierte manuelle Bazzite-Prüfung; bekannte Grenzen veröffentlicht;
  Feature-Dokumentation lokal und in Trilium;
  Reviewnachweise vollständig; Release ohne persönliche Daten reproduzierbar.
  Tests: vollständige Suite und Checkliste mit Versionen und Ergebnissen.
  Commit: `140afb9`; Test: test_central_flow_lists_opens_creates_and_verifies,
  test_environment_view_shows_release_and_diagnosis,
  test_tracked_symlink_is_refused_instead_of_becoming_a_regular_file,
  test_repository_content_has_no_personal_home_paths_or_secrets
  (14 Release-Tests, 2 Browsertests).
  Prüfungen: `bash scripts/verify.sh quick` Exit 0;
  `bash scripts/verify.sh full` Exit 0 (856 Unit- + 58 Browsertests, 914 erkannt).
  Release: `vibe-0.18.0-140afb9.tar.gz`, SHA-256
  `ef8367708648cd0d1b6a7df7df0998a3a0b7994d0551f16fee25997891e8e763`;
  `build-release.py verify` OK, zweiter Bau byte-identisch.
  Review: `docs/reviews/V-020-review-1.md`,
  `docs/reviews/V-020-review-2.md` (PASS).
  Dokumentation: `docs/features/V-020.md`, `docs/handbuch.md`,
  `docs/betrieb.md`, `docs/grenzen.md`, `docs/checkliste.md`,
  `docs/abnahme-bazzite.md`; Trilium `3IwzW6WLnBeU`.

- [x] V-021 Installationsvollständigkeit und Aufräumregeln
  Priorität: P1
  Abhängigkeiten: V-006, V-018
  Umfang: Setup installiert jedes vom Startbefehl importierte Modul;
  allgemeine Aufräumregeln gelten für bestehende und neue Projekte.
  Akzeptanz: eine frische Installation startet ohne fehlendes Modul
  (insbesondere `vibe_autonomous.py`); der Regressionstest leitet die
  benötigten Module aus `bin/vibe` ab und startet die installierte CLI;
  alle mitgelieferten Projektvorlagen enthalten die Aufräumregeln;
  `vibe init` ergänzt sie in einer vorhandenen `AGENTS.md` genau einmal und
  lässt vorhandene Inhalte sowie Symlinks unverändert.
  Tests: `tests/unit/test_setup_vibe.py`,
  `tests/unit/test_project_management.py`; `bash scripts/verify.sh quick/full`.
  Commit: `9d7f17d`; Test: test_every_module_imported_by_the_launcher_is_installed,
  test_installed_launcher_starts_with_all_options (47 Setup-Tests),
  test_init_appends_general_rules_to_an_existing_agents_file,
  test_init_does_not_duplicate_general_rules, test_init_does_not_follow_an_agents_symlink
  (16 Projektverwaltungstests).
  Prüfungen: `bash scripts/verify.sh quick` Exit 0;
  `bash scripts/verify.sh full` Exit 0 (792 Unit- + 56 Browser-Tests, 848 erkannt)
  in `/tmp/vibe-v021-full`.
  Review: `docs/reviews/V-021-review-1.md`, `docs/reviews/V-021-review-2.md` (PASS).
  Dokumentation: `docs/features/V-021.md`; Trilium `TNxOZ5jYhTfI`.

- [x] V-022 Ordnung im Git als allgemeine Projektregel
  Priorität: P1
  Abhängigkeiten: V-021
  Umfang: Die allgemeinen vibe-Regeln beschreiben neben dem Aufräumen des
  Projektordners auch die Ordnung im Git; bestehende Projekte übernehmen die
  Regeln beim nächsten `vibe init`.
  Akzeptanz: alle mitgelieferten Vorlagen und die Repository-`AGENTS.md`
  enthalten Feature-Branch-, Commit-, Diff-, Fremdänderungs- und
  History-Regeln; `vibe init` aktualisiert einen vorhandenen verwalteten Block
  ohne umgebende Inhalte zu verändern; unpaarige Marker und Symlinks bleiben
  unangetastet.
  Tests: `tests/unit/test_project_management.py`;
  `bash scripts/verify.sh quick/full`.
  Commit: `6532aa5` (Implementierung), `9cc736d` (Reviewbefunde).
  Prüfungen: `bash scripts/verify.sh quick` Exit 0;
  `bash scripts/verify.sh full` Exit 0 (796 Unit- + 56 Browser-Tests,
  852 erkannt) in `/tmp/vibe-v022-full`.
  Review: `docs/reviews/V-022-review-1.md` (CHANGES REQUIRED, 2 Medium/2 Minor;
  behoben), `docs/reviews/V-022-review-2.md` (PASS, 0 Critical/High/Medium;
  2 Minor).
  Dokumentation: `docs/features/V-022.md`; Trilium `0nTTx7KSysUQ`.

- [x] AP03 Überarbeitung Agentenverwaltung
  Beschreibung: Die Agentenverwaltung ist für die Menge der Agenten unübersichtlich geworden.
  
  Ich möchte die UI - sowohl im Allgemeinen, als auch je Projekt von neu aufbauen (komplett neu erstellen).
  
  Allgemeine Einstellungen:
  Fokus der UI muss darauf liegen, einfach Agenten erstellen zu können und ihnen eine bestimmte Rolle zuweisen zu können.
  
  Es müssen hierarchien und berechtigungen existieren und einstellbar sein, damit klar ist, welcher Agent zugriff auf welche Sub Agenten hat.
  
  Für jeden Agenten muss schnell erkennbar sein: Was ist seine Aufgabe, was ist sein ergebnis, wen darf er aufrufen, welches modell wird im standard verwendet.
  
  Projekte dürfen nur die systemweit definierten agenten verwenden, lediglich die modell können je projekt (und auch nur in den jeweiligen Projekt einstellungen) geändert werden. Im Projekt nicht konfigurierte agenten sollen im standard nicht sichtbar, aber vorhanden sein.
  
  Es muss immer mindestens einen StandardAgenten gebenden "Vibe-Agent" - für diesen muss immer ein modell konfiguriert sein, vorher können keine projekte mit vibe ausgeführt werden. Sofern kein anderer Agent definiert ist, übernimmt der vibe agent alle aufgaben. Er benötigt dementsprechend einen allgemeinen prompt mit der einzigen spezialisierng - unterstüzung des nutzers bei der benutzung und konfiguration von vibe.
  
  Vibe soll den nutzer aktiv bei der formulierung der prompts der agenten unterstützen. Wichtigste priorität der agenten prompts ist die aufgabe und die abkapselung der aufgabe. Die ausführung und detailtiefe soll der agent selbst defninieren dürfen, aber nur in dem jeweils eigenen bereich.
  Commit: 066e671
  Test: test_cmd_run_aborts_without_a_model_even_when_agent_is_set, test_cmd_run_aborts_when_the_vibe_agent_has_no_model, test_vibe_role_is_unique_and_cannot_be_removed_without_replacement, test_agent_validate_hierarchy_rejects_unknown_self_and_cycles, test_missing_config_activates_only_the_vibe_agent (tests/unit/test_ap03_agent_management.py, 33 Tests), test_05_project_settings_default_vibe_toggle_and_model_override (tests/browser/test_ap03_agents_ui.py, 20 Tests)
  Review: docs/reviews/AP03-review-1.md (CHANGES REQUIRED; 1 Medium behoben, 1 Medium als dokumentierte Umgebungsgrenze akzeptiert, 3 Minor)
  Doku: docs/features/AP03.md; Trilium `z9AVIt88OWdN`
  Hinweis: Der konfigurierte Test-Agent (`test-agent`) war in dieser Sitzung nicht aufrufbar (`permission.rejected`); die Test-Herkunft ist in `docs/features/AP03.md` offen dokumentiert.

- [x] AP04 Harniss alternativen
  Beschreibung: Ich möchte, dass vibe unabhängiger vom coding harniss opencode wird.
  Lege die Grundlagen, dass der harniss leichter getauscht werden kann.
  Biete mir sowohl im set up als auch in der UI die möglichkeit an den harniss zu wechseln, bzw bei der ersten installation einene harniss der wahl zu wählen.

  Vibe soll bei der einrichtung des harniss unterstüzen.

  Als ersten alternativen harniss soll Pi benutzt werden https://github.com/earendil-works/pi - dies soll am ende von diesem AP möglich sein.

  Es ist erlaubt unterarbeitspakete für diese ap zu erstellen, wenn benötigt.
  Commit: bb74270
  Test: test_default_is_opencode_when_no_selection_file_exists, test_corrupt_selection_file_is_reported_instead_of_silently_using_opencode, test_pi_run_command_uses_print_mode_and_the_agent_prompt, test_missing_pi_is_reported_with_the_binary_name (tests/unit/test_ap04_harness.py, 21 Tests), test_first_install_stores_the_chosen_harness (tests/unit/test_ap04_setup_harness.py, 6 Tests), test_harness_is_visible_and_pi_can_be_selected (tests/browser/test_ap04_harness_ui.py, 2 Tests)
  Review: docs/reviews/AP04-review-1.md (CHANGES REQUIRED; 1 Medium in der Doku behoben, 3 Minor)
  Doku: docs/features/AP04.md; docs/compatibility.md; Trilium `pVrde5xTkFvu`
  Hinweis: Der konfigurierte Test-Agent (`test-agent`) war in dieser Sitzung nicht aufrufbar (`permission.rejected`); die Test-Herkunft ist in `docs/features/AP04.md` offen dokumentiert.
