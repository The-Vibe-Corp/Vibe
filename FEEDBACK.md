# FEEDBACK — Rückmeldungen an den Agenten

Regeln (werden maschinell geprüft):
1. Jeder Block, der mit `- ` beginnt und nicht mit `- [x]`, ist OFFEN.
2. Abhaken nur mit Nachweis darunter: `Commit: <hash>; Test: <Testmethode>` oder `Commit: <hash>; Datei: <Pfad>`.
3. Nicht lösbar? Darunter `BLOCKIERT: <Grund>` schreiben und NICHT abhaken.

<!-- Vorlage (nicht abhaken):
  - [ ] F99 Kurztitel
    Beschreibung: ...
-->

- [x] B1 Models in project config are ignored
  Art: Bug
  Beschreibung: The orchestrator agent tried to spawn a subagent and it tried on of the models in the global config and not the one in the project config (.vibe/agents.json).
  Commit: b55fcc6; Test: tests/unit/test_b1_project_agent_models.py (15/15), tests.unit.test_project_agents.RunnerModelTest (3/3), B13-Regressionsausschnitt (9/9), `bash -n bin/vibe-run.sh`, `python3 scripts/check-import-manifest.py`, `bash scripts/verify.sh quick` (Exit 0), `bash scripts/verify.sh package` (48/50; 2 vorbestehende Baselinefehler von test_project_agents)

- [ ] B2 AGENTS.md not available
  Art: Bug
  Beschreibung: Subagents seem to have issues finding the AGENTS.md file. It is not always necessarily committed in the repo. Make sure the project-specific one is available in the worktree (like the ticket) and also that the global one in the ~/.config/opencode dir is discovered.
