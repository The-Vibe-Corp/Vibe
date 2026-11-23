# AP7-Korbat — Bericht des unabhängigen Test-Agenten (Runde 4)

> Abschnitte 1–10 dokumentieren Runde 3 (Rotphase, Testvorbereitung).
> Abschnitt 11 dokumentiert Runde 4: Behebung eines Defekts in der eigenen
> Testdatei und den Browserbefund.

- **Ticket:** AP7-Korbat (GitHub #41, „Rework verify.sh logic“, T-V13, T-V16–T-V21)
- **Rolle:** unabhängiger Test-Agent; ausschließlich Tests und dieser Bericht
- **Worktree:** `/var/log/custom/vibe-dev/worktrees/vibe-AP7-Korbat-0h9IlY`
- **Branch:** `feature/korbat/ap7-korbat` (nicht gewechselt)
- **Ausgangscommit:** `d4c24ee` („AP23: feature/m0p/ap23 (#38)“)
- **Ausgangsstand Produktion:** unverändert. `git diff --stat d4c24ee -- templates bin scripts` ist leer; nur Testdateien sind geändert/neu.
- **Quellen der Fälle:** `TICKETS.md` (AP7-Korbat inkl. Klarstellungen), `/opt/custom/vibe-dev/workspaces/vibe-audit/docs/features/AP12.md` (T-V13, T-V16–T-V21), Design-Brief `AP7-Korbat-design.md` und die Orchestrator-Entscheidungen D1–D3. Die Fälle sind **nicht** aus einem Implementierungsdiff abgeleitet.
- **Grenzen dieser Runde:** keine Produktionsdateien, keine Commits, kein Branch-Wechsel, keine Modell-/MCP-/Netzaufrufe, keine produktiven Pfade oder produktives `HOME`/`VIBE`. Alle Fixture-Projekte liegen in temporären Verzeichnissen.

---

## 1. Angelegte Testdateien (neu)

| Datei | Zweck |
| --- | --- |
| `tests/unit/ap7_verify_support.py` | Gemeinsame Fixturen (kein Testmodul): temporäre Projekte, Aufruf von `scripts/verify.sh`/`scripts/verify.py` mit bereinigter `VIBE_*`/`VERIFY_*`-Umgebung, Baseline-Schreib-/Lesehelfer, feste Grün-/Rot-/Anders-Rot-Testmodule. |
| `tests/unit/test_ap7_korbat_verify.py` | T-V13/T-V16: Selbstreferenz- und Tiefenwächter, Frontend/Engine/Shim-Architektur, `full` baut den Testlauf selbst, `package` führt `VERIFY_QUICK` aus, CLI-Vertrag. 24 Fälle. |
| `tests/unit/test_ap7_korbat_baseline.py` | T-V17–T-V19: Dreizustands-Auswertung, Exit 0/3/6/7, Env-Label exklusiv, `--write-baseline`, Ratchet/effektives Minimum, `--baseline`-Präzedenz. 20 Fälle. |
| `tests/unit/test_ap7_korbat_report.py` | `scripts/run-tests-parallel.py --report PATH`: JSON-Bericht (Module, `total_tests`, `error_class`/`error_message`), Textausgabe/Exitcodes unverändert. 6 Fälle. |
| `tests/unit/test_ap7_korbat_rules.py` | AGENTS-Regeln (Baseline-Disziplin, Effizienz) in `GENERAL_RULES`, allen fünf Vorlagen und der Repository-`AGENTS.md`; committed Baseline `tests/verify-baseline.json` (Schema v1, keine Umgebungsdetails). 13 Fälle. |
| `tests/unit/test_ap7_korbat_runner.py` | T-V21: Hash-/Diff-Wächter nach dem Agentenlauf (`project.env`, `.vibe/verify-baseline`) über den echten `bin/vibe-run.sh` in einer Fake-Toolchain. 5 Fälle. |

## 2. Geänderte Bestandsdateien (alle Änderungen mit Begründung)

| Datei | Änderung | Begründung |
| --- | --- | --- |
| `tests/unit/test_verify_script.py` | `VerifyFullTest`/`VerifyPackageTest` auf die neue Semantik umgestellt: `full` liest `VERIFY_FULL` nicht mehr als Befehl, sondern baut den Lauf über den eingebauten Läufer aus `VERIFY_TESTS`; `package` führt `VERIFY_QUICK` aus; Zählung über die strukturierte `VERIFY_RESULT:`-Zeile; `VERIFY_TEST_PATTERN` entfällt; `package` verlangt `VERIFY_QUICK` (nicht `VERIFY_PACKAGE`). Unverändert bleiben Nachweiszwang, Exit 6, Testdatei-Prüfung, `VERIFY_MIN_TESTS`, Isolations-/Usage-/Temp-/Tmux-Fälle. | T-V16/T-V19: Ein Nachweiszwang oder eine Zählung, die an eine abgeschaffte Befehlsvariable gebunden ist, wäre nach AP7 nicht mehr erfüllbar. Die Fachlichkeit (Nachweis, Zählung, Ausführung) bleibt dieselbe, nur gegen die neue Schnittstelle. Ein Kommentar im Modulkopf nennt die Umstellung ausdrücklich. |
| `tests/unit/test_project_management.py` | `TemplateRulesTest.VERIFY_EFFICIENCY_RULE`: Marker `VERIFY_PACKAGE`/`VERIFY_FULL` durch die design-fixierten Begriffe `verify.sh`, `quick\|package\|full`, `Prüfschnittstelle` ersetzt. Übrige Marker (Stufung, „genau einmal“, „vor der Abnahme“, „Nachweisumfang“, „abgeschwächt“) unverändert. | T-V19/D3: Die Sektion „Effizienz der Prüfungen“ nennt nach Design keine Befehlsvariablen mehr, sondern `verify.sh` als einzige Schnittstelle. Sonst würde die Vorlagenprüfung eine überholte Formulierung erzwingen. |
| `tests/unit/test_verify_api_package.py` | Paketmodus-Fall prüft die neue Schnittstelle; Fixture setzt `VERIFY_PACKAGE` auf die dokumentierte Nutzer-Verdrahtung `bash <repo>/scripts/verify.sh package --project <fixture>` (Runde-3-Korrektur). | Das Dashboard führt laut `bin/vibe.py::verify_command` den Wert von `VERIFY_PACKAGE` unverändert aus. Nur mit der im Design (T-V20) dokumentierten Nutzer-Verdrahtung erreicht der Klick die Engine; die Erwartung „Protokoll nennt `VERIFY_QUICK`“ ist damit ohne Änderung des Dashboards erfüllbar. Keine Assertion abgeschwächt: zusätzlich bleibt `VERIFY_PACKAGE_MARKER`/`VERIFY_FULL_MARKER` als Negativprobe verboten. |
| `tests/browser/test_f31_verify_package_ui.py` | Fixture wie oben auf die Wrapper-Verdrahtung umgestellt; die frühere Negativprobe `assertNotIn("alter-paket-befehl")` durch `assertIn("verify.sh")` ersetzt (Nachweis, dass der Knopf über den Wrapper lief); `assertNotIn("full-pruefung-marker")` bleibt. | Gleiche Ursache wie oben: Der alte Fixture-Wert `VERIFY_PACKAGE="echo alter-paket-befehl"` wäre nach AP7 unverändert ausgeführt worden, der erwartete `VERIFY_QUICK`-Marker hätte nie erscheinen können. Die Prüfintention (Paketknopf zeigt die Ausgabe der einzigen Prüfschnittstelle) bleibt erhalten. |
| `tests/unit/runner_support.py` | Nachgebildeter Agent um `FAKE_TAMPER` erweitert (`append`/`rewrite`/`create` auf `.vibe/<datei>`), inkl. `chmod`, weil der Transport best effort `0444` setzt. Ohne `FAKE_TAMPER` unverändert. | T-V21 braucht einen Agenten, der das Paket regulär abschließt und dabei eine transportierte Datei verändert; sonst wäre ein Block nicht eindeutig dem Wächter zuzuordnen. |
| `tests/unit/test_ap5_korbat_project_env_transport.py` | Drei neue Fälle für den zusätzlichen Einweg-Transport von `.vibe/verify-baseline` (1:1, best effort read-only, idempotenter Exclude-Eintrag, nie zurückgeschrieben). Die sechs Bestandsfälle bleiben unverändert. | Design „Transport-Erweiterung (vibe_packages.py)“. |

## 3. Rotphase (Runde 3, nach Fixture-Fix)

### 3.1 Befehl (identisch zum geplanten Grünlauf)

```bash
python3 -m unittest \
  tests.unit.test_ap7_korbat_verify \
  tests.unit.test_ap7_korbat_baseline \
  tests.unit.test_ap7_korbat_report \
  tests.unit.test_ap7_korbat_rules \
  tests.unit.test_ap7_korbat_runner \
  tests.unit.test_ap5_korbat_project_env_transport \
  tests.unit.test_verify_script \
  tests.unit.test_project_management -v
```

Ausführung gegen den **unveränderten** Ausgangsstand (Produktionscode noch nicht implementiert).
Vollständiges Protokoll: `/tmp/opencode/vibe-sandbox/vibe-c7188db792/tmp/opencode/round3-redphase.log`
(Runde-2-Protokoll vor dem Fixture-Fix: `.../redphase.log`.)

### 3.2 Ergebnis

```
Ran 147 tests in 40.335s

FAILED (failures=89, errors=1)
```

Exit 1. `failures=89` sind **89 Fehlschlag-Einträge** bei **85 auf Testebene fehlgeschlagenen Tests**: Der Fall
`test_ap7_korbat_rules.GeneralRulesTest.test_all_templates_carry_the_baseline_discipline` läuft als `subTest`
über fünf Vorlagen und erzeugt fünf Einträge. Auf Testebene gibt es **0 ERROR** in den neuen Modulen;
der einzige ERROR ist der vorbestehende, unten klassifizierte Fall
`test_project_management.TemplateRulesTest.test_shipped_test_agent_template_is_complete`.

### 3.3 Zusammenfassung je Modul

| Modul | Tests | bestanden | fehlgeschlagen (Testebene) | ERROR | Einordnung |
| --- | ---: | ---: | ---: | ---: | --- |
| `test_ap7_korbat_verify` | 24 | 5 | 19 | 0 | AP7-Neuverhalten (T-V13/T-V16). Grün: 3 Shim-Äquivalenzfälle (alter `verify.py` existiert noch), 2 Usage-Fälle (alter Parser lehnt unbekannte Option/fehlenden Wert schon mit Exit 2 ab). |
| `test_ap7_korbat_baseline` | 20 | 0 | 20 | 0 | AP7-Neuverhalten (T-V17–T-V19). Kein Fall kann ohne Engine/Baseline grün sein. |
| `test_ap7_korbat_report` | 6 | 0 | 6 | 0 | AP7-Neuverhalten (`--report` fehlt im Läufer). |
| `test_ap7_korbat_rules` | 13 | 0 | 13 | 0 | AP7-Neuverhalten (Regelblock, Vorlagen, committed Baseline fehlen). |
| `test_ap7_korbat_runner` | 5 | 3 | 2 | 0 | AP7-Neuverhalten (T-V21). Grün sind die drei Negativfälle („blockiert nicht“), weil ein fehlender Wächter sie trivial erfüllt; rot sind die beiden Tamper-Positivfälle. |
| `test_ap5_korbat_project_env_transport` | 9 | 6 | 3 | 0 | 3 neue AP7-Fälle rot; die 6 Bestandsfälle (project.env-Transport) grün. |
| `test_verify_script` | 34 | 21 | 13 | 0 | AP7-Semantik (`full`/`package`); alle 13 Fehlschläge stammen aus den umgestellten Fällen. |
| `test_project_management` | 36 | 26 | 9 | 1 | 3 AP7-Fälle (Effizienz-Sektion/`verify.sh`) + 6 vorbestehende + 1 vorbestehender ERROR (siehe §4). |
| **Summe** | **147** | **61** | **85** | **1** | |

Auszug (Kopf und Fehlerbild der neuen Module):

```
test_engine_module_exists_and_frontend_uses_it (...) ... FAIL
AssertionError: False is not true : scripts/verify_engine.py fehlt

test_quick_pointing_to_this_verify_sh_is_rejected (...) ... FAIL
AssertionError: 0 != 3 : OK: Prüfung 'quick' erfolgreich. (Exit 0)
   -> Der Selbstaufruf lief durch; der Wächter fehlt (B1).

test_known_failure_matching_the_baseline_is_baseline_ok (...) ... FAIL
AssertionError: 2 != 0 ... FEHLT: Unbekannte Option: --env

test_package_runs_verify_quick_instead_of_package_or_full (...) ... FAIL
AssertionError: 'quick-pruefung' not found in ... paket-pruefung ... (Exit 0)

ERROR: test_shipped_test_agent_template_is_complete
FileNotFoundError: .../templates/common/.opencode/agents/test-agent.md
```

Einordnung: **Jeder rote AP7-Fall scheitert an fehlendem Neuverhalten oder an einer abgeschafften
Schnittstelle**, nicht an defekter Umgebung. Es gibt in den neuen Modulen keinen `FileNotFoundError`,
`ImportError`, Syntax- oder Fixture-ERROR mehr. Der eine verbleibende ERROR ist vorbestehend (§4.1).

### 3.4 Fixture-Fix dieser Runde

`test_ap7_korbat_rules.CommittedBaselineManifestTest.test_manifest_contains_no_environment_details_or_secrets`
liest die committed Baseline erst nach einer expliziten `assertTrue(MANIFEST.is_file(), ...)`-Prüfung.
Vorher brach der Fall bei fehlender Datei mit `FileNotFoundError` als ERROR ab; jetzt ist es ein sauberer
FAIL mit der Meldung `tests/verify-baseline.json fehlt (kanonische Baseline)`. Die geforderte Datei
(Schema v1: `version=1`, `min_tests=2000`, `envs={}`) bleibt unverändert gefordert
(`test_manifest_has_schema_v1_and_the_initial_values`); es wurde keine Assertion abgeschwächt.

Verifikation (siehe §8): `python3 -m unittest tests.unit.test_ap7_korbat_rules -v` →
`Ran 13 tests`, `FAILED (failures=17)`, **0 ERROR**; 17 Einträge = 13 Test-Fehlschläge + 4 zusätzliche
`subTest`-Einträge der fünf Vorlagen.

## 4. Vorbestands- und Umgebungsklassifizierung (nur lesend geprüft)

### 4.1 Nachweise am Ausgangscommit `d4c24ee`

| Prüfung | Ergebnis |
| --- | --- |
| `git cat-file -e d4c24ee:templates/common/.opencode/agents/test-agent.md` | **Exit 128** (Pfad existiert nicht) |
| `git ls-tree -r --name-only d4c24ee -- templates/common` | nur `FEEDBACK.md`, `TICKETS.md`, `opencode.json` |
| `git cat-file -e d4c24ee:templates/{android,docker,generic,rebuild,web}/AGENTS.md` | Exit 0 (alle vorhanden) |
| `git cat-file -e d4c24ee:templates/{android,docker,generic,rebuild,web}/.vibe/project.env` | Exit 0 (alle vorhanden) |
| `git show d4c24ee:templates/<typ>/.vibe/project.env \| grep -c '^TESTER='` | 0 in allen fünf Vorlagen |
| `TEST_AGENT_TEMPLATE` in `bin/vibe` (Basis **und** Arbeitsstand) | kommt nicht vor (`grep -c` = 0) |
| `git show d4c24ee:tests/unit/test_project_management.py` | enthält die später fehlschlagenden Tests unverändert (u. a. `test_shipped_test_agent_template_is_complete`, `test_init_adds_the_test_agent_and_tester_to_an_existing_project`, `test_all_shipped_project_templates_configure_the_tester`) |
| `git diff --stat d4c24ee -- templates bin scripts` | leer → die geprüften Produktionsdateien sind exakt der Ausgangsstand |
| `git check-ignore -v AGENTS.md` | `.gitignore:23:/AGENTS.md` → Repository-`AGENTS.md` ist **nicht versioniert** (Harness-Artefakt) |

Zusätzlich dokumentiert `docs/features/AP6-Korbat.md` §4.2 `test_project_management` bereits als
Vorbestand am früheren Ausgangscommit (`TESTER`/Test-Agent-Vorlagen-Drift nach `35233ff`).

### 4.2 Klassifizierung der `test_project_management`-Fehlschläge

**Vorbestehend / umgebungsbedingt (keine AP7-Regression, bleiben im Grünlauf rot):**

1. `TemplateRulesTest.test_all_shipped_project_templates_contain_the_test_agent_rule` — `TESTER` fehlt in den Vorlagen.
2. `TemplateRulesTest.test_all_shipped_project_templates_configure_the_tester` — `TESTER=test-agent` fehlt in allen fünf `.vibe/project.env`.
3. `TemplateRulesTest.test_general_rules_require_an_independent_test_agent` — `TESTER` fehlt in `GENERAL_RULES`.
4. `TemplateRulesTest.test_repository_agents_file_contains_the_test_agent_rule` — `TESTER` fehlt in der (nicht versionierten) Repository-`AGENTS.md`.
5. `TemplateRulesTest.test_shipped_test_agent_template_is_complete` — **ERROR**, weil `templates/common/.opencode/agents/test-agent.md` fehlt **und** `cli.TEST_AGENT_TEMPLATE` nicht existiert; beides schon bei `d4c24ee` nicht vorhanden.
6. `InitTest.test_init_applies_a_new_template_type_without_code_changes` — erwartet `TESTER=test-agent`, `init` schreibt ihn nicht.
7. `InitTest.test_init_adds_the_test_agent_and_tester_to_an_existing_project` — erwartet angelegte `test-agent.md` und `TESTER=test-agent`; beides fehlt im Ausgangsstand.

Das sind 6 Fehlschläge + 1 ERROR. Sie gehören zur in AP6 dokumentierten T-BR7/TESTER-Familie und sind
**nicht** Teil von AP7 (Design-Brief: keine Test-Agent-Vorlagen-Implementierung). Ein Grünlauf kann sie
nicht beseitigen, ohne fremden Umfang zu implementieren.

**AP7-Neuverhalten (sollen im Grünlauf grün werden):**

8. `TemplateRulesTest.test_general_rules_require_tiered_verification` — `GENERAL_RULES` nennt noch `VERIFY_PACKAGE`/`VERIFY_FULL` statt `verify.sh`/`quick|package|full`/`Prüfschnittstelle`.
9. `TemplateRulesTest.test_all_shipped_project_templates_contain_the_verification_efficiency_rule` — Vorlagen tragen noch die alte Sektion.
10. `TemplateRulesTest.test_repository_agents_file_contains_the_verification_efficiency_rule` — die Repository-`AGENTS.md` trägt noch die alte Sektion (siehe aber §4.3).

### 4.3 Umgebungsbedingte Abhängigkeit von `AGENTS.md`

`AGENTS.md` im Repository-Wurzelverzeichnis ist **gitignored** (`.gitignore:23`) und existiert nur im
Harness. Drei Fälle lesen sie:

- `test_ap7_korbat_rules.GeneralRulesTest.test_repository_agents_file_carries_the_baseline_discipline` (neu),
- `test_project_management.TemplateRulesTest.test_repository_agents_file_contains_the_verification_efficiency_rule` (Bestand),
- `test_project_management.TemplateRulesTest.test_repository_agents_file_contains_the_test_agent_rule` (Bestand, ohnehin vorbestehend rot).

Konsequenz: Eine Änderung an `GENERAL_RULES` allein macht diese Fälle nicht grün; der verwaltete Block
muss auf der Platte aktualisiert werden. Der Läufer tut das beim Start über
`ensure_general_rules(p)` (`bin/vibe`, vor dem Agentenstart), sofern `AGENTS.md` keine nicht committeten
Änderungen hat. Diese Aktualisierung ist **nicht commitfähig**; die belastbare, versionierte Abdeckung
liefert `GENERAL_RULES` (in `bin/vibe`) plus die fünf Vorlagen. Die Fälle sind bewusst nicht auf `skip`
gestellt (kein Abschwächen); sie bleiben als Umgebungsabhängigkeit dokumentiert.

## 5. Testfälle (Name · Vorbedingung · Aktion · erwartetes Ergebnis)

Kürzel: Fixture-Projekte liegen immer in einem temporären Verzeichnis mit eigenem `HOME`/`VIBE`;
`clean_environment` entfernt geerbte `VIBE_*`/`VERIFY_*` und `TMUX`. „R“ = rot in der Rotphase erwartet,
„G“ = grün (Regressionsschutz), „V“ = vorbestehend rot (nicht AP7).

### 5.1 `tests/unit/test_ap7_korbat_verify.py` (24)

| Fall | Vorbedingung | Aktion | Erwartung |
| --- | --- | --- | --- |
| `ArchitectureTest.test_engine_module_exists_and_frontend_uses_it` | `scripts/verify.sh`, `scripts/verify_engine.py` | Dateien lesen | Engine existiert; `verify.sh` verweist auf `verify_engine.py` (T-V16). R |
| `ArchitectureTest.test_verify_py_is_a_delegating_compat_shim` | `scripts/verify.py` | Quelle lesen | Shim delegiert per `os.execv` an `verify_engine.py`, keine eigene Logik. R |
| `ShimCompatibilityTest.test_verify_py_and_verify_sh_agree_on_unknown_mode` | Fixture-Projekt | beide Aufrufer mit Modus `unbekannt` | beide Exit 2. G |
| `..._agree_on_missing_configuration` | leeres Projekt ohne `.vibe/project.env` | beide Aufrufer `quick` | beide Exit 3, Meldung nennt `project.env`. G |
| `..._agree_on_a_successful_quick_run` | `VERIFY_QUICK="true"` | beide Aufrufer `quick` | beide Exit 0. G |
| `SelfReferenceGuardTest.test_quick_pointing_to_this_verify_sh_is_rejected` | `VERIFY_QUICK` ruft dieses `verify.sh` | `quick` (Zeitlimit 120 s) | Exit 3, Meldung nennt `VERIFY_QUICK`, „Rekursion“, `verify.sh`; kein zweiter Lauf (B1). R |
| `..._with_relative_self_path_is_rejected` | `VERIFY_QUICK` enthält `scripts/verify.sh` relativ | `quick` | Exit 3 (Wächter löst relativ gegen Projektwurzel/cwd auf). R |
| `..._with_unresolvable_verify_basename_is_rejected` | `VERIFY_QUICK` nennt `gibtsnicht/verify.sh` | `quick` | Exit 3 (fail-safe trotz nicht auflösbarem Token). R |
| `..._pointing_to_verify_py_is_rejected` | `VERIFY_QUICK` ruft `scripts/verify.py` | `quick` | Exit 3, Meldung nennt `verify.py`. R |
| `..._pointing_to_verify_engine_is_rejected` | `VERIFY_QUICK` ruft `verify_engine.py` | `quick` | Exit 3, Meldung nennt `verify_engine.py`. R |
| `..._depth_two_is_rejected_as_recursion` | `VIBE_VERIFY_DEPTH=2`; `VERIFY_QUICK` legt Markerdatei an | `quick` | Exit 3, Meldung nennt `VIBE_VERIFY_DEPTH` und Tiefe/Rekursion; Marker fehlt. R |
| `..._depth_one_runs_normally_and_increments_the_child_depth` | `VIBE_VERIFY_DEPTH=1`; Beobachtermodul druckt Tiefe | `quick` | Exit 0; Kind sieht Tiefe 2. R |
| `FullModeTest.test_full_ignores_verify_full_as_a_command_and_hints` | `VERIFY_FULL="echo AP7-JUNK-FULL"`, `VERIFY_TESTS=tests` grün | `full` | Exit 0; Junk-Marker fehlt; Hinweis auf nicht gelesenes `VERIFY_FULL` erscheint (kein Fehler). R |
| `..._runs_the_built_in_parallel_runner` | `VERIFY_TESTS=tests` grün | `full` | Exit 0; Ausgabe enthält Modulblock `--- tests.test_gut ---`, `Gesamt:` und den Grünmarker. R |
| `..._does_not_recurse_when_verify_full_names_verify_sh` | `VERIFY_FULL="bash scripts/verify.sh full"`, `VERIFY_TESTS` grün | `full` (Zeitlimit) | Exit 0; genau eine `Gesamt:`-Zeile; kein Selbstaufruf. R |
| `..._verify_test_pattern_is_not_evaluated` | `VERIFY_TEST_PATTERN="("` (ungültig), Tests grün | `full` | Exit 0; Zählung aus dem Läuferbericht, Muster irrelevant. R |
| `PackageModeTest.test_package_does_not_execute_verify_package_as_a_command` | `VERIFY_QUICK="true"`, `VERIFY_PACKAGE` würde Markerdatei anlegen | `package` | Exit 0; Markerdatei fehlt → `VERIFY_PACKAGE` wird nicht als Befehl ausgeführt. R |
| `CliContractTest.test_help_lists_the_new_options` | — | `--help` | Exit 0; Hilfe nennt `--tests`, `--jobs`, `--timeout`, `--baseline`, `--env`, `--min-tests`, `--write-baseline`. R |
| `..._tests_option_overrides_the_configured_specs` | `VERIFY_TESTS=tests_rot` (rot), `tests_gut` grün daneben | `full --tests tests_gut` | Exit 0; nur grünes Modul läuft, `tests.test_rot` fehlt. R |
| `..._multiple_tests_options_run_each_directory` | zwei Marker-Testverzeichnisse | `full --tests tests_a --tests tests_b` | Exit 0; beide Marker erscheinen. R |
| `..._numeric_and_label_options_are_accepted` | grüne Tests | `full --tests … --jobs 1 --timeout 60 --min-tests 1 --env lichter` | Exit 0 (Optionen geparst). R |
| `..._baseline_option_is_accepted` | Baseline-Datei mit `envs={}`, `min_tests=1`; grüne Tests | `full --tests … --baseline <datei>` | Exit 0. R |
| `..._unknown_option_is_a_usage_error` | — | `full --quatsch` | Exit 2. G |
| `..._option_without_value_is_a_usage_error` | — | je `--tests/--jobs/--timeout/--baseline/--env/--min-tests` ohne Wert | Exit 2 (`subTest` je Option). G |

### 5.2 `tests/unit/test_ap7_korbat_baseline.py` (20)

| Fall | Vorbedingung | Aktion | Erwartung |
| --- | --- | --- | --- |
| `BaselineTriStateTest.test_green_run_exits_0_and_reports_the_result` | zwei grüne Tests, keine Baseline | `full` | Exit 0; `VERIFY_RESULT:`-Zeile mit `mode=full`, `tests=2`. R |
| `..._known_failure_matching_the_baseline_is_baseline_ok` | rotes Modul; lokale Baseline per `--write-baseline` erzeugt und als committed hinterlegt; Signatur `sha256:…` | `full --env lichter` | Exit 0; `BASELINE-OK`; `tests.test_rot` aufgelistet; `VERIFY_RESULT` mit `baseline_ok=1 env=lichter`. R |
| `..._new_red_module_not_in_the_baseline_exits_7` | committed Sektion `lichter` ohne Fehler; ein Modul rot | `full --env lichter` | Exit 7; rotes Modul im Diff; kein `BASELINE-OK`. R |
| `..._changed_signature_of_a_known_module_exits_7` | Modul in Baseline; danach andere Fehlerklasse/-meldung | `full --env lichter` | Exit 7 (nur Modulname reicht nicht). R |
| `..._count_below_the_minimum_exits_6` | zwei grüne Tests, committed `min_tests=50` | `full --env lichter` | Exit 6. R |
| `..._new_red_and_count_below_the_minimum_exits_7` | `min_tests=50` **und** neues rotes Modul | `full --env lichter` | Exit 7 (Regression gewinnt gegen Exit 6). R |
| `..._invalid_baseline_json_exits_3` | `tests/verify-baseline.json` ist kein JSON | `full` | Exit 3; Meldung nennt `verify-baseline`. R |
| `..._invalid_baseline_schema_exits_3` | Baseline mit `version=2` | `full` | Exit 3 (Schemafehler, nie still ignorieren). R |
| `..._package_mode_does_not_consult_the_baseline` | `VERIFY_PACKAGE_TESTS=tests`; Modul steht als bekannt rot in passender committed Baseline | `package --env lichter` | Exit 5; Paketmodus kennt keine Baseline (Fehlerfreiheit gilt). R |
| `EnvLabelTest.test_verify_env_from_project_env_selects_the_section` | `VERIFY_ENV="lichter"` in project.env; Baseline aus diesem Label | `full` ohne `--env` | Exit 0; `BASELINE-OK` (Label aus project.env). R |
| `..._similar_label_does_not_match` | Baseline kennt nur `lichter`; Lauf `lichter-2`; rotes Modul | `full --env lichter-2` | Exit 7; kein `BASELINE-OK`; Meldung nennt `--write-baseline`. R |
| `..._green_run_with_mismatched_label_still_exits_0` | Baseline für fremdes Label mit Fehler; alle Tests grün | `full --env lichter` | Exit 0 (ohne Fehlschläge keine Regression). R |
| `..._write_baseline_preserves_other_env_sections` | lokale Baseline mit Sektion `anderes`; Lauf mit rotem Modul und `--env lichter` | `full --env lichter --write-baseline` | **D2:** Exit 7 (Mismatch + Fehler ändert das Urteil nicht); lokale Datei wird geschrieben; `lichter` ergänzt; `anderes` unverändert; `min_tests` bleibt. R |
| `..._write_baseline_refuses_to_lower_the_minimum` | lokale `min_tests=3`; Aufruf `--min-tests 1` | `full --write-baseline --min-tests 1` | Exit 3; Datei bleibt bei `min_tests=3`. R |
| `..._write_baseline_marks_the_local_file_as_unversioned` | Lauf mit `--write-baseline` | Ausgabe prüfen | nennt `.vibe/verify-baseline`, „unversioniert/ignoriert“, „Merge-Request“. R |
| `..._baseline_option_overrides_the_committed_manifest` | committed Sektion ohne Fehler; separate Datei passt exakt zu Label+Signatur; lokale Datei entfernt | `full --env lichter --baseline <datei>` | Exit 0; `BASELINE-OK` (Option ersetzt die Manifest-Dateien). R |
| `RatchetTest.test_committed_min_tests_raises_the_threshold` | zwei grüne Tests; committed `min_tests=50` | `full --env lichter` | Exit 6. R |
| `..._local_min_tests_raises_the_threshold` | zwei grüne Tests; lokale `min_tests=50` | `full` | Exit 6. R |
| `..._min_tests_option_raises_the_threshold` | zwei grüne Tests | `full --min-tests 50` | Exit 6. R |
| `..._write_baseline_writes_at_least_the_effective_minimum` | vier grüne Tests; committed `min_tests=3`, lokal `1` | `full --write-baseline` | lokale Datei fordert danach `min_tests=3` (Maximum aller Quellen). R |

### 5.3 `tests/unit/test_ap7_korbat_report.py` (6)

| Fall | Vorbedingung | Aktion | Erwartung |
| --- | --- | --- | --- |
| `test_report_contains_a_module_entry_for_every_module` | grünes + rotes Fixture-Modul | Läufer mit `--report` | Exit 1 (unverändert); Bericht mit `modules`/`total_tests`; je Modul Eintrag mit allen sechs Feldern. R |
| `test_green_module_entry_has_count_and_no_error_details` | grünes Modul mit zwei Tests | `--report` | `tests=2`, `passed=true`, `returncode=0`, `error_class`/`error_message` null. R |
| `test_red_module_entry_reports_class_and_message` | rotes Modul `self.fail("AP7-REPORT-ROT")` | `--report` | `passed=false`, `returncode≠0`, `error_class="AssertionError"`, Meldung enthält Marker. R |
| `test_total_tests_matches_the_text_summary` | drei Tests in zwei Modulen | `--report` | `total_tests` = Zahl der `Gesamt:`-Zeile = 3. R |
| `test_text_output_and_exit_code_stay_unchanged_without_report` | gleiche Fixture mit/ohne Option | beide Läufe | gleicher Exitcode und Text (ohne Laufzeiten); ohne `--report` keine JSON-Datei. R |
| `test_green_run_writes_a_report_and_exits_0` | nur grüne Module | `--report` | Exit 0; alle Einträge bestanden, `total_tests=2`. R |

### 5.4 `tests/unit/test_ap7_korbat_rules.py` (13)

| Fall | Vorbedingung | Aktion | Erwartung |
| --- | --- | --- | --- |
| `GeneralRulesTest.test_rules_contain_the_baseline_discipline_exactly_once` | `GENERAL_RULES` aus `bin/vibe` (isoliertes `VIBE`/`HOME`) | Überschrift zählen | genau 1 Vorkommen von „Baseline-Disziplin (verbindlich)“. R |
| `..._fixes_exit_codes_in_the_code` | Sektion Baseline-Disziplin | Sektion lesen | enthält `Exit 7`, `Exit 6`, `Code`, `Baseline` (Fehler am Code beheben). R |
| `..._requires_monotone_reviewed_changes` | Sektion | lesen | enthält `monoton`, `VERIFY_MIN_TESTS`, `erhöhen`, `grün`, `Merge-Request`, `nie im Alleingang`. R |
| `..._makes_write_baseline_a_local_proposal` | Sektion | lesen | enthält `--write-baseline`, „unversioniert/ignoriert“, `Merge-Request`. R |
| `..._forbids_environment_details` | Sektion | lesen | enthält `IP-Adressen`, `Hostnamen`, `Geheimnisse`, `absolute Pfade`, `öffentlich`. R |
| `..._forbids_self_reference` | Sektion | lesen | enthält `VERIFY_QUICK`, `VERIFY_PACKAGE`, `VERIFY_FULL`, `Rekursionsschutz`, `Exit 3`. R |
| `..._efficiency_section_names_verify_sh_as_the_single_interface` | Sektion Effizienz | lesen | enthält `verify.sh`, `quick\|package\|full`, `Prüfschnittstelle`, `genau einmal`, `Nachweisumfang`, `abgeschwächt`. R |
| `..._all_templates_carry_the_baseline_discipline` | alle `templates/*/AGENTS.md` (genau 5) | Block vergleichen (`subTest` je Vorlage) | `GENERAL_RULES` byte-gleich enthalten; je genau ein Markerpaar und eine Baseline-Sektion. R (5 Einträge) |
| `..._repository_agents_file_carries_the_baseline_discipline` | Repository-`AGENTS.md` | Marker und Block prüfen | Datei vorhanden; Block byte-gleich; je genau einmal Markerpaar + Baseline-Sektion. R (Umgebungsabhängigkeit §4.3) |
| `CommittedBaselineManifestTest.test_manifest_has_schema_v1_and_the_initial_values` | committed `tests/verify-baseline.json` | JSON lesen | `version=1`, `min_tests=2000`, `envs={}`. R |
| `..._has_only_the_minimal_top_level_fields` | dieselbe Datei | Schlüssel prüfen | genau `{version, min_tests, envs}`. R |
| `..._contains_no_environment_details_or_secrets` | dieselbe Datei (fehlt in der Rotphase) | Datei-Existenz prüfen, dann Text scannen | **kein ERROR**: saubere Assertion „Datei fehlt“; sonst keine IPs, kein Hostname, keine absoluten Pfade, keine Geheimnis-Schlüssel. R |
| `..._min_tests_is_a_ratchet_floor` | dieselbe Datei | Schwelle prüfen | `min_tests >= 2000`. R |

### 5.5 `tests/unit/test_ap7_korbat_runner.py` (5, echter `bin/vibe-run.sh`, Fake-Toolchain)

| Fall | Vorbedingung | Aktion | Erwartung |
| --- | --- | --- | --- |
| `TamperedProjectEnvTest.test_tampered_project_env_blocks_and_names_the_file` | Projekt mit transportierter `.vibe/project.env`; Agent schließt ab und hängt eine Zeile an (`FAKE_TAMPER=append:project.env`) | Läufer einmal | Exit ≠ 0; `BLOCKIERT`-Zeile nennt `.vibe/project.env`; kein `FERTIG`, keine `REPARATUR`, genau ein Agentenaufruf, kein lokaler Merge, Ticket offen. R |
| `..._identical_rewrite_is_not_a_block` | Agent schreibt `project.env` identisch neu | Läufer einmal | Exit 0, `FERTIG`, keine `BLOCKIERT`-Zeile (Inhaltsvergleich, nicht mtime). G |
| `UntouchedFilesTest.test_untouched_project_and_baseline_do_not_block` | `project.env` + `.vibe/verify-baseline`; keine Änderung | Läufer einmal | Exit 0; keine `BLOCKIERT`-Zeile; Bericht „Geschlossen: F1“. G |
| `TamperedBaselineTest.test_tampered_verify_baseline_blocks_and_names_the_file` | `.vibe/verify-baseline`; Agent verändert sie (`append:verify-baseline`) | Läufer einmal | Exit ≠ 0; `BLOCKIERT` nennt `.vibe/verify-baseline`; kein Merge, Ticket offen, keine Reparaturrunde. R |
| `MissingFileAtStartTest.test_baseline_created_by_the_agent_does_not_block` | keine Baseline beim Start; Agent legt sie an (`create:verify-baseline`) | Läufer einmal | Exit 0, `FERTIG` (best effort: fehlende Startdatei hat keinen Wächter). G |

### 5.6 `tests/unit/test_ap5_korbat_project_env_transport.py` — neue AP7-Fälle (3 von 9)

| Fall | Vorbedingung | Aktion | Erwartung |
| --- | --- | --- | --- |
| `test_verify_baseline_is_transported_read_only_and_excluded` | Projekt mit `.vibe/project.env` + `.vibe/verify-baseline`; Arbeitskopie ohne `.vibe` | `copy-notes` | Exit 0; Baseline byte-gleich in der Arbeitskopie; best effort keine Schreibbits; Exclude enthält beide Pfade je genau einmal. R |
| `test_verify_baseline_transport_is_idempotent` | `copy-notes` lief; Projekt-Baseline danach geändert | `copy-notes` erneut | Exit 0; Kopie mit neuem Stand; Exclude-Eintrag genau einmal. R |
| `test_sync_proof_never_writes_the_verify_baseline_back` | Baseline transportiert; Arbeitskopie lokal verändert; Ticket abgehakt | `sync-proof --project … --worktree … --id T1` | Exit 0; Projekt-Baseline byte-gleich; Arbeitskopie bleibt mit lokalem Inhalt liegen. R |
| (Bestand, 6 Fälle) | project.env-Transport, Exclude-Idempotenz, fehlende Datei, Read-only, kein Rückschreiben, keine Geheimnisse | `copy-notes`/`sync-proof` | unverändertes Verhalten. G |

### 5.7 `tests/unit/test_verify_script.py` — umgestellte AP7-Fälle (13 von 34)

| Fall | Vorbedingung | Aktion | Erwartung |
| --- | --- | --- | --- |
| `VerifyFullTest.test_full_rejects_a_run_without_executed_tests` | `VERIFY_TESTS=tests`, Modul ohne Testfall | `full` | Exit 6; Meldung nennt 0 Tests. R |
| `..._passes_with_real_tests_and_reports_the_count` | grüner Test in `VERIFY_TESTS` | `full` | Exit 0; `VERIFY_RESULT:` mit `tests=1`; OK-Zeile. R |
| `..._rejects_fewer_tests_than_configured` | ein grüner Test, `VERIFY_MIN_TESTS=2` | `full` | Exit 6; Meldung nennt Minimum 2. R |
| `VerifyPackageTest.test_package_runs_verify_quick_instead_of_package_or_full` | unterscheidbare Marker in `VERIFY_QUICK`/`VERIFY_PACKAGE`/`VERIFY_FULL` | `package` | Exit 0; Quick-Marker erscheint, Paket-/Full-Marker nicht. R |
| `..._requires_verify_quick_without_falling_back` | `VERIFY_QUICK` fehlt; `VERIFY_PACKAGE`/`VERIFY_FULL` würden Marker anlegen | `package` | Exit 3; Meldung nennt `VERIFY_QUICK`; kein Marker. R |
| `..._rejects_a_todo_placeholder` | `VERIFY_QUICK="echo TODO"` | `package` | Exit 3; Meldung nennt `VERIFY_QUICK` und `TODO`. R |
| `..._requires_test_files_when_package_tests_is_set` | `VERIFY_PACKAGE_TESTS=tests`, kein Testordner | `package` | Exit 6. R |
| `..._rejects_a_run_without_executed_tests` | `VERIFY_PACKAGE_TESTS=tests`, Modul ohne Testfall | `package` | Exit 6; Meldung nennt 0 Tests. R |
| `..._passes_with_real_tests_and_reports_the_count` | `VERIFY_QUICK="true"`, `VERIFY_PACKAGE_TESTS=tests` mit echtem Test | `package` | Exit 0; „Tests erkannt: 1“. R |
| `..._rejects_fewer_tests_than_configured` | dito, `VERIFY_MIN_TESTS=2` | `package` | Exit 6; Meldung nennt Minimum 2. R |
| `..._without_package_tests_requires_no_test_proof` | nur `VERIFY_QUICK` (statisch) | `package` | Exit 0; kein Testnachweis verlangt. R |
| `..._stays_static_even_when_verify_tests_is_set` | `VERIFY_TESTS=tests` gesetzt, `VERIFY_PACKAGE_TESTS` fehlt | `package` | Exit 0; Vollmodus-Einstellung macht Paketmodus nicht nachweispflichtig. R |
| `..._does_not_start_the_opencode_service` | `VERIFY_QUICK` mit Marker; Fake-`opencode` | `package` | Exit 0; Dienst wurde nicht gestartet. R |
| (Bestand, 21 Fälle) | Quick-Modus, Usage, Temp-Verzeichnis, Tmux-Isolation, Screenshot-Isolation, fehlende Werkzeuge, Repo-Quick-Check, `package`-Hilfe, `full`-Nachweiszwang | verschiedene | unverändertes Verhalten. G |

### 5.8 `tests/unit/test_project_management.py` — berührte/relevante Fälle

| Fall | Vorbedingung | Aktion | Erwartung |
| --- | --- | --- | --- |
| `TemplateRulesTest.test_general_rules_require_tiered_verification` | `GENERAL_RULES` | Sektion prüfen | `verify.sh`, `quick\|package\|full`, `Prüfschnittstelle`, Stufung, „genau einmal“, „während der Bearbeitung“, `Nachweisumfang`, `abgeschwächt`. R (AP7) |
| `..._all_shipped_project_templates_contain_the_verification_efficiency_rule` | fünf Vorlagen-`AGENTS.md` | Marker je Vorlage | gleiche Effizienz-Marker in allen Vorlagen. R (AP7) |
| `..._repository_agents_file_contains_the_verification_efficiency_rule` | Repository-`AGENTS.md` | Marker prüfen | gleiche Marker; Datei muss vorhanden sein. R (AP7, Umgebungsabhängigkeit §4.3) |
| `..._all_shipped_project_templates_contain_the_test_agent_rule` | fünf Vorlagen | Marker | `TESTER`, `test-agent`, `ausschließlich`, `Reviewer`. V |
| `..._all_shipped_project_templates_configure_the_tester` | fünf `.vibe/project.env` | Marker | `TESTER=test-agent`. V |
| `..._general_rules_require_an_independent_test_agent` | `GENERAL_RULES` | Marker | `TESTER`, `test-agent`, `ausschließlich`, Rollentrennung, „kein Nachweis“. V |
| `..._repository_agents_file_contains_the_test_agent_rule` | Repository-`AGENTS.md` | Marker | `TESTER`, `test-agent`, `ausschließlich`. V |
| `..._shipped_test_agent_template_is_complete` | `templates/common/.opencode/agents/test-agent.md` | Datei lesen/vergleichen/validieren | Datei gleich `TEST_AGENT_TEMPLATE`, Pflichtfelder, `agent_validate`. V (ERROR, Datei fehlt) |
| `InitTest.test_init_applies_a_new_template_type_without_code_changes` | neuer Vorlagentyp `custom` | `init` | Projekt-`project.env` = `TYPE=generic\nTESTER=test-agent\n`. V |
| `InitTest.test_init_adds_the_test_agent_and_tester_to_an_existing_project` | bestehendes Projekt | `init` | `test-agent.md` mit `mode: subagent`, `TESTER=test-agent`, `TYPE=generic`, Ausgabehinweis. V |
| (übrige 26 Fälle) | Discovery, Roots, Symlinks, Marker-Invariante, Cleanup-/Coding-Regeln | verschiedene | unverändertes Verhalten. G |

## 6. Ambiguitäten und Orchestrator-Entscheidungen D1–D3

| Entscheidung | Inhalt | Umsetzung in den Tests |
| --- | --- | --- |
| **D1** | Präzedenz `--baseline` > lokale `.vibe/verify-baseline` > committed `tests/verify-baseline.json`; **die erste Quelle mit passender Env-Sektion gilt exklusiv, kein Union**; das Ratchet-Minimum ist immer das Maximum über alle Quellen. | `EnvLabelTest.test_baseline_option_overrides_the_committed_manifest` (`--baseline` ersetzt die Manifest-Dateien), `test_verify_env_from_project_env_selects_the_section`, `test_similar_label_does_not_match`; `RatchetTest.*` (committed/lokal/`--min-tests`, effektives Maximum beim Schreiben). **Abdeckungslücke:** Kein Fall unterscheidet derzeit „erste passende Quelle exklusiv“ von „Union“ (z. B. lokale Sektion ohne Fehler vs. committed Sektion mit dem Fehler). Empfehlung: solchen Fall nachziehen, sobald die Implementierung steht; bis dahin gilt der Design-Brief als verbindlich. |
| **D2** | `--write-baseline` ändert das Laufurteil nicht: Mismatch + Fehler ⇒ lokale Datei wird geschrieben **und** Exit 7. | `EnvLabelTest.test_write_baseline_preserves_other_env_sections` prüft jetzt ausdrücklich Exit 7 und zusätzlich das Schreiben/Erhalten der Sektionen. |
| **D3** | Nur design-fixierte Schlüsselwörter prüfen (keine frei erfundenen Formulierungen). | Alle Marker in `test_ap7_korbat_rules` und `TemplateRulesTest.VERIFY_EFFICIENCY_RULE` stammen wörtlich aus dem Design-Brief (Abschnitt „AGENTS.md-Regeln“); Wortlaut-Polieren bleibt erlaubt, die Kernaussagen sind fixiert. Tests prüfen Marker, nicht komplette Sätze. |

Weitere geklärte Punkte/Entscheidungen:

- **Paketmodus:** `package` führt `VERIFY_QUICK` aus und liest `VERIFY_PACKAGE` nie als Befehl (Design „Modi-Inhalte“). Der Runner/Dashboard führt dagegen weiterhin `VERIFY_PACKAGE` aus der autoritativen `project.env` aus; die dokumentierte Nutzer-Verdrahtung ist der `verify.sh`-Wrapper. Fixtures in `test_verify_api_package.py` und `test_f31_verify_package_ui.py` modellieren genau das.
- **`VERIFY_FULL`:** wird von der Engine ignoriert (Hinweis, kein Fehler); `full` baut den Läuferaufruf selbst.
- **`VERIFY_TEST_PATTERN`:** entfällt; Zählung aus dem strukturierten Bericht/`VERIFY_RESULT`.
- **Exit 7 vor Exit 6:** bei gleichzeitigem Nachweismangel und Regression gewinnt 7.

## 7. Geplanter Grünlauf (identisch zum Rotlauf)

```bash
python3 -m unittest \
  tests.unit.test_ap7_korbat_verify \
  tests.unit.test_ap7_korbat_baseline \
  tests.unit.test_ap7_korbat_report \
  tests.unit.test_ap7_korbat_rules \
  tests.unit.test_ap7_korbat_runner \
  tests.unit.test_ap5_korbat_project_env_transport \
  tests.unit.test_verify_script \
  tests.unit.test_project_management -v
```

Erwartung für den Grünlauf:

- Alle AP7-Fälle grün (Zeilen mit „R“).
- **Weiterhin rot (dokumentiert, vorbestehend):** die 6 Fehlschläge + 1 ERROR aus §4.2 (TESTER/Test-Agent-Vorlagen-Drift, fehlende `templates/common/.opencode/agents/test-agent.md`). Diese sind **nicht** AP7-Umfang; ein vollständig grüner Lauf ist in diesem Paket nicht erreichbar, ohne fremde Tickets zu implementieren.
- Zusätzlich muss die nicht versionierte Repository-`AGENTS.md` den neuen verwalteten Block tragen (Läufer aktualisiert ihn beim Start über `ensure_general_rules`), sonst bleiben die zwei `repository_agents_file_*`-Fälle rot.
- Nicht im Rotlauf enthalten und erst nach der Implementierung auszuführen:
  - `tests/unit/test_verify_api_package.py` (echtes Dashboard über HTTP, temporäres `HOME`/`VIBE`, freier Port),
  - `tests/browser/test_f31_verify_package_ui.py` (Playwright/Chromium, Screenshot).

  **Warnung:** In der Rotphase würde `test_verify_api_package`/die Browser-Abnahme wegen der Wrapper-Verdrahtung in die alte `verify.py`-Rekursion laufen (alter Paketmodus führt `VERIFY_PACKAGE` aus, das wieder `verify.sh` aufruft). Deshalb wurden sie in dieser Runde bewusst nicht ausgeführt.

## 8. Tatsächlich ausgeführte Befehle und Ergebnisse

| Befehl | Ergebnis |
| --- | --- |
| `python3 -m py_compile tests/unit/test_ap7_korbat_rules.py tests/unit/test_ap7_korbat_baseline.py tests/unit/test_verify_api_package.py tests/browser/test_f31_verify_package_ui.py` | Exit 0 |
| `python3 -m unittest tests.unit.test_ap7_korbat_rules -v` (nach Fixture-Fix) | Exit 1; `Ran 13 tests in 0.142s`, `FAILED (failures=17)` = 13 Test-Fehlschläge + 4 zusätzliche `subTest`-Einträge, **0 ERROR**. Protokoll: `/tmp/.../round3-rules.log` |
| `python3 -m unittest tests.unit.test_ap7_korbat_baseline.EnvLabelTest.test_write_baseline_preserves_other_env_sections -v` | Exit 1; 1 Test, 1 Fehlschlag: `7 != 2 : FEHLT: Unbekannte Option: --env` (D2-Assertion greift, Fehlerbild ist die fehlende Option). Protokoll: `/tmp/.../round3-d2.log` |
| `python3 -m unittest tests.unit.test_project_management.TemplateRulesTest tests.unit.test_project_management.InitTest -v` | Exit 1; `Ran 28 tests in 0.323s`, `FAILED (failures=9, errors=1)` — exakt die in §4.2 klassifizierten vorbestehenden Fälle. Protokoll: `/tmp/.../round3-pm.log` |
| Volle Rotphase (Befehl aus §3.1) | Exit 1; `Ran 147 tests in 40.335s`, `FAILED (failures=89, errors=1)`. Protokoll: `/tmp/opencode/vibe-sandbox/vibe-c7188db792/tmp/opencode/round3-redphase.log` |
| `git cat-file -e d4c24ee:<pfad>` für die Vorlagen-/Baseline-Dateien | `AGENTS.md` und `.vibe/project.env` je Exit 0; `templates/common/.opencode/agents/test-agent.md` Exit 128 |
| `git show d4c24ee:templates/<typ>/.vibe/project.env \| grep -c '^TESTER='` | 0 für alle fünf Vorlagen |
| `git show d4c24ee:bin/vibe \| grep -c TEST_AGENT_TEMPLATE` | 0 |
| `git diff --stat d4c24ee -- templates bin scripts` | leer (keine Produktionsänderung) |
| `git status --porcelain` | 6 geänderte, 6 neue Testdateien (siehe §1/§2); keine Produktionsdateien |

Nicht ausgeführt: Playwright-/Browserabnahme und Dashboard-API-Test (Begründung §7), `scripts/verify.sh`
gegen die produktive Installation, alle Modell-/MCP-/Netzaufrufe.

## 9. Offene Punkte, Grenzen, Hinweise an Coding-Agent/Orchestrator

1. **Vorbestand bleibt rot:** `test_project_management` (6 FAIL + 1 ERROR) und die fehlende
   `templates/common/.opencode/agents/test-agent.md`/`TEST_AGENT_TEMPLATE` sind nicht AP7.
   Der Reviewer darf daraus keine AP7-Regression ableiten.
2. **`AGENTS.md` ist nicht versioniert:** Der geforderte Regelblock in der Repository-`AGENTS.md`
   ist nur auf der Platte wirksam (Harness). Der Grünlauf braucht `ensure_general_rules` (Läuferstart)
   oder eine manuelle Aktualisierung; die versionierte Wahrheit liegt in `GENERAL_RULES`/Vorlagen.
3. **D1-Union-Lücke:** siehe §6; bitte bei der Implementierung strikt „erste passende Quelle exklusiv“
   umsetzen. Auf Wunsch zieht der Test-Agent einen diskriminierenden Fall nach.
4. **Nutzer-Verdrahtung:** Für den Endgate/Agentenlauf muss die autoritative `.vibe/project.env`
   (im Arbeitsbaum nur lesbar transportiert) auf `VERIFY_PACKAGE="bash scripts/verify.sh package"` und
   `VERIFY_FULL="bash scripts/verify.sh full"` (plus `VERIFY_ENV`) umgestellt werden; der aktuelle
   Worktree-Stand ruft `verify.sh` dort noch nicht auf. Das ist ein dokumentierter Nutzerschritt
   (Design T-V20), kein Testfehler; ohne ihn nutzt der Läufer die neue Baseline-Logik nicht.
5. **`test_f31_verify_package_ui.py` erzeugt** weiterhin den Screenshot
   `docs/features/F31-paketpruefung.png` (bestehendes Verhalten, nicht Teil des Commits).
6. **bwrap/Chromium:** Die Browserabnahme ist in dieser Umgebung nicht ausgeführt; eine Aussage über
   das tatsächliche UI-Verhalten ist damit nicht belegt.
7. **Fixture-Strenge:** `test_all_templates_carry_the_baseline_discipline` fordert wie das Design genau
   fünf Vorlagen; ein sechster Vorlagentyp würde den Fall bewusst rot machen.

## 10. Status (Runde 3)

**`complete`** für diese Runde (Testvorbereitung): Fixture-Fehler behoben und belegt, Vorbestand
read-only klassifiziert, Rotphase mit sauberem Gesamtlauf dokumentiert, Bericht vollständig.
Die Tests bleiben erwartungsgemäß rot; die Grünphase ist Aufgabe der Implementierung.

---

## 11. Runde 4 — Defektbehebung im Testcode und Browserbefund

- **Scope:** ausschließlich Testdateien (`tests/unit/test_verify_api_package.py`) und dieser Bericht.
  Keine Produktionsdatei, kein Commit, kein Branch-Wechsel.
- **Gemeldeter Defekt:** `test_api_verify_rejects_an_unknown_mode_without_starting_a_run`
  scheiterte mit `AssertionError: 'quick-pruefung' unexpectedly found`.

### 11.1 Ursache (vorher)

Die Klasse `VerifyApiPackageTest` startet **ein** Dashboard für **alle** Fälle; das Prüfprotokoll
`<runtime>/proj.verify.log` ist damit klassenweit geteilt. Der alphabetisch zuerst laufende Fall
`test_api_verify_accepts_package_and_runs_the_check_interface` schreibt dort legitim
`echo quick-pruefung` / `quick-pruefung` hinein. Die Negativprobe des zweiten Falls prüfte den
Marker jedoch gegen das **gesamte** Protokoll:

```python
self.assertNotIn(VERIFY_QUICK_MARKER, after or "",
                 "Unbekannter Modus fiel still auf quick zurück")
```

Damit war die Assertion unerfüllbar, sobald der erste Fall in derselben Klasse gelaufen war —
also immer im Modulslauf (isoliert lief der Fall zufällig grün, weil das Protokoll noch fehlte).
Das war ein Fehler **im Test**, nicht im Produktcode: die vorangehende Byte-Gleichheit
`assertEqual(before, after)` bewies bereits, dass der unbekannte Modus **nichts** geschrieben hatte.

### 11.2 Behebung (nachher)

Die Negativprobe ist jetzt auf den **Zuwachs seit dem Schnappschuss** begrenzt („distinkter
Marker“ im Sinne der Aufgabenstellung, ohne das geteilte Protokoll künstlich zu leeren):

```python
appended = (after or "") if before is None else after[len(before):]
for marker in (VERIFY_QUICK_MARKER, VERIFY_FULL_MARKER, VERIFY_PACKAGE_MARKER):
    self.assertNotIn(marker, appended,
                     f"Unbekannter Modus startete einen Prüflauf: {marker!r} neu im Protokoll")
```

**Prüfintention unverändert, nicht abgeschwächt:**

1. `assertEqual(before, after)` bleibt als stärkster Nachweis erhalten (byte-gleiches Protokoll ⇒
   kein Lauf, auch kein truncating Neustart).
2. Die Markerprüfung wirkt jetzt auf den neu angehängten Text und deckt zusätzlich `full`/`package`
   als stille Fallbacks ab — vorher nur `quick`.
3. Ist das Protokoll vor dem Aufruf noch nicht vorhanden (`before is None`), wird der komplette
   neue Inhalt geprüft; ein stiller `quick`-Fallback würde dort sofort auffallen (statt wie zuvor
   durch `after or ""`-Sonderlogik gar nicht).

Hilfsprüfung der Delta-Logik (Wegwerf-Skript im Temp-Verzeichnis, keine Datei im Repo):
`before=None`, `after="$ echo quick-pruefung…"` ⇒ erkannt; `before="alt\n"`,
`after="alt\n$ echo quick-pruefung…"` ⇒ erkannt.

### 11.3 Ausgeführte Befehle

| Befehl | Ergebnis |
| --- | --- |
| `python3 -m unittest tests.unit.test_verify_api_package -v` **vor** der Behebung | **Exit 1**; `Ran 2 tests`, `FAILED (failures=1)` — exakt der gemeldete `AssertionError: 'quick-pruefung' unexpectedly found` (Reproduktion bestätigt) |
| `python3 -c "import playwright"` | **Exit 0** (`playwright` 1.65.2 unter `/opt/custom/vibe-dev/.venv`) |
| `python3 -m playwright --version` / `ls ~/.cache/ms-playwright` | 1.65.2; `chromium-1255`, `chromium_headless_shell-1255` vorhanden |
| `python3 -m unittest tests.unit.test_verify_api_package -v` **nach** der Behebung | **Exit 0**; `Ran 2 tests in 3.23s`, `OK` |
| `python3 -m unittest tests.unit.test_verify_api_package.VerifyApiPackageTest.test_api_verify_rejects_an_unknown_mode_without_starting_a_run -v` (isoliert, Protokoll fehlt) | **Exit 0**; `Ran 1 test in 7.83s`, `OK` — Fall ist unabhängig von der Fallreihenfolge |
| `VIBE_VERIFY_SCREENSHOT_DIR=<tmp>/ap7-shots python3 -m unittest tests.browser.test_f31_verify_package_ui -v` | **Exit 0**; `Ran 1 test in 6.06s`, `OK` — Knopf „Check package“ sichtbar, Ausgabe enthält den `VERIFY_QUICK`-Marker und `verify.sh`, `full`-Marker fehlt; Screenshot in das Temp-Verzeichnis umgeleitet (kein Artefakt im Repo) |

Der Browserfall ist damit **tatsächlich ausgeführt**, nicht nur kompiliert: Playwright/Chromium
steht in dieser Umgebung bereit (anders als in früheren Paketen vermutet).

### 11.4 Grenzen

- Die Browserabnahme belegt das Verhalten nur für Chromium/headless in dieser Umgebung; andere
  Browser und echte Bedienung per Tastatur sind nicht geprüft.
- Der Screenshot `docs/features/F31-paketpruefung.png` entsteht beim Standardaufruf weiterhin im
  Repo (bestehendes Verhalten); für diesen Lauf wurde er bewusst in ein Temp-Verzeichnis umgeleitet.
- Kein vollständiger `scripts/verify.sh full`-Lauf in dieser Runde (nur die gezielten Module laut
  Auftrag); die Paketprüfung bleibt dem Läufer vorbehalten.

### 11.5 Status

**`complete`** für Runde 4: Testdefekt reproduziert, sauber behoben, beide Fälle (und der Fall
isoliert) grün; Browserfall ausgeführt und grün; keine Produktionsdatei berührt.

---

## 12. Runde 5 — Lösch-Tampering (T-V21) und D1-Exklusivität

- **Scope:** ausschließlich Testdateien (`tests/unit/runner_support.py`,
  `tests/unit/test_ap7_korbat_runner.py`, `tests/unit/test_ap7_korbat_baseline.py`) und dieser
  Bericht. Keine Produktionsdatei, kein Commit, kein Branch-Wechsel.
- **Anlass:** Review Runde 1 (`docs/reviews/AP7-Korbat-review-1.md`), zwei testseitige Punkte:
  der fehlende Löschfall im Hash-Wächter (Minor 1) und die fehlende diskriminierende
  D1-Absicherung (Minor 3). Der dritte Punkt (Doku-Widerspruch zur Browserabnahme) betrifft
  `docs/features/AP7-Korbat.md` und liegt nicht im Testauftrag.

### 12.1 Geänderte Testdateien

| Datei | Änderung |
| --- | --- |
| `tests/unit/runner_support.py` | `FAKE_TAMPER` kennt zusätzlich `delete:<dateiname>`: die Agentenattrappe entfernt eine transportierte `.vibe`-Datei (`unlink`, bei Bedarf vorher `chmod 0o644`; eine bereits fehlende Datei bleibt folgenlos wie `rm -f`). Bestehende Aktionen (`append`, `rewrite`, `create`) unverändert. |
| `tests/unit/test_ap7_korbat_runner.py` | Neue Klasse `DeletedTransportedFileTest` mit 2 Fällen; `MissingFileAtStartTest` um den Negativfall `test_deleting_an_absent_baseline_does_not_block` ergänzt. Keine bestehende Assertion abgeschwächt. |
| `tests/unit/test_ap7_korbat_baseline.py` | Neue Klasse `LocalBaselinePrecedenceTest` mit 3 Fällen; Modul-Docstring um den D1-Grundsatz ergänzt. Keine bestehende Assertion abgeschwächt. |

### 12.2 Fall 1 — Lösch-Tampering (erwartet ROT, offener Reviewbefund)

**Name:** `DeletedTransportedFileTest.test_deleted_verify_baseline_blocks_and_names_the_file`

- **Vorbedingung:** Projekt mit transportierter `.vibe/verify-baseline` (beim Paketstart vorhanden,
  vom Transport auf `0444` gesetzt); der nachgebildete Agent schließt das Paket vollständig ab
  (Commits, Ticket, Feature-Doku, Review) und löscht dabei die transportierte Datei
  (`FAKE_TAMPER=delete:verify-baseline`).
- **Aktion:** `bin/vibe-run.sh` einmal gegen das Fixture-Projekt ausführen (Fake-Toolchain, eigenes
  `HOME`/`VIBE`, keine Modellaufrufe).
- **Erwartetes Ergebnis:** Exit ≠ 0; eine `BLOCKIERT`-Zeile nennt `.vibe/verify-baseline`; keine
  Reparaturrunde (genau ein Agentenaufruf), kein `FERTIG`, kein lokaler Merge, Ticket bleibt offen.
- **Produktbedeutung:** Das Entfernen der Baseline darf nicht unbemerkt bleiben — sonst könnte ein
  Agent eine unbequeme Abnahmeschwelle oder bekannte Fehlerliste „aufräumen", statt sie zu erfüllen.

**Name:** `DeletedTransportedFileTest.test_deleted_project_env_blocks_and_names_the_file`
(analog für `.vibe/project.env`, `FAKE_TAMPER=delete:project.env`; Erwartung: Block mit Nennung der
Datei, kein Merge). Produktbedeutung: Die autoritative Projektkonfiguration darf nicht unbemerkt aus
der Arbeitskopie verschwinden.

**Gegenprobe (Best-effort bleibt):**
`MissingFileAtStartTest.test_deleting_an_absent_baseline_does_not_block` — Projekt ohne
`.vibe/verify-baseline`, `FAKE_TAMPER=delete:verify-baseline` (folgenlos): Erwartung Exit 0, `FERTIG`,
kein `BLOCKIERT`.

**Tatsächliches Ergebnis (gegen den aktuellen Stand):**

- `python3 -m unittest tests.unit.test_ap7_korbat_runner.DeletedTransportedFileTest -v`
  → **Exit 1**, `Ran 2 tests in 5.808s`, `FAILED (failures=2)`.
  Auszug:
  ```
  AssertionError: 0 == 0 : ... === Agent beendet, Exit-Code 0 ===
  === Paketprüfung für F1 ===
  OK: Abschlussschranke für F1 erfüllt.
  ...
  FERTIG: Abnahme bestanden. Jetzt selbst auf dem Zielgerät prüfen.
  ```
  Beide Läufe enden also grün, obwohl die beim Start vorhandene transportierte Datei nach dem
  Agentenlauf fehlt. Genau der Reviewbefund: `bin/vibe-run.sh` prüft `[ -f ... ]` und überspringt
  den Hash-Vergleich, wenn die Datei verschwunden ist (`bin/vibe-run.sh:1646`, `1651`).
- Gegenprobe im selben Modullauf: `test_deleting_an_absent_baseline_does_not_block` ist **grün** —
  die Best-effort-Semantik bleibt unangetastet und der neue Fall ist kein Fehlalarm.
- **Nachweis, dass die Attrappe wirklich löscht** (sonst wäre das Rot nicht aussagekräftig):
  `FAKE_OPENCODE` in einem Wegwerf-Repo mit `0444`-Datei und `FAKE_TAMPER=delete:verify-baseline`
  direkt aufgerufen → Agenten-Exit 0, `.vibe/` leer, Meldung `DELETED_OK`. Das Rot stammt damit aus
  dem fehlenden Wächter, nicht aus einer wirkungslosen Attrappe.

**Einordnung: ROT = offener Reviewbefund.** Die Fälle bleiben rot, bis der Hash-Wächter auch das
Fehlen einer beim Start vorhandenen Datei als Manipulation wertet (Review-Minor 1). Der Fix gehört
dem Coding-Agenten; die Tests werden hier nicht abgeschwächt.

### 12.3 Fall 2 — D1-Exklusivität (erwartet GRÜN, Absicherung)

**Name:** `LocalBaselinePrecedenceTest.test_local_env_section_overrides_the_committed_section`

- **Vorbedingung:** committed `tests/verify-baseline.json` kennt den Fehler von `tests.test_rot`
  (über den dokumentierten `--write-baseline`-Weg erzeugt, also ohne hartcodierte Signatur); die
  lokale `.vibe/verify-baseline` besitzt **dieselbe** Env-Sektion `lichter`, aber mit **leerer**
  Failure-Liste; `tests/test_rot.py` schlägt rot.
- **Aktion:** `full --env lichter` ausführen.
- **Erwartetes Ergebnis:** Exit 7, kein `BASELINE-OK`, `tests.test_rot` in der Ausgabe.
- **Fehlerfall (Union):** Würden die Sektionen vereinigt, gälte der committed Fehler weiter als
  bekannt → Exit 0 und die Regression bliebe unbemerkt.

**Name:** `LocalBaselinePrecedenceTest.test_disjoint_local_and_committed_failures_are_not_united`
— lokale Sektion kennt nur einen anderen, nicht auftretenden Fehler (`tests.test_alt`), committed
kennt den tatsächlichen. Erwartung ebenfalls Exit 7 ohne `BASELINE-OK`; bei Union wäre der Lauf grün.

**Gegenprobe:** `LocalBaselinePrecedenceTest.test_local_empty_section_keeps_a_green_run_green` —
grüner Lauf mit leerer lokaler Sektion über einer committed Sektion mit Fehler: Exit 0 (die
Exklusivität blockiert keinen gesunden Lauf).

**Tatsächliches Ergebnis:**

- `python3 -m unittest tests.unit.test_ap7_korbat_baseline.LocalBaselinePrecedenceTest -v`
  → **Exit 0**, `Ran 3 tests in 5.621s`, `OK`.
- `python3 -m unittest tests.unit.test_ap7_korbat_baseline` → **Exit 0**, `Ran 23 tests in 32.435s`,
  `OK` (alle bisherigen 20 Baseline-Fälle unverändert grün).
- **Diskriminationsnachweis (Union-Kontrolle):** Dasselbe Fixture, aber mit lokaler Sektion =
  Vereinigung (`failures` = committed Fehler) liefert `exit=0`, `BASELINE-OK: bekannte
  fehlgeschlagene Module`, `VERIFY_RESULT: mode=full tests=1 failed_modules=1 baseline_ok=1
  env=lichter`. Die neuen Fälle (Erwartung Exit 7, kein `BASELINE-OK`) wären bei Union-Verhalten
  also eindeutig rot.

**Einordnung: GRÜN = Absicherung einer bereits korrekt implementierten Annahme.** Der Review
bestätigt D1 in `scripts/verify_engine.py:555-563` (`select_failures`: erste Quelle mit Sektion gilt
exklusiv). Der Fall dokumentiert diese Zusage jetzt testseitig gegen ein späteres Union-Refactoring.

### 12.4 Ausgeführte Befehle

| Befehl | Ergebnis |
| --- | --- |
| `python3 -m unittest tests.unit.test_ap7_korbat_runner.DeletedTransportedFileTest -v` | **Exit 1**; `Ran 2 tests in 5.808s`, `FAILED (failures=2)` — beide Löschfälle laufen bis `FERTIG` (erwartetes Rot) |
| `python3 -m unittest tests.unit.test_ap7_korbat_runner -v` | **Exit 1**; `Ran 8 tests in 22.839s`, `FAILED (failures=2)` — ausschließlich die beiden neuen Löschfälle; die 6 bisherigen Fälle und der neue Best-effort-Negativfall sind grün. Wiederholung nach der Docstring-Ergänzung: `Ran 8 tests in 21.514s`, `FAILED (failures=2)`, dieselben zwei Fälle |
| `python3 -m unittest tests.unit.test_ap7_korbat_baseline.LocalBaselinePrecedenceTest -v` | **Exit 0**; `Ran 3 tests in 5.621s`, `OK` |
| `python3 -m unittest tests.unit.test_ap7_korbat_baseline` | **Exit 0**; `Ran 23 tests in 32.435s`, `OK` |
| `FAKE_OPENCODE` direkt mit `FAKE_TAMPER=delete:verify-baseline` in Wegwerf-Repo (`0444`) | Agenten-Exit 0; `.vibe/` leer; `DELETED_OK` (Attrappe löscht wirklich) |
| Union-Kontrolle desselben Baseline-Fixtures (temporäres Inline-Skript, keine Testdatei) | `exit=0`, `BASELINE-OK= True`, `VERIFY_RESULT: ... baseline_ok=1 env=lichter` (Union wäre grün ⇒ Fälle diskriminieren) |

Nicht ausgeführt: `bash scripts/verify.sh quick|package|full` (nicht Teil dieses fokussierten
Testauftrags; die Abnahme läuft über den Läufer), Browser-/Dashboard-Fälle (unverändert), alle
Modell-/MCP-/Netzaufrufe.

### 12.5 Grenzen

- Der Löschfall deckt die beiden transportierten Dateien (`.vibe/project.env`,
  `.vibe/verify-baseline`) und den Startzustand „vorhanden"/„fehlend" ab. Nicht geprüft ist die im
  Review ebenfalls erwähnte zweite Lücke — der Wächter läuft nur nach dem initialen `run_agent`,
  nicht nach `repair_round`; dafür fehlt derzeit ein Test (der Reparaturpfad wird erst nach grüner
  Paketprüfung betreten, also nach dem Wächter).
- Auf FUSE/NTFS können Unix-Rechte wirkungslos sein; der `0444`-Schreibschutz ist im Fall nur
  Nebenbedingung, nicht die geprüfte Zusage.
- Die D1-Fälle prüfen lokale Sektion gegen committed Sektion; die dritte Stufe der Präzedenz
  (`--baseline` > lokal) deckt weiterhin `test_baseline_option_overrides_the_committed_manifest` ab.

### 12.6 Status

**`partially complete`** für Runde 5: Fall 2 (D1-Exklusivität) ist grün und abgesichert; Fall 1
(Lösch-Tampering) ist bewusst **rot** und belegt den offenen Reviewbefund in `bin/vibe-run.sh` —
der Produktionsfix steht aus (Coding-Agent), danach müssen die beiden Fälle grün werden.
