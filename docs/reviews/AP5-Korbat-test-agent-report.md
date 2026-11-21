# AP5-Korbat — Testbericht des unabhängigen Test-Agenten

Stand: Rotphase vor der Implementierung
Repository: `/var/log/custom/vibe-dev/worktrees/vibe-AP5-Korbat-hjLTVH`
Branch: `feature/korbat/ap5-korbat`
Grundlage: Arbeitspaket AP5-Korbat (`TICKETS.md`), `SPEC.md`, `AGENTS.md`,
Audit-Lesestücke AP5.md/AP6.md. Die Fälle wurden aus dem Arbeitspaket und der
Spezifikation abgeleitet, nicht aus einem Implementierungsdiff.

## Angelegte und geänderte Testdateien

| Datei | Status | Inhalt |
|---|---|---|
| `tests/unit/test_ap5_korbat_init_adopt.py` | neu | C1–C5: `cmd_init`/`_adopt_checked_out_project` ohne `NameError`, Meldung/Notiz nur bei neu kopierter Test-Agent-Vorlage, Bestandsschutz, kein `TESTER=` |
| `tests/unit/test_ap5_korbat_project_env_transport.py` | neu | read-only Einweg-Transport von `.vibe/project.env`, Exclude, Idempotenz, keine Geheimnisse, kein Rückschreiben |
| `tests/unit/test_ap5_korbat_waiting_state.py` | neu | 4a/4b: Marker `WARTET AUF MERGE`, `mark-waiting`, Auswahl/Status/Priorität, Ticket-Status, Nachweis-Aufräumen, Läufer-Verdrahtung, Nova-/klassische GUI, i18n |
| `tests/unit/test_verify_script.py` | angepasst | T-V1: `VERIFY_PACKAGE_TESTS` statt `VERIFY_TESTS` für `package`; T-V2: Präfix `vv-` und `VIBE_VERIFY_TMP` |
| `tests/unit/test_ap4_korbat_github.py` | angepasst | PR-only-Marker auf `WARTET AUF MERGE`; neue Klasse `EnsureMergeableCredentialTest` für 4c |

Keine Produktionsdatei, kein Prüfskript und keine Konfiguration wurde
verändert. Es wurde nichts gestaged oder committet.

## Testfälle je Akzeptanzkriterium

### C1/C3/C5 — `vibe init` läuft und meldet nur einen neu angelegten Test-Agenten

| Test | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|
| `InitTestAgentMessageTest.test_init_reports_a_newly_created_test_agent` | Eigene `templates/common` mit `.opencode/agents/test-agent.md`, Projekt vorhanden | `cmd_init("proj")` | Kein `NameError`; Datei im Projekt; Ausgabe enthält „Unabhängiger Test-Agent ergänzt“ |
| `…test_init_stays_silent_without_a_test_agent_template` | Vorlage ohne Test-Agent-Datei | `cmd_init("proj")` | Kein `NameError`; keine Meldung, keine Datei (still) |
| `…test_init_does_not_overwrite_an_existing_test_agent` | Projekt hat eigenen Test-Agenten, Vorlage weicht ab | `cmd_init("proj")` | Bestand unverändert; keine Erfolgsmeldung |
| `…test_init_does_not_write_a_tester_assignment` | Vorlage mit Test-Agent, `project.env` nur `TYPE=generic` | `cmd_init("proj")` | Keine `TESTER=`-Zeile (kein Rückfall auf Commit 35233ff) |

Fehlerfall jeweils: Absturz, Meldung ohne Neuanlage, Überschreiben oder
hardcoded Tester-Zeile.

### C2/C4/C5 — Übernahme läuft und notiert nur einen neu angelegten Test-Agenten

| Test | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|
| `AdoptTestAgentNoteTest.test_adopt_notes_a_newly_created_test_agent` | Projekt ohne Agent, Vorlage mit Test-Agent | `_adopt_checked_out_project(project, "proj")` | Kein `NameError`; Datei angelegt; Notiz nennt „Test-Agent“ |
| `…test_adopt_stays_silent_without_a_test_agent_template` | keine Vorlagendatei | wie oben | Kein `NameError`; keine Notiz, keine Datei |
| `…test_adopt_preserves_an_existing_test_agent_and_stays_silent` | Projekt hat eigenen Test-Agenten | wie oben | Inhalt unverändert; keine Notiz |
| `…test_adopt_does_not_write_a_tester_assignment` | Vorlage mit Test-Agent | wie oben | Keine `TESTER=`-Zeile |

### project.env-Transport (read-only, Einweg)

Geprüft über den echten CLI-Einstieg `python3 bin/vibe_packages.py copy-notes`
in einem temporären Git-Projekt mit echter `git worktree`-Arbeitskopie.

| Test | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|
| `ProjectEnvTransportTest.test_project_env_is_copied_read_only_and_excluded` | `project/.vibe/project.env` vorhanden; Worktree ohne `.vibe`; Exclude-Datei fehlt zunächst | `copy-notes --project … --worktree …` | Exit 0; Kopie inhaltlich gleich; keine Schreibbits (0444 best effort, FS-Probe); Exclude-Datei wird angelegt und enthält `.vibe/project.env` genau einmal; eigene OK-Zeile mit „project.env“ |
| `…test_missing_project_env_creates_no_vibe_folder_and_no_exclude` | keine `project.env`, aber `.vibe/_secrets.env` | `copy-notes` | Exit 0; Worktree-`.vibe/` entsteht nicht; kein Exclude-Eintrag; keine Transport-OK-Zeile |
| `…test_only_project_env_is_transported_never_secrets` | `.vibe` enthält `project.env`, `_secrets.env`, weitere Datei | `copy-notes` | Nur `project.env` wird kopiert; Geheimnis und weitere Datei fehlen |
| `…test_copy_and_exclude_are_idempotent` | erster Transport erfolgt; Projektstand geändert | `copy-notes` erneut | Kopie trägt neuen Projektstand; Exclude-Eintrag weiterhin genau einmal |
| `…test_sync_proof_never_writes_the_project_env_back` | Transport erfolgt; Worktree-Kopie lokal geändert; abgehakter Nachweis T1 | `sync-proof --project … --worktree … --id T1` | Exit 0; Projekt-`project.env` byte-gleich; Worktree-Kopie bleibt liegen |

Fehlerfälle: fehlende/abweichende Kopie, beschreibbare Datei, fehlender oder
doppelter Exclude-Eintrag, transportierte Geheimnisse, Rückschreiben.

### T-V1 — `VERIFY_PACKAGE_TESTS` entkoppelt den Paketmodus vom Vollmodus

Angepasste Bestandstests (Vertragsänderung laut Ticket; vorher koppelten sie
`package` an `VERIFY_TESTS`):

* `test_package_requires_test_files_when_package_tests_is_set`
  (vorher `…when_verify_tests_is_set`) — jetzt `VERIFY_PACKAGE_TESTS`.
* `test_package_rejects_a_run_without_executed_tests` — jetzt
  `VERIFY_PACKAGE_TESTS`.
* `test_package_passes_with_real_tests_and_reports_the_count` — jetzt
  `VERIFY_PACKAGE_TESTS`.
* `test_package_rejects_fewer_tests_than_configured` — jetzt
  `VERIFY_PACKAGE_TESTS`.
* `test_package_without_package_tests_requires_no_test_proof` (vorher
  `…without_verify_tests…`) — Aussage unverändert: ohne Paket-Testschlüssel
  kein Nachweiszwang.

Neue Fälle:

| Test | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|
| `test_package_stays_static_even_when_verify_tests_is_set` | nur `VERIFY_TESTS="tests"` gesetzt, kein Testordner | `package` | Exit 0; statischer `VERIFY_PACKAGE` genügt |
| `test_full_still_requires_verify_tests_and_ignores_verify_package_tests` | `VERIFY_FULL` + `VERIFY_PACKAGE_TESTS`, aber kein `VERIFY_TESTS` | `full` | Exit 6; Meldung verlangt `VERIFY_TESTS` |
| `test_help_names_the_package_test_key` | `--help` | Hilfe ausgeben | `VERIFY_PACKAGE_TESTS` wird genannt |
| `test_package_requires_test_files_when_package_tests_is_set` | `VERIFY_PACKAGE_TESTS="tests"`, kein Testordner | `package` | Exit 6 |
| `…rejects_a_run_without_executed_tests` | „Ran 0 tests“ | `package` | Exit 6 |
| `…passes_with_real_tests_and_reports_the_count` | echte Tests | `package` | Exit 0, „Tests erkannt: 1“ |
| `…rejects_fewer_tests_than_configured` | `VERIFY_MIN_TESTS=2`, ein Test | `package` | Exit 6, „Minimum 2“ |

`full` behält `VERIFY_TESTS` als Pflicht (bestehende `VerifyFullTest`-Fälle
unverändert grün).

### T-V2 — kurzer Verify-Tempfpad

| Test | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|
| `VerifyTempDirectoryTest.test_default_temp_directory_uses_the_short_prefix` | eigener `TMPDIR` | `quick --keep` | Verzeichnisname beginnt mit `vv-`, nicht `vibe-verify-`; Elternordner = `TMPDIR` |
| `…test_vibe_verify_tmp_places_the_directory_under_the_configured_folder` | `VIBE_VERIFY_TMP` gesetzt | `quick --keep` | Prüfverzeichnis direkt unter diesem Ordner, Präfix `vv-` |
| `…test_vibe_verify_tmp_is_still_cleaned_up_without_keep` | `VIBE_VERIFY_TMP` gesetzt, Erfolg ohne `--keep` | `quick` | Prüfverzeichnis entfernt; Elternordner bleibt |

### 4a/4b — Wartet-auf-Merge-Zustand statt BLOCKIERT

| Test | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|
| `WaitingMarkerUnitTest.test_is_waiting_merge_is_true_for_the_new_marker_only` | Blöcke mit WARTET/BLOCKIERT | `is_waiting_merge`, `is_blocked` | Marker sauber getrennt; `is_blocked` unverändert |
| `…test_sync_proof_removes_waiting_and_blocked_markers` | Projektblock mit beiden Markern; Worktree-Nachweis | `sync_proof(..., require_commit=False)` | Beide Marker entfernt, Nachweis übernommen |
| `MarkWaitingCommandTest.test_mark_waiting_writes_an_indented_marker_and_reports_waiting` | offenes Paket T1 | `mark-waiting --id T1 --note …` | Exit 0; eingerückte Zeile `  WARTET AUF MERGE: …`; Ausgabe nennt „wartend“ |
| `…test_mark_waiting_is_idempotent` | Marke vorhanden | Befehl erneut | Marker genau einmal; Ausgabe nennt weiter „wartend“ |
| `…test_mark_waiting_leaves_other_blocks_unchanged` | T1 und T2 offen | `mark-waiting` für T1 | Nur T1 erhält die Marke |
| `WaitingSelectionAndReportTest.test_select_package_skips_a_waiting_package` | T1 wartet, T2 offen | `select_package` | T2 wird gewählt |
| `…test_select_package_with_prefer_reattaches_a_waiting_package` | T1 wartet | `select_package(prefer="T1")` | T1 wird ausdrücklich gewählt (Reattach) |
| `…test_status_report_lists_waiting_before_open` | T1 wartet, T2 offen, T3 blockiert, T4 beide Marker | `status_report` | `waiting=["T1"]`, `open=["T2"]`, `blocked` enthält T3/T4 |
| `…test_priority_view_marks_waiting_in_order_and_standard` | `PACKAGE_ORDER="T1,T2"`, T1 wartet | `priority_view` | `order`/`standard`: T1 „wartet auf Merge“; `queue` beginnt mit T2 |
| `TicketStatusWaitingTest.test_open_items_marks_waiting_tickets` | TICKETS T1 mit Marker | `open_items` | Status „WARTET AUF MERGE“ |
| `…test_open_items_shows_waiting_feedback` | FEEDBACK F1 mit Marker | `open_items` | Status „WARTET AUF MERGE“ |
| `…test_blocked_wins_when_a_block_carries_both_markers` | T1 mit beiden Markern | `open_items`/`_parse_entry` | Status „BLOCKIERT“ |
| `RunnerWiringTest.test_pr_only_fallback_uses_mark_waiting_and_keeps_the_log_line` | Quelltext `bin/vibe-run.sh` | `pr_only_fallback` ausschneiden | Aufruf `mark-waiting`, kein `mark-blocked`; Logzeile „WARTET AUF MERGE“ bleibt |

GUI (Quelltext-/Strukturprüfung wie im Bestand, kein Browser):

| Test | Erwartetes Ergebnis |
|---|---|
| `NovaWaitingSurfaceTest.test_nova_maps_waiting_to_its_own_column_and_label` | `nvpStateColumn` → `waiting`, Label „Wartet auf Merge“ |
| `…test_nova_board_orders_the_waiting_column_between_open_and_blocked` | Spaltenfolge `open, waiting, blocked` |
| `…test_nova_overview_counts_waiting_packages` | Übersichtskachel `waiting` zählt `WARTET AUF MERGE` |
| `…test_nova_offers_package_close_in_blocked_and_waiting_columns` | Abschluss-Button in `blocked` und `waiting`, nur `!isFeedback` |
| `…test_nova_waiting_pill_uses_the_warning_colors` | Wartend → `nv-warn` |
| `…test_english_translation_names_waiting_for_merge` | `"Wartet auf Merge": "Waiting for merge"` |
| `ClassicWaitingSurfaceTest.test_classic_ticket_pill_marks_waiting_as_warning` | `app.js`: WARTET → `warn`, BLOCKIERT → `bad` |

Bestandsschutz (Tickets mit alten BLOCKIERT-Vermerken bleiben blockiert) ist
durch `…test_blocked_wins_when_a_block_carries_both_markers` und den
unveränderten `is_blocked`-Fall abgedeckt.

### 4c — Credential aus dem Projektordner für `ensure_mergeable`

Neue Klasse `EnsureMergeableCredentialTest` in
`tests/unit/test_ap4_korbat_github.py` (bestehende `GithubCase`-Fixture,
Git-Stub statt Netz):

| Test | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|
| `test_fetch_in_the_worktree_uses_the_project_token` | Projekt-Token A, Worktree-Token B; Base `origin/main` Vorfahr | `ensure_mergeable(project, worktree, base=…)` | Alle Git-Aufrufe im Worktree erhalten Token A über die Prozessumgebung; A steht nie in argv/Meldung; Erfolg |
| `test_without_any_token_the_fetch_fails_with_guidance` | kein Token; Fetch scheitert mit „could not read Username“ | wie oben | `ok=False`; Meldung enthält „Zugangsdaten“; keine Credential-Injektion |

## Rotphase — tatsächlich ausgeführte Befehle und Ergebnisse

Alle Befehle im Repository-Root. Die Ausgangsstände sind unverändert (keine
Implementierung).

| Befehl | Ergebnis | Bewertung |
|---|---|---|
| `python3 -m unittest tests.unit.test_ap5_korbat_init_adopt -v` | `Ran 8 tests`, `FAILED (errors=8)` | Alle 8 scheitern mit `NameError: name 'agent' is not defined` in `bin/vibe:2743` — richtiger Grund (C1) |
| `python3 -m unittest tests.unit.test_ap5_korbat_project_env_transport -v` | `Ran 5 tests`, `FAILED (failures=2, errors=2)` | Kopie/Exclude/Idempotenz/Sync fehlen; der reine Negativfall („keine project.env“) ist erwartungsgemäß schon grün |
| `python3 -m unittest tests.unit.test_ap5_korbat_waiting_state -v` | `Ran 20 tests`, `FAILED (failures=17, errors=1)` | `is_waiting_merge` fehlt (`AttributeError`), `mark-waiting` unbekannt, Status/Auswahl/GUI unverändert; der `prefer`-Reattach und der BLOCKIERT-Vorrang bei beiden Markern sind bereits grün |
| `python3 -m unittest tests.unit.test_verify_script -v` | `Ran 34 tests`, `FAILED (failures=9)` | 8 erwartete Vertragsfälle (T-V1/T-V2) plus der bekannte Umgebungsfall `RepositoryVerifyTest` (siehe Grenzen) |
| `python3 -m unittest tests.unit.test_ap4_korbat_github -v` | `Ran 21 tests`, `FAILED (failures=2)` | `PrOnlyRunnerTest` schreibt noch `BLOCKIERT`; `EnsureMergeableCredentialTest` sieht den Worktree-Token statt des Projekt-Tokens |
| `python3 -m unittest tests.unit.test_project_management -v` (Referenz) | `Ran 36 tests`, `FAILED (failures=4, errors=15)` | 14× `NameError: name 'agent' is not defined`; 1× `FileNotFoundError` für die im Branch fehlende Vorlage `templates/common/.opencode/agents/test-agent.md`; 4 veraltete Fachlichkeitserwartungen (TESTER/Test-Agent in Vorlagen und `AGENTS.md`) |
| `python3 -m unittest tests.unit.test_ap9_github -v` (Referenz) | `Ran 44 tests`, `FAILED (failures=1)` | `test_cli_clone_checks_out_the_requested_branch`: `NameError: name 'agent_note' is not defined` — richtiger Grund (C2) |

Abweichung zur Vorgabe: Statt 17 `NameError`-Fehlern in
`test_project_management` wurden hier 14 `NameError` plus ein
`FileNotFoundError` beobachtet, weil die Test-Agent-Vorlage in diesem Branch
fehlt; zusätzlich bleiben 4 F22-/Vorlagen-Erwartungen rot. Diese Datei wurde
bewusst nicht angefasst.

Konkrete Rotursachen der neuen Fälle (belegt durch die Läufe):

* C1: `bin/vibe:2743` `agent` undefiniert.
* C2: `bin/vibe` `agent_note` undefiniert (Referenzlauf AP9).
* Transport: `copy-notes` kopiert `.vibe/project.env` nicht und schreibt
  keinen Exclude-Eintrag.
* Wartezustand: Marker/CLI/Funktionen fehlen; `open_items` meldet „offen“,
  `select_package` wählt das wartende Paket, `status_report` kennt kein
  `waiting`, `_apply_proof` lässt WARTET-Zeilen stehen.
* T-V1: `package` koppelt weiterhin an `VERIFY_TESTS`; Hilfe nennt
  `VERIFY_PACKAGE_TESTS` nicht.
* T-V2: Präfix ist weiterhin `vibe-verify-`; `VIBE_VERIFY_TMP` wird ignoriert.
* 4c: Credential-Auflösung nutzt den Worktree-Pfad.

## Anpassungen an Bestandstests (Vertragsänderung, nicht Abschwächung)

1. `tests/unit/test_ap4_korbat_github.py::PrOnlyRunnerTest`
   `test_pr_only_stops_without_local_merge_and_keeps_the_worktree`:
   Die Erwartung `BLOCKIERT` wurde auf `WARTET AUF MERGE` geändert und um
   `assertNotIn("BLOCKIERT", …)` ergänzt. Begründung: AP5-Korbat 4a ersetzt den
   PR-only-Vermerk ausdrücklich durch den neuen Wartezustand; der bisherige
   Test hätte die geforderte Änderung als Regression gemeldet.
2. `tests/unit/test_verify_script.py::VerifyPackageTest`:
   Fünf Fälle wurden vom Schlüssel `VERIFY_TESTS` auf
   `VERIFY_PACKAGE_TESTS` umgestellt (Namen und Docstrings angepasst).
   Begründung: T-V1 entkoppelt den Paketmodus; `VERIFY_TESTS` steuert nur noch
   `full`. Neue Fälle sichern die Entkopplung und die unveränderte
   Vollmoduspflicht. Keine Assertion wurde entfernt; die Prüfung ist strenger
   geworden (statischer Paketlauf trotz gesetztem `VERIFY_TESTS`).

## Grenzen und nicht ausgeführte Checks

* Die GUI-Fälle sind Quelltext-/Strukturprüfungen wie im Bestand (kein
  Browser/Playwright in dieser Umgebung). Das tatsächliche Rendering,
  Responsive-Verhalten und die Klickstrecke des Abschluss-Buttons wurden nicht
  im Browser geprüft.
* 4c prüft die Credential-Weitergabe über einen protokollierenden
  `subprocess.run`-Stub; ein echter HTTPS-Fetch mit Credential-Helper gegen
  einen 401-Server wurde nicht ausgeführt. Damit ist die Pfadauflösung und
  argv-Geheimnisfreiheit belegt, nicht die vollständige Git-Authentisierung.
* Die Rotphase wurde vollständig vor der Implementierung erhoben. Ein
  Grünlauf nach der Implementierung steht noch aus (Codeseite); nach
  Implementierung sind die genannten Modulbefehle erneut auszuführen.
* `RepositoryVerifyTest.test_repository_quick_check_passes` ist in dieser
  Arbeitskopie umgebungsbedingt rot: `.vibe/project.env` fehlt im Worktree.
  Das ist kein Befund der AP5-Änderung; der Test wurde nicht abgeschwächt.
* `test_project_management` bleibt als bekannte Baseline rot (F22-Alterwartungen
  und die im Branch fehlende Test-Agent-Vorlage). Prognose: Nach C1/C2 laufen
  die Init-Fälle ohne `NameError` durch und melden dann ihre veralteten
  fachlichen Erwartungen (`TESTER=test-agent`, hardcoded Test-Agent); die
  beiden in der Aufgabe genannten F22-Tests sind darunter.
* `tests/unit/test_sandbox`, `test_fritz_reconnect`, `test_pause_after_package`,
  `test_project_agents`, `test_run_control`, `test_run_autostop` wurden nicht
  ausgeführt (bekannte Umgebungsmodule).
* Die vollständige Suite (`VERIFY_FULL`) wurde nicht ausgeführt; die
  Prüfungen erfolgten gezielt je betroffenem Testmodul.

## Nachtrag (Volllauf-Fund)

Der einmalige Volllauf
`env -u GITHUB_AUTO_MERGE python3 scripts/run-tests-parallel.py --dir tests/unit --jobs 4`
ergab 2212 Tests, davon 91 von 127 Modulen bestanden. Als einziger
**neuer** Rotbefund neben der dokumentierten Baseline zeigte sich ein
Bestandstest, der noch den alten PR-only-Vertrag pinnt:

* Test: `tests/unit/test_b16_runner_wiring.py::PrOnlyClosureTest::test_successful_run_pushes_and_opens_the_pr_then_waits_for_merge`
* Alte Erwartung: `assertIn("BLOCKIERT", FEEDBACK.md.upper())` — der Lauf
  musste das Paket als blockiert vermerken.
* Tatsächliches Soll-Verhalten nach der Implementierung:
  `vibe-run.sh pr_only_fallback` ruft `mark-waiting` auf; in `FEEDBACK.md`
  steht `WARTET AUF MERGE: PR-only: wartet auf Merge des Eigentümers; …`.
  Die AssertionError-Ausgabe des Volllaufs zeigte genau diesen
  WARTET-AUF-MERGE-Block und kein BLOCKIERT.

**Anpassung (keine Abschwächung):** Die Erwartung in `PrOnlyClosureTest`
wurde auf den neuen Vertrag umgestellt — `WARTET AUF MERGE` muss vorhanden
sein **und** `BLOCKIERT` darf nicht mehr vorkommen
(`assertNotIn("BLOCKIERT", …)`). Die Prüfung ist damit strenger als zuvor.
Der Docstring nennt jetzt Vorbedingung, Aktion, Erwartung und Fehlerfall und
begründet die Änderung mit AP5-Korbat 4b (neuer Wartezustand statt
BLOCKIERT). Das ist dieselbe Vertragsänderung wie die bereits dokumentierte
Anpassung in `tests/unit/test_ap4_korbat_github.py::PrOnlyRunnerTest`. Die
übrigen `BLOCKIERT`-Erwartungen der Datei (abgelehnter Push, fehlgeschlagener
Merge-Request, divergierter dev) betreffen echte Fehlerpfade und blieben
unverändert.

**Ausgeführter Befehl:**

```
env -u GITHUB_AUTO_MERGE python3 -m unittest tests.unit.test_b16_runner_wiring -v
```

Ergebnis: `Ran 6 tests`, `OK`, Exit-Code 0. (`env -u` ist nötig, weil die
Runner-Umgebung dieses Agenten `GITHUB_AUTO_MERGE=1` exportiert; der Test
erwartet den ungesetzten PR-only-Standard.)

**Einordnung des Volllaufs:** Außer diesem b16-Fund traten ausschließlich
bereits dokumentierte Baseline-Fehler auf — die Umgebungsfamilie „vibe-web
ist nicht erreichbar“ (bwrap/tmux), die F22-Altschuld in
`test_project_management`/`test_ap8_github_checkout`, der
umgebungsbedingte `RepositoryVerifyTest` (fehlende `.vibe/project.env` im
Worktree) sowie vorbestehende Hygiene-/Doku-Drift (u. a. `AP21.md`). Keine
dieser Baseline-Stellen wurde verändert.

## Nachtrag (Review-Minor)

Grundlage: `docs/reviews/AP5-Korbat-review-1.md`, Minor-Finding 1 (vier
Teilpunkte). Für die drei verhaltensrelevanten Teilpunkte wurden zuerst
Regressionstests in `tests/unit/test_ap5_korbat_waiting_state.py` ergänzt und
in der Rotphase ausgeführt. Der vierte Teilpunkt (Chronik-Eintrag
`AP5-Korbat` im Array `aenderungen` von `docs/import-manifest.json`) ist eine
reine Metadaten-Ergänzung ohne beobachtbares Verhalten; dafür gibt es bewusst
keinen Testfall.

| Test | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|
| `NovaWaitingSurfaceTest.test_german_dictionary_keeps_the_status_label` | `bin/web/i18n.js` mit `DICTS.en` und `DICTS.de`; der `en`-Eintrag lautet bereits „Waiting for merge“ | Nur den `de`-Bereich ab `de: {` per Regex prüfen; zusätzlich den `en`-Bereich vor dem `de`-Block auf den unveränderten englischen Eintrag prüfen | `DICTS.de` enthält `"Wartet auf Merge": "Wartet auf Merge"`; der `en`-Eintrag bleibt `"Waiting for merge"` |
| `TicketStatusWaitingTest.test_waiting_marker_ends_the_description_section` | TICKETS-Block `- [ ] T1 Titel` mit `  Beschreibung: Bitte warten.` direkt gefolgt von `  WARTET AUF MERGE: PR #6` | `_feedback_scan` + `_parse_entry(..., need_proof=False)` | `description == "Bitte warten."` (Marke beendet den Abschnitt, nicht enthalten); `state == "WARTET AUF MERGE"` |
| `PriorityCommandWaitingTest.test_priority_list_names_a_waiting_package` | `PACKAGE_ORDER="T1,T2"` in `.vibe/project.env`; T1 wartet, T2 offen | `cmd_priority("proj", "list")` mit eingefangenem stdout | Die Ausgabezeile `  T1` nennt „wartet auf Merge“ (Statuszusatz aus `marks`) |

Fehlerfälle: Fall 1 fällt bei deutscher Oberfläche auf den englischen Default
zurück; Fall 2 saugt die Marke in die Beschreibung und zeigt sie im
Ticket-Editor; Fall 3 listet das wartende Paket ohne Zusatz und macht es von
einem offenen Paket nicht unterscheidbar.

### Rotphase (vor der Nachbesserung)

Befehl:

```
python3 -m unittest tests.unit.test_ap5_korbat_waiting_state -v
```

Ergebnis: `Ran 23 tests`, `FAILED (failures=3)`, Exit-Code 1. Ausschließlich
die drei neuen Fälle scheitern; die 20 bereits vorhandenen Fälle bleiben grün.
Die Fehlerursachen sind die erwarteten:

* `test_german_dictionary_keeps_the_status_label`:
  `AssertionError: Regex didn't match: '"Wartet auf Merge"\\s*:\\s*"Wartet auf
  Merge"' not found in '    de: {…'` — das Identitätspaar fehlt im `de`-Block.
* `test_waiting_marker_ends_the_description_section`:
  `'Bitte warten.' != 'Bitte warten.\nWARTET AUF MERGE: PR #6'` — die Marke
  steckt noch in `description` (der `state` war bereits korrekt).
* `test_priority_list_names_a_waiting_package`: Die Ausgabezeile lautet nur
  `  T1`; `(?i)wartet auf merge` fehlt — kein `marks`-Eintrag für den neuen
  Status.

Grenze: Fall 3 nutzt die echte `cmd_priority`-Funktion des CLI-Moduls in einer
temporären VIBE-/HOME-Umgebung (kein Produktionspfad, kein Netz); die
Formatierung wird nur insoweit geprüft, als die Zeile zu T1 den Statustext
enthält — Farb-/Einrückungsdetails sind bewusst nicht festgeschrieben.
Fall 1 ist eine Quelltext-/Strukturassertion, weil `i18n.js` in dieser
Umgebung nicht im Browser ausgeführt wird. Nach der Nachbesserung sind die
Tests erneut auszuführen; die obigen Fälle dürfen dann nicht abgeschwächt
werden.

Es wurden ausschließlich `tests/unit/test_ap5_korbat_waiting_state.py` und
dieser Testbericht geändert; keine Produktionsdatei, kein Prüfskript, keine
Konfiguration und kein Manifest. Es wurde nichts gestaged oder committet.
