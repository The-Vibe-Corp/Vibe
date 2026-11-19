# B16 — Testbericht des unabhängigen Test-Agenten (Rotphase)

**Arbeitspaket:** B16 „Fertiggestellte APs müssen für GitHub vorbereitet und als
PR erstellt werden“ (Art: Bug), Wortlaut aus `FEEDBACK.md`.
**Branch:** `vibe/vibe-B16-1795071980451527111-57043-225`
**Rolle:** Test-Agent — ausschließlich Tests und Test-Unterstützung, kein
Produktionscode, kein Commit.
**Stand:** Tests vor der Implementierung geschrieben und gegen den aktuellen
(unimplementierten) Stand ausgeführt (Rotphase).

**Herkunft der Soll-Semantik:** Arbeitspaket B16, `SPEC.md`, der
Schnittstellenvertrag des Orchestrators sowie die **Nutzerbestätigung vom
19.11.2026**: „Diese Prüfung ist nur verpflichtend, sofern GitHub für das
Projekt aktiviert ist. Ein rein lokales Projekt ohne GitHub benötigt nur einen
erfolgreichen Commit und ggf. das lokale Merge des Feature-Branchs.“ Der
Skip-Pfad ist damit bestätigte Soll-Semantik, kein Kompromiss.

---

## 1. Angelegte und geänderte Dateien

### Neu

| Datei | Zweck |
| --- | --- |
| `tests/unit/test_b16_branch_name.py` | Branch-Namensfunktion `package_branch_name` + Subkommando `branch-name` |
| `tests/unit/test_b16_github_closure.py` | `integration_state`, `complete_package` (4-Tupel), CLI `github-complete` |
| `tests/unit/test_b16_runner_wiring.py` | Echter Läufer: harte GitHub-Schranke, Push, PR, Divergenz, lokaler Skip |
| `tests/unit/test_b16_git_rules.py` | Anforderung D: neue Regeln in `GENERAL_RULES` und allen Vorlagen |

### Geändert (nur Test/Test-Unterstützung)

| Datei | Änderung | Begründung |
| --- | --- | --- |
| `tests/unit/runner_support.py` | `install_runner` kopiert jetzt `vibe_github.py` mit | Mit der harten Schranke würde `github-complete` in jeder Fake-Toolchain ohne dieses Modul mit `SystemExit(1)` scheitern und alle Läufer-Tests blockieren. In Fixtures ohne `GITHUB_ENABLED` meldet das Subkommando bewussten Skip (Exit 0). |
| `tests/unit/test_ap9_runner_github.py` | `complete_package`-Tests auf 4-Tupel und `result`-Schlüssel `branch`/`pr_url` umgestellt | B16 erweitert die Rückgabe bewusst. Pull-, Skip- und Subkommando-Tests bleiben unverändert. |
| `tests/unit/test_ap9_runner_wiring.py` | Modul-Docstring dokumentiert die B16-Semantikänderung; der alte Test `test_a_failing_github_pull_is_only_a_hint_and_does_not_block` wurde zu `test_a_failing_github_pull_is_a_hint_but_completion_blocks` umgeschrieben; manuelles Kopieren von `vibe_github.py` entfällt (jetzt in `install_runner`) | B16 ersetzt die AP9-Abschlusssemantik: Der Pull-Fehlschlag bleibt HINWEIS, der Abschluss blockiert aber. |

Nicht geändert: `bin/**`, `templates/**`, `docs/features/**`, `FEEDBACK.md`,
`TICKETS.md`.

---

## 2. Testfallliste

Legende: V = Vorbedingung, A = Aktion, E = erwartetes Ergebnis.

### 2.1 `tests/unit/test_b16_branch_name.py` — Branch-Regeln (Anforderung A)

Geltungsbereich: Repository-Regeln `feature/...`, konfigurierbares Muster.
Herkunft: B16 + SPEC.md + Schnittstellenvertrag A.

| Testfall | V | A | E |
| --- | --- | --- | --- |
| `test_default_pattern_uses_sanitized_git_user_name` | Projekt mit lokalem `user.name=M0P` | `package_branch_name(project, "B16")` | `feature/m0p/b16` |
| `test_owner_is_kebab_cased_from_a_name_with_spaces_and_uppercase` | `user.name="Max Mustermann"` | wie oben | `feature/max-mustermann/b16` |
| `test_missing_user_name_falls_back_to_vibe` | kein lokales `user.name` (global deaktiviert) | wie oben | `feature/vibe/b16` |
| `test_package_id_is_kebab_cased` | `user.name=Test` | ID `AP_19` | `feature/test/ap-19` |
| `test_configured_pattern_with_slug_uses_the_ticket_title` | `PACKAGE_BRANCH_PATTERN="feature/{owner}/{id}-{slug}"`, FEEDBACK `- [ ] F1 Kurzer Titel` | ID `F1` | `feature/test/f1-kurzer-titel` |
| `test_slug_is_limited_to_24_characters` | langer Tickettitel | ID `F1` | Slug = kebab(Titel) auf 24 Zeichen gekürzt, ohne End-Bindestrich |
| `test_slug_falls_back_to_paket_without_a_title` | kein Tickettitel zu `F1` | ID `F1` | `feature/f1-paket` |
| `test_pattern_without_owner_works` | Muster `pkg/{id}` | ID `B16` | `pkg/b16` |
| `test_explicit_pattern_argument_overrides_the_configuration` | Env-Muster `pkg/{id}` | `pattern="feature/{owner}/{id}"` | `feature/test/b16` |
| `test_unknown_placeholder_is_rejected` | Muster `feature/{foo}/{id}` | Aufruf | `ValueError`, Meldung nennt `{foo}` |
| `test_empty_pattern_is_rejected` | Muster `""` | Aufruf | `ValueError` |
| `test_empty_segment_is_rejected` | Muster `feature//{id}` | Aufruf | `ValueError` |
| `test_segment_ending_on_lock_is_rejected` | Muster `feature/{id}.lock` | Aufruf | `ValueError` |
| `test_uppercase_in_the_result_is_rejected` | Muster `Feature/{id}` | Aufruf | `ValueError` |
| `test_subcommand_reports_an_invalid_pattern_with_exit_one` | Env-Muster `{foo}/{id}` | `branch-name --project --id` | Exit 1, Ausgabe enthält `FEHLT:`, kein Branch |
| `test_subcommand_reports_an_invalid_result_with_exit_one` | Env-Muster `feature//{id}` | wie oben | Exit 1, `FEHLT:` |
| `test_existing_branch_gets_the_suffix_two` | lokaler Branch `feature/test/b16` existiert | Aufruf | `feature/test/b16-2` |
| `test_two_existing_branches_get_the_suffix_three` | `...b16` und `...b16-2` existieren | Aufruf | `feature/test/b16-3` |
| `test_subcommand_prints_exactly_the_branch_name_and_exits_zero` | Projekt mit `user.name=M0P` | Subkommando | Exit 0, stdout exakt eine Zeile `feature/m0p/b16` |
| `test_subcommand_uses_the_configured_pattern` | Env-Muster `pkg/{id}` | Subkommando | Exit 0, `pkg/b16` |

### 2.2 `tests/unit/test_b16_github_closure.py` — GitHub-Abschlussschranke (Anforderung B)

Geltungsbereich: `integration_state`, `complete_package`, CLI. Herkunft: B16 +
Schnittstellenvertrag B.

| Testfall | V | A | E |
| --- | --- | --- | --- |
| `test_detached_head_is_not_ok` | Projekt mit origin, detached HEAD | `integration_state` | `ok=False`, Meldung nicht leer |
| `test_failed_fetch_is_not_ok_and_mentions_credentials` | origin zeigt auf fehlenden Pfad | `integration_state` | `ok=False`, Auth-/Token-Hinweis, kein Token im Text |
| `test_first_publication_without_a_remote_branch_is_ok` | origin-Bare ohne `main` | `integration_state` | `ok=True`, ahead/behind 0 |
| `test_diverged_state_names_the_numbers_and_blocks` | lokaler Commit + Fremd-Commit auf origin | `integration_state` | `ok=False`, Meldung `divergiert`, nennt ahead/behind, endet auf `kein Abschluss auf veraltetem Stand.` |
| `test_outdated_state_uses_the_word_veraltet_and_blocks` | nur Fremd-Commit | `integration_state` | `ok=False`, `veraltet`, ahead 0, gleicher Schlusssatz |
| `test_ahead_only_is_ok` | nur lokaler Commit | `integration_state` | `ok=True`, ahead ≥ 1, behind 0 |
| `test_never_raises_and_always_returns_the_dict_shape` | detached HEAD, fehlender Pfad, Projekt ohne origin | `integration_state` | wirft nie; Dict mit `{ok,message,ahead,behind}` und korrekten Typen |
| `test_diverged_state_blocks_before_push_and_merge_request` | divergierter dev, Branch `feature/x` existiert, REST-Fake | `complete_package` | 4-Tupel, `performed=True`, `ok=False`, `divergiert`, `pr_url=""`, kein Fern-Branch, kein POST |
| `test_outdated_state_blocks_before_push_and_merge_request` | nur behind | `complete_package` | `ok=False`, `veraltet`, Schlusssatz, kein Push, kein POST |
| `test_ahead_only_pushes_and_opens_the_merge_request` | lokaler Commit, `feature/x` | `complete_package` | 4-Tupel, Erfolg, `branch=feature/x`, `pr_url=http://127.0.0.1/pull/42`, Branch gepusht, POST |
| `test_rejected_push_blocks_without_a_merge_request` | pre-receive-Hook lehnt mit GH013 ab | `complete_package` | `performed=True`, `ok=False`, Meldung `GH013`, `pr_url=""`, kein POST, kein Token |
| `test_failed_merge_request_blocks_and_reports_no_pr_url` | REST-Fake 422 | `complete_package` | `performed=True`, `ok=False`, `Merge-Request fehlgeschlagen`, `pr_url=""` |
| `test_never_raises_and_returns_four_elements_with_result_keys` | Projekt ohne origin | `complete_package` | wirft nie; 4 Elemente; `result` mit `branch`, `pr_url` |
| `test_disabled_configuration_skips_with_an_empty_pr_url` | kein `GITHUB_ENABLED`, origin vorhanden | `complete_package` | `(False, True, Meldung, pr_url="")` |
| `test_missing_origin_skips` | `GITHUB_ENABLED`, kein origin | `complete_package` | Skip, `pr_url=""` |
| `test_success_prints_the_delivery_line` | REST-Fake, Branch ausgecheckt | CLI `github-complete` | Exit 0, stdout `ABGABE: Branch feature/cli, Merge-Request http://127.0.0.1/pull/42` |
| `test_skip_prints_merge_request_keine` | GitHub deaktiviert | CLI | Exit 0, `ABGABE: Branch feature/cli, Merge-Request keine` |
| `test_failure_exits_one_and_still_prints_the_delivery_line` | REST-Fake 422 | CLI | Exit 1, `ABGABE: ... Merge-Request keine` trotzdem vorhanden |

### 2.3 `tests/unit/test_b16_runner_wiring.py` — echter Läufer (Anforderung C)

Geltungsbereich: `bin/vibe-run.sh` in Fake-Toolchain. Herkunft: B16 +
Schnittstellenvertrag C.

| Testfall | V | A | E |
| --- | --- | --- | --- |
| `test_successful_run_pushes_feature_branch_and_opens_the_pr` | GitHub aktiv, origin-Bare, REST-Fake | Läufer starten | Exit 0; Bare hat `refs/heads/feature/test/f1`; Report/Log `Geschlossen: F1 — Branch feature/test/f1` und `Merge-Request http://127.0.0.1/pull/42`; `impl-F1.txt` in HEAD; PR-POST |
| `test_rejected_push_blocks_without_merge_or_ticket_update` | origin-Bare mit GH013-pre-receive-Hook | Läufer starten | Exit ≠ 0; BLOCKIERT-Zeile mit `GH013`; nicht gemergt; Ticket `- [ ]`; Report `Blockiert: F1`, kein `Geschlossen: F1`; Arbeitskopie bleibt; kein POST |
| `test_failed_merge_request_blocks_but_the_push_happened` | REST-Fake 422 | Läufer starten | Exit ≠ 0; BLOCKIERT-Zeile mit `Merge-Request fehlgeschlagen`; nicht gemergt; Ticket offen; Bare hat gepushten Branch (beabsichtigtes Teilergebnis); Arbeitskopie bleibt |
| `test_diverged_integration_branch_blocks_with_divergiert` | Fernstand +1, lokaler Commit +1 (divergiert) | Läufer starten | Exit ≠ 0; `HINWEIS: GitHub-Pull …` bleibt; BLOCKIERT-Zeile mit `divergiert`; nicht gemergt; Ticket offen; Arbeitskopie bleibt |
| `test_report_without_github_names_branch_commit_and_keine` | rein lokales Projekt ohne origin, ohne `GITHUB_ENABLED` | Läufer starten | Exit 0; `Geschlossen: F1 — Branch feature/test/f1`; `Merge-Request: keine (GitHub nicht aktiv oder kein origin)`; lokal gemergt (**Nutzerbestätigung 19.11.2026**) |
| `test_github_enabled_but_without_origin_still_closes_locally` | `GITHUB_ENABLED` gesetzt, aber kein origin | Läufer starten | Exit 0; gleicher Report; lokal gemergt (Skip ist Soll-Semantik) |

### 2.4 `tests/unit/test_b16_git_rules.py` — Regeln (Anforderung D)

| Testfall | V | A | E |
| --- | --- | --- | --- |
| `test_general_rules_require_branch_pattern_and_completion_gate` | `bin/vibe` geladen | Abschnitt „Ordnung im Git halten“ prüfen | enthält `feature/`, `PACKAGE_BRANCH_PATTERN`, `Push`, `Merge-Request` |
| `test_all_shipped_templates_contain_the_new_rules` | alle `templates/*/AGENTS.md` | Block prüfen | `GENERAL_RULES` exakt enthalten; Abschnitt nennt dieselben Marker |

### 2.5 Angepasste AP9-Tests

| Testfall | Änderung | Erwartung nach B16 |
| --- | --- | --- |
| `test_ap9_runner_github.CompletePackageTest.*` (5 Tests) | 4-Tupel statt 3-Tupel; `result["pr_url"]`/`result["branch"]` | Fehlschlag-/Erfolgspfade unverändert, Rückgabe erweitert |
| `test_ap9_runner_github.test_complete_package_never_raises` | 4 Elemente + `result`-Schlüssel | wirft nie, 4-Tupel |
| `test_ap9_runner_wiring.test_a_failing_github_pull_is_a_hint_but_completion_blocks` | ersetzt `..._is_only_a_hint_and_does_not_block` | Pull-HINWEIS bleibt; Abschluss blockiert, kein Merge, kein `[x]`, Arbeitskopie bleibt |

---

## 3. Ausgeführte Befehle und Rotphase

Alle Läufe mit isolierter Umgebung (temporäres `VIBE_STATE`,
`GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM=1`, feste
`GIT_IDENTITY`, `NO_PROXY=127.0.0.1,localhost`). Kein echtes `github.com`,
keine Modellaufrufe.

| Befehl | Ergebnis | Bewertung |
| --- | --- | --- |
| `python3 -m unittest tests.unit.test_b16_branch_name -v` | 20 Tests: 16 Errors, 4 Failures | ROT — beabsichtigt |
| `python3 -m unittest tests.unit.test_b16_github_closure -v` | 18 Tests: 11 Errors, 9 Failures (inkl. Subtests) | ROT — beabsichtigt |
| `python3 -m unittest tests.unit.test_b16_runner_wiring -v` | 6 Tests: 6 Failures | ROT — beabsichtigt |
| `python3 -m unittest tests.unit.test_b16_git_rules -v` | 2 Tests: 6 Failures (Subtests) | ROT — beabsichtigt |
| `python3 -m unittest tests.unit.test_ap9_runner_wiring -v` | 3 Tests: 1 Failure, 2 ok | ROT nur für den bewusst umgestellten Test |
| `python3 -m unittest tests.unit.test_ap9_runner_github -v` | 17 Tests: 5 Errors, 1 Failure | ROT nur für 4-Tupel-Umstellung |
| `python3 -m unittest tests.unit.test_runner_package_gates -v` | 12 Tests: OK (136 s) | Baseline grün |
| Kombinierter Abschlusslauf der sechs oben genannten Module | 66 Tests: 27 Failures, 32 Errors (59 rote Einzelergebnisse inkl. Subtests) | ROT — beabsichtigt; 7 Tests bleiben grün (Pull-, Skip- und Subkommando-Pfade) |

### 3.1 `test_b16_branch_name` — entscheidende Zeilen

```
AttributeError: module 'vibe_packages_b16_branch_under_test' has no attribute 'package_branch_name'
```

```
vibe_packages.py: error: argument command: invalid choice: 'branch-name'
(choose from select, preflight, gate, copy-notes, sync-proof, classify,
barrier, mark-blocked, status, github-pull, github-complete)
```

Die Rotphase liegt am fehlenden Symbol und am fehlenden Subkommando, nicht an
der Umgebung: Git-Identität, temporäre Repositories und Kollisionsbranches
werden korrekt angelegt.

### 3.2 `test_b16_github_closure` — entscheidende Zeilen

```
AttributeError: module 'vibe_github_b16_closure_under_test' has no attribute 'integration_state'
```

```
ValueError: not enough values to unpack (expected 4, got 3)
```

```
AssertionError: 'ABGABE: Branch feature/cli, Merge-Request keine' not found in
'Skip: GitHub ist für dieses Projekt nicht aktiv: Übertragung übersprungen\n'
```

```
AssertionError: 'ABGABE: Branch feature/cli, Merge-Request http://127.0.0.1/pull/42'
not found in 'GitHub: Branch feature/cli übertragen; Merge-Request #42: http://127.0.0.1/pull/42\n'
```

### 3.3 `test_b16_runner_wiring` — entscheidende Zeilen

Erfolgsfall (alter `vibe/...`-Branch, kein Push unter `feature/...`):

```
AssertionError: 0 != 128 : Der Branch wurde nicht unter dem
Repository-Namensschema gepusht
```

Blockierte Fälle (alte AP9-Semantik: Lauf endet erfolgreich und mergt):

```
AssertionError: 0 == 0 : Die fehlgeschlagene GitHub-Schranke muss den Lauf blockieren
```

Bericht ohne GitHub (alter Bericht ohne Branch/Commit/PR-Angabe):

```
AssertionError: 'Geschlossen: F1 — Branch feature/test/f1' not found in
'=== Abschlussbericht ===\nGeschlossen: F1\nBlockiert: keine\nOffen: keine\n...'
```

### 3.4 `test_b16_git_rules` — entscheidende Zeile

```
AssertionError: 'feature/' not found in '\n\n- Änderungen auf einem Feature-Branch
umsetzen, ...' : 'feature/' fehlt in GENERAL_RULES (Branch-Regeln)
```

### 3.5 `test_ap9_runner_wiring` — entscheidende Zeile

```
AssertionError: 0 == 0 : Die fehlgeschlagene GitHub-Schranke muss den Lauf blockieren
```

Der Pull-HINWEIS-Teil bleibt bestehen; nur der Abschluss blockiert jetzt.

### 3.6 `test_ap9_runner_github` — entscheidende Zeilen

```
ValueError: not enough values to unpack (expected 4, got 3)
AssertionError: 4 != 3 : (performed, ok, message, result) erwartet
```

Alle Pull-, Skip- und Subkommando-Tests dieses Moduls bleiben grün.

---

## 4. Baseline-Befunde der bestehenden Suiten

Diese Suiten wurden **vor** jeder Implementierung ausgeführt, um den
Ausgangsstand zu dokumentieren.

| Suite | Ergebnis | Einordnung |
| --- | --- | --- |
| `tests.unit.test_runner_package_gates` | 12 Tests **OK** (136 s) | Baseline grün. `install_runner` kopiert nun `vibe_github.py`; Fixtures ohne `GITHUB_ENABLED` melden Skip und bleiben unverändert grün. |
| `tests.unit.test_ap06_github` | 54 Tests, **1 Failure** | Vorbestehend und unabhängig von B16: `test_cli_push_without_any_remote_reports_the_problem` erwartet `Remote` in der Ausgabe, git liefert stattdessen `fatal: 'origin' does not appear...`. Die für Anforderung D relevanten Tests (`CommitMessageRuleTest`, `test_all_shipped_templates_contain_the_same_commit_rule`) sind **grün**. |
| `tests.unit.test_project_management` | 36 Tests, **8 Failures, 17 Errors** | Vorbestehend und unabhängig von B16: `bin/vibe:2596` wirft `NameError: name 'agent' is not defined` in `cmd_init`; zusätzlich fehlt `AGENTS.md` im Repository-Wurzelverzeichnis und Template-Test-Agent-Regeln weichen ab. Die für D relevanten Blockprüfungen (`GENERAL_RULES` exakt in Vorlagen, Marker, Cleanup-/Coding-/Effizienzregeln) sind **grün**. |

**Wichtig:** Diese Baseline-Fehler liegen außerhalb des Test-Auftrags (kein
`bin/**`-Eingriff erlaubt). Sie sind keine Folge der B16-Teständerungen und
müssen vor einer Gesamtabnahme separat geklärt werden.

---

## 5. Grenzen des Nachweises

- **Kein echtes `github.com`:** Git läuft ausschließlich gegen lokale
  Bare-Repositories über `file://`; die REST-API ist ein Fake auf
  `127.0.0.1`. Ein reales GitHub-Verhalten (Rechte, Branch-Protection,
  GH013 im echten Dienst) wird nicht geprüft.
- **GH013 wird nachgebildet:** Der pre-receive-Hook erzeugt eine
  GH013-ähnliche Meldung. Das beweist die Fehlerbehandlung, nicht die echte
  GitHub-Ablehnung.
- **Branch-Name aus Tickettitel:** Der Slug wird aus `TICKETS.md`/`FEEDBACK.md`
  gelesen. Die genaue Titel-Extraktion ist Vertragsannahme; die Tests prüfen
  das beobachtbare Ergebnis, nicht die interne Parser-Implementierung.
- **Läufer-Tests** nutzen die Fake-Toolchain (`runner_support`), nicht die
  produktive Installation. Agentenaufrufe sind Attrappen; es gibt keine
  Modellaufrufe.
- **Rotphase** belegt fehlendes Verhalten, nicht die spätere
  Implementierungsqualität. Nach der Implementierung ist ein erneuter Lauf
  aller genannten Module erforderlich.
- **Nicht ausgeführt:** vollständige Testsuite und Browser-Abnahme (für B16
  nicht einschlägig, da keine UI-Fläche geändert wird).

---

## 6. Zusammenfassung für den Orchestrator

- 4 neue Testmodule, 3 Testdateien angepasst, `runner_support` um
  `vibe_github.py` ergänzt.
- Alle neuen und umgestellten Tests sind **rot** und scheitern am fehlenden
  B16-Verhalten (`package_branch_name`, `branch-name`, `integration_state`,
  4-Tupel, `ABGABE`-Zeile, harte Schranke, Berichtsformat, neue Regeln).
- Die unverändert gültigen AP9-Pull- und Subkommando-Tests bleiben grün; nur
  die bewusst ersetzte Abschlusssemantik ist rot.
- Baseline `test_runner_package_gates` grün; die zwei genannten
  Regel-Suiten haben vorbestehende, B16-unabhängige Fehler (siehe Abschnitt 4).
- Der lokale Skip-Pfad ist durch zwei ausdrückliche Läufer-Tests als
  Soll-Semantik abgesichert (**Nutzerbestätigung 19.11.2026**).

---

## 7. Nachtrag Grünphase (Fixture-Korrektur nach Implementierung)

Nach der B16-Implementierung war in `tests/unit/test_ap9_runner_wiring.py`
genau ein Test rot:

`PullWiringTest.test_a_successful_pull_updates_the_base_before_the_worktree`
nutzte `GITHUB_API="http://127.0.0.1:9"` (bewusst toter Port). Diese Fixture
setzte die alte AP9-Hinweis-Semantik voraus: Damals war ein fehlgeschlagener
Merge-Request nur ein HINWEIS. Unter B16 blockiert die harte Schranke zu
Recht, weil ohne erreichbaren Merge-Request-Endpunkt kein Abschluss möglich
ist. Der fachliche Kern des Tests (erfolgreicher `github-pull` zieht den
Fernstand **vor** Arbeitskopie/Paketbase; Elternteil des ältesten
F1-Commits == gezogener Fernstand) war davon unberührt.

**Korrektur:** Der Test startet jetzt einen `RestFakeServer`
(`from tests.unit.test_ap9_runner_github import RestFakeServer`) mit
`self.addCleanup(server.close)` und setzt `GITHUB_API=<server.base>` statt des
toten Ports. Alle ursprünglichen Assertions bleiben unverändert: keine
`HINWEIS: GitHub-Pull`-Zeile und Paketbase-Elternteil == gezogener
Fernstand. Keine Schranke wurde abgeschwächt; der Abschluss läuft mit Push
und Merge-Request erfolgreich durch (Exit 0).

**Erneuter Lauf:**

```
python3 -m unittest tests.unit.test_ap9_runner_wiring -v
Ran 3 tests in 20.052s
OK
```

**Nachweis, dass die B16-Abnahme unberührt bleibt:**

```
python3 -m unittest tests.unit.test_b16_runner_wiring -v
Ran 6 tests in 9.667s
OK
```

