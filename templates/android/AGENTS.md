# Projekt: {{NAME}} (Android)
- SPEC.md ist maßgeblich. Keine Rückfragen: Lücken nach "Decisions Locked" entscheiden.
- SDK nur über die Android CLI (`android sdk ...`); nie sdkmanager/avdmanager.
- Build/Test: ./gradlew testDebugUnitTest assembleDebug lintDebug
- Emulator (Tablet, headless, API 35 ohne Play Store): `bash scripts/emulator-start.sh` und `bash scripts/emulator-stop.sh`. Nicht `android emulator start`.
- Instrumented Tests nur auf dem Emulator: ANDROID_SERIAL=emulator-5554 ./gradlew connectedDebugAndroidTest. Spracherkennung (Mikrofon) ist im Emulator nicht testbar; dafür Fakes.
- Screenshots: adb exec-out screencap -p > /tmp/vibe/<name>.png (echte Aufnahmen, mind. 800x480).
- Schnelle Prüfung für Zwischenstände: `bash scripts/verify.sh quick` (unter 2 Minuten).
- Dateisystem ist FUSE/NTFS: keine Unix-Rechte, Skripte mit `bash datei.sh` aufrufen; core.fileMode ist false.
- Nach jedem Arbeitspaket: Tests grün, git commit.
