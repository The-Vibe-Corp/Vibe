# Projekt: {{NAME}} (Web)
- SPEC.md ist maßgeblich (anlegen und füllen). Keine Rückfragen: Lücken nach "Decisions Locked" entscheiden.
- Umgebung: Distrobox android-dev (Steuer-Container). $VIBE ist gesetzt. Nichts in ~ ablegen.
- Prüfbefehle stehen in .vibe/project.env (VERIFY_QUICK, VERIFY_FULL). Shell-Befehle laufen höchstens etwa 2 Minuten; Längeres im Hintergrund mit Log starten und das Log abfragen.
- Nach jedem Arbeitspaket: Tests grün, git commit.
- Node/npm laufen im Steuer-Container. Abhängigkeiten nur mit `npm ci`/`npm install` im Projektordner; node_modules nicht committen.
- Tests: `npm test`. Ein Entwicklungsserver gehört in den Hintergrund (Log in /tmp), nie im Vordergrund.
- UI-Änderungen mit einem Test oder einem echten Screenshot belegen (Playwright o. ä., falls im Projekt vorhanden).
