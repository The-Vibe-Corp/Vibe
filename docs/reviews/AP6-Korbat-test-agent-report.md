# AP6-Korbat — Testbericht des unabhängigen Test-Agenten

Stand: 2026-11-22
Repository: `/var/log/custom/vibe-dev/worktrees/vibe-AP6-Korbat-cpr9Pv`
Branch: `feature/korbat/ap6-korbat`
Ausgangscommit: `4db1b78`
Grundlage: Arbeitspaket AP6-Korbat (`TICKETS.md`), Audit `docs/features/AP10.md`,
die Testaufträge A/B/C/D/E/G/H/I aus der Koordination sowie Review-Runde 1
(`docs/reviews/AP6-Korbat-review-1.md`, Befunde J1/J2). Die Fälle wurden aus
Arbeitspaket, Spezifikation und beobachtetem Verhalten abgeleitet, nicht aus
einem Implementierungsdiff.

Es wurden ausschließlich Testdateien (und dieser Bericht) verändert. Keine
Produktionsdatei, kein Prüfskript und keine Konfiguration wurde angefasst;
nichts wurde gestaged, committet, gebrancht, gemerged oder gepusht.

## Umgebung der Nachweise

Alle Läufe fanden im **kontaminierten Runner-Environment** statt (so
vorgefunden, kein `env -i`):

```
VIBE_UI_BIND=<LAN-IP>
VIBE_UI_PORT=3001
GITHUB_AUTO_MERGE=1
HOME=/opt/custom/vibe-dev        (persönliche config.json mit profiles.prod.runtime)
VIBE_OPENCODE_PORT=4096, VIBE_MODEL=opencode-go/glm-5.3-flash, VIBE_MANAGED=run
```

Das Arbeitsverzeichnis `/var/log/custom/vibe-dev` ist read-only (EROFS).
`bubblewrap` ist installiert, aber unprivilegierte Benutzernamensräume sind in
dieser Gesamtumgebung nicht verfügbar („No permissions to create a new
namespace“); echte bwrap-Läufe können hier nur scheitern. Die
Verschachtelungs-Skips wurden deshalb über den Marker `VIBE_SANDBOX_ACTIVE=1`
verifiziert.

Einzellauf je Modul: `python3 -m unittest tests.unit.<modul> -v` im
Arbeitskopie-Verzeichnis. Vollläufe sind Sache des Runners und wurden nicht
ausgeführt.

## Geänderte Testdateien

| Datei | Status | Inhalt |
|---|---|---|
| `tests/unit/env_support.py` | neu | `INHERITED_INSTANCE_KEYS`, `isolated_environ`, `isolated_process_environment`, `sandbox_nested`, `skip_if_sandbox_nested` |
| `tests/unit/test_web_api_security.py` | angepasst | Server-Env isoliert (2 Fixtures) |
| `tests/unit/test_project_write_dirs.py` | angepasst | Server-Env isoliert |
| `tests/unit/test_lifecycle.py` | angepasst | Lauf-Env isoliert |
| `tests/unit/test_pause_after_package.py` | angepasst | Server-Env isoliert |
| `tests/unit/test_costs.py` | angepasst | Server-Env isoliert |
| `tests/unit/test_b8_no_remote_block.py` | angepasst | Server-Env isoliert |
| `tests/unit/test_fritz_reconnect.py` | angepasst | Server-Env isoliert |
| `tests/unit/test_storage.py` | angepasst | Server-Env isoliert |
| `tests/unit/test_feedback_capture.py` | angepasst | `load_cli` + Server-Env isoliert; Label-Regex an AP21-i18n |
| `tests/unit/test_feedback_completed.py` | angepasst | `load_cli` + Server-Env isoliert |
| `tests/unit/test_feedback_edit_delete.py` | angepasst | `load_cli` + Server-Env isoliert |
| `tests/unit/test_ticket_feedback_processing.py` | angepasst | `load_cli` + Server-Env isoliert; AP3-Präzedenz; offenes V-1-Ticket |
| `tests/unit/test_ap4_korbat_github.py` | angepasst | `GITHUB_AUTO_MERGE` isoliert (Test-Setup und Läufer-Env) |
| `tests/unit/test_ap06_github.py` | angepasst | Push-Fehlerassertion robust + `LC_ALL=C` |
| `tests/unit/test_feedback_entries.py` | angepasst | Fixturedaten statt lokalem Ledger, neuer Blockregel-Fall |
| `tests/unit/test_install_lifecycle.py` | angepasst | Installationsziel `_toolchain`; Rollback/Uninstall/Verify am Installationsort |
| `tests/unit/test_setup_vibe.py` | angepasst | Installationsziel/Launcher/`register_projects(workspace, install)` |
| `tests/unit/test_ap03_agent_management.py` | angepasst | `ensure_test_agent`-Patch entfernt |
| `tests/unit/test_b3_password_auto_setup.py` | angepasst | `ensure_test_agent`-Patch entfernt |
| `tests/unit/test_f22_preflight_assist.py` | angepasst | `ensure_test_agent`-Patch entfernt |
| `tests/unit/test_f27_keep_changes.py` | angepasst | `ensure_test_agent`-Stub entfernt |
| `tests/unit/test_project_agents.py` | angepasst | `VIBE_MODEL` isoliert; zwei obsolete Test-Agent-Fälle ersetzt |
| `tests/unit/test_v025_agent_start_repair.py` | angepasst | `ensure_test_agent`-Patch entfernt |
| `tests/unit/test_v026_run_isolation.py` | angepasst | `ensure_test_agent`-Stub entfernt; `running_installation(self.runtime)` |
| `tests/unit/test_sandbox.py` | angepasst | API-Env isoliert; bwrap-Skips; `openwrt` aus `TOOL_DEFAULTS` |
| `tests/unit/test_b4_pi_agent_dir.py` | angepasst | bwrap-Skip |
| `tests/unit/test_b5_sandbox.py` | angepasst | bwrap-Skips |
| `tests/unit/test_b13_private_server_runner.py` | angepasst | bwrap-Skip |
| `tests/unit/test_project_guide.py` | angepasst | Server-Env isoliert; bwrap-Skips |
| `tests/unit/test_b17_sandbox_argv.py` | angepasst (J2) | persistenter Vertragstest für `VIBE_SANDBOX_ACTIVE` |
| `tests/browser/test_b18_harness_ui.py` | angepasst | persönlicher Home-Pfad im Docstring portabel |

Damit sind 30 `tests/unit`-Module, `env_support.py` und die B18-Stelle
geändert (29 Module aus den Aufträgen A–I plus `test_b17_sandbox_argv.py` aus J2).

---

## 1) Baseline am Ausgangscommit 4db1b78

Beobachtet mit den oben genannten Einzelbefehlen im kontaminierten Env
(Logs: `/tmp/opencode/vibe-sandbox/vibe-c7188db792/tmp/ap6base*`).

| Modul | Rote Fälle (Anzahl) | Ursache |
|---|---|---|
| `test_web_api_security` | 5 setUpClass-Errors | geerbtes `VIBE_UI_BIND`; Server band an die LAN-Adresse, Test fragte 127.0.0.1 |
| `test_project_write_dirs` | 1 setUpClass-Error | dito |
| `test_pause_after_package` | 1 setUpClass-Error | dito |
| `test_b8_no_remote_block` | 1 setUpClass-Error | dito |
| `test_fritz_reconnect` | 1 setUpClass-Error | dito |
| `test_storage` | 1 setUpClass-Error | dito |
| `test_lifecycle` | 8 Failures | dito (Dashboard-/Port-Lebenszyklus) |
| `test_costs` | 7 Failures | dito |
| `test_sandbox` | 12 Failures, 1 Error | echte bwrap-Läufe + `TOOL_DEFAULTS["openwrt"]` |
| `test_feedback_capture` | 1 setUpClass-Error | EROFS `/var/log/custom/vibe-dev/.vibe-*.tmp` |
| `test_feedback_completed` | 1 setUpClass-Error | dito |
| `test_feedback_edit_delete` | 1 setUpClass-Error | dito |
| `test_ticket_feedback_processing` | 1 Failure, 2 Errors | dito + vor-AP3-Präzedenz + `KeyError 'V-1'` |
| `test_ap4_korbat_github` | 1 Failure | geerbtes `GITHUB_AUTO_MERGE=1` → ungewollter Auto-Merge |
| `test_ap06_github` | 1 Failure | Assertion auf Substring „Remote“, Git meldet englisch |
| `test_install_lifecycle` | 7 Failures, 28 Errors | `install_program_files`/`uninstall`/`rollback` am falschen Ziel |
| `test_setup_vibe` | 6 Failures, 4 Errors | Installationsziel, Launcher, `register_projects`-Signatur |
| `test_ap03_agent_management` | 5 Errors | Patch auf entferntem `ensure_test_agent` |
| `test_b3_password_auto_setup` | 3 Errors | dito |
| `test_f22_preflight_assist` | 1 Error | dito |
| `test_f27_keep_changes` | 5 Errors, 1 Failure | dito + Merge-/Keep-Changes-Konflikt |
| `test_project_agents` | 2 Failures, 1 Error | dito + `VIBE_MODEL`-Leck |
| `test_v025_agent_start_repair` | 9 Errors | dito |
| `test_v026_run_isolation` | 2 Errors, 1 Failure | dito + falsches Logverzeichnis bei `running_installation` |

`test_feedback_entries` war laut Audit (AP10) am Ausgangscommit rot
(`StopIteration`, lokale `FEEDBACK.md` ohne F7-Block). Diesen Rotlauf habe ich
**nicht selbst** ausgeführt; die Ursache habe ich am Quelltext der alten
Fassung und am lokalen Ledger-Zustand nachvollzogen. Alle anderen Rotstände
wurden von mir tatsächlich beobachtet.

Der EROFS-Pfad wurde konkret diagnostiziert: geerbtes
`HOME=/opt/custom/vibe-dev` → `vibe_paths.load_config` liest die persönliche
`config.json` (nur Schlüssel geprüft, keine Werte) mit
`profiles.prod.runtime=/var/log/custom/vibe-dev`; da die Feedback-Tests kein
`VIBE_RUNTIME` setzten, gewann die Config vor dem Default, und
`vibe_storage._stage_bytes` legte die Laufzeitkennung dort an
(Stacktrace bis `bin/vibe_storage.py:248`).

---

## 2) Außergewöhnliche Befunde und Einordnung

### F27: Merge-/Keep-Changes-Konflikt (produktseitig behoben)

Zwischenzeitlich scheiterte
`RunnerKeepChangesTest.test_keep_changes_starts_a_package_and_preserves_changes`:

1. zuerst an `bin/vibe-run.sh` `merge_package` mit
   `git merge --ff-only` → „Your local changes … would be overwritten“
   (uncommittete `AGENTS.md`), danach
2. an der damaligen Verwurf-Logik, die die uncommittete `AGENTS.md` beim Merge
   verwarf (`WARNUNG: Uncommittete Änderungen an Arbeitsnotizen werden für den
   Merge verworfen: AGENTS.md`).

Das Szenario wurde produktseitig (Variante A: `copy_work_notes` überspringt
dirty `AGENTS.md`, `merge_package` verwirft nur die Schnittmenge
`git diff HEAD..$BRANCH` ∩ dirty) behoben. **Letzter von mir ausgeführter
Lauf: `Ran 14 tests … OK`** (siehe Grünphase). Die Assertions des F27-Tests
wurden nicht verändert; lediglich der obsolete `ensure_test_agent`-Stub
entfernt.

### `test_release` und `test_ap12_github_readiness`

Beide bleiben rot, beide außerhalb meines Änderungsumfangs:

* `test_release.…no_personal_home_paths…` meldet
  `docs/reviews/AP6-Korbat-review-1.md:22` (der Review-Text nennt den alten
  absoluten Home-Pfad wörtlich). Fremdes Review-Artefakt; ich habe es nicht
  verändert. Neutralisierung durch den Verfasser/Koordinator nötig.
* `test_ap12_github_readiness.test_local_test_agent_preserved_when_environment_established`
  erwartet `.opencode/agents/test-agent.md`, obwohl `templates/common/.opencode`
  seit `35233ff` nicht existiert. Nach Nutzerentscheidung A (kein Restore) ist
  die Testprämisse veraltet; als offene Vorlagenfrage klassifiziert, nicht
  testseitig abgeschwächt.

Die vier aus AP10 §4.2 bekannten Vorabstände (`test_ap12_github_readiness`,
`test_ap8_github_checkout`, `test_project_management`, `test_rebuild_profile`)
sind nicht Teil dieses Pakets.

---

## 3) Testfälle je Auftragsteil

### A — T-BR1: Test-Isolation vervollständigen

Die Änderungen sind Harness-/Fixture-Isolation, keine neuen Testnamen. Je
Modul gilt: Vorbedingung = kontaminiertes Runner-Env; Aktion = Modul
ausführen; Erwartetes Ergebnis = eigene Prozesse binden auf 127.0.0.1 und
schreiben ausschließlich in temporäre Pfade.

| Modul | Isolationsänderung | Betroffene Fälle | Erwartetes Ergebnis |
|---|---|---|---|
| `test_web_api_security` | `env_support.isolated_environ()` in beiden Server-Fixtures | gesamte `WebApiFixture`-Klassen + `LoopbackBindTest` | Health/Token/Logs erreichbar; 0.0.0.0-Fall bindet weiterhin ausdrücklich 0.0.0.0 |
| `test_project_write_dirs` | dito | `WriteDirsApiFixture` | API-Schreibverzeichnisse prüfbar |
| `test_pause_after_package` | dito | `PauseApiTest` | Pause-API erreichbar |
| `test_costs` | dito | `CostsApiTest` | Kosten-API erreichbar |
| `test_b8_no_remote_block` | dito (statt manueller Ausschlussliste) | `ApiProjectBlockingTest` | Blockade ohne Remote prüfbar |
| `test_fritz_reconnect` | dito | `FritzApiTest` | Reconnect-API erreichbar |
| `test_storage` | dito | `AgentApiConflictTest` | Konflikt-API erreichbar |
| `test_lifecycle` | `self.env` aus `isolated_environ()` | `DashboardLifecycleTest`, `PortTest` | Dashboard-Sessions/Ports laufen auf 127.0.0.1 |
| `test_feedback_capture/completed/edit_delete` | `load_cli` mit isoliertem `HOME`/`VIBE_RUNTIME`/`VIBE_STATE`/`VIBE_CONFIG_FILE`; Server ebenso | gesamte API-Fälle | keine EROFS, kein Lesen persönlicher Config |
| `test_ticket_feedback_processing` | dito (beide Prozess-Envs) | `FeedbackFixture`, `FeedbackApiConcurrencyTest` | keine EROFS |
| `test_ap4_korbat_github` | `GITHUB_AUTO_MERGE` in `ISOLATED_ENV`; alle `ISOLATED_ENV`-Keys im Test-Setup entfernt; Läufer-Env entfernt den geerbten Schalter | `PrOnlyRunnerTest` (und alle Läuferfälle) | ohne project.env-Schalter PR-only |
| `test_sandbox` | API-Server-Env isoliert | `SandboxApiTest` | API erreichbar |
| `test_project_guide` | API-Server-Env isoliert | `ProjectGuideApiTest` | kein EROFS |

Neu ist `test_feedback_capture.test_detail_page_offers_only_title_and_description`
in der Regex-Fassung: Vorbedingung = ausgelieferte Classic-Seite; Aktion =
Feedback-Karte extrahieren; Erwartung = genau die Labels „Titel“ und
„Beschreibung“ (AP21 schreibt `el('label',{},tr('Titel'))`, ältere Stände
literal). Das ist eine Nachziehung auf den aktuellen Produktstand, keine
Abschwächung.

### B — T-BR2: explizite Verschachtelungs-Skips

`env_support.sandbox_nested()` liefert True nur für
`VIBE_SANDBOX_ACTIVE` ∈ {`1`,`on`,`true`} (case-insensitiv, getrimmt).
`skip_if_sandbox_nested` trägt die Begründung: Innerhalb der vibe-Sandbox kann
bwrap keinen weiteren Benutzernamensraum anlegen; der Skip betrifft nur die
Verschachtelung, nicht die Verfügbarkeit.

| Testfall | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|
| `SandboxCommandTest.test_real_sandbox_allows_questions_but_not_the_web_token` | SANDBOX=on, echtes bwrap | vibe_sandbox mit Rückfrage-/Token-Probe starten | nested: skipped; außerhalb: echter Lauf |
| `…test_real_sandbox_allows_write_dirs_and_denies_unlisted_paths` | dito | Schreibproben | dito |
| `…test_real_sandbox_denies_writes_to_the_unlisted_tmp` | dito | Schreibprobe /tmp | dito |
| `…test_real_sandbox_keeps_the_project_configuration_read_only` | dito | Schreibprobe project.env | dito |
| `…test_check_passes_with_bwrap_and_available_tools` | SANDBOX=on, `check()` | `check()` | nested: skipped |
| `…test_cargo_file_cache_does_not_break_the_sandbox` | Cargo-Cache, `check()` | `check()` | nested: skipped |
| `SandboxApiTest.test_api_switches_sandbox_sets_tools_and_runs_the_check` | Dashboard, SANDBOX-Schalter | POST /api/sandbox → `check()` | nested: skipped |
| `SandboxRunnerTest.test_runner_uses_standalone_sandbox_and_blocks_home_writes` | SANDBOX=on, Fake-opencode | `vibe-run.sh` | nested: skipped |
| `…test_runner_sandboxes_every_documented_active_value` | on/TRUE/yes/1 | `vibe-run.sh` je Wert | nested: skipped |
| `PiAgentDirRunTest.test_pi_agent_dir_writable_state_visible_and_home_denied` | SANDBOX=on | echter bwrap-Lauf | nested: skipped |
| `ShmIsolationTest.test_host_shm_content_is_invisible_inside_the_sandbox` | SANDBOX=on | echter bwrap-Lauf | nested: skipped |
| `…test_sandbox_shm_content_is_invisible_to_the_host` | dito | dito | nested: skipped |
| `ShmProjectRunTest.test_project_under_shm_is_writable_and_host_shm_stays_isolated` | dito | dito | nested: skipped |
| `SandboxPrivateServerTest.test_sandboxed_run_starts_the_private_server_inside_the_sandbox` | SANDBOX=on, privater Server | `vibe-run.sh` | nested: skipped |
| `ProjectGuideAgentTest.test_agent_command_is_wrapped_when_the_sandbox_is_on` | SANDBOX=on | `_agent_command` | nested: skipped |
| `…test_sandboxed_command_can_write_the_draft_but_not_the_configuration` | SANDBOX=on | echter bwrap-Lauf | nested: skipped |

Nicht markiert bleiben Fälle, die nur `bwrap_argv`/`status`/`--print-command`
prüfen oder bewusst einen fehlenden/broken bwrap erwarten (z. B.
`test_missing_bwrap_fails_closed_without_running_the_command`): sie brauchen
keinen echten Sandbox-Start.

**Beobachtete Skip-Zahlen**

| Lauf | Ergebnis |
|---|---|
| `VIBE_SANDBOX_ACTIVE=1 … test_sandbox` | `Ran 36 tests … OK (skipped=9)` |
| `VIBE_SANDBOX_ACTIVE=1 … test_b4_pi_agent_dir` | `Ran 6 … OK (skipped=1)` |
| `VIBE_SANDBOX_ACTIVE=1 … test_b5_sandbox` | `Ran 14 … OK (skipped=3)` |
| `VIBE_SANDBOX_ACTIVE=1 … test_b13_private_server_runner` | `Ran 10 … OK (skipped=1)` |
| `VIBE_SANDBOX_ACTIVE=1 … test_project_guide` | `Ran 36 … OK (skipped=2)` |
| ohne Variable: dieselben Module | `test_sandbox` FAILED (12), b4 FAILED (1), b5 FAILED (3), b13 FAILED (1), project_guide FAILED (2 Errors) — jeweils an bwrap, erwartbar |

### C — T-BR6: robuste Git-Meldung in `test_ap06_github`

| Test | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|
| `CliPushTest.test_cli_push_without_any_remote_reports_the_problem` | Projekt ohne Remote; `LC_ALL=C`/`LANG=C` für den Aufruf | `cmd_github("proj","push")` | Exit 1, nichtleere Ausgabe und Git-Fehlerkern „does not appear to be a git repository“ **oder** „Could not read from remote repository“ |

Intent erhalten: Eine verschluckte Meldung (Exit 0 oder leere/andere Ausgabe)
lässt den Test scheitern; der frühere deutsche Substring „Remote“ war keine
stabile Git-Ausgabe. `run_push` setzt die Locale deterministisch.

### D — T-BR8: `test_feedback_entries` entkoppelt

Moduldocstring dokumentiert: `FEEDBACK.md` ist nicht versioniert, der lokale
Ledger-Zustand ist nicht repo-verifizierbar.

| Test | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|
| `FeedbackBlockStructureTest.test_every_checked_entry_keeps_its_proof_inside_the_block` | `F7_FIXTURE` mit F7/F8 | `blocks()` + Prüf-Regexe | jeder abgehakte Punkt hat `Commit:` und `Test:`/`Datei:` im Block |
| `…test_f7_continuation_and_proof_belong_to_the_item` | dito | F7-Block selektieren | Fortsetzung `  ist es möglich` und `  Commit: 0406429; Test: Sandbox` gehören zum Block |
| `…test_non_indented_continuation_ends_the_block` | `BROKEN_FIXTURE` (Fortsetzung ohne Einrückung) | F7-Block selektieren | Fortsetzung/Nachweis fehlen im Block — die Blockregel greift |

### E — T-BR7: Installationsvertrag und BLOCKED-Präzedenz

| Test | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|
| `InstallLifecycleBase.install()`-Fälle (Frischinstallation/Update/Reuse/Rollback/Uninstall, 43 Tests) | Kit + Workspace; Installationsort `<workspace>/_toolchain` | `install_program_files(kit, toolchain)`, `verify_installation(toolchain)`, `rollback/select_backup/uninstall(toolchain)` | Programme/Vorlagen/Katalog im Installationsort; Sicherungen/Rollback dort; Launcher-Entfernung am Installationsort |
| `FreshInstallTest.test_fresh_install_copies_all_program_modules_and_writes_version` | dito | Installation | alle `PROGRAM_FILES`/`WEB_FILES`, `version.json` |
| `UpdateTest.test_reuse_keeps_user_templates_and_programs` | vorhandene Installation | Reuse | Bestand bleibt, nur Fehlendes ergänzt |
| `PreviewTest.test_plan_lists_new_changed_and_unchanged_files` | vorhandene `bin/vibe` | `build_install_plan(kit, toolchain)` | `copy`/`backup`/`skip` korrekt |
| `test_setup_vibe.InstallFilesTest.*` | Kit, Workspace, Installationsort | `install_program_files(..., vibe/"_toolchain")` | identische Erwartungen wie bisher, nun am Ist-Vertrag |
| `LauncherTest.test_posix_launcher_is_a_symlink_to_the_installed_program` | Toolchain-Programm | `install_launcher(toolchain, home, …)` | Symlink → `<toolchain>/bin/vibe` |
| `…test_windows_launcher_starts_the_python_program` | dito, Windows-Plattform | `install_launcher(toolchain, …)` | `<toolchain>/vibe.cmd`, Inhalt `py -3 "%~dp0bin\vibe" %*`; kein `vibe.cmd` im Workspace |
| `ProjectRegistrationTest.test_existing_project_configuration_is_kept_and_new_projects_are_registered` | Workspace mit bestehendem/neuem/worktree/android-Projekt | `register_projects(workspace, toolchain)` | vorhandene Config unverändert; neue aus Toolchain-Vorlage; Reihenfolge unverändert |
| `ProjectRegistrationTest.test_registration_does_not_create_a_hardcoded_test_agent` | dito, Vorlage `common/.opencode/...` vorhanden | dito | **kein** `.opencode/agents/test-agent.md`, **kein** `TESTER=`; kein `test_agent_created` |
| `…test_register_projects_keeps_an_existing_test_agent` | Projekt hat eigenen Test-Agenten | dito | Datei byte-gleich; kein `test_agent_created` |
| `BlockedEntryTest.test_blocked_entry_with_checkbox_and_proof_is_done` | FEEDBACK F1: `[x]`, gültiger Commit + Test, zusätzlich `BLOCKIERT:` | `feedback_items`/`open_items` | AP3-Präzedenz: `state=erledigt`, `completed=True`, nicht in `open_items` |
| `BlockedEntryTest.test_blocked_ticket_stays_open` | TICKETS V-1 **offen** (`- [ ]`) mit `BLOCKIERT:` | `open_items` | `("Blockiert","BLOCKIERT")` (angehakte, vollständig erledigte Einträge werden nach B3/AP3 übersprungen) |

Doku-Drift, nicht testseitig versteckt: `docs/features/F6.md:145` nennt noch
die alte Launcher-Form `%~dp0_toolchain\bin\vibe`; die Implementierung schreibt
im getrennten Layout `%~dp0bin\vibe` im Installationsort. Die Tests folgen der
Implementierung; die Doku sollte nachgezogen werden.

### G — T-BR3: `ensure_test_agent`-Cleanup (Entscheidung A)

Entfernt wurden ausschließlich Stubs/Patches auf das mit `35233ff` entfernte
Attribut; alle übrigen Assertions blieben unverändert:

| Modul | Entfernung | Betroffene Fälle (wieder grün) |
|---|---|---|
| `test_ap03_agent_management` | `mock.patch.object(cli, "ensure_test_agent")` im `cmd_run`-Helfer | `VibeRunGateTest` (5) |
| `test_b3_password_auto_setup` | dito | `AutoSetupOnRunStartTest` (2), `SteerAfterAutoSetupTest` (1) |
| `test_f22_preflight_assist` | Eintrag aus `patch.multiple` | `VibeRunLaunchTest.test_vibe_run_starts_runner_with_preflight_assist` |
| `test_f27_keep_changes` | Eintrag aus `patches()` | `AgentsRulesTest` (2), `CliKeepChangesTest` (3) |
| `test_v025_agent_start_repair` | `stack.enter_context(patch.object(...))` | alle `run_cmd`-Fälle (9) |
| `test_v026_run_isolation` | Eintrag aus `patch.multiple` | `RunSessionSocketTest` (2) |
| `test_project_agents` | `VIBE_MODEL` in `ISOLATED_ENV`; zwei obsolete Fälle ersetzt | `RunnerModelTest.test_without_override_no_model_flag_is_sent`; neuer Fall unten |

Ersetzung in `test_project_agents`:

| Test | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|
| `RunSelectionTest.test_cmd_run_does_not_create_a_hardcoded_test_agent` | Globaler Agent vorhanden, Projekt `TYPE=generic AGENT=tester` | `cmd_run("proj","vibe-agent")` mit externen Grenzen als Attrappen | `.opencode/agents/test-agent.md` existiert **nicht**; `project.env` enthält **kein** `TESTER=` |

Begründung: `test_cmd_run_ensures_the_independent_test_agent_for_an_existing_project`
und `test_cmd_run_aborts_when_the_test_agent_cannot_be_created` prüften die mit
`35233ff` bewusst entfernte Mechanik. Nach Entscheidung A wird nicht
wiederhergestellt; der neue Fall sichert die aktuelle Aussage (kein
hartkodierter Test-Agent, kein `TESTER=`). Der Nachweis-/Meldungspfad über
`copy_tree`/`_test_agent_created` ist in `test_ap5_korbat_init_adopt` belegt.

`test_v026_run_isolation`: `running_installation(self.runtime)` statt
`self.root` — seit `67d53bc` liest die Setup-Sperre `runs.json` aus dem
Logverzeichnis; Vorbedingung `runs.json` mit laufendem `lauf-1` in `_logs`,
Aktion `running_installation(runtime, runner=Fake, which=Fake)`, Erwartung
`reasons` nennt `lauf-1` und die tmux-Prüfung nutzt `-L vibe-proj`.

### H — `openwrt` aus `TOOL_DEFAULTS`

Der Projekttyp wurde im Repo-Cleanup entfernt (`templates/openwrt` existiert
nicht, `types()` listet ihn nicht). `SandboxConfigTest.test_templates_preselect_sandbox_and_build_tools`
prüft jetzt nur noch `generic`, `web`, `android`, `docker`, `rebuild`.
Erwartung unverändert je Typ: `SANDBOX=on` und die dokumentierten Werkzeuge
(`web`: `git node npm`, `docker`: `git docker`; Vorlagen vom Coding-Agenten
ergänzt). Beobachtet: `…test_templates_preselect_sandbox_and_build_tools … ok`.

### I — persönlicher Home-Pfad in B18

`tests/browser/test_b18_harness_ui.py` Zeile 84 war ein Docstring-Beispiel für
den Playwright-Aufruf mit einem persönlichen Home-Pfad. Ersetzt durch
`PLAYWRIGHT_BROWSERS_PATH="$HOME/vibe-logs/playwright-browsers"`. Die Aussage
(so werden die Browser für die Rotphase gefunden) bleibt erhalten, der Pfad
ist portabel.

Prüfung: `git ls-files` + `HOME_PATH_RE`/`PLACEHOLDER_USERS` aus
`scripts/build-release.py` → **0 Treffer**. `test_release` bleibt dennoch rot,
weil der fremde Review-Text (`docs/reviews/AP6-Korbat-review-1.md:22`) den
alten absoluten Pfad wörtlich zitiert (siehe §2).

### J2 — persistenter Vertragstest für den T-BR2-Marker

| Test | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|
| `SandboxArgvTest.test_nested_sandbox_marker_is_set_once_before_the_command` | `SANDBOX=on` in `project.env`; `VIBE_BWRAP` zeigt auf ausführbare Attrappe; kein echter Sandbox-Start | `vibe_sandbox.bwrap_argv(project, ["true"], runtime=…)` | genau ein Tripel `('--setenv','VIBE_SANDBOX_ACTIVE','1')`; `VIBE_SANDBOX_ACTIVE` steht vor dem `--`-Trenner und nicht in der Kommandoliste |

Sinn: Fällt die Marker-Setzung produktseitig weg, wird dieser Test rot. Damit
hängt der Verschachtelungs-Skip dauerhaft am Marker und nicht an einem
pauschalen `skipUnless(bwrap verfügbar)`. Eine eigene Rotphase war für diesen
Fall nicht beobachtbar, weil der Marker zum Zeitpunkt der Testergänzung
bereits implementiert war; der Fall wurde gegen den Ist-Vertrag geschrieben
und tatsächlich ausgeführt.

Lauf: `env -u SANDBOX python3 -m unittest tests.unit.test_b17_sandbox_argv -v`
→ **Ran 5 tests … OK** (vorher 4 Fälle; +1).

---

## 4) Grünphasen-Belege (tatsächlich ausgeführt)

Alle Befehle als `python3 -m unittest tests.unit.<modul> -v` im kontaminierten
Env, sofern nicht anders angegeben.

| Modul | Ergebnis |
|---|---|
| `test_web_api_security` | Ran 22 — OK |
| `test_project_write_dirs` | Ran 40 — OK |
| `test_lifecycle` | Ran 17 — OK |
| `test_pause_after_package` | Ran 16 — OK |
| `test_costs` | Ran 36 — OK |
| `test_b8_no_remote_block` | Ran 13 — OK |
| `test_fritz_reconnect` | Ran 28 — OK |
| `test_storage` | Ran 32 — OK |
| `test_feedback_capture` | Ran 8 — OK |
| `test_feedback_completed` | Ran 9 — OK |
| `test_feedback_edit_delete` | Ran 21 — OK |
| `test_ticket_feedback_processing` | Ran 28 — OK |
| `test_ap4_korbat_github` | Ran 21 — OK |
| `test_ap06_github` | Ran 54 — OK |
| `test_feedback_entries` | Ran 3 — OK |
| `test_install_lifecycle` | Ran 43 — OK |
| `test_setup_vibe` | Ran 50 — OK |
| `test_sandbox` (mit Marker) | Ran 36 — OK (skipped=9) |
| `test_sandbox` (ohne Marker) | Ran 36 — FAILED (12) — bwrap-Umgebung |
| `test_b4_pi_agent_dir` (mit Marker / ohne) | Ran 6 — OK (skipped=1) / FAILED (1) |
| `test_b5_sandbox` (mit Marker / ohne) | Ran 14 — OK (skipped=3) / FAILED (3) |
| `test_b13_private_server_runner` (mit Marker / ohne) | Ran 10 — OK (skipped=1) / FAILED (1) |
| `test_project_guide` (mit Marker / ohne) | Ran 36 — OK (skipped=2) / FAILED (2 Errors) |
| `test_ap03_agent_management` | Ran 32 — OK |
| `test_b3_password_auto_setup` | Ran 3 — OK |
| `test_f22_preflight_assist` | Ran 20 — OK |
| `test_f27_keep_changes` | Ran 14 — OK (nach Produktkorrektur) |
| `test_project_agents` | Ran 25 — OK |
| `test_v025_agent_start_repair` | Ran 11 — OK |
| `test_v026_run_isolation` | Ran 18 — OK |
| `test_b17_sandbox_argv` | Ran 5 — OK |
| `tests.browser.test_b18_harness_ui` | Ran 6 — OK |
| `test_ap12_github_readiness` + `test_release` | Ran 25 — FAILED (2) — §2 |
| `python3 -m py_compile` über `env_support.py`, `tests/unit/test_*.py`, `test_b18_harness_ui.py` | Exit 0 (compile ok) |

Der Rückgang von `test_project_agents` 26 → 25 erklärt sich durch das
Zusammenlegen der zwei obsoleten Test-Agent-Fälle zu einem neuen
Regressionsfall.

---

## 5) Grenzen

* `test_feedback_entries` war am Ausgangscommit laut Audit rot; den Rotlauf
  habe ich nicht selbst ausgeführt (die alte Fassung ist nicht mehr im
  Arbeitsbaum). Die Ursache ist am Quelltext und am lokalen Ledger
  nachvollzogen.
* bwrap ist in dieser Umgebung grundsätzlich nicht startbar; die Skips sind
  nur über den Marker, nicht über eine echte Verschachtelung verifizierbar.
  Außerhalb der Sandbox bleiben die bwrap-Fälle sichtbar rot — wie beabsichtigt.
* Keine Vollläufe, keine Browser-Suite insgesamt, kein Verify-Skript: Diese
  Checks liegen beim Runner. `test_ap12_github_readiness` und `test_release`
  bleiben mit den in §2 genannten, außerhalb meines Umfangs liegenden Ursachen
  rot.
* Der Rename-Randfall in `merge_package` (Review Minor 3) ist fail-closed und
  nicht testseitig abgedeckt; er ist als dokumentierte Grenze im Review
  benannt.
