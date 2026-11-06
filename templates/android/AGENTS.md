# Projekt: {{NAME}} (Android)
- SPEC.md ist maßgeblich. Keine Rückfragen: Lücken nach "Decisions Locked" entscheiden.
- Umgebung: Distrobox android-dev, JDK 25. Gesetzt sind $ANDROID_HOME, $GRADLE_USER_HOME, $VIBE. Nichts in ~ ablegen.
- SDK nur über die Android CLI (`android sdk ...`); nie sdkmanager/avdmanager.
- Build/Test: ./gradlew testDebugUnitTest assembleDebug lintDebug
- Emulator (Tablet, headless, API 35 ohne Play Store): `bash scripts/emulator-start.sh` und `bash scripts/emulator-stop.sh`. Nicht `android emulator start`.
- Instrumented Tests nur auf dem Emulator: ANDROID_SERIAL=emulator-5554 ./gradlew connectedDebugAndroidTest. Spracherkennung (Mikrofon) ist im Emulator nicht testbar; dafür Fakes.
- Screenshots: adb exec-out screencap -p > docs/screens/<name>.png (echte Aufnahmen, mind. 800x480).
- Schnelle Prüfung für Zwischenstände: `bash scripts/verify.sh quick` (unter 2 Minuten).
- Dateisystem ist FUSE/NTFS: keine Unix-Rechte, Skripte mit `bash datei.sh` aufrufen; core.fileMode ist false.
- Nach jedem Arbeitspaket: Tests grün, git commit.

<!-- vibe:general-rules -->
## Projektordner sauber halten

- Im Projektordner nur Quellcode, Konfiguration, Tests und die vereinbarten Nachweise ablegen.
- Temporäre Dateien, Protokolle, Sicherungen und Arbeitskopien nach Abschluss des Arbeitspakets entfernen und nicht committen.
- Laufzeitdaten, persönliche Konfiguration und Geheimnisse gehören nicht ins Repository.

## Ordnung im Git halten

- Änderungen auf einem Feature-Branch umsetzen, nicht direkt auf main, master oder einem geschützten Branch.
- Jedes abgeschlossene Arbeitspaket als zusammenhängenden Commit sichern; keine Zwischenstände oder fremden Änderungen mitcommitten.
- Vor jedem Commit `git status` und den relevanten Diff prüfen und ausschließlich Dateien des eigenen Arbeitspakets stagen.
- Keine temporären Dateien, Protokolle, Build-Artefakte, Arbeitskopien oder Screenshots ohne Nachweiswert committen.
- Fremde oder vorbestehende Änderungen nicht löschen, überschreiben, stashen oder mitcommitten.
- Keine Historie umschreiben, keine Force-Pushes und kein Push ohne ausdrückliche Freigabe.

## Leitlinien für Coding-Agenten (verbindlich)

- KISS ist verpflichtend: Wähle die einfachste Lösung, die das Problem vollständig löst. Keine spekulativen Abstraktionen, Funktionen oder Optimierungen auf Vorrat und keine Komplexität ohne belegten Bedarf.
- Clean Code ist der verbindliche Code-Stil: sprechende Namen, kleine Funktionen mit einer klaren Aufgabe, explizite Schnittstellen, keine unnötige Duplizierung und nachvollziehbare Fehlerbehandlung. Verhalten wird durch Tests abgesichert, nicht durch Kommentare.
- Caching ist eine begründete Performance-Optimierung und nur mit funktionierender Invalidierung zulässig. Jeder Cache braucht einen eindeutigen Schlüssel, eine definierte Lebensdauer und eine benannte Invalidierung (Zeit, Änderungsereignis oder Version). Ohne korrekte Invalidierung wird nicht gecacht. Sicherheits-, Berechtigungs- und Geheimnisdaten werden nicht ungeprüft zwischengespeichert.
- Diese Leitlinien gelten für alle neuen und bestehenden Projekte unabhängig vom Projekttyp.

## Unabhängiger Test-Agent (verbindlich)

- Tests werden ausschließlich vom Test-Agenten geschrieben, geändert und gelöscht. Der Test-Agent ist in `.vibe/project.env` als `TESTER` konfiguriert (Vorlage: `test-agent`, Datei `.opencode/agents/test-agent.md`).
- Coding- und Review-Agent dürfen keine Testdateien anlegen, ändern, löschen oder abschwächen. Sie dürfen die vom Test-Agenten geschriebenen Tests ausführen und deren Ergebnisse melden.
- Vor der Implementierung fordert der Coding-Agent die Tests beim Test-Agenten an und übergibt Arbeitspaket, Akzeptanzkriterien und den vorgesehenen Testbefehl. Der Test-Agent leitet die Fälle unabhängig aus Arbeitspaket und `SPEC.md` ab, nicht aus dem Implementierungsdiff.
- Der Test-Agent beschreibt jeden Testfall (Name, Vorbedingung, Aktion, erwartetes Ergebnis), schreibt ihn vor der Implementierung und führt ihn tatsächlich aus. Ein nicht ausgeführter Test ist kein Nachweis.
- Nur Tests, die nachweislich vom Test-Agenten stammen, zählen für die Abnahme. Vom Coding-Agenten geschriebene oder nachträglich abgeschwächte Tests sind kein Nachweis; der Reviewer weist sie zurück.
- Fehlt der Test-Agent oder `TESTER` in `.vibe/project.env`, ist das Arbeitspaket blockiert.
<!-- /vibe:general-rules -->
