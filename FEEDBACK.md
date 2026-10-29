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

- [ ] F9 Guide für neue Projekte
  Beschreibung: Ich benötige einen Assistenten für das fachliche aufsetzen neuer projekte. Er soll mich dabei führen und alle notwendigen fachlichen dateien erstellen. es soll die möglichkeit geben dateien bzw informationen mit Agenten unterstüzung gezielt zu verbessern oder zu erstellen, wenn input fehlt.

  Ziel ist ein sauberes fachliches projekt set up.
