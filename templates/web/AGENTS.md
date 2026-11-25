# Projekt: {{NAME}} (Web)
- SPEC.md ist maßgeblich (anlegen und füllen). Keine Rückfragen: Lücken nach "Decisions Locked" entscheiden.
- Prüfbefehle stehen in .vibe/project.env (VERIFY_QUICK, VERIFY_FULL). 
- Nach jedem Arbeitspaket: Tests grün, git commit.
- Node/npm laufen im Steuer-Container. Abhängigkeiten nur mit `npm ci`/`npm install` im Projektordner; node_modules nicht committen.
- Tests: `npm test`. Ein Entwicklungsserver gehört in den Hintergrund (Log in /tmp), nie im Vordergrund.
- UI-Änderungen mit einem Test oder einem echten Screenshot belegen (Playwright o. ä., falls im Projekt vorhanden).
