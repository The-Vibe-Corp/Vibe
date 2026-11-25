# Projekt: {{NAME}} (Docker: Client/Server)
- SPEC.md ist maßgeblich (anlegen und füllen). Keine Rückfragen: Lücken nach "Decisions Locked" entscheiden.
- Prüfbefehle stehen in .vibe/project.env (VERIFY_QUICK, VERIFY_FULL).
- Nach jedem Arbeitspaket: Tests grün, git commit.
- Server und Client getrennt testen (Unit-Tests je Teil), danach Integrationstest über compose. Ports und Zugangsdaten nur über Umgebungsvariablen/.env (nicht committen).
- Beim Aufräumen nur Container/Images dieses Projekts löschen (Label oder Präfix `{{NAME}}`), nie ` system prune`.
