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

- [ ] F2 Project detail ui anpassungen
  Schritte: 
  Erwartet: Bestehende Feedback punkte müssen bearbeitbar und löschbar sein.
Live ausgabe sollte pausiert werden können
Live ausgabe sollte die gesamte verfügbare UI höhe nutzen
Live ausgabe sollte über einen button deutlich vergrößert werden können (fast bildschimfüllend)
  Ist: 

- [ ] F3 Dynamische Agenten rechte
  Schritte: 
  Erwartet: Jedes Projekte sollte eine liste an erlaubten verzeichnissen mit schreibrechten haben. diese liste muss vom nutzer angepasst werden können. default verzeichnisse: /tmp/opencode; das jeweils eigene projektverzeichnis
  Ist: 

- [ ] F4 Feature: Nach aktuellen Arbeitspaket stoppen
  Schritte: 
  Erwartet: Das Feature ermöglicht ein gezieltes pausieren, ohne den Agent mitten im lauf unterbrechen zu müssen. Der Nutzer soll dies aktivieren können, sofern das aktiviert ist, wird der laufende Arbeitspaket beendet und danach kein neues Paket gestartet.
  Ist: 
