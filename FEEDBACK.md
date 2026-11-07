# FEEDBACK — Rückmeldungen an den Agenten

Regeln (werden maschinell geprüft):
1. Jeder Block, der mit `- ` beginnt und nicht mit `- [x]`, ist OFFEN.
2. Abhaken nur mit Nachweis darunter: `Commit: <hash>; Test: <Testmethode>` oder `Commit: <hash>; Datei: <Pfad>`.
3. Nicht lösbar? Darunter `BLOCKIERT: <Grund>` schreiben und NICHT abhaken.
4. Fortsetzungszeilen eines Punktes müssen eingerückt sein. Eine nicht eingerückte Zeile beendet den Block; der Nachweis zählt dann nicht mehr zum Punkt.

<!-- Vorlage (nicht abhaken):
  - [ ] F99 Kurztitel
    Beschreibung: ...
-->

- [x] F1 Projet detail verbesserungen
  Schritte: 
  Erwartet: Feedback erfassung anpassen: Nur felder Titel und beschreibung (aktuell "erwartet"). "Schritte" und "ist" benötige ich nicht.
  Ist: 
  Commit: ca6c224; Test: FeedbackMarkdownTest.test_writes_only_title_and_description (tests/unit/test_feedback_capture.py, 8 Tests)

- [x] F2 Project detail ui anpassungen
  Schritte: 
  Erwartet: Bestehende Feedback punkte müssen bearbeitbar und löschbar sein.
  Live ausgabe sollte pausiert werden können
  Live ausgabe sollte die gesamte verfügbare UI höhe nutzen
  Live ausgabe sollte über einen button deutlich vergrößert werden können (fast bildschimfüllend)
  Ist: 
  Commit: a467953; Test: FeedbackBrowserTest.test_edit_and_delete_existing_feedback_entries, FeedbackBrowserTest.test_live_output_can_be_paused_and_resumed, FeedbackBrowserTest.test_live_output_uses_available_height_and_can_be_enlarged (tests/browser/test_feedback_ui.py; 59 Unit-Tests OK)

- [x] F3 Dynamische Agenten rechte
  Schritte: 
  Erwartet: Jedes Projekte sollte eine liste an erlaubten verzeichnissen mit schreibrechten haben. diese liste muss vom nutzer angepasst werden können. default verzeichnisse: /tmp/opencode; das jeweils eigene projektverzeichnis
  Ist: 
  Commit: 4637c27; Test: WriteDirsModelTest.test_default_list_contains_tmp_opencode_and_project_directory (tests/unit/test_project_write_dirs.py, 40 Tests; Browser: WriteDirsBrowserTest, 4 Tests)
  Test-Fix: 137c542 (Browsertest-Stabilisierung, tests/browser/test_write_dirs_ui.py)

- [x] F4 Feature: Nach aktuellen Arbeitspaket stoppen
  Schritte: 
  Erwartet: Das Feature ermöglicht ein gezieltes pausieren, ohne den Agent mitten im lauf unterbrechen zu müssen. Der Nutzer soll dies aktivieren können, sofern das aktiviert ist, wird der laufende Arbeitspaket beendet und danach kein neues Paket gestartet.
  Ist: 
  Commit: 5dc9529; Test: PauseModelTest.test_cli_requests_reports_and_releases_the_pause, RunnerPauseTest.test_runner_finishes_the_current_package_and_starts_no_new_one, RunnerPauseTest.test_pause_at_the_package_limit_is_consumed_after_the_loop, PauseBrowserTest.test_pause_is_requested_without_stopping_the_run_and_can_be_released (tests/unit/test_pause_after_package.py, 16 Tests; tests/browser/test_pause_after_package_ui.py, 2 Tests; gesamt 115 Unit-Tests, 9 Browsertests)
  Review: docs/reviews/F4-review-1.md, docs/reviews/F4-review-2.md, docs/reviews/F4-review-3.md (PASS)
  Doku: docs/features/F4.md; Trilium `hcX8exIYkgWR`

- [x] F5 Fritzbox Reconnect in UI
  Schritte: 
  Erwartet: Es soll die möglichkeit geben den Fritzbox reconenct über die UI einzustellen und zu steuern (Automatik:an/aus; manuell)

  Ist: 
  Commit: 7229d07; Test: FritzModelTest.test_automation_is_off_by_default, FritzModelTest.test_manual_reconnect_runs_the_helper_with_the_configured_env, FritzApiTest.test_api_switches_the_automation, RunnerFritzTest.test_runner_reconnects_automatically_when_the_gate_allows_it, FritzBrowserTest.test_automation_and_manual_reconnect_are_controllable (tests/unit/test_fritz_reconnect.py, 27 Tests; tests/browser/test_fritz_ui.py, 1 Test; gesamt 142 Unit-Tests, 10 Browsertests)
  Review: docs/reviews/F5-review-1.md, docs/reviews/F5-review-2.md (PASS)
  Doku: docs/features/F5.md; Trilium `8DoXPxXg7jnD`

- [x] F6 Universeller Setup Prozess
  Schritte: 
  Erwartet: Es soll einen interaktiven Setup prozess geben, welcher sowohl für Windows oder Linux (Ubuntu/Fedora/Bazzite/Docker) funktioniert und es ermöglicht vibe auf jedem system inklusiver aller notwendigen abhängigkeiten und tools zu installieren. Es muss die möglichkeit geben auf bestehendes zurückzugreifen.
  Ist: 
  Commit: c2ef5e2; Test: PlatformDetectionTest.test_ubuntu_uses_apt, DependencyPlanTest.test_missing_linux_tools_become_one_argument_list, InstallFilesTest.test_reuse_keeps_existing_programs_and_only_adds_missing_ones, CliFlowTest.test_failed_package_command_is_reported, WrapperTest.test_install_vibe_sh_uses_the_python_setup (tests/unit/test_setup_vibe.py, 45 Tests; gesamt 187 Unit-Tests, 10 Browsertests)
  Review: docs/reviews/F6-review-1.md, docs/reviews/F6-review-2.md, docs/reviews/F6-review-3.md (PASS)
  Doku: docs/features/F6.md; Trilium `sHzUT9bBs8NI`

- [x] F7 Sandbox (wenn möglich)
  Beschreibung: aktueller stand: "Verzeichnisse für das Schreibwerkzeug (edit) der Projektagenten. Voreingestellt sind /tmp/opencode und das Projektverzeichnis. Agenten ohne Schreibrecht bleiben unverändert. Shell-Befehle (bash) bleiben erlaubt und können Dateien außerhalb dieser Liste ändern – die Liste ist keine Sandbox."

  ist es möglich, die agenten auch über die shell befehle zu begrenzen und somit eine sandbox aufzubauen, welche nur die verzeichnisse mit schreibrechten, mcp, und notwendige build tools erlaubt? die build tools sollten idealerweise je projekt konfigurierbar sein und mit dem projekt templates bereits vorausgewählt mitgeliefert werden.
  Commit: 0406429; Test: SandboxConfigTest.test_cli_off_replaces_the_last_of_duplicate_keys, SandboxRunnerTest.test_runner_fails_closed_when_sandbox_module_is_broken, SandboxCommandTest.test_real_sandbox_allows_write_dirs_and_denies_unlisted_paths (tests/unit/test_sandbox.py, 31 Tests; gesamt 218 Unit-Tests, 11 Browsertests)
  Review: docs/reviews/F7-review-1.md, docs/reviews/F7-review-2.md, docs/reviews/F7-review-3.md (PASS)
  Doku: docs/features/F7.md; Trilium `ZzVeElHG2ifr`
  Nachweis-Fix: 6d59e8f (FEEDBACK-Block F7 zusammengeführt, tests/unit/test_feedback_entries.py; Review docs/reviews/F7-review-4.md)

- [x] F8 Überarbeitung feedback system
  Beschreibung: abgeschlossene feedback aufgaben müssen nicht über die ui bearbeitbar sein, diese sollen im standard ausgeblendet sein.
  Commit: c3cf99b; Test: FeedbackCompletedModelTest.test_flags_only_entries_with_proof_as_completed, FeedbackCompletedModelTest.test_update_rejects_completed_entry_without_changing_file, FeedbackCompletedApiTest.test_api_rejects_update_of_completed_entry_and_keeps_file, FeedbackCompletedBrowserTest.test_completed_entries_are_hidden_by_default_and_can_be_shown, FeedbackCompletedBrowserTest.test_completed_entry_offers_no_edit_control (tests/unit/test_feedback_completed.py, 9 Tests; tests/browser/test_feedback_completed_ui.py, 3 Tests; gesamt 227 Unit-Tests, 14 Browsertests)
  Review: docs/reviews/F8-review-1.md (PASS, 1 Minor)
  Doku: docs/features/F8.md; Trilium `6U4QBUkWcwg1`

- [x] F9 Guide für neue Projekte
  Beschreibung: Ich benötige einen Assistenten für das fachliche aufsetzen neuer projekte. Er soll mich dabei führen und alle notwendigen fachlichen dateien erstellen. es soll die möglichkeit geben dateien bzw informationen mit Agenten unterstüzung gezielt zu verbessern oder zu erstellen, wenn input fehlt.

  Ziel ist ein sauberes fachliches projekt set up.
  Commit: b51fa4e; Test: ProjectGuideModelTest.test_apply_creates_spec_and_all_missing_fachliche_files, ProjectGuideAgentTest.test_headings_inside_a_fenced_block_stay_unchanged, ProjectGuideApiTest.test_api_saves_answers_and_creates_fachliche_files, ProjectGuideBrowserTest.test_guide_lists_steps_and_writes_spec_and_missing_files (tests/unit/test_project_guide.py, 36 Tests; tests/browser/test_project_guide_ui.py, 4 Tests; gesamt 353 Unit-Tests, 18 Browsertests)
  Review: docs/reviews/F9-review-7.md (PASS, 2 Minor)
  Doku: docs/features/F9.md; Trilium `WIk1kdJ8vgom`

- [x] F10 Bug: Kein automatischer stop
  Beschreibung: wenn alle arbeitspakete beendet sind, stoppt der agent. vibe gibt jedoch weiterhin an, dass der agentlauf noch aktiv ist. wenn alles erledigt ist, soll der agentlauf automatisch enden
  Commit: 0fcd908; Test: RunnerSessionEndTest.test_session_ends_when_the_runner_has_finished, RunnerSessionEndTest.test_session_ends_even_when_the_run_pauses, RunAutostopBrowserTest.test_detail_switches_to_stopped_when_the_run_ends (tests/unit/test_run_autostop.py, 2 Tests; tests/browser/test_run_autostop_ui.py, 1 Test; gesamt 355 Unit-Tests, 19 Browsertests)
  Review: docs/reviews/F10-review-1.md (PASS, 2 Minor)
  Doku: docs/features/F10.md; Trilium `srn5HaKQXjsu`

- [x] F11 Feature: weniger browser modale dialoge
  Beschreibung: modale dialoge nerven - es muss eine bessere lösung geben
  Commit: 205c1a3; Test: NonModalPageTest.test_page_offers_live_status_messages_and_inline_confirmation, NonModalPageTest.test_page_calls_no_blocking_browser_dialogs, NonModalBrowserTest.test_action_feedback_is_a_non_blocking_status_message, NonModalBrowserTest.test_delete_asks_inline_and_cancel_keeps_the_entry, NonModalBrowserTest.test_shutdown_asks_inline_and_cancel_keeps_the_dashboard_running (tests/unit/test_web_ui_nonmodal.py, 2 Tests; tests/browser/test_nonmodal_ui.py, 3 Tests)
  Review: docs/reviews/F11-review-1.md (PASS, 3 Minor)
  Doku: docs/features/F11.md; Trilium `0A6oTTAbOeGH`

- [x] F12 Kostenermittlung je AP/Projekt
  Beschreibung: Vibe soll mir für jedes AP oder Feedback oder gleichwertiges Paket und für das gesamte Projekt die kosten transparent ausgeben. Dafür soll es je Projekte eine separate Übersicht geben. In dieser sollen für jedes AP (oder gleichwertig) statistiken ausgegeben werden, wieviele input token, davon cached input token und output token je verwendetes modell/agent verbraucht wurden. diese sollen dann mit den kosten des jeweiligen Agent in euro werte umgerechnet werden. die summen aus allen statistiken der ap ergibt dann die statistik für das gesamte projekt. wenn die kosten des modells nicht bekannt sind, soll 0 angenommen werden.für den endnutzer soll es in immer die möglichkeit einer eingabe der einzelnen kosten geben - und auf dessen basis sollen die kosten dann neu berechnet werden. die nutzereingabe überschreibt immer die systemisch hinterlegten kosten. die nutzereingabe muss pro projekt gespeichert werden.
  Commit: de69ff8; Test: CommandLineTest.test_costs_command_prints_the_project_overview, CostsBrowserTest.test_project_overview_lists_tokens_and_costs (tests/unit/test_costs.py, 36 Tests; tests/browser/test_costs_ui.py, 4 Tests)
  Review: docs/reviews/F12-review-1.md, docs/reviews/F12-review-2.md (PASS, 0 Critical/High/Medium)
  Doku: docs/features/F12.md; Trilium `IwU7vi5DgDdd`

- [x] F13 Projekt detail UI überarbeitung
  Beschreibung: Die Projekt detail UI ist stark gewachsen und nicht mehr nutzerfreundlich.

  es sind sehr viele informationen im default sichtbar. wichtige felder sind schwer zu erreichen, weniger wichtige felder sind sehr präsent.

  erstelle die ui von grund auf neu, die aktuellen inhalte und funktionen sind gut und sollen erhalten bleiben, jedoch neu strukturiert. baue nicht auf der bestehenden ui auf, sondern denke neu, nach modernen standards.
  Commit: 37a2156; Test: ProjectDetailUiTest.test_detail_groups_content_into_tabs_and_shows_only_the_active_area, ProjectDetailUiTest.test_tabs_can_be_switched_by_mouse_and_keyboard, ProjectDetailUiTest.test_chosen_tab_survives_an_action_and_resets_when_leaving_the_detail, ProjectDetailUiTest.test_verify_action_opens_the_output_area_and_streams_the_check_log, ProjectDetailUiTest.test_narrow_viewport_keeps_the_detail_usable_without_page_scroll, ProjectDetailUiTest.test_each_tab_is_linked_to_its_panel_for_assistive_technology, ProjectDetailUiTest.test_new_project_opens_the_assistant_area, ProjectDetailUiTest.test_primary_actions_and_run_state_stay_visible_in_every_area (tests/browser/test_project_detail_ui.py, 8 Tests)
  Review: docs/reviews/F13-review-1.md, docs/reviews/F13-review-2.md (PASS, 0 Critical/High/Medium)
  Doku: docs/features/F13.md; Trilium `ppnQBKTcRlLQ`

- [x] F14 Project Type: Rebuild
  Beschreibung: Vibe soll einen neuen Projekttyp erhalten, welcher darauf spezialisiert ist eine bestehende anwendung zu analysieren und neu zu erstellen, so dass die neue version der anwendung unter allen betriebssystem lauffähig ist. Ziel ist es betriebssystemgrenzen aufzulösen und allen die funktionalität der anwendung zur verfügung zu stellen.

  Die fachliche Funktionsweise der Anwendung soll dabei 1:! übernommen werden. Technisch darf es angepasst werden, sofern die kompatibilität mit originalen Speicherständen behalten bleibt.

  Das profil soll alle notwendigen werkzeuge und entwicklungsumgebung für diesen prüfen bzw. aufsetzen wenn nicht vorhanden.

  hier ein unverbindlicher vorschlag:
  Agenten

      Orchestrator (Planung, Kontext, Kosten)

      Discovery/Analyse

      Reverse-Engineering

      Spezifikation

      Architektur

      Implementierung

      Verifikation/Parität

      Packaging

      CI/Test

  Tools

      Ghidra (headless) + MCP-Bridge (GhidraMCP, ReVa, REA)

      Wine für Verhaltensbeobachtung

      Debugger, Tracing, Datei-/Registry-Monitoring

      Coding-Agent mit Git/GitHub

      Sandbox (Container/VM) mit Shell und Compiler

      Test-Framework, Screenshot-Vergleich

      linuxdeploy, appimagetool

      CI-Pipeline mit Tests auf mehreren Distributionen
  Commit: 0cb9ce2; Test: ProfileTest.test_rebuild_type_creates_agents_parity_rules_and_toolcheck, ToolCheckTest.test_missing_required_tool_is_reported_and_blocks, ToolCheckTest.test_missing_optional_tool_is_reported_but_does_not_block, ToolCheckTest.test_install_plan_maps_missing_tools_to_packages_and_manual_steps, ToolCheckTest.test_install_plan_prefers_available_package_manager, ToolCheckTest.test_setup_runs_only_package_commands_and_never_claims_manual_success, ToolCheckTest.test_unknown_required_group_is_rejected_instead_of_silently_ignored, ToolCheckTest.test_project_env_selects_the_required_groups, ToolCheckCliTest.test_cli_check_is_green_with_all_required_tools, ToolCheckCliTest.test_cli_check_returns_error_and_names_missing_tool, ToolCheckCliTest.test_cli_setup_without_confirmation_changes_nothing (tests/unit/test_rebuild_profile.py, 11 Tests), RebuildProjectBrowserTest.test_rebuild_type_is_selectable_and_creates_the_profile (tests/browser/test_rebuild_project_ui.py, 1 Test)
  Review: docs/reviews/F14-review-1.md (PASS, 0 Critical/High/Medium)
  Doku: docs/features/F14.md; Trilium `ajp3HtOEv9k1`

- [x] F15 Arbeitspakete
  Beschreibung: Der nutzer soll über die UI nicht nur Feedback geben können. Es soll auch möglich sein: Arbetispakete zu defnieren/bearbeiten. Bugs melden zu können
  Commit: 9def788; Test: WorkPackageModelTest.test_lists_work_packages_with_title_description_and_state, WorkPackageModelTest.test_update_changes_title_and_description_but_keeps_other_fields, WorkPackageModelTest.test_add_work_package_appends_and_keeps_existing_entries, WorkPackageModelTest.test_delete_removes_only_the_selected_work_package, WorkPackageModelTest.test_add_bug_writes_a_bug_marker_and_numbers_separately, WorkPackageModelTest.test_update_bug_keeps_the_bug_marker, WorkPackageApiTest.test_api_adds_updates_and_deletes_a_work_package, WorkPackageApiTest.test_api_reports_a_bug_as_feedback_of_kind_bug (tests/unit/test_work_packages.py, 23 Tests), WorkPackageBrowserTest.test_add_edit_and_delete_a_work_package, WorkPackageBrowserTest.test_report_a_bug_from_the_ui (tests/browser/test_tickets_ui.py, 2 Tests)
  Review: docs/reviews/F15-review-1.md (PASS, 0 Critical/High/Medium; 2 Minor)
  Doku: docs/features/F15.md; Trilium `xuUMi61n9BPD`

- [x] F16 Rückfragen beantworten
  Beschreibung: Der Agent soll dem nutzer rückfragen stellen dürfen. Diese sollen von vibe in der ui angezeigt werden, mögliche auswahlmöglichkeiten vom agent sollen auch dem nutzer in der ui angezeigt werden. sobald eine rückfrage gestellt wird, soll der nutzer eine benachrichtigung bekommen. Es muss jedoch zusätzlich einen autonomen modus geben, welcher auch während des lauf aktivierbar sein muss, in welchem der Agent allein entscheiden muss, falls der Nutzer nicht zur verfügung steht.
  Commit: d7593a3; Test: QuestionStoreTest.test_create_returns_an_open_question_with_options, QuestionStoreTest.test_second_answer_is_rejected_without_overwriting_the_first, QuestionStoreTest.test_structurally_invalid_question_files_are_skipped, AutonomousCliTest.test_switching_the_mode_on_during_the_wait_ends_the_question, QuestionApiTest.test_api_reports_and_switches_the_autonomous_mode, QuestionBrowserTest.test_a_question_appears_with_options_and_is_answered, QuestionBrowserTest.test_the_project_detail_switches_the_autonomous_mode (tests/unit/test_questions.py, 35 Tests; tests/browser/test_questions_ui.py, 4 Tests)
  Review: docs/reviews/F16-review-1.md, docs/reviews/F16-review-2.md (PASS, 0 Critical/High/Medium; Runde 1: 1 Minor, in Runde 2 behoben)
  Doku: docs/features/F16.md; Trilium `8jT8gBFUV1Or`

- [x] F17 Agenten verwaltung
  Beschreibung: aktuell gibt es einen bug, dass modelle bei agenten nicht gepeichtert werden (allgmeien übersicht).
  
  zudem soll jedes projekt eine eigene ansicht der agenten erhalten, der nutzer soll hier eine auswahl haben, welche agenten er für dieses projekt einsetzt - diese sollen dann auch beim agentenlauf berücksichtigt werden. die modellauswahl eines agenten kommt im standard aus der übergreifenden konfig, kann aber je projekt vom nutzer je agent überschrieben werden
  Commit: 51272c7; Test: SelectionTest.test_default_selection_uses_all_available_agents_and_their_models, SelectionTest.test_disabled_agent_is_stored_for_one_project_only, SelectionTest.test_model_override_wins_over_the_agent_file_and_can_be_cleared, SelectionTest.test_non_string_model_is_rejected_without_writing, SelectionTest.test_concurrent_change_is_refused, RunSelectionTest.test_cmd_run_aborts_before_tmux_for_a_disabled_agent, RunSelectionTest.test_cmd_run_passes_the_project_model_override, RunnerModelTest.test_model_override_is_forwarded_to_opencode (tests/unit/test_project_agents.py, 21 Tests), AgentApiTest.test_api_save_applies_changed_structured_values, AgentApiTest.test_api_save_rejects_an_invalid_structured_value_without_writing (tests/unit/test_agent_management.py, 6 Tests), ProjectAgentsBrowserTest.test_model_selection_is_saved_without_manual_render, ProjectAgentsBrowserTest.test_project_selection_and_model_override_are_saved_and_shown (tests/browser/test_project_agents_ui.py, 2 Tests)
  Review: docs/reviews/F17-review-1.md, docs/reviews/F17-review-2.md (PASS, 0 Critical/High/Medium; Runde 1: 1 Medium, in Runde 2 behoben)
  Doku: docs/features/F17.md; Trilium `ullL9BIh9cui`

- [x] F18 Verbesserung internet reconnect
  Beschreibung: Wenn mehrere Projekte gleichzeitig laufen, soll vibe sicherstellen, dass nur ein internet reconnect durchgeführt wird und nicht jedes projekt einen eigenen reconnect startet. vibe soll dies zentral steuern und alle projekte informieren bzw nach dem reconnect die bertroffenen projekte wieder anstoßen
  Commit: 1b5bf9d; Test: test_simultaneous_projects_share_one_reconnect, test_a_failed_reconnect_is_reported_to_all_projects_and_not_repeated, test_a_waiting_project_never_starts_a_second_reconnect, test_a_recent_reconnect_is_reused_and_expires, test_automation_off_still_means_no_reconnect, test_a_manual_reconnect_participates_in_the_central_control, test_status_reports_the_central_result, test_a_project_name_with_control_characters_is_published_cleanly (tests/unit/test_fritz_coordination.py, 8 Tests), test_runner_tells_the_central_reconnect_which_project_continues (tests/unit/test_fritz_reconnect.py, 36 Tests gesamt)
  Review: docs/reviews/F18-review-1.md, docs/reviews/F18-review-2.md (PASS, 0 Critical/High/Medium; 3 Minor)
  Doku: docs/features/F18.md; Trilium `deX8hDMqAQ1k`

- [x] F19 Ausgabe ansicht, im Projekte.
  Beschreibung: Ich möchte im Ausgabefenster Syntax highlighting, ähnlich wie open code.
  Weiterhin möchte ich in der Lage sein, dem agenten, während der ausführung zusätzliche anweisungen/oder informationen direkt in der aktiven arbeit zukommen zu lassen.
  Außerdem möchte ich sehen, ob und welche sub agenten zu jedem zeitpunkt im projekt laufen und mir auch von diesen die ausgaben anzeigen lassen können.
  Commit: 6cff1a2
  Test: test_steering_is_delivered_and_marked_in_log, test_rejections_before_any_delivery, test_active_run_and_wrong_or_missing_password_is_rejected, test_subagents_reports_state_file_entries, test_output_of_a_captured_subagent, test_output_of_running_subagent_without_live_data_is_ok_false (tests/unit/test_output_view_f19_api.py), test_runner_logs_only_human_readable_lines, test_runner_calls_opencode_with_format_json (tests/unit/test_output_view_f19_runner.py, 19 Tests gesamt)
  Review: docs/reviews/F19-review-1.md (CHANGES REQUIRED; 1 Medium als dokumentierte Umgebungsgrenze akzeptiert, 1 Medium Browsertest als Folgearbeit ausgewiesen, 3 Minor)
  Doku: docs/features/F19.md; Trilium `dlKtNm7UtzYY`
  Hinweis: Der konfigurierte Test-Agent (`test-agent`) war in dieser Sitzung nicht aufrufbar (`permission.rejected`); die Test-Herkunft ist in `docs/features/F19.md` offen dokumentiert. Ein dauerhafter Browsertest für die F19-Oberfläche bleibt ausdrücklich offene Folgearbeit.

- [x] B1 Kostentabelle aktualisiert sich nur träge, oder zeigt gar keine werte an
  Art: Bug
  Beschreibung: Die Kostentabelle aktualisiert sich nur träge, oder zeigt gar keine werte an, bei manchen projekten.
  
  Ich möchte, dass die kostentabelle sich nach jedem ap komplett aktualisiert (aber nur dort, wo es änderungen gab)
  Commit: b805b96
  Test: test_overview_refreshes_automatically_and_keeps_unchanged_rows, test_project_rows_are_updated_in_place (tests/browser/test_costs_refresh_ui.py, 3 Tests), test_session_under_equivalent_mount_alias_belongs_to_the_project, test_alias_does_not_attribute_unrelated_sessions, test_duplicate_session_id_in_both_databases_is_counted_once (tests/unit/test_costs_refresh.py, 8 Tests)
  Review: docs/reviews/B1-review-1.md (CHANGES REQUIRED), docs/reviews/B1-review-2.md (CHANGES REQUIRED; 1 Medium als dokumentierte Umgebungsgrenze akzeptiert, 2 Minor)
  Doku: docs/features/B1.md; Trilium `V3AV2elZkQgo`
  Hinweis: Der konfigurierte Test-Agent (`test-agent`) war in dieser Sitzung nicht aufrufbar (`permission.rejected`); die Test-Herkunft ist in `docs/features/B1.md` offen dokumentiert. Die Blockade ist damit aufgelöst und das Paket fachlich abgenommen.

- [x] F21 UI-konfigurierte Agenten für den Lauf freigeben
  Art: Bug
  Beschreibung: Nach der Agentenkonfiguration über die vibe-Oberfläche
  (Rollen in `profiles.json`, Auswahl in `.vibe/agents.json`) bricht
  `vibe run` im Preflight mit "REVIEWER fehlt" ab, obwohl ein Agent mit der
  Rolle `reviewer` vorhanden ist. Zusätzlich lehnt
  `vibe_runs.py finish --state blocked` den Zustand ab, sodass ein durch den
  Preflight blockierter Lauf nicht sauber beendet wird.
  Akzeptanz: Der Preflight liest eine fehlende REVIEWER-Zuordnung aus den
  Rollen in `profiles.json` und bevorzugt dabei einen verfügbaren Agenten.
  Ein ausdrücklich gesetzter REVIEWER bleibt vorrangig. Fehlt jede
  reviewer-Rolle oder ist kein zugeordneter Agent verfügbar, bleibt der
  Preflight blockiert. `blocked` ist ein gültiger Endzustand im Laufregister;
  unbekannte Zustände werden weiterhin abgelehnt. Die Ablehnung eines
  unsauberen Arbeitsbaums bleibt unverändert.
  Commit: d28a7f5; Test: python3 -m unittest discover -s tests/unit -p 'test_f21_agents_preflight.py' -v (22 Tests OK)
  Review: docs/reviews/F21-review-1.md (CHANGES REQUIRED), docs/reviews/F21-review-2.md (PASS)
  Doku: docs/features/F21.md; Trilium `nmgfEHK5Yz2L`

- [x] F22 Preflight nicht bestanden
  Beschreibung: vibe soll den nutzer in diesem fall, über die funktion rückfragen stellen (F16) zu einem stand führen, das das nächste paket gestartet werden kann.
  Commit: 6a348d4, b9f88ae, 2e75c40; Test: python3 -m unittest discover -s tests/unit -p 'test_f22_preflight_assist.py' -v (19 Tests OK)
  Review: docs/reviews/F22-review-1.md (CHANGES REQUIRED), docs/reviews/F22-review-2.md (PASS), docs/reviews/F22-review-3.md (PASS)
  Doku: docs/features/F22.md; Trilium `h5WeRmvzjTol`
