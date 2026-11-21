# AP4-Korbat — Bericht des unabhängigen Test-Agenten

Stand: 2026-11-21
Arbeitspaket: **AP4-Korbat** (Branch `feature/korbat/ap4-korbat`, Ausgangscommit `212d97d`)
Rolle: unabhängiger Test-Agent. Es wurden ausschließlich Tests angelegt/angepasst und ausgeführt; kein Produktionscode, keine Build-/Prüfskripte, keine `SPEC.md`/`docs/features/` und kein Commit.

Quellen der Ableitung (nicht der Implementierungsdiff):

- `TICKETS.md`, Eintrag AP4-Korbat mit allen Untertickets
- `/opt/custom/vibe-dev/workspaces/vibe-audit/docs/features/AP3.md` (§3–§8, insbesondere §4.1–4.6, §5, §6, §7, §8)
- `/opt/custom/vibe-dev/workspaces/vibe-audit/docs/features/AP2.md` (§4, §5.3, §9)
- `SPEC.md`
- verbindliche Design-Entscheidungen des Koordinators (1–17)
- Folgeanweisung des Koordinators vom 2026-11-21 zur Nova-Feature-Frage

## 0. Verbindliche Nutzerentscheidung (Option B), 2026-11-21

Die offene Rückfrage zu den Nova-Feature-Defaults ist über die Dashboard-Rückfrage
`q409cd6f04517` entschieden: **Option B**.

- Der AP22-Default (alle Bereiche standardmäßig ausgeblendet) bleibt unverändert.
- Es werden nur die fehlenden GitHub-Aktionen (`link`, `unlink`, `fetch`) und die
  neue AP4-Funktionalität ergänzt; der Nutzer schaltet Bereiche selbst frei.
- Keine neuen Feature-IDs; die GitHub-Karte bleibt hinter `NV.feature('github')`.
- `tests/browser/test_ap22_settings_ui.py` bleibt unverändert; dafür wurden keine
  Tests geschrieben.

Diese Entscheidung ist in den GUI-Testfällen (unten `test_ap4_korbat_gui.py`)
berücksichtigt.

## 1. Angelegte und angepasste Testdateien

Angelegt:

- `tests/unit/test_ap4_korbat_github.py`
- `tests/unit/test_ap4_korbat_worktrees_sessions.py`
- `tests/unit/test_ap4_korbat_rules.py`
- `tests/unit/test_ap4_korbat_gui.py`

Angepasst (Bestehendes Sollverhalten wurde fortgeschrieben, nicht abgeschwächt):

- `tests/unit/test_b16_runner_wiring.py`
- `tests/unit/test_ap9_runner_wiring.py`

Nicht angepasst (bewusst): `tests/unit/test_ap22_settings_ui.py` (Option B),
`tests/unit/test_b16_git_rules.py` (B16-Anforderungen bleiben in der neuen
Abschlusszeile erhalten), `test_ap19_sessions_*`, `test_f25_session_continue.py`
(lokaler Modus unverändert).

## 2. Testfälle je Unterticket

Jeder Fall trägt im Quelltext einen Docstring mit Vorbedingung, Aktion,
erwartetem Ergebnis und Fehlerfall. Hier die Übersicht; die exakten Namen sind
die `test_*`-Methoden in den genannten Modulen.

### T-G0 — Auto-Merge-Schalter und Runner-Merge-Pfad

Modul `test_ap4_korbat_github.py`, Klasse `AutoMergeConfigTest`,
`PrOnlyRunnerTest`, `AutoMergeRunnerTest`:

| Testfall | Vorbedingung | Aktion | Erwartung / Fehlerfall |
|---|---|---|---|
| `test_missing_key_defaults_auto_merge_off` | project.env ohne `GITHUB_AUTO_MERGE` | `read_config` | `auto_merge is False`; Fehler: fehlender Schlüssel/Wahrwert |
| `test_empty_and_one_values_are_read_binary` | Wert `""` bzw. `"1"` | `read_config` | binär `False`/`True`; Fehler: Enum/Leerwert an |
| `test_status_exposes_auto_merge` | Projekt ohne/mit Schalter | `status()` | `status["auto_merge"]` bool; Fehler: fehlt/String |
| `test_pr_only_stops_without_local_merge_and_keeps_the_worktree` | GitHub aktiv, Schalter aus | Läufer end-to-end | Push+PR, kein lokaler Merge, Worktree bleibt, Registry mit MR-URL, Ticket offen+BLOCKIERT, Log „wartet auf Merge“ + `vibe package close`, kein REST-Merge |
| `test_auto_merge_squashes_the_pr_and_cleans_up` | Schalter `"1"`, REST-Fake kann squash-mergen | Läufer end-to-end | Exit 0, genau ein PUT mit `merge_method=squash`, Integrationsstand auf Fernspitze inkl. Paketänderung, `[x]`-Nachweis, Worktree/Branch/Registry entfernt, Bericht „Geschlossen“ |
| `test_auto_merge_does_not_merge_when_the_gate_is_red` | Schalter `"1"`, Agent ohne Nachweise | Läufer | kein REST-Merge, kein lokaler Merge |

Zusätzlich sichert `test_ap4_korbat_gui.py` die Checkbox in beiden Oberflächen
und die Backend-Persistenz.

### T-G7 — PR-Mergebarkeit vor Abschluss sichern

Modul `test_ap4_korbat_github.py`, Klasse `EnsureMergeableTest`
(Subkommando `vibe_packages.py ensure-mergeable --project … --base origin/main`):

| Testfall | Vorbedingung | Aktion | Erwartung / Fehlerfall |
|---|---|---|---|
| `test_base_already_ancestor_is_ok_without_a_new_commit` | Basis ist Vorfahr | ensure-mergeable | Exit 0, HEAD unverändert |
| `test_advanced_base_is_merged_with_a_merge_commit_and_not_pushed` | origin/main voraus | ensure-mergeable | Exit 0, Merge-Commit mit 2 Eltern, beide Änderungen, kein Push |
| `test_conflict_is_left_in_the_worktree_and_paths_are_reported` | beide Seiten ändern dieselbe Datei | ensure-mergeable | Exit ≠ 0, `.git/MERGE_HEAD` bleibt, `shared.txt` unmerged und in der Ausgabe |
| `test_after_a_repair_the_second_run_is_clean` | Konflikt gelöst und committet | ensure-mergeable erneut | Exit 0, kein MERGE_HEAD, sauberer Baum |

### T-G1 — Lokalen Merge vom Squash-Merge entkoppeln

Abgedeckt durch `PrOnlyRunnerTest` (kein lokaler Merge im Standard),
`AutoMergeRunnerTest` (Merge erst nach REST-Squash, danach `fetch --prune` +
`merge --ff-only`, Notiz-Sync, Cleanup) sowie durch die angepassten
B16-/AP9-Verkabelungstests. Zusätzlich `PackageCloseCliTest` (zweite
Abschlussphase) in `test_ap4_korbat_worktrees_sessions.py`.

### T-W2 — Worktree-Registry und Reconnect

Modul `test_ap4_korbat_worktrees_sessions.py`, Klassen `WorktreeRegistryTest`,
`ReconnectTest`:

| Testfall | Vorbedingung | Aktion | Erwartung / Fehlerfall |
|---|---|---|---|
| `test_register_and_get_roundtrip_with_all_contract_fields` | leere Registry | register/get | alle Felder inkl. realpath, created/updated, pr_url, session, state |
| `test_get_is_keyed_by_project_and_id` | zwei Projekte, gleiche ID | get | richtiger Eintrag, unbekannt None |
| `test_all_filters_by_project_and_returns_all_without_argument` | 3 Einträge/2 Projekte | all(project)/all() | Filter bzw. Gesamtliste |
| `test_register_updates_existing_entry_and_keeps_created` | Eintrag vorhanden | erneut registrieren | ein Eintrag, created bleibt, Werte aktualisiert |
| `test_unregister_removes_only_the_named_entry` | zwei Einträge | unregister | nur der benannte fehlt |
| `test_registry_file_is_written_atomically_next_to_the_lock` | leere Registry | register | `worktrees.json` gültig + `worktrees.lock` |
| `test_valid_registered_worktree_is_reused_instead_of_a_new_one` | gültiger Worktree registriert | Läufer (lokal) | Agent läuft genau dort, keine zweite Arbeitskopie, danach alles entfernt |
| `test_stale_registry_entry_is_discarded_and_a_fresh_worktree_is_used` | Eintrag zeigt auf fehlenden Pfad | Läufer | neuer Worktree, alter Pfad unbenutzt |

### T-W1 — Session-↔-Worktree-Anbindung

Modul `test_ap4_korbat_worktrees_sessions.py`, Klassen
`SessionWorktreeAttachmentTest`, `SessionResumeHintsTest`,
`PackageCloseCliTest` (Session-Vergessen):

| Testfall | Vorbedingung | Aktion | Erwartung / Fehlerfall |
|---|---|---|---|
| `test_observe_persists_worktree_path_package_and_branch` | leeres Register | observe mit 3 Feldern | Felder gespeichert |
| `test_old_entries_without_attachment_remain_readable` | Alteintrag ohne Felder | get/overview | kein Fehler, Anhang leer (Integrationsstand) |
| `test_overview_exposes_the_attachment_fields` | Session mit Anhang | session_overview | Felder im Eintrag |
| `test_stream_cli_passes_the_worktree_options` | JSON-Ereignis auf stdin | `vibe_runs.py stream --session-worktree/--session-package/--session-branch` | Felder im Register |
| `test_resume_exports_the_worktree_package_and_branch` | Session mit Anhang | `vibe sessions resume --session` | Startbefehl exportiert `VIBE_RESUME_WORKTREE/-PACKAGE/-BRANCH` und `VIBE_CONTINUE_SESSION` |
| `test_runner_contains_a_logged_fallback_for_a_closed_package` | Läuferquelltext | Hints prüfen | `VIBE_RESUME_PACKAGE` + protokollierter Rückfall |
| `test_merged_pr_syncs_notes_cleans_up_and_forgets_sessions` | gemergter PR, Registry+Session | `vibe package close` | Exit 0, Fernspitze, `[x]`, Worktree/Branch/Registry/Session weg |

### T-S1 — Session-Zustand persistieren und altersbasiert aufräumen

Modul `test_ap4_korbat_worktrees_sessions.py`, Klassen
`SessionStatePersistTest`, `RunnerSessionPersistTest`:

| Testfall | Vorbedingung | Aktion | Erwartung / Fehlerfall |
|---|---|---|---|
| `test_sessions_finish_persists_the_state_without_a_run_record` | Session mit `run_id`, kein Lauf | `sessions-finish --run-id … --state finished` | overview `finished`/„abgeschlossen“ |
| `test_run_registry_state_wins_over_persisted_state` | persistiert `finished`, Lauf `running` | overview | `running` (Laufregister maßgeblich) |
| `test_aging_prune_removes_old_entries_without_a_worktree` | >30 Tage, kein Anhang + aktueller Eintrag | `sessions-finish` | alter Eintrag entfernt, aktueller bleibt |
| `test_aging_prune_keeps_old_entries_with_an_existing_worktree` | >30 Tage, existierender Worktree | `sessions-finish` | Eintrag bleibt |
| `test_aging_prune_removes_old_entries_whose_worktree_is_gone` | >30 Tage, Worktree fehlt | `sessions-finish` | Eintrag entfernt |
| `test_final_state_survives_a_missing_run_record` | Läufer schließt F1 ab | `runs.json` löschen, overview | `finished` statt `unknown` (Runner persistiert) |

### T-G2 — Pruning-Fetch überall

Modul `test_ap4_korbat_github.py`, Klasse `PruneFetchTest`:

| Testfall | Aktion | Erwartung |
|---|---|---|
| `test_fetch_prunes_deleted_remote_branches` | `fetch()` nach Fern-Löschung | `origin/temp` weg |
| `test_pull_integration_prunes_deleted_remote_branches` | `pull_integration()` | `origin/temp` weg, Branch aktuell |
| `test_integration_state_prunes_deleted_remote_branches` | `integration_state()` | `origin/temp` weg, Zustand ok |
| `test_ensure_mergeable_source_fetches_with_prune` | Quelltext | ensure-mergeable-Fetch enthält `--prune` |

Hinweis: Der enge Refspec `origin/main` prunt keine fremden Refs; deshalb wird
der ensure-mergeable-Fetch als Quelltext-/Strukturassertion geprüft.

### T-G3 — Upstream bei GitHub-Verknüpfung setzen

Modul `test_ap4_korbat_github.py`, Klasse `GithubLinkUpstreamTest`:

- `test_link_sets_upstream_for_branches_with_a_remote_counterpart` — lokale
  Branches mit `origin/<branch>` erhalten den Upstream.
- `test_link_is_not_fatal_when_a_local_branch_has_no_counterpart` — Branch ohne
  Fern-Pendant bricht die Verknüpfung nicht ab und bleibt ohne Upstream.

### T-G4 — Worktree-bewusstes Branch-Löschen

- `WorktreeCheckoutTest.test_checkout_branch_refuses_a_branch_held_by_another_worktree`
  (Modul 1): `checkout_branch` verweigert mit Meldung „Arbeitskopie“, HEAD bleibt.
- `CleanupWiringTest.test_cleanup_consults_worktree_list_before_deleting_the_branch`
  (Modul 2): `vibe-run.sh` wertet `git worktree list --porcelain` aus und nutzt
  `branch -d` mit verständlicher Meldung.

### T-G5 — Branch-Kollision inkl. Worktrees und Remotes

Modul `test_ap4_korbat_worktrees_sessions.py`, Klasse `BranchCollisionTest`:

- `test_remote_only_branch_collision_gets_a_suffix` — nur
  `refs/remotes/origin/feature/test/f1` vorhanden → `…-2`.
- `test_branch_checked_out_in_a_worktree_is_a_collision` — in zweiter
  Arbeitskopie ausgecheckter Branch → freier Name.

### T-I1 — Eine kanonische Regeln-/SPEC-Quelle + Marker-Invariante

Modul `test_ap4_korbat_rules.py`, Klassen `GeneralRulesTest`,
`SpecCanonicalTest`:

- `test_rules_contain_exactly_one_marker_pair`
- `test_completion_line_keeps_the_push_gate_and_names_auto_merge`
- `test_github_module_docstring_describes_auto_merge`
- `test_both_old_strictly_enforced_sections_are_gone`
- `test_exactly_one_canonical_git_section_exists`
- `test_canonical_section_describes_pr_only_and_auto_merge`
- `test_no_agent_side_squash_merge_or_force_delete_remains`
- `test_conflict_repair_wording_is_documented`
- `test_out_of_scope_line_names_approval_and_auto_merge`

### T-I2 — „Laufende Instanz nicht verändern“ entduplizieren

- `test_rules_contain_exactly_one_running_instance_block`
- `test_every_template_contains_the_rules_exactly_once` (Vorkommen + Bytengleichheit)

### T-S1/GUI — Oberflächen

Modul `test_ap4_korbat_gui.py` (siehe Abschnitt 3).

## 3. GUI-Testfälle (Punkt 17, ohne 17(e))

Datei `tests/unit/test_ap4_korbat_gui.py`; Playwright steht nicht zur
Verfügung, daher Quelltext-/Strukturassertions auf die JS-Dateien plus echte
API-Aufrufe gegen den isolierten `vibe-web`-Server.

- `ClassicSurfaceTest.test_github_body_has_an_auto_merge_checkbox_in_the_settings_payload`
- `ClassicSurfaceTest.test_github_hint_describes_pr_only_default_and_auto_merge`
- `ClassicSurfaceTest.test_session_rows_show_worktree_and_package_attachment`
- `NovaSurfaceTest.test_nova_github_section_has_auto_merge_checkbox`
- `NovaSurfaceTest.test_nova_github_card_has_link_unlink_and_fetch_actions`
  (link inkl. `url`, unlink, fetch; Labels „Mit GitHub verknüpfen“,
  „Verknüpfung lösen“, „Abrufen“)
- `NovaSurfaceTest.test_nova_session_rows_show_worktree_and_package_attachment`
- `NovaSurfaceTest.test_nova_work_tab_has_a_package_close_action`
- `WebBackendTextTest.test_settings_handler_writes_github_auto_merge`
- `WebBackendTextTest.test_package_endpoint_is_known`
- `WebApiBehaviourTest.test_settings_persist_auto_merge_on_and_off`
- `WebApiBehaviourTest.test_sessions_api_returns_the_worktree_attachment`
- `WebApiBehaviourTest.test_package_close_without_github_link_reports_a_clear_error`

Feature-Gatter: Die neuen Aktionen liegen in `nvpGithubSection` bzw. den
bestehenden Bereichen; es wurden keine neuen Feature-IDs und keine
Default-Änderungen verlangt/getestet (Option B).

## 4. Rotphase auf dem unveränderten Stand `212d97d`

Befehle (jeweils aus dem Repository-Wurzelverzeichnis):

```bash
python3 -m unittest tests.unit.test_ap4_korbat_github -v
python3 -m unittest tests.unit.test_ap4_korbat_worktrees_sessions -v
python3 -m unittest tests.unit.test_ap4_korbat_rules -v
python3 -m unittest tests.unit.test_ap4_korbat_gui -v
python3 -m unittest tests.unit.test_b16_runner_wiring -v
python3 -m unittest tests.unit.test_ap9_runner_wiring -v
```

Beobachtete Ergebnisse (echte Läufe, Ausgangsstand ohne AP4-Implementierung):

| Modul | Ergebnis | Bewertung |
|---|---|---|
| `test_ap4_korbat_github` | `Ran 17 tests … FAILED (failures=15, errors=2)`, Exit 1 | Alle 17 rot. 2 Errors sind `KeyError: 'auto_merge'` in den beiden Unwerten; die übrigen Fehlschläge sind fehlendes Verhalten (Subkommando `ensure-mergeable` unbekannt, kein `--prune`, kein Upstream, Worktree-Meldung, kein REST-Merge, lokaler Merge im PR-only-Pfad) |
| `test_ap4_korbat_worktrees_sessions` | `Ran 26 tests … FAILED (failures=9, errors=15)`, Exit 1 | 24 rot; 2 grün, weil sie Bestandsverhalten sichern: `test_branch_checked_out_in_a_worktree_is_a_collision` (lokale Ref-Prüfung existiert bereits) und `test_old_entries_without_attachment_remain_readable` (zusätzliche Felder stören den Alteintrag nicht). 15 Errors = fehlende `WorktreeRegistry` bzw. `observe`-Felder |
| `test_ap4_korbat_rules` | `Ran 11 tests … FAILED (failures=14)`, Exit 1 | 10 Methoden rot (5 Vorlagen-Subtests zählen einzeln); grün ist nur `test_rules_contain_exactly_one_marker_pair` (Markerpaar ist bereits einfach) |
| `test_ap4_korbat_gui` | `Ran 12 tests … FAILED (failures=11)`, Exit 1 | 11 rot; grün ist `test_sessions_api_returns_the_worktree_attachment`, weil `session_overview` unbekannte Felder bereits durchreicht |
| `test_b16_runner_wiring` (angepasst) | `Ran 6 tests … FAILED (failures=1)`, Exit 1 | Nur der fortgeschriebene PR-only-Fall rot („wartet auf Merge“ fehlt, alter lokaler Merge); die übrigen 5 B16-Fälle bleiben grün |
| `test_ap9_runner_wiring` (angepasst) | `Ran 3 tests … FAILED (failures=1)`, Exit 1 | Nur der fortgeschriebene Reihenfolge-Fall rot (Paketbranch wird im alten Stand weggeräumt); die übrigen 2 grün |

Auszüge der Rotphase (wörtlich, gekürzt):

```text
ERROR: test_empty_and_one_values_are_read_binary ... KeyError: 'auto_merge'
ERROR: test_register_and_get_roundtrip_with_all_contract_fields ...
       AttributeError: module 'vibe_runs_ap4_under_test' has no attribute 'WorktreeRegistry'
FAIL: test_fetch_prunes_deleted_remote_branches ...
       AssertionError: True is not false : fetch hat veraltete Fern-Referenzen nicht entfernt
FAIL: test_checkout_branch_refuses_a_branch_held_by_another_worktree ...
       AssertionError: 'Arbeitskopie' not found in "fatal: 'feature/held' is already used by worktree at ..."
FAIL: test_sessions_finish_persists_the_state_without_a_run_record ...
       (sessions-finish ist unbekannt; Zustand bleibt unknown)
FAIL: test_final_state_survives_a_missing_run_record ...
       AssertionError: 'finished' != 'unknown'
FAIL: test_both_old_strictly_enforced_sections_are_gone ...
       AssertionError: '## Git Workflow & Branch Rules (Strictly Enforced)' unexpectedly found
```

Nicht als Erfolg gewertet: Ein nicht ausgeführter Test zählt nicht. Alle oben
genannten Fälle wurden tatsächlich ausgeführt.

## 5. Anpassungen an bestehenden Tests (altes vs. neues Sollverhalten)

1. `tests/unit/test_b16_runner_wiring.py`
   - Alt: `SuccessfulClosureTest` erwartete nach erfolgreichem
     `github-complete` sofortigen lokalen Merge, Cleanup und Bericht
     „Geschlossen: F1“.
   - Neu: `PrOnlyClosureTest` prüft den AP4-Standard: Push und Merge-Request
     bleiben Pflicht, aber kein lokaler Merge; Arbeitskopie bleibt registriert,
     Ticket bleibt offen mit Blockievermerk, Protokoll nennt „wartet auf Merge“
     und `vibe package close`. Der Auto-Merge-Erfolgspfad (Bericht
     „Geschlossen“, Cleanup, Squash) wird in `test_ap4_korbat_github.py`
     geprüft.
   - Begründung: AP3 §4.4/§5 und Design-Entscheidungen 4–5 machen PR-only zum
     Standard; ein lokaler Merge wäre eine Regression.
   - Der Modul-Docstring wurde entsprechend präzisiert.

2. `tests/unit/test_ap9_runner_wiring.py`
   - Alt: `test_a_successful_pull_updates_the_base_before_the_worktree`
     verlangte Exit 0 und prüfte die Paketcommits auf `main` (lokaler Merge).
   - Neu: Die Reihenfolge wird auf dem verbleibenden Paketbranch
     `feature/test/f1` geprüft; der lokale Merge wird nicht mehr erwartet.
   - Begründung: gleiche AP4-Umstellung; die eigentliche AP9-Aussage
     (Pull vor Paketbase) bleibt unverändert und wird weiter geprüft.
   - Modul-Docstring präzisiert.

Keine Assertion wurde gelöscht oder abgeschwächt; keine bestehenden Tests
wurden entfernt. `test_b16_git_rules.py` blieb unverändert, weil die neue
Abschlusszeile „Push“, „Merge-Request“ und „aktivier“ weiterhin enthält.

## 6. Grenzen und verbleibende Lücken

- **Kein Browser/Playwright**: GUI-Fälle sind Quelltext-/Strukturassertions plus
  echte API-Aufrufe gegen den isolierten `vibe-web`-Server. Keine visuelle oder
  interaktive Abnahme.
- **Kein echtes GitHub**: REST läuft ausschließlich gegen lokale Fakes auf
  `127.0.0.1`; echte Branch-Protection, Merge-Queue oder API-Versionsdetails
  sind nicht abgedeckt.
- **ensure-mergeable-Pruning** ist nur als Quelltextassertion prüfbar, weil ein
  enges Refspec-basiertes `git fetch --prune origin main` fremde Fern-Refs
  nicht entfernt (verifiziert).
- **Altersaufräumen**: Als Auslöser wird der von der Spezifikation genannte
  Laufabschluss (`sessions-finish`) angenommen. Falls die Implementierung ein
  separates Subkommando wählt, sind die Fälle entsprechend anzupassen.
- **Zweiter Konflikt → `git merge --abort` + Paket blockiert** (T-G7,
  Design-Entscheidung 2) ist nicht end-to-end getestet; der Einzelaufruf
  `ensure-mergeable` und der Reparaturfolgeaufruf sind abgedeckt. Die
  begrenzte Reparaturrunde im Auto-Merge (Design-Entscheidung 4) ist ebenfalls
  nicht end-to-end simuliert.
- **Worktree-Registry-CLI** (`worktree-add/get/remove` oder äquivalent) wird
  über die Klassen-API und das Läuferverhalten geprüft, nicht über konkrete
  Subkommandonamen.
- **`sessions-finish`-Feldname** wird nicht direkt geprüft; die Fälle prüfen
  das beobachtbare Ergebnis über `session_overview`.
- Der `test_sessions_api_returns_the_worktree_attachment` und der lokale
  Worktree-Kollisionsfall waren bereits vor der Implementierung grün
  (Bestandsverhalten); sie sind als Regressionsschutz behalten.

## 7. Testbefehle (für Coding- und Review-Agent)

```bash
python3 -m unittest tests.unit.test_ap4_korbat_github -v
python3 -m unittest tests.unit.test_ap4_korbat_worktrees_sessions -v
python3 -m unittest tests.unit.test_ap4_korbat_rules -v
python3 -m unittest tests.unit.test_ap4_korbat_gui -v
python3 -m unittest tests.unit.test_b16_runner_wiring -v
python3 -m unittest tests.unit.test_ap9_runner_wiring -v
```

Für den Gesamtnachweis vor der Abnahme bleibt die Projektvorgabe maßgeblich
(`bash scripts/verify.sh package` bzw. `full`); der Test-Agent hat in der
Rotphase bewusst keine Vollsuite gestartet (Effizienzvorgabe).

## 8. Setup-Defekt-Korrektur (2026-11-21)

Auf Hinweis des Koordinators wurde ein Defekt im Testaufbau korrigiert. Es
handelt sich **nicht** um eine Spezifikationsänderung; Produktionsdateien
wurden nicht angefasst, und kein anderer Testfall wurde geändert.

- **Datei:** `tests/unit/test_ap4_korbat_github.py`
- **Fall:** `EnsureMergeableTest.test_advanced_base_is_merged_with_a_merge_commit_and_not_pushed`
- **Defekt:** Die Fixture `feature_project("advanced")` (nicht-konfliktfrei)
  legt auf der Feature-Seite `feature.txt` an und schiebt auf der Fern-Seite
  `remote.txt` mit „remote\n“. `shared.txt` bleibt auf beiden Seiten
  unverändert („base\n“). Die Assertion prüfte fälschlich
  `shared.txt == "remote\n"` und widersprach damit der eigenen Fixture.
- **Korrektur:** Geprüft wird jetzt die tatsächlich gemergte Fernänderung:
  `remote.txt == "remote\n"`. Zusätzlich wird gesichert, dass die unveränderte
  Datei `shared.txt == "base\n"` bleibt, `feature.txt` vorhanden ist und kein
  Push erfolgt. Das Fehlerfall-Kriterium „fehlende Änderung“ bleibt erhalten.
- **Begründung:** AP3 §4.1/§4.2 verlangt, dass der Merge die Fernänderung in
  den Paketbranch bringt, ohne zu pushen. Die bisherige Assertion prüfte eine
  Datei, die in diesem Szenario bewusst unverändert bleibt.
- **Nachlauf (Implementierung lief parallel):**
  `python3 -m unittest tests.unit.test_ap4_korbat_github -v`
  → Exit 1, `Ran 17 tests`, `FAILED (failures=2)`.
  Grün ist jetzt u. a. der korrigierte ensure-mergeable-Fall. Rot bleiben nur
  `AutoMergeRunnerTest.test_auto_merge_squashes_the_pr_and_cleans_up` und
  `PrOnlyRunnerTest.test_pr_only_stops_without_local_merge_and_keeps_the_worktree`.
  Beide scheitern am noch nicht umgestellten Abschluss der Läuferfolge
  (alter lokaler Merge/Cleanup, kein REST-PUT, kein „vibe package close“ im
  Protokoll) — also an der laufenden Implementierung, nicht am Testaufbau.
  Die ursprüngliche Rotphase in Abschnitt 4 bleibt als Nachweis des
  Ausgangsstands unverändert dokumentiert.

## 9. Weitere Setup-Defekt-Korrekturen (2026-11-21)

Zwei weitere reine Testaufbau-Defekte wurden auf Hinweis des Koordinators
korrigiert. Es gab keine Spezifikationsänderung; Produktionsdateien wurden
nicht angefasst und kein anderer Testfall wurde verändert.

### 9.1 Defekt A — `RunnerFixtureMixin.worktrees` delegierte ins Leere

- **Datei/Fall:** `tests/unit/test_ap4_korbat_github.py`,
  `RunnerFixtureMixin.worktrees` (genutzt von
  `PrOnlyRunnerTest` und `AutoMergeRunnerTest`).
- **Defekt:** `worktrees()` rief `self.fixture.worktrees(self)` auf, aber
  `_fixture()` liefert `AP9WiringFixture`, die keine Methode `worktrees`
  besitzt. Nur `B16WiringFixture` hatte sie. Folge:
  `AttributeError: type object 'AP9WiringFixture' has no attribute
  'worktrees'` — obwohl das Verhalten der Implementierung korrekt war.
- **Korrektur (Variante i):** Die generische `worktrees`-Hilfsmethode wurde
  in `AP9WiringFixture` (`tests/unit/test_ap9_runner_wiring.py`) aufgenommen;
  die nun redundante Definition in `B16WiringFixture`
  (`tests/unit/test_b16_runner_wiring.py`) wurde entfernt (B16 erbt).
- **Begründung:** Eine gemeinsame Fixture soll ihre Hilfsmethoden selbst
  bereitstellen; das vermeidet doppelte Wahrheiten und hält beide
  Läufer-Testmodule konsistent.
- **Nachlauf:** siehe 9.3 (beide Module grün).

### 9.2 Defekt B — `PackageCloseCliTest.env` ignorierte `api`/`enabled`

- **Datei/Fälle:** `tests/unit/test_ap4_korbat_worktrees_sessions.py`,
  `PackageCloseCliTest.env` sowie die drei `vibe package close`-Fälle.
- **Defekt:** `env(api=…, enabled=…)` nahm die Parameter an, verwendete sie
  aber nie. `GITHUB_API`/`GITHUB_ENABLED` gelangten weder in die
  Prozessumgebung noch in `.vibe/project.env`. Damit hätte
  `vibe package close` die echte `https://api.github.com` kontaktiert — ein
  Verstoß gegen „keine Netzaufrufe in Tests“, und der gemergte Fall hätte
  den Fake nicht geprüft.
- **Korrektur:** Neue Hilfsmethode `write_github_env(api, enabled)` schreibt
  `GITHUB_ENABLED="1"`/`""` und bei Bedarf `GITHUB_API="…"` in die
  Projektdatei; `env()` ruft sie mit den übergebenen Werten auf,
  `_build_project()` nutzt dieselbe Methode (keine Doppelwartung). Der
  dritte Fall nutzt nun `self.close("", enabled=False)` statt eines
  manuellen Dateischreibens. Der Erfolgsfall prüft zusätzlich
  `server.requests` nicht leer, damit der Fake nachweislich getroffen wurde.
- **Begründung:** Die Werte müssen dort ankommen, wo der Befehl sie liest
  (Projektdatei), nicht nur als ungenutzte Signatur. Das schärft die
  bestehende Spezifikationsaussage (Close prüft den PR über REST) und
  verhindert echte Netzaufrufe.
- **Querprüfung:** Das Modul wurde nach weiteren ungenutzten Parametern
  dieser Art durchsucht (`env`-Helfer, `fresh_env`, `close`, `register`,
  `observe_session`, Fake-Server). Weitere Fundstellen gab es nicht; die
  übrigen Parameter werden verwendet.

### 9.3 Nachlauf nach beiden Korrekturen (echte Ergebnisse)

```text
python3 -m unittest tests.unit.test_ap4_korbat_github \
    tests.unit.test_ap4_korbat_worktrees_sessions -v
→ Ran 43 tests in 38.823s, OK (Exit 0)

python3 -m unittest tests.unit.test_b16_runner_wiring \
    tests.unit.test_ap9_runner_wiring -v
→ Ran 9 tests in 41.205s, OK (Exit 0)
```

Damit sind beide neuen Module vollständig grün, und die gemeinsame
Läufer-Fixture bleibt in B16 und AP9 grün.

## 10. Regressionsschutz nach Review Runde 1 (2026-11-21)

Der unabhängige Review `docs/reviews/AP4-Korbat-review-1.md` gab
`Verdict: PASS` mit drei Minor-Befunden. Für alle drei wurde in den eigenen
Testmodulen Regressionsschutz ergänzt. Die Fixes des Coding-Agenten liefen
parallel; der IST-Zustand vor dem Fix war bei der Prüfung noch sichtbar
(Handler reichte nur `continue_session` durch, `cmd_run` exportierte die
Resume-Werte unquotiert, `cmd_github status` hatte keine Auto-Merge-Zeile).
Beim ersten Testlauf waren die Fixes bereits eingespielt; alle neuen Fälle
waren grün.

### 10.1 Befund 1 — `/api/sessions action="continue"` reicht das Resume-Paket durch

- **Datei/Klasse:** `tests/unit/test_ap4_korbat_gui.py`,
  `SessionsContinueResumePackageTest` (echter Web-Handler mit
  aufzeichnender tmux-Attrappe, Muster `Ap19SessionsApiFixture`).
- **Fall 1a:** `test_continue_exports_the_resume_package_and_worktree`
  - Vorbedingung: Session-Register-Eintrag mit `package_id=F1`,
    `worktree_path` und `branch=feature/test/f1`.
  - Aktion: `POST /api/sessions` mit `action="continue"` und der Session.
  - Erwartung: Der gestartete `vibe.cmd_run`-Aufruf exportiert
    `VIBE_CONTINUE_SESSION` **und** `VIBE_RESUME_PACKAGE`,
    `VIBE_RESUME_WORKTREE`, `VIBE_RESUME_BRANCH` mit den Registerwerten.
  - Fehlerfall: Handler lässt das Resume-Paket weg; Agent landet im falschen
    Baum.
- **Fall 1b:** `test_continue_without_attachment_stays_plain_continue`
  - Vorbedingung: Session ohne `package_id`/`worktree_path` (Alteintrag).
  - Aktion: derselbe POST.
  - Erwartung: nur `VIBE_CONTINUE_SESSION`, keine Resume-Hinweise.
  - Fehlerfall: leere Anhänge werden als Resume-Paket exportiert.

### 10.2 Befund 2 — `shlex.quote` für Resume-Hinweise

- **Datei/Klasse:** `tests/unit/test_ap4_korbat_worktrees_sessions.py`,
  `SessionResumeHintsTest`.
- **Fall:** `test_resume_hints_are_quoted_for_the_shell`
  - Vorbedingung: Session mit `worktree_path` „…/x y“ (Leerzeichen) und
    `branch=feature/test/f1;echo PWNED` (Semikolon/Leerzeichen);
    `vibe sessions resume` ruft `cmd_run(..., resume_worktree=…,
    resume_branch=…)` auf.
  - Aktion: Resume über die echte CLI mit aufzeichnender tmux-Attrappe.
  - Erwartung: Der tmux-Innenteil enthält beide Werte in
    `shlex.quote`-Form; der ungeschützte String
    `VIBE_RESUME_BRANCH=<wert>;` kommt nicht vor. Der bestehende
    `exports`-Parser bleibt für einfache Werte nutzbar (`F1`).
  - Fehlerfall: Unquotierte Werte zerreißen den Startbefehl oder führen
    Fremdkommandos aus.

### 10.3 Befund 3 — CLI-Status nennt Auto-Merge

- **Datei/Klasse:** `tests/unit/test_ap4_korbat_github.py`,
  `GithubCliStatusTest` (`cmd_github(..., out=StringIO)`).
- **Fall 3a:** `test_status_names_auto_merge_ja_when_enabled`
  - Vorbedingung: `GITHUB_AUTO_MERGE="1"`.
  - Aktion: `vibe github proj status`.
  - Erwartung: Zeile „Auto-Merge:“ mit „ja“.
- **Fall 3b:** `test_status_names_auto_merge_nein_when_disabled`
  - Vorbedingung: `GITHUB_AUTO_MERGE=""` (Standard aus).
  - Aktion/Erwartung: dieselbe Zeile mit „nein“.
- Fehlerfall: Status verschweigt den Schalter oder zeigt „aus“ als „an“.

### 10.4 Echte Nachlauf-Ergebnisse

```text
python3 -m unittest tests.unit.test_ap4_korbat_gui \
    tests.unit.test_ap4_korbat_worktrees_sessions -v
→ Ran 41 tests in 14.887s, OK (Exit 0)

python3 -m unittest tests.unit.test_ap4_korbat_github -v
→ Ran 19 tests in 29.152s, OK (Exit 0)
```

Damit sind die drei Review-Befunde durch unabhängige Tests abgedeckt; die
AP4-Testmodule umfassen jetzt 71 Fälle (19 GitHub, 27 Worktrees/Sessions,
14 GUI, 11 Regeln). Keine anderen Testfälle wurden geändert.



