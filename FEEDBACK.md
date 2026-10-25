# FEEDBACK — Rückmeldungen an den Agenten

Regeln (werden maschinell geprüft):
1. Jeder Block, der mit `- ` beginnt und nicht mit `- [x]`, ist OFFEN.
2. Abhaken nur mit Nachweis darunter: `Commit: <hash>; Test: <Testmethode>` oder `Commit: <hash>; Datei: <Pfad>`.
3. Nicht lösbar? Darunter `BLOCKIERT: <Grund>` schreiben und NICHT abhaken.

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

- [ ] F4 Feature: Nach aktuellen Arbeitspaket stoppen
  Schritte: 
  Erwartet: Das Feature ermöglicht ein gezieltes pausieren, ohne den Agent mitten im lauf unterbrechen zu müssen. Der Nutzer soll dies aktivieren können, sofern das aktiviert ist, wird der laufende Arbeitspaket beendet und danach kein neues Paket gestartet.
  Ist: 
