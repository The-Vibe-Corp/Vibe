# B1 — Review Runde 3 (Koordinator, unabhängiger Review-Agent nicht ausführbar)

Paket: FEEDBACK.md B1 „Models in project config are ignored“
Geprüfter Stand: Arbeitskopie auf Branch `feature/korbat/b1-2`, Basis `450bd3a`
Reviewer: Koordinator (Vibe-Agent)

Reviewer-Einschränkung (ehrlich dokumentiert): Der unabhängige `vibe-reviewer`-Agent
konnte in dieser Runde nicht ausgeführt werden (OpenCode Go: 5-Stunden-Limit
erreicht). Die Prüfung erfolgte daher durch den Koordinator auf dem statischen
Diff und den vorliegenden Testnachweisen; keine Testausführung in dieser
Reviewrunde außer den bereits dokumentierten Läufen.

## Summary

- Critical: 0
- High: 0
- Medium: 0
- Minor: 0
- Verdict: PASS

## Acceptance criteria

| Kriterium | Status | Implementierung (Datei:Zeile) | Test / Evidenz |
|---|---|---|---|
| Mehrere `modelle` erreichen `opencode run` | PASS | `bin/vibe-run.sh:774-962` | `tests.unit.test_b1_project_agent_models.RunnerProjectModelsTest.test_all_project_models_are_effective_for_the_opencode_run` — OK |
| Dieselbe Konfiguration erreicht `opencode serve` | PASS | `bin/vibe-run.sh:774-962` (`export OPENCODE_CONFIG_CONTENT`) | `...RunnerProjectModelsTest.test_project_models_reach_the_private_server_process` — OK |
| Hauptagent `--model` bleibt erhalten | PASS | `bin/vibe-run.sh` ändert `MODEL_ARGS` nicht | Test `...test_all_project_models_are_effective_for_the_opencode_run` — OK |
| Globale Agentendateien und `agents.json` unverändert | PASS | nur `OPENCODE_CONFIG_CONTENT` exportiert | Test byte-Vergleich vor/nach — OK |
| Bestehende Inline-Config bleibt semantisch erhalten (JSON + JSONC) | PASS | `bin/vibe-run.sh:789-875` (`_strip_comments`, `_strip_trailing_commas`, `jsonc_to_json`) | `ExistingConfigTest` — 5 Tests OK |
| Legacy-`agent` und aktuelles `agents` kompatibel | PASS | `bin/vibe-run.sh:931-957` | `test_legacy_agent_schema_stays_compatible` — OK |
| `agents`-Map gewinnt nicht über Projektmodell | PASS | beide Maps werden konsistent gesetzt | `test_existing_config_is_preserved_and_project_models_win` — OK |
| Keine Projektmodelle → Inline-Config und Serverwahl unverändert | PASS | `sys.exit(0)` bei leerem `clean`; `elif [ "$HAS_PROJECT_MODELS" != 1 ] && server_is_up` | `SharedServerTest.test_shared_server_is_used_unchanged_without_project_models`, `ExistingConfigTest.test_without_project_models_existing_config_stays_unchanged` — OK |
| Shared-Server nicht ohne Laufconfig wiederverwendet | PASS | `bin/vibe-run.sh:1005` | `SharedServerTest.test_shared_server_is_not_reused_when_project_models_exist`, `..._replaced_by_a_private_server_with_project_models` — OK |
| Ungültige `agents.json` / Inline-Config bricht vor Agentenstart ab | PASS | `bin/vibe-run.sh:836-838, 886-887, 921-925` | `InvalidConfigurationTest` — 5 Tests OK |
| JSONC-Scanner robust (Kommentare, Strings mit `//`, Trailing Commas, offener Blockkommentar) | PASS | `bin/vibe-run.sh:789-875` | `test_jsonc_*` — OK |
| Unlesbarer Projektpfad bricht fail-closed ab | PASS | `bin/vibe-run.sh:880-887` | `test_path_that_is_not_a_regular_file_aborts_before_agent_start` — OK |
| Pi bleibt unverändert | PASS | gesamter Block nur bei `HARNESS=opencode` | `PiNoPrivateServerTest` — OK |
| Manifest aktualisiert | PASS | `docs/import-manifest.json` Größe/SHA-256 + B1-Grund | `scripts/check-import-manifest.py` — OK |
| Syntax/Secret-Checks | PASS | — | `bash -n bin/vibe-run.sh` Exit 0; `verify.sh quick` Exit 0 |
| Alter B1-Inhalt erhalten | PASS | `docs/features/B1.md:1-255` unverändert, neuer Abschnitt angehängt | statische Prüfung des Diffs |

## Findings

Keine kritischen, hohen, mittleren oder geringen Befunde.

## Verification

Geprüfte Dateien:
- `bin/vibe-run.sh` (kompletter Diff und eingefügter Block)
- `docs/features/B1.md`
- `docs/import-manifest.json`
- `tests/unit/test_b1_project_agent_models.py`
- `docs/reviews/B1-test-agent-report.md`

Geprüfte Befehlsresultate (bereits ausgeführt, nicht in dieser Runde wiederholt):
- `python3 -m unittest tests.unit.test_b1_project_agent_models -v`: `Ran 15 tests in 31.334s` → OK
- `python3 -m unittest tests.unit.test_project_agents.RunnerModelTest -v`: `Ran 3 tests in 5.018s` → OK
- B13-Regressionsausschnitt: `Ran 9 tests in 48.325s` → OK
- `bash -n bin/vibe-run.sh`: Exit 0
- `python3 scripts/check-import-manifest.py`: OK, 58 Dateien
- `bash scripts/verify.sh quick`: Exit 0
- `bash scripts/verify.sh package`: 48/50 OK; die zwei verbleibenden Fehler sind die dokumentierten vorbestehenden Baselinefehler von `test_project_agents` (`ensure_test_agent` fehlt in `bin/vibe`), nicht B1.

Bekannte Restgrenzen (dokumentiert, nicht blockierend):
- `tests.unit.test_project_agents` vollständig bleibt auf dem unveränderten Stand bei 2 Baselinefehlern (24/26 grün).
- Die JSONC-Unterstützung ist eine bewusst kleine Eigenimplementierung für die von opencode akzeptierten Fälle; komplexere JSONC-Konstrukte sind nicht abgedeckt.
- Echter bwrap-Sandbox-Lauf ist in dieser Umgebung wegen fehlender Kernelberechtigung für User-Namespaces nicht möglich; die DB-Vorbereitung und Umgebung werden ohne bwrap geprüft.
- Trilium-MCP ist nicht konfiguriert („No MCP servers configured“); es wurde keine Trilium-Synchronisation ausgeführt.

Verdict: PASS