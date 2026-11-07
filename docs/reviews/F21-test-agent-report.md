# F21 — Bericht des unabhängigen Test-Agenten

Arbeitsbranch: `feature/f21-ui-agenten-preflight`
Ausgangsstand: `5d806a8`
Datum: 2026-11-07
Testdatei: `tests/unit/test_f21_agents_preflight.py`

Der Test-Agent hat ausschließlich diese Testdatei angelegt bzw. ergänzt. Der
Bericht wird hier als Nachweis der Herkunft und der beobachteten Rotphase
abgelegt.

## Erste Runde: 20 Tests

### Testfälle

| Test | Vorbedingung | Aktion | Erwartung |
|---|---|---|---|
| `test_reviewer_role_from_profiles_json_completes_preflight` | project.env ohne REVIEWER, profiles.json mit Rolle reviewer, Agentendatei vorhanden | Preflight | keine Fehler |
| `test_project_local_agent_file_satisfies_the_reviewer_role` | nur projektlokale Agentendatei | Preflight | keine Fehler |
| `test_explicit_reviewer_argument_wins_over_profiles_role` | profiles.json hat Reviewer; Argument nennt fehlenden Agenten | Preflight | REVIEWER-Fehler, Argument nicht ersetzt |
| `test_project_env_reviewer_wins_over_profiles_role` | project.env nennt fehlenden Reviewer; profiles.json hat verfügbaren | Preflight | REVIEWER-Fehler |
| `test_unavailable_role_entry_does_not_block_an_available_reviewer` | erster Rolleneintrag ohne Datei, zweiter mit Datei | Preflight | keine Fehler |
| `test_missing_reviewer_role_blocks_with_reviewer_message` | profiles.json ohne reviewer-Rolle | Preflight | REVIEWER-Fehler |
| `test_reviewer_role_without_available_agent_blocks` | Rolle zeigt auf fehlende Datei | Preflight | REVIEWER-Fehler mit Agentennamen |
| `test_missing_profiles_file_blocks_without_crash` | keine profiles.json | Preflight | REVIEWER-Fehler, kein Absturz |
| `test_broken_profiles_file_blocks_without_crash` | ungültiges JSON | Preflight | REVIEWER-Fehler, kein Absturz |
| `test_profiles_with_invalid_roles_structure_blocks_without_crash` | `rollen` ist Liste | Preflight | REVIEWER-Fehler, kein Absturz |
| `test_dirty_worktree_still_blocks_with_role_resolved_reviewer` | untracked Datei im Projekt | Preflight | Arbeitsbaum-Fehler |
| `test_missing_test_agent_still_blocks_with_role_resolved_reviewer` | TESTER-Agentendatei entfernt | Preflight | TESTER-Fehler |
| `test_cli_preflight_resolves_reviewer_from_state_directory` | CLI mit `--state` | Preflight | Exit 0, kein BLOCKIERT |
| `test_cli_preflight_without_state_still_blocks_missing_reviewer` | CLI ohne `--state` | Preflight | Exit 2, REVIEWER |
| `test_registry_stores_blocked_as_final_state` | laufender Registereintrag | `finish(state="blocked")` | blocked und Exitcode gespeichert |
| `test_registry_rejects_unknown_final_state` | laufender Registereintrag | `finish(state="kaputt")` | ValueError, Zustand unverändert |
| `test_cli_finish_accepts_blocked_and_returns_zero` | laufender Registereintrag | CLI `finish --state blocked` | Exit 0, Register blocked |
| `test_cli_finish_rejects_unknown_state` | laufender Registereintrag | CLI `finish --state kaputt` | Exit 2, Zustand unverändert |
| `test_runner_passes_preflight_without_reviewer_in_project_env` | echter Runner, project.env ohne REVIEWER, Rolle in profiles.json | Lauf | Exit 0, ein Agentenaufruf, F1 geschlossen |
| `test_blocked_preflight_finishes_the_run_register_as_blocked` | Lauf vorab starting, unsauberer Arbeitsbaum, VIBE_RUN_ID | Lauf | Exit 2, Register blocked mit Exitcode 2 |

### Rotphase vor der Implementierung

```bash
python3 -m unittest discover -s tests/unit -p 'test_f21_agents_preflight.py' -v
# EXIT=1, 20 Tests: 13 errors, 4 failures, 3 ok
```

Erwartete Rot-Gründe:

- 12× `TypeError: preflight_errors() got an unexpected keyword argument 'state_dir'`
- 1× `ValueError: Unbekannter Laufzustand: 'blocked'`
- CLI: `vibe_packages.py: error: unrecognized arguments: --state ...`
- CLI: `vibe_runs.py finish: error: argument --state ...`
- Integration: `BLOCKIERT: REVIEWER fehlt ...`
- Register: `AssertionError: 'starting' != 'blocked'`

Drei Tests waren bewusst schon vor der Implementierung grün, weil sie
bestehendes Verhalten als Regressionswächter prüfen (CLI ohne `--state`
blockiert; unbekannter Registerzustand wird abgelehnt).

### Bestehende betroffene Tests

```bash
python3 -m unittest tests.unit.test_package_gates tests.unit.test_run_control tests.unit.test_runner_package_gates -v
# EXIT=0, 68 Tests OK

python3 scripts/check-syntax.py
# EXIT=0, 98 Python-, 8 Bash-, 5 JSON-Dateien geprüft
```

## Nachtrag nach Review: 2 Tests für sichere Agentennamen

| Test | Vorbedingung | Aktion | Erwartung |
|---|---|---|---|
| `test_invalid_reviewer_role_names_are_ignored` | profiles.json enthält genau einen reviewer-Eintrag mit unsicherem Namen (`../ausserhalb`, `name mit leerzeichen`, `name;rm`); passende Datei existiert | Preflight je Fall | unsicherer Name ignoriert; REVIEWER-Blockade; außerhalb liegende Datei nicht akzeptiert |
| `test_valid_reviewer_beside_unsafe_entry_remains_usable` | unsicherer Eintrag mit außerhalb liegender Datei, danach gültiger `code-reviewer` mit Agentendatei | Preflight; danach gültige Datei entfernen und erneut | zuerst keine Fehler; danach REVIEWER-Blockade, unsicherer Eintrag kein Ersatz |

### Rotphase vor der Namensvalidierung

```bash
python3 -m unittest discover -s tests/unit -p 'test_f21_agents_preflight.py' -v
# EXIT=1, Ran 22 tests, FAILED (failures=4)
```

- 20 bisherige Tests grün.
- 3 Subtests von `test_invalid_reviewer_role_names_are_ignored` rot:
  `AssertionError: False is not true : []`
- `test_valid_reviewer_beside_unsafe_entry_remains_usable` rot:
  `AssertionError: False is not true : []`

Die neuen Tests scheiterten genau am fehlenden Namensfilter: Die unsicheren
Einträge wurden als verfügbare Agenten akzeptiert, obwohl der Preflight
blockieren muss.

### Grünphase nach der Implementierung

```bash
python3 -m unittest discover -s tests/unit -p 'test_f21_agents_preflight.py' -v
# EXIT=0, Ran 22 tests, OK
```
