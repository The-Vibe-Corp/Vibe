# TICKETS — vibe

SPEC.md ist maßgeblich.
Reihenfolge: P0 vor P1 vor P2; Abhängigkeiten beachten.
Jedes Ticket ist genau ein Arbeitspaket.
Abhaken nur nach erfüllten Kriterien, erfolgreichen relevanten Tests und Review.
Nachweise unter dem Ticket: Commit, Testbefehle, Reviewdatei, Dokumentation.
Ein fehlender externer Dienst bedeutet BLOCKIERT, nicht erledigt.

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

- [ ] V-004 Web-API absichern und Health-Endpunkt ergänzen
  Priorität: P0
  Abhängigkeiten: V-002
  Umfang: Authentisierung, Host-/Origin-Prüfung, Requestlimits, Health.
  Akzeptanz: nur Loopback; nicht autorisierte Schreibzugriffe abgelehnt;
  Health identifiziert vibe und seine Instanz ohne Geheimnisse auszugeben;
  keine Tokens in Logs; strukturierte Fehler.
  Tests: fehlendes/falsches Token, fremder Origin/Host, ungültiges JSON,
  übergroße Requests, parallele Anfragen.

- [ ] V-005 Atomare Dateizugriffe und sichere Sicherungen
  Priorität: P0
  Abhängigkeiten: V-002
  Umfang: gemeinsame Storage-Schicht für Konfigurationen und Agenten.
  Akzeptanz: konkurrierende Änderungen erkannt; atomare Writes;
  kollisionsfreie Sicherungen; Wiederherstellung möglich;
  kein falsches Sicherheitsversprechen auf FUSE/NTFS.
  Tests: gleichzeitiges Speichern, Schreibfehler, unterbrochener Write,
  Namenskollision bei Sicherungen, Restore.

- [ ] V-006 Quellen-, Installations- und Laufzeitpfade trennen
  Priorität: P0
  Abhängigkeiten: V-001, V-005
  Umfang: Pfadmodell und Konfigurationspriorität definieren.
  Akzeptanz: separates Dev-Profil; produktive Instanz unverändert;
  Pfade und Ports konfigurierbar; Modulimport ohne Nebenwirkungen;
  persönliche Einstellungen überschreiben Defaults.
  Tests: alternativer Arbeitsbereich, fehlende Verzeichnisse, Leerzeichen,
  abweichender Port, Import ohne Prozessstart.

- [ ] V-007 opencode-Kompatibilitätsadapter erstellen
  Priorität: P0
  Abhängigkeiten: V-001, V-002
  Umfang: tatsächlich installierte Version und unterstützte CLI/API erfassen.
  Akzeptanz: docs/compatibility.md nennt geprüfte Version und Verfahren;
  Modelllisting, Agenten, MCP und Serverstart über einen Adapter;
  keine ungeprüfte mcp.servers-Annahme; unbekannte Version verständlich behandelt.
  Tests: Fixtures unterstützter Versionen, unerwartete Ausgabe, fehlendes Binary,
  Fehlercode und Timeout.

- [ ] V-008 Projektverwaltung und Vorlagen regressionssicher machen
  Priorität: P1
  Abhängigkeiten: V-003, V-006
  Umfang: Roots, Discovery, Init und Neuanlage.
  Akzeptanz: gleiche Projektnamen eindeutig; Init erhält bestehende Dateien;
  Entfernen eines Roots löscht nichts; Typen sind erweiterbar.
  Tests: Git-Verzeichnis und Git-Datei, doppelte Namen, Symlinks,
  nicht lesbare Ordner, bereits vorbereitetes Projekt.

- [ ] V-009 Ticket- und Feedbackverarbeitung stabilisieren
  Priorität: P1
  Abhängigkeiten: V-005
  Umfang: Parser, IDs, Status und neue Feedbackeinträge.
  Akzeptanz: Kommentare ignoriert; stabile IDs; BLOCKIERT bleibt offen;
  fehlende Nachweise werden sichtbar; keine Doppel-IDs bei Parallelzugriff.
  Tests: mehrzeilige Blöcke, Kommentare, defekte Checkboxen, fehlender Commit,
  gleichzeitige Einträge und nicht vorhandene Dateien.

- [ ] V-010 Agentenverwaltung vervollständigen
  Priorität: P1
  Abhängigkeiten: V-005, V-007
  Umfang: globale und projektbezogene CRUD-Funktionen.
  Akzeptanz: strukturierter und Rohtexteditor; sichere Validierung;
  Konflikte und tatsächliche Prioritäten sichtbar; keine festen Kernagentennamen;
  unbekannte Felder erhalten; Restore möglich.
  Tests: ungültiges Frontmatter, Duplikate, Projektüberschattung,
  Traversal, Kopieren auf vorhandenes Ziel, Browserworkflow.

- [ ] V-011 Modellkatalog bereinigen und belegbar machen
  Priorität: P1
  Abhängigkeiten: V-007
  Umfang: lokalen Altkatalog prüfen und versionierten öffentlichen Katalog erzeugen.
  Akzeptanz: jede nicht triviale Angabe mit Quelle/Datum;
  unbekannte Werte zulässig; Fakten und Einschätzungen getrennt;
  keine ungeprüften Preise oder Modell-IDs übernommen;
  ausklappbare Tabelle und Detailzeilen erhalten.
  Tests: fehlende Quellen, veraltete Preise, unbekannte Modelle,
  entfernte Modelle, Währung und Tarifeinheiten, Browserdarstellung.

- [ ] V-012 Modellprofile transaktional anwenden
  Priorität: P1
  Abhängigkeiten: V-005, V-010, V-011
  Umfang: Profile und frei zuordenbare Rollen, global und projektbezogen.
  Akzeptanz: Änderungsvorschau; vollständige Vorvalidierung; Rollback;
  leeres Profil kein Erfolg; Abweichungen sichtbar; kein automatischer
  kostenpflichtiger Fallback; Anbieterzugang getrennt von Modellwahl.
  Tests: ungültiger zweiter Agent, Fehler beim zweiten Write,
  nicht verfügbares Modell, leeres Profil, manuelle Modelländerung.

- [ ] V-013 MCP-Konfiguration verlustarm bearbeiten
  Priorität: P1
  Abhängigkeiten: V-005, V-007
  Umfang: globale/projektbezogene CRUD-Funktionen und Status.
  Akzeptanz: tatsächliches Schema verwendet; nicht unterstützte Felder nicht
  blind angeboten; Kommentare/unbekannte Einstellungen erhalten oder explizite
  Warnung mit Vorschau; maskierte Geheimnisse unverändert erhalten.
  Tests: JSONC-Kommentare, Trailing Commas, unbekannte Schlüssel,
  mehrere Konfigurationsdateien, Rename-Konflikte, geheime URL-Parameter.

- [ ] V-014 MCP-Verbindungstests robust und begrenzt ausführen
  Priorität: P1
  Abhängigkeiten: V-003, V-013
  Umfang: Handshake, Werkzeugliste und Diagnose.
  Akzeptanz: kein automatisches tools/call; unterstützte Transporte angegeben;
  OAuth-Grenzen deutlich; Startwarnung; Limits und vollständiges Prozesscleanup;
  keine Geheimnisse in Ausgabe.
  Tests: lokaler Mockserver, HTTP-Mockserver, Authfehler, Protokollfehler,
  Dauerstream, große Ausgabe, Kindprozess, Timeout, unbekannter Transport.

- [ ] V-015 Agentenläufe und Projektprüfungen entkoppeln
  Priorität: P1
  Abhängigkeiten: V-003, V-007, V-009
  Umfang: Laufstatus, eindeutige IDs, Logs und typabhängige Prüfadapter.
  Akzeptanz: nicht-Android ohne Android-Dateien ausführbar;
  Exitcodes korrekt; Projektkollisionen ausgeschlossen;
  Stoppen betrifft nur den gewählten Lauf; keine automatische
  Router-Neuverbindung oder Limitumgehung.
  Tests: parallele Projekte, gleiche normalisierte Namen, fehlender Prüfbefehl,
  Fehlerexit, beendeter Prozess, Wiederholungslimit, Logrotation.

- [ ] V-016 Dashboard- und opencode-Lebenszyklus getrennt prüfen
  Priorität: P1
  Abhängigkeiten: V-004, V-015
  Umfang: Starten und Beenden beider Anwendungen.
  Akzeptanz: Dashboard beenden stoppt weder Agentenläufe noch opencode;
  opencode stoppen beendet nicht vibe; nur verwaltete Prozesse werden beendet;
  aktive Streams und Hintergrundthreads sauber behandelt.
  Tests: alle Kombinationen laufender Prozesse; Neustart; belegter Port;
  Browser-Tab schließen; Beenden während eines aktiven Agentenlaufs.

- [ ] V-017 Bazzite-Starter produktionsreif integrieren
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

- [ ] V-018 Installation, Aktualisierung und Rollback implementieren
  Priorität: P1
  Abhängigkeiten: V-006, V-017
  Umfang: reproduzierbare Installation aus dem Repository.
  Akzeptanz: Vorschau, Sicherung, Versionskennung und Rollback;
  Laufzeitdaten und persönliche Konfiguration bleiben erhalten;
  keine Überschreibung der produktiven Instanz mitten im Self-Development;
  Uninstall löscht keine Projekte.
  Tests: frische Installation, Update, abgebrochenes Update, Rollback,
  geänderte Nutzervorlagen, fehlende Rechte.

- [ ] V-019 Frontend und Backend schrittweise modularisieren
  Priorität: P2
  Abhängigkeiten: V-008 bis V-018
  Umfang: gemeinsame Dienste, Adapter und separate statische Webdateien.
  Akzeptanz: CLI/Web nutzen dieselbe Fachlogik; keine globale stdout-Umleitung
  in parallelen Requests; keine funktionale Neuentwicklung nebenbei.
  Tests: gesamte vorhandene Regressionssuite vor und nach jedem Teilschritt;
  parallele API-Requests ohne vermischte Ausgabe.

- [ ] V-020 Browserabnahme, Dokumentation und Releasebasis
  Priorität: P2
  Abhängigkeiten: V-008 bis V-019
  Umfang: echte Browsertests, Handbuch, Diagnose- und Betriebsanleitung.
  Akzeptanz: zentrale Nutzerabläufe automatisiert im Browser;
  dokumentierte manuelle Bazzite-Prüfung; bekannte Grenzen veröffentlicht;
  Feature-Dokumentation lokal und in Trilium;
  Reviewnachweise vollständig; Release ohne persönliche Daten reproduzierbar.
  Tests: vollständige Suite und Checkliste mit Versionen und Ergebnissen.
