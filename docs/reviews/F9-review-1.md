# Review result

## Verdict

**CHANGES REQUIRED**

## Summary
- Critical: 0
- High: 0
- Medium: 2
- Minor: 2
- Verdict: CHANGES REQUIRED (Medium-Befunde offen; bis auf die Diff-Einschränkung siehe "Verification" vollständig prüfbar umgesetzt)

## Acceptance criteria
| Kriterium | Status | Implementierung | Test / Nachweis |
|---|---|---|---|
| Assistent führt durch fachliches Setup neuer Projekte | PASS | `bin/vibe_guide.py:37-111` (STEPS/FILES, state), `bin/vibe-web.py:624-654` (guideCard) | `test_project_guide.ProjectGuideModelTest` (Unit), `ProjectGuideBrowserTest.test_guide_lists_steps_and_writes_spec_and_missing_files` (Browser), `verify-full-4.log:139-164,399-401` |
| Erforderliche fachliche Dateien werden angelegt, ohne vorhandene still zu überschreiben | PASS | `bin/vibe_guide.py:272-293` (_ensure_files), `407-463` (apply, replace-Semantik), `155-177` (atomarer Write), `138-144` (Pfad-/Symlink-Grenze) | `test_apply_creates_spec_and_all_missing_fachliche_files`, `test_existing_files_are_kept_and_never_overwritten`, `test_explicit_replace_overwrites_the_selected_section_only`, `test_apply_rejects_spec_symlink_leaving_the_project`; API/Browser wie oben |
| Agentenunterstützung für fehlenden Input, Entwurf nur auf ausdrückliche Aktion | PASS | `bin/vibe_guide.py:478-596` (agent_prompt, start_agent, tmux-Argumentliste), `646-669` (draft_apply/draft_discard); API `bin/vibe-web.py:432-440` | `ProjectGuideAgentTest` (8 Tests), `test_api_rejects_agent_run_for_unknown_step_without_starting_tmux`, `test_api_rejects_a_too_long_agent_note`; Browser `test_agent_draft_is_only_applied_on_explicit_request` |
| Validierung, Tokenpflicht, keine Teil-Schreibvorgänge bei ungültigen Eingaben | PASS | `bin/vibe-web.py:317-327` (Token, known), `425-443` (400-Fälle); `bin/vibe_guide.py:376-404` (Antworten/replace-Validierung vor jedem Schreiben) | `test_api_rejects_unknown_step_without_writing`, `test_api_requires_a_valid_token` (403), Rot-Phase laut F9.md/Log-Ablage |
| Prüfungen `verify.sh quick` / `full` | PASS (vorgelegte Nachweise) | – | Log `verify-full-4.log:5-7,384,409-414`: Manifest 27 Dateien OK, 311 Unit- + 17 Browser-Tests OK, Exit 0 (nur vom Coding-Agent vorgelegt, nicht von mir ausgeführt) |
| Dokumentation `docs/features/F9.md` + Trilium | PASS | `docs/features/F9.md` (vollständig gelesen), `docs/import-manifest.json:229-237`, `docs/trilium-index.md:21`, `FEEDBACK.md:76-79` (F9 korrekt offen) | Trilium-Notiz `WIk1kdJ8vgom` von mir selbst gelesen: existiert unter „Features“ (`IjRpjYJTtqam`), Inhalt deckt Ziel, Entscheidungen, Tests, Grenzen ab; Screenshot `F9-assistent.png` als echtes UI-Bild gelesen |

## Findings

- [Medium] `bin/vibe_guide.py:545` — tmux-Sitzungsname kollidiert mit Paketlauf-Sitzungen
  - Evidence: `_session()` bildet `"vibe-guide-" + safe(name)`. `bin/vibe:509` bildet für Läufe `"vibe-" + safe(name)`. Für ein legitim anlegbares Projekt `guide-proj` (bin/vibe:862 erlaubt `[a-z0-9][a-z0-9_-]*`) ist die Lauf-Sitzung ebenfalls `vibe-guide-proj`: Startet der Assistent für Projekt `proj`, meldet `tmux_has` fälschlich „Für proj läuft bereits ein Assistenten-Auftrag“, solange der Paketlauf von `guide-proj` aktiv ist; umgekehrt meldet `cmd_run` (bin/vibe:746) für `guide-proj` „Läuft bereits“, solange die Assistent-Sitzung von `proj` läuft, und `vibe attach` hängt an der falschen Sitzung an. Das verstößt gegen SPEC.md:191 „Gleiche Namen oder gleich normalisierte Namen dürfen keine Kollision erzeugen.“
  - Required fix: Session-Präfix so wählen, dass `"vibe-" + safe(Projektname)` ihn nie erzeugen kann (oder eine projekt-eindeutige Kommissionierung in den Namen einbeziehen); einen Unit-Test mit zwei kollidierenden Projekten (`proj` vs. `guide-proj`, `tmux_has` injiziert) ergänzen und in F9.md dokumentieren.

- [Medium] `bin/vibe_guide.py:579-586` — Agentenstart umgeht Sandbox und etablierten Lauf-Läufer
  - Evidence: `cmd_run` prüft den Sandbox-Zustand und bricht bei Fehler ab (bin/vibe:748-751) und startet jeden Lauf über `bin/vibe-run.sh`, das Sandbox-Befehle fail-closed behandelt und den Agenten bei `on` in bubblewrap einschließt (vibe-run.sh:36-66, Kommandozeile 86). `start_agent` ruft dagegen `opencode run` direkt in tmux auf: Bei eingeschalteter Sandbox (F7) läuft der Assistent-Agent unsandboxed mit unbegrenzter Shell, SANDBOX-Fehlwerte werden still ignoriert; zudem fehlt der Secrets-/Umgebungs-Aufbau der aktiven Installation aus vibe-run.sh (docs/baseline.md Abschnitt 3). Das umgeht die dokumentierte Architekturgrenze „Eine einzige Quelle für die Auswertung von SANDBOX“ (vibe-run.sh:36-39) und widerspricht SPEC.md:326 („Sicherheits- und Datenintegritätsfehler vor neuen Komfortfunktionen“).
  - Required fix: Alternativen klar entscheiden und dokumentieren: (a) den Assistentenstart über dieselbe Sandbox-/Fail-Closed-Prüfung und denselben Laufpfad (vibe-run.sh bzw. `cmd_run` bis auf die Paket-Iteration) wie Paketläufe leiten, oder (b) die Ausnahme bewusst beschließen und in F9.md (Abschnitt „Grenzen“) plus Trilium ausdrücklich ausweisen. Lieber fail-closed analog F7.

- [Minor] `bin/vibe-web.py:433` / `bin/vibe_guide.py:482-484` — Nicht-Text-Hinweis erzeugt HTTP 500 statt 400
  - Evidence: `body.get("note", "")` wird ungeprüft an `agent_prompt` durchgereicht; eine JSON-Liste/–Objekt als `note` führt in `(note or "").strip()` zu `AttributeError`, die nur vom Sammelhandler als 500 `internal_error` beantwortet wird.
  - Required fix: Typ- und Längenprüfung für `note` analog `_validate_answers`/`_validate_replace` an der Trust-Grenze ergänzen (400 mit Meldung) und einen API-Test dafür aufnehmen.

- [Minor] `bin/vibe_guide.py:572-575` — Vorhandener Entwurf wird vor dem Start gelöscht
  - Evidence: `os.unlink(target)` passiert vor dem eigentlichen Start; wenn `runner` danach mit `code != 0` abbricht (ValueError, Zeile 589-590), ist ein nicht übernommener Entwurf verloren, ohne dass ein Agentenlauf lief und ohne dass darunter eine Ersetzung der `SPEC.md` steht.
  - Required fix: Reihenfolge tauschen, Entwurfsdatei erst nach erfolgtem Start löschen, und einen Fehlerfall-Test ergänzen (Runner gibt 1 zurück, Entwurf bleibt erhalten).

## Verification
- Change set reviewed: Arbeitstree (`feature/f9-projektassistent`). Neue untracked Dateien vollständig gelesen: `bin/vibe_guide.py`, `tests/unit/test_project_guide.py`, `tests/browser/test_project_guide_ui.py`, `docs/features/F9.md`; Screenshot gelesen. Bestehende Kontextdateien gelesen: `bin/vibe-web.py` (guide-relevante Stellen vollständig), `bin/vibe` (Lauf-/Validate-Code), `bin/vibe-run.sh`, `SPEC.md`, `FEEDBACK.md`, `.vibe/project.env`, `templates/generic/AGENTS.md`, Manifest/Dokumentation.
- Git commands run by me: keine — der Shell-/Git-Zugriff wurde durch Berechtigungen verweigert (`Permission denied: shell`), und im Code-Mode-Katalog existiert kein Git-Werkzeug. Damit konnten `git status --short` und `git diff 4fbbd04` nicht selbst ausgeführt werden; Unverändertheit bestehender Tests/Dateien gegenüber dem Ausgangscommit ist daher ausschließlich indirekt geprüft (Volltext-Lesung, Breakevents-Logik wie FEEDBACK-Karte und Sandbox-Karte unangetastet wirkend,pll Green-Testrun).
- Checks with supplied output: `bash scripts/verify.sh quick` (OK: 27 Dateien im Manifest, Syntax, Geheimnisse), `bash scripts/verify.sh full` (Log `verify-full-4.log`, 328 Tests „Ran … OK“, Exit 0), `python3 -m unittest tests.unit.test_project_guide -v` (26 OK), Rot-Phase `ModuleNotFoundError: No module named 'vibe_guide'` — alles vom Coding-Agent vorgelegt, Loginhalt stimmplausibel gegen den Projekt-„Verify“-Befehl, aber nicht von mir ausgeführt.
- Checks not independently run: alle Prüfungen, Testläufe; SHA-256 der Manifest-Einträge nicht selbst nachgerechnet (kein Shellzugriff); Diff gegen 4fbbd04 nicht rekonstruiert.
- Important areas inspected: Pfad-/Symlink-Grenze, replace-Semantik, Platzhalter-/Leer-Antworten, Agentenstart (Argumentliste statt Shellverkettung, Agentennamen-/Notenlimit, Session-Dopplungsschutz), API-Validierung/Statuscodes, UI-Rendering (ausschillicheappendChild-DOM-API, kein innerHTML — draft-/Log-Texte als Textknoten, kein XSS-Kanal),充值 Tests von der Warnung bis zur Verwerfen-Kette, Manifest-/Dokumentations-/Trilium-Synkronisation.
- Remaining risks: (1) mögliche unentdeckte Änderungen an bestehenden Dateien/Tests ohne Diff-Grundlage; (2) zwei Medium-Befunde (Session-Kollision, Sandbox-Bypass) blockieren den finalen PASS; (3) die F9-Doku beansprucht 311 Unit-Tests — die Aufwärtsbewegung von 227 (F8) auf 311 ist um mehr als die neuen 26+2 Tests nicht vinabert,artig, aber der grgreenliersche Gesamtnachweis ist mit dem Log plausibel; kein Markdown-„TODO“ für FEEDBACK-Abhaken verbleibend, F9-Korrekturen erst nach PullRequest-Kommit abhaken.
