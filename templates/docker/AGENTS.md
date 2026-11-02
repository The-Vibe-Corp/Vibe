# Projekt: {{NAME}} (Docker: Client/Server)
- SPEC.md ist maßgeblich (anlegen und füllen). Keine Rückfragen: Lücken nach "Decisions Locked" entscheiden.
- Umgebung: Distrobox android-dev (Steuer-Container). $VIBE ist gesetzt. Nichts in ~ ablegen.
- Prüfbefehle stehen in .vibe/project.env (VERIFY_QUICK, VERIFY_FULL). Shell-Befehle laufen höchstens etwa 2 Minuten; Längeres im Hintergrund mit Log starten und das Log abfragen.
- Nach jedem Arbeitspaket: Tests grün, git commit.
- Container-Builds laufen auf dem HOST, nicht verschachtelt im Steuer-Container: `distrobox-host-exec podman ...` bzw. `distrobox-host-exec podman compose ...` (nicht auf dem Host getestet).
- Server und Client getrennt testen (Unit-Tests je Teil), danach Integrationstest über compose. Ports und Zugangsdaten nur über Umgebungsvariablen/.env (nicht committen).
- Beim Aufräumen nur Container/Images dieses Projekts löschen (Label oder Präfix `{{NAME}}`), nie `podman system prune`.

<!-- vibe:general-rules -->
## Projektordner sauber halten

- Im Projektordner nur Quellcode, Konfiguration, Tests und die vereinbarten Nachweise ablegen.
- Temporäre Dateien, Protokolle, Sicherungen und Arbeitskopien nach Abschluss des Arbeitspakets entfernen und nicht committen.
- Vor dem Commit `git status` prüfen und nur Dateien des eigenen Arbeitspakets stagen.
- Fremde oder vorbestehende Änderungen nicht löschen, überschreiben oder mitcommitten.
<!-- /vibe:general-rules -->
