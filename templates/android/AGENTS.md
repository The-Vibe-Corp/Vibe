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
- Vor dem Commit `git status` prüfen und nur Dateien des eigenen Arbeitspakets stagen.
- Fremde oder vorbestehende Änderungen nicht löschen, überschreiben oder mitcommitten.
<!-- /vibe:general-rules -->
