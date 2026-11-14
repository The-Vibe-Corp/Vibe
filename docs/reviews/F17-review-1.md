Ich habe alle F17-Dateien im Arbeitsbaum gegen den vorgelegten Diff geprüft. Zusammenfassung meiner Prüfung und das Ergebnis:

# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 1
- Minor: 0
- Verdict: CHANGES REQUIRED

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Test (file:method) / Evidence |
|---|---|---|---|
| Bugfix: Modellauswahl wird ohne „In Rohtext übernehmen“ gespeichert | PASS | `bin/vibe-web.py:607-614` (values → `agent_render_fields`), `bin/vibe:1626-1648`, `bin/vibe:1584-1624` (unbekannte Felder erhalten), `bin/vibe-web.py:1258-1289` (`baseline`/Diff-Versand) | `tests/unit/test_agent_management.py:742` (`test_api_save_applies_changed_structured_values`) und `tests/browser/test_project_agents_ui.py:215` (`test_model_selection_is_saved_without_manual_render`); supplied output „OK“, Rotphase belegt |
| Projektansicht mit Agentenauswahl | PASS | `bin/vibe:1730-1890`, `bin/vibe-web.py:183-197` (GET), `bin/vibe-web.py:588-599` (POST), `bin/vibe-web.py:923-940` (`projectAgentsCard`) | `tests/unit/test_project_agents.py` SelectionTest (10 Tests, tatsächliche Dateien in temp. Arbeitsbereich); supplied output „21 tests OK“; Browser-Test `test_project_selection_and_model_override_are_saved_and_shown` |
| Auswahl wird beim Agentenlauf durchgesetzt | PASS | `bin/vibe:1168-1171` + `bin/vibe:1885-1890` (`run_agent_selection` in `cmd_run` vor tmux) | `test_run_selection_rejects_a_disabled_agent`, `test_cmd_run_aborts_before_tmux_for_a_disabled_agent` — grün laut supplied output; Rotphase nur für `run_agent_selection`-Tests dokumentiert (s. Finding M-1) |
| Modell standardmäßig aus übergreifender Konfig, je Projekt überschreibbar | PASS | `bin/vibe:1800-1846` (Inventory/Rows, `effective_model = override or base`), `bin/vibe:1192-1197` (Argument `"$7"`), `bin/vibe-run.sh:52-62,186` (gefiltertes `--model` per Array, keine Shell-Auswertung) | `test_model_override_wins_over_the_agent_file_and_can_be_cleared`, `test_run_selection_returns_the_project_override`, `test_model_override_is_forwarded_to_opencode`, `test_without_override_no_model_flag_is_sent`, `test_invalid_model_aborts_before_opencode` (echter Läufer + opencode-Attrappe) |
| Validierung, Atomarität, Concurrency | PASS | `bin/vibe:1744-1798` (`_project_agents_check`, `write_text` mit `expected`/`MISSING`), `bin/vibe:1855-1883`, `bin/vibe-web.py:595-596` (409), `bin/vibe_storage.py:140-163,329` | `test_corrupt_config_is_reported_and_never_overwritten`, `test_unknown_config_keys_are_rejected_instead_of_dropped`, `test_non_string_model_in_the_file_is_reported`, `test_concurrent_change_is_refused`, `test_invalid_model_is_rejected_without_writing` u. a. |
| UI-Verhalten und Fehleranzeige | PASS | `bin/vibe-web.py:936-939` (Fehleranzeige ohne „null“), `bin/vibe-web.py:904` (Karte im Reiter Einstellungen) | Browser-Test mit Chromium; Screenshot `docs/features/F17-agenten.png` von mir direkt geöffnet: echte Oberfläche (1500×1100, Karte „Agenten in diesem Projekt“, Toast „Agentenauswahl gespeichert“), kein Platzhalter |
| Tests + Fach-/Trilium-Dokumentation | PASS | `docs/features/F17.md`, `docs/import-manifest.json` (F17-Eintrag, Hashes aktualisiert; `scripts/verify.sh` nicht berührt) | Trilium-Notiz `ullL9BIh9cui` „F17 Agentenverwaltung je Projekt“ von mir per MCP gelesen (geändert 2026-11-02, Parent `IjRpjYJTtqam`) — Trilium-Dokumentation nachweislich vorhanden |

## Findings

- [Medium] `docs/features/F17.md:1595-1612` — Rotphasen-Nachweis deckt nur 19 der 21 Unit-Tests
  - Evidence: F17.md dokumentiert für `tests.unit.test_project_agents` die Rotphase mit „Ran 19 tests … FAILED (failures=3, errors=16)“. Im Endstand enthält die Datei laut Arbeitsbaum 21 Tests (grep bestätigt). Nur 3 Fehlschläge + 16 Fehler ergeben genau 19 fehlgeschlagene Tests; die beiden `cmd_run`-Tests `test_cmd_run_aborts_before_tmux_for_a_disabled_agent` und `test_cmd_run_passes_the_project_model_override` (`tests/unit/test_project_agents.py:394,410`) — genau die Prüfpunkte Auswahl-Durchsetzung und Übergabe an den Lauf — fehlen damit in der dokumentierten Rotphase. Zwar decken die roten `run_agent_selection`-Tests dieselben Fachregeln ab, und die Implementierung habe ich im Quelltext verifiziert, aber der geforderte Failing-first-Nachweis für diese beiden Tests liegt nicht vor; der Rotlauf-Dateistand (19 Tests) weicht vom committeten Stand ab, was nicht erklärt ist.
  - Required fix: Beide `cmd_run`-Tests gegen die Basis-Kopie (Ausgangscommit + Tests ohne F17-Implementierung) ausführen, ihre Fehlschläge mit Ausgaben in `docs/features/F17.md` ergänzen, und den abweichenden Rotlauf-Dateistand (19 vs. 21 Tests) korrekt beschreiben — keine Änderung an Produkt- oder Testcode.

## Verification
- Change set reviewed: Ausgangscommit `0031166..Arbeitsbaum` (vorgelegter vollständiger Diff in `.f17-review-diff.txt` + direkte Lese-Verifikation aller F17-Dateien im Arbeitsbaum).
- Git commands run by me: `git status`, `git diff` — nicht möglich; Shellzugriff wurde mit „Permission denied: shell“ abgelehnt, der Diff stammt vollständig aus der vorgelegten Review-Datei und wurde stichproben-/passagenweise gegen den Arbeitsbaum abgeglichen (alle grepbaren Symbole vorhanden, `bin/vibe:1192-1197,1626-1648,1730-1890`, `bin/vibe-web.py:588-614,923-940,1258-1289`, `bin/vibe-run.sh:52-62,186`).
- Checks with supplied output: Rotphase (19 F/16 E unit, 2 browser-Failures, beide AgentApiTests FAIL), Grünphase (21/6/2 OK), `verify.sh quick` Exit 0, `verify.sh full` 8+7 Umgebungsfehler identisch am Ausgangscommit — alles angebotsseitige Nachweise, plausibel und präzise beschrieben (benannte vorbestehende Tests, Ursache schreibgeschütztes /tmp / verschachteltes bwrap), aber von mir nicht unabhängig wiederholbar.
- Checks not independently run: alle Builds/Tests (`unittest`, `verify.sh`), Manifest-Hash-Prüfung (ohne Shell kein sha256), Baseline-Vergleich der 8+7 Fehlschläge.
- Important areas inspected: `bin/vibe` F17-Baustein und `cmd_run`, `bin/vibe-run.sh`, `bin/vibe-web.py` (API/PAGE), `vibe_storage.write_text/expected/MISSING` (Atomarität/409), `agent_render_fields`/`_apply_agent_fields` (unbekannte Felder erhalten), alle drei Testdateien vollständig, `docs/features/F17.md`, `F17-agenten.png` (direkt angesehen), `docs/import-manifest.json`, FEEDBACK.md-Eintrag F17 (korrekt offen), Trilium-Notiz.
- Remaining risks: Einfachdirekter Aufruf von `bin/vibe-run.sh` unter Umgehung von `cmd_run` prüft die Projektauswahl nicht (Dokumentation nennt den Läufer nur als Empfänger; im normalen Laufpfad alleinige Einstiegsstelle ist `cmd_run` — Verifizierung „nicht verifiziert“ durch die mitgelieferten, weltweit plausiblen Prüfausgaben bestätigt die sonstige Durchsetzung nicht vollständig).

## Urteil (kurzfassung)

**2. Befund nach Schweregrad:**

- **Medium** — Rotphasen-Evidenz unvollständig für die beiden `cmd_run`-Lauftests (Details oben; Datei/Zeilen: `docs/features/F17.md:1597-1604`, `tests/unit/test_project_agents.py:394 ff.`).
- Keine Critical-, kein weiterer High-/Medium-Befund. Alles von mir direkt geprüfte Verhalten (Speichern strukturierter Felder inkl. Erhalt unbekannter Felder wie `color: blau` — `bin/vibe:1591-1605`; Validierung ohne Schreiben — `bin/vibe:1544-1570`/`1865-1876`; Projektisolierung; Effective-Model-Sicht; Läuferübergabe ohne Shell-Injektion via Array-Argument und Regex an beiden Schichten, `bin/vibe:1738` und `bin/vibe-run.sh:57`) ist korrekt und sauber umgesetzt; die Begründungen in `docs/features/F17.md` decken die Grenzen (kein nachträgliches Abwählen laufender Agenten, keine Anbieterverfügbarkeitsprüfung) ehrlich ab.

**3. Prüfzusammenfassung:** Vorgelegte Review-Datei vollständig gelesen; alle F17-Dateien im Arbeitsbaum auf Übereinstimmung geprüft; Speicher-/CLI-/Läufer-/API-/UI-Implementierung nachvollzogen (u. a. BLOCKED bei Shell: keine eigene Testausführung); Screenshot und Trilium-Notiz unabhängig verifiziert; FEEDBACK.md-Eintrag bewusst offen gelassen (Abhaken erst nach PASS ist korrekt). Ein Befund (unvollständiger Rotphasen-Nachweis für 2 von 21 Unit-Tests) verhindert gemäß Prüfregeln das PASS; kein Codefehler bekannt. Beanstandungen beheben (reine Nachweiserweiterung in F17.md), sonst unverändert lassen, dann erneut reviewen.
