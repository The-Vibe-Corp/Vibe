# F27 — Testbericht des Test-Agenten

Datum: 2026-11-09
Repository: `/var/mnt/data/Dokumente/Informatik/VibeCode/vibe`
Branch: `feature/f27-lauf-neustart`
Ausgangscommit: `7c5a76f`
Ticket: F27 „Unterbrochenen Lauf trotz nicht committeter Änderungen wieder
anstoßen“ (`FEEDBACK.md`), Kriterien zusätzlich aus `SPEC.md` und `AGENTS.md`.

## 0. Herkunft und Umfang dieses Berichts

Die beiden F27-Testdateien wurden in einer **früheren Sitzung des
Test-Agenten vor der Implementierung** geschrieben. In der vorliegenden
Sitzung habe ich sie unabhängig gelesen, ausgeführt und dokumentiert. Ich habe
in dieser Sitzung **keine Testdatei und keine Produktionsdatei geändert**, neu
angelegt, gelöscht oder abgeschwächt. Die Rotphase habe ich in dieser Sitzung
nicht selbst beobachtet, weil die Implementierung bereits vorhanden war; die
Angaben dazu stammen aus der früheren Sitzung und sind als solche
gekennzeichnet (Abschnitt 5).

Unveränderte Prüfsummen der geprüften Dateien:

```
dd6334c303c84718ef5750cae54b3c0cf14ff4292f424da57bfdc07703e7e231  tests/unit/test_f27_keep_changes.py
ba0a2315336fa11caa5074e660bb5811dfc007d92d5e8452c9961f3ee519e87a  tests/browser/test_f27_keep_changes_ui.py
1865993010ac8cddecc2202659f85b3d238d7bee225bf4fd2ec473c776bdc60c  tests/unit/runner_support.py
```

`tests/unit/runner_support.py` ist gegenüber `7c5a76f` unverändert
(`git diff --stat 7c5a76f -- tests/unit/runner_support.py` leer) und wurde für
F27 nur mitbenutzt.

## 1. Testdateien und Testfälle

| Datei | Testfälle | Stand |
|---|---|---|
| `tests/unit/test_f27_keep_changes.py` | 14 | unverändert aus früherer Test-Agent-Sitzung |
| `tests/browser/test_f27_keep_changes_ui.py` | 2 | unverändert aus früherer Test-Agent-Sitzung |

Zuordnung der Akzeptanzkriterien aus dem Ticket:

* **A1** `vibe run <projekt> --keep-changes` startet trotz Änderungen; kein
  Stage, Commit, Stash, Checkout oder Wiederherstellen.
* **A2** Ohne ausdrückliche Option blockiert der Preflight weiterhin.
* **A3** Andere Preflight-Befunde blockieren auch mit der Option.
* **A4** Der verwaltete `AGENTS.md`-Block wird bei uncommitteten Änderungen
  nicht überschrieben; verständliche Warnung, Nutzeränderung bleibt.
* **A5** Das Dashboard bietet dieselbe Aktion und nennt die zurückbehaltenen
  Dateien.
* **A6** Die Abschlussprüfung bleibt streng und blockiert einen unsauberen
  Integrationsstand.

## 2. Testfälle

### 2.1 Unit (`tests/unit/test_f27_keep_changes.py`)

| # | Testname | Akzeptanz | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|---|---|
| 1 | `PreflightAllowDirtyTest.test_dirty_tree_is_rejected_by_default_and_allowed_only_explicitly` | A1, A2, A3 | Temporäres Git-Repository mit gültiger `.vibe/project.env`; unversionierte Datei `unfertig.txt`. | `preflight_errors` je ohne Argument, mit `allow_dirty=False` und `allow_dirty=True`. | Default und `False` melden „Arbeitsbaum“ und `unfertig.txt`; `True` liefert keine Arbeitsbaum-Meldung und insgesamt `[]`. |
| 2 | `PreflightAllowDirtyTest.test_other_findings_still_block_with_allow_dirty` | A3 | Fünf Projekte: kein Repository, detached HEAD, fehlender `TESTER`, unbekannter `REVIEWER`, fehlende Paketprüfung; jeweils unsauber. | `preflight_errors(..., allow_dirty=True)`. | Jeder andere Befund bleibt als Fehler erhalten („Kein Git-Repository“, „Detached HEAD“, „TESTER“, „REVIEWER“, „Paketprüfung fehlt“); keine Arbeitsbaum-Blockade. |
| 3 | `PreflightAllowDirtyTest.test_assist_preflight_passes_a_dirty_tree_only_with_allow_dirty` | A1, A2 | Repository mit unversionierter Datei. | `assist_preflight` mit `allow_dirty=False` bzw. `True`, `runtime=None`. | Streng: `action="unavailable"` mit Arbeitsbaum-Fehler. Erlaubt: `action="pass"`, `errors=[]`. |
| 4 | `RunnerKeepChangesTest.test_runner_without_keep_changes_blocks_on_dirty_tree` | A2 | Isolierte Testinstallation, Mini-Repository mit unsauberer Datei. | `bash vibe-run.sh <projekt>` ohne `VIBE_KEEP_CHANGES`. | Exit 2; Ausgabe nennt „Arbeitsbaum“ und `unfertig.txt`; kein Agentenaufruf. |
| 5 | `RunnerKeepChangesTest.test_keep_changes_starts_a_package_and_preserves_changes` | A1 | `AGENTS.md` committet, danach geändert; zusätzlich unversionierte `unfertig.txt`; Byte- und Status-Snapshot vor dem Lauf. | Läufer mit `VIBE_KEEP_CHANGES=1`, `VIBE_MAX_PACKAGES=1`. | Genau ein Agentenaufruf; Log nennt „Arbeitspaket F1“, Ausgabe „Geschlossen: F1“; Status und Bytes von `AGENTS.md`/`unfertig.txt` unverändert; nichts gestaged; `git stash list` leer; `unfertig.txt` nicht im HEAD; Status weiterhin ` M AGENTS.md` und `?? unfertig.txt`. |
| 6 | `RunnerKeepChangesTest.test_final_verification_still_blocks_a_dirty_integration_tree` | A6 | Projekt mit unsauberer Datei; `VERIFY_FULL` würde eine Markierungsdatei schreiben. | Läufer mit `VIBE_KEEP_CHANGES=1`, `VIBE_MAX_PACKAGES=1`. | Ein Paket startet; Exit 1; Ausgabe „Integrationsstand ist nicht sauber“ und `unfertig.txt`; Markierungsdatei der Gesamtprüfung fehlt. |
| 7 | `RunnerKeepChangesTest.test_other_findings_block_even_with_keep_changes` | A3 | Fünf fehlerhafte Projektvarianten wie Fall 2. | Läufer mit `VIBE_KEEP_CHANGES=1`, `VIBE_MAX_PACKAGES=1`. | Jeweils Exit 2 und der typspezifische Fehler; kein Agentenaufruf; keine Meldung `BLOCKIERT: Arbeitsbaum`. |
| 8 | `CliKeepChangesTest.test_cli_run_with_keep_changes_exports_the_intent` | A1 | Geladenes CLI-Modul mit isolierter Umgebung; tmux/Registry/Agentenpfade als Attrappen. | `vibe run proj --keep-changes`. | Ein `new-session`-Aufruf; enthält `VIBE_KEEP_CHANGES=1` und `VIBE_PREFLIGHT_ASSIST=1`; die Option erscheint nicht als Literal im Aufruf. |
| 9 | `CliKeepChangesTest.test_cli_run_without_keep_changes_does_not_export_the_intent` | A2 | Wie Fall 8. | `vibe run proj`. | Ein `new-session`-Aufruf; kein `VIBE_KEEP_CHANGES=1`; `VIBE_PREFLIGHT_ASSIST=1` bleibt erhalten. |
| 10 | `CliKeepChangesTest.test_cli_run_accepts_an_agent_before_keep_changes` | A1 | Wie Fall 8. | `vibe run proj test-agent --keep-changes`. | Ein `new-session`-Aufruf; `VIBE_KEEP_CHANGES=1` und `test-agent` enthalten; Option nicht als Literal. |
| 11 | `AgentsRulesTest.test_uncommitted_agents_change_is_not_rewritten_and_warns` | A4 | `AGENTS.md` mit altem verwaltetem Block committet, danach uncommittet geändert. | `cmd_run("proj")` mit echtem `ensure_general_rules`. | Ausgabe nennt `AGENTS.md` und warnt bzw. meldet „nicht aktualisiert“/„unverändert“; Datei bleibt byte-gleich zur Nutzeränderung; alter Block und Nutzertext bleiben; neuer `GENERAL_RULES`-Block fehlt; Status `M AGENTS.md`; genau eine tmux-Sitzung. |
| 12 | `AgentsRulesTest.test_clean_agents_file_is_still_updated` | A4 | `AGENTS.md` mit altem Block, Arbeitsbaum sauber. | `cmd_run("proj")` mit echtem `ensure_general_rules`. | Ausgabe meldet „aktualisiert“; Datei enthält den neuen `GENERAL_RULES`-Block, der alte Block ist ersetzt; genau eine tmux-Sitzung. |
| 13 | `WebRunApiTest.test_api_run_with_keep_changes_exports_intent_and_names_files` | A1, A5 | Echte Dashboard-Instanz auf freiem localhost-Port, tmux-Attrappe, Projekt mit `unfertig.txt`. | `POST /api/run {"name":"proj","keep_changes":true}`. | HTTP 200, `ok=true`, Meldung nennt `unfertig.txt`; genau ein `new-session` mit `VIBE_KEEP_CHANGES=1`; Git-Status unverändert. |
| 14 | `WebRunApiTest.test_api_run_without_keep_changes_does_not_export_the_intent` | A2, A5 | Wie Fall 13. | `POST /api/run {"name":"proj"}`. | HTTP 200, `ok=true`; genau ein `new-session`; kein `VIBE_KEEP_CHANGES=1`. |

### 2.2 Browser (`tests/browser/test_f27_keep_changes_ui.py`)

| # | Testname | Akzeptanz | Vorbedingung | Aktion | Erwartetes Ergebnis |
|---|---|---|---|---|---|
| 15 | `KeepChangesUiTest.test_dirty_project_offers_keep_changes_with_confirmation_and_files` | A5 | Dashboard auf eigenem Port, tmux-Attrappe, schmutziges Projekt `dirtyproj`, Headless-Chromium. | Detail öffnen, Schaltfläche „Trotz Änderungen starten“ anklicken, Bestätigung ausführen, auf Toast warten. | Schaltfläche sichtbar; Screenshot `docs/features/F27-trotz-aenderungen.png` entsteht und ist nicht leer; eine Bestätigung war erforderlich; Toast nennt `unfertig.txt`; genau ein `new-session` mit `VIBE_KEEP_CHANGES=1`; Dateiinhalt bleibt `unfertig\n`. |
| 16 | `KeepChangesUiTest.test_clean_project_does_not_offer_an_enabled_keep_changes_action` | A5 | Dashboard wie oben, sauberes Projekt `cleanproj`. | Detail öffnen und Schaltfläche suchen. | Falls die Schaltfläche existiert, ist sie weder sichtbar noch aktiviert. |

## 3. Tatsächlich ausgeführte Befehle und Ergebnisse

Alle Befehle wurden in dieser Sitzung im Repository ausgeführt.

### 3.1 F27-Unit-Tests

```
python3 -m unittest discover -s tests/unit -p 'test_f27_*.py' -v
```

Ergebnis: `Ran 14 tests in 4.304s`, `OK`, Exit 0.

### 3.2 F27-Browsertests

```
python3 -m unittest discover -s tests/browser -p 'test_f27_*.py' -v
```

Ergebnis: `Ran 2 tests in 2.074s`, `OK`, Exit 0. Der Test hat
`docs/features/F27-trotz-aenderungen.png` erzeugt bzw. aktualisiert
(153907 Bytes).

### 3.3 Schnellprüfung

```
bash scripts/verify.sh quick
```

Ergebnis: Manifest 57 Dateien OK, Syntax 115 Python-/8 Bash-/6 JSON-Dateien OK,
keine Geheimnisse erkannt, Exit 0.

### 3.4 Gezielte Prüfung der beiden Full-Fehler

```
python3 -m unittest tests.unit.test_ap04_setup_harness tests.unit.test_release -v
```

Ergebnis: `Ran 20 tests in 1.047s`, `FAILED (failures=2)`, Exit 1. Die beiden
Fehlschläge sind:

* `tests.unit.test_ap04_setup_harness.SetupHarnessTest.test_dry_run_explains_pi_and_its_install_command`
  — erwartet `@earendil-works/pi-coding-agent` in der Dry-Run-Ausgabe, gefunden
  wird nur der allgemeine Pi-Hinweis.
* `tests.unit.test_release.ReleaseBuildTest.test_repository_content_has_no_personal_home_paths_or_secrets`
  — findet fünf vorbestehende absolute Home-Pfade in `docs/features/B4.md`,
  `docs/features/B5.md`, `docs/features/F23.md` und
  `docs/reviews/V-023-review-2.md`.

## 4. Isolation

* **Keine echten Modelle / Router:** `opencode` und `package-agent` sind
  ausführbare Attrappen aus `runner_support.install_fake_tools`; der
  Agentenaufruf wird über `FAKE_CALLS`/`FAKE_COUNTER` protokolliert. Die
  CLI-Tests ersetzen `run`, `tmux_has`, `require_agent`,
  `run_agent_selection` und die Registry durch Attrappen; die API- und
  Browsertests nutzen eine tmux-Attrappe.
* **Kein echtes tmux:** CLI-Tests patchen die tmux-Aufrufe; API- und
  Browsertests stellen ein ausführbares `tmux`-Fake in den `PATH`, das
  `new-session`, `has-session` und `show-environment` beantwortet und die
  Aufrufe aufzeichnet.
* **Keine echten externen Dienste / kein Internet:** Die Web- und
  Browsertests binden ausschließlich an `127.0.0.1` auf einem freien Port.
  `curl` ist im Läufer-Test ebenfalls eine Attrappe.
* **Keine produktiven Nutzerdaten:** Alle Projekte, Home-Verzeichnisse,
  Laufzeit- und Zustandsverzeichnisse liegen in `tempfile.TemporaryDirectory`.
  `VIBE`, `HOME`, `XDG_CONFIG_HOME`, `VIBE_RUNTIME`, `VIBE_STATE` und
  `VIBE_AGENTS_DIR` werden überschrieben; geerbte `VIBE_*`-/`FAKE_*`-Werte
  werden entfernt.
* **Echtes Git** wird nur in den temporären Repositories verwendet. Das ist
  beabsichtigt, weil die Kernaussage (kein Stage/Commit/Stash/Checkout,
  unveränderte Bytes) ohne echtes Git nicht belastbar prüfbar wäre.

## 5. Rotphase (aus früherer Test-Agent-Sitzung, hier nicht erneut beobachtet)

Die Tests wurden vor der Implementierung geschrieben. In der früheren Sitzung
wurden folgende rote Stände belegt:

* Unit: `FAILED (failures=10, errors=3)` bei 14 Tests.
* Browser: `FAILED (errors=1)` bei 2 Tests.

Diese Zahlen sind übernommen und in dieser Sitzung **nicht** reproduziert
worden, da die Implementierung bereits im Arbeitsbaum liegt. Eine nachträgliche
Rotphase lässt sich daraus nicht ableiten; die damalige Beobachtung bleibt die
Grundlage für die Aussage „Tests vor der Implementierung“.

## 6. Aktueller Grünzustand

| Suite | Ergebnis |
|---|---|
| F27-Unit | 14 Tests, `OK`, Exit 0 |
| F27-Browser | 2 Tests, `OK`, Exit 0 |
| `verify.sh quick` | Exit 0 |

Die Tests sind in der aktuellen Form grün. Es wurden keine Assertions
abgeschwächt und keine Tests gelöscht oder übersprungen.

## 7. Baseline-Vergleich der zwei Full-Fehler

Zur unabhängigen Prüfung der übergebenen Angabe habe ich am Ausgangscommit
`7c5a76f` einen temporären, detachierten Worktree unter
`/tmp/opencode/f27-baseline-*` angelegt und dort dieselbe gezielte Suite
ausgeführt:

```
git worktree add --detach <tmp> 7c5a76f
cd <tmp>
python3 -m unittest tests.unit.test_ap04_setup_harness tests.unit.test_release -v
# Ran 20 tests in 1.011s
# FAILED (failures=2)
# FAIL: test_dry_run_explains_pi_and_its_install_command ...
# FAIL: test_repository_content_has_no_personal_home_paths_or_secrets ...
git worktree remove --force <tmp>
```

Ergebnis: exakt dieselben zwei Fehlschläge wie im aktuellen Arbeitsbaum. Die
betroffenen Testdateien und die in der Fehlermeldung genannten Dokumente sind
gegenüber `7c5a76f` unverändert. Die beiden Fehler sind damit **nicht durch
F27 verursacht**, sondern vorbestehend.

Die vollständige Suite (`verify.sh full`, laut Auftragskontext 1240 Tests,
2 Fehlschläge) habe ich in dieser Sitzung nicht erneut ausgeführt; geprüft und
reproduziert habe ich die beiden genannten Fehlschläge sowie den F27-Anteil.

## 8. Verbleibende Lücken

1. **CLI-Preflight-Option `--allow-dirty`:** Die Akzeptanzkriterien verlangen
   den Weg über `vibe run --keep-changes`; der direkte CLI-Aufruf
   `vibe preflight --allow-dirty` wird von den F27-Tests nicht separat geprüft.
   Das ist keine Lücke gegenüber dem Tickettext, aber gegenüber der
   Implementierungsdokumentation.
2. **Ende-zu-Ende-Kette CLI → tmux → Läufer:** Die CLI-Prüfung endet bei der
   Zusammensetzung des tmux-Aufrufs; der Läufer wird separat mit
   `VIBE_KEEP_CHANGES=1` geprüft. Eine einzige durchgehende Ausführung mit
   echtem tmux findet bewusst nicht statt (Isolation).
3. **CLI-Rückmeldung mit Dateinamen:** Die Web-API und das Dashboard werden
   darauf geprüft, dass die zurückbehaltenen Dateien genannt werden; für die
   reine CLI-Ausgabe von `vibe run` wird dies nicht separat assertiert.
4. **Sauberes Projekt im Browser:** Fall 16 akzeptiert sowohl „Schaltfläche
   fehlt“ als auch „vorhanden, aber unsichtbar/deaktiviert“. Er beweist damit
   die Nutzbarkeit nur negativ, nicht die exakte Darstellungsvariante.
5. **Screenshot:** Der Browsertest prüft Existenz und Größe des Screenshots,
   nicht dessen visuellen Inhalt. Eine visuelle Abnahme ist damit nicht
   ersetzt.
6. **Vollständige Suite:** Siehe Abschnitt 7; die zwei vorbestehenden Fehler
   bleiben bis zu einer separaten Bereinigung bestehen und sind nicht
   F27-spezifisch.

## 9. Änderungen durch diesen Bericht

In dieser Sitzung wurde ausschließlich diese Berichtsdatei
`docs/reviews/F27-test-agent-report.md` neu angelegt. Tests und
Produktionscode blieben unverändert. Es gab keinen Commit, keinen Push, keinen
Merge und keinen Stash.
