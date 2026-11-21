# Review result

## Summary
- Critical: 0
- High: 0
- Medium: 0
- Minor: 1
- Verdict: PASS

## Acceptance criteria
| Criterion | Status | Implementation (file:line) | Verification evidence |
|---|---|---|---|
| **1. C1–C5 (`init`/`adopt` Test-Agent-Meldung ohne `NameError`)**: Fix der undefinierten Variablen `agent` (`cmd_init`) und `agent_note` (`_adopt_checked_out_project`); explizites Verfolgen von `.opencode/agents/test-agent.md` über `created` aus `copy_tree` (`TEST_AGENT_REL`/`_test_agent_created`); Meldung/Notiz nur bei Neuanlage; kein hardcoded Test-Agent, kein `TESTER=`-Schreiben, keine neue Vorlage `templates/common/.opencode/agents/test-agent.md`. | PASS | `bin/vibe:2739-2758`, `bin/vibe:2967-2976` | `tests/unit/test_ap5_korbat_init_adopt.py:137-275` (8 Tests); Rotphase in `docs/reviews/AP5-Korbat-test-agent-report.md:154` (8× `NameError: name 'agent' is not defined`); Grünlauf gemeldet (`Ran 13, OK` zusammen mit Transport-Suite; `test_ap9_github` `Ran 44, OK` ohne `agent_note`-`NameError`). |
| **2. `project.env`-Transport (AP5.md §5.3)**: Read-only, einwegige Kopie von `<project>/.vibe/project.env` nach `<worktree>/.vibe/project.env` (`0444` best effort); idempotenter Eintrag `.vibe/project.env` in `info/exclude` des Worktrees; ohne Quelldatei kein `.vibe/`-Ordner und kein Exclude; niemals `_secrets.env` oder andere `.vibe/`-Dateien; niemals Rückschreiben in `sync_proof`; bei `RECONNECT=1` wird `copy-notes` übersprungen (`bin/vibe-run.sh:1529-1531`). | PASS | `bin/vibe_packages.py:105`, `bin/vibe_packages.py:201-251`, `bin/vibe_packages.py:303-346`, `bin/vibe_packages.py:1576-1590`, `bin/vibe-run.sh:1529-1537` | `tests/unit/test_ap5_korbat_project_env_transport.py:60-280` (5 Tests); Rotphase in `docs/reviews/AP5-Korbat-test-agent-report.md:155`; Grünlauf gemeldet (`Ran 13, OK`). |
| **3. T-V1 (`VERIFY_PACKAGE_TESTS` entkoppelt Paket- vom Vollmodus)**: `VERIFY_PACKAGE_TESTS` (Default leer) steuert den Testnachweis im Modus `package`; `VERIFY_TESTS` gilt ausschließlich für `full` (unverändert streng inkl. Pflicht, Dateiprüfung, Mindestanzahl und Exit 6); Hilfe (`USAGE`) und Modul-Docstring aktualisiert. | PASS | `scripts/verify.py:20-34`, `scripts/verify.py:61-74`, `scripts/verify.py:404-436`, `scripts/verify.py:473-481` | `tests/unit/test_verify_script.py:418-667` (`VerifyPackageTest`); Rotphase in `docs/reviews/AP5-Korbat-test-agent-report.md:157`; Grünlauf gemeldet (`Ran 34`, davon 33 OK, einzig der dokumentierte Umgebungsfall `RepositoryVerifyTest` rot). |
| **4. T-V2 (Kurzer Verify-Temppfpad `vv-` und `$VIBE_VERIFY_TMP`)**: `TEMP_PREFIX = "vv-"`; optionaler Elternordner über `VIBE_VERIFY_TMP` (mit sauberem Exit 3 bei `OSError`); ohne `VIBE_VERIFY_TMP` Standardverhalten über `tempfile.mkdtemp(prefix=TEMP_PREFIX)` (`TMPDIR`-konform); Aufräumen und `--keep` unverändert. | PASS | `scripts/verify.py:59`, `scripts/verify.py:438-449`, `scripts/verify.py:499-504` | `tests/unit/test_verify_script.py:708-789` (`VerifyTempDirectoryTest`, 3 Tests); Rotphase in `docs/reviews/AP5-Korbat-test-agent-report.md:157`; Grünlauf gemeldet. |
| **5. 4a (GUI-Button „Paket abschließen" & Dokumentation)**: Bestandsbutton in Nova (`nvpBoardColumn`, `/api/package` mit `action: 'close'` → `vibe.package_close`) jetzt für `column === 'blocked' \|\| column === 'waiting'` und `!isFeedback` verfügbar; Lage und Bedienung für den Nutzer in der Feature-Dokumentation beschrieben. | PASS | `bin/web/nova-project.js:138-154`, `docs/features/AP5-Korbat.md:53-60`, `docs/features/AP5-Korbat.md:248-251` | `tests/unit/test_ap5_korbat_waiting_state.py:502-519` (`test_nova_offers_package_close_in_blocked_and_waiting_columns`); Grünlauf gemeldet (`Ran 20, OK`). |
| **6. 4b (Neuer Zustand `WARTET AUF MERGE` statt `BLOCKIERT` für PR-only)**: `WAITING_MARKER = "WARTET AUF MERGE:"`, `is_waiting_merge`, `mark_waiting_merge`, CLI `mark-waiting`; `_apply_proof` entfernt `BLOCK_MARKER` und `WAITING_MARKER`; `select_package` überspringt wartende Pakete in `_ready`, erlaubt aber `prefer`-Reattach; `status_report["waiting"]` (`blocked` vor `waiting`); `priority_view` meldet `"wartet auf merge"` in `order` und `standard`; `bin/vibe` `open_items` und `_parse_entry` liefern `"WARTET AUF MERGE"` (`BLOCKIERT` hat Vorrang); `bin/vibe-run.sh` `pr_only_fallback` ruft `mark-waiting`; Nova-Board (`open`, `waiting`, `blocked`, `proof`, `done`), Kachel `waiting`, Label `"Wartet auf Merge"`, Pille `nv-warn`; `i18n.js` EN `"Waiting for merge"`; `app.js` Pille `warn`; Bestandsschutz für alte `BLOCKIERT:`-Vermerke. | PASS | `bin/vibe_packages.py:80`, `bin/vibe_packages.py:282-286`, `bin/vibe_packages.py:406-409`, `bin/vibe_packages.py:694-707`, `bin/vibe_packages.py:1252-1283`, `bin/vibe_packages.py:1396-1414`, `bin/vibe_packages.py:1446-1453`, `bin/vibe_packages.py:1487-1491`, `bin/vibe_packages.py:1668-1677`, `bin/vibe_packages.py:1896-1903`, `bin/vibe:589-592`, `bin/vibe:641-645`, `bin/vibe-run.sh:1369-1378`, `bin/web/nova-project.js:53-69`, `bin/web/nova-project.js:124-163`, `bin/web/nova-project.js:981-988`, `bin/web/nova-project.js:1039`, `bin/web/i18n.js:902`, `bin/web/app.js:633`, `bin/web/app.js:657`, `bin/web/app.js:1123` | `tests/unit/test_ap5_korbat_waiting_state.py:106-563` (20 Tests), `tests/unit/test_ap4_korbat_github.py:946-996` (`PrOnlyRunnerTest`), `tests/unit/test_b16_runner_wiring.py:114-174` (`PrOnlyClosureTest`); Rotphase in `docs/reviews/AP5-Korbat-test-agent-report.md:156,158,225-263`; Grünläufe gemeldet (`Ran 20, OK`, `Ran 21, OK`, `Ran 6, OK`). |
| **7. 4c (Credential-Auflösung aus dem Projektpfad in `ensure_mergeable`)**: `ensure_mergeable` löst das Git-Credential einmal über `credential_for_git(project)` auf und reicht es per `with _credential_passdown(...):` an `remotes(wt)` und `_ensure_mergeable(wt, base_ref)` weiter; Rücksetzen im `finally`-Block von `_credential_passdown`; Token ausschließlich in `VIBE_GITHUB_CREDENTIAL` (Prozessumgebung), nie in `argv` oder Meldungen/Logs. | PASS | `bin/vibe_github.py:418-427`, `bin/vibe_github.py:570-585`, `bin/vibe_github.py:1439-1444` | `tests/unit/test_ap4_korbat_github.py:404-504` (`EnsureMergeableCredentialTest`, 2 Tests); Rotphase in `docs/reviews/AP5-Korbat-test-agent-report.md:158`; Grünlauf gemeldet (`Ran 21, OK`). |

## Findings
- [Minor] `bin/web/i18n.js:902` (`DICTS.en`) vs. `bin/web/i18n.js:1903-1968` (`DICTS.de`), `bin/vibe:599-601`, `bin/vibe:934-938`, `docs/import-manifest.json:1200-1209` — Kleine Symmetrie- und Metadaten-Lücken um den neuen Zustand `WARTET AUF MERGE`
  - Evidence:
    1. In `bin/web/i18n.js:902` wurde `"Wartet auf Merge": "Waiting for merge"` in `DICTS.en` ergänzt, in `DICTS.de` (um Zeile 1911) fehlt das symmetrische Identitätspaar `"Wartet auf Merge": "Wartet auf Merge"`. Da `t()` in `bin/web/i18n.js:2071-2075` bei einem in `DICTS.de` fehlenden Schlüssel zunächst auf `DICTS[DEFAULT_LANG]` (`DICTS.en`) zurückfällt (`else if (Object.prototype.hasOwnProperty.call(DICTS[DEFAULT_LANG], key)) text = DICTS[DEFAULT_LANG][key];`), liefert `tr('Wartet auf Merge')` bei aktivierter deutscher Oberfläche (`lang === 'de'`) den englischen String `"Waiting for merge"` statt `"Wartet auf Merge"`.
    2. In `bin/vibe:599-601` enthält `_FEEDBACK_LABEL` zwar `BLOCKIERT`, aber nicht `WARTET AUF MERGE`. Folgt eine `WARTET AUF MERGE:`-Zeile unmittelbar auf einen `Beschreibung:`-Block, wird sie beim Parsen in `_parse_entry` (`bin/vibe:632-635`) an `description` angehängt und beim Bearbeiten des Tickets in der Oberfläche als Teil der Beschreibung übernommen.
    3. In `bin/vibe:934-938` (`cmd_priority`) kennt das `marks`-Dict für `view["order"]` nur `"erledigt"`, `"gesperrt"` und `"fehlt"`, nicht aber den neuen Status `"wartet auf Merge"` aus `vibe_packages.priority_view`, sodass `vibe priority <projekt> list` wartende Pakete ohne Statuszusatz ausgibt.
    4. In `docs/import-manifest.json:1210-1370` sind die `bytes`- und `sha256`-Werte der 7 geänderten `bin/**`-Dateien zwar exakt aktualisiert (`check-import-manifest.py` prüft nur `files` und läuft daher mit Exit 0 durch), im Array `aenderungen` (`docs/import-manifest.json:2-1209`) wurde jedoch noch kein Chronik-Eintrag für `AP5-Korbat` ergänzt (entgegen dem Hinweis in `docs/import-manifest.json:1547`).
  - Required fix: Vor einem späteren Nachzug (nicht blockierend für dieses Verdict): (1) `"Wartet auf Merge": "Wartet auf Merge"` in `DICTS.de` in `bin/web/i18n.js` ergänzen, (2) `WARTET AUF MERGE` in `_FEEDBACK_LABEL` (`bin/vibe:599-601`) und `"wartet auf Merge"` in `marks` (`bin/vibe:934-936`) aufnehmen sowie (3) den `AP5-Korbat`-Eintrag in `aenderungen` von `docs/import-manifest.json` nachtragen.

## Verification
- Change set reviewed: `1048210..working tree` (Inspektion aller geänderten und neuen Dateien des Arbeitspakets über die Read-Werkzeuge: `bin/vibe`, `bin/vibe_packages.py`, `bin/vibe_github.py`, `bin/vibe-run.sh`, `scripts/verify.py`, `bin/web/nova-project.js`, `bin/web/i18n.js`, `bin/web/app.js`, `docs/import-manifest.json`, `docs/features/AP5-Korbat.md`, `docs/reviews/AP5-Korbat-test-agent-report.md`, `tests/unit/test_ap5_korbat_init_adopt.py`, `tests/unit/test_ap5_korbat_project_env_transport.py`, `tests/unit/test_ap5_korbat_waiting_state.py`, `tests/unit/test_verify_script.py`, `tests/unit/test_ap4_korbat_github.py`, `tests/unit/test_b16_runner_wiring.py`).
- Git commands run by me: none (in dieser Read-only-Review-Sitzung steht kein Shell-/Git-Tool zur Verfügung; alle Prüfungen erfolgten durch direkte Dateiinspektion mit `read`).
- Checks evidenced by supplied raw output:
  - Vor-Implementierungs-Rotphase des unabhängigen Test-Agenten (`docs/reviews/AP5-Korbat-test-agent-report.md:147-180`):
    - `python3 -m unittest tests.unit.test_ap5_korbat_init_adopt -v` → `Ran 8 tests`, `FAILED (errors=8)` (`NameError: name 'agent' is not defined` in `bin/vibe:2743`)
    - `python3 -m unittest tests.unit.test_ap5_korbat_project_env_transport -v` → `Ran 5 tests`, `FAILED (failures=2, errors=2)`
    - `python3 -m unittest tests.unit.test_ap5_korbat_waiting_state -v` → `Ran 20 tests`, `FAILED (failures=17, errors=1)`
    - `python3 -m unittest tests.unit.test_verify_script -v` → `Ran 34 tests`, `FAILED (failures=9)`
    - `python3 -m unittest tests.unit.test_ap4_korbat_github -v` → `Ran 21 tests`, `FAILED (failures=2)`
    - `python3 -m unittest tests.unit.test_project_management -v` → `Ran 36 tests`, `FAILED (failures=4, errors=15)`
    - `python3 -m unittest tests.unit.test_ap9_github -v` → `Ran 44 tests`, `FAILED (failures=1)` (`NameError: name 'agent_note' is not defined`)
  - Nachlauf des unabhängigen Test-Agenten nach Volllauf-Vertragstreffer (`docs/reviews/AP5-Korbat-test-agent-report.md:256-261`):
    - `env -u GITHUB_AUTO_MERGE python3 -m unittest tests.unit.test_b16_runner_wiring -v` → `Ran 6 tests`, `OK` (Exit 0)
- Checks reported only by the coding agent:
  - `python3 -m unittest tests.unit.test_ap5_korbat_init_adopt tests.unit.test_ap5_korbat_project_env_transport` → `Ran 13, OK`
  - `python3 -m unittest tests.unit.test_ap5_korbat_waiting_state` → `Ran 20, OK`
  - `python3 -m unittest tests.unit.test_verify_script` → `Ran 34, FAILED (failures=1)` (einzig `RepositoryVerifyTest`, umgebungsbedingt mangels `.vibe/project.env` im Worktree)
  - `env -u GITHUB_AUTO_MERGE python3 -m unittest tests.unit.test_ap4_korbat_github` → `Ran 21, OK`
  - `python3 -m unittest tests.unit.test_ap9_github` → `Ran 44, OK`
  - `python3 -m unittest tests.unit.test_project_management` → `Ran 36, FAILED (failures=6, errors=1)` (vorbestehende F22-Baseline; alle 14 `NameError` behoben)
  - `python3 -m unittest tests.unit.test_worknotes_sync` → `Ran 19, OK`
  - `python3 -m unittest tests.unit.test_ap4_korbat_worktrees_sessions` → `Ran 27, OK`
  - `env -u GITHUB_AUTO_MERGE python3 -m unittest tests.unit.test_b16_runner_wiring` → `Ran 6, OK`
  - `python3 scripts/check-syntax.py` → Exit 0 (214 Python, 8 Bash, 3 JSON)
  - `python3 scripts/check-no-secrets.py` → Exit 0
  - `python3 scripts/check-import-manifest.py` → Exit 0 (67 Dateien stimmen überein)
  - `env -u GITHUB_AUTO_MERGE python3 scripts/run-tests-parallel.py --dir tests/unit --jobs 4` → 2212 Tests, 91/127 Module bestanden, 36 Module rot (ausschließlich dokumentierte Baseline nach Option A).
- Checks not independently run: all build, test, and other non-Git checks (sowie Git-Befehle, da in dieser Reviewer-Umgebung kein Shell-Werkzeug freigeschaltet ist).
- Important areas inspected:
  - `bin/vibe:580-650`, `bin/vibe:918-944`, `bin/vibe:2568-2585`, `bin/vibe:2735-2761`, `bin/vibe:2961-2986`
  - `bin/vibe_packages.py:74-108`, `bin/vibe_packages.py:188-347`, `bin/vibe_packages.py:401-410`, `bin/vibe_packages.py:658-743`, `bin/vibe_packages.py:1220-1283`, `bin/vibe_packages.py:1396-1494`, `bin/vibe_packages.py:1576-1600`, `bin/vibe_packages.py:1656-1678`, `bin/vibe_packages.py:1887-1904`
  - `bin/vibe_github.py:393-428`, `bin/vibe_github.py:548-618`, `bin/vibe_github.py:1370-1450`
  - `bin/vibe-run.sh:1357-1464`, `bin/vibe-run.sh:1524-1538`, `bin/vibe-run.sh:1662-1703`
  - `scripts/verify.py:1-75`, `scripts/verify.py:391-509`
  - `bin/web/nova-project.js:51-76`, `bin/web/nova-project.js:124-190`, `bin/web/nova-project.js:977-994`, `bin/web/nova-project.js:1038-1047`
  - `bin/web/i18n.js:893-915`, `bin/web/i18n.js:1903-1925`, `bin/web/i18n.js:2071-2084`
  - `bin/web/app.js:633-680`, `bin/web/app.js:1111-1126`
  - `docs/import-manifest.json:1175-1385`, `docs/features/AP5-Korbat.md`, `docs/reviews/AP5-Korbat-test-agent-report.md`
  - `tests/unit/test_ap5_korbat_init_adopt.py`, `tests/unit/test_ap5_korbat_project_env_transport.py`, `tests/unit/test_ap5_korbat_waiting_state.py`, `tests/unit/test_verify_script.py`, `tests/unit/test_ap4_korbat_github.py`, `tests/unit/test_b16_runner_wiring.py`
- Remaining risks:
  - Die in `docs/features/AP5-Korbat.md` §5 offen dokumentierten Umgebungsgrenzen: keine Browser-/Playwright-Ausführung in der Agenten-Umgebung (GUI-Änderungen über Quelltext-/Strukturassertions geprüft) und 4c über protokollierenden `subprocess.run`-Git-Stub statt echten HTTPS-401-Fetch getestet.
  - Das oben als Minor dokumentierte Fehlen des Identitätseintrags `"Wartet auf Merge": "Wartet auf Merge"` in `DICTS.de` (`bin/web/i18n.js`), wodurch die deutsche UI-Einstellung beim Statuslabel auf den englischen Default `"Waiting for merge"` zurückfällt.

Verdict: PASS
Keine Implementierungsänderung ist für den Abschluss dieses Arbeitspakets mehr erforderlich.
